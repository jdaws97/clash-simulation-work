"""walls4.py IMG cx top a b lift MODE thr buildings.txt OUT.json : per-tile wall score at the cap (tile centre lifted),
MODE pale|dark|gold. Keeps tiles >= thr outside building footprints that have a wall-ish 4-neighbour (score >= thr/2)
or score >= 1.5 thr. Prints counts."""
import sys, json
import numpy as np
from PIL import Image
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from baselab.mechanics import BUILDING_TYPES
img = sys.argv[1]; cx, top, a, b, lift = map(float, sys.argv[2:7]); mode = sys.argv[7]; thr = float(sys.argv[8]); bf, out = sys.argv[9], sys.argv[10]
im = np.asarray(Image.open(img).convert("RGB")).astype(float); H, W, _ = im.shape
R, G, B = im[..., 0], im[..., 1], im[..., 2]
if mode == "pale":
    m = (R > 215) & (G > 195) & (B > 145) & (R - B < 95) & (np.abs(R - G) < 40)
elif mode == "gold":
    m = ((R > 215) & (G > 195) & (B > 145) & (R - B < 95)) | ((R > 200) & (G > 150) & (B < 110) & (R - G < 70))
elif mode == "cyan":
    m = (B > 115) & (B > R + 25) & (np.abs(G - B) < 45) & (G > R + 15)
    wgt = m.astype(float) if "wgt" in dir() or True else None
elif mode == "dark":
    m = (B > R + 8) & (B >= G) & (R < 130) & (B > 60) & (B < 200)
occ = set()
if bf != "-":
    for line in open(bf):
        p = line.split("#")[0].split()
        if not p or p[0].startswith("T:"): continue
        s = BUILDING_TYPES[p[0]].size; x, y = int(p[1]), int(p[2])
        occ |= {(x + i, y + j) for i in range(s) for j in range(s)}
sc = {}
for x in range(44):
    for y in range(44):
        sx = cx + (x - y) * a; sy = top + (x + y + 1) * b - lift
        BX = float(__import__("os").environ.get("BX", ".35")); BY = float(__import__("os").environ.get("BY", ".45"))
        x0, x1, y0, y1 = int(sx - a * BX), int(sx + a * BX), int(sy - b * BY), int(sy + b * BY)
        if x0 < 0 or y0 < 0 or x1 >= W or y1 >= H: continue
        sc[(x, y)] = m[y0:y1, x0:x1].mean()
keep = []
for t, v in sc.items():
    if t in occ or v < thr: continue
    nb = [sc.get((t[0] + dx, t[1] + dy), 0) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
    if max(nb) >= thr / 2 or v >= 1.5 * thr: keep.append(list(t))
json.dump(sorted(keep), open(out, "w"))
json.dump({f"{k[0]},{k[1]}": round(v, 3) for k, v in sc.items()}, open(out + ".scores", "w"))
print(len(keep), "walls; hist", np.histogram(list(sc.values()), bins=10, range=(0, 1))[0].tolist())
