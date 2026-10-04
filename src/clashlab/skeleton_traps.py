"""One-shot Skeleton Trap reserves released into ordinary defending-unit combat.

The pinned trap row supplies count and Skeleton level, but no combat statistics.
Level-one units therefore require a named, unarmored Skeleton Spell reference
hypothesis. Spell armor is never imported and higher Skeleton levels fail closed.
"""

from copy import deepcopy
from math import floor, hypot

from .spell_visibility import untargetable_until
from .common import InputError, identifier, integer, number, require
from .spatial import EPSILON, _active, _blocked, center
from .trap_support import (
    circle_entry_delay,
    eligible_trap_unit,
    validate_trap_footprints,
)


SKELETON_RULES = {
    "skeleton_trap_trigger": "one_selected_layer_visible_enemy_entry_then_complete_release",
    "skeleton_trap_reserves": "compiler_generated_controlled_defending_units_not_destruction_targets",
    "skeleton_trap_statistics": "explicit_unarmored_level_one_spell_reference_hypothesis",
    "skeleton_trap_release": "declared_clear_offsets_and_finite_independent_release_clock",
    "skeleton_trap_targeting": "shared_retained_defending_unit_targeting_with_explicit_attacker_responses",
}
STATISTIC_BASIS = "unarmored_level_one_skeleton_spell_reference_hypothesis"
HOUSING_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/release-notes/"
    "welcome-to-clash-anytime-update/"
)
PARAMETERS = {
    "source",
    "arming_seconds",
    "trigger_radius_multiplier",
    "excluded_trigger_entities",
    "release_delay_seconds",
    "release_interval_seconds",
    "spawn_offsets",
    "first_attack_delay_seconds",
    "statistics_basis",
    "unit_lifetime_policy",
    "trigger_loss_policy",
    "trap_freeze_policy",
    "spawn_policy",
    "ground_wall_policy",
    "released_targeting_policy",
}
MODEL_FIELDS = {
    "id",
    "entity",
    "level",
    "team",
    "mode",
    "statistics_source",
    "x",
    "y",
    "width",
    "height",
    "damage",
    "trigger_radius",
    "skeleton_level",
    "unit_ids",
    "unit_statistics",
    "parameters",
}


def _validate_parameters(parameters, count):
    if not isinstance(parameters, dict) or set(parameters) != PARAMETERS:
        raise InputError("Skeleton Trap requires every release and statistics policy")
    identifier(parameters["source"], "Skeleton Trap evidence")
    for field in (
        "arming_seconds",
        "release_delay_seconds",
        "release_interval_seconds",
        "first_attack_delay_seconds",
    ):
        number(parameters[field], field, 0)
    number(
        parameters["trigger_radius_multiplier"],
        "Skeleton trigger radius scale",
        EPSILON,
    )
    policies = {
        "statistics_basis": STATISTIC_BASIS,
        "unit_lifetime_policy": "persist_until_killed_or_battle_end",
        "trigger_loss_policy": "complete_release_after_trigger_even_if_enemy_leaves_or_dies",
        "trap_freeze_policy": "release_clock_independent_of_unit_freeze",
        "spawn_policy": "declared_offsets_must_be_clear",
        "ground_wall_policy": "avoid_all_blocking_walls_and_structures",
        "released_targeting_policy": "nearest_retained_hostile_units_anywhere",
    }
    for field, expected in policies.items():
        if parameters[field] != expected:
            raise InputError(f"Unsupported Skeleton Trap {field}")
    excluded = parameters["excluded_trigger_entities"]
    if not isinstance(excluded, list) or len(excluded) != len(set(excluded)):
        raise InputError("Skeleton trigger exclusions must be an explicit unique list")
    for entity_id in excluded:
        identifier(entity_id, "Skeleton trigger exclusion")
    offsets = parameters["spawn_offsets"]
    if not isinstance(offsets, list) or len(offsets) != count:
        raise InputError("Skeleton Trap needs one explicit spawn offset per unit")
    for offset in offsets:
        if not isinstance(offset, dict) or set(offset) != {"dx", "dy"}:
            raise InputError("Skeleton spawn offsets require dx and dy")
        number(offset["dx"], "Skeleton horizontal offset")
        number(offset["dy"], "Skeleton vertical offset")


