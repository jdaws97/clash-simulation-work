"""Released spell damage, explicit repeated quakes, and independent visibility.

Poison shares the existing pulsed-hazard pipeline. Other damage enters the same
health batch as a source-attributed spell packet. Overgrowth preserves blocking
footprints and deliberately leaves the separate garrison release clock running.
"""

from collections import defaultdict
from copy import deepcopy
from math import hypot

from .attack_spell_models import (
    SPELL_CLASSES,
    poison_fields,
    validate_attack_spell,
)
from .battle_termination import continuation_fact
from .buffs import _circle_events
from .common import InputError, number
from .damage_receipts import record_damage
from .hazards import HAZARD_CLASSES, validate_hazard
from .rates import pause_attack_work
from .spatial import EPSILON, _active, center, target_distance
from .spell_visibility import untargetable_until


def _unit_class(actor):
    value = actor.get("hazard_class")
    if value not in HAZARD_CLASSES:
        raise InputError(
            "Spell-exposed units require an explicit supported hazard class"
        )
    return value


def _inside(model, actor):
    if model["parameters"]["geometry"] == "point_to_live_target_footprint":
        distance = target_distance(model["position"], actor)
    else:
        point = center(actor)
        distance = hypot(
            point[0] - model["position"][0], point[1] - model["position"][1]
        )
    return distance <= model["radius"] + EPSILON


def _pause(actor, time, until):
    pause_attack_work(actor, time, until)
    actor["frozen_until"] = max(actor["frozen_until"], until)


