# Full-village conditional comparison

The matched pair has completed and its saved receipts were independently
verified. See [publication results and review scope](PROTOTYPE_PUBLICATION.md).
The command below reproduces the declared experiment under its explicit limits.

Run with Python 3.11+ from this checkout or its source archive:

```powershell
python -B tools/run_full_comparison.py --accept-experimental-air-contact --case ranked-defense-0-hot-candle-sixteen-dragons --case ranked-defense-0-hot-candle-fourteen-dragons-twenty-minions --output ../contact-pair-results-new
```

Use a new output directory. The command selects the matched Legend I Hot Candle
pair. Omitting both `--case` options selects all six predeclared cases. They run serially with a
400-second wall bound each and 2,400 seconds overall. No automatic retries,
watchdog threads, network or game interaction occur. A native process failure
stops remaining cases. Timeouts and failures are retained without outcomes.
Use `--case CASE_ID` to select a named case from the frozen manifest.

This edition requires explicit acceptance of the provisional air-contact
movement convention. An eligible airborne weapon at outer range may translate
with a departing/tangential retained target at target speed when it can keep up.
This is uncalibrated and may change trajectories, targets, hits and outcomes.
It preserves positive arrivals and existing attack clocks; it is not an
equivalent cache optimization or verified Clash movement. Consent and the
applied `air_contact_policy` are recorded in each new attempt/result.

`examples/full-comparison/manifest.json` pins each complete input. Each case
preserves the complete selected TH18 inventory, including walls, traps, four
defending heroes, defending Castle, Guardian and one active crafted Station.
Station placement is an exact same-footprint swap in the original synthetic
packing layout: one forward Hot Candle design and one central Hero Hunter
design. These are distinct design packages, not an isolated experiment on
only the module or only the position. No screenshot or player base is used.

The two original TH16 candidate plans use either 16 Dragons, or 14 Dragons and
20 delayed Minions, with full 320 troop housing. Each includes four heroes,
explicit paired equipment and pets, a Stone Slammer, full 11 owned spell housing
and a separately owned 50-housing Castle payload and three donated spell housing.
The second plan delays cleanup, changes Queen/Warden ability timing and gates
Queen activation on observed health. Exact loadouts and schedules are in every
input. These are synthetic candidate experiments, not current player loadouts
or recommended armies; equipment and action timing remain part of each plan.

Four cases use Legend I: both armies against both design packages. Two war
controls use the forward Hot Candle design with its unmodified battle profile.
Compare the two plans within the same defense and mode; no cross-mode pooled
score, opponent weights, overall ranking or optimization claim is produced.

Outputs include `comparison.csv`, `comparison.json`, copied frozen inputs,
per-worker logs, exact code/data/runtime/runner identities, paid resources,
crafted events, actual terminal decisions and compressed complete results.
Every successful receipt must bind to the fresh attempt and its result hash.

The source archive's checkpoint manifest identifies the exact new commit and
verification evidence. This edition integrates independently scoped-cleared
movement patch `25e7deb539bee4802bddc4a1d184df6edbda11f7` into the full-village
prototype. Its combined integration remains separately reviewable.

The preserved prior edition `6fa09dde4508368ce05fc10637958d8af4b84d53`, with
cache-only engine `3902967f36a82b7519b22e3f081c99c9f4ecd6fc`, completed five of
six cases and retained one unscored Legend I Dragon/Minion timeout. Those results
belong to that exact old convention. The new matched pair must be scored from
fresh runs; old war/Hero Hunter results are not relabeled as new-engine results.
The owner's separate Root TH18 receipt also retains its own input/engine.
TH16 full-battle completion is a separate workstream and is not claimed here.

The pinned catalog, seasonal selection, Giga response coefficients, motion,
targeting, equipment/child behavior and combat policies remain explicit
conditional models. The seasonal choice is not certified current availability.
Deployment passes the declared static mask; live game corner legality is not
proven. Observation samples engine state without visibility or human latency.
Complete held-out game calibration remains zero. See PROTOTYPE_BACKLOG.md for
other unsupported families. Optional unfinished Monolith wiring is excluded.
