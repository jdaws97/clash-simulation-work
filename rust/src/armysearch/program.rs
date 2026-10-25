//! Editable attack programs executed by the ordinary PlaybookPlan path.
//! Seed fitting mirrors playbook.py:1529-1700,1921-2100; learned changes are
//! deliberately outside the source-only consolidation policy.

#[path = "fix_proof.rs"]
mod fixes;
#[path = "program_mutate.rs"]
pub mod mutate;
#[path = "program_proof.rs"]
pub mod proof;
#[path = "program_validate.rs"]
mod validate;

use std::collections::{BTreeMap, BTreeSet};

use crate::armies::{put, remove};
use crate::catalog::Catalog;
use crate::compile::Compiler;
use crate::json::Json;

use super::account::AccountRules;
use super::genome::ArmyGenome;
use super::util::{array, encode, number, object, string, text};

#[derive(Clone, Debug, PartialEq)]
pub struct AttackProgram {
    pub steps: Vec<Json>,
    pub seed_steps: Vec<Json>,
    pub seed_family: String,
    /// Composition/loadout identity, used only to detect an army mutation.
    pub seed_army: String,
}

/// JSON key order is irrelevant; step order and trigger child order execute.
/// Keep citations: playbook.py:741-785 interprets aimed AD-count quotes, and
/// at_cite changes the Duke deployment path (playbook.py:592-661).
pub fn canonical(value: &Json) -> Json {
    match value {
        Json::Obj(fields) => {
            let mut fields: Vec<_> = fields
                .iter()
                .map(|(key, value)| (key.clone(), canonical(value)))
                .collect();
            fields.sort_by(|a, b| a.0.cmp(&b.0));
            Json::Obj(fields)
        }
        Json::Arr(values) => Json::Arr(values.iter().map(canonical).collect()),
        Json::Num(value) if *value == 0.0 => Json::Num(0.0),
        _ => value.clone(),
    }
}

impl AttackProgram {
    pub fn identity_json(&self) -> Json {
        // output/hunt/r11/u2.out #1: learned records provenance only. Keep
        // uncited/completion and citations: they affect executor priority/aim.
        let steps = self
            .steps
            .iter()
            .map(|step| match step {
                Json::Obj(fields) => Json::Obj(
                    fields
                        .iter()
                        .filter(|(key, _)| key != "learned")
                        .cloned()
                        .collect(),
                ),
                _ => step.clone(),
            })
            .collect();
        canonical(&Json::Arr(steps))
    }

    pub fn identity(&self) -> String {
        encode(&self.identity_json())
    }

    pub fn normalize(&mut self) {
        self.steps = self.steps.iter().map(canonical).collect();
        self.seed_steps = self.seed_steps.iter().map(canonical).collect();
    }

    pub fn to_json(&self) -> Json {
        object([
            ("steps", canonical(&Json::Arr(self.steps.clone()))),
            ("seed_steps", canonical(&Json::Arr(self.seed_steps.clone()))),
            ("seed_family", string(&self.seed_family)),
            ("seed_army", string(&self.seed_army)),
        ])
    }

    pub fn from_json(value: &Json) -> Result<Self, String> {
        validate::finite(value, 0)?;
        for key in ["seed_family", "seed_army"] {
            if !matches!(value.get(key), Some(Json::Str(_))) {
                return Err(format!("program {key} must be a string"));
            }
        }
        let steps = |key| match value.get(key) {
            Some(Json::Arr(steps)) => Ok(steps.clone()),
            _ => Err(format!("program {key} must be an array")),
        };
        let mut result = Self {
            steps: steps("steps")?,
            seed_steps: steps("seed_steps")?,
            seed_family: text(value, "seed_family", "generic").to_owned(),
            seed_army: text(value, "seed_army", "").to_owned(),
        };
        result.normalize();
        Ok(result)
    }

    pub fn validate(&self, genome: &ArmyGenome) -> Result<(), String> {
        validate::validate(self, genome)
    }
}

