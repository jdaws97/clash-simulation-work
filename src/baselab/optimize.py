"""Base-layout search.

Two stages:

1. **Design screen** - many random ``Blueprint`` designs are built and scored
   on a cheap scenario set; the best few survive.
2. **Local search** - each survivor is refined by hill climbing with
   occasional uphill-tolerant moves (simulated annealing). Moves swap
   same-size buildings, nudge buildings, move traps, change defense modes and
   shift wall tiles. Scenarios are fixed during a run (common random numbers),
   and the winner is re-scored on a larger held-out scenario set to catch
   overfitting to particular approach angles.
"""

from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations_with_replacement
from pathlib import Path

from .evaluate import Evaluation, evaluate
from .generator import build, random_blueprint
from .layout import Layout, Placement
from .mechanics import WALL_COUNT, BUILDING_TYPES, VILLAGE

SWAPPABLE_KINDS = {"defense", "resource", "army", "townhall", "castle", "other"}


def hole_tiles(layout) -> int:
    """Deployable tiles enclosed by walls (gaps wider than two tiles)."""
    from .deploy import inside_holes

    return sum(len(h) for h in inside_holes(layout))


def objective(ev: Evaluation, mode: str, layout=None) -> float:
    """Higher is better for the defender. Interior drop holes are penalised
    on top of the attackers exploiting them in the battles, so the search
    never trades a hole for a lucky scenario set."""
    pen = 0.0
    if layout is not None:
        # BASELAB_HOLE_PENALTY overrides the per-tile penalty (the user wants
        # no drop pockets at all: overnight searches set it high)
        per = float(
            os.environ.get("BASELAB_HOLE_PENALTY")
            or (0.25 if mode == "ranked" else 0.8)
        )
        pen = hole_tiles(layout) * per
    if mode == "ranked":
        # data/wiki/text/Ranked_Battles.txt:45: destruction only breaks ties.
        # At 0..100%, this costs at most 0.005 trophies, below a 0.01 gap.
        return ev.ranked_trophies - 0.00005 * ev.avg_destruction - pen
    # war: avoid three stars first, then stars, then destruction
    return (
        100.0 * (1.0 - ev.three_star_rate)
        - 10.0 * ev.avg_stars
        - 0.05 * ev.avg_destruction
        - pen
    )


# ------------------------------------------------------------------ moves


def _occupied(lay: Layout, skip_building=None, skip_trap=None):
    occ = set(lay.walls)
    for i, b in enumerate(lay.buildings):
        if i != skip_building:
            occ.update(b.tiles())
    for i, t in enumerate(lay.traps):
        if i != skip_trap:
            occ.update(t.tiles())
    return occ


def _fits(occ, x, y, s):
    if x < 0 or y < 0 or x + s > VILLAGE or y + s > VILLAGE:
        return False
    return all((x + dx, y + dy) not in occ for dx in range(s) for dy in range(s))


FILLERS = {
    "gm",
    "ec",
    "dd",
    "camp",
    "barracks",
    "dbarracks",
    "sf",
    "dsf",
    "lab",
    "workshop",
    "pethouse",
    "smith",
    "herohall",
    "helper",
    "bob",
    "gs",
    "es",
    "crafting",
}


def _fill_hole(new: Layout, rng: random.Random):
    """Move a resource/army building into an interior drop hole (real bases
    plug gaps wider than two tiles with collectors, camps and huts)."""
    from .deploy import inside_holes

    holes = inside_holes(new)
    if not holes:
        return None
    hole = rng.choice(holes[:3])
    tx, ty = rng.choice(sorted(hole))
    cands = [i for i, b in enumerate(new.buildings) if b.key in FILLERS]
    rng.shuffle(cands)
    for i in cands[:12]:
        b = new.buildings[i]
        occ = _occupied(new, skip_building=i)
        s = b.size
        for dx in range(-s + 1, 1):
            for dy in range(-s + 1, 1):
                if _fits(occ, tx + dx, ty + dy, s):
                    b.x, b.y = tx + dx, ty + dy
                    return f"fill hole {b.key}"
    return None


