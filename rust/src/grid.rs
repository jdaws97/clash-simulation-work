use std::collections::HashMap;
use std::rc::Rc;

use crate::geom::round_half_even;

pub const RES: usize = 2;
pub const INF: f32 = 1_000_000_000.0;
// battle.py:58-60: sqrt(0.5) / RES + 1e-6, and WALL_COST["normal"] / RES.
pub const GOAL_REACH_MIN: f64 = std::f64::consts::FRAC_1_SQRT_2 / 2.0 + 0.000_001;
pub const NORMAL_WALL_EXTRA: f64 = 12.0 / RES as f64;

// pathing.py:20-24: both relaxation and next_step use this order.
const NEIGHBORS: [(isize, isize); 8] = [
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
];
const NO_NEIGHBOR: usize = usize::MAX;
// pathing.py:96-99: check [ci, nj] before [ni, cj] for each diagonal.
const DIAGONAL_CORNERS: [(usize, usize); 4] = [(2, 0), (3, 0), (2, 1), (3, 1)];

pub type Field = Rc<[f32]>;

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub enum TargetIdentity {
    Building(usize),
    Wall(i32, i32),
}

#[derive(Clone, Copy, Debug)]
pub struct NextStep {
    pub x: f64,
    pub y: f64,
    pub is_wall: bool,
    pub at_goal: bool,
}

#[derive(Clone, Copy, Eq, Hash, PartialEq)]
enum CacheKey {
    Target {
        identity: TargetIdentity,
        x: u64,
        y: u64,
        reach: u64,
        wall_extra: u64,
    },
    Source {
        tile_i: usize,
        tile_j: usize,
        wall_extra: u64,
    },
}

enum CachedGoal {
    Target(Vec<bool>),
    Source((usize, usize)),
}

struct CachedField {
    key: CacheKey,
    version: u64,
    distances: Field,
    goal: CachedGoal,
}

struct Change {
    version: u64,
    decrease_only: bool,
    i0: isize,
    i1: isize,
    j0: isize,
    j1: isize,
}

pub struct Grid {
    pub n: usize,
    // Flat arrays are indexed x * n + y, matching NumPy's [x, y] layout.
    pub blocked: Vec<bool>,
    pub wall: Vec<bool>,
    pub version: u64,
    cache: Vec<CachedField>,
    cache_indices: HashMap<CacheKey, usize>,
    log: Vec<Change>,
    neighbors: Vec<[usize; 8]>,
    distance_buffer: Vec<f32>,
    seed: Vec<bool>,
    source_goal: Vec<bool>,
    heap: Heap,
}

impl Grid {
    pub fn new(world_tiles: usize) -> Self {
        let n = world_tiles * RES;
        assert!(n > 0, "grid must have at least one cell");
        Self {
            n,
            blocked: vec![false; n * n],
            wall: vec![false; n * n],
            version: 0,
            cache: Vec::new(),
            cache_indices: HashMap::new(),
            log: Vec::new(),
            neighbors: neighbor_indices(n),
            distance_buffer: vec![INF; n * n],
            seed: vec![false; n * n],
            source_goal: vec![false; n * n],
            heap: Heap::new(n * n * 8 + 16),
        }
    }

    pub fn index(&self, i: usize, j: usize) -> usize {
        i * self.n + j
    }

    // pathing.py:189-199: rounded, half-open NumPy slices; every write versions.
    pub fn block_square(&mut self, cx: f64, cy: f64, half: f64, value: bool) {
        let lo_i = round_half_even((cx - half) * RES as f64) as isize;
        let hi_i = round_half_even((cx + half) * RES as f64) as isize;
        let lo_j = round_half_even((cy - half) * RES as f64) as isize;
        let hi_j = round_half_even((cy + half) * RES as f64) as isize;
        for i in slice_bound(lo_i, self.n)..slice_bound(hi_i, self.n) {
            for j in slice_bound(lo_j, self.n)..slice_bound(hi_j, self.n) {
                let index = self.index(i, j);
                self.blocked[index] = value;
            }
        }
        self.changed(lo_i, hi_i, lo_j, hi_j, !value);
    }

