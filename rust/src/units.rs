//! Ports units.py:23-74,249-568,626-847,984-992,1152-2030.
//! Stage 1 includes plain troops, Headhunter castle defenders and trap Skeletons.

use std::collections::HashMap;

use crate::combat::{SplashBuildingsOptions, SplashUnitsOptions};
use crate::effects;
use crate::geom;
use crate::spells;
use crate::state::{Battle, EntityRef, Pending, SpinPosition, StatusSource, Team, Unit, UnitRef};
use crate::stats::Level;

pub const RESOURCE_KEYS: &[&str] = &["gm", "ec", "dd", "gs", "es", "ds", "th", "cc"];

// units.py:1170-1197: membership only; attack order comes from attack_targets.
const SPATIAL_TROOPS: &[&str] = &[
    "Valkyrie",
    "Wizard",
    "Witch",
    "Electro Dragon",
    "Bowler",
    "Dragon",
    "Baby Dragon",
    "Balloon",
    "Wall Breaker",
    "Yetimite",
    "Firemite",
    "Meteor Golem",
    "Stone Slammer",
    "Phoenix",
    "Flame Flinger",
    "Giant Giant",
    "Super Archer",
    "Super Wizard",
    "Super Bowler",
    "Super Dragon",
    "Super Witch",
    "Super Valkyrie",
    "Rocket Balloon",
    "Witch Golem",
    "Super Wall Breaker",
    "Electromite",
];

// units.py:23-25: replacing a source keeps its dictionary insertion position.
pub fn add_rage(unit: &mut Unit, source: StatusSource, damage: f64, speed: f64, until: f64) {
    let value = (damage, speed, until);
    if let Some((_, old)) = unit
        .extra
        .rage_effects
        .iter_mut()
        .find(|(key, _)| *key == source)
    {
        *old = value;
    } else {
        unit.extra.rage_effects.push((source, value));
    }
}

// units.py:28-35: independent expiry, strongest active damage and speed.
pub fn rage_boost(unit: &Unit, t: f64) -> (f64, f64) {
    let mut damage = if t < unit.rage_until {
        unit.rage_dmg
    } else {
        1.0
    };
    let mut speed = if t < unit.rage_until {
        unit.rage_spd
    } else {
        0.0
    };
    for (_, (added_damage, added_speed, until)) in &unit.extra.rage_effects {
        if t < *until {
            damage = damage.max(*added_damage);
            speed = speed.max(*added_speed);
        }
    }
    (damage, speed)
}

// units.py:38-43.
pub fn haste_speed(unit: &Unit, t: f64) -> f64 {
    let mut speed = if t < unit.haste_until {
        unit.haste_spd
    } else {
        0.0
    };
    for (_, (added, until)) in &unit.extra.haste_effects {
        if t < *until {
            speed = speed.max(*added);
        }
    }
    speed
}

// units.py:60-74: geom implements the same closed-slab intersection.
pub fn segment_entry(
    battle: &Battle,
    x: f64,
    y: f64,
    tx: f64,
    ty: f64,
    target: EntityRef,
) -> Option<f64> {
    let (cx, cy) = battle.entity_position(target);
    let half_hit = match target {
        EntityRef::Building(id) => battle.building(id).half_hit,
        EntityRef::Wall(id) => battle.walls[id.0].half_hit,
        _ => panic!("segment_entry requires a square hitbox"),
    };
    geom::segment_entry(x, y, tx, ty, cx, cy, half_hit)
}

// units.py:249-328: stage-1 specs have no spawn-time specials.
pub fn on_spawn(battle: &mut Battle, unit: UnitRef) {
    let u = battle.unit(unit);
    let sp = &u.spec;
    if u.name == "Spell Skeleton" {
        todo!("stage 4: units.py:250 Spell Skeleton armor");
    }
    if sp.has_special("boosters") {
        todo!("stage 2: units.py:264 Rocket Balloon initial haste");
    }
    if sp.has_special("cloak") {
        todo!("stage 2: units.py:267 spawn cloak");
    }
    if sp.has_special("start_rage") {
        todo!("stage 2: units.py:269 Super Barbarian initial rage");
    }
    if sp.has_special("burrow") {
        todo!("stage 2: units.py:272 burrowing troop spawn");
    }
    if sp.has_special("yetimites") {
        todo!("stage 2: units.py:280 Yeti child reserves");
    }
    if sp.has_special("electromites") {
        todo!("stage 2: units.py:283 Super Yeti child reserves");
    }
    if sp.has_special("furnace") {
        todo!("stage 2: units.py:286 Furnace spawn and decay");
    }
    if sp.has_special("siege_barracks") {
        todo!("stage 2: units.py:292 Siege Barracks spawn queue");
    }
    if sp.has_special("logs") {
        todo!("stage 2: units.py:296 Log Launcher spawn and decay");
    }
    if sp.has_special("flinger") {
        todo!("stage 2: units.py:299 Flame Flinger decay");
    }
    if u.name == "Druid" {
        todo!("stage 2: units.py:301 Druid transformation deadline");
    }
    if sp.has_special("witch_skeletons") {
        todo!("stage 2: units.py:303 Witch summon initialization");
    }
    if sp.has_special("big_boy") {
        todo!("stage 2: units.py:306 Super Witch summon initialization");
    }
    if sp.has_special("ruin_witch") {
        todo!("stage 2: units.py:308 Ruin Witch summon initialization");
    }
    if sp.has_special("long_shot") {
        todo!("stage 2: units.py:310 Super Minion Long Shot count");
    }
    if sp.has_special("burst") {
        todo!("stage 2: units.py:314 Super Dragon burst initialization");
    }
    if sp.has_special("sky_wagon") {
        todo!("stage 2: units.py:321 Sky Wagon barrels");
    }
    if sp.has_special("troop_launcher") {
        todo!("stage 2: units.py:324 Troop Launcher barrels and lifetime");
    }
}

