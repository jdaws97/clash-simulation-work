//! Ports defense.py:139-159,500-1095,1114-1409.
//! Weapon setup comes from Python; weapon handles are owning BuildingIds.

use std::f64::consts::PI;

use crate::combat::SplashUnitsOptions;
use crate::geom::{dist, py_hypot};
use crate::labels::{Name, Tag};
use crate::state::{
    Battle, BuildingId, EntityRef, Field, Pending, PoisonConfig, Team, Unit, UnitRef,
    Weapon, WeaponTrigger,
};
use crate::stats::Level;
use crate::{effects, geom, spells, units};

// defense.py:17-57: access the original weapon across damage callbacks.
fn weapon(battle: &Battle, owner: BuildingId) -> &Weapon {
    battle
        .building(owner)
        .weapon
        .as_ref()
        .expect("defensive weapon")
}

// defense.py:17-57: mutate the weapon without detaching it from its owner.
fn weapon_mut(battle: &mut Battle, owner: BuildingId) -> &mut Weapon {
    battle
        .building_mut(owner)
        .weapon
        .as_mut()
        .expect("defensive weapon")
}

// defense.py:104-142: static lookup values, including the explicit 100 entries.
pub fn group_weight(unit: &Unit) -> i64 {
    match unit.name_id {
        Name::AzureDragon => 5000,
        Name::Kane => 6000,
        Name::SuperDragon | Name::TheDisarmer | Name::WitchGolem => 4000,
        Name::SuperYeti => 3500,
        Name::GiantGiant => 3400,
        Name::ElectroTitan | Name::Golem | Name::LavaHound | Name::MeteorGolem => 3000,
        Name::BarbarianKing | Name::DragonDuke | Name::DragonRider | Name::MinionPrince
        | Name::SuperBowler | Name::SuperWitch | Name::Yeeter => 2500,
        Name::SuperMiner => 2400,
        Name::BroomWitch | Name::Dragon | Name::ElectroDragon | Name::GiantSkeleton
        | Name::Pekka | Name::RootRider => 2000,
        Name::Furnace | Name::IceHound | Name::Yeti => 1800,
        Name::Bear | Name::Druid => 1600,
        Name::InfernoDragon | Name::Lavaloon | Name::Meteormite | Name::SuperValkyrie => 1500,
        Name::SuperHogRider => 1200,
        Name::BabyDragon | Name::Cookie | Name::Mecha | Name::RamRider | Name::RoyalChampion
        | Name::SuperMinion | Name::SuperWizard => 1000,
        Name::BigBoy | Name::Firecracker | Name::Henchman | Name::SuperGiant => 800,
        Name::Thrower => 700,
        Name::GiantThrower | Name::Golemite | Name::HogWizard | Name::SuperArcher => 600,
        Name::ArcherQueen | Name::Balloon | Name::BattleRam | Name::Bowler | Name::Giant | Name::GrandWarden
        | Name::HogRider | Name::IceGolem | Name::Miner | Name::RocketBalloon | Name::SkeletonBarrel
        | Name::SnakeBarrel | Name::SuperHog | Name::SuperRider | Name::Valkyrie => 500,
        Name::BarbarianKicker | Name::SuperBarbarian => 400,
        Name::Booger => 300,
        Name::Barcher | Name::IceWizard | Name::PartyWizard | Name::SneakyGoblin | Name::Witch
        | Name::Wizard => 200,
        Name::DebtCollector | Name::Electromite | Name::Firemite | Name::Goblin | Name::SuperWallBreaker
        | Name::WallBreaker | Name::Yetimite => 50,
        Name::Healer => 30,
        Name::PhoenixEgg => 0,
        Name::ApprenticeWarden | Name::Archer | Name::Barbarian | Name::Bat | Name::BattleBlimp
        | Name::BattleDrill | Name::FlameFlinger | Name::Frostmite | Name::Headhunter | Name::IceMinion
        | Name::IcePup | Name::LavaPup | Name::LogLauncher | Name::Minion | Name::PumpkinBarbarian
        | Name::RoyalGhost | Name::SiegeBarracks | Name::Skeleton | Name::Snake | Name::SpellSkeleton
        | Name::StoneSlammer | Name::Totem | Name::TroopLauncher | Name::WallWrecker => 100,
        _ => {
            if unit.kind == Tag::Pet {
                return 400;
            }
            100
        }
    }
}

// defense.py:145-159: max keeps the first equal (score, negative distance).
pub fn eagle_pick(battle: &Battle, owner: BuildingId, pool: &[UnitRef]) -> UnitRef {
    let building = battle.building(owner);
    let mut best = None;
    let mut best_score = 0;
    let mut best_distance = 0.0;
    for &reference in pool {
        let unit = battle.unit(reference);
        let score: i64 = battle
            .attackers_near_iter(unit.x, unit.y, 5.0)
            .filter_map(|other| {
                let other = battle.unit(other);
                (other.targetable(battle) && dist(other.x, other.y, unit.x, unit.y) <= 5.0)
                    .then(|| group_weight(other))
            })
            .sum();
        let distance = dist(unit.x, unit.y, building.x, building.y);
        if best.is_none()
            || score > best_score
            || score == best_score && distance < best_distance
        {
            best = Some(reference);
            best_score = score;
            best_distance = distance;
        }
    }
    best.expect("Eagle target pool is nonempty")
}

// defense.py:500-517.
pub fn reveal_tesla(battle: &mut Battle, owner: BuildingId) {
    let building = battle.building(owner);
    if building.revealed || !building.alive {
        return;
    }
    battle.building_mut(owner).revealed = true;
    for unit in battle.attackers.iter_mut().filter(|unit| unit.in_pool) {
        unit.target = None;
        unit.wall_target = None;
        unit.target_kind = None;
        unit.extra.next_engage = 0.0;
    }
    for index in 0..battle.fields.len() {
        let field = &battle.fields[index];
        if !(field.started <= battle.t && battle.t < field.until) {
            continue;
        }
        if battle.building(owner).edge_distance(field.x, field.y) > field.radius {
            continue;
        }
        let until = field.until;
        match field.kind {
            Tag::TeslaFreeze => {
                let building = battle.building_mut(owner);
                building.frozen_until = building.frozen_until.max(until);
            }
            Tag::TeslaOvergrowth => {
                let building = battle.building_mut(owner);
                building.overgrown_until = building.overgrown_until.max(until);
            }
            _ => {}
        }
    }
}

