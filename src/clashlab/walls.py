"""Conditional wall routes and weapons sharing the sector's live actor state.

The two breach motion profiles are hypotheses to compare with recordings. They
are not assertions about the game's exact Root Rider movement or hit cadence.
"""

from functools import lru_cache
from heapq import heappop, heappush
from math import ceil, floor, hypot

from .combat import COMBAT_RULES
from .common import InputError, identifier, number, require
from .rates import attack_rate, movement_speed
from .buffs import damage_multiplier
from .spatial import (
    EPSILON,
    _active,
    _eligible,
    _select_target,
    center,
    ground_attack_point,
    ground_attack_points,
    target_distance,
    target_priority,
)


RULESET = "spatial-wall-breach-kernel-v3"
WALL_RULES = {
    **COMBAT_RULES,
    "ground_path": "declared_four_neighbor_routes_with_live_wall_state",
    "target_tie": "declared_route_cost_then_instance_id_within_priority",
    "wall_target": "first_enemy_wall_on_retained_primary_route",
    "wall_weapon": "explicit_instant_hits_in_the_simultaneous_damage_phase",
    "wall_motion": "per_actor_clear_before_crossing_or_penetrate_hypothesis",
    "wall_clearance_cost": "ceil_current_hp_over_hit_damage_times_hit_interval",
    "wall_replanning": "live_hp_and_destroyed_footprints_at_every_solver_boundary",
    "ground_terminal_approach": "nearest_attack_point_within_a_reachable_cell",
}
BREACH_KINDS = {"clear_obstructions", "penetrate_obstructions"}
ROUTE_COSTS = {"travel_seconds_only", "travel_seconds_plus_nominal_clearance"}
COOLDOWNS = {"shared_with_main_weapon", "independent_from_main_weapon"}


@lru_cache(maxsize=256)
def _weighted_route(
    position,
    footprint,
    attack_range,
    speed,
    wall_hit,
    wall_interval,
    current_attack_rate,
    wall_hps,
    solid,
    width,
    height,
):
    """Pure original Dijkstra query; every geometric and live cost input is keyed."""
    target = dict(zip(("x", "y", "width", "height"), footprint))
    walls = dict(wall_hps)
    start = floor(position[0]), floor(position[1])
    pending = [(0.0, start)]
    costs = {start: 0.0}
    previous = {start: None}
    destination = None
    endpoint = None
    attack_points = ground_attack_points(target, attack_range, width, height)
    while pending:
        cost, cell = heappop(pending)
        if cost > costs[cell] + EPSILON:
            continue
        # A planned destination may occupy a wall cell: clearing makes it
        # traversable before arrival. _approach prevents premature crossing.
        endpoint = (
            attack_points.get(cell)
            if attack_points is not None
            else ground_attack_point(cell, target, attack_range)
        )
        if endpoint is not None:
            destination = cell
            break
        x, y = cell
        for neighbor in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y)):
            nx, ny = neighbor
            if not (0 <= nx < width and 0 <= ny < height) or neighbor in solid:
                continue
            edge_cost = 1 / speed
            if cell == start:
                edge_cost = (
                    hypot(nx + 0.5 - position[0], ny + 0.5 - position[1]) / speed
                )
            if neighbor in walls:
                edge_cost += (
                    ceil(walls[neighbor] / wall_hit)
                    * wall_interval
                    / current_attack_rate
                )
            candidate = cost + edge_cost
            if candidate < costs.get(neighbor, float("inf")) - EPSILON:
                costs[neighbor] = candidate
                previous[neighbor] = cell
                heappush(pending, (candidate, neighbor))
    if destination is None:
        return None, None
    final_cost = costs[destination]
    cells = []
    while destination != start:
        cells.append(destination)
        destination = previous[destination]
    cells.reverse()
    route = [(x + 0.5, y + 0.5) for x, y in cells]
    if not route:
        final_cost += (
            hypot(endpoint[0] - position[0], endpoint[1] - position[1]) / speed
        )
        return (endpoint,), final_cost
    destination_center = route[-1]
    if endpoint != destination_center:
        route.append(endpoint)
        final_cost += (
            hypot(
                endpoint[0] - destination_center[0],
                endpoint[1] - destination_center[1],
            )
            / speed
        )
    return tuple(route), final_cost


