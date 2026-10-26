> Predecessor Python filenames and parity procedures in this document are
> historical provenance from `f04706c`. Deleted tools are not runnable; see
> [the current documentation](README.md) for native commands and remaining Python ports.

Build this as a Rust layout library plus a Rust base-search coordinator, reusing the existing compiler, scorer, runner, and army-search types.

This design reflects checkout `0d64a07`. I made no edits, downloads, builds, or battle runs. Python remains frozen at `python-frozen`; its layout verdicts can provide limited compatibility evidence, while Rust goldens remain the engine regression gate. [GOLDEN.md:3](GOLDEN.md:3)

**1. Module map and data model**

Use two namespaces: `layout` owns physical layouts and admission; `basesearch` owns proposals, evaluation schedules, archives, and reports.

| Frozen Python source | Proposed Rust home | Keep / redesign / drop |
|---|---|---|
| `layout.py` | `layout/{model,json,rules,admit}.rs` | Keep JSON compatibility; introduce typed placements, issues, and explicit admission policies. |
| `deploy.py` | `layout/geometry.rs` | Keep deploy masks, outside regions, connected holes, and eight-way flood semantics. |
| `archetypes.py` | `basesearch/generate.rs` | Keep wall-first generation; replace TH16-specific placement lists with TH-aware rules. |
| `macro_moves.py` | `basesearch/operators/macro_ops.rs` | Keep design-scale proposals and their descriptions; make applicability explicit. |
| `optimize.py` | `basesearch/{operators,repair,anneal}.rs` | Keep local, wall, setup, and guided proposals; preserve levels and inventory through every operation. |
| `evaluate.py` | Existing `scoring.rs`, with `basesearch/eval.rs` adapter | Reuse scenarios, summaries, trophies, and objective. Do not create competing scoring implementations. |
| `redteam.py` | `basesearch/oracle.rs` | Keep bounded screening/refinement/fresh evaluation; replace pointwise ordinary/red-team outcome selection with separate reports. |
| `qd_search.py` | `basesearch/{archive,search,race}.rs` | Keep MAP-Elites and quick/confirm admission; redesign descriptors, allocation, and persistence. |
| `funnel.py` | `basesearch/{eval,race}.rs` | Keep batched evaluation and staged screening. Defer surrogate training/inference. |
| `evolve_bases.py` | Same search coordinator, configurable emitters | Avoid a second evolutionary implementation with separate accounting and checkpoint semantics. |
| `explain_base.py` | `basesearch/{diagnostics,report,render}.rs` | Keep paired comparisons, interventions, and representative traces; run everything through Rust. |

The dependency closure also includes `generator.py`, `unconventional.py`, `evolve.py`, and `diagnose.py`: current QD directly imports their packing, unconventional generation, crossover, and diagnostics. qd_search.py:45 (historical `tools/baselab/qd_search.py` at `f04706c`), [evolve.py:49](../src/baselab/evolve.py:49)

Proposed structures:

| Type | Contents and invariants |
|---|---|
| `Layout` | TH, buildings, walls, traps, defensive CC, hero-to-banner assignments, guardian, levels, descriptive metadata. |
| `BuildingPlacement` | Stable instance ID, catalog building key, integral tile origin, typed mode. Footprint comes from rules. |
| `TrapPlacement` | Stable ID, trap key, integral origin, typed skeleton mode. |
| `WallPiece` | Stable ID, coordinate, effective level. Moving a wall moves its level with it. |
| `DefenseSetup` | Building/trap levels, ordered CC entries with optional donated levels, defending heroes and their levels, guardian. |
| `BaseRules` | Patch/version identity, footprints, TH inventories, merge recipes, mode unlocks, level limits, capacities, optional seasonal content. |
| `AdmissionReport` | Structured issues: code, JSON path, instance IDs, coordinates, expected/actual values. |
| `AdmittedLayout` | Immutable validated layout plus resolved rules/account identity. Search evaluation accepts this type. |
| `SearchConfig` | Objective, battle mode/modifier, inventory policy, hole policy, scenario manifests, budgets, operators, archive definitions. |

