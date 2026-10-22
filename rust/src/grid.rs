use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashMap};

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

// Cache indices remain valid until the next prune.
#[derive(Clone, Copy)]
pub struct Field(usize);

// Nonnegative, non-NaN f32 keys have the same order as their bits.
type Frontier = BinaryHeap<Reverse<(u32, usize)>>;

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

struct CachedField {
    key: CacheKey,
    version: u64,
    distances: Vec<f32>,
    frontier: Frontier,
    wall_extra: f64,
}

pub struct Grid {
    pub n: usize,
    // Flat arrays are indexed x * n + y, matching NumPy's [x, y] layout.
    pub blocked: Vec<bool>,
    pub wall: Vec<bool>,
    pub version: u64,
    cache: Vec<CachedField>,
    cache_indices: HashMap<CacheKey, usize>,
    neighbors: Vec<[usize; 8]>,
    spare_fields: Vec<CachedField>,
    goal_marks: Vec<bool>,
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
            neighbors: neighbor_indices(n),
            spare_fields: Vec::new(),
            goal_marks: vec![false; n * n],
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
        self.version += 1;
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
        // pathing.py:185-187,197-199: even an unchanged write versions the grid.
        self.version += 1;
    }

    // pathing.py:272-275: truncate before clamping, rather than rounding.
    pub fn cell(&self, x: f64, y: f64) -> (usize, usize) {
        let i = ((x * RES as f64) as isize).clamp(0, self.n as isize - 1);
        let j = ((y * RES as f64) as isize).clamp(0, self.n as isize - 1);
        (i as usize, j as usize)
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
        if let Some(field) = self.cached(&key) {
            return field;
        }
        let field = self.reset_field(key, wall_extra);
        let entry = &mut self.cache[field.0];
        let blocked = &self.blocked;
        // pathing.py:28-35: only unblocked goal cells seed the field.
        for_each_goal_cell(self.n, cx, cy, half, reach, |cell| {
            if !blocked[cell] {
                entry.seed(cell);
            }
        });
        field
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
        if let Some(field) = self.cached(&key) {
            return field;
        }
        let field = self.reset_field(key, wall_extra);
        let cell = self.index(i, j);
        if !self.blocked[cell] {
            self.cache[field.0].seed(cell);
        }
        field
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
        let field = self.source_field(x, y, wall_extra);
        let entry = &mut self.cache[field.0];
        let goal_marks = &mut self.goal_marks;
        goal_marks.fill(false);
        // Stored values below the frontier are already final.
        let frontier_min = entry
            .frontier
            .peek()
            .map(|&Reverse((key, _))| f32::from_bits(key))
            .unwrap_or(INF);
        let mut best = INF;
        for b in 0..xs.len() {
            for_each_goal_cell(self.n, xs[b], ys[b], halves[b], reach, |cell| {
                goal_marks[cell] = true;
                let distance = entry.distances[cell];
                // Earlier queries may already have settled this pool's goals.
                if distance < frontier_min && distance < best {
                    best = distance;
                }
            });
        }
        while let Some(&Reverse((key, _))) = entry.frontier.peek() {
            if f32::from_bits(key) > best {
                break;
            }
            if let Some((distance, cell)) =
                entry.expand(&self.blocked, &self.wall, &self.neighbors)
            {
                if goal_marks[cell] && distance < best {
                    best = distance;
                }
            }
        }

        // Once the frontier exceeds best, every value <= best is final.
        // Larger stored upper bounds cannot change the first argmin or its
        // >= 1e8 fallback (pathing.py:145-169; battle.py:1432-1441).
        let distances = &entry.distances;
        let mut costs = vec![INF; xs.len()];
        // pathing.py:145-169; battle.py:1432-1441: output stays float32,
        // geometry stays float64, and strict comparisons retain the first tie.
        for b in 0..xs.len() {
            let mut best = INF;
            for_each_goal_cell(self.n, xs[b], ys[b], halves[b], reach, |cell| {
                let distance = distances[cell];
                if distance < best {
                    best = distance;
                }
            });
            costs[b] = best;
        }
        costs
    }

    pub fn distance(&mut self, field: Field, cell: usize) -> f32 {
        self.ensure(field, cell);
        self.cache[field.0].distances[cell]
    }

    pub fn next_step(&mut self, field: Field, x: f64, y: f64) -> NextStep {
        let (i, j) = self.cell(x, y);
        let cell = self.index(i, j);
        self.ensure(field, cell);
        let distances = &self.cache[field.0].distances;
        let here = distances[cell];
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
        // Unsettled neighbors have stored values >= here and cannot be chosen.
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
        // Drop stale entries instead of retaining them for repair. Keep live
        // source fields so whole-tile hits still use the first caller's cell.
        let mut index = 0;
        while index < self.cache.len() {
            if self.cache[index].version != self.version {
                let mut entry = self.cache.swap_remove(index);
                entry.frontier.clear();
                self.spare_fields.push(entry);
            } else {
                index += 1;
            }
        }
        self.spare_fields.truncate(400);
        self.cache_indices.clear();
        for (index, entry) in self.cache.iter().enumerate() {
            self.cache_indices.insert(entry.key, index);
        }
    }

    fn cached(&self, key: &CacheKey) -> Option<Field> {
        let index = *self.cache_indices.get(key)?;
        let entry = &self.cache[index];
        if entry.version == self.version {
            Some(Field(index))
        } else {
            None
        }
    }

    fn reset_field(&mut self, key: CacheKey, wall_extra: f64) -> Field {
        let index = if let Some(&index) = self.cache_indices.get(&key) {
            index
        } else {
            let index = self.cache.len();
            let entry = self.spare_fields.pop().unwrap_or_else(|| CachedField {
                key,
                version: self.version,
                distances: vec![INF; self.n * self.n],
                frontier: Frontier::new(),
                wall_extra: 0.0,
            });
            self.cache_indices.insert(key, index);
            self.cache.push(entry);
            index
        };
        let entry = &mut self.cache[index];
        entry.key = key;
        entry.version = self.version;
        entry.distances.fill(INF);
        entry.frontier.clear();
        // pathing.py:220,233,254: wall_extra is converted to float32 at entry.
        entry.wall_extra = f64::from(wall_extra as f32);
        Field(index)
    }

    fn ensure(&mut self, field: Field, cell: usize) {
        let entry = &mut self.cache[field.0];
        debug_assert_eq!(entry.version, self.version);
        // Drain equal keys too: afterwards this cell and all lower values are
        // final, even if the cell started with an INF upper bound.
        while let Some(&Reverse((key, _))) = entry.frontier.peek() {
            if f32::from_bits(key) > entry.distances[cell] {
                break;
            }
            let _ = entry.expand(&self.blocked, &self.wall, &self.neighbors);
        }
    }
}

