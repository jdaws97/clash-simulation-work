G4 status (2026-10-25): replaced/unused Python and stale procedures are
removed, required unported Python remains, and valuable output moved to ignored
`local/`. Sections 3–4 below are the original planning inventory, not the current
file list. See [CLEANUP_G4.md](CLEANUP_G4.md) for decisions and pending Rust paths.

> Predecessor Python filenames and parity procedures in this document are
> historical provenance from `f04706c`. Deleted tools are not runnable; see
> [the current documentation](README.md) for native commands and remaining Python ports.

G1/G2 status (2026-10-25): the root workspace now contains the ten requested
crates and one `clash` CLI, with thin compatibility binaries. Source and shared
fixtures have moved; `data/` and `rust/data/` remain in place. The strict offline
gate is `scripts/verify.sh`, also reached through `rust/verify.sh`.
See [RESTRUCTURE_LOG.md](RESTRUCTURE_LOG.md) for every moved file, helper
extractions, frozen hashes and acceptance evidence. Clippy is absent from the
installed WSL toolchain and is reported without downloading it.

The inventory and target below are the original plan. G0's writers are merged
at `24d25e7`; the current base-search and video union was used for G2. G3–G5,
including Python ports/deletions, new dataimport/playbook tool crates, data
reorganization, exact toolchain provisioning and Windows acceptance, remain
later work. The rule importer is temporarily CLI-owned and generic snapshot
readers are data-owned, so those future tool crates are not engine dependencies.

Recommend a Cargo workspace with **five reusable libraries, six tool libraries, and one `clash` CLI**. Keep the attacker executor inside the simulation engine; move army composition and playbook fitting into `clash-plans`. Introduce `clash-data` to break the catalog/layout/runtime dependency cycle.

The original read-only planning inventory used the checkout and both worktrees;
no files, downloads, builds, or tests were performed during that planning pass.
It covers:

- **85** files under the main `rust/src`.
- **12** additional base-search files in `../clash-lab-bs`.
- **22** video files in `../clash-lab-vid/rust/vidmine/src`, including six additions beyond main.
- **193** Python/shell/PowerShell files under `src/` and `tools/`, plus `rust/verify.sh`.
- Generated scripts under `output/` and memory-related helpers under `private/`.

“Cadence” below describes the workflow supported by the code. The repository does not establish actual execution frequency.

**1. Target workspace**

```text
clash-lab/
├── Cargo.toml
├── Cargo.lock
├── rust-toolchain.toml
├── README.md
├── AGENTS.md
├── THIRD_PARTY.md
├── .gitattributes
├── .gitignore
├── .github/workflows/verify.yml
│
├── crates/
│   ├── clash-data/
│   │   └── src/
│   │       ├── catalog.rs
│   │       ├── stats.rs
│   │       ├── labels.rs
│   │       ├── content.rs
│   │       ├── json.rs
│   │       ├── wire.rs
│   │       ├── node.rs
│   │       ├── battlelog.rs
│   │       └── fast_hash.rs
│   │
│   ├── clash-layout/
│   │   ├── src/{model,json,geometry,admit,rules,render}.rs
│   │   └── tests/
│   │
│   ├── clash-engine/
│   │   ├── src/
│   │   │   ├── battle.rs
│   │   │   ├── state.rs
│   │   │   ├── setup.rs
│   │   │   ├── load.rs
│   │   │   ├── runner.rs
│   │   │   ├── plans.rs
│   │   │   ├── plans/attacker.rs
│   │   │   ├── playbook.rs
│   │   │   ├── units.rs
│   │   │   ├── defense.rs
│   │   │   ├── spells.rs
│   │   │   ├── traps.rs
│   │   │   ├── heroes.rs
│   │   │   ├── pets.rs
│   │   │   ├── movement.rs
│   │   │   ├── targeting.rs
│   │   │   └── remaining runtime modules
│   │   ├── tests/{mechanics.rs,support/}
│   │   └── examples/mechanics_proof.rs
│   │
│   ├── clash-plans/
│   │   └── src/{armies,compile,compile_tests}.rs
│   │
│   ├── clash-scoring/
│   │   └── src/{scoring,scouting,uncertainty}.rs
│   │
│   ├── clash-armysearch/
│   │   └── src/
│   ├── clash-basesearch/
│   │   └── src/
│   ├── clash-fidelity/
│   │   └── src/
│   ├── clash-vidmine/
│   │   ├── src/
│   │   └── templates/
│   ├── clash-dataimport/
│   │   └── src/
│   │       ├── catalog/
│   │       ├── registry/
│   │       ├── csv/
│   │       ├── wiki/
│   │       ├── battlelog/
│   │       ├── snapshots/
│   │       ├── digitize/
│   │       ├── manifest/
│   │       └── patch/
│   ├── clash-playbook-tools/
│   │   └── src/{sources,transcripts,extract,verify,consolidate,complete,gaps,research}/
│   └── clash-cli/
│       └── src/
│           ├── main.rs
│           ├── simulate.rs
│           ├── compile.rs
│           ├── score.rs
│           └── checks/{golden,plan_golden,layout_proof}.rs
│
├── data/
│   ├── source/
│   │   ├── clashking/
│   │   ├── gamecsv/v18.200.9/
│   │   ├── secondary-catalog/
│   │   ├── mechanics/
│   │   ├── armies/
│   │   ├── playbooks/
│   │   ├── calibration-priors/
│   │   ├── layouts/
│   │   └── research/
│   ├── generated/
│   │   ├── registry.json
│   │   ├── catalog.json
│   │   ├── base_rules.json
│   │   ├── clan_castle.json
│   │   └── manifest.json
│   └── licenses/
│
├── fixtures/
│   ├── golden/{cases.jsonl,expected.jsonl,plans.jsonl}
│   ├── accounts/
│   ├── layout/{admission,geometry,inventory}.json
│   ├── mechanics/{demos,evidence}.json
│   ├── battlelog/
│   ├── fidelity/
│   ├── digitize/
│   └── playbooks/
│
├── scripts/verify.sh
├── docs/
│   ├── architecture/
│   ├── engine/
│   ├── tools/
│   ├── research/
│   └── evidence/
│
├── private/                       # ignored; explicit personal inputs
├── output/                        # ignored; generated reports/checkpoints
└── target/                        # ignored
```

The five reusable libraries are `clash-data`, `clash-layout`, `clash-engine`, `clash-plans`, and `clash-scoring`. The six tool libraries are army search, base search, fidelity, video mining, data import, and playbook tooling.

Use a virtual root workspace, explicit members, shared package metadata/lints, one lockfile, and the existing release settings at the root. Remove `rust/vidmine`’s nested `[workspace]` and duplicate release profiles during its move. Determine and pin the supported Rust toolchain through the workspace checks rather than guessing an MSRV.

Keep the engine and foundational libraries free of network, transcription, research-provider, and media-process dependencies. Tool crates may have their own Rust dependencies.

