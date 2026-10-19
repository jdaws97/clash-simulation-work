# Exact shared slow expiry

HitStatusCombat now retains a slow until its actual expiry, including an
observation one representable float before the deadline. The shared event loop
also retains a positive sub-tolerance gap to that expiry; spatial membership
tolerance no longer removes this temporal boundary.

One grouped regression covers both 2 - 5e-11 and nextafter(2, 0), the component
state, actual shared-loop expiry at 2, and the unchanged work-preserving weapon
launches at 0, 2.5, 3.5 and 4.5. Existing overlapping slow, poison, Freeze,
movement and source-death checks remain applicable.

This addresses the shared dependency reproduced by task18 while reviewing
Poison Lizard/Rocket component fix616383ec. Their full-battle admission is still
separate; no unsupported equipment or pet is admitted by this change. No replay
calibration, mechanic values or deployment policy is inferred.
