# Red team: the best cited attack on one base

`src/baselab/redteam.py` searches the choices a player makes when they read a base, but only inside the army's cited playbook (`data/playbooks/<family>.json`). It adds no new actions or troop uses. A base search scored against the fixed script finds bases that only beat the script. The red team is the attacker such a search should face.

## What is searched

| Choice | Values | Source |
|---|---|---|
| Entry side | 16 sides, then ±11.25° around the best | every playbook ("choose the entry") |
| Charge flank | left / right | `edge:charge` / `edge:funnel` in the playbooks |
| Flank offset | 0.6 / 0.9 / 1.2 rad | super-bowler base reading: "adjust lane spacing to the funnel width" |
| Step targets | a step that targets `building:<key>`, `th` or `threat:main` may target any building that some playbook step with the same action and unit or spell targets (Rocket Balloons: at, mortar, ad, bt, xbow; Earthquake: cc, mono, st, inferno, ...) | the playbooks' own steps and variants |
| Ability aim | Giant Arrow: ad, sweeper, cc, revenge, mono, st. Fireball: cc and the heavy defenses | steps plus base-reading rules (`READING`, each one checked against the playbook JSON when it loads) |
| Timing | wait before the main push: 0.5x, 1x or 1.5x the measured median gap. Invisibility cadence of 4 or 10 s, but only for a hero with a Spirit Fox | `data/playbook-gaps.json`; both cadences are cited |

Each choice reaches the executor as a per-step override (`engine/playbook.py: apply_overrides`, fields `at`, `aim`, `every`, `delay`). With no overrides, the plans are unchanged.

## Search and budget (`Budget`)

1. Coarse: 32 configurations (16 sides x 2 flanks) on 5 seeds. All candidates share the same seeds (common random numbers), and seed % 5 picks the skill quantile, so each block of 5 seeds covers all five skills once.
2. Successive halving: the best 8 get 10 seeds, then the best 3 get 20.
3. Refinement: one coordinate-descent pass from the best configuration. Each single change is screened on 5 seeds. A change that passes the screen is replayed on all 20 search seeds and kept only if it gains more than 0.5 trophies there. Refinement is skipped when the coarse winner already three-stars every search seed.
4. Fresh replay: the pick is replayed on 10 unseen seeds (20 in the check below). That fresh number is what gets reported and scored, so it carries no winner's-curse optimism.

Total cost: 230 battles for stages 1–2. Stage 3 adds 0–270, capped by `max_battles` = 500. The fresh replay adds 10. On this shared machine with 6 workers, one army on one base took 90–500 s (230–480 search battles; about 1 s per battle in wall time).

## Use

- `redteam(layout, army)` returns a `RedTeamResult` with the attack, its search score, its fresh score and the per-side coarse scores.
- `evaluate_redteam(layout, [(army, weight)])` returns `(Evaluation, results)`. A base search can call it directly.
- `BASELAB_REDTEAM=1` switches `evaluate.evaluate()` to red-team mode. Every scenario army that has a cited playbook is replaced by its red-team attack, with the army's total weight spread over the fresh battles. Armies without a playbook are evaluated as before. Hero-charge techniques and tuned tactics for playbook armies are absorbed. `BASELAB_REDTEAM_BATTLES` changes the cap. This mode costs several hundred battles per army per base, so for a meta mix use a few representative builds.

## Validation (2026-10-20, `tools/baselab/redteam_check.py`)

Setup: the user's levels, r7 calibration, `BASELAB_PLAYBOOKS=1`. The baseline is the current scouting of `playbook_check.py`: 8 sides x 2 flanks, picked on 4 seeds. Both picks are replayed on the same 20 fresh seeds. All numbers are expected attacker trophies.

| Base | Army | Scouting: in-sample → fresh (3★) | Red team: search → fresh (3★, %) | Red-team entry |
|---|---|---|---|---|
| ranked-funnel1 | user-rr | 37.0 → 35.8 (65%) | 38.7 → **36.2** (65%, 96.9%) | 219.5°, left |
| ranked-funnel1 | user-druid-ruin | 27.2 → 23.8 (5%) | 28.9 → **29.1** (25%, 84.2%) | 253.2°, left; Quake 2 on the Monolith |
| ranked-funnel1 | mass-dragons-17-1 | 40.0 → 40.0 (100%) | 40.0 → **40.0** (100%) | 5.7°, left |
| ranked-holefree | user-rr | 40.0 → 39.4 (95%) | 38.6 → **39.4** (95%, 99.2%) | 230.7°, right |
| ranked-holefree | user-druid-ruin | 37.2 → 25.6 (25%) | 28.1 → **25.5** (25%, 92.3%) | 5.7°, right; Freeze on an Inferno |
| ranked-holefree | mass-dragons-17-1 | 37.5 → 36.9 (70%) | 39.0 → **38.5** (85%, 98.8%) | 28.2°, left |

Against the three goals:

- (a) At least as good as scouting: met within noise. The red team is equal or better in 5 of 6 cases and 0.1 below in one; the gains are +5.3 (druid, funnel1) and +1.6 (dragons, hole-free). Scouting's in-sample numbers overstate it by up to 11.6 trophies (druid on hole-free: 37.2 in-sample, 25.6 fresh). The red team's search numbers sit within 3 trophies of its fresh ones.
- (b) Hole-free weaker than funnel1 for the user's armies: Root Riders yes (39.4 vs 36.2 trophies, 95% vs 65% 3★). Druids no: once the red team plays funnel1 well (29.1), funnel1 looks weaker than hole-free (25.5), although hole-free still concedes more destruction (92% vs 84%). Scouting alone had the druid ordering right (25.6 vs 23.8), but only because it played funnel1 badly.
- (c) Entry near the Eagle (about 128° from the centre): not reproduced. The picks sit 90–145° away from it. On the 5-seed coarse scan of hole-free, the Eagle-side entries (118° and 141°) give Root Riders 33/33 against 40 at 231–253°, and Druids 27/28 against 31 at 343°. On funnel1 the same Eagle-side entries are among Root Riders' best (36/38). The sim does not yet see the hole-free Eagle side as the weak point the user found.

Caveats: with 20 fresh seeds, the standard error is about 1–2 trophies, so differences under about 2 are noise. The fresh-seed scores of all 32 coarse configurations are not measured, so the red team is a lower bound on the best cited attack. Coordinate descent makes one pass and does not search combinations of changes.