**CLI recommendation**

Use **one supported `clash` executable**, with each tool exposing a library entry point. This gives consistent resource paths, error handling, output directories, and configuration.

```text
clash simulate run|trace|jobs|bench
clash plan compile|check
clash score
clash armysearch run|proof|train-policy
clash basesearch run|proof|compare|explain|train-surrogate
clash fidelity replay|board|calibrate|cv|observed
clash video probe|extract|positions|spatial|review|verify
clash data catalog|registry|rules|manifest|patch|wiki
clash data battlelog decode|fetch|collect
clash data snapshot add|list|for-battle|report
clash data digitize ...
clash playbook harvest|extract|verify|consolidate|complete|gaps
clash research usage|audit
clash golden check
clash golden plans check
```

Retain `baselab-engine`, `fidelity`, and `vidmine` as thin compatibility binaries during migration. Remove them after scripts and documentation use `clash`.

**Dependency direction**

| Crate | Permitted workspace dependencies |
|---|---|
| `clash-data` | None |
| `clash-layout` | Data |
| `clash-engine` | Data, layout |
| `clash-plans` | Data, engine |
| `clash-scoring` | Data, layout, engine, plans |
| `clash-armysearch` | Data, engine, plans, scoring |
| `clash-basesearch` | Data, layout, engine, plans, scoring; armysearch for bounded attacker refinement |
| `clash-dataimport` | Data, layout |
| `clash-fidelity` | Data, engine, plans, scoring, dataimport |
| `clash-vidmine` | Initially preserve its independent implementation |
| `clash-playbook-tools` | Data, plans |
| `clash-cli` | All command implementations |

Do not make the engine depend on the compiler, search, fidelity, or CLI crates.

**Data ownership**

| Current material | Disposition |
|---|---|
| `rust/data/catalog.json` | Move byte-for-byte to `data/generated/catalog.json`; this is the runtime catalog. |
| `data/catalog.json` | Retain separately as source data. It has a different schema and is read by video identity analysis. Do not overwrite or merge it with the runtime catalog. |
| `data/clashking-static-{data,source}.json`, `data/gamecsv/**` | Versioned source snapshots, preserving attribution and hashes. |
| `data/registry.json` | Pinned generated intermediate until the native builder reproduces it. |
| Balance/mechanics claims, overrides, lifecycle evidence, warden weights | Retain reviewed public/model inputs under `data/source/mechanics/`; distinguish source claims from generated measurements. |
| `rust/data/base_rules.json` | Pinned generated rules; retain source pointers and explicit model overrides. |
| `rust/data/clan_castle.json` | Retain; compiler reads it. Document its generation/source contract. |
| `rust/data/target17.json`, `target18.json` | Move to declared target/layout fixtures after classifying their provenance. |
| Army libraries, attacker policy, playbook gaps, playbooks | Retain as distinct source/model inputs, with provenance. Personal army records require separation. |
| Public calibration priors | Retain pinned priors, including their existing identifiers/hashes. |
| Fitted defense calibrations and reports | Generated artifacts under `output/fidelity/`, including ancestry needed to validate existing fits. |
| `data/live/**`, personal levels/layouts, real replay records | Remove from tracking and use explicit ignored/private paths. |
| `data/wiki/**` | Ignored acquisition cache. Preserve source revisions/hashes needed to reproduce pinned generated data. |
| Builder screenshots and video templates | Retain only distributable assets with provenance/license coverage; otherwise private inputs plus synthetic fixtures. |
| `data/battle-policies/**` and old claim/catalog files | Retain only those referenced by surviving code, fixtures, or retained evidence; delete the obsolete prototype remainder after that closure is checked. |

Generated does **not** automatically mean untracked: the runtime catalog, normalized rules, and portable fixtures should remain tracked so ordinary verification is offline.

Place shared goldens in `fixtures/golden/`, because they span engine execution and plan compilation. Keep test implementations in their owning crates.

The existing golden design already makes battle cases self-contained. Preserve that property and every byte of the three golden files. [Current golden contract](GOLDEN.md)

---

**2. Complete Rust mapping and required decoupling**

Paths in the following tables are relative to `rust/src/` unless otherwise stated. Grouping means identical destination, not omission.

| Existing file(s) | Target |
|---|---|
| `catalog.rs`, `content.rs`, `fast_hash.rs`, `json.rs`, `labels.rs`, `stats.rs` | `clash-data/src/`, preserving module names |
| `ai.rs`, `battle.rs`, `combat.rs`, `defense.rs`, `detmath.rs`, `effects.rs`, `field_profile.rs`, `geom.rs`, `grid.rs` | `clash-engine/src/` |
| `heroes.rs`, `load.rs`, `movement.rs`, `params.rs`, `pets.rs`, `plans.rs`, `playbook.rs`, `pyrandom.rs` | `clash-engine/src/` |
| `runner.rs`, `setup.rs`, `shared.rs`, `source.rs`, `spells.rs`, `state.rs`, `targeting.rs`, `trace.rs`, `traps.rs`, `units.rs` | `clash-engine/src/` |
| `attacker.rs` | `clash-engine/src/plans/attacker.rs`; preserve its existing `plans` namespace/re-exports |
| `playbook_tests.rs` | Engine executor tests; replace compiler-dependent preparation as described below |
| `armies.rs`, `compile.rs`, `compile_tests.rs` | `clash-plans/src/` |
| `scoring.rs`, `scouting.rs` | `clash-scoring/src/` |
| `layout/model.rs`, `layout/json.rs`, `layout/geometry.rs`, `layout/admit.rs` | `clash-layout/src/` |
| `layout/rules.rs` | Rule types/loading/validation remain in layout; `derive` and source-import helpers move to dataimport |
| `layout/mod.rs` | Becomes `clash-layout/src/lib.rs` |
| `layout/cli.rs` | CLI layout dispatch |
| `layout/proof.rs` | CLI layout verification suite; it currently uses engine setup, grid, and scoring |
| `jobs.rs` | CLI simulation/jobs module; reusable `Job`/`Runner` remain engine-owned |
| `compile_cli.rs` | CLI compilation commands; extract shared wire helpers first |
| `scoring_cli.rs` | CLI scoring commands |
| `golden.rs`, `plan_golden.rs` | CLI verification modules, retaining existing record/check behavior |
| `main.rs` | Replace with umbrella dispatch and temporary compatibility binary |
| `lib.rs` | Replace with owning-crate roots and transitional re-exports |
| `test_support.rs` | Split engine battle/catalog helpers from plans’ compiler helper |

All army-search files move to `clash-armysearch`:

