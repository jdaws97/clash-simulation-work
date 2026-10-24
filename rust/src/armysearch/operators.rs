//! Constrained exchanges and family-aware recombination; redteam.py:307-383.

use std::collections::BTreeSet;
use std::path::Path;

use crate::catalog::Catalog;
use crate::compile::{Compiler, TACTIC_DEFAULTS};
use crate::json::Json;

use super::account::{compatible, AccountRules, EligibleUnit};
use super::genome::{ArmyGenome, HeroChoice, PlanGenes, UnitCount};
use super::util::{array, numeric, read, text, Random};

pub fn seeds(
    root: &Path,
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: &Catalog,
) -> Result<(Vec<ArmyGenome>, Vec<String>), String> {
    let mut builds: Vec<Json> = compiler.library.builds.iter().map(|build| build.value.clone()).collect();
    let mut paths = std::fs::read_dir(root.join("data")).map_err(|error| error.to_string())?
        .map(|entry| entry.map(|entry| entry.path()).map_err(|error| error.to_string()))
        .collect::<Result<Vec<_>, _>>()?;
    paths.sort();
    for path in paths {
        let name = path.file_name().and_then(|name| name.to_str()).unwrap_or("");
        if name.starts_with("meta-armies-") && name.ends_with(".json") {
            builds.extend_from_slice(array(&read(&path)?, "builds"));
        }
    }
    for (family, book) in &compiler.playbooks {
        if family.starts_with("test-") {
            continue;
        }
        if let Some(army) = book.get("army") {
            let mut build = army.clone();
            crate::armies::put(&mut build, "archetype", Json::Str(family.clone()));
            builds.push(build);
        }
    }
    let mut found = Vec::new();
    let mut rejected = Vec::new();
    let mut identities = BTreeSet::new();
    for (index, build) in builds.iter().enumerate() {
        let mut genome = ArmyGenome::from_build(build);
        // Filename is authoritative for template seeds, including families
        // whose signature overlaps another family (e.g. Warden air charges).
        let archetype = text(build, "archetype", "");
        if compiler.playbooks.iter().any(|(name, _)| name == archetype && !name.starts_with("test-")) {
            genome.plan.family = archetype.to_owned();
        }
        // meta_armies.py:282-343 recognizes Lava Hound as the Lalo signature.
        // The Ice Hound template is an example, so adapt its seed to the
        // native compiler's recognized, account-owned version of that role.
        if genome.plan.family == "lavaloon" {
            for unit in &mut genome.troops {
                if unit.name == "Ice Hound" {
                    unit.name = "Lava Hound".to_owned();
                    unit.count = unit.count.max(2);
                }
            }
        }
        if let Err(reason) = account.repair(&mut genome) {
            rejected.push(format!("seed {index}: {reason}"));
            continue;
        }
        if compatible(compiler, &genome).is_err() {
            genome.plan = PlanGenes::default();
        }
        match admit(account, compiler, catalog, &mut genome) {
            Ok(()) => {
                if identities.insert(genome.identity()) {
                    found.push(genome);
                }
            }
            Err(reason) => {
                // An incompatible cited seed is still useful as an honestly
                // labelled generic composition after account repair.
                genome.plan = PlanGenes::default();
                match admit(account, compiler, catalog, &mut genome) {
                    Ok(()) => {
                        if identities.insert(genome.identity()) {
                            found.push(genome);
                        }
                    }
                    Err(generic) => rejected.push(format!("seed {index}: {reason}; generic: {generic}")),
                }
            }
        }
    }
    if found.is_empty() {
        return Err(format!("no legal executable seeds: {}", rejected.join("; ")));
    }
    found.sort_by_key(ArmyGenome::identity);
    Ok((found, rejected))
}

/// Freeze genes which this fitted plan cannot execute. tactics.py:81-89
/// explicitly limits playbook tactics; generic tactics stay frozen until the
/// shared compiler exposes their native implementation.
pub fn applicability(plan: &Json) -> [bool; 19] {
    let mut mask = [false; 19];
    if text(plan, "$type", "") != "PlaybookPlan" {
        return mask;
    }
    let steps = array(plan, "steps");
    // playbook.py:148-154: these anchors actually execute flank_offset.
    mask[1] = steps.iter().any(|step| {
        ["at", "aim"].iter().any(|field| {
            matches!(text(step, field, ""), "edge:charge" | "edge:funnel" | "edge:left" | "edge:right")
        })
    });
    mask[4] = steps.iter().any(|step| {
        text(step, "action", "") == "deploy"
            && !crate::plans::is_hero(text(step, "what", ""))
            && text(step, "what", "") != "Healer"
    });
    mask[5] = steps.iter().any(|step| {
        text(step, "action", "") == "deploy" && text(step, "what", "") == "Healer"
    });
    let spare = |name: &str, key: &str| {
        let mut reserved = 0.0;
        for step in steps {
            if text(step, "action", "") == "spell" && text(step, "what", "") == name {
                if numeric(step, "every", 0.0) > 0.0 {
                    return false;
                }
                // playbook.py:spell and fallback_spells reserve one cast per
                // pending step; a repeating step reserves that spell kind.
                reserved += 1.0;
            }
        }
        numeric(plan.at("spells"), key, 0.0) > reserved
    };
    mask[9] = spare("Freeze Spell", "freeze");
    mask[10] = spare("Revive Spell", "revive");
    mask
}

