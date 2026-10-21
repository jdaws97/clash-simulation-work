import sys
from collections import Counter
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from baselab.mechanics import INVENTORY, BUILDING_TYPES
c = Counter()
occ = {}
for line in open(sys.argv[1]):
    b = line.split("#")[0].split()
    if not b or b[0].isdigit(): continue
    k, x, y = b[0], int(b[1]), int(b[2]); c[k] += 1; s = BUILDING_TYPES[k].size
    for i in range(s):
        for j in range(s):
            t = (x + i, y + j)
            if not (0 <= t[0] < 44 and 0 <= t[1] < 44): print("OUT", k, x, y)
            if t in occ: print("OVERLAP", k, x, y, "with", occ[t])
            occ[t] = f"{k}@{x},{y}"
inv = INVENTORY[16]
print("missing:", {k: v - c[k] for k, v in inv.items() if v > c[k]})
print("extra:", {k: c[k] - v for k, v in inv.items() if c[k] > v})
print("total", sum(c.values()), "of", sum(v for k, v in inv.items()))