// defense.py:520-571: explicitly tag death impacts; tower cast retains context.
pub fn on_destroyed(battle: &mut Battle, owner: BuildingId) {
    if battle.building(owner).name_id == Name::HeroBell {
        bell_tick(battle);
    }
    let building = battle.building(owner);
    if building.weapon.is_none() || building.extra.unavailable {
        return;
    }
    if weapon(battle, owner).kind == Tag::SpellTower && weapon(battle, owner).cooldown <= 0.0 {
        let near = tower_candidates(battle, owner);
        let mode = weapon(battle, owner).mode.clone().expect("Spell Tower mode");
        spells::tower_cast(battle, owner, &mode, Some(&near));
        let weapon = weapon_mut(battle, owner);
        weapon.cooldown = if matches!(mode.as_str(), "rage" | "poison") {
            70.0
        } else {
            50.0
        };
        weapon.extra.trigger = None;
    }
    let building = battle.building(owner);
    let w = weapon(battle, owner);
    let mut pending = if w.kind == Tag::GigaInferno {
        let mut pending = Pending::new(
            battle.t + 1.0,
            building.x,
            building.y,
            w.extra.death_radius,
            w.extra.death,
            true,
            true,
            "th_death",
        );
        pending.extra.poison = Some(PoisonConfig {
            dps: w.extra.poison_dps,
            time: Some(w.extra.poison_time),
            slow: Some(w.extra.slow),
            radius: Some(w.extra.death_radius),
            atk: None,
            ramp: false,
            hero_mult: 1.0,
            unknown: Vec::new(),
        });
        pending
    } else if building.key == "bt" {
        Pending::new(
            battle.t + w.extra.death_delay,
            building.x,
            building.y,
            w.extra.death_radius,
            w.extra.death,
            false,
            true,
            "bt_death",
        )
    } else {
        return;
    };
    pending.actor = Some(EntityRef::Building(owner));
    pending.effect = Some(Tag::Death);
    battle.add_pending(pending);
}

// defense.py:574-590: the bucket helper already applies the outer radius.
pub fn visible(battle: &Battle, owner: BuildingId, radius: f64) -> Vec<UnitRef> {
    let building = battle.building(owner);
    let w = weapon(battle, owner);
    let mut out = Vec::new();
    for reference in battle.attackers_near_iter(building.x, building.y, radius) {
        let unit = battle.unit(reference);
        if !unit.targetable(battle) {
            continue;
        }
        if unit.name_id != Name::Totem {
            if unit.flying {
                if w.targets == Tag::Ground {
                    continue;
                }
            } else if w.targets == Tag::Air {
                continue;
            }
        }
        if w.min_range != 0.0 && dist(unit.x, unit.y, building.x, building.y) < w.min_range {
            continue;
        }
        out.push(reference);
    }
    out
}

// defense.py:593-598.
pub fn rage(battle: &Battle, owner: BuildingId) -> f64 {
    let building = battle.building(owner);
    if battle.t < building.rage_until {
        building.rage_mult
    } else {
        1.0
    }
}

// defense.py:597-598.
pub fn slow(battle: &Battle, owner: BuildingId) -> f64 {
    effects::building_slow_mult(battle.building(owner), battle.t)
}

// defense.py:601-633: carry cooldown remainders through up to twelve cycles.
pub fn act(battle: &mut Battle, owner: BuildingId) {
    let t = battle.t;
    let dt = battle.dt;
    let building = battle.building(owner);
    let w = weapon(battle, owner);
    if w.kind == Tag::BhRepairOnly {
        return;
    }
    if building.key == "tesla" && !building.revealed {
        let Some(WeaponTrigger::Radius(radius)) = w.extra.trigger.as_ref() else {
            panic!("Hidden Tesla trigger radius");
        };
        if battle
            .attackers_near_iter(building.x, building.y, *radius)
            .any(|unit| {
                let unit = battle.unit(unit);
                unit.name_id != Name::Totem && !unit.underground
            })
        {
            reveal_tesla(battle, owner);
        } else {
            return;
        }
    }
    let building = battle.building(owner);
    if building.extra.unavailable || weapon(battle, owner).ammunition == Some(0) {
        return;
    }
    if t < building.stun_until && weapon(battle, owner).kind == Tag::Monolith {
        weapon_mut(battle, owner).target = None;
    }
    if battle.building(owner).disabled(t) {
        let w = weapon_mut(battle, owner);
        w.lock_time = 0.0;
        if w.kind != Tag::Eagle {
            w.burst_left = 0;
        }
        return;
    }
    if weapon(battle, owner).kind == Tag::GigaInferno && !battle.th_active() {
        return;
    }
    let cooldown = (weapon(battle, owner).cooldown - dt * slow(battle, owner)).max(-dt);
    weapon_mut(battle, owner).cooldown = cooldown;
    for _ in 0..12 {
        let before = weapon(battle, owner).cooldown;
        act_once(battle, owner);
        let w = weapon(battle, owner);
        if w.ammunition == Some(0) || w.cooldown > 0.0 || w.cooldown == before {
            break;
        }
    }
}

