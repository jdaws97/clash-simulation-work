"""Bind generated geometry to combat probes and audit the complete village.

A probe removes explicitly listed parts of the village to isolate supported
mechanics. It cannot be passed off as a prediction for the original defense.
"""

from copy import deepcopy

from .adapters import (
    compile_entity_scene,
    partial_adapter_status,
    simulate_entity_closed_loop,
)
from .common import InputError, identifier, require, stable_id
from .geometry import validate_layout


def inspect_blueprint_combat(layout, catalog):
    validation = validate_layout(layout, catalog, require_destruction_flags=False)
    by_entity = {}
    for building in layout["buildings"]:
        entity_id = building["id"]
        if entity_id not in by_entity:
            support = partial_adapter_status(
                catalog.entity(entity_id), building["level"]
            )
            by_entity[entity_id] = {
                "entity": entity_id,
                "instances": [],
                "conditional_adapter": deepcopy(support),
                "complete_village_behavior_verified": False,
            }
        by_entity[entity_id]["instances"].append(building["instance"])
    missing = [
        group
        for group in by_entity.values()
        if not group["conditional_adapter"]["available"]
    ]
    return {
        "status": "FULL_VILLAGE_COMBAT_NOT_READY",
        "blueprint_id": stable_id(layout),
        "validation": validation,
        "required_entities": list(by_entity.values()),
        "unsupported_entity_types": [group["entity"] for group in missing],
        "unsupported_instance_count": sum(len(group["instances"]) for group in missing),
        "unknown_destruction_instances": [
            building["instance"]
            for building in layout["buildings"]
            if building["counts_for_destruction"] is None
        ],
        "defending_hero_requirements": [
            deepcopy(building.get("settings"))
            for building in layout["buildings"]
            if building["id"] == "hero-banner"
        ],
        "defending_castle_requirement": deepcopy(
            layout.get("design_configuration", {}).get("defensive_castle")
        ),
        "full_game_prediction": False,
        "remaining": [
            "Complete all required entity, hero, equipment, pet, garrison and trap behavior handlers",
            "Reconcile current numeric/behavior rules, destruction flags and game layout settings",
            "Supply the complete legal attacking army and a measured human plan/response profile",
            "Validate the complete battle model on held-out replays/friendly tests before ranking defenses",
        ],
    }


