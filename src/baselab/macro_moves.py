"""Macro moves: whole design ideas applied to a layout in one step.

The search's small moves (optimize.mutate: one swap, one nudge, one trap)
change the score by 0.2-1 trophies, below the noise of an affordable battle
count. These moves each apply one sourced design rule
(docs/BASE_DESIGN_PRINCIPLES.md) to the whole base at once, so their effect
is large enough to see on a short paired battle set.

Most moves only permute buildings between same-size slots (the positions
the base already uses), so the result is always legal: every building, wall
and trap is kept. ``ring_th`` moves walls (count unchanged) and the trap
moves re-seat traps on free tiles.

Every move is ``fn(layout, **kw) -> (new_layout, description) | None``
(None: the idea does not apply, e.g. the Town Hall is already deepest).
``MOVES`` lists them by name; ``apply(name, layout, **kw)`` runs one.
"""

from __future__ import annotations

import math
from collections import deque
from itertools import combinations

from .archetypes import ROLE, compartments
from .deploy import tile_neighbors
from .layout import Layout
from .mechanics import BUILDING_TYPES, VILLAGE, WALL_COUNT

# how deep a building belongs, 0 = Town Hall compartment .. 1 = outermost
# (archetypes.ROLE, the generator's role table); the Town Hall goes deepest
# (ranked: Town Hall survival is the lever, principles 6.2), trash last
TARGET = {k: t for k, (t, _w) in ROLE.items()}
TARGET.update({"th": -0.1, "bh": 0.8})
TRASH = 1.2

# principles 2.2: high-value defenses (Fireball / Rocket Spear targets)
HIGH = {"inferno", "eagle", "mono", "scatter", "mat", "ric"}
# key defenses that should not stand in the outer layer
KEY = HIGH | {"ad", "xbow", "st", "cc", "crafting"}
# principles 2.2: what the closest defense from an edge should be
LOW_DEF = {"at", "cannon", "mortar", "sweeper", "bt", "bh", "tesla", "wt"}
SPLASH = {"wt", "bt", "mortar", "scatter"}


def target(key: str) -> float:
    return TARGET.get(key, TRASH)


# ----------------------------------------------------------------- geometry


def centre(b) -> tuple[float, float]:
    return b.x + b.size / 2.0, b.y + b.size / 2.0


def th_of(lay: Layout):
    return next(b for b in lay.buildings if b.key == "th")


def wall_depth(lay: Layout) -> dict:
    """Walls an attacker must break to reach each tile from the map edge
    (0-1 BFS; buildings are walked around)."""
    walls = lay.walls
    INF = 10**9
    d = {(x, y): INF for x in range(VILLAGE) for y in range(VILLAGE)}
    q = deque()
    for i in range(VILLAGE):
        for t in ((i, 0), (i, VILLAGE - 1), (0, i), (VILLAGE - 1, i)):
            c = 1 if t in walls else 0
            if c < d[t]:
                d[t] = c
                (q.appendleft if c == 0 else q.append)(t)
    while q:
        x, y = q.popleft()
        for n in tile_neighbors(x, y):
            if n in d:
                c = d[(x, y)] + (1 if n in walls else 0)
                if c < d[n]:
                    d[n] = c
                    (q.appendleft if c == d[(x, y)] else q.append)(n)
    return d


class Geo:
    """Per-layout geometry the moves share: wall depth per tile, the walled
    area's centre and the Town Hall centre."""

    def __init__(self, lay: Layout):
        self.depth = wall_depth(lay)
        inner = [t for t, v in self.depth.items() if v >= 1 and t not in lay.walls]
        if inner:
            self.mid = (
                sum(t[0] for t in inner) / len(inner) + 0.5,
                sum(t[1] for t in inner) / len(inner) + 0.5,
            )
        else:
            self.mid = (VILLAGE / 2, VILLAGE / 2)
        self.th = centre(th_of(lay))

    def bdepth(self, b) -> int:
        return min(self.depth[t] for t in b.tiles())

    def inward(self, b, ref: str = "walls") -> tuple:
        """Sort key, larger = more protected: wall depth first, then
        closeness to the walled centre ('walls') or the Town Hall ('th')."""
        cx, cy = centre(b)
        rx, ry = self.mid if ref == "walls" else self.th
        return (self.bdepth(b), -math.hypot(cx - rx, cy - ry))

    def th_dist(self, b) -> float:
        cx, cy = centre(b)
        return math.hypot(cx - self.th[0], cy - self.th[1])


