# PB1b: recipe, packet, cohort and objective semantics

PB1b implements A5–A10 and the cited A15 controller dependencies from
[the consolidated review](../local/reviews/playbooks/consolidated.md), then applies
its dependent playbook corrections. These are declared synthetic diagnostic
replays of source inventories on existing layouts, not real-game calibration.
No Python files were edited or executed; builds and helpers use Rust in WSL,
`CARGO_TARGET_DIR=/tmp/clash-target-pb`, the repository catalog and offline Cargo.
Nothing was downloaded or installed. `rust/vidmine` and the preserved checkouts
were not edited. An unrelated change to `data/source/live/player-latest.json` was left
untouched; TH18 uses the existing custom build's explicit levels.

## Executable contract

- **A5 — explicit recipes.** `build.recipe` or the `__recipe__` override selects
  a book's `recipes` entry or exact variant name. Entries contain variant-name
  arrays. `default` explicitly selects the default opening. Source-video aliases
  and `variant-N` aliases are declared in the books. `__variants__.names` remains
  available; combining it with a recipe is rejected. Without a declaration,
  selection retains repair-only behavior. Selected additions still pass the
  composition, stock, ability and dependency checks. Variant `required_loadouts`
  maps heroes to **all-required** equipment lists. Step equipment arrays keep
  their existing **any-of** activation meaning. In particular Backpack/Fire Heart
  cannot select the Root Rider Flame Blower recipe.
- **A6 — siege roles.** Siege repair retains replacement siege deployments by
  `siege_role` (default `siege`), including replacements with different IDs. It
  retains their supplied prerequisites and rewires inherited successors when
  there is one replaced siege. It does not install the unrelated charge portion
  of a combined opening. Duplicate siege commitments still fail feasibility.
- **A7 — packets.** Equal, nonempty `packet` labels preserve zero tactical delays
  across recursive temporal conditions and group changes. The engine's normal
  action clock still applies. Positive declared delays survive. Unrelated phase
  boundaries keep ordinary wait fitting; median removal is not global. Citation
  recognition also includes “right after.”
- **A8 — primary cohorts and reserves.** `primary` designates deployment actions.
  `primary_cohort` records that the fitted plan uses explicit designation, so a
  removed primary cannot silently turn a tank into the main force. A successful
  designated action latches the milestone. `allocated_count`, group and the
  action's actual tap interval identify its units, excluding hero/spell clones
  and later same-name deployments. Main pressure, centroids and support use that
  cohort. Remainders have stable name order and preserve cited packet roles;
  unnamed scouts/breakers receive cleanup/breach roles. `reserved` deployments
  are not forced early by stall recovery and release at the existing bounded
  deployment deadline; late surplus retains its role. `cohort:<deployment-id>`
  anchors support on the deployed cohort.
- **A9 — roles.** Generic funnel/push hints do not overwrite cited or variant
  roles. When a variant moves a main hero to a flank, inherited main successors
  bypass that hero's old main dependency; deliberately supplied variant
  dependencies survive. This normalization applies to explicit and automatic
  variants. The library's explicitly described Puppet Queen recipe joins Queen
  to the Thrower preparation chain, keeping its replacement-healing intent.
- **A10 — Recall lifecycle.** Storing an opening hero latches charge closure and
  retires charge-only support, even if allied healers survive. `post_recall`
  explicitly permits a separate post-Recall policy. Fitting binds named returns
  with `recall_from`; unambiguous older prepared plans receive the same binding
  at load. A failed source or permanently lost named hero terminalizes the return
  promptly. A named return requires its own successful Recall and matching hero,
  and returns only units sharing that hero's Recall timestamp. It cannot borrow
  another stash or manufacture an already deployed hero. Without Recall, an
  opening hero/Healer return package becomes one main-entry package. Ordinary
  non-Recall Warden walks retain their walk role. A named return waits for its
  named hero's planned Revive, not unrelated Revive inventory.
- **A15 — narrow objective/effect dependencies.** `objective` binds a building
  identity, retaining its center for follow-up area work even when selection
  would otherwise drift. `objective_at`, `target_mode`, and optional `target_keys`
  describe selection. The cited Zapquake value selector uses the existing threat
  weights and actual resolved Earthquake radius. Bound line abilities require
  intersection with the selected building; bound Fireball requires the actual
  candidate splash to include it. The existing aim deadline cancels a failed
  bound job instead of substituting an unrelated shot. `after_success` prevents
  follow-ups to failed actions and removes them when that prerequisite is fitted
  out. `effect_active`/`effect_expired` use the actual field expiry captured at
  casting, never a new spell-duration rule. Objective predicates distinguish
  alive, destroyed, damaged and Rage mode; named Headhunter predicates and anchors
  target that threat. `bind_before` captures an obstruction before the shot that
  may destroy it. Per-target Rocket packets select distinct threatening towers,
  retain other cited troop reservations, and use the input clock. Super Minion
  snipes require a legal tile within the catalog's actual Long Shot range;
  Flinger release requires the payload on Queen's current route segment.
  Offensive masks bind distinct eligible defenses nearest the caster, excluding
  the Fireball objective and buildings already covered by pending or active
  Invisibility. This avoids waiting for a defense to start firing before masking
  it. Defensive unit protection remains a separate policy.

