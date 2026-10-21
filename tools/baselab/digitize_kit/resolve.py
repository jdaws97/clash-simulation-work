"""resolve.py buildings.txt walls.json OUT.txt : nudge overlapping buildings (later lines move) to the nearest free spot;
walls under a building are dropped later by digitize build. Prints every move."""
import sys, json, math
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from baselab.mechanics import BUILDING_TYPES
rows = []
for line in open(sys.argv[1]):
    p = line.split("#")[0].split()
    if p: rows.append([p[0], int(p[1]), int(p[2]), p[3] if len(p) > 3 else None, line.split("#")[1].strip() if "#" in line else ""])
occ = set(); out = []
for k, x, y, m, c in rows:
    s = BUILDING_TYPES[k].size
    t = lambda x, y: {(x + i, y + j) for i in range(s) for j in range(s)}
    if t(x, y) & occ or not all(0 <= a < 44 for a in (x, y, x + s - 1, y + s - 1)):
        best = None
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                X, Y = x + dx, y + dy
                if X < 0 or Y < 0 or X + s > 44 or Y + s > 44 or t(X, Y) & occ: continue
                d = math.hypot(dx, dy)
                if best is None or d < best[0]: best = (d, X, Y)
        if best is None: print("NO ROOM", k, x, y); continue
        print(f"nudge {k} {x},{y} -> {best[1]},{best[2]}"); c = (c + f" nudged from {x},{y}").strip(); x, y = best[1], best[2]
    occ |= t(x, y); out.append(f"{k} {x} {y}" + (f" {m}" if m else "") + (f"  # {c}" if c else ""))
open(sys.argv[3], "w").write("\n".join(out) + "\n")
