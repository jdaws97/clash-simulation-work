"""Permanent home-village defense variants; no builder-base or seasonal fallback.

The geared Cannon's four-shot statistics are pinned. The ambiguous burst gap
interpretation remains an explicit experimental choice, as with Multi-Gear.
"""

from copy import deepcopy

from .common import InputError, identifier, integer, number, require
from .combat import validate_pattern
from .rates import attack_rate
from .spatial import EPSILON, _active, _eligible, center, target_distance


BURST_TIMINGS = {
    "snapshot_timeBetweenBursts_is_post_last_shot_gap",
    "snapshot_timeBetweenBursts_is_extra_after_one_inter_shot_interval",
}


def validate_geared_cannon_parameters(parameters):
    if not isinstance(parameters, dict) or set(parameters) != {
        "source",
        "status",
        "burst_timing",
        "targeting",
        "freeze",
    }:
        raise InputError(
            "Geared Cannon requires a complete experimental burst contract"
        )
    identifier(parameters["source"], "Cannon burst evidence")
    if (
        parameters["status"] != "experimental_not_replay_calibrated"
        or parameters["burst_timing"] not in BURST_TIMINGS
        or parameters["targeting"] != "retain_eligible_primary_reacquire_per_shot"
        or parameters["freeze"] != "pause_remaining_shot_clock_preserve_burst_index"
    ):
        raise InputError("Unsupported Cannon burst hypothesis")


def compile_geared_cannon(actor, instance, entity, row, modifiers):
    """Binding hook for adapters.py; owns statistics and burst contract only."""
    if (
        entity["id"] != "cannon"
        or instance["entity"] != "cannon"
        or instance["mode"] != "gearedUpBurst"
        or instance["statistics_mode"] != "gearedUpBurst"
        or instance["team"] != "defense"
        or actor["team"] != "defense"
        or not instance["counts_for_destruction"]
        or instance["spawn_seconds"] != 0
        or instance["supercharge"] is not False
        or row["level"] != instance["level"]
        or row["townHallRequired"] > instance["town_hall"]
    ):
        raise InputError(
            "Geared Cannon requires a counted unlocked home-village defense"
        )
    mode = entity["modes"]["gearedUpBurst"]
    if instance["level"] < mode["availableFromLevel"]:
        raise InputError("Cannon gear-up is locked at this level")
    parameters = require(instance, "geared_cannon_parameters")
    validate_geared_cannon_parameters(parameters)
    attack = require(instance, "attack_parameters")
    if set(attack) != {"projectile"}:
        raise InputError("Geared Cannon requires one shared single-target projectile")
    interval = number(mode["attackSpeed"], "Cannon shot interval", EPSILON)
    interval *= modifiers["attack_interval_multiplier"]
    gap = number(mode["timeBetweenBursts"], "Cannon burst gap", EPSILON)
    gap *= modifiers["attack_interval_multiplier"]
    if parameters["burst_timing"].endswith("extra_after_one_inter_shot_interval"):
        gap += interval
    pattern = {
        "kind": "single",
        "source": actor["source"],
        "target_kinds": ["unit"],
        "target_layers": ["ground"],
        "maximum_hp_fraction": 0,
        "projectile": deepcopy(attack["projectile"]),
    }
    validate_pattern(pattern)
    actor.update(
        kind="defense",
        layer="ground",
        movement="stationary",
        speed=0,
        blocking=True,
        width=3,
        height=3,
        minimum_range=0,
        target_priorities=["unit"],
        target_priority_tiers=[["unit"]],
        target_layers=["ground"],
        range=number(mode["range"], "Cannon range", EPSILON)
        * modifiers["range_multiplier"],
        damage=number(
            row["stats"]["gearedUpBurst"]["damagePerShot"], "Cannon hit", EPSILON
        )
        * modifiers["damage_multiplier"],
        attack_interval_seconds=interval,
        attack_model=pattern,
        geared_cannon_model={
            "source": parameters["source"],
            "parameters": deepcopy(parameters),
            "shots_per_burst": integer(
                mode["shotsPerBurst"], "Cannon burst count", 4, 4
            ),
            "inter_shot_seconds": interval,
            "post_burst_seconds": gap,
        },
    )
    actor["entity_adapter"].update(
        geared_cannon_parameters=deepcopy(parameters),
        behavior_verification="experimental_burst_gap_not_replay_calibrated",
    )
    return actor


