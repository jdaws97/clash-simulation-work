"""Weaponized huts with autonomous, untargetable defensive repair workers.

Workers are internal motion/status objects, never additional combat actors or
destruction targets. Acquisition around the home hut is distinct from reaching
the selected building and completing a repair swing. Pathing, retention, self
repair, stacking and exact animation timing remain explicit hypotheses.
"""

from collections import defaultdict
from copy import deepcopy
from math import hypot

from .buffs import _circle_events
from .combat import validate_pattern
from .common import InputError, identifier, number, require
from .hazards import PulsedHazards
from .rates import attack_rate, movement_speed, pause_attack_work
from .spatial import (
    EPSILON,
    _active,
    _blocked,
    _move,
    _remember_route,
    _route,
    _route_length,
    center,
    target_distance,
)


BUILDER_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/game-updates/battle-builders-2/"
)
BUILDER_RULES = {
    "builder_identity": "internal_untargetable_worker_linked_to_own_hut",
    "builder_acquisition": "damaged_friendly_declared_structures_within_home_hut_radius",
    "builder_travel": "four_neighbor_route_to_explicit_contact_repair_distance",
    "builder_repair": "independent_catalog_swing_clock_after_contact",
    "builder_health_phase": "incoming_lethal_damage_prevents_source_or_target_repair",
    "builder_status": "worker_position_freeze_and_shared_hazard_status_without_damage_pulses",
    "builder_hut_loss": "retire_worker_when_own_hut_dies",
    "builder_stacking": "explicit_additive_independent_workers_capped_by_target_health",
}
PARAMETERS = {
    "source",
    "acquisition_range_basis",
    "acquisition_range_multiplier",
    "contact_repair_range_tiles",
    "repair_amount_multiplier",
    "repair_interval_multiplier",
    "movement_speed_multiplier",
    "first_repair_delay_seconds",
    "target_kinds",
    "excluded_entities",
    "selection",
    "retention",
    "self_hut_policy",
    "path_policy",
    "idle_policy",
    "hut_freeze_linkage",
    "worker_freeze_policy",
    "stacking_policy",
    "repair_boost_policy",
    "hut_death_policy",
    "lethal_damage_policy",
}
MODEL_FIELDS = PARAMETERS - {
    "acquisition_range_multiplier",
    "repair_amount_multiplier",
    "repair_interval_multiplier",
    "movement_speed_multiplier",
} | {
    "kind",
    "acquisition_range_tiles",
    "repair_amount",
    "repair_interval_seconds",
    "movement_speed_tiles_per_second",
}


def _validate_policies(model):
    identifier(model["source"], "Builder behavior evidence")
    policies = {
        "acquisition_range_basis": "catalog_builder_range_is_home_hut_acquisition_radius",
        "retention": "until_full_destroyed_or_ineligible",
        "idle_policy": "wait_at_current_position",
        "worker_freeze_policy": "pause_movement_and_unfinished_repair_work",
        "stacking_policy": "additive_independent_workers",
        "repair_boost_policy": "ignore_troop_hero_and_hut_damage_healing_bonuses",
        "hut_death_policy": "retire_worker_immediately",
        "lethal_damage_policy": "incoming_lethal_damage_prevents_source_and_target_repair",
    }
    for name, value in policies.items():
        if model[name] != value:
            raise InputError(f"Builder requires explicit {name}: {value}")
    for name, choices in (
        (
            "selection",
            {"nearest_path_then_instance_id", "lowest_health_fraction_then_path"},
        ),
        ("self_hut_policy", {"allow_self_hut", "exclude_self_hut"}),
        (
            "path_policy",
            {"four_neighbor_avoid_structures", "four_neighbor_ignore_friendly_walls"},
        ),
        (
            "hut_freeze_linkage",
            {"worker_independent_of_hut_freeze", "hut_freeze_also_pauses_worker"},
        ),
    ):
        if model[name] not in choices:
            raise InputError(f"Builder needs an explicit supported {name}")
    number(
        model["contact_repair_range_tiles"], "Builder contact repair range", EPSILON, 1
    )
    number(model["first_repair_delay_seconds"], "Builder first repair delay", 0)
    kinds = model["target_kinds"]
    if (
        not isinstance(kinds, list)
        or not kinds
        or len(kinds) != len(set(kinds))
        or not set(kinds) <= {"defense", "building"}
    ):
        raise InputError(
            "Builder repair targets must explicitly exclude walls and units"
        )
    exclusions = model["excluded_entities"]
    if not isinstance(exclusions, list):
        raise InputError("Builder target exclusions must be an explicit list")
    for entity_id in exclusions:
        identifier(entity_id, "Builder excluded entity")
    if len(exclusions) != len(set(exclusions)):
        raise InputError("Builder target exclusions must be unique")


