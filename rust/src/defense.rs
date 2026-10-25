//! Ports defense.py:139-159,500-1095,1114-1409.
//! Weapon setup comes from Python; weapon handles are owning BuildingIds.

use std::f64::consts::PI;

use crate::catalog::game_required_int;
use crate::combat::SplashUnitsOptions;
use crate::geom::{dist, py_hypot};
use crate::labels::{Name, Tag};
use crate::state::{
    Battle, BuildingId, EntityRef, Field, Pending, PoisonConfig, Team, Unit, UnitRef, Weapon,
    WeaponTrigger,
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
        Name::BarbarianKing
        | Name::DragonDuke
        | Name::DragonRider
        | Name::MinionPrince
        | Name::SuperBowler
        | Name::SuperWitch
        | Name::Yeeter => 2500,
        Name::SuperMiner => 2400,
        Name::BroomWitch
        | Name::Dragon
        | Name::ElectroDragon
        | Name::GiantSkeleton
        | Name::Pekka
        | Name::RootRider => 2000,
        Name::Furnace | Name::IceHound | Name::Yeti => 1800,
        Name::Bear | Name::Druid => 1600,
        Name::InfernoDragon | Name::Lavaloon | Name::Meteormite | Name::SuperValkyrie => 1500,
        Name::SuperHogRider => 1200,
        Name::BabyDragon
        | Name::Cookie
        | Name::Mecha
        | Name::RamRider
        | Name::RoyalChampion
        | Name::SuperMinion
        | Name::SuperWizard => 1000,
        Name::BigBoy | Name::Firecracker | Name::Henchman | Name::SuperGiant => 800,
        Name::Thrower => 700,
        Name::GiantThrower | Name::Golemite | Name::HogWizard | Name::SuperArcher => 600,
        Name::ArcherQueen
        | Name::Balloon
        | Name::BattleRam
        | Name::Bowler
        | Name::Giant
        | Name::GrandWarden
        | Name::HogRider
        | Name::IceGolem
        | Name::Miner
        | Name::RocketBalloon
        | Name::SkeletonBarrel
        | Name::SnakeBarrel
        | Name::SuperHog
        | Name::SuperRider
        | Name::Valkyrie => 500,
        Name::BarbarianKicker | Name::SuperBarbarian => 400,
        Name::Booger => 300,
        Name::Barcher
        | Name::IceWizard
        | Name::PartyWizard
        | Name::SneakyGoblin
        | Name::Witch
        | Name::Wizard => 200,
        Name::DebtCollector
        | Name::Electromite
        | Name::Firemite
        | Name::Goblin
        | Name::SuperWallBreaker
        | Name::WallBreaker
        | Name::Yetimite => 50,
        Name::Healer => 30,
        Name::PhoenixEgg => 0,
        Name::ApprenticeWarden
        | Name::Archer
        | Name::Barbarian
        | Name::Bat
        | Name::BattleBlimp
        | Name::BattleDrill
        | Name::FlameFlinger
        | Name::Frostmite
        | Name::Headhunter
        | Name::IceMinion
        | Name::IcePup
        | Name::LavaPup
        | Name::LogLauncher
        | Name::Minion
        | Name::PumpkinBarbarian
        | Name::RoyalGhost
        | Name::SiegeBarracks
        | Name::Skeleton
        | Name::Snake
        | Name::SpellSkeleton
        | Name::StoneSlammer
        | Name::Totem
        | Name::TroopLauncher
        | Name::WallWrecker => 100,
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
        let score: i64 = ordered_attackers_near(battle, unit.x, unit.y, 5.0)
            .into_iter()
            .filter_map(|other| {
                let other = battle.unit(other);
                (other.targetable(battle) && dist(other.x, other.y, unit.x, unit.y) <= 5.0)
                    .then(|| group_weight(other))
            })
            .sum();
        let distance = dist(unit.x, unit.y, building.x, building.y);
        if best.is_none() || score > best_score || score == best_score && distance < best_distance {
            best = Some(reference);
            best_score = score;
            best_distance = distance;
        }
    }
    best.expect("Eagle target pool is nonempty")
}

fn tesla_target_priority(battle: &Battle, pref: &Tag, target: EntityRef) -> i32 {
    let EntityRef::Building(owner) = target else {
        return 0;
    };
    let building = battle.building(owner);
    if *pref == Tag::AirDefense && building.key == "ad" {
        return 2;
    }
    if matches!(pref, Tag::Defense | Tag::AirDefense) {
        return i32::from(battle.is_defense_target(owner));
    }
    if *pref == Tag::Resource {
        return i32::from(building.resource_target);
    }
    0
}

