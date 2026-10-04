"""Finite Tornado fields with explicit damage quantity and displacement physics.

The catalog's damage number does not identify DPS, total damage or a pulse.
Its interpretation is required input. Pull speed, orbit geometry, collision,
protection and arbitration remain named hypotheses, never replay calibration.
"""

from collections import defaultdict
from copy import deepcopy
from math import atan2, cos, hypot, pi, sin

from .spell_visibility import untargetable_until
from .common import InputError, identifier, integer, number, require
from .rates import pause_attack_work
from .spatial import EPSILON, _active, _blocked, center, target_distance
from .trap_support import (
    circle_entry_delay,
    eligible_trap_unit,
    validate_trap_footprints,
)


TORNADO_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/news/"
    "october-2018-update-patch-notes/"
)
TORNADO_RULES = {
    "tornado_trigger": "one_visible_enemy_ground_or_air_entry_then_fixed_duration_field",
    "tornado_damage": "explicit_catalog_quantity_with_independent_pulse_clock_and_final_partial_interval",
    "tornado_motion": "finite_inward_linear_pull_then_declared_regular_polygon_orbit",
    "tornado_status": "forced_motion_continues_during_freeze_with_separate_attack_work_pause",
    "tornado_sweeper_overlap": "tornado_capture_cancels_existing_sweeper_and_rejects_new_gusts_until_release",
    "tornado_overlap": "earliest_active_tornado_then_instance_id",
    "tornado_collision": "clip_before_ground_obstacles_or_board_edge_then_hold_until_release",
}
PARAMETERS = {
    "source",
    "arming_seconds",
    "delay_seconds",
    "duration_multiplier",
    "trigger_radius_multiplier",
    "effect_radius_multiplier",
    "damage_multiplier",
    "damage_quantity",
    "pulse_interval_seconds",
    "excluded_trigger_entities",
    "excluded_effect_entities",
    "pull_speed_tiles_per_second",
    "orbit_radius_tiles",
    "orbit_vertices",
    "orbit_period_seconds",
    "orbit_direction",
    "recovery_seconds",
    "recipient_speed_policy",
    "motion_policy",
    "attack_policy",
    "freeze_policy",
    "damage_immunity_policy",
    "effect_visibility_policy",
    "sweeper_overlap_policy",
    "tornado_overlap_policy",
    "collision_policy",
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
    "damage",
    "trigger_radius",
    "effect_radius",
    "duration_seconds",
    "parameters",
}
DAMAGE_QUANTITIES = {
    "catalog_damage_is_total_over_duration",
    "catalog_damage_is_damage_per_second",
    "catalog_damage_is_each_pulse",
}


def _validate_parameters(parameters):
    if not isinstance(parameters, dict) or set(parameters) != PARAMETERS:
        raise InputError("Tornado Trap requires every damage and displacement policy")
    identifier(parameters["source"], "Tornado Trap evidence")
    for field in (
        "arming_seconds",
        "delay_seconds",
        "damage_multiplier",
        "recovery_seconds",
    ):
        number(parameters[field], field, 0)
    for field in (
        "duration_multiplier",
        "trigger_radius_multiplier",
        "effect_radius_multiplier",
        "pulse_interval_seconds",
        "pull_speed_tiles_per_second",
        "orbit_radius_tiles",
        "orbit_period_seconds",
    ):
        number(parameters[field], field, EPSILON)
    integer(parameters["orbit_vertices"], "Tornado orbit vertices", 3, 256)
    if parameters["orbit_period_seconds"] / parameters["orbit_vertices"] <= EPSILON:
        raise InputError("Tornado orbit segments must have positive solver duration")
    if parameters["damage_quantity"] not in DAMAGE_QUANTITIES:
        raise InputError("Tornado catalog damage quantity must be explicitly selected")
    if parameters["orbit_direction"] not in {"clockwise", "counterclockwise"}:
        raise InputError("Tornado orbit direction must be explicit")
    if parameters["damage_immunity_policy"] not in {
        "blocks_damage_only",
        "blocks_damage_and_capture",
    }:
        raise InputError("Tornado damage-immunity capture policy must be explicit")
    policies = {
        "recipient_speed_policy": "same_declared_pull_speed_for_all_included_units",
        "motion_policy": "finite_inward_pull_then_regular_polygon_orbit",
        "attack_policy": "pause_unfinished_attack_work_until_release",
        "freeze_policy": "forced_motion_continues_while_frozen",
        "effect_visibility_policy": "affect_invisible_units_after_visible_trigger",
        "sweeper_overlap_policy": "tornado_priority_cancel_existing_and_reject_new_gusts",
        "tornado_overlap_policy": "earliest_active_tornado_then_instance_id",
        "collision_policy": "clip_before_ground_obstacles_or_board_edge_then_hold",
    }
    for field, expected in policies.items():
        if parameters[field] != expected:
            raise InputError(f"Unsupported Tornado {field}")
    for field in ("excluded_trigger_entities", "excluded_effect_entities"):
        values = parameters[field]
        if not isinstance(values, list) or len(values) != len(set(values)):
            raise InputError("Tornado exclusions must be explicit unique lists")
        for entity_id in values:
            identifier(entity_id, field)


