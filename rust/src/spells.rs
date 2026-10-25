//! Ports spells.py:32-43,109-1238. Setup validation stays in Python.

use std::cell::RefCell;
use std::rc::Rc;

use crate::catalog::game_int;
use crate::effects;
use crate::geom::py_hypot;
use crate::labels::{Name, Special, Tag};
use crate::source::Source;
use crate::state::*;
use crate::trace::round_decimal;
use crate::{defense, traps, units};

pub const NO_TRIGGER: &[Name] = &[Name::SpellSkeleton, Name::Skeleton, Name::Bat, Name::Totem];

// spells.py:24: also used by Headhunter poison (units.py:2376).
pub const POISON_HERO_MULT: f64 = 0.05;

// spells.py:1199-1211: marking a KO does not cast a Revive Spell.
pub fn maybe_revive(battle: &mut Battle, hero: UnitRef) {
    let unit = battle.unit(hero);
    if !unit.is_hero || hero.team != Team::Atk || unit.extra.mirror_clone {
        return;
    }
    let t = battle.t;
    let unit = battle.unit_mut(hero);
    unit.extra.revivable = true;
    unit.extra.ko_at = Some(t);
    if let Some(pet) = unit.pet.take() {
        let pet = battle.unit_mut(pet);
        pet.extra.rampage_detached = true;
        pet.owner = None;
    }
    if let Some(kit) = &mut battle.unit_mut(hero).kit {
        kit.pet_unit = None;
    }
}

// spells.py:42-43.
fn affected(unit: &Unit) -> bool {
    unit.alive && !matches!(unit.kind, Tag::Siege | Tag::SiegeIdle) && unit.name_id != Name::Totem
}

// spells.py:258-280: snapshot original fields, preserve fields appended mid-tick.
pub fn tick(battle: &mut Battle) {
    let t = battle.t;
    for field in &mut battle.fields {
        if field.identity == 0 {
            battle.field_identity += 1;
            field.identity = battle.field_identity;
        }
    }
    // spells.py:270-287,765-783: tuple snapshots preserve object identity.
    // A later Ice Block may update an already processed summon, so keep the
    // live field slots until all callbacks have finished, then filter by index.
    let count = battle.fields.len();
    let mut keep = vec![false; count];
    for index in 0..count {
        let mut field = battle.fields[index].clone();
        if t < field.started {
            keep[index] = true;
            continue;
        }
        if field.kind == Tag::Tornado && t >= field.until {
            traps::tornado_tick(battle, &mut field);
            expire(battle, &field);
            battle.fields[index] = field;
            continue;
        }
        let alive = apply(battle, &mut field);
        keep[index] = alive && t < field.until;
        if !keep[index] {
            expire(battle, &field);
        }
        battle.fields[index] = field;
    }
    battle.fields = std::mem::take(&mut battle.fields)
        .into_iter()
        .enumerate()
        .filter(|(index, _)| *index >= count || keep[*index])
        .map(|(_, field)| field)
        .collect();
    poison_states(battle);
    clone_expiry(battle);
}

// spells.py:283-779: snapshot order and instantaneous field mutations.
pub fn apply(battle: &mut Battle, f: &mut Field) -> bool {
    let t = battle.t;
    let dt = battle.dt;
    let kind = f.kind.clone();
    if matches!(
        kind,
        Tag::Poison
            | Tag::DefPoison
            | Tag::DefRage
            | Tag::DefBurn
            | Tag::Burn
            | Tag::Rage
            | Tag::Invis
            | Tag::DefInvis
            | Tag::Angry
    ) && t >= f.until
    {
        return false;
    }
    if matches!(kind, Tag::Lightning | Tag::Freeze | Tag::Poison)
        || kind == Tag::Rage && f.team == Team::Def
    {
        defense::builder_spell(battle, f);
    }
    match kind {
        // spells.py:308-324: residual freeze/overgrowth coverage for revealed Teslas.
        Tag::TeslaFreeze | Tag::TeslaOvergrowth => {
            if t >= f.until {
                return false;
            }
            for building in &mut battle.buildings {
                if building.alive
                    && building.key == "tesla"
                    && building.revealed
                    && building.edge_distance(f.x, f.y) <= f.radius
                {
                    if kind == Tag::TeslaFreeze {
                        building.frozen_until = building.frozen_until.max(f.until);
                    } else {
                        building.overgrown_until = building.overgrown_until.max(f.until);
                    }
                }
            }
            true
        }
        Tag::RollingLog => units::advance_log(battle, f),
        Tag::Lightning => damaging_field(battle, f, false),
        Tag::Birthday => damaging_field(battle, f, true),
        Tag::Yellow => yellow(battle, f),
        Tag::Santa => santa(battle, f),
        Tag::Heal => heal(battle, f),
        Tag::Rage => rage(battle, f),
        Tag::Burn => burn(battle, f),
        // spells.py:465-494: pool damage does not stack or gain defense difficulty.
        Tag::DefBurn => {
            if !f.extra.has_pulses || !pulses(f, t).is_empty() {
                f.extra.victims = battle
                    .attackers_near_iter(f.x, f.y, f.radius)
                    .map(|unit| unit.id)
                    .collect();
            }
            for reference in battle.attackers_near(f.x, f.y, f.radius) {
                let u = battle.unit(reference);
                if !u.alive
                    || u.underground
                    || u.extra.burn_tick == Some(t)
                    || !f.extra.victims.contains(&u.id)
                {
                    continue;
                }
                let mut damage = None;
                for field in &battle.fields {
                    if field.kind == Tag::DefBurn
                        && field.started <= t
                        && t < field.until
                        && u.dist(field.x, field.y) <= field.radius
                    {
                        damage = Some(
                            damage.map_or(field.value, |previous: f64| previous.max(field.value)),
                        );
                    }
                }
                battle.unit_mut(reference).extra.burn_tick = Some(t);
                battle.hit_unit(
                    reference,
                    damage.unwrap_or(f.value) * dt,
                    Some("th"),
                    "normal",
                    None,
                );
            }
            true
        }
        Tag::Tornado => {
            traps::tornado_tick(battle, f);
            true
        }
        // spells.py:500-517: defense rage does not stack with itself.
        Tag::DefRage => {
            // spells.py:516-527: each 300-ms pulse lasts a full second.
            let row = battle.catalog.game_data("spells", "Spell Tower Rage", None);
            let gap = game_int(row, "TimeBetweenHitsMS", 0) as f64 / 1000.0;
            let boost_time = game_int(row, "BoostTimeMS", 0) as f64 / 1000.0;
            let Some(pulse) = application(f, t, gap) else {
                return true;
            };
            let until = crate::geom::round6(pulse + boost_time);
            for index in 0..battle.builders.len() {
                let builder = &battle.builders[index];
                if battle.building(builder.owner).alive
                    && crate::geom::dist(builder.x, builder.y, f.x, f.y) <= f.radius
                {
                    let builder = &mut battle.builders[index];
                    builder.repair_boost = 2.0;
                    builder.rage_speed = f.extra.speed.unwrap_or(30.0 / 8.0);
                    builder.rage_until = until;
                }
            }
            for building in &mut battle.buildings {
                if building.alive
                    && building.weapon.is_some()
                    && building.edge_distance(f.x, f.y) <= f.radius
                {
                    building.rage_mult = f.value;
                    building.rage_until = until;
                }
            }
            for reference in battle.defenders_near(f.x, f.y, f.radius) {
                let factor = if battle.unit(reference).is_hero {
                    0.5
                } else {
                    1.0
                };
                let status_source = source(battle, f);
                units::add_rage(
                    battle.unit_mut(reference),
                    status_source,
                    1.0 + (f.value - 1.0) * factor,
                    30.0 / 8.0 * factor,
                    until,
                );
            }
            true
        }
        Tag::Haste => haste(battle, f),
        Tag::Jump => jump(battle, f),
        Tag::Freeze => freeze(battle, f),
        Tag::Poison => attacker_poison(battle, f),
        // spells.py:566-587.
        Tag::DefPoison => {
            let gap = f.extra.gap.unwrap_or(dt);
            if application(f, t, gap).is_none() {
                return true;
            }
            for reference in battle.attackers_near(f.x, f.y, f.radius) {
                let u = battle.unit(reference);
                // output/research/usage/battle-blimp.md: April made sieges immune
                // to TH14-16 poison, superseding the older game-data exception.
                // https://supercell.com/en/games/clashofclans/blog/release-notes/the-sound-of-clash-update/
                if affected(u) || u.name_id == Name::Totem {
                    let multiplier = if u.is_hero { f.extra.hero_mult } else { 1.0 };
                    let field_source = source(battle, f);
                    let StatusSource::Field(serial) = field_source else {
                        unreachable!()
                    };
                    poison(
                        battle,
                        reference,
                        f.value,
                        f.extra.slow,
                        f.extra.atk,
                        multiplier,
                        PoisonOptions {
                            ramp: f.extra.ramp,
                            origin: f.extra.origin.as_deref().unwrap_or("tower"),
                            source: Some(("field".to_owned(), serial)),
                            source_until: Some(f.until),
                            refresh: f.extra.gap.unwrap_or(0.2),
                        },
                    );
                }
            }
            true
        }
        Tag::Quake | Tag::DefQuake => quake(battle, f),
        Tag::Clone => clone_field(battle, f),
        Tag::Summon => summon(battle, f),
        Tag::Invis => invis(battle, f),
        // spells.py:713-725: each pulse grants 0.6 seconds of invisibility.
        Tag::DefInvis => {
            let Some(until) = invisibility_until(f, t) else {
                return true;
            };
            // output/research/usage/invisibility-spell.md: towers also use centres.
            // https://www.reddit.com/r/ClashOfClans/comments/1l4z2tu/guide_to_attacking_invisibility_spell_tower_bases/
            for building in &mut battle.buildings {
                if building.alive && crate::geom::dist(building.x, building.y, f.x, f.y) <= f.radius
                {
                    building.invisible_until = building.invisible_until.max(until);
                }
            }
            for reference in battle.defenders_near(f.x, f.y, f.radius) {
                let u = battle.unit_mut(reference);
                u.invisible_until = u.invisible_until.max(until);
            }
            for reference in battle.attackers_near(f.x, f.y, f.radius) {
                let u = battle.unit_mut(reference);
                if !matches!(u.kind, Tag::Siege | Tag::SiegeIdle) {
                    u.invisible_until = u.invisible_until.max(until);
                }
            }
            true
        }
        Tag::Recall => recall(battle, f),
        Tag::Overgrowth => overgrowth(battle, f),
        Tag::Iceblock => iceblock(battle, f),
        Tag::Totem => totem(battle, f),
        Tag::Angry => angry(battle, f),
        Tag::ReviveCast => revive_cast(battle, f),
        Tag::ReviveDue => {
            let hero = f.extra.hero.expect("delayed Revive hero");
            let u = battle.unit(hero);
            if !u.alive && u.extra.revivable {
                revive(battle, hero, f.value);
            }
            false
        }
        _ => false,
    }
}

