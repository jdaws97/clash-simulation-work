//! Search admission: plans.py:563-839, heroes.py:119, spells.py:60.
//! The search deliberately narrows the frozen oracle's capacities to 320/11/50/3.

use std::collections::{BTreeMap, BTreeSet};

use crate::catalog::Catalog;
use crate::compile::{CompileOptions, Compiler, TACTIC_DEFAULTS};
use crate::json::Json;
use crate::scoring::{PlanProvider, Scenario};
use crate::stats::{self, Level};

use super::genome::{normalize, ArmyGenome, HeroChoice, UnitCount};
use super::util::{array, numeric, object, string, text};

#[derive(Clone, Debug)]
pub struct EligibleUnit {
    pub name: String,
    pub housing: usize,
    pub level: i64,
    pub boosted: bool,
}

#[derive(Clone, Debug)]
pub struct EligibleRoster {
    pub troops: Vec<EligibleUnit>,
    pub spells: Vec<EligibleUnit>,
    pub sieges: Vec<EligibleUnit>,
    pub heroes: Vec<String>,
    pub equipment: BTreeMap<String, Vec<String>>,
    pub pets: Vec<String>,
}

#[derive(Clone, Debug)]
pub struct AccountRules {
    pub roster: EligibleRoster,
    pub spell_factory: i64,
    pub assumptions: Vec<String>,
}

fn owned(user: &Json, field: &str, name: &str) -> Option<i64> {
    user.get(field).and_then(|value| value.get(name))
        .and_then(|value| stats::num(value, None))
        .filter(|value| *value > 0.0).map(|value| value as i64)
}

fn raw_requirement(record: &Json, key: &str) -> f64 {
    record.at("attrs").get("raw").and_then(|raw| raw.get(key))
        .and_then(|value| stats::num(value, None)).unwrap_or(0.0)
}

