**Scope and references.** This specifies the Python implementation, including its numerical and ordering quirks. References to `battle.py`, `units.py`, etc. mean `src/baselab/engine/`; `pathing.py` means `src/baselab/pathing.py`. Use `DT=0.1`, windup enabled, and game-data flyer ranges. The fixed deployment adapter must have a no-op `on_tick` and report no additional pending offense. Defaults are no league modifier, strength `1.0`, and a 180-second limit. (`battle.py:33–40,125–151,797–855`; `units.py:1263–1308`; `specs.py:482–491`)

The fixture must actually remove excluded combat behavior: empty defending troops/heroes/traps, no guardian, no builders, and no weapons on passive buildings. **Stock setup attaches a Town Hall weapon at TH13–17**, so simply retaining the default TH16 constructor does not satisfy this scenario. A weaponless TH produces no death bomb. (`battle.py:265–306`; `defense.py:273–293,387–398,520–571`)

**1. Tick execution.** `step()` performs this exact sequence:

1. Return immediately if ended or `t >= max_time`.
2. If scouting, increment only `scout_time` by `0.1`, capped at 30; disable scouting upon reaching 30, then return. No combat, deployments, or combat-time advance occurs on that call.
3. Deploy every scheduled entry with `time <= t`, in stable time-sorted order.
4. Rebuild attacker spatial buckets; apply auras, which provide no buffs here.
5. Call `plan.on_tick`; return without advancing time if it ends the battle.
6. Set spell provenance; run spell upkeep, then resolve pending impacts.
7. Set trap provenance; run traps, castle release, guardian upkeep, bell upkeep, builder upkeep. These have no combat effects under this fixture.
8. Act every living attacker, using a snapshot of the attacker list in spawn order.
9. Separate attackers.
10. Act living armed buildings in original building-list order.
11. Act defending units in snapshot order; the list is empty here.
12. Clear current actor; prune path caches every five seconds, including `t=0`. If attacker-list length exceeds 160, remove dead ordinary troops while preserving survivor order. Record a frame every 0.5 seconds if enabled.
13. Set `t = round(t + 0.1, 6)`.

References: `battle.py:208,893–950,1079–1085`.

Thus newly deployed troops act immediately; attackers can destroy a defense before it fires that tick. Pending impacts resolve before attacker movement. Victory/wipe checks are in `run()` **after** `step()` and its time increment, not between actors. (`battle.py:797–809,902–935`)

Buckets have width four tiles. Construction follows attacker-list order; bucket insertion order follows first encounter. Queries enumerate bucket x ascending, then y ascending, then stored members; they test current squared distance `<= r²` and current alive status. Membership remains from before movement/separation until the next tick. Preserve this stale-membership behavior for defense targeting and splash. (`battle.py:41,556–573,1079–1084`)

Separation visits buckets in insertion order and pairs `i<j`. Only living, positive-speed units of the same flying status interact, and only within the same stored bucket. Radius is `0.35 + 0.015*min(30,housing)`: Valkyrie `0.47`, Dragon `0.65`. For distance `d < radius_sum`, move each oppositely by `(radius_sum-d)/4`. If `d<1e-6`, use angle `(first.id*2.399) % (2*pi)`, direction `(cos,sin)`, and push `radius_sum/4`. Ground nudges are rejected if their destination cell is building-blocked or contains a standing wall; accepted coordinates are clamped to `[0.1,49.9]`. Flying nudges ignore obstacles. (`battle.py:1087–1130`)

**2. Setup, geometry, and statistics.** World coordinates cover `[0,50)²`; layout buildings and walls receive a three-tile offset. Deployment coordinates are already world coordinates. Buildings retain layout-list order and receive zero-based IDs. A building of size `s` placed at `(x,y)` has center `(x+3+s/2,y+3+s/2)`. (`src/baselab/mechanics.py:22–26`; `battle.py:245–264,392–396`; `entities.py:28–36`)

Building levels use explicit `defense_levels[key]`, overriding `layout.levels[key]`, otherwise the registry maximum for the battle Town Hall. `max_level` uses its Town Hall mapping when available, otherwise the highest integer level whose required Town Hall is legal. Invalid/unavailable levels raise. Town Hall level is the battle Town Hall itself. (`battle.py:190–193,237–260`; `stats.py:137–175`)

