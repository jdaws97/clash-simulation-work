//! Ports spells.py:258-280,283-779 (defensive fields),798-847,873-1078,1226-1238.

use crate::effects;
use crate::geom::py_hypot;
use crate::state::*;
use crate::trace::round_decimal;
use crate::{defense, traps, units};

pub const NO_TRIGGER: &[&str] = &["Spell Skeleton", "Skeleton", "Bat", "Totem"];

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
    unit.alive && !matches!(unit.kind.as_str(), "siege" | "siege_idle") && unit.name != "Totem"
}

// spells.py:258-280: snapshot original fields, preserve fields appended mid-tick.
pub fn tick(battle: &mut Battle) {
    let t = battle.t;
    let fields = battle.fields.clone();
    let count = fields.len();
    let mut keep = Vec::new();
    for mut field in fields {
        if t < field.started {
            keep.push(field);
            continue;
        }
        if field.kind == "tornado" && t >= field.until {
            traps::tornado_tick(battle, &mut field);
            expire(battle, &field);
            continue;
        }
        let alive = apply(battle, &mut field);
        if alive && t < field.until {
            keep.push(field);
        } else {
            expire(battle, &field);
        }
    }
    keep.extend(battle.fields.drain(count..));
    battle.fields = keep;
    poison_states(battle);
    clone_expiry(battle);
}

