"""Re-place a base's traps where the attacks actually go.

Traps are cheap to move and barely change pathing, so they can be tuned on
their own. Each round traces the attack set against the base
(diagnose.py), then for every trap tries the hottest legal tiles of the
traffic that trap punishes (Giant Bombs on ground packs, Seeking Air Mines
on Healers and flying heroes, Tornado and ground Skeletons on hero charges,
diagnose.TRAP_TRAFFIC). All candidate moves are screened in one batch on a
cheap common battle set; the best few are confirmed on the search battles,
and confirmed moves are combined one by one, each kept only if the search
score still rises. The final layout is
compared with the original on fresh hold-out battles.

Usage: python tools/baselab/trap_polish.py BASE.json --out OUT.json
         [--mode ranked] [--rounds 2] [--tiles 6] [--angles 8]
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.diagnose import diagnose  # noqa: E402
from baselab.evaluate import evaluate, meta_scenarios, war_scenarios  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.optimize import _fits, _occupied, objective  # noqa: E402

sys.path.insert(0, str(ROOT / "tools" / "baselab"))
from funnel import eval_many  # noqa: E402


def scen(mode, n, seeds, angle_offset=0.0):
    if os.environ.get("BASELAB_PLAYBOOKS") == "1" or mode == "ranked":
        return meta_scenarios(mode, n, seeds, angle_offset=angle_offset)
    return war_scenarios(n_angles=n, seeds=seeds, angle_offset=angle_offset)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["ranked", "war"], default="ranked")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--tiles", type=int, default=6, help="candidate tiles tried per trap per round")
    ap.add_argument("--angles", type=int, default=8)
    ap.add_argument("--confirm", type=int, default=8, help="best screened moves confirmed on the search set")
    args = ap.parse_args()

    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    lay = Layout.load(Path(args.base))
    lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
    search = scen(args.mode, args.angles, (0, 1))
    # fresh sides halfway between the search's (same angles with seed 11
    # would replay seed 1: same skill quantile and charge flank)
    holdout = scen(args.mode, args.angles, (11, 12, 13), math.pi / args.angles)

    quick = scen(args.mode, 4, (0,))  # cheap common screen for every candidate move

    def score(layout):
        return objective(evaluate(layout, search), args.mode, layout)

    best = score(lay)
    print(f"start {best:.2f} (search set, {len(search)} battles)", flush=True)
    for rnd in range(args.rounds):
        diag = diagnose(lay, search)
        # every candidate move: each trap onto the hottest legal tiles of the
        # traffic it punishes; all screened in one batch on the same battles
        moves, cands = [], []
        for i, t in enumerate(lay.traps):
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
                moves.append((i, x, y))
                cands.append(cand)
        scored = eval_many([lay] + cands, quick, args.mode)
        base_q = scored[0][0]
        ranked = sorted(zip(moves, cands, (s for s, _ in scored[1:])), key=lambda m: -m[2])
        top = [m for m in ranked if m[2] > base_q][: args.confirm]
        print(f"round {rnd}: {len(moves)} moves screened ({len(quick)} battles each), {len(top)} confirmed on the search set", flush=True)
        if not top:
            break
        full = eval_many([c for _, c, _ in top], search, args.mode)
        good = sorted(((m, c, s) for (m, c, _), (s, _) in zip(top, full) if s > best + 0.05), key=lambda m: -m[2])
        moved, used = 0, set()
        for (i, x, y), cand, s in good:
            if i in used:
                continue
            trial = copy.deepcopy(lay)
            if not _fits(_occupied(trial, skip_trap=i), x, y, trial.traps[i].size):
                continue
            t = trial.traps[i]
            old = (t.x, t.y)
            t.x, t.y = x, y
            ts = score(trial) if moved else s
            if ts > best + 0.05:
                print(f"  {t.key}{'/' + t.mode if t.mode else ''} {old} -> ({x},{y}): {best:.2f} -> {ts:.2f}", flush=True)
                lay, best = trial, ts
                used.add(i)
                moved += 1
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
