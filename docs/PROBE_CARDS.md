# Friendly-challenge probe cards (RM1)

**Hypotheses, not game calibration.** The Rust alternatives are provisional.
The CSV names and numbers establish candidate rules to test, not their meaning.
Every fixture and result under `fixtures/mechanics/` is declared synthetic.
Do not mix these outcomes with real-game calibration records.

Record the deployment release, first turn, first target, first wall strike, first
building strike and target switches at 60 fps. Keep troop/building levels and hero
loadouts fixed. Start without pets, equipment, spells or defending CC unless a card
requires them. Place other required village buildings far from the test lane and
verify none enter the nearest-six list. Use paired layouts differing in one item;
repeat forced-retarget/noise cards at least 20 times. Frame times distinguish
latency from actual first movement/attack. Save the layout and notes with the probe
ID; do not commit private replay media or raw captures.

Coordinates in layout instructions are village tile coordinates, with building
locations referring to the top-left corner. The Rust fixture's explicitly prepared
unit positions are world coordinates (village coordinates plus the catalog's
3-tile margin). Synthetic prepared targets isolate a rule; they are not observations
of how a real player can deploy. Friendly probes below recreate those states by
staging support and then making one controlled troop drop.

## T1 — nearest-three list versus cheapest route (`target_list`)

Minimal lane: three low-level 3x3 Gold Storages A=(14,18), B=(14,23), C=(14,13),
inside a rectangular wall at x=12/18, y=10..28 (top and bottom joined). Put open
storage D=(5,35). Drop **one Barbarian at (5,19)**, outside the red line. Keep every
other building farther away. Use a Giant and Cannons instead in a second pair to
check preferred-defense filtering, keeping sizes/distances matched.

Hypothesis: legacy global path ranking chooses open D first; a three-candidate
model chooses one of A/B/C and approaches the wall. Record first target, direction
at 1/3/5 s and first wall/building strike. In the declared-synthetic demo this
changes first target **D (id 3) → A (id 0)**. The measured game outcome must decide
whether edge distance, centre distance, or another candidate metric fits.

Move D inward one tile at a time across third/fourth/sixth-nearest thresholds.
This tests `TARGET_LIST_SIZE=3`, `MAX_TARGET_LIST_SIZE=6`, and whether the larger
list is an unreachable/forced expansion. Block all primary routes with buildings
in a separate pair; do not conflate an expensive wall route with an unreachable
route. Rust uses a maximum of six only when forced or all primary paths fail.

## T2 — path and wall cost / extra candidates

Use one low-level Cannon A behind one wall row and an open Cannon B a few tiles
farther away. Drop **one Giant** from the lane centre; move B outward in one-tile
steps. Repeat with two separated wall rows, not a thicker visual wall at the same
location. Record target and first wall strike.

Hypotheses: the crossover moves by about 10 tiles per wall crossing if
`WALL_COST_BASE=1000` shares the 100-units/tile distance scale; legacy cost predicts
about 12. Actual grid costs depend on the wall cells crossed and attack reach.
Fit the crossover from paired paths, not by equating raw walking time and wall DPS.
Then use the T1 fourth candidate during a forced retarget. Vary the added open
candidate's path in one-tile steps: the Rust extra-candidate hypothesis adds
`EXTRA_TARGET_PATH_COST_PENALTY=5` tiles per extra rank. Whether 5 is tiles, internal
units, a multiplier, or applies to all candidates is **unresolved**.

## T3 — forget, remember and forced stickiness

Place storage A behind a blocker arrangement with no immediate usable attack
position and open storage B alongside it. Drop **one Barbarian** toward A. Film
without interference past 2 s, 4 s and 6 s. In a paired layout, allow the troop to
keep striking a wall without advancing. Record whether distance, wall damage,
movement, or a periodic timer governs target changes.

