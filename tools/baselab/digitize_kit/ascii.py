import sys, json
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from baselab.mechanics import BUILDING_TYPES
w = {tuple(t) for t in json.load(open(sys.argv[1]))}
occ = {}
for line in open(sys.argv[2]):
    p = line.split("#")[0].split()
    if not p: continue
    s = BUILDING_TYPES[p[0]].size; x, y = int(p[1]), int(p[2])
    for i in range(s):
        for j in range(s): occ[(x + i, y + j)] = p[0][0].upper()
print("    " + "".join(str(x % 10) for x in range(44)))
for y in range(44):
    print(f"{y:3d} " + "".join("#" if (x, y) in w and (x, y) not in occ else ("!" if (x, y) in w else occ.get((x, y), ".")) for x in range(44)))
