"""Fit per-army attacker strength to real ranked three-star rates.

Real targets: TrophyCoach same-TH ranked battles, 30-day window to
2026-10-15 (docs/RESEARCH-2026-10.md). We simulate TH16 armies against a set
of generated TH16 reference bases (all defenses max TH16) from 8 approach
angles each, sweep a strength multiplier on attacking unit HP/DPS, and
interpolate the multiplier that reproduces each army's real 3-star rate.

Usage: python tools/baselab/calibrate.py [--bases 12] [--angles 8]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.evaluate import Scenario, angles, run_batch, scouted  # noqa: E402
from baselab.generator import build, random_blueprint  # noqa: E402

TARGETS = {  # TH16 same-TH: (3-star rate, average stars)
    "hydra": (0.493, 2.32),
    "edrag": (0.318, 2.05),
    "rootrider": (0.644, 2.56),
    "throwers": (0.730, 2.65),
}
GRID = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.45, 1.6, 1.8, 2.0, 2.2, 2.45, 2.7]


def reference_bases(n, seed=7, which="gen"):
    """'gen' = generated designs, 'real' = human-designed reference bases."""
    if which == "real":
        files = sorted((ROOT / "data" / "reference-bases").glob("real-*.json"))
        return [json.loads(f.read_text()) for f in files]
    rng = random.Random(seed)
    return [build(random_blueprint(rng, seed=i)).to_json() for i in range(n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bases", type=int, default=12)
    ap.add_argument("--angles", type=int, default=8)
    ap.add_argument("--th", type=int, default=16)
    ap.add_argument("--set", default="gen", choices=["gen", "real"])
    ap.add_argument("--armies", default=",".join(TARGETS))
    ap.add_argument("--out", default=str(ROOT / "data" / "baselab-calibration.json"))
    args = ap.parse_args()
    bases = reference_bases(args.bases, which=args.set)
    report = {}
    for army, (target3, target_stars) in TARGETS.items():
        if army not in args.armies.split(","):
            continue
        rows = []
        for k in GRID:
            t0 = time.time()
            jobs = [
                (b, Scenario(army, args.th, a, seed=i * args.angles + j), k)
                for i, b in enumerate(bases)
                for j, a in enumerate(angles(args.angles, offset=0.3 * i))
            ]
            res = run_batch(jobs)
            # attackers scout and take the better of SCOUT sides (evaluate.SCOUT)
            scs = [Scenario(sc.army, sc.town_hall, sc.angle, sc.seed, 1.0, None, i // args.angles) for i, (_b, sc, _k) in enumerate(jobs)]
            srows = scouted(scs, res)
            W = sum(w for _s, _r, w in srows)
            three = sum(w * (r[0] >= 3) for _s, r, w in srows) / W
            stars = sum(w * r[0] for _s, r, w in srows) / W
            pct = sum(w * r[1] for _s, r, w in srows) / W
            rows.append((k, three, stars, pct))
            print(f"{army:10} k={k:4.2f} 3*={three:5.1%} stars={stars:.2f} pct={pct:5.1f}  ({time.time()-t0:.0f}s)", flush=True)
            if three > target3 + 0.15:
                break
        fit = None
        for (k0, a0, _, _), (k1, a1, _, _) in zip(rows, rows[1:]):
            if a0 <= target3 <= a1 and a1 > a0:
                fit = k0 + (k1 - k0) * (target3 - a0) / (a1 - a0)
                break
        if fit is None:
            fit = rows[0][0] if rows[0][1] > target3 else rows[-1][0]
        report[army] = {"strength": round(fit, 3), "target_3star": target3, "target_stars": target_stars, "sweep": rows}
        print(f"  -> {army} strength {fit:.3f}", flush=True)
    Path(args.out).write_text(json.dumps(report, indent=1))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
