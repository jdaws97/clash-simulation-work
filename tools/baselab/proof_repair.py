"""Proof test 2: can the search repair a deliberately broken base?

The user's base with every defense scrambled with a same-size non-defense
(test 1: ~4 trophies worse) is handed to the search's annealer (attack-guided
moves, a validation set that a new best must also beat) for a fixed time.
Pass: on fresh hold-out battles it recovers at least half the trophies the
scramble cost, with the gain beyond 2 standard errors.

Usage: python tools/baselab/proof_repair.py [--minutes 30]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.evaluate import evaluate, meta_scenarios  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.optimize import Candidate, anneal, objective  # noqa: E402
from proof_scorer import own, score, scrambled  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=30)
    args = ap.parse_args()
    original = own(Layout.load(ROOT / "data/reference-bases/your-base.json"))
    broken = scrambled(original)
    search = meta_scenarios("ranked", 4, (0,))
    validate = meta_scenarios("ranked", 4, (1,), angle_offset=math.pi / 8)
    guide = meta_scenarios("ranked", 2, (2,), angle_offset=math.pi / 3)
    hold = meta_scenarios("ranked", 4, (100, 101), angle_offset=math.pi / 4)
    ev = evaluate(broken, search)
    start = Candidate(broken, objective(ev, "ranked", broken), ev)
    print(f"start (scrambled) search score {start.score:.2f}", flush=True)
    best = anneal(start, search, "ranked", steps=10_000, seed=1, time_budget=args.minutes * 60,
                  validate=validate, guide=guide, guide_every=15)
    (m0, e0, t0), (m1, e1, t1), (m2, e2, t2) = score([broken, best.layout, original], hold)
    lost = m2 - m0
    gain = m1 - m0
    z = gain / math.sqrt(e0 ** 2 + e1 ** 2)
    print(f"\nhold-out ({len(hold)} battles each), defender trophies:")
    print(f"  scrambled start  {m0:6.2f} +- {e0:.2f}   3-star {t0:.1%}")
    print(f"  after search     {m1:6.2f} +- {e1:.2f}   3-star {t1:.1%}")
    print(f"  unbroken base    {m2:6.2f} +- {e2:.2f}   3-star {t2:.1%}")
    frac = gain / lost if lost > 0 else float("nan")
    ok = frac >= 0.5 and z > 2
    print(f"recovered {gain:.2f} of {lost:.2f} lost ({frac:.0%}), z = {z:.1f}  ->  {'PASS' if ok else 'FAIL'}")
    out = ROOT / "output" / "proof"
    out.mkdir(parents=True, exist_ok=True)
    import json
    (out / "repaired.json").write_text(json.dumps(best.layout.to_json(), indent=1))


if __name__ == "__main__":
    main()
