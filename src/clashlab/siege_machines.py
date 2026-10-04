"""Conditional Blimp, Slammer and Wrecker weapons and payload termination.

Travel, projectile geometry, deployment regions, spell response, decay and
release timing are explicit hypotheses. Snapshot damage quantities retain their
named roles; Wrecker wall damage never becomes ordinary building damage.
"""

from collections import defaultdict
from copy import deepcopy
from heapq import heappop, heappush
from math import hypot

from .common import InputError, identifier, integer, number, require
from .defending_heroes import defending_collateral_eligible
from .rates import attack_rate, movement_speed
from .spatial import EPSILON, _active, _eligible, _route_length, center, target_distance
from .traps import segment_circle_entry


SIEGE_MACHINES = {"battle-blimp", "stone-slammer", "wall-wrecker"}
SIEGE_RULES = {
    "siege_statistics": "snapshot_named_hit_and_death_quantities_with_explicit_geometry",
    "siege_blimp_route": "captured_hall_anchor_flight_with_independent_in_range_bomb_targets",
    "siege_wrecker_route": "straight_hall_route_stops_before_first_live_blocking_footprint",
    "siege_slammer_targeting": "retained_defenses_then_other_reachable_structures",
    "siege_area_damage": "strongest_explicit_zone_per_recipient_with_separate_wall_multiplier",
    "siege_termination": "manual_actual_death_explicit_expiry_or_declared_hall_arrival_once",
    "siege_decay": "explicit_maximum_hp_pulses_continue_during_freeze_and_bypass_protection",
    "siege_payload": "termination_captures_release_point_and_pending_troops_survive_carrier_loss",
    "siege_spell_response": "beneficial_healing_and_buff_fields_excluded_hostile_statuses_remain_explicit",
}
PARAMETERS = {
    "source",
    "origin",
    "donor_town_hall",
    "payload_group_id",
    "statistics_mapping",
    "range_tiles",
    "targeting",
    "weapon",
    "termination",
    "death",
    "spell_response",
}
TARGETING_KINDS = {
    "battle-blimp": "town_hall_flight_with_in_range_bombs",
    "stone-slammer": "retained_defenses_then_other_structures",
    "wall-wrecker": "straight_town_hall_route_clear_first_blocker",
}
DEATH_STATISTICS = {
    "battle-blimp": {"damageWhenDestroyed"},
    "stone-slammer": {"damageWhenDestroyedHitbox1", "damageWhenDestroyedHitbox2"},
    "wall-wrecker": set(),
}


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise InputError(f"{label} requires its complete explicit parameters")


def _validate_projectile(projectile):
    fields = {"timing", "delay_seconds", "destination", "inactive_primary_policy"}
    timing = require(projectile, "timing")
    if timing == "launch_distance_delay":
        fields.add("speed_tiles_per_second")
        number(
            require(projectile, "speed_tiles_per_second"),
            "siege projectile speed",
            EPSILON,
        )
    elif timing != "instant":
        raise InputError("Unsupported siege projectile timing")
    _fields(projectile, fields, "Siege projectile")
    number(
        projectile["delay_seconds"],
        "siege projectile delay",
        0,
        0 if timing == "instant" else None,
    )
    if projectile["destination"] not in {
        "fixed_target_center_at_launch",
        "locked_actor_center_at_impact",
    }:
        raise InputError("Siege weapon needs an explicit target-centered destination")
    if projectile["inactive_primary_policy"] not in {
        "fizzle",
        "resolve_at_fixed_launch_position",
    }:
        raise InputError("Siege inactive-primary policy is unsupported")
    if (
        projectile["inactive_primary_policy"] == "resolve_at_fixed_launch_position"
        and projectile["destination"] != "fixed_target_center_at_launch"
    ):
        raise InputError("Independent siege impacts require a fixed launch destination")


def _validate_zones(zones):
    if not isinstance(zones, list) or not zones:
        raise InputError("Siege area damage needs explicit radial zones")
    for zone in zones:
        _fields(
            zone,
            {
                "inner_radius_tiles",
                "outer_radius_tiles",
                "damage_multiplier",
                "wall_damage_multiplier",
            },
            "Siege damage zone",
        )
        inner = number(zone["inner_radius_tiles"], "siege inner radius", 0)
        number(zone["outer_radius_tiles"], "siege outer radius", inner)
        number(zone["damage_multiplier"], "siege zone damage scale", 0)
        number(zone["wall_damage_multiplier"], "siege zone wall scale", 0)