```text
armysearch.rs                    → src/lib.rs
armysearch/account.rs            → src/account.rs
armysearch/eval.rs               → src/eval.rs
armysearch/fix_proof.rs          → src/fix_proof.rs
armysearch/genome.rs             → src/genome.rs
armysearch/novelty.rs            → src/novelty.rs
armysearch/operators.rs          → src/operators.rs
armysearch/program.rs            → src/program.rs
armysearch/program_mutate.rs     → src/program_mutate.rs
armysearch/program_proof.rs      → src/program_proof.rs
armysearch/program_validate.rs   → src/program_validate.rs
armysearch/proof.rs              → src/proof.rs
armysearch/report.rs             → src/report.rs
armysearch/score.rs              → src/score.rs
armysearch/search.rs             → src/search.rs
armysearch/themed.rs             → src/themed.rs
armysearch/util.rs               → src/util.rs
```

Preserve the existing `#[path]` relationships during the mechanical move. Normalize filenames later if useful.

All fidelity files are accounted for:

| Existing file | Target |
|---|---|
| `fidelity/board.rs`, `fit.rs`, `metrics.rs`, `observed.rs`, `provenance.rs`, `replay.rs`, `th18.rs` | `clash-fidelity/src/` |
| `fidelity/main.rs` | Public command entry point in fidelity, called by umbrella CLI |
| `fidelity/decode.rs` | Split shared share-code parser/name resolution into `clash-data::battlelog`; keep observed-build conversion in fidelity |
| `fidelity/history.rs` | Reusable snapshot/history reader under dataimport; fidelity consumes it |
| `fidelity/io.rs` | Shared wire/hash utilities into data; fidelity-specific helpers remain local |
| `fidelity/archive_export.rs` | **Delete from active source.** It is an unregistered historical-crate proof helper, not a production target. Preserve any necessary historical reproduction instructions in documentation/history. |

The decoder split prevents the data-import tool from acquiring a scoring dependency merely because the existing decoder also constructs simulation builds.

The base-search worktree currently contains **M2 proposals**, not the complete evaluator/QD coordinator. Its own report says M3 evaluation and M4 search remain outstanding. [M2 implementation report](history/BASE_SEARCH_M2.md)

Every current base-search file moves to `clash-basesearch`:

```text
basesearch/mod.rs                 → src/lib.rs
basesearch/anneal.rs              → src/anneal.rs
basesearch/crossover.rs           → src/crossover.rs
basesearch/generate.rs            → src/generate.rs
basesearch/repair.rs              → src/repair.rs
basesearch/spatial.rs             → src/spatial.rs
basesearch/proof.rs               → src/proof.rs
basesearch/operators/mod.rs       → src/operators/mod.rs
basesearch/operators/guided.rs    → src/operators/guided.rs
basesearch/operators/macro_ops.rs → src/operators/macro_ops.rs
basesearch/operators/setup.rs    → src/operators/setup.rs
basesearch/operators/walls.rs    → src/operators/walls.rs
```

The worktree’s `lib.rs`/`main.rs` wiring must be merged selectively. Its older copies of compiler/playbook files must not replace the concurrent main-checkout fixes.

For video mining, use the video worktree’s union as the source of truth:

| Existing `rust/vidmine/src/` files | Target |
|---|---|
| `audit.rs`, `extract.rs`, `icons.rs`, `identity.rs`, `identity_review.rs`, `image.rs`, `json.rs`, `league.rs`, `ocr.rs`, `positions.rs`, `probe.rs`, `replay.rs`, `review.rs`, `timing.rs`, `video.rs` | Same modules under `clash-vidmine/src/` |
| `appearance.rs`, `camera.rs`, `grid.rs`, `spatial.rs`, `spatial_review.rs`, `townhall.rs` | Same destination; these six currently exist only in the video worktree |
| `main.rs` | Split library command entry point from umbrella dispatch |

Keep vidmine’s JSON implementation during the move. It has different representation/order behavior from the engine parser; unifying parsers is unnecessary migration risk.

Also move:

| Outside `rust/src` | Target |
|---|---|
| `rust/tests/mechanics.rs` | Engine integration tests |
| `rust/tests/support/mechanics.rs` | Engine integration-test support |
| `rust/examples/mechanics_proof.rs` | Engine example |
| `rust/fixtures/layout/**` | `fixtures/layout/` |
| `rust/fixtures/mechanics/**` | `fixtures/mechanics/` |
| `rust/golden/**` | `fixtures/golden/`, byte-identical |
| `rust/vidmine/templates/**` | Vidmine templates, subject to provenance/license classification |

**Cycles that block a direct split**

| Actual dependency | Minimal change |
|---|---|
| `state → plans/playbook → state`, with heroes/spells/units involved | Keep the executor, triggers, live inventory, and attacker decisions together in engine. These are simulation behavior. |
| `compile → armies → engine plans`, while engine `playbook → armies` | Move `put`, `string`, `list`, and related JSON helpers out of `armies`; move the pure `is_siege` predicate to data. The executor then stops importing the compiler library. |
| `setup → layout::admit`, while layout imports `Catalog`, `Stats`, `Level`, `ContentError` | Put those shared types in data. Layout depends on data; engine depends on layout. Keep the same content validation call and error behavior. |
| `catalog → load::Node → catalog/state` | Extract the generic `Node` reader into data. Keep team parsing in engine through a local helper/extension trait; do not move `Team` into data just to satisfy the parser. |
| `stats → trace::py_float_repr → state` | Move the pure float formatter into data; re-export it through `engine::trace`. |
| `layout::json`, fidelity IO and mechanics support call `compile_cli::to_json` | Move the exact serializer into data and retain compatibility re-exports. Libraries must not depend on CLI code. |
| `compile_cli ↔ plan_golden` | Keep both in CLI verification initially; no crate cycle remains. |
| `layout::proof → scoring/engine` | Move proof orchestration out of the layout production library. |
| `grid ↔ field_profile` | Keep both in engine; no benefit from splitting them. |
| Engine `test_support::with_compiler`, used by executor tests | Preserve private executor assertions in engine. Replace their compilation helper with explicit prepared synthetic inputs; test compilation of those inputs separately in plans. |
| Fidelity IO/decoder/history use sibling helpers | Extract helpers first, then move modules. Avoid duplicating snapshot hashing or share-code semantics. |

Make helpers public only where another owning crate requires them. Do not expose private executor internals simply to relocate tests.

Preserve module names through re-exports where possible. Keep `Runner`, `PreparedInputs`, `Compiler`, `CompileOptions`, JSON shapes, plan `$type` values, array order, RNG behavior, deterministic math, and unsupported-content behavior unchanged.

**Path and identity work is part of the move**

Update all of these together:

- Catalog discovery in `main.rs`, compile CLI and test support.
- `Compiler::load` paths, especially `clan_castle.json`.
- Golden default paths.
- Mechanics `include_str!` paths.
- Vidmine’s template and source-catalog paths.
- Layout corpus proof’s Git pathspecs.
- Armysearch report fingerprints, currently scanning `rust/src`, `rust/data`, flat `data`, and playbooks.
- Fidelity provenance scans and archived-calibration discovery.

