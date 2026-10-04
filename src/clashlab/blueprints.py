"""Complete inventory-preserving tile candidates with explicit design hypotheses.

These plans provide geometry and design probes, not an in-game base-copy link or
battle prediction. Unknown rules and destruction flags remain visible.
"""

from collections import Counter
from copy import deepcopy
from itertools import combinations
from math import hypot

from .common import InputError, identifier, integer, number, require, stable_id
from .geometry import footprint, gap, rectangle, validate_layout


STATUS = "COMPLETE_DECLARED_INVENTORY_GEOMETRY_NOT_GAME_VALIDATED_BASE"


def _tiles(x, y, width, height):
    return {
        (column, row) for column in range(x, x + width) for row in range(y, y + height)
    }


def _center(building, catalog):
    x, y, right, bottom = rectangle(building, catalog)
    return (x + right) / 2, (y + bottom) / 2


def _wall_tiles(configuration, width, height):
    tiles = set()
    for segment in require(configuration, "wall_segments"):
        if set(segment) != {"x1", "y1", "x2", "y2"}:
            raise InputError("Every declared wall segment needs its four endpoints")
        x1, y1, x2, y2 = (
            integer(segment[field], "wall coordinate", 0)
            for field in ("x1", "y1", "x2", "y2")
        )
        if x1 != x2 and y1 != y2:
            raise InputError("Blueprint wall segments must be orthogonal")
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                if x >= width or y >= height:
                    raise InputError("Wall segment is outside the declared board")
                tiles.add((x, y))
    return tiles


def _placement_score(x, y, size, rule, placed, catalog):
    center = (x + size[0] / 2, y + size[1] / 2)
    anchors = require(rule, "preferred_points")
    if not anchors:
        raise InputError("Placement needs explicit preferred points")
    anchor_distance = min(
        hypot(center[0] - point[0], center[1] - point[1]) for point in anchors
    )
    separation = number(
        require(rule, "separation_weight"), "design separation weight", 0
    )
    nearest = min(
        (
            hypot(center[0] - px, center[1] - py)
            for px, py in (
                _center(item, catalog) for item in placed if item["id"] != "wall"
            )
        ),
        default=0,
    )
    return anchor_distance - separation * nearest, y, x


def _place_free(building, occupied, placed, catalog, width, height, rule):
    size = footprint(building, catalog)
    candidates = []
    zones = require(rule, "zones")
    minimum_gap = number(
        require(rule, "minimum_footprint_gap_tiles"), "design minimum gap", 0
    )
    for zone in zones:
        if len(zone) != 4:
            raise InputError("Design zones need x, y, right, bottom")
        left, top, right, bottom = (
            integer(value, "design zone boundary", 0) for value in zone
        )
        if left >= right or top >= bottom or right > width or bottom > height:
            raise InputError("Design zone is outside the declared board")
        for y in range(top, bottom - size[1] + 1):
            for x in range(left, right - size[0] + 1):
                tiles = _tiles(x, y, *size)
                if tiles & occupied:
                    continue
                candidate = {**building, "x": x, "y": y}
                if minimum_gap and any(
                    item["id"] != "wall" and gap(candidate, item, catalog) < minimum_gap
                    for item in placed
                ):
                    continue
                candidates.append(
                    (_placement_score(x, y, size, rule, placed, catalog), x, y)
                )
    if not candidates:
        raise InputError(
            f"No position satisfies the declared design constraints: {building['instance']}"
        )
    _, x, y = min(candidates)
    building.update(x=x, y=y)
    occupied.update(_tiles(x, y, *size))
    placed.append(building)