pub fn admit(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: &Catalog,
    genome: &mut ArmyGenome,
) -> Result<(), String> {
    account.check(genome)?;
    let mut neutral = genome.clone();
    neutral.plan.tactics = TACTIC_DEFAULTS;
    neutral.plan.step_timing.clear();
    let plan = account.compile(compiler, catalog, &neutral, neutral.plan.angle_offset, 0)?;
    let mask = applicability(&plan);
    for index in 0..19 {
        if !mask[index] {
            genome.plan.tactics[index] = TACTIC_DEFAULTS[index];
        }
    }
    if genome.plan.family != "generic" {
        let uses_charge_side = array(&plan, "steps").iter().any(|step| {
            ["at", "aim"].iter().any(|field| {
                matches!(text(step, field, ""), "edge:charge" | "edge:funnel")
            })
        });
        if !uses_charge_side {
            genome.plan.charge_side = "left".to_owned();
        }
        if !mask[1] {
            genome.plan.flank_offset = 0.9;
        }
    }
    let valid_steps: BTreeSet<String> = timing_steps(&plan).into_iter().collect();
    genome.plan.step_timing.retain(|id, _| valid_steps.contains(id));
    genome.normalize();
    account.compile(compiler, catalog, genome, genome.plan.angle_offset, 0)?;
    Ok(())
}

fn timing_steps(plan: &Json) -> Vec<String> {
    fn delayed(when: &Json) -> bool {
        when.get("after").is_some() && numeric(when, "delay", 0.0) > 0.0
            || array(when, "all").iter().any(delayed)
    }
    array(plan, "steps").iter().filter(|step| {
        !step.get("uncited").is_some_and(Json::bool)
            && !array(step, "cite").is_empty()
            && step.get("when").is_some_and(delayed)
    }).map(|step| text(step, "id", "").to_owned()).collect()
}

fn exchange(values: &mut Vec<UnitCount>, roster: &[EligibleUnit], rng: &mut Random, large: bool) {
    if !values.is_empty() {
        let index = rng.index(values.len());
        let removed = if large {
            values[index].count
        } else {
            1 + rng.index(values[index].count.max(1).min(4))
        };
        values[index].count = values[index].count.saturating_sub(removed);
    }
    let selected = &roster[rng.index(roster.len())];
    values.push(UnitCount {
        name: selected.name.clone(),
        count: 1 + rng.index(if large {
            12
        } else {
            3
        })
    });
}

pub(super) fn empty_immigrant(account: &AccountRules, rng: &mut Random) -> ArmyGenome {
    let mut heroes = account.roster.heroes.clone();
    let mut pets = account.roster.pets.clone();
    for index in (1..heroes.len()).rev() {
        let other = rng.index(index + 1);
        heroes.swap(index, other);
    }
    for index in (1..pets.len()).rev() {
        let other = rng.index(index + 1);
        pets.swap(index, other);
    }
    let choices = heroes.into_iter().take(4).enumerate().map(|(index, hero)| {
        let inventory = &account.roster.equipment[&hero];
        let first = rng.index(inventory.len());
        let second = (first + 1 + rng.index(inventory.len() - 1)) % inventory.len();
        HeroChoice {
            hero,
            equipment: [inventory[first].clone(), inventory[second].clone()],
            pet: pets[index].clone()
        }
    }).collect();
    ArmyGenome {
        troops: Vec::new(),
        spells: Vec::new(),
        cc_troops: Vec::new(),
        cc_spells: Vec::new(),
        siege: account.roster.sieges.get(rng.index(account.roster.sieges.len().max(1)))
            .map(|unit| unit.name.clone()),
        heroes: choices,
        plan: PlanGenes {
            angle_offset: rng.unit() * (2.0 * std::f64::consts::PI),
            ..PlanGenes::default()
        },
    }
}

pub fn immigrant(account: &AccountRules, rng: &mut Random) -> Result<ArmyGenome, String> {
    let mut genome = empty_immigrant(account, rng);
    for _ in 0..8 {
        exchange(&mut genome.troops, &account.roster.troops, rng, true);
    }
    for _ in 0..3 {
        exchange(&mut genome.spells, &account.roster.spells, rng, false);
    }
    exchange(&mut genome.cc_troops, &account.roster.troops, rng, true);
    exchange(&mut genome.cc_spells, &account.roster.spells, rng, false);
    account.repair(&mut genome)?;
    Ok(genome)
}

