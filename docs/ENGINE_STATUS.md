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

Behavior remains conditional on explicit geometry, quantity, stacking, visibility,
projectile, targeting, and timing policies. Unit collisions, Warden following,
automatic hero activation, and many selectable entities remain unsupported.
Selected unsupported content must fail explicitly. Catalog presence is not
equivalent to combat support.

Electro Titan and Druid have standalone components and tests, but v30 integration
was not completed. The siege-extension module is an unintegrated draft, without
end-to-end validation. Do not include either in a claimed full-battle coverage
count. The old v28 coverage count is stale; it is not a completion percentage.

## Numerical limits

The full-air development benchmark exposed an attracting Dragon Duke isolation
boundary: isolated Duke stops at the longer weapon range; a nearby moving ally
removes isolation; Duke chases faster, exits the radius, and stops again.
Opposing one-sided motion creates repeated near-zero events.
The preserved original full-air case reaches genuine contact chatter at
18.305471759 simulated seconds under strict continuous membership. An explicit
experimental policy now provides a separate, conditional continuation.

Stabilization rejects immediate reversal of a committed isolation contact with a
diagnostic identifying actors, time, radius, and the unresolved policy. It does
not invent hysteresis, sampled updates, or sliding/contact dynamics. Completing
that battle requires evidence or an explicit experimental policy for this case.
An opt-in [sampled-isolation policy](DUKE_CONTACT_EXPERIMENT.md) now provides a
finite experimental continuation, with explicit timing/provenance and separate
sensitivity checks. Strict rejection remains the default. Its cadence is not a
measured game mechanic.

An older full-village step comparison agreed on stars, destruction, and end time
but diverged in late event positions/timing. Outcome agreement alone is not
trajectory convergence. Compare the same code and input fingerprints, declare
tolerances before inspecting results, and retain the first divergent event.

## Evidence boundaries

The private handoff preserved five replays with 44 scoreboard checkpoints.
Integrity checks do not establish correct patch, exact layout, equipment,
defensive modes, trap positions, or battle-clock alignment. Synthetic portable
fixtures validate evidence schemas and mechanics; they are not observations.
Private data and raw transcripts remain outside this repository.

The previous ground development battle reached three stars under its declared
parameters. The strict full-air run still rejects; the explicitly sampled
full-air experiment completes, with sensitivity to its unmeasured cadence.
Neither supports ranking real armies or recommending a base. Recommendations
must distinguish current game observations, expert examples, model experiments,
and unknowns.

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
