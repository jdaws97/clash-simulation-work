"""Electro Titan weapon-independent aura under explicit pulse hypotheses."""

from collections import defaultdict
from copy import deepcopy
from math import hypot

from .buffs import damage_multiplier
from .common import InputError, identifier, number, require
from .damage_receipts import record_damage
from .spatial import EPSILON, _active, center, target_distance
from .spell_visibility import untargetable_until


PARAMETERS = {
    "source",
    "first_pulse_delay_seconds",
    "geometry",
    "membership",
    "freeze_policy",
    "visibility_policy",
    "damage_scaling",
    "stacking",
    "protection",
    "source_persistence",
}


def validate_aura_parameters(parameters):
    if not isinstance(parameters, dict) or set(parameters) != PARAMETERS:
        raise InputError("Electro Titan requires every explicit aura convention")
    identifier(parameters["source"], "Electro Titan aura evidence")
    number(parameters["first_pulse_delay_seconds"], "first aura pulse delay", 0)
    choices = {
        "geometry": {"source_center_to_target_footprint", "center_to_center"},
        "membership": {"live_at_each_pulse"},
        "freeze_policy": {"continues_while_frozen", "skip_frozen_pulses"},
        "visibility_policy": {"hits_invisible", "requires_targetable"},
        "damage_scaling": {"catalog_aura_only", "source_damage_multiplier_at_pulse"},
        "stacking": {"additive_per_source", "strongest_due_source_per_recipient"},
        "protection": {"shared_damage_immunity"},
        "source_persistence": {"living_deployed_source_only"},
    }
    for field, allowed in choices.items():
        if parameters[field] not in allowed:
            raise InputError(f"Unsupported Electro Titan aura {field}")


def compile_electro_titan(actor, instance, entity, row, modifiers):
    """Attach aura statistics without replacing the ordinary whip weapon."""
    if (
        entity.get("id") != "electro-titan"
        or actor.get("entity_adapter", {}).get("entity") != "electro-titan"
        or actor.get("team") != "attack"
        or actor.get("kind") != "unit"
        or actor.get("layer") != "ground"
        or actor.get("attack_model", {}).get("kind") != "single"
    ):
        raise InputError("Electro Titan aura requires its attacking ground actor")
    parameters = require(instance, "aura_parameters")
    validate_aura_parameters(parameters)
    stats = require(require(row, "stats"), "aura")
    actor["aura_model"] = {
        "entity": "electro-titan",
        "parameters": deepcopy(parameters),
        "radius": number(require(entity, "auraRange"), "catalog aura range", 0),
        "interval_seconds": number(
            require(entity, "auraAttackSpeed"), "catalog aura cadence", EPSILON
        ),
        "damage_per_pulse": number(
            require(stats, "damagePerShot"), "catalog aura pulse", 0
        )
        * modifiers["damage_multiplier"],
        "target_kinds": ["unit", "defense", "building"],
        "target_layers": ["ground", "air"],
        "source": actor["source"],
    }
    actor["entity_adapter"]["aura_statistics"] = {
        "damage": "stats.aura.damagePerShot times explicit troop damage modifier",
        "radius": "auraRange independent of whip range modifier",
        "cadence": "auraAttackSpeed independent of whip attack modifier",
        "verification": "catalog_snapshot_with_explicit_uncalibrated_behavior",
        "parameters": deepcopy(parameters),
    }
    return actor


