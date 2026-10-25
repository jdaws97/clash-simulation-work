# Runtime mechanics parameters (RM1)

`rust/src/params.rs` is the runtime registry. Every entry has a default,
provenance and unit. Parameters are resolved once per battle; jobs do not mutate
shared catalog values or process environment. All four new behavior flags default
to **false**. The default model retains the legacy route rule and float operation
order. The existing golden corpus is the compatibility oracle.

A prepared job can override parameters directly or in its environment:

```json
{
  "layout": 0,
  "plan": 0,
  "seed": 123,
  "town_hall": 16,
  "env": {
    "params": {
      "target_list": true,
      "ground_radius": 0.4,
      "separation_push": 0.2
    }
  }
}
```

A JSON object with the same parameter keys can be supplied through
`BASELAB_PARAMS_FILE=/absolute/path/params.json` for CLI/library jobs. Exported
battle snapshots accept `env.params` too. No CLI argument parsing changes were
needed in shared `main.rs`. Precedence, from lowest to highest, is registry defaults
and catalog-derived defaults, catalog environment, process file, job environment,
then job `params`. Legacy `pace*` environment fields are recognized at their
respective environment layer. The existing `dt`, `windup`, `fast_end` and
`flyer_range` switches retain their existing input contract.

Unknown/duplicate keys, wrong JSON types, negative/non-finite numbers, zero unit
scales or poison/projectile divisors, and invalid candidate-list sizes are rejected.
List sizes must be integers with `1 <= target_list_size <= max_target_list_size <=
1024`. Applying an invalid object leaves the registry unchanged. Setup reports a
parameter error through the existing job failure boundary. An explicitly false job
flag overrides a true process-file flag.

`new_target_delay.<unit name>` overrides each existing catalog attack-delay entry;
unknown names fail. Its defaults, plus Warden legacy radius/threshold, Healer group
radius and poison ramp, come from the loaded catalog. The table below lists the
committed catalog's defaults. Measured provenance names the existing local
measurement, not a new measurement made by this stream.

## Interpretation of the game constants

All behavioral interpretations below are **hypotheses to validate with probes**.
The numeric values themselves are checked against the committed
`data/gamecsv/v18.200.9/globals.csv`. `TargetGroupsRange=1300` for Apprentice and
Grand Warden corresponds to 13 tiles: **100 internal distance units = 1 tile**.
Applying that distance scale to path cost or noise is a separate hypothesis.
Applying a factor of 100 to Warden weights is another separate hypothesis.

With `target_list=true`, normal eligible buildings are stably sorted by distance
to their hitbox edge. The first `TARGET_LIST_SIZE` (3) are primary candidates.
`MAX_TARGET_LIST_SIZE` (6) caps expansion when all primary paths are unreachable or
when a retarget is forced. All compared paths are settled exactly. The legacy grid
union query deliberately settles only the cheapest goal and returns sentinel
values for other goals; it is not used to infer candidate reachability.

Ground wall cost becomes `WALL_COST_BASE / internal_units_per_tile`, currently
10 tiles, divided by the two-cells-per-tile grid resolution for each wall cell.
Flyers, underground troops and wall-ignoring units use direct distances. An
expanded candidate gets `EXTRA_TARGET_PATH_COST_PENALTY` (5 **tiles**, a hypothesis)
for each rank beyond the primary list. Ordinary candidates get no noise. Forced
retargets add seeded uniform score noise in `[0, max_noise / units_per_tile]`,
using the DEFAULT/JUMP/TESLA bound according to the event. Pushback and no-progress
expiry are DEFAULT events; entering/exiting wall-ignore mode is treated as JUMP;
Tesla reveal is TESLA. These event classifications and the uniform distribution
are hypotheses. Preference filters, Wall Breaker logic, rubble and siege Town Hall
destinations retain their specialized selection rules.