Hypothesis: `FORGET_TARGET_TIME=6000` means six seconds without route/attack
progress, rather than the legacy two-second stuck-waypoint fallback. Repeat with
an unobstructed A and one CC defender lured into the lane after A was selected.
After the defender dies, record whether the Barbarian resumes A or chooses B.
This distinguishes `REMEMBER_ORIGINAL_TARGET` from ordinary nearest selection.
Move or reveal a Tesla during a second pair to separate
`STICK_TO_TARGETED_BUILDING_WHEN_FORCING_RETARGET` from remembered retaliation.
The exact forgetting trigger and memory lifetime remain hypotheses.

## T4 — retarget noise and cause

Use two near-tied candidate Cannons beyond a fork. Drop **one Giant** at the same
point in repeated challenges. Make three paired causes after it has committed:
a defending knockback (DEFAULT hypothesis), a Jump becoming usable/expiring (JUMP
hypothesis), and a nearby Tesla reveal (TESLA hypothesis). Keep the two candidates'
path difference small and record the chosen branch and switch frame.

Hypotheses: forced score-noise upper bounds are DEFAULT=800, JUMP=100, TESLA=400
internal units, interpreted in Rust as 8/1/4 tiles. Uniform additive noise, event
classification, sign, and scale are all **unvalidated**. Compare branch frequencies
across repeated probes; a single different branch is not a noise estimate. Also
check whether an already eligible original target remains sticky and suppresses
noise. If nothing switches, first test stickiness before inferring zero noise.

## T5 — selected wall / retarget after wall death

Put two live Cannons on opposite sides of one shared wall approach. Drop **one
Giant** and let it start breaking the wall. In a pair, destroy the second nearby
wall remotely after about 1 s, 3 s or 5 s. In another pair, let its chosen wall die
naturally with the two Cannons equally reachable. Record selected-wall persistence,
first turn after wall death and next building target.

Hypotheses: `SELECTED_WALL_TIME=4000` holds a live wall for four seconds;
`RETARGET_AFTER_DESTROYING_WALL=false` preserves the building destination.
Compare against immediate reranking after a new opening. Rechoosing the same wall
at four seconds is consistent with a hold timeout; it is not proof of an infinite
hold. Jump bypass should end wall attacks immediately even during a hold.

## W1 — spatial group versus aggregate target voting (`warden_spatial`)

Use two isolated storage targets A and B. Stage five Giants within a 5-tile patch
so three commit to A and two to B. Stage three more Giants spread around the patch,
more than 5 tiles from its centre and from each other, but within 13 tiles of the
Warden drop; have these three commit to B. Then drop **one Grand Warden** at the
marked centre. Film his first target/path. Adjust the support staging as necessary;
record actual positions and targets when the Warden is released.

Hypothesis: old aggregate voting favors B (five Giants targeting it); the heaviest
spatial group favors A (three of its five members). The synthetic fixture uses
prepared ally targets to isolate that vote, and changes B (id 1) → A (id 0).
Separate compact groups gradually across 4/5/6 tiles to test
`TargetGroupsRadius=500`. Build a long chain with adjacent gaps below 5 tiles to
distinguish seed-centred neighborhoods from transitive connected groups.

For threshold probes, stage one small group just below/above the catalog weight
20 (Grand Warden), or weight 10 (Apprentice Warden), then make **one Warden drop**.
`TargetGroupsMinWeight=2000/1000` divided by 100 is a hypothesis connecting CSV and
wiki weights; it is independent of the established distance scale.

## W2 — wait for group retargeting

Prepare one compact qualifying group whose last building is about to fall, with a
second distant building still alive. Drop **one Grand Warden** just before the
first building dies. Film the interval in which group members have no live target.
Repeat with the group dispersed or below threshold.

Hypothesis: `WARDEN_WAITS_FOR_GROUP_RETARGETING=true` pauses the Warden until the
qualifying group selects its next target; immediate independent targeting predicts
a first turn or shot toward the second building. Separate waiting from cooldown,
first-hit wind-up, group movement following, and retaliation. The exact waiting
state, duration, membership updates and tie rules remain hypotheses.

## C1 — defender separation (`defender_separation`) and ground crowding