pub fn army_identity(genome: &ArmyGenome) -> String {
    let mut genome = genome.clone();
    genome.normalize();
    encode(&canonical(&genome.to_build()))
}

pub(super) fn deploy_stock(genome: &ArmyGenome) -> BTreeMap<String, usize> {
    let mut stock = BTreeMap::new();
    for unit in &genome.troops {
        *stock.entry(unit.name.clone()).or_default() += unit.count;
    }
    for hero in &genome.heroes {
        stock.insert(hero.hero.clone(), 1);
    }
    if let Some(siege) = &genome.siege {
        stock.insert(siege.clone(), 1);
    }
    stock
}

pub(super) fn spell_stock(genome: &ArmyGenome) -> BTreeMap<String, usize> {
    let mut stock = BTreeMap::new();
    for unit in genome.spells.iter().chain(&genome.cc_spells) {
        *stock.entry(unit.name.clone()).or_default() += unit.count;
    }
    stock
}

pub(super) fn unit_names(genome: &ArmyGenome) -> BTreeSet<String> {
    let mut names: BTreeSet<_> = deploy_stock(genome).into_keys().collect();
    names.extend(genome.cc_troops.iter().map(|unit| unit.name.clone()));
    for hero in &genome.heroes {
        names.insert(hero.pet.clone());
        // heroes.py:1077-1089,1418-1422: summons are references, not inventory.
        for item in &hero.equipment {
            let child = match item.as_str() {
                "Archer Puppet" => "Archer",
                "Barbarian Puppet" => "Barbarian",
                "Healer Puppet" => "Healer",
                "Hog Rider Puppet" => "Hog Rider",
                "Lavaloon Puppet" => "Lavaloon",
                "Henchmen Puppet" => "Henchman",
                _ => continue,
            };
            names.insert(child.to_owned());
        }
        // pets.py:193-209; these children inherit the assigned hero's group.
        if hero.pet == "Frosty" {
            names.insert("Frostmite".to_owned());
        }
        if hero.pet == "Sneezy" {
            names.insert("Booger".to_owned());
        }
    }
    // units.py:477-586,665,823,950-989,1060: troop-specific children can
    // anchor spells as well. They cannot be deployed from the home inventory.
    for unit in genome.troops.iter().chain(&genome.cc_troops) {
        let child = match unit.name.as_str() {
            "Furnace" => "Firemite",
            "Yeti" => "Yetimite",
            "Super Yeti" => "Electromite",
            "Golem" => "Golemite",
            "Lava Hound" => "Lava Pup",
            "Ice Hound" => "Ice Pup",
            "Witch" => "Skeleton",
            "Super Witch" => "Big Boy",
            "Ruin Witch" => "Ruin Knight",
            "Druid" => "Bear",
            _ => continue,
        };
        names.insert(child.to_owned());
    }
    if genome.siege.as_deref() == Some("Siege Barracks") {
        names.insert("P.E.K.K.A".to_owned());
        names.insert("Wizard".to_owned());
    }
    // spells.py:241-255,1473-1490: spell summons are references, not inventory.
    for spell in spell_stock(genome).keys() {
        let child = match spell.as_str() {
            "Skeleton Spell" => "Spell Skeleton",
            "Bat Spell" => "Bat",
            "Totem Spell" => "Totem",
            _ => continue,
        };
        names.insert(child.to_owned());
    }
    names
}

pub(super) fn time(seconds: f64) -> Json {
    object([("t", Json::Num(seconds))])
}

pub(super) fn step(
    id: &str,
    action: &str,
    what: &str,
    count: usize,
    at: &str,
    group: &str,
    when: Json,
) -> Json {
    object([
        ("id", string(id)),
        ("action", string(action)),
        ("what", string(what)),
        ("count", number(count)),
        ("at", string(at)),
        ("group", string(group)),
        ("when", when),
        ("uncited", Json::Bool(true)),
    ])
}

