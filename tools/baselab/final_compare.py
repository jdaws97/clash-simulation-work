"""Overnight wrap-up: every funnel winner next to the user's bases and the
remixes, on fresh battles (seeds no search used), per mode; renders the
winners and writes output/funnel/final.json.

Usage: python tools/baselab/final_compare.py
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.evaluate import meta_scenarios  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.render import render  # noqa: E402
from funnel import eval_many, own_levels  # noqa: E402

REFS = {"your current base": "data/reference-bases/your-base.json", "your l6x": "data/reference-bases/real-l6x.json",
        "ranked remix": "output/bases-deep/ranked-winner.json", "war remix": "output/bases-deep/war-winner.json"}


def main():
    own = own_levels()
    out = {}
    for mode in ("ranked", "war"):
        cands = dict(REFS)
        for f in sorted(glob.glob(str(ROOT / "output" / "funnel" / f"{mode}-*" / "evolve" / "best.json"))):
            cands[f"funnel {Path(f).parents[1].name}"] = f
        lays, names = [], []
        for n, f in cands.items():
            p = ROOT / f if not Path(f).is_absolute() else Path(f)
            if p.exists():
                lay = Layout.load(p)
                lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
                lays.append(lay)
                names.append(n)
        sc = meta_scenarios(mode, 8, (5, 6, 7))
        res = eval_many(lays, sc, mode)
        rows = sorted(zip(names, res, lays), key=lambda r: -r[1][0])
        print(f"== {mode}: {len(sc)} fresh battles per base (real meta armies, your levels)", flush=True)
        for n, (s, ev), lay in rows:
            print(f"  {n:24s} score {s:6.2f}  {ev.summary()}", flush=True)
        out[mode] = [{"name": n, "score": s, "summary": ev.summary()} for n, (s, ev), _ in rows]
        for n, (s, ev), lay in rows:
            if n.startswith("funnel"):
                render(lay, ROOT / "output" / "funnel" / f"final-{mode}-{n.split()[-1]}.png", title=f"{mode} {n}: {ev.summary()}")
    (ROOT / "output" / "funnel" / "final.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