Preserve legacy JSON fields, including `wall_level` plus per-position `wall_levels`. Import the ordered hero list as explicit banner bindings: runtime currently zips heroes with banners in building order. Preserve building/trap order when exporting to the engine because IDs, ties, and execution order can be observable. Exclude names and notes from physical identity. [layout.py:64](../src/baselab/layout.py:64), [setup.rs:539](../crates/clash-engine/src/setup.rs), [setup.rs:592](../crates/clash-engine/src/setup.rs)

Keep account levels fixed during layout optimization. CC composition, hero selection/banner assignment, defense modes, and guardian choice are legitimate search variables; upgrading equipment or buildings is a separate task.

For inventory, derive a tracked normalized `data/generated/base_rules.json` using a **Rust-only importer**:

- Accumulate Town Hall unlock quantities.
- Consume source buildings according to actual merge recipes.
- Apply explicit, cited seasonal/model overrides.
- Resolve owned counts and levels from a supplied account snapshot, or use a clearly labelled fully merged TH preset.

The local data already contains unlock quantities and merge requirements, including geared AT+Cannon→MGT. `Catalog::BuildingType.count` alone is insufficient for TH-specific inventories. [clashking-static-data.json:969](../data/source/clashking-static-data.json:969), [clashking-static-data.json:1041](../data/source/clashking-static-data.json:1041), [clashking-static-data.json:9921](../data/source/clashking-static-data.json:9921), [catalog.rs:219](../crates/clash-data/src/catalog.rs)

**2. Legality and admission**

Separate three questions:

1. **Content:** can the engine represent this content and configuration?
2. **Physical/inventory legality:** is this a valid complete or partial layout?
3. **Search policy:** does it satisfy this run’s restrictions, such as zero deploy holes?

`require_full=false` should waive missing inventory only. It must not waive overlaps, coordinate errors, unsupported content, or illegal modes.

Port every existing `Layout.problems()` / `content_problems()` check:

| Check | Required Rust behavior |
|---|---|
| Coordinates | Reject booleans, strings, fractions, nonfinite numbers, and overflowing values before conversion. Accept integral JSON numbers such as `4.0`. |
| Bounds and overlap | Check every footprint tile of buildings, walls, and traps against the village and all other placements. |
| Buildings | Enforce TH-specific maximum counts; require nonoptional inventory in full mode. |
| Walls | Enforce maximum count; reject level overrides without a corresponding wall. Preserve the distinction between maximum wall count and a search requirement to place every owned wall. |
| Traps | Enforce each TH’s trap limits and required counts in full mode. |
| Gear-ups | At most one geared Cannon, Archer Tower, and Mortar; recognize existing `geared`/`fast`/`burst` aliases. Reject geared AT alongside MGT at TH17+. |
| Heroes | Reject unknown and duplicate defending heroes. |
| Firespitters | Only N/E/S/W; preserve the existing default facing. |
| Spell Towers | Rage L1, Poison L2, Invisibility L3, Earthquake L4; Earthquake also requires TH17+. Retain supported Earthquake aliases on import. |

Sources: [layout.py:170](../src/baselab/layout.py:170), [layout.py:232](../src/baselab/layout.py:232), [defense.py:313](../src/baselab/engine/defense.py:313).

Add production admission checks that are currently scattered through setup/operators:

- Known building/trap keys and supported modes.
- Valid selected levels and TH availability.
- Hero Hall unlocks, defensive slots, and banner capacity.
- Defensive CC housing, donation eligibility, and receiving caps.
- Gear availability and minimum home-building level.
- Guardian availability and supported seasonal/crafting configuration.

Existing implementations provide the semantics to consolidate. [setup.rs:332](../crates/clash-engine/src/setup.rs), [setup.rs:616](../crates/clash-engine/src/setup.rs), [optimize.py:675](../src/baselab/optimize.py:675), [optimize.py:816](../src/baselab/optimize.py:816)

Expose the shared content checks to direct engine setup as fallible admission, preserving `ContentError::Unsupported`. Full inventory requirements belong to production search admission; small declared synthetic battle fixtures must remain usable. Existing setup already checks several F7–F13 cases, but uses assertions for layout errors. [content.rs:16](../crates/clash-data/src/content.rs), [setup.rs:369](../crates/clash-engine/src/setup.rs), [setup.rs:1380](../crates/clash-engine/src/setup.rs)

Connectivity needs **three explicit operations**:

- Deploy masks: expand visible buildings and walls by one tile; Teslas and traps create no no-deploy zone.
- Drop holes and wall-only compartments: eight-way flooding, matching frozen Python.
- Runtime navigation: existing half-tile grid, eight neighbors, with building-hitbox corner restrictions; walls do not block diagonal corners.

Disconnected wall groups and open bases are legal. Deploy holes are a selectable constraint or penalty, rather than a universal legality error. [deploy.py:22](../src/baselab/deploy.py:22), [deploy.py:58](../src/baselab/deploy.py:58), [grid.rs:484](../crates/clash-engine/src/grid.rs)

**Fix the existing Rust hole counter during this stage:** it currently floods four ways. Route `scoring::hole_tiles` through the shared eight-way geometry implementation and review changed scoring fixtures explicitly. [scoring.rs:1405](../crates/clash-scoring/src/scoring.rs)

**3. Generators, mutations, and repair**

Start with imported admitted layouts and simple operators, then add original generation.

- **Generators:** grid, offset, rings, wide, binary-split freeform, organic/Voronoi; then cram, onion, and scatter. Use one packing board and inventory resolver. Include explicit central/mid/edge TH sampling.
- **Local operators:** same-footprint swaps, nudges, long relocations, trap relocation, mode/facing changes, skeleton air/ground, hero/banner permutations, CC packages, guardian changes.
- **Wall operators:** single-piece relocation, run shifts, compartment split/merge rewiring, TH rings, and seam closure.
- **Macro operators:** role repacking, strongest defenses inward, splash placement, AD/Fireball spread, outer screening, core rotation, core/flank exchange.
- **Guided operators:** traps onto traffic, quiet defenses into busy regions, early-lost defenses deeper, reinforcement behind observed breaches.
- **Crossover:** spatial cut, repair seam conflicts, restore inventory near parental positions, preserve ownership/levels, then admit.

These correspond to existing working operator families. [archetypes.py:326](../src/baselab/archetypes.py:326), [optimize.py:207](../src/baselab/optimize.py:207), [optimize.py:361](../src/baselab/optimize.py:361), macro_moves.py:838 (historical `src/baselab/macro_moves.py` at `f04706c`)

Use transactional proposals:

`parent → proposed edit → bounded repair → admission → candidate or typed rejection`

Each accepted proposal records its operator, changed instances, repair actions, and parent lineage. Preserve building/trap inventory and the **wall-level multiset**, not merely wall count. Failed repair leaves the parent unchanged.

Repair should be deterministic under its proposal seed: resolve seam conflicts, replace missing pieces, relocate displaced traps, restore wall pieces, repair illegal gear allocations, and optionally close holes. Unknown content or invalid imported levels should be rejected rather than silently replaced.

Redesign the TH16 role tables to cover MGT, Firespitters, SWT, and Revenge Towers. Also avoid copying `_orient_firespitters` verbatim: that older generator still selects among eight directions, conflicting with current admission. [archetypes.py:42](../src/baselab/archetypes.py:42), [generator.py:368](../src/baselab/generator.py:368)

Trap polishing becomes a bounded local-search phase after structural search: freeze buildings/walls, collect Rust diagnostics on development scenarios, reseat or mutate traps, confirm improvements independently, and invalidate diagnostics whenever their layout/policy identity changes. The existing traffic-class weighting is a useful starting point. macro_moves.py:723 (historical `src/baselab/macro_moves.py` at `f04706c`), [diagnose.py:108](../src/baselab/diagnose.py:108)

**4. Evaluation, racing, and budgets**

`basesearch::eval` should orchestrate existing Rust components:

1. Resolve explicit scoring data, account, modifier, policy, and scenario manifests.
2. Prepare native plans once where reusable.
3. Evaluate immutable inputs through `Runner`.
4. Use `Scorer::scout(..., Visible, ...)`.
5. Summarise committed outcomes with `scout=1`.
6. Apply the existing objective and separately report its deterministic layout penalty.

The CLI already demonstrates this sequence. Calling `summarise` with ordinary scouting again would reintroduce hindsight. [scoring_cli.rs:218](../crates/clash-cli/src/scoring_cli.rs), [scoring_cli.rs:236](../crates/clash-cli/src/scoring_cli.rs)

