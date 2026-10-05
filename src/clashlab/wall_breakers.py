"""Owned ordinary Wall Breaker blast and consumption bridge for paid battles."""

from copy import deepcopy

from .attacking_extensions import SCOPE, compile_attacking_extension
from .common import InputError, identifier, number, require
from .valkyries import validate_source_radial


POLICIES = {
    "status": "explicit_uncalibrated_hypothesis",
    "geometry": "instant_source_center_at_launch_and_settled_death",
    "death_clock": "immediate_after_settled_prelaunch_hp_death",
    "same_time_settlement": "capture_attack_then_consume_once_before_shared_weapon_health",
}
CONTRACT_FIELDS = (
    "team",
    "kind",
    "layer",
    "movement",
    "damage",
    "range",
    "attack_interval_seconds",
    "target_layers",
    "target_priorities",
    "target_priority_tiers",
    "attack_model",
    "wall_behavior",
    "death_model",
    "troop_behavior_model",
    "wall_breaker_model",
)


def compile_wall_breaker(actor, instance, entity, row, modifiers, movement_units):
    parameters = deepcopy(require(instance, "wall_breaker_parameters"))
    if not isinstance(parameters, dict) or set(parameters) != {
        "source",
        "wall_damage_multiplier",
        "death_radius_tiles",
        *POLICIES,
    }:
        raise InputError(
            "Wall Breaker requires its complete blast and settlement policy"
        )
    identifier(parameters["source"], "Wall Breaker evidence")
    if any(parameters[key] != value for key, value in POLICIES.items()):
        raise InputError("Unsupported Wall Breaker blast policy")
    multiplier = number(
        parameters["wall_damage_multiplier"], "wall blast multiplier", 1e-10
    )
    radius = number(parameters["death_radius_tiles"], "death blast radius", 1e-10)
    if actor.get("wall_behavior", {}).get("kind") != "avoid":
        raise InputError(
            "Wall Breaker cannot use a separate wall weapon or cross intact walls"
        )
    pattern = actor["attack_model"]
    if pattern["kind"] != "radial" or pattern["radius"] < actor["range"]:
        raise InputError("Wall Breaker blast must include its acquired primary")
    projectile = pattern["projectile"]
    if projectile["timing"] != "instant" or projectile["delay_seconds"] != 0:
        raise InputError("Wall Breaker only admits its explicit instant contact blast")
    pattern["kind"] = "source_radial"
    projectile.update(
        destination="fixed_source_center_at_launch",
        inactive_primary_policy="resolve_at_fixed_launch_position",
    )
    validate_source_radial(pattern)
    death = number(
        require(require(row["stats"], "normal"), "deathDamage"),
        "catalog Wall Breaker death damage",
        0,
    )
    death *= modifiers["damage_multiplier"]
    actor["death_model"] = {
        "kind": "fixed_area_sequence_at_death",
        "geometry": "offsets_from_source_center_at_death",
        "source": parameters["source"],
        "effects": [
            {
                "id": "wall-breaker-death-" + name,
                "source": parameters["source"],
                "kind": "area_damage",
                "delay_seconds": 0,
                "amount": death * scale,
                "area": {
                    "offset_x": 0,
                    "offset_y": 0,
                    "radius": radius,
                    "target_team": "defense",
                    "target_kinds": kinds,
                    "target_layers": ["ground"],
                },
            }
            for name, kinds, scale in (
                ("structures", ["defense", "building"], 1),
                ("walls", ["wall"], multiplier),
            )
        ],
    }
    compile_attacking_extension(
        actor, instance, entity, row, modifiers, movement_units, enabled_scope=SCOPE
    )
    actor["wall_breaker_model"] = parameters
    actor["entity_adapter"]["wall_breaker_contract"] = {
        key: deepcopy(actor[key]) for key in CONTRACT_FIELDS
    }
    return actor


def validate_wall_breaker_owners(actors, enabled):
    for actor in actors.values():
        adapter = actor.get("entity_adapter", {})
        if (
            adapter.get("entity") != "wall-breaker"
            and "wall_breaker_model" not in actor
        ):
            continue
        if (
            not enabled
            or adapter.get("entity") != "wall-breaker"
            or actor.get("team") != "attack"
            or adapter.get("attacking_extension_scope") != SCOPE
            or not actor.get("wall_breaker_model")
            or {key: actor.get(key) for key in CONTRACT_FIELDS}
            != adapter.get("wall_breaker_contract")
            or set(actor.get("troop_behavior_model", {}).get("features", {}))
            != {"wall", "suicide"}
        ):
            raise InputError(
                "Wall Breaker requires its complete owned v27+ blast and consumption contract"
            )


def wall_blast_multiplier(source, recipient):
    model = source.get("wall_breaker_model")
    return (
        model["wall_damage_multiplier"] if model and recipient["kind"] == "wall" else 1
    )