// spells.py:479-542: the first active pool accounts for all attacking fire.
// The Vec is Python's insertion-ordered target dictionary: replacing a
// stronger source retains the target's original position.
fn burn(battle: &mut Battle, current: &mut Field) -> bool {
    let t = battle.t;
    if current.extra.burn_tick == Some(t) {
        return true;
    }
    let mut damage_by_target: Vec<(EntityRef, f64, usize)> = Vec::new();
    for index in 0..battle.fields.len() {
        let field = &battle.fields[index];
        if field.kind != Tag::Burn || !(field.started <= t && t < field.until) {
            continue;
        }
        let mut field = field.clone();
        field.extra.burn_tick = Some(t);
        if !field.extra.has_pulses || !pulses(&mut field, t).is_empty() {
            field.extra.victims = battle
                .defenders_near(field.x, field.y, field.radius)
                .into_iter()
                .map(|unit| battle.unit(unit).id)
                .collect();
        }
        let fraction = if field.extra.ramp {
            1.0_f64.min((t - field.started) / battle.params.poison_ramp)
        } else {
            1.0
        };
        let damage = field.value * fraction;
        let mut targets = Vec::new();
        if field.extra.buildings {
            targets.extend(
                battle
                    .buildings
                    .iter()
                    .filter(|building| {
                        building.alive && building.edge_distance(field.x, field.y) <= field.radius
                    })
                    .map(|building| EntityRef::Building(building.id)),
            );
        }
        if field.extra.walls {
            targets.extend(
                battle
                    .walls
                    .iter()
                    .filter(|wall| {
                        wall.alive && wall.edge_distance(field.x, field.y) <= field.radius
                    })
                    .map(|wall| EntityRef::Wall(wall.id)),
            );
        }
        targets.extend(
            battle
                .defenders_near(field.x, field.y, field.radius)
                .into_iter()
                .map(|unit| battle.unit(unit))
                .filter(|unit| {
                    unit.indirect_targetable(battle)
                        && field.extra.victims.contains(&unit.id)
                        && (!unit.flying || field.extra.hits_air)
                })
                .map(|unit| EntityRef::Unit(unit.reference())),
        );
        for target in targets {
            let amount = if matches!(target, EntityRef::Wall(_)) {
                damage * field.extra.wall_mult
            } else {
                damage
            };
            if let Some((_, previous, source)) = damage_by_target
                .iter_mut()
                .find(|(key, _, _)| *key == target)
            {
                if amount > *previous {
                    *previous = amount;
                    *source = index;
                }
            } else {
                damage_by_target.push((target, amount, index));
            }
        }
        // tick() owns a clone of its current slot; keep its pulse state in
        // sync so the callback's writeback preserves this shared update.
        if field.identity == current.identity {
            *current = field.clone();
        }
        battle.fields[index] = field;
    }
    for (target, damage, index) in damage_by_target {
        let field = &battle.fields[index];
        let actor = field.extra.actor.expect("attacking burn actor");
        let src = field.extra.src.clone().expect("attacking burn source");
        effects::damage_source(
            battle,
            Some(EntityRef::Unit(actor)),
            Tag::Attack,
            |battle| {
                if let EntityRef::Unit(unit) = target {
                    battle.hit_unit(
                        unit,
                        damage * battle.dt,
                        Some(&src),
                        "normal",
                        Some(EntityRef::Unit(actor)),
                    );
                } else {
                    let dealt =
                        battle.hit_building(target, damage * battle.dt, Some(&src), "normal");
                    battle.unit_mut(actor).damage_dealt += dealt;
                }
            },
        );
    }
    true
}

// spells.py:789-795: one persistent source identity per field.
fn source(battle: &mut Battle, field: &mut Field) -> StatusSource {
    if field.extra.source.is_none() {
        battle.field_serial += 1;
        field.extra.source = Some(("field".to_owned(), battle.field_serial));
    }
    let (name, serial) = field.extra.source.as_ref().expect("field source");
    assert_eq!(name, "field", "unknown field source tag");
    StatusSource::Field(*serial)
}

// spells.py:798-805: Python math.isclose defaults rel_tol=1e-9, abs_tol=0.
fn close(a: f64, b: f64) -> bool {
    a == b
        || (a.is_finite()
            && b.is_finite()
            && ((a - b).abs() <= (1e-9 * b).abs() || (a - b).abs() <= (1e-9 * a).abs()))
}

pub fn application(field: &mut Field, t: f64, gap: f64) -> Option<f64> {
    let mut at = field.extra.next_apply.unwrap_or(field.started);
    if at > t && !close(at, t) {
        return None;
    }
    while at + gap < t || close(at + gap, t) {
        at += gap;
    }
    field.extra.next_apply = Some(at + gap);
    Some(at)
}

// spells.py:808-818: application budget for defensive burn pools too.
pub fn pulses(field: &mut Field, t: f64) -> Vec<f64> {
    let mut delivered = field.extra.delivered;
    let mut due = Vec::new();
    while delivered < field.extra.pulses {
        let at = field.started + delivered as f64 * field.extra.gap.expect("pulse gap");
        if at > t && !close(at, t) {
            break;
        }
        due.push(at);
        delivered += 1;
    }
    field.extra.delivered = delivered;
    due
}

// spells.py:821-834.
pub fn invisibility_until(field: &mut Field, t: f64) -> Option<f64> {
    application(field, t, 0.25).map(|hit| hit + 0.6)
}

// spells.py:837-838 is deliberately empty in Python too.
pub fn expire(_battle: &mut Battle, _field: &Field) {}

// spells.py:841-847.
pub fn wall_jumped(battle: &Battle, wall: WallId) -> bool {
    let w = &battle.walls[wall.0];
    battle.fields.iter().any(|field| {
        field.kind == Tag::Jump
            && field.started <= battle.t
            && battle.t < field.until
            && py_hypot(w.x - field.x, w.y - field.y) <= field.radius
    })
}

// spells.py:873-879.
pub fn poison_factors(unit: &Unit, damage: f64, movement: f64, attack: f64) -> (f64, f64, f64) {
    if unit.kind == Tag::Guardian {
        if unit.extra.waiting {
            return (0.0, 0.0, 0.0);
        }
        return (damage * 0.3, movement * 0.3, attack * 0.3);
    }
    (damage, movement, attack)
}

pub struct PoisonOptions<'a> {
    pub ramp: bool,
    pub origin: &'a str,
    pub source: Option<(String, i64)>,
    pub source_until: Option<f64>,
    pub refresh: f64,
}