def compile_wall_mechanics_probe(layout, catalog, specification):
    identifier(require(specification, "source"), "wall combat probe evidence")
    if require(specification, "blueprint_id") != stable_id(layout):
        raise InputError("Wall combat probe must bind to the exact blueprint")
    if (
        require(specification, "removal_policy")
        != "explicit_other_instances_removed_for_controlled_mechanics_probe"
    ):
        raise InputError("This combat bridge cannot simulate a complete village")
    if require(specification, "wall_policy") != "include_every_blueprint_wall":
        raise InputError("Wall probes must explicitly retain all blueprint walls")
    if require(specification, "troop_group_is_complete_army") is not False:
        raise InputError(
            "A wall mechanics probe cannot claim a complete army or defense result"
        )
    structures = require(specification, "structure_instance_ids")
    removed = require(specification, "removed_instance_ids")
    if (
        not isinstance(structures, list)
        or not structures
        or not isinstance(removed, list)
    ):
        raise InputError(
            "Probe needs selected structures and a complete explicit removal list"
        )
    for instance in structures + removed:
        identifier(instance, "probe structure instance")
    if len(set(structures)) != len(structures) or len(set(removed)) != len(removed):
        raise InputError("Selected and removed instances must each be unique")
    buildings = {item["instance"]: item for item in layout["buildings"]}
    validate_layout(layout, catalog, require_destruction_flags=False)
    walls = {key for key, building in buildings.items() if building["id"] == "wall"}
    if set(structures) & walls:
        raise InputError("Walls are retained separately from selected structures")
    included = walls | set(structures)
    if included & set(removed) or included | set(removed) != set(buildings):
        raise InputError(
            "Every blueprint instance must be retained or explicitly removed exactly once"
        )
    parameters = require(specification, "parameters_by_entity")
    needed_entities = {buildings[key]["id"] for key in included}
    if set(parameters) != needed_entities:
        raise InputError(
            "Probe parameters must exactly cover the retained entity types"
        )
    counts = require(specification, "destruction_flags")
    identifier(require(counts, "source"), "probe destruction hypothesis evidence")
    flags = require(counts, "by_instance")
    if set(flags) != included or any(
        not isinstance(value, bool) for value in flags.values()
    ):
        raise InputError(
            "Every retained instance needs an explicit boolean destruction flag"
        )
    entities = []
    for key in sorted(included):
        building = buildings[key]
        entity_id = building["id"]
        instance_parameters = deepcopy(parameters[entity_id])
        support = partial_adapter_status(catalog.entity(entity_id), building["level"])
        if not support["available"]:
            raise InputError(f"Missing {entity_id} mechanics: {support.get('missing')}")
        immutable_fields = {
            "id",
            "entity",
            "level",
            "town_hall",
            "x",
            "y",
            "mode",
            "team",
            "counts_for_destruction",
        }
        if set(instance_parameters) & immutable_fields:
            raise InputError(
                "Probe parameters cannot override blueprint identity, geometry, mode or level"
            )
        observed_flag = building["counts_for_destruction"]
        if observed_flag is not None and flags[key] != observed_flag:
            raise InputError(
                "Probe destruction flag conflicts with a known blueprint flag"
            )
        if entity_id == "wall" and flags[key]:
            raise InputError("Walls cannot count toward probe destruction")
        if entity_id == "town-hall":
            weapon = catalog.level(entity_id, building["level"]).get("weapon")
            if not isinstance(weapon, dict) or weapon.get("name") != "Giga Inferno":
                raise InputError(
                    "Town Hall probe needs its own supported weapon mapping"
                )
            mode = "gigaInferno"
        elif entity_id == "wall":
            mode = "passive"
        else:
            mode = require(building, "mode")
        entities.append(
            {
                **instance_parameters,
                "id": key,
                "entity": entity_id,
                "level": building["level"],
                "town_hall": layout["town_hall"],
                "mode": mode,
                "team": "defense",
                "counts_for_destruction": flags[key],
                "x": building["x"],
                "y": building["y"],
            }
        )
    attackers = deepcopy(require(specification, "attacking_entities"))
    if not isinstance(attackers, list) or not attackers:
        raise InputError("Mechanics probes need explicit attacking entities")
    if any(require(actor, "team") != "attack" for actor in attackers):
        raise InputError("Probe attacking entities must belong to the attacking team")
    template = deepcopy(require(specification, "scene_template"))
    if any(field in template for field in ("entities", "width", "height")):
        raise InputError(
            "Scene template cannot replace blueprint geometry or actor selection"
        )
    if require(template, "statistics_policy") != require(
        layout["design_configuration"], "statistics_policy"
    ):
        raise InputError("Probe and blueprint must use the same exact statistic policy")
    native_specification = {
        **template,
        "width": layout["width"],
        "height": layout["height"],
        "entities": entities + attackers,
    }
    compiled = compile_entity_scene(native_specification, catalog)
    return {
        "status": "ARTIFICIAL_WALL_COMBAT_PROBE_NOT_ORIGINAL_BASE_DEFENSE",
        "source": specification["source"],
        "blueprint_id": stable_id(layout),
        "retained_blueprint_instances": sorted(included),
        "removed_blueprint_instances": sorted(removed),
        "removed_footprints_become_empty_in_this_artificial_experiment": True,
        "full_village_audit": inspect_blueprint_combat(layout, catalog),
        "compiled": compiled,
        "native_specification": native_specification,
        "full_game_prediction": False,
        "limitations": [
            "Removing structures changes target choice, routes and defensive exposure; results do not score the original base",
            "Only the retained entities and explicitly declared conditional physics are simulated",
            "An incomplete troop group and synthetic human traces cannot establish full-army triple probability",
            "A complete calibrated battle model is still needed for ranked/war/CWL defense selection",
        ],
    }


def simulate_wall_mechanics_probe(layout, catalog, specification):
    probe = compile_wall_mechanics_probe(layout, catalog, specification)
    human = require(specification, "human")
    probe["result"] = simulate_entity_closed_loop(
        probe["native_specification"],
        catalog,
        require(human, "plan"),
        require(human, "profile"),
        require(human, "seed"),
        require(human, "trials"),
    )
    return probe
