import sys
import numpy as np
from PIL import Image, ImageFilter
S = sys.argv[1]
m = Image.open(S + "/digitize/img/bp-TH16_ranked.jpg").convert("RGB")
t = Image.open(S + "/digitize/img/bp-th16_trap_view.jpg").convert("RGB")
cxm, tm, am, bm = 1361.7, -138.4, 29.118, 21.822
cxt, tt, at, bt = 1310.8, -146.3, 29.373, 22.0
A = at / am; C = cxt - cxm * at / am; E = bt / bm; F = tt - tm * bt / bm
w = t.transform(m.size, Image.AFFINE, (A, 0, C, 0, E, F), resample=Image.BILINEAR)
w.save(S + "/digitize/trap_warped.jpg", quality=90)
d = np.abs(np.asarray(m.filter(ImageFilter.GaussianBlur(2))).astype(int) - np.asarray(w.filter(ImageFilter.GaussianBlur(2))).astype(int)).sum(2)
img = Image.fromarray(np.clip(d * 2, 0, 255).astype("uint8"))
img.resize((1440, 810)).save(S + "/digitize/diff.jpg")
print(np.percentile(d, [50, 90, 99]))