// spells.py:882-910: independent exposures keyed by unit, origin, source.
pub fn poison(
    battle: &mut Battle,
    reference: UnitRef,
    max_dps: f64,
    slow: f64,
    attack: f64,
    multiplier: f64,
    options: PoisonOptions<'_>,
) {
    let u = battle.unit(reference);
    if u.kind == Tag::Guardian && u.extra.waiting {
        return;
    }
    let (damage, slow, attack) = poison_factors(u, max_dps * multiplier, slow, attack);
    let linger = if u.team == Team::Def { 6.0 } else { 0.0 };
    let mut until = battle.t
        + if u.team == Team::Def {
            6.0
        } else {
            options.refresh
        };
    if let Some(source_until) = options.source_until {
        until = until.min(source_until + linger);
    }
    let index = battle.poison.iter().position(|state| {
        state.unit == reference && state.origin == options.origin && state.source == options.source
    });
    let index = match index {
        Some(index) => index,
        None => {
            let index = battle.poison.len();
            battle.poison.push(PoisonState {
                unit: reference,
                origin: options.origin.to_owned(),
                source: options.source,
                since: battle.t,
                dps: 0.0,
                ramp: false,
                until: 0.0,
                slow: 0.0,
                attack: 0.0,
            });
            index
        }
    };
    let state = &mut battle.poison[index];
    state.dps = damage;
    state.ramp = options.ramp;
    state.until = until;
    state.slow = slow;
    state.attack = attack;
}

// spells.py:913-959: first insertion controls the active damage origin on ties.
pub fn poison_states(battle: &mut Battle) {
    let t = battle.t;
    let mut dead = Vec::new();
    let mut live = Vec::new();
    let mut exposure: Vec<(UnitId, f64)> = Vec::new();
    for (index, state) in battle.poison.iter().enumerate() {
        let unit = battle.unit(state.unit);
        if t >= state.until || !unit.alive && unit.extra.recalled.is_none() {
            dead.push(index);
            continue;
        }
        if unit.extra.recalled.is_some() {
            continue;
        }
        if unit.underground && state.origin != "town_hall" {
            continue;
        }
        live.push(state.clone());
        if state.ramp {
            if let Some((_, value)) = exposure.iter_mut().find(|(id, _)| *id == unit.id) {
                // spells.py:935: (previous + t) - since + DT, not previous + (t-since+DT).
                *value = *value + t - state.since + battle.dt;
            } else {
                exposure.push((unit.id, 0.0 + t - state.since + battle.dt));
            }
        }
    }
    let mut active: Vec<(UnitRef, f64, String, f64, f64)> = Vec::new();
    for state in live {
        let fraction = if state.ramp {
            1.0_f64.min(
                exposure
                    .iter()
                    .find(|(id, _)| *id == state.unit.id)
                    .expect("poison exposure")
                    .1
                    / battle.params.poison_ramp,
            )
        } else {
            1.0
        };
        let damage = state.dps * fraction;
        if let Some(previous) = active.iter_mut().find(|item| item.0 == state.unit) {
            if damage > previous.1 {
                previous.1 = damage;
                previous.2 = state.origin;
            }
            previous.3 = previous.3.max(state.slow);
            previous.4 = previous.4.max(state.attack);
        } else {
            active.push((state.unit, damage, state.origin, state.slow, state.attack));
        }
    }
    for (unit, damage, origin, movement, attack) in active {
        battle.src = if unit.team == Team::Def {
            Source::Literal("spell")
        } else {
            Source::Literal("poison")
        };
        let kind = if origin == "town_hall" {
            "th_poison"
        } else {
            "poison"
        };
        let label = battle.src.clone();
        battle.hit_unit(unit, damage * battle.dt, Some(&label), kind, None);
        let until = t + 2.0 * battle.dt;
        effects::add_slow(
            battle.unit_mut(unit),
            StatusSource::Name("poison".to_owned()),
            1.0 - movement,
            1.0 - attack,
            until,
        );
    }
    let mut index = 0;
    battle.poison.retain(|_| {
        let keep = !dead.contains(&index);
        index += 1;
        keep
    });
}

// spells.py:962-988: common defensive cloud construction (called by impacts).
pub fn add_defensive_poison(
    battle: &mut Battle,
    x: f64,
    y: f64,
    mut config: PoisonConfig,
    origin: &str,
) {
    if origin == "town_hall" && battle.town_hall == 16 {
        config.atk = Some(0.5);
    }
    let mut extra = FieldExtra {
        slow: config.slow.unwrap_or(0.35),
        atk: config.atk.unwrap_or(0.0),
        ramp: config.ramp,
        origin: Some(origin.to_owned()),
        hero_mult: config.hero_mult,
        ..Default::default()
    };
    if origin == "tower" {
        extra.gap = Some(0.4);
    }
    battle.fields.push(Field {
        identity: 0,
        kind: Tag::DefPoison,
        x,
        y,
        radius: config.radius.unwrap_or(5.0),
        until: battle.t + config.time.unwrap_or(12.0),
        team: Team::Def,
        value: config.dps,
        extra,
        started: battle.t,
    });
}

// spells.py:991-1039: log precedes candidate selection, even for empty pools.
pub fn tower_cast(battle: &mut Battle, owner: BuildingId, mode: &str, near: Option<&[UnitRef]>) {
    let t = battle.t;
    battle.log_event(vec![
        round_decimal(t, 1).into(),
        "spell_tower".into(),
        mode.into(),
    ]);
    let b = battle.building(owner);
    let (bx, by) = (b.x, b.y);
    let mut target = None;
    let mut distance = f64::INFINITY;
    if let Some(near) = near {
        for &reference in near {
            let unit = battle.unit(reference);
            if matches!(mode, "eq" | "quake" | "earthquake") && unit.flying {
                continue;
            }
            let d = unit.dist(bx, by);
            // spells.py:1295-1297: equal distances use the entering troop's ID.
            if target.is_none()
                || d < distance
                || d == distance
                    && target.is_some_and(|previous: UnitRef| unit.id.0 < previous.id.0)
            {
                target = Some(reference);
                distance = d;
            }
        }
    }
    let (x, y) = target.map_or((bx, by), |unit| {
        battle.entity_position(EntityRef::Unit(unit))
    });
    let (kind, x, y, radius, until, value, started) = match mode {
        "rage" => ("def_rage", bx, by, 5.0, t + 18.0, 1.6, t),
        "poison" => {
            add_defensive_poison(
                battle,
                x,
                y,
                PoisonConfig {
                    dps: 60.0,
                    time: Some(12.0),
                    slow: Some(0.35),
                    radius: Some(5.0),
                    atk: Some(0.25),
                    ramp: false,
                    hero_mult: 0.2,
                    unknown: Vec::new(),
                },
                "tower",
            );
            return;
        }
        "invis" => ("def_invis", bx, by, 4.5, t + 4.5, 0.0, t),
        "eq" | "quake" | "earthquake" => {
            // spells.py:1121-1126: the tower's value is per hit, rather than per cast.
            let row = battle
                .catalog
                .game_data("spells", "Spell Tower Earthquake", None);
            let percentage = game_int(row, "TroopDamagePermil", 0) as f64 / 1000.0;
            ("def_quake", x, y, 4.7, t + 0.3, percentage, t + 0.3)
        }
        _ => return,
    };
    battle.fields.push(Field {
        identity: 0,
        kind: Tag::from(kind),
        x,
        y,
        radius,
        until,
        team: Team::Def,
        value,
        extra: FieldExtra::default(),
        started,
    });
}

// spells.py:1042-1078: source-field cost and tuple-min x/y tie breaking.
pub fn escape_poison(battle: &mut Battle, reference: UnitRef) -> bool {
    use crate::grid::{INF, RES};
    let u = battle.unit(reference);
    if u.is_hero || matches!(u.name_id, Name::Healer | Name::Druid) || u.speed <= 0.0 {
        return false;
    }
    let (ux, uy, flying) = (u.x, u.y, u.flying);
    let saved = u.extra.poison_exit.clone();
    let clouds: Vec<_> = battle
        .fields
        .iter()
        .filter(|f| f.kind == Tag::Poison && f.started <= battle.t && battle.t < f.until)
        .map(|f| (f.identity as u64, f.x, f.y, f.radius))
        .collect();
    if !clouds
        .iter()
        .any(|(_, x, y, radius)| py_hypot(ux - x, uy - y) <= *radius)
    {
        battle.unit_mut(reference).extra.poison_exit = None;
        return false;
    }
    let identities: Vec<_> = clouds.iter().map(|(id, _, _, _)| *id).collect();
    let grid = battle.navigation_grid(reference);
    let version = grid.version;
    let destination = if let Some((_, _, point)) =
        saved.filter(|(v, ids, _)| *v == version && *ids == identities)
    {
        point
    } else {
        let costs = (!flying).then(|| grid.source_field(ux, uy, 0.0));
        let mut best: Option<(f64, f64, f64)> = None;
        for i in 0..grid.n {
            for j in 0..grid.n {
                let cell = grid.index(i, j);
                let cost = if let Some(costs) = costs {
                    if grid.blocked[cell] {
                        continue;
                    }
                    let cost = grid.distance(costs, cell);
                    if cost >= INF {
                        continue;
                    }
                    Some(cost as f64)
                } else {
                    None
                };
                let (x, y) = ((i as f64 + 0.5) / RES as f64, (j as f64 + 0.5) / RES as f64);
                if clouds
                    .iter()
                    .all(|(_, cx, cy, radius)| py_hypot(x - cx, y - cy) > *radius)
                {
                    let candidate = (cost.unwrap_or_else(|| py_hypot(ux - x, uy - y)), x, y);
                    if best.is_none_or(|previous| candidate < previous) {
                        best = Some(candidate);
                    }
                }
            }
        }
        let Some((_, x, y)) = best else {
            return false;
        };
        (x, y)
    };
    battle.unit_mut(reference).extra.poison_exit = Some((version, identities, destination));
    battle.move_towards(reference, EntityRef::Unit(reference), Some(destination));
    true
}

