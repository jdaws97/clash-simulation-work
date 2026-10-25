# Native fidelity measurements (RF1)

`fidelity` ports the battle-log decoder, defensive setup reader, real-defense
replayer, distribution calibration, fidelity board, observed replay controller,
and TH18 replay experiment to Rust. Runtime measurement and fitting do not
invoke Python. The executable lives under `rust/src/fidelity/`; its Cargo binary
registration is the only RF1 change outside that directory and this document.
RM1 owns engine mechanics and `params.rs`; RF1 does not modify them. The v29
Python source and preserved checkouts remain unchanged.

Build from the repository root:

```sh
CARGO_TARGET_DIR=/tmp/clash-rf1-target cargo build \
  --manifest-path Cargo.toml --offline --release --bin fidelity
F=/tmp/clash-rf1-target/release/fidelity
```

Pass `--root /path/to/clash-lab` when running outside the repository. Inputs and
output paths are relative to that root. Reports with real observations stay in
ignored `output/fidelity-rust/`; no profiles, share codes, media, transcripts,
memory captures or credentials are added to Git. The tests declare their
synthetic inputs explicitly. They are software checks, not game calibration.

## Decode and reconstruct defenses

```sh
$F decode data/live/battles.jsonl --out output/fidelity-rust/decoded.json
$F replay --attacker generic --threads 4 --seeds 5 \
  --out output/fidelity-rust/replay.json
$F check-a --attacker playbook --threads 4 \
  --calibration data/meta-calibration-r8.json \
  --out output/fidelity-rust/a-visible.json
```

Share-code IDs come from the existing ClashKing static export. Hero mode, pet
and both equipment slots survive decoding. An unparsed hero suffix or unknown
troop, spell, equipment or pet excludes the entire army; content is never
silently dropped to make an attack runnable. Duplicate observations are
deduplicated by the same SHA-256 identity used by Python: compact JSON of
`[battleTimestamp, opponentTownHallLevel, armyShareCode]`. Reports expose the
digest rather than the code or player identity.

Snapshot lookup uses UTC instants, inclusive start and exclusive end. It rejects
overlaps and verifies the canonical JSON SHA-256 before loading a frozen setup.
Canonical hashing preserves integer versus float tokens and Python's ASCII
string escaping. Legacy inclusive-day periods are only a fallback. Calibration
requires explicit historical defense/hero/wall levels in that fallback;
replay follows the frozen Python tool's current-account fallback and labels it
`current_levels_fallback_unverified`. `--base FILE` explicitly chooses the latter
behavior. The supplied archive currently has no frozen snapshots: historical
layout and occupancy assumptions remain material limitations of this dataset.

Logged armies use the Rust compiler and its content checks. The sole TH15
observation uses a narrow adapter: the compiler's TH-independent role construction
is entered at TH16, then the actual TH15 is restored **before** stock resolution,
level validation and battle construction. It never runs with TH16 combat levels.
The compiler's documented logged-inventory exceptions remain visible in stderr;
unsupported content still fails. Other attacker Town Halls outside the compiler's
supported range are not silently remapped.

Calibrated replay uses share-weighted geometric family strength at the attacker's
actual TH, then TH16 fallback, then the legacy family fallback. `--strength raw`
disables the calibration multiplier but retains the existing skill quantiles.
`--techniques` adds the frozen generic Queen/Warden charge candidates.

## Scouting and scoring

Visible scouting is the default and delegates to the native scout described in
[SCOUTING.md](SCOUTING.md). `--scout-policy random|visible|oracle` selects its
policy. Visible planning uses independent hidden layouts; real-state outcomes
are evaluated only after commitment. Native policies use the documented fresh
execution seed namespaces. Their deterministic diagnostic replays verify the
native execution and observe end reasons; reports count that additional work
separately. Oracle end-reason counts cover every evaluated candidate, including
losers, rather than only retained winners.

`--legacy-oracle` is an explicit compatibility mode for frozen `replay_log.py`:
eight sides at `0.21 + 2*pi*k/8`, identity-derived seeds, all side pairs, and the
completed-battle trophy/destruction maximum. It also preserves that tool's
omission of league modifiers. Ordinary replay retains recorded league modifiers;
fitting always retains them. The legacy mode is an unattainable oracle estimate,
not visible scouting. `--scout N`, `--angles N`, `--seeds N` and `--threads N` are
explicit; all five default replay seeds cover all five skill quantiles.

