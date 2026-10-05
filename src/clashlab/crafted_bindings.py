"""Shared Station ownership, explicit clock/phase policies and raw-entry guards."""

from copy import deepcopy

from .common import InputError, identifier, require
from .crafted_defenses import WEAPON_KIND, compile_crafted_defense
from .crafted_selection import (
    SELECTION_FIELDS,
    selection_projection,
    validate_availability,
)


SHARED_POLICIES = {
    "status": "explicit_uncalibrated_hypothesis",
    "same_time_settlement": "launches_then_crafted_impacts_and_new_poison_in_shared_health_batch",
    "clock_rounding": "positive_delay_rounds_up_if_lost",
    "range_contact": "shared_inclusive_geometry_tolerance",
    "resources": "one_selected_station_no_extra_modules_or_destruction_credit",
}
ACTOR_FIELDS = (
    "team",
    "kind",
    "layer",
    "hitpoints",
    "damage",
    "attack_interval_seconds",
    "range",
    "minimum_range",
    "movement",
    "speed",
    "width",
    "height",
    "blocking",
    "counts_for_destruction",
    "target_priorities",
    "target_priority_tiers",
    "target_layers",
    "attack_model",
    "spawn_seconds",
)


def validate_binding(binding):
    if not isinstance(binding, dict) or set(binding) != {"source", *SHARED_POLICIES}:
        raise InputError(
            "Crafted shared binding requires its complete explicit contract"
        )
    identifier(binding["source"], "crafted shared evidence")
    if any(binding[key] != value for key, value in SHARED_POLICIES.items()):
        raise InputError("Unsupported crafted shared settlement policy")


def compile_shared_crafted(actor, instance, catalog):
    validate_binding(require(instance, "crafted_shared_binding"))
    validate_availability(
        require(instance, "crafted_parameters"), instance["town_hall"]
    )
    actor.update(kind="defense", layer="ground")
    compile_crafted_defense(actor, instance, catalog, catalog.crafting_station_source())
    if actor["spawn_seconds"] != 0:
        raise InputError("Crafted Station must exist at battle zero")
    actor["entity_adapter"].update(
        crafted_shared_binding=deepcopy(instance["crafted_shared_binding"]),
        crafted_model=deepcopy(actor["crafted_defense_model"]),
        crafted_actor_contract={key: deepcopy(actor[key]) for key in ACTOR_FIELDS},
    )
    return actor


def validate_crafted_owners(actors, enabled):
    selected = [
        a
        for a in actors.values()
        if "crafted_defense_model" in a
        or "crafted_parameters" in a.get("entity_adapter", {})
        or a.get("attack_model", {}).get("kind") == WEAPON_KIND
    ]
    if any(
        a.get("entity_adapter", {}).get("catalog_category") == "crafted-defense"
        for a in actors.values()
    ):
        raise InputError("Crafted modules cannot be independent counted actors")
    if not selected:
        return
    stations = [
        a
        for a in actors.values()
        if a.get("entity_adapter", {}).get("entity") == "crafting-station"
    ]
    if (
        not enabled
        or len(selected) != 1
        or len(stations) != 1
        or selected[0] is not stations[0]
    ):
        raise InputError("Crafted weapon requires one compiled v27+ Station owner")
    actor = selected[0]
    adapter = actor["entity_adapter"]
    validate_binding(require(adapter, "crafted_shared_binding"))
    availability = validate_availability(
        require(adapter, "crafted_parameters"), adapter.get("town_hall")
    )
    if actor.get("crafted_defense_model", {}).get("availability") != availability:
        raise InputError(
            "Crafted runtime availability differs from its compiled Station contract"
        )
    if (
        adapter.get("level") != 1
        or adapter.get("mode") != "normal"
        or adapter.get("statistics_mode") != "normal"
        or actor.get("crafted_defense_model") != adapter.get("crafted_model")
        or actor.get("crafted_defense_model", {}).get("parameters")
        != adapter.get("crafted_parameters")
        or {key: actor.get(key) for key in ACTOR_FIELDS}
        != adapter.get("crafted_actor_contract")
    ):
        raise InputError("Crafted runtime differs from its compiled Station contract")


def bind_layout_selection(building, instance):
    settings = require(building, "settings")
    expected = {"crafted": selection_projection(instance["crafted_parameters"])}
    if settings != expected:
        raise InputError(
            "Layout crafted selection differs from the Station's declared modules/rotation"
        )


def synchronize_profile_contract(actor):
    """Refresh the owned runtime projection after the checked profile transform.

    The modifier owner validates the original contract before changing any stats.
    Source rows, selection, experimental policies and timing remain unchanged.
    """
    if "crafted_defense_model" not in actor:
        return
    actor["entity_adapter"].update(
        crafted_model=deepcopy(actor["crafted_defense_model"]),
        crafted_actor_contract={key: deepcopy(actor[key]) for key in ACTOR_FIELDS},
    )
