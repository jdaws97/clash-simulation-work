//! Ports effects.py:10-124: ordered status accounting and damage provenance.

use crate::labels::Tag;
use crate::state::{Battle, Building, EntityRef, StatusSource, Team, Unit, UnitRef};

// effects.py:10-16: _src is deliberately NOT restored by this context.
// The caller owns any separate _src save/restore required by its Python rule.
pub fn damage_source<R>(
    battle: &mut Battle,
    actor: Option<EntityRef>,
    effect: Tag,
    action: impl FnOnce(&mut Battle) -> R,
) -> R {
    let previous_actor = battle.src_obj;
    let previous_effect = std::mem::replace(&mut battle.effect, effect);
    battle.src_obj = actor;
    let result = action(battle);
    battle.src_obj = previous_actor;
    battle.effect = previous_effect;
    result
}

// effects.py:31-32: reassignment retains the dictionary's insertion position.
pub fn add_slow(unit: &mut Unit, source: StatusSource, movement: f64, attack: f64, until: f64) {
    let value = (movement, attack, until);
    if let Some((_, old)) = unit.extra.slows.iter_mut().find(|(key, _)| *key == source) {
        *old = value;
    } else {
        unit.extra.slows.push((source, value));
    }
}

// effects.py:36-50: unit movement and attacks also use independent frost.
pub fn slow_mult(unit: &Unit, t: f64, movement: bool) -> f64 {
    let mut result = if movement {
        if t < unit.move_slow_until {
            unit.move_slow
        } else {
            1.0
        }
    } else if t < unit.atk_slow_until {
        unit.atk_slow
    } else {
        1.0
    };
    for (_, (move_factor, attack_factor, until)) in &unit.extra.slows {
        if t < *until {
            result *= if movement {
                *move_factor
            } else {
                *attack_factor
            };
        }
    }
    result * crate::units::frost_mult(&unit.extra.frost_effects, t)
}

// effects.py:36-50; defense.py:597-598: building callers use attack slowdown.
pub fn building_slow_mult(building: &Building, t: f64) -> f64 {
    let mut result = if t < building.atk_slow_until {
        building.atk_slow
    } else {
        1.0
    };
    for (_, (_, attack, until)) in &building.extra.slows {
        if t < *until {
            result *= *attack;
        }
    }
    result * crate::units::frost_mult(&building.extra.frost_effects, t)
}

// effects.py:47-50.
pub fn invulnerable(unit: &Unit, t: f64) -> bool {
    t < unit.invuln_until || unit.extra.tomes.iter().any(|(_, until)| t < *until)
}

// effects.py:53-59.
pub fn torch_stats(unit: &Unit, t: f64) -> (f64, f64) {
    let (mut speed, mut reduction) = (0.0_f64, 0.0_f64);
    for (_, (until, added_speed, reduced)) in &unit.extra.torches {
        if t < *until {
            speed = speed.max(*added_speed);
            reduction = reduction.max(*reduced);
        }
    }
    (speed, reduction)
}

// effects.py:62-74: bonus health absorbs damage before base health.
pub fn health_aura(unit: &mut Unit, percentage: f64, cap: f64) {
    let capacity = (unit.base_max_hp * percentage).min(cap);
    if capacity == unit.aura_bonus {
        return;
    }
    let remaining = std::mem::replace(&mut unit.extra.aura_hp, 0.0);
    unit.hp = 0.0_f64.max(unit.hp - remaining);
    unit.max_hp -= unit.aura_bonus;
    let grant = (unit.hp * percentage).min(cap);
    unit.aura_bonus = capacity;
    unit.max_hp += capacity;
    unit.hp += grant;
    unit.extra.aura_hp = grant;
}

// effects.py:77-105: only hero equipment can receive death housing.
pub fn record_death(battle: &mut Battle, victim: UnitRef) {
    let unit = battle.unit(victim);
    if unit.team != Team::Atk
        || matches!(unit.kind, Tag::Siege | Tag::SiegeIdle)
        || unit.extra.clone
        || unit.extra.mirror_clone
        || unit.extra.recalled.is_some()
    {
        return;
    }
    let housing = if unit.name == "Totem" {
        // output/research/usage/dark-crown.md: August fixed Totems to one housing.
        // https://supercell.com/en/games/clashofclans/blog/release-notes/august-update-3/
        1
    } else if unit.is_hero {
        25
    } else if unit.kind == Tag::Pet {
        20
    } else {
        unit.housing
    };
    let recipients: Vec<_> = battle
        .attackers_pool()
        .filter(|prince| {
            prince.kit.as_ref().is_some_and(|kit| kit.has("Dark Crown"))
                && prince.reference() != victim
                && prince.extra.recalled.is_none()
        })
        .map(Unit::reference)
        .collect();
    for prince in recipients {
        battle.unit_mut(prince).extra.crown_housing += housing;
    }
}

// effects.py:108-124.
pub fn crown_buff(battle: &mut Battle, reference: UnitRef) -> f64 {
    let unit = battle.unit(reference);
    if !unit.kit.as_ref().is_some_and(|kit| kit.has("Dark Crown")) {
        return 0.0;
    }
    let stage = 3.min(unit.extra.crown_housing.div_euclid(60)) as usize;
    let level = unit
        .kit
        .as_ref()
        .expect("Dark Crown kit")
        .lv("Dark Crown")
        .clone();
    battle
        .unit_mut(reference)
        .kit
        .as_mut()
        .expect("Dark Crown kit")
        .crown_stage = stage;
    if stage == 0 {
        return 0.0;
    }
    let columns = [
        "~first health & damage increase",
        "~second health & damage increase",
        "~max health increase",
    ];
    battle
        .catalog
        .stats
        .get("Dark Crown", &level, &[columns[stage - 1]], None)
        .expect("Dark Crown stage buff")
        / 100.0
}
