"""Python 3.10 oracle for M1 native scoring.

The fixtures command runs without the Python battle engine's NumPy/Numba
dependencies. The prepare command uses the usual Python battle engine.

python -B tools/baselab/score_reference.py fixtures rust/score-reference.json
baselab-engine score-check rust/score-reference.json
python -B tools/baselab/score_reference.py prepare rust/bundle.json \
    rust/reference.json layout.json --mode ranked --angles 2 --playbooks
baselab-engine score rust/bundle.json
baselab-engine score-check rust/bundle.json rust/reference.json --battles
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import os
from pathlib import Path
import sys
import tempfile
from contextlib import contextmanager
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(os.environ.get("BASELAB_SCORE_ROOT") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(ROOT / "src"))

from baselab import evaluate, meta_armies  # noqa: E402
from baselab.deploy import inside_holes  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.mechanics import BUILDING_TYPES  # noqa: E402
from baselab.optimize import objective  # noqa: E402


def write_json(path, value):
    Path(path).write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")


def sources():
    """Capture scoring inputs without raw defense-log identities."""

    def optional(path):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    calibration = (
        os.environ.get("BASELAB_CALIBRATION") or ROOT / "data/meta-calibration-r8.json"
    )
    return {
        "base_calibration": optional(ROOT / "data/baselab-calibration.json"),
        "meta_calibration": optional(calibration),
        "observed": optional(meta_armies.OBSERVED),
        "custom": optional(meta_armies.CUSTOM),
        "meta": json.loads(meta_armies.DATA.read_text(encoding="utf-8")),
        "observations": meta_armies.ranked_observations(),
        "playbooks": [
            p.stem
            for p in sorted((ROOT / "data/playbooks").glob("*.json"))
            if json.loads(p.read_text(encoding="utf-8")) is not None
        ],
    }


@contextmanager
def oracle_context(bundle):
    """Exercise production Python functions against portable file snapshots."""
    data = bundle["data"]
    options = bundle.get("scenario_options", {})
    with tempfile.TemporaryDirectory(prefix="baselab-score-") as directory:
        root = Path(directory)
        (root / "data").mkdir()
        for key, filename in [
            ("base_calibration", "baselab-calibration.json"),
            ("meta_calibration", "meta-calibration-r8.json"),
            ("observed", "observed-armies.json"),
            ("custom", "custom-armies.json"),
        ]:
            if data.get(key) is not None:
                write_json(root / "data" / filename, data[key])
        battles = root / "battles.jsonl"
        if "battle_lines" in data:
            battles.write_text(data["battle_lines"], encoding="utf-8")
        meta = copy.deepcopy(data.get("meta", {"builds": []}))
        observed = data.get("observed") or {}
        if isinstance(observed, dict):
            meta["builds"].extend(observed.get("builds", []))
        environment = dict(os.environ)
        for key in ["BASELAB_CALIBRATION", "BASELAB_TH_MIX", "BASELAB_HOLE_PENALTY"]:
            environment.pop(key, None)
        if options.get("th_mix_env") is not None:
            environment["BASELAB_TH_MIX"] = options["th_mix_env"]
        environment["BASELAB_PLAYBOOKS"] = "1" if options.get("playbooks") else "0"
        if bundle.get("hole_penalty") is not None:
            environment["BASELAB_HOLE_PENALTY"] = str(bundle["hole_penalty"])
        observations = data.get("observations")
        if observations is None:
            with (
                patch.object(meta_armies, "BATTLES", battles),
                patch.object(
                    meta_armies,
                    "_share_troop_names",
                    lambda: {int(k): v for k, v in data.get("troop_names", {}).items()},
                ),
            ):
                observations = meta_armies.ranked_observations.__wrapped__()
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(evaluate, "__file__", str(root / "src/baselab/evaluate.py")),
            patch.object(evaluate, "_META_MIX_PRINTED", True),
            patch.object(evaluate, "META_MIX_INFO", {}),
            patch.object(meta_armies, "data", lambda: meta),
            patch.object(meta_armies, "ranked_observations", lambda: observations),
            patch.object(
                meta_armies,
                "_playbook",
                lambda family: {} if family in data.get("playbooks", []) else None,
            ),
        ):
            yield evaluate._load_strength(), observations


def scenario_list(bundle):
    if "scenario_options" not in bundle:
        return [evaluate.Scenario(**row) for row in bundle["scenarios"]]
    options = dict(bundle["scenario_options"])
    options.pop("playbooks", None)
    options.pop("th_mix_env", None)
    if options.get("th_mix") is not None:
        options["th_mix"] = {int(k): v for k, v in options["th_mix"].items()}
    return evaluate.meta_scenarios(**options)


def oracle(bundle):
    with oracle_context(bundle) as (strength, observations):
        scenarios = scenario_list(bundle)
        info = evaluate.META_MIX_INFO
        indices = {id(sc): i for i, sc in enumerate(scenarios)}
        layouts = []
        for raw, results in zip(bundle["layouts"], bundle["results"]):
            layout = Layout.from_json(raw)
            summary = evaluate.summarise(scenarios, results, bundle.get("scout"))
            selections = evaluate.scouted(scenarios, results, bundle.get("scout"))
            layouts.append(
                {
                    "name": layout.name,
                    "objective": objective(
                        summary, bundle.get("mode", "ranked"), layout
                    ),
                    "summary": dataclasses.asdict(summary),
                    "scouting": [[indices[id(sc)], w] for sc, _r, w in selections],
                    "results": results,
                    "holes": sum(map(len, inside_holes(layout))),
                }
            )
        result = {
            "scenarios": [dataclasses.asdict(sc) for sc in scenarios],
            "skills": [evaluate.skill(sc.seed) for sc in scenarios],
            "strength": strength,
            "observations": observations,
            "th_mix": info.get("th_mix"),
            "mix_source": info.get("source"),
            "build_shares": info.get("build_shares"),
            "layouts": layouts,
        }
        if "trophy_cases" in bundle:
            result["trophies"] = [
                [
                    evaluate.attacker_trophies(stars, pct),
                    evaluate.defender_trophies(stars, pct),
                ]
                for stars, pct in bundle["trophy_cases"]
            ]
        return result


def building_sizes():
    return {key: value.size for key, value in BUILDING_TYPES.items()}


def synthetic_data():
    """Declared synthetic builds and log rows; no real account data."""
    builds = []
    for th in [18, 16, 17]:
        for archetype, troop, index, share in [
            ("mass-dragons", "Dragon", 1, 0.2),
            ("mass-dragons", "Dragon", 2, 0.3),
            ("root-rider", "Root Rider", 1, 0.7),
            ("user-rr", "Root Rider", 1, 0.4),
            ("mass-thrower", "Thrower", 1, 0.6),
            ("unsaved-book", "Witch", 1, 0.8),
        ]:
            builds.append(
                {
                    "th": th,
                    "archetype": archetype,
                    "build": index,
                    "share": share,
                    "troops": {troop: 8, "Healer": 2},
                    "heroes": ["Royal Champion", "Archer Queen", "Dragon Duke"],
                }
            )
    observed = [
        {
            "th": th,
            "archetype": archetype,
            "build": 9,
            "share": 0.1,
            "troops": {troop: 8},
            "heroes": ["Archer Queen"],
        }
        for th, archetype, troop in [
            (17, "mass-dragons", "Dragon"),
            (18, "mass-thrower", "Thrower"),
            (17, "new-family", "Witch"),
            (18, "new-family", "Witch"),
        ]
    ]
    lines = [
        {
            "battleType": "ranked",
            "attack": False,
            "opponentTownHallLevel": th,
            "armyShareCode": code,
        }
        for th, code in [
            (15, "u3x1s1x7"),
            (17, "h9u2x2-1x2s2x8"),
            (17, "u2x3-2x2"),
            (18, "u2x4"),
            (19, "u2x3"),
            (16, "u1x1"),
            (18, "u0x1"),
            (17, "u2x999"),
            (18, ""),
            (17, "u2x1u3x3s1x5"),
        ]
    ]
    lines.extend(
        [
            {"battleType": "war", "attack": False},
            {"battleType": "ranked", "attack": True},
            {"battleType": "ranked", "attack": False, "opponentTownHallLevel": 16.0},
            {"battleType": 1, "attack": False},
            {"battleType": "ranked", "attack": False, "opponentTownHallLevel": True},
            {"battleType": "ranked", "attack": False, "opponentTownHallLevel": 0},
            [],
        ]
    )
    return {
        "base_calibration": {
            "hydra": {"strength": 0.9},
            "throwers": {"strength": 1.087},
        },
        "meta_calibration": {
            "mass-dragons-16-1": {"strength": 0.81},
            "mass-dragons-16-2": {"strength": 0.94},
            "mass-thrower-17-1": {"strength": 1.11},
            "mass-thrower-18-1": {"strength": 1.27},
            "_note": {"text": "synthetic calibration"},
            "_metadata": "skipped",
        },
        "observed": {"builds": observed},
        "custom": {
            "builds": [
                {"archetype": "charge", "family": "mass-dragons"},
                {"archetype": "raw"},
            ]
        },
        "meta": {
            "builds": builds,
            "archetype_share_th18": {
                "mass-dragons": [0.271],
                "root-rider": [0.097],
                "user-rr": [0.031],
                "mass-thrower": [0.260],
                "witch": [0.041],
                "lavaloon": [0.019],
            },
        },
        "troop_names": {
            "1": "Dragon",
            "2": "Root Rider",
            "3": "Thrower",
            "4": "Lava Hound",
        },
        "battle_lines": "\n".join(map(json.dumps, lines)) + "\n{invalid\n\n",
        "playbooks": ["dragon", "root-rider"],
    }


def synthetic_layouts():
    open_layout = Layout("synthetic-open", cc_troops=[], heroes=[]).to_json()
    pocket = copy.deepcopy(open_layout)
    pocket["name"] = "synthetic-pocket-tesla-trap"
    pocket["walls"] = sorted(
        {
            (x, y)
            for x in range(8, 18)
            for y in range(8, 18)
            if x in (8, 17) or y in (8, 17)
        }
    )
    pocket["buildings"] = [{"key": "tesla", "x": 11, "y": 11}]
    pocket["traps"] = [{"key": "bomb", "x": 13, "y": 13}]
    plugged = copy.deepcopy(pocket)
    plugged["name"] = "synthetic-plugged"
    plugged["buildings"].append({"key": "th", "x": 11, "y": 11})
    return [open_layout, pocket, plugged]


def finish_case(name, bundle):
    try:
        with oracle_context(bundle):
            scenarios = scenario_list(bundle)
        bundle["scenarios"] = [dataclasses.asdict(sc) for sc in scenarios]
        if "results" not in bundle:
            bundle["results"] = [
                [
                    [
                        (i * 7 + li) % 4,
                        [
                            0.0,
                            1.0,
                            9.999999999999998,
                            49.0,
                            50.0,
                            53.0,
                            91.0,
                            98.0,
                            100.0,
                        ][(i * 11 + li) % 9],
                        (i + li) % 3 == 0,
                        17.5 + i % 13,
                    ]
                    for i in range(len(scenarios))
                ]
                for li in range(len(bundle["layouts"]))
            ]
        expected = oracle(bundle)
    except ValueError as error:
        expected = {"error": str(error)}
    return {"name": name, "bundle": bundle, "expected": expected}


def fixtures(path):
    data = synthetic_data()
    base = {
        "data": data,
        "layouts": synthetic_layouts(),
        "building_sizes": building_sizes(),
        "plans": [],
        "hole_penalty": None,
    }
    cases = []
    for name, extra in [
        ("ranked-observed", {}),
        ("war-techniques", {"mode": "war", "techniques_on": True}),
        ("playbook-filter", {"playbooks": True, "techniques_on": True}),
        ("budget-minimum", {"budget": 7, "techniques_on": True}),
        ("budget-proportional", {"budget": 1200, "playbooks": True}),
        (
            "explicit-mix-order",
            {"th_mix": {"18": 0.2, "16": 0.0, "17": 0.7}, "angle_offset": 0.21},
        ),
        ("environment-mix", {"th_mix_env": "17:0.2,16:0.8", "modifier": "legend3"}),
        ("argument-precedence", {"th_mix": {"16": 1.0}, "th_mix_env": "broken"}),
        ("war-precedence", {"mode": "war", "th_mix_env": "broken"}),
    ]:
        bundle = copy.deepcopy(base)
        bundle["scenario_options"] = {
            "n_angles": 3,
            "seeds": [2, -1],
            "th_mix_env": None,
            "playbooks": False,
            **extra,
        }
        bundle["mode"] = extra.get("mode", "ranked")
        cases.append(finish_case(name, bundle))
    for name, change in [
        ("missing-log-default", "missing"),
        ("empty-log-smoothed", ""),
        ("no-playbooks-retains-builds", "no-books"),
        ("bad-base-atomic", "bad-base"),
    ]:
        bundle = copy.deepcopy(base)
        bundle["scenario_options"] = {
            "n_angles": 2,
            "th_mix_env": None,
            "playbooks": change == "no-books",
        }
        if change == "missing":
            bundle["data"].pop("battle_lines")
        elif change == "":
            bundle["data"]["battle_lines"] = ""
        elif change == "no-books":
            bundle["data"]["playbooks"] = []
        else:
            bundle["data"]["base_calibration"]["broken"] = {}
        cases.append(finish_case(name, bundle))
    for budget in [12.5, 17.5, 1000000]:
        bundle = copy.deepcopy(base)
        bundle["data"]["meta"]["builds"] = [data["meta"]["builds"][6]]
        bundle["data"]["observed"] = None
        bundle["scenario_options"] = {
            "th_mix": {"16": 1.0},
            "budget": budget,
            "th_mix_env": None,
            "playbooks": False,
        }
        cases.append(finish_case(f"budget-round-cap-{budget}", bundle))
    for text in ["16:1,16:2", "broken", "16:-1", "16:0", "16:nan", "16:inf"]:
        bundle = copy.deepcopy(base)
        bundle["scenario_options"] = {"th_mix_env": text, "playbooks": False}
        cases.append(finish_case(f"invalid-mix-{text}", bundle))
    for scout in [0, 1, 2, 3, 9]:
        bundle = copy.deepcopy(base)
        bundle["scout"] = scout
        bundle["mode"] = "war" if scout == 3 else "ranked"
        bundle["hole_penalty"] = 1.125 if scout == 9 else None
        scenarios = []
        for full in [False, True]:
            for angle in [0.1234564, 0.12345649, 2.675, -1.125, 5.2]:
                for charge in [None, ("Archer Queen", 4)]:
                    scenarios.append(
                        evaluate.Scenario(
                            "synthetic",
                            16,
                            angle,
                            -1,
                            0.07,
                            group=9999,
                            charge=charge,
                            full_scout=full,
                        )
                    )
        scenarios.append(
            evaluate.Scenario("negative-zero", 16, -0.0, 0, 0.31, modifier="legend1")
        )
        bundle["scenarios"] = [dataclasses.asdict(sc) for sc in scenarios]
        if scout == 2:
            bundle["results"] = [
                [[2, 80.0, True, float(i)] for i in range(len(scenarios))]
                for _layout in bundle["layouts"]
            ]
        cases.append(finish_case(f"scout-{scout}-techniques-full-ties", bundle))
    bundle = copy.deepcopy(base)
    bundle["scout"] = 1
    pcts = [
        -0.0,
        -0.1,
        0,
        1,
        9.999999999999998,
        10,
        49,
        50,
        52.99999999999999,
        53,
        91,
        98,
        100,
        101,
    ]
    outcomes = [[stars, pct, stars >= 2, 0.0] for stars in [0, 1, 2, 3] for pct in pcts]
    bundle["scenarios"] = [
        dataclasses.asdict(
            evaluate.Scenario("trophy-boundaries", 16, 2.675, i, 1 / len(outcomes))
        )
        for i in range(len(outcomes))
    ]
    bundle["results"] = [outcomes for _layout in bundle["layouts"]]
    bundle["trophy_cases"] = [[stars, pct] for stars, pct, _th, _time in outcomes]
    cases.append(finish_case("trophy-floor-boundaries", bundle))
    for name in ["missing-strength-files", "partial-transfer-loops"]:
        bundle = copy.deepcopy(base)
        bundle["scenarios"] = []
        bundle["results"] = [[] for _layout in bundle["layouts"]]
        if name == "missing-strength-files":
            for key in ["base_calibration", "meta_calibration", "observed", "custom"]:
                bundle["data"][key] = None
        else:
            bundle["data"]["observed"] = [
                {"archetype": "mass-dragons", "th": 17, "build": 7},
                {"archetype": "new-family", "th": 17, "build": 7},
                {"archetype": "new-family", "th": 18, "build": 7},
                {"archetype": "missing-key"},
                {"archetype": "skipped", "th": 18, "build": 7},
            ]
            bundle["data"]["custom"] = {
                "builds": [
                    {"archetype": "before", "family": "mass-dragons"},
                    {},
                    {"archetype": "after", "family": "mass-dragons"},
                ]
            }
        cases.append(finish_case(name, bundle))
    write_json(
        path,
        {
            "provenance": "declared synthetic scoring fixtures; Python 3.10 oracle",
            "cases": cases,
        },
    )
    print(f"wrote {len(cases)} scoring cases to {path}")


def prepare(args):
    from baselab.rust_bridge import scenario_plan

    options = {
        "mode": args.mode,
        "n_angles": args.angles,
        "seeds": args.seeds,
        "th_mix_env": os.environ.get("BASELAB_TH_MIX"),
        "playbooks": args.playbooks,
        "techniques_on": args.techniques,
        "budget": args.budget,
        "angle_offset": args.angle_offset,
    }
    bundle = {
        "mode": args.mode,
        "data": sources(),
        "scenario_options": options,
        "layouts": [Layout.load(p).to_json() for p in args.layouts],
        "building_sizes": building_sizes(),
        "scout": args.scout,
        "hole_penalty": (
            float(os.environ["BASELAB_HOLE_PENALTY"])
            if os.environ.get("BASELAB_HOLE_PENALTY")
            else None
        ),
    }
    with oracle_context(bundle) as (strength, _observations):
        scenarios = scenario_list(bundle)
    # Real playbook documents are needed for plans, outside availability stubs.
    with patch.dict(os.environ, {"BASELAB_PLAYBOOKS": "1" if args.playbooks else "0"}):
        plans = [
            json.loads(scenario_plan(sc, strength.get(sc.army, 1.0)))
            for sc in scenarios
        ]
        results = [
            [
                evaluate._run_one((layout, sc, strength.get(sc.army, 1.0)))
                for sc in scenarios
            ]
            for layout in bundle["layouts"]
        ]
    bundle.update(
        scenarios=[dataclasses.asdict(sc) for sc in scenarios],
        plans=plans,
        results=results,
    )
    expected = oracle(bundle)
    write_json(args.bundle, bundle)
    write_json(args.reference, {"expected": expected})
    print(f"wrote {len(scenarios)} scenarios for {len(results)} layouts")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fixture_parser = commands.add_parser("fixtures")
    fixture_parser.add_argument("output", type=Path)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("bundle", type=Path)
    prepare_parser.add_argument("reference", type=Path)
    prepare_parser.add_argument("layouts", nargs="+", type=Path)
    prepare_parser.add_argument("--mode", choices=["ranked", "war"], default="ranked")
    prepare_parser.add_argument("--angles", type=int, default=2)
    prepare_parser.add_argument("--seeds", nargs="+", type=int, default=[0])
    prepare_parser.add_argument("--scout", type=int, default=2)
    prepare_parser.add_argument(
        "--playbooks",
        action="store_true",
        default=os.environ.get("BASELAB_PLAYBOOKS") == "1",
    )
    prepare_parser.add_argument("--techniques", action="store_true")
    prepare_parser.add_argument("--budget", type=float)
    prepare_parser.add_argument("--angle-offset", type=float, default=0.0)
    args = parser.parse_args()
    if args.command == "fixtures":
        fixtures(args.output)
    else:
        prepare(args)


if __name__ == "__main__":
    main()
