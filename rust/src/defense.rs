use crate::battle::{Battle, Impact, Pending, Splash};
use crate::geom::dist;
use crate::input::{Targets, WeaponKind, WeaponSpec};

pub struct Weapon<'a> {
    spec: &'a WeaponSpec,
    cooldown: f64,
    target: Option<usize>,
    lock_time: f64,
    idle_until: f64,
    ammunition: Option<usize>,
    ammo_time: f64,
    candidates: Vec<usize>,
}

impl<'a> Weapon<'a> {
    pub fn new(spec: &'a WeaponSpec) -> Self {
        // defense.py:39-57: all clocks and the ammunition remainder start at zero.
        Self {
            spec,
            cooldown: 0.0,
            target: None,
            lock_time: 0.0,
            idle_until: 0.0,
            ammunition: spec.ammo,
            ammo_time: 0.0,
            candidates: Vec::new(),
        }
    }
}

pub fn act(battle: &mut Battle<'_>, owner: usize, weapon: &mut Weapon<'_>) {
    // defense.py:601-633: empty weapons do not even decrement cooldown.
    if weapon.ammunition == Some(0) {
        return;
    }
    let dt = battle.input.dt;
    weapon.cooldown = (weapon.cooldown - dt).max(-dt);
    for _ in 0..12 {
        let before = weapon.cooldown;
        act_once(battle, owner, weapon);
        if weapon.ammunition == Some(0) || weapon.cooldown > 0.0 || weapon.cooldown == before {
            break;
        }
    }
}

fn act_once(battle: &mut Battle<'_>, owner: usize, weapon: &mut Weapon<'_>) {
    let spec = weapon.spec;
    let building = battle.buildings[owner].spec;
    let mut target = weapon.target;
    // defense.py:679-697: keep valid targets, including while cooling down.
    if let Some(index) = target {
        let unit = &battle.units[index];
        let distance = dist(unit.x, unit.y, building.cx, building.cy);
        if !unit.alive || distance > spec.range || distance < spec.min_range {
            target = None;
            weapon.lock_time = 0.0;
        }
    }
    if target.is_none() {
        if battle.t < weapon.idle_until {
            return;
        }
        battle.attackers_near(building.cx, building.cy, spec.range, &mut weapon.candidates);
        let mut best_distance = f64::INFINITY;
        for &index in &weapon.candidates {
            let unit = &battle.units[index];
            if unit.spec.flying && spec.targets == Targets::Ground
                || !unit.spec.flying && spec.targets == Targets::Air
            {
                continue;
            }
            let distance = dist(unit.x, unit.y, building.cx, building.cy);
            if spec.min_range != 0.0 && distance < spec.min_range {
                continue;
            }
            if distance < best_distance {
                best_distance = distance;
                target = Some(index);
            }
        }
        let Some(index) = target else {
            weapon.idle_until = battle.t + 0.25;
            return;
        };
        weapon.target = Some(index);
        weapon.lock_time = 0.0;
    }
    let target = target.expect("acquired target");
    if spec.kind == WeaponKind::Inferno {
        // defense.py:698-713: one damage tick, ordinary addition for lock time.
        weapon.lock_time += battle.input.dt;
        let mut dps = 0.0;
        for (start, value) in spec.ramp {
            if weapon.lock_time >= start {
                dps = value;
            }
        }
        let mut duration = battle.input.dt;
        if let Some(rounds) = weapon.ammunition {
            duration = duration.min(rounds as f64 * spec.interval - weapon.ammo_time);
        }
        battle.hit_unit(target, dps * duration);
        weapon.ammo_time += duration;
        while weapon.ammo_time + 1e-9 >= spec.interval {
            weapon.ammo_time -= spec.interval;
            if let Some(rounds) = weapon.ammunition.as_mut() {
                *rounds -= 1;
            }
        }
        return;
    }
    if weapon.cooldown > 0.0 {
        return;
    }
    // defense.py:736-747: add rather than reset, preserving fractional carry.
    weapon.cooldown += spec.interval;
    if let Some(rounds) = weapon.ammunition.as_mut() {
        *rounds -= 1;
    }
    match spec.kind {
        WeaponKind::Single => {
            if spec.proj_speed > 0.0 {
                // defense.py:810-826: retain the unit, not the saved aim point.
                let unit = &battle.units[target];
                let flight =
                    dist(building.cx, building.cy, unit.x, unit.y).max(0.0) / spec.proj_speed;
                battle.pending.push(Pending {
                    at: battle.t + flight,
                    impact: Impact::Direct {
                        unit: target,
                        damage: spec.damage,
                    },
                });
            } else {
                battle.hit_unit(target, spec.damage);
            }
        }
        WeaponKind::Splash | WeaponKind::Mortar => {
            let unit = &battle.units[target];
            let hits_air = if spec.same_type {
                unit.spec.flying
            } else {
                spec.targets != Targets::Ground
            };
            let hits_ground = if spec.same_type {
                !unit.spec.flying
            } else {
                spec.targets != Targets::Air
            };
            let splash = Splash {
                x: unit.x,
                y: unit.y,
                radius: spec.splash,
                damage: spec.damage,
                hits_air,
                hits_ground,
                falloff: spec.falloff,
            };
            // defense.py:767-803,829-842: WT aims at release; mortar has fixed flight.
            if spec.kind == WeaponKind::Mortar || spec.proj_speed > 0.0 {
                let flight = if spec.kind == WeaponKind::Mortar {
                    spec.flight
                } else {
                    dist(building.cx, building.cy, unit.x, unit.y) / spec.proj_speed
                };
                battle.pending.push(Pending {
                    at: battle.t + flight,
                    impact: Impact::Area(splash),
                });
            } else {
                battle.splash_units(splash);
            }
        }
        WeaponKind::Inferno => unreachable!("inferno returns before ordinary fire"),
    }
}
