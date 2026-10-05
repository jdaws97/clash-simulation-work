"""Conditional attacking heroes, equipment and shared ability activation.

The selected loadout is explicit. Pet behavior, defensive hero AI, automatic
activation and unsupported equipment cannot silently enter this sector scope.
"""

import re
from collections import defaultdict
from copy import deepcopy
from math import isclose

from .equipment_lifecycles import (
    OWNERS as LOCAL_EQUIPMENT_OWNERS,
    EquipmentLifecycles,
    compile_equipment as compile_local_equipment,
    validate_equipment as validate_local_equipment,
)
from .equipment_auras import (
    OWNERS as AURA_EQUIPMENT_OWNERS,
    EquipmentAuraCombat,
    compile_equipment as compile_aura_equipment,
    validate_equipment as validate_aura_equipment,
)
from .equipment_weapons import (
    OWNERS as WEAPON_EQUIPMENT_OWNERS,
    compile_equipment as compile_weapon_equipment,
    validate_equipment as validate_weapon_equipment,
)
from .equipment_summons import (
    OWNERS as SUMMON_EQUIPMENT_OWNERS,
    compile_equipment as compile_summon_equipment,
    compile_reserves as compile_equipment_reserves,
    validate_equipment as validate_summon_equipment,
    validate_independent_deployment,
)
from .common import InputError, identifier, integer, number, require
from .combat import validate_pattern
from .defense_patterns import RULES as AREA_DEFENSE_RULES
from .rates import skip_elapsed_pulses
from .spatial import EPSILON, _active, center, target_distance
from .recipe_equipment import (
    OWNERS as RECIPE_EQUIPMENT_OWNERS,
    compile_action_figure_summons,
    compile_recipe_equipment,
    validate_recipe_equipment,
)


RULESET = "spatial-hero-equipment-area-kernel-v9"
SCOPE = "attacking_hero_equipment_area_sector_without_pets_traps_or_defending_troops"
LEGACY_HEROES = {"archer-queen", "royal-champion", "grand-warden"}
EXTENDED_HEROES = {"barbarian-king", "minion-prince", "dragon-duke"}
HEROES = LEGACY_HEROES | EXTENDED_HEROES
EXTENDED_EQUIPMENT_OWNERS = {
    "spiky-ball": "barbarian-king",
    "giant-gauntlet": "barbarian-king",
    "stick-horse": "barbarian-king",
    "revenge-deck": "dragon-duke",
    "fire-heart": "dragon-duke",
    "metal-pants": "minion-prince",
    "noble-iron": "minion-prince",
    "dark-orb": "minion-prince",
}
EQUIPMENT = (
    {
        "invisibility-vial",
        "magic-mirror",
        "rocket-spear",
        "electro-boots",
        "royal-gem",
        "eternal-tome",
        "healing-tome",
    }
    | set(EXTENDED_EQUIPMENT_OWNERS)
    | set(RECIPE_EQUIPMENT_OWNERS)
    | set(LOCAL_EQUIPMENT_OWNERS)
    | set(AURA_EQUIPMENT_OWNERS)
    | set(WEAPON_EQUIPMENT_OWNERS)
    | set(SUMMON_EQUIPMENT_OWNERS)
)
HERO_RULES = {
    **AREA_DEFENSE_RULES,
    "wall_motion": "explicit_clear_penetrate_avoid_or_enemy_wall_jump_hypothesis",
    "hero_activation": "one_shared_manual_charge_executes_all_selected_active_equipment",
    "hero_auto_activation": "disabled_for_controlled_probe_not_current_game_behavior",
    "invisibility": "blocks_weapon_acquisition_but_not_area_or_released_packets",
    "equipment_statistics": "base_and_gear_additions_before_explicit_modifiers",
    "hero_buffs": "cast_time_membership_with_explicit_recipient_pulse_clocks",
    "hero_summons": "predeclared_clones_with_explicit_offsets_and_expiry",
    "same_time_hero_membership": "after_plain_deployments_before_same_time_summons",
    "rocket_spear": "finite_boosted_launches_with_captured_pattern_and_damage",
}


def quantity(value, unit):
    """Parse a named snapshot quantity without inferring another unit."""
    if not isinstance(value, str):
        raise InputError(f"Equipment quantity must explicitly use {unit}")
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*" + re.escape(unit), value)
    if match is None:
        raise InputError(f"Unsupported equipment quantity: {value}")
    return number(float(match.group(1)), f"equipment {unit}", 0)


def _equipment_parameter_fields(entity_id):
    required = {"source"}
    additions = {
        "magic-mirror": {
            "clone_offsets",
            "clone_statistics",
            "source_death_policy",
            "first_attack_delay_seconds",
        },
        "rocket-spear": {"splash_layer_policy"},
        "electro-boots": {
            "first_aura_pulse_delay_seconds",
            "self_heal_interval_seconds",
            "first_self_heal_delay_seconds",
            "frozen_passives_policy",
            "aura_target_kinds",
            "aura_target_layers",
        },
        "eternal-tome": {"radius", "membership"},
        "healing-tome": {
            "radius",
            "membership",
            "pulse_interval_seconds",
            "first_pulse_delay_seconds",
            "healing_multipliers_by_class",
        },
    }
    return required | additions.get(entity_id, set())