// defense.py:636-807: one complete firing cycle for every weapon family.
pub fn act_once(battle: &mut Battle, owner: BuildingId) {
    let t = battle.t;
    let dt = battle.dt;
    let w = weapon(battle, owner).clone();
    let (bx, by) = battle.entity_position(EntityRef::Building(owner));
    let kind = &w.kind;
    if kind == &Tag::Hook {
        if w.cooldown > 0.0 {
            return;
        }
        let candidates = visible(battle, owner, w.range);
        let Some(target) = nearest(battle, &candidates, bx, by) else {
            return;
        };
        battle.hit_unit(target, w.damage, None, "normal", None);
        let unit = battle.unit_mut(target);
        unit.stun_until = unit.stun_until.max(t + w.extra.stun);
        weapon_mut(battle, owner).cooldown += w.interval;
        return;
    }
    match kind {
        Tag::Eagle => return eagle(battle, owner),
        Tag::Sweeper => return sweeper(battle, owner),
        Tag::SpellTower => return spell_tower(battle, owner),
        _ => {}
    }
    let damage_rage = rage(battle, owner);
    match kind {
        Tag::Candle => {
            if let Some(first) = battle.first_deploy_t {
                let active = battle.t - first;
                weapon_mut(battle, owner).extra.targets = if active < w.extra.melt1 {
                    6
                } else if active < w.extra.melt2 {
                    4
                } else {
                    3
                };
            }
            return multi(battle, owner, damage_rage);
        }
        Tag::Cake => return cake(battle, owner, damage_rage),
        Tag::MultiArcher | Tag::InfernoMulti | Tag::GigaInferno => {
            return multi(battle, owner, damage_rage);
        }
        Tag::InfernoArtillery => return inferno_artillery(battle, owner, damage_rage),
        Tag::SuperWizard => return super_wizard(battle, owner, damage_rage),
        Tag::Firespitter => return firespitter(battle, owner, damage_rage),
        _ => {}
    }
    let mut target = w.target;
    if let Some(reference) = target {
        let unit = battle.unit(reference);
        let distance = dist(unit.x, unit.y, bx, by);
        if !unit.alive
            || !unit.targetable(battle)
            || distance > w.range
            || distance < w.min_range
        {
            target = None;
            weapon_mut(battle, owner).lock_time = 0.0;
        }
    }
    if target.is_none() {
        if t < w.idle_until {
            return;
        }
        let mut pool = visible(battle, owner, w.range);
        if pool.is_empty() {
            weapon_mut(battle, owner).idle_until = t + 0.25;
            return;
        }
        if kind == &Tag::Hunter && pool.iter().any(|unit| battle.unit(*unit).is_hero) {
            pool.retain(|unit| battle.unit(*unit).is_hero);
        }
        target = nearest(battle, &pool, bx, by);
        let actual = weapon_mut(battle, owner);
        actual.target = target;
        actual.lock_time = 0.0;
    }
    let target = target.expect("single-target defense target");
    if kind == &Tag::InfernoSingle {
        weapon_mut(battle, owner).lock_time += dt;
        let mut dps = 0.0;
        for &(start, value) in &w.extra.ramp {
            if weapon(battle, owner).lock_time >= start {
                dps = value;
            }
        }
        let mut duration = dt * slow(battle, owner);
        if let Some(ammunition) = w.ammunition {
            duration = duration.min(ammunition as f64 * w.interval - w.ammo_time);
        }
        battle.hit_unit(target, dps * duration * damage_rage, None, "normal", None);
        let actual = weapon_mut(battle, owner);
        actual.ammo_time += duration;
        while actual.ammo_time + 1e-9 >= actual.interval {
            actual.ammo_time -= actual.interval;
            *actual.ammunition.as_mut().expect("Inferno Tower ammunition") -= 1;
        }
        return;
    }
    if weapon(battle, owner).cooldown > 0.0 {
        return;
    }
    if kind == &Tag::Burst {
        if weapon(battle, owner).burst_left <= 0 {
            weapon_mut(battle, owner).burst_left = w.extra.shots as i64;
        }
        if battle.building(owner).key == "mgt" {
            projectile(battle, owner, target, w.damage * damage_rage, 12.0, 0.0);
        } else {
            battle.hit_unit(target, w.damage * damage_rage, None, "normal", None);
        }
        let actual = weapon_mut(battle, owner);
        actual.burst_left -= 1;
        actual.cooldown += if actual.burst_left > 0 {
            actual.extra.gap
        } else {
            actual.interval
        };
        return;
    }
    if kind == &Tag::MortarBurst {
        if weapon(battle, owner).burst_left <= 0 {
            weapon_mut(battle, owner).burst_left = w.extra.shots as i64;
        }
        mortar_shell(battle, owner, target, w.damage * damage_rage);
        let actual = weapon_mut(battle, owner);
        actual.burst_left -= 1;
        actual.cooldown += if actual.burst_left != 0 {
            actual.extra.gap
        } else {
            actual.interval
        };
        return;
    }
    if kind == &Tag::Revenge {
        revenge(battle, owner, target, damage_rage);
        return;
    }
    let actual = weapon_mut(battle, owner);
    actual.cooldown += actual.interval;
    if let Some(ammunition) = &mut actual.ammunition {
        *ammunition -= 1;
    }
    let damage = w.damage * damage_rage;
    match kind {
        Tag::Single => match battle.building(owner).key.as_str() {
            "cannon" => projectile(battle, owner, target, damage, 12.0, 0.0),
            "at" => projectile(battle, owner, target, damage, 18.0, 0.0),
            "ad" => projectile(battle, owner, target, damage, 8.0, 0.0),
            _ => {
                battle.hit_unit(target, damage, None, "normal", None);
            }
        },
        Tag::Monolith => {
            let amount = damage + w.extra.pct * battle.unit(target).max_hp / battle.def_mult;
            battle.hit_unit(target, amount, None, "normal", None);
        }
        Tag::Ricochet => {
            battle.hit_unit(target, damage, None, "normal", None);
            let (tx, ty) = battle.entity_position(EntityRef::Unit(target));
            let mut best = None;
            let mut best_distance = w.extra.bounce_range;
            for reference in battle.attackers_near_iter(tx, ty, best_distance) {
                let unit = battle.unit(reference);
                if reference != target && !unit.flying && unit.indirect_targetable(battle) {
                    let distance = dist(unit.x, unit.y, tx, ty);
                    if distance <= best_distance {
                        best_distance = distance;
                        best = Some(reference);
                    }
                }
            }
            if let Some(best) = best {
                battle.hit_unit(best, w.extra.bounce * damage_rage, None, "normal", None);
            }
        }
        Tag::Splash => {
            let unit = battle.unit(target);
            let (tx, ty) = (unit.x, unit.y);
            let air = if w.extra.same_type {
                unit.flying
            } else {
                matches!(w.targets, Tag::Air | Tag::Both)
            };
            let ground = if w.extra.same_type {
                !unit.flying
            } else {
                matches!(w.targets, Tag::Ground | Tag::Both)
            };
            let building = battle.building(owner);
            if building.key == "wt"
                && matches!(building.level.as_ref(), Some(Level::Int(level)) if *level <= 4)
            {
                let flight = dist(bx, by, tx, ty) / 5.0;
                battle.add_pending(Pending::new(
                    t + flight,
                    tx,
                    ty,
                    w.extra.splash,
                    damage,
                    air,
                    ground,
                    "wizard_tower",
                ));
            } else if building.key == "bt" {
                battle.add_pending(Pending::new(
                    t + dist(bx, by, tx, ty) / 8.0,
                    tx,
                    ty,
                    w.extra.splash,
                    damage,
                    air,
                    ground,
                    "bt",
                ));
            } else {
                battle.splash_units(
                    tx,
                    ty,
                    w.extra.splash,
                    damage,
                    air,
                    ground,
                    SplashUnitsOptions::default(),
                );
            }
        }
        Tag::Mortar => mortar_shell(battle, owner, target, damage),
        Tag::Scatter => scatter(battle, owner, target, damage, damage_rage),
        Tag::Hunter => hunter_hit(battle, owner, target, damage_rage),
        _ => {}
    }
}

