"""Defensive ownership adapters over the attacking troop domain's lifecycles.

Every parent is compiled by the shared troop implementation; only role, hostile
recipient kinds, documented defensive quantities and reserve ownership change.
No paid army or second Clan Castle payload is manufactured by a generated child.
"""

from copy import deepcopy

from .attacking_extensions import EXTENSION_ADAPTERS, SCOPE as ATTACK_SCOPE
from .attacking_extensions import compile_attacking_extension
from .common import InputError, identifier, integer, require
from .defending_troop_roles import bind_defending_weapon
from .troop_summons import TroopSummonCombat, compile_troop_reserves


SCOPE = "explicit_experimental_defending_cc_extensions"
ROLE_FIELDS = {
    "source",
    "status",
    "abilities",
    "target_layers",
    "wall_policy",
    "hound_quantity_basis",
    "ice_hound_freeze_basis",
}


def _validate_role(parameters, entity_id):
    if not isinstance(parameters, dict) or set(parameters) != ROLE_FIELDS:
        raise InputError(
            "Defending extensions require a complete role eligibility contract"
        )
    identifier(parameters["source"], "defending troop role evidence")
    if parameters["status"] != "explicit_uncalibrated_hypothesis":
        raise InputError("Defending troop ability eligibility is not replay calibrated")
    layers = parameters["target_layers"]
    if (
        not isinstance(layers, list)
        or not layers
        or len(set(layers)) != len(layers)
        or not set(layers) <= {"ground", "air"}
    ):
        raise InputError("Defending troop target layers must be explicit")
    if parameters["wall_policy"] not in {"avoid", "jump_enemy_walls", "not_applicable"}:
        raise InputError("Unknown defending extension wall policy")
    if not isinstance(parameters["abilities"], dict) or any(
        value
        not in {"enabled_on_defense_experimental", "suppressed_on_defense_experimental"}
        for value in parameters["abilities"].values()
    ):
        raise InputError(
            "Every compiled intrinsic feature needs explicit defending eligibility"
        )
    expected_hound = (
        "pupsOnDefense"
        if entity_id in {"lava-hound", "ice-hound"}
        else "not_applicable"
    )
    if parameters["hound_quantity_basis"] != expected_hound:
        raise InputError("Defending Hound summons must use pupsOnDefense")
    expected_freeze = (
        "snapshot_freezeTime_defending_hypothesis"
        if entity_id == "ice-hound"
        else "not_applicable"
    )
    if parameters["ice_hound_freeze_basis"] != expected_freeze:
        raise InputError(
            "Ice Hound defensive Freeze mapping must be explicitly experimental"
        )


def _retarget_child(child, source):
    if child["kind"] != "unit" or child["counts_for_destruction"]:
        raise InputError(
            "Defending generated children cannot own destruction inventory"
        )
    child.update(
        team="defense", target_priorities=["unit"], target_priority_tiers=[["unit"]]
    )
    if child["attack_model"]["kind"] != "none":
        child["attack_model"]["target_kinds"] = ["unit"]
        child["attack_model"]["target_layers"] = list(child["target_layers"])
    if child["movement"] == "ground":
        child["wall_behavior"] = {"kind": "avoid", "source": source}
    for effect in child.get("death_model", {}).get("effects", []):
        if "area" in effect:
            effect["area"].update(target_team="attack", target_kinds=["unit"])