// units.py:331-542: sourced("aura") restores actor/effect, but never src.
pub fn pre_tick(battle: &mut Battle, unit: UnitRef) -> bool {
    effects::damage_source(battle, Some(EntityRef::Unit(unit)), "aura", |battle| {
        pre_tick_effect(battle, unit)
    })
}

fn pre_tick_effect(battle: &mut Battle, unit: UnitRef) -> bool {
    let t = battle.t;
    let sp = battle.unit(unit).spec.clone();
    if battle.unit(unit).extra.leaping {
        return true;
    }
    if battle.unit(unit).name == "Meteormite" {
        todo!("stage 2: units.py:338 Meteormite merging");
    }
    if sp.attack == "beam" {
        if let Some(target) = battle.unit(unit).target {
            if target_distance(battle, EntityRef::Unit(unit), target)
                > effective_range(battle.unit(unit))
            {
                reset_beam(battle.unit_mut(unit));
            }
        }
    }
    if battle.unit(unit).extra.mirror_clone && t >= battle.unit(unit).extra.expire_at {
        todo!("stage 3: units.py:344 Magic Mirror clone expiry");
    }
    if t >= battle.unit(unit).extra.expires_at {
        battle.kill(unit);
        return true;
    }
    if battle.unit(unit).name == "Root Rider" && unit.team == Team::Atk {
        todo!("stage 2: units.py:352 Root Rider wall contact pulses");
    }
    if battle.unit(unit).name == "Totem" {
        todo!("stage 4: units.py:366 Totem decay and inactivity");
    }
    if battle.unit(unit).decay > 0.0 {
        let decay = battle.unit(unit).decay * battle.dt;
        battle.unit_mut(unit).hp -= decay;
        if battle.unit(unit).hp <= 0.0 {
            battle.kill(unit);
            return true;
        }
    }
    if battle.unit(unit).kind == "pet" {
        todo!("stage 3: units.py:371 pet passives and actions");
    }
    if battle.unit(unit).kit.is_some() {
        todo!("stage 3: units.py:379 hero equipment tick and dash");
    }
    let u = battle.unit(unit);
    if u.name == "Giant Giant" && !u.extra.enraged && u.hp <= 0.5 * u.max_hp {
        todo!("stage 2: units.py:392 Giant Giant enrage");
    }
    if sp.special.is_empty() {
        return false;
    }
    if sp.has_special("titan_aura") {
        todo!("stage 2: units.py:399 Electro Titan aura");
    }
    if u.name == "Druid" && t >= u.extra.bear_at {
        todo!("stage 2: units.py:419 Druid timed transformation");
    }
    if sp.has_special("ruin_witch") && unit.team == Team::Atk {
        todo!("stage 2: units.py:422 Ruin Witch rubble delivery");
    }
    if sp.has_special("witch_skeletons") && u.can_act(t) && t >= u.extra.next_summon {
        todo!("stage 2: units.py:469 Witch skeleton summons");
    }
    if sp.has_special("big_boy") && t >= u.extra.next_summon {
        todo!("stage 2: units.py:491 Super Witch Big Boy summons");
    }
    if sp.has_special("furnace")
        && unit.team == Team::Def
        && !battle
            .attackers_pool()
            .any(|attacker| attacker.targetable(battle) && attacker.name != "Totem")
    {
        todo!("stage 2: units.py:496 idle defending Furnace summon clock");
    }
    if sp.has_special("furnace") && t >= u.extra.next_mite && u.extra.mites > 0 {
        todo!("stage 2: units.py:502 Furnace Firemite summons");
    }
    if sp.has_special("siege_barracks") && t >= u.extra.next && !u.extra.queue.is_empty() {
        todo!("stage 2: units.py:515 Siege Barracks troop release");
    }
    if sp.has_special("logs") && u.can_act(t) && t >= u.extra.next_log {
        todo!("stage 2: units.py:525 Log Launcher rolling logs");
    }
    if sp.has_special("troop_launcher")
        && u.can_act(t)
        && t >= u.extra.next
        && u.extra.barrels > 0
    {
        todo!("stage 2: units.py:528 Troop Launcher barrel release");
    }
    if sp.has_special("blimp_bombs") && u.can_act(t) && t >= u.extra.next_bomb {
        todo!("stage 2: units.py:538 Battle Blimp bomb drops");
    }
    false
}

// units.py:545-568.
pub fn update_burrow(battle: &mut Battle, unit: UnitRef, _target: Option<EntityRef>) {
    if !battle.unit(unit).spec.has_special("burrow") {
        return;
    }
    todo!("stage 2: units.py:548 burrow retreat, hiding and Battle Drill emergence");
}

