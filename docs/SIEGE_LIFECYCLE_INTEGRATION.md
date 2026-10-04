# Siege lifecycle domain handoff

This patch implements domain lifecycle contracts for the five permanent missing
families: Siege Barracks, Flame Flinger, Battle Drill, Troop Launcher and Sky
Wagon. It preserves the existing three carriers and recipe Log Launcher.
These are conditional capabilities, not complete-battle support or current-game
calibration. Shared adapter, loader, resource and termination integration remains
owned by the integration lead. Seasonal and Builder Base content is excluded.

## Entry points and ownership

`siege_lifecycle.compile_permanent_siege` accepts the same actor, instance,
entity, row, modifiers, catalog and conversion arguments as `compile_siege`.
New families require `siege_experimental_opt_in: true`. The existing Log
Launcher adapter may retain its recipe route to avoid changing old inputs.
The runtime factory `permanent_siege_runtime(actors, select_target,
reinforcements, width, height)` accepts the existing recipe runtime interface.
It rejects multiple selected carriers and orphan generated reserves. A stored
list is not passed to this factory. `validate_siege_choices` validates that a
single selected identity is among separately stored choices; army validation
still validates own and donated levels, availability, and the one siege slot.

The new `siege_barrels` module owns barrel carrier compilation, finite generated
reserve manifests, member attachment, the streamed attacking CC specialization,
and the barrel runtime. `siege_extensions` continues to own the other four
families. The `siege_machines` change only improves positive event-clock
preservation and checks non-progressing schedules. No shared files are changed.

## Narrow shared binding requirements

1. Adapter: route the five newly promoted identities through
   `compile_permanent_siege` in an explicit lifecycle scope; preserve the opt-in
   and all model fields. Reject unrelated siege parameters on non-siege actors.
   Do not remove unsupported-content checks. Existing three carriers retain
   their existing role/source/donation validation.
2. Raw attack validation: add `siege_barrel` to the dedicated pattern kinds and
   call `siege_barrels.validate_barrel_pattern`. Generic `PatternCombat.launch`
   must reject this marker, as it rejects `siege_area` and `siege_extended`.
3. Loader: permit only a validated, nonblocking, zero-footprint stationary siege
   point to have a controlled spawn and fractional x/y. Keep speed zero. Do not
   relax stationary building/defense footprint rules. This applies to Barracks
   and Troop Launcher. Stationary carriers have no target tiers; the compiler
   removes the invalid empty tier list.
4. Runtime: replace `recipe_siege_runtime` with `permanent_siege_runtime` after
   the single payload group is compiled. Immediately assign
   `reinforcements = sieges.reinforcements`. For barrel families, the factory
   replaces the original payload object with its compatible streamed
   specialization. Every subsequent command, release-ready, continuation,
   result and damage-receipt hook must use that same object. Keeping the old
   object creates a second mutable payload owner and is invalid.
5. Generated actors: ordinary troop compilation happens first. Attach barrel
   actors with `attach_barrel_member(actor, instance)`, using exactly
   `barrel_member_parameters: {carrier_id, barrel_index}`. Barracks use
   `attach_barracks_member`. All generated actors are controlled attacking units
   with no destruction count and no paid army or CC member model. Runtime
   initialization rejects missing, duplicate, misleveled, externally deployed,
   multiply owned, and orphan members. Preserve `barrel_member_model` and
   `barracks_member_model` through all loader/binding paths.
6. Full-battle binding: assign a separate `siege_generated` origin. It must be
   allowed in generated origins for termination and resource reporting, but
   never user-deployable origins. Exclude generated children from the ordinary
   army and CC inventory count. Bind every child to its carrier, identity and
   level. Barracks generated levels are attacker-confirmed research levels;
   barrel levels are named source quantities and must not become donor/receiver
   laboratory upgrades or fabricated own research.
7. Status/defense/traps: use `siege_effect_eligible(actor, effect)` with canonical
   kinds. `spell` excludes the carrier from all spells including Recall, Clone,
   Freeze and healing. `life_gem`, `apprentice_warden_aura` and `town_hall_poison`
   exclude the carrier. Released children receive ordinary troop policies.
   `defense_targeting` excludes underground Drill. Underground generic damage,
   trap and status exclusion is an explicit experimental hypothesis already
   declared in the Drill model; the hook rejects absent policy. Environmental
   Firemite fire remains eligible. Do not conflate spell immunity with every
   damage/status mechanism or with the hero Eternal Tome ability.
8. Settlement: the existing carrier launch/resolve/prepare interfaces are used.
   Connect shared damage receipts to the runtime; `resolve` returns attributed
   damage for shared health settlement. Settle carrier HP death before a new
   launch and before generation at the same boundary. Call `prepare` again after
   source death and after blocked release geometry changes. Check both
   `sieges.release_ready(time)` and the selected CC object's release-ready hook
   before leaving a boundary. Keep remaining attack work in the shared scheduler
   when external rates change; siege-generated troops use ordinary rates.
9. Continuation: `ExtendedSiegeCombat` and `BarrelSiegeCombat` now implement
   `continuation_reasons(time)` with `continuation_fact`. Prefer this hook over
   legacy `siege_continuation`, whose packet-schema assumption is invalid for
   Flinger unlaunched burst packets. The domain hook accounts for projectiles,
   flames, produced Barracks children, future generation while the carrier is
   active, and in-flight barrel children. Cancelled/unproduced barrel reserves
   do not keep a battle alive. Keep the single attacking CC continuation hook.