// spells.py:1226-1238: recalled clones pause expiry; others vanish without death effects.
pub fn clone_expiry(battle: &mut Battle) {
    if battle.clones.is_empty() {
        return;
    }
    let mut keep = Vec::new();
    for reference in battle.clones.clone() {
        let u = battle.unit(reference);
        if u.extra.recalled.is_some() {
            keep.push(reference);
        } else if u.alive && battle.t >= u.extra.expire_at {
            battle.unit_mut(reference).alive = false;
        } else if u.alive
            || battle.portal_stash.iter().any(
                |value| matches!(value, Value::Ref(EntityRef::Unit(unit)) if *unit == reference),
            )
        {
            keep.push(reference);
        }
    }
    battle.clones = keep;
}

// spells.py:27-43,103-254. The stock's already resolved level wins.
pub fn cast_effect(
    battle: &mut Battle,
    name: &str,
    x: f64,
    y: f64,
    level: Option<crate::stats::Level>,
) -> usize {
    use crate::stats::{self, Level};
    let level = level
        .filter(|lv| *lv != Level::Int(0))
        .or_else(|| {
            if let Some(p) = battle.plan.attack() {
                p.spell_levels
                    .iter()
                    .find(|(key, _)| key == name)
                    .and_then(|(_, lv)| lv.clone())
            } else {
                None
            }
        })
        .unwrap_or_else(|| {
            Level::Int(
                battle
                    .catalog
                    .stats
                    .max_level(name, battle.plan.town_hall())
                    .expect("spell max level"),
            )
        });
    battle.start_battle();
    if battle.first_deploy_t.is_none() {
        battle.first_deploy_t = Some(battle.t);
    }
    let t = if name == "Revive Spell" {
        battle.t
    } else {
        battle.t + battle.params.spell_landing_delay
    };
    battle.log_event(vec![
        round_decimal(battle.t, 1).into(),
        "spell".into(),
        name.into(),
        round_decimal(x, 1).into(),
        round_decimal(y, 1).into(),
    ]);
    let stats = &battle.catalog.stats;
    let get = |keys: &[&str], default: f64| {
        stats
            .get(name, &level, keys, Some(default))
            .expect("spell number")
    };
    let raw = |key: &str, default: f64| {
        stats
            .attrs(name)
            .get("raw")
            .and_then(|r| r.get(key))
            .map_or(default, |v| stats::num(v, Some(default)).unwrap_or(default))
    };
    let radius = || {
        battle
            .catalog
            .resolved
            .at("spell_radii")
            .at(&format!("{name}|{level}"))
            .f64()
    };
    let mut f = match name {
        "Lightning Spell" => {
            let mut f = Field::new("lightning", x, y, radius(), t);
            f.value = get(&["damage", "Damage"], 640.0);
            f
        }
        "Healing Spell" => {
            let mut f = Field::new("heal", x, y, 5.0, t + 12.0);
            f.value = get(&["Healing per Pulse"], 60.0);
            f.extra.pulses = 41;
            f.extra.has_pulses = true;
            f.extra.gap = Some(0.3);
            f
        }
        "Rage Spell" => {
            let mut f = Field::new("rage", x, y, 5.0, t + 18.0);
            f.value = 1.0 + get(&["Damage Increase"], 180.0) / 100.0;
            f.extra.speed = Some(get(&["Speed Increase"], 30.0) / 8.0);
            f.extra.pulses = 60;
            f.extra.has_pulses = true;
            f.extra.gap = Some(0.3);
            f
        }
        "Jump Spell" => Field::new("jump", x, y, radius(), t + get(&["duration"], 60.0)),
        "Freeze Spell" => {
            let lv = if let Level::Int(lv) = &level {
                *lv as f64
            } else {
                panic!("integer Freeze level")
            };
            let mut f = Field::new("freeze", x, y, 3.5, t);
            f.value = get(&["Freeze Time"], 2.0 + 0.5 * lv);
            f
        }
        "Poison Spell" => {
            let mut f = Field::new("poison", x, y, 4.0, t + raw("Spell Duration", 16.0));
            f.value = get(&["Max damage per second"], 340.0);
            f.extra.slow = get(&["Speed Decrease"], 50.0) / 100.0;
            f.extra.atk = get(&["Attack Rate Decrease"], 72.0) / 100.0;
            f
        }
        "Earthquake Spell" => {
            let mut f = Field::new("quake", x, y, radius(), t);
            // spells.py:150-164: registry percentages describe all five impacts.
            let row = battle
                .catalog
                .game_data("spells", "Earthquake", Some(&level));
            let denominator = 100.0 * game_int(row, "NumberOfHits", 0) as f64;
            f.value = get(&["Building Damage %"], 29.0) / denominator;
            f.extra.troop = get(&["Troop Damage %"], 0.0) / denominator;
            f
        }
        "Haste Spell" => {
            let mut f = Field::new("haste", x, y, radius(), t + get(&["Spell Duration"], 30.0));
            f.extra.speed = Some(get(&["Speed Increase"], 52.0) / 8.0);
            f
        }
        "Clone Spell" => {
            let mut f = Field::new("clone", x, y, 3.5, t + 18.0);
            f.value = get(&["Cloned Capacity"], 42.0);
            f
        }
        "Skeleton Spell" | "Bat Spell" => {
            let (unit, n, first, gap) = if name == "Skeleton Spell" {
                (
                    "Spell Skeleton",
                    get(&["Skeletons generated"], 19.0),
                    3,
                    1.0,
                )
            } else {
                ("Bat", get(&["Bats generated"], 22.0), 1, 0.6)
            };
            let mut f = Field::new("summon", x, y, radius(), t + (n - first as f64) * gap);
            f.value = n;
            f.extra.unit = Some(unit.to_owned());
            f.extra.first = Some(first);
            f.extra.gap = Some(gap);
            f
        }
        "Bag of Frostmites" => {
            let mut f = Field::new("summon", x, y, 1.75, t);
            f.value = get(&["Frostmites spawned"], 17.0);
            f.extra.unit = Some("Frostmite".to_owned());
            f.extra.freeze = stats.get(name, &level, &["Freeze Time"], None);
            f
        }
        "Invisibility Spell" => Field::new("invis", x, y, 4.0, t + get(&["Duration"], 4.25)),
        "Recall Spell" => {
            let mut f = Field::new("recall", x, y, 5.0, t);
            f.value = get(&["Recalled Capacity"], 107.0);
            f
        }
        "Overgrowth Spell" => {
            let mut f = Field::new("overgrowth", x, y, 6.0, t);
            f.value = get(&["Duration"], 25.0);
            f
        }
        "Revive Spell" => {
            let mut f = Field::new("revive_cast", x, y, 8.0, t);
            f.value = get(&["Hero Heal %"], 70.0) / 100.0;
            f
        }
        "Ice Block Spell" => {
            let mut f = Field::new("iceblock", x, y, 5.0, t);
            f.value = get(&["Incoming Damage Reduction"], 92.0) / 100.0;
            f.extra.time = get(&["Duration"], 7.0);
            f
        }
        "Totem Spell" => {
            let mut f = Field::new("totem", x, y, 5.0, t);
            f.value = get(&["Totem Hitpoints"], 11000.0);
            f
        }
        "Angry Spell" => {
            let mut f = Field::new("angry", x, y, 6.0, t + get(&["Duration"], 5.0));
            f.value = get(&["Anger Duration"], 8.0);
            f
        }
        "Santa's Surprise" => {
            let mut f = Field::new("santa", x, y, 1.0, t + 0.4);
            f.value = get(&["Damage per Strike"], 370.0);
            f.extra.pulses = 5;
            f.extra.has_pulses = true;
            f.extra.gap = Some(0.1);
            f
        }
        "Birthday Boom" => {
            let mut f = Field::new("birthday", x, y, 2.5, t);
            f.value = get(&["Damage"], 0.0);
            f.extra.town_hall = get(&["Damage vs Town Hall"], 0.0);
            f.extra.freeze = Some(get(&["Freeze Duration"], 0.0));
            f
        }
        "Yellow Card" => {
            let mut f = Field::new("yellow", x, y, 7.0, t);
            f.value = get(&["Duration"], 0.0);
            f
        }
        _ => panic!("unknown spell {name}"),
    };
    f.started = t;
    f.extra.name = Some(name.to_owned());
    let index = battle.fields.len();
    battle.fields.push(f);
    index
}

