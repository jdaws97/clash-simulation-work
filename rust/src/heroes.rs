//! Ports heroes.py:1082-1140,1185-1200,1348-1470 hooks for stages 1 and 2.

use crate::catalog::UnitSpec;
use crate::effects;
use crate::state::{Battle, Team, UnitRef};

// heroes.py:1082-1140: combatant order includes dead members for aura reset.
pub fn apply_auras(battle: &mut Battle) {
    let combatants: Vec<_> = battle
        .attackers_pool()
        .chain(battle.defenders_pool())
        .map(|u| u.reference())
        .collect();
    let mut want = Vec::new();
    for &reference in &combatants {
        let unit = battle.unit_mut(reference);
        let boost = effects::crown_buff(unit);
        unit.aura_dmg = 1.0 + boost;
        if boost != 0.0 {
            want.push((reference, (boost, f64::INFINITY)));
        }
    }
    for &reference in &combatants {
        let unit = battle.unit(reference);
        if unit.alive && unit.name == "Apprentice Warden" {
            let percentage = battle
                .catalog
                .stats
                .get(
                    "Apprentice Warden",
                    unit.level.as_ref().expect("Apprentice Warden level"),
                    &["Aura HP Increase"],
                    None,
                )
                .expect("aura HP increase")
                / 100.0;
            let (x, y) = (unit.x, unit.y);
            let allies: Vec<_> = if reference.team == Team::Atk {
                battle.attackers_pool().map(|u| u.reference()).collect()
            } else {
                battle.defenders_pool().map(|u| u.reference()).collect()
            };
            for ally in allies {
                let a = battle.unit(ally);
                if !a.alive
                    || crate::geom::dist(a.x, a.y, x, y) > 7.0
                    || ally == reference
                    || a.name == "Totem"
                    || matches!(a.kind.as_str(), "siege" | "siege_idle")
                {
                    continue;
                }
                if percentage != 0.0 {
                    let previous = want.iter_mut().find(|(unit, _)| *unit == ally);
                    if let Some((_, (previous_pct, previous_cap))) = previous {
                        if (percentage * a.base_max_hp).min(f64::INFINITY)
                            > (*previous_pct * a.base_max_hp).min(*previous_cap)
                        {
                            *previous_pct = percentage;
                            *previous_cap = f64::INFINITY;
                        }
                    } else if (percentage * a.base_max_hp).min(f64::INFINITY) > 0.0 {
                        want.push((ally, (percentage, f64::INFINITY)));
                    }
                }
                let a = battle.unit_mut(ally);
                a.aura_dmg = a.aura_dmg.max(1.0);
            }
        }
        let unit = battle.unit(reference);
        if unit.alive && unit.name == "Grand Warden" {
            todo!("stage 3: heroes.py:1106 Grand Warden equipment auras");
        }
    }
    for reference in combatants {
        if battle.unit(reference).alive {
            let (percentage, cap) = want
                .iter()
                .find(|(unit, _)| *unit == reference)
                .map_or((0.0, 0.0), |(_, value)| *value);
            effects::health_aura(battle.unit_mut(reference), percentage, cap);
        }
    }
}

// heroes.py:1185-1200: no guardian exists in stage-1 exports.
pub fn guardians_tick(battle: &mut Battle) {
    if battle.guardian.is_some_and(|g| battle.unit(g).alive) {
        todo!("stage 3: heroes.py:1189 Guardian activation and enrage");
    }
}

// heroes.py:1348-1350: intentionally empty in Python too.
pub fn defending_hero_ability(_battle: &mut Battle, _unit: UnitRef) {
}

// heroes.py:1357-1387.
pub fn summon_tick(battle: &mut Battle, unit: UnitRef) -> bool {
    if battle.unit(unit).name != "Lavaloon" {
        return false;
    }
    todo!("stage 3: heroes.py:1360 Lavaloon equipment summon tick");
}

// heroes.py:1390-1425.
pub fn summon_death(battle: &mut Battle, unit: UnitRef) {
    if battle.unit(unit).name == "Lavaloon" {
        todo!("stage 3: heroes.py:1393 Lavaloon death pups and bomb");
    }
}

// heroes.py:1435-1449 is preprocessed in Catalog::summon_spec by Python.
// Keep this interface for callers with an unmodified specification.
pub fn summon_spec(name: &str, mut specification: UnitSpec) -> UnitSpec {
    match name {
        "Henchman" | "Booger" => specification.walls = "fly".to_owned(),
        "Lavaloon" => specification.prefer = "air_defense".to_owned(),
        "Frostmite" => {
            specification.prefer = "defense".to_owned();
            specification.walls = "ignore".to_owned();
            specification.engages_units = false;
        }
        _ => {
        }
    }
    specification
}

// heroes.py:1452-1470: bucket membership also updates for mid-tick spawns.
pub fn new_member(battle: &mut Battle, reference: UnitRef) {
    let unit = battle.unit_mut(reference);
    match unit.name.as_str() {
        "Frostmite" => unit.housing = 1,
        "Booger" => unit.housing = 4,
        _ => {
        }
    }
    if battle.buckets_initialized {
        let unit = battle.unit(reference);
        let cell = ((unit.x / 4.0) as i32, (unit.y / 4.0) as i32);
        let index = if let Some(&index) = battle.bucket_indices.get(&cell) {
            index
        } else {
            let index = battle.buckets.len();
            battle.buckets.push((cell, Vec::new()));
            battle.bucket_indices.insert(cell, index);
            index
        };
        if !battle.buckets[index].1.contains(&reference) {
            battle.buckets[index].1.push(reference);
        }
    }
    let unit = battle.unit(reference);
    for warden in battle.attackers_pool() {
        if warden.alive && warden.name == "Grand Warden" && warden.dist(unit.x, unit.y) <= 9.0 {
            todo!("stage 3: heroes.py:1470 new member moving equipment aura");
        }
    }
}