`STICK_TO_TARGETED_BUILDING_WHEN_FORCING_RETARGET` preserves an eligible original
building during forced selection. When stickiness is disabled,
`REMEMBER_ORIGINAL_TARGET` retains it for resumption after a temporary detour or
retaliation. `FORGET_TARGET_TIME` is interpreted as milliseconds without decreasing
destination distance or changing obstacle HP. An expired building is skipped while
other candidates exist; a sole remaining building may be retried. Dead/ineligible
originals cannot be resumed. Successful wall damage resets the progress timer.
`SELECTED_WALL_TIME` holds a live chosen wall for 4000 ms, after which routing may
select it again. `RETARGET_AFTER_DESTROYING_WALL=false` keeps the building target;
true explicitly reselects it. No wall is held after death or a valid wall bypass.

With `warden_spatial=true`, ID-ordered allies within the 13-tile search radius
form seed-centred neighborhoods of `TargetGroupsRadius / units_per_tile` (5 tiles).
This is not transitive clustering. Choose the heaviest qualifying neighborhood,
then its nearest seed, then its earliest ID. Grand Warden's minimum is 2000 and
Apprentice Warden's is 1000, each divided by `group_weight_units_per_weight` (100).
Weights remain the existing catalog Warden weights. Members vote by live target;
first ID-ordered member breaks tied target votes. If the qualifying group has no
valid building/wall target, `WARDEN_WAITS_FOR_GROUP_RETARGETING=true` pauses the
Warden until a group member acquires one. Retaliation, Angry and attached-pet
exceptions still apply. All grouping, conversion and tie rules are hypotheses.

Ground separation uses `ground_radius + ground_radius_per_housing * min(cap,
housing)` and each pair receives `separation_push` of its overlap per tick.
`defender_separation=true` applies the same rule to defenders, with ground/air
pairs kept separate. Defenders retain the existing grid and movement restrictions.

With `hidden_information=true`, attacker plan scans use `visible_buildings()` and
exclude unrevealed Teslas. Their footprints are absent from navigation until
`reveal_tesla` inserts them and advances the grid version, invalidating path and
Jump caches. Existing targetability already hid concealed Teslas. Traps have no
navigation footprints and current attacker plans do not inspect trap positions;
`attacker_knows_trap` exposes only triggered/spent traps for future plan consumers.
Physical trap effects and damage to concealed structures still use the full world
state. This flag does not claim to solve completed-battle hindsight in side scoring;
that is a separate policy concern.

## Audit boundary

The registry covers the remaining numeric assumptions called out in ENGINE_V2,
current mechanics and policy comments: wall/separation costs, fallback wind-ups,
retarget/alert/wake timers, human pace/reaction/jitter/hold/aim/revive times, Healer
weights/radius/travel, spell landing/poison ramp, trap frame conversion, Spring
fuse/stun and Tornado force interpretation. A non-default explicit plan revive
delay remains a plan override. The standard 1.5-second plan default uses the
registry's `revive_delay`.

ENGINE_V2's older assumed list includes values subsequently sourced from game
tables/wiki (Bomb and other trap ActionFrames, pet cooldowns, Rage Vial duration,
Witch summons, Giga throw distance and Healer stacking). Those data-driven values
are not replaced with new guesses. Clone disappearance and folding CC into the
main army are categorical model choices, not numeric calibration parameters.
The grid resolution, numerical tolerances, world bounds and cache capacities are
implementation invariants, not assumed game measurements. Plan-specific named
strategy knobs remain in their plan schema.

## Registry

