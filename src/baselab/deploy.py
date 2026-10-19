"""Where an attacker can drop troops on a Home Village layout.

Wiki (Walls): every structure has a one-tile perimeter where troops cannot be
spawned, so any gap wider than two tiles can be deployed into. Walls push the
no-spawn zone like buildings (wiki: Builder's Hut). Hidden Teslas and traps do
not create a no-spawn zone (wiki: Hidden Tesla).

Coordinates are village tiles (0..43); the 3-tile margin around the village is
always deployable.
"""

from __future__ import annotations

from collections import deque

from .layout import Layout
from .mechanics import MARGIN, VILLAGE

NO_ZONE_KEYS = {"tesla"}


def blocked_tiles(layout: Layout) -> set:
    occ = set()
    for p in layout.buildings:
        if p.key in NO_ZONE_KEYS:
            continue
        occ.update(p.tiles())
    occ.update(layout.walls)
    out = set()
    for tx, ty in occ:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                out.add((tx + dx, ty + dy))
    return out


def deployable(layout: Layout) -> set:
    blocked = blocked_tiles(layout)
    return {(x, y) for x in range(VILLAGE) for y in range(VILLAGE) if (x, y) not in blocked}


def outside(layout: Layout) -> set:
    """Village tiles a ground unit reaches from the map edge without
    crossing a wall (buildings are walked around)."""
    walls = set(layout.walls)
    seen = set()
    q = deque()
    for i in range(VILLAGE):
        for t in ((i, 0), (i, VILLAGE - 1), (0, i), (VILLAGE - 1, i)):
            if t not in walls and t not in seen:
                seen.add(t)
                q.append(t)
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if 0 <= n[0] < VILLAGE and 0 <= n[1] < VILLAGE and n not in walls and n not in seen:
                seen.add(n)
                q.append(n)
    return seen


def inside_holes(layout: Layout) -> list[set]:
    """Drop pockets: deployable tiles that are not connected (through other
    deployable tiles, 4-way) to the deployable strip around the map, grouped
    into connected holes. Covers gaps enclosed by walls and open gaps between
    buildings alike; attackers drop troops into both."""
    blocked = blocked_tiles(layout)
    lo, hi = -MARGIN, VILLAGE + MARGIN
    legal = {(x, y) for x in range(lo, hi) for y in range(lo, hi) if (x, y) not in blocked}
    q = deque(t for t in legal if t[0] in (lo, hi - 1) or t[1] in (lo, hi - 1))
    seen = set(q)
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n in legal and n not in seen:
                seen.add(n)
                q.append(n)
    holes = []
    left = legal - seen
    while left:
        start = left.pop()
        group = {start}
        q = deque([start])
        while q:
            x, y = q.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if n in left:
                    left.discard(n)
                    group.add(n)
                    q.append(n)
        holes.append(group)
    return sorted(holes, key=len, reverse=True)
