"""Search sub-tile offset (and lift) maximising pale-wall hits at tile centres."""
import sys
import numpy as np
from PIL import Image
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6])
im = np.asarray(Image.open(img).convert("RGB")).astype(float)
H, W, _ = im.shape
def pale(sx, sy):
    sx, sy = int(sx), int(sy)
    if not (3 <= sx < W - 3 and 3 <= sy < H - 3): return None
    c = im[sy-2:sy+3, sx-2:sx+3].reshape(-1, 3).mean(0)
    return c[0] > 200 and c[1] > 175 and c[2] > 120
best = []
for lift in (8, 12, 16, 20):
    for du in np.arange(-0.5, 0.51, 0.1):
        for dv in np.arange(-0.5, 0.51, 0.1):
            n = 0; tot = 0
            for x in range(44):
                for y in range(44):
                    X, Y = x + 0.5 + du, y + 0.5 + dv
                    r = pale(cx + (X - Y) * a, top + (X + Y) * b - lift)
                    if r is None: continue
                    tot += 1; n += r
            best.append((n, lift, round(du, 1), round(dv, 1)))
best.sort(reverse=True)
for r in best[:12]: print(r)