Keep raw expected defender trophies separate from the penalized search objective. Initially preserve the existing ranked and war formulas; add archive worst-case/CVaR metrics as explicitly versioned robustness dimensions. Set war’s attacker TH from the defender/run manifest: the current scorer’s default war mixture is TH16. [scoring.rs:908](../crates/clash-scoring/src/scoring.rs), [scoring.rs:1418](../crates/clash-scoring/src/scoring.rs)

Use common random numbers:

- Freeze army/profile draws, candidate sides, hidden-prior seeds, and execution seeds across compared bases.
- Keep proposal randomness separate from battle randomness.
- Pair results by immutable scenario-group ID.
- Preserve declared population weights regardless of simulation allocation.
- Keep all sides/techniques of a scouting group together.

The current Python race already preserves complete groups and fixed mixture weights; retain that principle, while replacing its approximate repeated-look bound. qd_search.py:146 (historical `tools/baselab/qd_search.py` at `f04706c`)

Recommended allocation:

- **Screen:** approximately 20 scored groups per candidate.
- **Confirm:** approximately 68 independent development groups.
- **Finalist gate:** 400+ groups, with additional archive attacks.
- **Final report:** untouched scenarios after winner/order selection is frozen.

Within proposal waves, use successive halving with nominal reduction factor three, protected cell-opening quotas, and exploration slots. Race against incumbents using paired group differences and an alpha-spending bounded interval. Sparse strata or insufficient replication mean “continue,” not zero uncertainty. Confirmation selects archive occupants, so its intervals remain selection-biased.

The review’s 20/68/400 guidance is appropriate, but **those counts must not hide visible-scouting costs**. [RUST_REVIEW_2026-10-25.md:243](history/RUST_REVIEW_2026-10-25.md:243)

A practical ordinary-policy group can sample one pair from the eight candidate sides, evaluate both against three hidden samples, commit, then execute once: **seven physical battles**. Sampling pairs integrates the existing two-side policy without enumerating all 28 pairs every time. Complete-grid integration remains available for diagnostics. The current visible scorer explicitly charges planning and execution separately. [SCOUTING.md:10](SCOUTING.md:10)

Illustrative conservative round, before cache savings:

| Work | Physical battles |
|---|---:|
| 2,000 bases × 20 groups × 7 | 280,000 |
| 200 promotions × 68 groups × 7 | 95,200 |
| Best-response searches: 10 × 4,420 | 44,200 |
| 30 finalists × 400 ordinary groups × 7 | 84,000 |
| 30 finalists × 8 frozen archive attacks × 100 executions | 24,000 |
| Frozen winner + reference: 400 fresh ordinary groups each × 7 | 5,600 |
| Same pair: 8 frozen attacks × 100 fresh executions | 1,600 |
| **Total** | **534,600** |

At **50–90 physical battles/s**, this is **99–178 minutes of battle time**, plus packing, compilation, persistence, diagnostics, and synchronization. Treat the attack-search 4,420 as an all-in physical budget: its scenarios already specify hidden samples/profiles; do not multiply them again by five skill quantiles. [MOVE_LIBRARY_DESIGN.md:154](MOVE_LIBRARY_DESIGN.md:154)

Twenty groups may be insufficient to cover a large weighted library. Report coverage, use valid sampling weights, and increase confirmation budgets when required floors do not fit. The existing proportional allocator can exceed a nominal budget through per-build side floors; the new allocator must preflight actual cost. [scoring.rs:1019](../crates/clash-scoring/src/scoring.rs)

Track logical comparisons, planning battles, execution battles, cache hits, and diagnostic battles separately. Reserve complete-group cost before dispatch. Use fixed logical budgets and wave boundaries for reproducibility; wall-clock limits can stop a run but should not govern scientific comparisons.

Cache validated/lowered plans, immutable prepared inputs, and outcomes. Keys must include engine/rules/catalog identity, effective layout and ordering, account, modifier, compiler/program, scouting knowledge, profiles, and seeds. Trap-only polishing can reuse planning results when public state is unchanged. Mutable battle state remains worker-local. [runner.rs:229](../crates/clash-engine/src/runner.rs), [MOVE_LIBRARY_DESIGN.md:178](MOVE_LIBRARY_DESIGN.md:178)

**5. Attack archive and double-oracle loop**

Maintain separate products:

- **Ordinary-meta defense estimate:** fixed population weights and ordinary execution policy.
- **Discovered-attack robustness:** strongest attacks found within a declared adaptation budget.

Do not infer population prevalence from searched success. This is the intended integration in the move-library design. [MOVE_LIBRARY_DESIGN.md:194](MOVE_LIBRARY_DESIGN.md:194)

An `AttackArchiveEntry` should contain:

- Army/account/loadout and executable program.
- Compiler/move-library version and evidence classification.
- Public-state adaptation procedure and budget.
- Knowledge policy, execution profile, TH/mode/modifier applicability.
- Discovery target lineage, seeds, cost, and fresh validation.
- Payoff signature, mechanic sensitivities, and provenance.

Use this loop:

1. Freeze attack archive version **Aᵣ**.
2. Search diverse bases against ordinary meta and Aᵣ.
3. Choose strong bases, diverse cells, and historical weaknesses as oracle targets.
4. Search bounded best-response attacks.
5. Freeze each proposed attack before fresh evaluation.
6. Add validated discoveries to **Aᵣ₊₁**.
7. Extend the empirical base×attack payoff matrix.
8. Re-evaluate affected elites before comparing scores under the new archive.

Keep a permanent hall of fame; an active subset may control cost, but old exploits remain available for scheduled replay. Never compare an incumbent scored under Aᵣ with a child scored under Aᵣ₊₁. This implements the review’s anti-cycling archive proposal. [RUST_REVIEW_2026-10-25.md:229](history/RUST_REVIEW_2026-10-25.md:229)

Plug in attacks through an `AttackOracle` interface:

| Adapter | Scope |
|---|---|
| Cited-playbook tuner | First implementation: fixed army, sides, variants, supported anchors/timing. |
| Native army-search adapter | Joint composition/loadout/program search, retaining native account legality. |
| Future move-library adapter | Registered move composition lowered into the existing program executor. |

Reuse `ArmyGenome`, `AttackProgram`, `AccountRules`, and native compilation. Avoid invoking the entire army-search CLI inside each base evaluation. Its current manifest requires search and holdout targets, and its evaluator/report uses oracle scouting; add an in-memory bounded-search adapter with visible-state training instead. Existing oracle results can seed proposals, but cannot certify feasible ranked attacks. [armysearch/score.rs:154](../crates/clash-armysearch/src/score.rs), [armysearch/eval.rs:98](../crates/clash-armysearch/src/eval.rs), [armysearch/report.rs:349](../crates/clash-armysearch/src/report.rs)

For ranked best responses, optimize against plausible hidden-state ensembles, then freeze before evaluating actual hidden content. Merely hiding traps from the program does not prevent repeated optimization from learning them through outcomes. War/prior-attack knowledge must be separately declared. [MOVE_LIBRARY_DESIGN.md:224](MOVE_LIBRARY_DESIGN.md:224)

For PSRO, compute approximate equilibrium mixtures on the restricted payoff matrix, partitioned by compatible TH/account/mode. A deterministic multiplicative-weights solver avoids introducing an external LP dependency initially. Publish its residual and restricted-game scope. Keep Nash-style robustness rankings separate from ordinary-meta trophy rankings.

Drop Python’s pointwise “better ordinary or red-team completed outcome” combination from the default metric: it grants outcome-dependent choice. Freeze a policy/program before fresh execution. Retain any such envelope only as a labelled upper-bound diagnostic. [redteam.py:659](../src/baselab/redteam.py:659)

**6. QD descriptors and checkpoints**

Replace the Eagle-depth descriptor immediately: current QD returns no cell without an Eagle, excluding the fully merged TH17–18 inventories. qd_search.py:82 (historical `tools/baselab/qd_search.py` at `f04706c`), [mechanics.py:128](../src/baselab/mechanics.py:128)

Start with **81 cells per TH/configuration**, three bins on four human-readable dimensions:

| Descriptor | Concrete definition |
|---|---|
| TH offset | Distance from TH center to village center, normalized; initial boundaries 0.3/0.6. |
| Compartments | Number of enclosed wall-only eight-connected regions of at least four tiles; retain initial boundaries 6/14. |
| AD spread | Mean pairwise Air Defense distance. Freeze numeric bin edges from a declared generator corpus. |
| Core defense density | Footprint-area fraction occupied by defenses within a fixed central region; freeze boundaries before search. |

