//! Ports units.py troop behavior through the ranked stage-5 armies.
//! Unrelated troops and later-stage content retain explicit unsupported branches.

use std::sync::Arc;

use std::collections::HashSet;

use crate::battle::SpawnOptions;
use crate::combat::{SplashBuildingsOptions, SplashUnitsOptions};
use crate::effects;
use crate::fast_hash::FastMap as HashMap;
use crate::geom;
use crate::grid::{TargetIdentity, RES};
use crate::heroes;
use crate::labels::{Name, Special, Tag};
use crate::spells;
use crate::state::{
    Battle, CargoEntry, EntityRef, Pending, SpinPosition, StatusSource, Team, Unit, UnitRef, WallId,
};
use crate::stats::Level;

pub const RESOURCE_KEYS: &[&str] = &["gm", "ec", "dd", "gs", "es", "ds", "th", "cc"];

fn unit_stat(battle: &Battle, unit: UnitRef, keys: &[&str], default: Option<f64>) -> f64 {
    let u = battle.unit(unit);
    battle
        .catalog
        .stats
        .get(&u.name, u.level.as_ref().expect("unit level"), keys, default)
        .expect("unit statistic")
}

fn spawn_child(battle: &mut Battle, owner: UnitRef, name: &str, x: f64, y: f64) -> UnitRef {
    let u = battle.unit(owner);
    battle.spawn(
        name,
        owner.team,
        x,
        y,
        SpawnOptions {
            level: u.level.clone(),
            kind: Tag::Summon,
            group: u.group.clone(),
            owner: Some(owner),
            ..Default::default()
        },
    )
}

// Python math.isclose defaults: relative tolerance 1e-9, no absolute tolerance.
pub fn isclose(a: f64, b: f64) -> bool {
    a == b
        || a.is_finite()
            && b.is_finite()
            && ((a - b).abs() <= (1e-9 * b).abs() || (a - b).abs() <= (1e-9 * a).abs())
}

// units.py:46-57: own pets count only after detachment, except a live revival.
pub fn duke_alone(battle: &Battle, unit: UnitRef) -> bool {
    let duke = battle.unit(unit);
    for ally in battle.attackers_near_iter(duke.x, duke.y, 6.0) {
        let ally_unit = battle.unit(ally);
        if ally == unit || !ally_unit.flying || ally_unit.name_id == Name::Totem {
            continue;
        }
        if ally_unit.kind == Tag::Pet && ally_unit.owner == Some(unit) {
            let phoenix = duke.kit.as_ref().is_some_and(|kit| kit.doomed_at.is_some());
            if !ally_unit.extra.rampage_detached || phoenix {
                continue;
            }
        }
        return false;
    }
    true
}

// units.py:1170-1197: membership only; attack order comes from attack_targets.
const SPATIAL_TROOPS: &[Name] = &[
    Name::Valkyrie,
    Name::Wizard,
    Name::Witch,
    Name::ElectroDragon,
    Name::Bowler,
    Name::Dragon,
    Name::BabyDragon,
    Name::Balloon,
    Name::WallBreaker,
    Name::Yetimite,
    Name::Firemite,
    Name::MeteorGolem,
    Name::StoneSlammer,
    Name::Phoenix,
    Name::FlameFlinger,
    Name::GiantGiant,
    Name::SuperArcher,
    Name::SuperWizard,
    Name::SuperBowler,
    Name::SuperDragon,
    Name::SuperWitch,
    Name::SuperValkyrie,
    Name::RocketBalloon,
    Name::WitchGolem,
    Name::SuperWallBreaker,
    Name::Electromite,
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

// units.py:92-163: connectivity is membership-only; building and route order
// determine the selected wall. Cached access components treat walls as solid.
pub fn wall_breaker_target(battle: &mut Battle, unit: UnitRef) -> Option<WallId> {
    if battle.wall_mode(unit) == Tag::Ignore {
        return None;
    }
    let walls: Vec<_> = battle
        .walls
        .iter()
        .filter(|wall| wall.alive && !spells::wall_jumped(battle, wall.id))
        .map(|wall| ((wall.tx, wall.ty), wall.id))
        .collect();
    let mut unseen: HashSet<_> = walls.iter().map(|(key, _)| *key).collect();
    let mut connected = HashSet::new();
    while let Some(&start) = unseen.iter().next() {
        unseen.remove(&start);
        let mut todo = vec![start];
        let mut component = vec![start];
        while let Some((x, y)) = todo.pop() {
            for neighbor in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)] {
                if unseen.remove(&neighbor) {
                    component.push(neighbor);
                    todo.push(neighbor);
                }
            }
        }
        if component.len() >= 3 {
            connected.extend(component);
        }
    }
    let u = battle.unit(unit);
    let (x, y) = (u.x, u.y);
    let mut buildings: Vec<_> = battle
        .buildings
        .iter()
        .filter(|b| battle.building_targetable(b.id))
        .map(|b| (b.id, b.x, b.y, b.half_hit, b.edge_distance(x, y)))
        .collect();
    buildings.sort_by(|a, b| a.4.partial_cmp(&b.4).expect("building distance"));
    if buildings.is_empty() {
        return None;
    }
    let grid = battle.navigation_grid(unit);
    let reach = 1.0 / RES as f64;
    let component = grid.access_component(x, y);
    for building in &buildings {
        if grid.building_accessible(component, building.1, building.2, building.3, reach) {
            continue;
        }
        let route = grid.field(
            TargetIdentity::Breaker(building.0.0),
            building.1,
            building.2,
            building.3,
            reach,
            0.0,
        );
        let (mut px, mut py) = (x, y);
        let mut visited = HashSet::new();
        while visited.insert(grid.cell(px, py)) {
            let next = grid.next_step(route, px, py);
            (px, py) = (next.x, next.y);
            if next.at_goal {
                break;
            }
            if next.is_wall {
                let key = (px as i32, py as i32);
                if connected.contains(&key) {
                    return walls
                        .iter()
                        .find(|(tile, _)| *tile == key)
                        .map(|(_, id)| *id);
                }
                break;
            }
        }
    }
    None
}

// units.py:166-206: score insertion order decides ties, including zero weights.
pub fn follow_target(battle: &mut Battle, unit: UnitRef) -> Option<EntityRef> {
    let mut scores = std::mem::take(&mut battle.follow_scores_scratch);
    scores.clear();
    let target = follow_target_with_scores(battle, unit, &mut scores);
    scores.clear();
    battle.follow_scores_scratch = scores;
    target
}

fn follow_target_with_scores(
    battle: &Battle,
    unit: UnitRef,
    scores: &mut Vec<(EntityRef, f64)>,
) -> Option<EntityRef> {
    let ww = &battle.catalog.warden_weights;
    let table = ww.at("weights");
    let u = battle.unit(unit);
    let (radius, threshold) = if u.name_id == Name::ApprenticeWarden {
        (13.0, 10.0)
    } else {
        (ww.at("vision_radius").f64(), ww.at("threshold").f64())
    };
    let mut total_weight = 0.0;
    for ally in battle.attackers_near_iter(u.x, u.y, radius) {
        let a = battle.unit(ally);
        if ally == unit || !a.alive || matches!(a.name_id, Name::Totem | Name::Yetimite) {
            continue;
        }
        let weight = if a.is_hero {
            ww.at("heroes").f64()
        } else if a.kind == Tag::Pet {
            ww.at("pets").f64()
        } else {
            table.get(&a.name).map_or(0.0, |value| value.f64())
        };
        total_weight += weight;
        let target = a
            .wall_target
            .filter(|id| battle.walls[id.0].alive)
            .map(EntityRef::Wall)
            .or(a.target);
        let Some(target) = target else {
            continue;
        };
        if !battle.entity_alive(target)
            || !matches!(target, EntityRef::Building(_) | EntityRef::Wall(_))
        {
            continue;
        }
        if let Some((_, score)) = scores.iter_mut().find(|(key, _)| *key == target) {
            *score += weight;
        } else {
            scores.push((target, weight));
        }
    }
    if total_weight < threshold {
        return None;
    }
    let mut best = None;
    for &(target, score) in scores.iter() {
        if best
            .as_ref()
            .map_or(true, |(_, previous)| score > *previous)
        {
            best = Some((target, score));
        }
    }
    best.map(|(target, _)| target)
}

// units.py:209-235: dead counted buildings remain available as rubble.
pub fn rubble_target(battle: &mut Battle, unit: UnitRef) -> (Option<EntityRef>, Option<Tag>) {
    let mut best = None;
    let mut best_distance = 1e9;
    for index in 0..battle.buildings.len() {
        let b = &battle.buildings[index];
        if b.alive
            || !b.counted
            || b.extra.rubble_taken
            || battle.t < b.invisible_until
            || battle.t < b.overgrown_until
        {
            continue;
        }
        let u = battle.unit(unit);
        if b.extra.rubble_claim.is_some_and(|claim| {
            claim != u.id
                && battle
                    .unit_indices
                    .get(claim.0)
                    .and_then(|location| *location)
                    .is_some_and(|(team, index)| {
                        team == Team::Atk
                            && battle.attackers[index].in_pool
                            && battle.attackers[index].alive
                    })
        }) {
            continue;
        }
        let (id, bx, by, half) = (b.id, b.x, b.y, b.half_hit);
        let (x, y, reach) = (u.x, u.y, u.range);
        let grid = battle.navigation_grid(unit);
        if !grid.rubble_reachable(id.0, bx, by, half, reach, x, y) {
            continue;
        }
        let distance = geom::dist(x, y, bx, by);
        if distance < best_distance {
            best_distance = distance;
            best = Some(EntityRef::Building(id));
        }
    }
    (best, best.map(|_| Tag::Rubble))
}

