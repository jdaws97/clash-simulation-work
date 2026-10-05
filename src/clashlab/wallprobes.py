"""Static wall access diagnostics; these do not predict Clash target selection.

Explicit entries and ranges make paired geometry comparisons reproducible.
Routes have no combat clock, casualties, retargeting, spells, or wall damage.
"""

from collections import deque
from heapq import heappop, heappush
from math import hypot

from .common import InputError, identifier, integer, number, require, stable_id
from .geometry import footprint, validate_layout
from .spatial import ground_attack_point, target_distance


def _neighbors(cell, width, height):
    x, y = cell
    for neighbor in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y)):
        if 0 <= neighbor[0] < width and 0 <= neighbor[1] < height:
            yield neighbor


def _maps(layout, catalog):
    walls = {}
    solids = set()
    for building in layout["buildings"]:
        width, height = footprint(building, catalog)
        cells = {
            (x, y)
            for x in range(building["x"], building["x"] + width)
            for y in range(building["y"], building["y"] + height)
        }
        if building["id"] == "wall":
            for cell in cells:
                walls[cell] = building["instance"]
        elif catalog.entity(building["id"])["category"] != "trap":
            solids.update(cells)
    return walls, solids


def _wall_regions(walls, width, height):
    unseen = {
        (x, y) for x in range(width) for y in range(height) if (x, y) not in walls
    }
    enclosed_sizes = []
    while unseen:
        first = min(unseen)
        unseen.remove(first)
        pending = deque([first])
        size = 0
        touches_boundary = False
        while pending:
            cell = pending.popleft()
            size += 1
            x, y = cell
            touches_boundary |= x in {0, width - 1} or y in {0, height - 1}
            for neighbor in _neighbors(cell, width, height):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    pending.append(neighbor)
        if not touches_boundary:
            enclosed_sizes.append(size)
    return sorted(enclosed_sizes)


def _route(start, target, profile, walls, solids, width, height):
    movement = profile["movement"]
    attack_range = profile["range_tiles"]
    if movement == "air_direct":
        position = start[0] + 0.5, start[1] + 0.5
        distance = target_distance(position, target)
        nearest = (
            min(max(position[0], target["x"]), target["x"] + target["width"]),
            min(max(position[1], target["y"]), target["y"] + target["height"]),
        )
        fraction = max(0, distance - attack_range) / distance if distance else 0
        endpoint = [
            position[index] + fraction * (nearest[index] - position[index])
            for index in range(2)
        ]
        return {
            "reachable": True,
            "route_points": [list(position), endpoint],
            "distance_tiles": max(0, distance - attack_range),
            "wall_instances_crossed": [],
            "grid_steps": None,
        }
    pending = [(0, 0, start)]
    costs = {start: (0, 0)}
    previous = {start: None}
    endpoint = None
    destination = None
    while pending:
        crossings, steps, cell = heappop(pending)
        if costs[cell] != (crossings, steps):
            continue
        endpoint = ground_attack_point(cell, target, attack_range)
        if endpoint is not None:
            destination = cell
            break
        for neighbor in _neighbors(cell, width, height):
            if neighbor in solids:
                continue
            if movement == "ground_avoid" and neighbor in walls:
                continue
            wall_cost = int(movement == "ground_minimum_breaches" and neighbor in walls)
            candidate = crossings + wall_cost, steps + 1
            if candidate < costs.get(neighbor, (float("inf"), float("inf"))):
                costs[neighbor] = candidate
                previous[neighbor] = cell
                heappush(pending, (*candidate, neighbor))
    if destination is None:
        return {
            "reachable": False,
            "route_points": [],
            "distance_tiles": None,
            "wall_instances_crossed": [],
            "grid_steps": None,
        }
    cells = [destination]
    while cells[-1] != start:
        cells.append(previous[cells[-1]])
    cells.reverse()
    points = [[x + 0.5, y + 0.5] for x, y in cells]
    if list(endpoint) != points[-1]:
        points.append(list(endpoint))
    distance = sum(
        hypot(second[0] - first[0], second[1] - first[1])
        for first, second in zip(points, points[1:])
    )
    return {
        "reachable": True,
        "route_points": points,
        "distance_tiles": distance,
        "wall_instances_crossed": [walls[cell] for cell in cells if cell in walls],
        "grid_steps": costs[destination][1],
    }


