"""Restricted spatial combat kernel with explicitly selected model conventions.

This supplies movement, obstacle changes, targeting, cooldowns, and coupled HP
feedback. It does not supply Clash entity adapters or claim game fidelity.
"""

from collections import defaultdict, deque
from copy import deepcopy
from functools import lru_cache
from math import floor, hypot
from types import MappingProxyType

from .spell_visibility import untargetable_until
from .common import InputError, identifier, integer, number, require
from .range_events import first_weapon_range_entry_delay
from .rates import attack_rate, movement_speed, pause_attack_work


EPSILON = 1e-10
RULESET = "spatial-single-target-kernel-v1"
MODEL_RULES = {
    "ground_path": "four_neighbor_shortest_reachable_path",
    "target_retention": "until_dead_or_ineligible",
    "target_tie": "path_distance_then_instance_id",
    "range_metric": "source_center_to_target_footprint",
    "hit_model": "instant_single_target",
    "phase_order": "commands_then_simultaneous_hits_then_simultaneous_movement",
    "freeze_model": "pause_movement_and_remaining_attack_cooldown",
    "unit_collision": "none",
}
AIR_CONTACT_POLICY = (
    "declared_air_weapon_follows_departing_retained_target_at_target_speed"
)


def center(actor):
    return actor["x"] + actor["width"] / 2, actor["y"] + actor["height"] / 2


def target_distance(position, target):
    x, y = position
    dx = max(target["x"] - x, x - target["x"] - target["width"], 0)
    dy = max(target["y"] - y, y - target["y"] - target["height"], 0)
    return hypot(dx, dy)


def ground_attack_point(cell, target, attack_range):
    """Find an in-cell point that reaches a footprint with a short melee range."""
    return _ground_attack_point(
        tuple(cell),
        target["x"],
        target["y"],
        target["width"],
        target["height"],
        attack_range,
    )


def ground_attack_points(target, attack_range, width, height, *, terminal=True):
    """Bounded pure geometry index; live walls and search ordering remain local."""
    return _ground_attack_points(
        target["x"],
        target["y"],
        target["width"],
        target["height"],
        attack_range,
        width,
        height,
        terminal,
    )


@lru_cache(maxsize=256)
def _ground_attack_points(
    x, y, target_width, target_height, attack_range, width, height, terminal
):
    # Include an extra cell at each edge to preserve exact inclusive tolerance
    # and in-cell terminal geometry. Cells outside this box cannot reach.
    left = max(0, floor(x - attack_range - EPSILON) - 1)
    right = min(width - 1, floor(x + target_width + attack_range + EPSILON) + 1)
    bottom = max(0, floor(y - attack_range - EPSILON) - 1)
    top = min(height - 1, floor(y + target_height + attack_range + EPSILON) + 1)
    # Avoid materializing unusually large declared boards/ranges. The existing
    # cell-by-cell calculation remains an equivalent bounded-memory fallback.
    if (right - left + 1) * (top - bottom + 1) > 4096:
        return None
    target = {"x": x, "y": y, "width": target_width, "height": target_height}
    result = {}
    for cx in range(left, right + 1):
        for cy in range(bottom, top + 1):
            cell = cx, cy
            if terminal:
                point = _ground_attack_point(
                    cell, x, y, target_width, target_height, attack_range
                )
            else:
                point = cx + 0.5, cy + 0.5
                if target_distance(point, target) > attack_range + EPSILON:
                    point = None
            if point is not None:
                result[cell] = point
    return result


@lru_cache(maxsize=65536)
def _ground_attack_point(cell, x, y, width, height, attack_range):
    # Pure geometry only. Moving/resized targets and changed ranges use new
    # keys; live wall HP, path costs and obstruction eligibility are not cached.
    target = {"x": x, "y": y, "width": width, "height": height}
    point = cell[0] + 0.5, cell[1] + 0.5
    if target_distance(point, target) <= attack_range + EPSILON:
        return point
    nearest = (
        min(max(point[0], target["x"]), target["x"] + target["width"]),
        min(max(point[1], target["y"]), target["y"] + target["height"]),
    )
    distance = hypot(nearest[0] - point[0], nearest[1] - point[1])
    fraction = (distance - attack_range) / distance
    endpoint = (
        point[0] + (nearest[0] - point[0]) * fraction,
        point[1] + (nearest[1] - point[1]) * fraction,
    )
    if cell[0] <= endpoint[0] < cell[0] + 1 and cell[1] <= endpoint[1] < cell[1] + 1:
        return endpoint
    return None


def _blocked(actors, time):
    cells = set()
    for actor in actors.values():
        if not _active(actor, time) or not actor["blocking"]:
            continue
        for x in range(actor["x"], actor["x"] + actor["width"]):
            for y in range(actor["y"], actor["y"] + actor["height"]):
                cells.add((x, y))
    return cells


def _active(actor, time):
    return (
        actor["hp"] > 0
        and not actor.get("_recalled", False)
        and actor["spawn_seconds"] != "controlled"
        and actor["spawn_seconds"] <= time + EPSILON
    )


@lru_cache(maxsize=128)
def _ground_navigation(start, blocked, width, height):
    """The target-independent BFS order and parents for one exact free grid.

    Goal checks do not affect the queue or predecessor choice in _ground_route.
    Reusing its complete traversal therefore also handles moving and unreachable
    targets without caching eligibility, goal geometry, or an actor's position.
    The caller bounds board size; all obstruction cells are in the immutable key.
    """
    pending = deque([start])
    previous = {start: None}
    order = {}
    while pending:
        cell = pending.popleft()
        order[cell] = len(order)
        x, y = cell
        for neighbor in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y)):
            nx, ny = neighbor
            if (
                0 <= nx < width
                and 0 <= ny < height
                and neighbor not in blocked
                and neighbor not in previous
            ):
                previous[neighbor] = cell
                pending.append(neighbor)
    return MappingProxyType(order), MappingProxyType(previous)


def _ground_route(actor, target, blocked, width, height, *, exit_cells=None):
    position = center(actor)
    start = floor(position[0]), floor(position[1])
    if start in blocked:
        raise InputError(f"Ground unit occupies a blocking footprint: {actor['id']}")
    # Equivalent motion partitions can leave a unit a few ulps on either
    # side of an integer grid seam. Replanning from floor(9.999999999999998)
    # then sends it toward 9.5 instead of the exact-contact cell's 10.5.
    # Canonicalize only free interior cells within the existing tolerance;
    # do not change obstacle occupancy or move a start outside the board.
    canonical = tuple(
        floor(round(value) if abs(value - round(value)) <= EPSILON else value)
        for value in position
    )
    if (
        0 <= canonical[0] < width
        and 0 <= canonical[1] < height
        and canonical not in blocked
    ):
        start = canonical
    pending = deque([start])
    previous = {start: None}
    destination = None
    endpoint = None
    attack_points = (
        None
        if exit_cells is not None
        else ground_attack_points(
            target,
            actor["range"],
            width,
            height,
            terminal=bool(actor.get("_terminal_ground_approach")),
        )
    )
    if width * height <= 4096 and (exit_cells is not None or attack_points is not None):
        order, previous = _ground_navigation(start, frozenset(blocked), width, height)
        if exit_cells is not None:
            destination = next((cell for cell in order if cell not in exit_cells), None)
            if destination is not None:
                endpoint = destination[0] + 0.5, destination[1] + 0.5
        else:
            destination = min(
                (cell for cell in attack_points if cell in order),
                key=order.__getitem__,
                default=None,
            )
            if destination is not None:
                endpoint = attack_points[destination]
        pending.clear()
    while pending:
        cell = pending.popleft()
        point = cell[0] + 0.5, cell[1] + 0.5
        if exit_cells is not None:
            endpoint = point if cell not in exit_cells else None
        elif attack_points is not None:
            endpoint = attack_points.get(cell)
        elif actor.get("_terminal_ground_approach"):
            endpoint = ground_attack_point(cell, target, actor["range"])
        elif target_distance(point, target) <= actor["range"] + EPSILON:
            endpoint = point
        if endpoint is not None:
            destination = cell
            break
        x, y = cell
        for neighbor in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y)):
            nx, ny = neighbor
            if (
                0 <= nx < width
                and 0 <= ny < height
                and neighbor not in blocked
                and neighbor not in previous
            ):
                previous[neighbor] = cell
                pending.append(neighbor)
    if destination is None:
        return None
    cells = []
    while destination != start:
        cells.append(destination)
        destination = previous[destination]
    cells.reverse()
    waypoints = [(x + 0.5, y + 0.5) for x, y in cells]
    destination_center = (
        waypoints[-1] if waypoints else (start[0] + 0.5, start[1] + 0.5)
    )
    if endpoint != destination_center:
        waypoints.append(endpoint)
    start_center = start[0] + 0.5, start[1] + 0.5
    if hypot(position[0] - start_center[0], position[1] - start_center[1]) > EPSILON:
        waypoints.insert(0, start_center)
    return waypoints


def _route(actor, target, blocked, width, height):
    position = center(actor)
    if (
        actor["movement"] == "stationary"
        and target_distance(position, target) < actor.get("_minimum_range", 0) - EPSILON
    ):
        return None
    if target_distance(position, target) <= actor["range"] + EPSILON:
        return []
    if actor["movement"] == "stationary":
        return None
    if actor["movement"] == "ground":
        signature = (
            target["id"],
            actor["range"],
            target["x"],
            target["y"],
            target["width"],
            target["height"],
            frozenset(blocked),
        )
        if actor.get("_path_signature") == signature:
            return list(actor["_remaining_path"])
        previous_signature = actor.get("_path_signature")
        remaining_path = actor.get("_remaining_path", [])
        if (
            previous_signature is not None
            and previous_signature[:2] == signature[:2]
            and previous_signature[-1] == signature[-1]
            and remaining_path
        ):
            # A moving primary changes the destination while the pursuer is
            # partway along a grid edge. Finish that edge before replanning;
            # repeatedly returning to the current cell center prevents motion.
            waypoint = remaining_path[0]
            if hypot(position[0] - waypoint[0], position[1] - waypoint[1]) > EPSILON:
                continuation = {
                    **actor,
                    "x": waypoint[0] - actor["width"] / 2,
                    "y": waypoint[1] - actor["height"] / 2,
                }
                tail = (
                    []
                    if target_distance(waypoint, target) <= actor["range"] + EPSILON
                    else _ground_route(continuation, target, blocked, width, height)
                )
                if tail is not None:
                    return [waypoint, *tail]
        return _ground_route(actor, target, blocked, width, height)
    nearest_x = min(max(position[0], target["x"]), target["x"] + target["width"])
    nearest_y = min(max(position[1], target["y"]), target["y"] + target["height"])
    if (
        actor["damage"] > 0
        and actor["team"] != target["team"]
        and target["movement"] != "stationary"
    ):
        # Do not stop an airborne weapon at a moving enemy's old range edge.
        # The shared relative-motion contact solver clips this same pursuit ray
        # at actual range entry. Stale endpoints create false arrival cascades.
        return [(nearest_x, nearest_y)]
    distance = hypot(nearest_x - position[0], nearest_y - position[1])
    fraction = max(distance - actor["range"], 0) / distance
    return [
        (
            position[0] + (nearest_x - position[0]) * fraction,
            position[1] + (nearest_y - position[1]) * fraction,
        )
    ]


def _route_length(actor, route):
    distance = 0
    previous = center(actor)
    for point in route:
        distance += hypot(point[0] - previous[0], point[1] - previous[1])
        previous = point
    return distance


def _retained_primary_stays_in_range(source, actors, motions, time, horizon):
    """An ordinary retained weapon cannot change at an unrelated range entry.

    Bound distance by total possible travel, without predicting a changed route.
    Secondary selectors and weapons keep their existing contact behavior.
    """
    if source.get("attack_model", {}).get("kind") != "single" or any(
        key.endswith("_model") and key != "attack_model" for key in source
    ):
        return False
    target = actors.get(source.get("target"))
    if target is None or not _eligible(source, target, time):
        return False
    source_speed = motions.get(source["id"], ([], 0))[1]
    target_speed = motions.get(target["id"], ([], 0))[1]
    travel = (source_speed + target_speed) * horizon
    distance = target_distance(center(source), target)
    return (
        distance + travel <= source["range"] + EPSILON
        and distance - travel >= source.get("_minimum_range", 0) - EPSILON
    )