impl AccountRules {
    pub fn load(catalog: &Catalog, compiler: &Compiler<'_>) -> Result<Self, String> {
        let user = &compiler.library.user;
        if numeric(user.at("levels"), "gm", 0.0) != 16.0 {
            return Err("armysearch currently requires the TH16 account".to_owned());
        }
        let mut assumptions = Vec::new();
        let spell_factory = if let Some(level) = user.at("levels").get("sf") {
            level.i64()
        } else {
            // Derive a lower bound from actual researched spells, not TH max.
            // Totem is owned and requires SF9 in the cached metadata.
            let mut required = 0.0_f64;
            for (name, level) in user.at("attack_levels").obj() {
                if level.f64() > 0.0 {
                    if let Some(record) = catalog.stats.registry.get(name) {
                        required = required.max(raw_requirement(record, "Spell Factory Level Required"));
                    }
                }
            }
            if required <= 0.0 || required > catalog.stats.max_level("Spell Factory", 16)
                .unwrap_or(0) as f64 {
                return Err("cannot derive a validated Spell Factory level from owned spells".to_owned());
            }
            assumptions.push(format!("Missing levels.sf: use validated lower bound {} from owned spell unlock requirements", required as i64));
            required as i64
        };
        let mut roster = EligibleRoster {
            troops: Vec::new(),
            spells: Vec::new(),
            sieges: Vec::new(),
            heroes: Vec::new(),
            equipment: BTreeMap::new(),
            pets: Vec::new(),
        };
        for (name, record) in catalog.stats.registry.obj() {
            if record.get("seasonal").is_some_and(Json::bool) {
                continue;
            }
            let kind = text(record, "kind", "");
            let boosted = record.get("super").is_some_and(Json::bool);
            let level = if boosted {
                let mut level = None;
                if let Some(raw) = record.at("attrs").get("raw") {
                    for (key, requirement) in raw.obj() {
                        if let Some(base) = key.strip_suffix(" Level Required") {
                            if let Some(value) = owned(user, "attack_levels", base) {
                                let minimum = stats::num(requirement, None).unwrap_or(f64::INFINITY);
                                if value as f64 >= minimum {
                                    level = Some(value);
                                    break;
                                }
                            }
                        }
                    }
                }
                level
            } else {
                let field = match kind {
                    "hero" => "hero_levels",
                    "equipment" => "equipment_levels",
                    "pet" => "pet_levels",
                    _ => "attack_levels",
                };
                owned(user, field, name)
            };
            let Some(level) = level else {
                continue;
            };
            let Some(row) = record.at("levels").arr().iter().find(|row| row
                .at("level") == &Json::Num(level as f64)) else {
                continue;
            };
            if catalog.stats.required_town_hall(name, &Level::Int(level)) > 16.0 {
                continue;
            }
            let mut available = true;
            for (building, key) in [
                ("Barracks", "barracks"),
                ("Dark Barracks", "dbarracks"),
                ("Workshop", "workshop"),
                ("Spell Factory", "sf"),
                ("Dark Spell Factory", "dsf"),
                ("Pet House", "pethouse"),
            ] {
                let actual = if key == "sf" {
                    spell_factory as f64
                } else {
                    numeric(user.at("levels"), key, 0.0)
                };
                if raw_requirement(record, &format!("{building} Level Required")) > actual {
                    available = false;
                }
            }
            let research = row.get("wiki").and_then(|wiki| wiki.get("Laboratory Level Required"))
                .and_then(|value| stats::num(value, None)).unwrap_or(0.0);
            if research > numeric(user.at("levels"), "lab", 0.0) || !available {
                continue;
            }
            match kind {
                "hero" => roster.heroes.push(name.clone()),
                "equipment" => {
                    let owner = record.at("attrs").get("raw").map_or("", |raw| text(raw, "User", ""));
                    roster.equipment.entry(owner.to_owned()).or_default().push(name.clone());
                }
                "pet" => roster.pets.push(name.clone()),
                "troop" | "super_troop" | "spell" | "siege" | "siege_machine" => {
                    let housing = if kind == "spell" {
                        numeric(record.at("attrs"), "housing", 0.0)
                    } else {
                        numeric(record.at("attrs"), "housing_ck", numeric(record.at("attrs"), "housing", 0.0))
                    };
                    let siege = crate::armies::is_siege(name);
                    if kind == "spell" && crate::plans::spell_key(name).is_none() {
                        continue;
                    }
                    if !siege && kind != "spell" && !catalog.units.contains_key(name) {
                        continue;
                    }
                    if !siege && (housing <= 0.0 || housing.fract() != 0.0) {
                        continue;
                    }
                    let unit = EligibleUnit {
                        name: name.clone(),
                        housing: housing as usize,
                        level,
                        boosted
                    };
                    if siege {
                        roster.sieges.push(unit);
                    } else if kind == "spell" {
                        roster.spells.push(unit);
                    } else {
                        roster.troops.push(unit);
                    }
                }
                _ => {}
            }
        }
        roster.heroes.sort();
        roster.heroes.retain(|hero| roster.equipment.get(hero).is_some_and(|items| items.len() >= 2));
        roster.pets.sort();
        for items in roster.equipment.values_mut() {
            items.sort();
        }
        roster.troops.sort_by(|a, b| a.name.cmp(&b.name));
        roster.spells.sort_by(|a, b| a.name.cmp(&b.name));
        roster.sieges.sort_by(|a, b| a.name.cmp(&b.name));
        if roster.heroes.len() < 4 || roster.pets.len() < 4 || roster.troops.is_empty() || roster.spells.is_empty() {
            return Err("insufficient supported account inventory".to_owned());
        }
        Ok(Self {
            roster,
            spell_factory,
            assumptions
        })
    }