// spells.py:1102-1114.
fn retarget(battle: &mut Battle, target: EntityRef) {
    match target {
        EntityRef::Building(id) => {
            if let Some(w) = &mut battle.building_mut(id).weapon {
                w.target = None;
                w.multi.clear();
                w.lock_time = 0.0;
                w.burst_left = 0;
            }
        }
        EntityRef::Unit(reference) => {
            let u = battle.unit_mut(reference);
            u.target = None;
            u.wall_target = None;
            units::interrupt_attack(battle, reference);
        }
        _ => panic!("spell retarget expects a building or unit"),
    }
}

// spells.py:325-350,351-371.
fn damaging_field(battle: &mut Battle, f: &Field, birthday: bool) -> bool {
    let t = battle.t;
    if !birthday {
        battle.src = Source::Literal("spell");
    }
    let stun = if birthday {
        0.0
    } else {
        let raw = battle
            .catalog
            .stats
            .attrs("Lightning Spell")
            .at("raw")
            .at("Stun Time");
        crate::stats::num(raw, None).expect("Lightning stun time")
    };
    for index in 0..battle.buildings.len() {
        let b = &battle.buildings[index];
        if !b.alive
            || b.key == "tesla" && !b.revealed
            || b.edge_distance(f.x, f.y) > f.radius
            || !birthday && matches!(b.key.as_str(), "gs" | "es" | "ds" | "th" | "cc")
        {
            continue;
        }
        let id = b.id;
        let damage = if birthday && b.key == "th" {
            f.extra.town_hall
        } else {
            f.value
        };
        battle.hit_building(EntityRef::Building(id), damage, None, "normal");
        let b = battle.building_mut(id);
        if birthday {
            b.frozen_until = b
                .frozen_until
                .max(t + f.extra.freeze.expect("Birthday freeze"));
            retarget(battle, EntityRef::Building(id));
        } else if b.weapon.is_some() {
            b.stun_until = b.stun_until.max(t + stun);
            retarget(battle, EntityRef::Building(id));
        }
    }
    for index in 0..battle.walls.len() {
        let w = &battle.walls[index];
        if w.alive && w.edge_distance(f.x, f.y) <= f.radius {
            battle.hit_building(EntityRef::Wall(w.id), f.value, None, "normal");
        }
    }
    for reference in battle.defenders_near(f.x, f.y, f.radius) {
        battle.hit_unit(reference, f.value, None, "normal", None);
        let u = battle.unit_mut(reference);
        if birthday {
            u.frozen_until = u
                .frozen_until
                .max(t + f.extra.freeze.expect("Birthday freeze"));
        } else {
            u.stun_until = u.stun_until.max(t + stun);
        }
        retarget(battle, EntityRef::Unit(reference));
    }
    false
}

// spells.py:372-400: building candidates precede defending heroes.
fn yellow(battle: &mut Battle, f: &Field) -> bool {
    let mut candidates: Vec<_> = battle
        .buildings
        .iter()
        .filter(|b| {
            b.alive
                && b.weapon
                    .as_ref()
                    .is_some_and(|w| w.kind != Tag::BhRepairOnly)
                && !b.extra.unavailable
                && (b.key != "tesla" || b.revealed)
                && (b.is_defense || b.key == "th")
                && b.edge_distance(f.x, f.y) <= f.radius
        })
        .map(|b| EntityRef::Building(b.id))
        .collect();
    candidates.extend(
        battle
            .defenders_near(f.x, f.y, f.radius)
            .into_iter()
            .filter(|r| battle.unit(*r).is_hero)
            .map(EntityRef::Unit),
    );
    let mut best = None;
    let mut closest = f64::INFINITY;
    for target in candidates {
        let d = crate::heroes::distance(battle, target, f.x, f.y);
        if best.is_none() || d < closest {
            best = Some(target);
            closest = d;
        }
    }
    if let Some(target) = best {
        let t = battle.t;
        let until = match target {
            EntityRef::Building(id) => &mut battle.building_mut(id).extra.yellow_until,
            EntityRef::Unit(r) => &mut battle.unit_mut(r).extra.yellow_until,
            _ => unreachable!(),
        };
        if t >= *until {
            *until = t + f.value;
            retarget(battle, target);
        }
    }
    false
}

// spells.py:401-414.
fn santa(battle: &mut Battle, f: &mut Field) -> bool {
    for _ in pulses(f, battle.t) {
        let angle = battle.rng.as_mut().expect("battle rng").random() * 2.0 * std::f64::consts::PI;
        let radius = battle.rng.as_mut().expect("battle rng").random() * f.radius;
        let (x, y) = (
            f.x + radius * crate::geom::py_cos(angle),
            f.y + radius * crate::geom::py_sin(angle),
        );
        for index in 0..battle.buildings.len() {
            let b = &battle.buildings[index];
            if b.alive && b.edge_distance(x, y) <= 1.5 {
                battle.hit_building(EntityRef::Building(b.id), f.value, None, "normal");
            }
        }
        for unit in battle.defenders_near(x, y, 1.5) {
            battle.hit_unit(unit, f.value, None, "normal", None);
        }
    }
    f.extra.delivered < f.extra.pulses
}

// spells.py:415-421.
fn heal(battle: &mut Battle, f: &mut Field) -> bool {
    for _ in pulses(f, battle.t) {
        for unit in battle.attackers_near(f.x, f.y, f.radius) {
            let u = battle.unit_mut(unit);
            if u.alive && !matches!(u.kind, Tag::Siege | Tag::SiegeIdle) {
                u.heal(f.value * if u.is_hero { 0.55 } else { 1.0 });
            }
        }
    }
    f.extra.delivered < f.extra.pulses
}

// spells.py:422-464.
fn rage(battle: &mut Battle, f: &mut Field) -> bool {
    let due = if f.extra.has_pulses {
        pulses(f, battle.t)
    } else {
        vec![battle.t]
    };
    let Some(&last) = due.last() else {
        return battle.t < f.until;
    };
    let pool = if f.team == Team::Atk {
        battle.attackers_near(f.x, f.y, f.radius)
    } else {
        battle.defenders_near(f.x, f.y, f.radius)
    };
    for reference in pool {
        let u = battle.unit(reference);
        if !affected(u) {
            continue;
        }
        let mut inc = f.value - 1.0;
        let mut speed = f.extra.speed.expect("Rage speed");
        if u.is_hero {
            inc *= 0.5;
            speed *= 0.5;
        }
        let key = source(battle, f);
        units::add_rage(
            battle.unit_mut(reference),
            key,
            1.0 + inc,
            speed,
            last + f.extra.boost_time,
        );
    }
    if f.team == Team::Def {
        if let Some(damage) = f.extra.defense_damage {
            for b in &mut battle.buildings {
                if b.alive && b.weapon.is_some() && b.edge_distance(f.x, f.y) <= f.radius {
                    b.rage_mult = (if battle.t < b.rage_until {
                        b.rage_mult
                    } else {
                        1.0
                    })
                    .max(damage);
                    b.rage_until = b.rage_until.max(last + f.extra.boost_time);
                }
            }
        }
    }
    true
}

// spells.py:518-531.
fn haste(battle: &mut Battle, f: &mut Field) -> bool {
    if battle.t > f.until {
        return false;
    }
    let Some(pulse) = application(f, battle.t, 0.25) else {
        return true;
    };
    for reference in battle.attackers_near(f.x, f.y, f.radius) {
        let u = battle.unit(reference);
        if affected(u) {
            let speed = f.extra.speed.expect("Haste speed") * if u.is_hero { 0.5 } else { 1.0 };
            let key = source(battle, f);
            crate::plans::set(
                &mut battle.unit_mut(reference).extra.haste_effects,
                key,
                (speed, pulse + 1.0),
            );
        }
    }
    true
}

// spells.py:532-540.
fn jump(battle: &mut Battle, f: &mut Field) -> bool {
    if battle.t > f.until {
        return false;
    }
    let Some(pulse) = application(f, battle.t, 0.25) else {
        return true;
    };
    // spells.py:561-563: JumpBoostMS=400, rather than a one-second tail.
    let row = battle.catalog.game_data("spells", "Jump", None);
    let boost_time = game_int(row, "JumpBoostMS", 0) as f64 / 1000.0;
    let until = pulse + boost_time;
    for reference in battle.attackers_near(f.x, f.y, f.radius) {
        let u = battle.unit_mut(reference);
        if affected(u) && !u.flying {
            u.extra.jump_until = u.extra.jump_until.max(until);
            u.wall_target = None;
        }
    }
    true
}

