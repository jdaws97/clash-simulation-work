# Fidelity results log

Dated, comparable results of the native fidelity checks. Newest first. Each
entry names the engine commit, data, and settings, so later entries can be
compared on the same footing. Raw outputs live in ignored `local/`.

## 2026-10-26 — MF public meta refit (f3e0916)

**CONFIRMED method.** Native `clash fidelity meta-fit` replaces the frozen
`calibrate_meta.py` workflow. Every r8 `real` target comes from the matching
build's `three_star` in the pinned 2026-10-15 TrophyCoach snapshot: same-TH,
ranked battles, last 30 days at collection. This run uses the current engine
at `f3e0916a5309b75df2f866e85b43bdb86d66b168` plus the MF adapter (hashes in
r9), eight angles with 0.21-radian offset, full visible scouting with three
hidden samples, playbooks, no league modifier, two replicates of every one
of the five skill quantiles, 32 requested workers, and fixed common random
numbers across strengths (100 committed outcomes per TH16 build/strength;
40 per TH18 build/strength).
`BASELAB_PARAMS_FILE`, `BASELAB_FLYER_RANGE`, `BASELAB_PACE` and `BASELAB_GAPS`
were unset: engine/catalog defaults, compiler pace 1.0 and pinned gaps enabled.
The search uses a five-point log grid on [0.4, 2.5], six log-bisection
refinements and a fresh evaluation at the selected strength. Raw curves,
isotonic projections, reversals, target errors and clamps are retained.

The public TH16 prior uses only the ten pinned human ranked layouts in
`ranked-2026-10-24`, equally weighted, with their existing levels and hidden
defense hypotheses. These files already contain historical user-level
assumptions; no new private account or defense data enters this fit. The ranked
pool has five empty defending-hero rosters (rb01/05/06/08/10), plus the
documented inferred hidden defenses; these are transcription assumptions,
not confirmed empty real-game defenses. All are retained without inventing
new source values. The old own-layout pool is excluded because including the
layout defended in CV would leak held-out layout information into its prior.
TH17/18 borrow the
arithmetic mean of same-archetype TH16 builds, or 1.0 when absent, and remain
uncalibrated. A separate fit of the 13 TH18 targets on the four ranked TH18
transcriptions is **sensitivity only**; it never contributes to r9 or CV.
At `python-frozen`, the fitter's top-level `reference-bases/*.json` glob
would select the two own-base files and overlay the account's levels; the
nested ranked collections would not enter that glob. Thus r8's CV comparison
holds out defense outcomes, but its historical prior already saw the base
layout; it is not a layout-held-out comparator.

**Evaluation protocol.** r8 and r9 use the same stable-ID three folds, 20
evaluation seeds, 32 requested workers, playbook attacker, eight full visible scouting candidates,
and training-only constant baselines. Each fold refits its own defense
corrections from its selected public prior (one replicate of five skill
quantiles, four full visible sides, nine correction-grid points). Only these
CV runs enable the existing read-only private archive. TH18 and Maroon replay
checks use public mode and the public TH16-cap account; TH18 uses five
replicates of five quantiles, TH18-max defenders, eight visible sides and the
saved default CC. This account setting differs from the earlier historical
user-inventory experiment, so compare the paired runs below with each other.
All derived reports are under `local/fidelity/mf/`; commands are documented in
[FIDELITY_RUST.md](FIDELITY_RUST.md).

**Result: r9 is rejected; r8 stays the default.** Paired 20-seed CV on the
same folds, and the TH18 check in public mode:

| Prior | CV sim 3★ (real 68.2%) | Brier | Destruction MAE | Joint log | Star RPS | TH18 visible mean stars (real 1/2/2/3) |
|---|---:|---:|---:|---:|---:|---|
| r8 | 55.9% | 0.222 | 7.22 | 2.37 | 0.134 | 1.92 / 1.96 / 2.16 / 1.84 |
| r9 | 50.7% | 0.288 | 8.81 | 2.26 | 0.146 | 1.36 / 1.36 / 1.80 / 1.72 |
| constant | — | 0.219 | 8.17 | 1.36 | 0.102 | — |

r9 lowers most strengths (Dragons 0.83 to 0.69, Root Rider 1.20 to 0.98), and
the recorded human Dragon attack replays at 0.69, further from its real clear.
The likely cause is the fitting pool: five of the ten ranked TH16 layouts have
no defending heroes in their transcriptions, so they are easier than real
Legend bases and every fitted strength comes out low. Refit only after those
rosters are filled in from the source screenshots. The TH18 r8 numbers here
use the public TH16-cap account and are higher than the user-account run
(1.44 / 1.60 / 1.88 / 1.44); compare only within a column.

