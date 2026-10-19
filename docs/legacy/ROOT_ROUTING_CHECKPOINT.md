# Bounded routing work and relevant range events

Base: 155475a19a7f0b5fbc7854909db59b0a17767c8c. Root throughput remains a separate
acceptance gate from family coverage and game fidelity. The original private four
input blobs are unchanged and excluded from Git. No watchdog, diagnostic dump
thread, crash retry, system change, or timeout inflation is part of this patch.

A bounded cProfile run of the exact Root input reached the same 10.047605962359132
simulation frontier through159 boundaries. Baseline internal CPU time was27.017s:
1,294 ordinary ground searches consumed5.055s, and270 wall-cost searches consumed
1.826s. The geometry-only patch reduced those costs to1.903s and1.142s respectively,
with total profiled time21.978s, about19% lower. These are one paired prefix
measurement on this host, not a full-battle throughput result or statistical claim.

Ground routes now obtain a pure geometry map of cells that can reach the target.
Every stored terminal point uses the existing exact point calculation. Nonterminal
center-only routes preserve their old inclusive range rule. Search order, route
costs, live wall HP, damage/rate/speed modifiers and obstruction checks are unchanged.
Moving targets and changed ranges/footprints use different keys. The cache contains
at most256 maps, each at most4,096 candidate cells; larger geometry falls back to
the original per-cell calculation. Jump forced-exit searches retain their own path.

The shared range scheduler also omits an unrelated entry only for an ordinary
single-target weapon with a live retained primary. A conservative bound using both
actors' maximum possible travel proves that the primary stays within both minimum
and maximum range until the already scheduled next event. Thus the entrant cannot
change acquisition or launch before that event. Missing acquisition, possible range
exit, all secondary model owners and multi/area weapons keep the original query.
No event time is rounded, coalesced or skipped because it is small.

Five focused checks cover exact terminal/center geometry over varied seams,
footprints, zero/nonzero reach and board edges; fallback/memory bounds; direct vs
indexed full wall battles with live wall HP, Freeze and both breach policies; a
paid TH16 Root/P.E.K.K.A breach with identical resources, receipts, clocks and
computed Hall outcome at.017/.25; and a paired retained-weapon battle that removes
the irrelevant t1.75 contact while preserving every shot and final state. Negative
controls retain events for an unacquired weapon, outgoing primary, minimum range,
secondary selector and multitarget pattern. Existing Healer/pet/Valkyrie/wall and
first-contact controls remain required.

The fresh full Root attempt uses the existing150s outer serial process guard and
a120s orderly observation stop, writes run-bound input/source hashes, and creates
a result artifact only after the full simulation returns. A partial observation
has no battle outcome and cannot be used for army/base scoring. Exact evidence is
recorded in the external checkpoint manifest once verification completes.

The first full attempt stopped orderly with no outcome after120.061s at simulation
time18.474623688974813 through888 boundaries. It passed simulation18 at61.533s,
but event density then increased sharply. The full recipe throughput gate remains
open; this checkpoint is a measured acceleration and relevant-contact correction,
not Root completion. A follow-up observation must identify the post18 event owner
before another performance change or full outcome attempt.

Unverified catalog and experimental mechanics are unchanged. This patch does not
repair unrelated family admission or certify the game's targeting/path rules.
Independent review is pending. Complete held-out game calibration remains zero.
