"""chk2.py IMG cx0 top0 a b [region-rule]: scan sub-tile phase (ox, oy) of the ground lattice against the checkered grass.
Prints the best phase as (ox, oy) relative to the given lattice and the resulting cx, top."""
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
img = sys.argv[1]; cx0, top0, a, b = map(float, sys.argv[2:6])
im = np.asarray(Image.open(img).convert("RGB")).astype(float)
R, G, B = im[..., 0], im[..., 1], im[..., 2]; YY, XX = np.indices(R.shape)
import os; grass = eval(os.environ.get("GRASS", "(G > R + 25) & (G > B + 40) & (G > 110)"))
if len(sys.argv) > 6: grass &= eval(sys.argv[6])
L = G + R; hp = np.clip(L - gaussian_filter(L, 6), -30, 30)
ys, xs = np.nonzero(grass); X, Y, V = xs.astype(float), ys.astype(float), hp[ys, xs]
res = []
for ox in np.arange(0, 1, 0.05):
    for oy in np.arange(0, 1, 0.05):
        cx = cx0 + (ox - oy) * a; top = top0 + (ox + oy) * b
        u = (X - cx) / a; v = (Y - top) / b; x = (u + v) / 2; y = (v - u) / 2
        s = 1 - 2 * ((np.floor(x) + np.floor(y)) % 2)
        res.append((abs(np.mean(s * V)), round(ox, 2), round(oy, 2), cx, top))
res.sort(reverse=True)
for r in res[:6]: print("score %.3f ox %.2f oy %.2f -> cx %.2f top %.2f" % r)
print("worst", "%.3f" % res[-1][0], "n", len(X))
