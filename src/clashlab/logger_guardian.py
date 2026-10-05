"""Opt-in Logger rolling logs, using the existing Guardian lifecycle.

Pinned quantities supply hit damage, cadence, push distance and post-hit range.
Projectile speed, corridor width, collision sampling, terrain and protection
semantics are unresolved. They must be explicitly experimental; no default
Logger configuration is presented as game fidelity.
"""

from collections import defaultdict
from copy import deepcopy
from heapq import heappop, heappush
from math import hypot

from .buffs import damage_multiplier
from .combat import validate_pattern
from .common import InputError, identifier, number, require
from .damage_receipts import record_damage
from .rates import attack_rate
from .spatial import EPSILON, _active, _eligible, center, target_distance


FIELDS = {
    "source",
    "status",
    "speed_tiles_per_second",
    "corridor_half_width_tiles",
    "collision",
    "trajectory",
    "source_loss",
    "target_motion",
    "pushback",
    "protected_pushback",
    "death",
}


def validate_logger_parameters(parameters):
    if not isinstance(parameters, dict) or set(parameters) != FIELDS:
        raise InputError(
            "Logger needs every explicit experimental trajectory parameter"
        )
    identifier(parameters["source"], "Logger trajectory evidence")
    expected = {
        "status": "experimental_not_replay_calibrated",
        "collision": "launch_sampled_centers_once_per_log",
        "trajectory": "fixed_planar_ray_to_primary_then_snapshot_postHitTileRange",
        "source_loss": "released_logs_persist",
        "target_motion": "hit_if_still_inside_corridor_at_sampled_arrival",
        "pushback": "delegated_shared_clipped_linear_displacement",
        "death": "no_extra_effect_explicit_uncalibrated_hypothesis",
    }
    for field, value in expected.items():
        if parameters[field] != value:
            raise InputError(f"Unsupported Logger {field}")
    if parameters["protected_pushback"] not in {"suppress", "allow"}:
        raise InputError("Logger immunity/pushback interaction must be explicit")
    number(parameters["speed_tiles_per_second"], "Logger log speed", EPSILON)
    number(parameters["corridor_half_width_tiles"], "Logger log half width", EPSILON)


def compile_logger_weapon(actor, instance, entity, row, modifiers, conversion):
    """Invoked from compile_guardian after its common role/home/wall checks."""
    parameters = deepcopy(require(instance, "logger_parameters"))
    validate_logger_parameters(parameters)
    if entity["id"] != "logger" or entity["category"] != "guardian":
        raise InputError("Logger weapon requires its own Guardian identity")
    if instance["attack_parameters"] != {} or any(
        key in instance for key in ("death_parameters", "smasher_parameters")
    ):
        raise InputError("Logger logs cannot borrow radial/death/rage parameters")
    guardian = deepcopy(instance["guardian_parameters"])
    mode = entity["mode"]
    pattern = {
        "kind": "single",
        "source": actor["source"],
        "target_kinds": ["unit"],
        "target_layers": ["ground", "air"],
        "maximum_hp_fraction": 0,
        "projectile": {
            "timing": "instant",
            "delay_seconds": 0,
            "destination": "locked_actor_center_at_impact",
            "hit_radius": 0,
        },
    }
    validate_pattern(pattern)
    # A distinct pattern forces shared dispatch integration. It must never
    # silently fire the validation-only single-target placeholder weapon.
    pattern["kind"] = "logger_rolling_log"
    actor.update(
        kind="unit",
        layer="ground",
        movement="ground",
        blocking=False,
        width=0,
        height=0,
        speed=number(mode["movementSpeed"], "Logger movement", EPSILON)
        / conversion
        * modifiers["movement_speed_multiplier"],
        damage=number(row["stats"]["normal"]["damagePerShot"], "Logger hit", EPSILON)
        * modifiers["damage_multiplier"],
        range=number(mode["range"], "Logger range", EPSILON)
        * modifiers["range_multiplier"],
        attack_interval_seconds=number(mode["attackSpeed"], "Logger cadence", EPSILON)
        * modifiers["attack_interval_multiplier"],
        target_priorities=["unit"],
        target_priority_tiers=[["unit"]],
        target_layers=["ground", "air"],
        wall_behavior=deepcopy(instance["wall_parameters"]),
        buff_class="guardian",
        hazard_class="guardian",
        healing_class="guardian",
        attack_model=pattern,
        guardian_model={
            "entity": "logger",
            "level": instance["level"],
            "parameters": guardian,
            "trigger_radius": number(
                mode["triggerRadius"], "Logger trigger radius", EPSILON
            )
            * guardian["activation"]["trigger_radius_multiplier"],
        },
        logger_model={
            "parameters": parameters,
            "post_hit_range": number(
                row["postHitTileRange"], "Logger post-hit travel", EPSILON
            ),
            "push_distance": number(mode["pushbackRange"], "Logger pushback", EPSILON),
        },
    )
    actor["entity_adapter"].update(
        guardian_parameters=deepcopy(guardian),
        logger_parameters=deepcopy(parameters),
        behavior_verification="experimental_logger_trajectory_not_replay_calibrated",
    )
    return actor


