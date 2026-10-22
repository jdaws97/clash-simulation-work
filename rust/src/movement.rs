//! Ports battle.py:1087-1130,1428-1669: navigation and separation.

use crate::geom::py_hypot;
use crate::grid::{Grid, TargetIdentity, GOAL_REACH_MIN, NORMAL_WALL_EXTRA, RES};
use crate::state::*;
use crate::{effects, units};

impl Battle {
    // battle.py:1087-1117: frozen bucket order, live positions after each nudge.
    pub fn separate(&mut self) {
        let cells: Vec<_> = self.buckets.iter().map(|(_, members)| members.clone()).collect();
        for cell in cells {
            if cell.len() < 2 {
                continue;
            }
            for i in 0..cell.len() {
                let a = cell[i];
                if !self.unit(a).alive || self.unit(a).speed <= 0.0 {
                    continue;
                }
                let ra = 0.35 + 0.015 * 30.min(self.unit(a).housing) as f64;
                for &b in &cell[i + 1..] {
                    let ua = self.unit(a);
                    let ub = self.unit(b);
                    if !ub.alive || ub.flying != ua.flying || ub.speed <= 0.0 {
                        continue;
                    }
                    let rb = 0.35 + 0.015 * 30.min(ub.housing) as f64;
                    let (mut dx, mut dy) = (ub.x - ua.x, ub.y - ua.y);
                    let d2 = dx * dx + dy * dy;
                    let limit = ra + rb;
                    if d2 >= limit * limit {
                        continue;
                    }
                    let mut d = d2.sqrt();
                    let push = if d < 1e-6 {
                        let angle = (ua.id.0 as f64 * 2.399).rem_euclid(2.0 * std::f64::consts::PI);
                        dx = angle.cos();
                        dy = angle.sin();
                        d = 1.0;
                        limit * 0.25
                    } else {
                        (limit - d) * 0.25
                    };
                    let (ux, uy) = (dx / d * push, dy / d * push);
                    self.nudge(a, -ux, -uy);
                    self.nudge(b, ux, uy);
                }
            }
        }
    }

    // battle.py:1119-1130.
    pub fn nudge(&mut self, reference: UnitRef, dx: f64, dy: f64) {
        let u = self.unit(reference);
        if self.t < u.extra.tornado_wall_until {
            return;
        }
        let (nx, ny, flying) = (u.x + dx, u.y + dy, u.flying);
        if !flying {
            let (i, j) = self.grid.cell(nx, ny);
            let mode = self.wall_mode(reference).to_owned();
            let grid = self.navigation_grid(reference);
            let index = grid.index(i, j);
            if grid.blocked[index] || grid.wall[index] && mode == "normal" {
                return;
            }
        }
        let high = self.catalog.world as f64 - 0.1;
        let u = self.unit_mut(reference);
        u.x = high.min(0.1_f64.max(nx));
        u.y = high.min(0.1_f64.max(ny));
    }

    // battle.py:1428-1442: first argmin, first nearest fallback.
    pub fn path_target(&mut self, reference: UnitRef, pool: &[BuildingId]) -> BuildingId {
        let xs: Vec<_> = pool.iter().map(|id| self.building(*id).x).collect();
        let ys: Vec<_> = pool.iter().map(|id| self.building(*id).y).collect();
        let halves: Vec<_> = pool.iter().map(|id| self.building(*id).half_hit).collect();
        let u = self.unit(reference);
        let (x, y) = (u.x, u.y);
        let reach = units::effective_range(u).max(GOAL_REACH_MIN);
        let costs = self.navigation_grid(reference).building_costs(x, y, NORMAL_WALL_EXTRA, &xs, &ys, &halves, reach);
        let mut k = 0;
        for i in 1..costs.len() {
            if costs[i] < costs[k] {
                k = i;
            }
        }
        if costs[k] >= 1e8 {
            let mut best = pool[0];
            let mut distance = self.building(best).edge_distance(x, y);
            for &id in &pool[1..] {
                let d = self.building(id).edge_distance(x, y);
                if d < distance {
                    distance = d;
                    best = id;
                }
            }
            return best;
        }
        pool[k]
    }

    // battle.py:1460-1476.
    pub fn wall_mode(&self, reference: UnitRef) -> &str {
        let u = self.unit(reference);
        if u.team == Team::Def {
            return "ignore";
        }
        if !matches!(u.kind.as_str(), "siege" | "siege_idle") && self.t < u.extra.jump_until {
            return "ignore";
        }
        if self.t < u.extra.horse_until || effects::torch_stats(u, self.t).1 != 0.0 {
            return "ignore";
        }
        if !u.extra.torches.is_empty() && !u.flying {
            let (i, j) = self.grid.cell(u.x, u.y);
            if self.grid.wall[self.grid.index(i, j)] {
                return "ignore";
            }
        }
        &u.spec.walls
    }

    // battle.py:1478-1503: Jump Spell's separate topology belongs to stage 4.
    pub fn navigation_grid(&mut self, reference: UnitRef) -> &mut Grid {
        if matches!(self.unit(reference).kind.as_str(), "siege" | "siege_idle") {
            return &mut self.grid;
        }
        if self.fields.iter().any(|f| f.kind == "jump" && f.started <= self.t && self.t < f.until) {
            todo!("stage 4: battle.py:1488 Jump Spell navigation grid");
        }
        &mut self.grid
    }

