"""finalize.py layout.json out.json overlay_src.png notes.txt : set notes, save, write a small overlay next to it, print checks."""
import sys
from pathlib import Path
sys.path.insert(0, r"C:/Users/jarod/Documents/clash-lab/src")
from PIL import Image
from baselab.layout import Layout
src, out, ov, notes = sys.argv[1:5]
lay = Layout.load(src)
lay.name = Path(out).stem
lay.notes = Path(notes).read_text(encoding="utf-8").strip()
lay.save(Path(out))
im = Image.open(ov).convert("RGB"); im.thumbnail((1400, 1400)); im.save(Path(out).with_suffix(".jpg"), quality=82)
chk = Layout.load(out)
print("buildings", len(chk.buildings), "walls", len(chk.walls), "traps", len(chk.traps))
print("problems(require_full=False):", chk.problems(require_full=False))
print("problems():", chk.problems())
