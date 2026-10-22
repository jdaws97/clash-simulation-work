use crate::fast_hash::FastMap as HashMap;
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
const NO_NEIGHBOR: u32 = u32::MAX;
const BLOCKED: u8 = 1;
const WALL: u8 = 2;
// pathing.py:96-99: check [ci, nj] before [ni, cj] for each diagonal.
const DIAGONAL_CORNERS: [(usize, usize); 4] = [(2, 0), (3, 0), (2, 1), (3, 1)];

// Cache indices remain valid until the next prune.
#[derive(Clone, Copy)]
pub struct Field(usize);

// Nonnegative, non-NaN f32 keys have the same order as their bits. Dijkstra
// pushes keys >= the last pop, including after rounding a candidate to f32.
// Equal-key pop order does not change the field: relaxation is monotone, and
// lazy queries drain all equal keys before using a settled distance.
struct Frontier {
    buckets: [Vec<(u32, u32)>; 33],
    occupied: u64,
    last: u32,
}

impl Frontier {
    fn new() -> Self {
        Self {
            buckets: std::array::from_fn(|_| Vec::new()),
            occupied: 0,
            last: 0,
        }
    }

    fn clear(&mut self) {
        for bucket in &mut self.buckets {
            bucket.clear();
        }
        self.occupied = 0;
        self.last = 0;
    }

    fn push(&mut self, key: u32, cell: u32) {
        debug_assert!(key >= self.last);
        let bucket = (u32::BITS - (key ^ self.last).leading_zeros()) as usize;
        self.buckets[bucket].push((key, cell));
        self.occupied |= 1_u64 << bucket;
    }

    fn rebase(&mut self, minimum: u32) {
        if minimum >= self.last {
            return;
        }
        // Repair can seed distances below the last pop. Keep all unfinished
        // work, but rebuild its buckets against the lower monotone base.
        let count = self.buckets.iter().map(Vec::len).sum();
        let mut entries = Vec::with_capacity(count);
        for bucket in &mut self.buckets {
            entries.append(bucket);
        }
        self.occupied = 0;
        self.last = minimum;
        for (key, cell) in entries {
            self.push(key, cell);
        }
    }

    fn min_key(&mut self) -> Option<u32> {
        if self.occupied == 0 {
            return None;
        }
        if self.occupied & 1 == 0 {
            self.redistribute();
        }
        Some(self.last)
    }

    fn redistribute(&mut self) {
        let bucket = self.occupied.trailing_zeros() as usize;
        let mut entries = std::mem::take(&mut self.buckets[bucket]);
        self.last = entries
            .iter()
            .map(|&(key, _)| key)
            .min()
            .expect("occupied bucket");
        self.occupied &= !(1_u64 << bucket);
        // Every entry moves to a strictly lower bucket; retain this bucket's
        // allocation for later redistributions and field reuse.
        for (key, cell) in entries.drain(..) {
            self.push(key, cell);
        }
        self.buckets[bucket] = entries;
    }

