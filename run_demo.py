"""Exercise the complete offline workflow with clearly marked demo fixtures."""

import sys
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from clashlab.army import generate_armies, validate_army
from clashlab.blueprints import (
    generate_blueprint,
    inspect_blueprint,
    screen_blueprint_swaps,
)
from clashlab.adapters import simulate_entity_closed_loop, simulate_entity_scene
from clashlab.catalog import Catalog
from clashlab.closed_loop import simulate_closed_loop
from clashlab.common import read_json, write_json
from clashlab.decisions import benchmark_decisions, build_jev_request
from clashlab.encounter import paired_interventions, simulate_encounter
from clashlab.execution import review_execution
from clashlab.experiments import design_campaign
from clashlab.geometry import layout_features, mutate_layout, validate_layout
from clashlab.margins import damage_margins
from clashlab.modifiers import resolve_battle_modifiers
from clashlab.policy import simulate_policy
from clashlab.planning import planning_account
from clashlab.spatial import simulate_spatial
from clashlab.stat_layers import build_statistic_branch


ARMIES = (
    "root-fireball-druid-experiment",
    "fireball-thrower-experiment",
    "giant-arrow-dragons-experiment",
    "queen-charge-root-experiment",
)


def wall_resolution_study(catalog):
    settings = read_json(ROOT / "examples/wall-resolution-study.json")
    scene = read_json(ROOT / "examples/entity-wall-sector-conditional.json")
    plan = read_json(ROOT / "examples/entity-wall-plan-synthetic.json")
    cases = []
    for step in settings["maximum_step_seconds"]:
        selected_scene = deepcopy(scene)
        selected_scene["maximum_step_seconds"] = step
        for response in ("timely", "late"):
            result = simulate_entity_closed_loop(
                selected_scene,
                catalog,
                plan,
                read_json(ROOT / "examples" / f"entity-wall-{response}-synthetic.json"),
                seed=7,
                trials=1,
            )
            sample = result["human_combat"]["samples"][0]
            actors = sample["combat"]["actors"]
            cases.append(
                {
                    "maximum_step_seconds": step,
                    "response_fixture": response,
                    "wall_hp_at_horizon": actors["wall-5"]["hp"],
                    "wall_breached_at": actors["wall-5"]["death_time"],
                    "root_died_at": actors["root"]["death_time"],
                    "follower_deployed_at": actors["follower-0"]["spawn_seconds"],
                }
            )
    breach_times = [
        case["wall_breached_at"]
        for case in cases
        if case["response_fixture"] == "timely" and case["wall_breached_at"] is not None
    ]
    return {
        "status": "DECLARED_SOLVER_SENSITIVITY_NOT_REPLAY_CALIBRATION",
        "settings": settings,
        "scene_id": scene["id"],
        "plan_id": plan["id"],
        "cases": cases,
        "timely_breach_time_spread_seconds": (
            max(breach_times) - min(breach_times) if breach_times else None
        ),
        "game_resolution_certified": False,
        "full_game_prediction": False,
    }


def support_resolution_study(catalog):
    settings = read_json(ROOT / "examples/support-resolution-study.json")
    scene = read_json(ROOT / "examples/entity-support-sector-conditional.json")
    plan = read_json(ROOT / "examples/entity-support-plan-synthetic.json")
    cases = []
    for step in settings["maximum_step_seconds"]:
        selected_scene = deepcopy(scene)
        selected_scene["maximum_step_seconds"] = step
        for placement in ("accurate", "displaced"):
            result = simulate_entity_closed_loop(
                selected_scene,
                catalog,
                plan,
                read_json(
                    ROOT / "examples" / f"entity-support-{placement}-synthetic.json"
                ),
                seed=7,
                trials=1,
            )
            combat = result["human_combat"]["samples"][0]["combat"]
            cases.append(
                {
                    "maximum_step_seconds": step,
                    "placement_fixture": placement,
                    "death_times": {
                        actor_id: combat["actors"][actor_id]["death_time"]
                        for actor_id in ("root", "healer-0", "healer-1")
                    },
                    "air_defense_hp_at_horizon": combat["actors"]["air-defense"]["hp"],
                    "fields": combat["support"]["fields"],
                }
            )
    return {
        "status": "DECLARED_SOLVER_SENSITIVITY_NOT_REPLAY_CALIBRATION",
        "settings": settings,
        "cases": cases,
        "game_resolution_certified": False,
        "full_game_prediction": False,
    }