def _validate_parameters(parameters, entity_id):
    _fields(parameters, PARAMETERS, "Siege machine")
    identifier(parameters["source"], "siege behavior evidence")
    identifier(parameters["payload_group_id"], "siege payload group")
    if parameters["origin"] not in {"own", "donated"}:
        raise InputError("Siege origin must be own or donated")
    if parameters["origin"] == "own":
        if parameters["donor_town_hall"] is not None:
            raise InputError("An owned siege cannot hide a donor-level override")
    else:
        integer(parameters["donor_town_hall"], "siege donor Town Hall", 1)
    if (
        parameters["statistics_mapping"]
        != "snapshot_damagePerHit_and_entity_attackSpeed"
    ):
        raise InputError("Siege weapon statistics need an explicit source mapping")
    number(parameters["range_tiles"], "siege weapon range hypothesis", EPSILON)
    targeting = parameters["targeting"]
    _fields(
        targeting,
        {
            "kind",
            "hall_actor_id",
            "arrival_radius_tiles",
            "hall_loss",
            "ineligible_blocker",
        },
        "Siege targeting",
    )
    if targeting["kind"] != TARGETING_KINDS[entity_id]:
        raise InputError("Siege entity and targeting behavior differ")
    if entity_id == "stone-slammer":
        if targeting != {
            "kind": TARGETING_KINDS[entity_id],
            "hall_actor_id": None,
            "arrival_radius_tiles": None,
            "hall_loss": "not_applicable",
            "ineligible_blocker": "not_applicable",
        }:
            raise InputError(
                "Stone Slammer uses retained structure targeting without a Hall arrival release"
            )
    else:
        identifier(targeting["hall_actor_id"], "siege Town Hall actor")
        number(targeting["arrival_radius_tiles"], "siege Hall arrival radius", 0)
        if targeting["hall_loss"] != "continue_to_captured_anchor":
            raise InputError(
                "Hall loss behavior must keep the explicitly captured destination"
            )
        expected = (
            "wait_until_targetable" if entity_id == "wall-wrecker" else "not_applicable"
        )
        if targeting["ineligible_blocker"] != expected:
            raise InputError("Siege blocker behavior must be explicit")
    weapon = parameters["weapon"]
    _fields(
        weapon,
        {
            "projectile",
            "zones",
            "zone_composition",
            "zone_membership",
            "wall_damage_basis",
        },
        "Siege weapon",
    )
    _validate_projectile(weapon["projectile"])
    _validate_zones(weapon["zones"])
    if (
        weapon["zone_composition"] != "strongest_per_recipient"
        or weapon["zone_membership"] != "minimum_point_to_footprint_distance"
    ):
        raise InputError("Unsupported siege zone composition or membership")
    expected = (
        "snapshot_damageVsWalls_ratio"
        if entity_id == "wall-wrecker"
        else "explicit_zone_multiplier"
    )
    if weapon["wall_damage_basis"] != expected:
        raise InputError("Siege wall damage must use its entity-specific mapping")
    if entity_id == "wall-wrecker":
        if weapon["projectile"]["timing"] != "instant" or any(
            zone["wall_damage_multiplier"] != 1 for zone in weapon["zones"]
        ):
            raise InputError(
                "Wrecker melee uses instant impacts and its source wall ratio exactly once"
            )
    termination = parameters["termination"]
    _fields(
        termination,
        {"manual_release", "maximum_lifetime_seconds", "decay"},
        "Siege termination",
    )
    if termination["manual_release"] != "destroy_and_release":
        raise InputError("Manual siege release must terminate its single carrier")
    if termination["maximum_lifetime_seconds"] is not None:
        number(termination["maximum_lifetime_seconds"], "siege lifetime", EPSILON)
    decay = termination["decay"]
    _fields(
        decay,
        {"interval_seconds", "maximum_hp_fraction_per_pulse", "protection", "freeze"},
        "Siege decay",
    )
    number(decay["interval_seconds"], "siege decay cadence", EPSILON)
    number(decay["maximum_hp_fraction_per_pulse"], "siege decay fraction", 0, 1)
    if (
        decay["protection"] != "bypass_damage_immunity"
        or decay["freeze"] != "clock_continues"
    ):
        raise InputError(
            "Siege decay requires explicit independent protection and Freeze policies"
        )
    death = parameters["death"]
    _fields(death, {"triggers", "overlap", "effects"}, "Siege death effects")
    if (
        death["triggers"] not in {"all_terminations", "hp_death_only"}
        or death["overlap"] != "sum_explicit_effects"
    ):
        raise InputError("Unsupported siege death trigger or overlap policy")
    effects = death["effects"]
    if (
        not isinstance(effects, list)
        or {effect.get("statistic") for effect in effects}
        != DEATH_STATISTICS[entity_id]
        or len(effects) != len(DEATH_STATISTICS[entity_id])
    ):
        raise InputError(
            "Siege death geometry must cover each named source death statistic exactly once"
        )
    for effect in effects:
        _fields(
            effect,
            {
                "statistic",
                "delay_seconds",
                "inner_radius_tiles",
                "outer_radius_tiles",
                "damage_multiplier",
                "target_kinds",
                "target_layers",
            },
            "Siege death area",
        )
        number(effect["delay_seconds"], "siege death delay", 0)
        inner = number(effect["inner_radius_tiles"], "siege death inner radius", 0)
        number(effect["outer_radius_tiles"], "siege death outer radius", inner)
        number(effect["damage_multiplier"], "siege death damage scale", EPSILON)
        for field, supported in (
            ("target_kinds", {"defense", "building", "wall", "unit"}),
            ("target_layers", {"ground", "air"}),
        ):
            values = effect[field]
            if (
                not isinstance(values, list)
                or not values
                or len(values) != len(set(values))
                or not set(values) <= supported
            ):
                raise InputError("Siege death recipient filters must be explicit")
    if parameters["spell_response"] != {
        "beneficial_fields": "immune_to_healing_rage_and_haste",
        "hostile_effects": "explicit_shared_status_and_hazard_policies",
    }:
        raise InputError(
            "Siege spell response requires separate beneficial and hostile policies"
        )


