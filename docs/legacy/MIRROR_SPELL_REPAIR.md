# S1 paid Queen/Magic Mirror admission repair

Base: 28204a91d6b392c42037edde80fa9cd8d55a215e. Original task-17 finding S1:
core_hero admitted the Queen's Magic Mirror loadout, but the finite predeclared
children carried summon_model and were rejected by Ice/Angry's secondary guard.
Dropping gear was not a valid paid-army workaround. This patch retains both items
and adds a narrow owned-child binding; independent same-reviewer recheck is pending.

New mirror_children policy:
finite_owned_core_queen_children_fresh_membership_absolute_expiry.
It is required only for an Ice/Angry scene with a supported Mirror-equipped Queen.
Existing ordinary/core-hero spell inputs without Mirror retain their former binding
schema. The default current binding dictionary includes the new policy. Other
secondary summons, equipment children, troop morphs and Clone-spell equipment-child
sources remain rejected.

The admission regenerates the finite Mirror templates from the compiled equipped
Queen and requires exact child IDs, count, ownership, selected stats/weapon,
controlled birth and summon geometry/lifetime. Actor-specific defending-unit
response fields remain under the shared response validator. Forged damage, missing
children or invented extra children cannot gain admission by claiming summon_model.
The admitted children use the ordinary shared weapon, movement, protection and
spell-status paths. They receive fresh live field membership rather than copying
parent status. They acquire no paid hero, spell, equipment activation or pet.

Mirror expiry is now an exact absolute frontier even when held by Recall. Expiry
retires a still-living child at its original deadline, leaves Recall ownership for
its later empty return, and preserves any earlier actual death. This correction
also applies to the existing Mirror runtime outside advanced-spell scenes; other
equipment summon lifetime semantics are unchanged.

Three focused tests establish:
- Paid Queen 95, Invisibility Vial 7 and Magic Mirror 20, two released children,
  Ice .2..7.2, ordinary child weapon shots at 0 then 7.75, and real incoming shared
  receipts reduced by .14 only during Ice. One shared hero activation, one spell,
  no extra paid unit; steps .017/.25.
- Paid Angry plus Freeze protecting the Queen until activation at1: children born
  outside Angry attack the nearby storage without inheriting the parent's defense
  priority, survive the owner's actual Hall death, are Recalled shortly before
  their t26 absolute expiry, expire while held, and are excluded from the later
  return. A separately paid reserve keeps that return reachable. Three paid spells,
  one activation, two finite children; both solver steps.
- Same-field Angry children acquire the live status normally; raw forged child
  damage and omission of the new Mirror policy reject. A legacy ordinary Ice input
  without the new key still runs.

Fixture HP/positions are explicit synthetic controls. Catalog remains unverified
c6967314d7281bb87c362993e2635e58cd77b351. These checks do not establish actual client
Mirror/Freeze/status timing, all Queen revival or pet compositions, broader spell
secondary lifecycles, or full-game calibration. Held-out complete calibration: zero.