// units.py:626-666: stage-1 units have neither damage-triggered child ability.
pub fn on_damaged(battle: &mut Battle, unit: UnitRef, _amount: f64) {
    let sp = &battle.unit(unit).spec;
    if sp.has_special("electromites") {
        todo!("stage 2: units.py:628 damage-triggered Electromites");
    }
    if sp.has_special("yetimites") {
        todo!("stage 2: units.py:651 damage-triggered Yetimites");
    }
}

// units.py:670-847: the decorator supplies death provenance to immediate hits.
pub fn on_death(battle: &mut Battle, unit: UnitRef) {
    effects::damage_source(battle, Some(EntityRef::Unit(unit)), "death", |battle| {
        on_death_effect(battle, unit);
    });
}

fn on_death_effect(battle: &mut Battle, unit: UnitRef) {
    let sp = battle.unit(unit).spec.clone();
    let t = battle.t;
    if let Some(key) = sp.death_damage.as_deref().filter(|key| !key.is_empty()) {
        if !battle.unit(unit).extra.suicided {
            let u = battle.unit(unit);
            if u.name == "Longshot" {
                todo!("stage 3: units.py:679 Longshot air death damage");
            }
            let death_air = false;
            let damage = battle
                .catalog
                .stats
                .get(
                    &u.name,
                    u.level.as_ref().expect("death damage level"),
                    &[key],
                    Some(0.0),
                )
                .expect("death damage default");
            let radius = if sp.death_radius != 0.0 {
                sp.death_radius
            } else {
                1.2
            };
            let (x, y) = (u.x, u.y);
            let opposing_team = if unit.team == Team::Atk {
                Team::Def
            } else {
                Team::Atk
            };
            if damage != 0.0 && sp.death_delay > 0.0 {
                let mut pending = Pending::new(
                    t + sp.death_delay,
                    x,
                    y,
                    radius,
                    damage,
                    death_air,
                    true,
                    &u.name,
                );
                pending.team = opposing_team;
                pending.extra.buildings = if unit.team == Team::Atk {
                    damage
                } else {
                    0.0
                };
                pending.actor = Some(EntityRef::Unit(unit));
                pending.effect = Some("death".to_owned());
                battle.add_pending(pending);
            } else if damage != 0.0 {
                if unit.team == Team::Atk {
                    let wall_key = format!("{key} vs. Walls");
                    let alternate =
                        key.replace("Damage when destroyed", "Damage when destroyed to Walls");
                    let wall_damage = battle
                        .catalog
                        .stats
                        .get(
                            &u.name,
                            u.level.as_ref().expect("death damage level"),
                            &[&wall_key, &alternate],
                            Some(damage),
                        )
                        .expect("wall death damage default");
                    battle.splash_buildings(
                        x,
                        y,
                        radius,
                        damage,
                        SplashBuildingsOptions {
                            walls: true,
                            wall_mult: wall_damage / damage,
                            ..Default::default()
                        },
                    );
                }
                battle.splash_units(
                    x,
                    y,
                    radius,
                    damage,
                    death_air,
                    true,
                    SplashUnitsOptions {
                        team: opposing_team,
                        ..Default::default()
                    },
                );
            }
        }
    }
    if sp.death_freeze.as_ref().is_some_and(|key| !key.is_empty()) {
        todo!("stage 2: units.py:714 troop death freeze");
    }
    if !sp.death_spawn.is_empty() {
        todo!("stage 2: units.py:756 troop death summons");
    }
    if sp.has_special("death_bolts") {
        todo!("stage 2: units.py:777 Electro Dragon death bolts");
    }
    if sp.has_special("smasher") && unit.team == Team::Def {
        todo!("stage 2: units.py:799 defending Smasher death Rage");
    }
    if sp.has_special("death_rage") {
        todo!("stage 2: units.py:802 Super Valkyrie death Rage");
    }
    if sp.has_special("hog_split") && unit.team == Team::Atk {
        todo!("stage 2: units.py:827 Super Hog Rider death split");
    }
    if (sp.has_special("yetimites") || sp.has_special("electromites"))
        && battle.unit(unit).extra.mites > 0
    {
        todo!("stage 2: units.py:829 remaining death child release");
    }
    if battle.unit(unit).name == "Druid" && !battle.unit(unit).extra.sprung {
        todo!("stage 2: units.py:844 Druid death transformation");
    }
    if sp.has_special("siege_cc") && unit.team == Team::Atk {
        todo!("stage 2: units.py:846 siege Clan Castle cargo release");
    }
}

// units.py:984-992: ordinary spawned descendants do not enter clone bookkeeping.
pub fn inherit_clone(battle: &mut Battle, owner: UnitRef, _child: UnitRef) {
    if !battle.unit(owner).extra.clone {
        return;
    }
    todo!("stage 4: units.py:987 Clone Spell descendant inheritance");
}

// units.py:1152-1165.
pub fn tantrum(battle: &Battle, unit: UnitRef) -> bool {
    if !battle.unit(unit).spec.has_special("tantrum") {
        return false;
    }
    todo!("stage 2: units.py:1155 Baby Dragon allied-air Tantrum check");
}

