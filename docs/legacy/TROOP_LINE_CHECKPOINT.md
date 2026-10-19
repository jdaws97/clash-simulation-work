# Finite troop line weapon shared checkpoint

Base: e8b89f4f8a22c0597dff95479fec1ed288a5af8e. Bowler, Super Bowler and
Super Archer now use the owned shared projectile queue in v27-v29. Their selected
catalog identity, level, paid army slot or defending Castle membership is retained.
The runtime never creates a troop, extra payload or ordinary duplicate projectile.

Every instance requires attacking_extension_scope, complete line_weapon_parameters
and line_binding. Defensive instances additionally require the explicit defending
extension scope, role contract and existing donor/receiver Castle contract. Target
layers, geometry, repeats, live impact membership and source persistence are
caller-supplied uncalibrated policies. The binding explicitly selects whole-segment
Super Archer damage at terminal arrival, invisible-target exclusion, shared
collateral/protection, line packets before ordinary packets within the same health
batch, and upward rounding when a positive impact delay is lost to floating point.
This is not a claim of actual continuous projectile collision timing.

Released packets retain direction, launch damage/buffs, layers and response policy.
They survive actual source death and Recall, sample live target footprints at each
impact, and share a once-per-launch visited ledger. Protection is settled through
the same damage receipt service as other weapons. Shared collateral allow/ignore
and hidden-Tesla eligibility apply. Exact strictly future deadlines participate in
the event frontier even below the general EPSILON tolerance. Defensive pending
packets carry defense ownership and cannot keep an exhausted attacking army alive.

Five focused tests in test_troop_line_integration.py cover:
- Paid three-identity family at steps .017/.25: one launch, source death at zero,
  primary loss, later counted-building damage, drained finite queue and outcome.
- Paid defending Bowler release, actual damage after Castle death, one defensive
  owner, no attacking resource charge and exhausted-army termination with a
  defensive packet still pending (.017/.25).
- Protection consuming a visited hit without a later unprotected repeat; exact
  2.5e-12 and 6.5e-12 paid impact boundaries.
- Paid Recall retaining a released projectile; paired paid defender collateral
  allow/ignore membership with a Castle-released defender.
- Raw missing owner/model and omitted shared-binding rejection.

Pinned catalog: c6967314d7281bb87c362993e2635e58cd77b351; row quantities remain
unverified snapshot data. Full held-out game calibration: zero. No current-game
accuracy or performance ranking is established. Advanced Ice/Clone/Angry secondary
lifecycle combinations still fail closed. Other troop families, remaining sieges,
selected crafted defenses and full Root recipe throughput remain separate work.
Independent review of this new checkpoint is pending.

Prior independent review: task-16 limited-cleared 3056d21 Healer moving-primary
contact and e8b89f4 attacking Super Valkyrie generated Rage. That review expressly
does not clear Root throughput, other troop families or game calibration. The
four earlier frozen worktrees remain unchanged.
