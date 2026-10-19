"""Per-base adaptive attackers: for each army, search the best tactics
(side, funnel, timing, hero charge, Freeze targets...) against each base,
like a human who scouts and plans, then score on fresh seeds.

The real-world check (2026-10-18): the user 3-starred the hole-free base
with every army except Throwers, while the earlier base was hard. Adaptive
scoring is only trusted for base search if it reproduces that ordering.

Usage: python tools/baselab/adaptive_check.py A.json B.json ... [--armies ...] [--iters 6]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.layout import Layout  # noqa: E402
from baselab.meta_armies import library  # noqa: E402
from baselab.tactics import describe, optimize  # noqa: E402

USER = [("custom:user-rr", 16), ("custom:user-air", 16), ("custom:user-druid-ruin", 16)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bases", nargs="+")
    ap.add_argument("--armies", nargs="*", help="army ids (default: the user's 3 armies + top 3 TH17 ranked builds)")
    ap.add_argument("--iters", type=int, default=6)
    ap.add_argument("--pop", type=int, default=24)
    ap.add_argument("--final", type=int, default=24)
    ap.add_argument("--out", default=str(ROOT / "output" / "adaptive-check.json"))
    args = ap.parse_args()
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    if args.armies:
        armies = [(a, 16 if a.startswith("custom:") else int(a.rsplit("-", 2)[1])) for a in args.armies]
    else:
        top = sorted(library(17), key=lambda bw: -bw[1])[:3]
        armies = USER + [(f"meta:{b['archetype']}-17-{b['build']}", 17) for b, _ in top]
    out = {}
    for f in args.bases:
        lay = Layout.load(Path(f))
        lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
        name = Path(f).stem
        out[name] = {}
        for army, th in armies:
            r = optimize(lay, army, th, iters=args.iters, pop=args.pop, k=6, final_seeds=args.final, seed=7)
            d = describe(r.vec)
            out[name][army] = {"three_star": r.three_star, "avg_stars": r.avg_stars, "avg_pct": r.avg_pct, "tactic": d}
            print(f"{name:22s} {army:34s} tuned {r.summary()}  side {d['angle_deg']}deg charge {d.get('charge')}", flush=True)
            Path(args.out).write_text(json.dumps(out, indent=1))
    names = list(out)
    print("== summary (tuned 3-star rate)", flush=True)
    for army, _ in armies:
        print(f"  {army:34s} " + "  ".join(f"{n}: {out[n][army]['three_star']:4.0%} ({out[n][army]['avg_pct']:.0f}%)" for n in names), flush=True)
    for n in names:
        v = [out[n][a]["three_star"] for a, _ in armies]
        print(f"  mean over armies  {n}: {sum(v) / len(v):.1%}", flush=True)


if __name__ == "__main__":
    main()
