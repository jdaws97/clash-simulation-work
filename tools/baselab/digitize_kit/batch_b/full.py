"""full.py IMG cx top a b walls bfile OUT [lift] [scale]: whole-image overlay, walls drawn at cap height (lift)."""
import sys, json
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from PIL import Image, ImageDraw, ImageFont
from baselab.mechanics import BUILDING_TYPES
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); wf, bf, out = sys.argv[6:9]
lift = float(sys.argv[9]) if len(sys.argv) > 9 else 0; sc = float(sys.argv[10]) if len(sys.argv) > 10 else 1.0
P = lambda x, y, l=0: (cx + (x - y) * a, top + (x + y) * b - l)
im = Image.open(img).convert("RGBA"); ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
f = ImageFont.truetype("arialbd.ttf", 11)
for i in range(0, 45, 4):
    d.line([P(i, 0), P(i, 44)], fill=(255, 255, 0, 90)); d.line([P(0, i), P(44, i)], fill=(255, 255, 0, 90))
for x, y in (json.load(open(wf)) if wf != "-" else []):
    d.polygon([P(x + .25, y + .25, lift), P(x + .75, y + .25, lift), P(x + .75, y + .75, lift), P(x + .25, y + .75, lift)], fill=(255, 0, 255, 170))
if bf != "-":
    for line in open(bf):
        p = line.split("#")[0].split()
        if not p: continue
        k, x, y = p[0], int(p[1]), int(p[2])
        if k.startswith("T:"):
            k = k[2:]; s = 2 if k in ("giant", "giga") else 1
            d.polygon([P(x + .2, y + .2), P(x + s - .2, y + .2), P(x + s - .2, y + s - .2), P(x + .2, y + s - .2)], outline=(255, 140, 0, 255), width=2); continue
        s = BUILDING_TYPES[k].size
        d.polygon([P(x, y), P(x + s, y), P(x + s, y + s), P(x, y + s)], outline=(0, 255, 255, 230), width=2)
        tx, ty = P(x + s / 2, y + s / 2); d.text((tx - 12, ty - 6), k, fill=(0, 255, 255, 255), font=f, stroke_width=1, stroke_fill=(0, 0, 0, 255))
r = Image.alpha_composite(im, ov).convert("RGB")
if sc != 1: r = r.resize((int(r.width * sc), int(r.height * sc)), Image.LANCZOS)
r.save(out, quality=88)