def _settings(building, catalog, configuration):
    entity = catalog.entity(building["id"])
    if entity.get("modes"):
        selected = require(configuration["modes"], building["instance"])
        if selected not in entity["modes"]:
            raise InputError("Blueprint selects an unknown defense mode")
        building["mode"] = selected
    settings = require(configuration, "instance_settings")
    if building["id"] == "clan-castle" and building["instance"] in settings:
        selected = settings[building["instance"]]
        if not isinstance(selected, dict) or set(selected) != {"garrison"}:
            raise InputError(
                "Clan Castle settings must explicitly declare a garrison roster"
            )
        if not isinstance(selected["garrison"], list):
            raise InputError("Clan Castle garrison roster must be a list")
        building["settings"] = deepcopy(selected)
    if building["id"] in {"hero-banner", "air-sweeper", "skeleton-trap"}:
        building["settings"] = deepcopy(require(settings, building["instance"]))
        if building["id"] == "air-sweeper":
            direction = integer(
                require(building["settings"], "facing_degrees"),
                "design direction",
                0,
                359,
            )
            if direction % 45:
                raise InputError(
                    "Declared sweeper orientation needs a 45-degree direction"
                )
        elif building["id"] == "skeleton-trap":
            if require(building["settings"], "target_layer") not in {"ground", "air"}:
                raise InputError("Skeleton trap needs an explicit air/ground mode")
        else:
            hero = require(building["settings"], "hero")
            level = integer(
                require(building["settings"], "level"), "defending hero level", 1
            )
            if catalog.entity(hero)["category"] != "hero" or not catalog.available(
                hero, level, configuration["town_hall"]
            ):
                raise InputError("Defending hero is unavailable at this Town Hall")


