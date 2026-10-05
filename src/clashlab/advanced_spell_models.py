"""Seven permanent home spell contracts; catalog statistics are not calibration."""

from copy import deepcopy
from math import inf, nextafter

from .common import InputError, identifier, integer, number, require

# Shared acceptance is narrower than the independently testable domain compiler.
SHARED_BOUND_SPELLS = frozenset(
    {
        "bat-spell",
        "skeleton-spell",
        "jump-spell",
        "ice-block-spell",
        "clone-spell",
        "revive-spell",
        "angry-spell",
    }
)


SPELL_CLASSES = {
    "clone-spell": "summon",
    "bat-spell": "summon",
    "skeleton-spell": "summon",
    "revive-spell": "revive",
    "jump-spell": "support_only",
    "ice-block-spell": "support_only",
    "angry-spell": "support_only",
}
SUPPORTED_SPELLS = frozenset(SPELL_CLASSES)
CONTRACT = "opt_in_experimental_permanent_spells_v1"
POLICIES = {
    "geometry": "live_center_distance",
    "stacking": "independent_fields_strongest_effect_union_duration",
    "eligibility": "attacking_troops_heroes_no_pets_siege_decoys",
    "clone_selection": "distance_then_id_fill_each_source_skip_nonfitting",
    "clone_state": "full_health_fresh_weapon_no_copied_runtime_status",
    "revive_selection": "nearest_dead_hero_then_id_one_per_cast",
    "revive_state": "preserve_spent_ability_absolute_status_clocks_no_pet_revival",
    "ice_membership": "capture_at_arrival_until_field_expiry",
    "anger_membership": "refresh_while_inside_linger_from_last_contact",
    "jump_expiry": "finish_current_wall_exit_then_replan",
    "skeleton_armor": "one_hit_shield_discards_breaking_hit_overflow",
    "summon_garrison_trigger": "do_not_trigger_defending_castle_still_attackable",
    "same_time_settlement": "all_due_releases_and_revivals_then_clone_closure_then_field_membership",
    "clock_rounding": "positive_delay_rounds_up_when_sum_does_not_advance",
}
PARAMETERS = {
    "source",
    "status",
    "impact_delay_seconds",
    "spawn_interval_seconds",
    "spawn_offsets",
    "movement_units_per_tile",
    "skeleton_armor_minimum_level",
    "bat_town_hall_damage_multiplier",
    *POLICIES,
}
QUANTITY_FIELDS = {
    "clone-spell": {"capacity", "duration_seconds", "lifespan_seconds"},
    "bat-spell": {
        "count",
        "hitpoints",
        "attack_interval_seconds",
        "damage",
        "speed",
        "range",
        "armor_hitpoints",
        "resource_damage_multiplier",
        "town_hall_damage_multiplier",
    },
    "skeleton-spell": {
        "count",
        "hitpoints",
        "attack_interval_seconds",
        "damage",
        "speed",
        "range",
        "armor_hitpoints",
        "resource_damage_multiplier",
        "town_hall_damage_multiplier",
    },
    "revive-spell": {"health_fraction"},
    "jump-spell": {"duration_seconds", "exit_linger_seconds"},
    "ice-block-spell": {"duration_seconds", "incoming_damage_multiplier"},
    "angry-spell": {"duration_seconds", "anger_seconds", "movement_bonus"},
}


def spell_clock_after(time, delay):
    """Keep positive spell delays observable even below the clock's current ULP."""
    number(time, "spell clock", 0)
    number(delay, "spell clock delay", 0)
    result = time + delay
    if delay > 0 and result <= time:
        result = nextafter(time, inf)
    return number(result, "representable future spell clock", time)


