//! Ports traps.py. TASK 1c owns this file; trap setup comes from Python.

use crate::state::{Battle, Field, TrapId, Unit};

// traps.py:80-81 _raw: numeric raw registry attribute with Python default.
pub fn raw(_battle: &Battle, _name: &str, _key: &str, _default: Option<f64>) -> Option<f64> {
    todo!("TASK 1c: port traps.py:80-81");
}

// traps.py:114-123 _housing: trap interaction housing, including heroes/pets.
pub fn housing(_unit: &Unit) -> i64 {
    todo!("TASK 1c: port traps.py:114-123");
}

// traps.py:126-131 _effect_target: effect eligibility, distinct from triggering.
pub fn effect_target(_battle: &Battle, _trap: TrapId, _unit: &Unit, _t: f64) -> bool {
    todo!("TASK 1c: port traps.py:126-131");
}

// traps.py:134-146 _eligible: trigger exclusions and seeking housing limit.
pub fn eligible(_battle: &Battle, _trap: TrapId, _unit: &Unit, _t: f64) -> bool {
    todo!("TASK 1c: port traps.py:134-146");
}

// traps.py:149-173 tick: ordered trap arming, fuses and seeking flight.
pub fn tick(_battle: &mut Battle) {
    todo!("TASK 1c: port traps.py:149-173");
}

// traps.py:176-183 _fire: save/restore _src around fire_effect, not actor/effect.
pub fn fire(_battle: &mut Battle, _trap: TrapId) {
    todo!("TASK 1c: port traps.py:176-183");
}

// traps.py:186-324 _fire_effect: damage/push, springs, skeletons and tornado.
pub fn fire_effect(_battle: &mut Battle, _trap: TrapId) {
    todo!("TASK 1c: port traps.py:186-324");
}

// traps.py:327-345 _seeking_step: advance the mine toward its committed target.
pub fn seeking_step(_battle: &mut Battle, _trap: TrapId) {
    todo!("TASK 1c: port traps.py:327-345");
}

// traps.py:348-401 tornado_tick: mutate this field's pulse budget, pull units.
// Field is detached while ticking; effects that append fields keep their order.
pub fn tornado_tick(_battle: &mut Battle, _field: &mut Field) {
    todo!("TASK 1c: port traps.py:348-401");
}

// traps.py:404-431 _tornado_move: first wall contact and nextafter placement.
pub fn tornado_move(
    _battle: &mut Battle,
    _unit: crate::state::UnitRef,
    _nx: f64,
    _ny: f64,
    _until: f64,
) {
    todo!("TASK 1c: port traps.py:404-431");
}
