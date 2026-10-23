"""Fit ranked-defense star and destruction distributions on historical layouts.

Loss = multinomial star negative log likelihood + n times the integrated
squared destruction-CDF error + a Gaussian prior on log strength correction.
The correction multiplies the current calibration, preserving build differences.
Families with fewer than --min-family defenses share a Town Hall pool.

Usage: python3 -B tools/baselab/calibrate_defenses.py --quick
Writes a flat meta-calibration file and a separate aggregate JSON report.
These defenses become training data; they cannot also prove replay accuracy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.evaluate import (  # noqa: E402
    STRENGTH,
    Scenario,
    defender_trophies,
    scouted,
    skill,
    summarise,
)
from baselab.layout import Layout  # noqa: E402
from baselab.meta_armies import (  # noqa: E402
    _share_troops,
    data,
    family_of,
    plan_for_build,
)
from calibrate_meta import calibration_provenance  # noqa: E402
from decode_battlelog import decode  # noqa: E402
from replay_log import to_build  # noqa: E402


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_id(build):
    return f"{build['archetype']}-{build['th']}-{build['build']}"


def current_strength(th, family):
    """Use this TH's current family calibration, then TH16, then raw stats."""
    for level in dict.fromkeys((th, 16)):
        values = [
            (STRENGTH["meta:" + build_id(b)], b.get("share", 1.0))
            for b in data()["builds"]
            if b["th"] == level
            and family_of(b) == family
            and "meta:" + build_id(b) in STRENGTH
        ]
        if values:
            total = sum(w for _, w in values)
            return math.exp(sum(w * math.log(v) for v, w in values) / total)
    fallback = {
        "dragon": "hydra",
        "thrower": "throwers",
        "electro-dragon": "edrag",
        "root-rider": "rootrider",
    }
    return STRENGTH.get(fallback.get(family), 1.0)


def observations(log, history, town_halls=None):
    """Read only ranked defenses; retain no player identifiers in the report."""
    periods = json.loads(history.read_text(encoding="utf-8"))["periods"]
    skipped = Counter()
    rows = []
    layouts = {}
    seen = set()
    for line in log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            battle = json.loads(line)
            if not isinstance(battle, dict):
                raise ValueError("not an object")
        except ValueError:
            skipped["invalid_json"] += 1
            continue
        if battle.get("battleType") != "ranked" or battle.get("attack") is not False:
            continue
        th = battle.get("opponentTownHallLevel")
        stars = battle.get("stars")
        pct = battle.get("destructionPercentage")
        try:
            timestamp = battle["battleTimestamp"]
            time_format = "%Y%m%dT%H%M%S.%fZ" if "." in timestamp else "%Y%m%dT%H%M%SZ"
            day = datetime.strptime(timestamp, time_format)
            if (
                type(th) is not int
                or not 1 <= th <= 18
                or type(stars) is not int
                or not 0 <= stars <= 3
                or type(pct) not in (int, float)
                or not math.isfinite(pct)
                or not 0 <= pct <= 100
                or (stars == 3) != (pct == 100)
            ):
                raise ValueError("invalid outcome")
        except (KeyError, TypeError, ValueError):
            skipped["invalid_outcome_or_timestamp"] += 1
            continue
        if town_halls and th not in town_halls:
            skipped["town_hall_filter"] += 1
            continue
        code = battle.get("armyShareCode") or ""
        if not isinstance(code, str):
            skipped["undecodable_army"] += 1
            continue
        identity = (battle["battleTimestamp"], th, code)
        if identity in seen:
            skipped["duplicate"] += 1
            continue
        seen.add(identity)
        matches = [
            p
            for p in periods
            if p["from"] <= day.date().isoformat()
            and (p.get("to") is None or day.date().isoformat() <= p["to"])
        ]
        if len(matches) != 1 or not matches[0].get("layout"):
            skipped["missing_or_ambiguous_history"] += 1
            continue
        period = matches[0]
        path = ROOT / period["layout"]
        if not path.is_file():
            skipped["missing_layout_file"] += 1
            continue
        if str(path) not in layouts:
            layout = Layout.load(path)
            # docs/GAP_ANALYSIS.md:45-48: never replace old levels with today's.
            if not layout.levels or not layout.hero_levels or not layout.wall_level:
                skipped["missing_historical_levels"] += 1
                continue
            layouts[str(path)] = layout.to_json()
        try:
            troops = _share_troops(code)
            build, unknown = to_build(decode(code), th, len(rows))
            unknown += [name for name in build.get("cc", {}) if "#" in name]
            if unknown:
                skipped["unknown_share_content:" + ",".join(sorted(unknown))] += 1
                continue
            family = family_of({"archetype": "observed", "troops": troops})
        except (KeyError, TypeError, ValueError):
            skipped["undecodable_army"] += 1
            continue
        league = str(battle.get("player_league", "")).lower()
        modifier = None
        if "legend" in league:
            suffix = league.split("legend", 1)[1].strip()
            modifier = {"i": "legend1", "ii": "legend2", "iii": "legend3"}.get(suffix)
            if modifier is None:
                skipped["unknown_league_modifier"] += 1
                continue
        rows.append(
            {
                "th": th,
                "family": family or "unclassified",
                "build": build,
                "layout": layouts[str(path)],
                "layout_path": period["layout"],
                "layout_sha256": file_hash(path),
                "history_confidence": str(period.get("confidence", "unspecified"))
                .split(":")[0]
                .split(" (")[0],
                "modifier": modifier,
                "stars": stars,
                "pct": float(pct),
            }
        )
    return rows, dict(skipped)


