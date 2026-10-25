//! Ports units.py troop behavior through the ranked stage-6 armies.
//! TH18 defending Guardians retain explicit unsupported branches.

use std::sync::Arc;

use std::collections::HashSet;

use crate::battle::SpawnOptions;
use crate::catalog::{game_float, game_int, game_required_int};
use crate::combat::{SplashBuildingsOptions, SplashUnitsOptions};
use crate::effects;
use crate::fast_hash::FastMap as HashMap;
use crate::geom;
use crate::grid::{TargetIdentity, RES};
use crate::heroes;
use crate::labels::{Name, Special, Tag};
use crate::spells;
use crate::state::{
    Battle, CargoEntry, EntityRef, Field, Pending, RollingLog, SpinPosition, StatusSource, Team,
    Unit, UnitRef, WallId,
};
use crate::stats::Level;

pub const RESOURCE_KEYS: &[&str] = &["gm", "ec", "dd", "gs", "es", "ds", "th", "cc"];

fn unit_stat(battle: &Battle, unit: UnitRef, keys: &[&str], default: Option<f64>) -> f64 {
    let u = battle.unit(unit);
    battle
        .catalog
        .stats
        .get(
            &u.name,
            u.level.as_ref().expect("unit level"),
            keys,
            default,
        )
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
    Name::WallWrecker,
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
    // units.py:94-109: Jump only opens its covered walls; retain other bypasses.
    let u = battle.unit(unit);
    let jumped = battle.t < u.extra.jump_until;
    if battle.wall_mode(unit) == Tag::Ignore && !jumped {
        return None;
    }
    if jumped {
        let (i, j) = battle.grid.cell(u.x, u.y);
        if u.team == Team::Def
            || u.spec.walls == Tag::Ignore
            || battle.t < u.extra.horse_until
            || effects::torch_stats(u, battle.t).1 != 0.0
            || !u.extra.torches.is_empty() && !u.flying && battle.grid.wall[battle.grid.index(i, j)]
        {
            return None;
        }
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
    for building in &buildings {
        // units.py:125-146: partial enclosure still protects the building.
        let route = grid.field(
            TargetIdentity::Breaker(building.0 .0),
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
            }
        }
    }
    None
}

