# Conditional Frosty and Frostmites

Frosty now uses the paired-pet deployment, targeting and death lifecycle, with a
separate generated Frostmite reserve and the shared impact-slow scheduler. This
enables complete conditional behavior, while retaining explicit failure for
missing Frostmite statistics. It does not establish game-calibrated Frostmites.

## Evidence

[Supercell's TH15 release notes, 10 October 2022](https://supercell.com/en/games/clashofclans/blog/release-notes/full-release-notes-2/)
describe Frosty's slowing attack, periodic Frostmites that attack defenses, both
attack layers, and preference within 4.5 tiles of the hero. They do not establish
the current Frostmite HP, damage, movement, lifetime or slow constants.

The existing [pinned Frosty catalog](https://github.com/chiefpansancolt/clash-of-clans-data/blob/c6967314d7281bb87c362993e2635e58cd77b351/data/home/pets/frosty.json)
provides the base pet HP, damage, interval, range and movement; summon cadence
(8 seconds); and level-specific batch/cap. Level 10 summons two at a time with
at most ten living Frostmites. These are pinned snapshot values, not a claim
that all current game values are verified. No catalog rows changed.

Neither supplied source resolves Frostmite combat statistics. The source file
must therefore supply their complete quantities and mark the selection
`explicit_uncalibrated_hypothesis`. Frostmite HP, attack damage and slow duration
remain uncalibrated.

## Conditional parameters

`data/battle-policies/recipe-frosty.json` contains a **synthetic example** for
testing and sensitivity only: 75 HP, 20 damage per hit, 1-second attack interval,
0.5-tile range, 4 tiles/second movement, one housing unit for trap/Recall
classification, 12-second lifetime, and 3-second slows at 0.5 attack/movement
rate. These quantities are not observations or borrowed catalog defaults. A
comparison using them must retain their source/status and report that its
Frostmite branch is synthetic.

Every Frosty assignment requires the common pet contract plus the full behavior
mapping. Missing statistics, slow fields or lifecycle decisions fail explicitly.
The contract includes:

- Actual pet deployment anchors the first summon delay and 8-second grid.
  Frozen, recalled or otherwise inactive ticks are skipped; missed ticks never
  produce a burst on return. Owner death leaves Frosty fighting independently.
- Only living generated children count against the level-specific cap,
  including recalled children. Partial batches fill free slots. The finite
  reserve is explicit; exhaustion rejects before spawning any part of a batch.
  The example 48 reserves covers every level-10 batch in a 180-second battle.
- Each Frostmite is an ordinary targetable ground point, jumps enemy walls,
  targets defenses only, and uses the explicit single-target projectile. This
  is an uncalibrated movement/attack representation, not a verified leap or
  attachment animation model.
- Frosty and Frostmites capture slow packets at weapon launch. Impact applies
  the declared slow, uses shared strongest-per-axis stacking, refreshes per
  source, and preserves remaining attack work. The example blocks slow during
  damage immunity. Its slow membership includes any defending units admitted
  by the scene's explicit response policy.
- Frosty death stops future summons. Already spawned children, launched
  projectiles and existing slow effects persist. Children expire on their
  absolute lifetime clock even during Recall; dead expired children cannot be
  redeployed. Expiry does not cancel already released projectiles/statuses.

Frostmites have troop healing/buff/hazard/Spring classes. Their housing value
does not consume army capacity: it is used only by relevant interaction rules.
They inherit no implicit hero/pet stat multiplier. Independent child statistics
and the scenario's explicit generated-child modifier policy remain visible.

## Integration

`compile_pet` emits `frosty_model` and the pet's `on_hit_status`.
`compile_frostmite_reserves(pet)` emits predeclared actors with
`summon_model.kind = "frostmite"`, their Frosty parent and the paired hero.
The pet compiler still returns only pets; adapters append reserves after
validating unique owner assignments. Full-battle accounting treats these as
generated children, with no independent deployment inventory.

`PetCombat` owns `FrostyCombat` and forwards prepare/boundary/frame/result calls.
The existing weapon scheduler, damage receipts and hit-status runtime handle
combat. No background simulation worker or separate timer is introduced.
Independent user deployment of a Frostmite is rejected.

## Validation and remaining gap

Focused checks exercise capped partial batches, source death and absolute
expiry; Freeze/Recall with no catch-up and atomic reserve exhaustion; and an
integrated two-step comparison of Frosty/Frostmite slow and summon behavior.
Existing pet fixtures retain their statistics checks and explicitly reject
Frosty when its Frostmite statistics are omitted.

Before treating this as recommendation evidence, bind observed Frostmite
quantities and contact/lifetime behavior or run a clearly labeled sensitivity
range. This implementation closes the lifecycle plumbing gap; it does not turn
the synthetic parameter example into a measured pet model.
