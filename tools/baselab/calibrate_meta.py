"""Calibrate the real meta builds: for each TH16 build, find the attacker
strength at which its simulated 3-star rate on the real TH16 bases
(data/reference-bases, human-made, the user's levels) matches its real
same-Town-Hall 3-star rate (TrophyCoach). Scouting (best of SCOUT sides) and
the skill spread are applied as in evaluate.py.

TH17/18 builds have no same-TH real bases here, so they take the strength of
their archetype's TH16 build (1.0 when there is none) and are reported as
uncalibrated.

Usage: python tools/baselab/calibrate_meta.py [--angles 8] [--seeds 2]
Writes data/meta-calibration.json.
"""

from __future__ import annotations

import argparse
import glob
import itertools
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.evaluate import SCOUT, apply_charge, attacker_trophies, pool, skill, techniques  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.meta_armies import compose, data, plan_for_build  # noqa: E402


def _run(args):
    lj, build, angle, seed, strength, tech = args
    from baselab.engine.battle import Battle

    plan = plan_for_build(build, angle=angle, seed=seed)
    if tech is not None:
        apply_charge(plan, tech)
    plan.strength = strength * skill(seed)
    lay = Layout.from_json(lj)
    r = Battle(lay, plan, seed=seed, town_hall=lay.town_hall).run()
    return r.stars, r.destruction


TECH = False


def rate(lays, build, strength, angles, seeds):
    """Scouted 3-star rate: the attacker looks at SCOUT sides and, on each,
    picks the best of its techniques (with --techniques)."""
    techs = techniques(build) if TECH else [None]
    jobs, keys = [], []
    for bi, lj in enumerate(lays):
        for k in range(angles):
            for s in seeds:
                for tech in techs:
                    jobs.append((lj, build, 2 * math.pi * k / angles + 0.13 * bi, s * 11 + k, strength, tech))
                    keys.append((bi, s, k))
    res = list(pool().map(_run, jobs, chunksize=2))
    sides: dict = {}
    for key, r in zip(keys, res):
        sides.setdefault(key, []).append(r)
    groups: dict = {}
    for (bi, s, k), rows in sides.items():
        groups.setdefault((bi, s), []).append(max(rows, key=lambda r: (attacker_trophies(*r), r[1])))
    picked = []
    for rows in groups.values():
        for combo in itertools.combinations(rows, SCOUT):
            picked.append(max(combo, key=lambda r: (attacker_trophies(*r), r[1])))
    return sum(s >= 3 for s, _ in picked) / len(picked)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--angles", type=int, default=8)
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--techniques", action="store_true", help="attackers also pick hero charges (evaluate.techniques)")
    ap.add_argument("--out", default=str(ROOT / "data" / "meta-calibration.json"))
    args = ap.parse_args()
    global TECH
    TECH = args.techniques
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    lays = []
    for f in sorted(glob.glob(str(ROOT / "data" / "reference-bases" / "*.json"))):
        lay = Layout.load(f)
        lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
        lays.append(lay.to_json())
    seeds = tuple(range(args.seeds))
    out = {}
    for b in data()["builds"]:
        if b["th"] != 16:
            continue
        bid = f"{b['archetype']}-16-{b['build']}"
        target = b["three_star"]
        lo, hi = 0.4, 2.5
        r_lo, r_hi = rate(lays, b, lo, args.angles, seeds), rate(lays, b, hi, args.angles, seeds)
        print(f"{bid}: real 3* {target:.0%}; sim at {lo} -> {r_lo:.0%}, at {hi} -> {r_hi:.0%}", flush=True)
        if not r_lo <= target <= r_hi:
            s = lo if target < r_lo else hi
            out[bid] = {"strength": s, "sim": r_lo if s == lo else r_hi, "real": target, "clamped": True}
            print(f"  outside the range, clamped to {s}", flush=True)
            continue
        for _ in range(6):
            mid = math.sqrt(lo * hi)
            r = rate(lays, b, mid, args.angles, seeds)
            if r < target:
                lo = mid
            else:
                hi = mid
            print(f"  strength {mid:.3f} -> {r:.0%}", flush=True)
        s = math.sqrt(lo * hi)
        out[bid] = {"strength": s, "real": target, "clamped": False}
        print(f"  {bid}: strength {s:.3f}", flush=True)
    by_arch: dict = {}
    for bid, v in out.items():
        by_arch.setdefault(bid.rsplit("-", 2)[0], []).append(v["strength"])
    for b in data()["builds"]:
        if b["th"] == 16:
            continue
        bid = f"{b['archetype']}-{b['th']}-{b['build']}"
        st = by_arch.get(b["archetype"])
        out[bid] = {"strength": (sum(st) / len(st)) if st else 1.0, "real": b["three_star"], "uncalibrated": True}
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(f"saved {args.out}", flush=True)


if __name__ == "__main__":
    main()