def grouped(rows, min_family):
    counts = Counter((r["th"], r["family"]) for r in rows)
    groups = defaultdict(list)
    for row in rows:
        family = row["family"]
        if family == "unclassified" or counts[row["th"], family] < min_family:
            family = "pooled"
        groups[row["th"], family].append(row)
    return dict(sorted(groups.items()))


def make_jobs(rows, correction, *, quick=False, angles=4, seeds=1):
    """All strengths reuse identical armies, angles and skill quantiles."""
    jobs = []
    for index, row in enumerate(rows):
        quantiles = (2,) if quick else range(5)
        for s in range(seeds):
            for q in quantiles:
                for k in range(angles):
                    seed = 5 * (1000 * index + s * angles + k) + q
                    scenario = Scenario(
                        army=f"observed:{index}",
                        town_hall=row["th"],
                        angle=0.21 + 2 * math.pi * k / angles,
                        seed=seed,
                        group=5 * s + q,
                        modifier=row["modifier"],
                        weight=1 / (len(rows) * seeds * len(quantiles) * angles),
                    )
                    strength = current_strength(row["th"], row["family"]) * correction
                    jobs.append((row, scenario, strength))
    return jobs


def job_plan(job):
    row, sc, strength = job
    plan = plan_for_build(row["build"], angle=sc.angle, seed=sc.seed)
    plan.observed = True
    plan.strength = strength * skill(sc.seed)
    return plan


class Runner:
    def __init__(self, engine):
        self.engine = engine
        self.used = Counter()
        self.fallbacks = Counter()

    def run(self, jobs):
        if self.engine != "python":
            try:
                results = self.rust(jobs)
                self.used["rust"] += len(jobs)
                return results
            except (OSError, RuntimeError) as error:
                # rust_bridge.run_jobs_file preserves explicit unsupported errors.
                self.fallbacks[type(error).__name__ + ": " + str(error)[:240]] += 1
                print(
                    "Rust jobs unavailable/unsupported; using Python for this bin.",
                    flush=True,
                )
        from baselab.engine.battle import Battle

        results = []
        for job in jobs:
            row, sc, _ = job
            layout = Layout.from_json(row["layout"])
            result = Battle(
                layout,
                job_plan(job),
                seed=sc.seed,
                town_hall=layout.town_hall,
                modifier=sc.modifier,
            ).run()
            results.append(
                (result.stars, result.destruction, result.th_destroyed, result.time)
            )
        self.used["python"] += len(jobs)
        return results

    @staticmethod
    def rust(jobs):
        from baselab.rust_bridge import plan_json, run_jobs_file

        layouts, indices, plans, entries = [], {}, [], []
        for job in jobs:
            row, sc, _ = job
            key = json.dumps(row["layout"], sort_keys=True)
            if key not in indices:
                indices[key] = len(layouts)
                layouts.append(row["layout"])
            plans.append(plan_json(job_plan(job)))
            entries.append(
                {
                    "layout": indices[key],
                    "plan": len(plans) - 1,
                    "seed": sc.seed,
                    "town_hall": row["layout"].get("town_hall", 16),
                    "modifier": sc.modifier,
                }
            )
        with tempfile.TemporaryDirectory(prefix="baselab-defense-") as tmp:
            path = Path(tmp) / "jobs.json"
            path.write_text(
                json.dumps({"layouts": layouts, "plans": plans, "jobs": entries})
            )
            results = run_jobs_file(path, threads=1)
        if len(results) != len(jobs):
            raise RuntimeError("Rust returned an incomplete job batch")
        return [
            (r["stars"], r["destruction"], r["th_destroyed"], r["time"])
            for r in results
        ]


