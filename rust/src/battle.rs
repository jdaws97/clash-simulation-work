use crate::defense::{self, Weapon};
use crate::geom::{dist, round6, round_half_even};
use crate::grid::Grid;
use crate::input::{BuildingSpec, Input, Scenario, WallSpec};
use crate::units::Unit;

const BUCKET_WIDTH: f64 = 4.0;
const BUCKET_SIDE: usize = 13;
const WORLD: usize = 50;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Target {
    Building(usize),
    Wall(usize),
}

pub struct Building<'a> {
    pub spec: &'a BuildingSpec,
    pub hp: f64,
    pub alive: bool,
    pub weapon: Option<Weapon<'a>>,
    pub fell: Option<f64>,
}

pub struct Wall<'a> {
    pub spec: &'a WallSpec,
    pub hp: f64,
    pub alive: bool,
}

#[derive(Clone, Copy)]
pub struct Splash {
    pub x: f64,
    pub y: f64,
    pub radius: f64,
    pub damage: f64,
    pub hits_air: bool,
    pub hits_ground: bool,
    pub falloff: bool,
}

pub enum Impact {
    Direct { unit: usize, damage: f64 },
    Area(Splash),
}

pub struct Pending {
    pub at: f64,
    pub impact: Impact,
}

pub struct ResultRow {
    pub angle: f64,
    pub seed: u64,
    pub stars: usize,
    pub destruction: f64,
    pub time: f64,
    pub fell: Vec<(usize, f64)>,
    pub units_left: usize,
}

pub struct Battle<'a> {
    pub input: &'a Input,
    scenario: &'a Scenario,
    pub t: f64,
    tick: usize,
    next_drop: usize,
    pub buildings: Vec<Building<'a>>,
    pub walls: Vec<Wall<'a>>,
    pub units: Vec<Unit<'a>>,
    pub grid: Grid,
    pub pending: Vec<Pending>,
    pending_scratch: Vec<Pending>,
    near_scratch: Vec<usize>,
    // battle.py:1079-1084: membership stays unchanged until the next tick.
    buckets: Vec<Vec<usize>>,
    bucket_order: Vec<usize>,
    wall_indices: Vec<Option<usize>>,
    total_counted: usize,
    destroyed_counted: usize,
}

impl<'a> Battle<'a> {
    pub fn new(input: &'a Input, scenario: &'a Scenario) -> Self {
        let mut grid = Grid::new(input.world);
        let mut buildings = Vec::with_capacity(input.buildings.len());
        let mut total_counted = 0;
        for spec in &input.buildings {
            // battle.py:248-264: banners start dead and never block pathing.
            let alive = spec.key != "banner";
            if alive {
                grid.block_square(spec.cx, spec.cy, spec.half_hit, true);
            }
            if spec.counted {
                total_counted += 1;
            }
            buildings.push(Building {
                spec,
                hp: spec.hp,
                alive,
                weapon: spec.weapon.as_ref().map(Weapon::new),
                fell: None,
            });
        }
        let mut walls = Vec::with_capacity(input.walls.len());
        let mut wall_indices = vec![None; WORLD * WORLD];
        for spec in &input.walls {
            grid.set_wall(spec.tx, spec.ty, true);
            wall_indices[spec.tx as usize * WORLD + spec.ty as usize] = Some(walls.len());
            walls.push(Wall {
                spec,
                hp: spec.hp,
                alive: true,
            });
        }
        Self {
            input,
            scenario,
            t: 0.0,
            tick: 0,
            next_drop: 0,
            buildings,
            walls,
            units: Vec::with_capacity(scenario.drops.len()),
            grid,
            pending: Vec::new(),
            pending_scratch: Vec::new(),
            near_scratch: Vec::with_capacity(scenario.drops.len()),
            buckets: (0..BUCKET_SIDE * BUCKET_SIDE)
                .map(|_| Vec::new())
                .collect(),
            bucket_order: Vec::with_capacity(scenario.drops.len()),
            wall_indices,
            total_counted,
            destroyed_counted: 0,
        }
    }

    pub fn run(mut self) -> ResultRow {
        // battle.py:797-809: termination is checked after time advances.
        while self.t < self.input.max_time {
            self.step();
            if self.destroyed_counted >= self.total_counted {
                break;
            }
            if self.next_drop == self.scenario.drops.len()
                && !self.units.iter().any(|unit| unit.alive)
            {
                break;
            }
        }
        ResultRow {
            angle: self.scenario.angle,
            seed: self.scenario.seed,
            stars: self.stars(),
            destruction: self.destruction() as f64,
            // The clock is already rounded to tenths (battle.py:950).
            time: round_half_even(self.t * 10.0) / 10.0,
            fell: self
                .buildings
                .iter()
                .filter_map(|building| building.fell.map(|t| (building.spec.id, t)))
                .collect(),
            units_left: self.units.iter().filter(|unit| unit.alive).count(),
        }
    }

