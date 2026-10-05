"""Apply explicitly selected potions without granting equipment or unlocks."""

from copy import deepcopy

from .common import InputError, integer, require


def effective_account(account, catalog, mode):
    result = deepcopy(account)
    potions = require(account, "potions_by_mode")
    selected = require(potions, mode)
    for field in ("power", "hero"):
        if not isinstance(require(selected, field), bool):
            raise InputError("Potion choices must be explicit booleans")
    laboratory = integer(require(account, "laboratory_level"), "Laboratory level", 1)
    changed = {}
    for entity_id, current in account["levels"].items():
        if current is None or current == 0:
            continue
        entity = catalog.entity(entity_id)
        category = entity["category"]
        power = selected["power"] and category in {"troop", "spell", "siege-machine"}
        hero = selected["hero"] and category in {"hero", "pet"}
        if not power and not hero:
            continue
        eligible = []
        for row in entity["levels"]:
            if row.get("supercharge"):
                continue
            level = row["level"]
            if not catalog.available(entity_id, level, account["town_hall"]):
                continue
            if power and row.get("laboratoryRequired", laboratory) > laboratory:
                continue
            eligible.append(level)
        if not eligible:
            raise InputError(f"No confirmed potion cap for {entity_id}")
        if current > max(eligible):
            raise InputError(
                f"Owned level exceeds snapshot potion cap: {entity_id}; reconcile data first"
            )
        result["levels"][entity_id] = max(eligible)
        if result["levels"][entity_id] != current:
            changed[entity_id] = {"owned": current, "effective": max(eligible)}
    result["effective_mode"] = mode
    result["potion_changes"] = changed
    result["potion_cap_status"] = "CATALOG_CAPS_REQUIRE_PATCH_VERIFICATION"
    return result