// defense.py:646,697,904: Python min keeps the first equal-distance unit.
fn nearest(battle: &Battle, pool: &[UnitRef], x: f64, y: f64) -> Option<UnitRef> {
    let mut best = None;
    let mut best_distance = 0.0;
    for &reference in pool {
        let unit = battle.unit(reference);
        let distance = dist(unit.x, unit.y, x, y);
        if best.is_none() || distance < best_distance {
            best = Some(reference);
            best_distance = distance;
        }
    }
    best
}

// defense.py:810-825.
pub fn projectile(
    battle: &mut Battle,
    owner: BuildingId,
    target: UnitRef,
    damage: f64,
    speed: f64,
    offset: f64,
) {
    let building = battle.building(owner);
    let unit = battle.unit(target);
    let flight = 0.0_f64.max(dist(building.x, building.y, unit.x, unit.y) - offset) / speed;
    let mut pending = Pending::new(
        battle.t + flight,
        unit.x,
        unit.y,
        0.0,
        damage,
        unit.flying,
        !unit.flying,
        building.source.clone(),
    );
    pending.extra.direct = true;
    pending.target = Some(EntityRef::Unit(target));
    battle.add_pending(pending);
}

// defense.py:828-842.
pub fn mortar_shell(battle: &mut Battle, owner: BuildingId, target: UnitRef, damage: f64) {
    let building = battle.building(owner);
    let w = weapon(battle, owner);
    let unit = battle.unit(target);
    let mut pending = Pending::new(
        battle.t + w.extra.flight,
        unit.x,
        unit.y,
        w.extra.splash,
        damage,
        false,
        true,
        "mortar",
    );
    pending.falloff = true;
    pending.extra.origin = Some((building.x, building.y));
    battle.add_pending(pending);
}

// defense.py:845-894: stable sort and retained list mutation both matter.
pub fn multi(battle: &mut Battle, owner: BuildingId, damage_rage: f64) {
    let w = weapon(battle, owner).clone();
    if w.cooldown > 0.0 {
        return;
    }
    let (bx, by) = battle.entity_position(EntityRef::Building(owner));
    let count = if w.kind == Tag::MultiArcher {
        3
    } else {
        w.extra.targets
    };
    let mut keep = if w.kind == Tag::Candle {
        let mut pool = visible(battle, owner, w.range);
        sort_concentrated(battle, &mut pool, bx, by);
        pool.truncate(count);
        pool
    } else {
        w.multi
            .iter()
            .copied()
            .filter(|reference| {
                let unit = battle.unit(*reference);
                unit.alive
                    && unit.targetable(battle)
                    && dist(unit.x, unit.y, bx, by) <= w.range
            })
            .collect::<Vec<_>>()
    };
    if keep.len() < count {
        let mut pool = visible(battle, owner, w.range);
        pool.sort_by(|a, b| {
            let a = battle.unit(*a);
            let b = battle.unit(*b);
            dist(a.x, a.y, bx, by)
                .partial_cmp(&dist(b.x, b.y, bx, by))
                .expect("finite distance")
        });
        for reference in pool {
            if !keep.contains(&reference) {
                keep.push(reference);
                if keep.len() >= count {
                    break;
                }
            }
        }
    }
    weapon_mut(battle, owner).multi = keep.clone().into();
    if keep.is_empty() {
        return;
    }
    if matches!(w.kind, Tag::MultiArcher | Tag::Candle) {
        sort_concentrated(battle, &mut keep, bx, by);
        weapon_mut(battle, owner).multi = keep.clone().into();
        // keep and count are the same immutable snapshot previously used to
        // build arrows; callbacks cannot change this local cycling order.
        for index in 0..count {
            let reference = keep[index % keep.len()];
            if w.kind == Tag::MultiArcher {
                projectile(battle, owner, reference, w.damage * damage_rage, 18.0, 0.0);
            } else {
                battle.hit_unit(reference, w.damage * damage_rage, None, "normal", None);
            }
        }
        weapon_mut(battle, owner).cooldown += w.interval;
        return;
    }
    let damage = w.damage * damage_rage;
    if let Some(ammunition) = &mut weapon_mut(battle, owner).ammunition {
        *ammunition -= 1;
    }
    for reference in keep {
        battle.hit_unit(reference, damage, None, "normal", None);
    }
    weapon_mut(battle, owner).cooldown += w.interval;
}

// defense.py:858-860,881: exact (distance, spawned_at, id) tuple ordering.
fn sort_concentrated(battle: &Battle, pool: &mut [UnitRef], x: f64, y: f64) {
    pool.sort_by(|a, b| {
        let a = battle.unit(*a);
        let b = battle.unit(*b);
        dist(a.x, a.y, x, y)
            .partial_cmp(&dist(b.x, b.y, x, y))
            .expect("finite distance")
            .then_with(|| {
                a.spawned_at
                    .partial_cmp(&b.spawned_at)
                    .expect("finite spawn time")
            })
            .then_with(|| a.id.0.cmp(&b.id.0))
    });
}

// defense.py:897-907.
pub fn cake(battle: &mut Battle, owner: BuildingId, damage_rage: f64) {
    let w = weapon(battle, owner).clone();
    if w.cooldown > 0.0 {
        return;
    }
    let (bx, by) = battle.entity_position(EntityRef::Building(owner));
    let pool = visible(battle, owner, w.range);
    let Some(target) = nearest(battle, &pool, bx, by) else {
        return;
    };
    let unit = battle.unit(target);
    let (x, y, flying) = (unit.x, unit.y, unit.flying);
    battle.splash_units(
        x,
        y,
        w.extra.splash,
        w.damage * damage_rage,
        flying,
        !flying,
        SplashUnitsOptions::default(),
    );
    // The target may move in a damage callback; Python reads it again here.
    let (x, y) = battle.entity_position(EntityRef::Unit(target));
    battle.add_pending(Pending::new(
        battle.t + w.extra.bomb_delay,
        x,
        y,
        w.extra.bomb_radius,
        w.extra.bomb * damage_rage,
        true,
        true,
        "cake",
    ));
    weapon_mut(battle, owner).cooldown += w.interval;
}