/// meta_armies.py:150-277 supplies role order; the actual timings below are
/// synthetic search priors, never attributed to a player.
fn generic_steps(genome: &ArmyGenome) -> Vec<Json> {
    let mut steps = Vec::new();
    for (index, unit) in genome.troops.iter().enumerate() {
        let (group, at, at_time) = match unit.name.as_str() {
            "Sneaky Goblin" | "Super Barbarian" | "Baby Dragon" | "Wizard" => {
                ("funnel", "edge:funnel", 0.0)
            }
            "Golem" | "Ice Golem" | "Giant" | "Lava Hound" | "Ice Hound" | "Root Rider" => {
                ("main", "edge:main", 5.0)
            }
            "Healer" | "Druid" | "Apprentice Warden" => ("main", "edge:main", 9.0),
            _ => ("main", "edge:main", 8.0),
        };
        steps.push(step(
            &format!("troop-{index}"),
            "deploy",
            &unit.name,
            unit.count,
            at,
            group,
            time(at_time),
        ));
    }
    for (index, hero) in genome.heroes.iter().enumerate() {
        steps.push(step(
            &format!("hero-{index}"),
            "deploy",
            &hero.hero,
            1,
            "edge:main",
            "main",
            time(7.0),
        ));
        steps.push(step(
            &format!("ability-{index}"),
            "ability",
            &hero.hero,
            1,
            "edge:main",
            "main",
            object([("hp_below", string(&hero.hero)), ("frac", Json::Num(0.45))]),
        ));
    }
    if let Some(siege) = &genome.siege {
        steps.push(step(
            "siege",
            "deploy",
            siege,
            1,
            "edge:main",
            "main",
            time(6.0),
        ));
    }
    for (index, (name, count)) in spell_stock(genome).into_iter().enumerate() {
        for copy in 0..count {
            steps.push(step(
                &format!("spell-{index}-{copy}"),
                "spell",
                &name,
                1,
                "group:main",
                "main",
                time(16.0 + copy as f64 * 6.0),
            ));
        }
    }
    steps
}

/// fit_steps (playbook.py:1529-1700) normally supplies leftover hero roles.
/// Learned programs need the same guarantee after a hero is replaced.
fn complete_hero_roles(steps: &mut Vec<Json>, genome: &ArmyGenome) {
    let defaults = generic_steps(genome);
    let mut ids: BTreeSet<_> = steps
        .iter()
        .map(|step| text(step, "id", "").to_owned())
        .collect();
    for hero in &genome.heroes {
        if steps
            .iter()
            .any(|step| text(step, "action", "") == "deploy" && text(step, "what", "") == hero.hero)
        {
            continue;
        }
        for role in defaults
            .iter()
            .filter(|step| text(step, "what", "") == hero.hero)
        {
            let action = text(role, "action", "");
            if steps.iter().any(|step| {
                text(step, "action", "") == action && text(step, "what", "") == hero.hero
            }) {
                continue;
            }
            let mut role = role.clone();
            let mut serial = 0;
            let id = loop {
                let id = format!("hero-role-{serial}");
                if ids.insert(id.clone()) {
                    break id;
                }
                serial += 1;
            };
            put(&mut role, "id", string(id));
            put(&mut role, "learned", Json::Bool(true));
            steps.push(role);
        }
    }
}

