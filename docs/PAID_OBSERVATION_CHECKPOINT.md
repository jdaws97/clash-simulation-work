# Finite paid observation checkpoint

Capability: `paid-observation-scheduler-v1`. This is an explicit experimental
control policy over the existing v29 paid battle compiler, not a measured
player-response model or a calibrated game prediction.

`simulate_full_battle` accepts an optional `paid_observation_plan`. Its exact
policy keys and values are exported by `clashlab.paid_control.POLICIES`; callers
must supply them, a source, an observation interval, a complete event list and
an explicit funnel declaration. Missing or different policies fail closed.
Each event selects exactly one already admitted actor deployment, command or
spell and supplies its admitted earliest time plus typed conditions. All
scheduled paid actions must be covered exactly once. Placement and ownership
are still checked by the ordinary compiler. Conditions can inspect time,
alive/active state, health fraction or the current active target identity.

The finite grid includes interval samples, exact earliest times, the funnel
deadline and the inclusive battle limit. The interval grid has a 10,000-boundary
budget and there are at most 512 events. Observations occur before commands and
same-time combat settlement, once per boundary. Commands recheck their cues and
execution eligibility when released. Same-boundary deployments precede their
abilities/releases. Effects caused by commands or damage at this boundary
become observations at a later grid point. Tiny positive control boundaries
are not rounded backwards; a paid observation battle reaches its exact time
limit even when a preceding event lies within the legacy epsilon.

Held spells are removed from runtime schedules until paid release. The
existing spell owner handles impact, fields, children, Recall and expiry.
Impact delay and Recall's return offset are preserved relative to actual cast
time. Finite generated actor identities remain the compiler's owned reserves.
The execution ledger starts with unspent spells and undeployed actors, then
records actual releases once; the original admission ledger remains available
separately. Termination reads the same actual spell ledger and existing
continuation facts, including latent generated offense after army loss.

Funnel commitments require a battlefield-state prerequisite, a deadline and
both failure and Hall-bait contingencies. Main and alternate event IDs are
disjoint paid reservations. The first matching declared contingency wins;
failure is eligible at/after the deadline, Hall bait at any observation. Main
commitment requires an executable event and its prerequisite before or at the
deadline. A selected alternate rechecks its own cues on execution. Unchosen
branches stay unspent; no branch grants extra army, ability, CC or spell slots.
If no branch is ready by the deadline, commitment is held. This selected order
is an explicit hypothesis, not inferred live-game behavior.

Joint search plans can now supply `observation_policy` containing the source,
interval and all policy keys. Search applies declared placements first and
passes the complete finite event/funnel plan into the paid compiler. The
scheduler dependency is removed only when the compiler returns this capability.
Plans without the policy remain blocked and unscored. Receipts include the
actual paid observation audit. Existing opponent immutability, cache identity,
failed-result handling and crafted-profile dependency gates remain in force.

Seven bounded grouped acceptance cases exercise:

- health-triggered Freeze, hero ability and reserve deployment at two steps;
- exclusive main, alternate and held funnel branches;
- Bat casting after army loss, actual owned child offense and malformed plans;
- direct CC and carrier deployment/release with one shared payload at two steps;
- delayed Rage membership and Recall capture/return with later real offense;
- positive sub-epsilon release, inclusive final deadline and stale alternate cue;
- actual subprocess search admission, delayed paid cast and identical cache reuse.

Fixtures are synthetic partial inventories. No full-village strategy ranking,
human latency calibration or held-out game accuracy is established. Independent
review of this new shared-kernel integration remains pending.
