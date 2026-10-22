"""Paired comparison of a few complete layouts on identical battles.

Each layout faces the same ranked meta attacks (same armies, sides, seeds);
reports defender trophies and 3-star rate, and every layout's difference
from the first one with its paired standard error.

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
from proof_scorer import own, score  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("layouts", nargs="+")
    ap.add_argument("--angles", type=int, default=8)
    ap.add_argument("--seeds", type=int, default=2)
    args = ap.parse_args()
    lays = [own(Layout.load(f)) for f in args.layouts]
    sc = meta_scenarios("ranked", args.angles, tuple(range(args.seeds)))
    # evaluate.summarise: use scouted outcomes, paired by attacker group.
    results, w, per = score(lays, sc, return_samples=True)
    k = len(sc)
    print(f"{k} battles per layout (identical across layouts)")
    base = per[0]
    for f, t, (m, _se, three) in zip(args.layouts, per, results):
        d = t - base
        md = (w * d).sum()
        se = math.sqrt((w ** 2 * (d - md) ** 2).sum())
        print(
            f"{Path(f).stem:28s} trophies {m:6.2f}  3-star {three:5.1%}  vs first {md:+6.2f} +- {se:.2f}  (z {md / se if se else 0:+.1f})"
        )


if __name__ == "__main__":
    main()
