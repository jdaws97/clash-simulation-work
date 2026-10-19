# Defense and defending Castle handoff

## Baseline and ownership

Built from the stable applied v29 recipe snapshot (net recipe patch SHA256
`ef9c8035ae108b9c6ff9362e1cbb99cac977bfeb1dfe8e8ba43d769ed3f4515f`).
No shared kernel, registry, full-battle, damage-receipt, rate, resource or trap
dispatch files are changed. The patch contains only this document, defense/CC
domain modules and their focused tests. The isolated Git baseline has no private
ancestry; distribute the net patch, not repository history.

## Implemented and already connected

`garrisons.GARRISON_MEMBERS` adds Electro Dragon, Dragon Rider, Ice Golem, Giant
and Hog Rider to the existing seven ordinary defenders. Existing adapter dispatch
imports that registry and calls `compile_garrison_member`, so these five use the
current Castle release/target/death integration without shared-file edits.
`defending_troop_roles.compile_shared_garrison_member` invokes the existing troop
compiler under donor training availability, then changes only defending roles.
It preserves the shared weapon, projectile, wall, on-hit and death models.

All released defenders target hostile units; the Castle scheduler retains its
explicit lure policy: currently eligible enemies trigger release, release pauses
when they leave, released members pursue without a leash, and idle members hold.
Castle destruction cancels reserves and keeps released members/projectiles.
The recipe continues to require explicit timing/position hypotheses. No new
leash or server donation rule is inferred. Defensive Ice Golem specifically uses
`freezeRadiusOnDefense` and `deathFreezeTimeOnDefense`, not offensive quantities.

Receiver laboratory/capacity checks, unique Castle ownership, reserve deployment
prohibition, member destruction exclusion and independent attacking-CC inventory
remain enforced. Full-battle compilation binds an Ice Golem defender to its exact
Castle roster. No attacking troop behavior is duplicated.

## Integration hooks awaiting the integration owner

These features are domain-ready and tested, **not yet full-battle support**.

| Feature | Compiler / surviving fields | Runtime / dispatch requirements |
|---|---|---|
| Geared Cannon | `defense_variants.compile_geared_cannon`; instance `geared_cannon_parameters`; actor `geared_cannon_model`, `attack_model`, `minimum_range` | Register Cannon `gearedUpBurst`; invoke domain compiler rather than generic cadence; construct `GearedCannonCombat(actors, pattern_combat)`; `prepare(actors,time,trace)` before launches and after health; route its weapon launches through `launch`; combine `result`. Shared base selector retains/reacquires each shot. Shared rates own Freeze/rate rescaling. |
| Logger | `guardians.compile_guardian` delegates Logger to `logger_guardian.compile_logger_weapon`; instance `logger_parameters`; actor `guardian_model`, `logger_model`; distinct `attack_model.kind=logger_rolling_log` | Register and validate the distinct pattern; generic PatternCombat must reject ordinary launch for it. Existing GuardianCombat owns emergence, patrol, leash, return, Hall loss and permanent death. Construct `LoggerCombat(actors,pushback_callback)`; dispatch its `launch`; include `next_boundary(time)`; call `resolve(actors,time,trace)` before shared health; attach shared `damage_receipts`; include result/continuation provider. |
| Earthquake Tower | `spell_towers.compile_spell_tower`; selected mode `earthquake`, level >=4; existing `spell_tower_parameters`, `spell_tower_model` with zero duration and explicit fraction | Add mode to adapter defense registry and selected-mode scope. Existing SpellTowerCombat owns trigger/cast/Freeze/recharge/death release. Call new `SpellTowerCombat.resolve(actors,time,trace)` after prepare and before health, attaching shared damage receipts. Existing prepare queues one instantaneous pulse; it never installs an aura. |
| X-Bow finite ammo | `defense_variants.attach_explicit_defense_ammunition`; actor `weapon_ammunition` | Accept explicit ammo parameters during X-Bow compile and invoke hook. Existing PatternCombat already owns finite rounds/depletion. Do not reuse this hook for Inferno beams. |
| Builder Lightning reset | `BuilderHutCombat.lightning_reset(worker_ids,actors,time,trace,clock_policy)` | At an actual Lightning spell impact, identify affected internal workers with the spell's geometry; call the hook with explicit `restart_declared_first_repair_delay` policy. Do not infer Lightning from ordinary damage or add workers to combat/inventory. Unbound synthetic `builder_target_reset` commands still reject. |

Logger's `pushback_callback(target, axis, distance, time, source_id, trace)` must
clip the destination for the target layer and board/terrain policy, then use the
shared `enqueue_linear_displacement` storage and attack-work pause. Projectile
speed/width are explicit inputs. The tested corridor uses launch-sampled target
centers, per-target arrival, live corridor recheck and one hit per log. It does
not claim continuous moving-target collision accuracy or calibrated bounce
animation. Released logs preserve launch damage and survive source/Hall loss.
Invulnerability blocks shared damage; pushback suppression/allowance is explicit.
Logger cannot construct a runtime without a displacement callback. Its unique
pattern intentionally fails in the old generic compiler until integration, so
the validation placeholder cannot silently become a single-target Logger.

