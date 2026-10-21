import sys, glob
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
src, out, pat = sys.argv[1], sys.argv[2], sys.argv[3]
files = sorted(glob.glob(src + "/" + pat))
font = ImageFont.truetype("arial.ttf", 22)
W, H = 640, 400
per = 6
for k in range(0, len(files), per):
    sheet = Image.new("RGB", (W * 2, H * 3), "black")
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(files[k:k + per]):
        im = Image.open(f).convert("RGB")
        print(Path(f).name, im.size)
        im.thumbnail((W, H - 26))
        x, y = (i % 2) * W, (i // 2) * H
        sheet.paste(im, (x, y + 26))
        d.text((x + 4, y + 2), Path(f).name[:60], fill="yellow", font=font)
    sheet.save(f"{out}_{k // per}.jpg", quality=85)