def compile_tornado_trap(instance, catalog):
    if require(instance, "entity") != "tornado-trap":
        raise InputError("Tornado compiler requires tornado-trap")
    level = integer(require(instance, "level"), "Tornado level", 1)
    town_hall = integer(require(instance, "town_hall"), "Tornado Town Hall", 1)
    if not catalog.available("tornado-trap", level, town_hall):
        raise InputError("Tornado level is unavailable at the selected Town Hall")
    if require(instance, "team") != "defense":
        raise InputError("Tornado Traps belong to the defending team")
    parameters = require(instance, "parameters")
    _validate_parameters(parameters)
    for field in ("excluded_trigger_entities", "excluded_effect_entities"):
        for entity_id in parameters[field]:
            catalog.entity(entity_id)
    row = catalog.level("tornado-trap", level)
    entity = catalog.entity("tornado-trap")
    effect_radius = (
        number(require(entity, "damageRadius"), "Tornado radius", EPSILON)
        * parameters["effect_radius_multiplier"]
    )
    if parameters["orbit_radius_tiles"] > effect_radius:
        raise InputError("Tornado orbit radius cannot exceed its effect radius")
    return {
        "id": identifier(require(instance, "id"), "Tornado instance"),
        "entity": "tornado-trap",
        "level": level,
        "team": "defense",
        "statistics_source": catalog.records["tornado-trap"]["source"],
        "x": integer(require(instance, "x"), "Tornado x", 0),
        "y": integer(require(instance, "y"), "Tornado y", 0),
        "width": 1,
        "height": 1,
        "damage": number(require(row, "damage"), "Tornado catalog damage", 0)
        * parameters["damage_multiplier"],
        "trigger_radius": number(
            require(entity, "triggerRadius"), "Tornado trigger radius", EPSILON
        )
        * parameters["trigger_radius_multiplier"],
        "effect_radius": effect_radius,
        "duration_seconds": number(
            require(row, "duration"), "Tornado duration", EPSILON
        )
        * parameters["duration_multiplier"],
        "parameters": deepcopy(parameters),
    }


def _rectangle_entry(origin, destination, left, bottom, right, top):
    """Closed rectangle entry fraction for an axis-aligned blocking tile."""
    low, high = 0.0, 1.0
    for start, end, minimum, maximum in (
        (origin[0], destination[0], left, right),
        (origin[1], destination[1], bottom, top),
    ):
        difference = end - start
        if abs(difference) <= EPSILON:
            if start < minimum or start > maximum:
                return None
            continue
        first, second = (minimum - start) / difference, (maximum - start) / difference
        low = max(low, min(first, second))
        high = min(high, max(first, second))
        if low > high + EPSILON:
            return None
    return max(low, 0) if high >= 0 and low <= 1 else None


def _legal_endpoint(actor, destination, actors, time, width, height):
    origin = center(actor)
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
        for x, y in _blocked(actors, time):
            entry = _rectangle_entry(origin, destination, x, y, x + 1, y + 1)
            if entry is not None:
                fraction = min(fraction, entry)
    blocked = fraction < 1 - EPSILON
    if blocked:
        length = hypot(destination[0] - origin[0], destination[1] - origin[1])
        fraction = max(0, fraction - EPSILON * 256 / max(length, EPSILON))
    point = tuple(
        origin[index] + (destination[index] - origin[index]) * fraction
        for index in (0, 1)
    )
    return point, blocked


