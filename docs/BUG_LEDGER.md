# Simulation bug ledger

Findings from bug-hunt passes over the Python engine (`src/baselab/engine/`),
each checked against game data (`data/gamecsv/v18.200.9/*.csv`), the wiki
text in `data/wiki/`, or video measurements (`docs/VIDEO_MEASUREMENTS.md`).
Every fix goes into the Python engine first, then the Rust port
(`docs/RUST_PORT.md`), then parity. Hunters: read this first; do not
re-report items listed here unless you have new evidence.

Policy: game data wins over the wiki for numbers it has (the wiki's flyer
ranges were 0.5 tile long; the real replay agreed with game data).

## Fixed

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
