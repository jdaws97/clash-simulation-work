"""fh.py IMG cx top a b RULE : histogram of frac(x), frac(y) (ground lattice) of mask pixels -> where wall caps sit."""
import sys
import numpy as np
from PIL import Image
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); rule = sys.argv[6]
im = np.asarray(Image.open(img).convert("RGB")).astype(int)
R, G, B = im[..., 0], im[..., 1], im[..., 2]; YY, XX = np.indices(R.shape)
m = eval(rule); ys, xs = np.nonzero(m)
u = (xs - cx) / a; v = (ys - top) / b; x = (u + v) / 2; y = (v - u) / 2
fx, fy = x % 1, y % 1
hx = np.histogram(fx, bins=20, range=(0, 1))[0]; hy = np.histogram(fy, bins=20, range=(0, 1))[0]
print("bins  " + " ".join(f"{k / 20:.2f}"[1:] for k in range(20)))
print("fx    " + " ".join(f"{v * 100 // max(hx):3d}" for v in hx))
print("fy    " + " ".join(f"{v * 100 // max(hy):3d}" for v in hy))
print("n", len(xs))
