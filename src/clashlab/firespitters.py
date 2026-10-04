"""Oriented Firespitter bursts with explicit, straight, first-contact bullets.

The publisher confirms oriented acquisition, inaccurate aim and cross-layer
collisions. The pinned catalog supplies per-shot damage and burst quantities;
spread, collision radius, flight speed and burst-gap interpretation are explicit
hypotheses. Displayed DPS is retained as evidence, never substituted for a shot.
"""

from collections import defaultdict
from copy import deepcopy
from math import atan2, cos, degrees, hypot, radians, sin, sqrt

from .buffs import damage_multiplier
from .common import InputError, identifier, integer, number, require
from .rates import attack_rate
from .spatial import EPSILON, _active, _eligible, center
from .sweepers import EXTRACTION_SOURCE, _inside_sector, _segment_sector_entry


PUBLISHER_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/game-updates/"
    "the-town-hall-17-update-is-here-2/"
)
EXTRACTED_GEOMETRY = {
    "data_id": 1000089,
    "cone_angle": 150,
    "aim_rotate_step": 90,
    "attack_range": 1600,
    "attack_speed": 1000,
    "dps_by_level": {1: 411, 2: 438, 3: 456},
}
PATTERN = "firespitter_ballistic_bullet"
FIRESPITTER_RULES = {
    "firespitter_acquisition": "oriented_extracted_cone_live_enemy_unit_centers",
    "firespitter_burst": "declared_catalog_inter_shot_and_post_last_shot_gap",
    "firespitter_aim": "live_primary_center_plus_explicit_per_burst_angle_sequence",
    "firespitter_collision": "moving_bullet_disk_first_live_enemy_point_contact",
    "firespitter_layers": "ground_and_air_collide_independent_of_primary_layer",
    "firespitter_release": "captured_bullets_continue_after_source_or_primary_death",
    "firespitter_phase": "commands_then_shared_launch_phase_then_simultaneous_impacts",
    "firespitter_rate": "shared_attack_work_clock_freeze_pause_and_rate_rescaling",
    "firespitter_damage": "capture_per_shot_damage_and_composed_rage_once_at_launch",
    "firespitter_validation": "spread_and_flight_hypotheses_not_replay_calibrated",
}
PARAMETERS = {
    "source",
    "geometry_basis",
    "orientation_basis",
    "orientation_degrees",
    "damage_basis",
    "burst_timing",
    "targeting",
    "spread",
    "projectile",
    "readiness_policy",
}
TARGETING = {
    "selection": "retain_primary_else_nearest_center_then_instance_id",
    "aim": "live_primary_center_each_shot",
    "loss": "preserve_unfired_burst_until_eligible_primary",
    "exclusion_scope": "acquisition_and_projectile_collision",
}
PROJECTILE_POLICIES = {
    "origin": "source_center_at_launch",
    "collision": "first_live_enemy_unit_point_contact_then_instance_id",
    "damage_immunity": "consume_bullet_without_damage",
    "invisibility": "released_bullets_ignore_acquisition_visibility",
    "buildings": "ignore_structure_footprints",
    "released": "persist_independent_of_source_and_primary",
}
READINESS_POLICY = (
    "shared_attack_work_pauses_during_freeze_or_displacement_"
    "no_target_preserves_burst_source_death_cancels_unfired"
)
BURST_TIMING = "snapshot_attackSpeed_between_shots_timeBetweenBursts_after_last_shot"


def _exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise InputError(f"Firespitter {label} needs every explicit supported field")


