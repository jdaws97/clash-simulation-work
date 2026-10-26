G5a layout (2026-10-25): current workflows are Rust only. Runtime artifacts
live in `data/generated/`, inputs in `data/source/`, and derived work in ignored
`local/`. The lane receipt below preserves its original scope; see
[ARCHITECTURE.md](../../docs/ARCHITECTURE.md) for current dependencies and paths.

# Native base search, M3–M6

This crate extends the admitted M2 proposals with a native evaluator, racing,
QD coordinator, attack archive, double-oracle adapters, diagnostics, trap polish
and winner reports. All battles use the existing v29 engine and scorer. No
Python process, subprocess army-search CLI, network access or new dependency
download is needed.

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-lA
cargo build -p clash-cli --release --locked --offline
/tmp/clash-target-lA/release/clash basesearch smoke --out /tmp/clash-lA-smoke --threads 4
/tmp/clash-target-lA/release/clash basesearch run --config run.json --out /tmp/my-search --threads 4
/tmp/clash-target-lA/release/clash basesearch run --config run.json --out /tmp/my-search --threads 16 --resume /tmp/my-search/checkpoint.json
/tmp/clash-target-lA/release/clash basesearch proof-completion --out /tmp/clash-lA-proof
```

`clash basesearch proof` retains the original M2 proof entry point. The workspace
gate runs the focused M3–M6 tests as part of `cargo test`.

Example bounded run configuration:

```json
{
  "synthetic_account": true,
  "town_hall": 16,
  "mode": "ranked",
  "modifier": null,
  "seed": 137,
  "battle_seed": 8191,
  "final_seed": 99823,
  "waves": 2,
  "batch": 3,
  "physical_battles": 2400,
  "screen_groups": 10,
  "confirm_groups": 10,
  "gate_groups": 10,
  "final_groups": 10,
  "oracle_budget": 28,
  "oracle_every": 1,
  "archive_groups": 2,
  "polish_attempts": 1,
  "racing": true,
  "immigrant_every": 5,
  "crossover_every": 7,
  "operator_weights": {
    "Swap": 3,
    "TrapRelocate": 2,
    "WallRunShift": 1,
    "AirDefenseSpread": 1
  }
}
```

An explicit `account` path can replace `synthetic_account`. The smoke/proof
account is derived from public catalog level limits, excludes event content
without an event version, and never copies personal levels. An optional
`population` array contains `{ "genome": <ArmyGenome JSON>, "weight": <positive
number> }` entries. Without it, two admitted cited seeds form an explicitly
declared model population; their discovery success does not establish real
prevalence. Plans use native account legality, the uncalibrated five-bin skill
model, fixed compiler pace 1 and explicit zero fitted dependency gaps.
Each manifest requires at least five groups per population entry, crossing
each army with every skill bin. Bin counts per army differ by at most one.
Manifest names namespace their random streams, and overlapping group, plan or
scouting seeds across manifests are rejected before evaluation. Each search
wave has a fresh screen; incumbents are reevaluated on it before paired racing.
These extra incumbent battles count against the physical budget. Checkpoint
schema 4 records consumed screen seeds and rejects reuse after resume.
The manifest records the actual account, population, compiled plans and sources.
War requires the attacker account TH to match the defender TH.

The short configuration is a development smoke, not a production recommendation.
Normal defaults use 20 screen groups, 68 independent confirmation groups and
400 development finalist-gate and independent final groups. A group samples
two distinct sides from eight, evaluates each on three hidden priors, commits
using `Scorer::scout(Visible)`, then executes once. Every complete group costs
seven physical battles. Confirmation and finalist gates are development data;
only the frozen final manifest is untouched. A final archive attack uses its
own disjoint fresh seed namespace. Reports flag fewer than 400 gate groups or
100 fresh replicates per archived attack as insufficient evidence.

Population weights are retained per stratum regardless of simulation allocation.
Raw defender trophies, the scorer's penalized objective, worst discovered-attack
utility and restricted-game mixtures are separate fields. Group identities,
side pairs, profile draws, hidden draws and execution seeds are shared across
compared bases. Proposal randomness is independent. Paired racing uses bounded
Hoeffding intervals with alpha spending across waves, candidates, looks and
strata. Missing or singly sampled strata continue. Constant samples retain
uncertainty. Factor-three promotion protects cell openings and exploration.
Cell-opening protection chooses the strongest screened arrival in each new cell,
independently of proposal arrival order. Cell occupants retain the ordinary
objective; a bounded Pareto frontier preserves ordinary/robustness tradeoffs and
contributes every fourth parent pool.

The 81-cell descriptors are normalized TH offset, wall-only eight-connected
compartments of at least four tiles, mean pairwise AD distance, and defense
footprint fraction in the central 16×16 square. TH offset edges are 0.3/0.6;
compartment edges are 6/14. AD/density edges are frozen terciles from the admitted
members of a declared nine-attempt Grid/Wide/Scatter × Central/Mid/Edge corpus,
seeds 600–608. Failed packing attempts are recorded. Equal terciles receive a
documented one-tile / one-core-tile separation. TH17–18 require no Eagle.

Checkpoints retain the full raw development rows and outcomes, outcome cache,
population manifests through the run identity, proposal RNG and candidate cursor,
wave boundary, seen identities, rejections, lineage, admission receipts, archive,
Pareto points, permanent attack hall of fame, payoff rows, and all cost counters.
The empirical game solver is deterministic from the persisted matrix. Writes
use pending, file fsync, backup, rename and directory fsync on Unix. Resume
validates schema, payload checksum, executable/source/data/compiler/account
identities, admission, descriptors and recomputed objectives. An interrupted
wave restarts from the previous complete wave. A completed polished run cannot
be extended, since that would introduce a different selection history. Final
reports may be regenerated from the development checkpoint; final work is not
charged twice in that checkpoint. Worker count and output path are not scientific
inputs. Checkpoints from a different executable are rejected.

The playbook oracle varies sides, supported spread/freeze/charge parameters and
cited dependency timing. The army adapter uses `AccountRules`, `ArmyGenome`,
native mutation, `AttackProgram` enabling/mutation and native compilation. Both
train against plausible independently sampled hidden states, freeze the selected
genome, and validate it on fresh actual-state groups. Their declared budget
includes all training and validation battles. Archive growth refreshes every
affected elite before another comparison. Old attacks and payoff signatures
remain available. The multiplicative-weights solver reports its exploitability
gap and only claims a restricted empirical TH/account/mode/modifier game.
Oracle targets include the strongest ordinary elite and a different occupied
cell with the weakest archived-attack utility. Oracle training/validation counters
are subsets of the physical planning/execution counters, not additional costs.

Diagnostics replay committed plans with the exact native stopping conditions
and check the original scalar result. They collect ground/air/hero traffic,
five traffic classes, wall breaches, per-instance early loss, trap triggers and
damage by source type. Trap proposals preserve buildings, walls and defensive
setup, pass admission, and receive independent development confirmation. The
report labels each intervention and its selection bias. Diagnostics are rebuilt
after layout/policy changes. Damage is descriptive attribution, not causal proof.

Outputs include `winner.json`, `winner.svg`, `report.json`, `report.md`,
`diagnostics.json`, `prepared-jobs.json`, `winner-proof.json`,
`frozen-finalists.json`, `archive.json`, `attack-archive.json`, `checkpoint.json`
and `run-manifest.json`. Reports contain ordinary score/penalty, paired final
comparison, star/destruction distribution, TH survival, family/attacker-TH
breakdowns, actual costs, archive attacks, solver residual and limits. The
weighted median and failure-tail traces must reproduce their original bulk
outcome. Runtime proof receipts bind executable/input and frozen winner
identities. Report failures produce explicit incomplete status.

## Acceptance and port disposition

The focused tests cover:

- Direct native scorer equivalence on identical bundles and a recorded synthetic
  Root Rider/Legend I result in `fixtures/known-visible.json`.
- Hidden-content projection/commitment isolation; 1/4/16 workers; cold/warm cache;
  seven-battle reservation without budget overrun; diagnostic replay identity.
- 256 enumerable races, zero variance, ties, sparse/unequal strata, late reversals,
  a sufficiently replicated clear loss, objective signs and protected halving.
- A six-layout enumerable space with a known optimum and per-cell winners;
  archive-version invalidation; full/raced waves; exact checkpoint continuation,
  raw cache/budget continuation, backup recovery and input mismatch rejection.
- Duplicate discoveries, account legality, both oracle adapters and their budgets,
  historical-exploit retention, incompatible partitions, cyclic and pure payoff
  games, independent-final seed isolation and frozen finalist identity.
- TH17–18 descriptors without Eagle, deterministic corpus edges, paired report
  statistics and replayable prepared jobs.

These replace the retained search capabilities in `tools/baselab/qd_search.py`,
`evolve_bases.py`, the simulation stages of `funnel.py`, and winner explanation in
`explain_base.py`, plus the retained proposal/evolution/evaluation/diagnostic
capabilities in `src/baselab/{optimize,evolve,redteam,diagnose}.py`. CLI flags and
schemas intentionally follow the native contracts rather than Python aliases.
The original M2 modules retain proposal/crossover/annealing coverage.

`funnel.py`'s ridge training/data commands and `surrogate.py` remain deferred by
BASE_SEARCH_RUST_DESIGN §9 pending an equal-battle-budget benefit experiment.
There is no new claim of executed frozen-Python equivalence or real-game
calibration. No Python files are edited/deleted in this lane. The integration
lead owns final deletion after reference closure; `funnel.py` is not yet wholly
deletable if its training workflow is retained. Citation acquisition, arbitrary
research providers, broad presentation tooling and long scientific searches
are outside M3–M6.

The only integration edits outside this crate are the `basesearch` dispatch arm
in `crates/clash-cli/src/lib.rs` and the three local dependency additions in the
`clash-basesearch` package entry of `Cargo.lock`. No shared kernel API or engine
behavior is changed.

## Lane validation receipt

The seven focused M3–M6 tests passed in the workspace release test run. The
recorded visible-scouting fixture reproduces `[3, 100, true, 128.8]`, selected
source 1, six planning battles and one execution. The standalone completion
proof executed 256 enumerable races with zero false eliminations; its cyclic
game residual was zero and its pure-game residual was 0.036855127601162274.

The final TH16 smoke ran two waves in 51.64 seconds, used 1,434/2,400 physical
battles (1,224 planning, 204 execution, six diagnostic), occupied three cells and
retained eight attacks. It wrote `/tmp/clash-lA-th16-smoke/report.md` and the
associated JSON, SVG, checkpoint, jobs and proof receipts. One admitted trap
counterfactual preserved the structure, received four independent confirmation
groups and was rejected after zero screen/confirmation gain. No improvement is
claimed. The restricted empirical game residual was 0.7047582378950717.

Regenerating from the completed development checkpoint with 16 workers took
18.02 seconds and reproduced all eight report/winner artifacts byte for byte.
The legacy native `jobs` command replayed all 12 exported winner/reference jobs;
every stars/destruction/TH/time scalar matched the report exactly. The smoke is
explicitly `limited-model-report`: six final groups and two fresh groups per
archived attack do not meet the recommended scientific evidence floors.

All three golden files retain their original SHA-256 hashes. The original-file
integrity audit found only the crate manifest/library and the permitted CLI arm
changed within `crates/`, `fixtures/`, `scripts/` and `docs/`; `Cargo.lock` has
only the three local dependency entries described above. No Python was run or
edited, and no commit was made.

This worktree's `.git` file contains a Windows path. For the gate's read-only
committed-corpus checks under WSL, use these Git metadata overrides without
editing either checkout or Git metadata:

```sh
GIT_OPTIONAL_LOCKS=0 \
GIT_DIR=/mnt/c/Users/jarod/Documents/clash-lab/.git/worktrees/clash-lab-lA \
GIT_WORK_TREE=/mnt/c/Users/jarod/Documents/clash-lab-lA \
CARGO_BUILD_JOBS=4 scripts/verify.sh /tmp/clash-target-lA
```

The gate exited zero; its complete log is `/tmp/clash-lA-verify-final.log`.
It passed formatting, offline workspace build/tests, unchanged battle/plan
goldens, guardian checks, army-search proofs, the 100,000-case layout proof,
the preserved M2 proof and vidmine checks. Clippy was unavailable locally;
the script reported its supported skip and no component was installed.
Final log tail:

```text
test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

ALL CHECKS PASSED
```