    pub fn set_wall(&mut self, tx: i32, ty: i32, present: bool) {
        let lo_i = tx as isize * RES as isize;
        let hi_i = (tx as isize + 1) * RES as isize;
        let lo_j = ty as isize * RES as isize;
        let hi_j = (ty as isize + 1) * RES as isize;
        for i in slice_bound(lo_i, self.n)..slice_bound(hi_i, self.n) {
            for j in slice_bound(lo_j, self.n)..slice_bound(hi_j, self.n) {
                let index = self.index(i, j);
                self.wall[index] = present;
            }
        }
        self.changed(lo_i, hi_i, lo_j, hi_j, !present);
    }

    // pathing.py:185-187: log every write, with a one-cell repair border.
    fn changed(&mut self, i0: isize, i1: isize, j0: isize, j1: isize, decrease_only: bool) {
        self.version += 1;
        self.log.push(Change {
            version: self.version,
            decrease_only,
            i0: (i0 - 1).max(0),
            i1: (i1 + 1).min(self.n as isize),
            j0: (j0 - 1).max(0),
            j1: (j1 + 1).min(self.n as isize),
        });
    }

    // pathing.py:272-275: truncate before clamping, rather than rounding.
    pub fn cell(&self, x: f64, y: f64) -> (usize, usize) {
        let i = ((x * RES as f64) as isize).clamp(0, self.n as isize - 1);
        let j = ((y * RES as f64) as isize).clamp(0, self.n as isize - 1);
        (i as usize, j as usize)
    }

    pub fn goal_mask(&self, cx: f64, cy: f64, half: f64, reach: f64) -> Vec<bool> {
        let mut goal = vec![false; self.n * self.n];
        let (lo_i, hi_i) = goal_bounds(self.n, cx, half, reach);
        let (lo_j, hi_j) = goal_bounds(self.n, cy, half, reach);
        // pathing.py:121-141: compare squared distances in float64.
        for i in lo_i..=hi_i {
            let px = (i as f64 + 0.5) / 2.0;
            let dx = ((px - cx).abs() - half).max(0.0);
            for j in lo_j..=hi_j {
                let py = (j as f64 + 0.5) / 2.0;
                let dy = ((py - cy).abs() - half).max(0.0);
                if dx * dx + dy * dy <= reach * reach {
                    goal[self.index(i as usize, j as usize)] = true;
                }
            }
        }
        goal
    }

    pub fn field(
        &mut self,
        identity: TargetIdentity,
        cx: f64,
        cy: f64,
        half: f64,
        reach: f64,
        wall_extra: f64,
    ) -> Field {
        // battle.py:1604-1611: callers pass max(range, GOAL_REACH_MIN),
        // or max(0.5, GOAL_REACH_MIN) and half=0 for a positioning goal.
        // Only normal wall mode is used here, so its cost identifies the mode.
        let key = CacheKey::Target {
            identity,
            x: float_key(cx),
            y: float_key(cy),
            reach: float_key(reach),
            wall_extra: float_key(wall_extra),
        };
        if let Some(distances) = self.cached(&key) {
            return distances;
        }
        let goal = self.goal_mask(cx, cy, half, reach);
        let mut distances = None;
        // pathing.py:222-234: a stale target field needs an identical goal mask.
        if let Some(&index) = self.cache_indices.get(&key) {
            let same_goal = match &self.cache[index].goal {
                CachedGoal::Target(cached_goal) => cached_goal == &goal,
                CachedGoal::Source(_) => false,
            };
            if same_goal {
                distances = self.repair(index, &goal, wall_extra);
            }
        }
        let distances = match distances {
            Some(distances) => distances,
            None => self.dijkstra(&goal, wall_extra),
        };
        self.store_field(key, Rc::clone(&distances), CachedGoal::Target(goal));
        distances
    }

