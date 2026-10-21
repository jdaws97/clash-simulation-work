"""gl.py IMG cx top a b OUT x0 y0 x1 y1 zoom [walls.json] [buildings.txt]: grid lines only (every 4th labelled), dots at tile centres."""
import sys, json
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from PIL import Image, ImageDraw, ImageFont
from baselab.mechanics import BUILDING_TYPES
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); out = sys.argv[6]; x0, y0, x1, y1 = map(int, sys.argv[7:11]); z = float(sys.argv[11])
wf = sys.argv[12] if len(sys.argv) > 12 else "-"; bf = sys.argv[13] if len(sys.argv) > 13 else "-"
im = Image.open(img).convert("RGB").crop((x0, y0, x1, y1)); im = im.resize((int(im.width * z), int(im.height * z)), Image.LANCZOS).convert("RGBA")
ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
Q = lambda x, y: ((cx + (x - y) * a - x0) * z, (top + (x + y) * b - y0) * z)
f = ImageFont.truetype("arialbd.ttf", 13); fb = ImageFont.truetype("arialbd.ttf", 15)
for i in range(45):
    col = (255, 255, 0, 200) if i % 4 == 0 else (255, 255, 255, 80)
    d.line([Q(i, 0), Q(i, 44)], fill=col, width=1); d.line([Q(0, i), Q(44, i)], fill=col, width=1)
for i in range(0, 44, 4):
    for j in range(0, 44, 4):
        qx, qy = Q(i + .5, j + .5); d.text((qx - 10, qy - 7), f"{i},{j}", fill=(0, 255, 0, 255), font=f, stroke_width=1, stroke_fill=(0, 0, 0, 255))
if wf != "-":
    for x, y in json.load(open(wf)):
        d.polygon([Q(x + .3, y + .3), Q(x + .7, y + .3), Q(x + .7, y + .7), Q(x + .3, y + .7)], fill=(255, 0, 255, 160))
if bf != "-":
    for line in open(bf):
        p = line.split("#")[0].split()
        if not p: continue
        k, x, y = p[0], int(p[1]), int(p[2]); s = BUILDING_TYPES[k].size if not k.isdigit() else int(k)
        d.polygon([Q(x, y), Q(x + s, y), Q(x + s, y + s), Q(x, y + s)], outline=(0, 255, 255, 255), width=2)
        qx, qy = Q(x + s / 2, y + s / 2); d.text((qx - 15, qy - 8), k, fill=(0, 255, 255, 255), font=fb, stroke_width=2, stroke_fill=(0, 0, 0, 255))
Image.alpha_composite(im, ov).convert("RGB").save(out, quality=88)