`stats.get` merges level fields with wiki fields, performs case-insensitive numeric lookup in requested-key order, and parses the first signed number, stripping commas. `~fragment` searches matching column names in insertion order. Game `hitpoints` and `dps` override corresponding wiki values when numeric; wiki values provide fallbacks. Ordinary building HP is `get(name,level,"hitpoints","Hitpoints",default=1000)`; Town Hall HP uses `"hitpoints"`, default 10000. Initial HP equals maximum HP. (`stats.py:20–31,165–224`; `battle.py:253–264`; `entities.py:37–39`)

Hitbox width is `attrs.hitbox or max(1,size-1)`; `half_hit=width/2`. Ordinary supported defenses have size three and `half_hit=1`; Inferno has size two and `half_hit=0.5`; Town Hall has size four and `half_hit=1.5`. Distance from point `(px,py)` to a square is:

`hypot(max(abs(px-cx)-half_hit,0), max(abs(py-cy)-half_hit,0))`.

(`battle.py:261–264`; `entities.py:59–64`; `src/baselab/mechanics.py:70–88`; `data/registry.json:49024,51144,51559,52232,52548,52882,54312,55302`)

Walls use per-coordinate `layout.wall_levels`, otherwise `layout.wall_level or max_level("Wall",th)`. HP is `stats.get("Wall",level,"Hitpoints")`. Their world-tile coordinates are integers, centers are `(tx+0.5,ty+0.5)`, and `half_hit=0.5`. Wall-dictionary insertion follows iteration of `layout.walls`, which is a **set, not a sorted list**; preserve the reference run’s resulting order. (`battle.py:282–291`; `entities.py:75–94`; `src/baselab/layout.py:55–70`)

Building combat hitboxes populate the blocked grid; walls populate a separate wall grid. Deployment exclusion instead covers whole standing building footprints and standing wall tiles, expanded by all nine offsets `dx,dy∈{-1,0,1}`. Destroyed structures stop excluding drops. Banner tiles remain excluded; banners themselves are dead, uncounted markers. Illegal deployments snap to the nearest legal tile center by squared distance; ties choose x ascending, then y ascending. (`battle.py:248–251,281,359–405,457–462`)

For normal weapons, define `D(I)` as the first numeric `"Damage per Shot"`, `"Damage per Hit"`, `"Damage per Attack"`; otherwise `get("dps","Damage per Second",default=0)*I`. **Defense ranges/intervals below come from code, not registry attributes**, which may describe geared modes. (`defense.py:162–167,294–355`)

| Defense | Air/ground | Range; minimum | Interval | Damage and impact |
|---|---|---|---|---|
| cannon | Ground | 9; 0 | 0.8 | `D(0.8)`; direct projectile, 12 tiles/s |
| at | Both | 10; 0 | 0.5 | `D(0.5)`; direct projectile, 18 tiles/s |
| mortar | Ground | 11; 4 | 5 | First `"Damage per Hit"`, `"Damage per Shot"`; fixed 1.5-second flight, radius 1.5 |
| wt | Both, splash matching primary’s height | 7; 0 | 1.3 | `D(1.3)`; radius 1; levels ≤4 use 5 tiles/s flight, higher levels splash immediately |
| ad | Air | 10; 0 | 1 | `D(1)`; direct projectile, 8 tiles/s |
| inferno single | Both | 9; 0 | 0.128 ammunition period | Continuous tick damage with ramp below |
| xbow ground / both | Ground / both | 14 / 11.5; 0 | 0.128 | `D(0.128)`; immediate direct hit |

References: `defense.py:294–355,741–803,810–842`.

Inferno ramp DPS uses `"Damage per Second / Initial"` at lock time 0, `"/ After 1.5s"` at 1.5 seconds, and `"/ After 5.25s"` at 5.25 seconds; respective defaults are 120, 260, 2600. X-bow capacity is 1500 rounds; Inferno capacity is 1000. Ammunition override precedence is building ID, then building key, then capacity; require an integer within capacity. Initial cooldown, lock time, idle deadline, and ammunition-time remainder are zero. (`defense.py:39–57,350–355,455–462`)

