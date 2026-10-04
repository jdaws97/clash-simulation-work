"""Catalog quantities and explicit contracts for five attacking spell families.

The catalog supplies quantities, not undocumented pulse, collision, retargeting,
or repeated-hit rules. Every such choice remains a caller-supplied hypothesis.
"""

from copy import deepcopy

from .buffs import EXTRACTION_SOURCE
from .common import InputError, identifier, integer, number, require
from .hazards import HAZARD_CLASSES, PROTECTION_POLICIES
from .spatial import EPSILON


SPELL_CLASSES = {
    "lightning-spell": "damage",
    "earthquake-spell": "damage",
    "poison-spell": "damage",
    "invisibility-spell": "support_only",
    "overgrowth-spell": "support_only",
}
SUPPORTED_ATTACK_SPELLS = frozenset(SPELL_CLASSES)
COMMON_PARAMETERS = {
    "source",
    "caster_team",
    "radius_multiplier",
    "impact_delay_seconds",
    "geometry",
    "hidden_tesla_policy",
    "source_persistence",
}
DURATION_PARAMETERS = {"duration_basis", "duration_multiplier"}
LIGHTNING_PARAMETERS = {
    "damage_basis",
    "damage_multiplier",
    "stun_basis",
    "stun_multiplier",
    "status_protection",
    "excluded_entities",
    "unit_damage_multipliers",
}
EARTHQUAKE_PARAMETERS = {
    "building_damage_basis",
    "unit_damage_basis",
    "missing_unit_damage_percent",
    "damage_multiplier",
    "unit_damage_multipliers",
    "excluded_entities",
    "repeated_hits",
}
POISON_PARAMETERS = DURATION_PARAMETERS | {
    "damage_basis",
    "damage_multiplier",
    "pulse_interval_seconds",
    "first_pulse_offset_seconds",
    "growth_clock",
    "growth_by_field_age",
    "exit_linger_seconds",
    "status_protection",
    "class_scaling",
    "stacking_policy",
    "inactive_unit_policy",
}
INVISIBILITY_PARAMETERS = DURATION_PARAMETERS | {
    "membership_policy",
    "recipient_policy",
    "acquisition_policy",
    "immunity_policy",
    "collision_policy",
    "stacking_policy",
}
OVERGROWTH_PARAMETERS = DURATION_PARAMETERS | {
    "membership_policy",
    "recipient_policy",
    "acquisition_policy",
    "immunity_policy",
    "collision_policy",
    "stacking_policy",
    "disable_policy",
    "garrison_release_policy",
    "guardian_activation_policy",
    "builder_policy",
    "trap_policy",
}
SPECIFIC_PARAMETERS = {
    "lightning-spell": LIGHTNING_PARAMETERS,
    "earthquake-spell": EARTHQUAKE_PARAMETERS,
    "poison-spell": POISON_PARAMETERS,
    "invisibility-spell": INVISIBILITY_PARAMETERS,
    "overgrowth-spell": OVERGROWTH_PARAMETERS,
}
REPEAT_FIELDS = {
    "counter_scope",
    "protected_hits",
    "building_multipliers",
    "unit_multipliers",
    "wall_damage_multipliers",
    "wall_combo",
    "structure_hp_floor",
    "unit_hp_floor",
    "simultaneous_order",
}
POISON_FACTORS = {
    "damage_multiplier",
    "movement_reduction_multiplier",
    "attack_rate_reduction_multiplier",
}
MODEL_FIELDS = {
    "id",
    "entity",
    "source",
    "statistics_source",
    "time_seconds",
    "arrival_seconds",
    "radius",
    "position",
    "quantities",
    "parameters",
    "entity_adapter",
}
ACQUISITION_POLICY = "block_new_and_retained_acquisition_released_hits_continue"
COLLISION_POLICY = "preserve_original_obstacle_footprint"
STACKING_POLICY = "union_of_independent_field_lifetimes"
ATTACK_SPELL_RULES = {
    "attack_spell_phase": "deployments_then_field_status_then_cast_damage_before_weapon_launches",
    "attack_spell_geometry": "explicit_live_center_or_point_to_footprint_membership",
    "attack_spell_damage": "shared_health_and_source_receipts_with_no_attacker_weapon_buff",
    "attack_spell_visibility": "separate_acquisition_status_preserving_released_damage_and_collision",
    "attack_spell_poison": "explicit_pulse_growth_class_scaling_and_shared_hazard_stacking",
    "attack_spell_quake": "explicit_shared_target_counters_and_finite_repeated_hit_tables",
    "attack_spell_inventory": "one_bound_army_or_received_origin_per_cast",
    "attack_spell_termination": "positive_released_damage_continues_support_fields_do_not",
}
PRIMARY_SOURCES = {
    "invisibility_and_lightning_exclusions": (
        "https://supercell.com/en/games/clashofclans/blog/game-updates/coming-soon/"
    ),
    "overgrowth_roles": (
        "https://supercell.com/en/games/clashofclans/blog/release-notes/"
        "february-2024-update-patch-notes/"
    ),
    "quake_ground_units_and_guardian_slow": (
        "https://supercell.com/en/games/clashofclans/blog/release-notes/"
        "the-february-update-has-escaped/"
    ),
    "guardian_poison_damage_30_percent": (
        "https://supercell.com/en/games/clashofclans/blog/release-notes/"
        "the-sound-of-clash-update/"
    ),
}