// defense.py:910-919.
pub fn hunter_hit(battle: &mut Battle, owner: BuildingId, target: UnitRef, damage_rage: f64) {
    let w = weapon(battle, owner).clone();
    let multiplier = if battle.unit(target).is_hero { 2.0 } else { 1.0 };
    battle.hit_unit(target, w.damage * damage_rage * multiplier, None, "normal", None);
    let level = Level::Int(w.extra.poison_level as i64);
    let movement = battle
        .catalog
        .stats
        .get("Poison Spell", &level, &["Speed Decrease"], Some(50.0))
        .expect("Poison Spell movement slow")
        / 100.0;
    let attack = battle
        .catalog
        .stats
        .get("Poison Spell", &level, &["Attack Rate Decrease"], Some(70.0))
        .expect("Poison Spell attack slow")
        / 100.0;
    let t = battle.t;
    let unit = battle.unit_mut(target);
    let previous_movement = if t < unit.move_slow_until {
        unit.move_slow
    } else {
        1.0
    };
    unit.move_slow = previous_movement.min(1.0 - movement);
    unit.move_slow_until = t + w.extra.poison_time;
    let previous_attack = if t < unit.atk_slow_until {
        unit.atk_slow
    } else {
        1.0
    };
    unit.atk_slow = previous_attack.min(1.0 - attack);
    unit.atk_slow_until = t + w.extra.poison_time;
}

// defense.py:922-948: native atan2, Python positive-divisor modulo.
pub fn scatter(
    battle: &mut Battle,
    owner: BuildingId,
    target: UnitRef,
    damage: f64,
    damage_rage: f64,
) {
    let w = weapon(battle, owner).clone();
    battle.hit_unit(target, damage, None, "normal", None);
    let (bx, by) = battle.entity_position(EntityRef::Building(owner));
    let (tx, ty) = battle.entity_position(EntityRef::Unit(target));
    let angle = geom::py_atan2(ty - by, tx - bx);
    let splash_max = w.extra.splash_max * damage_rage;
    let splash_min = w.extra.splash_min * damage_rage;
    let inner_min = w.extra.inner_min.unwrap_or(w.extra.splash_max) * damage_rage;
    for reference in battle.attackers_near(tx, ty, 5.0) {
        let unit = battle.unit(reference);
        if reference == target
            || unit.flying != battle.unit(target).flying
            || !unit.alive
            || unit.underground
        {
            continue;
        }
        let (tx, ty) = battle.entity_position(EntityRef::Unit(target));
        let (dx, dy) = (unit.x - tx, unit.y - ty);
        let distance = py_hypot(dx, dy);
        if distance > 1e-6 {
            let offset = ((geom::py_atan2(dy, dx) - angle + PI).rem_euclid(2.0 * PI) - PI).abs();
            if offset > PI / 4.0 {
                continue;
            }
        }
        let amount = if distance <= 1.0 {
            damage - (damage - inner_min) * distance
        } else {
            splash_max - (splash_max - splash_min) * (distance - 1.0) / 4.0
        };
        battle.hit_unit(reference, amount, None, "normal", None);
    }
}

// defense.py:951-1009: wake once, choose per volley, launch only this shell pair.
pub fn eagle(battle: &mut Battle, owner: BuildingId) {
    let w = weapon(battle, owner);
    if battle.deployed_housing < w.extra.activation as i64 || w.cooldown > 0.0 {
        return;
    }
    let t = battle.t;
    let ready_at = *weapon_mut(battle, owner)
        .extra
        .wake_at
        .get_or_insert(t + 1.125);
    if battle.t < ready_at {
        return;
    }
    if weapon(battle, owner).burst_left <= 0 {
        let range = weapon(battle, owner).range;
        let pool: Vec<_> = visible(battle, owner, range)
            .into_iter()
            .filter(|unit| battle.unit(*unit).name_id != Name::Yetimite)
            .collect();
        if pool.is_empty() {
            return;
        }
        let target = eagle_pick(battle, owner, &pool);
        let w = weapon_mut(battle, owner);
        w.target = Some(target);
        w.burst_left = w.extra.shells as i64;
    }
    let mut target = weapon(battle, owner).target;
    if target.map_or(true, |unit| !battle.unit(unit).alive) {
        let range = weapon(battle, owner).range;
        let pool: Vec<_> = visible(battle, owner, range)
            .into_iter()
            .filter(|unit| battle.unit(*unit).name_id != Name::Yetimite)
            .collect();
        if pool.is_empty() {
            weapon_mut(battle, owner).burst_left = 0;
            return;
        }
        target = Some(eagle_pick(battle, owner, &pool));
        weapon_mut(battle, owner).target = target;
    }
    let target = target.expect("Eagle shell target");
    let w = weapon(battle, owner).clone();
    let (bx, by) = battle.entity_position(EntityRef::Building(owner));
    for (radius, damage, shock) in [
        (w.extra.splash, w.damage - w.extra.shock, false),
        (w.extra.shock_radius, w.extra.shock, true),
    ] {
        let (x, y) = battle.entity_position(EntityRef::Unit(target));
        let mut pending = Pending::new(
            battle.t + 5.0,
            x,
            y,
            radius,
            damage * rage(battle, owner),
            true,
            true,
            "eagle",
        );
        pending.extra.track = Some(EntityRef::Unit(target));
        pending.extra.origin = Some((bx, by));
        pending.extra.min_range = w.min_range;
        pending.extra.max_range = w.range;
        pending.extra.push = if shock {
            0.5
        } else {
            0.0
        };
        pending.extra.push_housing = 3.0;
        battle.add_pending(pending);
    }
    let actual = weapon_mut(battle, owner);
    if let Some(ammunition) = &mut actual.ammunition {
        *ammunition -= 1;
    }
    actual.burst_left -= 1;
    actual.cooldown += if actual.burst_left != 0 {
        actual.extra.gap
    } else {
        actual.interval
    };
}