class TornadoTrapCombat:
    """Persistent one-shot fields own finite motion and independent damage pulses."""

    def __init__(self, traps, actors, width, height, sweeper_motion=None):
        validate_trap_footprints(traps, actors, width, height)
        self.models = {}
        for trap in traps:
            if set(trap) - {"battle_modifier_application"} != MODEL_FIELDS:
                raise InputError("Tornado model has unsupported or missing fields")
            if trap["entity"] != "tornado-trap" or trap["team"] != "defense":
                raise InputError("Tornado runtime requires a defending Tornado Trap")
            _validate_parameters(trap["parameters"])
            for field in ("trigger_radius", "effect_radius", "duration_seconds"):
                number(trap[field], field, EPSILON)
            number(trap["damage"], "Tornado damage quantity", 0)
            if trap["parameters"]["orbit_radius_tiles"] > trap["effect_radius"]:
                raise InputError("Tornado orbit exceeds its effect radius")
            self.models[trap["id"]] = deepcopy(trap)
        self.actors = actors
        self.width = width
        self.height = height
        self.sweeper_motion = sweeper_motion
        self.states = {
            trap_id: {
                "trigger_seconds": None,
                "active_seconds": None,
                "end_seconds": None,
                "next_pulse": None,
                "last_pulse": None,
                "pulse_count": 0,
                "capture_count": 0,
            }
            for trap_id in self.models
        }
        self.captures = {}

    @staticmethod
    def _trigger_eligible(trap, actor, time):
        return eligible_trap_unit(
            actor,
            trap["team"],
            ["ground", "air"],
            trap["parameters"]["excluded_trigger_entities"],
            time,
        )

    @staticmethod
    def _effect_eligible(trap, actor, time):
        return (
            _active(actor, time)
            and actor["kind"] == "unit"
            and actor["team"] != trap["team"]
            and actor["layer"] in {"ground", "air"}
            and actor["movement"] in {"ground", "air"}
            and actor.get("entity_adapter", {}).get("entity")
            not in trap["parameters"]["excluded_effect_entities"]
        )

    def _segment(self, actor, capture, destination, speed, actors, time):
        endpoint, blocked = _legal_endpoint(
            actor, destination, actors, time, self.width, self.height
        )
        origin = center(actor)
        distance = hypot(endpoint[0] - origin[0], endpoint[1] - origin[1])
        capture.update(
            origin=origin,
            destination=endpoint,
            start_seconds=time,
            speed_tiles_per_second=speed,
            hold_on_arrival=blocked,
        )
        if distance <= EPSILON:
            capture.update(phase="held", arrival_seconds=None)
        else:
            capture["arrival_seconds"] = time + distance / speed

    def _orbit_segment(self, actor, capture, actors, time):
        trap = self.models[capture["trap_id"]]
        parameters = trap["parameters"]
        radius = capture["radius"]
        if radius <= EPSILON:
            capture.update(phase="held", arrival_seconds=None)
            return
        direction = 1 if parameters["orbit_direction"] == "clockwise" else -1
        angle = capture["angle"] + direction * 2 * pi / parameters["orbit_vertices"]
        origin = center(trap)
        destination = origin[0] + radius * cos(angle), origin[1] + radius * sin(angle)
        distance = hypot(destination[0] - actor["x"], destination[1] - actor["y"])
        interval = parameters["orbit_period_seconds"] / parameters["orbit_vertices"]
        capture.update(phase="orbiting", angle=angle)
        self._segment(
            actor, capture, destination, max(distance / interval, EPSILON), actors, time
        )

    def _capture(self, trap, actor, actors, time, trace):
        state = self.states[trap["id"]]
        parameters = trap["parameters"]
        origin = center(trap)
        point = center(actor)
        distance = hypot(point[0] - origin[0], point[1] - origin[1])
        angle = atan2(point[1] - origin[1], point[0] - origin[0])
        radius = min(distance, parameters["orbit_radius_tiles"])
        capture = {
            "trap_id": trap["id"],
            "captured_seconds": time,
            "release_seconds": state["end_seconds"],
            "phase": "pulling",
            "angle": angle,
            "radius": radius,
        }
        self.captures[actor["id"]] = capture
        state["capture_count"] += 1
        actor["_tornado_capture_until"] = state["end_seconds"]
        pause_until = state["end_seconds"] + parameters["recovery_seconds"]
        pause_attack_work(actor, time, pause_until)
        actor["_displacement_pause_until"] = max(
            actor.get("_displacement_pause_until", 0), pause_until
        )
        replaced_sweeper = None
        if self.sweeper_motion is not None:
            replaced_sweeper = self.sweeper_motion.motions.pop(actor["id"], None)
        actor.pop("_path_signature", None)
        actor.pop("_remaining_path", None)
        actor["target"] = None
        if "healing_target" in actor:
            actor["healing_target"] = None
        if distance > radius + EPSILON:
            destination = origin[0] + radius * cos(angle), origin[1] + radius * sin(
                angle
            )
            self._segment(
                actor,
                capture,
                destination,
                parameters["pull_speed_tiles_per_second"],
                actors,
                time,
            )
        else:
            self._orbit_segment(actor, capture, actors, time)
        trace.append(
            {
                "event": "tornado_capture",
                "time_seconds": time,
                "trap": trap["id"],
                "target": actor["id"],
                "release_seconds": state["end_seconds"],
                "replaced_sweeper": replaced_sweeper is not None,
            }
        )

    def prepare(self, actors, time, trace):
        for actor_id, capture in list(self.captures.items()):
            if (
                not _active(actors[actor_id], time)
                or capture["release_seconds"] <= time + EPSILON
            ):
                self.captures.pop(actor_id)
                actors[actor_id]["_tornado_capture_until"] = 0
                trace.append(
                    {
                        "event": "tornado_release",
                        "time_seconds": time,
                        "trap": capture["trap_id"],
                        "target": actor_id,
                        "reason": (
                            "field_expired"
                            if _active(actors[actor_id], time)
                            else "recipient_inactive"
                        ),
                    }
                )
        for trap_id, trap in sorted(self.models.items()):
            state = self.states[trap_id]
            if (
                state["trigger_seconds"] is not None
                or time + EPSILON < trap["parameters"]["arming_seconds"]
            ):
                continue
            point = center(trap)
            candidates = [
                actor
                for actor in actors.values()
                if self._trigger_eligible(trap, actor, time)
                and target_distance(point, actor) <= trap["trigger_radius"] + EPSILON
            ]
            if not candidates:
                continue
            trigger = min(
                candidates,
                key=lambda actor: (target_distance(point, actor), actor["id"]),
            )
            start = time + trap["parameters"]["delay_seconds"]
            end = start + trap["duration_seconds"]
            state.update(
                trigger_seconds=time,
                active_seconds=start,
                end_seconds=end,
                last_pulse=start,
                next_pulse=min(
                    start + trap["parameters"]["pulse_interval_seconds"], end
                ),
            )
            trace.append(
                {
                    "event": "tornado_trigger",
                    "time_seconds": time,
                    "trap": trap_id,
                    "trigger": trigger["id"],
                    "active_seconds": start,
                    "end_seconds": end,
                }
            )
        active = sorted(
            (state["active_seconds"], trap_id)
            for trap_id, state in self.states.items()
            if state["active_seconds"] is not None
            and state["active_seconds"] <= time + EPSILON
            and time < state["end_seconds"] - EPSILON
        )
        for _, trap_id in active:
            trap = self.models[trap_id]
            for actor in sorted(actors.values(), key=lambda item: item["id"]):
                if (
                    actor["id"] in self.captures
                    or not self._effect_eligible(trap, actor, time)
                    or target_distance(center(trap), actor)
                    > trap["effect_radius"] + EPSILON
                    or actor["immune_until"] > time + EPSILON
                    and trap["parameters"]["damage_immunity_policy"]
                    == "blocks_damage_and_capture"
                ):
                    continue
                self._capture(trap, actor, actors, time, trace)

    def resolve(self, actors, time, trace):
        from .damage_receipts import record_damage

        damage = defaultdict(float)
        for trap_id, trap in sorted(self.models.items()):
            state = self.states[trap_id]
            while (
                state["next_pulse"] is not None
                and state["next_pulse"] <= time + EPSILON
            ):
                pulse_time = state["next_pulse"]
                elapsed = pulse_time - state["last_pulse"]
                quantity = trap["parameters"]["damage_quantity"]
                if quantity == "catalog_damage_is_each_pulse":
                    amount = trap["damage"]
                elif quantity == "catalog_damage_is_total_over_duration":
                    amount = trap["damage"] * elapsed / trap["duration_seconds"]
                else:
                    amount = trap["damage"] * elapsed
                recipients = [
                    actor
                    for actor in actors.values()
                    if self._effect_eligible(trap, actor, time)
                    and target_distance(center(trap), actor)
                    <= trap["effect_radius"] + EPSILON
                ]
                for actor in recipients:
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
                state["pulse_count"] += 1
                state["last_pulse"] = pulse_time
                state["next_pulse"] = (
                    min(
                        pulse_time + trap["parameters"]["pulse_interval_seconds"],
                        state["end_seconds"],
                    )
                    if pulse_time < state["end_seconds"] - EPSILON
                    else None
                )
                trace.append(
                    {
                        "event": "tornado_pulse",
                        "time_seconds": pulse_time,
                        "trap": trap_id,
                        "targets": sorted(actor["id"] for actor in recipients),
                        "protected_targets": sorted(
                            actor["id"]
                            for actor in recipients
                            if actor["immune_until"] > time + EPSILON
                        ),
                        "requested_damage_per_target": amount,
                    }
                )
        return damage

    def forced_motion(self, actor, time):
        capture = self.captures.get(actor["id"])
        if (
            capture is None
            or not _active(actor, time)
            or capture["release_seconds"] <= time + EPSILON
        ):
            return None
        return {
            "route": [] if capture["phase"] == "held" else [capture["destination"]],
            "speed_tiles_per_second": (
                0 if capture["phase"] == "held" else capture["speed_tiles_per_second"]
            ),
        }

    @staticmethod
    def blocks_sweeper(actor, time):
        return actor.get("_tornado_capture_until", 0) > time + EPSILON

    def advance(self, actors, time, duration, trace):
        number(duration, "Tornado motion interval", 0)
        end = time + duration
        for actor_id, capture in list(self.captures.items()):
            actor = actors[actor_id]
            if not _active(actor, time):
                continue
            cursor = time
            while (
                cursor < min(end, capture["release_seconds"]) - EPSILON
                and capture["phase"] != "held"
            ):
                arrival = capture["arrival_seconds"]
                stop = min(end, arrival, capture["release_seconds"])
                fraction = min(
                    1,
                    max(0, stop - capture["start_seconds"])
                    / (arrival - capture["start_seconds"]),
                )
                point = tuple(
                    capture["origin"][axis]
                    + (capture["destination"][axis] - capture["origin"][axis])
                    * fraction
                    for axis in (0, 1)
                )
                actor["x"] = point[0] - actor["width"] / 2
                actor["y"] = point[1] - actor["height"] / 2
                actor.pop("_path_signature", None)
                actor.pop("_remaining_path", None)
                cursor = stop
                if stop < arrival - EPSILON:
                    break
                if capture["hold_on_arrival"]:
                    capture.update(phase="held", arrival_seconds=None)
                    trace.append(
                        {
                            "event": "tornado_collision_hold",
                            "time_seconds": stop,
                            "trap": capture["trap_id"],
                            "target": actor_id,
                            "position": center(actor),
                        }
                    )
                elif stop < capture["release_seconds"] - EPSILON:
                    self._orbit_segment(actor, capture, actors, stop)
                else:
                    break

    def next_boundary(self, time):
        boundaries = []
        if self.models:
            for actor in self.actors.values():
                if _active(actor, time):
                    boundaries.extend(
                        (actor["immune_until"], untargetable_until(actor))
                    )
        for trap_id, state in self.states.items():
            if state["trigger_seconds"] is None:
                boundaries.append(self.models[trap_id]["parameters"]["arming_seconds"])
            else:
                boundaries.extend(
                    state[field]
                    for field in ("active_seconds", "end_seconds", "next_pulse")
                    if state[field] is not None
                )
        boundaries.extend(
            capture["arrival_seconds"]
            for capture in self.captures.values()
            if capture["arrival_seconds"] is not None
        )
        future = [boundary for boundary in boundaries if boundary > time + EPSILON]
        return min(future) if future else None

    def first_crossing_delay(self, actor, route, time, horizon, effective_speed):
        delays = []
        for trap_id, trap in self.models.items():
            state = self.states[trap_id]
            if state["trigger_seconds"] is None:
                eligible = time + EPSILON >= trap["parameters"][
                    "arming_seconds"
                ] and self._trigger_eligible(trap, actor, time)
                radius = trap["trigger_radius"]
            else:
                eligible = (
                    state["active_seconds"] <= time + EPSILON
                    and time < state["end_seconds"] - EPSILON
                    and actor["id"] not in self.captures
                    and self._effect_eligible(trap, actor, time)
                )
                radius = trap["effect_radius"]
            if not eligible:
                continue
            delay = circle_entry_delay(
                actor, route, center(trap), radius, horizon, effective_speed
            )
            if delay is not None:
                delays.append(delay)
        return min(delays) if delays else None

    def frame(self, actor, time):
        capture = self.captures.get(actor["id"])
        return {"tornado": deepcopy(capture)} if capture is not None else {}

    def result(self):
        return {
            "states": deepcopy(self.states),
            "captures": deepcopy(self.captures),
            "physics_verification": "explicit_uncalibrated_polygon_orbit_and_damage_quantity",
        }
