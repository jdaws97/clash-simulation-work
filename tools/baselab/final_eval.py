"""Final comparison of defense bases on large held-out scenario sets.

Scores your current base, the optimized ranked and war winners and the human
reference bases on: ranked (Electro, no modifier), ranked under Legend III and
Legend I modifiers, and war. Writes output/final-defense.json plus a build
list (tile coordinates) for each optimized base.

Usage: python tools/baselab/final_eval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.evaluate import evaluate, ranked_scenarios, war_scenarios, with_modifier  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.mechanics import BUILDING_TYPES, TRAP_NAMES  # noqa: E402
from baselab.optimize import hole_tiles  # noqa: E402


def build_list(lay: Layout) -> dict:
    """Human-readable placement list. Tile (x, y): (0, 0) is the top corner of
    the village, x runs down-right, y runs down-left; a building of size s
    covers x..x+s-1, y..y+s-1."""
    rows = []
    for b in sorted(lay.buildings, key=lambda b: (BUILDING_TYPES[b.key].kind != "defense", b.key, b.x, b.y)):
        rows.append({"building": BUILDING_TYPES[b.key].name, "x": b.x, "y": b.y, "size": BUILDING_TYPES[b.key].size, "mode": b.mode})
    traps = [{"trap": TRAP_NAMES[t.key], "x": t.x, "y": t.y, "mode": t.mode} for t in lay.traps]
    return {"name": lay.name, "town_hall": lay.town_hall, "buildings": rows, "traps": traps,
            "walls": sorted([list(w) for w in lay.walls]), "cc_troops": lay.cc_troops, "heroes": lay.heroes}


def main():
    out_dir = ROOT / "output" / "bases"
    cands = {"your-base": Layout.load(ROOT / "data" / "reference-bases" / "your-base.json")}
    for mode in ("ranked", "war"):
        f = out_dir / f"{mode}-winner.json"
        if f.exists():
            cands[f"{mode}-winner"] = Layout.load(f)
        for k in (1, 2):
            g = out_dir / f"{mode}-best-{k}.json"
            if g.exists():
                cands[f"{mode}-best-{k}"] = Layout.load(g)
    for f in sorted((ROOT / "data" / "reference-bases").glob("real-*.json")):
        if f.stem != "real-l4x":  # same layout as your-base before corrections
            cands[f.stem] = Layout.load(f)
    ranked = ranked_scenarios(n_angles=12, seeds=(4, 5))
    sets = {
        "ranked": ranked,
        "ranked_legend3": with_modifier(ranked, "legend3"),
        "ranked_legend1": with_modifier(ranked, "legend1"),
        "war": war_scenarios(n_angles=12, seeds=(4, 5)),
        # the user's 13 logged ranked defenses (TH16 x5, TH17 x8) for checking
        # the simulator against reality
        "logmix": ranked_scenarios(n_angles=12, seeds=(4, 5), mix={
            ("hydra", 16): 2 / 13, ("throwers", 16): 1 / 13, ("rootrider", 16): 2 / 13, ("hydra", 17): 2 / 13,
            ("throwers", 17): 2 / 13, ("edrag", 17): 3 / 13, ("rootrider", 17): 1 / 13}),
    }
    report = {}
    for name, lay in cands.items():
        report[name] = {"holes": hole_tiles(lay)}
        for sname, sc in sets.items():
            ev = evaluate(lay, sc)
            report[name][sname] = {
                "defender_trophies": round(ev.ranked_trophies, 2), "three_star": round(ev.three_star_rate, 3),
                "avg_stars": round(ev.avg_stars, 2), "avg_destruction": round(ev.avg_destruction, 1),
                "th_killed": round(ev.th_kill_rate, 3), "per_army": ev.per_army,
            }
            print(f"{name:14s} {sname:15s} {ev.summary()}", flush=True)
    (ROOT / "output" / "final-defense.json").write_text(json.dumps(report, indent=1))
    for name in ("ranked-winner", "war-winner"):
        if name in cands:
            (out_dir / f"{name}-build-list.json").write_text(json.dumps(build_list(cands[name]), indent=1))
    print("wrote output/final-defense.json")


if __name__ == "__main__":
    main()