    fn pop(&mut self) -> Option<(u32, u32)> {
        self.min_key()?;
        let entry = self.buckets[0].pop();
        if self.buckets[0].is_empty() {
            self.occupied &= !1;
        }
        entry
    }
}

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub enum TargetIdentity {
    Building(usize),
    Wall(i32, i32),
    // battle.py:1609: unit identity is tagged to avoid building-id collisions.
    Unit(usize),
    // units.py:225: rubble paths have their own cache identity.
    Rubble(usize),
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

impl CacheKey {
    fn target(
        identity: TargetIdentity,
        cx: f64,
        cy: f64,
        reach: f64,
        wall_extra: f64,
    ) -> Self {
        Self::Target {
            identity,
            x: float_key(cx),
            y: float_key(cy),
            reach: float_key(reach),
            wall_extra: float_key(wall_extra),
        }
    }
}

struct CachedField {
    key: CacheKey,
    version: u64,
    // Rubble entries use only key/version and rubble_components; they neither
    // initialize nor expand distance storage, which may be reused after prune.
    distances: Vec<f32>,
    frontier: Frontier,
    wall_extra: f64,
    rubble_components: Vec<u32>,
    // Include blocked goals: a later removal may free a zero-distance seed.
    goals: Vec<usize>,
    goal_half: u64,
}

struct Change {
    version: u64,
    decrease_only: bool,
    i0: usize,
    i1: usize,
    j0: usize,
    j1: usize,
}

struct GoalSpan {
    start: usize,
    end: usize,
}

pub struct Grid {
    pub n: usize,
    // Flat arrays are indexed x * n + y, matching NumPy's [x, y] layout.
    pub blocked: Vec<bool>,
    pub wall: Vec<bool>,
    pub version: u64,
    cache: Vec<CachedField>,
    cache_indices: HashMap<CacheKey, usize>,
    neighbors: Vec<[u32; 8]>,
    cell_flags: Vec<u8>,
    move_masks: Vec<u8>,
    topology_version: Option<u64>,
    changes: Vec<Change>,
    connectivity: Connectivity,
    spare_fields: Vec<CachedField>,
    cell_marks: Vec<u32>,
    mark_generation: u32,
    repair_cells: Vec<usize>,
    // Goal geometry is independent of obstacles and survives field pruning.
    building_goals: Vec<Vec<GoalSpan>>,
    building_goal_indices: HashMap<(u64, u64, u64, u64), usize>,
    pool_goals: Vec<usize>,
    building_costs: Vec<f32>,
}

impl Grid {
    pub fn new(world_tiles: usize) -> Self {
        let n = world_tiles * RES;
        assert!(n > 0, "grid must have at least one cell");
        assert!(n * n < u32::MAX as usize, "grid indices must fit in u32");
        Self {
            n,
            blocked: vec![false; n * n],
            wall: vec![false; n * n],
            version: 0,
            cache: Vec::new(),
            cache_indices: HashMap::default(),
            neighbors: neighbor_indices(n),
            cell_flags: vec![0; n * n],
            move_masks: vec![0; n * n],
            topology_version: None,
            changes: Vec::new(),
            connectivity: Connectivity::new(),
            spare_fields: Vec::new(),
            cell_marks: vec![0; n * n],
            mark_generation: 0,
            repair_cells: Vec::new(),
            building_goals: Vec::new(),
            building_goal_indices: HashMap::default(),
            pool_goals: Vec::new(),
            building_costs: Vec::new(),
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
        // pathing.py:185-187,197-199: even an unchanged write versions the grid.
        self.changed(lo_i, hi_i, lo_j, hi_j, !present);
    }

    fn changed(&mut self, i0: isize, i1: isize, j0: isize, j1: isize, decrease_only: bool) {
        self.version += 1;
        // pathing.py:185-187: one cell around the write also covers diagonal
        // edges whose corner test changes. Retain NumPy's slice bounds.
        self.changes.push(Change {
            version: self.version,
            decrease_only,
            i0: slice_bound((i0 - 1).max(0), self.n),
            i1: slice_bound((i1 + 1).min(self.n as isize), self.n),
            j0: slice_bound((j0 - 1).max(0), self.n),
            j1: slice_bound((j1 + 1).min(self.n as isize), self.n),
        });
    }

    // pathing.py:272-275: truncate before clamping, rather than rounding.
    pub fn cell(&self, x: f64, y: f64) -> (usize, usize) {
        let i = ((x * RES as f64) as isize).clamp(0, self.n as isize - 1);
        let j = ((y * RES as f64) as isize).clamp(0, self.n as isize - 1);
        (i as usize, j as usize)
    }

    fn refresh_topology(&mut self) {
        if self.topology_version == Some(self.version) {
            return;
        }
        // Public blocked/wall arrays are also copied into newly created Jump
        // grids. Derive these packed arrays lazily, once per grid version.
        for (cell, flags) in self.cell_flags.iter_mut().enumerate() {
            *flags = u8::from(self.blocked[cell]) * BLOCKED | u8::from(self.wall[cell]) * WALL;
        }
        for (cell, neighbors) in self.neighbors.iter().enumerate() {
            let mut mask = 0;
            for (q, &next) in neighbors.iter().enumerate() {
                if next == NO_NEIGHBOR || self.cell_flags[next as usize] & BLOCKED != 0 {
                    continue;
                }
                if q >= 4 {
                    // A valid diagonal has both cardinal neighbors. Walls
                    // never block corners; only building hitboxes do.
                    let (along_y, along_x) = DIAGONAL_CORNERS[q - 4];
                    if self.cell_flags[neighbors[along_y] as usize] & BLOCKED != 0
                        || self.cell_flags[neighbors[along_x] as usize] & BLOCKED != 0
                    {
                        continue;
                    }
                }
                mask |= 1_u8 << q;
            }
            self.move_masks[cell] = mask;
        }
        self.topology_version = Some(self.version);
    }

    // With wall_extra=inf, only non-wall cells can relax a neighbor. Hence
    // finite cells are exactly: unblocked seeds; non-wall components containing
    // a non-wall seed; and unblocked walls adjacent by an allowed move to such
    // a component. A wall seed cannot propagate, and blocked cells never seed
    // or receive relaxation. The corner rule is symmetric, so the same move
    // masks serve component labelling and wall queries. Battle grids are far
    // too small for a finite simple path to reach the 1e9 distance sentinel.
    // Each Grid owns its labels, so Jump grids retain independent topology.
    pub fn rubble_reachable(
        &mut self,
        building: usize,
        cx: f64,
        cy: f64,
        half: f64,
        reach: f64,
        x: f64,
        y: f64,
    ) -> bool {
        self.refresh_topology();
        self.connectivity.ensure(
            self.version,
            &self.cell_flags,
            &self.move_masks,
            &self.neighbors,
        );
        let key = CacheKey::target(
            TargetIdentity::Rubble(building),
            cx,
            cy,
            reach,
            f64::INFINITY,
        );
        let (field, inserted) = self.cache_entry(key, f64::INFINITY);
        if inserted || self.cache[field.0].version != self.version {
            // Preserve the original field's cache insertion order and version
            // even for a blocked query cell. Pruning can evict source fields,
            // changing which half-cell is first reused for a tile. These
            // entries carry seed labels without allocating a distance field.
            let entry = &mut self.cache[field.0];
            entry.version = self.version;
            entry.rubble_components.clear();
            let labels = &self.connectivity.labels;
            let components = &mut entry.rubble_components;
            for_each_goal_cell(self.n, cx, cy, half, reach, |cell| {
                let label = labels[cell];
                if label != NO_COMPONENT && !components.contains(&label) {
                    components.push(label);
                }
            });
        }
        let (i, j) = self.cell(x, y);
        let cell = self.index(i, j);
        if self.cell_flags[cell] & BLOCKED != 0 {
            return false;
        }
        if is_goal_cell(self.n, i, j, cx, cy, half, reach) {
            return true;
        }
        let components = &self.cache[field.0].rubble_components;
        let labels = &self.connectivity.labels;
        if self.cell_flags[cell] & WALL == 0 {
            return components.contains(&labels[cell]);
        }
        let mut moves = self.move_masks[cell];
        while moves != 0 {
            let q = moves.trailing_zeros() as usize;
            moves &= moves - 1;
            let next = self.neighbors[cell][q] as usize;
            let label = labels[next];
            if label != NO_COMPONENT && components.contains(&label) {
                return true;
            }
        }
        false
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
        // Wall cost separates normal and ignore fields (fly bypasses fields).
        let key = CacheKey::target(identity, cx, cy, reach, wall_extra);
        let (field, inserted) = self.cache_entry(key, wall_extra);
        if !inserted && self.cache[field.0].version == self.version {
            return field;
        }
        self.refresh_topology();
        let entry = &mut self.cache[field.0];
        let mut same_goals = !inserted;
        if inserted || entry.goal_half != float_key(half) {
            let mut goals = Vec::new();
            for_each_goal_cell(self.n, cx, cy, half, reach, |cell| goals.push(cell));
            same_goals = !inserted && entry.goals == goals;
            entry.goals = goals;
            entry.goal_half = float_key(half);
        }
        // Geometry is cached with the key, separately from obstacle versions.
        // Half is not in Python's key: on stale hits compare the actual mask
        // if it changed, while same-version hits above still reuse verbatim.
        if !same_goals || !self.repair_field(field) {
            self.restart_field(field);
        }
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
        let (field, inserted) = self.cache_entry(key, wall_extra);
        if !inserted && self.cache[field.0].version == self.version {
            return field;
        }
        self.refresh_topology();
        let cell = self.index(i, j);
        let same_source = !inserted && self.cache[field.0].goals.first() == Some(&cell);
        // A different half-cell in the same tile can reuse only a current
        // version. Stale entries repair only for the original source cell.
        if !same_source {
            let goals = &mut self.cache[field.0].goals;
            goals.clear();
            goals.push(cell);
        }
        if !same_source || !self.repair_field(field) {
            self.restart_field(field);
        }
        field
    }

    pub fn building_costs(
        &mut self,
        x: f64,
        y: f64,
        wall_extra: f64,
        geometry: &[(f64, f64, f64)],
        reach: f64,
    ) -> &[f32] {
        self.pool_goals.clear();
        for &(cx, cy, half) in geometry {
            let key = (
                cx.to_bits(),
                cy.to_bits(),
                half.to_bits(),
                reach.to_bits(),
            );
            let index = if let Some(&index) = self.building_goal_indices.get(&key) {
                index
            } else {
                let mut goals: Vec<GoalSpan> = Vec::new();
                // Use exactly the original bounding box, cell order and f64
                // test. Adjacent goal cells form spans, so later scans read
                // contiguous distance slices without per-cell index gathers.
                for_each_goal_cell(self.n, cx, cy, half, reach, |cell| {
                    if let Some(span) = goals.last_mut() {
                        if span.end == cell {
                            span.end += 1;
                            return;
                        }
                    }
                    goals.push(GoalSpan {
                        start: cell,
                        end: cell + 1,
                    });
                });
                let index = self.building_goals.len();
                self.building_goals.push(goals);
                self.building_goal_indices.insert(key, index);
                index
            };
            self.pool_goals.push(index);
        }
        let field = self.source_field(x, y, wall_extra);
        let generation = self.next_mark_generation();
        let entry = &mut self.cache[field.0];
        let goal_marks = &mut self.cell_marks;
        // Start from every goal cell's stored value: each is an upper bound
        // on its distance. (Only counting values below the frontier minimum
        // was wrong once repairs exist: a repair can lower the frontier below
        // cells that are already final, and those were then never counted.)
        let mut best = INF;
        for &index in &self.pool_goals {
            for span in &self.building_goals[index] {
                goal_marks[span.start..span.end].fill(generation);
                for &distance in &entry.distances[span.start..span.end] {
                    if distance < best {
                        best = distance;
                    }
                }
            }
        }
        while let Some(key) = entry.frontier.min_key() {
            if f32::from_bits(key) > best {
                break;
            }
            if let Some((distance, cell)) =
                entry.expand(&self.cell_flags, &self.move_masks, &self.neighbors)
            {
                if goal_marks[cell] == generation && distance < best {
                    best = distance;
                }
            }
        }

        // Once the frontier minimum exceeds best, the goal cell holding best
        // is final (its stored value is below the frontier), and any goal
        // cell truly closer would also be below the frontier, hence final
        // and counted above or when popped. So every value <= best is final.
        // Larger stored upper bounds cannot change the first argmin or its
        // >= 1e8 fallback (pathing.py:145-169; battle.py:1432-1441).
        let distances = &entry.distances;
        self.building_costs.clear();
        let nearest = best;
        for &index in &self.pool_goals {
            let mut best = INF;
            'goals: for span in &self.building_goals[index] {
                for &distance in &distances[span.start..span.end] {
                    if distance < best {
                        best = distance;
                        // The global minimum is settled, so no remaining
                        // stored upper bound can improve on it.
                        if best == nearest {
                            break 'goals;
                        }
                    }
                }
            }
            self.building_costs.push(best);
        }
        &self.building_costs
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
        let mut best_cell = cell;
        // pathing.py:287-297: choose the lowest stored distance, retaining the
        // earlier neighbor on ties. Do not check obstacles or corner cutting.
        // Unsettled neighbors have stored values >= here and cannot be chosen.
        for &next in &self.neighbors[cell] {
            if next == NO_NEIGHBOR {
                continue;
            }
            let next = next as usize;
            let distance = distances[next];
            if distance < best {
                best = distance;
                best_cell = next;
            }
        }
        if best_cell == cell {
            return NextStep {
                x,
                y,
                is_wall: false,
                at_goal: here >= INF,
            };
        }
        let (bi, bj) = (best_cell / self.n, best_cell % self.n);
        NextStep {
            x: (bi as f64 + 0.5) / RES as f64,
            y: (bj as f64 + 0.5) / RES as f64,
            is_wall: self.cell_flags[best_cell] & WALL != 0,
            at_goal: false,
        }
    }

    pub fn prune(&mut self) {
        // pathing.py:261-267: preserve dictionary insertion order, including
        // stale keys. A stable version sort chooses the same retained fields
        // on ties. Evicting a live source key can change the first half-cell
        // reused for that tile, so this is observable simulation state.
        if self.cache.len() > 600 {
            self.cache.sort_by(|first, second| second.version.cmp(&first.version));
            for mut entry in self.cache.drain(400..) {
                entry.frontier.clear();
                self.spare_fields.push(entry);
            }
            self.spare_fields.truncate(400);
            self.cache_indices.clear();
            for (index, entry) in self.cache.iter().enumerate() {
                self.cache_indices.insert(entry.key, index);
            }
        }
        if let Some(oldest) = self.cache.iter().map(|entry| entry.version).min() {
            let obsolete = self.changes.partition_point(|change| change.version <= oldest);
            drop(self.changes.drain(..obsolete));
        }
    }

    fn next_mark_generation(&mut self) -> u32 {
        self.mark_generation = self.mark_generation.wrapping_add(1);
        if self.mark_generation == 0 {
            self.cell_marks.fill(0);
            self.mark_generation = 1;
        }
        self.mark_generation
    }

    fn restart_field(&mut self, field: Field) {
        let entry = &mut self.cache[field.0];
        entry.version = self.version;
        entry.frontier.clear();
        entry.distances.resize(self.n * self.n, INF);
        entry.distances.fill(INF);
        // pathing.py:28-35: only unblocked goals seed a restarted field.
        for &cell in &entry.goals {
            if !self.blocked[cell] {
                entry.distances[cell] = 0.0;
                entry.frontier.push(0.0_f32.to_bits(), cell as u32);
            }
        }
    }

    fn cache_entry(&mut self, key: CacheKey, wall_extra: f64) -> (Field, bool) {
        // One lookup serves current hits, stale repair, and restart alike.
        if let Some(&index) = self.cache_indices.get(&key) {
            return (Field(index), false);
        }
        let index = self.cache.len();
        let mut entry = self.spare_fields.pop().unwrap_or_else(|| CachedField {
            key,
            version: self.version,
            distances: Vec::new(),
            frontier: Frontier::new(),
            wall_extra: 0.0,
            rubble_components: Vec::new(),
            goals: Vec::new(),
            goal_half: 0,
        });
        entry.key = key;
        entry.version = self.version;
        entry.frontier.clear();
        entry.rubble_components.clear();
        entry.goals.clear();
        // pathing.py:220,233,254: wall_extra is converted to float32 at entry.
        entry.wall_extra = f64::from(wall_extra as f32);
        self.cache_indices.insert(key, index);
        self.cache.push(entry);
        (Field(index), true)
    }

    fn repair_field(&mut self, field: Field) -> bool {
        let version = self.cache[field.0].version;
        debug_assert!(version < self.version);
        let first = self.changes.partition_point(|change| change.version <= version);
        if self.changes.get(first).map(|change| change.version) != Some(version + 1)
            || self.changes[first..].iter().any(|change| !change.decrease_only)
        {
            return false;
        }
        let generation = self.next_mark_generation();
        self.repair_cells.clear();
        for change in &self.changes[first..] {
            for i in change.i0..change.i1 {
                for j in change.j0..change.j1 {
                    let cell = i * self.n + j;
                    if self.cell_marks[cell] != generation {
                        self.cell_marks[cell] = generation;
                        self.repair_cells.push(cell);
                    }
                }
            }
        }
        let entry = &mut self.cache[field.0];
        for &cell in &entry.goals {
            // pathing.py:216-220: freed targets AND freed source cells must
            // become goals again, including fields previously all-INF.
            if self.cell_marks[cell] == generation && !self.blocked[cell] {
                entry.distances[cell] = 0.0;
            }
        }
        let mut minimum = entry.frontier.last;
        for &cell in &self.repair_cells {
            if !self.blocked[cell] && entry.distances[cell] < INF {
                minimum = minimum.min(entry.distances[cell].to_bits());
            }
        }
        entry.frontier.rebase(minimum);
        for &cell in &self.repair_cells {
            let distance = entry.distances[cell];
            if !self.blocked[cell] && distance < INF {
                entry.frontier.push(distance.to_bits(), cell as u32);
            }
        }
        // Removing obstacles preserves every stored upper bound. Any newly
        // cheaper path first crosses a changed edge inside an expanded
        // rectangle: its predecessor is either seeded at its stored value,
        // or will be reached by the retained unfinished frontier. Freed goals
        // supply any new zero-distance starts. Thus every possible improvement
        // is queued, and again every stored value strictly below the frontier
        // minimum is final. Positive costs and monotone f32 rounding give the
        // same unique fixed point regardless of equal-key pop order (as for
        // a fresh field). ensure drains through the queried distance, so both
        // it and every smaller neighbor match a full repair exactly. Keeping
        // the old frontier is essential: lazy fields are only partly expanded.
        entry.version = self.version;
        true
    }

    fn ensure(&mut self, field: Field, cell: usize) {
        let entry = &mut self.cache[field.0];
        debug_assert_eq!(entry.version, self.version);
        // Drain equal keys too: afterwards this cell and all lower values are
        // final, even if the cell started with an INF upper bound.
        while let Some(key) = entry.frontier.min_key() {
            if f32::from_bits(key) > entry.distances[cell] {
                break;
            }
            let _ = entry.expand(&self.cell_flags, &self.move_masks, &self.neighbors);
        }
    }
}

impl CachedField {
    fn expand(
        &mut self,
        cell_flags: &[u8],
        move_masks: &[u8],
        neighbor_indices: &[[u32; 8]],
    ) -> Option<(f32, usize)> {
        let (key, index) = self.frontier.pop()?;
        let index = index as usize;
        let distance = f32::from_bits(key);
        // pathing.py:85-88: discard superseded queue entries.
        if distance > self.distances[index] {
            return None;
        }
        let diagonal = 2.0_f64.sqrt() / RES as f64;
        // pathing.py:100-104: compute each step-plus-wall cost once per pop.
        let mut straight_cost = 0.5;
        let mut diagonal_cost = diagonal;
        if cell_flags[index] & WALL != 0 {
            straight_cost += self.wall_extra;
            diagonal_cost += self.wall_extra;
        }
        let neighbors = &neighbor_indices[index];
        let mut moves = move_masks[index];
        while moves != 0 {
            let q = moves.trailing_zeros() as usize;
            moves &= moves - 1;
            let next = neighbors[q] as usize;
            // pathing.py:100-109: charge the current cell's wall, and add
            // that cost to the step before adding the popped f32 distance.
            let cost = if q < 4 {
                straight_cost
            } else {
                diagonal_cost
            };
            let candidate: f64 = f64::from(distance) + cost;
            // Compare in f64 BEFORE either the distance or heap key is
            // rounded to f32. Even an equal rounded value is pushed.
            if candidate < f64::from(self.distances[next]) {
                let rounded = candidate as f32;
                self.distances[next] = rounded;
                self.frontier.push(rounded.to_bits(), next as u32);
            }
        }
        Some((distance, index))
    }
}

// Reachability with infinite wall cost; no distance fields are stored here.
const NO_COMPONENT: u32 = u32::MAX;

struct Connectivity {
    version: Option<u64>,
    labels: Vec<u32>,
    pending: Vec<u32>,
}

impl Connectivity {
    fn new() -> Self {
        Self {
            version: None,
            labels: Vec::new(),
            pending: Vec::new(),
        }
    }

    fn ensure(
        &mut self,
        version: u64,
        cell_flags: &[u8],
        move_masks: &[u8],
        neighbors: &[[u32; 8]],
    ) {
        if self.version == Some(version) {
            return;
        }
        self.labels.resize(cell_flags.len(), NO_COMPONENT);
        self.labels.fill(NO_COMPONENT);
        self.pending.clear();
        let mut label = 0_u32;
        for cell in 0..cell_flags.len() {
            if cell_flags[cell] != 0 || self.labels[cell] != NO_COMPONENT {
                continue;
            }
            self.labels[cell] = label;
            self.pending.push(cell as u32);
            while let Some(current) = self.pending.pop() {
                let current = current as usize;
                let mut moves = move_masks[current];
                while moves != 0 {
                    let q = moves.trailing_zeros() as usize;
                    moves &= moves - 1;
                    let next = neighbors[current][q] as usize;
                    if cell_flags[next] == 0 && self.labels[next] == NO_COMPONENT {
                        self.labels[next] = label;
                        self.pending.push(next as u32);
                    }
                }
            }
            label += 1;
        }
        self.version = Some(version);
    }
}

fn neighbor_indices(n: usize) -> Vec<[u32; 8]> {
    let mut neighbors = vec![[NO_NEIGHBOR; 8]; n * n];
    // pathing.py:89-99: precompute geometry without changing neighbor order.
    for i in 0..n {
        for j in 0..n {
            for (q, (di, dj)) in NEIGHBORS.iter().copied().enumerate() {
                let ni = i as isize + di;
                let nj = j as isize + dj;
                if ni >= 0 && nj >= 0 && ni < n as isize && nj < n as isize {
                    neighbors[i * n + j][q] = (ni as usize * n + nj as usize) as u32;
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

fn is_goal_cell(
    n: usize,
    i: usize,
    j: usize,
    cx: f64,
    cy: f64,
    half: f64,
    reach: f64,
) -> bool {
    let (lo_i, hi_i) = goal_bounds(n, cx, half, reach);
    let (lo_j, hi_j) = goal_bounds(n, cy, half, reach);
    if (i as isize) < lo_i
        || (i as isize) > hi_i
        || (j as isize) < lo_j
        || (j as isize) > hi_j
    {
        return false;
    }
    // Match for_each_goal_cell's bounds, cell centers and f64 operation order.
    let px = (i as f64 + 0.5) / 2.0;
    let py = (j as f64 + 0.5) / 2.0;
    let dx = ((px - cx).abs() - half).max(0.0);
    let dy = ((py - cy).abs() - half).max(0.0);
    dx * dx + dy * dy <= reach * reach
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
