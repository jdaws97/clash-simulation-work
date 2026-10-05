"""Air Sweeper gusts and finite displacement under explicit physics hypotheses.

The catalog supplies zero damage, cadence, range and push strength. A pinned
extraction supplies acquisition angle, rotation step and minimum-range inputs.
Blast width, flight timing, push velocity and recovery remain selected inputs.
Linear displacement is separate from Freeze and from ordinary movement speed.
"""

from copy import deepcopy
from heapq import heappop, heappush
from math import atan2, cos, degrees, hypot, radians, sin, sqrt

from .spell_visibility import untargetable_until
from .common import InputError, identifier, number, require
from .rates import attack_rate
from .spatial import EPSILON, _active, center


EXTRACTION_SOURCE = (
    "https://raw.githubusercontent.com/ClashKingInc/ClashKingAssets/"
    "b8f42a707fe92d5293d46088bf536450ae422e7b/assets/static_data.json"
)
PUBLISHER_LEVEL_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/news/home-village-new-levels/"
)
EXTRACTED_GEOMETRY = {
    "data_id": 1000028,
    "cone_angle": 105,
    "aim_rotate_step": 45,
    "min_range": 100,
    "attack_range": 1500,
    "attack_speed": 5000,
}
SWEEPER_RULES = {
    "sweeper_weapon": "zero_damage_separate_gust_and_displacement_runtime",
    "sweeper_acquisition": "enemy_air_centers_in_oriented_annular_sector",
    "sweeper_selection": "nearest_center_then_instance_id_each_ready_launch",
    "sweeper_gust": "capture_launch_candidates_recheck_fixed_cone_at_individual_arrival",
    "sweeper_displacement": "finite_linear_motion_replaces_ordinary_movement",
    "sweeper_pause": "separate_attack_lock_preserves_unfinished_attack_work",
    "sweeper_overlap": "replace_remaining_motion_keep_longest_pause",
    "sweeper_board": "clip_distance_along_ray_keep_nominal_speed",
    "sweeper_validation": "declared_animation_and_physics_not_replay_validated",
}
PARAMETERS = {
    "source",
    "orientation_degrees",
    "orientation_basis",
    "geometry_basis",
    "blast_cone_degrees",
    "blast_aim",
    "recipient_policy",
    "excluded_entities",
    "launch_delay_seconds",
    "gust_speed_tiles_per_second",
    "push_statistic_basis",
    "push_distance_multiplier",
    "push_direction",
    "push_speed_tiles_per_second",
    "recovery_seconds",
    "recipient_freeze_policy",
    "damage_immunity_policy",
    "released_gust_policy",
    "overlap_policy",
    "board_policy",
    "collision_policy",
}
MODEL_FIELDS = PARAMETERS - {"push_distance_multiplier"} | {
    "kind",
    "acquisition_cone_degrees",
    "orientation_step_degrees",
    "minimum_range_tiles",
    "maximum_range_tiles",
    "push_distance_tiles",
}


