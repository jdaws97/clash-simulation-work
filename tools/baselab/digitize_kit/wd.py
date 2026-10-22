"""wd.py IMG cx top a b lift RULE thr OUT.json [buildings.txt|-] [minrun]
Wall tiles = tiles whose lifted-centre window (+-0.3a, +-0.5b) has mask fraction >= thr; minus building footprints;
keep 4-connected components of size >= minrun (default 2) and print isolated ones with their score."""
import sys, json
import numpy as np
from PIL import Image
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from baselab.mechanics import BUILDING_TYPES
img = sys.argv[1]; cx, top, a, b, lift = map(float, sys.argv[2:7]); rule = sys.argv[7]; thr = float(sys.argv[8]); out = sys.argv[9]
bf = sys.argv[10] if len(sys.argv) > 10 else "-"; minrun = int(sys.argv[11]) if len(sys.argv) > 11 else 2
im = np.asarray(Image.open(img).convert("RGB")).astype(int); H, W, _ = im.shape
R, G, B = im[..., 0], im[..., 1], im[..., 2]; YY, XX = np.indices(R.shape)
m = eval(rule)
occ = set()
if bf != "-":
    for line in open(bf):
        p = line.split("#")[0].split()
        if not p: continue
        s = BUILDING_TYPES[p[0]].size; x, y = int(p[1]), int(p[2])
        occ |= {(x + i, y + j) for i in range(s) for j in range(s)}
score = {}
for x in range(44):
    for y in range(44):
        sx = cx + (x - y) * a; sy = top + (x + y + 1) * b - lift
        x0, x1, y0, y1 = int(sx - a * .3), int(sx + a * .3) + 1, int(sy - b * .5), int(sy + b * .5) + 1
        if x0 < 0 or y0 < 0 or x1 >= W or y1 >= H: continue
        score[(x, y)] = m[y0:y1, x0:x1].mean()
cand = {t for t, v in score.items() if v >= thr and t not in occ}
keep = set(); left = set(cand)
while left:
    s0 = left.pop(); comp = {s0}; st = [s0]
    while st:
        x, y = st.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n in left: left.discard(n); comp.add(n); st.append(n)
    if len(comp) >= minrun: keep |= comp
    else: print("dropped", sorted(comp), [round(score[t], 2) for t in comp])
json.dump(sorted([list(t) for t in keep]), open(out, "w"))
print(len(keep), "wall tiles; hist", np.histogram(list(score.values()), bins=10, range=(0, 1))[0].tolist())
