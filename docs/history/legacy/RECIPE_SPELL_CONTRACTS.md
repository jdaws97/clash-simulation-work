> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Conditional recipe spell and siege contracts

These bindings make declared experiments executable. They are not calibrated game rules. Missing parameters reject; examples in `data/battle-policies/recipe-spells.json` and `recipe-log-launcher.json` are explicit hypotheses, not silent defaults.

## Totem

The pinned catalog commit `c6967314d7281bb87c362993e2635e58cd77b351` supplies radius 5, per-level Totem HP, and 334 HP/second decay. Its description supplies a decoy, landing damage and stun, but not the landing damage or stun quantities. The example **500 landing damage, 1-second stun, 0.5-second landing delay and 0.1-second maximum decay-observation step are uncalibrated scenario choices**. They must not be promoted to catalog facts.

Each paid cast owns one generated, stationary, nonblocking point. It uses neither an army housing slot nor an extra spell slot. A live nearby defense must select the nearest Totem (ID breaks ties) for new acquisition, including weapons ordinarily restricted to air. Released attacks retain their existing destination and source ownership. Totem decay settles elapsed continuous HP loss at every boundary, bypasses protection, and schedules residual lifetime from the current timestamp; the declared interval is a maximum decay-observation step. It stops at zero HP and cannot resurrect a destroyed Totem. The selected contract excludes traps, beneficial fields and ordinary unit status; the decoy does not keep an otherwise exhausted attack alive. Landing damage uses the shared health boundary and source receipts.

Taunt radius uses source/decoy centers, independently of the defense weapon range. All new acquisitions of a multi-target weapon are constrained by this hypothesis. This is deliberately narrower than claiming a measured multi-target game rule. Landing membership uses live centers; walls and unrevealed Teslas are excluded. Source quantities and all these behavior choices remain separate in the model output.

## Recall

[Supercell's TH15 release notes](https://supercell.com/en/games/clashofclans/blog/release-notes/full-release-notes-2/) describe returning troops, heroes and pets to deployment, retaining damage/status, preferring greater housing, and weights of 25 for heroes and 20 for pets. The pinned catalog supplies each level's capacity and radius. Historical publisher prose does not establish a current hidden scheduler.

The explicit experiment orders eligible live units by descending housing, then distance, then ID; it skips a member that does not fit remaining capacity. Troop housing is bound from catalog or an explicit generated-troop contract. Siege and spell decoys are excluded. Recall hides actors from acquisition through a distinct recalled state rather than death or a fresh deployment. It preserves HP, spent hero ability state, source-owned released packets and absolute status/cooldown deadlines. Absolute deadlines continuing in the deployment bar are an **uncalibrated clock policy** requiring independent validation.

A supplied redeployment declares a later time, one group position and allowed rectangles. The position must lie on the board, in those declared regions and outside a live blocking footprint for ground members. Regions are scenario inputs, not inferred live-game deployment exclusions. A null redeployment leaves the group held. Re-entry never refreshes army, spell or ability inventory and never resets the initial deployment record. Paid Recall is consumed even if nothing fits. Pending redeployment has explicit continuation ownership.

## Log Launcher

The previously separate extended-siege implementation is now bound for **Log Launcher only**. Flame Flinger, Siege Barracks and Battle Drill remain unavailable through this promotion. The pinned catalog supplies main hit, wall hit, point-blank hit, interval, speed, HP decay and lifetime; example travel geometry, log speed, width and hit limit remain hypotheses.

The carrier follows its captured Hall anchor. Each launch captures footprint contacts, orders them along the log, distinguishes named wall and structure damage, and does not charge wall contacts against the declared structure-hit limit. Point-blank composition selects the strongest named role once per recipient. A launched log survives carrier death or manual release. The existing siege lifecycle owns the one Clan Castle payload; generated weapon contacts cannot deploy it twice.

## Calibration boundary

These contracts have no calibrated full-battle evidence. Timing, geometry, status transitions and effect composition remain explicit hypotheses. Validation requires independently established inputs, equipment, patch, modifiers and event timing; successful synthetic execution alone does not establish those quantities.
