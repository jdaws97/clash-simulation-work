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


# ---------------------------------------------------------------------------
# Richer geometry (tools/baselab/predictor_proof.py measures what it buys):
# the base features plus approach rays to the Town Hall, core strength,
# compartments, trap placement and the Clan Castle troops. Measured
# 2026-10-21: slightly better whole-base ranking than features(), but no
# skill on one-mutation deltas, so not a pre-screen for local search.

CC_TYPES = ("Dragon", "Ice Golem", "Furnace", "Headhunter", "Archer", "Rocket Balloon", "Lava Hound")
AIR_TRAPS = {"airbomb", "seeking"}
RICH: list[str] = []


def _rays(lay, G, A, tx, ty, n=16):
    """Straight approaches from the map edge to the Town Hall: damage a
    troop walking each one is exposed to (DPS x tiles), walls and buildings
    it meets. Attackers scout and take a weak side, so the low end counts."""
    walls = lay.walls
    owner = {}
    for i, b in enumerate(lay.buildings):
        for t in b.tiles():
            owner[t] = i
    out = []
    for k in range(n):
        th = 2 * math.pi * k / n
        dx, dy = math.cos(th), math.sin(th)
        g = a = 0.0
        hit_w, hit_b = set(), set()
        for s in np.arange(0.0, 30.0, 0.5):
            x, y = tx + dx * s, ty + dy * s
            if not (0 <= x < VILLAGE and 0 <= y < VILLAGE):
                break
            t = (int(x), int(y))
            g += 0.5 * G[t]
            a += 0.5 * A[t]
            if t in walls:
                hit_w.add(t)
            if t in owner:
                hit_b.add(owner[t])
        out.append((g, a, len(hit_w), len(hit_b)))
    return np.array(out)


def _comps(lay, out):
    """Wall-enclosed regions (4-way connected non-wall tiles not reachable
    from the edge)."""
    free = {(x, y) for x in range(VILLAGE) for y in range(VILLAGE)} - out - set(lay.walls)
    comps, cid = [], {}
    while free:
        s = free.pop()
        comp, stack = {s}, [s]
        while stack:
            x, y = stack.pop()
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in free:
                    free.discard(n)
                    comp.add(n)
                    stack.append(n)
        for t in comp:
            cid[t] = len(comps)
        comps.append(comp)
    return comps, cid