    pub fn source_field(&mut self, x: f64, y: f64, wall_extra: f64) -> Field {
        let (i, j) = self.cell(x, y);
        let key = CacheKey::Source {
            tile_i: i / RES,
            tile_j: j / RES,
            wall_extra: float_key(wall_extra),
        };
        // pathing.py:237-255: same-version hits reuse the first half-cell's
        // field for the entire tile, without checking the new source cell.
        if let Some(distances) = self.cached(&key) {
            return distances;
        }
        // Reuse this temporary mask; source cache entries store only the cell.
        let mut goal = std::mem::take(&mut self.source_goal);
        goal.fill(false);
        goal[self.index(i, j)] = true;
        let mut distances = None;
        // pathing.py:245-255: repair only the same half-cell, passing its goal
        // mask so a source freed by a removed building restarts at zero.
        if let Some(&index) = self.cache_indices.get(&key) {
            let same_source = matches!(
                &self.cache[index].goal,
                CachedGoal::Source(cell) if *cell == (i, j)
            );
            if same_source {
                distances = self.repair(index, &goal, wall_extra);
            }
        }
        let distances = match distances {
            Some(distances) => distances,
            None => self.dijkstra(&goal, wall_extra),
        };
        self.source_goal = goal;
        self.store_field(key, Rc::clone(&distances), CachedGoal::Source((i, j)));
        distances
    }

    pub fn building_costs(
        &mut self,
        x: f64,
        y: f64,
        wall_extra: f64,
        xs: &[f64],
        ys: &[f64],
        halves: &[f64],
        reach: f64,
    ) -> Vec<f32> {
        assert_eq!(xs.len(), ys.len());
        assert_eq!(xs.len(), halves.len());
        let distances = self.source_field(x, y, wall_extra);
        let mut costs = vec![INF; xs.len()];
        // pathing.py:145-169; battle.py:1432-1441: output stays float32,
        // geometry stays float64, and strict comparisons retain the first tie.
        for b in 0..xs.len() {
            let (lo_i, hi_i) = goal_bounds(self.n, xs[b], halves[b], reach);
            let (lo_j, hi_j) = goal_bounds(self.n, ys[b], halves[b], reach);
            let mut best = INF;
            for i in lo_i..=hi_i {
                let px = (i as f64 + 0.5) / 2.0;
                let dx = ((px - xs[b]).abs() - halves[b]).max(0.0);
                for j in lo_j..=hi_j {
                    let py = (j as f64 + 0.5) / 2.0;
                    let dy = ((py - ys[b]).abs() - halves[b]).max(0.0);
                    let distance = distances[self.index(i as usize, j as usize)];
                    if dx * dx + dy * dy <= reach * reach && distance < best {
                        best = distance;
                    }
                }
            }
            costs[b] = best;
        }
        costs
    }

    pub fn next_step(&self, distances: &[f32], x: f64, y: f64) -> NextStep {
        let (i, j) = self.cell(x, y);
        let here = distances[self.index(i, j)];
        if here <= 0.0 {
            return NextStep {
                x,
                y,
                is_wall: false,
                at_goal: true,
            };
        }
        let mut best = here;
        let (mut bi, mut bj) = (i, j);
        // pathing.py:287-297: choose the lowest stored distance, retaining the
        // earlier neighbor on ties. Do not check obstacles or corner cutting.
        for (di, dj) in NEIGHBORS {
            let ni = i as isize + di;
            let nj = j as isize + dj;
            if ni < 0 || nj < 0 || ni >= self.n as isize || nj >= self.n as isize {
                continue;
            }
            let (ni, nj) = (ni as usize, nj as usize);
            let distance = distances[self.index(ni, nj)];
            if distance < best {
                best = distance;
                bi = ni;
                bj = nj;
            }
        }
        if bi == i && bj == j {
            return NextStep {
                x,
                y,
                is_wall: false,
                at_goal: here >= INF,
            };
        }
        NextStep {
            x: (bi as f64 + 0.5) / RES as f64,
            y: (bj as f64 + 0.5) / RES as f64,
            is_wall: self.wall[self.index(bi, bj)],
            at_goal: false,
        }
    }

