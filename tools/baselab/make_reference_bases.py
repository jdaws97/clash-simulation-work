"""Build calibration reference bases from real human-designed TH16 layouts.

Sources are the distinct memory-recovered layout slots (see
import_memory_layouts.py). Each slot is missing the same few objects (two
Infernos, a Mortar, a Drill, the Spell Factory, one Skeleton Trap, the hero
banners), most likely because they were mid-upgrade when memory was read.
Missing objects are imputed into free spots - defenses near the Town Hall,
everything else anywhere - and every imputation is listed in the layout notes.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.layout import Layout, Placement, TrapPlacement  # noqa: E402
from baselab.mechanics import BUILDING_TYPES, TRAP_COUNTS, VILLAGE  # noqa: E402
from baselab.render import render  # noqa: E402

SLOTS = ["l1x", "l3x", "l4x", "l5x", "l6x"]


def impute(lay: Layout, rng: random.Random) -> list[str]:
    occ = lay.occupancy()
    th = next(b for b in lay.buildings if b.key == "th")
    cx, cy = th.x + 2, th.y + 2
    notes = []

    def free_spots(size, near=None):
        spots = []
        for x in range(VILLAGE - size + 1):
            for y in range(VILLAGE - size + 1):
                if all((x + dx, y + dy) not in occ for dx in range(size) for dy in range(size)):
                    d = math.hypot(x + size / 2 - cx, y + size / 2 - cy) if near else rng.random()
                    spots.append((d, x, y))
        spots.sort()
        return spots

    counts = {}
    for b in lay.buildings:
        counts[b.key] = counts.get(b.key, 0) + 1
    for key, bt in BUILDING_TYPES.items():
        for _ in range(bt.count - counts.get(key, 0)):
            near = bt.kind in ("defense",) or key == "banner"
            spots = free_spots(bt.size, near=near)
            if not spots:
                continue
            pick = spots[min(len(spots) - 1, rng.randrange(0, 6))] if near else spots[0]
            _, x, y = pick
            mode = "single" if key == "inferno" else None
            lay.buildings.append(Placement(key, x, y, mode))
            for dx in range(bt.size):
                for dy in range(bt.size):
                    occ[(x + dx, y + dy)] = key
            notes.append(f"imputed {key} at {x},{y}")
    tcounts = {}
    for t in lay.traps:
        tcounts[t.key] = tcounts.get(t.key, 0) + 1
    for key, n in TRAP_COUNTS.items():
        for _ in range(n - tcounts.get(key, 0)):
            spots = free_spots(2 if key == "giant" else 1, near=True)
            _, x, y = spots[rng.randrange(0, min(20, len(spots)))]
            lay.traps.append(TrapPlacement(key, x, y, "ground" if key == "skeleton" else None))
            occ[(x, y)] = key
            notes.append(f"imputed trap {key} at {x},{y}")
    return notes


def main():
    out = ROOT / "data" / "reference-bases"
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(16)
    for slot in SLOTS:
        lay = Layout.load(ROOT / "output" / "memory-layouts" / f"memory-{slot}.json")
        for b in lay.buildings:
            if b.key == "inferno" and b.mode is None:
                b.mode = "single"
            if b.key == "xbow" and b.mode is None:
                b.mode = "both"
            if b.key == "st" and b.mode is None:
                b.mode = "invis"
        notes = impute(lay, rng)
        lay.name = f"real-{slot}"
        lay.notes = "Real human-designed layout (memory slot, unverified freshness). " + "; ".join(notes)
        problems = lay.problems()
        lay.save(out / f"real-{slot}.json")
        render(lay, out / f"real-{slot}.png", title=lay.name)
        print(slot, "problems:", problems, "| imputed:", len(notes))


if __name__ == "__main__":
    main()