def compile_skeleton_trap(instance, catalog, movement_units_per_tile):
    """Return a trap model; compile_skeleton_reserves creates its owned actors."""
    if require(instance, "entity") != "skeleton-trap":
        raise InputError("Skeleton Trap compiler requires skeleton-trap")
    level = integer(require(instance, "level"), "Skeleton Trap level", 1)
    town_hall = integer(require(instance, "town_hall"), "Skeleton Trap Town Hall", 1)
    if not catalog.available("skeleton-trap", level, town_hall):
        raise InputError("Skeleton Trap level is unavailable at the selected Town Hall")
    if require(instance, "team") != "defense":
        raise InputError("Skeleton Traps belong to the defending team")
    mode = require(instance, "mode")
    if mode not in {"ground", "air"}:
        raise InputError("Skeleton Trap requires an explicit ground or air mode")
    row = catalog.level("skeleton-trap", level)
    skeleton_level = integer(require(row, "skeletonLevel"), "trap Skeleton level", 1)
    if skeleton_level != 1:
        raise InputError("Higher trap Skeleton levels need separate combat statistics")
    count = integer(require(row, "spawnedUnits"), "spawned Skeleton count", 1)
    parameters = require(instance, "parameters")
    _validate_parameters(parameters, count)
    for entity_id in parameters["excluded_trigger_entities"]:
        catalog.entity(entity_id)
    conversion = number(
        movement_units_per_tile, "Skeleton movement units per tile", EPSILON
    )
    reference = require(catalog.entity("skeleton-spell"), "skeletonStats")
    cadence = number(
        require(reference, "attackSpeed"), "reference Skeleton cadence", EPSILON
    )
    statistics = {
        "source": catalog.records["skeleton-spell"]["source"],
        "basis": STATISTIC_BASIS,
        "hitpoints": number(
            require(reference, "hitpoints"), "reference Skeleton HP", EPSILON
        ),
        "damage": number(
            require(reference, "damagePerSecond"), "reference Skeleton DPS", EPSILON
        )
        * cadence,
        "attack_interval_seconds": cadence,
        "speed": number(
            require(reference, "movementSpeed"), "reference Skeleton speed", EPSILON
        )
        / conversion,
        "range": number(
            require(reference, "range"), "reference Skeleton range", EPSILON
        ),
        "housing_space": 1,
        "housing_source": HOUSING_SOURCE,
        "armor_policy": "none_spell_armor_is_not_a_trap_statistic",
        "layer_mapping": "selected_trap_mode_is_both_unit_and_weapon_layer_hypothesis",
    }
    trap_id = identifier(require(instance, "id"), "Skeleton Trap instance")
    return {
        "id": trap_id,
        "entity": "skeleton-trap",
        "level": level,
        "team": "defense",
        "mode": mode,
        "statistics_source": catalog.records["skeleton-trap"]["source"],
        "x": integer(require(instance, "x"), "Skeleton Trap x", 0),
        "y": integer(require(instance, "y"), "Skeleton Trap y", 0),
        "width": 1,
        "height": 1,
        "damage": number(require(row, "damage"), "Skeleton Trap direct damage", 0),
        "trigger_radius": number(
            catalog.entity("skeleton-trap")["triggerRadius"],
            "Skeleton trigger radius",
            EPSILON,
        )
        * parameters["trigger_radius_multiplier"],
        "skeleton_level": skeleton_level,
        "unit_ids": [f"{trap_id}::skeleton:{index}" for index in range(count)],
        "unit_statistics": statistics,
        "parameters": deepcopy(parameters),
    }


