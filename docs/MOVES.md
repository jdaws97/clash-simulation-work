# M1b typed cited move registry

The registry indexes the eleven production playbooks, gives each occurrence a versioned
technique assignment or an explicit unresolved/unsupported disposition, and
reconstructs the original programs. It adds no search, human controller or
executor behavior. `test-*` books are excluded from the registry.

The implementation is in `crates/clash-plans/src/moves/`. Authoring commands
live in `clash-playbook-tools`, which now depends on `clash-plans`. The engine's
dependency closure is unchanged. Source books and frozen goldens are unchanged.

## Schema and evidence contract

`library.json` pins `schema_version`, the runtime catalog's byte SHA-256, known
mechanic-dependency IDs and `definitions`. `MoveDefinition` has an immutable
`move_id`/`definition_version` identity, `name`, template `family`, `purpose`,
actor bindings, applicability, resource requirements, static/live preconditions,
supported parameters, control, completion, evidence, evidence scope, human costs,
mechanic dependencies, attribution and a lowering rule.

Actor kinds, exact cited actor names, permitted actions and supported executable
field paths are declared per definition. Preconditions identify technique-specific requirements
such as Fireball equipment, a named Recall stash, or actual Clone recipients.
The existing compiler remains authoritative for stock, equipment, availability,
recipe feasibility and transformed dependency graphs. Definition families are
taxonomy/provenance, not army-family eligibility restrictions.

The registry schema and all 35 definition versions are now **2**; lowering is
**`typed_v2`**. `occurrences.json` holds `MoveInstance` records. Each has:

- `instance_id = source_file#pointer`, schema version, occurrence kind and a
  canonical source-record hash;
- `status` (`mapped`, `unresolved`, `unsupported`), a versioned move reference for
  mapped entries, or a nonempty reason and null reference otherwise;
- typed `MoveParameters`, described below, with no full source-record copy or
  redundant executable projections;
- applicability, explicit `scope_unverified` reasons, evidence scope, human
  costs, mechanic dependencies and attribution;
- `evidence.citations` entries with source file, exact citation JSON pointer and the entire
  original citation object, retaining video ID, timestamp and quote without
  normalization, rounding or substitution;
- `evidence.annotations` for support counts, base-reading prose, notes and
  auxiliary citations, plus `cite_present` to distinguish missing/empty arrays.

`typed_v2` reconstructs executable fields from typed values and the explicit
residual map, then restores annotations and citations from evidence. The source
book supplies only the envelope, array positions and variant-selection metadata.
There is no step-value fallback. The `source_hash` still detects source drift.
Unresolved/unsupported records also use typed reconstruction; archival lowering
does not admit those records for composition.

The checker compares source hashes, typed parameters and every citation object
and pointer, validates definition/evidence/mechanic references and coverage,
checks the existing playbook vocabulary/dependencies, regenerates the role
matrix and compares the entire reconstructed book's canonical JSON. This is
stronger than comparing only executable fields. Inventory/resource validation
stays in the existing compiler. Operators can change typed values; strict
admission checks supported fields, actions, actor kinds and evidence scope.

### Typed executable vocabulary

`schema.rs` exports the concrete types implemented in `parameters.rs`. Each
purpose uses the shared typed groups below, constrained by its definition's
`parameters.supported_fields` (including recursive predicate paths). This avoids
duplicating the vocabulary across 35 purposes while rejecting unsupported fields
on a particular move. Operators work on Rust fields, not an opaque JSON step.

