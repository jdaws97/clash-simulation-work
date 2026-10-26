# Rust reference engine (2026-10-25)

Rust is the executable reference and supported workflows are Rust only. The
earlier cleanup inventory is retained in [CLEANUP_G4.md](CLEANUP_G4.md).
Python parity is retired. Preserve the separate v29
baseline and its unsupported-content checks.

G1/G2 now use the root Cargo workspace. The checked WSL compiler is
`rustc 1.99.1 (58cf8f9c3 2026-10-13)`; no older MSRV is claimed and no toolchain
components are downloaded by verification. There is one lockfile and one release
profile. `cargo tree -p clash-engine --offline` contains only `clash-data` and
`clash-layout`.

| Owner | Source paths |
| --- | --- |
| Data, parser, catalog, wire/hash helpers, snapshot readers | `crates/clash-data/src/` |
| Layout model, admission, geometry, runtime rules | `crates/clash-layout/src/` |
| Battle runtime and attacker executor | `crates/clash-engine/src/`, including `plans/attacker.rs` |
| Army composition and playbook compilation/fitting | `crates/clash-plans/src/` |
| Scoring and scouting | `crates/clash-scoring/src/` |
| Army/base search, fidelity, video | `crates/clash-{armysearch,basesearch,fidelity,vidmine}/src/` |
| Catalog construction, battle logs/snapshots and digitization | `crates/clash-dataimport/src/` |
| Playbook evidence, authoring queues and research jobs | `crates/clash-playbook-tools/src/` |
| CLI dispatch, jobs, checks and local rule derivation | `crates/clash-cli/src/` |

Rule import orchestration stays in CLI. Shared
share-code parsing and snapshot/hash semantics are data-owned; observed-build
construction remains fidelity-owned. Engine private tests read frozen synthetic
prepared plans in `fixtures/playbooks/executor.jsonl`; plans tests separately
check that compiling those inputs reproduces the same plans.

The regression gate is the 868-case Rust golden suite, documented in
[GOLDEN.md](GOLDEN.md). It freezes complete per-tick traces and outcomes against
committed fixtures and catalog data. Intended changes require reviewed case
changes and an explicit re-record; matching averages is insufficient.

## Build and check

The engine is std-only, forbids unsafe code, and needs no downloads:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-ws
export CLASH_CATALOG="$PWD/data/generated/catalog.json"
cargo build --workspace --all-targets --release --locked --offline --manifest-path Cargo.toml
/tmp/clash-target-ws/release/clash compile custom:user-rr-oct25 0 123 /tmp/plan.json --root "$PWD"
/tmp/clash-target-ws/release/clash guardian-check
/tmp/clash-target-ws/release/clash armysearch-proof --root "$PWD" --out /tmp/armysearch-proof
/tmp/clash-target-ws/release/clash golden check fixtures/golden/cases.jsonl fixtures/golden/expected.jsonl --threads 4
cargo fmt --manifest-path Cargo.toml --all -- --check
scripts/verify.sh /tmp/clash-target-ws
```

The gate can also be invoked from `/tmp` using the absolute script path. It
passes absolute catalog, fixture, root, account and temporary report paths;
failing build/test/check commands propagate their exit status directly. Battle
goldens run at one and four workers. Armysearch checks one/four/sixteen workers;
the full M2 proof checks one/four/sixteen/one workers. Clippy is strict with
`-D warnings`; unavailable components and failing checks fail the gate without
installing anything. Earlier Clippy limitations in G1/G2/G4 receipts are dated
history, not the current gate policy.

`clash` exposes `fidelity`, `video`, `dataimport` and `playbook` namespaces.
`simulate run|trace|jobs|bench`, `plan compile|check`,
`armysearch run|proof`, and `basesearch proof` are additional aliases. Native
base search also provides `run`, `smoke` and `proof-completion`. The
`baselab-engine`, `fidelity`, and `vidmine` binaries simply forward arguments.
See [RESTRUCTURE_LOG.md](RESTRUCTURE_LOG.md) for the complete rename inventory
and frozen hashes. No Python source was changed or executed in G1/G2.

On Windows use `target/release/clash.exe` and the same catalog
and golden files. Both platforms must reproduce the same expectations. A Windows
mismatch must be investigated, not accepted as another platform baseline.

## Runtime contract

- `setup.rs` constructs worker-local battles; `runner.rs` preserves input/result
  order across threads. `compile.rs` builds and validates native plans.
- Battles use a 0.1-second tick and half-tile, eight-neighbour lazy Dijkstra
  navigation fields (`grid.rs`). This differs from the preserved v29 engine.
- `detmath.rs` provides fixed musl-derived sin/cos/atan2/pow/exp algorithms.
  `geom.rs` retains compensated hypot and rounding. Use these wrappers, preserve
  arithmetic and iteration order, and avoid platform transcendental functions.
  The mathematical contract is platform-identical Rust golden traces.
- `pyrandom.rs` keeps deterministic MT19937 streams. Consume randomness in a
  documented order; keep scouting and evaluation seed domains separate.
- Catalog presence does not establish executable support. Compile and setup
  reject unsupported equipment/pets with admission errors before deployment.

## Inputs and scoring

`data/generated/catalog.json` supplies resolved game statistics; the minimal sourced
siege-cap table is `data/generated/clan_castle.json`. Synthetic default search targets
are committed under `data/generated/target17.json` and `target18.json`. No wiki mirror
or generated `output/` file is required. Explicit paths, such as `--manifest`,
`--catalog`, `--account`, score bundles and `BASELAB_CALIBRATION`, remain inputs
chosen by the caller. Existing tracked account/library defaults are retained;
new personal profiles must stay outside Git.

Army search accepts TH16–18 account snapshots through `--account FILE`; omission
uses the existing user's TH16 account. Capacities come from the account's actual
camp/factory/castle levels. A manifest's top-level `modifier` accepts null,
`legend3`, `legend2`, or `legend1` and follows scenarios, jobs, cache identity,
replays and reports. Army-search best-of-completed-side estimates remain oracle
estimates; the scorer's visible policy is documented separately.

`score` defaults to `scout_policy: "visible"`; `random` and the labelled `oracle`
upper bound are explicit alternatives. See [SCOUTING.md](SCOUTING.md) for hidden
priors, independent seeds, budgets and the TH18 development comparison.