def generate_blueprint(target, catalog, configuration):
    identifier(require(configuration, "source"), "design configuration evidence")
    identifier(require(configuration, "id"), "blueprint design id")
    statistics = require(configuration, "statistics_policy")
    if require(statistics, "snapshot_commit") != catalog.snapshot["snapshotCommit"]:
        raise InputError("Blueprint statistics must match the exact catalog snapshot")
    branch = catalog.snapshot.get("statistic_branch")
    if statistics["kind"] == "conditional_pinned_snapshot":
        if branch is not None:
            raise InputError("A source branch cannot be labeled an unchanged snapshot")
    elif statistics["kind"] == "conditional_primary_publications":
        if branch is None or require(statistics, "branch_policy") != branch["policy"]:
            raise InputError("Blueprint requires its exact selected source branch")
    else:
        raise InputError("Blueprint current-client statistics are not implemented")
    town_hall = integer(
        require(configuration, "town_hall"),
        "design Town Hall",
        1,
        catalog.maximum_town_hall,
    )
    if (
        require(configuration, "gearing_policy")
        != "explicit_no_geared_defenses_in_this_candidate"
    ):
        raise InputError(
            "Blueprint gearing needs an additional explicit inventory policy"
        )
    if (
        require(configuration, "supercharge_policy")
        != "explicit_no_supercharges_in_this_candidate"
    ):
        raise InputError(
            "Blueprint supercharge needs an additional applicability policy"
        )
    if any(
        mode.startswith("gearedUp") for mode in require(configuration, "modes").values()
    ):
        raise InputError(
            "Selected geared modes conflict with the explicit no-gearing policy"
        )
    if (
        require(configuration, "direction_convention")
        != "draft_grid_north_zero_degrees_clockwise_not_verified_UI_orientation"
    ):
        raise InputError("Blueprint direction mapping must be explicitly supported")
    if town_hall != require(target, "town_hall"):
        raise InputError("Blueprint target and configuration Town Halls differ")
    board = require(configuration, "board")
    identifier(require(board, "source"), "board dimension evidence")
    if require(board, "verification") not in {
        "declared_hypothesis",
        "verified_game_observation",
    }:
        raise InputError("Board dimensions need an explicit evidence status")
    width = integer(require(board, "width"), "design board width", 1)
    height = integer(require(board, "height"), "design board height", 1)
    occupied = _wall_tiles(configuration, width, height)
    wall_count = require(target["inventory"], "wall")["count"]
    if len(occupied) > wall_count:
        raise InputError("Declared wall segments exceed the target wall inventory")
    placements = require(configuration, "fixed_placements")
    rules = require(configuration, "placement_rules")
    instances = []
    for entity_id, item in target["inventory"].items():
        if item["size"] != catalog.entity(entity_id).get("size"):
            raise InputError("Target inventory footprint conflicts with the catalog")
        if entity_id == "wall":
            continue
        for index in range(integer(item["count"], "target inventory count", 0)):
            building = {
                "instance": f"{entity_id}-{index}",
                "id": entity_id,
                "level": item["maximum_level_under_snapshot"],
                "counts_for_destruction": (
                    True if entity_id == "town-hall" else item["destruction_flag"]
                ),
            }
            _settings(building, catalog, configuration)
            instances.append(building)
    known_instances = {building["instance"] for building in instances}
    if not set(placements) <= known_instances:
        raise InputError("Pinned placement names an absent target instance")
    for instance in configuration["instance_settings"]:
        if instance not in known_instances:
            raise InputError("Configuration names an absent target instance")
    placed = []
    for building in instances:
        if building["instance"] not in placements:
            continue
        x, y = (
            integer(value, "pinned coordinate", 0)
            for value in placements[building["instance"]]
        )
        size = footprint(building, catalog)
        tiles = _tiles(x, y, *size)
        if x + size[0] > width or y + size[1] > height or tiles & occupied:
            raise InputError(
                f"Pinned position overlaps or leaves board: {building['instance']}"
            )
        building.update(x=x, y=y)
        occupied.update(tiles)
        placed.append(building)
    order = require(configuration, "placement_category_order")
    remaining = [item for item in instances if "x" not in item]
    categories = {catalog.entity(item["id"])["category"] for item in remaining}
    if len(order) != len(set(order)) or not categories <= set(order):
        raise InputError(
            "Placement order must cover every remaining category explicitly"
        )
    remaining.sort(
        key=lambda item: (
            order.index(catalog.entity(item["id"])["category"]),
            -footprint(item, catalog)[0] * footprint(item, catalog)[1],
            item["instance"],
        )
    )
    for building in remaining:
        category = catalog.entity(building["id"])["category"]
        _place_free(
            building, occupied, placed, catalog, width, height, require(rules, category)
        )
    wall_tiles = _wall_tiles(configuration, width, height)
    additional = require(configuration, "additional_wall_policy")
    if require(additional, "kind") != "extend_connected_walls_toward_declared_points":
        raise InputError(
            "Additional wall allocation needs an explicit supported policy"
        )
    points = require(additional, "preferred_points")
    if not points:
        raise InputError("Additional walls need explicit preferred points")
    while len(wall_tiles) < wall_count:
        choices = set()
        for x, y in wall_tiles:
            for tile in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if (
                    0 <= tile[0] < width
                    and 0 <= tile[1] < height
                    and tile not in occupied
                ):
                    choices.add(tile)
        if not choices:
            raise InputError(
                "No connected free position remains for the full wall inventory"
            )
        tile = min(
            choices,
            key=lambda cell: (
                min(
                    hypot(cell[0] + 0.5 - point[0], cell[1] + 0.5 - point[1])
                    for point in points
                ),
                cell[1],
                cell[0],
            ),
        )
        wall_tiles.add(tile)
        occupied.add(tile)
    for index, (x, y) in enumerate(
        sorted(wall_tiles, key=lambda cell: (cell[1], cell[0]))
    ):
        placed.append(
            {
                "instance": f"wall-{index}",
                "id": "wall",
                "level": target["inventory"]["wall"]["maximum_level_under_snapshot"],
                "x": x,
                "y": y,
                "counts_for_destruction": False,
            }
        )
    blueprint = {
        "id": configuration["id"],
        "width": width,
        "height": height,
        "town_hall": town_hall,
        "inventory": {key: item["count"] for key, item in target["inventory"].items()},
        "buildings": placed,
        "data_status": STATUS,
        "board_evidence": deepcopy(board),
        "design_configuration": deepcopy(configuration),
        "full_game_prediction": False,
    }
    validate_layout(blueprint, catalog, require_destruction_flags=False)
    heroes = [
        item["settings"]["hero"] for item in placed if item["id"] == "hero-banner"
    ]
    if len(heroes) != len(set(heroes)):
        raise InputError("Defending banners cannot repeat the same hero")
    return blueprint