def _swap(a, b):
    a.x, b.x = b.x, a.x
    a.y, b.y = b.y, a.y


def _aim_sweepers(lay: Layout, moved) -> None:
    """A moved Air Sweeper faces away from the Town Hall (its 90-degree
    cone covers the approach on its side)."""
    tx, ty = centre(th_of(lay))
    dirs = ["E", "SE", "S", "SW", "W", "NW", "N", "NE"]
    for b in moved:
        if b.key == "sweeper":
            cx, cy = centre(b)
            ang = math.atan2(cy - ty, cx - tx)
            b.mode = dirs[int(round(ang / (math.pi / 4))) % 8]


def _permute(lay: Layout, group: list, new_pos: dict) -> list:
    """Move buildings of `group` (indices, one size) to the positions in
    new_pos {index: (x, y)}; returns the buildings that moved."""
    moved = []
    for i in group:
        b = lay.buildings[i]
        if (b.x, b.y) != new_pos[i]:
            b.x, b.y = new_pos[i]
            moved.append(b)
    return moved


def _by_size(lay: Layout) -> dict:
    out: dict = {}
    for i, b in enumerate(lay.buildings):
        out.setdefault(b.size, []).append(i)
    return out


# ------------------------------------------------------------- slot moves


def role_repack(lay: Layout, ref: str = "walls"):
    """Re-pack the whole base by role: within each footprint size the most
    protected slots get the buildings that belong deepest (Town Hall,
    Infernos, Monolith, Eagle, Spell Towers, CC, Scattershots ...), the
    outer slots get Archer Towers, Cannons and trash. Slots ranked by walls
    to break, then closeness to the walled centre ('walls') or to the
    Town Hall ('th'). The wall plan and traps stay."""
    new = lay.copy()
    g = Geo(new)
    moved = []
    for size, idx in _by_size(new).items():
        slots = sorted(
            ((new.buildings[i].x, new.buildings[i].y) for i in idx),
            key=lambda p: g.inward(_Probe(p, size), ref),
            reverse=True,
        )
        # stable: among equals keep the building that is already deeper first
        order = sorted(
            idx,
            key=lambda i: (
                target(new.buildings[i].key),
                tuple(-v for v in g.inward(new.buildings[i], ref)),
            ),
        )
        moved += _permute(new, idx, dict(zip(order, slots)))
    if not moved:
        return None
    _aim_sweepers(new, moved)
    return new, f"role repack ({ref}, {len(moved)} moved)"


class _Probe:
    """A footprint at (x, y) of a size, for Geo.inward on an empty slot."""

    def __init__(self, p, size):
        self.x, self.y = p
        self.size = size

    def tiles(self):
        for dx in range(self.size):
            for dy in range(self.size):
                yield (self.x + dx, self.y + dy)


def th_deepest(lay: Layout):
    """Town Hall trades places with the most protected 4x4 slot (most walls
    to break, then nearest the walled centre). Principles 6.2."""
    new = lay.copy()
    g = Geo(new)
    th = th_of(new)
    others = [b for b in new.buildings if b.size == th.size and b is not th]
    if not others:
        return None
    best = max(others, key=g.inward)
    if g.inward(best) <= g.inward(th):
        return None
    _swap(th, best)
    return new, f"town hall to deepest 4x4 (was {best.key})"


def pull_strongest(lay: Layout, n: int = 6):
    """The n most valuable defenses that are not yet near the Town Hall
    each trade places with the least valuable same-size building that is
    nearer the Town Hall (principles 2.1: keep the Eagle and key defenses
    out of opener reach)."""
    new = lay.copy()
    g = Geo(new)
    cands = sorted(
        (b for b in new.buildings if b.key in KEY and b.key != "th"),
        key=lambda b: (target(b.key), -g.th_dist(b)),
    )
    moved, done = [], 0
    for b in cands:
        if done >= n:
            break
        d0 = g.th_dist(b)
        partners = [
            o
            for o in new.buildings
            if o.size == b.size
            and o.key not in KEY
            and o.key != "th"
            and target(o.key) > target(b.key) + 0.15
            and g.th_dist(o) < d0 - 2.0
        ]
        if not partners:
            continue
        o = min(partners, key=lambda o: (g.th_dist(o) - 0.0) - 2.0 * target(o.key))
        _swap(b, o)
        moved += [b, o]
        done += 1
    if not done:
        return None
    _aim_sweepers(new, moved)
    return new, f"pull {done} strongest toward the Town Hall"


