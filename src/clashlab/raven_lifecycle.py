"""Source-pinned resource weapon and opt-in resource-tier pet acquisition."""

from copy import deepcopy
from .common import InputError, identifier, number
from .spatial import center, target_distance, _route_length

POLICIES = {
    "experimental_policy": "raven_resource_weapon_v1_uncalibrated",
    "ability_interpretation": "catalog_single_target_resource_bonus_no_invented_secondary_attack",
    "resource_membership": "explicit_pinned_catalog_entity_ids",
    "damage_basis": "resource_dps_times_catalog_attack_interval_at_launch",
    "acquisition": "resource_tier_then_ordinary_priority_route_distance_id_retain_within_tier",
}


def validate_behavior(value):
    if not isinstance(value, dict) or set(value) != {
        "source",
        "resource_entities",
        *POLICIES,
    }:
        raise InputError(
            "Raven needs complete explicit resource and ability interpretation policies"
        )
    identifier(value["source"], "Raven resource mapping source")
    if any(value[key] != expected for key, expected in POLICIES.items()):
        raise InputError(
            "Raven targeting/ability interpretation must be opt-in uncalibrated"
        )
    ids = value["resource_entities"]
    if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
        raise InputError("Raven needs unique explicit catalog resource entity IDs")
    for item in ids:
        identifier(item, "Raven resource entity")


def compile_model(behavior, row, entity, catalog):
    validate_behavior(behavior)
    for key in behavior["resource_entities"]:
        if catalog.entity(key).get("category") != "resource":
            raise InputError(
                "Raven resource identities must have the pinned resource category"
            )
    base = number(row["damagePerHit"], "Raven ordinary hit", 1e-12)
    resource = number(row["dpsOnResourceBuildings"], "Raven resource DPS", 0) * number(
        entity["attackSpeed"], "Raven cadence", 1e-12
    )
    return {
        "source": row.get("source", behavior["source"]),
        "resource_multiplier": resource / base,
        "behavior": deepcopy(behavior),
        "experimental": True,
    }


def resource_member(model, target):
    return (
        target.get("entity_adapter", {}).get("entity")
        in model["behavior"]["resource_entities"]
    )


def launch_multiplier(actor, target):
    model = actor.get("raven_model")
    if model is None:
        return 1
    validate_behavior(model["behavior"])
    return model["resource_multiplier"] if resource_member(model, target) else 1


def select_target(runtime, actor, time, blocked):
    model = actor["raven_model"]
    choices = []
    for target in runtime.actors.values():
        if not runtime._enemy_eligible(actor, target, time):
            continue
        if target["kind"] in {"defense", "building"} and "entity_adapter" not in target:
            raise InputError(
                "Raven building acquisition needs source-bound entity classification"
            )
        route = runtime._route_to(actor, target, time, blocked)
        if route is None:
            continue
        choices.append(
            (
                not resource_member(model, target),
                actor["_target_ranks"][target["kind"]],
                _route_length(actor, route),
                target_distance(center(actor), target),
                target["id"],
                target,
                route,
            )
        )
    if not choices:
        return None, None
    tier = min(item[0] for item in choices)
    retained = next(
        (
            item
            for item in choices
            if item[0] == tier and item[4] == actor.get("target")
        ),
        None,
    )
    chosen = retained or min(choices, key=lambda item: item[:5])
    return chosen[-2], chosen[-1]
