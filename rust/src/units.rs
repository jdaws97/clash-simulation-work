//! Ports units.py and the troop AI entry points in battle.py.

use crate::state::{Battle, UnitRef};

pub fn on_spawn(_battle: &mut Battle, _unit: UnitRef) {
    // TASK 1d: port units.py:249 on_spawn.
}

pub fn inherit_clone(_battle: &mut Battle, _owner: UnitRef, _child: UnitRef) {
    // TASK 1d: port units.py:984 inherit_clone.
}

pub fn act_attacker(_battle: &mut Battle, _unit: UnitRef) {
    // TASK 1b/1d: port battle.py:1195 _act_attacker and units.py pre_tick/strike.
}

pub fn act_defender(_battle: &mut Battle, _unit: UnitRef) {
    // TASK 1b/1d: port battle.py:1672 _act_defender and units.py pre_tick/strike.
}

pub fn separate(_battle: &mut Battle) {
    // TASK 1b: port battle.py:1087 _separate and _nudge.
}

pub fn castle(_battle: &mut Battle) {
    // TASK 1b: port battle.py:1133 _castle.
}
