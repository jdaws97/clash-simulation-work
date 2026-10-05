# Controlled TH16 defense comparison

This follow-on fixture compares the project's generated ranked staggered-compartment
and split-core TH16 layouts against the same synthetic TH17 air attack. It preserves
the combat engine and data from `fc9d0b8a921dbc261f95be0418f8b7618b50a714`.

The reviewed architecture generator supplies both layouts. Exact full selected
inventory, merge conservation, footprint admission and initial deployment checks
must pass. Both carry one active phase-4 Hot Candle Station with module levels 1.
Its seasonal selection and behavior remain explicitly conditional; catalog and
geometry admission do not prove live-game placement legality or current availability.

The attacker has 17 level-12 Dragons (340 housing), four heroes with paired pets and
equipment, one owned Stone Slammer, 11 owned spell housing and 3 donated spell
housing. The Castle holds two Dragons, two Wizards and seven Archers (55 housing),
with levels validated through the TH17 receiver's Castle donation cap. Owned levels
come from the pinned catalog's TH17/Laboratory limits. This is a synthetic supported
TH17 profile, not a relabeled TH16 attack or a player account.

Both cases use the same west-side deployment, fixed ability times, spell coordinates,
termination rules and Legend I role-aware profile. The builder requires identical
attack projections after removing only scene/specification labels and defenders.
It also requires identical defense records after removing only coordinates. Thus
geometry is the comparison variable; army, settings and inventory are controlled.

Run from this repository with standard-library Python:

```powershell
python -B tools/run_full_comparison.py --manifest examples/defense-comparison/manifest.json --output ../defense-pair-run1 --accept-experimental-air-contact
```

Use a fresh output directory. The manifest permits two serial cases, at most 240
wall seconds each and 485 seconds overall. Timeouts and errors receive no score;
there are no automatic retries. The runner accepts fixture-specific interpretation
limits from the manifest, retaining its previous limits for older manifests.

To regenerate inputs into a fresh directory:

```powershell
python -B tools/build_defense_comparison.py --output ../regenerated-defense-inputs
```

`preparation.json` records catalog identity, capacities, full inventory admission,
and the identical attack/nongeometry hashes. Both bundles retain every experimental
policy. Airborne contact following is explicitly accepted and can change outcomes.
There are zero complete held-out game calibrations. One fixed attack per layout
cannot establish a generally best base, opponent distribution or game recommendation.