// defense.py:1012-1050: aim at the first nearest eligible flyer.
pub fn sweeper(battle: &mut Battle, owner: BuildingId) {
    let w = weapon(battle, owner).clone();
    if w.cooldown > 0.0 {
        return;
    }
    let (bx, by) = battle.entity_position(EntityRef::Building(owner));
    let mut aim = None;
    let mut best_distance = 0.0;
    for reference in battle.attackers_near(bx, by, w.range) {
        let unit = battle.unit(reference);
        if !unit.flying || unit.name_id == Name::Totem || !unit.targetable(battle) {
            continue;
        }
        let distance = dist(unit.x, unit.y, bx, by);
        if distance < w.min_range {
            continue;
        }
        let angle = geom::py_atan2(unit.y - by, unit.x - bx);
        if ((angle - w.facing + PI).rem_euclid(2.0 * PI) - PI).abs() <= PI / 4.0
            && (aim.is_none() || distance < best_distance)
        {
            aim = Some(angle);
            best_distance = distance;
        }
    }
    let Some(aim) = aim else {
        return;
    };
    for reference in battle.attackers_near(bx, by, w.range) {
        let unit = battle.unit(reference);
        if !unit.flying || unit.name_id == Name::Totem {
            continue;
        }
        let angle = geom::py_atan2(unit.y - by, unit.x - bx);
        if ((angle - aim + PI).rem_euclid(2.0 * PI) - PI).abs() <= 5.0 * (PI / 180.0) {
            battle.nudge(
                reference,
                geom::py_cos(angle) * w.extra.push,
                geom::py_sin(angle) * w.extra.push,
            );
            let t = battle.t;
            let unit = battle.unit_mut(reference);
            unit.extra.pushed_at = Some(t);
            units::reset_beam(unit);
        }
    }
    weapon_mut(battle, owner).cooldown += w.interval;
}

// defense.py:1053-1061.
pub fn tower_candidates(battle: &Battle, owner: BuildingId) -> Vec<UnitRef> {
    let w = weapon(battle, owner);
    visible(battle, owner, w.range)
        .into_iter()
        .filter(|reference| {
            let unit = battle.unit(*reference);
            !spells::NO_TRIGGER.contains(&unit.name_id)
                && (!matches!(w.mode.as_deref(), Some("eq" | "quake" | "earthquake"))
                    || !unit.flying)
        })
        .collect()
}

// defense.py:1064-1095: hit_triggers is an insertion-ordered Python dictionary.
pub fn spell_tower(battle: &mut Battle, owner: BuildingId) {
    let w = weapon(battle, owner).clone();
    if w.cooldown > 0.0 {
        return;
    }
    let t = battle.t;
    let (unit, since) = if w.mode.as_deref() == Some("invis") {
        let triggers: Vec<_> = w
            .extra
            .hit_triggers
            .iter()
            .copied()
            .filter(|(unit, _)| battle.unit(*unit).alive)
            .collect();
        weapon_mut(battle, owner).extra.hit_triggers = triggers.clone().into();
        let Some(&(mut unit, mut since)) = triggers.first() else {
            return;
        };
        for &(candidate, time) in &triggers[1..] {
            if time < since {
                unit = candidate;
                since = time;
            }
        }
        (unit, since)
    } else {
        let near = tower_candidates(battle, owner);
        let trigger = match w.extra.trigger {
            Some(WeaponTrigger::UnitSince(unit, since)) => Some((unit, since)),
            None => None,
            Some(WeaponTrigger::Radius(_)) => panic!("Spell Tower unit trigger"),
        };
        if trigger.map_or(true, |(unit, _)| !near.contains(&unit)) {
            weapon_mut(battle, owner).extra.trigger = near
                .first()
                .map(|unit| WeaponTrigger::UnitSince(*unit, t));
            return;
        }
        trigger.expect("continuous Spell Tower trigger")
    };
    if t - since < 1.2 {
        return;
    }
    let mode = w.mode.as_deref().expect("Spell Tower mode");
    spells::tower_cast(battle, owner, mode, Some(&[unit]));
    let actual = weapon_mut(battle, owner);
    actual.extra.trigger = None;
    actual.extra.hit_triggers.clear();
    actual.cooldown += if matches!(mode, "rage" | "poison") {
        70.0
    } else {
        50.0
    };
}

// defense.py:1114-1141.
pub fn builder_spell(battle: &mut Battle, field: &Field) {
    let t = battle.t;
    for index in 0..battle.builders.len() {
        let builder = &battle.builders[index];
        if !battle.building(builder.owner).alive {
            continue;
        }
        if dist(builder.x, builder.y, field.x, field.y) > field.radius {
            continue;
        }
        let builder = &mut battle.builders[index];
        match field.kind {
            Tag::TeslaFreeze => {
                builder.frozen_until = builder.frozen_until.max(field.until);
            }
            Tag::Freeze => {
                builder.frozen_until = builder.frozen_until.max(t + field.value);
            }
            Tag::Poison => {
                builder.repair_slow = 1.0 - field.extra.atk;
                builder.slow_until = field.until.min(t + battle.dt);
            }
            Tag::Lightning | Tag::Totem => {
                builder.target = None;
                let duration = if field.kind == Tag::Lightning { 0.1 } else { 0.2 };
                builder.stun_until = builder.stun_until.max(t + duration);
            }
            Tag::DefRage | Tag::Rage if field.kind == Tag::DefRage || field.team == Team::Def => {
                builder.repair_boost = 2.0;
                builder.rage_speed = field.extra.speed.unwrap_or(30.0 / 8.0);
                builder.rage_until = field.until.min(t + battle.dt);
            }
            _ => {}
        }
    }
}