def _validate_runtime_equipment(model):
    entity_id = require(model, "entity")
    if entity_id in SUMMON_EQUIPMENT_OWNERS:
        validate_summon_equipment(model)
        return
    if entity_id in WEAPON_EQUIPMENT_OWNERS:
        validate_weapon_equipment(model)
        return
    if entity_id in AURA_EQUIPMENT_OWNERS:
        validate_aura_equipment(model)
        return
    if entity_id in LOCAL_EQUIPMENT_OWNERS:
        validate_local_equipment(model)
        return
    if entity_id in RECIPE_EQUIPMENT_OWNERS:
        validate_recipe_equipment(model)
        return
    if entity_id in EXTENDED_EQUIPMENT_OWNERS:
        from .barbarian_king import validate_king_equipment
        from .dragon_duke import validate_duke_equipment
        from .minion_prince import validate_prince_equipment

        validators = {
            "barbarian-king": validate_king_equipment,
            "dragon-duke": validate_duke_equipment,
            "minion-prince": validate_prince_equipment,
        }
        validators[EXTENDED_EQUIPMENT_OWNERS[entity_id]](model)
        return
    extra_fields = {
        "invisibility-vial": {"invisibility_seconds", "damage_per_hit_increase"},
        "magic-mirror": {
            "invisibility_seconds",
            "clone_duration_seconds",
            "clone_hitpoints",
            "clone_dps",
            "clone_count",
        },
        "rocket-spear": {
            "damage_per_hit_increase",
            "boosted_launches",
            "attack_range",
            "splash_radius",
        },
        "electro-boots": {
            "aura_radius",
            "aura_interval_seconds",
            "aura_damage",
            "self_healing_per_second",
        },
        "royal-gem": {"health_recovery"},
        "eternal-tome": {"duration_seconds"},
        "healing-tome": {"duration_seconds", "healing_per_second", "pulse_count"},
    }
    if entity_id not in extra_fields:
        raise InputError("Unsupported runtime equipment entity")
    required = {
        "entity",
        "level",
        "ability_type",
        "source",
        "behavior_source",
        "parameters",
    } | extra_fields[entity_id]
    if set(model) != required:
        raise InputError("Runtime equipment cannot hide unimplemented fields")
    integer(model["level"], "runtime equipment level", 1)
    expected_type = "Passive" if entity_id == "electro-boots" else "Active"
    if model["ability_type"] != expected_type:
        raise InputError(
            "The runtime equipment activation type does not match its behavior"
        )
    identifier(model["source"], "runtime equipment statistic source")
    identifier(model["behavior_source"], "runtime equipment behavior source")
    parameters = model["parameters"]
    if not isinstance(parameters, dict) or set(
        parameters
    ) != _equipment_parameter_fields(entity_id):
        raise InputError(
            "Runtime equipment parameters must match the supported behavior"
        )
    identifier(parameters["source"], "runtime equipment parameter source")
    for field in extra_fields[entity_id]:
        if field in {"clone_count", "boosted_launches", "pulse_count"}:
            integer(model[field], field, 1)
        else:
            number(model[field], field, 0)
    if entity_id == "magic-mirror":
        if (
            parameters["clone_statistics"]
            != "snapshot_clone_totals_without_equipment_hypothesis"
            or parameters["source_death_policy"]
            != "released_clones_persist_until_expiry"
        ):
            raise InputError("Unsupported runtime Mirror clone policies")
        offsets = parameters["clone_offsets"]
        if not isinstance(offsets, list) or len(offsets) != model["clone_count"]:
            raise InputError("Runtime Mirror clone count and offsets disagree")
        for offset in offsets:
            if not isinstance(offset, dict) or set(offset) != {"dx", "dy"}:
                raise InputError("Every runtime Mirror clone needs exactly dx and dy")
            number(offset["dx"], "runtime clone horizontal offset")
            number(offset["dy"], "runtime clone vertical offset")
        number(parameters["first_attack_delay_seconds"], "runtime clone readiness", 0)
    elif entity_id == "rocket-spear":
        if parameters["splash_layer_policy"] not in {
            "primary_target_layer_only",
            "all_declared_target_layers",
        }:
            raise InputError("Unsupported runtime Rocket Spear splash layers")
    elif entity_id == "electro-boots":
        if parameters["frozen_passives_policy"] != "continue_while_frozen_hypothesis":
            raise InputError("Unsupported runtime Boots Freeze policy")
        for field, allowed in (
            ("aura_target_kinds", {"unit", "building", "defense", "wall"}),
            ("aura_target_layers", {"ground", "air"}),
        ):
            values = parameters[field]
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(value, str) for value in values)
                or len(values) != len(set(values))
                or not set(values) <= allowed
            ):
                raise InputError("Unsupported runtime Boots target membership")
        number(model["aura_interval_seconds"], "runtime Boots aura interval", EPSILON)
        number(
            parameters["self_heal_interval_seconds"],
            "runtime Boots healing interval",
            EPSILON,
        )
        for field in (
            "first_aura_pulse_delay_seconds",
            "first_self_heal_delay_seconds",
        ):
            number(parameters[field], field, 0)
    elif entity_id in {"eternal-tome", "healing-tome"}:
        expected_membership = (
            "snapshot_at_activation_buff_follows_recipient"
            if entity_id == "healing-tome"
            else "snapshot_at_activation"
        )
        if parameters["membership"] != expected_membership:
            raise InputError("Unsupported runtime Tome membership")
        number(parameters["radius"], "runtime Tome radius", 0)
        if entity_id == "healing-tome":
            interval = number(
                parameters["pulse_interval_seconds"], "runtime Tome interval", EPSILON
            )
            first = number(
                parameters["first_pulse_delay_seconds"], "runtime Tome first pulse", 0
            )
            duration = model["duration_seconds"]
            if (
                first > interval
                or first >= duration
                or not isclose(duration / interval, model["pulse_count"])
            ):
                raise InputError("Runtime Tome pulse count and timing disagree")
            weights = parameters["healing_multipliers_by_class"]
            if (
                not isinstance(weights, dict)
                or not {"troop", "hero"} <= set(weights)
                or not set(weights) <= {"troop", "hero", "pet"}
            ):
                raise InputError(
                    "Runtime Tome healing requires explicit class multipliers"
                )
            for weight in weights.values():
                number(weight, "runtime Tome healing multiplier", 0)


