//! Ports traps.py:80-81,114-431. Trap setup comes from the Python export.

use crate::battle::SpawnOptions;
use crate::combat::SplashUnitsOptions;
use crate::geom::{self, dist};
use crate::labels::{Name, Tag};
use crate::state::{Battle, Field, Pending, Team, TrapId, Unit, UnitRef};
use crate::stats::{self, Level};
use crate::trace::round_decimal;

// traps.py:29-67: preserve the multiplication used to derive each fuse.
const NO_TRIGGER: &[Name] = &[
    Name::SpellSkeleton,
    Name::Skeleton,
    Name::Bat,
    Name::Totem,
    Name::Yetimite,
    Name::Electromite,
    Name::Firemite,
    Name::Frostmite,
    Name::Booger,
    Name::ElectroOwl,
    Name::PoisonLizard,
];

// traps.py:80-81.
pub fn raw(battle: &Battle, name: &str, key: &str, default: Option<f64>) -> Option<f64> {
    battle
        .catalog
        .stats
        .attrs(name)
        .get("raw")
        .and_then(|attrs| attrs.get(key))
        .map_or(default, |value| stats::num(value, default))
}

// traps.py:114-123.
pub fn housing(unit: &Unit) -> i64 {
    if unit.name_id == Name::Totem {
        // output/research/usage/totem-spell.md:36; August fixed 20 to 1 housing.
        // https://supercell.com/en/games/clashofclans/blog/release-notes/august-update-3/
        return 1;
    }
    if unit.is_hero {
        return 25;
    }
    if unit.kind == Tag::Pet {
        return 20;
    }
    0.max(unit.housing)
}

// traps.py:126-131: effect eligibility deliberately ignores activation time.
pub fn effect_target(battle: &Battle, trap: TrapId, unit: &Unit, t: f64) -> bool {
    let attached = unit.name_id == Name::AngryJelly
        && unit.owner.is_some_and(|owner| battle.unit(owner).alive)
        && t < unit.extra.brainwash_until;
    if !unit.alive || unit.underground || attached || unit.extra.suspended {
        return false;
    }
    if unit.name_id == Name::Totem {
        return true;
    }
    let trap = &battle.traps[trap.0];
    if unit.flying {
        trap.air
    } else {
        trap.ground
    }
}

// traps.py:134-146.
pub fn eligible(battle: &Battle, trap: TrapId, unit: &Unit, t: f64) -> bool {
    // traps.py:137-140: grounded Phoenix eggs never trigger traps.
    if unit.extra.egg {
        return false;
    }
    if !effect_target(battle, trap, unit, t) || NO_TRIGGER.contains(&unit.name_id) {
        return false;
    }
    if unit.name_id == Name::DragonDuke && unit.dash.is_some() {
        return false;
    }
    if battle.traps[trap.0].key == "seeking" {
        if matches!(unit.kind, Tag::Siege | Tag::SiegeIdle) && unit.flying {
            return true;
        }
        if housing(unit) < 5 {
            return false;
        }
    }
    true
}

