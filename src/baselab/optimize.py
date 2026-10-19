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

import math
import os
import random
import time
from dataclasses import dataclass

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
        per = float(os.environ.get("BASELAB_HOLE_PENALTY") or (0.25 if mode == "ranked" else 0.8))
        pen = hole_tiles(layout) * per
    if mode == "ranked":
        # expected trophies kept, tie-broken by lower destruction conceded
        return ev.ranked_trophies - 0.02 * ev.avg_destruction - pen
    # war: avoid three stars first, then stars, then destruction
    return 100.0 * (1.0 - ev.three_star_rate) - 10.0 * ev.avg_stars - 0.05 * ev.avg_destruction - pen


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


FILLERS = {"gm", "ec", "dd", "camp", "barracks", "dbarracks", "sf", "dsf", "lab", "workshop", "pethouse", "smith", "herohall", "helper", "bob", "gs", "es", "crafting"}


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


def _rewire(new: Layout, rng: random.Random):
    """Freeform wall move: take a short stretch out of a wall run and use
    those walls to build a new straight wall from one wall to another through
    open ground (splitting a compartment). Merges, splits and reshapes
    compartments without any style template."""
    runs = _wall_runs(new.walls)
    if not runs:
        return None
    run, _axis = rng.choice(runs)
    n = rng.randint(2, min(7, len(run)))
    a = rng.randrange(0, len(run) - n + 1)
    cut = set(run[a:a + n])
    walls = new.walls - cut
    occ = _occupied(new) - cut
    budget = WALL_COUNT - len(walls)
    wl = sorted(walls)
    for _ in range(120):
        wx, wy = rng.choice(wl)
        dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        seg = []
        x, y = wx + dx, wy + dy
        while 0 <= x < VILLAGE and 0 <= y < VILLAGE and (x, y) not in occ and len(seg) <= budget:
            seg.append((x, y))
            x, y = x + dx, y + dy
        if (x, y) in walls and 2 <= len(seg) <= budget and set(seg) != cut:
            new.walls = walls | set(seg)
            return f"rewire wall ({n} out, {len(seg)} in)"
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
            run = run[a:a + rng.randint(3, min(8, len(run) - a))]
        d = rng.choice((-1, 1, -2, 2))
        shift = (0, d) if axis == "x" else (d, 0)
        rest = new.walls - set(run)
        occ = _occupied(new) - set(run)
        moved = [(x + shift[0], y + shift[1]) for x, y in run]
        if all(0 <= x < VILLAGE and 0 <= y < VILLAGE and (x, y) not in occ for x, y in moved):
            new.walls = rest | set(moved)
            return f"wall segment ({len(run)}) shift"
        return None
    if r < 0.65:
        # move a defense together with its neighbours (a compartment's contents)
        defs = [i for i, b in enumerate(new.buildings) if BUILDING_TYPES[b.key].kind == "defense"]
        if not defs:
            return None
        c = new.buildings[rng.choice(defs)]
        cx, cy = c.x + c.size / 2, c.y + c.size / 2
        group = [i for i, b in enumerate(new.buildings) if abs(b.x + b.size / 2 - cx) <= 4 and abs(b.y + b.size / 2 - cy) <= 4]
        dx, dy = rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2), (1, 1), (-1, -1)])
        occ = set(new.walls)
        for i, b in enumerate(new.buildings):
            if i not in group:
                occ.update(b.tiles())
        for t in new.traps:
            occ.update(t.tiles())
        placed = set()
        for i in group:
            b = new.buildings[i]
            tiles = {(b.x + dx + ox, b.y + dy + oy) for ox in range(b.size) for oy in range(b.size)}
            if any(not (0 <= x < VILLAGE and 0 <= y < VILLAGE) for x, y in tiles) or tiles & occ or tiles & placed:
                return None
            placed |= tiles
        for i in group:
            new.buildings[i].x += dx
            new.buildings[i].y += dy
        return f"cluster shift ({len(group)}) around {c.key}"
    if r < 0.85:
        # relocate one defense anywhere it fits (big jump)
        defs = [i for i, b in enumerate(new.buildings) if BUILDING_TYPES[b.key].kind == "defense"]
        i = rng.choice(defs)
        b = new.buildings[i]
        occ = _occupied(new, skip_building=i)
        for _ in range(60):
            x, y = rng.randrange(0, VILLAGE - b.size + 1), rng.randrange(0, VILLAGE - b.size + 1)
            if _fits(occ, x, y, b.size):
                b.x, b.y = x, y
                return f"relocate {b.key}"
        return None
    # swap the Town Hall with another 4x4 building
    th = next((b for b in new.buildings if b.key == "th"), None)
    others = [b for b in new.buildings if b.size == th.size and b.key != "th"] if th else []
    if not others:
        return None
    o = rng.choice(others)
    th.x, o.x = o.x, th.x
    th.y, o.y = o.y, th.y
    return f"town hall <-> {o.key}"


# ------------------------------------------------------- attack-aware moves

