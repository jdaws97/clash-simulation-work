# Partial encounter evidence and calibration v1

`clashlab.replay_calibration` is a pure comparison layer. It does not edit the
battle kernel, admit unsupported mechanics, generate attacks or change defense
objectives. Existing `replay_evidence` scoreboard checks and
`replay_observations` comparisons retain their APIs. The new layer is opt-in.

A compatible result means the specified predicted interval intersects the
observed interval under the declared assumptions. It does not establish damage,
causality, game ticks, base weapon cadence, complete battle validity or a win
rate. Missing predictions are incomplete. A disjoint interval falsifies that
specified model; it is not proof of the competing mechanism.

## Executable schema

The versioned JSON contract is enforced by `validate_case` and
`validate_protocol`. The five bounded acceptance scenarios in
`tests/test_replay_calibration.py` include a fully declared synthetic fixture.
Real files, media, identities and reports belong outside the publication tree.

| `partial-encounter-v1` field | Contract |
| --- | --- |
| `id`, `evidence_class`, `selection_method` | Stable case ID, `real` or `synthetic`, explicit selection and sampling bias. |
| `sources` | Unique IDs, integer `[numerator, denominator]` timebase, nullable media SHA-256, and extraction-continuity description. No inferred 60fps clock. |
| `evidence` | Unique ID, source ID, integer PTS, relative frame path, SHA-256. All frames are hashed if `frame_root` is given; real comparisons without it are blocked. Paths cannot escape the authorized root. |
| `clock_segments` | Unique ID, source ID, encounter ID, nonoverlapping PTS bounds, local origin PTS, origin uncertainty interval in game seconds, positive speed interval, evidence IDs and explicit assumption. Only `local_relative` clocks are accepted. |
| `bindings` | Exactly `patch`, `mode`, `modifiers`, `loadout`, `geometry`. Each has `status`, `value`, `reason`; nonunknown values need evidence IDs. `unknown` values are null; partial values are never sufficient for engine comparison. |
| `observations` | Stable ID, clock ID, entity ID, explicit target ID, observable, positive occurrence number, PTS interval, `left_open`, annotation-error pair, evidence IDs, limitation and previous-review boolean. Each endpoint must be a referenced frame. `logical_event_time` must be null. |

Supported observables are projectile appearance, ring appearance, model
disappearance, UI counter change, and actor appearance. This version compares
their times, not pixel position errors or damage. For absence in a before frame
and presence in an after frame, use `(beforePTS, afterPTS]`. Evidence cannot
assert the internal release, application or HP-zero tick from that bracket.

Clock mapping uses rational PTS arithmetic. For interval endpoints `p`, it
encloses `(p - originPTS) * timebase * speed + originGameSeconds`, including
negative offsets, both speed endpoints and origin uncertainty. The
`annotation_error_seconds` pair expands the early and late endpoints;
v1 requires nonnegative ordered values. An uncertain clock or annotation
envelope conservatively closes the resulting interval. No use is made of
`180 - displayed replay countdown`. Cuts, pauses or speed transitions require
distinct nonoverlapping clock segments. Zero-width shared boundaries are
rejected instead of arbitrarily assigned.

An exact binding value contains `scope_id` equal to the case ID,
`complete_for_scope: true`, a nonempty `snapshot`, and its canonical
`snapshot_sha256`. The engine owner supplies and verifies the domain meaning of
these snapshots using the existing compiler. A digest identifies content;
it cannot prove the underlying annotation is true. Snapshot scope must include
every influence on the partial encounter, not an invented complete village:

| Binding | Required domain content before claiming exactness |
| --- | --- |
| Patch | Observed build/data version and pinned mechanics source revision. A later screenshot of availability does not bind an older replay. |
| Mode | The particular replay's mode and ruleset. Ranked and war/CWL remain distinct. |
| Modifiers | Explicit effective values and active/absent boosts or special rules. Displayed hero levels alone do not supply these. |
| Loadout | Actor and target IDs, effective levels, equipment IDs/levels, pet pairing, relevant summons/reserves, initial HP/charge/status and all other contributors in scope. |
| Geometry | Tile coordinate system, actor/target positions/footprints/levels, relevant range/line-of-sight/traps/influences and explicit boundary conditions. Pixel estimates remain partial. |

