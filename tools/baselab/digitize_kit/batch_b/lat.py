"""lat.py a b c0 d0 cx_guess topcap_guess : lattice (cx, top_cap) from proj.py phases, nearest to the guess.
Tile-centre wall lines: c = top_cap - s*cx + (2y+1) b, d = top_cap + s*cx + (2x+1) b."""
import sys
a, b, c0, d0, cxg, tg = map(float, sys.argv[1:7])
s = b / a
best = []
for k1 in range(-80, 81):
    for k2 in range(-80, 81):
        c = c0 + 2 * b * k1; d = d0 + 2 * b * k2
        # c = T - s*cx + b ; d = T + s*cx + b  (y = 0, x = 0 lines)
        T = (c + d) / 2 - b; cx = (d - c) / (2 * s)
        best.append((abs(cx - cxg) / a + abs(T - tg) / b, cx, T))
best.sort()
for r in best[:4]:
    print("cx %.2f top_cap %.2f   (dist %.2f)" % (r[1], r[2], r[0]))