def inspect_blueprint(blueprint, catalog, probes):
    validation = validate_layout(blueprint, catalog, require_destruction_flags=False)
    key_ids = require(probes, "key_entities")
    identifier(require(probes, "source"), "geometry probe evidence")
    radius = number(
        require(probes, "footprint_disc_radius_tiles"), "declared geometry radius", 0
    )
    anchors = [item for item in blueprint["buildings"] if item["id"] in key_ids]
    blast_cases = []
    for primary in anchors:
        px, py = _center(primary, catalog)
        covered = []
        for target in anchors:
            x, y, right, bottom = rectangle(target, catalog)
            distance = hypot(max(x - px, px - right, 0), max(y - py, py - bottom, 0))
            if distance <= radius:
                covered.append(target["instance"])
        blast_cases.append(
            {"centered_on": primary["instance"], "covered_anchors": covered}
        )
    town_hall = next(
        item for item in blueprint["buildings"] if item["id"] == "town-hall"
    )
    x, y, right, bottom = rectangle(town_hall, catalog)
    return {
        "status": "GEOMETRY_PROBES_NOT_DAMAGE_STARS_OR_DEFENSE_RANKING",
        "blueprint_id": stable_id(blueprint),
        "validation": validation,
        "inventory_counts": dict(
            Counter(item["id"] for item in blueprint["buildings"])
        ),
        "town_hall_boundary_distance_tiles": min(
            x, y, blueprint["width"] - right, blueprint["height"] - bottom
        ),
        "disc_coverage_cases": blast_cases,
        "maximum_key_anchors_under_declared_disc": max(
            (len(case["covered_anchors"]) for case in blast_cases), default=0
        ),
        "probes": deepcopy(probes),
        "unverified_destruction_instances": [
            item["instance"]
            for item in blueprint["buildings"]
            if item["counts_for_destruction"] is None
        ],
        "battle_ready": False,
        "wall_driven_combat_scoring": False,
        "wall_topology_optimized": False,
        "remaining": [
            "Confirm board boundaries and inventory in game; unknown destruction flags remain null",
            "Verify modes, gearing, supercharges, trap and hero behavior under the actual patch",
            "Implement and calibrate full army/village combat rather than treating geometry as defense performance",
            "Test ordinary and competent attacks plus scouted/adapted war/CWL follow-ups",
        ],
    }


def apply_blueprint_swap(blueprint, catalog, operation):
    identifier(require(operation, "source"), "swap proposal evidence")
    if require(operation, "base_id") != stable_id(blueprint):
        raise InputError("Swap proposal does not match the exact base blueprint")
    first_id = identifier(require(operation, "first"), "first swap instance")
    second_id = identifier(require(operation, "second"), "second swap instance")
    by_id = {item["instance"]: item for item in blueprint["buildings"]}
    if first_id == second_id or not {first_id, second_id} <= set(by_id):
        raise InputError("Swap requires two different existing instances")
    first, second = by_id[first_id], by_id[second_id]
    if "wall" in {first["id"], second["id"]} or footprint(first, catalog) != footprint(
        second, catalog
    ):
        raise InputError("This candidate operation requires equal non-wall footprints")
    candidate = deepcopy(blueprint)
    candidate_by_id = {item["instance"]: item for item in candidate["buildings"]}
    candidate_by_id[first_id].update(x=second["x"], y=second["y"])
    candidate_by_id[second_id].update(x=first["x"], y=first["y"])
    candidate["design_transformation"] = {
        "kind": "equal_footprint_position_swap",
        "operation": deepcopy(operation),
        "initial_design_configuration_is_provenance_not_final_coordinates": True,
    }
    validate_layout(candidate, catalog, require_destruction_flags=False)
    return candidate


