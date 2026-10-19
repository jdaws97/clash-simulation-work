# Research notes: TH16 ranked & war defense (October 2026)

Collected 2026-10-14/15 while rebuilding the simulator. Prior Codex/GPT outputs
were **not** treated as sources; everything below was re-checked against the
sources linked.

## 1. How ranked defense is scored (drives the optimizer objective)

Source: [Ranked Battles, Clash of Clans Wiki](https://clashofclans.fandom.com/wiki/Ranked_Battles)

- Weekly tournament, groups of 100 in the same league. **Electro 31: 18 attacks
  and 18 defenses per week, top 20% promoted.** No difficulty modifiers below
  Legend III (Electro is standard stats).
- Attacker trophies per attack (max 40):
  - 3★ = 40
  - 2★ = 16 + 1 per 3% above 50% (98% → 32)
  - 1★ = 5 + 1 per 9% (91% → 15)
  - 0★ = 1 per 10% (max 4) — but the **defender gets the full 40 on any 0★**
- **Defender gains 40 − attacker trophies.** So a 1★ at 45% still banks you
  ~30, a 2★ at 70% banks ~18, a 3★ banks 0.
- Ties are broken by average attack destruction, then **lowest average
  destruction conceded on defense**.
- The defense layout is snapshotted at the start of each weekly season; edits
  apply next week. Traps are always armed and heroes always defend in the
  snapshot. You pick defensive CC troops.
- Ranked groups mix Town Hall levels, so TH17/18 attackers hit TH16 bases.

**Optimizer objective (ranked):** maximize expected defender trophies
`40 − attacker_trophies(stars, %)` against a TH16–TH18 attack mix.
In practice: protect the Town Hall (1★ vs 2★ is a ~15-trophy swing) and keep
destruction low.

## 2. What actually attacks bases (real ranked data)

Source: [TrophyCoach army meta](https://trophycoach.com/clash-of-clans/army-meta?th=18),
133,586 classified ranked battles, snapshot 2026-10-15. Same-TH TH18 ranked
attacks, last 30 days (432,583 attacks, 44.9% baseline 3★ rate):

| Army | Share | 3★ rate |
|---|---:|---:|
| Mass Dragons (incl. Dragon Rider "Hydra") | 27.1% | 44.6% |
| Mass Thrower | 26.0% | 54.3% |
| E-Drag Spam | 11.5% | 22.1% |
| Root Rider | 9.7% | 41.4% |
| Super Bowler Smash | 6.4% | 56.4% |
| Mass Super Yeti | 4.0% | 50.9% |
| Mixed | 3.5% | 54.4% |
| Mass Meteor Golem | 2.3% | 40.7% |

Supercell's [July 9 2026 balance post](https://supercell.com/en/games/clashofclans/blog/news/july-balance-update)
confirms Dragon armies (~20%) and Throwers + Healers as the top two TH18 war
armies (~40% together). It nerfed Dragon Duke trap reduction and top-level
Dragon Rider, and buffed top-level Electro Dragon, Meteor Golem and Druid.
ClashKing's game data (Sept 28) already reflects these numbers.

### Your own defense log (Clash API, last ~week, decoded)

13 ranked defenses: 10 three-stars, 1★ 86%, 1★ 87%, 2★ 94%, which works out to
about **5 trophies per defense**. Attackers were TH16 ×5 and TH17 ×8. Armies:

- Throwers + Healers ×3 (11–17 Throwers, 4–5 Healers, Totems/Invis/Revive)
- Dragons + Dragon Riders ("Hydra") ×4 (often 9 Invisibility or Clone/Overgrowth)
- Electro Dragons ×3 (with Totems, Clone, Rage, Lightning)
- Meteor Golem ×1, Electro Titan/PEKKA/Root Rider ×1, Witch/Wizard smash ×1

Dragon Duke (Rocket Backpack / Fire Heart / Revenge Deck) and Royal Champion
(Rocket Spear + Electro Boots) appear in most attacks. Totem Spell appears in
roughly half.

## 3. Mechanics worth modelling (TH16–18 meta)

- **Totem Spell** (TH18 update, unlockable at TH16): lands in ~5–6 tile radius,
  damages and stuns buildings, then becomes a high-HP totem (11k–13k, decaying
  ~334 HP/s) that defenses retarget to. Effectively a long-lived damage sponge.
  Sources: [TH18 release notes](https://supercell.com/en/games/clashofclans/blog/release-notes/town-hall-18-crash-lands-update/),
  catalog values.
- **Dragon Duke**: Royal Rampage when no friendly flyers are near (+100% damage,
  +50% attack speed); trap damage reduction cut to ~20% in July. Rocket
  Backpack dashes in a straight line burning buildings; Fire Heart heals and
  explodes on death; Phoenix revive.
- **Overgrowth**: defenses in radius are frozen, invisible and invulnerable for
  ~25 s; attackers ignore them. Does **not** stop traps, CC troops or heroes.
- **Town Hall 16 Giga Inferno**: 300 DPS multi-target beams, range 10, slow,
  1,100 death damage + poison. (The legacy Codex catalog wrongly said TH16 has
  no weapon; ClashKing game data and the Supercell sneak peek agree it does.)
- **Merges**: each Multi-Archer Tower uses two Archer Towers, each Ricochet
  Cannon two Cannons. Maxed TH16 = 4 AT + 2 MAT, 3 Cannon + 2 Ricochet.

## 4. Current TH16 base-design patterns

Sources: [Blueprint top-5 TH16 bases](https://blueprintcoc.com/blogs/town-hall-16/best-th16-base-layouts),
[AllClash TH16 bases (Oct 2026)](https://www.allclash.com/the-best-th16-war-trophy-farming-base-layouts/).

- **Ring/box structures with compartments and dispersion**: wide rings of
  "dead zones" force long troop walks and break spam pushes.
- **Toxic core**: Infernos, Ricochet Cannons, Invisibility and Rage spell
  towers stacked around the TH; or Multi-Infernos + Poison towers against spam.
- **Trapped hero-entry bays** at the sides where RC/Duke like to start.
- **Isolated or offset Eagle**, Monolith behind the TH or off-centre, CC deep or
  off-centre to make lures hard.
- **Spread Air Defenses** so one Lightning + Freeze combo can't take two;
  Seeking Air Mines on air paths; sweepers covering the core.
- Ranked/trophy bases specifically aim at **anti-2-star**: deny the TH route and
  "limit Thrower value" with controlled paths.
- Defensive CC seen on current bases: 2 Ice Golem + Furnace + 2 Archers;
  Ice Golem + 2 Headhunters + Furnace + Archer; 3 Ice Golems + 5 Archers.