Check A reports three-star Brier, destruction MAE, three-star duration ratio,
timeout share, pooled failed duration and **matched failed duration** on the same
real failed defenses. Weighted medians preserve scouting probability mass.
End reasons distinguish total destruction, exhausted offense, timer with live
fighters, and timer with inventory only. No combat continuation or inventory
spending is added for measurement.

Every defense also retains its **joint** forecast over stars 0–3 and destruction
bins `[0,10), ..., [90,100), {100}`. Reports include joint negative log score,
mean squared lower-orthant joint CDF score, and marginal star RPS. The joint CDF
score respects both ordered axes; it does not impose an arbitrary flattened
ordering on the grid. Joint scores use the same declared 2% uniform mixture for
simulation and baseline; lower is better. Battle logs contain only final outcomes
and durations, so event metrics are reported by the observed replay command.

The constant baseline is estimated from **training observations only**. Use
`--train-log FILE`, a verifiably bound fit containing training rows present in the
selected log, or `cv`. Without training data baseline scores are null. An r8-only
Check A does not fit a constant to its evaluation outcomes. CV2's old pooled
`real_rate * (1-real_rate)` value is retained only as an archival comparator;
it is not the fair fold baseline.

## Fit and cross-validation

```sh
$F calibrate --legacy-oracle --attacker playbook --min-family 2 \
  --grid 13 --max-correction 2 --monotonic-cap --threads 4 \
  --out output/fidelity-rust/calibration.json \
  --report output/fidelity-rust/calibration-report.json

$F cv --reference-cv2 --refit --legacy-oracle --attacker generic \
  --min-family 2 --grid 13 --max-correction 2 --monotonic-cap --threads 4 \
  --fold-dir output/fidelity-rust/cv2-refit-generic \
  --out output/fidelity-rust/cv2-generic-refit.json
```

The flat calibration mapping preserves saved build differences, prior strength,
correction, defense group, family/sample counts, uncertainty flags and provenance.
It remains readable by the existing calibration consumers. The report records
the saved calibration's exact byte hash, direct battle IDs, recursive prior
snapshots, source/input hashes, tested grid, discrete posterior interval,
boundary status, observed/baseline/fitted distributions and input-change status.

The loss is exactly the frozen fitter's objective:

```
-n * sum(observed_star_p * log(0.98 * simulated_star_p + 0.02/4))
+n * mean((observed_destruction_CDF - simulated_destruction_CDF)^2) on 0..99
+0.5 * (log(correction) / prior_sd)^2
```

Families below `--min-family` share their actual Town Hall pool; TH15 is not
folded into TH16. Default fitting uses four angles, one repeat and all five skill
quantiles, with paired seeds across the log-spaced correction grid. `--quick`
uses one army per group, median skill, two angles and three corrections. Its
output is marked a dry run and uncalibrated. Grid intervals describe conditional
generalized-posterior uncertainty, not proof of game accuracy.

CV always starts from the byte-pinned public r8 prior. Default fold assignment is
round-robin over sorted stable battle IDs, with no outcomes in the assignment.
`--reference-cv2` uses the archived three training partitions; `--refit` generates
new Rust fits for them. The fitter keeps its four-angle/one-repeat budget
independently of the eight-angle/five-seed check-A budget. `--monotonic-cap`
reproduces CV2's TH16 <= TH17 <= TH18 archetype cap, **before** hashing the saved
mapping. Each evaluation observation must occur in exactly one test fold.

An explicit calibration report is accepted only if its saved hash matches.
Every ancestor must be bound recursively, except the byte-pinned public r8
prior with no defense training IDs. Unknown or replaced ancestry puts every row
in sample. `--exclude-fitted` rejects unknown ancestry instead of suggesting a
held-out score. New CV verifies disjoint ancestry and training IDs before scoring
the test fold. The old CV2 reports predate saved-byte hash binding; replaying their
saved calibrations without `--refit` is labeled **archival comparison only**.

## Observed replay and the full board

```sh
$F observed data/replays/2026-10-21-maroon-machine.json \
  --levels observed --strength calibrated --seeds 6 --threads 4 \
  --out output/fidelity-rust/observed.json
$F board --only ABCD --label "native fidelity" --attacker playbook --threads 4 \
  --out output/fidelity-rust/board.json
```

The observed controller uses an existing Stage plan for timed deployments,
stock-checked spells and scheduled hero abilities over the normal engine tick.
It adds no engine callback or special damage rule. Automatic hero activation is
disabled so the recorded schedule owns abilities; this is explicit in the
report. Observed level badges override troop, hero, spell and pet levels;
`--levels engine|observed|both`, `--strength raw|calibrated|both` and
`--jitter TILES` retain the original experiment controls. Seed zero of each
configuration has no jitter; other seeds use the declared position uncertainty.