// traps.py:149-173: trap Vec order and first-minimum ties are significant.
pub fn tick(battle: &mut Battle) {
    let t = battle.t;
    // output/research/usage/bomb.md: Bombs damage and knock back small troops.
    // https://clashofclans.fandom.com/wiki/Bomb
    // Canonical order also stabilizes damage callbacks across serialization.
    let mut due_bombs: Vec<_> = battle
        .traps
        .iter()
        .enumerate()
        .filter(|(_, tr)| {
            tr.armed
                && matches!(tr.key.as_str(), "bomb" | "giant")
                && 0.0 <= tr.fuse_at
                && tr.fuse_at <= t
        })
        .map(|(index, _)| TrapId(index))
        .collect();
    due_bombs.sort_by(|a, b| {
        let a = &battle.traps[a.0];
        let b = &battle.traps[b.0];
        a.fuse_at
            .total_cmp(&b.fuse_at)
            .then_with(|| a.x.total_cmp(&b.x))
            .then_with(|| a.y.total_cmp(&b.y))
            .then_with(|| a.key.cmp(&b.key))
            .then_with(|| a.damage.total_cmp(&b.damage))
            .then_with(|| a.radius.total_cmp(&b.radius))
    });
    let mut pushes = Vec::new();
    for trap in due_bombs {
        fire_deferred(battle, trap, Some(&mut pushes));
    }
    apply_bomb_pushes(battle, pushes);
    for index in 0..battle.traps.len() {
        let id = TrapId(index);
        let trap = &battle.traps[index];
        if trap.extra.state.as_deref() == Some("flight") {
            seeking_step(battle, id);
            continue;
        }
        if !trap.armed {
            continue;
        }
        if trap.fuse_at >= 0.0 {
            if t >= trap.fuse_at {
                fire(battle, id);
            }
            continue;
        }
        let near: Vec<_> = battle
            .attackers_near(trap.x, trap.y, trap.trigger)
            .into_iter()
            .filter(|unit| eligible(battle, id, battle.unit(*unit), t))
            .collect();
        if near.is_empty() {
            continue;
        }
        if trap.key == "giga"
            && (near
                .iter()
                .map(|unit| housing(battle.unit(*unit)))
                .sum::<i64>() as f64)
                < trap.extra.housing
        {
            continue;
        }
        let mut target = near[0];
        let mut distance = battle.unit(target).dist(trap.x, trap.y);
        for &unit in &near[1..] {
            let candidate = battle.unit(unit).dist(trap.x, trap.y);
            if candidate < distance {
                target = unit;
                distance = candidate;
            }
        }
        let fuse = match trap.key.as_str() {
            "bomb" => 35.0 * battle.params.trap_frame_seconds,
            "giant" => 37.0 * battle.params.trap_frame_seconds,
            "giga" => 38.0 * battle.params.trap_frame_seconds,
            "airbomb" | "seeking" => 7.0 * battle.params.trap_frame_seconds,
            "tornado" => 8.0 * battle.params.trap_frame_seconds,
            "spring" => battle.params.spring_delay,
            "skeleton" => 0.6,
            other => panic!("traps.py:171 unknown trap fuse {other}"),
        };
        let trap = &mut battle.traps[index];
        trap.extra.trigger_unit = Some(target);
        trap.fuse_at = t + fuse;
        if trap.fuse_at <= t {
            fire(battle, id);
        }
    }
}

// traps.py:176-183: only _src is restored; actor/effect remain as in Python.
pub fn fire(battle: &mut Battle, trap: TrapId) {
    fire_deferred(battle, trap, None);
}

fn fire_deferred(battle: &mut Battle, trap: TrapId, pushes: Option<&mut Vec<(UnitRef, f64, f64)>>) {
    let previous = battle.src.clone();
    fire_effect_with_pushes(battle, trap, pushes);
    battle.src = previous;
}

fn apply_bomb_pushes(battle: &mut Battle, pushes: Vec<(UnitRef, f64, f64)>) {
    let mut totals: Vec<(UnitRef, f64, f64)> = Vec::new();
    for (unit, dx, dy) in pushes {
        if let Some((_, old_x, old_y)) = totals.iter_mut().find(|(other, _, _)| *other == unit) {
            *old_x += dx;
            *old_y += dy;
        } else {
            totals.push((unit, dx, dy));
        }
    }
    totals.sort_by_key(|(unit, _, _)| battle.unit(*unit).id.0);
    for (unit, dx, dy) in totals {
        if battle.unit(unit).alive {
            if dx != 0.0 || dy != 0.0 {
                battle.nudge(unit, dx, dy);
            }
            let unit = battle.unit_mut(unit);
            unit.target = None;
            unit.wall_target = None;
        }
    }
}

// traps.py:186-324.
pub fn fire_effect(battle: &mut Battle, trap: TrapId) {
    fire_effect_with_pushes(battle, trap, None);
}

