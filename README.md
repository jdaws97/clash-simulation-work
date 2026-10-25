# clash-simulation-work

Clash Lab is an offline, conditional Clash of Clans combat simulator and
experiment toolkit. This private repository preserves the v29 engine and adds
portable fixtures, bounded regression checks, and reproducible development
benchmarks. It does not establish live-game accuracy or predict win rates.

The current draft includes a [runnable full-village prototype](docs/legacy/FULL_COMPARISON_QUICKSTART.md)
and an [independently checked publication summary](docs/legacy/PROTOTYPE_PUBLICATION.md).
Two complete synthetic TH18 battles compare declared TH16 attack plans against
the same Legend I Hot Candle defense. Running them requires explicit acceptance
of the provisional air-contact convention. These are conditional army-plan
results, with zero held-out game calibration; they do not establish an optimized
base, army ranking, or gameplay recommendation.

This is a publication baseline for review, not a calibrated release. Strict
mode still rejects the original full-air case at 18.305471759 simulated seconds
because of Dragon Duke isolation contact chatter. An explicitly selected
[sampled-isolation experiment](docs/legacy/DUKE_CONTACT_EXPERIMENT.md) now completes that
case and agrees under a half-step check, but its unmeasured cadence materially
changes the result. It is not a verified game mechanic. See
[publication scope](docs/legacy/PUBLICATION.md).

For practical starting layouts and loadouts, see the [TH16 account-matched guide](docs/TH16_USE_NOW_GUIDE.md). It includes the approved recorded game levels, distinguishes creator recipes from untested adaptations, and checks housing against the pinned catalog. These recommendations are not simulator-validated rankings.

Build the native Rust workspace offline in WSL with the installed toolchain:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-ws
cargo build --workspace --all-targets --release --locked --offline
export BASELAB_CATALOG="$PWD/rust/data/catalog.json"
/tmp/clash-target-ws/release/clash --help
scripts/verify.sh
```

The workspace uses only the Rust standard library. Its libraries live under
`crates/`; `clash-engine` depends only on `clash-data` and `clash-layout`.
The compiler, scoring, searches, fidelity and video tools have separate crates.
`clash` accepts all former engine subcommands, plus `clash fidelity ...` and
`clash video ...`. Compatibility binaries `baselab-engine`, `fidelity` and
`vidmine` retain their arguments. Video processing still requires explicitly
installed FFmpeg/FFprobe; its synthetic verification tests require no media.

`scripts/verify.sh` checks formatting, builds and tests every workspace target,
then runs battle and plan goldens, guardian fixtures and native search/layout
proofs. It never downloads components or regenerates fixtures. Clippy is strict
when clean, otherwise advisory; a missing local component is reported.
The script and its `rust/verify.sh` compatibility wrapper work from any directory:

```sh
cd /tmp
/absolute/path/to/clash-lab/scripts/verify.sh /tmp/clash-target-ws
```

Shared regression inputs are under `fixtures/`. The pinned runtime catalog,
rules and castle table stay at `rust/data/` during this migration; `data/` has
not been reorganized. Set `BASELAB_CATALOG` to an explicit absolute path when
selecting a catalog, and pass `--root` to compiler/search/fidelity commands
outside the checkout. Account, calibration and observation defaults are
unchanged; select private inputs explicitly for personal workflows.

Python under `src/` and `tools/` is frozen for later capability ports and cleanup.
The current native gate runs Rust only. See [the workspace migration record](docs/RESTRUCTURE_LOG.md)
and [Rust runtime contract](docs/RUST_PORT.md) for scope and verification evidence.

See [engine status and completion criteria](docs/ENGINE_STATUS.md),
[working rules](AGENTS.md), and [third-party notices](THIRD_PARTY.md). Personal
profiles, observations, media, game-memory captures, generated reports, and old
session transcripts remain outside Git. Legacy personal-report and workspace
cleanup scripts are preserved only in the private checkpoint.
