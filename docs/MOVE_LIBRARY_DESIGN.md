> Predecessor Python filenames and parity procedures in this document are
> historical provenance from `f04706c`. Deleted tools are not runnable; see
> [the current documentation](README.md) for native commands and remaining Python ports.

Build a **cited move library that compiles into the existing attack-program executor**, with Rust searching over move compositions. Keep two separate outputs: a prediction of ordinary human attacks and the strongest human-feasible attack discovered against each base.

The repository already supplies much of the foundation: editable programs, inventory and dependency validation, structural mutations, native evaluation, and learned-versus-cited labels. Extend those paths instead of introducing another battle engine. See [program.rs:26](../crates/clash-armysearch/src/program.rs), [program_mutate.rs:13](../crates/clash-armysearch/src/program_mutate.rs), and [program_validate.rs:411](../crates/clash-armysearch/src/program_validate.rs).

This is a read-only design. No files were edited, downloads made, or battles run. References into the three F14 executor files describe the read-time snapshot.

**1. Move schema and extraction**

A move should represent a human technique with a defined purpose and evidence-supported application. It may expand into several inputs, but every input must pass through the human scheduler.

Use two records:

- **`MoveDefinition`**: immutable, versioned technique, evidence, supported parameters, requirements, and lowering rules.
- **`MoveInstance`**: a particular use within an attack, including actors, objectives, placement, trigger, dependencies, and reserved resources.

| Field | Concrete contents |
|---|---|
| Identity | `move_id`, schema version, definition version, human-readable name |
| Purpose | Intended job: clear shoulder, protect charge, breach wall, suppress compartment, finish cleanup |
| Actor bindings | Specific hero, troop cohort, siege, equipment, pet; distinguish original troops, cargo, clones, and summoned units |
| Applicability | Attacker TH, mode, patch/catalog identity, owned and donated availability, required loadout |
| Resource requirements | Troop counts, spells by origin, ability uses, Recall capacity, siege release; conditional reservations |
| Static preconditions | Required equipment equipped, sufficient inventory, legal deployment action, supported mechanics |
| Live preconditions | Observed actor alive, objective available, required support present, useful coverage, time remaining |
| Parameters | Counts, deployment side/arc, formation, spread, placement offset, objective selector, trigger threshold, deadline |
| Control | `when`, predecessor IDs, repeat limit, interrupt policy, timeout, explicit failure branch |
| Completion | Observable event defining completion; separate successful completion from cancellation |
| Evidence | Source file and JSON pointer, video ID/time, exact verified quote, usage-research references, distinct-video support |
| Evidence scope | Which claims are supported: actor, purpose, order, geometry, timing; measured versus inferred versus assumed |
| Human costs | Lowered input sequence, slots used, taps/hold duration, gesture path, attention region, observation requirements |
| Mechanic dependencies | IDs referring to unresolved mechanics and gap-triage findings |
| Attribution | Exact cited sequence, parameter adaptation, novel composition, real-play validation status |

Do not let a search parameter change human reaction speed, precision, or input rate. Those belong to the evaluation profile.

Extend the existing validation rather than weakening it. It already checks inventories, references, dependency cycles, equipment, spell origins, and single-use abilities. Add registered-move membership, evidence scope, observation permissions, reservations, and failure-path resource accounting. See [program_validate.rs:553](../crates/clash-armysearch/src/program_validate.rs).

A particularly useful addition is **persistent objective binding**. “Remove this X-Bow” should retain that building’s identity; repeatedly resolving `building:xbow` can silently change the objective. The current nearest-building behavior is at [playbook.py:371](../src/baselab/engine/playbook.py:371); this is also gap-triage B1, alongside missing funnel, effect, coverage, and cohort predicates at [gap-triage.md:30](../local/research/gap-triage.md:30).

**Library size and extraction plan.** My read-time inventory, excluding `test-stealth-rr.json`, found:

- 11 production families and 80 variants.
- 271 default steps, 325 variant steps, and 3 spell-support rules: **599 step occurrences**.
- 104 base-reading rules.

Those occurrences are not 599 distinct techniques. I would start with **32 move-template families**, then publish the actual semantic count after reviewing the mappings:

| Area | Proposed templates |
|---|---|
| Funnel/access — 7 | Cheap shoulder clearing; isolated heavy funnel; hero perimeter walk; exposed-defense snipe; directed breach; Siege Barracks flank; Flame Flinger section clear |
| Charge/reuse — 6 | Queen–Healer charge; Warden–Healer walk; protected RC charge; Duke dive; Recall extraction; redeployment/transfer |
| Surgical removal — 5 | Giant Arrow line; Backpack setup/dash; Fireball setup; Zap–Quake package; siege-payload delivery |
| Main deployment — 5 | Ground tank/damage push; air deployment line; Hound–Balloon sector; healing-support wave; defending-unit counter deployment |
| Support/endgame — 9 | Rage/Haste window; Freeze intervention; Poison response; decoy placement; Overgrowth routing; protected Revive; equipment activation window; safe cleanup; funnel repair |

This is a proposed starting taxonomy, not a completed extraction result. Some templates will split when their preconditions or choreography differ materially.

Extract in four passes:

1. **Index every source occurrence.** Preserve default, variant, support, and base-reading provenance. Deduplicate repeated citations by video, not by JSON occurrence.
2. **Separate technique from incidental roster.** Extract purpose, actor requirements, prerequisites, and dependencies. Remove family membership as an execution restriction.
3. **Review against usage research.** Build an actor-to-supported-role matrix for every troop, spell, hero, pet, and equipment item. This enables arbitrary legal armies without assuming every troop is interchangeable.
4. **Lower and verify.** Every occurrence must map to a move, an explicitly unsupported capability, or a documented ambiguity. Reconstruct the original sequence before enabling recombination.

The existing source rules require citations to describe the actual use and prohibit invented timing; retain that standard. See [playbook-consolidation.md:60](playbook-consolidation.md:60) and [playbook-completion.md:53](playbook-completion.md:53).

Concrete examples:

| Move | Requirements and parameters | Evidence |
|---|---|---|
| Protect an advancing RC | Bind the actual RC; select a leading spell circle; account for current protection and Fox survival. A ten-second cycle requires its supporting conditions. | [root-rider.json:199](../data/source/playbooks/root-rider.json:199), [redteam.py:345](../src/baselab/redteam.py:345) |
| Recall a charge | Reserve Recall; check eligible actors and capacity; choose extraction deadline and redeployment job. Failed charge must take an explicit recovery branch. | [root-rider.json:284](../data/source/playbooks/root-rider.json:284) |
| Protected Fireball setup | Require Fireball equipment; prepare its real automatic target through deployment and masking; serialize protection and activation inputs. | [fireball-warden.json:350](../data/source/playbooks/fireball-warden.json:350) |
| Sustain a Queen charge | Place Rage to cover the Healers and useful Queen movement; monitor the two formations separately. | [queen-charge-queen-walk.md:17](../local/research/usage/queen-charge-queen-walk.md:17) |

A move’s objective must never become direct control over autonomous troop targeting. The Queen research explicitly distinguishes funneling from selecting her target at [queen-charge-queen-walk.md:15](../local/research/usage/queen-charge-queen-walk.md:15).

**2. Human limits and executor enforcement**

The executor already has substantial pacing support: `PACE_TAP=0.133`, `PACE_SWITCH=0.6`, `PACE_ABILITY=0.3`, a shared busy deadline, and staggered troop drops. Therefore this work should consolidate and extend existing enforcement. See [playbook.py:52](../src/baselab/engine/playbook.py:52), [playbook.py:743](../src/baselab/engine/playbook.py:743), and [playbook.rs:2428](../crates/clash-engine/src/playbook.rs).

| Quantity | Available evidence | Treatment |
|---|---|---|
| Held troop deployment | 0.133 s/unit; 20 intervals, three samples, two players | Measured default |
| Same-slot spells | 0.133 s held; approximately 0.17 s tapped; two samples | Preserve gesture distinction; limited evidence |
| Slot switching | Existing 0.6 s | Assumption needing measurement |
| Ability input | Existing 0.3 s | Assumption needing measurement |
| Reaction delay | No measurement established here | New explicit parameter |
| Placement precision | Existing jitter is not a measured human distribution | Measure against intended placements |
| Attention switching, gesture travel, errors | No measurements established here | Explicit hypotheses; sensitivity testing |

The deployment measurements and limitations are documented at [VIDEO_MEASUREMENTS.md:26](VIDEO_MEASUREMENTS.md:26). Do not accelerate held deployment below the observed cadence merely to represent an expert.

Implement one shared `HumanController` in the executor path:

