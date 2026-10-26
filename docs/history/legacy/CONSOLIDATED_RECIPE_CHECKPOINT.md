> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Consolidated recipe and higher-TH checkpoint

The local consolidation adds the fifteen initially missing selected recipe components and integrates the TH17/18 net patch from `28e751cad0fd354c9f29fdf0e6d7a1f32c822cc1`. The adapter overlap was combined explicitly. A raw Revenge model cannot bypass the advanced ruleset requirement. The review delta is relative to sanitized numerical publication `8ead4f5972c88ba8f5360fba06acdf5292443924`, whose tree is `00c1c8fa9f744c9ae0c51f5f59ea472333574888`; private development ancestry is not part of the patch.

The consolidated portable suite passed **1,224 tests** in 36.882 seconds before the later runner-reporting and documentation corrections. It includes the arrival correction and receiver-cap regression below. The suite was not rerun for those reporting corrections; focused process-stub checks verify them without starting a simulator. Integration regressions cover Totem lifetime after an intervening hit, forged generated-decoy fields, paid Recall return, shared equipment charges, generated troop ownership, released Log packets, and Revenge lifecycle scope. The CC Super Troop regression checks both allowed parent research levels and receiver-cap rejection.

Both complete saved TH16 account recipes compile against the TH16 layout and against each complete TH17/18 layout. Paid resources remain **320 troop / 11 spell / 50 CC troop / 3 CC spell housing**, with their original account and army inputs. No selected unit, spell, hero equipment, pet or siege was omitted to force compilation. Giga Bomb response maps cover the complete compiled attacking-unit sets: 88 for Dragon and 52 for Root, including neutral Totem entries. Defending-unit response maps cover those same actors. The higher-TH layout, defending actors and traps match the source scenario except for those required attacker response maps.

## Bounded full-battle attempts

The three attempts below preceded the arrival correction. They used the complete scenes, passive progress recording and a 240-second wall limit each. They overlapped in wall time, so these runtimes are not isolated performance benchmarks. The last periodic checkpoint precedes forced termination and is not the exact final solver timestamp.

| Complete recipe / defense | Last periodic simulation time | Last periodic wall time | Trace events | Result |
| --- | ---: | ---: | ---: | --- |
| Dragon / TH16 Ranked | 17.5096659345 s | 230.851 s | 625 | Wall timeout; no outcome |
| Dragon / TH17 CWL | 32.9655703426 s | 230.337 s | 3,676 | Wall timeout; no outcome |
| Root / TH18 Ranked | 23.5633791478 s | 233.548 s | 2,413 | Wall timeout; no outcome |

No stars, destruction score, successful completion or win rate is inferred from these attempts. They passed compilation and made simulation progress, but **complete exact-recipe battle execution remains unproven**. Dragon/TH18 and Root/TH17 are compile-only at this checkpoint.

Passive stack samples found ground-route/target selection, trap membership scans and Firespitter collision scheduling. The TH17 Dragon run advanced only about 0.000596 simulation seconds between its 180.274- and 230.337-second wall samples without another trace event. That is an observed near-stall, not proof of one particular numerical cause. No input or approval wait occurred inside these simulation subprocesses.

## Arrival correction and remaining performance question

Subsequent bounded probes captured the actual candidates at both near-stalls. Ordinary air pursuit scheduled a route endpoint on a moving target's current weapon-range circle. The remaining arrival duration could fall below `1e-10` seconds while the gap still exceeded `1e-10` tiles. Dropping that positive arrival allowed the target to pull away again, creating repeated pursuit cycles.

The scheduler now retains an arrival exactly when `time + arrival_delay > time`. This preserves representable forward progress without extending routes, widening range, adding a pursuit cadence or changing game behavior contracts. A three-actor synthetic kernel regression produces no attack with the old predicate; with the correction it kills the moving target at about `0.001064860391` seconds. Two solver steps exercise that result.

The captured TH17 equal-speed pair reaches the same range contact at `0.001126831961` seconds under step limits 0.25/0.125/0.01 after the correction. The old predicate gives different delayed contact times. However, the corrected pair still requires about 3,000 approach boundaries, so full-scene performance is a separate open check. The captured Dragon's weapon was cooling; range contact alone does not prove a shot.

Private before/after evidence is under `reports/equipment-boundary-diagnosis` and `reports/recipe-boundary-diagnosis`. The separate bounded CWL profile in `CWL_PROFILE_DIAGNOSIS.md` proves repeated route work dominates its earlier measured window. Full-battle reruns after the arrival correction retain their own bounds and source/input fingerprints; no full-recipe outcome should be claimed from the reduced tests.

## Native process failure and bounded mitigation

A subsequent Dragon/TH16 exact-recipe attempt using the private progress runner on Windows, CPython 3.12.14 (64-bit, MSC v.1944), exited with `3221225477` (`0xC0000005`, access violation). No worker result or completed battle outcome was produced; captured stderr was empty. The last periodic checkpoint was 20.496071081974563 simulation seconds, 151.0525203 wall seconds and 912 trace events. The supervisor ended after 159.143695 wall seconds. This was a native failure, distinct from the solver wall timeouts above.

The source/data aggregate SHA-256 was `563d380a28b7cc02e55bddd62e290632eef8020f3075e3f7d7ee0d9d4c39bad0`; the scene-input SHA-256 was `92d3d93a4227b7ea1b9b1e1ac6a120c8433277c76ab5fc3d80719bf49d544a5a`. The interpreter SHA-256 was `b7a12c3af0b4db44191eec14ea095eba731b7328917f570806183093d19ddca2`. Full input/source fingerprints remain in excluded local evidence; no private paths, recordings or raw account inputs are published.

The diagnostic runner removed scheduled `faulthandler.dump_traceback_later` calls while retaining in-thread progress, exception records and a supervisor wall deadline. One serial attempt with the same interpreter, source/data and input hashes reached 23.055884469172746 simulation seconds and 1,187 trace events. It stopped cooperatively after 165.0121214 wall seconds, before its 180-second hard bound, with child exit 3 (`0x00000003`) and a fresh matching result. No native failure was observed in that attempt. **This is mitigation evidence, not a proven root cause or crash fix; no full exact-recipe battle has completed.** Further simulation commands remain pending the runtime/performance investigation.

Separately, the higher-TH CLI now isolates every invocation in a new directory. The parent records a native/nonzero worker exit as failure before reading any success receipt; completion requires a zero exit and a fresh result matching run ID, worker PID, input hashes and engine/data fingerprint. These reporting protections do not change combat behavior or explain the native fault. Nonexecuting process stubs cover stale receipts and missing results; they do not certify native runtime stability.

## Evidence and remaining limits

Private inputs, hashes, exact binding audits, progress and stack files are retained under ignored `reports/recipe-integration/`. `manifest.json` describes the TH16 cases and `higher-th-manifest.json` describes the four higher-TH combinations. The net patch contains source, declared synthetic policies, tests and documentation, not account files or media.

Action Figure/Giant Giant identity, Frostmite example statistics, Totem landing quantities, Revenge phase mapping/HP and unmeasured geometry/timing policies remain explicit hypotheses. There are zero calibrated full battles. See the linked recipe and higher-TH contract documents for details. Unsupported configurations still reject; the implemented recipes do not establish full-category coverage.

No recipe/higher-TH changes were pushed or applied to the publication checkout. The parent separately published the preceding numerical state. This checkpoint is a reviewable local delta with remaining runtime and fidelity blockers.
