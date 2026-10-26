> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Joint attack search, version 1

This is a small, deterministic experiment runner, not an army recommendation
system. It uses the existing paid full-battle compiler and outcome computation.
It reports separate stars, destruction, elapsed time and completion time. It
does not estimate win probabilities, infer opponent weights or certify mechanics.

## Entry points and ownership

The existing `run.py generate-armies` enumerates legal troop/spell counts and
explicit loadout/CC options. `run.py evaluate` evaluates matched replay evidence;
it does not evaluate newly invented armies. `full-battle` binds and executes a
complete declared army/layout. This change adds a separate CLI without modifying
any of those entry points or shared kernel files:

```console
python -B tools/search_attacks.py run examples/attack-search-control.json --output reports/search-cold --cache work/search-cache
python -B tools/search_attacks.py run examples/attack-search-control.json --output reports/search-warm --cache work/search-cache
```

Use fresh output directories. The second run can reuse completed cached results.
The manifest is local JSON, with no network, game input, credentials or API calls.

`enumerate_joint_candidates(manifest, mode_rules)` returns a bounded declared-order
roster × plan prefix. It never materializes the unbounded Cartesian product.
`prepare_candidate(candidate, catalog, mode_rules)` returns the concrete paid
specification, compiler admission receipt and unmet integration dependencies.
`evaluate_candidate(...)` returns a completed outcome or an unscored dependency.
`run_search(...)` isolates each evaluation in a serial, wall-bounded process.

## Joint candidate representation

The manifest contains one explicit scenario and mode context, an account, layout,
opponent inventory declaration, battle policy, experimental assumptions/evidence
gaps, budget, army options and plan options. Each army option holds the full
existing `validate_army` schema plus its complete `entity_scene`:

- Troop counts/levels and own/received spell counts/levels.
- Selected heroes, each with two distinct owned equipment items, mode and one
  explicit pet or null; existing compiler support remains authoritative.
- One explicit siege or null, own/donated origin, and the complete CC payload.
- All required mechanic parameters and paid reserve identities in the scene.

Army generation can feed this axis after a domain adapter produces matching
entity instances. The search does not synthesize missing adapters from a name.
The manifest also requires a separate `scenario_environment`, captured explicitly
with `scenario_environment(reference_scene)` when authoring that scenario. It is
not inferred from whichever roster happens to run first. All defender entities
(including their complete activation, targeting, weapon and lifecycle policies),
traps, persistent hazards, shared simulation rules, target selection, defender
response policies and unknown future scene fields remain frozen. Only attack-team
entities, paid command/spell collections, attacking reinforcements and attacking
pet assignments are excluded from this projection; the paid compiler still
validates those variable channels. Shared policies cannot vary with a roster,
even if a new attack family would prefer different settings: use a separately
authored scenario with the necessary fixed policies.

Every roster's full immutable projection must match the manifest pin. Drift is
rejected before cache lookup or worker execution and checked again in preparation.
The environment and complete scenario context receive separate content hashes;
the scenario fingerprint is preserved in candidate, cache identity, row and
completed-result receipts. Comparisons require matching row/receipt fingerprints
and are partitioned by scenario hash, even if scenario labels happen to match.
Changing an opponent is a different experiment, not an attack-search option.
Older manifests lacking the explicit environment pin are rejected rather than
silently deriving an opponent from one of their candidate scenes.

Unsupported units, pets, equipment, siege or CC combinations fail existing
compiler admission. Existing compiler admission is conditional support, not a
claim of current-game correctness. All runs require experimental-model opt-in
and nonempty assumptions and evidence gaps. This version accepts only local
`conditional_pinned_snapshot` statistics; external statistic branches need a
separate content-hashed adapter.

Each plan event names exactly one `(collection, id)` selector, an `at_seconds`
value, explicit conditions, and optional placement. Supported collections are
scheduled attacking `entities`, `effects`, and the compiler's supported spell
collections. A plan must cover every scheduled spawn, deployment command,
ability, reinforcement command and spell cast. Controlled reserves without an
event remain reserved under the existing paid accounting. There are no free
effects or arbitrary JSON-path mutations.

For ordinary spawns and spell casts, `position` changes x/y. A CC deployment
uses its single `position`; a deploy command uses `positions` covering exactly
its paid targets. Abilities and manual siege releases carry no fake placement.
All legal board geometry and resource checks remain the compiler's responsibility;
live-game deployment exclusion zones are still an evidence gap.

Conditions support `time_seconds`, `alive`, `active`, `hp_fraction` and
`target_actor`, with declared actor identities and typed comparisons. A clock
condition must agree with the schedule. Any state condition blocks execution
until the paid observation scheduler hook exists. No condition is ignored.
For blocked candidates, `at_seconds` is the proposed earliest schedule used for
static admission; it does not imply that the gated action will occur then.

Each roster and plan records either `original_generated` provenance with its
source or `external_baseline`. Any external component makes the joint candidate
a baseline. Sources are supplied provenance, not independently authenticated.
External guides are not used by the included original synthetic control.

## Funnel and Hall-bait contract

TH18 scenarios require a funnel contract. Other scenarios may explicitly declare
a synthetic control without a funnel. Required contracts contain:

- Battlefield-state prerequisites and the commit event IDs they gate.
- A deadline within the battle time limit.
- Both `funnel_failed` and `hall_bait_detected` contingencies, each with explicit
  state conditions and either `hold_commit` or distinct alternate event IDs.

