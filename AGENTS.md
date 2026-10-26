# Working rules

- Rust only. The root Cargo workspace and `clash` CLI are the executable reference;
  do not add Python/PowerShell workflows or require a sibling checkout.
- Preserve v29 engine behavior, deterministic math and explicit unsupported-content
  checks. Organizational work must not change mechanics, source values or goldens.
- Before any commit, run `cargo fmt --all -- --check` and `scripts/verify.sh`.
  The gate must finish with `ALL CHECKS PASSED`; never skip failing checks.
  In WSL source `~/.cargo/env` and use a target directory outside the checkout.
  Verification is offline: no downloads, installs, providers or data acquisition.
- Keep every byte of `fixtures/golden/{cases,expected,plans}.jsonl` unchanged for
  restructuring. Compare SHA-256 before and after; do not re-record expectations.
  If an operational golden path must change, stop and report it.
- `data/source/` holds pinned inputs: ClashKing/gamecsv, balance overrides,
  mechanics evidence, army/playbook/model inputs, calibration priors, layouts
  and the relocated legacy log/account snapshots. `data/generated/` holds the
  pinned runtime catalog, registry, rules, Castle table, manifest and search targets.
  Preserve provenance/source hashes and fit/evaluation ancestry when moving data.
- The video catalog at `data/source/catalog.json` and engine catalog at
  `data/generated/catalog.json` have different schemas. Never merge them.
  Honor explicit catalog paths, then `CLASH_CATALOG`, then `BASELAB_CATALOG`.
- Keep new personal inputs, observations, transcripts, reports, fitted models,
  extracted evidence and other derived work in ignored `local/` or explicit
  `private/` paths. Never keep downloaded videos; use external video paths.
  Keep credentials and raw memory captures out of Git. No memory acquisition
  workflow is retained. Do not request, store or require a Supercell API key;
  use explicit local inputs or supported keyless providers outside verification.
- Use declared synthetic fixtures. Never label synthetic results as real-game
  calibration. Do not rewrite old ancestry to imply that a fit used new inputs.
- Keep the engine dependency closure limited to `clash-data` and `clash-layout`.
  Compilation, scoring, search, fidelity, media and authoring belong in their
  owning libraries/tools; shared formats belong in data.
- Write conventional multiline code with clear names and straightforward flow.
  Prefer focused patches; format all changed Rust, tests and helper scripts.
- Do not edit the original October 3 checkout or the preserved baseline.
  Respect explicit writer ownership and coordinate shared files when lanes exist.
- See `docs/README.md`, `docs/ARCHITECTURE.md`, `docs/DATA_PIPELINE.md` and
  `docs/RESTRUCTURE_LOG.md` for current contracts, data flow and migration evidence.
