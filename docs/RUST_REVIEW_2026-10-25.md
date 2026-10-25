# Rust engine review and enhancement research (2026-10-25)

Scope: the Rust engine at `d774e17` (F14), now that Python is frozen and new
work is Rust-only. Part 1 reviews what is there. Part 2 is research on making
the battles match the game, modelling how humans attack, and searching for the
best bases and armies. Part 3 is a prioritized Rust-only plan.

Everything measured here was run from a clean checkout on a 4-core Linux
container. One input had to be faked (see R1), so outcome numbers are
indicative, not calibration.

## What was run

| Check | Result |
|---|---|
| `cargo build --release` | 2 min 56 s, zero warnings |
| `guardian-check` | 50/50 synthetic fixtures pass |
| `armysearch-proof` | **fails on a clean checkout** (R1) |
| `compile custom:user-rr-oct25`, 8 angles, playbooks on | ok, after a placeholder `Clan_Castle.json` |
| `jobs`: user's RR army vs the 4 real TH18 bases, 8 sides x 5 seeds | 160 battles: 5.1/s on 1 thread, 19.0/s on 4 |
| Same 160 jobs, 1 thread vs 4 threads | identical results |

That is ~200 ms per battle per thread, against ~3.8 s for the Python engine
and ~200 s for the legacy v29 engine. RUST_PORT.md reports ~9/s per thread on
the 7800X3D. Speed is no longer the bottleneck. Fidelity and search design are.

Outcomes against the user's real TH18 results (no modifier, base levels and
CC assumed per each layout's notes, placeholder donated-siege caps):

| Base | Real | Sim mean stars | Sim 0/1/2/3 stars | Sim TH down | Army wiped out | Best side / worst side |
|---|---|---:|---|---:|---:|---|
| r18a | 1★ 61% | 1.10 | 12/12/16/0 | 40% | 95% | 2.0 / 0.0 |
| r18b | 2★ | 0.88 | 10/25/5/0 | 12% | 95% | 1.2 / 0.0 |
| r18c | 2★ | 0.90 | 8/28/4/0 | 32% | 75% | 1.4 / 0.4 |
| r18d | 3★ | 0.95 | 12/18/10/0 | 25% | 92% | 1.6 / 0.0 |

Correction: the "8 sides" are 8 uneven directions. The angles were passed as
0, 45, ... 315 radians (0°, 48°, 58°, 117°, 175°, 233°, 292°, 350°); see
SIMULATION_METHODS_RESEARCH.md, which also shows most of this gap is side
choice. The sim is about one star weaker than the user on every base and never
three-stars in 160 tries. Attacks end because the army is spent (median end
~115-145 s), not on time. Side choice swings mean stars by up to 2.0, so how
the attacker picks a side matters as much as most mechanics.

## Part 1: review findings (ranked by impact)

**R1. A clean checkout cannot run a Rust attack.** `Compiler::new` reads
`data/wiki/tables/Clan_Castle.json` (`rust/src/compile.rs:88`), but `data/wiki/`
is gitignored. Every path that compiles an army fails on it: `compile`,
`armysearch`, `armysearch-proof`, `score` with plans. Rust also references
`output/bases/target17-winner.json` and `target18-winner.json`, which are
gitignored too. Commit messages report "armysearch-proof passed", but that was
only on the machine with the mirror. Also `siege_cap` (`compile.rs:1672`)
returns 0 when the table or a row is missing (`unwrap_or(0.0)`), so a
new siege silently gets level 0 instead of failing.
Fix: commit the one derived table into `rust/data/` (or fold it into
`catalog.json`), make a missing row an error, and add a CI job that builds
Rust and runs the proofs.

**R2. The docs still say Python is the reference.** RUST_PORT.md requires
bit-exact parity with Python, and MOVE_LIBRARY_DESIGN.md milestones M2-M3
require "Python reference and Rust runtime" and "Python/Rust trace parity".
F14 froze Python. ENGINE_STATUS.md still describes the legacy v29 engine
(four-neighbour routing, continuous events). The Rust engine actually uses
half-tile, 8-neighbour lazy Dijkstra fields (`grid.rs:7-23`) at a 0.1 s tick.
Decision needed: Rust is the reference. Replace parity with a golden corpus of
Rust traces and outcomes, regenerated on purpose and diffed by `trace_diff`.
This also lifts the CPython-exactness rules (`py_hypot`, `py_pow`, ucrtbase
trig, Python operation order). They already hold only on Windows: off Windows,
`py_exp` falls back to Rust's `exp` (`scoring.rs:122`). Dropping them unblocks
the goal-directed path search RUST_PORT.md left undone (~15-20% of a battle).