// units.py:238-244: clocks survive a lethal hit until the next contact scan.
fn smash_wall(battle: &mut Battle, unit: UnitRef, wall: WallId) {
    let due = battle
        .unit(unit)
        .extra
        .wall_pulses
        .iter()
        .find(|(id, _)| *id == wall)
        .map_or(battle.t, |(_, due)| *due);
    if battle.t >= due || isclose(battle.t, due) {
        battle.hit_building(EntityRef::Wall(wall), 4000.0, None, "normal");
        let clocks = &mut battle.unit_mut(unit).extra.wall_pulses;
        if let Some((_, next)) = clocks.iter_mut().find(|(id, _)| *id == wall) {
            *next = due + 0.4;
        } else {
            clocks.push((wall, due + 0.4));
        }
    }
}

// units.py:249-328: spawn clocks begin before deploy-time strength scaling.
pub fn on_spawn(battle: &mut Battle, unit: UnitRef) {
    let name = battle.unit(unit).name.clone();
    let sp = Arc::clone(&battle.unit(unit).spec);
    let t = battle.t;
    if name == "Spell Skeleton" {
        battle.unit_mut(unit).extra.armor_hp = 30.0;
    }
    if sp.has_special(Special::Boosters) {
        let u = battle.unit_mut(unit);
        u.haste_spd = 52.0 / 8.0;
        u.haste_until = t + 4.0;
    }
    if sp.has_special(Special::Cloak) {
        battle.unit_mut(unit).invisible_until = t + 5.0;
    }
    if sp.has_special(Special::StartRage) {
        add_rage(
            battle.unit_mut(unit),
            StatusSource::Name("innate".to_owned()),
            1.7,
            16.0 / 8.0,
            t + 8.0,
        );
    }
    if sp.has_special(Special::Burrow) {
        todo!("stage 2: units.py:272 burrowing troop spawn");
    }
    if sp.has_special(Special::Yetimites) {
        let count = unit_stat(battle, unit, &["Yetimites spawned"], Some(14.0)) as i64;
        let u = battle.unit_mut(unit);
        u.extra.mites = count;
        u.extra.mite_dmg = 0.0;
    }
    if sp.has_special(Special::Electromites) {
        let count = unit_stat(battle, unit, &["Electromites spawned"], Some(14.0)) as i64;
        let u = battle.unit_mut(unit);
        u.extra.mites = count;
        u.extra.mite_dmg = 0.0;
    }
    if sp.has_special(Special::Furnace) {
        todo!("stage 2: units.py:286 Furnace spawn and decay");
    }
    if sp.has_special(Special::SiegeBarracks) {
        let level = battle
            .unit(unit)
            .level
            .as_ref()
            .expect("Siege Barracks level");
        let pekkas = battle
            .catalog
            .stats
            .get(&name, level, &["Troops Spawned / P.E.K.K.As"], Some(2.0))
            .expect("P.E.K.K.A count") as i64;
        let wizards = battle
            .catalog
            .stats
            .get(&name, level, &["Troops Spawned / Wizards"], Some(12.0))
            .expect("Wizard count") as i64;
        let u = battle.unit_mut(unit);
        u.decay = u.max_hp / 30.0;
        u.extra.queue = (0..pekkas)
            .map(|_| "P.E.K.K.A".to_owned())
            .chain((0..wizards).map(|_| "Wizard".to_owned()))
            .collect();
        u.extra.next = t + 0.5;
    }
    if sp.has_special(Special::Logs) {
        let u = battle.unit_mut(unit);
        u.decay = 156.0;
        u.extra.next_log = t + 1.0;
    }
    if sp.has_special(Special::Flinger) {
        todo!("stage 2: units.py:299 Flame Flinger decay");
    }
    if name == "Druid" {
        battle.unit_mut(unit).extra.bear_at = t + 30.0;
    }
    if sp.has_special(Special::WitchSkeletons) {
        todo!("stage 2: units.py:303 Witch summon initialization");
    }
    if sp.has_special(Special::BigBoy) {
        todo!("stage 2: units.py:306 Super Witch summon initialization");
    }
    if sp.has_special(Special::RuinWitch) {
        battle.unit_mut(unit).extra.knights = 0;
    }
    if sp.has_special(Special::LongShot) {
        battle.unit_mut(unit).extra.long_shots = if unit.team == Team::Atk { 8 } else { 3 };
    }
    if sp.has_special(Special::Burst) {
        todo!("stage 2: units.py:314 Super Dragon burst initialization");
    }
    if sp.has_special(Special::SkyWagon) {
        let count = unit_stat(battle, unit, &["Barrel Count"], Some(5.0)) as i64;
        let u = battle.unit_mut(unit);
        u.extra.barrels = count;
        u.extra.next = t + 2.0;
    }
    if sp.has_special(Special::TroopLauncher) {
        let count = unit_stat(battle, unit, &["Barrel Count"], Some(7.0)) as i64;
        let lifetime = unit_stat(battle, unit, &["Lifetime"], None);
        let u = battle.unit_mut(unit);
        u.extra.barrels = count;
        u.extra.next = t + 2.0;
        u.extra.expires_at = t + lifetime;
    }
}

// units.py:331-542: sourced("aura") restores actor/effect, but never src.
pub fn pre_tick(battle: &mut Battle, unit: UnitRef) -> bool {
    let u = battle.unit(unit);
    if u.extra.leaping {
        return true;
    }
    // Ordinary troops usually have no upkeep. These checks are read-only;
    // only enter the aura source context when the original body has work.
    // Keep this predicate in sync with the early work in pre_tick_effect.
    let upkeep = !u.spec.special.is_empty()
        || u.spec.attack == Tag::Beam && u.target.is_some()
        || u.name_id == Name::Meteormite
        || u.extra.mirror_clone && battle.t >= u.extra.expire_at
        || battle.t >= u.extra.expires_at
        || u.name_id == Name::RootRider && unit.team == Team::Atk
        || u.name_id == Name::Totem
        || u.decay > 0.0
        || u.kind == Tag::Pet
        || u.kit.is_some()
        || u.name_id == Name::GiantGiant && !u.extra.enraged && u.hp <= 0.5 * u.max_hp;
    if !upkeep {
        return false;
    }
    effects::damage_source(battle, Some(EntityRef::Unit(unit)), Tag::Aura, |battle| {
        pre_tick_effect(battle, unit)
    })
}

