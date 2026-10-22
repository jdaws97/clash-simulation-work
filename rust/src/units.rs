//! Ports units.py. TASK 1d owns this file; battle AI lives in ai.rs.

use crate::state::{Battle, EntityRef, Pending, StatusSource, Unit, UnitRef};

pub const RESOURCE_KEYS: &[&str] = &["gm", "ec", "dd", "gs", "es", "ds", "th", "cc"];

// units.py:23-25 add_rage: insert/update one rage source without changing dictionary order.
pub fn add_rage(_unit: &mut Unit, _source: StatusSource, _damage: f64, _speed: f64, _until: f64) {
    todo!("TASK 1d: port units.py:23-25");
}

// units.py:28-35 rage_boost: strongest active damage and speed boosts.
pub fn rage_boost(_unit: &Unit, _t: f64) -> (f64, f64) {
    todo!("TASK 1d: port units.py:28-35");
}

// units.py:38-43 haste_speed: strongest active haste speed.
pub fn haste_speed(_unit: &Unit, _t: f64) -> f64 {
    todo!("TASK 1d: port units.py:38-43");
}

// units.py:60-74 segment_entry: first segment contact with a square hitbox.
pub fn segment_entry(
    _battle: &Battle,
    _x: f64,
    _y: f64,
    _tx: f64,
    _ty: f64,
    _target: EntityRef,
) -> Option<f64> {
    todo!("TASK 1d: port units.py:60-74");
}

// units.py:249-328 on_spawn: initialize troop specials.
pub fn on_spawn(_battle: &mut Battle, _unit: UnitRef) {
    todo!("TASK 1d: port units.py:249-328");
}

// units.py:332-542 pre_tick: upkeep; save/restore actor/effect as sourced(aura).
pub fn pre_tick(_battle: &mut Battle, _unit: UnitRef) -> bool {
    todo!("TASK 1d: port units.py:332-542");
}

// units.py:545-568 update_burrow: update burrow state and emergence.
pub fn update_burrow(_battle: &mut Battle, _unit: UnitRef, _target: Option<EntityRef>) {
    todo!("TASK 1d: port units.py:545-568");
}

// units.py:626-666 on_damaged: damage-triggered child releases.
pub fn on_damaged(_battle: &mut Battle, _unit: UnitRef, _amount: f64) {
    todo!("TASK 1d: port units.py:626-666");
}

// units.py:671-847 on_death: death effects; save/restore actor/effect as sourced(death).
pub fn on_death(_battle: &mut Battle, _unit: UnitRef) {
    todo!("TASK 1d: port units.py:671-847");
}

// units.py:984-992 inherit_clone: inherit clone flags and deadline from owner.
pub fn inherit_clone(_battle: &mut Battle, _owner: UnitRef, _child: UnitRef) {
    todo!("TASK 1d: port units.py:984-992");
}

// units.py:1152-1165 tantrum: check nearby allied air troops.
pub fn tantrum(_battle: &Battle, _unit: UnitRef) -> bool {
    todo!("TASK 1d: port units.py:1152-1165");
}

// units.py:1200-1236 valkyrie_position: choose/cache a reachable position between buildings.
pub fn valkyrie_position(
    _battle: &mut Battle,
    _unit: UnitRef,
    _target: EntityRef,
) -> Option<(f64, f64)> {
    todo!("TASK 1d: port units.py:1200-1236");
}

// units.py:1239-1247 attack_ready: per-target leap preparation deadline.
pub fn attack_ready(_battle: &mut Battle, _unit: UnitRef, _target: EntityRef) -> bool {
    todo!("TASK 1d: port units.py:1239-1247");
}

// units.py:1250-1253 effective_range: current attack reach including Long Shots.
pub fn effective_range(_unit: &Unit) -> f64 {
    todo!("TASK 1d: port units.py:1250-1253");
}

// units.py:1256-1260 target_distance: origin centre to target edge/centre; origin can be any entity.
pub fn target_distance(_battle: &Battle, _origin: EntityRef, _target: EntityRef) -> f64 {
    todo!("TASK 1d: port units.py:1256-1260");
}

// units.py:1267-1291 _new_target_delays: use exported catalog NewTargetAttackDelay values.
pub fn new_target_delays(_battle: &Battle) -> &std::collections::HashMap<String, f64> {
    todo!("TASK 1d: port units.py:1267-1291");
}