| Group | Fields and meaning |
| --- | --- |
| Action | `MoveAction`: deploy, spell, ability, recall, redeploy, release_siege. |
| Actor | `what` binds the catalog hero/troop/spell/siege name; `count` is `Count::Exact`, `All`, or a preserved legacy numeric string. `level`, `origin` (`StockOrigin::Home`/`Donated`), `recall_from`, `allocated_count`, `siege_role` retain stock, stash, cohort-allocation and siege bindings. |
| Objective | `at` and `objective_at` are `Selector` values; `objective` is persistent identity. `mask_for`, `mask_hero`, `bind_before`, `target_keys`, `target_mode`, `route_hero`, `per_target`, `snipe` retain mask/route/target policies. |
| Placement | `spread` scales the executor's formation; `ahead_of` binds its screen recipient; `at_cite` controls the existing backpack placement heuristic. Edge selectors expose typed `EdgeSide::{Main,Left,Right,Charge,Funnel}` constructors/accessors. |
| Control | `id`, `group`, `packet`, `primary`, `primary_cohort`, recursive `when`/`until`, `every`, `timeout`, `after_success`, `recheck_when`, `post_recall`, `repeat_effect_remaining`, `repeat_units_absent`. |
| Activation | `ability`, `EquipmentSelection::One`/`AnyOf`, `Aim::{Arrow,Dash,At}`, `aim_count`, `required`. |
| Support | `optional`, `reserved`, `spell_budget`, `uncited`, compiler `variant` identity. |
| Completion | `completion`, `skip_if_impossible`. Observable action success and cancellation remain distinct from tactical success in the definition contract. |
| Residual | `BTreeMap<String, ResidualParameter { value: Json, reason: String }>` for unknown keys, including recursive predicate residuals. Known executable/evidence keys cannot be hidden here. Strict composition rejects residuals pending review. |

`SelectorKind` covers edge, unit, unit_ahead, group, cohort, th, threat, defenders,
defender and building expressions. Its argument retains the named actor, group,
cohort, building key or defender/group pair. `Field<T>` distinguishes absent,
explicit null and a typed value; counts and numeric strings retain canonical
identity. Fractions, distances, thresholds and delays are numeric fields.

`Condition` supports disabled predicates and typed recursive `all`/`any`, `t`,
`after`, `inside`, `group_inside`, `near_th`, `heavy_fire`, `hp_below`,
`spells_left`, `dead`, `defenders_near`, `destruction`, `effect_active`,
`effect_expired`, `objective`, `defender`, `cohort_absent`, `succeeded`, and their
`delay`, `r`, `frac`, `n`, `state`, `group` modifiers. Unknown modifiers are
explicit residuals, never discarded.

Origin follows actual executor semantics: `origin` selects home/donated spell
stock; redeploy plus `recall_from` selects a recalled stash; release_siege binds
siege cargo; Clone support targets a named unit/cohort through its selector.
Original deployments, cargo, recalled units and clone recipients remain distinct.
The executor has no direct deployment key for clone/summoned stock, arbitrary
formation/arc/offset, `target`, or configurable interruption/failure branches.
Those are not invented here. Placement uses existing selectors, spread and
book/plan geometry; interruption/recovery retains the existing executor policy.

The audit read `Step::load`, `Trigger::parse`, every direct `step.source` read in
`crates/clash-engine/src/playbook.rs`, the compiler's fitting/variant/stock/
dependency/pacing code, and every production source record. Citation quotes
still affect compiler pacing and equipment aiming. They remain in evidence and
are restored exactly for compatibility; M1b does not claim that evidence text
is execution-independent.

### Evidence-scope admission

`validate::check_instance` and `lower::lower_instance` reject unsupported typed
fields/actions/kinds and actor/equipment bindings outside citation scope.
Definition `allowed_actors` is the sorted set of source-bound actors literally
named in that definition's occurrence citations (including auxiliary citations).
The corpus checker recomputes it, preventing an unsupported actor from being
added silently. Each candidate also needs its own citations to name its actor
and each activated equipment item. Matching normalizes case/punctuation, permits
a plural `s`, and removes the ` Spell` suffix; it does not infer synonyms or roles.

The read-only corpus check permits an unchanged historical occurrence only with
the exact recomputed `scope_unverified` reasons. Clearing that marker never
bypasses strict admission. Mapped prose-only base rules also receive the marker:
they have no executable actor/purpose binding. Unresolved/unsupported records
retain their separate disposition. `lower_book` is the archival reconstruction
path; composition callers must use `lower_instance`.

**CONFIRMED:** **320/726 mapped occurrences** fail these strict scope checks:
**229 executable occurrences** and **91 mapped prose-only rules**. **406 mapped
occurrences** pass. The 13 unresolved and one unsupported record remain outside
mapped admission. These markers do not fail the archival verification gate.