/// Inventory fitting uses the compiler's already selected/fitted variant.
/// Unlike fit_steps (playbook.py:1529-1700), search materializes "all" and
/// rejects overspending instead of relying on executor clamping.
fn fit_counts(steps: &mut Vec<Json>, genome: &ArmyGenome) {
    let mut stock = deploy_stock(genome);
    let mut spells = spell_stock(genome);
    let mut abilities = BTreeSet::new();
    steps.retain_mut(|step| {
        let action = text(step, "action", "");
        let what = text(step, "what", "").to_owned();
        let pool = match action {
            "deploy" => &mut stock,
            "spell" | "recall" => &mut spells,
            "ability" => {
                return abilities.insert(what) && validate::equipment(step, genome).is_ok()
            }
            _ => return true,
        };
        let name = if action == "recall" {
            "Recall Spell"
        } else {
            &what
        };
        let left = pool.get(name).copied().unwrap_or(0);
        if left == 0 {
            return false;
        }
        let amount = if action == "deploy" {
            validate::amount(step, left, left).unwrap_or(left).min(left)
        } else {
            1
        };
        let reserve = if step.get("every").is_some() {
            left
        } else {
            amount
        };
        pool.insert(name.to_owned(), left - reserve);
        put(step, "count", number(amount));
        remove(step, "level");
        true
    });
}

fn repair_trigger(
    value: &Json,
    ids: &BTreeSet<String>,
    units: &BTreeSet<String>,
    groups: &BTreeSet<String>,
    spells: &BTreeMap<String, usize>,
) -> Json {
    if value
        .get("after")
        .is_some_and(|value| !ids.contains(value.str()))
    {
        return time(12.0);
    }
    for key in ["inside", "dead", "hp_below", "heavy_fire"] {
        if value
            .get(key)
            .is_some_and(|value| !units.contains(value.str()))
        {
            return time(12.0);
        }
    }
    for key in ["group_inside", "near_th", "defenders_near"] {
        if value
            .get(key)
            .is_some_and(|value| !groups.contains(value.str()))
        {
            return time(12.0);
        }
    }
    if value.get("spells_left").is_some_and(|value| {
        let name = value.str();
        let name = crate::plans::spell_key(name)
            .map(crate::plans::spell_name)
            .unwrap_or(name);
        !spells.contains_key(name)
    }) {
        return time(12.0);
    }
    let mut value = value.clone();
    for key in ["all", "any"] {
        if let Some(parts) = value.get(key) {
            let parts = parts
                .arr()
                .iter()
                .map(|part| repair_trigger(part, ids, units, groups, spells))
                .collect();
            put(&mut value, key, Json::Arr(parts));
        }
    }
    value
}

pub(super) fn repair_references(steps: &mut [Json], genome: &ArmyGenome) {
    let ids: BTreeSet<_> = steps
        .iter()
        .map(|step| text(step, "id", "").to_owned())
        .collect();
    let groups: BTreeSet<_> = steps
        .iter()
        .filter(|step| matches!(text(step, "action", ""), "deploy" | "redeploy"))
        .map(|step| text(step, "group", "main").to_owned())
        .collect();
    let units = unit_names(genome);
    let spells = spell_stock(genome);
    for step in steps {
        for key in ["when", "until"] {
            if let Some(value) = step.get(key) {
                let next = repair_trigger(value, &ids, &units, &groups, &spells);
                put(step, key, next);
            }
        }
        for key in ["at", "aim"] {
            let anchor = text(step, key, "");
            if let Some((kind, arg)) = anchor.split_once(':') {
                let absent = match kind {
                    "unit" | "unit_ahead" => !units.contains(arg),
                    "group" | "threat" | "defenders" => !groups.contains(arg),
                    _ => false,
                };
                if absent {
                    put(step, key, string("edge:main"));
                }
            }
        }
    }
}

