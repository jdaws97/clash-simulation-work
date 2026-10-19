"""Learned score predictor (surrogate) for layouts.

A layout becomes ~40 numbers that plausibly drive defense: damage coverage
of the buildings attackers must destroy (ground and air, overall and on the
weakest of 8 sides, since attackers scout and pick a side), wall layers
between the outside and the Town Hall / key defenses, compartment sizes,
geometry, traps and modes. A ridge regression (numpy only) maps them to the
simulated score. It is cheap (milliseconds per layout), so the search can
propose many moves, rank them with the surrogate and simulate only the
promising few.

Trained from BASELAB_EVAL_LOG files (output/evals/*.jsonl).
"""

from __future__ import annotations

import heapq
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

from .deploy import inside_holes, outside
from .layout import Layout
from .mechanics import BUILDING_TYPES, VILLAGE, weapon_spec

KEY_DEFS = ("inferno", "eagle", "scatter", "mono", "xbow", "ad", "mat", "ric")
GROUND_TRAPS = {"spring", "giant", "bomb", "giga", "tornado"}


@lru_cache(maxsize=None)
def _spec(key):
    try:
        w = weapon_spec(key, 16)
    except (KeyError, ValueError, TypeError):
        return None
    dps = w.damage / max(w.interval, 1e-3) * max(1, w.n_targets)
    return w.targets, w.range, w.min_range, dps, w.extra.get("both_range")


_YY, _XX = np.mgrid[0:VILLAGE, 0:VILLAGE]


def _coverage(lay):
    G = np.zeros((VILLAGE, VILLAGE))
    A = np.zeros((VILLAGE, VILLAGE))
    for b in lay.buildings:
        s = _spec(b.key)
        if s is None:
            continue
        targets, rng_, mn, dps, both_range = s
        cx, cy = b.x + b.size / 2, b.y + b.size / 2
        d = np.hypot(_XX + 0.5 - cx, _YY + 0.5 - cy)
        if b.key == "xbow" and b.mode == "both" and both_range:
            m = (d <= both_range).astype(float)
            G += dps * m
            A += dps * m
            continue
        m = ((d <= rng_ + b.size / 2) & (d >= mn)).astype(float)
        if targets in ("ground", "both"):
            G += dps * m
        if targets in ("air", "both"):
            A += dps * m
    return G.T, A.T  # index [x, y]


def _wall_layers(lay):
    """0-1 BFS: walls crossed to reach each tile from the map edge. Moves
    are 8-way: troops walk between two diagonally touching walls (wiki:
    Walls), so a corner-only joint is an opening."""
    walls = set(lay.walls)
    INF = 10**9
    dist = np.full((VILLAGE, VILLAGE), INF, dtype=np.int32)
    h = []
    for i in range(VILLAGE):
        for t in ((i, 0), (i, VILLAGE - 1), (0, i), (VILLAGE - 1, i)):
            c = 1 if t in walls else 0
            if c < dist[t]:
                dist[t] = c
                h.append((c, t))
    heapq.heapify(h)
    while h:
        d, (x, y) = heapq.heappop(h)
        if d > dist[x, y]:
            continue
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1), (x + 1, y + 1), (x + 1, y - 1), (x - 1, y + 1), (x - 1, y - 1)):
            if 0 <= n[0] < VILLAGE and 0 <= n[1] < VILLAGE:
                nd = d + (1 if n in walls else 0)
                if nd < dist[n]:
                    dist[n] = nd
                    heapq.heappush(h, (nd, n))
    return dist


FEATURES: list[str] = []