**R3. Base search is stranded in frozen Python.** Rust has battle setup,
the scorer and army search. Layout generation (`archetypes.py`), moves
(`macro_moves.py`, `_rewire`, `guided_move`), drop-hole detection
(`deploy.py`), quality-diversity and evolution (`qd_search.py`,
`evolve_bases.py`, `funnel.py`), trap polishing and the objective
(`optimize.py`, `evaluate.py`) are all Python. With Python frozen, the base
half of the goal can no longer get fixes. Porting the layout model, legality,
deploy zones, moves and the QD archive is the largest Rust gap.

**R4. The game's own AI parameters are unused.** `data/gamecsv/v18.200.9/globals.csv`
ships the targeting and pathing constants, and neither engine reads any of them:

| Constant | Value | What it likely governs |
|---|---:|---|
| `TARGET_LIST_SIZE` / `MAX_TARGET_LIST_SIZE` | 3 / 6 | candidate targets considered per retarget |
| `EXTRA_TARGET_PATH_COST_PENALTY` | 5 | penalty when ranking those candidates by path |
| `WALL_COST_BASE` | 1000 | wall cost in path planning (engine uses a hand-set 12 tiles, `grid.rs:11`) |
| `FORGET_TARGET_TIME` | 6000 ms | when an unreachable target is dropped |
| `REMEMBER_ORIGINAL_TARGET` | TRUE | return to the original target after a forced detour |
| `FORCE_NEW_TARGET_DEFAULT/JUMP/TESLA_MAX_NOISE` | 800 / 100 / 400 | randomness added on forced retargets |
| `RETARGET_AFTER_DESTROYING_WALL` | FALSE | breaking a wall does not trigger a retarget |
| `SELECTED_WALL_TIME` | 4000 ms | how long a chosen wall stays chosen |
| `STICK_TO_TARGETED_BUILDING_WHEN_FORCING_RETARGET` | TRUE | target stickiness |
| `WARDEN_WAITS_FOR_GROUP_RETARGETING` | TRUE | Warden follow behaviour |

These are what funnels, compartments and wall bait exploit. The engine's
"cheapest path to any eligible building with a fixed wall cost" is a different
rule. The meanings above are inferred from the names. Each needs a controlled
friendly-challenge test before it is trusted (Part 2). The unit scale is known
from fields the engine already cites (`Apprentice Warden.TargetGroupsRange=1300`
-> 13 tiles, so 100 units = 1 tile). If path costs share that scale,
`WALL_COST_BASE` is about 10 tiles against the engine's 12.

**R5. Scouting still uses hindsight.** `scoring::scouted`
(`rust/src/scoring.rs:1145`) runs every candidate side to completion and keeps
the outcome that was best for the attacker. The attacker therefore "knows"
hidden traps, Teslas and CC contents. That overvalues bases that are weak from
only one side and undervalues surprise. The 2-side vs 3-side swing in
ENGINE_V2.md (6.8 vs 1.6 trophies) shows how strongly the score depends on
this rule.

**R6. Skill is still stat scaling.** `scoring::skill` (`scoring.rs:127`)
multiplies attacker HP and damage by `exp(0.15 z)` over five quantiles, and
decisions stay identical. Real skill is timing, placement and mistakes, so a
base that causes human errors and a base that resists stronger stats look the
same.

**R7. Army search scope.** `armysearch/eval.rs:126` builds every scenario
with `modifier: None`, so Legend I is never searched. `account.rs:61` rejects
anything but the TH16 account. Both are noted in MOVE_LIBRARY_DESIGN.md. They
must be fixed before searching TH17/18 or ranked-modifier armies.

**R8. Personal data in Git.** `data/live/battles.jsonl`,
`data/live/player-latest.json`, `data/your-levels.json` and the
`data/reference-bases/real-*.png` screenshots are tracked. AGENTS.md says real
profiles stay out of Git. The repository is private, but this should be a
deliberate choice. The alternative is to load them from a gitignored
`private/` path.

**R9. Smaller items.**
- Unsupported equipment and pets `panic!` (`heroes.rs:519, 606, 1771, 2164`,
  `setup.rs:132`) instead of returning `Err`. The runner unwinds, but a search
  that proposes an unsupported item should get a typed rejection, not a crash
  log.
- GAP_ANALYSIS.md still lists 27 Rust `todo!` paths, but there are none now.
  Refresh it so it doesn't misdirect work.