Introduce explicit resource configuration, with existing `BASELAB_*` variables accepted temporarily. Verification must select a pinned synthetic account and must never overlay the changing `data/live/player-latest.json`.

Path changes legitimately change provenance identities. Version the manifest/checkpoint format and invalidate incompatible resumptions; do not pretend old fits/checkpoints were produced by the reorganized executable. **Golden bytes remain unchanged.**

---

**3. Complete Python and shell inventory**

Status meanings:

- **USED → native:** the capability already has a Rust implementation; verify coverage, then delete Python.
- **USED → port:** retain the workflow and implement its remaining behavior in Rust.
- **UNUSED → delete:** obsolete glue or an intentionally excluded workflow.
- Effort: **S** ≤1 engineer-day, **M** 2–3, **L** 4–7, **XL** 8–12. Group estimates overlap and must not be summed.

**`src/baselab/`: all 38 files**

| File(s) | Status, consumer/cadence | Rust destination and remaining work |
|---|---|---|
| `engine/battle.py`, `engine/defense.py`, `engine/effects.py`, `engine/entities.py`, `engine/heroes.py`, `engine/pets.py`, `engine/result.py`, `engine/spells.py`, `engine/traps.py`, `engine/units.py`, `pathing.py` | USED by legacy simulations and reference exports; per legacy run | Native engine already exists. Retire Python after coverage/golden gates. S–M audit. |
| `engine/plans.py`, `engine/playbook.py` | USED by simulation, composition, research checks, catalog export | Runtime → engine; construction/fitting → plans; exported constants → declarative source data. M boundary audit. |
| `engine/specs.py`, `engine/stats.py` | USED by catalog builder and legacy simulation; per patch/build | Runtime reading → data/engine; unit/summon specs, CSV inheritance, overrides and resolved-value construction → dataimport. XL with catalog work. |
| `gamedata.py`, `registry.py`, `mechanics.py` | USED by registry/catalog construction, decoder, layout tooling | Dataimport source loaders/registry/catalog/rules; shared types → data/layout. L–XL. |
| `layout.py`, `deploy.py` | USED throughout search/digitization; each layout/run | Existing native layout/admission/geometry; finish capability audit. M. |
| `loadouts.py` | USED by plans, catalog export and legacy tools | Existing plan/catalog/loadout representations. S. |
| `meta_armies.py` | USED by compiler, replay and search workflows | Existing armies/compiler/scoring coverage; retain account adaptation and observations. M audit. |
| `evaluate.py` | USED by nearly every legacy experiment | Existing scorer/runner/scouting plus remaining search adapters. M. |
| `archetypes.py`, `generator.py`, `unconventional.py` | USED by evolution, funnel, QD and seed completion | Basesearch generation/packing; M2 covers substantial functionality. Verify every retained style and TH policy. M–L. |
| `macro_moves.py`, `optimize.py`, `evolve.py` | USED by base search | M2 operators/repair/crossover/annealing plus production coordinator. L remaining. |
| `diagnose.py` | USED by guided moves, explanation and trap polishing | Basesearch diagnostics collected from Rust battles. M–L; M2 synthetic guidance is not this collector. |
| `redteam.py` | USED by evaluation/funnel/explanation | Bounded basesearch attacker refinement using plans/armysearch/scoring. M–L. |
| `tactics.py` | USED by adaptive army tests and legacy scoring | Armysearch tactic search/refinement; preserve applicability constraints. M. |
| `policy.py` | USED by composition and policy training | Policy loading in plans; fitting/search in armysearch. M. |
| `surrogate.py` | USED by funnel, evolution, predictor proof and training | Basesearch feature extraction, ridge fitting/inference and model serialization. L. Do not silently drop it because M2 does not include it. |
| `uncertainty.py` | USED by paired comparison/explanation | Scoring uncertainty/report API; preserve complete-group pairing/bootstrap semantics. M. |
| `render.py` | USED by guides, comparison, contact sheets and base outputs | Layout rendering; search tools compose reports around it. M. |
| `rust_bridge.py` | USED by remaining Python callers; per legacy evaluation | Rust calls engine/runner directly. Delete once callers are ported; no bridge replacement. S. |
| `__init__.py` | Python package glue | UNUSED in target → delete with package. |

**Core import, observation, calibration and verification tools**

All paths below are under `tools/baselab/`.

| File(s) | Status, consumer/cadence | Target |
|---|---|---|
| `snapshot_log.py` | USED standalone collector; produces archive/player data consumed by replay and army account loading. Poll interval is not defined here. | Dataimport battlelog fetch/collect. **M.** Preserve deduplication and player-context capture; eliminate hardcoded player/output defaults. |
| `decode_battlelog.py` | USED by `replay_log`, `replay_observed`, calibration | Existing native decoder → shared data parser plus dataimport command. S–M. |
| `snapshot.py` | USED by replay; native history reader already exists | Dataimport snapshot add/list/lookup/report writer and validation. **M.** Rust currently reading history does not replace the recording workflow. |
| `rust_export.py` | USED catalog builder and historical parity exporter; per patch/reference work | Split catalog construction into dataimport; port any retained synthetic job generators to Rust fixtures. Delete Python battle/trace/parity orchestration after native gates. **XL.** |
| `data_manifest.py` | USED by export/patch/calibration freshness checks | Dataimport manifest build/check; workspace-wide explicit input groups. M. |
| `patch_update.py` | USED patch workflow; invokes mechanic/coverage checks | Dataimport patch diff/citation checks, calling native verification. M–L. |
| `wiki_mirror.py` | USED by patch/registry source acquisition | Dataimport wiki acquisition with caching/revisions/retries. M. |
| `wiki_tables.py` | USED by registry/manifests/mirror workflow | Dataimport wiki table/text normalization, including rowspan/colspan behavior. M–L. |
| `wiki_digest.py` | USED standalone review digest | Dataimport digest report. S–M. |
| `verify_numbers.py`, `xcheck_stats.py` | USED by patch/source validation | Dataimport source checks. M together. |
| `calibrate.py` | USED aggregate archetype fitting, including legacy A/B support | Fidelity aggregate-target fitting mode. Existing native defense fitting does not prove replacement of this mode. M. |
| `calibrate_meta.py` | USED by meta fitting and defense calibration | Fidelity per-build/family fitting with explicit prior provenance and uncalibrated fallbacks. M–L. |
| `calibrate_defenses.py` | USED defense-distribution fit/CV | Existing fidelity fit/CV; audit remaining flags, ancestry and report semantics. M. |
| `replay_log.py`, `replay_observed.py`, `fidelity_board.py` | USED per observation/accuracy run | Existing fidelity replay/observed/board implementations. M coverage audit. |
| `mechanic_tests.py` | USED by patch and reference workflows | Engine synthetic mechanics tests; preserve named hypotheses and explicit unsupported cases. M. |
| `fingerprint.py`, `trace_diff.py` | USED by parity/coverage diagnostics | Native golden/trace diagnostics. S–M. |
| `score_reference.py`, `scorer_check.py` | USED historical scoring-oracle checks | Freeze useful portable cases; native scoring checks replace execution. Delete Python oracle. M. |
| `rust_spike.py` | UNUSED production path; superseded port spike | Delete. Retain useful independent fixture assertions in Rust first. S. |
| `engine_coverage.py` | USED patch/coverage workflow | Native coverage/check manifest. Python line coverage is retired; preserve mechanic/entity exercise reporting separately. M. |

