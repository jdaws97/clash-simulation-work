"""Step-by-step guide for building a layout in the in-game layout editor.

Full build (an original base):
  0. In the editor: "Remove all" so everything sits in the tray.
  1. walls: the wall plan split into straight runs, each numbered on the
     image with its length and direction.
  2-4. buildings in stages (core defenses, other defenses, everything else);
     each image shows that stage bright and numbered, earlier stages faded.
  5. traps.
  6. defensive Clan Castle troops, banner assignments and all modes.
Change list (--from an existing layout, e.g. a remix of the user's base):
  copy the existing layout in the editor, then only the differences:
  buildings to remove, move or add (numbered), walls to remove (red),
  walls to add (green), traps to move or switch, and defensive setup.

Images use the editor's camera angle: tile (0,0) at the top corner, +x
toward the bottom-right edge, +y toward the bottom-left edge, every 4th grid
line numbered.

Usage:
  python tools/baselab/build_guide.py LAYOUT.json --out output/guides/NAME [--from OLD.json]
"""

from __future__ import annotations

import argparse
import html
import sys
from collections import Counter
from itertools import zip_longest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.layout import Layout  # noqa: E402
from baselab.mechanics import BUILDING_TYPES, VILLAGE  # noqa: E402
from baselab.optimize import cc_entries  # noqa: E402
from baselab.render import (
    COLORS,
    LABELS,
    TILE,
    TRAP_COLORS,
    _font,
    _iso,
    add_legend,
)  # noqa: E402

CORE = {
    "th",
    "inferno",
    "eagle",
    "scatter",
    "mono",
    "cc",
    "crafting",
    "xbow",
    "st",
    "banner",
}
DIRS = {(1, 0): "toward the bottom-right", (0, 1): "toward the bottom-left"}
NAMES = {k: BUILDING_TYPES[k].name for k in BUILDING_TYPES}


def wall_runs(walls):
    """Greedy split of the wall set into straight runs, longest first."""
    left = set(walls)
    runs = []
    while left:
        best = None
        for x, y in sorted(left):
            for dx, dy in ((1, 0), (0, 1)):
                if (x - dx, y - dy) in left:
                    continue
                n = 1
                while (x + dx * n, y + dy * n) in left:
                    n += 1
                if best is None or n > best[0]:
                    best = (n, x, y, dx, dy)
        n, x, y, dx, dy = best
        runs.append((x, y, dx, dy, n))
        for k in range(n):
            left.discard((x + dx * k, y + dy * k))
    return runs


class Canvas:
    def __init__(self, title):
        self.W, self.H = VILLAGE * TILE * 2 + 120, VILLAGE * TILE + 170
        self.ox, self.oy = self.W / 2, 95
        self.img = Image.new("RGB", (self.W, self.H), (34, 70, 34))
        self.d = ImageDraw.Draw(self.img)
        self.small, self.tiny, self.big, self.num = (
            _font(11),
            _font(9),
            _font(20),
            _font(13),
        )
        d, ox, oy = self.d, self.ox, self.oy
        d.polygon(
            [
                _iso(0, 0, ox, oy),
                _iso(VILLAGE, 0, ox, oy),
                _iso(VILLAGE, VILLAGE, ox, oy),
                _iso(0, VILLAGE, ox, oy),
            ],
            fill=(92, 140, 60),
        )
        for i in range(VILLAGE + 1):
            col = (70, 110, 45) if i % 4 else (45, 80, 30)
            d.line([_iso(i, 0, ox, oy), _iso(i, VILLAGE, ox, oy)], fill=col)
            d.line([_iso(0, i, ox, oy), _iso(VILLAGE, i, ox, oy)], fill=col)
        for i in range(0, VILLAGE + 1, 4):
            x, y = _iso(i, 0, ox, oy)
            d.text((x + 4, y - 16), str(i), fill=(255, 255, 255), font=self.small)
            x, y = _iso(0, i, ox, oy)
            d.text((x - 18, y - 16), str(i), fill=(255, 255, 255), font=self.small)
        d.text((20, 15), title, fill=(255, 255, 255), font=self.big)

    def tile(self, x, y, s, fill, outline=(20, 20, 20)):
        o = (self.ox, self.oy)
        self.d.polygon(
            [
                _iso(x, y, *o),
                _iso(x + s, y, *o),
                _iso(x + s, y + s, *o),
                _iso(x, y + s, *o),
            ],
            fill=fill,
            outline=outline,
        )

    def label(self, x, y, s, text, color=(0, 0, 0)):
        cx, cy = _iso(x + s / 2, y + s / 2, self.ox, self.oy)
        self.d.multiline_text(
            (cx, cy),
            text,
            fill=color,
            font=self.tiny if s <= 2 else self.small,
            anchor="mm",
            align="center",
        )

    def badge(self, x, y, s, n, fill=(255, 230, 0)):
        cx, cy = _iso(x + s / 2, y, self.ox, self.oy)
        self.d.ellipse(
            [cx - 10, cy - 2, cx + 10, cy + 18], fill=fill, outline=(0, 0, 0)
        )
        self.d.text((cx, cy + 8), str(n), fill=(0, 0, 0), font=self.num, anchor="mm")

    def save(self, path, keys=(), trap_keys=()):
        add_legend(self.img, keys, trap_keys).save(path)


