"""Conditional Valkyrie placement and source-centered whirlwind geometry.

The catalog supplies HP, movement, range, and hit statistics through the ordinary
troop compiler. It does not establish splash radius, placement search resolution,
or willingness to detour. These remain explicit hypotheses. Buildings keep their
real blocking footprints; the troop remains a point under the shared kernel.
"""

from copy import deepcopy
from math import ceil, floor, hypot

from .combat import footprint_distance
from .common import InputError, identifier, integer, number, require
from .hit_status import RULES as HIT_RULES
from .rates import attack_rate, movement_speed
from .buffs import damage_multiplier
from .spatial import (
    EPSILON,
    _active,
    _eligible,
    _ground_route,
    _route_length,
    center,
    target_distance,
)
from .walls import WallRouting


RULESET = "spatial-valkyrie-placement-kernel-v13"
SCOPE = "valkyrie_hit_status_traps_heroes_sector_without_pets_or_defending_troops"
RULES = {
    **HIT_RULES,
    "valkyrie_primary": "retain_the_shared_selector_primary",
    "valkyrie_placement": "sample_reachable_points_within_primary_range",
    "valkyrie_pair_membership": "eligible_stationary_buildings_within_declared_footprint_gap",
    "valkyrie_placement_score": "most_buildings_then_smallest_pair_distance_imbalance_then_route_cost_then_xy",
    "valkyrie_detour": "declared_extra_route_seconds_over_ordinary_primary_approach",
    "valkyrie_retention": "retain_placement_until_primary_neighbor_geometry_or_blocking_cells_change",
    "valkyrie_swing": "instant_source_center_at_launch_with_footprint_distance",
    "valkyrie_walls": "shared_wall_routing_and_single_obstruction_weapon",
}
PARAMETER_FIELDS = {
    "source",
    "neighbor_gap_tiles",
    "samples_per_tile",
    "maximum_extra_travel_seconds",
}
MODEL_KIND = "sampled_reachable_building_pairs"
BUILDING_KINDS = {"building", "defense"}


def _validate_parameters(parameters):
    if not isinstance(parameters, dict) or set(parameters) != PARAMETER_FIELDS:
        raise InputError("Valkyrie placement needs its complete explicit parameters")
    identifier(parameters["source"], "Valkyrie placement evidence")
    number(parameters["neighbor_gap_tiles"], "Valkyrie neighboring footprint gap", 0)
    integer(parameters["samples_per_tile"], "Valkyrie samples per tile", 1, 8)
    number(parameters["maximum_extra_travel_seconds"], "Valkyrie extra route time", 0)


def validate_source_radial(pattern):
    """Additional pattern validation; the shared validator checks other fields."""
    if pattern.get("kind") != "source_radial":
        raise InputError("Source-centered attacks need the source_radial pattern")
    number(require(pattern, "radius"), "source-centered splash radius", EPSILON)
    projectile = require(pattern, "projectile")
    if (
        projectile.get("timing") != "instant"
        or projectile.get("delay_seconds") != 0
        or projectile.get("destination") != "fixed_source_center_at_launch"
        or projectile.get("inactive_primary_policy")
        != "resolve_at_fixed_launch_position"
    ):
        raise InputError("A source-centered swing must resolve instantly at its source")


def compile_valkyrie(actor, instance):
    """Attach placement after catalog stats and an explicit radial pattern exist.

    The adapter registry should admit Valkyrie as a ground/radial troop, then call
    this compiler. Radius is already required in ordinary attack_parameters and
    is never guessed from the catalog's melee acquisition range.
    """
    parameters = require(instance, "valkyrie_parameters")
    _validate_parameters(parameters)
    if instance.get("entity") != "valkyrie":
        raise InputError("Valkyrie placement parameters require a Valkyrie instance")
    if actor.get("movement") != "ground" or actor.get("kind") != "unit":
        raise InputError("Valkyrie placement requires a ground troop")
    pattern = deepcopy(require(actor, "attack_model"))
    if pattern.get("kind") != "radial":
        raise InputError("Compile Valkyrie from an explicitly parameterized radial hit")
    if (
        number(require(pattern, "radius"), "Valkyrie splash radius", EPSILON)
        < actor["range"]
    ):
        raise InputError("Valkyrie splash radius cannot omit an in-range primary")
    projectile = require(pattern, "projectile")
    if projectile.get("timing") != "instant" or projectile.get("delay_seconds") != 0:
        raise InputError("Delayed Valkyrie swings need a separate timing model")
    pattern["kind"] = "source_radial"
    pattern["projectile"]["destination"] = "fixed_source_center_at_launch"
    pattern["projectile"][
        "inactive_primary_policy"
    ] = "resolve_at_fixed_launch_position"
    validate_source_radial(pattern)
    actor["attack_model"] = pattern
    actor["valkyrie_model"] = {"kind": MODEL_KIND, **deepcopy(parameters)}
    actor["entity_adapter"]["valkyrie_parameters"] = deepcopy(parameters)