def splash_inward(lay: Layout):
    """Splash defenses (Wizard/Bomb Towers, Mortars, Scattershots) trade
    places with nearer-the-Town-Hall trash of the same size, so packs that
    reach the core walk into splash (principles 2.8, 3.4)."""
    new = lay.copy()
    g = Geo(new)
    moved = []
    for b in sorted(
        (b for b in new.buildings if b.key in SPLASH), key=lambda b: -g.th_dist(b)
    ):
        partners = [
            o
            for o in new.buildings
            if o.size == b.size
            and target(o.key) >= TRASH
            and g.th_dist(o) < g.th_dist(b) - 3.0
        ]
        if not partners:
            continue
        o = min(partners, key=g.th_dist)
        _swap(b, o)
        moved += [b, o]
    if not moved:
        return None
    return new, f"splash inward ({len(moved) // 2} swaps)"


def _collinear_pen(pts, width=1.5) -> int:
    """Triples where the third point is within `width` of the line of the
    other two (principles 2.3, Giant Arrow lines)."""
    pen = 0
    for a, b, c in combinations(pts, 3):
        for p, q, r in ((a, b, c), (a, c, b), (b, c, a)):
            dx, dy = q[0] - p[0], q[1] - p[1]
            L = math.hypot(dx, dy) or 1.0
            # r between p and q along the line, and close to it
            t = ((r[0] - p[0]) * dx + (r[1] - p[1]) * dy) / (L * L)
            if 0 < t < 1 and abs((r[0] - p[0]) * dy - (r[1] - p[1]) * dx) / L < width:
                pen += 1
                break
    return pen


def spread_ads(lay: Layout):
    """Air Defenses re-seated among the 3x3 slots at their depth so they are
    far apart and no third AD sits on the line of two (principles 2.3:
    one Giant Arrow or Lightning set takes one AD, not two)."""
    new = lay.copy()
    g = Geo(new)
    ads = [b for b in new.buildings if b.key == "ad"]
    if len(ads) < 2:
        return None
    lo, hi = min(g.bdepth(b) for b in ads), max(g.bdepth(b) for b in ads)
    pool = [
        b
        for b in new.buildings
        if b.size == ads[0].size
        and (b.key == "ad" or target(b.key) > target("ad"))
        and lo <= g.bdepth(b) <= hi
        and b.key not in KEY | {"th"} | {"ad"}
        or b.key == "ad"
    ]
    if (
        len(pool) > 22
    ):  # keep the search small: the ADs plus the nearest-to-centre others
        rest = sorted(
            (b for b in pool if b.key != "ad"), key=lambda b: -g.inward(b, "th")[1]
        )
        pool = ads + rest[: 22 - len(ads)]
    pts = {id(b): centre(b) for b in pool}

    def score(sel):
        P = [pts[id(b)] for b in sel]
        md = min(math.hypot(p[0] - q[0], p[1] - q[1]) for p, q in combinations(P, 2))
        return md - 4.0 * _collinear_pen(P)

    cur = score(ads)
    best, best_s = None, cur
    for sel in combinations(pool, len(ads)):
        s = score(sel)
        if s > best_s + 1.0:
            best, best_s = sel, s
    if best is None:
        return None
    # ADs already on a chosen slot stay; the others take the remaining slots
    stay = [b for b in ads if b in best]
    free_slots = [b for b in best if b.key != "ad"]
    movers = [b for b in ads if b not in best]
    moved = []
    for a, o in zip(movers, free_slots):
        _swap(a, o)
        moved += [a, o]
    _aim_sweepers(new, moved)
    return (
        new,
        f"spread ADs (min gap {cur:.1f} -> {best_s:.1f} score, {len(movers)} moved, {len(stay)} kept)",
    )