def validate_siege_pattern(pattern):
    """PatternCombat marker validation; SiegeCombat owns launch and resolution."""
    if pattern["kind"] != "siege_area":
        raise InputError("Siege weapons require their dedicated area packet model")
    identifier(require(pattern, "source"), "siege weapon source")
    if (
        set(pattern["target_kinds"])
        not in (
            {"defense", "building", "wall"},
            {"defense", "building", "wall", "unit"},
        )
        or pattern["target_layers"] != ["ground"]
        or pattern["maximum_hp_fraction"] != 0
    ):
        raise InputError("Siege weapons need explicit ground structure/wall recipients")
    if (
        "unit" in pattern["target_kinds"]
        and pattern.get("defending_unit_collateral_policy") != "allow"
    ):
        raise InputError(
            "Siege collateral against defenders must be independently declared"
        )
    _validate_projectile(pattern["projectile"])
    _validate_zones(pattern["zones"])
    number(pattern["wall_damage_ratio"], "siege source wall ratio", EPSILON)
    if pattern["zone_composition"] != "strongest_per_recipient":
        raise InputError("Unsupported siege area overlap")


def compile_siege(
    actor, instance, entity, row, modifiers, catalog, movement_units_per_tile
):
    """Compile a carrier without borrowing troop or hero statistic roles."""
    entity_id = entity["id"]
    if entity_id not in SIEGE_MACHINES or entity["category"] != "siege-machine":
        raise InputError("This siege machine needs its own complete lifecycle adapter")
    if (
        actor["team"] != "attack"
        or actor["counts_for_destruction"]
        or instance["mode"] != "normal"
        or instance["statistics_mode"] != "normal"
        or require(instance, "attack_parameters") != {}
        or any(
            field in instance
            for field in (
                "wall_parameters",
                "hero_parameters",
                "payload_member_parameters",
                "garrison_member_parameters",
            )
        )
    ):
        raise InputError(
            "Siege carriers need their attacking role and explicit independent parameters"
        )
    parameters = require(instance, "siege_parameters")
    _validate_parameters(parameters, entity_id)
    technology = (
        instance["town_hall"]
        if parameters["origin"] == "own"
        else parameters["donor_town_hall"]
    )
    if not catalog.available(entity_id, instance["level"], technology):
        raise InputError("Siege level is unavailable to its declared source")
    movement = "ground" if entity_id == "wall-wrecker" else "air"
    hit = number(require(row, "damagePerHit"), "snapshot siege hit", EPSILON)
    wall_ratio = (
        number(require(row, "damageVsWalls"), "snapshot Wrecker wall hit", EPSILON)
        / hit
        if entity_id == "wall-wrecker"
        else 1
    )
    weapon = parameters["weapon"]
    priorities = (
        ["defense", "building", "wall"]
        if entity_id == "wall-wrecker"
        else ["defense", "building"]
    )
    actor.update(
        kind="unit",
        layer=movement,
        movement=movement,
        speed=number(require(entity, "movementSpeed"), "siege movement", EPSILON)
        / movement_units_per_tile
        * modifiers["movement_speed_multiplier"],
        damage=hit * modifiers["damage_multiplier"],
        attack_interval_seconds=number(
            require(entity, "attackSpeed"), "siege attack cadence", EPSILON
        )
        * modifiers["attack_interval_multiplier"],
        range=parameters["range_tiles"] * modifiers["range_multiplier"],
        blocking=False,
        width=0,
        height=0,
        target_priorities=priorities,
        target_priority_tiers=(
            [["defense"], ["building"]]
            if entity_id == "stone-slammer"
            else [list(priorities)]
        ),
        target_layers=["ground"],
        healing_class="siege",
        buff_class="siege",
        hazard_class="siege",
        spring_class="siege",
        beneficial_field_immunity=True,
        attack_model={
            "kind": "siege_area",
            "source": actor["source"],
            "target_kinds": ["defense", "building", "wall"],
            "target_layers": ["ground"],
            "maximum_hp_fraction": 0,
            "projectile": deepcopy(weapon["projectile"]),
            "zones": deepcopy(weapon["zones"]),
            "zone_composition": weapon["zone_composition"],
            "wall_damage_ratio": wall_ratio,
        },
        siege_model={
            "entity": entity_id,
            "parameters": deepcopy(parameters),
            "reported_snapshot_dps": number(
                require(row, "damagePerSecond"), "reported siege DPS", 0
            ),
            "unmodified_hit_damage": hit,
            "death_effects": [
                {
                    **deepcopy(effect),
                    "amount": number(
                        require(row, effect["statistic"]),
                        "siege source death damage",
                        0,
                    )
                    * modifiers["damage_multiplier"]
                    * effect["damage_multiplier"],
                }
                for effect in parameters["death"]["effects"]
            ],
        },
    )
    if movement == "ground":
        actor["wall_behavior"] = {"kind": "avoid", "source": parameters["source"]}
    validate_siege_pattern(actor["attack_model"])
    actor["entity_adapter"].update(
        siege_parameters=deepcopy(parameters),
        behavior_verification="explicit_siege_and_payload_hypotheses_not_replay_validated",
    )
    return actor


