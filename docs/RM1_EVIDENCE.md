# RM1 implementation evidence — 2026-10-25

This report concerns Rust mechanics only. All demos are declared synthetic and
are **not real-game calibration**. Behavioral interpretations of the game constants
are hypotheses pending the friendly-challenge cards in [PROBE_CARDS.md](PROBE_CARDS.md).

## Delivered

- One battle-local registry: **100 named entries** in the committed catalog
  configuration: 68 scalar/boolean entries (including the four flags) and 32
  `new_target_delay.<unit>` entries. Defaults, provenance, units, overrides and
  audit scope are listed in [PARAMS.md](PARAMS.md).
- Four flags, all false by default: `target_list`, `warden_spatial`,
  `defender_separation`, `hidden_information`.
- Exact individual path costs for the candidate-list hypothesis; the original
  cheapest-goal union query is retained for the default engine.
- JSON overrides in job `env.params` / `params` and `BASELAB_PARAMS_FILE`.
  Strict type/name/value checks; atomic application; isolated concurrent jobs.
- Four complete before/after synthetic battles in
  [demos.json](../fixtures/mechanics/demos.json), with reproducible
  [evidence.json](../fixtures/mechanics/evidence.json).
- Probe cards T1–T5, W1–W2, C1 and H1 distinguish candidate limits, path/wall cost,
  memory, retarget causes/noise, wall holds, spatial grouping/waiting, crowding and
  pre-reveal information. Each specifies minimal staging, a controlled single
  troop drop, distinguishing target/path/time observations and unresolved meanings.

RM1 changes engine mechanics, loading and runtime plan scans. Its additions to
shared `lib.rs` are only the `params` and `targeting` module declarations. RM1 did
not edit `main.rs`, Cargo manifests, layout-owned files, fidelity-owned files,
vidmine, the golden corpus, or any Python file. Concurrent admission/module/command
changes from other streams were retained. No downloads or installations were used.

## Verification on WSL

Build environment:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-rm1
export BASELAB_CATALOG="$PWD/rust/data/catalog.json"
cargo build --release --manifest-path Cargo.toml --workspace --all-targets
cargo test --manifest-path Cargo.toml -p clash-engine --test mechanics
/tmp/clash-target-rm1/release/baselab-engine golden check fixtures/golden/cases.jsonl fixtures/golden/expected.jsonl
/tmp/clash-target-rm1/release/baselab-engine guardian-check
/tmp/clash-target-rm1/release/examples/mechanics_proof > /tmp/rm1-release-evidence.json
cmp fixtures/mechanics/evidence.json /tmp/rm1-release-evidence.json
```

Results:

| Check | Result |
|---|---|
| Release engine + example | Pass, no warnings; 51.82 s |
| Default golden check | **cases=868 passed=868 failed=0**, default threads=16; 5.991121 s |
| Guardian fixtures | **50 declared-synthetic fixtures passed** |
| Mechanics integration tests | **20 passed, 0 failed** |
| Release demo vs committed evidence | Byte-for-byte identical (`cmp`, exit 0) |
| RM1-owned Rust formatting | `cargo fmt` and its `--check` pass |
| Owned tracked-file whitespace / golden status | `git diff --check` clean; golden files unchanged |

Formatting used an ownership-scoped temporary Cargo manifest at
`/tmp/rm1-format/Cargo.toml`, listing the RM1 Rust files explicitly, with
`--config skip_children=true`. This prevents formatting the concurrent layout,
fidelity and vidmine sources. Application code, integration tests, shared proof
helpers and the example were all formatted. The normal crate manifest is used for
all builds, tests and engine runs.

The tests cover all four behavioral differences and reproduction of the committed
artifact; validation and override precedence; process-file overrides without
mutating the parent process environment; concurrent isolation; CSV globals and
Warden range/radius/weight scales; nearest-list truncation, expansion and penalty;
forget/remember/stickiness; progress from wall damage; wall hold expiry and optional
retarget after destruction; repeatable, cause-specific noise; Warden waiting;
defender separation and zero push; hidden plan/navigation filtering and reveal
invalidation.

No test here establishes the game's actual target-list algorithm, noise
probability distribution, Warden grouping algorithm, or separation constants.

## Concrete behavior

- Target list: first building **3 → 0**; first wall damage **15.9 → 3.7 s**;
  first building damage **7.9 → 6.9 s**; battle end **34.2 → 35.3 s**.
- Warden spatial groups: first building **1 → 0**; first building damage
  **5.2 → 4.8 s**; battle end **11.3 → 5.9 s**.
- Defender separation: the first defender position after the first tick changes
  from **(19.84443650813896, 20.15556349186104)** to
  **(19.765336748290288, 20.202165155211357)**. Its target and this battle's end
  time (21.3 s) remain the same. Position, rather than outcome, distinguishes the rule.
- Hidden information: first building **2 → 0**, before the Tesla reveals;
  first building damage **9.3 → 6.5 s**; battle end **30.7 → 12.1 s**.
  The initial known-building count is **3 → 2** and unknown-trap count **0 → 1**.

All four observed per-tick path/target digests differ. Damage timestamps are end
of simulation tick observations, not measured animation timings. Small fixtures
need not contain a Town Hall; their stars are simulator bookkeeping, not a claim
of a legally complete friendly-challenge village.

## Sizes and identities

Sizes measured on this WSL build:

| Item | Bytes |
|---|---:|
| Release `baselab-engine` | 6,166,560 |
| Release `examples/mechanics_proof` | 3,290,656 |
| `Params` inline storage | 520 |
| `TargetMemory` inline storage per tracked unit | 104 |
| Current `Battle` inline storage | 6,544 |
| Synthetic `demos.json` | 3,047 |
| Synthetic `evidence.json` | 7,172 |
| Both fixture artifacts | **10,219** |

Inline struct sizes exclude heap allocations. Default parameters own a copy of the
32-entry delay map; target memory is empty until the target-list flag is enabled.
The executable and Battle sizes reflect the shared workspace snapshot, including
concurrent streams, rather than an isolated RM1 size delta.

SHA-256:

```text
1b6c010e1c11dbf3a50b225071b8b89c9e42fe37de8ebdca689dfe036449c69b  demos.json
b43e389c160d940c854b7940433caf08c1dd33a18365bd2fffd5cbc135f11d23  evidence.json
b4b66f27d4b111452321a27cf84343f83f71a7e2a0165bd43fb61e0c35fc5358  release/baselab-engine
```
