"""Re-place a base's traps where the attacks actually go.

Traps are cheap to move and barely change pathing, so they can be tuned on
their own. Each round traces the attack set against the base
(diagnose.py), then for every trap tries the hottest legal tiles of the
traffic that trap punishes (Giant Bombs on ground packs, Seeking Air Mines
on Healers and flying heroes, Tornado and ground Skeletons on hero charges,
diagnose.TRAP_TRAFFIC). A move is kept only if it raises the objective on
the search battles (same seeds for every candidate). The final layout is
compared with the original on fresh hold-out battles.

Usage: python tools/baselab/trap_polish.py BASE.json --out OUT.json
         [--mode ranked] [--rounds 2] [--tiles 6] [--angles 8]
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.diagnose import diagnose  # noqa: E402
from baselab.evaluate import evaluate, meta_scenarios, war_scenarios  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.optimize import _fits, _occupied, objective  # noqa: E402


def scen(mode, n, seeds):
    if os.environ.get("BASELAB_PLAYBOOKS") == "1" or mode == "ranked":
        return meta_scenarios(mode, n, seeds)
    return war_scenarios(n_angles=n, seeds=seeds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["ranked", "war"], default="ranked")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--tiles", type=int, default=6, help="candidate tiles tried per trap per round")
    ap.add_argument("--angles", type=int, default=8)
    args = ap.parse_args()

    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    lay = Layout.load(Path(args.base))
    lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
    search = scen(args.mode, args.angles, (0, 1))
    holdout = scen(args.mode, args.angles, (11, 12, 13))

    def score(layout):
        return objective(evaluate(layout, search), args.mode, layout)

    best = score(lay)
    print(f"start {best:.2f}", flush=True)
    for rnd in range(args.rounds):
        diag = diagnose(lay, search)
        moved = 0
        for i in range(len(lay.traps)):
            t = lay.traps[i]
            occ = _occupied(lay, skip_trap=i)
            tried = 0
            for (x, y), _ in diag.trap_tiles(t.key, t.mode, 80):
                if tried >= args.tiles:
                    break
                if (x, y) == (t.x, t.y) or not _fits(occ, x, y, t.size):
                    continue
                tried += 1
                cand = copy.deepcopy(lay)
                cand.traps[i].x, cand.traps[i].y = x, y
                s = score(cand)
                if s > best + 0.05:
                    print(f"  round {rnd} {t.key}{'/' + t.mode if t.mode else ''} ({t.x},{t.y}) -> ({x},{y}): {best:.2f} -> {s:.2f}", flush=True)
                    lay, best = cand, s
                    moved += 1
                    break
        print(f"round {rnd}: {moved} traps moved, search score {best:.2f}", flush=True)
        if not moved:
            break

    start = Layout.load(Path(args.base))
    start.levels, start.wall_level, start.hero_levels = lay.levels, lay.wall_level, lay.hero_levels
    for name, layout in (("original", start), ("polished", lay)):
        ev = evaluate(layout, holdout)
        print(f"hold-out {name:9s} {objective(ev, args.mode, layout):6.2f}  {ev.summary()}", flush=True)
    lay.name = (lay.name or Path(args.base).stem) + "-traps"
    Path(args.out).write_text(json.dumps(lay.to_json(), indent=1))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
