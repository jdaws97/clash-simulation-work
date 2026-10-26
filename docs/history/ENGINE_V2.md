> Predecessor Python filenames and parity procedures in this document are
> historical provenance from `f04706c`. Deleted tools are not runnable; see
> [the current documentation](../README.md) for native commands and remaining Python ports.

> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Engine v2: how the simulator works and how far to trust it

Engine v2 (`src/baselab/engine/`) is the only battle engine (the old v1
`sim.py` was removed on 2026-10-20). Every number comes from
`data/registry.json`. That file merges ClashKing's game-file export with the
Fandom wiki level tables, mirrored 2026-10-15. Each behaviour cites the wiki
page it implements.

## Layout

| Module | What it covers |
|---|---|
| `stats.py` | Registry access: `get(name, level, *columns)`, `max_level(name, th)` |
| `specs.py` | Behaviour of every unit: targeting, wall handling, attack shape, death effects, specials. Event troops get a generic spec derived from their infobox |
| `battle.py` | 0.1 s tick loop, damage, destruction and stars, Clan Castle, attacker and defender AI, path-cost targeting |
| `defense.py` | Every defense: Giga Inferno (TH16), Inferno Artillery (TH17/18), Multi-Gear, Firespitter, Super Wizard Tower, Revenge Tower, Spell Tower modes, Builder's Huts |
| `units.py` | Troop specials, summons, death effects, healing, sieges |
| `heroes.py` | All 42 equipment pieces and 12 pets; auras; abilities; Phoenix; Revenge Deck and Snake Bracelet passives; defending heroes (no equipment, as on the wiki) |
| `spells.py` | All 20 spells, Spell Tower casts (rage, poison, invisibility, earthquake), defensive poison and Inferno Artillery flame pools |
| `traps.py` | All 8 traps, including the TH17+ Giga Bomb (18-housing trigger) |
| `plans.py` | Attack plans: armies taken from real attacks on your base, plus the attacker brain |
| `playbook.py` | Cited real-player playbooks as attack plans (`BASELAB_PLAYBOOKS=1`) |
| `result.py` | `Result`, the outcome of one battle |

## Checks that passed

- **Defense DPS.** One building fires at an immortal dummy for 20 s, and the delivered DPS is compared with the wiki table. All defenses land within about 3%. Examples: X-Bow 226 vs 225, Giga Inferno 301 vs 300, Firespitter 460 vs 455, Multi-Gear (fast) 716 vs 710, Air Defense 600 vs 600. This check found a real bug: the tick quantized cooldowns, so any weapon faster than 0.1 s fired at 64% of its true rate. That is now fixed for weapons and for troops.
- **Coverage.** `tools/baselab/engine_coverage.py` runs every registry entity in a battle: 111 units, 20 spells, 54 equipment pieces and pets. None crash. The 8 "no effect" units are expected: Healers don't deal damage, Wall Breakers only hit walls, and Minions and pups die before reaching a building.
- **Wall Breakers.** Three max-level Wall Breakers deal 3 × 5,040 to walls. One Super Wall Breaker Mega Bomb deals 16,520 to walls. Earthquake on walls follows the wiki formula: the nth quake deals p/n + 5(n−1)², so 3 quakes never break a wall and 4 always do.
- **Against reality.** On five real human TH16 bases, the meta TH17/18 armies give the defender **2–8 trophies with 59–86% three-starred**. Your actual ranked log is about **5 trophies per defense with 77% three-starred**.

## Calibration

Per-army strength multipliers scale unit HP and damage so that simulated 3★ rates match TrophyCoach's real same-TH ranked rates (`tools/baselab/calibrate.py`, `data/baselab-calibration.json`):

| Army | Strength | Meaning |
|---|---:|---|
| Hydra | 1.06 | Plays at face value |
| E-Drag | 1.01 | Plays at face value |
| Throwers | 1.51 | The sim's brain under-performs real players |
| Root Riders | 1.80 | The sim's brain under-performs real players |

Air armies need no correction. Ground armies still need 1.5–1.8×. The gap is attacker skill the brain doesn't reproduce yet: breaching and wall micro (timing Wall Breakers and Earthquakes, aiming the Log Launcher) and funnelling. Before this round it was 2.2–2.5×. Three fixes closed most of it:

1. Ground troops now pick targets by **path cost**, with walls counting as a detour. The wiki says ground troops "will often ignore" walled compartments without access.
2. The Log Launcher now matches the wiki: 20-tile logs plus the point-blank blast.
3. The plans now use your real attackers' armies.

