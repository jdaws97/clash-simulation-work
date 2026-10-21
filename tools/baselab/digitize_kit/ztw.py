"""ztw.py IMG cx top a b walls.json buildings.txt OUT x y r zoom : zoom with walls (magenta dots) + footprints."""
import sys, json, subprocess
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from PIL import Image, ImageDraw, ImageFont
from baselab.mechanics import BUILDING_TYPES
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); wf, bf, out = sys.argv[6:9]
tx, ty, r, z = map(float, sys.argv[9:13])
P = lambda x, y: (cx + (x - y) * a, top + (x + y) * b)
im = Image.open(img).convert("RGB")
sx, sy = P(tx, ty); box = (int(sx - r * a), int(sy - r * b - 60), int(sx + r * a), int(sy + r * b))
c = im.crop(box).resize((int((box[2] - box[0]) * z), int((box[3] - box[1]) * z)), Image.LANCZOS).convert("RGBA")
ov = Image.new("RGBA", c.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
Q = lambda x, y: ((P(x, y)[0] - box[0]) * z, (P(x, y)[1] - box[1]) * z)
f = ImageFont.truetype("arialbd.ttf", 12); fb = ImageFont.truetype("arialbd.ttf", 16)
for i in range(44):
    for j in range(44):
        if abs(i + .5 - tx) > r + 3 or abs(j + .5 - ty) > r + 3: continue
        d.polygon([Q(i, j), Q(i + 1, j), Q(i + 1, j + 1), Q(i, j + 1)], outline=(255, 255, 255, 90))
        qx, qy = Q(i + .5, j + .5); d.text((qx - 13, qy - 6), f"{i},{j}", fill=(255, 255, 0, 170), font=f)
for x, y in (json.load(open(wf)) if wf != "-" else []):
    d.polygon([Q(x + .3, y + .3), Q(x + .7, y + .3), Q(x + .7, y + .7), Q(x + .3, y + .7)], fill=(255, 0, 255, 170))
if bf != "-":
    for line in open(bf):
        p = line.split("#")[0].split()
        if not p: continue
        k, x, y = p[0], int(p[1]), int(p[2]); s = BUILDING_TYPES[k].size
        d.polygon([Q(x, y), Q(x + s, y), Q(x + s, y + s), Q(x, y + s)], outline=(0, 255, 255, 255), width=2)
        qx, qy = Q(x + s / 2, y + s / 2); d.text((qx - 18, qy - 9), k, fill=(0, 255, 255, 255), font=fb, stroke_width=2, stroke_fill=(0, 0, 0, 255))
Image.alpha_composite(c, ov).convert("RGB").save(out, quality=88)