def _equipment_model(instance, hero, catalog):
    if set(instance) != {"entity", "level", "parameters"}:
        raise InputError(
            "Equipment must declare its entity, level and behavior parameters"
        )
    entity_id = require(instance, "entity")
    if entity_id not in EQUIPMENT:
        raise InputError(f"Missing combat behavior for equipment: {entity_id}")
    entity = catalog.entity(entity_id)
    if entity["hero"] != hero["entity"]:
        raise InputError("Equipment belongs to a different hero")
    level = integer(require(instance, "level"), "equipment level", 1)
    if not catalog.available(entity_id, level, hero["town_hall"]):
        raise InputError("Equipment level is unavailable at this Town Hall")
    row = catalog.level(entity_id, level)
    parameters = require(instance, "parameters")
    source = identifier(require(parameters, "source"), "equipment behavior evidence")
    required = _equipment_parameter_fields(entity_id)
    if set(parameters) != required:
        raise InputError(
            "Every unresolved equipment behavior parameter must be explicit"
        )
    stats = require(row, "stats")
    model = {
        "entity": entity_id,
        "level": level,
        "ability_type": entity["abilityType"],
        "source": catalog.records[entity_id]["source"],
        "behavior_source": source,
        "parameters": deepcopy(parameters),
    }
    if entity_id == "invisibility-vial":
        model.update(
            invisibility_seconds=quantity(stats["abilityDuration"], "s"),
            damage_per_hit_increase=number(
                stats["damagePerShotIncrease"], "cloak hit bonus", 0
            ),
        )
    elif entity_id == "magic-mirror":
        if (
            parameters["clone_statistics"]
            != "snapshot_clone_totals_without_equipment_hypothesis"
        ):
            raise InputError(
                "Mirror clone statistics need an explicit supported mapping"
            )
        if parameters["source_death_policy"] != "released_clones_persist_until_expiry":
            raise InputError("Mirror clone persistence must be explicitly selected")
        number(parameters["first_attack_delay_seconds"], "clone first attack delay", 0)
        count = integer(require(stats, "clones"), "mirror clone count", 1)
        offsets = parameters["clone_offsets"]
        if not isinstance(offsets, list) or len(offsets) != count:
            raise InputError("Every Mirror clone needs an explicit deployment offset")
        for offset in offsets:
            if set(offset) != {"dx", "dy"}:
                raise InputError("Mirror offsets must exactly declare dx and dy")
            number(offset["dx"], "clone horizontal offset")
            number(offset["dy"], "clone vertical offset")
        model.update(
            invisibility_seconds=quantity(
                entity["ability"]["invisibilityDuration"], "s"
            ),
            clone_duration_seconds=quantity(stats["cloneDuration"], "s"),
            clone_hitpoints=number(stats["cloneHealth"], "clone HP", EPSILON),
            clone_dps=number(stats["cloneDps"], "clone DPS", EPSILON),
            clone_count=count,
        )
    elif entity_id == "rocket-spear":
        if parameters["splash_layer_policy"] not in {
            "primary_target_layer_only",
            "all_declared_target_layers",
        }:
            raise InputError("Rocket Spear splash layers need an explicit policy")
        model.update(
            damage_per_hit_increase=number(
                stats["damagePerShotIncrease"], "spear hit bonus", 0
            ),
            boosted_launches=integer(
                stats["numberOfAttacks"], "boosted spear launches", 1
            ),
            attack_range=quantity(entity["ability"]["attackRange"], "tiles"),
            splash_radius=quantity(entity["ability"]["areaDamageRadius"], "tiles"),
        )
    elif entity_id == "electro-boots":
        if parameters["frozen_passives_policy"] != "continue_while_frozen_hypothesis":
            raise InputError(
                "Passive effects during Freeze need an explicit supported hypothesis"
            )
        kinds = parameters["aura_target_kinds"]
        if (
            not isinstance(kinds, list)
            or not kinds
            or len(kinds) != len(set(kinds))
            or not set(kinds) <= {"unit", "building", "defense", "wall"}
        ):
            raise InputError("Electro Boots need explicit aura target kinds")
        layers = parameters["aura_target_layers"]
        if (
            not isinstance(layers, list)
            or not layers
            or len(layers) != len(set(layers))
            or not set(layers) <= {"ground", "air"}
        ):
            raise InputError("Electro Boots need explicit aura target layers")
        interval = quantity(entity["ability"]["auraAttackSpeed"], "s")
        damage = number(stats["auraDamagePerHit"], "boots pulse damage", 0)
        if not isclose(damage, stats["auraDps"] * interval):
            raise InputError("Boots DPS and pulse damage disagree in the snapshot")
        model.update(
            aura_radius=quantity(entity["ability"]["auraRadius"], "tiles"),
            aura_interval_seconds=interval,
            aura_damage=damage,
            self_healing_per_second=number(
                stats["selfHealingPerSecond"], "boots self healing", 0
            ),
        )
        for field in (
            "first_aura_pulse_delay_seconds",
            "first_self_heal_delay_seconds",
        ):
            number(parameters[field], field, 0)
        number(
            parameters["self_heal_interval_seconds"], "self healing interval", EPSILON
        )
    elif entity_id == "royal-gem":
        model["health_recovery"] = number(
            stats["healthRecovery"], "Royal Gem recovery", 0
        )
    elif entity_id in {"eternal-tome", "healing-tome"}:
        expected_membership = (
            "snapshot_at_activation_buff_follows_recipient"
            if entity_id == "healing-tome"
            else "snapshot_at_activation"
        )
        if parameters["membership"] != expected_membership:
            raise InputError(
                "Tome membership must use the explicitly supported hypothesis"
            )
        number(parameters["radius"], "Tome cast radius", 0)
        model["duration_seconds"] = quantity(stats["abilityDuration"], "s")
        if entity_id == "healing-tome":
            interval = number(
                parameters["pulse_interval_seconds"], "Tome healing interval", EPSILON
            )
            first = number(
                parameters["first_pulse_delay_seconds"], "Tome first pulse", 0
            )
            if first > interval or first >= model["duration_seconds"]:
                raise InputError(
                    "Tome first healing pulse must fall within the first interval"
                )
            count = model["duration_seconds"] / interval
            if not isclose(count, round(count)):
                raise InputError(
                    "The declared Tome pulse interval must divide its duration"
                )
            weights = parameters["healing_multipliers_by_class"]
            if (
                not isinstance(weights, dict)
                or not {"troop", "hero"} <= set(weights)
                or not set(weights) <= {"troop", "hero", "pet"}
            ):
                raise InputError(
                    "Tome healing requires separate troop and hero mappings"
                )
            for weight in weights.values():
                number(weight, "Tome healing class multiplier", 0)
            model["healing_per_second"] = number(
                stats["healingPerSecond"], "Tome healing rate", 0
            )
            model["pulse_count"] = round(count)
    _validate_runtime_equipment(model)
    return model, row


