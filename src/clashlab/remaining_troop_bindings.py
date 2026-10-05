"""Additive domain bindings; delivered attacking_extensions APIs stay unchanged."""

from copy import deepcopy

from .common import InputError, require
from .hit_status import validate_hit_status
from .meteor_golems import compile_meteor_golem
from .ruin_witches import compile_ruin_witch
from .troop_child_effects import compile_firemite_pool
from .troop_death_buffs import compile_super_valkyrie
from .troop_summons import compile_summon_model


REMAINING_ADAPTERS = {
    "ruin-witch": ("ground", "none"),
    "meteor-golem": ("ground", "radial"),
    "super-valkyrie": ("ground", "radial"),
}


def compile_remaining_troop(actor, instance, entity, row):
    if entity["id"] == "ruin-witch":
        return compile_ruin_witch(actor, instance, entity, row)
    if entity["id"] == "meteor-golem":
        return compile_meteor_golem(actor, instance, entity, row)
    if entity["id"] == "super-valkyrie":
        return compile_super_valkyrie(actor, instance, entity)
    raise InputError("Identity is outside the remaining-troop binding surface")


def complete_summon_family(actor, instance, entity, row):
    """Opt-in validation of child behaviors over the delivered summon compiler.

    Existing compiler calls are unchanged. Integration must invoke this stronger
    contract before promoting these families to complete experimental behavior.
    """
    compile_summon_model(actor, instance, entity, row)
    entity_id = entity["id"]
    children = actor["troop_summon_model"]["children"]
    for child in children:
        template = child["actor"]
        if entity_id == "furnace":
            compile_firemite_pool(template, require(template, "fire_pool_parameters"))
            if template.get("target_priority_tiers") != [["defense", "building"]]:
                raise InputError(
                    "Firemite targets nearest buildings without a defense-priority tier"
                )
        elif entity_id == "super-yeti":
            if template.get("attack_model", {}).get("kind") != "chain":
                raise InputError(
                    "Super Yeti electrical child needs an explicit validated shared chain weapon"
                )
        elif entity_id == "ice-hound":
            validate_hit_status(require(template, "on_hit_status"))
    if entity_id == "ice-hound":
        slow = deepcopy(require(instance, "hound_on_hit_status"))
        validate_hit_status(slow)
        actor["on_hit_status"] = slow
    if entity_id in {"lava-hound", "ice-hound"}:
        actor["troop_identity_target_model"] = {
            "source": instance["summon_parameters"]["source"],
            "preferred_entities": ["air-defense"],
            "fallback": "shared_nearest_reachable_target",
        }
    return actor


class TroopIdentityTargeting:
    """Filter catalog identity preference and delegate acquisition/path decisions."""

    @staticmethod
    def select_target(actor, actors, time, blocked, width, height, base_selector):
        model = actor.get("troop_identity_target_model")
        if model is None:
            return base_selector(actor, actors, time, blocked, width, height)
        preferred = {
            key: candidate
            for key, candidate in actors.items()
            if candidate["team"] == actor["team"]
            or candidate.get("entity_adapter", {}).get("entity")
            in model["preferred_entities"]
        }
        selected = base_selector(actor, preferred, time, blocked, width, height)
        return (
            selected
            if selected[0] is not None
            else base_selector(actor, actors, time, blocked, width, height)
        )