    /// Per-tick state in the format of `rust_spike.py trace`, to find the
    /// first tick where the two engines part.
    pub fn trace(mut self) -> Vec<String> {
        let mut lines = Vec::new();
        let mut last: Vec<f64> = self.buildings.iter().map(|b| b.spec.hp).collect();
        let mut last_wall: Vec<f64> = self.walls.iter().map(|w| w.spec.hp).collect();
        while self.t < self.input.max_time {
            lines.push(format!("T {:?}", self.t));
            self.step();
            for unit in self.units.iter().filter(|unit| unit.alive) {
                lines.push(format!("U {} {:?} {:?} {:?} {:?}", unit.id, unit.x, unit.y, unit.hp, unit.cooldown));
            }
            for (i, b) in self.buildings.iter().enumerate() {
                if b.hp != last[i] {
                    last[i] = b.hp;
                    lines.push(format!("B {} {:?}", b.spec.id, b.hp));
                }
            }
            for (i, w) in self.walls.iter().enumerate() {
                if w.hp != last_wall[i] {
                    last_wall[i] = w.hp;
                    lines.push(format!("B w{},{} {:?}", w.spec.tx, w.spec.ty, w.hp));
                }
            }
            if self.destroyed_counted >= self.total_counted
                || self.next_drop == self.scenario.drops.len() && !self.units.iter().any(|u| u.alive)
            {
                break;
            }
        }
        lines
    }

    fn step(&mut self) {
        // battle.py:902-935: drops, buckets, impacts, attackers, separation, defenses.
        while self.next_drop < self.scenario.drops.len()
            && self.scenario.drops[self.next_drop].tick <= self.tick
        {
            self.deploy();
            self.next_drop += 1;
        }
        self.rebuild_buckets();
        self.resolve_pending();
        for index in 0..self.units.len() {
            if self.units[index].alive {
                self.act_attacker(index);
            }
        }
        self.separate();
        for index in 0..self.buildings.len() {
            if self.buildings[index].alive {
                if let Some(mut weapon) = self.buildings[index].weapon.take() {
                    defense::act(self, index, &mut weapon);
                    self.buildings[index].weapon = Some(weapon);
                }
            }
        }
        // battle.py:938-950: prune at t=0 too; never round cooldowns/deadlines.
        if round_half_even(self.t * 10.0) as usize % 50 == 0 {
            self.grid.prune();
        }
        self.t = round6(self.t + self.input.dt);
        self.tick += 1;
    }

    fn deploy(&mut self) {
        let drop = &self.scenario.drops[self.next_drop];
        let spec = self
            .input
            .units
            .iter()
            .find(|spec| spec.name == drop.name)
            .expect("validated troop name");
        // battle.py:457-462: an illegal drop lands on the nearest legal tile
        // centre (first minimum, x then y), judged against what stands now.
        let no_deploy = self.no_deploy();
        let legal = |tx: i32, ty: i32| !no_deploy[tx as usize * WORLD + ty as usize];
        let (mut x, mut y) = (drop.x, drop.y);
        let inside = (0.0..WORLD as f64).contains(&x) && (0.0..WORLD as f64).contains(&y);
        if !inside || !legal(x as i32, y as i32) {
            let mut best = f64::INFINITY;
            for tx in 0..WORLD as i32 {
                for ty in 0..WORLD as i32 {
                    if legal(tx, ty) {
                        let (px, py) = (tx as f64 + 0.5, ty as f64 + 0.5);
                        let d = (px - drop.x).powi(2) + (py - drop.y).powi(2);
                        if d < best {
                            best = d;
                            (x, y) = (px, py);
                        }
                    }
                }
            }
        }
        // battle.py:427-480: IDs start at one; each drop acts immediately.
        let id = self.units.len() + 1;
        self.units.push(Unit::new(spec, id, x, y));
    }

    /// battle.py:370-390: tiles of standing buildings (banners always) and
    /// walls, grown by one tile all round.
    fn no_deploy(&self) -> Vec<bool> {
        let mut blocked = vec![false; WORLD * WORLD];
        let mut mark = |tx: i32, ty: i32| {
            for dx in -1..=1 {
                for dy in -1..=1 {
                    let (x, y) = (tx + dx, ty + dy);
                    if (0..WORLD as i32).contains(&x) && (0..WORLD as i32).contains(&y) {
                        blocked[x as usize * WORLD + y as usize] = true;
                    }
                }
            }
        };
        for b in &self.buildings {
            let spec = b.spec;
            if spec.key == "banner" || b.alive && spec.key != "tesla" {
                let half = spec.size as f64 / 2.0;
                let x0 = round_half_even(spec.cx - half) as i32;
                let y0 = round_half_even(spec.cy - half) as i32;
                for dx in 0..spec.size {
                    for dy in 0..spec.size {
                        mark(x0 + dx, y0 + dy);
                    }
                }
            }
        }
        for w in &self.walls {
            if w.alive {
                mark(w.spec.tx, w.spec.ty);
            }
        }
        blocked
    }

