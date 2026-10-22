//! Ports effects.py:9-16 damage provenance; combat effect hooks follow later.

use crate::state::{Battle, EntityRef, UnitRef};

// effects.py:9-16: _src is deliberately not part of the restored context.
pub fn damage_source(
    battle: &mut Battle,
    actor: Option<EntityRef>,
    effect: &str,
    action: impl FnOnce(&mut Battle),
) {
    let previous_actor = battle.src_obj;
    let previous_effect = std::mem::replace(&mut battle.effect, effect.to_owned());
    battle.src_obj = actor;
    action(battle);
    battle.src_obj = previous_actor;
    battle.effect = previous_effect;
}

pub fn tick_spells(_battle: &mut Battle) {
    // TASK 1c: port spells.py:258 tick, including defensive fields in stage 1.
}

pub fn resolve_pending(_battle: &mut Battle) {
    // TASK 1b: port battle.py:960 _resolve_pending.
}

pub fn guardians_tick(_battle: &mut Battle) {
    // TASK 1d: port heroes.py guardians_tick (no guardians in stage 1).
}

pub fn apply_auras(_battle: &mut Battle) {
    // TASK 1d: port heroes.py apply_auras (no hero auras in stage 1).
}

pub fn new_member(_battle: &mut Battle, _unit: UnitRef) {
    // TASK 1d: port heroes.py new_member (no hero auras in stage 1).
}
