> Predecessor Python filenames and parity procedures in this document are
> historical provenance from `f04706c`. Deleted tools are not runnable; see
> [the current documentation](../../README.md) for native commands and remaining Python ports.

> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Experimental sampled Dragon Duke isolation

This is an opt-in conditional model, not a claim about Clash of Clans' internal
clock or a calibrated prediction. Strict continuous membership remains the
default and retains the attracting-contact rejection documented in
[the contact diagnosis](DUKE_CONTACT_DIAGNOSIS.md).

## Evidence boundary

Primary publications checked on 2026-10-04:

- [Supercell's February 23 release notes](https://supercell.com/en/games/clashofclans/blog/release-notes/the-february-update-has-escaped/)
  connect Duke's enraged behavior to the absence of nearby flying troops and
  describe its damage and trap effects. They do not specify a sampling period,
  precise contact convention, hysteresis, or behavior at an attracting contact.
- [Supercell's July 9 balance explanation](https://supercell.com/en/games/clashofclans/blog/news/july-balance-update/)
  discusses isolation and a further trap-reduction adjustment. It does not give
  an isolation-update cadence or contact dynamics. Its balance discussion also
  reinforces that the preserved pinned statistics are not a current-game claim.

The repository's existing catalog record comes from a third-party pinned
snapshot and supplies melee/ranged modes and nearby range. Its geometry and
timing gaps remain declared hypotheses. No observed cadence was recovered from
the checked primary publications; no cadence is inferred from video frame rate
or from these benchmark outcomes.

## Experimental contract

The explicit configuration is
[`experimental-duke-isolation.json`](../../../data/battle-policies/experimental-duke-isolation.json).
Its period is 0.10 seconds. Sensitivity periods of 0.05 and 0.20 seconds were
selected before inspecting any experimental battle result. These are engineering
experiments spanning a factor of four, not measured game timings.

The policy samples all eligible friendly-air membership at deployment and then
at `deployment_time + integer_tick * interval_seconds`. Membership is inclusive
at the existing circle radius, with the engine's existing geometric epsilon.
The resulting isolation state is held until the next sample, including when
allies move, spawn, die, or become inactive between samples. This timing choice
is explicit in the configuration. It adds no geometric hysteresis or new speed.

Sampling occurs at the first existing hero-preparation phase at a due time.
Repeated preparation after later events at that same timestamp does not sample
again. This retains the kernel's phase order and avoids repeated cooldown
rescaling. A Duke that becomes inactive has its sample clock suspended; on
reactivation it samples immediately and resumes the original deployment-anchored
grid, skipping missed ticks without catch-up combat.

At a sample, existing range, damage, trap multiplier, attack-rate rescaling, and
future projectile selection are applied together using the existing code. The
ordinary selectors still retain and route toward targets. Already launched
projectiles keep their captured properties and lifecycle. Between samples there
are no exact isolation-crossing events; the sample clock is an explicit scheduler
boundary. Other event boundaries and combat mechanics are unchanged.

For one uninterrupted active period of duration T, there are at most
`floor(T / interval) + 1` samples. Contact therefore cannot generate an unbounded
relay of epsilon-sized isolation events. The minimum accepted interval is 0.001
seconds, an execution constraint rather than a claimed game cadence.

Two declarations are required: the actor's complete `isolation_update` contract
with experimental provenance, and the scene's `model_rules.duke_isolation` value
`explicit_friendly_air_membership_with_experimental_sampled_updates`. Missing,
inconsistent, nonfinite, or unsupported contracts fail validation. The normal
compiler preserves the policy in parameter provenance; runtime output includes
its source, period, status, and sample count. Unmodified inputs use strict mode.

## Reproduction and comparison

The diagnostic tool reads the preserved four input files without writing them.
It overlays the policy and scene declaration only in memory and records the
original file hashes, effective specification hash, policy override, and source/
data hash. Generated states and compressed results stay in ignored `reports/`.

From this checkout, with Python 3.12.14:

```powershell
python -B tools/diagnose_duke_contact.py `
  --fixtures '<private full-army directory>' `
  --prefix 'air-ranked-none-180s-step-0.25-' `
  --duke dragon-duke --ally army-dragon-15 `
  --isolation-policy data/battle-policies/experimental-duke-isolation.json `
  --wall-seconds 480 --save-result `
  --output reports/contact-experiment/period-0.1-step-0.25.json
```

Use `--step 0.125` for the half-step check. Use `--sample-period 0.05` or
`--sample-period 0.2` for policy sensitivity, with distinct output names. Omit
`--isolation-policy` to run strict mode (180-second wall limit is sufficient for
the preserved rejection). No army, layout, radius, range, health, damage, or
battle horizon is changed for these experiments.

Completion means that the original battle horizon or an existing legitimate
termination condition was reached. It does not mean victory or accuracy. The
tool saves outcomes, resources, complete traces, and final actors for comparison;
NaN or infinity cannot be serialized as a successful comparison result.
Heartbeat files show simulated time during each supervised run.

The half-step comparison uses an absolute tolerance of 1e-7 for numeric trace
and actor fields, selected before its result is inspected. Categorical events,
actor identities, finite resources, stars, and destroyed-building sets must
match exactly. This is a convergence check, not permission to smooth output or
alter events. Sensitivity across policy intervals is reported separately and is
not expected to satisfy the half-step tolerance.

Three focused tests were added: complete-contract validation; clock/lifecycle/
cooldown handling; and an attracting-contact integration that strictly rejects
without the policy but progresses with sampling at maximum steps 0.017 and 0.8.
Existing strict boundary regressions remain in place.

## Ground-route numerical correction

The first full-battle comparison exposed a separate grid-seam sensitivity. A
ground unit replanning at an integer coordinate could be placed in the cell to
its left by a few ulps of roundoff. The two otherwise equivalent positions then
received different cell-center waypoints, creating a macroscopic route change.
In the captured case this affected Royal Champion's route, introduced an extra
X-Bow range boundary, and changed a pursuing defender's subsequent trajectory.

`_ground_route` now canonicalizes a start within the existing 1e-10 tolerance of
an integer seam only when the original position is valid and the canonical cell
is free and inside the board. It does not change blocker occupancy checks or
snap positions outside that tolerance. A fourth focused regression covers both
sides of a free seam, a position outside tolerance, and a blocked neighboring
cell. This numerical correction also applies in strict mode.

The next comparison matched 4,116 events before a Seeking Air Mine selected
different effectively coincident targets. Trap trigger selection now treats
distance differences within the existing spatial epsilon as a tie and applies
the declared instance-ID ordering. Distinct distances outside epsilon still win
on distance. A fifth focused regression covers perturbations on both sides of
the tie and a genuinely nearer candidate; this does not change the trap's
declared target-selection policy.

## Recorded validation

On 2026-10-04, CPython 3.12.14 completed every experimental run below before
the 480-second supervisor limit. The original maximum step is 0.25 seconds;
the half-step run changes only that ceiling to 0.125 seconds. Each run keeps
the original 180-second battle limit and reaches the existing
`all_counted_buildings_destroyed` termination condition.

| Sampling period (s) | Maximum step (s) | Battle completion (s) | Trace events | Samples | Wall time (s) |
| --- | --- | --- | --- | --- | --- |
| 0.05 | 0.25 | 62.950568140148 | 4,915 | 1,162 | 194.963 |
| 0.10 | 0.25 | 62.479888798640 | 4,941 | 419 | 308.518 |
| 0.10 | 0.125 | 62.479888798640 | 4,941 | 419 | 306.508 |
| 0.20 | 0.25 | 67.624703841260 | 4,983 | 314 | 127.809 |

The two 0.10-second runs agree over all 4,941 ordered trace events, complete
final actor states, resources, and outcomes within the predeclared absolute
numeric tolerance of 1e-7. Categorical values and actor identities match.
Intermediate frames were not saved or compared. Serialized byte hashes differ
because insignificant floating-point digits remain; byte identity is not claimed.

All three experimental periods produce 3 stars and 100% destruction (94 of 94
counted buildings) in this conditional model. Completion time varies by about
5.145 seconds and traces differ across periods. Thus the result remains
sensitive to the unmeasured policy, despite the successful numerical half-step
check. These outcomes are not game predictions or calibration evidence, and
0.10 seconds was not selected by its score.

The unmodified strict input still rejects at 18.305471758783995 simulated
seconds in 70.267 wall seconds. Its diagnostic still requires a declared
contact dynamics policy; experimental completion does not silently relax that
contract.

All five runs use source/data fingerprint
`b6a0b2a48e47701aa78693b8b6f30e5161de735326d6701f4283be3d03099075`.
The preserved input specification SHA-256 is
`b49d055eade4154ce90a3cf29162be504e9e7ae8434e8e86615c7a4725e3ac1b`.
The private evidence includes all four input hashes, effective specification
hashes, compressed results, run summaries, and the half-step comparison under
ignored `reports/contact-experiment/final/`; none of those private inputs or
outputs is included in the code patch.

`python -B verify.py` passed all 1,196 tests in 32.576 seconds. Black 24.10.0
accepted all 11 touched Python files. The five added regressions cover the
explicit policy contract, sample clock/lifecycle handling, attracting contact,
grid-seam routing, and trap ties. The remaining limitation is empirical: an
actual isolation-update/contact model still needs independent game evidence.

## Published evidence

The [compact run summary](../../evidence/duke-contact-summary.json) and [half-step comparison](../../evidence/duke-half-step-comparison.json) preserve the reviewed numerical results and fingerprints. They contain no raw profile, layout dump or full private trace. The command above still requires separately retained private inputs.

An independent [publication verification](../../evidence/publication-numerical-verification.json)
reran the 0.10-second policy at maximum step 0.25 from a clean checkout. It
completed in 421.079 wall seconds under the 480-second limit and reproduced
62.479888798640 simulated seconds, all 4,941 trace events, final actors,
resources and outcomes within 1e-7. All 1,196 portable tests and the CLI,
repeatability, candidate export, formatting and cleanliness checks passed.
Raw checkout hashes differ with Windows line endings; normalized source/data
content was independently verified equal across all 125 relevant files.
