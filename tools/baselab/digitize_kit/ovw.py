"""ovw.py IMG cx top a b lift OUT x0 y0 x1 y1 : draw grid (all lines) + tile centres coloured by pale test"""
import sys
import numpy as np
from PIL import Image, ImageDraw
img = sys.argv[1]; cx, top, a, b, lift = map(float, sys.argv[2:7]); out = sys.argv[7]; crop = tuple(map(int, sys.argv[8:12]))
im = Image.open(img).convert("RGB"); arr = np.asarray(im).astype(float)
d = ImageDraw.Draw(im)
P = lambda x, y: (cx + (x - y) * a, top + (x + y) * b)
for i in range(45):
    d.line([P(i, 0), P(i, 44)], fill=(255, 255, 0) if i % 4 == 0 else (255, 255, 255), width=1)
    d.line([P(0, i), P(44, i)], fill=(255, 255, 0) if i % 4 == 0 else (255, 255, 255), width=1)
for x in range(44):
    for y in range(44):
        sx, sy = P(x + .5, y + .5)
        d.ellipse([sx - 2, sy - 2, sx + 2, sy + 2], fill=(0, 255, 0))
        if x % 4 == 0 and y % 4 == 0: d.text((sx + 3, sy - 6), f"{x},{y}", fill=(255, 255, 255))
c = im.crop(crop); c = c.resize((c.width * 2, c.height * 2)); c.save(out, quality=90)
