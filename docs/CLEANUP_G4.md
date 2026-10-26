# Cleanup G4 — 2026-10-25

Checkout: `/mnt/c/Users/jarod/Documents/clash-lab`, branch `sim-accuracy`,
starting HEAD `f04706c`. No commit, index write or download was performed.
No `.rs` file or `Cargo.toml` was edited; `data/` was not modified. Protected
historical checkouts and other worktrees were not touched.

Classified all **184** Python/shell/PowerShell files actually present
under `src/`, `tools/` and `scripts/`, excluding `scripts/verify.sh`:
**134 deleted**, **50 retained** (49 Python files and one audit shell).
The plan’s earlier 193-file inventory describes another revision; the tables
below cover every file in this checkout, including duplicate toolkit filenames.

Original output file content: **2,894,745,223 B (2760.64 MiB)**.
Retained output content: **1,408,802,213 B (1343.54 MiB)**; removed output content:
**1,485,943,010 B (1417.11 MiB)**. Directory metadata is excluded.

## Limits and pending work

- All files under `output/` were moved or deleted. The empty `output/restructure/`
  directory cannot be removed (`Permission denied`), so its empty parent remains.
- Empty `.agents`, `.aws` and `.codex` are protected mount points; `rmdir` returns
  `Device or resource busy`. They contain no files. `.black-cache/` was deleted.
- `scripts/verify.sh` passed formatting, offline build and workspace tests, then
  stopped at the existing Clippy `never_loop` error in
  `crates/clash-armysearch/src/fix_proof.rs:694`. The strict pass also reports other
  pre-existing warnings. Lane F owns that Rust work; no suppression or source
  change was made here. The remaining goldens/proofs were run separately and passed.
- Root `verify.py` is absent: the required attempted `python3 -B verify.py` fails
  with file-not-found. Active docs and CI now use the native workspace gate.
- Legacy calibration/training clients remain unported compatibility code. Their
  data defaults/ancestry are not upgraded by this cleanup. Existing data manifests
  describe the old source tree; rebuilding/rebinding them is a separate reviewed
  data step. No fit, catalog, registry, golden or measurement was regenerated.

## Byte inventory

File-content bytes before/after; excludes Git metadata, build targets and
directory allocation. The local manifest/index add a small amount of bookkeeping.

| Location | Before | After | Decision |
| --- | ---: | ---: | --- |
| `src/` | 1,871,519 | 1,057,614 | Retain only the unported clients’ import closure. |
| `tools/` | 778,031 | 136,505 | Remove replaced entry points; retain unported workflows. |
| `scripts/` | 2,304 | 2,304 | Keep verify.sh unchanged. |
| `examples/` | 9,163,603 | 0 | Obsolete v29 prototype collection; no live root references. |
| `profiles/` | 122,617 | 0 | Synthetic account to fixtures; personal JSON to private; obsolete preset deleted. |
| `work/` | 3,080,781 | 0 | Excluded reverse-local acquisition scratch; no live callers. |
| `private/` | 0 | 101,843 | Keep both personal inputs; directory was initially empty. |
| `output/` | 2,894,745,223 | 0 | No file contents remain; blocked empty directory shells only. |
| `.black-cache/` | 20,134 | 0 | Disposable cache deleted. |
| `docs/` | 2,438,568 | 1,700,327 | Current contracts, archived useful history and stale-document removal. |
| `.venv/` | 487,589,500 | 487,589,500 | Python workflows still need installed dependencies; no download/reinstall. |
| `local/` | 0 | 1,417,946,623 | Ignored private store, including moved data, manifest/index and G4 receipts. |
| `pyproject.toml` | 286 | 286 | Retained with Python and Black 24.10.0. |

## Output moves and deletion policy

| Original collection | Destination | Retention / deletion reason |
| --- | --- | --- |
| `output/web-videos` | `local/web-videos` | Keep JSON/JSONL attack observations, keyframes, army/slot icon crops. Delete full frames and redundant generated tables/logs; cited small exceptions go to evidence. |
| `output/sources` | `local/sources` | Keep transcripts, video index and raw/checked authoring outputs. Remove execution scripts. |
| `output/research` | `local/research` | Keep prompts, queues and research findings; no provider re-execution. |
| `output/checks` | `local/research/audits` | Keep audit/number finding markdown and prompts needed by retained validators; remove scratch execution/report residue unless cited. |
| `output/playbook-review` | `local/reviews/playbooks` | Keep review records and probe evidence; no source helper is executed. |
| `output/fidelity-rust` | `local/fidelity` | Keep all fit/report/prepared-job/outcome ancestry; original embedded paths/hashes remain historical. |
| `output/ranked-bases-2026-10-24` | `local/digitize/ranked-bases-2026-10-24` | Keep per-base transcription/grid/layout/reports, reviewed walls in layout.json and original screenshots. Delete generated images/crops/contact sheets. |
| `output/ranked-bases-2026-10-25-th18` | `local/digitize/ranked-bases-2026-10-25-th18` | Keep buildings.txt, grid.json, walls*.json, wall-runs, layout/report/uncertainties/attacker metadata, results.json and original screenshots. Delete crops/contact sheets/overlays. |
| `output/armysearch/run2` | `local/armysearch/run2` | Keep reports, summary, army candidates, archive/checkpoint, holdout and identity manifests. Delete binary, duplicate catalog and logs. |
| `other small cited output artifacts` | `local/evidence/<original-relative-path>` | Retain files smaller than 1,000,000 bytes that a pre-cleanup committed document cites; record each citation in the local manifest. Larger/regenerable uncited artifacts are deleted. |
| `all other output files` | `deleted` | Old parity runs, evaluations, speedproof, overnight logs, hunt output, scratch programs and images are disposable, except the cited small evidence rule. |

Every individual output move/deletion, with its reason and exact file size, is
recorded in the ignored [local manifest](../local/cleanup-G4-manifest.json).
The [local index](../local/README.md) lists collections. Historical artifact
payloads are byte-preserved; only live docs/scripts have path references updated.

Additional moves:

- `profiles/sample-th16.json` → `fixtures/accounts/sample-th16.json`: declared
  synthetic account; byte-preserved. No current caller uses the former root.
- `profiles/private/api-player.json` and `battlelog.json` → `private/profiles/`:
  personal data, preserved and ignored. `private/` was empty at intake; these
  two files are its complete post-cleanup contents. Nothing personal was deleted.
- `tools/baselab/digitize_kit/{bp,cc}_buildings.txt` →
  `local/digitize/legacy-inputs/`: reviewed transcriptions, not scratch programs.
- Five `docs/video-evidence/*.jpg` → `local/evidence/video/`: keep measurement
  stills private because distribution provenance/license is not established.

