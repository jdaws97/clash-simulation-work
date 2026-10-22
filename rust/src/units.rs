use crate::battle::{Battle, Target};
use crate::geom::{dist, edge_distance, py_hypot, segment_entry};
use crate::grid::{TargetIdentity, GOAL_REACH_MIN, NORMAL_WALL_EXTRA};
use crate::input::UnitSpec;

#[derive(Clone, Copy)]
struct SpinPosition {
    first: usize,
    second: usize,
    x: f64,
    y: f64,
}

pub struct Unit<'a> {
    pub spec: &'a UnitSpec,
    pub id: usize,
    pub x: f64,
    pub y: f64,
    pub hp: f64,
    pub alive: bool,
    pub cooldown: f64,
    target: Option<Target>,
    wall_target: Option<usize>,
    stuck: f64,
    spin_position: Option<SpinPosition>,
}

impl<'a> Unit<'a> {
    pub fn new(spec: &'a UnitSpec, id: usize, x: f64, y: f64) -> Self {
        // entities.py:126-153: neutral spawn state, no cooldown or target.
        Self {
            spec,
            id,
            x,
            y,
            hp: spec.hp,
            alive: true,
            cooldown: 0.0,
            target: None,
            wall_target: None,
            stuck: 0.0,
            spin_position: None,
        }
    }
}