pub fn seed(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: &Catalog,
    genome: &ArmyGenome,
) -> Result<AttackProgram, String> {
    let mut baseline = genome.clone();
    baseline.plan.program = None;
    // tactics.py:135-164 and redteam.py:360-383 run after installation.
    // Seed neutral steps so repeated admission never applies a gene twice.
    baseline.plan.tactics = crate::compile::TACTIC_DEFAULTS;
    baseline.plan.step_timing.clear();
    let plan = account.compile(compiler, catalog, &baseline, baseline.plan.angle_offset, 0)?;
    let mut steps = if genome.plan.family == "generic" {
        generic_steps(genome)
    } else {
        array(&plan, "steps").to_vec()
    };
    fit_counts(&mut steps, genome);
    complete_hero_roles(&mut steps, genome);
    repair_references(&mut steps, genome);
    let mut result = AttackProgram {
        seed_steps: steps.clone(),
        steps,
        seed_family: genome.plan.family.clone(),
        seed_army: army_identity(genome),
    };
    // An absent pet/ability can leave an optional source step unusable. Remove
    // that step with a bounded loop; cycles/global errors are never concealed.
    for _ in 0..validate::MAX_STEPS {
        match result.validate(genome) {
            Ok(()) => break,
            Err(reason) => {
                let index = reason
                    .strip_prefix("step ")
                    .and_then(|value| value.split_once(':'))
                    .and_then(|(index, _)| index.parse::<usize>().ok());
                let Some(index) = index else {
                    return Err(reason);
                };
                result.steps.remove(index);
                repair_references(&mut result.steps, genome);
            }
        }
    }
    result.seed_steps = result.steps.clone();
    result.normalize();
    result.validate(genome)?;
    Ok(result)
}

pub fn enable(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: &Catalog,
    genome: &mut ArmyGenome,
) -> Result<(), String> {
    if genome.plan.program.is_none() {
        genome.plan.program = Some(seed(account, compiler, catalog, genome)?);
    }
    Ok(())
}

/// Preserve the learned edits when the same army survives. Composition/loadout
/// changes fit the inherited program to the new inventory and reset its seed
/// comparison to the new family's cited/default program.
pub fn reconcile(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: &Catalog,
    genome: &mut ArmyGenome,
) -> Result<(), String> {
    let Some(old) = &genome.plan.program else {
        return Ok(());
    };
    if old.seed_army == army_identity(genome) && old.seed_family == genome.plan.family {
        return old.validate(genome);
    }
    let mut next = seed(account, compiler, catalog, genome)?;
    let mut steps = old.steps.clone();
    fit_counts(&mut steps, genome);
    complete_hero_roles(&mut steps, genome);
    repair_references(&mut steps, genome);
    next.steps = steps;
    next.validate(genome)?;
    genome.plan.program = Some(next);
    Ok(())
}

/// This is the tail of the ordinary AccountRules::compile path, before its
/// require_legal/account_legal gates. No alternate simulation or stat path.
/// Fresh runtime fields mirror playbook.py:1921-2100 and rust_bridge.py:91.
pub fn install(plan: &mut Json, genome: &ArmyGenome) -> Result<(), String> {
    let Some(program) = &genome.plan.program else {
        return Ok(());
    };
    program.validate(genome)?;
    put(plan, "$type", string("PlaybookPlan"));
    put(plan, "steps", canonical(&Json::Arr(program.steps.clone())));
    // playbook.py:2055-2099: the final learned opening, rather than the
    // replaced source steps, decides whether Healers require a ground Warden.
    let has_healers = genome
        .troops
        .iter()
        .any(|unit| unit.name == "Healer" && unit.count > 0);
    if crate::compile::warden_walk(&program.steps, has_healers) {
        put(plan, "ground", Json::Bool(true));
    }
    // playbook.py:1977-1981 retains build order and appends the siege last.
    // Inventory order determines the executor's unmentioned-unit rescue drops.
    let mut inventory: Vec<_> = genome
        .troops
        .iter()
        .map(|unit| (unit.name.clone(), number(unit.count)))
        .collect();
    if let Some(siege) = &genome.siege {
        inventory.push((siege.clone(), number(1)));
    }
    put(plan, "inventory", Json::Obj(inventory));
    put(plan, "flank_offset", Json::Num(genome.plan.flank_offset));
    put(plan, "charge_side", string(&genome.plan.charge_side));
    put(plan, "snipe_mode", string(&genome.plan.snipe_mode));
    put(plan, "auto_revive", Json::Bool(false));
    for key in ["_done", "_next", "_hurt", "_no_target"] {
        put(plan, key, object([]));
    }
    for key in ["_cancelled", "log_steps"] {
        put(plan, key, Json::Arr(Vec::new()));
    }
    put(plan, "strength", Json::Num(1.0));
    Ok(())
}

