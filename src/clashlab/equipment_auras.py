"""Explicit moving Warden equipment fields, distinct from paid spell fields.

Pinned equipment rows supply strengths; radius, recipients, stacking and HP
transformations require an opt-in contract. Moving circle boundaries use the
shared path segment/contact helpers. The integrator owns field factor binding.
"""

from copy import deepcopy
from math import floor, hypot

from .common import InputError, identifier, integer, number
from .hero_extensions import source_quantity
from .rates import rescale_remaining_cooldown
from .range_events import _contacts, _position, _segments
from .spatial import EPSILON, _active, center


OWNERS = {key: "grand-warden" for key in ("rage-gem", "life-gem", "heroic-torch")}
POLICIES = {
    "experimental_policy": "moving_warden_fields_v1_uncalibrated",
    "membership": "continuous_center_distance_while_source_active",
    "stacking": "strongest_per_axis_multiply_external_sources",
    "freeze": "field_and_absolute_duration_continue",
    "recall": "inactive_source_emits_no_field_absolute_duration_continues",
    "hp_transform": "preserve_positive_hp_fraction_without_reviving_zero",
    "torch_owner_reduction": "catalog_damageReductionIncrease_flat_per_packet_passive_experimental",
    "torch_wall_expiry": "retain_jump_until_outside_enemy_wall_then_restore",
}
MODEL_FIELDS = {
    "entity",
    "level",
    "ability_type",
    "source",
    "parameters",
    "damage_bonus",
    "hp_bonus_fraction",
    "hp_bonus_cap",
    "movement_bonus",
    "incoming_multiplier",
    "duration_seconds",
    "owner_attack_rate",
    "owner_flat_reduction",
}


def validate_equipment(model):
    if (
        not isinstance(model, dict)
        or set(model) != MODEL_FIELDS
        or model["entity"] not in OWNERS
    ):
        raise InputError("Warden aura requires a complete supported equipment model")
    identifier(model["source"], "aura statistics source")
    integer(model["level"], "aura level", 1)
    expected = "Active" if model["entity"] == "heroic-torch" else "Passive"
    if model["ability_type"] != expected:
        raise InputError("Warden field activation type mismatch")
    parameters = model["parameters"]
    if not isinstance(parameters, dict) or set(parameters) != {
        "source",
        "radius_tiles",
        "recipient_classes",
        "include_owner",
        *POLICIES,
    }:
        raise InputError("Warden aura needs explicit geometry and recipient policies")
    identifier(parameters["source"], "aura behavior provenance")
    if any(parameters[key] != value for key, value in POLICIES.items()):
        raise InputError("Unsupported Warden aura experimental policy")
    number(parameters["radius_tiles"], "aura radius", EPSILON)
    classes = parameters["recipient_classes"]
    if (
        not isinstance(classes, list)
        or not classes
        or len(classes) != len(set(classes))
        or not set(classes) <= {"troop", "hero", "pet", "siege"}
    ):
        raise InputError("Aura requires unique explicit recipient classes")
    if not isinstance(parameters["include_owner"], bool):
        raise InputError("Aura owner membership must be explicit")
    for field in MODEL_FIELDS - {
        "entity",
        "level",
        "ability_type",
        "source",
        "parameters",
    }:
        number(model[field], field, 1 if field == "owner_attack_rate" else 0)
    number(model["incoming_multiplier"], "aura incoming multiplier", 0, 1)
    if model["entity"] == "heroic-torch" and set(classes) != {"troop"}:
        raise InputError("Experimental Torch supports ordinary troop recipients only")


def compile_equipment(instance, hero, catalog, conversion):
    if set(instance) != {"entity", "level", "parameters"}:
        raise InputError("Aura equipment requires complete instance parameters")
    entity_id = instance["entity"]
    if entity_id not in OWNERS or hero["entity"] != OWNERS[entity_id]:
        raise InputError("Warden aura equipment owner mismatch")
    level = integer(instance["level"], "aura equipment level", 1)
    if not catalog.available(entity_id, level, hero["town_hall"]):
        raise InputError("Aura equipment unavailable at selected Town Hall")
    entity = catalog.entity(entity_id)
    row = catalog.level(entity_id, level)
    stats = row["stats"]
    model = {
        "entity": entity_id,
        "level": level,
        "ability_type": entity["abilityType"],
        "source": catalog.records[entity_id]["source"],
        "parameters": deepcopy(instance["parameters"]),
        "damage_bonus": 0,
        "hp_bonus_fraction": 0,
        "hp_bonus_cap": 0,
        "movement_bonus": 0,
        "incoming_multiplier": 1,
        "duration_seconds": 0,
        "owner_attack_rate": 1,
        "owner_flat_reduction": 0,
    }
    if entity_id == "rage-gem":
        model["damage_bonus"] = (
            source_quantity(stats["damageIncreasePercent"], "%") / 100
        )
        model["owner_attack_rate"] = (
            1
            + source_quantity(
                stats["attackSpeedIncrease"], "%", allow_leading_plus=True
            )
            / 100
        )
    elif entity_id == "life-gem":
        model["hp_bonus_fraction"] = (
            source_quantity(stats["hpIncreasePercent"], "%") / 100
        )
        model["hp_bonus_cap"] = number(stats["maxHpIncrease"], "Life Gem HP cap", 0)
    else:
        model["duration_seconds"] = source_quantity(stats["abilityDuration"], "s")
        model["movement_bonus"] = number(
            stats["speedIncrease"], "Torch movement units", 0
        ) / number(conversion, "movement conversion", EPSILON)
        model["incoming_multiplier"] = (
            1 - source_quantity(stats["incomingDamageReduction"], "%") / 100
        )
        model["owner_flat_reduction"] = number(
            stats["damageReductionIncrease"],
            "experimental Torch owner flat reduction",
            0,
        )
    validate_equipment(model)
    return model, row