def features(lay: Layout) -> np.ndarray:
    G, A = _coverage(lay)
    L = _wall_layers(lay)
    th = next(b for b in lay.buildings if b.key == "th")
    tx, ty = th.x + 2, th.y + 2
    tgt = [b for b in lay.buildings if BUILDING_TYPES[b.key].counted and b.key != "banner"]
    cx = np.array([int(b.x + b.size / 2) for b in tgt])
    cy = np.array([int(b.y + b.size / 2) for b in tgt])
    g, a, lay_l = G[cx, cy], A[cx, cy], L[cx, cy]
    f = {}
    for name, v in (("g", g), ("a", a)):
        f[f"{name}_mean"] = v.mean()
        f[f"{name}_min"] = v.min()
        f[f"{name}_p10"] = np.percentile(v, 10)
        f[f"{name}_p25"] = np.percentile(v, 25)
    f["g_th"], f["a_th"] = G[int(tx), int(ty)], A[int(tx), int(ty)]
    # sides: attackers pick the weakest of 8 approach sectors
    ang = np.arctan2(cy + 0.5 - 22, cx + 0.5 - 22)
    sec = ((ang + math.pi) / (2 * math.pi) * 8).astype(int) % 8
    for name, v in (("g", g), ("a", a)):
        means = [v[sec == k].mean() if (sec == k).any() else 0.0 for k in range(8)]
        f[f"{name}_side_min"] = min(means)
        f[f"{name}_side_spread"] = max(means) - min(means)
    f["layers_th"] = L[int(tx), int(ty)]
    keyd = [b for b in tgt if b.key in KEY_DEFS]
    f["layers_key"] = np.mean([L[int(b.x + b.size / 2), int(b.y + b.size / 2)] for b in keyd]) if keyd else 0
    f["layers_mean"] = lay_l.mean()
    f["frac_outside"] = float((lay_l == 0).mean())
    f["th_center_dist"] = math.hypot(tx - 22, ty - 22)
    f["key_th_dist"] = np.mean([math.hypot(b.x + b.size / 2 - tx, b.y + b.size / 2 - ty) for b in keyd]) if keyd else 0
    d_all = [b for b in tgt if _spec(b.key)]
    f["def_spread"] = np.std([b.x for b in d_all]) + np.std([b.y for b in d_all])
    # compartments
    out = outside(lay)
    inner = VILLAGE * VILLAGE - len(out) - len(lay.walls)
    f["inner_area"] = inner
    f["walls"] = len(lay.walls)
    f["holes"] = sum(len(h) for h in inside_holes(lay))
    # traps: share of ground traps behind at least one wall, distance to TH
    gt = [t for t in lay.traps if t.key in GROUND_TRAPS]
    f["traps_inside"] = np.mean([L[t.x, t.y] >= 1 for t in gt]) if gt else 0
    f["traps_th_dist"] = np.mean([math.hypot(t.x - tx, t.y - ty) for t in lay.traps]) if lay.traps else 0
    f["traps_near_cov"] = np.mean([G[t.x, t.y] for t in gt]) if gt else 0
    # modes
    f["inferno_single"] = sum(b.key == "inferno" and b.mode == "single" for b in lay.buildings)
    f["xbow_both"] = sum(b.key == "xbow" and b.mode == "both" for b in lay.buildings)
    for m in ("rage", "invis", "poison"):
        f[f"st_{m}"] = sum(b.key == "st" and b.mode == m for b in lay.buildings)
    for m in ("cake", "candle", "hunter"):
        f[f"craft_{m}"] = sum(b.key == "crafting" and b.mode == m for b in lay.buildings)
    if not FEATURES:
        FEATURES.extend(f.keys())
    return np.array([float(f[k]) for k in FEATURES])


def load_rows(paths, mode="ranked"):
    X, y, names = [], [], []
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            lay = Layout.from_json(row["layout"])
            s = row["summary"]
            X.append(features(lay))
            y.append(s[0] - 0.02 * s[3] if mode == "ranked" else 100 * (1 - s[1]) - 10 * s[2] - 0.05 * s[3])
            names.append(lay.name)
    return np.array(X), np.array(y), names


class Ridge:
    def __init__(self, alpha=1.0):
        self.alpha = alpha

    def fit(self, X, y):
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = (X - self.mu) / self.sd
        self.ym = y.mean()
        n = Z.shape[1]
        self.w = np.linalg.solve(Z.T @ Z + self.alpha * np.eye(n), Z.T @ (y - self.ym))
        return self

    def predict(self, X):
        return ((np.atleast_2d(X) - self.mu) / self.sd) @ self.w + self.ym

    def to_json(self):
        return {"alpha": self.alpha, "mu": self.mu.tolist(), "sd": self.sd.tolist(), "w": self.w.tolist(), "ym": self.ym, "features": FEATURES}

    @classmethod
    def from_json(cls, d):
        m = cls(d["alpha"])
        m.mu, m.sd, m.w, m.ym = np.array(d["mu"]), np.array(d["sd"]), np.array(d["w"]), d["ym"]
        return m
