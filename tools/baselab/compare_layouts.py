"""Paired comparison of a few complete layouts on identical battles.

Each layout faces the same ranked meta attacks (same armies, sides, seeds);
reports defender trophies and 3-star rate, and every layout's difference
from the first one with its paired standard error, bootstrap interval and
practical-tie verdict.

Usage: python tools/baselab/compare_layouts.py A.json B.json ... [--angles 8] [--seeds 2]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.evaluate import meta_scenarios  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.uncertainty import group_trophies, paired_comparison  # noqa: E402
from funnel import eval_many  # noqa: E402
from proof_scorer import own  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("layouts", nargs="+")
    ap.add_argument("--angles", type=int, default=8)
    ap.add_argument("--seeds", type=int, default=2)
    args = ap.parse_args()
    lays = [own(Layout.load(f)) for f in args.layouts]
    sc = meta_scenarios("ranked", args.angles, tuple(range(args.seeds)))
    results, battles = eval_many(lays, sc, "ranked", return_results=True)
    k = len(sc)
    print(f"{k} battles per layout (identical across layouts)")
    w, base = group_trophies(sc, battles[0])
    for f, raw, (_score, ev) in zip(args.layouts, battles, results):
        comparison = paired_comparison(sc, raw, battles[0])
        _, trophies = group_trophies(sc, raw)
        d = [t - b for t, b in zip(trophies, base)]
        md = comparison.difference
        se = math.sqrt(
            sum(weight**2 * (delta - md) ** 2 for weight, delta in zip(w, d))
        )
        print(
            f"{Path(f).stem:28s} trophies {ev.ranked_trophies:6.2f}  3-star {ev.three_star_rate:5.1%}  vs first {md:+6.2f} +- {se:.2f}  (z {md / se if se else 0:+.1f})"
        )
        print(
            f"  A=this layout, B=first: {comparison.summary()} ({comparison.groups} scouting groups)"
        )


if __name__ == "__main__":
    main()
