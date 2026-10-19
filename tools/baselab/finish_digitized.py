"""Finish a digitized layout: resolve overlaps, add standard traps, apply
the user's levels.

Defenses that overlap move to the nearest free spot. Resource and army
buildings that overlap move only to open ground outside the outer walls (so
they never fill a compartment by accident). Traps are invisible in layout
screenshots, so they are placed with the generator's trap heuristics and the
layout notes say so.

Usage: python tools/baselab/finish_digitized.py output/web-bases/web-a.json
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.deploy import inside_holes, outside  # noqa: E402
from baselab.generator import Blueprint, _Board, _place_traps  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.mechanics import BUILDING_TYPES  # noqa: E402


def tiles(b):
    return {(b.x + i, b.y + j) for i in range(b.size) for j in range(b.size)}


def main(f):
    lay = Layout.load(f)
    out_region = outside(lay)
    for _ in range(80):
        occ, bad = {}, None
        for i, b in enumerate(lay.buildings):
            if tiles(b) & set(lay.walls):
                bad = i
                break
            for t in tiles(b):
                if t in occ:
                    bad = i
                    break
                occ[t] = i
            if bad is not None:
                break
        if bad is None:
            break
        b = lay.buildings[bad]
        others = set(lay.walls)
        for k, o in enumerate(lay.buildings):
            if k != bad:
                others |= tiles(o)
        trash = BUILDING_TYPES[b.key].kind not in ("defense", "townhall", "castle")
        best = None
        for dx in range(-44, 45):
            for dy in range(-44, 45):
                x, y = b.x + dx, b.y + dy
                if x < 0 or y < 0 or x + b.size > 44 or y + b.size > 44:
                    continue
                t = {(x + p, y + q) for p in range(b.size) for q in range(b.size)}
                if t & others or (trash and not t <= out_region):
                    continue
                d = math.hypot(dx, dy)
                if best is None or d < best[0]:
                    best = (d, x, y)
        if best is None:
            print("no room, dropped", b.key)
            lay.buildings.pop(bad)
            continue
        print("move", b.key, (b.x, b.y), "->", best[1:])
        b.x, b.y = best[1], best[2]
    board = _Board(lay.walls)
    for b in lay.buildings:
        board.take(b.x, b.y, b.size)
    lay.traps = []
    _place_traps(lay, board, random.Random(7), Blueprint(town_hall=lay.town_hall))
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
    lay.notes = (lay.notes + " Digitized from a screenshot; positions about +-1 tile; traps placed by heuristic (not visible in screenshots); "
                 "built with the user's levels.").strip()
    print("problems", lay.problems())
    print("holes", sum(map(len, inside_holes(lay))))
    lay.save(Path(f))


if __name__ == "__main__":
    main(sys.argv[1])