## Added on 2026-10-15 (round 2)

- **Ranked difficulty modifiers.** Pass `modifier` (`legend3`, `legend2` or `legend1`) to `Battle` or `Scenario`. The values are the wiki table's:

  | League | Defense DPS | Defending heroes | Guardians | Attacking heroes |
  |---|---|---|---|---|
  | Legend III | +10% | +10% | +5% | −5% |
  | Legend II | +15% | +15% | +10% | −10% |
  | Legend I | +20% | +20% | +20% | −20% |

  The wiki's exclusions apply: no boost to death damage, Monolith's percentage bonus, traps or Spell Tower spells. The attacking hero penalty covers base stats and passive equipment boosts, plus fixed per-hit boosts such as Rocket Spear.
- **TH18 Guardians.** Longshot, Smasher and Logger defend from the Town Hall in place of a weapon. `Layout.guardian` selects which one. Each waits on the Town Hall until an attacker enters its trigger radius, then patrols within its patrol radius.
  - Longshot: long-range splash with a death blast.
  - Smasher: enrages by 60% when the Town Hall falls, and drops a defensive Rage Spell on death.
  - Logger: a rolling log that knocks units back.

  Guardians take 30% of poison effects.
- **Portal Pendant** (Minion Prince, released Oct 8, 2026). Pulled from the wiki because the ClashKing export predates it. It recalls the Prince and nearby units by the wiki's priority order up to its capacity. The plan redeploys them where the most buildings remain, with the healing and Haste from the stat table.
- **Your base** is `data/reference-bases/your-base.json`. It comes from game-memory slot `l4x`, checked against screenshot IMG_4219: walls match exactly, and two Infernos and one wall were corrected from the image. Hero banner positions are estimates.
- **Attacker brain.**
  - The main push lands against the base instead of at a distant gap.
  - Cleanup troops snipe the far buildings starting 25 s into the push.
  - Each change was checked with `tools/baselab/ab_test.py` on 80 battles. Root riders went from 25% to 40% three-stars at fixed strength.
  - Wide line deployment was tried and rejected, because it made both armies worse.
- **Where the ground gap comes from.** In ground attacks that fail, the army is spent: by 170 s the throwers are dead, and only Healers and Firemites remain. Time spent stuck on walls is not the cause. The remaining calibration factor (throwers 1.53, root riders 1.64) stands in for player skill with heroes and spells.

## Deploy zones (fixed 2026-10-15 after the user spotted holes)

The user noticed that the first ranked winner left open gaps inside its walls. A real attacker would drop troops into those gaps.

- **The rule** (wiki: Walls; Hidden Tesla). Every structure, walls included, has a one-tile no-spawn border. Hidden Teslas and traps have none. Any gap wider than two tiles is a drop spot.
- **The bug.** The sim's attackers only walked in from the map edge, so interior holes were never used, and the optimizer learned to leave them. The first ranked winner had 88 hole tiles.
- **The fix.**
  - `src/baselab/deploy.py` finds holes in any layout.
  - The battle's deploy zone is now live: destroyed buildings and walls stop blocking drops.
  - Attack plans consider every interior drop spot for the main push and for cleanup snipes.
  - The base search penalizes hole tiles, and a "fill hole" move plugs gaps with resource and army buildings.
- **Effect.**
  - The old ranked winner fell from 15.7 to 7.3 trophies per defense once attackers used its holes.
  - Recalibration closed most of the ground gap: throwers 1.53 → 1.23, root riders 1.64 → 1.17, hydra 1.01, e-drag 0.83. Live deploy zones were a large part of what earlier looked like player skill.
  - Against the user's logged attack mix (TH16 ×5, TH17 ×8), the sim scores their base at 4.0 trophies with 76% three-starred. The real log shows about 5 trophies and 77%.

## Real levels, Crafted Defenses and scouting (2026-10-15, round 3)

- **Your levels.** Game-memory slot `l4x` stores a level for every building, decoded as raw value + 1. The Town Hall decodes to exactly 16, which confirms the offset. Many of your defenses sit one level below the TH16 cap, and walls are mostly level 16.
  - `data/your-levels.json` holds these building levels plus your hero levels from the Clash API.
  - `Layout.levels`, `wall_level` and `hero_levels` carry an owner's levels, and the battle uses them.
  - TH16 base searches build every candidate with your levels.
