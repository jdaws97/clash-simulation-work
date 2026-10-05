"""Conditional damage arithmetic with explicit coverage, repair, and modifiers.

This calculator does not choose a Fireball target, infer spell coverage, predict
builder actions, or invent the diminishing effect of repeated Earthquakes.
"""

from copy import deepcopy

from .common import InputError, identifier, integer, number, require


RULES = {
    "arithmetic": "unrounded_real_number_sensitivity",
    "event_order": "explicit_sequence",
    "earthquake_basis": "modified_maximum_hp",
    "earthquake_repetition": "explicit_effective_multiplier_per_target_per_hit",
    "repair": "explicit_delivered_hp_capped_at_maximum",
    "death": "permanent_no_later_repair_or_damage",
    "coverage_and_protection": "explicit_per_target_per_event",
    "targets": "independent_damage_cases",
}


def _boolean_map(event, key, target_ids):
    values = require(event, key)
    if set(values) != target_ids or any(
        not isinstance(value, bool) for value in values.values()
    ):
        raise InputError(f"{key} must explicitly cover every target with booleans")
    return values


def _numeric_map(event, key, target_ids, maximum=None):
    values = require(event, key)
    if set(values) != target_ids:
        raise InputError(f"{key} must explicitly cover every target")
    for value in values.values():
        number(value, key, 0, maximum)
    return values


def _provenance(catalog, entity_id, level):
    entry = catalog.records[entity_id]
    return {
        "entity": entity_id,
        "level": level,
        "source": entry["source"],
        "verification": entry["verification"],
    }


