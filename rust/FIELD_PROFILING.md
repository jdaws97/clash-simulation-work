# Path-field measurements

Run the existing `jobs` command with `BASELAB_PROFILE_FIELDS=1`. Only the exact
value `1` enables profiling. The setting is cached once and copied into each
grid. Disabled runs create no profiling maps, timers or locks, and use expansion
loops with the pop counter compiled out.

The command writes its usual results and stdout unchanged. At command exit,
stderr receives space-separated `key=value` records prefixed by `fields_profile`:

```text
fields_profile format=1 time_unit=ms layout=input_index pops=including_stale state=version_at_work timings=exclusive
fields_profile kind=... source=... state=... builds=... pops=... repairs=... wall_ms=... distinct_initial=... battle_distinct_initial=... within_battle_rebuilds=... cross_battle_reuses=...
fields_profile job=... layout=... failed=... job_wall_ms=... battle_wall_ms=... fields_wall_ms=... battle_fields_wall_ms=... battle_fields_pct=...
fields_profile total jobs=... builds=... initial_builds=... pops=... initial_pops=... fields_wall_ms=... initial_fields_wall_ms=... initial_fields_pct=... battle_wall_ms=... battle_fields_wall_ms=... battle_fields_pct=...
```

`kind` distinguishes `building_goal`, `wall_goal`, `unit_chase`, `source`,
`wall_breaker`, and `rubble_goal`. Auxiliary work has its own `rubble_connectivity`,
`topology`, and `goal_geometry` rows. Builds include actual storage restarts after
eviction; successful in-place repairs increment `repairs` instead. Connectivity
and topology are rebuilt rather than repaired. `goal_geometry` builds count
individual cached building goal masks; their time also includes preparing the
union used to query source fields.

`source` is `main` or `jump`. The initial version is captured immediately after
layout setup and before opening-plan queries. `state=initial` means that the main
grid still has exactly that version when the work runs; `state=changed` covers
later versions and independent Jump views. Builds are classified at build time,
repairs at repair time, and lazy frontier pops at expansion time. Thus expanding
or repairing an initially built field after destruction counts as changed work.

The distinct-field columns apply to initial-state builds. Identity includes the
input layout index, initial grid version, existing cache key, saved seed geometry
and effective wall cost. Layout indices refer to the `layouts` array in the input;
duplicate layout entries are separate identities. No identity is inferred from
battle results or a randomized hash fingerprint.

- `distinct_initial`: unique initial fields across all jobs and worker threads.
- `battle_distinct_initial`: sum of each job's number of unique initial fields.
- `within_battle_rebuilds`: initial builds minus `battle_distinct_initial`.
- `cross_battle_reuses`: `battle_distinct_initial` minus `distinct_initial`.

The last two columns partition repeated initial builds into reuse within a battle
and additional reuse across battles. They describe matching field identities,
not how much of each lazy field was expanded or the memory cost of retaining it.

Times are elapsed wall time measured on each worker. Nested measurements subtract
their children's time so row times can be added. They cover field construction,
repairs, topology, goal preparation, source-field goal scans, and lazy expansion;
fully settled distance hits, target-cache hits and next-step selection are not
timed separately. Enabled measurements include instrumentation overhead.

`job_wall_ms` includes setup and battle execution. `battle_wall_ms` brackets
`Battle::run()`; the corresponding `battle_fields_wall_ms` excludes setup's field
work. `battle_fields_pct` uses those two battle-only times. Total battle times are
the sum of individual job times, not the concurrent command's elapsed time.
`initial_fields_pct` is the initial-state share of all measured field time,
including setup. Failed jobs retain their partial counters and have `failed=true`.

`src/grid.rs` owns the instrumentation hooks and local expansion counters.
`src/field_profile.rs` owns per-job thread-local counters and distinct keys, nested
timers, and the summary protected by a mutex. Each worker merges once per job;
frontier loops never touch shared counters. Connectivity pops are counted from
the final labels in one scan. `src/setup.rs` marks the initial version, and
`src/jobs.rs` brackets jobs and battle execution and owns summary lifetime.
