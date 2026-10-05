# Narrow useful army candidates before recommending a manual base build

Success is a practical shortlist of two army/action packages, with a clear funnel,
deployment, equipment, strengths and failure cases. It does not require guaranteed
three stars or perfect game replication. The search only supports claims within
the admitted candidate pool. Sixteen Dragons remains an engine control, not the
proposed final army. Existing Root/Druid recommendations remain withdrawn.

Task23 owns final candidate design and its bounded input/result screening; this is
the integrator's proposed control structure, not a competing run queue. Task24 owns
the diverse defense matrix, Task26 the Duke fix, and the independent reviewer owns
audit. The integrator checks compatibility and combines evidence without duplicating
their runs or editing their working files. Candidate identities may be refined by
Task23 and Jarod's feedback while retaining the declared comparison controls.

## Smallest next army screen: three serial full battles

Use the exact same full TH18 forward-Hot-Candle defense, Legend I profile, west
entry, account, donated inventory and engine version for all three cells:

| Cell | Army | Question |
|---|---|---|
| C0 control | 14 Dragons + 20 Minions | Current delayed-cleanup plan on the selected engine |
| A funnel/cleanup | 14 Dragons + 20 Minions | Does paid funnel preparation followed by scheduled concentrated commitment improve the control? |
| B funnel/screen | 15 Dragons + 4 Balloons | Is the same scheduled funnel structure stronger with a small Balloon screen rather than Minion cleanup? |

All use 320 owned troop housing. Keep the existing Stone Slammer, four heroes/pets,
11 owned spell housing and separate 50-housing Castle plus 3 donated spell housing.
Compare whole packages when composition and deployment differ; do not attribute
their entire score difference to one mechanic.

Preparation for A/B must reserve two owned Dragons, one for each shoulder of the
chosen entry and subtract them from the main wave. Specify deployable coordinates,
plausible shoulder-building targets and a paid preparation window. Main Dragons,
the central Warden and Slammer then use one declared finite deployment schedule.
Their deployment does not wait for the shoulders to clear and has no automatic
salvage branch. Keep `funnel.required=false` with an explicit reason describing
scheduled commitment after paid funnel preparation. Times are test parameters,
not game constants or proof that the funnel will be ready.

The Queen/Unicorn and Champion deploy on selected flanks; the Duke has an explicit
position and recorded isolation assumptions. Prose roles do not force their target
selection. Keep these placements and roles common across A/B where possible.
A schedules its Minions after the main wave; that delay alone does not establish
safe cleanup. B schedules four Balloons as an entry screen and keeps its extra
Dragon in the main wave. Align the Warden, siege, spells and cleanup with the actual
core schedule. Every deployment spends its own admitted actor once. Each final
card names times, intended visual tells and the risk of committing into a failed
funnel. Record shoulder clearance at commitment as an observation, not a release
condition. Inspect actual action times and target choices in the receipts.

The existing scheduler's alternate events must use disjoint paid actions. It does
not support two mutually exclusive deployment commands for the same paid troop:
full-battle admission rejects them with "Deployments may spend each declared
attacker once only". A separate salvage reserve can deploy, but selecting that
branch suppresses the main commitment and leaves those main troops undeployed.
It cannot rescue or redirect the same main force. Required-funnel experiments
with that behavior are diagnostics, not the current shortlist's player plan.

Single-entitlement alternative deployment belongs on the backlog; it is not
implemented or required for this bounded screen. See PROTOTYPE_BACKLOG.md. Existing
mass-air bundles remain seeds, not prepared A/B plans. Task23 must compile the
new single-deployment schedules before running and disclose failed-funnel risk.
Any retained exact-HP/target-ID ability gate remains an ideal engine observation;
slower polling alone does not make it a human reaction or visibility model.

## Keep equipment controlled initially

| Hero / pet | Existing seed equipment and levels |
|---|---|
| Queen / Unicorn | Invisibility Vial 7 + Magic Mirror 20 |
| Warden / Electro Owl | Eternal Tome 18 + Healing Tome 15 |
| Champion / Spirit Fox | Rocket Spear 21 + Electro Boots 23 |
| Dragon Duke / Phoenix | Revenge Deck 20 + Fire Heart 18 |