    pub fn prune(&mut self) {
        // pathing.py:261-270: stable sorting preserves the cache's current
        // insertion order on equal versions, including after earlier prunes.
        if self.cache.len() > 600 {
            self.cache
                .sort_by(|left, right| right.version.cmp(&left.version));
            self.cache.truncate(400);
            self.cache_indices.clear();
            for (index, entry) in self.cache.iter().enumerate() {
                self.cache_indices.insert(entry.key, index);
            }
        }
        if let Some(oldest) = self.cache.iter().map(|entry| entry.version).min() {
            self.log.retain(|change| change.version > oldest);
        }
    }

    fn cached(&self, key: &CacheKey) -> Option<Field> {
        let index = *self.cache_indices.get(key)?;
        let entry = &self.cache[index];
        if entry.version == self.version {
            Some(Rc::clone(&entry.distances))
        } else {
            None
        }
    }

    fn store_field(&mut self, key: CacheKey, distances: Field, goal: CachedGoal) {
        let entry = CachedField {
            key,
            version: self.version,
            distances,
            goal,
        };
        // pathing.py:234,255: replacing a dict value keeps its insertion order.
        if let Some(&index) = self.cache_indices.get(&key) {
            self.cache[index] = entry;
        } else {
            self.cache_indices.insert(key, self.cache.len());
            self.cache.push(entry);
        }
    }

    fn repair(&mut self, cache_index: usize, goal: &[bool], wall_extra: f64) -> Option<Field> {
        let entry = &self.cache[cache_index];
        let version = entry.version;
        // pathing.py:201-214: require an unbroken log of removal-only changes.
        if self.log.is_empty() || self.log[0].version > version + 1 {
            return None;
        }
        self.seed.fill(false);
        for change in self.log.iter().rev() {
            if change.version <= version {
                break;
            }
            if !change.decrease_only {
                return None;
            }
            let j0 = slice_bound(change.j0, self.n);
            let j1 = slice_bound(change.j1, self.n);
            for i in slice_bound(change.i0, self.n)..slice_bound(change.i1, self.n) {
                for j in j0..j1 {
                    self.seed[i * self.n + j] = true;
                }
            }
        }

        // pathing.py:215-220: copy the old field and reset freed goal cells.
        self.distance_buffer.copy_from_slice(&entry.distances);
        for (index, &is_goal) in goal.iter().enumerate() {
            if self.seed[index] && is_goal && !self.blocked[index] {
                self.distance_buffer[index] = 0.0;
            }
        }
        Some(self.relax(wall_extra))
    }

    fn dijkstra(&mut self, goal: &[bool], wall_extra: f64) -> Field {
        // pathing.py:28-35: full fields use the same relaxation as repairs.
        for (index, &is_goal) in goal.iter().enumerate() {
            self.distance_buffer[index] = if is_goal && !self.blocked[index] {
                0.0
            } else {
                INF
            };
        }
        self.seed.copy_from_slice(goal);
        self.relax(wall_extra)
    }

    fn relax(&mut self, wall_extra: f64) -> Field {
        self.heap.clear();
        // pathing.py:50-64: flat order is x then y, with the same finite-seed test.
        for (index, &is_seed) in self.seed.iter().enumerate() {
            if is_seed && !self.blocked[index] && self.distance_buffer[index] < INF {
                self.heap.push(self.distance_buffer[index], index);
            }
        }
        // pathing.py:220,233,254: wall_extra is converted to float32 at entry.
        let wall_extra = f64::from(wall_extra as f32);
        let diagonal = 2.0_f64.sqrt() / RES as f64;
        while let Some((distance, index)) = self.heap.pop() {
            if distance > self.distance_buffer[index] {
                continue;
            }
            // pathing.py:100-104: compute each step-plus-wall cost once per pop.
            let mut straight_cost = 0.5;
            let mut diagonal_cost = diagonal;
            if self.wall[index] {
                straight_cost += wall_extra;
                diagonal_cost += wall_extra;
            }
            let neighbors = &self.neighbors[index];
            for (q, &next) in neighbors.iter().enumerate() {
                if next == NO_NEIGHBOR || self.blocked[next] {
                    continue;
                }
                if q >= 4 {
                    // A valid diagonal always has both cardinal neighbors.
                    let (along_y, along_x) = DIAGONAL_CORNERS[q - 4];
                    if self.blocked[neighbors[along_y]] || self.blocked[neighbors[along_x]] {
                        continue;
                    }
                }
                // pathing.py:100-109: charge the current cell's wall, and add
                // that cost to the step before adding the popped f32 distance.
                let cost = if q < 4 {
                    straight_cost
                } else {
                    diagonal_cost
                };
                let candidate = f64::from(distance) + cost;
                // Compare in f64 BEFORE either the distance or heap key is
                // rounded to f32. Even an equal rounded value is pushed.
                if candidate < f64::from(self.distance_buffer[next]) {
                    self.distance_buffer[next] = candidate as f32;
                    self.heap.push(candidate as f32, next);
                }
            }
        }
        // Cached/returned fields own their storage; scratch buffers stay reusable.
        Rc::from(self.distance_buffer.as_slice())
    }
}

