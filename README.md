# clash-simulation-work

Clash Lab is an offline, conditional Clash of Clans combat simulator and
experiment toolkit. This private repository preserves the v29 engine and adds
portable fixtures, bounded regression checks, and reproducible development
benchmarks. It does not establish live-game accuracy or predict win rates.

This is a publication baseline for review, not a calibrated release. The original
full-air case encounters unresolved Dragon Duke isolation contact chatter at
18.305471759 simulated seconds. The baseline rejects this case diagnostically;
it does not complete the battle. See [publication scope](docs/PUBLICATION.md).

Python 3.10 or newer is required. Runtime code uses the standard library; no
account login, game process, network connection, or private player file is
required for the portable suite. Run from the source checkout:

```console
python -B verify.py
python -B run.py --data data --output reports/catalog-audit.json audit
python -B tools/run_full_army_regression.py
```

The combined-army runner repeats one 16-second synthetic lifecycle scenario and
prints input, source, outcome, event, and resource fingerprints. It checks
reproducibility and ownership; its distant single-target layout is not an
army-strength benchmark. Complete-village builders are development tools and
can encounter explicitly unsupported mechanics or numerical policies.

The suite uses a declared synthetic account and evidence fixtures. To verify
the preserved private replay checkpoint separately, use
`python -B verify.py --private-root PATH_TO_PRIVATE_CHECKPOINT`. This is optional,
is never silently included in the portable result, and does not calibrate combat.

CI runs the portable suite and CLI on Ubuntu and Windows with Python 3.10 and
3.12, plus Black 24.10.0. Formatting locally:

```console
python -m pip install black==24.10.0
python -m black --check --workers 1 .
```

See [engine status and completion criteria](docs/ENGINE_STATUS.md),
[working rules](AGENTS.md), and [third-party notices](THIRD_PARTY.md). Personal
profiles, observations, media, game-memory captures, generated reports, and old
session transcripts remain outside Git. Legacy personal-report and workspace
cleanup scripts are preserved only in the private checkpoint.
