"""Check 7 of docs/SIM_ACCURACY.md with cited playbook attackers: the user's
armies and the top TH17 ranked builds play their family playbooks against
each base from every side and both charge flanks, as a scouting player
would choose. The user's real result to reproduce (2026-10-18): the
hole-free base is weaker than ranked-funnel1 for every army but Throwers.

The side and flank are picked on --seeds selection seeds (700...) and the
pick is scored on --score-seeds other seeds (800...), so the best-side rate
carries no winner's-curse optimism (the in-sample rate is reported next to
it). Both counts must be multiples of 5: seed % 5 is the attacker-skill
quantile (evaluate.skill), so each block of 5 seeds covers every quantile
once.

Run with BASELAB_PLAYBOOKS=1 (set here) and the playbook calibration.

Usage: python tools/baselab/playbook_check.py A.json B.json ... [--seeds 5] [--score-seeds 10]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

os.environ["BASELAB_PLAYBOOKS"] = "1"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from baselab.evaluate import STRENGTH, attacker_trophies, pool, skill  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.meta_armies import library  # noqa: E402

# the user rarely attacks with air (2026-10-19), so their air army is left out
USER = [("custom:user-rr", 16), ("custom:user-druid-ruin", 16)]


def _run(args):
    lj, army, th, angle, seed, side, st = args
    from baselab.engine.battle import Battle
    from baselab.engine.playbook import PlaybookPlan
    from baselab.meta_armies import make_plan

    plan = make_plan(army, angle, th, seed)
    if isinstance(plan, PlaybookPlan):
        plan.charge_side = side
    plan.strength = st * skill(seed)
    r = Battle(Layout.from_json(lj), plan, seed=seed, town_hall=16).run()
    return r.stars, r.destruction, r.time, r.units_left


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bases", nargs="+")
    ap.add_argument("--seeds", type=int, default=5, help="selection seeds (multiple of 5)")
    ap.add_argument("--score-seeds", type=int, default=10, help="seeds the pick is scored on (multiple of 5)")
    ap.add_argument("--out", default=str(ROOT / "output" / "playbook-check.json"))
    args = ap.parse_args()
    if args.seeds <= 0 or args.score_seeds <= 0 or args.seeds % 5 or args.score_seeds % 5:
        ap.error("--seeds and --score-seeds must be positive multiples of 5 (one block per skill quantile)")
    pick_seeds, score_seeds = range(700, 700 + args.seeds), range(800, 800 + args.score_seeds)
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    top = sorted(library(17), key=lambda bw: -bw[1])[:3]
    armies = USER + [(f"meta:{b['archetype']}-17-{b['build']}", 17) for b, _ in top]
    trophies = np.vectorize(lambda s, p: attacker_trophies(int(s), p))
    out = {}
    for f in args.bases:
        lay = Layout.load(Path(f))
        lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
        lj = lay.to_json()
        name = Path(f).stem
        out[name] = {}
        for army, th in armies:
            st = STRENGTH.get(army, 1.0)
            sides = [(2 * math.pi * k / 8 + 0.1, side) for k in range(8) for side in ("left", "right")]
            jobs = [(lj, army, th, a, s, side, st) for a, side in sides for s in pick_seeds]
            res = np.array(list(pool().map(_run, jobs, chunksize=1)), dtype=float).reshape(len(sides), args.seeds, 4)
            # a scouting player picks the side and charge flank that pays best;
            # the pick is then scored on seeds it was not picked on
            i = int(np.argmax(trophies(res[..., 0], res[..., 1]).mean(axis=1)))
            a, side = sides[i]
            jobs = [(lj, army, th, a, s, side, st) for s in score_seeds]
            best = np.array(list(pool().map(_run, jobs, chunksize=1)), dtype=float)
            row = {"all_3star": float((res[..., 0] >= 3).mean()), "best_side": [round(a, 3), side],
                   "best_3star_insample": float((res[i, :, 0] >= 3).mean()), "best_3star": float((best[:, 0] >= 3).mean()),
                   "best_pct": float(best[:, 1].mean()), "best_units_left": float(best[:, 3].mean()), "best_time": float(best[:, 2].mean())}
            out[name][army] = row
            print(f"{name:22s} {army:32s} 3* all sides {row['all_3star']:4.0%} | best side {row['best_3star']:4.0%} "
                  f"(in-sample {row['best_3star_insample']:4.0%}) {row['best_pct']:5.1f}% units left "
                  f"{row['best_units_left']:4.1f} time {row['best_time']:4.0f}s", flush=True)
            Path(args.out).write_text(json.dumps(out, indent=1))
    names = list(out)
    print("== mean 3-star over armies (all sides / best side / best side in-sample)", flush=True)
    for n in names:
        a, b, c = ([out[n][x][k] for x, _ in armies] for k in ("all_3star", "best_3star", "best_3star_insample"))
        print(f"  {n:22s} {np.mean(a):.1%} / {np.mean(b):.1%} / {np.mean(c):.1%}", flush=True)


if __name__ == "__main__":
    main()