- **Crafted Defenses.** The Crafting Station is a defense with three switchable modes: Cake-A-Pult, Hot Candle and Hero Hunter.
  - Each mode follows its wiki behaviour, with module levels capped by Town Hall (level 6 at TH16).
  - The registry now classifies all 13 Crafted Defense pages. The ten from past seasons are listed but not given weapons.
  - Your base has a Cake-A-Pult at (20,24); the memory slot confirms its position.
- **Scouting.** `evaluate.SCOUT = 2`: each attacker looks at two random sides and attacks the better one. Calibration uses the same rule.
  - Against the user's 13 logged ranked defenses (TH16 ×5, TH17 ×8), the sim gives 6.8 trophies, 60% three-starred and the Town Hall destroyed 85% of the time.
  - Reality: about 5 trophies, 77% and 85%.
  - Without scouting the sim gave 10.0 trophies and 46%; with best-of-3 it gave 1.6 trophies and 86%.
- **Calibration** after these changes: hydra 0.90, e-drag 0.77, throwers 1.09, root riders 1.23, all close to face value. The earlier 1.5–2.5× ground factors came from missing realism: drop holes, live deploy zones, scouting and illegal army sizes.

## Values the wiki doesn't state (marked `assumed` in code)

- Spell landing delay is 0.5 s. Poison reaches full damage after 4 s and does 50% to heroes.
- Trap fuse times: Bomb, Giant Bomb, Air Bomb, Seeking Mine and Giga Bomb 0.5 s; Spring Trap 0.3 s.
- Tornado pull strength. Giga Bomb knockback distance. Spring Trap stun of 1 s on oversized troops.
- Cooldowns for Spirit Fox and Diggy. Durations for Rage Vial and Electro Boots.
- Revenge Tower stage thresholds. Witch skeleton summon interval. Effect of the third and later Healer on one target.
- Clan Castle troops land with the main push (siege CC is released when the siege dies).

Each of these is a single constant, so a replay measurement can replace it directly.

## Fixes from the Codex cross-check of "assumed" constants (2026-10-15)
Codex (gpt-6.1-sol) checked all 32 constants marked "assumed" against the wiki (`local/research/audits/codex-assumed-audit.md`). Each fix below was verified in the local wiki copy (`data/wiki/pages`) before changing the engine.

| Constant | Was | Now | Source |
|---|---|---|---|
| Healer stacking per extra Healer | flat 50% past the 2nd | 100/100/90/90/70/40/10% (7 Healers = 5×) | Healer page |
| TH16 Giga Inferno | 150 DPS per target, beam slow 50% | 300 DPS per target (38.4/hit); the 50% slow is only the death poison | Giga Inferno (TH16) |
| Electro Boots | aura for 10 s after the ability | passive aura while the Champion is deployed | Electro Boots (Ability Type: Passive) |
| Bomb trigger delay | 0.5 s | 1.5 s | Bomb |
| Spirit Fox reapply cooldown | 10 s | 6 s | Spirit Fox |
| Lava Pup | 150 HP, 45 DPS, range 1, 2 tiles/s | 50 HP, 35 DPS, range 2, 4 tiles/s | Lava Pup |

**Not changed, unverified locally:**
- Revenge Tower stage thresholds (TH18 only).
- Spring Trap delay (Codex cites an Oct 2025 removal).
- Helper and B.O.B huts counting toward destruction.
- Super Barbarian rage, Super Minion long shots.
- Skeleton stats.

All of these are listed in the Codex audit file.

## 2026-10-18: fixes after the hole-free base failed in real attacks

Each item was checked against the local wiki copy (data/wiki/pages, fetched 2026-10-15) and, for stats, ClashKing game data. 3,699 unit and building numbers already matched the game data; the only mismatch, the Meteor Golem, is ClashKing's old temporary-troop version, and the wiki agrees with the engine.