def inspect_wall_access(layout, catalog, specification):
    validate_layout(layout, catalog, require_destruction_flags=False)
    if set(specification) - {
        "source",
        "obstacle_policy",
        "route_policy",
        "entries",
        "profiles",
        "targets",
    }:
        raise InputError(
            "Static wall probes cannot silently accept extra combat inputs"
        )
    identifier(require(specification, "source"), "wall probe evidence")
    if (
        require(specification, "obstacle_policy")
        != "all_non_trap_footprints_hypothesis"
    ):
        raise InputError(
            "Static wall probes require an explicit supported obstacle policy"
        )
    if (
        require(specification, "route_policy")
        != "four_neighbor_minimum_walls_then_steps_hypothesis"
    ):
        raise InputError("Static route choice must be declared, not inferred Clash AI")
    walls, solids = _maps(layout, catalog)
    width, height = layout["width"], layout["height"]
    entries = require(specification, "entries")
    profiles = require(specification, "profiles")
    targets = require(specification, "targets")
    if any(
        not isinstance(items, list) or not items
        for items in (entries, profiles, targets)
    ):
        raise InputError("Wall probes need entries, profiles and target instances")
    entry_ids = set()
    for entry in entries:
        key = identifier(require(entry, "id"), "entry id")
        if key in entry_ids:
            raise InputError("Wall probe entry ids must be unique")
        entry_ids.add(key)
        position = require(entry, "cell")
        if not isinstance(position, list) or len(position) != 2:
            raise InputError("Entry cell needs two integer coordinates")
        x = integer(position[0], "entry x", 0, width - 1)
        y = integer(position[1], "entry y", 0, height - 1)
        if (x, y) in walls or (x, y) in solids:
            raise InputError("Wall probe entry occupies an obstacle")
    profile_ids = set()
    for profile in profiles:
        if set(profile) != {"id", "source", "movement", "range_tiles"}:
            raise InputError(
                "Static route profiles cannot hide combat or targeting weights"
            )
        key = identifier(require(profile, "id"), "route profile id")
        if key in profile_ids:
            raise InputError("Route profile ids must be unique")
        profile_ids.add(key)
        identifier(require(profile, "source"), "route profile evidence")
        number(require(profile, "range_tiles"), "route probe range", 0.000001)
        if require(profile, "movement") not in {
            "ground_avoid",
            "ground_minimum_breaches",
            "ground_ignore_walls",
            "air_direct",
        }:
            raise InputError("Unknown explicit wall probe movement")
    by_id = {item["instance"]: item for item in layout["buildings"]}
    for target_id in targets:
        identifier(target_id, "route target instance")
    if len(targets) != len(set(targets)) or not set(targets) <= set(by_id):
        raise InputError("Wall probes need unique existing target instances")
    results = []
    for target_id in targets:
        building = by_id[target_id]
        if catalog.entity(building["id"])["category"] in {"wall", "trap"}:
            raise InputError("Route probe targets must be non-wall structures")
        bw, bh = footprint(building, catalog)
        target = {**building, "width": bw, "height": bh}
        for entry in entries:
            for profile in profiles:
                results.append(
                    {
                        "target": target_id,
                        "entry": entry["id"],
                        "profile": profile["id"],
                        **_route(
                            tuple(entry["cell"]),
                            target,
                            profile,
                            walls,
                            solids,
                            width,
                            height,
                        ),
                    }
                )
    return {
        "status": "STATIC_WALL_ACCESS_NOT_ATTACK_PATH_OR_DEFENSE_PERFORMANCE",
        "blueprint_id": stable_id(layout),
        "specification": specification,
        "wall_only_enclosed_region_sizes_tiles": _wall_regions(walls, width, height),
        "routes": results,
        "full_game_prediction": False,
        "limitations": [
            "One selected target in an unchanged village; no target choice, funnel sequence or retargeting",
            "Minimum wall count is a geometry bound, not time to breach or a prediction of troop AI",
            "No range line-of-sight rule, wall breaker aim, Jump, Earthquake, Root Rider weapon, casualty or defensive fire calculation",
            "Wall-only regions ignore structures; actual troop compartments and deployment legality require separate checks",
            "Air paths ignore walls, but buildings, chains, splash, sweepers and traps still matter to combat",
        ],
    }
