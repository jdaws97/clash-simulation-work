"""Moving ally healing and persistent fields with declared behavior conventions.

Healer targeting, splash and stacking remain caller-supplied hypotheses. These
components share live HP, movement, protection and deployments with combat.
"""

from collections import defaultdict
from copy import deepcopy
from .buffs import healing_multiplier
from heapq import heappop, heappush
from math import hypot

from .combat import validate_pattern
from .common import InputError, identifier, integer, number, require
from .range_events import first_weapon_range_entry_delay
from .spatial import EPSILON, _active, _remember_route, _route, center, target_distance
from .walls import WALL_RULES


RULESET = "spatial-support-and-wall-kernel-v4"
SUPPORT_RULES = {
    **WALL_RULES,
    "healing_targeting": "explicit_allied_target_filter_selection_and_retention",
    "healing_stacking": "assigned_in_range_unfrozen_and_due_packets_per_recipient",
    "healing_flight": "launched_healing_survives_source_loss_or_freeze",
    "healing_primary_loss": "inactive_primary_fizzles_the_packet",
    "healing_health_phase": "damage_then_healing_without_resurrection",
    "healing_fields": "fixed_area_membership_recomputed_at_each_declared_pulse",
}
CLASSES = {"troop", "hero", "guardian", "siege", "pet"}
FIELD_KIND = "healing_field"
AREA_COMMANDS = {FIELD_KIND}


def _classes(values):
    if (
        not isinstance(values, list)
        or not values
        or len(values) != len(set(values))
        or not set(values) <= CLASSES
    ):
        raise InputError("Healing classes must be unique supported explicit values")


def _amounts(values, classes):
    if not isinstance(values, dict) or set(values) != set(classes):
        raise InputError("Every selected healing class needs an explicit pulse amount")
    for value in values.values():
        number(value, "healing per pulse", 0)


def validate_healing_field(field, actors):
    identifier(require(field, "id"), "healing field id")
    identifier(require(field, "source"), "healing field evidence")
    if require(field, "kind") != FIELD_KIND or "targets" in field:
        raise InputError("Healing fields cannot preselect their pulse membership")
    number(require(field, "time_seconds"), "healing field command time", 0)
    number(require(field, "first_pulse_delay_seconds"), "first field pulse delay", 0)
    integer(require(field, "pulse_count"), "healing field pulse count", 1)
    number(require(field, "pulse_interval_seconds"), "field pulse interval", EPSILON)
    area = require(field, "area")
    for coordinate in ("x", "y"):
        number(require(area, coordinate), f"field {coordinate}")
    number(require(area, "radius"), "healing field radius", 0)
    if require(area, "target_team") not in {actor["team"] for actor in actors.values()}:
        raise InputError("Healing fields need an explicit known target team")
    if require(area, "target_kinds") != ["unit"]:
        raise InputError("Healing buildings, walls and repairs require other adapters")
    layers = require(area, "target_layers")
    if (
        not isinstance(layers, list)
        or not layers
        or len(layers) != len(set(layers))
        or not set(layers) <= {"ground", "air"}
    ):
        raise InputError("Healing field target layers must be explicit")
    _classes(require(area, "target_classes"))
    _amounts(require(field, "amounts_by_class"), area["target_classes"])


def validate_healing_model(model, actors):
    if require(model, "kind") not in {"single", "radial"}:
        raise InputError("Other healing patterns need their complete behavior adapters")
    identifier(require(model, "source"), "healing behavior evidence")
    if require(model, "target_kinds") != ["unit"]:
        raise InputError("Moving troop healers cannot replace builder repair")
    _classes(require(model, "target_classes"))
    _amounts(require(model, "amounts_by_class"), model["target_classes"])
    pattern = {
        "kind": model["kind"],
        "source": model["source"],
        "target_kinds": model["target_kinds"],
        "target_layers": require(model, "target_layers"),
        "maximum_hp_fraction": 0,
        "projectile": require(model, "projectile"),
    }
    if model["kind"] == "radial":
        pattern["radius"] = require(model, "radius")
    validate_pattern(pattern)
    identifier(require(model, "stacking_group"), "healing stacking group")
    selector = require(model, "selector")
    identifier(require(selector, "source"), "healing target selection evidence")
    if require(selector, "selection") not in {
        "closest_eligible",
        "lowest_hp_fraction_then_distance",
    }:
        raise InputError("Unsupported healing selection hypothesis")
    if require(selector, "retention") not in {
        "until_dead_or_ineligible",
        "reselect_each_boundary",
    }:
        raise InputError("Healing retention must be explicitly selected")
    if not isinstance(require(selector, "follow_full_health_targets"), bool):
        raise InputError("Following healthy units must be explicit")
    acquisition = require(selector, "acquisition_range")
    if acquisition != "unbounded":
        number(acquisition, "healing acquisition range", 0)
    primary_ids = require(selector, "primary_target_ids")
    if primary_ids != "all_eligible" and (
        not isinstance(primary_ids, list)
        or not primary_ids
        or len(primary_ids) != len(set(primary_ids))
        or not set(primary_ids) <= set(actors)
    ):
        raise InputError("Healing primary target filter must name known unique actors")