**SUSPECTED:** a literal name match establishes a conservative textual scope,
not independently verified tactical support. Missing names can reflect aliases
such as “duke”, “rocket loons” or “Hydra”, or context split across quotes. M1b
does not invent that context or promote it to confirmed actor/role evidence.

**CONFIRMED:** exact citation identity and source coverage are checked offline.
**SUSPECTED:** technique purposes and parameter semantics are extraction
interpretations. Actor/purpose/order/geometry scopes are marked `inferred`;
timing is `unspecified`. `source_citations_not_reverified` explicitly records
that M1 did not acquire transcripts or independently reverify quotations.
Video timestamps are source locations, never battle delays.

Human costs have explicit fields for input sequence, slots, taps, hold duration,
gesture path, attention region and observation requirements. Unmeasured values
are null, with existing pacing retained. `M2-observation-and-human-costs` records
the unresolved observation/controller dependency. Reaction speed, precision,
attention and a composable failure/recovery policy remain later milestones.
Stored attribution records exact source reconstruction, no parameter adaptation, no
novel composition and no established real-play validation.

## Commands

From the workspace root:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-m1
export CLASH_CATALOG="$PWD/data/generated/catalog.json"
export CLASH_PRIVATE=none
cargo build --release --offline --locked
BIN="$CARGO_TARGET_DIR/release/clash"

# Refresh the skeleton. Unchanged reviewed records retain their assignments;
# new/changed records become explicitly unresolved. No automatic classification.
"$BIN" playbook moves index --root "$PWD"

# After reviewing assignments and updating definition evidence references,
# refresh the derived role matrix as well.
"$BIN" playbook moves index --root "$PWD" --roles

# Read-only registry, citations, coverage, role matrix and reconstruction check.
"$BIN" playbook moves check --root "$PWD" --report local/moves/check.json

# Reconstruct all books and compare canonical JSON; optionally write copies.
# --compiled compiles original and reconstructed books for every golden row,
# comparing both full outcomes against each other and the frozen oracle.
"$BIN" playbook moves lower --root "$PWD" --compiled \
  --out local/moves/lowered --report local/moves/lower.json
