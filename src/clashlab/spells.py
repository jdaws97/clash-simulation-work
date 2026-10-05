"""Source-linked spell commands for the restricted spatial combat scopes."""

from .common import InputError, identifier, integer, number, require


def compile_freeze_spell(instance, catalog):
    if require(instance, "entity") != "freeze-spell":
        raise InputError("This status-command adapter requires Freeze Spell")
    level = integer(require(instance, "level"), "Freeze level", 1)
    town_hall = integer(
        require(instance, "town_hall"), "Freeze Town Hall", 1, catalog.maximum_town_hall
    )
    if not catalog.available("freeze-spell", level, town_hall):
        raise InputError("Freeze level is unavailable at the declared Town Hall")
    parameters = require(instance, "parameters")
    if set(parameters) != {
        "duration_multiplier",
        "radius_multiplier",
        "caster_team",
        "source",
    }:
        raise InputError(
            "Freeze needs explicit duration/radius modifiers and caster team"
        )
    identifier(parameters["source"], "Freeze modifier and behavior evidence")
    if parameters["caster_team"] != "attack":
        raise InputError("This adapter covers an attacking Freeze Spell")
    entity = catalog.entity("freeze-spell")
    row = catalog.level("freeze-spell", level)
    return {
        "id": identifier(require(instance, "id"), "Freeze cast id"),
        "kind": "area_freeze",
        "source": catalog.records["freeze-spell"]["source"],
        "time_seconds": number(
            require(instance, "time_seconds"), "Freeze cast time", 0
        ),
        "duration_seconds": number(
            require(row, "spellDuration"), "Freeze duration", 0.000001
        )
        * number(
            parameters["duration_multiplier"], "Freeze duration multiplier", 0.000001
        ),
        "area": {
            "x": number(require(instance, "x"), "Freeze center x", 0),
            "y": number(require(instance, "y"), "Freeze center y", 0),
            "radius": number(require(entity, "radius"), "Freeze radius", 0)
            * number(
                parameters["radius_multiplier"], "Freeze radius multiplier", 0.000001
            ),
            "target_team": "defense",
            "target_kinds": ["unit", "defense", "building"],
            "target_layers": ["ground", "air"],
        },
        "entity_adapter": {
            "entity": "freeze-spell",
            "level": level,
            "town_hall": town_hall,
            "housing_space": require(entity, "housingSpace"),
            "snapshot_verification": catalog.records["freeze-spell"]["verification"],
            "behavior_verification": "conditional_area_status_not_replay_validated",
            "parameters": parameters,
        },
    }
