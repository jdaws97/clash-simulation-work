# Base search contracts, M0 / schema 1

Scope: the M0 contracts and M1 layout implementation. Rust is the reference.
The native M3–M6 coordinator is documented in
[clash-basesearch](../crates/clash-basesearch/README.md). This contract follows the complete
[design](BASE_SEARCH_RUST_DESIGN.md), [review R3](history/RUST_REVIEW_2026-10-25.md),
and [golden policy](GOLDEN.md). Evidence here is model/synthetic correctness,
not real-game calibration. The historical milestone receipts are under `history/`.

## Schemas and admission

The public Rust API is `baselab_engine::layout`. Its model types live in
`crates/clash-layout/src/model.rs`; `AdmittedLayout` lives in `admit.rs`. Layout schema
1 retains legacy JSON fields: buildings, walls, traps, ordered heroes,
cc_troops, guardian, levels, hero_levels, wall_level, wall_levels, town_hall,
name and notes. Absent fields use frozen `Layout.from_json` defaults, except
name is optional to accept the prepared engine corpus. Empty/null modes use
the engine default. Integral numbers such as `4.0` are accepted. Booleans,
strings, fractions, nonfinite and out-of-i32 coordinates are rejected before
conversion. Unknown modes and duplicate object fields are rejected.

Building/trap arrays retain order. Hero list index i binds to banner i in
building order; `HeroBinding` makes that relationship explicit. Reordering or
changing assignments requires rebinding and admission. CC string entries and
objects with name/type, optional level, count and source are supported. CC
levels are validated against donor TH18 and their effective receiving caps
are recorded, matching setup's clamping. No synthetic CC bypass is enabled.
The legacy Longshot default below TH18 is inert metadata. Active guardians
require TH18 and a Town Hall. Crafting admits only the catalog's phase-4 modes
with setup's fixed default date/phase; unsupported seasons are not invented.

The additive top-level `layout_schema: 1` and `instance_ids` object carry one
nonempty globally unique ID per building/wall/trap. Legacy imports receive
b0000/t0000/w0000 IDs in input order. These IDs survive extended JSON round
trips and movement; Python's legacy reader ignores the top-level extension.
Moving a `WallPiece` moves its level override. Effective wall levels are
materialized by admission; an override without a wall is always an error.
Walls may be disconnected. Duplicate wall coordinates are rejected instead
of silently deduplicated as the Python set constructor does.

`AdmissionIssue` has code, JSON path, instance IDs, coordinates, expected and
actual. Import syntax errors can fail early; semantic errors aggregate in a
stable order. `ContentError::Unsupported` remains the direct setup error for
unknown supported-content categories. The setup integration invokes shared
content checks without imposing full inventories or spatial search policy on
small synthetic battle fixtures. Physical admission rejects all footprint
collisions, including buildings/walls/traps, and checks every occupied tile.

`AdmissionPolicy` independently selects full inventory, every-owned-wall
placement, inventory source, and hole policy. `require_full=false` waives only
missing building/trap inventory. Optional crafting may be omitted in full
mode. Wall count is always bounded; requiring every wall is a separate flag.
Hole policies are Allow, Forbid or a finite nonnegative per-tile penalty.
Holes are not a universal legality error.

`InventoryPolicy::FullyMerged` explicitly labels a TH16–18 model preset,
including account-level overrides carried by a layout. `Owned` accepts a named
normalized account snapshot: building/trap quantities, wall count, fixed
building/trap/hero levels, default and optional mixed wall-level multiset, and
owned gear-up keys. Counts are checked against unlocks and consumed merge
sources. Every used owned level must be explicit; layout overrides cannot
upgrade it. Mixed wall placements consume a subset of the fixed owned level
multiset. Account snapshots are input contracts, not authenticated account
ownership evidence. Gear-up eligibility also requires the positive game-data
GearUpCost/GearUpLevelRequirement and minimum home-building level.

Only `admit` constructs `AdmittedLayout`. It owns a validated immutable Layout,
rules/catalog/account identities, policy, effective CC levels and hole count.
Read-only getters and `engine_json` expose it. A proposal clones the Layout and
must be admitted again; evaluation in later milestones accepts this receipt.
Admission is scoped to the matching catalog/rules pair. The CLI rejects a
catalog fingerprint mismatch; the proof regenerates the rules from inputs.

## Rules and geometry

`layout import-rules <repo-root> <output.json>` derives rules schema 1 from
`data/source/clashking-static-data.json` and the explicitly selected engine catalog.
It accumulates TH unlock quantities, consumes every first-level merge recipe
per owned product and each TH-upgrade merge once, and retains exact source
JSON pointers, source/catalog fingerprints, footprints, TH16–18 inventories,
level limits, mode unlocks and capacity source fields. MAT/ricochet consume two
sources each; MGT consumes geared AT+Cannon; TH17 consumes Eagle; each SWT
consumes two WT. TH18's additional WT unlock is included before SWT merges.
Seasonal Crafting Station=1 optional at TH16–18, four banner markers, the TH
itself, and trap footprint fallbacks are explicit cited model overrides.
Catalog BuildingType.count is never used as a TH inventory.