class GearedCannonCombat:
    """Shot-order owner; shared combat owns damage, protection and projectiles."""

    def __init__(self, actors, combat):
        self.combat = combat
        self.models = {}
        self.states = {}
        for key, actor in actors.items():
            if "geared_cannon_model" not in actor:
                continue
            model = deepcopy(actor["geared_cannon_model"])
            if set(model) != {
                "source",
                "parameters",
                "shots_per_burst",
                "inter_shot_seconds",
                "post_burst_seconds",
            }:
                raise InputError("Invalid Cannon runtime fields")
            validate_geared_cannon_parameters(model["parameters"])
            identifier(model["source"], "runtime Cannon evidence")
            if (
                actor["team"] != "defense"
                or actor["kind"] != "defense"
                or actor["movement"] != "stationary"
                or actor["target_layers"] != ["ground"]
                or actor["attack_model"]["kind"] != "single"
                or model["shots_per_burst"] != 4
                or actor["attack_interval_seconds"] != model["inter_shot_seconds"]
                or actor.get("entity_adapter", {}).get("entity") != "cannon"
                or not actor["counts_for_destruction"]
            ):
                raise InputError("Invalid runtime geared Cannon")
            for field in ("inter_shot_seconds", "post_burst_seconds"):
                number(model[field], "Cannon runtime clock", EPSILON)
            self.models[key] = model
            self.states[key] = {
                "next_shot_index": 0,
                "launched_shots": 0,
                "cancelled_shots": 0,
                "destroyed": False,
            }

    def prepare(self, actors, time, trace):
        for key, state in self.states.items():
            if actors[key]["hp"] > 0 or state["destroyed"]:
                continue
            state["cancelled_shots"] = (4 - state["next_shot_index"]) % 4
            state["next_shot_index"] = 0
            state["destroyed"] = True
            actors[key]["target"] = None
            trace.append(
                {
                    "event": "geared_cannon_destroyed",
                    "time_seconds": time,
                    "source": key,
                    "cancelled_shots": state["cancelled_shots"],
                }
            )

    def launch(self, actor, primary, actors, time, trace):
        if (
            not _active(actor, time)
            or actor["next_attack"] > time + EPSILON
            or actor["frozen_until"] > time + EPSILON
            or primary is None
            or not _eligible(actor, primary, time)
            or target_distance(center(actor), primary) > actor["range"] + EPSILON
        ):
            return False
        state, model = self.states[actor["id"]], self.models[actor["id"]]
        self.combat.launch(
            actor,
            primary,
            actors,
            time,
            trace,
            weapon_state={
                "kind": "geared_cannon",
                "shot_number": state["next_shot_index"] + 1,
            },
        )
        state["launched_shots"] += 1
        state["next_shot_index"] = (state["next_shot_index"] + 1) % 4
        interval = (
            model["inter_shot_seconds"]
            if state["next_shot_index"]
            else model["post_burst_seconds"]
        )
        actor["next_attack"] = time + interval / attack_rate(actor)
        return True

    def result(self):
        return {"states": deepcopy(self.states), "experimental": True}


def attach_explicit_defense_ammunition(actor, parameters):
    """X-Bow opt-in depletion using shared PatternCombat ammunition accounting.

    The pinned catalog does not contain a round count or reload state. Require
    caller evidence and explicit experimental initial rounds; never guess them.
    Inferno continuous/multibeam ammunition needs its ramp runtime and is rejected.
    """
    if actor.get("entity_adapter", {}).get("entity") != "x-bow":
        raise InputError("This ammunition binding supports X-Bow only")
    if set(parameters) != {"source", "status", "initial_rounds", "reload"}:
        raise InputError("Defense ammunition needs complete explicit parameters")
    if (
        parameters["status"] != "experimental_not_replay_calibrated"
        or parameters["reload"] != "none_during_battle"
    ):
        raise InputError("Unknown defense ammunition/reload behavior")
    actor["weapon_ammunition"] = {
        "source": identifier(parameters["source"], "ammunition evidence"),
        "initial_rounds": integer(parameters["initial_rounds"], "initial rounds", 0),
    }
    return actor
