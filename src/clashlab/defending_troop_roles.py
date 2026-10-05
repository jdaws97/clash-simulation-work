"""Defending-role binding over the existing, independently compiled troops.

This is not a second troop implementation. Shared adapters compile every weapon,
status and death quantity. This module changes hostility and target *roles* only;
unsupported special troops cannot fall back to an ordinary weapon.
"""

from copy import deepcopy

from .common import InputError, integer, number, require


def bind_defending_weapon(actor):
    """Retarget a compiled offensive troop, preserving its lifecycle models.

    Call before loading runtime modules, never while a projectile is in flight.
    Fixed death areas are rebound to hostile attacking units. Ground-only death
    effects remain ground-only; caller quantities and delays remain unchanged.
    """
    if actor["team"] != "attack" or actor["kind"] != "unit":
        raise InputError("Defending conversion requires a compiled attacking troop")
    if actor.get("spawn_seconds") != "controlled" or actor["counts_for_destruction"]:
        raise InputError(
            "Defending conversion requires an uncounted controlled reserve"
        )
    if any(
        key in actor
        for key in ("payload_member_model", "hero_model", "pet_model", "siege_model")
    ):
        raise InputError("An owned army/hero/pet/carrier cannot become a garrison")
    if actor["attack_model"]["kind"] == "none":
        raise InputError(
            "Nonattacking support needs its own defending support contract"
        )
    actor["team"] = "defense"
    actor["target_priorities"] = ["unit"]
    actor["target_priority_tiers"] = [["unit"]]
    actor["attack_model"]["target_kinds"] = ["unit"]
    actor["attack_model"]["target_layers"] = list(actor["target_layers"])
    for effect in actor.get("death_model", {}).get("effects", []):
        area = effect.get("area")
        if area is not None:
            area["target_team"] = "attack"
            area["target_kinds"] = ["unit"]
    return actor


def compile_shared_garrison_member(
    actor, instance, entity, row, catalog, movement_units_per_tile, compiler=None
):
    """Compile via shared adapter and restore the Castle's independent ownership.

    Adapter integration can inject its troop compiler. The current supported set
    uses v29 weapon/status/death runtimes, which already support both teams.
    New lifecycle runtimes must explicitly accept defensive ownership before
    being added to SHARED_GARRISON_MEMBERS; this helper does not authorize them.
    """
    from .garrisons import SHARED_GARRISON_MEMBERS, _receiver_lab_requirement

    if entity["id"] not in SHARED_GARRISON_MEMBERS:
        raise InputError("This troop has no shared defending lifecycle contract")
    if compiler is None:
        from .adapters import compile_actor

        compiler = compile_actor
    received = require(instance, "garrison_member_parameters")
    shadow = deepcopy(instance)
    shadow.pop("garrison_member_parameters")
    shadow["team"] = "attack"
    # The receiver lab cap is checked by GarrisonCombat; training availability
    # belongs to the donor, not the receiver's self-training roster.
    shadow["town_hall"] = received["donor_town_hall"]
    compiled = compiler(
        shadow,
        catalog,
        movement_units_per_tile,
        allow_walls=True,
        allow_deaths=True,
        allow_hit_status=True,
        allow_extended=True,
        allow_heroes=True,
        allow_support=True,
    )
    bind_defending_weapon(compiled)
    if entity["id"] == "ice-golem":
        # Defensive Freeze has distinct source quantities. Reusing offensive
        # values would silently exaggerate defending CC strength.
        parameters = instance["ice_parameters"]
        effect = compiled["death_model"]["effects"][0]
        effect["area"]["radius"] = (
            number(require(entity, "freezeRadiusOnDefense"), "defensive Ice radius", 0)
            * parameters["death_radius_multiplier"]
        )
        effect["duration_seconds"] = (
            number(
                require(row, "deathFreezeTimeOnDefense"), "defensive Ice duration", 0
            )
            * parameters["death_duration_multiplier"]
        )
        compiled["entity_adapter"]["defensive_death_statistic_fields"] = [
            "freezeRadiusOnDefense",
            "deathFreezeTimeOnDefense",
        ]
    if compiled["id"] != actor["id"]:
        raise InputError("Shared troop compiler changed the garrison identity")
    compiled["entity_adapter"]["town_hall"] = instance["town_hall"]
    compiled["entity_adapter"]["garrison_member_parameters"] = deepcopy(received)
    compiled["entity_adapter"][
        "behavior_verification"
    ] = "shared_troop_lifecycle_with_explicit_defending_roles_not_replay_validated"
    housing = integer(require(entity, "housingSpace"), "garrison housing", 1)
    compiled["housing_space"] = housing
    compiled.update(healing_class="troop", hazard_class="troop", spring_class="troop")
    compiled["garrison_member_model"] = {
        "entity": entity["id"],
        "level": instance["level"],
        "town_hall": instance["town_hall"],
        "housing_space": housing,
        "laboratory_required": _receiver_lab_requirement(entity["id"], row, catalog),
        "parameters": deepcopy(received),
    }
    return compiled
