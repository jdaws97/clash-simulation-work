"""Explicit Hidden Tesla reveal, readiness and footprint hypotheses.

The ordinary defense adapter owns weapon and HP statistics. This module adds a
lifecycle to that actor without replacing its damage pattern or its identity in
destruction accounting. Dormant actors remain alive; the kernel must honor
``_tesla_hidden`` when resolving damage as well as this selector's firing gate.
"""

from copy import deepcopy
from math import floor, hypot

from .common import InputError, identifier, number, require
from .hit_status import RULES as HIT_RULES
from .rates import attack_rate, movement_speed
from .spatial import EPSILON, _active, center
from .traps import IMPACT_KINDS, segment_circle_entry


RULESET = "spatial-hidden-tesla-hit-status-kernel-v13"
SCOPE = "hidden_tesla_hit_status_traps_heroes_sector_without_pets_or_defending_troops"
RULES = {
    **HIT_RULES,
    "tesla_trigger": "eligible_enemy_center_entry_or_declared_destruction_fraction",
    "tesla_trigger_tie": "proximity_before_threshold_distance_then_instance_id",
    "tesla_reveal": "once_after_explicit_delay_even_if_trigger_leaves_or_dies",
    "tesla_hidden": "alive_counted_untargetable_no_weapon_and_damage_immune",
    "tesla_status": "explicit_status_commands_follow_ordinary_kernel_rules",
    "tesla_footprint": "explicit_always_blocking_or_reveal_blocking_reject_overlap",
    "tesla_readiness": "declared_attack_work_after_reveal_and_current_freeze",
    "tesla_phase": "after_health_settlement_before_targeting_and_movement",
    "tesla_path_entry": "split_at_first_circle_entry_along_declared_polyline",
    "tesla_destruction_denominator": "initial_counted_friendly_structures_excluding_walls_and_traps",
}
FOOTPRINT_POLICIES = {
    "always_blocking_hypothesis",
    "blocks_on_reveal_reject_ground_overlap",
}
PARAMETERS = {
    "source",
    "initial_state",
    "trigger_radius_multiplier",
    "trigger_layers",
    "excluded_trigger_entities",
    "destruction_threshold_fraction",
    "reveal_delay_seconds",
    "first_attack_delay_seconds",
    "footprint_policy",
    "dormant_damage_policy",
    "reveal_clock_policy",
    "readiness_policy",
}
MODEL_FIELDS = (PARAMETERS - {"trigger_radius_multiplier"}) | {
    "kind",
    "trigger_radius",
}


def _validate_parameters(parameters, radius_field):
    identifier(parameters["source"], "Tesla lifecycle evidence")
    if parameters["initial_state"] not in {"dormant", "revealed"}:
        raise InputError("Tesla initial state must be dormant or revealed")
    number(parameters[radius_field], "Tesla trigger radius or scale", 0)
    number(
        parameters["destruction_threshold_fraction"],
        "Tesla destruction threshold",
        EPSILON,
        1,
    )
    for field in ("reveal_delay_seconds", "first_attack_delay_seconds"):
        number(parameters[field], field, 0)
    layers = parameters["trigger_layers"]
    if (
        not isinstance(layers, list)
        or not layers
        or any(
            not isinstance(layer, str) or layer not in {"ground", "air"}
            for layer in layers
        )
        or len(layers) != len(set(layers))
    ):
        raise InputError("Tesla trigger layers must be a unique ground/air list")
    excluded = parameters["excluded_trigger_entities"]
    if not isinstance(excluded, list):
        raise InputError("Tesla trigger exclusions must be an explicit list")
    for entity_id in excluded:
        identifier(entity_id, "Tesla excluded trigger entity")
    if len(excluded) != len(set(excluded)):
        raise InputError("Tesla trigger exclusions must be unique")
    if parameters["footprint_policy"] not in FOOTPRINT_POLICIES:
        raise InputError("Tesla footprint behavior must use an explicit policy")
    policies = {
        "dormant_damage_policy": "immune_until_revealed",
        "reveal_clock_policy": "continues_while_frozen",
        "readiness_policy": "attack_work_after_reveal_and_current_freeze",
    }
    for field, expected in policies.items():
        if parameters[field] != expected:
            raise InputError(f"Unsupported Tesla {field}")