10. Results/resources: carrier `states` and `weapon_launches` retain the existing
    result shape. Barracks results have `generated[carrier_id].members`; barrel
    results have `generated[member_id]`. Generated released-at times are separate
    from `sieges.reinforcements.members[*].released_at`. Do not charge generated
    arrivals as CC delivery. Streamed CC members additionally retain launched-at
    times and captured arrival points. First CC launch consumes the existing CC
    delivery resource; later barrels spend remaining members of that resource.

These are integration requirements, not pre-applied shared changes. The lead
must run complete compilation/binding and short full-battle cases after wiring.

## Lifecycle and unresolved policies

Barracks are stationary, source-counted PEKKA/Wizard producers, with source
lifetime and HP decay. Their declared schedule continues through Freeze;
termination cancels unproduced reserves, preserves produced but blocked
releases, and releases the one CC payload. Death precedes same-time production.
Production timing and member offsets remain experimental caller inputs.

Flinger uses named per-spirit hit damage, burst cadence/count, maximum flame
DPS, source decay and lifetime. Captured launched impacts and flame fields
survive carrier loss. Unlaunched spirits cancel on death or declared Freeze.
Fields compose as strongest pulse per source/recipient, sum between sources.
Burst offsets, flight, field geometry, duration and ramp remain experimental.
The prior field-hit packet omitted source-team attribution; this patch fixes it.

Drill delegates active eligibility, retains the chosen defense, burrows directly
past blocking footprints, surfaces before attacking, and stuns defenses through
the existing maximum-status clock. Official documentation establishes a target
stun of two seconds; wider stun radius and blanket underground hazard immunity
remain explicit hypotheses. No source decay/lifetime is invented.

Troop Launcher is stationary and selects the nearest eligible deployed ally in
the declared range. Sky Wagon delegates normal defense-first routing/targeting
to the shared selector. Each launch preclaims at most one ordered CC member and
releases the named finite generated group after declared flight. No ally/target
means wait without consuming a barrel. Source destruction/manual release
cancels unlaunched generated troops, preserves launched flights, and stages
remaining CC members at the carrier's captured death point. Barrel exhaustion
terminates the carrier and releases remaining CC. These placement, flight,
exhaustion and cancellation details are explicit experimental policies, not
assertions of exact current gameplay. Troop Launcher retains its named source
lifetime; its HP-decay curve is unknown and no curve is invented. Sky Wagon has
no lifetime in this catalog; callers must explicitly choose a conditional
maximum lifetime or null. Unknown/missing policies fail.

Flight packets retain launch points and source damage; later target movement or
death does not retarget them. Carrier death and source buffs do not change an
already launched packet. Generated reserve HP is fresh; reserves reject
unexplained damage and external deployment. Released troops keep the same
identity, independently survive carrier loss, and delegate Recall/status/attack
behavior to their ordinary troop runtime. Recall of a carrier is excluded by
spell immunity. Beneficial carrier immunity prevents ordinary Rage/Haste rate
changes; scripted external status hypotheses still require shared rate work
preservation. Positive representable barrel flight times do not collapse into
same-time releases. Non-progressing positive event clocks reject explicitly.

## Child dependencies and source conflicts

Barracks requires ordinary PEKKA and Wizard support. Launcher requires
Barbarian, Archer, Giant and Wall Breaker. Wagon requires Minion, Balloon and
Baby Dragon. The troop worker owns missing Wall Breaker, Balloon and Baby Dragon
capabilities. Include Giga/Spring/Tornado and defending-unit response maps for
all generated members, using their ordinary troop classes and explicit layer
policies. No attacking CC troop gets a second siege-generated origin. Siege
carriers acquire structures, never defending CC troops; released children
delegate combat against defending units to ordinary troop capabilities.

All named child rows requested by the pinned level-1 and level-4 barrel
manifests exist. `barrel_generated_requirements` explicitly fails if any source
child level is absent. Counts are 35/63 total generated actors for Troop Launcher
levels 1/4 and 16/30 for Sky Wagon levels 1/4. Those are snapshot quantities,
not claims of current max-level compositions.

The [publisher's Troop Launcher announcement](https://supercell.com/en/games/clashofclans/blog/news/get-geared-up-for-the-latest-update--3/)
states TH16 unlock, whereas the pinned catalog records TH17. The
[April 2026 Sky Wagon announcement](https://supercell.com/en/games/clashofclans/blog/release-notes/the-sound-of-clash-update/)
describes up to six barrels and maximum children at levels 14/13/12; the pinned
catalog ends at five barrels and child levels 13/12/11. This patch retains
conditional catalog availability/quantities and records the discrepancies.
It does not silently fabricate an absent level or overwrite the data snapshot.

## Bounded evidence and integration acceptance

Eight new lifecycle tests cross single-choice storage, manual loss, HP loss,
expiry, exhaustion, Freeze, blocked release, finite CC/generated conservation,
attribution, source loss and tiny positive flight. Generated test children are
deliberately inert synthetic actor fixtures; they certify release ownership,
not child attack fidelity. Stationary carrier tests initialize at the domain
boundary because the shared loader extension has not been applied. Neither
workaround exists in production code. The existing 42 focused carrier/CC and
full-battle binding checks remain passing in the selected 50-test run.

No large full simulation, native crash probe or held-out game calibration was
run. Full-battle integration is still pending. After applying shared changes,
the lead should use one short stationary Barracks/Launcher scenario, one Wagon
flight/source-loss scenario and one Flinger/Drill boundary scenario at two
justified solver steps. Assert single siege/CC spend, complete generated
membership, protected damage, source loss, continuation cleanup, explicit
unsupported failure, zero process exit and a fresh result. Report unfinished
recipes as unfinished, rather than converting compilation into outcomes.
