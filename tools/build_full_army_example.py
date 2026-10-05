"""Compile or run complete armies against the saved complete-inventory drafts."""

import argparse
from itertools import product
import json
from pathlib import Path
import shutil
import sys
from time import perf_counter

from build_full_village_example import write_compressed_result
from study_full_village_resolution import capture_runtime


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("compile", "simulate"))
    parser.add_argument(
        "--family", nargs="+", choices=("air", "ground"), default=["air"]
    )
    parser.add_argument(
        "--layout", nargs="+", choices=("ranked", "war-cwl"), default=["ranked"]
    )
    parser.add_argument(
        "--modifier", nargs="+", choices=("none", "legend_i"), default=["none"]
    )
    parser.add_argument("--duration", type=float, default=180)
    parser.add_argument("--maximum-step", type=float, default=0.25)
    arguments = parser.parse_args()
    if not 0 < arguments.duration <= 180 or not 0 < arguments.maximum_step <= 1:
        parser.error("Duration must be in (0, 180], and maximum step in (0, 1]")
    if "war-cwl" in arguments.layout and "legend_i" in arguments.modifier:
        parser.error("This benchmark uses the unmodified profile for war/CWL")
    runtime, fingerprint = capture_runtime()
    sys.path.insert(0, str(runtime))
    from clashlab.army import validate_army
    from clashlab.catalog import Catalog
    from clashlab.common import read_json, write_json
    from clashlab.development_armies import benchmark_army, build_army_scene
    from clashlab.development_village import termination_policy
    from clashlab.full_battle import compile_full_battle, simulate_full_battle
    from clashlab.planning import planning_account
    from clashlab.attack_spell_rules import RULES, SCOPE

    catalog = Catalog.load(ROOT / "data")
    owned = read_json(ROOT / "profiles/sample-th16.json")
    policies = read_json(ROOT / "data/battle-policies/development-full-army.json")
    base_policies = read_json(ROOT / "data/battle-policies/development-th16.json")
    mode_rules = read_json(ROOT / "data/mode-rules.json")
    destination = ROOT / "reports/full-army"
    destination.mkdir(exist_ok=True)
    shutil.copyfile(runtime, destination / runtime.name)
    write_json(destination / "behavior-policies.json", policies)
    write_json(destination / "defender-policies.json", base_policies)
    for family, layout_name, modifier in product(
        arguments.family, arguments.layout, arguments.modifier
    ):
        mode = "ranked" if layout_name == "ranked" else "cwl"
        account = planning_account(
            owned,
            catalog,
            {
                "mode": mode,
                "recipient_level_rule": "unique_capacity_match",
                "super_troops": [],
            },
        )
        army = benchmark_army(account, policies, family)
        validation = validate_army(army, account, catalog)
        layout = read_json(
            ROOT / f"reports/full-village/{layout_name}-simulation-layout.json"
        )
        scene = build_army_scene(
            layout,
            catalog,
            base_policies,
            policies,
            account,
            army,
            SCOPE,
            RULES,
            arguments.duration,
        )
        scene["maximum_step_seconds"] = arguments.maximum_step
        scene["attack_spells"] = []
        case_id = (
            f"{family}-{layout_name}-{modifier}-{arguments.duration:g}s"
            f"-step-{arguments.maximum_step:g}"
        )
        specification = {
            "id": case_id,
            "source": policies["source"],
            "time_limit_seconds": arguments.duration,
            "entity_scene": scene,
            "termination_policy": termination_policy(army, base_policies),
            "battle_modifier_policy": {
                "profile_id": modifier,
                "policy_source": policies["source"],
                "maximum_hp_damage_policy": "unchanged",
                "trap_damage_policy": "unchanged",
                "death_damage_policy": "unchanged",
                "impact_hazard_damage_policy": "unchanged",
                "equipment_aura_damage_policy": "unchanged",
                "hero_summon_statistics_policy": "unchanged",
                "healing_and_status_policy": "unchanged",
            },
        }
        for label, data in (
            ("input", specification),
            ("account", account),
            ("army", army),
            ("layout", layout),
        ):
            write_json(destination / f"{case_id}-{label}.json", data)
        compiled = compile_full_battle(
            specification, account, army, layout, catalog, mode_rules
        )
        summary = {
            "case_id": case_id,
            "status": policies["status"],
            "runtime_archive": runtime.name,
            "runtime_sha256": fingerprint,
            "army_validation": validation,
            "layout_objects": len(layout["buildings"]),
            "binding_counts": {
                name: len(compiled["validation"][name])
                for name in ("attacker_bindings", "defender_bindings", "spell_bindings")
            },
            "limitations": policies["limitations"],
            "replay_calibrated": False,
            "full_game_prediction": False,
        }
        if arguments.operation == "simulate":
            start = perf_counter()
            result = simulate_full_battle(
                specification, account, army, layout, catalog, mode_rules
            )
            summary["wall_seconds"] = perf_counter() - start
            summary["outcome"] = {
                name: result["outcome"][name]
                for name in (
                    "stars",
                    "destruction",
                    "town_hall_destroyed",
                    "elapsed_seconds",
                    "end_reason",
                )
            }
            write_compressed_result(destination / f"{case_id}-result.json.gz", result)
        write_json(destination / f"{case_id}-summary.json", summary)
        print(
            json.dumps(
                {key: value for key, value in summary.items() if key != "limitations"}
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
