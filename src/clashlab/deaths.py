"""Finite, explicit death-effect sequences anchored to the death position.

This supports conditional blasts and bolt patterns, without inventing random
lightning locations, summon statistics, or current entity behavior.
"""

from copy import deepcopy
from heapq import heappop, heappush

from .combat import expand_area_effects, validate_area_effect
from .common import InputError, identifier, number, require
from .ramping import RAMP_RULES
from .spatial import EPSILON, _apply_effects, center


RULESET = "spatial-death-effects-support-kernel-v6"
DEATH_RULES = {
    **RAMP_RULES,
    "death_trigger": "actual_hp_death_once_per_instance",
    "death_anchor": "source_center_captured_at_death",
    "death_geometry": "explicit_fixed_offsets_and_live_impact_membership",
    "death_phase": "settle_generations_after_commands_and_after_weapon_health",
    "death_sequence": "released_events_survive_source_loss_or_freeze",
}
SUPPORTED_EFFECTS = {"area_damage", "area_freeze"}


def validate_death_model(actor, actors):
    model = require(actor, "death_model")
    if set(model) != {"kind", "geometry", "source", "effects"}:
        raise InputError(
            "Death model must exactly declare the implemented sequence fields"
        )
    identifier(require(model, "source"), "death behavior evidence")
    if require(model, "kind") != "fixed_area_sequence_at_death":
        raise InputError("Death effects require an explicit fixed area sequence")
    if require(model, "geometry") != "offsets_from_source_center_at_death":
        raise InputError("Death geometry must be anchored to the actual death position")
    effects = require(model, "effects")
    if not isinstance(effects, list) or not effects:
        raise InputError("Death behavior needs a nonempty finite effect sequence")
    ids = set()
    for effect in effects:
        needed = {"id", "source", "kind", "delay_seconds", "area"}
        needed.add(
            "amount" if effect.get("kind") == "area_damage" else "duration_seconds"
        )
        if set(effect) != needed:
            raise InputError(
                "Death effects cannot include unsupported or preselected fields"
            )
        effect_id = identifier(require(effect, "id"), "death effect id")
        if effect_id in ids:
            raise InputError("An instance's death effect ids must be unique")
        ids.add(effect_id)
        if require(effect, "kind") not in SUPPORTED_EFFECTS:
            raise InputError(
                "Death summons, transformations and persistent poison need additional adapters"
            )
        number(require(effect, "delay_seconds"), "death effect delay", 0)
        identifier(require(effect, "source"), "death effect evidence")
        if "targets" in effect:
            raise InputError("Death effect membership must be resolved at impact")
        area = require(effect, "area")
        if set(area) != {
            "offset_x",
            "offset_y",
            "radius",
            "target_team",
            "target_kinds",
            "target_layers",
        }:
            raise InputError(
                "Death area must exactly declare offsets, radius and target filters"
            )
        if "x" in area or "y" in area:
            raise InputError(
                "Death effect areas need relative offsets, not preselected absolute positions"
            )
        number(require(area, "offset_x"), "death area horizontal offset")
        number(require(area, "offset_y"), "death area vertical offset")
        translated = deepcopy(effect)
        translated["time_seconds"] = effect["delay_seconds"]
        translated["area"]["x"] = area["offset_x"]
        translated["area"]["y"] = area["offset_y"]
        validate_area_effect(translated, actors)
    return model


class DeathCombat:
    """Release finite events exactly once and settle same-time death cascades."""

    def __init__(self, actors):
        self.models = {
            actor["id"]: deepcopy(validate_death_model(actor, actors))
            for actor in actors.values()
            if "death_model" in actor
        }
        self.emitted = set()
        self.pending = []
        self.serial = 0

    def _release(self, actors, time, trace):
        for actor_id in sorted(self.models):
            actor = actors[actor_id]
            if actor_id in self.emitted or actor["death_time"] is None:
                continue
            self.emitted.add(actor_id)
            if actor.get("wall_breaker_model") and actor.get("_troop_suicide_attack"):
                continue
            position = center(actor)
            for template in self.models[actor_id]["effects"]:
                effect = deepcopy(template)
                effect["id"] = f"{actor_id}:{template['id']}"
                effect["time_seconds"] = actor["death_time"] + template["delay_seconds"]
                effect["area"]["x"] = position[0] + template["area"]["offset_x"]
                effect["area"]["y"] = position[1] + template["area"]["offset_y"]
                effect["death_source"] = actor_id
                effect["death_position"] = {"x": position[0], "y": position[1]}
                self.serial += 1
                heappush(self.pending, (effect["time_seconds"], self.serial, effect))
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "death_effect_release",
                        "source": actor_id,
                        "effect_id": effect["id"],
                        "arrival_seconds": effect["time_seconds"],
                        "area": deepcopy(effect["area"]),
                    }
                )

    def settle(self, actors, time, trace, effect_observer=None, health_handler=None):
        while True:
            self._release(actors, time, trace)
            due = []
            while self.pending and self.pending[0][0] <= time + EPSILON:
                _, _, effect = heappop(self.pending)
                due.append(effect)
            if not due:
                break
            expanded = expand_area_effects(due, actors, time)
            if effect_observer is not None:
                effect_observer(expanded, actors, time, trace)
            for effect in expanded:
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "death_effect_impact",
                        "source": effect["death_source"],
                        "effect_id": effect["id"],
                        "targets": list(effect["targets"]),
                        "area": deepcopy(effect["area"]),
                        **(
                            {
                                "requested_damage_per_target": effect["amount"],
                                "protected_targets": [
                                    target_id
                                    for target_id in effect["targets"]
                                    if actors[target_id]["immune_until"]
                                    > time + EPSILON
                                ],
                            }
                            if effect["kind"] == "damage"
                            else {}
                        ),
                    }
                )
            _apply_effects(
                expanded,
                actors,
                time,
                trace,
                health_handler,
                getattr(self, "damage_receipts", None),
            )

    def next_boundary(self):
        return self.pending[0][0] if self.pending else None

    def result(self):
        return {
            "emitted_instances": sorted(self.emitted),
            "pending_effects_at_horizon": [
                {
                    "arrival_seconds": time,
                    "source": effect["death_source"],
                    "effect_id": effect["id"],
                    "area": deepcopy(effect["area"]),
                }
                for time, _, effect in self.pending
            ],
        }
