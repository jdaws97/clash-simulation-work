"""build.py IMG cx top a b buildings.txt walls.json OUT.json NOTES.txt [impute key:hx:hy ...]
Layout from transcription: walls under buildings dropped; each imputed building goes to the free spot nearest the hint tile
(not on walls). Default modes: inferno single, xbow both, st rage, sweeper toward centre. Writes OUT.json and a small overlay OUT.jpg."""
import sys, json, math
from pathlib import Path
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src"); sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/tools/baselab")
from PIL import Image
from baselab.layout import Layout, Placement
from baselab.mechanics import BUILDING_TYPES
from grid_overlay import draw
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); bf, wf, out, nf = sys.argv[6:10]
lay = Layout(Path(out).stem, town_hall=16)
for line in open(bf):
    p = line.split("#")[0].split()
    if p: lay.buildings.append(Placement(p[0], int(p[1]), int(p[2]), p[3] if len(p) > 3 else None))
taken = set()
for bd in lay.buildings: taken |= set(bd.tiles())
lay.walls = {tuple(w) for w in json.load(open(wf))} - taken
added = []
for it in sys.argv[10:]:
    k, hx, hy = it.split(":"); hx, hy = float(hx), float(hy); s = BUILDING_TYPES[k].size
    occ = taken | lay.walls
    best = min(((math.hypot(x + s / 2 - hx, y + s / 2 - hy), x, y) for x in range(45 - s) for y in range(45 - s)
                if not any((x + i, y + j) in occ for i in range(s) for j in range(s))))
    lay.buildings.append(Placement(k, best[1], best[2])); taken |= set(lay.buildings[-1].tiles()); added.append(f"{k} {best[1]},{best[2]}")
for bd in lay.buildings:
    if bd.key == "inferno" and not bd.mode: bd.mode = "single"
    if bd.key == "xbow" and not bd.mode: bd.mode = "both"
    if bd.key == "st" and not bd.mode: bd.mode = "rage"
    if bd.key == "sweeper" and not bd.mode:
        ang = math.atan2(22 - (bd.y + 1), 22 - (bd.x + 1)); bd.mode = ["E", "SE", "S", "SW", "W", "NW", "N", "NE"][int(round(ang / (math.pi / 4))) % 8]
lay.traps = []
notes = Path(nf).read_text(encoding="utf-8").strip()
if added: notes = notes.replace("{IMPUTED}", "; ".join(added))
lay.notes = notes
lay.save(Path(out))
im = draw(Image.open(img), {"cx": cx, "top": top, "a": a, "b": b}, lay.to_json())
P = lambda x, y: (cx + (x - y) * a, top + (x + y) * b)
xs = [P(0, 44)[0] - 20, P(44, 0)[0] + 20]; ys = [max(0, P(0, 0)[1] - 30), min(im.height, P(44, 44)[1] + 10)]
im = im.crop((int(max(0, xs[0])), int(ys[0]), int(min(im.width, xs[1])), int(ys[1])))
im.save(Path(out).with_suffix(".jpg"), quality=80)
chk = Layout.load(out)
print("buildings", len(chk.buildings), "walls", len(chk.walls), "traps", len(chk.traps), "imputed", added)
print("problems(require_full=False):", chk.problems(require_full=False))
