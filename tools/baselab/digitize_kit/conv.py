"""conv.py cx top a b WINS.txt RAW.txt OUT.txt : RAW lines 'win key zx zy [mode] [# note]' (bottom tips in zoomed windows)
or 'abs key X Y [mode]' (direct tiles) or 'orig key sx sy [mode]' (original-image bottom tip). WINS lines 'name ox oy z'."""
import sys
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from baselab.mechanics import BUILDING_TYPES
cx, top, a, b = map(float, sys.argv[1:5]); wins = {}
for l in open(sys.argv[5]):
    p = l.split()
    if p: wins[p[0]] = tuple(map(float, p[1:4]))
out = []
for l in open(sys.argv[6]):
    note = l.split("#", 1)[1].strip() if "#" in l else ""
    p = l.split("#")[0].split()
    if not p: continue
    w, k = p[0], p[1]; mode = p[4] if len(p) > 4 else ""
    if w == "abs":
        X, Y = int(p[2]), int(p[3]); tip = ""
    else:
        if w == "orig": sx, sy = float(p[2]), float(p[3])
        else:
            ox, oy, z = wins[w]; sx, sy = ox + float(p[2]) / z, oy + float(p[3]) / z
        u = (sx - cx) / a; v = (sy - top) / b; x = (u + v) / 2; y = (v - u) / 2
        s = BUILDING_TYPES[k].size; m = float(__import__("os").environ.get("M", "0.45")) + (0.3 if k == "camp" else 0)
        X, Y = round(x - s + m), round(y - s + m)
        cl = (min(max(X, 0), 44 - s), min(max(Y, 0), 44 - s))
        if cl != (X, Y): note = (note + f" clamped from {X},{Y}").strip(); X, Y = cl
        tip = f"tip {x:.2f},{y:.2f} "
    out.append(f"{k} {X} {Y}{(' ' + mode) if mode else ''}  # {tip}{w} {note}".rstrip())
open(sys.argv[7], "w").write("\n".join(out) + "\n"); print(len(out), "buildings")
