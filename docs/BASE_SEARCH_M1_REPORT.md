# Rust base search M0 + M1 proof report

M0/M1 implements [the frozen contracts](BASE_SEARCH_CONTRACTS.md), not a base
search loop. All evidence below concerns synthetic/model correctness. No
Python file was edited or executed by this work; no real-game calibration is
claimed. Original v29/baseline checkouts and `rust/vidmine/**` were not edited.

## Delivered surface and sizes

`rust/src/layout/` contains typed physical/setup/config contracts, fallible
legacy JSON import/export, data normalization, immutable admission receipts,
eight-way geometry, a CLI, and a reproducible proof harness. The module is
approximately 4,100 Rust lines including the proof harness. The generated
`rust/data/base_rules.json` is 53,189 bytes; the three declared synthetic
fixture files total approximately 9 KB. The final proof JSON is written under
`/tmp` and includes executable, catalog, rules, fixture and corpus identities.

The only layout integration changes are the lib/main wiring, one shared
fallible content call in setup, and scoring's adapter to shared geometry.
Other concurrent writers changed shared engine files and added the separate
fidelity binary during this task; their edits were preserved. Reported gates
run on the resulting WSL executable with its default engine configuration.

The normalized rules derive quantities from local Town Hall unlocks, not
`BuildingType.count`. Every unlock quantity and merge recipe has its source
JSON pointer. Level limits, mode unlocks, footprints, CC/Hero Hall capacities,
trap inventories, wall counts, input fingerprints and cited model overrides
are retained. No inputs were downloaded.

Final proof receipt: `/tmp/layout-proof-final.json` (45,458 bytes). A copy of
the tested release executable is retained at
`/tmp/clash-layout-final/baselab-engine` so concurrent builds cannot replace
the artifact behind this receipt. Its SHA-256 is
`7e5b4560270c7effcaaf7497a08f64689b5369333f462f9024c0a33e31708bda`.
The 100,000 ordered admission outcomes fingerprint to
`fnv128:bf1039222e77d4809516d9d68d102637`.

| Fully merged preset | Building placements¹ | Traps | Maximum walls | CC housing | Hero slots |
|---|---:|---:|---:|---:|---:|
| TH16 | 99 | 44 | 325 | 50 | 4 |
| TH17 | 98 | 47 | 325 | 55 | 4 |
| TH18 | 98 | 48 | 325 | 55 | 4 |

¹ Includes four banner markers and one optional seasonal Crafting Station.
MAT/ricochet consume pairs, MGT consumes geared AT+Cannon, TH17 consumes the
Eagle, and two SWT consume four WT after TH18's extra WT unlock. The optional
TH16–17 crafting allowance is an explicitly cited frozen-model override of
the static TH18 unlock, not inferred game availability.

## Proof results

- Rules regenerate identically from the selected local source/catalog, with
  exact TH16–18 building/trap/wall count snapshots matching frozen constants.
- 38 explicit JSON boundary fixtures pass; full synthetic packings for all
  three THs admit, export/import unchanged, and build through engine setup.
- 100,000 deterministic malformed/near-legal mutations: **2,944 accepted** and
  **97,056 rejected with structured reasons**. No admission panic. Each accepted
  mutation builds through `setup::build`; its complete red-line tile set equals
  `Battle::live_no_deploy`, including banners and Tesla/trap exclusions.
- 4,096 mutation outcomes agree at **1/4/16 workers**, with accepted candidates
  also built by the parallel runs. Rules import and JSON round trips are
  deterministic. Mixed owned-wall levels, stable physical/account identities,
  metadata exclusion and observable building order have explicit checks.
- Geometry covers sealed rings, diagonal wall leaks, diagonal deploy leaks,
  edge/margin access, outside regions, wall-only compartments, footprint
  dilation, banners, Tesla/trap exclusions, and half-tile runtime navigation.
  Runtime walls allow diagonal corners; runtime building hitboxes restrict them.
- Existing `armysearch-proof` passes: 4,096 legality proposals, 4,096 program
  proposals, native 1/4/16-thread determinism, resume/cache/budget/holdout gates.
- The unchanged battle golden corpus passes **868/868**. Expectations and cases
  were not re-recorded. `cargo fmt --check` and the offline release build pass.

The corrected scorer floods eight ways. The declared diagonal-deploy fixture
changes from 49 hole tiles under the former four-way counter to zero. In the
committed corpus, `target17` changes **24 → 20**, increasing the penalized
ranked objective by 1.0 (default 0.25/tile), or WarV1 by 3.2 (0.8/tile).
Raw battle outcomes and raw scoring summaries are unchanged. The other 22
corpus hole counts are unchanged. Both target hole counts are frozen as
explicit reviewed geometry expectations.

