"""build.py buildings.txt walls.json OUT.json NAME [impute key:x:y ...] : make the layout (walls under buildings dropped),
impute listed keys at the nearest free spot to (x, y), default modes (inferno single, xbow both). Prints checks."""
import sys, json, math
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from pathlib import Path
from baselab.layout import Layout, Placement
from baselab.mechanics import BUILDING_TYPES
bf, wf, out, name = sys.argv[1:5]
lay = Layout(name, town_hall=16)
for line in open(bf):
    p = line.split("#")[0].split()
    if p: lay.buildings.append(Placement(p[0], int(p[1]), int(p[2]), p[3] if len(p) > 3 else None))
occ = set()
for b in lay.buildings: occ |= set(b.tiles())
walls = {tuple(w) for w in json.load(open(wf))}
dropped = walls & occ
lay.walls = walls - occ
for spec in sys.argv[5:]:
    k, x, y = spec.split(":"); x, y = float(x), float(y); s = BUILDING_TYPES[k].size
    best = None
    for X in range(0, 45 - s):
        for Y in range(0, 45 - s):
            t = {(X + i, Y + j) for i in range(s) for j in range(s)}
            if t & occ or t & lay.walls: continue
            d = math.hypot(X + s / 2 - x, Y + s / 2 - y)
            if best is None or d < best[0]: best = (d, X, Y)
    lay.buildings.append(Placement(k, best[1], best[2])); occ |= {(best[1] + i, best[2] + j) for i in range(s) for j in range(s)}
    print(f"IMPUTED {k} at {best[1]},{best[2]}")
for b in lay.buildings:
    if b.key == "inferno" and not b.mode: b.mode = "single"
    if b.key == "xbow" and not b.mode: b.mode = "both"
lay.traps = []
lay.save(Path(out))
print("buildings", len(lay.buildings), "walls", len(lay.walls), "walls dropped under buildings", len(dropped))
print("problems(require_full=False):", lay.problems(require_full=False))
