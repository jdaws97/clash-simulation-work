> Predecessor Python filenames and parity procedures in this document are
> historical provenance from `f04706c`. Deleted tools are not runnable; see
> [the current documentation](README.md) for native commands and remaining Python ports.

# Visible scouting and oracle comparison (RW1, 2026-10-25)

`score` defaults to `scout_policy: "visible"`. It predicts candidate sides on
three independent hidden layouts, commits using mean attacker trophies (then
mean destruction, first candidate on ties), and only then runs the selected
side on the original layout. The existing stat-based skill model is unchanged.

## Policies and budget

A score bundle accepts `scout_policy: "visible" | "random" | "oracle"`.
`scout` remains the number of candidate sides considered together (default 2).
As before, a grid represents the equally weighted combinations of that size;
`scenario.full_scout: true` considers the whole grid. For each combination,
visible scouting commits using predicted outcomes. Repeated winning candidates
share one real-state evaluation and carry their combined probability weight.

- **Visible (default):** three hidden samples per candidate row, followed by
  one fresh real-state battle per distinct committed candidate. A group of
  eight sides with full scouting costs 24 planning battles + 1 evaluation.
- **Random:** one uniformly sampled candidate per group, then one real-state
  evaluation; no planning battles. A candidate includes its side and technique.
- **Oracle:** complete every candidate battle on the original hidden state,
  then choose the best result. This is a completed-battle upper bound on
  attacker trophy utility over the same candidate set, not a feasible scout.
  Full scouting of eight sides costs eight real-state battles per group.

Reports label the policy and include planning/evaluation battle counts,
source candidate indices, selected weights and `evaluation_scenarios` with
fresh battle seeds. Those seeds govern execution; the original prepared plans
retain their compiled timing, calibration and skill quantile. Replaying stored
completed outcomes requires an explicit `oracle` policy. Native army search
still uses its existing oracle estimates and labels them in stage reports.

Seeds use stable FNV mixing of army, attacker TH, modifier, group and sample.
The high bits define disjoint namespaces: hidden sampling 1, planning battles
2, real execution 3, random choice 4; the low 48 bits identify the draw. They
remain exact JSON integers. Candidate sides share hidden draws and paired
execution randomness. Neither actual hidden contents nor completed real-state
outcomes enter the selection. Results are independent of worker scheduling.

## Hidden priors and limits

The sampler constructs a new layout from visible buildings, walls and their
levels, defending heroes, guardian and town hall. It never copies actual trap
inventory/positions/levels, Tesla inventory/positions/levels, CC occupants or
CC troop levels, names, notes or arbitrary metadata. The CC building and its
level remain visible.

The following are declared modelling assumptions, not measured probabilities:

- Use the catalog's five-Tesla inventory and the existing TH16/17/18 trap
  inventories from `src/baselab/mechanics.py:146–150`. Sample positions uniformly
  from legal free footprints, excluding visible buildings, walls and prior
  sampled hidden objects. Hidden levels use the engine's normal TH defaults.
- Skeleton Trap ground/air mode is equally likely.
- Sample equally among defensive Ice Golem, Lava Hound/Headhunter and
  Dragon/Headhunter packages, filling spare housing with Archers. Housing comes
  from the visible Castle level and catalog; normal receiving caps still apply.
- Assume full hidden inventories. Crowded layouts with no legal sampled
  placement return an error rather than overlapping objects or consulting the
  original hidden layout. Priors currently cover defender TH16–18.

