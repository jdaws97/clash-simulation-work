"""Visible Giga Bombs with aggregate triggers and declared finite knockback.

The snapshot supplies the aggregate threshold, radii and blast damage. Every
attacker's trigger weight and response are explicit inputs, including reserves
and generated actors. Knockback distance, speed and collision remain hypotheses.
"""

from collections import defaultdict
from copy import deepcopy
from math import hypot

from .buffs import _circle_events
from .spell_visibility import untargetable_until
from .common import InputError, identifier, integer, number, require
from .displacements import enqueue_linear_displacement
from .spatial import EPSILON, _active, center, target_distance
from .tornado_traps import _rectangle_entry
from .trap_support import validate_trap_footprints


PUBLISHER_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/game-updates/"
    "the-town-hall-17-update-is-here-2/"
)
GIGA_BOMB_RULES = {
    "giga_bomb_layout": "visible_nonblocking_untargetable_trap_excluded_from_destruction",
    "giga_bomb_trigger": "inclusive_live_unit_centers_sum_explicit_weights_to_catalog_threshold",
    "giga_bomb_trigger_crossings": "positive_circle_entries_tangencies_and_reentries_on_declared_routes",
    "giga_bomb_blast": "fixed_trap_center_live_recipients_after_declared_delay",
    "giga_bomb_damage": "simultaneous_blast_damage_with_independent_protection_and_push",
    "giga_bomb_motion": "radial_finite_linear_push_with_declared_clipping_and_recovery",
    "giga_bomb_overlap": "tornado_priority_else_replace_gust_motion_keep_longest_pause",
    "giga_bomb_verification": "explicit_housing_and_knockback_hypotheses_not_replay_calibrated",
}
POLICIES = {
    "trigger_geometry": "inclusive_unit_centers",
    "trigger_weight_basis": "explicit_per_actor_housing_weight_hypothesis",
    "released_blast": "independent_of_trigger_survival_and_position",
    "blast_geometry": "point_to_live_target_footprint",
    "blast_visibility": "all_live_recipients_ignore_acquisition_visibility",
    "blast_resolution": "capture_all_recipients_then_simultaneous_damage",
    "trap_status": "freeze_and_overgrowth_do_not_pause_or_disarm_trap",
    "motion_policy": "finite_linear_radial_push_continues_during_freeze",
    "collision_policy": "clip_before_ground_obstacles_and_board_edge",
    "sweeper_overlap": "replace_existing_motion_preserve_longest_pause",
    "tornado_overlap": "tornado_blocks_push_but_not_blast_damage",
    "simultaneous_push_order": "arrival_then_trap_id_latest_push_replaces",
}
PARAMETERS = {
    *POLICIES,
    "source",
    "arming_seconds",
    "delay_seconds",
    "trigger_radius_multiplier",
    "damage_radius_multiplier",
    "damage_multiplier",
    "trigger_visibility",
    "trigger_protection",
    "push_protection",
    "push_distance_tiles",
    "push_speed_tiles_per_second",
    "recovery_seconds",
    "coincident_direction",
    "unit_responses",
}
MODEL_FIELDS = {
    "id",
    "entity",
    "level",
    "team",
    "statistics_source",
    "x",
    "y",
    "width",
    "height",
    "layout_visibility",
    "blocking",
    "targetable",
    "counts_for_destruction",
    "damage",
    "trigger_radius",
    "damage_radius",
    "trigger_housing_space",
    "parameters",
    "source_audit",
}
RESPONSE_FIELDS = {"trigger_weight", "damage_multiplier", "push_multiplier"}


def _exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise InputError(f"Giga Bomb {label} needs every explicit supported field")


def _validate_parameters(parameters):
    _exact(parameters, PARAMETERS, "parameters")
    identifier(parameters["source"], "Giga Bomb behavior evidence")
    for field, expected in POLICIES.items():
        if parameters[field] != expected:
            raise InputError(f"Unsupported Giga Bomb {field}")
    for field in (
        "arming_seconds",
        "delay_seconds",
        "trigger_radius_multiplier",
        "damage_radius_multiplier",
        "damage_multiplier",
        "push_distance_tiles",
        "recovery_seconds",
    ):
        number(parameters[field], f"Giga Bomb {field}", 0)
    number(parameters["push_speed_tiles_per_second"], "Giga Bomb push speed", EPSILON)
    choices = {
        "trigger_visibility": {
            "ignore_acquisition_visibility",
            "require_visible_units",
        },
        "trigger_protection": {
            "protected_units_contribute",
            "protected_units_do_not_contribute",
        },
        "push_protection": {
            "damage_immunity_blocks_push",
            "damage_immunity_does_not_block_push",
        },
    }
    for field, values in choices.items():
        if parameters[field] not in values:
            raise InputError(f"Unsupported Giga Bomb {field}")
    direction = parameters["coincident_direction"]
    if not isinstance(direction, list) or len(direction) != 2:
        raise InputError("Giga Bomb coincident direction needs two coordinates")
    for coordinate in direction:
        number(coordinate, "Giga Bomb coincident direction")
    if hypot(*direction) <= EPSILON:
        raise InputError("Giga Bomb coincident direction cannot be zero")
    responses = parameters["unit_responses"]
    if not isinstance(responses, dict):
        raise InputError("Giga Bomb responses must explicitly map attacker identities")
    for actor_id, response in responses.items():
        identifier(actor_id, "Giga Bomb response actor")
        _exact(response, RESPONSE_FIELDS, "unit response")
        integer(response["trigger_weight"], "Giga Bomb actor trigger weight", 0)
        number(
            response["damage_multiplier"], "Giga Bomb recipient damage multiplier", 0
        )
        number(response["push_multiplier"], "Giga Bomb recipient push multiplier", 0)


