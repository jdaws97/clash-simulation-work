> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Defense / Clan Castle second delta

Apply AFTER frozen defense commit c8628ee80bd6b75b63b4c2518eb1ea7220cd8d83
and task-9 attacking-troop-domain.patch. Imported attacking dependency commit
90bde0f exists only in this isolated checkout; it is excluded from this delta.
Do not copy private ancestry. No spatial/adapters/combat/rates/full_battle edits.

## Implemented domain capabilities

Defensive role bridge invokes task-9 compile_attacking_extension, never duplicates
its troop weapons/behaviors/summon clocks. Explicit defending role contract must
enumerate every compiled behavior feature as enabled/suppressed experimentally,
target layers and wall policy. Hounds substitute actual selected pupsOnDefense
for the attacking quantity in a copied source row; catalog is never mutated.
Ice Hound freezeTime has no separately saved defensive value and requires an
explicit named defensive hypothesis. Child death effects target attacking units.
Generated reserves retain Castle lineage, are uncounted, cannot be independently
deployed, and do not consume a second Castle payload or paid army inventory.
Released batches persist parent loss through the shared finite-reserve runtime.

GarrisonCombat accepts these extended members only with explicit scope/role
metadata; it does not add them silently to the ordinary availability registry.
Shared Castle release/lure/target pursuit remains in garrisons.py. No invented
Castle recall leash or return behavior is added. Castle death must never recall
already released parents/children; unreleased original payload still uses the
existing Castle gate.

DefendingTroopBehaviorCombat and DefendingTroopLineCombat reuse task-9 state and
projectile implementations; line continuation preserves defensive packet team.
DefendingSummonCombat reuses shared clocks and fixes defensive continuation team.
DefendingTitanCombat and DefendingDruidCombat use schema validation views only,
then restore actual actors for ALL lifecycle/health/damage operations. Titan uses
live hostile unit-only aura membership. Druid keeps one finite owned Bear, shared
transformation timeout/lethal interceptor and generated-form deployment guard.
The Druid ground wall policy must remain jump_enemy_walls as required by the
shared support lifecycle. Bear statistics remain caller-supplied experimental.

Supercharged defenses use separate ordinary base level and charge tier, validate
final ordinary level/TH availability, and feed the selected absolute source row
to the EXISTING owning compiler. No additive HP/DPS guess, no missing-field merge.
Returned provenance preserves actual charge row, tier and explicit assumption.
Existing compiler rejection still controls missing mode quantities.

Inferno fuel is an explicit experimental reservation gate AFTER existing target/
beam selection and BEFORE projectile emission. Choose pulse-vs-per-beam accounting
and explicit initial quantity; saved sources have no ammo quantity. Partial beam
prefixes conserve fuel; frozen/inactive/not-ready launches consume none. It never
creates/resets attack clock or copies Inferno ramp logic. Caller must clear all
retained beam locks when result is empty, and cancel newly selected launches.

Dragon Duke can bind the existing defending air hero patrol/leash/death lifecycle
with base source stats and no attacking hero/equipment/pet registry. It REQUIRES
explicit intrinsic suppression. Isolation defensive eligibility remains unknown;
this is experimental base-only support, not complete Duke support.

## Integration owner hooks (required before full-battle availability)

1. Add exact opt-in instance fields to shared validation: defending_extension_parameters,
   supercharge_parameters, defending_duke_parameters, inferno_ammunition_parameters.
   Do not infer missing role fields from catalog presence.
2. For defending extensions: create the same controlled uncounted base attacking
   troop weapon/death/support actor task-9 adapter would use, retaining donor and
   receiver TH checks, then call compile_defending_extension with defensive scope.
   Supply all task-9 extension parameters. Druid/Furnace need existing none-weapon
   base compilation; Furnace must compile stationary rather than walking.
3. Compile defending reserves before _load_actors and all registry creation.
   Never pass these reserves to paid manifest/donation accounting. Apply explicit
   attacking-unit response maps to every generated defender recipient where the
   shared combat binding requires them. Construct the defensive wrappers in place
   of shared task-9 runtimes (each includes ordinary attacking models too).
