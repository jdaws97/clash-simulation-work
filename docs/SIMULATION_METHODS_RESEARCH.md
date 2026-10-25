# How to simulate Clash of Clans as exactly as possible: methods and experiments (2026-10-25)

Question: what would a "perfect" Clash of Clans simulator take, which ways of
building one exist, and where does effort pay off? Part 1 is experiments run on
the Rust engine (`d774e17`). Part 2 is what the game itself and outside
projects reveal. Part 3 compares the candidate methods. Part 4 lists what to
do next.

## Part 1: experiments on the Rust engine

Setup: the user's Root Rider army (`custom:user-rr-oct25`, account levels,
playbooks on) against the four real TH18 bases (`ranked-th18-2026-10-25`).
Each run is 4 bases x 8 approach angles x 5 seeds = 160 battles. About 3,400
battles were run in all, at ~19 battles/s on 4 threads. The angles were passed
as 0, 45, ... 315 *radians*, which gives 8 unevenly spaced directions (0°, 48°,
58°, 117°, 175°, 233°, 292°, 350°). Every comparison below uses the same 8
directions, so the comparisons stand, but these are not evenly spaced sides.
`data/wiki/tables/Clan_Castle.json` was a local placeholder, because the
directory is gitignored (see RUST_REVIEW R1). It affects only the level of
donated sieges.

Two settings needed code hooks. These live in a scratch copy only. With
defaults, that copy gave results identical to `main`, battle for battle.
- `EXP_WALL_COST`: the wall detour cost in tiles, which replaces
  `NORMAL_WALL_EXTRA` (12).
- `EXP_JITTER_SCALE`: multiplies the `jitter` argument of `drop_fixed_at`.

Tick and pace were changed through `setup.env` in a catalog copy.

### 1a. Which modelling choices move outcomes

"Same ★" is the share of the 160 battles whose star count matches the
baseline.

| Variant | Mean ★ | TH down | Same ★ | Mean \|Δ destruction\| |
|---|---:|---:|---:|---:|
| Baseline (0.1 s tick, wall cost 12) | 0.96 | 28% | 100% | 0 |
| Different seeds only | 0.92 | 29% | 59% | 6.4 |
| Tick 0.05 s | 0.91 | 26% | 58% | 5.6 |
| Tick 0.025 s | 0.96 | 34% | 57% | 6.4 |
| Wall cost 6 / 10 / 18 tiles | 0.94 / 0.97 / 0.99 | 29-34% | 80-88% | 2.0-3.5 |
| Human pace x0.8 (faster) / x1.25 (slower) | 0.97 / 0.86 | 31% / 23% | 61-66% | 5.7-6.0 |
| Defense wind-ups off | **1.19** | 41% | 56% | 8.8 |

The standard error of a 160-battle mean is about 0.06★.
- **Tick length:** a finer tick changes individual battles as much as a new
  seed does, but leaves averages unchanged. 0.1 s is converged for
  distributions.
- **Wall cost:** the averages barely move, even with the cost halved or
  raised by half.
- **Wind-ups:** turning them off adds +0.23★ (about 4 SE), the largest
  effect here. Wind-up and first-hit timing deserve measurement before
  wall cost does.
- **Pace:** a 25% slower attacker loses about 0.1★.
- **Ranking these four bases:** the order changes under almost every variant
  (adcb, dacb, acdb, cadb). 40 battles per base cannot rank bases whose means
  sit within 0.2★ of each other.

### 1b. The engine is chaotic

The seed mostly sets deployment jitter (`plans.rs:1027`: ±0.3 tiles for heroes
and lines) plus a few death-spawn draws. Shrinking the jitter and comparing two
seeds:

| Jitter scale | Same ★ across two seeds | Mean \|Δ destruction\| |
|---|---:|---:|
| 1 (±0.3 tiles) | 59% | 6.4 |
| 0.1 (±0.03) | 68% | 5.4 |
| 0.001 (±0.0003) | 72% | 4.3 |
| 0 (only death-spawn randomness left) | 91% | 1.0 |