def validate_advanced_spell(model):
    fields = {
        "id",
        "entity",
        "source",
        "statistics_source",
        "time_seconds",
        "arrival_seconds",
        "position",
        "radius",
        "quantities",
        "parameters",
        "entity_adapter",
    }
    if (
        not isinstance(model, dict)
        or set(model) != fields
        or model["entity"] not in SUPPORTED_SPELLS
    ):
        raise InputError("Permanent spell model must declare all supported fields")
    validate_parameters(model["parameters"])
    for key in ("id", "source", "statistics_source"):
        identifier(model[key], "spell identity/evidence")
    time = number(model["time_seconds"], "cast time", 0)
    arrival = number(model["arrival_seconds"], "arrival time", time)
    if arrival != spell_clock_after(time, model["parameters"]["impact_delay_seconds"]):
        raise InputError("Permanent spell arrival disagrees with cast delay")
    number(model["radius"], "spell radius", 0)
    if not isinstance(model["position"], (list, tuple)) or len(model["position"]) != 2:
        raise InputError("Spell position requires two coordinates")
    for value in model["position"]:
        number(value, "spell coordinate", 0)
    if set(model["quantities"]) != QUANTITY_FIELDS[model["entity"]]:
        raise InputError("Permanent spell quantities disagree with mechanism")
    for key, value in model["quantities"].items():
        number(
            value,
            "spell quantity",
            0,
            1 if key.endswith("fraction") or key.endswith("multiplier") else None,
        )
        if key in {"capacity", "count"}:
            integer(value, "finite spell reserve budget", 1)
        elif key in {
            "duration_seconds",
            "lifespan_seconds",
            "anger_seconds",
            "attack_interval_seconds",
            "hitpoints",
            "health_fraction",
        }:
            number(value, "positive spell quantity", 0.000001)
    adapter = model["entity_adapter"]
    if (
        adapter.get("entity") != model["entity"]
        or adapter.get("termination_classification") != SPELL_CLASSES[model["entity"]]
        or adapter.get("behavior_verification") != CONTRACT
    ):
        raise InputError("Permanent spell identity/experimental mechanism disagree")


def validate_parameters(parameters):
    if not isinstance(parameters, dict) or set(parameters) != PARAMETERS:
        raise InputError("Permanent spells require the complete explicit contract")
    identifier(parameters["source"], "spell behavior evidence")
    if parameters["status"] != CONTRACT:
        raise InputError(
            "Unknown spell interactions require opt-in experimental status"
        )
    for key, value in POLICIES.items():
        if parameters[key] != value:
            raise InputError(f"Unsupported permanent spell policy: {key}")
    number(parameters["impact_delay_seconds"], "cast delay", 0)
    number(parameters["spawn_interval_seconds"], "spawn interval", 0.000001)
    number(parameters["movement_units_per_tile"], "movement conversion", 0.000001)
    integer(
        parameters["skeleton_armor_minimum_level"],
        "explicit armor unlock hypothesis",
        1,
    )
    number(
        parameters["bat_town_hall_damage_multiplier"],
        "explicit missing Bat Town Hall damage hypothesis",
        0,
        1,
    )
    offsets = parameters["spawn_offsets"]
    if not isinstance(offsets, list) or not offsets:
        raise InputError("Spawn offsets must be explicitly declared")
    for point in offsets:
        if not isinstance(point, list) or len(point) != 2:
            raise InputError("Spawn offset must have two coordinates")
        for value in point:
            number(value, "spawn offset")


