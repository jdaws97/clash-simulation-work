# Central audit corrections awaiting independent recheck

This delta follows frozen stage2 tree
`5f849ef556535fa4dcf50d3fdfd6684dca6b712d`. It is synthetic software evidence,
not current-game calibration or whole-family acceptance. The separate stage1
composition fix remains frozen at commit `873b79c7fab2ed1ff53a682a872893bc93505cd5`.

- Titan Recall retains its absolute aura epoch and discards withdrawn pulses.
  The independently reviewed exact pulse comparisons are composed with that
  change, and the shared solver now retains positive sub-epsilon Titan deadlines.
  Nonadvancing or overflowing aura additions reject. Recall at initial deployment,
  return on a pulse, Freeze and skipped active clocks have focused contracts.
- Jelly preserves the explicit defending-unit tier during its defense override,
  then restores all original priority fields. Collateral policy remains separate.
- Apprentice Warden checks the shared siege eligibility gate for aura membership.
  An actual compiled Blimp retains its HP while an ordinary troop gains the aura.
- Raw unbound attacking lifecycle models reject at shared kernel entry. This
  closes the audit's Golem death-without-children false success. It does not
  establish generated troop, Druid, Meteor or Ruin full-battle integration.
- Optional Inferno fuel is compiled only in the explicit advanced-defense scope
  and consumed by one owner after shared beam selection. Zero fuel blocks beams;
  per-beam and per-pulse hypotheses consume their declared quantities. Depletion
  clears acquisition. Existing unlimited behavior remains when no fuel contract
  is selected. This is not evidence for an actual game fuel count.
- Logger availability and compiler rejection now agree about its missing shared
  projectile/pushback/continuation bindings. The component is still unbound.
- Frames retain the maximum HP at their own timestamp. Life Gem changes also
  emit an HP/max-HP event. Replay packing retains that denominator and rendering
  uses it, preventing 4084.8/4200 from being rendered as 4084.8/3000. A source-loss
  kernel disturbance confirms older boosted frames remain unchanged after max HP
  returns to base. Legacy frames without this field keep their existing base-HP
  fallback; previously omitted dynamic history cannot be recovered from final HP.

## Reviewed domain deltas and migration

Troop correction `f9d05234` supplies exact aura timing and a supported Ruin Knight
wall-route contract. Its aura hunk is merged with the separate Recall fix; that
composition and the central scheduler change still need independent recheck.

Spell correction `cdf75fd841585a6748e71bfdfb9936f3645ecf52` requires two policy
fields in every saved advanced-spell parameter dictionary:

- `same_time_settlement`: `all_due_releases_and_revivals_then_clone_closure_then_field_membership`
- `clock_rounding`: `positive_delay_rounds_up_when_sum_does_not_advance`

Older dictionaries must be explicitly migrated; validation supplies no defaults.
No checked-in serialized advanced-spell dictionaries were found beyond the
explicit test factory. At the original stage3 checkpoint the seven full-battle
families remained unbound; their domain recheck did not establish paid battle
acceptance. Current stage4 status is tracked in `STAGE4_CLOSURE.md`.

Equipment correction `106cae153a7433c4b8fc4f40d8e083b1fe4d2a12` changes
`finite_inventory` from a tuple-keyed mapping to a list of owner/equipment records,
including the empty value `{}` to `[]`. The accompanying
`finite_inventory_schema=owner_equipment_records_v1` identifies the format.
Consumers should index records by `owner_id` and `equipment_id`; never split a
concatenated identifier. Repository consumers are compatible; external consumers
were not inspected. Independent review established the original Archer Puppet
CLI export now succeeds; broader generated-child battle fidelity remains open.

The original stage3 snapshot left Shield/Hall initial activation and Flinger
overlap open. Subsequent fixes at `59664f99` and `da093e6e` respectively now have
original-reviewer bounded acceptance. A release event alone must still not be
counted as a launched packet. Their scope and remaining limits are recorded in
`STAGE3_AUDIT_FIXES.md`, `FLINGER_SHARED_RECHECK.md` and `STAGE4_CLOSURE.md`.