// defense.py:_tesla_keeps_target: compare preference before edge distance.
fn tesla_keeps_target(battle: &mut Battle, reference: UnitRef) -> bool {
    let unit = battle.unit(reference);
    if !unit.flying {
        return false;
    }
    let Some(current) = unit.target else {
        return false;
    };
    if unit.target_kind == Some(Tag::Destination) {
        return true;
    }
    if !battle.entity_alive(current) {
        return false;
    }
    if let EntityRef::Unit(target) = current {
        if matches!(unit.spec.attack, Tag::Heal | Tag::HealChain) {
            return true;
        }
        if !battle.unit(target).targetable(battle) || battle.t < unit.extra.angry_until {
            return false;
        }
        let retaliation = matches!(unit.name_id, Name::RoyalChampion | Name::GiantGiant)
            || unit
                .pet
                .is_some_and(|pet| battle.unit(pet).attached(battle));
        let preferred = match &unit.spec.prefer {
            Tag::Wall => battle.walls.iter().any(|wall| wall.alive),
            Tag::Defense | Tag::AirDefense => battle.buildings.iter().any(|building| {
                building.targetable(battle.t) && battle.is_defense_target(building.id)
            }),
            Tag::Resource => battle
                .buildings
                .iter()
                .any(|building| building.targetable(battle.t) && building.resource_target),
            Tag::Building => battle
                .buildings
                .iter()
                .any(|building| building.targetable(battle.t)),
            _ => false,
        };
        return retaliation || !preferred;
    }
    if let EntityRef::Building(owner) = current {
        if !battle.building_targetable(owner) {
            return false;
        }
    }
    let (candidate, kind) = battle.choose_target(reference);
    let Some(candidate) = candidate else {
        return true;
    };
    if candidate == current {
        return true;
    }
    let unit = battle.unit(reference);
    let mut pref = unit.spec.prefer.clone();
    if battle.t < unit.extra.angry_until
        || unit
            .pet
            .is_some_and(|pet| battle.unit(pet).attached(battle))
    {
        pref = Tag::Defense;
    }
    if pref == Tag::Follow && units::follow_target(battle, reference) == Some(candidate) {
        return false;
    }
    if matches!(kind, Some(Tag::Destination | Tag::Unit)) {
        return false;
    }
    let origin = EntityRef::Unit(reference);
    (
        tesla_target_priority(battle, &pref, current),
        -units::target_distance(battle, origin, current),
    ) >= (
        tesla_target_priority(battle, &pref, candidate),
        -units::target_distance(battle, origin, candidate),
    )
}

