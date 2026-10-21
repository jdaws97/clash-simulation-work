"""vfit.py IMG cx top a b : refit the grid to the bottom corners of cyan pad outlines ("V" shapes)."""
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import label, binary_dilation
from scipy.optimize import minimize
img = sys.argv[1]; cx0, top0, a0, b0 = map(float, sys.argv[2:6])
im = np.asarray(Image.open(img).convert("RGB")).astype(int)
R, G, B = im[..., 0], im[..., 1], im[..., 2]
cyan = (G > 135) & (B > 150) & (R < 130) & (G - R > 60)
lab, n = label(binary_dilation(cyan, iterations=1))
pts = []
for i in range(1, n + 1):
    ys, xs = np.nonzero(lab == i)
    if len(ys) < 60: continue
    k = ys.argmax(); bx, by = xs[k], ys[k]
    # require a V: pixels both left-up and right-up of the bottom point
    left = ((xs < bx - 15) & (ys < by - 5)).sum(); right = ((xs > bx + 15) & (ys < by - 5)).sum()
    w = xs.max() - xs.min()
    if left > 10 and right > 10 and w > 40: pts.append((bx, by))
pts = np.array(pts, float); print(len(pts), "V bottoms")
def resid(p):
    cx, top, a, b = p
    u = (pts[:, 0] - cx) / a; v = (pts[:, 1] - top) / b
    x = (u + v) / 2; y = (v - u) / 2
    dx = x - np.round(x); dy = y - np.round(y)
    return np.sqrt(dx ** 2 + dy ** 2)
def loss(p): r = resid(p); return np.sum(np.minimum(r, 0.3) ** 2)
best = None
for a in np.arange(a0 - 1.0, a0 + 1.01, 0.1):
    for b in np.arange(b0 - 0.8, b0 + 0.81, 0.1):
        for dcx in np.arange(-a / 2, a / 2, a / 10):
            for dtop in np.arange(-b / 2, b / 2, b / 10):
                l = loss((cx0 + dcx, top0 + dtop, a, b))
                if best is None or l < best[0]: best = (l, (cx0 + dcx, top0 + dtop, a, b))
res = minimize(loss, best[1], method="Nelder-Mead")
p = res.x; r = resid(p)
print("fit cx %.1f top %.1f a %.3f b %.3f" % tuple(p), "median resid %.3f, frac<0.15: %.2f" % (np.median(r), np.mean(r < 0.15)))
r0 = resid((cx0, top0, a0, b0)); print("start median resid %.3f frac<0.15 %.2f" % (np.median(r0), np.mean(r0 < 0.15)))