def compile_skeleton_reserves(trap):
    """Preallocate genuine combat units without creating additional layout objects."""
    statistics = trap["unit_statistics"]
    parameters = trap["parameters"]
    actors = []
    for index, actor_id in enumerate(trap["unit_ids"]):
        offset = parameters["spawn_offsets"][index]
        point = center(trap)
        actor = {
            "id": actor_id,
            "source": statistics["source"],
            "team": "defense",
            "kind": "unit",
            "layer": trap["mode"],
            "movement": trap["mode"],
            "spawn_seconds": "controlled",
            "first_attack_seconds": parameters["first_attack_delay_seconds"],
            "x": point[0] + offset["dx"],
            "y": point[1] + offset["dy"],
            "width": 0,
            "height": 0,
            "blocking": False,
            "counts_for_destruction": False,
            **{
                field: statistics[field]
                for field in (
                    "hitpoints",
                    "damage",
                    "speed",
                    "range",
                    "attack_interval_seconds",
                    "housing_space",
                )
            },
            "minimum_range": 0,
            "target_priorities": ["unit"],
            "target_priority_tiers": [["unit"]],
            "target_layers": [trap["mode"]],
            "healing_class": "troop",
            "hazard_class": "defending_troop",
            "buff_class": "troop",
            "spring_class": "other",
            "attack_model": {
                "kind": "single",
                "source": statistics["source"],
                "target_kinds": ["unit"],
                "target_layers": [trap["mode"]],
                "maximum_hp_fraction": 0,
                "projectile": {
                    "timing": "instant",
                    "delay_seconds": 0,
                    "destination": "locked_actor_center_at_impact",
                    "hit_radius": 0,
                },
            },
            "trap_summon_model": {
                "trap_id": trap["id"],
                "unit_index": index,
                "unit_level": trap["skeleton_level"],
                "statistics_basis": statistics["basis"],
                "lifetime_policy": parameters["unit_lifetime_policy"],
            },
            "entity_adapter": {
                "entity": "skeleton-trap",
                "level": trap["level"],
                "mode": trap["mode"],
                "generated_unit": "trap_skeleton",
                "snapshot_verification": "unverified_snapshot",
                "behavior_verification": STATISTIC_BASIS,
                "modifiers": {
                    "source": parameters["source"],
                    **{
                        field: 1
                        for field in (
                            "hitpoints_multiplier",
                            "damage_multiplier",
                            "maximum_hp_damage_multiplier",
                            "attack_interval_multiplier",
                            "range_multiplier",
                            "movement_speed_multiplier",
                        )
                    },
                },
            },
        }
        if trap["mode"] == "ground":
            actor["wall_behavior"] = {"kind": "avoid", "source": parameters["source"]}
        actors.append(actor)
    return actors


def validate_skeleton_deployment(effect, actors):
    """Only the trap release clock may deploy one of its generated reserves."""
    if effect.get("kind") == "deploy" and any(
        "trap_summon_model" in actors.get(actor_id, {})
        for actor_id in effect.get("targets", [])
    ):
        raise InputError(
            "Skeleton Trap reserves cannot be deployed by external commands"
        )