def compile_giga_bomb(instance, catalog):
    if require(instance, "entity") != "giga-bomb":
        raise InputError("Giga Bomb compiler requires giga-bomb")
    level = integer(require(instance, "level"), "Giga Bomb level", 1)
    town_hall = integer(require(instance, "town_hall"), "Giga Bomb Town Hall", 1)
    if not catalog.available("giga-bomb", level, town_hall):
        raise InputError("Giga Bomb level is unavailable at the selected Town Hall")
    if require(instance, "team") != "defense":
        raise InputError("Giga Bombs belong to the defending team")
    parameters = require(instance, "parameters")
    _validate_parameters(parameters)
    entity = catalog.entity("giga-bomb")
    row = catalog.level("giga-bomb", level)
    return {
        "id": identifier(require(instance, "id"), "Giga Bomb instance"),
        "entity": "giga-bomb",
        "level": level,
        "team": "defense",
        "statistics_source": catalog.records["giga-bomb"]["source"],
        "x": integer(require(instance, "x"), "Giga Bomb x", 0),
        "y": integer(require(instance, "y"), "Giga Bomb y", 0),
        "width": 2,
        "height": 2,
        "layout_visibility": "visible",
        "blocking": False,
        "targetable": False,
        "counts_for_destruction": False,
        "damage": number(row["damage"], "Giga Bomb catalog damage", 0)
        * parameters["damage_multiplier"],
        "trigger_radius": number(entity["triggerRadius"], "Giga Bomb trigger radius", 0)
        * parameters["trigger_radius_multiplier"],
        "damage_radius": number(entity["damageRadius"], "Giga Bomb blast radius", 0)
        * parameters["damage_radius_multiplier"],
        "trigger_housing_space": integer(
            entity["triggerHousingSpace"], "Giga Bomb threshold", 1
        ),
        "parameters": deepcopy(parameters),
        "source_audit": {
            "publisher_source": PUBLISHER_SOURCE,
            "visibility": "publisher_confirms_visible_trap_and_strong_pushback",
            "catalog_quantities": "triggerHousingSpace_triggerRadius_damageRadius_level_damage",
            "unresolved": "per_actor_weights_trigger_policies_delay_push_distance_speed_collision",
        },
    }


def _validate_model(trap, actors):
    _exact(
        {
            key: value
            for key, value in trap.items()
            if key != "battle_modifier_application"
        },
        MODEL_FIELDS,
        "model",
    )
    if (
        trap["entity"] != "giga-bomb"
        or trap["team"] != "defense"
        or trap["layout_visibility"] != "visible"
        or trap["blocking"] is not False
        or trap["targetable"] is not False
        or trap["counts_for_destruction"] is not False
        or trap["width"] != 2
        or trap["height"] != 2
    ):
        raise InputError("Giga Bomb must remain a visible untargetable uncounted trap")
    _validate_parameters(trap["parameters"])
    for field in ("damage", "trigger_radius", "damage_radius"):
        number(trap[field], f"Giga Bomb {field}", 0)
    integer(trap["trigger_housing_space"], "Giga Bomb trigger threshold", 1)
    expected = {
        key
        for key, actor in actors.items()
        if actor["team"] != trap["team"] and actor["kind"] == "unit"
    }
    responses = set(trap["parameters"]["unit_responses"])
    if responses != expected:
        missing = sorted(expected - responses)
        extra = sorted(responses - expected)
        raise InputError(
            f"Giga Bomb responses must cover all attacking units, including reserves and generated actors; missing={missing}, extra={extra}"
        )