def _exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != fields:
        raise InputError(f"{label} requires every explicit supported field")


def _choice(value, expected, label):
    if value != expected:
        raise InputError(f"Unsupported {label}; select {expected}")


def _unit_factors(values, *, poison=False):
    _exact(values, HAZARD_CLASSES, "Spell unit-class scaling")
    for factors in values.values():
        if poison:
            if factors is None:
                continue
            _exact(factors, POISON_FACTORS, "Poison class scaling")
            for key, value in factors.items():
                maximum = 1 if key != "damage_multiplier" else None
                number(value, key, 0, maximum)
        else:
            number(factors, "spell unit damage multiplier", 0)


def validate_parameters(entity_id, parameters):
    _exact(
        parameters,
        COMMON_PARAMETERS | SPECIFIC_PARAMETERS[entity_id],
        f"{entity_id} parameters",
    )
    identifier(parameters["source"], "attacking spell behavior evidence")
    _choice(parameters["caster_team"], "attack", "spell caster team")
    number(parameters["radius_multiplier"], "spell radius multiplier", EPSILON)
    number(parameters["impact_delay_seconds"], "spell impact delay", 0)
    if parameters["geometry"] not in {
        "live_center_distance",
        "point_to_live_target_footprint",
    }:
        raise InputError("Spell geometry must explicitly select a supported metric")
    _choice(
        parameters["hidden_tesla_policy"],
        "exclude_hidden_teslas",
        "spell interaction with unrevealed Teslas",
    )
    _choice(
        parameters["source_persistence"],
        "released_cast_independent_of_attacker_survival",
        "released spell persistence",
    )
    if "damage_multiplier" in parameters:
        number(parameters["damage_multiplier"], "spell damage multiplier", 0)
    if "duration_multiplier" in parameters:
        _choice(
            parameters["duration_basis"], "snapshot_spellDuration", "spell duration"
        )
        number(parameters["duration_multiplier"], "spell duration multiplier", EPSILON)
    if "excluded_entities" in parameters:
        exclusions = parameters["excluded_entities"]
        if not isinstance(exclusions, list) or len(set(exclusions)) != len(exclusions):
            raise InputError("Spell entity immunities must be an explicit unique list")
        for entity in exclusions:
            identifier(entity, "spell excluded entity")
    if "unit_damage_multipliers" in parameters:
        _unit_factors(parameters["unit_damage_multipliers"])
    if "status_protection" in parameters:
        if parameters["status_protection"] not in PROTECTION_POLICIES:
            raise InputError("Spell protection/status interaction must be explicit")
    if entity_id == "lightning-spell":
        _choice(
            parameters["damage_basis"],
            "snapshot_damage_is_one_total_impact",
            "Lightning damage",
        )
        _choice(
            parameters["stun_basis"],
            "snapshot_stunTime_pauses_remaining_attack_work",
            "Lightning stun clock",
        )
        number(parameters["stun_multiplier"], "Lightning stun multiplier", 0)
    elif entity_id == "earthquake-spell":
        _choice(
            parameters["building_damage_basis"],
            "snapshot_buildingDamagePercent_of_maximum_hp",
            "Earthquake building damage",
        )
        if parameters["unit_damage_basis"] not in {
            "snapshot_troopDamagePercent_of_maximum_hp_ground_only",
            "explicit_missing_troop_damage_hypothesis_ground_only",
        }:
            raise InputError("Earthquake unit damage needs its explicit quantity basis")
        missing = parameters["missing_unit_damage_percent"]
        if missing is not None:
            number(missing, "missing Earthquake troop damage hypothesis", 0, 100)
        repeat = parameters["repeated_hits"]
        _exact(repeat, REPEAT_FIELDS, "Earthquake repeated hits")
        _choice(
            repeat["counter_scope"],
            "shared_per_target_across_owned_and_received_earthquake_spells",
            "Earthquake counter scope",
        )
        if repeat["protected_hits"] not in {
            "advance_counter",
            "do_not_advance_counter",
        }:
            raise InputError("Earthquake protected-hit counting must be selected")
        _choice(
            repeat["wall_combo"],
            "catalog_four_counted_quakes_destroy_wall",
            "Earthquake wall combo",
        )
        _choice(
            repeat["simultaneous_order"],
            "arrival_then_cast_id_with_sequential_virtual_hp",
            "simultaneous Earthquake ordering",
        )
        for key in (
            "building_multipliers",
            "unit_multipliers",
            "wall_damage_multipliers",
        ):
            table = repeat[key]
            if not isinstance(table, list) or not table:
                raise InputError(
                    "Earthquake needs explicit repeated-hit multiplier tables"
                )
            for value in table:
                number(value, "Earthquake repeated-hit multiplier", 0)
        if len(repeat["wall_damage_multipliers"]) != 3:
            raise InputError("The three pre-combo wall hits need explicit multipliers")
        for key in ("structure_hp_floor", "unit_hp_floor"):
            number(repeat[key], "Earthquake surviving HP floor", 0)
    elif entity_id == "poison-spell":
        _choice(
            parameters["damage_basis"],
            "snapshot_maxDamagePerSecond_is_maximum_dps",
            "Poison damage",
        )
        _choice(
            parameters["growth_clock"],
            "explicit_field_age_hypothesis",
            "Poison growth clock",
        )
        _choice(
            parameters["stacking_policy"],
            "additive_damage_strongest_slow_across_shared_hazards",
            "Poison stacking",
        )
        _choice(
            parameters["inactive_unit_policy"],
            "no_damage_or_status_while_inactive_or_underground",
            "Poison inactive-unit policy",
        )
        number(parameters["pulse_interval_seconds"], "Poison pulse interval", EPSILON)
        number(parameters["first_pulse_offset_seconds"], "Poison first pulse", 0)
        number(parameters["exit_linger_seconds"], "Poison status linger", 0)
        _unit_factors(parameters["class_scaling"], poison=True)
        growth = parameters["growth_by_field_age"]
        if not isinstance(growth, list) or not growth:
            raise InputError("Poison needs an explicit DPS growth curve")
        previous_age, previous_multiplier = -1, 0
        for index, stage in enumerate(growth):
            _exact(stage, {"after_seconds", "dps_multiplier"}, "Poison growth stage")
            age = number(stage["after_seconds"], "Poison growth age", 0)
            factor = number(stage["dps_multiplier"], "Poison growth factor", 0, 1)
            if (
                age <= previous_age
                or factor < previous_multiplier
                or (index == 0 and age != 0)
            ):
                raise InputError(
                    "Poison growth must start at zero and increase in age and strength"
                )
            previous_age, previous_multiplier = age, factor
    else:
        _choice(
            parameters["acquisition_policy"], ACQUISITION_POLICY, "spell acquisition"
        )
        _choice(
            parameters["collision_policy"],
            COLLISION_POLICY,
            "invisible building collision",
        )
        _choice(
            parameters["stacking_policy"], STACKING_POLICY, "visibility spell stacking"
        )
        if entity_id == "invisibility-spell":
            _choice(
                parameters["membership_policy"],
                "continuous_live_membership_no_linger",
                "Invisibility membership",
            )
            _choice(
                parameters["recipient_policy"],
                "both_teams_except_walls_and_siege",
                "Invisibility recipients",
            )
            _choice(
                parameters["immunity_policy"],
                "acquisition_only_no_damage_immunity",
                "Invisibility protection",
            )
        else:
            _choice(
                parameters["membership_policy"],
                "capture_live_structures_at_arrival",
                "Overgrowth membership",
            )
            _choice(
                parameters["recipient_policy"],
                "defending_buildings_and_defenses_excluding_walls_and_units",
                "Overgrowth recipients",
            )
            _choice(
                parameters["immunity_policy"],
                "full_damage_immunity_for_captured_structures",
                "Overgrowth protection",
            )
            _choice(
                parameters["disable_policy"],
                "freeze_shared_weapon_work_released_attacks_persist",
                "Overgrowth weapon clock",
            )
            _choice(
                parameters["garrison_release_policy"],
                "garrison_release_continues_without_overgrowth_pause",
                "Overgrowth garrison release",
            )
            _choice(
                parameters["guardian_activation_policy"],
                "dormant_guardian_activation_continues",
                "Overgrowth Guardian activation",
            )
            _choice(
                parameters["builder_policy"],
                "reuse_explicit_hut_freeze_linkage",
                "Overgrowth Builder policy",
            )
            _choice(
                parameters["trap_policy"], "traps_unaffected", "Overgrowth trap policy"
            )


