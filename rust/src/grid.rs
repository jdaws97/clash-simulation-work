use std::collections::hash_map::Entry;

use crate::fast_hash::FastMap as HashMap;
use crate::field_profile::{self, GoalKey, Row, Span};
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
// Bound distance/frontier storage independently of Python's observable cache.
// At 100 x 100 cells, 64 distance arrays contain 2.44 MiB of f32 values.
const MAX_STORED_FIELDS: usize = 64;
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
    // units.py:139: ("breaker", building.id), without geometry or wall mode.
    Breaker(usize),
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
pub(crate) enum CacheKey {
    Breaker(usize),
    Rubble(usize, u64),
    Target {
        identity: TargetIdentity,
        x: u64,
        y: u64,
        reach: u64,
        wall_extra: u64,
    },
    Source {
        i: usize,
        j: usize,
        wall_extra: u64,
    },
}

impl CacheKey {
    fn profile_kind(self) -> &'static str {
        match self {
            Self::Breaker(_) => "wall_breaker",
            Self::Rubble(..) => "rubble_goal",
            Self::Source { .. } => "source",
            Self::Target { identity, .. } => match identity {
                TargetIdentity::Building(_) => "building_goal",
                TargetIdentity::Wall(..) => "wall_goal",
                TargetIdentity::Unit(_) => "unit_chase",
                TargetIdentity::Breaker(_) => "wall_breaker",
                TargetIdentity::Rubble(_) => "rubble_goal",
            },
        }
    }

    fn target(identity: TargetIdentity, cx: f64, cy: f64, reach: f64, wall_extra: f64) -> Self {
        // These callers pass their complete Python key, unlike movement's
        // (identity, x, y, reach, mode).
        match identity {
            TargetIdentity::Breaker(building) => return Self::Breaker(building),
            TargetIdentity::Rubble(building) => return Self::Rubble(building, float_key(reach)),
            _ => {}
        }
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
    // Storage eviction leaves this metadata, its version and its goals intact.
    // Rubble entries keep seed geometry/components, without a storage slot.
    storage: Option<usize>,
    wall_extra: f64,
    rubble_components: Vec<u32>,
    // Include blocked goals: a later removal may free a zero-distance seed.
    goals: Vec<usize>,
    goal_geometry: (u64, u64, u64, u64),
}