// defense.py:1144-1204: groups retain first target occurrence and builder order.
pub fn builders_tick(battle: &mut Battle) {
    let mut groups: Vec<(BuildingId, Vec<(usize, f64)>)> = Vec::new();
    let t = battle.t;
    for index in 0..battle.builders.len() {
        let builder = battle.builders[index].clone();
        let building = battle.building(builder.owner);
        if !building.alive || building.extra.unavailable {
            continue;
        }
        let (bx, by) = (building.x, building.y);
        let repair_range = weapon(battle, builder.owner).extra.repair_range;
        let available = |id: BuildingId| {
            let other = battle.building(id);
            other.alive
                && other.counted
                && other.hp < other.max_hp
                && t >= other.invisible_until
                && t >= other.overgrown_until
                && dist(other.x, other.y, bx, by) <= repair_range
        };
        let mut target = builder.target;
        if target.map_or(true, |target| !available(target)) {
            target = None;
            let mut best_ratio = 0.0;
            for other in &battle.buildings {
                if available(other.id) {
                    let ratio = other.hp / other.max_hp;
                    if target.is_none() || ratio < best_ratio {
                        target = Some(other.id);
                        best_ratio = ratio;
                    }
                }
            }
            battle.builders[index].target = target;
        }
        let Some(target) = target else {
            continue;
        };
        if t < builder.frozen_until.max(builder.stun_until) {
            continue;
        }
        let mut speed = battle
            .catalog
            .stats
            .attrs(&battle.building(builder.owner).name)
            .at("speed_display")
            .f64()
            / 8.0;
        let boost = if t < builder.rage_until {
            builder.repair_boost
        } else {
            1.0
        };
        if t < builder.rage_until {
            speed += builder.rage_speed;
        }
        let (tx, ty) = battle.entity_position(EntityRef::Building(target));
        let distance = dist(builder.x, builder.y, tx, ty);
        if distance > 0.5 {
            let step = (speed * battle.dt).min(distance - 0.5);
            let actual = &mut battle.builders[index];
            actual.x += (tx - actual.x) * step / distance;
            actual.y += (ty - actual.y) * step / distance;
            if distance - step > 0.5 {
                continue;
            }
        }
        let slow = if t < builder.slow_until {
            builder.repair_slow
        } else {
            1.0
        };
        let actual = &mut battle.builders[index];
        actual.cooldown = (actual.cooldown - battle.dt * slow).max(-battle.dt);
        if let Some((_, builders)) = groups.iter_mut().find(|(id, _)| *id == target) {
            builders.push((index, boost));
        } else {
            groups.push((target, vec![(index, boost)]));
        }
    }
    for (target, builders) in groups {
        let weights = [1.0, 1.0, 0.9, 0.9, 0.7];
        let amounts: Vec<_> = builders
            .iter()
            .map(|(index, boost)| {
                let owner = battle.building(battle.builders[*index].owner);
                battle
                    .catalog
                    .stats
                    .get(
                        &owner.name,
                        owner.level.as_ref().expect("Builder's Hut level"),
                        &["Repair per Hit"],
                        None,
                    )
                    .expect("Builder's Hut repair per hit")
                    * boost
            })
            .collect();
        let efficiency = if amounts.iter().all(|amount| *amount == amounts[0]) {
            weights[..builders.len().min(weights.len())]
                .iter()
                .copied()
                .fold(0.0, |total, weight| total + weight)
                / builders.len() as f64
        } else {
            1.0
        };
        for ((index, _), amount) in builders.into_iter().zip(amounts) {
            if battle.builders[index].cooldown <= 0.0 {
                let target = battle.building_mut(target);
                target.hp = target.max_hp.min(target.hp + amount * efficiency);
                battle.builders[index].cooldown += 0.75;
            }
        }
    }
}

// defense.py:1207-1234: four projectiles, even when they share a target.
fn inferno_artillery(battle: &mut Battle, owner: BuildingId, damage_rage: f64) {
    let w = weapon(battle, owner).clone();
    if w.cooldown > 0.0 {
        return;
    }
    let (bx, by) = battle.entity_position(EntityRef::Building(owner));
    let mut pool = visible(battle, owner, w.range);
    pool.sort_by(|a, b| {
        let a = battle.unit(*a);
        let b = battle.unit(*b);
        dist(a.x, a.y, bx, by)
            .partial_cmp(&dist(b.x, b.y, bx, by))
            .expect("finite distance")
    });
    pool.truncate(w.extra.targets);
    if pool.is_empty() {
        return;
    }
    for index in 0..w.extra.targets {
        let target = pool[index % pool.len()];
        battle.hit_unit(target, w.damage * damage_rage, None, "normal", None);
        let (x, y) = battle.entity_position(EntityRef::Unit(target));
        let mut field = Field::new(
            "def_burn",
            x,
            y,
            w.extra.pool_radius,
            battle.t + w.extra.pool_time,
        );
        field.team = Team::Def;
        field.value = w.extra.pool_dps;
        field.extra.pulses = w.extra.pool_hits;
        field.extra.has_pulses = true;
        field.extra.gap = Some(w.extra.pool_gap);
        field.started = battle.t;
        battle.fields.push(field);
    }
    weapon_mut(battle, owner).cooldown += w.interval;
}

// defense.py:1236-1270: one choice draw on acquiring a target; every chain
// starts at the primary, with <= deliberately choosing the last equal unit.
fn super_wizard(battle: &mut Battle, owner: BuildingId, damage_rage: f64) {
    let w = weapon(battle, owner).clone();
    if w.cooldown > 0.0 {
        return;
    }
    let (bx, by) = battle.entity_position(EntityRef::Building(owner));
    let mut target = w.target;
    if let Some(reference) = target {
        let unit = battle.unit(reference);
        if !unit.alive || !unit.targetable(battle) || dist(unit.x, unit.y, bx, by) > w.range {
            target = None;
        }
    }
    if target.is_none() {
        let mut pool = visible(battle, owner, w.range);
        if pool.is_empty() {
            weapon_mut(battle, owner).target = None;
            return;
        }
        pool.sort_by_key(|unit| unit.id.0);
        let index = battle.rng_mut().below(pool.len());
        target = Some(pool[index]);
        weapon_mut(battle, owner).target = target;
    }
    let target = target.expect("Super Wizard Tower target");
    battle.hit_unit(target, w.damage * damage_rage, None, "normal", None);
    let mut hit = vec![target.id];
    for _ in 0..w.extra.chain {
        let mut next = None;
        let mut next_distance = w.extra.chain_range;
        let (tx, ty) = battle.entity_position(EntityRef::Unit(target));
        for reference in battle.attackers_near(tx, ty, next_distance) {
            let unit = battle.unit(reference);
            if !hit.contains(&unit.id) && unit.indirect_targetable(battle) {
                let distance = dist(unit.x, unit.y, tx, ty);
                if distance <= next_distance {
                    next_distance = distance;
                    next = Some(reference);
                }
            }
        }
        let Some(next) = next else {
            break;
        };
        hit.push(next.id);
        battle.hit_unit(next, w.extra.secondary * damage_rage, None, "normal", None);
    }
    weapon_mut(battle, owner).cooldown += w.interval;
}

