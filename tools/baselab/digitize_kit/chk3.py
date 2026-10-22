"""chk3.py IMG cx0 top0 a_lo a_hi [ratio] : for each a (b = ratio*a), best checker phase score. Prints table + best."""
import sys, os
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
img = sys.argv[1]; cx0, top0, alo, ahi = map(float, sys.argv[2:6]); r = float(sys.argv[6]) if len(sys.argv) > 6 else 0.75
im = np.asarray(Image.open(img).convert("RGB")).astype(float)
R, G, B = im[..., 0], im[..., 1], im[..., 2]; YY, XX = np.indices(R.shape)
grass = eval(os.environ.get("GRASS", "(G > R + 10) & (G > B + 15) & (G > 60)"))
if os.environ.get("REG"): grass &= eval(os.environ["REG"])
L = G + R; hp = np.clip(L - gaussian_filter(L, 6), -30, 30)
ys, xs = np.nonzero(grass); rng = np.random.default_rng(0); k = rng.choice(len(xs), min(len(xs), 80000), replace=False)
X, Y, V = xs[k].astype(float), ys[k].astype(float), hp[ys[k], xs[k]]
best = None
for a in np.arange(alo, ahi, 0.02):
    b = a * r; res = []
    for ox in np.arange(0, 1, 0.1):
        for oy in np.arange(0, 1, 0.1):
            cx = cx0 + (ox - oy) * a; top = top0 + (ox + oy) * b
            u = (X - cx) / a; v = (Y - top) / b
            s = 1 - 2 * ((np.floor((u + v) / 2) + np.floor((v - u) / 2)) % 2)
            res.append((abs(np.mean(s * V)), cx, top))
    m = max(res)
    if best is None or m[0] > best[0]: best = (m[0], a, m[1], m[2])
    print("a %.2f score %.3f" % (a, m[0]))
print("BEST a %.3f cx %.2f top %.2f score %.3f" % (best[1], best[2], best[3], best[0]))
