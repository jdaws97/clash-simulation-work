# Three bounded TH16 army/action inputs against TH18

The completed batch and disposition are in [RESULTS.md](RESULTS.md).
This document preserves the original v1 plan. The separate
[v2 corrections](review-corrections-v2/README.md) remove the single-Dragon
support dependency and correct the east upper-funnel description. V1's planned
two-candidate transfer was replaced by one B correction run and one B transfer,
keeping five total attempts. Do not run the obsolete v1 transfer queue by default.

These are candidate inputs for a conditional engine screen, not player-ready army
recommendations. No external guide supplied these plans. C0 is the existing engine
control; A and B are original joint composition/action packages. They use the
verified `fc9d0b8a921dbc261f95be0418f8b7618b50a714` prototype without combat edits.

| Package | Owned troops | Purpose |
|---|---|---|
| C0 control | 14 level-11 Dragons + 20 level-12 Minions | Reproduce the original broad west wave and timer-based cleanup |
| A prepared funnel / cleanup | 14 level-11 Dragons + 20 level-12 Minions | Spend two Dragons on shoulder preparation, concentrate twelve, and delay cleanup until named lane defenses die |
| B prepared funnel / screen | 15 level-11 Dragons + 4 level-11 Balloons | Same two-Dragon preparation and hero roles, four early Balloons, thirteen main Dragons |

All spend 320 troop housing, with 3 level-6 Rage and 5 level-7 Freeze spells
(11 owned spell housing). Stone Slammer level 5 carries 2 level-13 Dragons,
2 level-14 Wizards and 2 level-14 Archers (50 donated housing), plus a separate
level-7 Rage and level-8 Freeze (3 donated spell housing). Siege destruction
releases that single payload through the existing paid lifecycle; there is no
second Castle or free replacement wave.

| Hero | Mode / level | Equipment | Pet |
|---|---|---|---|
| Archer Queen | Ground / 95 | Invisibility Vial 7, Magic Mirror 20 | Unicorn 10 |
| Grand Warden | Air / 70 | Eternal Tome 18, Healing Tome 15 | Electro Owl 15 |
| Royal Champion | Ground / 45 | Rocket Spear 21, Electro Boots 23 | Spirit Fox 10 |
| Dragon Duke | Air / 15 | Revenge Deck 20, Fire Heart 18 | Phoenix 10 |

These are the synthetic account's potion/owned/donation assumptions. Availability
has not been confirmed for Jarod. The engine admits these exact entered levels;
that does not certify current client availability or recommend this equipment.

## A/B west preparation and commitment

Coordinates refer to the frozen 56 by 56 synthetic layout, with north at smaller
Y. They are actual paid deployment positions, not target commands.

| Tell or time | Paid action | Reservation / failure behavior |
|---|---|---|
| 0 seconds | Dragon 0 at (1.5,7.5), Dragon 1 at (1.5,21.5) | Two Dragons removed from the main wave; intended shoulders are `army-camp-0` and `gold-storage-0` |
| 1 second | Queen/Unicorn at (1.5,9.5) | Supports upper preparation; ordinary targeting decides her actual path |
| 4 / 5 seconds | Duke/Phoenix at (1.5,23.5), Champion/Fox at (1.5,21.5) | Lower-lane pressure; no King/Queen corner assumption or forced target lock |
| Earliest 12 seconds, lower shoulder and adjacent Multi-Archer still alive | One owned Freeze at (7.5,24.5) | Finite preparation support; otherwise remains unspent |
| B only, 18–18.75 seconds | Four Balloons at (1.5,14), (1.5,15), (1.5,16), (1.5,17) | Explicit screen; does not guarantee trap interception |
| 20–22.75 seconds for A; 20–23 for B | Main Dragons at x=1.5, y=13.5–17.5 in a repeating half-tile spread | **Scheduled commitment even if preparation failed** |
| 20 / 21 seconds | Warden/Owl at (1.5,15.5), Slammer at (1.5,15.5) | Each entitlement spends once |
| A only, earliest 40–44.75 seconds | Ten upper / ten lower Minions around shoulder Y ±0.9 | Upper group requires `archer-tower-0` dead; lower requires `multi-archer-tower-1` dead. Other threats may remain. Unmet cues leave that paid cleanup group unused |

Desired funnel prerequisites are both named shoulder buildings destroyed before
the 20-second core commitment. The receipt audit reports whether this happened.
They are **not executable release guarantees** in these practical schedule inputs.
The existing scheduler cannot express alternative deployments for the same paid
actor. A failed shoulder therefore risks a split core; neither dynamic rerouting
nor rescue of held main troops is claimed. The main force is never suppressed by
an artificial funnel branch. The new inputs explicitly set `funnel.required=false`
with this reason.

