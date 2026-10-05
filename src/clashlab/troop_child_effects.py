"""Owned Firemite contact consumption and persistent building-damaging pools.

The shared generic hazard currently accepts unit recipients only. This domain
resolver therefore returns attributed area damage for ordinary shared settlement;
it does not bypass protection, health clipping or death processing.
"""

from collections import defaultdict
from copy import deepcopy

from .battle_termination import continuation_fact
from .buffs import damage_multiplier
from .common import InputError, identifier, number, require
from .damage_receipts import record_damage
from .spatial import EPSILON, _active, target_distance
from .spell_visibility import untargetable_until


def compile_firemite_pool(actor, parameters):
    model = deepcopy(parameters)
    expected = {
        "source",
        "status",
        "trigger",
        "source_persistence",
        "duration_seconds",
        "pulse_interval_seconds",
        "first_pulse_offset_seconds",
        "maximum_dps",
        "radius_tiles",
        "target_kinds",
        "target_layers",
        "visibility",
        "damage_scaling",
    }
    if not isinstance(model, dict) or set(model) != expected:
        raise InputError(
            "Firemite pools require complete quantity, contact and field contracts"
        )
    identifier(model["source"], "Firemite pool statistics evidence")
    if (
        model["status"] != "explicit_uncalibrated_hypothesis"
        or model["trigger"] != "first_successful_weapon_impact_once"
        or model["source_persistence"] != "fixed_pool_survives_child_and_furnace_loss"
    ):
        raise InputError("Unsupported Firemite contact/persistence policy")
    duration = number(model["duration_seconds"], "Firemite pool lifetime", EPSILON)
    number(model["pulse_interval_seconds"], "Firemite pool cadence", EPSILON)
    first = number(model["first_pulse_offset_seconds"], "Firemite first pulse", 0)
    if first >= duration:
        raise InputError("Firemite first pool pulse must precede expiry")
    number(model["maximum_dps"], "Firemite pool DPS", EPSILON)
    number(model["radius_tiles"], "Firemite pool radius", EPSILON)
    for field, allowed in (
        ("target_kinds", {"unit", "defense", "building", "wall"}),
        ("target_layers", {"ground", "air"}),
    ):
        values = model[field]
        if (
            not isinstance(values, list)
            or not values
            or len(set(values)) != len(values)
            or not set(values) <= allowed
        ):
            raise InputError("Firemite pool filters must be explicit and unique")
    if not {"defense", "building"} <= set(model["target_kinds"]):
        raise InputError("Firemite pools must support the documented building damage")
    if model["visibility"] not in {"hits_invisible", "requires_targetable"} or model[
        "damage_scaling"
    ] not in {"unscaled_pool_statistics", "capture_child_damage_multiplier_at_launch"}:
        raise InputError("Firemite visibility/buff policy must be explicit")
    actor["troop_fire_pool_model"] = model
    return actor


class TroopChildEffectCombat:
    def __init__(self, actors):
        self.actors = actors
        self.models = {
            key: deepcopy(actor["troop_fire_pool_model"])
            for key, actor in actors.items()
            if "troop_fire_pool_model" in actor
        }
        self.launches, self.consumed, self.fields, self.pulses = {}, set(), {}, []

    def on_launch(self, child_id, launch_id, time):
        if child_id in self.models:
            key = child_id, str(launch_id)
            if key in self.launches:
                raise InputError("Firemite launch receipt cannot be recorded twice")
            self.launches[key] = {
                "time": time,
                "damage_multiplier": damage_multiplier(self.actors[child_id]),
            }

    def on_impact(self, child_id, launch_id, point, time, trace):
        if child_id not in self.models or child_id in self.consumed:
            return
        launch = self.launches.get((child_id, str(launch_id)))
        if launch is None:
            raise InputError("Firemite pool requires its captured owned launch receipt")
        actor, model = self.actors[child_id], self.models[child_id]
        self.consumed.add(child_id)
        # A launched contact may finish after another packet killed the child.
        # It must still emit its pool, without overwriting an earlier actual death.
        if actor.get("death_time") is None:
            actor["hp"] = 0
            actor["death_time"] = time
            actor["_troop_child_consumed"] = True
        multiplier = (
            launch["damage_multiplier"]
            if model["damage_scaling"] == "capture_child_damage_multiplier_at_launch"
            else 1
        )
        key = child_id + ":fire-pool"
        self.fields[key] = {
            "id": key,
            "source_actor": child_id,
            "source_team": actor["team"],
            "position": tuple(point),
            "start": time,
            "end": time + model["duration_seconds"],
            "next_pulse": time + model["first_pulse_offset_seconds"],
            "amount": model["maximum_dps"]
            * model["pulse_interval_seconds"]
            * multiplier,
            "model": model,
        }
        trace.append(
            {
                "time_seconds": time,
                "event": "firemite_pool_created",
                "source": child_id,
                "field": key,
            }
        )

    def resolve(self, time, trace):
        damage = defaultdict(float)
        for key, field in self.fields.items():
            due = field["next_pulse"]
            if due > time or due >= field["end"]:
                continue
            if due < time:
                raise InputError(
                    "A Firemite pool boundary was skipped; do not compress past pulses into one health batch"
                )
            model = field["model"]
            for actor in self.actors.values():
                if (
                    not _active(actor, time)
                    or actor["team"] == field["source_team"]
                    or actor["kind"] not in model["target_kinds"]
                    or actor["layer"] not in model["target_layers"]
                    or target_distance(field["position"], actor)
                    > model["radius_tiles"] + EPSILON
                ):
                    continue
                if (
                    model["visibility"] == "requires_targetable"
                    and untargetable_until(actor) > time
                ):
                    continue
                amount = record_damage(
                    self,
                    actor,
                    field["amount"],
                    time,
                    source_id=key,
                    source_actor_id=field["source_actor"],
                    source_team=field["source_team"],
                    origin="hazard",
                )
                damage[actor["id"]] += amount
                event = {
                    "time_seconds": time,
                    "event": "firemite_pool_pulse",
                    "source": field["source_actor"],
                    "field": key,
                    "target": actor["id"],
                    "amount": amount,
                }
                self.pulses.append(event)
                trace.append(deepcopy(event))
            future = due + model["pulse_interval_seconds"]
            if future <= due:
                raise InputError(
                    "Firemite pulse interval is not representable at this time"
                )
            field["next_pulse"] = future
        return damage

    def next_boundary(self, time):
        boundaries = [
            value
            for field in self.fields.values()
            for value in (field["next_pulse"], field["end"])
            if value > time and value <= field["end"]
        ]
        return min(boundaries, default=None)

    def continuation_reasons(self, time):
        return [
            continuation_fact(
                "lingering_damage",
                key,
                [field["source_actor"]],
                not_before_seconds=field["next_pulse"],
                expires_at_seconds=field["end"],
            )
            for key, field in self.fields.items()
            if field["next_pulse"] < field["end"] and time < field["end"]
        ]

    def result(self):
        return {
            "status": "EXPLICIT_UNCALIBRATED_FIREMITE_POOLS",
            "consumed_children": sorted(self.consumed),
            "pulses": deepcopy(self.pulses),
        }
