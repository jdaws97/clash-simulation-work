> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Healer relative contact checkpoint

This change fixes one numerical pursuit boundary in the declared simulator. It
does not establish current game targeting behavior or clear the full Root Rider
recipe's throughput limitation.

An airborne Healer outside a moving ally's range previously stopped at that
ally's old range edge. Each tiny arrival replanned against the ally's new position
and repeated whole-battle target and route work. The Healer now continues along
the same straight pursuit direction toward the current ally footprint; the
existing piecewise linear range solver clips motion at relative healing-range
contact. Selection, retention, ground routing, stationary targets, healing
amounts, stacking, packet ownership and paid resources retain their contracts.
No timer tolerance, maximum step or runner timeout is widened.

The shared movement phase provides both trajectories after target selection.
Support contributes the first eligible primary range contact, including when a
primary moves into a stationary or frozen Healer's range. Freeze still suppresses
the Healer's movement and launch clock; it does not cancel released packets.
This is a numerical implementation of the existing declared motion conventions,
not an additional source claim about continuous client pursuit.

Two focused vertical tests cover analytic straight pursuit with and without
Freeze at steps 2, 0.31 and 0.017; exact first healing and HP; bounded solver
boundaries rather than machine-speed timing; and a paid five-Healer/P.E.K.K.A
battle at steps 0.25 and 0.017 with 95 paid housing, six deployed identities,
five healing launches, valid primary ownership and a computed time-limit outcome.

The original Root recipe remains private and outside Git. Clean serial probes
used unchanged input/account/army/layout, a 65-second wall budget and an
18-second simulated-prefix ceiling. The baseline reached about 17.081 seconds;
this change reached about 17.222 seconds and removed the observed Healer arrival
cascade. Neither probe returned a complete battle outcome. Other route costs,
pursuit boundaries and the full recipe require further work. Independent review
and complete held-out game calibration remain outstanding.
