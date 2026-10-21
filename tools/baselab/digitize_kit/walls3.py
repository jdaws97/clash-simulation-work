"""walls2.py IMG cx top a b lift thr buildings.txt OUT.json : pale-cap wall tiles, excluding building footprints,
keeping 4-connected runs (components >= 2 tiles, or isolated tiles with a strong score)."""
import sys, json
import numpy as np
from PIL import Image
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from baselab.mechanics import BUILDING_TYPES
img = sys.argv[1]; cx, top, a, b, lift, thr = map(float, sys.argv[2:8]); bf, out = sys.argv[8], sys.argv[9]
im = np.asarray(Image.open(img).convert("RGB")).astype(float); H, W, _ = im.shape
R, G, B = im[..., 0], im[..., 1], im[..., 2]
pale = (R > 228) & (G > 205) & (B > 150)
occ = set()
for line in open(bf):
    p = line.split("#")[0].split()
    if not p: continue
    s = BUILDING_TYPES[p[0]].size; x, y = int(p[1]), int(p[2])
    occ |= {(x + i, y + j) for i in range(s) for j in range(s)}
score = {}
for x in range(44):
    for y in range(44):
        sx = cx + (x - y) * a; sy = top + (x + y + 1) * b - lift
        x0, x1, y0, y1 = int(sx - a * .3), int(sx + a * .3), int(sy - b * .7), int(sy + b * .7)
        if x0 < 0 or y0 < 0 or x1 >= W or y1 >= H: continue
        score[(x, y)] = pale[y0:y1, x0:x1].mean()
cand = {t for t, v in score.items() if v >= thr and t not in occ}
keep = set(); left = set(cand)
while left:
    s0 = left.pop(); comp = {s0}; st = [s0]
    while st:
        x, y = st.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n in left: left.discard(n); comp.add(n); st.append(n)
    if len(comp) >= 2 or score[s0] > float(sys.argv[10] if len(sys.argv) > 10 else 9): keep |= comp
    elif len(comp) == 1: print("single", s0, round(score[s0], 2))
json.dump(sorted([list(t) for t in keep]), open(out, "w"))
vis = sum(1 for (x, y) in score)
print(len(keep), "wall tiles; visible tiles", vis)
