"""cfit.py IMG cx top a : fit lattice to wall-cap peaks (bright cream). Cap = tile centre lifted; top absorbs lift."""
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter, maximum_filter
from scipy.optimize import minimize
img = sys.argv[1]; cx0, top0, a0 = map(float, sys.argv[2:5])
im = np.asarray(Image.open(img).convert("RGB")).astype(int)
R, G, B = im[..., 0], im[..., 1], im[..., 2]
m = uniform_filter(((R > 228) & (G > 205) & (B > 150)).astype(float), max(3, int(a0 / 3)))
pk = (m == maximum_filter(m, int(a0 * 0.8))) & (m > 0.35)
ys, xs = np.nonzero(pk); pts = np.c_[xs, ys].astype(float); print(len(pts), "cap peaks")
def resid(p):
    cx, top, a, b = p
    u = (pts[:, 0] - cx) / a; v = (pts[:, 1] - top) / b
    x = (u + v) / 2 - 0.5; y = (v - u) / 2 - 0.5
    return np.hypot(x - np.round(x), y - np.round(y))
loss = lambda p: np.sum(np.minimum(resid(p), 0.3) ** 2)
best = None
for a in np.arange(a0 * 0.95, a0 * 1.05, a0 * 0.005):
  for rat in np.arange(0.68, 0.82, 0.01):
    for dcx in np.arange(-a / 2, a / 2, a / 8):
        for dtop in np.arange(-a / 2, a / 2, a / 8):
            l = loss((cx0 + dcx, top0 + dtop, a, a * rat))
            if best is None or l < best[0]: best = (l, (cx0 + dcx, top0 + dtop, a, a * rat))
p = minimize(loss, best[1], method="Nelder-Mead").x; r = resid(p)
print("fit cx %.2f top %.2f a %.3f b %.3f ratio %.4f" % (p[0], p[1], p[2], p[3], p[3] / p[2]), "median resid %.3f frac<0.15 %.2f" % (np.median(r), np.mean(r < 0.15)))