def apply_blueprint_wall_edit(blueprint, catalog, operation):
    """Relocate declared walls without repacking buildings or changing inventory."""
    identifier(require(operation, "source"), "wall edit evidence")
    if require(operation, "base_id") != stable_id(blueprint):
        raise InputError("Wall edit does not match the exact base blueprint")
    moves = require(operation, "moves")
    if not isinstance(moves, list) or not moves:
        raise InputError("Wall edit needs an explicit nonempty move list")
    candidate = deepcopy(blueprint)
    by_id = {item["instance"]: item for item in candidate["buildings"]}
    moved = set()
    for move in moves:
        if set(move) != {"instance", "x", "y"}:
            raise InputError("Wall move needs exactly instance, x and y")
        instance = identifier(move["instance"], "wall move instance")
        if (
            instance in moved
            or instance not in by_id
            or by_id[instance]["id"] != "wall"
        ):
            raise InputError("Wall edit needs unique existing wall instances")
        moved.add(instance)
        by_id[instance].update(
            x=integer(move["x"], "wall destination x", 0),
            y=integer(move["y"], "wall destination y", 0),
        )
    candidate["design_transformation"] = {
        "kind": "explicit_inventory_preserving_wall_relocation",
        "operation": deepcopy(operation),
        "initial_design_configuration_is_provenance_not_final_coordinates": True,
    }
    validate_layout(candidate, catalog, require_destruction_flags=False)
    return candidate


def screen_blueprint_swaps(blueprint, catalog, settings):
    source = identifier(require(settings, "source"), "swap screen evidence")
    movable = require(settings, "movable_instance_ids")
    instances = {item["instance"]: item for item in blueprint["buildings"]}
    if (
        not isinstance(movable, list)
        or len(movable) != len(set(movable))
        or not set(movable) <= set(instances)
    ):
        raise InputError("Swap screen needs unique existing movable instances")
    limit = integer(require(settings, "maximum_candidates"), "swap candidate limit", 1)
    probes = require(settings, "probes")
    candidates = []
    for first_id, second_id in combinations(sorted(movable), 2):
        first, second = instances[first_id], instances[second_id]
        if "wall" in {first["id"], second["id"]} or footprint(
            first, catalog
        ) != footprint(second, catalog):
            continue
        operation = {
            "source": source,
            "base_id": stable_id(blueprint),
            "first": first_id,
            "second": second_id,
        }
        candidate = apply_blueprint_swap(blueprint, catalog, operation)
        analysis = inspect_blueprint(candidate, catalog, probes)
        candidates.append(
            {
                "candidate_id": stable_id(candidate),
                "operation": operation,
                "town_hall_boundary_distance_tiles": analysis[
                    "town_hall_boundary_distance_tiles"
                ],
                "maximum_key_anchors_under_declared_disc": analysis[
                    "maximum_key_anchors_under_declared_disc"
                ],
                "town_hall_disc_anchors": next(
                    case["covered_anchors"]
                    for case in analysis["disc_coverage_cases"]
                    if instances[case["centered_on"]]["id"] == "town-hall"
                ),
            }
        )
        if len(candidates) >= limit:
            break
    return {
        "status": "GEOMETRY_ONLY_CANDIDATE_SEARCH_NO_DEFENSE_RANKING",
        "base_id": stable_id(blueprint),
        "reference": inspect_blueprint(blueprint, catalog, probes),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "maximum_candidates": limit,
        "enumeration": "sorted_instance_pairs",
        "performance_winner_selected": False,
        "wall_geometry_varied": False,
        "limitations": [
            "Reduced disc concentration may also remove useful Town Hall support",
            "No unseen-base defense score follows from geometry alone",
            "Full battle mechanics and matched human plans are required to select a defense winner",
        ],
    }
