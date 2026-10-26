# Clash Lab

Clash Lab is an offline Clash of Clans simulator, search toolkit and evidence
pipeline. Rust is the executable reference. Regression checks protect the v29
behavior and explicit unsupported-content checks; synthetic results do not
establish real-game accuracy or predict win rates.

Build with the installed Rust toolchain; no downloads are needed:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-ws
export BASELAB_CATALOG="$PWD/rust/data/catalog.json"
cargo build --workspace --all-targets --release --locked --offline
"$CARGO_TARGET_DIR/release/clash" --help
scripts/verify.sh "$CARGO_TARGET_DIR"
```

On Windows use `clash.exe`. `scripts/verify.sh` also works from another working
directory using its absolute path. It checks formatting, offline builds/tests,
battle and plan goldens, guardian fixtures and native search/layout proofs.
It reports unavailable local components without downloading them.

The root Cargo workspace owns `crates/`. The engine depends only on the data
and layout libraries. One `clash` executable exposes simulation, plan compilation,
scoring, army/base search, fidelity, video, data import and playbook tools:

```sh
clash --help
clash armysearch run --help
clash basesearch --help
clash fidelity --help
clash playbook --help
```

See the [documentation index](docs/README.md), [runtime contract](docs/RUST_PORT.md)
and [current scope and limitations](docs/ENGINE_STATUS.md). The
[catalog pipeline](docs/DATA_PIPELINE.md), [digitizer](crates/clash-dataimport/src/digitize/README.md),
[playbook pipeline](docs/PLAYBOOK_PIPELINE.md) and
[base search](crates/clash-basesearch/README.md) document their native commands.
Video processing requires installed FFmpeg/FFprobe; providers must be configured
explicitly for acquisition or authoring. Ordinary verification is offline.

`fixtures/` contains declared regression inputs. `data/` and `rust/data/` retain
their existing organization and pinned runtime files. Select personal accounts,
observations and catalogs explicitly. Keep new personal inputs in ignored
`private/`; never add credentials, media, transcripts or raw captures to Git.

`local/` is an ignored store for retained transcripts, research, extracted
attacks, digitizer intermediates, fidelity ancestry and small cited evidence.
Its local `README.md` indexes the stored files. `output/` is disposable generated
scratch and was removed by G4. Some Rust defaults still require the lead's path
patch; pass the explicit `local/` paths listed in
[the cleanup report](docs/CLEANUP_G4.md) until that patch merges.

Python remains only for workflows with no complete native replacement and their
import dependencies: wiki acquisition/normalization, source audits/manifests,
aggregate/meta calibration, policy training and surrogate research. Keep
`pyproject.toml` and the local `.venv/` while those workflows remain. The
[per-file disposition](docs/CLEANUP_G4.md) records the remaining ports. New engine
or compiler behavior belongs in Rust. Historical Python parity procedures are
retired; [historical records](docs/history/README.md) are dated evidence.

See [working rules](AGENTS.md) and [third-party notices](THIRD_PARTY.md).
