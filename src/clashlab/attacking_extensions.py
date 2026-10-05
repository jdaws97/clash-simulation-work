"""Domain binding surface for the integration owner's shared adapter/kernel.

No registry is modified here. A caller must explicitly enable this experimental
scope, compile every reserve, and install all required runtime hooks.
"""

from copy import deepcopy

from .common import InputError, number, require
from .combat import validate_pattern
from .druids import compile_druid
from .electro_titans import compile_electro_titan
from .troop_behaviors import BEHAVIOR_ENTITIES, compile_troop_behavior
from .troop_projectiles import LINE_ENTITIES, compile_line_weapon
from .troop_summons import SUMMON_ENTITIES, compile_summon_model


SCOPE = "explicit_experimental_attacking_troop_extensions"
EXTENSION_ADAPTERS = {
    "electro-titan": ("ground", "single"),
    "druid": ("ground", "none"),
    "goblin": ("ground", "single"),
    "sneaky-goblin": ("ground", "single"),
    "super-giant": ("ground", "single"),
    "wall-breaker": ("ground", "radial"),
    "miner": ("ground", "single"),
    "super-miner": ("ground", "single"),
    "super-minion": ("air", "single"),
    "inferno-dragon": ("air", "single"),
    "super-archer": ("ground", "single"),
    "bowler": ("ground", "single"),
    "super-bowler": ("ground", "single"),
    "witch": ("ground", "radial"),
    "super-witch": ("ground", "radial"),
    "golem": ("ground", "single"),
    "lava-hound": ("air", "single"),
    "ice-hound": ("air", "single"),
    "yeti": ("ground", "single"),
    "super-yeti": ("ground", "single"),
    "super-hog-rider": ("ground", "single"),
    "furnace": ("ground", "none"),
    "super-wizard": ("ground", "chain"),
    "super-dragon": ("air", "radial"),
}
ATTACKING_EXTENSIONS = (
    BEHAVIOR_ENTITIES
    | LINE_ENTITIES
    | SUMMON_ENTITIES
    | {"electro-titan", "druid", "super-wizard", "super-dragon"}
)
UNRESOLVED_TROOPS = {
    "meteor-golem": "Meteormite current child statistics, separation trigger, pairing/recombination HP and ownership contract are absent",
    "ruin-witch": "Rubble consumption ownership, Ruin Knight child weapons and reserve/lifetime statistics are incomplete",
    "super-valkyrie": "Death rage radius, lifetime, source persistence, ally membership and stacking require a separately bound buff-field contract",
}


def compile_extension_weapon(actor, instance, entity, row, modifiers):
    """Map available catalog quantities onto existing validated shared patterns."""
    entity_id = entity["id"]
    if entity_id not in {"super-wizard", "super-dragon"}:
        return actor
    pattern = deepcopy(require(instance, "extension_weapon_parameters"))
    if (
        set(pattern) != {"status", "pattern"}
        or pattern["status"] != "explicit_uncalibrated_hypothesis"
    ):
        raise InputError("Extended weapon requires a complete experimental pattern")
    model = pattern["pattern"]
    if entity_id == "super-wizard":
        if model.get("kind") != "chain" or len(model.get("damage_multipliers", [])) < 2:
            raise InputError("Super Wizard requires an explicitly timed chain weapon")
        stats = require(require(row, "stats"), "normal")
        primary = number(
            require(stats, "damagePerShot"), "Super Wizard primary shot", 1e-10
        )
        secondary = number(
            require(stats, "chainDamagePerShot"), "Super Wizard chain shot", 0
        )
        if model["damage_multipliers"][0] != 1 or any(
            abs(value - secondary / primary) > 1e-10
            for value in model["damage_multipliers"][1:]
        ):
            raise InputError(
                "Super Wizard secondary damage must use the catalog chainDamagePerShot"
            )
    elif model.get("kind") != "radial":
        raise InputError(
            "Super Dragon requires explicit radial pulse/projectile timing"
        )
    validate_pattern(model)
    actor["attack_model"] = model
    actor["extension_weapon_statistics"] = {
        "status": pattern["status"],
        "source": actor["source"],
        "per_hit_catalog_mapping": True,
    }
    return actor


def compile_attacking_extension(
    actor, instance, entity, row, modifiers, movement_units_per_tile, *, enabled_scope
):
    if enabled_scope != SCOPE:
        raise InputError(
            "Attacking troop extensions require their explicit experimental scope"
        )
    entity_id = entity["id"]
    if entity_id in UNRESOLVED_TROOPS:
        raise InputError(UNRESOLVED_TROOPS[entity_id])
    if entity_id not in ATTACKING_EXTENSIONS:
        raise InputError("Identity is outside the attacking extension contract")
    if (
        actor.get("team") != "attack"
        or instance.get("mode") != "normal"
        or instance.get("statistics_mode") != "normal"
    ):
        raise InputError(
            "Extensions currently support attacking normal-mode contracts only"
        )
    if entity_id == "druid":
        return compile_druid(
            actor, instance, entity, row, modifiers, movement_units_per_tile
        )
    if entity_id == "electro-titan":
        return compile_electro_titan(actor, instance, entity, row, modifiers)
    if entity_id in BEHAVIOR_ENTITIES:
        compile_troop_behavior(actor, instance, entity, row, modifiers)
    if entity_id in LINE_ENTITIES:
        compile_line_weapon(actor, instance, entity)
    if entity_id in SUMMON_ENTITIES:
        compile_summon_model(actor, instance, entity, row)
    if entity_id in {"golem", "lava-hound", "ice-hound", "super-miner", "wall-breaker"}:
        death = require(actor, "death_model")
        effects = require(death, "effects")
        if entity_id == "ice-hound":
            expected = number(require(row, "freezeTime"), "Ice Hound death freeze", 0)
            if not any(
                effect.get("kind") == "area_freeze"
                and effect.get("duration_seconds") == expected
                for effect in effects
            ):
                raise InputError(
                    "Ice Hound requires its catalog attacking death Freeze"
                )
        else:
            stats = require(require(row, "stats"), "normal")
            expected = (
                number(require(stats, "deathDamage"), "catalog troop death damage", 0)
                * modifiers["damage_multiplier"]
            )
            if not any(
                effect.get("kind") == "area_damage" and effect.get("amount") == expected
                for effect in effects
            ):
                raise InputError(
                    "Troop death damage must map the separate catalog death quantity"
                )
    return compile_extension_weapon(actor, instance, entity, row, modifiers)