1. **Observe.** Expose public layout, own inventory, visible actors/effects, approximate health, and observed events through an `ObservationView`. Search policies cannot inspect raw `Battle`.
2. **Attend.** Track the current region/cohort. Monitoring the charge and then the opposite flank takes time. HUD information can have a separate, explicitly defined visibility rule.
3. **Recognize.** A reactive trigger becomes actionable after observation and reaction delay. Planned clock-based actions do not incur a fresh recognition delay each time.
4. **Queue.** Select one eligible action using fixed priorities and deadlines. No parallel spell, ability, troop, fallback, or rescue execution.
5. **Execute.** Spend slot-selection/gesture time before the relevant input; emit individual troop drops at the permitted cadence. Permit interruption of a hold, with corresponding costs.
6. **Recheck.** At execution, confirm the actor, inventory, target, and coverage remain valid. Expired opportunities take a logged failure branch.

For a reactive action:

```text
recognition_ready = observed_trigger_time + reaction_delay
input_start       = max(recognition_ready, hands_free_time)
first_input       = input_start + selection_and_gesture_cost
```

Subsequent held drops occur at `first_input + i × 0.133 s`. Define completion and release costs explicitly so the first drop, busy period, and successor timing agree.

Every action source must use this controller, including spell support, emergency abilities, late deployments, CC release, Recall, and automatic recovery. Current rescue paths are visible at [playbook.py:1403](../src/baselab/engine/playbook.py:1403).

Keep **input costs** separate from **tactical waiting**. The existing 4.5-second within-group and 16.6-second between-group gaps are population timing priors, not reaction-time measurements. Retain them for legacy reconstruction; replace them in extracted moves with supported events or explicitly marked timing priors. Avoid charging both mechanisms for the same delay. See [playbook.py:2180](../src/baselab/engine/playbook.py:2180).

For an initial experimental profile, retain the existing 0.6-second switch and 0.3-second ability assumptions. Sweep reaction delay around 0.2–0.6 seconds and placement error around 0.25–1 tile. These are **proposed sensitivity ranges**, not calibrated human measurements.

The optional error model should sample a persistent player profile per battle, then correlated errors: delayed recognition, a displaced placement, or an omitted action. Do not sample errors repeatedly until a favorable outcome appears.

Finally, distinguish this from existing “skill”: `evaluate.skill()` currently scales army strength. Preserve that legacy control for comparisons, but introduce human execution skill separately; compare strength-only, execution-only, and combined models before recalibration. See [evaluate.py:178](../src/baselab/evaluate.py:178).

**3. Search, budgets, and integration**

**Representation.** Keep `ArmyGenome` for composition/loadout, and add a versioned move program to `PlanGenes`. Represent it as an ordered list with dependency edges, bounded repeats, named objectives/cohorts, and explicit recovery branches. Start with at most 64 move instances and retain the existing 256-step limit after lowering.

Compile into the normal `PlaybookPlan` path; installation already does this at [program.rs:568](../crates/clash-armysearch/src/program.rs). Rust owns the reference compiler, executor and optimization. Python is frozen at `python-frozen`.

**Operators.** Reuse the current add/delete/anchor/trigger/count/group/swap/split/aim machinery, but operate on registered moves and typed bindings:

- Insert or remove a move with resource validation.
- Change actor, side, objective, count, formation, threshold, or timing within supported bounds.
- Split a deployment or move a reserve into another phase.
- Exchange two independent moves.
- Replace an opening or support package with another applicable package.
- Crossover dependency-complete subgraphs, renaming IDs and preserving resource ownership.

Do not repair invalid offspring by silently inventing a different technique. Existing crossover already rejects duplicate IDs and overspending; preserve that transparency. See [program_mutate.rs:517](../crates/clash-armysearch/src/program_mutate.rs).

Use playbooks as seeds and proposal priors. Source support should affect sampling frequency, not eligibility or claimed population usage. Change archive diversity descriptors from family alone to opening technique, main troop mix, attack domain, entry geometry, and attention demand; current cells remain family/hero based at [genome.rs:220](../crates/clash-armysearch/src/genome.rs).

**Three search scopes.**

| Scope | Variables | Appropriate use |
|---|---|---|
| Fixed army, one base | Move composition, sides, timing, objectives | User’s army against a particular base |
| Joint army/attack, one base | Composition, spells, CC, heroes/loadout, move program | Strongest discovered attack against a base |
| Army across bases | Army plus a bounded base-specific adaptation procedure | Find armies that transfer to unseen bases |

For army search, score **army + adaptation budget**, not an army with unlimited private tuning. Use lineage-separated training and held-out bases; the manifest already rejects cross-split lineage and duplicate-layout leakage at [score.rs:98](../crates/clash-armysearch/src/score.rs).

