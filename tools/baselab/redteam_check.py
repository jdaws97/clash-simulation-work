"""Red team vs scouting on real bases (docs/REDTEAM.md).

For each base and army: the scouting baseline of playbook_check.py (8 sides
x 2 charge flanks, best mean trophies on 4 seeds) and the red team
(src/baselab/redteam.py). Both picks are replayed on the same 20 fresh
seeds, so neither number carries winner's-curse optimism.

Usage: python tools/baselab/redteam_check.py A.json B.json [--armies ...]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

os.environ["BASELAB_PLAYBOOKS"] = "1"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.engine.plans import CENTER  # noqa: E402
from baselab.evaluate import STRENGTH  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.mechanics import MARGIN  # noqa: E402
from baselab.redteam import FRESH_SEEDS, Attack, Budget, _Evaluator, redteam  # noqa: E402

ARMIES = ["custom:user-rr", "custom:user-druid-ruin", "meta:mass-dragons-17-1"]


def scouting(lay, army):
    ev = _Evaluator(lay.to_json(), army, STRENGTH.get(army, 1.0))
    cands = [Attack(2 * math.pi * k / 8 + 0.1, side) for k in range(8) for side in ("left", "right")]
    seeds = tuple(range(700, 704))
    ev.run(cands, seeds)
    best = max(cands, key=lambda a: ev.score(a, seeds))
    insample = ev.score(best, seeds)[0]
    ev.run([best], FRESH_SEEDS)
    return best, insample, ev.score(best, FRESH_SEEDS), [ev.cache[(best, s)] for s in FRESH_SEEDS]


def eagle_angle(lay):
    e = next((b for b in lay.buildings if b.key == "eagle"), None)
    if e is None:
        return None
    # layout tiles -> battle world (MARGIN border), building centre
    x, y = e.x + MARGIN + 1.5, e.y + MARGIN + 1.5
    return math.degrees(math.atan2(y - CENTER, x - CENTER)) % 360


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bases", nargs="+")
    ap.add_argument("--armies", nargs="*", default=ARMIES)
    ap.add_argument("--out", default=str(ROOT / "output" / "redteam-check.json"))
    args = ap.parse_args()
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    out = {}
    for f in args.bases:
        lay = Layout.load(Path(f))
        lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
        name = Path(f).stem
        eag = eagle_angle(lay)
        out[name] = {"eagle_deg": eag}
        for army in args.armies:
            t0 = time.time()
            sb, s_in, (s_tr, s_pct), s_fresh = scouting(lay, army)
            t1 = time.time()
            r = redteam(lay, army, Budget(fresh_seeds=len(FRESH_SEEDS)), verbose=True)
            deg = math.degrees(r.attack.angle) % 360
            off = None if eag is None else round(abs((deg - eag + 180) % 360 - 180), 1)
            row = {
                "scout": {"attack": sb.describe(), "insample_tr": round(s_in, 2), "fresh_tr": round(s_tr, 2),
                          "fresh_pct": round(s_pct, 1), "fresh_3star": sum(x[0] >= 3 for x in s_fresh) / len(s_fresh),
                          "seconds": round(t1 - t0)},
                "redteam": {"attack": r.attack.describe(), "coarse": r.coarse_best.describe(),
                            "search_tr": round(r.search_trophies, 2), "fresh_tr": round(r.fresh_trophies, 2),
                            "fresh_pct": round(r.pct, 1), "fresh_3star": r.three_star, "battles": r.battles,
                            "seconds": round(r.seconds), "deg_from_eagle": off, "log": r.log, "sides": r.sides},
            }
            out[name][army] = row
            print(f"{name:18s} {army:26s} scout {s_tr:5.1f} tr ({s_in:4.1f} in-sample, {row['scout']['fresh_3star']:4.0%} 3*) "
                  f"| red team {r.fresh_trophies:5.1f} tr ({r.search_trophies:4.1f} search, {r.three_star:4.0%} 3*, {r.pct:5.1f}%) "
                  f"at {deg:5.1f} deg ({off} from Eagle) {r.battles} battles {r.seconds:4.0f}s", flush=True)
            Path(args.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