class LoggerCombat:
    """Finite released packets; health settlement and displacement stay shared."""

    def __init__(self, actors, pushback):
        self.actors = actors
        self.models = {}
        self.pending = []
        self.serial = 0
        self.logs_launched = 0
        self.pushback = pushback
        for key, actor in actors.items():
            if "logger_model" not in actor:
                continue
            model = deepcopy(actor["logger_model"])
            if set(model) != {"parameters", "post_hit_range", "push_distance"}:
                raise InputError("Invalid Logger runtime fields")
            validate_logger_parameters(model["parameters"])
            for field in ("post_hit_range", "push_distance"):
                number(model[field], "Logger runtime quantity", EPSILON)
            if (
                actor.get("guardian_model", {}).get("entity") != "logger"
                or actor["team"] != "defense"
                or actor["kind"] != "unit"
                or actor["target_layers"] != ["ground", "air"]
                or actor["attack_model"]["kind"] != "logger_rolling_log"
            ):
                raise InputError(
                    "Logger weapon lacks its linked defensive Guardian role"
                )
            self.models[key] = model
        if self.models and not callable(pushback):
            raise InputError("Logger needs the shared clipped displacement callback")

    @staticmethod
    def _in_corridor(actor, origin, axis, distance, half_width):
        point = center(actor)
        dx, dy = point[0] - origin[0], point[1] - origin[1]
        along = dx * axis[0] + dy * axis[1]
        across = abs(dx * axis[1] - dy * axis[0])
        return (
            -EPSILON <= along <= distance + EPSILON and across <= half_width + EPSILON,
            along,
        )

    def launch(self, actor, primary, actors, time, trace):
        if (
            not _active(actor, time)
            or actor["frozen_until"] > time
            or actor["next_attack"] > time
            or primary is None
            or not _eligible(actor, primary, time)
            or target_distance(center(actor), primary) > actor["range"] + EPSILON
        ):
            return False
        model = self.models[actor["id"]]
        parameters = model["parameters"]
        origin, point = center(actor), center(primary)
        length = hypot(point[0] - origin[0], point[1] - origin[1])
        if length <= EPSILON:
            raise InputError("Logger cannot infer a log direction at zero distance")
        axis = ((point[0] - origin[0]) / length, (point[1] - origin[1]) / length)
        distance = length + model["post_hit_range"]
        amount = actor["damage"] * damage_multiplier(actor)
        self.logs_launched += 1
        for target in sorted(actors.values(), key=lambda value: value["id"]):
            inside, along = self._in_corridor(
                target, origin, axis, distance, parameters["corridor_half_width_tiles"]
            )
            if not inside or not _eligible(actor, target, time):
                continue
            arrival = time + max(0, along) / parameters["speed_tiles_per_second"]
            self.serial += 1
            packet = {
                "source": actor["id"],
                "target": target["id"],
                "amount": amount,
                "origin": origin,
                "axis": axis,
                "distance": distance,
                "parameters": deepcopy(parameters),
                "push_distance": model["push_distance"],
            }
            heappush(self.pending, (arrival, self.serial, packet))
        actor["next_attack"] = time + actor["attack_interval_seconds"] / attack_rate(
            actor
        )
        trace.append(
            {
                "event": "logger_log_launch",
                "time_seconds": time,
                "source": actor["id"],
                "axis": axis,
                "travel_distance": distance,
            }
        )
        return True

    def next_boundary(self, time):
        return (
            self.pending[0][0] if self.pending and self.pending[0][0] > time else None
        )

    def resolve(self, actors, time, trace):
        damage = defaultdict(float)
        while self.pending and self.pending[0][0] <= time:
            arrival, _, packet = heappop(self.pending)
            target = actors[packet["target"]]
            inside, _ = self._in_corridor(
                target,
                packet["origin"],
                packet["axis"],
                packet["distance"],
                packet["parameters"]["corridor_half_width_tiles"],
            )
            if not _active(target, time) or target["team"] != "attack" or not inside:
                continue
            amount = record_damage(
                self,
                target,
                packet["amount"],
                time,
                source_id=packet["source"],
                source_team="defense",
                origin="weapon",
            )
            damage[target["id"]] += amount
            if (
                target["immune_until"] <= time
                or packet["parameters"]["protected_pushback"] == "allow"
            ):
                self.pushback(
                    target,
                    packet["axis"],
                    packet["push_distance"],
                    time,
                    packet["source"],
                    trace,
                )
            trace.append(
                {
                    "event": "logger_log_impact",
                    "time_seconds": arrival,
                    "source": packet["source"],
                    "target": target["id"],
                    "nominal_damage": amount,
                }
            )
        return dict(damage)

    def result(self):
        return {
            "logs_launched": self.logs_launched,
            "pending_impacts": len(self.pending),
            "experimental": True,
        }

    def continuation_reasons(self, time):
        from .battle_termination import continuation_fact

        return [
            continuation_fact(
                "logger_projectile",
                f"{packet['source']}:{serial}",
                (packet["target"],),
                source_team="defense",
                not_before_seconds=arrival,
            )
            for arrival, serial, packet in self.pending
            if arrival > time
        ]