def inferno_resolution_study(catalog):
    settings = read_json(ROOT / "examples/inferno-resolution-study.json")
    scene = read_json(ROOT / "examples/entity-inferno-sector-conditional.json")
    plan = read_json(ROOT / "examples/entity-inferno-plan-synthetic.json")
    cases = []
    for step in settings["maximum_step_seconds"]:
        for policy in settings["freeze_policies"]:
            for response in settings["response_fixtures"]:
                selected_scene = deepcopy(scene)
                selected_scene["maximum_step_seconds"] = step
                inferno = next(
                    entity
                    for entity in selected_scene["entities"]
                    if entity["id"] == "inferno"
                )
                inferno["ramp_parameters"]["freeze_policy"] = policy
                result = simulate_entity_closed_loop(
                    selected_scene,
                    catalog,
                    plan,
                    read_json(
                        ROOT / "examples" / f"entity-inferno-{response}-synthetic.json"
                    ),
                    seed=7,
                    trials=1,
                )
                sample = result["human_combat"]["samples"][0]
                actors = sample["combat"]["actors"]
                cases.append(
                    {
                        "maximum_step_seconds": step,
                        "freeze_policy": policy,
                        "response_fixture": response,
                        "root_died_at": actors["root"]["death_time"],
                        "inferno_hp_at_horizon": actors["inferno"]["hp"],
                        "control": sample["control"]["actions"],
                        "healer_hp_at_horizon": {
                            actor_id: actors[actor_id]["hp"]
                            for actor_id in ("healer-0", "healer-1")
                        },
                    }
                )
    return {
        "status": "DECLARED_TIMING_AND_RESET_SENSITIVITY_NOT_REPLAY_CALIBRATION",
        "settings": settings,
        "cases": cases,
        "game_resolution_certified": False,
        "full_game_prediction": False,
    }


def air_resolution_study(catalog, demo_directory):
    settings = read_json(ROOT / "examples/air-resolution-study.json")
    if settings["recorded_case_step_seconds"] not in settings["maximum_step_seconds"]:
        raise ValueError(
            "The recorded air case step must be among the declared study steps"
        )
    cases = []
    for step in settings["maximum_step_seconds"]:
        for layout in settings["layouts"]:
            for basis in settings["death_statistic_bases"]:
                basis_label = (
                    "total"
                    if basis == "snapshot_deathDamage_is_total_hypothesis"
                    else "per-impact"
                )
                for response in settings["response_fixtures"]:
                    scene = read_json(
                        ROOT / "examples" / f"entity-air-{layout}-conditional.json"
                    )
                    scene["maximum_step_seconds"] = step
                    electro = next(
                        entity
                        for entity in scene["entities"]
                        if entity["id"] == "electro"
                    )
                    parameters = electro["death_parameters"]
                    parameters["statistic_basis"] = basis
                    if basis_label == "total":
                        fractions = settings["total_damage_fractions"]
                        if len(fractions) != len(parameters["impacts"]):
                            raise ValueError(
                                "Declared total-damage allocation must match the fixed impact sequence"
                            )
                        for impact, fraction in zip(parameters["impacts"], fractions):
                            impact["damage_fraction"] = fraction
                            impact["source"] = settings["total_damage_fraction_source"]
                    result = simulate_entity_closed_loop(
                        scene,
                        catalog,
                        read_json(
                            ROOT
                            / "examples"
                            / f"entity-air-{layout}-plan-synthetic.json"
                        ),
                        read_json(
                            ROOT
                            / "examples"
                            / f"entity-air-{layout}-{response}-synthetic.json"
                        ),
                        seed=7,
                        trials=1,
                    )
                    sample = result["human_combat"]["samples"][0]
                    combat = sample["combat"]
                    actors = combat["actors"]
                    cases.append(
                        {
                            "maximum_step_seconds": step,
                            "layout": layout,
                            "death_statistic_basis": basis_label,
                            "response_fixture": response,
                            "unit_death_times": {
                                actor_id: actors[actor_id]["death_time"]
                                for actor_id in ("electro", "rider")
                            },
                            "unit_hp_at_horizon": {
                                actor_id: actors[actor_id]["hp"]
                                for actor_id in ("electro", "rider")
                            },
                            "structure_hp_at_horizon": {
                                actor_id: actor["hp"]
                                for actor_id, actor in actors.items()
                                if actor["team"] == "defense"
                            },
                            "emitted_death_instances": combat["death_effects"][
                                "emitted_instances"
                            ],
                            "death_impacts": [
                                event
                                for event in combat["trace"]
                                if event.get("event") == "death_effect_impact"
                            ],
                            "control": sample["control"],
                        }
                    )
                    if step == settings["recorded_case_step_seconds"]:
                        write_json(
                            demo_directory
                            / f"entity-air-{layout}-{basis_label}-{response}.json",
                            result,
                        )
    return {
        "status": "DECLARED_AIR_SPACING_RESPONSE_AND_QUANTITY_STUDY_NOT_REPLAY_CALIBRATION",
        "settings": settings,
        "cases": cases,
        "full_game_prediction": False,
        "game_resolution_certified": False,
        "death_pattern_is_actual_clash_pattern": False,
    }


