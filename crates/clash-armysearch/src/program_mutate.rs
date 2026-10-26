//! Program operators; execution remains playbook.py:505-675,964-1153.

use std::collections::BTreeMap;

use crate::armies::{put, remove};
use crate::json::Json;

use super::{deploy_stock, repair_references, spell_stock, step, time, unit_names, AttackProgram};
use crate::genome::ArmyGenome;
use crate::util::{number, object, string, text, Random};

#[derive(Clone, Copy, Debug)]
pub enum Mutation {
    Add,
    Delete,
    Anchor,
    Trigger,
    Parameter,
    Count,
    Group,
    Swap,
    Duplicate,
    Aim,
}

pub const MUTATIONS: [Mutation; 10] = [
    Mutation::Add,
    Mutation::Delete,
    Mutation::Anchor,
    Mutation::Trigger,
    Mutation::Parameter,
    Mutation::Count,
    Mutation::Group,
    Mutation::Swap,
    Mutation::Duplicate,
    Mutation::Aim,
];

fn fresh_id(program: &AttackProgram) -> String {
    for serial in 0.. {
        let id = format!("learned-{serial}");
        if !program.steps.iter().any(|step| text(step, "id", "") == id) {
            return id;
        }
    }
    unreachable!()
}

fn groups(program: &AttackProgram) -> Vec<String> {
    let mut groups: Vec<_> = program
        .steps
        .iter()
        .filter(|step| matches!(text(step, "action", ""), "deploy" | "redeploy"))
        .map(|step| text(step, "group", "main").to_owned())
        .collect();
    groups.sort();
    groups.dedup();
    groups
}