def _validate_policies(model):
    identifier(model["source"], "Air Sweeper behavior evidence")
    policies = {
        "orientation_basis": "clockwise_from_positive_x_in_screen_coordinates",
        "geometry_basis": "pinned_extraction_degrees_and_hundredths_of_a_tile",
        "recipient_policy": "capture_launch_candidates_recheck_fixed_cone_at_impact",
        "push_statistic_basis": "snapshot_push_strength_is_tiles",
        "released_gust_policy": "released_gust_independent_of_source_state",
        "overlap_policy": "replace_remaining_motion_keep_longest_pause",
        "board_policy": "clip_distance_along_ray_keep_nominal_speed",
        "collision_policy": "air_ignores_ground_footprints",
    }
    for name, expected in policies.items():
        if model[name] != expected:
            raise InputError(f"Air Sweeper requires explicit {name}: {expected}")
    for name, allowed in (
        ("blast_aim", {"toward_primary", "fixed_orientation"}),
        ("push_direction", {"away_from_captured_source", "along_captured_blast_axis"}),
        (
            "recipient_freeze_policy",
            {"forced_motion_continues_while_frozen", "frozen_targets_ignore_new_push"},
        ),
        (
            "damage_immunity_policy",
            {"damage_immunity_blocks_push", "damage_immunity_does_not_block_push"},
        ),
    ):
        if model[name] not in allowed:
            raise InputError(f"Air Sweeper needs an explicit supported {name}")
    angle = number(model["orientation_degrees"], "Sweeper orientation", 0, 360)
    step = EXTRACTED_GEOMETRY["aim_rotate_step"]
    if abs(angle / step - round(angle / step)) > EPSILON:
        raise InputError("Sweeper orientation must follow the extracted rotation step")
    number(model["blast_cone_degrees"], "Sweeper blast cone", EPSILON, 180)
    for name in ("launch_delay_seconds", "recovery_seconds"):
        number(model[name], name, 0)
    for name in ("gust_speed_tiles_per_second", "push_speed_tiles_per_second"):
        number(model[name], name, EPSILON)
    exclusions = model["excluded_entities"]
    if not isinstance(exclusions, list):
        raise InputError("Sweeper excluded entities must be an explicit list")
    for entity in exclusions:
        identifier(entity, "Sweeper excluded entity")
    if len(exclusions) != len(set(exclusions)):
        raise InputError("Sweeper excluded entities must be unique")


def compile_air_sweeper(actor, instance, entity, row, modifiers):
    """Attach a non-damaging weapon to an upstream level-validated base actor."""
    if (
        entity["id"] != "air-sweeper"
        or instance["entity"] != "air-sweeper"
        or instance["mode"] != "normal"
        or instance["statistics_mode"] != "normal"
        or require(instance, "attack_parameters") != {}
        or "wall_parameters" in instance
    ):
        raise InputError("Air Sweeper needs its normal non-damaging weapon")
    parameters = require(instance, "sweeper_parameters")
    if not isinstance(parameters, dict) or set(parameters) != PARAMETERS:
        raise InputError("Every Sweeper geometry and displacement policy is required")
    _validate_policies(parameters)
    number(parameters["push_distance_multiplier"], "Sweeper push multiplier", EPSILON)
    if (
        modifiers["damage_multiplier"] != 1
        or modifiers["maximum_hp_damage_multiplier"] != 1
    ):
        raise InputError("A non-damaging Sweeper cannot apply damage modifiers")
    mode = require(require(entity, "modes"), "normal")
    if mode.get("damageType") != "none" or entity.get("targetType") != "air":
        raise InputError("Catalog Air Sweeper must remain air-only and non-damaging")
    maximum_range = number(require(mode, "range"), "Sweeper catalog range", EPSILON)
    maximum_range *= modifiers["range_multiplier"]
    minimum_range = EXTRACTED_GEOMETRY["min_range"] / 100
    minimum_range *= modifiers["range_multiplier"]
    actor.update(
        kind="defense",
        layer="ground",
        movement="stationary",
        speed=0,
        blocking=True,
        width=2,
        height=2,
        damage=0,
        range=maximum_range,
        minimum_range=minimum_range,
        attack_interval_seconds=number(
            require(mode, "attackSpeed"), "Sweeper catalog attack interval", EPSILON
        )
        * modifiers["attack_interval_multiplier"],
        target_priorities=["unit"],
        target_priority_tiers=[["unit"]],
        target_layers=["air"],
        attack_model={"kind": "none", "source": actor["source"]},
    )
    actor["sweeper_model"] = {
        key: deepcopy(value)
        for key, value in parameters.items()
        if key != "push_distance_multiplier"
    }
    actor["sweeper_model"].update(
        kind="air_sweeper",
        acquisition_cone_degrees=EXTRACTED_GEOMETRY["cone_angle"],
        orientation_step_degrees=EXTRACTED_GEOMETRY["aim_rotate_step"],
        minimum_range_tiles=minimum_range,
        maximum_range_tiles=maximum_range,
        push_distance_tiles=number(
            require(require(require(row, "stats"), "normal"), "pushStrength"),
            "Sweeper catalog push strength",
            EPSILON,
        )
        * parameters["push_distance_multiplier"],
    )
    validate_sweeper_model(actor)
    actor["entity_adapter"].update(
        sweeper_parameters=deepcopy(parameters),
        sweeper_statistics={
            "push_distance": "levels[].stats.normal.pushStrength",
            "interval": "modes.normal.attackSpeed",
            "maximum_range": "modes.normal.range",
            "geometry_reference": {
                "source": EXTRACTION_SOURCE,
                **deepcopy(EXTRACTED_GEOMETRY),
                "selected_range_units_per_tile": 100,
                "selected_time_units_per_second": 1000,
            },
            "publisher_level_reference": PUBLISHER_LEVEL_SOURCE,
        },
        behavior_verification="explicit_gust_geometry_and_finite_motion_not_replay_validated",
    )
    return actor


