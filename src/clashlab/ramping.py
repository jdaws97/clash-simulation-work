"""Explicit lock-dependent weapons for conditional support/wall encounters.

Stage timings and interruption policies are caller-supplied evidence or named
hypotheses. This kernel does not establish current Clash Inferno behavior.
"""

from copy import deepcopy

from .common import InputError, identifier, number, require
from .healing import SUPPORT_RULES
from .spatial import EPSILON, _active, center, target_distance


RULESET = "spatial-lock-ramp-support-kernel-v5"
RAMP_RULES = {
    **SUPPORT_RULES,
    "weapon_ramp": "explicit_piecewise_lock_time_damage_at_launch",
    "ramp_target_loss": "reset_on_target_change_or_loss_of_eligible_range",
    "ramp_interruptions": "explicit_freeze_and_target_protection_policies",
    "ramp_health_phase": "launched_damage_fixed_before_simultaneous_impacts",
}


def validate_ramp(actor):
    model = require(actor, "ramp_model")
    identifier(require(model, "source"), "ramp behavior evidence")
    if (
        actor["movement"] != "stationary"
        or actor["kind"] != "defense"
        or actor["attack_model"]["kind"] != "single"
    ):
        raise InputError(
            "Lock ramps currently require a stationary single-target defense"
        )
    if require(model, "clock_start") not in {
        "first_weapon_launch",
        "eligible_in_range_lock",
    }:
        raise InputError("Ramp clock origin must be explicit")
    if require(model, "freeze_policy") not in {"reset", "pause"}:
        raise InputError("Freeze must explicitly reset or pause the ramp")
    if require(model, "protected_target_policy") not in {"continue", "pause", "reset"}:
        raise InputError("Protected-target ramp policy must be explicit")
    stages = require(model, "stages")
    if not isinstance(stages, list) or not stages:
        raise InputError("Ramp needs explicit timed damage stages")
    previous_time = -1
    previous_damage = 0
    for stage in stages:
        after = number(require(stage, "after_seconds"), "ramp stage time", 0)
        damage = number(require(stage, "damage_per_hit"), "ramp hit damage", EPSILON)
        identifier(require(stage, "source"), "ramp stage evidence")
        if after <= previous_time or damage < previous_damage:
            raise InputError("Ramp times must increase and damage cannot decrease")
        previous_time = after
        previous_damage = damage
    if (
        stages[0]["after_seconds"] != 0
        or abs(stages[0]["damage_per_hit"] - actor["damage"]) > EPSILON
    ):
        raise InputError("First ramp stage must begin at zero and match initial damage")
    return model


class RampCombat:
    """Maintain per-instance locks without changing the underlying hit clock."""

    def __init__(self, actors):
        self.models = {}
        self.states = {}
        for actor in actors.values():
            if "ramp_model" not in actor:
                continue
            self.models[actor["id"]] = deepcopy(validate_ramp(actor))
            self.states[actor["id"]] = {
                "target": None,
                "elapsed": 0.0,
                "last_time": 0.0,
                "running": False,
                "started": False,
                "interruption": None,
            }

    def prepare(self, actors, time, select_target, blocked, width, height, trace):
        for actor_id, model in self.models.items():
            actor = actors[actor_id]
            state = self.states[actor_id]
            if state["running"]:
                state["elapsed"] += time - state["last_time"]
            state["last_time"] = time
            target, _ = select_target(actor, actors, time, blocked, width, height)
            in_range = (
                _active(actor, time)
                and target is not None
                and actor["_minimum_range"] - EPSILON
                <= target_distance(center(actor), target)
                <= actor["range"] + EPSILON
            )
            target_id = target["id"] if in_range else None
            reason = None
            reset = False
            if target_id != state["target"]:
                reason = "target_changed" if target_id is not None else "lock_lost"
                reset = True
            state["target"] = target_id
            frozen = actor["frozen_until"] > time + EPSILON
            protected = in_range and target["immune_until"] > time + EPSILON
            interruption = "freeze" if frozen else "protection" if protected else None
            policy = (
                model["freeze_policy"]
                if frozen
                else model["protected_target_policy"] if protected else "continue"
            )
            if interruption is not None and policy == "reset":
                if state["interruption"] != interruption or state["elapsed"] > EPSILON:
                    reason = interruption
                reset = True
            if reset:
                state["elapsed"] = 0.0
                state["started"] = False
                if reason is not None:
                    trace.append(
                        {
                            "time_seconds": time,
                            "event": "weapon_ramp_reset",
                            "source": actor_id,
                            "target": target_id,
                            "reason": reason,
                        }
                    )
            interrupted = interruption is not None and policy in {"pause", "reset"}
            if (
                in_range
                and not interrupted
                and model["clock_start"] == "eligible_in_range_lock"
            ):
                state["started"] = True
            state["running"] = in_range and not interrupted and state["started"]
            state["interruption"] = interruption

    def launch_damage(self, actor_id):
        model = self.models[actor_id]
        state = self.states[actor_id]
        if state["interruption"] is None or (
            state["interruption"] == "protection"
            and model["protected_target_policy"] == "continue"
        ):
            state["started"] = True
            state["running"] = True
        selected = 0
        for index, stage in enumerate(model["stages"]):
            if stage["after_seconds"] <= state["elapsed"] + EPSILON:
                selected = index
        return model["stages"][selected]["damage_per_hit"], {
            "lock_seconds": state["elapsed"],
            "stage": selected,
            "target": state["target"],
        }

    def next_boundary(self, time):
        boundaries = []
        for actor_id, state in self.states.items():
            if not state["running"]:
                continue
            for stage in self.models[actor_id]["stages"]:
                remaining = stage["after_seconds"] - state["elapsed"]
                if remaining > EPSILON:
                    boundaries.append(time + remaining)
                    break
        return min(boundaries) if boundaries else None

    def frame(self, actor_id):
        if actor_id not in self.states:
            return {}
        state = self.states[actor_id]
        return {
            "weapon_target": state["target"],
            "weapon_lock_seconds": state["elapsed"],
            "weapon_ramp_running": state["running"],
        }

    def result(self):
        return {"models": deepcopy(self.models), "states": deepcopy(self.states)}