impl Battle<'_> {
    pub fn act_attacker(&mut self, index: usize) {
        // battle.py:1200-1226: primary validity is separate from the wall target.
        let dt = self.input.dt;
        self.units[index].cooldown = (self.units[index].cooldown - dt).max(-dt);
        let old_target = self.units[index].target;
        let mut target = old_target.filter(|&target| match target {
            Target::Building(building) => self.building_targetable(building),
            Target::Wall(wall) => self.walls[wall].alive,
        });
        if target.is_none() {
            self.units[index].wall_target = None;
            target = self.choose_target(index);
        }
        // units.py:1291-1308: windup counts down during travel, uses max, not add.
        if target.is_some() && target != old_target {
            self.units[index].cooldown = self.units[index]
                .cooldown
                .max(self.units[index].spec.windup_delay);
        }
        self.units[index].target = target;
        let Some(target) = target else {
            return;
        };
        // battle.py:1308-1311: acquiring a wall does not cause new-target windup.
        if let Some(wall) = self.units[index].wall_target {
            if self.walls[wall].alive {
                self.engage(index, Target::Wall(wall));
                return;
            }
        }
        self.units[index].wall_target = None;
        self.engage(index, target);
    }

    fn choose_target(&mut self, index: usize) -> Option<Target> {
        // battle.py:1395-1422: both troops prefer any targetable building.
        let pool: Vec<usize> = (0..self.buildings.len())
            .filter(|&building| self.building_targetable(building))
            .collect();
        if pool.is_empty() {
            return None;
        }
        let unit = &self.units[index];
        if !unit.spec.flying && pool.len() > 1 {
            return Some(Target::Building(self.path_target(index, &pool)));
        }
        let mut best = None;
        let mut best_distance = 1e9;
        for building in pool {
            let spec = self.buildings[building].spec;
            let distance = edge_distance(unit.x, unit.y, spec.cx, spec.cy, spec.half_hit);
            if distance < best_distance {
                best = Some(Target::Building(building));
                best_distance = distance;
            }
        }
        best
    }

    fn path_target(&mut self, index: usize, pool: &[usize]) -> usize {
        // battle.py:1426-1442: f32 argmin, first tie; only unreachable falls back.
        let xs: Vec<f64> = pool.iter().map(|&b| self.buildings[b].spec.cx).collect();
        let ys: Vec<f64> = pool.iter().map(|&b| self.buildings[b].spec.cy).collect();
        let halves: Vec<f64> = pool
            .iter()
            .map(|&b| self.buildings[b].spec.half_hit)
            .collect();
        let unit = &self.units[index];
        let costs = self.grid.building_costs(
            unit.x,
            unit.y,
            NORMAL_WALL_EXTRA,
            &xs,
            &ys,
            &halves,
            unit.spec.range.max(GOAL_REACH_MIN),
        );
        let mut best = 0;
        for k in 1..costs.len() {
            if costs[k] < costs[best] {
                best = k;
            }
        }
        if costs[best] >= 1e8_f32 {
            let mut best_distance = edge_distance(unit.x, unit.y, xs[0], ys[0], halves[0]);
            best = 0;
            for k in 1..pool.len() {
                let distance = edge_distance(unit.x, unit.y, xs[k], ys[k], halves[k]);
                if distance < best_distance {
                    best_distance = distance;
                    best = k;
                }
            }
        }
        pool[best]
    }

    fn valkyrie_position(&mut self, index: usize, target: Target) -> Option<(f64, f64)> {
        let Target::Building(first) = target else {
            return None;
        };
        if self.units[index].spec.name != "Valkyrie" {
            return None;
        }
        // units.py:1203-1208: reuse while both identities are valid, without rechecking geometry.
        if let Some(saved) = self.units[index].spin_position {
            if saved.first == first && self.building_targetable(saved.second) {
                return Some((saved.x, saved.y));
            }
        }
        let unit = &self.units[index];
        let target = self.buildings[first].spec;
        let mut best = None;
        let mut best_distance = f64::INFINITY;
        for second in 0..self.buildings.len() {
            if second == first || !self.building_targetable(second) {
                continue;
            }
            let other = self.buildings[second].spec;
            // units.py:1213-1218: closest points on the squares, then their midpoint.
            let px = other
                .cx
                .clamp(target.cx - target.half_hit, target.cx + target.half_hit);
            let py = other
                .cy
                .clamp(target.cy - target.half_hit, target.cy + target.half_hit);
            let qx = px.clamp(other.cx - other.half_hit, other.cx + other.half_hit);
            let qy = py.clamp(other.cy - other.half_hit, other.cy + other.half_hit);
            let x = (px + qx) / 2.0;
            let y = (py + qy) / 2.0;
            if edge_distance(x, y, target.cx, target.cy, target.half_hit) > unit.spec.range
                || edge_distance(x, y, other.cx, other.cy, other.half_hit) > unit.spec.splash
            {
                continue;
            }
            let (i, j) = self.grid.cell(x, y);
            if self.grid.blocked[self.grid.index(i, j)] {
                continue;
            }
            // units.py:1225-1229: touching any living building rejects this segment.
            let obstructed = self.buildings.iter().any(|building| {
                let spec = building.spec;
                building.alive
                    && segment_entry(unit.x, unit.y, x, y, spec.cx, spec.cy, spec.half_hit)
                        .is_some()
            });
            if obstructed {
                continue;
            }
            let distance = dist(unit.x, unit.y, x, y);
            if distance < best_distance {
                best_distance = distance;
                best = Some(SpinPosition { first, second, x, y });
            }
        }
        // units.py:1231-1236: an empty search clears the old cache.
        self.units[index].spin_position = best;
        best.map(|saved| (saved.x, saved.y))
    }

    fn engage(&mut self, index: usize, target: Target) {
        // battle.py:1542-1547: exact spin coordinate is required before range checks.
        if let Some(position) = self.valkyrie_position(index, target) {
            if (self.units[index].x, self.units[index].y) != position {
                self.move_towards(index, target, Some(position));
                return;
            }
        }
        let (x, y, half) = self.target_geometry(target);
        let unit = &self.units[index];
        let distance = edge_distance(unit.x, unit.y, x, y, half);
        if distance <= unit.spec.range {
            // battle.py:1571-1587: one strike per tick; carry the cooldown remainder.
            if unit.cooldown <= 0.0 {
                let interval = unit.spec.interval;
                self.strike(index, target);
                self.units[index].cooldown += interval;
            }
            return;
        }
        // Moving into range never also strikes (battle.py:1589-1592).
        self.move_towards(index, target, None);
    }

    fn move_towards(&mut self, index: usize, target: Target, position: Option<(f64, f64)>) {
        let unit = &self.units[index];
        let step = unit.spec.speed * self.input.dt;
        if step <= 0.0 {
            return;
        }
        let (cx, cy, half) = self.target_geometry(target);
        let (tx, ty) = position.unwrap_or((cx, cy));
        if unit.spec.flying {
            self.move_straight(index, tx, ty, step);
            return;
        }
        // battle.py:1604-1611: point positioning goals use half=0 and reach=0.5.
        let reach = if position.is_some() {
            0.5
        } else {
            unit.spec.range
        }
        .max(GOAL_REACH_MIN);
        let half = if position.is_some() { 0.0 } else { half };
        let identity = match target {
            Target::Building(building) => {
                TargetIdentity::Building(self.buildings[building].spec.id)
            }
            Target::Wall(wall) => {
                let spec = self.walls[wall].spec;
                TargetIdentity::Wall(spec.tx, spec.ty)
            }
        };
        let field = self
            .grid
            .field(identity, tx, ty, half, reach, NORMAL_WALL_EXTRA);
        let next = self.grid.next_step(&field, unit.x, unit.y);
        if next.at_goal {
            let (i, j) = self.grid.cell(unit.x, unit.y);
            let cell = self.grid.index(i, j);
            // battle.py:1613-1622: finish straight only at a goal or inside a building.
            if field[cell] == 0.0 || self.grid.blocked[cell] {
                self.move_straight(index, tx, ty, step);
            }
            return;
        }
        if next.is_wall {
            if let Some(wall) = self.wall_at(next.x, next.y) {
                if self.walls[wall].alive {
                    self.units[index].wall_target = Some(wall);
                    return;
                }
            }
        }
        if next.x == unit.x && next.y == unit.y {
            // battle.py:1632-1638: strict >2 seconds, clear only the primary target.
            self.units[index].stuck += self.input.dt;
            if self.units[index].stuck > 2.0 {
                self.units[index].target = None;
                self.units[index].stuck = 0.0;
            }
            return;
        }
        let mut left = step - py_hypot(next.x - unit.x, next.y - unit.y);
        self.units[index].stuck = 0.0;
        self.move_straight(index, next.x, next.y, step);
        let (mut nx, mut ny) = (next.x, next.y);
        // battle.py:1641-1657: spend the remaining step at up to four more waypoints.
        for _ in 0..4 {
            let unit = &self.units[index];
            if left <= 1e-9 || unit.x != nx || unit.y != ny {
                break;
            }
            let next = self.grid.next_step(&field, unit.x, unit.y);
            if next.at_goal || next.is_wall || next.x == unit.x && next.y == unit.y {
                break;
            }
            nx = next.x;
            ny = next.y;
            let distance = py_hypot(nx - unit.x, ny - unit.y);
            self.move_straight(index, nx, ny, left);
            left -= distance;
        }
    }

    fn move_straight(&mut self, index: usize, tx: f64, ty: f64, step: f64) {
        // battle.py:1659-1675: divide before multiplying; math.hypot, not f64::hypot.
        let unit = &mut self.units[index];
        let dx = tx - unit.x;
        let dy = ty - unit.y;
        let distance = py_hypot(dx, dy);
        if distance <= step || distance == 0.0 {
            unit.x = tx;
            unit.y = ty;
        } else {
            unit.x += dx / distance * step;
            unit.y += dy / distance * step;
        }
    }

    fn strike(&mut self, index: usize, target: Target) {
        // units.py:1835-1881: both troops use immediate spatial damage, no projectile.
        self.spatial_strike(index, target);
        if self.units[index].spec.name == "Valkyrie" && !self.target_alive(target) {
            self.units[index].target = None;
            self.units[index].wall_target = None;
        }
    }

    fn spatial_strike(&mut self, index: usize, target: Target) {
        let unit = &self.units[index];
        let (x, y) = if unit.spec.name == "Valkyrie" {
            (unit.x, unit.y)
        } else {
            let (x, y, _) = self.target_geometry(target);
            (x, y)
        };
        let radius = unit.spec.splash;
        let damage = unit.spec.damage;
        // units.py:1364-1383,1430-1440: buildings, then walls; append absent primary.
        // No hit can alter other candidates' liveness here, so the ordered scans
        // are equivalent to Python's snapshot without allocating a target list.
        for building in 0..self.buildings.len() {
            let victim = &self.buildings[building];
            let spec = victim.spec;
            if victim.alive
                && spec.counted
                && edge_distance(x, y, spec.cx, spec.cy, spec.half_hit) <= radius
            {
                self.hit_building(Target::Building(building), damage);
            }
        }
        for wall in 0..self.walls.len() {
            let victim = &self.walls[wall];
            let spec = victim.spec;
            if victim.alive
                && edge_distance(x, y, spec.tx as f64 + 0.5, spec.ty as f64 + 0.5, 0.5) <= radius
            {
                self.hit_building(Target::Wall(wall), damage);
            }
        }
        if let Target::Building(building) = target {
            if self.buildings[building].alive && !self.buildings[building].spec.counted {
                let (cx, cy, half) = self.target_geometry(target);
                if edge_distance(x, y, cx, cy, half) <= radius {
                    self.hit_building(target, damage);
                }
            }
        }
    }
}
