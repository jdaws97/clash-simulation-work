"""Can a learned predictor pre-screen layouts for the search?

gen: simulate a small labelled set with the current engine (68 ranked meta
     battles per layout, the search's own scenario set): a few parents, each
     with one-mutation variants (paired deltas on identical battles), plus
     standalone layouts from every generator and the real bases. Every
     layout gets the user's own levels, so only the layout varies.
fit: train predictors (surrogate.py) and measure them on held-out origins:
     rank correlation with the simulated score, sign accuracy of predicted
     vs simulated paired deltas, and top-20% recall when screening.
     Old-engine logs (main checkout output/, Oct 15-16) serve as extra
     training data and a second test; their labels predate the engine fixes.

Result 2026-10-21 (engine 89b3606, 51 fresh layouts, 3124 old rows): NOT
good enough. One-mutation deltas: sign accuracy 36-61% (chance 50%), corr
-0.35..+0.28, top-20% recall 10-21% on old data (random 20%). The
simulator's own 68-battle deltas are barely reproducible (two halves of the
builds agree on the sign 50% of the time, reliability ~0.38; 2 of 36 pairs
beyond 2 SE). Whole-base ranking carries weak signal (rho 0.52 old,
0.34 fresh over 15 bases).

Usage:
  python tools/baselab/predictor_proof.py gen [--out output/predictor/fresh.jsonl]
  python tools/baselab/predictor_proof.py fit
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.archetypes import design  # noqa: E402
from baselab.evaluate import STRENGTH, meta_scenarios, run_batch, summarise  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.optimize import mutate  # noqa: E402
from baselab.unconventional import unconventional  # noqa: E402
from proof_scorer import own, scrambled  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402
import numpy as np  # noqa: E402

MAIN = Path("C:/Users/jarod/Documents/clash-lab")  # untracked data lives in the main checkout


def _ref(name):
    return own(Layout.load(ROOT / "data" / "reference-bases" / name))


def _seed(name):
    return own(Layout.load(ROOT / "data" / "builder-bases" / name))


def plan():
    """(group, layout) parents that get variants, then standalone layouts."""
    parents = [
        ("your-base", lambda: _ref("your-base.json")),
        ("your-base-scrambled", lambda: scrambled(_ref("your-base.json"))),
        ("real-l3x", lambda: _ref("real-l3x.json")),
        ("blueprint-seed", lambda: _seed("blueprint-ranked-2026-06-seed.json")),
        ("design-organic", lambda: own(design("organic", 4101))),
        ("unconv-onion", lambda: own(unconventional("onion", 4102))),
    ]
    # most varied first: the time budget may stop the list early
    alone = [
        ("design-free", lambda: own(design("free", 4201))),
        ("unconv-cram", lambda: own(unconventional("cram", 4207))),
        ("real-l1x", lambda: _ref("real-l1x.json")),
        ("design-wide", lambda: own(design("wide", 4204))),
        ("loay-seed", lambda: _seed("loay-samy-cc92583-seed.json")),
        ("unconv-scatter", lambda: own(unconventional("scatter", 4208))),
        ("design-grid", lambda: own(design("grid", 4202))),
        ("real-l5x", lambda: _ref("real-l5x.json")),
        ("design-rings", lambda: own(design("rings", 4205))),
        ("reyferro-101332-seed", lambda: _seed("reyferro-cc101332-seed.json")),
        ("design-offset", lambda: own(design("offset", 4203))),
        ("real-l6x", lambda: _ref("real-l6x.json")),
        ("design-organic-2", lambda: own(design("organic", 4206))),
        ("reyferro-96154-seed", lambda: _seed("reyferro-cc96154-seed.json")),
    ]
    return parents, alone


def variants(lay, n, seed):
    """n distinct legal one-mutation variants (no-ops skipped)."""
    rng = random.Random(seed)
    out, seen = [], set()
    base_problems = len(lay.problems(require_full=False))
    while len(out) < n:
        v, desc = mutate(lay, rng)
        if desc == "noop" or len(v.problems(require_full=False)) > base_problems:
            continue
        key = json.dumps(v.to_json(), sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        out.append((v, desc))
    return out


def simulate(lays, scenarios):
    jobs = []
    for lay in lays:
        lj = lay.to_json()
        jobs += [(lj, sc, STRENGTH.get(sc.army, 1.0)) for sc in scenarios]
    res = run_batch(jobs)
    k = len(scenarios)
    return [res[i * k:(i + 1) * k] for i in range(len(lays))]


def gen(args):
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        done = {json.loads(l)["group"] for l in out.read_text(encoding="utf-8").splitlines()}
    sc = meta_scenarios("ranked", 4, (0,))
    parents, alone = plan()
    work = [(g, f, args.variants) for g, f in parents] + [(g, f, 0) for g, f in alone]
    t0 = time.time()
    for group, make, nv in work:
        if group in done:
            continue
        p = make()
        lays = [(p, None)] + variants(p, nv, zlib.crc32(group.encode()))
        res = simulate([l for l, _ in lays], sc)
        with out.open("a", encoding="utf-8") as f:
            for (lay, desc), r in zip(lays, res):
                ev = summarise(sc, r)
                row = {
                    "group": group, "move": desc, "layout": lay.to_json(),
                    "summary": [ev.ranked_trophies, ev.three_star_rate, ev.avg_stars, ev.avg_destruction, ev.th_kill_rate],
                    "battles": [[s.army, s.town_hall, round(s.angle, 3), s.seed, s.weight, s.modifier, x[0], x[1], x[2]]
                                for s, x in zip(sc, r)],
                }
                f.write(json.dumps(row, separators=(",", ":")) + "\n")
        print(f"{group:24s} {len(lays)} layouts, parent {summarise(sc, res[0]).ranked_trophies:5.2f}  t={time.time() - t0:.0f}s",
              flush=True)


# ---------------------------------------------------------------- data

def tokens(lay):
    """Placement tokens; the size of the symmetric difference between two
    layouts' tokens counts the edits between them (a swap is 4)."""
    t = {("b", b.key, b.x, b.y, b.mode) for b in lay.buildings}
    t |= {("w",) + w for w in lay.walls}
    t |= {("t", x.key, x.x, x.y, x.mode) for x in lay.traps}
    t.add(("cc",) + tuple(sorted(lay.cc_troops)))
    return frozenset(t)