def validate_sweeper_model(actor):
    model = require(actor, "sweeper_model")
    if (
        not isinstance(model, dict)
        or set(model) != MODEL_FIELDS
        or model["kind"] != "air_sweeper"
    ):
        raise InputError("Air Sweeper needs its complete non-damaging weapon model")
    _validate_policies(model)
    for name in ("minimum_range_tiles", "maximum_range_tiles", "push_distance_tiles"):
        number(model[name], name, 0 if name == "minimum_range_tiles" else EPSILON)
    if model["minimum_range_tiles"] >= model["maximum_range_tiles"]:
        raise InputError("Sweeper minimum range must be below its maximum range")
    if (
        model["acquisition_cone_degrees"] != EXTRACTED_GEOMETRY["cone_angle"]
        or model["orientation_step_degrees"] != EXTRACTED_GEOMETRY["aim_rotate_step"]
    ):
        raise InputError("Sweeper geometry must identify its selected extraction")
    if (
        actor["team"] != "defense"
        or actor["kind"] != "defense"
        or actor["layer"] != "ground"
        or actor["movement"] != "stationary"
        or actor["damage"] != 0
        or actor["attack_model"]["kind"] != "none"
        or actor["target_layers"] != ["air"]
        or not actor["blocking"]
        or not actor["counts_for_destruction"]
        or actor["spawn_seconds"] != 0
    ):
        raise InputError("Sweeper must be a counted stationary non-damaging defense")
    number(actor["attack_interval_seconds"], "Sweeper interval", EPSILON)
    return model


def attack_locked(actor, time):
    """The caller gates ordinary attacks/movement without changing Freeze."""
    return actor.get("_displacement_pause_until", 0) > time + EPSILON


def _inside_sector(point, origin, angle, cone, minimum_range, maximum_range):
    dx, dy = point[0] - origin[0], point[1] - origin[1]
    distance = hypot(dx, dy)
    if distance < minimum_range - EPSILON or distance > maximum_range + EPSILON:
        return False
    if distance <= EPSILON:
        return minimum_range <= EPSILON
    difference = (degrees(atan2(dy, dx)) - angle + 180) % 360 - 180
    return abs(difference) <= cone / 2 + EPSILON


def _segment_sector_entry(
    start, end, origin, angle, cone, minimum_range, maximum_range
):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = hypot(dx, dy)
    if length <= EPSILON:
        return None
    ux, uy = dx / length, dy / length
    ox, oy = start[0] - origin[0], start[1] - origin[1]
    projection = ox * ux + oy * uy
    candidates = [0.0, length]
    for radius in (minimum_range, maximum_range):
        discriminant = projection * projection - (ox * ox + oy * oy - radius * radius)
        if discriminant >= -EPSILON:
            root = sqrt(max(discriminant, 0))
            candidates.extend((-projection - root, -projection + root))
    for side in (-1, 1):
        edge = radians(angle + side * cone / 2)
        edge_x, edge_y = cos(edge), sin(edge)
        denominator = ux * edge_y - uy * edge_x
        if abs(denominator) > EPSILON:
            candidates.append((oy * edge_x - ox * edge_y) / denominator)
    for distance in sorted(candidates):
        if not -EPSILON <= distance <= length + EPSILON:
            continue
        point = start[0] + ux * distance, start[1] + uy * distance
        if _inside_sector(point, origin, angle, cone, minimum_range, maximum_range):
            return max(0, distance)
    return None


