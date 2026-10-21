import sys
from PIL import Image, ImageDraw
img, x0, y0, x1, y1, out = sys.argv[1], *map(int, sys.argv[2:6]), sys.argv[6]
z = float(sys.argv[7]) if len(sys.argv) > 7 else 2
step = int(sys.argv[8]) if len(sys.argv) > 8 else 50
im = Image.open(img).convert("RGB")
c = im.crop((x0, y0, x1, y1)).resize((int((x1 - x0) * z), int((y1 - y0) * z)))
d = ImageDraw.Draw(c)
for X in range((x0 // step + 1) * step, x1, step):
    d.line([((X - x0) * z, 0), ((X - x0) * z, c.height)], fill=(255, 255, 0), width=1); d.text(((X - x0) * z + 2, 2), str(X), fill="yellow")
for Y in range((y0 // step + 1) * step, y1, step):
    d.line([(0, (Y - y0) * z), (c.width, (Y - y0) * z)], fill=(255, 255, 0), width=1); d.text((2, (Y - y0) * z + 2), str(Y), fill="yellow")
c.save(out, quality=90)
