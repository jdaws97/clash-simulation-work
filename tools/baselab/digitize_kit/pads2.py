"""pads2.py IMG cx top a b OUT.txt : propose footprints from cyan pad 'V's (lower edges), checking the V ends at the corners."""
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); out = sys.argv[6]
im = np.asarray(Image.open(img).convert("RGB")).astype(int)
H, W, _ = im.shape
R, G, B = im[..., 0], im[..., 1], im[..., 2]
cyan = binary_dilation((G > 135) & (B > 150) & (R < 130) & (G - R > 60), iterations=2)
P = lambda x, y: (cx + (x - y) * a, top + (x + y) * b)
def frac(p, q, t0=0.1, t1=0.9, n=20):
    v = []
    for t in np.linspace(t0, t1, n):
        sx, sy = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        if 0 <= sx < W and 0 <= sy < H: v.append(cyan[int(sy), int(sx)])
    return np.mean(v) if len(v) >= n // 2 else 0.0
cands = []
for s in (2, 3, 4):
    for x in range(0, 45 - s):
        for y in range(0, 45 - s):
            e1 = frac(P(x, y + s), P(x + s, y + s)); e2 = frac(P(x + s, y + s), P(x + s, y))
            if max(e1, e2) < 0.8 or min(e1, e2) < 0.3: continue
            # V must stop at the side corners: segments continuing past the corners should not be cyan
            x1 = frac(P(x - 0.2, y + s), P(x - 0.8, y + s), 0, 1, 6) if e1 > 0.5 else 0
            x2 = frac(P(x + s, y - 0.2), P(x + s, y - 0.8), 0, 1, 6) if e2 > 0.5 else 0
            sc = (e1 + e2) / 2 - 0.5 * max(x1, x2)
            cands.append((round(sc, 3), s, x, y, round(e1, 2), round(e2, 2), round(x1, 2), round(x2, 2)))
cands.sort(reverse=True)
taken = set(); sel = []
for c in cands:
    if c[0] < 0.55: break
    s, x, y = c[1:4]
    t = {(x + i, y + j) for i in range(s) for j in range(s)}
    if t & taken: continue
    taken |= t; sel.append(c)
with open(out, "w") as f:
    for c in sorted(sel, key=lambda c: (c[2] + c[3], c[2])):
        f.write(f"{c[1]} {c[2]} {c[3]}  # sc {c[0]} e {c[4]} {c[5]} ext {c[6]} {c[7]}\n")
print(len(sel), "pads", {s: sum(1 for c in sel if c[1] == s) for s in (2, 3, 4)})
