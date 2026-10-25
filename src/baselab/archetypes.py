"""Original TH16 layouts built wall-plan first, not from an existing base.

``organic`` (the default) has no template at all: a random blob outline,
then irregular rooms from a weighted Voronoi split of random seed points,
packed tighter near the Town Hall (small core pockets, bigger outer rooms),
with a random distance rule per design (angular, round or skewed), random
room merges and dead-end wall spikes. ``free`` is the blockier variant: a random outer shape (a union of 1-3
rectangles: square, L, T, plus or lopsided) is cut by random binary splits
into compartments of random size, the Town Hall goes in a random spot and
each design jitters how deep every defense family sits. The named styles
below are kept as extra starting points.

Each archetype draws a compartment wall plan (straight, 4-connected walls
only, so no diagonal leaks), then packs buildings by role:

- ``grid``: a square of staggered "brick" compartments, Town Hall central.
- ``offset``: the same brick plan with the Town Hall pushed off centre, so
  the strongest defenses sit between it and the far side.
- ``rings``: nested rectangles cut into cells by staggered radial walls.
- ``wide``: a long rectangle, which changes the approach angles on two sides.

Placement: the Town Hall goes in its compartment, core defenses (Infernos,
Eagle, Scatters, Monolith, Spell Towers, CC) go in the compartments nearest
it, then the mid and outer layers. At most two big defenses share a
compartment. Collectors, camps and Builder's Huts plug any drop hole that
is left, and the rest of the trash rings the walls outside.
"""

from __future__ import annotations

import math
import random

from .deploy import flood_tiles, inside_holes, outside
from .generator import Blueprint, _Board, _orient_sweepers, _place_traps, top_up_walls
from .layout import Layout, Placement
from .mechanics import BUILDING_TYPES, INVENTORY, VILLAGE, WALL_COUNT

ARCHETYPES = ("organic", "free", "grid", "offset", "rings", "wide")

# role -> (target depth 0 = Town Hall compartment .. 1 = outermost, weight)
ROLE = {
    "inferno": (0.05, 6),
    "eagle": (0.1, 6),
    "scatter": (0.2, 5),
    "mono": (0.05, 6),
    "cc": (0.15, 4),
    "crafting": (0.25, 4),
    "st": (0.1, 5),
    "banner": (0.15, 3),
    "xbow": (0.4, 4),
    "ad": (0.45, 4),
    "wt": (0.55, 3),
    "ric": (0.45, 3),
    "mat": (0.4, 3),
    "bt": (0.6, 3),
    "sweeper": (0.5, 3),
    "tesla": (0.5, 2),
    "ds": (0.3, 2),
    "gs": (0.65, 2),
    "es": (0.65, 2),
    "at": (0.85, 3),
    "cannon": (0.9, 3),
    "mortar": (0.7, 3),
}
INSIDE = [
    "inferno",
    "mono",
    "eagle",
    "st",
    "scatter",
    "cc",
    "crafting",
    "xbow",
    "ad",
    "ric",
    "mat",
    "wt",
    "bt",
    "sweeper",
    "mortar",
    "at",
    "cannon",
    "tesla",
    "banner",
    "ds",
    "gs",
    "es",
]
BIG = {
    "inferno",
    "mono",
    "eagle",
    "scatter",
    "xbow",
    "ad",
    "ric",
    "mat",
    "wt",
    "bt",
    "mortar",
    "at",
    "cannon",
    "crafting",
    "sweeper",
    "st",
}
# hole pluggers, best first (Teslas do not block deployment, so never used)
FILLERS = [
    "bh",
    "gm",
    "ec",
    "dd",
    "camp",
    "barracks",
    "dbarracks",
    "sf",
    "dsf",
    "lab",
    "pethouse",
    "smith",
    "helper",
    "bob",
    "workshop",
    "herohall",
]


