# Moving enemy contact for air weapons

Base: 3a814ec6a36f06de3f2165b0c9da0df2a0b43972. A fresh bounded observation
of the unchanged private Root input identified 64 route arrivals by one defending
Dragon chasing an Action Figure Giant, plus eight range contacts for the same
pair, among 80 boundaries from simulation18 to18.15485954461885. These were
progressively stale range-edge destinations for a moving primary, not a reason
to round clocks or increase timeouts.

An airborne damage-dealing actor pursuing an enemy mobile primary now points its
route at the primary's current footprint. The existing relative-motion contact
scheduler clips the movement at weapon range. It therefore follows the same ray
without prematurely stopping at the primary's former range edge. Stationary
enemies, allied support, ground routes and nonweapon movement retain their prior
endpoint rules. Target acquisition, speed, damage and clock precision are unchanged.

Three focused checks cover analytic moving-relative contact with and without
Freeze across coarse and fine maximum steps; unchanged stationary/allied endpoints;
and a paid Root Rider against an owned defending Dragon released from its Castle,
with exact first lethal contact, finite paid ownership, counted building outcome
and attack exhaustion. The tiny paid case deliberately scales HP and movement to
isolate contact; it is not a combat-strength or gameplay calibration claim.

The fresh unchanged-input full Root run exited zero and stopped orderly after
120.041 wall seconds at simulation19.200834425709726 through720 boundaries. It
produced no result artifact or battle outcome. The prior run reached18.4746 through
888 boundaries. Host timing and the changed event sequence prevent a general speed
claim from these single attempts. The fix removes the demonstrated contact cascade;
full recipe throughput remains open and requires further bounded owner profiling.

Current ranked strategy is not validated by this historical throughput fixture.
No new recommendation follows from the patch. Independent review is pending;
complete held-out game calibration remains zero.
