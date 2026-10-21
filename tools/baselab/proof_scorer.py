"""Proof test 1: can the scorer tell good bases from bad ones beyond its noise?

Each base is scored on two independent battle sets (different seeds and
sides; ranked meta attackers, red-team off). Known-bad variants of real bases
(no traps, no walls, defenses scrambled with non-defenses of the same size)
must score clearly lower than their originals on both sets, the two sets
must agree, and freshly generated designs give a baseline.

Score = expected defender trophies per ranked defense (higher is better),
with a standard error from the per-battle spread.

Usage: python tools/baselab/proof_scorer.py [--angles 4] [--seeds 2]
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

import numpy as np  # noqa: E402

from baselab.archetypes import design  # noqa: E402
from baselab.evaluate import STRENGTH, defender_trophies, meta_scenarios, run_batch  # noqa: E402
from baselab.layout import Layout  # noqa: E402

DEF = {"inferno", "eagle", "scatter", "xbow", "mono", "ad", "mat", "ric", "wt", "bt", "mortar", "at", "cannon",
       "sweeper", "tesla", "st", "crafting", "th"}


def own(lay):
    lv = json.loads((ROOT / "data" / "your-levels.json").read_text())
    lay.levels, lay.wall_level, lay.hero_levels = dict(lv["levels"]), lv["wall_level"], dict(lv["hero_levels"])
    return lay


def no_traps(lay):
    l = copy.deepcopy(lay)
    l.traps = []
    return l


def no_walls(lay):
    l = copy.deepcopy(lay)
    l.walls = set()
    return l


def scrambled(lay, seed=0):
    """Every defense trades places with a random non-defense of the same size."""
    l = copy.deepcopy(lay)
    rng = random.Random(seed)
    others = {}
    for b in l.buildings:
        if b.key not in DEF:
            others.setdefault(b.size, []).append(b)
    for b in l.buildings:
        if b.key in DEF and others.get(b.size):
            o = rng.choice(others[b.size])
            b.x, o.x = o.x, b.x
            b.y, o.y = o.y, b.y
    return l


def score(lays, scenarios):
    """Per base: (mean defender trophies, standard error, 3-star rate)."""
    jobs = []
    for l in lays:
        lj = l.to_json()
        jobs += [(lj, sc, STRENGTH.get(sc.army, 1.0)) for sc in scenarios]
    res = run_batch(jobs)
    k = len(scenarios)
    w = np.array([sc.weight for sc in scenarios])
    w = w / w.sum()
    out = []
    for n in range(len(lays)):
        r = res[n * k:(n + 1) * k]
        t = np.array([defender_trophies(int(x[0]), x[1]) for x in r], dtype=float)
        three = np.array([x[0] >= 3 for x in r], dtype=float)
        m = float((w * t).sum())
        se = float(math.sqrt((w ** 2 * (t - m) ** 2).sum()))
        out.append((m, se, float((w * three).sum())))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--angles", type=int, default=4)
    ap.add_argument("--seeds", type=int, default=2)
    args = ap.parse_args()
    bases = {}
    for name, f in (("your-base", ROOT / "data/reference-bases/your-base.json"),
                    ("hole-free", ROOT / "output/winners/ranked-holefree.json")):
        b = own(Layout.load(f))
        bases[name] = b
        bases[name + " / no traps"] = no_traps(b)
        bases[name + " / no walls"] = no_walls(b)
        bases[name + " / scrambled"] = scrambled(b)
    for i, kind in enumerate(["organic", "free", "wide"]):
        bases[f"random {kind}"] = own(design(kind, 9000 + i))
    names = list(bases)
    sets = {
        "set A": meta_scenarios("ranked", args.angles, tuple(range(args.seeds))),
        "set B": meta_scenarios("ranked", args.angles, tuple(range(100, 100 + args.seeds)), angle_offset=math.pi / args.angles),
    }
    results = {s: score([bases[n] for n in names], sc) for s, sc in sets.items()}
    print(f"battles per base per set: {len(sets['set A'])}")
    print(f"{'base':28s} {'set A trophies':>18s} {'set B trophies':>18s}   3-star A / B")
    for i, n in enumerate(names):
        a, b = results["set A"][i], results["set B"][i]
        print(f"{n:28s} {a[0]:7.2f} +- {a[1]:4.2f}     {b[0]:7.2f} +- {b[1]:4.2f}     {a[2]:5.1%} / {b[2]:5.1%}")
    print("\nchecks (difference original - variant, in units of the combined standard error):")
    ok = True
    for base in ("your-base", "hole-free"):
        i0 = names.index(base)
        for v in ("no traps", "no walls", "scrambled"):
            i1 = names.index(f"{base} / {v}")
            zs = []
            for s in sets:
                (m0, e0, _), (m1, e1, _) = results[s][i0], results[s][i1]
                zs.append((m0 - m1) / math.sqrt(e0 ** 2 + e1 ** 2 + 1e-9))
            passed = all(z > 2 for z in zs)
            ok &= passed
            print(f"  {base:10s} vs {v:9s}: z = {zs[0]:5.1f} (A), {zs[1]:5.1f} (B)  {'PASS' if passed else 'FAIL'}")
    a = np.array([r[0] for r in results["set A"]])
    b = np.array([r[0] for r in results["set B"]])
    corr = float(np.corrcoef(a, b)[0, 1])
    print(f"  agreement between set A and set B over all {len(names)} bases: r = {corr:.2f} {'PASS' if corr > 0.8 else 'FAIL'}")
    ok &= corr > 0.8
    print("OVERALL", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