def _rect(x0, y0, x1, y1):
    t = set()
    for x in range(x0, x1 + 1):
        t.add((x, y0))
        t.add((x, y1))
    for y in range(y0, y1 + 1):
        t.add((x0, y))
        t.add((x1, y))
    return t


def _hseg(y, x0, x1):
    return {(x, y) for x in range(x0, x1 + 1)}


def _vseg(x, y0, y1):
    return {(x, y) for y in range(y0, y1 + 1)}


def _cuts(lo, hi, cell, offset):
    """Cut positions strictly inside (lo, hi), about `cell` apart."""
    out, p = [], lo + cell // 2 + offset if offset else lo + cell
    while p < hi - 3:
        if p > lo + 3:
            out.append(p)
        p += cell + 1
    return out


def _brick(x0, y0, x1, y1, rng, band, cell):
    """Outer rectangle, full-width horizontal walls every `band`, vertical
    walls inside each band staggered half a cell between bands."""
    keep = _rect(x0, y0, x1, y1)
    segs = []
    ys = [y0] + _cuts(y0, y1, band, 0) + [y1]
    for y in ys[1:-1]:
        segs.append(_hseg(y, x0, x1))
    for k, (a, b) in enumerate(zip(ys, ys[1:])):
        off = (cell + 1) // 2 if k % 2 else 0
        for x in _cuts(x0, x1, cell, off + rng.randint(-1, 1)):
            segs.append(_vseg(x, a, b))
    return keep, segs


def _rings(cx, cy, halves, rng, cell):
    segs = []
    for h in halves:
        segs.append(_rect(cx - h, cy - h, cx + h, cy + h))
    keep = segs.pop()  # the outer ring is never dropped
    for k, (hi, ho) in enumerate(zip(halves, halves[1:])):
        off = rng.randint(0, cell)
        for p in _cuts(cy - ho, cy + ho, cell, off):
            segs.append(_hseg(p, cx - ho, cx - hi))
            segs.append(_hseg(p, cx + hi, cx + ho))
        for p in _cuts(cx - hi, cx + hi, cell, off + 2):
            segs.append(_vseg(p, cy - ho, cy - hi))
            segs.append(_vseg(p, cy + hi, cy + ho))
    return keep, segs


