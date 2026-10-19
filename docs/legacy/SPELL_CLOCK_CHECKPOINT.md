# Paid Ice Block clocks and Jump displacement

This checkpoint extends `c20dd45026c64bafa9dc321fd4118b918ace5113`.
This document records frozen commit `03033db5cc6c58f49ce9e28d3f9ad0f5e269de1a`;
later scope additions are in [the lifecycle checkpoint](SPELL_LIFECYCLE_CHECKPOINT.md).
It is synthetic software acceptance, pending independent review. There is zero
complete held-out game calibration. The catalog remains the unverified snapshot
from `chiefpansancolt/clash-of-clans-data` commit
`c6967314d7281bb87c362993e2635e58cd77b351`, not current-game verification.

Ice Block now binds through v29 paid resources, shared movement, main/wall weapon
work, shared damage receipts, and the existing termination owner. Its captured
troops remain targetable. Independent Ice fields use the strongest reduction and
union pause duration; Freeze and displacement extend only newly paused work.
Reduction expiry is independent of the Freeze clock. An active field alone does
not retain an exhausted army. No generated housing or charges are introduced.

The complete existing experimental spell policies remain mandatory, including
the audited `same_time_settlement` and `clock_rounding` fields. The shared binding
adds `ice_lifecycles=ordinary_weapons_and_wall_work_reject_secondary_lifecycles`.
Ordinary troops and spell-generated Bat/Skeleton weapons can receive Ice.
Troops with secondary lifecycle models and heroes currently reject explicitly;
their production, aura, morph, equipment, pet and rescue clocks are not implied
by ordinary weapon acceptance. Clone, Revive and Angry remain unbound here.

The independent Jump/Tornado finding is corrected using the existing shared
four-neighbor router with a clear-cell exit goal. If forced capture discarded
the planned exit, the unit retains only its already granted wall exemptions,
recomputes a legal nearest clear exit, and walks it after forced motion releases.
Forced motion retains its declared obstacle clipping. No teleport, new wall
permission, building penetration or automatic damage is introduced. Missing
reachable exits still reject. The additional explicit binding policy is
`jump_displaced_exit=shared_ground_route_to_nearest_clear_cell_after_forced_motion_no_teleport`.

Four bounded vertical tests, each at maximum steps 0.017 and 0.25, establish:

- Two paid Ice fields preserve the initial unfinished cooldown through their
  union, spend exactly two spell slots, and apply source-attributed 0.14 damage
  scaling only during the pinned level-one field lifetimes.
- Ice suppresses ordinary movement for its pinned seven-second lifetime, then
  movement/weapon use resumes. A separate fragile paid army dies and exhausts
  immediately without waiting for the field end.
- A paid Lightning kills an actual released defending Ice Golem. Its declared
  death-Freeze overlaps Ice in both orders; unfinished attack work and independent
  damage reduction expiry survive. Exactly two paid slots are consumed. The
  longer defensive Freeze uses an explicit synthetic multiplier, not a game value.
- Paid Jump with Tornado capture at t=20 survives expiry at t=21, remains clipped
  during capture through t=27, and clears the wall afterward. Movement is bounded
  by elapsed time and speed, all walls stay alive, the Town Hall footprint stays
  blocked, exemptions clear, and one spell slot is spent. Existing no-Tornado
  traversal and expiry controls remain in the regression suite.

These checks do not establish army rankings, general secondary-lifecycle Ice
coverage, complete source fidelity, or the unresolved TH16 Root Rider throughput.
