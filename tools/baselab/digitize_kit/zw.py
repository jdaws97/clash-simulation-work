"""zw.py IMG cx top a b OUT sx0 sy0 sx1 sy1 zoom [walls.json|-] [buildings.txt|-] [traps.txt|-]
Screen window, every tile outlined and labelled 'x,y' (small), walls magenta squares, buildings cyan footprints, traps orange dots."""
import sys, json, os
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from PIL import Image, ImageDraw, ImageFont
from baselab.mechanics import BUILDING_TYPES
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); out = sys.argv[6]; x0, y0, x1, y1 = map(int, sys.argv[7:11]); z = float(sys.argv[11])
wf = sys.argv[12] if len(sys.argv) > 12 else "-"; bf = sys.argv[13] if len(sys.argv) > 13 else "-"; tf = sys.argv[14] if len(sys.argv) > 14 else "-"
lab = os.environ.get("LAB", "1") == "1"
im = Image.open(img).convert("RGB").crop((x0, y0, x1, y1)); im = im.resize((int(im.width * z), int(im.height * z)), Image.LANCZOS).convert("RGBA")
ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
Q = lambda x, y: ((cx + (x - y) * a - x0) * z, (top + (x + y) * b - y0) * z)
fs = max(9, int(a * z * 0.36)); f = ImageFont.truetype("arial.ttf", fs); fb = ImageFont.truetype("arialbd.ttf", int(fs * 1.3))
for i in range(45):
    col = (255, 255, 0, 150) if i % 4 == 0 else (255, 255, 255, 55)
    d.line([Q(i, 0), Q(i, 44)], fill=col, width=1); d.line([Q(0, i), Q(44, i)], fill=col, width=1)
if lab:
    for i in range(44):
        for j in range(44):
            qx, qy = Q(i + .5, j + .5)
            if -20 < qx < im.width + 20 and -20 < qy < im.height + 20:
                d.text((qx - fs * 0.9, qy - fs * 0.55), f"{i},{j}", fill=(255, 255, 120, 150), font=f)
if wf != "-":
    for x, y in json.load(open(wf)):
        d.polygon([Q(x + .3, y + .3), Q(x + .7, y + .3), Q(x + .7, y + .7), Q(x + .3, y + .7)], fill=(255, 0, 255, 170))
if bf != "-":
    for line in open(bf):
        p = line.split("#")[0].split()
        if not p: continue
        k, x, y = p[0], int(p[1]), int(p[2]); s = BUILDING_TYPES[k].size
        d.polygon([Q(x, y), Q(x + s, y), Q(x + s, y + s), Q(x, y + s)], outline=(0, 255, 255, 255), width=2)
        qx, qy = Q(x + s / 2, y + s / 2); d.text((qx - fs * 1.2, qy - fs * 0.6), k, fill=(0, 255, 255, 255), font=fb, stroke_width=2, stroke_fill=(0, 0, 0, 255))
if tf != "-":
    for line in open(tf):
        p = line.split("#")[0].split()
        if not p: continue
        k, x, y = p[0], int(p[1]), int(p[2]); s = 2 if k in ("giant", "giga") else 1
        d.polygon([Q(x + .15, y + .15), Q(x + s - .15, y + .15), Q(x + s - .15, y + s - .15), Q(x + .15, y + s - .15)], outline=(255, 120, 0, 255), width=2)
        qx, qy = Q(x + s / 2, y + s / 2); d.text((qx - fs, qy - fs * 0.5), k[:3], fill=(255, 150, 0, 255), font=f, stroke_width=1, stroke_fill=(0, 0, 0, 255))
Image.alpha_composite(im, ov).convert("RGB").save(out, quality=87)