Legacy-root reference checks scanned `crates/`, `scripts/`, `fixtures/` and
`data/` for actual `examples/`, `profiles/`, `work/`, `.agents/`, `.aws/`,
`.codex/` and `.black-cache/` roots. There were no live root references.
`/tmp/vidmine-work/` is an unrelated native temporary directory, not `work/`.
All 223 old example files, the obsolete inventory preset and 25 reverse-local
work files were removed; their complete names/sizes/reasons are in the manifest.

## Python and shell disposition

STILL NEEDED means a complete consuming workflow has no native replacement.
Many dependencies already have native runtime/search equivalents; deleting
those Python APIs before their fitting/label-generation clients are ported
would break the surviving workflows. No second engine/compiler port is proposed.

| Retained file | Why it remains | Port needed before removal |
| --- | --- | --- |
| `src/baselab/__init__.py` | Package glue for the retained unported workflow dependencies. | Remove after the final Python clients are ported; no separate package-glue port. |
| `src/baselab/archetypes.py` | Imported by retained charge_screen, funnel, policy_screen, train_policy workflows. Its production search/scoring counterpart is native. | Port the remaining fitting/label-generation caller and use native account/plan/search/scoring APIs; then remove this Python adapter. |
| `src/baselab/deploy.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/diagnose.py` | Imported by retained funnel workflows. Its production search/scoring counterpart is native. | Port the remaining fitting/label-generation caller and use native account/plan/search/scoring APIs; then remove this Python adapter. |
| `src/baselab/engine/battle.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/engine/defense.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/engine/effects.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/engine/entities.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/engine/heroes.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/engine/pets.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/engine/plans.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/engine/playbook.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/engine/result.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/engine/specs.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/engine/spells.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/engine/stats.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate, xcheck_stats. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/engine/traps.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/engine/units.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/evaluate.py` | Imported by retained calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy workflows. Its production search/scoring counterpart is native. | Port the remaining fitting/label-generation caller and use native account/plan/search/scoring APIs; then remove this Python adapter. |
| `src/baselab/evolve.py` | Imported by retained funnel workflows. Its production search/scoring counterpart is native. | Port the remaining fitting/label-generation caller and use native account/plan/search/scoring APIs; then remove this Python adapter. |
| `src/baselab/gamedata.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate, xcheck_stats. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/generator.py` | Imported by retained calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy workflows. Its production search/scoring counterpart is native. | Port the remaining fitting/label-generation caller and use native account/plan/search/scoring APIs; then remove this Python adapter. |
| `src/baselab/layout.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/loadouts.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/mechanics.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/meta_armies.py` | Imported by retained calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy workflows. Its production search/scoring counterpart is native. | Port the remaining fitting/label-generation caller and use native account/plan/search/scoring APIs; then remove this Python adapter. |
| `src/baselab/optimize.py` | Imported by retained funnel workflows. Its production search/scoring counterpart is native. | Port the remaining fitting/label-generation caller and use native account/plan/search/scoring APIs; then remove this Python adapter. |
| `src/baselab/pathing.py` | Imported compatibility/model dependency of calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy, train_surrogate. Native runtime/catalog capabilities already exist. | Port aggregate/meta calibration, policy and surrogate clients to native jobs/data, then remove this dependency; do not port a second engine. |
| `src/baselab/policy.py` | Policy parameter execution and fitting helpers are imported by retained calibration/training clients. | Native train-policy workflow; native loading/execution alone does not replace fitting. |
| `src/baselab/redteam.py` | Imported by retained calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy workflows. Its production search/scoring counterpart is native. | Port the remaining fitting/label-generation caller and use native account/plan/search/scoring APIs; then remove this Python adapter. |
| `src/baselab/rust_bridge.py` | Retained trainers/evaluation optionally dispatch prepared batches to native clash jobs. | Port the remaining trainers to native APIs/CLI; then remove Python serialization/glue. |
| `src/baselab/surrogate.py` | Feature extraction, ridge/GBM inference and serialization are imported by funnel/train_surrogate. | Native base-search surrogate features/training/inference; deferred by the base-search lane. |
| `src/baselab/tactics.py` | Imported by retained calibrate, calibrate_meta, charge_screen, funnel, patch_update, policy_screen, train_policy workflows. Its production search/scoring counterpart is native. | Port the remaining fitting/label-generation caller and use native account/plan/search/scoring APIs; then remove this Python adapter. |
| `tools/baselab/audit_fanout.sh` | Category-specific mechanic audit authoring is explicitly outside the playbook queue port. | Configured native category-audit jobs; retain explicit provider selection and offline ledger checks. |
| `tools/baselab/calibrate.py` | Aggregate-target strength sweeps are not ported by native defense fitting. | clash fidelity aggregate-target fitting and native generated-base jobs. |
| `tools/baselab/calibrate_meta.py` | Per-build/family fitting, fallback and provenance are not ported. | clash fidelity meta fitting with explicit accounts/targets and ancestry. |
| `tools/baselab/charge_screen.py` | Hero-charge parameter screening still supports policy research. | clash armysearch policy/charge screen over native prepared jobs. |
| `tools/baselab/data_manifest.py` | General source/artifact freshness manifest is not supplied by native catalog construction. | clash dataimport manifest build/check for complete workspace groups and derived bindings. |
| `tools/baselab/funnel.py` | Mixed file: labeled data generation and group-held-out surrogate training remain unported; production search is native. | Native surrogate label-generation/train commands; retire the legacy screen branch with this port. |
| `tools/baselab/patch_update.py` | CSV/registry diffs and citation/rebuild planning remain unported; report now invokes the native gate. | clash dataimport patch diff/cites/report, extending citation scans to native sources. |
| `tools/baselab/policy_screen.py` | Learned-policy comparison/screening has no native training interface. | clash armysearch policy screen and grouped validation. |
| `tools/baselab/recommend_armies.py` | Account/personalization helpers are imported by retained meta-army/red-team code; standalone ranking is native. | Migrate retained trainers to native account/compiler APIs, then remove this helper dependency. |
| `tools/baselab/train_policy.py` | Parameter-policy fitting is outside the existing native composition search. | clash armysearch train-policy with saved training identity. |
| `tools/baselab/train_surrogate.py` | Ridge model fitting and held-out ranking validation remain unported. | clash basesearch train-surrogate/proof, subject to the deferred equal-battle-budget benefit experiment. |
| `tools/baselab/verify_audit.py` | Wiki quote checks and finding-status ledger are explicitly outside the playbook port. | clash playbook audit-ledger verify, preserving statuses and source quotes. |
| `tools/baselab/verify_numbers.py` | Checks field claims in the retained source-number audit reports. | Native source-field citation/ledger validator. |
| `tools/baselab/wiki_digest.py` | Human review digest generation remains unported. | clash dataimport wiki digest. |
| `tools/baselab/wiki_mirror.py` | Wiki acquisition/cache refresh has no native equivalent; catalog consumes an existing mirror. | clash dataimport wiki acquisition with revisions, retries and caching. |
| `tools/baselab/wiki_tables.py` | HTML rowspan/colspan normalization is not part of the native normalized-input builder. | clash dataimport wiki normalize for the pinned table/text schema. |
| `tools/baselab/xcheck_stats.py` | Independent published/wiki/runtime number comparison remains unported. | Native source cross-check diagnostics with explicit precedence. |

