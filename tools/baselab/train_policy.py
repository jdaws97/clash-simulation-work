"""Train the attacker policy (when to Freeze, Invisibility, Rage, fire and
aim hero abilities, distract, lure the CC, Earthquake the core, commit the
push) across a library of very different bases with the cross-entropy
method, an evolution-strategies relative of policy-gradient RL.

Each round samples `pop` policies around the current mean, plays every one
on the same random draw of (base, army, attacker TH, side, skill seed)
battles, keeps the best quarter and moves the mean toward them. At the end
the best policy and the hand-written default are compared on held-out
battles (new sides and seeds). Nothing is adopted automatically: --adopt
writes data/attacker-policy.json.

Usage:
  python tools/baselab/train_policy.py --iters 15 --pop 24 --battles 96 [--army throwers] [--adopt]
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.archetypes import design  # noqa: E402
from baselab.evaluate import pool  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.policy import ACTIVE, DEFAULT, HI, LO, NAMES, run_job, to_dict  # noqa: E402

ARMIES = ("hydra", "throwers", "edrag", "rootrider")


def library():
    """Real human bases, optimized bases and freeform originals: very
    different layouts, so the policy learns general play."""
    files = sorted(glob.glob(str(ROOT / "data" / "reference-bases" / "*.json")))
    files += [f for f in sorted(glob.glob(str(ROOT / "output" / "bases*" / "*winner.json")))]
    files += [str(ROOT / "output" / "web-bases" / "web-a.json")]
    lays = []
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    for f in files:
        if Path(f).exists():
            lays.append(Layout.load(f))
    for kind, seed in (("organic", 101), ("organic", 102), ("free", 103), ("grid", 104), ("rings", 105), ("wide", 106)):
        try:
            lays.append(design(kind, seed))
        except RuntimeError:
            pass
    for lay in lays:
        if lay.town_hall == 16:
            lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
    return lays


def draw(rng, lays, armies, n):
    return [(rng.integers(len(lays)), armies[rng.integers(len(armies))], int(rng.choice([16, 17, 18])),
             float(rng.uniform(0, 2 * math.pi)), int(rng.integers(0, 10**6))) for _ in range(n)]


def play(lays_json, battles, pols):
    jobs = [(lays_json[b], a, th, ang, s, p) for p in pols for (b, a, th, ang, s) in battles]
    res = list(pool().map(run_job, jobs, chunksize=2))
    n = len(battles)
    return [res[i * n:(i + 1) * n] for i in range(len(pols))]


def fit(rows):
    return float(np.mean([s + p / 100.0 for s, p in rows]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=15)
    ap.add_argument("--pop", type=int, default=24)
    ap.add_argument("--battles", type=int, default=96, help="battles per policy per round")
    ap.add_argument("--holdout", type=int, default=400)
    ap.add_argument("--army", choices=ARMIES)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--adopt", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "output" / "policy"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    lays = library()
    lj = [l.to_json() for l in lays]
    armies = (args.army,) if args.army else ARMIES
    print(f"library: {len(lays)} bases; armies {armies}; {len(NAMES)} policy values", flush=True)
    mu, sd = DEFAULT.copy(), (HI - LO) / 4
    best, best_f = DEFAULT.copy(), -1.0
    t0 = time.time()
    hist = []
    for it in range(args.iters):
        battles = draw(rng, lays, armies, args.battles)
        V = np.clip(mu + sd * rng.standard_normal((args.pop, len(NAMES))), LO, HI)
        V[0] = mu  # the current mean is always re-measured
        rows = play(lj, battles, [to_dict(v) for v in V])
        F = np.array([fit(r) for r in rows])
        order = np.argsort(-F)
        E = V[order[: max(2, args.pop // 4)]]
        mu = 0.7 * E.mean(0) + 0.3 * mu  # smoothed update: the draws are noisy
        sd = np.maximum(0.8 * E.std(0) + 0.2 * sd, (HI - LO) * 0.03)
        if F[order[0]] > best_f:
            best_f, best = float(F[order[0]]), V[order[0]].copy()
        hist.append({"iter": it, "best": float(F[order[0]]), "mean_policy": float(F[0]), "elite": float(F[order[:len(E)]].mean())})
        print(f"iter {it:2d}: best {F[order[0]]:.3f}  current mean policy {F[0]:.3f}  elite {F[order[:len(E)]].mean():.3f}  t={time.time() - t0:.0f}s", flush=True)
    # held out: the final mean (less noisy than the single best draw) vs default
    battles = draw(np.random.default_rng(args.seed + 999), lays, armies, args.holdout)
    rows = play(lj, battles, [to_dict(DEFAULT), to_dict(mu), to_dict(best)])
    names = ("default", "learned-mean", "learned-best")
    res = {}
    for n, r in zip(names, rows):
        three = sum(s >= 3 for s, _ in r) / len(r)
        res[n] = {"fitness": fit(r), "three_star": three, "avg_stars": float(np.mean([s for s, _ in r])), "avg_pct": float(np.mean([p for _, p in r]))}
        print(f"hold-out {n:13s} fitness {res[n]['fitness']:.3f}  3* {three:5.1%}  avg {res[n]['avg_stars']:.2f}*  {res[n]['avg_pct']:.1f}%", flush=True)
    # paired comparison: how often the learned policy beats default on the same battle
    d = np.array([(s1 + p1 / 100) - (s0 + p0 / 100) for (s0, p0), (s1, p1) in zip(rows[0], rows[1])])
    se = d.std() / math.sqrt(len(d))
    print(f"learned-mean minus default: {d.mean():+.3f} +- {se:.3f} (paired, {len(d)} battles)", flush=True)
    changed = {k: (round(float(DEFAULT[i]), 2), round(float(mu[i]), 2)) for i, k in enumerate(NAMES) if abs(mu[i] - DEFAULT[i]) > 0.1 * (HI[i] - LO[i])}
    print("changed vs default:", changed, flush=True)
    rec = {"army": args.army or "*", "policy": to_dict(mu), "best": to_dict(best), "holdout": res, "paired_gain": float(d.mean()),
           "paired_se": float(se), "history": hist}
    (out / f"policy-{args.army or 'all'}.json").write_text(json.dumps(rec, indent=1))
    if args.adopt and d.mean() > 2 * se:
        cur = json.loads(ACTIVE.read_text()) if ACTIVE.exists() else {}
        cur[args.army or "*"] = to_dict(mu)
        ACTIVE.write_text(json.dumps(cur, indent=1))
        print(f"adopted into {ACTIVE}", flush=True)


if __name__ == "__main__":
    main()