def _clipped_push(actor, direction, distance, actors, time, width, height):
    origin = center(actor)
    length = hypot(*direction)
    destination = tuple(
        origin[index] + direction[index] / length * distance for index in (0, 1)
    )
    fraction = 1.0
    for start, end, minimum, maximum in (
        (
            origin[0],
            destination[0],
            actor["width"] / 2,
            width - actor["width"] / 2 - EPSILON * 256,
        ),
        (
            origin[1],
            destination[1],
            actor["height"] / 2,
            height - actor["height"] / 2 - EPSILON * 256,
        ),
    ):
        difference = end - start
        if difference > EPSILON:
            fraction = min(fraction, max(0, (maximum - start) / difference))
        elif difference < -EPSILON:
            fraction = min(fraction, max(0, (minimum - start) / difference))
    if actor["layer"] == "ground":
        for obstacle in actors.values():
            if not obstacle["blocking"] or not _active(obstacle, time):
                continue
            entry = _rectangle_entry(
                origin,
                destination,
                obstacle["x"] - actor["width"] / 2,
                obstacle["y"] - actor["height"] / 2,
                obstacle["x"] + obstacle["width"] + actor["width"] / 2,
                obstacle["y"] + obstacle["height"] + actor["height"] / 2,
            )
            if entry is not None:
                fraction = min(fraction, entry)
    if fraction < 1 - EPSILON:
        fraction = max(0, fraction - EPSILON * 256 / max(distance, EPSILON))
    return distance * fraction


