"""Layout legality, geometric screening, and inventory-preserving mutations."""

from collections import Counter
from copy import deepcopy
from itertools import combinations
from math import hypot
from random import Random

from .common import InputError, identifier, integer, number, require, stable_id


def footprint(building, catalog):
    size = catalog.entity(building["id"]).get("size")
    if size is None:
        raise InputError(f"Catalog footprint is missing: {building['id']}")
    try:
        width, height = (int(part) for part in size.split("x"))
    except (ValueError, AttributeError) as error:
        raise InputError(f"Invalid catalog footprint: {size}") from error
    return width, height


def rectangle(building, catalog):
    width, height = footprint(building, catalog)
    return building["x"], building["y"], building["x"] + width, building["y"] + height


def gap(first, second, catalog):
    ax, ay, ar, ab = rectangle(first, catalog)
    bx, by, br, bb = rectangle(second, catalog)
    dx = max(ax - br, bx - ar, 0)
    dy = max(ay - bb, by - ab, 0)
    return hypot(dx, dy)


def validate_layout(layout, catalog, require_destruction_flags=True):
    width = integer(require(layout, "width"), "board width", 1)
    height = integer(require(layout, "height"), "board height", 1)
    town_hall = integer(
        require(layout, "town_hall"), "Town Hall", 1, catalog.maximum_town_hall
    )
    inventory = require(layout, "inventory")
    buildings = require(layout, "buildings")
    seen = set()
    occupied = {}
    counts = Counter()
    for building in buildings:
        instance = identifier(building["instance"], "building instance")
        if instance in seen:
            raise InputError(f"Duplicate building instance: {instance}")
        seen.add(instance)
        entity_id = building["id"]
        entity = catalog.entity(entity_id)
        if entity_id == "hero-banner" and building.get("level") is None:
            if "level" not in building:
                raise InputError("Hero Banner must explicitly declare no upgrade level")
        else:
            integer(require(building, "level"), "building level", 1)
        if entity_id == "town-hall" and building["level"] != town_hall:
            raise InputError("Town Hall building level must match the layout Town Hall")
        x = integer(building["x"], "x coordinate", 0)
        y = integer(building["y"], "y coordinate", 0)
        size_x, size_y = footprint(building, catalog)
        if x + size_x > width or y + size_y > height:
            raise InputError(f"Building outside board: {instance}")
        if entity_id != "hero-banner":
            if not catalog.available(entity_id, building["level"], town_hall):
                raise InputError(f"Unavailable building level: {instance}")
        destruction = building.get("counts_for_destruction")
        if "counts_for_destruction" not in building:
            raise InputError(
                "Destruction eligibility must be explicit, even if unknown"
            )
        if require_destruction_flags and not isinstance(destruction, bool):
            raise InputError("Destruction eligibility must be explicit")
        if (
            not require_destruction_flags
            and destruction is not None
            and not isinstance(destruction, bool)
        ):
            raise InputError(
                "Geometry-only destruction eligibility must be boolean or null"
            )
        modes = entity.get("modes")
        if modes:
            selected_mode = require(building, "mode")
            if selected_mode not in modes:
                raise InputError(f"Invalid defensive mode: {instance}")
            minimum_mode_level = modes[selected_mode].get("availableFromLevel", 1)
            if building["level"] < minimum_mode_level:
                raise InputError(f"Defensive mode is not unlocked: {instance}")
            unlocks = {
                row["unlocksSpell"].removesuffix(" Spell").lower(): row["level"]
                for row in entity["levels"]
                if row.get("unlocksSpell")
            }
            if selected_mode in unlocks and building["level"] < unlocks[selected_mode]:
                raise InputError(f"Defensive mode is not unlocked: {instance}")
        counts[entity_id] += 1
        for tile_x in range(x, x + size_x):
            for tile_y in range(y, y + size_y):
                tile = (tile_x, tile_y)
                if tile in occupied:
                    raise InputError(f"Overlap between {instance} and {occupied[tile]}")
                occupied[tile] = instance
    if counts.get("town-hall") != 1:
        raise InputError("A complete layout must contain exactly one Town Hall")
    if not next(item for item in buildings if item["id"] == "town-hall")[
        "counts_for_destruction"
    ]:
        raise InputError("The Town Hall must count for destruction")
    expected = {
        key: integer(value, "inventory count", 0) for key, value in inventory.items()
    }
    actual = {key: value for key, value in counts.items() if value}
    expected = {key: value for key, value in expected.items() if value}
    if actual != expected:
        raise InputError("Placed buildings do not match the explicit inventory")
    for entity_id, count in counts.items():
        limits = catalog.entity(entity_id).get("availablePerTownHall", [])
        matches = [row["count"] for row in limits if row["townHallLevel"] == town_hall]
        if matches and count > matches[0]:
            raise InputError(f"Town Hall inventory limit exceeded: {entity_id}")
    if town_hall == 16:
        merge_counts = {
            "archer-tower": 2 * counts["multi-archer-tower"],
            "cannon": 2 * counts["ricochet-cannon"],
        }
        for entity_id, consumed in merge_counts.items():
            limits = catalog.entity(entity_id)["availablePerTownHall"]
            original = next(
                row["count"] for row in limits if row["townHallLevel"] == 16
            )
            if counts[entity_id] + consumed > original:
                raise InputError(
                    f"Merged defenses double-count consumed {entity_id} instances"
                )
    return {
        "id": stable_id(layout),
        "building_count": len(buildings),
        "occupied_tiles": len(occupied),
        "destruction_eligibility_complete": all(
            isinstance(building["counts_for_destruction"], bool)
            for building in buildings
        ),
        "status": "GEOMETRY_AND_SNAPSHOT_CONSTRAINTS_ONLY",
        "limitations": "Higher-TH merge rules, gearing, seasonal defenses, and destruction flags require independent validation",
    }


