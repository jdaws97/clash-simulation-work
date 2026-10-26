> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Airborne weapon contact correction

This delta is separate from the accepted exact-cache candidate `059b5e38`.
It changes movement semantics and is **not** an equivalent optimization or a
claim about verified Clash movement. The result exposes the applied convention
as `air_contact_policy`; existing explicit ruleset and unsupported-content
validation remain in force.

## Problem and evidence

In the private synthetic TH16 recipe, an Archer pursues defending Dragon 1 while
two Dragons pursue the moving Action Figure Giant. The old engine alternates
between stopping a Dragon at inclusive weapon range and restarting it when an
Archer arrival exposes another microscopic gap. These are positive movement
boundaries, not a stuck timestamp, duplicate attacks, or Healer events.

A four-owner replay exactly reproduces all 96 captured boundary times and the
four owners' positions, HP, target locks and attack clocks at the final snapshot.
Extending that replay to 1,000 boundaries advances only 1.5499643311045475e-6
seconds. No chasing weapon becomes ready in that window. Removing the Archer
from the diagnostic reduces a 0.001-second window to two boundaries. Raw input,
actor captures and diagnostic receipts remain outside Git.

## Declared correction

At the existing outer inclusive range boundary, an airborne weapon that has
stopped may translate with its retained enemy's first straight movement segment
at that enemy's speed. This applies only when the enemy departs or moves
tangentially, the source can keep up, and the translated endpoint stays on the
board. It preserves the current relative position and hence weapon range.

This represents continuous tracking after established contact. A faster airborne
weapon can maintain firing distance from a slower departing target without an
unrelated actor repeatedly switching its velocity between zero and full pursuit.
Copying target translation is an explicit convention; it is not a calibrated
claim that the game selects this particular minimum-distance pursuit trajectory.

Ground movement is unchanged. Actors deeper inside range, approaching targets,
stationary targets, faster departing targets and blocked/absent movement keep
their existing routes. Frozen or spell-paused sources have no proposed motion;
forced source displacement is excluded. Enemy eligibility, target locks, rates,
attack readiness and all status clocks are unchanged. Contact following ends
when these preconditions cease to hold. Mutual stopped target cycles do not
create movement, and target dependencies resolve before their followers.
Changed trajectories can still change future target choices, hits and battle
outcomes; this delta does not claim full-trace equivalence to the old policy.

All routes are selected before contact motion is resolved. The same resulting
route and effective speed are then passed through route arrivals, traps, fields,
other crossings, weapon contacts and final movement. The range tolerance is
unchanged. No event is discarded for being small, and no attack is skipped during
cooldown: ordinary readiness checks still execute at their original clocks.

## Bounded validation

- The corrected captured replay reaches +0.001 seconds in 9 boundaries (about
  0.0255 seconds wall time), including 7 positive tiny Archer arrivals. Its
  smallest executed step is 4.4444448121794267e-11 seconds. Old and new movement
  traces intentionally diverge once the new contact convention applies.
- Four focused synthetic regressions check progress, exact ready attack times
  and damage across steps 0.5/0.07/0.011; source Freeze and cooldown resumption;
  exclusions for faster/approaching targets, interior range, pauses, forced
  motion and board limits; and exact buff crossing/modified damage at the actual
  following speed across steps 0.5/0.013.
- 206 affected tests pass in 2.433 seconds, covering contact/range geometry,
  ordinary movement/walls, forced displacement, traps, buffs, healing and pets.
  No broad suite or expensive full battle was run for this delta.
- Two complete paid Root/Dragon controls match the accepted candidate's entire
  decoded results, including traces and resources, after removing only the new
  explicit `air_contact_policy` metadata field.
- One bounded run of the unchanged original TH16 input passes the former stall
  and stops normally at 25.000000000000117 simulated seconds: 169.1634 worker
  seconds, 1,428 observed frontiers and 1,848 trace records. Input hashes match
  the original diagnosis. The observer stops at the requested prefix; no full
  TH16 outcome or broader performance guarantee is claimed.
- Every reported run has a fresh receipt, zero exit and unchanged source hashes;
  no scheduled traceback watchdog or automatic crash retry was used.

Timestep robustness is bounded: the new air offsets, firing clocks and resulting
damage agree in the focused controls. Existing weighted ground replanning still
produces small absolute position differences across partitions; this patch does
not fix that separate convention or claim whole-battle timestep equivalence.

Run the focused regression with
`python -B -m unittest discover -s tests -p test_air_contact_following.py -v`
with `src` on `PYTHONPATH`. Parent receives the external receipt manifest and the
separate frozen delta for independent review. The accepted TH18 prototype remains
on its original candidate.
