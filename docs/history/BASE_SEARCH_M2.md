> Predecessor Python filenames and parity procedures in this document are
> historical provenance from `f04706c`. Deleted tools are not runnable; see
> [the current documentation](../README.md) for native commands and remaining Python ports.

> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Rust base search M2: proposals

M2 adds `baselab_engine::basesearch` on top of M1 layout admission. All
fixtures and proof objectives are declared synthetic model checks, not
real-game calibration. Python remains frozen and is never executed.

The API is a proposal library, not the M3 battle evaluator or M4 QD runner.
`Context` supplies matching rules and catalog. Operators, generation and
crossover take immutable `AdmittedLayout` parents. An accepted `Proposal`
contains an admitted candidate, logical seed, parent physical identities,
changed instance IDs and repair actions. A rejected transaction returns a
structured `Rejection`; the parent is never modified.

- Local/setup operators: nudge, same-footprint swap, long relocation, trap
  relocation, building modes/facings/gear, skeleton air/ground, hero/banner
  permutation, hero selection, CC packages and guardian selection.
- Wall operators: single relocation, run shift, partition split/merge,
  Town Hall ring and seam closure. Every wall retains its ID and level.
- Macro ideas ported from frozen `macro_moves.py`: role repacking, deepest
  TH, strongest/splash inward, AD/Fireball spread, outer screening, core
  rotation, core/flank exchange, transpose and traps toward the core.
  Slot matching uses equal footprints and updated TH17/18 defense roles.
- Guided moves: typed ground/air/hero traffic for traps, busy-region defense
  swaps, early-lost defenses deeper, and reinforcement behind breaches.
  Supplied diagnostics must match layout, account and evaluation-policy
  identities. M2 supplies synthetic diagnostics, not a battle diagnostic
  collector.
- Generators: grid, offset, rings, wide, binary-split freeform, Voronoi
  organic, cram, onion and scatter. Structural walls are reserved first;
  buildings and traps use one packing board; remaining owned walls fill
  legal space. Each supports explicit central/mid/edge TH sampling.
  `preset` resolves TH16–18 quantities from `BaseRules`, never catalog
  building counts. `generate` preserves an admitted account template.
- Spatial crossover requires the same ordered owned IDs, inventory, levels
  and admission policy. It cuts parental positions/modes spatially, repairs
  seam collisions near selected parental positions and records both parents.

Repair restores missing known pieces in parent order, rejects unknown IDs,
key/level changes and duplicate IDs, normalizes duplicate/merged gear
allocations, retains unaffected footprints, and reseats conflicts under
explicit tile-check and relocation limits. It never upgrades account levels.
Admission enforces modes, levels, housing, hero unlocks and hole policy. A
forbidden hole that survives the structural proposal is a typed rejection;
M2 does not silently relax the policy or add wall inventory. Search moves
remain proposals, not claims of better defenses.

`anneal` maximizes an injected finite objective on a fixed logical budget,
using a linear temperature schedule and the engine's deterministic
exponential. It retains best and current states separately, checks proposal
lineage/account compatibility and records its trajectory and rejection
counts. Production evaluation must reuse `scoring::objective` through M3;
M2 does not introduce a competing battle score.

Run in WSL, using only installed Rust tools:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-bs
export BASELAB_CATALOG="$PWD/rust/data/catalog.json"
cargo build --release --manifest-path Cargo.toml --bin baselab-engine
/tmp/clash-target-bs/release/baselab-engine basesearch-proof . /tmp/basesearch-m2-proof.json 2048
rust/verify.sh /tmp/clash-target-bs
```

The proof receipt binds executable, catalog and rules identities. Coverage
rows record attempts, accepted engine builds and typed rejection counts per
TH/operator and per generator/style/TH zone. Additional checks cover mixed
wall levels, restoration of missing pieces, failed-repair immutability,
repair budgets, illegal content/level rejection, duplicate gears, stale
layout/policy diagnostics, transpose round trips, crossover account mismatch,
repeatability and 1/4/16-worker determinism. A four-state enumerable objective
has a unique optimum behind a downhill step; positive-temperature annealing
must find it while zero-temperature search stays at the local optimum.

The regular Rust unit gate runs a smaller version of the same proof. Full
proofs and existing battle/plan goldens are independent gates. No golden
expectation is recorded or changed by M2.

Validation in this worktree on 2026-10-25, starting at `b9f7885`:

- Full M2 receipt: 190,464 operator attempts (2,048 per TH/operator),
  167,834 accepted engine builds, every operator covered, 316 admitted
  generator outputs from 324 attempts across all 81 TH/style/zone cells,
  6,144 accepted crossovers, and 104 owned-account engine builds.
- 849 deterministic jobs compared across 1/4/16/1 workers. The enumerable
  four-state annealing objective reached its unique score-5 optimum;
  zero-temperature search remained at the score-1 local optimum.
- Release build, all 18 library tests, all 868 battle goldens, 50 guardian
  fixtures and the existing 4,096-case army-search proofs passed.
- The required `rust/verify.sh /tmp/clash-target-bs` stops at `fmt` because
  the checked-in example `rust/examples/mechanics_proof.rs` references the
  absent `rust/tests/support/mechanics.rs`. The M2 files and narrow lib/main
  wiring pass a separate `rustfmt --check`.
- Independently, plan goldens pass 823/1,196 cases. All 373 failures select
  Rocket Spear level 21 where the reference expects 23. A separate binary
  built from untouched HEAD reproduces precisely these 373 failures with
  the same inputs. M2 changed no compiler, playbook, account-data or golden
  files. No golden was re-recorded; the gate is blocked and no commit made.

The executable-bound receipt is `/tmp/basesearch-m2-proof.json` (26,011 bytes).
The baseline plan comparison is `/tmp/clash-bs-baseline-plan-check.txt`;
the required-gate output is `/tmp/clash-bs-verify.txt`. These are local proof
artifacts, not tracked claims of real-game calibration.
