"""Compare explicitly mapped combat quantities across independent snapshots.

Neither source is promoted to current client truth. Ambiguous raw fields, such
as Eagle Artillery's `damage`, are deliberately excluded from automatic mapping.
"""

from math import isclose

from .common import InputError


GROUPS = ("buildings", "traps", "troops", "heroes", "pets", "equipment", "spells")


def audit_extracted_source(catalog, extracted, provenance):
    index = {}
    for group in GROUPS:
        for entity in extracted.get(group, []):
            key = entity["_id"]
            if key in index:
                raise InputError("Extracted source has duplicate numeric entity IDs")
            index[key] = group, entity
    comparisons = 0
    differences = []
    unmatched = []
    semantic_exclusions = []

    def compare(entity_id, level, field, old, new, source_path, conversion):
        nonlocal comparisons
        if old is None or new is None:
            return
        if isinstance(old, bool) or isinstance(new, bool):
            equal = old is new
        elif isinstance(old, (int, float)) and isinstance(new, (int, float)):
            equal = isclose(old, new, rel_tol=1e-9, abs_tol=1e-9)
        else:
            equal = old == new
        comparisons += 1
        if not equal:
            differences.append(
                {
                    "entity": entity_id,
                    "level": level,
                    "field": field,
                    "catalog_value": old,
                    "extracted_value": new,
                    "extracted_path": source_path,
                    "conversion": conversion,
                }
            )

    for entity_id, record in sorted(catalog.records.items()):
        entity = record["entity"]
        if entity.get("base", "home") != "home":
            continue
        matched = index.get(entity.get("dataId"))
        if matched is None:
            unmatched.append(entity_id)
            continue
        group, raw = matched
        if raw.get("village", "home") != "home":
            raise InputError("Catalog mapping crosses the home-village namespace")
        prefix = f"{group}[id={raw['_id']}]"
        if "width" in raw and "size" in entity:
            compare(
                entity_id,
                None,
                "placement_size",
                entity["size"],
                f"{raw['width']}x{raw['width']}",
                prefix + ".width",
                "square placement footprint",
            )
        normal = entity.get("modes", {}).get("normal", entity)
        for field, raw_field, conversion in (
            ("attackSpeed", "attack_speed", 1000),
            ("range", "attack_range", 100),
        ):
            if raw_field in raw:
                compare(
                    entity_id,
                    None,
                    field,
                    normal.get(field),
                    raw[raw_field] / conversion,
                    prefix + "." + raw_field,
                    f"raw / {conversion}",
                )
        if "movement_speed" in raw:
            compare(
                entity_id,
                None,
                "movement_tiles_per_second",
                (
                    entity.get("movementSpeed", 0) / 8
                    if "movementSpeed" in entity
                    else None
                ),
                raw["movement_speed"] / 100,
                prefix + ".movement_speed",
                "catalog / 8; extracted / 100",
            )
        raw_levels = {row["level"]: row for row in raw.get("levels", [])}
        for row in entity.get("levels", []):
            if row.get("supercharge"):
                continue
            level = row["level"]
            other = raw_levels.get(level)
            if other is None:
                continue
            path = f"{prefix}.levels[level={level}]"
            compare(
                entity_id,
                level,
                "hitpoints",
                row.get("hitpoints"),
                other.get("hitpoints"),
                path + ".hitpoints",
                "direct",
            )
            stats = row.get("stats", {}).get("normal", {})
            dps_field = "dpsInitial" if entity_id == "inferno-tower" else "dps"
            old_dps = stats.get(dps_field, row.get("damagePerSecond"))
            raw_dps = other.get("dps")
            if raw_dps is not None and raw_dps >= 0:
                compare(
                    entity_id,
                    level,
                    dps_field,
                    old_dps,
                    raw_dps,
                    path + ".dps",
                    (
                        "initial ramp DPS"
                        if entity_id == "inferno-tower"
                        else "direct normal-mode DPS"
                    ),
                )
            for field, raw_field, conversion in (
                ("attackSpeed", "attack_speed", 1000),
                ("range", "attack_range", 100),
            ):
                if raw_field in other:
                    if field == "attackSpeed" and entity_id in {
                        "eagle-artillery",
                        "firespitter",
                    }:
                        semantic_exclusions.append(
                            {
                                "entity": entity_id,
                                "level": level,
                                "field": field,
                                "reason": "Burst/cycle interval and per-shot interval are different quantities",
                            }
                        )
                        continue
                    compare(
                        entity_id,
                        level,
                        field,
                        normal.get(field),
                        other[raw_field] / conversion,
                        path + "." + raw_field,
                        f"raw / {conversion}",
                    )
    return {
        "status": "SOURCE_COMPARISON_NOT_AUTOMATIC_CORRECTIONS",
        "catalog_snapshot": catalog.snapshot["snapshotCommit"],
        "comparison_source": provenance,
        "mapped_comparisons": comparisons,
        "differences": differences,
        "unmatched_catalog_entities": unmatched,
        "semantic_exclusions": semantic_exclusions,
        "source_conversion_policy": {
            "raw_movement_units_per_tile": 100,
            "catalog_movement_units_per_tile": 8,
            "raw_attack_time_units_per_second": 1000,
            "raw_range_units_per_tile": 100,
        },
        "limitations": [
            "An extraction publication is not a current-client calibration.",
            "Only direct normal-mode mappings are compared; no equipment ability, alternate mode, supercharge or implicit damage conversion.",
            "Placement width and combat hitbox width are different fields; this audit compares placement only.",
            "Range differences require a separate check of actor radius and hitbox conventions before any correction.",
            "Missing fields are not treated as zero and are never interpolated.",
        ],
    }