def fireball_spread(lay: Layout, gap: float = 7.5, rounds: int = 6):
    """High-value defenses closer than `gap` tiles (one Fireball / Overgrowth
    takes both, principles 2.2 and 2.4) are pulled apart: the less valuable
    of the pair trades places with a same-size low-value building at about
    the same depth that is far from the other high-value defenses."""
    new = lay.copy()
    g = Geo(new)
    moved = []
    for _ in range(rounds):
        H = [b for b in new.buildings if b.key in HIGH]

        def near(b, skip=None):
            cx, cy = centre(b)
            return min(
                (
                    math.hypot(cx - centre(o)[0], cy - centre(o)[1])
                    for o in H
                    if o is not b and o is not skip
                ),
                default=99.0,
            )

        pairs = sorted(
            (
                (
                    math.hypot(
                        centre(a)[0] - centre(b)[0], centre(a)[1] - centre(b)[1]
                    ),
                    a,
                    b,
                )
                for a, b in combinations(H, 2)
            ),
            key=lambda t: t[0],
        )
        if not pairs or pairs[0][0] >= gap:
            break
        _, a, b = pairs[0]
        mover = a if target(a.key) >= target(b.key) else b
        d0 = g.bdepth(mover)
        partners = [
            o
            for o in new.buildings
            if o.size == mover.size
            and o.key not in KEY
            and o.key != "th"
            and abs(g.bdepth(o) - d0) <= 1
        ]
        best, best_d = None, near(mover)
        for o in partners:
            ox, oy = centre(o)
            dmin = min(
                (
                    math.hypot(ox - centre(h)[0], oy - centre(h)[1])
                    for h in H
                    if h is not mover
                ),
                default=99.0,
            )
            if dmin > best_d + 1.0 and dmin >= 4.0:
                best, best_d = o, dmin
        if best is None:
            break
        _swap(mover, best)
        moved += [mover, best]
    if not moved:
        return None
    _aim_sweepers(new, moved)
    return new, f"fireball spread ({len(moved) // 2} swaps)"


def outer_screen(lay: Layout):
    """Key defenses in the outermost layer trade places with a low-value
    defense of the same size from deeper in, so the closest defense from
    each edge is a Mortar, Archer Tower or Cannon (principles 2.2)."""
    new = lay.copy()
    g = Geo(new)
    depths = [g.bdepth(b) for b in new.buildings if g.bdepth(b) >= 1]
    if not depths:
        return None
    outer = min(depths)
    moved = []
    for b in [b for b in new.buildings if b.key in KEY and g.bdepth(b) <= outer]:
        partners = [
            o
            for o in new.buildings
            if o.size == b.size and o.key in LOW_DEF and g.bdepth(o) > g.bdepth(b)
        ]
        if not partners:
            partners = [
                o
                for o in new.buildings
                if o.size == b.size
                and target(o.key) >= TRASH
                and g.bdepth(o) > g.bdepth(b)
            ]
        if not partners:
            continue
        o = min(partners, key=lambda o: (-(g.bdepth(o)), g.th_dist(o)))
        _swap(b, o)
        moved += [b, o]
    if not moved:
        return None
    _aim_sweepers(new, moved)
    return new, f"outer screen ({len(moved) // 2} key defenses pulled off the edge)"


def _match(new: Layout, members: list, targets: dict) -> list:
    """Each member (index) goes to the same-size slot among the members'
    own positions nearest its target point (greedy, closest pairs first):
    a geometric idea realised as a legal permutation."""
    moved = []
    by: dict = {}
    for i in members:
        by.setdefault(new.buildings[i].size, []).append(i)
    for size, idx in by.items():
        slots = [(new.buildings[i].x, new.buildings[i].y) for i in idx]
        pairs = sorted(
            (
                math.hypot(
                    sx + size / 2 - targets[i][0], sy + size / 2 - targets[i][1]
                ),
                i,
                k,
            )
            for i in idx
            for k, (sx, sy) in enumerate(slots)
        )
        used_i, used_k, pos = set(), set(), {}
        for _d, i, k in pairs:
            if i in used_i or k in used_k:
                continue
            used_i.add(i)
            used_k.add(k)
            pos[i] = slots[k]
        moved += _permute(new, idx, pos)
    return moved


