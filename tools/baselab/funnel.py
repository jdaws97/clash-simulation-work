"""Multi-fidelity base search: try thousands of bases, test the promising
ones properly.

  data     Generate ~N varied bases and label each with quick simulations
           (ranked: real TH17/18 meta builds, 2 sides; war: TH16 builds,
           4 sides), for training the score predictor.
  train    Fit the predictor (surrogate.py) per mode and measure it honestly:
           rank correlation on bases from families it never saw (group split).
  screen   Stage A: generate `--candidates` bases, rank them with the
           predictor (plus a share of random explorers). Stage B: quick-sim
           the top `--quick`. Stage C: full scoring (272 battles) of the top
           `--full`. Writes the top bases as a population for evolve_bases.py.

Candidate sources (no single style is privileged): freeform organic and free
originals, the four styled plans, and variants of real and earlier-best bases
(1 to 40 random mutations each, including freeform wall rewiring) and
crossovers between all of them.

Usage:
  python tools/baselab/funnel.py data --n 1300 --out output/funnel/data.jsonl
  python tools/baselab/funnel.py train --data output/funnel/data.jsonl
  python tools/baselab/funnel.py screen --mode ranked --seed 1 --candidates 15000 --quick 500 --full 50 --out output/funnel/ranked-1
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.archetypes import TH_ZONES, design, th_zone  # noqa: E402
from baselab.evaluate import STRENGTH, meta_scenarios, pool, run_batch, summarise  # noqa: E402
from baselab.evolve import crossover  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.optimize import hole_tiles, mutate, objective  # noqa: E402
from baselab.surrogate import FEATURES, Ridge, features  # noqa: E402

KINDS = ["organic", "organic", "organic", "free", "free", "grid", "offset", "rings", "wide"]


def own_levels():
    return json.loads((ROOT / "data" / "your-levels.json").read_text())


def seed_bases():
    files = sorted(glob.glob(str(ROOT / "data" / "reference-bases" / "*.json")))
    files += [str(ROOT / "output" / "bases-deep" / f) for f in ("ranked-winner.json", "war-winner.json")]
    out = []
    for f in files:
        if Path(f).exists():
            lay = Layout.load(f)
            lay.name = "seed-" + Path(f).stem
            out.append(lay.to_json())
    return out


def _make(args):
    """One candidate: (layout_json, origin, features) or None. Runs in a worker."""
    kind, seed, seeds_json = args
    rng = random.Random(seed)
    own = own_levels()
    try:
        if kind.startswith("original"):
            zone = kind.split(":")[1] if ":" in kind else None
            lay = design(rng.choice(KINDS), seed, zone=zone)
            origin = "orig-" + lay.name.split("-")[1] + "-" + th_zone(lay)
        elif kind == "variant":
            src = rng.randrange(len(seeds_json))
            lay = Layout.from_json(seeds_json[src])
            origin = lay.name
            for _ in range(int(rng.choice([1, 2, 3, 5, 8, 12, 20, 30, 40]))):
                m, d = mutate(lay, rng)
                if d != "noop" and not m.problems():
                    lay = m
        else:  # crossover of a seed base with another seed base or an original
            a = Layout.from_json(seeds_json[rng.randrange(len(seeds_json))])
            b = Layout.from_json(seeds_json[rng.randrange(len(seeds_json))]) if rng.random() < 0.5 else design(rng.choice(KINDS), seed)
            lay = crossover(a, b, rng)
            if lay is None:
                return None
            origin = "x-" + a.name
        if lay.problems() or hole_tiles(lay) > 20:
            return None
        lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
        lay.name = f"{kind[:1]}{seed}"
        return lay.to_json(), origin, features(lay).tolist()
    except (RuntimeError, ValueError, IndexError, KeyError):
        return None


def generate(n, seed, mix=(0.4, 0.45, 0.15), originals_only=False):
    seeds_json = seed_bases()
    rng = random.Random(seed)
    jobs = []
    for i in range(n):
        if originals_only:
            kind = "original:" + TH_ZONES[i % 3]  # equal numbers per Town Hall zone
        else:
            r = rng.random()
            kind = "original" if r < mix[0] else "variant" if r < mix[0] + mix[1] else "cross"
        jobs.append((kind, seed * 1_000_000 + i, seeds_json))
    out = [r for r in pool().map(_make, jobs, chunksize=8) if r is not None]
    return out


def eval_many(lays, scenarios, mode):
    """Score many layouts in one parallel batch (keeps every core busy)."""
    jobs = []
    for lay in lays:
        lj = lay.to_json()
        jobs += [(lj, sc, STRENGTH.get(sc.army, 1.0)) for sc in scenarios]
    res = run_batch(jobs)
    k = len(scenarios)
    out = []
    for n, lay in enumerate(lays):
        ev = summarise(scenarios, res[n * k:(n + 1) * k])
        out.append((objective(ev, mode, lay), ev))
    return out


def quick_sets():
    return {"ranked": meta_scenarios("ranked", 2, (0,)), "war": meta_scenarios("war", 4, (0,))}


def cmd_data(args):
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    cands = generate(args.n, args.seed)
    print(f"generated {len(cands)} legal bases in {time.time() - t0:.0f}s", flush=True)
    sets = quick_sets()
    with open(out, "a", encoding="utf-8") as f:
        for b0 in range(0, len(cands), 40):
            chunk = cands[b0:b0 + 40]
            lays = [Layout.from_json(c[0]) for c in chunk]
            scores = {mode: eval_many(lays, sc, mode) for mode, sc in sets.items()}
            for n, (lj, origin, feat) in enumerate(chunk):
                row = {"layout": lj, "origin": origin, "features": feat}
                for mode in sets:
                    row[mode] = scores[mode][n][0]
                f.write(json.dumps(row, separators=(",", ":")) + "\n")
            f.flush()
            print(f"  {b0 + len(chunk)}/{len(cands)}  t={time.time() - t0:.0f}s", flush=True)
    print(f"done in {time.time() - t0:.0f}s", flush=True)


def load_data(path):
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    X = np.array([r["features"] for r in rows])
    groups = [r["origin"].split("-")[0] + "-" + r["origin"].split("-")[1] if r["origin"].startswith(("orig", "x")) else r["origin"] for r in rows]
    return rows, X, groups


def cmd_train(args):
    from scipy.stats import spearmanr

    rows, X, groups = load_data(args.data)
    report = {}
    for mode in ("ranked", "war"):
        y = np.array([r[mode] for r in rows])
        ug = sorted(set(groups))
        best = None
        for alpha in (1, 3, 10, 30, 100, 300):
            preds = np.zeros(len(y))
            for g in ug:  # leave one family out: honest generalisation
                te = np.array([gg == g for gg in groups])
                if te.all():
                    continue
                preds[te] = Ridge(alpha).fit(X[~te], y[~te]).predict(X[te])
            rho = spearmanr(preds, y).correlation
            if best is None or rho > best[0]:
                best = (rho, alpha, preds)
        rho, alpha, preds = best
        # how much of the true top 5% the predicted top 10% would keep
        k5, k10 = max(1, len(y) // 20), max(1, len(y) // 10)
        true_top = set(np.argsort(-y)[:k5])
        kept = len(true_top & set(np.argsort(-preds)[:k10])) / len(true_top)
        model = Ridge(alpha).fit(X, y)
        Path(args.out_dir).mkdir(parents=True, exist_ok=True)
        (Path(args.out_dir) / f"surrogate-{mode}.json").write_text(json.dumps(model.to_json() | {"rho": rho, "top_kept": kept, "n": len(y)}))
        report[mode] = {"rho_leave_family_out": rho, "alpha": alpha, "top5_kept_by_top10": kept, "n": len(y), "families": len(ug)}
        print(f"{mode}: {len(y)} bases, {len(ug)} families; leave-one-family-out rank correlation {rho:.3f} (alpha {alpha}); "
              f"the predicted top 10% keeps {kept:.0%} of the true top 5%", flush=True)
    (Path(args.out_dir) / "surrogate-report.json").write_text(json.dumps(report, indent=1))


def cmd_screen(args):
    mode = args.mode
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "screen.log", "a", encoding="utf-8")

    def say(m):
        print(m, flush=True)
        log.write(m + "\n")
        log.flush()

    t0 = time.time()
    model = Ridge.from_json(json.loads((Path(args.model_dir) / f"surrogate-{mode}.json").read_text()))
    cands = []
    batch = 2000
    for b0 in range(0, args.candidates, batch):
        cands += generate(min(batch, args.candidates - b0), args.seed * 100 + b0 // batch, originals_only=args.originals_only)
        say(f"  stage A: {len(cands)} legal candidates  t={time.time() - t0:.0f}s")
    X = np.array([c[2] for c in cands])
    pred = model.predict(X)
    rng = random.Random(args.seed)

    def pick(idx, k):
        order = sorted(idx, key=lambda i: -pred[i])
        n_explore = k // 6  # random explorers: the predictor is only a coarse filter
        return order[: k - n_explore] + rng.sample(order[k - n_explore:], min(n_explore, len(order[k - n_explore:])))

    def zone_of(i):
        return cands[i][1].rsplit("-", 1)[-1] if args.originals_only else "all"

    zones = sorted({zone_of(i) for i in range(len(cands))})
    # equal quick-sim quota per Town Hall zone (originals-only), so no zone is crowded out early
    picked = [i for z in zones for i in pick([i for i in range(len(cands)) if zone_of(i) == z], args.quick // len(zones))]
    origins: dict = {}
    for i in picked:
        origins[cands[i][1]] = origins.get(cands[i][1], 0) + 1
    say(f"stage A done: {len(cands)} candidates ranked by the predictor; {len(picked)} go to quick sims "
        f"(by origin: {dict(sorted(origins.items(), key=lambda kv: -kv[1])[:8])})")
    quick = quick_sets()[mode]
    scored = []
    for b0 in range(0, len(picked), 50):
        idx = picked[b0:b0 + 50]
        res = eval_many([Layout.from_json(cands[i][0]) for i in idx], quick, mode)
        scored += [(sc, i) for (sc, _ev), i in zip(res, idx)]
        say(f"  stage B: {b0 + len(idx)}/{len(picked)}  t={time.time() - t0:.0f}s")
    scored.sort(reverse=True)
    say(f"stage B done: quick-sim best {scored[0][0]:.2f}, 50th {scored[min(49, len(scored) - 1)][0]:.2f}")
    full = meta_scenarios(mode, 8, (0, 1))
    finals = []
    per_zone = args.full // len(zones)
    to_full = [i for z in zones for i in [i for _, i in scored if zone_of(i) == z][:per_zone]]
    for b0 in range(0, len(to_full), 10):
        idx = to_full[b0:b0 + 10]
        res = eval_many([Layout.from_json(cands[i][0]) for i in idx], full, mode)
        finals += [(sc, i, ev.summary()) for (sc, ev), i in zip(res, idx)]
    finals.sort(reverse=True)
    say(f"stage C done (272 battles each): top {finals[0][0]:.2f} {finals[0][2]} [{cands[finals[0][1]][1]}]")
    for s, i, summ in finals[:10]:
        say(f"    {s:7.2f}  {summ}  origin {cands[i][1]}")
    keep_per_zone = max(1, args.keep // len(zones))
    top_idx = [i for z in zones for i in [i for _, i, _ in finals if zone_of(i) == z][:keep_per_zone]]
    top = [Layout.from_json(cands[i][0]) for i in top_idx]
    for z in zones:
        zs = [s for s, i, _ in finals if zone_of(i) == z]
        if zs:
            say(f"  zone {z:6s}: best full score {max(zs):.2f} ({len(zs)} fully scored)")
    for k, lay in enumerate(top):
        lay.name = f"f{args.seed}-{k}"
    (out / "population.json").write_text(json.dumps([l.to_json() for l in top]))
    (out / "stage-c.json").write_text(json.dumps([{"score": s, "origin": cands[i][1], "summary": su} for s, i, su in finals], indent=1))
    say(f"wrote {len(top)} bases to {out / 'population.json'} in {time.time() - t0:.0f}s")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("data")
    d.add_argument("--n", type=int, default=1300)
    d.add_argument("--seed", type=int, default=7)
    d.add_argument("--out", default=str(ROOT / "output" / "funnel" / "data.jsonl"))
    t = sub.add_parser("train")
    t.add_argument("--data", default=str(ROOT / "output" / "funnel" / "data.jsonl"))
    t.add_argument("--out-dir", default=str(ROOT / "output" / "funnel"))
    s = sub.add_parser("screen")
    s.add_argument("--mode", choices=["ranked", "war"], default="ranked")
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--candidates", type=int, default=15000)
    s.add_argument("--quick", type=int, default=500)
    s.add_argument("--full", type=int, default=50)
    s.add_argument("--keep", type=int, default=20)
    s.add_argument("--model-dir", default=str(ROOT / "output" / "funnel"))
    s.add_argument("--originals-only", action="store_true", help="only from-scratch designs, equal quotas per Town Hall zone")
    s.add_argument("--out", default=str(ROOT / "output" / "funnel" / "ranked-1"))
    args = ap.parse_args()
    {"data": cmd_data, "train": cmd_train, "screen": cmd_screen}[args.cmd](args)


if __name__ == "__main__":
    main()
