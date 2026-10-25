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


def tile_neighbors(x, y):
    # data/wiki/text/Wall_Home_Village.txt:30: diagonal wall gaps are passable.
    # https://clashofclans.fandom.com/wiki/Wall/Home_Village
    for dx, dy in (
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
    ):
        yield x + dx, y + dy


def flood_tiles(seeds, legal, *, corner_blocked=None):
    """Reach legal tiles using the navigation's eight-way wall connectivity."""
    seen = set(seeds) & legal
    q = deque(sorted(seen))
    while q:
        x, y = q.popleft()
        for tile in tile_neighbors(x, y):
            if (
                corner_blocked is not None
                and tile[0] != x
                and tile[1] != y
                and ((x, tile[1]) in corner_blocked or (tile[0], y) in corner_blocked)
            ):
                continue
            if tile in legal and tile not in seen:
                seen.add(tile)
                q.append(tile)
    return seen


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
    return {
        (x, y) for x in range(VILLAGE) for y in range(VILLAGE) if (x, y) not in blocked
    }


def outside(layout: Layout) -> set:
    """Village tiles a ground unit reaches from the map edge without
    crossing a wall (buildings are walked around)."""
    legal = {(x, y) for x in range(VILLAGE) for y in range(VILLAGE)} - layout.walls
    seeds = {t for t in legal if t[0] in (0, VILLAGE - 1) or t[1] in (0, VILLAGE - 1)}
    return flood_tiles(seeds, legal)


def inside_holes(layout: Layout) -> list[set]:
    """Drop pockets: deployable tiles that are not connected (through other
    deployable tiles, 8-way) to the deployable strip around the map, grouped
    into connected holes. Covers gaps enclosed by walls and open gaps between
    buildings alike; attackers drop troops into both."""
    blocked = blocked_tiles(layout)
    lo, hi = -MARGIN, VILLAGE + MARGIN
    legal = {
        (x, y) for x in range(lo, hi) for y in range(lo, hi) if (x, y) not in blocked
    }
    seeds = {t for t in legal if t[0] in (lo, hi - 1) or t[1] in (lo, hi - 1)}
    seen = flood_tiles(seeds, legal)
    holes = []
    left = legal - seen
    while left:
        group = flood_tiles([min(left)], left)
        left -= group
        holes.append(group)
    return sorted(holes, key=len, reverse=True)