def _wall_runs(walls):
    """Straight wall runs (length >= 3) as (tiles, axis) with axis 'x' or 'y'."""
    runs = []
    for axis in ("x", "y"):
        seen = set()
        for t in sorted(walls):
            if (t, axis) in seen:
                continue
            step = (1, 0) if axis == "x" else (0, 1)
            if (t[0] - step[0], t[1] - step[1]) in walls:
                continue
            run = [t]
            while (run[-1][0] + step[0], run[-1][1] + step[1]) in walls:
                run.append((run[-1][0] + step[0], run[-1][1] + step[1]))
            for r in run:
                seen.add((r, axis))
            if len(run) >= 3:
                runs.append((run, axis))
    return runs


def _keep_count(cut_run, seg, n_cut):
    """Walls a move took out of `cut_run` (in run order) that go back so the
    wall count is unchanged: every wall must stay placed. The new segment may
    reuse cut tiles; the rest of the shortfall is refilled from one end of
    the cut, leaving the opening at the other end."""
    seg = set(seg)
    short = n_cut - len(seg)
    if short <= 0:
        return set()
    return set([t for t in cut_run if t not in seg][:short])


def _rewire(new: Layout, rng: random.Random):
    """Freeform wall move: take a short stretch out of a wall run and use
    those walls to build a new straight wall from one wall to another through
    open ground (splitting a compartment). Merges, splits and reshapes
    compartments without any style template. The wall count never drops:
    walls the new segment does not use go back into the cut."""
    runs = _wall_runs(new.walls)
    if not runs:
        return None
    run, _axis = rng.choice(runs)
    n = rng.randint(2, min(7, len(run)))
    a = rng.randrange(0, len(run) - n + 1)
    cut_run = run[a : a + n]
    cut = set(cut_run)
    walls = new.walls - cut
    occ = _occupied(new) - cut
    budget = WALL_COUNT - len(walls)
    wl = sorted(walls)
    for _ in range(120):
        wx, wy = rng.choice(wl)
        dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        seg = []
        x, y = wx + dx, wy + dy
        while (
            0 <= x < VILLAGE
            and 0 <= y < VILLAGE
            and (x, y) not in occ
            and len(seg) <= budget
        ):
            seg.append((x, y))
            x, y = x + dx, y + dy
        if (x, y) in walls and 2 <= len(seg) <= budget and set(seg) != cut:
            back = _keep_count(cut_run, seg, n)
            if set(seg) | back == cut:
                continue  # the same walls again
            new.walls = walls | set(seg) | back
            return f"rewire wall ({n - len(back)} out, {len(seg)} in)"
    return None