def lineages(toks, thr=0.5):
    """Union layouts whose building placements overlap (Jaccard >= thr):
    one lineage = one origin and everything derived from it."""
    parent = list(range(len(toks)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    bl = [{t for t in s if t[0] == "b"} for s in toks]
    index: dict = {}
    for i, s in enumerate(bl):
        for t in s:
            index.setdefault(t, []).append(i)
    for i, s in enumerate(bl):
        shared: dict = {}
        for t in s:
            for j in index[t]:
                if j < i:
                    shared[j] = shared.get(j, 0) + 1
        for j, c in shared.items():
            if c / (len(s) + len(bl[j]) - c) >= thr:
                parent[find(i)] = find(j)
    return [find(i) for i in range(len(toks))]


def load_old(cache):
    """Old-engine labels (before 2026-10-21's engine changes; Oct 15-16 logs):
    the funnel's 1299 quick-labelled bases (2 sides per build) and the
    eval logs of the evolution runs (ranked only)."""
    from baselab.surrogate import rich_features

    if cache.exists():
        d = np.load(cache, allow_pickle=True)
        return {k: d[k] for k in d.files}
    X, y, src, sig, toks = [], [], [], [], []
    for line in (MAIN / "output/funnel/data.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        lay = Layout.from_json(r["layout"])
        X.append(rich_features(lay)), y.append(r["ranked"]), src.append("funnel:" + r["origin"]), sig.append("funnel")
        toks.append(tokens(lay))
    for p in sorted((MAIN / "output/evals").glob("*.jsonl")):
        if "war" in p.name:
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            lay = Layout.from_json(r["layout"])
            X.append(rich_features(lay)), y.append(r["summary"][0]), src.append(p.stem)
            sig.append(p.stem + ":" + str(zlib.crc32(json.dumps([b[:4] for b in r["battles"]]).encode())))
            toks.append(tokens(lay))
        print(f"  features: {p.name} done ({len(y)} rows)", flush=True)
    lin = lineages(toks)
    out = {"X": np.array(X), "y": np.array(y), "src": np.array(src), "sig": np.array(sig), "lineage": np.array(lin),
           "toks": np.array([sorted(map(str, t)) for t in toks], dtype=object)}
    np.savez(cache, **out)
    return out


def load_fresh(path):
    from baselab.surrogate import rich_features

    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines()]
    for r in rows:
        r["lay"] = Layout.from_json(r["layout"])
        r["x"] = rich_features(r["lay"])
    return rows


def build_scores(battles):
    """Per attacking build (army, TH, modifier, seed group): weight and
    scouted expected defender trophies, from a logged battle list. The
    overall score is the weighted mean, so per-build differences give a
    paired delta with a standard error, and a split-half reliability."""
    from baselab.evaluate import Scenario, defender_trophies, scouted

    n_ang: dict = {}
    for b in battles:
        n_ang.setdefault((b[0], b[1], b[5]), set()).add(b[2])
    sc, res = [], []
    for b in battles:
        n = len(n_ang[(b[0], b[1], b[5])])
        sc.append(Scenario(b[0], b[1], b[2], b[3], b[4], b[5], group=(b[3] // 5) // n))
        res.append((b[6], b[7], b[8], 0.0))
    out: dict = {}
    for s, r, w in scouted(sc, res):
        k = (s.army, s.town_hall, s.modifier, s.group)
        a = out.setdefault(k, [0.0, 0.0])
        a[0] += w
        a[1] += w * defender_trophies(r[0], r[1])
    return {k: (w, t / w) for k, (w, t) in out.items()}


def paired(bs0, bs1):
    """Paired delta (1 - 0), its standard error over builds, and the deltas
    of two fixed halves of the builds (for split-half reliability)."""
    keys = sorted(bs0, key=str)
    w = np.array([bs0[k][0] for k in keys])
    w = w / w.sum()
    d = np.array([bs1[k][1] - bs0[k][1] for k in keys])
    m = float((w * d).sum())
    se = float(np.sqrt((w ** 2 * (d - m) ** 2).sum() * len(d) / max(1, len(d) - 1)))
    half = np.array([zlib.crc32(str(k).encode()) % 2 for k in keys]) == 0
    h = [float((w[s] * d[s]).sum() / w[s].sum()) if s.any() else float("nan") for s in (half, ~half)]
    return m, se, h


def pairs_old(d, max_edit=10):
    """Close pairs evaluated on identical battles: (i, j, edit size)."""
    toks = [set(t) for t in d["toks"]]
    by_sig: dict = {}
    for i, s in enumerate(d["sig"]):
        if s != "funnel":
            by_sig.setdefault(s, []).append(i)
    out = []
    for idx in by_sig.values():
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                i, j = idx[a], idx[b]
                if d["lineage"][i] != d["lineage"][j]:
                    continue
                e = len(toks[i] ^ toks[j])
                if 0 < e <= max_edit:
                    out.append((i, j, e))
    return out


# --------------------------------------------------------------- models

def ridge(alpha=10.0, rich=True):
    from baselab.surrogate import FEATURES, Ridge

    class M:
        def fit(self, X, y):
            self.k = X.shape[1] if rich else len(FEATURES)
            self.m = Ridge(alpha).fit(X[:, :self.k], y)
            return self

        def predict(self, X):
            return self.m.predict(np.atleast_2d(X)[:, :self.k])
    return M()


def gbm(**kw):
    from baselab.surrogate import GBM
    return GBM(**kw)


MODELS = {
    "ridge-base": lambda: ridge(10, rich=False),
    "ridge-rich": lambda: ridge(30, rich=True),
    "gbm-rich": lambda: gbm(n_trees=300, depth=3, lr=0.05),
}


def spearman(a, b):
    return float(spearmanr(a, b).correlation)


def group_folds(groups, k=5, seed=0):
    u = np.unique(groups)
    rng = np.random.default_rng(seed)
    rng.shuffle(u)
    return [np.isin(groups, u[i::k]) for i in range(k)]


def fit(args):
    out = ROOT / "output" / "predictor"
    out.mkdir(parents=True, exist_ok=True)
    from baselab.surrogate import rich_features
    rich_features(_ref("your-base.json"))  # fills the feature name lists
    d = load_old(out / "old.npz")
    X, y = d["X"], d["y"]
    print(f"old-engine rows {len(y)}; lineages {len(np.unique(d['lineage']))}")
    fun = d["sig"] == "funnel"
    groups = np.array([s.split(":")[1] for s in d["src"][fun]])
    print("\n[old] absolute: funnel set (1299 bases, 2 sides per build), leave-origin-family-out (5 folds)")
    Xf, yf = X[fun], y[fun]
    for name, make in MODELS.items():
        pred = np.zeros(len(yf))
        for te in group_folds(groups):
            pred[te] = make().fit(Xf[~te], yf[~te]).predict(Xf[te])
        print(f"  {name:11s} rho {spearman(pred, yf):.3f}")
    old_deltas(d)
    fresh(d, out)


def centred(d):
    """Old targets centred per scenario set (sets differ in difficulty)."""
    yc = d["y"].copy()
    for s in np.unique(d["sig"]):
        yc[d["sig"] == s] -= d["y"][d["sig"] == s].mean()
    return yc


def top_recall(pred, true, frac=0.2):
    """Is the truly best candidate among the predicted top `frac`?"""
    k = max(1, int(round(frac * len(pred))))
    return int(np.argmax(true) in np.argsort(-pred)[:k])


def mc_recall(c, n=100, frac=0.2, trials=20000, seed=0):
    """Chance that the best of n proposals survives a screen keeping the
    top frac, when predicted and true deltas correlate c (bivariate normal)."""
    rng = np.random.default_rng(seed)
    t = rng.standard_normal((trials, n))
    p = c * t + np.sqrt(max(0.0, 1 - c * c)) * rng.standard_normal((trials, n))
    k = int(round(frac * n))
    cut = -np.sort(-p, 1)[:, k - 1]
    return float(np.mean(p[np.arange(trials), np.argmax(t, 1)] >= cut))


def old_deltas(d):
    """Old-engine close pairs on identical battles (logged scores; the
    per-build battles of these logs cannot be re-scored: the scouting and
    seed conventions changed since). Models never see the pair's lineage."""
    X, y, yc, lin = d["X"], d["y"], centred(d), d["lineage"]
    P = pairs_old(d)
    pi = np.array([p[0] for p in P])
    pj = np.array([p[1] for p in P])
    dy = y[pj] - y[pi]
    big = np.abs(dy) >= np.quantile(np.abs(dy), 0.75)
    print(f"\n[old] paired deltas (identical battles, <=10 edits): {len(P)} pairs in {len(np.unique(lin[pi]))} lineages; "
          f"mean |delta| {np.abs(dy).mean():.2f}")
    folds = group_folds(lin[pi])
    dX = X[pj] - X[pi]
    models = dict(MODELS)
    models["ridge-delta"] = None  # fitted on (dX, dy) of the training lineages' pairs
    preds = {}
    for name, make in models.items():
        dp = np.zeros(len(P))
        for te in folds:
            if make is None:
                m = ridge(30).fit(dX[~te], dy[~te])
                dp[te] = m.predict(dX[te]) - m.predict(np.zeros_like(dX[te]))
                continue
            held = np.isin(lin, np.unique(lin[pi[te]]))
            m = make().fit(X[~held], yc[~held])
            dp[te] = m.predict(X[pj[te]]) - m.predict(X[pi[te]])
        preds[name] = dp
        nz = dp != 0
        acc = np.mean(np.sign(dp[nz]) == np.sign(dy[nz]))
        accb = np.mean(np.sign(dp[nz & big]) == np.sign(dy[nz & big]))
        print(f"  {name:11s} sign acc {acc:.3f} (n={nz.sum()}), largest-quartile deltas {accb:.3f} (n={(nz & big).sum()}); "
              f"corr {np.corrcoef(dp, dy)[0, 1]:+.3f}")
    # screening: anchors with >= 10 close neighbours on the same battles
    nb: dict = {}
    for k, (i, j, _e) in enumerate(P):
        nb.setdefault(i, []).append((j, k, +1))
        nb.setdefault(j, []).append((i, k, -1))
    anchors = [a for a, v in nb.items() if len(v) >= 10]
    print(f"  screening: {len(anchors)} layouts with >= 10 close variants; best variant kept in predicted top 20%:")
    for name, dp in preds.items():
        rec = [top_recall(np.array([s * dp[k] for _j, k, s in nb[a]]), np.array([y[j] for j, _k, _s in nb[a]]))
               for a in anchors]
        print(f"    {name:11s} {np.mean(rec):.0%} (random 20%)")


def fresh(d, out):
    path = out / "fresh.jsonl"
    if not path.exists():
        print("\nno fresh set yet (run gen)")
        return
    rows = load_fresh(path)
    Xn = np.array([r["x"] for r in rows])
    yn = np.array([r["summary"][0] for r in rows])
    grp = np.array([r["group"] for r in rows])
    par = np.array([r["move"] is None for r in rows])
    bs = [build_scores(r["battles"]) for r in rows]
    recon = np.array([sum(w * t for w, t in b.values()) / sum(w for w, _t in b.values()) for b in bs])
    print(f"\n[fresh] current engine: {len(rows)} layouts, {par.sum()} independent bases, 68 battles each; "
          f"score {yn.min():.1f}..{yn.max():.1f} (sd {yn[par].std():.2f}); per-build re-scoring check max err {np.abs(recon - yn).max():.1e}")
    pidx = {g: i for i, g in enumerate(grp) if par[i]}
    P = [(pidx[grp[i]], i) for i in range(len(rows)) if not par[i]]
    st = [paired(bs[i], bs[j]) for i, j in P]
    dy = np.array([s[0] for s in st])
    se = np.array([s[1] for s in st])
    h = np.array([s[2] for s in st])
    clear = np.abs(dy) > 2 * se
    r_half = float(np.corrcoef(h[:, 0], h[:, 1])[0, 1])
    r_full = 2 * r_half / (1 + r_half)
    print(f"  {len(P)} one-mutation pairs: mean |delta| {np.abs(dy).mean():.2f}, mean paired SE {se.mean():.2f}, "
          f"clear (|d| > 2 SE) {clear.sum()}")
    print(f"  simulator vs itself: two halves of the builds agree on the delta sign {np.mean(np.sign(h[:, 0]) == np.sign(h[:, 1])):.0%}, "
          f"split-half r {r_half:+.2f} -> full-set reliability {r_full:+.2f}")
    yc = centred(d)
    ind = np.where(par)[0]
    table = {}
    for name, make in MODELS.items():
        m = make().fit(d["X"], yc)
        pn = m.predict(Xn)
        table[name] = pn
        dp = np.array([pn[j] - pn[i] for i, j in P])
        nz = dp != 0
        acc = np.mean(np.sign(dp[nz]) == np.sign(dy[nz]))
        accc = np.mean(np.sign(dp[nz & clear]) == np.sign(dy[nz & clear])) if (nz & clear).any() else float("nan")
        fam = [top_recall(np.array([pn[i]] + [pn[j] for i2, j in P if i2 == i]), np.array([yn[i]] + [yn[j] for i2, j in P if i2 == i]), 2 / 7)
               for i in sorted(set(i for i, _ in P))]
        print(f"  trained on old -> {name:11s}: rho over {len(ind)} bases {spearman(pn[ind], yn[ind]):+.2f}; delta sign acc "
              f"{acc:.0%} (n={nz.sum()}), clear {accc:.0%} (n={(nz & clear).sum()}), corr {np.corrcoef(dp, dy)[0, 1]:+.2f}; "
              f"sim-best of 7 in predicted top 2: {sum(fam)}/{len(fam)}")
    print("  independent bases (sim score; predictions of the old-trained models, centred):")
    for i in ind[np.argsort(-yn[ind])]:
        print(f"    {grp[i]:22s} sim {yn[i]:5.2f}   " + "  ".join(f"{n} {table[n][i]:+5.2f}" for n in table))
    # fresh only / old + fresh, leave one origin out
    for label, use_old in (("fresh only", False), ("old + fresh", True)):
        for name in ("ridge-base", "ridge-rich", "gbm-rich"):
            pn = np.zeros(len(rows))
            for g in np.unique(grp):
                te = grp == g
                Xt, yt = Xn[~te], yn[~te] - yn[~te].mean()
                if use_old:
                    Xt, yt = np.vstack([d["X"], Xt]), np.concatenate([yc, yt])
                elif name == "gbm-rich":
                    continue
                pn[te] = MODELS[name]().fit(Xt, yt).predict(Xn[te])
            if not pn.any():
                continue
            dp = np.array([pn[j] - pn[i] for i, j in P])
            nz = dp != 0
            print(f"  {label:11s} leave-origin-out {name:11s}: rho over {len(ind)} bases {spearman(pn[ind], yn[ind]):+.2f}; "
                  f"delta sign acc {np.mean(np.sign(dp[nz]) == np.sign(dy[nz])):.0%}, corr {np.corrcoef(dp, dy)[0, 1]:+.2f}")
    print("\n  screening 100 one-mutation proposals, keep the predicted top 20: chance the best survives, "
          "by correlation c between predicted and true delta")
    print("   " + "  ".join(f"c={c:.1f}: {mc_recall(c):.0%}" for c in (0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9)))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen")
    g.add_argument("--out", default=str(ROOT / "output" / "predictor" / "fresh.jsonl"))
    g.add_argument("--variants", type=int, default=6)
    sub.add_parser("fit")
    args = ap.parse_args()
    if args.cmd == "gen":
        gen(args)
    else:
        fit(args)


if __name__ == "__main__":
    main()