// spells.py:542-551.
fn freeze(battle: &mut Battle, f: &mut Field) -> bool {
    let until = battle.t + f.value;
    for b in &mut battle.buildings {
        if b.alive
            && b.weapon.is_some()
            && b.edge_distance(f.x, f.y) <= f.radius
            && !(b.key == "tesla" && !b.revealed)
        {
            b.frozen_until = b.frozen_until.max(until);
        }
    }
    for reference in battle.defenders_near(f.x, f.y, f.radius) {
        let u = battle.unit_mut(reference);
        u.frozen_until = u.frozen_until.max(until);
    }
    f.kind = Tag::TeslaFreeze;
    f.until = until;
    true
}

// spells.py:552-565.
fn attacker_poison(battle: &mut Battle, f: &mut Field) -> bool {
    for reference in battle.defenders_near(f.x, f.y, f.radius) {
        let multiplier = if battle.unit(reference).is_hero {
            POISON_HERO_MULT
        } else {
            1.0
        };
        let StatusSource::Field(serial) = source(battle, f) else {
            unreachable!()
        };
        poison(
            battle,
            reference,
            f.value,
            f.extra.slow,
            f.extra.atk,
            multiplier,
            PoisonOptions {
                ramp: true,
                origin: "spell",
                source: Some(("field".to_owned(), serial)),
                source_until: Some(f.until),
                refresh: 0.2,
            },
        );
    }
    true
}

// spells.py:615-636: schedule all impacts now; counters belong to the cast.
fn quake(battle: &mut Battle, field: &Field) -> bool {
    let defensive = field.kind == Tag::DefQuake;
    let name = if defensive {
        "Spell Tower Earthquake"
    } else {
        "Earthquake"
    };
    let row = battle.catalog.game_data("spells", name, None);
    let count = game_int(row, "NumberOfHits", 0);
    let gap = game_int(row, "TimeBetweenHitsMS", 0) as f64 / 1000.0;
    let shared = Rc::new(RefCell::new(field.clone()));
    for index in 0..count {
        let mut pending = Pending::new(
            crate::geom::round6(field.started + index as f64 * gap),
            field.x,
            field.y,
            field.radius,
            0.0,
            false,
            true,
            if defensive { "spell_tower" } else { "spell" },
        );
        pending.team = if defensive { Team::Atk } else { Team::Def };
        pending.extra.quake = Some(Rc::clone(&shared));
        pending.effect = Some(Tag::Spell);
        battle.add_pending(pending);
    }
    false
}

// spells.py:823-866: diminish by the cast's first contact with each entity.
pub fn quake_hit(battle: &mut Battle, field: &mut Field) {
    if field.kind == Tag::Quake {
        for index in 0..battle.buildings.len() {
            let b = &mut battle.buildings[index];
            if b.alive
                && b.counted
                && !matches!(b.key.as_str(), "gs" | "es" | "ds")
                && !(b.key == "tesla" && !b.revealed)
                && b.edge_distance(field.x, field.y) <= field.radius
            {
                let target = EntityRef::Building(b.id);
                let count = match field
                    .extra
                    .quake_hits
                    .iter()
                    .find(|(key, _)| *key == target)
                {
                    Some((_, count)) => *count,
                    None => {
                        b.eq_hits += 1;
                        field.extra.quake_hits.push((target, b.eq_hits));
                        b.eq_hits
                    }
                };
                let damage = b.max_hp * field.value / (2 * count - 1) as f64;
                battle.hit_building(target, damage, None, "normal");
            }
        }
        for index in 0..battle.walls.len() {
            let wall = &mut battle.walls[index];
            if wall.alive && wall.edge_distance(field.x, field.y) <= field.radius {
                let target = EntityRef::Wall(wall.id);
                let count = match field
                    .extra
                    .quake_hits
                    .iter()
                    .find(|(key, _)| *key == target)
                {
                    Some((_, count)) => *count,
                    None => {
                        wall.eq_hits += 1;
                        field.extra.quake_hits.push((target, wall.eq_hits));
                        wall.eq_hits
                    }
                };
                let n = count as f64;
                // Keep Python's pow and multiplication order for the wall bonus.
                let damage =
                    wall.max_hp * (field.value / n + 0.01 * crate::geom::py_pow(n - 1.0, 2.0));
                battle.hit_building(target, damage, None, "normal");
            }
        }
    }
    let percentage = if field.kind == Tag::Quake {
        field.extra.troop
    } else {
        field.value
    };
    if percentage == 0.0 {
        return;
    }
    let pool = if field.kind == Tag::Quake {
        battle.defenders_near(field.x, field.y, field.radius)
    } else {
        battle.attackers_near(field.x, field.y, field.radius)
    };
    for reference in pool {
        let u = battle.unit_mut(reference);
        if u.flying || field.kind == Tag::DefQuake && !affected(u) {
            continue;
        }
        let target = EntityRef::Unit(reference);
        let count = match field
            .extra
            .quake_hits
            .iter()
            .find(|(key, _)| *key == target)
        {
            Some((_, count)) => *count,
            None => {
                u.extra.eq_n += 1;
                field.extra.quake_hits.push((target, u.extra.eq_n));
                u.extra.eq_n
            }
        };
        let damage = u.max_hp * percentage / (2 * count - 1) as f64;
        battle.hit_unit(reference, damage, None, "normal", None);
    }
}

// spells.py:782-786: equipment and spells share the same hit counter. Store
// the increment after the hit, whose callbacks may inspect the previous value.
pub fn quake_unit(battle: &mut Battle, unit: UnitRef, percentage: f64) {
    let u = battle.unit(unit);
    let n = u.extra.eq_n;
    let damage = u.max_hp * percentage / (2 * n + 1) as f64;
    battle.hit_unit(unit, damage, None, "normal", None);
    battle.unit_mut(unit).extra.eq_n = n + 1;
}

// spells.py:850-870: x-major free tile order, int truncation at bounds.
fn spawn_spots(battle: &Battle, x: f64, y: f64, radius: f64, flying: bool) -> Vec<(f64, f64)> {
    let mut spots = Vec::new();
    for tx in (x - radius) as i32..=(x + radius) as i32 {
        for ty in (y - radius) as i32..=(y + radius) as i32 {
            let (cx, cy) = (tx as f64 + 0.5, ty as f64 + 0.5);
            if py_hypot(cx - x, cy - y) > radius {
                continue;
            }
            let world = battle.catalog.world as f64;
            if !(0.0 <= cx && cx < world && 0.0 <= cy && cy < world) {
                continue;
            }
            if flying {
                spots.push((cx, cy));
                continue;
            }
            if battle
                .wall_indices
                .get(&(tx, ty))
                .is_some_and(|id| battle.walls[id.0].alive)
            {
                continue;
            }
            let (i, j) = battle.grid.cell(cx, cy);
            if battle.grid.blocked[battle.grid.index(i, j)] {
                continue;
            }
            spots.push((cx, cy));
        }
    }
    spots
}

// spells.py:619-662.
fn clone_field(battle: &mut Battle, f: &mut Field) -> bool {
    if battle.t >= f.until {
        return false;
    }
    if application(f, battle.t, 0.3).is_none() {
        return true;
    }
    let mut capacity = f.value;
    let mut sources = battle.attackers_near(f.x, f.y, f.radius);
    sources.sort_by(|a, b| {
        let a = battle.unit(*a);
        let b = battle.unit(*b);
        a.spawned_at.total_cmp(&b.spawned_at).then_with(|| {
            a.extra
                .spawn_sequence
                .unwrap_or(a.id.0)
                .cmp(&b.extra.spawn_sequence.unwrap_or(b.id.0))
        })
    });
    for reference in sources {
        let u = battle.unit(reference);
        if !affected(u) || u.is_hero || u.kind == Tag::Pet {
            continue;
        }
        let StatusSource::Field(serial) = source(battle, f) else {
            unreachable!()
        };
        let key = ("field".to_owned(), serial);
        let u = battle.unit(reference);
        if u.extra.clone_casts.contains(&key) {
            continue;
        }
        let housing = interaction_housing(u) as f64;
        let (name, level, group, flying, casts) = (
            u.name.clone(),
            u.level.clone(),
            u.group.clone(),
            u.flying,
            u.extra.clone_casts.clone(),
        );
        while housing <= capacity {
            capacity -= housing;
            let spots = spawn_spots(battle, f.x, f.y, f.radius, flying);
            if spots.is_empty() {
                return false;
            }
            let index = battle.rng.as_mut().expect("battle rng").below(spots.len());
            let (x, y) = spots[index];
            let child = battle.spawn(
                &name,
                Team::Atk,
                x,
                y,
                crate::battle::SpawnOptions {
                    level: level.clone(),
                    kind: Tag::Summon,
                    group: group.clone(),
                    ..Default::default()
                },
            );
            let t = battle.t;
            let strength = battle.unit(reference).extra.strength;
            let u = battle.unit_mut(child);
            // spells.py:738-746: copies retain the original's calibrated strength.
            if strength != 1.0 {
                u.hp *= strength;
                u.max_hp *= strength;
                u.base_max_hp *= strength;
                u.dmg *= strength;
                u.extra.strength = strength;
            }
            u.extra.clone_casts = casts.clone();
            if !u.extra.clone_casts.contains(&key) {
                u.extra.clone_casts.push(key.clone());
            }
            u.extra.clone = true;
            u.extra.expire_at = t + 30.0;
            if u.spec.has_special(Special::StartRage) {
                u.extra
                    .rage_effects
                    .retain(|(source, _)| *source != StatusSource::Name("innate".to_owned()));
            }
            battle.clones.push(child);
        }
    }
    f.value = capacity;
    capacity > 0.0
}

