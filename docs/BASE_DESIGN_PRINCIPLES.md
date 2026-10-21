# TH16 base design principles: trapping the TH16–TH18 meta

Research compiled 2026-10-20 for the ranked (Legend) and war base search. Read-only research: no code was changed.

## How to read this

- **Source quality.** Strongest: the game data in `data/gamecsv/v18.200.9` (G), the local wiki mirror (W), and Supercell posts (S). Next: named-builder write-ups on Blueprint CoC (B; Sawan, Pekkachu, Krispy, Ninj, Trottino, Ghost) and TrophyCoach guides and data (T). Weak: SEO and base-selling blogs: cocbasedrop (C), BoostRoom (R), AllClash (A). C contains at least one invented mechanic (see Contested). Blueprint sells bases, so its claims about results are marketing. Its descriptions of *what a builder did* are still useful evidence of practice.
- **Confidence** counts independent source families. G and W count as one "mechanics" family when W restates G.
- **Sim use** is either a **generator rule** (a hard or soft constraint during layout generation) or a **measurable test** (a score computed from simulated battles).
- Reddit could not be fetched directly. Reddit items come from a Codex lead and are marked unverified.

### TH16 numbers used throughout (game data v18.200.9 plus project catalog)

| Item at TH16 | Count | Key stats (tiles) |
|---|---|---|
| Spring Trap L11 | 9 | Trigger 1.0. Hits the single largest-housing troop in radius. Launches troops of 18 housing or less. Others take 1,200 damage plus pushback. Heroes take half. |
| Giant Bomb L10 | 7 | Trigger 2.0, radius 4.0, 450 damage |
| Bomb L12 | 8 | Trigger 1.5, radius 3.0, 170 damage |
| Seeking Air Mine L6 | 8 | Trigger 4.0, 3,000 damage to one air unit of 5+ housing |
| Air Bomb L11 | 7 | Trigger 4.0, radius 3.0, 375 damage |
| Skeleton Trap | 4 | Trigger 5.0, 5 skeletons, ground or air mode |
| Tornado Trap | 1 | Trigger 3.0, pull radius 3.0, 7 s |
| Giga Bomb | 0 | TH17+ only. Visible. Needs 18 housing within 3.5 tiles to trigger. |

Relevant attackers (max level): Healer 14 housing, 2,100 HP. Thrower 16 housing, 2,800 HP, range 6. Druid 16 housing, range 5. Root Rider 20 housing, 6,500 HP. Dragon 5,700 HP. Electro Dragon 6,700 HP. Dragon Rider 6,200 HP.

Equipment geometry:
- **Fireball:** splash radius 4 tiles (L1–8), 5 (L9–23), 6 (L24+) (G). Prima Games' "6 at L18" is wrong.
- **Rocket Spear:** range 10 tiles, aimed at the closest defense (W).
- **Overgrowth:** radius 6 (W).