class EquipmentAuraCombat:
    def __init__(self, actors):
        self.models = {}
        self.expiry = {}
        self.used = set()
        self.base_hp = {key: actor["maximum_hp"] for key, actor in actors.items()}
        self.last_hp = dict(self.base_hp)
        self.saved_walls = {}
        self.crossings = {}
        self.boundary_sides = {}
        self.members = {}
        self.log = []
        for key, actor in actors.items():
            for item in actor.get("hero_model", {}).get("equipment", []):
                if item["entity"] in OWNERS:
                    validate_equipment(item)
                    if actor["hero_model"]["entity"] != OWNERS[item["entity"]]:
                        raise InputError("Warden field runtime owner mismatch")
                    self.models[(key, item["entity"])] = deepcopy(item)

    def activate(self, hero_id, actors, time, trace):
        if hero_id in self.used or not _active(actors[hero_id], time):
            return
        self.used.add(hero_id)
        for key, model in self.models.items():
            if key[0] == hero_id and model["ability_type"] == "Active":
                self.expiry[key] = time + model["duration_seconds"]

    def _live(self, key, actors, time):
        return _active(actors[key[0]], time) and (
            self.models[key]["ability_type"] == "Passive"
            or self.expiry.get(key, 0) > time
        )

    def _eligible(self, key, actor, actors, time):
        parameters = self.models[key]["parameters"]
        return (
            _active(actor, time)
            and actor["kind"] == "unit"
            and actor["team"] == actors[key[0]]["team"]
            and not actor.get("beneficial_field_immunity", False)
            and actor.get("buff_class") in parameters["recipient_classes"]
            and (parameters["include_owner"] or actor["id"] != key[0])
        )

    def prepare(self, actors, time, trace):
        if not self.models:
            return
        for pair, hint in list(self.crossings.items()):
            if hint["time"] <= time:
                if hint["time"] == time:
                    self.boundary_sides[pair] = hint
                del self.crossings[pair]
        factors = {
            key: {
                "damage": 0,
                "movement": 0,
                "incoming": 1,
                "hp": 0,
                "torch": False,
                "rate": 1,
                "owner_flat": 0,
            }
            for key in actors
        }
        for key, model in self.models.items():
            source = actors[key[0]]
            factors[key[0]]["rate"] *= model["owner_attack_rate"]
            factors[key[0]]["owner_flat"] = max(
                factors[key[0]]["owner_flat"], model["owner_flat_reduction"]
            )
            live = self._live(key, actors, time)
            members = []
            for actor_id, actor in actors.items():
                pair = key, actor_id
                relative = (
                    center(actor)[0] - center(source)[0],
                    center(actor)[1] - center(source)[1],
                )
                side = self.boundary_sides.get(pair)
                if (
                    side
                    and hypot(
                        relative[0] - side["relative"][0],
                        relative[1] - side["relative"][1],
                    )
                    <= EPSILON * 128
                ):
                    inside = side["inside"]
                else:
                    self.boundary_sides.pop(pair, None)
                    inside = hypot(*relative) <= model["parameters"]["radius_tiles"]
                if (
                    not live
                    or not inside
                    or not self._eligible(key, actor, actors, time)
                ):
                    continue
                members.append(actor_id)
                entry = factors[actor_id]
                entry["damage"] = max(entry["damage"], model["damage_bonus"])
                entry["movement"] = max(entry["movement"], model["movement_bonus"])
                entry["incoming"] = min(entry["incoming"], model["incoming_multiplier"])
                entry["hp"] = max(
                    entry["hp"],
                    min(
                        self.base_hp[actor_id] * model["hp_bonus_fraction"],
                        model["hp_bonus_cap"],
                    ),
                )
                entry["torch"] |= model["entity"] == "heroic-torch"
            if self.members.get(key, []) != members:
                entry = {
                    "time_seconds": time,
                    "event": "equipment_field_membership",
                    "source": key[0],
                    "equipment": key[1],
                    "recipients": members,
                    "experimental": True,
                }
                trace.append(entry)
                self.log.append(deepcopy(entry))
            self.members[key] = members
        for key, actor in actors.items():
            values = factors[key]
            old_rate = actor.get("_equipment_field_attack_rate", 1)
            if old_rate != values["rate"]:
                rescale_remaining_cooldown(actor, time, old_rate, values["rate"])
            actor["_equipment_field_attack_rate"] = values["rate"]
            actor["_equipment_owner_flat_reduction"] = values["owner_flat"]
            actor["_equipment_field_damage_multiplier"] = 1 + values["damage"]
            actor["_equipment_field_movement_bonus"] = values["movement"]
            actor["_equipment_field_incoming_multiplier"] = values["incoming"]
            if any(model["entity"] == "life-gem" for model in self.models.values()):
                total_hp = self.base_hp[key] + values["hp"]
                if actor["maximum_hp"] != self.last_hp[key]:
                    raise InputError(
                        "Concurrent maximum-HP mutation requires the central HP modifier ledger"
                    )
                if actor["maximum_hp"] != total_hp:
                    previous_hp = actor["maximum_hp"]
                    if actor["hp"] > 0:
                        actor["hp"] *= total_hp / actor["maximum_hp"]
                    actor["maximum_hp"] = total_hp
                    entry = {
                        "time_seconds": time,
                        "event": "equipment_life_hp_change",
                        "target": key,
                        "previous_maximum_hp": previous_hp,
                        "maximum_hp": total_hp,
                        "hp": actor["hp"],
                        "experimental": True,
                    }
                    trace.append(entry)
                    self.log.append(deepcopy(entry))
                self.last_hp[key] = total_hp
            if values["torch"] and actor["movement"] == "ground":
                if key not in self.saved_walls:
                    self.saved_walls[key] = deepcopy(actor["wall_behavior"])
                    actor.pop("_path_signature", None)
                    actor.pop("_remaining_path", None)
                actor["wall_behavior"] = {
                    "kind": "jump_enemy_walls",
                    "source": "explicit-equipment-torch-field",
                }
            elif key in self.saved_walls:
                cell = floor(actor["x"]), floor(actor["y"])
                inside_wall = any(
                    other["kind"] == "wall"
                    and other["team"] != actor["team"]
                    and _active(other, time)
                    and cell == (floor(other["x"]), floor(other["y"]))
                    for other in actors.values()
                )
                if not inside_wall:
                    actor["wall_behavior"] = self.saved_walls.pop(key)
                    actor.pop("_path_signature", None)
                    actor.pop("_remaining_path", None)

    def next_boundary(self, time):
        values = [expiry for expiry in self.expiry.values() if expiry > time]
        return min(values) if values else None

    def first_crossing_delay(self, actors, routes, speeds, time, horizon):
        candidates = []
        for key, model in self.models.items():
            if not self._live(key, actors, time):
                continue
            source = actors[key[0]]
            source_segments = _segments(
                source, routes.get(key[0], []), speeds.get(key[0], 0), horizon
            )
            for actor_id, actor in actors.items():
                if not self._eligible(key, actor, actors, time) or actor_id == key[0]:
                    continue
                target_segments = _segments(
                    actor, routes.get(actor_id, []), speeds.get(actor_id, 0), horizon
                )
                for first in source_segments:
                    for second in target_segments:
                        start, end = max(first[0], second[0]), min(first[1], second[1])
                        if end <= start:
                            continue
                        source_point, target_point = _position(first, start), _position(
                            second, start
                        )
                        relative = (
                            target_point[0] - source_point[0],
                            target_point[1] - source_point[1],
                        )
                        velocity = (
                            second[3][0] - first[3][0],
                            second[3][1] - first[3][1],
                        )
                        for offset in _contacts(
                            relative,
                            velocity,
                            0,
                            0,
                            model["parameters"]["radius_tiles"],
                            end - start,
                        ):
                            delay = start + offset
                            if delay <= 0 or time + delay <= time:
                                continue
                            contact = (
                                relative[0] + velocity[0] * offset,
                                relative[1] + velocity[1] * offset,
                            )
                            inside_after = (
                                contact[0] * velocity[0] + contact[1] * velocity[1] < 0
                            )
                            candidates.append(
                                (delay, key, actor_id, contact, inside_after)
                            )
        self.crossings.clear()
        if not candidates:
            return None
        earliest = min(value[0] for value in candidates)
        for delay, key, actor_id, relative, inside in candidates:
            if delay == earliest:
                self.crossings[(key, actor_id)] = {
                    "time": time + delay,
                    "relative": relative,
                    "inside": inside,
                }
        return earliest

    def result(self):
        return {
            "membership_changes": self.log,
            "experimental": True,
            "calibrated": False,
        }