Curve errors use four-second evaluation points. Star and key-defense events
report conditional median/time MAE, observed/missing counts, occurrence Brier,
and share within the annotation's tolerance. A missing event is never replaced
with an invented 999-second observation. Board C reports actual TH16/TH17 family
inversions; D measures opening on the exposed Eagle and whether it falls by 30s.
These checks report failures rather than declaring the simulator accurate.

## TH18 first experiment

```sh
$F th18 --replicates 5 --threads 8 \
  --out output/fidelity-rust/th18-first-experiment.json
```

The experiment uses the four specified ranked reference bases, their existing
real outcome file, `custom:user-rr-oct25`, r8 strength, the account's TH16 army
levels, no league modifier, eight full-scout sides and all five skill quantiles
per replicate. It crosses three level conditions with three defending-CC
hypotheses and reports random, visible and oracle policies with paired execution
seeds and explicit budgets:

- TH18 maximum levels, including the selected crafted defense's module levels.
- One lower level on defenses, traps, guardian and defending heroes, floor one;
  economy and walls remain at TH18 maxima.
- TH17 maximum levels on buildings, defenses, heroes, traps and walls. TH18-only
  content remains at level one; the TH18 shell/artillery and topology remain.
- CC empty, saved default, or a declared 55-housing strong candidate of three
  Ice Golems and ten Archers. This candidate is not claimed to be empirically
  strongest, and none of these hypotheses is labeled an observed garrison.

The report saves the effective level and CC maps, per-cell joint distributions,
selected sides, seeds, source hashes and the four real star comparators. These
four single outcomes and uncertain transcriptions are development evidence,
not held-out calibration. A zero simulated three-star rate cannot establish
that a real three-star attack is impossible.

## Validation and result interpretation

Eight focused Rust tests cover decoder rejection, UTC boundaries, frozen
snapshot overlap/tampering, SHA/canonical JSON, proper joint scoring, missing
events and recursive calibration hash binding. They pass. Formatting is applied
with Rustfmt to the RF1 modules. The requested `python3 -B verify.py` was attempted;
that file is absent in this checkout.

The completed generic check-A determinism proof uses all 22 real defenses, eight
sides and five seeds. One, four and sixteen workers produce byte-identical rows,
including outcomes, weights, end reasons and execution scenarios. The common row
SHA-256 is `5b6c5cdef86ed2599d31c002e4b3d3856d426f7ba19b31a244124bfc7733eff9`.
See ignored `output/fidelity-rust/determinism-generic.json`.

Native reconstruction was checked against Python for every one of the 22
usable observations: all 22 layout objects match exactly. The first-side,
first-seed generic plans match all fields except last-bit strength differences
on a few rows and the TH15 adapter's descriptive label. There is one excluded
unknown army. Current r8 legacy-oracle results are:

| Attacker | Rust P(3*) | Archived CV2 P(3*) | Rust Brier | Archived CV2 Brier |
| --- | ---: | ---: | ---: | ---: |
| Generic | 0.4731 | 0.582 | 0.2249 | 0.177 |
| Playbook | 0.3938 | 0.433 | 0.2800 | 0.257 |

These are **not claimed to reproduce the old archive within simulation noise**.
The archived r8 reports were written around 04:22–05:09 on October 25, before
F12 (`36f730a`, 06:45), F13 (`3be5180`) and F14 (`d774e17`, 09:53), which is the
actual Python freeze point. In particular F12 preserved the log's Warden mode,
fixed explicit-generic fitting, and bound calibration reports; F13/F14 changed
playbook execution and Root Rider pacing/Recall behavior. Repeating the native
generic run against a read-only HEAD engine copy preceding RM1 gave identical
results, so the entire gap must not be attributed to the current RM1 work.

Fresh replay through the current frozen Python engine independently reproduced
the native generic run on every defense: maximum P(3*) difference
`1.78e-15`, destruction difference `5.12e-13` points, and conditional duration
difference `2.28e-13` seconds. Raw end-reason counts were identical. This was a
real run of all 880 battles, not a comparison of cached summaries. NumPy/Numba
were loaded from an existing local environment, with four workers and a writable
`/tmp` Numba cache; no Python source was edited.

