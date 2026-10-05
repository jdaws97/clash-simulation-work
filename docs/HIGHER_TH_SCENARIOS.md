# Conditional complete TH17/TH18 scenarios

`tools/build_higher_th_example.py` assembles all placed objects in the pinned
TH17/18 inventory, with independently bound defensive troops and heroes.
Coordinates are synthetic packing fixtures. They are not creator bases, game
imports, optimized defenses, or replay calibration. This closes executable
scenario assembly for the supported configuration; it does not establish live
TH16-versus-TH18 attack strength.

```console
python -B tools/build_higher_th_example.py compile --town-hall 18 --mode ranked
```

Simulation reruns are pending the current runtime/performance investigation.
An exact-recipe progress runner on Windows CPython 3.12.14 exited with native
failure `0xC0000005` and no result. One bounded attempt after removing scheduled
background stack dumps stopped cooperatively without recurrence; it did not
complete a battle or establish the crash cause. See the source/input fingerprints
and limits in [the consolidated checkpoint](CONSOLIDATED_RECIPE_CHECKPOINT.md).
The following commands document the interface, not a verified mitigation:

```console
python -B tools/build_higher_th_example.py simulate --town-hall 18 --mode ranked --wall-timeout 480
python -B tools/build_higher_th_example.py simulate --town-hall 17 --mode cwl --wall-timeout 480
```

Each run writes input, account, army, layout, source/data fingerprints, a binding
summary, and (on completion) compressed full battle frames/trace plus outcome and
resource receipt under a unique attempt directory in `reports/higher-th/`.
An explicit `--output` must name a new directory; an existing destination is
rejected without overwriting any artifact. Each simulation invocation runs one child worker;
the wall deadline is enforced, with a distinct timeout record and nonzero exit.
Nonzero/native exits are recorded as failures without accepting a result.
Completion requires exit zero and a new worker receipt bound to the attempt ID,
worker PID, exact input hashes and engine/data fingerprint. A receipt from another
attempt cannot establish success. These reporting checks do not prove the native
failure has been fixed.
The 180-second battle cap is separate from the wall deadline. No game connection
or private account is used. The benchmark is 16 level-10 Dragons, three level-6
Rages and five level-7 Freezes: 320 troop housing and 11 spell housing. It
explicitly selects no attacking heroes, pets, siege, or attacking CC. Its fixed
deployment/spell plan is an engineering benchmark, not an army recommendation.
The synthetic account's selected mode/potion policy is resolved before resource
validation. Both example modes use modifier profile `none`, not an inferred
Ranked league bonus.

| Inventory/configuration | TH17 | TH18 |
| --- | --- | --- |
| Placed objects including walls, traps, banners | 469 | 546 |
| Walls | 325 | 400 |
| Remaining Cannon / Archer Tower | 0 / 2 | 0 / 2 |
| Ricochet / Multi-Archer / Multi-Gear | 3 / 3 / 1 | 3 / 3 / 1 |
| Wizard / Super Wizard | 5 / 0 | 2 / 2 |
| Firespitter / Revenge Tower | 2 / 0 | 2 / 1 |
| Town Hall | Inferno Artillery level 5 weapon | Passive Hall with selected Longshot |
| Crafting | Absent in pinned TH17 inventory | Explicit uncrafted passive Station |
| Defensive CC | 2 Dragons + 15 Archers, 55 housing | 2 Dragons + 15 Archers, 55 housing |