fn neighbor_indices(n: usize) -> Vec<[usize; 8]> {
    let mut neighbors = vec![[NO_NEIGHBOR; 8]; n * n];
    // pathing.py:89-99: precompute geometry without changing neighbor order.
    for i in 0..n {
        for j in 0..n {
            for (q, (di, dj)) in NEIGHBORS.iter().copied().enumerate() {
                let ni = i as isize + di;
                let nj = j as isize + dj;
                if ni >= 0 && nj >= 0 && ni < n as isize && nj < n as isize {
                    neighbors[i * n + j][q] = ni as usize * n + nj as usize;
                }
            }
        }
    }
    neighbors
}

fn float_key(value: f64) -> u64 {
    // Python dictionary keys consider +0.0 and -0.0 equal.
    if value == 0.0 {
        0
    } else {
        value.to_bits()
    }
}

fn slice_bound(bound: isize, n: usize) -> usize {
    if bound < 0 {
        (bound + n as isize).max(0) as usize
    } else {
        (bound as usize).min(n)
    }
}

fn goal_bounds(n: usize, center: f64, half: f64, reach: f64) -> (isize, isize) {
    let low = ((center - half - reach - 1.0) * 2.0).max(0.0) as isize;
    let high = ((center + half + reach + 1.0) * 2.0).min(n as f64 - 1.0) as isize;
    (low, high)
}

// pathing.py:45-84,107-117: parallel-array min-heap with no index tie-break.
struct Heap {
    keys: Vec<f32>,
    indices: Vec<usize>,
}

impl Heap {
    fn new(capacity: usize) -> Self {
        Self {
            keys: Vec::with_capacity(capacity),
            indices: Vec::with_capacity(capacity),
        }
    }

    fn clear(&mut self) {
        self.keys.clear();
        self.indices.clear();
    }

    fn push(&mut self, key: f32, index: usize) {
        let mut child = self.keys.len();
        self.keys.push(key);
        self.indices.push(index);
        while child > 0 {
            let parent = (child - 1) >> 1;
            if self.keys[parent] <= self.keys[child] {
                break;
            }
            self.keys.swap(parent, child);
            self.indices.swap(parent, child);
            child = parent;
        }
    }

    fn pop(&mut self) -> Option<(f32, usize)> {
        if self.keys.is_empty() {
            return None;
        }
        let result = (self.keys[0], self.indices[0]);
        self.keys.swap_remove(0);
        self.indices.swap_remove(0);
        let mut current = 0;
        loop {
            let left = 2 * current + 1;
            let right = left + 1;
            let mut smallest = current;
            if left < self.keys.len() && self.keys[left] < self.keys[smallest] {
                smallest = left;
            }
            if right < self.keys.len() && self.keys[right] < self.keys[smallest] {
                smallest = right;
            }
            if smallest == current {
                break;
            }
            self.keys.swap(smallest, current);
            self.indices.swap(smallest, current);
            current = smallest;
        }
        Some(result)
    }
}