def rotate_core(lay: Layout, quarter: int = 2, radius: float = 9.0):
    """Turn the core (buildings within `radius` of the Town Hall) by
    quarter x 90 degrees about the Town Hall: the core's strong face points
    at a different side. Realised by same-size slot matching."""
    new = lay.copy()
    tx, ty = centre(th_of(new))
    members = [
        i
        for i, b in enumerate(new.buildings)
        if b.key != "th" and math.hypot(centre(b)[0] - tx, centre(b)[1] - ty) <= radius
    ]
    if len(members) < 4:
        return None
    a = quarter * math.pi / 2
    ca, sa = round(math.cos(a)), round(math.sin(a))
    tg = {}
    for i in members:
        cx, cy = centre(new.buildings[i])
        dx, dy = cx - tx, cy - ty
        tg[i] = (tx + ca * dx - sa * dy, ty + sa * dx + ca * dy)
    moved = _match(new, members, tg)
    if not moved:
        return None
    _aim_sweepers(new, moved)
    return new, f"rotate core {90 * quarter} deg ({len(moved)} moved)"


def swap_core_flank(lay: Layout, side: int = 0, radius: float = 8.0):
    """Swap the core (around the Town Hall) with one flank (the outer part
    of the walled area on side `side` of 4): the strong group moves out to
    form a kill zone on that side and the flank's buildings move in
    (principles 4.1, bait side). Same-size slot matching."""
    new = lay.copy()
    g = Geo(new)
    tx, ty = g.th
    ang = side * math.pi / 2 + math.pi / 4
    core = [
        i
        for i, b in enumerate(new.buildings)
        if b.key != "th" and g.th_dist(b) <= radius
    ]
    flank = []
    for i, b in enumerate(new.buildings):
        cx, cy = centre(b)
        a = math.atan2(cy - ty, cx - tx)
        if (
            b.key != "th"
            and i not in core
            and g.bdepth(b) >= 1
            and abs((a - ang + math.pi) % (2 * math.pi) - math.pi) <= math.pi / 4
        ):
            flank.append(i)
    if len(core) < 3 or len(flank) < 3:
        return None
    fc = [centre(new.buildings[i]) for i in flank]
    fx, fy = sum(p[0] for p in fc) / len(fc), sum(p[1] for p in fc) / len(fc)
    cc = [centre(new.buildings[i]) for i in core]
    kx, ky = sum(p[0] for p in cc) / len(cc), sum(p[1] for p in cc) / len(cc)
    tg = {}
    for i in core:
        cx, cy = centre(new.buildings[i])
        tg[i] = (cx + fx - kx, cy + fy - ky)
    for i in flank:
        cx, cy = centre(new.buildings[i])
        tg[i] = (cx + kx - fx, cy + ky - fy)
    moved = _match(new, core + flank, tg)
    if not moved:
        return None
    _aim_sweepers(new, moved)
    return new, f"swap core <-> flank {side} ({len(moved)} moved)"


def transpose(lay: Layout):
    """Control, not a design idea: the whole base mirrored on its diagonal
    (x, y) -> (y, x). The base is the same; only the sides the scenario
    angles hit change, so its paired delta measures angle noise."""
    new = lay.copy()
    for b in new.buildings:
        b.x, b.y = b.y, b.x
    for t in new.traps:
        t.x, t.y = t.y, t.x
    new.walls = {(y, x) for x, y in new.walls}
    new.wall_levels = {(y, x): v for (x, y), v in new.wall_levels.items()}
    flip = {
        "N": "W",
        "W": "N",
        "S": "E",
        "E": "S",
        "NE": "SW",
        "SW": "NE",
        "NW": "NW",
        "SE": "SE",
    }
    for b in new.buildings:
        if b.key in ("sweeper", "firespitter") and b.mode in flip:
            b.mode = flip[b.mode]
    return new, "transpose (control)"


# -------------------------------------------------------------- wall move


def _occ(lay: Layout, skip_traps=False) -> set:
    occ = set(lay.walls)
    for b in lay.buildings:
        occ.update(b.tiles())
    if not skip_traps:
        for t in lay.traps:
            occ.update(t.tiles())
    return occ


def _relocate_trap(lay: Layout, t, occ: set, near) -> bool:
    nx, ny = near
    best = None
    for x in range(VILLAGE - t.size + 1):
        for y in range(VILLAGE - t.size + 1):
            if all(
                (x + dx, y + dy) not in occ
                for dx in range(t.size)
                for dy in range(t.size)
            ):
                d = math.hypot(x - nx, y - ny)
                if best is None or d < best[0]:
                    best = (d, x, y)
    if best is None:
        return False
    t.x, t.y = best[1], best[2]
    occ.update(t.tiles())
    return True


