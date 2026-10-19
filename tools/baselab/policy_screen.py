"""Screen attacker-policy changes one at a time before any long training run.

Every variant plays the same fixed list of battles as the default policy
(same base, army, attacker TH, side and skill seed; battles are
deterministic), so the comparison is paired and precise. Reports, per
variant: mean change in attacker fitness (stars + destruction/100) with its
standard error, change in 3-star rate, and the per-army change. Also prints
the noise numbers needed to size later training runs.

Usage: python tools/baselab/policy_screen.py --battles 400
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from train_policy import ARMIES, draw, library, play  # noqa: E402

VARIANTS = {
    "arrow aimed": {"arrow_aim": 1.0},
    "backpack aimed": {"dash_aim": 1.0},
    "distract drops": {"distract_reach": 6.0},
    "cc lure at 3s": {"lure_time": 3.0},
    "freeze needs 4 in range": {"freeze_min_units": 4.0},
    "freeze earlier (reach 3.5)": {"freeze_reach": 3.5},
    "invis later (hp 0.45)": {"invis_hp": 0.45},
    "invis sooner (1 hot)": {"invis_hot": 1.0},
    "commit after 5 down": {"commit_progress": 5.0},
    "commit after 1 down": {"commit_progress": 1.0},
    "abilities later (hp 0.3)": {"hero_hp": 0.3, "duke_hp": 0.4, "warden_hp": 0.25},
    "abilities sooner (hp 0.7)": {"hero_hp": 0.7, "duke_hp": 0.8, "warden_hp": 0.6},
    "rage sooner": {"rage_engaged": 0.25},
    "totem more": {"totem_min_threats": 2.0, "totem_gap": 3.0},
    "angry spell": {"angry_min": 3.0},
    "skeleton spell": {"skeleton_on": 1.0},
    "bat spell": {"bat_on": 1.0},
    "tank lead 1.5s": {"tank_lead": 1.5},
    "tank lead 3s": {"tank_lead": 3.0},
    "bundle (all positives)": {"hero_hp": 0.7, "duke_hp": 0.8, "warden_hp": 0.6, "arrow_aim": 1.0, "freeze_reach": 3.5,
                               "invis_hot": 1.0, "totem_min_threats": 2.0, "totem_gap": 3.0, "rage_engaged": 0.25},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--battles", type=int, default=400)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--meta", action="store_true", help="real TrophyCoach builds instead of the 4 scripted armies")
    args = ap.parse_args()
    lays = library()
    lj = [l.to_json() for l in lays]
    rng = np.random.default_rng(args.seed)
    armies = ARMIES
    if args.meta:
        from baselab.meta_armies import data

        armies = tuple(f"meta:{b['archetype']}-{b['th']}-{b['build']}" for b in data()["builds"])
    battles = draw(rng, lays, armies, args.battles)
    names = ["default"] + [v for v in VARIANTS if not args.only or v in args.only]
    pols = [{}] + [VARIANTS[v] for v in names[1:]]
    t0 = time.time()
    rows = play(lj, battles, pols)
    print(f"{len(battles)} battles x {len(pols)} policies in {time.time() - t0:.0f}s", flush=True)
    f0 = np.array([s + p / 100 for s, p in rows[0]])
    s0 = np.array([s >= 3 for s, _ in rows[0]])
    arm = np.array([b[1] for b in battles])
    print(f"default: fitness {f0.mean():.3f} (per-battle sd {f0.std():.2f}), 3* {s0.mean():5.1%}", flush=True)
    out = {}
    for n, r in zip(names[1:], rows[1:]):
        f = np.array([s + p / 100 for s, p in r])
        d = f - f0
        se = d.std() / math.sqrt(len(d))
        three = np.mean([s >= 3 for s, _ in r]) - s0.mean()
        fam = np.array([a.split(":")[-1].rsplit("-", 2)[0] for a in arm])
        per = {a: float(d[fam == a].mean()) for a in sorted(set(fam))}
        same = float(np.mean(d == 0))
        flag = "  <-- helps" if d.mean() > 2 * se else ("  <-- hurts" if d.mean() < -2 * se else "")
        print(f"{n:28s} {d.mean():+.3f} +- {se:.3f}  3* {three:+6.1%}  unchanged {same:4.0%}  "
              + " ".join(f"{a} {v:+.2f}" for a, v in per.items()) + flag, flush=True)
        out[n] = {"delta": float(d.mean()), "se": float(se), "three_star_delta": float(three), "per_army": per, "unchanged": same}
    # noise sizing: how many paired battles to see a 0.05 fitness change at 2 sigma
    sds = [v["se"] * math.sqrt(len(battles)) for v in out.values() if v["unchanged"] < 0.95]
    if sds:
        sd = float(np.median(sds))
        print(f"paired-difference sd {sd:.2f}: about {math.ceil((2 * sd / 0.05) ** 2)} battles to see a +0.05 change; "
              f"unpaired would need about {math.ceil((2 * f0.std() * math.sqrt(2) / 0.05) ** 2)}", flush=True)
    (ROOT / "output" / ("policy-screen.json" if not args.only else "policy-screen-focus.json")).write_text(json.dumps({"n": len(battles), "default_fitness": float(f0.mean()), "variants": out}, indent=1))


if __name__ == "__main__":
    main()
