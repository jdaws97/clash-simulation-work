"""Benchmark armies (new strategies vs baselines) at the user's own levels
against a set of strong bases.

Stage 1, every army x every base: the scripted plan at 8 sides x `seeds`
skill seeds, attacker scouts 2 (best of 2 sides).
Stage 2, the best `top` armies on the `hard` hardest bases: tactics.py's
robust tuning (side, funnel, timing, charges), scored on fresh seeds.

Usage:
  python tools/baselab/army_bench.py [--armies custom:a meta:b rootrider ...] [--bases ...]
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
from baselab.meta_armies import custom  # noqa: E402
from baselab.tactics import DEFAULT, describe, optimize, play  # noqa: E402

class _Raw(dict):
    def get(self, k, d=None):
        return 1.0


RAW = _Raw()
BASELINES = ["rootrider", "meta:mass-thrower-16-1", "meta:mass-thrower-16-2", "meta:root-rider-16-1", "meta:mass-dragons-16-1"]
BASES = ["data/reference-bases/your-base.json", "data/reference-bases/real-l1x.json", "output/bases-deep/ranked-winner.json",
         "output/web-bases/web-a.json", "output/bases/target17-winner.json", "output/bases/target18-winner.json"]


def scouted(rows):
    picked = []
    for si in range(len(rows[0])):
        per = [r[si] for r in rows]
        for combo in itertools.combinations(per, SCOUT):
            picked.append(max(combo, key=lambda r: (attacker_trophies(*r), r[1])))
    return float(np.mean([s >= 3 for s, _ in picked])), float(np.mean([s for s, _ in picked]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--armies", nargs="*")
    ap.add_argument("--bases", nargs="*", default=BASES)
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--top", type=int, default=4)
    ap.add_argument("--hard", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "output" / "army-bench.json"))
    ap.add_argument("--raw", action="store_true", help="every army at strength 1.0 (raw sim, no calibration)")
    args = ap.parse_args()
    armies = args.armies or ([f"custom:{b['archetype']}" for b in custom()["builds"]] + BASELINES)
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    lays = {}
    for f in args.bases:
        if not Path(ROOT / f).exists():
            continue
        lay = Layout.load(ROOT / f)
        if lay.town_hall == 16:
            lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
        lays[Path(f).stem] = lay
    seeds = [9100 + i for i in range(args.seeds)]
    sides = []
    for k in range(8):
        v = DEFAULT.copy()
        v[0] = 2 * math.pi * k / 8 + 0.1
        sides.append(v)
    table = {}
    print(f"stage 1: {len(armies)} armies x {len(lays)} bases, 8 sides x {len(seeds)} seeds, scouting {SCOUT}", flush=True)
    for a in armies:
        table[a] = {}
        for bn, lay in lays.items():
            table[a][bn] = scouted(play(lay, a, 16, sides, seeds, user=True, strength=RAW if args.raw else None))[0]
        mean = np.mean(list(table[a].values()))
        print(f"  {a:34s} mean 3* {mean:5.1%}  " + "  ".join(f"{bn[:12]} {v:4.0%}" for bn, v in table[a].items()), flush=True)
    base_mean = {bn: np.mean([table[a][bn] for a in armies]) for bn in lays}
    hard = sorted(lays, key=lambda bn: base_mean[bn])[: args.hard]
    best = sorted(armies, key=lambda a: -np.mean(list(table[a].values())))[: args.top]
    print(f"stage 2: tuned tactics, armies {best} on the hardest bases {hard}", flush=True)
    tuned = {}
    for a in best:
        tuned[a] = {}
        for bn in hard:
            r = optimize(lays[bn], a, 16, user=True, iters=4, pop=16, k=4, final_seeds=24, strength=RAW if args.raw else None)
            tuned[a][bn] = {"three_star": r.three_star, "avg_stars": r.avg_stars, "tactics": describe(r.vec)}
            d = describe(r.vec)
            print(f"  {a:34s} vs {bn:16s} tuned 3* {r.three_star:5.1%}  avg {r.avg_stars:.2f}*  side {d['angle_deg']} charge {d.get('charge')}", flush=True)
    Path(args.out).write_text(json.dumps({"scripted": table, "tuned": tuned, "hard": hard}, indent=1, default=str))


if __name__ == "__main__":
    main()