If cannon/at/mortar modes are included, `None`/`normal` retain the table; `geared`, `burst`, and `fast` all select gear-up behavior. Minimum levels are 7/10/8 respectively; noninteger charged levels are rejected. Geared cannon has range 7, four immediate shots separated by cooldown additions of 0.192, then 1.6 after the last, using `"Damage per Hit**"`. Geared mortar fires three normal mortar shells with additions 0.5, 0.5, then 4, using `"Damage per Shot"`. Fast AT has range 8, interval 0.25, and level-10–21 damage `[31.5,35,37.5,40,45,50,52.5,55,60,65,69,72.5]`; its projectiles still travel at 18 tiles/s. (`defense.py:473–497,716–747`)

**3. Defense acquisition, damage, and projectiles.** `_visible` uses bucket queries measured **center-to-center**, includes maximum/minimum boundaries, requires `targetable(t)`, and filters flying status. Here ordinary living deployed troops are immediately targetable. Existing targets remain until dead, untargetable, outside maximum range, or below minimum range; a nearer arrival does not cause replacement. Invalidation resets Inferno lock time. Acquisition selects minimum Euclidean distance, with ties retaining candidate-query order. If no candidate exists, acquisition sleeps until `t+0.25`; this is checked only when there is no valid target. (`entities.py:227–238`; `defense.py:574–590,679–697`)

Unavailable or ammunition-empty weapons return before cooldown handling. Otherwise, decrement cooldown to `max(cooldown-0.1,-0.1)` and call `_act_once` up to twelve times, stopping when ammunition reaches zero, cooldown becomes positive, or cooldown does not change. Ordinary shots require `cooldown<=0`, then **add** the interval and consume one round where applicable. Acquisition/validation happens even while cooling down. No rounding or epsilon is applied to cooldown comparisons. (`defense.py:601–633,679–739`)

Inferno bypasses the ordinary cooldown firing gate. Each valid-target tick first adds `0.1` to lock time, chooses the last ramp threshold `<= lock_time`, then deals `DPS*duration`, where `duration=min(0.1, rounds*0.128-ammo_time)`. Add duration to `ammo_time`; while `ammo_time+1e-9>=0.128`, subtract 0.128 and one round. Thus the final partial round can produce a shortened damage tick. Lock accumulation is ordinary floating-point addition. (`defense.py:698–713`)

`hit_unit` ignores dead units/nonpositive damage. Here reductions are one, so subtract the damage directly; building-origin attacks additionally multiply by `def_mult` if a league modifier is selected: 1 normally, 1.10/1.15/1.20 for legend3/2/1. Record damage attribution capped at pre-hit HP, set `last_hit=t` and the source, and kill immediately at HP≤0. Killing sets HP zero/alive false. Neither troop has death effects. Building fire does **not** grant awareness, which requires an enemy Unit source. (`battle.py:64–69,587–652,671–691`; `specs.py:18–48,73,87`)

Direct projectiles schedule `at=t+center_distance/speed`, retain the target object, and hit that object at resolution if still indirectly targetable. They do not recheck range or aim coordinates. Mortar and low-level WT schedule fixed aim coordinates, without tracking. Pending entries retain firing actor/effect and survive destruction of their source. (`defense.py:771–785,810–842`; `battle.py:776–785,978–1000`)

Resolution partitions pending entries into due `at<=t` and future entries, then processes due entries in **append order**, not sorted impact-time order. New pending entries cannot resolve again in the same pass. Direct impacts hit only their retained living target. Area impacts query current units around their saved coordinates; no friendly building damage occurs here. (`battle.py:960–1026`)

Unit splash uses point-center distance, includes `d==radius`, and filters height. WT deals full damage throughout its radius and only to the primary’s flying/ground category. Mortar deals `damage*(1-0.5*d/1.5)` within radius 1.5. Its knockback applies only to housing≤3, so neither spike troop is knocked back. Stale buckets can affect even an immediate WT splash’s inclusion of its primary. (`battle.py:764–774,1048–1068`; `defense.py:767–803`)

