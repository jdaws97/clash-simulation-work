# Conditional layout pipeline

This adds separate layout/inventory/scene-builder modules on frozen integration
commit `3a814ec6a36f06de3f2165b0c9da0df2a0b43972`. It changes no shared combat,
adapter, spell, siege, Castle, resource, spatial or termination implementation.
No best layout, live buildability, population win rate or calibrated outcome is
established. The user's manually built V3 is never an input. An illustrative
opponent screenshot is likewise not a generator input, fitness term or weight.

## Reproduce

Run from the checkout with its Python environment (no install required):

```
python -B tools/build_layout_search.py --output ../layout-evidence
python -B tools/run_layout_ensemble.py ../layout-evidence/all-cases.json --output ../compile-evidence
python -B tools/run_layout_ensemble.py ../layout-evidence/smoke-simulate.json --output ../battle-evidence
python -B verify.py
```

Output directories must be new. The build reuses the exact six architecture
families selected by `build_candidate_bundle.py`: ranked and CWL versions of
staggered compartments, split core and offset ring. It also makes two explicit
synthetic packing fixtures per higher TH (one per mode). Each seed gets one
bounded deterministic equal-footprint defense swap, preserving wall topology.
This is a first bounded local variation search, not a broad strategic optimizer.
Higher-TH packing is a coverage fixture, not a designed strong defense.

The 20 outputs include all buildings/traps/walls, selected Station modules,
input hashes, seed/parent provenance, exact changed objects and aggregate moved
object/tile counts. Cost is edit effort, not gems, resources or upgrade advice.
`generation.json` also reports candidate isolated deployment cells. Such
pockets remain weaknesses to inspect, never a readiness approval.

The planned 128 cells match an original and its variation at TH16 for each mode,
all three attacker THs, two families, two entry directions and two ability
schedules. Smaller paired cells cover the other two architecture families and
all selected crafted variants. Additional TH17/18 defense cells expose coverage
gaps. The 12-run smoke sample spans modes/THs/families, original/variation pairs
and all three architecture/weapon choices but is insufficient to rank layouts.
The fractional grid is explicit; not every dimension has a full Cartesian
cross with every layout. West/east are model coordinates; east is a held-out synthetic input,
not held-out game evidence. No adaptive selection consults held-out outcomes.
No arbitrary occurrence weights or trophy estimate is added. War is supported
by the case contract but is not part of the supplied ranked/CWL sample.

## Inventory and deployment contracts

`selected_inventory(catalog, town_hall, merges, crafted)` requires all four
merge counts (zeros included). It conserves source Cannons, Archer Towers and
Wizard Towers across Ricochet, Multi-Archer, Multi-Gear and Super Wizard merges.
The Hall/Eagle transition follows the pinned TH-specific catalog. Exact full
selected counts, catalog footprint agreement, overlaps, board bounds, levels,
destruction flags and duplicate IDs are validated before evaluation.
This checks source conservation, not all live construction prerequisites or
actual account availability. Unknown levels/settings are not filled from photos.