def compile_attack_spell(instance, catalog):
    entity_id = require(instance, "entity")
    if entity_id not in SUPPORTED_ATTACK_SPELLS:
        raise InputError("Unsupported attacking spell family")
    level = integer(require(instance, "level"), "attacking spell level", 1)
    town_hall = integer(
        require(instance, "town_hall"),
        "attacking spell Town Hall",
        1,
        catalog.maximum_town_hall,
    )
    if not catalog.available(entity_id, level, town_hall):
        raise InputError(
            "Attacking spell level is unavailable at the declared Town Hall"
        )
    parameters = require(instance, "parameters")
    validate_parameters(entity_id, parameters)
    for excluded in parameters.get("excluded_entities", []):
        catalog.entity(excluded)
    entity, row = catalog.entity(entity_id), catalog.level(entity_id, level)
    radius = (
        require(row, "radius")
        if entity_id == "earthquake-spell"
        else require(entity, "radius")
    )
    quantities = {}
    if entity_id == "lightning-spell":
        quantities = {
            "damage": number(require(row, "damage"), "Lightning total damage", 0)
            * parameters["damage_multiplier"],
            "stun_seconds": number(require(entity, "stunTime"), "Lightning stun", 0)
            * parameters["stun_multiplier"],
        }
    elif entity_id == "earthquake-spell":
        has_troop_damage = "troopDamagePercent" in row
        if has_troop_damage:
            _choice(
                parameters["unit_damage_basis"],
                "snapshot_troopDamagePercent_of_maximum_hp_ground_only",
                "Earthquake troop statistic",
            )
            if parameters["missing_unit_damage_percent"] is not None:
                raise InputError(
                    "A present Earthquake troop statistic cannot be overridden"
                )
            troop_percent = row["troopDamagePercent"]
        else:
            _choice(
                parameters["unit_damage_basis"],
                "explicit_missing_troop_damage_hypothesis_ground_only",
                "missing Earthquake troop statistic",
            )
            troop_percent = parameters["missing_unit_damage_percent"]
            if troop_percent is None:
                raise InputError(
                    "Missing Earthquake troop damage requires an explicit numeric hypothesis"
                )
        quantities = {
            "building_fraction": number(
                require(row, "buildingDamagePercent"),
                "Earthquake building percent",
                0,
                100,
            )
            / 100
            * parameters["damage_multiplier"],
            "unit_fraction": number(troop_percent, "Earthquake troop percent", 0, 100)
            / 100
            * parameters["damage_multiplier"],
        }
    elif entity_id == "poison-spell":
        quantities = {
            "duration_seconds": number(
                require(entity, "spellDuration"), "Poison duration", EPSILON
            )
            * parameters["duration_multiplier"],
            "maximum_dps": number(
                require(row, "maxDamagePerSecond"), "Poison maximum DPS", 0
            )
            * parameters["damage_multiplier"],
            "movement_reduction": number(
                require(row, "speedDecrease"), "Poison movement reduction", 0, 100
            )
            / 100,
            "attack_rate_reduction": number(
                require(row, "attackRateDecrease"), "Poison attack reduction", 0, 100
            )
            / 100,
        }
    else:
        quantities = {
            "duration_seconds": number(
                require(row, "spellDuration"), "spell duration", EPSILON
            )
            * parameters["duration_multiplier"],
        }
    cast_time = number(require(instance, "time_seconds"), "spell cast time", 0)
    model = {
        "id": identifier(require(instance, "id"), "spell cast id"),
        "entity": entity_id,
        "source": parameters["source"],
        "statistics_source": catalog.records[entity_id]["source"],
        "time_seconds": cast_time,
        "arrival_seconds": cast_time + parameters["impact_delay_seconds"],
        "radius": number(radius, "spell radius", 0) * parameters["radius_multiplier"],
        "position": [
            number(require(instance, "x"), "spell x", 0),
            number(require(instance, "y"), "spell y", 0),
        ],
        "quantities": quantities,
        "parameters": deepcopy(parameters),
        "entity_adapter": {
            "entity": entity_id,
            "level": level,
            "town_hall": town_hall,
            "housing_space": require(entity, "housingSpace"),
            "termination_classification": SPELL_CLASSES[entity_id],
            "snapshot_verification": catalog.records[entity_id]["verification"],
            "behavior_verification": "explicit_uncalibrated_spell_contract",
            "source_audit": {
                "extraction_source": EXTRACTION_SOURCE,
                "quantity_selection": "catalog_damage_percent_duration_and_slow_fields",
                "extraction_duration_zero": "not_used_as_a_spell_lifetime",
                "extraction_earthquake_damage_zero": "not_used_as_percentage_damage",
                "primary_sources": deepcopy(PRIMARY_SOURCES),
                "guardian_poison": "April_2026_30_percent_damage_supersedes_February_full_damage_slow_scaling_stays_explicit",
                "unlock_selection": "declared_catalog_availability_not_unreliable_extraction_level_one_unlock",
            },
        },
    }
    validate_attack_spell(model)
    return model