class ElectroTitanCombat:
    """Resolve simultaneous aura emissions through shared damage attribution."""

    def __init__(self, actors):
        self.actors = actors
        self.models = {}
        self.states = {}
        for key, actor in actors.items():
            if "aura_model" not in actor:
                continue
            model = deepcopy(actor["aura_model"])
            if (
                model.get("entity") != "electro-titan"
                or actor["kind"] != "unit"
                or actor["team"] != "attack"
                or actor["layer"] != "ground"
                or model.get("target_kinds") != ["unit", "defense", "building"]
                or model.get("target_layers") != ["ground", "air"]
            ):
                raise InputError("Invalid Electro Titan ownership or aura filters")
            validate_aura_parameters(require(model, "parameters"))
            number(require(model, "radius"), "aura radius", 0)
            number(require(model, "interval_seconds"), "aura interval", EPSILON)
            number(require(model, "damage_per_pulse"), "aura pulse damage", 0)
            identifier(require(model, "source"), "aura statistic source")
            self.models[key] = model
            self.states[key] = {"next_pulse": None, "pulses": 0}
        stacking = {model["parameters"]["stacking"] for model in self.models.values()}
        if len(stacking) > 1:
            raise InputError("Simultaneous Titan auras need one shared stacking policy")

    def prepare(self, time):
        for key, state in self.states.items():
            actor = self.actors[key]
            if state["next_pulse"] is None and _active(actor, time):
                delay = self.models[key]["parameters"]["first_pulse_delay_seconds"]
                state["next_pulse"] = actor["spawn_seconds"] + delay

    def _members(self, actor, model, time):
        point = center(actor)
        for target in self.actors.values():
            if (
                not _active(target, time)
                or target["team"] == actor["team"]
                or target["kind"] not in model["target_kinds"]
                or target["layer"] not in model["target_layers"]
                or target.get("_tesla_hidden", False)
            ):
                continue
            if (
                model["parameters"]["visibility_policy"] == "requires_targetable"
                and untargetable_until(target) > time + EPSILON
            ):
                continue
            distance = (
                target_distance(point, target)
                if model["parameters"]["geometry"]
                == "source_center_to_target_footprint"
                else hypot(point[0] - center(target)[0], point[1] - center(target)[1])
            )
            if distance <= model["radius"] + EPSILON:
                yield target

    def resolve(self, time, trace):
        self.prepare(time)
        due = defaultdict(list)
        for key, model in sorted(self.models.items()):
            actor = self.actors[key]
            state = self.states[key]
            scheduled = state["next_pulse"]
            if (
                not _active(actor, time)
                or scheduled is None
                or scheduled > time + EPSILON
            ):
                continue
            if scheduled < time - EPSILON:
                raise InputError("Electro Titan aura pulse boundary was skipped")
            state["next_pulse"] = scheduled + model["interval_seconds"]
            state["pulses"] += 1
            parameters = model["parameters"]
            frozen = actor["frozen_until"] > time + EPSILON
            targets = []
            if not (frozen and parameters["freeze_policy"] == "skip_frozen_pulses"):
                multiplier = (
                    damage_multiplier(actor)
                    if parameters["damage_scaling"]
                    == "source_damage_multiplier_at_pulse"
                    else 1
                )
                amount = model["damage_per_pulse"] * multiplier
                for target in self._members(actor, model, time):
                    due[target["id"]].append((key, amount))
                    targets.append(target["id"])
            trace.append(
                {
                    "event": "electro_titan_aura_pulse",
                    "time_seconds": time,
                    "source": key,
                    "pulse_index": state["pulses"] - 1,
                    "targets": sorted(targets),
                    "source_frozen": frozen,
                }
            )
        damage = defaultdict(float)
        for target_id, emissions in sorted(due.items()):
            policy = self.models[emissions[0][0]]["parameters"]["stacking"]
            if policy == "strongest_due_source_per_recipient":
                emissions = [min(emissions, key=lambda item: (-item[1], item[0]))]
            for source_id, amount in emissions:
                damage[target_id] += record_damage(
                    self,
                    self.actors[target_id],
                    amount,
                    time,
                    source_id=source_id,
                    source_actor_id=source_id,
                    source_team=self.actors[source_id]["team"],
                    origin="ability",
                )
        return damage

    def next_boundary(self, time):
        self.prepare(time)
        pending = [
            state["next_pulse"]
            for key, state in self.states.items()
            if _active(self.actors[key], time)
            and state["next_pulse"] is not None
            and state["next_pulse"] > time + EPSILON
        ]
        return min(pending, default=None)

    def result(self):
        return {"auras": deepcopy(self.states), "replay_validated": False}