## Frozen protocol and prediction interface

`replay-protocol-v1` binds the canonical case digest and declares `fit_ids`,
`validation_ids`, `validation_design`, `target_layer`, `tolerance_seconds`,
`tolerance_rationale`, `falsification_rule`, and
`missing_prediction_policy: "incomplete"`. Every observation is assigned once.
`max_prediction_width_seconds` caps prediction uncertainty after rendering
projection; an arbitrarily broad prediction cannot manufacture compatibility.
Engine protocols additionally freeze `model_sha256` and `input_sha256`; trace
values must match them before timing rows can be compared.
Fit and validation cannot reuse physical source/time frames, even through
different crops or source labels. Media SHA-256 is the canonical source
identity; aliases of it must have the same timebase and cannot provide
overlapping clock segments. Physical time is integer PTS times that timebase.
Identical retained frame hashes across partitions are also rejected, even if
the metadata claims different media. `held_out_encounter` requires content-bound
source identities; missing media hashes cannot establish independence.
It also rejects encounter overlap and previously
inspected validation observations. Rechecking already reviewed frames is
`retrospective_same_encounter`, never pristine held-out validation. The
tool validates the declared split; audit receipts must establish chronology.

Freeze the case/protocol/model before running validation. Store their hashes
and a timestamped receipt separately. Changing a case, tolerance or split
requires a new protocol and report; the CLI never overwrites an old output.
Do not reinterpret a failure by widening tolerance after viewing residuals.

`replay-predictions-v1` contains `case_sha256`, `protocol_sha256`, `layer`,
`producer`, `input_sha256`, `model_sha256`, and `events`. Each event contains
`observation_id`, `clock_id`, `entity_id`, `target_id`, `observable`, `occurrence`,
and a finite ordered `seconds` interval on that local clock. Known targets
must match exactly, and missing prediction target fields are errors. An
observation without an identifiable/applicable target uses `target_id: null`
plus `target_status: "unknown"` or `"not_applicable"`; its prediction must
explicitly carry null too. Exact predictions use `[t,t]`.
Unknown/duplicate events and identity mismatches are errors. There is
no nearest-neighbor matching to make incorrect occurrence numbers look good.

Prediction time endpoints accept canonical rational strings such as `"1/15"`
or `"0"`, as well as finite JSON numbers. Generated cycle traces preserve
rational strings. Reports include exact rational observed/predicted bounds
alongside the float display values. A float identical to the published
representation of a comparison endpoint maps back to that exact endpoint;
this is a representation round-trip, not an added timing tolerance. The next
representable float outside the interval remains outside, and a point on an
open lower boundary remains excluded. Rational inputs are never snapped, even
if their float display rounds to a boundary. Ambiguous floats shared by two
different exact endpoints are rejected; supply rational seconds instead.
For engine projection this rule applies to the corresponding endpoint minus
its declared delay, before adding that delay in rational arithmetic.

The audit correction intentionally rejects older traces that omitted known
targets. Regenerate them from their frozen cases instead of guessing targets.
The retained original private trace/report remain immutable evidence of the
earlier implementation; new reports may differ in serialization without a
change to the observed timing brackets or their limited interpretation.

For `layer: "engine"`, all five exact snapshot values must also be copied
into `trace.bindings` and match the observed case. Each observable needs a
protocol `rendering_delays` entry with signed `seconds`, `engine_event_kind`,
`basis: "measured"` or `"experimental"`, and evidence. The trace event must
name that same engine event kind. Delay bounds project engine times to visible
times; animation onset is not automatically logical effect onset. Experimental
projections block comparisons unless explicitly enabled with
`allow_experimental=True` / `--allow-experimental-projection`. An opt-in never
turns that projection into a measured fact.

