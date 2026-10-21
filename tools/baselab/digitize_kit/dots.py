import sys
from PIL import Image, ImageDraw
img = sys.argv[1]; cx, top, a, b = map(float, sys.argv[2:6]); out = sys.argv[6]; x0, y0, x1, y1 = map(int, sys.argv[7:11]); z = float(sys.argv[11])
im = Image.open(img).convert("RGB").crop((x0, y0, x1, y1)); im = im.resize((int(im.width * z), int(im.height * z)), Image.LANCZOS)
d = ImageDraw.Draw(im)
Q = lambda x, y: ((cx + (x - y) * a - x0) * z, (top + (x + y) * b - y0) * z)
for i in range(44):
    for j in range(44):
        qx, qy = Q(i + .5, j + .5)
        col = (0, 255, 0) if (i + j) % 2 == 0 else (255, 0, 0)
        d.ellipse([qx - 3, qy - 3, qx + 3, qy + 3], fill=col)
im.save(out, quality=90)