```

`--moves DIR` selects a registry directory; `--playbooks DIR` selects a source
corpus with the same logical repository-relative citation paths. `index --out
FILE` can create an independent skeleton without changing the reviewed map.
`lower --out DIR` refuses to overwrite source books. `--compiled` also works
with `check`. Explicit catalog selection follows the shared `CLASH_CATALOG`,
`BASELAB_CATALOG`, then root default policy; an identity mismatch fails rather
than silently changing applicability.

`index` does not rewrite definition evidence lists after a changed occurrence:
that requires review. `index --roles` validates those references before
publishing a refreshed role matrix. Lowering writes semantically identical JSON,
not original whitespace or numeric token spelling. Only the frozen goldens are
required to remain byte-identical.

## Counts and taxonomy

**CONFIRMED:** the current corpus has **83 variants**, **740 occurrences**,
**726 mapped**, **13 unresolved**, **1 unsupported**, and **35 move definitions**.
The design's earlier inventory had 80 variants and 703 total occurrences;
the current PB1b source tree is the inventory used here.

| Kind | Occurrences | Mapped | Unresolved | Unsupported |
| --- | ---: | ---: | ---: | ---: |
| Default step | 275 | 275 | 0 | 0 |
| Variant step | 358 | 358 | 0 | 0 |
| Spell-support rule | 3 | 2 | 0 | 1 |
| Base-reading rule | 104 | 91 | 13 | 0 |
| Total | 740 | 726 | 13 | 1 |

| Source family | Occurrences | Mapped | Unresolved | Unsupported | Distinct definitions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dragon | 90 | 88 | 2 | 0 | 22 |
| Druid/Ruin Witch | 55 | 55 | 0 | 0 | 21 |
| Electro Dragon | 63 | 60 | 2 | 1 | 16 |
| Fireball Warden | 49 | 48 | 1 | 0 | 19 |
| Lavaloon | 94 | 91 | 3 | 0 | 25 |
| Meteor Golem | 46 | 45 | 1 | 0 | 15 |
| Root Rider | 77 | 77 | 0 | 0 | 27 |
| Super Bowler | 64 | 62 | 2 | 0 | 22 |
| Super Minion Air | 73 | 72 | 1 | 0 | 24 |
| Thrower | 90 | 90 | 0 | 0 | 21 |
| Yeti | 39 | 38 | 1 | 0 | 17 |

The design's 32 starting families are retained. Cheap shoulder clearing splits
into `shoulder-clear` and `trap-scout`: the Tesla/test/Coco Balloon evidence
supports probing/screening, which is different from clearing buildings.
Two additional families fill omissions in the initial list: `clone-window`
requires an eligible cohort and Clone stock; `protection-window` uses defensive
Invisibility/Ice Block stock. They cannot safely inherit healing-wave or equipment
activation requirements. Thus there are **34 template families**, one with two
definitions and 33 with one; none of the initial families was merged away.

| Template family | Definition IDs | Count |
| --- | --- | ---: |
| Cheap shoulder clearing | shoulder-clear, trap-scout | 2 |
| Isolated heavy funnel | heavy-funnel | 1 |
| Hero perimeter walk | hero-walk | 1 |
| Exposed defense snipe | defense-snipe | 1 |
| Directed breach | breach | 1 |
| Siege Barracks flank | barracks-flank | 1 |
| Flame Flinger section clear | flinger-clear | 1 |
| Queen–Healer charge | queen-charge | 1 |
| Warden–Healer walk | warden-walk | 1 |
| Protected RC charge | rc-charge | 1 |
| Duke dive | duke-dive | 1 |
| Recall extraction | recall | 1 |
| Redeployment/transfer | redeploy | 1 |
| Giant Arrow line | giant-arrow | 1 |
| Backpack setup/dash | backpack | 1 |
| Fireball setup | fireball | 1 |
| Zap–Quake package | zapquake | 1 |
| Siege payload delivery | siege-payload | 1 |
| Ground tank/damage push | ground-push | 1 |
| Air deployment line | air-line | 1 |
| Hound–Balloon sector | lalo-sector | 1 |
| Healing support wave | healing-wave | 1 |
| Defending-unit counter | defender-counter | 1 |
| Rage/Haste window | rage-haste | 1 |
| Freeze intervention | freeze | 1 |
| Poison response | poison | 1 |
| Decoy placement | decoy | 1 |
| Overgrowth routing | overgrowth | 1 |
| Protected Revive | revive | 1 |
| Equipment activation | equipment-window | 1 |
| Safe cleanup | cleanup | 1 |
| Funnel repair | funnel-repair | 1 |
| Clone support window (added) | clone-window | 1 |
| Spell protection window (added) | protection-window | 1 |

One technique may have several source stages: Fireball activation, offensive
masking and its successful-shot finishing Quakes retain separate instances,
stock and source dependencies. An Earthquake-only stage is not a claim that
every Zapquake instance contains Lightning. Source-specific objective/equipment
requirements remain on instances, even when a definition has broad actor kinds.

## Typed coverage and residual audit

**CONFIRMED:** all **740 occurrences** use typed parameters: **636 executable
steps/support rules**, plus **104 non-executable base-reading rules** whose
prose lives in evidence. Across the executable records there are **76 distinct
executable field paths** and **6,625 typed key uses**, with **zero residual
paths/uses**. A key use counts an object key, including recursive predicate
nodes/modifiers; array indices are normalized to `[]`. Evidence, support counts,
notes, hashes and envelope metadata are excluded. There are no residual keys
requiring an exception or justification.

`moves check` and `moves lower` include the machine-readable `typed_v2` report
with `by_definition` key frequencies and strict-scope counts. The table includes
all 35 definitions and the two unmapped dispositions:

| Definition / disposition | Occurrences | Typed key uses | Residual keys / uses | scope_unverified |
| --- | ---: | ---: | --- | ---: |
| air-line | 23 | 212 | none / 0 | 6 |
| backpack | 12 | 138 | none / 0 | 5 |
| barracks-flank | 4 | 43 | none / 0 | 1 |
| breach | 15 | 142 | none / 0 | 4 |
| cleanup | 17 | 168 | none / 0 | 3 |
| clone-window | 1 | 12 | none / 0 | 0 |
| decoy | 30 | 266 | none / 0 | 7 |
| defender-counter | 6 | 57 | none / 0 | 6 |
| defense-snipe | 14 | 132 | none / 0 | 8 |
| duke-dive | 47 | 322 | none / 0 | 24 |
| equipment-window | 53 | 517 | none / 0 | 43 |
| fireball | 40 | 435 | none / 0 | 26 |
| flinger-clear | 5 | 35 | none / 0 | 4 |
| freeze | 10 | 87 | none / 0 | 2 |
| funnel-repair | 2 | 0 | none / 0 | 2 |
| giant-arrow | 18 | 144 | none / 0 | 18 |
| ground-push | 80 | 754 | none / 0 | 40 |
| healing-wave | 9 | 89 | none / 0 | 0 |
| heavy-funnel | 27 | 249 | none / 0 | 5 |
| hero-walk | 29 | 237 | none / 0 | 20 |
| lalo-sector | 24 | 223 | none / 0 | 17 |
| overgrowth | 12 | 87 | none / 0 | 5 |
| poison | 15 | 142 | none / 0 | 1 |
| protection-window | 34 | 357 | none / 0 | 9 |
| queen-charge | 5 | 19 | none / 0 | 4 |
| rage-haste | 20 | 171 | none / 0 | 4 |
| rc-charge | 8 | 34 | none / 0 | 5 |
| recall | 8 | 90 | none / 0 | 4 |
| redeploy | 7 | 69 | none / 0 | 7 |
| revive | 9 | 65 | none / 0 | 5 |
| shoulder-clear | 22 | 155 | none / 0 | 6 |
| siege-payload | 30 | 267 | none / 0 | 9 |
| trap-scout | 10 | 89 | none / 0 | 3 |
| warden-walk | 18 | 127 | none / 0 | 8 |
| zapquake | 62 | 678 | none / 0 | 9 |
| unresolved | 13 | 0 | none / 0 | 0 |
| unsupported | 1 | 13 | none / 0 | 0 |
| **Total** | **740** | **6,625** | **none / 0** | **320** |

## Role matrix

`roles.json` inventories explicit roster/loadout/action/recipient references
and catalog-named mentions in notes, including embedded alternative rosters and
summoned Firemites. Names are matched longest first so Giant Arrow does not
create a Giant reference. Guardians are not attacker-role candidates.

**CONFIRMED:** the matrix has **121 entities**: 51 troops (including summoned
and prose-only references), 15 spells, 6 heroes, 10 pets, 31 equipment items and
8 siege machines. References without supported roles remain explicit.

Each entity lists move IDs/purposes, supporting video IDs and their distinct
count, context-only video IDs/counts, and occurrence references. A video repeated
across several steps or citations counts once per entity/purpose. A source
actor, explicit equipment or unit recipient supports an inferred role. A hero
loadout alone supplies context; item-specific support additionally requires its
literal mention in the cited quote. Base-reading prose and prose-only roster
mentions do not automatically establish an actor's role. Unmapped references
remain explicit with empty purposes. Zero support is not proof that an item is
unsuitable, and source support is not population frequency or interchangeability.

## Ambiguities and open questions

**CONFIRMED:** Electro Dragon `spell_support/0` cites a wiki quote without a
video ID or timestamp. It is `unsupported`, retaining the whole citation and
its explicit 4.5-second fallback assumption. Reconstruction preserves that
existing executable policy; M1 supplies no invented video timing.

**CONFIRMED:** the 13 unresolved base rules are Dragon 2/5, Electro Dragon 5/8,
Fireball Warden 8, Lavaloon 0/3/14, Meteor Golem 2, Super Bowler 1/10, Super
Minion Air 3 and Yeti 6 (zero-based indices). They span alternative techniques,
global threat/entry priorities, attention across sections, or the unidentified
defense called "cake". Each entry preserves its specific source rule in its
reason instead of selecting a single executable move.

**SUSPECTED:** grouping single source stages into reusable multi-input packages
will require more precise completion/failure semantics. Human costs, observation
permissions, unknown stock origins/capacity, source-unspecified TH/mode/patch,
loadout-only pet/equipment roles and exact geometry/timing remain open. Existing
source notes about controller approximations survive; successful reconstruction
does not independently validate those approximations or establish real-game
calibration. Review new usage research before broadening any role or parameter.

## M1b verification receipt

Commands ran offline with `CARGO_TARGET_DIR=/tmp/clash-target-m1`,
`CLASH_PRIVATE=none` and the pinned `CLASH_CATALOG` shown above:

```sh
cargo test -p clash-plans moves --release --offline --locked -- --nocapture
cargo clippy -p clash-plans -p clash-playbook-tools --all-targets \
  --release --offline --locked -- -D warnings