def compile_builder_hut(
    actor, instance, entity, row, modifiers, movement_units_per_tile
):
    """Compile the turret and attach an independent repair-worker model."""
    if (
        entity["id"] != "builders-hut"
        or instance["entity"] != "builders-hut"
        or instance["mode"] != "normal"
        or instance["statistics_mode"] != "normal"
        or actor["team"] != "defense"
        or not actor["counts_for_destruction"]
        or "wall_parameters" in instance
    ):
        raise InputError("Builder's Hut needs its combined normal turret/worker mode")
    actor.update(
        layer="ground",
        movement="stationary",
        speed=0,
        blocking=True,
        width=2,
        height=2,
        minimum_range=0,
    )
    if row["level"] == 1:
        if (
            require(instance, "attack_parameters") != {}
            or "builder_parameters" in instance
        ):
            raise InputError(
                "Level-one Builder's Hut has neither turret nor repair worker"
            )
        actor.update(
            kind="building",
            damage=0,
            range=0,
            attack_interval_seconds=1,
            target_priorities=[],
            target_layers=[],
            attack_model={"kind": "none", "source": actor["source"]},
        )
        return actor
    parameters = require(instance, "builder_parameters")
    if not isinstance(parameters, dict) or set(parameters) != PARAMETERS:
        raise InputError(
            "Every Builder targeting, travel, repair and status policy is required"
        )
    _validate_policies(parameters)
    for name in (
        "acquisition_range_multiplier",
        "repair_amount_multiplier",
        "repair_interval_multiplier",
        "movement_speed_multiplier",
    ):
        number(parameters[name], name, EPSILON)
    conversion = number(
        movement_units_per_tile, "Builder movement units per tile", EPSILON
    )
    attack_parameters = require(instance, "attack_parameters")
    if not isinstance(attack_parameters, dict) or set(attack_parameters) != {
        "projectile"
    }:
        raise InputError("Builder turret needs an explicit ordinary single projectile")
    normal = require(require(entity, "modes"), "normal")
    builder = require(entity["modes"], "builder")
    stats = require(require(row, "stats"), "normal")
    repair_stats = require(row["stats"], "builder")
    if normal.get("damageType") != "single" or entity.get("targetType") != "both":
        raise InputError(
            "Catalog Builder turret must remain a ground-and-air single weapon"
        )
    actor.update(
        kind="defense",
        damage=number(require(stats, "damagePerShot"), "Builder turret damage", EPSILON)
        * modifiers["damage_multiplier"],
        range=number(require(normal, "range"), "Builder turret range", EPSILON)
        * modifiers["range_multiplier"],
        attack_interval_seconds=number(
            require(normal, "attackSpeed"), "Builder turret attack interval", EPSILON
        )
        * modifiers["attack_interval_multiplier"],
        target_priorities=["unit"],
        target_priority_tiers=[["unit"]],
        target_layers=["ground", "air"],
        attack_model={
            "kind": "single",
            "source": actor["source"],
            "target_kinds": ["unit"],
            "target_layers": ["ground", "air"],
            "maximum_hp_fraction": 0,
            "projectile": deepcopy(attack_parameters["projectile"]),
        },
    )
    validate_pattern(actor["attack_model"])
    actor["builder_hut_model"] = {
        key: deepcopy(value) for key, value in parameters.items() if key in MODEL_FIELDS
    }
    actor["builder_hut_model"].update(
        kind="defensive_builder",
        acquisition_range_tiles=number(
            require(builder, "range"), "Builder catalog acquisition range", EPSILON
        )
        * parameters["acquisition_range_multiplier"],
        repair_amount=number(
            require(repair_stats, "repairPerHit"),
            "Builder catalog repair per hit",
            EPSILON,
        )
        * parameters["repair_amount_multiplier"],
        repair_interval_seconds=number(
            require(builder, "repairSpeed"), "Builder catalog repair interval", EPSILON
        )
        * parameters["repair_interval_multiplier"],
        movement_speed_tiles_per_second=number(
            require(builder, "movementSpeed"), "Builder catalog movement speed", EPSILON
        )
        / conversion
        * parameters["movement_speed_multiplier"],
    )
    validate_builder_hut_model(actor)
    actor["entity_adapter"].update(
        builder_parameters=deepcopy(parameters),
        builder_statistics={
            "source": actor["source"],
            "repair_amount": "levels[].stats.builder.repairPerHit",
            "repair_interval": "modes.builder.repairSpeed",
            "movement_speed": "modes.builder.movementSpeed",
            "movement_units_per_tile": conversion,
            "acquisition_range": "modes.builder.range",
            "contact_range": "explicit_separate_melee_repair_distance",
            "publisher_behavior_source": BUILDER_SOURCE,
        },
        behavior_verification="explicit_worker_targeting_and_travel_not_replay_validated",
    )
    return actor


