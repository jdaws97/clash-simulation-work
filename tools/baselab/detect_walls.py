"""Detect wall tiles on a screenshot with a fitted tile grid (grid_overlay.py
parameters). Walls have bluish-steel stone caps raised about half a tile; the
score compares blue against green/red at that height. Prints candidate tiles
and writes an overlay for manual checking.

Usage: python tools/baselab/detect_walls.py IMG --cx .. --top .. --a .. --b .. --out walls.json [--thr 10]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    for k in ("cx", "top", "a", "b"):
        ap.add_argument("--" + k, type=float, required=True)
    ap.add_argument("--thr", type=float, default=10.0)
    ap.add_argument("--lift", type=float, default=0.55, help="wall cap height in tile half-heights")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    img = Image.open(args.image).convert("RGB")
    im = np.asarray(img).astype(float)
    H, W, _ = im.shape

    def pr(x, y):
        return args.cx + (x - y) * args.a, args.top + (x + y) * args.b

    scores = {}
    for x in range(44):
        for y in range(44):
            sx, sy = pr(x + 0.5, y + 0.5)
            sy -= args.lift * args.b * 2
            if not (3 <= sx < W - 3 and 3 <= sy < H - 3):
                continue
            c = im[int(sy) - 2:int(sy) + 3, int(sx) - 2:int(sx) + 3].reshape(-1, 3).mean(0)
            scores[(x, y)] = float((c[2] - c[1]) + 0.3 * (c[2] - c[0]))
    walls = sorted(k for k, v in scores.items() if v >= args.thr)
    Path(args.out).write_text(json.dumps({"walls": walls, "scores": {f"{k[0]},{k[1]}": round(v, 1) for k, v in scores.items()}}))
    ov = img.copy()
    d = ImageDraw.Draw(ov)
    for x, y in walls:
        pts = [pr(x + 0.25, y + 0.25), pr(x + 0.75, y + 0.25), pr(x + 0.75, y + 0.75), pr(x + 0.25, y + 0.75)]
        d.polygon(pts, outline=(255, 0, 255))
    ov.save(Path(args.out).with_suffix(".png"))
    print(len(walls), "candidate wall tiles")


if __name__ == "__main__":
    main()
