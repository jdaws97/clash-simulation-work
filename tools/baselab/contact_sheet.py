"""Render a population of layouts as one contact sheet (small, labelled
with name and score), plus a full-size keyed image of each of the top N.

Usage: python tools/baselab/contact_sheet.py POPULATION.json --out DIR [--scores holdout.json] [--top 5]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.layout import Layout  # noqa: E402
from baselab.render import _font, render  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("population")
    ap.add_argument("--out", required=True)
    ap.add_argument("--labels", help="json {name: label}")
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    lays = [Layout.from_json(l) for l in json.loads(Path(args.population).read_text())]
    labels = json.loads(Path(args.labels).read_text()) if args.labels else {}
    tiles = []
    for k, lay in enumerate(lays):
        for b in lay.buildings:
            if b.key == "sweeper" and not b.mode:
                b.mode = "E"
        p = out / f"{k:02d}-{lay.name}.png"
        render(lay, p, title=f"#{k + 1} {lay.name}  {labels.get(lay.name, '')}")
        tiles.append(Image.open(p))
    cols = 4
    w, h = tiles[0].width // 3, tiles[0].height // 3
    sheet = Image.new("RGB", (cols * w, ((len(tiles) + cols - 1) // cols) * h), (20, 30, 20))
    d = ImageDraw.Draw(sheet)
    for k, (im, lay) in enumerate(zip(tiles, lays)):
        x, y = (k % cols) * w, (k // cols) * h
        sheet.paste(im.resize((w, h)), (x, y))
        d.rectangle([x, y, x + w - 1, y + 34], fill=(0, 0, 0))
        d.text((x + 8, y + 6), f"#{k + 1} {lay.name}  {labels.get(lay.name, '')}", fill=(255, 230, 120), font=_font(18))
    sheet.save(out / "contact-sheet.png")
    print(f"{len(lays)} bases -> {out / 'contact-sheet.png'}")


if __name__ == "__main__":
    main()
