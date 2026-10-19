"""Adaptive attacker: tune each army's tactics against a base (CEM) and
compare with the scripted plan from evenly spaced sides.

Usage:
  python tools/baselab/attack_search.py BASE.json [--armies throwers rootrider] [--th 17] [--modifier legend1] [--user]
--user plays the user's own account levels (TH16) instead of a max TH attacker.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.layout import Layout  # noqa: E402
from baselab.tactics import baseline, describe, optimize  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bases", nargs="+")
    ap.add_argument("--armies", nargs="*", default=["hydra", "throwers", "edrag", "rootrider"])
    ap.add_argument("--th", type=int, default=18)
    ap.add_argument("--modifier", default=None)
    ap.add_argument("--user", action="store_true")
    ap.add_argument("--iters", type=int, default=6)
    ap.add_argument("--pop", type=int, default=24)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--out")
    args = ap.parse_args()
    th = 16 if args.user else args.th
    report = []
    for f in args.bases:
        lay = Layout.load(f)
        if lay.town_hall == 16:
            own = json.loads((ROOT / "data" / "your-levels.json").read_text())
            lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
        print(f"== {Path(f).stem} vs TH{th} {'(your account) ' if args.user else ''}{args.modifier or 'no modifier'}", flush=True)
        for army in args.armies:
            t0 = time.time()
            base = baseline(lay, army, th, modifier=args.modifier, user=args.user)
            best = optimize(lay, army, th, iters=args.iters, pop=args.pop, k=args.k, modifier=args.modifier, user=args.user,
                            log=lambda m: print(m, flush=True))
            print(f"  {army:10s} scripted {base.summary()}", flush=True)
            print(f"  {army:10s} adaptive {best.summary()}  in {time.time() - t0:.0f}s  tactics {describe(best.vec)}", flush=True)
            report.append({"base": Path(f).stem, "army": army, "th": th, "modifier": args.modifier, "user": args.user,
                           "scripted": base.__dict__ | {"vec": None}, "adaptive": best.__dict__ | {"vec": describe(best.vec)}})
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1, default=float))


if __name__ == "__main__":
    main()