**4. Valkyrie and Dragon.** Spawn assigns increasing IDs starting at one, appends in deployment order, sets `spawned_at=active_at=t`, and initializes cooldown zero, no target/wall target, and neutral statuses. Explicit troop levels are read directly; absent levels use `max_level(name,deployment.town_hall or battle.town_hall) or 1`. A nondefault plan strength multiplies HP, maximum HP, and damage only. (`battle.py:427–480`; `entities.py:115–180`)

| Unit | Interval | Range | Speed | Housing | Flying | Attacks |
|---|---:|---:|---:|---:|---|---|
| Valkyrie | 1.8 | 0.5 | 3 tiles/s | 8 | No | Ground; self-centered radius-1 spin |
| Dragon | 1.25 | 2.5 | 2 tiles/s | 20 | Yes | Ground/air; target-centered radius-0.3 splash |

Sources: `data/registry.json:2108–2135,3132–3159`; `specs.py:73,87,349–378,482–503`; `data/gamecsv/v18.200.9/characters.csv:103`.

For levels 1 upward, `(HP,damage_per_hit)` are:

- Valkyrie: `(750,169.2),(850,190.8),(950,214.2),(1050,239.4),(1300,266.4),(1500,300.6),(1650,333),(1800,352.8),(2000,374.4),(2400,401.4),(2600,428.4),(2900,459)`. (`data/registry.json:3161–3329`)
- Dragon: `(1900,175),(2100,200),(2300,225),(2700,262.5),(3100,300),(3400,337.5),(3900,387.5),(4200,412.5),(4500,437.5),(4900,462.5),(5300,487.5),(5700,512.5),(6000,537.5)`. (`data/registry.json:2137–2319`)

HP uses game-first `stats.get`. Damage prefers explicit per-hit/per-attack columns; absent those, use `abs(DPS)*interval`. If game and wiki DPS differ by more than `max(1,0.02*game_DPS)`, an explicit wiki hit is scaled by `game_DPS/wiki_DPS`; the listed rows need no scaling. Interval prefers `attack_interval`, then `_ck`, then 1. Speed prefers `attrs.speed`, otherwise `speed_display/8`; housing prefers normal attrs then `_ck`. Dragon range overrides wiki range with CSV `AttackRange/100=2.5`. (`specs.py:349–364,401–503`)

Both prefer `"any"`: `_preferred_pool` returns `None`; their building pool is targetable buildings in original order. Targetable means alive and counted, with Town Hall explicitly permitted; walls are absent from this pool. Targets persist while valid. Dragon picks smallest square-edge distance, ties choosing first building. Valkyrie uses path cost when multiple buildings remain: minimum source-field distance over each building’s reachable goal cells, first minimum in building order; if the best cost is ≥`1e8`, fall back to smallest edge distance. With one building it selects by edge distance directly. (`specs.py:18–25,73,87`; `battle.py:536–548,1173–1187,1206–1226,1326–1442`)

Engagement checks run at most every 0.5 seconds. Awareness lasts two seconds following enemy troop attacks, or arises from an ally within seven tiles hit by a troop less than one second ago. There are no such sources or defending units here; Dragon’s separate nearest-defender check also finds none. (`battle.py:645–651,1265–1289,1313–1321,1444–1458`)

Each actionable tick decrements unit cooldown to `max(cooldown-0.1,-0.1)` before target selection. Changing the primary target sets cooldown to `max(current,delay)`: Valkyrie delay 0.6 from CSV; Dragon defaults to its interval, 1.25. Windup counts down while moving. Range uses square-edge distance and inclusive `<=`; in range and cooldown≤0, strike once and **add** the attack interval. Movement into range never also strikes in that call. Interrupting movement/attacks does not reset these troops’ cooldowns. (`battle.py:1189–1199,1277–1311,1542–1589`; `units.py:1239–1259,1267–1316,2003–2020`; `data/gamecsv/v18.200.9/characters.csv:234`)

