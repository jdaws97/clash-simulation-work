# Simulation bug ledger

Findings from bug-hunt passes over the Python engine (`src/baselab/engine/`),
each checked against game data (`data/gamecsv/v18.200.9/*.csv`), the wiki
text in `data/wiki/`, or video measurements (`docs/VIDEO_MEASUREMENTS.md`).
Every fix goes into the Python engine first, then the Rust port
(`docs/RUST_PORT.md`), then parity. Hunters: read this first; do not
re-report items listed here unless you have new evidence.

Policy: ClashKing static data (`data/clashking-static-data.json`, assets commit
b8f42a7, 2026-09-28) wins for every numerical field it carries, including unit,
hero, pet and building HP/DPS, attack speeds/ranges, equipment abilities and
spell values. Match the entity/variant, explicit level and quantity/units first.
The older `data/gamecsv/v18.200.9/*.csv` snapshot predates July 2026 balance
changes; use it only for fields ClashKing lacks (timings, radii, flags,
projectiles and ability internals), and flag CSV-only quantities affected by
those changes. The wiki mirror is the tie-breaker for rules.

## Fixed

- Data audit (2026-10-23, ClashKing b8f42a7; setup probes only): removed the
  round-7 CSV override of current unit stats. Changed HP/DPS (old -> new):
  Bowler L10 850/156 -> 860/160; Electro Dragon L8 6200/460 -> 6400/475,
  L9 6700/500 -> 6900/510; Dragon Rider L6 6200/520 -> 5900/490;
  Super Bowler L10 3600/300 -> 3700/310; Thrower L3 2600/230 -> 2500/220,
  L4 2800/240 -> 2650/230; permanent Meteor Golem L1 13000/450 -> 14500/480,
  L2 14500/500 -> 16000/530, L3 16000/550 -> 17500/580. Derived damage/hit:
  Bowler L10 343.2 -> 352; Electro Dragon L8 1610 -> 1662.5;
  Dragon Rider L6 624 -> 588; Super Bowler L10 660 -> 682;
  Thrower L3 575 -> 550, L4 600 -> 575; Meteor Golem damage/hit follows DPS.
  Druid L5 signed healing DPS -100 -> -105 (actual healing already 105);
  Troop Launcher L1-4 sentinel DPS -1 -> 0; Thrower L1-4 speed 2.2 -> 2 tiles/s.
  Giant Arrow damage L9-11 1200 -> 1100, L12-14 1500 -> 1200,
  L15-17 1750 -> 1350, L18 2000 -> 1500; Fire Heart regeneration L15-17
  155 -> 140, L18 175 -> 150 HP/s; Rocket Backpack damage L21-23
  1925 -> 1875, L27 2200 -> 2150. Geared Mortar L18 DPS 86 -> 89,
  damage/shell 129 -> 133.5 (CSV burst timing retained). Skeleton/Bat Spell
  L1-8 radius 2.25 -> 2.2 tiles. Yeti Undertaker L1-18 reach 4 -> 0.8 tiles
  (wiki infobox vs ClashKing; no CSV row). Spell Tower mode metadata now
  follows ClashKing: Invisibility range 9 -> 4.5 tiles and interval 70 -> 50 s;
  Earthquake interval 70 -> 50 s (effective triggers/recharges already matched).
  Hero Hall L1-3 HP and Spell Tower trigger ranges already used current values.
  Meteor Golem's 6000 HP at L3 belongs to the temporary event variant.
  CSV-only Meteormite L1-3 HP 6500/7250/8000 and DPS 180/200/220 remain flagged
  against wiki 7250/8000/8750 and 190/210/230; actual split HP inherits half
  the corrected parent's base HP. ClashKing has no permanent Meteormite row.

- 2026-10-22 Log Launcher logs dealt all damage along 20 tiles instantly;
  now travel at RollingLog.Speed 420 (4.2 tiles/s) from StartOffset 100.
- 2026-10-22 Flying hero ranges came from the wiki (Dragon Duke 0.3, Minion
  Prince 3.5): game data heroes.csv AttackRange 125 / 450; Grand Warden air
  mode AltAttackRange 650.
