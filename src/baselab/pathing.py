"""Ground pathfinding on a half-tile grid.

Each building blocks its combat hitbox (the inner footprint); the outer ring of
its footprint stays walkable, as in the game. Walls are passable at a cost that
stands in for the time spent breaking them. A Dijkstra distance field is
computed per (target, attack range, wall class) and shared by every unit that
heads for that target; fields are rebuilt lazily after a wall falls.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

RES = 2  # grid cells per tile
INF = np.float32(1e9)

_NEIGHBORS = np.array(
    [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)],
    dtype=np.int64,
)
_STEP = np.array([1.0, 1.0, 1.0, 1.0, math.sqrt(2), math.sqrt(2), math.sqrt(2), math.sqrt(2)]) / RES


@njit(cache=True)
def _dijkstra(goal, blocked, wall, wall_extra, neighbors, step):
    n, m = goal.shape
    dist = np.full((n, m), 1e9, dtype=np.float32)
    for i in range(n):
        for j in range(m):
            if goal[i, j] and not blocked[i, j]:
                dist[i, j] = 0.0
    return _relax(dist, goal, blocked, wall, wall_extra, neighbors, step)


@njit(cache=True)
def _relax(dist, seed, blocked, wall, wall_extra, neighbors, step):
    """Dijkstra from every seed cell at its current distance. From the goal
    cells (dist 0) this is the full field; from the cells around a removed
    obstacle it repairs a cached field exactly, since removing a wall or a
    building can only make paths cheaper (decrease-only update)."""
    n, m = dist.shape
    # binary heap stored in parallel arrays
    cap = n * m * 8 + 16
    hk = np.empty(cap, dtype=np.float32)
    hi = np.empty(cap, dtype=np.int64)
    size = 0
    for i in range(n):
        for j in range(m):
            if seed[i, j] and not blocked[i, j] and dist[i, j] < 1e9:
                # push
                k = size
                size += 1
                hk[k] = dist[i, j]
                hi[k] = i * m + j
                while k > 0:
                    p = (k - 1) >> 1
                    if hk[p] <= hk[k]:
                        break
                    hk[p], hk[k] = hk[k], hk[p]
                    hi[p], hi[k] = hi[k], hi[p]
                    k = p
    while size > 0:
        d = hk[0]
        idx = hi[0]
        size -= 1
        hk[0] = hk[size]
        hi[0] = hi[size]
        k = 0
        while True:
            l = 2 * k + 1
            r = l + 1
            s = k
            if l < size and hk[l] < hk[s]:
                s = l
            if r < size and hk[r] < hk[s]:
                s = r
            if s == k:
                break
            hk[s], hk[k] = hk[k], hk[s]
            hi[s], hi[k] = hi[k], hi[s]
            k = s
        ci = idx // m
        cj = idx % m
        if d > dist[ci, cj]:
            continue
        for q in range(8):
            ni = ci + neighbors[q, 0]
            nj = cj + neighbors[q, 1]
            if ni < 0 or nj < 0 or ni >= n or nj >= m:
                continue
            if blocked[ni, nj]:
                continue
            if q >= 4:
                # no corner cutting past blocked cells
                if blocked[ci, nj] or blocked[ni, cj]:
                    continue
            # cost of entering (ci, cj) from (ni, nj): we expand backwards
            cost = step[q]
            if wall[ci, cj]:
                cost += wall_extra
            nd = d + cost
            if nd < dist[ni, nj]:
                dist[ni, nj] = nd
                k = size
                size += 1
                hk[k] = nd
                hi[k] = ni * m + nj
                while k > 0:
                    p = (k - 1) >> 1
                    if hk[p] <= hk[k]:
                        break
                    hk[p], hk[k] = hk[k], hk[p]
                    hi[p], hi[k] = hi[k], hi[p]
                    k = p
    return dist


@njit(cache=True)
def _goal_mask(n, cx, cy, half, reach):
    """Cells whose centre lies within `reach` of the square hitbox."""
    goal = np.zeros((n, n), dtype=np.bool_)
    lo = int(max(0.0, (cx - half - reach - 1.0) * 2))
    hi = int(min(n - 1.0, (cx + half + reach + 1.0) * 2))
    lo2 = int(max(0.0, (cy - half - reach - 1.0) * 2))
    hi2 = int(min(n - 1.0, (cy + half + reach + 1.0) * 2))
    for i in range(lo, hi + 1):
        px = (i + 0.5) / 2.0
        dx = abs(px - cx) - half
        if dx < 0:
            dx = 0.0
        for j in range(lo2, hi2 + 1):
            py = (j + 0.5) / 2.0
            dy = abs(py - cy) - half
            if dy < 0:
                dy = 0.0
            if dx * dx + dy * dy <= reach * reach:
                goal[i, j] = True
    return goal


@njit(cache=True)
def _building_costs(dist, xs, ys, halves, reach):
    """Cheapest path cost from the source to any cell within `reach` of each
    building hitbox (dist is a source Dijkstra field)."""
    n = dist.shape[0]
    out = np.full(xs.shape[0], 1e9, dtype=np.float32)
    for b in range(xs.shape[0]):
        cx, cy, half = xs[b], ys[b], halves[b]
        lo = int(max(0.0, (cx - half - reach - 1.0) * 2))
        hi = int(min(n - 1.0, (cx + half + reach + 1.0) * 2))
        lo2 = int(max(0.0, (cy - half - reach - 1.0) * 2))
        hi2 = int(min(n - 1.0, (cy + half + reach + 1.0) * 2))
        best = np.float32(1e9)
        for i in range(lo, hi + 1):
            px = (i + 0.5) / 2.0
            dx = abs(px - cx) - half
            if dx < 0:
                dx = 0.0
            for j in range(lo2, hi2 + 1):
                py = (j + 0.5) / 2.0
                dy = abs(py - cy) - half
                if dy < 0:
                    dy = 0.0
                if dx * dx + dy * dy <= reach * reach and dist[i, j] < best:
                    best = dist[i, j]
        out[b] = best
    return out


class Grid:
    """Walkability for ground units; owned by one battle."""

    def __init__(self, world_tiles: int):
        self.n = world_tiles * RES
        self.blocked = np.zeros((self.n, self.n), dtype=np.bool_)
        self.wall = np.zeros((self.n, self.n), dtype=np.bool_)
        self.version = 0
        self._cache: dict = {}
        # change log for exact incremental repair: (version, decrease_only, i0, i1, j0, j1)
        self._log: list = []

    def _changed(self, i0, i1, j0, j1, decrease):
        self.version += 1
        self._log.append((self.version, decrease, max(0, i0 - 1), min(self.n, i1 + 1), max(0, j0 - 1), min(self.n, j1 + 1)))

    def block_square(self, cx: float, cy: float, half: float, value: bool = True) -> None:
        lo_i = int(round((cx - half) * RES))
        hi_i = int(round((cx + half) * RES))
        lo_j = int(round((cy - half) * RES))
        hi_j = int(round((cy + half) * RES))
        self.blocked[lo_i:hi_i, lo_j:hi_j] = value
        self._changed(lo_i, hi_i, lo_j, hi_j, not value)

    def set_wall(self, tx: int, ty: int, present: bool) -> None:
        self.wall[tx * RES : (tx + 1) * RES, ty * RES : (ty + 1) * RES] = present
        self._changed(tx * RES, (tx + 1) * RES, ty * RES, (ty + 1) * RES, not present)

    def _repair(self, entry, wall_extra):
        """Bring a cached field up to the current version without a full
        recompute when every change since it was built only removed obstacles.
        Returns None when a full recompute is needed."""
        v0, dist, goal = entry
        if not self._log or self._log[0][0] > v0 + 1:
            return None  # the log no longer reaches back that far
        seed = np.zeros((self.n, self.n), dtype=np.bool_)
        for ver, dec, i0, i1, j0, j1 in reversed(self._log):
            if ver <= v0:
                break
            if not dec:
                return None
            seed[i0:i1, j0:j1] = True
        dist = dist.copy()
        if goal is not None:
            # goal cells freed by a removed obstacle are goal cells again (distance 0)
            freed = seed & goal & ~self.blocked
            dist[freed] = 0.0
        return _relax(dist, seed, self.blocked, self.wall, np.float32(wall_extra), _NEIGHBORS, _STEP)

    def field(self, key, cx: float, cy: float, half: float, reach: float, wall_extra: float):
        entry = self._cache.get(key)
        if entry is not None and entry[0] == self.version:
            return entry[1]
        goal = _goal_mask(self.n, cx, cy, half, reach)
        dist = None
        # repair only when the goal area still matches (keeps results
        # identical to a recompute)
        if entry is not None and np.array_equal(entry[2], goal):
            dist = self._repair(entry, wall_extra)
        if dist is None:
            dist = _dijkstra(goal, self.blocked, self.wall, np.float32(wall_extra), _NEIGHBORS, _STEP)
        self._cache[key] = (self.version, dist, goal)
        return dist

    def source_field(self, x: float, y: float, wall_extra: float):
        """Path cost from (x, y) to every cell; cached per tile and version."""
        i, j = self.cell(x, y)
        key = ("src", i // RES, j // RES, wall_extra)
        entry = self._cache.get(key)
        if entry is not None and entry[0] == self.version:
            return entry[1]
        dist = None
        goal = np.zeros((self.n, self.n), dtype=np.bool_)
        goal[i, j] = True
        # the key is per tile but the source cell is a half-tile: repair only
        # for the same source cell (keeps results identical to a recompute).
        # The source is passed as the goal so a source inside a hitbox that
        # has since fallen restarts at 0; without it the field stayed all-INF.
        if entry is not None and entry[2] == (i, j):
            dist = self._repair((entry[0], entry[1], goal), wall_extra)
        if dist is None:
            dist = _dijkstra(goal, self.blocked, self.wall, np.float32(wall_extra), _NEIGHBORS, _STEP)
        self._cache[key] = (self.version, dist, (i, j))
        return dist

    def building_costs(self, x, y, wall_extra, xs, ys, halves, reach):
        return _building_costs(self.source_field(x, y, wall_extra), xs, ys, halves, np.float64(reach))

    def prune(self):
        """Keep the cache bounded. Stale entries are kept (they are repaired
        incrementally); the oldest beyond 600 entries are dropped, and the
        change log is trimmed to what the oldest kept entry still needs."""
        if len(self._cache) > 600:
            items = sorted(self._cache.items(), key=lambda kv: -kv[1][0])[:400]
            self._cache = dict(items)
        if self._cache:
            oldest = min(e[0] for e in self._cache.values())
            self._log = [c for c in self._log if c[0] > oldest]

    def cell(self, x: float, y: float) -> tuple[int, int]:
        i = min(self.n - 1, max(0, int(x * RES)))
        j = min(self.n - 1, max(0, int(y * RES)))
        return i, j

    def next_step(self, dist, x: float, y: float):
        """Best neighbouring cell centre and whether it is a wall cell.

        Returns (tx, ty, is_wall, at_goal). at_goal means the unit stands on a
        goal cell already and should attack.
        """
        i, j = self.cell(x, y)
        here = dist[i, j]
        if here <= 0.0:
            return x, y, False, True
        best = here
        bi, bj = i, j
        n = self.n
        for q in range(8):
            ni = i + _NEIGHBORS[q, 0]
            nj = j + _NEIGHBORS[q, 1]
            if 0 <= ni < n and 0 <= nj < n:
                d = dist[ni, nj]
                if d < best:
                    best = d
                    bi, bj = ni, nj
        if bi == i and bj == j:
            return x, y, False, here >= INF
        return (bi + 0.5) / RES, (bj + 0.5) / RES, bool(self.wall[bi, bj]), False