def distribution(samples):
    """samples: (stars, percent, weight); retain their joint trophy outcome."""
    total = sum(w for _, _, w in samples)
    counts = [sum(w for s, _, w in samples if s == k) / total for k in range(4)]
    cdf = [sum(w for _, p, w in samples if p <= k) / total for k in range(100)]
    return {
        "star_probabilities": counts,
        "destruction_cdf_0_to_99": cdf,
        "mean_destruction": sum(w * p for _, p, w in samples) / total,
        "mean_defender_trophies": sum(
            w * defender_trophies(s, p) for s, p, w in samples
        )
        / total,
    }


def loss(observed, simulated, n, correction, prior_sd):
    # docs/GAP_ANALYSIS.md:34-40: score failures as well as the three-star rate.
    # Fixed 2% uniform mixing keeps multinomial log scores finite at small MC n.
    probabilities = [0.98 * p + 0.02 / 4 for p in simulated["star_probabilities"]]
    star_nll = -n * sum(
        p * math.log(q) for p, q in zip(observed["star_probabilities"], probabilities)
    )
    cdf_error = (
        n
        * sum(
            (p - q) ** 2
            for p, q in zip(
                observed["destruction_cdf_0_to_99"],
                simulated["destruction_cdf_0_to_99"],
            )
        )
        / 100
    )
    prior = 0.5 * (math.log(correction) / prior_sd) ** 2
    return {
        "star_nll": star_nll,
        "destruction_cdf": cdf_error,
        "prior": prior,
        "total": star_nll + cdf_error + prior,
    }


def weighted_quantile(values, weights, quantile):
    cumulative = 0.0
    for value, weight in zip(values, weights):
        cumulative += weight
        if cumulative >= quantile * sum(weights):
            return value
    return values[-1]