Record continuous values as well as bins. Include open bases naturally. Additional report descriptors can include TH wall depth, defensive-value clustering, symmetry, deploy holes, and entry exposure. This follows the review’s proposed recognizable descriptors. [RUST_REVIEW_2026-10-25.md:238](history/RUST_REVIEW_2026-10-25.md:238)

Start with one confirmed elite per cell. Retain a small global Pareto set for ordinary score versus robustness. Parent selection should preserve uniform cell exploration alongside quality-weighted selection and fresh immigrants.

Checkpoint contents:

- Schema, executable/input identities, descriptor definition, objective, and rules.
- Proposal RNG, candidate cursor, completed wave, annealing state.
- Elite layouts, lineage, admission receipts, raw paired development rows.
- Scenario manifests, attack-archive version, payoff matrix, solver state.
- Budgets/counters, rejected proposals, seen identities, log offsets.
- Frozen-finalist manifest, stored separately from mutable development state.

Use pending-file/fsync/backup replacement and validate identities on resume, following army search. Persist enough raw results to race against incumbents without rerunning them. A layout-only archive is insufficient for exact continuation. [armysearch/report.rs:18](../crates/clash-armysearch/src/report.rs), [armysearch/search.rs:160](../crates/clash-armysearch/src/search.rs)

**7. Winner explanations and output**

Produce `winner.json`, `report.json`, `report.md`, a Rust-generated SVG layout, and replayable prepared jobs.

Each report should include:

- Inventory/legality receipt, levels, modes, facings, CC, heroes/banners, guardian, and hole map.
- Raw ordinary-meta score, penalized objective, population weights, policy/profile assumptions, and paired difference from the reference.
- Star×destruction distribution, TH survival, family/attacker-TH breakdown, and uncertainty.
- Discovered attacks, actual search budgets, evidence labels, fresh results, and robustness-gate outcome.
- Weighted-median representative Rust traces, plus separately labelled failure-tail examples.
- Building/trap contributions and small legal counterfactual interventions.
- Input identities, synthetic/real evidence status, mechanic sensitivities, and incomplete sections.

The frozen explanation tool already has useful median selection and intervention machinery, but currently uses Python traces. Port those concepts and require the Rust replay to reproduce its original bulk outcome. explain_base.py:98 (historical `tools/baselab/explain_base.py` at `f04706c`), explain_base.py:257 (historical `tools/baselab/explain_base.py` at `f04706c`), explain_base.py:559 (historical `tools/baselab/explain_base.py` at `f04706c`)

Damage totals are descriptive attribution; paired interventions estimate the effect of that particular change. Neither establishes a universal design rule.

Use a machine-readable proof receipt bound to executable/input identities instead of a caller-supplied “proof tests passed” flag. Preserve partial-report errors rather than publishing a complete-looking report when replay or gate evaluation failed. explain_base.py:603 (historical `tools/baselab/explain_base.py` at `f04706c`), explain_base.py:681 (historical `tools/baselab/explain_base.py` at `f04706c`)

**8. Validation and proof gates**

| Stage | Required evidence |
|---|---|
| Rules/admission | TH16/17/18 count snapshots derived from data; boundary cases for every check; at least 100,000 deterministic malformed/near-legal cases; no admission panics. |
| Frozen compatibility | Compare Rust against available frozen-Python `problems()`/`content_problems()` verdicts on a corpus. Compare issue categories, not string order. Record intended stricter Rust checks separately. No new Python implementation. |
| Geometry | Golden fixtures for diagonal leaks, sealed rings, corner pockets, edge/margin access, Tesla/trap exclusions, footprints, compartments, and dangling wall levels. |
| Operators | Thousands of seeded proposals per TH/operator; parent immutability, level/inventory preservation, legal output or typed rejection, deterministic repair, transform round trips. |
| Evaluation | Rust adapter agrees with existing scorer on identical bundles; correct signs/weights/modifiers; no second scouting pass; hidden-content changes cannot change public planning decisions. |
| Racing | Enumerable synthetic outcomes, including zero observed variance, unequal weights, ties, sparse groups, and adversarial late reversals. Measure false eliminations against complete evaluation. |
| Search | Tiny enumerable layout space with a known optimum and known per-cell winners; compare full-evaluation and raced runs. |
| Determinism | Identical proposals, outcomes, archive, and frozen winners with 1/4/16 workers, cold/warm caches, and uninterrupted/resumed execution. |
| Holdout isolation | Change final seeds, results, or held-out attack/base lineages: development archive and winner selection must remain unchanged. |
| Attack archive | Cyclic synthetic payoff game, duplicate-attack handling, archive-growth invalidation, historical-exploit retention, and oracle budget accounting. |
| Reports | Replay identity, paired statistics, intervention admission, proof receipts, and honest incomplete status. |

