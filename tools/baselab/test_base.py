"""Test bases against one army at the user's own levels (TH16), three ways:
  scripted   the plan as written, 8 sides, attacker scouts 2 (best of 2)
  charges    a hero charge (default Royal Champion) at several Healer counts,
             positions and start times, also scouted
  tuned      tactics.py's robust search (side, funnel, timing, charge)
and explain each base: its measurable traits next to the first base's, and
where the tuned attack still loses.

Usage:
  python tools/baselab/test_base.py A.json B.json ... [--army rootrider] [--charge "Royal Champion"]
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
from baselab.surrogate import FEATURES, features  # noqa: E402
from baselab.tactics import CHARGE_OPTIONS, DEFAULT, NAMES, describe, optimize, play  # noqa: E402


def scouted(rows_by_side):
    """rows_by_side[side][seed] -> (stars, pct); attacker scouts SCOUT sides."""
    picked = []
    for si in range(len(rows_by_side[0])):
        per = [r[si] for r in rows_by_side]
        for combo in itertools.combinations(per, SCOUT):
            picked.append(max(combo, key=lambda r: (attacker_trophies(*r), r[1])))
    return np.mean([s >= 3 for s, _ in picked]), np.mean([s for s, _ in picked]), np.mean([p for _, p in picked])


def vec(angle, charge=None):
    v = DEFAULT.copy()
    v[0] = angle
    if charge:
        hero, healers, lat, length = charge
        v[NAMES.index("charge_pick")] = CHARGE_OPTIONS.index(hero) + 0.5
        v[NAMES.index("charge_healers")] = healers + 0.5
        v[NAMES.index("charge_lat")] = lat
        v[NAMES.index("charge_at")] = 0.0
        v[NAMES.index("charge_len")] = length
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bases", nargs="+")
    ap.add_argument("--army", default="rootrider")
    ap.add_argument("--charge", default="Royal Champion")
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--no-tuned", action="store_true")
    args = ap.parse_args()
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    seeds = [8100 + i for i in range(args.seeds)]
    sides = [2 * math.pi * k / 8 + 0.1 for k in range(8)]
    report = {}
    feats = {}
    for f in args.bases:
        lay = Layout.load(f)
        lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
        name = Path(f).stem
        rows = play(lay, args.army, 16, [vec(a) for a in sides], seeds, user=True)
        s3, st, pc = scouted(rows)
        print(f"== {name}  ({args.army}, your levels, TH16)", flush=True)
        print(f"  scripted, scouted       3* {s3:5.1%}  avg {st:.2f}*  {pc:5.1f}%", flush=True)
        best_charge = None
        for healers in (0, 4):
            for lat in (-6.0, 0.0, 6.0):
                for length in (12.0, 25.0):
                    ch = (args.charge, healers, lat, length)
                    r = play(lay, args.army, 16, [vec(a, ch) for a in sides], seeds[: max(4, args.seeds // 2)], user=True)
                    c3, cst, cpc = scouted(r)
                    if best_charge is None or (c3, cst) > best_charge[0][:2]:
                        best_charge = ((c3, cst, cpc), ch)
        (c3, cst, cpc), ch = best_charge
        print(f"  best {args.charge} charge 3* {c3:5.1%}  avg {cst:.2f}*  {cpc:5.1f}%   ({ch[1]} Healers, side offset {ch[2]:+.0f}, Invisibility on her, Recall after {ch[3]:.0f}s or when hurt)", flush=True)
        if args.no_tuned:
            report[name] = {"scripted": s3, "charge": c3, "charge_setup": ch}
            feats[name] = features(lay)
            continue
        t = optimize(lay, args.army, 16, user=True, final_seeds=24)
        d = describe(t.vec)
        print(f"  tuned (any tactic)      3* {t.three_star:5.1%}  avg {t.avg_stars:.2f}*  {t.avg_pct:5.1f}%   side {d['angle_deg']} deg, "
              f"charge {d.get('charge')}, spread x{d['spread']}, main push {d['main_min']:.0f}-{d['main_min'] + d['main_gap']:.0f}s", flush=True)
        report[name] = {"scripted": s3, "charge": c3, "charge_setup": ch, "tuned": t.three_star, "tuned_tactics": d}
        feats[name] = features(lay)
    names = list(feats)
    if len(names) > 1:
        print("\n== what differs (first base vs the others)", flush=True)
        base = feats[names[0]]
        keyf = ["g_side_min", "a_side_min", "g_min", "a_min", "g_th", "a_th", "layers_th", "layers_key", "frac_outside",
                "th_center_dist", "key_th_dist", "inner_area", "traps_inside", "inferno_single", "xbow_both"]
        for k in keyf:
            i = FEATURES.index(k)
            print(f"  {k:16s} " + "  ".join(f"{n[:14]:>14s} {feats[n][i]:8.1f}" for n in names), flush=True)
    (ROOT / "output" / "checks" / f"test-{args.army}.json").write_text(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