def source_radial_impacts(packet, actors, time, damage_eligible):
    """Return whirlwind hits around the saved source, never around the primary.

    Shared PatternCombat still applies simultaneous damage, protection, and
    impact callbacks. Capturing launch_position makes the packet independent of
    later source movement or death and of the primary's continuing existence.
    """
    point = packet["launch_position"]
    radius = packet["pattern"]["radius"]
    return [
        (actor, 1)
        for actor in actors.values()
        if damage_eligible(packet, actor, time)
        and target_distance(point, actor) <= radius + EPSILON
    ]


def _building(actor):
    return actor["kind"] in BUILDING_KINDS and actor["movement"] == "stationary"


def _point_target(point, primary):
    return {**primary, "x": point[0], "y": point[1], "width": 0, "height": 0}


def _route_to(actor, target, actors, time, blocked, width, height, exact=False):
    """Reuse shared route geometry and wall costs without changing the actor."""
    mover = dict(actor)
    mover["_terminal_ground_approach"] = True
    if exact:
        mover["range"] = 0
    if target_distance(center(mover), target) <= mover["range"] + EPSILON:
        return [], 0, None
    profile = mover["wall_behavior"]
    if profile["kind"] == "avoid":
        route = _ground_route(mover, target, blocked, width, height)
        if route is None:
            return None, None, None
        return route, _route_length(mover, route) / movement_speed(mover), None
    walls, solid = WallRouting._maps(mover, actors, time, blocked)
    route, cost = WallRouting._virtual_route(mover, target, walls, solid, width, height)
    if route is None:
        return None, None, None
    obstruction = WallRouting._obstruction(mover, route, walls)
    if obstruction is not None:
        route = WallRouting._approach(mover, route, obstruction)
    return route, cost, obstruction


def _remaining_route(plan, position):
    """Consume an observed movement along a cached route without grid recentering."""
    previous = plan["route_origin"]
    route = plan["route"]
    if hypot(position[0] - previous[0], position[1] - previous[1]) <= EPSILON:
        return list(route)
    for index, point in enumerate(route):
        segment = hypot(point[0] - previous[0], point[1] - previous[1])
        travelled = hypot(position[0] - previous[0], position[1] - previous[1])
        remaining = hypot(point[0] - position[0], point[1] - position[1])
        if abs(travelled + remaining - segment) <= EPSILON:
            return list(route[index + 1 :] if remaining <= EPSILON else route[index:])
        previous = point
    return None