    pub fn check(&self, genome: &ArmyGenome) -> Result<(), String> {
        for (values, roster, cap, label) in [
            (&genome.troops, &self.roster.troops, 320, "camp"),
            (&genome.spells, &self.roster.spells, 11, "spells"),
            (&genome.cc_troops, &self.roster.troops, 50, "CC troops"),
            (&genome.cc_spells, &self.roster.spells, 3, "CC spells"),
        ] {
            let mut total = 0usize;
            let mut seen = BTreeSet::new();
            for unit in values {
                let item = roster.iter().find(|item| item.name == unit.name)
                    .ok_or_else(|| format!("unavailable {label}: {}", unit.name))?;
                if unit.count == 0 || unit.count > cap || !seen.insert(&unit.name) {
                    return Err(format!("invalid count or duplicate {label}: {}", unit.name));
                }
                total += item.housing * unit.count;
            }
            if total > cap {
                return Err(format!("{label} housing {total} exceeds {cap}"));
            }
        }
        let boosts = genome.troops.iter().filter(|unit| self.roster.troops.iter()
            .any(|item| item.name == unit.name && item.boosted)).count();
        if boosts > 2 {
            return Err("more than two home boosted types".to_owned());
        }
        if let Some(siege) = &genome.siege {
            if !self.roster.sieges.iter().any(|unit| &unit.name == siege) {
                return Err(format!("unavailable siege: {siege}"));
            }
        }
        if genome.heroes.len() != 4 {
            return Err("exactly four heroes required".to_owned());
        }
        let mut heroes = BTreeSet::new();
        let mut pets = BTreeSet::new();
        for hero in &genome.heroes {
            if !self.roster.heroes.contains(&hero.hero) || !heroes.insert(&hero.hero) {
                return Err(format!("unavailable or duplicate hero: {}", hero.hero));
            }
            let equipment = &self.roster.equipment[&hero.hero];
            if hero.equipment[0] == hero.equipment[1] || hero.equipment.iter().any(|item| !equipment
                .contains(item)) {
                return Err(format!("unowned, duplicate, or wrong-owner equipment for {}", hero.hero));
            }
            if !self.roster.pets.contains(&hero.pet) || !pets.insert(&hero.pet) {
                return Err(format!("unowned or duplicate pet: {}", hero.pet));
            }
        }
        let plan = &genome.plan;
        if !plan.angle_offset.is_finite() || !(0.0..2.0 * std::f64::consts::PI).contains(&plan.angle_offset)
            || !plan.flank_offset.is_finite() || !(0.3..=1.6).contains(&plan.flank_offset)
            || !matches!(plan.charge_side.as_str(), "left" | "right")
            || !matches!(plan.snipe_mode.as_str(), "off" | "value" | "aggressive")
            || plan.tactics.iter().any(|value| !value.is_finite())
            || plan.step_timing.values().any(|value| !value.is_finite() || value.abs() > 4.0)
        {
            return Err("invalid or unbounded plan genes".to_owned());
        }
        for (index, low, high) in [(1, 0.4, 1.8), (4, 0.4, 1.6), (5, 0.3, 2.0), (9, 0.0, 7.999999), (10, 0.5, 4.0)] {
            if !(low..=high).contains(&plan.tactics[index]) {
                return Err(format!("tactic {index} outside supported bounds"));
            }
        }
        for index in 0..19 {
            if ![1, 4, 5, 9, 10].contains(&index) && plan.tactics[index] != TACTIC_DEFAULTS[index] {
                return Err(format!("inactive tactic {index} must remain frozen"));
            }
        }
        if let Some(program) = &plan.program {
            program.validate(genome)?;
        }
        Ok(())
    }

