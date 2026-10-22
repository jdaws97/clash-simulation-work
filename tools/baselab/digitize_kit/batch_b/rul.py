"""rul.py IMG OUT x0 y0 x1 y1 zoom step : crop with original-pixel ruler lines every step px (labels every 2*step)."""
import sys
from PIL import Image, ImageDraw, ImageFont
img, out = sys.argv[1], sys.argv[2]; x0, y0, x1, y1 = map(int, sys.argv[3:7]); z = float(sys.argv[7]); st = int(sys.argv[8])
im = Image.open(img).convert("RGB")
c = im.crop((x0, y0, x1, y1)).resize((int((x1 - x0) * z), int((y1 - y0) * z)), Image.LANCZOS)
d = ImageDraw.Draw(c, "RGBA"); f = ImageFont.truetype("arialbd.ttf", 12)
for X in range((x0 // st + 1) * st, x1, st):
    d.line([((X - x0) * z, 0), ((X - x0) * z, c.height)], fill=(255, 255, 0, 70 if X % (2 * st) else 130))
    if X % (2 * st) == 0: d.text(((X - x0) * z + 2, 2), str(X), fill=(255, 255, 0, 255), font=f, stroke_width=1, stroke_fill=(0, 0, 0, 255))
for Y in range((y0 // st + 1) * st, y1, st):
    d.line([(0, (Y - y0) * z), (c.width, (Y - y0) * z)], fill=(0, 255, 255, 70 if Y % (2 * st) else 130))
    if Y % (2 * st) == 0: d.text((2, (Y - y0) * z + 2), str(Y), fill=(0, 255, 255, 255), font=f, stroke_width=1, stroke_fill=(0, 0, 0, 255))
c.save(out, quality=88)
