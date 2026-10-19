# Permanent spell domain handoff

This supplies seven spell-domain compilers and lifecycle contracts for declared
TH16-18 battles. Stage4 binds Bat, Skeleton and Jump to paid v29 battles under an
additional explicit `advanced_spell_binding` contract. Those three integrations
have focused full-battle regressions; Bat/Skeleton have conditional independent
acceptance. Ice Block's ordinary troop path and the Jump/Tornado correction are
now implemented and await recheck; see [clock scope](SPELL_CLOCK_CHECKPOINT.md).
Clone, Revive and Angry now bind within the explicit ordinary/core-hero limits
in [the lifecycle checkpoint](SPELL_LIFECYCLE_CHECKPOINT.md). Secondary lifecycles
continue to reject; no complete coverage claim follows. The remaining sections
describe the domain contract; callback presence alone is not shared acceptance.
Seasonal and Builder Base content is outside this work.

## Source and fidelity

All numeric game quantities are read from `data/catalog.json`, pinned to
`chiefpansancolt/clash-of-clans-data` commit
`c6967314d7281bb87c362993e2635e58cd77b351`; the catalog marks statistics unverified.
Each compiler result retains that entry's exact source URL and verification.

| Spell | Read quantities | Domain behavior |
| --- | --- | --- |
| Clone | radius, clonedCapacity, spellDuration, clonedLifespan | Finite housing budget; eligible live troops entering field; fresh independently compiled reserves; absolute lifetime and silent expiry |
| Jump | radius, spellDuration, boostTime | Per-actor set of affected live enemy wall cells; buildings stay blocked; lead must consume boostTime and finish current wall exit on expiry |
| Bat | radius, batsGenerated, batStats HP/DPS/interval/range/speed/resource multiplier | Finite delayed air-unit release; defense preference with building fallback; trap-trigger exemption |
| Skeleton | radius, skeletonsGenerated, skeletonStats HP/DPS/interval/range/speed/armor | Finite delayed ground-unit release; ground targets; explicit armor unlock and shield overflow assumption; trap-trigger exemption |
| Revive | radius, heroHealPercent | One nearest defeated deployed attacking hero per paid cast, ID tie; lifecycle callback required; subsequent combat must use same identity |
| Ice Block | radius, spellDuration, incomingDamageReduction | Arrival-captured troop/hero set; independent pause/reduction lifetime, strongest reduction across Ice fields, union pause duration |
| Angry | radius, spellDuration, angerDuration, movementSpeedIncrease | Continuous field contacts; expiry/exit linger; defense-first delegated acquisition; strongest own movement bonus; original preferences restored |

The descriptions support each broad role, but do not establish exact spawning,
recipient exceptions, stacking, clone eligibility/state, or revived-hero clocks.
All require `status=opt_in_experimental_permanent_spells_v1` with the complete
explicit policy dictionary. No default policy or claim of verified game fidelity
is supplied. Offsets, generation cadence, movement conversion and Skeleton armor
unlock are caller hypotheses. The pinned catalog omits Bat's Town Hall damage
exception; `bat_town_hall_damage_multiplier` must be supplied explicitly as an
experimental hypothesis. Tests deliberately use 0.123, which is not a game value.
Missing or different policies reject.

The interaction correction adds two required policies:
`same_time_settlement=all_due_releases_and_revivals_then_clone_closure_then_field_membership`
and `clock_rounding=positive_delay_rounds_up_when_sum_does_not_advance`.
Previously saved policy dictionaries need these fields before validation; the
compiler does not silently supply them.

Unknown hero recovery/Phoenix interactions, complex troop clone lifecycle,
spawn legality, landing geometry and cross-family target overrides must be checked
by the kernel callback or rejected. The module never copies live troop runtime
dictionaries or fabricates child stats. The configured Bat resource multiplier
must be classified from catalog identity/category, not instance-name matching.

## Compiler and reserve binding

`advanced_spell_models.compile_advanced_spell(instance,catalog)` returns the
existing attack-spell model shape. Add the seven `SPELL_CLASSES` to the shared
paid-spell registry, received-spell allowlist and termination classification map.
Keep casts in `attack_spells`; dispatch these identities to this compiler.
Do not allow paid spells as raw actor entities. Retain current scope checks;
raw models and generated actors cannot bypass v29+ ownership validation.