def compile_hidden_tesla(actor, instance, entity):
    """Attach lifecycle after shared normal-defense weapon compilation.

    The shared adapter must already have consumed Hidden Tesla's level HP,
    normal damagePerShot, attackSpeed, range, footprint and explicit projectile.
    Only the catalog triggerRange and lifecycle assumptions are consumed here.
    """
    if (
        entity["id"] != "hidden-tesla"
        or instance["entity"] != "hidden-tesla"
        or instance["mode"] != "normal"
        or instance["statistics_mode"] != "normal"
        or actor["attack_model"]["kind"] != "single"
        or actor["first_attack_seconds"] != 0
        or "wall_parameters" in instance
    ):
        raise InputError(
            "Hidden Tesla needs a normal single weapon and lifecycle readiness"
        )
    parameters = require(instance, "tesla_parameters")
    if not isinstance(parameters, dict) or set(parameters) != PARAMETERS:
        raise InputError("Every Tesla lifecycle parameter must be explicit")
    _validate_parameters(parameters, "trigger_radius_multiplier")
    mode = require(require(entity, "modes"), "normal")
    actor["tesla_model"] = {
        key: deepcopy(value)
        for key, value in parameters.items()
        if key != "trigger_radius_multiplier"
    }
    actor["tesla_model"].update(
        kind="hidden_tesla",
        trigger_radius=number(
            require(mode, "triggerRange"), "catalog Tesla trigger range", 0
        )
        * parameters["trigger_radius_multiplier"],
    )
    validate_tesla_model(actor)
    actor["entity_adapter"]["tesla_parameters"] = deepcopy(parameters)
    actor["entity_adapter"]["trigger_statistic"] = "modes.normal.triggerRange"
    actor["entity_adapter"][
        "behavior_verification"
    ] = "explicit_Tesla_lifecycle_hypothesis_not_replay_validated"
    return actor


def validate_tesla_model(actor):
    model = require(actor, "tesla_model")
    if (
        not isinstance(model, dict)
        or set(model) != MODEL_FIELDS
        or model["kind"] != "hidden_tesla"
    ):
        raise InputError("Tesla behavior must declare its complete lifecycle")
    _validate_parameters(model, "trigger_radius")
    if (
        actor["team"] != "defense"
        or actor["kind"] != "defense"
        or actor["layer"] != "ground"
        or actor["movement"] != "stationary"
        or not actor["blocking"]
        or not actor["counts_for_destruction"]
        or actor["spawn_seconds"] != 0
        or actor["first_attack_seconds"] != 0
    ):
        raise InputError(
            "Tesla must be a counted defense with a reserved initial footprint"
        )
    return model


