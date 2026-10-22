"""hfit.py IMG RULE [rmin rmax]: wall-line lattice fit.
For slope ratio r, intercepts c1 = sy - r*sx (lines of constant y) and c2 = sy + r*sx (constant x) of mask pixels are
histogrammed; best r = sharpest histograms; line spacing 2b from the histogram autocorrelation; phases from a comb fit.
Prints the 'mask-line lattice' (cx, top, a, b): mask lines lie on x = i + 0.5 / y = j + 0.5 of that lattice."""
import sys
import numpy as np
from PIL import Image
img, rule = sys.argv[1:3]
rmin, rmax = (float(sys.argv[3]), float(sys.argv[4])) if len(sys.argv) > 4 else (0.68, 0.80)
im = np.asarray(Image.open(img).convert("RGB")).astype(int)
R, G, B = im[..., 0], im[..., 1], im[..., 2]; YY, XX = np.indices(R.shape)
m = eval(rule)
ys, xs = np.nonzero(m); xs = xs.astype(float); ys = ys.astype(float)
bw = 0.25
def hists(r):
    c1 = ys - r * xs; c2 = ys + r * xs
    h1, e1 = np.histogram(c1, bins=np.arange(c1.min() - 2, c1.max() + 2, bw))
    h2, e2 = np.histogram(c2, bins=np.arange(c2.min() - 2, c2.max() + 2, bw))
    return h1.astype(float), e1, h2.astype(float), e2
best = None
for r in np.arange(rmin, rmax, 0.001):
    h1, _, h2, _ = hists(r)
    from scipy.ndimage import gaussian_filter1d
    s = (gaussian_filter1d(h1, 2) ** 2).sum() + (gaussian_filter1d(h2, 2) ** 2).sum()
    if best is None or s > best[0]: best = (s, r)
r = best[1]
import os
if os.environ.get('FIXR'): r = float(os.environ['FIXR'])
h1, e1, h2, e2 = hists(r)
from scipy.ndimage import gaussian_filter1d
g1, g2 = gaussian_filter1d(h1, 3), gaussian_filter1d(h2, 3)
def ac(h):
    h = h - h.mean(); n = len(h)
    f = np.fft.rfft(h, 2 * n); a = np.fft.irfft(f * np.conj(f))[:n]; return a / a[0]
A = ac(g1)[:int(60 / bw)] + ac(g2)[:int(60 / bw)]
lags = np.arange(len(A)) * bw
PL, PH = map(float, __import__("os").environ.get("PRANGE", "10 40").split()); sel = (lags > PL) & (lags < PH)
for L_ in (8, 12, 14, 15, 16, 16.5, 17, 18, 20, 25, 30, 33): print("ac@%.1f %.3f" % (L_, A[int(L_ / bw)]))
P0 = lags[sel][np.argmax(A[sel])]
# comb refine of period and phases
def comb(h, e, P, ph):
    c = (e[:-1] + e[1:]) / 2
    d = np.abs(((c - ph) / P + 0.5) % 1 - 0.5) * P
    return (h * np.exp(-(d / 1.0) ** 2)).sum()
bestc = None
Ps = [float(os.environ['FIXP'])] if os.environ.get('FIXP') else np.arange(P0 * 0.97, P0 * 1.03, 0.01)
for P in Ps:
    s1 = max((comb(g1, e1, P, ph), ph) for ph in np.arange(0, P, 0.1))
    s2 = max((comb(g2, e2, P, ph), ph) for ph in np.arange(0, P, 0.1))
    tot = s1[0] + s2[0]
    if bestc is None or tot > bestc[0]: bestc = (tot, P, s1[1], s2[1])
_, P, ph1, ph2 = bestc
b = P / 2; a = b / r
# c1 = top - r cx + 2 j' b with mask lines at j'+0.5 -> phase ph1 = top - r cx + b ; ph2 = top + r cx + b
top = (ph1 + ph2) / 2 - b; cx = (ph2 - ph1) / (2 * r)
# move cx near image centre (lattice shift by a along with top by b)
W = im.shape[1]
while cx < W / 2 - a: cx += a; top += b
while cx > W / 2 + a: cx -= a; top -= b
print("r %.4f  period 2b %.3f (ac guess %.2f)  a %.3f b %.3f  cx %.2f top %.2f" % (r, P, P0, a, b, cx, top))