The archived-kernel proof reconstructs commit `771a2f3` in `/tmp`, leaving the
original checkout untouched. For generic replay the port's `export-jobs
--archive-cv2` emits the pre-F12 wire without Warden mode. For playbook replay,
`archive_export.rs` is compiled as a temporary binary **against the historical
crate**, with that commit's playbooks and compiler. It reuses the native
decoder/setup reader and calibration/skill strengths, then resolves and executes
plans through the archived Rust runner. Its `--run` mode records raw end reasons.
Current production replay never opts into those old rules implicitly.

`score-jobs PREPARED OUTCOMES` performs the proof's complete aggregation in Rust.
`--train-log` selects the archived test partition and estimates the fair constant
from the complementary training observations. These old fits remain labeled
archival comparisons because their original reports lack saved-byte binding.

| Historical comparison, 22 defenses | Native historical P(3*) | Frozen Python P(3*) | Native Brier | Frozen Brier | Native destruction MAE | Frozen MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| r8 generic | 0.582468 | 0.582 | 0.176809 | 0.177 | 5.6325 | 5.6 |
| r8 playbook | 0.432792 | 0.433 | 0.255299 | 0.257 | 9.4062 | 9.4 |
| CV2 generic, saved fold fits | 0.559416 | 0.560 | 0.193263 | 0.193 | 6.0315 | 6.009 |
| CV2 playbook, saved fold fits | 0.500325 | 0.503 | 0.250819 | 0.249 | 8.8864 | 8.877 |

The generic archived r8 duration ratio is 0.861023 versus 0.86, and its matched
failed median is exactly 119.7s. Every generic fold's raw end-reason counts match
the archive exactly, and its individual metrics match archived rounding. The old
pooled script averages already-rounded fold metrics; this explains the generic
pooled MAE discrepancy. Playbook raw counts differ by at most two battles in a
fold (one exhausted/timer classification in folds 0/1, two triples in fold 2),
with a pooled three-star difference of 0.27 percentage points and Brier difference
0.00182. Those small residuals are reported rather than rounded away or used to
retune strengths. Platform floating-point/trajectory differences remain a limit
of this historical comparison. These are the equivalent-engine/settings proofs;
the larger current-versus-archive differences above are real version differences.

The complete native refits use the same three partitions, 13-point r8 correction
grid, four fitting angles, all five skill quantiles, and monotonic cap. All six
new reports bind to their saved calibration hashes, all ancestors are identified,
and every training/test intersection is empty. An initial run correctly refused
held-out status when another stream edited `rust/src/layout/{admit,json,proof}.rs`
during fitting. The successful rerun used `/tmp/rf1-validation`, a fixed source
copy with explicit links to the same real data and ignored output directory.

| New native CV fit | P(3*) | Brier | Fair constant Brier | Destruction MAE | Joint log score | Constant joint log score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Generic | 0.5516 | 0.2562 | 0.2761 | 7.1539 | 2.0200 | 1.3962 |
| Playbook | 0.4295 | 0.3021 | 0.2761 | 9.4153 | 2.1112 | 1.3962 |

The generic fit improves Brier over the fair fold constant here, but both joint
log scores are worse than that baseline; playbook Brier is also worse. This is
measurement evidence, not a claim that the fidelity checks pass. The current
native board still reports TH-order inversions. The observed six-seed run has
curve MAE 2.294 points and observes the third-star event in only one of six runs;
missing events remain explicit.

Visible scouting also passes byte-identical 1/4/16-worker replay on all 22
defenses with two replay seeds. Its common row digest is
`1a8796a2d73aa8eb57b6f5127987fb8ddbeeae26efe6ff9204d47726b1ef504c`.

The TH18 sweep completed all 36 cells and 108 policy comparisons. It ran 21,600
planning battles, 9,000 evaluation battles and 9,000 explicitly counted diagnostic
replays. On **r18d**, each policy has 25 selected skill/replicate groups:

| Levels | CC | Random P(3*) | Visible P(3*) | Oracle P(3*) | Visible mean stars |
| --- | --- | ---: | ---: | ---: | ---: |
| TH18 max | empty | 8% | 4% | 24% | 2.04 |
| TH18 max | default | 0% | 4% | 20% | 1.96 |
| TH18 max | strong candidate | 4% | 12% | 16% | 2.08 |
| One lower | empty | 16% | 20% | 48% | 2.20 |
| One lower | default | 4% | 24% | 40% | 2.20 |
| One lower | strong candidate | 4% | 20% | 24% | 2.08 |
| TH17 caps | empty | 12% | 28% | 48% | 2.28 |
| TH17 caps | default | 8% | 28% | 40% | 2.20 |
| TH17 caps | strong candidate | 8% | 24% | 32% | 2.20 |

The current engine already three-stars r18d under the maximum-level/default-CC
condition: one visible committed attack and five oracle selections out of 25.
Thus “never three-stars” does not hold for this native scout/seed configuration.
Lower assumed levels materially increase the chance. CC changes alone have mixed
effects in this small sample, including different combat trajectories; this does
not identify the real occupants or establish that the selected strong candidate
is stronger in every matchup. The result supports testing the level assumption
with actual replay evidence, not fitting unknown levels to one user outcome.

The long TH18 run conservatively reports `inputs_changed_during_run: true`:
RF1's scoring-helper source and another stream's layout-validation sources changed
while its **fixed executable** was running. Every game-data input hash was
unchanged. The measured executable was preserved at
`/tmp/rf1-validation/fidelity-measured`, SHA-256
`b10bfc42d084c28a23d3ca8357cb663cee4557f62bce1d8fd186d836ebd325c1`;
`output/fidelity-rust/run-binding.json` lists the changed source paths. This source
provenance caveat is retained; it is not hidden by rewriting the experiment's flag.
Calibration/CV uses the stricter refusal described above.

Primary ignored artifacts are `a-{generic,playbook}-r8.json`,
`archival-{generic,playbook}-{0,1,2}-score.json`,
`archival-{generic,playbook}-pooled.json`, `cv2-{generic,playbook}-refit.json`,
the six bound reports/mappings under `cv2-refit-{generic,playbook}/`,
`determinism-{generic,visible}.json`, `observed.json`, `board-cd.json`,
`python-fresh-generic.json`, and `th18-first-experiment.json`, all under
`output/fidelity-rust/`.

## Reproduce the archival proof without editing a checkout

The following creates a separate historical source tree. `git archive` is a
read-only operation on the working repository. Links expose existing data to the
copy; only playbooks come from the historical commit. The temporary Cargo entry
compiles the RF1 helper against the historical engine API.

```sh
RF1_ROOT="$PWD"
RF1_ARCHIVE=/tmp/rf1-cv2-reproduction
RF1_TARGET=/tmp/rf1-cv2-reproduction-target
mkdir -p "$RF1_ARCHIVE"
git archive 771a2f3 rust/src rust/data rust/Cargo.toml rust/Cargo.lock data/playbooks \
  | tar -x -C "$RF1_ARCHIVE"

