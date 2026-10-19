# Crafted-defense domain source and shared binding notes

The original domain delta below was independently conditionally cleared at
36f27465bed96d7c73c82377ed97d0c35e57a3f8. Shared stage6 now implements the hooks
and paid TH18 checks described in [CRAFTED_SHARED_CHECKPOINT.md](CRAFTED_SHARED_CHECKPOINT.md).
Its independent shared recheck is pending. The domain supports experimental
TH16-18 module gates; the shared full-battle adapter deliberately retains the
permanent TH18 Station unlock. No temporary lower-TH season availability is inferred.

Base: ae58eefacf01a2bab990bbfe02dc14644e32c0a7. This patch contains only
crafted_defenses.py, its representative contracts, and these source/binding notes.
Integration owner: 01a1085e-47bd-74f0-af55-d61c2f8230c2. No shared kernel edits.

## Selected rotation and evidence, checked October 4, 2026

Last officially confirmed trio: Cake-A-Pult, Hero Hunter, Hot Candle. Supercell's
July 31 announcement explicitly introduces those selections August 1 and temporary
TH11 availability. The saved catalog calls them phase 4 / isCurrent=true; the
secondary Crafting Station seasonal_defenses contains the same data IDs and
module rows. August 30 notes explicitly correct Candle melt starting during
scouting: it starts when battle begins. October 1 announcement and current official
archive do not announce a replacement. This is evidence reconciliation, NOT proof
that this trio remains available on October 4. Automatic current-season selection
is deliberately unavailable; every instance names phase/date/conditional policy.

Primary sources:
- https://supercell.com/en/games/clashofclans/blog/news/the-awesome-quest-is-here/
- https://supercell.com/en/games/clashofclans/blog/release-notes/august-update-3/
- https://supercell.com/en/games/clashofclans/blog/news/cosmic-curse-portal-panic-teleports-in/
- https://supercell.com/en/games/clashofclans/blog/

Saved statistics: catalog commit c6967314d7281bb87c362993e2635e58cd77b351,
data/home/crafted-defenses/{cake-a-pult,hero-hunter,hot-candle}.json. Exact source
URLs remain in compiled model catalog_source. Secondary pinned extraction
b8f42a707fe92d5293d46088bf536450ae422e7b, data/clashking-static-data.json,
buildings entry 1000097 -> seasonal_defenses 103000011/12/13.

Modules are independent levels, never averaged/summed into one weapon level.
Compile selects each module's dataId+level, checks secondary required_townhall,
crosschecks selected HealthOverride, AttackSpeed/1000 and Damage or DPS conversion.
This resolves saved Station TH18 versus season-specific TH11: domain scope is
TH16-18 and uses exact seasonal module TH gates rather than globally lowering the
permanent Station unlock. Unknown/missing rows and mismatched sources fail closed.
Hot Candle Seconds Active is catalog-only: secondary effect ability_data is empty.
Cake explosion amount is catalog-only; secondary exposes HitSpellLevelOverride,
not the actual explosion damage. These quantities remain unverified snapshot data.

## Implemented conditional lifecycles

Cake: launch eligibility range 3-12, cadence 3 seconds, independently selected HP,
shot damage and explosion damage. Fixed launch-sampled primary center is explicit
projectile hypothesis. Landing splash radius 2.5 uses live hostile ground/air unit
footprints and plants a separate bomb with saved 3-second delay/radius 2.5. Primary
death does not erase landing/bomb, and released packets persist Station death.
Damage buff is sampled at release; both stages use shared damage receipts/protection.

Hunter: range 9.5, cadence .6, selected DPS converted once to per-hit amount, saved
2x hero bonus. Explicit hero-first nearest/id selector uses healing_class=hero;
it does not accidentally classify Pets as Heroes. Poison Level crosschecks secondary
PoisonOnHitSpellLevel then obtains selected poison-spell max DPS and move/attack slow
rows. On hit creates a shared PulsedHazards field with saved 3-second duration.
Field geometry/pulse grid/growth/linger/exclusions/protection are explicit supplied
experiments. Impact-anchored field is NOT certified as the actual on-hit poison
membership (attached-target DOT vs area remains unknown). Existing shared scheduler
owns all poison clocks, stacking, protection, expiry, receipts and source-loss rules.
Poison source template validates before battle, not after a launch spends its clock.