Keep `src/baselab/` and `tools/baselab/` for this dependency closure, and keep
`pyproject.toml` plus `.venv/`. The installed local environment contains Black
24.10.0, NumPy 2.2.6, SciPy 1.15.3, Beautiful Soup 4.15.0, Requests 2.31.0 and
Pillow 12.3.0. It is a Windows environment; the Linux smoke checks use its pure
Python packages only. No training or personal calibration was executed.

| Deleted file | Disposition / command or reason |
| --- | --- |
| `src/baselab/macro_moves.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `src/baselab/registry.py` | REPLACED: clash dataimport catalog; clash layout rules derive |
| `src/baselab/render.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `src/baselab/uncertainty.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `src/baselab/unconventional.py` | UNUSED: dated surrogate proof tied to removed old logs and excluded memory-layout parents; retain generic surrogate training, not this obsolete experiment. |
| `tools/baselab/ab_guided.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/ab_test.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/adaptive_check.py` | REPLACED: clash armysearch run/proof; clash plan compile/check; clash score |
| `tools/baselab/army_bench.py` | REPLACED: clash armysearch run/proof; clash plan compile/check; clash score |
| `tools/baselab/army_guide.py` | UNUSED: dated publication/report composition; all callers retired, native search reports retained. |
| `tools/baselab/attack_lab.py` | REPLACED: clash armysearch run/proof; clash plan compile/check; clash score |
| `tools/baselab/attack_search.py` | REPLACED: clash armysearch run/proof; clash plan compile/check; clash score |
| `tools/baselab/audit_usage.sh` | REPLACED: clash playbook extract/queue usage/queue audit with configured providers and offline checks. |
| `tools/baselab/base_noise.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/build_guide.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/build_report.py` | UNUSED: dated publication/report composition; all callers retired, native search reports retained. |
| `tools/baselab/calibrate_defenses.py` | REPLACED: clash fidelity (replay/observed/board/calibrate/cv) |
| `tools/baselab/check_consolidated.py` | REPLACED: clash playbook (harvest/transcripts/extract/verify/consolidate/complete/gaps/queue) |
| `tools/baselab/check_playbook.py` | REPLACED: clash playbook (harvest/transcripts/extract/verify/consolidate/complete/gaps/queue) |
| `tools/baselab/compare_layouts.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/complete_digitized.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/contact_sheet.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/decode_battlelog.py` | REPLACED: clash dataimport battlelog (decode/collect/snapshot add/list/for-battle/report) |
| `tools/baselab/detect_walls.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/ascii.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/batch_b/build.py` | REPLACED: clash dataimport digitize (capability-consolidated toolkit); duplicate toolkit filenames are separately inventoried. |
| `tools/baselab/digitize_kit/batch_b/conv.py` | REPLACED: clash dataimport digitize (capability-consolidated toolkit); duplicate toolkit filenames are separately inventoried. |
| `tools/baselab/digitize_kit/batch_b/dewm.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/batch_b/full.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/batch_b/gal2.py` | REPLACED: clash dataimport digitize (capability-consolidated toolkit); duplicate toolkit filenames are separately inventoried. |
| `tools/baselab/digitize_kit/batch_b/gapfill.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/batch_b/lat.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/batch_b/proj.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/batch_b/rul.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/batch_b/seed.py` | REPLACED: clash dataimport digitize (capability-consolidated toolkit); duplicate toolkit filenames are separately inventoried. |
| `tools/baselab/digitize_kit/batch_b/symfix.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/batch_b/walls4.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/batch_b/wclean.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/batch_b/win.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/blobs.py` | UNUSED: excluded memory-derived pipeline or hardcoded acquisition/port scratch experiment; no supported port. |
| `tools/baselab/digitize_kit/build.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/cands.py` | UNUSED: excluded memory-derived pipeline or hardcoded acquisition/port scratch experiment; no supported port. |
| `tools/baselab/digitize_kit/ccparse.py` | UNUSED: excluded memory-derived pipeline or hardcoded acquisition/port scratch experiment; no supported port. |
| `tools/baselab/digitize_kit/cfit.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/chk2.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/chk3.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/chkmap.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/conv.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/diff.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/dots.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/fh.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/finalize.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/fitoff.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/fitoff2.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/gal.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/gal2.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/gl.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/hfit.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/inv.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/merge_impute.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/ov.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/ovl.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/ovt.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/ovw.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/pads.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/pads2.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/palewalls.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/probe.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/resolve.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/rt.sh` | UNUSED: dated or hardcoded scratch/orchestration wrapper; native search/proof commands are the maintained entry points. |
| `tools/baselab/digitize_kit/seed.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/sheet.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/snap.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/vfit.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/walls2.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/walls3.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/wd.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/wfit.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/win.sh` | UNUSED: dated or hardcoded scratch/orchestration wrapper; native search/proof commands are the maintained entry points. |
| `tools/baselab/digitize_kit/wins.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/zoom.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/zt.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/ztw.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/digitize_kit/zw.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/engine_coverage.py` | REPLACED: clash golden check; clash golden plans check; clash simulate trace; cargo test -p clash-engine --offline |
| `tools/baselab/evolve_bases.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/explain_base.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/extract_playbooks.sh` | REPLACED: clash playbook extract/queue usage/queue audit with configured providers and offline checks. |
| `tools/baselab/fidelity_board.py` | REPLACED: clash fidelity (replay/observed/board/calibrate/cv) |
| `tools/baselab/fill_pockets.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/final_compare.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/final_eval.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/fingerprint.py` | REPLACED: clash golden check; clash golden plans check; clash simulate trace; cargo test -p clash-engine --offline |
| `tools/baselab/finish_digitized.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/grid_overlay.py` | REPLACED: clash dataimport digitize (fit/walls/trace/build/convert/complete/seed/overlay/guide/inspect) |
| `tools/baselab/guided_test.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/harvest_videos.py` | REPLACED: clash playbook (harvest/transcripts/extract/verify/consolidate/complete/gaps/queue) |
| `tools/baselab/hero_banners.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/import_memory_layouts.py` | UNUSED: excluded memory-derived pipeline or hardcoded acquisition/port scratch experiment; no supported port. |
| `tools/baselab/make_reference_bases.py` | UNUSED: excluded memory-derived pipeline or hardcoded acquisition/port scratch experiment; no supported port. |
| `tools/baselab/mechanic_tests.py` | REPLACED: clash golden check; clash golden plans check; clash simulate trace; cargo test -p clash-engine --offline |
| `tools/baselab/merge_completion.py` | REPLACED: clash playbook (harvest/transcripts/extract/verify/consolidate/complete/gaps/queue) |
| `tools/baselab/optimize_base.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/playbook_check.py` | REPLACED: clash armysearch run/proof; clash plan compile/check; clash score |
| `tools/baselab/predictor_proof.py` | UNUSED: dated surrogate proof tied to removed old logs and excluded memory-layout parents; retain generic surrogate training, not this obsolete experiment. |
| `tools/baselab/proof_macro.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/proof_paired.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/proof_proxy.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/proof_repair.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/proof_scorer.py` | UNUSED: dated surrogate proof tied to removed old logs and excluded memory-layout parents; retain generic surrogate training, not this obsolete experiment. |
| `tools/baselab/qd_search.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/redteam_check.py` | REPLACED: clash armysearch run/proof; clash plan compile/check; clash score |
| `tools/baselab/replay_log.py` | REPLACED: clash fidelity (replay/observed/board/calibrate/cv) |
| `tools/baselab/replay_observed.py` | REPLACED: clash fidelity (replay/observed/board/calibrate/cv) |
| `tools/baselab/research_usage.sh` | REPLACED: clash playbook extract/queue usage/queue audit with configured providers and offline checks. |
| `tools/baselab/run_batch.sh` | UNUSED: dated or hardcoded scratch/orchestration wrapper; native search/proof commands are the maintained entry points. |
| `tools/baselab/run_deep.sh` | UNUSED: dated or hardcoded scratch/orchestration wrapper; native search/proof commands are the maintained entry points. |
| `tools/baselab/run_originals.sh` | UNUSED: dated or hardcoded scratch/orchestration wrapper; native search/proof commands are the maintained entry points. |
| `tools/baselab/run_originals_funnel.sh` | UNUSED: dated or hardcoded scratch/orchestration wrapper; native search/proof commands are the maintained entry points. |
| `tools/baselab/run_overnight.sh` | UNUSED: dated or hardcoded scratch/orchestration wrapper; native search/proof commands are the maintained entry points. |
| `tools/baselab/run_post.sh` | UNUSED: dated or hardcoded scratch/orchestration wrapper; native search/proof commands are the maintained entry points. |
| `tools/baselab/rust_export.py` | REPLACED: clash dataimport catalog; clash layout rules derive |
| `tools/baselab/rust_spike.py` | UNUSED: excluded memory-derived pipeline or hardcoded acquisition/port scratch experiment; no supported port. |
| `tools/baselab/score_reference.py` | REPLACED: clash golden check; clash golden plans check; clash simulate trace; cargo test -p clash-engine --offline |
| `tools/baselab/scorer_check.py` | REPLACED: clash golden check; clash golden plans check; clash simulate trace; cargo test -p clash-engine --offline |
| `tools/baselab/snapshot.py` | REPLACED: clash dataimport battlelog (decode/collect/snapshot add/list/for-battle/report) |
| `tools/baselab/snapshot_log.py` | REPLACED: clash dataimport battlelog (decode/collect/snapshot add/list/for-battle/report) |
| `tools/baselab/step_gaps.py` | REPLACED: clash playbook (harvest/transcripts/extract/verify/consolidate/complete/gaps/queue) |
| `tools/baselab/tactics_check.py` | REPLACED: clash armysearch run/proof; clash plan compile/check; clash score |
| `tools/baselab/test_base.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/trace_diff.py` | REPLACED: clash golden check; clash golden plans check; clash simulate trace; cargo test -p clash-engine --offline |
| `tools/baselab/trap_polish.py` | REPLACED: clash basesearch run/proof/proof-completion; clash score; clash layout render |
| `tools/baselab/yt_transcript.py` | REPLACED: clash playbook (harvest/transcripts/extract/verify/consolidate/complete/gaps/queue) |

All Python bytecode under `src/` and `tools/` and the Black cache were also
deleted. The retained audit shell now writes `local/research/audits/` and asks
about native engine sources. The patch helper prints native catalog rebuilding
and invokes `scripts/verify.sh`; source-manifest/provenance patterns now cover
the workspace paths. The retained Rust bridge selects `clash` through
`BASELAB_ENGINE_EXE` or `CARGO_TARGET_DIR`. Black 24.10.0 formats retained Python.

## Document classification

The [current index](README.md) lists the surviving active contracts and tools.
[history/README.md](history/README.md) indexes all useful dated records.
Historical filenames and Python/parity instructions in archival or acceptance
sections are explicitly marked as provenance, not current execution commands.
Current engine/status, roadmap, fidelity and accuracy pages were rewritten.

| Original document | Classification and resulting location | Reason |
| --- | --- | --- |
| `docs/ATTACK_AUDIT.md` | historical → `docs/history/ATTACK_AUDIT.md` | Historical research or milestone receipt; superseded execution/status claims, useful mechanics and evidence retained. |
| `docs/BASE_DESIGN_PRINCIPLES.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/BASE_SEARCH_CONTRACTS.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/BASE_SEARCH_M1_REPORT.md` | historical → `docs/history/BASE_SEARCH_M1_REPORT.md` | Historical research or milestone receipt; superseded execution/status claims, useful mechanics and evidence retained. |
| `docs/BASE_SEARCH_M2.md` | historical → `docs/history/BASE_SEARCH_M2.md` | Historical research or milestone receipt; superseded execution/status claims, useful mechanics and evidence retained. |
| `docs/BASE_SEARCH_RUST_DESIGN.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/BUG_LEDGER.md` | historical → `docs/history/BUG_LEDGER.md` | Historical research or milestone receipt; superseded execution/status claims, useful mechanics and evidence retained. |
| `docs/BUILDER_SCREENSHOTS.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/DATA_PIPELINE.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/ENGINE_STATUS.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/ENGINE_V2.md` | historical → `docs/history/ENGINE_V2.md` | Historical research or milestone receipt; superseded execution/status claims, useful mechanics and evidence retained. |
| `docs/FIDELITY_RUST.md` | historical → `docs/history/FIDELITY_RF1.md`; active path rewritten as current | Retain dated observation/port evidence; replace active path with current native workflow. |
| `docs/FIELD_PROFILING.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/GAP_ANALYSIS.md` | historical → `docs/history/GAP_ANALYSIS.md` | Historical research or milestone receipt; superseded execution/status claims, useful mechanics and evidence retained. |
| `docs/GOAL.md` | historical → `docs/history/GOAL.md` | Historical research or milestone receipt; superseded execution/status claims, useful mechanics and evidence retained. |
| `docs/GOLDEN.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/MOVE_LIBRARY_DESIGN.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/NEW_STRATEGIES.md` | historical → `docs/history/NEW_STRATEGIES.md` | Historical research or milestone receipt; superseded execution/status claims, useful mechanics and evidence retained. |
| `docs/PARAMS.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/PB1A.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/PB1B.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/PLAYBOOK_PIPELINE.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/PROBE_CARDS.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/REDTEAM.md` | historical → `docs/history/REDTEAM.md` | Historical research or milestone receipt; superseded execution/status claims, useful mechanics and evidence retained. |
| `docs/RESEARCH-2026-10.md` | historical → `docs/history/RESEARCH-2026-10.md` | Historical research or milestone receipt; superseded execution/status claims, useful mechanics and evidence retained. |
| `docs/RESTRUCTURE_LOG.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/RESTRUCTURE_PLAN.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/RM1_EVIDENCE.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/ROADMAP.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/RUST_PORT.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/RUST_REVIEW_2026-10-25.md` | historical → `docs/history/RUST_REVIEW_2026-10-25.md` | Historical research or milestone receipt; superseded execution/status claims, useful mechanics and evidence retained. |
| `docs/SCOUTING.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/SIMULATION_METHODS_RESEARCH.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/SIM_ACCURACY.md` | historical → `docs/history/SIM_ACCURACY_2026-10-20.md`; active path rewritten as current | Retain dated observation/port evidence; replace active path with current native workflow. |
| `docs/TH16_USE_NOW_GUIDE.md` | stale → deleted | STALE: personal account advice or superseded Python/Rust spike procedure. |
| `docs/VIDEO_MEASUREMENTS.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/VIDEO_SHOTLIST.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/WIKI_DIGEST.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/audit-ledger.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/evidence/duke-contact-summary.json` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/evidence/duke-half-step-comparison.json` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/evidence/full-village-contact-summary.json` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/evidence/publication-numerical-verification.json` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/legacy/AIR_CONTACT_CORRECTION.md` | historical → `docs/history/legacy/AIR_CONTACT_CORRECTION.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/AIR_PURSUIT_CHECKPOINT.md` | historical → `docs/history/legacy/AIR_PURSUIT_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/CENTRAL_AUDIT_CORRECTIONS.md` | historical → `docs/history/legacy/CENTRAL_AUDIT_CORRECTIONS.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/CONSOLIDATED_RECIPE_CHECKPOINT.md` | historical → `docs/history/legacy/CONSOLIDATED_RECIPE_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/CRAFTED_PROFILE_CHECKPOINT.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/CRAFTED_SEASON_ACCESS.md` | historical → `docs/history/legacy/CRAFTED_SEASON_ACCESS.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/CRAFTED_SHARED_CHECKPOINT.md` | historical → `docs/history/legacy/CRAFTED_SHARED_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/CWL_PROFILE_DIAGNOSIS.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/DEATH_RAGE_CHECKPOINT.md` | historical → `docs/history/legacy/DEATH_RAGE_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/DOMAIN_INTEGRATION_CHECKPOINT.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/DUKE_CONTACT_DIAGNOSIS.md` | historical → `docs/history/legacy/DUKE_CONTACT_DIAGNOSIS.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/DUKE_CONTACT_EXPERIMENT.md` | historical → `docs/history/legacy/DUKE_CONTACT_EXPERIMENT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/FLINGER_DAMAGE_CLOCK_CONTRACT.md` | historical → `docs/history/legacy/FLINGER_DAMAGE_CLOCK_CONTRACT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/FLINGER_SHARED_RECHECK.md` | historical → `docs/history/legacy/FLINGER_SHARED_RECHECK.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/FULL_COMPARISON_QUICKSTART.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/GENERATED_CANDIDATE_EVALUATION_PLAN.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/GIGA_CHILD_AUDIT_CORRECTION.md` | historical → `docs/history/legacy/GIGA_CHILD_AUDIT_CORRECTION.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/GIGA_RESPONSE_BINDING.md` | historical → `docs/history/legacy/GIGA_RESPONSE_BINDING.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/GROUND_NAVIGATION_CHECKPOINT.md` | historical → `docs/history/legacy/GROUND_NAVIGATION_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/HEALER_PURSUIT_CHECKPOINT.md` | historical → `docs/history/legacy/HEALER_PURSUIT_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/HIGHER_TH_SCENARIOS.md` | historical → `docs/history/legacy/HIGHER_TH_SCENARIOS.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/HIT_STATUS_EXPIRY_CHECKPOINT.md` | historical → `docs/history/legacy/HIT_STATUS_EXPIRY_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/LAYOUT_SEARCH_CONTRACT.md` | historical → `docs/history/legacy/LAYOUT_SEARCH_CONTRACT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/LEGEND_PROFILE_SCOPE.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/MIRROR_SPELL_REPAIR.md` | historical → `docs/history/legacy/MIRROR_SPELL_REPAIR.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/PAID_OBSERVATION_CHECKPOINT.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/PROTOTYPE_BACKLOG.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/PROTOTYPE_PUBLICATION.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/PROTOTYPE_QUICKSTART.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/PUBLICATION.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/PURSUIT_THROUGHPUT_CHECKPOINT.md` | historical → `docs/history/legacy/PURSUIT_THROUGHPUT_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/RECIPE_BINDING_MAP.md` | historical → `docs/history/legacy/RECIPE_BINDING_MAP.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/RECIPE_EQUIPMENT_CONTRACTS.md` | historical → `docs/history/legacy/RECIPE_EQUIPMENT_CONTRACTS.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/RECIPE_FROSTY_CONTRACT.md` | historical → `docs/history/legacy/RECIPE_FROSTY_CONTRACT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/RECIPE_SPELL_CONTRACTS.md` | historical → `docs/history/legacy/RECIPE_SPELL_CONTRACTS.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/RECIPE_TROOP_CONTRACTS.md` | historical → `docs/history/legacy/RECIPE_TROOP_CONTRACTS.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/REVIEWED_DOMAIN_INTEGRATION.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/REVIEWED_STREAM_INTEGRATION.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/ROOT_ROUTING_CHECKPOINT.md` | historical → `docs/history/legacy/ROOT_ROUTING_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/SIEGE_LIFECYCLE_INTEGRATION.md` | historical → `docs/history/legacy/SIEGE_LIFECYCLE_INTEGRATION.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/SKY_WAGON_CHECKPOINT.md` | historical → `docs/history/legacy/SKY_WAGON_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/SPELL_CLOCK_CHECKPOINT.md` | historical → `docs/history/legacy/SPELL_CLOCK_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/SPELL_LIFECYCLE_CHECKPOINT.md` | historical → `docs/history/legacy/SPELL_LIFECYCLE_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/STAGE3_AUDIT_FIXES.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/STAGE4_CLOSURE.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/STAGE5_COVERAGE_PROMOTION_MATRIX.md` | stale → deleted | STALE: retired prototype publication, profile, procedural or integration-checkpoint system; current native docs replace it. |
| `docs/legacy/TROOP_LINE_CHECKPOINT.md` | historical → `docs/history/legacy/TROOP_LINE_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/WALL_BREAKER_CHECKPOINT.md` | historical → `docs/history/legacy/WALL_BREAKER_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/WEIGHTED_ROUTE_CHECKPOINT.md` | historical → `docs/history/legacy/WEIGHTED_ROUTE_CHECKPOINT.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/advanced-spell-integration.md` | historical → `docs/history/legacy/advanced-spell-integration.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/attack-search-contract.md` | historical → `docs/history/legacy/attack-search-contract.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/attacking-troop-integration.txt` | historical → `docs/history/legacy/attacking-troop-integration.txt` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/crafted-defense-integration.md` | historical → `docs/history/legacy/crafted-defense-integration.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/defense-garrison-delta-integration.md` | historical → `docs/history/legacy/defense-garrison-delta-integration.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/defense-garrison-integration.md` | historical → `docs/history/legacy/defense-garrison-integration.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/equipment-clock-audit-repair.txt` | historical → `docs/history/legacy/equipment-clock-audit-repair.txt` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/partial-replay-calibration.md` | historical → `docs/history/legacy/partial-replay-calibration.md` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/remaining-equipment-integration.txt` | historical → `docs/history/legacy/remaining-equipment-integration.txt` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/remaining-troop-integration.txt` | historical → `docs/history/legacy/remaining-troop-integration.txt` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/legacy/troop-audit-corrections.txt` | historical → `docs/history/legacy/troop-audit-corrections.txt` | Historical mechanic/recipe correction and evidence; preserve dated decisions, retire execution procedures. |
| `docs/playbook-completion.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/playbook-consolidation.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/playbook-extraction.md` | current → retained | Active contract, research/input brief, ledger or current evidence; update native paths and mark historical predecessor references. |
| `docs/rust-spike-spec.md` | stale → deleted | STALE: personal account advice or superseded Python/Rust spike procedure. |
| `docs/video-evidence/12-XtLqXV-ab6U-174.jpg` | local evidence → `local/evidence/video/12-XtLqXV-ab6U-174.jpg` | Media provenance/license is not established for distribution; retain local measurement still, ignored by Git. |
| `docs/video-evidence/2026-10-21-maroon-base-overlay.jpg` | local evidence → `local/evidence/video/2026-10-21-maroon-base-overlay.jpg` | Media provenance/license is not established for distribution; retain local measurement still, ignored by Git. |
| `docs/video-evidence/2026-10-21-maroon-first-breath.jpg` | local evidence → `local/evidence/video/2026-10-21-maroon-first-breath.jpg` | Media provenance/license is not established for distribution; retain local measurement still, ignored by Git. |
| `docs/video-evidence/2026-10-21-maroon-key-falls.jpg` | local evidence → `local/evidence/video/2026-10-21-maroon-key-falls.jpg` | Media provenance/license is not established for distribution; retain local measurement still, ignored by Git. |
| `docs/video-evidence/icegolem-freeze-pHPMdLcXveY-207.jpg` | local evidence → `local/evidence/video/icegolem-freeze-pHPMdLcXveY-207.jpg` | Media provenance/license is not established for distribution; retain local measurement still, ignored by Git. |

