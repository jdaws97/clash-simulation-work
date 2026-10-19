"""Check 7 of docs/SIM_ACCURACY.md with cited playbook attackers: the user's
armies and the top TH17 ranked builds play their family playbooks against
each base from every side and both charge flanks, as a scouting player
would choose. The user's real result to reproduce (2026-10-18): the
hole-free base is weaker than ranked-funnel1 for every army but Throwers.

Run with BASELAB_PLAYBOOKS=1 (set here) and the playbook calibration.

Usage: python tools/baselab/playbook_check.py A.json B.json ... [--seeds 4]
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
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--out", default=str(ROOT / "output" / "playbook-check.json"))
    args = ap.parse_args()
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    top = sorted(library(17), key=lambda bw: -bw[1])[:3]
    armies = USER + [(f"meta:{b['archetype']}-17-{b['build']}", 17) for b, _ in top]
    out = {}
    for f in args.bases:
        lay = Layout.load(Path(f))
        lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
        lj = lay.to_json()
        name = Path(f).stem
        out[name] = {}
        for army, th in armies:
            st = STRENGTH.get(army, 1.0)
            jobs = [(lj, army, th, 2 * math.pi * k / 8 + 0.1, 700 + s, side, st)
                    for k in range(8) for side in ("left", "right") for s in range(args.seeds)]
            res = np.array(list(pool().map(_run, jobs, chunksize=1)), dtype=float).reshape(8, 2, args.seeds, 4)
            # a scouting player picks the side and charge flank that pays best
            score = (np.vectorize(lambda s, p: attacker_trophies(int(s), p))(res[..., 0], res[..., 1])).mean(axis=2)
            k, side = np.unravel_index(int(np.argmax(score)), score.shape)
            best = res[k, side]
            row = {"all_3star": float((res[..., 0] >= 3).mean()), "best_3star": float((best[:, 0] >= 3).mean()),
                   "best_pct": float(best[:, 1].mean()), "best_units_left": float(best[:, 3].mean()), "best_time": float(best[:, 2].mean())}
            out[name][army] = row
            print(f"{name:22s} {army:32s} 3* all sides {row['all_3star']:4.0%} | best side {row['best_3star']:4.0%} "
                  f"{row['best_pct']:5.1f}% units left {row['best_units_left']:4.1f} time {row['best_time']:4.0f}s", flush=True)
            Path(args.out).write_text(json.dumps(out, indent=1))
    names = list(out)
    print("== mean 3-star over armies (all sides / best side)", flush=True)
    for n in names:
        a = [out[n][x]["all_3star"] for x, _ in armies]
        b = [out[n][x]["best_3star"] for x, _ in armies]
        print(f"  {n:22s} {np.mean(a):.1%} / {np.mean(b):.1%}", flush=True)


if __name__ == "__main__":
    main()
