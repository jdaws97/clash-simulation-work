"""A/B: plain annealing vs attack-aware (guided) annealing from the same
starting layouts, same seeds and step budget, judged on a hold-out set.

Usage: python tools/baselab/ab_guided.py [--steps 60] [--starts organic:3 organic:5]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.archetypes import design  # noqa: E402
from baselab.evaluate import evaluate, ranked_scenarios  # noqa: E402
from baselab.optimize import Candidate, anneal, objective  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--starts", nargs="*", default=["organic:3", "organic:5"])
    ap.add_argument("--arms", nargs="*", default=["plain", "guided"])
    ap.add_argument("--result", default="result.json")
    args = ap.parse_args()
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    search = ranked_scenarios(n_angles=4, seeds=(0, 1))
    validate = ranked_scenarios(n_angles=6, seeds=(8, 9))
    guide = ranked_scenarios(n_angles=4, seeds=(0,))
    holdout = ranked_scenarios(n_angles=8, seeds=(1, 2, 3))
    out = []
    for spec in args.starts:
        kind, seed = spec.split(":")
        lay = design(kind, int(seed))
        lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
        ev = evaluate(lay, holdout)
        h0 = objective(ev, "ranked", lay)
        print(f"== {spec}: hold-out start {h0:.2f}  {ev.summary()}", flush=True)
        for arm in args.arms:
            t0 = time.time()
            ev = evaluate(lay, search)
            start = Candidate(lay.copy(), objective(ev, "ranked", lay), ev)
            best = anneal(start, search, "ranked", steps=args.steps, seed=11, validate=validate,
                          guide=guide if arm == "guided" else None, log=lambda m: print("   ", arm, m, flush=True))
            hev = evaluate(best.layout, holdout)
            h = objective(hev, "ranked", best.layout)
            print(f"  {arm:6s} hold-out {h:7.2f} (+{h - h0:.2f})  {hev.summary()}  in {time.time() - t0:.0f}s", flush=True)
            out.append({"start": spec, "arm": arm, "holdout": h, "gain": h - h0, "secs": time.time() - t0})
            best.layout.save(ROOT / "output" / "ab-guided" / f"{spec.replace(':', '-')}-{arm}.json")
    (ROOT / "output" / "ab-guided" / args.result).write_text(json.dumps(out, indent=1))
    for arm in args.arms:
        g = [r["gain"] for r in out if r["arm"] == arm]
        print(f"{arm}: mean hold-out gain {sum(g) / len(g):+.2f} over {len(g)} starts", flush=True)


if __name__ == "__main__":
    main()
