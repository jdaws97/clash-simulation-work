"""Explicit response selection after every finite attacker reserve is compiled."""

from copy import deepcopy

from .common import InputError, identifier, integer, number


STATUS = "explicit_uncalibrated_hypothesis"
SELECTION = "exact_actor_then_catalog_identity"
RESPONSE_FIELDS = {"trigger_weight", "damage_multiplier", "push_multiplier"}
GENERATED_MODELS = {
    "summon_model",
    "spell_generated_model",
    "spell_clone_model",
    "spell_decoy_model",
    "siege_generated_model",
    "barrel_member_model",
    "barracks_member_model",
}


def bind_giga_responses(scene, binding, catalog):
    """Build exact runtime maps; no inferred hero, pet, summon or siege weights."""
    if not isinstance(binding, dict) or set(binding) != {
        "source",
        "status",
        "selection",
        "actor_responses",
        "entity_responses",
    }:
        raise InputError("Giga response binding needs its complete explicit contract")
    identifier(binding["source"], "Giga response binding evidence")
    if binding["status"] != STATUS or binding["selection"] != SELECTION:
        raise InputError("Unsupported Giga response binding policy")
    traps = [trap for trap in scene.get("traps", []) if trap["entity"] == "giga-bomb"]
    if not traps:
        raise InputError("Giga response binding requires an actual Giga Bomb")
    if any(trap["parameters"]["unit_responses"] for trap in traps):
        raise InputError(
            "Explicit Giga response binding requires empty legacy unit_responses"
        )
    for name in ("actor_responses", "entity_responses"):
        mapping = binding[name]
        if not isinstance(mapping, dict):
            raise InputError("Giga response selectors must be explicit maps")
        for key, response in mapping.items():
            identifier(key, "Giga response selector")
            if not isinstance(response, dict) or set(response) != RESPONSE_FIELDS:
                raise InputError("Giga response selector needs weight, damage and push")
            weight = response["trigger_weight"]
            if weight == "catalog_housing_space":
                if name != "entity_responses":
                    raise InputError(
                        "Catalog Giga weight requires an exact catalog identity"
                    )
                integer(
                    catalog.entity(key).get("housingSpace"), "catalog Giga housing", 0
                )
            else:
                integer(weight, "explicit Giga trigger weight", 0)
            if name == "entity_responses":
                catalog.entity(key)
            for field in ("damage_multiplier", "push_multiplier"):
                number(response[field], "explicit Giga " + field, 0)
    actors = {
        actor["id"]: actor
        for actor in scene["actors"]
        if actor["team"] == "attack" and actor["kind"] == "unit"
    }
    if set(binding["actor_responses"]) - set(actors):
        raise InputError(
            "Giga actor responses contain stale or nonattacking identities"
        )
    responses, selections = {}, {}
    for key, actor in actors.items():
        entity = actor.get("entity_adapter", {}).get("entity")
        if key in binding["actor_responses"]:
            response = deepcopy(binding["actor_responses"][key])
            selection = {"actor": key}
        elif (
            not GENERATED_MODELS.intersection(actor)
            and entity in binding["entity_responses"]
        ):
            response = deepcopy(binding["entity_responses"][entity])
            selection = {"entity": entity}
        else:
            raise InputError(
                "Missing explicit Giga response for compiled attacker " + key
            )
        if response["trigger_weight"] == "catalog_housing_space":
            response["trigger_weight"] = catalog.entity(entity)["housingSpace"]
        responses[key], selections[key] = response, selection
    for trap in traps:
        trap["parameters"]["unit_responses"] = deepcopy(responses)
    scene["giga_bomb_response_audit"] = {
        "capability": "complete-giga-response-binding-v1",
        "source": binding["source"],
        "status": STATUS,
        "selection": SELECTION,
        "actor_selections": selections,
        "responses": responses,
        "trap_ids": sorted(trap["id"] for trap in traps),
        "snapshot_commit": catalog.snapshot["snapshotCommit"],
        "generated_and_controlled_reserves_included": True,
        "full_game_prediction": False,
    }
