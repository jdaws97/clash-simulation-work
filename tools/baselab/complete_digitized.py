"""Complete a digitized screenshot base for simulation.

Hidden Teslas and traps are invisible in layout screenshots. The five
Teslas go on free 2x2 spots inside the walls, spread out (farthest-point
order starting nearest the Town Hall). Overlaps are resolved, traps are
placed by the generator heuristics, walls are topped up to the inventory
and the user's levels are applied (tools/baselab/finish_digitized.py).
Every assumption is written to the layout notes.

Usage: python tools/baselab/complete_digitized.py IN.json OUT.json
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.deploy import outside  # noqa: E402
from baselab.layout import Layout, Placement  # noqa: E402
from baselab.mechanics import INVENTORY, VILLAGE  # noqa: E402


def add_teslas(lay: Layout) -> list:
    have = sum(1 for b in lay.buildings if b.key == "tesla")
    need = INVENTORY[lay.town_hall].get("tesla", 0) - have
    if need <= 0:
        return []
    out_region = outside(lay)
    taken = set(lay.walls)
    for b in lay.buildings:
        taken |= {(b.x + i, b.y + j) for i in range(b.size) for j in range(b.size)}
    spots = []
    for x in range(VILLAGE - 1):
        for y in range(VILLAGE - 1):
            tiles = {(x + i, y + j) for i in range(2) for j in range(2)}
            if tiles & taken or tiles & out_region:
                continue
            spots.append((x, y))
    th = next(b for b in lay.buildings if b.key == "th")
    cx, cy = th.x + th.size / 2, th.y + th.size / 2
    placed = []
    for _ in range(need):
        free = [s for s in spots if not any(abs(s[0] - p[0]) < 2 and abs(s[1] - p[1]) < 2 for p in placed)]
        if not free:
            break
        if not placed:
            pick = min(free, key=lambda s: math.hypot(s[0] + 1 - cx, s[1] + 1 - cy))
        else:
            pick = max(free, key=lambda s: min(math.hypot(s[0] - p[0], s[1] - p[1]) for p in placed))
        placed.append(pick)
    for x, y in placed:
        lay.buildings.append(Placement("tesla", x, y))
    return placed


def main(src: str, dst: str):
    lay = Layout.load(Path(src))
    lay.town_hall = lay.town_hall or 16
    if isinstance(lay.notes, list):  # the Codex digitizers wrote a list of notes
        lay.notes = " ".join(str(n) for n in lay.notes)
    placed = add_teslas(lay)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    lay.save(Path(dst))
    from finish_digitized import main as finish

    finish(dst)
    lay = Layout.load(Path(dst))
    note = (
        f" Hidden Teslas not visible in the screenshot: {len(placed)} placed inside the walls "
        f"at {placed} (assumed)."
    )
    lay.notes = (str(lay.notes or "") + note).strip()
    lay.save(Path(dst))
    print(dst, "teslas", placed, "problems", lay.problems())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
