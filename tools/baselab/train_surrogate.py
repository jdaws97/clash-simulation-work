"""Train the layout score predictor on logged evaluations and report how
well it ranks layouts it has not seen (5-fold rank correlation).

Usage: python tools/baselab/train_surrogate.py [--mode ranked] [logs...]
Default logs: output/evals/*.jsonl and *.jsonl.gz
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.surrogate import FEATURES, Ridge, load_rows  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="*")
    ap.add_argument("--mode", default="ranked")
    ap.add_argument("--out", default=str(ROOT / "output" / "surrogate.json"))
    args = ap.parse_args()
    logs = args.logs or sorted(str(p) for p in (ROOT / "output" / "evals").glob("*.jsonl*"))
    paths = []
    tmp = Path(tempfile.mkdtemp())
    for p in logs:
        if p.endswith(".gz"):
            q = tmp / Path(p).stem
            q.write_bytes(gzip.decompress(Path(p).read_bytes()))
            paths.append(q)
        else:
            paths.append(Path(p))
    X, y, names = load_rows(paths, args.mode)
    # identical layouts evaluated twice: keep one row (mean target)
    keyed: dict = {}
    for x, t in zip(X, y):
        keyed.setdefault(x.tobytes(), [x, []])[1].append(t)
    X = np.array([v[0] for v in keyed.values()])
    y = np.array([np.mean(v[1]) for v in keyed.values()])
    print(f"{len(y)} distinct layouts from {len(paths)} logs; target mean {y.mean():.2f} sd {y.std():.2f}")
    rng = np.random.default_rng(0)
    idx = rng.permutation(len(y))
    best = None
    for alpha in (0.3, 1, 3, 10, 30, 100):
        preds = np.zeros(len(y))
        for k in range(5):
            te = idx[k::5]
            tr = np.setdiff1d(idx, te)
            preds[te] = Ridge(alpha).fit(X[tr], y[tr]).predict(X[te])
        rho = spearmanr(preds, y).correlation
        print(f"  alpha {alpha:6.1f}: held-out rank correlation {rho:.3f}")
        if best is None or rho > best[0]:
            best = (rho, alpha)
    m = Ridge(best[1]).fit(X, y)
    top = sorted(zip(FEATURES, m.w), key=lambda t: -abs(t[1]))[:10]
    print("strongest features:", ", ".join(f"{n} {w:+.2f}" for n, w in top))
    Path(args.out).write_text(json.dumps(m.to_json() | {"rho": best[0], "n": len(y)}))
    print(f"saved {args.out} (rho {best[0]:.3f}, alpha {best[1]})")


if __name__ == "__main__":
    main()
