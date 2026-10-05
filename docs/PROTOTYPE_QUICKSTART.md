# Runnable conditional simulator prototype

From this checkout, using Python 3.11 or later:

```powershell
python -B tools/run_prototype.py --output ../prototype-results-new
```

Use a new output directory for every run. The runner uses only the Python
standard library and the included pinned catalog. It runs serial workers with
a 12-second wall limit per candidate. Inputs and engine/data fingerprints are
checked; timeout, error and unsupported results receive no score.

The output contains `prototype-summary.json`, a readable `comparison.csv`, and
per-scenario input manifests, expanded candidates, worker logs, resource and
outcome receipts, code/data/runtime identities, and completed-result cache
entries. A deliberate unsupported Monolith Arrow control must reject without
an objective. The unfinished optional Monolith implementation is excluded.

## What this demonstration does

Four frozen original input manifests in `examples/prototype` define two troop
mixtures, two plans and two compact TH18 defenses. Each uses a TH16 synthetic
account and the explicit Legend I profile. The mixtures are 16 Dragons, or
14 Dragons plus 20 Minions: 320 troop housing each. Both use one Queen with
Invisibility Vial/Magic Mirror, Unicorn, one Freeze and one Rage. Only three of
eleven spell spaces are filled; the Castle and siege slots are empty. These
are comparison inputs, not competitive army recommendations.

Each declared defense contains four counted buildings: TH18 Hall, active Hot
Candle Station, Air Defense and Archer Tower. Longshot and a visible Giga Bomb
participate under explicit response policies. The two coordinate arrangements
were authored for this demonstration; no screenshot or user base was used as
a template, and no opponent distribution weights were assigned.

The paid observation controller releases one final Dragon only after observed
Station damage. It has explicit failed-funnel and Hall-bait hold branches.
One plan spends support early; the other gates Freeze on Dragon health and the
Queen ability on her health. Resource receipts record actual releases and
unused slots. Shared spell, pet, child, death and continuation runtimes settle
the resulting battle to destruction, exhaustion or the declared time limit.

The first execution completed all eight battles in 9.157 wall seconds. All
four-building defenses were destroyed at 5.181–5.980 simulated seconds. These
easy, compact cases demonstrate the execution and comparison plumbing. They
provide no evidence for triples against a complete TH18 village.

Within one exact scenario, the existing search report compares its two plans.
The CSV places separate scenarios beside one another descriptively. Different
rosters require different explicit defender-response maps, hence different
scenario identities. No pooled rank or overall winner is computed.

## Verified foundation and limits

The engine base is `eed285efad426157b267547b29811ce96a4cf267`, with 1,416
portable tests passing. It includes the frozen paid scheduler, Giga/Barracks
audit corrections, reviewed equipment components, corrected layout pipeline
and actual crafted-profile scaling. Giga P1/P2 were independently cleared on
`3d97fe184e8731e2149c725b2bc70455e44fdae7`. The scheduler was independently
conditionally accepted on `f4289c440985a52b3284a1f09e4d356253fd5572`: its cues
sample engine state, without a sensor-visibility or human-latency model.

The full-inventory layout workflow is also included:
`tools/build_layout_search.py`, `tools/run_layout_ensemble.py` and
`docs/LAYOUT_SEARCH_CONTRACT.md`. It preserves selected inventory, immutable
input identity and failed cells. Mixed-army Giga case preparation still needs
an explicit contract bridge; its guard remains closed and no trap is removed.

Root pursuit on the TH16 full-village case remains unresolved. The throughput
owner's latest intentional stop established no outcome; increasing the wall
limit is not a mechanics fix. A separate full-village result, if accepted, must
retain its own exact input, engine identity and completion evidence. It cannot
be relabeled as a result from this compact prototype.

Catalog snapshot, source policies and every experimental input are retained
in the manifests and receipts. Movement, targeting, splash, Guardian responses,
Giga coefficients, observation timing and seasonal selection are conditional
models. Current account levels/availability, current season, human latency and
real-game fidelity are not verified here. Complete held-out game calibration
remains zero. War/CWL and higher/lower opponent classes must stay separate.

Optional families remain in the engine backlog. Unsupported bindings fail
closed; component presence alone never implies a paid full-battle lifecycle.
No game interaction, external publication, merge or deployment is performed
by this runner.
