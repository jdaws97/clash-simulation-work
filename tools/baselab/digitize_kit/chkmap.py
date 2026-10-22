"""chkmap.py IMG cx top a b : per-tile checker sign map (+ / - / . for no grass), tiles -6..49."""
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6])
im = np.asarray(Image.open(img).convert("RGB")).astype(float)
R, G, B = im[..., 0], im[..., 1], im[..., 2]
import os; grass = eval(os.environ.get("GRASS", "(G > R + 25) & (G > B + 40) & (G > 110)"))
L = G + R; hp = np.clip(L - gaussian_filter(L, 6), -30, 30)
ys, xs = np.nonzero(grass); X, Y, V = xs.astype(float), ys.astype(float), hp[ys, xs]
u = (X - cx) / a; v = (Y - top) / b; x = np.floor((u + v) / 2).astype(int); y = np.floor((v - u) / 2).astype(int)
s = 1 - 2 * ((x + y) % 2)
lo, hi = -6, 50
acc = {}
for xi, yi, val in zip(x, y, s * V):
    if lo <= xi < hi and lo <= yi < hi:
        t = acc.setdefault((xi, yi), [0.0, 0]); t[0] += val; t[1] += 1
mv = {k: v[0] / v[1] for k, v in acc.items() if v[1] >= 25}
for (xi, yi), val in list(mv.items()):
    nb = [mv[n] for n in ((xi + 1, yi), (xi - 1, yi), (xi, yi + 1), (xi, yi - 1)) if n in mv]
    if len(nb) >= 2:
        sgn = 1 - 2 * ((xi + yi) % 2)
        acc[(xi, yi)] = [sgn * (val - np.mean(nb)) * acc[(xi, yi)][1], acc[(xi, yi)][1]]
    else: acc[(xi, yi)] = [0, 0]
print("     " + "".join(str(abs(i) % 10) for i in range(lo, hi)))
for yi in range(lo, hi):
    row = ""
    for xi in range(lo, hi):
        t = acc.get((xi, yi))
        if not t or t[1] < 25: row += " "
        else:
            m = t[0] / t[1]; row += "+" if m > 3 else ("-" if m < -3 else ".")
    print(f"{yi:4d} " + row)
# column / row profiles of the mean checker indicator
def prof(axis):
    out = []
    for k in range(lo, hi):
        vals = [acc[t][0] / acc[t][1] for t in acc if acc[t][1] >= 25 and (t[0] if axis == 0 else t[1]) == k and 4 <= (t[1] if axis == 0 else t[0]) <= 39]
        out.append((k, np.mean(vals) if vals else float("nan"), len(vals)))
    return out
print("x-profile (mean over y 4..39):", " ".join(f"{k}:{m:.0f}" for k, m, n in prof(0) if n))
print("y-profile (mean over x 4..39):", " ".join(f"{k}:{m:.0f}" for k, m, n in prof(1) if n))
