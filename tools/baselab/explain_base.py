"""Explain a layout with held-out Rust battles, Python traces and paired tests.

Usage: python tools/baselab/explain_base.py LAYOUT.json [--ref BASE.json]
       [--out output/explain/NAME] [--angles 2] [--seeds 3]

Red-team searches require --proof-tests-passed. Legacy --out FILE.md still works.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab import evaluate as scoring  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.mechanics import BUILDING_TYPES, MARGIN, TRAP_NAMES, VILLAGE  # noqa: E402
from baselab.uncertainty import paired_comparison  # noqa: E402

KEY_DEFENSES = {"eagle", "inferno", "ad", "scatter", "xbow", "mono", "th"}
# evaluate.py:meta_scenarios: changing the seed alone retains the search angles.
HOLDOUT_ANGLE_OFFSET = 0.137
# engine/defense.py:558-588,697: None means ground X-Bow, single Inferno, Rage.
MODE_CHOICES = {
    "st": ("rage", "poison", "invis"),
    "xbow": ("ground", "both"),
    "inferno": ("single", "multi"),
}


def building_label(building):
    return f"{BUILDING_TYPES[building.key].name} ({building.x}, {building.y})"


def source_name(source):
    if source in BUILDING_TYPES:
        return BUILDING_TYPES[source].name
    if source.startswith("trap:"):
        return TRAP_NAMES.get(source[5:], source)
    return source


def central_distance(building):
    return math.hypot(
        building.x + building.size / 2 - VILLAGE / 2,
        building.y + building.size / 2 - VILLAGE / 2,
    )


def far_swap(lay, key, center_too=False):
    """Preserve the old importable helper for existing callers."""
    new = lay.copy()
    used = set()
    for building in (b for b in new.buildings if b.key == key):
        candidates = [
            (index, other)
            for index, other in enumerate(new.buildings)
            if other.size == building.size
            and other.key not in (key, "th")
            and BUILDING_TYPES[other.key].kind != "defense"
            and index not in used
        ]
        if not candidates:
            continue
        if center_too:
            index, other = min(candidates, key=lambda row: central_distance(row[1]))
        else:
            index, other = max(
                candidates,
                key=lambda row: math.hypot(
                    row[1].x - building.x, row[1].y - building.y
                ),
            )
        used.add(index)
        building.x, other.x = other.x, building.x
        building.y, other.y = other.y, building.y
    return new


def flip_infernos(lay, mode):
    new = lay.copy()
    for building in new.buildings:
        if building.key == "inferno":
            building.mode = mode
    return new


def feature_variants(base, reference, seed):
    """One intervention per variant; leave both input layouts untouched."""
    variants, skipped = [], []
    for index, building in enumerate(base.buildings):
        if building.key == "eagle":
            candidates = [
                (other_index, other)
                for other_index, other in enumerate(base.buildings)
                if other.size == building.size
                and BUILDING_TYPES[other.key].kind not in ("defense", "townhall")
            ]
            label = "Eagle moved to most central same-size non-defense slot"
            if not candidates:
                skipped.append(dict(change=label, reason="No legal swap partner"))
            else:
                other_index, other = min(
                    candidates, key=lambda row: (central_distance(row[1]), row[0])
                )
                if central_distance(other) >= central_distance(building):
                    skipped.append(
                        dict(
                            change=label, reason="Eagle is already at least as central"
                        )
                    )
                else:
                    variant = base.copy()
                    eagle, partner = (
                        variant.buildings[index],
                        variant.buildings[other_index],
                    )
                    eagle.x, partner.x = partner.x, eagle.x
                    eagle.y, partner.y = partner.y, eagle.y
                    variants.append(
                        (f"{label}; swap with {building_label(other)}", variant)
                    )
        if building.key not in MODE_CHOICES:
            continue
        choices = MODE_CHOICES[building.key]
        if building.key == "st":
            from baselab.engine import stats

            level = base.levels.get("st") or stats.max_level(
                "Spell Tower", base.town_hall
            )
            choices = tuple(
                mode for unlock, mode in enumerate(choices, 1) if level >= unlock
            )
            if base.town_hall >= 17 and level >= 4:
                choices += ("eq",)
        current = building.mode or MODE_CHOICES[building.key][0]
        if current in ("quake", "earthquake"):
            current = "eq"
        for mode in choices:
            if mode == current:
                continue
            variant = base.copy()
            variant.buildings[index].mode = mode
            variants.append(
                (f"{building_label(building)}: {current} → {mode}", variant)
            )
    label = "Clan Castle troops replaced by reference's"
    if base.cc_troops == reference.cc_troops:
        skipped.append(
            dict(change=label, reason="Identical troop composition (zero change)")
        )
    else:
        variant = base.copy()
        variant.cc_troops = list(reference.cc_troops)
        variants.append((label, variant))
    for key in sorted({trap.key for trap in base.traps}):
        variant = base.copy()
        moving = [trap for trap in variant.traps if trap.key == key]
        # layout.py:occupancy/problems: trap footprints cannot overlap any object.
        occupied = set(variant.walls)
        for item in variant.buildings + [
            trap for trap in variant.traps if trap.key != key
        ]:
            occupied.update(item.tiles())
        rng = random.Random(f"explain:{seed}:{key}")
        relocated = 0
        for trap in moving:
            candidates = []
            for x in range(VILLAGE - trap.size + 1):
                for y in range(VILLAGE - trap.size + 1):
                    tiles = {
                        (x + dx, y + dy)
                        for dx in range(trap.size)
                        for dy in range(trap.size)
                    }
                    if (x, y) != (trap.x, trap.y) and not occupied.intersection(tiles):
                        candidates.append((x, y))
            if not candidates:
                break
            trap.x, trap.y = rng.choice(candidates)
            occupied.update(trap.tiles())
            relocated += 1
        label = f"All {TRAP_NAMES[key]} relocated (seed {seed})"
        if relocated != len(moving):
            skipped.append(dict(change=label, reason="No complete legal relocation"))
        else:
            variants.append((label, variant))
    return variants, skipped


def army_family(army):
    from baselab.meta_armies import build_by_id, family_of

    build = build_by_id(army[5:] if army.startswith("meta:") else army)
    return family_of(build) or build["archetype"]


def bulk_battles(layout, scenarios):
    layout_json = layout.to_json()
    jobs = [(layout_json, sc, scoring.STRENGTH.get(sc.army, 1.0)) for sc in scenarios]
    results = [tuple(row) for row in scoring.run_batch(jobs, parallel=True)]
    if len(results) != len(scenarios):
        raise ValueError("Rust returned a different number of battles than requested")
    return results


def family_breakdown(scenarios, results):
    rows = defaultdict(lambda: Counter(share=0.0, three=0.0, pct=0.0, trophies=0.0))
    total = sum(sc.weight for sc in scenarios)
    if results is None:
        for scenario in scenarios:
            rows[(army_family(scenario.army), scenario.town_hall)]["share"] += (
                scenario.weight / total
            )
        return [
            dict(
                family=family,
                attacker_th=th,
                share=row["share"],
                three=None,
                pct=None,
                trophies=None,
            )
            for (family, th), row in sorted(rows.items())
        ]
    # evaluate.py:scouted/summarise: retain the scorer's side-selection weights.
    for scenario, result, weight in scoring.scouted(scenarios, results):
        row = rows[(army_family(scenario.army), scenario.town_hall)]
        row["share"] += weight / total
        row["three"] += weight / total * (result[0] >= 3)
        row["pct"] += weight / total * result[1]
        row["trophies"] += (
            weight / total * scoring.defender_trophies(result[0], result[1])
        )
    return [
        dict(
            family=family,
            attacker_th=th,
            share=row["share"],
            **{key: row[key] / row["share"] for key in ("three", "pct", "trophies")},
        )
        for (family, th), row in sorted(rows.items())
    ]


def representative_scenarios(scenarios, results):
    families = defaultdict(list)
    for scenario, result, weight in scoring.scouted(scenarios, results):
        families[army_family(scenario.army)].append((scenario, result, weight))
    total = sum(sc.weight for sc in scenarios)
    for family, rows in sorted(families.items()):
        mass = sum(row[2] for row in rows)
        if mass / total < 0.05 - 1e-12:
            continue
        # docs/GOAL.md:5: select only among held-out outcomes, never training seeds.
        rows.sort(
            key=lambda row: (
                scoring.attacker_trophies(row[1][0], row[1][1]),
                row[1][1],
                row[1][0],
                row[0].army,
                row[0].seed,
                row[0].angle,
            )
        )
        accumulated = 0.0
        for scenario, result, weight in rows:
            accumulated += weight
            if accumulated >= mass / 2 - 1e-12:
                yield family, mass / total, scenario, result
                break


def trace_battle(layout, scenario, bulk_result):
    from baselab.engine.battle import Battle
    from baselab.engine.entities import Building
    from baselab.meta_armies import make_plan

    plan = make_plan(scenario.army, scenario.angle, scenario.town_hall, scenario.seed)
    if scenario.tactic is not None:
        from baselab.tactics import apply

        apply(plan, scenario.tactic)
    if scenario.charge is not None:
        scoring.apply_charge(plan, scenario.charge)
    plan.strength = scoring.STRENGTH.get(scenario.army, 1.0) * scoring.skill(
        scenario.seed
    )
    battle = Battle(
        layout,
        plan,
        seed=scenario.seed,
        town_hall=layout.town_hall,
        modifier=scenario.modifier,
        record=True,
    )
    sources = {}
    explicit_actor = None

    def source_row(source, actor=None):
        if actor is None:
            actor = explicit_actor if explicit_actor is not None else battle._src_obj
        if isinstance(actor, Building):
            identity = f"building:{actor.id}"
            label, kind = building_label(layout.buildings[actor.id]), actor.key
        else:
            identity, kind = f"unattributed:{source}", str(source)
            label = f"{source_name(kind)} (individual origin unavailable)"
        return sources.setdefault(
            identity,
            dict(
                id=identity, label=label, type=kind, damage=0.0, kills=0, kill_housing=0
            ),
        )

    class ObservedCounter(dict):
        def __init__(self, metric):
            super().__init__()
            self.metric = metric

        def __setitem__(self, source, value):
            delta = value - self.get(source, 0)
            if delta > 0:
                row = source_row(source)
                row[self.metric] += delta
                if self.metric == "kill_housing":
                    row["kills"] += 1
            super().__setitem__(source, value)

    # engine/battle.py:653-654,690-693: kills_by_source measures housing, not heads.
    battle.damage_by_source = ObservedCounter("damage")
    battle.kills_by_source = ObservedCounter("kill_housing")
    for building in battle.buildings:
        if building.is_defense or building.key == "th":
            source_row(building.key, building)
    for key in sorted({trap.key for trap in layout.traps}):
        source_row("trap:" + key)
    destroyed, hero_deaths, trap_events, star_times = [], [], [], {}
    original_destroy, original_kill, original_step = (
        battle.destroy,
        battle.kill,
        battle.step,
    )
    original_hit = battle.hit_unit

    def observe_hit(unit, amount, **kwargs):
        nonlocal explicit_actor
        previous = explicit_actor
        explicit_actor = kwargs.get("attacker") or battle._src_obj
        try:
            return original_hit(unit, amount, **kwargs)
        finally:
            explicit_actor = previous

    def observe_destroy(building):
        was_alive = building.alive
        original_destroy(building)
        if was_alive and not building.alive and isinstance(building, Building):
            destroyed.append(
                dict(
                    time=round(battle.t, 1),
                    key=building.key,
                    label=building_label(layout.buildings[building.id]),
                )
            )

    def observe_kill(unit):
        was_alive = unit.alive
        position = [round(unit.x - MARGIN, 2), round(unit.y - MARGIN, 2)]
        original_kill(unit)
        if was_alive and not unit.alive and unit.is_hero and unit.team == "atk":
            hero_deaths.append(
                dict(time=round(battle.t, 1), hero=unit.name, position=position)
            )

    def observe_step():
        before = [trap.fuse_at for trap in battle.traps]
        tick = round(battle.t, 1)
        original_step()
        for index, (previous, trap) in enumerate(zip(before, battle.traps)):
            if previous < 0 <= trap.fuse_at:
                placement = layout.traps[index]
                trap_events.append(
                    dict(
                        time=tick,
                        key=trap.key,
                        label=f"{trap.name} ({placement.x}, {placement.y})",
                    )
                )
        for star in range(1, battle.stars() + 1):
            star_times.setdefault(str(star), tick)

    battle.destroy, battle.kill, battle.step = (
        observe_destroy,
        observe_kill,
        observe_step,
    )
    battle.hit_unit = observe_hit
    result = battle.run()
    outcome = (result.stars, result.destruction, result.th_destroyed, result.time)
    checkpoints = {}
    for second in (30, 60, 90):
        values = [
            entry[3]
            for entry in battle.log
            if entry[1] == "destroyed" and entry[0] <= second
        ]
        checkpoints[str(second)] = max(values, default=0.0)
    if result.stars >= 3:
        end_reason = "3-star"
    elif battle.t >= battle.max_time:
        end_reason = "timeout"
    elif battle.offense_finished():
        end_reason = "units exhausted"
    else:
        end_reason = "battle ended by plan"
    angle = math.degrees(scenario.angle) % 360
    sides = ("x+", "x+/y+", "y+", "x-/y+", "x-", "x-/y-", "y-", "x+/y-")
    first_drop = next((entry for entry in battle.log if entry[1] == "deploy"), None)
    return dict(
        scenario=asdict(scenario),
        bulk_result=bulk_result,
        python_result=outcome,
        parity=all(
            abs(float(a) - float(b)) < 1e-6 for a, b in zip(outcome, bulk_result)
        ),
        entry_angle_degrees=angle,
        entry_side=sides[int((angle + 22.5) // 45) % 8],
        first_drop=(
            dict(
                time=first_drop[0],
                unit=first_drop[2],
                position=[round(v - MARGIN, 1) for v in first_drop[3:5]],
            )
            if first_drop
            else None
        ),
        key_defenses_destroyed=sorted(
            (event for event in destroyed if event["key"] in KEY_DEFENSES),
            key=lambda event: (event["time"], event["label"]),
        ),
        key_defenses_surviving=[
            building_label(layout.buildings[b.id])
            for b in battle.buildings
            if b.alive and b.key in KEY_DEFENSES
        ],
        destruction_at_seconds=checkpoints,
        star_times=star_times,
        hero_deaths=hero_deaths,
        end_reason=end_reason,
        offensive_units_alive=sum(
            unit.alive
            and unit.name not in ("Healer", "Unicorn", "Totem")
            and unit.kind != "siege_idle"
            for unit in battle.attackers
        ),
        spells_left={
            key: count for key, count in getattr(plan, "spells", {}).items() if count
        },
        trap_positions=[
            f"{TRAP_NAMES[trap.key]} ({trap.x}, {trap.y})" for trap in layout.traps
        ],
        sources=list(sources.values()),
        trap_triggers=trap_events,
        damage_by_source=dict(battle.damage_by_source),
        kill_housing_by_source=dict(battle.kills_by_source),
        log=battle.log,
    )


def contribution_totals(traces):
    individuals, types, traps = {}, {}, Counter()
    for trace in traces:
        for label in trace["trap_positions"]:
            traps.setdefault(label, 0)
        for source in trace["sources"]:
            for target, key, label in (
                (individuals, source["id"], source["label"]),
                (types, source["type"], source_name(source["type"])),
            ):
                row = target.setdefault(
                    key, dict(label=label, damage=0.0, kills=0, kill_housing=0)
                )
                for metric in ("damage", "kills", "kill_housing"):
                    row[metric] += source[metric]
        traps.update(event["label"] for event in trace["trap_triggers"])

    def order(row):
        return -row["damage"], -row["kills"], row["label"]

    return dict(
        per_type=sorted(types.values(), key=order),
        per_individual=sorted(individuals.values(), key=order),
        trap_triggers=dict(sorted(traps.items())),
    )


def compare(scenarios, results_a, results_b, args):
    comparison = paired_comparison(
        scenarios,
        results_a,
        results_b,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.random_seed,
    )
    return {**asdict(comparison), "practical_tie": comparison.practical_tie}


def file_evidence(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def build_report(args):
    base, reference = Layout.load(args.base), Layout.load(args.ref)
    own = json.loads((ROOT / "data/your-levels.json").read_text(encoding="utf-8"))
    for layout in (base, reference):
        if layout.town_hall == 16:
            layout.levels = {**own["levels"], **layout.levels}
            layout.hero_levels = {**own["hero_levels"], **layout.hero_levels}
            if layout.wall_level is None:
                layout.wall_level = own["wall_level"]
    seeds = tuple(range(args.seed_start, args.seed_start + args.seeds))
    # evaluate.py:19-23,meta_scenarios: use fresh groups and shift the entry angles.
    scenarios = scoring.meta_scenarios(
        "ranked", args.angles, seeds, angle_offset=HOLDOUT_ANGLE_OFFSET
    )
    calibration = Path(
        os.environ.get("BASELAB_CALIBRATION") or ROOT / "data/meta-calibration-r8.json"
    )
    inputs = [
        args.base,
        args.ref,
        ROOT / "data/your-levels.json",
        calibration,
        ROOT / "data/baselab-calibration.json",
        ROOT / "data/attacker-policy.json",
        ROOT / "data/meta-armies-2026-10-15.json",
        ROOT / "data/observed-armies.json",
        ROOT / "data/registry.json",
        Path(__file__),
    ]
    inputs += sorted((ROOT / "data/playbooks").glob("*.json"))
    inputs += [
        ROOT / "src/baselab" / name
        for name in ("evaluate.py", "meta_armies.py", "redteam.py", "uncertainty.py")
    ]
    report = dict(
        schema_version=1,
        status="complete",
        base=base.to_json(),
        reference=reference.to_json(),
        settings=dict(
            bulk_engine="rust",
            trace_engine="python",
            playbooks=True,
            calibration=str(calibration.resolve()),
            seed_groups=seeds,
            angles=args.angles,
            angle_offset=HOLDOUT_ANGLE_OFFSET,
            random_seed=args.random_seed,
            bootstrap_samples=args.bootstrap_samples,
            proof_tests_passed=args.proof_tests_passed,
        ),
        inputs=[file_evidence(path) for path in inputs if Path(path).exists()],
        mix=dict(scoring.META_MIX_INFO),
        strengths={sc.army: scoring.STRENGTH.get(sc.army, 1.0) for sc in scenarios},
        scenarios=[asdict(sc) for sc in scenarios],
        counts=dict(
            scenarios_per_layout=len(scenarios),
            rust_completed=0,
            python_traces=0,
            feature_variants=0,
            redteam_battles=0,
        ),
        errors=[],
        family_breakdown=[],
        traces=[],
        feature_tests=[],
        redteam=[],
    )
    from baselab.rust_bridge import batch_statistics, engine_executable

    starting_battles = batch_statistics()["battles"]
    executable = engine_executable()
    report["engine_executable"] = (
        file_evidence(executable)
        if executable.is_file()
        else dict(path=str(executable), missing=True)
    )

    def failed(section, error):
        report["status"] = "incomplete"
        report["errors"].append(
            dict(section=section, reason=f"{type(error).__name__}: {error}")
        )

    variants, skipped = feature_variants(base, reference, args.random_seed)
    report["skipped_feature_tests"] = skipped
    report["planned_feature_tests"] = [label for label, _variant in variants]
    base_results = ref_results = None
    for label, layout in (("base", base), ("reference", reference)):
        try:
            print(
                f"{label}: {len(scenarios)} held-out Rust battles",
                file=sys.stderr,
                flush=True,
            )
            results = bulk_battles(layout, scenarios)
            report[f"{label}_results"] = results
            report[f"{label}_summary"] = asdict(scoring.summarise(scenarios, results))
            if label == "base":
                base_results = results
            else:
                ref_results = results
        except (OSError, RuntimeError, ValueError, ImportError) as error:
            failed(label, error)
    refs = {
        (row["family"], row["attacker_th"]): row
        for row in family_breakdown(scenarios, ref_results)
    }
    report["family_breakdown"] = [
        dict(base=row, reference=refs[(row["family"], row["attacker_th"])])
        for row in family_breakdown(scenarios, base_results)
    ]
    if base_results is not None and ref_results is not None:
        report["comparison"] = compare(scenarios, base_results, ref_results, args)
    if base_results is not None:
        for family, share, scenario, bulk_result in representative_scenarios(
            scenarios, base_results
        ):
            try:
                print(
                    f"trace: {family}, seed {scenario.seed}",
                    file=sys.stderr,
                    flush=True,
                )
                trace = trace_battle(base, scenario, bulk_result)
                report["traces"].append(dict(family=family, share=share, **trace))
                report["counts"]["python_traces"] += 1
                if not trace["parity"]:
                    failed(
                        f"trace {family}",
                        ValueError("Python and Rust outcomes differ; inspect trace"),
                    )
            except (OSError, RuntimeError, ValueError, ImportError) as error:
                failed(f"trace {family}", error)
        for label, variant in variants:
            try:
                issues = variant.problems(require_full=False)
                if issues:
                    raise ValueError(
                        "Intervention creates an invalid layout: "
                        + "; ".join(issues[:3])
                    )
                print(f"feature: {label}", file=sys.stderr, flush=True)
                results = bulk_battles(variant, scenarios)
                report["counts"]["feature_variants"] += 1
                report["feature_tests"].append(
                    dict(
                        change=label,
                        comparison=compare(scenarios, results, base_results, args),
                        layout=variant.to_json(),
                        results=results,
                    )
                )
            except (OSError, RuntimeError, ValueError, ImportError) as error:
                failed(f"feature {label}", error)
    report["contributions"] = contribution_totals(report["traces"])
    if args.proof_tests_passed and base_results is not None:
        from baselab.redteam import Budget, redteam

        # docs/GAP_ANALYSIS.md:74-80: test attacks within the cited playbook only.
        budget = Budget(
            sides=4,
            coarse_seeds=5,
            halving=((2, 5),),
            refine_seeds=5,
            fresh_seeds=5,
            max_battles=args.redteam_battles,
        )
        report["redteam_budget"] = asdict(budget)
        seed_start = 5 * (max(sc.seed for sc in scenarios) // 5 + 1001)
        search_seeds = tuple(range(seed_start, seed_start + 5))
        fresh_seeds = tuple(range(seed_start + 1000, seed_start + 1005))
        for army in sorted({sc.army for sc in scenarios}):
            try:
                result = redteam(
                    base,
                    army,
                    budget,
                    parallel=True,
                    # evaluate.py:STRENGTH: match the ordinary scoring arm.
                    strength=scoring.STRENGTH,
                    search_seeds=search_seeds,
                    fresh_seeds=fresh_seeds,
                )
                report["counts"]["redteam_battles"] += result.battles
                report["redteam"].append(
                    dict(
                        army=army,
                        family=army_family(army),
                        attack=result.attack.describe(),
                        search_attacker_trophies=result.search_trophies,
                        fresh_attacker_trophies=result.fresh_trophies,
                        three_star_rate=result.three_star,
                        destruction=result.pct,
                        fresh_results=result.fresh,
                        battles=result.battles,
                        log=result.log,
                        search_seeds=search_seeds,
                        fresh_seeds=fresh_seeds,
                    )
                )
            except (OSError, RuntimeError, ValueError, ImportError) as error:
                failed(f"redteam {army}", error)
    else:
        report["status"] = "incomplete"
        report["redteam_status"] = (
            "Not run: proof tests have not been confirmed passed (--proof-tests-passed)."
            if not args.proof_tests_passed
            else "Not run: base bulk battles failed."
        )
    report["counts"]["rust_completed"] = (
        batch_statistics()["battles"] - starting_battles
    )
    return report


def comparison_text(comparison):
    low, high = comparison["ci95"]
    verdict = (
        "practical tie" if comparison["practical_tie"] else "outside practical tie"
    )
    return f"{comparison['difference']:+.2f} [{low:+.2f}, {high:+.2f}]; {verdict}"


def table(lines, headers, rows):
    lines.extend(
        [
            "",
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
    )
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                str(value).replace("|", "\\|").replace("\n", " ") for value in row
            )
            + " |"
        )
    lines.append("")


def metric(value, spec, suffix=""):
    return "unavailable" if value is None else format(value, spec) + suffix


def markdown_report(report):
    lines = [
        f"# Why {report['base']['name']} holds or fails",
        "",
        f"Report status: **{report['status']}**. All outcomes are simulator estimates.",
        "",
        f"Reference: {report['reference']['name']}. Bulk engine: Rust; traces: Python; BASELAB_PLAYBOOKS=1.",
        f"Calibration: `{report['settings']['calibration']}`.",
        f"Hold-out seed groups: {report['settings']['seed_groups']}; {report['settings']['angles']} angles, "
        f"offset {math.degrees(report['settings']['angle_offset']):.2f}° from the scorer's unshifted sides.",
        "Exact scenarios, strengths, effective layouts, input hashes and battle results are in [report.json](report.json).",
        "Stored building/hero levels are preserved; missing TH16 fields use data/your-levels.json.",
    ]
    counts = report["counts"]
    lines += [
        "",
        f"Battles: {counts['scenarios_per_layout']} planned per bulk layout; {counts['rust_completed']} Rust completed "
        f"(including {counts['redteam_battles']} red-team battles), {counts['python_traces']} Python traces; "
        f"{counts['feature_variants']} feature variants completed.",
        "",
        "Intervals resample paired seed groups within the scorer's fixed strata; they measure simulation sampling, not real-game accuracy. "
        "One seed per stratum gives a degenerate interval. A practical tie includes ±0.25 trophies. "
        "These feature tests share the hold-out: any design selected from them needs a new independent evaluation.",
    ]
    if "comparison" in report:
        base, ref = report["base_summary"], report["reference_summary"]
        lines += [
            "",
            f"Expected defender trophies: **{base['ranked_trophies']:.2f} vs {ref['ranked_trophies']:.2f}**. "
            f"Base minus reference: {comparison_text(report['comparison'])} (95% interval).",
        ]
    if report["errors"]:
        lines += ["", "Incomplete sections:", ""]
        lines += [f"- {row['section']}: {row['reason']}" for row in report["errors"]]
    lines += [
        "",
        "## 1. Attacks in the ranked mix",
        "",
        f"Mix source: {report['mix'].get('source', 'see JSON')}. "
        "Family × attacker Town Hall shares include the scorer's scouting rule.",
        "Observed families absent from the saved mix: "
        + json.dumps(report["mix"].get("missing_families", {}), sort_keys=True)
        + ".",
    ]
    table(
        lines,
        [
            "Family",
            "Attacker TH",
            "Share",
            "Base 3★",
            "Ref 3★",
            "Base destruction",
            "Ref destruction",
            "Base trophies",
            "Ref trophies",
        ],
        [
            [
                row["base"]["family"],
                row["base"]["attacker_th"],
                f"{row['base']['share']:.1%}",
                metric(row["base"]["three"], ".1%"),
                metric(row["reference"]["three"], ".1%"),
                metric(row["base"]["pct"], ".1f", "%"),
                metric(row["reference"]["pct"], ".1f", "%"),
                metric(row["base"]["trophies"], ".2f"),
                metric(row["reference"]["trophies"], ".2f"),
            ]
            for row in report["family_breakdown"]
        ],
    )
    if not report["family_breakdown"]:
        lines += ["Unavailable: both base and reference bulk results are required.", ""]
    lines += [
        "## 2. Representative attacks",
        "",
        "One weighted median outcome per family with at least 5% total share, ordered by attacker trophies then destruction. "
        "The chosen build, TH, seed and side come from scored hold-out battles. Coordinates are village tiles (layout.py); "
        "x runs down-right and y down-left on the in-game diamond. Checkpoints carry final destruction after an early finish.",
        "",
    ]
    for trace in report["traces"]:
        scenario, outcome = trace["scenario"], trace["python_result"]
        lines += [
            f"### {trace['family']} ({trace['share']:.1%} share)",
            "",
            f"{scenario['army']}, attacker TH{scenario['town_hall']}, seed {scenario['seed']}. "
            f"Main entry {trace['entry_angle_degrees']:.1f}° ({trace['entry_side']}); "
            f"charge flank {'left' if scenario['seed'] % 2 == 0 else 'right'}.",
        ]
        if trace["first_drop"]:
            drop = trace["first_drop"]
            lines.append(
                f"First deployment: {drop['unit']} at {drop['position']} at {drop['time']:.1f}s."
            )
        lines += [
            f"Ended at {outcome[3]:.1f}s: **{outcome[0]}★, {outcome[1]:.1f}%, {trace['end_reason']}**. "
            f"Rust selection outcome: {trace['bulk_result']}; parity: **{trace['parity']}**.",
            f"At the end, {trace['offensive_units_alive']} offensive units were alive; "
            f"unused spells: {trace['spells_left']}. "
            "A timeout with no offensive units can reflect unspent spells or pending actions (engine/battle.py:offense_finished).",
            "Destruction: "
            + "; ".join(
                f"{second}s: {pct:.0f}%"
                for second, pct in trace["destruction_at_seconds"].items()
            )
            + ".",
            "Star times: "
            + (
                ", ".join(
                    f"{star}★ at {time:.1f}s"
                    for star, time in trace["star_times"].items()
                )
                or "none"
            )
            + ".",
        ]
        table(
            lines,
            ["Time", "Key defense destroyed"],
            [
                [f"{event['time']:.1f}s", event["label"]]
                for event in trace["key_defenses_destroyed"]
            ],
        )
        lines += [
            "Key defenses still standing: "
            + (", ".join(trace["key_defenses_surviving"]) or "none")
            + ".",
            "",
        ]
        for event in trace["hero_deaths"]:
            lines.append(
                f"- {event['hero']} died at {event['position']} at {event['time']:.1f}s."
            )
        if not trace["hero_deaths"]:
            lines.append("No attacking hero deaths recorded.")
        leaders = sorted(
            trace["sources"], key=lambda row: (-row["damage"], row["label"])
        )[:5]
        table(
            lines,
            ["Largest damage sources", "Damage", "Credited kills", "Kill housing"],
            [
                [
                    row["label"],
                    f"{row['damage']:.0f}",
                    row["kills"],
                    row["kill_housing"],
                ]
                for row in leaders
            ],
        )
        killers = sorted(
            trace["sources"],
            key=lambda row: (-row["kills"], -row["kill_housing"], row["label"]),
        )[:3]
        lines += [
            "Most credited kills: "
            + (
                "; ".join(
                    f"{row['label']}: {row['kills']} ({row['kill_housing']} housing)"
                    for row in killers
                    if row["kills"]
                )
                or "none"
            )
            + ".",
            "",
        ]
        actions = [
            entry
            for entry in trace["log"]
            if entry[1] in ("deploy", "ability", "spell", "spell_tower")
        ]
        table(
            lines,
            ["Time", "Attacker/Spell Tower action from log"],
            [
                [f"{entry[0]:.1f}s", " ".join(str(value) for value in entry[1:])]
                for entry in actions
            ],
        )
    if not report["traces"]:
        lines += ["Unavailable: no completed representative traces.", ""]
    lines += [
        "## 3. Defense contribution in the traced battles",
        "",
        "Totals across selected traces, without mixture weighting. These battles are descriptive, not a marginal-value estimate. "
        "Damage follows battle.damage_by_source; credited kills count increments in battle.kills_by_source and kill housing preserves its native units. "
        "Zero damage does not mean zero value (sweeping, freezing, tanking and pathing are indirect). "
        "Unattributed sources stay separate; trap damage is available by type, not individual trap.",
        "",
    ]
    contribution = report["contributions"]
    for key, title in (
        ("per_type", "Defense/source type"),
        ("per_individual", "Individual building/source"),
    ):
        table(
            lines,
            [title, "Damage", "Credited kills", "Kill housing"],
            [
                [
                    row["label"],
                    f"{row['damage']:.0f}",
                    row["kills"],
                    row["kill_housing"],
                ]
                for row in contribution[key]
            ],
        )
    table(
        lines,
        ["Trap position", "Triggers"],
        list(contribution["trap_triggers"].items()),
    )
    lines += [
        "## 4. Paired feature tests",
        "",
        "Each variant changes one feature of the base. Positive trophy change improves defense; "
        "negative change favors keeping the original feature. Intervals use src/baselab/uncertainty.py. "
        "Relocations are one deterministic draw per trap type, not optimized placements or an average over possible placements.",
    ]
    table(
        lines,
        ["Change", "Defender trophy change [95% interval]"],
        [
            [row["change"], comparison_text(row["comparison"])]
            for row in report["feature_tests"]
        ],
    )
    lines += [
        f"- {row['change']}: {row['reason']}."
        for row in report["skipped_feature_tests"]
    ]
    if not report["feature_tests"]:
        lines += [
            "",
            f"No feature battles completed; {len(report['planned_feature_tests'])} interventions planned (listed in JSON).",
        ]
    lines += [
        "",
        "## 5. Red-team attacks",
        "",
        "Best attack found per saved army within a small cited-playbook budget; entry/flank/tactic are fixed before fresh-seed replay. "
        "This is a bounded search, not proof of the strongest human attack.",
    ]
    if "redteam_status" in report:
        lines += ["", report["redteam_status"]]
    table(
        lines,
        [
            "Army",
            "Entry/flank/tactic",
            "Fresh 3★",
            "Fresh destruction",
            "Fresh attacker trophies",
            "Battles",
        ],
        [
            [
                row["army"],
                json.dumps(row["attack"], sort_keys=True),
                f"{row['three_star_rate']:.1%}",
                f"{row['destruction']:.1f}%",
                f"{row['fresh_attacker_trophies']:.2f}",
                row["battles"],
            ]
            for row in report["redteam"]
        ],
    )
    lines += [
        "## Reading the evidence",
        "",
        "A useful design claim needs both a traced mechanism and a paired trophy loss when that feature changes. "
        "A failed attack alone can reflect the playbook's funnel, targeting or timing limits. "
        "Check Python/Rust parity, calibration transfer, absent army families, scouting assumptions and timeout causes "
        "against docs/GAP_ANALYSIS.md before treating a gain as real-game strength. "
        "No real-game calibration or search ranking is changed by this report.",
        "",
    ]
    if "comparison" in report:
        largest = sorted(
            report["family_breakdown"],
            key=lambda row: -abs(
                row["base"]["share"]
                * (row["base"]["trophies"] - row["reference"]["trophies"])
            ),
        )[:3]
        for row in largest:
            base, reference = row["base"], row["reference"]
            contribution = base["share"] * (base["trophies"] - reference["trophies"])
            lines.append(
                f"- {base['family']} at TH{base['attacker_th']} contributes {contribution:+.2f} "
                "trophies to the overall base-minus-reference difference."
            )
    for row in sorted(
        report["feature_tests"], key=lambda row: row["comparison"]["difference"]
    )[:3]:
        comparison = row["comparison"]
        if comparison["difference"] < 0:
            lines.append(
                f"- Evidence for the existing design: intervention “{row['change']}” "
                f"changed defense by {comparison_text(comparison)} trophies. "
                "Use the trace timeline to check whether the inferred mechanism makes sense."
            )
    improvements = [
        row for row in report["feature_tests"] if row["comparison"]["difference"] > 0
    ]
    if improvements:
        row = max(improvements, key=lambda row: row["comparison"]["difference"])
        lines.append(
            f"- Largest tested improvement: {row['change']}: "
            f"{comparison_text(row['comparison'])} trophies; this exposes a weakness in the current design."
        )
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument(
        "--ref", type=Path, default=ROOT / "data/reference-bases/your-base.json"
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--angles", type=int, default=2)
    parser.add_argument(
        "--seeds", type=int, default=3, help="Number of fresh seed groups"
    )
    parser.add_argument("--seed-start", type=int, default=10001)
    parser.add_argument("--random-seed", type=int, default=271828)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument(
        "--proof-tests-passed",
        action="store_true",
        help="Confirm prerequisite proof tests passed; enable bounded red-team search",
    )
    parser.add_argument(
        "--redteam-battles",
        type=int,
        default=80,
        help="Search cap per army, plus five fresh battles (minimum 40)",
    )
    args = parser.parse_args()
    if min(args.angles, args.seeds, args.bootstrap_samples) < 1:
        parser.error("--angles, --seeds and --bootstrap-samples must be positive")
    if args.seed_start < 10001:
        parser.error(
            "--seed-start must be >=10001 to stay beyond search/selection seeds"
        )
    if args.redteam_battles < 40:
        parser.error(
            "--redteam-battles must be >=40 (four sides × two flanks × five seeds)"
        )
    os.environ["BASELAB_ENGINE"] = "rust"
    os.environ["BASELAB_PLAYBOOKS"] = "1"
    destination = args.out or ROOT / "output/explain" / args.base.stem
    if destination.suffix.lower() == ".md":
        markdown_path, json_path = destination, destination.with_suffix(".json")
    else:
        markdown_path, json_path = (
            destination / "report.md",
            destination / "report.json",
        )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(args)
    json_path.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    rendered = markdown_report(report).replace(
        "[report.json](report.json)", f"[{json_path.name}]({json_path.name})"
    )
    markdown_path.write_text(rendered, encoding="utf-8")
    if args.out is None or args.out.suffix.lower() == ".md":
        print(rendered)
    else:
        print(markdown_path)
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
