"""gapfill.py walls.json buildings.txt OUT.json maxgap : fill straight gaps (same row/col) of up to maxgap free tiles
between two walls; repeat until stable."""
import sys, json
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from baselab.mechanics import BUILDING_TYPES
w = {tuple(t) for t in json.load(open(sys.argv[1]))}; g = int(sys.argv[4])
occ = set()
for line in open(sys.argv[2]):
    p = line.split("#")[0].split()
    if not p or p[0].startswith("T:"): continue
    s = BUILDING_TYPES[p[0]].size; x, y = int(p[1]), int(p[2]); occ |= {(x + i, y + j) for i in range(s) for j in range(s)}
added = 0
while True:
    new = set()
    for (x, y) in w:
        for dx, dy in ((1, 0), (0, 1)):
            for k in range(2, g + 2):
                if (x + dx * k, y + dy * k) in w:
                    seg = [(x + dx * i, y + dy * i) for i in range(1, k)]
                    if all(t not in w and t not in occ for t in seg): new |= set(seg)
                    break
    new -= w
    if not new: break
    w |= new; added += len(new)
json.dump(sorted(map(list, w)), open(sys.argv[3], "w")); print(len(w), "walls, added", added)