Deployment masks dilate building footprints (including banner markers) and
wall tiles by one tile. Hidden Teslas and traps contribute nothing. Mask
coordinates are village-relative; adding catalog margin gives setup's world
mask, including its cells outside the village. Outside regions ignore
buildings and flood the 44×44 village from legal edge cells through non-wall
tiles. Compartments are enclosed wall-only eight-connected regions; the QD
descriptor later counts those of at least four tiles. Drop holes flood all
unblocked tiles in [-3,47)² from the outer edge, then group the remainder.
All these floods use eight neighbors, allowing diagonal wall gaps. Runtime
navigation remains the engine's half-tile grid with building-hitbox corner
restrictions; it is not replaced with tile geometry. `scoring::hole_tiles`
uses the shared eight-way implementation. Its former four-way result is an
intentional scoring correction, not a change to battle navigation.

## Identities, policies and objectives

Schema and objective versions are explicit. Deterministic fingerprints use
FNV-1a/128 with a `fnv128:` prefix, over the documented ordered canonical JSON;
they detect regressions, not malicious tampering. Names, notes, schema tags
and lineage instance IDs do not affect physical identity. Building/trap,
hero/banner and CC order, positions, modes, guardian and effective selected
levels do. Wall ordering is canonicalized because setup sorts it. Account
identity uses fixed inventory and the level ledger and wall-level multiset,
not wall coordinates. Proposals preserve IDs and account levels; metadata
and lineage identities are separate from physical/evaluation identity.

`SearchConfig` is a Rust type, not an implemented search runner. It freezes
objective, battle mode/modifier, admission policy, separate development /
confirmation / final manifests, logical and physical budgets, operator
weights, descriptor/archive definitions, independent proposal/battle seeds,
and engine/rules/catalog/compiler/knowledge/execution-profile identities.
Scenario IDs bind complete scouting groups and population weights; worker
allocation never changes those weights. Confirmation repeatedly consulted for
selection is development data. Final manifests cannot influence selection.

Reuse `scoring::objective`; do not add a second scorer. RankedV1 maximizes
expected defender trophies minus `0.00005 * avg_destruction` and hole penalty
(default 0.25/tile). WarV1 maximizes `100*(1-three_star_rate) - 10*avg_stars -
0.05*avg_destruction` minus hole penalty (default 0.8/tile). Raw ordinary-meta
scores, penalized objectives and discovered-attack robustness remain separate.
Future minimax/CVaR/PSRO measures must be versioned archive metrics; a searched
attack is not population prevalence. Modifier and attacker TH are explicit.
Visible-state scouting commits before actual hidden-state execution; committed
outcomes are summarized with scout=1. Complete-group cost is reserved before
dispatch, counting planning, execution, cache hits and diagnostics separately.
Screen/confirm/final defaults are approximately 20/68/400 independent groups,
not physical-battle counts; a two-side, three-hidden-sample group costs seven.

Evaluation/cache/checkpoint identity must additionally bind the executable,
rules/catalog, physical/account state, modifier/mode, compiler/program,
scouting knowledge, profiles, scenario-group manifest, seeds, and attack
archive version. Keep proposal RNG separate from battle RNG. Archive growth
invalidates old comparisons. Resume restores raw paired rows, budgets,
lineage, RNG, pending cursor and wave boundary; a layout-only archive cannot
certify exact continuation. Freeze finalists/order/attacks before final data.

## Ownership and exit gates

Layout owner: `crates/clash-layout/**`, `data/generated/base_rules.json`, small
`fixtures/layout/**`. For M0/M1 the layout owner is integration lead for
the narrow lib/main declarations, setup fallible-content call and scoring
geometry adapter. Preserve all other writers' work. `crates/clash-vidmine/**` belongs
to its existing writer. Read-only reviewers do not gain write ownership.
Future owners use the design's disjoint proposal/evaluation/search/oracle/
reporting modules; shared-engine edits require integration coordination.

Acceptance fixtures: `fixtures/layout/{inventory,admission,geometry}.json`.
The Rust `layout proof` gate checks data regeneration, count snapshots,
structured boundary verdicts, full synthetic packings, geometry, committed
reference corpus, 100,000 deterministic mutations (every acceptance builds
and matches engine deploy masks), and 1/4/16-worker admission determinism.
No Python process is run. Frozen Python verdict comparison requires previously
saved verdicts; source-read fixtures are not represented as executed parity.
The 868 battle goldens must pass unchanged, plus existing army-search proofs
and cargo fmt. Proof receipts bind executable/input identities. They certify
model correctness only; report any missing evidence explicitly.