class TeslaCombat:
    """Keep a single counted actor through dormant, revealing and revealed states.

    Initialize after layout/trap validation so every Tesla's reserved footprint
    participates in collision checks, but before commands and position checks.
    Run prepare after commands and health/death settlement. Wrap target selection
    and include next_boundary and first_crossing_delay in the spatial solver.
    """

    def __init__(self, actors, select_target):
        self.actors = actors
        self.models = {
            actor["id"]: deepcopy(validate_tesla_model(actor))
            for actor in actors.values()
            if "tesla_model" in actor
        }
        self.ordinary_select_target = select_target
        self.states = {}
        self.counted = {}
        for actor_id, model in self.models.items():
            actor = actors[actor_id]
            self.states[actor_id] = {
                "phase": "dormant",
                "triggered_at": None,
                "reveal_at": None,
                "revealed_at": None,
                "reason": None,
                "trigger_id": None,
                "destroyed_at": None,
            }
            self.counted[actor_id] = tuple(
                key
                for key, item in actors.items()
                if item["team"] == actor["team"]
                and item["counts_for_destruction"]
                and item["kind"] in {"building", "defense"}
                and item["movement"] == "stationary"
                and item.get("entity_adapter", {}).get("entity") not in IMPACT_KINDS
            )
            hidden = model["initial_state"] == "dormant"
            actor["_tesla_hidden"] = hidden
            actor["_untargetable_until"] = float("inf") if hidden else 0
            if (
                hidden
                and model["footprint_policy"]
                == "blocks_on_reveal_reject_ground_overlap"
            ):
                actor["blocking"] = False

    def eligible_trigger(self, tesla_id, actor, time):
        model = self.models[tesla_id]
        tesla = self.actors[tesla_id]
        return (
            _active(actor, time)
            and actor["kind"] == "unit"
            and actor["team"] != tesla["team"]
            and actor["layer"] in model["trigger_layers"]
            and actor.get("entity_adapter", {}).get("entity")
            not in model["excluded_trigger_entities"]
        )

    def _trigger(self, actor_id, actors, time):
        model = self.models[actor_id]
        if model["initial_state"] == "revealed":
            return "declared_initial_revealed_state", None
        origin = center(actors[actor_id])
        candidates = []
        for actor in actors.values():
            if not self.eligible_trigger(actor_id, actor, time):
                continue
            position = center(actor)
            distance = hypot(position[0] - origin[0], position[1] - origin[1])
            if distance <= model["trigger_radius"] + EPSILON:
                candidates.append((distance, actor["id"]))
        if candidates:
            return "eligible_enemy_proximity", min(candidates)[1]
        if self.destruction_fraction(actor_id, actors) >= (
            model["destruction_threshold_fraction"] - EPSILON
        ):
            return "declared_destruction_threshold", None
        return None, None

    def destruction_fraction(self, actor_id, actors):
        counted = self.counted[actor_id]
        return sum(actors[key]["death_time"] is not None for key in counted) / len(
            counted
        )

    @staticmethod
    def _reject_ground_overlap(tesla, actors, time):
        for actor in actors.values():
            if not _active(actor, time) or actor["movement"] != "ground":
                continue
            position = center(actor)
            x, y = floor(position[0]), floor(position[1])
            if (
                tesla["x"] <= x < tesla["x"] + tesla["width"]
                and tesla["y"] <= y < tesla["y"] + tesla["height"]
            ):
                raise InputError(
                    f"Tesla reveal would overlap ground unit {actor['id']}: "
                    "declared policy rejects overlap; displacement is unsupported"
                )

    def prepare(self, actors, time, trace):
        for actor_id, model in sorted(self.models.items()):
            actor = actors[actor_id]
            state = self.states[actor_id]
            if actor["death_time"] is not None:
                state["phase"] = "destroyed"
                state["destroyed_at"] = actor["death_time"]
                continue
            if not _active(actor, time) or state["revealed_at"] is not None:
                continue
            if state["triggered_at"] is None:
                reason, trigger_id = self._trigger(actor_id, actors, time)
                if reason is None:
                    continue
                delay = (
                    0
                    if model["initial_state"] == "revealed"
                    else model["reveal_delay_seconds"]
                )
                state.update(
                    phase="revealing",
                    triggered_at=time,
                    reveal_at=time + delay,
                    reason=reason,
                    trigger_id=trigger_id,
                )
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "tesla_trigger",
                        "source": actor_id,
                        "reason": reason,
                        "trigger_id": trigger_id,
                        "reveal_seconds": state["reveal_at"],
                        "destruction_fraction": self.destruction_fraction(
                            actor_id, actors
                        ),
                    }
                )
            if state["reveal_at"] > time + EPSILON:
                continue
            self._reject_ground_overlap(actor, actors, time)
            actor["blocking"] = True
            actor["_tesla_hidden"] = False
            actor["_untargetable_until"] = 0
            actor["next_attack"] = max(time, actor["frozen_until"]) + model[
                "first_attack_delay_seconds"
            ] / attack_rate(actor)
            state.update(phase="revealed", revealed_at=time)
            trace.append(
                {
                    "time_seconds": time,
                    "event": "tesla_reveal",
                    "source": actor_id,
                    "reason": state["reason"],
                    "trigger_id": state["trigger_id"],
                    "weapon_ready_seconds": actor["next_attack"],
                    "footprint_policy": model["footprint_policy"],
                }
            )

    def select_target(self, actor, actors, time, blocked, width, height):
        if actor["id"] in self.models and actor["_tesla_hidden"]:
            actor["target"] = None
            return None, None
        return self.ordinary_select_target(actor, actors, time, blocked, width, height)

    def next_boundary(self, time):
        pending = [
            state["reveal_at"]
            for state in self.states.values()
            if state["phase"] == "revealing" and state["reveal_at"] > time + EPSILON
        ]
        return min(pending) if pending else None

    def first_crossing_delay(self, actor, route, time, horizon, effective_speed=None):
        speed = movement_speed(actor) if effective_speed is None else effective_speed
        if speed <= EPSILON or (
            effective_speed is None and actor["frozen_until"] > time + EPSILON
        ):
            return None
        earliest = None
        for tesla_id, model in self.models.items():
            if (
                self.states[tesla_id]["phase"] != "dormant"
                or not _active(self.actors[tesla_id], time)
                or not self.eligible_trigger(tesla_id, actor, time)
            ):
                continue
            previous = center(actor)
            distance = 0.0
            for point in route:
                entry = segment_circle_entry(
                    previous,
                    point,
                    center(self.actors[tesla_id]),
                    model["trigger_radius"],
                )
                if entry is not None:
                    delay = (distance + entry) / speed
                    if EPSILON < delay <= horizon + EPSILON:
                        earliest = delay if earliest is None else min(earliest, delay)
                    break
                distance += hypot(point[0] - previous[0], point[1] - previous[1])
                if distance > speed * horizon:
                    break
                previous = point
        return earliest

    def frame(self, actor):
        if actor["id"] not in self.states:
            return {}
        state = self.states[actor["id"]]
        return {
            "tesla_phase": state["phase"],
            "tesla_hidden": actor["_tesla_hidden"],
            "tesla_reveal_reason": state["reason"],
        }

    def result(self):
        return {
            "states": deepcopy(self.states),
            "destruction_denominator_ids": {
                key: list(value) for key, value in self.counted.items()
            },
            "full_game_prediction": False,
        }