def _segment_rectangle_entry(start, end, rectangle):
    """Return traveled distance at first intersection with a closed rectangle."""
    low, high = 0.0, 1.0
    for coordinate, destination, minimum, maximum in zip(
        start, end, rectangle[:2], rectangle[2:]
    ):
        delta = destination - coordinate
        if abs(delta) <= EPSILON:
            if coordinate < minimum - EPSILON or coordinate > maximum + EPSILON:
                return None
            continue
        first, second = (minimum - coordinate) / delta, (maximum - coordinate) / delta
        low = max(low, min(first, second))
        high = min(high, max(first, second))
        if low > high + EPSILON:
            return None
    return max(low, 0) * hypot(end[0] - start[0], end[1] - start[1])


def _range_entry(start, end, target, radius):
    """Exact segment contact with a footprint expanded by a circular radius."""
    if target_distance(start, target) <= radius + EPSILON:
        return 0.0
    left, top = target["x"], target["y"]
    right, bottom = left + target["width"], top + target["height"]
    contacts = [
        _segment_rectangle_entry(
            start, end, (left - radius, top, right + radius, bottom)
        ),
        _segment_rectangle_entry(
            start, end, (left, top - radius, right, bottom + radius)
        ),
    ]
    contacts.extend(
        segment_circle_entry(start, end, corner, radius)
        for corner in ((left, top), (left, bottom), (right, top), (right, bottom))
    )
    return min((contact for contact in contacts if contact is not None), default=None)


def _along(start, end, distance):
    length = hypot(end[0] - start[0], end[1] - start[1])
    if length <= EPSILON:
        return start
    fraction = max(0, min(distance / length, 1))
    return (
        start[0] + (end[0] - start[0]) * fraction,
        start[1] + (end[1] - start[1]) * fraction,
    )