    /// Integer DP fills representable residual housing, including capacities
    /// whose eligible roster has no one-space filler. It never changes levels.
    pub fn repair(&self, genome: &mut ArmyGenome) -> Result<(), String> {
        repair_counts(&mut genome.troops, &self.roster.troops, 320, true);
        repair_counts(&mut genome.spells, &self.roster.spells, 11, false);
        repair_counts(&mut genome.cc_troops, &self.roster.troops, 50, false);
        repair_counts(&mut genome.cc_spells, &self.roster.spells, 3, false);
        if genome.siege.as_ref().is_some_and(|name| !self.roster.sieges.iter().any(|unit| &unit.name == name)) {
            genome.siege = self.roster.sieges.first().map(|unit| unit.name.clone());
        }
        let mut selected = BTreeSet::new();
        genome.heroes.retain(|hero| self.roster.heroes.contains(&hero.hero) && selected.insert(hero.hero.clone()));
        genome.heroes.truncate(4);
        for hero in &self.roster.heroes {
            if genome.heroes.len() == 4 {
                break;
            }
            if !genome.heroes.iter().any(|choice| &choice.hero == hero) {
                genome.heroes.push(HeroChoice {
                    hero: hero.clone(),
                    equipment: [String::new(), String::new()],
                    pet: String::new()
                });
            }
        }
        let mut pets = BTreeSet::new();
        for hero in &mut genome.heroes {
            let inventory = &self.roster.equipment[&hero.hero];
            for index in 0..2 {
                if !inventory.contains(&hero.equipment[index]) || (index == 1 && hero.equipment[0] == hero.equipment[1]) {
                    hero.equipment[index] = inventory.iter()
                        .find(|item| index == 0 || *item != &hero.equipment[0])
                        .ok_or("no compatible equipment")?.clone();
                }
            }
            if !self.roster.pets.contains(&hero.pet) || pets.contains(&hero.pet) {
                hero.pet = self.roster.pets.iter().find(|pet| !pets.contains(*pet))
                    .ok_or("no free pet")?.clone();
            }
            pets.insert(hero.pet.clone());
        }
        if genome.plan.family == "generic" && genome.plan.program.is_none() {
            genome.plan.tactics = TACTIC_DEFAULTS;
            genome.plan.step_timing.clear();
            genome.plan.charge_side = "left".to_owned();
            genome.plan.flank_offset = 0.9;
            genome.plan.snipe_mode = "value".to_owned();
        }
        genome.normalize();
        // Army repair precedes program fitting in operators::admit. Check the
        // repaired account choices here, then validate the reconciled program
        // at admission before it can enter the archive or a battle.
        let program = genome.plan.program.take();
        let checked = self.check(genome);
        genome.plan.program = program;
        checked
    }