STRONG = {"inferno", "mono", "scatter", "xbow", "eagle", "mat", "ric", "wt", "bt", "ad", "st", "crafting", "mortar", "sweeper"}
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
        kind = "air" if t.key in AIR_TRAPS or (t.key == "skeleton" and t.mode == "air") else "ground"
        hot = diag.hot_tiles(kind, 60)
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
        others = [b for b in new.buildings if b.size == d.size and b.key not in STRONG and b.key != "th"]
        if not others:
            return None
        o = max(rng.sample(others, min(10, len(others))), key=lambda b: _heat(diag, *_centre(b)))
        if _heat(diag, *_centre(o)) <= _heat(diag, *_centre(d)):
            return None
        _swap(d, o)
        return f"guided {d.key} to hot zone"
    if r < 0.7:
        # the defense the attacks strip first trades places with a same-size
        # building that usually survives
        if not diag.early:
            return None
        idx = [i for i, b in enumerate(new.buildings) if b.key in STRONG and diag.early.get(i, 0) > 0]
        if not idx:
            return None
        i = rng.choices(idx, [diag.early[i] for i in idx])[0]
        d = new.buildings[i]
        others = [j for j, b in enumerate(new.buildings) if b.size == d.size and b.key not in STRONG and b.key != "th"]
        if not others:
            return None
        j = min(rng.sample(others, min(10, len(others))), key=lambda j: diag.early.get(j, 0.0))
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
    if WALL_COUNT - len(walls) < 3:
        runs = _wall_runs(walls)
        if not runs:
            return None

        def quiet(run):
            return sum(diag.wall_heat.get(t, 0.0) for t in run) / len(run) + 0.02 * _heat(diag, run[len(run) // 2][0], run[len(run) // 2][1], 3)

        run, _ = rng.choice(sorted(runs, key=lambda ra: quiet(ra[0]))[:5])
        n = rng.randint(3, min(6, len(run)))
        a = rng.randrange(0, len(run) - n + 1)
        removed = set(run[a:a + n])
        walls -= removed
    budget = WALL_COUNT - len(walls)
    occ = _occupied(new) - removed
    d0 = math.hypot(bx - tx, by - ty)
    anchors = [w for w in walls if max(abs(w[0] - bx), abs(w[1] - by)) <= 4 and math.hypot(w[0] - tx, w[1] - ty) <= d0 + 1]
    if not anchors:
        return None
    for _ in range(80):
        wx, wy = rng.choice(anchors)
        dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        seg = []
        x, y = wx + dx, wy + dy
        while 0 <= x < VILLAGE and 0 <= y < VILLAGE and (x, y) not in occ and (x, y) not in walls and len(seg) <= budget:
            seg.append((x, y))
            x, y = x + dx, y + dy
        if (x, y) in walls and 2 <= len(seg) <= budget:
            mx = sum(p[0] for p in seg) / len(seg)
            my = sum(p[1] for p in seg) / len(seg)
            if math.hypot(mx - bx, my - by) <= 6:
                new.walls = walls | set(seg)
                return f"guided wall at breach ({len(removed)} out, {len(seg)} in)"
    return None


def mutate(lay: Layout, rng: random.Random, diag=None) -> tuple[Layout, str]:
    new = lay.copy()
    if diag is not None and rng.random() < GUIDED_P:
        desc = guided_move(new, rng, diag)
        if desc:
            return new, desc
        new = lay.copy()
    if rng.random() < 0.25:
        desc = _design_move(new, rng)
        if desc:
            return new, desc
        new = lay.copy()
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
        defs = [b for b in new.buildings if BUILDING_TYPES[b.key].kind in ("defense", "townhall")]
        for _ in range(30):
            d = rng.choice(defs)
            x = d.x + rng.randint(-3, d.size + 2)
            y = d.y + rng.randint(-3, d.size + 2)
            if _fits(occ, x, y, t.size):
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
            "firespitter": dirs,
        }
        if new.town_hall >= 18 and rng.random() < 0.15:
            new.guardian = rng.choice([g for g in ("Longshot", "Smasher", "Logger") if g != new.guardian])
            return new, f"guardian {new.guardian}"
        cands = [b for b in new.buildings if b.key in options]
        b = rng.choice(cands)
        b.mode = rng.choice([m for m in options[b.key] if m != b.mode])
        return new, f"mode {b.key}={b.mode}"
    if r < 0.92:
        # skeleton trap air/ground or CC composition tweak
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


def anneal(start: Candidate, scenarios, mode: str, *, steps=300, seed=0, temp0=0.6, log=print, time_budget=None, validate=None,
           guide=None, guide_every=25) -> Candidate:
    """Simulated annealing. With `validate` (a second, independent scenario
    set), a new best is only kept if it also beats the current best there,
    so a lucky draw on the search scenarios cannot become the answer."""
    rng = random.Random(seed)
    cur = start
    best = start
    best_val = objective(evaluate(start.layout, validate), mode, start.layout) if validate else None
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
        if sc >= cur.score or (temp > 0 and rng.random() < math.exp((sc - cur.score) / max(1e-6, temp))):
            cur = Candidate(cand_layout, sc, ev)
            accepted += 1
            if sc > best.score:
                if validate:
                    v = objective(evaluate(cand_layout, validate), mode, cand_layout)
                    if v <= best_val:
                        log(f"  step {step:4d} {desc:28s} -> {sc:7.2f}  (rejected: validation {v:.2f} <= {best_val:.2f})")
                        continue
                    best_val = v
                best = cur
                diag = None if guide else diag
                log(f"  step {step:4d} {desc:28s} -> {sc:7.2f}  {ev.summary()}" + (f"  validation {best_val:.2f}" if validate else ""))
    log(f"  annealing done: {accepted} accepted, best {best.score:.2f}")
    return best