def compile_advanced_spell(instance, catalog):
    entity_id = require(instance, "entity")
    if entity_id not in SUPPORTED_SPELLS:
        raise InputError("Unknown permanent spell family")
    parameters = require(instance, "parameters")
    validate_parameters(parameters)
    level = integer(require(instance, "level"), "spell level", 1)
    town_hall = integer(require(instance, "town_hall"), "Town Hall", 16, 18)
    if not catalog.available(entity_id, level, town_hall):
        raise InputError("Spell level is unavailable at the declared Town Hall")
    entity, row = catalog.entity(entity_id), catalog.level(entity_id, level)
    if entity.get("base") != "home" or entity.get("category") != "spell":
        raise InputError("Only permanent home-village spells are supported")
    quantities = {}
    if entity_id == "clone-spell":
        quantities = {
            "capacity": integer(require(row, "clonedCapacity"), "clone capacity", 1),
            "duration_seconds": number(
                require(entity, "spellDuration"), "clone field", 0.000001
            ),
            "lifespan_seconds": number(
                require(entity, "clonedLifespan"), "clone life", 0.000001
            ),
        }
    elif entity_id in {"bat-spell", "skeleton-spell"}:
        bat = entity_id == "bat-spell"
        stats = require(entity, "batStats" if bat else "skeletonStats")
        count = integer(
            require(row, "batsGenerated" if bat else "skeletonsGenerated"),
            "spawn count",
            1,
        )
        quantities = {
            "count": count,
            "hitpoints": number(require(stats, "hitpoints"), "summon HP", 0.000001),
            "attack_interval_seconds": number(
                require(stats, "attackSpeed"), "summon interval", 0.000001
            ),
            "damage": number(require(stats, "damagePerSecond"), "summon DPS", 0)
            * stats["attackSpeed"],
            "speed": number(require(stats, "movementSpeed"), "summon speed", 0)
            / parameters["movement_units_per_tile"],
            "range": number(require(stats, "range"), "summon range", 0),
            "armor_hitpoints": (
                number(stats.get("armorHitpoints", 0), "summon armor", 0)
                if level >= parameters["skeleton_armor_minimum_level"]
                else 0
            ),
            "resource_damage_multiplier": number(
                stats.get("damageVsResources", 1), "resource multiplier", 0, 1
            ),
            "town_hall_damage_multiplier": (
                parameters["bat_town_hall_damage_multiplier"] if bat else 1
            ),
        }
        if count > len(parameters["spawn_offsets"]):
            raise InputError("Every generated unit needs an explicit spawn offset")
    elif entity_id == "revive-spell":
        quantities = {
            "health_fraction": number(
                require(row, "heroHealPercent"), "revive percent", 0.000001, 100
            )
            / 100
        }
    else:
        quantities = {
            "duration_seconds": number(
                require(row, "spellDuration"), "spell duration", 0.000001
            )
        }
        if entity_id == "ice-block-spell":
            quantities["incoming_damage_multiplier"] = (
                1
                - number(
                    require(row, "incomingDamageReduction"), "ice reduction", 0, 100
                )
                / 100
            )
        elif entity_id == "angry-spell":
            quantities["anger_seconds"] = number(
                require(row, "angerDuration"), "anger duration", 0.000001
            )
            quantities["movement_bonus"] = (
                number(require(row, "movementSpeedIncrease"), "anger movement", 0)
                / parameters["movement_units_per_tile"]
            )
        else:
            quantities["exit_linger_seconds"] = number(
                require(entity, "boostTime"), "jump linger", 0
            )
    time = number(require(instance, "time_seconds"), "cast time", 0)
    model = {
        "id": identifier(require(instance, "id"), "cast ID"),
        "entity": entity_id,
        "source": parameters["source"],
        "statistics_source": catalog.records[entity_id]["source"],
        "time_seconds": time,
        "arrival_seconds": spell_clock_after(time, parameters["impact_delay_seconds"]),
        "position": [
            number(require(instance, "x"), "cast x", 0),
            number(require(instance, "y"), "cast y", 0),
        ],
        "radius": number(require(entity, "radius"), "spell radius", 0),
        "quantities": quantities,
        "parameters": deepcopy(parameters),
        "entity_adapter": {
            "entity": entity_id,
            "level": level,
            "town_hall": town_hall,
            "housing_space": integer(
                require(entity, "housingSpace"), "spell housing", 1
            ),
            "termination_classification": SPELL_CLASSES[entity_id],
            "snapshot_verification": catalog.records[entity_id]["verification"],
            "behavior_verification": CONTRACT,
        },
    }
    validate_advanced_spell(model)
    return model
