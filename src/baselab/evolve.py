"""Population search: crossover between layouts, mutation, diversity.

A child takes everything on one side of a random cut line from parent A
(walls, buildings, traps, modes) and the other side from parent B, then is
repaired into a legal layout: overlaps at the seam are dropped, missing
buildings and traps go back near where a parent had them (defenses inside
the walls, trash outside if there is no room), surplus ones are removed,
and drop holes are plugged. Selection keeps an elite and penalises
near-duplicate wall plans so several design ideas survive at once.
"""

from __future__ import annotations

import math
import random
from collections import Counter

from .deploy import outside
from .generator import top_up_walls
from .layout import Layout, Placement, TrapPlacement
from .mechanics import BUILDING_TYPES, INVENTORY, TRAP_INVENTORY, VILLAGE, WALL_COUNT
from .optimize import _fill_hole, _fits, _occupied, _repair_gears

TRAP_SIZE = {"giant": 2, "giga": 2}


def _side(cx, cy, ang):
    c, s = math.cos(ang), math.sin(ang)
    return lambda x, y: (x - cx) * c + (y - cy) * s >= 0


def _place_near(occ, key, size, prefer, region, rng):
    """Free spot for a size x size footprint nearest `prefer`, inside
    `region` (a tile set) when given."""
    px, py = prefer
    best = None
    for x in range(VILLAGE - size + 1):
        for y in range(VILLAGE - size + 1):
            if not _fits(occ, x, y, size):
                continue
            if region is not None and any((x + i, y + j) not in region for i in range(size) for j in range(size)):
                continue
            d = math.hypot(x - px, y - py) + rng.random() * 0.5
            if best is None or d < best[0]:
                best = (d, x, y)
    return best[1:] if best else None


def crossover(a: Layout, b: Layout, rng: random.Random) -> Layout | None:
    cx, cy = 22 + rng.uniform(-6, 6), 22 + rng.uniform(-6, 6)
    ang = rng.uniform(0, 2 * math.pi)
    side = _side(cx, cy, ang)

    def seam_dist(p):
        return abs((p.x + p.size / 2 - cx) * math.cos(ang) + (p.y + p.size / 2 - cy) * math.sin(ang))
    child = a.copy()
    child.name = "child"
    child.walls = {t for t in a.walls if side(t[0] + 0.5, t[1] + 0.5)} | {t for t in b.walls if not side(t[0] + 0.5, t[1] + 0.5)}
    taken: set = set()
    picked = []

    def take(p, src):
        tiles = set(p.tiles())
        if tiles & taken:
            return
        taken.update(tiles)
        picked.append((p, src))

    # A's side first so A wins seam conflicts; the Town Hall from the side its centre is on
    for p in a.buildings:
        if side(p.x + p.size / 2, p.y + p.size / 2):
            take(Placement(p.key, p.x, p.y, p.mode), "a")
    for p in b.buildings:
        if not side(p.x + p.size / 2, p.y + p.size / 2):
            take(Placement(p.key, p.x, p.y, p.mode), "b")
    inv = INVENTORY[a.town_hall]
    counts = Counter(p.key for p, _ in picked)
    # surplus: drop the copies nearest the seam (e.g. two Town Halls)
    for key, n in counts.items():
        extra = n - inv.get(key, 0)
        if extra > 0:
            mine = sorted([q for q in picked if q[0].key == key], key=lambda q: seam_dist(q[0]))
            for q in mine[:extra]:
                picked.remove(q)
    child.buildings = [p for p, _ in picked]
    child.walls -= {t for p in child.buildings for t in p.tiles()}
    # missing: put back near a parent's position (prefer the parent whose side it was not taken from)
    counts = Counter(p.key for p in child.buildings)
    out_region = outside(child)
    inside_region = {(x, y) for x in range(VILLAGE) for y in range(VILLAGE)} - out_region - child.walls
    occ = _occupied(child)
    occ |= {t for t in child.walls}
    for key in sorted(inv, key=lambda k: -BUILDING_TYPES[k].size):
        need = inv[key] - counts.get(key, 0)
        if need <= 0:
            continue
        spots = [(p.x, p.y, p.mode) for p in a.buildings + b.buildings if p.key == key]
        rng.shuffle(spots)
        size = BUILDING_TYPES[key].size
        kind = BUILDING_TYPES[key].kind
        for k in range(need):
            sx, sy, mode = spots[k % len(spots)] if spots else (22, 22, None)
            region = inside_region if kind in ("defense", "townhall", "castle") else None
            pos = _place_near(occ, key, size, (sx, sy), region, rng) or _place_near(occ, key, size, (sx, sy), None, rng)
            if pos is None:
                return None
            child.buildings.append(Placement(key, pos[0], pos[1], mode))
            occ.update((pos[0] + i, pos[1] + j) for i in range(size) for j in range(size))
    # traps: same split, then counts repaired
    tr = [TrapPlacement(t.key, t.x, t.y, t.mode) for t in a.traps if side(t.x + 0.5, t.y + 0.5)]
    tr += [TrapPlacement(t.key, t.x, t.y, t.mode) for t in b.traps if not side(t.x + 0.5, t.y + 0.5)]
    occ = set(child.walls)
    for p in child.buildings:
        occ.update(p.tiles())
    child.traps = []
    tcount: Counter = Counter()
    want = TRAP_INVENTORY[a.town_hall]
    for t in tr:
        if tcount[t.key] >= want.get(t.key, 0):
            continue
        tiles = set(t.tiles())
        if tiles & occ:
            continue
        occ |= tiles
        child.traps.append(t)
        tcount[t.key] += 1
    for key, n in want.items():
        spots = [(t.x, t.y, t.mode) for t in a.traps + b.traps if t.key == key]
        size = TRAP_SIZE.get(key, 1)
        for k in range(n - tcount[key]):
            sx, sy, mode = spots[k % len(spots)] if spots else (22, 22, None)
            pos = _place_near(occ, key, size, (sx, sy), None, rng)
            if pos is None:
                return None
            child.traps.append(TrapPlacement(key, pos[0], pos[1], mode))
            occ.update((pos[0] + i, pos[1] + j) for i in range(size) for j in range(size))
    # every wall stays placed: the seam and the buildings dropped on B's
    # walls lose some, so close the seam's one-tile gaps and add the rest
    top_up_walls(child, occ, rng, target=min(WALL_COUNT, max(len(a.walls), len(b.walls))), close_gaps=True)
    # wall budget: trim seam-most walls
    if len(child.walls) > WALL_COUNT:
        ws = sorted(child.walls, key=lambda t: math.hypot(t[0] - cx, t[1] - cy))
        for t in ws[: len(child.walls) - WALL_COUNT]:
            child.walls.discard(t)
    for _ in range(12):
        if not _fill_hole(child, rng):
            break
    # Wiki: Archer Tower, only one gear-up per type; parents may use different copies.
    _repair_gears(child)
    if child.problems():
        return None
    return child


def wall_similarity(a: Layout, b: Layout) -> float:
    if not a.walls or not b.walls:
        return 0.0
    return len(a.walls & b.walls) / len(a.walls | b.walls)