// units.py:1200-1236: cache identity, closed segment contacts, first minimum.
pub fn valkyrie_position(
    battle: &mut Battle,
    unit: UnitRef,
    target: EntityRef,
) -> Option<(f64, f64)> {
    let u = battle.unit(unit);
    if u.name != "Valkyrie" {
        return None;
    }
    let EntityRef::Building(target_id) = target else {
        return None;
    };
    if let Some(saved) = &u.extra.spin_position {
        if saved.first == target_id
            && battle.building(saved.second).alive
            && battle.building_targetable(saved.second)
        {
            return Some(saved.position);
        }
    }
    let first = battle.building(target_id);
    let mut best = None;
    for other in &battle.buildings {
        if other.id == target_id || !battle.building_targetable(other.id) {
            continue;
        }
        let px = (first.x + first.half_hit).min((first.x - first.half_hit).max(other.x));
        let py = (first.y + first.half_hit).min((first.y - first.half_hit).max(other.y));
        let qx = (other.x + other.half_hit).min((other.x - other.half_hit).max(px));
        let qy = (other.y + other.half_hit).min((other.y - other.half_hit).max(py));
        let x = (px + qx) / 2.0;
        let y = (py + qy) / 2.0;
        if first.edge_distance(x, y) > u.range || other.edge_distance(x, y) > u.spec.splash {
            continue;
        }
        let (i, j) = battle.grid.cell(x, y);
        if battle.grid.blocked[battle.grid.index(i, j)] {
            continue;
        }
        if battle.buildings.iter().any(|building| {
            building.alive
                && segment_entry(
                    battle,
                    u.x,
                    u.y,
                    x,
                    y,
                    EntityRef::Building(building.id),
                )
                .is_some()
        }) {
            continue;
        }
        let distance = geom::dist(u.x, u.y, x, y);
        if best
            .as_ref()
            .map_or(true, |(previous, _, _)| distance < *previous)
        {
            best = Some((distance, other.id, (x, y)));
        }
    }
    let saved = best.map(|(_, second, position)| SpinPosition {
        first: target_id,
        second,
        position,
    });
    let position = saved.as_ref().map(|saved| saved.position);
    battle.unit_mut(unit).extra.spin_position = saved;
    position
}

// units.py:1239-1247.
pub fn attack_ready(battle: &mut Battle, unit: UnitRef, _target: EntityRef) -> bool {
    if !matches!(battle.unit(unit).name.as_str(), "Frostmite" | "Firemite") {
        return true;
    }
    todo!("stage 2: units.py:1242 Frostmite and Firemite leap preparation");
}

// units.py:1250-1253.
pub fn effective_range(unit: &Unit) -> f64 {
    if unit.spec.has_special("long_shot") && unit.extra.long_shots > 0 {
        todo!("stage 2: units.py:1252 Super Minion Long Shot range");
    }
    unit.range
}

// units.py:1256-1260: subtract origin minus target in the unit-centre case.
pub fn target_distance(battle: &Battle, origin: EntityRef, target: EntityRef) -> f64 {
    let (x, y) = battle.entity_position(origin);
    if let EntityRef::Unit(victim) = target {
        let v = battle.unit(victim);
        geom::dist(x, y, v.x, v.y)
    } else {
        battle.entity_edge_distance(target, x, y)
    }
}

// units.py:1267-1291: Python exports the CSV-derived cache into the catalog.
pub fn new_target_delays(battle: &Battle) -> &HashMap<String, f64> {
    &battle.catalog.new_target_delays
}

// units.py:1294-1308: the exported WINDUP switch replaces the environment read.
pub fn new_target_windup(battle: &mut Battle, unit: UnitRef) {
    let u = battle.unit(unit);
    if !battle.windup || u.interval == 0.0 {
        return;
    }
    let delay = new_target_delays(battle)
        .get(&u.name)
        .copied()
        .unwrap_or(u.interval);
    let cooldown = u.cooldown.max(delay);
    battle.unit_mut(unit).cooldown = cooldown;
}

// units.py:1311-1324.
pub fn attack_interval(battle: &mut Battle, unit: UnitRef) -> f64 {
    if tantrum(battle, unit) {
        return battle.unit(unit).interval / 1.5;
    }
    if !battle.unit(unit).spec.has_special("burst") {
        return battle.unit(unit).interval;
    }
    todo!("stage 2: units.py:1319 Super Dragon burst cadence");
}

// units.py:1364-1380: snapshot buildings, optional walls, then opposing units.
pub fn attack_targets(battle: &Battle, unit: UnitRef, walls: bool) -> Vec<EntityRef> {
    let mut targets = Vec::new();
    if unit.team == Team::Atk {
        targets.extend(
            battle
                .buildings
                .iter()
                .filter(|b| b.alive && b.counted)
                .map(|b| EntityRef::Building(b.id)),
        );
        if walls {
            targets.extend(
                battle
                    .walls
                    .iter()
                    .filter(|wall| wall.alive)
                    .map(|wall| EntityRef::Wall(wall.id)),
            );
        }
    }
    let pool: Vec<_> = if unit.team == Team::Atk {
        battle.defenders_pool().map(Unit::reference).collect()
    } else {
        battle.attackers_pool().map(Unit::reference).collect()
    };
    for victim in pool {
        let v = battle.unit(victim);
        if v.alive
            && !v.extra.suspended
            && battle.t >= v.active_at
            && battle.can_hit(unit, victim)
        {
            if !(battle.unit(unit).spec.splash_ground_only && v.flying) {
                targets.push(EntityRef::Unit(victim));
            }
        }
    }
    targets
}