def ring_th(lay: Layout):
    """Close the Town Hall in its own wall ring (a 1- or 2-tile gap around
    it), paid for with spare walls and dead-end wall tips far from the Town
    Hall; traps on the ring tiles move to the nearest free tile. Ranked:
    one more wall layer between every attack and the Town Hall."""
    new = lay.copy()
    th = th_of(new)
    comps, _out = compartments(new.walls)
    thc = next((c for c in comps if (th.x, th.y) in c), None)
    if thc is not None and len(thc) <= 64:
        return None  # already in a tight compartment
    bocc = set()
    for b in new.buildings:
        bocc.update(b.tiles())
    for gap in (1, 2):
        x0, y0, x1, y1 = (
            th.x - gap,
            th.y - gap,
            th.x + th.size - 1 + gap,
            th.y + th.size - 1 + gap,
        )
        ring = {(x, y) for x in range(x0, x1 + 1) for y in (y0, y1)} | {
            (x, y) for y in range(y0, y1 + 1) for x in (x0, x1)
        }
        if (
            any(not (0 <= x < VILLAGE and 0 <= y < VILLAGE) for x, y in ring)
            or ring & bocc
        ):
            continue
        # the enclosed square must hold nothing but the TH and free tiles/traps
        need = len(ring - new.walls)
        walls = set(new.walls)
        spare = WALL_COUNT - len(walls)
        take = max(0, need - spare)
        tx, ty = centre(th)
        removed = 0
        for _ in range(take * 4 + 10):
            if removed >= take:
                break
            tips = [
                w
                for w in walls
                if w not in ring
                and sum(
                    (w[0] + dx, w[1] + dy) in walls
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                )
                <= 1
            ]
            if not tips:
                break
            w = max(tips, key=lambda w: math.hypot(w[0] - tx, w[1] - ty))
            walls.discard(w)
            removed += 1
        if removed < take:
            continue
        walls |= ring
        new.walls = walls
        new.wall_levels = {p: v for p, v in new.wall_levels.items() if p in walls}
        occ = _occ(new, skip_traps=True)
        for t in new.traps:
            if set(t.tiles()) & ring:
                if not _relocate_trap(new, t, occ, (t.x, t.y)):
                    return None
            else:
                occ.update(t.tiles())
        if new.problems():
            continue
        return (
            new,
            f"ring the Town Hall (gap {gap}, {need} walls, {removed} tips taken)",
        )
    return None


# -------------------------------------------------------------- trap moves

# placement order and the spacing kept between traps of one type (tiles):
# Giant Bombs, mines and Air Bombs may pair (principles 3.3, 3.4), but not pile
TRAP_ORDER = (
    "tornado",
    "giant",
    "seeking",
    "skeleton",
    "airbomb",
    "spring",
    "bomb",
    "giga",
)
TRAP_GAP = {
    "tornado": 0,
    "giant": 2.0,
    "seeking": 1.5,
    "skeleton": 3.0,
    "airbomb": 2.5,
    "spring": 1.5,
    "bomb": 2.5,
    "giga": 3.0,
}


def traps_on_traffic(lay: Layout, diag, *, top: int = 400):
    """Re-seat every trap where the traced attacks' troops actually go
    (diagnose.Diagnosis.trap_tiles: Giant Bombs on ground packs, mines on
    Healers and flying heroes, Tornado and ground Skeletons on heroes...),
    hottest tiles first, keeping a little spacing within a type
    (principles 3.1). Buildings and walls stay."""
    new = lay.copy()
    occ = _occ(new, skip_traps=True)
    placed_at: dict = {}
    moved = 0
    order = sorted(
        range(len(new.traps)),
        key=lambda i: (
            TRAP_ORDER.index(new.traps[i].key) if new.traps[i].key in TRAP_ORDER else 99
        ),
    )
    for i in order:
        t = new.traps[i]
        hot = diag.trap_tiles(t.key, t.mode, top)
        gap = TRAP_GAP.get(t.key, 2.0)
        spot = None
        for (x, y), _v in hot:
            x0, y0 = x - (t.size - 1 if t.size > 1 else 0), y - (
                t.size - 1 if t.size > 1 else 0
            )
            for px, py in ((x0, y0), (x, y)):
                tiles = [
                    (px + dx, py + dy) for dx in range(t.size) for dy in range(t.size)
                ]
                if all(
                    0 <= a < VILLAGE and 0 <= b < VILLAGE and (a, b) not in occ
                    for a, b in tiles
                ) and all(
                    math.hypot(px - qx, py - qy) >= gap
                    for qx, qy in placed_at.get(t.key, [])
                ):
                    spot = (px, py)
                    break
            if spot:
                break
        if spot is None:
            # no hot tile left: keep the old spot if it is still free
            tiles = list(t.tiles())
            if any(p in occ for p in tiles):
                if not _relocate_trap(new, t, occ, (t.x, t.y)):
                    return None
                continue
            spot = (t.x, t.y)
        if spot != (t.x, t.y):
            moved += 1
        t.x, t.y = spot
        occ.update(t.tiles())
        placed_at.setdefault(t.key, []).append(spot)
    if not moved or new.problems():
        return None
    return new, f"traps on traffic ({moved} re-seated)"


