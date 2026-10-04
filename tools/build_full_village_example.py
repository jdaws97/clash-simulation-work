"""Prepare, compile or simulate complete-inventory TH16 development examples."""

import argparse
import gzip
import io
import json
from itertools import product
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
from study_full_village_resolution import capture_runtime


def write_compressed_result(path, result):
    """Keep complete frames and traces without a large uncompressed artifact."""
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, separators=(",", ":"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "compile", "simulate"))
    parser.add_argument(
        "--layout", choices=("ranked", "war-cwl", "both"), default="both"
    )
    parser.add_argument(
        "--modifier", nargs="+", choices=("none", "legend_i"), default=["none"]
    )
    parser.add_argument("--duration", type=float, default=180)
    parser.add_argument("--maximum-step", type=float, default=0.25)
    parser.add_argument("--label", default="integrated-v28")
    arguments = parser.parse_args()
    if not 0 < arguments.duration <= 180:
        parser.error("Duration must be greater than zero and at most 180 seconds")
    if not 0 < arguments.maximum_step <= 1:
        parser.error("Maximum step must be greater than zero and at most one second")
    if not arguments.label.replace("-", "").isalnum():
        parser.error("Label must contain letters, digits and hyphens only")
    runtime, fingerprint = capture_runtime()
    sys.path.insert(0, str(runtime))
    from clashlab.blueprints import generate_blueprint
    from clashlab.catalog import Catalog
    from clashlab.common import read_json, stable_id, write_json
    from clashlab.development_village import (
        benchmark_army,
        build_scene,
        counted_layout,
        padded_layout,
        termination_policy,
    )
    from clashlab.full_battle import compile_full_battle, simulate_full_battle
    from clashlab.termination_rules import RULES, SCOPE
    from clashlab.geometry import validate_layout

    catalog = Catalog.load(ROOT / "data")
    target = read_json(ROOT / "profiles/target-max-th16-inventory.json")
    policies = read_json(ROOT / "data/battle-policies/development-th16.json")
    account = read_json(ROOT / "profiles/sample-th16.json")
    army = benchmark_army()
    destination = ROOT / "reports/full-village"
    destination.mkdir(parents=True, exist_ok=True)
    write_json(destination / "army.json", army)
    write_json(destination / "behavior-policies.json", policies)
    labels = (
        ("ranked", "war-cwl") if arguments.layout == "both" else (arguments.layout,)
    )
    summaries = []
    for label, modifier in product(labels, arguments.modifier):
        configuration = read_json(
            ROOT / f"examples/blueprint-{label}-configuration.json"
        )
        generation_key = stable_id(
            {
                "target": target,
                "configuration": configuration,
                "snapshot": catalog.snapshot,
            }
        )
        cache_path = destination / f"{label}-blueprint-cache.json"
        cached = read_json(cache_path) if cache_path.exists() else None
        if cached and cached["generation_key"] == generation_key:
            blueprint = cached["blueprint"]
        else:
            blueprint = generate_blueprint(target, catalog, configuration)
            write_json(
                cache_path, {"generation_key": generation_key, "blueprint": blueprint}
            )
        original = counted_layout(blueprint, catalog)
        layout = padded_layout(original)
        write_json(destination / f"{label}-layout.json", original)
        write_json(destination / f"{label}-simulation-layout.json", layout)
        geometry = validate_layout(layout, catalog)
        summary = {
            "layout": label,
            "modifier": modifier,
            "runtime_archive": runtime.name,
            "runtime_sha256": fingerprint,
            "status": "COMPLETE_DECLARED_INVENTORY_DEVELOPMENT_FIXTURE_NOT_RECOMMENDATION",
            "layout_objects": len(layout["buildings"]),
            "counted_structures": sum(
                item["counts_for_destruction"] for item in layout["buildings"]
            ),
            "geometry": geometry,
            "battle_compiled": False,
            "game_deployment_zones_verified": False,
            "replay_calibrated": False,
        }
        if arguments.operation != "prepare":
            scene = build_scene(
                layout, catalog, policies, SCOPE, RULES, arguments.duration
            )
            scene["maximum_step_seconds"] = arguments.maximum_step
            for collection in ("effects", "buff_spells", "freeze_spells"):
                scene[collection] = [
                    item
                    for item in scene[collection]
                    if item["time_seconds"] <= arguments.duration
                ]
            # Activation weights must exactly match the selected command set.
            selected_casts = {
                item["id"]
                for name in ("buff_spells", "freeze_spells")
                for item in scene[name]
            }
            for actor in scene["entities"]:
                if actor["entity"] == "eagle-artillery":
                    activation = actor["indirect_parameters"]["activation"]
                    activation["command_weights"] = {
                        key: value
                        for key, value in activation["command_weights"].items()
                        if key in selected_casts
                    }
            specification = {
                "id": f"{scene['id']}-{modifier}",
                "source": policies["source"],
                "time_limit_seconds": arguments.duration,
                "entity_scene": scene,
                "termination_policy": termination_policy(army, policies),
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
            case_id = f"{label}-{modifier}-{arguments.duration:g}s-{arguments.label}"
            if arguments.maximum_step != 0.25:
                case_id += f"-step-{arguments.maximum_step:g}"
            write_json(destination / f"{case_id}-input.json", specification)
            compiled = compile_full_battle(
                specification,
                account,
                army,
                layout,
                catalog,
                mode_rules=read_json(ROOT / "data/mode-rules.json"),
            )
            summary["battle_compiled"] = True
            summary["binding_counts"] = {
                key: len(compiled["validation"][key])
                for key in ("attacker_bindings", "defender_bindings", "spell_bindings")
            }
            if arguments.operation == "simulate":
                result = simulate_full_battle(
                    specification,
                    account,
                    army,
                    layout,
                    catalog,
                    mode_rules=read_json(ROOT / "data/mode-rules.json"),
                )
                write_compressed_result(
                    destination / f"{case_id}-result.json.gz", result
                )
                summary["outcome"] = result["outcome"]
            write_json(destination / f"{case_id}-summary.json", summary)
        summaries.append(summary)
        console_summary = {
            key: value for key, value in summary.items() if key != "outcome"
        }
        if "outcome" in summary:
            console_summary["outcome"] = {
                key: summary["outcome"][key]
                for key in (
                    "stars",
                    "destruction",
                    "town_hall_destroyed",
                    "elapsed_seconds",
                    "end_reason",
                )
            }
        print(json.dumps(console_summary), flush=True)
    write_json(destination / f"{arguments.operation}-summary.json", summaries)


if __name__ == "__main__":
    main()
