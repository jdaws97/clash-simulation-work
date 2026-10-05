# Exact-event pursuit throughput checkpoint

This is a performance delta after the independently reviewed recipe/higher-TH
tree `00cff2e417fd3292737b636a21a8b9c01330e610`. It does not add game mechanics or
change the pursuit policy. The reviewed recipe patch remains a separate rollback
checkpoint; these changes require their own review.

## Changes and invalidation

Weapon-range boundary queries now reuse a coarse target list for weapons with
the same team, target kinds and target layers. The list lives only for that one
query, preserves actor insertion order, includes spell decoys independently of
ordinary layer restrictions, and still runs every existing eligibility predicate.
No target, position, status, trajectory or event time is cached across queries.

Trap trigger selection filters active units once before iterating the traps.
The original per-trap exclusions, layer/team checks, weights, distance tolerance
and tie policy still apply. This phase only queues effects; damage, removal and
other lifecycle changes remain in the later original settlement phase.

Ground attack-point geometry uses a bounded 65,536-entry cache keyed by grid
cell, exact target position and footprint dimensions, and attack range. It does
not cache live wall HP, routing costs, source position, paths, targets or status.
Target motion, footprint changes and range changes produce different keys.

The scheduler still visits all the original boundaries. No route is extended,
range widened, time step changed, event dropped or new pursuit cadence selected.

## Measured comparisons

A declared synthetic scene uses two equal-speed point movers, 24 stationary
weapons, 200 inert wall actors and one destination. It reproduces the observed
near-parallel contraction cost, but is not a complete recipe or a calibrated game
battle. Its target uses straight air motion to isolate geometry; it does not
claim to reproduce the full defending-hero return state machine.

| Check | Preserved implementation | Optimized | Event/state comparison |
| --- | ---: | ---: | --- |
| Pursuit scene, cProfile wall time | 17.643 s | 13.544 s | Same 2,980 boundaries and complete result hash |
| Range-boundary query cumulative time | 5.107 s | 1.103 s | Same contact at 0.0011268319491742405 s |
| Live wall damage/opening scene, wall time | 0.570 s | 0.440 s | Same 2,000 boundaries and complete result hash |
| Delayed traps, mixed layers and reserve scene | 0.031 s | 0.030 s | Same 222 boundaries and complete result hash |

The pursuit result SHA-256 is
`6acfeff33670f4b1d303f92074d8b156a38a48904793ebaaf3ea54dbf43af9f0`.
The input SHA-256 is
`9735ac6bf0e941e9d72d8ae879e4da8d584869131f1f3b83be1136dc954b4e8c`.
The pursuit measurement isolates the candidate-list change; the subsequent
geometry cache is exercised by the wall comparison. All comparisons are bounded,
serial reduced runs with background stack dumping disabled. Single-run timings
show a local improvement, not a general full-battle speed guarantee.

The geometry calculation also matches the preserved implementation exactly for
2,000 queries spanning changes to target position, footprint and attack range.
The existing full suite then passed **1,224 tests in 34.902 seconds**. No tests
were added. Black 24.10.0 and whitespace checks pass. The independent reporting
review and these performance checks are distinct evidence.

Private reproduction/profile/result files remain under ignored
`reports/pursuit-throughput/`. The earlier no-background-stack-dump full-recipe
attempt stopped cooperatively at 165 seconds, as recorded in the consolidated
checkpoint; it predates this performance delta. No complete exact-recipe battle
has been rerun after this delta. The native fault cause remains unresolved.

## Remaining critical path

Near-parallel pursuit still requires approximately 3,000 boundaries in this
case; the current change lowers work per boundary rather than eliminating that
contraction. The reduced profile still spends substantial time in target scans
and health settlement. Full-scene route work and interacting mechanics can have
different costs. Further changes must preserve complete event/state comparisons
and explicit model assumptions. Complete exact-recipe execution and full-category
coverage remain unproven.
