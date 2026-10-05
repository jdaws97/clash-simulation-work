"""One selected home-village siege and separately owned generated reserves.

This is the domain entry point for integration. Caller policies remain explicit
experimental hypotheses; catalog statistics are a pinned, unverified snapshot.
Stored choices never become actors or additional deployable resources.
"""

from copy import deepcopy

from .common import InputError, integer, require
from .siege_extensions import (
    EXTENDED_SIEGES,
    ExtendedSiegeCombat,
    compile_extended_siege,
)
from .siege_machines import SIEGE_MACHINES, SiegeCombat, compile_siege


BARREL_SIEGES = {"troop-launcher", "sky-wagon"}
PERMANENT_SIEGES = SIEGE_MACHINES | EXTENDED_SIEGES | BARREL_SIEGES
BOUND_PERMANENT_SIEGES = {"flame-flinger", "siege-barracks", "sky-wagon"}


def validate_siege_choices(choices, selected, catalog):
    """Validate storage separately; only the selected choice spends one slot.

    Ownership/received-level validation remains the army validator's job. This
    contract checks identities and selection without converting storage to army.
    """
    if not isinstance(choices, list):
        raise InputError("Stored siege choices must be a list")
    identities = set()
    for choice in choices:
        if not isinstance(choice, dict) or set(choice) != {"id", "level", "origin"}:
            raise InputError("Stored siege choice requires id, level and origin")
        entity = choice["id"]
        if entity not in PERMANENT_SIEGES or choice["origin"] not in {"own", "donated"}:
            raise InputError("Unsupported permanent home-village siege choice")
        level = integer(choice["level"], "stored siege level", 1)
        catalog.level(entity, level)
        key = entity, level, choice["origin"]
        if key in identities:
            raise InputError("Duplicate stored siege choice")
        identities.add(key)
    if selected is not None:
        if not isinstance(selected, dict) or set(selected) != {"id", "level", "origin"}:
            raise InputError("Exactly one selected siege choice is required")
        if (selected["id"], selected["level"], selected["origin"]) not in identities:
            raise InputError("Selected siege is absent from stored choices")
    return {"stored_count": len(choices), "deployable_count": int(selected is not None)}


def compile_permanent_siege(
    actor, instance, entity, row, modifiers, catalog, movement_units_per_tile
):
    """Adapter hook; missing opt-in does not silently enable new behavior."""
    entity_id = entity["id"]
    if entity_id in SIEGE_MACHINES:
        return compile_siege(
            actor, instance, entity, row, modifiers, catalog, movement_units_per_tile
        )
    if require(instance, "siege_experimental_opt_in") is not True:
        raise InputError(
            "Uncalibrated siege lifecycle requires explicit experimental opt-in"
        )
    if entity_id in EXTENDED_SIEGES:
        return compile_extended_siege(
            actor, instance, entity, row, modifiers, catalog, movement_units_per_tile
        )
    if entity_id in BARREL_SIEGES:
        from .siege_barrels import compile_barrel_siege

        return compile_barrel_siege(
            actor, instance, entity, row, modifiers, catalog, movement_units_per_tile
        )
    raise InputError("Unsupported permanent siege identity")


def permanent_siege_runtime(actors, select_target, reinforcements, width, height):
    """Same interface as recipe_siege_runtime; never lose a carrier silently."""
    carriers = [actor for actor in actors.values() if "siege_model" in actor]
    if len(carriers) > 1:
        raise InputError("Stored choices cannot become multiple deployed siege actors")
    entity = carriers[0]["siege_model"]["entity"] if carriers else None
    for actor in actors.values():
        barrel_pattern = actor.get("attack_model", {}).get("kind") == "siege_barrel"
        barrel_owner = actor.get("siege_model", {}).get("entity") in BARREL_SIEGES
        if barrel_pattern != barrel_owner:
            raise InputError("Barrel weapons require their selected carrier owner")
        if barrel_owner and (
            actor["attack_model"]["entity"] != actor["siege_model"]["entity"]
            or actor.get("entity_adapter", {}).get("entity")
            != actor["siege_model"]["entity"]
        ):
            raise InputError("Barrel weapon, carrier and catalog identity disagree")
    if entity not in BARREL_SIEGES and any(
        "barrel_member_model" in actor for actor in actors.values()
    ):
        raise InputError("Generated barrel reserve has no selected barrel carrier")
    if entity != "siege-barracks" and any(
        "barracks_member_model" in actor for actor in actors.values()
    ):
        raise InputError("Generated Barracks reserve has no selected Barracks carrier")
    if entity in BARREL_SIEGES:
        from .siege_barrels import BarrelSiegeCombat, StreamedReinforcementCombat

        payload = StreamedReinforcementCombat(
            actors, deepcopy(reinforcements.model), width, height
        )
        return BarrelSiegeCombat(actors, select_target, payload, width, height)
    if entity in EXTENDED_SIEGES:
        return ExtendedSiegeCombat(actors, select_target, reinforcements, width, height)
    if entity is not None and entity not in SIEGE_MACHINES:
        raise InputError("Unknown siege runtime identity")
    return SiegeCombat(actors, select_target, reinforcements, width, height)


def siege_effect_eligible(actor, effect):
    """Shared-kernel hook for official spell immunity and Drill concealment.

    Decay is owned by the carrier runtime. Environmental fire is not a spell.
    Underground hazard handling outside defense targeting needs explicit policy.
    """
    if "siege_model" not in actor:
        return True
    if effect in {"spell", "life_gem", "apprentice_warden_aura", "town_hall_poison"}:
        return False
    if actor.get("_siege_underground", False) and effect == "defense_targeting":
        return False
    if actor.get("_siege_underground", False) and effect in {
        "damage",
        "trap",
        "status",
    }:
        behavior = actor["siege_model"]["parameters"].get("behavior", {})
        if (
            behavior.get("underground_effects")
            == "exclude_direct_splash_status_hazard_and_trap_effects"
        ):
            return False
        raise InputError(
            "Underground Drill hazard interaction requires an explicit kernel policy"
        )
    return True