**r10 (refit after the roster correction, c4827ea).** Filling the five empty
rosters with the modal ranked roster moves the fitted strengths back toward
r8 (Dragons 0.78, Root Rider 1.05 / 1.15, Thrower 1.00 / 1.26), which supports
the pool explanation for r9. On the same CV r10 is still worse than r8: sim 3★
51.6%, Brier 0.283, MAE 9.02, joint log 2.50, RPS 0.152; TH18 visible means
1.76 / 1.48 / 2.28 / 1.52. This comparison is biased toward r8: r8 was fitted on
a pool that contained the user's own layout, the layout behind all 22 CV
defenses, while r9/r10 never saw it. A fair verdict needs new held-out
observations (defenses of a new layout, or friendly-challenge results). r8
stays the default; r10 is pinned as a public prior for those future checks.

## 2026-10-26 — attacker gap investigation (d986b4f)

**Data.** 22 held-out real defenses of the user's base (private battle log,
3-fold CV, r8 prior, playbook attacker, visible scouting). The set of 22
battles differs from the one behind the b255970 numbers (the log moved on), so
those older numbers are not comparable. Four TH18 reference attacks
(r18a-d, real 1/2/2/3 stars). 324 timing-usable public video attacks.

**Held-out CV, 20 evaluation seeds** (`clash fidelity cv --seeds 20`):

| Scouting | Sim 3★ (real 68.2%) | Brier | Destruction MAE | Joint log score | Star RPS |
|---|---:|---:|---:|---:|---:|
| Best-of-two mixture (old default) | 51.8% | 0.240 | 8.25 | 1.77 | 0.134 |
| Best visible side of all candidates (new default) | 55.9% | 0.222 | 7.22 | 2.37 | 0.134 |
| Constant predictor (training folds) | — | 0.219 | 8.17 | 1.36 | 0.102 |

Full visible scouting is now the fidelity default (`--scout` defaults to
`--angles`), matching the TH18 and tempo checks. It improves Brier and
destruction error but sharpens the predictions, so the joint log score gets
worse. With five evaluation seeds the same change looked much better
(Brier 0.182, MAE 5.17); each prediction then rested on five battles, and the
20-seed run shows most of that gain was noise. The simulator is still no better
than the constant predictor on Brier, log score and RPS.

**TH18 replays** (`clash fidelity th18`, full visible scouting, TH18 max,
default CC): mean stars 1.44 / 1.60 / 1.88 / 1.44 against real 1 / 2 / 2 / 3.

**Diagnosis D4** (`local/evidence/fidelity/diag/d4/report.md`). Failed sim
attacks end because the army dies (exhausted offense, median 120 s vs real
173 s) with about 17 buildings standing; it is not an early-stop artifact,
and extending the clock adds no 3-stars. Largest one-factor sensitivities
on 3-star rate: removing attacker re-target waits (+14 to +25 points),
removing defending-hero damage (+12), skill at the top quantile (+25), full
scouting (+11), defenses one level lower (+7). Slower pacing and delaying
spells or abilities make things worse.

**Re-target timing research R1**
(`local/research/mechanics/r1-retarget-timing-2026-10-26.md`). Patch notes
confirm unit-specific first-attack and new-target delays; a gameplay guide
gives the Electro Dragon about 3.5 s to charge after arriving, matching the
engine. The evidence does not support removing the engine's re-target wait,
so no mechanics change was made.

**Video tempo VT** ([VIDEO_TEMPO.md](VIDEO_TEMPO.md)). Against TH16-estimate
videos the TH16 sim is 17 points further ahead at 60 s (90% interval 6.5 to
28), finishes its last deployment 42 s earlier (56.7 s vs 98.8 s), and
three-stars far less. Video three-star shares are selection-biased; the tempo
shape is the more robust signal: humans keep acting past 90 s, the sim
front-loads its whole army and then runs out.

**Strength calibration (r8) check.** r8 scales each meta army's troop HP and
damage between 0.83 (Dragons) and 1.20 (Root Rider, Thrower), fitted by the
old Python tool on an older engine. Raw strength (1.0 for every army) makes the
20-seed CV worse overall (3★ 42.7%, Brier 0.244, MAE 8.49) and lowers the TH18
replays (visible mean stars 1.12 / 1.44 / 1.36 / 1.44). But diagnosis D5
(`local/evidence/fidelity/diag/d5/report.md`) replays the user's one recorded
Dragon attack with its exact actions: it clears in 1 of 6 runs at r8 and 5 of 6
at strength 1.0, with an accurate destruction curve in both. The factors are
stale and family-specific rather than uniformly wrong; they need a refit on
the current engine against the same public targets (porting `calibrate_meta`).
D5 also found the Dragon playbook forced into a hero-first two-flank opening
when the army's equipment can't support it (Dragons enter at about 32 s; the
recorded human dropped them at 0.1 s), but removing inferred waits alone
lowers clears 36% to 28%, so no global speed-up was made.