## Part 2: research

The repo already holds better primary sources than the open web: game CSVs,
a 2,700-line wiki digest, cited playbooks, video measurements and the user's
battle log. Web searches for CoC internals (tick rate, pathing cost) return
only SEO pages, so the recommendations below lean on those local sources plus
established methods from the literature.

### 2.1 Make the battle match the game

1. **Targeting and pathing from game constants (R4).** Port the target-list
   model: on retarget, take the `TARGET_LIST_SIZE` nearest eligible buildings,
   rank them by path cost with walls at `WALL_COST_BASE` plus the extra-target
   penalty, and keep the target with the forget/remember rules and forced-
   retarget noise. Make the unit conversion (internal units per tile) an
   explicit parameter. Validate each rule with a two-to-three-building
   friendly challenge (one Giant or Valkyrie, a walled vs open compartment,
   recorded at 60 fps). VIDEO_SHOTLIST.md already has the protocol.
2. **Crowding and collision.** `Battle::separate` (`rust/src/movement.rs:12`)
   pushes overlapping attackers apart by a quarter of the overlap per tick. The
   radius is 0.35 tiles for flyers (measured) and 0.35 + 0.015 x housing for
   ground (assumed). Defending troops get no separation. Clumping sets splash,
   Scattershot, poison and Healer value, which decide ground-smash outcomes.
   Measure the ground radius and the per-tick push from footage of a mass deploy.
3. **Warden grouping.** GAP_ANALYSIS 4 found the Warden voting by current
   target within 13 tiles. The game data names spatial groups
   (`TargetGroupsRadius=500`, `TargetGroupsMinWeight=2000`,
   `WARDEN_WAITS_FOR_GROUP_RETARGETING`). Port that grouping.
4. **Hidden information.** Unrevealed Teslas and traps should not be in the
   attacker's plan logic or navigation until revealed (GAP_ANALYSIS 4).
5. **Spend measurement effort where it changes rankings.** ENGINE_V2.md lists
   roughly 40 `assumed` constants. With Rust at ~20 battles/s here (~90/s on 16
   threads), a Morris elementary-effects screen is cheap. 40 constants x 10
   trajectories = 410 configurations; x 200 battles each = 82k battles,
   ~15 min on 16 threads. Rank constants by their effect on *base ordering*,
   not on mean stars, and measure only the top few from video. Follow up on
   the survivors with Sobol indices.
6. **Calibrate distributions, not one rate.** Ranked trophies depend on how
   attacks fail (1★ vs 2★, 65% vs 98%). Fit to the joint star x destruction
   distribution by attacker TH and army, using simulation-based inference
   (approximate Bayesian computation or history matching) over the few free
   parameters, rather than one strength multiplier per army. Score with Brier
   and destruction MAE on out-of-fold real defenses, as SIM_ACCURACY.md
   already requires.

### 2.2 Model how humans attack

The project already has the right building blocks: cited playbooks, measured
deploy cadence (0.133 s per held drop), phase gaps from source videos, and
the move-library/HumanController design. What the research adds:

- **Scout from visible state, then commit (fixes R5).** A human picks a side
  from what is visible: the funnel cost, exposed defenses, TH distance and
  CC position. Implement a cheap side-scoring heuristic, or a learned one
  trained on sim outcomes averaged over a *hidden-state ensemble*: trap
  positions and CC contents sampled from plausible priors. Choose before
  running, then run once on the real hidden state. Keep "best of k completed
  battles" only as an upper bound, labelled as such.
- **Skill as execution, not stats (fixes R6).** Sample a persistent per-battle
  profile: reaction delay (sweep 0.2-0.6 s), placement error (0.25-1 tile,
  correlated within a battle), slot-switch time, and a small probability of
  a missed or late key action (Freeze, Rage, ability). Fit the profile
  population so the sim matches the real star/destruction distribution. These
  ranges are the design doc's sensitivity bounds, not measurements. Only the
  0.133 s deploy cadence is measured.
- **Reactive decisions.** The biggest human advantage in failed sim attacks is
  recovery: repairing a failed funnel, timing Freeze on the defense that is
  actually killing the charge, and switching cleanup on the clock. The move
  library's live preconditions and failure branches are the right vehicle.
  Prioritize "funnel failed", "charge dying" and "TH not reachable by 120 s".
- **Two separate attacker products.** (a) An *ordinary human* population,
  calibrated, used to score ranked defenses by expected trophies. (b) A
  *strongest feasible* attacker, searched per base under the same human
  limits, used as a robustness gate and for war bases. Never mix their
  numbers.

