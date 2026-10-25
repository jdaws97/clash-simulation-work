# Native catalog source pipeline

`clash dataimport catalog` constructs the runtime catalog from source inputs.
It never reads `rust/data/catalog.json` or `data/registry.json`. The native builder and its declarations
live entirely in `crates/clash-dataimport/src/catalog/`.

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-lB
cargo build -p clash-cli --bin clash --release --locked --offline
"$CARGO_TARGET_DIR/release/clash" dataimport catalog \
  --root /path/to/checkout \
  --wiki-root /path/to/local/wiki \
  --registry-out /tmp/registry-rebuilt.json \
  --out /tmp/catalog-rebuilt.json
```

`--root` defaults to the workspace containing the executable's source;
`--wiki-root` defaults to `ROOT/data/wiki`. Both can be set explicitly. There is
no sibling-checkout discovery, download, Python execution, account overlay, or
network dependency. The ignored mirror must be supplied for regeneration;
ordinary engine verification still uses the committed runtime catalog offline.
Missing required source files are errors before catalog output is written.

## Inputs and transformations

1. `data/clashking-static-data.json` supplies home-village records, exact level
   numbers, combat stats, equipment ability levels, and targeting flags.
2. Normalized wiki `tables/*.json` supplies infobox attributes, level and charge
   rows, and ability columns. `text/*.txt` supplies registry mechanic notes;
   selected `pages/*.json` supplies categories used to discover crafted
   defenses and equipment released after the ClashKing snapshot. Home Village
   pages take precedence over unqualified pages. Summon subpages are explicit
   in `registry.rs`. Temporary Meteor Golem tables remain excluded.
3. The resulting 253-record registry reproduces `data/registry.json` as parsed
   JSON and reproduces its LF bytes through the native registry encoder.
   Its historical Inferno Dragon L12 repair is reconstructed from the
   exact `characters.csv` VisualLevel/DPS/DPSLv2/DPSLv3 cells (91/182/1820),
   restoring the three wiki-shaped beam columns. The mirror repeats level 11;
   this correction was already documented in `ENGINE_V2.md` on October 18.
   No new level or value is inferred from array position.
4. Runtime registry additions preserve Birthday Boom, Yellow Card, Lavaloon
   Pup and the Monolith/Multi-Gear Tower charge rows from `stats.py`.
   `data/balance-overrides.json` schema 1 then applies explicit replacement
   totals to both the registry and ClashKing source view. Missing override
   entities/levels in the registry are errors; ClashKing omissions retain the
   legacy missing-field fallback.
5. `data/gamecsv/v18.200.9/{buildings,characters,heroes,pets,projectiles,
   special_abilities,spells}.csv` supplies mechanics absent from ClashKing.
   CSV cells inherit within each named entry, reset at the next entry, and
   retain ordered rows. Mechanic lookup clamps positional levels exactly as
   the former exporter did; unit-number fallback separately checks VisualLevel
   so a missing current troop level cannot borrow an unrelated older level.
6. `specs.rs` declares the 88 explicit behavior profiles and generic infobox
   inference. `tables.rs` declares the preserved v29 building, trap, setup,
   loadout and timing model inputs. These are native source declarations,
   separate from resolved game numbers. The three explicitly unsupported
   event troops remain excluded. The existing engine rejection code is intact.
7. Resolve unit/summon profiles, 1,782 unit-number rows, equipment abilities,
   pet ranges/speeds, spell radii, tower/mortar profiles and donation research
   limits. Merge `data/warden-weights.json`; obtain siege donation limits from
   the distinct `tables/Clan_Castle.json` Siege Machine Level Cap table.
   Serialize the complete 256-record runtime registry and 146 unit profiles.

Numeric precedence is explicit balance totals, then published ClashKing
fields, then CSV missing-field fallbacks and wiki values/mechanics under the
same per-field rules as the frozen exporter. A wiki damage-per-hit value is
rescaled when its DPS disagrees with the authoritative DPS; burst timing,
healer behavior, effective summon housing and exact radius rounding are
preserved. The `BASELAB_DT`, `BASELAB_FAST_END`, `BASELAB_WINDUP`,
`BASELAB_FLYER_RANGE` and `BASELAB_PACE` export options retain their defaults
and behavior. Clear those variables when reproducing the pinned export.

## Exact ignored wiki inputs

[`wiki-inputs.sha256`](../crates/clash-dataimport/src/catalog/wiki-inputs.sha256)
records the exact mirror-relative paths and original byte hashes: **516 table
JSON files, 191 page-metadata JSON files and 254 text files**, 961 files total.
This includes the entire pinned table discovery inventory, even tables whose
titles/categories exclude them from the registry. No mirrored article text or
raw acquisition payload is embedded in Git.

Every listed file must exist. This prevents removal of a preferred Home
Village table from silently selecting a different page, removal of a text file
from silently dropping notes, or missing category pages from dropping crafted
content. Additional unlisted mirror files do not change the pinned discovery
set. When adopting a newer mirror, review/update this manifest's discovery
membership and hashes along with the rebuilt registry/catalog. Hashes identify
the accepted snapshot; the builder permits changed bytes for patch work, while
the source-equivalence test verifies every pinned hash.

The mirror inputs are normalized table JSON and plain text. HTML acquisition,
HTML rowspan/colspan normalization, mirror refresh, patch validation and general
data manifests remain separate workflows; this port does not replace those
tools or claim to fetch the wiki.

## Equality and legacy provenance

The native catalog is **canonical-JSON identical** to the pinned export:
compare object members by key, retain array order and compare parsed numbers
exactly, with no numerical tolerance. Its serialized bytes differ because the
native wire writer uses compact JSON and a final LF; the old exporter also
distinguished integral float spellings. The old catalog `note` string is
retained for payload compatibility. The native registry encoder preserves
indentation, field order and the registry schema's integer/float spellings,
reproducing `data/registry.json` byte-for-byte in this LF checkout.

The catalog retains the legacy `resolved.source_hashes` fields. The registry
field identifies the rebuilt registry intermediate serialized with **CRLF**: the pinned
catalog was exported on Windows before the checkout's LF convention. The
builder encodes its rebuilt intermediate with CRLF before hashing. The
balance-override field hashes the actual file bytes, matching the exporter.
For the pinned sources these are respectively
`abe352222a0c93757708aa7f7b5c0e6378bd8ae6dfc045d4cb6243847368bc47`
and `a817239ccfa37fa898f332dffe2e54b7a89ebef28a41afbfb93234c9486fafd7`.
All registry/catalog values and the registry provenance hash are recomputed
from source inputs. Neither generated JSON file is an input, including for
hashing. An optional `--registry-out` writes the rebuilt pre-runtime
intermediate with LF to a separate reviewable location; the compatibility hash
uses the CRLF encoding independently of that output path.

## Verification and predecessor disposition

```sh
# Always available offline: complete recorded CSV/spec/unit-number comparisons,
# a small synthetic override case, and explicit missing-wiki rejection.
cargo test -p clash-dataimport --release --locked --offline catalog

# Source acceptance: validates all wiki hashes and compares both complete outputs.
CLASH_CATALOG_WIKI=/path/to/local/wiki \
  cargo test -p clash-dataimport --release --locked --offline \
  complete_source_pipeline -- --ignored --nocapture

# Run after regeneration; uses the new catalog without altering the pinned one.
BASELAB_CATALOG=/tmp/catalog-rebuilt.json "$CARGO_TARGET_DIR/release/clash" \
  golden check fixtures/golden/cases.jsonl fixtures/golden/expected.jsonl --threads 1
BASELAB_CATALOG=/tmp/catalog-rebuilt.json "$CARGO_TARGET_DIR/release/clash" \
  golden check fixtures/golden/cases.jsonl fixtures/golden/expected.jsonl --threads 4
BASELAB_CATALOG=/tmp/catalog-rebuilt.json "$CARGO_TARGET_DIR/release/clash" \
  golden plans check fixtures/golden/plans.jsonl --root "$PWD"
scripts/verify.sh "$CARGO_TARGET_DIR"
```

The catalog/registry source capability of `src/baselab/registry.py`,
`src/baselab/engine/stats.py` and `src/baselab/engine/specs.py` is replaced;
the existing native data/engine readers cover runtime use. These files can
retire with their remaining Python consumers. This lane deletes no frozen
Python files. The `catalog` branch of `tools/baselab/rust_export.py` and its
catalog-specific dependencies on `gamedata.py`, `mechanics.py`, `heroes.py`,
`units.py`, `spells.py`, `defense.py`, `battle.py`, `plans.py`, `playbook.py`,
`traps.py` and `loadouts.py` are replaced. Their unrelated capabilities and
the exporter's jobs/battle/trace/parity commands require their own deletion
decisions; this lane does not claim complete replacement of those files.

All equivalence and engine checks are regression proofs over the pinned
sources and declared synthetic fixtures, not real-game calibration.

## Lane lB acceptance receipt (WSL, 2026-10-25)

The release source-acceptance test passed with the mirror explicitly selected
as `/mnt/c/Users/jarod/Documents/clash-lab/data/wiki`. It verified every one
of the 961 input hashes, the complete registry and catalog, and a declared
source perturbation: a temporary source root contained neither generated JSON
file, and adding a Barbarian L1 HP override changed the rebuilt HP to 77.

| Check | Result |
| --- | --- |
| Rebuilt registry LF bytes | Identical; SHA-256 `c05e9f3378c2164e1c8ae177d2b38b2d0f67cf61f5f82a41d8202e153a6e1c08` |
| Rebuilt runtime catalog | Canonical-JSON identical, including all source hashes, arrays and numeric values |
| Ordinary focused catalog tests | 4 passed; source acceptance additionally passed when explicitly enabled |
| Regenerated-catalog battle goldens | 868/868 at both 1 and 4 workers |
| Regenerated-catalog plan goldens | 1354/1354 |
| Missing default wiki mirror | Explicit CLI error; no output file created |
| `scripts/verify.sh /tmp/clash-target-lB` | Exit 0; `ALL CHECKS PASSED` |
| Full-gate base-search proposal proof | 93000 attempts, 81864 accepted engine builds, 3000 crossovers; workers 1/4/16/1 |
| Frozen files | Three golden files, committed catalog and registry retain their original byte hashes |

The gate included formatting, offline locked workspace build/tests, battle and
plan goldens, 50 guardian fixtures, army-search proofs, the 100000-mutation
layout proof and 24 video tests. Clippy was unavailable in the installed
toolchain; the gate reported that limitation and downloaded nothing.

Local receipts are `/tmp/lB-source-acceptance.log`, `/tmp/lB-regeneration.log`,
`/tmp/lB-regenerated-goldens.log` and `/tmp/lB-verify-final.log`. Rebuilt outputs
are `/tmp/lB-registry.json` and `/tmp/lB-catalog.json`; no pinned data was
overwritten. Only the requested additive `docs/DATA_PIPELINE.md` is outside
the lane's catalog source directory; no shared Rust file was changed.
