"""Conflict-aware previews of read-only game layout observations.

This module deliberately produces previews, not battle-ready blueprints. Memory
copies are observations, not votes: one conflicting copy is enough to leave a
field unresolved, regardless of how many matching copies exist elsewhere.
"""

from collections import Counter, defaultdict
from copy import deepcopy
import json
import re

from .layout_records import select_layout_fields


def select_home_observations(candidates, catalog):
    """Filter the data namespace before resolving reused village object IDs."""
    home_data_ids = {
        entry["entity"]["dataId"]
        for entry in catalog.records.values()
        if entry["entity"].get("base") == "home"
        and "dataId" in entry["entity"]
        and "size" in entry["entity"]
    }
    return [
        candidate
        for candidate in candidates
        if candidate["fields"].get("data") in home_data_ids
    ]


def resolve_layout_objects(candidates):
    """Reconcile observed fields without inferring absent fields or freshness."""
    grouped = defaultdict(list)
    for candidate in candidates:
        fields = select_layout_fields(candidate["fields"])
        if "id" in fields:
            grouped[fields["id"]].append(fields)
    resolved = []
    for object_id, observations in sorted(grouped.items()):
        values = defaultdict(dict)
        for observation in observations:
            for key, value in observation.items():
                signature = json.dumps(value, sort_keys=True)
                values[key][signature] = value
        agreed = {}
        conflicts = {}
        for key, observed in sorted(values.items()):
            alternatives = [observed[key] for key in sorted(observed)]
            if len(alternatives) == 1:
                agreed[key] = deepcopy(alternatives[0])
            else:
                conflicts[key] = deepcopy(alternatives)
        resolved.append(
            {
                "object_id": object_id,
                "agreed_fields": agreed,
                "conflicts": conflicts,
                "observation_count": len(observations),
            }
        )
    return resolved


def available_layout_slots(objects):
    keys = {
        key
        for item in objects
        for key in set(item["agreed_fields"]) | set(item["conflicts"])
        if re.fullmatch(r"(?:l\d{1,2}x|lmx|e\d{1,2}x)", key)
    }
    return ["home_xy", *sorted(keys)]


def preview_layout(objects, catalog, target_inventory, slot, transform):
    """Project a named slot using explicit, unverified encoding assumptions.

    Coordinates from a different slot never fill a missing coordinate. Catalog
    modes, building sizes, ownership and active-slot meaning remain unverified.
    """
    mapping = defaultdict(list)
    for entry in catalog.records.values():
        entity = entry["entity"]
        if "dataId" in entity and "size" in entity:
            mapping[entity["dataId"]].append(entity["id"])
    records = []
    rejected = []
    coordinate_keys = ["x", "y"] if slot == "home_xy" else [slot]
    required = ["data", "lvl", *coordinate_keys]
    for item in objects:
        fields = item["agreed_fields"]
        missing = [key for key in required if key not in fields]
        if missing:
            rejected.append(
                {
                    "object_id": item["object_id"],
                    "missing_or_conflicting_fields": missing,
                }
            )
            continue
        entity_ids = mapping.get(fields["data"], [])
        if len(entity_ids) != 1:
            rejected.append(
                {
                    "object_id": item["object_id"],
                    "reason": "NO_UNIQUE_CATALOG_MAPPING",
                }
            )
            continue
        position = [fields["x"], fields["y"]] if slot == "home_xy" else fields[slot]
        if any(coordinate < 0 for coordinate in position):
            rejected.append(
                {"object_id": item["object_id"], "reason": "UNPLACED_SENTINEL"}
            )
            continue
        entity_id = entity_ids[0]
        entity = catalog.entity(entity_id)
        width, height = (int(part) for part in entity["size"].split("x"))
        records.append(
            {
                "instance": f"memory-{item['object_id']}",
                "object_id": item["object_id"],
                "id": entity_id,
                "name": entity["name"],
                "category": entity["category"],
                "raw_level": fields["lvl"],
                "level_hypothesis": fields["lvl"] + transform["level_offset"],
                "raw_position": position,
                "x": position[0] - transform["coordinate_offset"],
                "y": position[1] - transform["coordinate_offset"],
                "width": width,
                "height": height,
                "observed_mode_fields": {
                    key: value
                    for key, value in fields.items()
                    if "mode" in key or key in {"rot", "dir", "direction", "rotation"}
                },
                "unresolved_fields": item["conflicts"],
            }
        )
    counts = Counter(record["id"] for record in records)
    missing_inventory = {
        key: entry["count"] - counts[key]
        for key, entry in target_inventory.items()
        if counts[key] < entry["count"]
    }
    excess_inventory = {
        key: count - target_inventory.get(key, {}).get("count", 0)
        for key, count in counts.items()
        if count > target_inventory.get(key, {}).get("count", 0)
    }
    occupied = defaultdict(list)
    out_of_bounds = []
    for record in records:
        if (
            record["x"] < 0
            or record["y"] < 0
            or record["x"] + record["width"] > transform["board_size"]
            or record["y"] + record["height"] > transform["board_size"]
        ):
            out_of_bounds.append(record["instance"])
        for x in range(record["x"], record["x"] + record["width"]):
            for y in range(record["y"], record["y"] + record["height"]):
                occupied[x, y].append(record["instance"])
    overlaps = sorted(
        {
            tuple(sorted(instances))
            for instances in occupied.values()
            if len(instances) > 1
        }
    )
    return {
        "status": "PREVIEW_ONLY_UNVERIFIED_ENCODINGS",
        "slot": slot,
        "transform_assumptions": deepcopy(transform),
        "active_slot_verified": False,
        "ownership_and_freshness_verified": False,
        "records": records,
        "counts": dict(sorted(counts.items())),
        "missing_inventory": missing_inventory,
        "excess_inventory": excess_inventory,
        "rejected_records": rejected,
        "catalog_footprint_overlaps": overlaps,
        "out_of_bounds": out_of_bounds,
    }