fn fire_effect_with_pushes(
    battle: &mut Battle,
    trap: TrapId,
    pushes: Option<&mut Vec<(UnitRef, f64, f64)>>,
) {
    battle.traps[trap.0].armed = false;
    let t = battle.t;
    let tr = battle.traps[trap.0].clone();
    let src = format!("trap:{}", tr.key);
    battle.src = src.clone().into();
    battle.log_event(vec![
        round_decimal(t, 1).into(),
        "trap".into(),
        tr.key.clone().into(),
    ]);
    match tr.key.as_str() {
        "bomb" | "giant" => {
            let deferred = pushes.is_some();
            let mut immediate = Vec::new();
            let pushes = pushes.unwrap_or(&mut immediate);
            battle.splash_units(
                tr.x,
                tr.y,
                tr.radius,
                tr.damage,
                tr.air,
                tr.ground,
                SplashUnitsOptions {
                    src: Some(&src),
                    kind: "trap",
                    ..Default::default()
                },
            );
            for reference in battle.attackers_near(tr.x, tr.y, tr.radius) {
                let unit = battle.unit(reference);
                if unit.alive
                    && !unit.is_hero
                    && !matches!(unit.kind, Tag::Pet | Tag::Siege | Tag::SiegeIdle)
                    && effect_target(battle, trap, unit, t)
                    && unit.name_id != Name::Totem
                    && 0 < unit.housing
                    && unit.housing <= 3
                {
                    let distance = unit.dist(tr.x, tr.y);
                    if distance > 0.0 {
                        let push = 1.0 / unit.housing as f64;
                        pushes.push((
                            reference,
                            push * (unit.x - tr.x) / distance,
                            push * (unit.y - tr.y) / distance,
                        ));
                    } else {
                        pushes.push((reference, 0.0, 0.0));
                    }
                }
            }
            if !deferred {
                apply_bomb_pushes(battle, immediate);
            }
        }
        "airbomb" => {
            let committed = tr.extra.trigger_unit;
            let radius = if committed.is_some_and(|unit| battle.unit(unit).alive) {
                tr.trigger
            } else {
                2.0 * tr.trigger
            };
            let mut candidates: Vec<_> = battle
                .attackers_near(tr.x, tr.y, radius)
                .into_iter()
                .filter(|unit| eligible(battle, trap, battle.unit(*unit), t))
                .collect();
            if let Some(unit) = committed {
                if battle.unit(unit).alive && effect_target(battle, trap, battle.unit(unit), t) {
                    candidates.push(unit);
                }
            }
            let Some(&first) = candidates.first() else {
                return;
            };
            let mut target = first;
            let mut distance = battle.unit(target).dist(tr.x, tr.y);
            for &unit in &candidates[1..] {
                let candidate = battle.unit(unit).dist(tr.x, tr.y);
                if candidate < distance {
                    target = unit;
                    distance = candidate;
                }
            }
            let unit = battle.unit(target);
            let flight = 0.0_f64.max(dist(tr.x, tr.y, unit.x, unit.y) - 0.2) / 2.5;
            let mut pending = Pending::new(
                t + flight,
                unit.x,
                unit.y,
                tr.radius,
                tr.damage,
                true,
                false,
                &src,
            );
            pending.effect = Some(Tag::Trap);
            battle.add_pending(pending);
        }
        "giga" => {
            // Capture this pool before damage; movement rechecks survivors.
            let pool: Vec<_> = battle
                .attackers_near(tr.x, tr.y, tr.radius)
                .into_iter()
                .filter(|unit| {
                    let unit = battle.unit(*unit);
                    unit.name_id != Name::Totem && !unit.underground
                })
                .collect();
            battle.splash_units(
                tr.x,
                tr.y,
                tr.radius,
                tr.damage,
                true,
                true,
                SplashUnitsOptions {
                    src: Some(&src),
                    kind: "trap",
                    ..Default::default()
                },
            );
            for reference in pool {
                let unit = battle.unit(reference);
                if unit.alive
                    && !matches!(unit.kind, Tag::Siege | Tag::SiegeIdle)
                    && effect_target(battle, trap, unit, t)
                {
                    let distance = unit.dist(tr.x, tr.y);
                    if distance > 0.0 {
                        battle.nudge(
                            reference,
                            2.0 * (unit.x - tr.x) / distance,
                            2.0 * (unit.y - tr.y) / distance,
                        );
                    }
                    let unit = battle.unit_mut(reference);
                    unit.target = None;
                    unit.wall_target = None;
                }
            }
        }
        "seeking" => {
            let Some(unit) = tr.extra.trigger_unit else {
                return;
            };
            if !battle.unit(unit).alive || !effect_target(battle, trap, battle.unit(unit), t) {
                return;
            }
            // traps.py:273-280: launch 0.2 tiles toward the committed target.
            let target = battle.unit(unit);
            let distance = dist(tr.x, tr.y, target.x, target.y);
            let denominator = if distance != 0.0 { distance } else { 1.0 };
            let offset = 0.2_f64.min(distance) / denominator;
            let projectile = (
                tr.x + (target.x - tr.x) * offset,
                tr.y + (target.y - tr.y) * offset,
            );
            let extra = &mut battle.traps[trap.0].extra;
            extra.state = Some("flight".to_owned());
            extra.projectile = Some(projectile);
        }
        "spring" => {
            let candidates: Vec<_> = battle
                .attackers_near(tr.x, tr.y, tr.trigger)
                .into_iter()
                .filter(|unit| effect_target(battle, trap, battle.unit(*unit), t))
                .collect();
            let Some(&first) = candidates.first() else {
                return;
            };
            let mut target = first;
            let mut weight = housing(battle.unit(target));
            let mut distance = battle.unit(target).dist(tr.x, tr.y);
            for &reference in &candidates[1..] {
                let unit = battle.unit(reference);
                let candidate_weight = housing(unit);
                let candidate_distance = unit.dist(tr.x, tr.y);
                if candidate_weight > weight
                    || candidate_weight == weight && candidate_distance < distance
                {
                    target = reference;
                    weight = candidate_weight;
                    distance = candidate_distance;
                }
            }
            let unit = battle.unit(target);
            let special =
                unit.is_hero || matches!(unit.kind, Tag::Pet | Tag::Siege | Tag::SiegeIdle);
            // output/research/usage/spring-trap.md; verify/c1.out #5 corrects immunity:
            // springs can eject Totems when another troop triggers the trap.
            // https://clashofclans.fandom.com/wiki/Totem_Spell
            // https://www.mumuplayer.com/blog/clash-of-clans-th18-totem-spell.html
            if !special && 0 < weight && weight as f64 <= tr.extra.capacity {
                let housing = weight;
                if let Some((_, total)) = battle
                    .kills_by_source
                    .iter_mut()
                    .find(|(key, _)| key.as_str() == src.as_str())
                {
                    *total += housing;
                } else {
                    battle.kills_by_source.push((src.into(), housing));
                }
                battle.unit_mut(target).extra.sprung = true;
                battle.kill(target);
                return;
            }
            let damage = tr.damage * if special { 0.5 } else { 1.0 };
            battle.hit_unit(target, damage, Some(&src), "trap", None);
            let stun = battle.params.spring_stun;
            let unit = battle.unit_mut(target);
            if unit.alive && !matches!(unit.kind, Tag::Siege | Tag::SiegeIdle) {
                unit.stun_until = unit.stun_until.max(t + stun);
            }
        }
        "skeleton" => {
            let count = tr.extra.count;
            for index in 0..count {
                let angle = 2.0 * std::f64::consts::PI * index as f64 / 1.max(count) as f64;
                let x = tr.x + 0.7 * geom::py_cos(angle);
                let y = tr.y + 0.7 * geom::py_sin(angle);
                let at = tr.fuse_at + 0.15 * index as f64;
                if at <= t {
                    spawn_skeleton(battle, trap, x, y);
                } else {
                    let mut pending = Pending::new(at, x, y, 0.0, 0.0, false, false, &src);
                    pending.team = Team::Def;
                    pending.extra.trap_skeleton = Some(trap);
                    battle.add_pending(pending);
                }
            }
        }
        "tornado" => {
            let mut field = Field::new("tornado", tr.x, tr.y, tr.radius, t + tr.extra.time);
            field.team = Team::Def;
            field.extra.pulses = tr.extra.pulses;
            field.extra.has_pulses = true;
            field.extra.delivered = 0;
            field.started = t;
            // Python appends before the immediate tick. Keep it visible during
            // damage callbacks, then update its detached pulse state in place.
            let index = battle.fields.len();
            battle.fields.push(field.clone());
            tornado_tick(battle, &mut field);
            battle.fields[index] = field;
        }
        // traps.py:324: no other trap family has a runtime effect.
        _ => {}
    }
}

