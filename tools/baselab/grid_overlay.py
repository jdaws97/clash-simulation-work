"""Overlay the 44x44 village tile grid on an in-game screenshot.

Used to digitize real bases: fit the isometric projection to the village
diamond, draw tile lines with coordinates, then read building positions off
zoomed crops. Tile (x, y): (0, 0) is the top corner, x runs down-right and y
runs down-left (same convention as baselab.layout).

    screen_x = cx + (x - y) * a
    screen_y = top_y + (x + y) * b

Usage:
  python tools/baselab/grid_overlay.py IMG.png --cx 1395 --top -195 --a 22.8 --b 16.8 --out out.png
  ... --layout base.json   # also draw a digitized layout's footprints for checking
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

N = 44


def project(x, y, p):
    return p["cx"] + (x - y) * p["a"], p["top"] + (x + y) * p["b"]


def draw(img: Image.Image, p: dict, layout: dict | None = None) -> Image.Image:
    im = img.convert("RGBA")
    over = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    try:
        font = ImageFont.truetype("arial.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
    for i in range(N + 1):
        col = (255, 255, 0, 200) if i % 4 == 0 else (255, 255, 255, 90)
        w = 2 if i % 4 == 0 else 1
        d.line([project(i, 0, p), project(i, N, p)], fill=col, width=w)
        d.line([project(0, i, p), project(N, i, p)], fill=col, width=w)
    for i in range(0, N, 2):
        for j in range(0, N, 4):
            sx, sy = project(i + 0.5, j + 0.5, p)
            d.text((sx - 10, sy - 7), f"{i},{j}", fill=(255, 255, 255, 230), font=font)
    if layout:
        from baselab.layout import Layout
        from baselab.mechanics import BUILDING_TYPES

        lay = Layout.from_json(layout)
        for b in lay.buildings:
            s = BUILDING_TYPES[b.key].size
            pts = [project(b.x, b.y, p), project(b.x + s, b.y, p), project(b.x + s, b.y + s, p), project(b.x, b.y + s, p)]
            d.polygon(pts, outline=(0, 255, 255, 255), width=3)
            cx, cy = project(b.x + s / 2, b.y + s / 2, p)
            d.text((cx - 14, cy - 7), b.key, fill=(0, 255, 255, 255), font=font)
        for (x, y) in lay.walls:
            pts = [project(x + 0.2, y + 0.2, p), project(x + 0.8, y + 0.2, p), project(x + 0.8, y + 0.8, p), project(x + 0.2, y + 0.8, p)]
            d.polygon(pts, fill=(255, 0, 255, 120))
        for t in lay.traps:
            cx, cy = project(t.x + 0.5, t.y + 0.5, p)
            d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], outline=(255, 80, 0, 255), width=2)
    return Image.alpha_composite(im, over).convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--cx", type=float, required=True)
    ap.add_argument("--top", type=float, required=True)
    ap.add_argument("--a", type=float, required=True)
    ap.add_argument("--b", type=float, required=True)
    ap.add_argument("--layout")
    ap.add_argument("--out", required=True)
    ap.add_argument("--crop", nargs=4, type=int, action="append", help="x0 y0 x1 y1 crops saved next to --out")
    args = ap.parse_args()
    p = {"cx": args.cx, "top": args.top, "a": args.a, "b": args.b}
    lay = json.loads(Path(args.layout).read_text()) if args.layout else None
    out = draw(Image.open(args.image), p, lay)
    out.save(args.out)
    for k, c in enumerate(args.crop or []):
        out.crop(tuple(c)).save(Path(args.out).with_name(Path(args.out).stem + f"-crop{k}.png"))


if __name__ == "__main__":
    main()