def damage_margins(specification, catalog):
    experiment_id = identifier(require(specification, "id"), "margin experiment id")
    purpose = identifier(require(specification, "purpose"), "margin experiment purpose")
    if require(specification, "model_rules") != RULES:
        raise InputError("Conditional damage conventions must be explicitly selected")
    fireball_level = integer(
        require(specification, "fireball_level"), "Fireball level", 1
    )
    quake_level = integer(
        require(specification, "earthquake_level"), "Earthquake level", 1
    )
    fireball = catalog.level("fireball", fireball_level)
    earthquake = catalog.level("earthquake-spell", quake_level)
    fireball_damage = number(
        require(require(fireball, "stats"), "projectileDamage"),
        "snapshot Fireball damage",
        0,
    )
    quake_fraction = (
        number(
            require(earthquake, "buildingDamagePercent"),
            "snapshot Earthquake percentage",
            0,
            100,
        )
        / 100
    )
    targets = {}
    for target in require(specification, "targets"):
        target_id = identifier(require(target, "id"), "damage target id")
        if target_id in targets:
            raise InputError("Damage target IDs must be unique")
        entity_id = require(target, "entity")
        entity = catalog.entity(entity_id)
        if entity["category"] not in {"defense", "town-hall"}:
            raise InputError("This damage calculator requires defenses or Town Halls")
        level = integer(require(target, "level"), "defense level", 1)
        town_hall = integer(require(target, "town_hall"), "target Town Hall", 1)
        supercharge = require(target, "supercharge")
        if not isinstance(supercharge, bool):
            raise InputError("Supercharge selection must be explicit")
        if supercharge:
            raise InputError("Supercharge stages need a base-level/stage adapter")
        if not catalog.available(entity_id, level, town_hall):
            raise InputError("Defense level is unavailable at the declared Town Hall")
        row = catalog.level(entity_id, level)
        multiplier = number(
            require(target, "maximum_hp_multiplier"), "maximum HP multiplier", 0
        )
        if multiplier == 0:
            raise InputError("Maximum HP multiplier must be positive")
        fraction = number(
            require(target, "initial_hp_fraction"), "initial HP fraction", 0, 1
        )
        maximum_hp = (
            number(require(row, "hitpoints"), "snapshot defense HP", 1) * multiplier
        )
        targets[target_id] = {
            "entity": entity_id,
            "name": entity["name"],
            "level": level,
            "town_hall": town_hall,
            "maximum_hp": maximum_hp,
            "initial_hp": maximum_hp * fraction,
            "hp": maximum_hp * fraction,
            "destroyed_at_event": "initial_state" if fraction == 0 else None,
            "statistics": _provenance(catalog, entity_id, level),
            "timeline": [],
        }
    if not targets:
        raise InputError("Damage margins require targets")
    target_ids = set(targets)
    event_ids = set()
    events = require(specification, "hit_sequence")
    if not events:
        raise InputError("Damage margins require an explicit hit sequence")
    for event in events:
        event_id = identifier(require(event, "id"), "damage event id")
        if event_id in event_ids:
            raise InputError("Damage event IDs must be unique")
        event_ids.add(event_id)
        kind = require(event, "kind")
        identifier(require(event, "source"), "event assumption/evidence source")
        if kind == "repair":
            amounts = _numeric_map(event, "delivered_hp", target_ids)
        elif kind in {"fireball", "earthquake"}:
            covered = _boolean_map(event, "covered", target_ids)
            blocked = _boolean_map(event, "blocked_by_protection", target_ids)
            if kind == "earthquake":
                multipliers = _numeric_map(
                    event, "effective_hit_multiplier", target_ids, 1
                )
                identifier(
                    require(event, "multiplier_source"), "Earthquake repetition source"
                )
            else:
                damage_multiplier = number(
                    require(event, "damage_multiplier"), "Fireball damage multiplier", 0
                )
        else:
            raise InputError("Unsupported conditional damage event")
        for target_id, target in targets.items():
            before = target["hp"]
            result = "applied"
            nominal_damage = 0
            delivered_repair = 0
            if before == 0:
                result = "already_destroyed"
            elif kind == "repair":
                delivered_repair = min(
                    amounts[target_id], target["maximum_hp"] - before
                )
                target["hp"] += delivered_repair
            elif not covered[target_id]:
                result = "outside_declared_coverage"
            elif blocked[target_id]:
                result = "blocked_by_declared_protection"
            else:
                nominal_damage = (
                    fireball_damage * damage_multiplier
                    if kind == "fireball"
                    else target["maximum_hp"] * quake_fraction * multipliers[target_id]
                )
                target["hp"] = max(before - nominal_damage, 0)
                if target["hp"] == 0:
                    target["destroyed_at_event"] = event_id
            row = {
                "event_id": event_id,
                "kind": kind,
                "result": result,
                "hp_before": before,
                "nominal_damage": nominal_damage,
                "delivered_repair": delivered_repair,
                "hp_after": target["hp"],
            }
            if kind == "fireball" and nominal_damage > 0:
                row["damage_margin_before_hit"] = nominal_damage - before
            target["timeline"].append(row)
    return {
        "status": "CONDITIONAL_SNAPSHOT_DAMAGE_ARITHMETIC_NOT_GAME_PREDICTION",
        "id": experiment_id,
        "purpose": purpose,
        "snapshot_commit": catalog.snapshot["snapshotCommit"],
        "model_rules": RULES,
        "declared_hit_sequence": deepcopy(events),
        "fireball": {
            **_provenance(catalog, "fireball", fireball_level),
            "damage": fireball_damage,
        },
        "earthquake": {
            **_provenance(catalog, "earthquake-spell", quake_level),
            "first_hit_fraction_before_explicit_multiplier": quake_fraction,
        },
        "targets": targets,
        "full_game_prediction": False,
        "limitations": [
            "Snapshot values remain unverified and may disagree with the current patch",
            "Coverage, protection, modifiers, hit order and delivered repair are declared cases, not inferred from a base",
            "Repeated Earthquake multipliers must be supplied; no diminishing formula is invented",
            "Arithmetic is unrounded; sub-HP margins need verified game rounding",
            "Fireball target manipulation, travel time, builder pathing, wall damage, and full battle outcomes are not simulated here",
            "Recipe legality and account ownership are checked separately by validate-army",
        ],
    }
