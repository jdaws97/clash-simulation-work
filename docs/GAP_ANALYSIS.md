# Gap analysis (2026-10-22; Rust status refreshed 2026-10-25)

Rust is the reference; Python is frozen. The Rust golden suite replaces Python
parity, and `rust/src/detmath.rs` supplies platform-identical maths. Historical
Python findings below need current Rust verification; see
[RUST_PORT.md](RUST_PORT.md) and [RUST_REVIEW_2026-10-25.md](RUST_REVIEW_2026-10-25.md).

What the lab does not model, models crudely, or cannot check, ranked by how
likely each gap is to make a base the sim calls best fail in real ranked play.
Bugs (wrong numbers in modelled mechanics) are in `docs/BUG_LEDGER.md`; this
file is about what is missing. Sources: four read-only Codex passes
(`output/hunt/gap-a..d.out`: content coverage, battle mechanics, attacker
behaviour, pipeline), with the high-impact claims re-checked by hand
(marked *verified*).

Impact: **H** can change which base wins; **M** can change close rankings;
**L** edge cases. "Repo" = closable from data already here; "measure" =
needs real-game footage or new defenses.

## 1. Who attacks the base (H, cheapest to fix)

- **Wrong opponent mix (verified).** Ranked scoring assumes 65% TH18 / 35%
  TH17 / 0% TH16 attackers (`evaluate.py:270`). The account's archived ranked
  defenses (`data/live/battles.jsonl`, 23, all Electro League 31) were TH17
  x17, TH16 x5, TH15 x1, TH18 x0. The search mostly optimises against
  attackers this base has not met. Repo: refit the mix from the log now;
  keep collecting.
- **Thin army library per Town Hall.** TH17 has only Dragons and Throwers
  (51/49); the real log also shows E-Drags, Hydra (Dragons + Dragon Riders),
  Meteor Golem, Titan/PEKKA/Root Rider and Witch smash. All TH17/TH18 builds
  borrow TH18 archetype shares; the 22 meta builds carry no equipment
  loadouts, so every hero gets defaults. Repo + collection.
- **Max levels everywhere.** Non-user attackers use max levels for their
  Town Hall; real ranked attackers at Electro are often under-levelled.
  Collection (battle log gives TH only; army share codes give levels).

## 2. Calibration and validation (H)

- **What is scored is not what is calibrated (verified).** Calibration fits
  one number per army (same-TH three-star rate, TrophyCoach) by scaling
  attacker HP and damage. Every build in the default ranked mix is marked
  `uncalibrated` (TH17/18 strengths are transferred from TH16 or 1.0).
  Ranked trophies depend on how attacks fail (1 vs 2 stars, 65% vs 98%),
  which is never fitted. Measure: star/percent distributions by attacker
  TH and army.
- **One replay.** The only frame-level real check is a single TH17 Dragon
  three-star (`data/replays/2026-10-21-maroon-machine.json`); no ground
  attack, no failed attack, no timeout. The sim is still ~14 s too fast
  on it (69 s vs 83 s). Measure: more replays, especially failed attacks.
- **No real A/B of layouts.** Ranked uses a frozen snapshot per tournament;
  the archive maps to essentially one layout, and replay tools overwrite
  historical defense levels with today's. Nothing yet tests "sim ranks A
  above B" against real results. Repo tooling (snapshot archive) + weeks
  of alternating finalists.
- **No uncertainty on rankings.** Evaluations are point estimates: no
  paired confidence intervals, no winner probability, no minimum meaningful
  gain. Real defenses are noisy (mean 5.4 trophies, SD 9.1), so real
  confirmation of small gains is slow; sim-side intervals are cheap. Repo.

## 3. How the simulated attacker thinks (H)

- **Skill is stat scaling.** The five skill quantiles multiply attacker HP
  and damage (x0.83..x1.21); decisions are identical. Real skill is
  placement, timing and mistakes; scaling shifts one-shot breakpoints
  instead. A base that induces human errors and a base that resists strong
  stats are different bases. Repo (behavioural profiles) + measure.
- **Scouting prior quality (Rust R5 update).** Scoring now defaults to
  visible-state hidden ensembles and commits before real-state execution.
  The old completed-battle selection remains explicitly `oracle`. Priors are
  assumed and need held-out validation; see [SCOUTING.md](SCOUTING.md).
- **No route planning per layout.** Red-team search controls entry angle,
  flank and step overrides, but cannot choose a specific funnel, compartment
  or building instance; most `base_reading` rules in playbooks never become
  decisions. Offset compartments and narrow drop pockets can look strong
  because no attack expresses the human answer. Repo (large).
- **Hybrid recipes.** Applying a playbook to a meta build substitutes
  variants for missing resources and pushes unmatched units into the main
  entry; cited loadouts and pet pairings are not preserved. The base may be
  beating attacks nobody actually runs. Repo.
- **Pacing from narration.** Step gaps come from caption timestamps; three
  actions narrated at one timestamp get 3.8 s gaps each (Root Rider Healers,
  Warden, Sky Wagon). Slow assembly favours exposed entries. Measure (frame
  annotation of existing footage).
- **No recovery, endgame or spell-geometry planning.** Failed funnels are
  not repaired; cleanup starts at a fixed +25 s; no clock-aware choice to
  secure stars; spells aim at centroids, not at what they protect or stop.
  Repo.