// traps.py:337-358: create the Skeleton only when its Pending birth is due.
pub fn spawn_skeleton(battle: &mut Battle, trap: TrapId, x: f64, y: f64) {
    let tr = battle.traps[trap.0].clone();
    let level = Level::Int(tr.extra.skel_level);
    let reference = battle.spawn(
        "Skeleton",
        Team::Def,
        x,
        y,
        SpawnOptions {
            level: Some(level.clone()),
            kind: Tag::TrapSkeleton,
            ..Default::default()
        },
    );
    let hp = battle
        .catalog
        .stats
        .get(&tr.name, &level, &["Hitpoints"], None)
        .expect("Skeleton Trap hitpoints");
    let damage = battle
        .catalog
        .stats
        .get(&tr.name, &level, &["Damage per Hit"], None)
        .expect("Skeleton Trap damage");
    let interval = raw(battle, &tr.name, "Attack Speed", None).expect("Skeleton Trap attack speed");
    // traps.py:354-356: airborne trap skeletons attack at zero range.
    let range = if tr.mode.as_deref() == Some("air") {
        0.0
    } else {
        0.4
    };
    let unit = battle.unit_mut(reference);
    unit.hp = hp;
    unit.max_hp = hp;
    unit.base_max_hp = hp;
    unit.dmg = damage;
    unit.interval = interval;
    unit.range = range;
    unit.flying = tr.mode.as_deref() == Some("air");
    unit.hits_air = unit.flying;
    unit.hits_ground = !unit.flying;
    unit.speed = if unit.flying { 2.2 } else { 3.0 };
}