The existing red team provides a useful template: common-seed screening, successive halving, refinement, and fresh-seed reporting. It currently tunes inside a cited playbook rather than composing techniques. See [redteam.py:27](../src/baselab/redteam.py:27).

**Concrete starting budgets.** Using the supplied **50 total battles/s on 16 cores**:

| Fixed-army/per-base phase | Battles |
|---|---:|
| 128 initial programs × 5 common scenarios | 640 |
| 8 waves × 64 offspring × 5 scenarios | 2,560 |
| 32 survivors × 20 confirmation scenarios | 640 |
| 8 finalists × 3 human profiles × 20 seeds | 480 |
| Frozen winner × 100 fresh scenarios | 100 |
| **Total** | **4,420 ≈ 88 seconds of battle time** |

These are conservative counts before cache reuse and exclude orchestration overhead. Define the scenario’s profile explicitly; do not accidentally multiply every row by five legacy skill quantiles.

Suggested caps:

- Fixed-army tuning: approximately **4,500 battles / 90 seconds**.
- Joint army/attack search: **30,000 battles / 10 minutes per base**.
- Ten base finalists: **300,000 battles / 100 minutes**.
- Eight-hour theoretical capacity: **1.44 million battles**; reserve some capacity for confirmation and diagnostics.

For global army search, screening 256 armies on eight bases with five scenarios costs 10,240 battles. The expensive part is inner adaptation: eight finalists × sixteen bases × 4,420 battles costs about 566,000 battles, or 3.1 hours. Transfer cached programs and staged budgets are therefore essential.

Use common random scenarios during selection, independent confirmation scenarios, and untouched final scenarios. Select the program before final evaluation; do not choose a different program or angle after seeing each final seed. The current native search already separates quick and confirmation stages at [search.rs:421](../crates/clash-armysearch/src/search.rs).

**Caching and surrogates.**

Extend the native compiled-plan cache with persistent keys covering:

```text
engine + catalog/patch + full physical layout + public knowledge
+ account/loadout + mode/modifier + move-library/compiler version
+ compiled program + human profile + physics/error/hidden-state seeds
```

The current cache binds account/catalog/layout/options to evaluator lifetime and stores the compiled plan in its key; persistent storage needs those implicit bindings made explicit. See [eval.rs:29](../crates/clash-armysearch/src/eval.rs).

Cache three levels: validated/lowered programs, prepared immutable battle inputs, and completed outcomes. Do not share mutable battle state.

Use surrogates to prioritize candidates, not certify winners. Keep an exploration quota and log prediction residuals. `funnel.py` already reserves random explorers during surrogate screening at [funnel.py:332](../tools/baselab/funnel.py:332). Train attack surrogates on base/program/profile features and keep simulated outcomes clearly distinguished from real-play observations.

**Base scoring.** Publish two results:

```text
Meta defense score = Σ meta_weight × E[defender result | ordinary playbook policy]

Discovered attack report =
    fresh evaluation of the strongest program selected during search
```

Keep the meta-weighted playbook score as the population-facing score. Attach the discovered program, star/destruction distribution, confidence interval, skill sensitivity, evidence status, mechanic risks, and search budget.

Use the discovered result as a finalist robustness gate or Pareto dimension. Do not assign a novel composition a population frequency based on its simulated success. Feed validated discoveries into the reusable attack archive so future base candidates face them cheaply.

This fits the existing quick/confirm archive pipeline and finalist red-team hook in qd_search.py:449 (historical `tools/baselab/qd_search.py` at `f04706c`) and [funnel.py:149](../tools/baselab/funnel.py:149).

RW1 carries the manifest's ranked modifier through native scenarios/jobs, cache
identity, replays and reports. Admission supports data-derived TH16–18 capacities;
`--account FILE` selects an account, while the user's TH16 snapshot stays default.
Explicit CC reservations and donation availability remain separate milestones.

**4. Safeguards against simulator exploitation**

Cited moves constrain behavior; they cannot establish that the simulator implements those moves correctly.

1. **Separate move evidence from composition evidence.** Label outputs as exact cited sequence, adapted cited sequence, novel composition of cited moves, and subsequently tested in real play. The existing conservative learned label is a useful starting point at [program.rs:662](../crates/clash-armysearch/src/program.rs).

2. **Prevent citation laundering.** Require every instance’s actor and role to fall within its evidence scope. “Use Freeze” does not support every target or cadence. Usage-research frequency labels are sampled evidence, not measured population shares; see [queen-charge-queen-walk.md:53](../local/research/usage/queen-charge-queen-walk.md:53).

