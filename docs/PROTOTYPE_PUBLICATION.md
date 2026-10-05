# Conditional full-village prototype publication

This draft publishes the reviewed source snapshot
`fc9d0b8a921dbc261f95be0418f8b7618b50a714` as a new commit above the existing
sanitized private repository history. Source-checkpoint hashes in this document
identify local review evidence; that development ancestry is not imported.
The source tree is `6f3adbac8ceba95f95d71e39206cc2aa06c510da`.
Publication changes are documentation and a compact verification receipt.

## Matched conditional comparison

Both cases use the same generated TH18 layout, 94 counted buildings, active Hot
Candle Station, Legend I profile and synthetic TH16 account. The plans retain
the same heroes, equipment, pets, siege, Castle and spells. Their troop mix,
deployment timing and Queen/Warden ability policy differ. Thus this compares
complete army plans, not an isolated troop substitution or defensive designs.

| Declared plan | Stars | Destroyed | Destruction | Town Hall | Simulated time | Worker wall time |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| 16 Dragons | 1 | 81/94 | 86.17% | Survives | 180 s | 199.875 s |
| 14 Dragons, 20 Minions | 2 | 84/94 | 89.36% | Destroyed | 180 s | 215.422 s |

Both stop normally at the declared time limit with a living Unicorn, under the
explicit policy that living support units preserve continuation. A completed
simulation is not a three-star result. Scouting is outside the combat clock;
deployment delays consume the declared 180 seconds.

Each army is legal under the entered synthetic account and pinned catalog:
320 home troop housing, 11 home spell housing, 50 Castle troop housing, three
Castle spell housing, four heroes and one Stone Slammer. All bound attackers
deploy. Each run spends ten spell slots totaling 14 housing and all three
planned manual hero abilities; Dragon Duke has no planned manual activation.
Active crafted launches and impacts are present in both traces.

## Reproduction and verification

Follow [the quickstart](FULL_COMPARISON_QUICKSTART.md). The runner requires
`--accept-experimental-air-contact`, uses a fresh output directory, runs one
worker at a time with a 400-second bound per case, preserves failed cases as
unscored, and records exact input/source/runtime/attempt/result identities.
It does not retry crashes automatically. Runtime dependencies are standard
library only. The source-only archive was extracted in a new directory and all
208 packaged file hashes matched the frozen source and saved-run identities.

Independent review recomputed both compiled inputs, budget validation, outcomes,
paid resource use and actual terminal decisions from the saved results. Result
hashes and fresh attempt identities match; both worker exits are zero. CLI help
and rejection without consent were checked from the clean extraction, including
the worker's consent guard. The two long battles were not repeated for review.
The complete portable suite passed 1,423 checks in 70.416 seconds in a fresh
checkout. Black 24.10.0 passed for 345 Python files; the offline catalog CLI
passed and left tracked files unchanged. CI separately checks the published
commit on Ubuntu/Windows and Python 3.10/3.12.

The [compact receipt](evidence/full-village-contact-summary.json) binds these
results to the exact source and input/result hashes. Full traces, local paths,
raw captures and evidence archives remain outside Git. Synthetic reproduction
inputs and required portable fixtures are included. Catalog MIT, Statscell MIT
and ClashKing GPLv3 notices remain distinct; see [third-party notices](../THIRD_PARTY.md).

## Acceptance boundary

This is scoped acceptance of an executable conditional comparison and its
publication, not a blanket mechanics audit or calibrated release. It retains
reviewed component corrections, unsupported-content guards, exact resource
ownership and explicit model policies. The air-contact change is semantic and
can change trajectories, targets, hits and outcomes; it is not merely caching.
See [the contact convention and focused checks](AIR_CONTACT_CORRECTION.md).
The original strict Dragon Duke isolation failure at 18.305471759 seconds is a
separate case/policy and remains documented in the publication baseline.

Complete held-out game calibration is zero. Seasonal availability, live-game
deployment legality, observation visibility and human latency remain unverified.
The two results do not establish win rates, an optimized base, or an in-game
army recommendation. Older war/Hero Hunter results and the separate full TH16
receipt retain their own engine/input identities and are not relabeled here.
Optional unfinished equipment and the unexecuted Balloon extension are excluded.

Earlier checkpoint documents record their historical status. In particular,
the TH16 near-20.735-second stall was later passed under the separate reviewed
`25e7deb539bee4802bddc4a1d184df6edbda11f7` convention; its full receipt was
independently verified, but is not a run of this combined publication. The
[backlog](PROTOTYPE_BACKLOG.md) still describes unsupported families and future
calibration work; historical stalls or review gates there are not new claims
about this matched pair.