def _free(rng: random.Random):
    """Random outer shape cut into random compartments (binary splits)."""
    U = set()
    w, h = rng.randint(20, 32), rng.randint(20, 32)
    x0, y0 = rng.randint(3, 41 - w), rng.randint(3, 41 - h)
    rects = [(x0, y0, x0 + w - 1, y0 + h - 1)]
    for _ in range(rng.choice((0, 0, 1, 1, 2))):
        ew, eh = rng.randint(8, 18), rng.randint(8, 18)
        ax, ay, bx, by = rng.choice(rects)
        ex = rng.randint(max(3, ax - ew + 4), min(41 - ew, bx - 3))
        ey = rng.randint(max(3, ay - eh + 4), min(41 - eh, by - 3))
        rects.append((ex, ey, ex + ew - 1, ey + eh - 1))
    for ax, ay, bx, by in rects:
        U |= {(x, y) for x in range(ax, bx + 1) for y in range(ay, by + 1)}
    keep = {
        (x, y)
        for x, y in U
        if any((x + dx, y + dy) not in U for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    }
    inner = U - keep
    xs = [x for x, _ in U]
    ys = [y for _, y in U]
    segs = []
    min_cell = rng.randint(4, 6)
    target = rng.randint(25, 60)

    def split(ax, ay, bx, by):
        wd, ht = bx - ax - 1, by - ay - 1  # interior size between the bounding walls
        area = sum(
            1 for x in range(ax + 1, bx) for y in range(ay + 1, by) if (x, y) in inner
        )
        if area <= target * rng.uniform(0.7, 1.4):
            return
        horiz = ht > wd if abs(ht - wd) > 3 else rng.random() < 0.5
        lo, hi = (ay, by) if horiz else (ax, bx)
        if hi - lo - 1 < 2 * min_cell + 1:
            horiz = not horiz
            lo, hi = (ay, by) if horiz else (ax, bx)
            if hi - lo - 1 < 2 * min_cell + 1:
                return
        p = rng.randint(lo + min_cell + 1, hi - min_cell - 1)
        seg = (
            {(x, p) for x in range(ax, bx + 1)}
            if horiz
            else {(p, y) for y in range(ay, by + 1)}
        )
        seg &= inner
        if seg:
            segs.append(seg)
        if horiz:
            split(ax, ay, bx, p)
            split(ax, p, bx, by)
        else:
            split(ax, ay, p, by)
            split(p, ay, bx, by)

    split(min(xs), min(ys), max(xs), max(ys))
    th = rng.choice(sorted(inner))
    if rng.random() < 0.5:  # half the time near the shape's middle
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        th = (int(mx + rng.uniform(-3, 3)), int(my + rng.uniform(-3, 3)))
    return keep, segs, th


def _organic(rng: random.Random):
    """Blob outline + weighted Voronoi rooms, denser near the Town Hall."""
    # outline: union of random discs/ellipses/rects around a centre
    cx, cy = 22 + rng.uniform(-3, 3), 22 + rng.uniform(-3, 3)
    U = set()
    for _ in range(rng.randint(4, 9)):
        ox, oy = cx + rng.uniform(-8, 8), cy + rng.uniform(-8, 8)
        rx, ry = rng.uniform(6, 13), rng.uniform(6, 13)
        shape = rng.choice(("ellipse", "rect", "diamond"))
        for x in range(3, 41):
            for y in range(3, 41):
                u, v = (x + 0.5 - ox) / rx, (y + 0.5 - oy) / ry
                if (
                    (shape == "ellipse" and u * u + v * v <= 1)
                    or (shape == "rect" and abs(u) <= 1 and abs(v) <= 1)
                    or (shape == "diamond" and abs(u) + abs(v) <= 1.3)
                ):
                    U.add((x, y))
    # fill pockets so the outline is one solid region
    outer = outside(Layout("tmp", walls=set(U)))
    U |= {(x, y) for x in range(VILLAGE) for y in range(VILLAGE) if (x, y) not in outer}
    keep = {
        (x, y)
        for x, y in U
        if any((x + dx, y + dy) not in U for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    }
    inner = U - keep
    if len(inner) < 450:
        return keep, [], (int(cx), int(cy))
    # Town Hall point, then seeds by Poisson-disc with spacing growing outward
    cand = sorted(inner)
    th = (
        rng.choice(cand)
        if rng.random() < 0.35
        else (int(cx + rng.uniform(-3, 3)), int(cy + rng.uniform(-3, 3)))
    )
    base, grow = rng.uniform(4.0, 5.5), rng.uniform(0.15, 0.4)
    seeds = [th]
    rng.shuffle(cand)
    for t in cand:
        d = math.hypot(t[0] - th[0], t[1] - th[1])
        sp = base + grow * d
        if all(math.hypot(t[0] - a, t[1] - b) >= sp for a, b in seeds):
            seeds.append(t)
    p = rng.choice(
        (1.0, 1.5, 2.0, 2.0, 3.0, 8.0)
    )  # distance rule: diamond .. round .. square
    sx = rng.uniform(0.75, 1.3)  # skew
    wgt = [rng.uniform(-1.2, 1.2) for _ in seeds]

    def dist(t, i):
        a, b = seeds[i]
        return (abs(t[0] - a) * sx) ** p + (abs(t[1] - b) / sx) ** p

    cell = {}
    for t in inner:
        cell[t] = min(range(len(seeds)), key=lambda i: dist(t, i) ** (1 / p) + wgt[i])
    edges: dict = {}
    for (x, y), c in cell.items():
        lower = {
            cell[n]
            for n in ((x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            if n in cell and cell[n] < c
        }
        if lower:
            edges.setdefault((min(lower), c), set()).add((x, y))
    segs = list(edges.values())
    # random merges: drop a few room boundaries outright
    rng.shuffle(segs)
    segs = segs[int(len(segs) * rng.uniform(0.0, 0.25)) :]
    return keep, segs, th


def wall_plan(kind: str, rng: random.Random):
    """(walls, th_target) for an archetype, within the wall budget."""
    c = VILLAGE // 2
    if kind == "organic":
        for _ in range(60):
            keep, segs, th = _organic(rng)
            n = len(keep.union(*segs)) if segs else len(keep)
            if len(keep) < 200 and n >= WALL_COUNT - 40:
                break
    elif kind == "free":
        # freeform: redraw until the plan uses most of the wall budget
        for _ in range(60):
            keep, segs, th = _free(rng)
            n = len(keep.union(*segs)) if segs else len(keep)
            if WALL_COUNT - 45 <= n:
                break
    elif kind in ("grid", "offset"):
        h = rng.randint(14, 16)
        keep, segs = _brick(
            c - h,
            c - h,
            c + h - 1,
            c + h - 1,
            rng,
            band=rng.randint(5, 7),
            cell=rng.randint(6, 8),
        )
        th = (
            (c, c)
            if kind == "grid"
            else (
                c + rng.choice((-1, 1)) * rng.randint(5, 8),
                c + rng.choice((-1, 1)) * rng.randint(3, 8),
            )
        )
    elif kind == "wide":
        hx, hy = rng.randint(17, 19), rng.randint(11, 13)
        if rng.random() < 0.5:
            hx, hy = hy, hx
        keep, segs = _brick(
            c - hx,
            c - hy,
            c + hx - 1,
            c + hy - 1,
            rng,
            band=rng.randint(5, 6),
            cell=rng.randint(6, 8),
        )
        th = (c, c)
    else:
        a = rng.randint(3, 4)
        halves = (a, a + rng.randint(5, 6), rng.randint(15, 16))
        keep, segs = _rings(c, c, halves, rng, cell=rng.randint(6, 8))
        th = (c, c)
    keep = {(x, y) for x, y in keep if 0 <= x < VILLAGE and 0 <= y < VILLAGE}
    segs = [{t for t in s if 0 <= t[0] < VILLAGE and 0 <= t[1] < VILLAGE} for s in segs]
    rng.shuffle(segs)
    walls = keep.union(*segs) if segs else set(keep)
    # over budget: drop whole interior segments (merging two compartments)
    while len(walls) > WALL_COUNT and segs:
        segs.pop()
        walls = keep.union(*segs) if segs else set(keep)
    return walls, th


def compartments(walls):
    out_region = outside(Layout("tmp", walls=set(walls)))
    legal = (
        {(x, y) for x in range(VILLAGE) for y in range(VILLAGE)}
        - set(walls)
        - out_region
    )
    seen, comps = set(), []
    for x in range(VILLAGE):
        for y in range(VILLAGE):
            t = (x, y)
            if t in walls or t in out_region or t in seen:
                continue
            comp = flood_tiles([t], legal - seen)
            seen.update(comp)
            comps.append(comp)
    return comps, out_region


def _foot(x, y, s):
    return [(x + i, y + j) for i in range(s) for j in range(s)]


def _spikes(lay, board, rng):
    """Spend leftover walls on short dead-end spikes into open ground."""
    wl = sorted(lay.walls)
    for _ in range(300):
        left = WALL_COUNT - len(lay.walls)
        if left < 2:
            break
        wx, wy = rng.choice(wl)
        dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        n = rng.randint(2, min(4, left))
        seg = [(wx + dx * k, wy + dy * k) for k in range(1, n + 1)]
        end = (wx + dx * (n + 1), wy + dy * (n + 1))
        if (
            all(
                0 <= x < VILLAGE and 0 <= y < VILLAGE and (x, y) not in board.occ
                for x, y in seg
            )
            and end not in lay.walls
        ):
            for t in seg:
                board.occ.add(t)
            lay.walls |= set(seg)


TH_ZONES = ("center", "mid", "edge")


def th_zone(lay) -> str:
    """Where the Town Hall sits within the walled area: center / mid / edge,
    by its distance from the walled area's centre relative to the farthest
    walled tile (thirds)."""
    comps, out = compartments(lay.walls)
    inner = [t for c in comps for t in c]
    th = next(b for b in lay.buildings if b.key == "th")
    if not inner:
        return "edge"
    mx = sum(t[0] for t in inner) / len(inner)
    my = sum(t[1] for t in inner) / len(inner)
    far = max(math.hypot(x + 0.5 - mx, y + 0.5 - my) for x, y in inner) or 1.0
    r = math.hypot(th.x + 2 - mx, th.y + 2 - my) / far
    return "center" if r < 0.3 else "mid" if r < 0.6 else "edge"


def design(
    kind: str, seed: int, town_hall: int = 16, zone: str | None = None
) -> Layout:
    """`zone` (center / mid / edge) forces where the Town Hall goes inside
    the walled area, so every Town Hall placement gets explored."""
    rng = random.Random(seed)
    walls, (tx, ty) = wall_plan(kind, rng)
    comps, out_region = compartments(walls)
    cid = {t: i for i, comp in enumerate(comps) for t in comp}
    if zone and cid:
        inner = list(cid)
        mx = sum(t[0] for t in inner) / len(inner)
        my = sum(t[1] for t in inner) / len(inner)
        dist = sorted(inner, key=lambda t: math.hypot(t[0] + 0.5 - mx, t[1] + 0.5 - my))
        n = len(dist)
        band = {
            "center": dist[: n // 8],
            "mid": dist[n * 3 // 8 : n * 5 // 8],
            "edge": dist[n * 7 // 8 :],
        }[zone]
        tx, ty = rng.choice(band)
    board = _Board(walls)
    lay = Layout(f"orig-{kind}-{seed}", town_hall=town_hall)
    lay.walls = set(walls)
    inv = dict(INVENTORY[town_hall])

    def put(key, x, y, mode=None):
        s = BUILDING_TYPES[key].size
        board.take(x, y, s)
        lay.buildings.append(Placement(key, x, y, mode))
        inv[key] -= 1

    # Town Hall: the free 4x4 spot inside a compartment nearest the target
    best = None
    for x in range(VILLAGE - 3):
        for y in range(VILLAGE - 3):
            f = _foot(x, y, 4)
            if (
                board.fits(x, y, 4)
                and all(t in cid for t in f)
                and len({cid[t] for t in f}) == 1
            ):
                d = math.hypot(x + 2 - tx, y + 2 - ty)
                if best is None or d < best[0]:
                    best = (d, x, y)
    if best is None:
        raise RuntimeError("no Town Hall spot")
    put("th", best[1], best[2])
    thc = (best[1] + 2, best[2] + 2)

    # compartment depth: rank by distance from the Town Hall, 0..1
    cen = []
    for comp in comps:
        mx = sum(t[0] for t in comp) / len(comp) + 0.5
        my = sum(t[1] for t in comp) / len(comp) + 0.5
        cen.append(math.hypot(mx - thc[0], my - thc[1]))
    order = sorted(range(len(comps)), key=lambda i: cen[i])
    depth = {i: r / max(1, len(order) - 1) for r, i in enumerate(order)}
    load = {i: 0 for i in range(len(comps))}
    jit = 0.3 if kind == "free" else 0.0
    role = {
        k: (min(1.0, max(0.0, t + rng.uniform(-jit, jit))), w)
        for k, (t, w) in ROLE.items()
    }
    placed: dict = {}

    queue = []
    for key in INSIDE:
        queue += [key] * inv.get(key, 0)
    for key in queue:
        s = BUILDING_TYPES[key].size
        target, w = role[key]
        cands = []
        for x in range(VILLAGE - s + 1):
            for y in range(VILLAGE - s + 1):
                f = _foot(x, y, s)
                if not all(t in cid for t in f):
                    continue
                ids = {cid[t] for t in f}
                if len(ids) != 1 or not board.fits(x, y, s):
                    continue
                i = ids.pop()
                sc = w * abs(depth[i] - target) * 10
                if key in BIG:
                    sc += 6 * max(0, load[i] - 1)
                sibs = placed.get(key, [])
                if sibs:
                    near = min(math.hypot(x - a, y - b) for a, b in sibs)
                    sc += max(0.0, 9 - near) * (
                        0.3 if key in ("gs", "es", "banner") else 1.2
                    )
                cands.append((sc + rng.random() * 2.5, x, y, i))
        if not cands:
            continue  # goes outside with the trash
        _, x, y, i = min(cands)
        put(key, x, y)
        load[i] += key in BIG
        placed.setdefault(key, []).append((x, y))

    # plug interior drop holes with trash buildings, largest hole first
    fill = [k for k in FILLERS for _ in range(inv.get(k, 0))]
    for _ in range(200):
        holes = inside_holes(lay)
        if not holes or not fill:
            break
        hole = holes[0]
        best = None
        for key in dict.fromkeys(fill):
            s = BUILDING_TYPES[key].size
            for hx, hy in hole:
                for dx in range(-s, 2):
                    for dy in range(-s, 2):
                        x, y = hx + dx, hy + dy
                        f = _foot(x, y, s)
                        if not board.fits(x, y, s) or not all(t in cid for t in f):
                            continue
                        cover = sum(
                            1
                            for (a, b) in hole
                            if x - 1 <= a <= x + s and y - 1 <= b <= y + s
                        )
                        sc = cover - 0.4 * s * s
                        if best is None or sc > best[0]:
                            best = (sc, key, x, y)
        if best is None:
            break
        _, key, x, y = best
        put(key, x, y)
        fill.remove(key)

    # everything left (trash, plus any defense that found no room) hugs the walls outside
    rest = [k for k, n in inv.items() if n > 0 for _ in range(n)]
    rest.sort(key=lambda k: -BUILDING_TYPES[k].size)
    wall_list = list(walls)
    for key in rest:
        s = BUILDING_TYPES[key].size
        best = None
        for x in range(VILLAGE - s + 1):
            for y in range(VILLAGE - s + 1):
                f = _foot(x, y, s)
                if not board.fits(x, y, s) or not all(t in out_region for t in f):
                    continue
                cxx, cyy = x + s / 2, y + s / 2
                d = min(
                    max(abs(cxx - a - 0.5), abs(cyy - b - 0.5))
                    for a, b in wall_list[::3]
                )
                sc = d + rng.random() * 1.5
                if best is None or sc < best[0]:
                    best = (sc, x, y)
        if best is None:
            raise RuntimeError(f"no room for {key}")
        put(key, best[1], best[2])

    # modes
    for b in lay.buildings:
        if b.key == "inferno":
            b.mode = rng.choice(["single", "single", "multi"])
        elif b.key == "xbow":
            b.mode = rng.choice(["both", "both", "ground"])
        elif b.key == "st":
            b.mode = rng.choice(["rage", "invis", "poison"])
        elif b.key == "crafting":
            b.mode = rng.choice(["cake", "candle", "hunter"])
    if kind == "organic":
        _spikes(lay, board, rng)
    # every wall must be placed: the styled plans can leave up to ~90 unused
    top_up_walls(lay, board.occ, rng)
    _orient_sweepers(lay)
    _place_traps(
        lay,
        board,
        rng,
        Blueprint(town_hall=town_hall, skeleton_air=rng.randint(1, 3), seed=seed),
    )
    lay.notes = f"Original {kind} design (seed {seed}), wall plan first; not derived from any existing base."
    return lay