Candle: range 10.5, cadence .5, selected per-flame DPS converted to per-hit amount.
One shared weapon clock releases at most distinct live eligible targets: 6 until
selected Seconds Active expires, 4 until explicit second decay interval expires,
then 3. Melt clock begins at battle zero, never scouting. Freeze suppresses launches;
whether it pauses melt is unknown, so continuing melt is explicitly experimental.
Queued flames retain launch capacity and persist source loss. Exact melt boundaries
are returned even without a target, so a step cannot skip a capacity transition.

## Exact adapter and dispatch bindings for integration owner

1. Shared instance validator: add crafted_parameters ONLY to crafting-station;
   require one counted stationary Station at spawn_seconds=0, level1, normal mode,
   no supercharge. Reject crafted-defense category as independently counted actors.
   Preserve one Station destruction credit/footprint and no additional module actors.
   Enforce at most one selected Station (seasonal module rows do not establish count).
2. Before normal catalog available/empty-weapon checks, produce base Station actor
   and call compile_crafted_defense(actor, instance, catalog, secondary_station),
   where secondary_station is the exact pinned buildings ID1000097 dictionary.
   Do not compile the permanent empty Station as equivalent battle support.
3. Register WEAPON_KIND='crafted_phase4_weapon' with exact {kind,source} fields in
   shared validate_pattern. PatternCombat.launch MUST reject this tag unless the
   dedicated dispatch runs; no single/radial fallback. The shared tag is now
   registered and the generic launch explicitly rejects it. Domain tests use the
   ordinary loader; the former isolated test shim has been removed.
4. Construct one CraftedDefenseCombat(actors, shared_pulsed_hazards) after loading
   actors and shared hazard class assignment. Hero Hunter requires that scheduler.
   Attach the SAME damage_receipts service used by all other weapon runtimes.
5. In shared launch loop, handle crafted IDs before generic _can_attack's damage>0
   check (actor.damage=0 intentionally prevents fallback). Call launch(id,time,trace)
   once; it owns selection and advances existing next_attack using attack_rate.
   Route exact range-entry/freeze/first-ready/cooldown boundaries to this launch.
   Do not call generic weapon launch, advance the clock twice, or freeze queued shots.
6. Resolve crafted impacts before shared hazard status/resolve at the same boundary,
   so a Hunter hit can schedule a first Poison pulse at its specified offset.
   Add returned damage to SAME simultaneous damage map and one _apply_health call.
   No domain direct HP mutation or duplicated post-health death settlement.
7. Include crafted.next_boundary(time) in event frontier. It reports every strictly
   positive projectile/bomb/melt boundary, without EPSILON coalescing. resolve(time)
   requires the exact queued boundary and rejects skipping it. Clock-ready/Freeze
   and live range entry remain existing shared spatial kernel responsibilities.
8. Include crafted.continuation_reasons(time) in BattleTermination providers;
   released bombs survive source loss, with source_team=defense and due time.
   Existing shared hazard continuation facts cover scheduled Poison pulses/expiry.
   Add result() to output provenance; never report current-date certified support.
9. New full-battle certification owned by lead: launch Cake, kill source/primary,
   move an air/ground target into/out of bomb membership, settle delayed damage;
   Hunter hero priority/bonus plus shared protection/slow/poison after source loss;
   Candle frozen across first melt with mixed layers and distinct target caps.
   Use bounded fresh zero-exit results and no suspect runner blind retries.

## Bounded evidence and remaining capture question

Four representative tests cover actual domain launch/resolve/shared poison
interactions, source and primary loss, delayed continuation, live splash membership,
hero bonus, independent TH module rejection, battle-zero melt/Freeze, mixed layers,
and preserved generic PatternCombat rejection. They are synthetic conditional
contracts. Separate shared full-battle evidence is listed in the linked checkpoint;
neither set establishes current-game calibration.

Needed current UI text (no game automation/memory capture): which three selections
and season countdown does the Crafting Station display on October 4? Does it show
the same module levels and battle stats? Missing exact fields: Hot Candle second
melt interval/trigger and Freeze behavior; Hunter attached-target vs area poison,
radius, pulse/growth/stack/refresh/linger/protection and Hero/Pet classification;
Cake projectile travel/landing splash layers, whether bomb survives primary loss,
precise bomb delay/radius and immunity/status interactions. Current conditional
inputs visibly name these assumptions; no historical variant is implemented as
current and no unsupported field is silently assigned a game-fidelity default.