// units.py:1294-1308 new_target_windup: respect exported WINDUP and catalog delay.
pub fn new_target_windup(_battle: &mut Battle, _unit: UnitRef) {
    todo!("TASK 1d: port units.py:1294-1308");
}

// units.py:1311-1324 attack_interval: attack cadence with tantrum/burst state.
pub fn attack_interval(_battle: &mut Battle, _unit: UnitRef) -> f64 {
    todo!("TASK 1d: port units.py:1311-1324");
}

// units.py:1364-1380 _attack_targets: ordered buildings, optional walls, then opposing units.
pub fn attack_targets(_battle: &Battle, _unit: UnitRef, _walls: bool) -> Vec<EntityRef> {
    todo!("TASK 1d: port units.py:1364-1380");
}

// units.py:1383-1392 _frost: strongest current movement/attack frost.
pub fn frost(_battle: &mut Battle, _target: EntityRef, _factor: f64, _seconds: f64) {
    todo!("TASK 1d: port units.py:1383-1392");
}

// units.py:1395-1417 _chill: apply the attacker frost variant.
pub fn chill(_battle: &mut Battle, _unit: UnitRef, _target: EntityRef) {
    todo!("TASK 1d: port units.py:1395-1417");
}

// units.py:1420-1428 _hit_target: multipliers, hit, post-hit and chill accounting.
pub fn hit_target(_battle: &mut Battle, _unit: UnitRef, _target: EntityRef, _damage: f64) {
    todo!("TASK 1d: port units.py:1420-1428");
}

// units.py:1431-1440 _area_hit: ordered area hits including a missing primary.
pub fn area_hit(
    _battle: &mut Battle,
    _unit: UnitRef,
    _x: f64,
    _y: f64,
    _radius: f64,
    _damage: f64,
    _walls: bool,
    _primary: Option<EntityRef>,
) {
    todo!("TASK 1d: port units.py:1431-1440");
}

// units.py:1459-1594 _spatial_strike: area, spin, chain, bounce, pierce and suicide attacks.
pub fn spatial_strike(_battle: &mut Battle, _unit: UnitRef, _target: EntityRef, _damage: f64) {
    todo!("TASK 1d: port units.py:1459-1594");
}

// units.py:1597-1627 _mult_vs: wall/resource/defense/hero multipliers.
pub fn mult_vs(_battle: &Battle, _unit: UnitRef, _target: EntityRef) -> f64 {
    todo!("TASK 1d: port units.py:1597-1627");
}

// units.py:1630-1689 projectile_speed: optional per-unit projectile speed.
pub fn projectile_speed(_unit: &Unit) -> Option<f64> {
    todo!("TASK 1d: port units.py:1630-1689");
}

// units.py:1692-1757 launch_projectile: schedule tracked or fixed-location troop impacts.
pub fn launch_projectile(
    _battle: &mut Battle,
    _unit: UnitRef,
    _target: EntityRef,
    _damage: f64,
    _speed: f64,
    _rocket: bool,
) {
    todo!("TASK 1d: port units.py:1692-1757");
}

// units.py:1760-1831 projectile_impact: resolve detached pending impact, requeue if needed.
pub fn projectile_impact(_battle: &mut Battle, _pending: Pending) {
    todo!("TASK 1d: port units.py:1760-1831");
}

// units.py:1835-1924 strike: dispatch troop hit/projectile without changing provenance.
pub fn strike(_battle: &mut Battle, _unit: UnitRef, _target: EntityRef) {
    todo!("TASK 1d: port units.py:1835-1924");
}

// units.py:1948-2000 _after_unit_hit: post-hit poison, collateral and pushes.
pub fn after_unit_hit(_battle: &mut Battle, _unit: UnitRef, _target: UnitRef, _damage: f64) {
    todo!("TASK 1d: port units.py:1948-2000");
}

// units.py:2003-2010 interrupt_attack: reset beam and interrupted burst state.
pub fn interrupt_attack(_battle: &mut Battle, _unit: UnitRef) {
    todo!("TASK 1d: port units.py:2003-2010");
}

// units.py:2013-2016 reset_beam: remove beam target/time/tick.
pub fn reset_beam(_unit: &mut Unit) {
    todo!("TASK 1d: port units.py:2013-2016");
}

// units.py:2019-2030 track_beam: track uninterrupted beam elapsed time.
pub fn track_beam(_battle: &mut Battle, _unit: UnitRef, _target: EntityRef) {
    todo!("TASK 1d: port units.py:2019-2030");
}