class WallRouting:
    """Keep intended buildings separate from intervening wall weapon targets."""

    def __init__(self, actors):
        for actor in actors.values():
            if actor["kind"] == "wall":
                if (
                    actor["movement"] != "stationary"
                    or not actor["blocking"]
                    or actor["width"] != 1
                    or actor["height"] != 1
                    or actor["damage"] != 0
                    or actor["counts_for_destruction"]
                ):
                    raise InputError(
                        "Wall routing requires passive blocking one-tile walls outside destruction counts"
                    )
            if actor["movement"] != "ground":
                if "wall_behavior" in actor:
                    raise InputError("Only ground movers can select wall behavior")
                continue
            profile = require(actor, "wall_behavior")
            actor["_terminal_ground_approach"] = True
            kind = require(profile, "kind")
            identifier(require(profile, "source"), "wall behavior evidence")
            if kind == "avoid":
                if set(profile) != {"kind", "source"}:
                    raise InputError("Avoid-wall behavior cannot hide a wall weapon")
                continue
            if kind == "jump_enemy_walls":
                if set(profile) != {"kind", "source"}:
                    raise InputError("Wall jumping cannot hide a wall weapon")
                continue
            if kind not in BREACH_KINDS:
                raise InputError("Unsupported wall breach motion profile")
            if set(profile) != {"kind", "source", "route_cost", "weapon"}:
                raise InputError("Wall breach conventions must be fully explicit")
            if require(profile, "route_cost") not in ROUTE_COSTS:
                raise InputError("Unsupported wall route cost convention")
            if (
                actor["kind"] != "unit"
                or actor["damage"] <= 0
                or "wall" in actor["target_priorities"]
            ):
                raise InputError(
                    "Breach units need a separate non-wall primary weapon and target list"
                )
            weapon = require(profile, "weapon")
            if set(weapon) != {
                "damage",
                "range",
                "attack_interval_seconds",
                "first_attack_seconds",
                "timing",
                "cooldown",
                "source",
            }:
                raise InputError("Every wall weapon parameter must be explicit")
            identifier(require(weapon, "source"), "wall weapon evidence")
            number(require(weapon, "damage"), "wall hit damage", EPSILON)
            minimum_range = EPSILON if kind == "clear_obstructions" else 0
            number(require(weapon, "range"), "wall hit range", minimum_range)
            number(
                require(weapon, "attack_interval_seconds"), "wall hit interval", EPSILON
            )
            first = number(require(weapon, "first_attack_seconds"), "first wall hit", 0)
            if require(weapon, "timing") != "instant":
                raise InputError("Delayed wall impacts require another weapon adapter")
            if require(weapon, "cooldown") not in COOLDOWNS:
                raise InputError("Wall/main cooldown relationship must be explicit")
            if weapon["cooldown"] == "shared_with_main_weapon":
                if (
                    first != actor["next_attack"]
                    or weapon["attack_interval_seconds"]
                    != actor["attack_interval_seconds"]
                ):
                    raise InputError(
                        "Shared wall weapons must use the main weapon's initial clock and interval"
                    )
            if weapon["cooldown"] == "independent_from_main_weapon":
                actor["_wall_next_attack"] = first
            actor["obstruction_target"] = None

    @staticmethod
    def _maps(actor, actors, time, blocked):
        exempt = set(map(tuple, actor.get("_spell_jump_cells", [])))
        enemy_walls = {
            (wall["x"], wall["y"]): wall
            for wall in actors.values()
            if wall["kind"] == "wall"
            and wall["team"] != actor["team"]
            and _active(wall, time)
            and (wall["x"], wall["y"]) not in exempt
        }
        return enemy_walls, blocked - set(enemy_walls) - exempt

    def validate_positions(self, actors, blocked, time):
        for actor in actors.values():
            if not _active(actor, time) or actor["movement"] != "ground":
                continue
            cell = floor(actor["x"]), floor(actor["y"])
            if cell not in blocked:
                continue
            if cell in set(map(tuple, actor.get("_spell_jump_cells", []))):
                continue
            walls, solid = self._maps(actor, actors, time, blocked)
            profile = actor["wall_behavior"]
            if (
                profile["kind"] not in {"penetrate_obstructions", "jump_enemy_walls"}
                or cell in solid
                or cell not in walls
            ):
                raise InputError(
                    f"Ground unit occupies a prohibited blocking footprint: {actor['id']}"
                )

    @staticmethod
    def _virtual_route(actor, target, walls, solid, width, height):
        position = center(actor)
        speed = movement_speed(actor)
        current_attack_rate = attack_rate(actor)
        if target_distance(position, target) <= actor["range"] + EPSILON:
            if actor.get("_target_scoring") == "arrival_time_then_footprint_distance":
                return [], 0
            return [], target_distance(position, target) / speed
        start = floor(position[0]), floor(position[1])
        if start in solid:
            return None, None
        profile = actor["wall_behavior"]
        weapon = profile["weapon"]
        weighted = profile["route_cost"] == "travel_seconds_plus_nominal_clearance"
        # Cache the exact query, including fractional departure, nominal wall HP,
        # effective movement/attack/damage rates and all live obstruction cells.
        # Movement, damage and Freeze clocks themselves remain owned by callers.
        query = (
            _weighted_route if width * height <= 4096 else _weighted_route.__wrapped__
        )
        route, cost = query(
            position,
            tuple(target[key] for key in ("x", "y", "width", "height")),
            actor["range"],
            speed,
            weapon["damage"] * damage_multiplier(actor) if weighted else 0,
            weapon["attack_interval_seconds"] if weighted else 0,
            current_attack_rate if weighted else 1,
            (
                frozenset((cell, wall["hp"]) for cell, wall in walls.items())
                if weighted
                else frozenset()
            ),
            frozenset(solid),
            width,
            height,
        )
        return (list(route) if route is not None else None), cost

    @staticmethod
    def _obstruction(actor, route, walls):
        position = center(actor)
        for point in [position, *route]:
            cell = floor(point[0]), floor(point[1])
            if cell in walls:
                return walls[cell]
        return None

    @staticmethod
    def _approach(actor, route, wall):
        weapon_range = actor["wall_behavior"]["weapon"]["range"]
        if target_distance(center(actor), wall) <= weapon_range + EPSILON:
            return []
        approach = []
        for point in route:
            if floor(point[0]) == wall["x"] and floor(point[1]) == wall["y"]:
                previous = approach[-1] if approach else center(actor)
                cell = floor(previous[0]), floor(previous[1])
                endpoint = ground_attack_point(cell, wall, weapon_range)
                if endpoint is not None and endpoint != previous:
                    approach.append(endpoint)
                break
            approach.append(point)
            if target_distance(point, wall) <= weapon_range + EPSILON:
                break
        return approach

    def select_target(self, actor, actors, time, blocked, width, height):
        blocked = blocked - set(map(tuple, actor.get("_spell_jump_cells", [])))
        if actor["movement"] != "ground" or actor["wall_behavior"]["kind"] == "avoid":
            return _select_target(actor, actors, time, blocked, width, height)
        if actor["wall_behavior"]["kind"] == "jump_enemy_walls":
            _, solid = self._maps(actor, actors, time, blocked)
            return _select_target(actor, actors, time, solid, width, height)
        if not _active(actor, time):
            return None, None
        walls, solid = self._maps(actor, actors, time, blocked)
        retained = actors.get(actor["target"])
        choices = []
        if retained is not None and _eligible(actor, retained, time):
            route, cost = self._virtual_route(
                actor, retained, walls, solid, width, height
            )
            if route is not None:
                choices.append(
                    (
                        target_priority(actor, retained["kind"]),
                        cost,
                        (
                            target_distance(center(actor), retained)
                            if actor.get("_target_scoring")
                            == "arrival_time_then_footprint_distance"
                            else 0
                        ),
                        retained["id"],
                        retained,
                        route,
                    )
                )
        candidates = [] if choices else actors.values()
        for target in candidates:
            if not _eligible(actor, target, time):
                continue
            route, cost = self._virtual_route(
                actor, target, walls, solid, width, height
            )
            if route is not None:
                choices.append(
                    (
                        target_priority(actor, target["kind"]),
                        cost,
                        (
                            target_distance(center(actor), target)
                            if actor.get("_target_scoring")
                            == "arrival_time_then_footprint_distance"
                            else 0
                        ),
                        target["id"],
                        target,
                        route,
                    )
                )
        if not choices:
            actor["target"] = None
            actor["obstruction_target"] = None
            return None, None
        _, _, _, _, target, route = min(choices, key=lambda item: item[:4])
        actor["target"] = target["id"]
        obstruction = self._obstruction(actor, route, walls)
        actor["obstruction_target"] = (
            obstruction["id"] if obstruction is not None else None
        )
        if (
            obstruction is not None
            and actor["wall_behavior"]["kind"] == "clear_obstructions"
        ):
            route = self._approach(actor, route, obstruction)
        return target, route

    def wall_hit(self, actor, actors, time, damage, trace):
        from .damage_receipts import record_damage

        obstruction = actors.get(actor.get("obstruction_target"))
        if obstruction is None or not _active(obstruction, time):
            return
        profile = actor["wall_behavior"]
        weapon = profile["weapon"]
        if target_distance(center(actor), obstruction) > weapon["range"] + EPSILON:
            return
        clock = (
            "next_attack"
            if weapon["cooldown"] == "shared_with_main_weapon"
            else "_wall_next_attack"
        )
        if actor[clock] > time + EPSILON:
            return
        protected = obstruction["immune_until"] > time + EPSILON
        hit_damage = weapon["damage"] * damage_multiplier(actor)
        callback = getattr(self, "area_impacts", None)
        impacts = callback(actor, obstruction, actors, time) if callback else None
        if impacts is None:
            impacts = [obstruction]
        for recipient in impacts:
            damage[recipient["id"]] += record_damage(
                self,
                recipient,
                hit_damage,
                time,
                source_id=actor["id"],
                source_actor_id=actor["id"],
                source_team=actor["team"],
                origin="weapon",
            )
        actor[clock] = time + weapon["attack_interval_seconds"] / attack_rate(actor)
        trace.append(
            {
                "time_seconds": time,
                "event": "wall_impact",
                "source": actor["id"],
                "target": obstruction["id"],
                "targets": [recipient["id"] for recipient in impacts],
                "intended_primary_target": actor["target"],
                "damage": hit_damage,
                "protected": protected,
                "motion_profile": profile["kind"],
                "cooldown": weapon["cooldown"],
            }
        )

    @staticmethod
    def main_weapon_blocked(actor):
        return (
            actor["movement"] == "ground"
            and actor["wall_behavior"]["kind"] == "clear_obstructions"
            and actor.get("obstruction_target") is not None
        )