def _validate_parameters(parameters, shots):
    _exact(parameters, PARAMETERS, "parameters")
    identifier(parameters["source"], "Firespitter behavior evidence")
    policies = {
        "geometry_basis": "pinned_extraction_degrees_and_hundredths_of_a_tile",
        "orientation_basis": "clockwise_from_positive_x_in_screen_coordinates",
        "damage_basis": "snapshot_damagePerShot_is_one_bullet",
        "burst_timing": BURST_TIMING,
        "readiness_policy": READINESS_POLICY,
    }
    for field, expected in policies.items():
        if parameters[field] != expected:
            raise InputError(f"Firespitter requires explicit {field}: {expected}")
    orientation = number(
        parameters["orientation_degrees"], "Firespitter orientation", 0
    )
    step = EXTRACTED_GEOMETRY["aim_rotate_step"]
    if (
        orientation >= 360
        or abs(orientation / step - round(orientation / step)) > EPSILON
    ):
        raise InputError(
            "Firespitter orientation must select a 90-degree extraction step"
        )
    targeting = parameters["targeting"]
    _exact(targeting, {*TARGETING, "excluded_entities"}, "targeting")
    for field, expected in TARGETING.items():
        if targeting[field] != expected:
            raise InputError(f"Unsupported Firespitter targeting {field}")
    exclusions = targeting["excluded_entities"]
    if (
        not isinstance(exclusions, list)
        or any(not isinstance(value, str) for value in exclusions)
        or len(exclusions) != len(set(exclusions))
    ):
        raise InputError("Firespitter exclusions need an explicit unique entity list")
    for value in exclusions:
        identifier(value, "Firespitter excluded entity")
    spread = parameters["spread"]
    _exact(spread, {"kind", "angle_offsets_degrees", "sequence_policy"}, "spread")
    if (
        spread["kind"] != "explicit_per_burst_angle_sequence"
        or spread["sequence_policy"] != "restart_after_completed_burst"
    ):
        raise InputError(
            "Firespitter spread requires a declared deterministic sequence"
        )
    angles = spread["angle_offsets_degrees"]
    if not isinstance(angles, list) or len(angles) != shots:
        raise InputError(
            "Firespitter spread needs exactly one offset per catalog burst shot"
        )
    for angle in angles:
        number(angle, "Firespitter shot angle offset", -180, 180)
    projectile = parameters["projectile"]
    _exact(
        projectile,
        {
            *PROJECTILE_POLICIES,
            "speed_tiles_per_second",
            "hit_radius_tiles",
            "maximum_travel_range_multiplier",
        },
        "projectile",
    )
    for field, expected in PROJECTILE_POLICIES.items():
        if projectile[field] != expected:
            raise InputError(f"Unsupported Firespitter projectile {field}")
    number(
        projectile["speed_tiles_per_second"], "Firespitter projectile speed", EPSILON
    )
    number(projectile["hit_radius_tiles"], "Firespitter projectile radius", 0)
    number(
        projectile["maximum_travel_range_multiplier"],
        "Firespitter travel multiplier",
        EPSILON,
    )