def faded(col):
    return tuple(int(c * 0.35 + 92 * 0.65) for c in col)


def bcolor(b):
    return COLORS.get(
        b.key,
        (160, 130, 90) if BUILDING_TYPES[b.key].kind == "resource" else (130, 110, 90),
    )


def mode_text(b):
    if b.key in ("sweeper", "firespitter"):
        from baselab.render import SCREEN_DIR

        return "faces " + SCREEN_DIR.get(b.mode or "E", b.mode or "E") + " on screen"
    # src/baselab/engine/defense.py: attach() defaults also apply to missing modes.
    defaults = {
        "inferno": "single",
        "xbow": "ground",
        "st": "rage",
        "crafting": "none",
        "mgt": "fast",
        "cannon": "normal",
        "at": "normal",
        "mortar": "normal",
    }
    mode = b.mode or defaults.get(b.key, "")
    if b.key in ("cannon", "at", "mortar") and mode in ("geared", "fast", "burst"):
        return {"cannon": "double cannon", "at": "fast attack", "mortar": "burst fire"}[
            b.key
        ] + " (geared)"
    return {
        "both": "air+ground",
        "ground": "ground only",
        "eq": "earthquake",
        "invis": "invisibility",
        "cake": "Cake-A-Pult",
        "candle": "Hot Candle",
        "hunter": "Hero Hunter",
        "none": "no crafted defense",
    }.get(mode, mode)


def trap_mode(t):
    # src/baselab/engine/traps.py:99: an unspecified Skeleton Trap is ground.
    return t.mode or ("ground" if t.key == "skeleton" else "")


def defensive_setup(lay, out: Path, number):
    """A complete target checklist, also when only non-spatial setup changed."""
    from baselab.engine import stats

    c = Canvas(f"Step {number}: defensive setup (numbers identify hero banners)")
    for x, y in sorted(lay.walls):
        c.tile(x, y, 1, faded((205, 205, 215)), None)
    for b in lay.buildings:
        c.tile(b.x, b.y, b.size, faded(bcolor(b)), (70, 90, 60))
    rows = []
    # engine/units.py: cargo_entries expands structured counts and keeps levels.
    counts = Counter(cc_entries(lay.cc_troops))
    troops = ", ".join(
        f"{count} x {name}" + (f" (level {level})" if level is not None else "")
        for (name, level), count in counts.items()
    )
    housing = sum(
        count
        * int(
            stats.attrs(name).get("housing_ck") or stats.attrs(name).get("housing") or 0
        )
        for (name, _level), count in counts.items()
    )
    rows.append(
        f"Defensive Clan Castle troops: {troops or 'empty'} ({housing} housing)."
    )
    # src/baselab/engine/battle.py:298-300: pair heroes and banners in list order.
    banners = [b for b in lay.buildings if b.key == "banner"]
    for i, b in enumerate(banners):
        hero = lay.heroes[i] if i < len(lay.heroes) else "leave unassigned"
        c.badge(b.x, b.y, b.size, i + 1)
        rows.append(f"Hero Banner {i + 1} at ({b.x}, {b.y}): {hero}.")
    for b in lay.buildings:
        mode = mode_text(b)
        if mode:
            rows.append(f"{NAMES[b.key]} at ({b.x}, {b.y}): {mode}.")
            if b.key in ("cannon", "at", "mortar") and b.mode in (
                "geared",
                "fast",
                "burst",
            ):
                rows.append(
                    f"Use the owned geared-up {NAMES[b.key]} at ({b.x}, {b.y}); "
                    "swap copies of the same building if needed."
                )
    for t in lay.traps:
        mode = trap_mode(t)
        if mode:
            rows.append(f"{t.key} trap at ({t.x}, {t.y}): {mode}.")
    if lay.town_hall >= 18:
        rows.append(f"Town Hall Guardian: {lay.guardian or 'none'}.")
    filename = f"{number}-setup.png"
    c.save(out / filename, [b.key for b in lay.buildings], [t.key for t in lay.traps])
    return f"Step {number}: defensive setup (apply every setting)", filename, rows