The Spring Trap behavior above is the October 6 2025 rework (S, [Supercell](https://supercell.com/en/games/clashofclans/blog/release-notes/get-ready-for-ranked-update/)). Pre-October-2025 spring advice is outdated.

---

## 1. The attack meta and how each attack picks its side

**Meta shares.** These are TrophyCoach ranked data for TH18, already in `docs/RESEARCH-2026-10.md`:

| Army | Share | 3★ rate |
|---|---|---|
| Mass Dragons / Hydra | 27% | 44.6% |
| Mass Throwers (+ Healers) | 26% | 54.3% |
| E-Drag spam | 11.5% | 22% |
| Root Rider | 10% | 41.4% |
| Super Bowler | 6% | 56% |
| Super Yeti | 4% | 50.9% |
| Meteor Golem | 2% | 40.7% |

Supercell's [July 9 2026 balance post](https://supercell.com/en/games/clashofclans/blog/news/july-balance-update) confirms that Dragon armies (about 20%) and Throwers with Healers are the top two war armies, about 40% together. Your own log matches: Throwers, Hydra and E-Drags, with Duke and RC in most attacks.

**1.1 Attackers scout one side, not the whole base.**
- TrophyCoach says to count point defenses on the entry side only. Then trace the hero's nearest-building chain from the entry: if it runs into the core, the side works. If it runs along the ring, the funnel is not good enough. ([queen charge guide](https://trophycoach.com/clash-of-clans/guides/queen-charge-guide))
- Its war guide scouts four things: TH location, the side where the Inferno/Eagle/Scattershot/Monolith cluster is thinnest, Air Defense and Sweeper coverage (for air), and **open tiles that look like trap spots** ([guide](https://trophycoach.com/clash-of-clans/guides/how-to-three-star-in-war)).
- A Hydra guide lists the same four checks and says to switch sides if a side fails them ([C](https://cocbasedrop.com/blog/dragon-rider-army-guide-coc-2026-hydra)).
- Confidence: medium (T, C).
- *Sim use:* model the attacker's side choice explicitly. For each of 8–16 entry sectors, compute a scouting score: point-defense HP and DPS within about 12 tiles of the entry, visible empty 1×1 and 2×2 tiles, Sweeper facing, and AD spread. Let the attacker pick the best sector with softmax noise. Score a base by the defender result **on the sector attackers would actually choose**, not the average over sectors.

**1.2 Each meta attack needs something specific.**

| Attack | Side and target logic | What it needs from your base |
|---|---|---|
| **Root Riders + RC/Warden charge** | Root Riders target defenses only and walk over walls; walls of L14–17 hold them about 0.8 s (W). An activated TH weapon counts as a defense; the CC does not (W). The RC charge exists to "create pathing" into a route ([B, Ninj RR guide](https://blueprintcoc.com/blogs/coc-attack-strategies/ninj-root-riders-army-pro-tips)). | A defense-to-defense chain from the entry into the core, and Healers alive. |
| **Fireball Warden walk** | Fireball always hits the **closest defense, at any distance** (W). Attackers Invisibility the front defenses so the "closest" one becomes the cluster they want (W). | A cluster of valuable defenses within radius 5–6 of a defense that can be made the closest. |
| **RC with Rocket Spear** | Throws at the closest defense from 10 tiles. She cannot outrange X-Bows, Mortars, an **active** Eagle, or the Monolith (range 11) (W). | Outer defenses not covered by 11+ range defenses. |
| **Duke Rocket Backpack** | Flies a straight line **through the base center** to the far edge. He is untargetable, triggers no traps and no CC, but still triggers Hidden Teslas and takes Poison Tower damage (W; [B](https://blueprintcoc.com/blogs/clash-of-clans-guides/rocket-backpack-equipment-guide)). | Valuable buildings on a line through the center. |
| **Queen Giant Arrow** | Straight line through her current target. Since May 2026 it does double damage to Air Defenses with lower base damage ([S](https://supercell.com/en/games/clashofclans/blog/news/state-of-gameplay-part-2/)). | Air Defenses (and Sweepers) in a line. |
| **Hydra / Dragons** | Commit to one lane with funnels on both edges, kill ADs with Arrow or Lightning, Overgrowth the core ([C](https://cocbasedrop.com/blog/dragon-rider-army-guide-coc-2026-hydra); Codex lead: Trottino's guide on B). | ADs reachable from one lane, and no Seeking Air Mine stack on that lane. |
| **Electro Dragons** | The chain jumps only across gaps of 1 tile or less, and prefers the highest-HP building (W). Guides say to avoid spread bases (C; Codex lead: B TH18 army guide). | Dense clusters, ADs zapped first. |
| **Throwers + Healers** | Throwers hit the nearest building from 6 tiles and hit air too (G/W). Ninj starts from a corner, uses Duke on one flank and Queen on the other, removes a Rage Tower early, and Totems the Lava Launcher ([B](https://blueprintcoc.com/blogs/coc-attack-strategies/ninj-backpack-throwers-pro-tips)). | A funnel to the core, and Healers alive. |
| **Super Bowler smash** | Flame Flinger on one side, Warden walk on the other (Codex lead: Trottino on B, unverified). Weak to Monolith, Ricochet and single-target Inferno (W). | Flank clearance and Healer access. |
| **Lavaloon** | Hounds tank the ADs, Balloons hit defenses (W). | Clustered ADs. |

*Sim use:* the per-attack "needs" in the last column are the features the design rules below try to deny. Each row should exist as a scripted opener in the attacker library, with real-player playbooks per `docs/playbook-*.md`.

---

## 2. Anti-strategy design rules

**2.1 Keep the Eagle out of reach of any opener.**
- *Rule:* no opener of fewer than 200 housing should be able to reach the Eagle Artillery. The Eagle stays dormant until 200 housing is deployed; each hero counts 25 and each spell housing counts 5 (W, Eagle_Artillery). A 4-hero charge with 5 Healers plus a few spells is about 170–190, so an exposed Eagle dies **before it ever fires**. Rocket Spear "cannot be outranged" only by an *activated* Eagle (W).
- *Counters:* RC/Queen/Warden charges, Root Rider entries, Rocket Spear sniping.
- *Confidence:* high on the mechanism (W). The design rule is supported by the wiki ("centralize the Eagle", "keep it away from your Queen and CC") and by your real result.
- *Your loss:* the hole-free base lost every time from the exposed-Eagle side. Attackers picked the side where the most valuable defense was cheapest. That matches 1.1 exactly.
- *Sim use (test):* the **opener-survival test**. From every sector, run each meta opener (RC Spear charge, Queen Arrow charge, Fireball walk, Duke Backpack, a Root Rider spearhead of 3–4 Riders) with deployed housing capped at 199. Fail or penalize the base if the Eagle, the Monolith, or two or more Infernos/ADs die. *Generator rule:* the Eagle must be at least 2 compartments from every edge, and not among the first 4 defenses on the defense-targeting chain from any sector.

**2.2 Choose the "closest defense" from each side.**
- *Rule:* from every deploy edge, the closest defense should be a low-value one (a Mortar, Air Sweeper, Bomb Tower or Archer Tower). Its 6-tile Fireball disk should contain no other high-value defense. Put "worse defenses outside and others one tile back, so the attacker can't tell which is closer" (W, Fireball). Space Infernos at least 6 tiles apart ([C](https://cocbasedrop.com/blog/best-th16-war-base-layout-2026-anti-root-rider)). A Hidden Tesla near where the Warden is deployed disrupts the plan (W).
- *Counters:* Fireball walk, Rocket Spear sniping, Seeking Shield.
- *Confidence:* medium-high (W, C, plus B's Sawan design below).
- *Sim use (test):* for each deploy tile, find the closest defense, center a radius-6 disk on it, and sum the value-weighted HP of high-value defenses inside (for a 3×3 building, its center must be more than 7.5 tiles away to escape). Minimize the **maximum** over deploy tiles, not the mean. *Generator rule:* high-value pairs (Inferno, Eagle, Monolith, Scattershot, Multi-Archer, Ricochet) keep 7.5+ tiles between centers, except deliberate pairs inside a trap zone (see 4.2).

**2.3 No two Air Defenses on one Giant Arrow line, and no valuable line through the center.**
- *Rule:* keep Air Defenses non-collinear and slightly askew ("askew defenses confuse the arrow", W). Spread them so one Lightning/EQ set or one Freeze can't take two (W, Dragon).
- Since the Backpack always passes through the center (W, B), no line through the center should cross more than one of Eagle, AD, Sweeper, Monolith or Spell Tower within the dash corridor. Blueprint's TH18 war analysis names misaligned key buildings as its Backpack+Arrow defense (Codex lead, B, unverified page).
- *Counters:* Hydra, Dragons, Lavaloon openers, Duke Backpack.
- *Confidence:* high on the mechanism (W, S). Arrow corridor width is **unverified**.
- *Sim use (generator rule):* for every AD pair, the perpendicular distance from any third AD to their line must be more than 1.5 tiles (conservative width). Separately, for each of 32 center lines, count high-value buildings within 1.5 tiles. Penalize the maximum count. Verify the arrow and backpack widths in-engine against wiki images or replays.

**2.4 Spell-coverage limits.**
- *Rule:* no Overgrowth disk (radius 6) should cover more than two top-tier defenses. Don't group the Eagle with Scattershots, X-Bows or Infernos, because ZapQuake or Overgrowth takes all of them (W, Eagle, Scattershot, Inferno pages).
- *Counters:* every Overgrowth/Freeze/Totem army; Hydra and Root Riders use Overgrowth on the core ([B](https://blueprintcoc.com/blogs/coc-attack-strategies/ninj-root-riders-army-pro-tips); C).
- *Confidence:* high (W).
- *Sim use (test):* compute the maximum number of top-tier defenses inside any radius-6 disk (search over a grid of disk centers). Use it as a hard cap of 2.

**2.5 Spacing against chains.**
- *Rule:* leave 2+ tile gaps around high-value buildings so Electro Dragon chains and Super Yeti electromites can't jump (W, E-Drag and Super Yeti pages). Storages next to an Air Sweeper or AD act as "lightning rods", because the chain prefers the highest-HP building (W).
- *Counters:* E-Drag (11.5%), Super Yeti (4%).
- *Confidence:* high (W, consistent with C).
- *Sim use (generator rule):* a soft penalty for each pair of buildings with a gap of 1 tile or less, weighted by value. Reward a storage sitting within 1 tile of an AD or Sweeper while the AD keeps a 2+ tile gap from other defenses.

**2.6 Cover outer defenses with long range.**
- *Rule:* every outer defense should sit within range of an X-Bow set to ground (14 tiles) or the Monolith (11), so RC Rocket Spear sniping from 10 tiles gets punished (W, Rocket Spear: "the best defense ... is the X-Bow"). Pair the Monolith and single-target Infernos with splash, so swarms can't stall them (W, Monolith).
- *Counters:* RC Spear, Queen charges, Root Riders (high HP, so Monolith percentage damage hurts them).
- *Confidence:* medium (W only, but mechanical).
- *Sim use (test):* for each outer defense, find the 10-tile Spear standing positions and check whether some 11+ range defense covers them. Score the fraction covered.

**2.7 Spell Tower modes by matchup.**
- *Rule:* Poison is good against Root Riders and swarms, but the wiki says to swap it out against Throwers, Super Bowlers, Super Yetis and heroes, and it does nothing to air. Rage boosts the Eagle, Multi-Archer, X-Bow and CC troops, but not the Monolith's percentage bonus. Invisibility protects targets that have a time window, such as an Archer Queen ability. Earthquake mode (Spell Tower L4) does 30% of max HP to ground tanks (W, Spell Tower).
- Builders use paired Rage Towers as the punishing core: Sawan's "double Rage on each side melts Root Riders" ([B](https://blueprintcoc.com/blogs/town-hall-17/best-anti-2-th17-legend-league-base-link)); Ninj removes a Rage Tower first ([B](https://blueprintcoc.com/blogs/coc-attack-strategies/ninj-backpack-throwers-pro-tips)).
- *Confidence:* medium (W, B).
- *Unverified:* the Spell Tower level available at TH16. Check whether Earthquake mode is available to you.
- *Sim use (test):* treat mode as a search variable. Evaluate against the meta mix weighted by share; Throwers and Dragons together are more than 50%, which argues for Rage/Invisibility over Poison.

**2.8 Long, broken paths for ground pushes.**
- *Rule:* ring or dead-zone structures plus off-center compartments make troops walk long distances and split. Every current Blueprint TH16 layout uses them: a "toxic ring", toxic box, diamond, symmetric and trap bases ([B, 2026-03-11](https://blueprintcoc.com/blogs/town-hall-16/best-th16-base-layouts)). A long walk around the outside runs the timer down ([C](https://cocbasedrop.com/blog/thrower-troop-guide-coc-2026-healers)).
- Ice Golem CC troops freezing Root Riders can cause time fails (W, Root Rider).
- *Counters:* Throwers, Root Riders, Super Bowlers.
- *Confidence:* medium (B, C, W).
- *Sim use (test):* measure time-to-TH and time-to-50% for each ground opener plus push. Reward bases where the median ground attack reaches the TH after 150 s.

---

## 3. Trap theory

**3.1 Put traps where troops must stand or pass, using sim heat maps.**
- *Rule:* "trap where troops must go, not where you hope" ([R](https://boostroom.com/blog/clash-of-clans-trap-placement-guide-turn-defenses-into-wins)). Analyze attack paths and the deploy points you see in replays (W, Giant Bomb). Concentrate traps on the sides attackers actually choose; symmetric trap spreading wastes half of them (C, base-building blog).
- *Confidence:* medium (R, W, C, and every Blueprint layout).
- *Sim use (test):* a **trap-placement sub-optimizer**. Fix the building layout, run the meta mix weighted by share and by the sector-choice model from 1.1, and log per-tile occupancy separately for each unit class: hero, Healer, Thrower/Druid, Root Rider, dragon-class, swarm. Place each trap type greedily on the tile that maximizes its expected damage dealt to the units it can hit. Iterate a couple of times, since traps change paths. This is cheap compared with moving buildings and directly removes seed-layout bias in trap choice.

**3.2 Spring Traps at the standing ring of ranged troops.**
- *Rule:* after the October 2025 rework, a spring hits the **largest-housing troop in its 1-tile radius** and launches anything of 18 housing or less (S, G). At TH16 that means **Throwers (16), Druids (16), Yetis and Ice Golems are deleted outright**. Root Riders (20) take 1,200 damage plus a stun. Heroes take 600.
- Throwers stand 6 tiles from their target and Druids 5 (G), so springs belong on the "range ring" outside a building line, not adjacent to defenses. Against Root Riders, put them on the 1-tile approach to the next defense in the chain ("between defenses", W Spring Trap).
- Blueprint builders pair springs with Giant Bombs in RC bays at 2 and 10 o'clock ([B TH17, 2026-02-27](https://blueprintcoc.com/blogs/town-hall-17/best-th17-base-layouts)).
- *Counters:* Throwers (26% share), Druid support, Root Riders, Yetis.
- *Confidence:* high on mechanics (S, G). Ring placement is **my inference** from range data; no builder states it.
- *Sim use (generator rule):* for each likely Thrower target building (outer buildings on chosen sectors), mark tiles at distance 5.5–6.5 on the outward side as spring candidates. The 3.1 optimizer will confirm or reject them.

**3.3 Seeking Air Mines on Healer lanes, stacked against dragons.**
- *Rule:* a TH16 mine (3,000 damage) **one-shots a max-level Healer (2,100 HP)**. In a ground attack the Healers (and the Duke) are the only air units it can target, so every mine on the Healer flight path removes 14 housing of healing (G; W Healer: "can one-shot a relatively leveled Healer ... put mines where you predict ground armies").
- Attackers test the outer edge with single Balloons ("Coconut loons", W), so put mines one layer in, not on the perimeter.
- Against dragons, one mine does not kill: a dragon has 5,700–6,700 HP. Two or three stacked near an AD on the lane do. Builders and guides call clustered mines the thing that "ends" Hydra attacks (C, Hydra and E-Drag guides). Another guide advises offsetting mines instead (R), so this is contested in detail.
- In front of the TH, mines stop short Blimp entries ([B TH17 base 5](https://blueprintcoc.com/blogs/town-hall-17/best-th17-base-layouts)).
- The Duke resists mines while alone: his trap reduction went 50 to 40% in May, then down again in July (S).
- *Counters:* Thrower+Healer, Root Rider+Healer, Queen/Warden walks, Hydra.
- *Confidence:* high (G, W, S, B, C).
- *Sim use (test):* track Healer-seconds alive. Optimize mine placement on Healer occupancy maps from the ground armies, plus a dragon-lane map. Allow mine pairs or triples on dragon lanes within 4 tiles of an AD.

**3.4 Giant Bombs (and Tornado) where packs and heroes commit.**
- *Rule:* stack Giant Bombs, usually two or three, where the RC, her pet, or a hero pack must commit. Pekkachu's Legend base uses **three stacked Giant Bombs** to kill the RC/Spirit Fox at an isolated-TH bait ([B 2025-05-19](https://blueprintcoc.com/blogs/town-hall-17/best-th17-cwl-legend-bases)). Blueprint's TH17 "TH kill zone" layers Tornado, Giant Bombs and Springs at the 1 o'clock RC bait (B).
- Put the Tornado where it pulls troops into Giant Bombs or high-DPS defenses (W Tornado; R). The Tornado is the **only trap buffed by Legend difficulty modifiers** (W Ranked Battles). Giant Bombs and the Tornado heavily damage Throwers (W Thrower).
- *Counters:* RC/Queen/Warden charges, Throwers, Root Rider packs, Yeti.
- *Confidence:* high (B ×3 builders, W, R).
- *Sim use (test):* Giant Bomb candidate tiles are those where 3+ ground units of the push are within 4 tiles at once, or where a hero plus its pet stand. Score by expected hero damage dealt. Treat a "Tornado + 2 Giant Bombs within 3 tiles" motif as a candidate combo.

**3.5 Skeleton Traps by attack type.**
- *Rule:* in ground mode they distract heroes and defense-targeting troops. Root Riders and Dragon Riders *ignore* skeletons, so skeletons hit them freely (W). Spaced skeletons waste Rocket Spears (W). They stall slow-attacking Throwers and Meteor Golems (W).
- In air mode, place them near ADs against Dragons and Balloons; air skeletons are what stop Dragon Riders (W).
- Electro Titan aura and Golems neutralize them (W).
- No universal builder prescription for the mode was found (Codex, confirmed by searching).
- *Confidence:* medium (W, R).
- *Sim use:* make the mode a per-trap search variable. Score against the meta mix; Dragons/Hydra at 27% argue for at least 1–2 in air mode near ADs.

**3.6 Air Bombs: farms near the CC or core, not on lone tanks.**
- *Rule:* at high TH, keep Air Bombs out of AD range: Lava Hounds fly to the AD and soak them (W). Blueprint's anti-Healer diamond stacks all Air Bombs around the CC to catch Healers once a ground entry starts. Its ranked base puts an Air Bomb farm in the core, away from the TH, as part of an Eternal Tome dilemma ([B TH17](https://blueprintcoc.com/blogs/town-hall-17/best-th17-base-layouts); [B TH16 trophy](https://blueprintcoc.com/blogs/town-hall-16/best-th16-trophy-base)). Pair with mines: the bomb softens, the mine finishes (W, R).
- *Confidence:* medium (W, B, R).
- *Sim use:* place Air Bombs in clusters of 3–4 on tiles where 3+ Healers or Baby Dragons overlap within a 3-tile radius.

**3.7 Re-plan traps every week.**
- *Rule:* Legend attackers learn trap spots; make small trap or wall changes after bad hits ([B TH18 legend](https://blueprintcoc.com/blogs/town-hall-18/best-th18-legend-bases); C). The ranked layout is a weekly snapshot (W). In Legend I, layout and CC changes apply from the next League Day ([Supercell support](https://support.supercell.com/clash-of-clans/en/articles/legend-league-4.html), Codex lead).
- *Sim use:* keep 2–3 trap variants per layout from the 3.1 optimizer and rotate them.

---

## 4. Baiting and attacker psychology

**4.1 Make the cheapest-looking side the kill zone.**
- *Rule:* attackers pick the side whose high-value targets look cheapest (1.1). So pick that side **on purpose** and make it lethal. Named-builder examples:
  - Sawan's TH17 legend base "looks like an easy Fireball target" on the left. Attackers who commit lose the Warden and confuse the RC. A Tesla farm sits at 9 o'clock ([B 2025-10-24](https://blueprintcoc.com/blogs/town-hall-17/best-anti-2-th17-legend-league-base-link)).
  - Pekkachu's isolated TH invites a commit into stacked Giant Bombs and a hero-sniping Inferno (B).
  - Blueprint TH17 bases leave Firespitters "slightly exposed to bait RC charges", with Giant Bombs and Air Bombs to finish her (B).
  - Blueprint's TH16 diamond leaves the **Eagle exposed at 6 o'clock**, covered by traps and Tesla fire (B TH16 layouts).
- *Counters:* the attacker's own side-selection logic.
- *Confidence:* medium. The pattern is consistent across 4 Blueprint builders, but there is no outcome data.
- *Contested:* an exposed Eagle as bait directly conflicts with your real result and with 2.1. The Eagle is dormant at that point, so the bait only works if the approach kills the charge *before* the Eagle dies. Treat any "exposed Eagle" bait as unproven at TH16 until the sim's opener test (2.1) shows the charge dies first.
- *Sim use (test):* **bait efficacy** = (probability the attacker picks the bait side under the 1.1 model) × (defender trophies when it does). A bait only counts as good if the bait sector is both chosen most often and scores best for the defender. This replaces "hole-free" as the goal: a base where every side is equally strong just lets attackers choose freely.

**4.2 Force ability dilemmas.**
- *Rule:* build two threats that each need the same one-shot answer: Eternal Tome, Overgrowth, Freeze or Invisibility. Blueprint's TH16 ranked base puts the TH (surrounded by storages and the CC, with an Inferno behind) on the 4:30 side, and a trapped Rage section with an Air Bomb farm elsewhere. Using the Warden's Tome on the TH leaves the Rage sections to punish, and saving it lets the TH compartment punish ([B 2026-06-22](https://blueprintcoc.com/blogs/town-hall-16/best-th16-trophy-base)). C's TH18 base separates TH, Eagle and Monolith into separate pockets for the same reason.
- *Confidence:* medium-low (B, C, both sellers).
- *Sim use (test):* give scripted attackers one Tome, Overgrowth or Freeze each, and let them spend it on the highest-value threat. Reward bases where the second-highest threat zone still kills more than X housing after the first is neutralized.

**4.3 Make visible gaps meaningless.**
- *Rule:* attackers read empty tiles as trap spots (T, C). The wiki suggests putting Giant Bombs in the *other* 2×2 slots where a Hidden Tesla could be, so attackers relax after one Tesla pops (W, Giant Bomb).
- Attackers can now hide your obstacles and decorations during a battle (S, October 2025), so decoration baits are unreliable.
- *Confidence:* low-medium. This is a design inference; no builder data.
- *Sim use (generator rule):* add a "gap entropy" check. Empty 1×1 and 2×2 pockets should exist on every sector at similar density, so trap sectors can't be spotted from gap counts.

**4.4 An early CC pull can be the trap.**
- *Rule:* Sawan's base *wants* the early pull: Furnace, Ice Golem, 2 Rocket Balloons and a Headhunter next to a single Inferno kill the heroes that lure them. Losing the Warden or Queen early "usually ends the attack" (B). This is the opposite of the usual deep-CC rule (see 5.1). Choose per base and test both.
- *Confidence:* low-medium (1 builder).

---

## 5. Clan Castle and defending heroes

**5.1 CC placement.**
- *Rule:* troops leave the CC when enemies come within 12 tiles. If the CC is destroyed first (for example Fireball plus EQ from range), its troops never come out. Skeletons and bats don't trigger it (W, Clan Castle).
- A central or deep CC forces the attacker to fight it under defensive fire ([B TH16 diamond](https://blueprintcoc.com/blogs/town-hall-16/best-th16-base-layouts), [B TH17](https://blueprintcoc.com/blogs/town-hall-17/best-th17-base-layouts)). A CC behind the Monolith adds pressure in the core ([B TH16 trophy](https://blueprintcoc.com/blogs/town-hall-16/best-th16-trophy-base)). Putting the CC between Infernos lets CC troops survive a Fireball (C).
- Keep the CC out of the Eagle's area so a single dive doesn't get both (W, Eagle).
- *Confidence:* high (W, B, C, T).
- *Sim use (test):* **CC pull cost** = the cheapest unit (1 Balloon, 1 Hog, a hero) that can enter the 12-tile radius from any sector without taking more than X damage, and whether the pulled troops can be fought out of defense range. *Generator rule:* the CC center must be more than 12 tiles from every deployable tile, or inside the bait kill zone (4.4). Also check that no deploy tile within Fireball range can see the CC as part of a "closest defense" disk.

**5.2 CC troops.**
- *TH16:* Furnace + 2 Ice Golems + 2 Archers, or 3 Ice Golems + 5 Archers ([B CC guide 2026-04-15](https://blueprintcoc.com/blogs/clash-of-clans-faqs/best-clan-castle-combo-every-town-hall)).
- *TH17:* Furnace + 2 Rocket Balloons + Ice Golem + Headhunter (B).
- *TH18 war:* 2 Ice Golems + Furnace + Headhunter + Archer (B TH18 legend).
- *Other options:* TH16 ranked base used Lava Hound + Furnace + 3 Archers (B). AllClash rates Ice Golem + Furnace S-tier at TH16/17 (A, undated).
- *Why:* Ice Golem freezes stop Root Riders and Meteor Golems (W). Headhunters punish heroes, Archers stretch the deploy time (W).
- *Confidence:* high for Ice Golem + Furnace (B ×3, A, W).
- *Sim use:* make the CC composition a search variable from a short list of these 4–5 options, scored against the meta mix.

**5.3 Defending heroes and banners.**
- *Rule:* heroes defend from Hero Banners. Banners are not targetable and block deploys within 1 tile. All heroes defend on the ground except the Minion Prince and Dragon Duke, which fly; the Warden defends ground-only (W, Hero Banner).
- The defending Queen kills Totems in seconds (W, Totem). Rocket Spear can snipe the defending Warden (W).
- Blueprint has the TH16 Duke at the TH (B TH16 trophy) and says "defending heroes cover both sides" (B, Sawan).
- In Legend, defending heroes get +DPS and +HP from difficulty modifiers, while traps do not (except the Tornado) (W; S Tournament Mode is +20%).
- *Confidence:* medium.
- *Sim use (generator rule):* put banners where hero patrol covers the bait kill zone and the TH. Keep air-hero banners (Duke, Minion Prince) near the AD/mine net, so attacking air armies fight them under AD fire. Test the Queen near the likely Totem drop zone (just behind the outer layer on chosen sectors).

---

## 6. What a ranked defense must prevent

**6.1 Scoring.** Per attack, the defender gets 40 minus the attacker's trophies, except that the defender gets the full 40 on a 0★ (W Ranked Battles):

| Result | Attacker gets | Defender gets |
|---|---|---|
| 3★ | 40 | 0 |
| 2★ at d% | 16 + floor((d − 50)/3) | 8–24 (e.g. 2★ 92% = 30, so 10) |
| 1★ at d% | 5 + floor(d/9) | 25–35 (e.g. 1★ 90% = 15, so 25) |
| 0★ | | 40 |

Ties break on average attack destruction, then on **lowest average destruction conceded**. In Legend I, defenses and defending heroes are buffed, attacking heroes are nerfed, and traps are not buffed except the Tornado (W). Legend I has 8 battles per day (`data/mode-rules.json`, S).

**6.2 Design goal.**
- Your log shows 10 of 13 defenses three-starred. Turning a 3★ into a high-percentage 2★ earns about 8–10 trophies. Turning a 2★ into a 1★ (TH survives) earns about 15 more.
- At TH16 the 50% star is almost always taken by a meta army, so **the Town Hall surviving is the decisive lever**.
- The ranked objective is therefore: (a) the TH is the last building a full-clear attack reaches, and (b) no opener or Blimp/Recall path gets cheap TH damage. Remember the Giga Inferno only "wakes" when the TH is damaged or at 51% (W), and a Fireball can trigger it early on purpose (W).
- Every Legend/ranked base Blueprint publishes states the goal as forcing 1★ or low 2★, not 0★ ([B TH16 trophy](https://blueprintcoc.com/blogs/town-hall-16/best-th16-trophy-base), [B TH18 legend](https://blueprintcoc.com/blogs/town-hall-18/best-th18-legend-bases)).
- War: stars, then destruction. A 3★ denial is the whole game, so the TH and the last 5% matter equally.
- *Confidence:* high (W, project rules).
- *Sim use:* the optimizer objective = expected `40 − attacker_trophies` under the sector-choice model, with "TH destroyed" probability reported as a separate diagnostic and a tiebreak on mean % conceded.

---

## 7. Ten ideas most likely to beat a strong conventional base (ranked)

1. **Opener-survival constraint for the Eagle and AD pairs (2.1).** This is the only principle backed by *your own real result*, and the mechanism is exact: a dormant Eagle under 200 housing. Cheap to test, and it removes the exact failure mode you saw.
2. **Trap sub-optimizer on simulated occupancy maps (3.1), with Springs on Thrower/Druid range rings (3.2).** After the October 2025 rework, a TH16 spring deletes a Thrower outright, and Throwers are about a quarter of ranked attacks. Trap placement is also where the current search is most seed-biased, and it is cheap to optimize separately.
3. **A Seeking Air Mine net on Healer lanes (3.3).** Eight mines at 3,000 damage against 2,100-HP Healers: each correctly placed mine removes one Healer from Thrower, Root Rider and hero-charge attacks. That covers most non-air attacks you face.
4. **Optimize for TH survival, not hole-freeness (6.2).** About 15 trophies per defense separate a 1★ from a 2★. Make the TH the last building reached, and test Blimp and Recall paths.
5. **A side-choice attacker model plus a deliberate bait sector (1.1, 4.1).** Scoring bases on the side attackers would actually pick explains why "no holes" lost: attackers still choose a side. Design one tempting side as the kill zone (Giant Bomb stack, Tornado, Springs, Tesla farm, hero-sniping Inferno).
6. **Closest-defense control against Fireball and Spear (2.2).** Make the closest defense from every edge a low-value one with no high-value defense within 7.5 tiles. This makes hero openers spend equipment on Mortars and Sweepers.
7. **Spell-coverage caps (2.3, 2.4):** at most 2 top-tier defenses per Overgrowth disk, no AD pairs on arrow lines, and no valuable lines through the center against the Backpack. These deny the value that Hydra, Root Rider and Duke openers depend on.
8. **CC as a search variable: deep with Ice Golem/Furnace, or the deliberate-pull trap (5.1, 5.2, 4.4).** Two credible and opposite builder philosophies exist, so let the simulator decide per layout.
9. **Ability-dilemma layout (4.2).** Two separated threat zones, each needing the Tome, Overgrowth or Freeze. This is strong in principle and used by builders, but has no outcome data, so it ranks lower.
10. **Chain-breaking spacing and lightning-rod storages (2.5).** This reliably cuts E-Drag and Super Yeti value. It ranks last only because those armies are less common in your log and the rule costs mutual support. Apply it as a soft penalty.

---

## Contested or unverified

- **Root Rider "wall highway"**: cocbasedrop says Root Riders follow walls and use connected walls as a highway. This contradicts the wiki, where Root Riders ignore walls and walk over them. Trust the wiki.
- **"Cyclone" and "Frozen Tornado" Spell Tower modes** (cocbasedrop TH18 CWL post): these do not exist. The real modes are Rage, Poison, Invisibility and Earthquake (W). Treat other cocbasedrop mechanics as suspect.
- **Fireball radius breakpoints**: Prima's "6 tiles at L18" is wrong. Game data gives 4 / 5 (L9) / 6 (L24).
- **"Eagle activates at about 30% destruction"** (SEO blogs): wrong. It activates at 200 deployed housing (W).
- **Exposed Eagle as bait** (Blueprint TH16 diamond) vs "centralize the Eagle" (W) and your real loss: unresolved. Needs the sim's opener test.
- **Stack mines vs offset mines**: cocbasedrop says cluster them against Hydra and E-Drags; BoostRoom says offset them and use sparingly. The likely answer: stack on dragon lanes, single on Healer lanes. Verify in the sim.
- **Crafting Station availability**: the wiki says TH18 only; cocbasedrop implies module caps from TH11. Irrelevant to a TH16 defense either way.
- **Arrow and Backpack corridor widths, and TH16 Spell Tower max level**: not found. Measure them or check in-game.
- **Reddit evidence** (r/COCBaseLayouts TH18 critique; "Fireball 101" guide) came via Codex and could not be fetched. Unverified.
- **Outcome claims** ("forces 1★", "even pros struggled"): every base page making them sells bases. None has independent data.

## Sources

**Game data and wiki**
- `data/gamecsv/v18.200.9/{traps,characters,special_abilities}.csv`
- `data/catalog.json` (trap counts)
- Wiki mirror `data/wiki/text/`: Fireball, Giant_Arrow, Rocket_Spear, Rocket_Backpack, Root_Rider, Thrower, Dragon, Dragon_Rider, Electro_Dragon, Super_Yeti, Healer, Druid, Totem_Spell, Overgrowth_Spell, Eagle_Artillery, Monolith, Scattershot, Inferno_Tower, X-Bow, Air_Defense, Air_Sweeper, Spell_Tower, Town_Hall_Giga_Inferno_TH16, Clan_Castle, Hero_Banner, Ranked_Battles, and all trap pages.

**Supercell**
- [Ranked update and Spring rework (2025-10-06)](https://supercell.com/en/games/clashofclans/blog/release-notes/get-ready-for-ranked-update/)
- [State of Gameplay pt 2 (2026-05-22)](https://supercell.com/en/games/clashofclans/blog/news/state-of-gameplay-part-2/)
- [July balance update (2026-07-09)](https://supercell.com/en/games/clashofclans/blog/news/july-balance-update)

**Blueprint CoC**
- [TH16 layouts](https://blueprintcoc.com/blogs/town-hall-16/best-th16-base-layouts)
- [TH16 trophy](https://blueprintcoc.com/blogs/town-hall-16/best-th16-trophy-base)
- [TH17 layouts](https://blueprintcoc.com/blogs/town-hall-17/best-th17-base-layouts)
- [Pekkachu TH17](https://blueprintcoc.com/blogs/town-hall-17/best-th17-cwl-legend-bases)
- [Sawan TH17](https://blueprintcoc.com/blogs/town-hall-17/best-anti-2-th17-legend-league-base-link)
- [TH18 legend](https://blueprintcoc.com/blogs/town-hall-18/best-th18-legend-bases)
- [CC combos](https://blueprintcoc.com/blogs/clash-of-clans-faqs/best-clan-castle-combo-every-town-hall)
- [Ninj Root Riders](https://blueprintcoc.com/blogs/coc-attack-strategies/ninj-root-riders-army-pro-tips)
- [Ninj Throwers](https://blueprintcoc.com/blogs/coc-attack-strategies/ninj-backpack-throwers-pro-tips)
- [Rocket Backpack](https://blueprintcoc.com/blogs/clash-of-clans-guides/rocket-backpack-equipment-guide)

**TrophyCoach**
- [Queen charge](https://trophycoach.com/clash-of-clans/guides/queen-charge-guide)
- [War 3★](https://trophycoach.com/clash-of-clans/guides/how-to-three-star-in-war)
- [Army meta](https://trophycoach.com/clash-of-clans/army-meta?th=18)

**Low reliability**
- cocbasedrop: [TH16 anti-RR](https://cocbasedrop.com/blog/best-th16-war-base-layout-2026-anti-root-rider), [TH18 CWL](https://cocbasedrop.com/blog/best-th18-cwl-base-2026-anti-3-star-june), [Hydra](https://cocbasedrop.com/blog/dragon-rider-army-guide-coc-2026-hydra), [Thrower](https://cocbasedrop.com/blog/thrower-troop-guide-coc-2026-healers), [crafted defenses](https://cocbasedrop.com/blog/crafted-defense-placement-guide-coc-2026)
- [BoostRoom trap guide](https://boostroom.com/blog/clash-of-clans-trap-placement-guide-turn-defenses-into-wins)
- [AllClash CC tiers](https://www.allclash.com/best-clan-war-defending-troops/)