// spells.py:283-779: every later-stage field fails explicitly on entry.
pub fn apply(battle: &mut Battle, f: &mut Field) -> bool {
    let t = battle.t;
    let dt = battle.dt;
    let kind = f.kind.clone();
    if matches!(kind.as_str(), "poison" | "def_poison" | "def_rage" | "def_burn" | "rage" | "haste" | "invis" | "def_invis" | "angry")
        && t >= f.until {
        return false;
    }
    if matches!(kind.as_str(), "lightning" | "freeze" | "poison" | "def_rage")
        || kind == "rage"
        && f.team == Team::Def {
        defense::builder_spell(battle, f);
    }
    match kind.as_str() {
        // spells.py:308-324: residual freeze/overgrowth coverage for revealed Teslas.
        "tesla_freeze" | "tesla_overgrowth" => {
            if t >= f.until {
                return false;
            }
            if kind == "tesla_freeze" {
                defense::builder_spell(battle, f);
            }
            for building in &mut battle.buildings {
                if building.alive
                    && building.key == "tesla"
                    && building.revealed
                    && building.edge_distance(f.x, f.y) <= f.radius {
                    if kind == "tesla_freeze" {
                        building.frozen_until = building.frozen_until.max(f.until);
                    } else {
                        building.overgrown_until = building.overgrown_until.max(f.until);
                    }
                }
            }
            true
        }
        "lightning" => todo!("stage 4: spells.py:325 Lightning field"),
        "birthday" => todo!("stage 4: spells.py:351 Birthday field"),
        "yellow" => todo!("stage 4: spells.py:372 Yellow Card field"),
        "santa" => todo!("stage 4: spells.py:401 Santa field"),
        "heal" => todo!("stage 4: spells.py:415 Healing field"),
        "rage" => todo!("stage 2: spells.py:422 Super Valkyrie rage field (attacker spell stage 4)"),
        // spells.py:465-494: pool damage does not stack or gain defense difficulty.
        "def_burn" => {
            if !f.extra.has_pulses || !pulses(f, t).is_empty() {
                f.extra.victims = battle.attackers_near(f.x, f.y, f.radius).iter().map(|unit| unit.id).collect();
            }
            for reference in battle.attackers_near(f.x, f.y, f.radius) {
                let u = battle.unit(reference);
                if !u.alive
                    || u.underground
                    || u.extra.burn_tick == Some(t)
                    || !f.extra.victims.contains(&u.id) {
                    continue;
                }
                let mut damage = None;
                for field in &battle.fields {
                    if field.kind == "def_burn"
                        && field.started <= t
                        && t < field.until
                        && u.dist(field.x, field.y) <= field.radius {
                        damage = Some(damage.map_or(field.value, |previous: f64| previous.max(field.value)));
                    }
                }
                battle.unit_mut(reference).extra.burn_tick = Some(t);
                battle.hit_unit(reference, damage.unwrap_or(f.value) * dt, Some("th"), "normal", None);
            }
            true
        }
        "tornado" => {
            traps::tornado_tick(battle, f);
            true
        }
        // spells.py:500-517: defense rage does not stack with itself.
        "def_rage" => {
            let until = f.until.min(t + dt);
            for building in &mut battle.buildings {
                if building.alive
                    && building.weapon.is_some()
                    && building.edge_distance(f.x, f.y) <= f.radius {
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
                units::add_rage(battle.unit_mut(reference), status_source, 1.0 + (f.value - 1.0) * factor, 30.0 / 8.0 * factor, until);
            }
            true
        }
        "haste" => todo!("stage 4: spells.py:518 Haste field"),
        "jump" => todo!("stage 4: spells.py:532 Jump field"),
        "freeze" => todo!("stage 4: spells.py:542 Freeze field"),
        "poison" => todo!("stage 4: spells.py:552 attacking Poison field"),
        // spells.py:566-587.
        "def_poison" => {
            let gap = f.extra.gap.unwrap_or(dt);
            if application(f, t, gap).is_none() {
                return true;
            }
            for reference in battle.attackers_near(f.x, f.y, f.radius) {
                let u = battle.unit(reference);
                if affected(u)
                    || f.extra.origin.as_deref() == Some("town_hall")
                    && u.name == "Stone Slammer" {
                    let multiplier = if u.is_hero {
                        f.extra.hero_mult
                    } else {
                        1.0
                    };
                    let field_source = source(battle, f);
                    let StatusSource::Field(serial) = field_source else {
                        unreachable!()
                    };
                    poison(battle, reference, f.value, f.extra.slow, f.extra.atk, multiplier, PoisonOptions {
                        ramp: f.extra.ramp,
                        origin: f.extra.origin.as_deref().unwrap_or("tower"),
                        source: Some(("field".to_owned(), serial)),
                        source_until: Some(f.until), refresh: f.extra.gap.unwrap_or(0.2),
                    });
                }
            }
            true
        }
        "quake" => todo!("stage 4: spells.py:588 Earthquake field"),
        // spells.py:612-618: defensive Earthquake tower uses existing unit state.
        "def_quake" => {
            for reference in battle.attackers_near(f.x, f.y, f.radius) {
                let u = battle.unit_mut(reference);
                if affected(u) && !u.flying {
                    u.extra.eq_n += 1;
                    let amount = u.max_hp * f.value / (2 * u.extra.eq_n - 1) as f64;
                    battle.hit_unit(reference, amount, Some("spell_tower"), "normal", None);
                }
            }
            false
        }
        "clone" => todo!("stage 4: spells.py:619 Clone field"),
        "summon" => todo!("stage 4: spells.py:664 attacking spell summons"),
        "invis" => todo!("stage 4: spells.py:699 attacking Invisibility field"),
        // spells.py:713-725: each pulse grants 0.6 seconds of invisibility.
        "def_invis" => {
            let Some(until) = invisibility_until(f, t) else {
                return true;
            };
            for building in &mut battle.buildings {
                if building.alive && building.edge_distance(f.x, f.y) <= f.radius {
                    building.invisible_until = building.invisible_until.max(until);
                }
            }
            for reference in battle.defenders_near(f.x, f.y, f.radius) {
                let u = battle.unit_mut(reference);
                u.invisible_until = u.invisible_until.max(until);
            }
            for reference in battle.attackers_near(f.x, f.y, f.radius) {
                let u = battle.unit_mut(reference);
                if !matches!(u.kind.as_str(), "siege" | "siege_idle") {
                    u.invisible_until = u.invisible_until.max(until);
                }
            }
            true
        }
        "recall" => todo!("stage 4: spells.py:726 Recall field"),
        "overgrowth" => todo!("stage 4: spells.py:729 Overgrowth field"),
        "iceblock" => todo!("stage 4: spells.py:740 Ice Block field"),
        "totem" => todo!("stage 4: spells.py:752 Totem field"),
        "angry" => todo!("stage 4: spells.py:755 Angry field"),
        "revive_cast" => todo!("stage 4: spells.py:768 Revive cast field"),
        "revive_due" => todo!("stage 4: spells.py:776 delayed Revive field"),
        _ => false,
    }
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
    a == b || (a.is_finite() && b.is_finite() && ((a - b).abs() <= (1e-9 * b).abs() || (a - b).abs() <= (1e-9 * a).abs()))
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
pub fn expire(_battle: &mut Battle, _field: &Field) {
}

// spells.py:841-847.
pub fn wall_jumped(battle: &Battle, wall: WallId) -> bool {
    let w = &battle.walls[wall.0];
    battle.fields.iter().any(|field| field.kind == "jump" && field.started <= battle.t && battle.t < field.until && py_hypot(w.x - field.x, w.y - field.y) <= field.radius)
}

// spells.py:873-879.
pub fn poison_factors(unit: &Unit, damage: f64, movement: f64, attack: f64) -> (f64, f64, f64) {
    if unit.kind == "guardian" {
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
    if u.kind == "guardian" && u.extra.waiting {
        return;
    }
    let (damage, slow, attack) = poison_factors(u, max_dps * multiplier, slow, attack);
    let linger = if u.team == Team::Def {
        6.0
    } else {
        0.0
    };
    let mut until = battle.t + if u.team == Team::Def {
        6.0
    } else {
        options.refresh
    };
    if let Some(source_until) = options.source_until {
        until = until.min(source_until + linger);
    }
    let index = battle.poison.iter().position(|state| state.unit == reference && state.origin == options.origin && state.source == options.source);
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
            1.0_f64.min(exposure.iter().find(|(id, _)| *id == state.unit.id).expect("poison exposure").1 / 4.0)
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
            "spell"
        } else {
            "poison"
        }
        .to_owned();
        let kind = if origin == "town_hall" {
            "th_poison"
        } else {
            "poison"
        };
        let label = battle.src.clone();
        battle.hit_unit(unit, damage * battle.dt, Some(&label), kind, None);
        let until = t + 2.0 * battle.dt;
        effects::add_slow(battle.unit_mut(unit), StatusSource::Name("poison".to_owned()), 1.0 - movement, 1.0 - attack, until);
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
        kind: "def_poison".to_owned(),
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
    battle.log_event(vec![round_decimal(t, 1).into(), "spell_tower".into(), mode.into()]);
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
            if target.is_none() || d < distance {
                target = Some(reference);
                distance = d;
            }
        }
    }
    let (x, y) = target.map_or((bx, by), |unit| battle.entity_position(EntityRef::Unit(unit)));
    let (kind, x, y, radius, until, value, started) = match mode {
        "rage" => ("def_rage", bx, by, 5.0, t + 18.0, 1.6, t),
        "poison" => {
            add_defensive_poison(battle, x, y, PoisonConfig {
                dps: 60.0,
                time: Some(12.0),
                slow: Some(0.35),
                radius: Some(5.0),
                atk: Some(0.25),
                ramp: false,
                hero_mult: 0.2,
                unknown: Vec::new(),
            }, "tower");
            return;
        }
        "invis" => ("def_invis", bx, by, 4.5, t + 4.5, 0.0, t),
        "eq" | "quake" | "earthquake" => ("def_quake", x, y, 4.7, t + 0.3, 0.30, t + 0.3),
        _ => return,
    };
    battle.fields.push(Field {
        kind: kind.to_owned(),
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

// spells.py:1042-1078: the flee branch requires attacking Poison Spell fields.
pub fn escape_poison(battle: &mut Battle, reference: UnitRef) -> bool {
    let u = battle.unit(reference);
    if u.is_hero || matches!(u.name.as_str(), "Healer" | "Druid") || u.speed <= 0.0 {
        return false;
    }
    if battle.fields.iter().any(|field| field.kind == "poison"
        && field.started <= battle.t
        && battle.t < field.until
        && u.dist(field.x, field.y) <= field.radius) {
        todo!("stage 4: spells.py:1058 idle defender escapes attacker Poison Spell");
    }
    battle.unit_mut(reference).extra.poison_exit = None;
    false
}

// spells.py:1226-1238: clone expiration only needs existing stage-1 unit state.
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
        } else if u.alive || battle.portal_stash.iter().any(|value| matches!(value, Value::Ref(EntityRef::Unit(unit)) if *unit == reference)) {
            keep.push(reference);
        }
    }
    battle.clones = keep;
}