def traps_to_core(lay: Layout):
    """No battle traces needed: ground traps that sit outside the walls move
    into the free tiles nearest the Town Hall's approach (one or two walls
    in), air traps next to the Air Defenses; principles 3.3-3.4 (traps where
    troops must commit, mines one layer in)."""
    new = lay.copy()
    g = Geo(new)
    occ = _occ(new, skip_traps=True)
    ads = [centre(b) for b in new.buildings if b.key == "ad"]
    tx, ty = g.th
    out_traps = [t for t in new.traps if min(g.depth[p] for p in t.tiles()) == 0]
    keep = [t for t in new.traps if t not in out_traps]
    for t in keep:
        occ.update(t.tiles())
    if not out_traps:
        return None
    free = [
        (x, y)
        for x in range(VILLAGE)
        for y in range(VILLAGE)
        if (x, y) not in occ and g.depth[(x, y)] >= 1
    ]
    placed: list = [(t.x, t.y) for t in keep]
    moved = 0
    for t in out_traps:
        air = t.key in ("seeking", "airbomb") or (
            t.key == "skeleton" and t.mode == "air"
        )

        def cost(p):
            if air and ads:
                d = min(math.hypot(p[0] + 0.5 - a, p[1] + 0.5 - b) for a, b in ads)
                return abs(d - 3.0)
            return abs(math.hypot(p[0] + 0.5 - tx, p[1] + 0.5 - ty) - 5.0)

        for p in sorted(free, key=cost):
            tiles = [
                (p[0] + dx, p[1] + dy) for dx in range(t.size) for dy in range(t.size)
            ]
            if all(
                q not in occ and 0 <= q[0] < VILLAGE and 0 <= q[1] < VILLAGE
                for q in tiles
            ) and all(math.hypot(p[0] - a, p[1] - b) >= 2.0 for a, b in placed):
                t.x, t.y = p
                occ.update(tiles)
                placed.append(p)
                moved += 1
                break
        else:
            occ.update(t.tiles())
    if not moved or new.problems():
        return None
    return new, f"traps into the core ({moved} moved)"


# ------------------------------------------------------------------ table

MOVES = {
    "th_deepest": th_deepest,
    "role_repack": role_repack,
    "role_repack_th": lambda lay: role_repack(lay, "th"),
    "pull_strongest": pull_strongest,
    "splash_inward": splash_inward,
    "spread_ads": spread_ads,
    "fireball_spread": fireball_spread,
    "outer_screen": outer_screen,
    "rotate_core": rotate_core,
    "swap_core_flank": swap_core_flank,
    "ring_th": ring_th,
    "traps_to_core": traps_to_core,
    "traps_on_traffic": traps_on_traffic,  # needs diag=
    "transpose": transpose,  # control
}


def apply(name: str, lay: Layout, **kw):
    """Run one macro move; None if it does not apply. Raises if a move ever
    returns an illegal layout or loses a building, wall or trap."""
    out = MOVES[name](lay, **kw)
    if out is None:
        return None
    new, desc = out
    assert not new.problems(), (name, new.problems()[:3])
    assert sorted(b.key for b in new.buildings) == sorted(
        b.key for b in lay.buildings
    ), name
    assert len(new.walls) >= len(lay.walls) and len(new.traps) == len(lay.traps), name
    return new, desc


__all__ = ["MOVES", "apply", "Geo", "wall_depth"]