Repeated Clone support waits for the last quarter of the previous actual Clone
field, with input pacing between eligible casts; this overlap fraction is an
explicit controller policy, not a measured video interval. Continuing Skeleton
support waits for the previous summoned wave to disappear and rechecks primary
pressure. Druid's second healing wave waits for the first Druid cohort to leave
healing form or die, then rechecks Queen pressure. The repeated Fox/charge
protection policies retain their stock and end on stock/hero/charge lifecycle.

The strict army-search program schema now accepts and validates these fields,
anchors and predicates. Count fitting and program normalization update cohort
allocation metadata. Unknown fields, unknown references, invalid equipment,
overspending and cycles still fail; the proposal proof was repaired by extending
this boundary, not by reducing its required batch size or assertion coverage.

## Dependent data corrections and citations

The detailed existing `cite` arrays are retained; added quotations are extracted
from the nearest actual timestamp in the existing local transcripts. Video times
below are source times, not simulation waits.

| Book | Dependent correction and evidence |
| --- | --- |
| Dragon | Stable Quake packets; separate hero-core and later zapquake objectives; Rage-Tower selection for the three-Quake source; two Rockets per selected threatening Bomb Tower rather than an unconditional four; all-required Flame Blower/Backpack and an Inferno-intersecting line; Overgrowth renewal waits for expiry. [Quake cluster, 119.9–126.5](https://www.youtube.com/watch?v=KYxypCKWh-E&t=119), [two per tower, 90.3–108.8](https://www.youtube.com/watch?v=47wtlBeNIPw&t=90), [early-shot correction, 198.5–203.2](https://www.youtube.com/watch?v=PY3LIEa1Wck&t=198), [separate jobs, 152–169.7](https://www.youtube.com/watch?v=Sin7pQqHJLo&t=152). |
| Druid/Ruin Witch | Super Witch recipe uses one Ruin Witch behind Warden after Fireball and two at main. Main breach precedes Launcher and is independent of the remote RC/Duke chain. Source recipes retain Life Gem Furnaces, Titan lead and separate Druid healing waves. Freeze requires and targets a Headhunter. [Split, 157.5–175.5; breach, 94.3](https://www.youtube.com/watch?v=mTgmnznwvww&t=157), [Druids, 195.8–208.2](https://www.youtube.com/watch?v=NEvdsy6wmH4&t=195), [Headhunters, 696.2](https://www.youtube.com/watch?v=iBpk-396MQs&t=696). |
| Electro Dragon | Source aliases select Zap/Rocket/Rage/ground recipes. Connected opener and ground support retain input pacing; `flank_rage` anchors to the actual Electro Dragon deployment cohort and no longer the empty Duke-side edge. Two-AD aiming and reserved-breaker handling remain PB1a behavior. [Flank Rage, 149.1–169.8](https://www.youtube.com/watch?v=vbPEc45cUK4&t=149). |
| Fireball Warden | Separate offensive Fireball mask from later defensive Warden Invisibility. Default protected shot requires active Block and mask; redirect masks form one packet; Quick Fireball removes the inherited mask/Block package. Duke/Rockets/Super Minions stay connected. [Preparation, 95–106.6](https://www.youtube.com/watch?v=12Z_sTAEOHw&t=95), [defensive protection, 1349.1–1359.4](https://www.youtube.com/watch?v=pTmX2vmv4sc&t=1349), [Duke support, 436.8–438.3](https://www.youtube.com/watch?v=7rzBODLfnug&t=436). |
| Lavaloon | Siege and bulk air entry share input pacing, including Tome/Haste. Fireball requires all three active masks, follow-up Quakes retain its objective, Recall return is named, and Block renewals wait for actual expiry. Explicit post-Recall Poison remains available. [Masks, 89.5](https://www.youtube.com/watch?v=ahiJ-bgdmSE&t=89), [Tome/Haste, 353.4–357.5; overlapping transition, 935.4–939.4](https://www.youtube.com/watch?v=l0D7kFeev5g&t=353). |
| Meteor Golem | Explicit source dispatch; connected main support/Mirror/Rage/Tome; opposite Queen preserves main Warden dependency. The prepared recipe follows the declared four-Invisibility source: three clearing Balloons, actual obstruction removal, four distinct masks, bound Fireball and two successful-shot Quakes before main Golems. Nearest-Mortar clearing, weighted core selection and mask circles are explicit controller approximations; source coordinates are unavailable. [Clear/preparation/follow-up, 120–139](https://www.youtube.com/watch?v=lHLHvW8vFTg&t=120), [actual obstruction removal, 95–109](https://www.youtube.com/watch?v=lTp7FjulP8Q&t=95), [paired activation, 230.2](https://www.youtube.com/watch?v=MUssbWM-qpk&t=230). |
| Root Rider | Flame Blower **and** Backpack prerequisite; bound Duke-opening objective; preserved charge and Queen-flank roles; King before Warden; “right after” Tome pacing; TH-isolation Tome waits for Overgrowth expiry. No new exact Rocket quantity is asserted. [Pair/pathing, 182.4–195](https://www.youtube.com/watch?v=QCrKyyMDYr4&t=182), [King/Warden, 143.7–145.7](https://www.youtube.com/watch?v=b46w2PUASJI&t=143), [expiry, 354.9–357.3](https://www.youtube.com/watch?v=QBJSv33_sIc&t=354). |
| Super Bowler | RC/Duke repeated protected charges retain their budget; regeneration follows stock exhaustion and actual protection expiry. Source charge/Flame recipes require both Tome and Torch; the Flame pair remains all-required too. Stored-hero charge closure and coherent non-Recall Healers use A10. Existing PB2 Launcher/Warden ordering and saved-meta loadouts are retained; the meta file was not edited. [RC protection, 239–249](https://www.youtube.com/watch?v=_N5VEy9FTN0&t=239), [Duke protection/regeneration, 190–215; Tome/Torch, 307–309](https://www.youtube.com/watch?v=QH4OIrEePh4&t=190). |
| Super Minion Air | Surgical Super Minion/Rocket reserves retain their role; opening Rockets are a small Monolith support packet. Queen is the primary hero entry. Furnaces/Healers are kept outside the opening Recall package through later deployment. Fireball/Arrow/Backpack jobs are distinct; finishing Quakes require their prior successful shot, surviving damage and applicable Rage mode. Same-side Flinger waits on its bound X-Bow's destruction; release requires Queen-route geometry; two-Minions-per-tower snipes require legal Long Shot geometry. Existing exclusive three-Quake and duplicate-siege repairs remain. [Reserves, 1219](https://www.youtube.com/watch?v=qlLv2Bvu4ig&t=1219), [Monolith Rockets, 673](https://www.youtube.com/watch?v=x5AiCcU008Y&t=673), [tower snipes, 1346](https://www.youtube.com/watch?v=dn6J46bW0ts&t=1346). |
| Thrower | Explicit source dispatch and bound Zapquake jobs use the cited value candidates or Builder Hut repair objective instead of universal Monolith. Clone support repeats with actual field overlap; Skeleton distractions continue by wave and pressure; Fox-centered Invisibility retains its budget. Puppet Queen joins the main preparation chain. PB1a renewable Firemites and breaker reservations remain. [value selection, 171–218](https://www.youtube.com/watch?v=0h7c4WKuPB8&t=171), [Builder Hut, 124–138](https://www.youtube.com/watch?v=Xk6Q2cZqvHM&t=124), [Clone overlap, 133–160](https://www.youtube.com/watch?v=HJfCl7Ycf6E&t=133), [Skeletons, 76–90](https://www.youtube.com/watch?v=dxLogWcc0VU&t=76). |
| Yeti | Bulk `yetis` is primary. Totem/Freeze require that deployment and primary pressure; tank/flank Yetis do not unlock them. Left/right/bulk and activation support form one paced packet; Rage uses the actual advancing primary cohort. Existing compatible Mirror alternative and Baby Dragon allocation repair remain. [Rapid flanks, 695.1–703](https://www.youtube.com/watch?v=3O9g9-Gujcw&t=695), [bulk support, 203–206.9](https://www.youtube.com/watch?v=g36z6N8CfTc&t=203). |

Super Minion also declares two complementary objective recipes: Ricochet
Fireball with Monolith/Revenge hero jobs, and Scatter Fireball with Clan
Castle/Super Wizard Tower hero jobs. They require the actual Fireball, Giant
Arrow and Backpack loadouts, and two successful-shot finishing Quakes. The
default's conditional finishing opportunities instead share an explicit optional
budget, so a smaller spell stock does not silently select a different tactical
recipe. Evidence: [Ricochet and separate hero jobs, 259](https://www.youtube.com/watch?v=HnEtYULN4Y0&t=259)
and [Scatter and complementary jobs, 44–54](https://www.youtube.com/watch?v=b_kCBBnsuvo&t=44).
The individual Arrow/Backpack assignment is a declared controller policy; exact
aim tiles are not recovered from these transcripts. The Block source has its
own two-Furnace preparation and protected-shot window.

## Evidence boundaries and section C holds

No damage, range, duration, Recall-capacity/priority, or targeting-rule constants
were changed. No Meteor Super Archer/Launcher ordering was inferred from frames.
No new Super Minion coco tap order or split-Quake impact synchronization was
asserted. Yeti Baby Dragon coordinates and Thrower Clone-opening Healers were
not invented. Empty unresolved split/Recall branches remain unresolved.
Unverified source inventories and historical loadouts retain their limitations.

Bindings and guards establish controller prerequisites, not guaranteed full spell
value or a reproduction of a video's placements. Threat-based concealment,
Zapquake value weights, the Clone overlap fraction, a two-Rocket small support
batch and Queen's current-route-segment test are explicit controller policies.
They are not new real-game measurements. The Electro Dragon cohort correction
uses actual recipients; it does not claim recovery of every source's exact Rage
circle. Lava/Fireball source probes use the existing documented witness-only
Lavaloon book alias where production family routing lacks an Ice-Hound-only
Lavaloon route. No routing expansion was added to conceal that limitation.

## Before/after review witnesses

The original binary/library and public books were saved under `/tmp/pb1b` before
editing. Native helpers replay the PB2 witness manifest, all source-book default
and explicit-variant controls, public linked-source reconstructions from PB1a,
and explicit recipe dispatch with the same input before/after. A source-book
inventory is not assumed compatible with every alternative variant: expected
incompatibilities are retained and reported. Unresolved source allocation/level
exceptions remain synthetic diagnostic controls rather than exact legal armies.

Artifacts and Rust helpers are in ignored
[`local/reviews/playbooks/pb1b`](../local/reviews/playbooks/pb1b/). Complete step logs,
active-field windows, binding IDs/modes/HP, plans and rejection reasons are saved
there. The focused table below reports battle seconds; the full paired outcome
matrix follows it. Score changes are observations, not acceptance targets.

Unless noted otherwise, these controls use `r18a`, seed 2, angle 0. Times
describe the logged action, including the explicitly marked cancellations.

| Item and witness | Before | After |
| --- | --- | --- |
| A5/A7, linked Rocket Electro Dragon, `recipe` input; `r18b/2/0.21` | Recipe input falls through to default; Arrow 11.0, Duke 27.3, Electro Dragons 43.2 | Selected Quakes 0.0/0.6; Lightning 1.2/1.8/2.4; secondary Quakes 3.0/3.6; Duke 4.2; Backpack 5.0; Arrow 8.1; Electro Dragons 8.4 |
| A5, source Dragon Flame recipe with incompatible equipment | Branch admitted, 2★/78% | Rejected for the missing all-required loadout; Root Rider's pair has a separate compiler regression test |
| A6, Super Minion Troop Launcher auto/explicit | Automatic uncited remainder 40.4; explicit cited Launcher 81.0 | Both cited `troop_launcher` 21.5, one deployment, identical 1★/74%. The actual Backpack fires before deployment; the named step reports already-used equipment |
| A7 and dependent Druid split, linked Super Witch | Fireball 17.6; all three Ruin Witches at main 35.6; Launcher 37.4; breach 73.0 | Fireball 6.5; one flank Witch 8.0; Super Witches 23.4; two main Witches 24.4; breach 26.1; Launcher 27.0 |
| A7/A15, linked staggered Druids | Druid waves 51.9/52.7 | 28.1/61.1, second gated by the first cohort leaving healing form and Queen pressure |
| A8, linked Titan/Druid source | Balloon remainder 8.3 unlocks Totem 11.2, before Queen 42.0/Witches 43.7 | Balloon 8.0; Queen 23.6, Titan 24.4, Witches 25.3, Totem 28.2 |
| A7/A8, source Yeti flank variant | Left/right/bulk 69.2/85.1/101.0; Totem 63.3 and Freeze 74.8 precede bulk | Left/right/bulk 54.1/54.9/55.7; Totem 62.9 and Freeze 63.5 follow bulk and primary pressure |
| A8, Super Minion siege control reserves | Four surplus Super Minions 10.5 before Queen 34.8 | Surgical reserves retain their roles; this control does not find their threat and releases at the existing 150.0 deadline. Queen enters 11.7 |
| A9, account Root Rider roles | RC `funnel/edge:funnel`, Queen `main/edge:main` | RC `charge/edge:charge`, Queen `funnel/edge:funnel`; the main Warden retains its own dependency |
| A9, library Puppet Queen | Queen 29.6 after Throwers 0.8; 2★/71% | Queen 6.4 in the main preparation packet; 1★/60% |
| A10, source Bowler Recall lifecycle | Recall 7.1; charge Poison stays pending until stock failure 66.3 | Recall 7.1; charge Poison closes 7.7; separate post-Recall Poison remains conditional |
| A10, non-Recall Bowler meta #3 | Charge Queen/Healers remain split from the main entry; no named return | Both retain one main-role package; no manufactured return. Bowlers 35.8→21.1; 2★/73%→2★/80% |
| A10, linked joint Root Rider | Recall 21.5, Queen 37.5, Barracks 41.3, main tank/Riders 64.4/65.2, nominal Warden return 69.2 despite loss | Recall 21.5; named Warden return fails 22.1; Queen 22.9, Barracks 23.7, tank/Riders 31.8/32.6 |
| A15, TH-isolation Root Rider source | Overgrowth 30.4; Tome 34.8 while protection is active | Overgrowth 27.0; Tome 53.5 after actual effect expiry |
| A7/A15, Lavaloon Fireball; `r18d/2/0.21` | Masks 9.7/13.9/19.0, Fireball 32.9 | Masks 0.8/1.4/2.0. Bound shot cannot align while all masks remain active: cancels 5.6; both Quakes cancel with it; Recall proceeds 5.6 |
| A15, Fireball Warden default | Block 2.4; Invisibility 6.8; named Fireball already used 12.5, but Quakes still cast 17.3/21.2 | Block 3.3; offensive mask 3.9; named shot already used 4.6; dependent Quakes cancel 4.6. Emergency equipment use is not counted as a successful sourced shot |
| A15, linked Meteor prepared recipe | No mask/clear/Quake stage; 0★/46% | Three clearing Balloons 0.8; the clear does not complete before emergency equipment use. Named Fireball and its Quakes cancel 4.9, main Golems follow 5.1. Four masks remain conditional on actual clearing; no prepared-shot success is claimed. 1★/51% |
| A15, linked Super Minion Block recipe | Explicit source rejected by inherited spell commitments | Admitted source package: two Furnaces 0.8, Block 1.7, offensive mask 2.3. Bound shot cannot align before protection expiry, cancels 7.1; no finishing Quake follows |

The Lavaloon binding audit records goal **building 69 (`revenge`)**, and three
distinct concealed buildings **27 (`at`), 33 (`mortar`), 53 (`swt`)**. The goal
remains visible; the actual mask-field expiries are **5.55/6.15/6.75**. The 5.6
shot cancellation therefore enforces the protection window rather than firing
after it. On this layout the source-specific Dragon three-Quake recipe finds no
eligible Rage-mode Spell Tower and cancels its jobs; it does not substitute a
different tower. Stable identities, actual Block/Overgrowth landing and status
deadlines, named-return stash isolation, cohort membership and reserve-stock
isolation also have focused Rust regression tests.

The Druid default's Fireball and both Quakes retain **building 91 (`xbow`, ground
mode)** in the audit. The Yeti flank control's actual spell-Rage status reaches
**four main Super Yetis** from 62.0 seconds, plus an incidental right-flank Yeti;
this is measured from applied field status, not cast-center proximity. Full
recipient IDs and first/last status times are retained for the controls,
including automatic surplus casts. These measurements do not assert that every
remaining unit receives every spell, or that generic surplus policies reproduce
a cited placement.

<details>
<summary>Complete PB2, source-book and library control outcomes</summary>

Each cell is stars / destruction. Rejections remain explicit; the JSON artifacts
retain full reasons, inventories, selected variants and deployment logs. `source-`
controls use one book's declared roster, not a reconstructed roster for every
alternative. Their trailing index is zero for default, otherwise one-based variant.
Newly declared variants have no prior branch.

| Witness | Before | After |
| --- | --- | --- |
| `dragon-three-quakes` | 3★ / 100% | 2★ / 80% |
| `dragon-ice-hound` | 2★ / 71% | 2★ / 71% |
| `dragon-zapquake` | 2★ / 79% | 2★ / 80% |
| `electro-ground` | 3★ / 100% | 3★ / 100% |
| `electro-rocket` | 2★ / 79% | 2★ / 62% |
| `fireball-quick` | 2★ / 61% | 1★ / 57% |
| `fireball-arrow` | 1★ / 62% | 1★ / 50% |
| `lavaloon-default-blocks` | 2★ / 70% | 3★ / 100% |
| `lavaloon-fireball` | 0★ / 45% | 2★ / 71% |
| `meteor-walk` | 2★ / 63% | 0★ / 48% |
| `meteor-opposite` | 0★ / 44% | 0★ / 46% |
| `root-joint-exact` | rejected: package feasibility | rejected: package feasibility |
| `root-joint-furnace` | 1★ / 57% | 2★ / 63% |
| `root-flame-rockets` | 1★ / 61% | 1★ / 67% |
| `bowler-log-order` | 2★ / 64% | 2★ / 85% |
| `bowler-meta-1` | 2★ / 68% | 1★ / 71% |
| `bowler-meta-3` | 1★ / 55% | 2★ / 76% |
| `minion-log` | 1★ / 65% | 2★ / 77% |
| `minion-three-quakes` | 1★ / 76% | 1★ / 78% |
| `minion-walk-support` | 2★ / 66% | 1★ / 73% |
| `thrower-walk` | 3★ / 100% | 3★ / 100% |
| `yeti-arrow-meta1` | 1★ / 73% | 1★ / 78% |
| `yeti-arrow-meta4` | 2★ / 94% | 2★ / 97% |
| `yeti-mirror` | 1★ / 78% | 2★ / 98% |
| `druid-notes-control` | 1★ / 52% | 1★ / 55% |
| `dragon-three-quakes-auto` | 2★ / 78% | 2★ / 83% |
| `dragon-zapquake-auto` | 2★ / 85% | 2★ / 87% |
| `electro-ground-auto` | 3★ / 100% | 3★ / 100% |
| `lavaloon-fireball-auto` | 0★ / 45% | 2★ / 71% |
| `meteor-walk-auto` | 2★ / 63% | 0★ / 48% |
| `root-joint-exact-auto` | 1★ / 64% | 1★ / 57% |
| `minion-log-auto` | 2★ / 65% | 2★ / 77% |
| `minion-three-quakes-auto` | 1★ / 64% | 1★ / 73% |
| `siege-Troop Launcher-auto` | 2★ / 81% | 1★ / 74% |
| `siege-Troop Launcher-explicit` | 1★ / 70% | 1★ / 74% |
| `siege-Battle Drill-auto` | 2★ / 66% | 2★ / 80% |
| `siege-Battle Drill-explicit` | 1★ / 62% | 2★ / 80% |
| `source-dragon-0` | 2★ / 78% | 2★ / 83% |
| `source-dragon-1` | 3★ / 100% | 2★ / 80% |
| `source-dragon-2` | rejected: source roster | rejected: source roster |
| `source-dragon-3` | rejected: source roster | rejected: source roster |
| `source-dragon-4` | rejected: source roster | rejected: source roster |
| `source-dragon-5` | rejected: source roster | rejected: source roster |
| `source-dragon-6` | rejected: source roster | rejected: source roster |
| `source-dragon-7` | 2★ / 91% | 2★ / 94% |
| `source-dragon-8` | rejected: source roster | rejected: source roster |
| `source-dragon-9` | rejected: source roster | rejected: source roster |
| `source-dragon-10` | rejected: source roster | rejected: source roster |
| `source-dragon-11` | 2★ / 78% | rejected: required loadout |
| `source-dragon-12` | rejected: package feasibility | rejected: package feasibility |
| `source-dragon-13` | rejected: source roster | rejected: source roster |
| `source-druid-ruin-witch-0` | 1★ / 53% | 1★ / 88% |
| `source-druid-ruin-witch-1` | rejected: package feasibility | rejected: package feasibility |
| `source-druid-ruin-witch-2` | rejected: source roster | rejected: source roster |
| `source-druid-ruin-witch-3` | rejected: source roster | rejected: source roster |
| `source-druid-ruin-witch-4` | rejected: source roster | rejected: source roster |
| `source-electro-dragon-0` | 2★ / 51% | 1★ / 70% |
| `source-electro-dragon-1` | rejected: source roster | rejected: source roster |
| `source-electro-dragon-2` | rejected: source roster | rejected: source roster |
| `source-electro-dragon-3` | rejected: source roster | rejected: source roster |
| `source-electro-dragon-4` | rejected: source roster | rejected: source roster |
| `source-fireball-warden-0` | 1★ / 60% | 0★ / 49% |
| `source-fireball-warden-1` | 1★ / 56% | 1★ / 59% |
| `source-fireball-warden-2` | 2★ / 61% | 1★ / 57% |
| `source-fireball-warden-3` | 1★ / 55% | 1★ / 57% |
| `source-fireball-warden-4` | 1★ / 60% | 1★ / 50% |
| `source-fireball-warden-5` | 1★ / 62% | 1★ / 50% |
| `source-lavaloon-0` | 2★ / 70% | 3★ / 100% |
| `source-lavaloon-1` | rejected: source roster | rejected: source roster |
| `source-meteor-golem-0` | 0★ / 46% | 0★ / 48% |
| `source-meteor-golem-1` | 0★ / 46% | 0★ / 48% |
| `source-meteor-golem-2` | rejected: source roster | rejected: source roster |
| `source-meteor-golem-3` | rejected: source roster | rejected: source roster |
| `source-meteor-golem-4` | rejected: source roster | rejected: source roster |
| `source-meteor-golem-5` | 0★ / 44% | 0★ / 46% |
| `source-root-rider-0` | 1★ / 63% | 1★ / 63% |
| `source-root-rider-1` | 1★ / 65% | 1★ / 64% |
| `source-root-rider-2` | rejected: source roster | rejected: source roster |
| `source-root-rider-3` | 1★ / 55% | 1★ / 62% |
| `source-root-rider-4` | rejected: source roster | rejected: required loadout |
| `source-root-rider-5` | rejected: source roster | rejected: source roster |
| `source-root-rider-6` | rejected: source roster | rejected: source roster |
| `source-root-rider-7` | rejected: source roster | rejected: source roster |
| `source-root-rider-8` | rejected: source roster | rejected: source roster |
| `source-root-rider-9` | 1★ / 60% | 1★ / 67% |
| `source-super-bowler-0` | 2★ / 69% | 2★ / 76% |
| `source-super-bowler-1` | rejected: source roster | rejected: source roster |
| `source-super-bowler-2` | 2★ / 63% | 1★ / 53% |
| `source-super-bowler-3` | 2★ / 71% | 1★ / 57% |
| `source-super-bowler-4` | rejected: source roster | rejected: source roster |
| `source-super-bowler-5` | rejected: source roster | rejected: source roster |
| `source-super-bowler-6` | 2★ / 64% | rejected: required loadout |
| `source-super-minion-air-0` | 2★ / 60% | 1★ / 73% |
| `source-super-minion-air-1` | rejected: source roster | rejected: source roster |
| `source-super-minion-air-2` | rejected: source roster | rejected: source roster |
| `source-super-minion-air-3` | rejected: source roster | rejected: source roster |
| `source-super-minion-air-4` | 2★ / 77% | 1★ / 78% |
| `source-super-minion-air-5` | 1★ / 68% | 1★ / 73% |
| `source-super-minion-air-6` | 1★ / 66% | 1★ / 68% |
| `source-super-minion-air-7` | 1★ / 66% | 1★ / 73% |
| `source-super-minion-air-8` | rejected: source roster | rejected: source roster |
| `source-super-minion-air-9` | rejected: source roster | rejected: source roster |
| `source-super-minion-air-10` | 2★ / 80% | 1★ / 77% |
| `source-super-minion-air-11` | 1★ / 68% | 1★ / 75% |
| `source-super-minion-air-12` | 1★ / 66% | 1★ / 73% |
| `source-super-minion-air-13` | 1★ / 60% | rejected: package feasibility |
| `source-super-minion-air-14` | 2★ / 64% | 1★ / 73% |
| `source-super-minion-air-15` | N/A: new declaration | 1★ / 80% |
| `source-super-minion-air-16` | N/A: new declaration | 1★ / 80% |
| `source-test-stealth-rr-0` | 1★ / 56% | 1★ / 56% |
| `source-thrower-0` | 3★ / 100% | 3★ / 100% |
| `source-thrower-1` | rejected: source roster | rejected: source roster |
| `source-thrower-2` | 2★ / 80% | 2★ / 85% |
| `source-thrower-3` | rejected: source roster | rejected: source roster |
| `source-thrower-4` | rejected: source roster | rejected: source roster |
| `source-thrower-5` | rejected: source roster | rejected: source roster |
| `source-thrower-6` | rejected: source roster | rejected: source roster |
| `source-thrower-7` | rejected: source roster | rejected: source roster |
| `source-thrower-8` | rejected: source roster | rejected: source roster |
| `source-thrower-9` | rejected: source roster | rejected: source roster |
| `source-thrower-10` | rejected: package feasibility | rejected: package feasibility |
| `source-yeti-0` | 3★ / 100% | 2★ / 90% |
| `source-yeti-1` | rejected: source roster | rejected: source roster |
| `source-yeti-2` | rejected: source roster | rejected: source roster |
| `source-yeti-3` | 1★ / 83% | 2★ / 81% |
| `source-yeti-4` | 3★ / 100% | 2★ / 90% |
| `source-yeti-5` | rejected: source roster | rejected: source roster |
| `custom:puppet-queen-throwers` | 2★ / 71% | 1★ / 60% |
| `meta:super-bowler-smash-18-3` | 2★ / 73% | 2★ / 80% |
| `custom:user-rr-oct25` | 0★ / 44% | 0★ / 42% |

</details>

<details>
<summary>Linked-source and explicit recipe controls</summary>

IDs retain the inherited PB1a witness labels. Full reconstruction details are in
`linked_probe.rs`; these are synthetic controls. Explicit selection and the public
`recipe` path are replayed separately with unchanged input for each before/after pair.

| Selection | Witness | Before | After |
| --- | --- | --- | --- |
| explicit | `A1-dragon-live38` | 0★ / 41% | 0★ / 41% |
| explicit | `A1-druid-life` | 3★ / 100% | 3★ / 100% |
| explicit | `A1-edrag-observed5` | 1★ / 56% | 2★ / 58% |
| explicit | `A11-edrag-rocket` | 2★ / 76% | 2★ / 61% |
| explicit | `A11-thrower-arrow` | Illegal attack plan: Duplicate pet: Unicorn | Illegal attack plan: Duplicate pet: Unicorn |
| explicit | `A11-thrower-linked` | 3★ / 100% | 3★ / 100% |
| explicit | `A12-thrower-clone` | 2★ / 99% | 3★ / 100% |
| explicit | `A12-thrower-linked` | Infeasible playbook variant: Firemite Clone opening; only the first Clone cast is specified | Infeasible playbook variant: Firemite Clone opening; only the first Clone cast is specified |
| explicit | `A13-thrower-default` | 3★ / 100% | 3★ / 100% |
| explicit | `A13-thrower-yeti` | 3★ / 100% | 3★ / 100% |
| explicit | `A14-edrag-default` | 3★ / 100% | 2★ / 64% |
| explicit | `A15-meteor-prepared` | 0★ / 46% | 1★ / 51% |
| explicit | `A15-minion-protected` | Infeasible playbook variant: Ice Block-assisted Fireball | 0★ / 49% |
| explicit | `A2-bowler-linked` | 0★ / 37% | 1★ / 74% |
| explicit | `A2-bowler-rc` | Illegal attack plan: cc 56 > 55 | Illegal attack plan: cc 56 > 55 |
| explicit | `A2-druid-life` | 2★ / 60% | 1★ / 52% |
| explicit | `A2-druid-linked-druids` | 1★ / 57% | 1★ / 78% |
| explicit | `A2-druid-linked-life` | 3★ / 100% | 3★ / 100% |
| explicit | `A2-druid-linked-superwitch` | 1★ / 60% | 2★ / 60% |
| explicit | `A2-druid-linked-titans` | 1★ / 75% | 1★ / 91% |
| explicit | `A2-thrower-zap` | 3★ / 100% | 3★ / 100% |
| explicit | `A3-root-joint` | 0★ / 46% | 1★ / 61% |
| explicit | `A3-root-meta1` | 0★ / 41% | 1★ / 57% |
| explicit | `A3-yeti-decoy` | 2★ / 57% | 1★ / 59% |
| explicit | `A4-quick-fireball` | 2★ / 61% | 1★ / 57% |
| explicit | `D1-lalo-L` | 1★ / 72% | 1★ / 63% |
| explicit | `D1-meteor` | 0★ / 46% | 0★ / 48% |
| explicit | `D1-root-revival` | 2★ / 77% | 1★ / 74% |
| explicit | `D2-lalo-R` | 2★ / 70% | 2★ / 70% |
| recipe | `A1-dragon-live38` | 0★ / 41% | 0★ / 41% |
| recipe | `A1-druid-life` | 3★ / 100% | 3★ / 100% |
| recipe | `A1-edrag-observed5` | 1★ / 56% | 2★ / 58% |
| recipe | `A11-edrag-rocket` | 2★ / 77% | 2★ / 61% |
| recipe | `A11-thrower-arrow` | Illegal attack plan: Duplicate pet: Unicorn | Illegal attack plan: Duplicate pet: Unicorn |
| recipe | `A11-thrower-linked` | 3★ / 100% | 3★ / 100% |
| recipe | `A12-thrower-clone` | 2★ / 99% | 3★ / 100% |
| recipe | `A12-thrower-linked` | 3★ / 100% | Infeasible playbook variant: Firemite Clone opening; only the first Clone cast is specified |
| recipe | `A13-thrower-default` | 3★ / 100% | 3★ / 100% |
| recipe | `A13-thrower-yeti` | 3★ / 100% | 3★ / 100% |
| recipe | `A14-edrag-default` | 3★ / 100% | 2★ / 64% |
| recipe | `A15-meteor-prepared` | 1★ / 64% | 1★ / 51% |
| recipe | `A15-minion-protected` | 0★ / 44% | 0★ / 49% |
| recipe | `A2-bowler-linked` | 0★ / 37% | 1★ / 74% |
| recipe | `A2-bowler-rc` | Illegal attack plan: cc 56 > 55 | Illegal attack plan: cc 56 > 55 |
| recipe | `A2-druid-life` | 2★ / 60% | 1★ / 52% |
| recipe | `A2-druid-linked-druids` | 1★ / 57% | 1★ / 78% |
| recipe | `A2-druid-linked-life` | 3★ / 100% | 3★ / 100% |
| recipe | `A2-druid-linked-superwitch` | 1★ / 60% | 2★ / 60% |
| recipe | `A2-druid-linked-titans` | 1★ / 75% | 1★ / 91% |
| recipe | `A2-thrower-zap` | 3★ / 100% | 3★ / 100% |
| recipe | `A3-root-joint` | 1★ / 55% | 1★ / 61% |
| recipe | `A3-root-meta1` | 0★ / 41% | 1★ / 57% |
| recipe | `A3-yeti-decoy` | 2★ / 57% | 1★ / 59% |
| recipe | `A4-quick-fireball` | 1★ / 60% | 1★ / 57% |
| recipe | `D1-lalo-L` | 1★ / 72% | 1★ / 63% |
| recipe | `D1-meteor` | 0★ / 46% | 0★ / 48% |
| recipe | `D1-root-revival` | 2★ / 77% | 1★ / 74% |
| recipe | `D2-lalo-R` | 2★ / 70% | 2★ / 70% |

</details>


## TH18 before/after

Both runs use `fidelity th18 --replicates 5`: four ranked bases, eight sides,
all five skill quantiles, paired execution seeds, the existing TH16
`custom:user-rr-oct25`, r8 strength and no league modifier. The full sweep crosses
three level conditions and three CC hypotheses. A final maximum-level rerun uses
the pinned original inputs to confirm the baseline. The final full after sweep
uses a frozen copy of the final Rust/data inputs. The frozen reports have
`inputs_changed_during_run=false`; a provenance check compares the final Root
Rider inputs and all 200 compiled side/seed plans against the working tree.
Final Meteor/Bowler data-only corrections are outside the Root Rider experiment;
the final tree must still produce exactly those same 200 Root Rider plans.

Reports stay in ignored `local/fidelity/pb1b-before-th18.json`,
`pb1b-after-th18.json` and the baseline confirmation
`pb1b-before-current-locked.json`. The comparison below
uses **TH18 maximum levels and saved/default CC**, separately from the empty and
strong-candidate hypotheses. Each policy has 25 selected skill/replicate groups.

The original full baseline report flagged input-file changes while development
continued, although it used the saved binary and already compiled plans. Exact
recovery of its 114 pinned inputs and the maximum-level baseline replay
reproduced every reported baseline mean with a stable fingerprint. The table
uses that pinned confirmation. The final after sweep is also stable; its
provenance check matches 96 final Rust/Root Rider input hashes and all 200 plans.

Each entry is **before → after mean stars per base**.

| Base | Real stars | Random side | Visible side | Oracle side |
| --- | --- | --- | --- | --- |
| r18a | 1 | 1.48 → 1.20 | 1.72 → 1.44 | 2.12 → 2.24 |
| r18b | 2 | 1.08 → 1.52 | 1.36 → 1.60 | 1.68 → 2.16 |
| r18c | 2 | 1.44 → 1.60 | 1.68 → 1.88 | 2.00 → 2.20 |
| r18d | 3 | 1.48 → 1.08 | 1.96 → 1.44 | 2.20 → 2.00 |


The real column is the user's four single results, **1/2/2/3**, not an estimated
mean. Oracle side choice is an unattainable comparator. These development bases,
uncertain defense transcriptions and unknown historical occupants do not provide
held-out calibration, and a corrected controller can lower a seed's score.

## Verification

- `cargo fmt --manifest-path Cargo.toml --check`: passed.
- `cargo test --offline --manifest-path Cargo.toml`: **59 passed**, two documentation examples intentionally ignored.
- Battle golden check: **868/868**; two intentional A10 changes, 866 byte-identical cases.
- Plan golden check: **1,354/1,354**; 522 changed old cases, 674 unchanged old cases, 158 new recipe controls.
- `guardian-check`: **50/50** declared synthetic fixtures.
- `armysearch-proof`: passed all **4,096 legality and 4,096 program iterations**, native determinism at **1/4/16 workers**, and its existing optimization/checkpoint/budget/holdout assertions.
- `fidelity th18`: full paired before/after sweeps, five replicates, eight sides, five skill quantiles, three level conditions and three CC hypotheses; original baseline confirmed from exact pinned inputs. Final Root Rider provenance checks all 200 plans.
- `git diff --check`: passed for this task's files.

The final command logs, complete paired witness reports, objective audit, source
citation extracts and formatted Rust replay helpers are retained in the ignored
artifact directory. Cargo ran offline with the repository catalog; no Python
verification command was run.

Intentional battle and compiled-plan changes, including every changed case and
its reason, are recorded in [`GOLDEN.md`](GOLDEN.md). The golden fixture inputs
were not edited. Neither the unsupported-content gates nor the proof assertions
were relaxed.