def compile_firespitter(actor, instance, entity, row, modifiers):
    """Attach this model after shared catalog identity, level and HP validation."""
    if (
        instance["entity"] != "firespitter"
        or entity["id"] != "firespitter"
        or instance["mode"] != "normal"
        or instance["statistics_mode"] != "normal"
        or instance["team"] != "defense"
        or not instance["counts_for_destruction"]
        or instance["spawn_seconds"] != 0
        or instance["attack_parameters"] != {}
        or "wall_parameters" in instance
    ):
        raise InputError(
            "Firespitter requires a counted normal defense and its dedicated bullet parameters"
        )
    if instance["town_hall"] < 17 or row["townHallRequired"] > instance["town_hall"]:
        raise InputError("Firespitter level is unavailable at the declared Town Hall")
    if entity.get("dataId") != EXTRACTED_GEOMETRY["data_id"]:
        raise InputError("Firespitter extraction identity does not match the catalog")
    mode = require(require(entity, "modes"), "normal")
    shots = integer(require(mode, "shotsPerBurst"), "Firespitter shots per burst", 1)
    parameters = require(instance, "firespitter_parameters")
    _validate_parameters(parameters, shots)
    interval = (
        number(mode["attackSpeed"], "Firespitter shot interval", EPSILON)
        * modifiers["attack_interval_multiplier"]
    )
    gap = (
        number(mode["timeBetweenBursts"], "Firespitter post-burst gap", EPSILON)
        * modifiers["attack_interval_multiplier"]
    )
    maximum_range = (
        number(mode["range"], "Firespitter catalog range", EPSILON)
        * modifiers["range_multiplier"]
    )
    stats = require(require(row, "stats"), "normal")
    damage = (
        number(stats["damagePerShot"], "Firespitter bullet damage", EPSILON)
        * modifiers["damage_multiplier"]
    )
    number(interval, "modified Firespitter shot interval", EPSILON)
    number(gap, "modified Firespitter post-burst gap", EPSILON)
    number(damage, "modified Firespitter shot damage", EPSILON)
    number(maximum_range, "modified Firespitter range", EPSILON)
    model = {
        "kind": "firespitter_shot_stream",
        **deepcopy(parameters),
        "shots_per_burst": shots,
        "inter_shot_seconds": interval,
        "post_burst_seconds": gap,
        "acquisition_cone_degrees": EXTRACTED_GEOMETRY["cone_angle"],
        "orientation_step_degrees": EXTRACTED_GEOMETRY["aim_rotate_step"],
        "maximum_travel_distance": maximum_range
        * parameters["projectile"]["maximum_travel_range_multiplier"],
    }
    actor.update(
        kind="defense",
        movement="stationary",
        layer="ground",
        speed=0,
        blocking=True,
        width=3,
        height=3,
        range=maximum_range,
        minimum_range=0,
        damage=damage,
        attack_interval_seconds=interval,
        target_priorities=["unit"],
        target_priority_tiers=[["unit"]],
        target_layers=["ground", "air"],
        attack_model={
            "kind": PATTERN,
            "source": parameters["source"],
            "target_kinds": ["unit"],
            "target_layers": ["ground", "air"],
            "maximum_hp_fraction": 0,
        },
        firespitter_model=model,
    )
    cycle = (shots - 1) * interval + gap
    actor["entity_adapter"].update(
        firespitter_parameters=deepcopy(parameters),
        behavior_verification="declared_shot_stream_not_replay_calibrated",
        bullet_statistic="stats.normal.damagePerShot",
        source_audit={
            "publisher_source": PUBLISHER_SOURCE,
            "extraction_source": EXTRACTION_SOURCE,
            "extracted_geometry": deepcopy(EXTRACTED_GEOMETRY),
            "selected_burst_source": actor["source"],
            "catalog_displayed_dps": stats.get("dps"),
            "extraction_displayed_dps": EXTRACTED_GEOMETRY["dps_by_level"].get(
                row["level"]
            ),
            "extraction_attack_speed_raw": EXTRACTED_GEOMETRY["attack_speed"],
            "selected_inter_shot_seconds": interval,
            "selected_post_last_shot_gap_seconds": gap,
            "selected_uninterrupted_cycle_seconds": cycle,
            "derived_full_hit_dps_before_runtime_buffs": shots * damage / cycle,
            "resolution": "per_shot_catalog_damage_and_explicit_burst_mapping_keep_display_dps_disagreement",
        },
    )
    validate_firespitter_model(actor)
    return actor


def validate_firespitter_pattern(pattern):
    _exact(
        pattern,
        {"kind", "source", "target_kinds", "target_layers", "maximum_hp_fraction"},
        "pattern",
    )
    identifier(pattern["source"], "Firespitter pattern evidence")
    if (
        pattern["kind"] != PATTERN
        or pattern["target_kinds"] != ["unit"]
        or pattern["target_layers"] != ["ground", "air"]
        or pattern["maximum_hp_fraction"] != 0
    ):
        raise InputError(
            "Firespitter needs its dedicated cross-layer ballistic pattern"
        )


def validate_firespitter_model(actor):
    model = require(actor, "firespitter_model")
    _exact(
        model,
        PARAMETERS
        | {
            "kind",
            "shots_per_burst",
            "inter_shot_seconds",
            "post_burst_seconds",
            "acquisition_cone_degrees",
            "orientation_step_degrees",
            "maximum_travel_distance",
        },
        "model",
    )
    shots = integer(model["shots_per_burst"], "Firespitter burst size", 1)
    _validate_parameters({field: model[field] for field in PARAMETERS}, shots)
    for field in (
        "inter_shot_seconds",
        "post_burst_seconds",
        "maximum_travel_distance",
    ):
        number(model[field], f"Firespitter {field}", EPSILON)
    if (
        model["kind"] != "firespitter_shot_stream"
        or model["acquisition_cone_degrees"] != EXTRACTED_GEOMETRY["cone_angle"]
        or model["orientation_step_degrees"] != EXTRACTED_GEOMETRY["aim_rotate_step"]
        or actor["kind"] != "defense"
        or actor["team"] != "defense"
        or actor["movement"] != "stationary"
        or actor["layer"] != "ground"
        or not actor["counts_for_destruction"]
        or actor["spawn_seconds"] != 0
        or actor["minimum_range"] != 0
        or not actor["blocking"]
        or actor["width"] != 3
        or actor["height"] != 3
    ):
        raise InputError(
            "Firespitter runtime requires the explicit counted stationary defense"
        )
    if actor["attack_interval_seconds"] != model["inter_shot_seconds"]:
        raise InputError("Firespitter actor and burst shot intervals disagree")
    validate_firespitter_pattern(actor["attack_model"])
    return model


