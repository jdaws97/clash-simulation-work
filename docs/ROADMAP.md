# Remaining work

The native engine, compiler, scorer, army/base search, catalog builder, digitizer,
battle-log/snapshot ingestion and playbook tools are integrated. Their regression
gates establish model consistency, not real-game accuracy.

| Work | Current boundary / next result |
| --- | --- |
| Complete Python retirement | Port wiki acquisition/HTML normalization, source audit/manifest/patch workflows, aggregate/meta calibration, policy fitting and surrogate research; then remove each import closure. See [G4](CLEANUP_G4.md). |
| Finish integration | Apply the listed Rust `local/` paths after lane F merges, reorganize data separately, provision the exact toolchain and run Windows acceptance. |
| Evidence and calibration | Collect explicit private snapshots and held-out observations; preserve fit/evaluation separation and hash-bound ancestry. See [fidelity](FIDELITY_RUST.md). |
| Attacker and mechanic validity | Review timing-corpus drift and unsupported citations, measure target choice/crowding/grouping/CC and siege release, and test sensitivity. See [scope](ENGINE_STATUS.md) and [probe cards](PROBE_CARDS.md). |
| Search claims | Require equal physical-battle budgets, paired final comparisons and independently frozen finals. Keep limited smoke reports separate from gameplay recommendations. See [base search](../crates/clash-basesearch/README.md). |

Historical task lists and Python results are indexed under [history](history/README.md).