| Mechanic | Before | Now | Source |
|---|---|---|---|
| Rocket Spear | extra damage only, normal 3-tile range | spears thrown from 10 tiles until the shots run out | Rocket Spear (Attack Range 10 tiles) |
| Unused hero ability on KO | hero just died | the ability fires automatically when the hero is about to be defeated (default setting) | Royal Champion; Phoenix |
| Fire Heart | exploded when the Phoenix revive ran out | explodes at the first fall only | Fire Heart |
| Phoenix | fought and could be hit from deployment | an invulnerable, untargetable egg until its hero's first KO, then both are invincible for the revive | Phoenix |
| Totem Spell | retargeted single-target defenses only | multi-target defenses and nearby defending troops retarget too (stun duration not stated, not modelled) | Totem Spell |
| Ruin Witch | walked to rubble and did nothing | vacuums 4 s, winds up 2 s, summons a Ruin Knight of her level; self-destructs after 10 | Ruin Witch; Ruin Knight |
| Giant Giant (Action Figure) | no rage | enrages at half health: +50% damage, +12 speed, 20 s | Giant Giant |

Inputs fixed the same day:
- The user's own armies (custom:user-*) now attack at the account's live levels (heroes, troops, spells, equipment, pets) from the API, not the Town Hall maximum. Their Dragon Duke is level 13.
- Bases are scored with technique choice (evaluate.techniques): on each scouted side the attacker plays the scripted plan or a hero charge with Invisibility + Recall (Queen with 4 Healers, Royal Champion, Dragon Duke), whichever pays best.

Still open (verified as gaps, numbers not on the wiki, so not guessed): Frosty's Frostmite slow, Totem landing stun duration, Giant Giant splash radius, Rocket Spear 0.8-tile splash.

## 2026-10-18 (later): category audits and patches

Thirteen Codex audits (local/research/audits/audit-*.md) compared every TH16-18 entity's wiki-stated mechanics with the engine: 710 findings, tracked in docs/audit-ledger.md. Each wiki quote a finding relies on is checked word for word against the local wiki copy (tools/baselab/verify_audit.py). Codex then drafted patches by category. Each was read in full before it was applied, and after it the wiki-fact checks (tools/baselab/mechanic_tests.py) and a sweep of every meta army and 35 layouts were run.

Applied so far: hero equipment (King, Queen, Warden, Champion, Prince, Duke), pets, heroes, traps, super troops, Elixir/Dark troops, siege machines, defenses. Fixes where the wiki gives no number are partial and say so in a comment. Nothing was guessed.

Problems caught in review and fixed by hand:
- Warden following: the patch used Warden Weights that the registry did not have, so every troop weighed 0 and the Warden would never follow. The weights now come from the wiki's Template:Warden_Weight (data/warden-weights.json, 13-tile vision, threshold 20, heroes 21, pets 3). The patch had also wrongly excluded heroes and pets.
- Inferno Dragon levels 11-12 raised an error (the wiki table repeats a row). They now use the game data's rows.
- Hook Tower raised an error on non-siege targets (reeling not modelled). It now damages and stuns without reeling.
- Root Riders walked through walls without breaking them: wall contact required the centre to sit inside the wall tile. Contact now starts at half a tile, so walls fall at the wiki's 0.8 s.
- Eagle Artillery crashed when its burst target was cleared mid-burst. It now retargets or ends the burst.
- Air Sweeper (older bug): target ties compared units directly and crashed. Fixed.
- Clan Castle cargo ordering missed an import. Fixed.

Rage is additive (wiki: "a level 1 Rage Spell do 130% more damage"), so the level-4 Super Valkyrie death Rage is x2.6.

## 2026-10-20: traps checked against game data v18.200.9

Every TH16-18 trap rule was checked against data/gamecsv/v18.200.9 first (Traps.csv, Projectiles.csv, Spells.csv for the Tornado, Characters/Heroes/Pets.csv for TriggersTraps and housing), then the wiki. Damage, trigger and damage radii, capacities, Seeking's 5-housing minimum, the Giga Bomb's 18-housing sum, hero (25) and pet (20) housing, Spring's highest-housing pick, 18-housing ejection and half damage to heroes/pets/sieges, projectile speeds and the Tornado pulses already matched. Spring at TH16 (level 11) ejects Throwers, Druids and Yetis (16-18 housing) and does 1,200 to Root Riders and bigger units (checked in a staged battle).