fn readable(step: &Json) -> String {
    let mut line = format!(
        "{}: {} {} x{} at {} group={} when={}",
        text(step, "id", ""),
        text(step, "action", ""),
        text(step, "what", ""),
        step.get("count").map_or_else(|| "all".to_owned(), encode),
        text(step, "at", "edge:main"),
        text(step, "group", "main"),
        step.get("when").map_or_else(|| "always".to_owned(), encode)
    );
    for key in ["aim", "every", "until", "origin", "equipment"] {
        if let Some(value) = step.get(key) {
            line.push_str(&format!(" {key}={}", encode(value)));
        }
    }
    line
}

pub fn report(genome: &ArmyGenome, compiler: &Compiler<'_>) -> Json {
    let Some(program) = &genome.plan.program else {
        return object([("enabled", Json::Bool(false))]);
    };
    let mut diff = Vec::new();
    for (index, old) in program.seed_steps.iter().enumerate() {
        let id = text(old, "id", "");
        match program
            .steps
            .iter()
            .enumerate()
            .find(|(_, step)| text(step, "id", "") == id)
        {
            None => diff.push(string(format!("- {}", readable(old)))),
            Some((position, step)) => {
                if canonical(old) != canonical(step) {
                    diff.push(string(format!("- {}", readable(old))));
                    diff.push(string(format!("+ {}", readable(step))));
                }
                if index != position {
                    diff.push(string(format!("move {id}: {index} -> {position}")));
                }
            }
        }
    }
    for step in &program.steps {
        if !program
            .seed_steps
            .iter()
            .any(|old| old.get("id") == step.get("id"))
        {
            diff.push(string(format!("+ {}", readable(step))));
        }
    }
    // Conservative attribution: compare executable fields against every real
    // source and its explicit variants. Inventory/timing adaptations count as
    // learned unless exactly represented in a cited playbook.
    let executable = |steps: &[Json]| {
        let steps = steps
            .iter()
            .map(|step| {
                let mut step = step.clone();
                for key in ["support", "note", "notes", "variant"] {
                    remove(&mut step, key);
                }
                canonical(&step)
            })
            .collect();
        encode(&Json::Arr(steps))
    };
    let current = executable(&program.steps);
    let mut matches = Vec::new();
    for (family, book) in &compiler.playbooks {
        if family.starts_with("test-") {
            continue;
        }
        if current == executable(array(book, "steps")) {
            matches.push(string(family));
        }
        for variant in array(book, "variants") {
            let mut steps = array(book, "steps").to_vec();
            let replaces = array(variant, "replaces");
            let position = steps
                .iter()
                .position(|step| step.get("id").is_some_and(|id| replaces.contains(id)))
                .unwrap_or(steps.len());
            steps.retain(|step| !step.get("id").is_some_and(|id| replaces.contains(id)));
            let position = position.min(steps.len());
            steps.splice(position..position, array(variant, "steps").iter().cloned());
            if current == executable(&steps) {
                matches.push(string(format!("{family}:{}", text(variant, "name", ""))));
            }
        }
    }
    let label = if matches.is_empty() {
        "learned (not from a real player)"
    } else {
        "matches cited playbook"
    };
    object([
        ("enabled", Json::Bool(true)),
        ("label", string(label)),
        ("matching_cited_playbooks", Json::Arr(matches)),
        ("seed_family", string(&program.seed_family)),
        ("steps", canonical(&Json::Arr(program.steps.clone()))),
        (
            "readable_steps",
            Json::Arr(
                program
                    .steps
                    .iter()
                    .map(|step| string(readable(step)))
                    .collect(),
            ),
        ),
        ("seed_steps", Json::Arr(program.seed_steps.clone())),
        ("diff_vs_seed", Json::Arr(diff)),
    ])
}