fn pre_tick_effect(battle: &mut Battle, unit: UnitRef) -> bool {
    let t = battle.t;
    // Capture the same original spec properties without atomic Arc traffic.
    let (beam, special) = {
        let spec = &battle.unit(unit).spec;
        (spec.attack == Tag::Beam, spec.special)
    };
    if battle.unit(unit).extra.leaping {
        return true;
    }
    if battle.unit(unit).name_id == Name::Meteormite && try_merge_meteor(battle, unit) {
        return true;
    }
    if beam {
        if let Some(target) = battle.unit(unit).target {
            if target_distance(battle, EntityRef::Unit(unit), target)
                > effective_range(battle.unit(unit))
            {
                reset_beam(battle.unit_mut(unit));
            }
        }
    }
    if battle.unit(unit).extra.mirror_clone && t >= battle.unit(unit).extra.expire_at {
        let unit = battle.unit_mut(unit);
        unit.alive = false;
        unit.hp = 0.0;
        return true;
    }
    if t >= battle.unit(unit).extra.expires_at {
        battle.kill(unit);
        return true;
    }
    if battle.unit(unit).name_id == Name::RootRider && unit.team == Team::Atk {
        let mut contacts = std::mem::take(&mut battle.wall_contact_scratch);
        contacts.clear();
        let u = battle.unit(unit);
        let (x, y) = (u.x, u.y);
        // The center must lie within 1.0 on each axis: half-hit 0.5 plus
        // contact reach 0.5. The extra tile margin also covers truncation at
        // negative coordinates; the exact edge-distance test remains below.
        if battle.wall_tiles_standard {
            let tile_x = x.floor() as i32;
            let tile_y = y.floor() as i32;
            for tx in tile_x.saturating_sub(2)..=tile_x.saturating_add(2) {
                for ty in tile_y.saturating_sub(2)..=tile_y.saturating_add(2) {
                    if let Some(&id) = battle.wall_indices.get(&(tx, ty)) {
                        let wall = &battle.walls[id.0];
                        if wall.alive && wall.edge_distance(x, y) <= 0.5 {
                            contacts.push(id);
                        }
                    }
                }
            }
        } else {
            contacts.extend(battle.walls.iter()
                .filter(|wall| wall.alive && wall.edge_distance(x, y) <= 0.5)
                .map(|wall| wall.id));
        }
        contacts.sort_unstable_by_key(|id| id.0);
        for &id in &contacts {
            smash_wall(battle, unit, id);
        }
        battle
            .unit_mut(unit)
            .extra
            .wall_pulses
            .retain(|(id, _)| {
                contacts
                    .binary_search_by_key(&id.0, |contact| contact.0)
                    .is_ok()
            });
        contacts.clear();
        battle.wall_contact_scratch = contacts;
    }
    if battle.unit(unit).name_id == Name::Totem || battle.unit(unit).decay > 0.0 {
        let decay = battle.unit(unit).decay * battle.dt;
        battle.unit_mut(unit).hp -= decay;
        if battle.unit(unit).hp <= 0.0 {
            battle.kill(unit);
            return true;
        }
    }
    if battle.unit(unit).kind == Tag::Pet {
        heroes::pet_passives(battle, unit);
        if battle.unit(unit).can_act(t) {
            let dt = battle.dt;
            let pet = battle.unit_mut(unit);
            pet.cooldown = (pet.cooldown - dt).max(-dt);
            heroes::act_pet(battle, unit);
        }
        return true;
    }
    if battle.unit(unit).kit.is_some() {
        heroes::tick(battle, unit);
        if !battle.unit(unit).alive {
            return true;
        }
        let hero = battle.unit(unit);
        if hero.dash.is_some() {
            if t >= hero.frozen_until && t >= hero.stun_until {
                heroes::dash_step(battle, unit);
            }
            return true;
        }
    }
    let u = battle.unit(unit);
    if u.name_id == Name::GiantGiant && !u.extra.enraged && u.hp <= 0.5 * u.max_hp {
        let u = battle.unit_mut(unit);
        u.extra.enraged = true;
        u.rage_dmg = 1.5;
        u.rage_spd = 12.0 / 8.0;
        u.rage_until = t + 20.0;
    }
    if special.is_empty() {
        return false;
    }
    if special.contains(Special::TitanAura) {
        let due = battle.unit(unit).extra.aura_next.unwrap_or(t);
        if t >= due || isclose(t, due) {
            let damage = unit_stat(battle, unit, &["Aura Damage per Hit"], None);
            battle.unit_mut(unit).extra.aura_next = Some(due + 0.4);
            let foes: Vec<_> = if unit.team == Team::Atk {
                battle.defenders_pool().map(Unit::reference).collect()
            } else {
                battle.attackers_pool().map(Unit::reference).collect()
            };
            for foe in foes {
                let u = battle.unit(unit);
                let f = battle.unit(foe);
                if f.alive && geom::dist(u.x, u.y, f.x, f.y) <= 3.5 {
                    let amount = if f.is_hero {
                        damage * 0.25
                    } else {
                        damage
                    };
                    battle.hit_unit(foe, amount, None, "normal", None);
                }
            }
            if unit.team == Team::Atk {
                for index in 0..battle.buildings.len() {
                    let b = &battle.buildings[index];
                    let u = battle.unit(unit);
                    if b.alive && b.counted && b.edge_distance(u.x, u.y) <= 3.5 {
                        battle.hit_building(EntityRef::Building(b.id), damage, None, "normal");
                    }
                }
            }
        }
    }
    let u = battle.unit(unit);
    if u.name_id == Name::Druid && t >= u.extra.bear_at {
        transform_bear(battle, unit);
        return true;
    }
    if special.contains(Special::RuinWitch) && unit.team == Team::Atk {
        if let Some((rubble, started)) = battle.unit(unit).extra.vacuum {
            if !battle.unit(unit).extra.delivery_committed && t >= started + 4.0 {
                battle.building_mut(rubble).extra.rubble_taken = true;
                let u = battle.unit_mut(unit);
                u.extra.delivery_committed = true;
                u.extra.knights += 1;
                let u = battle.unit(unit);
                let level = battle
                    .catalog
                    .stats
                    .get(
                        &u.name,
                        u.level.as_ref().expect("Ruin Witch level"),
                        &["Ruin Knight Level"],
                        None,
                    )
                    .expect("Ruin Knight level") as i64;
                let u = battle.unit(unit);
                let mut pending = Pending::new(
                    started + 6.0,
                    u.x,
                    u.y,
                    0.0,
                    0.0,
                    false,
                    false,
                    "Ruin Witch",
                );
                pending.team = unit.team;
                pending.extra.summon = Some((
                    "Ruin Knight".to_owned(),
                    Level::Int(level),
                    u.group.clone(),
                    Some(unit),
                ));
                battle.add_pending(pending);
            }
            if t >= started + 6.0 {
                let u = battle.unit_mut(unit);
                u.extra.vacuum = None;
                u.extra.delivery_committed = false;
                let u = battle.unit(unit);
                let cap = battle
                    .catalog
                    .stats
                    .get(
                        &u.name,
                        u.level.as_ref().expect("Ruin Witch level"),
                        &["Maximum Ruin Knights Summoned"],
                        None,
                    )
                    .expect("Ruin Knight cap") as i64;
                if u.extra.knights >= cap {
                    battle.kill(unit);
                }
            }
            return true;
        }
        let u = battle.unit(unit);
        if let Some(EntityRef::Building(target)) = u.target {
            let rubble = battle.building(target);
            if !rubble.alive
                && rubble.counted
                && !rubble.extra.rubble_taken
                && rubble.edge_distance(u.x, u.y) <= u.range
                && u.can_act(t)
                && t >= u.held_until
            {
                let id = u.id;
                battle.building_mut(target).extra.rubble_claim = Some(id);
                let u = battle.unit_mut(unit);
                u.extra.vacuum = Some((target, t));
                u.target = None;
                return true;
            }
        }
    }
    let u = battle.unit(unit);
    if special.contains(Special::WitchSkeletons) && u.can_act(t) && t >= u.extra.next_summon {
        todo!("stage 2: units.py:469 Witch skeleton summons");
    }
    if special.contains(Special::BigBoy) && t >= u.extra.next_summon {
        todo!("stage 2: units.py:491 Super Witch Big Boy summons");
    }
    if special.contains(Special::Furnace)
        && unit.team == Team::Def
        && !battle
            .attackers_pool()
            .any(|attacker| attacker.targetable(battle) && attacker.name_id != Name::Totem)
    {
        todo!("stage 2: units.py:496 idle defending Furnace summon clock");
    }
    if special.contains(Special::Furnace) && t >= u.extra.next_mite && u.extra.mites > 0 {
        todo!("stage 2: units.py:502 Furnace Firemite summons");
    }
    if special.contains(Special::SiegeBarracks) && t >= u.extra.next && !u.extra.queue.is_empty() {
        let name = battle.unit_mut(unit).extra.queue.remove(0);
        let level = match battle.plan.researched_level(&name) {
            Some(level) => level.clone(),
            None => battle
                .catalog
                .stats
                .max_level(&name, battle.plan.town_hall())
                .map(Level::Int),
        }
        .filter(|level| !matches!(level, Level::Int(0)))
        .unwrap_or(Level::Int(1));
        let u = battle.unit(unit);
        battle.spawn(
            &name,
            unit.team,
            u.x + 0.6,
            u.y + 0.6,
            SpawnOptions {
                level: Some(level),
                kind: Tag::Troop,
                group: u.group.clone(),
                ..Default::default()
            },
        );
        battle.unit_mut(unit).extra.next = t + 30.0 / 14.0;
    }
    let u = battle.unit(unit);
    if special.contains(Special::Logs) && u.can_act(t) && t >= u.extra.next_log {
        roll_log(battle, unit);
        battle.unit_mut(unit).extra.next_log = t + 3.0;
    }
    let u = battle.unit(unit);
    if special.contains(Special::TroopLauncher)
        && u.can_act(t)
        && t >= u.extra.next
        && u.extra.barrels > 0
    {
        if let Some(target) = launcher_target(battle, unit) {
            launch_barrel(battle, unit, EntityRef::Unit(target));
        }
    }
    let u = battle.unit(unit);
    if special.contains(Special::BlimpBombs) && u.can_act(t) && t >= u.extra.next_bomb {
        todo!("stage 2: units.py:538 Battle Blimp bomb drops");
    }
    false
}

// units.py:545-568.
pub fn update_burrow(battle: &mut Battle, unit: UnitRef, _target: Option<EntityRef>) {
    if !battle.unit(unit).spec.has_special(Special::Burrow) {
        return;
    }
    todo!("stage 2: units.py:548 burrow retreat, hiding and Battle Drill emergence");
}

// units.py:572-577: transformation does not run the Druid's death callbacks.
fn transform_bear(battle: &mut Battle, unit: UnitRef) {
    battle.unit_mut(unit).alive = false;
    let u = battle.unit(unit);
    let bear = battle.spawn(
        "Bear",
        unit.team,
        u.x,
        u.y,
        SpawnOptions {
            level: u.level.clone(),
            kind: Tag::Summon,
            group: u.group.clone(),
            owner: Some(unit),
            ..Default::default()
        },
    );
    battle.unit_mut(bear).extra.from_druid = true;
}

// units.py:580-622: launch blast, walls, buildings, then defenders at each step.
fn roll_log(battle: &mut Battle, unit: UnitRef) {
    let u = battle.unit(unit);
    let (tx, ty) = battle.th.map_or((25.0, 25.0), |id| {
        battle.entity_position(EntityRef::Building(id))
    });
    let (mut dx, mut dy) = (tx - u.x, ty - u.y);
    let length = geom::py_hypot(dx, dy);
    let length = if length == 0.0 { 1.0 } else { length };
    dx /= length;
    dy /= length;
    let level = u.level.as_ref().expect("Log Launcher level");
    let damage = battle
        .catalog
        .stats
        .get(&u.name, level, &["Damage per Hit"], Some(690.0))
        .expect("log damage")
        * u.extra.strength;
    let wall_damage = battle
        .catalog
        .stats
        .get(
            &u.name,
            level,
            &["Damage per Hit vs. Walls"],
            Some(damage * 4.0),
        )
        .expect("log wall damage");
    let point_blank = battle
        .catalog
        .stats
        .get(
            &u.name,
            level,
            &["Point-Blank Damage*", "Point-Blank Damage"],
            Some(0.0),
        )
        .expect("point blank default");
    if point_blank != 0.0 {
        let (x, y) = (u.x, u.y);
        battle.splash_buildings(
            x,
            y,
            1.0,
            point_blank,
            SplashBuildingsOptions {
                walls: true,
                wall_mult: 4.0,
                ..Default::default()
            },
        );
        battle.splash_units(
            x,
            y,
            1.0,
            point_blank,
            false,
            true,
            SplashUnitsOptions {
                team: Team::Def,
                ..Default::default()
            },
        );
    }
    let mut hit_buildings = HashSet::new();
    let mut hit_walls = HashSet::new();
    let mut hit_units = HashSet::new();
    for step in 0..41 {
        let u = battle.unit(unit);
        let (px, py) = (
            u.x + dx * step as f64 * 0.5,
            u.y + dy * step as f64 * 0.5,
        );
        for key in [
            (px as i32, py as i32),
            ((px + 0.5) as i32, py as i32),
            (px as i32, (py + 0.5) as i32),
        ] {
            if let Some(&wall) = battle.wall_indices.get(&key) {
                if battle.walls[wall.0].alive && hit_walls.insert(key) {
                    battle.hit_building(EntityRef::Wall(wall), wall_damage, None, "normal");
                }
            }
        }
        for index in 0..battle.buildings.len() {
            let b = &battle.buildings[index];
            if b.alive
                && b.counted
                && !hit_buildings.contains(&b.id)
                && b.edge_distance(px, py) < 0.8
            {
                let id = b.id;
                hit_buildings.insert(id);
                battle.hit_building(EntityRef::Building(id), damage, None, "normal");
                if hit_buildings.len() >= 4 {
                    return;
                }
            }
        }
        // Death callbacks can append defenders, as Python's live list iterator does.
        let mut index = 0;
        while index < battle.defenders.len() {
            let foe = &battle.defenders[index];
            if foe.in_pool
                && foe.alive
                && !foe.flying
                && !hit_units.contains(&foe.reference())
                && geom::dist(px, py, foe.x, foe.y) < 0.8
            {
                let victim = foe.reference();
                hit_units.insert(victim);
                battle.hit_unit(
                    victim,
                    damage,
                    None,
                    "normal",
                    Some(EntityRef::Unit(unit)),
                );
            }
            index += 1;
        }
    }
}