    pub fn building_targetable(&self, index: usize) -> bool {
        // battle.py:536-548: Town Hall is permitted even if uncounted.
        let building = &self.buildings[index];
        building.alive && (building.spec.counted || building.spec.key == "th")
    }

    pub fn target_alive(&self, target: Target) -> bool {
        match target {
            Target::Building(index) => self.buildings[index].alive,
            Target::Wall(index) => self.walls[index].alive,
        }
    }

    pub fn target_geometry(&self, target: Target) -> (f64, f64, f64) {
        match target {
            Target::Building(index) => {
                let spec = self.buildings[index].spec;
                (spec.cx, spec.cy, spec.half_hit)
            }
            Target::Wall(index) => {
                let spec = self.walls[index].spec;
                (spec.tx as f64 + 0.5, spec.ty as f64 + 0.5, 0.5)
            }
        }
    }

    pub fn wall_at(&self, x: f64, y: f64) -> Option<usize> {
        let tx = x as i32;
        let ty = y as i32;
        if tx < 0 || ty < 0 || tx >= WORLD as i32 || ty >= WORLD as i32 {
            return None;
        }
        self.wall_indices[tx as usize * WORLD + ty as usize]
    }

    fn destruction(&self) -> usize {
        // battle.py:518-534: ceiling percent is also used for the 50% star.
        let total = self.total_counted.max(1);
        (100 * self.destroyed_counted + total - 1) / total
    }

    fn stars(&self) -> usize {
        usize::from(self.destruction() >= 50)
            + usize::from(
                self.buildings
                    .iter()
                    .any(|building| building.spec.key == "th" && !building.alive),
            )
            + usize::from(self.destroyed_counted >= self.total_counted)
    }

    pub fn hit_unit(&mut self, index: usize, amount: f64) {
        // battle.py:587-652,671-691: no reductions or death effects in this fixture.
        let unit = &mut self.units[index];
        if !unit.alive || amount <= 0.0 {
            return;
        }
        unit.hp -= amount;
        if unit.hp <= 0.0 {
            self.kill(index);
        }
    }

    fn kill(&mut self, index: usize) {
        self.units[index].alive = false;
        self.units[index].hp = 0.0;
    }

    pub fn hit_building(&mut self, target: Target, amount: f64) {
        // battle.py:693-732: full damage, including overkill, before immediate death.
        if !self.target_alive(target) || amount <= 0.0 {
            return;
        }
        let hp = match target {
            Target::Building(index) => &mut self.buildings[index].hp,
            Target::Wall(index) => &mut self.walls[index].hp,
        };
        *hp -= amount;
        if *hp <= 0.0 {
            self.destroy(target);
        }
    }

    fn destroy(&mut self, target: Target) {
        // battle.py:735-750: walls change the grid but never destruction credit.
        match target {
            Target::Building(index) => {
                let building = &mut self.buildings[index];
                building.alive = false;
                building.hp = 0.0;
                building.fell = Some(round_half_even(self.t * 100.0) / 100.0);
                let spec = building.spec;
                self.grid.block_square(spec.cx, spec.cy, spec.half_hit, false);
                if spec.counted {
                    self.destroyed_counted += 1;
                }
            }
            Target::Wall(index) => {
                let wall = &mut self.walls[index];
                wall.alive = false;
                wall.hp = 0.0;
                self.grid.set_wall(wall.spec.tx, wall.spec.ty, false);
            }
        }
    }

    fn resolve_pending(&mut self) {
        // battle.py:960-1000: append order, not impact-time order; sources may be dead.
        let mut old = std::mem::take(&mut self.pending);
        self.pending = std::mem::take(&mut self.pending_scratch);
        for pending in old.drain(..) {
            if pending.at > self.t {
                self.pending.push(pending);
                continue;
            }
            match pending.impact {
                Impact::Direct { unit, damage } => self.hit_unit(unit, damage),
                Impact::Area(splash) => self.splash_units(splash),
            }
        }
        self.pending_scratch = old;
    }