Counts, unlock caps, ordinary HP and per-hit weapon values come from
`data/catalog.json`, snapshot
[`c6967314d7281bb87c362993e2635e58cd77b351`](https://github.com/chiefpansancolt/clash-of-clans-data/tree/c6967314d7281bb87c362993e2635e58cd77b351).
The schema distinguishes original counts from `countAfterMerges`. Validation
checks full inventory and conserves the consumed parents: two Cannons per
Ricochet, two Archer Towers per Multi-Archer, one of each for Multi-Gear, and two
Wizard Towers per Super Wizard. Eagle count is zero. All fixture building levels
use their TH-specific snapshot caps **except TH18 Skeleton Traps, explicitly
level 4**. Level 5 requires absent level-2 Skeleton combat data and is rejected.
Selected defending King, Queen, Minion Prince and Royal Champion use their
TH-specific caps. Longshot is separately bound and excluded from destruction.
No TH16 defense stats are relabeled as TH18.

## Publisher evidence and experimental boundaries

The [TH17 release notes](https://supercell.com/en/games/clashofclans/blog/game-updates/the-town-hall-17-update-is-here-2/)
describe Eagle/Town Hall merging, always-active four-projectile artillery,
separate impact fields, and no Hall death bomb. The [Multi-Gear release](https://supercell.com/en/games/clashofclans/blog/news/get-geared-up-for-the-latest-update--3/)
identifies a geared Cannon and Archer Tower as its consumed parents.

The [TH18 release notes](https://supercell.com/en/games/clashofclans/blog/release-notes/town-hall-18-crash-lands-update/)
describe one selected Guardian, Wizard Tower merging, and Revenge Tower power/HP
increases as buildings fall. They also distinguish the Crafting Station from a
selected seasonal defense. The [28 January 2026 balance notes](https://supercell.com/en/games/clashofclans/blog/news/balance-changes-4/)
move Revenge phase-3/4 thresholds to 25/50 destroyed buildings and slow its final
cadence to 350 ms. Combined with the unchanged first threshold of five, this
supports thresholds `[5,25,50]`; it does not resolve the phase mapping or health
transition rule.

`revenge_towers.py` requires an explicit experimental contract. The catalog has
three weapon modes and empty normal stats, whereas the publisher describes four
phases. The selected fixture maps them to **dormant, stage1, stage2, stage3**;
this is a hypothesis. Initial dormancy is not claimed as a verified mechanic.
The caller supplies four HP multipliers; `[1,1.15,1.30,1.45]` is a sensitivity
fixture, not sourced game HP. The pinned extraction's base damage 50/60 conflict
remains recorded in `REVENGE_GAPS` and is not silently substituted.

The implemented lifecycle counts settled deaths of same-team counted structures,
excludes itself/walls/traps/units, applies all crossed thresholds once, preserves
remaining HP fraction, never revives a destroyed tower, and preserves unfinished
attack work excluding Freeze. The selected initial activation waits one complete
new-phase interval after existing Freeze. Released projectiles keep their launch
phase and survive source death. Two-/three-link ricochets use catalog damage
ratios and require explicit link distance/timing/tie/protection policies.
Phase transitions appear in the trace and frames; final state is under
`combat.multi_gear.revenge_towers`. Existing advanced-defense hooks own the
lifecycle, so this work does not change the shared movement/timeout kernel.

Selected current TH18 crafted defenses remain a full-village evaluation gap for
this particular example. Its uncrafted passive Station does not represent a
village with an active crafted weapon. Cake-A-Pult, Hero Hunter and Hot Candle
are now separately wired and paid-battle tested, including explicit TH11+ season
eligibility, module caps and shared clocks; see
[CRAFTED_SEASON_ACCESS.md](CRAFTED_SEASON_ACCESS.md). Independent shared-path
review is pending. The pinned catalog snapshot
`c6967314d7281bb87c362993e2635e58cd77b351` (retrieved 2026-10-03) lists twelve
variants; it marks Cake-A-Pult, Hero Hunter and Hot Candle `isCurrent=true` and
nine others historical. These flags do not verify the October 2026 live rotation.
Accepted selected-weapon inputs require the versioned variant/module selection,
explicit experimental behavior parameters, strict Station/module inventory and
ownership contract. Unsupported or incomplete selections fail closed. Unknown
identity or module levels in an opponent image stay unknown. No uncrafted
stand-in may be labelled representative current TH18 crafted coverage. This
profile-`none` engineering example also does not validate Legend I; see
[LEGEND_PROFILE_SCOPE.md](LEGEND_PROFILE_SCOPE.md).

Other inherited conditional policies remain material: Firespitter spread and
flight, artillery pool overlap, Guardian movement/emergence, Super Wizard fanout,
CC release, defense response, destruction scoring, and the six-tile deployment
margin. The source-linked policy JSON records the selected values. No current
season or current live patch is certified. Supercharges, selected crafted weapons,
Logger, and unsupported Skeleton summon levels fail explicitly. These choices
do not block the declared uncrafted/Longshot/level-4-trap fixture.

## Entered coordinates and integration

`--layout path.json` accepts the same full layout schema as the generated file,
with `higher_th_configuration.coordinate_provenance` set to
`{"kind":"entered_coordinates","source":"your-observation-reference"}`.
The input must describe a complete fully merged inventory; partial/under-merged
villages are outside this builder's contract. Per-building levels, modes, facing,
CC roster and hero/Guardian selections remain explicit. The builder preserves
coordinates with a documented +6/+6 simulation translation; it never invents
missing buildings, imports from a creator link, or drops unsupported entries.
For raw game coordinates, use an unpadded 44x44 layout rather than a generated
56x56 simulation-layout file. Additional supported combat configurations can
supply their own `higher_town_halls` policy entries through the Python API.

The numerical lead can combine these defenders with its complete TH16 package
after rebinding attacker-specific Giga Bomb responses, defensive-unit response
maps, and resource inventories. Do not reuse the 16-Dragon response weights for
a different army. Existing strict full-battle binding validates final membership.

Focused tests cover real inventory totals/merge parents, complete TH16 resource
binding, entered-coordinate preservation and unsupported choices, Revenge
thresholds/HP/Freeze/no-resurrection, and source-persistent three-link packets at
two solver steps. Run the repository suite with `python -B verify.py`.

## Recorded synthetic runs (4 October 2026)

Source worker engine/data fingerprint for these recorded benchmark runs:
`903f099d353026438bfab40177785a7d416a0397a9b97e0206cfea3e2f2bea49`.
Full inputs, source fingerprints, compressed traces and resource receipts are in
`reports/higher-th-final/` (generated, excluded from Git).

| TH16 benchmark matchup | Stars | Destruction | Battle end | Wall runtime |
| --- | --- | --- | --- | --- |
| TH17, CWL, modifier none | 1 | 52.6882% (49/93) | Troops exhausted at 47.8202 s | 116.250 s |
| TH18, Ranked, modifier none | 0 | 29.7872% (28/94) | Troops exhausted at 36.8593 s | 110.984 s |

Each run deployed all 16 paid Dragons, with no resource overflow. The TH18 trace
records Revenge transitions at 6.2104 s (five destroyed structures) and 26.5287 s
(25), and seven Revenge projectile launches. The Guardian remained dormant; this
attack did not enter its trigger area. Stage-four behavior is exercised by the
focused lifecycle test rather than this failed assault. These results are only
conditional fixture outcomes; they do not estimate a real player's chance to
score stars or validate army/base recommendations. Portable suite: 1,202 tests
passed. Black 24.10.0 checked all 231 Python files unchanged.

A later [selected crafted shared checkpoint](CRAFTED_SHARED_CHECKPOINT.md) adds
conditional paid TH18 family checks. The large benchmark above still selects an
uncrafted Station and has not been rerun or promoted as selected-variant coverage.

The [season access correction](CRAFTED_SEASON_ACCESS.md) also admits explicitly
selected seasonal Stations at TH11–18. The nonseasonal inventory constructor above
is a historical benchmark choice, not proof that a TH16/17 live base lacks its
seasonal Station. Its old results do not validate a current complete inventory.
