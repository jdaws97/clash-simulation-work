# Fidelity results log

Dated, comparable results of the native fidelity checks. Newest first. Each
entry names the engine commit, data, and settings, so later entries can be
compared on the same footing. Raw outputs live in ignored `local/`.

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