def compile_hero(
    actor,
    instance,
    entity,
    row,
    modifiers,
    catalog,
    movement_units_per_tile,
    allow_pets=False,
    allow_hero_extensions=False,
):
    if instance["entity"] not in HEROES:
        raise InputError("This hero needs additional intrinsic combat behavior")
    if instance["entity"] in EXTENDED_HEROES and not allow_hero_extensions:
        raise InputError("Extended attacking heroes require the explicit v27 scope")
    if instance["team"] != "attack" or instance["counts_for_destruction"]:
        raise InputError(
            "Only attacking heroes outside destruction counts are implemented"
        )
    if instance["statistics_mode"] != "normal":
        raise InputError("Hero statistics require the normal snapshot row")
    if entity["id"] == "grand-warden":
        allowed_modes = {"ground", "air"}
    elif entity["id"] in {"dragon-duke", "minion-prince"}:
        allowed_modes = {"air"}
    else:
        allowed_modes = {"ground"}
    if instance["mode"] not in allowed_modes:
        raise InputError("Unsupported hero movement mode")
    parameters = require(instance, "hero_parameters")
    expected = {
        "source",
        "equipment",
        "loadout_policy",
        "recovery_basis",
        "activation_policy",
        "pet_policy",
        "targeting_policy",
        "statistics_mapping",
    }
    if set(parameters) != expected:
        raise InputError(
            "Heroes require every explicit loadout and lifecycle parameter"
        )
    identifier(parameters["source"], "hero behavior evidence")
    if parameters["activation_policy"] != "manual_only_controlled_probe":
        raise InputError(
            "Automatic hero activation needs an additional calibrated handler"
        )
    pet_policies = {"omitted_for_controlled_probe"}
    if allow_pets:
        pet_policies.add("paired_pet_from_explicit_scene_assignment")
    if parameters["pet_policy"] not in pet_policies:
        raise InputError("Hero pet assignment requires its own behavior adapter")
    if (
        parameters["statistics_mapping"]
        != "base_and_equipment_additions_before_modifiers"
    ):
        raise InputError("Hero equipment statistic ordering must be explicit")
    if (
        parameters["recovery_basis"]
        != "snapshot_base_and_equipment_recovery_on_activation_hypothesis"
    ):
        raise InputError("Hero health recovery cannot be inferred from a field name")
    targeting = (
        "independent_targeting_without_army_following_controlled_probe"
        if entity["id"] == "grand-warden"
        else "retained_building_targeting_hypothesis"
    )
    if parameters["targeting_policy"] != targeting:
        raise InputError("This hero targeting policy needs an additional AI handler")
    equipment = parameters["equipment"]
    policy = parameters["loadout_policy"]
    if (
        not isinstance(equipment, list)
        or (policy == "exact_two_equipment" and len(equipment) != 2)
        or (policy == "bare_hero_controlled_probe" and equipment)
        or policy not in {"exact_two_equipment", "bare_hero_controlled_probe"}
    ):
        raise InputError(
            "A hero needs exactly two items or an explicitly bare controlled probe"
        )
    if len({item["entity"] for item in equipment}) != len(equipment):
        raise InputError("A hero cannot equip duplicate equipment")
    models = []
    hp_addition = 0
    dps_addition = 0
    recovery = number(require(row, "healthRecovery"), "snapshot base recovery", 0)
    for item in equipment:
        if item["entity"] in SUMMON_EQUIPMENT_OWNERS:
            if not allow_hero_extensions:
                raise InputError(
                    "Finite equipment children require the explicit v27+ scope"
                )
            model, gear_row = compile_summon_equipment(
                item, instance, catalog, movement_units_per_tile
            )
        elif item["entity"] in WEAPON_EQUIPMENT_OWNERS:
            if not allow_hero_extensions:
                raise InputError(
                    "Equipment release queues require the explicit v27+ scope"
                )
            model, gear_row = compile_weapon_equipment(item, instance, catalog)
        elif item["entity"] in AURA_EQUIPMENT_OWNERS:
            if not allow_pets and not allow_hero_extensions:
                raise InputError(
                    "Warden equipment fields require the explicit v25+ recipient-class scope"
                )
            model, gear_row = compile_aura_equipment(
                item, instance, catalog, movement_units_per_tile
            )
        elif item["entity"] in LOCAL_EQUIPMENT_OWNERS:
            model, gear_row = compile_local_equipment(
                item, instance, catalog, movement_units_per_tile
            )
        elif item["entity"] in RECIPE_EQUIPMENT_OWNERS:
            if not allow_hero_extensions:
                raise InputError("Recipe equipment requires the explicit v27 scope")
            model, gear_row = compile_recipe_equipment(item, instance, catalog)
        elif item["entity"] in EXTENDED_EQUIPMENT_OWNERS:
            if not allow_hero_extensions:
                raise InputError("Extended hero equipment requires the v27 scope")
            from .barbarian_king import compile_king_equipment
            from .dragon_duke import compile_duke_equipment
            from .minion_prince import compile_prince_equipment

            if instance["entity"] == "barbarian-king":
                model, gear_row = compile_king_equipment(
                    item, instance, catalog, movement_units_per_tile
                )
            elif instance["entity"] == "dragon-duke":
                model, gear_row = compile_duke_equipment(item, instance, catalog)
            else:
                model, gear_row = compile_prince_equipment(item, instance, catalog)
        else:
            model, gear_row = _equipment_model(item, instance, catalog)
        models.append(model)
        if model.get("on_hit_status") is not None:
            actor["on_hit_status"] = deepcopy(model["on_hit_status"])
        hp_addition += number(
            gear_row.get("hitpointIncrease", 0), "gear HP addition", 0
        )
        dps_addition += number(
            gear_row["stats"].get("dpsIncrease", 0), "gear DPS addition", 0
        )
        recovery += number(
            gear_row.get("hpRecoveryIncrease", 0), "gear recovery addition", 0
        )
        recovery += model.get("health_recovery", 0)
    interval = number(entity["attackSpeed"], "hero base attack interval", EPSILON)
    actor.update(
        hitpoints=(row["hitpoints"] + hp_addition) * modifiers["hitpoints_multiplier"],
        damage=(row["damagePerHit"] + dps_addition * interval)
        * modifiers["damage_multiplier"],
        attack_interval_seconds=interval * modifiers["attack_interval_multiplier"],
        range=number(entity["range"], "hero range", 0) * modifiers["range_multiplier"],
        kind="unit",
        layer=instance["mode"],
        movement=instance["mode"],
        speed=entity["movementSpeed"]
        / movement_units_per_tile
        * modifiers["movement_speed_multiplier"],
        width=0,
        height=0,
        blocking=False,
        healing_class="hero",
        hazard_class="hero",
        target_priorities=["defense", "building"],
        target_priority_tiers=(
            [["defense"], ["building"]]
            if entity["id"] == "royal-champion"
            else [["defense", "building"]]
        ),
        target_layers=(
            ["ground"] if entity["id"] == "barbarian-king" else ["ground", "air"]
        ),
    )
    attack = require(instance, "attack_parameters")
    if set(attack) != {"projectile"}:
        raise InputError(
            "Ordinary hero weapons need exactly one explicit projectile model"
        )
    actor["attack_model"] = {
        "kind": "single",
        "source": actor["source"],
        "target_kinds": ["defense", "building"],
        "target_layers": list(actor["target_layers"]),
        "maximum_hp_fraction": 0,
        "projectile": deepcopy(attack["projectile"]),
    }
    validate_pattern(actor["attack_model"])
    actor["hero_model"] = {
        "entity": instance["entity"],
        "loadout_policy": policy,
        "source": parameters["source"],
        "activation_policy": parameters["activation_policy"],
        "equipment": models,
        "health_recovery": recovery,
        "damage_multiplier": modifiers["damage_multiplier"],
        "range_multiplier": modifiers["range_multiplier"],
    }
    if entity["id"] == "dragon-duke":
        from .dragon_duke import compile_duke_intrinsic

        actor["duke_model"] = compile_duke_intrinsic(instance, entity, catalog)
    elif "duke_parameters" in instance:
        raise InputError("Duke intrinsic parameters require Dragon Duke")
    actor["entity_adapter"]["hero_parameters"] = deepcopy(parameters)
    actor["entity_adapter"]["equipment_statistics"] = {
        "added_hitpoints": hp_addition,
        "added_dps": dps_addition,
        "activation_health_recovery": recovery,
        "all_fields_current_client_verified": False,
    }
    return actor


