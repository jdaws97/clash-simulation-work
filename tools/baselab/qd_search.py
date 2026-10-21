"""Quality-diversity base search (MAP-Elites): keep the best base of every
KIND, not one lineage descended from a few seed bases.

A base's kind is four layout descriptors, three bins each (81 cells):
  Town Hall zone (center / mid / edge, archetypes.th_zone),
  Eagle Artillery depth (core / middle / outer: share of buildings closer
    to the centroid than it, < 0.1 / < 0.3 / more),
  wall compartments of 4+ tiles (open <= 6 / 7-14 / 15+; ranked-funnel1
    has 3, generated originals 7-21),
  defense spread (mean defense distance from the centroid).
It starts from freshly generated originals only (no user or earlier bases):
the compartment generators plus unconventional ones (open cram, onion,
scatter; unconventional.py), so radically different designs compete too.
Each batch makes children by mutating elites, crossing elites of different
cells, and generating new originals; a child takes its cell if it beats the
cell's elite on the quick battle set (the same seeds for everyone). At the
end the best elites get the full battle set, then a hold-out comparison with
the reference bases.

Two-stage scoring: a quick 44-battle set prunes, an independent 176-battle
set decides (elites are compared on it). Run with BASELAB_HOLE_PENALTY=0 to
score pure defense trophies. --seed-files adds starting layouts.

Usage: python tools/baselab/qd_search.py --out output/qd --batches 30 [--batch 64] [--mode ranked] [--seed-files A.json ...]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.archetypes import compartments, design, th_zone  # noqa: E402
from baselab.evaluate import meta_scenarios, pool  # noqa: E402
from baselab.evolve import crossover  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.optimize import mutate  # noqa: E402
from baselab.render import render  # noqa: E402
from baselab.unconventional import STYLES, unconventional  # noqa: E402
from funnel import KINDS, eval_many, own_levels  # noqa: E402

DEF = {"inferno", "eagle", "scatter", "xbow", "mono", "ad", "mat", "ric", "wt", "bt", "mortar", "at", "cannon",
       "sweeper", "tesla", "st", "crafting"}


def descriptor(lay: Layout):
    bs = [b for b in lay.buildings if b.key not in ("wall",)]
    if not bs:
        return None
    cx = sum(b.x + b.size / 2 for b in bs) / len(bs)
    cy = sum(b.y + b.size / 2 for b in bs) / len(bs)

    def r(b):
        return math.hypot(b.x + b.size / 2 - cx, b.y + b.size / 2 - cy)

    dists = sorted(r(b) for b in bs)
    eagle = next((b for b in bs if b.key == "eagle"), None)
    if eagle is None:
        return None
    pct = sum(d < r(eagle) for d in dists) / len(dists)
    e = 0 if pct < 0.1 else 1 if pct < 0.3 else 2
    zone = {"center": 0, "mid": 1, "edge": 2}.get(th_zone(lay), 1)
    n = sum(len(c) >= 4 for c in compartments(lay.walls)[0])  # enclosed areas of 4+ tiles
    c = 0 if n <= 6 else 1 if n <= 14 else 2
    defs = [r(b) for b in bs if b.key in DEF]
    spread = sum(defs) / max(1, len(defs))
    s = 0 if spread < 11.3 else 1 if spread < 12.3 else 2
    return (zone, e, c, s)


def _child(args):
    """One child layout (json) from an op; runs in a worker."""
    op, seed, a_json, b_json = args
    rng = random.Random(seed)
    own = own_levels()
    try:
        if op == "new":
            if rng.random() < 0.35:
                lay = unconventional(rng.choice(STYLES), seed)  # open cram, onion, scatter
            else:
                lay = design(rng.choice(KINDS), seed, zone=rng.choice(["center", "mid", "edge"]))
        elif op == "cross":
            lay = crossover(Layout.from_json(a_json), Layout.from_json(b_json), rng)
            if lay is None:
                return None
        else:
            lay = Layout.from_json(a_json)
            for _ in range(rng.choice([1, 2, 3, 5, 8])):
                m, d = mutate(lay, rng)
                if d != "noop" and not m.problems():
                    lay = m
        if lay.problems():
            return None
        lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
        return lay.to_json()
    except (RuntimeError, ValueError, IndexError, KeyError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["ranked", "war"], default="ranked")
    ap.add_argument("--batches", type=int, default=30)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--init", type=int, default=192)
    ap.add_argument("--final", type=int, default=16, help="elites given the full battle set")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--margin", type=float, default=1.0, help="stage-1 slack below the elite's quick score")
    ap.add_argument("--seed-files", nargs="*", default=[], help="layouts to start from (e.g. digitized builder bases)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    quick = meta_scenarios(args.mode, 2 if args.mode == "ranked" else 4, (0,))
    # second stage: an independent, larger set (other seeds, other sides).
    # The quick set only prunes; a child takes a cell only on this score, so
    # a design that got lucky on 44 battles cannot win (the first run's
    # quick-set "best" of 11.1 trophies fell to 5.3 on the full set).
    confirm = meta_scenarios(args.mode, 4, (1, 2), angle_offset=math.pi / 4)
    archive: dict = {}  # cell -> (confirm score, layout_json, summary, quick score)
    t0 = time.time()
    log = open(out / "progress.log", "a", encoding="utf-8")

    def say(m):
        print(m, flush=True)
        log.write(m + "\n")
        log.flush()

    def offer(jsons):
        lays = [Layout.from_json(j) for j in jsons if j is not None]
        lays = [(l, descriptor(l)) for l in lays]
        lays = [(l, d) for l, d in lays if d is not None]
        if not lays:
            return 0
        scored = eval_many([l for l, _ in lays], quick, args.mode)
        # stage 1: a child goes on if its cell is empty or it comes within
        # `margin` of the elite's quick score
        keep = [(l, d, qs) for (l, d), (qs, _) in zip(lays, scored)
                if d not in archive or qs >= archive[d][3] - args.margin]
        if not keep:
            return 0
        full = eval_many([l for l, _, _ in keep], confirm, args.mode)
        won = 0
        for (l, d, qs), (cs, ev) in zip(keep, full):
            if d not in archive or cs > archive[d][0]:
                archive[d] = (cs, l.to_json(), ev.summary(), qs)
                won += 1
        return won

    jobs = [("new", args.seed * 1_000_000 + i, None, None) for i in range(args.init)]
    seeds_json = []
    own_lv = own_levels()
    for f in args.seed_files:
        l = Layout.load(Path(f))
        if l.problems():
            say(f"skipping seed {f}: {l.problems()[:3]}")
            continue
        l.levels, l.wall_level, l.hero_levels = dict(own_lv["levels"]), own_lv["wall_level"], dict(own_lv["hero_levels"])
        l.name = "seed-" + Path(f).stem
        seeds_json.append(l.to_json())
    won = offer(seeds_json + list(pool().map(_child, jobs, chunksize=4)))
    say(f"init: {len(archive)} cells filled ({won} entries) t={time.time() - t0:.0f}s")
    for bt in range(args.batches):
        cells = list(archive)
        jobs = []
        for i in range(args.batch):
            r = rng.random()
            seed = args.seed * 1_000_000 + 10_000 * (bt + 1) + i
            if r < 0.15:
                jobs.append(("new", seed, None, None))
            elif r < 0.45 and len(cells) > 1:
                a, b = rng.sample(cells, 2)
                jobs.append(("cross", seed, archive[a][1], archive[b][1]))
            else:
                # parents weighted toward the better elites, all cells still chosen
                ranked = sorted(cells, key=lambda c: -archive[c][0])
                c = ranked[min(int(rng.expovariate(1 / max(1.0, len(ranked) / 3))), len(ranked) - 1)]
                jobs.append(("mutate", seed, archive[c][1], None))
        won = offer(list(pool().map(_child, jobs, chunksize=4)))
        best = max(archive.values(), key=lambda v: v[0])
        say(f"batch {bt}: {won} improvements, {len(archive)} cells, best confirmed {best[0]:.2f} | {best[2]}  t={time.time() - t0:.0f}s")
        json.dump({str(k): v[:2] for k, v in archive.items()}, open(out / "archive.json", "w"))

    # full battle set for the best elites, then hold-out against the references
    full = meta_scenarios(args.mode, 8, (0, 1))
    top = sorted(archive.items(), key=lambda kv: -kv[1][0])[: args.final]
    lays = [Layout.from_json(v[1]) for _, v in top]
    for (cell, _), l in zip(top, lays):
        l.name = "qd-" + "".join(map(str, cell))
    scored = eval_many(lays, full, args.mode)
    order = sorted(zip(lays, scored), key=lambda x: -x[1][0])
    say("== full battle set (TH zone, Eagle depth, compartments, spread)")
    for l, (s, ev) in order:
        say(f"  {l.name}  {s:6.2f}  {ev.summary()}")
    # fresh battles: sides halfway between the full set's 8 (same angles
    # would repeat it; seed group 21 alone has group 1's skill and flank)
    hold = meta_scenarios(args.mode, 8, (21, 22, 23), angle_offset=math.pi / 8)
    own = own_levels()
    refs = []
    for f in [ROOT / "output/winners/ranked-funnel1.json", ROOT / "data/reference-bases/your-base.json"]:
        if f.exists():
            l = Layout.load(f)
            l.levels, l.wall_level, l.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
            l.name = "ref-" + f.stem
            refs.append(l)
    finalists = [l for l, _ in order[:5]] + refs
    say("== hold-out")
    for l, (s, ev) in zip(finalists, eval_many(finalists, hold, args.mode)):
        say(f"  {l.name:22s} {s:6.2f}  {ev.summary()}")
        if not l.name.startswith("ref-"):
            (out / f"{l.name}.json").write_text(json.dumps(l.to_json(), indent=1))
            try:
                render(l, out / f"{l.name}.png")
            except Exception as e:  # rendering is a convenience
                say(f"  (render failed: {e})")
    say(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