// defense.py:reveal_tesla.
pub fn reveal_tesla(battle: &mut Battle, owner: BuildingId) {
    let building = battle.building(owner);
    if building.revealed || !building.alive {
        return;
    }
    battle.building_mut(owner).revealed = true;
    // output/research/usage/overgrowth-spell.md:36: a covered Tesla stays untargetable.
    // https://clashofclans.fandom.com/wiki/Hidden_Tesla/Home_Village
    // Apply residual coverage before comparing the newly revealed target.
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
    // output/research/usage/baby-dragon.md:16; verify/c2.out #9: only flying
    // units keep a better current target (October 2020); ground units retarget.
    // https://clashofclans.fandom.com/wiki/Baby_Dragon
    // https://www.clash.ninja/blog/october-2020-update-is-here
    // https://clashofclans.fandom.com/wiki/Hidden_Tesla/Home_Village
    let attackers: Vec<_> = battle.attackers_pool().map(Unit::reference).collect();
    // Warden follow_target reads allies' targets: decide before clearing any.
    let retarget: Vec<_> = attackers
        .into_iter()
        .filter(|&reference| !tesla_keeps_target(battle, reference))
        .collect();
    for reference in retarget {
        let unit = battle.unit_mut(reference);
        unit.target = None;
        unit.wall_target = None;
        unit.target_kind = None;
        unit.extra.next_engage = 0.0;
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
        let mode = weapon(battle, owner)
            .mode
            .clone()
            .expect("Spell Tower mode");
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
            // defense.py:577-578: poison has its own radius, separate from the blast.
            radius: Some(4.0),
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
fn ordered_attackers_near(battle: &Battle, x: f64, y: f64, radius: f64) -> Vec<UnitRef> {
    // output/hunt/r10/t3.out #2: bucket alignment must not decide target ties.
    // output/research/usage/dealing-with-monolith-and-inferno-towers.md:
    // https://clashofclans.fandom.com/wiki/Monolith
    // Stable spawn IDs define candidate and accumulation order. This is a
    // deterministic tie policy, not a sourced game tie-break rule.
    let mut units = battle.attackers_near(x, y, radius);
    units.sort_by_key(|reference| battle.unit(*reference).id.0);
    units
}

pub fn visible(battle: &Battle, owner: BuildingId, radius: f64) -> Vec<UnitRef> {
    let building = battle.building(owner);
    let w = weapon(battle, owner);
    let mut out = Vec::new();
    for reference in ordered_attackers_near(battle, building.x, building.y, radius).into_iter() {
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

fn hit_damage(
    battle: &Battle,
    owner: BuildingId,
    max_hp: f64,
    is_hero: bool,
    damage_rage: f64,
    held: Option<f64>,
) -> f64 {
    let w = weapon(battle, owner);
    let mut damage = w.damage;
    if w.kind == Tag::InfernoSingle {
        damage = 0.0;
        for &(start, value) in &w.extra.ramp {
            if held.unwrap_or(w.lock_time) >= start {
                damage = value;
            }
        }
    }
    damage *= damage_rage;
    if w.kind == Tag::Monolith {
        damage += w.extra.pct * max_hp / battle.def_mult;
    } else if w.kind == Tag::Hunter && is_hero {
        damage *= 2.0;
    }
    damage
}

fn candle_targets(battle: &Battle, owner: BuildingId) -> usize {
    let w = weapon(battle, owner);
    let Some(first) = battle.first_deploy_t else {
        return w.extra.targets;
    };
    let active = battle.t - first;
    if active < w.extra.melt1 {
        6
    } else if active < w.extra.melt2 {
        4
    } else {
        3
    }
}

// output/research/usage/dealing-with-monolith-and-inferno-towers.md:
// https://clashofclans.fandom.com/wiki/Monolith
// Policy estimate: uninterrupted lock, concentrated shots and sustained bursts.
// Reuse combat hit damage without changing weapon or battle state.
pub fn opening_damage(
    battle: &Battle,
    owner: BuildingId,
    max_hp: f64,
    is_hero: bool,
    seconds: f64,
    is_siege: bool,
    flying: bool,
) -> f64 {
    let w = weapon(battle, owner);
    if seconds <= 0.0 || w.ammunition == Some(0) || battle.building(owner).disabled(battle.t) {
        return 0.0;
    }
    // output/research/usage/hero-sniping-of-exposed-defenses.md: TH16 must wake.
    // https://clashofclans.fandom.com/wiki/Town_Hall/Giga_Inferno
    if w.kind == Tag::GigaInferno && !battle.th_active() {
        return 0.0;
    }
    if w.kind == Tag::SpellTower {
        // game data v18.200.9 spells.csv: Spell Tower Poison has 60 DPS,
        // HeroDamageMultiplier=20; Earthquake has five 6% hits 400 ms apart.
        // Neither sets AffectsSiegeMachines. Mirror tower_cast, including the
        // continuous 1.2 s trigger, cooldown and Earthquake's 0.3 s landing.
        if is_siege {
            return 0.0;
        }
        let exposure = 0.0_f64.max(seconds - 0.0_f64.max(w.cooldown) - 1.2);
        if w.mode.as_deref() == Some("poison") {
            let hero_mult = if is_hero { 0.2 } else { 1.0 };
            return 60.0 * hero_mult * 12.0_f64.min(exposure);
        }
        if matches!(w.mode.as_deref(), Some("eq" | "quake" | "earthquake")) && !flying {
            let hits = 5.0_f64.min(0.0_f64.max(((exposure - 0.3) / 0.4).ceil()));
            return max_hp * 0.06 * hits;
        }
        return 0.0;
    }
    let damage_rage = rage(battle, owner);
    let mut interval = 0.1_f64.max(w.interval);
    if w.kind == Tag::InfernoSingle {
        let mut total = 0.0;
        for (index, &(start, _)) in w.extra.ramp.iter().enumerate() {
            let end = w.extra.ramp.get(index + 1).map_or(seconds, |entry| entry.0);
            let duration = 0.0_f64.max(seconds.min(end) - start);
            total +=
                hit_damage(battle, owner, max_hp, is_hero, damage_rage, Some(start)) * duration;
        }
        return total / interval * battle.def_mult;
    }
    let mut damage = hit_damage(battle, owner, max_hp, is_hero, damage_rage, None);
    let mut extra_damage = 0.0;
    match w.kind {
        Tag::MultiArcher => damage *= 3.0,
        // output/research/usage/crafting-station.md: unused flames concentrate.
        // https://clashofclans.fandom.com/wiki/Hot_Candle
        Tag::Candle => damage *= candle_targets(battle, owner) as f64,
        Tag::Cake => damage += w.extra.bomb * damage_rage,
        Tag::InfernoArtillery => {
            damage *= w.extra.targets as f64;
            // Existing pools do not stack or receive Rage/difficulty scaling.
            extra_damage = w.extra.pool_dps * seconds;
        }
        Tag::Burst | Tag::MortarBurst | Tag::Firespitter => {
            let shots = w.extra.shots as f64;
            damage *= shots;
            interval = 0.1_f64.max(w.interval + (shots - 1.0) * w.extra.gap);
        }
        Tag::Eagle => {
            let shots = w.extra.shells as f64;
            damage = (w.damage + w.extra.shock) * damage_rage * shots;
            interval = 0.1_f64.max(w.interval + (shots - 1.0) * w.extra.gap);
        }
        Tag::Revenge => {
            let Some((_, amount, cadence)) = revenge_profile(battle, owner, damage_rage) else {
                return 0.0;
            };
            damage = amount;
            interval = cadence;
        }
        Tag::Hook => damage = w.damage,
        Tag::Sweeper | Tag::BhRepairOnly => return 0.0,
        _ => {}
    }
    // Mirror hit_unit: scale weapon hits, cancelling Monolith's percent
    // compensation in hit_damage; spell/poison pools remain unscaled.
    damage * seconds / interval * battle.def_mult + extra_damage
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
        if ordered_attackers_near(battle, building.x, building.y, *radius)
            .into_iter()
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
    // defense.py:696-699: charge advances once per tick, including cooling ticks.
    if weapon(battle, owner).kind == Tag::InfernoSingle {
        weapon_mut(battle, owner).lock_time += dt;
    }
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
    let (bx, by) = battle.entity_position(EntityRef::Building(owner));
    let kind = weapon(battle, owner).kind.clone();
    if kind == Tag::Hook {
        let w = weapon(battle, owner);
        if w.cooldown > 0.0 {
            return;
        }
        let (range, damage, stun, interval) = (w.range, w.damage, w.extra.stun, w.interval);
        let candidates = visible(battle, owner, range);
        let Some(target) = nearest(battle, &candidates, bx, by) else {
            return;
        };
        battle.hit_unit(target, damage, None, "normal", None);
        let unit = battle.unit_mut(target);
        unit.stun_until = unit.stun_until.max(t + stun);
        weapon_mut(battle, owner).cooldown += interval;
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
            let targets = candle_targets(battle, owner);
            weapon_mut(battle, owner).extra.targets = targets;
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
    let w = weapon(battle, owner);
    let (range, min_range, idle_until, mut target) = (w.range, w.min_range, w.idle_until, w.target);
    if let Some(reference) = target {
        let unit = battle.unit(reference);
        let distance = dist(unit.x, unit.y, bx, by);
        if !unit.alive || !unit.targetable(battle) || distance > range || distance < min_range {
            target = None;
            weapon_mut(battle, owner).lock_time = 0.0;
        }
    }
    if target.is_none() {
        if t < idle_until {
            return;
        }
        let mut pool = visible(battle, owner, range);
        if pool.is_empty() {
            weapon_mut(battle, owner).idle_until = t + 0.25;
            return;
        }
        if kind == Tag::Hunter && pool.iter().any(|unit| battle.unit(*unit).is_hero) {
            pool.retain(|unit| battle.unit(*unit).is_hero);
        }
        target = nearest(battle, &pool, bx, by);
        let actual = weapon_mut(battle, owner);
        actual.target = target;
        actual.lock_time = 0.0;
        if kind == Tag::Scatter {
            // defense.py:1020-1022: every newly acquired target starts the delay.
            actual.cooldown = actual.cooldown.max(actual.extra.new_target_delay);
        }
    }
    let target = target.expect("single-target defense target");
    if kind == Tag::InfernoSingle {
        let w = weapon(battle, owner);
        if w.cooldown > 0.0 {
            return;
        }
        // defense.py:767-780: ramp entries are full per-hit damage, at 128 ms.
        let unit = battle.unit(target);
        let damage = hit_damage(battle, owner, unit.max_hp, unit.is_hero, damage_rage, None);
        battle.hit_unit(target, damage, None, "normal", None);
        let actual = weapon_mut(battle, owner);
        actual.cooldown += actual.interval;
        if let Some(ammunition) = &mut actual.ammunition {
            *ammunition -= 1;
        }
        return;
    }
    if weapon(battle, owner).cooldown > 0.0 {
        return;
    }
    // Specialized and cooling weapons never need an owning snapshot. Keep
    // one only across firing callbacks, which can mutate this weapon.
    let w = weapon(battle, owner).clone();
    if kind == Tag::Burst {
        if weapon(battle, owner).burst_left <= 0 {
            weapon_mut(battle, owner).burst_left = w.extra.shots as i64;
        }
        if battle.building(owner).key == "mgt" {
            let data = projectile_data(battle, owner, true);
            let offset = game_required_int(data, "StartOffset") as f64 / 100.0;
            projectile(battle, owner, target, w.damage * damage_rage, 12.0, offset);
        } else if battle.building(owner).key == "cannon" {
            // defense.py:744-748: geared Cannon projectile offset is level-specific.
            let Level::Int(level) = battle.building(owner).level.as_ref().expect("Cannon level")
            else {
                panic!("integer Cannon level");
            };
            let minimum = battle.catalog.setup.at("gear_minimum").at("cannon").i64();
            let offset = battle.catalog.setup.at("geared_cannon_offsets").arr()
                [(*level - minimum) as usize]
                .f64();
            projectile(battle, owner, target, w.damage * damage_rage, 12.0, offset);
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
    if kind == Tag::MortarBurst {
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
    if kind == Tag::Revenge {
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
            "cannon" | "at" | "ad" | "xbow" | "bh" | "mgt" => {
                let building = battle.building(owner);
                let alternate = building.key == "at"
                    && !matches!(building.mode.as_deref(), None | Some("normal"));
                let data = projectile_data(battle, owner, alternate);
                let offset = game_required_int(data, "StartOffset") as f64 / 100.0;
                let speed = match building.key.as_str() {
                    "cannon" => 12.0,
                    "at" => 18.0,
                    // defense.py:1090-1095: X-Bow arrows use the catalog projectile speed.
                    "xbow" | "bh" => game_required_int(data, "Speed") as f64 / 100.0,
                    _ => 8.0,
                };
                projectile(battle, owner, target, damage, speed, offset);
            }
            _ => {
                battle.hit_unit(target, damage, None, "normal", None);
            }
        },
        Tag::Monolith => {
            let unit = battle.unit(target);
            let amount = hit_damage(battle, owner, unit.max_hp, unit.is_hero, damage_rage, None);
            battle.hit_unit(target, amount, None, "normal", None);
        }
        Tag::Ricochet => {
            battle.hit_unit(target, damage, None, "normal", None);
            let (tx, ty) = battle.entity_position(EntityRef::Unit(target));
            let mut best = None;
            let mut best_distance = w.extra.bounce_range;
            for reference in ordered_attackers_near(battle, tx, ty, best_distance).into_iter() {
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
            if building.key == "wt" {
                // defense.py:866-877: every Wizard Tower starts 0.7 tiles forward.
                let flight = if matches!(
                    building.level.as_ref(),
                    Some(Level::Int(level)) if *level <= 4
                ) {
                    0.0_f64.max(dist(bx, by, tx, ty) - 0.7) / 5.0
                } else {
                    0.0_f64.max(dist(bx, by, tx, ty) - 0.7) / 9.0
                };
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
                let data = projectile_data(battle, owner, false);
                let offset = game_required_int(data, "StartOffset") as f64 / 100.0;
                let flight = 0.0_f64.max(dist(bx, by, tx, ty) - offset) / 8.0;
                battle.add_pending(Pending::new(
                    t + flight,
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
        Tag::Scatter => {
            // defense.py:1175-1196: track the primary and resolve the cone at impact.
            let data = projectile_data(battle, owner, false);
            let speed = game_required_int(data, "Speed") as f64 / 100.0;
            let offset = game_required_int(data, "StartOffset") as f64 / 100.0;
            let unit = battle.unit(target);
            let flight = 0.0_f64.max(dist(bx, by, unit.x, unit.y) - offset) / speed;
            let mut pending = Pending::new(
                t + flight,
                unit.x,
                unit.y,
                0.0,
                damage,
                unit.flying,
                !unit.flying,
                "scatter",
            );
            pending.extra.scatter = Some(owner);
            pending.extra.rage = damage_rage;
            pending.target = Some(EntityRef::Unit(target));
            battle.add_pending(pending);
        }
        Tag::Hunter => hunter_hit(battle, owner, target, damage_rage),
        _ => {}
    }
}

// defense.py:_visible: candidates use stable spawn order, including distance ties.
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

// defense.py:872-889: supercharges retain the final integer level's projectile.
fn projectile_data(battle: &Battle, owner: BuildingId, alternate: bool) -> &crate::json::Json {
    let building = battle.building(owner);
    let level = match building.level.as_ref().expect("defense level") {
        Level::Int(level) => *level,
        Level::Text(_) => battle
            .catalog
            .stats
            .record(&building.name)
            .at("levels")
            .arr()
            .iter()
            .filter_map(|row| match row.at("level") {
                crate::json::Json::Num(_) => Some(row.at("level").i64()),
                _ => None,
            })
            .max()
            .expect("integer building level"),
    };
    let name = match building.key.as_str() {
        "bh" => "Builders Hut",
        "mat" => "Multi Archer Tower",
        "mgt" => "Multi Gear Tower",
        _ => &building.name,
    };
    let row = battle
        .catalog
        .game_data("buildings", name, Some(&Level::Int(level)));
    let projectile = row
        .at(if alternate {
            "AltProjectile"
        } else {
            "Projectile"
        })
        .str();
    battle.catalog.game_data("projectiles", projectile, None)
}

// defense.py:892-906: tracking flight starts at the selected projectile offset.
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
    // defense.py:866-872: all Mortar shells use distance-based flight.
    let flight = 0.0_f64.max(dist(building.x, building.y, unit.x, unit.y) - 0.2) / 5.0;
    let mut pending = Pending::new(
        battle.t + flight,
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
                unit.alive && unit.targetable(battle) && dist(unit.x, unit.y, bx, by) <= w.range
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
        // defense.py:1009-1023: only pairs within one tile alternate the spare.
        let spare = if w.kind == Tag::MultiArcher
            && keep.len() == 2
            && battle
                .unit(keep[0])
                .dist(battle.unit(keep[1]).x, battle.unit(keep[1]).y)
                <= 1.0
        {
            let spare = if w.extra.spare_target == Some(keep[0]) {
                keep[1]
            } else {
                keep[0]
            };
            weapon_mut(battle, owner).extra.spare_target = Some(spare);
            Some(spare)
        } else {
            None
        };
        for index in 0..count {
            let reference = if index + 1 == count {
                spare.unwrap_or(keep[index % keep.len()])
            } else {
                keep[index % keep.len()]
            };
            if w.kind == Tag::MultiArcher {
                let data = projectile_data(battle, owner, false);
                let offset = game_required_int(data, "StartOffset") as f64 / 100.0;
                projectile(
                    battle,
                    owner,
                    reference,
                    w.damage * damage_rage,
                    18.0,
                    offset,
                );
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
        weapon_mut(battle, owner).target = None;
        return;
    };
    // output/research/usage/crafting-station.md: Cake exposes its firing target.
    // https://clashofclans.fandom.com/wiki/Cake-A-Pult
    weapon_mut(battle, owner).target = Some(target);
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
    let unit = battle.unit(target);
    let damage = hit_damage(battle, owner, unit.max_hp, unit.is_hero, damage_rage, None);
    battle.hit_unit(target, damage, None, "normal", None);
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
        .get(
            "Poison Spell",
            &level,
            &["Attack Rate Decrease"],
            Some(70.0),
        )
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
    for reference in ordered_attackers_near(battle, tx, ty, 5.0) {
        let unit = battle.unit(reference);
        if reference == target
            || (unit.name_id != Name::Totem && unit.flying != battle.unit(target).flying)
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
    // defense.py:1435-1442: catalog flight time; damage delay remains explicitly unused.
    let data = projectile_data(battle, owner, false);
    let flight = game_required_int(data, "FixedTravelTime") as f64 / 1000.0;
    let damage_delay = 0.0;
    for (radius, damage, shock) in [
        (w.extra.splash, w.damage, false),
        (w.extra.shock_radius, w.extra.shock, true),
    ] {
        let (x, y) = battle.entity_position(EntityRef::Unit(target));
        let mut pending = Pending::new(
            battle.t + flight,
            x,
            y,
            radius,
            damage * rage(battle, owner),
            true,
            true,
            "eagle",
        );
        pending.extra.damage_delay = damage_delay;
        pending.extra.track = Some(EntityRef::Unit(target));
        pending.extra.origin = Some((bx, by));
        pending.extra.min_range = w.min_range;
        pending.extra.max_range = w.range;
        pending.extra.push = if shock { 0.5 } else { 0.0 };
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

// defense.py:1110-1167: aim at the first nearest flyer, then enqueue wave arrivals.
pub fn sweeper(battle: &mut Battle, owner: BuildingId) {
    let w = weapon(battle, owner).clone();
    if w.cooldown > 0.0 {
        return;
    }
    let (bx, by) = battle.entity_position(EntityRef::Building(owner));
    let mut aim = None;
    let mut best_distance = 0.0;
    let mut best_id = usize::MAX;
    for reference in ordered_attackers_near(battle, bx, by, w.range) {
        let unit = battle.unit(reference);
        if !unit.flying || unit.name_id == Name::Totem || !unit.targetable(battle) {
            continue;
        }
        let distance = dist(unit.x, unit.y, bx, by);
        if distance < w.min_range {
            continue;
        }
        let angle = geom::py_atan2(unit.y - by, unit.x - bx);
        // defense.py:1038: math.radians multiplies by the rounded PI / 180.0.
        if ((angle - w.facing + PI).rem_euclid(2.0 * PI) - PI).abs() <= 52.5 * (PI / 180.0)
            && (aim.is_none()
                || distance < best_distance
                || distance == best_distance && unit.id.0 < best_id)
        {
            aim = Some(angle);
            best_distance = distance;
            best_id = unit.id.0;
        }
    }
    let Some(aim) = aim else {
        return;
    };
    let mut arrivals = ordered_attackers_near(battle, bx, by, w.range);
    arrivals.sort_by(|a, b| {
        let a = battle.unit(*a);
        let b = battle.unit(*b);
        (dist(a.x, a.y, bx, by), a.id.0)
            .partial_cmp(&(dist(b.x, b.y, bx, by), b.id.0))
            .expect("Sweeper arrival order")
    });
    for reference in arrivals {
        let unit = battle.unit(reference);
        if !unit.flying || unit.name_id == Name::Totem {
            continue;
        }
        let angle = geom::py_atan2(unit.y - by, unit.x - bx);
        if ((angle - aim + PI).rem_euclid(2.0 * PI) - PI).abs() <= 5.0 * (PI / 180.0) {
            let flight = 0.0_f64.max(dist(unit.x, unit.y, bx, by) - 1.25) / 6.0;
            let mut pending = Pending::new(
                battle.t + flight,
                bx,
                by,
                w.range,
                0.0,
                true,
                false,
                &battle.building(owner).key,
            );
            pending.extra.sweeper_aim = Some(aim);
            pending.extra.push = w.extra.push;
            pending.actor = Some(EntityRef::Building(owner));
            pending.target = Some(EntityRef::Unit(reference));
            battle.add_pending(pending);
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
            // defense.py:1107-1115: spell Skeletons can trigger Poison Towers.
            (!spells::NO_TRIGGER.contains(&unit.name_id)
                || w.mode.as_deref() == Some("poison") && unit.name_id == Name::SpellSkeleton)
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
        // defense.py:1201-1207: each eligible unit retains its own timer.
        let previous = match w.extra.trigger.as_ref() {
            Some(WeaponTrigger::Units(triggers)) => triggers.as_slice(),
            None => &[],
            Some(WeaponTrigger::Radius(_)) => panic!("Spell Tower unit trigger"),
        };
        let triggers: Vec<_> = near
            .into_iter()
            .map(|unit| {
                let since = previous
                    .iter()
                    .find(|(candidate, _)| *candidate == unit)
                    .map_or(t, |(_, since)| *since);
                (unit, since)
            })
            .collect();
        weapon_mut(battle, owner).extra.trigger =
            Some(WeaponTrigger::Units(triggers.clone().into()));
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
    };
    if t - since < 1.2 {
        return;
    }
    let mode = w.mode.as_deref().expect("Spell Tower mode");
    spells::tower_cast(battle, owner, mode, Some(&[unit]));
    let actual = weapon_mut(battle, owner);
    actual.extra.trigger = None;
    actual.extra.hit_triggers.clear();
    actual.cooldown += actual.interval;
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
            // defense.py:builder_spell: Freeze applies to Builders at landing.
            Tag::Freeze => {
                builder.frozen_until = builder.frozen_until.max(t + field.value);
            }
            Tag::Poison => {
                builder.repair_slow = 1.0 - field.extra.atk;
                builder.slow_until = field.until.min(t + battle.dt);
            }
            Tag::Lightning | Tag::Totem => {
                builder.target = None;
                let duration = if field.kind == Tag::Lightning {
                    0.1
                } else {
                    0.2
                };
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
        // defense.py:1253-1259: marginal weights follow battle.builders order.
        for (position, ((index, _), amount)) in builders.into_iter().zip(amounts).enumerate() {
            let efficiency = weights[position.min(weights.len() - 1)];
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
        for reference in ordered_attackers_near(battle, tx, ty, next_distance) {
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

pub fn firespitter_in_sector(battle: &Battle, owner: BuildingId, x: f64, y: f64) -> bool {
    // output/research/usage/firespitter.md: acquisition stays inside its sector.
    // https://supercell.com/en/games/clashofclans/blog/game-updates/the-town-hall-17-update-is-here-2/
    let building = battle.building(owner);
    let w = weapon(battle, owner);
    let angle = geom::py_atan2(y - building.y, x - building.x);
    ((angle - w.facing + PI).rem_euclid(2.0 * PI) - PI).abs() <= w.extra.arc
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
        firespitter_in_sector(battle, owner, unit.x, unit.y)
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
            if firespitter_in_sector(battle, owner, unit.x, unit.y) {
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
    for reference in ordered_attackers_near(battle, bx, by, length + 2.0) {
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

struct RevengeShot {
    owner: BuildingId,
    stage: usize,
    hit: Vec<EntityRef>,
}

fn revenge_projectile(
    battle: &mut Battle,
    shot: RevengeShot,
    target: UnitRef,
    damage: f64,
    damage_rage: f64,
    x: f64,
    y: f64,
    at: f64,
    offset: f64,
) {
    // game data v18.200.9: projectiles.csv RevengeTowerProjectile1/2/3:
    // Speed=1400/1800/2200, StartOffset=135 -> 14/18/22 tiles/s, 1.35 tiles.
    let speed = [14.0, 18.0, 22.0][shot.stage - 1];
    let unit = battle.unit(target);
    let flight = 0.0_f64.max(dist(x, y, unit.x, unit.y) - offset) / speed;
    let mut pending = Pending::new(
        at + flight,
        unit.x,
        unit.y,
        0.0,
        damage,
        unit.flying,
        !unit.flying,
        battle.building(shot.owner).source.clone(),
    );
    pending.extra.scatter = Some(shot.owner);
    pending.extra.remaining = shot.stage;
    pending.extra.hit = shot.hit;
    pending.extra.rage = damage_rage;
    pending.target = Some(EntityRef::Unit(target));
    battle.add_pending(pending);
}

pub fn revenge_impact(battle: &mut Battle, pending: Pending) {
    let shot = RevengeShot {
        owner: pending.extra.scatter.expect("Revenge projectile owner"),
        stage: pending.extra.remaining,
        hit: pending.extra.hit,
    };
    let Some(EntityRef::Unit(target)) = pending.target else {
        panic!("Revenge projectile target");
    };
    if !battle.unit(target).indirect_targetable(battle) {
        return;
    }
    battle.hit_unit(target, pending.damage, None, "normal", None);
    if shot.hit.len() >= shot.stage {
        return;
    }
    let unit = battle.unit(target);
    let (x, y) = (unit.x, unit.y);
    // Keep the wiki's two-tile radius: projectiles.csv MaxBounceDistance=450
    // conflicts with it (output/hunt/r9/s5.out #1).
    let next = ordered_attackers_near(battle, x, y, 2.0)
        .into_iter()
        .find(|reference| {
            let unit = battle.unit(*reference);
            !shot.hit.contains(&EntityRef::Unit(*reference)) && unit.indirect_targetable(battle)
        });
    let Some(next) = next else {
        return;
    };
    let column = ["Damage per Shot (Secondary)", "Damage per Shot (Tertiary)"][shot.hit.len() - 1];
    let owner = battle.building(shot.owner);
    let damage = battle
        .catalog
        .stats
        .get(
            &owner.name,
            owner.level.as_ref().expect("Revenge Tower level"),
            &[column],
            None,
        )
        .expect("Revenge Tower chain damage")
        * pending.extra.rage;
    let mut following = shot;
    following.hit.push(EntityRef::Unit(next));
    revenge_projectile(
        battle,
        following,
        next,
        damage,
        pending.extra.rage,
        x,
        y,
        pending.at,
        0.0,
    );
}

// defense.py:_revenge: stage and damage are fixed when each shot launches.
fn revenge_profile(
    battle: &Battle,
    owner: BuildingId,
    damage_rage: f64,
) -> Option<(usize, f64, f64)> {
    let destroyed = battle.destroyed_counted;
    if destroyed < 5 {
        return None;
    }
    let stage = if destroyed >= 50 {
        3
    } else if destroyed >= 25 {
        2
    } else {
        1
    };
    let building = battle.building(owner);
    let damage = if stage == 1 {
        weapon(battle, owner).damage
    } else {
        battle
            .catalog
            .stats
            .get(
                &building.name,
                building.level.as_ref().expect("Revenge Tower level"),
                &["Damage per Shot (Primary)"],
                None,
            )
            .expect("Revenge Tower primary damage")
    } * damage_rage;
    let interval = if stage == 1 {
        1.2
    } else if stage == 2 {
        0.6
    } else {
        0.35
    };
    Some((stage, damage, interval))
}

fn revenge(battle: &mut Battle, owner: BuildingId, target: UnitRef, damage_rage: f64) {
    let Some((stage, damage, interval)) = revenge_profile(battle, owner, damage_rage) else {
        return;
    };
    let building = battle.building(owner);
    let (x, y) = (building.x, building.y);
    let shot = RevengeShot {
        owner,
        stage,
        hit: vec![EntityRef::Unit(target)],
    };
    let at = battle.t;
    revenge_projectile(battle, shot, target, damage, damage_rage, x, y, at, 1.35);
    weapon_mut(battle, owner).cooldown += interval;
}

// defense.py:1373-1409: health rescales immediately; damage lingers one second.
pub fn bell_tick(battle: &mut Battle) {
    let bells: Vec<_> = battle
        .buildings
        .iter()
        .filter(|building| building.alive && building.name_id == Name::HeroBell && battle.t >= 2.2)
        .map(|building| building.id)
        .collect();
    let heroes: Vec<_> = battle
        .defenders_pool()
        .filter(|hero| hero.alive && hero.is_hero)
        .map(Unit::reference)
        .collect();
    for hero in heroes {
        let (mut damage_boost, mut health_boost) = (0.0_f64, 0.0_f64);
        for &bell in &bells {
            let building = battle.building(bell);
            let unit = battle.unit(hero);
            if dist(unit.x, unit.y, building.x, building.y)
                > battle.catalog.stats.attrs("Hero Bell").at("range").f64()
            {
                continue;
            }
            let level = building.level.as_ref().expect("Hero Bell level");
            let damage_level = battle
                .defense_levels
                .iter()
                .find(|(key, _)| key == "crafting:damage")
                .map_or(level, |(_, level)| level);
            let health_level = battle
                .defense_levels
                .iter()
                .find(|(key, _)| key == "crafting:health")
                .map_or(level, |(_, level)| level);
            damage_boost = damage_boost.max(
                battle
                    .catalog
                    .stats
                    .get("Hero Bell", damage_level, &["Hero DPS Boost"], None)
                    .expect("Hero Bell damage boost")
                    / 100.0,
            );
            health_boost = health_boost.max(
                battle
                    .catalog
                    .stats
                    .get("Hero Bell", health_level, &["Hero HP Boost"], None)
                    .expect("Hero Bell health boost")
                    / 100.0,
            );
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