fn anchors(program: &AttackProgram, genome: &ArmyGenome) -> Vec<String> {
    let mut anchors: Vec<String> = [
        "edge:main",
        "edge:charge",
        "edge:funnel",
        "edge:left",
        "edge:right",
        "th",
        "building:ad",
        "building:inferno",
        "building:mono",
        "building:cc",
        "building:scatter",
        "building:xbow",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect();
    for unit in unit_names(genome) {
        anchors.push(format!("unit:{unit}"));
        anchors.push(format!("unit_ahead:{unit}"));
    }
    for group in groups(program) {
        for kind in ["group", "threat", "defenders"] {
            anchors.push(format!("{kind}:{group}"));
        }
    }
    anchors
}

fn random_anchor(program: &AttackProgram, genome: &ArmyGenome, rng: &mut Random) -> String {
    let choices = anchors(program, genome);
    choices[rng.index(choices.len())].clone()
}

pub(super) fn random_trigger(
    program: &AttackProgram,
    genome: &ArmyGenome,
    id: &str,
    rng: &mut Random,
    nested: bool,
) -> Json {
    let units: Vec<_> = unit_names(genome).into_iter().collect();
    let groups = groups(program);
    let steps: Vec<_> = program
        .steps
        .iter()
        .filter(|step| text(step, "id", "") != id)
        .collect();
    let spells: Vec<_> = spell_stock(genome).into_keys().collect();
    let choice = rng.index(if nested { 12 } else { 14 });
    match choice {
        0 => time(rng.unit() * 90.0),
        1 if !steps.is_empty() => object([
            (
                "after",
                string(text(steps[rng.index(steps.len())], "id", "")),
            ),
            ("delay", Json::Num(rng.unit() * 20.0)),
        ]),
        2..=5 if !units.is_empty() => {
            let key = match choice {
                2 => "inside",
                3 => "heavy_fire",
                4 => "hp_below",
                _ => "dead",
            };
            let mut when = object([(key, string(&units[rng.index(units.len())]))]);
            if choice == 3 || choice == 4 {
                put(&mut when, "frac", Json::Num(0.1 + rng.unit() * 0.8));
            }
            when
        }
        6..=8 if !groups.is_empty() => {
            let key = match choice {
                6 => "group_inside",
                7 => "near_th",
                _ => "defenders_near",
            };
            let mut when = object([(key, string(&groups[rng.index(groups.len())]))]);
            if choice == 7 {
                put(&mut when, "r", Json::Num(4.0 + rng.unit() * 16.0));
            }
            when
        }
        9 if !spells.is_empty() => object([
            ("spells_left", string(&spells[rng.index(spells.len())])),
            ("n", number(rng.index(3))),
        ]),
        10 => object([("destruction", Json::Num(rng.unit() * 100.0))]),
        12 | 13 => {
            let first = random_trigger(program, genome, id, rng, true);
            let second = random_trigger(program, genome, id, rng, true);
            object([(
                if choice == 12 { "all" } else { "any" },
                Json::Arr(vec![first, second]),
            )])
        }
        _ => time(rng.unit() * 90.0),
    }
}

/// Optional, weak priors derived by hand from local/research/usage/:
/// rage-spell.md (dangerous engagements), freeze-spell.md (active threats),
/// poison-spell.md (emerged defenders), healer.md (ground support),
/// sneaky-goblin.md (resource funnels), super-bowler.md (protected core push),
/// eternal-tome.md (dangerous passage), fireball.md (defense clusters).
/// They choose only 1/4 of proposals; every item also gets unrestricted
/// vocabulary proposals. These are search hypotheses, not new oracle rules.
fn prior(program: &AttackProgram, genome: &ArmyGenome, what: &str) -> Option<(String, Json)> {
    let groups = groups(program);
    let group = groups
        .iter()
        .find(|group| group.as_str() == "main")
        .or_else(|| groups.first())?;
    let inside = object([("group_inside", string(group))]);
    match what {
        "Rage Spell" | "Healing Spell" | "Haste Spell" | "Super Bowler" => {
            Some((format!("group:{group}"), inside))
        }
        "Freeze Spell" => Some((format!("threat:{group}"), inside)),
        "Poison Spell" => Some((
            format!("defenders:{group}"),
            object([("defenders_near", string(group))]),
        )),
        "Sneaky Goblin" => Some(("edge:funnel".to_owned(), time(0.0))),
        "Healer" => genome
            .heroes
            .iter()
            .find(|hero| hero.hero == "Archer Queen" || hero.hero == "Grand Warden")
            .map(|hero| (format!("unit:{}", hero.hero), time(5.0))),
        "Grand Warden" => Some(("building:cc".to_owned(), inside)),
        _ => None,
    }
}

fn mark_changed(step: &mut Json) {
    // playbook.py:1007 partitions uncited actions behind cited actions.
    // Learned provenance must not change that execution priority or quotes.
    put(step, "learned", Json::Bool(true));
}

fn remaining(program: &AttackProgram, genome: &ArmyGenome) -> Vec<(String, String, usize)> {
    let mut deploy = deploy_stock(genome);
    let mut spells = spell_stock(genome);
    let mut abilities: BTreeMap<_, _> = genome
        .heroes
        .iter()
        .map(|hero| (hero.hero.clone(), 1_usize))
        .collect();
    for step in &program.steps {
        let action = text(step, "action", "");
        let what = if action == "recall" {
            "Recall Spell"
        } else {
            text(step, "what", "")
        };
        let stock = match action {
            "deploy" => &mut deploy,
            "spell" | "recall" => &mut spells,
            "ability" => &mut abilities,
            _ => continue,
        };
        let left = stock.get(what).copied().unwrap_or(0);
        let used = if step.get("every").is_some() {
            left
        } else {
            super::validate::amount(step, left, if action == "deploy" { left } else { 1 })
                .unwrap_or(left)
        };
        stock.insert(what.to_owned(), left.saturating_sub(used));
    }
    let mut choices = Vec::new();
    for (action, stock) in [
        ("deploy", deploy),
        ("spell", spells),
        ("ability", abilities),
    ] {
        for (name, left) in stock {
            if left > 0 {
                choices.push((action.to_owned(), name, left));
            }
        }
    }
    if let Some(siege) = &genome.siege {
        if !program
            .steps
            .iter()
            .any(|step| text(step, "action", "") == "release_siege")
        {
            choices.push(("release_siege".to_owned(), siege.clone(), 1));
        }
    }
    let recalled = program
        .steps
        .iter()
        .filter(|step| {
            text(step, "action", "") == "recall" || text(step, "what", "") == "Recall Spell"
        })
        .count();
    let redeployed = program
        .steps
        .iter()
        .filter(|step| text(step, "action", "") == "redeploy")
        .count();
    if recalled > redeployed {
        choices.push(("redeploy".to_owned(), String::new(), 1));
    }
    choices
}

fn adjust_parameter(when: &mut Json, rng: &mut Random) {
    for key in ["all", "any"] {
        if let Some(parts) = when.get(key) {
            let mut parts = parts.arr().to_vec();
            if !parts.is_empty() {
                let index = rng.index(parts.len());
                adjust_parameter(&mut parts[index], rng);
                put(when, key, Json::Arr(parts));
                return;
            }
        }
    }
    let (key, low, high) = if when.get("t").is_some() {
        ("t", 0.0, 120.0)
    } else if when.get("after").is_some() {
        ("delay", 0.0, 45.0)
    } else if when.get("hp_below").is_some() || when.get("heavy_fire").is_some() {
        ("frac", 0.05, 0.95)
    } else if when.get("near_th").is_some() {
        ("r", 1.0, 30.0)
    } else if when.get("spells_left").is_some() {
        ("n", 0.0, 3.0)
    } else if when.get("destruction").is_some() {
        ("destruction", 0.0, 100.0)
    } else {
        return;
    };
    let value = low + rng.unit() * (high - low);
    put(
        when,
        key,
        Json::Num(if key == "n" { value.floor() } else { value }),
    );
}

/// Returns an invalid proposal with a reason instead of silently repairing
/// mutation errors. The archive can therefore never contain invalid programs.
pub fn apply(
    parent: &ArmyGenome,
    mutation: Mutation,
    rng: &mut Random,
) -> Result<ArmyGenome, String> {
    let mut child = parent.clone();
    let mut program = child
        .plan
        .program
        .take()
        .ok_or("program mutation requires --programs on")?;
    let index = rng.index(program.steps.len());
    match mutation {
        Mutation::Add => {
            let choices = remaining(&program, parent);
            if choices.is_empty() {
                return Err("program has no unspent items".to_owned());
            }
            let (action, what, left) = &choices[rng.index(choices.len())];
            let id = fresh_id(&program);
            let mut at = random_anchor(&program, parent, rng);
            let mut when = random_trigger(&program, parent, &id, rng, false);
            if rng.index(4) == 0 {
                if let Some((anchor, trigger)) = prior(&program, parent, what) {
                    at = anchor;
                    when = trigger;
                }
            }
            let count = if action == "deploy" {
                1 + rng.index(*left)
            } else {
                1
            };
            let action = if what == "Recall Spell" {
                "recall"
            } else {
                action
            };
            let groups = groups(&program);
            let group = groups.first().map_or("main", String::as_str);
            program
                .steps
                .push(step(&id, action, what, count, &at, group, when));
        }
        Mutation::Delete => {
            program.steps.remove(index);
            repair_references(&mut program.steps, parent);
        }
        Mutation::Anchor => {
            let at = random_anchor(&program, parent, rng);
            put(&mut program.steps[index], "at", string(at));
            mark_changed(&mut program.steps[index]);
        }
        Mutation::Trigger => {
            let id = text(&program.steps[index], "id", "");
            let mut when = random_trigger(&program, parent, id, rng, false);
            if rng.index(4) == 0 {
                if let Some((_, trigger)) =
                    prior(&program, parent, text(&program.steps[index], "what", ""))
                {
                    when = trigger;
                }
            }
            put(&mut program.steps[index], "when", when);
            mark_changed(&mut program.steps[index]);
        }
        Mutation::Parameter => {
            if program.steps[index].get("every").is_some() && rng.index(2) == 0 {
                put(
                    &mut program.steps[index],
                    "every",
                    Json::Num(0.5 + rng.unit() * 20.0),
                );
            } else {
                let key = if program.steps[index].get("until").is_some() && rng.index(3) == 0 {
                    "until"
                } else {
                    "when"
                };
                let mut trigger = program.steps[index]
                    .get(key)
                    .cloned()
                    .unwrap_or_else(|| time(0.0));
                adjust_parameter(&mut trigger, rng);
                put(&mut program.steps[index], key, trigger);
            }
            mark_changed(&mut program.steps[index]);
        }
        Mutation::Count => {
            let step = &mut program.steps[index];
            match text(step, "action", "") {
                "deploy" => {
                    let stock = deploy_stock(parent);
                    let left = stock.get(text(step, "what", "")).copied().unwrap_or(1);
                    put(step, "count", number(1 + rng.index(left)));
                }
                "spell" | "recall" => {
                    if step.get("every").is_some() {
                        remove(step, "every");
                        remove(step, "until");
                    } else {
                        let spell = if text(step, "action", "") == "recall" {
                            "Recall Spell"
                        } else {
                            text(step, "what", "")
                        }
                        .to_owned();
                        put(step, "every", Json::Num(2.0 + rng.unit() * 10.0));
                        put(
                            step,
                            "until",
                            object([("spells_left", string(spell)), ("n", number(0))]),
                        );
                    }
                }
                _ => return Err("count mutation requires deploy or cast".to_owned()),
            }
            mark_changed(step);
        }
        Mutation::Group => {
            let choices = ["main", "charge", "funnel", "left", "right", "duke"];
            put(
                &mut program.steps[index],
                "group",
                string(choices[rng.index(choices.len())]),
            );
            mark_changed(&mut program.steps[index]);
            repair_references(&mut program.steps, parent);
        }
        Mutation::Swap => {
            let other = rng.index(program.steps.len());
            program.steps.swap(index, other);
        }
        Mutation::Duplicate => {
            let mut duplicate = program.steps[index].clone();
            let action = text(&duplicate, "action", "").to_owned();
            if action == "deploy" {
                let count = super::validate::amount(&duplicate, 10000, 1)?;
                if count < 2 {
                    return Err("split requires two deployable units".to_owned());
                }
                let split = 1 + rng.index(count - 1);
                put(&mut duplicate, "count", number(split));
                put(&mut program.steps[index], "count", number(count - split));
            } else if matches!(action.as_str(), "spell" | "recall") {
                for step in [&mut duplicate, &mut program.steps[index]] {
                    remove(step, "every");
                    remove(step, "until");
                }
            } else {
                return Err("duplicate requires troop or spell stack".to_owned());
            }
            let id = fresh_id(&program);
            let old = text(&duplicate, "at", "edge:main");
            let mut choices = anchors(&program, parent);
            choices.retain(|anchor| anchor != old);
            put(&mut duplicate, "id", string(id));
            put(
                &mut duplicate,
                "at",
                string(&choices[rng.index(choices.len())]),
            );
            mark_changed(&mut duplicate);
            mark_changed(&mut program.steps[index]);
            program.steps.insert(index + 1, duplicate);
        }
        Mutation::Aim => {
            let step = &mut program.steps[index];
            let hero = parent
                .heroes
                .iter()
                .find(|hero| hero.hero == text(step, "what", ""))
                .ok_or("aim mutation requires a selected hero")?;
            if text(step, "action", "") != "ability" {
                return Err("aim mutation requires ability".to_owned());
            }
            let mut choices = vec![None];
            if hero.equipment.iter().any(|item| item == "Giant Arrow") {
                choices.extend([Some("arrow"), Some("building:ad"), Some("building:cc")]);
            }
            if hero.equipment.iter().any(|item| item == "Fireball") {
                choices.extend([
                    Some("building:ad"),
                    Some("building:cc"),
                    Some("building:mono"),
                ]);
            }
            if hero.equipment.iter().any(|item| item == "Rocket Backpack") {
                choices.push(Some("dash"));
            }
            match choices[rng.index(choices.len())] {
                Some(aim) => put(step, "aim", string(aim)),
                None => remove(step, "aim"),
            }
            mark_changed(step);
        }
    }
    program.normalize();
    program.validate(&child)?;
    child.plan.program = Some(program);
    child.normalize();
    Ok(child)
}

pub fn random(parent: &ArmyGenome, rng: &mut Random) -> Result<ArmyGenome, String> {
    apply(parent, MUTATIONS[rng.index(MUTATIONS.len())], rng)
}

pub fn crossover(
    first: &ArmyGenome,
    second: &ArmyGenome,
    rng: &mut Random,
) -> Result<ArmyGenome, String> {
    if super::army_identity(first) != super::army_identity(second) {
        return Err("program crossover requires the same army and loadout".to_owned());
    }
    let mut child = first.clone();
    let mut program = first
        .plan
        .program
        .clone()
        .ok_or("first parent has no program")?;
    let other = second
        .plan
        .program
        .as_ref()
        .ok_or("second parent has no program")?;
    let first_cut = rng.index(program.steps.len() + 1);
    let second_cut = rng.index(other.steps.len() + 1);
    program.steps.truncate(first_cut);
    program.steps.extend_from_slice(&other.steps[second_cut..]);
    // Duplicate IDs and overspent inventory are meaningful rejections. There
    // is no repair which could quietly change the inherited execution order.
    program.validate(&child)?;
    program.normalize();
    child.plan.program = Some(program);
    Ok(child)
}
