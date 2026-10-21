import sys
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageFont
from scipy.ndimage import label, binary_closing, find_objects
S = sys.argv[1]
m = Image.open(S + "/digitize/img/bp-TH16_ranked.jpg").convert("RGB")
w = Image.open(S + "/digitize/trap_warped.jpg").convert("RGB")
cx, top, a, b = 1361.7, -138.4, 29.118, 21.822
d = np.abs(np.asarray(m.filter(ImageFilter.GaussianBlur(2))).astype(int) - np.asarray(w.filter(ImageFilter.GaussianBlur(2))).astype(int)).sum(2)
mask = binary_closing(d > 110, iterations=3)
lab, n = label(mask)
res = []
for i, sl in enumerate(find_objects(lab), 1):
    area = (lab[sl] == i).sum()
    if area < 300: continue
    y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
    if x0 < 120 or x1 > 2760: continue
    gx, gy = (x0 + x1) / 2, y1 - 8  # ground point ~ bottom of blob
    u = (gx - cx) / a; v = (gy - top) / b
    res.append((area, x0, y0, x1, y1, round((u + v) / 2 - 0.5, 1), round((v - u) / 2 - 0.5, 1)))
res.sort(key=lambda r: (r[2]))
for r in res: print(r)
# gallery from warped trap image
font = ImageFont.truetype("arial.ttf", 15)
cols = 6; W = 200
items = [r for r in res if r[0] < 20000]
sheet = Image.new("RGB", (cols * W, ((len(items) + cols - 1) // cols) * (W + 20))); dr = ImageDraw.Draw(sheet)
for k, r in enumerate(items):
    _, x0, y0, x1, y1, tx, ty = r
    c = (x0 + x1) // 2, (y0 + y1) // 2
    cr = w.crop((c[0] - 70, c[1] - 70, c[0] + 70, c[1] + 70)).resize((W - 4, W - 4))
    sheet.paste(cr, ((k % cols) * W + 2, (k // cols) * (W + 20) + 20)); dr.text(((k % cols) * W + 4, (k // cols) * (W + 20) + 2), f"#{k} {tx},{ty} a{r[0]}", fill="yellow", font=font)
sheet.save(S + "/digitize/blobs.jpg", quality=88)
