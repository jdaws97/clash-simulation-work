> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Exact ground navigation reuse

Base: `9a31421941050ad9958f251b2759e19449ce3acf`.

The subsequent [weighted-route checkpoint](WEIGHTED_ROUTE_CHECKPOINT.md) records
a completed representative Root Rider versus TH18 battle on the combined patch.
The separate TH16 near-stall described here remains open.

`spatial._ground_route` previously rebuilt a breadth-first search for each goal,
including repeated unreachable and moving-target queries on the same grid.
The queue order and predecessor tree do not depend on the goal. The bounded
navigation cache now stores those two immutable maps, keyed by the canonical
start cell, the complete blocked-cell set, and both board dimensions. Each query
still computes its live goal footprint/range and picks the first reachable goal
in precisely the original BFS order. Fractional departure and terminal approach
are composed as before. Route lists remain independent mutable copies.

The cache holds at most 128 grids, each on a board of at most 4,096 cells. Larger
boards use the original search. Wall destruction, obstacle changes, jump/leash
exemptions, movement to a new start cell, and changed board bounds produce new
keys. Target motion, target size, range, and exit-cell membership are evaluated
outside the cached traversal. The ground route signature uses an immutable set
instead of repeatedly sorting the same obstacle cells; only set membership was
ever compared. No clocks, EPSILON, events, weapons, resources, selector policies,
or experimental game assumptions change.

## Bounded verification

Two small regression tests cover BFS ties, changed goals/ranges/fractional
positions, exit routes, obstacle mutation, board dimensions, unreachable goals,
and isolation of consumed route lists. Existing pursuit, Freeze, wall, healing,
and range tests also passed (79 focused tests).
The complete repository suite passed: 1,392 tests in 54.305 seconds, supervised
zero exit in 56.047 seconds. Two completed paid Root/owned-Dragon controls
(coarse and fine solver steps) matched the frozen baseline byte-for-byte across
their complete result objects, including outcomes, resource use, and traces.
These small controls are deliberately scaled contact tests, not representative
full villages.

An external differential harness compared 2,500 seeded varied geometry cases and
2,600 ground queries from a captured Root state against the frozen original
`_ground_route`: every returned route matched exactly.

The unchanged historical conditional TH16 Root input was then compared through
simulation time 18. Both serial fresh processes visited exactly 553 frontiers and
produced 919 trace records. The complete frontier time sequence and a hash of
every frontier's actors, live clocks, HP, targets, and status state matched; only
internal path caches were excluded. The complete trace hash also matched:
`54d7706b70b059ab5da16ac5f71886da7fa0827f77276a0cc9ecc8900d3d3d2a`.
Identical instrumentation took 73.330 seconds before and 62.415 seconds after,
a 14.9% reduction in this single paired prefix, not a general benchmark claim.

## Remaining full-battle blocker

The one fresh full attempt retained its 120-second simulation wall budget and
150-second external process limit. It stopped normally after 120.030 seconds at
simulation time 20.732081141328347, with 1,234 frontiers and 1,200 trace records.
There is **no completed full battle and no scored timeout result**.

A subsequent bounded observation from simulation 19.4 to 19.756 identified 23
range entries for each of two defending Dragons pursuing the Action Figure
Giant. These are relative-motion range entries, not the previously repaired
stale range-edge route arrivals. A three-actor reduction using the captured
geometry and an explicit 0.05-second external cadence completed 0.3 simulated
seconds in 16 frontiers (10 range contacts); its stationary-target control used
8 frontiers (2 contacts). Both Dragon weapons remained on cooldown throughout
that reduced interval. This is a local geometry control, not a replacement battle
or evidence that all full-battle events are redundant.

The later CPU window spent 10.07 of 18.15 profiled seconds in selector dispatch,
including 3.65 seconds in weighted wall routes and 2.64 seconds in ordinary
ground routes. The residual work is repeated whole-battle recomputation at dense
contact boundaries. Removing those boundaries or changing pursuit/retention
would change the existing movement model. This patch does neither. Further work
needs incremental event processing with explicit dependency invalidation, or an
independently reviewed equivalent optimization; this workstream has not proved
that the remaining slowdown is fundamentally irreducible.

All runs used fresh labels, serial processes, no scheduled traceback watchdog,
and no native-crash retries. Supervised differential and full-attempt receipts
record matching before/after source hashes and zero exits. The original input
files and captured states remain outside Git. This historical conditional input
is not current ranked-strategy validation. Complete held-out game calibration
remains zero. No publication, merge, deployment, or recommendation is authorized
by this checkpoint.
