# Bounded CWL performance diagnosis

The saved ground war/CWL comparison previously reached a 900-second wall limit without a battle outcome. Its last heartbeat was simulation time 37.201609 seconds. This is a censored run, not a loss or a completed result.

A diagnostic run used an archive of commit `c61900535b7ca3ac55c1f7380fa73fdb778506d7`, independent of concurrent recipe edits. It used the exact saved account, army, layout and scene inputs. It began cProfile at simulation time 10, stopped after 60 seconds of profiled wall time, and had independent inner/outer wall bounds of 175/200 seconds. Only its own subprocess was controlled. Total wall time was 154.60 seconds. The last periodic sample was simulation time 12.833569 at wall time 150.05; the simulator continued making progress until the profiling stop.

The measured window contained 170,468,962 function calls and 214 solver boundary checks in 59.65 profiled seconds:

| Operation | Calls | Cumulative seconds |
|---|---:|---:|
| Target-selector chain | 101,436 | 32.75 |
| Ground wall virtual route | 13,023 | 20.71 |
| Ground attack-point calculation | 3,521,974 | 10.41 |
| Weapon range-boundary scanning | 214 | 4.94 |
| Trap update | 214 | 4.14 |

Rows are nested and must not be summed. At 60 wall seconds, a passive traceback also found the process inside `walls._virtual_route` → `ground_attack_point`, called by the movement target-selection pass. The dominant measured cause is repeated weighted grid-route searches and actor/target scans across small event boundaries. There was no wait for approval or input in this run, and its observed progress is inconsistent with a process deadlock.

This profiles an early window, not every later boundary around simulation time 20.8–21.2. It does not prove there is no additional late hotspot. A safe next optimization is exact-input reuse of virtual route work, with live wall HP, obstacle set, source position, rate, damage, target geometry and policy in invalidation. Then compare complete traces against the pinned implementation on representative ground fixtures before rerunning the full case under a bound. Increasing the timeout alone supplies neither a cause nor a valid outcome.

Local ignored artifacts retain `profile.pstats`, the sorted profile, periodic progress, traceback and reproduction script under `reports/cwl-profile` and `reports/profile_cwl.py`. The handoff manifest records their hashes. Private comparison inputs remain outside the net patch.
