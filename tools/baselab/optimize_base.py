"""Search for a TH16 ranked or war base with engine v2.

Stages:
1. Screen: the human reference bases plus N random generated designs are
   scored on a cheap scenario set (4 approach angles per army).
2. Anneal: the best K are refined by simulated annealing on a fixed scenario
   set (common random numbers).
3. Hold-out: the winner and the reference bases are re-scored on a larger set
   of unseen angles and skill seeds, so overfitting shows up.

Ranked = TH17/18 attackers weighted by the live meta (defender trophies);
war = TH16 attackers (avoid three stars).

Usage:
  python tools/baselab/optimize_base.py --mode ranked --designs 30 --steps 250
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.archetypes import design as original_design  # noqa: E402
from baselab.evaluate import evaluate, ranked_scenarios, target_scenarios, war_scenarios  # noqa: E402
from baselab.generator import build, random_blueprint  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.optimize import Candidate, anneal, hole_tiles, objective  # noqa: E402
from baselab.render import render  # noqa: E402


def scenarios(mode, n_angles, seeds):
    if mode == "ranked":
        return ranked_scenarios(n_angles=n_angles, seeds=seeds)
    if mode.startswith("target"):
        return target_scenarios(int(mode[-2:]), n_angles=n_angles, seeds=seeds)
    return war_scenarios(n_angles=n_angles, seeds=seeds)


def objective_mode(mode):
    return "war" if mode == "war" else "ranked"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["ranked", "war", "target17", "target18"], default="ranked")
    ap.add_argument("--designs", type=int, default=30)
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--steps", type=int, default=250)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "output" / "bases"))
    ap.add_argument("--search-angles", type=int, default=6)
    ap.add_argument("--search-seeds", type=int, default=2)
    ap.add_argument("--seeds-from", nargs="*", default=None, help="only anneal these reference layouts (names)")
    ap.add_argument("--originals", type=int, default=0, help="freeform original designs to screen (archetypes.py: organic and free, 2:1)")
    ap.add_argument("--styled", type=int, default=0, help="styled original designs (grid/offset/rings/wide) to screen")
    ap.add_argument("--originals-only", action="store_true", help="anneal only original designs; references are benchmarks")
    ap.add_argument("--compare", nargs="*", default=[], help="extra layout files scored in the hold-out as benchmarks")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log_f = open(out / f"{args.mode}-search.log", "w", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        log_f.write(msg + "\n")
        log_f.flush()

    cheap = scenarios(args.mode, 4, (0, 1))
    search = scenarios(args.mode, args.search_angles, tuple(range(args.search_seeds)))
    holdout = scenarios(args.mode, 8, (1, 2, 3))
    # independent validation battles guard each new best against lucky draws
    validate = scenarios(args.mode, 6, (8, 9))
    t0 = time.time()

    th = int(args.mode[-2:]) if args.mode.startswith("target") else 16
    om = objective_mode(args.mode)
    refs = [Layout.load(f) for f in sorted((ROOT / "data" / "reference-bases").glob("*.json"))] if th == 16 else []
    refs = [r for r in refs if r.name.startswith("real-") or r.name == "your-base"]
    pool = []
    log(f"== screen ({args.mode}): {len(refs)} reference bases + {args.designs} generated designs")
    for lay in refs:
        ev = evaluate(lay, cheap)
        pool.append(Candidate(lay, objective(ev, om, lay), ev))
        log(f"  ref {lay.name:12s} score {pool[-1].score:7.2f}  {ev.summary()}")
    # TH16 bases are built with the user's actual buildings (data/your-levels.json)
    own = json.loads((ROOT / "data" / "your-levels.json").read_text()) if th == 16 else None

    def with_levels(lay):
        if own:
            lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
        return lay

    refs = [with_levels(r) for r in refs]
    rng = random.Random(args.seed)
    for i in range(args.designs):
        try:
            bp = random_blueprint(rng, seed=rng.randrange(10**6))
            bp.town_hall = th
            lay = with_levels(build(bp))
        except RuntimeError:
            continue
        lay.name = f"{args.mode}-design-{i}"
        ev = evaluate(lay, cheap)
        pool.append(Candidate(lay, objective(ev, om, lay), ev))
        log(f"  gen {i:3d}          score {pool[-1].score:7.2f}  {ev.summary()}")
    kinds = [("organic", "organic", "free")[i % 3] for i in range(args.originals)] + [("grid", "offset", "rings", "wide")[i % 4] for i in range(args.styled)]
    for i, kind in enumerate(kinds):
        try:
            lay = with_levels(original_design(kind, args.seed * 1000 + i, town_hall=th))
        except RuntimeError:
            continue
        ev = evaluate(lay, cheap)
        pool.append(Candidate(lay, objective(ev, om, lay), ev))
        log(f"  orig {lay.name:20s} score {pool[-1].score:7.2f}  {ev.summary()}  holes {hole_tiles(lay)}")
    pool.sort(key=lambda c: -c.score)
    if args.originals_only:
        pool = [c for c in pool if c.layout.name.startswith("orig-")]
    if args.seeds_from:
        pool = [c for c in pool if c.layout.name in args.seeds_from] + [c for c in pool if c.layout.name not in args.seeds_from]
    log(f"screen done in {time.time() - t0:.0f}s; top: " + ", ".join(f"{c.layout.name}={c.score:.2f}" for c in pool[: args.top]))

    finalists = []
    for k, cand in enumerate(pool[: args.top]):
        ev = evaluate(cand.layout, search)
        start = Candidate(cand.layout, objective(ev, om, cand.layout), ev)
        log(f"== anneal {k + 1}/{args.top}: {cand.layout.name} start {start.score:.2f}")
        best = anneal(start, search, om, steps=args.steps, seed=args.seed + k, log=log, validate=validate)
        best.layout.name = f"{args.mode}-best-{k + 1}"
        finalists.append(best)

    log("== hold-out")
    rows = []
    bench = [with_levels(Layout.load(f)) for f in args.compare]
    for f, lay in zip(args.compare, bench):
        lay.name = "bench-" + Path(f).parent.name + "-" + Path(f).stem
    for lay in [c.layout for c in finalists] + refs + bench:
        ev = evaluate(lay, holdout)
        sc = objective(ev, om, lay)
        rows.append((sc, lay, ev))
        log(f"  {lay.name:16s} hold-out {sc:7.2f}  {ev.summary()}  holes {hole_tiles(lay)}")
    rows.sort(key=lambda r: -r[0])
    win_sc, win, win_ev = rows[0]
    win.save(out / f"{args.mode}-winner.json")
    render(win, out / f"{args.mode}-winner.png", title=f"TH{th} {args.mode} base (hold-out {win_ev.summary()})")
    (out / f"{args.mode}-winner-eval.json").write_text(json.dumps({
        "objective": win_sc, "summary": win_ev.summary(), "per_army": win_ev.per_army, "worst_side": win_ev.worst_side,
        "table": [{"name": l.name, "objective": s, "summary": e.summary(), "per_army": e.per_army} for s, l, e in rows],
    }, indent=1))
    for c in pool[: max(args.top, 8)]:
        if c.layout.name.startswith("orig-"):
            c.layout.save(out / f"screen-{c.layout.name}.json")
    for k, c in enumerate(finalists):
        c.layout.save(out / f"{args.mode}-best-{k + 1}.json")
    log(f"winner {win.name} ({win_sc:.2f}) in {time.time() - t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