// units.py:1383-1392: generic frost accounting; callers exclude walls.
pub fn frost(battle: &mut Battle, target: EntityRef, factor: f64, seconds: f64) {
    let t = battle.t;
    match target {
        EntityRef::Building(id) => {
            let target = battle.building_mut(id);
            let current = if t < target.atk_slow_until {
                target.atk_slow
            } else {
                1.0
            };
            target.atk_slow = current.min(factor);
            target.atk_slow_until = target.atk_slow_until.max(t + seconds);
        }
        EntityRef::Unit(id) => {
            let target = battle.unit_mut(id);
            let current = if t < target.atk_slow_until {
                target.atk_slow
            } else {
                1.0
            };
            target.atk_slow = current.min(factor);
            target.atk_slow_until = target.atk_slow_until.max(t + seconds);
            let current = if t < target.move_slow_until {
                target.move_slow
            } else {
                1.0
            };
            target.move_slow = current.min(factor);
            target.move_slow_until = target.move_slow_until.max(t + seconds);
        }
        _ => panic!("frost requires a building or unit"),
    }
}

// units.py:1395-1417.
pub fn chill(battle: &mut Battle, unit: UnitRef, _target: EntityRef) {
    let u = battle.unit(unit);
    if u.extra.bouncing_frostmite {
        todo!("stage 3: units.py:1396 equipment Bouncing Frostmite frost");
    }
    if u.name == "Frostmite" {
        todo!("stage 2: units.py:1401 Frostmite frost (pet stage 3)");
    }
    if u.name == "Frosty" {
        todo!("stage 3: units.py:1401 Frosty frost");
    }
    if !u.spec.has_special("ice_chill") && !u.spec.has_special("chill") {
        return;
    }
    todo!("stage 2: units.py:1410 Ice Golem and Ice Hound frost");
}

// units.py:1420-1428: post-hit reactions precede frost; wall hits omit frost.
pub fn hit_target(battle: &mut Battle, unit: UnitRef, target: EntityRef, mut damage: f64) {
    damage *= mult_vs(battle, unit, target);
    if let EntityRef::Unit(victim) = target {
        battle.hit_unit(victim, damage, None, "normal", Some(EntityRef::Unit(unit)));
        after_unit_hit(battle, unit, victim, damage);
    } else {
        // Python reads the augmented-assignment left side before the hit,
        // whose destruction callbacks can recursively enter unit code.
        let previous = battle.unit(unit).damage_dealt;
        let dealt = battle.hit_building(target, damage, None, "normal");
        battle.unit_mut(unit).damage_dealt = previous + dealt;
    }
    if !matches!(target, EntityRef::Wall(_)) {
        chill(battle, unit, target);
    }
}

// units.py:1431-1440: the primary is appended only if alive and absent.
pub fn area_hit(
    battle: &mut Battle,
    unit: UnitRef,
    x: f64,
    y: f64,
    radius: f64,
    damage: f64,
    walls: bool,
    primary: Option<EntityRef>,
) {
    let mut targets = attack_targets(battle, unit, walls);
    if let Some(primary) = primary {
        if battle.entity_alive(primary) && !targets.contains(&primary) {
            targets.push(primary);
        }
    }
    for victim in targets {
        let distance = if let EntityRef::Unit(victim) = victim {
            let v = battle.unit(victim);
            geom::dist(x, y, v.x, v.y)
        } else {
            battle.entity_edge_distance(victim, x, y)
        };
        if distance <= radius {
            hit_target(battle, unit, victim, damage);
        }
    }
}

// units.py:1459-1594: Valkyrie spins at herself; other stage-1 areas at target.
pub fn spatial_strike(battle: &mut Battle, unit: UnitRef, target: EntityRef, damage: f64) {
    let u = battle.unit(unit);
    let sp = &u.spec;
    if u.name == "Stone Slammer" {
        todo!("stage 2: units.py:1461 Stone Slammer secondary hitbox");
    } else if matches!(u.name.as_str(), "Yetimite" | "Firemite") {
        todo!("stage 2: units.py:1485 Yetimite and Firemite suicide splash");
    } else if u.name == "Flame Flinger" {
        todo!("stage 2: units.py:1494 Flame Flinger three-shot splash");
    } else if sp.attack == "suicide" {
        todo!("stage 2: units.py:1501 Wall Breaker suicide blast");
    } else if sp.attack == "chain" {
        todo!("stage 2: units.py:1513 troop chain attacks");
    } else if sp.attack == "bounce" {
        todo!("stage 2: units.py:1538 troop bouncing attacks");
    } else if sp.attack == "pierce" {
        todo!("stage 2: units.py:1555 troop piercing attacks");
    } else if u.name == "Super Dragon" {
        todo!("stage 2: units.py:1569 Super Dragon footprint");
    } else if sp.attack == "spin" {
        if u.name == "Super Valkyrie" {
            todo!("stage 2: units.py:1574 Super Valkyrie spin");
        }
        let (x, y, radius) = (u.x, u.y, sp.splash);
        area_hit(battle, unit, x, y, radius, damage, true, Some(target));
    } else {
        if u.name == "Phoenix" {
            todo!("stage 3: units.py:1582 Phoenix area attack");
        }
        if !matches!(u.name.as_str(), "Wizard" | "Dragon" | "Balloon") {
            todo!("stage 2: units.py:1582 other special troop area attacks");
        }
        let radius = sp.splash;
        let (x, y) = battle.entity_position(target);
        area_hit(battle, unit, x, y, radius, damage, true, Some(target));
    }
}