Valkyrie positioning precedes range checking. For each other targetable building, let `P=clamp(other.center,target.square)`, `Q=clamp(P,other.square)`, and midpoint `M=(P+Q)/2`. Accept M only if target-edge distance≤0.5, other-edge distance≤1, its grid cell is not blocked, and the segment from Valkyrie to M intersects no living building’s closed square. Segment intersection maintains `[enter,leave]`, initially `[0,1]`, intersected with each axis’s slab-parameter interval; touching counts. Choose the accepted midpoint nearest the unit, ties retaining building order. Cache it while the primary is unchanged and the second building remains targetable; cached positions are not geometrically revalidated. She must reach the exact coordinate before attacking. (`units.py:60–74,1200–1236`; `battle.py:1542–1547`)

Valkyrie wall mode is normal; Dragon flies. Ground navigation uses the battle grid. When the selected next cell is a standing wall, store `wall_target` and return without moving or attacking; later ticks engage that wall before the primary building. This does not itself invoke primary-target windup. A dead wall target is cleared. If Valkyrie’s strike kills its engaged target, both primary and wall target are cleared; the normal interval is still added afterward. (`battle.py:1290–1311,1460–1487,1622–1631`; `units.py:1878–1881`)

Both attacks are immediate spatial strikes, with no troop projectile. Valkyrie centers splash on herself; Dragon centers it on the target’s **center**, not its edge. Snapshot candidates are living counted buildings in list order, then living walls in wall-dictionary order; add the living primary if absent. Hit every candidate whose square-edge distance from the splash center is within radius, once, for full damage. Dragon can therefore damage walls even with radius 0.3; the separate `splash_buildings` radius≥0.5 wall restriction is not used. All damage multipliers are one here. (`units.py:1364–1440,1574–1627,1630–1689,1835–1888`)

**5. Ground fields and movement.** Resolution is two cells/tile: `100×100`, indexed `[x,y]`, cell centers `((i+0.5)/2,(j+0.5)/2)`. Position lookup truncates `2*x,2*y`, clamped to `[0,99]`. Building blocking writes half-open slices with endpoints `round(2*(center±half_hit))`; wall tiles write their corresponding `2×2` cells. (`pathing.py:17–24,176–199,272–275`)

A goal cell satisfies square-edge-distance²≤reach². Reach is `max(effective_range,sqrt(0.5)/2+1e-6)`; Valkyrie uses 0.5. Positioning goals use a point hitbox and reach 0.5. Normal wall extra cost is `12/2=6` per wall cell, independent of wall HP. (`pathing.py:121–141`; `battle.py:58–60,1435–1438,1604–1611`)

Dijkstra initializes unblocked goals to zero, everything else to float32 `1e9`. Neighbors, in order, are:

`(+1,0),(-1,0),(0,+1),(0,-1),(+1,+1),(+1,-1),(-1,+1),(-1,-1)`.

Costs are 0.5 cardinal and `sqrt(2)/2` diagonal. Reject blocked neighbors and diagonals touching either blocked orthogonal cell; walls do not block diagonals. Expanding backward from current cell C into neighbor N computes `nd=dist[C]+step+(6 if wall[C] else 0)`, charging **C**, not N. Update only when `nd<dist[N]`. Source fields use this same recurrence with the source cell as their sole goal. (`pathing.py:20–35,89–118,237–259`)

The binary heap stores float32 keys and flattened cell indices; initial seeds scan x then y. Push stops when parent key≤child; pop compares left then right using strict `<`. Equal keys have no coordinate tie-break. Skip popped entries only when their key exceeds stored distance. (`pathing.py:39–118`)

**Precision is mixed:** distances, heap keys, and building-cost outputs are float32; step costs, coordinates, hitbox geometry, and reach are float64. Relaxation arithmetic promotes to float64 before comparison with stored float32, then assignment rounds to float32. Preserve this instead of making the whole pathfinder float64 or rounding the candidate before comparison. (`pathing.py:24,30,47,100–109,149–169,220,233,259`; `battle.py:1432–1434`)

Target-field cache keys are `(target_identity,goal_x,goal_y,reach,wall_mode)`. Source-field keys are `("src",i//2,j//2,wall_extra)`. **Same-version source reuse is per whole tile**, even when a later caller occupies a different half-tile cell; same-cell checking happens only for repair. (`battle.py:1608–1611`; `pathing.py:222–255`)

