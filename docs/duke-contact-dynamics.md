# Experimental Dragon Duke contact dynamics

`nearby_translation_at_single_attracting_air_contact_experimental` is an
explicit, uncalibrated movement hypothesis. It is reported in the Duke result
and in contact start/end trace events. It is not evidence of observed game
behavior, and results produced with it must not be presented as calibrated
predictions or silently compared with a different engine policy.

The continuous isolation model can have an attracting discontinuity: nearby
Duke pursuit leaves the friendly-air circle, but his longer isolated range
stops him, letting the same ally immediately enter again. The existing guard
correctly rejects that unresolved pair of motions. The captured split-core
case first reached it with `army-dragon-12` at 24.884611317783275 seconds.

This policy supplies a finite continuation for a narrowly supported case:

- Exactly one eligible friendly airborne actor is inside the isolation circle.
- Duke has a direct, single-segment proposal. The ally has an unchanged direct
  proposal or follows a ground target, with a single segment. Neither is forced
  or missing a proposal (for example through freeze). The ally is not another
  Duke, and its speed when establishing contact is positive and no greater
  than Duke's available speed.
- Duke retains an eligible stationary enemy within his isolated range.
- At contact, nearby motion has positive relative radial velocity (exit),
  while an isolated stop has negative relative radial velocity (entry).
- Copying the ally's translation keeps Duke's endpoint inside the board.

At the actual exit-contact timestamp, the committed after-side stays nearby.
Duke then copies the ally's first translation segment at the ally's speed,
preserving their relative vector and the inclusive nearby state. An entry
from outside also reaches the normal circle boundary before this continuation
is applied. The solver's existing two-epsilon event advance can put that
entry slightly inside the circle: its existing committed crossing identifies
the contact, and the retained relative vector identifies its continuation.
There is no enlarged circle, new tolerance, position snap, skipped event,
sampled membership interval, or change to attack/status/resource clocks.

Once established, this contact also copies an ally's normal zero-speed weapon
stop, preserving the same relative vector and nearby side until it moves
again. At that stop the isolated-side radial velocity is zero; the policy
chooses continued inclusive contact. A fresh stationary-ally contact cannot
acquire this state. Missing or forced motion still releases it. This clause
matters when an ally alternates pursuing a moving ground defender and reaching
weapon range; immediately releasing contact during each weapon stop can
recreate the isolation relay a few milliseconds later.

The established partner also remains the contact partner if another friendly
air actor enters. Abruptly discarding the existing motion at the newcomer's
entry can reverse that exact committed entry even though Duke's nearby mode
never changed. This persistence does not allow acquiring multiple partners:
initial acquisition still requires a single friendly actor, and the original
partner must continue to pass the motion, range and lifecycle checks. A
nonpartner can enter during that stop and exit when the partner resumes.
Those real crossings are scheduled and delivered even if they immediately
reverse a committed side: another retained contact guarantees that neither isolation
nor contact ownership changes. The guard still rejects unresolved reversals
of the actual contact partner, or any reversal lacking another retained
contact. Focused controls require exactly one such entry or exit, then finite
progress with unchanged motion, isolation and unfinished attack cooldown.

Ordinary airborne following is resolved first to obtain the ally's motion.
Duke contact may depend only on an unchanged proposal or a follower of a
ground target; ground proposals are not changed by either contact resolver.
After resolving Duke, ordinary airborne following is recomputed from original
proposals with his resolved motion substituted, so enemies following him see
his final velocity. These motions then feed all route, field, trap, weapon
and hero crossing queries. This excludes circular dependencies through other
airborne following or another Duke, while supporting a moving ground defender.

Each frontier rechecks eligibility, targets, speed, geometry and membership.
Contact releases when those conditions no longer hold. Genuine range, route
arrival, lifecycle and circle-crossing events remain scheduled. Existing
isolation preparation still owns damage, range and cooldown changes. Fixed
cadence experimental isolation, when explicitly selected by an input, is
unaffected. Unsupported geometry still reaches the chatter guard; the sole
narrow exception above distinguishes a real nonpartner exit from a feedback
cycle, without dropping the exit event.

Focused synthetic controls cover approach from both sides at three temporal
step sizes, unchanged unfinished cooldown during translation, correct
cooldown rescaling when the ally dies, committed-entry roundoff, downstream
weapon following, ground-target dependencies, stop/restart continuity,
neutral translation, and excluded motion cases. Existing
Duke boundary/guard and airborne weapon tests also remain applicable. These
are numerical/model controls, not game calibration.
