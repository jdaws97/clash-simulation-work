"""Baselab: a fast Clash of Clans battle simulator and base-layout optimizer.

Baselab trades the legacy ``clashlab`` engine's exhaustive mechanics contracts
for speed: a full 3-minute battle runs in well under a second, so thousands of
attacks can be simulated per candidate layout during optimization.

Statistics come from ClashKing's game-file extraction (``data/clashking-static-
data.json``). Behaviour that the game files do not describe (targeting rules,
spell AI, trap triggering details) lives in ``mechanics.py`` with a note on
where each value came from and how confident we are in it.
"""