`rust_export.py` is not just a JSON copier. It resolves registry overrides, specs and summons, CSV tables, equipment abilities, spell radii, pet ranges/speeds, weapon profiles, donation requirements, setup tables and environment defaults. Deleting it before those constructors are ported leaves the runtime catalog unmaintainable. Catalog construction (historical `tools/baselab/rust_export.py` at `f04706c`)

**Army, policy, search, comparison and report tools**

| File(s) | Status, consumer/cadence | Target |
|---|---|---|
| `adaptive_check.py`, `army_bench.py`, `attack_lab.py`, `attack_search.py`, `tactics_check.py` | USED standalone army/tactic experiments; per experiment | Armysearch benchmark/refine/compare commands. M–L together. |
| `recommend_armies.py` | USED directly and by attack/report tools | Armysearch account loading/ranking; explicit private account input. M. |
| `army_guide.py` | USED by report builder | Plans/armysearch guide generation. S–M. |
| `charge_screen.py`, `policy_screen.py`, `train_policy.py` | USED policy research/training chain | Armysearch policy screen/train, using native runner. M–L. |
| `playbook_check.py`, `redteam_check.py` | USED attacker-quality experiments | Fidelity evaluation plus bounded attacker refinement; retain explicit oracle labels. M. |
| `test_base.py` | USED direct base evaluation with tactics/surrogate options | Basesearch evaluate command. M. |
| `optimize_base.py`, `evolve_bases.py`, `funnel.py`, `qd_search.py` | USED production-style legacy search entry points | One basesearch coordinator with configurable emitters, staged evaluation and QD archive. **XL remaining beyond M2.** |
| `ab_guided.py`, `guided_test.py` | USED guided-search checks | Basesearch diagnostics/operator proof suite. S–M. |
| `base_noise.py`, `proof_paired.py`, `proof_scorer.py` | USED noise/scorer experiments; proof utilities import each other | Scoring paired uncertainty and basesearch proofs. M. |
| `proof_macro.py`, `proof_proxy.py`, `proof_repair.py` | USED proposal/screening/repair proofs | Basesearch proof modes. M. |
| `predictor_proof.py`, `train_surrogate.py` | USED by surrogate workflow | Basesearch surrogate train/proof. M–L, alongside `surrogate.py`. |
| `compare_layouts.py`, `final_compare.py`, `final_eval.py` | USED final/paired comparison workflows | Basesearch compare/report using scoring. M. |
| `explain_base.py` | USED detailed explanation workflow | Basesearch diagnostics, paired interventions, representative native traces and reports. L. |
| `fill_pockets.py`, `hero_banners.py`, `trap_polish.py` | USED specialized base modifications/search | Basesearch constrained operators/refinement modes. M–L. |
| `build_guide.py`, `contact_sheet.py` | USED layout presentation | Layout render/build-guide/contact-sheet support. M–L. |
| `build_report.py` | USED by `run_post.sh` | CLI report composition over native outputs; no second scoring implementation. M. |
| `ab_test.py` | USED old brain-change A/B harness | Replace with native paired experiment command/test cases. S–M. |
| `run_batch.sh`, `run_deep.sh`, `run_originals.sh`, `run_originals_funnel.sh`, `run_overnight.sh`, `run_post.sh` | UNUSED as permanent interfaces: dated orchestration around retained tools | Extract useful parameters into named run configurations; delete shell wrappers after native commands exist. M together. |

**Research and playbook pipelines**

| File(s) | Status, consumer/cadence | Target |
|---|---|---|
| `harvest_videos.py` | USED source-discovery workflow; calls transcript fetcher | Playbook tools source discovery/provider. M. |
| `yt_transcript.py` | USED by harvesting | Playbook tools transcript provider, with local-file import always supported. M. |
| `extract_playbooks.sh` | USED per harvested transcript; invokes external provider then checker | Playbook tools resumable extraction queue, bounded workers, atomic outputs and verification. M. |
| `check_playbook.py` | USED by extraction, consolidation, completion and gap measurement | Playbook tools quote normalization/location/time verification. M. |
| `check_consolidated.py` | USED before writing executable source playbooks | Playbook tools consolidation validation and diagnostics. M. |
| `merge_completion.py` | USED completion merge workflow | Playbook tools verified completion merge/order/dependency handling. M. |
| `step_gaps.py` | USED timing-data derivation | Playbook tools gap measurement. S–M. |
| `research_usage.sh`, `audit_usage.sh`, `audit_fanout.sh` | USED resumable research/audit workflows; per research batch | Playbook tools research queue/provider adapters. M–L. Move reusable prompts/queues out of `output/`. |
| `verify_audit.py` | USED standalone first-pass research check | Playbook tools audit validation. S. |

These workflows currently depend on user-specific `~/bin/codex-ask` / `codex-research` commands and prompts inside `output/`. Replace that coupling with a configured process/provider interface and saved job manifests. An offline mode must validate already-supplied results without invoking a provider.

Retain quote verification, cited versus learned provenance, source-only consolidation rules, and rejection diagnostics. Do not replace these with unchecked model output.

**Screenshot digitization**

| File(s) | Status, consumer/cadence | Target |
|---|---|---|
| `digitize.py`, `grid_overlay.py`, `detect_walls.py` | USED manual screenshot workflow; per screenshot | Dataimport digitize build/walls/overlay. M–L. |
| `finish_digitized.py`, `complete_digitized.py` | USED completion chain; complete invokes finish | Dataimport explicit repair/imputation/seed completion. M. |
| `trace_walls.py` | **Absent** from main and both current tool inventories | No file to move/delete. Provide manual wall tracing/import in the native digitizer; do not invent a current implementation. |

Port the toolkit by capability rather than preserving dozens of tiny executables. Every toolkit file is assigned below; paths are relative to `tools/baselab/digitize_kit/`.