Prerequisites should refer to the scenario's flank targets, route clearing or
observed target lock. They are not fixed King/Queen corners. A planned example
could require both flank buildings destroyed and the lead unit targeting the
intended lane, while withholding the main commitment if a declared bait cue
persists. These are user-authored observation predicates, not an implemented
funnel-quality detector or a claim that the example is strategically correct.

`paid-observation-scheduler-v1` is a kernel-owner dependency. To make the contract
executable, the owner must connect observation boundaries to the compiler's finite
paid troop, spell, hero ability and CC entitlements; recheck cues at execution;
gate/hold the main commit at the deadline; select at most one alternative for a
commit; and retain unspent reserves and correct termination continuation.
All potential branch commands are currently admitted as distinct paid reservations.
Mutually exclusive branches cannot share a spell/ability slot by bypassing the
compiler. A future alternative-command entitlement requires an explicit owner
contract. The runner must remain unscored until that integration is accepted.

The standalone `SpatialController` has observation cues, but it is not wired to
the full-battle paid ledger/termination path. This search deliberately does not
splice a second ledger around it.

## Modes and crafted defenses

Ranked context explicitly requires `Legend I` and `legend_i`. War/CWL are separate
contexts with the `none` modifier profile. Friendly experiments may select an
explicit profile. The manifest's profile must match its complete battle modifier
policy, and the actual engine application ledger is preserved in results. Profile
data and all input policies participate in the cache identity; Town Hall never
selects a modifier profile implicitly. No existing account profile is rewritten.

Every opponent declares `crafted_status`: `selected`, `unknown`, or (only for
synthetic controls) `synthetic_omitted`. `selected` requires an active Station
with explicit variant, independent module levels and availability/rotation
policy. The existing paid compiler binds this selection to the actual crafted
weapon. It validates the official seasonal TH11+ eligibility and independent
module limits; July's announcement does not verify October rotation. Runtime
selection, availability and crafted launch/impact counts are retained.

A current opponent whose screenshot does not establish crafted identity/levels
is `unknown`, causing `opponent-crafted-identity-and-module-levels` to block scoring.
An empty Station is not active crafted coverage. Omitted synthetic crafted coverage
does not establish representative ranked-village performance.

Frozen baseline `3a814ec` also needs `crafted-role-profile-model-scaling-v1`:
Legend I scales Station `actor.damage` (zero) while leaving the separate crafted
weapon model unchanged. A neutral Cake-A-Pult fixture emits 195 damage at t=0.1
under both `none` and `legend_i`. Therefore selected crafted weapons with
nonneutral defense multipliers are blocked here. The owner must synchronize
crafted primary/projectile, explosion and poison models, source ownership guards
and audit receipts before this gate can be lifted. Neutral-profile full-battle
controls exercise Cake-A-Pult, Hero Hunter and Hot Candle at TH16 today.

## Reproducibility, bounds and failure semantics

The declared option order is deterministic. Each pair consumes one candidate
budget slot even if rejected. Limits are 32 candidates, 60 seconds per process
and 120 total configured worker seconds. The engine itself is deterministic;
wall timing and timeout occurrence depend on machine load. A timed-out prefix
is not an outcome. No retries or increased budgets are automatic.

The full SHA-256 cache identity includes source/runner contents, all files in the
selected data directory, runtime version/platform, mode context/rules, the full
expanded candidate and timeout. Working-copy edits invalidate identity without
depending on Git HEAD. Workers check code/data/runtime before and after evaluation;
the parent rechecks at completion. Only completed paid results are cached.
Cache writes are atomic and content hashes reject malformed/corrupt records.
All decoded worker receipts are validated before field access: root/status shape,
null objectives on unscored attempts, dependency/failure descriptions, completed
scenario identity, outcome/objective types and consistency, finite times and
required audit containers. Invalid JSON shapes (including a zero-exit worker
returning `[]`) become unscored failed rows; remaining candidates still run and a
final report is written. Completed cache reads use the same receipt validator.

Receipts preserve input manifest, expanded candidates, fingerprints, per-attempt
requests/results/logs, progress and final comparisons. `rejected`, `failed`,
`timeout` and `blocked_dependency` all carry `objective: null` and are excluded
from comparisons. They are never zeros or losses. Cache failures are reevaluated
within the same budget. No probabilities or scalar weighted fitness are emitted.
Elapsed time is reported separately; speed is compared only when both candidates
finish complete destruction, so early force exhaustion cannot score as fast.

## Evidence and future evaluation scope

The included 2×2 grid varies a paid synthetic roster and deployment time/position
against one underfilled Hall control. It proves resource admission, deterministic
selection, finite worker execution, outcomes and caching. It is not a plausible
army recommendation or a calibrated modern-village benchmark. Four acceptance
methods cover this control, invalid admission/hash boundaries, cue/funnel/crafted
gates and three active seasonal crafted variants. Existing domain tests continue
to own targeting, melting, lifecycle and projectile semantics.

The difficult base illustration contributes no weights, calibration observations
or generated-defense template here. Future scenario manifests should span varied
layouts, attack styles and entry directions, with held-out cases identified
before selection. Keep TH16 attacking mostly TH18 and defense versus mostly
TH17/18 as explicit user context; qualitative prevalence is not a numerical
sampling distribution. War/CWL TH16–18 needs separate runs. Cross-scenario robust
optimization, representative inventories and whole-battle calibration remain
outside this small infrastructure acceptance. Recommendations remain empty.