def fit(rows, runner, args):
    # Quick is a pipeline smoke check: one observed army and median skill per bin.
    selected = rows[:1] if args.quick else rows
    angles = 2 if args.quick else args.angles
    seeds = 1 if args.quick else args.seeds
    grid_size = 3 if args.quick else args.grid
    log_limit = math.log(args.max_correction)
    corrections = [
        math.exp(-log_limit + 2 * log_limit * i / (grid_size - 1))
        for i in range(grid_size)
    ]
    observed = distribution([(r["stars"], r["pct"], 1.0) for r in rows])
    effective_n = len(selected)
    candidates = []
    for correction in corrections:
        jobs = make_jobs(
            selected, correction, quick=args.quick, angles=angles, seeds=seeds
        )
        results = runner.run(jobs)
        scenarios = [sc for _, sc, _ in jobs]
        samples = [(r[0], r[1], w) for _, r, w in scouted(scenarios, results)]
        simulated = distribution(samples)
        evaluation = summarise(scenarios, results)
        if not math.isclose(
            evaluation.ranked_trophies,
            simulated["mean_defender_trophies"],
            abs_tol=1e-9,
        ):
            raise ValueError("Distribution and evaluate.summarise disagree")
        objective = loss(observed, simulated, effective_n, correction, args.prior_sd)
        candidates.append(
            {"correction": correction, "loss": objective, "simulated": simulated}
        )
        print(
            f"  correction {correction:.3f}: {len(jobs)} battles; "
            f"loss {objective['total']:.3f}, "
            f"defender trophies {simulated['mean_defender_trophies']:.2f}",
            flush=True,
        )
    best = min(
        candidates, key=lambda c: (c["loss"]["total"], abs(math.log(c["correction"])))
    )
    weights = [math.exp(best["loss"]["total"] - c["loss"]["total"]) for c in candidates]
    interval = [weighted_quantile(corrections, weights, q) for q in (0.025, 0.975)]
    return {
        "n": len(rows),
        "simulated_armies": len(selected),
        "fit_effective_n": effective_n,
        "family_counts": dict(sorted(Counter(r["family"] for r in rows).items())),
        "observed": observed,
        "baseline": candidates[grid_size // 2]["simulated"],
        "fitted": best["simulated"],
        "correction": best["correction"],
        "correction_interval_95": interval,
        "uncertainty": "approximate discrete generalized posterior on the tested log grid; conditional on engine, layouts and prior",
        "star_probability_se_upper_bound": 0.5 / math.sqrt(len(rows)),
        "destruction_cdf_dkw_95_half_width": min(
            1.0, math.sqrt(math.log(40) / (2 * len(rows)))
        ),
        "constraint": (
            "weak: fewer than 40 real defenses"
            if len(rows) < 40
            else "conditional on model and historical layout accuracy"
        ),
        "grid_boundary": best in (candidates[0], candidates[-1]),
        "grid": candidates,
        "layouts": [
            dict(
                path=path,
                sha256=next(
                    r["layout_sha256"] for r in rows if r["layout_path"] == path
                ),
                n=sum(r["layout_path"] == path for r in rows),
                confidence=sorted(
                    {r["history_confidence"] for r in rows if r["layout_path"] == path}
                ),
            )
            for path in sorted({r["layout_path"] for r in rows})
        ],
    }


def calibration_rows(groups, fits, quick, provenance):
    out = {}
    for build in data()["builds"]:
        bid = build_id(build)
        family = family_of(build)
        key = (build["th"], family)
        if key not in groups:
            key = (build["th"], "pooled")
        fitted = fits.get(key)
        correction = fitted["correction"] if fitted else 1.0
        strength = STRENGTH.get("meta:" + bid, 1.0)
        family_n = fitted["family_counts"].get(family, 0) if fitted else 0
        out[bid] = {
            "strength": strength * correction,
            "real": build["three_star"],
            "real_source": "TrophyCoach same-TH rate; not the defense fit target",
            "prior_strength": strength,
            "correction": correction,
            "defense_group": f"TH{key[0]}:{key[1]}" if fitted else None,
            "n": fitted["n"] if fitted else 0,
            "family_n": family_n,
            "uncalibrated": quick or fitted is None or family_n == 0,
            "weakly_constrained": fitted is None or fitted["n"] < 40,
            "dry_run": quick,
            "provenance": provenance,
        }
    # Keep unsaved observed families visible without inventing saved army builds.
    for key, fitted in fits.items():
        out[f"defense-th{key[0]}-{key[1]}"] = {
            "strength": fitted["correction"],
            "strength_kind": "correction to each family's current strength",
            "n": fitted["n"],
            "correction_interval_95": fitted["correction_interval_95"],
            "uncalibrated": quick,
            "dry_run": quick,
            "provenance": provenance,
        }
    return out


def town_hall_summaries(rows, fits):
    summaries = {}
    for th in sorted({r["th"] for r in rows}):
        matching = [r for r in rows if r["th"] == th]
        summary = {
            "n": len(matching),
            "observed": distribution([(r["stars"], r["pct"], 1.0) for r in matching]),
        }
        for stage in ("baseline", "fitted"):
            combined = {}
            for (level, _), fitted in fits.items():
                if level != th:
                    continue
                weight = fitted["n"] / len(matching)
                for key, value in fitted[stage].items():
                    if isinstance(value, list):
                        previous = combined.setdefault(key, [0.0] * len(value))
                        combined[key] = [
                            a + weight * b for a, b in zip(previous, value)
                        ]
                    else:
                        combined[key] = combined.get(key, 0.0) + weight * value
            summary[stage] = combined
        summaries[th] = summary
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=ROOT / "data/live/battles.jsonl")
    parser.add_argument(
        "--history", type=Path, default=ROOT / "data/live/base-history.json"
    )
    parser.add_argument(
        "--out", type=Path, default=ROOT / "data/meta-calibration-defenses.json"
    )
    parser.add_argument(
        "--report", type=Path, help="default: report-OUT.json beside OUT"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="dry run: six battles per bin, one army, median skill; never a validated calibration",
    )
    parser.add_argument(
        "--town-hall",
        type=int,
        action="append",
        help="optionally restrict attacker TH; repeatable",
    )
    parser.add_argument("--min-family", type=int, default=8)
    parser.add_argument("--angles", type=int, default=4)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument(
        "--grid", type=int, default=9, help="odd number of log-spaced corrections"
    )
    parser.add_argument("--max-correction", type=float, default=1.5)
    parser.add_argument(
        "--prior-sd",
        type=float,
        default=0.2,
        help="prior standard deviation of log correction",
    )
    parser.add_argument(
        "--engine",
        choices=("auto", "python", "rust"),
        default=os.environ.get("BASELAB_ENGINE", "auto"),
    )
    args = parser.parse_args()
    if (
        args.angles < 2
        or args.seeds < 1
        or args.min_family < 2
        or args.grid < 3
        or args.grid % 2 != 1
    ):
        parser.error("need angles >=2, seeds >=1, min-family >=2 and an odd grid >=3")
    if (
        not math.isfinite(args.prior_sd)
        or args.prior_sd <= 0
        or not math.isfinite(args.max_correction)
        or args.max_correction <= 1
    ):
        parser.error("prior-sd must be positive and max-correction must exceed one")
    # data_manifest.py:33 scans meta-calibration*.json as calibration mappings.
    report_path = args.report or args.out.with_name("report-" + args.out.name)
    if args.out.resolve() in {
        args.log.resolve(),
        args.history.resolve(),
        report_path.resolve(),
    }:
        parser.error("calibration, report and inputs must have distinct paths")
    if report_path.resolve() in {args.log.resolve(), args.history.resolve()}:
        parser.error("report cannot overwrite an input")
    provenance = calibration_provenance("rust" if args.engine != "python" else "python")
    input_hashes = {
        "battle_log_sha256": file_hash(args.log),
        "history_sha256": file_hash(args.history),
    }
    rows, skipped = observations(args.log, args.history, args.town_hall)
    groups = grouped(rows, args.min_family)
    if not groups:
        parser.error(f"no usable ranked defenses: {skipped}")
    runner = Runner(args.engine)
    fits = {}
    for key, group in groups.items():
        print(
            f"TH{key[0]} {key[1]}: n={len(group)}; fitting distributions"
            + (" (QUICK DRY RUN)" if args.quick else ""),
            flush=True,
        )
        fits[key] = fit(group, runner, args)
        result = fits[key]
        before, after = (
            result["baseline"]["mean_defender_trophies"],
            result["fitted"]["mean_defender_trophies"],
        )
        print(
            f"  correction {result['correction']:.3f}; 95% grid interval {result['correction_interval_95']}; defender trophies {before:.2f} -> {after:.2f}; real {result['observed']['mean_defender_trophies']:.2f}",
            flush=True,
        )
    final_provenance = calibration_provenance(
        "rust" if args.engine != "python" else "python"
    )
    provenance["engine"] = final_provenance["engine"] = "+".join(sorted(runner.used))
    inputs_changed = input_hashes != {
        "battle_log_sha256": file_hash(args.log),
        "history_sha256": file_hash(args.history),
    }
    layouts_changed = any(
        file_hash(ROOT / r["layout_path"]) != r["layout_sha256"] for r in rows
    )
    report = {
        "dry_run": args.quick,
        "validation_status": "training fit only; requires fresh held-out defenses",
        "loss": "multinomial star NLL (98% simulated + 2% uniform) + n * mean squared destruction CDF difference on 0..99% + 0.5*(log(correction)/prior_sd)^2",
        "prior_sd": args.prior_sd,
        "pooling": f"families with n < {args.min_family} share their actual TH pool; no TH15 -> TH16 folding",
        "quick_limitations": (
            "one army/bin, two angles, median skill, three corrections; effective fit n=1"
            if args.quick
            else None
        ),
        "attacker_levels": "Town Hall maximum; share codes do not encode researched levels",
        "scouting": "evaluate.scouted and summarise; no technique search",
        "skipped": skipped,
        "n": len(rows),
        "inputs": input_hashes,
        "provenance": provenance,
        "final_provenance": final_provenance,
        "inputs_changed_during_run": provenance != final_provenance
        or inputs_changed
        or layouts_changed,
        "engine_battles": dict(runner.used),
        "engine_fallbacks": dict(runner.fallbacks),
        "groups": {f"TH{th}:{family}": value for (th, family), value in fits.items()},
        "by_town_hall": town_hall_summaries(rows, fits),
    }
    out = calibration_rows(groups, fits, args.quick, provenance)
    for row in out.values():
        row["inputs_changed_during_run"] = report["inputs_changed_during_run"]
        if report["inputs_changed_during_run"]:
            row["uncalibrated"] = True
    args.out.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"saved {args.out}; report {report_path}", flush=True)


if __name__ == "__main__":
    main()
