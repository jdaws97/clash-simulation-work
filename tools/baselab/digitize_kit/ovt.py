"""ovt.py IMG cx top a b OUTPREFIX cols rows [walls.json] [buildings.txt]: tiles of the village, every tile labelled, zoom 1.5"""
import sys, json
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from PIL import Image, ImageDraw, ImageFont
from baselab.mechanics import BUILDING_TYPES
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); pre = sys.argv[6]; cols, rows = int(sys.argv[7]), int(sys.argv[8])
wf = sys.argv[9] if len(sys.argv) > 9 else "-"; bf = sys.argv[10] if len(sys.argv) > 10 else "-"
P = lambda x, y: (cx + (x - y) * a, top + (x + y) * b)
im = Image.open(img).convert("RGBA"); over = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(over)
small = ImageFont.truetype("arialbd.ttf", int(__import__("os").environ.get("OVF", "10"))); font = ImageFont.truetype("arialbd.ttf", 16)
for i in range(45):
    col = (255, 255, 0, 170) if i % 4 == 0 else (255, 255, 255, 70)
    d.line([P(i, 0), P(i, 44)], fill=col, width=1); d.line([P(0, i), P(44, i)], fill=col, width=1)
for i in range(44):
    for j in range(44):
        if (i + j) % 2 == 0:
            d.polygon([P(i, j), P(i + 1, j), P(i + 1, j + 1), P(i, j + 1)], fill=(255, 255, 255, 28))
        sx, sy = P(i + .5, j + .5); d.text((sx - 9, sy - 5), f"{i},{j}", fill=(255, 255, 255, 170), font=small)
if wf != "-":
    for x, y in json.load(open(wf)):
        d.polygon([P(x + .3, y + .3), P(x + .7, y + .3), P(x + .7, y + .7), P(x + .3, y + .7)], fill=(255, 0, 255, 140))
if bf != "-":
    for line in open(bf):
        line = line.split("#")[0].split()
        if not line: continue
        k, x, y = line[0], int(line[1]), int(line[2])
        if k.isdigit():
            s = int(k); d.polygon([P(x, y), P(x + s, y), P(x + s, y + s), P(x, y + s)], outline=(255, 140, 0, 255), width=2); continue
        s = BUILDING_TYPES[k].size
        d.polygon([P(x, y), P(x + s, y), P(x + s, y + s), P(x, y + s)], outline=(0, 255, 255, 255), width=3)
        tx, ty = P(x + s / 2, y + s / 2); d.text((tx - 14, ty - 8), k, fill=(0, 255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0, 255))
r = Image.alpha_composite(im, over).convert("RGB")
xs = [P(0, 44)[0], P(44, 0)[0]]; ys = [max(0, P(0, 0)[1]), min(r.height, P(44, 44)[1])]
x0, x1 = max(0, int(xs[0]) - 20), min(r.width, int(xs[1]) + 20); y0, y1 = int(ys[0]), int(ys[1])
w, h = (x1 - x0) / cols, (y1 - y0) / rows
for rr in range(rows):
    for cc in range(cols):
        c = r.crop((int(x0 + cc * w - 30), int(y0 + rr * h - 30), int(x0 + (cc + 1) * w + 30), int(y0 + (rr + 1) * h + 30)))
        Z = float(__import__("os").environ.get("OVZ", "1.4")); c = c.resize((int(c.width * Z), int(c.height * Z)), Image.LANCZOS)
        c.save(f"{pre}_{rr}{cc}.jpg", quality=88)
