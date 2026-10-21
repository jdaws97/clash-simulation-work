"""Evolve TH16 bases: a population of original layouts improved by
crossover + mutation (including attack-aware moves), with diversity kept so
several design ideas compete, and a validation guard on the reported best.

Every generation:
  1. children: 60% crossover of two tournament-picked parents (then 0-2
     mutations), 40% mutation only (1-3 moves); the current best's children
     use attack-aware moves aimed at its traced weak spots.
  2. score children on the search scenarios (fixed: common random numbers).
  3. survivors: best first, skipping near-duplicates of a better survivor
     (wall-plan overlap above --dup).
  4. the leader is checked on independent validation battles; the best
     validated layout is what gets reported.
Co-evolution (--adapt-every N): every N generations the adaptive attacker
(tactics.py, CEM) tunes each meta army against the current leader; the
tactics found are archived and become scenarios (--adapt-share of the
weight) for every base from then on, so bases must hold against counter-
strategies, not only the scripted plans. The population is re-scored then.
At the end the top validated layouts are scored on hold-out battles next to
benchmark layouts (--compare).

Usage:
  python tools/baselab/evolve_bases.py --mode ranked --pop 24 --children 24 --gens 30 --out output/evolve-ranked
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.archetypes import design  # noqa: E402
from baselab.diagnose import diagnose  # noqa: E402
from baselab.evaluate import adaptive_scenarios, blend, evaluate, meta_scenarios, ranked_scenarios, war_scenarios  # noqa: E402
from baselab.meta_armies import library  # noqa: E402
from baselab import tactics  # noqa: E402
from baselab.surrogate import Ridge, features  # noqa: E402
import numpy as np  # noqa: E402
from baselab.evolve import crossover, wall_similarity  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.optimize import hole_tiles, mutate, objective  # noqa: E402
from baselab.render import render  # noqa: E402


META = False


def scen(mode, n, seeds, angle_offset=0.0):
    if META:
        return meta_scenarios(mode, n, seeds, angle_offset=angle_offset)
    if mode == "ranked":
        return ranked_scenarios(n_angles=n, seeds=seeds, angle_offset=angle_offset)
    return war_scenarios(n_angles=n, seeds=seeds, angle_offset=angle_offset)


class Ind:
    def __init__(self, lay, score, ev):
        self.lay, self.score, self.ev = lay, score, ev
        self.val = None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["ranked", "war"], default="ranked")
    ap.add_argument("--pop", type=int, default=24)
    ap.add_argument("--children", type=int, default=24)
    ap.add_argument("--gens", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dup", type=float, default=0.85)
    ap.add_argument("--seed-files", nargs="*", default=[], help="extra layouts added to the first population")
    ap.add_argument("--resume", help="population.json from an earlier run")
    ap.add_argument("--compare", nargs="*", default=[])
    ap.add_argument("--adapt-every", type=int, default=0)
    ap.add_argument("--adapt-share", type=float, default=0.35)
    ap.add_argument("--adapt-keep", type=int, default=2, help="tactics kept per army")
    ap.add_argument("--final-adaptive", action="store_true", help="tune fresh attacks against each finalist at the end")
    ap.add_argument("--meta", action="store_true", help="real TrophyCoach builds (meta_armies.py) instead of the 4 scripted armies")
    ap.add_argument("--search-angles", type=int, default=4)
    ap.add_argument("--search-seeds", type=int, default=2)
    ap.add_argument("--rr-sides", type=float, default=0.0, help="share of the score from Root Rider + RC charge attacks on the weakest side")
    ap.add_argument("--niche", action="store_true", help="keep at least pop/4 survivors per Town Hall zone (center / mid / edge)")
    ap.add_argument("--surrogate", type=int, default=0, help="propose this many times more children and simulate the ones the learned predictor ranks best (0 = off)")
    ap.add_argument("--no-random", action="store_true", help="start from --seed-files only (a polish, not a search)")
    ap.add_argument("--max-holes", type=int, default=20, help="children with more drop-pocket tiles are discarded")
    ap.add_argument("--out", default=str(ROOT / "output" / "evolve"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    logf = open(out / "evolve.log", "a", encoding="utf-8")

    def log(m):
        print(m, flush=True)
        logf.write(m + "\n")
        logf.flush()

    rng = random.Random(args.seed)
    global META
    META = args.meta
    search0 = scen(args.mode, args.search_angles, tuple(range(args.search_seeds)))
    # validation and hold-out face sides the search never uses (the angles
    # depend on the angle count and offset only, not on the seeds)
    validate0 = scen(args.mode, 6, (8, 9), math.pi / 4)
    holdout_extra = []
    if args.rr_sides > 0:
        from baselab.evaluate import side_scenarios

        rr = [("custom:user-rr", 16), ("meta:root-rider-16-1", 16), ("meta:root-rider-18-1", 18)]
        search0 = blend(search0, side_scenarios(rr, (0, 1), args.rr_sides), args.rr_sides)
        validate0 = blend(validate0, side_scenarios(rr, (8, 9), args.rr_sides), args.rr_sides)
        holdout_extra = side_scenarios(rr, (21, 22, 23), args.rr_sides)
    search, validate = list(search0), list(validate0)
    archive: dict = {}
    attackers = [(a, 18) for a in ("hydra", "throwers", "edrag", "rootrider")] if args.mode == "ranked" else         [(a, 16) for a in ("hydra", "edrag", "rootrider", "throwers")]
    weights = None
    if args.meta:
        # co-evolving attackers: the 4 most-used real builds for the attacking Town Hall
        th_a = 18 if args.mode == "ranked" else 16
        lib = sorted(library(th_a), key=lambda bw: -bw[1])[:4]
        attackers = [(f"meta:{b['archetype']}-{b['th']}-{b['build']}", th_a) for b, _ in lib]
        weights = {a: w for (a, _), (_, w) in zip(attackers, lib)}
    guide = scen(args.mode, 4, (0,))
    holdout = scen(args.mode, 8, (21, 22, 23), math.pi / 8)  # seed 1 is a search seed
    if holdout_extra:
        holdout = blend(holdout, holdout_extra, args.rr_sides)
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())

    def levels(lay):
        lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
        return lay

    memory: list = []  # (features, score) of every simulated layout, for the predictor

    def score(lay):
        ev = evaluate(lay, search)
        ind = Ind(lay, objective(ev, args.mode, lay), ev)
        if args.surrogate:
            memory.append((features(lay), ind.score))
        return ind

    t0 = time.time()
    pop: list[Ind] = []
    if args.resume:
        for lj in json.loads(Path(args.resume).read_text()):
            pop.append(score(levels(Layout.from_json(lj))))
        log(f"resumed {len(pop)} from {args.resume}")
    elif not args.no_random:
        kinds = ["organic", "organic", "free", "grid", "offset", "rings", "wide", "organic"]
        i = 0
        while len(pop) < args.pop:
            kind = kinds[i % len(kinds)]
            try:
                lay = levels(design(kind, args.seed * 10000 + i))
            except RuntimeError:
                i += 1
                continue
            i += 1
            pop.append(score(lay))
            log(f"  init {lay.name:22s} {pop[-1].score:7.2f}  {pop[-1].ev.summary()}")
    for f in args.seed_files:
        lay = levels(Layout.load(f))
        lay.name = "seed-" + Path(f).stem
        pop.append(score(lay))
        log(f"  seed {lay.name:22s} {pop[-1].score:7.2f}")
    pop.sort(key=lambda d: -d.score)
    best_val: Ind | None = None
    uid = 0

    def tournament():
        return max(rng.sample(pop, min(3, len(pop))), key=lambda d: d.score)

    for gen in range(args.gens):
        leader = pop[0]
        if args.adapt_every and gen % args.adapt_every == 0:
            for army, th in attackers:
                r = tactics.optimize(leader.lay, army, th, iters=4, pop=16, k=2, seed=gen)
                archive.setdefault((army, th), []).append(tuple(map(float, r.vec)))
                archive[(army, th)] = archive[(army, th)][-args.adapt_keep:]
                log(f"  adaptive {army}@TH{th} vs {leader.lay.name}: {r.summary()}  {tactics.describe(r.vec)}")
            search = blend(search0, adaptive_scenarios(archive, args.mode, (0, 1), args.adapt_share, weights), args.adapt_share)
            validate = blend(validate0, adaptive_scenarios(archive, args.mode, (8, 9), args.adapt_share, weights), args.adapt_share)
            pop = sorted((score(d.lay) for d in pop), key=lambda d: -d.score)
            leader = pop[0]
            if best_val is not None:
                best_val.val = objective(evaluate(best_val.lay, validate), args.mode, best_val.lay)
            log(f"  re-scored population with {len(search)} scenarios ({sum(len(v) for v in archive.values())} tactics); leader {leader.lay.name} {leader.score:.2f}")
        # battle traces for the top parents (A/B 2026-10-15: guided moves gained
        # +1.10 on hold-out vs +0.16 for random moves, same compute)
        top_ids = {id(d) for d in pop[:4]}
        diags: dict = {}

        def diag_for(ind):
            if id(ind) not in top_ids:
                return None
            if id(ind) not in diags:
                diags[id(ind)] = diagnose(ind.lay, guide)
            return diags[id(ind)]
        kids = []
        tries = 0
        want = args.children * max(1, args.surrogate)
        while len(kids) < want and tries < want * 6:
            tries += 1
            if rng.random() < 0.6:
                a, b = tournament(), tournament()
                if a is b:
                    continue
                c = crossover(a.lay, b.lay, rng)
                if c is None or hole_tiles(c) > args.max_holes:
                    continue
                how = "x"
                for _ in range(rng.randint(0, 2)):
                    m, d = mutate(c, rng)
                    if d != "noop" and not m.problems():
                        c = m
            else:
                p = rng.choice(pop[:4]) if rng.random() < 0.5 else tournament()
                c, how = p.lay, "m"
                for _ in range(rng.randint(1, 3)):
                    m, d = mutate(c, rng, diag_for(p))
                    if d != "noop" and not m.problems():
                        c = m
                if c is p.lay:
                    continue
            if hole_tiles(c) > args.max_holes:
                continue
            uid += 1
            c = c.copy()
            c.name = f"g{gen}-{how}{uid}"
            kids.append(c)
        if args.surrogate > 1 and len(memory) >= 40 and len(kids) > args.children:
            X = np.array([m[0] for m in memory[-600:]])
            y = np.array([m[1] for m in memory[-600:]])
            model = Ridge(30.0).fit(X, y)
            pred = model.predict(np.array([features(c) for c in kids]))
            order = list(np.argsort(-pred))
            n_explore = max(1, args.children // 5)
            chosen = order[: args.children - n_explore]
            rest = order[args.children - n_explore:]
            chosen += list(rng.sample(rest, min(n_explore, len(rest))))
            kids = [kids[i] for i in chosen]
        else:
            kids = kids[: args.children]
        scored = [score(c) for c in kids]
        everyone = sorted(pop + scored, key=lambda d: -d.score)
        nxt: list[Ind] = []
        if args.niche:
            from baselab.archetypes import TH_ZONES, th_zone

            for z in TH_ZONES:  # protected niches: the best few of every Town Hall zone survive
                nxt += [d for d in everyone if th_zone(d.lay) == z][: args.pop // 4]
        for d in everyone:
            if len(nxt) >= args.pop:
                break
            if d in nxt:
                continue
            if any(wall_similarity(d.lay, k.lay) > args.dup and d.score <= k.score for k in nxt[:8]) and len(nxt) < args.pop - 2:
                continue
            nxt.append(d)
        nxt.sort(key=lambda d: -d.score)
        pop = nxt
        lead = pop[0]
        if lead.val is None:
            ev = evaluate(lead.lay, validate)
            lead.val = objective(ev, args.mode, lead.lay)
        if best_val is None or lead.val > best_val.val:
            best_val = lead
            best_val.lay.save(out / "best.json")
            render(best_val.lay, out / "best.png", title=f"evolved {args.mode} gen {gen} ({best_val.ev.summary()})")
        med = sorted(d.score for d in pop)[len(pop) // 2]
        log(f"gen {gen:3d}  best {lead.score:7.2f} ({lead.lay.name}) val {lead.val:7.2f}  median {med:7.2f}  "
            f"kids {len(kids)} (x {sum(k.name.split('-')[1].startswith('x') for k in kids)})  "
            f"best-validated {best_val.lay.name} {best_val.val:.2f}  {lead.ev.summary()}  t={time.time() - t0:.0f}s")
        (out / "population.json").write_text(json.dumps([d.lay.to_json() for d in pop]))

    log("== hold-out")
    finals, seen = [], set()
    for d in [best_val] + pop[:3]:
        if d.lay.name not in seen:  # the population is re-scored into new objects
            seen.add(d.lay.name)
            finals.append(d)
    rows = []
    bench = []
    for f in args.compare:
        lay = levels(Layout.load(f))
        lay.name = "bench-" + Path(f).parent.name + "-" + Path(f).stem
        bench.append(lay)
    for lay in [d.lay for d in finals] + bench:
        ev = evaluate(lay, holdout)
        if holdout_extra:
            rr = evaluate(lay, holdout_extra)
            log(f"  {lay.name:34s} Root Rider + RC charge, weakest side: 3* {rr.three_star_rate:5.1%}  avg {rr.avg_stars:.2f}*  {rr.avg_destruction:5.1f}%")
        sc = objective(ev, args.mode, lay)
        rows.append({"name": lay.name, "holdout": sc, "summary": ev.summary(), "holes": hole_tiles(lay)})
        log(f"  {lay.name:34s} hold-out {sc:7.2f}  {ev.summary()}  holes {hole_tiles(lay)}")
    if args.final_adaptive:
        log("== adaptive attackers (fresh tactic search per finalist)")
        meta = {"hydra": 0.271, "throwers": 0.260, "edrag": 0.115, "rootrider": 0.097} if args.mode == "ranked" else             {"hydra": 0.375, "edrag": 0.257, "rootrider": 0.146, "throwers": 0.061}
        for row, lay in zip(rows, [d.lay for d in finals] + bench):
            per = {}
            for army, th in attackers:
                r = tactics.optimize(lay, army, th, iters=5, pop=20, k=3, seed=99)
                per[army] = r.three_star
            row["adaptive_3star"] = per
            ww = weights or meta
            row["adaptive_3star_meta"] = sum(ww.get(a, 0.05) * v for a, v in per.items()) / sum(ww.get(a, 0.05) for a in per)
            log(f"  {lay.name:34s} adaptive 3* (meta-weighted) {row['adaptive_3star_meta']:5.1%}  {per}")
    (out / "holdout.json").write_text(json.dumps(rows, indent=1))
    log(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
