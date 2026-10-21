"""merge_impute.py buildings.txt walls.json OUT_layout.json : convert an unmerged TH16 layout (7 cannons / 8 ATs) to merged
inventory by merging the two closest cannon pairs into Ricochet Cannons and the two closest AT pairs into Multi-Archer Towers
(the merged building keeps the first tower's spot; the second spot is freed), then impute anything still missing with
make_reference_bases.impute. Prints every change."""
import sys, json, math, random, itertools
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src"); sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/tools/baselab")
from baselab.layout import Layout, Placement
from make_reference_bases import impute
lay = Layout("draft", town_hall=16)
for line in open(sys.argv[1]):
    p = line.split("#")[0].split()
    if p: lay.buildings.append(Placement(p[0], int(p[1]), int(p[2]), p[3] if len(p) > 3 else None))
taken = set()
for b in lay.buildings: taken |= set(b.tiles())
lay.walls = {tuple(w) for w in json.load(open(sys.argv[2]))} - taken
notes = []
def merge(key, newkey, keep):
    while sum(b.key == key for b in lay.buildings) > keep:
        bs = [b for b in lay.buildings if b.key == key]
        a, c = min(itertools.combinations(bs, 2), key=lambda p: math.hypot(p[0].x - p[1].x, p[0].y - p[1].y))
        a.key = newkey; lay.buildings.remove(c)
        notes.append(f"merged {key} {a.x},{a.y} + {c.x},{c.y} -> {newkey} at {a.x},{a.y}")
        if sum(b.key == newkey for b in lay.buildings) >= 2: break
merge("cannon", "ric", 3); merge("at", "mat", 4)
for b in lay.buildings:
    if b.key == "inferno" and not b.mode: b.mode = "single"
    if b.key == "xbow" and not b.mode: b.mode = "both"
lay.traps = []
imp = impute(lay, random.Random(16))
imp = [n for n in imp if "trap" not in n]
lay.traps = []
notes += imp
from pathlib import Path; lay.save(Path(sys.argv[3])); print("\n".join(notes)); print("problems(require_full=False):", lay.problems(require_full=False))
json.dump(notes, open(sys.argv[3] + ".changes.json", "w"))
