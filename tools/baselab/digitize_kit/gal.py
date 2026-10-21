"""gal.py IMG cx top a b OUT name:x:y ... : gallery of crops around tile centres (x, y floats)."""
import sys
from PIL import Image, ImageDraw, ImageFont
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); out = sys.argv[6]; items = [s.split(":") for s in sys.argv[7:]]
im = Image.open(img)
P = lambda x, y: (cx + (x - y) * a, top + (x + y) * b)
cols = 5; W, H = 230, 260
sheet = Image.new("RGB", (cols * W, ((len(items) + cols - 1) // cols) * H)); d = ImageDraw.Draw(sheet); f = ImageFont.truetype("arial.ttf", 16)
for i, (n, x, y) in enumerate(items):
    sx, sy = P(float(x), float(y))
    R0 = float(__import__("os").environ.get("GR", "1")); c = im.crop((int(sx - 90 * R0), int(sy - 140 * R0), int(sx + 90 * R0), int(sy + 50 * R0))).resize((W - 10, int((W - 10) * 190 / 180)))
    sheet.paste(c, ((i % cols) * W + 5, (i // cols) * H + 22)); d.text(((i % cols) * W + 5, (i // cols) * H + 2), f"{n} {x},{y}", fill="yellow", font=f)
sheet.save(out, quality=88)