def layout_features(layout, catalog, settings):
    validation = validate_layout(layout, catalog)
    threshold = number(require(settings, "neighbor_gap_tiles"), "neighbor gap", 0)
    radius = number(require(settings, "cluster_radius_tiles"), "cluster radius", 0)
    buildings = [item for item in layout["buildings"] if item["counts_for_destruction"]]
    adjacency = {item["instance"]: set() for item in buildings}
    pairs = []
    for first, second in combinations(buildings, 2):
        distance = gap(first, second, catalog)
        if distance <= threshold:
            adjacency[first["instance"]].add(second["instance"])
            adjacency[second["instance"]].add(first["instance"])
            pairs.append(
                {
                    "first": first["instance"],
                    "second": second["instance"],
                    "gap": distance,
                }
            )
    unseen = set(adjacency)
    components = []
    while unseen:
        pending = [min(unseen)]
        component = set()
        while pending:
            current = pending.pop()
            if current in component:
                continue
            component.add(current)
            pending.extend(adjacency[current] - component)
        unseen -= component
        components.append(sorted(component))
    centers = {}
    for building in buildings:
        x, y, right, bottom = rectangle(building, catalog)
        centers[building["instance"]] = ((x + right) / 2, (y + bottom) / 2)
    clusters = []
    for anchor, (x, y) in centers.items():
        members = [
            key for key, (bx, by) in centers.items() if hypot(x - bx, y - by) <= radius
        ]
        clusters.append({"anchor": anchor, "members": members})
    town_hall = next(item for item in buildings if item["id"] == "town-hall")
    x, y, right, bottom = rectangle(town_hall, catalog)
    boundary_distance = min(x, y, layout["width"] - right, layout["height"] - bottom)
    return {
        "layout_id": validation["id"],
        "status": "GEOMETRY_ONLY_NOT_DAMAGE_OR_STAR_PREDICTIONS",
        "neighbor_pairs": pairs,
        "connected_groups": components,
        "largest_connected_group": max((len(group) for group in components), default=0),
        "center_radius_clusters": clusters,
        "largest_center_radius_cluster": max(
            (len(item["members"]) for item in clusters), default=0
        ),
        "town_hall_boundary_distance_tiles": boundary_distance,
        "settings": settings,
    }


def mutate_layout(layout, catalog, specification):
    validate_layout(layout, catalog)
    random = Random(integer(require(specification, "seed"), "seed", 0))
    attempts = integer(require(specification, "attempts"), "attempts", 1)
    limit = integer(require(specification, "maximum_candidates"), "candidate limit", 1)
    allowed = require(specification, "movable_instances")
    instances = {
        item["instance"]: index for index, item in enumerate(layout["buildings"])
    }
    if not allowed or not set(allowed) <= set(instances):
        raise InputError(
            "Movable instances must be explicitly selected from the layout"
        )
    operations = require(specification, "operations")
    if not operations or not set(operations) <= {"swap", "move"}:
        raise InputError("Supported mutation operations are swap and move")
    candidates = []
    seen = {stable_id(layout)}
    for attempt in range(attempts):
        candidate = deepcopy(layout)
        operation = random.choice(operations)
        first = candidate["buildings"][instances[random.choice(allowed)]]
        if operation == "swap":
            if len(allowed) < 2:
                continue
            choices = [key for key in allowed if key != first["instance"]]
            second = candidate["buildings"][instances[random.choice(choices)]]
            first["x"], second["x"] = second["x"], first["x"]
            first["y"], second["y"] = second["y"], first["y"]
        else:
            first["x"] = random.randrange(layout["width"])
            first["y"] = random.randrange(layout["height"])
        try:
            validation = validate_layout(candidate, catalog)
        except InputError:
            continue
        if validation["id"] in seen:
            continue
        seen.add(validation["id"])
        candidates.append(
            {"id": validation["id"], "layout": candidate, "operation": operation}
        )
        if len(candidates) >= limit:
            break
    return {
        "candidates": candidates,
        "attempts_requested": attempts,
        "status": "GEOMETRY_VALID_EXPERIMENT_CANDIDATES_NOT_VALIDATED_DEFENSES",
    }