// spells.py:664-698.
fn summon(battle: &mut Battle, f: &mut Field) -> bool {
    let n = f.value as usize;
    let name = f
        .extra
        .unit
        .as_deref()
        .expect("spell summon name")
        .to_owned();
    if f.extra.spots.is_none() {
        if let Some(duration) = f.extra.freeze {
            let mut freeze = Field::new("freeze", f.x, f.y, f.radius, battle.t);
            freeze.started = battle.t;
            freeze.value = duration;
            apply(battle, &mut freeze);
            battle.fields.push(freeze);
        }
        f.extra.spots = Some(spawn_spots(battle, f.x, f.y, f.radius, name == "Bat"));
    }
    let spots = f.extra.spots.as_ref().expect("summon spots");
    if spots.is_empty() {
        return false;
    }
    let first = f.extra.first.unwrap_or(n);
    let gap = f.extra.gap.unwrap_or(0.0);
    let mut j = f.extra.delivered;
    while j < n {
        let at = f.started + (j as i64 - first as i64 + 1).max(0) as f64 * gap;
        if at > battle.t && !close(at, battle.t) {
            break;
        }
        let (x, y) = spots[j % spots.len()];
        j += 1;
        f.extra.delivered = j;
        let child = battle.spawn(
            &name,
            Team::Atk,
            x,
            y,
            crate::battle::SpawnOptions {
                kind: Tag::Summon,
                group: "spell".to_owned(),
                ..Default::default()
            },
        );
        // spells.py:708-717: only future spawns inside each retained cast area freeze.
        for (source, (reduction, until, cx, cy, radius)) in &f.extra.iceblocks {
            if battle.t < *until && crate::geom::dist(x, y, *cx, *cy) <= *radius {
                let child = battle.unit_mut(child);
                crate::plans::set(
                    &mut child.extra.iceblocks,
                    source.clone(),
                    (*reduction, *until),
                );
                child.frozen_until = child.frozen_until.max(*until);
            }
        }
        if f.extra.name.as_deref() == Some("Bag of Frostmites") {
            let u = battle.unit_mut(child);
            u.extra.bouncing_frostmite = true;
            std::sync::Arc::make_mut(&mut u.spec).splash = 0.8;
        }
    }
    j < n
}

// spells.py:699-712.
fn invis(battle: &mut Battle, f: &mut Field) -> bool {
    let Some(until) = invisibility_until(f, battle.t) else {
        return true;
    };
    for reference in battle.attackers_near(f.x, f.y, f.radius) {
        let u = battle.unit_mut(reference);
        if !matches!(u.kind, Tag::Siege | Tag::SiegeIdle) {
            u.invisible_until = u.invisible_until.max(until);
        }
    }
    for reference in battle.defenders_near(f.x, f.y, f.radius) {
        let u = battle.unit_mut(reference);
        u.invisible_until = u.invisible_until.max(until);
    }
    if f.team == Team::Atk {
        // output/research/usage/invisibility-spell.md: use building centres.
        // https://www.reddit.com/r/ClashOfClans/comments/1l4z2tu/guide_to_attacking_invisibility_spell_tower_bases/
        for b in &mut battle.buildings {
            if b.alive && crate::geom::dist(b.x, b.y, f.x, f.y) <= f.radius {
                b.invisible_until = b.invisible_until.max(until);
            }
        }
    }
    true
}

// spells.py:1082-1099.
pub fn interaction_housing(unit: &Unit) -> i64 {
    if unit.is_hero {
        return 25;
    }
    if unit.kind == Tag::Pet {
        return 20;
    }
    match unit.name.as_str() {
        "Skeleton" | "Spell Skeleton" | "Bat" | "Frostmite" | "Lava Pup" | "Ice Pup" => 1,
        "Yetimite" => 2,
        "Golemite" => 6,
        "Big Boy" => 20,
        _ => unit.housing.max(1),
    }
}

// spells.py:1117-1151.
fn recall(battle: &mut Battle, f: &Field) -> bool {
    let mut capacity = f.value;
    let mut candidates = Vec::new();
    for reference in battle.attackers_near(f.x, f.y, f.radius) {
        let u = battle.unit(reference);
        if affected(u)
            && matches!(
                u.kind,
                Tag::Troop | Tag::Hero | Tag::HeroClone | Tag::Pet | Tag::Summon
            )
            && !candidates.contains(&reference)
        {
            candidates.push(reference);
        }
    }
    candidates.sort_by(|a, b| {
        let a = battle.unit(*a);
        let b = battle.unit(*b);
        (!a.is_hero, -interaction_housing(a))
            .cmp(&(!b.is_hero, -interaction_housing(b)))
            .then_with(|| a.spawned_at.total_cmp(&b.spawned_at))
            .then_with(|| {
                a.extra
                    .spawn_sequence
                    .unwrap_or(a.id.0)
                    .cmp(&b.extra.spawn_sequence.unwrap_or(b.id.0))
            })
    });
    let mut taken = Vec::new();
    for reference in candidates {
        let u = battle.unit(reference);
        let housing = interaction_housing(u) as f64;
        if crate::heroes::free_pet(battle, reference)
            || taken.contains(&reference)
            || housing > capacity
        {
            continue;
        }
        capacity -= housing;
        taken.push(reference);
        if u.is_hero {
            if let Some(pet) = u.pet {
                let p = battle.unit(pet);
                if p.alive && (p.extra.egg || p.attached(battle)) && !taken.contains(&pet) {
                    taken.push(pet);
                }
            }
        }
    }
    crate::heroes::stash(battle, taken, (0.0, 0.0, 0.0));
    false
}

// spells.py:729-739.
fn overgrowth(battle: &mut Battle, f: &mut Field) -> bool {
    let until = battle.t + f.value;
    for b in &mut battle.buildings {
        if b.alive && !(b.key == "tesla" && !b.revealed) && b.edge_distance(f.x, f.y) <= f.radius {
            b.overgrown_until = b.overgrown_until.max(until);
        }
    }
    f.kind = Tag::TeslaOvergrowth;
    f.until = until;
    true
}

// spells.py:740-751.
fn iceblock(battle: &mut Battle, f: &mut Field) -> bool {
    let until = battle.t + f.extra.time;
    // spells.py:763-783: save coverage for unspawned Skeletons and Bats.
    for index in 0..battle.fields.len() {
        let summon = &battle.fields[index];
        if summon.kind == Tag::Summon
            && matches!(summon.extra.unit.as_deref(), Some("Spell Skeleton" | "Bat"))
            && summon.started <= battle.t
            && battle.t <= summon.until
            && (summon.extra.delivered as f64) < summon.value
            && crate::geom::dist(summon.x, summon.y, f.x, f.y) <= summon.radius + f.radius
        {
            let key = source(battle, f);
            let coverage = (f.value, until, f.x, f.y, f.radius);
            crate::plans::set(&mut battle.fields[index].extra.iceblocks, key, coverage);
        }
    }
    for reference in battle.attackers_near(f.x, f.y, f.radius) {
        let u = battle.unit(reference);
        // spells.py:860-861: Ice Block has no effect during Rocket Backpack.
        // output/research/usage/ice-block-spell.md: October 2025 fixed
        // underground recipients, superseding the stale wiki exclusion.
        // https://supercell.com/en/games/clashofclans/blog/release-notes/get-ready-for-ranked-update/
        if affected(u) && u.dash.is_none() {
            let key = source(battle, f);
            let u = battle.unit_mut(reference);
            crate::plans::set(&mut u.extra.iceblocks, key, (f.value, until));
            u.frozen_until = u.frozen_until.max(until);
        }
    }
    false
}

