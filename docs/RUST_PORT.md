# Rust engine port: conventions

The Python engine (`src/baselab/engine/`, `src/baselab/pathing.py`) is the
reference. The Rust engine (`rust/`) must reproduce it **bit for bit**: same
stars, destruction, time, and the same per-tick trace. Speed is the reason for
the port (the base search is noise-limited); exactness is what lets us trust it
and debug it (`tools/baselab/trace_diff.py` finds the first tick where the two
engines part).

History: `rust/` started as a spike (Valkyrie + Dragon vs seven defenses), exact
on 32 battles and 44x faster (commits 8d7d1bd..ad63d52). Its hard-won pieces are
kept: `geom.rs` (CPython-exact `py_hypot`, `round6`), `grid.rs` (lazy path
fields), `pyrandom.rs` (bit-exact `random.Random`), `json.rs` (std-only JSON).

## Status and use (2026-10-22)

- Exact on 340 parity battles: stages 1-4 (every defense and trap, the
  user's two armies with heroes, equipment, pets, spells and playbook plans)
  and stage 5 (the 17 ranked meta armies the base scorer uses), with Rust
  building each battle itself from a layout + plan job.
- `BASELAB_ENGINE=rust` makes `evaluate.run_batch` (the base scorer) run in
  Rust via `src/baselab/rust_bridge.py`: identical results to the Python
  engine (`tools/baselab/scorer_check.py`), ~19x faster end to end than the
  Python process pool on this machine; ~9 battles/s per thread, ~89/s on 16.
- Build: `cargo build --release --manifest-path rust/Cargo.toml` (binary
  `rust/target/release/baselab-engine.exe`, or set `BASELAB_ENGINE_EXE`).
- After a game patch: update the Python data/engine, then
  `python tools/baselab/rust_export.py catalog --out rust/data/catalog.json`,
  then rerun parity (below). Rule changes go into the Python engine first;
  the Rust engine must then match its traces again.
- Parity: `python tools/baselab/rust_export.py parity-setup --stage S --n N`
  for S in 1..5 (N = 72, 72, 64, 64, 68), with
  `BASELAB_CALIBRATION=data/meta-calibration-r8.json`.

## Performance notes (2026-10-22)

Real-army battles ~105 ms per thread (~9.3/s), meta armies ~68 ms (~14.7/s);
16 threads ~92/s and ~117/s (8-core Ryzen 7 7800X3D). Python: ~3.8 s per
battle, ~4.6/s on its 15-process pool. What mattered: rubble reachability as
connectivity (was 41% of a battle), lazy path fields with in-place repair,
interned names and no per-tick clones/allocations, bounded field storage (the
31 MB per-battle working set limited scaling past 10 threads), wall-breaker
reachability as connectivity.
Tried and rejected: a 0.5-tile bucket (Dial) queue instead of the radix heap
(exact but 8% slower); more or fewer stored fields (32-256: no gain);
`-C target-cpu=native` (+2%, not worth a machine-specific binary).
Remaining cost: about half of a battle is path-field expansion (~900k pops
per real battle; 1,035 fields per battle chase moving units and are rebuilt
each tick, as in Python). A goal-directed search for those could save maybe
15-20%, but its exactness argument (every neighbour of the chaser final,
fields shared by several chasers, f32 rounding) is subtle; not done.

## Division of work

- **Python prepares, Rust builds and runs.** Python supplies layouts
  (`Layout.to_json()` with levels) and constructed attack plans (plan
  construction stays in Python; plans do not depend on the layout, so each is
  built once and reused). Rust ports battle setup (`rust/src/setup.rs`:
  `Battle.__init__`, weapons, traps, Clan Castle, defending heroes) and runs
  the battle. The Python battle-state export (`rust_export.py battle`) remains
  the reference that `setup-check` compares Rust's setup against.
- **Catalog** (`rust/data/catalog.json`, `rust_export.py catalog`): the
  processed registry (`stats.registry()`), every `UnitSpec` (`spec(name)` and
  `heroes.summon_spec(name, spec(name))`), `unit_numbers(name, level)` for
  every unit and integer level, `BUILDING_TYPES`, trap tables. Regenerated
  after each game patch; Rust code never hard-codes a number the catalog or
  the battle export carries. `stats.get/text/num/row/attrs/record/max_level`
  are ported in `rust/src/stats.rs` over the catalog registry.

## Exactness rules (each one has bitten us)

- Every `math.hypot` -> `geom::py_hypot` (Rust's `f64::hypot` differs in the
  last bit for ~16% of inputs). `math.sqrt` -> `f64::sqrt` is fine.
- `math.cos/sin/atan2` -> `geom::py_cos/py_sin/py_atan2`, and Python `x ** y`
  (including `** 2`!) -> `geom::py_pow`: they call the same C runtime
  (ucrtbase.dll) as CPython. Rust's own cos/sin differ in the last bit for ~3%
  of inputs, atan2 ~0.1%, and `x * x` differs from Python's `x ** 2` in ~0.05%;
  each broke parity runs (verified exact on 100k inputs each).
- Keep Python's operation order in arithmetic: `a + b + c` is `(a + b) + c`;
  `x / d * s` is not `x * s / d`.
- Python `round()` is half-even on the exact binary value
  (`geom::round_half_even`, `geom::round6`). `int()` truncates toward zero.
  `%` on floats: Python's result takes the divisor's sign (`rem_euclid` for
  positive divisors), Rust's `%` takes the dividend's.
- Iteration orders are results: lists in insertion order, dicts in insertion
  order (Python dicts preserve it; a dict re-assigned an existing key keeps its
  position), `min()`/`max()` keep the FIRST extreme, `sorted()` is stable.
- Comparisons: copy `<` vs `<=` exactly; no added epsilons; keep Python's
  explicit ones.
- `random.Random(seed)`: `pyrandom::PyRandom` (random, uniform, choice). Every
  call consumes the generator: keep the call order.
- The clock: `t = round(t + DT, 6)` (`geom::round6`).
- Object identity: Python compares objects with `is`; Rust uses typed indices
  (`UnitId`, `BuildingId`, `WallId`, `TrapId`). Units are never removed from
  their Vec mid-battle (Python prunes dead attackers above 160 entries:
  port that only as an iteration-order equivalent).
- Python `extra` dicts carry ad-hoc state. In Rust give every key a typed field
  (with its Python default, e.g. `u.extra.get("angry_until", 0.0)` -> a field
  initialised to 0.0). Keys that are tested for presence (`"recalled" in
  u.extra`) become `Option`s or bools.

## Layout

```
rust/src/
  main.rs       CLI: run exported battles, write results and traces
  json.rs pyrandom.rs geom.rs grid.rs   (from the spike)
  catalog.rs    load catalog.json; unit specs and numbers
  stats.rs      stats.get & co. over the catalog registry
  state.rs      Battle, Building, Wall, Weapon, Unit, Trap, Field, Pending
  load.rs       battle export JSON -> state
  battle.rs     battle.py: step, deploy/spawn, queries, hits, kills, destroy,
                pending, splash, separation, result
  defense.rs    defense.py
  traps.rs      traps.py
  units.rs      units.py
  effects.rs    effects.py
  heroes.rs pets.rs spells.rs plans.rs playbook.rs   (later stages)
  trace.rs      the trace format of rust_export.py
```

Each file starts with the Python file it ports; each rule cites `file.py:line`.
Plain, readable code; no traits for one type, no speculative generality, no
tests or benchmarks (parity runs are the tests), no `unsafe`, no warnings, std
only (no crates can be downloaded).

## Stages (each must reach exact parity before the next starts)

1. Core, every defense and trap, Clan Castle defenders; plain troops
   (Barbarian, Archer, Giant, Wizard, Valkyrie, Dragon, P.E.K.K.A, Minion,
   Balloon) dropped at fixed times (`mechanic_tests.Stage`); no heroes, no
   spells. Scenarios: `rust_export.py ... --stage 1`.
2. The rest of the user's armies' troops and summons (Root Rider, Druid/Bear,
   Ruin Witch/Ruin Knight, Healer, Ice Golem/Frostmite, Super Minion, Rocket
   Balloon, Super Hog Rider, Apprentice Warden, Log Launcher, Siege Barracks
   and attacker Clan Castle cargo).
3. Heroes (attacking and defending), equipment, pets.
4. Spells and the playbook/plan logic: the user's real armies
   (`custom:user-rr`, `custom:user-druid-ruin`).

## Checking

```
python tools/baselab/rust_export.py battle --stage 1 --k K --out output/parity/battle-1-K.json
python tools/baselab/rust_export.py trace  --stage 1 --k K --out output/parity/trace-py-1-K.txt
rust/target/release/baselab-engine.exe trace output/parity/battle-1-K.json output/parity/trace-rs-1-K.txt
python tools/baselab/trace_diff.py output/parity/trace-py-1-K.txt output/parity/trace-rs-1-K.txt
```