for source in "$RF1_ROOT"/data/*; do
  name="${source##*/}"
  if [ "$name" != playbooks ] && [ ! -e "$RF1_ARCHIVE/data/$name" ]; then
    ln -s "$source" "$RF1_ARCHIVE/data/$name"
  fi
done

cat >> "$RF1_ARCHIVE/rust/Cargo.toml" <<EOF

[[bin]]
name = "archive-export"
path = "$RF1_ROOT/rust/src/fidelity/archive_export.rs"
EOF
CARGO_TARGET_DIR="$RF1_TARGET" cargo build \
  --manifest-path "$RF1_ARCHIVE/rust/Cargo.toml" \
  --offline --release --bin archive-export

$F export-jobs --archive-cv2 --attacker generic --seeds 5 --angles 8 \
  --calibration data/meta-calibration-r8.json \
  --out output/fidelity-rust/reproduced-prepared.json
"$RF1_TARGET/release/archive-export" --run \
  output/fidelity-rust/reproduced-prepared.json \
  output/fidelity-rust/reproduced-outcomes.json \
  "$RF1_ROOT/rust/data/catalog.json" 4
$F score-jobs output/fidelity-rust/reproduced-prepared.json \
  output/fidelity-rust/reproduced-outcomes.json \
  --out output/fidelity-rust/reproduced-score.json
```

For a saved fold, select `output/overnight/cv2/generic-N.json` during export and
pass `--train-log output/overnight/cv2/train-N.jsonl` during scoring. For playbook
proofs, export strengths with the selected playbook calibration using generic
plans, then rebuild those plans with the historical compiler/books:

```sh
"$RF1_TARGET/release/archive-export" "$RF1_ARCHIVE" \
  "$RF1_ROOT/rust/data/catalog.json" \
  output/fidelity-rust/reproduced-prepared.json \
  output/fidelity-rust/reproduced-playbook-prepared.json playbook
```

Run and score that resulting file as above, passing `--attacker playbook` to
scoring. Remove `--archive-cv2` from the initial strengths export in this case;
the historical compiler owns the plan wire. The helper's comments and five
explicit arguments keep the archival configuration separate from ordinary
production replay.