3. **Make citation-dependent execution explicit.** Citation text currently influences aiming and deployment, as documented in [program.rs:34](../crates/clash-armysearch/src/program.rs). Introduce explicit semantic fields through an equivalence-tested migration. Until then, citations remain part of executable identity.

4. **Enforce an information boundary throughout search.** An observation wrapper alone is insufficient: repeatedly optimizing against one fixed hidden-trap layout can reveal its secrets through outcomes. Search against plausible hidden-state ensembles consistent with public scouting. Evaluate the actual hidden layout after freezing the attack. Legitimate prior-attack knowledge must be separately declared; gap-triage already distinguishes known positions from physical reveal at [gap-triage-addendum.md:84](../local/research/gap-triage-addendum.md:84).

5. **Require robustness.** Test fresh seeds, ordinary/expert execution profiles, nearby placement perturbations, and timing shifts. Report brittle wins separately. Evaluate expected attack quality and failure tails rather than the luckiest run.

6. **Track disputed mechanics dynamically.** Definitions declare dependencies; traces record which affected the result. Flag sensitivity to Invisibility landing/coverage, Healer allocation, Spring radius, defense wind-up/projectiles, Freeze boundaries, Blimp emergence, Torch speed, and TH18 Guardian interactions. These are documented in [BUG_LEDGER.md:293](history/BUG_LEDGER.md:293) and [gap-triage.md:13](../local/research/gap-triage.md:13). Reconcile each finding against the current build before treating it as open or fixed.

7. **Challenge suspicious improvements.** If a win disappears under modest human perturbation or a plausible unresolved-mechanic hypothesis, label it mechanic-sensitive. Hypothesis runs are declared sensitivity experiments, never real calibration. Preserve unsupported-content errors and quarantine affected claims rather than silently substituting behavior.

**5. Validation with real play and fidelity measurements**

Use a paired loop:

1. Freeze the base, army/loadout, patch, mode, human profile, and proposed program.
2. Produce a readable attack card with placement diagrams, cues, reserves, and failure branches.
3. The user attempts it in friendly challenges; record actual execution and outcome.
4. Replay the **observed inputs** to test mechanics separately from the planner.
5. Compare prescribed versus actual inputs to test feasibility.
6. Diagnose whether a mismatch arose from execution, policy, mechanics, or missing information; promote evidence only at the level demonstrated.

Record drop/ability times, placements, selected slots, target choices, HP/coverage events, destruction curves, troop survival, and end reason. Keep replay media and personal data outside Git. A successful friendly challenge supports that composition on those conditions; it does not establish a population success rate.

Maintain three evaluation tracks:

- **Execution fidelity:** deployment-interval, switching, reaction, placement, concurrency, and omitted-action distributions.
- **Mechanics fidelity:** observed-input replay destruction curves, milestone times, targeting, survival, and termination.
- **Predictive usefulness:** unseen real outcomes, base ordering, and army transfer after a fixed adaptation budget.

**Check A must use the playbook attacker.** Reuse the cv2 method: fit each fold from the declared unfitted prior using training battles, exclude fitted battles and calibration ancestry, evaluate its held-out battles, and pool results. See [cv2/run.sh:2](../local/evidence/overnight/cv2/run.sh:2) and fidelity_board.py:267 (historical `tools/baselab/fidelity_board.py` at `f04706c`).

The archived cv2 playbook-mode baseline is:

| Metric | Archived result |
|---|---:|
| Held-out defenses | 22 |
| Real / simulated triple rate | 68.2% / 50.3% |
| Brier / constant-predictor Brier | 0.249 / 0.217 |
| Destruction MAE | 8.877 points |
| Triple completion-time ratio | 0.94 |

These are archived results, not measurements of the concurrent F14 fixes. Also, the report contains **20 playbook and two generic cases**, so preserve explicit attacker/fallback accounting. Sources: [pooled-playbook.json:2](../local/evidence/overnight/cv2/pooled-playbook.json:2) and [pooled-playbook.json:47](../local/evidence/overnight/cv2/pooled-playbook.json:47).

Judge improvement using paired out-of-fold predictions:

- Brier below the constant baseline, with uncertainty estimated over real battles.
- Lower destruction MAE; retain the project target below four points.
- Completion-time ratio within 0.85–1.15.
- Failed-attack duration on the **same real failed defenses**, plus end-reason distributions.
- At least 40 real defenses before treating the established project gate as adequately populated.

