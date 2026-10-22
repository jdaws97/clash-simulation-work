"""Does the scorer give identical results with the Rust engine?

Scores layouts on the ranked meta scenarios through evaluate.run_batch with
the Python engine and with the Rust engine (BASELAB_ENGINE=rust), compares
every (stars, destruction, th_destroyed, time) tuple, and reports wall times.

Usage: python tools/baselab/scorer_check.py [--angles 4] [--seeds 0]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("BASELAB_PLAYBOOKS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

BASES = ["your-base", "real-l6x", "real-l1x"]


def main():
    from baselab.evaluate import STRENGTH, meta_scenarios, run_batch
    from baselab.layout import Layout
    from proof_scorer import own

    ap = argparse.ArgumentParser()
    ap.add_argument("--angles", type=int, default=4)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0])
    args = ap.parse_args()
    sc = meta_scenarios("ranked", args.angles, tuple(args.seeds))
    jobs = []
    for name in BASES:
        lj = own(Layout.load(ROOT / f"data/reference-bases/{name}.json")).to_json()
        jobs += [(lj, s, STRENGTH.get(s.army, 1.0)) for s in sc]
    os.environ.pop("BASELAB_ENGINE", None)
    t0 = time.time()
    py = run_batch(jobs)
    t_py = time.time() - t0
    os.environ["BASELAB_ENGINE"] = "rust"
    t0 = time.time()
    rs = run_batch(jobs)
    t_rs = time.time() - t0
    t0 = time.time()
    rs2 = run_batch(jobs)  # plans cached now: the cost a search pays per layout batch
    t_rs2 = time.time() - t0
    bad = [i for i, (a, b) in enumerate(zip(py, rs)) if tuple(a) != tuple(b)]
    print(f"{len(jobs)} battles ({len(BASES)} layouts x {len(sc)} scenarios)")
    print(f"python pool {t_py:.1f}s, rust {t_rs:.1f}s first call (builds plans), {t_rs2:.1f}s with cached plans")
    print(f"identical: {len(jobs) - len(bad)}/{len(jobs)}", "" if not bad else f"first differences: {bad[:10]}")
    for i in bad[:5]:
        print("  ", jobs[i][1].army, round(jobs[i][1].angle, 2), jobs[i][1].seed, "py", py[i], "rs", rs[i])
    assert rs == rs2, "Rust results changed between identical calls"


if __name__ == "__main__":
    main()
