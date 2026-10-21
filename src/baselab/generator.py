"""Procedural TH16 layouts built from concentric wall rings and compartments.

A ``Blueprint`` is a small set of design choices (ring radii, spokes, which
zone each building family lives in, trap preferences). ``build`` turns it into
a concrete, legal ``Layout`` using randomized greedy placement. The optimizer
mutates both blueprints and concrete placements.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .layout import Layout, Placement, TrapPlacement
from .mechanics import BUILDING_TYPES, INVENTORY, TRAP_INVENTORY, VILLAGE, WALL_COUNT

C = VILLAGE / 2.0  # 22.0


def cheb(x: float, y: float) -> float:
    return max(abs(x - C), abs(y - C))


def tile_ring(r: int):
    """Tiles whose centre sits at Chebyshev radius r (+-0.5) from the centre."""
    out = []
    for i in range(VILLAGE):
        for j in range(VILLAGE):
            d = cheb(i + 0.5, j + 0.5)
            if r - 0.5 < d <= r + 0.5:
                out.append((i, j))
    return out


# zone name -> Chebyshev radius band (inclusive inner, exclusive outer) for a
# building's centre
DEFAULT_ZONES = {
    "core": (0.0, 6.0),
    "inner": (6.0, 12.5),
    "outer": (12.5, 17.5),
    "trash": (17.5, 22.0),
}

DEFAULT_ASSIGN = {
    "th": "core",
    "inferno": "core",
    "scatter": "core",
    "mono": "core",
    "swt": "core",
    "cc": "core",
    "mgt": "inner",
    "firespitter": "inner",
    "revenge": "inner",
    "crafting": "core",
    "eagle": "inner",
    "xbow": "inner",
    "ad": "inner",
    "st": "core",
    "wt": "inner",
    "mat": "inner",
    "ric": "inner",
    "bt": "inner",
    "sweeper": "inner",
    "at": "outer",
    "cannon": "outer",
    "mortar": "inner",
    "tesla": "inner",
    "bh": "outer",
    "banner": "inner",
    "gs": "outer",
    "es": "outer",
    "ds": "inner",
    "gm": "trash",
    "ec": "trash",
    "dd": "trash",
    "camp": "trash",
    "barracks": "trash",
    "dbarracks": "trash",
    "sf": "trash",
    "dsf": "trash",
    "lab": "trash",
    "workshop": "trash",
    "pethouse": "trash",
    "smith": "trash",
    "herohall": "trash",
    "helper": "trash",
    "bob": "trash",
}

# placement order: big and important first
ORDER = [
    "th",
    "eagle",
    "inferno",
    "scatter",
    "mono",
    "swt",
    "cc",
    "mgt",
    "firespitter",
    "revenge",
    "xbow",
    "ad",
    "st",
    "mat",
    "ric",
    "wt",
    "bt",
    "mortar",
    "sweeper",
    "tesla",
    "banner",
    "at",
    "cannon",
    "bh",
    "ds",
    "gs",
    "es",
    "camp",
    "workshop",
    "herohall",
    "gm",
    "ec",
    "dd",
    "barracks",
    "dbarracks",
    "sf",
    "dsf",
    "lab",
    "pethouse",
    "smith",
    "helper",
    "bob",
    "crafting",
]


@dataclass
class Blueprint:
    rings: tuple = (6, 12, 17)
    spokes: int = 8  # radial wall segments between rings 1-2 and 2-3
    spoke_offset: float = 0.0  # rotation of the spokes (radians)
    zones: dict = field(default_factory=lambda: dict(DEFAULT_ZONES))
    assign: dict = field(default_factory=lambda: dict(DEFAULT_ASSIGN))
    th_offset: tuple = (0, 0)
    modes: dict = field(
        default_factory=lambda: {
            "inferno": ["multi", "single", "multi"],
            "xbow": ["both", "both", "ground", "ground"],
            "st": ["invis", "rage"],
            "sweeper": ["auto", "auto"],
        }
    )
    skeleton_air: int = 2  # how many skeleton traps target air
    seed: int = 0
    town_hall: int = 16


MOVABLE = ["eagle", "xbow", "ad", "st", "wt", "mat", "ric", "bt", "mortar", "sweeper", "tesla", "at", "cannon", "bh", "inferno", "scatter", "mono", "cc", "gs", "es", "ds", "banner"]


def random_blueprint(rng: random.Random, seed: int | None = None) -> Blueprint:
    """A plausible but unoptimized design, used for calibration and as
    optimizer starting points."""
    rings = rng.choice([(6, 12, 17), (7, 13, 18), (5, 11, 17), (6, 11, 16), (7, 12, 18), (5, 10, 15)])
    bp = Blueprint(
        rings=rings,
        spokes=rng.choice([0, 4, 4, 6, 8]),
        spoke_offset=rng.uniform(0, math.pi / 2),
        th_offset=(rng.randint(-2, 2), rng.randint(-2, 2)),
        seed=seed if seed is not None else rng.randrange(10**6),
        skeleton_air=rng.randint(0, 4),
    )
    zones = ["core", "inner", "outer"]
    for key in MOVABLE:
        if rng.random() < 0.25:
            bp.assign[key] = rng.choice(zones)
    bp.zones = {
        "core": (0.0, rings[0] + 0.0),
        "inner": (rings[0] + 0.0, rings[1] + 0.5),
        "outer": (rings[1] + 0.5, rings[2] + 0.5),
        "trash": (rings[2] + 0.5, 22.0),
    }
    infernos = [rng.choice(["multi", "single"]) for _ in range(3)]
    bp.modes["inferno"] = infernos
    bp.modes["st"] = [rng.choice(["invis", "rage", "poison"]) for _ in range(2)]
    bp.modes["xbow"] = [rng.choice(["both", "ground"]) for _ in range(4)]
    return bp


def wall_tiles(bp: Blueprint) -> set:
    """Closed rings first, then spokes while the 325-wall budget lasts."""
    walls: set = set()
    for r in sorted(bp.rings):
        ring = tile_ring(r)
        if len(walls) + len(ring) > WALL_COUNT:
            break
        walls.update(ring)
    rings = sorted(bp.rings)
    spoke_tiles = []
    for k in range(bp.spokes):
        ang = bp.spoke_offset + 2 * math.pi * k / bp.spokes
        dx, dy = math.cos(ang), math.sin(ang)
        m = max(abs(dx), abs(dy))
        seg = []
        for a, b in zip(rings, rings[1:]):
            for s in range(int((b - a) * 3) + 1):
                rr = a + (b - a) * s / ((b - a) * 3)
                t = (int(math.floor(C + dx / m * rr)), int(math.floor(C + dy / m * rr)))
                if t not in walls and t not in seg:
                    seg.append(t)
        spoke_tiles.append(seg)
    # add spokes round-robin, inner tiles first, so every spoke grows evenly
    depth = 0
    while len(walls) < WALL_COUNT and any(depth < len(s) for s in spoke_tiles):
        for seg in spoke_tiles:
            if depth < len(seg) and len(walls) < WALL_COUNT:
                walls.add(seg[depth])
        depth += 1
    return {(x, y) for x, y in walls if 0 <= x < VILLAGE and 0 <= y < VILLAGE}


class _Board:
    def __init__(self, walls):
        self.occ = set(walls)

    def fits(self, x, y, s):
        if x < 0 or y < 0 or x + s > VILLAGE or y + s > VILLAGE:
            return False
        for dx in range(s):
            for dy in range(s):
                if (x + dx, y + dy) in self.occ:
                    return False
        return True

    def take(self, x, y, s):
        for dx in range(s):
            for dy in range(s):
                self.occ.add((x + dx, y + dy))


def _candidates(zone, size, rng, *, angle_bias=None):
    lo, hi = zone
    out = []
    for x in range(VILLAGE - size + 1):
        for y in range(VILLAGE - size + 1):
            d = cheb(x + size / 2.0, y + size / 2.0)
            if lo <= d < hi:
                out.append((x, y))
    rng.shuffle(out)
    return out


def build(bp: Blueprint) -> Layout:
    rng = random.Random(bp.seed)
    walls = wall_tiles(bp)
    board = _Board(walls)
    lay = Layout(name=f"gen-{bp.seed}", town_hall=bp.town_hall)
    inventory = INVENTORY[bp.town_hall]
    lay.walls = set(walls)
    placed_by_key: dict = {}
    mode_iters = {k: list(v) for k, v in bp.modes.items()}
    for key in ORDER:
        bt = BUILDING_TYPES[key]
        zone_name = bp.assign.get(key, "trash")
        for n in range(inventory.get(key, 0)):
            s = bt.size
            if key == "th":
                cx, cy = C + bp.th_offset[0], C + bp.th_offset[1]
                spots = [(int(cx - s / 2) + dx, int(cy - s / 2) + dy) for dx in range(-2, 3) for dy in range(-2, 3)]
            else:
                spots = _candidates(bp.zones[zone_name], s, rng)
                # spread repeats of the same family: prefer spots far from siblings
                sibs = placed_by_key.get(key, [])
                if sibs and key not in ("gm", "ec", "camp", "dd", "gs", "es", "banner"):
                    spots.sort(key=lambda p: -min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in sibs) + rng.random() * 3)
            placed = False
            for x, y in spots:
                if board.fits(x, y, s):
                    board.take(x, y, s)
                    mode = None
                    if key in mode_iters and mode_iters[key]:
                        mode = mode_iters[key].pop(0)
                    lay.buildings.append(Placement(key, x, y, mode))
                    placed_by_key.setdefault(key, []).append((x, y))
                    placed = True
                    break
            if not placed:
                # fall back to anywhere
                for x, y in _candidates((0, 22.1), s, rng):
                    if board.fits(x, y, s):
                        board.take(x, y, s)
                        lay.buildings.append(Placement(key, x, y, None))
                        placed_by_key.setdefault(key, []).append((x, y))
                        placed = True
                        break
            if not placed:
                raise RuntimeError(f"could not place {key}")
    _orient_sweepers(lay)
    _orient_firespitters(lay)
    top_up_walls(lay, board.occ, rng)  # the rings and spokes may leave walls unused
    _place_traps(lay, board, rng, bp)
    return lay


def top_up_walls(lay: Layout, occ: set, rng: random.Random, target: int = WALL_COUNT, close_gaps: bool = False) -> int:
    """Place walls until the layout has `target` of them: every wall the
    player owns must be on the map. `occ` holds the tiles already taken
    (walls, buildings, traps) and is updated. With `close_gaps`, one-tile
    gaps between two walls in line are closed first (a crossover seam);
    then short dead-end spikes grow off existing walls, then single walls
    go next to a wall. Returns how many walls were added."""
    added = 0

    def free(t):
        return 0 <= t[0] < VILLAGE and 0 <= t[1] < VILLAGE and t not in occ

    def put(t):
        nonlocal added
        lay.walls.add(t)
        occ.add(t)
        added += 1

    if close_gaps:
        gaps = sorted({(x + dx, y + dy) for x, y in lay.walls for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))})
        rng.shuffle(gaps)
        for x, y in gaps:
            if len(lay.walls) >= target:
                break
            w = lay.walls
            if free((x, y)) and (((x - 1, y) in w and (x + 1, y) in w) or ((x, y - 1) in w and (x, y + 1) in w)):
                put((x, y))
    wl = sorted(lay.walls)
    for _ in range(300 if wl else 0):
        left = target - len(lay.walls)
        if left < 2:
            break
        wx, wy = rng.choice(wl)
        dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        n = rng.randint(2, min(4, left))
        seg = [(wx + dx * k, wy + dy * k) for k in range(1, n + 1)]
        end = (wx + dx * (n + 1), wy + dy * (n + 1))
        if all(free(t) for t in seg) and end not in lay.walls:
            for t in seg:
                put(t)
    if len(lay.walls) < target:
        near = sorted({(x + dx, y + dy) for x, y in lay.walls for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))})
        rng.shuffle(near)
        for t in near + [(x, y) for x in range(VILLAGE) for y in range(VILLAGE)]:
            if len(lay.walls) >= target:
                break
            if free(t):
                put(t)
    return added


def _orient_sweepers(lay: Layout):
    for b in lay.buildings:
        if b.key == "sweeper" and (b.mode in (None, "auto")):
            # face the village centre: sweepers push air units back outward
            cx, cy = b.x + 1, b.y + 1
            ang = math.atan2(C - cy, C - cx)
            dirs = ["E", "SE", "S", "SW", "W", "NW", "N", "NE"]
            b.mode = dirs[int(round(ang / (math.pi / 4))) % 8]


def _orient_firespitters(lay: Layout):
    """Firespitters cover a ~150 degree arc; face them outward so they cover
    the approach on their side of the base."""
    dirs = ["E", "SE", "S", "SW", "W", "NW", "N", "NE"]
    for b in lay.buildings:
        if b.key == "firespitter" and b.mode is None:
            ang = math.atan2(b.y + 1.5 - C, b.x + 1.5 - C)
            b.mode = dirs[int(round(ang / (math.pi / 4))) % 8]


def _place_traps(lay: Layout, board: _Board, rng: random.Random, bp: Blueprint):
    """Traps go in gaps near defenses, biased by trap role."""
    defense_centres = {}
    for b in lay.buildings:
        defense_centres.setdefault(b.key, []).append((b.x + b.size / 2.0, b.y + b.size / 2.0))

    def near(keys, radius):
        pts = [p for k in keys for p in defense_centres.get(k, [])]
        out = []
        for x in range(VILLAGE):
            for y in range(VILLAGE):
                if any(math.hypot(x + 0.5 - px, y + 0.5 - py) <= radius for px, py in pts):
                    out.append((x, y))
        rng.shuffle(out)
        return out

    plan = {
        "seeking": near(["ad", "inferno", "eagle", "xbow"], 6),
        "airbomb": near(["ad", "scatter", "th"], 7),
        "giant": near(["mat", "ric", "wt", "bt", "th"], 5),
        "spring": near(["at", "cannon", "xbow", "mortar"], 4),
        "bomb": near(["wt", "mat", "cannon"], 4),
        "skeleton": near(["th", "inferno", "eagle"], 7),
        "tornado": near(["th"], 6),
        "giga": near(["th", "inferno"], 6),
    }
    sk_air = bp.skeleton_air
    for key, n in TRAP_INVENTORY[bp.town_hall].items():
        size = 2 if key in ("giant", "giga") else 1
        spots = plan[key]
        placed = 0
        used = []
        for x, y in spots:
            if placed >= n:
                break
            if any(abs(x - ux) + abs(y - uy) < 3 for ux, uy in used):
                continue
            if board.fits(x, y, size):
                board.take(x, y, size)
                mode = None
                if key == "skeleton":
                    mode = "air" if sk_air > 0 else "ground"
                    sk_air -= 1
                lay.traps.append(TrapPlacement(key, x, y, mode))
                used.append((x, y))
                placed += 1
        while placed < n:
            x, y = rng.randrange(VILLAGE), rng.randrange(VILLAGE)
            if board.fits(x, y, size):
                board.take(x, y, size)
                mode = None
                if key == "skeleton":  # same air/ground split as the planned spots
                    mode = "air" if sk_air > 0 else "ground"
                    sk_air -= 1
                lay.traps.append(TrapPlacement(key, x, y, mode))
                placed += 1
