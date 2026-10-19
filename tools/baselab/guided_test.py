"""Check the battle tracer and the attack-aware moves on one original design.

Usage: python tools/baselab/guided_test.py
"""

from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.archetypes import design  # noqa: E402
from baselab.diagnose import diagnose  # noqa: E402
from baselab.evaluate import ranked_scenarios  # noqa: E402
from baselab.optimize import guided_move  # noqa: E402


def main():
    lay = design("organic", 3)
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
    t = time.time()
    sc = ranked_scenarios(n_angles=4, seeds=(0,))
    d = diagnose(lay, sc)
    print(f"diagnosis: {len(sc)} battles in {time.time() - t:.0f}s; broken wall tiles {len(d.wall_heat)}, "
          f"ground tiles {len(d.ground)}, air tiles {len(d.air)}, buildings that fell {len(d.early)}", flush=True)
    print("falls first:", sorted(((round(v, 2), lay.buildings[i].key) for i, v in d.early.items()), reverse=True)[:8], flush=True)
    rng = random.Random(0)
    kinds, bad = Counter(), 0
    for _ in range(300):
        n = lay.copy()
        r = guided_move(n, rng, d)
        if r:
            kinds[" ".join(r.split(" (")[0].split(" ")[:2])] += 1
            bad += bool(n.problems())
    print("moves made:", dict(kinds), "illegal:", bad, flush=True)


if __name__ == "__main__":
    main()
