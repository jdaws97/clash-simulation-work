"""ovl.py IMG cx top a b walls.json buildings.txt OUT [x0 y0 x1 y1] [scale] : overlay walls (magenta) + building footprints (cyan) with labels."""
import sys, json
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from PIL import Image, ImageDraw, ImageFont
from baselab.mechanics import BUILDING_TYPES
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); wf, bf, out = sys.argv[6:9]
crop = tuple(map(int, sys.argv[9:13])) if len(sys.argv) > 12 else None
scale = float(sys.argv[13]) if len(sys.argv) > 13 else 1.0
P = lambda x, y: (cx + (x - y) * a, top + (x + y) * b)
im = Image.open(img).convert("RGBA"); over = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(over)
font = ImageFont.truetype("arial.ttf", 15); small = ImageFont.truetype("arial.ttf", 11)
for i in range(45):
    col = (255, 255, 0, 160) if i % 4 == 0 else (255, 255, 255, 60)
    d.line([P(i, 0), P(i, 44)], fill=col, width=1); d.line([P(0, i), P(44, i)], fill=col, width=1)
for i in range(0, 44, 2):
    for j in range(0, 44, 2):
        sx, sy = P(i + .5, j + .5); d.text((sx - 9, sy - 6), f"{i},{j}", fill=(255, 255, 255, 150), font=small)
walls = json.load(open(wf)) if wf != "-" else []
for x, y in walls:
    d.polygon([P(x + .25, y + .25), P(x + .75, y + .25), P(x + .75, y + .75), P(x + .25, y + .75)], fill=(255, 0, 255, 150))
if bf != "-":
    for line in open(bf):
        line = line.split("#")[0].split()
        if not line: continue
        k, x, y = line[0], int(line[1]), int(line[2]); s = BUILDING_TYPES[k].size
        d.polygon([P(x, y), P(x + s, y), P(x + s, y + s), P(x, y + s)], outline=(0, 255, 255, 255), width=3)
        tx, ty = P(x + s / 2, y + s / 2); d.text((tx - 14, ty - 8), k, fill=(0, 255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0, 255))
r = Image.alpha_composite(im, over).convert("RGB")
if crop: r = r.crop(crop)
if scale != 1: r = r.resize((int(r.width * scale), int(r.height * scale)))
r.save(out, quality=88)