// spells.py:755-767.
fn angry(battle: &mut Battle, f: &Field) -> bool {
    let t = battle.t;
    for reference in battle.attackers_near(f.x, f.y, f.radius) {
        let u = battle.unit(reference);
        let sp = &u.spec;
        if !u.alive
            || matches!(sp.attack, Tag::Heal | Tag::HealChain)
            || matches!(sp.prefer, Tag::Defense | Tag::AirDefense)
                && !matches!(u.name_id, Name::LavaHound | Name::IceHound)
            || matches!(u.name_id, Name::RuinWitch | Name::Totem)
            || matches!(u.kind, Tag::Siege | Tag::SiegeIdle)
        {
            continue;
        }
        if !u.extra.paused_timers.angry_until || u.extra.angry_until < t + f.value - 0.5 {
            let defense = u.target_kind.as_ref() == Some(&Tag::Building)
                && u.target
                    .is_some_and(|r| crate::plans::entity_is_defense(battle, r));
            let u = battle.unit_mut(reference);
            u.extra.angry_until = t + f.value;
            u.extra.paused_timers.angry_until = true;
            if !defense {
                u.target = None;
            }
        }
    }
    true
}

// spells.py:768-775.
fn revive_cast(battle: &mut Battle, f: &Field) -> bool {
    let mut best = None;
    let mut closest = f.radius;
    for u in battle.attackers_pool() {
        if u.is_hero && !u.alive && u.extra.revivable {
            let d = u.dist(f.x, f.y);
            // Python intentionally replaces the previous hero on equal distance.
            if d <= closest {
                best = Some(u.reference());
                closest = d;
            }
        }
    }
    if let Some(hero) = best {
        revive(battle, hero, f.value);
    }
    false
}

// spells.py:1214-1223.
fn revive(battle: &mut Battle, hero: UnitRef, percentage: f64) {
    let now = battle.t;
    if let Some(kit) = &mut battle.unit_mut(hero).kit {
        if kit.doomed_at.is_some_and(|deadline| deadline <= now) {
            kit.doomed_at = None;
        }
    }
    // spells.py:1302-1311: clear stale aura health, then recompute living coverage.
    effects::health_aura(battle.unit_mut(hero), 0.0, 0.0);
    battle.unit_mut(hero).alive = true;
    crate::heroes::apply_auras(battle);
    let u = battle.unit_mut(hero);
    u.extra.revivable = false;
    u.hp = u.max_hp * percentage;
    u.extra.aura_hp = u.aura_bonus * percentage;
    u.target = None;
    u.wall_target = None;
    u.cooldown = 0.0;
    u.frozen_until = 0.0;
    u.stun_until = 0.0;
    let name = u.name.clone();
    battle.log_event(vec![
        round_decimal(battle.t, 1).into(),
        "revive".into(),
        name.into(),
    ]);
}

#[cfg(test)]
mod phoenix_tests {
    use super::*;
    use crate::battle::SpawnOptions;
    use crate::heroes::Kit;

    #[test]
    fn both_terminal_phoenix_paths_allow_revive_without_reusing_phoenix() {
        for damage_death in [false, true] {
            let mut battle = crate::test_support::battle();
            let hero = battle.spawn(
                "Dragon Duke",
                Team::Atk,
                10.0,
                10.0,
                SpawnOptions {
                    kind: Tag::Hero,
                    ..Default::default()
                },
            );
            let mut kit = Kit::new("Dragon Duke");
            kit.phoenix = false;
            kit.doomed_at = Some(10.0);
            battle.unit_mut(hero).kit = Some(kit);
            battle.unit_mut(hero).ability_used = true;
            battle.t = 10.0;
            if damage_death {
                battle.unit_mut(hero).hp = 0.0;
                battle.kill(hero);
            } else {
                crate::heroes::tick(&mut battle, hero);
            }
            assert!(!battle.unit(hero).alive);
            assert!(battle.unit(hero).extra.revivable);
            assert_eq!(battle.unit(hero).kit.as_ref().unwrap().doomed_at, None);
            battle.t = 20.0;
            revive(&mut battle, hero, 0.5);
            crate::heroes::tick(&mut battle, hero);
            let unit = battle.unit(hero);
            assert!(unit.alive);
            assert!(unit.ability_used);
            assert!(!unit.kit.as_ref().unwrap().phoenix);
            battle.unit_mut(hero).hp = 0.0;
            battle.kill(hero);
            assert!(!battle.unit(hero).alive);
        }
    }

    #[test]
    fn revive_defensively_retires_an_expired_deadline() {
        let mut battle = crate::test_support::battle();
        let hero = battle.spawn(
            "Dragon Duke",
            Team::Atk,
            10.0,
            10.0,
            SpawnOptions {
                kind: Tag::Hero,
                ..Default::default()
            },
        );
        let mut kit = Kit::new("Dragon Duke");
        kit.doomed_at = Some(5.0);
        battle.unit_mut(hero).kit = Some(kit);
        battle.unit_mut(hero).alive = false;
        battle.t = 10.0;
        revive(&mut battle, hero, 0.5);
        crate::heroes::tick(&mut battle, hero);
        assert!(battle.unit(hero).alive);
        assert_eq!(battle.unit(hero).kit.as_ref().unwrap().doomed_at, None);
    }
}

// spells.py:1154-1196: Totem bypasses ordinary spawn/equipment hooks.
fn totem(battle: &mut Battle, f: &Field) -> bool {
    let spots = spawn_spots(battle, f.x, f.y, 7.0 / 2.0, false);
    let mut best = None;
    let mut distance = f64::INFINITY;
    for point in spots {
        let d = py_hypot(point.0 - f.x, point.1 - f.y);
        if best.is_none() || d < distance {
            best = Some(point);
            distance = d;
        }
    }
    let Some((x, y)) = best else {
        return false;
    };
    defense::builder_spell(battle, f);
    battle.uid += 1;
    let spec = crate::catalog::UnitSpec::totem();
    let decay = crate::traps::raw(
        battle,
        "Totem Spell",
        "Hitpoint Decay per Second",
        Some(334.0),
    )
    .expect("Totem decay");
    // output/research/usage/archer-queen.md and dark-crown.md: each Totem now
    // counts as one housing, including Monolith Arrow's deployment counter.
    // https://supercell.com/en/games/clashofclans/blog/release-notes/august-update-3/
    let unit = Unit {
        source: Source::Literal("unit:Totem"),
        name_id: Name::Totem,
        id: UnitId(battle.uid),
        name: "Totem".to_owned(),
        kind: Tag::Summon,
        team: Team::Atk,
        level: Some(crate::stats::Level::Int(1)),
        x,
        y,
        hp: f.value,
        max_hp: f.value,
        base_max_hp: f.value,
        dmg: 0.0,
        interval: 1.0,
        range: 0.0,
        speed: 0.0,
        housing: 1,
        flying: false,
        hits_air: false,
        hits_ground: false,
        spec: std::sync::Arc::new(spec),
        alive: true,
        cooldown: 0.0,
        target: None,
        target_kind: None,
        wall_target: None,
        group: "main".to_owned(),
        spawned_at: battle.t,
        active_at: battle.t,
        stuck: 0.0,
        frozen_until: 0.0,
        stun_until: 0.0,
        held_until: 0.0,
        invisible_until: 0.0,
        invuln_until: 0.0,
        move_slow: 1.0,
        move_slow_until: 0.0,
        atk_slow: 1.0,
        atk_slow_until: 0.0,
        rage_dmg: 1.0,
        rage_spd: 0.0,
        rage_until: 0.0,
        haste_spd: 0.0,
        haste_until: 0.0,
        iceblock_red: 0.0,
        iceblock_until: 0.0,
        dmg_taken_mult: 1.0,
        dmg_taken_until: 0.0,
        aura_bonus: 0.0,
        aura_dmg: 1.0,
        underground: false,
        aware_until: 0.0,
        last_hit: -100.0,
        poison_stack: 0,
        is_hero: false,
        kit: None,
        pet: None,
        owner: None,
        follow: None,
        home: None,
        leash: 0.0,
        ability_used: false,
        decay,
        dash: None,
        extra: UnitExtra::default(),
        damage_dealt: 0.0,
        in_pool: true,
    };

    let reference = unit.reference();
    battle.register_unit(unit.id, Team::Atk, battle.attackers.len());
    battle.monolith_housing += unit.housing;
    battle.attackers.push(unit);
    battle.attacker_order.push(reference);
    let until = battle.t + 0.2;
    for index in 0..battle.buildings.len() {
        let b = &mut battle.buildings[index];
        if b.alive && b.weapon.is_some() && b.edge_distance(f.x, f.y) <= f.radius {
            b.stun_until = b.stun_until.max(until);
            let id = b.id;
            retarget(battle, EntityRef::Building(id));
        }
    }
    for reference in battle.defenders_near(f.x, f.y, f.radius) {
        let u = battle.unit_mut(reference);
        u.stun_until = u.stun_until.max(until);
        retarget(battle, EntityRef::Unit(reference));
    }
    false
}