These targets come from [SIM_ACCURACY.md:13](SIM_ACCURACY.md:13). The current board implements matched failure-duration accounting at fidelity_board.py:78 (historical `tools/baselab/fidelity_board.py` at `f04706c`); the old cv2 pooling helper should be updated to retain that field.

**TH18 replay diagnostic.** The saved report’s playbook predictions average 0.84, 0.93, 0.97, and 1.19 scouted stars against the user’s **1/2/2/3** results, with no predicted triples on the fourth base. See [th18_replay_check.txt:2](../local/evidence/rescore/th18_replay_check.txt:2).

The script evaluates the user’s **TH16 army against TH18 bases**. Its 400 simulations per base arise from eight sides × ten seeds × five skill quantiles; preserve that accounting. See [th18_replay_check.py:18](../local/evidence/rescore/th18_replay_check.py:18) and [evaluate.py:207](../src/baselab/evaluate.py:207).

Rerun the unchanged diagnostic after F14, then compare the human scheduler and move attacker under matched conditions. Report probabilities for the observed stars, available destruction error, and TH-kill probability. Four outcomes cannot identify a skill distribution. Because these cases already inform development, reserve subsequent real attacks for prospective validation.

A stronger searched attacker alone does not demonstrate improved fidelity. Ordinary-human prediction and adversarial vulnerability discovery must be evaluated separately.

**6. Staged Rust implementation and proof gates**

| Milestone | Implementation | Required gate |
|---|---|---|
| **M0 — Freeze F14 baseline** | Coordinate with the writer; record engine/catalog/configuration identity and rerun current diagnostics | Demonstrate the failure/recovery invariants exposed by d3; archive post-fix check A and TH18 results |
| **M1 — Move registry** | Proposed `rust/src/moves/{schema,library,validate,lower}.rs`; extract source mappings and role matrix | Every source occurrence mapped or explicitly unresolved; exact citations retained; original programs reconstruct |
| **M2 — Human controller** | Shared observation, attention, queue, input scheduling, and error semantics in the Rust reference runtime | No overlapping inputs; correct held cadence; reactive delay enforced; fallback and rescue use the same controller |
| **M3 — Missing vocabulary** | Persistent objectives/cohorts, effect events, funnel predicates, constrained circles, payload and named-Revive identity | Focused declared-synthetic proofs, compiled-plan agreement, and Rust golden trace/outcome checks |
| **M4 — Search correctness** | Move operators, modifier propagation, account-derived TH16–18 rules, explicit CC reservations, versioned cache/checkpoints | Reject unsupported combinations; cold/warm cache and restart equivalence; deterministic results across worker counts |
| **M5 — Bounded attack search** | Fixed-army tuning, joint search, diverse archive, racing, fresh-seed reports | At equal battle budgets, outperform existing red-team tuning on held-out synthetic/reference targets; publish sensitivity and mechanic flags |
| **M6 — Scoring integration** | Preserve meta score; add discovered-attack report and finalist gate; reuse attacks against later base candidates | Correct score weights/signs, no duplicate scouting advantage, no final-seed selection leakage |
| **M7 — Real validation** | Friendly-challenge records, observed-input replay, prospective checks | Human feasibility demonstrated; improved out-of-fold fidelity; base/army recommendations supported beyond simulation |

F14’s ownership remains with the current writer. Use its diagnostic as a regression specification: charge failure must not discard unused heroes; main support must wait for the actual push; dependent deployment must recover without waiting for its prerequisite troop’s death. Those failures are documented at [d3.out:34](../local/evidence/fidelity/diag/d3.out:34), [d3.out:77](../local/evidence/fidelity/diag/d3.out:77), and [d3.out:94](../local/evidence/fidelity/diag/d3.out:94).

Rust is the executable reference; Python is frozen at `python-frozen`. Executor
changes must pass the Rust golden suite's per-tick traces, outcomes and RNG
ordering, or explicitly review and re-record intended changes. Mathematical
operations use the platform-identical implementations in `crates/clash-engine/src/detmath.rs`
and `geom.rs`; see [RUST_PORT.md](RUST_PORT.md). Give human errors a separately
specified deterministic stream, preserving existing RNG consumption.

Extend the existing program proofs rather than replacing them: they already cover identity, invalid programs, native execution, mutation, and worker-count determinism at [program_proof.rs:427](../crates/clash-armysearch/src/program_proof.rs). Apply `cargo fmt`, run the native proofs and the Rust golden gate before production base searches. Do not edit frozen Python.