| Files | Status and native destination |
|---|---|
| `cfit.py`, `chk2.py`, `chk3.py`, `chkmap.py`, `fh.py`, `fitoff.py`, `fitoff2.py`, `hfit.py`, `vfit.py`, `wfit.py` | USED manual fitting/diagnostics → `digitize::fit`; M–L |
| `palewalls.py`, `walls2.py`, `walls3.py`, `wd.py` | USED alternative wall detectors → `digitize::walls`; consolidate strategies, M |
| `pads.py`, `pads2.py`, `probe.py`, `snap.py` | USED footprint proposals/alignment → `digitize::buildings`; M |
| `conv.py`, `build.py`, `finalize.py`, `resolve.py`, `seed.py`, `merge_impute.py`, `inv.py` | USED conversion/validation/completion → digitize import/build/repair/seed; M–L |
| `gal.py`, `gal2.py`, `gl.py`, `ov.py`, `ovl.py`, `ovt.py`, `ovw.py`, `sheet.py`, `wins.py`, `zoom.py`, `zt.py`, `ztw.py`, `zw.py` | USED inspection/rendering capabilities → digitize overlay/crop/gallery/windows; M |
| `ascii.py`, `dots.py`, `diff.py` | USED small inspection capabilities → digitize diagnostics; S |
| `blobs.py`, `cands.py`, `ccparse.py` | UNUSED as supported tools: hardcoded batch/source experiments → delete; preserve reviewed candidate metadata as data, not executable scraping notebooks |
| `rt.sh`, `win.sh` | UNUSED as portable workflows: hardcoded temporary paths → delete |
| `batch_b/build.py`, `batch_b/conv.py`, `batch_b/seed.py` | USED batch variants → same import/build/seed commands; S incremental |
| `batch_b/lat.py`, `batch_b/proj.py` | USED lattice fitting → digitize fit; M incremental |
| `batch_b/walls4.py`, `batch_b/gapfill.py`, `batch_b/wclean.py` | USED detection/manual wall editing → digitize walls/edit; M incremental |
| `batch_b/full.py`, `batch_b/gal2.py`, `batch_b/rul.py`, `batch_b/win.py` | USED visual inspection variants → overlay/gallery/ruler/windows; S–M incremental |
| `batch_b/dewm.py` | USED image-inspection transform → optional inspection transform; preserve original image and record transform; S |
| `batch_b/symfix.py` | USED assumed symmetry correction → explicit proposal/edit operation with provenance; S |

`merge_impute.py` currently imports `make_reference_bases.impute`. Extract only its generic completion capability into the native digitizer; do not preserve its memory-layout input pipeline.

The digitizer must distinguish **measured**, **manually corrected**, and **imputed** positions. Hidden Teslas, traps, added walls, applied account levels, and assumed symmetry must remain explicit. Completion must produce a new output, rather than silently rewriting the measured source layout.

**Memory-related deletion: no ports**

These are **excluded from the retained workflow**, regardless of historical invocation:

```text
tools/baselab/collect_game_memory.ps1
tools/baselab/scan_game_memory.py
tools/baselab/extract_game_tables.py
tools/baselab/game_memory_selection.ps1
tools/baselab/compare_game_tables.py
tools/baselab/test_compare_game_tables.py
tools/baselab/test_extract_game_tables.py
tools/baselab/test_scan_game_memory.py
tools/baselab/test_game_memory_selection.ps1

docs/LOCAL_CLIENT_EVIDENCE.md
docs/evidence/local-static-audit-2026-10-21.json
```

Also delete the additional memory-derived pipeline found during inspection:

```text
tools/baselab/import_memory_layouts.py
tools/baselab/make_reference_bases.py
```

The latter explicitly builds the `real-l*x` reference layouts from recovered memory slots. Remove those layouts from active search/fidelity source sets; do not merely rename them. Audit derived calibration ancestry and exclude affected evidence from accuracy claims.

Remove `data/extracted-stat-selection.json` if its only remaining consumer is the excluded table-comparison workflow.

**Python execution hidden in Rust**

`compile_cli.rs` can invoke Python with an embedded exporter or an optional `tools/baselab/plan_reference.py`. That standalone file is currently absent. The default native `compile-check` path already uses plan goldens; explicit Python comparison retains the dependency. [Reference adapter](../crates/clash-cli/src/compile_cli.rs)

Final disposition:

- Keep native plan checking and saved-reference comparison.
- Remove `REFERENCE_EXPORTER`, Python process invocation, `--python`, `BASELAB_PYTHON`, and `--write-reference-script`.
- Return a clear migration error for retired flags during compatibility.
- Do not port a second compiler as an “oracle”; use frozen independent fixtures.

Other observed Rust subprocesses are Git for corpus enumeration and FFmpeg/FFprobe for media. Keep those explicit tool dependencies. Python comments/source citations alone are not execution dependencies.

**Keyless battle-log fetching**

The existing collector uses a public keyless proxy. Preserve that as an optional provider, without assuming continued service availability.

Implement:

```text
BattleLogSource
├── LocalJson
├── LocalJsonLines
├── Stdin
└── ConfiguredKeylessHttpProvider
```

Required behavior:

- Explicit player/tag, endpoint/provider and output location.
- No official API key requirement or credential prompt.
- Preserve raw observations privately; record provider and fetch time.
- Preserve collector deduplication separately from fidelity’s observation identity.
- Retry/rate-limit handling, pagination when supported, atomic archive updates.
- Provider unavailable/unsupported is an explicit result.
- Local import remains fully functional without network access.

**Generated scripts outside source directories**

There is no `scripts/` directory today. Create only the requested verification entry point.

All 71 Python/shell files currently under `output/` need disposition:

| Existing generated scripts | Disposition |
|---|---|
| `dragon-spacing/analyze.py` | Port retained spacing measurement into fidelity; delete script afterward |
| `overnight/bench_commits.sh`, `overnight/cap_monotonic.py`, `overnight/clump.py`, `overnight/cv/run.sh`, `overnight/cv/split.py`, `overnight/cv2/pool.py`, `overnight/cv2/run.sh` | Native benchmark/fidelity experiment manifests; preserve historical artifacts and ancestry, delete execution glue |
| `overnight/exp_alloc.py`, `overnight/exp_surrogate.py`, `overnight/score_qd_proof.py` | Basesearch allocation/surrogate/proof capabilities; retire scratch scripts |
| `playbook-review/run_reviews.sh` | Playbook review queue |
| `ranked-bases-2026-10-24/run.sh` | Digitization job manifest |
| `ranked-bases-2026-10-25-th18/t18b/{finalize,review,verify}.py`, `.../t18d/{finalize,refine}.py` | Preserve reviewed manual edits/provenance as data; native digitizer replaces executable scratch helpers |
| `rescore/{eagle_check,ranked_compare,rescore,sep_test,th18_replay_check}.py` | Native scoring/fidelity experiment configurations |
| `run_accuracy.sh`, `run_bases.sh`, `run_bases_r7.sh`, `run_cc_completion.sh`, `run_completion.sh`, `run_playbook_round.sh`, `run_round3.sh`, `run_round4.sh`, `run_round5.sh`, `run_traps.sh` | Extract retained configurations; delete dated wrappers |
| `speedproof/{dump_jobs,exp_alloc_decisions,exp_alloc_truth,exp_race}.py` | Native runner/basesearch benchmark modes |
| `web-videos/run_batch.sh` | Native vidmine batch processing. Local media is the baseline; do not introduce mandatory Python-backed downloading |
| `snapshots/baselab-2026-10-18-pre-audit/**/*.py` — 36 files | Historical duplicate source, not a runtime dependency. Preserve any designated baseline untouched; remove expendable duplicates only after the baseline/unique-content gate |