def compile_defending_extension(
    actor, instance, entity, row, modifiers, catalog, conversion, *, enabled_scope
):
    """Binding hook after the integration owner compiles the base troop weapon.

    The input actor is an uncounted, controlled, shared attacking troop. The
    returned actor is defensively owned; this function does not create statistics
    or promote the attacking adapter's registry into defending availability.
    """
    from .garrisons import _receiver_lab_requirement, _validate_member_parameters

    if enabled_scope != SCOPE or entity["id"] not in EXTENSION_ADAPTERS:
        raise InputError("Defending extensions need their explicit registered scope")
    if (
        actor["team"] != "attack"
        or actor["kind"] != "unit"
        or actor["spawn_seconds"] != "controlled"
        or actor["counts_for_destruction"]
    ):
        raise InputError(
            "Defending extension requires a shared controlled troop reserve"
        )
    parameters = deepcopy(require(instance, "defending_extension_parameters"))
    entity_id = entity["id"]
    _validate_role(parameters, entity_id)
    ownership = require(instance, "garrison_member_parameters")
    _validate_member_parameters(ownership, catalog.maximum_town_hall)
    if not catalog.available(
        entity_id, instance["level"], ownership["donor_town_hall"]
    ):
        raise InputError("Declared donor cannot supply this defensive troop level")
    selected = deepcopy(row)
    if entity_id in {"lava-hound", "ice-hound"}:
        selected["pupsOnOffense"] = integer(
            require(row, "pupsOnDefense"), "defending pups", 1
        )
    compile_attacking_extension(
        actor,
        instance,
        entity,
        selected,
        modifiers,
        conversion,
        enabled_scope=ATTACK_SCOPE,
    )
    features = actor.get("troop_behavior_model", {}).get("features", {})
    if set(parameters["abilities"]) != set(features):
        raise InputError(
            "Defending eligibility must cover every compiled intrinsic feature"
        )
    for feature, eligibility in parameters["abilities"].items():
        if eligibility == "suppressed_on_defense_experimental":
            features.pop(feature)
    if actor["attack_model"]["kind"] == "none":
        # The support/factory may be lured by enemies but does not gain a weapon.
        actor.update(
            team="defense", target_priorities=["unit"], target_priority_tiers=[["unit"]]
        )
    else:
        bind_defending_weapon(actor)
    actor["target_layers"] = list(parameters["target_layers"])
    if actor["attack_model"]["kind"] != "none":
        actor["attack_model"]["target_layers"] = list(parameters["target_layers"])
    if actor["movement"] == "ground":
        if parameters["wall_policy"] == "not_applicable":
            raise InputError("Ground defenders need an explicit wall policy")
        actor["wall_behavior"] = {
            "kind": parameters["wall_policy"],
            "source": parameters["source"],
        }
    elif parameters["wall_policy"] != "not_applicable":
        raise InputError("Air defenders cannot carry a ground wall policy")
    if "aura_model" in actor:
        actor["aura_model"]["target_kinds"] = ["unit"]
    for child in actor.get("troop_summon_model", {}).get("children", []):
        _retarget_child(child["actor"], parameters["source"])
    housing = integer(require(entity, "housingSpace"), "defending CC housing", 1)
    actor.update(
        healing_class="troop",
        hazard_class="troop",
        spring_class="troop",
        housing_space=housing,
    )
    actor["garrison_member_model"] = {
        "entity": entity_id,
        "level": instance["level"],
        "town_hall": instance["town_hall"],
        "housing_space": housing,
        "laboratory_required": _receiver_lab_requirement(entity_id, row, catalog),
        "parameters": deepcopy(ownership),
    }
    actor["defending_extension_model"] = {
        "entity": entity_id,
        "scope": SCOPE,
        "parameters": parameters,
    }
    actor["entity_adapter"].update(
        defending_extension_parameters=deepcopy(parameters),
        defending_quantity_mapping=(
            "pupsOnDefense"
            if entity_id in {"lava-hound", "ice-hound"}
            else "shared_catalog_quantities"
        ),
    )
    return actor


def compile_defending_reserves(actors):
    """Precompile every defender-generated child before all shared registries."""
    parents = [actor for actor in actors if "defending_extension_model" in actor]
    result = compile_troop_reserves(parents)
    from .druids import compile_druid_forms

    result.extend(compile_druid_forms(parents))
    ids = {actor["id"] for actor in actors}
    parent_map = {actor["id"]: actor for actor in parents}
    for child in result:
        if child["id"] in ids:
            raise InputError("Defending child ID collides with the full scene")
        ids.add(child["id"])
        parent = parent_map[child["summon_model"]["parent"]]
        _retarget_child(
            child, parent["defending_extension_model"]["parameters"]["source"]
        )
        if child["summon_model"]["kind"] == "attacking_troop_child":
            child["summon_model"]["kind"] = "defending_troop_child"
        child["defending_child_model"] = {
            "parent": parent["id"],
            "castle_id": parent["garrison_member_model"]["parameters"]["castle_id"],
            "resources": "generated_no_paid_housing_or_castle_payload",
        }
    return result


class DefendingSummonCombat(TroopSummonCombat):
    """Reuse summon clocks/queues; validate defensive lineage and continuation."""

    def __init__(self, actors, can_release):
        for key, actor in actors.items():
            if "troop_summon_model" not in actor or actor["team"] != "defense":
                continue
            if (
                "defending_extension_model" not in actor
                or "garrison_member_model" not in actor
            ):
                raise InputError(
                    "Defensive summon parent requires linked Castle ownership"
                )
            for item in actor["troop_summon_model"]["children"]:
                child = actors.get(item["actor"]["id"], {})
                if (
                    child.get("team") != "defense"
                    or child.get("counts_for_destruction") is not False
                    or child.get("defending_child_model", {}).get("parent") != key
                ):
                    raise InputError(
                        "Defending summon child has invalid lineage or resources"
                    )
        super().__init__(actors, can_release)

    def validate_command(self, command):
        if command.get("kind") == "deploy" and any(
            "defending_child_model" in self.actors.get(key, {})
            for key in command.get("targets", [])
        ):
            raise InputError(
                "Defender-generated children cannot be independently deployed"
            )
        super().validate_command(command)

    def continuation_reasons(self, time):
        facts = super().continuation_reasons(time)
        for fact, item in zip(facts, self.pending):
            fact["source_team"] = self.actors[item["parent"]]["team"]
        return facts
