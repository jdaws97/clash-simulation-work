"""How many battles does a base need before its score can be trusted?
Scores the same layouts on two disjoint scenario sets (different skill
seeds, same armies and sides) at several sizes and reports, per size, the
spread of the score difference (noise) and how well the two sets agree on
the ranking of the layouts.

Usage: python tools/baselab/base_noise.py [--mode ranked]
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.archetypes import design  # noqa: E402
from baselab.evaluate import evaluate, meta_scenarios  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.optimize import objective  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="ranked")
    args = ap.parse_args()
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    lays = [Layout.load(f) for f in sorted(glob.glob(str(ROOT / "data" / "reference-bases" / "*.json")))]
    lays += [Layout.load(str(ROOT / "output" / "bases-deep" / "ranked-winner.json"))]
    lays += [design("organic", s) for s in (3, 5, 11)]
    for l in lays:
        l.levels, l.wall_level, l.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
    for n_angles, seeds_a, seeds_b in ((4, (0,), (1,)), (8, (0,), (1,)), (8, (0, 2), (1, 3))):
        A = meta_scenarios(args.mode, n_angles, seeds_a)
        B = meta_scenarios(args.mode, n_angles, seeds_b)
        sa = np.array([objective(evaluate(l, A), args.mode, l) for l in lays])
        sb = np.array([objective(evaluate(l, B), args.mode, l) for l in lays])
        d = sa - sb
        print(f"{len(A):4d} battles per score: noise (sd of A-B)/sqrt2 = {d.std() / np.sqrt(2):.2f}; "
              f"rank agreement {spearmanr(sa, sb).correlation:.2f}; scores range {sa.min():.1f}..{sa.max():.1f}", flush=True)


if __name__ == "__main__":
    main()