## Committed corpus verdicts

The gate obtains every committed JSON under `data/reference-bases/` using
`git ls-files`, plus the two Rust targets. It checks full and partial policies
separately, records all structured reasons, and builds every accepted verdict.
Uncommitted reference bases are excluded. No corpus file is repaired or edited.
Default hole policy is Allow; requiring zero holes would reject the nonzero
counts below as a search-policy decision.

| Path (relative to data/reference-bases unless rust/) | Full | Partial | Eight-way hole tiles / explanation |
|---|---|---|---|
| ranked-2026-10-24/rb01.json | pass | pass | 10 |
| ranked-2026-10-24/rb02.json | pass | pass | 0 |
| ranked-2026-10-24/rb03.json | pass | pass | 6 |
| ranked-2026-10-24/rb04.json | pass | pass | 1 |
| ranked-2026-10-24/rb05.json | pass | pass | 11 |
| ranked-2026-10-24/rb06.json | pass | pass | 12 |
| ranked-2026-10-24/rb07.json | pass | pass | 0 |
| ranked-2026-10-24/rb08.json | pass | pass | 0 |
| ranked-2026-10-24/rb09.json | pass | pass | 15 |
| ranked-2026-10-24/rb10.json | pass | pass | 0; inactive crafting level ledger retained |
| ranked-th18-2026-10-25/r18a.json | reject | pass | 7; Revenge Tower 0/1 |
| ranked-th18-2026-10-25/r18b.json | pass | pass | 6 |
| ranked-th18-2026-10-25/r18c.json | reject | pass | 14; camp 3/4, dbarracks 0/1, dd 2/3, gm 6/7 |
| ranked-th18-2026-10-25/r18d.json | pass | pass | 4 |
| real-l1x.json | pass | pass | 6 |
| real-l3x.json | pass | pass | 21; inactive crafting level ledger retained |
| real-l4x.json | pass | pass | 13 |
| real-l5x.json | pass | pass | 22; inactive crafting level ledger retained |
| real-l6x.json | pass | pass | 7 |
| your-base-2026-10-21.json | pass | pass | 8 |
| your-base.json | pass | pass | 13 |
| rust/data/target17.json | pass | pass | 20; reviewed correction from 24 |
| rust/data/target18.json | pass | pass | 17 |

## Compatibility limits and reproduction

No check in frozen `Layout.problems` or `content_problems` was intentionally
left unported. Rust also rejects unknown content/modes, invalid levels,
Hero Hall/banner capacity errors, illegal CCs, and unsupported guardian or
crafting selections. Import rejects duplicate walls/overrides/object fields
rather than inheriting Python's silent set/dict deduplication. The Longshot
default below TH18 stays inert. No unsupported season, content bypass, physics
change, tolerance or expectation update was added.

**Executed Python parity is unavailable:** the user prohibited running Python,
and this task has no saved frozen verdict oracle. Compatibility claims rest
on reading the complete frozen functions, explicit category fixtures and exact
count snapshots, not a fresh Python-versus-Rust run. Account snapshots use the
normalized Rust `InventoryPolicy::Owned` API; interpreting raw private account
formats or authenticating ownership is outside M1. Search operators, racing,
archives, evaluation adapters and reporting search winners remain M2–M6.

From the repository root in WSL:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target
export BASELAB_CATALOG="$PWD/rust/data/catalog.json"
cargo build --release --offline --manifest-path Cargo.toml
/tmp/clash-target/release/baselab-engine layout import-rules "$PWD" /tmp/base-rules-regenerated.json
cmp rust/data/base_rules.json /tmp/base-rules-regenerated.json
/tmp/clash-target/release/baselab-engine layout proof "$PWD" /tmp/layout-proof-final.json
/tmp/clash-target/release/baselab-engine layout check rust/data/base_rules.json rust/data/target18.json
/tmp/clash-target/release/baselab-engine layout roundtrip rust/data/target18.json /tmp/layout-export.json
/tmp/clash-target/release/baselab-engine golden check fixtures/golden/cases.jsonl fixtures/golden/expected.jsonl --threads 16
/tmp/clash-target/release/baselab-engine armysearch-proof --root "$PWD" --catalog "$BASELAB_CATALOG" --out /tmp/layout-armysearch-proof
cargo fmt --manifest-path Cargo.toml -- --check
```

Current unchanged SHA-256 identities:

- Golden cases: `cea706d86516a2100876f9aa4ec7cdd5de32f691202f9a6d049b64e690d172ab`
- Golden expectations: `7bcf0c5f160aa1e98cbc7a76f9947fae9eb089cce1020cd7553f392565e1bbd5`
- Catalog: `91f122ee1649c50fca3cda9bb4d36b837dd2714e071e025b010613a5424979cc`
