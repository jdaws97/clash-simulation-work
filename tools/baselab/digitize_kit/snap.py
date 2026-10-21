"""snap.py IMG cx top a b buildings.txt [--apply]: for each building, score its footprint's lower 'V' against cyan pad
outlines at offsets -2..2 and suggest the best position (prints current score, best score, best offset)."""
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from baselab.mechanics import BUILDING_TYPES
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); bf = sys.argv[6]; apply = "--apply" in sys.argv
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
def score(x, y, s):
    e1 = frac(P(x, y + s), P(x + s, y + s)); e2 = frac(P(x + s, y + s), P(x + s, y))
    x1 = frac(P(x - 0.2, y + s), P(x - 0.8, y + s), 0, 1, 6); x2 = frac(P(x + s, y - 0.2), P(x + s, y - 0.8), 0, 1, 6)
    return (e1 + e2) / 2 - 0.25 * (x1 + x2)
lines = open(bf).read().splitlines(); out = []
for line in lines:
    body = line.split("#")[0].split()
    if not body or body[0].isdigit(): out.append(line); continue
    k, x, y = body[0], int(body[1]), int(body[2]); s = BUILDING_TYPES[k].size
    cur = score(x, y, s)
    best = max(((score(x + dx, y + dy, s), dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)), key=lambda t: (t[0], -abs(t[1]) - abs(t[2])))
    flag = ""
    if best[0] > cur + 0.25 and best[0] > 0.6:
        flag = f"  -> suggest {x + best[1]} {y + best[2]} (score {best[0]:.2f})"
        if apply:
            body[1], body[2] = str(x + best[1]), str(y + best[2]); line = " ".join(body) + "  # snapped"
    print(f"{k:10s} {x:2d} {y:2d}  cur {cur:.2f}{flag}")
    out.append(line)
if apply: open(bf, "w").write("\n".join(out) + "\n")