def _collision_delay(relative_position, relative_velocity, radius, horizon):
    """First contact between a moving point and a circle in relative coordinates."""
    x, y = relative_position
    vx, vy = relative_velocity
    squared_distance = x * x + y * y
    if squared_distance <= radius * radius + EPSILON * EPSILON:
        return 0.0
    speed_squared = vx * vx + vy * vy
    if speed_squared <= EPSILON * EPSILON:
        return None
    projection = x * vx + y * vy
    discriminant = projection * projection - speed_squared * (
        squared_distance - radius * radius
    )
    if discriminant < -EPSILON:
        return None
    contact = (-projection - sqrt(max(discriminant, 0))) / speed_squared
    if contact < -EPSILON or contact > horizon + EPSILON:
        return None
    return max(0.0, contact)


def _position(packet, time):
    elapsed = max(0, time - packet["launch_seconds"])
    return tuple(
        packet["origin"][index] + packet["velocity"][index] * elapsed
        for index in (0, 1)
    )


class FirespitterCombat:
    """Own burst launches and live bullet contacts using the shared attack clock.

    The core calls resolve with other post-launch impacts, routes modeled actors
    through select_target/launch, and includes next_boundary plus
    first_crossing_delay for ordinary and forced movement routes. Prepare runs
    before launches and after health settlement to cancel unreleased shots.
    """

    def __init__(self, actors, ordinary_select_target):
        for actor in actors.values():
            if (actor.get("attack_model", {}).get("kind") == PATTERN) != (
                "firespitter_model" in actor
            ):
                raise InputError(
                    "Firespitter pattern and dedicated model must be bound together"
                )
        self.actors = actors
        self.ordinary_select_target = ordinary_select_target
        self.models = {
            key: deepcopy(validate_firespitter_model(actor))
            for key, actor in actors.items()
            if "firespitter_model" in actor
        }
        self.states = {
            key: {
                "next_shot_index": 0,
                "burst_number": 0,
                "launched_shots": 0,
                "cancelled_shots": 0,
                "destroyed": False,
            }
            for key in self.models
        }
        self.bullets = {}
        self.serial = 0
        self.hit_count = 0
        self.miss_count = 0

    def prepare(self, actors, time, trace):
        for key, model in self.models.items():
            actor = actors[key]
            state = self.states[key]
            if actor["hp"] <= 0 and not state["destroyed"]:
                state["destroyed"] = True
                index = state["next_shot_index"]
                remaining = model["shots_per_burst"] - index if index else 0
                state["cancelled_shots"] += remaining
                state["next_shot_index"] = 0
                actor["target"] = None
                trace.append(
                    {
                        "event": "firespitter_destroyed",
                        "time_seconds": time,
                        "source": key,
                        "cancelled_unreleased_shots": remaining,
                    }
                )

    def _acquirable(self, source, target, time):
        model = self.models[source["id"]]
        return (
            _eligible(source, target, time)
            and target.get("entity_adapter", {}).get("entity")
            not in model["targeting"]["excluded_entities"]
            and _inside_sector(
                center(target),
                center(source),
                model["orientation_degrees"],
                model["acquisition_cone_degrees"],
                0,
                source["range"],
            )
        )

    def select_target(self, actor, actors, time, blocked, width, height):
        if actor["id"] not in self.models:
            return self.ordinary_select_target(
                actor, actors, time, blocked, width, height
            )
        if not _active(actor, time):
            actor["target"] = None
            return None, None
        target = actors.get(actor["target"])
        if target is None or not self._acquirable(actor, target, time):
            origin = center(actor)
            candidates = [
                (
                    hypot(
                        center(candidate)[0] - origin[0],
                        center(candidate)[1] - origin[1],
                    ),
                    candidate["id"],
                    candidate,
                )
                for candidate in actors.values()
                if self._acquirable(actor, candidate, time)
            ]
            target = (
                min(candidates, key=lambda value: value[:2])[-1] if candidates else None
            )
        actor["target"] = target["id"] if target is not None else None
        return (target, []) if target is not None else (None, None)

    def launch(self, actor, primary, actors, time, trace):
        if (
            not _active(actor, time)
            or actor["frozen_until"] > time + EPSILON
            or actor.get("_displacement_pause_until", 0) > time + EPSILON
            or actor["next_attack"] > time + EPSILON
            or primary is None
            or not self._acquirable(actor, primary, time)
        ):
            return False
        model = self.models[actor["id"]]
        state = self.states[actor["id"]]
        index = state["next_shot_index"]
        if index == 0:
            state["burst_number"] += 1
        origin = center(actor)
        aim = center(primary)
        angle = (
            degrees(atan2(aim[1] - origin[1], aim[0] - origin[0]))
            + model["spread"]["angle_offsets_degrees"][index]
        )
        speed = model["projectile"]["speed_tiles_per_second"]
        self.serial += 1
        bullet_id = f"{actor['id']}:bullet:{self.serial}"
        packet = {
            "id": bullet_id,
            "source": actor["id"],
            "source_team": actor["team"],
            "primary": primary["id"],
            "launch_seconds": time,
            "origin": origin,
            "aim_position": aim,
            "velocity": (cos(radians(angle)) * speed, sin(radians(angle)) * speed),
            "angle_degrees": angle,
            "radius": model["projectile"]["hit_radius_tiles"],
            "maximum_travel_distance": model["maximum_travel_distance"],
            "expires_seconds": time + model["maximum_travel_distance"] / speed,
            "damage": actor["damage"] * damage_multiplier(actor),
            "target_layers": list(actor["target_layers"]),
            "excluded_entities": list(model["targeting"]["excluded_entities"]),
            "projectile_policy": deepcopy(model["projectile"]),
        }
        self.bullets[bullet_id] = packet
        state["launched_shots"] += 1
        state["next_shot_index"] = (index + 1) % model["shots_per_burst"]
        interval = (
            model["inter_shot_seconds"]
            if state["next_shot_index"]
            else model["post_burst_seconds"]
        )
        actor["next_attack"] = time + interval / attack_rate(actor)
        trace.append(
            {
                "event": "firespitter_launch",
                "time_seconds": time,
                "source": actor["id"],
                "target": primary["id"],
                "bullet_id": bullet_id,
                "burst_number": state["burst_number"],
                "shot_number": index + 1,
                "damage": packet["damage"],
                "angle_degrees": angle,
                "expires_seconds": packet["expires_seconds"],
            }
        )
        return True

    @staticmethod
    def _collidable(packet, actor, time):
        return (
            _active(actor, time)
            and actor["team"] != packet["source_team"]
            and actor["kind"] == "unit"
            and actor["layer"] in packet["target_layers"]
            and actor.get("entity_adapter", {}).get("entity")
            not in packet["excluded_entities"]
        )

    def resolve(self, actors, time, trace):
        from .damage_receipts import record_damage

        damage = defaultdict(float)
        for bullet_id, packet in list(self.bullets.items()):
            point = _position(packet, time)
            choices = (
                [
                    actor
                    for actor in actors.values()
                    if self._collidable(packet, actor, time)
                    and hypot(center(actor)[0] - point[0], center(actor)[1] - point[1])
                    <= packet["radius"] + EPSILON
                ]
                if time <= packet["expires_seconds"] + EPSILON
                else []
            )
            if choices:
                target = min(choices, key=lambda actor: actor["id"])
                protected = target["immune_until"] > time + EPSILON
                resolved = record_damage(
                    self,
                    target,
                    packet["damage"],
                    time,
                    source_id=packet["source"],
                    source_actor_id=packet["source"],
                    source_team=packet["source_team"],
                    origin="weapon",
                )
                if resolved > 0:
                    damage[target["id"]] += resolved
                trace.append(
                    {
                        "event": "firespitter_impact",
                        "time_seconds": time,
                        "source": packet["source"],
                        "target": target["id"],
                        "primary": packet["primary"],
                        "bullet_id": bullet_id,
                        "position": point,
                        "damage": packet["damage"],
                        "protected": protected,
                    }
                )
                self.hit_count += 1
                self.bullets.pop(bullet_id)
            elif time >= packet["expires_seconds"] - EPSILON:
                trace.append(
                    {
                        "event": "firespitter_miss",
                        "time_seconds": time,
                        "source": packet["source"],
                        "bullet_id": bullet_id,
                    }
                )
                self.miss_count += 1
                self.bullets.pop(bullet_id)
        return damage

    def next_boundary(self, time):
        values = []
        for packet in self.bullets.values():
            values.append(packet["expires_seconds"])
            point = _position(packet, time)
            horizon = max(0, packet["expires_seconds"] - time)
            for actor in self.actors.values():
                if not self._collidable(packet, actor, time):
                    continue
                position = center(actor)
                delay = _collision_delay(
                    (point[0] - position[0], point[1] - position[1]),
                    packet["velocity"],
                    packet["radius"],
                    horizon,
                )
                if delay is not None and delay > EPSILON:
                    values.append(time + delay)
        future = [value for value in values if value > time + EPSILON]
        return min(future) if future else None

    def first_crossing_delay(self, actor, route, time, horizon, effective_speed):
        if not _active(actor, time) or not route or horizon <= EPSILON:
            return None
        speed = number(effective_speed, "Firespitter crossing speed", 0)
        if speed <= EPSILON:
            return None
        earliest = None
        elapsed = 0.0
        previous = center(actor)
        for point in route:
            length = hypot(point[0] - previous[0], point[1] - previous[1])
            if length <= EPSILON:
                previous = point
                continue
            duration = min(length / speed, horizon - elapsed)
            velocity = (
                (point[0] - previous[0]) / length * speed,
                (point[1] - previous[1]) / length * speed,
            )
            endpoint = tuple(
                previous[index] + velocity[index] * duration for index in (0, 1)
            )
            for source_id, model in self.models.items():
                source = self.actors[source_id]
                if not _active(source, time) or not _eligible(source, actor, time):
                    continue
                if (
                    actor.get("entity_adapter", {}).get("entity")
                    in model["targeting"]["excluded_entities"]
                ):
                    continue
                contact = _segment_sector_entry(
                    previous,
                    endpoint,
                    center(source),
                    model["orientation_degrees"],
                    model["acquisition_cone_degrees"],
                    0,
                    source["range"],
                )
                if contact is not None:
                    delay = elapsed + contact / speed
                    if delay > EPSILON:
                        earliest = (
                            min(earliest, delay) if earliest is not None else delay
                        )
            for packet in self.bullets.values():
                start = time + elapsed
                if not self._collidable(packet, actor, start):
                    continue
                bullet = _position(packet, start)
                remaining = min(duration, packet["expires_seconds"] - start)
                if remaining < -EPSILON:
                    continue
                contact = _collision_delay(
                    (bullet[0] - previous[0], bullet[1] - previous[1]),
                    (
                        packet["velocity"][0] - velocity[0],
                        packet["velocity"][1] - velocity[1],
                    ),
                    packet["radius"],
                    max(0, remaining),
                )
                if contact is not None:
                    delay = elapsed + contact
                    if delay > EPSILON:
                        earliest = (
                            min(earliest, delay) if earliest is not None else delay
                        )
            elapsed += duration
            if elapsed >= horizon - EPSILON:
                break
            previous = point
        return earliest

    def frame(self, actor):
        if actor["id"] not in self.states:
            return {}
        return {"firespitter_state": deepcopy(self.states[actor["id"]])}

    def result(self):
        return {
            "states": deepcopy(self.states),
            "pending_bullets": deepcopy(list(self.bullets.values())),
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "limitations": [
                "Spread angles are explicitly supplied per burst, not a verified game RNG distribution",
                "Bullet speed, radius, maximum travel and burst-gap interpretation remain declared hypotheses",
                "Unit centers are collision points; structure occlusion is explicitly ignored",
                "Catalog and extraction displayed DPS disagree and do not override per-shot damage",
            ],
            "full_game_prediction": False,
        }
