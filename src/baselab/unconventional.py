"""Unconventional base generators, so the search also tries designs the
compartment generators (archetypes.py) never make:

- ``cram``:    every building packed tight around the centre, walls as single
               scattered pieces that enclose nothing (an open base).
- ``onion``:   the same cram with the walls as rings hugging the core.
- ``scatter``: buildings spread over the whole village, walls scattered.

The building, trap and wall counts come from an archetypes.design() base, so
every result is a complete legal TH16 layout. Within each style the order is
randomised (Town Hall, Clan Castle and key defenses usually first, i.e.
innermost), so no two designs are alike.
"""

from __future__ import annotations

import math
import random

from .archetypes import design
from .layout import Layout
from .mechanics import VILLAGE

KEY_DEF = {"th", "cc", "eagle", "inferno", "scatter", "xbow", "mono", "ric", "mat", "crafting", "st"}
DEF = KEY_DEF | {"ad", "wt", "bt", "mortar", "at", "cannon", "sweeper", "tesla"}
STYLES = ("cram", "onion", "scatter")


def _free(occ, x, y, s):
    return all(0 <= x + i < VILLAGE and 0 <= y + j < VILLAGE and (x + i, y + j) not in occ for i in range(s) for j in range(s))


def _take(occ, x, y, s):
    for i in range(s):
        for j in range(s):
            occ.add((x + i, y + j))


def unconventional(style: str, seed: int, town_hall: int = 16) -> Layout:
    rng = random.Random(seed)
    base = design(rng.choice(["organic", "free", "wide"]), seed, town_hall=town_hall)
    lay = Layout(f"u-{style}-{seed}", town_hall=town_hall)
    lay.cc_troops = list(base.cc_troops)
    lay.levels, lay.wall_level, lay.hero_levels = base.levels, base.wall_level, base.hero_levels
    blds = list(base.buildings)
    # inner order: key defenses (with TH and CC), other defenses, the rest;
    # shuffled inside each tier, and sometimes a piece jumps a tier
    tiers = [((0 if b.key in KEY_DEF else 1 if b.key in DEF else 2) - (rng.random() < 0.15) + (rng.random() < 0.15), rng.random()) for b in blds]
    blds = [b for _, b in sorted(zip(tiers, blds), key=lambda tb: tb[0])]
    occ: set = set()
    c = VILLAGE / 2
    cells = [(x, y) for x in range(VILLAGE) for y in range(VILLAGE)]
    if style == "scatter":
        gap = 1
        for b in blds:
            for _ in range(400):
                x, y = rng.randrange(1, VILLAGE - b.size - 1), rng.randrange(1, VILLAGE - b.size - 1)
                if _free(occ, x - gap, y - gap, b.size + 2 * gap) or _free(occ, x, y, b.size):
                    break
            else:
                raise RuntimeError("scatter: no room")
            _take(occ, x, y, b.size)
            b.x, b.y = x, y
    else:
        # spiral packing: each building at the free spot nearest the centre
        # (jittered, a 0-tile or 1-tile gap so ground troops can still walk)
        jit = {t: math.hypot(t[0] + 0.5 - c, t[1] + 0.5 - c) + rng.uniform(0, 1.5) for t in cells}
        order = sorted(cells, key=jit.get)
        gap = rng.choice([0, 0, 1])
        for b in blds:
            s = b.size
            for g in sorted({gap, 0}, reverse=True):
                spot = next(((x, y) for (x, y) in order
                             if (_free(occ, x - g, y - g, s + 2 * g) if g else _free(occ, x, y, s))), None)
                if spot:
                    break
            if spot is None:
                raise RuntimeError("cram: no room")
            x, y = spot
            _take(occ, x, y, s)
            b.x, b.y = x, y
    lay.buildings = blds
    n_walls = len(base.walls)
    walls: set = set()
    if style == "onion":
        # rings around the packed core, innermost first
        ring = set(occ)
        while len(walls) < n_walls:
            nxt = {(x + dx, y + dy) for (x, y) in ring for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
            nxt = {t for t in nxt if 0 <= t[0] < VILLAGE and 0 <= t[1] < VILLAGE and t not in occ and t not in walls}
            if not nxt:
                break
            for t in sorted(nxt, key=lambda t: rng.random()):
                if len(walls) >= n_walls:
                    break
                walls.add(t)
            ring = ring | nxt
            # leave a one-tile corridor between rings
            pad = {(x + dx, y + dy) for (x, y) in nxt for dx in (-1, 0, 1) for dy in (-1, 0, 1)} - occ - walls
            ring |= pad
    else:
        # dashes: straight pieces of up to 5 walls on every other row (or
        # column), one tile apart along the row, so no two pieces touch and
        # nothing is enclosed. Outer rows first, so walls sit away from the
        # core and act only as obstacles and decoys.
        first = rng.random() < 0.5
        for horiz, phase in ((first, 0), (first, 1), (not first, 0), (not first, 1)):
            if len(walls) >= n_walls:
                break
            walls = set()
            _dashes(walls, occ, horiz, phase, n_walls, c, rng)
        if len(walls) < n_walls:
            raise RuntimeError("no room for all walls")
    lay.walls = walls
    return _traps(lay, base, occ, walls, cells, c, rng)


def _dashes(walls, occ, horiz, phase, n_walls, c, rng):
        rows = sorted(range(phase, VILLAGE, 2), key=lambda r: -abs(r + 0.5 - c) + rng.uniform(0, 4))
        for r in rows:
            run = []
            for k in range(VILLAGE + 1):
                t = (k, r) if horiz else (r, k)
                ok = k < VILLAGE and t not in occ and len(walls) + len(run) < n_walls
                if ok and len(run) < 5:
                    run.append(t)
                    continue
                if len(run) >= 2:
                    walls.update(run)
                run = []
            if len(walls) >= n_walls:
                break


def _traps(lay, base, occ, walls, cells, c, rng):
    taken = occ | walls
    traps = []
    for t in base.traps:
        near = sorted((p for p in cells if _free(taken, p[0], p[1], t.size)),
                      key=lambda p: math.hypot(p[0] - c, p[1] - c) + rng.uniform(0, 10))
        if not near:
            raise RuntimeError("no room for traps")
        x, y = near[0]
        _take(taken, x, y, t.size)
        t.x, t.y = x, y
        traps.append(t)
    lay.traps = traps
    return lay