class AttackSpellCombat:
    """Own five paid-cast lifecycles without assigning an actor to a spell."""

    def __init__(self, models, actors, hazards):
        if not isinstance(models, list):
            raise InputError("Attacking spell models must be an explicit list")
        self.models = {}
        self.hazards = hazards
        self.launched = set()
        self.resolved = set()
        self.captured = {}
        self.quake_hits = defaultdict(int)
        self.boundary_sides = {}
        self.crossing_hints = {}
        self.last_time = None
        for model in models:
            validate_attack_spell(model)
            if model["id"] in self.models:
                raise InputError("Attacking spell cast IDs must be unique")
            self.models[model["id"]] = deepcopy(model)
            if model["entity"] == "poison-spell":
                for field in poison_fields(model):
                    validate_hazard(field, actors)
        quake_count = sum(model["entity"] == "earthquake-spell" for model in models)
        repeat_contract = None
        for model in models:
            if model["entity"] != "earthquake-spell":
                continue
            repeat = model["parameters"]["repeated_hits"]
            for table in ("building_multipliers", "unit_multipliers"):
                if len(repeat[table]) < quake_count:
                    raise InputError(
                        "Earthquake repeated-hit tables must cover every declared cast"
                    )
            if repeat_contract is not None and repeat != repeat_contract:
                raise InputError(
                    "All Earthquakes sharing target counters need the same repeated-hit contract"
                )
            repeat_contract = repeat
        if models:
            for actor in actors.values():
                if actor["kind"] == "unit":
                    _unit_class(actor)

    @staticmethod
    def _eligible(model, actor, time):
        if not _active(actor, time) or actor.get("_tesla_hidden", False):
            return False
        entity_id = model["entity"]
        if entity_id == "invisibility-spell":
            return actor["kind"] != "wall" and (
                actor["kind"] != "unit" or _unit_class(actor) != "siege"
            )
        if actor["team"] != "defense":
            return False
        if entity_id == "overgrowth-spell":
            return actor["kind"] in {"defense", "building"}
        if entity_id == "poison-spell":
            return actor["kind"] == "unit" and (
                model["parameters"]["class_scaling"][_unit_class(actor)] is not None
            )
        if (
            actor.get("entity_adapter", {}).get("entity")
            in model["parameters"]["excluded_entities"]
        ):
            return False
        if entity_id == "earthquake-spell" and actor["layer"] != "ground":
            return False
        return actor["kind"] in {"unit", "defense", "building", "wall"}

    @staticmethod
    def _live(model, time):
        return (
            model["arrival_seconds"] <= time + EPSILON
            and time
            < model["arrival_seconds"]
            + model["quantities"]["duration_seconds"]
            - EPSILON
        )

    def _field_inside(self, model, actor):
        key = model["id"], actor["id"]
        hint = self.boundary_sides.get(key)
        point = center(actor)
        if hint is not None:
            if (
                hypot(point[0] - hint["position"][0], point[1] - hint["position"][1])
                <= EPSILON * 128
            ):
                return hint["inside_after"]
            self.boundary_sides.pop(key)
        return _inside(model, actor)

    def _advance_hints(self, actors, time):
        for key, hint in list(self.crossing_hints.items()):
            if hint["time_seconds"] > time + EPSILON:
                continue
            point = center(actors[key[1]])
            if (
                abs(hint["time_seconds"] - time) <= EPSILON
                and hypot(
                    point[0] - hint["position"][0], point[1] - hint["position"][1]
                )
                <= EPSILON * 128
            ):
                self.boundary_sides[key] = hint
            self.crossing_hints.pop(key)

    def _launch(self, model, actors, time, trace):
        self.launched.add(model["id"])
        if model["entity"] == "poison-spell":
            for field in poison_fields(model):
                self.hazards.schedule(field, actors)
        trace.append(
            {
                "event": "attack_spell_cast",
                "time_seconds": time,
                "cast_id": model["id"],
                "entity": model["entity"],
                "arrival_seconds": model["arrival_seconds"],
                "position": list(model["position"]),
            }
        )

    def _capture_overgrowth(self, model, actors, time, trace):
        until = model["arrival_seconds"] + model["quantities"]["duration_seconds"]
        recipients = [
            actor
            for actor in actors.values()
            if self._eligible(model, actor, time) and _inside(model, actor)
        ]
        self.captured[model["id"]] = sorted(actor["id"] for actor in recipients)
        for actor in recipients:
            actor["immune_until"] = max(actor["immune_until"], until)
            # The castle's shared next_attack/frozen clock is its troop release
            # clock, not a weapon. Conceal/protect the building without pausing it.
            if "garrison_model" not in actor:
                _pause(actor, time, until)
        self.resolved.add(model["id"])
        trace.append(
            {
                "event": "overgrowth_capture",
                "time_seconds": time,
                "cast_id": model["id"],
                "targets": list(self.captured[model["id"]]),
                "expires_at_seconds": until,
                "collision_policy": model["parameters"]["collision_policy"],
            }
        )

    def prepare(self, actors, time, trace):
        number(time, "attacking spell time", 0)
        if self.last_time is not None and time < self.last_time - EPSILON:
            raise InputError("Attacking spells cannot move backward in time")
        self._advance_hints(actors, time)
        self.last_time = time
        for cast_id, model in sorted(
            self.models.items(), key=lambda item: (item[1]["time_seconds"], item[0])
        ):
            if cast_id not in self.launched and model["time_seconds"] <= time + EPSILON:
                self._launch(model, actors, time, trace)
            if (
                cast_id not in self.launched
                or model["arrival_seconds"] > time + EPSILON
            ):
                continue
            if model["entity"] == "overgrowth-spell" and cast_id not in self.resolved:
                self._capture_overgrowth(model, actors, time, trace)
            elif model["entity"] in {"invisibility-spell", "poison-spell"}:
                self.resolved.add(cast_id)
        for actor in actors.values():
            until, memberships = 0, []
            for cast_id in sorted(self.launched):
                model = self.models[cast_id]
                if model["entity"] not in {
                    "invisibility-spell",
                    "overgrowth-spell",
                } or not self._live(model, time):
                    continue
                if model["entity"] == "overgrowth-spell":
                    inside = _active(actor, time) and actor["id"] in self.captured.get(
                        cast_id, []
                    )
                else:
                    inside = self._eligible(model, actor, time) and self._field_inside(
                        model, actor
                    )
                if inside:
                    memberships.append(cast_id)
                    until = max(
                        until,
                        model["arrival_seconds"]
                        + model["quantities"]["duration_seconds"],
                    )
            if actor.get("_attack_spell_fields", []) != memberships:
                trace.append(
                    {
                        "event": "attack_spell_membership",
                        "time_seconds": time,
                        "target": actor["id"],
                        "fields": memberships,
                        "untargetable_until": until,
                    }
                )
            actor["_attack_spell_fields"] = memberships
            actor["_attack_spell_untargetable_until"] = until
        for actor in actors.values():
            target = actors.get(actor.get("target"))
            if target is not None and untargetable_until(target) > time + EPSILON:
                actor["target"] = None
                actor.pop("_remaining_path", None)
                actor.pop("_path_signature", None)
        # Newly deployed or released units acquire the shared slow immediately;
        # field pulses retain their independent scheduled cadence.
        self.hazards.prepare_status(actors, time, trace)

    def _quake_damage(self, model, actor, hp, time):
        parameters = model["parameters"]
        repeat = parameters["repeated_hits"]
        index = self.quake_hits[actor["id"]]
        protected = actor["immune_until"] > time + EPSILON
        if not protected or repeat["protected_hits"] == "advance_counter":
            self.quake_hits[actor["id"]] += 1
        if actor["kind"] == "wall":
            if index >= 3:
                return hp, index + 1
            factor = repeat["wall_damage_multipliers"][index]
            fraction = model["quantities"]["building_fraction"]
            floor = 0
        elif actor["kind"] == "unit":
            factor = repeat["unit_multipliers"][index]
            factor *= parameters["unit_damage_multipliers"][_unit_class(actor)]
            fraction = model["quantities"]["unit_fraction"]
            floor = repeat["unit_hp_floor"]
        else:
            factor = repeat["building_multipliers"][index]
            fraction = model["quantities"]["building_fraction"]
            floor = repeat["structure_hp_floor"]
        return (
            min(actor["maximum_hp"] * fraction * factor, max(hp - floor, 0)),
            index + 1,
        )

    def resolve(self, actors, time, trace, status_observer=None):
        """Resolve due direct casts after field protection, before shared health."""
        damage = defaultdict(float)
        virtual_hp = {key: actor["hp"] for key, actor in actors.items()}
        pending = sorted(
            (model["arrival_seconds"], cast_id)
            for cast_id, model in self.models.items()
            if cast_id in self.launched
            and cast_id not in self.resolved
            and model["entity"] in {"lightning-spell", "earthquake-spell"}
            and model["arrival_seconds"] <= time + EPSILON
        )
        for _, cast_id in pending:
            model = self.models[cast_id]
            parameters = model["parameters"]
            stunned = []
            for actor_id, actor in sorted(actors.items()):
                if (
                    not self._eligible(model, actor, time)
                    or not _inside(model, actor)
                    or virtual_hp[actor_id] <= EPSILON
                ):
                    continue
                hit_number = None
                if model["entity"] == "earthquake-spell":
                    if (
                        actor["kind"] == "unit"
                        and model["quantities"]["unit_fraction"] <= 0
                    ):
                        continue
                    amount, hit_number = self._quake_damage(
                        model, actor, virtual_hp[actor_id], time
                    )
                else:
                    amount = model["quantities"]["damage"]
                    if actor["kind"] == "unit":
                        amount *= parameters["unit_damage_multipliers"][
                            _unit_class(actor)
                        ]
                    protected = actor["immune_until"] > time + EPSILON
                    if model["quantities"]["stun_seconds"] > EPSILON and (
                        not protected
                        or parameters["status_protection"]
                        == "damage_immunity_does_not_block_status"
                    ):
                        stunned.append(actor_id)
                resolved = record_damage(
                    self,
                    actor,
                    amount,
                    time,
                    source_id=cast_id,
                    source_team="attack",
                    origin="spell",
                )
                damage[actor_id] += resolved
                virtual_hp[actor_id] = max(virtual_hp[actor_id] - resolved, 0)
                trace.append(
                    {
                        "event": "attack_spell_impact",
                        "time_seconds": time,
                        "cast_id": cast_id,
                        "entity": model["entity"],
                        "target": actor_id,
                        "requested_damage": amount,
                        "resolved_damage": resolved,
                        "quake_hit_number": hit_number,
                    }
                )
            if stunned:
                duration = model["quantities"]["stun_seconds"]
                command = {
                    "id": f"{cast_id}:stun",
                    "kind": "freeze",
                    "time_seconds": time,
                    "targets": stunned,
                    "duration_seconds": duration,
                    "source": model["source"],
                }
                if status_observer is not None:
                    status_observer([command], actors, time, trace)
                for actor_id in stunned:
                    _pause(actors[actor_id], time, time + duration)
                trace.append(
                    {
                        "event": "lightning_stun",
                        "time_seconds": time,
                        "cast_id": cast_id,
                        "targets": stunned,
                        "until_seconds": time + duration,
                    }
                )
            self.resolved.add(cast_id)
        return damage

    def next_boundary(self, time):
        boundaries = []
        for cast_id, model in self.models.items():
            if cast_id not in self.launched:
                boundaries.append(model["time_seconds"])
            if cast_id not in self.resolved:
                boundaries.append(model["arrival_seconds"])
            if "duration_seconds" in model["quantities"] and cast_id in self.launched:
                boundaries.append(
                    model["arrival_seconds"] + model["quantities"]["duration_seconds"]
                )
        future = [value for value in boundaries if value > time + EPSILON]
        return min(future) if future else None

    def first_crossing_delay(self, actor, route, time, horizon, effective_speed):
        """Continuous point-unit field crossings, including forced movement."""
        speed = number(effective_speed, "spell-field crossing speed", 0)
        if speed <= EPSILON or horizon <= EPSILON:
            return None
        if actor["width"] != 0 or actor["height"] != 0:
            raise InputError(
                "Spell-field movement requires the shared point-unit convention"
            )
        earliest = None
        for cast_id in sorted(self.launched):
            model = self.models[cast_id]
            if (
                model["entity"] not in {"poison-spell", "invisibility-spell"}
                or not self._live(model, time)
                or not self._eligible(model, actor, time)
            ):
                continue
            key = cast_id, actor["id"]
            self.crossing_hints.pop(key, None)
            poison = model["entity"] == "poison-spell"
            inside = (
                _inside(model, actor) if poison else self._field_inside(model, actor)
            )
            previous, traveled = center(actor), 0
            found = False
            for point_index, point in enumerate(route):
                length = hypot(point[0] - previous[0], point[1] - previous[1])
                for contact, inside_after in _circle_events(
                    previous, point, model["position"], model["radius"]
                ):
                    if abs(contact - length) <= EPSILON:
                        for following in route[point_index + 1 :]:
                            direction = following[0] - point[0], following[1] - point[1]
                            if hypot(*direction) <= EPSILON:
                                continue
                            projection = sum(
                                (point[index] - model["position"][index])
                                * direction[index]
                                for index in (0, 1)
                            )
                            inside_after = projection < -EPSILON
                            break
                    if inside_after == inside:
                        continue
                    if traveled + contact <= speed * EPSILON:
                        contact = max(contact, speed * EPSILON * 2, EPSILON * 4)
                    delay = (traveled + contact) / speed
                    if (
                        delay <= EPSILON
                        or delay > horizon + EPSILON
                        or contact > length + EPSILON
                    ):
                        continue
                    fraction = min(contact / length, 1)
                    position = tuple(
                        previous[index] + (point[index] - previous[index]) * fraction
                        for index in (0, 1)
                    )
                    if not poison:
                        self.crossing_hints[key] = {
                            "time_seconds": time + delay,
                            "position": position,
                            "inside_after": inside_after,
                        }
                    earliest = min(earliest, delay) if earliest is not None else delay
                    found = True
                    break
                if found:
                    break
                traveled += length
                if traveled >= speed * horizon - EPSILON:
                    break
                previous = point
        return earliest

    def continuation_reasons(self, time):
        """Report released direct offense; shared hazards own Poison continuation."""
        facts = []
        for cast_id in sorted(self.launched - self.resolved):
            model = self.models[cast_id]
            if (
                SPELL_CLASSES[model["entity"]] != "damage"
                or model["entity"] == "poison-spell"
            ):
                continue
            quantities = model["quantities"]
            if not any(
                quantities.get(key, 0) > 0
                for key in ("damage", "building_fraction", "unit_fraction")
            ):
                continue
            facts.append(
                continuation_fact(
                    "pending_damage",
                    f"spell:{cast_id}",
                    not_before_seconds=model["arrival_seconds"],
                )
            )
        return facts

    def frame(self, actor):
        return {
            "attack_spell_fields": list(actor.get("_attack_spell_fields", [])),
            "attack_spell_untargetable_until": actor.get(
                "_attack_spell_untargetable_until", 0
            ),
        }

    def result(self):
        return {
            "launched": sorted(self.launched),
            "resolved": sorted(self.resolved),
            "pending_at_horizon": sorted(self.launched - self.resolved),
            "quake_hits": dict(self.quake_hits),
            "overgrowth_recipients": deepcopy(self.captured),
            "behavior_verification": "explicit_uncalibrated_spell_contract",
        }
