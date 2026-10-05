# Flinger overlap correction and shared continuation contract

The independent review reproduced 240 component flame damage in `(1, 2]` from
one level-1 source with a declared 80 maximum DPS. Field-local clocks composed
only coincident ticks, so staggered fields minted additional damage budgets.
This delta replaces those clocks with one per source. It does not claim exact
live-game timing; it enforces the declared conditional source composition.

Each field retains its captured position, creation and expiry times. Ramp
fractions apply piecewise over absolute field age at the declared interval.
For each recipient, each source tick integrates the strongest matching field's
DPS across its interval. Integration splits at creation, expiry and ramp
boundaries. Fields from the same source cannot increase the source's maximum
damage rate. Independent source damage still adds. Target membership and shared
protection are evaluated at the settlement boundary. A final partial tick ends
at final field expiry, rather than granting a full interval beyond expiry.

The source clock is anchored at the first impact and stays alive while any
launched field survives. Later impacts do not reset the clock. Carrier death
does not destroy fields or their clocks. Fields and clocks are removed after
their final settlement; inert expired fields never produce continuation facts.
Damage still goes through `record_damage` and the existing shared health batch.
Trace events expose `flame_interval: {start, end}`; `time_seconds` remains the
current settlement time, including a caller's explicit catch-up boundary.

Fresh synthetic controls use genuine compiled Flinger launch/impact events:

- Staggered offsets `[0, 0.1, 0.2]`: 80 damage in `(1, 2]`; 176 total over the
  2.2-second union of three constant-80-DPS fields.
- Aligned offsets `[0, 0.5, 1]`: 80 in `(1, 2]`; 240 total over their three-second
  union. Equal total across these controls would incorrectly erase the longer
  field coverage of the aligned case.
- Kill at 0.21, after all three launches: staggered field total stays 176.
- Kill at 0.01, before the second/third launches: those two intents cancel;
  the one launched field emits 160 over its two-second lifetime.
- Ramp fractions `[0.5, 1]`: strongest-source integral is 156. Protected
  recipients receive zero returned damage, despite persistent fields.

These are component receipts with synthetic geometry and exact domain
boundaries, not completed full battles or game observations.

## Required lead binding for continuation

`ExtendedSiegeCombat.pending` is an opaque scheduling queue. Its packet variants
do not all represent released damage:

| Variant | Meaning | Source loss |
| --- | --- | --- |
| `flinger_shot` | Cancellable future launch intent; no released damage receipt | Cancels if dead/frozen when due |
| `flinger_impact` | Released fixed-position impact | Survives carrier loss |
| `log_contact` | Released log contact | Survives carrier loss |
| `drill_hit` | Surface weapon packet | Existing explicit packet policy |

Do not add `source_team`/`amount` to every launch intent merely to satisfy the
legacy generic queue scanner. That would blur the distinction between a future
launch and released offense. Domain `continuation_reasons(time)` supplies typed
`continuation_fact` objects, with ownership from the actual source actor and
variant-specific eligibility. It reports source flame clocks, rather than one
continuation per staggered field. Death removes cancellable future launches from
these facts but preserves released impacts/fields.

The integration lead owns the narrow shared change in `battle_continuation.py`:
prefer `siege.continuation_reasons(time)` when the runtime exposes that provider;
otherwise retain legacy `siege_continuation(siege)` for the original carrier
runtime. Pass the real settled time from `runtime_continuation_reasons`, after
damage/death/source-loss transitions. Do not scan `pending` in addition to the
provider, which would duplicate facts and still encounter variant schema errors.
Keep the separately owned attacking CC continuation provider unchanged.

This shared binding is **not applied in the domain delta**. The independent
review exposed the legacy `KeyError`; focused tests validate the real domain
provider facts from genuine queued launch intents. The shared incompatibility
remains an integration blocker until the lead's consumer change is independently
verified. Integration acceptance must assert that the shared collector returns
those provider facts.

The Apprentice Warden/Blimp aura exclusion remains lead-owned. New-family
adapter/loader/generated-resource wiring remains unaccepted at the reviewed
checkpoint. Balloon and Baby Dragon already have recipe capabilities; the
remaining siege dependency is real generated-child compilation, policy and
ownership binding. Ordinary Wall Breaker remains a troop-worker dependency.