def _clip_air_displacement(actor, direction, distance, width, height):
    """Clip one ray against the legal actor rectangle; ground footprints do not block air."""
    if actor["layer"] != "air" or actor["movement"] != "air":
        raise InputError("This displacement policy cannot push a ground recipient")
    length = hypot(*direction)
    if length <= EPSILON:
        raise InputError("Displacement direction cannot be zero")
    direction = tuple(component / length for component in direction)
    allowed = distance
    for position, extent, size, component in (
        (actor["x"], width, actor["width"], direction[0]),
        (actor["y"], height, actor["height"], direction[1]),
    ):
        if component > EPSILON:
            upper = min(extent - size, extent - EPSILON * 256)
            allowed = min(allowed, max(0, (upper - position) / component))
        elif component < -EPSILON:
            allowed = min(allowed, max(0, -position / component))
    origin = center(actor)
    destination = tuple(origin[index] + direction[index] * allowed for index in (0, 1))
    return destination, allowed


class LinearDisplacement:
    """Finite air motion with separate attack lock, reusable by explicit callers.

    This is a displacement primitive, not a Tornado or Spring Trap model. Other
    mechanics must supply their own activation, trajectories and eligibility.
    """

    def __init__(self, width, height):
        self.width = number(width, "displacement board width", EPSILON)
        self.height = number(height, "displacement board height", EPSILON)
        self.motions = {}

    def start(self, actor, time, direction, model, source_id, trace):
        from .displacements import enqueue_linear_displacement

        number(time, "displacement start", 0)
        number(model["push_distance_tiles"], "displacement distance", EPSILON)
        number(model["push_speed_tiles_per_second"], "displacement speed", EPSILON)
        number(model["recovery_seconds"], "displacement recovery", 0)
        destination, _ = _clip_air_displacement(
            actor, direction, model["push_distance_tiles"], self.width, self.height
        )
        enqueue_linear_displacement(
            self,
            actor,
            time,
            destination,
            model["push_speed_tiles_per_second"],
            model["recovery_seconds"],
            source_id,
            trace,
            requested_distance=model["push_distance_tiles"],
        )

    def forced_motion(self, actor, time):
        motion = self.motions.get(actor["id"])
        if (
            motion is None
            or not _active(actor, time)
            or motion["arrival_seconds"] <= time + EPSILON
        ):
            return None
        return {
            "route": [motion["destination"]],
            "speed_tiles_per_second": motion["speed_tiles_per_second"],
        }

    def advance(self, actors, time, duration, trace):
        number(duration, "forced movement interval", 0)
        end = time + duration
        for actor_id, motion in list(self.motions.items()):
            actor = actors[actor_id]
            if not _active(actor, time):
                self.motions.pop(actor_id)
                actor["_displacement_pause_until"] = 0
                trace.append(
                    {
                        "event": "displacement_cancel",
                        "time_seconds": time,
                        "target": actor_id,
                        "reason": "recipient_inactive",
                    }
                )
                continue
            progress = min(
                1,
                max(0, end - motion["start_seconds"])
                / (motion["arrival_seconds"] - motion["start_seconds"]),
            )
            point = tuple(
                motion["origin"][index]
                + (motion["destination"][index] - motion["origin"][index]) * progress
                for index in (0, 1)
            )
            actor["x"] = point[0] - actor["width"] / 2
            actor["y"] = point[1] - actor["height"] / 2
            actor.pop("_remaining_path", None)
            actor.pop("_path_signature", None)
            if motion["arrival_seconds"] <= end + EPSILON:
                self.motions.pop(actor_id)
                trace.append(
                    {
                        "event": "displacement_arrive",
                        "time_seconds": motion["arrival_seconds"],
                        "source": motion["source"],
                        "target": actor_id,
                        "position": center(actor),
                    }
                )

    def next_boundary(self, actors, time):
        boundaries = [motion["arrival_seconds"] for motion in self.motions.values()]
        boundaries.extend(
            actor.get("_displacement_pause_until", 0) for actor in actors.values()
        )
        future = [value for value in boundaries if value > time + EPSILON]
        return min(future) if future else None


