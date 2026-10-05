"""Offline command-line entry point for evidence, candidates, and encounters."""

import argparse
from pathlib import Path

from .army import generate_armies, validate_army
from .adapters import (
    compile_entity_scene,
    simulate_entity_closed_loop,
    simulate_entity_scene,
)
from .boosts import effective_account
from .blueprints import (
    apply_blueprint_swap,
    apply_blueprint_wall_edit,
    generate_blueprint,
    inspect_blueprint,
    screen_blueprint_swaps,
)
from .wallprobes import inspect_wall_access
from .architectures import generate_architecture_candidates
from .basecombat import (
    inspect_blueprint_combat,
    compile_wall_mechanics_probe,
    simulate_wall_mechanics_probe,
)
from .catalog import Catalog
from .closed_loop import simulate_closed_loop
from .common import InputError, read_json, require, write_json
from .decisions import benchmark_decisions, build_jev_request
from .encounter import paired_interventions, simulate_encounter
from .evaluation import evaluate_candidates
from .execution import review_execution
from .experiments import design_campaign, evaluate_strata
from .geometry import layout_features, mutate_layout, validate_layout
from .human import perturb_plan
from .margins import damage_margins
from .modifiers import resolve_battle_modifiers
from .policy import simulate_policy
from .planning import planning_account
from .spatial import simulate_spatial
from .stat_layers import build_statistic_branch
from .extracted_branch import build_extracted_branch
from .full_battle import compile_full_battle, simulate_full_battle


ROOT = Path(__file__).resolve().parents[2]


def parser():
    commands = argparse.ArgumentParser(
        description="Clash Lab: evidence-aware experiments"
    )
    commands.add_argument("--data", type=Path, default=ROOT / "data")
    commands.add_argument("--output", type=Path, required=True)
    sub = commands.add_subparsers(dest="command", required=True)
    sub.add_parser("audit")
    sub.add_parser("coverage")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("entity")
    inspect.add_argument("--level", type=int)
    boost = sub.add_parser("boost")
    boost.add_argument("account", type=Path)
    boost.add_argument("mode", choices=["ranked", "war", "cwl", "friendly"])
    for name in ("validate-army", "generate-armies", "plan-account"):
        command = sub.add_parser(name)
        command.add_argument("input", type=Path)
        command.add_argument("account", type=Path)
    for name in (
        "validate-layout",
        "encounter",
        "spatial",
        "review-execution",
        "design",
        "damage-margins",
        "compile-entities",
        "entity-encounter",
        "inspect-source-branch",
        "mode-modifiers",
        "inspect-blueprint-combat",
    ):
        command = sub.add_parser(name)
        command.add_argument("input", type=Path)
    for name in (
        "layout-features",
        "mutate-layout",
        "evaluate",
        "evaluate-strata",
        "intervene",
        "prepare-jev",
        "benchmark-decisions",
        "generate-blueprint",
        "generate-architectures",
        "inspect-blueprint",
        "screen-blueprint-swaps",
        "apply-blueprint-swap",
        "apply-blueprint-wall-edit",
        "inspect-wall-access",
        "compile-wall-mechanics-probe",
        "wall-mechanics-probe",
    ):
        command = sub.add_parser(name)
        command.add_argument("input", type=Path)
        command.add_argument("configuration", type=Path)
    human = sub.add_parser("human")
    human.add_argument("plan", type=Path)
    human.add_argument("profile", type=Path)
    human.add_argument("--seed", type=int, required=True)
    human.add_argument("--trials", type=int, required=True)
    policy = sub.add_parser("policy")
    policy.add_argument("plan", type=Path)
    policy.add_argument("observations", type=Path)
    policy.add_argument("profile", type=Path)
    policy.add_argument("--seed", type=int, required=True)
    policy.add_argument("--trials", type=int, required=True)
    for name in ("closed-loop", "entity-closed-loop"):
        closed_loop = sub.add_parser(name)
        closed_loop.add_argument("scene", type=Path)
        closed_loop.add_argument("plan", type=Path)
        closed_loop.add_argument("profile", type=Path)
        closed_loop.add_argument("--seed", type=int, required=True)
        closed_loop.add_argument("--trials", type=int, required=True)
    for name in ("compile-full-battle", "full-battle"):
        battle = sub.add_parser(name)
        battle.add_argument("specification", type=Path)
        battle.add_argument("account", type=Path)
        battle.add_argument("army", type=Path)
        battle.add_argument("layout", type=Path)
        battle.add_argument(
            "--mode-rules",
            type=Path,
            help="Battle profiles; defaults to DATA/mode-rules.json when a battle modifier policy is supplied",
        )
    return commands