// defense.py:1273-1334: native atan2 and Python modulo for sector tests.
fn firespitter(battle: &mut Battle, owner: BuildingId, damage_rage: f64) {
    let w = weapon(battle, owner).clone();
    if w.cooldown > 0.0 {
        return;
    }
    let (bx, by) = battle.entity_position(EntityRef::Building(owner));
    let mut target = w.target;
    let in_sector = target.is_some_and(|target| {
        let unit = battle.unit(target);
        ((geom::py_atan2(unit.y - by, unit.x - bx) - w.facing + PI).rem_euclid(2.0 * PI) - PI)
            .abs() <= w.extra.arc
    });
    if target.map_or(true, |target| {
        let unit = battle.unit(target);
        !unit.alive || !unit.targetable(battle) || dist(unit.x, unit.y, bx, by) > w.range
    }) || !in_sector
    {
        weapon_mut(battle, owner).burst_left = 0;
        let mut candidates = Vec::new();
        for reference in visible(battle, owner, w.range) {
            let unit = battle.unit(reference);
            let angle = geom::py_atan2(unit.y - by, unit.x - bx);
            if ((angle - w.facing + PI).rem_euclid(2.0 * PI) - PI).abs() <= w.extra.arc {
                candidates.push(reference);
            }
        }
        target = nearest(battle, &candidates, bx, by);
        if target.is_none() {
            return;
        }
        weapon_mut(battle, owner).target = target;
    }
    let target = target.expect("Firespitter target");
    if weapon(battle, owner).burst_left <= 0 {
        weapon_mut(battle, owner).burst_left = w.extra.shots as i64;
    }
    let unit = battle.unit(target);
    let length = dist(unit.x, unit.y, bx, by);
    let ux = (unit.x - bx) / length.max(1e-9);
    let uy = (unit.y - by) / length.max(1e-9);
    let mut path = vec![(length, target.id.0, target)];
    for reference in battle.attackers_near(bx, by, length + 2.0) {
        let unit = battle.unit(reference);
        if reference == target || !unit.indirect_targetable(battle) {
            continue;
        }
        let along = (unit.x - bx) * ux + (unit.y - by) * uy;
        if !(1.7 <= along && along <= length + 2.0) {
            continue;
        }
        if ((unit.x - bx) * uy - (unit.y - by) * ux).abs() > 0.5 {
            continue;
        }
        path.push((along, unit.id.0, reference));
    }
    path.sort_by(|a, b| {
        a.0.partial_cmp(&b.0)
            .expect("finite path distance")
            .then_with(|| a.1.cmp(&b.1))
    });
    for &(_, _, reference) in path.iter().take(2) {
        projectile(battle, owner, reference, w.damage * damage_rage, 20.0, 1.7);
    }
    let actual = weapon_mut(battle, owner);
    actual.burst_left -= 1;
    actual.cooldown += if actual.burst_left > 0 {
        actual.extra.gap
    } else {
        actual.interval
    };
}

// defense.py:1337-1370: next() selects the first eligible chain target.
fn revenge(battle: &mut Battle, owner: BuildingId, target: UnitRef, damage_rage: f64) {
    let destroyed = battle.destroyed_counted;
    if destroyed < 5 {
        return;
    }
    let stage = if destroyed >= 50 {
        3
    } else if destroyed >= 25 {
        2
    } else {
        1
    };
    if stage == 1 {
        let damage = weapon(battle, owner).damage * damage_rage;
        battle.hit_unit(target, damage, None, "normal", None);
        weapon_mut(battle, owner).cooldown += 1.2;
        return;
    }
    let columns = [
        "Damage per Shot (Primary)",
        "Damage per Shot (Secondary)",
        "Damage per Shot (Tertiary)",
    ];
    let mut current = target;
    let mut hit = vec![target.id];
    let building = battle.building(owner);
    let name = building.name.clone();
    let level = building.level.clone().expect("Revenge Tower level");
    let damage = battle
        .catalog
        .stats
        .get(&name, &level, &[columns[0]], None)
        .expect("Revenge Tower primary damage")
        * damage_rage;
    battle.hit_unit(target, damage, None, "normal", None);
    for column in &columns[1..stage] {
        let (x, y) = battle.entity_position(EntityRef::Unit(current));
        let next = battle
            .attackers_near_iter(x, y, 2.0)
            .find(|reference| {
                let unit = battle.unit(*reference);
                !hit.contains(&unit.id) && unit.indirect_targetable(battle)
            });
        let Some(next) = next else {
            break;
        };
        let damage = battle
            .catalog
            .stats
            .get(&name, &level, &[*column], None)
            .expect("Revenge Tower chain damage")
            * damage_rage;
        battle.hit_unit(next, damage, None, "normal", None);
        hit.push(next.id);
        current = next;
    }
    weapon_mut(battle, owner).cooldown += if stage == 2 {
        0.6
    } else {
        0.35
    };
}

// defense.py:1373-1409: health rescales immediately; damage lingers one second.
pub fn bell_tick(battle: &mut Battle) {
    let bells: Vec<_> = battle.buildings.iter().filter(|building| {
        building.alive && building.name_id == Name::HeroBell && battle.t >= 2.2
    }).map(|building| building.id).collect();
    let heroes: Vec<_> = battle.defenders_pool().filter(|hero| hero.alive && hero.is_hero)
        .map(Unit::reference).collect();
    for hero in heroes {
        let (mut damage_boost, mut health_boost) = (0.0_f64, 0.0_f64);
        for &bell in &bells {
            let building = battle.building(bell);
            let unit = battle.unit(hero);
            if dist(unit.x, unit.y, building.x, building.y)
                > battle.catalog.stats.attrs("Hero Bell").at("range").f64() {
                continue;
            }
            let level = building.level.as_ref().expect("Hero Bell level");
            let damage_level = battle.defense_levels.iter().find(|(key, _)| key == "crafting:damage")
                .map_or(level, |(_, level)| level);
            let health_level = battle.defense_levels.iter().find(|(key, _)| key == "crafting:health")
                .map_or(level, |(_, level)| level);
            damage_boost = damage_boost.max(battle.catalog.stats.get("Hero Bell", damage_level,
                &["Hero DPS Boost"], None).expect("Hero Bell damage boost") / 100.0);
            health_boost = health_boost.max(battle.catalog.stats.get("Hero Bell", health_level,
                &["Hero HP Boost"], None).expect("Hero Bell health boost") / 100.0);
        }
        let t = battle.t;
        let unit = battle.unit_mut(hero);
        let previous = unit.extra.bell_health;
        let multiplier = 1.0 + health_boost;
        unit.hp *= multiplier / previous;
        unit.max_hp *= multiplier / previous;
        unit.extra.bell_health = multiplier;
        if damage_boost != 0.0 {
            unit.extra.bell_damage = 1.0 + damage_boost;
            unit.extra.bell_damage_until = t + 1.0;
        } else if t >= unit.extra.bell_damage_until {
            unit.extra.bell_damage = 1.0;
        }
    }
}