def air_death_quantity_diagnostic(catalog, demo_directory):
    settings = read_json(ROOT / "examples/air-resolution-study.json")
    cases = []
    for basis in settings["death_statistic_bases"]:
        scene = read_json(ROOT / "examples/entity-air-death-quantity-diagnostic.json")
        electro = next(
            entity for entity in scene["entities"] if entity["id"] == "electro"
        )
        parameters = electro["death_parameters"]
        parameters["statistic_basis"] = basis
        label = (
            "total"
            if basis == "snapshot_deathDamage_is_total_hypothesis"
            else "per-impact"
        )
        if label == "total":
            for impact, fraction in zip(
                parameters["impacts"], settings["total_damage_fractions"]
            ):
                impact["damage_fraction"] = fraction
                impact["source"] = settings["total_damage_fraction_source"]
        result = simulate_entity_scene(scene, catalog)
        write_json(demo_directory / f"air-death-quantity-{label}.json", result)
        cases.append(
            {
                "basis": label,
                "impact_count": len(parameters["impacts"]),
                "remaining_storage_hp": result["combat"]["actors"]["entry-storage"][
                    "hp"
                ],
                "death_impacts": [
                    event
                    for event in result["combat"]["trace"]
                    if event.get("event") == "death_effect_impact"
                ],
            }
        )
    return {
        "status": "ARTIFICIAL_DEATH_QUANTITY_MAPPING_DIAGNOSTIC_NOT_LEGAL_ATTACK",
        "cases": cases,
        "actual_game_quantity_resolved": False,
        "full_game_prediction": False,
    }