class SupportCombat:
    """Keep support assignment and queued healing separate from enemy weapons."""

    def __init__(self, actors, specification, base_selector):
        self.base_selector = base_selector
        self.models = {}
        self.pending = []
        self.serial = 0
        self.fields = {}
        stacking = deepcopy(require(specification, "healing_stacking"))
        identifier(require(stacking, "source"), "stacking evidence")
        self.groups = require(stacking, "groups")
        if not isinstance(self.groups, dict):
            raise InputError("Healing stacking groups must be an explicit mapping")
        for group in self.groups.values():
            identifier(require(group, "source"), "stacking group evidence")
            if require(group, "allocation") not in {
                "instance_id",
                "highest_class_pulse_then_instance_id",
            }:
                raise InputError("Healing stacking allocation must be explicit")
            tables = require(group, "tables")
            if not isinstance(tables, dict):
                raise InputError("Healing class tables must be an explicit mapping")
            for healing_class, values in tables.items():
                if (
                    healing_class not in CLASSES
                    or not isinstance(values, list)
                    or not values
                ):
                    raise InputError(
                        "Stacking tables require explicit nonempty class weights"
                    )
                for value in values:
                    number(value, "healing stacking contribution weight", 0)
        for actor in actors.values():
            if (
                actor["kind"] == "unit"
                and require(actor, "healing_class") not in CLASSES
            ):
                raise InputError("Every unit needs an explicit healing class")
            if "healing_model" not in actor:
                continue
            if actor["kind"] != "unit" or actor["damage"] != 0:
                raise InputError(
                    "Dual-purpose support actors need additional weapon adapters"
                )
            model = deepcopy(actor["healing_model"])
            validate_healing_model(model, actors)
            group_id = model["stacking_group"]
            if group_id not in self.groups or not set(model["target_classes"]) <= set(
                self.groups[group_id]["tables"]
            ):
                raise InputError(
                    "Healers need source-linked stacking tables for every class"
                )
            self.models[actor["id"]] = model
            actor["healing_target"] = None

    def _eligible_recipient(self, model, source, target, time):
        return (
            _active(target, time)
            and not target.get("beneficial_field_immunity", False)
            and target["id"] != source["id"]
            and target["team"] == source["team"]
            and target["kind"] in model["target_kinds"]
            and target["layer"] in model["target_layers"]
            and target["healing_class"] in model["target_classes"]
        )

    def _eligible_primary(self, model, source, target, time):
        if not self._eligible_recipient(model, source, target, time):
            return False
        selector = model["selector"]
        ids = selector["primary_target_ids"]
        if ids != "all_eligible" and target["id"] not in ids:
            return False
        if (
            not selector["follow_full_health_targets"]
            and target["hp"] >= target["maximum_hp"]
        ):
            return False
        acquisition = selector["acquisition_range"]
        return (
            acquisition == "unbounded"
            or target_distance(center(source), target) <= acquisition + EPSILON
        )

    def select_target(self, actor, actors, time, blocked, width, height):
        if actor["id"] not in self.models:
            return self.base_selector(actor, actors, time, blocked, width, height)
        if not _active(actor, time):
            return None, None
        model = self.models[actor["id"]]
        selector = model["selector"]
        retained = actors.get(actor["healing_target"])
        if (
            selector["retention"] == "until_dead_or_ineligible"
            and retained is not None
            and self._eligible_primary(model, actor, retained, time)
        ):
            route = _route(actor, retained, blocked, width, height)
            if route is not None:
                _remember_route(actor, retained, route, blocked)
                return retained, self._pursuit_route(actor, retained, route)
        choices = []
        for target in actors.values():
            if not self._eligible_primary(model, actor, target, time):
                continue
            route = _route(actor, target, blocked, width, height)
            if route is None:
                continue
            injury = (
                target["hp"] / target["maximum_hp"]
                if selector["selection"] == "lowest_hp_fraction_then_distance"
                else 0
            )
            choices.append(
                (
                    injury,
                    target_distance(center(actor), target),
                    target["id"],
                    target,
                    route,
                )
            )
        if not choices:
            actor["healing_target"] = None
            return None, None
        _, _, _, target, route = min(choices, key=lambda item: item[:3])
        actor["healing_target"] = target["id"]
        _remember_route(actor, target, route, blocked)
        return target, self._pursuit_route(actor, target, route)

    @staticmethod
    def _pursuit_route(actor, target, route):
        if (
            not route
            or actor["movement"] != "air"
            or target["movement"] == "stationary"
        ):
            return route
        # Continue the existing straight pursuit ray beyond the old range edge.
        # The shared motion phase clips it at relative healing-range contact.
        # Stopping at the moving primary's OLD range edge instead creates a
        # geometric series of false arrivals and repeated whole-battle solves.
        x, y = center(actor)
        return [
            (
                min(max(x, target["x"]), target["x"] + target["width"]),
                min(max(y, target["y"]), target["y"] + target["height"]),
            )
        ]

    def first_crossing_delay(self, actors, motions, time, horizon):
        earliest = None
        for actor_id, model in self.models.items():
            actor = actors[actor_id]
            target = actors.get(actor.get("healing_target"))
            if (
                not _active(actor, time)
                or target is None
                or not self._eligible_primary(model, actor, target, time)
            ):
                continue
            route, speed = motions.get(actor_id, ((), 0))
            target_route, target_speed = motions.get(target["id"], ((), 0))
            delay = first_weapon_range_entry_delay(
                actor,
                target,
                route,
                target_route,
                speed,
                target_speed,
                horizon if earliest is None else earliest,
            )
            if delay is not None:
                earliest = delay if earliest is None else min(earliest, delay)
        return earliest

    def prepare_targets(self, actors, time, blocked, width, height):
        for actor_id in sorted(self.models):
            self.select_target(actors[actor_id], actors, time, blocked, width, height)

    def _queue(self, packet, time):
        self.serial += 1
        heappush(self.pending, (time, self.serial, packet))

    def launch(self, actor, target, time, trace):
        model = self.models[actor["id"]]
        projectile = model["projectile"]
        position = center(target)
        source_position = center(actor)
        delay = (
            0
            if projectile["timing"] == "instant"
            else hypot(
                position[0] - source_position[0], position[1] - source_position[1]
            )
            / projectile["speed_tiles_per_second"]
        )
        self._queue(
            {
                "kind": "healer",
                "source": actor["id"],
                "target": target["id"],
                "position": position,
                "source_healing_multiplier": healing_multiplier(actor),
            },
            time + delay,
        )
        trace.append(
            {
                "time_seconds": time,
                "event": "healing_launch",
                "source": actor["id"],
                "target": target["id"],
                "arrival_seconds": time + delay,
            }
        )

    def schedule_field(self, field, actors, time):
        validate_healing_field(field, actors)
        if field["id"] in self.fields:
            raise InputError("A healing field instance cannot be cast twice")
        self.fields[field["id"]] = {
            "specification": deepcopy(field),
            "pulses_delivered": 0,
        }
        self._queue(
            {"kind": "field", "field_id": field["id"], "pulse_index": 0},
            time + field["first_pulse_delay_seconds"],
        )

    def _packet_recipients(self, packet, actors, time, trace):
        source = actors[packet["source"]]
        primary = actors[packet["target"]]
        model = self.models[source["id"]]
        if not _active(primary, time):
            trace.append(
                {
                    "time_seconds": time,
                    "event": "healing_fizzle",
                    "source": source["id"],
                    "target": primary["id"],
                }
            )
            return []
        point = (
            center(primary)
            if model["projectile"]["destination"] == "locked_actor_center_at_impact"
            else packet["position"]
        )
        if model["kind"] == "single":
            if (
                target_distance(point, primary)
                > model["projectile"]["hit_radius"] + EPSILON
            ):
                return []
            return (
                [primary]
                if self._eligible_recipient(model, source, primary, time)
                else []
            )
        return [
            target
            for target in actors.values()
            if self._eligible_recipient(model, source, target, time)
            and target_distance(point, target) <= model["radius"] + EPSILON
        ]

    def _assigned_contributors(self, group_id, target, actors, time):
        contributors = set()
        for actor_id, model in self.models.items():
            source = actors[actor_id]
            primary = actors.get(source["healing_target"])
            if (
                model["stacking_group"] != group_id
                or not _active(source, time)
                or source["frozen_until"] > time + EPSILON
                or primary is None
                or not _active(primary, time)
                or target_distance(center(source), primary) > source["range"] + EPSILON
                or not self._eligible_recipient(model, source, target, time)
            ):
                continue
            covered = (
                target["id"] == primary["id"]
                if model["kind"] == "single"
                else target_distance(center(primary), target)
                <= model["radius"] + EPSILON
            )
            if covered:
                contributors.add(actor_id)
        return contributors

    def _resolve_field(self, packet, actors, time, healing, trace):
        state = self.fields[packet["field_id"]]
        field = state["specification"]
        area = field["area"]
        members = []
        for actor in actors.values():
            if (
                _active(actor, time)
                and not actor.get("beneficial_field_immunity", False)
                and actor["team"] == area["target_team"]
                and actor["kind"] in area["target_kinds"]
                and actor["layer"] in area["target_layers"]
                and actor["healing_class"] in area["target_classes"]
                and target_distance((area["x"], area["y"]), actor)
                <= area["radius"] + EPSILON
            ):
                healing[actor["id"]] += field["amounts_by_class"][
                    actor["healing_class"]
                ]
                members.append(actor["id"])
        state["pulses_delivered"] += 1
        trace.append(
            {
                "time_seconds": time,
                "event": "healing_field_pulse",
                "field_id": field["id"],
                "pulse_index": packet["pulse_index"],
                "targets": sorted(members),
                "area": deepcopy(area),
            }
        )
        next_index = packet["pulse_index"] + 1
        if next_index < field["pulse_count"]:
            self._queue(
                {**packet, "pulse_index": next_index},
                time + field["pulse_interval_seconds"],
            )

    def resolve(self, actors, time, trace):
        healing = defaultdict(float)
        hits = []
        while self.pending and self.pending[0][0] <= time + EPSILON:
            _, _, packet = heappop(self.pending)
            if packet["kind"] == "field":
                self._resolve_field(packet, actors, time, healing, trace)
            else:
                for target in self._packet_recipients(packet, actors, time, trace):
                    hits.append(
                        (packet["source"], target, packet["source_healing_multiplier"])
                    )
        due_sources = defaultdict(dict)
        for source_id, target, multiplier in hits:
            group_id = self.models[source_id]["stacking_group"]
            source_factors = due_sources[(group_id, target["id"])]
            source_factors[source_id] = max(
                source_factors.get(source_id, 0), multiplier
            )
        for source_id, target, multiplier in hits:
            model = self.models[source_id]
            group_id = model["stacking_group"]
            group = self.groups[group_id]
            healing_class = target["healing_class"]
            contributors = self._assigned_contributors(group_id, target, actors, time)
            captured_factors = due_sources[(group_id, target["id"])]
            contributors |= set(captured_factors)
            if group["allocation"] == "instance_id":
                ordered = sorted(contributors)
            else:
                ordered = sorted(
                    contributors,
                    key=lambda key: (
                        -self.models[key]["amounts_by_class"][healing_class]
                        * captured_factors.get(key, healing_multiplier(actors[key])),
                        key,
                    ),
                )
            table = group["tables"][healing_class]
            if len(table) < len(ordered):
                raise InputError(
                    "Measured/declared stacking table does not cover all contributors"
                )
            rank = ordered.index(source_id)
            amount = model["amounts_by_class"][healing_class] * multiplier * table[rank]
            healing[target["id"]] += amount
            trace.append(
                {
                    "time_seconds": time,
                    "event": "healing_impact",
                    "source": source_id,
                    "target": target["id"],
                    "healing_class": healing_class,
                    "nominal_amount": amount,
                    "stack_rank": rank + 1,
                    "stacking_weight": table[rank],
                    "source_healing_multiplier": multiplier,
                }
            )
        return healing

    def next_boundary(self):
        return self.pending[0][0] if self.pending else None

    def result(self):
        return {
            "fields": {
                field_id: {
                    "pulses_delivered": state["pulses_delivered"],
                    "pulse_count": state["specification"]["pulse_count"],
                }
                for field_id, state in self.fields.items()
            },
            "pending_healing_at_horizon": [
                {"arrival_seconds": time, **packet} for time, _, packet in self.pending
            ],
        }
