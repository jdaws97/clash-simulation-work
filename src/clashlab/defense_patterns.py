"""Conditional Wizard, Scattershot and Bomb Tower statistic mappings."""

from copy import deepcopy

from .common import InputError, identifier, integer, number, require
from .spatial import EPSILON
from .townhalls import TOWN_HALL_RULES


AREA_DEFENSES = {"wizard-tower", "bomb-tower"}
RULESET = "spatial-area-defenses-town-hall-kernel-v8"
SCOPE = "area_defenses_town_hall_hazards_support_wall_sector_without_heroes_pets_traps_or_defending_troops"
RULES = {
    **TOWN_HALL_RULES,
    "inactive_primary_at_impact": "explicit_pattern_policy_or_legacy_fizzle",
    "directional_splash_axis": "captured_launch_source_to_live_or_fixed_impact_point",
    "directional_splash_geometry": "explicit_center_based_angle_and_linear_distance_bands",
    "splash_layer_filtering": "explicit_primary_layer_or_all_declared_layers",
    "finite_weapon_ammunition": "explicit_initial_rounds_spent_once_per_launched_volley",
}


def compile_defense_pattern(entity_id, mode, stats, parameters, source):
    needed = {"projectile", "splash_layer_policy", "source"}
    needed.add("radius_multiplier" if entity_id in AREA_DEFENSES else "cone_parameters")
    if set(parameters) != needed:
        raise InputError(
            "Area defense parameters must exactly declare geometry and layers"
        )
    identifier(parameters["source"], "area defense behavior evidence")
    require(parameters["projectile"], "inactive_primary_policy")
    pattern = {
        "kind": "radial" if entity_id in AREA_DEFENSES else "directional_splash",
        "source": source,
        "behavior_source": parameters["source"],
        "target_kinds": ["unit"],
        "target_layers": ["ground"] if entity_id == "bomb-tower" else ["ground", "air"],
        "maximum_hp_fraction": 0,
        "projectile": deepcopy(parameters["projectile"]),
        "splash_layer_policy": parameters["splash_layer_policy"],
    }
    if entity_id in AREA_DEFENSES:
        pattern["radius"] = number(
            require(mode, "splashRadius"), "snapshot splash radius", 0
        ) * number(parameters["radius_multiplier"], "splash radius multiplier", 0)
        return pattern
    cone = require(parameters, "cone_parameters")
    if set(cone) != {
        "statistic_basis",
        "axis",
        "half_angle_degrees",
        "near_band_end",
        "far_band_end",
        "source",
    }:
        raise InputError(
            "Scattershot needs every unresolved cone and falloff parameter"
        )
    identifier(cone["source"], "Scattershot geometry evidence")
    if cone["statistic_basis"] != "two_linear_distance_bands_from_snapshot_hypothesis":
        raise InputError("Scattershot damage fields need an explicit quantity mapping")
    near = number(cone["near_band_end"], "near splash boundary", EPSILON)
    far = number(cone["far_band_end"], "far splash boundary", near + EPSILON)
    primary = number(
        require(stats, "damagePerShot"), "Scattershot primary damage", EPSILON
    )
    pattern["directional_splash"] = {
        "source": cone["source"],
        "axis": cone["axis"],
        "half_angle_degrees": cone["half_angle_degrees"],
        "distance_bands": [
            {
                "start": 0,
                "end": near,
                "start_multiplier": 1,
                "end_multiplier": number(
                    require(stats, "damagePerShotMin"), "near splash minimum", 0
                )
                / primary,
            },
            {
                "start": near,
                "end": far,
                "start_multiplier": number(
                    require(stats, "splashDamageMax"), "far splash maximum", 0
                )
                / primary,
                "end_multiplier": number(
                    require(stats, "splashDamageMin"), "far splash minimum", 0
                )
                / primary,
            },
        ],
    }
    return pattern


def compile_scattershot_ammunition(actor, instance, mode):
    parameters = require(instance, "ammunition_parameters")
    if set(parameters) != {"source", "initial_rounds"}:
        raise InputError("Scattershot ammunition must be explicitly initialized")
    identifier(parameters["source"], "Scattershot ammunition evidence")
    maximum = integer(
        require(mode, "numberOfRounds"), "snapshot ammunition capacity", 1
    )
    integer(parameters["initial_rounds"], "initial rounds", 0, maximum)
    actor["weapon_ammunition"] = deepcopy(parameters)
    actor["entity_adapter"]["ammunition_capacity_under_snapshot"] = maximum


def compile_bomb_tower_death(actor, instance, row):
    parameters = require(instance, "bomb_death_parameters")
    if set(parameters) != {
        "source",
        "delay_seconds",
        "radius",
        "damage_multiplier",
        "target_layers",
    }:
        raise InputError("Bomb Tower requires every unresolved death-blast parameter")
    identifier(parameters["source"], "Bomb Tower death behavior evidence")
    layers = require(parameters, "target_layers")
    if layers != ["ground"]:
        raise InputError(
            "Conditional Bomb Tower death damage supports ground units only"
        )
    damage = number(
        require(row, "deathDamage"), "snapshot Bomb Tower death damage", 0
    ) * number(parameters["damage_multiplier"], "death damage multiplier", 0)
    actor["death_model"] = {
        "kind": "fixed_area_sequence_at_death",
        "geometry": "offsets_from_source_center_at_death",
        "source": parameters["source"],
        "effects": [
            {
                "id": "bomb-tower-destruction-blast",
                "source": parameters["source"],
                "kind": "area_damage",
                "delay_seconds": number(
                    parameters["delay_seconds"], "death blast delay", 0
                ),
                "amount": damage,
                "area": {
                    "offset_x": 0,
                    "offset_y": 0,
                    "radius": number(parameters["radius"], "death blast radius", 0),
                    "target_team": "attack",
                    "target_kinds": ["unit"],
                    "target_layers": deepcopy(layers),
                },
            }
        ],
    }
    actor["entity_adapter"]["bomb_death_parameters"] = deepcopy(parameters)
    actor["entity_adapter"]["death_statistic_source"] = actor["source"]
