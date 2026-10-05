"""Explicit shared ownership of the experimental finite line weapon family."""

from copy import deepcopy

from .common import InputError, identifier, require
from .troop_projectiles import LINE_ENTITIES, compile_line_weapon


LINE_POLICIES = {
    "status": "explicit_uncalibrated_hypothesis",
    "impact_eligibility": "shared_collateral_and_protection_exclude_invisible",
    "piercing_clock": "whole_segment_at_terminal_arrival",
    "same_time_settlement": "line_packets_before_pattern_packets_in_shared_health_batch",
    "clock_rounding": "positive_delay_rounds_up_if_lost",
}


def validate_line_binding(binding):
    if not isinstance(binding, dict) or set(binding) != {
        "source",
        "target_layers",
        *LINE_POLICIES,
    }:
        raise InputError("Line binding requires complete shared lifecycle policies")
    identifier(binding["source"], "line binding evidence")
    if any(binding[key] != value for key, value in LINE_POLICIES.items()):
        raise InputError("Unsupported shared line lifecycle policy")
    layers = binding["target_layers"]
    if (
        not isinstance(layers, list)
        or not layers
        or len(set(layers)) != len(layers)
        or not set(layers) <= {"ground", "air"}
    ):
        raise InputError("Line target layers require an explicit hypothesis")
    return layers


def validate_line_owners(actors, enabled):
    from .attacking_extensions import SCOPE
    from .defending_cc_extensions import SCOPE as DEFENSE_SCOPE, _validate_role

    for actor in actors.values():
        adapter = actor.get("entity_adapter", {})
        entity = adapter.get("entity")
        if "defending_extension_model" in actor and entity not in LINE_ENTITIES:
            raise InputError("Unbound defending extension at shared kernel entry")
        if "troop_line_model" not in actor and entity not in LINE_ENTITIES:
            continue
        if (
            not enabled
            or entity not in LINE_ENTITIES
            or adapter.get("attacking_extension_scope") != SCOPE
            or "troop_line_model" not in actor
            or actor["troop_line_model"] != adapter.get("line_weapon_parameters")
            or actor.get("kind") != "unit"
            or actor.get("counts_for_destruction") is not False
            or actor.get("attack_model", {}).get("kind") != "single"
        ):
            raise InputError("Line weapon requires its compiled v27+ lifecycle owner")
        layers = validate_line_binding(require(adapter, "line_binding"))
        if (
            actor["target_layers"] != layers
            or actor["attack_model"]["target_layers"] != layers
        ):
            raise InputError("Line weapon target layers disagree with its binding")
        view = deepcopy(actor)
        view["team"] = "attack"
        compile_line_weapon(
            view, {"line_weapon_parameters": actor["troop_line_model"]}, {"id": entity}
        )
        if actor["team"] == "defense":
            role = require(actor, "defending_extension_model")
            member = require(actor, "garrison_member_model")
            parameters = require(role, "parameters")
            _validate_role(parameters, entity)
            if (
                role.get("entity") != entity
                or role.get("scope") != DEFENSE_SCOPE
                or member.get("entity") != entity
                or parameters != adapter.get("defending_extension_parameters")
                or parameters["target_layers"] != layers
                or parameters["abilities"] != {}
                or actor["target_priorities"] != ["unit"]
                or actor["attack_model"]["target_kinds"] != ["unit"]
                or actor.get("wall_behavior", {}).get("kind")
                != parameters["wall_policy"]
            ):
                raise InputError("Defending line weapon requires matching Castle role")
        elif (
            actor["team"] != "attack"
            or "garrison_member_model" in actor
            or "defending_extension_model" in actor
        ):
            raise InputError("Line weapon has invalid team ownership")
