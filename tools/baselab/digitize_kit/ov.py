"""ov.py IMG cx top a b OUT [layout.json] [--crop x0 y0 x1 y1] [--scale s]"""
import sys, json
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src"); sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/tools/baselab")
from PIL import Image
from grid_overlay import draw
a = sys.argv[1:]
img, cx, top, A, B, out = a[0], *map(float, a[1:5]), a[5]
lay = None; crop = None; scale = 1.0
rest = a[6:]
i = 0
while i < len(rest):
    if rest[i] == "--crop": crop = tuple(map(int, rest[i+1:i+5])); i += 5
    elif rest[i] == "--scale": scale = float(rest[i+1]); i += 2
    else: lay = json.load(open(rest[i])); i += 1
im = draw(Image.open(img), {"cx": cx, "top": top, "a": A, "b": B}, lay)
if crop: im = im.crop(crop)
if scale != 1: im = im.resize((int(im.width*scale), int(im.height*scale)))
im.save(out, quality=88)