def full_guide(lay, out: Path):
    steps = []
    runs = wall_runs(lay.walls)
    c = Canvas(f"Step 1: walls ({len(lay.walls)} in {len(runs)} straight runs)")
    for x, y in lay.walls:
        c.tile(x, y, 1, (205, 205, 215), (120, 120, 130))
    rows = []
    for i, (x, y, dx, dy, n) in enumerate(runs, 1):
        c.badge(x, y, 1, i)
        rows.append(
            f"{i}. start at tile ({x}, {y}), {n} wall{'s' if n > 1 else ''} {DIRS[(dx, dy)] if n > 1 else '(single)'}"
        )
    c.save(
        out / "1-walls.png", [b.key for b in lay.buildings], [t.key for t in lay.traps]
    )
    steps.append(("Step 1: walls", "1-walls.png", rows))
    stages = [
        ("Step 2: core defenses", lambda b: b.key in CORE),
        (
            "Step 3: other defenses",
            lambda b: b.key not in CORE and BUILDING_TYPES[b.key].kind == "defense",
        ),
        (
            "Step 4: resources, army and other buildings",
            lambda b: b.key not in CORE and BUILDING_TYPES[b.key].kind != "defense",
        ),
    ]
    done: list = []
    for si, (title, pick) in enumerate(stages, 2):
        cur = sorted(
            [b for b in lay.buildings if pick(b)], key=lambda b: (b.y + b.x, b.x)
        )
        c = Canvas(title)
        for x, y in lay.walls:
            c.tile(x, y, 1, faded((205, 205, 215)), None)
        for b in done:
            c.tile(b.x, b.y, b.size, faded(bcolor(b)), (70, 90, 60))
        rows = []
        for b in cur:
            m = mode_text(b)
            c.tile(b.x, b.y, b.size, bcolor(b))
            c.label(
                b.x, b.y, b.size, LABELS.get(b.key, b.key) + ("\n" + m if m else "")
            )
        for i, b in enumerate(cur, 1):
            m = mode_text(b)
            c.badge(b.x, b.y, b.size, i)
            rows.append(
                f"{i}. {NAMES[b.key]}{' (' + m + ')' if m else ''}: top tile ({b.x}, {b.y})"
            )
        c.save(
            out / f"{si}-stage.png",
            [b.key for b in lay.buildings],
            [t.key for t in lay.traps],
        )
        steps.append((title, f"{si}-stage.png", rows))
        done += cur
    c = Canvas("Step 5: traps")
    for x, y in lay.walls:
        c.tile(x, y, 1, faded((205, 205, 215)), None)
    for b in lay.buildings:
        c.tile(b.x, b.y, b.size, faded(bcolor(b)), (70, 90, 60))
    rows = []
    for i, t in enumerate(sorted(lay.traps, key=lambda t: (t.x + t.y, t.x)), 1):
        c.tile(t.x, t.y, t.size, TRAP_COLORS.get(t.key, (0, 0, 0)))
        c.badge(t.x, t.y, t.size, i, fill=(255, 255, 255))
        mode = trap_mode(t)
        rows.append(
            f"{i}. {t.key}{' (' + mode + ')' if mode else ''}: tile ({t.x}, {t.y})"
        )
    c.save(
        out / "5-traps.png", [b.key for b in lay.buildings], [t.key for t in lay.traps]
    )
    steps.append(("Step 5: traps", "5-traps.png", rows))
    steps.append(defensive_setup(lay, out, 6))
    return steps


def building_changes(old, new):
    """Match copies by position, then pair moves; None marks a tray transfer."""
    removals, moves, additions = [], [], []
    # mechanics.py:145: optional Crafting Stations can exist on only one side.
    keys = {b.key for b in old.buildings} | {b.key for b in new.buildings}
    for key in sorted(keys):
        a = [b for b in old.buildings if b.key == key]
        bnew = [b for b in new.buildings if b.key == key]
        stay_old = {(b.x, b.y) for b in a}
        target = [b for b in bnew if (b.x, b.y) not in stay_old]
        source = [b for b in a if (b.x, b.y) not in {(q.x, q.y) for q in bnew}]
        for s, t in zip_longest(
            sorted(source, key=lambda b: (b.x, b.y)),
            sorted(target, key=lambda b: (b.x, b.y)),
        ):
            if t is None:
                removals.append((s, None))
            elif s is None:
                additions.append((None, t))
            else:
                moves.append((s, t))
        for b in bnew:  # same spot, changed mode
            o = next((q for q in a if (q.x, q.y) == (b.x, b.y)), None)
            if o is not None and (o.mode or None) != (b.mode or None):
                moves.append((o, b))
    return removals + moves + additions