pub fn mutate(
    parent: &ArmyGenome,
    templates: &[ArmyGenome],
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: &Catalog,
    rng: &mut Random,
) -> Result<ArmyGenome, String> {
    let mut child = parent.clone();
    match rng.index(14) {
        0 | 1 => exchange(&mut child.troops, &account.roster.troops, rng, false),
        2 => exchange(&mut child.spells, &account.roster.spells, rng, false),
        3 => exchange(&mut child.cc_troops, &account.roster.troops, rng, false),
        4 => exchange(&mut child.cc_spells, &account.roster.spells, rng, false),
        5 => {
            child.siege = account.roster.sieges.get(rng.index(account.roster.sieges.len().max(1)))
                .map(|unit| unit.name.clone());
        }
        6 => {
            let index = rng.index(4);
            let available: Vec<_> = account.roster.heroes.iter().filter(|hero| !child.heroes.iter()
                .any(|choice| &choice.hero == *hero)).collect();
            if !available.is_empty() {
                child.heroes[index].hero = available[rng.index(available.len())].clone();
            }
        }
        7 => {
            let index = rng.index(4);
            let slot = rng.index(2);
            let items = &account.roster.equipment[&child.heroes[index].hero];
            child.heroes[index].equipment[slot] = items[rng.index(items.len())].clone();
        }
        8 => {
            let first = rng.index(4);
            if rng.index(2) == 0 {
                let second = (first + 1 + rng.index(3)) % 4;
                let pet = child.heroes[first].pet.clone();
                child.heroes[first].pet = child.heroes[second].pet.clone();
                child.heroes[second].pet = pet;
            } else {
                child.heroes[first].pet = account.roster.pets[rng.index(account.roster.pets.len())].clone();
            }
        }
        9 => {
            let template = &templates[rng.index(templates.len())];
            child.troops = template.troops.clone();
            child.spells = template.spells.clone();
            child.plan = template.plan.clone();
        }
        10 => {
            let tau = 2.0 * std::f64::consts::PI;
            child.plan.angle_offset = (child.plan.angle_offset + (rng.unit() - 0.5) * 0.8).rem_euclid(tau);
        }
        11 => {
            if child.plan.family != "generic" {
                match rng.index(3) {
                    0 => child.plan.charge_side = if child.plan.charge_side == "left" {
                        "right"
                    } else {
                        "left"
                    }.to_owned(),
                    1 => child.plan.flank_offset = (child.plan.flank_offset + (rng
                        .unit() - 0.5) * 0.4).clamp(0.3, 1.6),
                    _ => child.plan.snipe_mode = ["off", "value", "aggressive"][rng.index(3)].to_owned(),
                }
            }
        }
        12 => {
            let plan = account.compile(compiler, catalog, parent, parent.plan.angle_offset, 0)?;
            let steps = timing_steps(&plan);
            if !steps.is_empty() {
                child.plan.step_timing.insert(steps[rng.index(steps.len())].clone(), (rng
                    .unit() - 0.5) * 8.0);
            }
            let mask = applicability(&plan);
            let active: Vec<_> = (0..19).filter(|index| mask[*index]).collect();
            if !active.is_empty() {
                let index = active[rng.index(active.len())];
                let (low, high) = match index {
                    1 => (0.4, 1.8),
                    4 => (0.4, 1.6),
                    5 => (0.3, 2.0),
                    9 => (0.0, 7.999999),
                    _ => (0.5, 4.0),
                };
                child.plan.tactics[index] = low + rng.unit() * (high - low);
            }
        }
        _ => exchange(&mut child.troops, &account.roster.troops, rng, true),
    }
    account.repair(&mut child)?;
    admit(account, compiler, catalog, &mut child)?;
    Ok(child)
}

pub fn crossover(
    first: &ArmyGenome,
    second: &ArmyGenome,
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: &Catalog,
    rng: &mut Random,
) -> Result<ArmyGenome, String> {
    if first.plan.family != second.plan.family {
        return Err("crossover requires the same family".to_owned());
    }
    let mut child = first.clone();
    if rng.index(2) == 0 {
        child.troops = second.troops.clone();
    }
    if rng.index(2) == 0 {
        child.spells = second.spells.clone();
    }
    if rng.index(2) == 0 {
        child.cc_troops = second.cc_troops.clone();
        child.cc_spells = second.cc_spells.clone();
        child.siege = second.siege.clone();
    }
    if rng.index(2) == 0 {
        child.heroes = second.heroes.clone();
    }
    if rng.index(2) == 0 {
        child.plan = second.plan.clone();
    }
    account.repair(&mut child)?;
    admit(account, compiler, catalog, &mut child)?;
    Ok(child)
}
