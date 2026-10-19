"""Quick A/B check of attacker-brain changes: army 3-star rate at a fixed
strength on the real reference bases (same jobs as calibrate.py).

Usage: python tools/baselab/ab_test.py --armies throwers,rootrider --k 1.3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.evaluate import Scenario, angles, run_batch  # noqa: E402
from calibrate import reference_bases  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--armies", default="throwers,rootrider")
    ap.add_argument("--k", type=float, default=1.3)
    ap.add_argument("--th", type=int, default=16)
    ap.add_argument("--angles", type=int, default=8)
    args = ap.parse_args()
    bases = reference_bases(0, which="real")
    for army in args.armies.split(","):
        jobs = [(b, Scenario(army, args.th, a, seed=i * args.angles + j), args.k)
                for i, b in enumerate(bases) for j, a in enumerate(angles(args.angles, offset=0.3 * i))]
        res = run_batch(jobs)
        n = len(res)
        print(f"{army:10s} k={args.k} 3*={sum(r[0] >= 3 for r in res) / n:5.1%} stars={sum(r[0] for r in res) / n:.2f} "
              f"pct={sum(r[1] for r in res) / n:5.1f} time={sum(r[3] for r in res) / n:5.1f} "
              f"timeout85={sum(r[3] >= 179 and r[1] >= 85 and r[0] < 3 for r in res) / n:5.1%} "
              f"wiped={sum(r[3] < 179 and r[0] < 3 for r in res) / n:5.1%}", flush=True)


if __name__ == "__main__":
    main()