def validate_builder_hut_model(actor):
    model = require(actor, "builder_hut_model")
    if (
        not isinstance(model, dict)
        or set(model) != MODEL_FIELDS
        or model["kind"] != "defensive_builder"
    ):
        raise InputError("Builder's Hut requires the complete autonomous worker model")
    _validate_policies(model)
    for name in (
        "acquisition_range_tiles",
        "repair_amount",
        "repair_interval_seconds",
        "movement_speed_tiles_per_second",
    ):
        number(model[name], name, EPSILON)
    if model["contact_repair_range_tiles"] > model["acquisition_range_tiles"]:
        raise InputError(
            "Builder contact reach cannot exceed home-hut acquisition range"
        )
    if (
        actor["kind"] != "defense"
        or actor["team"] != "defense"
        or actor["movement"] != "stationary"
        or actor["attack_model"]["kind"] != "single"
        or actor["damage"] <= 0
        or not actor["blocking"]
        or not actor["counts_for_destruction"]
        or actor["spawn_seconds"] != 0
    ):
        raise InputError(
            "Defensive Builder must remain linked to a living counted turret hut"
        )
    return model


class _WorkerHazards(PulsedHazards):
    """Use the shared status semantics with directed circle-contact boundaries."""

    def __init__(self, actors):
        super().__init__(actors, [])
        self.boundary_sides = {}
        self.crossing_hints = {}

    def _inside(self, field, actor, time):
        inside = super()._inside(field, actor, time)
        key = field["id"], actor["id"]
        side = self.boundary_sides.get(key)
        if side is not None:
            point = center(actor)
            if (
                hypot(point[0] - side["position"][0], point[1] - side["position"][1])
                <= EPSILON * 128
            ):
                return inside and side["inside_after"]
            self.boundary_sides.pop(key)
        return inside

    def prepare_status(self, actors, time, trace):
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
        super().prepare_status(actors, time, trace)

    def first_crossing(self, worker, route, time, speed):
        earliest = None
        for field_id, field in sorted(self.fields.items()):
            area = field["area"]
            if (
                not self._live(field, time)
                or worker["team"] != area["target_team"]
                or worker["layer"] not in area["target_layers"]
                or worker["hazard_class"] in field["excluded_classes"]
            ):
                continue
            key = field_id, worker["id"]
            self.crossing_hints.pop(key, None)
            current_inside = self._inside(field, worker, time)
            previous = center(worker)
            traveled = 0.0
            found = False
            for index, point in enumerate(route):
                length = hypot(point[0] - previous[0], point[1] - previous[1])
                for contact, inside_after in _circle_events(
                    previous, point, (area["x"], area["y"]), area["radius"]
                ):
                    if abs(contact - length) <= EPSILON:
                        for following in route[index + 1 :]:
                            dx, dy = following[0] - point[0], following[1] - point[1]
                            if hypot(dx, dy) <= EPSILON:
                                continue
                            inside_after = (point[0] - area["x"]) * dx + (
                                point[1] - area["y"]
                            ) * dy < -EPSILON
                            break
                    if inside_after == current_inside:
                        continue
                    distance = traveled + contact
                    if distance <= speed * EPSILON:
                        contact = max(contact, speed * EPSILON * 2)
                        distance = traveled + contact
                    if contact > length + EPSILON or length <= EPSILON:
                        continue
                    arrival = time + distance / speed
                    fraction = min(contact / length, 1)
                    position = tuple(
                        previous[axis] + (point[axis] - previous[axis]) * fraction
                        for axis in (0, 1)
                    )
                    self.crossing_hints[key] = {
                        "time_seconds": arrival,
                        "position": position,
                        "inside_after": inside_after,
                    }
                    earliest = (
                        min(earliest, arrival) if earliest is not None else arrival
                    )
                    found = True
                    break
                if found:
                    break
                traveled += length
                previous = point
        return earliest