Army search already supplies useful templates for tiny-optimum, thread-count, resume, and holdout-isolation proofs. [armysearch/proof.rs:102](../crates/clash-armysearch/src/proof.rs), [armysearch/proof.rs:198](../crates/clash-armysearch/src/proof.rs)

Treat repeatedly consulted confirmation/gate data as development data. Freeze winner identities, ordering, programs, and thresholds before final evaluation. Current Python QD sorts and saves its winner using “holdout” results; do not preserve that behavior. Reuse army search’s explicit frozen-selection contract. qd_search.py:598 (historical `tools/baselab/qd_search.py` at `f04706c`), [armysearch/report.rs:236](../crates/clash-armysearch/src/report.rs)

At every shared-engine integration, run Rust goldens and existing army-search proofs, then `cargo fmt --check`. Review intentional expectation changes individually. Real-game predictive validation remains separate from synthetic search correctness. [GOLDEN.md:111](GOLDEN.md:111)

**9. Milestones, sizes, and parallel ownership**

Estimates are engineering days, including focused tests and review.

| Milestone | Size | Deliverable / exit gate |
|---|---:|---|
| M0: contracts | 0.5–1 | Freeze schemas, identities, ownership, objective/policy definitions, and acceptance fixtures. |
| M1: layout/rules/admission | 4–6 | TH16–18 import/export, data-derived inventory, structured legality, shared geometry; admission/geometry proofs pass. |
| M2: proposals | 3–4 | Local/setup/wall/macro operators, crossover, generators, bounded repair, annealing; conservation proofs pass. |
| M3: evaluation/racing | 2–3 | Visible-state adapter, CRNs, cost accounting, caches, halving; scorer and racing proofs pass. |
| M4: QD/checkpoints | 2–3 | TH-independent descriptors, confirmed archive, exact resume, tiny-optimum and thread determinism. |
| M5: attack archive | 4–6 | Playbook oracle, native army-search adapter, versioned payoff matrix, double-oracle loop, restricted-game solver. |
| M6: polish/reports | 2–3 | Rust diagnostics, trap polish, replayable winner reports, independent final evaluation. |

**Total: approximately 18–26 person-days.** With three writers after M0, a usable M1–M4 search can precede the full coevolution/reporting release.

Assign disjoint ownership:

| Writer | Exclusive files |
|---|---|
| Layout owner | `layout/{model,json,rules,admit,geometry}.rs`, normalized rule data, layout fixtures. |
| Proposal owner | `basesearch/generate.rs`, `operators/**`, `repair.rs`, `anneal.rs`, operator fixtures. |
| Evaluation owner | `basesearch/{eval,race,cache}.rs`, evaluation/racing fixtures. |
| Search owner | `basesearch/{archive,search,checkpoint,cli}.rs`, search fixtures. |
| Oracle owner | `basesearch/{oracle,psro}.rs`, attack-archive schema and proofs. |
| Reporting owner | `basesearch/{diagnostics,report,render}.rs`, report fixtures. |

The integration lead alone edits `lib.rs`, `main.rs`, root module declarations, and shared files such as `setup.rs`, `scoring.rs`, `scouting.rs`, `runner.rs`, and `armysearch/*`. Owners deliver narrow integration patches against agreed interfaces. Keep `crates/clash-vidmine/**` with its current writer and leave the playbook reviewers’ sources untouched.

Defer the surrogate until a measured equal-battle-budget experiment shows useful gains over direct Rust screening. Preserve evaluation logs and a proposal-filter interface now; any later surrogate gets an exploration quota and no authority to certify winners. [RUST_REVIEW_2026-10-25.md:249](history/RUST_REVIEW_2026-10-25.md:249)