    pub fn compile(
        &self,
        compiler: &Compiler<'_>,
        catalog: &Catalog,
        genome: &ArmyGenome,
        angle: f64,
        seed: i64,
    ) -> Result<Json, String> {
        let mut canonical = genome.clone();
        canonical.normalize();
        let genome = &canonical;
        self.check(genome)?;
        compatible(compiler, genome)?;
        let build = genome.to_build();
        let cited = genome.plan.family != "generic";
        let mut tactics = genome.plan.tactics;
        tactics[0] = angle;
        let options = CompileOptions {
            playbooks: cited,
            account: true,
            charge_side: Some(genome.plan.charge_side.clone()),
            flank_offset: genome.plan.flank_offset,
            overrides: object([("__opening__", object([("snipe_mode", string(&genome.plan.snipe_mode))]))]),
            tactics: cited.then(|| tactics.to_vec()),
        };
        let mut plan = compiler.plan_for_build(&build, angle, seed, &options)?;
        crate::armies::put(&mut plan, "label", string(format!(
            "armysearch {} (TH16, account levels, uncalibrated)",
            genome.plan.family,
        )));
        crate::armies::put(&mut plan, "strength", Json::Num(1.0));
        crate::armies::put(&mut plan, "observed", Json::Bool(false));
        crate::armies::put(&mut plan, "spell_factory_level", Json::Num(self.spell_factory as f64));
        let mut levels = plan.at("troop_levels").clone();
        for unit in genome.troops.iter().chain(&genome.cc_troops) {
            let selected = self.roster.troops.iter().find(|item| item.name == unit.name)
                .expect("checked roster");
            crate::armies::put(&mut levels, &unit.name, Json::Num(selected.level as f64));
        }
        if let Some(siege) = &genome.siege {
            let selected = self.roster.sieges.iter().find(|item| &item.name == siege).expect("checked siege");
            crate::armies::put(&mut levels, siege, Json::Num(selected.level as f64));
        }
        crate::armies::put(&mut plan, "troop_levels", levels);
        let mut cargo = Vec::new();
        for unit in &genome.cc_troops {
            let selected = self.roster.troops.iter().find(|item| item.name == unit.name)
                .expect("checked cargo");
            let level = receiving_level(catalog, &plan, &unit.name, selected.level);
            cargo.push(object([
                ("name", string(&unit.name)),
                ("count", Json::Num(unit.count as f64)),
                ("level", Json::Num(level as f64)),
            ]));
        }
        crate::armies::put(&mut plan, "cc_troops", Json::Arr(cargo));
        let mut cc_levels = object([]);
        for unit in &genome.cc_spells {
            let selected = self.roster.spells.iter().find(|item| item.name == unit.name)
                .expect("checked CC spell");
            let level = receiving_level(catalog, &plan, &unit.name, selected.level);
            crate::armies::put(&mut cc_levels, &unit.name, Json::Num(level as f64));
        }
        crate::armies::put(&mut plan, "cc_spell_levels", cc_levels);
        let mut steps = array(&plan, "steps").to_vec();
        for (id, offset) in &genome.plan.step_timing {
            let step = steps.iter_mut().find(|step| text(step, "id", "") == id)
                .ok_or_else(|| format!("timing gene step absent: {id}"))?;
            if step.get("uncited").is_some_and(Json::bool) || array(step, "cite").is_empty() {
                return Err(format!("timing gene requires cited step: {id}"));
            }
            if !shift_delay(step, *offset) {
                return Err(format!("timing gene requires dependency delay: {id}"));
            }
        }
        if cited {
            // fit_steps intentionally emits uncited leftovers (playbook.py:1313).
            // Retain the family label only while cited deployments cover a
            // substantial part of the actual home army.
            let mut cited_space = 0.0;
            let mut remaining: BTreeMap<String, usize> = genome.troops.iter()
                .map(|unit| (unit.name.clone(), unit.count)).collect();
            for step in &steps {
                if text(step, "action", "") == "ability"
                    && step.get("aim").is_some_and(|aim| !aim.is_null())
                    && !step.get("uncited").is_some_and(Json::bool)
                {
                    let hero = text(step, "what", "");
                    let required = match hero {
                        "Grand Warden" => Some("Fireball"),
                        "Archer Queen" => Some("Giant Arrow"),
                        _ => None,
                    };
                    if let Some(required) = required {
                        let carries = genome.heroes.iter().find(|choice| choice.hero == hero)
                            .is_some_and(|choice| choice.equipment.iter().any(|item| item == required));
                        if !carries {
                            return Err(format!("cited aimed ability for {hero} requires {required}"));
                        }
                    }
                }
                if text(step, "action", "") != "deploy" {
                    continue;
                }
                let name = text(step, "what", "");
                if let Some(left) = remaining.get_mut(name) {
                    let count = step_count(step, *left)?;
                    *left -= count;
                    if !step.get("uncited").is_some_and(Json::bool) && !array(step, "cite").is_empty() {
                        let unit = self.roster.troops.iter().find(|unit| unit.name == name)
                            .expect("checked deployment troop");
                        cited_space += unit.housing as f64 * count as f64;
                    }
                }
            }
            let total: usize = genome.troops.iter().map(|unit| unit.count * self.roster.troops
                .iter().find(|item| item.name == unit.name).expect("checked troop").housing).sum();
            if cited_space < total as f64 * 0.35 {
                return Err("family incompatible: fewer than 35% cited troop deployments".to_owned());
            }
            crate::armies::put(&mut plan, "steps", Json::Arr(steps));
        }
        super::program::install(&mut plan, genome)?;
        compiler.require_legal(&mut plan)?;
        let problems = compiler.account_legal(&build, &plan);
        if !problems.is_empty() {
            return Err(problems.join("; "));
        }
        Ok(plan)
    }
}