class GigaBombCombat:
    """Capture aggregate trigger evidence, then resolve a live delayed explosion."""

    def __init__(self, traps, actors, width, height, displacement):
        validate_trap_footprints(traps, actors, width, height)
        self.models = {}
        for trap in traps:
            _validate_model(trap, actors)
            self.models[trap["id"]] = deepcopy(trap)
        self.width = width
        self.height = height
        self.displacement = displacement
        self.triggered = {}
        self.resolved = set()

    @staticmethod
    def _live_unit(trap, actor, time):
        return (
            _active(actor, time)
            and actor["kind"] == "unit"
            and actor["team"] != trap["team"]
            and actor["layer"] in {"ground", "air"}
        )

    def _trigger_eligible(self, trap, actor, time):
        if not self._live_unit(trap, actor, time):
            return False
        parameters = trap["parameters"]
        response = parameters["unit_responses"][actor["id"]]
        if response["trigger_weight"] == 0:
            return False
        if (
            parameters["trigger_protection"] == "protected_units_do_not_contribute"
            and actor["immune_until"] > time + EPSILON
        ):
            return False
        if (
            parameters["trigger_visibility"] == "require_visible_units"
            and untargetable_until(actor) > time + EPSILON
        ):
            return False
        return True

    def _start_push(self, trap, actor, actors, time, trace):
        parameters = trap["parameters"]
        response = parameters["unit_responses"][actor["id"]]
        distance = parameters["push_distance_tiles"] * response["push_multiplier"]
        if distance <= EPSILON:
            return
        reason = None
        if actor.get("_tornado_capture_until", 0) > time + EPSILON:
            reason = "tornado_priority"
        elif (
            actor["immune_until"] > time + EPSILON
            and parameters["push_protection"] == "damage_immunity_blocks_push"
        ):
            reason = "damage_immunity_blocks_push"
        if reason is not None:
            trace.append(
                {
                    "event": "giga_bomb_push_suppressed",
                    "time_seconds": time,
                    "trap_id": trap["id"],
                    "target": actor["id"],
                    "reason": reason,
                }
            )
            return
        origin = center(trap)
        point = center(actor)
        direction = tuple(point[index] - origin[index] for index in (0, 1))
        if hypot(*direction) <= EPSILON:
            direction = parameters["coincident_direction"]
        clipped = _clipped_push(
            actor, direction, distance, actors, time, self.width, self.height
        )
        direction_length = hypot(*direction)
        destination = tuple(
            point[index] + direction[index] / direction_length * clipped
            for index in (0, 1)
        )
        enqueue_linear_displacement(
            self.displacement,
            actor,
            time,
            destination,
            parameters["push_speed_tiles_per_second"],
            parameters["recovery_seconds"],
            trap["id"],
            trace,
            requested_distance=distance,
        )
        trace.append(
            {
                "event": "giga_bomb_push",
                "time_seconds": time,
                "trap_id": trap["id"],
                "target": actor["id"],
                "requested_distance": distance,
                "actual_distance": clipped,
                "collision_clipped": clipped < distance - EPSILON,
            }
        )

    def update(self, actors, time, trace):
        for trap_id, trap in sorted(self.models.items()):
            parameters = trap["parameters"]
            if (
                trap_id in self.triggered
                or time + EPSILON < parameters["arming_seconds"]
            ):
                continue
            origin = center(trap)
            members = [
                actor
                for actor in actors.values()
                if self._trigger_eligible(trap, actor, time)
                and hypot(center(actor)[0] - origin[0], center(actor)[1] - origin[1])
                <= trap["trigger_radius"] + EPSILON
            ]
            weights = {
                actor["id"]: parameters["unit_responses"][actor["id"]]["trigger_weight"]
                for actor in sorted(members, key=lambda value: value["id"])
            }
            weight = sum(weights.values())
            if weight < trap["trigger_housing_space"]:
                continue
            event = {
                "trap_id": trap_id,
                "trigger_seconds": time,
                "arrival_seconds": time + parameters["delay_seconds"],
                "trigger_weights": weights,
                "aggregate_trigger_weight": weight,
            }
            self.triggered[trap_id] = event
            trace.append(
                {"event": "giga_bomb_trigger", "time_seconds": time, **deepcopy(event)}
            )
        damage = defaultdict(float)
        pending = sorted(
            (event["arrival_seconds"], trap_id)
            for trap_id, event in self.triggered.items()
            if trap_id not in self.resolved
            and event["arrival_seconds"] <= time + EPSILON
        )
        for _, trap_id in pending:
            trap = self.models[trap_id]
            origin = center(trap)
            recipients = [
                actor
                for actor in actors.values()
                if self._live_unit(trap, actor, time)
                and target_distance(origin, actor) <= trap["damage_radius"] + EPSILON
            ]
            amounts = {}
            protected = []
            for actor in sorted(recipients, key=lambda value: value["id"]):
                from .damage_receipts import record_damage

                response = trap["parameters"]["unit_responses"][actor["id"]]
                amount = trap["damage"] * response["damage_multiplier"]
                amounts[actor["id"]] = amount
                if actor["immune_until"] > time + EPSILON:
                    protected.append(actor["id"])
                resolved = record_damage(
                    self,
                    actor,
                    amount,
                    time,
                    source_id=trap_id,
                    source_team=trap["team"],
                    origin="trap",
                )
                if resolved > 0:
                    damage[actor["id"]] += resolved
                self._start_push(trap, actor, actors, time, trace)
            self.resolved.add(trap_id)
            trace.append(
                {
                    "event": "giga_bomb_impact",
                    "time_seconds": time,
                    "trap_id": trap_id,
                    "position": origin,
                    "requested_damage": amounts,
                    "protected_targets": protected,
                    "trigger_weights": deepcopy(
                        self.triggered[trap_id]["trigger_weights"]
                    ),
                }
            )
        return damage

    def next_boundary(self, time):
        values = [
            trap["parameters"]["arming_seconds"]
            for key, trap in self.models.items()
            if key not in self.triggered
        ]
        values.extend(
            event["arrival_seconds"]
            for key, event in self.triggered.items()
            if key not in self.resolved
        )
        future = [value for value in values if value > time + EPSILON]
        return min(future) if future else None

    def first_crossing_delay(self, actor, route, time, horizon, effective_speed):
        speed = number(effective_speed, "Giga Bomb crossing speed", 0)
        if speed <= EPSILON or horizon <= EPSILON:
            return None
        earliest = None
        for trap_id, trap in self.models.items():
            if (
                trap_id in self.triggered
                or trap["parameters"]["arming_seconds"] > time + EPSILON
                or not self._trigger_eligible(trap, actor, time)
            ):
                continue
            origin = center(trap)
            previous = center(actor)
            traveled = 0.0
            for point in route:
                length = hypot(point[0] - previous[0], point[1] - previous[1])
                for contact, inside_after in _circle_events(
                    previous, point, origin, trap["trigger_radius"]
                ):
                    delay = (traveled + contact) / speed
                    if delay <= EPSILON or delay > horizon + EPSILON:
                        continue
                    fraction = contact / length
                    position = tuple(
                        previous[index] + (point[index] - previous[index]) * fraction
                        for index in (0, 1)
                    )
                    outward = sum(
                        (position[index] - origin[index])
                        * (point[index] - previous[index])
                        for index in (0, 1)
                    )
                    if not inside_after and outward > EPSILON:
                        continue
                    earliest = min(earliest, delay) if earliest is not None else delay
                traveled += length
                if traveled >= speed * horizon - EPSILON:
                    break
                previous = point
        return earliest

    def result(self):
        return {
            "triggered": deepcopy(self.triggered),
            "resolved": sorted(self.resolved),
            "untriggered": sorted(set(self.models) - set(self.triggered)),
            "pending_at_horizon": [
                deepcopy(event)
                for key, event in sorted(self.triggered.items())
                if key not in self.resolved
            ],
            "layout_visibility": "visible",
            "physics_verification": "declared_aggregate_housing_and_finite_push_hypothesis",
        }