Call `advanced_spells.compile_advanced_spell_reserves(models,actor_map)` after
ordinary attackers and independently owned children have been compiled. It
returns Bat/Skeleton templates and finite Clone requests. Clone requests need
the original supported entity/lifecycle compiler, sourced from `entity_adapter`,
with full initial HP and no inherited runtime buffs/statuses. Every reserve must
remain `spawn_seconds=controlled` until its spell owner releases it. Do not create
new paid deployments, housing, CC payloads or hero abilities for these actors.

Compile generated weapon models before creating `AdvancedSpellCombat`. Its
constructor checks exact finite reserve ownership. A Clone request is not a raw
combat actor and must not be treated as one. Clone requests exist for every
eligible declared troop source, including Bat/Skeleton reserves supplied in the
same call; the cast's shared capacity limits actual activation. Later equipment,
siege or troop child groups must be compiled first if cloning them is supported.
Unknown source lifecycle or missing housing explicitly rejects.

New fields that must survive compilation and raw-scene validation:

- `spell_generated_model`: cast_id/entity/index.
- `spell_clone_model`: cast_id/source_id/index.
- `clone_state_policy` on compile requests; no live dictionary inheritance.
- `_spell_trap_trigger_exempt`, `_spell_armor_hp`, `_spell_resource_damage_multiplier`.
- `_spell_garrison_trigger_exempt`, `_spell_town_hall_damage_multiplier`.
- `_spell_pause_until`, `_spell_incoming_damage_multiplier`, `_spell_movement_bonus`,
  `_spell_defense_priority` as owned runtime values.

Generated actors count as ordinary live attacking combatants, are attackable and
eligible for declared healing/buffs/statuses, and never count toward defending
destruction. Assign complete Giga Bomb, Spring, Tornado and defending-unit response
maps by identity. Trap-trigger exemption must not exclude already-triggered damage
or splash; shield and damage reductions are separate.
The explicit garrison policy excludes these summons as castle-release triggers;
they remain attackable after an independently triggered garrison release.

## Runtime hooks and callbacks

Instantiate `AdvancedSpellCombat` with only these seven models and the existing
actor map. It requires these shared-owner callbacks when relevant:

```python
register_actor(reserve, time, source_actor_id) -> same_registered_actor
revive_actor(actor, health_fraction, time, explicit_state_policy)
expire_actor(actor, time)
status_callback(actor, time, previous_spell_pause, new_spell_pause)
base_selector(actor, actors, time, blocked, width, height)
```

`register_actor` activates a precompiled reserve and registers its controlled
release with every applicable runtime owner. It must validate legal spawn geometry,
first attack work and child lifecycle. It must return the same registered actor.
`source_actor_id` identifies the original Clone troop; it is None for Bat/Skeleton.
Released children survive source death. Delayed summons continue independently
after the cast is paid. No reserve can be released twice.

`revive_actor` restores a positive fraction of the hero's maximum HP, reconciles
hero/death observers and permits normal combat. It preserves spent abilities,
equipment charges and absolute status clocks, retains unfinished attack work,
does not revive pets or reset Phoenix rescue entitlement, and rejects unsupported
temporary-life interactions. Merely assigning HP is insufficient.
`expire_actor` silently despawns a Clone at its absolute lifetime even while
Recall-held; no ordinary death explosion, new summons or refunded capacity.

`status_callback` must use shared remaining-work pause logic before the domain
writes its new pause clock. Extend `rates.attack_resume_time` to include
`_spell_pause_until`; pause union is max(Freeze, displacement, Ice Block). Invoke
the callback idempotently only on changed pause clocks. Ice Block never resets
weapon cooldowns. Ordinary field clocks expire absolutely while frozen or held.
Angry retains its established absolute expiry through Recall and death; inactive
actors receive neither its movement bonus nor its target override. Returning
before expiry restores those effects; returning after expiry does not extend or
recreate the clock. Ordinary live field entry can still apply a new effect.

Required scheduling hooks:

- `prepare(time,trace)` after deployment/Recall membership settles and before
  acquisition/weapon launches; idempotent cast/release/revive/expiry transitions.
  Every due Bat/Skeleton release and Revive settles first, then Clone considers
  all resulting non-clone sources, then Ice captures and Angry refreshes membership.
  Cast IDs break ties within phases, not source availability between families.
  Clone reserves cannot source more clones, so a finite dependency sweep reaches
  the domain's fixed point without zero-time retries. Shared external child
  producers must also settle before this hook; clone descendants need clone
  lineage metadata and cannot become independently clonable sources.
- `next_boundary(time)` among solver boundaries, including positive sub-epsilon
  cast delays; returns strictly future representable times.
  If a positive delay is below the current clock's ULP, `spell_clock_after` advances
  to `nextafter(time,+inf)`. The same rule applies to cast arrival, finite release,
  field end, clone life, linger and continuation clocks; overflow rejects.
- `first_crossing_delay(actor,route,time,horizon,effective_speed,forced_motion)`
  for exact Clone/Angry motion entry/exit; consume hint by calling prepare at the
  resulting boundary. Do not approximate contacts with the recording interval.
- `select_target(...)` wraps the delegated base selector while Angry is active.
  It preserves shared target eligibility, visibility, footprint, layer and routing.
- `jump_wall_cells(actor,time)` supplies only eligible enemy wall exemptions.
  Shared routing must use the same exemption for target choice, movement and
  position validation, invalidate paths at field transitions, consume boostTime
  and finish an already-entered wall-exit segment on expiry. These route hooks are
  required integration work; the domain does not implement a second wall solver.
- `continuation_reasons(time)` joins the existing registry for paid pending
  Bat/Skeleton releases and delayed Revive when a defeated eligible hero exists.
- `result()` exposes launched/resolved casts, finite generation counts, remaining
  clone budgets and live clone expiry clocks.

No resolve/weapon/death damage hooks are required from the spell runtime itself:
generated units use the shared ordinary weapon and troop lifecycle systems.

## Shared damage and status consumption

Apply `_spell_incoming_damage_multiplier` through `DamageReceipts.register`
alongside the existing hero/trap reduction factors. Check immunity before damage
and keep attribution/overkill/death settlement intact. Use `armor_damage` only at
shared health settlement for the explicit Skeleton shield policy; aggregate a
same-time breaking-hit policy consistently and account armor damage separately
from health damage. This helper does not subtract actor HP or emit receipts.

Capture the Bat resource and explicit Town Hall damage exceptions in shared weapon launch quantities;
released packets retain that multiplier and source ownership after death or
Recall. Do not apply it based on the source actor's later status. Consume
`_spell_movement_bonus` in the declared movement-buff composition; interactions
with Rage/Haste/hero movement must be explicitly selected or reject. Independent
Ice fields choose strongest reduction; combination with external reductions
remains a declared kernel contract.

## Validation and remaining acceptance

Nine bounded unittest cases pass against the sanitized snapshot. They cover
pause-work preservation through overlap/expiry, two step sizes for Angry linger,
finite Bat/Skeleton release and existing resource receipts, finite Clone housing
and Recall-held expiry after source death, one-hero Revive with spent ability and
attack work retained, Jump wall eligibility, exact positive sub-epsilon arrival,
and full-battle compilation rejecting all seven unbound families. Kernel callbacks
in lifecycle tests are explicit synthetic surrogates, not battle integration.
The two interaction regressions compose Angry with the real Recall owner and
check return before/after the retained expiry, plus simultaneous Bat/Clone under
both cross-family cast-ID orders and repeated same-time prepare calls. The existing
Jump timing case also checks a positive sub-ULP delay at time 100. The two material
interaction cases failed on the frozen domain before correction.

The lead still needs two bounded complete-battle acceptance fixtures after atomic
binding: (1) Bat/Skeleton + Clone crossing, source loss, trap trigger exclusion,
resource exception/shield and exhaustion at two solver steps; (2) dead-hero Revive
+ Ice overlap/expiry + Angry/Jump entry/expiry with retained cooldown, legal wall
exit and correct spent-resource outcome. Assert actual shared damage/HP, trace
ordering, continuation, generated membership and battle resource receipts.

No full simulations or crash probes were run under the shared contract. No full
recipe or game-calibration claim is made. Black 24.10.0 is absent in the execution
runtime; installation is forbidden, so the integration owner must run the required
formatter before final integration.
