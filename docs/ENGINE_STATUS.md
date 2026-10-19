# Engine status and next decisions

This is a preserved v29 conditional combat engine with a stabilization layer.
Passing tests verify the declared software contracts, not live Clash of Clans
accuracy. No complete held-out battle calibration or reliable army win-rate
ranking has been established.

## Architecture

`Catalog`, account planning, army legality, and layout validation feed entity
adapters. The spatial kernel combines target selection, four-neighbor ground
routing, continuous event boundaries, attacks, projectiles, status effects,
healing, deaths, traps, reinforcements, heroes, pets, and siege components.
`full_battle` binds finite resources and adds scoring and termination. Closed-loop
control can apply explicitly supplied response delays and placement errors.

The shared kernel and adapters are large integration points. Changes to event
ordering, ownership, or finite-resource accounting require one integration owner.
Do not implement new mechanics through independent edits to these files.

## Supported scope and assumptions

v29 adds Lightning, Earthquake, Poison, Invisibility, and Overgrowth to the
previously integrated components. Its ruleset is
`spatial-attack-spells-kernel-v29`; scope is
`attack_spells_battle_exhaustion_extended_hero_roster_sector`. Inputs require an
explicit `attack_spells` list, including `[]` when no such cast is selected.

The conditional recipe integration adds seven selected troops, four equipment
items, Frosty with explicit Frostmite statistics, paid Totem/Recall, and Log
Launcher. See [the recipe binding map](legacy/RECIPE_BINDING_MAP.md). Complete TH17/18
scenario assembly and the experimental Revenge Tower contract are documented in
[higher-TH scenarios](legacy/HIGHER_TH_SCENARIOS.md). Compilation does not establish
complete battle execution or game accuracy.

Behavior remains conditional on explicit geometry, quantity, stacking, visibility,
projectile, targeting, and timing policies. Unit collisions, Warden following,
automatic hero activation, and many selectable entities remain unsupported.
Selected unsupported content must fail explicitly. Catalog presence is not
equivalent to combat support.

Electro Titan is connected through explicit opt-in to the paid troop adapter,
shared aura clock, health settlement and short synthetic full-battle contracts.
Recall composition and positive pulse timing have corrective integration checks;
independent acceptance is tracked per frozen checkpoint, not inferred from tests.
Druid and the other attacking extension runtimes remain unbound at the general
entry point. Raw unbound lifecycle models now reject before execution.

Flame Flinger and Siege Barracks join Log Launcher and the three original siege
carriers in conditional shared dispatch. Their short synthetic battle contracts
cover released damage, finite payload ownership and generated Barracks resources;
the Flinger overlap and positive final-tail corrections have independent bounded
conditional acceptance at `da093e6eeacc677d056bbfce85642e92bbed8cf8`.
Drill, Troop Launcher and Sky Wagon remain unbound. Logger discovery explicitly
reports unavailable until projectile, pushback and continuation are connected.
Optional Inferno fuel now gates the shared weapon rather than being discarded.

Ice Block's ordinary troop weapon/movement path is now bound and tested through
paid battles, including defensive Ice Golem death-Freeze overlap in both orders.
Secondary lifecycle recipients fail closed; selected core hero loadouts now bind
under the subsequent [spell lifecycle checkpoint](legacy/SPELL_LIFECYCLE_CHECKPOINT.md).
The Jump/Tornado expiry correction uses a legal shared ground exit after capture.
See [the clock checkpoint](legacy/SPELL_CLOCK_CHECKPOINT.md) for exact scope and limits.

Bat, Skeleton and Jump now have explicit v29 shared bindings and paid battle
regressions. They require `advanced_spell_binding` as well as the complete spell
policy dictionary. Bat/Skeleton have conditional independent acceptance; the
Jump correction and later Ice/Clone/Revive/Angry bindings await recheck. Clone
supports ordinary fresh troop/spell-unit lifecycles; Revive and Angry enforce
the documented core hero and targeting limits. No
updated coverage percentage or full-game fidelity claim follows from this work.

## Numerical limits

The full-air development benchmark exposed an attracting Dragon Duke isolation
boundary: isolated Duke stops at the longer weapon range; a nearby moving ally
removes isolation; Duke chases faster, exits the radius, and stops again.
Opposing one-sided motion creates repeated near-zero events.

Stabilization rejects immediate reversal of a committed isolation contact with a
diagnostic identifying actors, time, radius, and the unresolved policy. It does
not invent hysteresis, sampled updates, or sliding/contact dynamics. Completing
that battle requires evidence or an explicit experimental policy for this case.
An opt-in [sampled-isolation policy](legacy/DUKE_CONTACT_EXPERIMENT.md) now provides a
finite experimental continuation, with explicit timing/provenance and separate
sensitivity checks. Strict rejection remains the default. Its cadence is not a
measured game mechanic.

An older full-village step comparison agreed on stars, destruction, and end time
but diverged in late event positions/timing. Outcome agreement alone is not
trajectory convergence. Compare the same code and input fingerprints, declare
tolerances before inspecting results, and retain the first divergent event.

## Evidence boundaries

Evidence integrity alone does not establish correct patch, exact layout,
equipment, defensive modes, trap positions, or battle-clock alignment. Synthetic
portable fixtures validate evidence schemas and mechanics; they are not
observations. These contracts have no calibrated full-battle validation.

The previous ground development battle reached three stars under its declared
parameters. The full-air benchmark completes only under the explicitly selected
sampled-isolation policy; strict isolation still rejects the unresolved contact.
The [consolidated recipe checkpoint](legacy/CONSOLIDATED_RECIPE_CHECKPOINT.md) separates
exact-recipe compilation, bounded execution attempts and remaining blockers.
One exact-recipe attempt also ended in native process failure `0xC0000005` with
no outcome. A bounded runner mitigation stopped cooperatively without recurrence;
the cause and complete-battle reliability remain unresolved.
Neither benchmark supports ranking real armies or recommending a base.
Recommendations must distinguish current
game observations, expert examples, model experiments, and unknowns.

## Completion criteria

1. A clean checkout runs without user-specific files, preserves meaningful
   assertions, and passes the bounded CI matrix on its exact commit.
2. Representative combined-army checks catch illegal capacity, duplicate/lost
   ownership, incorrect payload/pet/clone lifecycle, and nondeterminism.
3. Harmful numerical non-progress is detected, with unresolved dynamics explicit.
4. Candidate layouts have complete legal inventories and usable coordinates or
   source-verified copy links, with separate ranked and war/CWL objectives.
5. Attack recipes specify all capacities, heroes/equipment/pets, siege and Clan
   Castle, plus deployment cues and unsupported-model limitations.
6. Any accuracy claim uses held-out observed battles with matching input state;
   synthetic success never substitutes for calibration.

Testing is bounded by risk. Preserve useful existing coverage; add only checks
that detect consequential simulation errors. Test count and coverage percentage
are not success criteria.