4. Wire shared task-9 prepare/launch/resolve/after-health/next_boundary/continuation/
   frame/result hooks identically for defensive models. Attach shared damage_receipts
   to Titan and line runtimes. DruidSupportCombat already heals by actor's team;
   retain first_crossing_delay and shared lethal interceptor ordering. Use only one
   runtime per model family, no duplicated pulse/weapon clock.
5. Select compile_supercharged_defense before ordinary supercharge rejection; pass
   the existing compile_actor plus appropriate existing flags. Extend full-battle
   result provenance and plan identity to preserve ordinary level AND charge tier.
6. After native Inferno beam/ramp selection call reserve_launch exactly once at
   each real launch, before health/projectile release. Fuel reservation must run
   only after other launch gates pass; do not spend then cancel for a later gate.
   Preserve clocks and released packets. Clear all native retained locks on empty.
7. Defending Duke adapter route must precede any attacking-only Duke intrinsic
   binding, and retain explicit suppression in entity_adapter for runtime validation.

## Evidence and honest remaining gaps

Numeric evidence is the saved community catalog commit
c6967314d7281bb87c362993e2635e58cd77b351, with exact per-entity blob URLs retained
in data/catalog.json and secondary ClashKing extraction
b8f42a707fe92d5293d46088bf536450ae422e7b. No new current-game fidelity claim.
Fifteen defense identities have saved supercharge rows: Air Defense, Bomb Tower,
Builder's Hut, Firespitter, Tesla, Inferno, Monolith, Mortar, Multi-Archer,
Multi-Gear, Revenge, Ricochet, Scattershot, Super Wizard Tower and X-Bow.
Resource extractor charges are outside battle effects. Existing Revenge/higherTH
experimental compilers are reused, not copied or replaced.

The task-9 bridge covers its 24 declared extension interfaces but DOES NOT mean
24 complete defending identities. Meteor Golem, Ruin Witch and Super Valkyrie
remain explicitly unavailable through dependency rejection/absence. Missing
Furnace Firemite persistent pools, Super Yeti electrical child interactions,
Ice Hound hit slow, exact Super Dragon burst, generated child source statistics,
defensive feature eligibility and recall/revival state semantics remain gaps.
Opt-in suppression of an intrinsic is an assumption, never source-backed fidelity.
Seasonal/crafted and builder-base are separate; no historical phase is promoted
into permanent TH16-18 support by this patch.

Concrete source capture questions for the parent:
- Inferno: initial usable fuel, pulse vs beam debit, empty-lock behavior, refill
  eligibility during battle. Saved catalog and secondary building rows omit count.
- Duke: does defending isolation exist; ally neighborhood/radius and qualifying
  air troop/hero/pet/summon types; attack/trap scaling and clock transition; any
  defensive ability/equipment effects. Descriptions alone do not answer these.
- Defensive CC specials: ability eligibility and quantities for each intrinsic;
  child weapon/HP/movement/lifetime source rows; Druid heal recipient/transformation
  behavior, Furnace pool ownership, Ice Hound slow and freeze role difference.
- Current crafted selectors: exact season/release identifiers and modifier rows
  plus selection/mode lifecycle; never reuse an isCurrent=false historical phase.

## Checks and certification limit

tests/test_defense_delta.py contains six bounded cross-lifecycle checks: absolute
supercharge compile, frozen/partial-beam fuel, defense Hound count and parent-loss
child attack, explicit Duke suppression, Titan live hostile filters, and finite
defensive Druid Bear transformation. Fixtures are synthetic, not game calibration.
Existing shared attacking, Castle and defending-hero regression tests remain used.
No suspect Python battle runner retries, installs or game automation occurred.

No newly bound full-battle simulation exists for this delta. Integration owner
must provide fresh zero-exit bounded complete-battle crossings after shared hooks:
Castle lure/release -> Titan pulse -> effective lethal Druid -> owned Bear and
Hound child release after Castle/parent loss; finite Inferno pulse and absolute
supercharge defense versus attacking ground/air units; Duke home/aggro/leash/death
with suppressed intrinsic. Two justified solver steps only if integration changes
need them. Do not mark catalog presence or these component checks FULL support.