// traps.py:327-345.
pub fn seeking_step(battle: &mut Battle, trap: TrapId) {
    let tr = &battle.traps[trap.0];
    let target = tr.extra.trigger_unit.expect("Seeking Air Mine target");
    if !battle.unit(target).alive || !effect_target(battle, trap, battle.unit(target), battle.t) {
        battle.traps[trap.0].extra.state = Some("spent".to_owned());
        return;
    }
    let (x, y) = tr.extra.projectile.expect("Seeking Air Mine projectile");
    let unit = battle.unit(target);
    let (tx, ty) = (unit.x, unit.y);
    let distance = dist(x, y, tx, ty);
    let step = 3.5 * battle.dt;
    if distance <= step {
        let damage = tr.damage;
        let extra = &mut battle.traps[trap.0].extra;
        extra.projectile = Some((tx, ty));
        extra.state = Some("spent".to_owned());
        battle.hit_unit(target, damage, Some("trap:seeking"), "trap", None);
    } else {
        battle.traps[trap.0].extra.projectile = Some((
            x + (tx - x) / distance * step,
            y + (ty - y) / distance * step,
        ));
    }
}

// traps.py:348-401: pulse timestamps temporarily replace the battle clock.
pub fn tornado_tick(battle: &mut Battle, field: &mut Field) {
    let t = battle.t;
    let mut delivered = field.extra.delivered;
    while delivered < field.extra.pulses {
        let at = field.started + delivered as f64 * 0.128;
        if at > t.min(field.until) {
            break;
        }
        battle.t = at;
        for reference in battle.attackers_near(field.x, field.y, field.radius) {
            if !battle.unit(reference).underground {
                battle.hit_unit(
                    reference,
                    1.0 * battle.def_mult,
                    Some("trap:tornado"),
                    "trap",
                    None,
                );
            }
        }
        battle.t = t;
        delivered += 1;
    }
    field.extra.delivered = delivered;
    if t >= field.until {
        return;
    }
    // traps.py:375-377: rotate every pulled position, including the inner radius.
    let angle = -std::f64::consts::PI * battle.dt;
    let (cos_angle, sin_angle) = (crate::geom::py_cos(angle), crate::geom::py_sin(angle));
    for reference in battle.attackers_near(field.x, field.y, field.radius) {
        let unit = battle.unit(reference);
        if !unit.alive || unit.underground || unit.attached(battle) || unit.extra.suspended {
            continue;
        }
        if t < unit.extra.tornado_wall_until {
            continue;
        }
        if unit.name_id == Name::Totem {
            continue;
        }
        if matches!(
            unit.name_id,
            Name::Miner | Name::SuperMiner | Name::Diggy | Name::BattleDrill
        ) {
            continue;
        }
        let weight = if unit.is_hero || unit.kind == Tag::Pet {
            5
        } else if matches!(unit.kind, Tag::Siege | Tag::SiegeIdle) {
            if unit.speed <= 0.0 {
                continue;
            }
            1
        } else {
            (unit.housing as f64 / 3.0).ceil().clamp(1.0, 5.0) as usize
        };
        let distance = unit.dist(field.x, field.y);
        let (mut nx, mut ny) = (unit.x, unit.y);
        if distance > 0.7 {
            let fraction = 1.0_f64.min((distance - 0.7) / 1e-9_f64.max(field.radius - 0.7));
            let percentage = 1.0 + (0.65 - 1.0) * fraction;
            let force = if unit.flying {
                [5.0, 4.0, 3.0, 2.0, 1.5]
            } else {
                [4.0, 3.0, 2.0, 1.0, 1.0]
            };
            let speed = force[weight - 1] * percentage * battle.params.tornado_force_scale;
            let step = (distance - 0.7).min(speed * battle.dt);
            nx = unit.x + (field.x - unit.x) / distance * step;
            ny = unit.y + (field.y - unit.y) / distance * step;
        }
        let (dx, dy) = (nx - field.x, ny - field.y);
        nx = field.x + dx * cos_angle - dy * sin_angle;
        ny = field.y + dx * sin_angle + dy * cos_angle;
        tornado_move(battle, reference, nx, ny, field.until);
    }
}