class SkeletonTrapCombat:
    """Trigger once and release preallocated units on an independent finite clock."""

    def __init__(self, traps, actors, width, height):
        self.models = {}
        self.actors = actors
        self.width = width
        self.height = height
        validate_trap_footprints(traps, actors, width, height)
        owned = set()
        for trap in traps:
            if set(trap) - {"battle_modifier_application"} != MODEL_FIELDS:
                raise InputError(
                    "Skeleton Trap model has unsupported or missing fields"
                )
            if trap["entity"] != "skeleton-trap" or trap["team"] != "defense":
                raise InputError("Skeleton runtime requires a defending Skeleton Trap")
            if trap["mode"] not in {"ground", "air"} or trap["damage"] != 0:
                raise InputError(
                    "Skeleton Trap must remain a selected-layer summon trap"
                )
            unit_ids = trap["unit_ids"]
            if not unit_ids or len(unit_ids) != len(set(unit_ids)):
                raise InputError("Skeleton Trap requires unique generated reserve IDs")
            _validate_parameters(trap["parameters"], len(unit_ids))
            number(trap["trigger_radius"], "Skeleton Trap trigger radius", EPSILON)
            for index, actor_id in enumerate(unit_ids):
                if actor_id not in actors or actor_id in owned:
                    raise InputError("Skeleton reserves must be unique existing actors")
                actor = actors[actor_id]
                ownership = actor.get("trap_summon_model", {})
                if (
                    ownership.get("trap_id") != trap["id"]
                    or ownership.get("unit_index") != index
                    or actor["team"] != "defense"
                    or actor["kind"] != "unit"
                    or actor["spawn_seconds"] != "controlled"
                    or actor["counts_for_destruction"]
                    or actor["blocking"]
                    or actor["layer"] != trap["mode"]
                    or actor["target_priorities"] != ["unit"]
                ):
                    raise InputError(
                        "Skeleton reserve identity or combat role is invalid"
                    )
                self._validate_spawn(actor, actors, 0)
                owned.add(actor_id)
            self.models[trap["id"]] = deepcopy(trap)
        if owned != {
            actor_id
            for actor_id, actor in actors.items()
            if "trap_summon_model" in actor
        }:
            raise InputError("Every Skeleton reserve must belong to one declared trap")
        self.states = {
            trap_id: {
                "trigger_seconds": None,
                "trigger_id": None,
                "released": 0,
                "next_release": None,
            }
            for trap_id in self.models
        }

    def _validate_spawn(self, actor, actors, time):
        if not (0 <= actor["x"] < self.width and 0 <= actor["y"] < self.height):
            raise InputError("Skeleton spawn point lies outside the board")
        if actor["layer"] == "ground" and (
            floor(actor["x"]),
            floor(actor["y"]),
        ) in _blocked(actors, time):
            raise InputError(
                "Skeleton ground spawn point occupies a blocking footprint"
            )

    @staticmethod
    def _eligible(trap, actor, time):
        return eligible_trap_unit(
            actor,
            trap["team"],
            [trap["mode"]],
            trap["parameters"]["excluded_trigger_entities"],
            time,
        )

    def prepare(self, actors, time, trace):
        for trap_id, trap in sorted(self.models.items()):
            state = self.states[trap_id]
            parameters = trap["parameters"]
            if state["trigger_seconds"] is None:
                if time + EPSILON < parameters["arming_seconds"]:
                    continue
                point = center(trap)
                candidates = [
                    actor
                    for actor in actors.values()
                    if self._eligible(trap, actor, time)
                    and hypot(center(actor)[0] - point[0], center(actor)[1] - point[1])
                    <= trap["trigger_radius"] + EPSILON
                ]
                if not candidates:
                    continue
                trigger = min(
                    candidates,
                    key=lambda actor: (
                        hypot(center(actor)[0] - point[0], center(actor)[1] - point[1]),
                        actor["id"],
                    ),
                )
                state.update(
                    trigger_seconds=time,
                    trigger_id=trigger["id"],
                    next_release=time + parameters["release_delay_seconds"],
                )
                trace.append(
                    {
                        "event": "skeleton_trap_trigger",
                        "time_seconds": time,
                        "trap": trap_id,
                        "trigger": trigger["id"],
                    }
                )
            while (
                state["next_release"] is not None
                and state["next_release"] <= time + EPSILON
            ):
                actor_id = trap["unit_ids"][state["released"]]
                actor = actors[actor_id]
                if actor["spawn_seconds"] != "controlled":
                    raise InputError("Skeleton Trap reserve was externally deployed")
                self._validate_spawn(actor, actors, time)
                actor.update(
                    spawn_seconds=time,
                    target=None,
                    next_attack=time + actor["first_attack_seconds"],
                )
                actor["_terminal_ground_approach"] = True
                state["released"] += 1
                state["next_release"] = (
                    state["trigger_seconds"]
                    + parameters["release_delay_seconds"]
                    + state["released"] * parameters["release_interval_seconds"]
                    if state["released"] < len(trap["unit_ids"])
                    else None
                )
                trace.append(
                    {
                        "event": "skeleton_trap_release",
                        "time_seconds": time,
                        "trap": trap_id,
                        "unit": actor_id,
                        "position": center(actor),
                    }
                )

    def next_boundary(self, time):
        boundaries = []
        if self.models:
            boundaries.extend(
                untargetable_until(actor)
                for actor in self.actors.values()
                if _active(actor, time)
            )
        for trap_id, state in self.states.items():
            if state["trigger_seconds"] is None:
                boundaries.append(self.models[trap_id]["parameters"]["arming_seconds"])
            elif state["next_release"] is not None:
                boundaries.append(state["next_release"])
        future = [boundary for boundary in boundaries if boundary > time + EPSILON]
        return min(future) if future else None

    def first_crossing_delay(self, actor, route, time, horizon, effective_speed):
        delays = []
        for trap_id, trap in self.models.items():
            if (
                self.states[trap_id]["trigger_seconds"] is not None
                or time + EPSILON < trap["parameters"]["arming_seconds"]
                or not self._eligible(trap, actor, time)
            ):
                continue
            delay = circle_entry_delay(
                actor,
                route,
                center(trap),
                trap["trigger_radius"],
                horizon,
                effective_speed,
            )
            if delay is not None:
                delays.append(delay)
        return min(delays) if delays else None

    def result(self):
        return {
            "states": deepcopy(self.states),
            "generated_unit_ids": [
                actor_id
                for trap in self.models.values()
                for actor_id in trap["unit_ids"]
            ],
            "statistics_verification": STATISTIC_BASIS,
        }
