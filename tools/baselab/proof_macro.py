"""Proof test 2 with macro moves (src/baselab/macro_moves.py).

effects: each macro move applied to a start layout, child and parent scored
on IDENTICAL battles (meta_scenarios("ranked", 4, (0,)), 68 battles; per
battle defender trophies), reporting the paired delta and its standard error.

repair: greedy macro-move sequence from the scrambled user base (each round
takes the move with the best paired delta if it beats max(0.3, 1 SE)), then
scrambled / repaired / unbroken on fresh hold-out battles
(meta_scenarios("ranked", 4, (100, 101), angle_offset=pi/4)).

2026-10-21 run (engine 89b3606, playbooks on, r8 calibration): role_repack
+4.89 +- 1.38 on the scrambled base, rotate_core +1.21 +- 1.04 after it;
hold-out scrambled 5.63, repaired 9.87, unbroken 11.67 (paired gain
+4.25 +- 1.04, 70% recovered). role_repack alone: 9.11 on the hold-out.

Usage: python tools/baselab/proof_macro.py effects --starts your-base,scrambled [--moves a,b]
       python tools/baselab/proof_macro.py repair [--rounds 3]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

import numpy as np  # noqa: E402

from baselab import macro_moves as mm  # noqa: E402
from baselab.archetypes import design  # noqa: E402
from baselab.evaluate import STRENGTH, defender_trophies, meta_scenarios, run_batch  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from proof_scorer import own, scrambled  # noqa: E402

SEARCH = lambda: meta_scenarios("ranked", 4, (0,))  # noqa: E731
GUIDE = lambda: meta_scenarios("ranked", 2, (2,), angle_offset=math.pi / 3)  # noqa: E731
HOLD = lambda: meta_scenarios("ranked", 4, (100, 101), angle_offset=math.pi / 4)  # noqa: E731
MOVES = "th_deepest,role_repack,role_repack_th,pull_strongest,splash_inward,spread_ads,fireball_spread,outer_screen,rotate_core,traps_to_core,traps_on_traffic"


def starts() -> dict:
    yb = own(Layout.load(ROOT / "data/reference-bases/your-base.json"))
    out = {"your-base": yb, "scrambled": scrambled(yb)}
    for k, s in (("organic", 9000), ("free", 9001), ("grid", 9002)):
        out[f"{k}-{s}"] = own(design(k, s))
    for f in sorted((ROOT / "data/builder-bases").glob("*-seed.json")):
        out[f.stem[:-5]] = own(Layout.load(f))
    return out


def per_battle(lays, scenarios):
    jobs = []
    for lay in lays:
        lj = lay.to_json()
        jobs += [(lj, sc, STRENGTH.get(sc.army, 1.0)) for sc in scenarios]
    res = run_batch(jobs)
    k = len(scenarios)
    return [np.array([defender_trophies(int(r[0]), r[1]) for r in res[n * k:(n + 1) * k]], dtype=float) for n in range(len(lays))]


def mean_se(t, w):
    m = float((w * t).sum())
    return m, float(math.sqrt((w ** 2 * (t - m) ** 2).sum()))


def weights(scenarios):
    w = np.array([s.weight for s in scenarios])
    return w / w.sum()


def children(lay, moves):
    out = []
    for mv in moves:
        kw = {}
        if mv == "traps_on_traffic":
            from baselab.diagnose import diagnose

            kw["diag"] = diagnose(lay, GUIDE())
        r = mm.apply(mv, lay, **kw)
        if r is not None:
            out.append((mv, r[0], r[1]))
    return out


def effects(names, moves):
    S = starts()
    sc = SEARCH()
    w = weights(sc)
    for n in names:
        kids = children(S[n], moves)
        t = per_battle([S[n]] + [k[1] for k in kids], sc)
        print(f"{n}: parent {mean_se(t[0], w)[0]:.2f}", flush=True)
        for (mv, _lay, desc), tc in zip(kids, t[1:]):
            d, se = mean_se(tc - t[0], w)
            print(f"  {mv:16s} {d:+6.2f} +- {se:4.2f}  {desc}", flush=True)


def repair(rounds, moves):
    S = starts()
    sc = SEARCH()
    w = weights(sc)
    cur = S["scrambled"]
    tcur = per_battle([cur], sc)[0]
    path = []
    for rnd in range(rounds):
        kids = children(cur, moves)
        if not kids:
            break
        ts = per_battle([k[1] for k in kids], sc)
        scored = []
        for (mv, lay, desc), tc in zip(kids, ts):
            d, se = mean_se(tc - tcur, w)
            scored.append((d, se, mv, lay, tc))
            print(f"  round {rnd + 1} {mv:16s} {d:+6.2f} +- {se:4.2f}  {desc}", flush=True)
        d, se, mv, lay, tc = max(scored, key=lambda s: s[0])
        if d <= max(0.3, se):
            break
        cur, tcur = lay, tc
        path.append(f"{mv} ({d:+.2f})")
    hold = HOLD()
    hw = weights(hold)
    t0, t1, t2 = per_battle([S["scrambled"], cur, S["your-base"]], hold)
    (m0, e0), (m1, e1), (m2, e2) = mean_se(t0, hw), mean_se(t1, hw), mean_se(t2, hw)
    g, ge = mean_se(t1 - t0, hw)
    print(f"path: {' -> '.join(path) or '(none)'}")
    print(f"hold-out ({len(hold)} battles): scrambled {m0:.2f} +- {e0:.2f} | repaired {m1:.2f} +- {e1:.2f} | unbroken {m2:.2f} +- {e2:.2f}")
    print(f"paired gain {g:+.2f} +- {ge:.2f}; recovered {g / (m2 - m0):.0%}")
    out = ROOT / "output" / "proof"
    out.mkdir(parents=True, exist_ok=True)
    cur.save(out / "macro-repaired.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["effects", "repair"])
    ap.add_argument("--starts", default="your-base,scrambled")
    ap.add_argument("--moves", default=MOVES)
    ap.add_argument("--rounds", type=int, default=3)
    a = ap.parse_args()
    if a.what == "effects":
        effects(a.starts.split(","), a.moves.split(","))
    else:
        repair(a.rounds, a.moves.split(","))


if __name__ == "__main__":
    main()
