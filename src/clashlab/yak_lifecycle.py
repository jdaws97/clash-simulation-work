"""Pinned Mighty Yak wall damage and one owner-defeat rage window.

Independent wall-route selection is explicitly experimental. Owner revival
does not reset the latched rage; an inactive pet cannot start a new window.
"""

from .common import InputError, identifier, number
from .spatial import EPSILON, _active


POLICIES = {
    "experimental_policy": "yak_independent_wall_routing_uncalibrated",
    "rage_trigger": "first_observed_owner_defeat_while_pet_active",
    "owner_revival": "does_not_reset_or_retrigger_rage",
    "wall_clock": "instant_shared_with_main_weapon",
}


def validate_behavior(behavior):
    if behavior != POLICIES:
        raise InputError("Mighty Yak requires explicit experimental lifecycle policies")


def compile_model(entity, row, source, conversion):
    return {
        "source": source,
        "wall_damage": number(row["damageVsWalls"], "Yak wall damage", 0),
        "rage_duration": number(entity["rageDuration"], "Yak rage duration", 0),
        "rage_damage_factor": 1
        + number(entity["rageDamageIncreasePercent"], "Yak rage bonus", 0) / 100,
        "rage_movement_bonus": number(entity["rageSpeedIncrease"], "Yak speed bonus", 0)
        / conversion,
    }


class YakLifecycle:
    def __init__(self, actors):
        self.models = {}
        self.base = {}
        self.used = set()
        self.expiry = {}
        for key, actor in actors.items():
            if actor.get("pet_model", {}).get("entity") != "mighty-yak":
                continue
            model = actor.get("yak_model")
            if not isinstance(model, dict) or set(model) != {
                "source",
                "wall_damage",
                "rage_duration",
                "rage_damage_factor",
                "rage_movement_bonus",
            }:
                raise InputError(
                    "Mighty Yak requires complete pinned lifecycle quantities"
                )
            for field in set(model) - {"source"}:
                number(model[field], field, 0)
            identifier(model["source"], "Yak statistic provenance")
            number(model["rage_damage_factor"], "Yak rage factor", 1)
            if (
                actor.get("wall_behavior", {}).get("weapon", {}).get("damage")
                != model["wall_damage"]
            ):
                raise InputError(
                    "Yak wall weapon must match its declared lifecycle quantities"
                )
            self.models[key] = model
            self.base[key] = (actor["damage"], actor["speed"])

    def prepare(self, actors, time, trace):
        for key, model in self.models.items():
            actor = actors[key]
            owner = actors[actor["pet_model"]["hero_id"]]
            if key not in self.used and _active(actor, time) and owner["hp"] <= 0:
                self.used.add(key)
                self.expiry[key] = time + model["rage_duration"]
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "yak_owner_defeat_rage",
                        "pet": key,
                        "hero": owner["id"],
                        "expires_at": self.expiry[key],
                        "experimental": True,
                    }
                )
            active = self.expiry.get(key, 0) > time
            factor = model["rage_damage_factor"] if active else 1
            damage, speed = self.base[key]
            actor["damage"] = damage * factor
            actor["speed"] = speed + (model["rage_movement_bonus"] if active else 0)
            actor["wall_behavior"]["weapon"]["damage"] = model["wall_damage"] * factor

    def next_boundary(self, time):
        values = [expiry for expiry in self.expiry.values() if expiry > time]
        return min(values) if values else None