| Rule | Before | Now | Source |
|---|---|---|---|
| Giant Bomb / Giga Bomb delay | 0.5 s | 1.59 s / 1.63 s | Traps.csv ActionFrame 37/38, scaled by the Bomb's 35 frames = 1.5 s (wiki: Bomb) |
| Air Bomb / Seeking Air Mine opening | 0.5 s | 0.3 s | ActionFrame=7 |
| Tornado Trap start | instant | 0.34 s | ActionFrame=8 |
| Skeleton Trap spawn | instant, all at once | 0.6 s, then one every 0.15 s | SpawnInitialDelayMs=600, TimeBetweenSpawnsMs=150 |
| Units that cannot trigger traps | Yetimite only for Spring; Electromite, Firemite, Frostmite, Poison Lizard could trigger; Snake Bracelet snakes could not | all of these follow TriggersTraps | Characters.csv / Pets.csv TriggersTraps |
| Bomb / Giant Bomb knockback | flag only | housing 3 or less pushed 2 tiles | Pushback=100, PushbackHousingLimit=3, same as the Mortar (wiki: 2 tiles) |
| Giga Bomb knockback | retarget only | survivors thrown 2 tiles (sieges, Totem exempt) | RadialThrowDistance=200, RadialThrowRadius=450 |
| Tornado pull | 3 tiles/s divided by weight, to 0.3 tiles | TornadoForce 4/3/2/1/1 (ground), 5/4/3/2/1.5 (air) tiles/s by weight, 100% inside 0.7 tiles to 65% at the edge | Spells.csv Tornado Trap |
| Air Bomb on Dragon Duke | no trap reduction | 20% reduction | shells now count as trap damage |
| Trap damage label | stayed set after a trap fired | restored | later hits were credited to the trap |

Kept, with the reason in a code comment:
- Dragon Duke trap reduction 20%: game data says 50%, but the wiki history cuts it to 40% (May 26, 2026) and then 20% (July 14, 2026), so v18.200.9 is older.
- Giant Bomb level 12 (490 damage, 4.2 tiles) at TH18 is wiki-only; v18.200.9 stops at level 11.
- Spring delay 0.3 s and victim radius 1 tile: ActionFrame=5 (0.21 s) and EjectRadius=200 would stop any fast troop passing, which contradicts the wiki (speed 32+ passes). Still open (traps:F11).
- Not stated anywhere: the smaller push for 2-3 housing troops, Giga's longer throw for farther units, the Tornado's rotation and how its force combines with a unit's own walking, Spring's stun length (1 s assumed), Tornado field radius (trap DamageRadius 3 tiles is kept; the Tornado spell row says Radius=400).

Ledger: traps F3-F10, F12-F15, F18-F21, pets row426/518/519 applied; equipment-1:F13 (snakes) rejected by game data; F22-F26 deferred (event traps); F1, F2, F11, F16, F17, F27 open.

## 2026-10-20: scoring and check fixes (these change scores)

- **Attacker skill no longer depends on the side.** Each scenario seed picks one of five skill quantiles (`seed % 5`). The seed used to be `s * 7 + k` for side k, so the 8 sides of one scouting group were played at mixed skills, and "best of 2 sides" partly picked the stronger attacker instead of the weaker side. Now every side of a group has the same quantile; seeds are `5 * (s * n_sides + k) + q` (`evaluate._assign_skill`). The quantile varies between groups instead: each army's groups take a set symmetric around the median, and armies are placed (heaviest first) so the weighted quantile shares stay near 1/5 each. This applies to `meta_scenarios`, `ranked_scenarios`, `war_scenarios`, `target_scenarios` and `side_scenarios`, and to the scouting in `calibrate_meta.py` and `replay_log.py`.
  - The old seeds were not even either: `meta_scenarios(n_angles=2, seeds=(0,))` (the funnel and QD quick screens) played every attacker at the two lowest quantiles (mean z −0.90), and 8 angles × 1 seed at mean z −0.23. The new assignment gives mean z within ±0.07 of 0 for every set checked (single-seed sets with few armies cannot cover all quantiles evenly; use 5 seeds for that).
  - All results move, because every battle seed changed. The r7 calibration (`data/meta-calibration-r7.json`) was fitted with the coupled skills; refit it before comparing new scores with old ones.
- **No duplicate charge battles in playbook mode.** With `BASELAB_PLAYBOOKS=1`, `techniques()` returns only the plan for builds with a cited playbook (its charges are in its steps; `PlaybookPlan.setup_charge` is a no-op). `techniques_on=True` used to run 384 ranked battles per 8 angles where 136 were distinct.
- **Check 7 (`playbook_check.py`)** picks the side and flank on seeds 700-704 and scores the pick on seeds 800-809. Before, both used 700-703, which inflated the best-side rate and covered only skill quantiles 0-3.
- **`engine_coverage.py`** compares every spell, equipment piece and pet with the same battle without it; "ok" now means the end state changed.
