> Predecessor Python filenames and parity procedures in this document are
> historical provenance from `f04706c`. Deleted tools are not runnable; see
> [the current documentation](../../README.md) for native commands and remaining Python ports.

> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Dragon Duke contact policy blocker

This strict-mode diagnosis was recorded against integration commit
`4ce79a13ffe4e3d862f829603392e31fc702161d`. Its diagnostic establishes rejection,
not battle completion. An optional continuation is now documented separately in
[the explicit sampled-isolation experiment](DUKE_CONTACT_EXPERIMENT.md).

## Why the remaining failure is not root roundoff

The endpoint-root canonicalization in `dragon_duke.py` already removes the
spurious near-zero interval. The remaining contact has opposing, nonzero
relative radial velocities on the two sides of the isolation radius.

`DragonDukeCombat.prepare` immediately changes weapon range from the nearby
range to the isolated range. `spatial._select_target` retains an eligible target,
and `spatial._route` returns an empty route when that target is in weapon range.
Consequently, the same target can require chasing in the nearby state and
stopping in the isolated state. `HeroRosterCombat.first_crossing_delay` receives
these completed trajectories, so the contact calculation is using the motion
that the scheduler intends to apply.

A synthetic one-dimensional example makes the conflict explicit. Place Duke
at x=10 and an ally at x=7, use isolation radius 3, and let the ally move right
at 2 tiles/second. A retained target at x=14 is in isolated range 4 but outside
nearby range 1.25. Duke's chase speed is 2.5 tiles/second. Define
`q = x_Duke - x_ally - 3`:

- Outside, Duke stops: `dq/dt = 0 - 2 = -2`, pointing into the radius.
- Inside, Duke chases: `dq/dt = 2.5 - 2 = 0.5`, pointing out of the radius.

Neither after-side remains consistent with its own motion. More accurate roots,
smaller steps, or a different inclusive-boundary comparison do not specify a
continuation. Holding q=0 would instead require a new contact motion rule; in
this example it would move Duke at 2 tiles/second, neither of the two declared
velocities. It would also require explicit rules for isolation-dependent damage,
attack cooldown rescaling, projectile choice, and multiple simultaneous allies.

The existing boundary tests already exercise this attracting relay at horizons
0.01, 0.1, and 1 second, ordinary exits and later reversals, inclusive contact,
roundoff contacts, and partitioned simultaneous motion. No additional regression
tests were added to duplicate that coverage.

## Reproduce without changing the model

Use Python 3.12.14 from the checkout root. Keep the four preserved input files
outside Git and write the detailed diagnostic under ignored `reports/`:

```powershell
python -B tools/diagnose_duke_contact.py `
  --fixtures '<private full-army directory>' `
  --prefix 'air-ranked-none-180s-step-0.25-' `
  --duke dragon-duke --ally army-dragon-15 `
  --wall-seconds 180 `
  --output reports/contact-diagnosis/original.json
```

Repeat with `--step 0.125` and a distinct output path to check a nearby step
size. This override changes only `entity_scene.maximum_step_seconds` in memory;
the tool records it separately from the hashes of the unchanged input files.

The observer calls the original crossing method unchanged. It records six recent
states, retained targets, target distance, motion velocities, and committed sides.
It never bypasses the rejection guard. The supervisor kills and waits for only
its own simulation subprocess if the explicit wall limit expires. Rejection and
timeout return nonzero; they cannot be mistaken for completion. Input hashes and
a source/data fingerprint are included with the private evidence.

## Evidence and next action

The unchanged original input reproduced the rejection at
18.305471758783998 simulated seconds in 57.494 seconds wall time under the
180-second cap. The retained target did not change. Immediately before contact
the relative radial velocity was positive, approximately 1.05 tiles/second;
the isolated state made it negative, approximately -1.19 tiles/second.
These signs are not a machine-precision ambiguity.

The half-step run rejected at 18.30547175878399 simulated seconds in 57.922
seconds wall time, also under a 180-second cap. Both runs used source/data
fingerprint
`d6e1a97993aebafa07530f569549f1c438ffaac364d634a4555d9cbf46507bc8`.
The original input hash was
`b49d055eade4154ce90a3cf29162be504e9e7ae8434e8e86615c7a4725e3ac1b`.
Neither run completed the battle; both returned the existing explicit rejection.

`python -B verify.py` passed all 1,191 existing tests in 26.045 seconds,
supervised with a 120-second wall limit (27.437 seconds including startup).
Black 24.10.0 accepted the diagnostic script with `--check --workers 1`.
A separate 0.001-second supervisor check returned `wall_timeout`,
`completion_proven: false`, and exit code 2 in 0.015 seconds. These checks use
Python 3.12.14. Logs and detailed states remain local under
`reports/contact-diagnosis/`.

Completion requires an explicit contact-response contract supported by observed
behavior or clearly declared as an experimental hypothesis. Possible contracts
include a specified membership sampling cadence, a specified release/retention
rule, or explicit contact dynamics. These have different movement and combat
consequences; selecting one merely because it finishes this fixture would change
the model. The current input specifies none of them. Preserve the diagnostic
rejection until that contract is established, then implement and validate it
against the unchanged battle plus nearby contacts.

No private fixtures, detailed runtime states, or generated evidence are part of
this commit. No publication or merge is performed by this diagnostic.
