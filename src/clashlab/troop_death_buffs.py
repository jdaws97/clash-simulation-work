"""Once-only death Rage routed through existing continuous shared buff fields.

This is a generated effect, never a paid Rage cast. Unknown field quantities and
cross-class scaling require explicit experimental input; no spell level is guessed.
"""

from copy import deepcopy
from math import inf, nextafter

from .buffs import validate_buff_field
from .common import InputError, identifier, number, require
from .spatial import center
from .valkyries import compile_valkyrie


def validate_death_buff_parameters(parameters):
    if not isinstance(parameters, dict) or set(parameters) != {
        "source",
        "status",
        "release_delay_seconds",
        "field",
        "trigger",
        "origin",
    }:
        raise InputError(
            "Super Valkyrie needs complete death Rage geometry, timing and provenance"
        )
    identifier(parameters["source"], "Super Valkyrie death Rage evidence")
    if (
        parameters["status"] != "explicit_uncalibrated_hypothesis"
        or parameters["trigger"] != "actual_hp_death_once"
        or parameters["origin"] != "generated_troop_effect_not_paid_spell"
    ):
        raise InputError(
            "Super Valkyrie must retain explicit experimental generated-effect ownership"
        )
    number(parameters["release_delay_seconds"], "death Rage release delay", 0)
    field = parameters["field"]
    if (
        not isinstance(field, dict)
        or field.get("kind") != "area_buff"
        or field.get("entity") != "rage-spell"
        or field.get("start_seconds") != 0
        or field.get("area", {}).get("x") != 0
        or field.get("area", {}).get("y") != 0
        or field.get("area", {}).get("target_team") != "attack"
    ):
        raise InputError(
            "Death Rage needs a relative-origin shared Rage field template"
        )
    if "spell_adapter" in field or "army_binding" in field:
        raise InputError("Generated death Rage cannot create spell inventory")


def compile_super_valkyrie(actor, instance, entity):
    if entity.get("id") != "super-valkyrie" or actor.get("team") != "attack":
        raise InputError("Death Rage requires an attacking Super Valkyrie")
    parameters = deepcopy(require(instance, "death_buff_parameters"))
    validate_death_buff_parameters(parameters)
    # Reuse the exact existing placement/swing compiler; this capability view does
    # not change actor.entity_adapter, catalog stats, super identity or inventory.
    capability_instance = {**instance, "entity": "valkyrie"}
    compile_valkyrie(actor, capability_instance)
    actor["troop_death_buff_model"] = parameters
    actor["entity_adapter"]["death_buff_parameters"] = deepcopy(parameters)
    return actor


class TroopDeathBuffCombat:
    def __init__(self, actors, buffs):
        self.actors, self.buffs = actors, buffs
        self.models = {
            key: deepcopy(actor["troop_death_buff_model"])
            for key, actor in actors.items()
            if "troop_death_buff_model" in actor
        }
        self.emitted, self.fields, self.pending = set(), {}, []
        if any(key + ":death-rage" in buffs.fields for key in self.models):
            raise InputError("Generated death Rage ID collides with a declared buff")
        for model in self.models.values():
            validate_death_buff_parameters(model)
            validate_buff_field(model["field"], actors)

    def prepare(self, time, trace):
        for key, model in self.models.items():
            actor = self.actors[key]
            if (
                key in self.emitted
                or actor.get("death_time") is None
                or actor["death_time"] > time
            ):
                continue
            # Form retirement/consumption and nondeath removals are not HP death.
            if actor.get("_troop_form_retired") or actor.get("_troop_suicide_attack"):
                continue
            self.emitted.add(key)
            field = deepcopy(model["field"])
            field["id"] = key + ":death-rage"
            death, delay = actor["death_time"], model["release_delay_seconds"]
            release = death + delay
            field["start_seconds"] = (
                nextafter(death, inf) if delay > 0 and release <= death else release
            )
            field["area"]["x"], field["area"]["y"] = center(actor)
            field["generated_effect_owner"] = key
            field["generated_effect_origin"] = model["origin"]
            self.pending.append((key, field))
        waiting = []
        for key, field in self.pending:
            if field["start_seconds"] > time:
                waiting.append((key, field))
                continue
            self.buffs.schedule(field, self.actors)
            self.fields[key] = field["id"]
            trace.append(
                {
                    "time_seconds": time,
                    "event": "troop_death_rage_released",
                    "source": key,
                    "field": field["id"],
                }
            )

        self.pending = waiting

    def next_boundary(self, time):
        # Keep positive release delays exact before admitting the field to the
        # older shared buff runtime, whose active checks use spatial epsilon.
        return min(
            (
                field["start_seconds"]
                for _, field in self.pending
                if field["start_seconds"] > time
            ),
            default=None,
        )

    def continuation_reasons(self, time):
        # A beneficial field without active attackers cannot damage a village.
        return []

    def result(self):
        return {
            "status": "EXPLICIT_UNCALIBRATED_GENERATED_DEATH_RAGE",
            "emitted": sorted(self.emitted),
            "fields": deepcopy(self.fields),
            "pending_fields": [
                {
                    "owner_actor_id": owner,
                    "field_id": field["id"],
                    "release_at": field["start_seconds"],
                }
                for owner, field in self.pending
            ],
        }