Regenerate this table with the existing WSL toolchain (no installation):

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-rm1
export BASELAB_CATALOG="$PWD/rust/data/catalog.json"
cargo run --manifest-path rust/Cargo.toml --example mechanics_proof -- params
```

| Name | Default | Provenance | Unit | Meaning |
|---|---:|---|---|---|
| `target_list` | false | assumed | flag | Opt-in target-list hypothesis |
| `warden_spatial` | false | assumed | flag | Opt-in spatial grouping hypothesis |
| `defender_separation` | false | assumed | flag | Separate defenders using the same collision rule |
| `hidden_information` | false | assumed | flag | Hide unrevealed structures from attacker planning and navigation |
| `wall_cost` | 12 | assumed | tiles | Legacy normal wall cost, divided by grid resolution per cell |
| `ground_radius` | 0.35 | assumed | tiles | Ground separation base radius |
| `ground_radius_per_housing` | 0.015 | assumed | tiles/housing | Ground separation housing contribution |
| `separation_housing_cap` | 30 | assumed | housing | Cap on ground radius housing contribution |
| `air_radius` | 0.35 | measured | tiles | Dragon spacing estimate; output/dragon-spacing/measure.md |
| `separation_push` | 0.25 | assumed | overlap/tick | Each member receives this fraction of overlap |
| `separation_angle` | 2.399 | assumed | radians/id | Deterministic direction for coincident units |
| `stuck_timeout` | 2 | assumed | seconds | Legacy no-waypoint timeout |
| `dragon_arrival_windup` | 0.75 | assumed | seconds | Fallback Dragon arrival wind-up |
| `melee_arrival_windup` | 0.33 | assumed | seconds | Fallback melee arrival wind-up cap |
| `mite_attack_windup` | 0.5 | assumed | seconds | Frostmite/Firemite first attack gate |
| `defender_retarget_delay` | 0.5 | assumed | seconds | Defender periodic target selection |
| `attacker_engage_delay` | 0.5 | assumed | seconds | Attacker retaliation checks |
| `siege_blocker_delay` | 0.5 | assumed | seconds | Ground siege blocker checks |
| `retaliation_radius` | 7 | game-data | tiles | CHAR_VS_CHAR_RADIUS_FOR_ATTACKER; ally alert search |
| `ally_hit_memory` | 1 | assumed | seconds | Recent ally damage counts for retaliation |
| `castle_radius` | 13 | game-data | tiles | CLAN_CASTLE_RADIUS |
| `castle_exit_delay` | 0.3 | assumed | seconds | Spacing between defending CC releases |
| `th_activation_delay` | 0.5 | assumed | seconds | Town Hall weapon wake delay |
| `guardian_activation_delay` | 0.5 | assumed | seconds | Guardian rooftop wake delay |
| `scout_time` | 30 | assumed | seconds | Pre-attack scouting budget |
| `hero_jitter` | 0.5 | assumed | tiles | Generic hero deployment jitter per axis |
| `cleanup_jitter` | 0.3 | assumed | tiles | Generic cleanup deployment jitter per axis |
| `reaction_delay` | 0.5 | assumed | seconds | Generic plan and fallback decision interval |
| `pace` | 1 | assumed | multiplier | Human input time scale |
| `pace_tap` | 0.133 | measured | seconds | Held deployment cadence; docs/VIDEO_MEASUREMENTS.md |
| `pace_switch` | 0.6 | assumed | seconds | Slot/spot switch time |
| `pace_ability` | 0.3 | assumed | seconds | Ability action time |
| `aim_wait` | 10 | assumed | seconds | Ready ability/spell aim timeout |
| `late_deployment` | 150 | assumed | seconds | Spend remaining camp by this time |
| `opening_hold` | 30 | assumed | seconds | Maximum generic opening hold |
| `revive_delay` | 1.5 | assumed | seconds | Default revive reaction delay (explicit plans still override) |
| `healer_group_radius` | 1.5 | game-data | tiles | Healer splash/group radius |
| `healer_group_min_housing` | 2 | assumed | housing | Group must exceed this housing |
| `healer_hero_weight` | 25 | assumed | housing | Hero weight in Healer group test |
| `healer_projectile_speed` | 12 | assumed | tiles/second | Healer beam travel speed |
| `warden_radius` | 13 | game-data | tiles | Legacy Warden vision radius |
| `warden_min_weight` | 20 | game-data | weight | Legacy Grand Warden vote threshold |
| `apprentice_radius` | 13 | game-data | tiles | Apprentice TargetGroupsRange / 100 |
| `apprentice_min_weight` | 10 | assumed | weight | Legacy Apprentice vote threshold |
| `spell_landing_delay` | 0.5 | assumed | seconds | Bottle landing delay except instant Revive |
| `poison_ramp` | 4 | assumed | seconds | Poison time to full DPS |
| `trap_frame_seconds` | 0.04285714285714286 | assumed | seconds/frame | Bomb-derived ActionFrame conversion |
| `spring_delay` | 0.3 | assumed | seconds | Spring fuse retained over conflicting frame inference |
| `spring_stun` | 1 | assumed | seconds | Spring stun on survivors |
| `tornado_force_scale` | 1 | assumed | multiplier | Interpret table force as pull velocity |
| `internal_units_per_tile` | 100 | game-data | units/tile | TargetGroupsRange evidence; path/noise scale transfer is a hypothesis |
| `target_list_size` | 3 | game-data | candidates | TARGET_LIST_SIZE; nearest primary candidates (hypothesis) |
| `max_target_list_size` | 6 | game-data | candidates | MAX_TARGET_LIST_SIZE; unreachable/forced expansion cap (hypothesis) |
| `extra_target_path_cost_penalty` | 5 | game-data | tiles/rank | EXTRA_TARGET_PATH_COST_PENALTY; extra candidate penalty (hypothesis) |
| `wall_cost_base` | 1000 | game-data | internal units | WALL_COST_BASE; path wall cost (hypothesis) |
| `forget_target_time` | 6000 | game-data | milliseconds | FORGET_TARGET_TIME; no-progress forgetting (hypothesis) |
| `remember_original_target` | true | game-data | bool | REMEMBER_ORIGINAL_TARGET; resume after retaliation/detour (hypothesis) |
| `force_new_target_default_max_noise` | 800 | game-data | internal units | FORCE_NEW_TARGET_DEFAULT_MAX_NOISE; forced score noise bound (hypothesis) |
| `force_new_target_jump_max_noise` | 100 | game-data | internal units | FORCE_NEW_TARGET_JUMP_MAX_NOISE; Jump forced score noise bound (hypothesis) |
| `force_new_target_tesla_max_noise` | 400 | game-data | internal units | FORCE_NEW_TARGET_TESLA_MAX_NOISE; Tesla forced score noise bound (hypothesis) |
| `retarget_after_destroying_wall` | false | game-data | bool | RETARGET_AFTER_DESTROYING_WALL; reselect building when wall falls (hypothesis) |
| `selected_wall_time` | 4000 | game-data | milliseconds | SELECTED_WALL_TIME; hold a selected live wall (hypothesis) |
| `stick_to_targeted_building_when_forcing_retarget` | true | game-data | bool | STICK_TO_TARGETED_BUILDING_WHEN_FORCING_RETARGET; preserve eligible original (hypothesis) |
| `target_groups_radius` | 500 | game-data | internal units | TargetGroupsRadius; seed-centred spatial cluster radius (hypothesis) |
| `target_groups_min_weight` | 2000 | game-data | centi-weight | TargetGroupsMinWeight; divide by 100 (hypothesis) |
| `apprentice_target_groups_min_weight` | 1000 | game-data | centi-weight | Apprentice TargetGroupsMinWeight (hypothesis) |
| `group_weight_units_per_weight` | 100 | assumed | units/weight | Conversion of TargetGroupsMinWeight to wiki Warden weights (hypothesis) |
| `warden_waits_for_group_retargeting` | true | game-data | bool | WARDEN_WAITS_FOR_GROUP_RETARGETING; wait while selected group has no target (hypothesis) |
| `new_target_delay.BB Bat` | 1 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.BB Cannon Cart` | 0.4 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.BB Enraged Bat` | 1 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.BB MovingCannonSecondary` | 0.4 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Balloon` | 2.25 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Bat` | 1.5 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.BouncingFrostmite` | 0.5 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Bowler` | 1.1 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Defensive Disarmer` | 0.6 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Disarmer` | 0.6 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Electromite` | 0.5 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Firemite` | 0.5 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Firemite Spawn` | 0.5 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Firemite Spawn_DEF` | 0.5 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Frostmite` | 0.5 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Icemite` | 0.5 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Minion Prince` | 0.45 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Rocket Balloon` | 2.25 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Royal Champion` | 0.4 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Royal Ghost` | 2.4 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Skeleton Barrel` | 2.25 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Snake Barrel` | 2.25 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Spell Bat` | 1.5 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Stone Slammer` | 2.25 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Super Barbarian` | 0.7 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Super Bowler` | 1.1 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Super Valkyrie` | 0.6 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Super Wall Breaker` | 1 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.The Disarmer` | 0.6 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Valkyrie` | 0.6 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Witch Spirit` | 0.5 | game-data | seconds | Catalog new-target attack delay | 
| `new_target_delay.Yetimite` | 0.5 | game-data | seconds | Catalog new-target attack delay | 
