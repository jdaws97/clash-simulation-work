"""Which heroes defend, and on which banner? Same battles for every option.

1. Every set of 4 defending heroes (from those given), each in a fixed
   order on the base's banners.
2. For the best set: all 24 orders on the 4 banners.
Scored on ranked and war (real meta armies, the user's levels).

Usage: python tools/baselab/hero_banners.py BASE.json [--heroes "Archer Queen" ...] [--sets-only]
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.evaluate import meta_scenarios  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from funnel import eval_many, own_levels  # noqa: E402

ALL = ["Barbarian King", "Archer Queen", "Grand Warden", "Royal Champion", "Minion Prince", "Dragon Duke"]
SHORT = {"Barbarian King": "King", "Archer Queen": "Queen", "Grand Warden": "Warden", "Royal Champion": "Champion",
         "Minion Prince": "Minion Prince", "Dragon Duke": "Duke"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--heroes", nargs="*", default=ALL)
    ap.add_argument("--slots", type=int, default=4)
    ap.add_argument("--orders-for", nargs="*", default=[], help='skip the set test; try every banner order for these sets, e.g. "Barbarian King,Grand Warden,Minion Prince,Dragon Duke"')
    ap.add_argument("--seeds", type=int, nargs="*", default=[5, 6])
    ap.add_argument("--out", default=str(ROOT / "output" / "hero-banners.json"))
    args = ap.parse_args()
    own = own_levels()
    base = Layout.load(args.base)
    base.levels, base.wall_level, base.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
    banners = [b for b in base.buildings if b.key == "banner"]
    th = next(b for b in base.buildings if b.key == "th")
    order = sorted(range(len(banners)), key=lambda i: abs(banners[i].x - th.x) + abs(banners[i].y - th.y))
    print("banners, nearest the Town Hall first:", [(banners[i].x, banners[i].y) for i in order], flush=True)
    sc = {m: meta_scenarios(m, 8, tuple(args.seeds)) for m in ("ranked", "war")}

    def variant(heroes_in_banner_order):
        lay = base.copy()
        lay.levels, lay.wall_level, lay.hero_levels = base.levels, base.wall_level, base.hero_levels
        # layout.heroes pairs with the banners in building-list order
        seq = [None] * len(banners)
        for slot, h in zip(order, heroes_in_banner_order):
            seq[slot] = h
        lay.heroes = [h for h in seq if h]
        return lay

    def score(lays):
        r = {m: eval_many(lays, s, m) for m, s in sc.items()}
        return [(r["ranked"][k][1], r["war"][k][1]) for k in range(len(lays))]

    def key(r):
        rk, wr = r[1]
        return -(rk.ranked_trophies - 4.0 * wr.three_star_rate)

    def show(label, rows):
        print(f"== {label}", flush=True)
        for hs, (rk, wr) in rows:
            print(f"  {' / '.join(SHORT[h] for h in hs):44s} ranked {rk.ranked_trophies:4.1f} trophies, 3* {rk.three_star_rate:4.0%} | war 3* {wr.three_star_rate:4.0%}", flush=True)

    out = {"banners_nearest_th_first": [(banners[i].x, banners[i].y) for i in order], "sets": [], "orders": []}
    if args.orders_for:
        best_sets = [tuple(x.split(",")) for x in args.orders_for]
    else:
        sets = list(itertools.combinations(args.heroes, min(args.slots, len(banners), len(args.heroes))))
        rows = sorted(zip(sets, score([variant(list(s)) for s in sets])), key=key)
        show("which heroes defend (fixed order on the banners)", rows)
        out["sets"] = [[list(s), rk.summary(), wr.summary()] for s, (rk, wr) in rows]
        best_sets = [rows[0][0]]
    for best in best_sets:
        perms = list(itertools.permutations(best))
        rows2 = sorted(zip(perms, score([variant(list(p)) for p in perms])), key=key)
        show(f"banner order for {', '.join(SHORT[h] for h in best)} (banners nearest the Town Hall first)", rows2)
        out["orders"] += [[list(p), rk.summary(), wr.summary()] for p, (rk, wr) in rows2]
        Path(args.out).write_text(json.dumps(out, indent=1))
    Path(args.out).write_text(json.dumps(out, indent=1))

if __name__ == "__main__":
    main()