Register continuation kind `logger_projectile` as a defensive released packet
with the affected target actor and its arrival time. Do not grant paid resources
or generated destruction credit. None of these defenses creates child actors.
Keep all original defending-unit response, Giga/Spring/Tornado mappings required
for existing controlled defenders. Add raw-model/scope ownership validation for
every new model; do not permit old scopes to ignore specialized models.

## Cross-worker troop dependency

The five new Castle members use existing v29 troop modules, with no dependency
on a worker's moving tree. Further members must use the attacking troop owner's
compiled lifecycle objects and a runtime that explicitly supports team=defense,
controlled Castle ownership and hostile-unit targets. Do not add recipe/summon/
support identities merely because their catalog statistics exist.

In particular, RecipeTroopCombat currently requires team=attack. Witch/Golem/
Lava/Super-Hog children need predeclared finite defender-owned reserves and
same-team inheritance; Druid/Bear needs complete child stats; Healer/Apprentice
need explicit defending recipient/follow contracts. `bind_defending_weapon` is a
role conversion helper, not authorization to bypass those runtime checks.

## Evidence and explicit uncertainty

Numeric and descriptive evidence is the repository's unverified pinned catalog
at commit `c6967314d7281bb87c362993e2635e58cd77b351`:

- [Cannon](https://github.com/chiefpansancolt/clash-of-clans-data/blob/c6967314d7281bb87c362993e2635e58cd77b351/data/home/defenses/cannon.json): geared range, four shots, per-hit damage, 0.192-second interval and 1.6-second burst gap. Two gap interpretations are opt-in experimental; neither is silently calibrated.
- [Logger](https://github.com/chiefpansancolt/clash-of-clans-data/blob/c6967314d7281bb87c362993e2635e58cd77b351/data/home/guardians/logger.json): both target layers, rolling/pushing logs, hit damage, 2.5-second cadence, one-tile push and level-specific post-hit range. Speed, width, planar collision sampling and no extra death effect are explicit uncalibrated hypotheses.
- [Ice Golem](https://github.com/chiefpansancolt/clash-of-clans-data/blob/c6967314d7281bb87c362993e2635e58cd77b351/data/home/troops/ice-golem.json): independent offensive/defensive Freeze quantities.
- [Spell Tower](https://github.com/chiefpansancolt/clash-of-clans-data/blob/c6967314d7281bb87c362993e2635e58cd77b351/data/home/defenses/spell-tower.json): Earthquake radius 4.7, troopDamagePercent 30 and recharge 50. Maximum-HP interpretation, source-centered aim, membership and level-four unlock are explicit experimental choices; no structure damage or repeated attacking-Earthquake reduction is borrowed.
- [Supercell Battle Builders](https://supercell.com/en/games/clashofclans/blog/game-updates/battle-builders-2/), verified 4 October 2026: Lightning resets the Builder's repair target; workers are untargetable by attacking troops; Hut destruction retires repair. Exact clock restart behavior remains a required hypothesis.

The pinned X-Bow and Inferno entities contain no ammunition quantity. X-Bow
initial rounds must be caller-sourced and experimental; no automatic refill is
invented. Inferno ammo depletion, supercharges and account upgrade-state behavior
remain unsupported. Revenge and higher-TH experimental modules are preserved.

All twelve crafted-defense identities are seasonal/phase-specific catalog extras,
including historical `isCurrent=false` rows. They remain separate from permanent
TH16-18 coverage and unsupported here. An uncrafted Station does not simulate a
crafted weapon. Module progression/HP/weapon construction must not be inferred
from standalone formula values or stale seasonal rows.

## Validation and limits

Fresh focused unittest processes exited zero: the final 65 checks completed in
0.223 seconds. They cover existing Builder/Tower/Castle regressions, specialized
troop role preservation, Castle actual-death Freeze, full-battle special roster
binding, Cannon midburst Freeze/gap, released Logger source loss/immunity,
Earthquake source loss/immunity and Builder target reset. An earlier 21-check
run also included the existing short complete-battle Castle integration.

Black 24.10.0 formatted all changed Python files using existing local packages,
one worker and a writable cache; no packages were installed. No suspect runner,
crash retries, faulthandler dumps or broad full-army simulations were used. The
global verify suite was not run because the coordination contract limits this
worker to focused checks. Exact full recipes, all special defending troops,
Logger displacement through the integrated solver and replay calibration remain
the integration owner's acceptance work, not established outcomes of this patch.
