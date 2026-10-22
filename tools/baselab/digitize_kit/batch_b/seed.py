"""seed.py LAYOUT.json : write <stem>-seed.json: walls topped up with generator.top_up_walls, missing traps placed on free
tiles inside the walled area (tiles a ground unit cannot reach from the map edge), spread by farthest-point sampling."""
import sys, json, random, math
from pathlib import Path
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from baselab.layout import Layout, TrapPlacement
from baselab.generator import top_up_walls
from baselab.deploy import outside
from baselab.mechanics import TRAP_INVENTORY, WALL_COUNT
src = Path(sys.argv[1]); lay = Layout.load(src); rng = random.Random(16)
occ = set(lay.occupancy())
w0 = set(lay.walls)
top_up_walls(lay, occ, rng)
added_w = sorted(set(lay.walls) - w0)
from scipy.spatial import Delaunay
hull = Delaunay(sorted(w0))
free = [(x, y) for x in range(44) for y in range(44) if (x, y) not in occ and hull.find_simplex((x, y)) >= 0]
inside = len(free)
have = {}
for t in lay.traps: have[t.key] = have.get(t.key, 0) + 1
need = []
for k, n in TRAP_INVENTORY[16].items():
    need += [k] * (n - have.get(k, 0))
need.sort(key=lambda k: k not in ("giant", "giga"))  # 2x2 first
placed = []
pts = [(t.x, t.y) for t in lay.traps]
for k in need:
    s = 2 if k in ("giant", "giga") else 1
    cands = [(x, y) for x, y in free if all((x + i, y + j) in set(free) - occ for i in range(s) for j in range(s))] if s == 2 else [t for t in free if t not in occ]
    if not cands: raise SystemExit("no room for trap " + k)
    rng.shuffle(cands)
    best = max(cands[:400], key=lambda c: min((math.hypot(c[0] - p[0], c[1] - p[1]) for p in pts), default=99))
    x, y = best
    lay.traps.append(TrapPlacement(k, x, y, "ground" if k == "skeleton" else None))
    for i in range(s):
        for j in range(s): occ.add((x + i, y + j))
    pts.append(best); placed.append(f"{k} {x},{y}")
lay.name = src.stem + "-seed"
lay.notes = (lay.notes + f"\nSEED COMPLETION (from {src.name}): walls {len(w0)} -> {len(lay.walls)}: {len(added_w)} walls ADDED by "
             "baselab.generator.top_up_walls (dead-end spikes / single posts next to existing walls, not the builder's design): "
             + " ".join(f"{x},{y}" for x, y in added_w) + f". Traps: {len(placed)} ADDED on free tiles inside the convex hull of the "
             f"digitized walls ({inside} free tiles; the wall ring has gaps so 'enclosed' is not well defined), spread by farthest-point sampling (not the builder's trap layout; the search's trap "
             "placer is expected to move them; skeleton traps set to ground): " + "; ".join(placed) + ".")
dst = src.with_name(src.stem + "-seed.json"); lay.save(dst)
chk = Layout.load(dst)
print(dst.name, "walls", len(chk.walls), "traps", len(chk.traps), "buildings", len(chk.buildings))
print("problems():", chk.problems())
