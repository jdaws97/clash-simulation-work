> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Weighted routing and completed Root prototype

This increment follows `f5894d45d442c97d0424f57f93e89ed84f69e652` and changes
`walls.py` plus one focused regression. The original Dijkstra arithmetic, heap
ordering, tolerance and terminal approach are preserved. A bounded pure cache
keys the exact fractional source position, target footprint, attack range,
effective movement speed, effective wall damage, attack interval and attack rate,
every live wall's HP, all solid cells, and board dimensions. Travel-only queries
omit irrelevant wall-clearance data. Target selection, wall ownership, obstruction
selection, damage, clocks and resource use remain outside the cache.

The cache holds at most 256 immutable routes on boards of at most 4,096 cells.
Larger boards execute the same uncached query. Returned paths are independent
lists. The focused regression changes wall HP, damage/rate modifiers and speed,
then consumes returned routes. An external oracle compared 2,365 varied and
captured queries to the original weighted search: routes and floating-point costs
matched exactly. The combined patch also preserves all 553 frontier states and
919 trace records of the original TH16 prefix through simulation time 18.
That paired prefix took 73.330 seconds on the frozen base and 60.949 seconds on
the combined patch (16.9% less wall time in this one comparison).
The complete final suite passed: 1,393 tests in 52.698 seconds, supervised exit
zero in 54.453 seconds. Both complete paid Root/Dragon control results remain
byte-identical to the frozen base, including resource use and outcomes.

## Completed representative case

The unchanged original Root Rider versus TH18 fixture completed on the combined
patch, with its original account, army, full village, deployments and policies:

- Supervisor exit: **0**, before/after source hashes unchanged.
- Wall time: **302.313 seconds** (303.047 including the supervisor).
- Actual battle end: **116.85723807163991 simulated seconds**, force exhausted.
- Observed frontiers: **5,991**; trace records: **5,084**.
- Conditional outcome: **2 stars**, **89.36170212765957%**, 84/94 counted buildings.
- All **49** bound attackers deployed, **0** undeployed, all **11** spell slots spent.
- Clan Castle delivery spent; no pending members remained.
- Result gzip SHA256:
  `31624f263fe78d7ec8d8f2601a7a6ba8477d6a909a2e54871542278e543da7b3`.

The run used a fixed 400-second wall budget and a 430-second external process
limit, fresh outputs, and no scheduled traceback watchdog. It did not stop on a
wall-clock timeout. Input hashes were checked against the historical receipt
before execution. The raw inputs, result, supervisor receipt and reproducible
runner scripts remain outside Git in the task-26 handoff workspace.

This completion is a supported conditional prototype path, not gameplay
calibration or a strategy recommendation. The historical result used an older
engine and had a different outcome; it is provenance, not an equivalence or speed
control. Exact equivalence claims above are against the frozen current baseline.

## Remaining TH16 limitation

The separate TH16 fixture has a severe frontier near-stall near simulation
20.7354677. An extended attempt advanced from 20.7354613428 at 1,358 frontiers to
20.7354695844 at 2,953 frontiers. It was intentionally terminated after 232.922
wall seconds through a guarded stop of the owned process. Exit `0xFFFFFFFF` was
that deliberate termination, not an access-violation crash. Its cancellation
receipt is preserved and no outcome is claimed. Both completed and bounded runs
retain every scheduled event; neither EPSILON nor pursuit policy was relaxed.
The exact boundary owner at that stall was not captured. The earlier bounded
observation identifies Dragon/Giant recontacts at 19.4--19.756 seconds, but does
not prove they own the later stall.

No native Python crash occurred in this workstream. Independent review is pending.
No push, merge, deployment, private input import into Git, or new troop/spell
family is included. The net patch must be integrated without publishing private
ancestry.