impl CachedField {
    fn seed(&mut self, cell: usize) {
        self.distances[cell] = 0.0;
        self.frontier.push(Reverse((0.0_f32.to_bits(), cell)));
    }

    fn expand(
        &mut self,
        blocked: &[bool],
        wall: &[bool],
        neighbor_indices: &[[usize; 8]],
    ) -> Option<(f32, usize)> {
        let Reverse((key, index)) = self.frontier.pop()?;
        let distance = f32::from_bits(key);
        // pathing.py:85-88: discard superseded queue entries.
        if distance > self.distances[index] {
            return None;
        }
        let diagonal = 2.0_f64.sqrt() / RES as f64;
        // pathing.py:100-104: compute each step-plus-wall cost once per pop.
        let mut straight_cost = 0.5;
        let mut diagonal_cost = diagonal;
        if wall[index] {
            straight_cost += self.wall_extra;
            diagonal_cost += self.wall_extra;
        }
        let neighbors = &neighbor_indices[index];
        for (q, &next) in neighbors.iter().enumerate() {
            if next == NO_NEIGHBOR || blocked[next] {
                continue;
            }
            if q >= 4 {
                // pathing.py:96-99: a valid diagonal has both cardinal neighbors.
                let (along_y, along_x) = DIAGONAL_CORNERS[q - 4];
                if blocked[neighbors[along_y]] || blocked[neighbors[along_x]] {
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
            if candidate < f64::from(self.distances[next]) {
                let rounded = candidate as f32;
                self.distances[next] = rounded;
                self.frontier.push(Reverse((rounded.to_bits(), next)));
            }
        }
        Some((distance, index))
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

fn for_each_goal_cell(
    n: usize,
    cx: f64,
    cy: f64,
    half: f64,
    reach: f64,
    mut visit: impl FnMut(usize),
) {
    let (lo_i, hi_i) = goal_bounds(n, cx, half, reach);
    let (lo_j, hi_j) = goal_bounds(n, cy, half, reach);
    // pathing.py:121-141,145-169: identical bounds and float64 square test.
    for i in lo_i..=hi_i {
        let px = (i as f64 + 0.5) / 2.0;
        let dx = ((px - cx).abs() - half).max(0.0);
        for j in lo_j..=hi_j {
            let py = (j as f64 + 0.5) / 2.0;
            let dy = ((py - cy).abs() - half).max(0.0);
            if dx * dx + dy * dy <= reach * reach {
                visit(i as usize * n + j as usize);
            }
        }
    }
}