def compile_mirror_clones(actor):
    clones = []
    for equipment in actor["hero_model"]["equipment"]:
        if equipment["entity"] != "magic-mirror":
            continue
        for index in range(equipment["clone_count"]):
            clone = deepcopy(actor)
            clone.pop("hero_model")
            clone.pop("entity_adapter")
            clone["id"] = f"{actor['id']}-mirror-clone-{index}"
            clone["source"] = equipment["source"]
            clone["spawn_seconds"] = "controlled"
            clone["hitpoints"] = (
                equipment["clone_hitpoints"]
                * actor["entity_adapter"]["modifiers"]["hitpoints_multiplier"]
            )
            clone["damage"] = (
                equipment["clone_dps"]
                * actor["attack_interval_seconds"]
                / actor["entity_adapter"]["modifiers"]["attack_interval_multiplier"]
                * actor["hero_model"]["damage_multiplier"]
            )
            clone["first_attack_seconds"] = actor["first_attack_seconds"]
            clone["summon_model"] = {
                "parent": actor["id"],
                "equipment": "magic-mirror",
                "source": equipment["source"],
                "duration_seconds": equipment["clone_duration_seconds"],
                "offset": deepcopy(equipment["parameters"]["clone_offsets"][index]),
                "first_attack_delay_seconds": equipment["parameters"][
                    "first_attack_delay_seconds"
                ],
            }
            if clone["wall_behavior"]["kind"] == "clear_obstructions":
                clone["wall_behavior"]["weapon"]["damage"] = clone["damage"]
            clones.append(clone)
    return (
        clones
        + compile_action_figure_summons(actor)
        + compile_equipment_reserves(actor)
    )


def validate_ability_command(command, actors):
    hero_id = require(command, "hero_id")
    if hero_id not in actors or "hero_model" not in actors[hero_id]:
        raise InputError("Hero ability command requires a known supported hero")
    if "targets" in command or "area" in command or "positions" in command:
        raise InputError(
            "Equipment targets and geometry come from the selected loadout"
        )


