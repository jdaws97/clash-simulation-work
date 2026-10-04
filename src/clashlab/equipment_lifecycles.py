"""Owner-local equipment effects with opt-in, uncalibrated clock policies.

Statistics and ability duration come from the pinned catalog record. Contracts
name unresolved stacking, hit timing and revival semantics rather than infer
them. The runtime uses ordinary launch callbacks and healing receipts.
"""

from collections import defaultdict
from copy import deepcopy

from .common import InputError, identifier, integer, number, require
from .hero_extensions import source_quantity
from .rates import rescale_remaining_cooldown
from .spatial import EPSILON, _active


OWNERS = {
    "rage-vial": "barbarian-king",
    "haste-vial": "royal-champion",
    "vampstache": "barbarian-king",
    "frozen-arrow": "archer-queen",
}
POLICIES = {
    "experimental_policy": "owner_local_v1_uncalibrated",
    "stacking": "multiply_damage_and_cadence_add_movement_independent_sources",
    "freeze": "absolute_duration_continues_cooldown_work_preserved",
    "revival": "no_new_charge_absolute_effect_expiry",
    "healing_trigger": "ordinary_weapon_launch_once_not_per_splash_target",
    "slow": "catalog_strength_both_axes_refresh_same_source_immunity_does_not_block",
}
FIELDS = {
    "entity",
    "level",
    "ability_type",
    "source",
    "parameters",
    "duration_seconds",
    "damage_factor",
    "movement_bonus",
    "active_attack_rate",
    "passive_attack_rate",
    "healing_per_launch",
    "on_hit_status",
}


def validate_equipment(model):
    if not isinstance(model, dict) or set(model) != FIELDS:
        raise InputError("Owner-local equipment requires a complete runtime contract")
    entity = model["entity"]
    if entity not in OWNERS:
        raise InputError("Unsupported owner-local equipment")
    expected = "Passive" if entity in {"vampstache", "frozen-arrow"} else "Active"
    if model["ability_type"] != expected:
        raise InputError("Owner-local equipment ability type mismatch")
    integer(model["level"], "equipment level", 1)
    identifier(model["source"], "equipment statistics source")
    parameters = model["parameters"]
    if not isinstance(parameters, dict) or set(parameters) != {"source", *POLICIES}:
        raise InputError("Owner-local equipment needs explicit experimental policies")
    identifier(parameters["source"], "equipment behavior source")
    if any(parameters[key] != value for key, value in POLICIES.items()):
        raise InputError("Unsupported owner-local equipment policy")
    for field in FIELDS - {
        "entity",
        "level",
        "ability_type",
        "source",
        "parameters",
        "on_hit_status",
    }:
        number(
            model[field],
            field,
            1 if field.endswith("rate") or field == "damage_factor" else 0,
        )
    if entity in {"vampstache", "frozen-arrow"} and any(
        model[field] != value
        for field, value in {
            "duration_seconds": 0,
            "damage_factor": 1,
            "movement_bonus": 0,
            "active_attack_rate": 1,
        }.items()
    ):
        raise InputError("Passive owner equipment cannot acquire an active effect")
    if entity == "frozen-arrow":
        from .hit_status import validate_hit_status

        validate_hit_status(model["on_hit_status"])
    elif model["on_hit_status"] is not None:
        raise InputError("Only Frozen Arrow declares an owner-local impact status")


def compile_equipment(instance, hero, catalog, movement_units_per_tile):
    if set(instance) != {"entity", "level", "parameters"}:
        raise InputError("Owner-local equipment requires entity, level and parameters")
    entity_id = require(instance, "entity")
    if entity_id not in OWNERS or OWNERS[entity_id] != hero["entity"]:
        raise InputError("Owner-local equipment belongs to a different hero")
    if entity_id in {"vampstache", "frozen-arrow"} and hero.get(
        "wall_parameters", {}
    ).get("kind") in {"clear_obstructions", "penetrate_obstructions"}:
        raise InputError(
            "Equipment wall-hit healing/status needs the shared wall-impact callback"
        )
    entity = catalog.entity(entity_id)
    level = integer(instance["level"], "equipment level", 1)
    if not catalog.available(entity_id, level, hero["town_hall"]):
        raise InputError("Equipment unavailable at selected Town Hall")
    row = catalog.level(entity_id, level)
    stats = row["stats"]
    units = number(movement_units_per_tile, "movement units per tile", EPSILON)
    model = {
        "entity": entity_id,
        "level": level,
        "ability_type": entity["abilityType"],
        "source": catalog.records[entity_id]["source"],
        "parameters": deepcopy(instance["parameters"]),
        "duration_seconds": 0,
        "damage_factor": 1,
        "movement_bonus": 0,
        "active_attack_rate": 1,
        "passive_attack_rate": 1,
        "healing_per_launch": 0,
        "on_hit_status": None,
    }
    if entity_id == "rage-vial":
        model.update(
            duration_seconds=number(
                entity["ability"]["abilityDuration"], "Rage duration", 0
            ),
            damage_factor=1
            + source_quantity(stats["damageIncrease"], "%", allow_leading_plus=True)
            / 100,
            movement_bonus=number(
                stats["movementSpeedIncrease"], "Rage movement bonus", 0
            )
            / units,
        )
    elif entity_id == "haste-vial":
        model.update(
            duration_seconds=source_quantity(stats["abilityDuration"], "s"),
            movement_bonus=number(stats["speedIncrease"], "Haste movement bonus", 0)
            / units,
            active_attack_rate=1
            + source_quantity(
                stats["abilityAttackSpeedIncrease"], "%", allow_leading_plus=True
            )
            / 100,
        )
    elif entity_id == "frozen-arrow":
        strength = source_quantity(stats["slowDown"], "%") / 100
        model["on_hit_status"] = {
            "source": model["source"],
            "duration_seconds": source_quantity(stats["slowDownDuration"], "s"),
            "attack_rate_multiplier": 1 - strength,
            "movement_multiplier": 1 - strength,
            "protection_policy": "damage_immunity_does_not_block_status",
        }
    else:
        model["healing_per_launch"] = number(
            stats["healPerHit"], "Vampstache healing", 0
        )
    if "attackSpeedIncrease" in stats:
        model["passive_attack_rate"] = (
            1
            + source_quantity(
                stats["attackSpeedIncrease"], "%", allow_leading_plus=True
            )
            / 100
        )
    validate_equipment(model)
    return model, row