def _design_move(new: Layout, rng: random.Random):
    """Base-design scale moves: shift a whole wall segment, rewire walls,
    shift a cluster of buildings, relocate a building anywhere, or move the
    Town Hall."""
    r = rng.random()
    if 0.25 <= r < 0.4:
        return _rewire(new, rng)
    if r < 0.25:
        runs = _wall_runs(new.walls)
        if not runs:
            return None
        run, axis = rng.choice(runs)
        # optionally only part of a long run (a segment between corners)
        if len(run) > 6 and rng.random() < 0.5:
            a = rng.randrange(0, len(run) - 3)
            run = run[a : a + rng.randint(3, min(8, len(run) - a))]
        d = rng.choice((-1, 1, -2, 2))
        shift = (0, d) if axis == "x" else (d, 0)
        rest = new.walls - set(run)
        occ = _occupied(new) - set(run)
        moved = [(x + shift[0], y + shift[1]) for x, y in run]
        if all(
            0 <= x < VILLAGE and 0 <= y < VILLAGE and (x, y) not in occ
            for x, y in moved
        ):
            new.walls = rest | set(moved)
            return f"wall segment ({len(run)}) shift"
        return None
    if r < 0.65:
        # move a defense together with its neighbours (a compartment's contents)
        defs = [
            i
            for i, b in enumerate(new.buildings)
            if BUILDING_TYPES[b.key].kind == "defense"
        ]
        if not defs:
            return None
        c = new.buildings[rng.choice(defs)]
        cx, cy = c.x + c.size / 2, c.y + c.size / 2
        group = [
            i
            for i, b in enumerate(new.buildings)
            if abs(b.x + b.size / 2 - cx) <= 4 and abs(b.y + b.size / 2 - cy) <= 4
        ]
        dx, dy = rng.choice(
            [
                (1, 0),
                (-1, 0),
                (0, 1),
                (0, -1),
                (2, 0),
                (-2, 0),
                (0, 2),
                (0, -2),
                (1, 1),
                (-1, -1),
            ]
        )
        occ = set(new.walls)
        for i, b in enumerate(new.buildings):
            if i not in group:
                occ.update(b.tiles())
        for t in new.traps:
            occ.update(t.tiles())
        placed = set()
        for i in group:
            b = new.buildings[i]
            tiles = {
                (b.x + dx + ox, b.y + dy + oy)
                for ox in range(b.size)
                for oy in range(b.size)
            }
            if (
                any(not (0 <= x < VILLAGE and 0 <= y < VILLAGE) for x, y in tiles)
                or tiles & occ
                or tiles & placed
            ):
                return None
            placed |= tiles
        for i in group:
            new.buildings[i].x += dx
            new.buildings[i].y += dy
        return f"cluster shift ({len(group)}) around {c.key}"
    if r < 0.85:
        # relocate one defense anywhere it fits (big jump)
        defs = [
            i
            for i, b in enumerate(new.buildings)
            if BUILDING_TYPES[b.key].kind == "defense"
        ]
        i = rng.choice(defs)
        b = new.buildings[i]
        occ = _occupied(new, skip_building=i)
        for _ in range(60):
            x, y = rng.randrange(0, VILLAGE - b.size + 1), rng.randrange(
                0, VILLAGE - b.size + 1
            )
            if _fits(occ, x, y, b.size):
                b.x, b.y = x, y
                return f"relocate {b.key}"
        return None
    # swap the Town Hall with another 4x4 building
    th = next((b for b in new.buildings if b.key == "th"), None)
    others = (
        [b for b in new.buildings if b.size == th.size and b.key != "th"] if th else []
    )
    if not others:
        return None
    o = rng.choice(others)
    th.x, o.x = o.x, th.x
    th.y, o.y = o.y, th.y
    return f"town hall <-> {o.key}"


# ------------------------------------------------------- attack-aware moves

STRONG = {
    "inferno",
    "mono",
    "scatter",
    "xbow",
    "eagle",
    "mat",
    "ric",
    "wt",
    "bt",
    "ad",
    "st",
    "crafting",
    "mortar",
    "sweeper",
}
AIR_TRAPS = {"airbomb", "seeking"}
GUIDED_P = 0.45  # share of moves aimed by the battle traces when a diagnosis exists


def _heat(diag, cx, cy, r=5.0):
    h = 0.0
    for c in (diag.ground, diag.air):
        for (x, y), v in c.items():
            if abs(x + 0.5 - cx) <= r and abs(y + 0.5 - cy) <= r:
                h += v
    return h


def _centre(b):
    return b.x + b.size / 2.0, b.y + b.size / 2.0


def _swap(a, b):
    a.x, b.x = b.x, a.x
    a.y, b.y = b.y, a.y