### 2.3 Find the best bases and armies

Treat this as a two-player game. The defender commits a base and the attacker
best-responds after scouting.

- **Ranked base = expectation vs a population.** Maximize expected defender
  trophies against the meta-weighted ordinary-human population. The Rust
  scorer already takes the attacker-TH mix from the battle log, plus one
  pseudo-count per TH (`scoring.rs:961`). The 65/35 TH18/TH17 default applies
  only when the log is missing.
- **War base = worst case vs a planned attack.** Minimize 3★ probability
  against the best feasible attacks: a minimax or CVaR objective over an
  attack archive.
- **Avoid cycling with an archive (double oracle / PSRO).** Keep a growing
  archive of attacks. Score each candidate base against the archive. Every
  few generations, search a best-response attack against the current top
  bases and add it to the archive. Evaluate the final populations with
  Nash averaging so rankings don't depend on which opponents happened to be
  included. Refs: McMahan, Gordon & Blum (2003) double oracle; Lanctot et al.
  (2017) PSRO, arXiv:1711.00832; Balduzzi et al. (2018) "Re-evaluating
  Evaluation", arXiv:1806.02643; Rosin & Belew (1997) hall of fame for
  competitive coevolution.
- **Quality-diversity for bases (port `qd_search.py`).** MAP-Elites (Mouret &
  Clune 2015, arXiv:1504.04909) or CMA-ME (Fontaine et al. 2020,
  arXiv:1912.02400). Use descriptors a human would recognize: TH offset from
  centre, number of compartments, air-defence spread, and core density. A
  diverse archive also gives the attacker archive varied targets.
- **Budget the noise.** Existing numbers: 300-700 paired battles to detect
  +0.05 in attacker policy, and base rank agreement 0.79 at 68 battles.
  Use common random numbers (same seeds and sides for every candidate), then
  successive halving or Hyperband (Li et al. 2017, arXiv:1603.06560). Screen
  with 20 battles, promote the top third to 68, then the top few to 400+, and
  report paired confidence intervals.
- **Surrogate as a filter, not a judge.** At ~90 battles/s, a surrogate is
  worth it only for move pre-screening inside annealing. A grid CNN over
  building-type channels, trained on the logged evaluations, can propose
  moves, keeping an exploration quota. Final rankings always come from
  simulation.
- **Army search.** Search army + adaptation budget, not an army tuned per
  base without limit (MOVE_LIBRARY_DESIGN.md §3). Use CMA-ES (Hansen 2016,
  arXiv:1604.00772) for continuous plan knobs: angle offsets, timings,
  spell offsets. Use the existing MAP-Elites over composition, scored on
  held-out bases.

Indicative budget at 90 battles/s (16 threads):

| Stage | Battles | Time |
|---|---:|---:|
| Base QD, 2,000 candidates x 20 screening battles | 40k | 7 min |
| Promote 200 x 68 | 14k | 3 min |
| Best-response attack search vs top 10 bases (4,420 each) | 44k | 8 min |
| Re-score 30 finalists x 400 vs the grown archive | 12k | 2 min |
| One double-oracle round | ~110k | ~20 min |

So 10-20 rounds fit in an overnight run.

## Part 3: Rust-only plan

1. **Clean-checkout Rust** (R1). Commit the siege-cap table, make missing rows
   errors, and add `cargo build --release`, `guardian-check`,
   `armysearch-proof` and a small `jobs` golden run to CI. *Hours.*
2. **Make Rust the reference** (R2). Write a golden trace corpus, update
   RUST_PORT.md, ENGINE_STATUS.md, MOVE_LIBRARY_DESIGN.md and GAP_ANALYSIS.md,
   and stop adding exactness shims. *A day.*
3. **Scoring realism** (R5, R6, R7). Visible-state scouting over hidden-state
   ensembles, an execution-noise profile replacing stat skill, modifier
   propagation in army search and TH17/18 accounts. *Days.*
4. **Port base search** (R3). Layout model, legality, deploy holes, moves,
   QD archive and the double-oracle loop with racing. *1-2 weeks.*
5. **Targeting from game constants** (R4) plus crowding and Warden groups,
   each behind a flag. Use the Morris screen to choose which friendly-
   challenge measurements to record first. *1-2 weeks, plus measurement.*
6. **Real loop.** Put finalists in the war/ranked slots and compare predicted
   vs real defense distributions weekly. The 4 TH18 replays here are
   development data now. Keep later ones held out.