class BuilderHutCombat:
    """Repair workers coexist with their huts' ordinary damaging turret weapons."""

    def __init__(self, actors, width, height, shared_hazards=None):
        self.models = {
            actor["id"]: deepcopy(validate_builder_hut_model(actor))
            for actor in actors.values()
            if "builder_hut_model" in actor
        }
        self.actors = actors
        self.width = width
        self.height = height
        self.shared_hazards = shared_hazards
        self.workers = {}
        self.states = {}
        for hut_id, model in self.models.items():
            worker_id = f"{hut_id}::builder"
            if worker_id in actors:
                raise InputError(
                    "Internal Builder identity collides with a combat actor"
                )
            x, y = center(actors[hut_id])
            self.workers[worker_id] = {
                "id": worker_id,
                "team": "defense",
                "kind": "unit",
                "layer": "ground",
                "movement": "ground",
                "x": x,
                "y": y,
                "width": 0,
                "height": 0,
                "range": model["contact_repair_range_tiles"],
                "speed": model["movement_speed_tiles_per_second"],
                "hp": 1,
                "maximum_hp": 1,
                "spawn_seconds": 0,
                "frozen_until": 0,
                "immune_until": 0,
                "next_attack": 0,
                "hazard_class": "builder",
                "_terminal_ground_approach": True,
            }
            self.states[hut_id] = {
                "worker_id": worker_id,
                "phase": "idle",
                "target": None,
                "route": [],
                "repair_count": 0,
                "nominal_repair_delivered": 0,
            }
        self.status_hazards = _WorkerHazards(self.workers)

    def internal_status_actors(self):
        """Status-only objects; never add these to combat actors or inventory."""
        return self.workers

    def _sync_hazards(self):
        if self.shared_hazards is None or not self.workers:
            return
        for field_id, field in self.shared_hazards.fields.items():
            if field_id in self.status_hazards.fields:
                continue
            area = field["area"]
            if (
                area["target_team"] == "defense"
                and "ground" in area["target_layers"]
                and "builder" not in field["excluded_classes"]
            ):
                self.status_hazards.schedule(field, self.workers)

    def freeze(self, worker_ids, time, duration, trace):
        number(duration, "Builder Freeze duration", EPSILON)
        for worker_id in sorted(set(worker_ids)):
            if worker_id not in self.workers:
                raise InputError("Builder Freeze must identify a known internal worker")
            worker = self.workers[worker_id]
            if not _active(worker, time):
                continue
            end = time + duration
            pause_attack_work(worker, time, end)
            worker["frozen_until"] = max(worker["frozen_until"], end)
            trace.append(
                {
                    "event": "builder_freeze",
                    "time_seconds": time,
                    "worker": worker_id,
                    "frozen_until": worker["frozen_until"],
                }
            )

    def apply_effects(self, effects, actors, time, trace):
        for effect in effects:
            if effect["kind"] not in {"freeze", "area_freeze"}:
                if effect["kind"] == "builder_target_reset":
                    raise InputError(
                        "Builder target resets require a supported Lightning adapter"
                    )
                continue
            selected = []
            area = effect.get("area")
            for hut_id, state in self.states.items():
                worker = self.workers[state["worker_id"]]
                if not _active(actors[hut_id], time) or not _active(worker, time):
                    continue
                if area is not None:
                    affected = (
                        area["target_team"] == worker["team"]
                        and "ground" in area["target_layers"]
                        and target_distance((area["x"], area["y"]), worker)
                        <= area["radius"] + EPSILON
                    )
                else:
                    affected = (
                        hut_id in effect.get("targets", [])
                        and self.models[hut_id]["hut_freeze_linkage"]
                        == "hut_freeze_also_pauses_worker"
                    )
                if affected:
                    selected.append(worker["id"])
            self.freeze(selected, time, effect["duration_seconds"], trace)

    def lightning_reset(self, worker_ids, actors, time, trace, clock_policy):
        """Reset affected repair targets after a source-bound Lightning impact.

        Official behavior establishes the reset, not the exact repair-clock
        outcome. The spell integration supplies affected internal workers and
        its explicit clock hypothesis. These objects remain untargetable and
        uncounted; ordinary damage is never reinterpreted as Lightning.
        """
        if clock_policy != "restart_declared_first_repair_delay":
            raise InputError(
                "Lightning builder reset requires an explicit clock hypothesis"
            )
        for worker_id in sorted(set(worker_ids)):
            if worker_id not in self.workers:
                raise InputError("Lightning reset requires a known internal worker")
            worker = self.workers[worker_id]
            hut_id = (
                worker["hut_id"]
                if "hut_id" in worker
                else next(
                    key
                    for key, state in self.states.items()
                    if state["worker_id"] == worker_id
                )
            )
            state = self.states[hut_id]
            if state["phase"] == "retired" or not _active(actors[hut_id], time):
                continue
            previous = state["target"]
            state.update(target=None, route=[], phase="idle")
            worker.pop("_remaining_path", None)
            worker.pop("_path_signature", None)
            worker["next_attack"] = max(time, worker["frozen_until"]) + self.models[
                hut_id
            ]["first_repair_delay_seconds"] / attack_rate(worker)
            trace.append(
                {
                    "event": "builder_lightning_target_reset",
                    "time_seconds": time,
                    "worker": worker_id,
                    "previous_target": previous,
                    "clock_policy": clock_policy,
                    "source": BUILDER_SOURCE,
                }
            )

    def _eligible_target(self, hut_id, target, actors, time):
        model = self.models[hut_id]
        hut = actors[hut_id]
        return (
            _active(target, time)
            and target["team"] == hut["team"]
            and target["kind"] in model["target_kinds"]
            and target["layer"] == "ground"
            and target["hp"] < target["maximum_hp"] - EPSILON
            and target.get("entity_adapter", {}).get("entity")
            not in model["excluded_entities"]
            and (target["id"] != hut_id or model["self_hut_policy"] == "allow_self_hut")
            and target_distance(center(hut), target)
            <= model["acquisition_range_tiles"] + EPSILON
        )

    def _blocked_for(self, hut_id, actors, time):
        blocked = _blocked(actors, time)
        hut = actors[hut_id]
        ignored = [hut]
        if self.models[hut_id]["path_policy"] == "four_neighbor_ignore_friendly_walls":
            ignored.extend(
                actor
                for actor in actors.values()
                if actor["kind"] == "wall" and actor["team"] == hut["team"]
            )
        for actor in ignored:
            for x in range(actor["x"], actor["x"] + actor["width"]):
                for y in range(actor["y"], actor["y"] + actor["height"]):
                    blocked.discard((x, y))
        return blocked

    def _retire(self, hut_id, time, trace):
        state = self.states[hut_id]
        if state["phase"] == "retired":
            return
        worker = self.workers[state["worker_id"]]
        worker["hp"] = 0
        state.update(phase="retired", target=None, route=[])
        trace.append(
            {
                "event": "builder_retire",
                "time_seconds": time,
                "hut": hut_id,
                "worker": worker["id"],
            }
        )

    def prepare(self, actors, time, trace):
        self._sync_hazards()
        for hut_id in self.models:
            if not _active(actors[hut_id], time):
                self._retire(hut_id, time, trace)
        self.status_hazards.prepare_status(self.workers, time, trace)
        for hut_id, model in sorted(self.models.items()):
            state = self.states[hut_id]
            worker = self.workers[state["worker_id"]]
            if state["phase"] == "retired":
                continue
            hut = actors[hut_id]
            if (
                model["hut_freeze_linkage"] == "hut_freeze_also_pauses_worker"
                and hut["frozen_until"] > worker["frozen_until"] + EPSILON
            ):
                self.freeze([worker["id"]], time, hut["frozen_until"] - time, trace)
            blocked = self._blocked_for(hut_id, actors, time)
            target = actors.get(state["target"])
            route = None
            if target is not None and self._eligible_target(
                hut_id, target, actors, time
            ):
                route = _route(worker, target, blocked, self.width, self.height)
            if route is None:
                choices = []
                for candidate in actors.values():
                    if not self._eligible_target(hut_id, candidate, actors, time):
                        continue
                    candidate_route = _route(
                        worker, candidate, blocked, self.width, self.height
                    )
                    if candidate_route is None:
                        continue
                    injury = (
                        candidate["hp"] / candidate["maximum_hp"]
                        if model["selection"] == "lowest_health_fraction_then_path"
                        else 0
                    )
                    choices.append(
                        (
                            injury,
                            _route_length(worker, candidate_route),
                            candidate["id"],
                            candidate,
                            candidate_route,
                        )
                    )
                if choices:
                    _, _, _, target, route = min(choices, key=lambda choice: choice[:3])
                else:
                    target, route = None, []
            target_id = target["id"] if target is not None else None
            changed = state["target"] != target_id
            if changed:
                trace.append(
                    {
                        "event": "builder_target",
                        "time_seconds": time,
                        "hut": hut_id,
                        "worker": worker["id"],
                        "target": target_id,
                    }
                )
            prior_phase = state["phase"]
            state["target"] = target_id
            state["route"] = list(route)
            if target is None:
                state["phase"] = "idle"
                continue
            _remember_route(worker, target, route, blocked)
            in_contact = (
                target_distance(center(worker), target)
                <= model["contact_repair_range_tiles"] + EPSILON
            )
            state["phase"] = "repairing" if in_contact else "moving"
            if in_contact and (changed or prior_phase != "repairing"):
                worker["next_attack"] = max(time, worker["frozen_until"]) + model[
                    "first_repair_delay_seconds"
                ] / attack_rate(worker)
                trace.append(
                    {
                        "event": "builder_contact",
                        "time_seconds": time,
                        "hut": hut_id,
                        "worker": worker["id"],
                        "target": target_id,
                        "first_repair_seconds": worker["next_attack"],
                    }
                )

    def resolve(self, actors, time, trace, pending_damage=None):
        repair = defaultdict(float)
        pending_damage = pending_damage or {}
        for hut_id, model in sorted(self.models.items()):
            state = self.states[hut_id]
            worker = self.workers[state["worker_id"]]
            if (
                state["phase"] != "repairing"
                or worker["frozen_until"] > time + EPSILON
                or worker["next_attack"] > time + EPSILON
            ):
                continue
            hut = actors[hut_id]
            target = actors.get(state["target"])
            if not _active(hut, time):
                self._retire(hut_id, time, trace)
                continue
            if target is None or not self._eligible_target(
                hut_id, target, actors, time
            ):
                continue
            if (
                hut["hp"] <= pending_damage.get(hut_id, 0) + EPSILON
                or target["hp"] <= pending_damage.get(target["id"], 0) + EPSILON
            ):
                trace.append(
                    {
                        "event": "builder_repair_cancel",
                        "time_seconds": time,
                        "hut": hut_id,
                        "target": target["id"],
                        "reason": "incoming_lethal_damage",
                    }
                )
                continue
            if (
                target_distance(center(worker), target)
                > model["contact_repair_range_tiles"] + EPSILON
            ):
                continue
            amount = model["repair_amount"]
            repair[target["id"]] += amount
            worker["next_attack"] = time + model[
                "repair_interval_seconds"
            ] / attack_rate(worker)
            state["repair_count"] += 1
            state["nominal_repair_delivered"] += amount
            trace.append(
                {
                    "event": "builder_repair",
                    "time_seconds": time,
                    "hut": hut_id,
                    "worker": worker["id"],
                    "target": target["id"],
                    "nominal_amount": amount,
                    "next_repair_seconds": worker["next_attack"],
                }
            )
        return repair

    def advance(self, actors, time, duration, trace):
        number(duration, "Builder movement interval", 0)
        for hut_id, state in self.states.items():
            if not _active(actors[hut_id], time):
                self._retire(hut_id, time, trace)
                continue
            worker = self.workers[state["worker_id"]]
            if state["phase"] != "moving" or worker["frozen_until"] > time + EPSILON:
                continue
            point, remaining = _move(worker, state["route"], duration)
            worker["x"], worker["y"] = point
            state["route"] = remaining
            worker["_remaining_path"] = list(remaining)

    def next_boundary(self, time):
        boundaries = []
        hazard_boundary = self.status_hazards.next_boundary(time)
        if hazard_boundary is not None:
            boundaries.append(hazard_boundary)
        for hut_id, state in self.states.items():
            if state["phase"] == "retired":
                continue
            worker = self.workers[state["worker_id"]]
            boundaries.append(worker["frozen_until"])
            if worker["frozen_until"] > time + EPSILON:
                continue
            if state["phase"] == "repairing":
                boundaries.append(worker["next_attack"])
            elif state["phase"] == "moving":
                speed = movement_speed(worker)
                boundaries.append(time + _route_length(worker, state["route"]) / speed)
                crossing = self.status_hazards.first_crossing(
                    worker, state["route"], time, speed
                )
                if crossing is not None:
                    boundaries.append(crossing)
        future = [value for value in boundaries if value > time + EPSILON]
        return min(future) if future else None

    def frame(self, actor, time):
        state = self.states.get(actor["id"])
        if state is None:
            return {}
        worker = self.workers[state["worker_id"]]
        return {
            "builder": {
                "id": worker["id"],
                "x": worker["x"],
                "y": worker["y"],
                "phase": state["phase"],
                "target": state["target"],
                "frozen_until": worker["frozen_until"],
                "next_repair_seconds": worker["next_attack"],
                "repair_count": state["repair_count"],
                **self.status_hazards.frame(worker),
            }
        }

    def result(self):
        return {
            "workers": {
                hut_id: {
                    **deepcopy(state),
                    "position": center(self.workers[state["worker_id"]]),
                    "targetable": False,
                    "damageable": False,
                    "counts_for_destruction": False,
                }
                for hut_id, state in self.states.items()
            },
            "status_only_fields": sorted(self.status_hazards.fields),
        }
