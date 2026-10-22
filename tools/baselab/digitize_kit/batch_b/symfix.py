"""symfix.py IN OUT [maxd] : for same-key pairs that are near-mirrors (x<->y) within maxd tiles, average the measured
u/xy (from conv.py comments) and re-snap both, making the pair exactly mirrored. Prints changes."""
import sys, re, math
rows = []
for line in open(sys.argv[1]):
    body, _, com = line.partition("#"); p = body.split()
    if not p: continue
    m = re.search(r"u (-?[\d.]+) xy (-?[\d.]+)", com)
    rows.append(dict(k=p[0], x=int(p[1]), y=int(p[2]), u=float(m[1]) if m else None, sm=float(m[2]) if m else None, com=com.strip(), line=line.rstrip()))
maxd = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
used = set()
def snap(u, sm):
    best = None
    for uu in (math.floor(u), math.ceil(u)):
        for ss in range(int(sm) - 2, int(sm) + 3):
            if (ss - uu) % 2: continue
            d = (uu - u) ** 2 + ((ss - sm) / 1.2) ** 2
            if best is None or d < best[0]: best = (d, uu, ss)
    return best[1], best[2]
for i, r in enumerate(rows):
    if i in used or r["u"] is None or r["u"] >= 0: continue
    best = None
    for j, q in enumerate(rows):
        if j == i or j in used or q["k"] != r["k"] or q["u"] is None or q["u"] <= 0: continue
        d = math.hypot(q["x"] - r["y"], q["y"] - r["x"])
        if d <= maxd and (best is None or d < best[0]): best = (d, j)
    if not best: continue
    j = best[1]; q = rows[j]
    if best[0] == 0: used |= {i, j}; continue
    u = (abs(r["u"]) + abs(q["u"])) / 2; sm = (r["sm"] + q["sm"]) / 2
    uu, ss = snap(u, sm)  # uu > 0 for the right one
    xr, yr = (ss + uu) // 2, (ss - uu) // 2
    print(f"{r['k']}: {r['x']},{r['y']} & {q['x']},{q['y']} -> {yr},{xr} & {xr},{yr}")
    r["x"], r["y"] = yr, xr; q["x"], q["y"] = xr, yr; used |= {i, j}
with open(sys.argv[2], "w") as f:
    for r in rows:
        f.write(f"{r['k']} {r['x']} {r['y']}" + (f"  # {r['com']}" if r["com"] else "") + "\n")
