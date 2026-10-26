# Native fidelity workflow

`clash fidelity` replays observations, fits defense distributions, evaluates
cross-validation, compares observed replays and produces the fidelity board.
It does not execute Python. Native battle-log collection, decoding and snapshot
recording are documented in [the ingestion port](../crates/clash-fidelity/PORT_LC.md).

Use an offline-built `clash`, explicit private observations and a reviewed fit:

```sh
clash fidelity replay /private/archive/battles.jsonl --root "$PWD" \
  --calibration /private/fit.json --attacker playbook --threads 4 \
  --out local/fidelity/replay.json
clash fidelity cv --root "$PWD" --log /private/archive/battles.jsonl \
  --attacker playbook --threads 4 --fold-dir local/fidelity/cv \
  --out local/fidelity/cv.json
clash fidelity board --root "$PWD" --fold-dir local/fidelity/cv \
  --out local/fidelity/board.json
clash fidelity observed /private/observed-replay.json --root "$PWD" \
  --out local/fidelity/observed.json
```

Create destination directories as needed. `clash fidelity --help` lists commands;
use explicit `--out` and `--fold-dir` until the lead applies the pending defaults
listed in [G4](CLEANUP_G4.md). The TH18 experiment also has one pending input-path
change; it is not part of ordinary verification.

Visible scouting commits using independent hidden-state planning, then evaluates
on the actual state. `random` and labeled `oracle` policies remain explicit;
see [SCOUTING.md](SCOUTING.md). Unknown share-code names, unsupported builds,
invalid historical setups and hash/ancestry mismatches remain explicit failures.
Snapshots use UTC half-open periods and preserve historical levels. Never overlay
today's account onto a frozen observation without an explicit, labeled assumption.

CV fits stable-ID training folds with disjoint hash-bound ancestry. Supplied
saved JSON metrics may be compared with `--reference FILE`. Python execution,
implicit CV2 training and retired `--python`, `--reference-cv2` and
`--archive-cv2` paths are unavailable. Baseline metrics need separate training
observations; a fit/evaluation overlap is not held-out evidence.

`local/fidelity/` retains the original fit/report/prepared-job/outcome ancestry.
These archived bytes retain their original hashes and historical path strings;
use explicit paths and do not rewrite them to manufacture new provenance.
The [RF1 record](history/FIDELITY_RF1.md) preserves dated results and legacy
comparison procedures as history. They are not current execution instructions.

Native defense fitting does not replace the retained Python aggregate-target
`calibrate.py` or per-build/family `calibrate_meta.py` workflows. Their pending
ports and dependencies are listed in [CLEANUP_G4.md](CLEANUP_G4.md).