/// playbook.py:620: omitted, None and "all" deploy the remaining inventory.
/// Admission counts cannot consume more than the actual remaining inventory.
pub(super) fn step_count(step: &Json, left: usize) -> Result<usize, String> {
    let count = match step.get("count") {
        None => left,
        Some(Json::Null) => left,
        Some(Json::Str(value)) if value == "all" => left,
        Some(Json::Str(value)) => value.parse::<usize>().map_err(|_| "invalid fitted step count")?,
        Some(Json::Num(value)) if value.is_finite() && *value >= 0.0 => *value as usize,
        _ => return Err("invalid fitted step count".to_owned()),
    };
    Ok(count.min(left))
}

fn receiving_level(catalog: &Catalog, plan: &Json, name: &str, mut level: i64) -> i64 {
    let castle = Level::Int(plan.at("clan_castle_level").i64());
    let cap = catalog.stats.get("Clan Castle", &castle, &["~Laboratory Level Cap"], None);
    if let Some(cap) = cap {
        let requirements = catalog.setup.at("donated_laboratory").get(name);
        while level > 1 && requirements.and_then(|values| values.get(&level.to_string()))
            .and_then(|value| stats::num(value, None)).is_some_and(|required| required > cap)
        {
            level -= 1;
        }
    }
    level
}

fn shift_delay(step: &mut Json, offset: f64) -> bool {
    fn shift(when: &mut Json, offset: f64) -> bool {
        if when.get("after").is_some() {
            let old = numeric(when, "delay", 0.0);
            // Same constrained half/one-and-a-half interval as redteam.py:381.
            let next = (old + offset).clamp(old * 0.5, (old * 1.5).max(0.5));
            crate::armies::put(when, "delay", Json::Num(next));
            return true;
        }
        if let Some(parts) = when.get("all") {
            let mut parts = parts.arr().to_vec();
            let mut changed = false;
            for part in &mut parts {
                changed |= shift(part, offset);
            }
            crate::armies::put(when, "all", Json::Arr(parts));
            return changed;
        }
        false
    }
    let Some(mut when) = step.get("when").cloned() else {
        return false
    };
    let changed = shift(&mut when, offset);
    crate::armies::put(step, "when", when);
    changed
}

pub fn compatible(compiler: &Compiler<'_>, genome: &ArmyGenome) -> Result<(), String> {
    let family = genome.plan.family.as_str();
    if family == "generic" {
        return Ok(());
    }
    if family.starts_with("test-") || !compiler.playbooks.iter().any(|(name, _)| name == family) {
        return Err(format!("unknown production family: {family}"));
    }
    if crate::armies::family_of(&genome.to_build()) != Some(family) {
        return Err(format!("compiler resolves a different family than {family}"));
    }
    let signature: &[&str] = match family {
        "root-rider" => &["Root Rider"],
        "thrower" => &["Thrower"],
        "dragon" => &["Dragon"],
        "electro-dragon" => &["Electro Dragon"],
        "super-bowler" => &["Super Bowler"],
        "yeti" => &["Yeti", "Super Yeti"],
        "meteor-golem" => &["Meteor Golem"],
        "druid-ruin-witch" => &["Ruin Witch"],
        "super-minion-air" | "fireball-warden" => &["Super Minion"],
        "lavaloon" => &["Lava Hound", "Ice Hound", "Balloon"],
        _ => &[],
    };
    let count: usize = genome.troops.iter().filter(|unit| signature.contains(&unit.name.as_str()))
        .map(|unit| unit.count).sum();
    if count < 2 {
        return Err(format!("missing essential troops for {family}"));
    }
    let essential_spells: &[&str] = match family {
        "root-rider" | "super-minion-air" | "druid-ruin-witch" => &["Invisibility Spell"],
        "fireball-warden" => &["Earthquake Spell", "Invisibility Spell"],
        "super-bowler" => &["Rage Spell"],
        "dragon" | "electro-dragon" | "thrower" | "meteor-golem" => &["Totem Spell"],
        "yeti" => &["Ice Block Spell"],
        "lavaloon" => &["Haste Spell"],
        _ => &[],
    };
    for name in essential_spells {
        if !genome.spells.iter().chain(&genome.cc_spells).any(|unit| unit.name == *name) {
            return Err(format!("missing essential spell {name} for {family}"));
        }
    }
    if matches!(family, "fireball-warden" | "super-minion-air" | "druid-ruin-witch") {
        let warden = genome.heroes.iter().find(|hero| hero.hero == "Grand Warden")
            .ok_or("Warden charge family requires Grand Warden")?;
        if family == "fireball-warden" && !warden.equipment.contains(&"Fireball".to_owned()) {
            return Err("Fireball family requires owned Fireball equipment".to_owned());
        }
        if !genome.troops.iter().any(|unit| unit.name == "Healer" && unit.count >= 2) {
            return Err("Warden charge family requires healers".to_owned());
        }
    }
    Ok(())
}