class ValkyrieRouting:
    """Wrap a selector while retaining its primary targeting and wall semantics.

    Integration must call attack_ready after select_target and before launching
    a main-weapon hit. Otherwise a troop already in melee range can swing before
    reaching its deliberately chosen between-building position.
    """

    def __init__(self, actors, select_target):
        self.ordinary_select_target = select_target
        self.models = {}
        self.plans = {}
        for actor in actors.values():
            if "valkyrie_model" not in actor:
                continue
            model = actor["valkyrie_model"]
            if not isinstance(model, dict) or set(model) != PARAMETER_FIELDS | {"kind"}:
                raise InputError(
                    "Valkyrie model must declare its complete placement rule"
                )
            if model["kind"] != MODEL_KIND:
                raise InputError("Unsupported Valkyrie placement rule")
            _validate_parameters({key: model[key] for key in PARAMETER_FIELDS})
            if (
                actor["kind"] != "unit"
                or actor["movement"] != "ground"
                or actor["wall_behavior"]["kind"] not in {"avoid", "clear_obstructions"}
            ):
                raise InputError(
                    "Valkyries require ordinary ground/wall-clearing motion"
                )
            validate_source_radial(actor["attack_model"])
            if actor["attack_model"]["radius"] < actor["range"]:
                raise InputError(
                    "Valkyrie splash must include the primary attack range"
                )
            self.models[actor["id"]] = deepcopy(model)

    def _neighbors(self, actor, primary, actors, time):
        gap = self.models[actor["id"]]["neighbor_gap_tiles"]
        return sorted(
            (
                target
                for target in actors.values()
                if target["id"] != primary["id"]
                and _building(target)
                and _eligible(actor, target, time)
                and footprint_distance(primary, target) <= gap + EPSILON
            ),
            key=lambda target: target["id"],
        )

    @staticmethod
    def _signature(primary, neighbors, blocked):
        geometry = tuple(
            (
                item["id"],
                item["kind"],
                item["x"],
                item["y"],
                item["width"],
                item["height"],
            )
            for item in [primary, *neighbors]
        )
        return geometry, frozenset(blocked)

    @staticmethod
    def _route_state(actor, actors, time):
        if actor["wall_behavior"]["kind"] == "avoid":
            return None
        walls = tuple(
            sorted(
                (wall["id"], wall["hp"])
                for wall in actors.values()
                if wall["kind"] == "wall"
                and wall["team"] != actor["team"]
                and _active(wall, time)
            )
        )
        return (
            walls,
            movement_speed(actor),
            attack_rate(actor),
            damage_multiplier(actor),
        )

    def _candidates(self, actor, primary, neighbors, blocked, width, height):
        samples = self.models[actor["id"]]["samples_per_tile"]
        reach = actor["range"]
        radius = actor["attack_model"]["radius"]
        left = max(0, ceil((primary["x"] - reach) * samples))
        right = min(
            width * samples - 1,
            floor((primary["x"] + primary["width"] + reach) * samples),
        )
        bottom = max(0, ceil((primary["y"] - reach) * samples))
        top = min(
            height * samples - 1,
            floor((primary["y"] + primary["height"] + reach) * samples),
        )
        points = {center(actor)}
        points.update(
            (x / samples, y / samples)
            for x in range(left, right + 1)
            for y in range(bottom, top + 1)
        )
        for point in sorted(points):
            if not (0 <= point[0] < width and 0 <= point[1] < height):
                continue
            if (floor(point[0]), floor(point[1])) in blocked:
                continue
            primary_distance = target_distance(point, primary)
            if primary_distance > reach + EPSILON:
                continue
            hit = [
                target
                for target in neighbors
                if target_distance(point, target) <= radius + EPSILON
            ]
            if hit:
                imbalance = min(
                    abs(primary_distance - target_distance(point, target))
                    for target in hit
                )
                yield point, hit, imbalance

    def _choose_plan(
        self, actor, primary, neighbors, actors, time, blocked, width, height
    ):
        _, baseline_cost, _ = _route_to(
            actor, primary, actors, time, blocked, width, height
        )
        if baseline_cost is None:
            return None
        budget = self.models[actor["id"]]["maximum_extra_travel_seconds"]
        choices = []
        for point, hit, imbalance in self._candidates(
            actor, primary, neighbors, blocked, width, height
        ):
            route, cost, obstruction = _route_to(
                actor,
                _point_target(point, primary),
                actors,
                time,
                blocked,
                width,
                height,
                exact=True,
            )
            if route is None or cost > baseline_cost + budget + EPSILON:
                continue
            score = (-len(hit), round(imbalance, 10), cost, point)
            choices.append((score, point, route, obstruction, hit))
        if not choices:
            return None
        _, point, route, obstruction, hit = min(choices, key=lambda item: item[0])
        return {
            "point": point,
            "route": route,
            "route_origin": center(actor),
            "route_state": self._route_state(actor, actors, time),
            "obstruction": obstruction,
            "neighbors": [target["id"] for target in hit],
            "signature": self._signature(primary, neighbors, blocked),
        }

    def select_target(self, actor, actors, time, blocked, width, height):
        primary, ordinary_route = self.ordinary_select_target(
            actor, actors, time, blocked, width, height
        )
        if actor["id"] not in self.models:
            return primary, ordinary_route
        if primary is None or not _building(primary):
            self.plans.pop(actor["id"], None)
            return primary, ordinary_route
        neighbors = self._neighbors(actor, primary, actors, time)
        signature = self._signature(primary, neighbors, blocked)
        plan = self.plans.get(actor["id"])
        if plan is not None and plan["signature"] != signature:
            plan = None
        if plan is None and neighbors:
            plan = self._choose_plan(
                actor, primary, neighbors, actors, time, blocked, width, height
            )
        if plan is None:
            self.plans.pop(actor["id"], None)
            return primary, ordinary_route
        route = None
        route_state = self._route_state(actor, actors, time)
        if plan["route_state"] == route_state:
            route = _remaining_route(plan, center(actor))
        if route is None:
            route, _, obstruction = _route_to(
                actor,
                _point_target(plan["point"], primary),
                actors,
                time,
                blocked,
                width,
                height,
                exact=True,
            )
            plan["obstruction"] = obstruction
        if route is None:
            self.plans.pop(actor["id"], None)
            return primary, ordinary_route
        plan["route"] = list(route)
        plan["route_origin"] = center(actor)
        plan["route_state"] = route_state
        self.plans[actor["id"]] = plan
        # The movement phase stores its remaining route on the shared actor.
        # That route reaches our placement, not the ordinary cached endpoint.
        actor.pop("_path_signature", None)
        if actor["wall_behavior"]["kind"] == "clear_obstructions":
            obstruction = plan["obstruction"]
            actor["obstruction_target"] = (
                obstruction["id"] if obstruction is not None else None
            )
        return primary, list(route)

    def attack_ready(self, actor):
        plan = self.plans.get(actor["id"])
        if plan is None:
            return True
        point = plan["point"]
        position = center(actor)
        return hypot(point[0] - position[0], point[1] - position[1]) <= EPSILON

    def frame(self, actor):
        plan = self.plans.get(actor["id"])
        if plan is None:
            return {}
        return {
            "valkyrie_placement": {"x": plan["point"][0], "y": plan["point"][1]},
            "valkyrie_neighbors": list(plan["neighbors"]),
        }