Every grid write increments version and logs its rectangle expanded by one cell. Stale fields are repaired only when intervening changes are all removals and the log reaches their version. Copy old distances, seed changed rectangles, reset newly freed goal cells to zero, and rerun relaxation. Target repair additionally requires identical goal masks; source repair requires the same source half-cell. Otherwise recompute. Above 600 entries, retain 400 sorted by descending stored version, preserving insertion order on equal versions; trim logs before the oldest retained version. (`pathing.py:185–270`)

`next_step` returns at-goal immediately for current distance≤0. Otherwise choose the first neighbor with strictly smaller stored distance, in neighbor order. It adds no movement/wall cost and performs no blocked/corner check. Return the winning center and its wall flag. With no improvement, return unchanged coordinates and `at_goal=(here>=1e9)`. (`pathing.py:277–300`)

Movement allowance is speed×0.1: Valkyrie 0.3, Dragon 0.2. Flyers move straight toward target center. Ground units follow the chosen waypoint; at a zero-distance goal cell, or an unreachable currently blocked cell, move straight toward the requested goal. Unreachable unblocked cells return without movement. An unchanged non-goal waypoint accumulates stuck time; after `>2` seconds clear the primary target. After reaching a waypoint, spend leftover movement through at most four additional waypoints, stopping at goals/walls/no progress. Straight movement snaps exactly to destinations within allowance, otherwise adds normalized direction×allowance; it performs no collision check. (`battle.py:1505–1520,1591–1669`)

**6. Destruction and results.** `hit_building` ignores dead targets/nonpositive amounts, updates building `last_hit`, subtracts full damage, and destroys immediately at HP≤0; return value includes overkill. `damage_dealt` consequently includes overkill. Destroy sets HP zero/alive false; wall destruction clears its wall cells and returns without destruction credit/logging. Building destruction clears its blocked hitbox and increments the counter only if counted. Weaponless Town Hall activation calls do nothing. (`battle.py:224–234,693–750`; `units.py:1420–1426`)

For counted total N and destroyed count K, raw destruction is `100.0*K/max(1,N)`; displayed destruction is integer ceiling `(100*K+max(1,N)-1)//max(1,N)`. Stars add independently for displayed destruction≥50, destroyed Town Hall, and `K>=N`. Thus a rounded-up 50% earns the percentage star. Walls do not contribute. (`battle.py:203–204,518–534,735–745`)

`run()` ends after a completed tick for `K>=N`, or when no attackers and no future deployments/additional plan offense remain; otherwise it stops at the time limit or explicit end. Outstanding **defense** projectiles do not prevent a wipe ending. Result time therefore normally includes the final tick’s 0.1 seconds. (`battle.py:793–855`)

Result fields are `stars`, destruction rounded to two decimals, `th_destroyed`, time rounded to one decimal, counts of destroyed counted buildings by key, living-defense keys in building order including duplicates, number of living attackers, and log. Score is `stars+destruction/100`. Recording logs deployment, unit death, and building destruction in execution order; wall destruction has no event. With recording disabled, these logs remain empty. (`battle.py:513–514,690–691,749–750,869–890`; `result.py:8–22`)

**7. Randomness and numerical parity.** `random.Random(seed)` is constructed, but **no RNG calls occur in this fixed-deployment spike**. Separation’s angle is ID-derived. The engine’s random calls belong to excluded Electro Dragon death bolts, Super Wizard Tower targeting, and spells. Plan `_drop` jitter would call `uniform(-jitter,jitter)` first for x, then y, but the stipulated fixed list bypasses it. (`battle.py:148,1109–1112`; `units.py:777–785`; `defense.py:1253–1256`; `spells.py:405–406,639–643`; `plans.py:581–584`)

Use float64 for combat geometry, HP/damage, times, cooldowns, and Inferno lock/ammunition remainders. Preserve Python operation order and nearest-even rounding; Rust’s ordinary rounding differs at ties. Do not round pending deadlines or cooldowns, or introduce comparison tolerances: `t+flight` can lie just above a nominal tick, delaying impact, and small positive cooldown residuals delay attacks. Retain only explicitly coded tolerances, particularly ammunition’s `1e-9` and movement’s `1e-9`. (`battle.py:950,1571–1584,1645–1653`; `defense.py:628–632,698–715,771–776,810–840`; `pathing.py:190–193`)