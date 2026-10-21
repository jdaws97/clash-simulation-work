import sys
import numpy as np
from PIL import Image
img = sys.argv[1]; cx0, top0, a0, b0 = map(float, sys.argv[2:6]); lift = float(sys.argv[6])
im = np.asarray(Image.open(img).convert("RGB")).astype(float)
H, W, _ = im.shape
mask = (im[..., 0] > 200) & (im[..., 1] > 175) & (im[..., 2] > 120)
from scipy.ndimage import uniform_filter
m = uniform_filter(mask.astype(float), 5)
xs, ys = np.meshgrid(np.arange(44) + 0.5, np.arange(44) + 0.5, indexing="ij")
def score(cx, top, a, b):
    sx = (cx + (xs - ys) * a).astype(int); sy = (top + (xs + ys) * b - lift).astype(int)
    ok = (sx >= 0) & (sx < W) & (sy >= 0) & (sy < H)
    return (m[sy[ok], sx[ok]] > 0.6).sum()
res = []
for a in np.arange(a0 - 0.6, a0 + 0.61, 0.1):
    for b in np.arange(b0 - 0.6, b0 + 0.61, 0.1):
        for dcx in range(-30, 31, 3):
            for dtop in range(-24, 25, 3):
                res.append((score(cx0 + dcx, top0 + dtop, a, b), round(a, 2), round(b, 2), cx0 + dcx, top0 + dtop))
res.sort(reverse=True)
for r in res[:15]: print(r)
