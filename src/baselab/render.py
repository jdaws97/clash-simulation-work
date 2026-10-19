"""Render layouts to PNG in the in-game diamond orientation.

The image matches what you see in the layout editor: tile (0, 0) at the top
corner, x increasing towards the right-hand edge, y towards the left-hand edge.
Every 4th grid line is drawn darker and numbered along the top edges so a base
can be rebuilt tile by tile.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .layout import Layout
from .mechanics import BUILDING_TYPES, VILLAGE

TILE = 22  # half-width of a tile diamond in pixels
COLORS = {
    "th": (250, 200, 40),
    "cc": (200, 120, 60),
    "inferno": (230, 70, 30),
    "scatter": (180, 60, 160),
    "eagle": (140, 40, 40),
    "mono": (80, 40, 120),
    "xbow": (170, 90, 200),
    "ad": (40, 120, 230),
    "sweeper": (120, 200, 240),
    "at": (110, 170, 80),
    "mat": (60, 150, 60),
    "cannon": (120, 120, 120),
    "ric": (90, 90, 90),
    "bt": (200, 110, 110),
    "wt": (90, 90, 200),
    "mortar": (150, 130, 90),
    "tesla": (240, 240, 120),
    "st": (150, 60, 220),
    "bh": (190, 150, 110),
    "banner": (255, 255, 255),
}
LABELS = {
    "th": "TH",
    "cc": "CC",
    "inferno": "INF",
    "scatter": "SCAT",
    "eagle": "EAGLE",
    "mono": "MONO",
    "xbow": "XB",
    "ad": "AD",
    "sweeper": "SW",
    "at": "AT",
    "mat": "MAT",
    "cannon": "CN",
    "ric": "RIC",
    "bt": "BT",
    "wt": "WT",
    "mortar": "MOR",
    "tesla": "TES",
    "st": "ST",
    "bh": "BH",
    "banner": "HERO",
    "gs": "GS",
    "es": "ES",
    "ds": "DS",
    "gm": "GM",
    "ec": "EC",
    "dd": "DD",
    "camp": "CAMP",
    "barracks": "BAR",
    "dbarracks": "DBAR",
    "sf": "SF",
    "dsf": "DSF",
    "lab": "LAB",
    "workshop": "WS",
    "pethouse": "PET",
    "smith": "SMITH",
    "herohall": "HALL",
    "helper": "HELP",
    "bob": "BOB",
}
TRAP_COLORS = {
    "bomb": (60, 60, 60),
    "spring": (160, 160, 40),
    "giant": (20, 20, 20),
    "airbomb": (200, 40, 40),
    "seeking": (240, 100, 0),
    "skeleton": (255, 105, 180),  # pink, so it never reads as a wall
    "tornado": (80, 200, 200),
}


def _font(size):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


# sim compass (+x = E, +y = S) -> where it points on the editor screen (tile 0,0 at the top corner)
SCREEN_DIR = {"N": "up-right", "NE": "right", "E": "down-right", "SE": "down", "S": "down-left", "SW": "left", "W": "up-left", "NW": "up"}
TRAP_NAMES = {"bomb": "Bomb", "spring": "Spring Trap", "giant": "Giant Bomb", "airbomb": "Air Bomb",
              "seeking": "Seeking Air Mine", "skeleton": "Skeleton Trap", "tornado": "Tornado Trap", "giga": "Giga Bomb"}
MODE_NOTES = ["INF single / multi = Inferno Tower mode", "XB air+gnd / gnd = X-Bow targets air and ground / ground only",
              "ST rage / invis / poison = Spell Tower spell", "SW faces up / right / down-left ... = which way the Air Sweeper points on screen",
              "HERO / King / Warden ... = hero banner, labelled with the hero that defends there", "crafting + cake / candle / hunter = Crafting Station mode (Cake-A-Pult, Hot Candle, Hero Hunter)"]


def color_of(key):
    return COLORS.get(key, (160, 130, 90) if BUILDING_TYPES[key].kind == "resource" else (130, 110, 90))


def add_legend(img, keys, trap_keys=()):
    """Return the image with a key panel below it: every abbreviation used
    (colour swatch, label, full building name), trap colours, mode notes."""
    from PIL import Image as _I

    small, bold = _font(13), _font(15)
    keys = sorted(set(keys), key=lambda k: (BUILDING_TYPES[k].kind != "townhall", BUILDING_TYPES[k].kind != "defense", LABELS.get(k, k)))
    cols, colw, rowh = 5, img.width // 5, 22
    rows_b = (len(keys) + cols - 1) // cols
    traps = [t for t in TRAP_NAMES if t in set(trap_keys)] or list(TRAP_NAMES)
    rows_t = (len(traps) + cols - 1) // cols
    h = 40 + rows_b * rowh + 30 + rows_t * rowh + 30 + ((len(MODE_NOTES) + 1) // 2) * rowh + 20
    out = _I.new("RGB", (img.width, img.height + h), (24, 40, 24))
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    y = img.height + 12
    d.text((20, y), "KEY - buildings", fill=(255, 230, 120), font=bold)
    y += 28
    for n, k in enumerate(keys):
        x = 20 + (n % cols) * colw
        yy = y + (n // cols) * rowh
        d.rectangle([x, yy + 2, x + 16, yy + 16], fill=color_of(k), outline=(0, 0, 0))
        d.text((x + 22, yy), f"{LABELS.get(k, k)} = {BUILDING_TYPES[k].name}", fill=(255, 255, 255), font=small)
    y += rows_b * rowh + 12
    d.rectangle([20 + 4 * colw, y - 26, 36 + 4 * colw, y - 12], fill=(205, 205, 215), outline=(120, 120, 130))
    d.text((42 + 4 * colw, y - 28), "Wall (light grey square)", fill=(255, 255, 255), font=small)
    d.text((20, y), "KEY - traps", fill=(255, 230, 120), font=bold)
    y += 28
    for n, k in enumerate(traps):
        x = 20 + (n % cols) * colw
        yy = y + (n // cols) * rowh
        d.rectangle([x, yy + 2, x + 16, yy + 16], fill=TRAP_COLORS.get(k, (0, 0, 0)), outline=(0, 0, 0))
        d.text((x + 22, yy), TRAP_NAMES[k], fill=(255, 255, 255), font=small)
    y += rows_t * rowh + 12
    d.text((20, y), "KEY - labels", fill=(255, 230, 120), font=bold)
    y += 28
    for n, note in enumerate(MODE_NOTES):
        d.text((20 + (n % 2) * (img.width // 2), y + (n // 2) * rowh), note, fill=(255, 255, 255), font=small)
    return out


def _iso(x, y, ox, oy):
    return (ox + (x - y) * TILE, oy + (x + y) * TILE / 2)


def render(layout: Layout, path: Path, *, show_traps: bool = True, title: str | None = None, mode_labels: bool = True):
    W = VILLAGE * TILE * 2 + 120
    H = VILLAGE * TILE + 160
    ox, oy = W / 2, 90
    img = Image.new("RGB", (W, H), (34, 70, 34))
    d = ImageDraw.Draw(img)
    small = _font(11)
    tiny = _font(9)
    big = _font(20)

    # ground diamond
    corners = [_iso(0, 0, ox, oy), _iso(VILLAGE, 0, ox, oy), _iso(VILLAGE, VILLAGE, ox, oy), _iso(0, VILLAGE, ox, oy)]
    d.polygon(corners, fill=(92, 140, 60))
    for i in range(VILLAGE + 1):
        col = (70, 110, 45) if i % 4 else (45, 80, 30)
        d.line([_iso(i, 0, ox, oy), _iso(i, VILLAGE, ox, oy)], fill=col, width=1)
        d.line([_iso(0, i, ox, oy), _iso(VILLAGE, i, ox, oy)], fill=col, width=1)
    for i in range(0, VILLAGE + 1, 4):
        x, y = _iso(i, 0, ox, oy)
        d.text((x + 4, y - 16), str(i), fill=(255, 255, 255), font=small)
        x, y = _iso(0, i, ox, oy)
        d.text((x - 18, y - 16), str(i), fill=(255, 255, 255), font=small)
    d.text((W / 2 + 40, oy - 40), "x →", fill=(255, 255, 255), font=small)
    d.text((W / 2 - 70, oy - 40), "← y", fill=(255, 255, 255), font=small)

    # walls
    for wx, wy in layout.walls:
        poly = [_iso(wx, wy, ox, oy), _iso(wx + 1, wy, ox, oy), _iso(wx + 1, wy + 1, ox, oy), _iso(wx, wy + 1, ox, oy)]
        d.polygon(poly, fill=(205, 205, 215), outline=(120, 120, 130))

    if show_traps:
        for t in layout.traps:
            s = t.size
            poly = [_iso(t.x, t.y, ox, oy), _iso(t.x + s, t.y, ox, oy), _iso(t.x + s, t.y + s, ox, oy), _iso(t.x, t.y + s, ox, oy)]
            d.polygon(poly, fill=TRAP_COLORS.get(t.key, (0, 0, 0)), outline=(0, 0, 0))

    # defending heroes pair with the banners in building-list order (as in battle.py)
    hero_short = {"Barbarian King": "King", "Archer Queen": "Queen", "Grand Warden": "Warden", "Royal Champion": "Champ",
                  "Minion Prince": "Prince", "Dragon Duke": "Duke"}
    banner_hero = {id(bn): hero_short.get(h, h) for h, bn in zip(layout.heroes, [x for x in layout.buildings if x.key == "banner"])}
    for b in sorted(layout.buildings, key=lambda p: p.x + p.y):
        s = b.size
        col = COLORS.get(b.key, (160, 130, 90) if BUILDING_TYPES[b.key].kind == "resource" else (130, 110, 90))
        poly = [_iso(b.x, b.y, ox, oy), _iso(b.x + s, b.y, ox, oy), _iso(b.x + s, b.y + s, ox, oy), _iso(b.x, b.y + s, ox, oy)]
        d.polygon(poly, fill=col, outline=(20, 20, 20))
        cx, cy = _iso(b.x + s / 2, b.y + s / 2, ox, oy)
        label = LABELS.get(b.key, b.key)
        if mode_labels and b.mode and b.key in ("inferno", "xbow", "st", "sweeper", "crafting"):
            if b.key == "sweeper":
                label += "\nfaces " + SCREEN_DIR.get(b.mode, b.mode)
            else:
                label += "\n" + {"multi": "multi", "single": "single", "both": "air+gnd", "ground": "gnd"}.get(b.mode, b.mode)
        if id(b) in banner_hero:
            label = banner_hero[id(b)]
        d.multiline_text((cx, cy), label, fill=(0, 0, 0), font=tiny if s <= 2 else small, anchor="mm", align="center")

    if title:
        d.text((20, 15), title, fill=(255, 255, 255), font=big)
    img = add_legend(img, [b.key for b in layout.buildings], [t.key for t in layout.traps])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def render_frames(layout: Layout, battle, frames_at: list[float], path: Path, *, cols: int = 3, scale: float = 0.45):
    """Contact sheet of battle snapshots (requires Battle(record=True))."""
    from .mechanics import MARGIN

    base_path = Path(path).with_suffix(".base.png")
    render(layout, base_path, show_traps=False, mode_labels=False)
    base = Image.open(base_path)
    W, H = base.size
    ox, oy = W / 2, 90
    sheets = []
    by_t = {f["t"]: f for f in battle.frames}
    font = _font(28)
    for t in frames_at:
        key = min(by_t, key=lambda k: abs(k - t))
        f = by_t[key]
        img = base.copy()
        d = ImageDraw.Draw(img)
        dead = set(f["dead"])
        for b in battle.buildings:
            if b.id in dead:
                s = b.size
                x0, y0 = b.x - s / 2 - MARGIN, b.y - s / 2 - MARGIN
                poly = [_iso(x0, y0, ox, oy), _iso(x0 + s, y0, ox, oy), _iso(x0 + s, y0 + s, ox, oy), _iso(x0, y0 + s, ox, oy)]
                d.polygon(poly, fill=(60, 60, 60), outline=(0, 0, 0))
        for wx, wy in f["walls"]:
            x0, y0 = wx - MARGIN, wy - MARGIN
            poly = [_iso(x0, y0, ox, oy), _iso(x0 + 1, y0, ox, oy), _iso(x0 + 1, y0 + 1, ox, oy), _iso(x0, y0 + 1, ox, oy)]
            d.polygon(poly, fill=(92, 140, 60))
        for name, x, y, hp, team in f["u"]:
            px, py = _iso(x - MARGIN, y - MARGIN, ox, oy)
            r = 6
            col = (255, 40, 40) if team == "atk" else (40, 120, 255)
            if name == "Totem":
                col = (255, 255, 0)
            d.ellipse([px - r, py - r, px + r, py + r], fill=col, outline=(0, 0, 0))
        d.text((30, H - 60), f"t = {key:.0f}s", fill=(255, 255, 255), font=font)
        sheets.append(img.resize((int(W * scale), int(H * scale))))
    rows = (len(sheets) + cols - 1) // cols
    sw, sh = sheets[0].size
    out = Image.new("RGB", (sw * cols, sh * rows), (0, 0, 0))
    for i, sheet in enumerate(sheets):
        out.paste(sheet, ((i % cols) * sw, (i // cols) * sh))
    out.save(path)
    base_path.unlink(missing_ok=True)
    return path
