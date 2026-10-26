> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Shared paid spell lifecycle checkpoint

This follows the frozen Ice/Jump checkpoint
`03033db5cc6c58f49ce9e28d3f9ad0f5e269de1a`. All seven permanent spell families now
have paid v29 bindings within the explicit limits below. Task-17 independently
conditionally cleared the bounded original paths except S1 (Queen/Mirror Ice/Angry
admission). The subsequent [Mirror repair](MIRROR_SPELL_REPAIR.md) is separately
implemented and awaiting the same reviewer. This is synthetic software acceptance, not complete game coverage.
There is zero complete held-out game calibration. Quantities remain from the
unverified catalog pinned to `chiefpansancolt/clash-of-clans-data` commit
`c6967314d7281bb87c362993e2635e58cd77b351`.

Clone reserves are compiled from original declarations or fresh spell-generated
templates. They have finite spell/source/index ownership, a shared housing budget,
fresh HP and weapon state, and no paid army, spell, ability or CC entitlement.
The raw entry point validates their declaration against their source and rejects
forged damage or unknown secondary lifecycles. Released clones survive source
loss; their absolute lifetime also expires while Recall-held. Silent expiry
retains Recall's group ownership until its scheduled return, excludes expired
members from return, and preserves any earlier actual death timestamp.
Complex summons, aura, morph, split, equipment-child and carrier-owned clones
remain explicitly unsupported rather than copied as ordinary units.

Revive restores the same defeated hero at the pinned health fraction. It retains
unfinished main/wall attack work, shared ability spend, equipment charges, and
absolute status clocks. It does not revive pets or reset Phoenix state. An
unsettled Phoenix temporary life rejects. Core Royal Champion, Archer Queen and
Grand Warden loadouts are bound only with the existing Rocket Spear, Electro
Boots, Invisibility Vial, Magic Mirror, Eternal Tome and Healing Tome contracts,
or their permitted bare controls. Other hero/equipment/secondary models reject.
Electro Boots skip pulses while dead using the same absolute grid as Recall;
revival cannot replay missed pulses. Broader pet/revival compositions still need
independent acceptance and are not inferred from the core fixture.

Ice now admits those same core hero loadouts in addition to ordinary troops.
Weapon and movement work pauses; the supported core passives retain their declared
absolute-clock behavior. Angry uses the shared selector and movement composition,
preserves its expiry through Recall, and restores the original priorities. Its
recipients must have a bound ordinary/core-hero lifecycle and a weapon capable of
targeting defenses. Other targeting owners reject. The complete shared binding
adds a named `shared_lifecycles` policy and updates `ice_lifecycles`; existing
inputs must explicitly select these contracts. The domain's audited
`same_time_settlement` and `clock_rounding` fields remain mandatory.

Four additional bounded tests establish the shared behavior:

- Same-time paid Bat/Clone with both cast-ID orders: source production precedes
  Clone's finite closure, the original paid army dies, cloned Bats use ordinary
  weapons and the explicit synthetic Hall factor, capacity exhausts once, and
  exactly two spell slots are spent at steps 0.017 and 0.25.
- Paid ordinary Minion cloning: original source death, eleven finite clones,
  Recall-held lifetime expiry at t=30, exhausted-army termination, no fresh
  paid deployment, and raw forged-stat rejection. An independent paid reserve
  also exercises the scheduled Recall return after the held clones expired.
- Paid Revive with a defeated Royal Champion, spent Rocket Spear ability, Ice
  captured on the revival boundary, and a paid Freeze suppressing the defender.
  The same hero resumes its unfinished shot at t=9.2; missed Electro Boots pulses
  are skipped and exactly three spell slots are spent. Duplicate paid hero
  activation remains illegal. Both solver steps exercise actual shared HP.
- Paid Angry and Recall return before/after the retained expiry: the movement
  bonus and defense preference return only while still live, real attacks select
  the expected defense/building, and the original army and two spell slots remain
  the only paid resources. Both solver steps agree on these decisions.

These explicit hypotheses do not settle secondary-lifecycle semantics, current
game statistics, six source-gap equipment/pet items, the remaining domain
integrations, TH16 Root Rider throughput, or army/base performance rankings.

Magic Mirror children now require the explicit mirror_children policy for Ice
or Angry. Their finite owner roster, fresh template, status membership and absolute
lifetime are checked; unrelated equipment summons remain outside this admission.
