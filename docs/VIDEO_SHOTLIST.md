# Friendly-challenge measurement shot list

Campaign plan, 2026-10-22. Build these small test areas in a spare layout, record
a challenge, then reuse the layout for the listed variants. Most runs need only
15–40 seconds of useful footage. Finish or surrender after the observation.
One person can deploy, record live, then record a zoomed replay of that attack.

Priorities follow [GAP_ANALYSIS.md §4](GAP_ANALYSIS.md#4-troop-and-defense-behaviour-the-engine-approximates-hm):
**H** can change the winning base; **M** can reverse close rankings; **L** is an
edge case. These are impact categories, not measured trophy effects. **H17+**
means high impact against attackers with that content, including attacks on a
TH16 base. Defenses requiring a higher defending TH are labelled separately.
Skip locked content; do not substitute a different mechanic for it.

Starting assumptions and file:line references are from the working Python engine
on 2026-10-22. Function names remain useful if lines move. Proposed setups are
experiments, not measurements or claims that the game follows the engine.
Bare Python filenames below mean `src/baselab/engine/<filename>`; tool paths
are relative to the repository root. Tile positions here exclude the engine's
3-tile world margin; add that margin when converting annotations to sim positions.

## Recording and layout conventions

- Use a saved test layout and the client's available friendly-challenge/practice
  flow. Prepare it before the session; respect any eligibility wait shown by the
  client. If that flow needs someone to post/accept the challenge, arrange that
  once. Recording and annotation need one person, without synchronized inputs.
- Coordinates use the editable **44 × 44 village**: `(0,0)` is its north corner,
  x/y follow the two grid edges. Building positions are **top-left tiles**.
  A 3 × 3 building at `(10,8)` has centre `(11.5,9.5)`. Walls/traps use occupied
  tiles; note the actual centre of multi-tile traps. Troop/spell drops are ground
  points. `(x,-1)` is one tile outside the north edge. Translate/rotate the whole
  rig around obstacles and save the actual positions.
- Park unused buildings, traps, hero banners and Builder Huts in the south half,
  preferably y ≥ 26; Town Hall far southeast unless specified. Fit everything
  into a valid layout. Keep unused long-range defenses as far away as possible.
  CC is empty except in CC shots. Check for stray shots and discard contaminated
  intervals. Keep deployed housing below Eagle activation except in 12d; do not
  deploy spare troops just to start the clock.
- Use actual owned levels. Record an overview and all relevant levels, modes,
  equipment, pets, boosts, game version/date and challenge modifiers before each
  change. No extra spells, pets, abilities or supporting troops. Keep hero gear
  fixed, avoid automatic low-HP activation, and record both equipment slots.
  Each **variant/repeat is a fresh challenge**, unless explicitly continuing
  the same attack. Siege/loadout/defending CC changes are separate runs.
- Record native **1×**, preferably **60 fps**, with timer and army bar visible.
  A phone's built-in recorder or a PC screen recorder is enough. Use touch
  indicators if available. Otherwise time from first visible troop/bottle, not
  an invented input frame. Record a zoomed replay pass for exits/projectiles/HP;
  keep the camera still during the event and avoid spell clutter.
- Map the isometric picture to tiles using wall centres/building corners. Track
  feet or ground-projected centres, not sprite tops; allow uncertainty for air
  shadows. Save both centre and building-edge distances. Separate trap boundary
  crossing, reveal, launch and HP loss. A hidden trigger yields a bound, not an
  exact time.
- `game_seconds = frame_gap / recording_fps × replay_speed`; check speed against
  ≥8 seconds of battle timer. Start with **3 runs/condition**, **5 for choice
  forks**. Keep every outcome; report n, median/range and frame/tile uncertainty.
  Use wider bounds at 30 fps. One observed choice cannot prove a hidden list size.
- Keep raw media and real profiles/layout details out of Git, for example under
  ignored `private/video-measurements/`. Name clips `01-targets-A-r01-1x.mp4`.
  Local notes: layout ID/positions, levels, variant, deploy/event frames, result,
  uncertainty and confounders. Only reviewed anonymized summaries belong in Git.
  Controlled challenges are real observations; simulated fixtures stay synthetic.

## Session order and layout reuse

| Family | Measurements captured together in one run | Priority / ranking consequence |
|---|---|---|
| 01 Target forks | Choice, route, arrival, first-hit phase; memory/reveal variants | H: compartment and funnel ordering; wind-up follow-up M |
| 02 Corridor/split | Crowding, contact, Warden choice and switch timing | H: splash/heal value and which push gets Warden support |
| 03 CC/siege lane | Exit order/spacing, defender crowding, cargo appearance/action | H: lure, Poison and siege delivery value |
| 04 Wall detour | Mounted route/jump threshold; optional Yak control | H17+: whether walls divert the King |
| 05 Trap lane | Trigger, effect, displacement and Tornado orbit | Tornado H; other traps M |
| 06 Spell/ice patch | Landing phases, freeze boundary and resumption | M: coverage and timing breakpoints |
| 07 Hero banner | Patrol, alert, acquisition, pursuit and return | M: defending hero placement |
| 08 Two-target tower | Multi-Archer allocation, replacement and flight | M: split entries/distractions |
| 09 Summon lane | Parent animation, child spawn/activation, pet following | M: early tanking and army assembly |
| 10 Healing/Poison | Druid links, Poison curve, Unicorn/Rage and slows | M: sustain and CC value |
| 11 Repair patch | Builder choice, persistence, travel and pulses | M: core building survival |
| 12 Firing range | New-target delays, travel, splash, log width/scatter | M; higher-TH extensions only if available |
| 13 Isolated stats | Conflicting level rows, defensive variants, early RC/Dragon | M in §4; diagnoses H calibration failures in §2 |
| 14 Whole attacks | Pacing, failures, finish times and paired A/B results | H in GAP_ANALYSIS §§2–3 |

This is a menu across sessions, not one oversized army. In a short session start
with five target-fork runs, three corridor/split runs, three CC runs and three
Tornado runs. Save ordinary failed defense replays whenever available.

## 01 — Target lists, memory, hidden Tesla and first-hit phase

**Build:** three 3 × 3 storages/collectors A `(10,8)`, B `(6,12)`, C `(14,12)`
inside a closed wall rectangle: x = 4 and 18, y = 6…16; y = 6 and 16, x = 5…17.
Four more 3 × 3 collectors D `(22,8)`, E `(22,12)`, F `(26,8)`, G `(26,12)`
are outside. Note each target's type/HP. No active defenses in the patch.

For the six-versus-seven candidate probe, move G to `(35,8)` and enclose A–F:
extend the inner rectangle's east wall to x = 30, keeping west x = 4 and
y = 6…16; add closed rectangles x = 2…32, y = 4…18 and x = 0…33, y = 2…20.
Each rectangle means wall tiles along its perimeter, not a filled area. Run
01a's single troop from the same drop with one, two, then three rings. This
puts six nearer targets behind walls and a seventh outside; record whether the
additional barrier cost ever produces a discriminating fork. If every condition
chooses A, report the list-size question unresolved rather than estimating a cap.

| Shot | Exact attack / variant | Record → measured output | Engine rule / constant |
|---|---|---|---|
| 01a **H** candidate list versus route cost | **1 P.E.K.K.A** at `(11.5,-1)`; fresh runs with **1 Barbarian**, then **1 Thrower**. Repeat with north-wall gaps of 1/3/5 tiles centred at x = 11. Closed-wall candidate controls park B/C, then restore them and park D/E/F, then restore all seven; A/G remain fixed. Mirror the rig after five repeats per fork. | First committed direction, first attacked wall/building, route length and contact time → choice frequencies versus candidate count/gap. Fit candidate-set and wall-penalty hypotheses jointly; these choices bracket a rule, not prove list size 3/6 alone. | `battle.py:1509` `_path_target`: cheapest route over every eligible building; fixed `WALL_COST["normal"]` at `battle.py:1518`. Tests missing `TARGET_LIST_SIZE`, `MAX_TARGET_LIST_SIZE` and refresh/noise rules. |
| 01b **H** original-target memory | Open variant: only A `(8,8)` and B `(20,8)` nearby. **1 P.E.K.K.A** at `(9.5,-1)`; after commitment cast **1 Invisibility** on A while troop is outside its circle. Fresh runs vary cast time; longer concealment uses **1 Overgrowth** instead. Log actual expiry and keep spell types separate. | Target/position before concealment, during diversion and when A returns → return-to-A rate versus absence time/distance, retarget latency and whether already attacking B changes it. | `battle.py:1265` drops untargetable buildings; `battle.py:1349` chooses afresh. No `REMEMBER_ORIGINAL_TARGET` / `FORGET_TARGET_TIME` model. |
| 01c **H** Tesla reveal scope | Same open patch, **1 Tesla `(14,6)`**. **1 P.E.K.K.A** toward each target at `(9.5,-1)` / `(21.5,-1)`; at +3 s **1 Giant `(15,-1)`** to reveal. Control parks Tesla. Repeat with Tesla 2 tiles into the observed approach. | Both P.E.K.K.A tracks before/after reveal → local/remote retarget frequency and latency, pre-reveal footprint detour. | `battle.py:274` setup footprint; `defense.py:525` `reveal_tesla` clears every attacker's target. Tests in-battle information scope, not the planner's preattack knowledge. |
| 01d **M** new-target wind-up/contact | Reuse open-gap 01a with **1 P.E.K.K.A**. Fresh **1 Dragon** run keeps only A nearby. Compare drops `(11.5,-1)` / `(11.5,-3)` and next-target transitions after a kill. | Deploy, move, range-entry/stop, animation, launch, HP-drop frames → deploy→launch, arrival→launch, flight and subsequent interval versus travel distance. | `units.py:1509` `new_target_windup` counts down during travel; `battle.py:1368` target-change application; `units.py:1460` centre-to-unit/edge-to-building contact. Old “first hit on arrival” premise is obsolete. |

## 02 — Crowding, collision and Warden grouping

**Corridor:** wall rails x = 9 and 14, y = 0…13, open ends; **Cannon `(10,15)`**.
**Split variant:** remove rails; Cannons `(6,10)` / `(18,10)`, storage `(12,3)`.

| Shot | Exact attack / variant | Record → measured output | Engine rule / constant |
|---|---|---|---|
| 02a **H** attacker collision | Hold **6 Giants** at `(11.5,-1)` into corridor; controls **1 Giant**, then **12 Barbarians**, fresh runs. Widen right rail to x = 16 and repeat. Translate entire rig 1 tile for a bucket-boundary control. | Ground tracks, number abreast, pair spacing, headways and first/last contact → spacing/contact radius in tiles, throughput in troops/s, queue delay versus solo, plus held-deploy spacing. | `battle.py:1137` `_separate`: housing-based radii, within-bucket attacker separation only; `units.py:1460` combat distance. |
| 02b **H** groups versus target votes | Split: **2 Giants `(7.5,-1)`**, **3 Giants `(19.5,-1)`**, then **ground Grand Warden `(13.5,-1)`** as both groups move; no ability. Repeat left count **1**, then **4**, right fixed at 3. Fresh 2-versus-3 run replaces Grand with **1 Apprentice Warden**. | Group centres, all targets, Warden path/first target and switches after Cannon death → group-choice rate by weight/distance, switch delay. Engine Giant weight 6, Grand threshold 20, Apprentice 10; nearby storage exposes independent targeting. | `units.py:166` `follow_target` votes by target within 13 tiles; `units.py:174` Apprentice override. Tests spatial `TargetGroupsRadius`, `TargetGroupsMinWeight`, `WARDEN_WAITS_FOR_GROUP_RETARGETING`. |
| 02c **H** radius and split targets | **4 Giants left / 3 right / ground Grand Warden** as above. Move right Cannon/drop together 4 tiles left, then 4 right in fresh layouts. Split-target variant replaces left Cannon with Cannons `(2,10)` / `(8,10)`, **2 Giants toward each**; right still 3. | Warden choice versus measured troop separation despite split building votes → group-radius bracket, weight threshold and wait interval. | Same `units.py:166`; distinguishes spatial clustering from per-building votes. |
| 02d **M** Heroic Torch speed | Widened corridor: **King without pet/Stick Horse**, **2 Giants**, then **ground Warden with Heroic Torch**, north entrance with 1-tile lateral offsets. Activate with all in aura on a clear walking segment. Fresh control repeats without activation. | ≥2 tiles of clear motion, aura entry/exit, recipient identity → added tiles/s separately for King/Giants and tail duration; compare added speed, not total-speed ratio. | `heroes.py:745` Torch binding; `heroes.py:1339` aura, especially `heroes.py:1355` half speed for other heroes versus ledger Round 4 `SpeedBoost2=9`. |

## 03 — Defending CC exits and siege/cargo delivery

**Build:** CC `(8,8)`, Cannon `(8,16)`; other defenses remote. Siege variants
park/empty defending CC, TH `(10,16)`, clear north approach. Fresh loadout per run.

| Shot | Exact attack / variant | Record → measured output | Engine rule / constant |
|---|---|---|---|
| 03a **H** CC cadence/order/position | Defending **10 Archers + 1 Wizard + 1 Giant + 1 Balloon + 1 Witch = 36 housing** if capacity allows; smaller control omits Witch, **24 housing**. Lure **2 Giants `(9.5,-1)`**, no Poison. Fresh air-gating run uses **1 Dragon** there. Mirror lane for direction control. | Entrant/trigger, every defender's first ground position and action, exit order and queue pauses → first-exit delay, inter-exit distribution, species order, offset from CC/facing, air/ground eligibility. | `battle.py:1183` `_castle`: fixed east offset `(x+1.5,y)`, **0.3 s** at `battle.py:1218`; `units.py:1017` `cargo_entries` ordering. |
| 03b **H** defender crowding/contact | Continue **same ground-lure attack**: once defenders emerge, **1 P.E.K.K.A `(9.5,-1)`**; no spells. | Defender pair tracks/overlap and engagement rings before deaths obscure them → spacing by species, surround time and attack distance. | `battle.py:1137` separates attackers only; `battle.py:1766` defender motion and `battle.py:1834` centre-distance attacks. |
| 03c **H** ordinary siege cargo | Attacking **1 Giant + 5 Archers = 10 housing**. **1 Wall Wrecker `(12,-1)`**, release near ground point `(12,6)`. Fresh run same cargo in **1 Blimp**, same release point. | Release tap if visible, break, blast, each passenger appearance/move/hit → release→first/last cargo, cadence/order, offsets/spread and activation delay. | `units.py:1083` `release_cc_at`: all at once on **0.6-tile ring**; `units.py:960` death release. |
| 03d **H** Blimp arrival/emergence | **1 Blimp + same 10-housing cargo**, let reach TH. Compare manual release and HP-death separately; HP-death variant adds **Air Defense `(16,8)`**. No spells on cargo; ≥3 clean runs per available cause. | Stop gap from TH edge, HP/cause of break, break→blast and blast→each passenger appearance/action → two separate delays, emergence cadence and positions. | `battle.py:1621` arrival; `specs.py:194` blast **3 tiles / 0.7 s**; `units.py:1083` no emergence delay. Ledger Round 4 **~1.15 s after blast** is one sample. “TH centre/no blast” is already fixed. |
| 03e **H** Wagon/Launcher delivery | If unlocked: Cannon `(10,14)`; **1 Giant `(11.5,-1)`** as forward target, **1 Sky Wagon `(11.5,-3)`**, same 10-housing cargo. Fresh run replaces Wagon with **1 Troop Launcher**. Record until cargo exhausted. | Launch/landing, native and CC passenger appearance, first action and order per delivery → separate native/cargo flight/activation times, delivery spacing/positions. | `units.py:1233` `launch_barrel`; `units.py:1305` Wagon cargo instant, versus delayed Launcher `units.py:1332` `barrel_impact`. |
| 03f **M** Siege Barracks by level | Storage `(10,16)` only nearby; **1 Siege Barracks `(12,-1)`**, same cargo, natural expiry. Repeat another machine level only if obtainable; note researched P.E.K.K.A/Wizard levels. | Every native exit/action, expiry and donated exit → startup, species/count, each interval by level, native-versus-CC phase. | `units.py:296` startup **0.5 s**; `units.py:546` uniform **30/14 s** cadence. Ledger Round 1 deferred. |

## 04 — Stick Horse detour preference

**Build:** storage `(10,12)`; wall bar x = 5…17, y = 7, open ends. No nearby
defenders/defenses. King only, no pet; keep second gear fixed, no extra ability.

| Shot | Exact attack / variant | Record → measured output | Engine rule / constant |
|---|---|---|---|
| 04a **H17+** walk versus jump | **King with Stick Horse `(11.5,-1)`**. Fresh bars x = 8…14, then 2…20. Each length: drops x = 8.5/11.5/14.5, y = -1. Unmounted control replaces Horse with fixed gear without a movement/wall effect in the measured interval. | Mounted route, walk-around/jump location, approach/jump/landing and expiry → excess open-route length at walk/jump threshold, jump time, choice rates. Measure from actual decision position. | `battle.py:1545` `wall_mode` makes mounted walls free; `battle.py:1477` bypasses route-cost selection in ignore mode. Tests nonzero jump penalty/open-route preference. |
| 04b **M** Yak speed | **King without Horse + Mighty Yak**, same drop/bar; fresh run parks bar for clear ≥4-tile walk. | Yak/King tracks separately, ram startup/second hit → Yak tiles/s and ram intervals, excluding follow stops. | `specs.py:418` `movement_speed` data binding; `pets.py:218` motion/ram reset, `pets.py:331` **0.5 s** startup. Ledger Round 1 CSV **3.0** versus wiki **2.5 tiles/s**. |

## 05 — Tornado dynamics and trap timing lanes

**Build one trap lane at a time:** Cannon `(9,18)`, trap centred as near as its
footprint allows to `(10.5,6.5)`. Photograph exact occupied tiles. Air runs swap
Cannon for Air Defense `(9,18)`. This separates trap motion from defensive fire;
Spring has its own closer-Cannon variant. Fresh challenges reset/rearm each trap.

| Shot | Exact attack / variant | Record → measured output | Engine rule / constant |
|---|---|---|---|
| 05a **H** Tornado dynamics/radius | **1 Tornado**; separate **1 Barbarian**, **1 Giant**, **1 Balloon**, **1 Blimp**, or **King without speed gear/pet** from `(10.5,-1)`. Radius probes drop x = 12.5/13.5/14.5. No-trap controls; wall variant adds rail x = 13, y = 3…10. | Reveal/first displacement, position every ~0.1 s, release → onset, radius bracket (**3 versus 4 tiles**), radial tiles/s/angular degrees/s by tier, duration, wall sticking. Use actual distance at onset and subtract normal movement; an inward walking track alone does not measure pull. | `traps.py:28` fuse; `traps.py:105` radius; `traps.py:67` force tiers; `traps.py:383` `tornado_tick`, assumed force→speed at `traps.py:426`, wall response `traps.py:446`. Tests unused `TornadoSpeedTowardsCenter`; rotation exists, dynamics remain open. |
| 05b **M** Bomb/Giant Bomb | Substitute **1 Bomb**, then **1 Giant Bomb**; **1 Giant** per run. Fresh **3 Barbarians** run measures push only if they survive. | Boundary crossing, reveal, blast/HP loss and surviving tracks → trigger→blast bounds, reveal→blast, radius/push distance. Fit frame conversion across multiple trap types. | `traps.py:28` `_FRAME_S=1.5/35`, `traps.py:29` `FUSE`, `traps.py:77` assumed **2-tile** push, `traps.py:197` effect. |
| 05c **M** Air Bomb/Seeking Mine | **1 air trap + 1 Balloon** from `(10.5,-1)`; repeat each with **1 Dragon**, lateral drop x = 13.5, and no-trap control. | Reveal→launch and launch→impact separately, missile/target paths → opening delay, flight speed, miss/track error. | `traps.py:33` opening fuse; `traps.py:216` Air Bomb fixed-location impact; `traps.py:362` Seeking Mine already steps homing flight. **0.3 s** is assumed opening, not total time to hit. |
| 05d **M** Spring eject radius/fast pass | Move Cannon to `(9,13)`, **1 Spring `(10,10)`** on approach. Separate **1 Giant**, **1 Hog Rider**, **1 Hog + 1 Haste** already active before crossing. Lateral drops x = 10.5/11.5/12.5, y = -1. Fresh **1 Miner** variant moves Spring to `(10,12)` beside its surfacing/attack point; use only visibly surfaced frames. | Reveal/action, victim position, eject/damage/stun and departure → delay, maximum ejection distance, outcome frequency versus actual speed, stun duration. Underground passage and stopping to attack are separate conditions, not evidence of speed bypass. | `traps.py:39` **0.3 s**; `traps.py:270` trigger-radius selection ignores CSV `EjectRadius=200`; `traps.py:295` assumed **1 s** stun. |
| 05e **M** Skeleton Trap activation | **1 ground Skeleton Trap + 1 Giant** along lane; fresh air-mode **1 Balloon** control. | Reveal, every skeleton appearance/move/hit → first delay, spawn cadence, spawn→active. | `traps.py:40` **0.6 s**; `traps.py:296` **0.15 s** stagger; `traps.py:337` positions. Activation control for 09. |
| 05f **M**, Giga Bomb if owned at TH17+ | Same quiet lane, **1 Giga Bomb**; hold **4 Giants** at `(10.5,-1)` so at least 18 housing enters together. Fresh **1 Golem** control. | Actual housing/positions at reveal, blast/HP loss and post-blast tracks → housing threshold, action delay and radial throw versus distance, including any airtime. A spread group below threshold is a failed trigger treatment. | `traps.py:32` inferred fuse; `traps.py:171` housing gate; `traps.py:245` displacement, fixed **2-tile** throw from `traps.py:80`. |

## 06 — Spell landing and freeze boundaries

**Build:** Cannons `(8,8)` / `(12,8)`; Ice Golem variant adds `(16,8)`.
CC/heroes/Builders remote. **1 Giant per Cannon**, drops `(9.5,-1)` / `(13.5,-1)`,
keeps both firing so their resumption is visible.

| Shot | Exact attack / variant | Record → measured output | Engine rule / constant |
|---|---|---|---|
| 06a **M** spell landing phases | First firing cycles: **1 Freeze `(9.5,8.5)`**. Fresh runs use **1 Lightning**, **1 Earthquake**, **1 Rage**, **1 Heal**, **1 Haste**, **1 Invisibility**, one spell per run at the engaged Giant/target as appropriate; log actual centre. | Touch marker if available, bottle appearance/landing, first status/HP event, pulses/expiry → per-spell deploy/effect/charge/hit offsets. Rage/Haste use rate/motion change; Heal uses injured Giant HP. | `spells.py:16` shared bottle `LAND_DELAY=0.5`; `spells.py:103` `cast_effect` (Revive is already an exception). Tests `DeployTimeMS`, `ChargingTimeMS`, `HitTimeMS` separately. |
| 06b **M** Freeze inclusion/outer duration | Reuse **same Freeze clip**; fresh casts shift centre **0.5 tile** toward second Cannon until just included/excluded. No-Freeze firing control. | Target centre/edge distances, freeze graphic onset/end and resumed firing → inclusion radius, inner/outer boundary bracket and duration by radius. Account for normal shot cooldown when using resumption as proxy. | `spells.py:138` unused outer band/time; `spells.py:631` uniform freeze. Local CSV L7 **5.5 s inner / 4.95 s outer** is a hypothesis for current footage, not a measured result. |
| 06c **M** Ice Golem outer duration | Fresh **1 Ice Golem `(9.5,-1)` + 1 Giant `(13.5,-1)`**, no Freeze. Let Cannons kill Golem. Repeat third Cannon `(18,8)` instead of `(16,8)`. | Death position/frame, affected centre/edge distances and thaw/resumption → offensive duration-versus-distance and boundary bracket. Do not transfer this duration to defending Ice Golems. | `units.py:799` death freeze; `units.py:809` uniform duration despite outer row. Earlier weak edge-thaw evidence in [VIDEO_MEASUREMENTS.md](VIDEO_MEASUREMENTS.md) does not establish a boundary or universal 0.9 factor. |

## 07 — Defending hero patrol, search, alert and leash

**Build:** one defending **King banner `(10,10)`**, storage `(10,17)`; other
banners/defenses/traps/CC remote. Note actual banner centre. Repeat with Queen,
Warden or flying heroes only if available/assigned, retaining their identities.

| Shot | Exact attack / variant | Record → measured output | Engine rule / constant |
|---|---|---|---|
| 07a **M** idle patrol | Start with **1 Archer `(35,-1)`** working remote collector `(34,8)`, outside test hero's search/alert. Record banner **20 s**. | Hero track relative to banner → patrol radius, speed, dwell and path/period; keep no-motion outcomes. | `battle.py:1823` returns directly home without patrol; `heroes.py:1438` home/leash setup. Tests `PatrolRadius=3` meaning. |
| 07b **M** search/alert/pursuit | Fresh **1 Giant `(11.5,-1)`** toward storage. Separate **1 Archer** runs from `(11.5,-3)`, `(11.5,-1)` and legal lateral points; fresh **1 P.E.K.K.A** sustains combat. After contact add **1 Archer** 6 tiles farther north, then one 6 tiles east; note actual legal points. | First alert/move/hit, distances from banner and opponents, furthest chase, switches/return → search/alert brackets, pursuit limit, retarget interval, return speed. Condition on initial patrol position. | `heroes.py:1449` King leash **7**/other search; `battle.py:1768` hard King clamp, `battle.py:1798` **0.5 s** retarget. Tests CSV search **10**, patrol **3**, alert **12** rather than one interchangeable radius. |

## 08 — Multi-Archer allocation and homing flight

**Build:** Multi-Archer Tower `(10,7)`, storages `(6,2)` / `(14,2)` as durable
attack stations inside its range. Other shooting defenses remote.

| Shot | Exact attack / variant | Record → measured output | Engine rule / constant |
|---|---|---|---|
| 08a **M** nearby/far-two allocation | **1 P.E.K.K.A `(7.5,-1)` + 1 P.E.K.K.A `(15.5,-1)`**; ≥6 volleys with exactly two in range. Fresh narrow layout moves stations/drops 2 tiles inward, wide 2 outward. Solo control uses left only; third-target run adds **1 Giant `(11.5,-1)`** after two volleys. | Each arrow's source/destination, positions and HP steps → three-arrow allocation sequence, separation cutoff bracket and replacement delay; count lost/unassigned arrows. | `defense.py:931` `_multi`; `defense.py:967` always alternates spare arrow for any pair. Tests absent far-two-target rule. |
| 08b **M** moving-target projectile ETA | Reuse **same clips before targets stop**. Fresh layout swaps tower for **Air Defense**, stations for **Cannons**, troops for **2 Balloons**; record a Balloon moving after a Cannon falls. Fresh ground version: **Archer Tower + 1 Hog Rider** between those Cannons. Optional Haste is a separate condition. | Projectile positions, launch/impact and target track → travelled path, flight time versus initial distance/target displacement, moving-versus-stationary residual. Reject unidentifiable arrows. | `defense.py:892` `_projectile` fixes impact time at launch; `units.py:1935` attacker ETA; `battle.py:1037` direct-hit target identity. Compare the stepped Seeking Mine `traps.py:362`. |

## 09 — Summon phases, activation and pet following

**Build:** storage `(10,12)` behind 04's open-ended wall bar; Cannon `(17,12)`
for a separate summon-kill/cap run. Initial lane has no defensive fire.

| Shot | Exact attack / variant | Record → measured output | Engine rule / constant |
|---|---|---|---|
| 09a **M** Witch/Super Witch | **1 Witch `(11.5,-1)`**, ≥25 s; fresh **1 Super Witch**. Replacement variant moves Cannon into summons' route so skeletons/Big Boy die; record next summon. | Parent animation/movement/attack pauses, every child spawn/move/hit, cap/replacement → initial delay, summon animation, spawn→active, cooldown origin and batch spread. | `units.py:307` Witch first **3 s**, Super Witch **4 s**; `units.py:497` instant Witch batch then **7 s**; `units.py:519` Big Boy. Tests `SummonTime` / `SpawnIdle`, not just cooldown. |
| 09b **M** pet deployment/leash | Fresh **King + Frosty**, **King + Sneezy**, **King + Mighty Yak**, no speed/wall gear/ability; `(11.5,-1)`. One no-pet control. Only owned pets. | Hero/pet appearance/activation, pet-child summons, separation on approach/stop/turn → spawn/activation delay, child phases, maximum follow separation and return threshold. | `heroes.py:227` immediate fixed-offset pet spawn; `pets.py:165` summons, `pets.py:218` move, `pets.py:25` owner/follow. Tests `SpawnDelay` / `LeashLength`. |
| 09c **M** spell/equipment summon controls | Storage-only lane: **1 Skeleton Spell**; fresh **1 Bat Spell** over remote Cannon `(17,12)`. Fresh **Queen with Archer Puppet**, no pet, activate once while attacking storage; fixed second gear without another summon. | Bottle/ability, first/later children and action, locations versus caster facing, parent pause → batch cadence, spread and spawn→active. | `spells.py:180` Skeleton/Bat schedules; `heroes.py:1161` `_puppet`; `battle.py:993` pending summons. Staged births exist; activation phase still needs checking. |

## 10 — Druid links, Poison ramp, Unicorn Rage and slow phase

Use only the specified active defense/CC, with all other healing, splash and
repair sources remote. Recipients must be visibly injured and distinguishable.

| Shot | Exact build and attack / variant | Record → measured output | Engine rule / constant |
|---|---|---|---|
| 10a **M** Druid recipient count | **Wizard Tower `(10,12)`**, **5 Giants** held `(11.5,-1)`, then **1 Druid** there after first splash injures group. Capture three pulses before transformation. | Each link/recipient HP increase with all five wounded → distinct total recipients (**3 versus 4**, primary counted separately), pulse/hop interval and heal amount. Full/dead/hidden recipients invalidate cap inference. | `specs.py:108` `chain=3` extras; `units.py:2568` selection, `units.py:2608` hop flight **12 tiles/s**. |
| 10b **M** Druid link distance | Cannons `(6,12)` / `(10,12)`; **1 Giant each**, x = 7.5/11.5, y = -1; once hurt **1 Druid `(7.5,-1)`**. Fresh right Cannon/drop shifts 1 tile toward/away: nominal 3/4/5-tile stations. | Actual centres at each pulse, primary, secondary injury, link/no-link → maximum distance bracket and eligibility. Refine near boundary with half-tile drops; building spacing is not recipient spacing. | `units.py:2571` / `units.py:2581` **3 tiles** versus `BattleDruidProjectile.MaxBounceDistance=450` (**4.5 tiles**). |
| 10c **M** Poison curve/stack/linger | CC `(8,8)` with **1 Dragon** only, Cannon `(8,16)`. **2 Giants `(9.5,-1)`** lure; add **4 Barbarians** there to hold Dragon's attention. **1 Poison** on stopped Dragon; these troops cannot damage air. Fresh stack **2 Poisons** one second apart; exit variant places **4 fresh Barbarians** beyond cloud after ~3 s, following after the current target dies. | HP fraction every 0.5 s from contact, attack/move, exit/last damage → normalized damage curve, ramp/plateau, linear/nonlinear fit, stack acceleration and linger/reset. Absolute DPS needs independently verified HP/modifiers; if it never exits, no linger result. | `spells.py:22` `POISON_RAMP=4`, `spells.py:21` linger **6 s**, `spells.py:1078` exposure/stacking. Attacking Poison is separate from Tower/TH poison, not automatically the same curve. |
| 10d **M** slow applied mid-cycle | Same lane, sole CC **1 Balloon**; lure **1 Giant**, no Archers. **1 Poison** immediately after visible bomb release; fresh cast just before next expected release; no-Poison control. | Launches and slow onset/expiry with target alive → remaining cycle versus elapsed fraction at slow onset, recovery phase. | `battle.py:1786` cooldown decreases in real time; `battle.py:1843` adds entire slowed next interval. Ledger Round 1 baked-in cooldown question. Attacking units under Poison Tower require a separate condition. |
| 10e **M** Unicorn under Rage | Cannon `(8,12)`; **King + Unicorn `(9.5,-1)`**, no ability/other healing gear. Injured King: **1 Rage** covering Unicorn only if their spacing permits; fresh both-covered run and no-Rage control. If separation fails retain both-covered result, attribution unresolved. | Identifiable pulse HP changes, concurrent Cannon hits, recipient/caster in Rage → heal amount/interval ratios, avoiding HP cap and accounting for damage. | `pets.py:269` pulse; `pets.py:284` amount has no Rage multiplier. Ledger Round 1 deferred; one pet avoids heal stacking. |

## 11 — Builder repair choice and persistence

**Build:** one active Hut `(10,10)`, Archer Tower A `(6,8)`, collector B `(14,8)`,
Cannon C `(10,15)`, all within nominal 7-tile repair reach by centre. Other Huts
remote. Save each building's level/HP first, including the test Hut: it can be
damaged and may itself be a repair candidate. Use these non-storage targets;
Earthquake does not provide the required storage damage.

| Shot | Exact attack / variant | Record → measured output | Engine rule / constant |
|---|---|---|---|
| 11a **M** initial choice/persistence | **1 Earthquake `(11,11)`** damages A/B/C and Hut together; compare fractional HP, absolute missing HP and travel distance. Fresh Hut moves 2 tiles toward A; another swaps A/B positions. If fractions tie, fresh **1 Lightning on B**, then **1 Earthquake** while Builder travels tests persistence instead; reject if B dies. | All damage fractions/frames, Builder exit/destination/path/first nail, switches when B worsens → priority rule, selection/travel latency, stickiness and repair pulse amount/interval. Keep ties explicit. | `defense.py:1262` `builders_tick`; `defense.py:1284` chooses lowest HP fraction only when old target unavailable; `defense.py:1295` reach **0.5**, `defense.py:1320` pulses **0.75 s**. |
| 11b **M** interruption/multiple Builders | Continue same run with **1 Freeze on Builder/Hut area** during repair. Fresh two-Hut layout adds Hut `(12,12)`, repeats one Earthquake; use mixed Hut levels if owned. | Target retained across freeze, individual Builder/nail/HP steps → resume delay and per-Builder marginal repair by level/order. Unreadable merged HP steps cannot establish stacking rate. | `defense.py:1232` `builder_spell`; `defense.py:1307` stacking weights assigned in builder-list order. |

## 12 — Defense delays, projectile geometry and scatter

**Reusable range:** test defense at `(10,12)` using its actual footprint. Others
remote. Unless specified, **1 Giant `(11.5,-1)`**, fresh **1 Golem** control if
Giant dies too soon. Photograph modes/facing; keep defense families separate.

| Shot | Exact attack / layout variant | Record → measured output | Engine rule / constant |
|---|---|---|---|
| 12a **M** Scattershot first/reacquired shot | **1 Scattershot + 1 Giant**, then **1 Giant `(17.5,-1)`** after first release. Solo **1 Golem** control for cadence; fresh **3 Barbarians** for a quick death followed by replacement Giant. | Range entry, lock/turn, release/impact, later releases/death/new lock → entry→release, flight, cadence, kill→new release. Visible lock is only an acquisition proxy. | `defense.py:396` omits new-target **2.2 s** / `CoolDownOverride=1.5 s`; `defense.py:1017` hits instantly. Tests first-only versus every-target delay. |
| 12b **M** Inferno target-pick delay | Separate **single/multi Inferno** runs. **1 Barbarian**, then **1 Giant** 0.5 s later at `(11.5,-1)`; annotate actual tap times. | Beam start, death and replacement damage per slot → kill→new damage and continuity of other beams. | `defense.py:712` single pick, `defense.py:931` multi refill omit `AlternatePickNewTargetDelay=50 ms`; need several clear 60 fps samples. |
| 12c **M** Sweeper prep/width/push | Sweeper faces north along lane; **5 Balloons**, x = 5.5/8.5/11.5/14.5/17.5, y = -1, toward **Cannon `(10,18)`**. Fresh Cannon `(10,10)` gives another puff radius. Solo **1 Balloon** lateral-drop runs probe sector edge. | Facing/aim, launch front, first push, hit/miss set and tracks → prep delay, width in tiles/degrees **at each radius**, wave speed, push distance/time and cadence. Actual Balloon positions govern. | `defense.py:1108` `_sweeper`: acquisition **±52.5°**, puff **±5°** at `defense.py:1145`, wave **6 tiles/s**; unmodelled `PrepareSpeed=600`, arc/expansion interpretation. |
| 12d **M** Eagle phases, layout with Eagle | Eagle `(10,18)`; **8 Dragons** in compact north line, then **2 Golems** there to cross recorded activation threshold. No spells, other defenses remote. Record first volley. | Housing threshold, wake, mark, each release/arrival/main/shock HP loss → wake/prep, shell gap, flight, arrival→damage including candidate **580 ms**. | `defense.py:1046` `_eagle` wake **1.125 s**, flight **5 s**; `defense.py:1075` phases lack explicit `DamageDelay=580`. Activation and target-lock are different origins. |
| 12e **M** X-Bow/Ricochet/Monolith travel | One defense per run, **1 Golem** baseline; fresh adds **1 Hog `(17.5,-1)`**. Ground X-Bow mode. | Release/path/HP steps at short/long distance → flight time versus distance, reacquisition and interval; unresolvable travel is a bound, not zero. | `defense.py:805` X-Bow fallback instant hit, `defense.py:806` Monolith, `defense.py:810` Ricochet; acquisition `defense.py:705`. |
| 12f **M** Mortar radial falloff | Mortar; **3 Giants**, x = 9.5/11.5/13.5, y = -1. First shell before dead zone; repeat spacing 1 and 3 tiles. | Impact centre, each Giant centre/HP decrement/push → damage ratio versus radius, push distance, flat versus **50% falloff**. Reject other damage sources. | `defense.py:910` `_mortar_shell` passes `falloff=True`; `battle.py:778` splash falloff. Ledger Round 1 says curve lacks evidence. |
| 12g **M** log width / Wall Breaker collateral | TH `(10,20)`, **Log Launcher `(12,-1)`**, collectors `(8,8)` / `(13,12)` with nearest edges 1 tile off nominal axis, wall rows x = 8…15, y = 6/16. Repeat drop x = 11.5/12.5, record actual heading toward TH. Separate **1 Wall Breaker `(12.5,-1)`** run uses closed wall rectangle x = 9…15, y = 8…14 enclosing collector `(11,9)` directly behind north wall; fresh **1 Super Wall Breaker** control if available. | Log/edge distances, hit/no-hit; WB arrival/death blast and building HP → log half-width bracket/travel speed and WB collateral amount/bound by blast phase. | `units.py:675` `advance_log`, **0.8** edge test `units.py:691` versus `PenetratingHitBoxWidth=30`; `units.py:786` WB death splash, `units.py:1762` spatial arrival strike. Old “WB never damages buildings” is not the current baseline. |
| 12h **M** Invisibility Tower lethal hit | Invis Tower `(10,10)`, collector `(7,10)`, storage `(13,10)` in coverage. **1 P.E.K.K.A `(8.5,-1)`** for nonlethal hits. Lethal-first-hit variant pre-damages collector with **1 Lightning**, waits for spell effect, then same troop; choose recorded levels giving remaining HP below one verified hit. Storage untouched. | Troop hit/death, tower cast, storage invisibility → trigger/no-trigger and latency by lethal/nonlethal hit; reject if pre-damage bound fails. | `battle.py:732` requires `b.hp > amount` except tower itself; `defense.py:1188` trigger processing. Spell pre-damage is not the trigger being tested. |
| 12i **M** aim scatter | Isolated Cannon `(10,14)`, **1 Flame Flinger `(11.5,-1)`**, no cargo/support. Fresh **1 Super Dragon** at same drop versus storage there. | ≥10 identified impact centres across repeats, launch aim/footprint; separate Flinger subshots from burn → scatter distribution in tiles and within-burst correlation. | `units.py:1935` `launch_projectile`, `units.py:1993` Flinger burst use deterministic target geometry; tests `TargetPosRandomRadius`. |
| 12j **M** Inferno Dragon killed-target pause | Collectors `(8,10)` / `(12,10)`, **1 Inferno Dragon `(9.5,-1)`**; fresh adds storage `(10,15)` for long beam. No defenses. | Beam stages, target death, new beam/damage, travel and new ramp → killed-target cooldown after accounting for range entry, reset/retained ramp. | `units.py:2418` `track_beam`, `units.py:2432` `_beam`, `units.py:1509` generic wind-up omit `TargetKilledCooldownTimer`. |

**Higher-TH defending extensions — only if the layout owns the defense:**

| Shot | Exact attack / layout variant | Record → measured output | Engine rule / constant |
|---|---|---|---|
| 12k **M** Inferno Artillery flight/burn, TH17/18 | TH `(10,16)` only active defense; **2 Golems `(10,-1)` / `(14,-1)`**, then **2 Giants** there one second later. Solo **1 Golem** control. | Four releases/destinations, impact/burn/first pulse and target tracks → flight, allocation, impact→burn and damage phase. | `defense.py:1323` `_inferno_artillery` applies damage/burn instantly. Ledger Round 1 deferred. |
| 12l **M** Firespitter burst/aim/reach, TH17+ | Firespitter faces north; **1 Golem `(11.5,-1)`**, **2 Giants** same approach at +1/+2 s. Fresh Giants 1 tile sideways; fresh **1 Haste** on moving targets. | Every ball release/first two victims, positions, flight and burst gaps → intra/inter-burst delay, flight/aim scatter, fixed aim versus tracking, reach past primary. Seek actual 0.5/1/2-tile trailing positions at impact; repeat drops until obtained. | `defense.py:1389` `_firespitter`; `defense.py:1431` assumed **2-tile** extra reach versus CSV **1**, `defense.py:1448` tracking despite `DontTrackTarget`, `defense.py:1450` burst clocks. Ledger Rounds 1/4. |

## 13 — Conflicting stats, defensive variants and early replay damage

Record levels/version/modifiers first. A current-client measurement applies to
that version; a difference from v18.200.9 can be a balance change. Do not adjust
a hidden timing rule to absorb a wrong level or unsupported content.

| Shot | Exact build and attack / variant | Record → measured output | Engine rule / constant |
|---|---|---|---|
| 13a **M** conflicting HP/DPS rows | Storage `(10,10)`, defenses/Builders/CC remote. **One troop per run:** Electro Dragon **L8 then L9**, Thrower **L3 then L4**, Super Bowler **L10**, Meteor Golem at recorded owned level. Only available levels; do not guess or silently substitute. Record troop's current in-game stat panel/boosts for HP. Meteor split variant adds **single Inferno `(16,10)`** to damage the parent while it attacks storage; record resulting children/merges separately. HP cross-check swaps storage for **1 Archer Tower**, counts isolated received hits while possible. | Storage HP steps, hit count/cadence/kill time, panel HP and received-hit count → DPH/DPS and displayed HP; incoming hits cross-check bounds, not exact HP unless troop dies to counted verified hits. A destroyed Tower or surviving troop gives a censored result. Keep parent/child/merge identity separate. | `specs.py:508` `unit_numbers`, `specs.py:553` DPS/DPH reconciliation, `stats.py:178` source precedence, `units.py:1135` split / `units.py:1145` merge. Ledger Round 1 conflicts; Druid heal row uses 10a. |
| 13b **M** defending troop variants | CC `(8,8)` with **1 Wizard**, no other firing defense/hero; **1 Giant `(9.5,-1)`** toward Cannon `(8,18)`. Count isolated Wizard hits before Cannon range. Fresh offensive **1 Wizard of same effective donated level** versus storage `(10,10)`. Repeat sole defending **1 Giant**, lure **1 P.E.K.K.A**. | Exit/first hit, interval, victim HP changes, effective donation level/modifiers → offense/defense DPH/interval ratios and HP bounds. Different recipients need known modifiers; raw kill times are not comparable. | `battle.py:1210` generic defender spawn; `units.py:253` has some explicit defensive overrides; `specs.py:508` otherwise shares attacker stats. Ledger Round 2 deferred. |
| 13c **M** early RC/Dragon excess damage | X-Bow `(10,10)`, single Inferno `(17,10)`; other defenses/CC/Builders remote. **1 RC without pet `(11.5,-1)`**, record before ability; fresh **1 Dragon** same drop. Repeat RC with exact maroon-machine replay gear levels if known, otherwise mark historical loadout unknown. Separate RC ability run records tap, animation, shield/spear releases and ordinary throws. | Entry, first target/hit, every hit/ability and building deaths → first X-Bow/Inferno kill time, damage source and first-shot phase. Compare with original replay's first 30 s, including Dragons on Eagle. | `units.py:1509` wind-up, `units.py:1935` flight, `heroes.py:756` Shield lock/release, `specs.py:508` numbers. BUG_LEDGER “Known, not fixed”: RC/Dragons kill early despite matching max-level base stats. An isolated run diagnoses mechanics, not unknown historical gear. |

## 14 — Whole attacks, pacing and real base ordering

Collect these alongside H controlled shots. They address
[SIM_ACCURACY.md](SIM_ACCURACY.md) checks 5–8 and GAP_ANALYSIS §§2–3;
mechanics clips alone cannot establish real base ordering or star/percent accuracy.

| Shot | Exact setup / recording | Measured output | Engine / evaluation rule |
|---|---|---|---|
| 14a **H** held-out defenses/times | Save **10 complete real defense replays** initially: aim for **3 ground, 3 air, 2 failed/partial, 2 timeouts**; categories may overlap. If unavailable, keep actual distribution, continue toward **≥40 defenses**. Record start→result, army/equipment levels, deployment bar, defending CC/heroes and exact dated layout snapshot. Prioritize a ground failure over another fast Dragon triple. | Deploy/cast/ability times/coordinates, first engagements/deaths, 30/60/90 s destruction, star transitions, finish/timeout and result. Against frozen predictions: destruction error, finish-time ratio and Brier versus average baseline, by TH/army. | `battle.py:911` event order, `plans.py:624` drop scheduling; `tools/baselab/replay_log.py` validation. Preserve held-out data rule; GAP_ANALYSIS's known full Dragon replay is ~14 s fast in sim. |
| 14b **H** real assembly pacing | Your normal saved base, **one actual army you play**, exact counts/levels/full loadout recorded. **3 challenges with identical army**, normal manual play, no imposed pauses. Include held troop line and hero/siege/spell sequence only if part of that army. Live bar/touch markers in frame. | Held-drop spacing, switches, tank→damage→hero/siege gaps, spell/ability decisions, funnel repair/cleanup start → distributions by action type. Separate measured ~**0.133 s** held spacing from human decision gaps. | `plans.py:624` `_drop`, `tools/baselab/step_gaps.py` narration-derived gaps, `battle.py:920` scheduling. Old **0.15 s** deploy assumption is obsolete; do not fit one universal pacing constant. |
| 14c **H** paired base rankings | Freeze **two buildable finalists A/B**, same levels, CC, hero assignment and modes. Use **one exact ground army and one exact air army** from 14b; **5 attacks per army per layout**, alternating A/B and reversing first layout each pair. Save entry/action deviations and full results. Keep pairs out of fitting; fresh pairs after any engine tune. | Paired stars/percent, survivors/time, trophies only if that mode supplies them → ranking direction and paired spread by army. Record practice/order effects. Twenty FCs do not reproduce ranked opponent mix; later alternate committed ranked finalists across comparable exposures with all snapshots/defenses saved. | SIM_ACCURACY check 7 and `tools/baselab/adaptive_check.py`; GAP_ANALYSIS §2 missing real A/B. Holds army/levels fixed to isolate layout while retaining manual variation. |
| 14d **M** numerical phase/order diagnostic | Reuse clean solo 01d/12a exchanges, **3 repeats**, no support, through death of either side; do not hand-time a supposed simultaneous duel. | Both release/impact/death frames, whether released hits land after shooter dies → bounded event ordering and video-versus-frozen-trace residuals. | `battle.py:33` default **0.1 s** DT, `battle.py:930` pending effects, `battle.py:940` attackers before defenses. Footage can falsify resulting ordering, not identify internal game tick. Half-DT convergence is a separate synthetic check. |

## Deferred items that should not consume a recording session

- BUG_LEDGER Round 2 **calibrated strength for pets/equipment summons** is a
  simulator consistency issue: real troops have no synthetic strength knob.
  Use 09/13 for real baseline behavior, then synthetic inheritance checks at
  `heroes.py:227` pet spawn / `heroes.py:1161` puppet spawn. Do not label synthetic
  multiplier tests real-game calibration.
- Round 2 **predictor_proof seed grouping** is repo-only
  (`tools/baselab/predictor_proof.py`); video cannot settle `seed % 5` grouping.
- GAP_ANALYSIS **plan-level hidden-Tesla knowledge**, seasonal-content rejection,
  absent event effects, search controls and unsupported Rust paths need code/data
  work. 01c covers in-battle reveal only. Preserve the v29 engine and explicit
  unsupported-content checks while measurements remain pending.
- §4 **L** items (Miner hide randomness, Hero Hunter/Cake-A-Pult phases, Meteor
  merge immunity, event traps) follow H/M. Save an incidental clean clip with
  levels/positions if owned/relevant; otherwise leave explicitly unmeasured.
  The core campaign does not require event content or a higher defending TH.
- Earthquake Boots and held-drop spacing already have corrections. For a spare
  Boots check reuse 04's storage/wall patch with **King + Earthquake Boots, no
  pet/other damage ability**, activate once next to the bar: record activation,
  first and all five shock/HP frames → first-hit delay and four inter-hit gaps
  (`heroes.py:923` `_boots_quake_hit`, five pulses **400 ms** apart). This replaces
  the old “instant” premise; no special layout is needed. Blimp blast existence
  and log travel similarly check implemented rules; emergence/width remain open.

Before fitting an engine change, retain a clean clip outside the fitting set and
replay the chosen rule against it. Mark every shot measured, ambiguous or
unavailable; unreadable bars/hidden triggers are not zero delays. Then rerun
paired rankings for affected layouts/armies, keeping real-defense holdout separate
from calibration.
