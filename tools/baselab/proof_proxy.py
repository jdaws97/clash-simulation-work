"""Does a fast screening setting rank bases like the full simulator?

`run` scores a fixed set of ~20 varied bases on the same battles and saves
per-battle defender trophies plus the wall time. Run it once with the normal
engine and once with the fast setting (e.g. BASELAB_DT=0.2), then `compare`:
speed ratio, rank agreement of base scores (Spearman), and agreement on the
DIFFERENCES between a base and one-change variants (what a search decides).

Usage: python tools/baselab/proof_proxy.py run --out output/proxy-full.json
       BASELAB_DT=0.2 python tools/baselab/proof_proxy.py run --out output/proxy-dt02.json
       python tools/baselab/proof_proxy.py compare output/proxy-full.json output/proxy-dt02.json
"""

from __future__ import annotations

import argparse
import glob
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

import numpy as np  # noqa: E402


def bases():
    from baselab.archetypes import design
    from baselab.layout import Layout
    from baselab.optimize import mutate
    from baselab.unconventional import unconventional
    from proof_scorer import no_traps, own, scrambled

    out = {}
    for f in sorted(glob.glob(str(ROOT / "data/reference-bases/*.json"))):
        if f.endswith("-2026-10-21.json"):
            continue
        out[Path(f).stem] = own(Layout.load(f))
    for f in sorted(glob.glob(str(ROOT / "data/builder-bases/*-seed.json"))):
        out["builder " + Path(f).stem.replace("-seed", "")] = own(Layout.load(f))
    for i, k in enumerate(["organic", "free", "wide"]):
        out[f"generated {k}"] = own(design(k, 7000 + i))
    out["open cram"] = own(unconventional("cram", 7100))
    yb = out["your-base"]
    out["your-base scrambled"] = scrambled(yb)
    out["your-base no traps"] = no_traps(yb)
    rng = random.Random(11)
    n = 0
    while n < 3:
        m, d = mutate(yb, rng)
        if d != "noop" and not m.problems():
            n += 1
            out[f"your-base variant {n} ({d})"] = m
    return out


def cmd_run(out_path):
    import os

    from baselab.evaluate import STRENGTH, defender_trophies, meta_scenarios, run_batch

    bs = bases()
    sc = meta_scenarios("ranked", 4, (0, 1))
    jobs = []
    for lay in bs.values():
        lj = lay.to_json()
        jobs += [(lj, s, STRENGTH.get(s.army, 1.0)) for s in sc]
    t0 = time.time()
    res = run_batch(jobs)
    wall = time.time() - t0
    k = len(sc)
    per = {n: [float(defender_trophies(int(r[0]), r[1])) for r in res[i * k:(i + 1) * k]] for i, n in enumerate(bs)}
    Path(out_path).write_text(json.dumps({"dt": os.environ.get("BASELAB_DT", "0.1"), "wall_s": wall,
                                          "battles": len(jobs), "weights": [s.weight for s in sc], "per": per}))
    print(f"{len(jobs)} battles in {wall:.0f}s ({wall / len(jobs) * 1000:.0f} ms each, pooled); saved {out_path}")


def cmd_compare(a_path, b_path):
    from scipy.stats import spearmanr

    A, B = json.loads(Path(a_path).read_text()), json.loads(Path(b_path).read_text())
    w = np.array(A["weights"]); w = w / w.sum()
    names = list(A["per"])
    ma = {n: float((w * np.array(A["per"][n])).sum()) for n in names}
    mb = {n: float((w * np.array(B["per"][n])).sum()) for n in names}
    print(f"speed: full {A['wall_s'] / A['battles'] * 1000:.0f} ms/battle, fast {B['wall_s'] / B['battles'] * 1000:.0f} ms/battle "
          f"-> {A['wall_s'] / B['wall_s']:.2f}x")
    print(f"{'base':48s} {'full':>6s} {'fast':>6s}")
    for n in sorted(names, key=lambda n: -ma[n]):
        print(f"{n[:48]:48s} {ma[n]:6.2f} {mb[n]:6.2f}")
    rho = spearmanr([ma[n] for n in names], [mb[n] for n in names]).correlation
    print(f"\nrank agreement (Spearman) over {len(names)} bases: {rho:.2f}")
    base = "your-base"
    print("differences from your-base (what a search decides):")
    agree = 0
    pairs = [n for n in names if n.startswith("your-base ") ]
    for n in pairs:
        da, db = ma[n] - ma[base], mb[n] - mb[base]
        agree += np.sign(da) == np.sign(db)
        print(f"  {n[:44]:44s} full {da:+6.2f}  fast {db:+6.2f}")
    print(f"same direction in {agree}/{len(pairs)}")
    ok = rho >= 0.9 and A["wall_s"] / B["wall_s"] >= 1.5
    print("VERDICT:", "fast setting usable for screening" if ok else "not good enough")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    args = ap.parse_args()
    if args.cmd == "run":
        cmd_run(args.out)
    else:
        cmd_compare(args.a, args.b)


if __name__ == "__main__":
    main()