The visibility distinction is supported by
`local/research/usage/hidden-tesla.md` and
`local/research/usage/clan-castle-lure-and-kill.md`, citing the
[Hidden Tesla reference](https://clashofclans.fandom.com/wiki/Hidden_Tesla/Home_Village)
and [Clan Castle reference](https://clashofclans.fandom.com/wiki/Clan_Castle).
The proposed ensemble method comes from R5 in
[RUST_REVIEW_2026-10-25.md](history/RUST_REVIEW_2026-10-25.md) and
[SIMULATION_METHODS_RESEARCH.md](SIMULATION_METHODS_RESEARCH.md).
These sources do not establish a calibrated hidden-state distribution. Future
priors need held-out observations; this implementation makes no targeting,
pathing, collision, wind-up or execution-noise rule changes.

## Four-base development comparison

Inputs: the four existing real-layout transcriptions under
`data/reference-bases/ranked-th18-2026-10-25/r18{a,b,c,d}.json`;
`custom:user-rr-oct25`, user TH16 inventory, playbooks enabled, r8 calibration,
no league modifier. All angles are **radians**: `2*pi*k/8`, k=0..7.

Use five replicate groups and all five existing skill quantiles per replicate:
`group = 5*r + q`, original plan seed `5*(8*r+k)+q`, r,q=0..4. Plans are compiled
natively with `CompileOptions::default()`, then receive strength
`Strength::load(root).get("custom:user-rr-oct25") * skill(seed)`.
The r8 custom strength is 1.1875673814385301 (the mean of its TH16 Root Rider
family). Use full scouting, three hidden samples, the seed namespaces above,
and four workers. Each policy evaluates 25 committed attacks per base, except
oracle which completes all 200 candidates before retaining 25 outcomes.

| Base | User real stars | Random mean stars | Visible mean stars | Oracle mean stars |
| --- | ---: | ---: | ---: | ---: |
| r18a | 1 | 1.48 | 1.72 | 2.12 |
| r18b | 2 | 1.08 | 1.36 | 1.68 |
| r18c | 2 | 1.44 | 1.68 | 2.00 |
| r18d | 3 | 1.48 | 1.96 | 2.20 |
| Mean | 2.00 | 1.37 | 1.68 | 2.00 |

Budget across four bases: random 100 real battles; visible 2,400 planning +
100 real battles; oracle 800 real battles; total 3,400 battles. This comparison
uses the same prepared candidates and paired fresh execution seeds across
policies, not equal compute budgets. The existing real outcomes are development
comparators, not held-out calibration. A single real attack per base cannot
validate these means or establish an improvement in game accuracy.

## Validation and evidence

- Before changes: the G2 golden suite passed 868/868. R1/R7/R9's prior failure
  paths are documented and code-verified in the Rust review. D1/D2 in
  `local/research/gap-triage.md`, `gaps/dragon.md` U14 and
  `gaps/greedy-raven.md` identify modifier and account admission restrictions.
- After changes: a tracked-files-only copy plus RW1 files at `/tmp/fresh-rw1`
  contained no `data/wiki`, `output`, `rust/target` or old target directories.
  It built offline into `/tmp/clash-fresh-target`, compiled the custom RR army,
  passed 50/50 guardian fixtures, the full 4,096 legality + 4,096 program
  mutation proof (including 1/4/16-worker determinism), and 868/868 goldens.
  Golden cases and expectations were unchanged. Windows verification remains
  with the reviewer; no platform-specific expectations were introduced.
- Removing Siege Barracks' row from a temporary copy of the derived table
  returned `missing siege donation cap`; replacing its cell with text returned
  `invalid siege donation cap`. Neither produced a panic or a level-zero plan.
- TH17 and TH18 synthetic account variants derived from the default account
  admitted 72 seeds each, compiled at their selected TH, and completed native
  search/confirmation/fresh-seed/holdout plus verified median replays with
  Legend I. Capacities: TH16 320/11/50/3; TH17 340/11/55/3; TH18 352/11/55/4
  (camp/brewed/CC troops/CC spells). Limits follow actual building levels, not
  TH maxima; under-upgraded accounts retain their lower capacities.
- Legend I reached setup as multipliers 1.2/1.2/1.2/0.8. Repeated rows hit the
  cache 22/22; raw rows and every stage report retained `legend1`.
- Unsupported synthetic equipment, pet and plan names produced typed
  `ContentError::Unsupported` results and compiler rejections. Existing
  invariant assertions remain; this is not a wholesale malformed-JSON parser
  rewrite or a relaxation of unsupported-content checks.
- Removing all actual Teslas, traps and CC occupants and changing their hidden
  levels left sampled layouts and committed choices unchanged. The visible
  smoke result was byte-identical with one and four workers, cost 24 + 1
  battles, and reported execution seeds in namespace 3.
- `cargo fmt --check` and `git diff --check` pass. RW1 did not edit Python or `rust/vidmine`; unrelated workspace changes
  were left alone. No test files were added or changed. The requested legacy
  `python3 -B verify.py` entry point is absent in this checkout.

The minimal donation-cap artifact preserves its source URL, revision and
retrieval time in `rust/data/clan_castle.json`; it agrees with the catalog's
existing `setup.siege_donation_caps`. The generated TH17/18 targets were copied
into `rust/data/target17.json` and `target18.json` with synthetic names and
without original notes/provenance. Runtime readers no longer depend on ignored
wiki/output files. Caller-selected manifests, catalogs, account snapshots,
score bundles and calibration paths remain explicit external inputs.

## Change map

Paths below are relative to the repository root. Evidence is the R1/R2/R5/R7/R9
review, D1/D2 audits and the cited catalog/wiki sources above.

| File:line | RW1 change |
| --- | --- |
| `rust/src/compile.rs:88`, `:1673`, `:2283`, `:2321` | Committed donation table; missing/invalid cap errors; supported-loadout preflight; data-derived account capacity enforcement. |
| `rust/data/clan_castle.json:1` | Minimal nine-siege, eight-Castle-column table with original source/revision/time. |
| `rust/data/target17.json:1`, `rust/data/target18.json:1` | Sanitized, declared synthetic generated targets formerly read from ignored output. |
| `rust/src/armysearch/score.rs:44`, `:172`, `:205` | Validate/retain/serialize manifest modifier; use committed default target paths. |
| `rust/src/armysearch/report.rs:119`, `:349`, `:438` | Fingerprint committed Rust data instead of wiki mirror; report modifier, oracle label, attacker TH and account capacities. |
| `rust/src/armysearch/account.rs:63` | TH16–18 admission, catalog/building-derived capacities, supported inventory filtering and actual-TH plan compilation/check/repair. |
| `rust/src/armysearch/themed.rs:73`, `:152` | Derive proposal budgets and main/CC housing ranges from account capacities. |
| `rust/src/armysearch.rs:276` | Optional account snapshot input; include effective account contents in run/checkpoint identity; retain existing default. |
| `rust/src/armysearch/eval.rs:126`, `:303` | Propagate modifier through scenarios, jobs, cache, raw rows and median replay. |
| `rust/src/content.rs:17`, `:109`, `:142` | Typed unsupported/invalid admission errors; support sets mirror existing executor; validate both build and prepared loadouts. |
| `rust/src/setup.rs:136` | Return typed preflight failures before constructing battle state. |
| `rust/src/runner.rs:187`, `:248` | Propagate typed setup failures as indexed job rejections, without panic logs. |
| `rust/src/jobs.rs:24` | Adapt setup/trace CLI paths to fallible construction. |
| `rust/src/golden.rs:255` | Adapt golden runner to fallible construction; trace behavior/expectations unchanged. |
| `rust/src/heroes.rs:2987` | Adapt the existing supported Guardian fixture constructor to the fallible setup API. |
| `rust/src/scouting.rs:120`, `:267` | Visible-only hidden sampling; precommitted ensemble selection; independent seed domains; random/oracle comparison policies and explicit budgets. |
| `rust/src/scoring.rs:1114`, `:1131` | Retain the old selector as the documented oracle; share deterministic selection over predicted trophy/destruction utility. |
| `rust/src/scoring_cli.rs:107`, `:353` | Default to visible policy; require explicit oracle replay; report selected execution scenarios/budgets and summarize committed outcomes without a second selection. |
| `rust/src/lib.rs:13`, `:36` | Register content validation and scouting modules. |
| `docs/RUST_PORT.md:1` | Current Rust reference/golden/maths/build/input contract. |
| `docs/ENGINE_STATUS.md:1` | Mark preserved v29 status as legacy and point to current Rust docs. |
| `docs/history/GAP_ANALYSIS.md:1`, `:149` | Retire the stale unfinished-Rust-path claim and update scouting/reference status. |
| `docs/MOVE_LIBRARY_DESIGN.md:127`, `:286`, `:298` | Rust-owned compiler/controller/vocabulary milestones and golden checks; account/modifier restrictions resolved. |
| `docs/SCOUTING.md:1` | Policies, priors, budget, reproducible experiment parameters, comparison and validation evidence. |

Git staging/commit was attempted after validation, but `.git` is mounted
read-only and Git could not create `index.lock`. All RW1 files remain in the
working tree. `/tmp/rw1.patch` contains only these changes and passes reverse
application checking against the final working tree. No unrelated files were
staged or changed by this task.
