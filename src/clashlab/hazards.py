"""Explicit persistent damage areas with live membership and status clocks.

Pulse timing, growth, lingering and overlap are experiment inputs. This module
does not infer the game's poison curve or substitute for replay calibration.
"""

from collections import defaultdict
from copy import deepcopy

from .combat import validate_area_effect
from .common import InputError, identifier, number, require
from .rates import rescale_remaining_cooldown
from .spatial import EPSILON, _active, target_distance


HAZARD_CLASSES = {
    "troop",
    "hero",
    "pet",
    "siege",
    "defending_troop",
    "builder",
    "guardian",
}
PROTECTION_POLICIES = {
    "damage_immunity_does_not_block_status",
    "damage_immunity_also_blocks_status",
}


def validate_hazard(field, actors):
    expected = {
        "id",
        "source",
        "start_seconds",
        "duration_seconds",
        "pulse_interval_seconds",
        "first_pulse_offset_seconds",
        "maximum_dps",
        "growth_by_field_age",
        "area",
        "movement_multiplier",
        "attack_rate_multiplier",
        "exit_linger_seconds",
        "protection_policy",
        "excluded_classes",
    }
    if set(field) - {"guardian_damage_multiplier", "source_team"} != expected:
        raise InputError("A hazard must explicitly supply every supported field")
    if "source_team" in field and field["source_team"] not in {
        "attack",
        "defense",
        "environment",
    }:
        raise InputError("Persistent damage needs explicit source ownership")
    if "guardian_damage_multiplier" in field:
        number(
            field["guardian_damage_multiplier"], "Guardian hazard damage multiplier", 0
        )
    identifier(field["id"], "hazard id")
    identifier(field["source"], "hazard evidence")
    number(field["start_seconds"], "hazard start", 0)
    duration = number(field["duration_seconds"], "hazard duration", EPSILON)
    number(field["pulse_interval_seconds"], "hazard pulse interval", EPSILON)
    first = number(field["first_pulse_offset_seconds"], "first hazard pulse", 0)
    if first >= duration:
        raise InputError("First hazard pulse must occur before the field expires")
    number(field["maximum_dps"], "maximum hazard DPS", 0)
    number(field["movement_multiplier"], "hazard movement multiplier", EPSILON, 1)
    number(field["attack_rate_multiplier"], "hazard attack rate", EPSILON, 1)
    number(field["exit_linger_seconds"], "hazard exit linger", 0)
    if field["protection_policy"] not in PROTECTION_POLICIES:
        raise InputError("Hazard protection/status behavior must be selected")
    exclusions = field["excluded_classes"]
    if (
        not isinstance(exclusions, list)
        or len(exclusions) != len(set(exclusions))
        or not set(exclusions) <= HAZARD_CLASSES
    ):
        raise InputError("Hazard exclusions must name unique supported classes")
    growth = field["growth_by_field_age"]
    if not isinstance(growth, list) or not growth:
        raise InputError("Hazard damage needs an explicit field-age growth curve")
    previous_age = -1
    previous_multiplier = 0
    for index, stage in enumerate(growth):
        if set(stage) != {"after_seconds", "dps_multiplier"}:
            raise InputError("Hazard growth stages need age and DPS multiplier")
        age = number(stage["after_seconds"], "hazard growth age", 0)
        multiplier = number(stage["dps_multiplier"], "hazard growth DPS", 0, 1)
        if age <= previous_age or age >= duration or multiplier < previous_multiplier:
            raise InputError("Hazard growth stages must rise within the field lifetime")
        if index == 0 and age != 0:
            raise InputError("Hazard growth must explicitly start at age zero")
        previous_age = age
        previous_multiplier = multiplier
    area = field["area"]
    if set(area) != {
        "x",
        "y",
        "radius",
        "target_team",
        "target_kinds",
        "target_layers",
    }:
        raise InputError("Hazard areas need explicit geometry and target filters")
    if area["target_kinds"] != ["unit"]:
        raise InputError("This persistent hazard model supports unit targets")
    validate_area_effect(
        {
            "id": field["id"],
            "kind": "area_damage",
            "time_seconds": field["start_seconds"],
            "amount": 0,
            "area": deepcopy(area),
        },
        actors,
    )
    for actor in actors.values():
        if actor["kind"] == "unit" and actor.get("hazard_class") not in HAZARD_CLASSES:
            raise InputError("Every unit exposed to hazards needs an explicit class")
        if (
            actor.get("hazard_class") == "guardian"
            and actor["team"] == area["target_team"]
            and "guardian" not in field["excluded_classes"]
            and "guardian_damage_multiplier" not in field
        ):
            raise InputError(
                "Hazards affecting Guardians need a separate explicit damage multiplier"
            )
    return field


