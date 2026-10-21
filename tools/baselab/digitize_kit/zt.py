"""zt.py IMG cx top a b buildings.txt OUT x y [r] [zoom]: zoomed crop around tile (x,y) with every tile labelled and current footprints."""
import sys
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from PIL import Image, ImageDraw, ImageFont
from baselab.mechanics import BUILDING_TYPES
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); bf, out = sys.argv[6], sys.argv[7]
tx, ty = float(sys.argv[8]), float(sys.argv[9]); r = float(sys.argv[10]) if len(sys.argv) > 10 else 5; z = float(sys.argv[11]) if len(sys.argv) > 11 else 2.5
P = lambda x, y: (cx + (x - y) * a, top + (x + y) * b)
im = Image.open(img).convert("RGB")
sx, sy = P(tx, ty); box = (int(sx - r * a), int(sy - r * b - 60), int(sx + r * a), int(sy + r * b))
c = im.crop(box).resize((int((box[2] - box[0]) * z), int((box[3] - box[1]) * z)), Image.LANCZOS).convert("RGBA")
ov = Image.new("RGBA", c.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
Q = lambda x, y: ((P(x, y)[0] - box[0]) * z, (P(x, y)[1] - box[1]) * z)
f = ImageFont.truetype("arialbd.ttf", 13); fb = ImageFont.truetype("arialbd.ttf", 18)
for i in range(44):
    for j in range(44):
        if abs(i + .5 - tx) > r + 3 or abs(j + .5 - ty) > r + 3: continue
        d.polygon([Q(i, j), Q(i + 1, j), Q(i + 1, j + 1), Q(i, j + 1)], outline=(255, 255, 255, 110))
        qx, qy = Q(i + .5, j + .5); d.text((qx - 14, qy - 7), f"{i},{j}", fill=(255, 255, 0, 200), font=f)
if bf != "-":
    for line in open(bf):
        p = line.split("#")[0].split()
        if not p or p[0].isdigit(): continue
        k, x, y = p[0], int(p[1]), int(p[2]); s = BUILDING_TYPES[k].size
        d.polygon([Q(x, y), Q(x + s, y), Q(x + s, y + s), Q(x, y + s)], outline=(0, 255, 255, 255), width=3)
        qx, qy = Q(x + s / 2, y + s / 2); d.text((qx - 20, qy - 10), k, fill=(0, 255, 255, 255), font=fb, stroke_width=2, stroke_fill=(0, 0, 0, 255))
Image.alpha_composite(c, ov).convert("RGB").save(out, quality=88)