The two `private/local-game-memory/*/normalize_manifest.py` files belong to the excluded memory artifacts: delete with those artifacts, not port.

---

**4. Non-code cleanup**

| Location | Plan |
|---|---|
| `examples/` — 223 tracked files | Mostly the older prototype’s inputs. Move only the transitive inputs of retained Rust examples/tests/docs into `fixtures/`; retain a few runnable examples. Delete the obsolete prototype collection after reference closure checks. |
| `profiles/sample-th16.json` | Explicitly synthetic: move to `fixtures/accounts/`. |
| `profiles/target-max-th16-inventory.json` | Validate against current native rules; retain as a named inventory preset only if needed. Otherwise delete obsolete unresolved planning data. |
| Real profiles / `profiles/private/` | Ignored private inputs. No compiler or verifier should discover them implicitly. |
| `private/local-game-memory/`, `private/local-game-disk/`, `work/reverse-local-2026-10-21/` | Delete excluded acquisition artifacts from the active working environment; never make them a native importer source. |
| Other `private/` | Keep only needed personal observations/media/account inputs, ignored and explicitly selected. |
| Other `work/` | Disposable scratch; delete after checking for unmerged unique work. |
| `.claude/worktrees/` | Preserve unique changes/commits, then remove completed worktrees through Git. Do not recursively delete registered worktrees blindly. |
| `output/` | Keep active search checkpoints, source-verification material, research prompts/queues, reviewed digitization work, current fidelity artifacts and required calibration ancestry until migrated. Delete reproducible stale runs, temporary images, duplicate parity exports and dated wrappers afterward. |
| `../clash-lab-bs`, `../clash-lab-vid` | Keep until writers merge and workspace gates pass. Remove only after unique-work reconciliation. |
| `../clash-lab-parity` | No final runtime dependency. Preserve required historical provenance and unique work, then retire the worktree. Goldens already contain the battle inputs. |
| `../clash-lab-bench` | Retain useful benchmark recipes/results, then retire the detached worktree after uniqueness checks. |
| `../clash-lab-legacy-archive` | **Leave untouched.** It contains the old `run.py`, tests and `verify.py`; respect the preserved-checkout rule. |
| Original October 3 checkout / preserved baseline | **Leave untouched.** |
| `.venv/`, Python caches, Black cache | Delete after the last Python-dependent migration gate. |
| `pyproject.toml` | Delete when Python is removed. |
| `.github/workflows/*` | Replace Python/Black jobs with workspace Rust verification on Linux and Windows. |

Git currently reports several Windows-form worktree registrations as prunable from WSL. That is not sufficient evidence that the worktrees are disposable: both named active worktrees exist. Reconcile paths and ownership before any future prune/remove operation.

**Documentation keep/merge/delete list**

| Current documentation | Disposition |
|---|---|
| `GOLDEN.md`, `PARAMS.md`, `SCOUTING.md`, `FIDELITY_RUST.md`, `ENGINE_V2.md` | Keep and update under engine/tool documentation |
| `ENGINE_STATUS.md`, `GOAL.md`, `ROADMAP.md`, `GAP_ANALYSIS.md`, `BUG_LEDGER.md`, `audit-ledger.md` | Consolidate into current scope/status, roadmap and issue/evidence ledger; preserve unresolved limitations |
| `BASE_DESIGN_PRINCIPLES.md`, `BASE_SEARCH_CONTRACTS.md`, `BASE_SEARCH_RUST_DESIGN.md` | Keep as base-search architecture/contracts |
| `BASE_SEARCH_M1_REPORT.md`, worktree `BASE_SEARCH_M2.md` | Retain implementation/proof records with dated scope; do not present M2 as completed production search |
| `PB1A.md`, `PB1B.md`, `RM1_EVIDENCE.md` | Retain corrections/evidence tied to current behavior and goldens |
| `playbook-extraction.md`, `playbook-consolidation.md`, `playbook-completion.md` | Keep as provider-independent pipeline contracts/prompts |
| `SIMULATION_METHODS_RESEARCH.md`, `RESEARCH-2026-10.md`, `WIKI_DIGEST.md` | Keep useful cited source research; remove stale execution instructions |
| `SIM_ACCURACY.md`, `VIDEO_MEASUREMENTS.md`, `VIDEO_SHOTLIST.md`, `PROBE_CARDS.md`, `BUILDER_SCREENSHOTS.md` | Keep relevant measurement/digitization contracts; separate private observations and update native commands |
| `ATTACK_AUDIT.md`, `REDTEAM.md`, `MOVE_LIBRARY_DESIGN.md`, `NEW_STRATEGIES.md` | Merge retained mechanics/search requirements and cited recipes into current docs; delete redundant originals afterward |
| `TH16_USE_NOW_GUIDE.md` | Remove personal account advice from the repository; retain reusable public recipe material elsewhere if needed |
| `RUST_REVIEW_2026-10-25.md` | Transfer open findings into the migration/issue ledger; retire completed review narrative |
| `RUST_PORT.md`, `rust-spike-spec.md` | Delete superseded port instructions after documenting final architecture and historical baseline |
| `docs/legacy/**` | Delete obsolete prototype/checkpoint documentation after transferring still-applicable mechanics decisions and provenance |
| `LOCAL_CLIENT_EVIDENCE.md`, specified local-static audit JSON | Delete |
| Other `docs/evidence/*.json` | Retain only evidence referenced by surviving claims; preserve dated/synthetic scope |
| `docs/video-evidence/**` | Private media by default; retain only explicitly distributable material with provenance |
| `rust/FIELD_PROFILING.md` | Move to engine performance documentation |
| `rust/vidmine/README.md` | Merge into native video-tool documentation |

Rewrite `README.md` around workspace installation/building, `clash` commands, data/private inputs, verification, and the simulator’s actual supported scope.

Rewrite `AGENTS.md` to require:

- Workspace Rust formatting and `scripts/verify.sh`.
- Preservation of v29 behavior, deterministic math and explicit unsupported-content checks.
- No golden regeneration for organizational changes.
- Synthetic regression fixtures clearly distinguished from real-game accuracy evidence.
- No personal observations/media/credentials or memory workflows in Git.
- Explicit file ownership and integration-lead ownership of shared boundaries.
- No edits to protected historical checkouts.

The existing README and CI reference root `verify.py` and `run.py`, which are absent from this checkout. The final instructions must describe working native entry points.

Suggested ignore rules:

```gitignore
/target/
/output/
/private/
/work/
/data/cache/
/data/live/
/profiles/private/
/.claude/worktrees/

.venv/
venv/
__pycache__/
*.py[cod]
.black-cache/
.pytest_cache/

.env
.env.*
*.log
```

Keep specific private/media directory ignores rather than globally ignoring every image: distributable vidmine templates and synthetic image fixtures can be legitimate tracked inputs. Adding ignore rules does not untrack existing personal files.

---

**5. Execution order, gates and writer ownership**

**G0 — finish and reconcile the in-flight work first**

1. Let the main compiler/playbook writers and both worktree writers finish.
2. Merge base-search additions and video changes selectively.
3. Inventory new files again; the plan reflects the currently observed M2/video state.
4. Resolve existing failures through the responsible owners.
5. Freeze the accepted source/data state and record hashes of all golden files and pinned catalogs.

The base-search report records a blocked verification state from its own earlier inputs. Treat that as historical evidence, not a current test result. Do not regenerate goldens to make the reorganization pass.

**G1 — establish the native gate before moving modules**

Replace the current verification script’s output-grep-based build/test checks. A failing Cargo command must fail directly; its output does not need to contain a particular word. [Current script](../rust/verify.sh)

The workspace gate should run:

```sh
set -euo pipefail

cargo fmt --all -- --check
cargo build --workspace --all-targets --release --locked --offline
cargo test --workspace --all-targets --release --locked --offline
cargo clippy --workspace --all-targets --locked --offline -- -D warnings
```

Then invoke native checks with explicit catalog, fixtures, account and temporary output paths:

- Battle goldens.
- Plan goldens.
- Guardian fixtures.
- Armysearch proof, including its existing 4,096 fuzz cases.
- Layout admission/geometry/inventory proof.
- Base-search proposal proof.
- Vidmine synthetic tests.
- Fidelity/dataimport/playbook synthetic tests as their ports land.

Provision dependencies separately from verification. Verification itself should not fetch data, install tools, contact providers, or mutate fixtures.

Use temporary directories with reliable cleanup. Preserve command failure statuses through logging pipelines.

**G2 — break boundaries, then move mechanically**

Integration lead owns all changes to:

- Root workspace/lockfile/toolchain.
- Crate roots and public boundary re-exports.
- Data wire helpers and `Node` extraction.
- Executor→armies helper removal.
- Resource paths and provenance identities.
- Shared fixture preparation.
- Golden/verification wiring.

Gate after boundary changes and again after relocation:

- Identical golden file hashes.
- Identical battle results/traces and compiled plans.
- Existing unsupported-content rejection cases still fail.
- Worker-count determinism remains intact.
- Verification works from outside the repository directory with explicit paths.
- No accidental live-account overlay.

Do not combine mechanics cleanup, parser replacement, math changes, or new scoring policy with this phase.

**G3 — parallel port work after boundaries are frozen**

| Task | Exclusive ownership | Scope | Estimate |
|---|---|---|---:|
| A. Search completion | `clash-basesearch/**`, `clash-armysearch/**` | Evaluator/coordinator, QD, refinement, diagnostics, surrogate/policy training, compare/explain/report | 10–16 days |
| B. Catalog/source pipeline | Dataimport `catalog/`, `registry/`, `csv/`, `wiki/`, `manifest/`, `patch/` | Native catalog regeneration, source precedence, wiki normalization, manifests, patch checks | 8–12 days |
| C. Observation ingestion/fidelity | Dataimport `battlelog/`, `snapshots/`; `clash-fidelity/**` | Keyless providers, archive collection, snapshot recording, remaining calibration/replay parity | 4–7 days |
| D. Digitization/presentation | Dataimport `digitize/`; layout rendering module | Grid fitting, walls, overlays, manual edits, explicit imputation, guides | 6–10 days |
| E. Playbook/research pipeline | `clash-playbook-tools/**` | Discovery/transcripts, extraction/review queues, citation checking, completion and timing data | 5–8 days |
| F. Video migration | `clash-vidmine/**` | Worktree integration, library entry point, resources, batch processing and portable fixtures | 2–4 days |

These ownership boundaries allow separate writers without shared-kernel edits. The integration lead alone wires new public modules and umbrella commands. Writers propose interface changes to the lead instead of editing another owner’s crate root.

With three writers, schedule these as lanes; they are not six simultaneous shared-directory assignments.

**Port acceptance gates**

| Capability | Required gate before deleting Python |
|---|---|
| Catalog builder | Reproduce pinned registry/catalog payloads, ordered tables, numeric values and source hashes; then pass engine goldens |
| Rules importer | Same rules identity/content for pinned inputs; admission and inventory proofs pass |
| Search | Same legal-input constraints, declared budgets, resume rejection rules, deterministic logical seeds, paired evaluation and independent final evaluation |
| Surrogate/policy | Native training and inference; deterministic model inputs/serialization, documented numerical tolerance where solver differences matter |
| Fidelity | Decoder preservation/rejection, UTC snapshot boundaries, canonical hashes, ancestry validation, fitting/evaluation separation |
| Digitizer | Synthetic projection/detection fixtures, reviewed real private examples, retained manual edits, complete imputation receipt |
| Playbook pipeline | Quote normalization, four-line location window, timing checks, vocabulary/dependency validation and provenance behavior |
| Vidmine | Existing tests plus worktree spatial checks; explicit weak/ambiguous evidence rejection; no source downloads in verification |
| Python removal | Native commands work with Python unavailable; no required Python-backed executable/provider remains |

Catalog regeneration must compute data from source inputs. Reading the existing generated catalog and writing it back is not completion of the port.

**G4 — delete predecessors and clean data/docs**

Delete Python by accepted capability group, not all at once. Remove obsolete shell wrappers, embedded Python, `.venv`, `pyproject.toml`, stale CI, and dead source directories after the final group passes.

Move personal tracked files to ignored/private ownership while preserving any observations still needed by private workflows. Preserve calibration ancestry before deleting old `output/overnight` material.

Delete the excluded memory workflow independently; it is not a port prerequisite.

**G5 — final workspace acceptance**

- Root workspace is the only supported build.
- One lockfile and release profile.
- Full Linux and Windows verification passes.
- All three golden files retain their frozen bytes.
- Engine dependency closure contains no tool crates.
- Public library APIs and private input selection are documented.
- Every retained workflow has a native command.
- No required Python, PowerShell, scratch-path wrapper, sibling checkout, live API key, or ignored source file is needed for portable verification.
- Protected historical checkouts remain untouched.

Allow **45–74 engineer-days overall**, including approximately 8–13 days for baseline reconciliation, boundary/workspace migration, integration and final cleanup. With three writers and an integration lead sharing some implementation work, plan roughly **5–8 weeks after the in-flight work merges**. The largest uncertainties are full catalog regeneration and the base-search coordinator/diagnostics work still beyond M2.