cargo build --release --offline --locked
/tmp/clash-target-m1/release/clash playbook moves index --root "$PWD" --roles
sha256sum -c local/moves/m1b-registry-before-index.sha256
/usr/bin/time -f '%e seconds' -o local/moves/typed-check-time.txt \
  /tmp/clash-target-m1/release/clash playbook moves check --root "$PWD" \
  --report local/moves/typed-check.json
/tmp/clash-target-m1/release/clash playbook moves lower --root "$PWD" \
  --compiled --out local/moves/typed-lowered --report local/moves/typed-lower.json
cargo fmt --all -- --check
scripts/verify.sh /tmp/clash-target-m1
```

**CONFIRMED:** ten focused tests passed; strict Clippy and release build passed.
Refreshing the index and roles kept all three registry files byte-identical.
`moves check` passed in **8.46 seconds** and is included in `scripts/verify.sh`.

**CONFIRMED:** the single mutation known-answer test uses frozen synthetic case
`meta-armies-2026-10-15.json:mass-dragons-18-1`, angle/seed zero. It changes only
the default Dragon book's Warden `Selector` side from `Main` to `Left`, lowers
and compiles it, and compares the entire compiled plan against the original
golden with exactly `/steps/7/at` changed from `edge:main` to `edge:left`.
Separate negative checks reject a Rocket Balloon snipe rebound to Dragon and
an unsupported typed `spread` field, and prove unknown fields survive in
explicit residual maps while known keys cannot be hidden there.

**CONFIRMED:** all **11** books reconstruct with identical canonical JSON,
including all 740 source records. Original and reconstructed compiler outcomes
both match all **1,354** frozen plan rows, including **669** production-playbook
cases and **139** identical rejections; **zero differences**. Rejections count
as preserved rejection behavior, not successful plans. Existing logged-army
replay-handling diagnostics remain unchanged.

**CONFIRMED:** `cargo fmt --all -- --check` and
`scripts/verify.sh /tmp/clash-target-m1` passed with exit status **0**, ending in
**`ALL CHECKS PASSED`**. The gate includes workspace release build/tests and
strict Clippy, **868/868** battle cases at both one and four workers,
**1,354/1,354** plan cases, the new registry check, **50** guardian fixtures,
army-search proofs, **100,000** layout mutations, base-search proofs and the
**24** video tests. Logs and reports remain in ignored `local/moves/`.

Fresh `moves index --out local/moves/m1b-fresh-skeleton.json` also produced all
**740** records as explicitly unresolved, without changing the reviewed map.

The before/after frozen SHA-256 identities are:

```text
cea706d86516a2100876f9aa4ec7cdd5de32f691202f9a6d049b64e690d172ab  cases.jsonl
40446127d538f7bab2a86ab9c7fcae8b3a725c4ceb462fd2d95236cb38af0ab4  expected.jsonl
60dbb24903bb2c0443abf4624e0231e5f33e083492fac571b187a830dcc47958  plans.jsonl
```

For read-only Git checks in WSL, the worktree's Windows-style `.git` marker was
mapped through `GIT_DIR=/mnt/c/Users/jarod/Documents/clash-lab/.git/worktrees/m1`,
`GIT_WORK_TREE="$PWD"` and `GIT_OPTIONAL_LOCKS=0`. No Git metadata was edited and
no commit was made.
