"""Impact-applied slows and the attacking Ice Golem lifecycle.

Slow strength, duration, protection and stacking are declared conventions. This
does not infer the game's current chill constants from descriptive text.
"""

from copy import deepcopy

from .common import InputError, identifier, number, require
from .rates import rescale_remaining_cooldown
from .spatial import EPSILON, _active
from .traps import RULES as TRAP_RULES


RULESET = "spatial-hit-status-traps-kernel-v12"
SCOPE = "hit_status_damage_traps_heroes_sector_without_pets_or_defending_troops"
RULES = {
    **TRAP_RULES,
    "hit_status_phase": "successful_impact_after_same_time_weapon_launches",
    "hit_status_stack": "strongest_per_axis_with_independent_source_expiry",
    "hit_status_refresh": "same_source_refreshes_expiry_without_multiplying_strength",
    "hit_status_clock": "preserve_remaining_attack_work_including_frozen_work",
    "hit_status_hazards": "multiply_hit_status_and_hazard_rates",
    "hit_status_source_death": "released_packets_and_existing_statuses_persist",
}
MODEL_FIELDS = {
    "source",
    "duration_seconds",
    "attack_rate_multiplier",
    "movement_multiplier",
    "protection_policy",
}
PROTECTION_POLICIES = {
    "damage_immunity_does_not_block_status",
    "damage_immunity_also_blocks_status",
}


def validate_hit_status(model):
    if not isinstance(model, dict) or set(model) != MODEL_FIELDS:
        raise InputError("Hit status must declare its complete supported model")
    identifier(require(model, "source"), "hit status evidence")
    number(model["duration_seconds"], "hit status duration", EPSILON)
    for field in ("attack_rate_multiplier", "movement_multiplier"):
        number(model[field], field, EPSILON, 1)
    if model["protection_policy"] not in PROTECTION_POLICIES:
        raise InputError("Hit status protection policy must be explicit")


def compile_ice_golem(actor, instance, entity, row):
    parameters = require(instance, "ice_parameters")
    if not isinstance(parameters, dict) or set(parameters) != {
        "source",
        "on_hit_slow",
        "death_delay_seconds",
        "death_radius_multiplier",
        "death_duration_multiplier",
        "death_target_kinds",
        "death_target_layers",
    }:
        raise InputError("Ice Golem needs explicit chill and death-freeze parameters")
    source = identifier(parameters["source"], "Ice Golem behavior evidence")
    validate_hit_status(parameters["on_hit_slow"])
    actor["on_hit_status"] = deepcopy(parameters["on_hit_slow"])
    delay = number(parameters["death_delay_seconds"], "death freeze delay", 0)
    radius = number(entity["freezeRadiusOnOffense"], "snapshot freeze radius", 0)
    radius *= number(parameters["death_radius_multiplier"], "freeze radius scale", 0)
    duration = number(
        row["deathFreezeTimeOnOffense"], "snapshot freeze duration", EPSILON
    )
    duration *= number(
        parameters["death_duration_multiplier"], "freeze duration scale", EPSILON
    )
    actor["death_model"] = {
        "kind": "fixed_area_sequence_at_death",
        "geometry": "offsets_from_source_center_at_death",
        "source": source,
        "effects": [
            {
                "id": "ice-golem-death-freeze",
                "source": source,
                "kind": "area_freeze",
                "delay_seconds": delay,
                "duration_seconds": duration,
                "area": {
                    "offset_x": 0,
                    "offset_y": 0,
                    "radius": radius,
                    "target_team": "defense",
                    "target_kinds": deepcopy(parameters["death_target_kinds"]),
                    "target_layers": deepcopy(parameters["death_target_layers"]),
                },
            }
        ],
    }
    actor["entity_adapter"]["ice_parameters"] = deepcopy(parameters)


class HitStatusCombat:
    """Keep every source's expiry so a weaker remaining slow can resume."""

    def __init__(self, actors):
        for actor in actors.values():
            if "on_hit_status" in actor:
                validate_hit_status(actor["on_hit_status"])
        self.exposures = {}

    def impact(self, packet, target, actors, time, trace):
        model = packet.get("on_hit_status")
        if model is None or not _active(target, time):
            return
        if (
            target["immune_until"] > time + EPSILON
            and model["protection_policy"] == "damage_immunity_also_blocks_status"
        ):
            return
        key = target["id"], packet["source"]
        self.exposures[key] = {
            **deepcopy(model),
            "expires_at": time + model["duration_seconds"],
        }
        trace.append(
            {
                "event": "hit_status_apply",
                "time_seconds": time,
                "source": packet["source"],
                "target": target["id"],
                "status": deepcopy(self.exposures[key]),
            }
        )

    def prepare(self, actors, time, trace):
        self.exposures = {
            key: exposure
            for key, exposure in self.exposures.items()
            if exposure["expires_at"] > time and _active(actors[key[0]], time)
        }
        grouped = {}
        for (target, source), exposure in self.exposures.items():
            grouped.setdefault(target, []).append((source, exposure))
        for actor in actors.values():
            exposures = grouped.get(actor["id"], [])
            attack = min(
                [1, *(model["attack_rate_multiplier"] for _, model in exposures)]
            )
            movement = min(
                [1, *(model["movement_multiplier"] for _, model in exposures)]
            )
            old_attack = actor.get("_hit_status_attack_rate", 1)
            old_movement = actor.get("_hit_status_movement_multiplier", 1)
            if abs(old_attack - attack) > EPSILON:
                rescale_remaining_cooldown(actor, time, old_attack, attack)
            if (
                abs(old_attack - attack) > EPSILON
                or abs(old_movement - movement) > EPSILON
            ):
                trace.append(
                    {
                        "event": "hit_status_change",
                        "time_seconds": time,
                        "target": actor["id"],
                        "attack_rate_multiplier": attack,
                        "movement_multiplier": movement,
                        "sources": sorted(source for source, _ in exposures),
                    }
                )
            actor["_hit_status_attack_rate"] = attack
            actor["_hit_status_movement_multiplier"] = movement

    def next_boundary(self):
        return min(
            (model["expires_at"] for model in self.exposures.values()), default=None
        )

    def result(self):
        return [
            {"target": target, "source_actor": source, **deepcopy(model)}
            for (target, source), model in sorted(self.exposures.items())
        ]
