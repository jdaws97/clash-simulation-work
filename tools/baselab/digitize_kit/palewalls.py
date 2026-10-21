"""palewalls.py IMG cx top a b lift thr OUT.json : pale (gold/white) wall tiles by fraction of pale pixels near the lifted tile centre."""
import sys, json
import numpy as np
from PIL import Image
img = sys.argv[1]; cx, top, a, b, lift, thr = map(float, sys.argv[2:8]); out = sys.argv[8]
im = np.asarray(Image.open(img).convert("RGB")).astype(float)
H, W, _ = im.shape
R, G, B = im[..., 0], im[..., 1], im[..., 2]
pale = (R > 190) & (G > 160) & (B > 110) & (R - B < 120)
res = {}
for x in range(44):
    for y in range(44):
        sx = cx + (x - y + 0) * a; sy = top + (x + y + 1) * b - lift
        x0, x1, y0, y1 = int(sx - a * .3), int(sx + a * .3), int(sy - b * .7), int(sy + b * .7)
        if x0 < 0 or y0 < 0 or x1 >= W or y1 >= H: continue
        res[(x, y)] = pale[y0:y1, x0:x1].mean()
walls = sorted([list(k) for k, v in res.items() if v >= thr])
json.dump(walls, open(out, "w"))
print(len(walls), "tiles; histogram:", np.histogram(list(res.values()), bins=10, range=(0, 1))[0].tolist())
