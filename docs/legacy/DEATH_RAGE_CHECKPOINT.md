# Super Valkyrie shared death Rage

Attacking Super Valkyrie is bound in the explicit v27+ attacking extension scope.
Its HP, damage, movement, range and interval use the selected pinned catalog row.
Source-centered swings and ordinary ground/wall placement reuse ValkyrieRouting
and PatternCombat. Its distinct super-troop identity and paid housing remain
unchanged; no ordinary Valkyrie identity is substituted in resources.

Complete `death_buff_parameters` remain mandatory and explicitly experimental:
relative field geometry, duration, damage/movement/healing bonuses, class scaling,
membership, stacking, protection, source persistence and release delay. No Rage
spell level or current game quantities are inferred. Missing scope, malformed
models, another actor's model, paid-spell metadata and generated-field ID
collisions reject. Raw scenes require the same compiled identity, scope,
placement and matching model declaration, then revalidate the complete field.

Actual HP death queues one owned fixed field. Nondeath Recall does not trigger
it; the original actor may return and later die normally. Positive release delays
are retained even below the spatial tolerance, rounding up one representable
instant if addition would otherwise lose the delay. Death release settles after
the killing health batch. It cannot retroactively strengthen hits already
launched in that batch. Shared BuffCombat owns subsequent eligibility,
entry/exit, strongest-axis overlap and expiry. Its inherited field membership
and expiry spatial tolerance is unchanged by this integration.

Released effects appear separately under `resource_use.generated_troop_effects`
with owner, generated origin and release time. They never spend or create a paid
spell slot. Pending or active beneficial fields do not keep an otherwise
exhausted attacking force alive. A meaningful paid reserve can keep the battle
alive until the delayed field releases. Pending fields are exposed in the combat
result when termination precedes release.

Two paid vertical tests at steps 0.017 and 0.25 cross: simultaneous attack and
death, exact delayed release (including 5e-11 seconds), actual doubled shared
weapon damage followed by unboosted damage after expiry, finite paid housing and
an untouched Rage slot; Recall pickup/return, actual later death, delayed release
versus exhausted-force termination, a later paid deployment, and raw/scope
rejection. Existing domain and Valkyrie controls remain required.

Limitations: catalog snapshot c6967314d7281bb87c362993e2635e58cd77b351 is unverified;
field quantities/placement are caller-supplied hypotheses. Defensive Super
Valkyrie is not bound. Secondary lifecycle combinations with Clone, Ice Block or
Angry remain explicitly rejected by those owners. No held-out complete game
calibration or independent acceptance is claimed.