// units.py:626-666: damage is accumulated before testing the child thresholds.
pub fn on_damaged(battle: &mut Battle, unit: UnitRef, amount: f64) {
    if battle.unit(unit).spec.has_special(Special::Electromites) {
        battle.unit_mut(unit).extra.mite_dmg += amount;
        let mut threshold = battle.unit(unit).extra.next_mite_damage;
        while battle.unit(unit).extra.mites > 0 && battle.unit(unit).extra.mite_dmg >= threshold {
            battle.unit_mut(unit).extra.mites -= 1;
            threshold += 400.0;
            let u = battle.unit(unit);
            spawn_child(battle, unit, "Electromite", u.x, u.y);
        }
        battle.unit_mut(unit).extra.next_mite_damage = threshold;
        return;
    }
    if battle.unit(unit).spec.has_special(Special::Yetimites) {
        battle.unit_mut(unit).extra.mite_dmg += amount;
        while battle.unit(unit).extra.mites > 0 && battle.unit(unit).extra.mite_dmg >= 600.0 {
            let u = battle.unit_mut(unit);
            u.extra.mite_dmg -= 600.0;
            u.extra.mites -= 1;
            let (x, y) = (u.x + 0.4, u.y + 0.4);
            spawn_child(battle, unit, "Yetimite", x, y);
        }
    }
}

// units.py:670-847: the decorator supplies death provenance to immediate hits.
pub fn on_death(battle: &mut Battle, unit: UnitRef) {
    effects::damage_source(battle, Some(EntityRef::Unit(unit)), Tag::Death, |battle| {
        on_death_effect(battle, unit);
    });
}