One physical 3x3 Station holds one selected shared `crafted_selection` contract.
The official [July 31 announcement](https://supercell.com/en/games/clashofclans/blog/news/the-awesome-quest-is-here/)
establishes August's TH11+ access. It does not certify October rotation. The
example explicitly selects phase 4, independently level-1 modules and opt-in
experimental weapon policies. Actual account module levels remain unknown.
`data/battle-policies/layout-search-crafted-experimental.json` supplies each
weapon's unresolved projectile, poison, target and Candle clock choices. It
does not assert those choices are observed mechanics.

`deployment_mask(layout, catalog, policy)` models initial tile-center territory.
Policy must name square or orthogonal one-tile rim, whether Hero Banners create
territory, and initially hidden Teslas. Hidden Teslas, traps, decorations and
obstacles do not create exclusion. Live edge/corner taps, revealed Teslas,
destruction, Recall and special deployment permissions remain unverified.
Four-neighbor flood fill groups isolated pockets and separately labels cells
inside walls; an edge-connected ground path is NOT needed for deployment.
Both rim models are emitted so uncertain corners cannot be hidden by one pass.
`inspect_deployments` gates initial paid deploy commands only. Padded simulation
board edges are an explicit open-board hypothesis, not verified game red lines.

## Integration hooks and remaining contracts

`build_layout_scene` assembles the authoritative complete layout and binds the
selected active Station. `layout_higher_assembly` preserves the explicit merge
counts, including partial TH17/18 selections, through the existing shared
defender helpers and experimental policies. It retains the source checks for
four distinct heroes, non-supercharged buildings and destruction conventions;
it does not replace selected inventory with maximum merges.
`bind_selected_station` requires exact selected module
parity with its combat policy and supplies `crafted_shared_binding`. The shared
compiler still validates every raw weapon/source/policy. `assert_crafted_compiled`
rejects a passive or unwired Station. Finite paid execution, source loss, range,
projectile/poison and melt behavior remain owned by the existing crafted kernel.

`prepare_case` composes full benchmark air and ground armies with their pets,
equipment, siege and donated contents. It derives per-TH Lab/camp/Castle caps
from the snapshot and keeps fixed benchmark troop quantities explicit: higher
TH armies may be underfilled and are not a model of maximum opponent strength.
An assembly-only TH16 hero projection accommodates the old builder's hardcoded
temporary hero compile; exact selected levels/TH are restored before the shared
compiler validates the final paid army. No combat stats are copied from TH16.
Entry reflection affects attack deployment/spell coordinates; the base and its
directional defenses stay fixed. Ability schedules are the existing schedule
or an explicit five-second delay. Neither represents human timing probabilities.

TH17/18 mixed-army defense requires the integration owner's Giga Bomb response
roster: exact troop/hero/pet/generated-child IDs, trigger weight, damage response
and push response. The old fixture's 16-dragon-only roster is rejected. Do not
silently drop Giga Bomb, keep wrong weights or label a failed run a defense win.
Future generated-army work may supply a ready bundle instead of `prepare_case`:
`case`, `specification`, `account`, `army`, `layout`, `deployment_policy`.
The authoritative `layout.inventory_selection` and full scene must agree.

Every ready case now requires `case.candidate_layout_sha256`, registered from
`candidate_layout_sha256(layout)` before execution. It hashes the actual padded
simulation layout with complete building/selection/settings content, sorted by
instance; human labels and generation receipts do not define identity.
`case.candidate_id` must also equal `layout.candidate_id`, and case/specification
IDs must match. Summaries include the canonical digest and reject a human label
mapped to multiple contents. Caller-controlled labels are not global identity;
the canonical digest identifies what was actually evaluated.
The generator registers this field automatically. Older frozen bundles remain
historical evidence; a new ready bundle must explicitly register its unchanged
layout before using the new interface. Do not retroactively promote old receipts
into new-engine outcomes or rewrite the old input artifacts.

## Outcome integrity

The serial runner retains the initial manifest byte hash, ALL planned input
digests and the engine/data fingerprint before it starts any worker. Worker
receipts never replace these parent expectations. Workers receive expected input
and engine digests; prelaunch, postworker and final checks reject changes to
the manifest, own input, later inputs or previously processed inputs. Returned
worker case/engine/input identities must also match the retained expectations.
The runner
sets a per-process wall bound and stores terminal evidence/resource receipts.
Compile-only, unsupported, error, killed and timed-out cells have `outcome: null`.
Completed results need a matching termination reason and time; the complete
combat result is retained compressed and hashed. A partial run never becomes a
zero-star attack or defensive success. Failed preparation cells stay in the
matrix with the exact reason, rather than disappearing from the denominator.

Summaries separate candidate, mode, attacker TH, defender TH and search/held-out
split. They report worst observed stars/destruction with its complete case and
missing coverage. Full-grid worst and unweighted grid means are unavailable if
any planned cell is missing. Grid means describe only that synthetic grid, not
the user's opponent mix. No overall winner is returned. Independent review and
held-out real replay calibration remain separate missing gates.