def guided_move(new: Layout, rng: random.Random, diag):
    """Moves aimed at where the winning attacks actually went (diagnose.py):
    traps onto the paths troops walk, strong defenses into the busy zones,
    defenses that fall first swapped deeper, and walls doubled behind the
    breaches the attacks keep making (paid for by the quietest wall run)."""
    r = rng.random()
    if r < 0.3 and new.traps:
        i = rng.randrange(len(new.traps))
        t = new.traps[i]
        hot = (
            diag.trap_tiles(t.key, getattr(t, "mode", None), 60)
            if hasattr(diag, "trap_tiles")
            else diag.hot_tiles(
                (
                    "air"
                    if t.key in AIR_TRAPS or (t.key == "skeleton" and t.mode == "air")
                    else "ground"
                ),
                60,
            )
        )
        if not hot:
            return None
        tiles, weights = zip(*hot)
        occ = _occupied(new, skip_trap=i)
        for _ in range(25):
            x, y = rng.choices(tiles, weights)[0]
            x -= rng.randint(0, t.size - 1)
            y -= rng.randint(0, t.size - 1)
            if (x, y) != (t.x, t.y) and _fits(occ, x, y, t.size):
                t.x, t.y = x, y
                return f"guided trap {t.key}"
        return None
    if r < 0.55:
        # a strong defense idling in a quiet zone trades places with a
        # same-size building where the attacks go
        defs = [b for b in new.buildings if b.key in STRONG]
        if not defs:
            return None
        sample = rng.sample(defs, min(6, len(defs)))
        d = min(sample, key=lambda b: _heat(diag, *_centre(b)))
        others = [
            b
            for b in new.buildings
            if b.size == d.size and b.key not in STRONG and b.key != "th"
        ]
        if not others:
            return None
        o = max(
            rng.sample(others, min(10, len(others))),
            key=lambda b: _heat(diag, *_centre(b)),
        )
        if _heat(diag, *_centre(o)) <= _heat(diag, *_centre(d)):
            return None
        _swap(d, o)
        return f"guided {d.key} to hot zone"
    if r < 0.7:
        # the defense the attacks strip first trades places with a same-size
        # building that usually survives
        if not diag.early:
            return None
        idx = [
            i
            for i, b in enumerate(new.buildings)
            if b.key in STRONG and diag.early.get(i, 0) > 0
        ]
        if not idx:
            return None
        i = rng.choices(idx, [diag.early[i] for i in idx])[0]
        d = new.buildings[i]
        others = [
            j
            for j, b in enumerate(new.buildings)
            if b.size == d.size and b.key not in STRONG and b.key != "th"
        ]
        if not others:
            return None
        j = min(
            rng.sample(others, min(10, len(others))),
            key=lambda j: diag.early.get(j, 0.0),
        )
        if diag.early.get(j, 0.0) >= diag.early[i]:
            return None
        _swap(d, new.buildings[j])
        return f"guided protect {d.key}"
    # double the wall behind a breach, paid for by the quietest wall run
    hot = diag.hot_tiles("wall", 30)
    th = next((b for b in new.buildings if b.key == "th"), None)
    if not hot or th is None:
        return None
    tiles, weights = zip(*hot)
    bx, by = rng.choices(tiles, weights)[0]
    tx, ty = _centre(th)
    walls = set(new.walls)
    removed: set = set()
    removed_run: list = []
    if WALL_COUNT - len(walls) < 3:
        runs = _wall_runs(walls)
        if not runs:
            return None

        def quiet(run):
            return sum(diag.wall_heat.get(t, 0.0) for t in run) / len(
                run
            ) + 0.02 * _heat(diag, run[len(run) // 2][0], run[len(run) // 2][1], 3)

        run, _ = rng.choice(sorted(runs, key=lambda ra: quiet(ra[0]))[:5])
        n = rng.randint(3, min(6, len(run)))
        a = rng.randrange(0, len(run) - n + 1)
        removed_run = run[a : a + n]
        removed = set(removed_run)
        walls -= removed
    budget = WALL_COUNT - len(walls)
    occ = _occupied(new) - removed
    d0 = math.hypot(bx - tx, by - ty)
    anchors = [
        w
        for w in walls
        if max(abs(w[0] - bx), abs(w[1] - by)) <= 4
        and math.hypot(w[0] - tx, w[1] - ty) <= d0 + 1
    ]
    if not anchors:
        return None
    for _ in range(80):
        wx, wy = rng.choice(anchors)
        dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        seg = []
        x, y = wx + dx, wy + dy
        while (
            0 <= x < VILLAGE
            and 0 <= y < VILLAGE
            and (x, y) not in occ
            and (x, y) not in walls
            and len(seg) <= budget
        ):
            seg.append((x, y))
            x, y = x + dx, y + dy
        if (x, y) in walls and 2 <= len(seg) <= budget:
            mx = sum(p[0] for p in seg) / len(seg)
            my = sum(p[1] for p in seg) / len(seg)
            if math.hypot(mx - bx, my - by) <= 6:
                # walls the new segment does not use go back (none are lost)
                back = _keep_count(removed_run, seg, len(removed_run))
                new.walls = walls | set(seg) | back
                return f"guided wall at breach ({len(removed) - len(back)} out, {len(seg)} in)"
    return None


def mutate(lay: Layout, rng: random.Random, diag=None) -> tuple[Layout, str]:
    new = lay.copy()
    _repair_gears(new)
    setup = rng.random()
    desc = None
    if setup < 0.03:
        desc = _hero_move(new, rng)
    elif setup < 0.06:
        desc = _cc_move(new, rng)
    elif setup < 0.09:
        desc = _gear_move(new, rng)
    if desc:
        return new, desc
    if diag is not None and rng.random() < GUIDED_P:
        desc = guided_move(new, rng, diag)
        if desc:
            return new, desc
        new = lay.copy()
        _repair_gears(new)
    if rng.random() < 0.25:
        desc = _design_move(new, rng)
        if desc:
            return new, desc
        new = lay.copy()
        _repair_gears(new)
    if rng.random() < 0.12:
        desc = _fill_hole(new, rng)
        if desc:
            return new, desc
    r = rng.random()
    if r < 0.35:
        # swap two buildings of the same footprint (keeps the layout legal)
        by_size: dict = {}
        for i, b in enumerate(new.buildings):
            if b.key != "th":
                by_size.setdefault(b.size, []).append(i)
        size = rng.choice([s for s, v in by_size.items() if len(v) >= 2])
        i, j = rng.sample(by_size[size], 2)
        a, b = new.buildings[i], new.buildings[j]
        if a.key == b.key:
            return new, "noop"
        a.x, b.x = b.x, a.x
        a.y, b.y = b.y, a.y
        return new, f"swap {a.key}<->{b.key}"
    if r < 0.55:
        # nudge one building to a nearby free spot
        i = rng.randrange(len(new.buildings))
        b = new.buildings[i]
        occ = _occupied(new, skip_building=i)
        for _ in range(20):
            x = b.x + rng.randint(-3, 3)
            y = b.y + rng.randint(-3, 3)
            if (x, y) != (b.x, b.y) and _fits(occ, x, y, b.size):
                b.x, b.y = x, y
                return new, f"move {b.key}"
        return new, "noop"
    if r < 0.75:
        # move a trap near a random defense
        i = rng.randrange(len(new.traps))
        t = new.traps[i]
        occ = _occupied(new, skip_trap=i)
        defs = [
            b
            for b in new.buildings
            if BUILDING_TYPES[b.key].kind in ("defense", "townhall")
        ]
        for _ in range(30):
            d = rng.choice(defs)
            x = d.x + rng.randint(-3, d.size + 2)
            y = d.y + rng.randint(-3, d.size + 2)
            if (x, y) != (t.x, t.y) and _fits(occ, x, y, t.size):
                t.x, t.y = x, y
                return new, f"trap {t.key}"
        return new, "noop"
    if r < 0.85:
        # flip a defense mode
        dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        options = {
            "inferno": ["single", "multi"],
            "xbow": ["ground", "both"],
            # the Earthquake mode needs Spell Tower level 4 (TH17+)
            "st": ["rage", "poison", "invis"] + (["eq"] if new.town_hall >= 17 else []),
            "sweeper": dirs,
            "mgt": ["fast", "long"],
            "crafting": ["cake", "candle", "hunter"],
            # output/research/usage/firespitter.md: facing changes in 90-degree steps.
            # https://clash-of-clans.1337wiki.com/firespitter/
            "firespitter": ["N", "E", "S", "W"],
        }
        if new.town_hall >= 18 and rng.random() < 0.15:
            new.guardian = rng.choice(
                [g for g in ("Longshot", "Smasher", "Logger") if g != new.guardian]
            )
            return new, f"guardian {new.guardian}"
        cands = [b for b in new.buildings if b.key in options]
        b = rng.choice(cands)
        b.mode = rng.choice([m for m in options[b.key] if m != b.mode])
        return new, f"mode {b.key}={b.mode}"
    if r < 0.92:
        # skeleton trap air/ground (CC setup has its own move above)
        sk = [t for t in new.traps if t.key == "skeleton"]
        if sk:
            t = rng.choice(sk)
            t.mode = "air" if t.mode != "air" else "ground"
            return new, "skeleton mode"
        return new, "noop"
    # move one wall tile to a free tile adjacent to another wall
    walls = list(new.walls)
    src = rng.choice(walls)
    occ = _occupied(new)
    for _ in range(40):
        anchor = rng.choice(walls)
        dx, dy = rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
        dst = (anchor[0] + dx, anchor[1] + dy)
        if 0 <= dst[0] < VILLAGE and 0 <= dst[1] < VILLAGE and dst not in occ:
            new.walls.discard(src)
            new.walls.add(dst)
            return new, "wall"
    return new, "noop"


# Defending Clan Castle compositions top builders use (docs/BASE_DESIGN_PRINCIPLES.md 5.2,
# Blueprint CoC CC guide 2026-04-15 and TH16-18 legend bases), plus the user's own
CC_OPTIONS = [
    (
        "user",
        ["Dragon", "Dragon", "Headhunter", "Archer", "Archer", "Archer", "Archer"],
    ),
    ("furnace-2ice", ["Furnace", "Ice Golem", "Ice Golem", "Archer", "Archer"]),
    ("3ice", ["Ice Golem"] * 3 + ["Archer"] * 5),
    (
        "furnace-rockets-ice-hh",
        ["Furnace", "Rocket Balloon", "Rocket Balloon", "Ice Golem", "Headhunter"],
    ),
    ("2ice-furnace-hh", ["Ice Golem", "Ice Golem", "Furnace", "Headhunter", "Archer"]),
    ("lava-furnace", ["Lava Hound", "Furnace", "Archer", "Archer", "Archer"]),
]


@lru_cache(maxsize=1)
def _account_setup():
    root = Path(__file__).resolve().parents[2] / "data"
    own = json.loads((root / "your-levels.json").read_text())
    live_path = root / "live" / "player-latest.json"
    live = json.loads(live_path.read_text()) if live_path.exists() else {}
    return own, live


def _hero_move(new: Layout, rng: random.Random):
    from .engine import stats

    own, live = _account_setup()
    levels = dict(own["hero_levels"])
    levels.update(
        (hero["name"], hero["level"])
        for hero in live.get("heroes", [])
        if hero.get("village") == "home"
    )
    hall = new.levels.get("herohall", own["levels"]["herohall"])
    # data/wiki/text/Hero_Hall.txt:20,23-28: four independent defensive slots;
    # upgrades do not exclude heroes from ranked or war defense.
    available = {}
    for name in sorted(levels):
        level = new.hero_levels.get(name, levels[name])
        maximum = stats.max_level(name, new.town_hall)
        if not isinstance(level, int) or not 0 < level <= (maximum or 0):
            continue
        required_hall = stats.get(name, level, "Hero Hall Level Required", default=1)
        if required_hall <= hall:
            available[name] = level
    slots = min(
        sum(b.key == "banner" for b in new.buildings),
        int(stats.get("Hero Hall", hall, "Hero Slots")),
        len(available),
    )
    if not slots:
        return None
    heroes = list(dict.fromkeys(h for h in new.heroes if h in available))[:slots]
    heroes += [h for h in available if h not in heroes][: slots - len(heroes)]
    choices = []
    for i in range(slots):
        for j in range(i + 1, slots):
            changed = list(heroes)
            changed[i], changed[j] = changed[j], changed[i]
            choices.append(changed)
        for name in available:
            if name not in heroes:
                changed = list(heroes)
                changed[i] = name
                choices.append(changed)
    if heroes != new.heroes:
        choices.append(heroes)
    if not choices:
        return None
    # src/baselab/engine/battle.py:298-300: heroes zip with banner list order.
    new.heroes = rng.choice(choices)
    new.hero_levels.update(available)
    return "heroes " + "/".join(new.heroes)


@lru_cache(maxsize=None)
def _cc_combinations(capacity: int):
    from .engine import stats

    names = sorted({name for _, troops in CC_OPTIONS for name in troops})
    housing = {}
    for name in names:
        attrs = stats.attrs(name)
        housing[name] = int(attrs.get("housing_ck") or attrs.get("housing") or 0)
        if housing[name] <= 0:
            raise ValueError(f"Missing defensive CC housing for {name}")
    options = []
    seen = set()

    def add(label, troops):
        key = tuple(sorted(troops))
        used = sum(housing[name] for name in troops)
        if key not in seen and 0 < used <= capacity:
            seen.add(key)
            options.append((label, tuple(troops)))

    for label, troops in CC_OPTIONS:
        add(label, troops)
    # data/registry.json: housing_ck; keep at most three non-Archer troops,
    # then fill with Archers. Only 83 mixtures plus the original six presets.
    core = [name for name in names if name != "Archer"]
    for count in range(1, 4):
        for troops in combinations_with_replacement(core, count):
            used = sum(housing[name] for name in troops)
            if used <= capacity:
                filler = (capacity - used) // housing["Archer"]
                add(" + ".join(troops), list(troops) + ["Archer"] * filler)
    return tuple(options)


def cc_presets(layout=None):
    """Small CC menu bounded by the account's and layout's Castle capacity."""
    from .engine import stats

    own, _ = _account_setup()
    level = own["levels"]["cc"]
    if layout is not None:
        if not any(b.key == "cc" for b in layout.buildings):
            return []
        level = min(level, layout.levels.get("cc", level))
        level = min(level, stats.max_level("Clan Castle", layout.town_hall))
    # data/your-levels.json: CC 11; data/registry.json: 50 housing.
    capacity = int(stats.get("Clan Castle", level, "Troop Capacity"))
    return [(name, list(troops)) for name, troops in _cc_combinations(capacity)]


def cc_entries(entries):
    """Expand supported CC entries to (name, optional level) pairs."""
    # engine/units.py: cargo_entries accepts names or {name/type, level, count}.
    troops = []
    for entry in entries:
        item = {"name": entry} if isinstance(entry, str) else entry
        name = item.get("name") or item["type"]
        for _ in range(int(item.get("count", 1))):
            troops.append((name, item.get("level")))
    return troops


def _cc_move(new: Layout, rng: random.Random):
    current = cc_entries(new.cc_troops)
    names = sorted(name for name, _ in current)
    options = [
        (name, troops) for name, troops in cc_presets(new) if sorted(troops) != names
    ]
    if not options:
        return None
    name, troops = rng.choice(options)
    # Wiki: Clan Castle, donated troops retain their levels (subject to its cap).
    levels = {}
    for troop, level in current:
        levels.setdefault(troop, []).append(level)
    used = {}
    new.cc_troops = []
    for troop in troops:
        known = levels.get(troop, [None])
        index = used.get(troop, 0)
        level = known[min(index, len(known) - 1)]
        used[troop] = index + 1
        new.cc_troops.append(
            {"name": troop, "level": level} if level is not None else troop
        )
    return f"cc {name}"


def _repair_gears(new: Layout):
    """Keep the first eligible geared copy in coordinate order, without RNG."""
    from .engine.specs import game_data

    own, _ = _account_setup()
    merged = any(b.key == "mgt" for b in new.buildings)
    for key in ("cannon", "at", "mortar"):
        active = sorted(
            (
                b
                for b in new.buildings
                if b.key == key and b.mode in ("geared", "fast", "burst")
            ),
            key=lambda b: (b.x, b.y),
        )
        if not active:
            continue
        level = new.levels.get(key, own["levels"][key])
        row = (
            game_data("buildings", BUILDING_TYPES[key].name, level)
            if isinstance(level, int)
            else {}
        )
        # game data v18.200.9: Cannon/Archer Tower/Mortar.GearUpCost first
        # appears at levels 7/10/8 -> lower levels cannot use geared weapons.
        allowed = (
            bool(row.get("GearUpLevelRequirement"))
            and int(row.get("GearUpCost") or 0) > 0
        )
        # Wiki: Cannon/Archer Tower, their geared copies merge into Multi-Gear Tower.
        if merged and key in ("cannon", "at"):
            allowed = False
        # Wiki: Archer Tower, "Like with other gear ups, only one" may be geared.
        for building in active[1:] if allowed else active:
            building.mode = "normal"


def _gear_move(new: Layout, rng: random.Random):
    from .engine.specs import game_data

    own, live = _account_setup()
    # data/live/player-latest.json:309-315: High Gear=3 proves all three owned.
    all_owned = any(
        a["name"] == "High Gear" and a.get("value", 0) >= 3
        for a in live.get("achievements", [])
    )
    options = []
    merged = any(b.key == "mgt" for b in new.buildings)
    for key in ("cannon", "at", "mortar"):
        if merged and key in ("cannon", "at"):
            continue
        copies = [b for b in new.buildings if b.key == key]
        active = [b for b in copies if b.mode in ("geared", "fast", "burst")]
        if len(active) > 1 or not (all_owned or active):
            continue
        level = new.levels.get(key, own["levels"][key])
        if not isinstance(level, int):
            continue
        row = game_data("buildings", BUILDING_TYPES[key].name, level)
        # buildings.csv: GearUpLevelRequirement is the Builder Base prerequisite;
        # GearUpCost first appears at home levels 7/10/8. Ownership proves the former.
        if not row.get("GearUpLevelRequirement") or not int(row.get("GearUpCost") or 0):
            continue
        for building in active or copies:
            options.append((building, "normal" if active else "geared"))
    if not options:
        return None
    building, mode = rng.choice(options)
    building.mode = mode
    return f"gear {building.key}@{building.x},{building.y}={building.mode}"


# ----------------------------------------------------------------- search


@dataclass
class Candidate:
    layout: Layout
    score: float
    ev: Evaluation


def screen(n: int, scenarios, mode: str, *, seed=0, log=print) -> list[Candidate]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        bp = random_blueprint(rng, seed=rng.randrange(10**6))
        try:
            lay = build(bp)
        except RuntimeError:
            continue
        lay.name = f"{mode}-design-{i}"
        ev = evaluate(lay, scenarios)
        out.append(Candidate(lay, objective(ev, mode, lay), ev))
        log(f"  design {i:3d}: score {out[-1].score:7.2f}  {ev.summary()}")
    out.sort(key=lambda c: -c.score)
    return out


def anneal(
    start: Candidate,
    scenarios,
    mode: str,
    *,
    steps=300,
    seed=0,
    temp0=0.6,
    log=print,
    time_budget=None,
    validate=None,
    guide=None,
    guide_every=25,
) -> Candidate:
    """Simulated annealing. With `validate` (a second, independent scenario
    set), a new best is only kept if it also beats the current best there,
    so a lucky draw on the search scenarios cannot become the answer."""
    rng = random.Random(seed)
    cur = start
    best = start
    best_val = (
        objective(evaluate(start.layout, validate), mode, start.layout)
        if validate
        else None
    )
    t_start = time.time()
    accepted = 0
    # attack-aware moves: trace battles on the current layout, refreshed
    # after every new best and every `guide_every` steps
    diag, diag_at = None, -1
    for step in range(steps):
        if time_budget and time.time() - t_start > time_budget:
            break
        if guide and (diag is None or step - diag_at >= guide_every):
            from .diagnose import diagnose

            diag, diag_at = diagnose(cur.layout, guide), step
        cand_layout, desc = mutate(cur.layout, rng, diag)
        if desc == "noop" or cand_layout.problems():
            continue
        ev = evaluate(cand_layout, scenarios)
        sc = objective(ev, mode, cand_layout)
        temp = temp0 * (1 - step / steps)
        if sc >= cur.score or (
            temp > 0 and rng.random() < math.exp((sc - cur.score) / max(1e-6, temp))
        ):
            cur = Candidate(cand_layout, sc, ev)
            accepted += 1
            if sc > best.score:
                if validate:
                    v = objective(evaluate(cand_layout, validate), mode, cand_layout)
                    if v <= best_val:
                        log(
                            f"  step {step:4d} {desc:28s} -> {sc:7.2f}  (rejected: validation {v:.2f} <= {best_val:.2f})"
                        )
                        continue
                    best_val = v
                best = cur
                diag = None if guide else diag
                log(
                    f"  step {step:4d} {desc:28s} -> {sc:7.2f}  {ev.summary()}"
                    + (f"  validation {best_val:.2f}" if validate else "")
                )
    log(f"  annealing done: {accepted} accepted, best {best.score:.2f}")
    return best