class EquipmentLifecycles:
    """Compose local effects after base weapon reset, before hero extensions."""

    def __init__(self, actors):
        self.items = {}
        self.base = {}
        self.expiry = {}
        self.used = set()
        self.rates = {}
        self.pending_healing = defaultdict(float)
        self.log = []
        for key, actor in actors.items():
            selected = [
                item
                for item in actor.get("hero_model", {}).get("equipment", [])
                if item["entity"] in OWNERS
            ]
            if not selected:
                continue
            for item in selected:
                validate_equipment(item)
                if OWNERS[item["entity"]] != actor["hero_model"]["entity"]:
                    raise InputError("Equipment runtime owner mismatch")
                if item["entity"] in {"vampstache", "frozen-arrow"} and actor.get(
                    "wall_behavior", {}
                ).get("kind") in {"clear_obstructions", "penetrate_obstructions"}:
                    raise InputError(
                        "Equipment wall-hit healing/status requires central integration"
                    )
                if (
                    item["on_hit_status"] is not None
                    and actor.get("on_hit_status") != item["on_hit_status"]
                ):
                    raise InputError(
                        "Frozen Arrow requires its shared impact-status binding"
                    )
            self.items[key] = deepcopy(selected)
            self.base[key] = (actor["speed"], actor["attack_interval_seconds"])
            self.rates[key] = 1

    def activate(self, hero_id, actors, time, trace):
        if (
            hero_id not in self.items
            or hero_id in self.used
            or not _active(actors[hero_id], time)
        ):
            return
        self.used.add(hero_id)
        for item in self.items[hero_id]:
            if item["ability_type"] == "Active":
                self.expiry[(hero_id, item["entity"])] = time + item["duration_seconds"]
                entry = {
                    "time_seconds": time,
                    "event": "owner_equipment_activated",
                    "source": hero_id,
                    "equipment": item["entity"],
                    "expires_at": time + item["duration_seconds"],
                    "experimental": True,
                }
                trace.append(entry)
                self.log.append(deepcopy(entry))

    def prepare(self, actors, time):
        for key, items in self.items.items():
            actor = actors[key]
            rate = 1
            damage = 1
            movement = 0
            for item in items:
                rate *= item["passive_attack_rate"]
                if self.expiry.get((key, item["entity"]), 0) > time:
                    rate *= item["active_attack_rate"]
                    damage *= item["damage_factor"]
                    movement += item["movement_bonus"]
            if rate != self.rates[key]:
                rescale_remaining_cooldown(actor, time, self.rates[key], rate)
                self.rates[key] = rate
            speed, interval = self.base[key]
            actor["speed"] = speed + movement
            actor["attack_interval_seconds"] = interval / rate
            actor["damage"] *= damage
            if actor.get("wall_behavior", {}).get("kind") == "clear_obstructions":
                actor["wall_behavior"]["weapon"]["damage"] = actor["damage"]
                if (
                    actor["wall_behavior"]["weapon"]["cooldown"]
                    == "shared_with_main_weapon"
                ):
                    actor["wall_behavior"]["weapon"]["attack_interval_seconds"] = (
                        interval / rate
                    )

    def weapon_launched(self, hero_id, time, trace):
        for item in self.items.get(hero_id, []):
            if item["healing_per_launch"]:
                self.pending_healing[hero_id] += item["healing_per_launch"]
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "vampstache_launch_healing",
                        "source": hero_id,
                        "amount": item["healing_per_launch"],
                        "experimental": True,
                    }
                )

    def resolve_healing(self, actors, time):
        healing = {
            key: amount
            for key, amount in self.pending_healing.items()
            if _active(actors[key], time)
        }
        self.pending_healing.clear()
        return healing

    def next_boundary(self, time):
        values = [expiry for expiry in self.expiry.values() if expiry > time]
        return min(values) if values else None

    def result(self):
        return {"activations": self.log, "experimental": True, "game_calibrated": False}