    pub fn splash_units(&mut self, splash: Splash) {
        // battle.py:764-774: WT matches height; mortar falloff includes the boundary.
        let mut near = std::mem::take(&mut self.near_scratch);
        self.attackers_near(splash.x, splash.y, splash.radius, &mut near);
        for &index in &near {
            let unit = &self.units[index];
            if unit.spec.flying && !splash.hits_air || !unit.spec.flying && !splash.hits_ground {
                continue;
            }
            let distance = dist(unit.x, unit.y, splash.x, splash.y);
            let amount = if splash.falloff && splash.radius > 0.0 {
                splash.damage * (1.0 - 0.5 * distance / splash.radius)
            } else {
                splash.damage
            };
            self.hit_unit(index, amount);
        }
        near.clear();
        self.near_scratch = near;
    }

    fn rebuild_buckets(&mut self) {
        for &index in &self.bucket_order {
            self.buckets[index].clear();
        }
        self.bucket_order.clear();
        for (index, unit) in self.units.iter().enumerate() {
            if unit.alive {
                let i = (unit.x / BUCKET_WIDTH) as usize;
                let j = (unit.y / BUCKET_WIDTH) as usize;
                let bucket = i * BUCKET_SIDE + j;
                if self.buckets[bucket].is_empty() {
                    self.bucket_order.push(bucket);
                }
                self.buckets[bucket].push(index);
            }
        }
    }

    pub fn attackers_near(&self, x: f64, y: f64, radius: f64, out: &mut Vec<usize>) {
        out.clear();
        let radius_squared = radius * radius;
        // battle.py:556-573: int truncates toward zero, then x/y ascending.
        let low_i = ((x - radius) / BUCKET_WIDTH) as i32;
        let high_i = ((x + radius) / BUCKET_WIDTH) as i32;
        let low_j = ((y - radius) / BUCKET_WIDTH) as i32;
        let high_j = ((y + radius) / BUCKET_WIDTH) as i32;
        for i in low_i.max(0)..=high_i.min(BUCKET_SIDE as i32 - 1) {
            for j in low_j.max(0)..=high_j.min(BUCKET_SIDE as i32 - 1) {
                for &index in &self.buckets[i as usize * BUCKET_SIDE + j as usize] {
                    let unit = &self.units[index];
                    let dx = unit.x - x;
                    let dy = unit.y - y;
                    if dx * dx + dy * dy <= radius_squared && unit.alive {
                        out.push(index);
                    }
                }
            }
        }
    }

    fn separate(&mut self) {
        // battle.py:1087-1116: insertion-ordered buckets, pairs i<j, same height only.
        for bucket_position in 0..self.bucket_order.len() {
            let bucket = self.bucket_order[bucket_position];
            let count = self.buckets[bucket].len();
            for i in 0..count {
                let first = self.buckets[bucket][i];
                if !self.units[first].alive || self.units[first].spec.speed <= 0.0 {
                    continue;
                }
                let first_spec = self.units[first].spec;
                let first_radius = 0.35 + 0.015 * first_spec.housing.min(30) as f64;
                for j in i + 1..count {
                    let second = self.buckets[bucket][j];
                    let other = &self.units[second];
                    if !other.alive
                        || other.spec.flying != first_spec.flying
                        || other.spec.speed <= 0.0
                    {
                        continue;
                    }
                    let second_radius = 0.35 + 0.015 * other.spec.housing.min(30) as f64;
                    let mut dx = other.x - self.units[first].x;
                    let mut dy = other.y - self.units[first].y;
                    let squared = dx * dx + dy * dy;
                    let limit = first_radius + second_radius;
                    if squared >= limit * limit {
                        continue;
                    }
                    let mut distance = squared.sqrt();
                    let push = if distance < 1e-6 {
                        let angle = (self.units[first].id as f64 * 2.399)
                            % (2.0 * std::f64::consts::PI);
                        dx = angle.cos();
                        dy = angle.sin();
                        distance = 1.0;
                        limit * 0.25
                    } else {
                        (limit - distance) * 0.25
                    };
                    let ux = dx / distance * push;
                    let uy = dy / distance * push;
                    self.nudge(first, -ux, -uy);
                    self.nudge(second, ux, uy);
                }
            }
        }
    }

    fn nudge(&mut self, index: usize, dx: f64, dy: f64) {
        // battle.py:1118-1130: test the unclamped destination, then clamp on acceptance.
        let unit = &mut self.units[index];
        let nx = unit.x + dx;
        let ny = unit.y + dy;
        if !unit.spec.flying {
            let (i, j) = self.grid.cell(nx, ny);
            let cell = self.grid.index(i, j);
            if self.grid.blocked[cell] || self.grid.wall[cell] {
                return;
            }
        }
        unit.x = nx.clamp(0.1, WORLD as f64 - 0.1);
        unit.y = ny.clamp(0.1, WORLD as f64 - 0.1);
    }
}
