"""Is per-base tactic tuning (tactics.py) a real gain? For one base and each
army: the scripted plan with scouting (best of SCOUT sides out of 8, the
calibrated attacker model) vs tactics tuned by CEM, both scored on the same
fresh skill seeds (48 by default). Also re-runs the tuning with a different
search seed to see whether it lands on similar tactics.

Usage: python tools/baselab/tactics_check.py BASE.json [--th 18] [--fresh 48]
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.evaluate import SCOUT, attacker_trophies  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.tactics import DEFAULT, describe, optimize, play  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--th", type=int, default=18)
    ap.add_argument("--fresh", type=int, default=48)
    ap.add_argument("--armies", nargs="*", default=["hydra", "throwers", "edrag", "rootrider"])
    args = ap.parse_args()
    lay = Layout.load(args.base)
    if lay.town_hall == 16:
        own = json.loads((ROOT / "data" / "your-levels.json").read_text())
        lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
    seeds = [7000 + i for i in range(args.fresh)]
    for army in args.armies:
        vecs = []
        for k in range(8):
            v = DEFAULT.copy()
            v[0] = 2 * math.pi * k / 8 + 0.1
            vecs.append(v)
        rows = play(lay, army, args.th, vecs, seeds)  # rows[side][seed]
        picked = []
        for si in range(len(seeds)):
            per_side = [rows[k][si] for k in range(8)]
            for combo in itertools.combinations(per_side, SCOUT):
                picked.append(max(combo, key=lambda r: (attacker_trophies(*r), r[1])))
        scripted = np.mean([s >= 3 for s, _ in picked])
        res = []
        for search_seed in (0, 1):
            best = optimize(lay, army, args.th, seed=search_seed, final_seeds=1)
            fr = play(lay, army, args.th, [best.vec], seeds)[0]
            res.append((np.mean([s >= 3 for s, _ in fr]), best.vec))
        print(f"{army:10s} scripted+scouting 3* {scripted:5.1%} | tuned (search seed 0) {res[0][0]:5.1%}, (seed 1) {res[1][0]:5.1%}  "
              f"[{args.fresh} fresh seeds]  sides {describe(res[0][1])['angle_deg']} / {describe(res[1][1])['angle_deg']} deg", flush=True)


if __name__ == "__main__":
    main()
