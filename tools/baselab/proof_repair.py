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


def paired(lays, scenarios):
    """Per-battle defender trophies for each layout on the same battles."""
    from proof_paired import per_battle

    return per_battle(lays, scenarios)


def batch_search(start, minutes, *, k=13, seed=1, log=print):
    """Batched paired hill-climb: each round k guided mutations of the
    current layout are screened on the same small battle set as the current
    layout (paired differences), the best 3 are re-checked on a separate
    paired set, and the best confirmed gain is accepted."""
    import random as _r
    import time as _t

    import numpy as _np

    from baselab.diagnose import diagnose
    from baselab.optimize import mutate

    rng = _r.Random(seed)
    screen = meta_scenarios("ranked", 2, (3,), angle_offset=0.2)
    check = meta_scenarios("ranked", 4, (4,), angle_offset=1.1)
    guide = meta_scenarios("ranked", 2, (2,), angle_offset=math.pi / 3)
    ws = _np.array([x.weight for x in screen]); ws = ws / ws.sum()
    wc = _np.array([x.weight for x in check]); wc = wc / wc.sum()
    cur = start
    cur_s = paired([cur], screen)[0]
    cur_c = paired([cur], check)[0]
    t0 = _t.time()
    rnd = 0
    while _t.time() - t0 < minutes * 60:
        rnd += 1
        diag = diagnose(cur, guide)
        cands, descs = [], []
        while len(cands) < k:
            m, d = mutate(cur, rng, diag)
            if d != "noop" and not m.problems():
                cands.append(m)
                descs.append(d)
        scores = paired(cands, screen)
        deltas = [float((ws * (x - cur_s)).sum()) for x in scores]
        top = sorted(range(k), key=lambda i: -deltas[i])[:3]
        top = [i for i in top if deltas[i] > 0]
        if not top:
            log(f"round {rnd}: no screened gain")
            continue
        checks = paired([cands[i] for i in top], check)
        conf = [float((wc * (c - cur_c)).sum()) for c in checks]
        j = max(range(len(top)), key=lambda q: conf[q])
        if conf[j] > 0.3:
            i = top[j]
            cur, cur_c = cands[i], checks[j]
            cur_s = scores[i]
            log(f"round {rnd}: accepted {descs[i]:28s} screened {deltas[i]:+.2f} confirmed {conf[j]:+.2f}  t={_t.time() - t0:.0f}s")
        else:
            log(f"round {rnd}: best confirmed gain {conf[j]:+.2f} too small")
    return cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--method", choices=["anneal", "batch"], default="batch")
    args = ap.parse_args()
    original = own(Layout.load(ROOT / "data/reference-bases/your-base.json"))
    broken = scrambled(original)
    search = meta_scenarios("ranked", 4, (0,))
    validate = meta_scenarios("ranked", 4, (1,), angle_offset=math.pi / 8)
    guide = meta_scenarios("ranked", 2, (2,), angle_offset=math.pi / 3)
    hold = meta_scenarios("ranked", 4, (100, 101), angle_offset=math.pi / 4)
    if args.method == "batch":
        result = batch_search(broken, args.minutes, log=lambda m: print(m, flush=True))
    else:
        ev = evaluate(broken, search)
        start = Candidate(broken, objective(ev, "ranked", broken), ev)
        print(f"start (scrambled) search score {start.score:.2f}", flush=True)
        result = anneal(start, search, "ranked", steps=10_000, seed=1, time_budget=args.minutes * 60,
                        validate=validate, guide=guide, guide_every=15).layout
    (m0, e0, t0), (m1, e1, t1), (m2, e2, t2) = score([broken, result, original], hold)
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
    (out / "repaired.json").write_text(json.dumps(result.to_json(), indent=1))


if __name__ == "__main__":
    main()
