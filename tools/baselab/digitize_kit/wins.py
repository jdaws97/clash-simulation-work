"""wins.py IMG cx top a b PREFIX W H zoom [walls] [buildings] [traps]: render overlapping screen windows covering the village diamond."""
import sys, subprocess, os
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); pre = sys.argv[6]; Ww, Hh = int(sys.argv[7]), int(sys.argv[8]); z = sys.argv[9]
rest = sys.argv[10:]
P = lambda x, y: (cx + (x - y) * a, top + (x + y) * b)
L, Rr = P(0, 44)[0] - 10, P(44, 0)[0] + 10; T, Bm = P(0, 0)[1] - 30, P(44, 44)[1] + 5
here = os.path.dirname(os.path.abspath(__file__))
k = 0
y = T
r = 0
while y < Bm:
    # diamond x-extent for this band
    yc0, yc1 = y, y + Hh
    def half(yy):  # half width of diamond at screen y
        d = min(yy - P(0, 0)[1], P(44, 44)[1] - yy)
        return max(0, d) * a / b
    hw = max(half(yy) for yy in (yc0, yc1, (P(0, 0)[1] + P(44, 44)[1]) / 2 if yc0 <= (P(0, 0)[1] + P(44, 44)[1]) / 2 <= yc1 else yc0))
    x0, x1 = cx - hw - 15, cx + hw + 15
    n = max(1, int(round((x1 - x0) / (Ww - 40) + 0.49)))
    step = (x1 - x0 - Ww) / max(1, n - 1) if n > 1 else 0
    for c in range(n):
        sx = int(x0 + c * step) if n > 1 else int(cx - Ww / 2)
        out = f"{pre}_{r}{c}.jpg"
        subprocess.run([sys.executable, "-I", os.path.join(here, "zw.py"), img, *sys.argv[2:6], out, str(sx), str(int(y)), str(sx + Ww), str(int(y + Hh)), z, *rest], check=True)
        print(out, sx, int(y), sx + Ww, int(y + Hh))
    y += Hh - 40; r += 1