// units.py:1597-1627: wall early return, then resource/defense/building factors.
pub fn mult_vs(battle: &Battle, unit: UnitRef, target: EntityRef) -> f64 {
    let u = battle.unit(unit);
    let sp = &u.spec;
    let mut multiplier = 1.0;
    if matches!(target, EntityRef::Wall(_)) {
        return sp.vs_walls;
    }
    if let EntityRef::Building(id) = target {
        let target = battle.building(id);
        if matches!(u.name.as_str(), "Spell Skeleton" | "Bat")
            && matches!(target.key.as_str(), "gs" | "es" | "ds" | "th")
        {
            todo!("stage 4: units.py:1603 spell summon storage damage reduction");
        }
        if u.name == "Frostmite"
            && (matches!(target.key.as_str(), "gs" | "es" | "ds")
                || target.key == "th" && battle.is_defense_target(id))
        {
            todo!("stage 2: units.py:1610 Frostmite storage damage reduction (pet stage 3)");
        }
        if target.kind == "resource" || RESOURCE_KEYS.contains(&target.key.as_str()) {
            multiplier *= sp.vs_resources;
        }
        if battle.is_defense_target(id) {
            multiplier *= sp.vs_defenses;
        }
        multiplier *= sp.vs_buildings;
    } else if let EntityRef::Unit(target) = target {
        if battle.unit(target).is_hero {
            multiplier *= sp.vs_heroes;
        }
    }
    multiplier
}

// units.py:1630-1689: compare integer troop levels only in the named branches.
fn level_between(unit: &Unit, low: i64, high: i64) -> bool {
    match unit.level.as_ref().expect("numeric troop level") {
        Level::Int(level) => low <= *level && *level <= high,
        Level::Text(_) => panic!("numeric troop level required"),
    }
}

pub fn projectile_speed(unit: &Unit) -> Option<f64> {
    if unit.name == "Royal Champion" {
        todo!("stage 3: units.py:1632 Royal Champion projectile speed");
    }
    if unit.name == "Minion Prince" {
        todo!("stage 3: units.py:1635 Minion Prince projectile speed");
    }
    if unit.name == "Longshot" {
        todo!("stage 3: units.py:1638 Longshot projectile speed");
    }
    if unit.name == "Wizard" && level_between(unit, 1, 3) {
        return Some(5.0);
    }
    if unit.name == "Thrower" && level_between(unit, 1, 4) {
        todo!("stage 2: units.py:1644 Thrower projectile speed");
    }
    if unit.name == "Minion" && level_between(unit, 1, 14) {
        return Some(3.8);
    }
    if matches!(unit.name.as_str(), "Witch" | "Super Witch") && level_between(unit, 1, 8) {
        todo!("stage 2: units.py:1650 Witch projectile speed");
    }
    if unit.name == "Lava Hound" && level_between(unit, 1, 8) {
        todo!("stage 2: units.py:1653 Lava Hound projectile speed");
    }
    if unit.name == "Lava Pup" {
        todo!("stage 2: units.py:1656 Lava Pup projectile speed");
    }
    if unit.name == "Super Archer" && level_between(unit, 5, 14) {
        todo!("stage 2: units.py:1659 Super Archer projectile speed");
    }
    if unit.name == "Super Dragon" && level_between(unit, 3, 12) {
        todo!("stage 2: units.py:1662 Super Dragon projectile speed");
    }
    if unit.name == "Super Minion" {
        todo!("stage 2: units.py:1665 Super Minion projectile speed");
    }
    if unit.name == "Ice Pup" {
        todo!("stage 2: units.py:1671 Ice Pup projectile speed");
    }
    if unit.name == "Super Bowler" && level_between(unit, 1, 10) {
        todo!("stage 2: units.py:1674 Super Bowler projectile speed");
    }
    if unit.name == "Bowler" && level_between(unit, 1, 10) {
        todo!("stage 2: units.py:1677 Bowler projectile speed");
    }
    if unit.name == "Frostmite" {
        todo!("stage 2: units.py:1680 Frostmite leap speed (pet stage 3)");
    }
    if unit.name == "Firemite" {
        todo!("stage 2: units.py:1683 Firemite leap speed");
    }
    if unit.name == "Lavaloon Pup" && level_between(unit, 1, 11) {
        todo!("stage 3: units.py:1686 equipment Lavaloon Pup projectile speed");
    }
    None
}