class SiegeCombat:
    """Carrier travel, weapons and termination with independently owned payloads."""

    def __init__(self, actors, select_target, reinforcements, width, height):
        self.actors = actors
        self.ordinary_select_target = select_target
        self.reinforcements = reinforcements
        self.width = width
        self.height = height
        self.models = {}
        self.states = {}
        self.pending = []
        self.serial = 0
        for actor_id, actor in actors.items():
            if "siege_model" not in actor:
                continue
            model = deepcopy(actor["siege_model"])
            _fields(
                model,
                {
                    "entity",
                    "parameters",
                    "reported_snapshot_dps",
                    "unmodified_hit_damage",
                    "death_effects",
                },
                "Siege runtime model",
            )
            if model["entity"] not in SIEGE_MACHINES:
                raise InputError("Unsupported runtime siege entity")
            _validate_parameters(model["parameters"], model["entity"])
            validate_siege_pattern(actor["attack_model"])
            movement = "ground" if model["entity"] == "wall-wrecker" else "air"
            priorities = (
                ["defense", "building", "wall"]
                if model["entity"] == "wall-wrecker"
                else ["defense", "building"]
            )
            if (
                actor["team"] != "attack"
                or actor["kind"] != "unit"
                or actor["movement"] != movement
                or actor["layer"] != movement
                or actor["counts_for_destruction"]
                or actor["blocking"]
                or actor["target_priorities"] != priorities
                or actor["target_layers"] != ["ground"]
                or actor.get("healing_class") != "siege"
                or actor.get("buff_class") != "siege"
                or actor.get("beneficial_field_immunity") is not True
                or model["parameters"]["payload_group_id"]
                != reinforcements.parameters["id"]
                or reinforcements.parameters["delivery"]
                != {"kind": "siege", "carrier_id": actor_id}
            ):
                raise InputError(
                    "Siege runtime role, targeting or payload ownership is inconsistent"
                )
            if (
                actor.get("defending_unit_response", {}).get("primary", "ignore")
                != "ignore"
            ):
                raise InputError(
                    "Siege machines cannot acquire defending troops as primary targets"
                )
            for effect in model["death_effects"]:
                number(require(effect, "amount"), "compiled siege death damage", 0)
            if len(model["death_effects"]) != len(
                model["parameters"]["death"]["effects"]
            ):
                raise InputError("Compiled siege death effects omit source geometry")
            targeting = model["parameters"]["targeting"]
            anchor = None
            if targeting["hall_actor_id"] is not None:
                hall = actors.get(targeting["hall_actor_id"])
                if (
                    hall is None
                    or hall.get("entity_adapter", {}).get("entity") != "town-hall"
                    or hall["team"] != "defense"
                ):
                    raise InputError(
                        "Siege destination must bind to a declared defending Town Hall"
                    )
                anchor = center(hall)
            self.models[actor_id] = model
            if actor["spawn_seconds"] != "controlled":
                reinforcements.validate_deployment_point(
                    {"x": actor["x"], "y": actor["y"]}
                )
            self.states[actor_id] = {
                "phase": "undeployed",
                "deployed_at": None,
                "terminated_at": None,
                "termination_reason": None,
                "anchor": anchor,
                "next_decay": None,
                "expires_at": None,
                "route_arrival": None,
                "blocker": None,
                "weapon_launches": 0,
            }

    def validate_command(self, command, time=None):
        if command.get("kind") != "siege_release":
            return
        _fields(
            command, {"id", "kind", "time_seconds", "target"}, "Manual siege release"
        )
        identifier(command["id"], "siege release command ID")
        number(command["time_seconds"], "siege release time", 0)
        actor_id = command["target"]
        if actor_id not in self.models:
            raise InputError("Manual release does not own the selected siege carrier")
        if time is not None and (
            not _active(self.actors[actor_id], time)
            or self.states[actor_id]["phase"] == "terminated"
        ):
            raise InputError(
                "Manual release requires the active, unspent siege carrier"
            )

    def apply_commands(self, commands, time, trace):
        remaining = []
        for command in commands:
            if command["kind"] == "siege_release":
                self.validate_command(command, time)
                self._activate(command["target"], time, trace)
                self._terminate(command["target"], time, "manual_release", trace)
            else:
                remaining.append(command)
        return remaining

    def _activate(self, actor_id, time, trace):
        state = self.states[actor_id]
        if state["phase"] != "undeployed":
            return
        actor = self.actors[actor_id]
        if (
            actor["spawn_seconds"] == "controlled"
            or actor["spawn_seconds"] > time + EPSILON
        ):
            return
        self.reinforcements.validate_deployment_point(
            {"x": actor["x"], "y": actor["y"]}, time
        )
        termination = self.models[actor_id]["parameters"]["termination"]
        state["phase"] = "active"
        state["deployed_at"] = actor["spawn_seconds"]
        state["next_decay"] = (
            actor["spawn_seconds"] + termination["decay"]["interval_seconds"]
            if termination["decay"]["maximum_hp_fraction_per_pulse"]
            else None
        )
        lifetime = termination["maximum_lifetime_seconds"]
        state["expires_at"] = (
            actor["spawn_seconds"] + lifetime if lifetime is not None else None
        )
        trace.append(
            {"time_seconds": time, "event": "siege_deployed", "source": actor_id}
        )

    def _queue(self, time, packet):
        self.serial += 1
        heappush(self.pending, (time, self.serial, packet))

    def _terminate(self, actor_id, time, reason, trace):
        state = self.states[actor_id]
        if state["phase"] == "terminated":
            return False
        actor = self.actors[actor_id]
        model = self.models[actor_id]
        point = center(actor)
        actor["hp"] = 0
        if actor["death_time"] is None:
            actor["death_time"] = time
        actor["target"] = None
        state.update(
            phase="terminated",
            terminated_at=time,
            termination_reason=reason,
            next_decay=None,
            expires_at=None,
            route_arrival=None,
        )
        self.reinforcements.begin_release(
            time, {"x": point[0], "y": point[1]}, reason, actor_id, trace
        )
        if (
            model["parameters"]["death"]["triggers"] == "all_terminations"
            or reason == "hp_death"
        ):
            for effect in model["death_effects"]:
                self._queue(
                    time + effect["delay_seconds"],
                    {
                        "kind": "death",
                        "source": actor_id,
                        "source_team": actor["team"],
                        "target": None,
                        "position": point,
                        "amount": effect["amount"],
                        "effect": deepcopy(effect),
                        "pattern": deepcopy(actor["attack_model"]),
                    },
                )
        trace.append(
            {
                "time_seconds": time,
                "event": "siege_terminated",
                "source": actor_id,
                "reason": reason,
                "x": point[0],
                "y": point[1],
            }
        )
        return True

    def prepare(self, actors, time, trace, allow_release=True):
        changed = False
        for actor_id, model in self.models.items():
            actor = actors[actor_id]
            self._activate(actor_id, time, trace)
            state = self.states[actor_id]
            if state["phase"] != "active":
                continue
            if actor["hp"] <= 0:
                changed |= self._terminate(actor_id, time, "hp_death", trace)
                continue
            decay = model["parameters"]["termination"]["decay"]
            while (
                state["next_decay"] is not None
                and state["next_decay"] <= time + EPSILON
            ):
                amount = actor["maximum_hp"] * decay["maximum_hp_fraction_per_pulse"]
                actor["hp"] = max(actor["hp"] - amount, 0)
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "siege_decay",
                        "source": actor_id,
                        "damage": amount,
                    }
                )
                state["next_decay"] += decay["interval_seconds"]
                if actor["hp"] <= 0:
                    changed |= self._terminate(actor_id, time, "hp_death", trace)
                    break
            if state["phase"] != "active":
                continue
            if (
                state["expires_at"] is not None
                and state["expires_at"] <= time + EPSILON
            ):
                changed |= self._terminate(actor_id, time, "lifetime_expired", trace)
                continue
            if state["anchor"] is not None:
                position = center(actor)
                radius = model["parameters"]["targeting"]["arrival_radius_tiles"]
                if (
                    hypot(
                        position[0] - state["anchor"][0],
                        position[1] - state["anchor"][1],
                    )
                    <= radius + EPSILON
                ):
                    changed |= self._terminate(actor_id, time, "hall_arrival", trace)
        released = self.reinforcements.prepare(time, trace, allow_release=allow_release)
        return changed or bool(released)

    def _remember_arrival(self, actor, route, time):
        state = self.states[actor["id"]]
        state["route_arrival"] = None
        if route and actor["frozen_until"] <= time + EPSILON:
            state["route_arrival"] = time + _route_length(
                actor, route
            ) / movement_speed(actor)
        return route

    def _hall_route(self, actor):
        state = self.states[actor["id"]]
        anchor = state["anchor"]
        position = center(actor)
        radius = self.models[actor["id"]]["parameters"]["targeting"][
            "arrival_radius_tiles"
        ]
        distance = hypot(anchor[0] - position[0], anchor[1] - position[1])
        return _along(position, anchor, max(distance - radius, 0))

    def select_target(self, actor, actors, time, blocked, width, height):
        actor_id = actor["id"]
        if actor_id not in self.models:
            return self.ordinary_select_target(
                actor, actors, time, blocked, width, height
            )
        state = self.states[actor_id]
        if state["phase"] != "active" or not _active(actor, time):
            return None, None
        entity_id = self.models[actor_id]["entity"]
        if entity_id == "stone-slammer":
            target, route = self.ordinary_select_target(
                actor, actors, time, blocked, width, height
            )
            return target, self._remember_arrival(actor, route, time)
        position = center(actor)
        destination = self._hall_route(actor)
        if entity_id == "battle-blimp":
            choices = [
                (target_distance(position, target), target["id"], target)
                for target in actors.values()
                if _eligible(actor, target, time)
                and target_distance(position, target) <= actor["range"] + EPSILON
            ]
            target = min(choices, key=lambda choice: choice[:2])[2] if choices else None
            actor["target"] = target["id"] if target is not None else None
            route = (
                [destination]
                if hypot(destination[0] - position[0], destination[1] - position[1])
                > EPSILON
                else []
            )
            return target, self._remember_arrival(actor, route, time)
        obstacles = []
        for target in actors.values():
            if (
                target["id"] == actor_id
                or not target["blocking"]
                or not _active(target, time)
            ):
                continue
            rectangle = (
                target["x"],
                target["y"],
                target["x"] + target["width"],
                target["y"] + target["height"],
            )
            entry = _segment_rectangle_entry(position, state["anchor"], rectangle)
            if entry is not None:
                obstacles.append((entry, target["id"], target))
        if not obstacles:
            actor["target"] = None
            state["blocker"] = None
            return None, self._remember_arrival(actor, [destination], time)
        _, _, blocker = min(obstacles, key=lambda choice: choice[:2])
        entry = _range_entry(position, destination, blocker, actor["range"])
        if entry is None:
            actor["target"] = None
            state["blocker"] = None
            return None, self._remember_arrival(actor, [destination], time)
        state["blocker"] = blocker["id"]
        if not _eligible(actor, blocker, time):
            actor["target"] = None
            return None, self._remember_arrival(actor, [], time)
        actor["target"] = blocker["id"]
        route = [_along(position, destination, entry)] if entry > EPSILON else []
        return blocker, self._remember_arrival(actor, route, time)

    def launch(self, actor, target, actors, time, trace):
        if (
            actor["id"] not in self.models
            or self.states[actor["id"]]["phase"] != "active"
        ):
            raise InputError("A terminated or unowned siege cannot launch a weapon")
        if (
            not _eligible(actor, target, time)
            or target_distance(center(actor), target) > actor["range"] + EPSILON
        ):
            raise InputError(
                "Siege weapon target is not currently eligible and in range"
            )
        pattern = deepcopy(actor["attack_model"])
        projectile = pattern["projectile"]
        point = center(target)
        distance = hypot(point[0] - actor["x"], point[1] - actor["y"])
        delay = projectile["delay_seconds"]
        if projectile["timing"] == "launch_distance_delay":
            delay += distance / projectile["speed_tiles_per_second"]
        self._queue(
            time + delay,
            {
                "kind": "weapon",
                "source": actor["id"],
                "source_team": actor["team"],
                "target": target["id"],
                "position": point,
                "amount": actor["damage"],
                "pattern": pattern,
            },
        )
        actor["next_attack"] = time + actor["attack_interval_seconds"] / attack_rate(
            actor
        )
        self.states[actor["id"]]["weapon_launches"] += 1
        trace.append(
            {
                "time_seconds": time,
                "event": "siege_projectile_launch",
                "source": actor["id"],
                "target": target["id"],
                "arrival_seconds": time + delay,
            }
        )

    @staticmethod
    def _eligible_recipient(packet, target, time):
        pattern = packet["pattern"]
        filters = packet["effect"] if packet["kind"] == "death" else pattern
        return (
            _active(target, time)
            and not target.get("_tesla_hidden", False)
            and target["team"] != packet["source_team"]
            and target["kind"] in filters["target_kinds"]
            and target["layer"] in filters["target_layers"]
            and defending_collateral_eligible(packet, target)
        )

    def resolve(self, actors, time, trace):
        damage = defaultdict(float)
        while self.pending and self.pending[0][0] <= time + EPSILON:
            _, _, packet = heappop(self.pending)
            point = packet["position"]
            if packet["kind"] == "weapon":
                target = actors[packet["target"]]
                projectile = packet["pattern"]["projectile"]
                if (
                    not _active(target, time)
                    and projectile["inactive_primary_policy"] == "fizzle"
                ):
                    trace.append(
                        {
                            "time_seconds": time,
                            "event": "siege_projectile_fizzle",
                            "source": packet["source"],
                            "target": target["id"],
                        }
                    )
                    continue
                if projectile["destination"] == "locked_actor_center_at_impact":
                    point = center(target)
            for target in actors.values():
                if not self._eligible_recipient(packet, target, time):
                    continue
                distance = target_distance(point, target)
                if packet["kind"] == "death":
                    effect = packet["effect"]
                    factor = (
                        1
                        if effect["inner_radius_tiles"] - EPSILON
                        <= distance
                        <= effect["outer_radius_tiles"] + EPSILON
                        else 0
                    )
                else:
                    pattern = packet["pattern"]
                    factors = [
                        zone["damage_multiplier"]
                        * (
                            zone["wall_damage_multiplier"]
                            * pattern["wall_damage_ratio"]
                            if target["kind"] == "wall"
                            else 1
                        )
                        for zone in pattern["zones"]
                        if zone["inner_radius_tiles"] - EPSILON
                        <= distance
                        <= zone["outer_radius_tiles"] + EPSILON
                    ]
                    factor = max(factors, default=0)
                if factor <= 0:
                    continue
                amount = packet["amount"] * factor
                protected = target["immune_until"] > time + EPSILON
                if not protected:
                    damage[target["id"]] += amount
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "siege_impact",
                        "source": packet["source"],
                        "target": target["id"],
                        "packet_kind": packet["kind"],
                        "damage": amount,
                        "protected": protected,
                    }
                )
        return damage

    def next_boundary(self, time):
        pending = [
            state[field]
            for state in self.states.values()
            for field in ("next_decay", "expires_at", "route_arrival")
            if state[field] is not None and state[field] > time + EPSILON
        ]
        pending.extend(
            arrival for arrival, _, _ in self.pending if arrival > time + EPSILON
        )
        payload = self.reinforcements.next_boundary(time)
        if payload is not None:
            pending.append(payload)
        return min(pending) if pending else None

    def first_crossing_delay(
        self, actor, route, time, horizon, effective_speed=None, forced_motion=False
    ):
        if (
            actor["id"] not in self.models
            or self.states[actor["id"]]["phase"] != "active"
        ):
            return None
        speed = (
            movement_speed(actor)
            if effective_speed is None
            else number(effective_speed, "siege motion speed", 0)
        )
        if speed <= EPSILON or (
            actor["frozen_until"] > time + EPSILON and not forced_motion
        ):
            return None
        state = self.states[actor["id"]]
        model = self.models[actor["id"]]
        previous = center(actor)
        travelled = 0.0
        earliest = None
        for point in route:
            contacts = []
            if state["anchor"] is not None:
                contacts.append(
                    segment_circle_entry(
                        previous,
                        point,
                        state["anchor"],
                        model["parameters"]["targeting"]["arrival_radius_tiles"],
                    )
                )
            if model["entity"] == "battle-blimp":
                contacts.extend(
                    _range_entry(previous, point, target, actor["range"])
                    for target in self.actors.values()
                    if _eligible(actor, target, time)
                )
            for contact in contacts:
                if contact is not None:
                    delay = (travelled + contact) / speed
                    if EPSILON < delay <= horizon + EPSILON:
                        earliest = delay if earliest is None else min(earliest, delay)
            travelled += hypot(point[0] - previous[0], point[1] - previous[1])
            if travelled > speed * horizon:
                break
            previous = point
        return earliest

    def frame(self, actor):
        state = self.states.get(actor["id"])
        return (
            {
                "siege_phase": state["phase"],
                "siege_blocker": state["blocker"],
                "siege_termination": state["termination_reason"],
            }
            if state
            else {}
        )

    def result(self):
        return {
            "states": deepcopy(self.states),
            "pending_impacts": len(self.pending),
            "reinforcements": self.reinforcements.result(),
            "full_game_prediction": False,
        }