    // battle.py:1505-1520: add strongest speed bonus, then multiply slow.
    pub fn speed_of(&self, reference: UnitRef) -> f64 {
        let u = self.unit(reference);
        let mut speed = u.speed;
        let (_, rage_speed) = units::rage_boost(u, self.t);
        let horse_speed = if self.t < u.extra.horse_until {
            u.extra.horse_speed
        } else {
            0.0
        };
        speed += rage_speed.max(units::haste_speed(u, self.t)).max(horse_speed).max(effects::torch_stats(u, self.t).0);
        speed *= effects::slow_mult(u, self.t, true);
        speed
    }

    // battle.py:1591-1653: field handles outlive waypoint lookups until prune.
    pub fn move_towards(
        &mut self,
        reference: UnitRef,
        target: EntityRef,
        position: Option<(f64, f64)>,
    ) {
        let step = self.speed_of(reference) * self.dt;
        if step <= 0.0 {
            return;
        }
        let (tx, ty) = position.unwrap_or_else(|| self.entity_position(target));
        let mut mode = self.wall_mode(reference).to_owned();
        let u = self.unit(reference);
        if u.name == "Ruin Witch" && u.team == Team::Atk {
            mode = "normal".to_owned();
        }
        if mode == "smash" {
            mode = "ignore".to_owned();
        }
        if u.flying || mode == "fly" || u.underground || u.spec.prefer == "th" {
            self.move_straight(reference, tx, ty, step);
            return;
        }
        let reach = if position.is_none() {
            units::effective_range(u)
        } else {
            1.0 / RES as f64
        };
        let reach = reach.max(GOAL_REACH_MIN);
        let half = if position.is_none() {
            match target {
                EntityRef::Building(id) => self.building(id).half_hit,
                EntityRef::Wall(id) => self.walls[id.0].half_hit,
                _ => 0.0,
            }
        } else {
            0.0
        };
        let identity = match target {
            EntityRef::Building(id) => TargetIdentity::Building(id.0),
            EntityRef::Wall(id) => TargetIdentity::Wall(self.walls[id.0].tx, self.walls[id.0].ty),
            EntityRef::Unit(id) => TargetIdentity::Unit(id.id.0),
            EntityRef::Trap(_) => panic!("navigation target is a trap"),
        };
        let wall_extra = match mode.as_str() {
            "normal" => NORMAL_WALL_EXTRA,
            "ignore" | "fly" => 0.0,
            _ => panic!("unknown wall mode {mode}"),
        };
        let (x, y) = (u.x, u.y);
        let grid = self.navigation_grid(reference);
        let field = grid.field(identity, tx, ty, half, reach, wall_extra);
        let mut next = grid.next_step(field, x, y);
        if next.at_goal {
            let (i, j) = grid.cell(x, y);
            let cell = grid.index(i, j);
            if grid.distance(field, cell) == 0.0 || grid.blocked[cell] {
                self.move_straight(reference, tx, ty, step);
            }
            return;
        }
        if next.is_wall && mode == "ignore" {
            next.is_wall = false;
        }
        if next.is_wall {
            if let Some(&wall) = self.wall_indices.get(&(next.x as i32, next.y as i32)) {
                if self.walls[wall.0].alive {
                    if self.unit(reference).name == "Ruin Witch" && reference.team == Team::Atk {
                        todo!("stage 2: battle.py:1628 Ruin Witch wall retarget");
                    }
                    self.unit_mut(reference).wall_target = Some(wall);
                    return;
                }
            }
        }
        if next.x == x && next.y == y {
            let dt = self.dt;
            let u = self.unit_mut(reference);
            u.stuck += dt;
            if u.stuck > 2.0 {
                u.target = None;
                u.stuck = 0.0;
            }
            return;
        }
        self.unit_mut(reference).stuck = 0.0;
        let mut left = step - py_hypot(next.x - x, next.y - y);
        self.move_straight(reference, next.x, next.y, step);
        for _ in 0..4 {
            let u = self.unit(reference);
            if left <= 1e-9 || u.x != next.x || u.y != next.y {
                break;
            }
            let (x, y) = (u.x, u.y);
            next = self.navigation_grid(reference).next_step(field, x, y);
            if next.at_goal || next.is_wall && mode != "ignore" || next.x == x && next.y == y {
                break;
            }
            let d = py_hypot(next.x - x, next.y - y);
            self.move_straight(reference, next.x, next.y, left);
            left -= d;
        }
    }

    // battle.py:1655-1669: preserve dx / d * step evaluation order.
    pub fn move_straight(&mut self, reference: UnitRef, tx: f64, ty: f64, step: f64) {
        let t = self.t;
        let u = self.unit_mut(reference);
        if t < u.extra.tornado_wall_until {
            return;
        }
        let (dx, dy) = (tx - u.x, ty - u.y);
        if dx != 0.0 || dy != 0.0 {
            u.extra.facing = (dx, dy);
        }
        let d = py_hypot(dx, dy);
        if d != 0.0 && u.name == "Super Hog Rider" {
            todo!("stage 2: battle.py:1664 Super Hog Rider heading");
        }
        if d <= step || d == 0.0 {
            u.x = tx;
            u.y = ty;
        } else {
            u.x += dx / d * step;
            u.y += dy / d * step;
        }
    }
}
