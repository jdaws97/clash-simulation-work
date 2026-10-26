# Documentation

Current contracts and workflows are listed below. Dated results establish only
their stated scope; synthetic regressions are not real-game calibration.
Historical Python filenames in migration/acceptance receipts identify the
pre-cleanup revision `f04706c`, not runnable tools. Use `scripts/verify.sh` for
native acceptance. The root workspace and current workflows are Rust only;
[CLEANUP_G4.md](CLEANUP_G4.md) preserves the earlier cleanup inventory.

| Current document | Purpose |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Crate dependencies, input ownership, runtime paths and data flow. |
| [ENGINE_STATUS.md](ENGINE_STATUS.md) | Supported native scope, unsupported-content guards and unresolved limitations. |
| [RUST_PORT.md](RUST_PORT.md) | Workspace ownership, runtime behavior and native build/verification. |
| [ROADMAP.md](ROADMAP.md) | Remaining ports, measurement and integration work. |
| [CLEANUP_G4.md](CLEANUP_G4.md) | Cleanup decisions, every Python disposition, local moves and pending Rust paths. |
| [GOLDEN.md](GOLDEN.md) | Frozen battle/plan regression policy and dated acceptance receipts. |
| [PARAMS.md](PARAMS.md) | Model parameters and evidence labels. |
| [SCOUTING.md](SCOUTING.md) | Visible/random/oracle policy, seed separation and budgets. |
| [RM1_EVIDENCE.md](RM1_EVIDENCE.md) | Current Rust mechanics hypotheses, synthetic tests and evidence. |
| [PB1A.md](PB1A.md) | Plan/compiler correction evidence and declared regression scope. |
| [PB1B.md](PB1B.md) | Recipe/controller correction evidence and frozen plan scope. |
| [MOVES.md](MOVES.md) | M1 cited move registry, occurrence mappings, role evidence and lossless lowering. |
| [FIELD_PROFILING.md](FIELD_PROFILING.md) | Native path-field performance measurements. |
| [BASE_SEARCH_CONTRACTS.md](BASE_SEARCH_CONTRACTS.md) | Core layout admission, identities and search contracts. |
| [BASE_SEARCH_RUST_DESIGN.md](BASE_SEARCH_RUST_DESIGN.md) | Native search design; historical Python citations are provenance. |
| [BASE_DESIGN_PRINCIPLES.md](BASE_DESIGN_PRINCIPLES.md) | Cited design research, contested claims and source quality. |
| [MOVE_LIBRARY_DESIGN.md](MOVE_LIBRARY_DESIGN.md) | Attack move-library design and human-feasibility requirements. |
| [DATA_PIPELINE.md](DATA_PIPELINE.md) | Native source-to-registry/catalog construction and exact mirror inputs. |
| [PLAYBOOK_PIPELINE.md](PLAYBOOK_PIPELINE.md) | Native evidence checks, local/provider jobs and port receipt. |
| [FIDELITY_RUST.md](FIDELITY_RUST.md) | Native observation replay, fitting, CV and archival ancestry. |
| [SIM_ACCURACY.md](SIM_ACCURACY.md) | Accuracy evidence criteria and held-out measurement boundaries. |
| [PROBE_CARDS.md](PROBE_CARDS.md) | Controlled friendly-challenge measurement cards. |
| [VIDEO_MEASUREMENTS.md](VIDEO_MEASUREMENTS.md) | Dated video samples, measurement uncertainty and local stills. |
| [VIDEO_SHOTLIST.md](VIDEO_SHOTLIST.md) | Observation collection requirements. |
| [BUILDER_SCREENSHOTS.md](BUILDER_SCREENSHOTS.md) | Screenshot transcription/acquisition checklist. |
| [SIMULATION_METHODS_RESEARCH.md](SIMULATION_METHODS_RESEARCH.md) | Sourced numerical-method and simulation research. |
| [WIKI_DIGEST.md](WIKI_DIGEST.md) | Generated review digest from the normalized local wiki. |
| [audit-ledger.md](audit-ledger.md) | Source-finding ledger and historical review evidence. |
| [playbook-extraction.md](playbook-extraction.md) | Provider-independent extraction brief. |
| [playbook-consolidation.md](playbook-consolidation.md) | Provider-independent consolidation brief. |
| [playbook-completion.md](playbook-completion.md) | Provider-independent completion brief. |
| [RESTRUCTURE_PLAN.md](RESTRUCTURE_PLAN.md) | Living integration plan with explicitly historical inventory sections. |
| [RESTRUCTURE_LOG.md](RESTRUCTURE_LOG.md) | Workspace migration inventory, frozen hashes and acceptance evidence. |

Tool-specific current reports:

- [Base search](../crates/clash-basesearch/README.md)
- [Battle logs, snapshots and fidelity port](../crates/clash-fidelity/PORT_LC.md)
- [Screenshot digitizer](../crates/clash-dataimport/src/digitize/README.md)
- [Video tools](../crates/clash-vidmine/README.md)

[Historical records](history/README.md) retain useful mechanic decisions, dated
research and implementation receipts. Stale prototype/publication/profile
procedures and personal account advice were deleted. `evidence/*.json` retains
the four committed numerical/synthetic evidence summaries; media stills moved
to ignored `local/evidence/video/`, with original measurement limitations.

Retained transcripts and other working data are ignored under `local/`; its
`README.md` is the local data index. G5a separates pinned inputs in `data/source/`
from runtime outputs in `data/generated/`; licenses live in `data/licenses/`.
The old `rust/` directory and verification forwarder are removed. See the
[architecture](ARCHITECTURE.md) and [move log](RESTRUCTURE_LOG.md).
