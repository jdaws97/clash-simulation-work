"""Digitize a base from an in-game screenshot.

1. Fit the tile grid (grid_overlay.py parameters: cx, top, a, b).
2. `walls`: detect wall tiles. Walls show a bluish body at ground level and a
   bright steel cap ~12 px above; olive grass fails both tests. Runs of 3+
   tiles are kept, plus isolated "posts" that pass both tests strongly.
3. Write the buildings by hand in a text file, one per line:
       key x y [mode]
   (x, y = top tile of the footprint; keys as in baselab.mechanics).
4. `build`: combine walls + buildings into a layout JSON, minus walls under
   buildings, and render an overlay on the screenshot for checking.

Usage:
  python tools/baselab/digitize.py walls IMG --cx .. --top .. --a .. --b .. --out walls.json
  python tools/baselab/digitize.py build IMG --cx .. --top .. --a .. --b .. --walls walls.json --buildings b.txt --name NAME --out layout.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))


def detect_walls(img_path, p, lift=12.0):
    im = np.asarray(Image.open(img_path).convert("RGB")).astype(float)
    H, W, _ = im.shape

    def pr(x, y):
        return p["cx"] + (x - y) * p["a"], p["top"] + (x + y) * p["b"]

    def col(x, y, up):
        sx, sy = pr(x + 0.5, y + 0.5)
        sy -= up
        if not (3 <= sx < W - 3 and 3 <= sy < H - 3):
            return None
        return im[int(sy) - 2:int(sy) + 3, int(sx) - 2:int(sx) + 3].reshape(-1, 3).mean(0)

    cand, strong = set(), set()
    for x in range(44):
        for y in range(44):
            c0, c6, c1 = col(x, y, 0), col(x, y, lift / 2), col(x, y, lift)
            if c0 is None or c1 is None or c6 is None:
                continue
            # dark (purple/navy) walls: dark at ground and mid height, or bluish body
            dark = (c0.max() < 110 and c6.max() < 120) or ((c0[2] - c0[1]) > 5 and c0[2] > c0[0] - 15)
            # pale gold/white walls: very bright warm cap at mid height
            light = c6[0] > 205 and c6[1] > 170
            # steel cap (TH16 walls seen from above)
            cap = (c1[2] - c1[1]) > -12 and c1.min() > 120 and (c1[2] - c1[0]) > 0
            if dark or light or cap:
                cand.add((x, y))
            if (dark and cap) or light:
                strong.add((x, y))
    left, keep = set(cand), set()
    while left:
        s = left.pop()
        comp, st = {s}, [s]
        while st:
            x, y = st.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (x + dx, y + dy)
                    if n in left:
                        left.discard(n)
                        comp.add(n)
                        st.append(n)
        if len(comp) >= 3 or comp <= strong:
            keep |= comp
    return sorted(keep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["walls", "build"])
    ap.add_argument("image")
    for k in ("cx", "top", "a", "b"):
        ap.add_argument("--" + k, type=float, required=True)
    ap.add_argument("--walls")
    ap.add_argument("--buildings")
    ap.add_argument("--name", default="digitized")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    p = {"cx": args.cx, "top": args.top, "a": args.a, "b": args.b}
    if args.cmd == "walls":
        w = detect_walls(args.image, p)
        Path(args.out).write_text(json.dumps(w))
        print(len(w), "wall tiles")
        return
    from baselab.layout import Layout, Placement
    from grid_overlay import draw

    lay = Layout(args.name, town_hall=16)
    for line in Path(args.buildings).read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        parts = line.split()
        lay.buildings.append(Placement(parts[0], int(parts[1]), int(parts[2]), parts[3] if len(parts) > 3 else None))
    taken = set()
    for b in lay.buildings:
        taken.update(b.tiles())
    lay.walls = {tuple(w) for w in json.loads(Path(args.walls).read_text())} - taken
    lay.traps = []
    lay.save(Path(args.out))
    draw(Image.open(args.image), p, lay.to_json()).save(Path(args.out).with_suffix(".png"))
    probs = lay.problems(require_full=False)
    from collections import Counter
    from baselab.mechanics import INVENTORY

    c = Counter(b.key for b in lay.buildings)
    inv = INVENTORY[16]
    missing = {k: v - c[k] for k, v in inv.items() if v > c[k]}
    print(len(lay.buildings), "buildings,", len(lay.walls), "walls; problems:", probs[:8])
    print("missing vs TH16 inventory:", missing)


if __name__ == "__main__":
    main()