// units.py:1692-1757: single projectiles track identity; splash fixes position.
pub fn launch_projectile(
    battle: &mut Battle,
    unit: UnitRef,
    target: EntityRef,
    damage: f64,
    speed: f64,
    rocket: bool,
) {
    let u = battle.unit(unit);
    let sp = &u.spec;
    let (x, y) = battle.entity_position(target);
    let length = geom::dist(u.x, u.y, x, y);
    let mut mode = "single";
    let mut track = Some(target);
    if sp.attack == "pierce" {
        todo!("stage 2: units.py:1700 launch piercing projectile");
    } else if sp.attack == "bounce" {
        todo!("stage 2: units.py:1709 launch bouncing projectiles");
    } else if matches!(u.name.as_str(), "Firemite" | "Frostmite") {
        todo!("stage 2: units.py:1729 launch Firemite or Frostmite leap");
    } else if u.name == "Super Dragon" {
        todo!("stage 2: units.py:1732 launch Super Dragon projectile");
    } else if sp.attack == "splash" {
        mode = "area";
        track = None;
    }
    if rocket {
        todo!("stage 3: units.py:1737 launch Rocket Spear projectile");
    } else if u.name == "Longshot" {
        todo!("stage 3: units.py:1739 launch Longshot projectile");
    }
    let mut pending = Pending::new(
        battle.t + length / speed,
        x,
        y,
        sp.splash,
        damage,
        u.hits_air,
        u.hits_ground,
        &format!("unit:{}", u.name),
    );
    pending.team = if unit.team == Team::Atk {
        Team::Def
    } else {
        Team::Atk
    };
    pending.extra.troop_impact = Some(mode.to_owned());
    pending.actor = Some(EntityRef::Unit(unit));
    pending.target = track;
    battle.add_pending(pending);
}

// units.py:1760-1831: resolve even after the actor dies; source is set by caller.
pub fn projectile_impact(battle: &mut Battle, pending: Pending) {
    let Some(EntityRef::Unit(unit)) = pending.actor else {
        panic!("troop projectile actor must be a unit");
    };
    let mode = pending.extra.troop_impact.as_deref().expect("troop impact mode");
    let (x, y) = pending
        .target
        .map_or((pending.x, pending.y), |target| battle.entity_position(target));
    if mode == "pierce" {
        todo!("stage 2: units.py:1766 piercing projectile travel and requeue");
    }
    if mode == "rocket" {
        todo!("stage 3: units.py:1794 Rocket Spear impact");
    }
    if mode == "longshot" {
        todo!("stage 3: units.py:1806 Longshot same-height splash");
    }
    if mode == "single" {
        let target = pending.target.expect("single projectile target");
        if battle.entity_alive(target)
            && match target {
                EntityRef::Unit(victim) => battle.unit(victim).indirect_targetable(battle),
                _ => true,
            }
        {
            hit_target(battle, unit, target, pending.damage);
        }
        return;
    }
    if mode == "dragon" {
        todo!("stage 2: units.py:1822 Super Dragon projectile footprint");
    }
    area_hit(battle, unit, x, y, pending.radius, pending.damage, true, None);
    if mode == "leap" {
        todo!("stage 2: units.py:1828 leap landing and suicide");
    }
}

// units.py:1834-1924: the attack decorator is required for direct callers too.
pub fn strike(battle: &mut Battle, unit: UnitRef, target: EntityRef) {
    effects::damage_source(battle, Some(EntityRef::Unit(unit)), "attack", |battle| {
        strike_effect(battle, unit, target);
    });
}

fn strike_effect(battle: &mut Battle, unit: UnitRef, target: EntityRef) {
    let t = battle.t;
    let sp = battle.unit(unit).spec.clone();
    if sp.attack == "none" {
        if battle.unit(unit).name == "Ruin Witch" && unit.team == Team::Def {
            todo!("stage 2: units.py:1838 defending Ruin Witch attack");
        }
        return;
    }
    let (mut rage, _) = rage_boost(battle.unit(unit), t);
    let u = battle.unit(unit);
    rage = rage.max(u.aura_dmg).max(u.extra.bell_damage);
    let multiplier = 1.0;
    if sp.has_special("royal_rampage") && unit.team == Team::Atk {
        todo!("stage 3: units.py:1843 Dragon Duke Royal Rampage damage");
    }
    if tantrum(battle, unit) {
        rage = rage.max(2.0);
    }
    let mut damage = battle.unit(unit).dmg * multiplier;
    if sp.has_special("burst") && battle.unit(unit).extra.burst_target != Some(target) {
        todo!("stage 2: units.py:1849 Super Dragon burst target switch");
    }
    if sp.attack == "beam" {
        todo!("stage 2: units.py:1852 Inferno Dragon and Super Miner beam damage");
    }
    damage *= rage;
    if battle.unit(unit).kit.is_some() {
        // This guard also covers the later Monolith Arrow, Gauntlet and on-hit
        // equipment branches at units.py:1890-1902,1921-1924.
        todo!("stage 3: units.py:1856 hero equipment strike bonuses and effects");
    }
    let speed = projectile_speed(battle.unit(unit));
    if sp.has_special("long_shot") && battle.unit(unit).extra.long_shots > 0 {
        todo!("stage 2: units.py:1870 consume Super Minion Long Shot");
    }
    if let Some(speed) = speed {
        launch_projectile(battle, unit, target, damage, speed, false);
        return;
    }
    if SPATIAL_TROOPS.contains(&battle.unit(unit).name.as_str())
        || matches!(
            sp.attack.as_str(),
            "suicide" | "spin" | "chain" | "bounce" | "pierce"
        )
    {
        spatial_strike(battle, unit, target, damage);
        if battle.unit(unit).name == "Valkyrie" && !battle.entity_alive(target) {
            let u = battle.unit_mut(unit);
            u.target = None;
            u.wall_target = None;
        }
        if battle.unit(unit).name == "Meteor Golem" {
            todo!("stage 2: units.py:1882 Meteor Golem attack split");
        }
        if battle.unit(unit).name == "Electromite" {
            todo!("stage 2: units.py:1884 Electromite discharge death");
        }
        return;
    }
    damage *= mult_vs(battle, unit, target);
    if let EntityRef::Unit(victim) = target {
        battle.hit_unit(victim, damage, None, "normal", Some(EntityRef::Unit(unit)));
        after_unit_hit(battle, unit, victim, damage);
        chill(battle, unit, target);
        if matches!(battle.unit(unit).name.as_str(), "Miner" | "Super Miner")
            && unit.team == Team::Atk
            && !battle.entity_alive(target)
        {
            todo!("stage 2: units.py:1903 Miner reburrow after a unit kill");
        }
        return;
    }
    if unit.team == Team::Def {
        return;
    }
    battle.unit_mut(unit).damage_dealt += damage;
    if sp.attack == "splash" {
        battle.hit_building(target, damage, None, "normal");
        if sp.splash > 0.0 {
            for index in 0..battle.buildings.len() {
                let b = &battle.buildings[index];
                let (x, y) = battle.entity_position(target);
                if EntityRef::Building(b.id) != target
                    && b.alive
                    && b.edge_distance(x, y) <= sp.splash
                {
                    battle.hit_building(EntityRef::Building(b.id), damage, None, "normal");
                }
            }
        }
    } else {
        battle.hit_building(target, damage, None, "normal");
    }
    if matches!(target, EntityRef::Building(_)) {
        chill(battle, unit, target);
    }
}

