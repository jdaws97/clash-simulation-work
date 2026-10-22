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

## Division of work

- **Python builds, Rust runs.** Python constructs each `Battle` (layout,
  levels, weapons, traps, Clan Castle queue, defending heroes, plan) and
  exports its starting state with `tools/baselab/rust_export.py battle`. Rust
  never re-implements setup (`Battle._setup`, `defense.attach_weapon`,
  `traps.make_trap`, plan construction).
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