Minimal defense: one Clan Castle with two Barbarians and an otherwise empty lane.
Drop **one Giant** at the same marked point to draw both defenders out. Film their
exit timestamps and trajectories as they converge. Use a second pair where their
approach is blocked briefly so they overlap. No splash or poison is needed for the
first position measurement.

Hypothesis: legacy defenders may remain coincident; separation pushes same-height
mobile defenders apart. The synthetic demo prepares two coincident defenders and
shows a position difference on the first tick. Real CC units exit sequentially,
so compare positions after convergence, not at their different release times.
For attacker ground radii/push, repeat single-troop drops at a fixed held-deploy
cadence into the same lane and measure pair gap/overlap decay. Sweep housing and
use air pairs as the existing 0.35-tile reference. Fit radius and per-tick push
separately; the current ground base 0.35, housing slope 0.015, cap 30 and push 0.25
are **assumptions**.

## H1 — navigation and planning before reveal (`hidden_information`)

Use two near-tied visible storages with a Tesla in one approach lane, outside its
trigger range at deployment. In the synthetic fixture, the visible targets are
(24,20) and (5,39), Tesla=(18,19), and the single Barbarian starts at village
(5,20). Drop **one Barbarian**, film path and target before the Tesla rises, then
repeat after moving only the concealed Tesla. A more sensitive pair uses a narrow
fork whose branch decision occurs outside the Tesla trigger radius.

Hypothesis: hidden positions cannot affect an attacker's route or spell planning
before reveal. The old grid includes the concealed footprint; the new grid adds
it only when revealed. Compare the first path samples and reveal frame, then verify
rerouting after reveal. The current targetability check already excludes the Tesla,
so a first-target difference is not required. Include a trap-only moved pair as a
negative control: current traps have no navigation footprint and plan code does
not inspect their coordinates. Physical damage and trigger timing can diverge
**after** the troop reaches the hidden hazard; that is not planning hindsight.
For a plan probe, offer a Lightning-capable opener and move only a hidden Tesla;
record whether the intended pre-reveal aim changes.

## Runnable synthetic proofs

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-rm1
export BASELAB_CATALOG="$PWD/rust/data/catalog.json"
cargo test --manifest-path Cargo.toml -p clash-engine --test mechanics
cargo run --manifest-path Cargo.toml -p clash-engine --example mechanics_proof
cargo run --manifest-path Cargo.toml -p clash-engine --example mechanics_proof -- summary
cargo run --manifest-path Cargo.toml -p clash-engine --example mechanics_proof -- sizes
cargo build --release --manifest-path Cargo.toml --bin baselab-engine
/tmp/clash-target-rm1/release/baselab-engine golden check fixtures/golden/cases.jsonl fixtures/golden/expected.jsonl
```

`demos.json` declares all four battles. `evidence.json` records before/after
samples at 0.1/1/3/5/10 s when the battle reaches those times, its per-tick path/target
FNV64 digest, first damage to any building/wall, end time and outcome. First damage
is reported at the end of the tick that delivered it, not as a sub-tick animation
measurement. `null` means no such event before the synthetic battle ended.
Defender-separation samples observe the defender; other cards observe the attacker.
Hashes are reproducibility checks, not security proofs or game measurements.

| Synthetic demo | First target before → after | First building damage before → after | End time before → after |
|---|---|---|---|
| target-list | "Building(BuildingId(3))" → "Building(BuildingId(0))" | {"time":7.9,"building":3.0} → {"time":6.9,"building":0.0} | 34.2 → 35.3 |
| warden-spatial | "Building(BuildingId(1))" → "Building(BuildingId(0))" | {"time":5.2,"building":1.0} → {"time":4.8,"building":0.0} | 11.3 → 5.9 |
| defender-separation | "Unit(UnitRef { id: UnitId(1), team: Atk })" → "Unit(UnitRef { id: UnitId(1), team: Atk })" | {"time":21.3,"building":0.0} → {"time":21.3,"building":0.0} | 21.3 → 21.3 |
| hidden-information | "Building(BuildingId(2))" → "Building(BuildingId(0))" | {"time":9.3,"building":2.0} → {"time":6.5,"building":1.0} | 30.7 → 12.1 |