- 2026-10-22 Air Sweeper acquisition cone +-45 deg; game data
  TargetingConeAngle=105 (+-52.5).
- 2026-10-22 Puppet summons fell back to the defender's Town Hall level cap.
- 2026-10-22 Seeking Shield did not stop ordinary attacks (game data
  DisableAttacking, DeactivateAfterTime 1200).
- 2026-10-22 Haste Vial reset the attack cooldown (20 throws in 10 s; wiki
  max 19).
- 2026-10-22 Log Launcher log damage ignored calibrated strength
  (u.extra["strength"] was never set).
- 2026-10-22 pathing.next_step returned np.float64 positions (NumPy round()
  in logs).
- 2026-10-22 Battle built walls in set order (depended on set history).
- 2026-10-22 playbook steps were shallow copies: building a plan appended a
  citation to the cached playbook every time.

- Round 1 (2026-10-22, output/hunt/r1-*.out): Tornado Trap rotation;
  Eagle main damage (was reduced by the shockwave); projectile travel for
  Wizard Tower >4, geared Cannon, long-range Multi-Gear, Mortar flight from
  distance; Poison Tower triggered by spell Skeletons; Multi-Archer spare
  arrow alternation; game-data movement speeds (Thrower 2.2, Log Launcher
  0.7, Flame Flinger 0.8, Yak 3); Meteormite approach-and-merge; Ruin Witch
  rubble claims; SelfAsAoeCenter splash (Balloons); Log Launcher wall and
  point-blank strength; Meteor Golem and Yetimite flights; chain hops 128 ms
  apart; Electro Dragon death lightning timed; data-driven projectile speeds
  and start offsets for troops, heroes and pets; Long Shot 9.75; Electromite
  frost; equipment validation (hero, duplicates, slots); Spiky Ball and
  Giant Arrow travel; Fire Heart hits units and walls; Poison Lizard poison;
  Diggy re-attach; Unicorn heal projectile; Jelly brainwash pause; pet ranges
  from pets.csv; puppet batches; Revive without stale aura; Earthquake 5
  hits 400 ms apart; Angry ignores defenders; Jump window 0.4 s; Totems take
  defensive poison; tower Rage lasts 1 s; Skeleton/Bat radius 2.25; Ice
  Block covers pending spell summons; Valkyrie kill resets her cooldown;
  Jelly disables Warden follow. Saved army lavaloon-queen-dragons had Warden
  equipment on the Queen (now Archer Puppet).

- Round 2 (2026-10-22, output/hunt/r2-*.out): next_step walked into walls
  beside cheaper open routes (now minimises distance plus entering cost);
  source fields reused another troop's whole-tile field (now per half-tile
  cell); attack ranges from game data for every unit; Valkyrie spin-position
  livelock (0.3-tile arrival tolerance); Warden follow ignored untargetable
  buildings; Wall Breakers skipped partial enclosures; defending Firemite
  burn pools; hound pup spawn spread; Super Witch 25 s summon cooldown;
  strength missing on CC cargo and Bears; Skeleton Trap skeletons existed
  before their spawn times; Town Hall poison skipped sieges; mixed-level
  Builders stacked without the reduction. Plans: fallback Wall Breakers
  deployed beyond the army; Giant Arrow aimed at a substituted target and
  required 12 tiles; cited immediate casts stretched by add_waits; fallback
  Revive not counted as pending offense; a step's troops spawned at once
  (now 0.133 s apart); variant selection blocked by usable steps; recalled
  units left their group; meteor-golem and super-minion-air armies illegal.
  Scoring: skill quantiles only balanced globally; compare_layouts and
  proof_scorer used raw averages, not the scouting objective; default
  calibration not round 8; archetype shares shifted by build coverage;
  full scouting keyed on group >= 5000; one-star trophies not capped at 15.