These are synthetic benchmark selections, not confirmed Jarod-owned levels or a
recommended final gear set. Confirm available gear/pets and the intended Castle
donations before publishing a player-ready card. Keep them fixed for C0/A/B so an
equipment swap does not obscure the funnel/composition question. After narrowing,
at most one supported, user-owned equipment substitution gets a matched two-run
comparison if feedback identifies a specific failure it could address.

## Budget, comparison and promotion

The integrator runs no combat batch. Task23 can prepare and execute the agreed small
screen after the selected engine and exact A/B inputs are frozen. Proposed C0/A/B
budget: serial cases at 240 seconds wall per cell, 730 seconds total.
These are ceilings, not a request to extend a stalled run. Preserve every timeout,
unsupported guard and incomplete result without a score or automatic retry.

If using the unchanged fc9 engine and exact original C0 input, its prior completed
receipt can be a reference, saving one run. If the Duke correction changes the
engine, run fresh C0; do not pool or relabel old scores as new-engine evidence.

Review stars/destruction and Hall destruction first, then shoulder clearance at
the scheduled commitment,
actual main commitment, wasted/reserved housing and spells, hero/ability use,
late cleanup, ending survivors, time limit and execution complexity. Show the
individual cells; do not invent a weighted score or opponent probabilities.
Prefer a clear improvement without a major new failure mode. An uncleared shoulder
at scheduled commitment is an observed strategy failure to review. An unsupported
cell has no score and cannot establish that an army is weak.

Promote up to two plans for two additional matched full battles against the saved
central-Hero-Hunter TH18 design, with east-side entry and explicitly reselected
funnel placements and schedules. This is a transfer check of whole plans, not an
isolated position test.
If the order reverses, retain both with their conditions. If neither is useful,
revise one observed deployment failure before adding more families or a broad grid.
Present a provisional shortlist with specific strengths/risks and invite practical
feedback even while calibration is incomplete. Do not imply global optimality.

Jarod's highest-value feedback is: preferred attack complexity; his reliable/current
funnel and typical failure (missed Hall, army split, core losses, cleanup timeout);
and confirmed equipment/pet levels and realistic Castle donations. This can reshape
the candidates without waiting for perfect replay matching.

## Defense has a higher evidence bar

The two generated TH16 layouts have identical nongeometry inventory/settings and
active Hot Candle under Legend I. One TH17 attack completed; the other hit the Duke
boundary guard. That pair cannot justify manual construction. Task26 owns the fix.

After its scoped review, use two generated layouts against at least three materially
different admitted attack styles and two entry directions: twelve paired cells as
the first defense screen. Include an air style, a ground style, and another genuinely
distinct supported hero/siege or spell-led plan; two minor Dragon variants do not
count as broad style coverage. Keep attacker TH, army and semantics identical within
each layout pair. Match the user's TH17/18 threat range, and add targeted opposite-TH
sensitivity only where a candidate's apparent advantage depends on that level.
Availability of all three meaningful styles must be checked before scheduling;
this plan does not claim those full profiles are already prepared.

Use the conditional paired outcomes and worst observed cases to assess robustness.
Require useful advantages across varied cases, explicit bad matchups and no hidden
unscored comparison cells before suggesting the time-consuming manual build. Show
tradeoffs when no layout dominates. A twelve-cell synthetic screen is not a calibrated
defense probability. Before manual construction, also validate the final coordinates,
inventory, orientation and seasonal Station choice against the actual build context.
Do not extrapolate a win percentage from unweighted synthetic fixtures.

## Reusable runner and artifact readiness

`tools/run_full_comparison.py` already accepts explicit manifests of at most six
cases, per-case and total wall bounds, case selection and the required experimental
air-contact opt-in. It freezes inputs/engine identity, uses fresh output directories,
records paid actions/resources and terminal receipts, and leaves failures unscored.
No new battle mechanics or broad test suite is needed for the proposed preparation.

`examples/candidate-search/readiness.json` records fresh compilation of the existing
Dragon/Minion and Dragon/Balloon seed inputs on both saved TH18 design packages.
It is admission evidence only; no new full battle was run. `plan.json` is an explicitly
disabled work queue, not an executable simulation manifest. The Balloon seed uses
its existing declared synthetic splash/recipe assumptions. Duke boundary handling,
Warden independent targeting, conditional crafted rotation and zero complete held-out
game calibrations remain visible limits, not reasons to suppress a useful shortlist.