def main():
    catalog = Catalog.load(ROOT / "data")
    account = planning_account(
        read_json(ROOT / "profiles/sample-th16.json"),
        catalog,
        read_json(ROOT / "examples/planning-policy.json"),
    )
    write_json(ROOT / "reports/derived-planning-account.json", account)
    demo = ROOT / "reports/demo"
    demo.mkdir(parents=True, exist_ok=True)
    write_json(demo / "air-resolution.json", air_resolution_study(catalog, demo))
    write_json(
        demo / "air-death-quantity.json", air_death_quantity_diagnostic(catalog, demo)
    )
    write_json(demo / "inferno-resolution.json", inferno_resolution_study(catalog))
    for response in ("timely", "late"):
        write_json(
            demo / f"entity-inferno-{response}.json",
            simulate_entity_closed_loop(
                read_json(ROOT / "examples/entity-inferno-sector-conditional.json"),
                catalog,
                read_json(ROOT / "examples/entity-inferno-plan-synthetic.json"),
                read_json(
                    ROOT / "examples" / f"entity-inferno-{response}-synthetic.json"
                ),
                seed=7,
                trials=1,
            ),
        )
        pause_scene = read_json(
            ROOT / "examples/entity-inferno-sector-conditional.json"
        )
        pause_inferno = next(
            entity for entity in pause_scene["entities"] if entity["id"] == "inferno"
        )
        pause_inferno["ramp_parameters"]["freeze_policy"] = "pause"
        write_json(
            demo / f"entity-inferno-pause-{response}.json",
            simulate_entity_closed_loop(
                pause_scene,
                catalog,
                read_json(ROOT / "examples/entity-inferno-plan-synthetic.json"),
                read_json(
                    ROOT / "examples" / f"entity-inferno-{response}-synthetic.json"
                ),
                seed=7,
                trials=1,
            ),
        )
    write_json(
        demo / "mode-modifiers-legend-i-defense.json",
        resolve_battle_modifiers(
            read_json(ROOT / "examples/mode-modifiers-legend-i-defense.json"),
            read_json(ROOT / "data/mode-rules.json"),
        ),
    )
    decision_bundle = read_json(ROOT / "examples/decision-benchmark-synthetic.json")
    write_json(
        demo / "decision-benchmark.json",
        benchmark_decisions(
            decision_bundle["cases"],
            decision_bundle["responses"],
            read_json(ROOT / "examples/decision-benchmark-config-synthetic.json"),
        ),
    )
    write_json(
        demo / "jev-prepared-request.json",
        build_jev_request(
            decision_bundle["cases"][0],
            read_json(ROOT / "examples/jev-request-config-example.json"),
        ),
    )
    results = {}
    for army_id in ARMIES:
        army = read_json(ROOT / "examples" / f"{army_id}.json")
        result = validate_army(army, account, catalog)
        write_json(ROOT / "reports" / f"{army_id}-validation.json", result)
        results[army_id] = result
    reference = read_json(ROOT / "examples/root-fireball-druid-experiment.json")
    castle_checks = []
    for choice in read_json(ROOT / "examples/defense-castle-experiments.json")[
        "options"
    ]:
        recipe = deepcopy(reference)
        recipe["clan_castle"]["troops"] = choice["troops"]
        check = validate_army(recipe, account, catalog)
        castle_checks.append(
            {
                "id": choice["id"],
                "housing": check["used"]["clan_castle_troops"],
                "status": "HOUSING_AND_SNAPSHOT_CAP_CHECK_ONLY",
            }
        )
    write_json(ROOT / "reports/defense-castle-validation.json", castle_checks)
    write_json(
        ROOT / "reports/catalog-audit.json",
        catalog.audit(read_json(ROOT / "data/balance-claims.json")),
    )
    write_json(ROOT / "reports/coverage.json", catalog.coverage())
    branch = build_statistic_branch(
        catalog,
        read_json(ROOT / "data/primary-stat-claims.json"),
        read_json(ROOT / "examples/primary-stat-policy.json"),
    )
    write_json(
        ROOT / "reports/primary-stat-branch.json",
        {
            "status": "SELECTED_PRIMARY_PUBLICATION_BRANCH_NOT_VERIFIED_LIVE_PATCH",
            "branch": branch.snapshot["statistic_branch"],
            "owned_equipment_examples": {
                entity_id: branch.inspect(entity_id, 18)
                for entity_id in ("giant-arrow", "fire-heart")
            },
        },
    )
    write_json(
        demo / "entity-sector.json",
        simulate_entity_scene(
            read_json(ROOT / "examples/entity-sector-conditional.json"), catalog
        ),
    )
    for response in ("timely", "late"):
        write_json(
            demo / f"entity-protection-{response}.json",
            simulate_entity_closed_loop(
                read_json(ROOT / "examples/entity-protection-sector-conditional.json"),
                catalog,
                read_json(ROOT / "examples/entity-protection-plan-synthetic.json"),
                read_json(
                    ROOT / "examples" / f"entity-protection-{response}-synthetic.json"
                ),
                seed=7,
                trials=1,
            ),
        )
        write_json(
            demo / f"entity-wall-{response}.json",
            simulate_entity_closed_loop(
                read_json(ROOT / "examples/entity-wall-sector-conditional.json"),
                catalog,
                read_json(ROOT / "examples/entity-wall-plan-synthetic.json"),
                read_json(ROOT / "examples" / f"entity-wall-{response}-synthetic.json"),
                seed=7,
                trials=1,
            ),
        )
    for motion, name in (
        ("clear", "entity-wall-sector-conditional"),
        ("penetrate", "entity-wall-penetration-conditional"),
    ):
        write_json(
            demo / f"entity-wall-{motion}.json",
            simulate_entity_scene(
                read_json(ROOT / "examples" / f"{name}.json"), catalog
            ),
        )
    write_json(demo / "wall-resolution.json", wall_resolution_study(catalog))
    for placement in ("accurate", "displaced"):
        write_json(
            demo / f"entity-support-{placement}.json",
            simulate_entity_closed_loop(
                read_json(ROOT / "examples/entity-support-sector-conditional.json"),
                catalog,
                read_json(ROOT / "examples/entity-support-plan-synthetic.json"),
                read_json(
                    ROOT / "examples" / f"entity-support-{placement}-synthetic.json"
                ),
                seed=7,
                trials=1,
            ),
        )
    write_json(demo / "support-resolution.json", support_resolution_study(catalog))
    for name in ("ranked", "war-cwl"):
        blueprint = generate_blueprint(
            read_json(ROOT / "profiles/target-max-th16-inventory.json"),
            catalog,
            read_json(ROOT / "examples" / f"blueprint-{name}-configuration.json"),
        )
        write_json(ROOT / "reports" / f"blueprint-{name}.json", blueprint)
        write_json(
            ROOT / "reports" / f"blueprint-{name}-analysis.json",
            inspect_blueprint(
                blueprint,
                catalog,
                read_json(ROOT / "examples/blueprint-probes-conditional.json"),
            ),
        )
        write_json(
            ROOT / "reports" / f"blueprint-{name}-swap-search.json",
            screen_blueprint_swaps(
                blueprint,
                catalog,
                read_json(ROOT / "examples" / f"blueprint-{name}-swap-search.json"),
            ),
        )
    generated = generate_armies(
        read_json(ROOT / "examples/generation-reference.json"), account, catalog
    )
    write_json(demo / "enumeration.json", generated)
    encounter = read_json(ROOT / "examples/encounter-synthetic.json")
    write_json(demo / "encounter.json", simulate_encounter(encounter))
    spatial = read_json(ROOT / "examples/spatial-synthetic.json")
    write_json(demo / "spatial.json", simulate_spatial(spatial))
    closed_loop_plan = read_json(ROOT / "examples/closed-loop-plan-synthetic.json")
    for response in ("timely", "late"):
        write_json(
            demo / f"closed-loop-{response}.json",
            simulate_closed_loop(
                read_json(ROOT / "examples/closed-loop-scene-synthetic.json"),
                closed_loop_plan,
                read_json(ROOT / "examples" / f"closed-loop-{response}-synthetic.json"),
                seed=7,
                trials=1,
            ),
        )
    for placement in ("accurate", "displaced"):
        write_json(
            demo / f"area-{placement}.json",
            simulate_closed_loop(
                read_json(ROOT / "examples/area-scene-synthetic.json"),
                read_json(ROOT / "examples/area-plan-synthetic.json"),
                read_json(ROOT / "examples" / f"area-{placement}-synthetic.json"),
                seed=7,
                trials=1,
            ),
        )
    for condition in ("no-repair", "one-repair", "alone"):
        write_json(
            ROOT / "reports" / f"fireball-margins-{condition}.json",
            damage_margins(
                read_json(ROOT / "examples" / f"fireball-margins-{condition}.json"),
                catalog,
            ),
        )
    write_json(
        demo / "protection-intervention.json",
        paired_interventions(
            encounter, read_json(ROOT / "examples/interventions-synthetic.json")
        ),
    )
    layout = read_json(ROOT / "examples/layout-synthetic.json")
    write_json(demo / "layout-check.json", validate_layout(layout, catalog))
    write_json(
        demo / "layout-features.json",
        layout_features(
            layout, catalog, read_json(ROOT / "examples/layout-features-synthetic.json")
        ),
    )
    write_json(
        demo / "layout-mutations.json",
        mutate_layout(
            layout,
            catalog,
            read_json(ROOT / "examples/layout-mutations-synthetic.json"),
        ),
    )
    write_json(
        demo / "practice-schedule.json",
        design_campaign(read_json(ROOT / "examples/campaign-synthetic.json")),
    )
    write_json(
        demo / "cue-policy.json",
        simulate_policy(
            read_json(ROOT / "examples/policy-synthetic.json"),
            read_json(ROOT / "examples/policy-observations-synthetic.json"),
            read_json(ROOT / "examples/policy-latencies-synthetic.json"),
            seed=7,
            trials=3,
        ),
    )
    reviewed = [
        review_execution(review)
        for review in read_json(ROOT / "reports/execution-reviews.json")
    ]
    write_json(demo / "execution-review-validation.json", reviewed)
    write_json(
        demo / "summary.json",
        {
            "status": "OFFLINE_DEMO_COMPLETED",
            "experimental_armies_checked": len(results),
            "defense_castle_choices_checked": len(castle_checks),
            "synthetic_outputs_are_game_predictions": False,
            "full_battle_model_validated": False,
        },
    )
    print(
        f"Checked {len(results)} experimental armies and {len(castle_checks)} CC choices."
    )
    print(f"Saved clearly labeled synthetic workflow outputs in {demo}")


if __name__ == "__main__":
    main()