def _weapon_range_boundary(actors, motions, time, next_time, excluded_sources):
    """Resolve positive range entries without mutating routes or target locks."""
    active = [actor for actor in actors.values() if _active(actor, time)]
    # All trajectories and actor categories are fixed for this one query.
    # Reuse the coarse candidate list across weapons with the same categories;
    # retain active order and still apply every live eligibility predicate.
    candidate_pools = {}
    for source in active:
        if (
            (source["damage"] <= 0 and "crafted_defense_model" not in source)
            or source["id"] in excluded_sources
            or source.get("_tesla_hidden", False)
            or source.get("attack_model", {}).get("kind") == "none"
        ):
            continue
        if _retained_primary_stays_in_range(
            source, actors, motions, time, next_time - time
        ):
            continue
        source_route, source_speed = motions.get(source["id"], ([], 0))
        minimum_range = source.get("_minimum_range", 0)
        key = (
            source["team"],
            tuple(source["target_priorities"]),
            tuple(source["target_layers"]),
        )
        if key not in candidate_pools:
            candidate_pools[key] = [
                target
                for target in active
                if target["team"] != source["team"]
                and target["kind"] in source["target_priorities"]
                and (
                    target["layer"] in source["target_layers"]
                    or "spell_decoy_model" in target
                )
            ]
        for target in candidate_pools[key]:
            if not _eligible(source, target, time):
                continue
            target_route, target_speed = motions.get(target["id"], ([], 0))
            if source_speed <= EPSILON and target_speed <= EPSILON:
                continue
            horizon = next_time - time
            distance = target_distance(center(source), target)
            maximum_travel = (source_speed + target_speed) * horizon
            if (
                distance > source["range"] + maximum_travel + EPSILON
                or distance + maximum_travel < minimum_range - EPSILON
            ):
                continue
            crossing = first_weapon_range_entry_delay(
                source,
                target,
                source_route,
                target_route,
                source_speed,
                target_speed,
                horizon,
                minimum_range=minimum_range,
            )
            if crossing is not None:
                next_time = min(next_time, time + crossing)
    return next_time


def _eligible(actor, target, time):
    return (
        target["team"] != actor["team"]
        and (
            not actor.get("_totem_forced_target")
            or target["id"] == actor["_totem_forced_target"]
        )
        and (
            not actor.get("_recipe_priority_targets")
            or target["id"] in actor["_recipe_priority_targets"]
        )
        and target["kind"] in actor["target_priorities"]
        and (target["layer"] in actor["target_layers"] or "spell_decoy_model" in target)
        and _active(target, time)
        and untargetable_until(target) <= time + EPSILON
    )


def target_priority(actor, kind):
    return actor["_target_ranks"][kind]


def _select_target(actor, actors, time, blocked, width, height):
    if actor.get("_inferno_fuel_depleted", False):
        actor["target"] = None
        return None, None
    if actor["damage"] == 0 or not _active(actor, time):
        return None, None
    retained = actors.get(actor["target"])
    if retained is not None and _eligible(actor, retained, time):
        route = _route(actor, retained, blocked, width, height)
        if route is not None:
            _remember_route(actor, retained, route, blocked)
            return retained, route
    choices = []
    for target in actors.values():
        if not _eligible(actor, target, time):
            continue
        route = _route(actor, target, blocked, width, height)
        if route is not None:
            priority = target_priority(actor, target["kind"])
            distance = (
                _route_length(actor, route)
                if route
                else target_distance(center(actor), target)
            )
            secondary = 0
            if actor.get("_target_scoring") == "arrival_time_then_footprint_distance":
                speed = movement_speed(actor)
                distance = _route_length(actor, route) / speed if route else 0
                secondary = target_distance(center(actor), target)
            choices.append((priority, distance, secondary, target["id"], target, route))
    if not choices:
        actor["target"] = None
        return None, None
    _, _, _, _, target, route = min(choices, key=lambda item: item[:4])
    actor["target"] = target["id"]
    _remember_route(actor, target, route, blocked)
    return target, route


def _remember_route(actor, target, route, blocked):
    if actor["movement"] == "ground":
        actor["_path_signature"] = (
            target["id"],
            actor["range"],
            target["x"],
            target["y"],
            target["width"],
            target["height"],
            frozenset(blocked),
        )
        actor["_remaining_path"] = list(route)


def _air_contact_motions(actors, motions, time, width, height, excluded_sources=()):
    """Keep established airborne weapon contact with a departing retained target.

    This is a declared movement convention, not a range tolerance or event filter.
    Follow only the target's first straight segment, at its speed, when the source
    can keep up. Translation preserves the current relative footprint and lets
    the unchanged weapon clocks fire at inclusive contact. All crossing queries
    must use these resolved motions, including those for fields and traps.
    """
    resolved = set()
    resolving = set()

    def resolve(actor_id):
        if actor_id in resolved or actor_id in resolving:
            return
        resolving.add(actor_id)
        actor = actors[actor_id]
        target = actors.get(actor.get("target"))
        route, _ = motions[actor_id]
        if (
            not route
            and actor_id not in excluded_sources
            and actor["movement"] == "air"
            and actor["damage"] > 0
            and actor.get("attack_model", {}).get("kind", "single") != "none"
            and target is not None
            and _eligible(actor, target, time)
            and target["movement"] != "stationary"
            and target["id"] in motions
            and max(actor.get("_minimum_range", 0), actor["range"]) - EPSILON
            <= target_distance(center(actor), target)
            <= actor["range"] + EPSILON
        ):
            resolve(target["id"])
            target_route, target_speed = motions[target["id"]]
            position = center(actor)
            target_position = center(target)
            point = next(
                (
                    p
                    for p in target_route
                    if hypot(p[0] - target_position[0], p[1] - target_position[1])
                    > EPSILON
                ),
                None,
            )
            if point is not None and 0 < target_speed <= movement_speed(actor):
                delta = (point[0] - target_position[0], point[1] - target_position[1])
                nearest = (
                    min(max(position[0], target["x"]), target["x"] + target["width"]),
                    min(max(position[1], target["y"]), target["y"] + target["height"]),
                )
                departing = sum((nearest[i] - position[i]) * delta[i] for i in (0, 1))
                endpoint = (position[0] + delta[0], position[1] + delta[1])
                if (
                    departing >= 0
                    and 0 <= endpoint[0] < width
                    and 0 <= endpoint[1] < height
                ):
                    motions[actor_id] = ([endpoint], target_speed)
        resolving.remove(actor_id)
        resolved.add(actor_id)

    for actor_id in motions:
        resolve(actor_id)


def _move(actor, route, duration, *, speed=None):
    position = center(actor)
    remaining = (movement_speed(actor) if speed is None else speed) * duration
    consumed = 0
    for point in route:
        distance = hypot(point[0] - position[0], point[1] - position[1])
        if distance <= remaining + EPSILON:
            position = point
            remaining = max(remaining - distance, 0)
            consumed += 1
        else:
            fraction = remaining / distance
            position = (
                position[0] + (point[0] - position[0]) * fraction,
                position[1] + (point[1] - position[1]) * fraction,
            )
            break
    return position, route[consumed:]


def _load_actors(specification, width, height):
    actors = {}
    occupied = set()
    target_scoring = specification.get("target_scoring")
    if target_scoring is not None:
        if (
            not isinstance(target_scoring, dict)
            or set(target_scoring) != {"selection", "source"}
            or target_scoring["selection"]
            not in {
                "legacy_route_or_footprint_distance",
                "arrival_time_then_footprint_distance",
            }
        ):
            raise InputError(
                "Target scoring needs an explicit supported policy and source"
            )
        identifier(target_scoring["source"], "target scoring evidence")
    for entry in require(specification, "actors"):
        if any(field.startswith("_") for field in entry):
            raise InputError("Actor inputs cannot override internal kernel state")
        actor = deepcopy(entry)
        if target_scoring is not None:
            actor["_target_scoring"] = target_scoring["selection"]
        actor_id = identifier(require(actor, "id"), "actor id")
        if actor_id in actors:
            raise InputError("Spatial actor instances must be unique")
        if actor.get("catalog_entity"):
            raise InputError(
                "Catalog entities require behavior adapters; no generic fallback"
            )
        identifier(require(actor, "source"), "actor statistics source")
        identifier(require(actor, "team"), "actor team")
        if require(actor, "kind") not in {"unit", "building", "defense", "wall"}:
            raise InputError("Unsupported spatial actor kind")
        if require(actor, "layer") not in {"ground", "air"}:
            raise InputError("Actor layer must be ground or air")
        if require(actor, "movement") not in {"stationary", "ground", "air"}:
            raise InputError("Unsupported movement model")
        hp = number(require(actor, "hitpoints"), "hitpoints", EPSILON)
        actor["hp"] = hp
        actor["maximum_hp"] = hp
        actor["death_time"] = None
        actor["target"] = None
        actor["next_attack"] = number(
            require(actor, "first_attack_seconds"), "first attack", 0
        )
        actor["frozen_until"] = 0.0
        actor["immune_until"] = 0.0
        spawn = require(actor, "spawn_seconds")
        if spawn != "controlled":
            number(spawn, "spawn time", 0)
        elif (
            actor["movement"] == "stationary"
            and "spell_decoy_model" not in actor
            and actor.get("siege_model", {}).get("entity") != "siege-barracks"
        ):
            raise InputError("Only moving units can await a controlled deployment")
        number(require(actor, "damage"), "damage per hit", 0)
        number(require(actor, "attack_interval_seconds"), "attack interval", EPSILON)
        number(require(actor, "speed"), "speed in tiles/second", 0)
        number(require(actor, "range"), "attack range", 0)
        if not isinstance(require(actor, "blocking"), bool):
            raise InputError("Blocking must be explicit")
        if not isinstance(require(actor, "counts_for_destruction"), bool):
            raise InputError("Destruction eligibility must be explicit")
        for field in ("target_priorities", "target_layers"):
            values = require(actor, field)
            allowed = (
                {"unit", "building", "defense", "wall"}
                if field == "target_priorities"
                else {"ground", "air"}
            )
            if len(values) != len(set(values)) or not set(values) <= allowed:
                raise InputError(f"Invalid or duplicate {field}")
        if "target_priority_tiers" not in actor:
            actor["_target_ranks"] = {
                kind: rank for rank, kind in enumerate(actor["target_priorities"])
            }
        else:
            tiers = require(actor, "target_priority_tiers")
            if (
                not isinstance(tiers, list)
                or not tiers
                or any(not isinstance(tier, list) or not tier for tier in tiers)
            ):
                raise InputError(
                    "Target priority tiers must be explicit nonempty groups"
                )
            flattened = [kind for tier in tiers for kind in tier]
            if flattened != actor["target_priorities"]:
                raise InputError(
                    "Target tiers must exactly partition the declared kinds"
                )
            actor["_target_ranks"] = {
                kind: rank for rank, tier in enumerate(tiers) for kind in tier
            }
        if actor["movement"] == "stationary":
            if actor["speed"] != 0:
                raise InputError("Stationary actors need zero movement speed")
            if (
                "spell_decoy_model" in actor
                or actor.get("siege_model", {}).get("entity") == "siege-barracks"
            ):
                if actor["width"] != 0 or actor["height"] != 0 or actor["blocking"]:
                    raise InputError(
                        "Controlled stationary reserves must be nonblocking points"
                    )
                number(actor["x"], "stationary point x", 0, width - EPSILON)
                number(actor["y"], "stationary point y", 0, height - EPSILON)
            else:
                for field, maximum in (("x", width), ("y", height)):
                    integer(require(actor, field), field, 0, maximum - 1)
                for field in ("width", "height"):
                    integer(require(actor, field), field, 1)
        else:
            actor_width = number(require(actor, "width"), "moving actor width", 0)
            actor_height = number(require(actor, "height"), "moving actor height", 0)
            if actor["blocking"] or actor_width != 0 or actor_height != 0:
                raise InputError("Moving actors are nonblocking points in this kernel")
            if actor["speed"] <= 0:
                raise InputError("Moving actors need positive movement speed")
            if actor["movement"] != actor["layer"]:
                raise InputError("Moving actor layer must match its movement model")
            number(require(actor, "x"), "x", 0, width - EPSILON)
            number(require(actor, "y"), "y", 0, height - EPSILON)
        if actor["x"] + actor["width"] > width or actor["y"] + actor["height"] > height:
            raise InputError("Actor footprint is outside the board")
        if actor["blocking"]:
            if actor["spawn_seconds"] != 0:
                raise InputError(
                    "Blocking footprints must exist at scene initialization"
                )
            cells = {
                (x, y)
                for x in range(actor["x"], actor["x"] + actor["width"])
                for y in range(actor["y"], actor["y"] + actor["height"])
            }
            if cells & occupied:
                raise InputError("Blocking footprints overlap")
            occupied |= cells
        actors[actor_id] = actor
    if not actors:
        raise InputError("Spatial scene needs actors")
    return actors


def _validate_ground_positions(actors, blocked, time):
    for actor in actors.values():
        if _active(actor, time) and actor["movement"] == "ground":
            position = center(actor)
            cell = floor(position[0]), floor(position[1])
            if cell in blocked:
                raise InputError(
                    f"Ground unit occupies a blocking footprint: {actor['id']}"
                )


