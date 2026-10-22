"""dewm.py IMG OUT x0 y0 x1 y1 zoom alpha : undo a white overlay of opacity alpha inside the box (where pixels look washed), ruler."""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter
img, out = sys.argv[1], sys.argv[2]; x0, y0, x1, y1 = map(int, sys.argv[3:7]); z = float(sys.argv[7]); al = float(sys.argv[8])
im = np.asarray(Image.open(img).convert("RGB")).astype(float)[y0:y1, x0:x1]
# washed-out mask: low local saturation & high min channel
mn = im.min(2); sat = im.max(2) - mn
wash = gaussian_filter(((mn > 95)).astype(float), 3)
a = al * np.clip(wash * 1.2, 0, 1)[..., None]
rec = np.clip((im - a * 255) / (1 - a), 0, 255)
c = Image.fromarray(rec.astype("uint8")).resize((int((x1 - x0) * z), int((y1 - y0) * z)), Image.LANCZOS)
d = ImageDraw.Draw(c, "RGBA"); f = ImageFont.truetype("arialbd.ttf", 12)
for X in range((x0 // 20 + 1) * 20, x1, 20):
    d.line([((X - x0) * z, 0), ((X - x0) * z, c.height)], fill=(255, 255, 0, 60))
    if X % 40 == 0: d.text(((X - x0) * z + 2, 2), str(X), fill=(255, 255, 0, 255), font=f)
for Y in range((y0 // 20 + 1) * 20, y1, 20):
    d.line([(0, (Y - y0) * z), (c.width, (Y - y0) * z)], fill=(0, 255, 255, 60))
    if Y % 40 == 0: d.text((2, (Y - y0) * z + 2), str(Y), fill=(0, 255, 255, 255), font=f)
c.save(out, quality=90)
