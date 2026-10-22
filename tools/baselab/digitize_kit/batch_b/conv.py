"""conv.py cx top a b IN OUT : lines 'key sx sy_bottom [# comment]' (original px: sprite horizontal centre,
lowest visible point of the base) -> 'key x y  # comment (u v)'. Keys starting with T: are traps (sy = trap centre).
Lines already in 'key x y' form (small ints, flagged with '=') pass through: '= key x y'."""
import sys
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from baselab.mechanics import BUILDING_TYPES
cx, top, a, b = map(float, sys.argv[1:5]); DELTA = float(__import__("os").environ.get("DELTA", "1.6"))
out = []
for line in open(sys.argv[5]):
    body, _, com = line.partition("#"); p = body.split()
    if not p: out.append(line.rstrip()); continue
    if p[0] == "=": out.append(" ".join(p[1:]) + (f"  #{com.rstrip()}" if com else "")); continue
    k, sx, sy = p[0], float(p[1]), float(p[2])
    u = (sx - cx) / a; v = (sy - top) / b
    if k.startswith("T:"):
        s = 2 if k[2:] in ("giant", "giga") else 1
        sm = v - s  # centre of footprint at v = x+y+s
    else:
        s = BUILDING_TYPES[k].size
        sm = v + float(__import__("os").environ.get("D0", "0.4")) + float(__import__("os").environ.get("D1", "0.2")) * s - 2 * s  # x + y estimate (base-bottom margin grows with size)
    ui = round(u)
    if s % 2 == 1:
        pass
    # x - y = u for the footprint centre in all cases (centre u = x - y)
    cands = []
    for uu in (ui - 1, ui, ui + 1):
        for ss in range(int(sm) - 2, int(sm) + 3):
            if (ss - uu) % 2: continue
            cands.append(((uu - u) ** 2 * 1.0 + ((ss - sm) / 1.2) ** 2, uu, ss))
    cands.sort()
    _, uu, ss = cands[0]
    x, y = (ss + uu) // 2, (ss - uu) // 2
    out.append(f"{k} {x} {y}  # u {u:.2f} xy {sm:.2f}" + (f" {com.strip()}" if com.strip() else ""))
open(sys.argv[6], "w").write("\n".join(out) + "\n")
print("\n".join(out))