def main():
    arguments = parser().parse_args()
    catalog = Catalog.load(arguments.data)
    try:
        name = arguments.command
        if name == "audit":
            result = catalog.audit(read_json(arguments.data / "balance-claims.json"))
        elif name == "coverage":
            result = catalog.coverage()
        elif name == "inspect":
            result = catalog.inspect(arguments.entity, arguments.level)
        elif name == "boost":
            result = effective_account(
                read_json(arguments.account), catalog, arguments.mode
            )
        elif name == "mode-modifiers":
            result = resolve_battle_modifiers(
                read_json(arguments.input),
                read_json(arguments.data / "mode-rules.json"),
            )
        elif name in {"validate-army", "generate-armies"}:
            operation = validate_army if name == "validate-army" else generate_armies
            result = operation(
                read_json(arguments.input), read_json(arguments.account), catalog
            )
        elif name == "plan-account":
            result = planning_account(
                read_json(arguments.account), catalog, read_json(arguments.input)
            )
        elif name == "prepare-jev":
            result = build_jev_request(
                read_json(arguments.input), read_json(arguments.configuration)
            )
        elif name == "benchmark-decisions":
            bundle = read_json(arguments.input)
            result = benchmark_decisions(
                bundle["cases"], bundle["responses"], read_json(arguments.configuration)
            )
        elif name == "validate-layout":
            result = validate_layout(read_json(arguments.input), catalog)
        elif name == "generate-blueprint":
            configuration = read_json(arguments.input)
            selected_catalog = entity_catalog(configuration, catalog, arguments.data)
            result = generate_blueprint(
                read_json(arguments.configuration), selected_catalog, configuration
            )
        elif name == "generate-architectures":
            specification = read_json(arguments.input)
            selected_catalogs = [
                entity_catalog(proposal["configuration"], catalog, arguments.data)
                for proposal in require(specification, "proposals")
            ]
            if not selected_catalogs or any(
                selected.snapshot != selected_catalogs[0].snapshot
                for selected in selected_catalogs[1:]
            ):
                raise InputError(
                    "Architecture proposals need the same exact statistic branch"
                )
            result = generate_architecture_candidates(
                read_json(arguments.configuration), selected_catalogs[0], specification
            )
        elif name in {
            "inspect-blueprint",
            "screen-blueprint-swaps",
            "apply-blueprint-swap",
            "apply-blueprint-wall-edit",
            "inspect-wall-access",
            "compile-wall-mechanics-probe",
            "wall-mechanics-probe",
        }:
            blueprint = read_json(arguments.input)
            selected_catalog = entity_catalog(
                blueprint["design_configuration"], catalog, arguments.data
            )
            operation = {
                "inspect-blueprint": inspect_blueprint,
                "screen-blueprint-swaps": screen_blueprint_swaps,
                "apply-blueprint-swap": apply_blueprint_swap,
                "apply-blueprint-wall-edit": apply_blueprint_wall_edit,
                "inspect-wall-access": inspect_wall_access,
                "compile-wall-mechanics-probe": compile_wall_mechanics_probe,
                "wall-mechanics-probe": simulate_wall_mechanics_probe,
            }[name]
            result = operation(
                blueprint, selected_catalog, read_json(arguments.configuration)
            )
        elif name == "inspect-blueprint-combat":
            blueprint = read_json(arguments.input)
            selected_catalog = entity_catalog(
                blueprint["design_configuration"], catalog, arguments.data
            )
            result = inspect_blueprint_combat(blueprint, selected_catalog)
        elif name == "layout-features":
            result = layout_features(
                read_json(arguments.input), catalog, read_json(arguments.configuration)
            )
        elif name == "mutate-layout":
            result = mutate_layout(
                read_json(arguments.input), catalog, read_json(arguments.configuration)
            )
        elif name == "evaluate":
            result = evaluate_candidates(
                read_json(arguments.input), read_json(arguments.configuration)
            )
        elif name == "human":
            result = perturb_plan(
                read_json(arguments.plan),
                read_json(arguments.profile),
                arguments.seed,
                arguments.trials,
            )
        elif name == "policy":
            result = simulate_policy(
                read_json(arguments.plan),
                read_json(arguments.observations),
                read_json(arguments.profile),
                arguments.seed,
                arguments.trials,
            )
        elif name == "encounter":
            result = simulate_encounter(read_json(arguments.input))
        elif name == "spatial":
            result = simulate_spatial(read_json(arguments.input))
        elif name == "damage-margins":
            result = damage_margins(read_json(arguments.input), catalog)
        elif name == "compile-entities":
            specification = read_json(arguments.input)
            selected_catalog = entity_catalog(specification, catalog, arguments.data)
            result = compile_entity_scene(specification, selected_catalog)
        elif name == "entity-encounter":
            specification = read_json(arguments.input)
            selected_catalog = entity_catalog(specification, catalog, arguments.data)
            result = simulate_entity_scene(specification, selected_catalog)
        elif name in {"compile-full-battle", "full-battle"}:
            specification = read_json(arguments.specification)
            mode_rules = None
            if "battle_modifier_policy" in specification:
                mode_rules = read_json(
                    arguments.mode_rules or arguments.data / "mode-rules.json"
                )
            selected_catalog = entity_catalog(
                require(specification, "entity_scene"), catalog, arguments.data
            )
            operation = (
                compile_full_battle
                if name == "compile-full-battle"
                else simulate_full_battle
            )
            result = operation(
                specification,
                read_json(arguments.account),
                read_json(arguments.army),
                read_json(arguments.layout),
                selected_catalog,
                mode_rules=mode_rules,
            )
        elif name == "inspect-source-branch":
            specification = read_json(arguments.input)
            branch = build_statistic_branch(
                catalog,
                read_json(arguments.data / "primary-stat-claims.json"),
                specification["policy"],
            )
            result = {
                "status": "EXPLICIT_PRIMARY_PUBLICATION_BRANCH_NOT_VERIFIED_LIVE_PATCH",
                "branch": branch.snapshot["statistic_branch"],
                "entity": branch.inspect(
                    specification["entity"], specification["level"]
                ),
            }
        elif name == "closed-loop":
            result = simulate_closed_loop(
                read_json(arguments.scene),
                read_json(arguments.plan),
                read_json(arguments.profile),
                arguments.seed,
                arguments.trials,
            )
        elif name == "intervene":
            result = paired_interventions(
                read_json(arguments.input), read_json(arguments.configuration)
            )
        elif name == "entity-closed-loop":
            specification = read_json(arguments.scene)
            selected_catalog = entity_catalog(specification, catalog, arguments.data)
            result = simulate_entity_closed_loop(
                specification,
                selected_catalog,
                read_json(arguments.plan),
                read_json(arguments.profile),
                arguments.seed,
                arguments.trials,
            )
        elif name == "review-execution":
            result = review_execution(read_json(arguments.input))
        elif name == "design":
            result = design_campaign(read_json(arguments.input))
        elif name == "evaluate-strata":
            result = evaluate_strata(
                read_json(arguments.input), read_json(arguments.configuration)
            )
        write_json(arguments.output, result)
        print(f"Saved {arguments.output}")
    except (InputError, KeyError, TypeError, ValueError) as error:
        write_json(
            arguments.output,
            {"status": "INPUT_OR_EVIDENCE_REQUIRED", "reason": str(error)},
        )
        print(f"Input/evidence required: {error}")
        raise SystemExit(2) from error


def entity_catalog(specification, catalog, data_directory):
    statistics = require(specification, "statistics_policy")
    if require(statistics, "kind") == "conditional_extracted_fields":
        policy = require(statistics, "branch_policy")
        branch = build_extracted_branch(
            catalog,
            read_json(data_directory / "clashking-static-data.json"),
            read_json(data_directory / "clashking-static-source.json"),
            require(policy, "selection"),
        )
        if branch.snapshot["statistic_branch"]["policy"] != policy:
            raise InputError(
                "The extraction branch does not match the selected source or fields"
            )
        return branch
    if require(statistics, "kind") == "conditional_primary_publications":
        return build_statistic_branch(
            catalog,
            read_json(data_directory / "primary-stat-claims.json"),
            require(statistics, "branch_policy"),
        )
    return catalog


if __name__ == "__main__":
    main()