Placement differences thousands of times smaller than a tile still change the
star count in 28% of battles. Small differences grow through target choice,
splash and trap triggers. The real game is likely sensitive in the same way.
It runs the same kind of threshold-driven deterministic logic, and
replays desync whenever one input such as a boost is not recorded
([GamingonPhone](https://gamingonphone.com/news/supercell-confirms-the-clan-war-replay-bug-in-clash-of-clans/),
[Sportsdunia](https://www.sportsdunia.com/gaming/clash-of-clans-replay-glitch-april-2026)).

Consequences:
- A single real battle can only be reproduced from its **exact** inputs
  (positions in game units, tick times, every boost and level). Anything less
  can only be checked as a distribution.
- Validation should use proper scoring rules (Brier, ranked probability score)
  on held-out real battles, as SIM_ACCURACY.md does. Exact trace comparison
  needs exact input logs.
- Per-battle SD of defender trophies is ~7.1. Telling two bases apart takes
  about 49 battles each at a 4-trophy gap, 195 at 2 trophies and 780 at
  1 trophy (unpaired, 80% power).

### 1c. Side choice explains most of the "sim is too weak" gap

The user's real results on these bases average 2.0★ (1/2/2/3). The sim's
random-side mean is 0.96★.

| How the side is chosen | Mean ★ | Attacker trophies |
|---|---:|---:|
| Random side | 0.96 | 10.9 |
| Best of 2 by hindsight (the scorer's `SCOUT=2` rule) | 1.33 | 13.9 |
| Best of 8 by hindsight | 1.80 | 18.6 |
| Best side by its 5-seed mean, scored on 5 **fresh** seeds | **1.65** | 12.9 |
| Visible-only heuristic: side closest to the TH | 1.48 | - |

Visible features, within-base correlation with a side's mean stars (32 cells,
10 seeds each):

| Feature | r |
|---|---:|
| Distance from entry to the TH | -0.45 |
| Wall tiles on the entry-TH line | -0.36 |
| Defenses within 7 tiles of that line | -0.29 |
| Defenses within 12 tiles of the entry | 0.00 |

Implications:
- An attacker who picks the right side recovers most of the gap without any
  new mechanics.
- The hindsight rule mixes two things: side knowledge, which is legitimate,
  and seed luck, which is not.
- A one-feature visible scout already gets about 80% of the side value. A
  small model on visible features, trained on simulated side values,
  is the obvious replacement for hindsight scouting.

The sample is small (4 bases). The heuristic was the best of three tried.

### 1d. What side choice does not explain

No battle three-starred in about 3,400 tries. Highest destruction: r18a 94%,
r18b 78%, r18c 86%, r18d 98%. Only 0.2% reached 90%. The user three-starred
r18d. Candidate causes, untested here:
- The layouts assume max levels, default CC and assumed defending heroes,
  which may overstate the defense.
- Execution the playbook doesn't capture.
- Mechanics.

The first is cheap to test: rerun r18d with the defense one level lower.

### 1e. The game data points to a fine tick

Hasty-CR chose a 50 ms tick for Clash Royale because every timing field in
that game's data is a multiple of 50
([Hasty-CR](https://github.com/amjaid/Hasty-CR)). The same test on
`data/gamecsv/v18.200.9` (1,757 time values over 1 ms; movement speeds
excluded):
- 92% are multiples of 50 ms.
- Common exceptions: 256, 128, 192, 64 and 416 ms (multiples of 16),
  875 and 375 (multiples of 125), and 666.

Those don't fit a 50 or 100 ms grid, so CoC most likely runs a fine logic
tick (16 ms or finer). Ranges use 100 units per tile (Barbarian
`AttackRange=40` is 0.4 tiles; `TargetGroupsRange=1300` is 13 tiles). Given 1a,
a finer tick matters for exact replays, not for averages.

## Part 2: what the game and outside projects show

- **Replays are re-simulated input logs.** The replay stores the attacker's
  taps and deployments and re-runs the deterministic battle
  ([GamingonPhone](https://gamingonphone.com/news/supercell-confirms-the-clan-war-replay-bug-in-clash-of-clans/)).
  A community protocol dump shows client turns carry a `tick`, a `checksum`
  and a command list
  ([SC-DevTeam/coc-messages](https://github.com/SC-DevTeam/coc-messages)).
  The game client is therefore an exact simulator, and each replay is an
  exact human input log. No public document gives the replay schema or the
  tick rate.
- **Reverse-engineered logic is not available.** CoCSharp, Pinocchio and
  COC_2k18 cover protocol and village data, not battle logic
  ([CoCSharp](https://github.com/FICTURE7/CoCSharp),
  [SC-DevTeam](https://github.com/SC-DevTeam),
  [COC_2k18](https://github.com/iGio90/COC_2k18)). The Rust
  "Clashofclans-RE" combat module is a non-functional prototype: its path
  search is a FIFO queue, and character data is `None`, so troops never move
  ([source](https://raw.githubusercontent.com/Killersparrow1/Clashofclans-RE/main/clash-of-clans-re-server/src/logic/combat.rs)).
  Nothing public is ahead of this project's engine.
- **Clean-room engine from client data (Hasty-CR, Clash Royale).**
  - Integer millitiles, a fixed 50 ms tick and seven ordered phases per tick.
  - Every phase emits normalized events, so a match can be diffed against a
    recording.
  - 1,600+ tests, plus behaviour cloning followed by PPO, against a 50/50
    mix of rule and meta opponents.
  - Its own stated limits: body-blocking is "judgement, not measurement",
    no quantitative replay accuracy is reported, and results are "the
    simulator marking its own homework"
    ([Hasty-CR](https://github.com/amjaid/Hasty-CR)).
  - The same position as this project. Its event-diff tooling and stated
    limits are the parts worth copying.
- **Data from video (KataCR, Clash Royale).** No detection dataset existed,
  so the authors generated one by compositing sprites. They trained YOLOv8 on
  it, built replay datasets with OCR and frame extraction, and trained
  Decision Transformer / StARformer policies offline. Their stated cost:
  dataset building takes substantial human effort, and the agents are not at
  human level
  ([arXiv:2504.04783](https://arxiv.org/abs/2504.04783), ICIRA 2024).
- **Learned residuals on a physics simulator.** Robotics fits the
  simulator's parameters first, then trains a network on the remaining error
  ([arXiv:2402.01086](https://arxiv.org/html/2402.01086v2)). One paper warns
  that injecting learned per-step corrections destabilizes the dynamics
  ([alphaxiv 2607.13451](https://www.alphaxiv.org/abs/2607.13451.md)). In a
  chaotic battle any residual belongs at the outcome level, not per tick.

## Part 3: ways to build a "perfect" simulator

| Method | What it gives | Cost and risk | Verdict |
|---|---|---|---|
| **A. Game client as the oracle** (friendly challenges, recorded at 1x) | Exact game behaviour for controlled set-ups | Manual; only what the camera shows; slow | Best ground truth for single mechanics. Keep VIDEO_SHOTLIST.md |
| **B. Capture replay input logs from the client** (memory or network) | Exact human inputs plus exact layout, the dataset everything else lacks | Reading or intercepting the client likely breaches Supercell's terms; risk to the account; format undocumented | Only with eyes open about the account risk. Would enable exact replay validation and imitation learning |
| **C. Computer vision on 1x replays** (KataCR route) | Deployment positions and times, troop tracks and destruction curves, without touching the client | Detector training: sprites can be composited synthetically onto base images (`grid_overlay.py` already maps tiles to pixels). Expect about 0.25-tile and 1-frame (17 ms) accuracy | **Recommended data engine.** Replays at 4x lose the positions (`data/replays` notes) |
| **D. Clean-room rule engine from client data** (current Rust engine, Hasty-CR) | Fast (~200 ms per battle), inspectable, extrapolates to new layouts and armies | Every unmeasured rule is a guess; chaos limits per-battle checks | Keep it as the core. Spend effort per 1a: AI rules from `globals.csv`, wind-ups, scouting, execution |
| **E. Calibrated hybrid** (D plus simulation-based inference over uncertain constants, plus an outcome-level residual model) | Matches real star/% distributions with uncertainty | Needs about 40+ real battles with matching inputs; risk of fitting noise | Do once C supplies inputs. Use a Morris screen to pick the constants |
| **F. Learned simulator / world model** (neural net trained on battles) | Very fast outcome prediction | Needs huge data, fails on unseen layouts, learns sim quirks if trained on D | Only as a search pre-screen surrogate, never as the judge |

No route gives a per-battle exact prediction without exact inputs (1b). The
realistic target is D+E with C as the data source: the engine predicts the
*distribution* of outcomes for a base, army and attacker profile. It is
validated on held-out real battles and spot-checked per mechanic with A.

### Modelling human attackers

- **Scouting is the biggest lever (1c).** Replace hindsight best-of-k with a
  visible-state scout: a small model on visible features (TH distance, walls
  and defenses on the corridor, exposed defenses, CC position). Train it on
  simulated side values averaged over hidden-state ensembles, then add human
  noise to its choice.
- **Execution, not stat scaling.** Use per-battle reaction delay, placement
  error and missed-action rates. Placement error matters even at small sizes
  (1b), so the error model's *shape* matters. Measure it from C.
- **Imitation needs input logs.** Behaviour cloning, then RL, worked for
  Hasty-CR. For CoC it needs the deployment logs from B or C. The
  move-library design (MOVE_LIBRARY_DESIGN.md) is the right structure to fit
  them into.
- **Evaluate attackers on real outcomes, not sim wins.** Hasty-CR's "marking
  its own homework" caveat applies to any policy trained in the simulator.

## Part 4: next steps

| # | Step | Evidence for it | Size |
|---|---|---|---|
| 1 | Visible-state scout replacing hindsight `scouted()`; report both | 1c: 1.48 vs 1.33★, no luck selection | Days |
| 2 | Re-test r18d with lower defense levels and other CC; find why no triples | 1d | Hours |
| 3 | Measure defense wind-up and first-hit timing from 1x footage | 1a: largest single effect | Measurement |
| 4 | Target-list rules from `globals.csv`, behind a flag; A/B against real outcomes | RUST_REVIEW R4 | 1-2 weeks |
| 5 | CV pipeline for 1x replays: synthetic sprite frames, YOLO detector, deployment and track extraction | Part 2 (KataCR); unlocks E and imitation | 2-4 weeks |
| 6 | Base comparisons with common seeds and at least 200 battles per finalist, with paired CIs | 1b sample sizes | Hours |
| 7 | Keep the 0.1 s tick for search; add an exact-replay mode at 16 ms only once input logs exist | 1a, 1e | Later |