def _load_effects(
    specification,
    actors,
    area_validator=None,
    healing_validator=None,
    hero_validator=None,
    reinforcement_validator=None,
    siege_validator=None,
):
    effects = deepcopy(require(specification, "effects"))
    ids = set()
    for effect in effects:
        effect_id = identifier(require(effect, "id"), "effect id")
        if effect_id in ids:
            raise InputError("Effect instances must be unique")
        ids.add(effect_id)
        number(require(effect, "time_seconds"), "effect time", 0)
        if reinforcement_validator is not None:
            reinforcement_validator(effect)
            if effect["kind"] == "clan_castle_deploy":
                continue
        if effect["kind"] == "siege_release" and siege_validator is not None:
            siege_validator(effect)
            continue
        if effect["kind"] == "hero_ability" and hero_validator is not None:
            hero_validator(effect, actors)
            continue
        if healing_validator is not None and effect["kind"] == "healing_field":
            healing_validator(effect, actors)
            continue
        if area_validator is not None and effect["kind"].startswith("area_"):
            area_validator(effect, actors)
            continue
        if require(effect, "kind") not in {
            "damage",
            "heal",
            "freeze",
            "invulnerability",
            "deploy",
        }:
            raise InputError("Unsupported spatial effect")
        targets = require(effect, "targets")
        if (
            not targets
            or len(targets) != len(set(targets))
            or not set(targets) <= set(actors)
        ):
            raise InputError("Effects require unique known target instances")
        if effect["kind"] == "deploy":
            if any(
                any(
                    key in actors[target]
                    for key in ("spell_generated_model", "spell_clone_model")
                )
                for target in targets
            ):
                raise InputError(
                    "Generated spell reserves cannot be player deployments"
                )
            if any(
                actors[target]["spawn_seconds"] != "controlled" for target in targets
            ):
                raise InputError(
                    "Deployment commands require undeployed controlled units"
                )
            positions = require(effect, "positions")
            if set(positions) != set(targets):
                raise InputError("Deployment commands need positions for all targets")
            for position in positions.values():
                number(require(position, "x"), "deployment x", 0)
                number(require(position, "y"), "deployment y", 0)
        elif effect["kind"] in {"damage", "heal"}:
            number(require(effect, "amount"), "effect amount", 0)
        else:
            number(require(effect, "duration_seconds"), "effect duration", EPSILON)
    return sorted(effects, key=lambda effect: (effect["time_seconds"], effect["id"]))


def _validate_health_batch(actors, damage, healing):
    """Sparse batches omit unaffected actors, never name unknown recipients."""
    for label, amounts in (("damage", damage), ("healing", healing)):
        if not isinstance(amounts, dict):
            raise InputError(f"Health {label} requires an actor-to-amount mapping")
        for actor_id, amount in amounts.items():
            if actor_id not in actors:
                raise InputError(
                    f"Health {label} names an unknown recipient: {actor_id}"
                )
            number(amount, f"Health {label} for {actor_id}", 0)


def _apply_health(
    actors,
    damage,
    healing,
    time,
    lethal_interceptor=None,
    healing_filter=None,
    trace=None,
):
    _validate_health_batch(actors, damage, healing)
    for actor_id, actor in actors.items():
        if not _active(actor, time):
            continue
        protected = (
            actor.get("_tesla_hidden", False) or actor["immune_until"] > time + EPSILON
        )
        received_damage = 0 if protected else damage.get(actor_id, 0)
        actor["_received_damage"] = actor.get("_received_damage", 0) + min(
            actor["hp"], received_damage
        )
        actor["hp"] = max(actor["hp"] - received_damage, 0)
        if actor["hp"] == 0:
            rescued = (
                received_damage > 0
                and lethal_interceptor is not None
                and lethal_interceptor(actor, time, trace if trace is not None else [])
            )
            if not rescued:
                actor["death_time"] = time
        if (
            actor["hp"] > 0
            and not actor.get("beneficial_field_immunity", False)
            and (healing_filter is None or healing_filter(actor, time))
        ):
            actor["hp"] = min(
                actor["maximum_hp"], actor["hp"] + healing.get(actor_id, 0)
            )


def _apply_effects(
    effects, actors, time, trace, health_handler=None, damage_receipts=None
):
    damage = defaultdict(float)
    healing = defaultdict(float)
    for effect in effects:
        if effect["kind"] != "deploy":
            continue
        for target_id in effect["targets"]:
            actor = actors[target_id]
            if actor["spawn_seconds"] != "controlled":
                raise InputError(f"Unit was already deployed: {target_id}")
            actor["spawn_seconds"] = time
            actor["x"] = effect["positions"][target_id]["x"]
            actor["y"] = effect["positions"][target_id]["y"]
    for effect in effects:
        for target_id in effect["targets"]:
            actor = actors[target_id]
            if not _active(actor, time):
                continue
            if effect["kind"] == "freeze":
                end = time + effect["duration_seconds"]
                pause_attack_work(actor, time, end)
                actor["frozen_until"] = max(actor["frozen_until"], end)
            elif effect["kind"] == "invulnerability":
                actor["immune_until"] = max(
                    actor["immune_until"], time + effect["duration_seconds"]
                )
    for effect in effects:
        for target_id in effect["targets"]:
            actor = actors[target_id]
            if not _active(actor, time):
                continue
            if effect["kind"] == "damage":
                amount = effect["amount"]
                if damage_receipts is not None:
                    source_id = effect.get("death_source")
                    amount = damage_receipts.register(
                        actor,
                        amount,
                        time,
                        source_id=effect["id"],
                        source_actor_id=source_id,
                        source_team=(
                            actors[source_id]["team"]
                            if source_id is not None
                            else "environment"
                        ),
                        origin="death" if source_id is not None else "scripted",
                    )
                elif actor["immune_until"] > time + EPSILON:
                    amount = 0
                damage[target_id] += amount
            elif effect["kind"] == "heal":
                healing[target_id] += effect["amount"]
        effect_log = {
            "time_seconds": time,
            "effect_id": effect["id"],
            "kind": effect["kind"],
            "targets": list(effect["targets"]),
        }
        if "area" in effect:
            effect_log["area"] = deepcopy(effect["area"])
        trace.append(effect_log)
    (health_handler or _apply_health)(actors, damage, healing, time)


