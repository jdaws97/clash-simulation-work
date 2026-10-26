> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Giga / Siege Barracks audit correction

This delta addresses task-3's P1 and P2 findings on checkpoint
`9a31421941050ad9958f251b2759e19449ce3acf`. It builds on the separate frozen
paid observation checkpoint and does not modify any frozen review tree.

Giga eligibility and impact now run inside the existing same-time lifecycle
settling loop, after due finite siege/CC and spell children are released. A
newly resolved blast causes another settling iteration, allowing its actual
health changes to cause ordinary death releases without advancing simulation
time. The trap's existing trigger and resolution latches prevent a second
blast. This is an ordering correction within the declared synthetic model;
it adds no measured game timing or damage values.

`barracks_member_model` now belongs to the generated-response marker set.
Every finite Barracks child requires an exact actor response, including future
unreleased children. Ordinary PEKKA/Wizard entity selectors cannot supply the
child's trigger weight, damage multiplier or push multiplier. Explicit zero
child responses remain supported.

Two grouped paid TH16-versus-TH17 regression checks reproduce the auditor's
fixture at maximum steps 0.017 and 0.25 seconds. PEKKA and Wizard release at
0.0, provide explicit weights 25 + 4, and trigger at 0.0. The single delayed
blast and Wizard death occur at 0.2 at both steps. The zero-delay variant
settles one blast and death at 0.0. A zero-response control stays untriggered;
removing all exact child entries or just the last unreleased Wizard rejects.
Paid carrier/CC and generated accounting, real damage, outcome and input
immutability are checked. Existing mixed-roster Giga and paid scheduler cases
also pass the targeted recheck.

Independent recheck by the original auditor is still pending. These tests are
synthetic partial inventories and establish no strategy ranking, current
account facts, Root pursuit result or held-out game calibration.
