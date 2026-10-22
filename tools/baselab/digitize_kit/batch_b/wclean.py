"""wclean.py walls.json buildings.txt OUT.json [add x,y ...] [del x,y ...] [addseg x0,y0-x1,y1] [delseg ...]:
drop isolated walls (no 4-neighbour), close single gaps in straight lines (not under buildings), apply manual edits."""
import sys, json
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from baselab.mechanics import BUILDING_TYPES
w = {tuple(t) for t in json.load(open(sys.argv[1]))}
occ = set()
for line in open(sys.argv[2]):
    p = line.split("#")[0].split()
    if not p or p[0].startswith("T:"): continue
    s = BUILDING_TYPES[p[0]].size; x, y = int(p[1]), int(p[2]); occ |= {(x + i, y + j) for i in range(s) for j in range(s)}
args = sys.argv[4:]; mode = None; add, dele = set(), set()
def seg(s):
    a, b = s.split("-"); x0, y0 = map(int, a.split(",")); x1, y1 = map(int, b.split(","))
    if x0 != x1 and y0 != y1: raise SystemExit("bad seg " + s)
    return {(x, y) for x in range(min(x0, x1), max(x0, x1) + 1) for y in range(min(y0, y1), max(y0, y1) + 1)}
for t in args:
    if t in ("add", "del", "addseg", "delseg"): mode = t; continue
    if mode == "add": add.add(tuple(map(int, t.split(","))))
    elif mode == "del": dele.add(tuple(map(int, t.split(","))))
    elif mode == "addseg": add |= seg(t)
    elif mode == "delseg": dele |= seg(t)
w -= occ
nb = lambda t, s: sum((t[0] + dx, t[1] + dy) in s for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
iso = {t for t in w if nb(t, w) == 0}
w -= iso
gaps = set()
for x in range(44):
    for y in range(44):
        t = (x, y)
        if t in w or t in occ: continue
        if ((x - 1, y) in w and (x + 1, y) in w) or ((x, y - 1) in w and (x, y + 1) in w): gaps.add(t)
w |= gaps; w |= add; w -= dele
bad = w & occ
json.dump(sorted([list(t) for t in w]), open(sys.argv[3], "w"))
print(len(w), "walls; dropped isolated", len(iso), "closed gaps", len(gaps), "under buildings", sorted(bad))