struct FieldStorage {
    // Cache indices move only at prune, which updates the surviving owners.
    owner: Option<usize>,
    previous: Option<usize>,
    next: Option<usize>,
    distances: Vec<f32>,
    frontier: Frontier,
    wall_extra: f64,
    forward: bool,
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
    profile_enabled: bool,
    profile_initial_version: Option<u64>,
    cache: Vec<CachedField>,
    cache_indices: HashMap<CacheKey, usize>,
    neighbors: Vec<[u32; 8]>,
    cell_flags: Vec<u8>,
    move_masks: Vec<u8>,
    topology_version: Option<u64>,
    changes: Vec<Change>,
    connectivity: Connectivity,
    field_storage: Vec<FieldStorage>,
    oldest_storage: Option<usize>,
    newest_storage: Option<usize>,
    free_storage: Vec<usize>,
    cell_marks: Vec<u32>,
    mark_generation: u32,
    repair_cells: Vec<usize>,
    // Goal geometry is independent of obstacles and survives field pruning.
    building_goals: Vec<Vec<GoalSpan>>,
    building_goal_indices: HashMap<(u64, u64, u64, u64), usize>,
    pool_goals: Vec<usize>,
    pool_geometry: Vec<(f64, f64, f64)>,
    pool_reach: Option<u64>,
    pool_spans: Vec<GoalSpan>,
    pool_goal_mask: Vec<bool>,
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
            profile_enabled: field_profile::enabled(),
            profile_initial_version: None,
            cache: Vec::new(),
            cache_indices: HashMap::default(),
            neighbors: neighbor_indices(n),
            cell_flags: vec![0; n * n],
            move_masks: vec![0; n * n],
            topology_version: None,
            changes: Vec::new(),
            connectivity: Connectivity::new(),
            field_storage: Vec::new(),
            oldest_storage: None,
            newest_storage: None,
            free_storage: Vec::new(),
            cell_marks: vec![0; n * n],
            mark_generation: 0,
            repair_cells: Vec::new(),
            building_goals: Vec::new(),
            building_goal_indices: HashMap::default(),
            pool_goals: Vec::new(),
            pool_geometry: Vec::new(),
            pool_reach: None,
            pool_spans: Vec::new(),
            pool_goal_mask: Vec::new(),
            building_costs: Vec::new(),
        }
    }

    // Called after all starting buildings/walls are installed, before opening
    // plan queries. Jump views are independent grids and never marked initial.
    pub fn profile_initial_state(&mut self) {
        if self.profile_enabled {
            self.profile_initial_version = Some(self.version);
        }
    }

    fn profile_row(&self, kind: &'static str) -> Row {
        Row {
            kind,
            source: if self.profile_initial_version.is_some() {
                "main"
            } else {
                "jump"
            },
            initial: self.profile_initial_version == Some(self.version),
        }
    }

    fn profile_span(&self, kind: &'static str) -> Option<Span> {
        if self.profile_enabled {
            Span::start(self.profile_row(kind))
        } else {
            None
        }
    }

    fn profile_field_span(&self, field: Field) -> Option<Span> {
        if self.profile_enabled {
            Span::start(self.profile_row(self.cache[field.0].key.profile_kind()))
        } else {
            None
        }
    }

    fn profile_build(
        &self,
        kind: &'static str,
        cache: Option<CacheKey>,
        geometry: (u64, u64, u64, u64),
        wall_extra: u64,
    ) {
        if self.profile_enabled {
            field_profile::build(
                self.profile_row(kind),
                self.profile_initial_version,
                GoalKey {
                    cache,
                    geometry,
                    wall_extra,
                },
            );
        }
    }

    fn profile_field_build(&self, field: Field) {
        if self.profile_enabled {
            let entry = &self.cache[field.0];
            self.profile_build(
                entry.key.profile_kind(),
                Some(entry.key),
                entry.goal_geometry,
                entry.wall_extra.to_bits(),
            );
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
        let _profile = self.profile_span("topology");
        // Each change rectangle already reaches one cell past the write, which
        // covers every move mask whose corner test reads a rewritten flag. Use
        // the rectangles when the log holds every version since the last pass.
        if let Some(done) = self.topology_version {
            let first = self
                .changes
                .partition_point(|change| change.version <= done);
            let complete = self.changes.get(first).map(|change| change.version) == Some(done + 1)
                && self.changes.last().map(|change| change.version) == Some(self.version);
            if complete {
                let rects: Vec<_> = self.changes[first..]
                    .iter()
                    .map(|c| (c.i0, c.i1, c.j0, c.j1))
                    .collect();
                for &(i0, i1, j0, j1) in &rects {
                    for i in i0..i1 {
                        for j in j0..j1 {
                            let cell = self.index(i, j);
                            self.cell_flags[cell] = u8::from(self.blocked[cell]) * BLOCKED
                                | u8::from(self.wall[cell]) * WALL;
                        }
                    }
                }
                for &(i0, i1, j0, j1) in &rects {
                    for i in i0..i1 {
                        for j in j0..j1 {
                            let cell = self.index(i, j);
                            self.move_masks[cell] = self.move_mask(cell);
                        }
                    }
                }
                self.topology_version = Some(self.version);
                self.profile_build("topology", None, (0, 0, 0, 0), 0);
                return;
            }
        }
        // Public blocked/wall arrays are also copied into newly created Jump
        // grids. Derive these packed arrays lazily, once per grid version.
        for (cell, flags) in self.cell_flags.iter_mut().enumerate() {
            *flags = u8::from(self.blocked[cell]) * BLOCKED | u8::from(self.wall[cell]) * WALL;
        }
        for cell in 0..self.neighbors.len() {
            self.move_masks[cell] = self.move_mask(cell);
        }
        self.topology_version = Some(self.version);
        self.profile_build("topology", None, (0, 0, 0, 0), 0);
    }

    fn move_mask(&self, cell: usize) -> u8 {
        let neighbors = &self.neighbors[cell];
        {
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
            mask
        }
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
        let _profile = self.profile_span("rubble_goal");
        self.refresh_topology();
        if self.connectivity.version != Some(self.version) {
            let _profile = self.profile_span("rubble_connectivity");
            let pops = self.connectivity.ensure(
                self.version,
                &self.cell_flags,
                &self.move_masks,
                &self.neighbors,
                self.profile_enabled,
            );
            self.profile_build("rubble_connectivity", None, (0, 0, 0, 0), 0);
            if self.profile_enabled {
                field_profile::work(self.profile_row("rubble_connectivity"), pops, 0);
            }
        }
        let key = CacheKey::target(
            TargetIdentity::Rubble(building),
            cx,
            cy,
            reach,
            f64::INFINITY,
        );
        let (field, inserted) = self.cache_entry(key, f64::INFINITY);
        if inserted || self.cache[field.0].version != self.version {
            // Keep seed labels without allocating a distance field.
            let entry = &mut self.cache[field.0];
            entry.version = self.version;
            entry.goal_geometry = (cx.to_bits(), cy.to_bits(), half.to_bits(), reach.to_bits());
            entry.rubble_components.clear();
            let labels = &self.connectivity.labels;
            let components = &mut entry.rubble_components;
            for_each_goal_cell(self.n, cx, cy, half, reach, |cell| {
                let label = labels[cell];
                if label != NO_COMPONENT && !components.contains(&label) {
                    components.push(label);
                }
            });
            self.profile_field_build(field);
        }
        let (i, j) = self.cell(x, y);
        let cell = self.index(i, j);
        if self.cell_flags[cell] & BLOCKED != 0 {
            return false;
        }
        // A current Python key reuses its original goals even if the caller's
        // geometry changed. Rubble's key contains only building id and range.
        let (gx, gy, gh, gr) = self.cache[field.0].goal_geometry;
        if is_goal_cell(
            self.n,
            i,
            j,
            f64::from_bits(gx),
            f64::from_bits(gy),
            f64::from_bits(gh),
            f64::from_bits(gr),
        ) {
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
        let same_cost = self.cache[field.0].wall_extra == f64::from(wall_extra as f32);
        if !inserted && same_cost && self.cache[field.0].version == self.version {
            // Python's key can omit goal geometry: even after storage
            // eviction, reuse saved goals rather than the current geometry.
            self.use_field(field);
            return field;
        }
        let _profile = self.profile_field_span(field);
        self.refresh_topology();
        let entry = &mut self.cache[field.0];
        let mut same_goals = !inserted && same_cost;
        entry.wall_extra = f64::from(wall_extra as f32);
        let geometry = (cx.to_bits(), cy.to_bits(), half.to_bits(), reach.to_bits());
        if inserted || entry.goal_geometry != geometry {
            let mut goals = Vec::new();
            for_each_goal_cell(self.n, cx, cy, half, reach, |cell| goals.push(cell));
            same_goals = !inserted && same_cost && entry.goals == goals;
            entry.goals = goals;
            entry.goal_geometry = geometry;
        }
        // Geometry is cached with the key, separately from obstacle versions.
        // On stale hits compare actual masks if any geometry changed (half
        // for movement; all geometry for breaker). Current hits reuse verbatim.
        if !same_goals || !self.repair_field(field) {
            self.restart_field(field);
        }
        self.use_field(field);
        field
    }

    pub fn source_field(&mut self, x: f64, y: f64, wall_extra: f64) -> Field {
        let (i, j) = self.cell(x, y);
        let key = CacheKey::Source {
            i,
            j,
            wall_extra: float_key(wall_extra),
        };
        // pathing.py:248-261: each half-tile source has its own field.
        let (field, inserted) = self.cache_entry(key, wall_extra);
        if !inserted && self.cache[field.0].version == self.version {
            self.use_field(field);
            return field;
        }
        let _profile = self.profile_span("source");
        self.refresh_topology();
        let cell = self.index(i, j);
        if inserted {
            self.cache[field.0].goals.push(cell);
        }
        if inserted || !self.repair_field(field) {
            self.restart_field(field);
        }
        self.use_field(field);
        field
    }

    fn building_goal_index(&mut self, cx: f64, cy: f64, half: f64, reach: f64) -> usize {
        let key = (cx.to_bits(), cy.to_bits(), half.to_bits(), reach.to_bits());
        if let Some(&index) = self.building_goal_indices.get(&key) {
            return index;
        }
        let _profile = self.profile_span("goal_geometry");
        let mut goals: Vec<GoalSpan> = Vec::new();
        // Use exactly the original bounding box, cell order and f64 test.
        // Adjacent goal cells form spans for contiguous distance scans.
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
        self.profile_build("goal_geometry", None, key, 0);
        index
    }

    fn prepare_building_goals(&mut self, geometry: &[(f64, f64, f64)], reach: f64) {
        if self.pool_reach == Some(float_key(reach)) && self.pool_geometry.as_slice() == geometry {
            return;
        }
        let _profile = self.profile_span("goal_geometry");
        self.pool_geometry.clear();
        self.pool_geometry.extend_from_slice(geometry);
        self.pool_reach = Some(float_key(reach));
        self.pool_goals.clear();
        self.pool_spans.clear();
        if self.pool_goal_mask.is_empty() {
            self.pool_goal_mask.resize(self.n * self.n, false);
        } else {
            self.pool_goal_mask.fill(false);
        }
        for &(cx, cy, half) in geometry {
            let index = self.building_goal_index(cx, cy, half, reach);
            self.pool_goals.push(index);
            for span in &self.building_goals[index] {
                self.pool_goal_mask[span.start..span.end].fill(true);
            }
        }
        // Cache the union as well as each building's ordered goals. Only the
        // global minimum and membership use this union, so overlap/order has
        // no effect on costs or first-argmin ties. Repairs use separate marks.
        // Build runs in one grid scan rather than sorting all building spans.
        let mut start = 0;
        while start < self.pool_goal_mask.len() {
            if !self.pool_goal_mask[start] {
                start += 1;
                continue;
            }
            let mut end = start + 1;
            while end < self.pool_goal_mask.len() && self.pool_goal_mask[end] {
                end += 1;
            }
            self.pool_spans.push(GoalSpan { start, end });
            start = end;
        }
    }

    pub fn building_costs(
        &mut self,
        x: f64,
        y: f64,
        wall_extra: f64,
        geometry: &[(f64, f64, f64)],
        reach: f64,
    ) -> &[f32] {
        let _profile = self.profile_span("source");
        self.prepare_building_goals(geometry, reach);
        let field = self.source_field(x, y, wall_extra);
        let storage = self.cache[field.0].storage.expect("source field storage");
        let entry = &mut self.field_storage[storage];
        // Start from every goal cell's stored value: each is an upper bound
        // on its distance. (Only counting values below the frontier minimum
        // was wrong once repairs exist: a repair can lower the frontier below
        // cells that are already final, and those were then never counted.)
        let mut best = INF;
        for span in &self.pool_spans {
            for &distance in &entry.distances[span.start..span.end] {
                if distance < best {
                    best = distance;
                }
            }
        }
        // Specialize outside the loop: the disabled version has no pop counter.
        let pops = if self.profile_enabled {
            entry.expand_building_goals::<true>(
                &mut best,
                &self.pool_goal_mask,
                &self.cell_flags,
                &self.move_masks,
                &self.neighbors,
            )
        } else {
            entry.expand_building_goals::<false>(
                &mut best,
                &self.pool_goal_mask,
                &self.cell_flags,
                &self.move_masks,
                &self.neighbors,
            )
        };

        // Once the frontier minimum exceeds best, the goal cell holding best
        // is final (its stored value is below the frontier), and any goal
        // cell truly closer would also be below the frontier, hence final
        // and counted above or when popped. So every value <= best is final.
        // Larger stored upper bounds cannot change the minimum-cost ties or
        // the >= 1e8 fallback (pathing.py:145-169; battle.py:1519-1529).
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
        if self.profile_enabled {
            field_profile::work(self.profile_row("source"), pops, 0);
        }
        &self.building_costs
    }

    pub fn distance(&mut self, field: Field, cell: usize) -> f32 {
        let storage = self.ensure(field, cell);
        self.field_storage[storage].distances[cell]
    }

    pub fn next_step(&mut self, field: Field, x: f64, y: f64) -> NextStep {
        let (i, j) = self.cell(x, y);
        let cell = self.index(i, j);
        let storage = self.ensure(field, cell);
        let here = self.field_storage[storage].distances[cell];
        if here <= 0.0 {
            return NextStep {
                x,
                y,
                is_wall: false,
                at_goal: true,
            };
        }
        if self.blocked[cell] {
            return NextStep {
                x,
                y,
                is_wall: false,
                at_goal: here >= INF,
            };
        }
        // next_step now compares every legal neighbor's full entry cost.
        // Settle all of them: unlike descending raw distances, a wall can
        // make the winner's distance larger than the current cell's value.
        let mut moves = self.move_masks[cell];
        while moves != 0 {
            let q = moves.trailing_zeros() as usize;
            moves &= moves - 1;
            let next = self.neighbors[cell][q] as usize;
            self.ensure(field, next);
        }
        let distances = &self.field_storage[storage].distances;
        let wall_extra = self.cache[field.0].wall_extra;
        let mut best = f64::INFINITY;
        let mut best_cell = cell;
        // pathing.py:307-324: preserve neighbor order, f64 step arithmetic
        // and the relaxation's blocked/corner rules.
        let mut moves = self.move_masks[cell];
        while moves != 0 {
            let q = moves.trailing_zeros() as usize;
            moves &= moves - 1;
            let next = self.neighbors[cell][q] as usize;
            if distances[next] >= INF {
                continue;
            }
            let mut cost = if q < 4 {
                0.5
            } else {
                2.0_f64.sqrt() / RES as f64
            };
            if self.wall[next] {
                cost += wall_extra;
            }
            let distance = f64::from(distances[next]) + cost;
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
        // pathing.py:266-272: preserve stable version order when pruning.
        if self.cache.len() > 600 {
            self.cache
                .sort_by(|first, second| second.version.cmp(&first.version));
            while self.cache.len() > 400 {
                let entry = self.cache.pop().expect("cache beyond retention limit");
                if let Some(storage) = entry.storage {
                    self.unlink_storage(storage);
                    let slot = &mut self.field_storage[storage];
                    slot.owner = None;
                    slot.frontier.clear();
                    self.free_storage.push(storage);
                }
            }
            self.cache_indices.clear();
            for (index, entry) in self.cache.iter().enumerate() {
                self.cache_indices.insert(entry.key, index);
                if let Some(storage) = entry.storage {
                    self.field_storage[storage].owner = Some(index);
                }
            }
        }
        if let Some(oldest) = self.cache.iter().map(|entry| entry.version).min() {
            let obsolete = self
                .changes
                .partition_point(|change| change.version <= oldest);
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
        let _profile = self.profile_field_span(field);
        let storage = self.storage_slot(field);
        let entry = &mut self.cache[field.0];
        entry.version = self.version;
        let slot = &mut self.field_storage[storage];
        slot.wall_extra = entry.wall_extra;
        // pathing.py:269-281: source fields expand forward, including repairs.
        slot.forward = matches!(entry.key, CacheKey::Source { .. });
        slot.frontier.clear();
        // Keep contiguous building-goal scans and a sequential reset without
        // per-cell stamps or touched-cell lists. Initialize new arrays only
        // once rather than following resize with a second fill.
        if slot.distances.is_empty() {
            slot.distances.resize(self.n * self.n, INF);
        } else {
            slot.distances.fill(INF);
        }
        // pathing.py:28-35: only unblocked goals seed a restarted field.
        for &cell in &entry.goals {
            if !self.blocked[cell] {
                slot.distances[cell] = 0.0;
                slot.frontier.push(0.0_f32.to_bits(), cell as u32);
            }
        }
        self.profile_field_build(field);
    }

    fn storage_slot(&mut self, field: Field) -> usize {
        if let Some(storage) = self.cache[field.0].storage {
            return storage;
        }
        let storage = if let Some(free) = self.free_storage.pop() {
            free
        } else if self.field_storage.len() < MAX_STORED_FIELDS {
            let index = self.field_storage.len();
            self.field_storage.push(FieldStorage::new());
            index
        } else {
            // The linked LRU and free list move storage alone: no Python
            // key, version, goal or insertion order changes on eviction.
            let storage = self.oldest_storage.expect("nonempty field storage pool");
            self.unlink_storage(storage);
            storage
        };
        let slot = &mut self.field_storage[storage];
        if let Some(owner) = slot.owner {
            self.cache[owner].storage = None;
        }
        slot.owner = Some(field.0);
        self.cache[field.0].storage = Some(storage);
        storage
    }

    fn unlink_storage(&mut self, storage: usize) {
        let slot = &self.field_storage[storage];
        let (previous, next) = (slot.previous, slot.next);
        if let Some(previous) = previous {
            self.field_storage[previous].next = next;
        } else if self.oldest_storage == Some(storage) {
            self.oldest_storage = next;
        }
        if let Some(next) = next {
            self.field_storage[next].previous = previous;
        } else if self.newest_storage == Some(storage) {
            self.newest_storage = previous;
        }
        let slot = &mut self.field_storage[storage];
        slot.previous = None;
        slot.next = None;
    }

    fn touch_storage(&mut self, storage: usize) {
        if self.newest_storage == Some(storage) {
            return;
        }
        self.unlink_storage(storage);
        let previous = self.newest_storage;
        if let Some(previous) = previous {
            self.field_storage[previous].next = Some(storage);
        } else {
            self.oldest_storage = Some(storage);
        }
        self.field_storage[storage].previous = previous;
        self.newest_storage = Some(storage);
    }

    fn use_field(&mut self, field: Field) -> usize {
        if self.cache[field.0].storage.is_none() {
            // Rebuild evicted storage from the saved goals and wall cost.
            self.refresh_topology();
            self.restart_field(field);
        }
        let storage = self.cache[field.0].storage.expect("field storage");
        debug_assert_eq!(self.field_storage[storage].owner, Some(field.0));
        self.touch_storage(storage);
        storage
    }

    fn cache_entry(&mut self, key: CacheKey, wall_extra: f64) -> (Field, bool) {
        // One lookup serves current hits, stale repair, and restart alike.
        match self.cache_indices.entry(key) {
            Entry::Occupied(entry) => (Field(*entry.get()), false),
            Entry::Vacant(entry) => {
                let index = self.cache.len();
                entry.insert(index);
                self.cache.push(CachedField {
                    key,
                    version: self.version,
                    storage: None,
                    // pathing.py:220,233,254: round wall_extra to float32.
                    wall_extra: f64::from(wall_extra as f32),
                    rubble_components: Vec::new(),
                    goals: Vec::new(),
                    goal_geometry: (0, 0, 0, 0),
                });
                (Field(index), true)
            }
        }
    }

    fn repair_field(&mut self, field: Field) -> bool {
        let _profile = self.profile_field_span(field);
        let Some(storage) = self.cache[field.0].storage else {
            return false;
        };
        let version = self.cache[field.0].version;
        debug_assert!(version < self.version);
        let first = self
            .changes
            .partition_point(|change| change.version <= version);
        if self.changes.get(first).map(|change| change.version) != Some(version + 1)
            || self.changes[first..]
                .iter()
                .any(|change| !change.decrease_only)
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
        let slot = &mut self.field_storage[storage];
        for &cell in &entry.goals {
            // pathing.py:216-220: freed targets AND freed source cells must
            // become goals again, including fields previously all-INF.
            if self.cell_marks[cell] == generation && !self.blocked[cell] {
                slot.distances[cell] = 0.0;
            }
        }
        let mut minimum = slot.frontier.last;
        for &cell in &self.repair_cells {
            if !self.blocked[cell] && slot.distances[cell] < INF {
                minimum = minimum.min(slot.distances[cell].to_bits());
            }
        }
        slot.frontier.rebase(minimum);
        for &cell in &self.repair_cells {
            let distance = slot.distances[cell];
            if !self.blocked[cell] && distance < INF {
                slot.frontier.push(distance.to_bits(), cell as u32);
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
        if self.profile_enabled {
            field_profile::work(
                self.profile_row(self.cache[field.0].key.profile_kind()),
                0,
                1,
            );
        }
        true
    }

    fn ensure(&mut self, field: Field, cell: usize) -> usize {
        debug_assert_eq!(self.cache[field.0].version, self.version);
        // Field handles address metadata, so they survive storage eviction.
        // field/source_field already touched resident storage. Repeated
        // waypoint and distance queries need only restore an evicted slot.
        let storage = match self.cache[field.0].storage {
            Some(storage) => storage,
            None => self.use_field(field),
        };
        let entry = &self.field_storage[storage];
        // last is a lower bound on unfinished work even before redistribution.
        // Strictly smaller values are final; equality still drains below.
        if entry.frontier.occupied == 0 || entry.distances[cell].to_bits() < entry.frontier.last {
            return storage;
        }
        let _profile = self.profile_field_span(field);
        let entry = &mut self.field_storage[storage];
        // Drain equal keys too: afterwards this cell and all lower values are
        // final, even if the cell started with an INF upper bound.
        if self.profile_enabled {
            let pops =
                entry.expand_to::<true>(cell, &self.cell_flags, &self.move_masks, &self.neighbors);
            field_profile::work(
                self.profile_row(self.cache[field.0].key.profile_kind()),
                pops,
                0,
            );
        } else {
            entry.expand_to::<false>(cell, &self.cell_flags, &self.move_masks, &self.neighbors);
        }
        storage
    }
}

impl FieldStorage {
    fn expand_building_goals<const PROFILE: bool>(
        &mut self,
        best: &mut f32,
        goal_mask: &[bool],
        cell_flags: &[u8],
        move_masks: &[u8],
        neighbors: &[[u32; 8]],
    ) -> u64 {
        let mut pops = 0;
        while let Some(key) = self.frontier.min_key() {
            if f32::from_bits(key) > *best {
                break;
            }
            if PROFILE {
                pops += 1;
            }
            if let Some((distance, cell)) = self.expand(cell_flags, move_masks, neighbors) {
                if goal_mask[cell] && distance < *best {
                    *best = distance;
                }
            }
        }
        pops
    }

    fn expand_to<const PROFILE: bool>(
        &mut self,
        cell: usize,
        cell_flags: &[u8],
        move_masks: &[u8],
        neighbors: &[[u32; 8]],
    ) -> u64 {
        let mut pops = 0;
        while let Some(key) = self.frontier.min_key() {
            if f32::from_bits(key) > self.distances[cell] {
                break;
            }
            if PROFILE {
                pops += 1;
            }
            let _ = self.expand(cell_flags, move_masks, neighbors);
        }
        pops
    }

    fn new() -> Self {
        Self {
            owner: None,
            previous: None,
            next: None,
            distances: Vec::new(),
            frontier: Frontier::new(),
            wall_extra: 0.0,
            forward: false,
        }
    }

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
        let neighbors = &neighbor_indices[index];
        let mut moves = move_masks[index];
        while moves != 0 {
            let q = moves.trailing_zeros() as usize;
            moves &= moves - 1;
            let next = neighbors[q] as usize;
            // pathing.py:100-110: source fields charge the entered cell's
            // wall; backward fields charge the current cell's wall. Repairs
            // use this same direction and add wall cost before the distance.
            let mut cost = if q < 4 { 0.5 } else { diagonal };
            let wall_cell = if self.forward { next } else { index };
            if cell_flags[wall_cell] & WALL != 0 {
                cost += self.wall_extra;
            }
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

// Non-wall components for rubble; no distances stored.
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
        profile: bool,
    ) -> u64 {
        if self.version == Some(version) {
            return 0;
        }
        self.labels.resize(cell_flags.len(), NO_COMPONENT);
        self.labels.fill(NO_COMPONENT);
        self.pending.clear();
        let mut label = 0_u32;
        let mut pops = 0;
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
        // Every labelled cell is pushed and popped exactly once. Count the
        // completed labels in one scan, leaving the flood-fill loop untouched.
        if profile {
            pops = self
                .labels
                .iter()
                .filter(|&&label| label != NO_COMPONENT)
                .count() as u64;
        }
        self.version = Some(version);
        pops
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

fn is_goal_cell(n: usize, i: usize, j: usize, cx: f64, cy: f64, half: f64, reach: f64) -> bool {
    let (lo_i, hi_i) = goal_bounds(n, cx, half, reach);
    let (lo_j, hi_j) = goal_bounds(n, cy, half, reach);
    if (i as isize) < lo_i || (i as isize) > hi_i || (j as isize) < lo_j || (j as isize) > hi_j {
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
