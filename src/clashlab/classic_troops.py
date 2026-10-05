"""Conditional Giant, Wizard and Hog Rider behavior on shared combat systems.

The registry supplies catalog statistics and explicit projectile parameters.
This module adds structure-targeting tiers, Wizard splash-layer filtering and
Hog wall traversal. It does not invent a splash radius, jump delay, defending
troop aggro rule, or new movement system.
"""

from copy import deepcopy

from .combat import validate_pattern
from .common import InputError, identifier, integer, number, require
from .spatial import EPSILON
from .splash import LAYER_POLICIES


CLASSIC_TROOPS = frozenset({"giant", "wizard", "hog-rider"})
CLASSIC_PATTERNS = {"giant": "single", "wizard": "radial", "hog-rider": "single"}
WIZARD_PARAMETERS = {"source", "splash_layer_policy"}


def _compile_wizard(actor, instance, pattern):
    parameters = require(instance, "wizard_parameters")
    if not isinstance(parameters, dict) or set(parameters) != WIZARD_PARAMETERS:
        raise InputError("Wizard needs explicit splash-layer policy and evidence")
    source = identifier(parameters["source"], "Wizard splash evidence")
    if parameters["splash_layer_policy"] not in LAYER_POLICIES:
        raise InputError("Unsupported Wizard splash-layer policy")
    # The catalog's acquisition range and damageType do not supply this radius.
    number(require(pattern, "radius"), "explicit Wizard splash radius", EPSILON)
    projectile = require(pattern, "projectile")
    if require(projectile, "destination") not in {
        "locked_actor_center_at_impact",
        "fixed_target_center_at_launch",
    }:
        raise InputError("Wizard splash must resolve at an explicit target center")
    require(projectile, "inactive_primary_policy")
    pattern["splash_layer_policy"] = parameters["splash_layer_policy"]
    pattern["behavior_source"] = source
    actor["entity_adapter"]["wizard_parameters"] = deepcopy(parameters)


def _compile_hog_jump(actor, instance):
    parameters = require(instance, "wall_parameters")
    if (
        not isinstance(parameters, dict)
        or set(parameters) != {"kind", "source"}
        or parameters["kind"] != "jump_enemy_walls"
    ):
        raise InputError("Hog Rider requires explicit enemy-wall jumping")
    identifier(parameters["source"], "Hog Rider wall-jump evidence")
    actor["wall_behavior"] = deepcopy(parameters)
    actor["entity_adapter"][
        "wall_behavior_verification"
    ] = "shared_enemy_wall_traversal_without_calibrated_jump_animation"


def compile_classic_troop(actor, instance, entity):
    """Attach behavior after the registry has compiled statistics and pattern.

    Register Giant/Hog as ground/single and Wizard as ground/radial. Wizard
    needs the area-pattern scope; Hog needs the shared wall-jump scope. The
    registry must bypass its ordinary wall-weapon compiler for Hog Rider.
    """
    entity_id = require(instance, "entity")
    if entity_id not in CLASSIC_TROOPS or entity.get("id") != entity_id:
        raise InputError("Classic troop compiler requires Giant, Wizard or Hog Rider")
    if (
        actor.get("kind") != "unit"
        or actor.get("movement") != "ground"
        or actor.get("layer") != "ground"
        or actor.get("team") != "attack"
        or entity.get("category") != "troop"
    ):
        raise InputError("Classic troop behaviors require an attacking ground troop")
    adapter = require(actor, "entity_adapter")
    if adapter.get("entity") != entity_id:
        raise InputError("Classic troop instance and statistic adapter must match")
    if entity_id != "wizard" and "wizard_parameters" in instance:
        raise InputError("Wizard splash parameters cannot attach to another troop")
    expected_type = "splash" if entity_id == "wizard" else "single"
    expected_layers = ["ground", "air"] if entity_id == "wizard" else ["ground"]
    expected_target_type = "both" if entity_id == "wizard" else "ground"
    if (
        entity.get("damageType") != expected_type
        or entity.get("targetType") != expected_target_type
    ):
        raise InputError("Catalog damage or target layers need another troop adapter")
    pattern = deepcopy(require(actor, "attack_model"))
    if pattern.get("kind") != CLASSIC_PATTERNS[entity_id]:
        raise InputError("Classic troop requires its declared supported attack pattern")
    if require(pattern, "maximum_hp_fraction") != 0:
        raise InputError("Classic troops do not use a maximum-HP damage weapon")
    if entity_id == "wizard":
        _compile_wizard(actor, instance, pattern)
    else:
        projectile = require(pattern, "projectile")
        if (
            projectile.get("timing") != "instant"
            or projectile.get("delay_seconds") != 0
        ):
            raise InputError("Giant and Hog melee attacks use explicit instant impacts")
    if entity_id == "hog-rider":
        _compile_hog_jump(actor, instance)
    actor["target_priorities"] = ["defense", "building"]
    actor["target_priority_tiers"] = (
        [["defense", "building"]]
        if entity_id == "wizard"
        else [["defense"], ["building"]]
    )
    actor["target_layers"] = expected_layers
    pattern["target_kinds"] = list(actor["target_priorities"])
    pattern["target_layers"] = list(expected_layers)
    validate_pattern(pattern)
    actor["attack_model"] = pattern
    actor["spring_class"] = "troop"
    actor["housing_space"] = integer(
        require(entity, "housingSpace"), "catalog troop housing space", 1
    )
    adapter["classic_targeting"] = {
        "selection": (
            "any_reachable_structure"
            if entity_id == "wizard"
            else "reachable_defenses_then_reachable_buildings"
        ),
        "basis": "declared_entity_behavior_not_a_catalog_numeric_statistic",
        "retention": "shared_until_dead_or_ineligible",
        "scope": "structure_sectors_without_defending_troop_aggro",
    }
    return actor
