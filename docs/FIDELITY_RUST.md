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
  --attacker playbook --threads 4 --prior data/source/meta-calibration-r8.json \
  --fold-dir local/fidelity/cv \
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

Public meta strengths can be refitted with the native aggregate-target port:

```sh
export CLASH_PRIVATE=none
export CLASH_CATALOG="$PWD/data/generated/catalog.json"
unset BASELAB_PARAMS_FILE BASELAB_FLYER_RANGE BASELAB_PACE BASELAB_GAPS
clash fidelity meta-fit --root "$PWD" --replicates 2 --threads 32 \
  --out local/fidelity/meta-calibration.json
clash fidelity meta-fit --root "$PWD" --town-hall 18 --replicates 2 --threads 32 \
  --out local/fidelity/meta-fit-th18-sensitivity.json
```

`meta-fit` requires public mode before loading the compiler. It fits the five
TH16 builds with a `three_star` target in the pinned TrophyCoach snapshot
`data/source/meta-armies-2026-10-15.json`, on the ten ranked TH16 transcriptions
in `data/source/reference-bases/ranked-2026-10-24`. It retains their pinned
levels, walls, heroes and hidden hypotheses; it does not read or overlay a live
account. The old pool containing the user's own layout is excluded because
that layout also underlies the held-out defense CV. TH17/18 retain the frozen
borrowing rule: arithmetic mean of same-archetype TH16 strengths, otherwise
1.0; these entries remain `uncalibrated`. The four ranked TH18 bases can be
fitted separately with `--town-hall 18`; this is a sensitivity, never the r9
prior or a held-out replay validation.

The attacker uses the current playbook compiler (with explicit generic fallback
when a family has no cited book), all eight visible scouting candidates, three
hidden planning samples and all five equally weighted skill quantiles per
replicate. `--angles`, `--replicates`, `--iterations`, `--lower` and `--upper`
control the budget and search (defaults 8, 2, 6, 0.4, 2.5). `--seeds` is rejected:
replicates always include all five quantiles. A five-point log grid precedes
log bisection. Plan, hidden-state, planning and execution draws are fixed
across strengths. Common randomness cannot guarantee monotonic game outcomes;
equal-weight isotonic regression makes the search response monotone. Reports
retain raw/projected curves, reversals, actual final-strength rates, target
errors and boundary clamps. This is a finite public-pool fit, not an accuracy
claim about the population behind TrophyCoach's last-30-day aggregate.

The flat build mapping includes `_provenance`: engine HEAD, executable-source
and public-data SHA-256 manifest, catalog and base hashes, settings and seed
formulas. A changed input aborts the write. The manifest includes the fitter,
replay adapter and executable engine/compiler/scoring closure; it excludes the
prior-admission code containing r9's own digest, avoiding a circular hash. Git
must resolve HEAD; a relocated Windows worktree running in WSL may need an
explicit `GIT_DIR` pointing to its existing worktree metadata.

CV accepts `--prior FILE` for either byte-pinned public r8 or r9, including an
identical archived copy. The default remains r8. Unknown or altered priors and
defense-fitted priors are rejected; a self-declared public status grants no
ancestry exemption. Each fold refits from the selected prior, with stable-ID
fold assignment, training-only constant baselines and disjoint hash-bound
ancestry. Use separate output directories for a paired comparison:

```sh
# Set CLASH_PRIVATE to the existing read-only private archive for these CV runs.
clash fidelity cv --attacker playbook --seeds 20 --threads 32 \
  --prior data/source/meta-calibration-r8.json \
  --fold-dir local/fidelity/cv-r8 --out local/fidelity/cv-r8.json
clash fidelity cv --attacker playbook --seeds 20 --threads 32 \
  --prior data/source/meta-calibration-r9.json \
  --fold-dir local/fidelity/cv-r9 --out local/fidelity/cv-r9.json
# Return to public mode for replay checks.
CLASH_PRIVATE=none clash fidelity th18 --variants current --threads 12 \
  --reference /path/to/existing/th18/results.json \
  --calibration data/source/meta-calibration-r9.json --out local/fidelity/th18-r9.json
CLASH_PRIVATE=none clash fidelity observed data/source/replays/2026-10-21-maroon-machine.json \
  --calibration data/source/meta-calibration-r9.json --threads 6 --out local/fidelity/observed-r9.json
```

The historical Python `calibrate_meta.py` is replaced by `meta-fit`; the
separate Python `calibrate.py` aggregate-target workflow remains unported.