def change_guide(old, new, out: Path):
    steps = []
    changes = building_changes(old, new)
    removed = sorted(set(old.walls) - set(new.walls))
    added = sorted(set(new.walls) - set(old.walls))
    c = Canvas(f"Step 1: walls - remove {len(removed)} (red), add {len(added)} (green)")
    for x, y in set(old.walls) & set(new.walls):
        c.tile(x, y, 1, faded((205, 205, 215)), None)
    for x, y in removed:
        c.tile(x, y, 1, (220, 40, 40))
    for x, y in added:
        c.tile(x, y, 1, (40, 220, 60))
    c.save(
        out / "1-walls.png", [b.key for b in new.buildings], [t.key for t in new.traps]
    )
    steps.append(
        (
            "Step 1: walls (remove first; park blocking buildings in the tray)",
            "1-walls.png",
            [f"remove wall at ({x}, {y})" for x, y in removed]
            + [f"add wall at ({x}, {y})" for x, y in added],
        )
    )
    c = Canvas(
        f"Step 2: {len(changes)} building changes (red = remove, green = add, dark = old spot)"
    )
    for x, y in new.walls:
        c.tile(x, y, 1, faded((205, 205, 215)), None)
    moved_new = {id(t) for _, t in changes if t is not None}
    for b in new.buildings:
        if id(b) not in moved_new:
            c.tile(b.x, b.y, b.size, faded(bcolor(b)), (70, 90, 60))
    rows = []
    # old spots first, then new spots, then the numbers, so chains and swaps stay readable
    for i, (s, t) in enumerate(changes, 1):
        if s is None:
            continue
        if t is None or (s.x, s.y) != (t.x, t.y):
            color = (220, 40, 40) if t is None else (60, 60, 60)
            c.tile(s.x, s.y, s.size, color, (255, 230, 0))
            label = f"remove {i}" if t is None else f"was {i}"
            c.label(s.x, s.y, s.size, label, (255, 230, 0))
    for s, t in changes:
        if t is None:
            continue
        m = mode_text(t)
        outline = (40, 220, 60) if s is None else (20, 20, 20)
        c.tile(t.x, t.y, t.size, bcolor(t), outline)
        c.label(t.x, t.y, t.size, LABELS.get(t.key, t.key) + ("\n" + m if m else ""))
    for i, (s, t) in enumerate(changes, 1):
        b = t if t is not None else s
        c.badge(b.x, b.y, b.size, i)
    for i, (s, t) in enumerate(changes, 1):
        if t is None:
            rows.append(
                f"{i}. Remove {NAMES[s.key]} at ({s.x}, {s.y}) to the editor tray."
            )
            continue
        m = mode_text(t)
        if s is None:
            rows.append(
                f"{i}. Add {NAMES[t.key]} from the editor tray: top tile ({t.x}, {t.y}){', mode ' + m if m else ''}"
            )
        elif (s.x, s.y) == (t.x, t.y):
            rows.append(f"{i}. {NAMES[t.key]} at ({t.x}, {t.y}): switch mode to {m}")
        else:
            rows.append(
                f"{i}. {NAMES[t.key]}: ({s.x}, {s.y}) -> ({t.x}, {t.y}){', mode ' + m if m else ''}"
            )
    c.save(
        out / "2-moves.png",
        [b.key for b in old.buildings] + [b.key for b in new.buildings],
        [t.key for t in new.traps],
    )
    steps.append(
        (
            "Step 2: buildings (remove to the tray, move, then add from the tray)",
            "2-moves.png",
            rows,
        )
    )
    ot = {(t.key, t.x, t.y, trap_mode(t)) for t in old.traps}
    nt = [t for t in new.traps if (t.key, t.x, t.y, trap_mode(t)) not in ot]
    c = Canvas(f"Step 3: traps - {len(nt)} positions or modes to change")
    for x, y in new.walls:
        c.tile(x, y, 1, faded((205, 205, 215)), None)
    for b in new.buildings:
        c.tile(b.x, b.y, b.size, faded(bcolor(b)), (70, 90, 60))
    rows = []
    for i, t in enumerate(nt, 1):
        c.tile(t.x, t.y, t.size, TRAP_COLORS.get(t.key, (0, 0, 0)))
        c.badge(t.x, t.y, t.size, i, fill=(255, 255, 255))
        mode = trap_mode(t)
        rows.append(
            f"{i}. {t.key}{' (' + mode + ')' if mode else ''} at ({t.x}, {t.y})"
        )
    c.save(
        out / "3-traps.png", [b.key for b in new.buildings], [t.key for t in new.traps]
    )
    steps.append(("Step 3: traps (set positions and modes)", "3-traps.png", rows))
    steps.append(defensive_setup(new, out, 4))
    return steps


