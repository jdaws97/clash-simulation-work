"""Bit-for-bit fingerprint of a fixed set of battles, for speed work that must
not change results. Runs N battles (bases x armies x sides x seeds) in this
process, hashes each battle's full event log and result, and either writes
the fingerprint (--save) or compares with a saved one. Also reports the
average wall time per battle.

Usage: python tools/baselab/fingerprint.py --save output/fingerprint.json
       python tools/baselab/fingerprint.py --check output/fingerprint.json
       python tools/baselab/fingerprint.py --profile   (cProfile of one battle)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("BASELAB_PLAYBOOKS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

BASES = ["data/reference-bases/your-base.json", "data/reference-bases/real-l3x.json"]
ARMIES = ["custom:user-rr", "custom:user-druid-ruin", "meta:mass-dragons-17-1", "meta:mass-thrower-17-1",
          "meta:e-drag-spam-18-1", "meta:root-rider-18-1"]


def battles():
    for b in BASES:
        for a in ARMIES:
            for k in (0, 3):
                yield b, a, 2 * math.pi * k / 8 + 0.1, 11 + k


def run_one(base, army, angle, seed):
    from baselab.engine.battle import Battle
    from baselab.evaluate import STRENGTH, skill
    from baselab.layout import Layout
    from baselab.meta_armies import make_plan

    lv = json.loads((ROOT / "data" / "your-levels.json").read_text())
    lay = Layout.load(ROOT / base)
    lay.levels, lay.wall_level, lay.hero_levels = dict(lv["levels"]), lv["wall_level"], dict(lv["hero_levels"])
    plan = make_plan(army, angle, 16, seed)
    plan.strength = STRENGTH.get(army, 1.0) * skill(seed)
    b = Battle(lay, plan, seed=seed, town_hall=16, record=True)
    r = b.run()
    h = hashlib.sha256(repr((r.stars, r.destruction, round(r.time, 6), b.log)).encode()).hexdigest()
    return h, r.stars, r.destruction, round(r.time, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save")
    ap.add_argument("--check")
    ap.add_argument("--profile", action="store_true")
    args = ap.parse_args()
    if args.profile:
        import cProfile
        import pstats

        cProfile.runctx("run_one(*next(iter(battles())))", globals(), locals(), str(ROOT / "output" / "profile.out"))
        cProfile.runctx("run_one(BASES[0], 'meta:mass-dragons-17-1', 0.1, 11)", globals(), locals(), str(ROOT / "output" / "profile2.out"))
        for f in ("profile.out", "profile2.out"):
            print(f"== {f}")
            pstats.Stats(str(ROOT / "output" / f)).sort_stats("tottime").print_stats(25)
        return
    out, t0 = {}, time.time()
    for key in battles():
        out["|".join(map(str, key))] = run_one(*key)
    dt = (time.time() - t0) / len(out)
    print(f"{len(out)} battles, {dt:.2f} s per battle (single process)")
    if args.save:
        Path(args.save).write_text(json.dumps(out, indent=1))
        print("saved", args.save)
    if args.check:
        ref = json.loads(Path(args.check).read_text())
        bad = [k for k in ref if ref[k][0] != out.get(k, [None])[0]]
        print("IDENTICAL" if not bad else f"DIFFERENT in {len(bad)} of {len(ref)} battles: {bad[:5]}")


if __name__ == "__main__":
    main()
