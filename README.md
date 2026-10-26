# Clash Lab

Clash Lab is a Rust workspace for offline Clash of Clans simulation, army and
base search, and evidence processing. The v29 engine is the executable reference:
its deterministic math and explicit unsupported-content errors are protected by
frozen battle and compiled-plan goldens. Synthetic regression results establish
model consistency; they do not establish real-game accuracy or win rates.

The reusable libraries define data, layouts, battle execution, plans and scoring.
Tool crates build on those libraries; the engine depends only on data and layout.
One supported `clash` CLI dispatches the workflows.

| Crate | Purpose |
| --- | --- |
| `clash-data` | Catalogs, statistics, JSON/wire formats, hashes and snapshot readers. |
| `clash-layout` | Layout models, geometry, rules, admission and rendering. |
| `clash-engine` | Deterministic battle simulation and attacker/playbook execution. |
| `clash-plans` | Army libraries and compilation of armies/playbooks into executable plans. |
| `clash-scoring` | Scenarios, scouting policy, uncertainty and battle scoring. |
| `clash-armysearch` | Legal army/program proposals, evaluation, search and reports. |
| `clash-basesearch` | Admitted base proposals, evaluation, archives, search and diagnostics. |
| `clash-fidelity` | Replay observations, calibration, cross-validation and fit ancestry. |
| `clash-vidmine` | Local video probing, extraction, identity, timing and spatial evidence. |
| `clash-dataimport` | Source catalog construction, keyless battle-log ingestion and digitization. |
| `clash-playbook-tools` | Transcript import, citation checks, playbook authoring and research queues. |
| `clash-cli` | Command dispatch, simulation/compile/score adapters and regression proofs. |

## Quick start

Build from the workspace root in WSL with the installed toolchain:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-g5
cargo build --release --locked --offline
export PATH="$CARGO_TARGET_DIR/release:$PATH"
clash --help
mkdir -p local
clash plan compile custom:user-fireball-warden 0 123 local/plan.json --root "$PWD"
clash guardian-check
```

`cargo build --release` builds the CLI through the workspace's default member;
`--locked --offline` keeps dependency resolution local. On Windows the executable
is `clash.exe`. No Python runtime or Supercell API key is required.

Commands below show each workflow. Supply your own battle, scoring bundle,
search configuration and video at the indicated paths. Output belongs in `local/`.

```sh
clash simulate run local/battle.json
clash compile custom:user-fireball-warden 0 123 local/plan.json --root "$PWD"
clash score local/score-bundle.json --root "$PWD" --threads 4
clash fidelity replay private/live/battles.jsonl --root "$PWD" --out local/replay.json
clash armysearch run --root "$PWD" --account data/source/accounts/public-th16.json --out local/armysearch
clash basesearch smoke --out local/basesearch --threads 4
clash video probe /path/to/replay.mp4
clash dataimport catalog --root "$PWD" --wiki-root data/source/wiki \
  --registry-out local/registry.json --out local/catalog.json
clash playbook verify --all --transcripts local/sources/transcripts \
  --report local/playbook-verification.json
```

Video processing needs installed FFmpeg/FFprobe and an explicitly selected local
video. Do not download or retain videos in this repository. Catalog regeneration
needs an existing normalized wiki mirror; ordinary builds and verification use
the pinned generated catalog without it. Citation checks need the corresponding
local transcripts. Missing sources are errors, not invented evidence.

## Data and local work

```text
data/
  source/       Pinned external/model inputs: ClashKing snapshots, gamecsv,
                balance overrides, mechanics evidence, armies, playbooks,
                calibration priors, layouts/reference bases and the synthetic
                public account (accounts/public-th16.json).
  generated/    catalog.json, registry.json, base_rules.json, clan_castle.json,
                manifest.json and synthetic target17.json/target18.json.
  licenses/     Attribution/license files for the source snapshots.
fixtures/       Declared regression inputs, including the frozen goldens.
local/          Gitignored derived data, reports, transcripts and fit ancestry.
private/        Gitignored player data: your-levels.json (account levels) and
                live/ (battles.jsonl, player-latest.json, base-history.json).
```

`data/source/catalog.json` is the distinct upstream catalog used by video identity
analysis. `data/generated/catalog.json` is the engine's runtime catalog; their
schemas are different. The ignored wiki mirror lives in `data/source/wiki/`.
Pinned generated data stays versioned so verification works offline.

Runtime catalog selection is an explicit command/configuration path, then
`CLASH_CATALOG`, then legacy `BASELAB_CATALOG`, then
`data/generated/catalog.json` under the selected workspace root. For example:

```sh
CLASH_CATALOG="$PWD/local/catalog.json" clash guardian-check
```

Existing provenance strings, source hashes, fit ancestry and historical manifest
keys retain their original identities across relocation. New fits and search
checkpoints receive new input fingerprints; old fits must not be relabeled.
The [restructure log](docs/RESTRUCTURE_LOG.md) maps every moved file.
Player data stays out of Git. Tools read `private/your-levels.json` and
`private/live/` when they exist and otherwise fall back to the synthetic
`data/source/accounts/public-th16.json` (regenerate it with
`clash dataimport account caps --th 16 --out ...`). `CLASH_PRIVATE=none` forces
public mode, and `CLASH_PRIVATE=DIR` selects another private directory. The
verification gate and plan goldens always use public mode. Point the battle-log
collector at `--out private/live`. Never add credentials, raw captures or
downloaded media to Git.

## Verification

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-g5
scripts/verify.sh
```

The gate checks workspace formatting, offline locked release builds/tests,
strict Clippy, battle goldens at one and four workers, plan goldens, guardian
fixtures, army-search fuzz/determinism, layout admission/geometry/inventory and
base-search proofs, plus synthetic video/dataimport/playbook tests. It prints
`ALL CHECKS PASSED` only after every command succeeds. It also works from another
working directory when invoked by absolute path.

`fixtures/golden/{cases,expected,plans}.jsonl` are frozen regression contracts.
Organizational changes must keep every byte unchanged; never re-record them to
make a move pass. See the [golden policy](docs/GOLDEN.md).

Start with the [documentation index](docs/README.md),
[architecture and data flow](docs/ARCHITECTURE.md),
[runtime contract](docs/RUST_PORT.md), and [scope/limitations](docs/ENGINE_STATUS.md).
The [data pipeline](docs/DATA_PIPELINE.md), [playbook pipeline](docs/PLAYBOOK_PIPELINE.md),
[base-search guide](crates/clash-basesearch/README.md), and
[video guide](crates/clash-vidmine/README.md) describe tool inputs and commands.
See [working rules](AGENTS.md) and [third-party notices](THIRD_PARTY.md).
