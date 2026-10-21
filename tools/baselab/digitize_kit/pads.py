"""pads.py IMG cx top a b OUT.txt [walls.json]: propose building footprints from cyan pad outlines.
Scores each (size, x, y) by the fraction of the footprint's two lower edges (and, less weight, upper edges)
that lie on cyan pixels; greedy non-overlapping selection."""
import sys, json
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); out = sys.argv[6]
walls = {tuple(w) for w in json.load(open(sys.argv[7]))} if len(sys.argv) > 7 else set()
im = np.asarray(Image.open(img).convert("RGB")).astype(int)
H, W, _ = im.shape
R, G, B = im[..., 0], im[..., 1], im[..., 2]
cyan = (G > 135) & (B > 150) & (R < 130) & (G - R > 60)
cyan = binary_dilation(cyan, iterations=2)
P = lambda x, y: (cx + (x - y) * a, top + (x + y) * b)
def edge(p, q, n=24):
    vals = []
    for t in np.linspace(0.08, 0.92, n):
        sx, sy = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        if 0 <= sx < W and 0 <= sy < H: vals.append(cyan[int(sy), int(sx)])
    return np.mean(vals) if len(vals) > n * 0.6 else None
cands = []
for s in (2, 3, 4):
    for x in range(0, 45 - s):
        for y in range(0, 45 - s):
            L, Bo, Rr, T = P(x, y + s), P(x + s, y + s), P(x + s, y), P(x, y)
            e1, e2 = edge(L, Bo), edge(Bo, Rr)
            if e1 is None or e2 is None: continue
            e3, e4 = edge(T, L), edge(T, Rr)
            up = np.mean([e for e in (e3, e4) if e is not None]) if (e3 is not None or e4 is not None) else 0
            # inner ring at 1 tile in must NOT be cyan (rules out sub-squares of bigger pads)
            score = min(e1, e2) * 0.7 + up * 0.3
            cands.append((score, s, x, y, round(e1, 2), round(e2, 2), round(up, 2)))
cands.sort(reverse=True)
taken = set(); sel = []
for c in cands:
    sc, s, x, y = c[:4]
    if sc < 0.55: break
    t = {(x + i, y + j) for i in range(s) for j in range(s)}
    if t & taken: continue
    taken |= t; sel.append(c)
with open(out, "w") as f:
    for c in sorted(sel, key=lambda c: (c[3] + c[2], c[2])):
        f.write(f"{c[1]} {c[2]} {c[3]}  # score {c[0]:.2f} lower {c[4]} {c[5]} upper {c[6]}\n")
print(len(sel), "pads;", {s: sum(1 for c in sel if c[1] == s) for s in (2, 3, 4)})