- Round 3 (2026-10-22, output/hunt/r3-*.out): attacking burn fields missing
  (Flame Flinger fire FireSpiritExplosion: PoisonIncreaseSlowly ramp, x25
  walls, 75 x 400 ms per game data vs the wiki's 22 s; Furnace Firemite
  FireSpiritBurn pools); frost combined one source's factor with another's
  expiry; summon wind-ups missed CSV aliases (Spell Bat, Icemite, Firemite
  Spawn, Disarmer); Spell Skeleton 30/hit (game data 25; per-hit now follows
  DPS x interval except bursts); Lavaloon bombs ignored rage/aura/slows/haste;
  Recall did not pause Gauntlet splash and other equipment timers; Tome/Torch
  admitted recipients during the 1 s tail (emission = DeactivateAfterTime);
  Rage Gem tail; opening zap spent every Lightning on one Air Defense;
  deployed cleanup stayed in reserve (false timeouts, double lure); fallback
  spells cast together in one tick; level overrides not checked against
  Town Hall/Laboratory; one-star trophies counted from 0% (now above 1%).

- Round 4 (2026-10-22, output/hunt/r4-*.out): TH death poison radius 4.5
  (game data 4); Air Sweeper pushes were instant (wave 6 tiles/s); Geared
  Mortar cooldown 4 s (AltAttackSpeed 3.5); Builder's Hut nails instant;
  missing projectile StartOffsets (Cannon, Archer Tower, Air Defense,
  Multi-Archer, Bomb Tower, Multi-Gear); Mortar pushback 2 tiles (1);
  Troop Launcher picked the largest single troop, delivered instantly, no
  HP decay, wrong occupant order; Battle Drill no surfacing stun; Blimp
  bombs 1.5 tiles, buildings only (3 tiles, walls, ground defenders); Wall
  Wrecker no splash; Super Hog rider landed instantly; Meteormites of
  different levels never merged; Firemite direct radius 0.8 (0.1); Flame
  Flinger shots simultaneous (128 ms apart); Headhunter poison had no
  damage; Giant Giant ignored defenders; Noble Iron used the normal
  projectile; Greedy Raven had no projectile; Giant Arrow 1500 (2000),
  Fire Heart 150/s (175), Rocket Backpack 2150 (2200); Stun Blaster skipped
  TH/CC/collectors; Earthquake Boots instant (5 hits 400 ms apart);
  equipment summons at fixed world offsets (now facing-relative); Poison
  Lizard poisoned at launch; Clone ignored strength; air trap skeletons
  range 0.4 (0).

- Round 5 (2026-10-22, output/hunt/r5-*.out, review output/hunt/review5.out):
  Warden flipped targets every tick (never attacked); in-range buildings
  chosen by list order (now closest); source fields undercounted the goal
  wall cost; Jump made Wall Breakers skip all walls; Yetimites ignored in
  Warden weight; Root/Dragon Riders dropped cleanup targets to retaliate;
  Invisibility Tower trigger used centre distance; Headhunter poison hit
  heroes 20x (round-4 regression); Spell Tower timer restarted when the
  first trigger troop died; Dark Orb skipped invisible targets; Ice Block
  stopped Rocket Backpack; Seeking Shield KO release delayed 0.93 s.
  Plans: variant used a pet on the wrong hero; surplus Revives unusable;
  opening Lightning after the main deploy; cancelled repeating steps kept
  their spells; skipped deploys dropped their troops.

