"""proj.py IMG MASK a0 b0 [x0 y0 x1 y1] : lattice from line projections.
Projects mask pixels onto c = sy - s*sx and d = sy + s*sx (s = b/a); wall runs / checker edges
are lines with spacing 2b in c and d. Finds a, b maximising the folded first-harmonic strength and
reports the phases. MASK: pale | gold | dark | grad
Output phases are c0, d0 in [0, 2b): mask lines lie at c = c0 + 2b*k, d = d0 + 2b*k.
For a lattice (cx, top, a, b) the tile-centre lines (lift L) are at
  c = top - s*cx + (2y+1) b - L,   d = top + s*cx + (2x+1) b - L."""
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, sobel
from scipy.optimize import minimize

img, mode = sys.argv[1], sys.argv[2]
a0, b0 = float(sys.argv[3]), float(sys.argv[4])
box = tuple(map(int, sys.argv[5:9])) if len(sys.argv) > 8 else None
im = np.asarray(Image.open(img).convert("RGB")).astype(float)
R, G, B = im[..., 0], im[..., 1], im[..., 2]
H, W = R.shape
if mode == "pale":
    m = (R > 225) & (G > 205) & (B > 165)
    wgt = m.astype(float)
elif mode == "gold":
    m = (R > 200) & (G > 150) & (B < 120) & (R - B > 100)
    wgt = m.astype(float)
elif mode == "cyan":
    m = (B > 115) & (B > R + 25) & (np.abs(G - B) < 45) & (G > R + 15)
    wgt = m.astype(float) if "wgt" in dir() or True else None
elif mode == "dark":
    m = (B > R + 10) & (B > G) & (R < 120) & (B > 70)
    wgt = m.astype(float)
elif mode == "grad":
    lum = gaussian_filter(0.3 * R + 0.59 * G + 0.11 * B, 1.0)
    gx, gy = sobel(lum, 1), sobel(lum, 0)
    mag = np.hypot(gx, gy)
    grass = (G > R + 10) & (G > B + 40)
    grass = gaussian_filter(grass.astype(float), 3) > 0.99
    wgt = np.where(grass & (mag > 4) & (mag < 60), mag, 0.0)
    m = wgt > 0
if box:
    keep = np.zeros_like(m); keep[box[1]:box[3], box[0]:box[2]] = True; m = m & keep
ys, xs = np.nonzero(m)
w = wgt[ys, xs]
if len(xs) > 150000:
    sel = np.random.default_rng(0).choice(len(xs), 150000, replace=False); xs, ys, w = xs[sel], ys[sel], w[sel]
xs = xs.astype(float); ys = ys.astype(float)
print(len(xs), "mask pixels")


def strength(a, b):
    s = b / a; P = 2 * b
    c = ys - s * xs; d = ys + s * xs
    zc = np.sum(w * np.exp(2j * np.pi * c / P)) / w.sum()
    zd = np.sum(w * np.exp(2j * np.pi * d / P)) / w.sum()
    return abs(zc), abs(zd), (np.angle(zc) / (2 * np.pi) * P) % P, (np.angle(zd) / (2 * np.pi) * P) % P


best = None
for a in np.arange(a0 * 0.94, a0 * 1.06, 0.02):
    for b in np.arange(b0 * 0.94, b0 * 1.06, 0.02):
        sc, sd, _, _ = strength(a, b)
        v = sc + sd
        if best is None or v > best[0]:
            best = (v, a, b)
res = minimize(lambda p: -sum(strength(*p)[:2]), best[1:], method="Nelder-Mead", options=dict(xatol=1e-3, fatol=1e-6))
a, b = res.x
sc, sd, c0, d0 = strength(a, b)
print("a %.3f b %.3f ratio %.4f  strength c %.3f d %.3f  phase c0 %.2f d0 %.2f (period %.2f)" % (a, b, b / a, sc, sd, c0, d0, 2 * b))