def validate_attack_spell(model):
    _exact(model, MODEL_FIELDS, "Compiled attacking spell")
    entity_id = model["entity"]
    if entity_id not in SUPPORTED_ATTACK_SPELLS:
        raise InputError("Unknown compiled attacking spell family")
    validate_parameters(entity_id, model["parameters"])
    for field in ("id", "source", "statistics_source"):
        identifier(model[field], "compiled spell evidence or identity")
    time = number(model["time_seconds"], "compiled spell cast time", 0)
    arrival = number(model["arrival_seconds"], "compiled spell arrival", time)
    if abs(arrival - time - model["parameters"]["impact_delay_seconds"]) > EPSILON:
        raise InputError("Compiled spell arrival disagrees with its declared delay")
    number(model["radius"], "compiled spell radius", 0)
    if not isinstance(model["position"], (list, tuple)) or len(model["position"]) != 2:
        raise InputError("Spell placement needs two coordinates")
    for value in model["position"]:
        number(value, "spell placement coordinate", 0)
    expected = {
        "lightning-spell": {"damage", "stun_seconds"},
        "earthquake-spell": {"building_fraction", "unit_fraction"},
        "poison-spell": {
            "duration_seconds",
            "maximum_dps",
            "movement_reduction",
            "attack_rate_reduction",
        },
        "invisibility-spell": {"duration_seconds"},
        "overgrowth-spell": {"duration_seconds"},
    }[entity_id]
    _exact(model["quantities"], expected, "Compiled spell quantities")
    for key, value in model["quantities"].items():
        minimum = EPSILON if key == "duration_seconds" else 0
        maximum = 1 if key.endswith("_reduction") else None
        number(value, "compiled spell quantity", minimum, maximum)
    if entity_id == "poison-spell":
        duration = model["quantities"]["duration_seconds"]
        parameters = model["parameters"]
        if parameters["first_pulse_offset_seconds"] >= duration:
            raise InputError("Poison first pulse must precede expiry")
        if any(
            stage["after_seconds"] >= duration
            for stage in parameters["growth_by_field_age"]
        ):
            raise InputError("Poison growth stages must precede expiry")
    adapter = model["entity_adapter"]
    if (
        adapter.get("entity") != entity_id
        or adapter.get("termination_classification") != SPELL_CLASSES[entity_id]
    ):
        raise InputError("Spell identity and mechanism classification disagree")