class HeroCombat:
    """Live passive pulses, one shared charge, launch buffs and clone lifetime."""

    def __init__(self, actors, combat, allow_hero_extensions=False):
        self.extensions = None
        self.models = {
            key: deepcopy(actor["hero_model"])
            for key, actor in actors.items()
            if "hero_model" in actor
        }
        self.base_weapons = {
            key: {
                field: deepcopy(actors[key][field])
                for field in ("damage", "range", "attack_model")
            }
            for key in self.models
        }
        self.used = set()
        self.visibility_until = {}
        self.invisibility_bonus_until = {}
        self.rocket_remaining = {}
        self.passive_next = {}
        self.healing_buffs = []
        self.clone_expiry = {}
        self.mirror_ids = {
            key
            for key, actor in actors.items()
            if actor.get("summon_model", {}).get("equipment") == "magic-mirror"
        }
        self.combat = combat
        self.log = []
        for key, model in self.models.items():
            if set(model) != {
                "entity",
                "loadout_policy",
                "source",
                "activation_policy",
                "equipment",
                "health_recovery",
                "damage_multiplier",
                "range_multiplier",
            }:
                raise InputError(
                    "Hero runtime models cannot hide unimplemented behavior"
                )
            if model["entity"] not in HEROES:
                raise InputError("Unsupported runtime hero entity")
            if model["entity"] in EXTENDED_HEROES and not allow_hero_extensions:
                raise InputError("Extended runtime heroes require the v27 scope")
            air_heroes = {"grand-warden", "dragon-duke", "minion-prince"}
            if actors[key]["layer"] == "air" and model["entity"] not in air_heroes:
                raise InputError("This runtime hero cannot use the air movement mode")
            if model["entity"] in {"dragon-duke", "minion-prince"} and (
                actors[key]["layer"] != "air" or actors[key]["movement"] != "air"
            ):
                raise InputError("Duke and Prince require air movement")
            identifier(model["source"], "hero runtime evidence")
            if model["activation_policy"] != "manual_only_controlled_probe":
                raise InputError("Unsupported hero automatic activation policy")
            if (
                actors[key].get("healing_class") != "hero"
                or actors[key].get("hazard_class") != "hero"
            ):
                raise InputError(
                    "Hero runtime models require explicit hero class labels"
                )
            number(model["health_recovery"], "hero activation recovery", 0)
            number(model["damage_multiplier"], "hero damage scaling", 0)
            number(model["range_multiplier"], "hero range scaling", 0)
            names = [equipment.get("entity") for equipment in model["equipment"]]
            if not set(names) <= EQUIPMENT or len(names) != len(set(names)):
                raise InputError(
                    "Hero runtime equipment requires unique supported entities"
                )
            policy = model["loadout_policy"]
            if (
                (policy == "exact_two_equipment" and len(names) != 2)
                or (policy == "bare_hero_controlled_probe" and names)
                or policy not in {"exact_two_equipment", "bare_hero_controlled_probe"}
            ):
                raise InputError(
                    "Runtime hero loadout must explicitly select two items or a bare probe"
                )
            owners = {
                **SUMMON_EQUIPMENT_OWNERS,
                **WEAPON_EQUIPMENT_OWNERS,
                **AURA_EQUIPMENT_OWNERS,
                **LOCAL_EQUIPMENT_OWNERS,
                **EXTENDED_EQUIPMENT_OWNERS,
                **RECIPE_EQUIPMENT_OWNERS,
                "invisibility-vial": "archer-queen",
                "magic-mirror": "archer-queen",
                "rocket-spear": "royal-champion",
                "electro-boots": "royal-champion",
                "royal-gem": "royal-champion",
                "eternal-tome": "grand-warden",
                "healing-tome": "grand-warden",
            }
            for equipment in model["equipment"]:
                if (
                    equipment["entity"] in SUMMON_EQUIPMENT_OWNERS
                    and not allow_hero_extensions
                ):
                    raise InputError(
                        "Equipment children require the explicit v27+ runtime"
                    )
                if (
                    equipment["entity"] in WEAPON_EQUIPMENT_OWNERS
                    and not allow_hero_extensions
                ):
                    raise InputError(
                        "Equipment release queues require the explicit v27+ runtime"
                    )
                if equipment["entity"] in AURA_EQUIPMENT_OWNERS and any(
                    actor["team"] == "attack"
                    and actor["kind"] == "unit"
                    and actor.get("buff_class") is None
                    for actor in actors.values()
                ):
                    raise InputError(
                        "Warden field recipients require explicit shared buff classes"
                    )
                if (
                    equipment["entity"] in RECIPE_EQUIPMENT_OWNERS
                    and not allow_hero_extensions
                ):
                    raise InputError("Recipe runtime equipment requires the v27 scope")
                _validate_runtime_equipment(equipment)
                if (
                    equipment["entity"] == "healing-tome"
                    and any("pet_model" in actor for actor in actors.values())
                    and "pet"
                    not in equipment["parameters"]["healing_multipliers_by_class"]
                ):
                    raise InputError(
                        "Healing Tome accompanying pets needs an explicit pet multiplier"
                    )
                if owners[equipment["entity"]] != model["entity"]:
                    raise InputError("Runtime equipment belongs to a different hero")
                if equipment["entity"] == "electro-boots":
                    self.passive_next[key] = {"aura": None, "self_heal": None}

        self.local_equipment = EquipmentLifecycles(actors)
        self.equipment_auras = EquipmentAuraCombat(actors)

    def _equipment(self, hero_id, entity):
        return next(
            (
                item
                for item in self.models[hero_id]["equipment"]
                if item["entity"] == entity
            ),
            None,
        )

    @staticmethod
    def _recipients(hero, actors, radius, time):
        return [
            key
            for key, actor in actors.items()
            if _active(actor, time)
            and actor["team"] == hero["team"]
            and actor["kind"] == "unit"
            and target_distance(center(hero), actor) <= radius + EPSILON
        ]

    def expand_commands(self, commands, actors, time, trace):
        expanded = []
        for command in commands:
            if command["kind"] != "hero_ability":
                validate_independent_deployment(command, actors)
                expanded.append(command)
                continue
            validate_ability_command(command, actors)
            hero_id = command["hero_id"]
            hero = actors[hero_id]
            status = "activated"
            if not _active(hero, time):
                status = "hero_inactive"
            elif hero_id in self.used:
                status = "ability_already_used"
            entry = {
                "time_seconds": time,
                "event": "hero_ability",
                "hero_id": hero_id,
                "status": status,
            }
            trace.append(entry)
            self.log.append(deepcopy(entry))
            if status != "activated":
                continue
            self.used.add(hero_id)
            self.local_equipment.activate(hero_id, actors, time, trace)
            self.equipment_auras.activate(hero_id, actors, time, trace)
            if self.extensions is not None:
                self.extensions.activate(hero_id, actors, time, trace)
            expanded.append(
                {
                    "id": command["id"] + "-recovery",
                    "kind": "heal",
                    "time_seconds": time,
                    "targets": [hero_id],
                    "amount": self.models[hero_id]["health_recovery"],
                }
            )
            for equipment in self.models[hero_id]["equipment"]:
                entity = equipment["entity"]
                if equipment["ability_type"] != "Active":
                    continue
                if entity in {"invisibility-vial", "magic-mirror", "action-figure"}:
                    hero["_untargetable_until"] = max(
                        hero.get("_untargetable_until", 0),
                        time + equipment["invisibility_seconds"],
                    )
                    self.visibility_until[hero_id] = hero["_untargetable_until"]
                    if entity == "invisibility-vial":
                        self.invisibility_bonus_until[hero_id] = (
                            time + equipment["invisibility_seconds"]
                        )
                    else:
                        targets = []
                        positions = {}
                        for key, clone in actors.items():
                            summon = clone.get("summon_model", {})
                            if (
                                summon.get("parent") != hero_id
                                or summon.get("equipment") != entity
                            ):
                                continue
                            targets.append(key)
                            x, y = center(hero)
                            positions[key] = {
                                "x": x + summon["offset"]["dx"],
                                "y": y + summon["offset"]["dy"],
                            }
                            if "duration_seconds" in summon:
                                self.clone_expiry[key] = (
                                    time + summon["duration_seconds"]
                                )
                            clone["next_attack"] = (
                                time + summon["first_attack_delay_seconds"]
                            )
                        expanded.append(
                            {
                                "id": command["id"]
                                + (
                                    "-mirror"
                                    if entity == "magic-mirror"
                                    else "-action-figure"
                                ),
                                "kind": "deploy",
                                "time_seconds": time,
                                "targets": targets,
                                "positions": positions,
                            }
                        )
                elif entity == "rocket-spear":
                    self.rocket_remaining[hero_id] = equipment["boosted_launches"]
                elif entity == "eternal-tome":
                    targets = self._recipients(
                        hero, actors, equipment["parameters"]["radius"], time
                    )
                    expanded.append(
                        {
                            "id": command["id"] + "-eternal",
                            "kind": "invulnerability",
                            "time_seconds": time,
                            "targets": targets,
                            "duration_seconds": equipment["duration_seconds"],
                        }
                    )
                elif entity == "healing-tome":
                    targets = [
                        key
                        for key in self._recipients(
                            hero, actors, equipment["parameters"]["radius"], time
                        )
                        if not actors[key].get("beneficial_field_immunity", False)
                    ]
                    self.healing_buffs.append(
                        {
                            "source": hero_id,
                            "equipment": equipment,
                            "targets": targets,
                            "next_pulse": time
                            + equipment["parameters"]["first_pulse_delay_seconds"],
                            "remaining": equipment["pulse_count"],
                        }
                    )
        if self.extensions is not None:
            self.extensions.prepare(actors, time, trace)
        return expanded

    def prepare(self, actors, time, trace):
        for key, expiry in list(self.clone_expiry.items()):
            mirror = key in self.mirror_ids
            expired = time >= expiry if mirror else time >= expiry - EPSILON
            eligible = actors[key]["hp"] > 0 if mirror else _active(actors[key], time)
            if expired and eligible:
                # Absolute Mirror lifetime also expires while Recall-held. Keep
                # Recall ownership for its later return and earlier real deaths.
                actors[key]["hp"] = 0
                actors[key]["death_time"] = expiry if mirror else time
                trace.append(
                    {"time_seconds": time, "event": "summon_expired", "source": key}
                )
        for key in self.models:
            actor = actors[key]
            base = self.base_weapons[key]
            damage = base["damage"]
            attack_range = base["range"]
            pattern = deepcopy(base["attack_model"])
            if self.invisibility_bonus_until.get(key, 0) > time + EPSILON:
                damage += (
                    self._equipment(key, "invisibility-vial")["damage_per_hit_increase"]
                    * self.models[key]["damage_multiplier"]
                )
            if self.rocket_remaining.get(key, 0) > 0:
                equipment = self._equipment(key, "rocket-spear")
                damage += (
                    equipment["damage_per_hit_increase"]
                    * self.models[key]["damage_multiplier"]
                )
                attack_range = (
                    equipment["attack_range"] * self.models[key]["range_multiplier"]
                )
                pattern.update(
                    kind="radial",
                    radius=equipment["splash_radius"],
                    splash_layer_policy=equipment["parameters"]["splash_layer_policy"],
                )
            actor["damage"] = damage
            actor["range"] = attack_range
            actor["attack_model"] = pattern
            self.combat.patterns[key] = pattern
            if actor.get("wall_behavior", {}).get("kind") == "clear_obstructions":
                actor["wall_behavior"]["weapon"]["damage"] = damage
        self.local_equipment.prepare(actors, time)
        for key, clocks in self.passive_next.items():
            actor = actors[key]
            if not _active(actor, time):
                continue
            equipment = self._equipment(key, "electro-boots")
            if clocks["aura"] is None:
                clocks["aura"] = (
                    actor["spawn_seconds"]
                    + equipment["parameters"]["first_aura_pulse_delay_seconds"]
                )
                clocks["self_heal"] = (
                    actor["spawn_seconds"]
                    + equipment["parameters"]["first_self_heal_delay_seconds"]
                )
        if self.extensions is not None:
            self.extensions.prepare(actors, time, trace)

        self.equipment_auras.prepare(actors, time, trace)

    def weapon_launched(self, hero_id, time, trace):
        self.local_equipment.weapon_launched(hero_id, time, trace)
        if self.extensions is not None:
            self.extensions.weapon_launched(hero_id, time, trace)
        if self.rocket_remaining.get(hero_id, 0) > 0:
            self.rocket_remaining[hero_id] -= 1
            trace.append(
                {
                    "time_seconds": time,
                    "event": "rocket_spear_launch_spent",
                    "source": hero_id,
                    "remaining": self.rocket_remaining[hero_id],
                }
            )

    def resolve_passives(self, actors, time, trace):
        damage = defaultdict(float)
        healing = defaultdict(float)
        for key, clocks in self.passive_next.items():
            hero = actors[key]
            if not _active(hero, time):
                # Death/Recall suppress emission while preserving the absolute
                # pulse grid. Revive must not replay the missed pulses.
                equipment = self._equipment(key, "electro-boots")
                intervals = {
                    "aura": equipment["aura_interval_seconds"],
                    "self_heal": equipment["parameters"]["self_heal_interval_seconds"],
                }
                for field, clock in clocks.items():
                    if clock is not None:
                        clocks[field] = skip_elapsed_pulses(
                            clock, intervals[field], time
                        )
                continue
            if not _active(hero, time):
                continue
            equipment = self._equipment(key, "electro-boots")
            if clocks["aura"] <= time + EPSILON:
                targets = []
                for target_id, target in actors.items():
                    if not _active(target, time) or target["team"] == hero["team"]:
                        continue
                    if (
                        target["kind"]
                        not in equipment["parameters"]["aura_target_kinds"]
                    ):
                        continue
                    if (
                        target["layer"]
                        not in equipment["parameters"]["aura_target_layers"]
                    ):
                        continue
                    if (
                        target_distance(center(hero), target)
                        > equipment["aura_radius"] + EPSILON
                    ):
                        continue
                    targets.append(target_id)
                    if target["immune_until"] <= time + EPSILON:
                        damage[target_id] += equipment["aura_damage"]
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "electro_boots_pulse",
                        "source": key,
                        "targets": targets,
                    }
                )
                clocks["aura"] += equipment["aura_interval_seconds"]
            if clocks["self_heal"] <= time + EPSILON:
                interval = equipment["parameters"]["self_heal_interval_seconds"]
                healing[key] += equipment["self_healing_per_second"] * interval
                clocks["self_heal"] += interval
        for buff in self.healing_buffs:
            if buff["remaining"] == 0 or buff["next_pulse"] > time + EPSILON:
                continue
            equipment = buff["equipment"]
            parameters = equipment["parameters"]
            live = []
            for key in buff["targets"]:
                actor = actors[key]
                if _active(actor, time):
                    live.append(key)
                    healing[key] += (
                        equipment["healing_per_second"]
                        * parameters["pulse_interval_seconds"]
                        * parameters["healing_multipliers_by_class"][
                            actor["healing_class"]
                        ]
                    )
            trace.append(
                {
                    "time_seconds": time,
                    "event": "healing_tome_pulse",
                    "source": buff["source"],
                    "targets": live,
                }
            )
            buff["remaining"] -= 1
            buff["next_pulse"] += parameters["pulse_interval_seconds"]
        for key, amount in self.local_equipment.resolve_healing(actors, time).items():
            healing[key] += amount
        return damage, healing

    def mirror_boundary(self, time):
        values = [
            expiry
            for key, expiry in self.clone_expiry.items()
            if key in self.mirror_ids and expiry > time
        ]
        return min(values) if values else None

    def next_boundary(self, time):
        values = list(self.visibility_until.values()) + list(self.clone_expiry.values())
        local_boundary = self.local_equipment.next_boundary(time)
        values.extend(
            clock
            for clocks in self.passive_next.values()
            for clock in clocks.values()
            if clock is not None
        )
        values.extend(
            buff["next_pulse"] for buff in self.healing_buffs if buff["remaining"] > 0
        )
        values = [value for value in values if value > time + EPSILON]
        if local_boundary is not None:
            values.append(local_boundary)
        aura_boundary = self.equipment_auras.next_boundary(time)
        if aura_boundary is not None:
            values.append(aura_boundary)
        return min(values) if values else None

    def first_crossing_delay(self, actors, routes, speeds, time, horizon):
        return self.equipment_auras.first_crossing_delay(
            actors, routes, speeds, time, horizon
        )

    def frame(self, actor_id, actor):
        if actor_id not in self.models and actor_id not in self.clone_expiry:
            return {}
        return {
            "hero_ability_used": actor_id in self.used,
            "untargetable_until": actor.get("_untargetable_until", 0),
            "rocket_spear_launches_remaining": self.rocket_remaining.get(actor_id, 0),
            "summon_expiry_seconds": self.clone_expiry.get(actor_id),
        }

    def result(self):
        return {
            "activations": self.log,
            "hero_abilities_used": sorted(self.used),
            "rocket_spear_launches_remaining": dict(self.rocket_remaining),
            "summon_expiry_seconds": dict(self.clone_expiry),
            "owner_local_equipment": self.local_equipment.result(),
            "equipment_auras": self.equipment_auras.result(),
            "automatic_activation_modeled": False,
            "game_calibrated": False,
        }
