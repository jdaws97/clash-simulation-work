"""wfit.py IMG cx top a lift: fit grid by maximizing pale wall-cap hits at tile centres AND minimizing hits at tile corners (b = 0.7494 a)."""
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter
from scipy.optimize import minimize
img = sys.argv[1]; cx0, top0, a0, lift = map(float, sys.argv[2:6])
im = np.asarray(Image.open(img).convert("RGB")).astype(float); H, W, _ = im.shape
R, G, B = im[..., 0], im[..., 1], im[..., 2]
m = uniform_filter(((R > 200) & (G > 180) & (B > 130) & (R - B < 100)).astype(float), 3)
xs, ys = np.meshgrid(np.arange(44) + 0.5, np.arange(44) + 0.5, indexing="ij")
def sample(cx, top, a, ox=0, oy=0):
    b = a * 0.7494
    sx = cx + (xs + ox - ys - oy) * a; sy = top + (xs + ox + ys + oy) * b - lift * a / 15
    ok = (sx >= 0) & (sx < W - 1) & (sy >= 0) & (sy < H - 1)
    return m[sy[ok].astype(int), sx[ok].astype(int)]
def score(p):
    cx, top, a = p
    c = sample(cx, top, a); e = sample(cx, top, a, 0.5, 0.5)
    v = np.sort(c)[::-1][:400]
    return v.sum() - 0.5 * np.sort(e)[::-1][:400].sum()
best = []
for a in np.arange(a0 * 0.95, a0 * 1.05, a0 * 0.005):
    for dcx in np.arange(-a, a, a / 6):
        for dtop in np.arange(-a, a, a / 6):
            best.append((score((cx0 + dcx, top0 + dtop, a)), cx0 + dcx, top0 + dtop, a))
best.sort(reverse=True)
for r in best[:8]: print([round(v, 2) for v in r])