def rich_features(lay: Layout) -> np.ndarray:
    base = features(lay)
    G, A = _coverage(lay)
    th = next(b for b in lay.buildings if b.key == "th")
    tx, ty = th.x + 2, th.y + 2
    f = {}
    R = _rays(lay, G, A, tx, ty)
    for j, name in enumerate(("ray_g", "ray_a", "ray_walls", "ray_blds")):
        v = np.sort(R[:, j])
        f[f"{name}_min"], f[f"{name}_p25"], f[f"{name}_mean"] = v[0], v[len(v) // 4], v.mean()
    defs = [(b, _spec(b.key)) for b in lay.buildings if _spec(b.key)]
    for rad in (7, 12):
        near = [(b, s) for b, s in defs if math.hypot(b.x + b.size / 2 - tx, b.y + b.size / 2 - ty) <= rad]
        f[f"core_g{rad}"] = sum(s[3] for b, s in near if s[0] in ("ground", "both"))
        f[f"core_a{rad}"] = sum(s[3] for b, s in near if s[0] in ("air", "both"))
        f[f"core_key{rad}"] = sum(b.key in KEY_DEFS for b, _ in near)
    keyd = [b for b in lay.buildings if b.key in KEY_DEFS]
    f["g_key"] = np.mean([G[int(b.x + b.size / 2), int(b.y + b.size / 2)] for b in keyd]) if keyd else 0
    f["a_key"] = np.mean([A[int(b.x + b.size / 2), int(b.y + b.size / 2)] for b in keyd]) if keyd else 0
    # damage centre vs Town Hall, and the weakest of 8 sectors around the TH
    w = np.array([s[3] for _, s in defs])
    px = np.array([b.x + b.size / 2 for b, _ in defs])
    py = np.array([b.y + b.size / 2 for b, _ in defs])
    f["dps_centroid_off"] = math.hypot((w * px).sum() / w.sum() - tx, (w * py).sum() / w.sum() - ty)
    sec = (((np.arctan2(py - ty, px - tx) + math.pi) / (2 * math.pi) * 8).astype(int)) % 8
    share = np.array([w[sec == k].sum() for k in range(8)]) / w.sum()
    f["sector_min_share"], f["sector_max_share"] = share.min(), share.max()
    f["bld_th_dist"] = np.mean([math.hypot(b.x + b.size / 2 - tx, b.y + b.size / 2 - ty) for b in lay.buildings])
    # compartments
    out = outside(lay)
    comps, cid = _comps(lay, out)
    sizes = sorted((len(c) for c in comps), reverse=True) or [0]
    f["n_comps"], f["max_comp"] = len(comps), sizes[0]
    f["th_comp"] = len(comps[cid[(tx, ty)]]) if (tx, ty) in cid else 0
    kc = [cid.get((int(b.x + b.size / 2), int(b.y + b.size / 2))) for b in keyd]
    f["key_in_th_comp"] = sum(c is not None and c == cid.get((tx, ty)) for c in kc)
    f["key_max_per_comp"] = max([kc.count(c) for c in set(kc) if c is not None] or [0])
    holes = inside_holes(lay)
    f["max_hole"] = max((len(h) for h in holes), default=0)
    # traps
    tr = lay.traps
    f["traps_near_th"] = sum(math.hypot(t.x - tx, t.y - ty) <= 6 for t in tr)
    at_ = [t for t in tr if t.key in AIR_TRAPS or (t.key == "skeleton" and t.mode == "air")]
    f["air_traps_cov"] = np.mean([A[t.x, t.y] for t in at_]) if at_ else 0
    f["air_traps_th_dist"] = np.mean([math.hypot(t.x - tx, t.y - ty) for t in at_]) if at_ else 0
    f["skeleton_air"] = sum(t.key == "skeleton" and t.mode == "air" for t in tr)
    gb = [t for t in tr if t.key in ("giant", "giga")]
    f["giant_cov"] = np.mean([G[t.x, t.y] for t in gb]) if gb else 0
    # defending heroes stand near their banners; CC troops
    ban = [b for b in lay.buildings if b.key == "banner"]
    f["banner_th_dist"] = np.mean([math.hypot(b.x + 1 - tx, b.y + 1 - ty) for b in ban]) if ban else 0
    for c in CC_TYPES:
        f["cc_" + c.lower().replace(" ", "_")] = sum(x == c for x in lay.cc_troops)
    if not RICH:
        RICH.extend(FEATURES + list(f.keys()))
    return np.concatenate([base, [float(f[k]) for k in RICH[len(FEATURES):]]])


class GBM:
    """Small gradient-boosted regression trees (numpy only; no sklearn in
    the venv): squared loss, quantile-binned splits, row subsampling."""

    def __init__(self, n_trees=300, depth=3, lr=0.05, bins=32, subsample=0.8, min_leaf=8, seed=0):
        self.n_trees, self.depth, self.lr, self.bins = n_trees, depth, lr, bins
        self.subsample, self.min_leaf, self.seed = subsample, min_leaf, seed

    def _bin(self, X):
        return np.stack([np.searchsorted(self.edges[j], X[:, j], side="right") for j in range(X.shape[1])], 1)

    def fit(self, X, y):
        X = np.asarray(X, float)
        y = np.asarray(y, float)
        self.edges = [np.unique(np.quantile(X[:, j], np.linspace(0, 1, self.bins + 1)[1:-1])) for j in range(X.shape[1])]
        B = self._bin(X)
        rng = np.random.default_rng(self.seed)
        self.y0 = float(np.mean(y))
        pred = np.full(len(y), self.y0)
        self.trees = []
        for _ in range(self.n_trees):
            r = y - pred
            tree = self._grow(B, r, np.where(rng.random(len(y)) < self.subsample)[0], 0)
            self.trees.append(tree)
            pred += self.lr * self._apply(tree, B)
        return self

    def _grow(self, B, r, idx, d):
        if d == self.depth or len(idx) < 2 * self.min_leaf:
            return float(r[idx].mean()) if len(idx) else 0.0
        best = None
        tot, n, nb = r[idx].sum(), len(idx), self.bins + 1
        for j in range(B.shape[1]):
            b = B[idx, j]
            cs = np.cumsum(np.bincount(b, weights=r[idx], minlength=nb))[:-1]
            cn = np.cumsum(np.bincount(b, minlength=nb))[:-1]
            ok = (cn >= self.min_leaf) & (n - cn >= self.min_leaf)
            if not ok.any():
                continue
            gain = np.where(ok, cs ** 2 / np.maximum(cn, 1) + (tot - cs) ** 2 / np.maximum(n - cn, 1), -np.inf)
            k = int(np.argmax(gain))
            if best is None or gain[k] > best[0]:
                best = (gain[k], j, k)
        if best is None:
            return float(r[idx].mean())
        _, j, k = best
        left = B[idx, j] <= k
        return (j, k, self._grow(B, r, idx[left], d + 1), self._grow(B, r, idx[~left], d + 1))

    def _apply(self, tree, B):
        if not isinstance(tree, tuple):
            return np.full(len(B), tree)
        j, k, lt, rt = tree
        m = B[:, j] <= k
        out = np.empty(len(B))
        out[m] = self._apply(lt, B[m])
        out[~m] = self._apply(rt, B[~m])
        return out

    def predict(self, X):
        B = self._bin(np.atleast_2d(np.asarray(X, float)))
        return self.y0 + self.lr * sum(self._apply(t, B) for t in self.trees)