// traps.py:430-431: math.nextafter(value, toward), including signed zero.
fn nextafter(value: f64, toward: f64) -> f64 {
    if value.is_nan() || toward.is_nan() {
        return value + toward;
    }
    if value == toward {
        return toward;
    }
    if value == 0.0 {
        return f64::from_bits(1).copysign(toward);
    }
    let bits = value.to_bits();
    if (toward > value) == (value > 0.0) {
        f64::from_bits(bits + 1)
    } else {
        f64::from_bits(bits - 1)
    }
}

// traps.py:404-431: closed wall slabs; the first equal contact keeps its order.
pub fn tornado_move(battle: &mut Battle, reference: UnitRef, nx: f64, ny: f64, until: f64) {
    let unit = battle.unit(reference);
    if unit.flying {
        let unit = battle.unit_mut(reference);
        unit.x = nx;
        unit.y = ny;
        return;
    }
    let (x, y) = (unit.x, unit.y);
    let mut first: Option<f64> = None;
    for wall in &battle.walls {
        if !wall.alive {
            continue;
        }
        let (mut enter, mut leave) = (0.0_f64, 1.0_f64);
        for (start, end, center) in [(x, nx, wall.x), (y, ny, wall.y)] {
            let (low, high) = (center - wall.half_hit, center + wall.half_hit);
            let delta = end - start;
            if delta == 0.0 {
                if start < low || start > high {
                    leave = -1.0;
                    break;
                }
                continue;
            }
            let a = (low - start) / delta;
            let b = (high - start) / delta;
            enter = enter.max(a.min(b));
            leave = leave.min(a.max(b));
        }
        if enter <= leave && first.map_or(true, |first| enter < first) {
            first = Some(enter);
        }
    }
    let unit = battle.unit_mut(reference);
    let Some(first) = first else {
        unit.x = nx;
        unit.y = ny;
        return;
    };
    unit.extra.tornado_wall_until = unit.extra.tornado_wall_until.max(until);
    unit.x = nextafter(x + (nx - x) * first, x);
    unit.y = nextafter(y + (ny - y) * first, y);
}
