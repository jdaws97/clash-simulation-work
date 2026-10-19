"""Fill interior drop pockets: legal drop tiles that can't be reached from
the edge of the map, so an attacker can drop troops inside the base.

Only non-defense buildings move (camps, storages, collectors, huts, army
buildings). Greedy: each step makes the single move that removes the most
pocket tiles without opening new corridors next to key defenses. Stops when
no pocket is left or no move helps.

Usage: python tools/baselab/fill_pockets.py BASE.json --out FILLED.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.layout import Layout  # noqa: E402
from baselab.mechanics import MARGIN, VILLAGE, WORLD  # noqa: E402
from baselab.optimize import FILLERS, _fits, _occupied  # noqa: E402

MOVABLE = FILLERS | {"bh"}
KEY = {"th", "eagle", "inferno", "scatter", "xbow", "mono", "mat", "ric", "crafting"}
EXPOSE_R = 4  # an edge-reachable drop tile this close to a key defense counts as exposure


def drop_map(lay: Layout):
    """(pocket mask, edge-reachable legal mask) in world coordinates."""
    occ = np.zeros((WORLD, WORLD), bool)
    for b in lay.buildings:
        if b.key == "tesla":  # hidden, does not block drops
            continue
        for x, y in b.tiles():
            occ[x + MARGIN, y + MARGIN] = True
    for x, y in lay.walls:
        occ[x + MARGIN, y + MARGIN] = True
    blocked = ndimage.binary_dilation(occ, structure=np.ones((3, 3), bool))
    legal = ~blocked
    lab, _ = ndimage.label(legal)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    outside = np.isin(lab, list(edge))
    return legal & ~outside, outside


def key_zone(lay: Layout):
    z = np.zeros((WORLD, WORLD), bool)
    for b in lay.buildings:
        if b.key in KEY:
            cx, cy = int(b.x + b.size / 2) + MARGIN, int(b.y + b.size / 2) + MARGIN
            z[max(0, cx - EXPOSE_R - 1):cx + EXPOSE_R + 1, max(0, cy - EXPOSE_R - 1):cy + EXPOSE_R + 1] = True
    return z


def cost(lay, zone):
    pockets, outside = drop_map(lay)
    return int(pockets.sum()), int((outside & zone).sum())


def fill(lay: Layout, log=print, max_moves=30):
    lay = lay.copy()
    zone = key_zone(lay)
    p, e = cost(lay, zone)
    log(f"start: {p} pocket tiles, {e} edge drop tiles near key defenses")
    moves = []
    for _ in range(max_moves):
        if p == 0:
            break
        pockets, _ = drop_map(lay)
        targets = [(int(x) - MARGIN, int(y) - MARGIN) for x, y in zip(*np.nonzero(pockets))]
        best = None
        for i, b in enumerate(lay.buildings):
            if b.key not in MOVABLE:
                continue
            occ = _occupied(lay, skip_building=i)
            s, old = b.size, (b.x, b.y)
            tried = set()
            for tx, ty in targets:
                for dx in range(-s, 2):
                    for dy in range(-s, 2):
                        pos = (tx + dx, ty + dy)
                        if pos in tried or not _fits(occ, pos[0], pos[1], s):
                            continue
                        tried.add(pos)
                        b.x, b.y = pos
                        np_, ne = cost(lay, zone)
                        b.x, b.y = old
                        # never trade pockets for new exposure near key defenses
                        if ne > e or np_ >= p:
                            continue
                        key = (np_, ne, abs(pos[0] - old[0]) + abs(pos[1] - old[1]))
                        if best is None or key < best[0]:
                            best = (key, i, pos)
        if best is None:
            break
        (np_, ne, _), i, pos = best
        b = lay.buildings[i]
        moves.append((b.key, (b.x, b.y), pos))
        log(f"  move {b.key} {b.x},{b.y} -> {pos[0]},{pos[1]}: pockets {p} -> {np_}, exposure {e} -> {ne}")
        b.x, b.y = pos
        p, e = np_, ne
    return lay, moves, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    lay = Layout.load(Path(args.base))
    filled, moves, left = fill(lay)
    issues = filled.problems(require_full=False)
    if issues:
        sys.exit(f"illegal result: {issues[:5]}")
    filled.name = (lay.name or "base") + "-filled"
    filled.save(Path(args.out))
    print(f"{len(moves)} moves, {left} pocket tiles left -> {args.out}")


if __name__ == "__main__":
    main()