fn repair_counts(
    values: &mut Vec<UnitCount>,
    roster: &[EligibleUnit],
    cap: usize,
    boost_limit: bool
) {
    values.retain(|unit| roster.iter().any(|item| item.name == unit.name));
    for unit in values.iter_mut() {
        unit.count = unit.count.min(cap);
    }
    normalize(values);
    let mut boosts = 0;
    values.retain(|unit| {
        let boosted = roster.iter().find(|item| item.name == unit.name).expect("filtered unit").boosted;
        if boosted {
            boosts += 1;
        }
        !boost_limit || !boosted || boosts <= 2
    });
    let housing = |name: &str| roster.iter().find(|unit| unit.name == name).expect("eligible unit").housing;
    let mut total: usize = values.iter().map(|unit| unit.count * housing(&unit.name)).sum();
    while total > cap {
        let index = values.iter().enumerate().filter(|(_, unit)| unit.count > 0)
            .max_by_key(|(index, unit)| (unit.count * housing(&unit.name), std::cmp::Reverse(*index))).map(|(index, _)| index).expect("overfull army");
        values[index].count -= 1;
        total -= housing(&values[index].name);
    }
    let free = cap - total;
    let fillers: Vec<&EligibleUnit> = roster.iter().filter(|unit| !unit.boosted).collect();
    let mut previous = vec![None; free + 1];
    previous[0] = Some((0, 0));
    for space in 1..=free {
        for (index, unit) in fillers.iter().enumerate() {
            if unit.housing <= space && previous[space - unit.housing].is_some() {
                previous[space] = Some((space - unit.housing, index));
                break;
            }
        }
    }
    let mut space = (0..=free).rev().find(|space| previous[*space].is_some()).unwrap_or(0);
    while space > 0 {
        let (next, index) = previous[space].expect("reachable housing");
        values.push(UnitCount {
            name: fillers[index].name.clone(),
            count: 1
        });
        space = next;
    }
    normalize(values);
}

/// This provider intentionally differs from calibration * skill in the general
/// scorer: evaluate.py:226 is overridden by the search's real-level contract.
pub struct NativePlanProvider<'a, 'b> {
    pub account: &'a AccountRules,
    pub compiler: &'a Compiler<'b>,
    pub catalog: &'a Catalog,
    pub genome: &'a ArmyGenome,
}

impl PlanProvider for NativePlanProvider<'_, '_> {
    fn prepare(&mut self, scenario: &Scenario, strength: f64) -> Result<Json, String> {
        if strength.to_bits() != 1.0_f64.to_bits() {
            return Err("armysearch requires strength exactly 1.0".to_owned());
        }
        self.account.compile(self.compiler, self.catalog, self.genome, scenario.angle, scenario.seed)
    }
}
