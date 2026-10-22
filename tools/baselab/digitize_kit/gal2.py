"""gal2.py IMG OUT r zoom name:sx:sy ... : gallery of crops (+-r px, shifted up) around original-image points."""
import sys
from PIL import Image, ImageDraw, ImageFont
img, out = sys.argv[1:3]; r = int(sys.argv[3]); z = float(sys.argv[4])
im = Image.open(img).convert("RGB"); items = [s.split(":") for s in sys.argv[5:]]
W = int(2 * r * z); H = int(2.2 * r * z); cols = 5
sheet = Image.new("RGB", (cols * W, ((len(items) + cols - 1) // cols) * (H + 20)), "black"); d = ImageDraw.Draw(sheet)
f = ImageFont.truetype("arialbd.ttf", 16)
for i, (n, x, y) in enumerate(items):
    x, y = float(x), float(y)
    c = im.crop((int(x - r), int(y - 1.4 * r), int(x + r), int(y + 0.8 * r))).resize((W, H), Image.LANCZOS)
    sheet.paste(c, ((i % cols) * W, (i // cols) * (H + 20) + 20)); d.text(((i % cols) * W + 3, (i // cols) * (H + 20) + 1), n, fill="yellow", font=f)
sheet.save(out, quality=90)