class PulsedHazards:
    """Additive pulse damage and the strongest live or lingering slow effect."""

    def __init__(self, actors, fields):
        self.fields = {}
        self.source_actor_ids = {}
        self.next_pulses = {}
        self.exposure_expiry = {}
        self.previous_membership = {}
        for field in fields:
            self.schedule(field, actors)

    def schedule(self, field, actors, source_actor_id=None):
        validate_hazard(field, actors)
        if field["id"] in self.fields:
            raise InputError("Persistent hazard ids must be unique")
        self.fields[field["id"]] = deepcopy(field)
        if source_actor_id is not None and source_actor_id not in actors:
            raise InputError("Hazard attribution requires a known source actor")
        if (
            source_actor_id is not None
            and field.get("source_team", actors[source_actor_id]["team"])
            != actors[source_actor_id]["team"]
        ):
            raise InputError("Hazard source actor and declared team disagree")
        self.source_actor_ids[field["id"]] = source_actor_id
        self.next_pulses[field["id"]] = (
            field["start_seconds"] + field["first_pulse_offset_seconds"]
        )

    def _inside(self, field, actor, time):
        area = field["area"]
        return (
            _active(actor, time)
            and "spell_decoy_model" not in actor
            and actor["team"] == area["target_team"]
            and actor["kind"] in area["target_kinds"]
            and actor["layer"] in area["target_layers"]
            and actor["hazard_class"] not in field["excluded_classes"]
            and target_distance((area["x"], area["y"]), actor)
            <= area["radius"] + EPSILON
        )

    def _live(self, field, time):
        return (
            field["start_seconds"] <= time + EPSILON
            and time < field["start_seconds"] + field["duration_seconds"] - EPSILON
        )

    def prepare_status(self, actors, time, trace):
        for actor in actors.values():
            movement = 1
            attack_rate = 1
            active_fields = []
            if _active(actor, time) and actor["kind"] == "unit":
                for field_id, field in self.fields.items():
                    inside = self._live(field, time) and self._inside(
                        field, actor, time
                    )
                    key = field_id, actor["id"]
                    if inside:
                        self.exposure_expiry[key] = time + field["exit_linger_seconds"]
                    elif self.previous_membership.get(key, False):
                        self.exposure_expiry[key] = time + field["exit_linger_seconds"]
                    self.previous_membership[key] = inside
                    lingering = self.exposure_expiry.get(key, 0) > time + EPSILON
                    if not inside and not lingering:
                        continue
                    if (
                        field["protection_policy"]
                        == "damage_immunity_also_blocks_status"
                        and actor["immune_until"] > time + EPSILON
                    ):
                        continue
                    movement = min(movement, field["movement_multiplier"])
                    attack_rate = min(attack_rate, field["attack_rate_multiplier"])
                    active_fields.append(field_id)
            old_rate = actor.get("_hazard_attack_rate", 1)
            if abs(old_rate - attack_rate) > EPSILON:
                rescale_remaining_cooldown(actor, time, old_rate, attack_rate)
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "hazard_status_change",
                        "target": actor["id"],
                        "old_attack_rate": old_rate,
                        "attack_rate": attack_rate,
                        "movement_multiplier": movement,
                        "fields": active_fields,
                    }
                )
            actor["_hazard_attack_rate"] = attack_rate
            actor["_hazard_movement_multiplier"] = movement
            actor["_hazard_fields"] = active_fields

    def resolve(self, actors, time, trace):
        from .damage_receipts import record_damage

        damage = defaultdict(float)
        for field_id in sorted(self.fields):
            field = self.fields[field_id]
            next_pulse = self.next_pulses[field_id]
            if not self._live(field, time) or next_pulse > time + EPSILON:
                continue
            age = time - field["start_seconds"]
            multiplier = field["growth_by_field_age"][0]["dps_multiplier"]
            for stage in field["growth_by_field_age"]:
                if stage["after_seconds"] <= age + EPSILON:
                    multiplier = stage["dps_multiplier"]
            amount = field["maximum_dps"] * multiplier * field["pulse_interval_seconds"]
            targets = []
            protected = []
            for actor in actors.values():
                if not self._inside(field, actor, time):
                    continue
                targets.append(actor["id"])
                if actor["immune_until"] > time + EPSILON:
                    protected.append(actor["id"])
                guardian_factor = (
                    field.get("guardian_damage_multiplier", 1)
                    if actor.get("hazard_class") == "guardian"
                    else 1
                )
                source_id = self.source_actor_ids[field_id]
                resolved = record_damage(
                    self,
                    actor,
                    amount * guardian_factor,
                    time,
                    source_id=field_id,
                    source_actor_id=source_id,
                    source_team=(
                        actors[source_id]["team"]
                        if source_id is not None
                        else field.get("source_team", "environment")
                    ),
                    origin="hazard",
                )
                if resolved > 0:
                    damage[actor["id"]] += resolved
            trace.append(
                {
                    "time_seconds": time,
                    "event": "hazard_pulse",
                    "field": field_id,
                    "targets": sorted(targets),
                    "protected_targets": sorted(protected),
                    "requested_damage_per_target": amount,
                    "dps_multiplier": multiplier,
                }
            )
            self.next_pulses[field_id] = next_pulse + field["pulse_interval_seconds"]
        return damage

    def next_boundary(self, time):
        boundaries = []
        for field_id, field in self.fields.items():
            boundaries.extend(
                (
                    field["start_seconds"],
                    field["start_seconds"] + field["duration_seconds"],
                    self.next_pulses[field_id],
                )
            )
        boundaries.extend(self.exposure_expiry.values())
        future = [value for value in boundaries if value > time + EPSILON]
        return min(future) if future else None

    def frame(self, actor):
        if actor["kind"] != "unit":
            return {}
        return {
            "hazard_movement_multiplier": actor.get("_hazard_movement_multiplier", 1),
            "hazard_attack_rate": actor.get("_hazard_attack_rate", 1),
            "hazard_fields": list(actor.get("_hazard_fields", [])),
        }

    def result(self):
        return {
            "fields": deepcopy(self.fields),
            "next_pulses": deepcopy(self.next_pulses),
        }
