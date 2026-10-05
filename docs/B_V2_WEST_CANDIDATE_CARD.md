# B v2: prepared west funnel with Dragons and Balloons

**A conditional TH16 → TH18 Legend I candidate from our engine screen.** On the saved west-entry Hot Candle layout it scored **2 stars, 98.94%**. On the other saved TH18 layout from the east, it scored **0 stars, 47.87%**. This supports keeping the west package as a candidate; it does not establish a general TH18 winner or a player-ready recommendation.

The exact loadout is legal under the entered synthetic account and pinned catalog. Effective levels assume the declared Power/Hero potion profile; Jarod's available equipment, pets and donations still need confirmation. No potion use, purchases or game actions were performed.

## Exact loadout

| Resource | Tested selection |
|---|---|
| Owned troops — 320 housing | **15 Dragons level 11 + 4 Balloons level 11** |
| Owned spells — 11 housing | **3 Rage level 6 + 5 Freeze level 7** |
| Siege | **Stone Slammer level 5**, own siege |
| Castle troops — 50 housing | **2 Dragons level 13 + 2 Wizards level 14 + 2 Archers level 14** |
| Castle spells — 3 housing | **1 Rage level 7 + 1 Freeze level 8** |

| Hero | Equipment | Pet |
|---|---|---|
| Queen 95, ground | Invisibility Vial 7 + Magic Mirror 20 | Unicorn 10 |
| Warden 70, **air** | Eternal Tome 18 + Healing Tome 15 | Electro Owl 15 |
| Champion 45, ground | Rocket Spear 21 + Electro Boots 23 | Spirit Fox 10 |
| Dragon Duke 15, air | Revenge Deck 20 + Fire Heart 18 | Phoenix 10 |

The two preparation Dragons come out of the fifteen; **thirteen remain for the main wave**. Balloons are a paid entry screen, with no guarantee of intercepting traps. There are no reserved cleanup troops. The Slammer carries one Castle payload, released on its destruction; there is no second Castle deployment.

## Where the evidence applies

The tested entry is the west side of the saved **56 × 56 defense-0-hot-candle** layout. Smaller Y is north. An outer Army Camp at (6,6) and Gold Storage at (6,20) bracket the intended entry. The main wave enters between them, around Y=15.5. The named structure positions are footprint origins, not player target commands.

The entire defender inventory, traps, active Hot Candle, geometry and Legend I modifiers are fixed in the saved input. Both shoulders were destroyed before the scheduled commitment in this run. This is an observed condition, **not a sufficient rule for choosing an arbitrary base**: both shoulders also cleared in the failed east transfer.

## Tested deployment schedule

Times are seconds after the first troop, not the remaining attack-clock display. Coordinates apply only to the saved layout. Simultaneous shoulder placements and quarter-second deployment spacing are modeled timings; their sensitivity to manual tap timing has not been tested.

| Time | Action |
|---|---|
| 0 | One Dragon at **(1.5,7.5)** toward the upper Camp; one at **(1.5,21.5)** toward the lower Gold Storage. |
| 1 | Queen/Unicorn at **(1.5,9.5)**, supporting the upper flank. |
| 4 | Duke/Phoenix at **(1.5,23.5)**, supporting the lower flank. |
| 5 | Champion/Fox at **(1.5,21.5)**. Normal targeting decides the hero routes. |
| 18–18.75 | Four Balloons at X=1.5, Y=**14, 15, 16, 17**, one every 0.25 seconds. |
| 20 | Warden/Owl at **(1.5,15.5)**; begin the thirteen main Dragons. |
| 20–23 | Main Dragons at X=1.5, one every 0.25 seconds. Y sequence: **13.5, 14, 14.5, 15, 15.5, 16, 16.5, 17, 17.5, 13.5, 14, 14.5, 15**. |
| 21 | Slammer at **(1.5,15.5)**. |
| 27 | Warden ability if he is active. It no longer depends on one particular Dragon surviving. |

**Commitment stays on schedule even if the shoulders survive.** No automatic hold, reroute or same-force salvage was tested. If the preparation fails, this package can split or enter under more fire; its successful west result cannot be carried over to that situation.

Queen ability is allowed from 8 seconds when active and at or below **65% HP**; Champion from 9 seconds at the same threshold. They actually activated at **51.25s and 23.5s** in the west run. These are engine health gates sampled every 0.25 seconds. Using a visible “about two-thirds health” cue is a possible manual translation, **not the tested policy**. The Duke's selected equipment is passive in this model.

## Tested spell plan

Rage fields stay at these coordinates; they do not follow the army.

| Spell | Time / condition | Location |
|---|---|---|
| Owned Rage 1 | 23s | (9,16) |
| Owned Rage 2 | 35s | (18,17) |
| Donated Rage | 45s | (25,20) |
| Owned Rage 3 | 55s | (29,11) |
| Preparation Freeze | Earliest 12s, lower Gold Storage and Multi-Archer Tower 1 both alive | (7.5,24.5) |
| Core Freeze 1 | Earliest 24s, Firespitter 0 alive | (18.5,18.5) |
| Core Freeze 2 | Earliest 36s, Monolith 0 alive | (29.5,21.5) |
| Core Freeze 3 | Earliest 48s, Air Defense 0 alive | (44.5,7.5) |
| Core Freeze 4 | Earliest 60s, Hall alive | (33.5,7.5) |
| Donated Freeze | Earliest 30s, Hall alive and active Queen at/below 35% HP | (33.5,7.5) |

The donated Freeze condition is an imperfect proxy, not detection of Hall bait, invisibility or a threat to the Queen. It triggered at **54.75s** in the west run. The preparation Freeze stayed unused because the lower shoulder had already cleared. No automatic reassignment of an unused spell was tested.

## What worked and what failed

West: the Camp died at **1.75s** and Gold Storage at **9.63s**; the declared first targets matched. All 320 owned troop housing deployed, all three active hero abilities fired, and **13/14 spell housing** was spent. The Hall died at **61.44s**. One untouched Hidden Tesla remained at the end. **Only the Unicorn survived**, so the 180-second result is not evidence that a small timing adjustment would secure the third star. The lower preparation Dragon died at 4.2s; the whole attacking group, not that Dragon alone, completed its shoulder clearance.

East transfer: both shoulders cleared before 20s, but the preparation Dragons died at **1.22s and 4.83s**. The upper Dragon never launched a projectile, so it did not clear its named Air Defense. Champion, Duke and Queen died by **29.92s**; the entire force was exhausted at **68.62s**, leaving the Hall standing. This is a demonstrated entry/support failure, not proof that east entry alone is the cause: both layout and entry changed.

Keep this as the **west candidate**, with the exact entry and loadout attached. The batch does not establish a second recommended army: the Dragon/Minion funnel case remains unscored because of the Duke guard, and the simple control is a baseline. Confirm available gear, pets, potion assumptions and Castle donations before translating this into a manual attack plan. Real-battle calibration remains absent, and the engine's air-contact, targeting, splash and exact-state control assumptions still limit confidence.

Exact west input: `6465af880a2e0037d652cb671279ecbc46dcda99302f527765c71316ff05e9e0`.
Engine: `fc9d0b8`, unchanged across all five attempts. Input/result identities and evidence-archive hashes are recorded in the [deliverable manifest](../examples/reviewed-deliverable/manifest.json); the exact v2 input is in the [frozen screen package](../examples/army-input-screen/review-corrections-v2/README.md).
