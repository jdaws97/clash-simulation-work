"""seed.py IN.json OUT.json [--seed N] [--box keys:x0,x1,y0,y1 ...]

Complete a digitized layout into a search seed:
  1. walls topped up to 325 with baselab.generator.top_up_walls (dead-end spikes/posts next to existing walls);
  2. missing traps placed on free tiles inside the walled area (flood fill from the village edge with walls as
     barriers; falls back to the convex hull of the walls when gaps leak), spread by farthest-point sampling.
     --box puts the listed trap keys (comma list, or 'all') preferentially inside a tile box first.
Appends a description of every addition to notes and prints problems()."""
import sys, json, math, random, argparse
from pathlib import Path
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from baselab.layout import Layout, TrapPlacement
from baselab.generator import top_up_walls
from baselab.mechanics import TRAP_INVENTORY, WALL_COUNT, VILLAGE

ap = argparse.ArgumentParser()
ap.add_argument("inp"); ap.add_argument("out")
ap.add_argument("--seed", type=int, default=16)
ap.add_argument("--box", action="append", default=[])
args = ap.parse_args()
rng = random.Random(args.seed)
lay = Layout.load(args.inp)
src_name = lay.name
lay.name = Path(args.out).stem
occ = set(lay.occupancy())
n0 = len(lay.walls)
before = set(lay.walls)
added_w = top_up_walls(lay, occ, rng, target=WALL_COUNT)
new_walls = sorted(set(lay.walls) - before)

# walled area
walls = lay.walls
outside = set()
st = [(x, y) for x in range(VILLAGE) for y in (0, VILLAGE - 1)] + [(x, y) for y in range(VILLAGE) for x in (0, VILLAGE - 1)]
st = [t for t in st if t not in walls]
outside.update(st)
while st:
    x, y = st.pop()
    for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if 0 <= n[0] < VILLAGE and 0 <= n[1] < VILLAGE and n not in walls and n not in outside:
            outside.add(n); st.append(n)
inside = {(x, y) for x in range(VILLAGE) for y in range(VILLAGE)} - outside - walls
how = "enclosed by walls"
if len(inside) < 300:
    # convex hull of the walls (monotone chain), then point-in-polygon on tile centres
    pts = sorted(set((x + .5, y + .5) for x, y in walls))
    def cross(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0: hi.pop()
        hi.append(p)
    hull = lo[:-1] + hi[:-1]
    def inhull(q): return all(cross(hull[i], hull[(i + 1) % len(hull)], q) >= 0 for i in range(len(hull)))
    inside = {(x, y) for x in range(VILLAGE) for y in range(VILLAGE) if (x, y) not in walls and inhull((x + .5, y + .5))}
    how = "inside the convex hull of the walls (wall ring has gaps)"

boxes = []
for b in args.box:
    keys, rect = b.split(":")
    x0, x1, y0, y1 = map(int, rect.split(","))
    boxes.append((None if keys == "all" else set(keys.split(",")), (x0, x1, y0, y1)))

have = {}
for t in lay.traps:
    have[t.key] = have.get(t.key, 0) + 1
todo = []
for key, n in TRAP_INVENTORY[lay.town_hall].items():
    todo += [key] * max(0, n - have.get(key, 0))
todo.sort(key=lambda k: 0 if k in ("giant", "giga") else 1)  # 2x2 first
placed_pts = [(t.x + .5, t.y + .5) for t in lay.traps]
added_t = []
sk_air = 0
for key in todo:
    s = 2 if key in ("giant", "giga") else 1
    def fits(x, y):
        return all((x + i, y + j) in inside and (x + i, y + j) not in occ for i in range(s) for j in range(s))
    cands = [(x, y) for (x, y) in inside if fits(x, y)]
    pref = [c for c in cands for keys, (x0, x1, y0, y1) in boxes
            if (keys is None or key in keys) and x0 <= c[0] <= x1 and y0 <= c[1] <= y1]
    pool = pref or cands
    if not pool:
        print("NO ROOM for", key); continue
    rng.shuffle(pool)
    pool = pool[:400]
    def gap(c):
        return min((math.hypot(c[0] + s / 2 - p[0], c[1] + s / 2 - p[1]) for p in placed_pts), default=99) + rng.random() * 0.5
    x, y = max(pool, key=gap)
    mode = None
    if key == "skeleton":
        mode = "ground"
    lay.traps.append(TrapPlacement(key, x, y, mode))
    for i in range(s):
        for j in range(s):
            occ.add((x + i, y + j))
    placed_pts.append((x + s / 2, y + s / 2))
    added_t.append(f"{key} {x},{y}")

note = (f"\nSEED COMPLETION (seed.py, rng seed {args.seed}, from {src_name}.json): "
        f"walls {n0} -> {len(lay.walls)}: {added_w} walls ADDED by baselab.generator.top_up_walls (dead-end spikes/single posts "
        f"next to existing walls, not the builder's design): {' '.join(f'{x},{y}' for x, y in new_walls)}. "
        f"Traps: {len(added_t)} ADDED on free tiles {how}, spread by farthest-point sampling"
        + (f" with preference boxes {args.box}" if args.box else "")
        + f" (not the builder's trap layout; the search's trap placer is expected to move them; skeleton traps set to ground): "
        + "; ".join(added_t) + ".")
lay.notes = (lay.notes or "").rstrip() + note
lay.save(Path(args.out))
chk = Layout.load(args.out)
print("walls", len(chk.walls), "traps", len(chk.traps), "buildings", len(chk.buildings), "| inside tiles", len(inside), how)
print("problems():", chk.problems())