- **No enforced red-team gate.** Quality-diversity search and its hold-out
  bypass red-team scoring (`funnel.py:116`); adaptive attackers exist but
  finalists are not required to survive them. Repo, small.

## 4. Troop and defense behaviour the engine approximates (H/M)

- **Ground targeting (H).** Troops pick the cheapest route to any eligible
  building with a fixed wall cost. The game keeps short target lists and
  target memory (`globals.csv`: TARGET_LIST_SIZE=3, MAX_TARGET_LIST_SIZE=6,
  REMEMBER_ORIGINAL_TARGET, FORGET_TARGET_TIME, retarget noise). This is the
  core of what base design exploits. Measure (controlled target-choice
  tests) + repo parameters.
- **Crowding and collision (H).** Separation only within a 4-tile bucket,
  none for defenders, centre-to-centre combat distances. Clumping drives
  splash, Scattershot, poison and healing value. Measure.
- **Grand/Apprentice Warden grouping (H).** Votes by current target within
  13 tiles instead of spatial groups (TargetGroupsRadius=500,
  TargetGroupsMinWeight=2000; WARDEN_WAITS_FOR_GROUP_RETARGETING). Split
  funnels decide which push keeps Tome/Rage. Measure.
- **Hidden information inside the battle (H).** Unrevealed Teslas count as
  known threats in plan logic and sit in the navigation grid; one Tesla
  reveal clears every attacker's target map-wide. Repo + measure.
- **Clan Castle exits and siege/cargo delivery (H).** Defending CC troops
  leave from one point every 0.3 s; siege cargo appears at once on a ring;
  Sky Wagon delivers instantly. Lure and poison value depend on this.
  Measure.
- **Stick Horse King (H vs TH17+).** Mounted King treats walls as free;
  wiki says he prefers a longer open route over jumping. Measure thresholds.
- **Tornado dynamics (H), trap timings (M).** Tornado force model assumed;
  TornadoSpeedTowardsCenter unused. Trap action frames use an inferred
  frame rate; Spring EjectRadius unused. Measure.
- **Medium:** defending heroes do not patrol (PatrolRadius unused);
  Multi-Archer Tower lacks the far-two-targets rule; homing projectiles hit
  at a launch-time ETA instead of flying; summon animations/activation
  (Witch SummonTime, SpawnIdle, pet SpawnDelay/LeashLength); projectile aim
  scatter (TargetPosRandomRadius: Flame Flinger, Super Dragon); Poison ramp
  is an assumed 4 s linear curve; Builder repair priority; Inferno Dragon
  TargetKilledCooldownTimer; Druid heal-chain count (3 vs 4 targets) and
  link distance (3 vs 4.5 tiles); fixed 0.1 s tick with attackers resolved
  before defenders.
- **Low:** Miner hide randomness, Hero Hunter / Cake-A-Pult phases, Meteor
  Golem merge immunity, seasonal troops run as generic units (should be
  rejected in ranked), event traps/effects absent.

## 5. What the base search cannot change (H/M)

- **Defensive setup outside the layout:** which heroes defend and on which
  banner (originals keep King/Queen/Warden/Prince; the observed replay had
  King/Queen/Prince/Duke), Clan Castle composition (only 3 of 6 presets
  fit the account's capacity), gear-up modes (implemented, never mutated).
  Repo, days.
- **Per-copy levels.** One level per building key; a partly upgraded
  account cannot put the stronger copy in the critical compartment. Repo.
- **Objective (verified).** Ranked search maximises `trophies - 0.02 x
  destruction` (`optimize.py:51`): up to 2 trophies of weight on
  destruction, not a tie-break; it can pick the lower-trophy base. Repo,
  minutes.
- **Build guide omits CC troops and hero-to-banner assignments**, so the
  user can follow it exactly and field a different defense. Repo.

## 6. Engine coverage and data currency (M)

- **Rust content coverage requires admission checks.** There are no remaining
  `todo!` paths in `rust/src`. Supported equipment/pets are checked before
  compile/setup; catalog presence alone does not prove combat support. The
  868-case golden suite protects existing traces, not real-game fidelity.
- **No versioned data chain.** Registry, wiki tables, CSV folders, Rust
  catalog, calibration and saved winners are not tied to one data version;
  `wiki_mirror.py fetch` skips existing pages, so refreshed wiki text never
  arrives; calibration files record no input hashes. After a balance patch,
  rankings can silently rest on old numbers. Repo, days.

## Checked and not a gap

- Supercharges are TH18 content (`data/wiki/text/Supercharge.txt`); a TH16
  base has none.
- Defending heroes have no equipment abilities on defense (wiki, hero
  pages).
- Ranked attackers bring a prepared army; per-base army choice is a war
  concern only.
- Weekly defense schedule: with fixed exposure, maximising expected
  trophies per defense is the right objective.

## Suggested order

1. Cheap, high-leverage, repo only: opponent mix from the defense log;
   lexicographic objective; enforced red-team gate on finalists; paired
   confidence intervals on rankings; search hero assignment, CC and gear
   modes; complete build guide.
2. Attacker realism in code: scouting without hindsight (choose the side
   from visible state, then run once); skill as decision noise instead of
   stats; preserve cited recipes.
3. Measurement campaign (video): ground target choice, crowding, Warden
   grouping, CC exits, trap/tornado timings, failed-attack replays; then
   recalibrate on star/percent distributions by attacker TH and army.
4. Infrastructure: versioned data manifest, snapshot archive of committed
   ranked layouts, Rust coverage of every Python path.