- Round 6 (2026-10-22, 8 slices, output/hunt/r6-*.out, review
  output/hunt/review6.out): Multi-Archer distant-pair rule; Inferno 128 ms
  packets; Burst Mortar over AltDPS after round 4; Scattershot skipped
  Totems; Wizard Tower L1-4 offset; supercharged Bomb Tower death damage;
  Air Sweeper push lockout; Phoenix egg triggered traps; Bomb push 2 tiles;
  air trap offsets; Duke/Inferno Dragon kill cooldowns; Rampage x Rage;
  mites opened the Clan Castle; Clone/Recall housing of Big Boy and pups;
  Super Troops skipped by Monolith Arrow; continuous siege decay; Hog Rider
  Puppet batches; unowned Meteor Staff on account plans; Sneezy range;
  Lavaloon pups stacked; orphan Unicorn healed Furnace; Raven stalled on
  hidden resources; donated Lightning unused; donated siege levels capped
  at the attacker's; air-mode Warden with Healers; repeated Invisibility on
  hidden buildings; hero roles ignored; Super Troop levels; AttackPlan
  waves dropped at once; evolution on the old opponent mix; final_compare
  without the red team; seed overlap; SE vs bootstrap.
  Rejected: KO auto-activation should leave 1 HP with no heal (the wiki's
  "1 hitpoint" is before the ability's heal).

## Known, not fixed

- Town Halls 13-15 get the TH16 Giga Inferno profile (defense.py
  GIGA_INFERNO[16]); bundled tables data/wiki/tables/Town_Hall_Giga_Inferno_TH13..15.
  Irrelevant to the user's TH16 base; fix when lower Town Halls matter.
- Royal Champion / Dragons too strong in the first 30 s of the real replay
  (data/replays/2026-10-21-maroon-machine.json): sim kills the first X-Bow
  and Infernos at 16-21 s (RC 66-94% of the damage), real 24-26 s; Eagle 9 s
  vs real 14.5 s (Dragons). RC numbers match max-level game data; cause
  unknown (equipment level, position, first target, spear timing). Needs
  frame measurement.

## Unresolved (evidence conflicts or missing)

- New-target wind-up counts down during travel (units.new_target_windup).
  Replay: a Dragon's first breath 1.67 s after drop, 0.6-0.9 s after
  reaching range: between "from selection" and "from arrival".
- Freeze outer duration (spells.csv FreezeOuterTimeMS) unused; boundary rule
  unknown.
- Air Sweeper puff width (+-5 deg) vs ShockwaveArcLength=700; replay sweeper
  facings unknown.
- Defending-hero leash / search radii (heroes.csv 10-tile search, 3-tile
  patrol, 12-tile alert) vs the engine's 7-tile leash and 0.5 s retargeting.
- Spell landing phases (DeployTimeMS / ChargingTimeMS / HitTimeMS) vs the
  universal 0.5 s.
- Invisibility Tower triggers only on non-lethal hits.
- Unmodelled defense delays: Scattershot NewTargetAttackDelay 2.2 s and
  CoolDownOverride, Inferno AlternatePickNewTargetDelay, Air Sweeper
  PrepareSpeed, Eagle DamageDelay 580; instant X-Bow/Ricochet/Monolith/
  Scattershot hits.
- Log width: RollingLog.PenetratingHitBoxWidth=30 vs the engine's 0.8.

- Round 1 deferred: Mortar 50% radial falloff (no data either way);
  Inferno Artillery instant fireballs and Firespitter burst delay (TH17-18
  defenses); unit HP/DPS where game data v18.200.9 and the wiki differ
  (Electro Dragon 8-9, Thrower 3-4, Meteor Golem/Meteormite, Super Bowler
  10, Druid heal: the wiki may reflect a later balance patch); Siege
  Barracks release cadence by level; Unicorn healing under Rage; Mighty Yak
  speed (CSV 300 vs wiki table 250 - CSV applied by the speed rule); attack
  slows baked into the whole cooldown (needs measurement).

- Round 6 deferred (need video): tracking projectiles vs moving targets
  (launch-time ETA); Tornado force vs TornadoSpeedTowardsCenter; Spring
  Trap EjectRadius vs TriggerRadius; Sky Wagon barrel flight (no data);
  whether burn fields keep a battle running; Burst Mortar cycle (wiki
  123/shell implies 5 s).

- Round 4 deferred: Firespitter DontTrackTarget (TH17+ defense); Blimp
  cargo emergence delay (~1.15 s after the blast, one video sample);
  Tornado radius 3 (trap) vs 4 (spell row); Heroic Torch half speed for
  other heroes (wiki) vs SpeedBoost2=9 (game data).

- Round 2 deferred: defensive troop stat variants (CC troops use attacker
  stats); calibrated strength for pets and hero equipment summons;
  tools/baselab/predictor_proof.py still groups seeds the old way (needs
  the seed % 5 skill grouping).

## Rejected

- Destroyed buildings/walls should keep their no-deploy zone (round 3,
  SUSPECTED): no evidence; in the game the red zone shrinks as buildings
  fall.
- Illegal drops should not deploy (round 3): plans aim at points and the
  engine snaps them to the nearest legal tile, modelling a player tapping
  the border; intended.

- Royal Champion base HP/DPS inflated: no, match heroes.csv level 55 and
  equipment at max (round 0).