New indices: `docs/README.md`, `docs/history/README.md`, and `local/README.md`.
The restructure plan remains an active integration document, with sections 3–4
explicitly labeled as its historical inventory. Stale prototype publication,
profile/advice and Python parity/spike procedures were removed. Still-useful
mechanic/recipe corrections remain dated under `docs/history/legacy/`.

## Rust path handoff — no Rust edits

The following are every source location containing a literal `output/` path
(including historical source citations). The first table contains runtime
defaults/inputs; pass explicit path options where supported until the lead
patches these after lane F merges. Line numbers are those in this unchanged
checkout. The armysearch default is included even though it is `rust/output/`.

| Runtime source location | Existing hard-coded path | Intended local path / action |
| --- | --- | --- |
| `crates/clash-armysearch/src/lib.rs:209` | `rust/output/armysearch` | `local/armysearch` |
| `crates/clash-fidelity/src/board.rs:209` | `output/fidelity-rust/cv` | `local/fidelity/cv` |
| `crates/clash-fidelity/src/lib.rs:329` | `output/fidelity-rust/calibration.json` | `local/fidelity/calibration.json` |
| `crates/clash-fidelity/src/th18.rs:140` | `output/ranked-bases-2026-10-25-th18/results.json` | `local/digitize/ranked-bases-2026-10-25-th18/results.json` |
| `crates/clash-playbook-tools/src/lib.rs:135` | `output/sources` | `local/sources` |
| `crates/clash-playbook-tools/src/lib.rs:474` | `output/research/brief-entity.txt` | `local/research/brief-entity.txt` |
| `crates/clash-playbook-tools/src/lib.rs:475` | `output/research/brief-gap.txt` | `local/research/brief-gap.txt` |
| `crates/clash-playbook-tools/src/lib.rs:496` | `output/research/usage` | `local/research/usage` |
| `crates/clash-playbook-tools/src/lib.rs:498` | `output/research/gaps` | `local/research/gaps` |
| `crates/clash-playbook-tools/src/lib.rs:499` | `output/research/gaps/skip-event.txt` | `local/research/gaps/skip-event.txt` |
| `crates/clash-playbook-tools/src/lib.rs:502` | `output/research/queue.tsv` | `local/research/queue.tsv` |
| `crates/clash-playbook-tools/src/lib.rs:504` | `output/research/usage` | `local/research/usage` |
| `crates/clash-vidmine/src/lib.rs:387` | `output/web-videos/{}` | `local/web-videos/{}` |

