"""Paired screen of hero charges (Queen, Royal Champion, Dragon Duke,
Barbarian King) against no charge, on the same battles: real meta builds
that bring the hero, across the base library, random sides and skill seeds.

Usage: python tools/baselab/charge_screen.py --battles 300
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.evaluate import STRENGTH, pool, skill  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.meta_armies import data  # noqa: E402
from baselab.tactics import DEFAULT, NAMES  # noqa: E402
from train_policy import library  # noqa: E402

VARIANTS = {
    "none": None,
    "Queen charge, 4 Healers": (1, 4),
    "Royal Champion charge, 2 Healers": (2, 2),
    "Dragon Duke charge": (3, 0),
    "Barbarian King charge, 3 Healers": (4, 3),
}


def _run(args):
    lj, bid, angle, seed, vec = args
    from baselab.engine.battle import Battle
    from baselab.meta_armies import build_by_id, compose
    from baselab.tactics import apply

    b = build_by_id(bid)
    plan = compose(b, angle=angle, seed=seed)
    apply(plan, vec)
    plan.strength = STRENGTH.get("meta:" + bid, 1.0) * skill(seed)
    lay = Layout.from_json(lj)
    r = Battle(lay, plan, seed=seed, town_hall=lay.town_hall).run()
    return r.stars, r.destruction


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--battles", type=int, default=300)
    args = ap.parse_args()
    rng = np.random.default_rng(5)
    lays = [l.to_json() for l in library()]
    builds = [f"{b['archetype']}-{b['th']}-{b['build']}" for b in data()["builds"]]
    battles = []
    for _ in range(args.battles):
        battles.append((int(rng.integers(len(lays))), builds[int(rng.integers(len(builds)))],
                        float(rng.uniform(0, 2 * math.pi)), int(rng.integers(10**6)), float(rng.uniform(-6, 6)), float(rng.uniform(0, 4))))
    names = list(VARIANTS)
    jobs = []
    for n in names:
        for li, bid, ang, seed, lat, at in battles:
            v = DEFAULT.copy()
            v[0] = ang
            if VARIANTS[n]:
                pick, healers = VARIANTS[n]
                v[NAMES.index("charge_pick")] = pick + 0.5
                v[NAMES.index("charge_healers")] = healers + 0.5
                v[NAMES.index("charge_lat")] = lat
                v[NAMES.index("charge_at")] = at
            jobs.append((lays[li], bid, ang, seed, tuple(map(float, v))))
    res = list(pool().map(_run, jobs, chunksize=2))
    k = len(battles)
    F = {n: np.array([s + p / 100 for s, p in res[i * k:(i + 1) * k]]) for i, n in enumerate(names)}
    S = {n: np.array([s >= 3 for s, _ in res[i * k:(i + 1) * k]]) for i, n in enumerate(names)}
    print(f"{k} paired battles; no charge: fitness {F['none'].mean():.3f}, 3* {S['none'].mean():.1%}", flush=True)
    for n in names[1:]:
        d = F[n] - F["none"]
        changed = d != 0
        se = d.std() / math.sqrt(k)
        flag = "  <-- helps" if d.mean() > 2 * se else ("  <-- hurts" if d.mean() < -2 * se else "")
        print(f"{n:34s} {d.mean():+.3f} +- {se:.3f}  3* {S[n].mean() - S['none'].mean():+6.1%}  "
              f"(applies in {changed.mean():4.0%} of battles; mean change where it applies {d[changed].mean() if changed.any() else 0:+.3f}){flag}", flush=True)


if __name__ == "__main__":
    main()