// units.py:166-221: equal scores use buildings before walls, then entity ID.
pub fn follow_target(battle: &mut Battle, unit: UnitRef) -> Option<EntityRef> {
    if battle.params.warden_spatial {
        return battle.spatial_follow_target(unit).0;
    }
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
        (
            battle.params.apprentice_radius,
            battle.params.apprentice_min_weight,
        )
    } else {
        (battle.params.warden_radius, battle.params.warden_min_weight)
    };
    let mut total_weight = 0.0;
    for ally in battle.attackers_near_iter(u.x, u.y, radius) {
        let a = battle.unit(ally);
        // units.py:183-184: Yetimites contribute their catalog Warden weight.
        if ally == unit || !a.alive || a.name_id == Name::Totem {
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
        if matches!(target, EntityRef::Building(id) if !battle.building_targetable(id)) {
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
    let target_key = |target: EntityRef| match target {
        EntityRef::Building(id) => (false, battle.building(id).id.0 as i64, 0),
        // Python wall IDs are ("wall", tx, ty), not storage indices.
        EntityRef::Wall(id) => {
            let wall = &battle.walls[id.0];
            (true, i64::from(wall.tx), i64::from(wall.ty))
        }
        _ => unreachable!("Warden follows buildings or walls"),
    };
    scores
        .iter()
        .min_by(|(a, a_score), (b, b_score)| {
            b_score
                .total_cmp(a_score)
                .then_with(|| target_key(*a).cmp(&target_key(*b)))
        })
        .map(|(target, _)| *target)
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
    // units.py:263-265: preserve birth order across same-tick spawns and Recall.
    battle.unit_mut(unit).extra.spawn_sequence = Some(unit.id.0);
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
        // units.py:260-267: attackers start underground; defenders keep ground speed.
        let u = battle.unit_mut(unit);
        u.underground = unit.team == Team::Atk;
        if name == "Miner" && unit.team == Team::Def {
            u.speed = 2.5;
        }
        if name == "Super Miner" && unit.team == Team::Def {
            u.speed = 4.0 * 0.7;
        }
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
        // units.py:274-279: initialize the parent of defensive Firemites.
        let count = unit_stat(battle, unit, &["Firemites Spawned"], Some(22.0)) as i64;
        let u = battle.unit_mut(unit);
        u.extra.mites = count;
        u.extra.next_mite = t + 1.0;
        u.decay = u.max_hp / 60.0;
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
        battle.unit_mut(unit).extra.next_log = t + 1.0;
    }
    if sp.has_special(Special::Logs) || sp.has_special(Special::Flinger) {
        // units.py:303-307: first discrete HP loss follows the CSV interval.
        let u = battle.unit(unit);
        let row = battle.catalog.game_unit_data(&u.name, u.level.as_ref());
        let interval = game_required_int(row, "LoseHpInterval") as f64 / 1000.0;
        battle.unit_mut(unit).extra.hp_loss_at = Some(t + interval);
    }
    if name == "Druid" {
        battle.unit_mut(unit).extra.bear_at = t + 30.0;
    }
    if sp.has_special(Special::WitchSkeletons) {
        // units.py:291-293: each Witch owns a separate living-skeleton cap.
        let u = battle.unit_mut(unit);
        u.extra.next_summon = t + 3.0;
        u.extra.skeletons.clear();
    }
    if sp.has_special(Special::BigBoy) {
        // units.py:294-295: Big Boy starts one second after Witch skeletons.
        battle.unit_mut(unit).extra.next_summon = t + 4.0;
    }
    if sp.has_special(Special::RuinWitch) {
        battle.unit_mut(unit).extra.knights = 0;
    }
    if sp.has_special(Special::LongShot) {
        battle.unit_mut(unit).extra.long_shots = if unit.team == Team::Atk { 8 } else { 3 };
    }
    if sp.has_special(Special::Burst) {
        // units.py:302-306: use the wiki's shot count without DPS rescaling.
        let shots = burst_shots(battle, unit);
        battle.unit_mut(unit).extra.burst_left = shots;
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
        u.extra.hp_loss_at = Some(t + 1.0);
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
        || u.extra.hp_loss_at.is_some()
        || u.kind == Tag::Pet
        || u.kit.is_some()
        || u.name_id == Name::GiantGiant && !u.extra.enraged;
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
                > effective_range(battle, battle.unit(unit))
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
    if battle.unit(unit).name_id == Name::Totem {
        let u = battle.unit_mut(unit);
        u.extra.hp_loss_at.get_or_insert(u.spawned_at + 0.5);
    }
    // units.py:pre_tick: discrete losses include every skipped interval.
    if let Some(mut at) = battle.unit(unit).extra.hp_loss_at {
        let u = battle.unit(unit);
        let row = battle.catalog.game_unit_data(&u.name, u.level.as_ref());
        let loss = game_required_int(row, "LoseHpPerTick") as f64;
        let interval = game_required_int(row, "LoseHpInterval") as f64 / 1000.0;
        while t >= at || isclose(t, at) {
            let u = battle.unit_mut(unit);
            u.hp -= loss;
            at += interval;
            u.extra.hp_loss_at = Some(at);
            if u.hp <= 0.0 {
                battle.kill(unit);
                return true;
            }
        }
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
        // Half-hit 0.5 plus the 0.75-tile aura bounds wall candidates. The extra
        // tile margin covers negative coordinates; retain the exact test below.
        if battle.wall_tiles_standard {
            let tile_x = x.floor() as i32;
            let tile_y = y.floor() as i32;
            for tx in tile_x.saturating_sub(2)..=tile_x.saturating_add(2) {
                for ty in tile_y.saturating_sub(2)..=tile_y.saturating_add(2) {
                    if let Some(&id) = battle.wall_indices.get(&(tx, ty)) {
                        let wall = &battle.walls[id.0];
                        if wall.alive && wall.edge_distance(x, y) <= 0.75 {
                            contacts.push(id);
                        }
                    }
                }
            }
        } else {
            contacts.extend(
                battle
                    .walls
                    .iter()
                    .filter(|wall| wall.alive && wall.edge_distance(x, y) <= 0.75)
                    .map(|wall| wall.id),
            );
        }
        contacts.sort_unstable_by_key(|id| id.0);
        for &id in &contacts {
            smash_wall(battle, unit, id);
        }
        battle.unit_mut(unit).extra.wall_pulses.retain(|(id, _)| {
            contacts
                .binary_search_by_key(&id.0, |contact| contact.0)
                .is_ok()
        });
        contacts.clear();
        battle.wall_contact_scratch = contacts;
    }
    if battle.unit(unit).decay > 0.0 && battle.unit(unit).name_id != Name::Totem {
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
            if t >= pet.extra.pushed_until {
                heroes::act_pet(battle, unit);
            }
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
    if u.name_id == Name::Totem {
        return true;
    }
    if u.name_id == Name::GiantGiant && !u.extra.enraged {
        let row = battle.catalog.game_unit_data(&u.name, u.level.as_ref());
        let level = Level::Int(game_required_int(row, "SpecialAbilitiesLevel"));
        let ability = battle.catalog.game_data(
            "special_abilities",
            row.at("SpecialAbilities").str(),
            Some(&level),
        );
        if u.extra.rage_damage_taken >= game_required_int(ability, "ActiveAfterTakingDamage") as f64
        {
            let u = battle.unit_mut(unit);
            u.extra.enraged = true;
            u.rage_dmg = 1.5;
            u.rage_spd = 12.0 / 8.0;
            u.rage_until = t + 20.0;
        }
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
                    let amount = if f.is_hero { damage * 0.25 } else { damage };
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
            // units.py:426-435: a stale rubble claim must never deliver a Knight.
            let claim = &battle.building(rubble).extra;
            if !battle.unit(unit).extra.delivery_committed
                && (claim.rubble_taken || claim.rubble_claim != Some(unit.id))
            {
                battle.unit_mut(unit).extra.vacuum = None;
                return true;
            }
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
            // units.py:467-476: a living Witch's claim excludes other Witches.
                && (rubble.extra.rubble_claim.is_none()
                || rubble.extra.rubble_claim == Some(u.id)
                || !battle.attackers_pool().any(|witch| witch.alive && Some(witch.id) == rubble.extra.rubble_claim))
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
        // units.py:481-502: prune in list order, then append this summon's children.
        let mut alive: Vec<_> = u
            .extra
            .skeletons
            .iter()
            .copied()
            .filter(|skeleton| battle.unit(*skeleton).alive)
            .collect();
        let cap = unit_stat(battle, unit, &["Maximum Skeletons Summoned"], Some(16.0)) as i64;
        let count = unit_stat(battle, unit, &["Skeletons per Summon"], Some(5.0)) as i64;
        let n = count.min(cap - alive.len() as i64);
        for k in 0..n.max(0) {
            let level = unit_stat(battle, unit, &["Skeleton Level"], None) as i64;
            let u = battle.unit(unit);
            let skeleton = battle.spawn(
                "Skeleton",
                unit.team,
                u.x + 0.6 * geom::py_cos(k as f64),
                u.y + 0.6 * geom::py_sin(k as f64),
                SpawnOptions {
                    level: Some(Level::Int(level)),
                    kind: Tag::Summon,
                    group: u.group.clone(),
                    owner: Some(unit),
                    ..Default::default()
                },
            );
            alive.push(skeleton);
        }
        let u = battle.unit_mut(unit);
        u.extra.skeletons = alive;
        u.extra.next_summon = t + 7.0;
        if n > 0 {
            return true;
        }
    }
    let u = battle.unit(unit);
    if special.contains(Special::BigBoy) && t >= u.extra.next_summon {
        // units.py:503-510: a live Big Boy prevents replacement after the cooldown.
        if u.extra.bb.is_none_or(|boy| !battle.unit(boy).alive) {
            let child = battle.spawn(
                "Big Boy",
                unit.team,
                u.x + 0.5,
                u.y,
                SpawnOptions {
                    level: Some(Level::Int(1)),
                    kind: Tag::Summon,
                    group: u.group.clone(),
                    owner: Some(unit),
                    ..Default::default()
                },
            );
            let u = battle.unit(unit);
            let row = battle.catalog.game_unit_data(&u.name, u.level.as_ref());
            let cooldown = game_int(row, "SummonCooldown", 0) as f64 / 1000.0;
            let u = battle.unit_mut(unit);
            u.extra.bb = Some(child);
            u.extra.next_summon = t + cooldown;
        }
    }
    if special.contains(Special::Furnace)
        && unit.team == Team::Def
        && !battle
            .attackers_pool()
            .any(|attacker| attacker.targetable(battle) && attacker.name_id != Name::Totem)
    {
        let dt = battle.dt;
        battle.unit_mut(unit).extra.next_mite += dt;
    }
    let u = battle.unit(unit);
    if special.contains(Special::Furnace) && t >= u.extra.next_mite && u.extra.mites > 0 {
        battle.unit_mut(unit).extra.mites -= 1;
        let u = battle.unit(unit);
        battle.spawn(
            "Firemite",
            unit.team,
            u.x + 0.5,
            u.y + 0.5,
            SpawnOptions {
                level: u.level.clone(),
                kind: Tag::Summon,
                group: u.group.clone(),
                owner: Some(unit),
                ..Default::default()
            },
        );
        battle.unit_mut(unit).extra.next_mite = t + 60.0 / 22.0;
    }
    let u = battle.unit(unit);
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
        // units.py:553-557: bombs hit ground units, buildings and walls before moving.
        let damage = unit_stat(battle, unit, &["Damage per Attack"], Some(450.0));
        let u = battle.unit(unit);
        let (x, y) = (u.x, u.y);
        area_hit(battle, unit, x, y, 3.0, damage, true, None);
        battle.unit_mut(unit).extra.next_bomb = t + 1.5;
    }
    false
}

// units.py:561-593: burrow transitions and Battle Drill emergence.
pub fn update_burrow(battle: &mut Battle, unit: UnitRef, target: Option<EntityRef>) {
    if !battle.unit(unit).spec.has_special(Special::Burrow) {
        return;
    }
    if unit.team == Team::Def {
        battle.unit_mut(unit).underground = false;
        return;
    }
    let u = battle.unit(unit);
    let was_underground = u.underground;
    let retreating = target.is_none_or(|target| {
        target_distance(battle, EntityRef::Unit(unit), target) > effective_range(battle, u)
    });
    let t = battle.t;
    if u.name_id == Name::Miner && retreating && !was_underground {
        let u = battle.unit_mut(unit);
        let hide_at = *u.extra.hide_at.get_or_insert(t + 1.0);
        u.held_until = u.held_until.max(hide_at);
        u.underground = t >= hide_at;
    } else {
        let u = battle.unit_mut(unit);
        u.underground = retreating;
        let hide_at = u.extra.hide_at.take();
        if !retreating && hide_at.is_some_and(|hide_at| u.held_until == hide_at) {
            u.held_until = t;
        }
    }
    let u = battle.unit(unit);
    if u.name_id == Name::BattleDrill && was_underground && !u.underground {
        let (x, y) = (u.x, u.y);
        for index in 0..battle.walls.len() {
            let wall = &battle.walls[index];
            if wall.alive && isclose(wall.edge_distance(x, y), 0.0) {
                battle.hit_building(EntityRef::Wall(wall.id), wall.hp, None, "normal");
            }
        }
        // units.py:585-594: surfacing stuns nearby defense targets for 2 s.
        for index in 0..battle.buildings.len() {
            let building = &battle.buildings[index];
            if building.alive
                && battle.is_defense_target(building.id)
                && building.edge_distance(x, y) <= 1.5
            {
                let building = &mut battle.buildings[index];
                building.stun_until = building.stun_until.max(t + 2.0);
            }
        }
    }
}

// units.py:572-577: transformation does not run the Druid's death callbacks.
fn transform_bear(battle: &mut Battle, unit: UnitRef) {
    battle.unit_mut(unit).alive = false;
    let u = battle.unit(unit);
    let strength = if unit.team == Team::Atk {
        u.extra.strength
    } else {
        1.0
    };
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
    let bear = battle.unit_mut(bear);
    // units.py:583-594: a fresh Bear inherits its attacking Druid's strength.
    if strength != 1.0 {
        bear.hp *= strength;
        bear.max_hp *= strength;
        bear.base_max_hp *= strength;
        bear.dmg *= strength;
        bear.extra.strength = strength;
    }
    bear.extra.from_druid = true;
}

// units.py:580-585: RollingLog.Speed, StartOffset, and maximum travel in tiles.
const LOG_SPEED: f64 = 4.2;
const LOG_START: f64 = 1.0;
const LOG_RANGE: f64 = 20.0;

// units.py:588-614: point-blank blast, then launch a travelling log.
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
    // units.py:608-623: strength scales ordinary, wall and point-blank damage.
    let strength = u.extra.strength;
    let base = battle
        .catalog
        .stats
        .get(&u.name, level, &["Damage per Hit"], Some(690.0))
        .expect("log damage");
    let damage = base * strength;
    let wall_damage = battle
        .catalog
        .stats
        .get(
            &u.name,
            level,
            &["Damage per Hit vs. Walls"],
            Some(base * 4.0),
        )
        .expect("log wall damage")
        * strength;
    let point_blank = battle
        .catalog
        .stats
        .get(
            &u.name,
            level,
            &["Point-Blank Damage*", "Point-Blank Damage"],
            Some(0.0),
        )
        .expect("point blank default")
        * strength;
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
    let u = battle.unit(unit);
    let mut log = Field::new("rolling_log", u.x, u.y, 0.0, f64::INFINITY);
    log.team = unit.team;
    log.started = battle.t;
    log.extra.rolling_log = Some(RollingLog {
        launcher: unit,
        dx,
        dy,
        damage,
        wall_damage,
        launched: battle.t,
        next: (LOG_START * 2.0) as usize,
        hit_buildings: HashSet::new(),
        hit_walls: HashSet::new(),
        hit_units: HashSet::new(),
    });
    if advance_log(battle, &mut log) {
        battle.fields.push(log);
    }
}

// units.py:617-650: walls, buildings, then defenders at each half-tile sample.
pub fn advance_log(battle: &mut Battle, field: &mut Field) -> bool {
    let (x, y) = (field.x, field.y);
    let log = field.extra.rolling_log.as_mut().expect("rolling log state");
    let reach = LOG_RANGE.min(LOG_START + LOG_SPEED * (battle.t - log.launched));
    effects::damage_source(
        battle,
        Some(EntityRef::Unit(log.launcher)),
        Tag::Attack,
        |battle| {
            while log.next as f64 * 0.5 <= reach {
                let step = log.next;
                log.next += 1;
                // Match Python's left-to-right multiplication before adding the origin.
                let (px, py) = (
                    x + log.dx * step as f64 * 0.5,
                    y + log.dy * step as f64 * 0.5,
                );
                for key in [
                    (px as i32, py as i32),
                    ((px + 0.5) as i32, py as i32),
                    (px as i32, (py + 0.5) as i32),
                ] {
                    if let Some(&wall) = battle.wall_indices.get(&key) {
                        if battle.walls[wall.0].alive && log.hit_walls.insert(key) {
                            battle.hit_building(
                                EntityRef::Wall(wall),
                                log.wall_damage,
                                None,
                                "normal",
                            );
                        }
                    }
                }
                for index in 0..battle.buildings.len() {
                    let b = &battle.buildings[index];
                    if b.alive
                        && b.counted
                        && !log.hit_buildings.contains(&b.id)
                        && b.edge_distance(px, py) < 0.8
                    {
                        let id = b.id;
                        log.hit_buildings.insert(id);
                        battle.hit_building(EntityRef::Building(id), log.damage, None, "normal");
                        if log.hit_buildings.len() >= 4 {
                            return false;
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
                        && !log.hit_units.contains(&foe.reference())
                        && geom::dist(px, py, foe.x, foe.y) < 0.8
                    {
                        let victim = foe.reference();
                        log.hit_units.insert(victim);
                        battle.hit_unit(
                            victim,
                            log.damage,
                            None,
                            "normal",
                            Some(EntityRef::Unit(log.launcher)),
                        );
                    }
                    index += 1;
                }
            }
            log.next as f64 * 0.5 <= LOG_RANGE
        },
    )
}

// units.py:626-666: damage is accumulated before testing the child thresholds.
pub fn on_damaged(battle: &mut Battle, unit: UnitRef, amount: f64) {
    if battle.unit(unit).name_id == Name::GiantGiant {
        battle.unit_mut(unit).extra.rage_damage_taken += amount;
    }
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
                pending.extra.buildings = if unit.team == Team::Atk { damage } else { 0.0 };
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
            // units.py:804-815: offense uses the Hound freeze; defense uses
            // the defensive Ice Golem spell and its separate level mapping.
            if unit.team == Team::Atk {
                radius = 6.5;
            } else {
                radius = 5.5;
                let Level::Int(level) = level else {
                    panic!("Ice Hound level must be numeric")
                };
                seconds = if *level <= 5 { 2.0 } else { 2.25 };
            }
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
        // units.py:806-844: preserve per-child RNG draws and spawn order.
        let name = sp.death_spawn[0].str();
        let count = &sp.death_spawn[1];
        let mut n = if let crate::json::Json::Num(value) = count {
            *value as i64
        } else {
            unit_stat(battle, unit, &[count.str()], Some(0.0)) as i64
        };
        if unit.team == Team::Def {
            if let crate::json::Json::Str(key) = count {
                let key = key.replace("On Offense", "On Defense");
                n = unit_stat(battle, unit, &[&key], Some(n as f64)) as i64;
            }
        }
        let max_level = battle
            .catalog
            .stats
            .max_level(name, 18)
            .filter(|level| *level != 0);
        let sub_level = if name == "Golemite" {
            battle.unit(unit).level.clone().expect("Golem level")
        } else {
            Level::Int(max_level.unwrap_or(1))
        };
        let mut spawn_distance = 0.7;
        let mut spawn_offset = 0.0;
        let mut randomize_distance = false;
        let u = battle.unit(unit);
        if matches!(u.name.as_str(), "Lava Hound" | "Ice Hound") {
            let row_name = if unit.team == Team::Def {
                format!("Defensive {}", u.name)
            } else {
                u.name.clone()
            };
            let row = battle
                .catalog
                .game_data("characters", &row_name, u.level.as_ref());
            spawn_distance = game_int(row, "SecondarySpawnDist", 0) as f64 / 100.0;
            spawn_offset = game_int(row, "SecondarySpawnOffset", 0) as f64 / 100.0;
            randomize_distance = row
                .get("RandomizeSecSpawnDist")
                .is_some_and(|value| value.str() == "TRUE");
        }
        let level = match sub_level {
            Level::Int(level) => Level::Int(level.min(max_level.unwrap_or(level))),
            _ => panic!("integer death-spawn level"),
        };
        for k in 0..n {
            let angle = 2.0 * std::f64::consts::PI * k as f64 / n.max(1) as f64;
            let mut radius = spawn_distance;
            if randomize_distance {
                radius *= battle.rng_mut().random();
            }
            radius += spawn_offset;
            let u = battle.unit(unit);
            battle.spawn(
                name,
                unit.team,
                u.x + radius * geom::py_cos(angle),
                u.y + radius * geom::py_sin(angle),
                SpawnOptions {
                    level: Some(level.clone()),
                    kind: Tag::Summon,
                    group: u.group.clone(),
                    owner: Some(unit),
                    ..Default::default()
                },
            );
        }
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
        // units.py:832-843: inherit ability/spell rows at the dying troop's level.
        let ability = battle.catalog.game_data(
            "special_abilities",
            "ElectroDragonOnDeath",
            u.level.as_ref(),
        );
        let spell_level = Level::Int(game_int(ability, "SelfSpellLevel", 1));
        let spell =
            battle
                .catalog
                .game_data("spells", ability.at("SelfSpell").str(), Some(&spell_level));
        let count = game_int(spell, "NumberOfHits", 0);
        let gap = game_int(spell, "TimeBetweenHitsMS", 0) as f64 / 1000.0;
        for index in 0..count {
            let angle = battle.rng_mut().random() * 2.0 * std::f64::consts::PI;
            let offset = battle.rng_mut().random() * 2.5;
            let u = battle.unit(unit);
            let (x, y) = (
                u.x + offset * geom::py_cos(angle),
                u.y + offset * geom::py_sin(angle),
            );
            // units.py:848-862: the first bolt is due now; append order is radial order.
            let mut pending = Pending::new(
                t + index as f64 * gap,
                x,
                y,
                2.0,
                damage,
                false,
                true,
                &u.name,
            );
            pending.team = if unit.team == Team::Atk {
                Team::Def
            } else {
                Team::Atk
            };
            pending.extra.buildings = if unit.team == Team::Atk { damage } else { 0.0 };
            pending.actor = Some(EntityRef::Unit(unit));
            pending.effect = Some(Tag::Death);
            battle.add_pending(pending);
        }
    }
    if sp.has_special(Special::Smasher) && unit.team == Team::Def {
        crate::heroes::guardian_death(battle, unit);
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
    let strength = battle.plan.strength();
    let child = battle.unit_mut(child);
    // units.py:1033-1042: cargo receives the same strength as camp troops.
    if strength != 1.0 {
        child.hp *= strength;
        child.max_hp *= strength;
        child.base_max_hp *= strength;
        child.dmg *= strength;
        child.extra.strength = strength;
    }
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

// units.py:_spawn_meteormite: transfer exact current base and aura HP shares.
fn spawn_meteormite(
    battle: &mut Battle,
    unit: UnitRef,
    x: f64,
    y: f64,
    health: f64,
    small: bool,
    aura_bonus: f64,
    aura_hp: f64,
) {
    let child = spawn_child(battle, unit, "Meteormite", x, y);
    let base_max_hp = battle.unit(unit).base_max_hp / 2.0;
    let share = if small { 1.0 } else { 0.5 };
    let level = battle.unit(unit).level.clone().expect("Meteor Golem level");
    let child = battle.unit_mut(child);
    child.base_max_hp = base_max_hp;
    child.aura_bonus = aura_bonus / 2.0;
    child.max_hp = child.base_max_hp + child.aura_bonus;
    child.hp = health * share;
    child.extra.aura_hp = aura_hp * share;
    child.extra.meteor_aura_transfer = aura_bonus > 0.0;
    child.extra.meteor_components = Some(vec![("permanent".to_owned(), level)]);
}

// units.py:1077-1084: the thrown child is created only when the projectile lands.
fn split_meteor(battle: &mut Battle, unit: UnitRef, pending: &mut Pending) {
    let u = battle.unit(unit);
    let small = (u.hp - u.extra.aura_hp).max(0.0) < u.base_max_hp * 0.01;
    let (x, y, health) = (u.x, u.y, u.hp);
    let (aura_bonus, aura_hp) = (u.aura_bonus, u.extra.aura_hp);
    pending.extra.meteor_health = health;
    pending.extra.meteor_small = small;
    pending.extra.meteor_aura_bonus = aura_bonus;
    pending.extra.meteor_aura_hp = aura_hp;
    if !small {
        spawn_meteormite(battle, unit, x, y, health, small, aura_bonus, aura_hp);
    }
    battle.unit_mut(unit).alive = false;
}

// units.py:1087-1141: approach the nearest compatible idle child, then combine.
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
    let row = battle.catalog.game_unit_data(&u.name, u.level.as_ref());
    let radius = game_int(row, "MergeSearchRadius", 0) as f64 / 100.0;
    let mut other = None;
    let mut best_key = (f64::INFINITY, usize::MAX);
    for candidate in battle.attackers_pool() {
        let reference = candidate.reference();
        if reference == unit
            || !candidate.alive
            || candidate.name_id != Name::Meteormite
            || candidate.extra.clone
            || !candidate.can_act(battle.t)
            || candidate.extra.leaping
            || geom::dist(u.x, u.y, candidate.x, candidate.y) > radius
        {
            continue;
        }
        if candidate.target.is_some_and(|target| {
            battle.entity_alive(target)
                && target_distance(battle, EntityRef::Unit(reference), target) <= candidate.range
        }) {
            continue;
        }
        let key = (
            geom::dist(u.x, u.y, candidate.x, candidate.y),
            candidate.id.0,
        );
        if other.is_none() || key < best_key {
            other = Some(reference);
            best_key = key;
        }
    }
    let Some(other) = other else {
        return false;
    };
    let (x, y) = battle.entity_position(EntityRef::Unit(other));
    let u = battle.unit(unit);
    if (u.x, u.y) != (x, y) {
        if battle.t < u.held_until {
            return true;
        }
        battle.move_towards(unit, EntityRef::Unit(other), Some((x, y)));
        let u = battle.unit(unit);
        let other = battle.unit(other);
        if (u.x, u.y) != (other.x, other.y) {
            return true;
        }
    }
    let u = battle.unit(unit);
    let parent = battle.spawn(
        "Meteor Golem",
        Team::Atk,
        u.x,
        u.y,
        SpawnOptions {
            level: u.level.clone(),
            group: u.group.clone(),
            ..Default::default()
        },
    );
    let base_max_hp = battle.unit(unit).base_max_hp + battle.unit(other).base_max_hp;
    let aura_bonus = battle.unit(unit).aura_bonus + battle.unit(other).aura_bonus;
    let hp = battle.unit(unit).hp + battle.unit(other).hp;
    let aura_hp = battle.unit(unit).extra.aura_hp + battle.unit(other).extra.aura_hp;
    let mut components = battle
        .unit(unit)
        .extra
        .meteor_components
        .clone()
        .unwrap_or_default();
    components.extend(
        battle
            .unit(other)
            .extra
            .meteor_components
            .clone()
            .unwrap_or_default(),
    );
    let parent_unit = battle.unit_mut(parent);
    parent_unit.base_max_hp = base_max_hp;
    parent_unit.aura_bonus = aura_bonus;
    parent_unit.max_hp = base_max_hp + aura_bonus;
    parent_unit.hp = hp;
    parent_unit.extra.aura_hp = aura_hp;
    parent_unit.extra.meteor_aura_transfer = aura_bonus > 0.0;
    parent_unit.extra.meteor_components = Some(components);
    battle.unit_mut(unit).alive = false;
    battle.unit_mut(other).alive = false;
    battle.unit_mut(parent).invuln_until = battle.t + battle.dt;
    true
}

// units.py:1188-1220: rank eligible one-tile groups by total housing, then ID.
fn launcher_target(battle: &Battle, unit: UnitRef) -> Option<UnitRef> {
    let candidates: Vec<_> = battle
        .attackers_pool()
        .filter(|ally| {
            ally.reference() != unit
                && ally.alive
                && battle.t >= ally.active_at
                && !ally.extra.suspended
                && !matches!(
                    ally.name_id,
                    Name::SpellSkeleton | Name::Bat | Name::Totem | Name::Furnace | Name::Firemite
                )
                && !matches!(ally.kind, Tag::Siege | Tag::SiegeIdle)
        })
        .collect();
    let mut best: Option<UnitRef> = None;
    let mut best_weight = 0;
    for ally in &candidates {
        let weight: i64 = candidates
            .iter()
            .filter(|member| geom::dist(ally.x, ally.y, member.x, member.y) <= 1.0)
            .map(|member| if member.is_hero { 25 } else { member.housing })
            .sum();
        let heavier = weight > best_weight;
        let earlier = weight == best_weight && best.is_some_and(|best| ally.id.0 < best.id.0);
        if weight >= 2 && (heavier || earlier) {
            best = Some(ally.reference());
            best_weight = weight;
        }
    }
    best
}

// units.py:1223-1319: enqueue launcher occupants before its delayed healing/cargo.
pub fn launch_barrel(battle: &mut Battle, unit: UnitRef, target: EntityRef) {
    if battle.unit(unit).extra.barrels <= 0 {
        return;
    }
    let (x, y) = battle.entity_position(target);
    battle.unit_mut(unit).extra.barrels -= 1;
    let mut landing = None;
    if battle.unit(unit).name_id == Name::SkyWagon {
        for (name, column) in [
            ("Minion", "Minions"),
            ("Balloon", "Balloon"),
            ("Baby Dragon", "Baby Dragon"),
        ] {
            let count =
                unit_stat(battle, unit, &[&format!("Troops Spawned / {column}")], None) as i64;
            let level =
                unit_stat(battle, unit, &[&format!("Troop Levels / {column}")], None) as i64;
            for _ in 0..count {
                let u = battle.unit(unit);
                battle.spawn(
                    name,
                    unit.team,
                    x,
                    y,
                    SpawnOptions {
                        level: Some(Level::Int(level)),
                        kind: Tag::Summon,
                        group: u.group.clone(),
                        owner: Some(unit),
                        ..Default::default()
                    },
                );
            }
        }
        let damage = unit_stat(battle, unit, &["Damage per Hit*"], None);
        battle.hit_building(target, damage, None, "normal");
    } else {
        // units.py:1244-1291: HitSpell order, durations and first group sizes.
        let projectile = projectile_data(battle, battle.unit(unit), false);
        let spell_level = Level::Int(game_required_int(projectile, "HitSpellLevel"));
        let spell = battle.catalog.game_data(
            "spells",
            projectile.at("HitSpell").str(),
            Some(&spell_level),
        );
        let at = battle.t + game_required_int(projectile, "FixedTravelTime") as f64 / 1000.0;
        landing = Some(at);
        let names: Vec<_> = spell
            .at("SummonTroop")
            .str()
            .split(';')
            .map(str::to_owned)
            .collect();
        let parse = |key: &str, default: &str| -> Vec<i64> {
            spell
                .get(key)
                .map_or(default, crate::json::Json::str)
                .split(';')
                .map(|value| value.trim().parse().expect("barrel integer cell"))
                .collect()
        };
        let counts = parse("UnitsToSpawn", "");
        let levels = parse("SpawnUpgradeLevel", "");
        let durations = parse("SpawnDuration", "0;0;0;0");
        let first_groups = parse("SpawnFirstGroupSize", "1;1;1;1");
        let mut group_start = at;
        let groups = names
            .into_iter()
            .zip(counts)
            .zip(levels)
            .zip(durations)
            .zip(first_groups);
        for ((((name, count), level), duration), first) in groups {
            let duration = duration as f64 / 1000.0;
            let gap = if count != 0 {
                duration / count as f64
            } else {
                0.0
            };
            for index in 0..count {
                let u = battle.unit(unit);
                let mut pending = Pending::new(
                    group_start + (index - first + 1).max(0) as f64 * gap,
                    x,
                    y,
                    0.0,
                    0.0,
                    false,
                    false,
                    &u.name,
                );
                pending.team = unit.team;
                pending.extra.summon =
                    Some((name.clone(), Level::Int(level), u.group.clone(), Some(unit)));
                pending.actor = Some(EntityRef::Unit(unit));
                battle.add_pending(pending);
            }
            group_start += duration;
        }
    }
    let entry = if battle.onboard_cargo.is_empty() {
        None
    } else {
        Some(battle.onboard_cargo.remove(0))
    };
    let had_entry = entry.is_some();
    if battle.unit(unit).name_id == Name::SkyWagon {
        if let Some(entry) = entry {
            let group = battle.unit(unit).group.clone();
            spawn_cargo(battle, entry, x, y, &group, true);
        }
    } else {
        let mut pending = Pending::new(
            landing.expect("launcher landing time"),
            x,
            y,
            1.0,
            0.0,
            false,
            false,
            &battle.unit(unit).name,
        );
        pending.team = unit.team;
        pending.extra.launcher_barrel = Some(entry);
        pending.actor = Some(EntityRef::Unit(unit));
        battle.add_pending(pending);
    }
    if had_entry && battle.onboard_cargo.is_empty() {
        battle.plan.release_cc();
    }
    let next = battle.t + battle.unit(unit).interval;
    battle.unit_mut(unit).extra.next = next;
    if battle.unit(unit).extra.barrels == 0 {
        battle.kill(unit);
    }
}

// units.py:1322-1344: heal eligible ground allies, then deliver this barrel's cargo.
pub fn barrel_impact(battle: &mut Battle, pending: Pending) {
    let recipients: Vec<_> = battle
        .attackers_pool()
        .filter(|ally| {
            ally.alive
                && battle.t >= ally.active_at
                && !ally.extra.suspended
                && !ally.flying
                && !matches!(
                    ally.name_id,
                    Name::Furnace | Name::Firemite | Name::Totem | Name::SpellSkeleton | Name::Bat
                )
                && !matches!(ally.kind, Tag::Siege | Tag::SiegeIdle)
                && geom::dist(pending.x, pending.y, ally.x, ally.y) <= pending.radius
        })
        .map(Unit::reference)
        .collect();
    for ally in recipients {
        battle.unit_mut(ally).heal(6.0);
    }
    if let Some(entry) = pending.extra.launcher_barrel.expect("launcher barrel") {
        let Some(EntityRef::Unit(actor)) = pending.actor else {
            panic!("launcher barrel actor");
        };
        let group = battle.unit(actor).group.clone();
        spawn_cargo(battle, entry, pending.x, pending.y, &group, true);
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
        ally.reference() != unit
            && ally.alive
            && ally.flying
            && battle.t >= ally.active_at
            && !ally.extra.suspended
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
    if !matches!(u.name_id, Name::Valkyrie | Name::SuperValkyrie) {
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
                && segment_entry(battle, u.x, u.y, x, y, EntityRef::Building(building.id)).is_some()
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

// units.py:1578-1590: arrival and pushback delays share the attack gate.
pub fn attack_ready(battle: &mut Battle, unit: UnitRef, target: EntityRef) -> bool {
    let u = battle.unit_mut(unit);
    let arrival_delay = std::mem::take(&mut u.extra.arrival_windup);
    let pushback_delay = std::mem::take(&mut u.extra.pushback_windup);
    if arrival_delay > 0.0 || pushback_delay > 0.0 {
        u.cooldown = u.cooldown.max(arrival_delay).max(pushback_delay);
    }
    if !matches!(battle.unit(unit).name_id, Name::Frostmite | Name::Firemite) {
        return true;
    }
    let t = battle.t;
    let delay = battle.params.mite_attack_windup;
    let u = battle.unit_mut(unit);
    if u.extra.attack_target != Some(target) {
        u.extra.attack_target = Some(target);
        u.extra.attack_ready_at = t + delay;
    }
    t >= u.extra.attack_ready_at
}

// units.py:1250-1253.
pub fn effective_range(battle: &Battle, unit: &Unit) -> f64 {
    if unit.spec.has_special(Special::LongShot) && unit.extra.long_shots > 0 {
        // units.py:1333-1335: game-data Long Shot range is 9.75 tiles.
        let row =
            battle
                .catalog
                .game_data("special_abilities", "SuperMinionSpecialProjectiles", None);
        return game_int(row, "AttackRange", 0) as f64 / 100.0;
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
    &battle.params.new_target_delays
}

// units.py:1649-1675: selection wait and the first-hit minimum on arrival.
pub fn new_target_windup(battle: &mut Battle, unit: UnitRef, target: EntityRef) {
    let u = battle.unit_mut(unit);
    u.extra.arrival_windup = 0.0;
    let killed_delay = std::mem::take(&mut u.extra.target_killed_cooldown);
    let u = battle.unit(unit);
    if !battle.windup || u.interval == 0.0 {
        return;
    }
    let explicit_delay = new_target_delays(battle).get(&u.name).copied();
    let mut delay = if killed_delay != 0.0 {
        killed_delay
    } else {
        explicit_delay.unwrap_or(u.interval)
    };
    if killed_delay == 0.0 {
        let cooldown = u.cooldown.max(delay);
        battle.unit_mut(unit).cooldown = cooldown;
    }
    let u = battle.unit(unit);
    let range = effective_range(battle, u);
    if target_distance(battle, EntityRef::Unit(unit), target) <= range {
        return;
    }
    if killed_delay == 0.0 && explicit_delay.is_none() {
        if u.name_id == Name::Dragon {
            delay = battle.params.dragon_arrival_windup;
        } else if range < 1.0 {
            delay = delay.min(battle.params.melee_arrival_windup);
        }
    }
    battle.unit_mut(unit).extra.arrival_windup = delay;
}

// units.py:1678-1690: a live wall target takes priority when restarting a charge.
pub fn pushback_windup(battle: &mut Battle, unit: UnitRef) {
    let u = battle.unit(unit);
    let target = u
        .wall_target
        .filter(|wall| battle.entity_alive(EntityRef::Wall(*wall)))
        .map(EntityRef::Wall)
        .or(u.target);
    if !battle.windup || u.interval == 0.0 {
        return;
    }
    let Some(target) = target else {
        return;
    };
    if !battle.entity_alive(target)
        || target_distance(battle, EntityRef::Unit(unit), target) <= effective_range(battle, u)
    {
        return;
    }
    // units.py:pushback_windup: only the Electro Dragon's charge is evidenced.
    if u.name != "Electro Dragon" {
        return;
    }
    let delay = new_target_delays(battle)
        .get(&u.name)
        .copied()
        .unwrap_or(u.interval);
    battle.unit_mut(unit).extra.pushback_windup = delay;
}

// units.py:1693-1704: retain the numeric kill delay for the next arrival.
pub fn target_killed_cooldown(battle: &mut Battle, unit: UnitRef, target: EntityRef) {
    if battle.entity_alive(target) {
        return;
    }
    let u = battle.unit(unit);
    let row = if u.spec.has_special(Special::RoyalRampage)
        && unit.team == Team::Atk
        && duke_alone(battle, unit)
    {
        battle
            .catalog
            .game_data("special_abilities", "DragonDukeRageWhenAlone", None)
    } else {
        battle.catalog.game_unit_data(&u.name, u.level.as_ref())
    };
    let delay = game_int(row, "TargetKilledCooldownTimer", 0) as f64 / 1000.0;
    if delay > 0.0 {
        let u = battle.unit_mut(unit);
        u.cooldown = delay;
        u.extra.target_killed_cooldown = delay;
    }
}

// units.py:304-306,1522,2389-2391: all burst resets read the same shot count.
fn burst_shots(battle: &Battle, unit: UnitRef) -> i64 {
    let raw = battle
        .catalog
        .stats
        .attrs(&battle.unit(unit).name)
        .at("raw");
    crate::stats::num(raw.at("Shots per Burst"), None).expect("burst shot count") as i64
}

// units.py:1510-1523: decrement after each shot; the final shot starts the gap.
pub fn attack_interval(battle: &mut Battle, unit: UnitRef) -> f64 {
    if tantrum(battle, unit) {
        return battle.unit(unit).interval / 1.5;
    }
    if !battle.unit(unit).spec.has_special(Special::Burst) {
        return battle.unit(unit).interval;
    }
    battle.unit_mut(unit).extra.burst_left -= 1;
    if battle.unit(unit).extra.burst_left > 0 {
        let raw = battle
            .catalog
            .stats
            .attrs(&battle.unit(unit).name)
            .at("raw");
        return crate::stats::num(raw.at("Time Between Shots"), None).expect("burst shot interval");
    }
    let shots = burst_shots(battle, unit);
    battle.unit_mut(unit).extra.burst_left = shots;
    let raw = battle
        .catalog
        .stats
        .attrs(&battle.unit(unit).name)
        .at("raw");
    crate::stats::num(raw.at("Time Between Bursts"), None).expect("burst interval")
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
    // units.py:1550-1567: Rider becomes active only when its 1.3 s flight lands.
    let mut pending = Pending::new(
        battle.t + 1.3,
        u.x - 5.0 * dx,
        u.y - 5.0 * dy,
        0.0,
        0.0,
        false,
        false,
        &u.name,
    );
    pending.team = unit.team;
    pending.extra.summon = Some((
        "Super Rider".to_owned(),
        u.level.clone().expect("Super Hog Rider level"),
        u.group.clone(),
        Some(unit),
    ));
    pending.actor = Some(EntityRef::Unit(unit));
    battle.add_pending(pending);
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
        if v.alive
            && !v.extra.suspended
            && battle.t >= v.active_at
            && battle.can_hit(unit, victim)
            && !(battle.unit(unit).spec.splash_ground_only && v.flying)
        {
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

// units.py:1502-1514: strongest active frost, with independent expiries.
pub fn frost_mult(effects: &[(f64, f64)], t: f64) -> f64 {
    effects
        .iter()
        .filter(|(_, until)| t < *until)
        .map(|(factor, _)| *factor)
        .reduce(f64::min)
        .unwrap_or(1.0)
}

// units.py:1517-1530: frost remains separate from all other slow sources.
pub fn frost(battle: &mut Battle, target: EntityRef, factor: f64, seconds: f64) {
    let t = battle.t;
    let active = match target {
        EntityRef::Building(id) => &mut battle.building_mut(id).extra.frost_effects,
        EntityRef::Unit(id) => &mut battle.unit_mut(id).extra.frost_effects,
        _ => panic!("frost requires a building or unit"),
    };
    active.retain(|(_, until)| t < *until);
    active.push((factor, t + seconds));
}

// units.py:1395-1417.
pub fn chill(battle: &mut Battle, unit: UnitRef, target: EntityRef) {
    let u = battle.unit(unit);
    if u.name_id == Name::Electromite {
        // units.py:1478-1483: Electromite applies complete frost for 100 ms.
        let row = battle
            .catalog
            .game_data("special_abilities", "ElectromiteStunAbility", None);
        let factor = 1.0 - game_int(row, "FrostOnHitPercent", 0) as f64 / 100.0;
        let duration = game_int(row, "FrostOnHitTime", 0) as f64 / 1000.0;
        frost(battle, target, factor, duration);
        return;
    }
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
pub fn hit_target(battle: &mut Battle, unit: UnitRef, target: EntityRef, damage: f64) {
    hit_target_bonus(battle, unit, target, damage, 0.0);
}

// units.py:1507-1519: percentage bonuses bypass multipliers; splash visits once.
fn hit_target_bonus(
    battle: &mut Battle,
    unit: UnitRef,
    target: EntityRef,
    damage: f64,
    bonus: f64,
) {
    let damage = damage * mult_vs(battle, unit, target) + bonus;
    if let EntityRef::Unit(victim) = target {
        battle.hit_unit(victim, damage, None, "normal", Some(EntityRef::Unit(unit)));
        after_unit_hit(battle, unit, victim, damage, false);
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
        chain_hit(
            battle,
            unit,
            target,
            damage,
            Vec::new(),
            target,
            sp.chain,
            damage,
            battle.t,
        );
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
            area_hit(
                battle,
                unit,
                x,
                y,
                sp.splash,
                damage,
                true,
                if k == 0 { Some(target) } else { None },
            );
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
        area_hit(
            battle,
            unit,
            u.x,
            u.y,
            sp.splash,
            damage,
            true,
            Some(target),
        );
    } else {
        // units.py:1709-1726: SelfAsAoeCenter uses the attacker's position.
        let center = if self_aoe_center(battle, unit) {
            EntityRef::Unit(unit)
        } else {
            target
        };
        let (x, y) = battle.entity_position(center);
        area_hit(battle, unit, x, y, sp.splash, damage, true, Some(target));
    }
}

// units.py:1548-1605: delayed chains keep the original 128-ms clock and hit set.
fn chain_hit(
    battle: &mut Battle,
    unit: UnitRef,
    target: EntityRef,
    damage: f64,
    mut hit: Vec<EntityRef>,
    primary: EntityRef,
    remaining: usize,
    base_damage: f64,
    at: f64,
) {
    if battle.entity_alive(target)
        && match target {
            EntityRef::Unit(victim) => battle.unit(victim).indirect_targetable(battle),
            _ => true,
        }
    {
        hit_target(battle, unit, target, damage);
    }
    if !hit.contains(&target) {
        hit.push(target);
    }
    if remaining == 0 {
        return;
    }
    let u = battle.unit(unit);
    let sp = Arc::clone(&u.spec);
    let is_electro_dragon = u.name_id == Name::ElectroDragon;
    let origin = if sp.chain_from_primary {
        primary
    } else {
        target
    };
    let mut next = None;
    let mut best_key = (f64::INFINITY, f64::INFINITY);
    for victim in attack_targets(battle, unit, false) {
        if hit.contains(&victim) {
            continue;
        }
        let mut distance = target_distance(battle, origin, victim);
        let mut reach = sp.chain_range;
        if is_electro_dragon {
            if let (EntityRef::Building(origin), EntityRef::Building(victim)) = (origin, victim) {
                let origin = battle.building(origin);
                let victim = battle.building(victim);
                let half_size = (origin.size + victim.size) as f64 / 2.0;
                distance = geom::py_hypot(
                    0.0_f64.max((origin.x - victim.x).abs() - half_size),
                    0.0_f64.max((origin.y - victim.y).abs() - half_size),
                );
                reach = 1.0;
            }
        }
        if distance <= reach {
            let max_hp = match victim {
                EntityRef::Building(id) => battle.building(id).max_hp,
                EntityRef::Wall(id) => battle.walls[id.0].max_hp,
                EntityRef::Unit(id) => battle.unit(id).max_hp,
                EntityRef::Trap(_) => unreachable!(),
            };
            let key = (distance, -max_hp);
            if next.is_none() || key < best_key {
                next = Some(victim);
                best_key = key;
            }
        }
    }
    let Some(next) = next else {
        return;
    };
    let amount = (if sp.chain_from_primary {
        base_damage
    } else {
        damage
    }) * sp.chain_decay;
    let u = battle.unit(unit);
    let row = if u.name_id == Name::Electromite {
        battle
            .catalog
            .game_data("special_abilities", "ElectromiteStunAbility", None)
    } else {
        battle.catalog.game_unit_data(&u.name, u.level.as_ref())
    };
    let delay = game_int(row, "ChainAttackDelay", 0) as f64 / 1000.0;
    if delay == 0.0 {
        chain_hit(
            battle,
            unit,
            next,
            amount,
            hit,
            primary,
            remaining - 1,
            base_damage,
            at,
        );
        return;
    }
    let (x, y) = battle.entity_position(next);
    let mut pending = Pending::new(
        at + delay,
        x,
        y,
        0.0,
        amount,
        u.hits_air,
        u.hits_ground,
        u.source.clone(),
    );
    pending.team = if unit.team == Team::Atk {
        Team::Def
    } else {
        Team::Atk
    };
    pending.extra.troop_impact = Some("chain".to_owned());
    pending.extra.hit = hit;
    pending.extra.primary = Some(primary);
    pending.extra.remaining = remaining - 1;
    pending.extra.base_damage = base_damage;
    pending.actor = Some(EntityRef::Unit(unit));
    pending.effect = Some(Tag::Chain);
    pending.target = Some(next);
    battle.add_pending(pending);
}

fn self_aoe_center(battle: &Battle, unit: UnitRef) -> bool {
    let u = battle.unit(unit);
    battle
        .catalog
        .game_unit_data(&u.name, u.level.as_ref())
        .get("SelfAsAoeCenter")
        .is_some_and(|value| value.str() == "TRUE")
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
            if (tx - x - dx as f64).abs() <= half + 0.5 && (ty - y - dy as f64).abs() <= half + 0.5
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

// units.py:1760-1778: resolve the per-level projectile before consuming Long Shot.
fn projectile_data<'a>(battle: &'a Battle, unit: &Unit, noble_iron: bool) -> &'a crate::json::Json {
    let row = battle
        .catalog
        .game_unit_data(&unit.name, unit.level.as_ref());
    let projectile = if unit.name_id == Name::SuperMinion && unit.extra.long_shots > 0 {
        Some("super_gargoyle_projectile_big")
    } else if noble_iron {
        Some("TurboStartProjectile")
    } else {
        row.get("Projectile").map(crate::json::Json::str)
    };
    battle
        .catalog
        .game_data("projectiles", projectile.unwrap_or(""), None)
}

pub fn projectile_speed(battle: &Battle, unit: &Unit, noble_iron: bool) -> Option<f64> {
    let speed = game_int(projectile_data(battle, unit, noble_iron), "Speed", 0);
    (speed > 0).then_some(speed as f64 / 100.0)
}

// units.py:1781-1888: geometry and offsets are captured at release time.
pub fn launch_projectile(
    battle: &mut Battle,
    unit: UnitRef,
    target: EntityRef,
    damage: f64,
    speed: f64,
    rocket: bool,
    noble_iron: bool,
) {
    let u = battle.unit(unit);
    let sp = Arc::clone(&u.spec);
    let name = u.name_id;
    let source = u.source.clone();
    let (hits_air, hits_ground) = (u.hits_air, u.hits_ground);
    let (mut x, mut y) = battle.entity_position(target);
    let length = geom::dist(u.x, u.y, x, y);
    let denominator = if length == 0.0 { 1.0 } else { length };
    let (dx, dy) = ((x - u.x) / denominator, (y - u.y) / denominator);
    let projectile = if rocket {
        battle
            .catalog
            .game_data("projectiles", "RocketSpearProjectile", None)
    } else {
        projectile_data(battle, u, noble_iron)
    };
    let start_offset = game_int(projectile, "StartOffset", 0) as f64 / 100.0;
    let flight = 0.0_f64.max(length - start_offset) / speed;
    let mut mode = "single";
    let mut track = Some(target);
    let mut extra = crate::state::PendingExtra::default();
    if sp.attack == Tag::Pierce {
        mode = "pierce";
        track = None;
        extra.origin = Some((u.x, u.y));
        extra.direction = Some((dx, dy));
        extra.speed = speed;
    } else if sp.attack == Tag::Bounce {
        for index in 0..=sp.bounces {
            let travel = 0.0_f64.max(length - start_offset) + index as f64 * sp.bounce_gap;
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
            pending.team = if unit.team == Team::Atk {
                Team::Def
            } else {
                Team::Atk
            };
            pending.extra.troop_impact = Some("area".to_owned());
            pending.actor = Some(EntityRef::Unit(unit));
            battle.add_pending(pending);
        }
        return;
    } else if matches!(name, Name::Yetimite | Name::Firemite | Name::Frostmite) {
        mode = "leap";
        battle.unit_mut(unit).extra.leaping = true;
    } else if name == Name::MeteorGolem {
        mode = "meteor";
    } else if name == Name::FlameFlinger {
        // units.py:1977-1995: preserve the three separate 128 ms arrivals.
        for index in 0..3 {
            let mut pending = Pending::new(
                battle.t + flight + index as f64 * 0.128,
                x,
                y,
                sp.splash,
                damage,
                hits_air,
                hits_ground,
                source.clone(),
            );
            pending.team = if unit.team == Team::Atk {
                Team::Def
            } else {
                Team::Atk
            };
            pending.extra.troop_impact = Some("area".to_owned());
            pending.actor = Some(EntityRef::Unit(unit));
            battle.add_pending(pending);
        }
        return;
    } else if name == Name::SuperDragon {
        mode = "dragon";
        track = None;
    } else if sp.attack == Tag::Splash {
        mode = "area";
        track = None;
    }
    if self_aoe_center(battle, unit) {
        let u = battle.unit(unit);
        (x, y) = (u.x, u.y);
        mode = "area";
        track = None;
    }
    if rocket {
        mode = "rocket";
    } else if name == Name::Longshot {
        mode = "longshot";
        track = Some(target);
    }
    extra.troop_impact = Some(mode.to_owned());
    if mode == "single" && battle.unit(unit).kit.is_some() {
        extra.monolith_bonus = heroes::monolith_bonus(battle, unit, target);
    }
    let mut pending = Pending::new(
        battle.t + if mode == "pierce" { battle.dt } else { flight },
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
    pending.extra = extra;
    pending.actor = Some(EntityRef::Unit(unit));
    pending.target = track;
    if mode == "meteor" {
        split_meteor(battle, unit, &mut pending);
    }
    battle.add_pending(pending);
}

// units.py:1891-1992: impacts survive actor death; append new hops after all due hits.
pub fn projectile_impact(battle: &mut Battle, mut pending: Pending) {
    let Some(EntityRef::Unit(unit)) = pending.actor else {
        panic!("troop projectile actor must be a unit");
    };
    let mode = pending
        .extra
        .troop_impact
        .as_deref()
        .expect("troop impact mode");
    let (x, y) = pending.target.map_or((pending.x, pending.y), |target| {
        battle.entity_position(target)
    });
    if mode == "chain" {
        chain_hit(
            battle,
            unit,
            pending.target.expect("chain target"),
            pending.damage,
            pending.extra.hit,
            pending.extra.primary.expect("chain primary"),
            pending.extra.remaining,
            pending.extra.base_damage,
            pending.at,
        );
        return;
    }
    if mode == "pierce" {
        let (ox, oy) = pending.extra.origin.expect("piercing origin");
        let (dx, dy) = pending.extra.direction.expect("piercing direction");
        let previous = pending.extra.travel;
        let range = battle.unit(unit).spec.pierce;
        let travel = range.min(
            (battle.t - pending.released_at.expect("projectile release")) * pending.extra.speed,
        );
        for victim in attack_targets(battle, unit, true) {
            if pending.extra.hit.contains(&victim) {
                continue;
            }
            let (vx, vy) = battle.entity_position(victim);
            let (px, py) = (vx - ox, vy - oy);
            let along = px * dx + py * dy;
            let half = entity_half(battle, victim);
            if along + half >= previous
                && along - half <= travel
                && 0.0 < along
                && along <= range
                && (px * dy - py * dx).abs() <= half + 0.3
            {
                pending.extra.hit.push(victim);
                hit_target(battle, unit, victim, pending.damage);
            }
        }
        if travel < range {
            pending.extra.travel = travel;
            pending.at = geom::round6(battle.t + battle.dt);
            battle.add_pending(pending);
        }
        return;
    }
    if mode == "rocket" {
        let target = pending.target.expect("Rocket Spear target");
        if battle.entity_alive(target)
            && match target {
                EntityRef::Unit(victim) => battle.unit(victim).indirect_targetable(battle),
                _ => true,
            }
        {
            heroes::damage_target(battle, target, pending.damage);
            heroes::blast(battle, x, y, 0.9, pending.damage, Some(target), 1.0, false);
        }
        return;
    }
    if mode == "longshot" {
        let Some(EntityRef::Unit(target)) = pending.target else {
            panic!("Longshot unit target");
        };
        let flying = battle.unit(target).flying;
        let mut targets = attack_targets(battle, unit, false);
        for &victim in &targets {
            if let EntityRef::Unit(reference) = victim {
                let victim_unit = battle.unit(reference);
                if victim_unit.flying == flying
                    && geom::dist(victim_unit.x, victim_unit.y, x, y) <= pending.radius
                {
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
            hit_target_bonus(
                battle,
                unit,
                target,
                pending.damage,
                pending.extra.monolith_bonus,
            );
            if battle.unit(unit).kit.is_some() {
                heroes::on_hit_extra(battle, unit, target);
            }
        }
        return;
    }
    if mode == "dragon" {
        for victim in attack_targets(battle, unit, true) {
            if dragon_footprint(battle, victim, x, y) {
                hit_target(battle, unit, victim, pending.damage);
            }
        }
        return;
    }
    area_hit(
        battle,
        unit,
        x,
        y,
        pending.radius,
        pending.damage,
        true,
        None,
    );
    if mode == "meteor" {
        spawn_meteormite(
            battle,
            unit,
            x,
            y,
            pending.extra.meteor_health,
            pending.extra.meteor_small,
            pending.extra.meteor_aura_bonus,
            pending.extra.meteor_aura_hp,
        );
    }
    let u = battle.unit(unit);
    if (mode == "leap" && u.name_id == Name::Firemite) || u.name_id == Name::FlameFlinger {
        // units.py:2040-2094: each impact resolves its projectile's HitSpell.
        let projectile = if unit.team == Team::Def && u.name_id == Name::Firemite {
            let row =
                battle
                    .catalog
                    .game_data("characters", "Firemite Spawn_DEF", u.level.as_ref());
            battle
                .catalog
                .game_data("projectiles", row.at("Projectile").str(), None)
        } else {
            projectile_data(battle, u, false)
        };
        let level = Level::Int(game_required_int(projectile, "HitSpellLevel"));
        let spell =
            battle
                .catalog
                .game_data("spells", projectile.at("HitSpell").str(), Some(&level));
        let hits = game_required_int(spell, "NumberOfHits");
        let gap = game_required_int(spell, "TimeBetweenHitsMS") as f64 / 1000.0;
        let radius = game_required_int(spell, "Radius") as f64 / 100.0;
        let damage = spell
            .at("PoisonDPS")
            .str()
            .parse::<f64>()
            .expect("burn DPS");
        let strength = if unit.team == Team::Atk {
            u.extra.strength
        } else {
            1.0
        };
        let kind = if unit.team == Team::Atk {
            "burn"
        } else {
            "def_burn"
        };
        let mut field = Field::new(kind, x, y, radius, battle.t + hits as f64 * gap);
        field.team = unit.team;
        field.value = damage * strength;
        field.extra.pulses = hits as usize;
        field.extra.has_pulses = true;
        field.extra.gap = Some(gap);
        field.extra.ramp = spell
            .get("PoisonIncreaseSlowly")
            .is_some_and(|v| v.str() == "TRUE");
        field.extra.hits_air = spell
            .get("PoisonAffectAir")
            .is_some_and(|v| v.str() == "TRUE");
        field.extra.hits_ground = true;
        field.extra.buildings = unit.team == Team::Atk;
        field.extra.walls = !spell
            .get("ImmunityWalls")
            .is_some_and(|v| v.str() == "TRUE");
        field.extra.wall_mult = if spell
            .get("PreferredTarget")
            .is_some_and(|v| v.str() == "Wall")
        {
            spell.get("PreferredTargetDamageMod").map_or(1.0, |v| {
                v.str().parse::<f64>().expect("wall damage multiplier")
            })
        } else {
            1.0
        };
        field.extra.actor = Some(unit);
        field.extra.src = Some(u.source.clone());
        field.started = battle.t;
        battle.fields.push(field);
    }
    if mode == "leap" {
        let u = battle.unit_mut(unit);
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
    if sp.attack == Tag::None
        && !(battle.unit(unit).name_id == Name::RuinWitch && unit.team == Team::Def)
    {
        return;
    }
    let (mut rage, _) = rage_boost(battle.unit(unit), t);
    let u = battle.unit(unit);
    rage = rage.max(u.aura_dmg).max(u.extra.bell_damage);
    let multiplier = 1.0;
    if sp.has_special(Special::RoyalRampage) && unit.team == Team::Atk && duke_alone(battle, unit) {
        // units.py:2237-2241: Rampage competes with other damage boosts.
        rage = rage.max(2.0);
    }
    if tantrum(battle, unit) {
        rage = rage.max(2.0);
    }
    let mut damage = battle.unit(unit).dmg * multiplier;
    if sp.has_special(Special::Burst) && battle.unit(unit).extra.burst_target != Some(target) {
        // units.py:2205-2207: reset before binding the new target.
        interrupt_attack(battle, unit);
        battle.unit_mut(unit).extra.burst_target = Some(target);
    }
    if sp.attack == Tag::Beam {
        // units.py:2208-2209: stage damage replaces the unit's ordinary hit.
        damage = beam(battle, unit, target) * multiplier;
    }
    let ordinary = damage;
    damage *= rage;
    let rocket = battle
        .unit(unit)
        .kit
        .as_ref()
        .is_some_and(|kit| kit.has("Rocket Spear") && kit.spear_shots > 0);
    let noble_iron = battle
        .unit(unit)
        .kit
        .as_ref()
        .is_some_and(|kit| kit.has("Noble Iron") && kit.spear_shots > 0);
    if battle.unit(unit).kit.is_some() {
        let u = battle.unit(unit);
        if t < u.extra.vial_until {
            let vial = u.extra.vial_bonus * battle.atk_hero_mult;
            damage = damage.max(ordinary + vial);
        }
        damage = damage.max(ordinary + heroes::strike_bonus(battle, unit));
    }
    if rocket {
        launch_projectile(battle, unit, target, damage, 12.0, true, false);
        return;
    }
    // units.py:2028-2037: choose and launch before consuming a Long Shot.
    let speed = projectile_speed(battle, battle.unit(unit), noble_iron);
    if let Some(speed) = speed {
        launch_projectile(battle, unit, target, damage, speed, false, noble_iron);
    }
    if sp.has_special(Special::LongShot) && battle.unit(unit).extra.long_shots > 0 {
        battle.unit_mut(unit).extra.long_shots -= 1;
    }
    if speed.is_some() {
        return;
    }
    if SPATIAL_TROOPS.contains(&battle.unit(unit).name_id)
        || matches!(
            sp.attack,
            Tag::Suicide | Tag::Spin | Tag::Chain | Tag::Bounce | Tag::Pierce
        )
        || self_aoe_center(battle, unit)
    {
        spatial_strike(battle, unit, target, damage);
        if battle.unit(unit).name_id == Name::Valkyrie && !battle.entity_alive(target) {
            let u = battle.unit_mut(unit);
            u.target = None;
            u.wall_target = None;
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
            gauntlet_hit(battle, unit, target, damage);
            heroes::on_hit_extra(battle, unit, target);
            return;
        }
    }
    if let EntityRef::Unit(victim) = target {
        battle.hit_unit(victim, damage, None, "normal", Some(EntityRef::Unit(unit)));
        after_unit_hit(battle, unit, victim, damage, true);
        chill(battle, unit, target);
        if battle.unit(unit).kit.is_some() {
            heroes::on_hit_extra(battle, unit, target);
        }
        if matches!(battle.unit(unit).name_id, Name::Miner | Name::SuperMiner)
            && unit.team == Team::Atk
            && !battle.entity_alive(target)
        {
            // units.py:2265-2267: the Miner hides; the Super Miner burrows now.
            battle.unit_mut(unit).target = None;
            update_burrow(battle, unit, None);
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

// units.py:2289-2309: primary first, buildings then walls, then ground defenders.
fn gauntlet_hit(battle: &mut Battle, unit: UnitRef, target: EntityRef, damage: f64) {
    let radius = battle.unit(unit).extra.gauntlet_radius;
    if let EntityRef::Unit(victim) = target {
        battle.hit_unit(victim, damage, None, "normal", Some(EntityRef::Unit(unit)));
    } else {
        battle.unit_mut(unit).damage_dealt += damage;
        battle.hit_building(target, damage, None, "normal");
    }
    let structures: Vec<_> = battle
        .buildings
        .iter()
        .map(|building| EntityRef::Building(building.id))
        .chain(battle.walls.iter().map(|wall| EntityRef::Wall(wall.id)))
        .collect();
    for structure in structures {
        let (x, y) = battle.entity_position(target);
        if structure != target
            && battle.entity_alive(structure)
            && heroes::distance(battle, structure, x, y) <= radius
        {
            battle.hit_building(structure, damage, None, "normal");
        }
    }
    let (x, y) = battle.entity_position(target);
    for defender in battle.defenders_near(x, y, radius) {
        let victim = battle.unit(defender);
        if EntityRef::Unit(defender) != target && !victim.flying && !victim.underground {
            battle.hit_unit(
                defender,
                damage,
                None,
                "normal",
                Some(EntityRef::Unit(unit)),
            );
        }
    }
}

// units.py:1947-2000: secondary provenance does not replace the attacker's src.
pub fn after_unit_hit(
    battle: &mut Battle,
    unit: UnitRef,
    target: UnitRef,
    damage: f64,
    splash: bool,
) {
    effects::damage_source(
        battle,
        Some(EntityRef::Unit(unit)),
        Tag::Secondary,
        |battle| {
            after_unit_hit_effect(battle, unit, target, damage, splash);
        },
    );
}

fn after_unit_hit_effect(
    battle: &mut Battle,
    unit: UnitRef,
    target: UnitRef,
    damage: f64,
    splash: bool,
) {
    let t = battle.t;
    let sp = Arc::clone(&battle.unit(unit).spec);
    if sp.has_special(Special::Logger) {
        // specs.py:257-261: Logger is a TH18 defending Guardian, not an
        // attacking troop or a legal Clan Castle donation.
        crate::heroes::guardian_after_hit(battle, unit, target, damage);
    }
    let victim = battle.unit(target);
    if sp.has_special(Special::HhPoison) && !(victim.kind == Tag::Guardian && victim.extra.waiting)
    {
        let u = battle.unit(unit);
        // units.py:2338-2367: Headhunter uses the shared, source-keyed poison ramp.
        let row = battle.catalog.game_unit_data(&u.name, u.level.as_ref());
        let ability_level = Level::Int(game_required_int(row, "SpecialAbilitiesLevel"));
        let ability = battle.catalog.game_data(
            "special_abilities",
            "HeadhunterPoison",
            Some(&ability_level),
        );
        let poison_level = Level::Int(game_required_int(ability, "PoisonOnHitSpellLevel"));
        let poison = battle.catalog.game_data(
            "spells",
            ability.at("PoisonOnHitSpell").str(),
            Some(&poison_level),
        );
        let duration = game_required_int(ability, "PoisonOnHitDuration") as f64 / 1000.0;
        // output/research/usage/headhunter.md:18-23; L4 is absent from the older CSV.
        // https://cocwiki.com/troops/headhunter
        let level = u.level.as_ref().expect("Headhunter level");
        let slow = battle
            .catalog
            .stats
            .get(
                &u.name,
                level,
                &["Speed Decrease"],
                Some(-game_float(poison, "SpeedBoost")),
            )
            .expect("Headhunter movement slow")
            / 100.0;
        let attack = battle
            .catalog
            .stats
            .get(
                &u.name,
                level,
                &["Attack Rate Decrease"],
                Some(-game_float(poison, "AttackSpeedBoost")),
            )
            .expect("Headhunter attack slow")
            / 100.0;
        let damage = battle
            .catalog
            .stats
            .get(
                "Poison Spell",
                &poison_level,
                &["damage"],
                Some(game_float(poison, "PoisonDPS")),
            )
            .expect("poison damage default");
        let damage = battle
            .catalog
            .stats
            .get(&u.name, level, &["Poison Max DPS"], Some(damage))
            .expect("Headhunter poison damage");
        let ramp = poison
            .get("PoisonIncreaseSlowly")
            .is_some_and(|value| value.str() == "TRUE");
        let source = Some(("unit".to_owned(), unit.id.0 as i64));
        // units.py:2375-2376: share the Poison spell's hero damage multiplier.
        let multiplier = if battle.unit(target).is_hero {
            spells::POISON_HERO_MULT
        } else {
            1.0
        };
        spells::poison(
            battle,
            target,
            damage,
            slow,
            attack,
            multiplier,
            spells::PoisonOptions {
                ramp,
                origin: "headhunter",
                source: source.clone(),
                source_until: None,
                refresh: 0.2,
            },
        );
        if let Some(state) = battle.poison.iter_mut().find(|state| {
            state.unit == target && state.origin == "headhunter" && state.source == source
        }) {
            state.until = t + duration;
        }
    }
    if splash
        && !SPATIAL_TROOPS.contains(&battle.unit(unit).name_id)
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

// units.py:2385-2392: interruption always discards beam state first.
pub fn interrupt_attack(battle: &mut Battle, unit: UnitRef) {
    reset_beam(battle.unit_mut(unit));
    if battle.unit(unit).spec.has_special(Special::Burst) {
        let shots = burst_shots(battle, unit);
        let u = battle.unit_mut(unit);
        u.extra.burst_left = shots;
        u.extra.burst_target = None;
    }
}

// units.py:2395-2398: None models removal, separately from a stored zero.
pub fn reset_beam(unit: &mut Unit) {
    unit.extra.beam_target = None;
    unit.extra.beam_time = None;
    unit.extra.beam_tick = None;
}

// units.py:2401-2412: track uninterrupted time even between damage pulses.
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

// units.py:2415-2440: staged DPS uses Python's operation order and isclose.
fn beam(battle: &mut Battle, unit: UnitRef, target: EntityRef) -> f64 {
    if battle.unit(unit).extra.beam_target != Some(target) {
        track_beam(battle, unit, target);
    }
    let u = battle.unit(unit);
    let held = u.extra.beam_time.unwrap_or(0.0);
    beam_damage(battle, u, held)
}

pub fn beam_damage(battle: &Battle, u: &Unit, held: f64) -> f64 {
    let stages = if u.name_id == Name::SuperMiner {
        [
            (0.0, "Damage per Second / Initial"),
            (1.5, "Damage per Second / After 1.5s"),
            (3.0, "Damage per Second / After 3s"),
        ]
    } else {
        // game data v18.200.9 characters.csv: Inferno Dragon L12 DPS/DPSLv2/DPSLv3
        // = 91/182/1820; ClashKing b8f42a7 agrees on base DPS. Registry exports all stages.
        [
            (0.0, "Damage per Second / Initial"),
            (1.7, "Damage per Second / After 1.7s"),
            (3.2, "Damage per Second / After 3.2s"),
        ]
    };
    let mut dps = u.dmg / u.interval;
    for (start, column) in stages {
        if held >= start || isclose(held, start) {
            if let Some(value) = battle.catalog.stats.get(
                &u.name,
                u.level.as_ref().expect("beam level"),
                &[column],
                None,
            ) {
                dps = value;
            }
        }
    }
    dps * u.interval
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
    // output/research/usage/unicorn.md: Healers cannot heal Unicorns.
    // https://clashofclans.fandom.com/wiki/Unicorn
    if u.name_id == Name::Healer && a.name_id == Name::Unicorn {
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
        && !(matches!(
            a.kind,
            Tag::Cc | Tag::Hero | Tag::Summon | Tag::TrapSkeleton | Tag::Guardian
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
    battle
        .unit_mut(recipient)
        .extra
        .healing_sources
        .clone_from(&sources);
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

// units.py:2708-2717: housing is nonnegative; stop once the group exceeds two.
fn healer_grouped(target: &Unit, weighted: &[(f64, f64, f64)], radius: f64, minimum: f64) -> bool {
    let mut weight = 0.0;
    for &(x, y, housing) in weighted {
        if geom::dist(target.x, target.y, x, y) <= radius {
            weight += housing;
            if weight > minimum {
                return true;
            }
        }
    }
    false
}

// units.py:2720-2820: recipients and projectile appends retain ally-list order.
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
    let due = battle.unit(unit).extra.heal_next.unwrap_or(t);
    let heal_ready = t >= due || isclose(t, due);
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
    let splash = if battle.unit(unit).name_id == Name::Healer {
        battle.params.healer_group_radius
    } else {
        sp.splash
    };
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
                    (
                        a.x,
                        a.y,
                        if a.is_hero {
                            battle.params.healer_hero_weight
                        } else {
                            a.housing as f64
                        },
                    )
                }),
        );
        if heal_ready {
            eligible.retain(|target| {
                healer_grouped(
                    battle.unit(*target),
                    weighted,
                    battle.params.healer_group_radius,
                    battle.params.healer_group_min_housing,
                )
            });
        } else {
            let u = battle.unit(unit);
            let current = match u.target {
                Some(EntityRef::Unit(target)) => Some(target),
                _ => None,
            };
            let mut target = [u.follow, current].into_iter().flatten().find(|candidate| {
                eligible.contains(candidate)
                    && healer_grouped(
                        battle.unit(*candidate),
                        weighted,
                        battle.params.healer_group_radius,
                        battle.params.healer_group_min_housing,
                    )
            });
            if target.is_none() {
                if unit.team == Team::Def {
                    eligible.retain(|ally| {
                        let ally = battle.unit(*ally);
                        ally.hp < ally.max_hp
                    });
                }
                eligible.sort_by(|a, b| {
                    let a = battle.unit(*a);
                    let b = battle.unit(*b);
                    geom::dist(u.x, u.y, a.x, a.y).total_cmp(&geom::dist(u.x, u.y, b.x, b.y))
                });
                target = eligible.iter().copied().find(|candidate| {
                    healer_grouped(
                        battle.unit(*candidate),
                        weighted,
                        battle.params.healer_group_radius,
                        battle.params.healer_group_min_housing,
                    )
                });
            }
            eligible.clear();
            eligible.extend(target);
        }
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
        recipients.extend(allies.iter().copied().filter(|ally| {
            let ally_unit = battle.unit(*ally);
            heal_eligible(battle, unit, *ally, false)
                && geom::dist(a.x, a.y, ally_unit.x, ally_unit.y) <= splash
        }));
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
    if !heal_ready {
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
    let mut flight =
        geom::dist(u.x, u.y, target_unit.x, target_unit.y) / battle.params.healer_projectile_speed;
    let mut previous = target;
    for (index, ally) in recipients.iter().copied().enumerate() {
        let a = battle.unit(ally);
        if druid && index != 0 {
            let previous = battle.unit(previous);
            flight += geom::dist(previous.x, previous.y, a.x, a.y)
                / battle.params.healer_projectile_speed;
        }
        previous = ally;
        let amount = (if a.is_hero { hero_rate } else { rate }) * boost * effectiveness[index];
        let mut pending =
            Pending::new(t + flight, a.x, a.y, 0.0, 0.0, false, false, source.clone());
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
    let unit = battle
        .attackers_pool()
        .find(|u| u.alive && u.kind == Tag::Siege && name.is_none_or(|name| u.name == name))
        .map(Unit::reference);
    if let Some(unit) = unit {
        battle.kill(unit);
        true
    } else {
        false
    }
}