Historical source citations (comments and parameter-source metadata) also
need path review. Research citations map to `local/research/`; retained small
evidence maps through the local manifest. A citation to a deleted uncited old
hunt/proof log must be labeled historical, not redirected to unrelated evidence.

| Source location | Original citation text |
| --- | --- |
| `crates/clash-armysearch/src/account.rs:648` | `// output/hunt/r11/u2.out #3: only the installed program can` |
| `crates/clash-armysearch/src/account.rs:819` | `// output/research/usage/super-dragon.md: the cited variant lives in dragon.json.` |
| `crates/clash-armysearch/src/lib.rs:1` | `//! Native account army search. See output/rustfirst/b-armysearch.out for design.` |
| `crates/clash-armysearch/src/program.rs:55` | `// output/hunt/r11/u2.out #1: learned records provenance only. Keep` |
| `crates/clash-armysearch/src/program_mutate.rs:163` | `/// Optional, weak priors derived by hand from output/research/usage/:` |
| `crates/clash-armysearch/src/program_proof.rs:218` | `// output/research/usage/rage-spell.md: Rage has an 18-second duration.` |
| `crates/clash-armysearch/src/program_validate.rs:320` | `// output/research/usage/grand-warden.md: a cited paired activation needs` |
| `crates/clash-armysearch/src/report.rs:317` | `// output/hunt/r16/v2.out #1: confirmation has selected parents/winners.` |
| `crates/clash-armysearch/src/score.rs:51` | `// output/research/usage/dragon.md U14, Supercell battle modifiers:` |
| `crates/clash-armysearch/src/score.rs:413` | `// output/hunt/r16/v2.out #1: frozen finalists, same search bases,` |
| `crates/clash-engine/src/battle.rs:874` | `// output/research/usage/bag-of-frostmites.md: generated Frostmites` |
| `crates/clash-engine/src/combat.rs:614` | `// output/research/usage/totem-spell.md: Totems stay fixed.` |
| `crates/clash-engine/src/defense.rs:271` | `// output/research/usage/overgrowth-spell.md:36: a covered Tesla stays untargetable.` |
| `crates/clash-engine/src/defense.rs:295` | `// output/research/usage/baby-dragon.md:16; verify/c2.out #9: only flying` |
| `crates/clash-engine/src/defense.rs:386` | `// output/hunt/r10/t3.out #2: bucket alignment must not decide target ties.` |
| `crates/clash-engine/src/defense.rs:387` | `// output/research/usage/dealing-with-monolith-and-inferno-towers.md:` |
| `crates/clash-engine/src/defense.rs:479` | `// output/research/usage/dealing-with-monolith-and-inferno-towers.md:` |
| `crates/clash-engine/src/defense.rs:497` | `// output/research/usage/hero-sniping-of-exposed-defenses.md: TH16 must wake.` |
| `crates/clash-engine/src/defense.rs:523` | `// output/research/usage/spell-tower.md: Rage covers nearby weapons.` |
| `crates/clash-engine/src/defense.rs:560` | `// output/research/usage/crafting-station.md: unused flames concentrate.` |
| `crates/clash-engine/src/defense.rs:604` | `// output/research/usage/flame-flinger.md: Heroes, Guardians and CC guard lanes.` |
| `crates/clash-engine/src/defense.rs:614` | `// output/research/usage/ruin-witch.md; ClashKing/characters.csv:` |
| `crates/clash-engine/src/defense.rs:673` | `// output/research/usage/super-minion.md: three defensive Long Shots,` |
| `crates/clash-engine/src/defense.rs:1307` | `// output/research/usage/crafting-station.md: Cake exposes its firing target.` |
| `crates/clash-engine/src/defense.rs:1906` | `// output/research/usage/firespitter.md: acquisition stays inside its sector.` |
| `crates/clash-engine/src/defense.rs:2044` | `// conflicts with it (output/hunt/r9/s5.out #1).` |
| `crates/clash-engine/src/effects.rs:118` | `// output/research/usage/dark-crown.md: August fixed Totems to one housing.` |
| `crates/clash-engine/src/heroes.rs:1308` | `// output/research/usage/barbarian-king.md:19; initial targeting includes size.` |
| `crates/clash-engine/src/heroes.rs:2850` | `// output/research/usage/freeze-spell.md:20; frozen Guardians cannot activate.` |
| `crates/clash-engine/src/heroes.rs:3460` | `// output/research/usage/rocket-backpack.md; cached Rocket_Backpack.txt:` |
| `crates/clash-engine/src/movement.rs:77` | `// (output/dragon-spacing/measure.md); ground keeps the housing term.` |
| `crates/clash-engine/src/params.rs:53` | `air_radius: f64 = 0.35, "measured", "tiles", "Dragon spacing estimate; output/dragon-spacing/measure.md";` |
| `crates/clash-engine/src/pets.rs:563` | `// output/research/usage/diggy.md:27; stun includes attackable defenders.` |
| `crates/clash-engine/src/plans/attacker.rs:130` | `// output/research/usage/lightning-spell.md: Invisibility allows spell damage;` |
| `crates/clash-engine/src/plans/attacker.rs:759` | `// output/research/usage/cleanup-troops-and-end-of-attack-play.md:` |
| `crates/clash-engine/src/plans/attacker.rs:1026` | `// output/research/usage/seeking-shield.md: fixed ability damage.` |
| `crates/clash-engine/src/plans/attacker.rs:1205` | `// output/research/usage/hidden-tesla.md: concealed Teslas are not scouted.` |
| `crates/clash-engine/src/plans/attacker.rs:1231` | `// output/research/usage/air-sweeper.md: Sweepers displace Healers.` |
| `crates/clash-engine/src/plans/attacker.rs:1429` | `// output/research/usage/archer-queen.md: equipment supplies passive HP.` |
| `crates/clash-engine/src/plans/attacker.rs:1468` | `// output/research/usage/flame-flinger.md: ranked penalties affect Heroes.` |
| `crates/clash-engine/src/plans/attacker.rs:1701` | `// output/research/usage/lightning-spell.md: spells need no approach.` |
| `crates/clash-engine/src/plans/attacker.rs:2046` | `// output/research/usage/hero-sniping-of-exposed-defenses.md:` |
| `crates/clash-engine/src/plans/attacker.rs:2066` | `// output/research/usage/lightning-spell.md: concealed buildings take spells.` |
| `crates/clash-engine/src/plans.rs:97` | `// output/research/usage/crafting-station.md: crafted weapons need counterplay.` |
| `crates/clash-engine/src/plans.rs:257` | `// output/research/usage/super-minion.md: Blimp cargo needs reserved support.` |
| `crates/clash-engine/src/plans.rs:949` | `// output/research/usage/cleanup-troops-and-end-of-attack-play.md:` |
| `crates/clash-engine/src/plans.rs:1902` | `// output/research/usage/earthquake-spell.md:18: four casts open walls.` |
| `crates/clash-engine/src/plans.rs:1967` | `// output/research/usage/freeze-spell.md: overlapping Freezes` |
| `crates/clash-engine/src/playbook.rs:395` | `// output/research/usage/hero-sniping-of-exposed-defenses.md:` |
| `crates/clash-engine/src/playbook.rs:473` | `// output/research/usage/grand-warden.md: equipment supplies abilities.` |
| `crates/clash-engine/src/playbook.rs:883` | `// output/research/usage/root-rider.md: Duke follows the Riders' entry.` |
| `crates/clash-engine/src/playbook.rs:920` | `// output/research/usage/root-rider.md: support follows the main troops.` |
| `crates/clash-engine/src/playbook.rs:1001` | `// output/research/usage/invisibility-spell.md: cover advancing heroes.` |
| `crates/clash-engine/src/playbook.rs:1225` | `// output/research/usage/revive-spell.md: unused abilities survive KO.` |
| `crates/clash-engine/src/playbook.rs:1575` | `// output/research/usage/archer.md: spread deployments avoid splash.` |
| `crates/clash-engine/src/playbook.rs:1909` | `// output/research/usage/grand-warden.md: paired activation names` |
| `crates/clash-engine/src/playbook.rs:2195` | `// output/research/usage/minion-prince.md: Pendant recalls the Prince` |
| `crates/clash-engine/src/playbook.rs:2462` | `// output/research/usage/super-minion.md: release Blimp at the chosen cluster.` |
| `crates/clash-engine/src/playbook.rs:2487` | `// output/hunt/r9/s2.out #4: pets, summons and cargo also arrive in battle.` |
| `crates/clash-engine/src/playbook.rs:2488` | `// output/research/usage/archer-queen.md: Mirror clones are separate heroes.` |
| `crates/clash-engine/src/playbook.rs:2509` | `// output/research/usage/root-rider.md: Recall closes the opener.` |
| `crates/clash-engine/src/playbook.rs:2601` | `// output/research/usage/grand-warden.md: equipped abilities` |
| `crates/clash-engine/src/playbook.rs:2702` | `// output/research/usage/invisibility-spell.md: support under` |
| `crates/clash-engine/src/playbook.rs:2806` | `// output/research/usage/recall-spell.md: legal drops only.` |
| `crates/clash-engine/src/playbook.rs:2945` | `// output/research/usage/cleanup-troops-and-end-of-attack-play.md:` |
| `crates/clash-engine/src/playbook.rs:3165` | `// output/research/usage/dragon.md: support follows the push.` |
| `crates/clash-engine/src/setup.rs:419` | `// output/research/usage/archer-tower.md: the geared tower is merged.` |
| `crates/clash-engine/src/spells.rs:245` | `// output/research/usage/battle-blimp.md: April made sieges immune` |
| `crates/clash-engine/src/spells.rs:282` | `// output/research/usage/invisibility-spell.md: towers also use centres.` |
| `crates/clash-engine/src/spells.rs:1738` | `// output/research/usage/invisibility-spell.md: use building centres.` |
| `crates/clash-engine/src/spells.rs:1854` | `// output/research/usage/ice-block-spell.md: October 2025 fixed` |
| `crates/clash-engine/src/spells.rs:2044` | `// output/research/usage/archer-queen.md and dark-crown.md: each Totem now` |
| `crates/clash-engine/src/traps.rs:40` | `// output/research/usage/totem-spell.md:36; August fixed 20 to 1 housing.` |
| `crates/clash-engine/src/traps.rs:98` | `// output/research/usage/bomb.md: Bombs damage and knock back small troops.` |
| `crates/clash-engine/src/traps.rs:423` | `// output/research/usage/spring-trap.md; verify/c1.out #5 corrects immunity:` |
| `crates/clash-engine/src/units.rs:3458` | `// output/research/usage/headhunter.md:18-23; L4 is absent from the older CSV.` |
| `crates/clash-engine/src/units.rs:3656` | `// output/research/usage/unicorn.md: Healers cannot heal Unicorns.` |
| `crates/clash-plans/src/armies.rs:66` | `// output/research/usage/yeti.md: no cited ordinary-Yeti book exists.` |
| `crates/clash-plans/src/armies.rs:606` | `// output/research/usage/grand-warden.md: preserve the replay's chosen mode.` |
| `crates/clash-plans/src/compile.rs:117` | `// output/research/usage/super-dragon.md: use dragon.json's variant;` |
| `crates/clash-plans/src/compile.rs:279` | `// output/research/usage/invisibility-spell.md: cover the first hero` |
| `crates/clash-plans/src/compile.rs:655` | `// output/research/usage/root-rider.md: siege alternatives retain` |
| `crates/clash-plans/src/compile.rs:691` | `// output/research/usage/root-rider.md: preserve the chosen funnel/main roles.` |
| `crates/clash-plans/src/compile.rs:1478` | `// output/research/usage/dragon.md: Dragons precede supporting Riders.` |
| `crates/clash-plans/src/compile.rs:1505` | `// output/research/usage/super-wall-breaker.md: breach with the push.` |
| `crates/clash-plans/src/compile.rs:1646` | `// output/research/usage/invisibility-spell.md: protect the cited recipient.` |
| `crates/clash-plans/src/compile.rs:1788` | `// output/research/usage/root-rider.md: one paced smash deployment chain.` |
| `crates/clash-plans/src/compile.rs:1919` | `// output/research/usage/grand-warden-walk.md: Healers require ground mode.` |
| `crates/clash-plans/src/compile.rs:2458` | `// output/research/usage/lavaloon.md: summons cannot occupy camps.` |
| `crates/clash-plans/src/compile.rs:2592` | `// output/research/usage/meteor-golem.md and sky-wagon.md.` |
| `crates/clash-scoring/src/scouting.rs:117` | `/// output/research/usage/hidden-tesla.md and clan-castle-lure-and-kill.md:` |

