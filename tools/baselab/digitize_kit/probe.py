"""probe.py IMG cx top a b key x0 x1 y0 y1: pad-edge score grid for a building type."""
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from baselab.mechanics import BUILDING_TYPES
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); k = sys.argv[6]; x0, x1, y0, y1 = map(int, sys.argv[7:11])
s = BUILDING_TYPES[k].size if not k.isdigit() else int(k)
im = np.asarray(Image.open(img).convert("RGB")).astype(int); H, W, _ = im.shape
R, G, B = im[..., 0], im[..., 1], im[..., 2]
cyan = binary_dilation((G > 135) & (B > 150) & (R < 130) & (G - R > 60), iterations=2)
P = lambda x, y: (cx + (x - y) * a, top + (x + y) * b)
def frac(p, q, t0=0.1, t1=0.9, n=20):
    v = [cyan[int(p[1] + (q[1] - p[1]) * t), int(p[0] + (q[0] - p[0]) * t)] for t in np.linspace(t0, t1, n)]
    return np.mean(v)
print("      " + " ".join(f"y{y:<4d}" for y in range(y0, y1 + 1)))
for x in range(x0, x1 + 1):
    row = []
    for y in range(y0, y1 + 1):
        e1 = frac(P(x, y + s), P(x + s, y + s)); e2 = frac(P(x + s, y + s), P(x + s, y))
        row.append(f"{e1:.1f}/{e2:.1f}")
    print(f"x{x:<3d}  " + " ".join(row))