// units.py:1947-2000: secondary provenance does not replace the attacker's src.
pub fn after_unit_hit(battle: &mut Battle, unit: UnitRef, target: UnitRef, damage: f64) {
    effects::damage_source(battle, Some(EntityRef::Unit(unit)), "secondary", |battle| {
        after_unit_hit_effect(battle, unit, target, damage);
    });
}

fn after_unit_hit_effect(battle: &mut Battle, unit: UnitRef, target: UnitRef, damage: f64) {
    let t = battle.t;
    let sp = battle.unit(unit).spec.clone();
    if sp.has_special("logger") {
        todo!("stage 2: units.py:1951 Logger collateral and pushback");
    }
    let victim = battle.unit(target);
    if sp.has_special("hh_poison") && !(victim.kind == "guardian" && victim.extra.waiting) {
        let u = battle.unit(unit);
        let level = u.level.as_ref().expect("Headhunter level");
        let duration = if level_between(u, i64::MIN, 3) {
            3.0
        } else {
            2.0
        };
        let slow = battle
            .catalog
            .stats
            .get("Headhunter", level, &["Speed Decrease"], Some(46.0))
            .expect("Headhunter speed default")
            / 100.0;
        let attack = battle
            .catalog
            .stats
            .get("Headhunter", level, &["Attack Rate Decrease"], Some(68.0))
            .expect("Headhunter attack default")
            / 100.0;
        let (_, slow, attack) = spells::poison_factors(battle.unit(target), 0.0, slow, attack);
        let victim = battle.unit_mut(target);
        victim.move_slow = 1.0 - slow;
        victim.move_slow_until = t + duration;
        victim.atk_slow = 1.0 - attack;
        victim.atk_slow_until = t + duration;
    }
    if !SPATIAL_TROOPS.contains(&battle.unit(unit).name.as_str())
        && matches!(sp.attack.as_str(), "splash" | "spin")
        && sp.splash > 0.0
        && !sp.has_special("logger")
    {
        let victim = battle.unit(target);
        let pool = if unit.team == Team::Atk {
            battle.defenders_near(victim.x, victim.y, sp.splash)
        } else {
            battle.attackers_near(victim.x, victim.y, sp.splash)
        };
        for other in pool {
            if other != target
                && battle.can_hit(unit, other)
                && (battle.unit(unit).name != "Longshot"
                    || battle.unit(other).flying == battle.unit(target).flying)
            {
                battle.hit_unit(other, damage, None, "normal", Some(EntityRef::Unit(unit)));
            }
        }
    }
}

// units.py:2003-2010: interruption always discards beam state first.
pub fn interrupt_attack(battle: &mut Battle, unit: UnitRef) {
    reset_beam(battle.unit_mut(unit));
    if battle.unit(unit).spec.has_special("burst") {
        todo!("stage 2: units.py:2005 interrupted Super Dragon burst reset");
    }
}

// units.py:2013-2016: None models removal, separately from a stored zero.
pub fn reset_beam(unit: &mut Unit) {
    unit.extra.beam_target = None;
    unit.extra.beam_time = None;
    unit.extra.beam_tick = None;
}

// units.py:2019-2030: common tracking state; beam damage remains stage 2.
pub fn track_beam(battle: &mut Battle, unit: UnitRef, target: EntityRef) {
    if battle.unit(unit).spec.attack != "beam" {
        return;
    }
    let t = battle.t;
    let dt = battle.dt;
    let u = battle.unit_mut(unit);
    let last = u.extra.beam_tick;
    if u.extra.beam_target != Some(target) || last.is_none() {
        u.extra.beam_time = Some(0.0);
    } else {
        let last = last.expect("beam tick");
        if t - last <= dt + 1e-9 {
            let time = u.extra.beam_time.as_mut().expect("beam time");
            *time += t - last;
        } else {
            u.extra.beam_time = Some(0.0);
        }
    }
    u.extra.beam_target = Some(target);
    u.extra.beam_tick = Some(t);
}
