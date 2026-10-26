> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Explicit recipe troop contracts

These adapters provide conditional simulations. The supplied policy is an
uncalibrated experiment, not a recovered game engine or a claim of current game
accuracy. Each instance must opt in with a complete `recipe_parameters` object
from `data/battle-policies/recipe-troops.json`; omitted fields and unknown policies
fail. Existing unsupported-content rejection remains in force until the registry
and all runtime hooks are wired.

## Source boundary

Numeric values come from the repository's pinned catalog at
`chiefpansancolt/clash-of-clans-data` commit
`c6967314d7281bb87c362993e2635e58cd77b351`. They are not silently replaced with
current online statistics. Super troop records are flattened from their parent
troop records: Rocket Balloon from Balloon, Super Barbarian from Barbarian and
Super Wall Breaker from Wall Breaker. Their flattened entries omit damage/target
type, so the registry must explicitly bind `RECIPE_ADAPTERS` and target layers.

Historical primary evidence:

- [Supercell Spring 2020 release notes](https://supercell.com/en/games/clashofclans/blog/news/the-spring-update-is-here-2/)
  establish Super Barbarian's opening eight-second boost, and Super Wall
  Breaker's arrival/death explosion and 40x wall damage. They do not establish
  present-day source statistics, splash radii, exact animation delays or routing.
- [Supercell TH14 release notes](https://supercell.com/en/games/clashofclans/blog/release-notes/full-patch-notes-th14-update)
  mention fixes to troop ability and Headhunter poison timers, supporting the need
  for explicit clocks without specifying the current timer constants.
- [Supercell October 2025 release notes](https://supercell.com/en/games/clashofclans/blog/release-notes/get-ready-for-ranked-update)
  state that Headhunter poison damage is displayed. Poison is therefore modeled
  as damage plus slow; it is not silently omitted.

These troop contracts remain uncalibrated. Geometry, update
cadence, poison ramp/stacking and effect composition below remain hypotheses.
Unknowns are exposed in the policy, never inferred from an acquisition range.

## Balloon and Rocket Balloon

The normal weapon retains the instance's explicit radial projectile parameters.
Defense-first targeting falls back to ordinary buildings. Death damage is
`stats.normal.deathDamage` times the scenario damage modifier, released once by
the shared `DeathCombat` at the actual death center. It survives the source's
death and uses live ground membership at impact. The policy's radius 1.2 tiles
and zero delay are experimental. Temporary Rage does not scale this death blast.
The current death contract includes enemy units, defenses and buildings; wall
collateral is excluded. Ordinary weapon collateral follows the separately
declared projectile/defending-unit response contract.

Rocket Balloon adds a deployment-relative movement boost. The example selects
four seconds and 4x movement; these are explicit unverified values, not catalog
fields. Freeze and displacement do not extend elapsed ability time. Controlled
Clan Castle deployment uses the actual release time, not battle zero. Ability
expiry is an exact solver boundary, independent of the maximum integration step.

## Baby Dragon

`stats.enraged.damagePerShot / stats.normal.damagePerShot` supplies the damage
factor. The ratio of enraged DPS-per-hit to normal DPS-per-hit supplies attack
rate (2x hit and 1.5x rate in this snapshot). Base statistics remain intact.
Remaining attack work is rescaled once at each state transition, including
paused work. Damage and attack rate multiply independently with shared effects.

The example selects a 4.5-tile radius, 0.1-second deployment-anchored samples,
inclusive center distance, and all five declared friendly-air classes. Frozen
and invisible living allies count; reserves, dead actors and Phoenix eggs do
not. Membership, including births and deaths, is held between samples. On
reactivation the actor resamples immediately and resumes its original sample
grid. No movement root-finding or continuous-contact claim is made. Missing a
scheduled active sample fails rather than silently skipping it.

## Headhunter

The normal hit comes from `stats.normal.damagePerShot`; against an actor with a
hero model it receives `dpsOnHeroes / dps` (4x here). Hero identity is model
metadata, never a guessed ID substring. The explicit branch targets ground and
air despite the pinned record's `targetType=ground`; this mismatch remains
visible. Existing enemy-wall traversal is required, with no jump-animation claim.

At every solver boundary, visible living enemy heroes are preferred globally;
if any exist, ordinary targets become ineligible, including retained targets.
Otherwise normal declared targeting resumes. Unreachable heroes can stall this
global preference; no exact compartment/aggro behavior is claimed. The full scene
must bind Headhunter's defending-unit response to `same_tier_as_buildings` and
`allow` collateral before runtime validation.

Shared hit status uses catalog `poisonAttackRateDecrease` and
`poisonSpeedDecrease` percentages. The example holds the slow for one second.
Poison damage uses `poisonMaxDps` times the scenario modifier, follows the struck
enemy unit, and survives source death. The example chooses a one-second linear
ramp evaluated at each 0.25-second right-endpoint pulse, one-second expiry,
refresh preserving ramp/tick phase, and additive independent sources. A partial
final interval is paid at expiry. These are explicit modeling choices; especially
stacking and ramp need evidence/sensitivity before a recommendation. Temporary
weapon boosts and the hero direct-hit multiplier do not multiply poison damage.
Damage immunity protects poison damage; the example permits status application
during immunity. Both the slow and poison are restricted to enemy units.

## Super Wall Breaker

The example selects nearest reachable walls before structures, using existing
ground routing to a wall's attack point. This is not the game's compartment
selection algorithm. It cannot coexist with a second obstruction weapon.

On the first ordinary source-centered instant attack, the compiled attack packet
is queued, then the troop is consumed. Shared death settlement releases its
catalog death damage once. Thus an arrival has one attack contribution plus one
death contribution; a prior lethal hit has only the death contribution. Calling
the launch hook twice fails. Disjoint wall/nonwall death effects apply 40x to
walls without hitting a recipient twice. The attack impact uses the same wall
factor, separately from the shared death effects. Radius and zero delay are
explicit hypotheses, with no guarantee to destroy every current wall level.

## Super Barbarian

The normal melee hit and movement come from its super troop catalog row. The
example selects eight seconds of 4x damage and 2x movement, elapsed during
Freeze; the historical official source supports the duration and axes, not
these multiplier values. Independent spell/status factors multiply. No attack
rate increase is invented.

## Integration contract

1. Register `RECIPE_ADAPTERS` only in a scope with death, hit-status, walls and
   defending-unit response support. Run `compile_recipe_troop(actor, instance,
   entity, row, modifiers)` after the base weapon; preserve `recipe_troop_model`,
   `death_model`, `on_hit_status`, housing and wall fields through full-battle
   validation. Reject `recipe_parameters` on all other entities. Ground Headhunter
   and Super Wall Breaker bypass the generic obstruction-weapon compiler.
2. Instantiate `RecipeTroopCombat(actors)` after actor preparation and response
   binding. Attach the shared `damage_receipts` object. Call `prepare(time, trace)`
   before target selection and after lifecycle changes. Include
   `next_boundary(time)` when selecting the next solver event.
3. Compose `_recipe_attack_rate` into `rates.attack_rate`,
   `_recipe_movement_multiplier` into `rates.movement_speed`, and
   `_recipe_damage_multiplier` into `buffs.damage_multiplier`. Additional
   `recipe_target_eligible(actor, target)` filters shared eligibility. Ordinary
   weapon impacts multiply `recipe_damage_multiplier(source, impacted)` once.
4. After a successfully queued ordinary attack, call
   `launched(source_id, time, trace)`, then settle existing death effects at the
   ordinary health/death phase. Do not manufacture a second attack on consumption.
5. On every impact, call existing hit status only when
   `recipe_status_eligible(source, impacted)` allows it, then call
   `impact(packet, target, actors, time, trace)`. Add `resolve(time, trace)` damage
   to the same shared health batch as other weapon/status sources, and expose
   `result()` as provenance. Poison on structures is forbidden.
6. Assign the previous target selector to `runtime.base_selector`, then wrap it
   with `runtime.select_target` after all existing selector wrappers. Apprentice
   Warden needs this wrapper; its ordinary ranged attack alone is insufficient.
   Include `continuation_reasons(time)` in termination so released poison remains
   relevant after Headhunter death.

## Apprentice Warden

The catalog supplies `auraRange` and level `auraHpIncrease` as a percentage. Its
ordinary slingshot statistics remain independent. The example samples aura and
follow-group membership every 0.1 seconds; this is not a claimed game cadence.
Alive friendly actors of the declared classes within inclusive center radius
receive the strongest Apprentice percentage. Apprentices do not buff themselves
or one another. Frozen/invisible sources and recipients still participate;
undeployed actors, dead actors and Phoenix eggs do not. Source death or inactivity
removes its contribution immediately. Entry/exit preserves current HP fraction
while scaling maximum HP; repeated membership cannot manufacture healing, and
zero HP never becomes positive. These HP rules require empirical verification.
Life Gem coexistence rejects explicitly until its interaction is implemented.

Following selects the largest housing-weight cluster (catalog aura radius around
each eligible troop/hero), then nearest hub, then stable actor ID. Hero weight 25
is explicit; troop housing comes from each actor's catalog-derived binding and
missing values fail. Apprentices are excluded from follow candidates. The example
follows to three tiles and adopts the selected leader's enemy target only when
already within weapon range. Otherwise it follows the leader using the declared
shared ground path/wall policy. It falls back to ordinary enemy selection when
there is no living follow target. This sampled deterministic policy is an
engineering hypothesis, not reverse-engineered troop AI. Choosing `avoid` versus
`jump_enemy_walls` is an explicit per-instance wall hypothesis.

Resource and legal super-troop capacity checks remain upstream; no runtime creates
extra troops or changes deployment inventories.