def poison_fields(model):
    """Partition recipient classes to reuse the shared hazard clocks and stacking."""
    validate_attack_spell(model)
    if model["entity"] != "poison-spell":
        raise InputError("Only Poison produces persistent poison fields")
    parameters, quantities = model["parameters"], model["quantities"]
    fields = []
    for unit_class, factors in sorted(parameters["class_scaling"].items()):
        if factors is None:
            continue
        field = {
            "id": f"{model['id']}:poison:{unit_class}",
            "source": model["source"],
            "source_team": "attack",
            "start_seconds": model["arrival_seconds"],
            "duration_seconds": quantities["duration_seconds"],
            "pulse_interval_seconds": parameters["pulse_interval_seconds"],
            "first_pulse_offset_seconds": parameters["first_pulse_offset_seconds"],
            "maximum_dps": quantities["maximum_dps"] * factors["damage_multiplier"],
            "growth_by_field_age": deepcopy(parameters["growth_by_field_age"]),
            "area": {
                "x": model["position"][0],
                "y": model["position"][1],
                "radius": model["radius"],
                "target_team": "defense",
                "target_kinds": ["unit"],
                "target_layers": ["ground", "air"],
            },
            "movement_multiplier": 1
            - quantities["movement_reduction"]
            * factors["movement_reduction_multiplier"],
            "attack_rate_multiplier": 1
            - quantities["attack_rate_reduction"]
            * factors["attack_rate_reduction_multiplier"],
            "exit_linger_seconds": parameters["exit_linger_seconds"],
            "protection_policy": parameters["status_protection"],
            "excluded_classes": sorted(HAZARD_CLASSES - {unit_class}),
        }
        if unit_class == "guardian":
            # Scaling is already in maximum_dps; this required separate guard
            # explicitly prevents the shared hazard from multiplying it twice.
            field["guardian_damage_multiplier"] = 1
        fields.append(field)
    return fields


def validate_spell_classifications(policy):
    """Bind the user's termination choices to the implemented spell mechanisms."""
    for entry in policy["spell_inventory"]:
        expected = SPELL_CLASSES.get(entry["entity"])
        if expected is not None and entry["classification"] != expected:
            raise InputError(
                "Termination classification disagrees with implemented spell mechanics"
            )
