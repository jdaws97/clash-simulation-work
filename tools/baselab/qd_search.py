"""Quality-diversity base search (MAP-Elites): keep the best base of every
KIND, not one lineage descended from a few seed bases.

A base's kind is four layout descriptors, three bins each (81 cells):
  Town Hall zone (center / mid / edge, archetypes.th_zone),
  Eagle Artillery depth (core / middle / outer: share of buildings closer
    to the centroid than it, < 0.1 / < 0.3 / more),
  wall compartments of 4+ tiles (open <= 6 / 7-14 / 15+; ranked-funnel1
    has 3, generated originals 7-21),
  defense spread (mean defense distance from the centroid).
It starts from freshly generated originals only (no user or earlier bases):
the compartment generators plus unconventional ones (open cram, onion,
scatter; unconventional.py), so radically different designs compete too.
Each batch makes children by mutating elites, crossing elites of different
cells, and generating new originals; a child takes its cell after completing
the confirm set and beating the cell's elite (the same seeds for everyone).
At the end the best elites get the full battle set, then a hold-out comparison
with the reference bases.

Two-stage scoring: quick and confirm sets race children against their cell's
elite; the independent, larger confirm set decides after completion. Complete
scouting groups are sampled within each army's fixed mixture weight. Run
with BASELAB_HOLE_PENALTY=0 to score pure defense trophies. --seed-files adds
starting layouts; --race-chunk 0 restores full evaluations and bulk init.

Usage: python tools/baselab/qd_search.py --out output/qd --batches 30 [--batch 64] [--mode ranked] [--seed-files A.json ...]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.archetypes import compartments, design, th_zone  # noqa: E402
from baselab.evaluate import (
    STRENGTH,
    meta_scenarios,
    pool,
    run_batch,
    summarise,
)  # noqa: E402
from baselab.evolve import crossover  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.optimize import mutate, objective  # noqa: E402
from baselab.render import render  # noqa: E402
from baselab.rust_bridge import batch_statistics  # noqa: E402
from baselab.unconventional import STYLES, unconventional  # noqa: E402
from funnel import KINDS, eval_many, own_levels  # noqa: E402

DEF = {
    "inferno",
    "eagle",
    "scatter",
    "xbow",
    "mono",
    "ad",
    "mat",
    "ric",
    "wt",
    "bt",
    "mortar",
    "at",
    "cannon",
    "sweeper",
    "tesla",
    "st",
    "crafting",
}


def descriptor(lay: Layout):
    bs = [b for b in lay.buildings if b.key not in ("wall",)]
    if not bs:
        return None
    cx = sum(b.x + b.size / 2 for b in bs) / len(bs)
    cy = sum(b.y + b.size / 2 for b in bs) / len(bs)

    def r(b):
        return math.hypot(b.x + b.size / 2 - cx, b.y + b.size / 2 - cy)

    dists = sorted(r(b) for b in bs)
    eagle = next((b for b in bs if b.key == "eagle"), None)
    if eagle is None:
        return None
    pct = sum(d < r(eagle) for d in dists) / len(dists)
    e = 0 if pct < 0.1 else 1 if pct < 0.3 else 2
    zone = {"center": 0, "mid": 1, "edge": 2}.get(th_zone(lay), 1)
    n = sum(
        len(c) >= 4 for c in compartments(lay.walls)[0]
    )  # enclosed areas of 4+ tiles
    c = 0 if n <= 6 else 1 if n <= 14 else 2
    defs = [r(b) for b in bs if b.key in DEF]
    spread = sum(defs) / max(1, len(defs))
    s = 0 if spread < 11.3 else 1 if spread < 12.3 else 2
    return (zone, e, c, s)


def _child(args):
    """One child layout (json) from an op; runs in a worker."""
    op, seed, a_json, b_json = args
    rng = random.Random(seed)
    own = own_levels()
    try:
        if op == "new":
            if rng.random() < 0.35:
                lay = unconventional(
                    rng.choice(STYLES), seed
                )  # open cram, onion, scatter
            else:
                lay = design(
                    rng.choice(KINDS), seed, zone=rng.choice(["center", "mid", "edge"])
                )
        elif op == "cross":
            lay = crossover(Layout.from_json(a_json), Layout.from_json(b_json), rng)
            if lay is None:
                return None
        else:
            lay = Layout.from_json(a_json)
            for _ in range(rng.choice([1, 2, 3, 5, 8])):
                m, d = mutate(lay, rng)
                if d != "noop" and not m.problems():
                    lay = m
        if lay.problems():
            return None
        lay.levels, lay.wall_level, lay.hero_levels = (
            dict(own["levels"]),
            own["wall_level"],
            dict(own["hero_levels"]),
        )
        return lay.to_json()
    except (RuntimeError, ValueError, IndexError, KeyError):
        return None


class QuickRace:
    """Race a fixed set, preserving paired scouting groups and weights."""

    def __init__(self, scenarios, *, chunk_size=32, alpha=0.01, seed=0, stage="quick"):
        self.stage = stage
        self.scenarios = list(scenarios)
        if not self.scenarios:
            raise ValueError("the racing set must not be empty")
        if chunk_size < 0 or not 0 < alpha < 0.5:
            raise ValueError("racing needs a nonnegative chunk and 0 < alpha < 0.5")
        if any(not math.isfinite(sc.weight) or sc.weight < 0 for sc in self.scenarios):
            raise ValueError("scenario weights must be finite and nonnegative")
        self.weight = math.fsum(sc.weight for sc in self.scenarios)
        if self.weight <= 0:
            raise ValueError("scenario weights must have a positive total")
        groups = {}
        for i, sc in enumerate(self.scenarios):
            key = (sc.army, sc.town_hall, sc.modifier, sc.full_scout, sc.group)
            groups.setdefault(key, []).append(i)
        strata = {}
        for key, indices in groups.items():
            if any(self.scenarios[i].weight > 0 for i in indices):
                strata.setdefault(key[:-1], []).append(indices)
        self.strata = list(strata.values())
        rng = random.Random(seed)
        for stratum in self.strata:
            rng.shuffle(stratum)
        self.chunks = []
        pending = []
        # evaluate.py:713: sides/techniques in one group share battles.
        # Two complete groups per army are needed before estimating variance.
        for round_index in range(max(map(len, self.strata))):
            for stratum in self.strata:
                if round_index < len(stratum):
                    pending.extend(stratum[round_index])
            if chunk_size and round_index >= 1 and len(pending) >= chunk_size:
                self.chunks.append(pending)
                pending = []
        # Zero-weight groups still belong to the original complete battle set.
        covered = {i for stratum in self.strata for group in stratum for i in group}
        pending.extend(i for i in range(len(self.scenarios)) if i not in covered)
        if pending:
            self.chunks.append(pending)
        if chunk_size == 0:
            self.chunks = [list(range(len(self.scenarios)))]
        looks = max(1, len(self.chunks) - 1)
        # docs/GAP_ANALYSIS.md:50-53: pair uncertainty rather than point scores.
        # Spend nominal alpha over all looks; >=3 SE plus the small-sample
        # Student correction below protects close contenders (an approximation).
        self.critical = max(3.0, NormalDist().inv_cdf(1 - alpha / looks))

    def upper_bound(self, results, elite_results, mode, penalty_difference):
        """Upper bound for child - elite on the finite full battle set."""
        difference = penalty_difference
        variance = 0.0
        variance_degrees = 0.0
        incomplete = False
        for stratum in self.strata:
            paired = []
            for indices in stratum:
                if any(results[i] is None for i in indices):
                    continue
                scenarios = [self.scenarios[i] for i in indices]
                child = summarise(scenarios, [results[i] for i in indices])
                elite = summarise(scenarios, [elite_results[i] for i in indices])
                weight = math.fsum(sc.weight for sc in scenarios) / self.weight
                paired.append(
                    weight * (objective(child, mode) - objective(elite, mode))
                )
            count, population = len(paired), len(stratum)
            if not count or (count < population and count < 2):
                return math.inf
            # Uniform sampling without replacement within each army. Scaling
            # by population/count preserves unequal scenario weights in mean.
            mean = math.fsum(paired) / count
            difference += population * mean
            if count < population:
                incomplete = True
                stratum_variance = (
                    population**2
                    * (1 - count / population)
                    * math.fsum((value - mean) ** 2 for value in paired)
                    / (count * (count - 1))
                )
                variance += stratum_variance
                variance_degrees += stratum_variance**2 / (count - 1)
        # A constant prefix cannot establish zero uncertainty about unseen play.
        if incomplete and variance == 0:
            return math.inf
        if not incomplete:
            return difference
        # Welch degrees of freedom detect a few high-weight pairs dominating
        # the estimate. Keep sampling if fewer than four degrees remain.
        degrees = variance**2 / variance_degrees
        if degrees < 4:
            return math.inf
        z = self.critical
        # Student-t quantile expansion, with an extra 1/df safety cushion.
        critical = (
            z
            + (z**3 + z) / (4 * degrees)
            + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * degrees**2)
            + (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / (384 * degrees**3)
            + 1 / degrees
        )
        return difference + critical * math.sqrt(variance)

    def evaluate(self, lays, mode, archive, elite_results, margin, *, score_index=3):
        """Return complete scores in input order plus this stage's battle usage."""
        engine_before = batch_statistics()
        results = [[None] * len(self.scenarios) for _ in lays]
        paired = {}
        for i, (lay, cell) in enumerate(lays):
            if cell in archive and cell in elite_results:
                rows = elite_results[cell]
                ev = summarise(self.scenarios, rows)
                # optimize.py:42: the layout penalty is deterministic and
                # must be included in the paired difference, without extra noise.
                penalty = objective(ev, mode, lay) - archive[cell][score_index]
                paired[i] = (rows, penalty)
        active = list(range(len(lays)))
        completed = []
        battles = calls = stopped = 0
        for chunk in self.chunks:
            if not active:
                break
            jobs = []
            placements = []
            for i in active:
                # Empty cells need the entire set. Put those jobs in the
                # same call as the first chunks of children with incumbents.
                indices = chunk if i in paired else range(len(self.scenarios))
                layout_json = lays[i][0].to_json()
                for index in indices:
                    sc = self.scenarios[index]
                    jobs.append((layout_json, sc, STRENGTH.get(sc.army, 1.0)))
                    placements.append((i, index))
            rows = run_batch(jobs)
            if len(rows) != len(placements):
                raise RuntimeError("the race needs one result per battle")
            battles += len(jobs)
            calls += 1
            for (i, index), row in zip(placements, rows):
                results[i][index] = row
            survivors = []
            for i in active:
                if all(row is not None for row in results[i]):
                    ev = summarise(self.scenarios, results[i])
                    score = objective(ev, mode, lays[i][0])
                    completed.append((i, score, results[i]))
                else:
                    elite_rows, penalty = paired[i]
                    if (
                        self.upper_bound(results[i], elite_rows, mode, penalty)
                        < -margin
                    ):
                        stopped += 1
                    else:
                        survivors.append(i)
            active = survivors
        completed.sort(key=lambda row: row[0])
        usage = {
            self.stage: battles,
            f"{self.stage}_full": len(lays) * len(self.scenarios),
            f"{self.stage}_early_stopped": stopped,
            f"{self.stage}_race_calls": calls,
            "early_stopped": stopped,
            "race_calls": calls,
        }
        if os.environ.get("BASELAB_ENGINE") == "rust":
            engine_after = batch_statistics()
            for key in ("battles", "calls"):
                usage[f"{self.stage}_engine_{key}"] = (
                    engine_after[key] - engine_before[key]
                )
        return completed, usage


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["ranked", "war"], default="ranked")
    ap.add_argument("--batches", type=int, default=30)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--init", type=int, default=192)
    ap.add_argument(
        "--final", type=int, default=16, help="elites given the full battle set"
    )
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument(
        "--margin",
        type=float,
        default=1.0,
        help="stage-1 slack below the elite's quick score",
    )
    ap.add_argument(
        "--race-chunk",
        type=int,
        default=32,
        help="target battles per child per racing wave (0 disables early stopping)",
    )
    ap.add_argument(
        "--race-alpha",
        type=float,
        default=0.01,
        help="nominal per-child false-rejection budget across looks in each stage",
    )
    ap.add_argument(
        "--seed-files",
        nargs="*",
        default=[],
        help="layouts to start from (e.g. digitized builder bases)",
    )
    args = ap.parse_args()
    if args.race_chunk < 0 or not 0 < args.race_alpha < 0.5:
        ap.error("racing needs --race-chunk >= 0 and 0 < --race-alpha < 0.5")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    quick = meta_scenarios(args.mode, 2 if args.mode == "ranked" else 4, (0,))
    race = QuickRace(
        quick, chunk_size=args.race_chunk, alpha=args.race_alpha, seed=args.seed
    )
    # second stage: an independent, larger set (other seeds, other sides).
    # The quick set only prunes; a child takes a cell only on this score, so
    # a design that got lucky on 44 battles cannot win (the first run's
    # quick-set "best" of 11.1 trophies fell to 5.3 on the full set).
    confirm = meta_scenarios(args.mode, 4, (1, 2), angle_offset=math.pi / 4)
    confirm_race = QuickRace(
        confirm,
        chunk_size=args.race_chunk,
        alpha=args.race_alpha,
        seed=args.seed,
        stage="confirm",
    )
    archive: dict = {}  # cell -> (confirm score, layout_json, summary, quick score)
    elite_results: dict = {}  # cell -> quick rows in the original scenario order
    confirm_results: dict = {}  # cell -> complete confirm rows in scenario order
    battles_total = 0
    stage_totals = {"quick": 0, "confirm": 0}
    engine_start = batch_statistics()
    t0 = time.time()
    log = open(out / "progress.log", "a", encoding="utf-8")

    def say(m):
        print(m, flush=True)
        log.write(m + "\n")
        log.flush()

    def offer(jsons, *, initialize=False):
        nonlocal battles_total
        engine_before = batch_statistics()
        lays = [Layout.from_json(j) for j in jsons if j is not None]
        lays = [(l, descriptor(l)) for l in lays]
        lays = [(l, d) for l, d in lays if d is not None]
        waves = [lays]
        if initialize and args.race_chunk:
            # output/overnight/qd-proof/progress.log: init pays both sets.
            # Keep per-cell input order; fill cells before racing their rivals.
            waves = []
            counts = {}
            for lay, cell in lays:
                wave = counts.get(cell, 0)
                counts[cell] = wave + 1
                if wave == len(waves):
                    waves.append([])
                waves[wave].append((lay, cell))
        usage = {
            "quick": 0,
            "quick_full": 0,
            "confirm": 0,
            "confirm_full": 0,
            "quick_early_stopped": 0,
            "confirm_early_stopped": 0,
            "quick_race_calls": 0,
            "confirm_race_calls": 0,
            "early_stopped": 0,
            "race_calls": 0,
        }
        won = 0
        for wave in waves:
            scored, quick_usage = race.evaluate(
                wave, args.mode, archive, elite_results, args.margin
            )
            # output/overnight/qd-proof/progress.log: init confirmed originals;
            # completed quick sets still pass without a new point-score screen.
            keep = [
                (wave[i][0], wave[i][1], qs, rows)
                for i, qs, rows in scored
                if initialize
                or wave[i][1] not in archive
                or qs >= archive[wave[i][1]][3] - args.margin
            ]
            full, confirm_usage = confirm_race.evaluate(
                [(lay, cell) for lay, cell, _, _ in keep],
                args.mode,
                archive,
                confirm_results,
                args.margin,
                score_index=0,
            )
            for stage_usage in (quick_usage, confirm_usage):
                for key, value in stage_usage.items():
                    usage[key] = usage.get(key, 0) + value
            for i, cs, rows in full:
                lay, cell, qs, quick_rows = keep[i]
                if cell not in archive or cs > archive[cell][0]:
                    ev = summarise(confirm, rows)
                    archive[cell] = (cs, lay.to_json(), ev.summary(), qs)
                    elite_results[cell] = quick_rows
                    confirm_results[cell] = rows
                    won += 1
        if os.environ.get("BASELAB_ENGINE") == "rust":
            engine_after = batch_statistics()
            usage["engine_battles"] = engine_after["battles"] - engine_before["battles"]
            usage["engine_calls"] = engine_after["calls"] - engine_before["calls"]
        battles_total += usage.get("engine_battles", usage["quick"] + usage["confirm"])
        for stage in stage_totals:
            stage_totals[stage] += usage.get(f"{stage}_engine_battles", usage[stage])
        return won, usage

    def battle_log(usage):
        used = usage.get("engine_battles", usage["quick"] + usage["confirm"])
        engine_calls = ""
        if "engine_calls" in usage:
            engine_calls = (
                f", quick_engine_battles={usage.get('quick_engine_battles', 0)}, "
                f"confirm_engine_battles={usage.get('confirm_engine_battles', 0)}, "
                f"engine_calls={usage['engine_calls']}"
            )
        return (
            f"battles={used} (quick_jobs={usage['quick']}/{usage['quick_full']}, "
            f"confirm_jobs={usage['confirm']}/{usage['confirm_full']}, "
            f"quick_early_stopped={usage['quick_early_stopped']}, "
            f"confirm_early_stopped={usage['confirm_early_stopped']}, "
            f"early_stopped={usage['early_stopped']}, "
            f"race_calls={usage['race_calls']}{engine_calls}) "
            f"search_battles_total={battles_total}"
        )

    for stage_race in (race, confirm_race):
        say(
            f"race: {len(stage_race.scenarios)} {stage_race.stage} battles, "
            f"{len(stage_race.chunks)} waves, upper = paired mean + at least "
            f"{stage_race.critical:.3f} SE < -{args.margin:g}; "
            f"alpha={args.race_alpha:g} per child per stage (Student-t approximation)"
        )

    jobs = [("new", args.seed * 1_000_000 + i, None, None) for i in range(args.init)]
    seeds_json = []
    own_lv = own_levels()
    for f in args.seed_files:
        l = Layout.load(Path(f))
        if l.problems():
            say(f"skipping seed {f}: {l.problems()[:3]}")
            continue
        l.levels, l.wall_level, l.hero_levels = (
            dict(own_lv["levels"]),
            own_lv["wall_level"],
            dict(own_lv["hero_levels"]),
        )
        l.name = "seed-" + Path(f).stem
        seeds_json.append(l.to_json())
    won, usage = offer(
        seeds_json + list(pool().map(_child, jobs, chunksize=4)), initialize=True
    )
    say(
        f"init: {len(archive)} cells filled ({won} entries) {battle_log(usage)} "
        f"t={time.time() - t0:.0f}s"
    )
    for bt in range(args.batches):
        cells = list(archive)
        jobs = []
        for i in range(args.batch):
            r = rng.random()
            seed = args.seed * 1_000_000 + 10_000 * (bt + 1) + i
            if r < 0.15:
                jobs.append(("new", seed, None, None))
            elif r < 0.45 and len(cells) > 1:
                a, b = rng.sample(cells, 2)
                jobs.append(("cross", seed, archive[a][1], archive[b][1]))
            else:
                # parents weighted toward the better elites, all cells still chosen
                ranked = sorted(cells, key=lambda c: -archive[c][0])
                c = ranked[
                    min(
                        int(rng.expovariate(1 / max(1.0, len(ranked) / 3))),
                        len(ranked) - 1,
                    )
                ]
                jobs.append(("mutate", seed, archive[c][1], None))
        won, usage = offer(list(pool().map(_child, jobs, chunksize=4)))
        best = max(archive.values(), key=lambda v: v[0])
        say(
            f"batch {bt}: {won} improvements, {len(archive)} cells, best confirmed {best[0]:.2f} | {best[2]}  "
            f"{battle_log(usage)} t={time.time() - t0:.0f}s"
        )
        json.dump(
            {str(k): v[:2] for k, v in archive.items()}, open(out / "archive.json", "w")
        )

    # full battle set for the best elites, then hold-out against the references
    full = meta_scenarios(args.mode, 8, (0, 1))
    top = sorted(archive.items(), key=lambda kv: -kv[1][0])[: args.final]
    lays = [Layout.from_json(v[1]) for _, v in top]
    for (cell, _), l in zip(top, lays):
        l.name = "qd-" + "".join(map(str, cell))
    ordinary = eval_many(lays, full, args.mode)
    # docs/GAP_ANALYSIS.md:85-87: finalists must survive adaptive attackers.
    scored = eval_many(lays, full, args.mode, redteam=True)
    order = sorted(zip(lays, scored, ordinary), key=lambda x: -x[1][0])
    say("== full battle set (TH zone, Eagle depth, compartments, spread)")
    for l, (s, ev), (normal, normal_ev) in order:
        say(f"  {l.name} red-team {s:6.2f}  {ev.summary()}")
        say(f"    ordinary {normal:6.2f}  {normal_ev.summary()}")
    # review5 #2: redteam_rows now uses these disjoint seeds for both a new
    # attack search and unseen replay battles, with shifted coarse sides.
    hold = meta_scenarios(args.mode, 8, (21, 22, 23), angle_offset=math.pi / 8)
    own = own_levels()
    refs = []
    for f in [ROOT / "data/reference-bases/your-base.json"]:
        if f.exists():
            l = Layout.load(f)
            l.levels, l.wall_level, l.hero_levels = (
                dict(own["levels"]),
                own["wall_level"],
                dict(own["hero_levels"]),
            )
            l.name = "ref-" + f.stem
            refs.append(l)
    finalists = [l for l, _, _ in order[:5]] + refs
    say("== hold-out")
    ordinary = eval_many(finalists, hold, args.mode)
    gated = eval_many(finalists, hold, args.mode, redteam=True)
    ranked = sorted(zip(finalists, gated, ordinary), key=lambda row: -row[1][0])
    rows = []
    winner_saved = False
    for l, (s, ev), (normal, normal_ev) in ranked:
        say(f"  {l.name:22s} red-team {s:6.2f}  {ev.summary()}")
        say(f"    ordinary {normal:6.2f}  {normal_ev.summary()}")
        rows.append(
            {
                "name": l.name,
                "score": s,
                "summary": ev.summary(),
                "ordinary_score": normal,
                "ordinary_summary": normal_ev.summary(),
            }
        )
        if not l.name.startswith("ref-"):
            if not winner_saved:
                l.save(out / "best.json")
                winner_saved = True
            (out / f"{l.name}.json").write_text(json.dumps(l.to_json(), indent=1))
            try:
                render(l, out / f"{l.name}.png")
            except Exception as e:  # rendering is a convenience
                say(f"  (render failed: {e})")
    (out / "holdout.json").write_text(json.dumps(rows, indent=1))
    engine_end = batch_statistics()
    engine_usage = ""
    if os.environ.get("BASELAB_ENGINE") == "rust":
        engine_usage = (
            f" engine_battles_total={engine_end['battles'] - engine_start['battles']}"
            f" engine_calls={engine_end['calls'] - engine_start['calls']}"
        )
    say(
        f"done in {time.time() - t0:.0f}s search_battles_total={battles_total}"
        f" quick_battles_total={stage_totals['quick']}"
        f" confirm_battles_total={stage_totals['confirm']}"
        f"{engine_usage}"
    )


if __name__ == "__main__":
    main()