class SweeperCombat:
    """Non-damaging gust packets plus independently advanced forced motion."""

    def __init__(self, actors, width, height):
        self.models = {
            actor["id"]: deepcopy(validate_sweeper_model(actor))
            for actor in actors.values()
            if "sweeper_model" in actor
        }
        self.actors = actors
        self.pending = []
        self.serial = 0
        self.launch_count = {source: 0 for source in self.models}
        self.motion = LinearDisplacement(width, height)

    @staticmethod
    def _eligible(target, source_team, model, time):
        entity_id = target.get("entity_adapter", {}).get("entity")
        return (
            _active(target, time)
            and target["team"] != source_team
            and target["kind"] == "unit"
            and target["layer"] == "air"
            and target["movement"] == "air"
            and untargetable_until(target) <= time + EPSILON
            and entity_id not in model["excluded_entities"]
        )

    @staticmethod
    def _in_cone(target, origin, angle, cone, model):
        return _inside_sector(
            center(target),
            origin,
            angle,
            cone,
            model["minimum_range_tiles"],
            model["maximum_range_tiles"],
        )

    def prepare(self, actors, time, trace):
        for source_id, model in sorted(self.models.items()):
            source = actors[source_id]
            if (
                not _active(source, time)
                or source["frozen_until"] > time + EPSILON
                or source["next_attack"] > time + EPSILON
                or attack_locked(source, time)
            ):
                continue
            origin = center(source)
            candidates = [
                target
                for target in actors.values()
                if self._eligible(target, source["team"], model, time)
                and self._in_cone(
                    target,
                    origin,
                    model["orientation_degrees"],
                    model["acquisition_cone_degrees"],
                    model,
                )
            ]
            if not candidates:
                source["target"] = None
                continue
            primary = min(
                candidates,
                key=lambda target: (
                    hypot(center(target)[0] - origin[0], center(target)[1] - origin[1]),
                    target["id"],
                ),
            )
            point = center(primary)
            angle = (
                degrees(atan2(point[1] - origin[1], point[0] - origin[0]))
                if model["blast_aim"] == "toward_primary"
                else model["orientation_degrees"]
            )
            recipients = []
            for target in sorted(actors.values(), key=lambda item: item["id"]):
                if not self._eligible(
                    target, source["team"], model, time
                ) or not self._in_cone(
                    target, origin, angle, model["blast_cone_degrees"], model
                ):
                    continue
                distance = hypot(
                    center(target)[0] - origin[0], center(target)[1] - origin[1]
                )
                arrival = time + model["launch_delay_seconds"]
                arrival += distance / model["gust_speed_tiles_per_second"]
                self.serial += 1
                packet = {
                    "source": source_id,
                    "source_team": source["team"],
                    "target": target["id"],
                    "primary": primary["id"],
                    "origin": origin,
                    "angle_degrees": angle,
                    "launch_seconds": time,
                    "arrival_seconds": arrival,
                    "model": deepcopy(model),
                }
                heappush(self.pending, (arrival, self.serial, packet))
                recipients.append(target["id"])
            source["target"] = primary["id"]
            source["next_attack"] = time + source[
                "attack_interval_seconds"
            ] / attack_rate(source)
            self.launch_count[source_id] += 1
            trace.append(
                {
                    "event": "sweeper_launch",
                    "time_seconds": time,
                    "source": source_id,
                    "primary": primary["id"],
                    "origin": origin,
                    "angle_degrees": angle,
                    "recipients": recipients,
                    "next_attack_seconds": source["next_attack"],
                }
            )

    def resolve(self, actors, time, trace):
        while self.pending and self.pending[0][0] <= time + EPSILON:
            _, _, packet = heappop(self.pending)
            target = actors[packet["target"]]
            model = packet["model"]
            reason = None
            if not self._eligible(target, packet["source_team"], model, time):
                reason = "recipient_inactive_or_ineligible"
            elif target.get("_tornado_capture_until", 0) > time + EPSILON:
                reason = "tornado_capture_rejects_new_gust"
            elif not self._in_cone(
                target,
                packet["origin"],
                packet["angle_degrees"],
                model["blast_cone_degrees"],
                model,
            ):
                reason = "recipient_left_captured_cone"
            elif (
                target["immune_until"] > time + EPSILON
                and model["damage_immunity_policy"] == "damage_immunity_blocks_push"
            ):
                reason = "damage_immunity_blocks_push"
            elif (
                target["frozen_until"] > time + EPSILON
                and model["recipient_freeze_policy"] == "frozen_targets_ignore_new_push"
            ):
                reason = "frozen_recipient_ignores_new_push"
            if reason is not None:
                trace.append(
                    {
                        "event": "sweeper_miss",
                        "time_seconds": time,
                        "source": packet["source"],
                        "target": target["id"],
                        "reason": reason,
                    }
                )
                continue
            if model["push_direction"] == "away_from_captured_source":
                point = center(target)
                direction = tuple(
                    point[index] - packet["origin"][index] for index in (0, 1)
                )
            else:
                angle = radians(packet["angle_degrees"])
                direction = cos(angle), sin(angle)
            self.motion.start(target, time, direction, model, packet["source"], trace)
            trace.append(
                {
                    "event": "sweeper_impact",
                    "time_seconds": time,
                    "source": packet["source"],
                    "target": target["id"],
                    "damage": 0,
                }
            )

    def forced_motion(self, actor, time):
        return self.motion.forced_motion(actor, time)

    def advance(self, actors, time, duration, trace):
        self.motion.advance(actors, time, duration, trace)

    @staticmethod
    def attack_locked(actor, time):
        return attack_locked(actor, time)

    def next_boundary(self, time):
        boundaries = [self.pending[0][0]] if self.pending else []
        movement_boundary = self.motion.next_boundary(self.actors, time)
        if movement_boundary is not None:
            boundaries.append(movement_boundary)
        for source_id in self.models:
            source = self.actors[source_id]
            if _active(source, time):
                boundaries.extend((source["next_attack"], source["frozen_until"]))
        future = [value for value in boundaries if value > time + EPSILON]
        return min(future) if future else None

    def first_crossing_delay(self, actor, route, time, horizon, effective_speed):
        speed = number(effective_speed, "Sweeper crossing speed", 0)
        if speed <= EPSILON:
            return None
        earliest = None
        for source_id, model in sorted(self.models.items()):
            source = self.actors[source_id]
            if (
                not _active(source, time)
                or source["frozen_until"] > time + EPSILON
                or source["next_attack"] > time + EPSILON
                or not self._eligible(actor, source["team"], model, time)
            ):
                continue
            previous = center(actor)
            traveled = 0.0
            for point in route:
                entry = _segment_sector_entry(
                    previous,
                    point,
                    center(source),
                    model["orientation_degrees"],
                    model["acquisition_cone_degrees"],
                    model["minimum_range_tiles"],
                    model["maximum_range_tiles"],
                )
                if entry is not None:
                    delay = (traveled + entry) / speed
                    if EPSILON < delay <= horizon + EPSILON:
                        earliest = (
                            min(earliest, delay) if earliest is not None else delay
                        )
                    break
                traveled += hypot(point[0] - previous[0], point[1] - previous[1])
                if traveled > speed * horizon:
                    break
                previous = point
        return earliest

    def frame(self, actor, time):
        result = {
            "displacement_pause_until": actor.get("_displacement_pause_until", 0),
            "displacement_attack_locked": attack_locked(actor, time),
        }
        motion = self.forced_motion(actor, time)
        if motion is not None:
            result["forced_motion"] = motion
        if actor["id"] in self.models:
            result["sweeper_launches"] = self.launch_count[actor["id"]]
        return result

    def result(self):
        return {
            "launch_counts": deepcopy(self.launch_count),
            "pending_gusts": [deepcopy(packet) for _, _, packet in self.pending],
            "active_displacements": deepcopy(self.motion.motions),
        }