def edit_cost(old, new):
    """Editor actions: building removals/moves/additions/modes, wall pieces,
    trap moves/modes and defensive setup. The second count covers buildings."""
    moves = len(building_changes(old, new))
    walls = len(set(old.walls) ^ set(new.walls))
    ot = {(t.key, t.x, t.y, trap_mode(t)) for t in old.traps}
    traps = sum(1 for t in new.traps if (t.key, t.x, t.y, trap_mode(t)) not in ot)
    # optimize.py:cc_entries preserves levels and expands structured counts.
    setup = int(
        Counter(cc_entries(old.cc_troops)) != Counter(cc_entries(new.cc_troops))
    )
    setup += sum(a != b for a, b in zip_longest(old.heroes, new.heroes))
    setup += int(new.town_hall >= 18 and old.guardian != new.guardian)
    return moves + walls + traps + setup, moves, walls, traps


def closest_start(new):
    """The user's saved layouts (and earlier winners) that need the fewest edits."""
    import glob

    cands = sorted(glob.glob(str(ROOT / "data" / "reference-bases" / "*.json")))
    cands += sorted(glob.glob(str(ROOT / "output" / "bases-deep" / "*winner.json")))
    rows = []
    for f in cands:
        old = Layout.load(f)
        rows.append((edit_cost(old, new), f))
    rows.sort()
    return rows


def write_html(steps, out: Path, title, intro):
    parts = [
        f"<!doctype html><meta charset=utf-8><title>{html.escape(title)}</title>",
        "<style>body{font-family:system-ui,sans-serif;max-width:1100px;margin:0 auto;padding:16px;background:#111;color:#eee}"
        "img{width:100%;border-radius:8px}ol,ul{columns:2;font-size:14px}h2{margin-top:32px}</style>",
        f"<h1>{html.escape(title)}</h1><p>{html.escape(intro)}</p>",
    ]
    for t, img, rows in steps:
        parts.append(
            f"<h2>{html.escape(t)}</h2><img src='{img}' alt='{html.escape(t)}'><ul>"
        )
        parts += [f"<li>{html.escape(r)}</li>" for r in rows]
        parts.append("</ul>")
    (out / "index.html").write_text("\n".join(parts), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("layout")
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--from",
        dest="src",
        help="an existing layout to start from, or 'auto' for the one needing the fewest edits",
    )
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    new = Layout.load(args.layout)
    if args.src == "auto":
        rows = closest_start(new)
        full = (
            len(new.buildings) + len(new.walls) + len(new.traps) + len(new.heroes) + 1
        )
        for (c, m, w, t), f in rows[:4]:
            print(
                f"  from {Path(f).stem:16s} {c:4d} edits ({m} buildings, {w} wall pieces, {t} traps, {c - m - w - t} setup)"
            )
        print(f"  from scratch      {full:4d} placements")
        best_cost, best_f = rows[0][0][0], rows[0][1]
        args.src = best_f if best_cost < full * 0.8 else None
    if args.src:
        old = Layout.load(args.src)
        steps = change_guide(old, new, out)
        intro = (
            f"Start from a copy of {Path(args.src).stem} in the layout editor, then make only these changes. "
            "Return removed buildings and park blocking buildings in the tray before placing walls or buildings. "
            "Tile numbers match the grid lines on the images (every 4th line is numbered). "
            "Finish by applying every defensive setup setting, including Clan Castle troops and heroes."
        )
    else:
        steps = full_guide(new, out)
        intro = (
            "In the layout editor, tap Remove all first. Then build in this order: walls, core defenses, other "
            "defenses, everything else, traps, defensive setup. Tile numbers match the grid lines on the images."
        )
    write_html(steps, out, f"Build guide: {new.name}", intro)
    n = sum(len(r) for _, _, r in steps)
    print(f"{len(steps)} steps, {n} instructions -> {out / 'index.html'}")


if __name__ == "__main__":
    main()