fn on_death_effect(battle: &mut Battle, unit: UnitRef) {
    let sp = Arc::clone(&battle.unit(unit).spec);
    let t = battle.t;
    if let Some(key) = sp.death_damage.as_deref().filter(|key| !key.is_empty()) {
        if !battle.unit(unit).extra.suicided {
            let u = battle.unit(unit);
            let death_air = u.name_id == Name::Longshot;
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
                pending.effect = Some(Tag::Death);
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
    if let Some(key) = sp.death_freeze.as_deref().filter(|key| !key.is_empty()) {
        let u = battle.unit(unit);
        let level = u.level.as_ref().expect("death freeze level");
        let mut seconds = battle
            .catalog
            .stats
            .get(&u.name, level, &[key], Some(0.0))
            .expect("death freeze default");
        if unit.team == Team::Def {
            seconds = battle
                .catalog
                .stats
                .get(
                    &u.name,
                    level,
                    &[&key.replace("On Offense", "On Defense")],
                    Some(seconds / 2.5),
                )
                .expect("defensive freeze default");
        }
        let mut radius = sp.death_freeze_radius;
        if u.name_id == Name::IceGolem {
            if battle.offense_finished() {
                return;
            }
            radius = if unit.team == Team::Atk { 7.5 } else { 5.5 };
            if unit.team == Team::Def {
                let Level::Int(level) = level else {
                    panic!("Ice Golem level must be numeric")
                };
                seconds = [2.0, 2.25, 2.5, 2.75, 3.0, 3.25][((*level).clamp(1, 6) - 1) as usize];
            }
        } else if u.name_id == Name::IceHound {
            // This troop remains outside the stage-2 armies.
            todo!("stage 2: units.py:729 Ice Hound death freeze");
        }
        let (x, y) = (u.x, u.y);
        if unit.team == Team::Atk {
            for b in &mut battle.buildings {
                if b.alive && b.edge_distance(x, y) <= radius {
                    b.frozen_until = b.frozen_until.max(t + seconds);
                }
            }
            for foe in battle.defenders_near(x, y, radius) {
                let f = battle.unit_mut(foe);
                f.frozen_until = f.frozen_until.max(t + seconds);
            }
        } else {
            for ally in battle.attackers_near(x, y, radius) {
                let a = battle.unit_mut(ally);
                a.frozen_until = a.frozen_until.max(t + seconds);
            }
        }
    }
    if !sp.death_spawn.is_empty() {
        todo!("stage 2: units.py:756 troop death summons");
    }
    if sp.has_special(Special::DeathBolts) {
        let u = battle.unit(unit);
        let text = battle
            .catalog
            .stats
            .text(
                &u.name,
                u.level.as_ref().expect("Electro Dragon level"),
                &["Damage when destroyed"],
                None,
            )
            .unwrap_or_else(|| crate::json::Json::Str("0 x0".to_owned()));
        let damage = crate::stats::num(&text, None).unwrap_or(0.0);
        for _ in 0..6 {
            let angle = battle.rng_mut().random() * 2.0 * std::f64::consts::PI;
            let offset = battle.rng_mut().random() * 2.5;
            let u = battle.unit(unit);
            let (x, y) = (
                u.x + offset * geom::py_cos(angle),
                u.y + offset * geom::py_sin(angle),
            );
            if unit.team == Team::Atk {
                battle.splash_buildings(
                    x,
                    y,
                    2.0,
                    damage,
                    SplashBuildingsOptions {
                        walls: false,
                        ..Default::default()
                    },
                );
            }
            battle.splash_units(
                x,
                y,
                2.0,
                damage,
                false,
                true,
                SplashUnitsOptions {
                    team: if unit.team == Team::Atk {
                        Team::Def
                    } else {
                        Team::Atk
                    },
                    ..Default::default()
                },
            );
        }
    }
    if sp.has_special(Special::Smasher) && unit.team == Team::Def {
        todo!("stage 2: units.py:799 defending Smasher death Rage");
    }
    if sp.has_special(Special::DeathRage) {
        let u = battle.unit(unit);
        let mut field = crate::state::Field::new("rage", u.x, u.y, 4.0, t + 18.0);
        field.team = unit.team;
        field.value = 2.6;
        field.extra.speed = Some(26.0 / 8.0);
        field.extra.defense_damage = Some(1.6);
        field.extra.pulses = 60;
        field.extra.has_pulses = true;
        field.extra.gap = Some(0.3);
        field.extra.boost_time = 1.0;
        field.started = t;
        battle.fields.push(field);
    }
    if sp.has_special(Special::HogSplit) && unit.team == Team::Atk {
        split_hog(battle, unit);
    }
    if (sp.has_special(Special::Yetimites) || sp.has_special(Special::Electromites))
        && battle.unit(unit).extra.mites > 0
    {
        let name = if sp.has_special(Special::Yetimites) {
            "Yetimite"
        } else {
            "Electromite"
        };
        let count = battle.unit(unit).extra.mites;
        for k in 0..count {
            let u = battle.unit(unit);
            let (x, y) = (
                u.x + 0.4 * geom::py_cos(k as f64),
                u.y + 0.4 * geom::py_sin(k as f64),
            );
            spawn_child(battle, unit, name, x, y);
        }
        battle.unit_mut(unit).extra.mites = 0;
    }
    if battle.unit(unit).name_id == Name::Druid && !battle.unit(unit).extra.sprung {
        transform_bear(battle, unit);
    }
    if sp.has_special(Special::SiegeCc) && unit.team == Team::Atk {
        let u = battle.unit(unit);
        let (x, y, group) = (u.x, u.y, u.group.clone());
        release_cc_at(battle, x, y, &group, true);
    }
}

// units.py:933-981: cargo is normalized by Python, then consumed once per plan.
fn spawn_cargo(battle: &mut Battle, entry: CargoEntry, x: f64, y: f64, group: &str, siege: bool) {
    let child = battle.spawn(
        &entry.name,
        Team::Atk,
        x,
        y,
        SpawnOptions {
            level: Some(entry.level),
            kind: Tag::Troop,
            group: group.to_owned(),
            ..Default::default()
        },
    );
    let child = battle.unit_mut(child);
    child.extra.deployment_source = Some(if siege {
        "siege".to_owned()
    } else {
        entry.source
    });
    if siege && child.spec.has_special(Special::StartRage) {
        child
            .extra
            .rage_effects
            .retain(|(source, _)| *source != StatusSource::Name("innate".to_owned()));
    }
}

pub fn release_cc_at(battle: &mut Battle, x: f64, y: f64, group: &str, siege: bool) {
    if battle.plan.cc_released() {
        return;
    }
    let entries = std::mem::take(&mut battle.onboard_cargo);
    battle.plan.release_cc();
    let count = entries.len().max(1);
    for (index, entry) in entries.into_iter().enumerate() {
        let angle = 2.0 * std::f64::consts::PI * index as f64 / count as f64;
        spawn_cargo(
            battle,
            entry,
            x + 0.6 * geom::py_cos(angle),
            y + 0.6 * geom::py_sin(angle),
            group,
            siege,
        );
    }
}

// units.py:995-1014: children are allocated in position order, then health is
// quantized using their fully initialized (including inherited aura) maximum.
fn split_meteor(battle: &mut Battle, unit: UnitRef, target: EntityRef) {
    let u = battle.unit(unit);
    let small = u.hp < u.max_hp * 0.01;
    let target_position = battle.entity_position(target);
    let positions = if small {
        vec![target_position]
    } else {
        vec![(u.x, u.y), target_position]
    };
    for (x, y) in positions {
        let child = spawn_child(battle, unit, "Meteormite", x, y);
        let quantum = battle.unit(child).max_hp * 0.01;
        let hp = if small {
            1.0
        } else {
            ((battle.unit(unit).hp / 2.0) / quantum).floor() * quantum
        };
        let level = battle.unit(unit).level.clone().expect("Meteor Golem level");
        let child = battle.unit_mut(child);
        child.hp = hp;
        child.extra.meteor_components = Some(vec![("permanent".to_owned(), level)]);
    }
    battle.unit_mut(unit).alive = false;
}

// units.py:1018-1059: first coincident eligible partner in attacker list order.
fn try_merge_meteor(battle: &mut Battle, unit: UnitRef) -> bool {
    let u = battle.unit(unit);
    if unit.team != Team::Atk || u.extra.clone || !u.can_act(battle.t) {
        return false;
    }
    if u.target.is_some_and(|target| {
        battle.entity_alive(target)
            && target_distance(battle, EntityRef::Unit(unit), target) <= u.range
    }) {
        return false;
    }
    let other = battle.attackers_pool().find(|other| {
        let reference = other.reference();
        reference != unit && other.alive && other.name_id == Name::Meteormite
            && !other.extra.clone && other.level == u.level
            && other.extra.meteor_components == u.extra.meteor_components
            && other.x == u.x && other.y == u.y
            && !other.target.is_some_and(|target| {
                battle.entity_alive(target)
                    && target_distance(battle, EntityRef::Unit(reference), target) <= other.range
            })
    }).map(Unit::reference);
    let Some(other) = other else {
        return false;
    };
    let parent = battle.spawn("Meteor Golem", Team::Atk, u.x, u.y, SpawnOptions {
        level: u.level.clone(),
        group: u.group.clone(),
        ..Default::default()
    });
    let quantum = battle.unit(parent).max_hp * 0.005;
    let hp = 1.0_f64.max(((battle.unit(unit).hp + battle.unit(other).hp) / quantum).floor() * quantum);
    let mut components = battle.unit(unit).extra.meteor_components.clone().unwrap_or_default();
    components.extend(battle.unit(other).extra.meteor_components.clone().unwrap_or_default());
    let parent = battle.unit_mut(parent);
    parent.hp = hp;
    parent.extra.meteor_components = Some(components);
    battle.unit_mut(unit).alive = false;
    battle.unit_mut(other).alive = false;
    true
}

// units.py:1062-1080: Python max keeps the first (housing, -id) extreme.
fn launcher_target(battle: &Battle, unit: UnitRef) -> Option<UnitRef> {
    let mut best = None;
    let mut best_key = (i64::MIN, i64::MIN);
    for ally in battle.attackers_pool() {
        if ally.reference() == unit || !ally.alive || ally.extra.suspended
            || matches!(
                ally.name_id,
                Name::SpellSkeleton | Name::Bat | Name::Totem | Name::Furnace | Name::Firemite
            )
            || matches!(ally.kind, Tag::Siege | Tag::SiegeIdle)
            || !(ally.is_hero || ally.housing >= 2)
        {
            continue;
        }
        let key = (if ally.is_hero { 25 } else { ally.housing }, -(ally.id.0 as i64));
        if best.is_none() || key > best_key {
            best = Some(ally.reference());
            best_key = key;
        }
    }
    best
}

// units.py:1083-1149: contents, healing, one cargo entry, clock, then final death.
pub fn launch_barrel(battle: &mut Battle, unit: UnitRef, target: EntityRef) {
    if battle.unit(unit).extra.barrels <= 0 {
        return;
    }
    let (x, y) = battle.entity_position(target);
    battle.unit_mut(unit).extra.barrels -= 1;
    if battle.unit(unit).name_id == Name::SkyWagon {
        for (name, column) in [
            ("Minion", "Minions"),
            ("Balloon", "Balloon"),
            ("Baby Dragon", "Baby Dragon"),
        ] {
            let count = unit_stat(battle, unit, &[&format!("Troops Spawned / {column}")], None) as i64;
            let level = unit_stat(battle, unit, &[&format!("Troop Levels / {column}")], None) as i64;
            for _ in 0..count {
                let u = battle.unit(unit);
                battle.spawn(name, unit.team, x, y, SpawnOptions {
                    level: Some(Level::Int(level)),
                    kind: Tag::Summon,
                    group: u.group.clone(),
                    owner: Some(unit),
                    ..Default::default()
                });
            }
        }
        let damage = unit_stat(battle, unit, &["Damage per Hit*"], None);
        battle.hit_building(target, damage, None, "normal");
    } else {
        let level = unit_stat(battle, unit, &["Troop Level"], None) as i64;
        for (name, column) in [
            ("Barbarian", "Barbarians"),
            ("Archer", "Archers"),
            ("Giant", "Giants"),
            ("Wall Breaker", "Wall Breakers"),
        ] {
            let count = unit_stat(battle, unit, &[&format!("Troops Spawned / {column}")], None) as i64;
            for _ in 0..count {
                let u = battle.unit(unit);
                battle.spawn(name, unit.team, x, y, SpawnOptions {
                    level: Some(Level::Int(level)),
                    kind: Tag::Summon,
                    group: u.group.clone(),
                    owner: Some(unit),
                    ..Default::default()
                });
            }
        }
        let recipients: Vec<_> = battle.attackers_pool().filter(|ally| {
            ally.alive && !ally.flying
                && !matches!(
                    ally.name_id,
                    Name::Furnace | Name::Firemite | Name::Totem | Name::SpellSkeleton | Name::Bat
                )
                && !matches!(ally.kind, Tag::Siege | Tag::SiegeIdle)
                && geom::dist(x, y, ally.x, ally.y) <= 1.0
        }).map(Unit::reference).collect();
        for ally in recipients {
            battle.unit_mut(ally).heal(6.0);
        }
    }
    if !battle.onboard_cargo.is_empty() {
        let entry = battle.onboard_cargo.remove(0);
        let group = battle.unit(unit).group.clone();
        spawn_cargo(battle, entry, x, y, &group, true);
        if battle.onboard_cargo.is_empty() {
            battle.plan.release_cc();
        }
    }
    let next = battle.t + battle.unit(unit).interval;
    battle.unit_mut(unit).extra.next = next;
    if battle.unit(unit).extra.barrels == 0 {
        battle.kill(unit);
    }
}

// units.py:984-992: ordinary spawned descendants do not enter clone bookkeeping.
pub fn inherit_clone(battle: &mut Battle, owner: UnitRef, child: UnitRef) {
    if !battle.unit(owner).extra.clone {
        return;
    }
    let parent = battle.unit(owner);
    let casts = parent.extra.clone_casts.clone();
    let deadline = parent.extra.expire_at;
    let u = battle.unit_mut(child);
    u.extra.clone = true;
    u.extra.clone_casts = casts;
    u.extra.expire_at = deadline;
    battle.clones.push(child);
}

// units.py:1152-1165.
pub fn tantrum(battle: &Battle, unit: UnitRef) -> bool {
    if !battle.unit(unit).spec.has_special(Special::Tantrum) {
        return false;
    }
    let u = battle.unit(unit);
    let eligible = |ally: &Unit| {
        ally.reference() != unit && ally.alive && ally.flying
            && battle.t >= ally.active_at && !ally.extra.suspended
            && geom::dist(u.x, u.y, ally.x, ally.y) <= 4.5
    };
    let nearby_air = if unit.team == Team::Atk {
        battle.attackers_pool().any(eligible)
    } else {
        battle.defenders_pool().any(eligible)
    };
    !nearby_air
}

// units.py:1200-1236: cache identity, closed segment contacts, first minimum.
pub fn valkyrie_position(
    battle: &mut Battle,
    unit: UnitRef,
    target: EntityRef,
) -> Option<(f64, f64)> {
    let u = battle.unit(unit);
    if u.name_id != Name::Valkyrie {
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
pub fn attack_ready(battle: &mut Battle, unit: UnitRef, target: EntityRef) -> bool {
    if !matches!(battle.unit(unit).name_id, Name::Frostmite | Name::Firemite) {
        return true;
    }
    if battle.unit(unit).name_id == Name::Firemite {
        todo!("stage 2: units.py:1242 Firemite leap preparation");
    }
    let t = battle.t;
    let u = battle.unit_mut(unit);
    if u.extra.attack_target != Some(target) {
        u.extra.attack_target = Some(target);
        u.extra.attack_ready_at = t + 0.5;
    }
    t >= u.extra.attack_ready_at
}

// units.py:1250-1253.
pub fn effective_range(unit: &Unit) -> f64 {
    if unit.spec.has_special(Special::LongShot) && unit.extra.long_shots > 0 {
        return 10.25;
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
    if !battle.unit(unit).spec.has_special(Special::Burst) {
        return battle.unit(unit).interval;
    }
    todo!("stage 2: units.py:1319 Super Dragon burst cadence");
}

// units.py:1327-1361: Super Hog is allocated before choosing the Rider heading.
fn split_hog(battle: &mut Battle, unit: UnitRef) {
    let u = battle.unit(unit);
    battle.spawn(
        "Super Hog",
        unit.team,
        u.x,
        u.y,
        SpawnOptions {
            level: u.level.clone(),
            kind: Tag::Summon,
            group: u.group.clone(),
            owner: Some(unit),
            ..Default::default()
        },
    );
    let mut heading = battle.unit(unit).extra.heading;
    let mut target = battle.unit(unit).target;
    if heading.is_none() && target.is_none() {
        target = battle.choose_target(unit).0;
    }
    if let (None, Some(target)) = (heading, target) {
        let u = battle.unit(unit);
        let (tx, ty) = battle.entity_position(target);
        let (dx, dy) = (tx - u.x, ty - u.y);
        let length = geom::py_hypot(dx, dy);
        if length != 0.0 {
            heading = Some((dx / length, dy / length));
        }
    }
    let (dx, dy) = heading.unwrap_or((0.0, 0.0));
    let u = battle.unit(unit);
    battle.spawn(
        "Super Rider",
        unit.team,
        u.x - 5.0 * dx,
        u.y - 5.0 * dy,
        SpawnOptions {
            level: u.level.clone(),
            kind: Tag::Summon,
            group: u.group.clone(),
            owner: Some(unit),
            ..Default::default()
        },
    );
}

// units.py:1364-1380: snapshot buildings, optional walls, then opposing units.
pub fn attack_targets(battle: &mut Battle, unit: UnitRef, walls: bool) -> Vec<EntityRef> {
    let mut targets = std::mem::take(&mut battle.entity_scratch);
    targets.clear();
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
    let mut append = |v: &Unit| {
        let victim = v.reference();
        if v.alive && !v.extra.suspended && battle.t >= v.active_at
            && battle.can_hit(unit, victim)
            && !(battle.unit(unit).spec.splash_ground_only && v.flying) {
            targets.push(EntityRef::Unit(victim));
        }
    };
    if unit.team == Team::Atk {
        battle.defenders_pool().for_each(&mut append);
    } else {
        battle.attackers_pool().for_each(&mut append);
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
pub fn chill(battle: &mut Battle, unit: UnitRef, target: EntityRef) {
    let u = battle.unit(unit);
    if u.extra.bouncing_frostmite {
        frost(battle, target, 0.7, 3.0);
        return;
    }
    if u.name_id == Name::Frostmite {
        frost(battle, target, 0.5, 4.0);
        return;
    }
    if u.name_id == Name::Frosty {
        frost(battle, target, 0.5, 4.0);
        return;
    }
    if !u.spec.has_special(Special::IceChill) && !u.spec.has_special(Special::Chill) {
        return;
    }
    frost(battle, target, 0.5, 2.0);
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
    for &victim in &targets {
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
    targets.clear();
    battle.entity_scratch = targets;
}

// units.py:1459-1594: preserve target-pool order and first minimum chain ties.
pub fn spatial_strike(battle: &mut Battle, unit: UnitRef, target: EntityRef, damage: f64) {
    let u = battle.unit(unit);
    let name = u.name_id;
    let sp = Arc::clone(&u.spec);
    if name == Name::StoneSlammer {
        let (x, y) = battle.entity_position(target);
        area_hit(battle, unit, x, y, 1.0, damage, true, Some(target));
        let pair = match battle.unit(unit).level.as_ref() {
            Some(Level::Int(1)) => Some((100.0, 200.0)),
            Some(Level::Int(2)) => Some((150.0, 300.0)),
            Some(Level::Int(3)) => Some((200.0, 400.0)),
            Some(Level::Int(4)) => Some((250.0, 500.0)),
            Some(Level::Int(5)) => Some((300.0, 600.0)),
            Some(Level::Int(6)) => Some((350.0, 700.0)),
            _ => None,
        };
        if let Some((minimum, maximum)) = pair {
            let boost = damage / unit_stat(battle, unit, &["Damage per Hit / Hitbox 1"], None);
            for victim in attack_targets(battle, unit, true) {
                let distance = target_distance(battle, target, victim);
                if distance <= 3.0 {
                    let fraction = 0.0_f64.max(distance - 2.0);
                    let mut amount = (maximum - (maximum - minimum) * fraction) * boost;
                    if matches!(victim, EntityRef::Wall(_)) {
                        amount *= 25.0;
                    }
                    hit_target(battle, unit, victim, amount);
                }
            }
        }
    } else if matches!(name, Name::Yetimite | Name::Firemite) {
        battle.unit_mut(unit).extra.leaping = true;
        let (x, y) = battle.entity_position(target);
        area_hit(battle, unit, x, y, sp.splash, damage, true, Some(target));
        battle.unit_mut(unit).extra.suicided = true;
        battle.kill(unit);
    } else if name == Name::FlameFlinger {
        for _ in 0..3 {
            let (x, y) = battle.entity_position(target);
            area_hit(battle, unit, x, y, sp.splash, damage, true, Some(target));
        }
    } else if sp.attack == Tag::Suicide {
        let (x, y) = battle.entity_position(target);
        area_hit(battle, unit, x, y, sp.splash, damage, true, Some(target));
        if name == Name::WallBreaker {
            battle.unit_mut(unit).extra.suicided = true;
        }
        battle.kill(unit);
    } else if sp.attack == Tag::Chain {
        hit_target(battle, unit, target, damage);
        let mut hit = vec![target];
        let mut current = target;
        let mut amount = damage;
        for _ in 0..sp.chain {
            amount = if sp.chain_from_primary {
                damage * sp.chain_decay
            } else {
                amount * sp.chain_decay
            };
            let origin = if sp.chain_from_primary { target } else { current };
            let mut best = None;
            let mut best_key = (f64::INFINITY, f64::INFINITY);
            for victim in attack_targets(battle, unit, false) {
                if hit.contains(&victim) {
                    continue;
                }
                let distance = target_distance(battle, origin, victim);
                if distance <= sp.chain_range {
                    let max_hp = match victim {
                        EntityRef::Building(id) => battle.building(id).max_hp,
                        EntityRef::Wall(id) => battle.walls[id.0].max_hp,
                        EntityRef::Unit(id) => battle.unit(id).max_hp,
                        EntityRef::Trap(_) => unreachable!(),
                    };
                    let key = (distance, -max_hp);
                    if best.is_none() || key < best_key {
                        best = Some(victim);
                        best_key = key;
                    }
                }
            }
            let Some(next) = best else {
                break;
            };
            current = next;
            hit.push(current);
            hit_target(battle, unit, current, amount);
        }
    } else if sp.attack == Tag::Bounce {
        let u = battle.unit(unit);
        let (tx, ty) = battle.entity_position(target);
        let (dx, dy) = (tx - u.x, ty - u.y);
        let length = geom::py_hypot(dx, dy);
        let length = if length == 0.0 { 1.0 } else { length };
        for k in 0..=sp.bounces {
            let (tx, ty) = battle.entity_position(target);
            let x = tx + dx / length * sp.bounce_gap * k as f64;
            let y = ty + dy / length * sp.bounce_gap * k as f64;
            area_hit(battle, unit, x, y, sp.splash, damage, true,
                if k == 0 { Some(target) } else { None });
        }
    } else if sp.attack == Tag::Pierce {
        hit_target(battle, unit, target, damage);
        let u = battle.unit(unit);
        let (tx, ty) = battle.entity_position(target);
        let (dx, dy) = (tx - u.x, ty - u.y);
        let length = geom::py_hypot(dx, dy);
        let length = if length == 0.0 { 1.0 } else { length };
        for victim in attack_targets(battle, unit, true) {
            if victim == target {
                continue;
            }
            let u = battle.unit(unit);
            let (vx, vy) = battle.entity_position(victim);
            let (px, py) = (vx - u.x, vy - u.y);
            let along = (px * dx + py * dy) / length;
            let width = entity_half(battle, victim) + 0.3;
            if 0.0 < along && along <= sp.pierce && (px * dy - py * dx).abs() / length <= width {
                hit_target(battle, unit, victim, damage);
            }
        }
    } else if name == Name::SuperDragon {
        for victim in attack_targets(battle, unit, true) {
            let (x, y) = battle.entity_position(target);
            if dragon_footprint(battle, victim, x, y) {
                hit_target(battle, unit, victim, damage);
            }
        }
    } else if sp.attack == Tag::Spin {
        let u = battle.unit(unit);
        area_hit(battle, unit, u.x, u.y, sp.splash, damage, true, Some(target));
    } else {
        let (x, y) = battle.entity_position(target);
        area_hit(battle, unit, x, y, sp.splash, damage, true, Some(target));
    }
}

fn entity_half(battle: &Battle, target: EntityRef) -> f64 {
    match target {
        EntityRef::Building(id) => battle.building(id).half_hit,
        EntityRef::Wall(id) => battle.walls[id.0].half_hit,
        _ => 0.0,
    }
}

// units.py:1443-1456: the square's four corner cells are omitted.
fn dragon_footprint(battle: &Battle, target: EntityRef, x: f64, y: f64) -> bool {
    let half = entity_half(battle, target);
    let (tx, ty) = battle.entity_position(target);
    for dx in -2_i32..3 {
        for dy in -2_i32..3 {
            if dx.abs() == 2 && dy.abs() == 2 {
                continue;
            }
            if (tx - x - dx as f64).abs() <= half + 0.5
                && (ty - y - dy as f64).abs() <= half + 0.5
            {
                return true;
            }
        }
    }
    false
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
        if matches!(u.name_id, Name::SpellSkeleton | Name::Bat)
            && matches!(target.key.as_str(), "gs" | "es" | "ds" | "th")
        {
            multiplier *= 0.15;
        }
        if u.name_id == Name::Frostmite
            && (matches!(target.key.as_str(), "gs" | "es" | "ds")
                || target.key == "th" && battle.is_defense_target(id))
        {
            multiplier *= 0.5;
        }
        if target.kind == Tag::Resource || RESOURCE_KEYS.contains(&target.key.as_str()) {
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
    if unit.name_id == Name::RoyalChampion {
        return Some(12.0);
    }
    if unit.name_id == Name::MinionPrince {
        return Some(10.0);
    }
    if unit.name_id == Name::Longshot {
        return Some(15.0);
    }
    if unit.name_id == Name::Wizard && level_between(unit, 1, 3) {
        return Some(5.0);
    }
    if unit.name_id == Name::Thrower && level_between(unit, 1, 4) {
        return Some(7.0);
    }
    if unit.name_id == Name::Minion && level_between(unit, 1, 14) {
        return Some(3.8);
    }
    if matches!(unit.name_id, Name::Witch | Name::SuperWitch) && level_between(unit, 1, 8) {
        todo!("stage 2: units.py:1650 Witch projectile speed");
    }
    if unit.name_id == Name::LavaHound && level_between(unit, 1, 8) {
        todo!("stage 2: units.py:1653 Lava Hound projectile speed");
    }
    if unit.name_id == Name::LavaPup {
        todo!("stage 2: units.py:1656 Lava Pup projectile speed");
    }
    if unit.name_id == Name::SuperArcher && level_between(unit, 5, 14) {
        todo!("stage 2: units.py:1659 Super Archer projectile speed");
    }
    if unit.name_id == Name::SuperDragon && level_between(unit, 3, 12) {
        todo!("stage 2: units.py:1662 Super Dragon projectile speed");
    }
    if unit.name_id == Name::SuperMinion {
        return Some(if unit.extra.long_shots > 0 { 6.0 } else { 4.0 });
    }
    if unit.name_id == Name::IcePup {
        todo!("stage 2: units.py:1671 Ice Pup projectile speed");
    }
    if unit.name_id == Name::SuperBowler && level_between(unit, 1, 10) {
        return Some(4.75);
    }
    if unit.name_id == Name::Bowler && level_between(unit, 1, 10) {
        return Some(4.75);
    }
    if unit.name_id == Name::Frostmite {
        return Some(4.0);
    }
    if unit.name_id == Name::Firemite {
        todo!("stage 2: units.py:1683 Firemite leap speed");
    }
    if unit.name_id == Name::LavaloonPup && level_between(unit, 1, 11) {
        return Some(3.0);
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
    let sp = Arc::clone(&u.spec);
    let name = u.name_id;
    let source = u.source.clone();
    let (hits_air, hits_ground) = (u.hits_air, u.hits_ground);
    let (x, y) = battle.entity_position(target);
    let length = geom::dist(u.x, u.y, x, y);
    let denominator = if length == 0.0 { 1.0 } else { length };
    let (dx, dy) = ((x - u.x) / denominator, (y - u.y) / denominator);
    let mut mode = "single";
    let mut track = Some(target);
    if sp.attack == Tag::Pierce {
        todo!("stage 2: units.py:1700 launch piercing projectile");
    } else if sp.attack == Tag::Bounce {
        for index in 0..=sp.bounces {
            let travel = length + index as f64 * sp.bounce_gap;
            let (x, y) = battle.entity_position(target);
            let mut pending = Pending::new(
                battle.t + travel / speed,
                x + dx * index as f64 * sp.bounce_gap,
                y + dy * index as f64 * sp.bounce_gap,
                sp.splash,
                damage,
                hits_air,
                hits_ground,
                source.clone(),
            );
            pending.team = if unit.team == Team::Atk { Team::Def } else { Team::Atk };
            pending.extra.troop_impact = Some("area".to_owned());
            pending.actor = Some(EntityRef::Unit(unit));
            battle.add_pending(pending);
        }
        return;
    } else if name == Name::Frostmite {
        mode = "leap";
        battle.unit_mut(unit).extra.leaping = true;
    } else if name == Name::Firemite {
        todo!("stage 2: units.py:1729 launch Firemite or Frostmite leap");
    } else if name == Name::SuperDragon {
        todo!("stage 2: units.py:1732 launch Super Dragon projectile");
    } else if sp.attack == Tag::Splash {
        mode = "area";
        track = None;
    }
    if rocket {
        mode = "rocket";
    } else if name == Name::Longshot {
        mode = "longshot";
        track = Some(target);
    }
    let mut pending = Pending::new(
        battle.t + length / speed,
        x,
        y,
        sp.splash,
        damage,
        hits_air,
        hits_ground,
        source,
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
        let target = pending.target.expect("Rocket Spear target");
        if battle.entity_alive(target) && match target {
            EntityRef::Unit(victim) => battle.unit(victim).indirect_targetable(battle),
            _ => true,
        } {
            heroes::damage_target(battle, target, pending.damage);
            heroes::blast(battle, x, y, 0.9, pending.damage, Some(target), 1.0);
        }
        return;
    }
    if mode == "longshot" {
        let Some(EntityRef::Unit(target)) = pending.target else {
            panic!("Longshot target must be a unit");
        };
        let flying = battle.unit(target).flying;
        let mut targets = attack_targets(battle, unit, false);
        for &victim in &targets {
            if let EntityRef::Unit(reference) = victim {
                let victim_unit = battle.unit(reference);
                if victim_unit.flying == flying && geom::dist(victim_unit.x, victim_unit.y, x, y) <= pending.radius {
                    hit_target(battle, unit, victim, pending.damage);
                }
            }
        }
        targets.clear();
        battle.entity_scratch = targets;
        return;
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
        let u = battle.unit_mut(unit);
        if u.name_id != Name::Frostmite {
            todo!("stage 2: units.py:1828 Firemite landing and suicide");
        }
        u.x = x;
        u.y = y;
        u.extra.suicided = true;
        battle.kill(unit);
    }
}

// units.py:1834-1924: the attack decorator is required for direct callers too.
pub fn strike(battle: &mut Battle, unit: UnitRef, target: EntityRef) {
    effects::damage_source(battle, Some(EntityRef::Unit(unit)), Tag::Attack, |battle| {
        strike_effect(battle, unit, target);
    });
}

fn strike_effect(battle: &mut Battle, unit: UnitRef, target: EntityRef) {
    let t = battle.t;
    let sp = Arc::clone(&battle.unit(unit).spec);
    if sp.attack == Tag::None && !(battle.unit(unit).name_id == Name::RuinWitch && unit.team == Team::Def)
    {
        return;
    }
    let (mut rage, _) = rage_boost(battle.unit(unit), t);
    let u = battle.unit(unit);
    rage = rage.max(u.aura_dmg).max(u.extra.bell_damage);
    let mut multiplier = 1.0;
    if sp.has_special(Special::RoyalRampage) && unit.team == Team::Atk && duke_alone(battle, unit) {
        multiplier *= 2.0;
    }
    if tantrum(battle, unit) {
        rage = rage.max(2.0);
    }
    let mut damage = battle.unit(unit).dmg * multiplier;
    if sp.has_special(Special::Burst) && battle.unit(unit).extra.burst_target != Some(target) {
        todo!("stage 2: units.py:1849 Super Dragon burst target switch");
    }
    if sp.attack == Tag::Beam {
        todo!("stage 2: units.py:1852 Inferno Dragon and Super Miner beam damage");
    }
    let ordinary = damage;
    damage *= rage;
    let rocket = battle.unit(unit).kit.as_ref()
        .is_some_and(|kit| kit.has("Rocket Spear") && kit.spear_shots > 0);
    if battle.unit(unit).kit.is_some() {
        let u = battle.unit(unit);
        if t < u.extra.vial_until {
            let vial = u.extra.vial_bonus * battle.atk_hero_mult;
            damage = damage.max(ordinary + vial);
        }
        damage = damage.max(ordinary + heroes::strike_bonus(battle, unit));
    }
    let speed = projectile_speed(battle.unit(unit));
    if rocket {
        launch_projectile(battle, unit, target, damage, 12.0, true);
        return;
    }
    if sp.has_special(Special::LongShot) && battle.unit(unit).extra.long_shots > 0 {
        battle.unit_mut(unit).extra.long_shots -= 1;
    }
    if let Some(speed) = speed {
        launch_projectile(battle, unit, target, damage, speed, false);
        return;
    }
    if SPATIAL_TROOPS.contains(&battle.unit(unit).name_id)
        || matches!(sp.attack, Tag::Suicide | Tag::Spin | Tag::Chain | Tag::Bounce | Tag::Pierce
        )
    {
        spatial_strike(battle, unit, target, damage);
        if battle.unit(unit).name_id == Name::Valkyrie && !battle.entity_alive(target) {
            let u = battle.unit_mut(unit);
            u.target = None;
            u.wall_target = None;
        }
        if battle.unit(unit).name_id == Name::MeteorGolem {
            split_meteor(battle, unit, target);
        }
        if battle.unit(unit).name_id == Name::Electromite {
            battle.kill(unit);
        }
        return;
    }
    damage *= mult_vs(battle, unit, target);
    if battle.unit(unit).kit.is_some() {
        damage += heroes::monolith_bonus(battle, unit, target);
        if t < battle.unit(unit).extra.gauntlet_until {
            todo!("stage 3+: Giant Gauntlet strike");
        }
    }
    if let EntityRef::Unit(victim) = target {
        battle.hit_unit(victim, damage, None, "normal", Some(EntityRef::Unit(unit)));
        after_unit_hit(battle, unit, victim, damage);
        chill(battle, unit, target);
        if battle.unit(unit).kit.is_some() {
            heroes::on_hit_extra(battle, unit, target);
        }
        if matches!(battle.unit(unit).name_id, Name::Miner | Name::SuperMiner)
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
    if sp.attack == Tag::Splash {
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
    if battle.unit(unit).kit.is_some() {
        heroes::on_hit_extra(battle, unit, target);
    }
}

// units.py:1947-2000: secondary provenance does not replace the attacker's src.
pub fn after_unit_hit(battle: &mut Battle, unit: UnitRef, target: UnitRef, damage: f64) {
    effects::damage_source(battle, Some(EntityRef::Unit(unit)), Tag::Secondary, |battle| {
        after_unit_hit_effect(battle, unit, target, damage);
    });
}

fn after_unit_hit_effect(battle: &mut Battle, unit: UnitRef, target: UnitRef, damage: f64) {
    let t = battle.t;
    let sp = Arc::clone(&battle.unit(unit).spec);
    if sp.has_special(Special::Logger) {
        todo!("stage 2: units.py:1951 Logger collateral and pushback");
    }
    let victim = battle.unit(target);
    if sp.has_special(Special::HhPoison) && !(victim.kind == Tag::Guardian && victim.extra.waiting) {
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
    if !SPATIAL_TROOPS.contains(&battle.unit(unit).name_id)
        && matches!(sp.attack, Tag::Splash | Tag::Spin)
        && sp.splash > 0.0
        && !sp.has_special(Special::Logger)
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
                && (battle.unit(unit).name_id != Name::Longshot
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
    if battle.unit(unit).spec.has_special(Special::Burst) {
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
    if battle.unit(unit).spec.attack != Tag::Beam {
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

// units.py:2063-2092: primary and secondary healing have different eligibility.
const HEAL_STACK: [f64; 8] = [1.0, 1.0, 0.9, 0.9, 0.7, 0.4, 0.1, 0.0];

fn heal_eligible(battle: &Battle, healer: UnitRef, ally: UnitRef, primary: bool) -> bool {
    let u = battle.unit(healer);
    let a = battle.unit(ally);
    if ally == healer
        || !a.alive
        || ally.team != healer.team
        || battle.t < a.active_at
        || a.extra.suspended
        || matches!(a.name_id, Name::Totem | Name::Furnace)
        || matches!(a.kind, Tag::Siege | Tag::SiegeIdle)
    {
        return false;
    }
    if a.flying && !u.spec.heal_air {
        return false;
    }
    let healing = matches!(a.spec.attack, Tag::Heal | Tag::HealChain);
    if primary && (a.name_id == Name::Unicorn || healing) {
        return false;
    }
    if u.name_id == Name::Healer && healing {
        return false;
    }
    if u.name_id == Name::Druid && !primary && a.name_id == Name::Druid {
        return false;
    }
    if healer.team == Team::Def
        && !(matches!(a.kind, Tag::Cc | Tag::Hero | Tag::Summon | Tag::TrapSkeleton | Tag::Guardian
        ) || a.name_id == Name::Skeleton)
    {
        return false;
    }
    true
}

// units.py:2095-2114: registration precedes the pulse-clock check.
pub fn heal_effectiveness(battle: &mut Battle, healer: UnitRef, recipient: UnitRef) -> f64 {
    let mut sources = std::mem::take(&mut battle.healing_source_scratch);
    sources.clear();
    for &(source, since) in &battle.unit(recipient).extra.healing_sources {
        let s = battle.unit(source);
        if !s.alive || !s.can_act(battle.t) || s.extra.suspended {
            continue;
        }
        if s.name_id != Name::Unicorn {
            if let Some(EntityRef::Unit(target)) = s.target {
                let target = battle.unit(target);
                if geom::dist(s.x, s.y, target.x, target.y) > s.range {
                    continue;
                }
            }
        }
        if !s.extra.healing_targets.contains(&recipient) {
            continue;
        }
        sources.push((source, since));
    }
    if !sources.iter().any(|(source, _)| *source == healer) {
        sources.push((healer, battle.t));
    }
    battle.unit_mut(recipient).extra.healing_sources.clone_from(&sources);
    sources.sort_by(|(a, at), (b, bt)| {
        at.partial_cmp(bt)
            .expect("healing timestamp")
            .then(a.id.0.cmp(&b.id.0))
    });
    let index = sources
        .iter()
        .position(|(source, _)| *source == healer)
        .expect("registered healer");
    let result = HEAL_STACK[index.min(HEAL_STACK.len() - 1)];
    sources.clear();
    battle.healing_source_scratch = sources;
    result
}

// units.py:2117-2236: recipients and projectile appends retain ally-list order.
pub fn act_healer(battle: &mut Battle, unit: UnitRef) {
    let mut scratch = std::mem::take(&mut battle.healer_scratch);
    act_healer_with_scratch(battle, unit, &mut scratch);
    battle.healer_scratch = scratch;
}

fn act_healer_with_scratch(
    battle: &mut Battle,
    unit: UnitRef,
    scratch: &mut crate::state::HealerScratch,
) {
    let crate::state::HealerScratch {
        allies,
        eligible,
        weighted,
        recipients,
        effectiveness,
    } = scratch;
    allies.clear();
    eligible.clear();
    weighted.clear();
    recipients.clear();
    effectiveness.clear();
    let t = battle.t;
    battle.unit_mut(unit).extra.healing_targets.clear();
    if unit.team == Team::Def
        && battle
            .poison
            .iter()
            .any(|state| state.unit == unit && t < state.until)
    {
        return;
    }
    let sp = Arc::clone(&battle.unit(unit).spec);
    if unit.team == Team::Atk {
        allies.extend(battle.attackers_pool().map(Unit::reference));
    } else {
        allies.extend(battle.defenders_pool().map(Unit::reference));
    }
    eligible.extend(
        allies
            .iter()
            .copied()
            .filter(|ally| heal_eligible(battle, unit, *ally, true)),
    );
    if battle.unit(unit).name_id == Name::Healer {
        weighted.extend(
            allies
                .iter()
                .copied()
                .filter(|ally| heal_eligible(battle, unit, *ally, false))
                .map(|ally| {
                    let a = battle.unit(ally);
                    (a.x, a.y, if a.is_hero { 25 } else { a.housing })
                }),
        );
        eligible.retain(|target| {
            let target = battle.unit(*target);
            weighted
                .iter()
                .filter(|(x, y, _)| geom::dist(target.x, target.y, *x, *y) <= sp.splash)
                .map(|(_, _, weight)| *weight)
                .sum::<i64>()
                > 2
        });
    }
    let u = battle.unit(unit);
    let mut target = match u.target {
        Some(EntityRef::Unit(target)) if eligible.contains(&target) => Some(target),
        _ => None,
    };
    if u.follow.is_some_and(|follow| eligible.contains(&follow)) {
        target = u.follow;
    }
    if target.is_none() {
        let mut nearest = f64::INFINITY;
        for &ally in eligible.iter() {
            let a = battle.unit(ally);
            if unit.team == Team::Def && a.hp >= a.max_hp {
                continue;
            }
            let distance = geom::dist(u.x, u.y, a.x, a.y);
            if target.is_none() || distance < nearest {
                nearest = distance;
                target = Some(ally);
            }
        }
    }
    let u = battle.unit_mut(unit);
    u.target = target.map(EntityRef::Unit);
    u.target_kind = Some(Tag::Unit);
    let Some(target) = target else {
        return;
    };
    let u = battle.unit(unit);
    let a = battle.unit(target);
    if geom::dist(u.x, u.y, a.x, a.y) > u.range {
        battle.move_towards(unit, EntityRef::Unit(target), None);
        return;
    }
    if sp.attack == Tag::Heal {
        recipients.extend(
            allies.iter().copied().filter(|ally| {
                let ally_unit = battle.unit(*ally);
                heal_eligible(battle, unit, *ally, false)
                    && geom::dist(a.x, a.y, ally_unit.x, ally_unit.y) <= sp.splash
            }),
        );
    } else {
        recipients.push(target);
        let mut current = target;
        for _ in 0..sp.chain {
            let mut chosen = None;
            let mut nearest = f64::INFINITY;
            for &ally in allies.iter() {
                let a = battle.unit(ally);
                let previous = battle.unit(current);
                if recipients.contains(&ally)
                    || !heal_eligible(battle, unit, ally, false)
                    || a.hp >= a.max_hp
                {
                    continue;
                }
                let distance = geom::dist(previous.x, previous.y, a.x, a.y);
                if distance <= 3.0 && (chosen.is_none() || distance < nearest) {
                    nearest = distance;
                    chosen = Some(ally);
                }
            }
            let Some(chosen) = chosen else {
                break;
            };
            current = chosen;
            recipients.push(current);
        }
    }
    battle
        .unit_mut(unit)
        .extra
        .healing_targets
        .clone_from(recipients);
    // Registration has side effects and must still precede the pulse check.
    effectiveness.extend(
        recipients
            .iter()
            .map(|ally| heal_effectiveness(battle, unit, *ally)),
    );
    let due = battle.unit(unit).extra.heal_next.unwrap_or(t);
    if t < due && !isclose(t, due) {
        return;
    }
    let u = battle.unit_mut(unit);
    u.extra.heal_next = Some(t + u.interval);
    let u = battle.unit(unit);
    let level = u.level.as_ref().expect("healer level");
    let (rate_key, hero_key) = if u.name_id == Name::Healer {
        ("Healing per Pulse", "HPP on Heroes")
    } else {
        ("Healing per Hit", "Hero Healing")
    };
    let rate = battle
        .catalog
        .stats
        .get(&u.name, level, &[rate_key], None)
        .expect("healing rate");
    let hero_rate = battle
        .catalog
        .stats
        .get(&u.name, level, &[hero_key], None)
        .expect("hero healing rate");
    let (rage, _) = rage_boost(u, t);
    let boost = rage.max(u.aura_dmg);
    let druid = u.name_id == Name::Druid;
    let source = u.source.clone();
    let target_unit = battle.unit(target);
    let mut flight = geom::dist(u.x, u.y, target_unit.x, target_unit.y) / 12.0;
    let mut previous = target;
    for (index, ally) in recipients.iter().copied().enumerate() {
        let a = battle.unit(ally);
        if druid && index != 0 {
            let previous = battle.unit(previous);
            flight += geom::dist(previous.x, previous.y, a.x, a.y) / 12.0;
        }
        previous = ally;
        let amount = (if a.is_hero { hero_rate } else { rate }) * boost * effectiveness[index];
        let mut pending = Pending::new(t + flight, a.x, a.y, 0.0, 0.0, false, false, source.clone());
        pending.team = unit.team;
        pending.extra.healing = Some(amount);
        pending.actor = Some(EntityRef::Unit(unit));
        pending.effect = Some(Tag::Heal);
        pending.target = Some(EntityRef::Unit(ally));
        battle.add_pending(pending);
    }
}

// battle.py:858-869: the first live matching siege is manually released.
pub fn release_siege(battle: &mut Battle, name: Option<&str>) -> bool {
    let unit = battle.attackers_pool().find(|u| {
        u.alive && u.kind == Tag::Siege && name.is_none_or(|name| u.name == name)
    }).map(Unit::reference);
    if let Some(unit) = unit {
        battle.kill(unit);
        true
    } else {
        false
    }
}