Queen ability: earliest 8 seconds, active and HP at most 65%. Champion: earliest
9 seconds, active and HP at most 65%. Warden: earliest 23 seconds, Warden and main
Dragon 2 active and Dragon 2 HP at most 70%. Duke's selected equipment is passive.
These exact HP cues use ideal engine information sampled every 0.25 seconds,
with no human visibility or reaction-delay model. A dead designated lead Dragon
can leave later gated spells or Warden ability unspent: this is an explicit
single-sentinel limitation, not a resilient detector of army-wide pressure.

Owned Rages have earliest times 23, 35 and 55 seconds at (9,16), (18,17), (29,11).
Donated Rage is earliest 45 at (25,20). All require main Dragon 2 active. These
are fixed fields; the engine does not move the cast to the army's later location.
Remaining owned Freezes: earliest 24 at Firespitter 0, 36 at Monolith 0,
48 at Air Defense 0, 60 at the Hall. They require the named structure alive and
main Dragon 2 active. Coordinates are the saved structure origin plus (1.5,1.5).

The donated Freeze is reserved for an explicitly imperfect Hall-risk contingency:
earliest 30 seconds, Hall alive, Queen active and HP at most 35%, at (33.5,7.5).
It is **not detection of Hall invisibility, lure geometry, or actual Hall targeting**.
It cannot redirect the main force and may fire far from the endangered Queen or
remain unused. The Hall/Guardian mechanics stay identical to C0. This limitation
must be addressed before presenting a baited-Hall solution to a player.

## Control and transfer

C0's exact original input is copied byte-for-byte. Dragons fan down the west edge
at 0–1.95 seconds, heroes at 4–4.9, Slammer at 5, and Minions at 10–12.85 without
cleared-lane checks. Its Queen HP gate, scheduled Warden/Champion abilities and
spell fields remain as originally admitted. Comparing C0/A/B compares full action
packages; composition alone is not isolated.

At most two completed A/B plans may transfer to the saved central Hero-Hunter
design with east entry. Those inputs were frozen before screen outcomes: x=54.5;
shoulder Dragons y=13.5/24.5, aimed by proximity at `dark-elixir-drill-2` and
`super-wizard-tower-0`; core center y=19. Queen y=15.5, Duke y=26.5, Champion y=24.5.
Timing and roles match the west templates. East cleanup requires Air Defense 3
and Multi-Archer Tower 0 respectively. East Rages are (45,19), (37,19), (33,9),
(29,21); Freeze targets become Super Wizard Tower 0, Multi-Archer Tower 0,
Scattershot 1, Air Defense 3, Hall, Hall. This is transfer of whole plans across
both layout and entry, not an isolated direction test or independent game holdout.

## Fairness, bounds and evidence

`admission-audit.json` records five full-battle admissions and exact 320/11/50/3
paid budgets. It pins code/data, full layout, account, every defender and trap,
shared policies, termination and Legend I modifiers. Roster-indexed response maps
are verified against the same existing rules before normalization: ordinary
actors use same-tier/allow, Unicorn ignore/ignore, siege ignore/allow; Giga uses
catalog troop housing, heroes 25, siege 1, pets/clones 0 and damage/push 1.
Only those proven roster expansions differ. No Hall timing, defensive mechanics,
or attack-search safety invariant is relaxed.

Legend I uses this snapshot's defense damage ×1.2; defending hero and Guardian
HP/damage ×1.2; attacking hero HP/damage ×0.8; equipment level reduction zero.
Other damage/status classes retain the separately explicit unchanged policies.
These are the pinned simulation settings, not a new independent rules verification.
War and CWL are not included or pooled.

Run with the existing runner:

```powershell
python -B tools/run_full_comparison.py --manifest examples/army-input-screen/screen-manifest.json --accept-experimental-air-contact --output ../army-screen-run1
```

Three serial cases, 240 wall seconds each, 730 total; no retries. Eligible transfer
uses `transfer-manifest.json`, at most two cases, 240 each and 490 total. Its
selection gate is enforced by the owner choosing only completed screen candidates;
the generic runner does not interpret that extra manifest description.
Timeouts, guards and incomplete results remain unscored. Stars, destruction and
elapsed time stay separate. Wall time is a compute budget, not attack duration.

The experimental airborne contact convention requires explicit runner opt-in.
The existing Duke isolation guard can reject a case; do not suppress it. Warden
independent targeting, instant ordinary projectiles, Balloon splash radius 1.2,
Rage hero/pet scaling and sampled-state control remain declared hypotheses.
The two full-inventory TH18 bases are synthetic row-packed geometry with selected
active Hot Candle / Hero Hunter, walls, traps, defensive Castle, heroes and Guardian.
Their seasonal availability/rotation is conditional; complete held-out game
calibrations remain zero. These inputs do not establish opponent probabilities,
global optimality, or a player recommendation.
