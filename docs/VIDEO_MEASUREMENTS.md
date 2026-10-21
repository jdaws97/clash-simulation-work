# Video measurements

## Traps and defenses

Measured from public YouTube attack footage (60 fps, frame by frame; the speed factor comes from the on-screen battle timer). Full samples are in `data/video-measurements-traps.json`. Only one item could be measured reliably; the others are marked not measured, with the reason in the JSON.

| item | engine value | measured (median, spread, n) | confidence | sources (video id @ time) |
|---|---|---|---|---|
| 9 Ice Golem death freeze, outer ring | uniform freeze | **The edge thaws ~1.0 s before the centre** (0.84-1.07 s, n=2 frame-checked + 1 automatic); edge/centre duration ratio ~0.90 (0.89-0.91); total ~9.3-9.7 s | low-medium | pHPMdLcXveY @ 1216.2, @ 199.3, @ 862.1 (auto); still: `docs/video-evidence/icegolem-freeze-pHPMdLcXveY-207.jpg` |
| 8 Freeze Spell, outer ring | uniform freeze | not measured (no clean single-spell sample). The game data already has it: `spells.csv` FreezeOuterTimeMS = 0.9 x FreezeTimeMS (L7: 5.5 s inner, 4.95 s outer) | game data, not video | - |
| 1 Bomb trigger -> blast | 1.5 s | not measured | - | - |
| 2 Giant Bomb trigger -> blast | 1.59 s | not measured (candidates hidden under spell effects or too small) | - | iK1yGLjF2Us @ ~820, aRUj8A45u4A @ 556 (unusable) |
| 3 Air Bomb / Seeking Air Mine trigger -> hit | 0.3 s | not measured | - | - |
| 4 Tornado Trap trigger -> first pull | 0.34 s | not measured (trigger frame not visible; effect unconfirmed) | - | pHPMdLcXveY @ 1205.8 (candidate) |
| 5 Spring Trap vs fast troops | within 1 tile | not measured | - | - |
| 6 Scattershot first shot / interval | instant, 3.2 s | not measured | - | - |
| 7 Air Sweeper puff angle / push | +-5 deg | not measured | - | ahiJ-bgdmSE @ ~251 (seen, not measured) |
| 13 Firespitter reach past target | 2 tiles | not measured | - | - |

Notes:
- The Ice Golem result fits the Freeze Spell's 90% outer-ring rule in the game data. The engine probably should use FreezeOuterTimeMS for the spell, and the same 0.9 ratio for the Ice Golem until better data exists.
- Why most items failed: the live-stream layouts show the game in a small window, cameras pan constantly, edited guides cut or slow down segments, and traps are invisible until they fire. Clean 60 fps defense replays with a static camera (shot list section A/B) are still needed for items 1-7 and 13.

## Troops and deploys

Measured from public YouTube attack footage at 60 fps (two clips at 30 fps), frame by frame. Every segment's speed was checked against the on-screen battle timer over >= 8 s, and all were 1.0x. Full samples are in `data/video-measurements-troops.json`.

| item | engine value | measured (median, spread, n) | confidence | sources (video id @ time) |
|---|---|---|---|---|
| 11 Deploy rate, holding a troop slot | 0.15 s per troop | **0.133 s per troop** (8 frames at 60 fps; intervals 7-9 frames; per-sample means 0.131-0.133 s; n=3 samples, 20 intervals) | high | dMcpXZ_wc8Q @ 124.05 (Super Yeti x6), w4RTiOi6C_w @ 88.4 (Super Yeti x7), w4RTiOi6C_w @ 183.15 (E-Drag x10) |
| 11 Spell drops, same slot | (0.15 s) | **0.133 s held** (EQ x8, median 8 frames); 0.17 s when tapped (Lightning x6); n=2 | medium | w4RTiOi6C_w @ 52.7, XtLqXV-ab6U @ 141.65 |
| 11 Slot switch | 0.6 s | not measured (set by the player's hand, varies widely) | - | - |
| 10 Melee arrival -> first hit | first hit on arrival | ~0.33 s (Super Yeti onto a cannon: crown stops advancing -> building HP bar appears), +-0.1 s, n=1 | low | AAawYGfV-AE @ 352.03 |
| 10 Ranged entering range -> first hit | first hit on arrival | not measured (10 overlapping E-Drags, cannot pair bolts with dragons) | - | XtLqXV-ab6U @ ~190 |
| 12 Battle Blimp at the TH | breaks over TH centre, no death blast | **Stops ~1-2 tiles outside the TH edge, not over the centre; area blast ~0.35 s after it stops** (~12 walls/buildings incl. the TH get HP bars in the same frame); CC troops out ~1.15 s after the blast. n=1 clean, 1 weak, 1 inconclusive | medium | XtLqXV-ab6U @ 174.45-175.95 (still: `docs/video-evidence/12-XtLqXV-ab6U-174.jpg`), w4RTiOi6C_w @ ~330.5 (weak), kCIDOAubL28 @ ~455 (inconclusive) |
| 14 Earthquake Boots activation -> first shock, interval | instant | not measured: in all 3 samples the boots fire inside a pile of yetis/spells with the camera moving | - | dMcpXZ_wc8Q @ 830.63, AAawYGfV-AE @ 379.37, yI1ZdPZswNM @ 358.0 |
| 15 Druid heal chain size | 4 | not measured (heal links unreadable at YouTube resolution) | - | dMcpXZ_wc8Q @ ~131, AAawYGfV-AE @ ~362 |
| 16 Wall Breaker next to a building | no damage | not measured (breakers not visible in zoomed-out footage) | - | dMcpXZ_wc8Q @ 974, JEM-kTBTmz4 @ ~507 |
| extra: Rocket Balloon burst, Super Barbarian rage | ~4 s / - | not observed cleanly | - | kCIDOAubL28 @ ~426-460 |

Notes:
- Deploy rate: 0.133 s per troop (8 game frames at 60 fps) held across two players and two troop types, with no drift. The engine's 0.15 s is about 13% slow.
- Battle Blimp: the game data agrees with the video. `data/gamecsv/v18.200.9/characters.csv` has Battle Blimp AttackRange 150 (1.5 tiles), DieDamage 700-1100, DieDamageRadius 300 (3 tiles), DieDamageDelay 700 ms. The engine's "over the TH centre, no death blast" looks wrong on both counts. The blimp's HP bar was still almost full at the blast, so it broke on reaching its target, not from defense fire.
- Melee arrival -> first hit: the one sample points to a ~0.3 s wind-up, but with n=1 in a crowded line it is not enough to change the engine.
- Items 14, 15 and 16 need clean, zoomed-in 60 fps recordings (shot list section B). Live-commentary and guide videos are too zoomed out and cluttered for them.