def simulate_spatial(specification, controller=None, termination=None):
    from .combat import (
        COMBAT_RULES,
        RULESET as PATTERN_RULESET,
        PatternCombat,
        expand_area_effects,
        validate_area_effect,
    )
    from .walls import RULESET as WALL_RULESET, WALL_RULES, WallRouting
    from .healing import (
        FIELD_KIND,
        RULESET as SUPPORT_RULESET,
        SUPPORT_RULES,
        SupportCombat,
        validate_healing_field,
    )
    from .ramping import RULESET as RAMP_RULESET, RAMP_RULES, RampCombat
    from .deaths import RULESET as DEATH_RULESET, DEATH_RULES, DeathCombat
    from .townhalls import RULESET as TOWN_HALL_RULESET, TOWN_HALL_RULES, TownHallCombat
    from .defense_patterns import (
        RULESET as AREA_DEFENSE_RULESET,
        RULES as AREA_DEFENSE_RULES,
    )
    from .heroes import (
        RULESET as HERO_RULESET,
        HERO_RULES,
        HeroCombat,
        validate_ability_command,
    )

    from .artillery import (
        RULESET as ARTILLERY_RULESET,
        RULES as ARTILLERY_RULES,
        ArtilleryCombat,
    )

    from .traps import RULESET as TRAP_RULESET, RULES as TRAP_RULES, TrapCombat
    from .hit_status import RULESET as HIT_RULESET, RULES as HIT_RULES, HitStatusCombat
    from .engine_rules import RULESET as EXTENDED_RULESET, RULES as EXTENDED_RULES
    from .teslas import TeslaCombat
    from .valkyries import ValkyrieRouting
    from .buffs import BuffCombat
    from .buff_rules import RULESET as BUFF_RULESET, RULES as BUFF_RULES
    from .indirect_defenses import IndirectDefenseCombat
    from .indirect_rules import RULESET as INDIRECT_RULESET, RULES as INDIRECT_RULES
    from .sweepers import SweeperCombat
    from .sweeper_rules import RULESET as SWEEPER_RULESET, RULES as SWEEPER_RULES
    from .defending_heroes import DefendingHeroCombat
    from .defending_hero_rules import (
        RULESET as DEFENDING_HERO_RULESET,
        RULES as DEFENDING_HERO_RULES,
    )

    from .spell_towers import SpellTowerCombat
    from .spell_tower_rules import (
        RULESET as SPELL_TOWER_RULESET,
        RULES as SPELL_TOWER_RULES,
    )
    from .builder_huts import BuilderHutCombat
    from .builder_rules import RULESET as BUILDER_RULESET, RULES as BUILDER_RULES
    from .garrison_rules import RULESET as GARRISON_RULESET, RULES as GARRISON_RULES
    from .garrisons import GarrisonCombat, validate_garrison_deployment
    from .guardians import GuardianCombat, validate_guardian_deployment
    from .guardian_rules import RULESET as GUARDIAN_RULESET, RULES as GUARDIAN_RULES
    from .reinforcements import ReinforcementCombat
    from .siege_lifecycle import permanent_siege_runtime, BOUND_PERMANENT_SIEGES
    from .siege_extensions import BOUND_RECIPE_SIEGES
    from .siege_machines import SIEGE_MACHINES
    from .siege_rules import RULESET as SIEGE_RULESET, RULES as SIEGE_RULES
    from .pet_rules import RULESET as PET_RULESET, RULES as PET_RULES
    from .advanced_defense_rules import (
        RULESET as ADVANCED_DEFENSE_RULESET,
        RULES as ADVANCED_DEFENSE_RULES,
    )
    from .advanced_defenses import FANOUT_PATTERN, MultiGearCombat
    from .giga_bombs import GigaBombCombat
    from .hero_roster_rules import (
        RULESET as HERO_ROSTER_RULESET,
        RULES as HERO_ROSTER_RULES,
        select_duke_isolation_rules,
    )
    from .hero_roster import EXTENDED_HEROES, HeroRosterCombat
    from .termination_rules import (
        RULESET as TERMINATION_RULESET,
        RULES as TERMINATION_RULES,
    )
    from .attack_spell_rules import (
        RULESET as ATTACK_SPELL_RULESET,
        RULES as ATTACK_SPELL_RULES,
    )
    from .attack_spells import AttackSpellCombat
    from .battle_continuation import runtime_continuation_reasons
    from .damage_receipts import DamageReceipts
    from .hero_pets import PetCombat, validate_pet_deployment
    from .recipe_troops import RecipeTroopCombat, recipe_status_eligible
    from .defense_variants import GearedCannonCombat
    from .electro_titans import ElectroTitanCombat

    from .firespitters import FirespitterCombat
    from .firespitter_rules import (
        RULESET as FIRESPITTER_RULESET,
        RULES as FIRESPITTER_RULES,
    )

    from .trap_lifecycle_rules import (
        RULESET as TRAP_LIFECYCLE_RULESET,
        RULES as TRAP_LIFECYCLE_RULES,
    )
    from .skeleton_traps import SkeletonTrapCombat, validate_skeleton_deployment
    from .tornado_traps import TornadoTrapCombat
    from .trap_support import validate_trap_footprints

    ruleset = require(specification, "ruleset")
    if ruleset not in {
        RULESET,
        PATTERN_RULESET,
        WALL_RULESET,
        SUPPORT_RULESET,
        RAMP_RULESET,
        DEATH_RULESET,
        TOWN_HALL_RULESET,
        AREA_DEFENSE_RULESET,
        HERO_RULESET,
        ARTILLERY_RULESET,
        TRAP_RULESET,
        HIT_RULESET,
        EXTENDED_RULESET,
        BUFF_RULESET,
        INDIRECT_RULESET,
        SWEEPER_RULESET,
        DEFENDING_HERO_RULESET,
        SPELL_TOWER_RULESET,
        BUILDER_RULESET,
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    }:
        raise InputError("Unsupported spatial ruleset")
    selected_rules = {
        RULESET: MODEL_RULES,
        PATTERN_RULESET: COMBAT_RULES,
        WALL_RULESET: WALL_RULES,
        SUPPORT_RULESET: SUPPORT_RULES,
        RAMP_RULESET: RAMP_RULES,
        DEATH_RULESET: DEATH_RULES,
        TOWN_HALL_RULESET: TOWN_HALL_RULES,
        AREA_DEFENSE_RULESET: AREA_DEFENSE_RULES,
        HERO_RULESET: HERO_RULES,
        ARTILLERY_RULESET: ARTILLERY_RULES,
        TRAP_RULESET: TRAP_RULES,
        HIT_RULESET: HIT_RULES,
        EXTENDED_RULESET: EXTENDED_RULES,
        BUFF_RULESET: BUFF_RULES,
        INDIRECT_RULESET: INDIRECT_RULES,
        SWEEPER_RULESET: SWEEPER_RULES,
        DEFENDING_HERO_RULESET: DEFENDING_HERO_RULES,
        SPELL_TOWER_RULESET: SPELL_TOWER_RULES,
        BUILDER_RULESET: BUILDER_RULES,
        GARRISON_RULESET: GARRISON_RULES,
        FIRESPITTER_RULESET: FIRESPITTER_RULES,
        TRAP_LIFECYCLE_RULESET: TRAP_LIFECYCLE_RULES,
        GUARDIAN_RULESET: GUARDIAN_RULES,
        SIEGE_RULESET: SIEGE_RULES,
        PET_RULESET: PET_RULES,
        ADVANCED_DEFENSE_RULESET: ADVANCED_DEFENSE_RULES,
        HERO_ROSTER_RULESET: HERO_ROSTER_RULES,
        TERMINATION_RULESET: TERMINATION_RULES,
        ATTACK_SPELL_RULESET: ATTACK_SPELL_RULES,
    }[ruleset]
    selected_rules = select_duke_isolation_rules(
        selected_rules,
        [
            actor.get("duke_model", {}).get("parameters")
            for actor in require(specification, "actors")
        ],
    )
    if require(specification, "model_rules") != selected_rules:
        raise InputError("All spatial model conventions must be explicitly selected")
    unsupported = require(specification, "unsupported_mechanics")
    if not isinstance(unsupported, list):
        raise InputError("Unsupported mechanics must be an explicit list")
    if unsupported:
        raise InputError("Required mechanics are not implemented in the spatial kernel")
    width = integer(require(specification, "width"), "board width", 1)
    height = integer(require(specification, "height"), "board height", 1)
    duration = number(require(specification, "duration_seconds"), "duration", EPSILON)
    if termination is not None:
        if abs(termination.limit - duration) > EPSILON:
            raise InputError("Termination observer must use the declared scene horizon")
        if termination.requires_runtime_facts:
            for field in specification.get("persistent_hazards", []):
                if "source_team" not in field:
                    raise InputError(
                        "Force exhaustion requires explicit source_team on static hazards"
                    )
    step = number(
        require(specification, "maximum_step_seconds"), "maximum solver step", EPSILON
    )
    recording = number(
        require(specification, "recording_interval_seconds"),
        "recording interval",
        EPSILON,
    )
    actors = _load_actors(specification, width, height)
    from .troop_line_bindings import validate_line_owners

    validate_line_owners(
        actors,
        ruleset in {HERO_ROSTER_RULESET, TERMINATION_RULESET, ATTACK_SPELL_RULESET},
    )
    from .crafted_bindings import validate_crafted_owners

    validate_crafted_owners(
        actors,
        ruleset in {HERO_ROSTER_RULESET, TERMINATION_RULESET, ATTACK_SPELL_RULESET},
    )
    from .wall_breakers import validate_wall_breaker_owners

    validate_wall_breaker_owners(
        actors,
        ruleset in {HERO_ROSTER_RULESET, TERMINATION_RULESET, ATTACK_SPELL_RULESET},
    )
    unbound_troop_models = {
        "troop_summon_model",
        "troop_behavior_model",
        "troop_identity_target_model",
        "troop_fire_pool_model",
        "meteor_parameters",
        "meteor_adult_model",
        "meteor_mite_model",
        "ruin_witch_model",
        "druid_model",
        "druid_form_model",
    }
    for actor in actors.values():
        unbound = sorted(unbound_troop_models.intersection(actor))
        if "wall_breaker_model" in actor:
            unbound = [name for name in unbound if name != "troop_behavior_model"]
        if unbound:
            raise InputError(
                f"Unbound troop lifecycle at shared kernel entry: {actor['id']}: {', '.join(unbound)}"
            )
        adapter = actor.get("entity_adapter", {})
        if (
            "troop_death_buff_model" in actor
            or adapter.get("entity") == "super-valkyrie"
        ):
            if (
                ruleset
                not in {HERO_ROSTER_RULESET, TERMINATION_RULESET, ATTACK_SPELL_RULESET}
                or adapter.get("entity") != "super-valkyrie"
                or actor["team"] != "attack"
                or adapter.get("attacking_extension_scope")
                != "explicit_experimental_attacking_troop_extensions"
                or not actor.get("troop_death_buff_model")
                or actor.get("troop_death_buff_model")
                != adapter.get("death_buff_parameters")
                or "valkyrie_model" not in actor
                or actor.get("attack_model", {}).get("kind") != "source_radial"
            ):
                raise InputError(
                    "Death Rage requires its complete compiled Super Valkyrie owner and v27+ scope"
                )
    if any(
        "siege_model" in actor
        and actor["siege_model"].get("entity")
        not in SIEGE_MACHINES | BOUND_RECIPE_SIEGES | BOUND_PERMANENT_SIEGES
        for actor in actors.values()
    ):
        raise InputError("Siege lifecycle is not yet bound to the shared kernel")
    for actor in actors.values():
        if "aura_model" in actor and (
            ruleset
            not in {HERO_ROSTER_RULESET, TERMINATION_RULESET, ATTACK_SPELL_RULESET}
            or actor.get("entity_adapter", {}).get("entity") != "electro-titan"
            or actor.get("entity_adapter", {}).get("attacking_extension_scope")
            != "explicit_experimental_attacking_troop_extensions"
        ):
            raise InputError(
                "Titan aura requires its compiled owner and explicit v27+ extension contract"
            )
    for actor in actors.values():
        if "duke_model" in actor and (
            actor.get("hero_model", {}).get("entity") != "dragon-duke"
        ):
            raise InputError("Duke intrinsic models require their owning hero")
    giga_bomb_models = [
        trap
        for trap in specification.get("traps", [])
        if trap.get("entity") == "giga-bomb"
    ]
    if ruleset not in {
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and (
        giga_bomb_models
        or any(
            "multi_gear_model" in actor
            or "revenge_model" in actor
            or "geared_cannon_model" in actor
            or "inferno_ammunition_model" in actor
            or (
                actor.get("entity_adapter", {}).get("entity") == "x-bow"
                and "weapon_ammunition" in actor
            )
            or actor.get("spell_tower_model", {}).get("mode") == "earthquake"
            or actor.get("attack_model", {}).get("kind") == FANOUT_PATTERN
            for actor in actors.values()
        )
    ):
        raise InputError("Advanced TH17/18 defenses require the explicit v26 ruleset")
    if ruleset not in {
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and any("pet_model" in actor for actor in actors.values()):
        raise InputError("Paired pet lifecycle models require the explicit v25 ruleset")
    has_reinforcements = "attacking_reinforcements" in specification
    if ruleset not in {
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and (
        has_reinforcements
        or any(
            "siege_model" in actor
            or "payload_member_model" in actor
            or "barracks_member_model" in actor
            or "barrel_member_model" in actor
            or actor.get("attack_model", {}).get("kind")
            in {"siege_area", "siege_extended", "siege_barrel"}
            for actor in actors.values()
        )
    ):
        raise InputError(
            "Attacking reinforcements and siege require the explicit v24 ruleset"
        )
    lifecycle_traps = [
        trap
        for trap in specification.get("traps", [])
        if trap.get("entity") in {"skeleton-trap", "tornado-trap"}
    ]
    if ruleset not in {
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and any(
        "guardian_model" in actor or "guardian_hall_model" in actor
        for actor in actors.values()
    ):
        raise InputError("TH18 Guardians require the explicit v23 ruleset")
    if ruleset not in {
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and (
        lifecycle_traps
        or any("trap_summon_model" in actor for actor in actors.values())
    ):
        raise InputError("Skeleton and Tornado Traps require the explicit v22 ruleset")
    if ruleset not in {
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and any(
        "firespitter_model" in actor
        or actor.get("attack_model", {}).get("kind") == "firespitter_ballistic_bullet"
        for actor in actors.values()
    ):
        raise InputError("Firespitter shot streams require the explicit v21 ruleset")
    if ruleset not in {
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and any(
        "garrison_model" in actor or "garrison_member_model" in actor
        for actor in actors.values()
    ):
        raise InputError("Defending garrisons require the explicit v20 ruleset")
    if ruleset not in {
        BUILDER_RULESET,
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and any("builder_hut_model" in actor for actor in actors.values()):
        raise InputError("Builder repair workers require the explicit v19 ruleset")
    if ruleset not in {
        SPELL_TOWER_RULESET,
        BUILDER_RULESET,
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and any("spell_tower_model" in actor for actor in actors.values()):
        raise InputError("Reactive Spell Towers require the explicit v18 ruleset")
    if ruleset not in {
        INDIRECT_RULESET,
        SWEEPER_RULESET,
        DEFENDING_HERO_RULESET,
        SPELL_TOWER_RULESET,
        BUILDER_RULESET,
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and any(
        "indirect_model" in actor
        or actor.get("attack_model", {}).get("kind") == "eagle_shell"
        for actor in actors.values()
    ):
        raise InputError("Indirect shells require the explicit v15 ruleset")
    if ruleset not in {
        SWEEPER_RULESET,
        DEFENDING_HERO_RULESET,
        SPELL_TOWER_RULESET,
        BUILDER_RULESET,
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and any("sweeper_model" in actor for actor in actors.values()):
        raise InputError("Sweeper displacement requires the explicit v16 ruleset")
    if ruleset not in {
        DEFENDING_HERO_RULESET,
        SPELL_TOWER_RULESET,
        BUILDER_RULESET,
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and any(
        "defending_hero_model" in actor or "defending_unit_response" in actor
        for actor in actors.values()
    ):
        raise InputError("Defending hero behavior requires the explicit v17 ruleset")
    if ruleset not in {
        EXTENDED_RULESET,
        BUFF_RULESET,
        INDIRECT_RULESET,
        SWEEPER_RULESET,
        DEFENDING_HERO_RULESET,
        SPELL_TOWER_RULESET,
        BUILDER_RULESET,
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and any(
        "tesla_model" in actor
        or "valkyrie_model" in actor
        or actor.get("attack_model", {}).get("kind") == "source_radial"
        for actor in actors.values()
    ):
        raise InputError(
            "Tesla and source-centered Valkyrie behavior require the extended ruleset"
        )
    if ruleset not in {
        AREA_DEFENSE_RULESET,
        HERO_RULESET,
        ARTILLERY_RULESET,
        TRAP_RULESET,
        HIT_RULESET,
        EXTENDED_RULESET,
        BUFF_RULESET,
        INDIRECT_RULESET,
        SWEEPER_RULESET,
        DEFENDING_HERO_RULESET,
        SPELL_TOWER_RULESET,
        BUILDER_RULESET,
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and any(
        "weapon_ammunition" in actor
        or actor.get("attack_model", {}).get("kind") == "directional_splash"
        or "splash_layer_policy" in actor.get("attack_model", {})
        or "inactive_primary_policy"
        in actor.get("attack_model", {}).get("projectile", {})
        for actor in actors.values()
    ):
        raise InputError(
            "Area-defense geometry, ammunition and projectile policies require the v8 ruleset"
        )
    combat = PatternCombat(actors) if ruleset != RULESET else None
    wall_routing = (
        WallRouting(actors)
        if ruleset
        in {
            WALL_RULESET,
            SUPPORT_RULESET,
            RAMP_RULESET,
            DEATH_RULESET,
            TOWN_HALL_RULESET,
            AREA_DEFENSE_RULESET,
            HERO_RULESET,
            ARTILLERY_RULESET,
            TRAP_RULESET,
            HIT_RULESET,
            EXTENDED_RULESET,
            BUFF_RULESET,
            INDIRECT_RULESET,
            SWEEPER_RULESET,
            DEFENDING_HERO_RULESET,
            SPELL_TOWER_RULESET,
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        }
        else None
    )
    if wall_routing is None and any(
        "wall_behavior" in actor for actor in actors.values()
    ):
        raise InputError("Wall behavior requires the explicit wall-breach ruleset")
    if ruleset not in {
        HERO_RULESET,
        ARTILLERY_RULESET,
        TRAP_RULESET,
        HIT_RULESET,
        EXTENDED_RULESET,
        BUFF_RULESET,
        INDIRECT_RULESET,
        SWEEPER_RULESET,
        DEFENDING_HERO_RULESET,
        SPELL_TOWER_RULESET,
        BUILDER_RULESET,
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    } and any(
        "hero_model" in actor
        or "summon_model" in actor
        or actor.get("wall_behavior", {}).get("kind") == "jump_enemy_walls"
        for actor in actors.values()
    ):
        raise InputError("Hero, summon and wall-jump behavior requires the v9 ruleset")
    select_target = wall_routing.select_target if wall_routing else _select_target
    support = (
        SupportCombat(actors, specification, select_target)
        if ruleset
        in {
            SUPPORT_RULESET,
            RAMP_RULESET,
            DEATH_RULESET,
            TOWN_HALL_RULESET,
            AREA_DEFENSE_RULESET,
            HERO_RULESET,
            ARTILLERY_RULESET,
            TRAP_RULESET,
            HIT_RULESET,
            EXTENDED_RULESET,
            BUFF_RULESET,
            INDIRECT_RULESET,
            SWEEPER_RULESET,
            DEFENDING_HERO_RULESET,
            SPELL_TOWER_RULESET,
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        }
        else None
    )
    if support is None and any(
        "healing_model" in actor or "healing_class" in actor
        for actor in actors.values()
    ):
        raise InputError("Healing behaviors require the explicit support ruleset")
    if support is not None:
        select_target = support.select_target
    ramp = (
        RampCombat(actors)
        if ruleset
        in {
            RAMP_RULESET,
            DEATH_RULESET,
            TOWN_HALL_RULESET,
            AREA_DEFENSE_RULESET,
            HERO_RULESET,
            ARTILLERY_RULESET,
            TRAP_RULESET,
            HIT_RULESET,
            EXTENDED_RULESET,
            BUFF_RULESET,
            INDIRECT_RULESET,
            SWEEPER_RULESET,
            DEFENDING_HERO_RULESET,
            SPELL_TOWER_RULESET,
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        }
        else None
    )
    if ramp is None and any("ramp_model" in actor for actor in actors.values()):
        raise InputError("Lock-dependent weapons require the explicit ramp ruleset")
    deaths = (
        DeathCombat(actors)
        if ruleset
        in {
            DEATH_RULESET,
            TOWN_HALL_RULESET,
            AREA_DEFENSE_RULESET,
            HERO_RULESET,
            ARTILLERY_RULESET,
            TRAP_RULESET,
            HIT_RULESET,
            EXTENDED_RULESET,
            BUFF_RULESET,
            INDIRECT_RULESET,
            SWEEPER_RULESET,
            DEFENDING_HERO_RULESET,
            SPELL_TOWER_RULESET,
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        }
        else None
    )
    if deaths is None and any("death_model" in actor for actor in actors.values()):
        raise InputError("Death behavior requires the explicit death-effects ruleset")
    town_halls = None
    if ruleset in {
        TOWN_HALL_RULESET,
        AREA_DEFENSE_RULESET,
        HERO_RULESET,
        ARTILLERY_RULESET,
        TRAP_RULESET,
        HIT_RULESET,
        EXTENDED_RULESET,
        BUFF_RULESET,
        INDIRECT_RULESET,
        SWEEPER_RULESET,
        DEFENDING_HERO_RULESET,
        SPELL_TOWER_RULESET,
        BUILDER_RULESET,
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    }:
        require(specification, "target_scoring")
        fields = require(specification, "persistent_hazards")
        if not isinstance(fields, list):
            raise InputError("Persistent hazards must be an explicit list")
        town_halls = TownHallCombat(actors, fields, select_target)
        select_target = town_halls.select_target
    elif (
        any("town_hall_model" in actor for actor in actors.values())
        or "persistent_hazards" in specification
    ):
        raise InputError(
            "Town Hall lifecycle/hazards require their own explicit ruleset"
        )
    area_validator = validate_area_effect if combat is not None else None
    heroes = (
        HeroCombat(
            actors,
            combat,
            ruleset in {HERO_ROSTER_RULESET, TERMINATION_RULESET, ATTACK_SPELL_RULESET},
        )
        if ruleset
        in {
            HERO_RULESET,
            ARTILLERY_RULESET,
            TRAP_RULESET,
            HIT_RULESET,
            EXTENDED_RULESET,
            BUFF_RULESET,
            INDIRECT_RULESET,
            SWEEPER_RULESET,
            DEFENDING_HERO_RULESET,
            SPELL_TOWER_RULESET,
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        }
        else None
    )
    artillery = (
        ArtilleryCombat(actors)
        if ruleset
        in {
            ARTILLERY_RULESET,
            TRAP_RULESET,
            HIT_RULESET,
            EXTENDED_RULESET,
            BUFF_RULESET,
            INDIRECT_RULESET,
            SWEEPER_RULESET,
            DEFENDING_HERO_RULESET,
            SPELL_TOWER_RULESET,
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        }
        else None
    )
    if artillery is None and any(
        "artillery_model" in actor for actor in actors.values()
    ):
        raise InputError("Artillery impact flames require the v10 ruleset")
    traps = None
    if ruleset in {
        TRAP_RULESET,
        HIT_RULESET,
        EXTENDED_RULESET,
        BUFF_RULESET,
        INDIRECT_RULESET,
        SWEEPER_RULESET,
        DEFENDING_HERO_RULESET,
        SPELL_TOWER_RULESET,
        BUILDER_RULESET,
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    }:
        trap_models = require(specification, "traps")
        validate_trap_footprints(trap_models, actors, width, height)
        traps = TrapCombat(
            [
                trap
                for trap in trap_models
                if trap.get("entity")
                not in {"skeleton-trap", "tornado-trap", "giga-bomb"}
            ],
            actors,
            width,
            height,
        )
    elif "traps" in specification:
        raise InputError("Traps require the explicit v11 ruleset")
    hit_status = (
        HitStatusCombat(actors)
        if ruleset
        in {
            HIT_RULESET,
            EXTENDED_RULESET,
            BUFF_RULESET,
            INDIRECT_RULESET,
            SWEEPER_RULESET,
            DEFENDING_HERO_RULESET,
            SPELL_TOWER_RULESET,
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        }
        else None
    )
    if hit_status is None and any(
        "on_hit_status" in actor for actor in actors.values()
    ):
        raise InputError("On-hit status effects require the explicit v12 ruleset")
    teslas = (
        TeslaCombat(actors, select_target)
        if ruleset
        in {
            EXTENDED_RULESET,
            BUFF_RULESET,
            INDIRECT_RULESET,
            SWEEPER_RULESET,
            DEFENDING_HERO_RULESET,
            SPELL_TOWER_RULESET,
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        }
        else None
    )
    if teslas is not None:
        select_target = teslas.select_target
    valkyries = (
        ValkyrieRouting(actors, select_target)
        if ruleset
        in {
            EXTENDED_RULESET,
            BUFF_RULESET,
            INDIRECT_RULESET,
            SWEEPER_RULESET,
            DEFENDING_HERO_RULESET,
            SPELL_TOWER_RULESET,
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        }
        else None
    )
    if valkyries is not None:
        select_target = valkyries.select_target
    buffs = None
    if ruleset in {
        BUFF_RULESET,
        INDIRECT_RULESET,
        SWEEPER_RULESET,
        DEFENDING_HERO_RULESET,
        SPELL_TOWER_RULESET,
        BUILDER_RULESET,
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    }:
        buffs = BuffCombat(actors, require(specification, "buff_fields"))
    elif "buff_fields" in specification:
        raise InputError("Area buff fields require the explicit v14 ruleset")
    indirect = None
    if ruleset in {
        INDIRECT_RULESET,
        SWEEPER_RULESET,
        DEFENDING_HERO_RULESET,
        SPELL_TOWER_RULESET,
        BUILDER_RULESET,
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    }:
        indirect = IndirectDefenseCombat(actors, combat, select_target, specification)
        select_target = indirect.select_target
    sweepers = (
        SweeperCombat(actors, width, height)
        if ruleset
        in {
            SWEEPER_RULESET,
            DEFENDING_HERO_RULESET,
            SPELL_TOWER_RULESET,
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        }
        else None
    )
    defending_heroes = None
    skeleton_traps = None
    tornado_traps = None
    if ruleset in {
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    }:
        skeleton_traps = SkeletonTrapCombat(
            [trap for trap in lifecycle_traps if trap["entity"] == "skeleton-trap"],
            actors,
            width,
            height,
        )
        tornado_traps = TornadoTrapCombat(
            [trap for trap in lifecycle_traps if trap["entity"] == "tornado-trap"],
            actors,
            width,
            height,
            sweepers.motion,
        )
    if ruleset in {
        DEFENDING_HERO_RULESET,
        SPELL_TOWER_RULESET,
        BUILDER_RULESET,
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    }:
        defending_heroes = DefendingHeroCombat(actors, select_target, specification)
        select_target = defending_heroes.select_target
    spell_towers = (
        SpellTowerCombat(actors, town_halls.hazards)
        if ruleset
        in {
            SPELL_TOWER_RULESET,
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        }
        else None
    )
    builders = (
        BuilderHutCombat(actors, width, height, town_halls.hazards)
        if ruleset
        in {
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        }
        else None
    )
    guardians = None
    if ruleset in {
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    }:
        guardians = GuardianCombat(actors, select_target, specification)
        select_target = guardians.select_target

    def effect_observer(effects, actors, time, trace):
        if builders is not None:
            builders.apply_effects(effects, actors, time, trace)
        if guardians is not None:
            guardians.apply_effects(effects, actors, time, trace)

    garrisons = None
    if ruleset in {
        GARRISON_RULESET,
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    }:
        garrisons = GarrisonCombat(actors, select_target, specification)
        select_target = garrisons.select_target
    firespitters = None
    if ruleset in {
        FIRESPITTER_RULESET,
        TRAP_LIFECYCLE_RULESET,
        GUARDIAN_RULESET,
        SIEGE_RULESET,
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    }:
        firespitters = FirespitterCombat(actors, select_target)
        select_target = firespitters.select_target
    reinforcements = None
    sieges = None
    if has_reinforcements:
        reinforcements = ReinforcementCombat(
            actors, specification["attacking_reinforcements"], width, height
        )
        sieges = permanent_siege_runtime(
            actors, select_target, reinforcements, width, height
        )
        reinforcements = sieges.reinforcements
        select_target = sieges.select_target
    elif any(
        "siege_model" in actor
        or "payload_member_model" in actor
        or "barracks_member_model" in actor
        or "barrel_member_model" in actor
        or actor.get("attack_model", {}).get("kind")
        in {"siege_area", "siege_extended", "siege_barrel"}
        for actor in actors.values()
    ):
        raise InputError(
            "Attacking reserves and siege require their owned delivery group"
        )

    pets = None
    if ruleset in {
        PET_RULESET,
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    }:
        pets = PetCombat(actors, width, height, select_target)
        select_target = pets.select_target
        if traps is not None:
            traps.lethal_interceptor = pets.intercept_lethal
    multi_gear = None
    giga_bombs = None
    if ruleset in {
        ADVANCED_DEFENSE_RULESET,
        HERO_ROSTER_RULESET,
        TERMINATION_RULESET,
        ATTACK_SPELL_RULESET,
    }:
        multi_gear = MultiGearCombat(actors, select_target, combat)
        select_target = multi_gear.select_target
        giga_bombs = GigaBombCombat(
            giga_bomb_models, actors, width, height, sweepers.motion
        )

    attack_spells = None
    if ruleset == ATTACK_SPELL_RULESET:
        attack_spells = AttackSpellCombat(
            require(specification, "attack_spell_models"),
            actors,
            town_halls.hazards,
            width,
            height,
        )
    elif "attack_spell_models" in specification:
        raise InputError("Attacking spell models require the explicit v29 ruleset")
    elif any(
        any(
            key in actor
            for key in (
                "spell_decoy_model",
                "spell_generated_model",
                "spell_clone_model",
            )
        )
        for actor in actors.values()
    ):
        raise InputError(
            "Generated Totem actors require the explicit v29 spell runtime"
        )
    hero_roster = None
    damage_receipts = None
    if ruleset in {HERO_ROSTER_RULESET, TERMINATION_RULESET, ATTACK_SPELL_RULESET}:
        hero_roster = HeroRosterCombat(
            actors, combat, hit_status, select_target, width, height
        )
        heroes.extensions = hero_roster
        select_target = hero_roster.select_target
        wall_routing.area_impacts = hero_roster.wall_impacts
        damage_receipts = DamageReceipts(
            {
                key
                for key, actor in actors.items()
                if actor.get("hero_model", {}).get("entity") in EXTENDED_HEROES
                or "spell_generated_model" in actor
                or "spell_clone_model" in actor
                or (
                    actor["team"] == "attack"
                    and actor["kind"] == "unit"
                    and any(
                        model["entity"] == "ice-block-spell"
                        for model in specification.get("attack_spell_models", [])
                    )
                )
            }
        )
        for runtime in (
            combat,
            wall_routing,
            traps,
            tornado_traps,
            giga_bombs,
            artillery,
            firespitters,
            deaths,
            attack_spells,
            spell_towers,
            sieges,
            town_halls.hazards if town_halls is not None else None,
        ):
            if runtime is not None:
                runtime.damage_receipts = damage_receipts
    elif any("duke_model" in actor for actor in actors.values()):
        raise InputError("Duke runtime behavior requires the explicit v27 ruleset")

    from .defending_troop_runtime import DefendingTroopLineCombat

    troop_lines = DefendingTroopLineCombat(actors)
    troop_lines.damage_receipts = damage_receipts
    troop_lines.damage_eligible = (
        combat._damage_eligible if combat is not None else None
    )
    from .crafted_defenses import CraftedDefenseCombat

    crafted = CraftedDefenseCombat(
        actors, town_halls.hazards if town_halls is not None else None
    )
    crafted.damage_receipts = damage_receipts
    recipe_troops = RecipeTroopCombat(actors)
    from .troop_death_buffs import TroopDeathBuffCombat

    troop_death_buffs = (
        TroopDeathBuffCombat(actors, buffs) if buffs is not None else None
    )
    geared_cannons = GearedCannonCombat(actors, combat)
    titans = ElectroTitanCombat(actors)
    titans.damage_receipts = damage_receipts
    if recipe_troops.models and hero_roster is None:
        raise InputError("Recipe troop runtime requires the explicit v27+ ruleset")
    recipe_troops.damage_receipts = damage_receipts
    recipe_troops.base_selector = select_target
    select_target = recipe_troops.select_target
    from .troop_behaviors import AttackingTroopCombat

    troop_behaviors = AttackingTroopCombat(actors)
    behavior_base_selector = select_target

    def select_behavior_target(actor, actors, time, blocked, width, height):
        return troop_behaviors.select_target(
            actor, actors, time, blocked, width, height, behavior_base_selector
        )

    if troop_behaviors.models:
        select_target = select_behavior_target
    from .advanced_spell_models import SUPPORTED_SPELLS as ADVANCED_SPELLS
    from .advanced_spell_bindings import SharedAdvancedSpells

    advanced_models = [
        m
        for m in specification.get("attack_spell_models", [])
        if m["entity"] in ADVANCED_SPELLS
    ]
    if advanced_models:
        attack_spells.advanced = SharedAdvancedSpells(
            advanced_models,
            actors,
            require(specification, "advanced_spell_binding"),
            width,
            height,
            select_target,
            pets,
        )
        select_target = attack_spells.advanced.select_target
    elif "advanced_spell_binding" in specification or any(
        any(
            key in a
            for key in (
                "spell_generated_model",
                "spell_clone_model",
                "spell_unit_effects",
            )
        )
        for a in actors.values()
    ):
        raise InputError("Generated spell actors require their owning advanced spell")
    for actor in actors.values():
        if any(key.startswith("_spell_") for key in actor) and not any(
            key in actor for key in ("spell_generated_model", "spell_clone_model")
        ):
            raise InputError("Private spell state requires its generated owner")

    def apply_health(health_actors, damage, healing, at_time):
        _validate_health_batch(health_actors, damage, healing)
        settled_receipts = (
            damage_receipts.settle(health_actors, damage, at_time)
            if damage_receipts is not None
            else []
        )
        _apply_health(
            health_actors,
            damage,
            healing,
            at_time,
            pets.intercept_lethal if pets is not None else None,
            pets.healing_allowed if pets is not None else None,
            trace,
        )
        if hero_roster is not None:
            trace.extend(
                {
                    "event": (
                        "hero_received_damage"
                        if "hero_model" in health_actors[receipt["target_id"]]
                        else "damage_received"
                    ),
                    **receipt,
                }
                for receipt in settled_receipts
            )
            counter_healing = hero_roster.after_health(
                health_actors, settled_receipts, at_time, trace
            )
            if counter_healing:
                _apply_health(
                    health_actors,
                    defaultdict(float),
                    counter_healing,
                    at_time,
                    pets.intercept_lethal if pets is not None else None,
                    pets.healing_allowed if pets is not None else None,
                    trace,
                )

    def apply_effects(effects, effect_actors, at_time, effect_trace):
        _apply_effects(
            effects, effect_actors, at_time, effect_trace, apply_health, damage_receipts
        )

    def pet_status_impact(packet, target, impact_actors, at_time, impact_trace):
        if (
            hit_status is not None
            and "spell_decoy_model" not in target
            and recipe_status_eligible(impact_actors[packet["source"]], target)
        ):
            hit_status.impact(packet, target, impact_actors, at_time, impact_trace)
        recipe_troops.impact(packet, target, impact_actors, at_time, impact_trace)
        if pets is not None:
            pets.impact(packet, target, impact_actors, at_time, impact_trace)

    def settle_lifecycles(time, trace, allow_release=True):
        # A field can deal damage immediately and destroy another source. Keep
        # same-timestamp death releases and hazard pulses in one settling phase.
        while True:
            changed = False
            if hero_roster is not None:
                hero_roster.after_health(actors, [], time, trace)
                hero_damage, hero_healing = hero_roster.resolve(
                    actors, time, trace, damage_receipts
                )
                if hero_damage or hero_healing:
                    apply_health(actors, hero_damage, hero_healing, time)
                    changed = True
            if sieges is not None:
                changed |= sieges.prepare(
                    actors, time, trace, allow_release=allow_release
                )
                siege_damage = sieges.resolve(actors, time, trace)
                if siege_damage:
                    apply_health(actors, siege_damage, defaultdict(float), time)
                    changed = True
            if spell_towers is not None:
                spell_towers.prepare(actors, time, trace)
                quake_damage = spell_towers.resolve(actors, time, trace)
                if quake_damage:
                    apply_health(actors, quake_damage, defaultdict(float), time)
                    changed = True
            geared_cannons.prepare(actors, time, trace)
            if town_halls is not None:
                town_halls.settle(
                    actors, time, trace, deaths, effect_observer, apply_health
                )
            elif deaths is not None:
                deaths.settle(actors, time, trace, effect_observer, apply_health)
            if troop_death_buffs is not None:
                emitted_fields = len(troop_death_buffs.fields)
                troop_death_buffs.prepare(time, trace)
                if len(troop_death_buffs.fields) != emitted_fields:
                    buffs.prepare(actors, time, trace)
            if sieges is not None:
                changed |= sieges.prepare(
                    actors, time, trace, allow_release=allow_release
                )
            if attack_spells is not None:
                attack_spells.prepare(actors, time, trace)
            if giga_bombs is not None:
                # Newly released finite children participate at this timestamp.
                # A zero-delay blast can cause more source-death releases, so
                # settle it inside this loop and retain the trap's one-shot latch.
                resolved_before = len(giga_bombs.resolved)
                giga_damage = giga_bombs.update(actors, time, trace)
                if giga_damage:
                    apply_health(actors, giga_damage, defaultdict(float), time)
                changed |= len(giga_bombs.resolved) != resolved_before
            if spell_towers is not None:
                changed |= bool(spell_towers.prepare(actors, time, trace))
            if hero_roster is not None:
                changed |= hero_roster.has_due_offense(time)
            if not changed:
                break

    effects = _load_effects(
        specification,
        actors,
        area_validator,
        validate_healing_field if support is not None else None,
        validate_ability_command if heroes is not None else None,
        reinforcements.validate_command if reinforcements is not None else None,
        sieges.validate_command if sieges is not None else None,
    )
    trace = []
    if controller is not None and getattr(controller, "paid_observation", False):
        effects = controller.bind_runtime(
            actors, effects, buffs, attack_spells, heroes, reinforcements, sieges
        )
    frames = []
    time = 0.0
    next_recording = 0.0
    effect_index = 0
    deadline_tolerance = (
        0 if getattr(controller, "paid_observation", False) else EPSILON
    )
    revisit_time = False
    if town_halls is not None:
        # Declared initial defenses must be eligible for time-zero abilities.
        # Damage/threshold activation and hazards retain their settling phase.
        town_halls.prepare(actors, time, trace, initial_state_only=True)
    while time <= duration + EPSILON:
        observe_controller = not revisit_time
        revisit_time = False
        if teslas is not None:
            teslas.prepare(actors, time, trace)
        if heroes is not None:
            heroes.prepare(actors, time, trace)
        if pets is not None:
            pets.prepare(actors, time, trace)
            if heroes is not None:
                heroes.prepare(actors, time, trace)
        if buffs is not None:
            buffs.prepare(actors, time, trace)
        due = []
        while (
            effect_index < len(effects)
            and effects[effect_index]["time_seconds"] <= time + EPSILON
        ):
            due.append(effects[effect_index])
            effect_index += 1
        if controller is not None and observe_controller:
            due.extend(controller.commands(time, actors))
            if getattr(controller, "paid_observation", False) and buffs is not None:
                buffs.prepare(actors, time, trace)
        if reinforcements is not None:
            due = reinforcements.apply_commands(due, time, trace)
        if garrisons is not None:
            for effect in due:
                validate_garrison_deployment(effect, actors)
        if guardians is not None:
            for effect in due:
                validate_guardian_deployment(effect, actors)
        if skeleton_traps is not None:
            for effect in due:
                validate_skeleton_deployment(effect, actors)
        if pets is not None:
            for effect in due:
                validate_pet_deployment(effect, actors)
        # Internal workers and dormant Guardians need original area geometry.
        effect_observer(due, actors, time, trace)
        if indirect is not None:
            indirect.observe_commands(due, time, trace)
        if combat is not None:
            deployments = [effect for effect in due if effect["kind"] == "deploy"]
            apply_effects(deployments, actors, time, trace)
            due = [effect for effect in due if effect["kind"] != "deploy"]
            if pets is not None:
                pets.prepare(actors, time, trace)
            if sieges is not None:
                due = sieges.apply_commands(due, time, trace)
            if heroes is not None:
                due = heroes.expand_commands(due, actors, time, trace)
                summons = [effect for effect in due if effect["kind"] == "deploy"]
                apply_effects(summons, actors, time, trace)
                due = [effect for effect in due if effect["kind"] != "deploy"]
            if support is not None:
                for field in due:
                    if field["kind"] == FIELD_KIND:
                        support.schedule_field(field, actors, time)
                due = [effect for effect in due if effect["kind"] != FIELD_KIND]
            due = expand_area_effects(
                [effect for effect in due if effect["kind"] != "deploy"], actors, time
            )
        apply_effects(due, actors, time, trace)
        if attack_spells is not None:
            attack_spells.prepare(actors, time, trace)
            apply_health(
                actors,
                attack_spells.resolve(actors, time, trace, effect_observer),
                defaultdict(float),
                time,
            )
        if hit_status is not None:
            hit_status.prepare(actors, time, trace)
        if heroes is not None:
            heroes.prepare(actors, time, trace)
        if pets is not None:
            pets.prepare(actors, time, trace)
            if heroes is not None:
                heroes.prepare(actors, time, trace)
        if traps is not None:
            apply_health(
                actors, traps.update(actors, time, trace), defaultdict(float), time
            )
        if skeleton_traps is not None:
            skeleton_traps.prepare(actors, time, trace)
        if tornado_traps is not None:
            tornado_traps.prepare(actors, time, trace)
            apply_health(
                actors,
                tornado_traps.resolve(actors, time, trace),
                defaultdict(float),
                time,
            )
        if artillery is not None:
            apply_health(
                actors, artillery.resolve(actors, time, trace), defaultdict(float), time
            )
        settle_lifecycles(time, trace)
        if garrisons is not None:
            garrisons.prepare(actors, time, trace)
        if guardians is not None:
            guardians.prepare(actors, time, trace)
        if attack_spells is not None:
            attack_spells.prepare(actors, time, trace)
        if teslas is not None:
            teslas.prepare(actors, time, trace)
        if buffs is not None:
            buffs.prepare(actors, time, trace)
        for actor in actors.values():
            if not (
                0 <= actor["x"] < width
                and 0 <= actor["y"] < height
                and actor["x"] + actor["width"] <= width
                and actor["y"] + actor["height"] <= height
            ):
                raise InputError(f"Deployment is outside the board: {actor['id']}")
        if indirect is not None:
            indirect.prepare(actors, time, trace)
        if firespitters is not None:
            firespitters.prepare(actors, time, trace)
        if multi_gear is not None:
            multi_gear.prepare(actors, time, trace)
        blocked = _blocked(actors, time)
        if defending_heroes is not None:
            defending_heroes.prepare(actors, time, trace)
        if sweepers is not None:
            sweepers.prepare(actors, time, trace)
            sweepers.resolve(actors, time, trace)
        if builders is not None:
            builders.prepare(actors, time, trace)
        if wall_routing is not None:
            wall_routing.validate_positions(actors, blocked, time)
        else:
            _validate_ground_positions(actors, blocked, time)
        if support is not None:
            support.prepare_targets(actors, time, blocked, width, height)
        recipe_troops.prepare(time, trace)
        troop_behaviors.prepare(
            time,
            lambda actor: select_target(actor, actors, time, blocked, width, height)[0],
            trace,
        )
        if ramp is not None:
            ramp.prepare(actors, time, select_target, blocked, width, height, trace)
        damage = defaultdict(float)
        for actor in sorted(actors.values(), key=lambda item: item["id"]):
            if (
                not _active(actor, time)
                or actor["frozen_until"] > time + EPSILON
                or actor.get("_spell_pause_until", 0) > time
            ):
                continue
            if spell_towers is not None and actor["id"] in spell_towers.models:
                continue
            if sweepers is not None and (
                actor["id"] in sweepers.models or sweepers.attack_locked(actor, time)
            ):
                continue
            if actor["id"] in crafted.models:
                crafted.launch(actor["id"], time, trace)
                continue
            target, _ = select_target(actor, actors, time, blocked, width, height)
            if support is not None and actor["id"] in support.models:
                if (
                    target is not None
                    and actor["next_attack"] <= time + EPSILON
                    and target_distance(center(actor), target)
                    <= actor["range"] + EPSILON
                ):
                    support.launch(actor, target, time, trace)
                    actor["next_attack"] = time + actor[
                        "attack_interval_seconds"
                    ] / attack_rate(actor)
                continue
            if wall_routing is not None:
                wall_routing.wall_hit(actor, actors, time, damage, trace)
                if wall_routing.main_weapon_blocked(actor):
                    continue
            if target is None or actor["next_attack"] > time + EPSILON:
                continue
            if valkyries is not None and not valkyries.attack_ready(actor):
                continue
            if target_distance(center(actor), target) > actor["range"] + EPSILON:
                continue
            if combat is not None:
                if actor["id"] in geared_cannons.models:
                    geared_cannons.launch(actor, target, actors, time, trace)
                    continue
                if multi_gear is not None and actor["id"] in multi_gear.models:
                    multi_gear.launch(actor, target, actors, time, trace)
                    continue
                if sieges is not None and actor["id"] in sieges.models:
                    sieges.launch(actor, target, actors, time, trace)
                    continue
                if firespitters is not None and actor["id"] in firespitters.models:
                    firespitters.launch(actor, target, actors, time, trace)
                    continue
                if indirect is not None and actor["id"] in indirect.models:
                    indirect.launch(actor, target, actors, time, trace)
                    continue
                if actor["id"] in troop_lines.models:
                    troop_lines.launch(actor, target, time, trace)
                elif ramp is not None and actor["id"] in ramp.models:
                    flat_damage, weapon_state = ramp.launch_damage(actor["id"])
                    combat.launch(
                        actor, target, actors, time, trace, flat_damage, weapon_state
                    )
                else:
                    combat.launch(actor, target, actors, time, trace)
                    recipe_troops.launched(actor["id"], time, trace)
                    if actor["id"] in troop_behaviors.models:
                        troop_behaviors.on_launch(actor["id"], time, trace)
                    if heroes is not None:
                        heroes.weapon_launched(actor["id"], time, trace)
            elif target["immune_until"] <= time + EPSILON:
                damage[target["id"]] += actor["damage"]
            actor["next_attack"] = time + actor[
                "attack_interval_seconds"
            ] / attack_rate(actor)
            if hero_roster is not None and actor["id"] in heroes.models:
                # Opening-launch boosts end after the captured packet and its
                # attack work have been established, so the remaining work can
                # be rescaled exactly once by the normal preparation path.
                heroes.prepare(actors, time, trace)
            if combat is None:
                trace.append(
                    {
                        "time_seconds": time,
                        "source": actor["id"],
                        "target": target["id"],
                        "damage": actor["damage"],
                        "protected": target["immune_until"] > time + EPSILON,
                    }
                )
        for target_id, amount in crafted.resolve(time, trace).items():
            damage[target_id] += amount
        if crafted.models and town_halls is not None:
            town_halls.hazards.prepare_status(actors, time, trace)
            for target_id, amount in town_halls.hazards.resolve(
                actors, time, trace
            ).items():
                damage[target_id] += amount
        for target_id, amount in troop_lines.resolve(time, trace).items():
            damage[target_id] += amount
        if combat is not None:
            impact_callback = artillery.impact if artillery is not None else None
            for target_id, amount in combat.resolve(
                actors,
                time,
                trace,
                impact_callback,
                (
                    pet_status_impact
                    if hit_status is not None or pets is not None
                    else None
                ),
            ).items():
                damage[target_id] += amount
        if firespitters is not None:
            for target_id, amount in firespitters.resolve(actors, time, trace).items():
                damage[target_id] += amount
        if sieges is not None:
            for target_id, amount in sieges.resolve(actors, time, trace).items():
                damage[target_id] += amount
        healing = (
            support.resolve(actors, time, trace) if support else defaultdict(float)
        )
        if defending_heroes is not None:
            for actor_id, amount in defending_heroes.resolve_healing(
                actors, time, trace
            ).items():
                healing[actor_id] += amount
        if heroes is not None:
            extra_damage, extra_healing = heroes.resolve_passives(actors, time, trace)
            for target_id, amount in extra_damage.items():
                damage[target_id] += amount
            for target_id, amount in extra_healing.items():
                healing[target_id] += amount
        if builders is not None:
            for target_id, amount in builders.resolve(
                actors, time, trace, pending_damage=damage
            ).items():
                healing[target_id] += amount
        if pets is not None:
            for target_id, amount in pets.resolve_healing(actors, time, trace).items():
                healing[target_id] += amount
        for target_id, amount in recipe_troops.resolve(time, trace).items():
            damage[target_id] += amount
        for target_id, amount in titans.resolve(time, trace).items():
            damage[target_id] += amount
        apply_health(actors, damage, healing, time)
        if hit_status is not None:
            hit_status.prepare(actors, time, trace)
        if artillery is not None:
            apply_health(
                actors, artillery.resolve(actors, time, trace), defaultdict(float), time
            )
        settle_lifecycles(time, trace, allow_release=False)
        if reinforcements is not None and (
            reinforcements.release_ready(time)
            or (
                sieges is not None
                and getattr(sieges, "release_ready", lambda _: False)(time)
            )
        ):
            revisit_time = True
            continue
        if indirect is not None:
            indirect.prepare(actors, time, trace)
        if teslas is not None:
            revealed_before = {
                key
                for key, state in teslas.states.items()
                if state["revealed_at"] is not None
            }
            teslas.prepare(actors, time, trace)
            revealed_after = {
                key
                for key, state in teslas.states.items()
                if state["revealed_at"] is not None
            }
            if revealed_after - revealed_before:
                # A destruction threshold can reveal a ready weapon during the
                # health phase. Settle that new eligibility at the same timestamp
                # without repeating controller observations or external commands.
                revisit_time = True
                continue
        if sweepers is not None:
            sweepers.advance(actors, time, 0, trace)
        if tornado_traps is not None:
            tornado_traps.prepare(actors, time, trace)
        if garrisons is not None:
            garrisons.prepare(actors, time, trace, allow_release=False)
        if guardians is not None:
            guardians.prepare(actors, time, trace, allow_emergence=False)
            if guardians.emergence_ready(time):
                revisit_time = True
                continue
        if firespitters is not None:
            firespitters.prepare(actors, time, trace)
        if multi_gear is not None:
            multi_gear.prepare(actors, time, trace)
        if defending_heroes is not None:
            defending_heroes.prepare(actors, time, trace)
        if builders is not None:
            # Newly injured structures become eligible at this timestamp, and
            # a destroyed source retires its worker before recording or travel.
            builders.prepare(actors, time, trace)
        if pets is not None:
            pets.prepare(actors, time, trace)
        recipe_troops.prepare(time, trace)
        terminal = None
        if termination is not None:
            if damage_receipts is not None:
                damage_receipts.assert_settled()
            facts = []
            if termination.requires_runtime_facts:
                facts = runtime_continuation_reasons(
                    time,
                    actors,
                    patterns=combat,
                    deaths=deaths,
                    siege=sieges,
                    reinforcements=reinforcements,
                    pets=pets,
                    hazards=town_halls.hazards if town_halls is not None else None,
                    hero_providers=(
                        hero_roster,
                        recipe_troops,
                        troop_death_buffs,
                        troop_lines,
                        crafted,
                    ),
                    attack_spells=attack_spells,
                    damage_receipts=damage_receipts,
                )
            terminal = termination.evaluate(time, actors, facts, settled=True)
        if (
            terminal is not None
            or time >= next_recording - EPSILON
            or time >= duration - deadline_tolerance
        ):
            frames.append(
                {
                    "time_seconds": time,
                    "actors": {
                        key: {
                            "x": actor["x"],
                            "y": actor["y"],
                            "hp": actor["hp"],
                            "maximum_hp": actor["maximum_hp"],
                            "active": _active(actor, time),
                            "target": actor["target"],
                            **(
                                {
                                    "frozen_until": actor["frozen_until"],
                                    "attack_rate_multiplier": attack_rate(actor),
                                }
                                if hit_status is not None
                                else {}
                            ),
                            **(
                                {"healing_target": actor.get("healing_target")}
                                if support is not None
                                else {}
                            ),
                            **(ramp.frame(key) if ramp is not None else {}),
                            **(teslas.frame(actor) if teslas is not None else {}),
                            **(garrisons.frame(actor) if garrisons is not None else {}),
                            **(guardians.frame(actor) if guardians is not None else {}),
                            **(sieges.frame(actor) if sieges is not None else {}),
                            **(
                                reinforcements.frame(actor)
                                if reinforcements is not None
                                else {}
                            ),
                            **(
                                tornado_traps.frame(actor, time)
                                if tornado_traps is not None
                                else {}
                            ),
                            **(
                                firespitters.frame(actor)
                                if firespitters is not None
                                else {}
                            ),
                            **(
                                multi_gear.frame(actor)
                                if multi_gear is not None
                                else {}
                            ),
                            **(buffs.frame(actor) if buffs is not None else {}),
                            **(
                                attack_spells.frame(actor)
                                if attack_spells is not None
                                else {}
                            ),
                            **(
                                builders.frame(actor, time)
                                if builders is not None
                                else {}
                            ),
                            **(
                                spell_towers.frame(actor)
                                if spell_towers is not None
                                else {}
                            ),
                            **(indirect.frame(actor) if indirect is not None else {}),
                            **(
                                defending_heroes.frame(actor)
                                if defending_heroes is not None
                                else {}
                            ),
                            **(
                                sweepers.frame(actor, time)
                                if sweepers is not None
                                else {}
                            ),
                            **(valkyries.frame(actor) if valkyries is not None else {}),
                            **(heroes.frame(key, actor) if heroes is not None else {}),
                            **(
                                hero_roster.frame(key, actor)
                                if hero_roster is not None
                                else {}
                            ),
                            **(pets.frame(actor, time) if pets is not None else {}),
                            **(
                                artillery.frame(actor, time)
                                if artillery is not None
                                else {}
                            ),
                            **(
                                town_halls.frame(actor)
                                if town_halls is not None
                                else {}
                            ),
                        }
                        for key, actor in actors.items()
                    },
                }
            )
            while next_recording <= time + EPSILON:
                next_recording += recording
        if terminal is not None or time >= duration - deadline_tolerance:
            break
        boundaries = [duration, time + step, next_recording]
        recipe_boundary = recipe_troops.next_boundary(time)
        if recipe_boundary is not None:
            boundaries.append(recipe_boundary)
        titan_boundary = titans.next_boundary(time)
        if titan_boundary is not None:
            boundaries.append(titan_boundary)
        if effect_index < len(effects):
            boundaries.append(effects[effect_index]["time_seconds"])
        if controller is not None:
            boundaries.append(controller.next_boundary())
        if combat is not None and combat.next_boundary() is not None:
            boundaries.append(combat.next_boundary())
        if support is not None and support.next_boundary() is not None:
            boundaries.append(support.next_boundary())
        if ramp is not None and ramp.next_boundary(time) is not None:
            boundaries.append(ramp.next_boundary(time))
        if deaths is not None and deaths.next_boundary() is not None:
            boundaries.append(deaths.next_boundary())
        if town_halls is not None and town_halls.next_boundary(time) is not None:
            boundaries.append(town_halls.next_boundary(time))
        if heroes is not None and heroes.next_boundary(time) is not None:
            boundaries.append(heroes.next_boundary(time))
        if hero_roster is not None:
            hero_boundary = hero_roster.next_boundary(time)
            if hero_boundary is not None:
                boundaries.append(hero_boundary)
        if pets is not None and pets.next_boundary(time) is not None:
            boundaries.append(pets.next_boundary(time))
        if artillery is not None and artillery.next_boundary(time) is not None:
            boundaries.append(artillery.next_boundary(time))
        if traps is not None and traps.next_boundary(time) is not None:
            boundaries.append(traps.next_boundary(time))
        for trap_runtime in (skeleton_traps, tornado_traps, giga_bombs):
            if trap_runtime is not None:
                trap_boundary = trap_runtime.next_boundary(time)
                if trap_boundary is not None:
                    boundaries.append(trap_boundary)
        if hit_status is not None and hit_status.next_boundary() is not None:
            boundaries.append(hit_status.next_boundary())
        if teslas is not None and teslas.next_boundary(time) is not None:
            boundaries.append(teslas.next_boundary(time))
        if buffs is not None and buffs.next_boundary(time) is not None:
            boundaries.append(buffs.next_boundary(time))
        if attack_spells is not None:
            spell_boundary = attack_spells.next_boundary(time)
            if spell_boundary is not None:
                boundaries.append(spell_boundary)
        if spell_towers is not None and spell_towers.next_boundary(time) is not None:
            boundaries.append(spell_towers.next_boundary(time))
        if builders is not None and builders.next_boundary(time) is not None:
            boundaries.append(builders.next_boundary(time))
        if garrisons is not None and garrisons.next_boundary(time) is not None:
            boundaries.append(garrisons.next_boundary(time))
        if guardians is not None and guardians.next_boundary(time) is not None:
            boundaries.append(guardians.next_boundary(time))
        if sieges is not None and sieges.next_boundary(time) is not None:
            boundaries.append(sieges.next_boundary(time))
        if firespitters is not None and firespitters.next_boundary(time) is not None:
            boundaries.append(firespitters.next_boundary(time))
        if sweepers is not None and sweepers.next_boundary(time) is not None:
            boundaries.append(sweepers.next_boundary(time))
        if (
            defending_heroes is not None
            and defending_heroes.next_boundary(time) is not None
        ):
            boundaries.append(defending_heroes.next_boundary(time))
        if heroes is not None:
            heroes.prepare(actors, time, trace)
        for actor in actors.values():
            boundaries.extend(
                value
                for value in (
                    actor["spawn_seconds"],
                    actor["frozen_until"],
                    actor["next_attack"],
                    actor.get("_wall_next_attack"),
                )
                if isinstance(value, (int, float)) and value > time + EPSILON
            )
        next_time = min(value for value in boundaries if value > time + EPSILON)
        if controller is not None and getattr(controller, "paid_observation", False):
            control_boundary = controller.next_boundary()
            if time < control_boundary < next_time:
                next_time = control_boundary
        if hit_status is not None:
            status_boundary = hit_status.next_boundary()
            if status_boundary is not None and time < status_boundary < next_time:
                next_time = status_boundary
        mirror_boundary = heroes.mirror_boundary(time) if heroes is not None else None
        if mirror_boundary is not None and time < mirror_boundary < next_time:
            next_time = mirror_boundary
        crafted_boundary = crafted.next_boundary(time)
        if crafted_boundary is not None and time < crafted_boundary < next_time:
            next_time = crafted_boundary
        line_boundary = troop_lines.next_boundary(time)
        if line_boundary is not None and time < line_boundary < next_time:
            next_time = line_boundary
        if troop_death_buffs is not None:
            death_buff_boundary = troop_death_buffs.next_boundary(time)
            if (
                death_buff_boundary is not None
                and time < death_buff_boundary < next_time
            ):
                next_time = death_buff_boundary
        if attack_spells is not None:
            exact_spell_boundary = attack_spells.next_boundary(time)
            if (
                exact_spell_boundary is not None
                and time < exact_spell_boundary < next_time
            ):
                next_time = exact_spell_boundary
        if titan_boundary is not None and time < titan_boundary < next_time:
            next_time = titan_boundary
        # Instantaneous tower pulses retain every representable future arrival.
        # Their clock is a time, not the spatial membership tolerance.
        if spell_towers is not None:
            tower_boundary = spell_towers.next_boundary(time)
            if tower_boundary is not None and time < tower_boundary < next_time:
                next_time = tower_boundary
        if sieges is not None:
            siege_boundary = sieges.next_boundary(time)
            if siege_boundary is not None and time < siege_boundary < next_time:
                next_time = siege_boundary
        blocked = _blocked(actors, time)
        routes = {}
        motions = {}
        forced_actors = set()
        for actor in actors.values():
            if not _active(actor, time) or actor["movement"] == "stationary":
                continue
            forced = (
                tornado_traps.forced_motion(actor, time)
                if tornado_traps is not None
                else None
            )
            if forced is None and sweepers is not None:
                forced = sweepers.forced_motion(actor, time)
            if forced is not None:
                forced_actors.add(actor["id"])
                route = forced["route"]
                speed = forced["speed_tiles_per_second"]
            else:
                if (
                    actor.get("_spell_pause_until", 0) > time
                    or actor["frozen_until"] > time + EPSILON
                    or (sweepers is not None and sweepers.attack_locked(actor, time))
                ):
                    continue
                _, route = select_target(actor, actors, time, blocked, width, height)
                speed = movement_speed(actor)
            if route is not None:
                motions[actor["id"]] = (route, speed if route else 0)
                if forced is None:
                    routes[actor["id"]] = route
        original_motions = dict(motions)
        _air_contact_motions(actors, motions, time, width, height, forced_actors)
        if hero_roster is not None:
            contacts = hero_roster.duke.resolve_contact_motions(
                actors,
                motions,
                time,
                width,
                height,
                forced_actors,
                trace,
                original_motions,
            )
            if contacts:
                # Duke contact depends only on unchanged direct proposals or
                # an ally following a ground target. Re-resolve other airborne
                # followers from their original proposals so they see the
                # Duke's final velocity. Ground proposals remain unchanged.
                motions = {
                    **original_motions,
                    **{key: motions[key] for key in contacts},
                }
                _air_contact_motions(
                    actors, motions, time, width, height, forced_actors
                )
        for actor_id, (route, speed) in motions.items():
            actor = actors[actor_id]
            if actor_id not in forced_actors:
                routes[actor_id] = route
                if route and speed > EPSILON:
                    arrival_delay = _route_length(actor, route) / speed
                    # Range tolerance is a distance, not a duration. A fast
                    # pursuer can still be outside inclusive weapon range
                    # when its remaining arrival time is below EPSILON.
                    # Keep every representable positive arrival so a moving
                    # primary cannot repeatedly reopen that tiny gap.
                    if time + arrival_delay > time:
                        next_time = min(next_time, time + arrival_delay)
            if traps is not None:
                crossing = traps.first_crossing_delay(
                    actor, route, time, next_time - time, speed
                )
                if crossing is not None:
                    next_time = min(next_time, time + crossing)
            for trap_runtime in (skeleton_traps, tornado_traps, giga_bombs):
                if trap_runtime is not None:
                    crossing = trap_runtime.first_crossing_delay(
                        actor, route, time, next_time - time, speed
                    )
                    if crossing is not None:
                        next_time = min(next_time, time + crossing)
            if teslas is not None:
                crossing = teslas.first_crossing_delay(
                    actor, route, time, next_time - time, speed
                )
                if crossing is not None:
                    next_time = min(next_time, time + crossing)
            if buffs is not None:
                crossing = buffs.first_crossing_delay(
                    actor,
                    route,
                    time,
                    next_time - time,
                    speed,
                    forced_motion=actor_id in forced_actors,
                )
                if crossing is not None:
                    next_time = min(next_time, time + crossing)
            if sweepers is not None:
                crossing = sweepers.first_crossing_delay(
                    actor, route, time, next_time - time, speed
                )
                if crossing is not None:
                    next_time = min(next_time, time + crossing)
            if spell_towers is not None:
                crossing = spell_towers.first_crossing_delay(
                    actor, route, time, next_time - time, speed
                )
                if crossing is not None:
                    next_time = min(next_time, time + crossing)
            if attack_spells is not None:
                crossing = attack_spells.first_crossing_delay(
                    actor, route, time, next_time - time, speed
                )
                if crossing is not None:
                    next_time = min(next_time, time + crossing)
            if defending_heroes is not None:
                crossing = defending_heroes.first_crossing_delay(
                    actor,
                    route,
                    time,
                    next_time - time,
                    speed,
                    forced_motion=actor_id in forced_actors,
                )
                if crossing is not None:
                    next_time = min(next_time, time + crossing)
            if garrisons is not None:
                crossing = garrisons.first_crossing_delay(
                    actor,
                    route,
                    time,
                    next_time - time,
                    speed,
                    forced_motion=actor_id in forced_actors,
                )
                if crossing is not None:
                    next_time = min(next_time, time + crossing)
            if firespitters is not None:
                crossing = firespitters.first_crossing_delay(
                    actor, route, time, next_time - time, speed
                )
                if crossing is not None:
                    next_time = min(next_time, time + crossing)
            if guardians is not None:
                crossing = guardians.first_crossing_delay(
                    actor,
                    route,
                    time,
                    next_time - time,
                    speed,
                    forced_motion=actor_id in forced_actors,
                )
                if crossing is not None:
                    next_time = min(next_time, time + crossing)
            if sieges is not None:
                crossing = sieges.first_crossing_delay(
                    actor,
                    route,
                    time,
                    next_time - time,
                    speed,
                    forced_motion=actor_id in forced_actors,
                )
                if crossing is not None:
                    next_time = min(next_time, time + crossing)
        # The selectors above can update retained targets and route caches.
        # Use their completed trajectories here rather than selecting again.
        excluded_range_sources = set()
        for runtime in (support, sweepers, spell_towers, firespitters, sieges):
            if runtime is not None:
                excluded_range_sources.update(runtime.models)
        if town_halls is not None:
            excluded_range_sources.update(
                actor_id
                for actor_id, state in town_halls.states.items()
                if state["activated_at"] is None
            )
        if indirect is not None:
            excluded_range_sources.update(
                actor_id
                for actor_id, state in indirect.states.items()
                if not state["activated"]
            )
        next_time = _weapon_range_boundary(
            actors, motions, time, next_time, excluded_range_sources
        )
        if support is not None:
            crossing = support.first_crossing_delay(
                actors, motions, time, next_time - time
            )
            if crossing is not None:
                next_time = min(next_time, time + crossing)
        if heroes is not None:
            crossing = heroes.first_crossing_delay(
                actors,
                {key: route for key, (route, _) in motions.items()},
                {key: speed for key, (_, speed) in motions.items()},
                time,
                next_time - time,
            )
            if crossing is not None:
                next_time = min(next_time, time + crossing)
        if hero_roster is not None:
            crossing = hero_roster.first_crossing_delay(
                actors, motions, time, next_time - time
            )
            if crossing is not None:
                next_time = min(next_time, time + crossing)
        if pets is not None:
            for pet_id, model in pets.models.items():
                if model["entity"] != "unicorn":
                    continue
                actor = actors[pet_id]
                target = pets.range_target(actor, time)
                if target is None:
                    continue
                route, speed = motions.get(pet_id, ((), 0))
                target_route, target_speed = motions.get(target["id"], ((), 0))
                crossing = pets.first_crossing_delay(
                    actor,
                    route,
                    time,
                    next_time - time,
                    speed,
                    target_route,
                    target_speed,
                )
                if crossing is not None:
                    next_time = min(next_time, time + crossing)
        positions = {
            actor_id: _move(
                actors[actor_id], route, next_time - time, speed=motions[actor_id][1]
            )
            for actor_id, route in routes.items()
        }
        for actor_id, ((x, y), remaining_path) in positions.items():
            actors[actor_id]["x"] = x
            actors[actor_id]["y"] = y
            if actors[actor_id]["movement"] == "ground":
                actors[actor_id]["_remaining_path"] = remaining_path
        if sweepers is not None:
            sweepers.advance(actors, time, next_time - time, trace)
        if tornado_traps is not None:
            tornado_traps.advance(actors, time, next_time - time, trace)
        if builders is not None:
            builders.advance(actors, time, next_time - time, trace)
        if pets is not None:
            pets.advance(actors, time, next_time - time, trace)
        time = next_time
    if damage_receipts is not None:
        damage_receipts.assert_settled()
    return {
        "id": require(specification, "id"),
        "status": "SPATIAL_KERNEL_EXPERIMENT_NOT_VALIDATED_CLASH_BATTLE",
        "air_contact_policy": AIR_CONTACT_POLICY,
        "ruleset": ruleset,
        **({"termination": termination.result()} if termination is not None else {}),
        "combat": combat.result() if combat is not None else None,
        **({"recipe_troops": recipe_troops.result()} if recipe_troops.models else {}),
        **(
            {"troop_behaviors": troop_behaviors.result()}
            if troop_behaviors.models
            else {}
        ),
        "support": support.result() if support is not None else None,
        "weapon_ramps": ramp.result() if ramp is not None else None,
        "death_effects": deaths.result() if deaths is not None else None,
        "town_halls_and_hazards": (
            town_halls.result() if town_halls is not None else None
        ),
        "target_scoring": deepcopy(specification.get("target_scoring")),
        **({"hero_abilities": heroes.result()} if heroes is not None else {}),
        **(
            {"extended_heroes": hero_roster.result()} if hero_roster is not None else {}
        ),
        **({"hero_pets": pets.result()} if pets is not None else {}),
        **({"artillery_flames": artillery.result()} if artillery is not None else {}),
        **({"traps": traps.result()} if traps is not None else {}),
        **(
            {"skeleton_traps": skeleton_traps.result()}
            if skeleton_traps is not None
            else {}
        ),
        **(
            {"tornado_traps": tornado_traps.result()}
            if tornado_traps is not None
            else {}
        ),
        **({"hit_statuses": hit_status.result()} if hit_status is not None else {}),
        **({"teslas": teslas.result()} if teslas is not None else {}),
        **({"buffs": buffs.result()} if buffs is not None else {}),
        **(
            {"attack_spells": attack_spells.result()}
            if attack_spells is not None
            else {}
        ),
        **({"spell_towers": spell_towers.result()} if spell_towers is not None else {}),
        **(
            {"geared_cannons": geared_cannons.result()} if geared_cannons.models else {}
        ),
        **({"builders": builders.result()} if builders is not None else {}),
        **({"garrisons": garrisons.result()} if garrisons is not None else {}),
        **({"electro_titans": titans.result()} if titans.models else {}),
        **({"troop_lines": troop_lines.result()} if troop_lines.models else {}),
        **({"crafted_defenses": crafted.result()} if crafted.models else {}),
        **(
            {"troop_death_buffs": troop_death_buffs.result()}
            if troop_death_buffs is not None and troop_death_buffs.models
            else {}
        ),
        **({"guardians": guardians.result()} if guardians is not None else {}),
        **({"sieges": sieges.result()} if sieges is not None else {}),
        **({"firespitters": firespitters.result()} if firespitters is not None else {}),
        **({"multi_gear": multi_gear.result()} if multi_gear is not None else {}),
        **({"giga_bombs": giga_bombs.result()} if giga_bombs is not None else {}),
        **({"indirect_defenses": indirect.result()} if indirect is not None else {}),
        **({"sweepers": sweepers.result()} if sweepers is not None else {}),
        **(
            {"defending_heroes": defending_heroes.result()}
            if defending_heroes is not None
            else {}
        ),
        "actors": {
            key: {
                field: value
                for field, value in actor.items()
                if not field.startswith("_")
            }
            for key, actor in actors.items()
        },
        "trace": trace,
        "frames": frames,
        "full_game_prediction": False,
        "limitations": [
            "Range entry and movement feedback are resolved at the declared solver boundaries; run resolution sensitivity checks",
            "Four-neighbor routing and target retention are declared conventions, not verified Clash AI",
            "No generic replacement for complete hero/equipment/pet behaviors, summons, traps, or guardians; wall behavior requires its own explicit conditional ruleset",
            "Projectile destinations, area geometry, chain ties and volley allocation are declared experiment conventions; actual Clash adapters remain unverified",
            "A complete game adapter and held-out replay calibration are still required",
        ],
    }
