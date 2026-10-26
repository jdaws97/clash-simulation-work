# Current engine scope

Rust is the executable reference in the root Cargo workspace. The preserved v29
and October 3 checkouts remain separate and untouched. The
[runtime contract](RUST_PORT.md), [golden policy](GOLDEN.md),
[scouting contract](SCOUTING.md) and [parameter inventory](PARAMS.md) describe
current behavior. `scripts/verify.sh` is the offline acceptance gate.

Catalog presence does not establish executable support. Admission rejects
unsupported equipment, pets and event content before a battle. Preserve those
checks, deterministic arithmetic, ordered randomness and the frozen goldens.
The native gate checks regression behavior; it does not certify game accuracy.

Native base search now includes evaluation, racing, QD, bounded attacker
refinement, diagnostics and winner reports; see its
[implementation and limits](../crates/clash-basesearch/README.md).
[Catalog regeneration](DATA_PIPELINE.md),
[battle-log/snapshot ingestion](../crates/clash-fidelity/PORT_LC.md),
[digitization](../crates/clash-dataimport/src/digitize/README.md) and
[playbook validation](PLAYBOOK_PIPELINE.md) have native commands.

Remaining work includes:

- Native catalog building consumes an existing normalized mirror; it does not
  refresh that mirror. Acquisition, HTML normalization and general source
  auditing need separate native acceptance before being supported workflows.
- Aggregate-target and per-build/meta calibration, policy fitting, and surrogate
  research need capability-specific native acceptance. Native replay, defense
  calibration and CV do not by themselves replace those fitting modes.
- Held-out game observations, sensitivity analysis and source-owner review are
  still needed. The playbook lane records a wiki-only support citation and timing
  corpus drift. Native synthetic proofs are not calibration evidence.
- Historical concerns about target choice, crowding, Warden grouping, hidden
  information, siege/CC release, tornado dynamics and animation timing require
  current Rust verification and controlled measurements. The dated
  [gap inventory](history/GAP_ANALYSIS.md) and
  [engine review](history/RUST_REVIEW_2026-10-25.md) retain the unresolved questions;
  their old Python status statements are not current verdicts.
- Retained output and current tool defaults use ignored `local/`. G5a separates
  `data/source/` and `data/generated/` and removes `rust/`; see
  [ARCHITECTURE.md](ARCHITECTURE.md). Toolchain provisioning and Windows
  acceptance remain separate integration work.

The [documentation index](README.md) separates current contracts from dated
research, milestone receipts and retired prototype procedures.