The sole kernel owner can consume `result.combat.trace` and pinned compiled
inputs to generate this external JSON envelope. The current replay renderer
already consumes `event` and `time_seconds` fields. Do not convert a
`death_time` to model-disappearance time, a spell field start to ring onset,
or a damage event to projectile release without the matching projection and
evidence. No shared spatial/adapter/full-battle/resource/termination or
spell/siege/CC edits are required by this patch.

```python
from clashlab.replay_calibration import compare_replay

report = compare_replay(case, frozen_protocol, predictions, frame_root)
```

Reports carry all three digests, frame verification count, exact binding gaps,
per-event signed interval residuals, missing/falsified/compatible statuses and
the declared validation design. An excluded open endpoint can be falsified
with zero numeric residual; the status is authoritative. Blocked reports may
show diagnostic timing rows but their verdict stays `blocked`. No aggregate
score can hide missing or falsified events. Whole-battle calibration count
remains zero; this module does not certify full battles.

## Existing private partial encounter

`tools/bind_existing_replay.py EVIDENCE_ROOT PRIVATE_OUTPUT` consumes the
existing `matched-observations.json`, pass-2 roster annotations and
`pass2-calibration-inputs.json`. It does not read NAS paths or collect new
evidence. `--media-hashes` optionally supplies source-ID/SHA-256 bindings.
It refuses output directories inside the publication checkout.

It binds three consecutive RC-to-one-X-Bow projectile appearances from the
first opening. The first two fit a conditional constant rendered interval;
the third supplies a retrospective check. `calibrate_rendered_cycle` uses
only the first two timing bounds to compute the period and third forecast:
`period = [b_low-a_high, b_high-a_low]` and
`next = [2*b_low-a_high, 2*b_high-a_low]`. These conservative closed envelopes
avoid reporting a midpoint as an exact fitted parameter. The third bound does
not enter the model hash or forecast. In-sample fit residuals are explicitly
marked. Same-target attribution and absence of missed appearances remain
conditional visual assumptions.

Outputs are `case.json`, `protocol.json`, `freeze-receipt.json`, `trace.json`,
`comparison.json` and `held-out-protocol.json`. The current footage has already
been inspected; the freeze receipt explicitly says it is not preregistration
before original evidence review. Passing this example is only an
observation-layer fit. Equipment/geometry/build/modifier gaps block engine
calibration. Visible RC/Unicorn pairing must not be replaced with Spirit Fox.
Stored account equipment levels and policy settings are not replay bindings.

Run a frozen comparison with:

```text
python -B tools/compare_partial_replay.py CASE PROTOCOL FRESH_OUTPUT --trace TRACE --frame-root EVIDENCE_ROOT
```

Omit `--trace` to produce the two-appearance fit and its retrospective report.
Exit status 0 means compatible within this limited protocol; 2 means blocked,
incomplete or falsified (inspect the saved report). Invalid input is an error.

## Held-out and coverage policy

No pristine held-out mechanical case exists in the inspected clips. The
generated held-out protocol is pending and specifies an entire independent
encounter as the split unit, including every overlapping crop and transition.
Freeze entity matching, uncertainty, eligible events, initial state, model
revision/seed, phase, rendering delay, and tolerances before validation. Missing
outcomes are incomplete; disjoint intervals reject the stated model. Report
selection/exclusion and per-encounter coverage without a convenience-sample
win rate. A plan for future collection does not authorize game actions.

Keep all Duke isolation candidates 0.05/0.10/0.20 seconds admissible. A cadence
comparison needs a validated isolation-state indicator, a known qualifying
neighbor crossing with sufficient geometry, and independently bounded
observation delay/phase. Current 4x frames, glow and pose changes do not supply
these. An opt-in 0.10-second model remains experimental.

The difficult-base description is one user-reported qualitative illustration.
CC placement, hero/trap density, Invisibility Tower and funnel difficulty
must not be promoted to visually verified hidden facts, overweighted in
calibration, or used as a global generated-defense template. Keep independent
coverage for varied layouts, attack styles and entry directions. Preserve the
user's Legend I TH16-versus-predominantly-TH18 attacking context, predominantly
TH17/18 defense context, and separate TH16–18 war/CWL evaluation. This module
adds no selection weights or TH-bait objective.
