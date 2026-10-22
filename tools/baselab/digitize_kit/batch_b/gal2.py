"""gal2.py IMG OUT name:sx:sy_bottom ... : gallery of sprites (crop 80x90 above the base point, x3)."""
import sys
from PIL import Image, ImageDraw, ImageFont
im = Image.open(sys.argv[1]).convert("RGB"); out = sys.argv[2]; items = [s.split(":") for s in sys.argv[3:]]
Z = 3; cw, ch = 84, 84; W, H = cw * Z, ch * Z + 18; cols = 6
sheet = Image.new("RGB", (cols * W, ((len(items) + cols - 1) // cols) * H)); d = ImageDraw.Draw(sheet); f = ImageFont.truetype("arialbd.ttf", 14)
for i, (n, x, y) in enumerate(items):
    x, y = float(x), float(y)
    c = im.crop((int(x - cw / 2), int(y - ch + 8), int(x + cw / 2), int(y + 8))).resize((cw * Z, ch * Z), Image.LANCZOS)
    sheet.paste(c, ((i % cols) * W, (i // cols) * H + 18)); d.text(((i % cols) * W + 3, (i // cols) * H + 1), f"{n} {int(x)},{int(y)}", fill="yellow", font=f)
sheet.save(out, quality=88)