The digitizer’s dated folder-name literals at
`crates/clash-dataimport/src/digitize/replay.rs:111` and `:118` still work with
`--inputs local/digitize`; they are child names, not hard-coded `output/` roots.
No source root, data file or archived payload was edited to hide an old path.

The optional Python reference adapter in `crates/clash-cli/src/compile_cli.rs`
is also unchanged: `--python`/`--write-reference-script` (lines 100–101),
`BASELAB_PYTHON`/optional `plan_reference.py` (305–316), and the embedded
`REFERENCE_EXPORTER` (549) still need the lead’s Rust-only retirement pass.
They are not used by the native gate. No absent standalone exporter was added.

## Validation

Detailed receipts are retained under `local/evidence/g4/`:

- `scripts/verify.sh /tmp/clash-target-ws`: formatting, locked offline release
  build and workspace tests passed; Clippy stopped on the lane-F-owned error
  above. This is not reported as a full-gate pass.
- Remaining native gate commands (battle/plan goldens, guardian, armysearch,
  layout and M2 base-search proofs, plus video tests): passed; see `native-proofs.log`.
- Native digitizer replay over moved intermediates and native frozen-playbook
  recorded-output comparison: 14/14 layouts equal/admitted; 1,054 citations, 260
  extractions and 11 consolidations checked with zero differences. See their local receipts.
- Retained Python AST/import closure, source audit/normalization/rebuild-plan
  smoke checks, Black 24.10.0, shell syntax, doc links/default paths, Git diff
  whitespace and protected-byte checks: see `cleanup-checks.json`.
- No root verification shim was invented. Existing untracked data files and
  `target-ws/` from intake were left alone. HEAD and branch are unchanged.
