"""How much noise is left when a base and a one-mutation variant are compared
on IDENTICAL battles (same armies, sides, seeds), versus comparing two
independent scores. If the paired difference is much less noisy, the search
can decide each move with far fewer battles.

Usage: python tools/baselab/proof_paired.py [--variants 10]
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

import numpy as np  # noqa: E402

from baselab.evaluate import STRENGTH, defender_trophies, meta_scenarios, run_batch  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.optimize import mutate  # noqa: E402
from proof_scorer import own  # noqa: E402


def per_battle(lays, scenarios):
    jobs = []
    for l in lays:
        lj = l.to_json()
        jobs += [(lj, sc, STRENGTH.get(sc.army, 1.0)) for sc in scenarios]
    res = run_batch(jobs)
    k = len(scenarios)
    return [np.array([defender_trophies(int(x[0]), x[1]) for x in res[n * k:(n + 1) * k]], dtype=float) for n in range(len(lays))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", type=int, default=10)
    args = ap.parse_args()
    base = own(Layout.load(ROOT / "data/reference-bases/your-base.json"))
    rng = random.Random(5)
    variants, descs = [], []
    while len(variants) < args.variants:
        m, d = mutate(base, rng)
        if d != "noop" and not m.problems():
            variants.append(m)
            descs.append(d)
    sc = meta_scenarios("ranked", 4, (0, 1))
    w = np.array([s.weight for s in sc])
    w = w / w.sum()
    t = per_battle([base] + variants, sc)
    b = t[0]
    mb = (w * b).sum()
    se_b = math.sqrt((w ** 2 * (b - mb) ** 2).sum())
    print(f"{len(sc)} battles each; base {mb:.2f} +- {se_b:.2f}")
    print(f"{'mutation':32s} {'delta':>7s} {'paired SE':>10s} {'independent SE':>15s} {'ratio':>6s}  battles changed")
    ratios = []
    for v, d in zip(t[1:], descs):
        diff = v - b
        md = (w * diff).sum()
        se_p = math.sqrt((w ** 2 * (diff - md) ** 2).sum())
        mv = (w * v).sum()
        se_v = math.sqrt((w ** 2 * (v - mv) ** 2).sum())
        se_i = math.sqrt(se_b ** 2 + se_v ** 2)
        ratios.append(se_p / se_i)
        print(f"{d[:32]:32s} {md:7.2f} {se_p:10.2f} {se_i:15.2f} {se_p / se_i:6.2f}  {int((diff != 0).sum())}/{len(sc)}")
    r = float(np.median(ratios))
    print(f"\nmedian paired/independent noise ratio {r:.2f}: deciding a move needs about {r * r:.0%} of the battles")


if __name__ == "__main__":
    main()
