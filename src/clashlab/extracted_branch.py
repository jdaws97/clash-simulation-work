"""Opt-in, field-specific extraction branches with derived shot consistency."""

from copy import deepcopy
from math import isclose

from .common import InputError, identifier, number, require, stable_id


POLICY = "selected_extracted_fields_without_claiming_current_client_verification"


def build_extracted_branch(catalog, extracted, provenance, selection):
    if "statistic_branch" in catalog.snapshot:
        raise InputError("Extracted branches must start from the base catalog")
    if not isinstance(selection, list) or not selection:
        raise InputError("Select specific extracted fields before building a branch")
    identifier(require(provenance, "commit"), "extracted source commit")
    identifier(require(provenance, "url"), "extracted source URL")
    by_data_id = {}
    for group in ("troops", "heroes", "pets", "buildings"):
        for entity in extracted.get(group, []):
            if entity.get("village", "home") == "home":
                if entity["_id"] in by_data_id:
                    raise InputError("Duplicate extracted home entity IDs")
                by_data_id[entity["_id"]] = entity
    branch = deepcopy(catalog)
    applied = []
    seen = set()
    for request in selection:
        if not isinstance(request, dict) or set(request) != {
            "entity",
            "level",
            "field",
            "expected_catalog_value",
        }:
            raise InputError(
                "Every extracted selection needs identity, level, field and expected old value"
            )
        entity_id = request["entity"]
        level = request["level"]
        field = request["field"]
        identity = entity_id, level, field
        if identity in seen:
            raise InputError("Duplicate extracted field selection")
        seen.add(identity)
        entity = branch.entity(entity_id)
        raw = by_data_id.get(entity.get("dataId"))
        if raw is None:
            raise InputError("No exact home-entity mapping in the extracted source")
        if field == "movementSpeed":
            if level is not None:
                raise InputError("Movement speed belongs to the entity, not a level")
            target = entity
            value = (
                number(require(raw, "movement_speed"), "extracted movement speed", 0)
                * 8
                / 100
            )
            source_path = "movement_speed"
        elif field in {"hitpoints", "dps"}:
            row = branch.level(entity_id, level)
            raw_rows = [
                item for item in raw.get("levels", []) if item["level"] == level
            ]
            if len(raw_rows) != 1:
                raise InputError("No unique extracted level")
            raw_row = raw_rows[0]
            target = (
                row
                if field == "hitpoints"
                else require(require(row, "stats"), "normal")
            )
            value = number(require(raw_row, field), "extracted combat statistic", 1)
            source_path = f"levels[level={level}].{field}"
        else:
            raise InputError(
                "This branch only maps HP, normal troop DPS and movement speed"
            )
        before = require(target, field)
        if before != request["expected_catalog_value"]:
            raise InputError("Catalog field changed since this selection was reviewed")
        evidence = {
            "entity": entity_id,
            "level": level,
            "field": field,
            "previous_value": before,
            "value": value,
            "source": provenance["url"],
            "source_path": f"id={raw['_id']}.{source_path}",
            "verification": "selected_community_extraction_not_client_confirmation",
        }
        if field == "dps":
            if entity.get("category") != "troop" or entity.get("damageType") not in {
                "single",
                "splash",
                "chain",
            }:
                raise InputError(
                    "DPS-to-shot conversion is restricted to direct troop weapons"
                )
            interval = number(
                require(entity, "attackSpeed"), "catalog hit interval", 0.000001
            )
            extracted_interval = (
                number(require(raw, "attack_speed"), "extracted hit interval", 1) / 1000
            )
            if not isclose(interval, extracted_interval):
                raise InputError("Conflicting attack intervals require separate review")
            if not isclose(require(target, "damagePerShot"), before * interval):
                raise InputError(
                    "Catalog DPS and shot damage do not have a direct interval mapping"
                )
            target["damagePerShot"] = value * interval
            evidence["derived_damage_per_shot"] = target["damagePerShot"]
            evidence["derivation"] = (
                "selected extracted DPS times independently matching hit interval"
            )
        target[field] = value
        branch.records[entity_id].setdefault("field_provenance", []).append(evidence)
        applied.append(evidence)
    policy = {
        "kind": POLICY,
        "source_commit": provenance["commit"],
        "source_content_fingerprint": stable_id(extracted),
        "selection": deepcopy(selection),
    }
    branch.snapshot["statistic_branch"] = {
        "id": "selected-extracted-combat-fields",
        "kind": "extracted_fields",
        "policy": policy,
        "applied_fields": applied,
        "fingerprint": stable_id({"policy": policy, "applied": applied}),
        "base_snapshot_is_unchanged": True,
        "full_current_patch_verified": False,
        "unspecified_levels_are_interpolated": False,
    }
    return branch
