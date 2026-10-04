"""Conditional defending heroes with banner-bound patrol and combat lifecycles.

Snapshot base statistics do not establish defensive AI. Acquisition, leash,
patrol, regeneration and statue destruction semantics are explicit hypotheses.
The banner is metadata, never a damageable building or an extra destruction
credit. The Warden statue is a separate, explicitly counted or excluded actor.
"""

from collections import defaultdict, deque
from copy import deepcopy
from math import floor, hypot

from .common import InputError, identifier, integer, number, require
from .rates import movement_speed
from .spatial import (
    EPSILON,
    _active,
    _blocked,
    _eligible,
    _ground_route,
    _route_length,
    center,
    target_distance,
)
from .traps import segment_circle_entry


DEFENDING_HEROES = {
    "barbarian-king",
    "archer-queen",
    "royal-champion",
    "grand-warden",
    "minion-prince",
}
DEFENDING_HERO_RULES = {
    "defending_hero_statistics": "explicit_snapshot_base_without_attacking_equipment_or_pets",
    "defending_hero_banner": "unique_nonblocking_indestructible_metadata_with_catalog_footprint_and_slot_limit",
    "defending_hero_aggro": "banner_center_search_radius_or_received_damage_then_nearest_reachable_enemy",
    "defending_hero_leash": "return_after_primary_loss_or_leash_boundary_no_reacquisition_until_home",
    "defending_hero_patrol": "ordered_explicit_waypoints_with_exact_arrival_and_wait_boundaries",
    "defending_hero_wall_motion": "explicit_avoid_all_blocking_walls_and_structures",
    "defending_hero_healing": "explicit_home_only_pulses_after_combat_delay_no_resurrection",
    "defending_hero_freeze": "shared_attack_and_movement_pause_heal_clock_skips_frozen_pulses",
    "defending_hero_death": "permanent_actor_death_with_released_projectiles_persisting",
    "defending_warden": "stationary_banner_footprint_statue_with_explicit_destruction_policy",
    "defending_unit_response": "explicit_per_attacker_primary_tier_and_separate_collateral_policy",
}
PARAMETERS = {
    "source",
    "statistics_mapping",
    "equipment_policy",
    "pet_policy",
    "ability_policy",
    "destruction_policy",
    "banner",
    "aggro",
    "leash",
    "patrol",
    "return",
    "healing",
    "death",
}
PRIMARY_RESPONSES = {"same_tier_as_buildings", "after_buildings", "ignore"}


def _fields(value, fields, label):
    if not isinstance(value, dict) or set(value) != fields:
        raise InputError(f"{label} requires its complete explicit parameters")


def _distance(first, second):
    return hypot(first[0] - second[0], first[1] - second[1])


def _anchor(model):
    banner = model["banner"]
    return banner["x"] + banner["width"] / 2, banner["y"] + banner["height"] / 2


def _validate_parameters(parameters, statue):
    _fields(parameters, PARAMETERS, "Defending hero")
    identifier(parameters["source"], "defending hero evidence")
    policies = {
        "statistics_mapping": "snapshot_base_defending_no_equipment_hypothesis",
        "equipment_policy": "none_on_defense",
        "pet_policy": "none_on_defense",
        "ability_policy": "no_active_defending_ability",
        "death": "permanent_for_battle",
    }
    for field, policy in policies.items():
        if parameters[field] != policy:
            raise InputError(f"Unsupported defending hero {field}")
    destruction = (
        {"statue_counts_hypothesis", "statue_excluded_hypothesis"}
        if statue
        else {"hero_excluded_hypothesis"}
    )
    if parameters["destruction_policy"] not in destruction:
        raise InputError("Defending hero/statue destruction policy must be explicit")
    banner = parameters["banner"]
    _fields(banner, {"id", "x", "y", "footprint_policy"}, "Hero banner")
    identifier(banner["id"], "hero banner ID")
    for axis in ("x", "y"):
        integer(banner[axis], "banner coordinate", 0)
    if banner["footprint_policy"] != "nonblocking_indestructible_anchor":
        raise InputError("Unsupported hero banner footprint hypothesis")
    aggro = parameters["aggro"]
    _fields(
        aggro,
        {"radius_basis", "radius_multiplier", "trigger", "retaliation"},
        "Defending hero aggro",
    )
    if (
        aggro["radius_basis"] != "snapshot_searchRadius"
        or aggro["trigger"] != "altar_radius_or_received_damage"
        or aggro["retaliation"] != "nearest_eligible_within_leash"
    ):
        raise InputError("Unsupported defending hero aggro hypothesis")
    number(aggro["radius_multiplier"], "hero aggro radius scale", EPSILON)
    leash = parameters["leash"]
    _fields(leash, {"radius_tiles", "loss_policy"}, "Defending hero leash")
    number(leash["radius_tiles"], "hero leash radius", EPSILON)
    if (
        leash["loss_policy"]
        != "return_when_primary_dead_ineligible_outside_leash_or_unreachable"
    ):
        raise InputError("Unsupported defending hero leash loss policy")
    patrol = parameters["patrol"]
    _fields(patrol, {"waypoints", "selection"}, "Defending hero patrol")
    if patrol["selection"] != "ordered_loop" or not isinstance(
        patrol["waypoints"], list
    ):
        raise InputError("Defending patrol needs an explicit ordered waypoint list")
    if statue and patrol["waypoints"]:
        raise InputError("A defending Warden statue cannot patrol")
    for waypoint in patrol["waypoints"]:
        _fields(waypoint, {"x", "y", "wait_seconds"}, "Defending patrol waypoint")
        for axis in ("x", "y"):
            number(waypoint[axis], "patrol coordinate", 0)
        number(waypoint["wait_seconds"], "patrol dwell time", 0)
    if parameters["return"] != {
        "reacquire": "only_after_arrival",
        "attack_clock": "preserve_shared_cooldown",
    }:
        raise InputError("Defending hero return and cooldown policies must be explicit")
    healing = parameters["healing"]
    _fields(
        healing,
        {
            "amount_per_pulse",
            "interval_seconds",
            "delay_after_combat_seconds",
            "location",
            "freeze",
            "first_pulse",
        },
        "Defending hero healing",
    )
    number(healing["amount_per_pulse"], "defending heal amount", 0)
    number(healing["interval_seconds"], "defending heal interval", EPSILON)
    number(healing["delay_after_combat_seconds"], "defending heal delay", 0)
    if (
        healing["location"] != "at_banner_only"
        or healing["freeze"] != "pulse_clock_continues_skip_while_frozen"
        or healing["first_pulse"] != "one_interval_after_home_and_combat_delay"
    ):
        raise InputError("Unsupported defending regeneration hypothesis")


def compile_defending_hero(
    actor, instance, entity, row, modifiers, catalog, movement_units_per_tile
):
    """Compile independently of the attacking-hero equipment registry."""
    from .combat import validate_pattern

    entity_id = entity["id"]
    if entity_id not in DEFENDING_HEROES or entity["category"] != "hero":
        raise InputError(
            "This defending hero needs an entity-specific behavior adapter"
        )
    statue = entity_id == "grand-warden"
    expected_mode = (
        "statue" if statue else "air" if entity_id == "minion-prince" else "ground"
    )
    if (
        instance["entity"] != entity_id
        or actor["team"] != "defense"
        or actor["spawn_seconds"] != 0
        or instance["statistics_mode"] != "normal"
        or instance["mode"] != expected_mode
        or any(field in instance for field in ("hero_parameters", "equipment", "pet"))
    ):
        raise InputError(
            "Defending heroes require initial defense deployment, their defensive mode, and no attack loadout"
        )
    parameters = require(instance, "defending_hero_parameters")
    _validate_parameters(parameters, statue)
    counted = parameters["destruction_policy"] == "statue_counts_hypothesis"
    if actor["counts_for_destruction"] != counted:
        raise InputError("Hero destruction eligibility must match its explicit policy")
    banner = deepcopy(parameters["banner"])
    dimensions = catalog.entity("hero-banner")["size"].split("x")
    banner["width"], banner["height"] = (int(part) for part in dimensions)
    slots = next(
        (
            entry["count"]
            for entry in catalog.entity("hero-banner")["availablePerTownHall"]
            if entry["townHallLevel"] == instance["town_hall"]
        ),
        0,
    )
    if slots == 0:
        raise InputError("No defending hero banners exist at this Town Hall")
    point = banner["x"] + banner["width"] / 2, banner["y"] + banner["height"] / 2
    expected_position = (banner["x"], banner["y"]) if statue else point
    if (actor["x"], actor["y"]) != expected_position:
        raise InputError("Defending hero must begin at its declared banner")
    aggro_radius = number(
        require(entity, "searchRadius"), "snapshot hero search radius", EPSILON
    )
    aggro_radius *= parameters["aggro"]["radius_multiplier"]
    if parameters["leash"]["radius_tiles"] <= aggro_radius:
        raise InputError(
            "Defender leash must exceed acquisition radius to avoid boundary reaggro"
        )
    if statue or expected_mode == "air":
        if "wall_parameters" in instance:
            raise InputError(
                "Stationary and flying defenders cannot have ground wall rules"
            )
    else:
        wall = require(instance, "wall_parameters")
        _fields(wall, {"kind", "source"}, "Defender wall behavior")
        if wall["kind"] != "avoid":
            raise InputError("This defending ground route explicitly avoids all walls")
        identifier(wall["source"], "defending wall behavior evidence")
        actor["wall_behavior"] = deepcopy(wall)
    layers = ["ground"] if entity_id == "barbarian-king" else ["ground", "air"]
    interval = number(
        require(entity, "attackSpeed"), "defending hero attack interval", EPSILON
    )
    attack = require(instance, "attack_parameters")
    _fields(attack, {"projectile"}, "Defending hero weapon")
    actor.update(
        kind="defense" if statue else "unit",
        layer="air" if expected_mode == "air" else "ground",
        movement="stationary" if statue else expected_mode,
        speed=(
            0
            if statue
            else number(require(entity, "movementSpeed"), "defending movement", EPSILON)
            / movement_units_per_tile
            * modifiers["movement_speed_multiplier"]
        ),
        damage=number(
            require(row, "damagePerHit"), "defending base hit damage", EPSILON
        )
        * modifiers["damage_multiplier"],
        attack_interval_seconds=interval * modifiers["attack_interval_multiplier"],
        range=number(require(entity, "range"), "defending hero range", EPSILON)
        * modifiers["range_multiplier"],
        blocking=False,
        width=banner["width"] if statue else 0,
        height=banner["height"] if statue else 0,
        target_priorities=["unit"],
        target_priority_tiers=[["unit"]],
        target_layers=layers,
        healing_class="hero",
        hazard_class="hero",
        attack_model={
            "kind": "single",
            "source": actor["source"],
            "target_kinds": ["unit"],
            "target_layers": layers,
            "maximum_hp_fraction": 0,
            "projectile": deepcopy(attack["projectile"]),
        },
        defending_hero_model={
            "entity": entity_id,
            "source": parameters["source"],
            "statue": statue,
            "town_hall": instance["town_hall"],
            "banner_slots": slots,
            "banner": banner,
            "aggro_radius": aggro_radius,
            "parameters": deepcopy(parameters),
        },
    )
    validate_pattern(actor["attack_model"])
    actor["entity_adapter"].update(
        defending_hero_parameters=deepcopy(parameters),
        behavior_verification="explicit_defending_hero_hypotheses_not_replay_validated",
        equipment_statistics="no_attacking_equipment_statistics_applied",
    )
    return actor


def apply_defending_unit_responses(scene):
    """Apply explicit acquisition and collateral changes before runtime loading.

    This also handles predeclared Mirror units: every attacking unit gets its own
    entry. A primary policy never silently chooses a collateral-damage policy.
    """
    specification = require(scene, "defending_unit_responses")
    _fields(specification, {"source", "actors"}, "Defending-unit responses")
    identifier(specification["source"], "defending-unit response evidence")
    responses = specification["actors"]
    attackers = {
        actor["id"]: actor
        for actor in scene["actors"]
        if actor["team"] == "attack" and actor["kind"] == "unit"
    }
    if not isinstance(responses, dict) or set(responses) != set(attackers):
        raise InputError(
            "Defending-unit responses must explicitly cover every attacking unit"
        )
    for actor_id, actor in attackers.items():
        response = responses[actor_id]
        _fields(response, {"primary", "collateral"}, "Attacker defending-unit response")
        if response["primary"] not in PRIMARY_RESPONSES or response[
            "collateral"
        ] not in {"allow", "ignore"}:
            raise InputError(
                "Unsupported defending-unit primary or collateral response"
            )
        if "defending_unit_response" in actor:
            raise InputError("Defending-unit responses cannot be applied twice")
        actor["defending_unit_response"] = {
            "source": specification["source"],
            **deepcopy(response),
        }
        if actor["attack_model"]["kind"] == "none":
            if response != {"primary": "ignore", "collateral": "ignore"}:
                raise InputError(
                    "Non-attacking support units must ignore defending-unit combat"
                )
            continue
        pattern = actor["attack_model"]
        if "unit" in actor["target_priorities"]:
            raise InputError(
                "Attacking unit already has an unbound defending-unit primary rule"
            )
        # Ordinary compiler patterns can share this list with the primary
        # priorities. Collateral membership must not mutate acquisition rules.
        pattern["target_kinds"] = list(pattern["target_kinds"])
        pattern["defending_unit_collateral_policy"] = response["collateral"]
        if response["primary"] != "ignore" or response["collateral"] == "allow":
            if "unit" not in pattern["target_kinds"]:
                pattern["target_kinds"].append("unit")
        if response["primary"] == "ignore":
            continue
        tiers = deepcopy(actor["target_priority_tiers"])
        actor["target_priority_tiers"] = tiers
        if response["primary"] == "after_buildings":
            tiers.append(["unit"])
        else:
            tier = next((tier for tier in tiers if "building" in tier), None)
            if tier is None:
                raise InputError(
                    "Same-tier defending response needs a building target tier"
                )
            tier.append("unit")
        actor["target_priorities"] = [kind for tier in tiers for kind in tier]


def defending_collateral_eligible(packet, actor):
    """Shared PatternCombat hook: a selected primary still takes its direct hit."""
    return not (
        actor["kind"] == "unit"
        and actor["team"] == "defense"
        and packet["pattern"].get("defending_unit_collateral_policy") == "ignore"
        and actor["id"] != packet["target"]
    )


def validate_defending_unit_responses(actors, specification):
    """Reject raw scenes whose combat eligibility bypasses the response binding."""
    responses = require(specification, "defending_unit_responses")
    _fields(responses, {"source", "actors"}, "Defending-unit responses")
    identifier(responses["source"], "defending-unit response evidence")
    attackers = {
        actor_id: actor
        for actor_id, actor in actors.items()
        if actor["team"] == "attack" and actor["kind"] == "unit"
    }
    if not isinstance(responses["actors"], dict) or set(responses["actors"]) != set(
        attackers
    ):
        raise InputError("Runtime responses must cover every attacking unit")
    for actor_id, actor in attackers.items():
        response = responses["actors"][actor_id]
        _fields(response, {"primary", "collateral"}, "Runtime attacker response")
        if response["primary"] not in PRIMARY_RESPONSES or response[
            "collateral"
        ] not in {"allow", "ignore"}:
            raise InputError("Unsupported runtime defending-unit response")
        if actor.get("defending_unit_response") != {
            "source": responses["source"],
            **response,
        }:
            raise InputError("Runtime actor response does not match the scene binding")
        pattern = actor["attack_model"]
        if pattern["kind"] == "none":
            if response != {"primary": "ignore", "collateral": "ignore"}:
                raise InputError("Non-attacking support cannot acquire defending units")
            continue
        has_primary = "unit" in actor["target_priorities"]
        if has_primary != (response["primary"] != "ignore"):
            raise InputError(
                "Runtime defending-unit acquisition disagrees with its binding"
            )
        if pattern.get("defending_unit_collateral_policy") != response["collateral"]:
            raise InputError(
                "Runtime defending-unit collateral policy disagrees with its binding"
            )
        if ("unit" in pattern["target_kinds"]) != (
            has_primary or response["collateral"] == "allow"
        ):
            raise InputError(
                "Runtime defending-unit damage eligibility disagrees with its binding"
            )
        if response["primary"] == "same_tier_as_buildings":
            if not any(
                "unit" in tier and "building" in tier
                for tier in actor["target_priority_tiers"]
            ):
                raise InputError(
                    "Defending-unit primary is not in the declared building tier"
                )
        elif response["primary"] == "after_buildings":
            if actor["target_priority_tiers"][-1] != ["unit"]:
                raise InputError(
                    "Defending-unit primary must follow all structure tiers"
                )


def _validate_model(actor):
    model = require(actor, "defending_hero_model")
    _fields(
        model,
        {
            "entity",
            "source",
            "statue",
            "town_hall",
            "banner_slots",
            "banner",
            "aggro_radius",
            "parameters",
        },
        "Defending hero runtime model",
    )
    if model["entity"] not in DEFENDING_HEROES or not isinstance(model["statue"], bool):
        raise InputError("Unsupported defending hero identity")
    if model["statue"] != (model["entity"] == "grand-warden"):
        raise InputError("Only Warden uses the defending statue lifecycle")
    _validate_parameters(model["parameters"], model["statue"])
    identifier(model["source"], "defender model source")
    integer(model["town_hall"], "defending Town Hall", 1)
    integer(model["banner_slots"], "defending banner slots", 1)
    number(model["aggro_radius"], "defender acquisition radius", EPSILON)
    if model["parameters"]["leash"]["radius_tiles"] <= model["aggro_radius"]:
        raise InputError("Defender leash must exceed acquisition radius")
    _fields(
        model["banner"],
        {"id", "x", "y", "width", "height", "footprint_policy"},
        "Runtime hero banner",
    )
    for field in ("width", "height"):
        integer(model["banner"][field], "banner footprint", 1)
    if {
        key: value
        for key, value in model["banner"].items()
        if key not in {"width", "height"}
    } != model["parameters"]["banner"]:
        raise InputError("Runtime and declared banner disagree")
    if (
        actor["team"] != "defense"
        or actor["spawn_seconds"] != 0
        or actor["kind"] != ("defense" if model["statue"] else "unit")
        or actor["blocking"]
        or "hero_model" in actor
        or actor["counts_for_destruction"]
        != (model["parameters"]["destruction_policy"] == "statue_counts_hypothesis")
    ):
        raise InputError(
            "Invalid defending hero runtime role or destruction eligibility"
        )
    expected_movement = (
        "stationary"
        if model["statue"]
        else "air" if model["entity"] == "minion-prince" else "ground"
    )
    expected_layers = (
        ["ground"] if model["entity"] == "barbarian-king" else ["ground", "air"]
    )
    if (
        actor["movement"] != expected_movement
        or actor["layer"] != ("air" if expected_movement == "air" else "ground")
        or actor["target_priorities"] != ["unit"]
        or actor["target_layers"] != expected_layers
        or _distance(center(actor), _anchor(model)) > EPSILON
    ):
        raise InputError(
            "Defending hero movement, targeting or initial banner position is inconsistent"
        )
    return model


class DefendingHeroCombat:
    """Target wrapper with explicit patrol/return routes and scheduled recovery."""

    def __init__(self, actors, select_target, specification):
        self.models = {
            actor["id"]: deepcopy(_validate_model(actor))
            for actor in actors.values()
            if "defending_hero_model" in actor
        }
        self.ordinary_select_target = select_target
        self.actors = actors
        self.width = specification["width"]
        self.height = specification["height"]
        self.states = {}
        self.trace = None
        self.reachable_cells = {}
        self.blocked = set()
        if self.models or "defending_unit_responses" in specification:
            validate_defending_unit_responses(actors, specification)
        blocking_cells = {
            (x, y)
            for other in actors.values()
            if other["blocking"]
            for x in range(other["x"], other["x"] + other["width"])
            for y in range(other["y"], other["y"] + other["height"])
        }
        occupied_banners = set()
        hero_ids = set()
        banner_ids = set()
        for actor_id, model in self.models.items():
            banner = model["banner"]
            if model["entity"] in hero_ids or banner["id"] in banner_ids:
                raise InputError("Defending heroes and their banner IDs must be unique")
            if banner["id"] in actors:
                raise InputError(
                    "A hero banner is indestructible metadata, not a second actor"
                )
            hero_ids.add(model["entity"])
            banner_ids.add(banner["id"])
            if len(self.models) > model["banner_slots"]:
                raise InputError(
                    "Defending hero count exceeds the selected Town Hall banner slots"
                )
            cells = {
                (x, y)
                for x in range(banner["x"], banner["x"] + banner["width"])
                for y in range(banner["y"], banner["y"] + banner["height"])
            }
            if any(
                not (0 <= x < self.width and 0 <= y < self.height) for x, y in cells
            ):
                raise InputError("Hero banner extends outside the board")
            if cells & occupied_banners:
                raise InputError("Defending hero banners cannot overlap")
            occupied_banners |= cells
            for other in actors.values():
                if other["blocking"]:
                    other_cells = {
                        (x, y)
                        for x in range(other["x"], other["x"] + other["width"])
                        for y in range(other["y"], other["y"] + other["height"])
                    }
                    if cells & other_cells:
                        raise InputError(
                            "A defending hero banner cannot overlap a blocking structure"
                        )
            anchor = _anchor(model)
            for waypoint in model["parameters"]["patrol"]["waypoints"]:
                point = waypoint["x"], waypoint["y"]
                if (
                    not (0 <= point[0] < self.width and 0 <= point[1] < self.height)
                    or _distance(point, anchor)
                    >= model["parameters"]["leash"]["radius_tiles"] - EPSILON
                ):
                    raise InputError(
                        "Defending patrol waypoints must stay inside the board and leash"
                    )
                if (
                    actors[actor_id]["movement"] == "ground"
                    and (floor(point[0]), floor(point[1])) in blocking_cells
                ):
                    raise InputError(
                        "Ground patrol waypoint occupies a blocking structure"
                    )
            self.states[actor_id] = {
                "phase": "guarding",
                "primary": None,
                "waypoint_index": 0,
                "wait_until": None,
                "route_arrival": None,
                "next_heal": None,
                "last_combat": 0,
                "received_damage": 0,
                "retaliation_pending": False,
                "healing_pulses": 0,
                "healing_total": 0,
            }

    def _transition(self, actor, state, phase, time):
        if state["phase"] == phase:
            return
        previous = state["phase"]
        state["phase"] = phase
        if self.trace is not None:
            self.trace.append(
                {
                    "time_seconds": time,
                    "event": "defending_hero_phase",
                    "source": actor["id"],
                    "from": previous,
                    "to": phase,
                }
            )

    def prepare(self, actors, time, trace):
        self.trace = trace
        self.blocked = _blocked(actors, time)
        for actor_id, model in self.models.items():
            actor = actors[actor_id]
            state = self.states[actor_id]
            received = actor.get("_received_damage", 0)
            if received > state["received_damage"] + EPSILON:
                state["retaliation_pending"] = True
                state["last_combat"] = time
            state["received_damage"] = received
            if not _active(actor, time):
                self._transition(actor, state, "dead", time)
                state.update(
                    primary=None, route_arrival=None, next_heal=None, wait_until=None
                )
                actor["target"] = None
            elif (
                state["phase"] == "recovering"
                and actor["hp"] >= actor["maximum_hp"] - EPSILON
            ):
                state["next_heal"] = None
                self._transition(actor, state, "guarding", time)

    def _bounded_blocks(self, actor, model, blocked, width, height):
        anchor = _anchor(model)
        radius = model["parameters"]["leash"]["radius_tiles"]
        outside = {
            (x, y)
            for x in range(width)
            for y in range(height)
            if _distance((x + 0.5, y + 0.5), anchor) >= radius - EPSILON
        }
        outside.discard((floor(actor["x"]), floor(actor["y"])))
        return blocked | outside

    @staticmethod
    def _save_route(actor, key, route):
        actor["_defender_path_key"] = key
        actor["_remaining_path"] = list(route) if route is not None else []
        return route

    @staticmethod
    def _continuation(actor, solid):
        """Finish the current grid segment when a moving target forces a replan."""
        remaining = actor.get("_remaining_path", [])
        if actor.get("_defender_path_key") is not None and remaining:
            point = remaining[0]
            if (floor(point[0]), floor(point[1])) not in solid:
                if _distance(center(actor), point) > EPSILON:
                    return {**actor, "x": point[0], "y": point[1]}, [point]
        return actor, []

    def _combat_route(
        self, actor, target, model, blocked, width, height, remember=False
    ):
        if target_distance(center(actor), target) <= actor["range"] + EPSILON:
            if remember:
                self._save_route(actor, None, [])
            return []
        if model["statue"]:
            return []
        if actor["movement"] == "air":
            first, second = center(actor), center(target)
            distance = _distance(first, second)
            fraction = max(distance - actor["range"], 0) / distance
            return [
                (
                    first[0] + (second[0] - first[0]) * fraction,
                    first[1] + (second[1] - first[1]) * fraction,
                )
            ]
        solid = self._bounded_blocks(actor, model, blocked, width, height)
        key = ("combat", target["id"], actor["range"], frozenset(solid))
        remaining = actor.get("_remaining_path", [])
        if (
            actor.get("_defender_path_key") == key
            and remaining
            and target_distance(remaining[-1], target) <= actor["range"] + EPSILON
        ):
            return list(remaining)
        planning_actor, prefix = self._continuation(actor, solid)
        probe = {**planning_actor, "_terminal_ground_approach": False}
        route = _ground_route(
            probe,
            target,
            solid,
            width,
            height,
        )
        if route is not None:
            route = prefix + route
        return self._save_route(actor, key, route) if remember else route

    def _point_route(self, actor, goal, model, blocked, width, height):
        if _distance(center(actor), goal) <= EPSILON:
            return []
        if actor["movement"] == "air":
            return [goal]
        solid = self._bounded_blocks(actor, model, blocked, width, height)
        key = ("point", goal, frozenset(solid))
        if actor.get("_defender_path_key") == key:
            return list(actor["_remaining_path"])
        planning_actor, prefix = self._continuation(actor, solid)
        start = floor(planning_actor["x"]), floor(planning_actor["y"])
        destination = floor(goal[0]), floor(goal[1])
        if destination in solid:
            return None
        pending = deque([start])
        previous = {start: None}
        while pending:
            point = pending.popleft()
            if point == destination:
                break
            x, y = point
            for neighbor in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y)):
                if (
                    0 <= neighbor[0] < width
                    and 0 <= neighbor[1] < height
                    and neighbor not in solid
                    and neighbor not in previous
                ):
                    previous[neighbor] = point
                    pending.append(neighbor)
        if destination not in previous:
            return None
        cells = []
        cursor = destination
        while cursor != start:
            cells.append((cursor[0] + 0.5, cursor[1] + 0.5))
            cursor = previous[cursor]
        route = list(reversed(cells))
        if start != destination:
            start_center = start[0] + 0.5, start[1] + 0.5
            if _distance(center(planning_actor), start_center) > EPSILON:
                route.insert(0, start_center)
        if not route or _distance(route[-1], goal) > EPSILON:
            route.append(goal)
        return self._save_route(actor, key, prefix + route)

    def _remember_arrival(self, actor, state, route, time):
        state["route_arrival"] = None
        if route and actor["frozen_until"] <= time + EPSILON:
            state["route_arrival"] = time + _route_length(
                actor, route
            ) / movement_speed(actor)
        return route

    def _eligible_primary(self, actor, target, model, time):
        return (
            target is not None
            and _eligible(actor, target, time)
            and _distance(_anchor(model), center(target))
            < model["parameters"]["leash"]["radius_tiles"] - EPSILON
        )

    def _acquire(self, actor, actors, model, state, time, blocked, width, height):
        radius = (
            model["parameters"]["leash"]["radius_tiles"]
            if state["retaliation_pending"]
            else model["aggro_radius"]
        )
        choices = []
        for target in actors.values():
            if (
                not self._eligible_primary(actor, target, model, time)
                or _distance(_anchor(model), center(target)) > radius + EPSILON
            ):
                continue
            route = self._combat_route(actor, target, model, blocked, width, height)
            if route is not None:
                choices.append(
                    (
                        target_distance(center(actor), target),
                        target["id"],
                        target,
                        route,
                    )
                )
        state["retaliation_pending"] = False
        if not choices:
            return None, None
        _, _, target, route = min(choices, key=lambda choice: choice[:2])
        route = self._combat_route(
            actor, target, model, blocked, width, height, remember=True
        )
        state.update(primary=target["id"], next_heal=None, wait_until=None)
        actor["target"] = target["id"]
        self._transition(actor, state, "engaged", time)
        if self.trace is not None:
            self.trace.append(
                {
                    "time_seconds": time,
                    "event": "defending_hero_acquired",
                    "source": actor["id"],
                    "target": target["id"],
                }
            )
        return target, self._remember_arrival(actor, state, route, time)

    def _home_idle(self, actor, model, state, time, blocked, width, height):
        healing = model["parameters"]["healing"]
        if (
            actor["hp"] < actor["maximum_hp"] - EPSILON
            and healing["amount_per_pulse"] > 0
            and _distance(center(actor), _anchor(model)) <= EPSILON
        ):
            if state["next_heal"] is None:
                state["next_heal"] = (
                    max(
                        time,
                        state["last_combat"] + healing["delay_after_combat_seconds"],
                    )
                    + healing["interval_seconds"]
                )
            self._transition(actor, state, "recovering", time)
            return None, []
        waypoints = model["parameters"]["patrol"]["waypoints"]
        if not waypoints or model["statue"]:
            self._transition(actor, state, "guarding", time)
            return None, []
        for _ in range(len(waypoints) + 1):
            waypoint = waypoints[state["waypoint_index"]]
            goal = waypoint["x"], waypoint["y"]
            if _distance(center(actor), goal) > EPSILON:
                route = self._point_route(actor, goal, model, blocked, width, height)
                self._transition(actor, state, "patrolling", time)
                return None, self._remember_arrival(actor, state, route, time)
            if state["wait_until"] is None:
                state["wait_until"] = time + waypoint["wait_seconds"]
            if state["wait_until"] > time + EPSILON:
                state["route_arrival"] = None
                self._transition(actor, state, "patrol_wait", time)
                return None, []
            state["waypoint_index"] = (state["waypoint_index"] + 1) % len(waypoints)
            state["wait_until"] = None
        return None, []

    def select_target(self, actor, actors, time, blocked, width, height):
        actor_id = actor["id"]
        if actor_id not in self.models:
            return self.ordinary_select_target(
                actor, actors, time, blocked, width, height
            )
        model = self.models[actor_id]
        state = self.states[actor_id]
        if not _active(actor, time):
            return None, None
        state["route_arrival"] = None
        if state["phase"] == "engaged":
            target = actors.get(state["primary"])
            route = (
                self._combat_route(
                    actor, target, model, blocked, width, height, remember=True
                )
                if self._eligible_primary(actor, target, model, time)
                else None
            )
            if route is not None:
                actor["target"] = target["id"]
                return target, self._remember_arrival(actor, state, route, time)
            state.update(primary=None, last_combat=time, wait_until=None)
            actor["target"] = None
            self._transition(actor, state, "returning", time)
        if state["phase"] == "returning":
            home = _anchor(model)
            if _distance(center(actor), home) > EPSILON:
                route = self._point_route(actor, home, model, blocked, width, height)
                return None, self._remember_arrival(actor, state, route, time)
            self._transition(actor, state, "guarding", time)
        target, route = self._acquire(
            actor, actors, model, state, time, blocked, width, height
        )
        if target is not None:
            return target, route
        actor["target"] = None
        if (
            actor["hp"] < actor["maximum_hp"] - EPSILON
            and model["parameters"]["healing"]["amount_per_pulse"] > 0
            and _distance(center(actor), _anchor(model)) > EPSILON
        ):
            self._transition(actor, state, "returning", time)
            route = self._point_route(
                actor, _anchor(model), model, blocked, width, height
            )
            return None, self._remember_arrival(actor, state, route, time)
        return self._home_idle(actor, model, state, time, blocked, width, height)

    def resolve_healing(self, actors, time, trace):
        healing = defaultdict(float)
        for actor_id, model in self.models.items():
            actor = actors[actor_id]
            state = self.states[actor_id]
            if (
                not _active(actor, time)
                or state["phase"] != "recovering"
                or state["next_heal"] is None
                or state["next_heal"] > time + EPSILON
            ):
                continue
            settings = model["parameters"]["healing"]
            state["next_heal"] = time + settings["interval_seconds"]
            if actor["frozen_until"] > time + EPSILON:
                continue
            amount = min(
                settings["amount_per_pulse"], max(actor["maximum_hp"] - actor["hp"], 0)
            )
            healing[actor_id] += amount
            state["healing_pulses"] += 1
            state["healing_total"] += amount
            trace.append(
                {
                    "time_seconds": time,
                    "event": "defending_hero_heal",
                    "source": actor_id,
                    "target": actor_id,
                    "amount": amount,
                }
            )
        return healing

    def next_boundary(self, time):
        pending = [
            state[field]
            for state in self.states.values()
            for field in ("wait_until", "route_arrival", "next_heal")
            if state[field] is not None and state[field] > time + EPSILON
        ]
        return min(pending) if pending else None

    def _reachable_firing_points(self, defender, model):
        """Cache the same connected cell centers used by ground combat routing."""
        solid = self._bounded_blocks(
            defender, model, self.blocked, self.width, self.height
        )
        start = floor(defender["x"]), floor(defender["y"])
        signature = start, frozenset(solid)
        cached = self.reachable_cells.get(defender["id"])
        if cached is not None and cached[0] == signature:
            return cached[1]
        pending = deque([start])
        visited = {start}
        while pending:
            x, y = pending.popleft()
            for neighbor in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y)):
                nx, ny = neighbor
                if (
                    0 <= nx < self.width
                    and 0 <= ny < self.height
                    and neighbor not in solid
                    and neighbor not in visited
                ):
                    visited.add(neighbor)
                    pending.append(neighbor)
        points = [(x + 0.5, y + 0.5) for x, y in sorted(visited)]
        self.reachable_cells[defender["id"]] = signature, points
        return points

    def _reachability_crossing_delay(
        self, defender, target, model, route, speed, horizon
    ):
        """Wake when a moving unit first becomes reachable behind an obstacle.

        Entering the banner's search circle is insufficient when every possible
        firing cell is out of range. With the declared cell-center path rule,
        reachability changes at the union of attack circles around connected
        cells. Moving actors have zero footprint under the spatial contract.
        """
        if (
            defender["movement"] != "ground"
            or _distance(center(target), _anchor(model))
            > model["aggro_radius"] + EPSILON
        ):
            return None
        points = [center(defender), *self._reachable_firing_points(defender, model)]
        radius = defender["range"]
        position = center(target)
        if any(_distance(position, point) <= radius + EPSILON for point in points):
            return None
        travel_limit = speed * horizon
        candidates = [
            point
            for point in points
            if _distance(position, point) <= radius + travel_limit + EPSILON
        ]
        earliest = None
        previous = position
        travelled = 0.0
        for waypoint in route:
            segment = _distance(previous, waypoint)
            for point in candidates:
                crossing = segment_circle_entry(previous, waypoint, point, radius)
                if crossing is None:
                    continue
                delay = (travelled + crossing) / speed
                if EPSILON < delay <= horizon + EPSILON:
                    earliest = delay if earliest is None else min(earliest, delay)
            travelled += segment
            if travelled >= travel_limit - EPSILON:
                break
            previous = waypoint
        return earliest

    def first_crossing_delay(
        self,
        actor,
        route,
        time,
        horizon,
        effective_speed=None,
        forced_motion=False,
    ):
        speed = (
            movement_speed(actor)
            if effective_speed is None
            else number(effective_speed, "defender trigger motion speed", 0)
        )
        if speed <= EPSILON or (
            actor["frozen_until"] > time + EPSILON and not forced_motion
        ):
            return None
        earliest = None
        for defender_id, model in self.models.items():
            defender = self.actors[defender_id]
            state = self.states[defender_id]
            if not _active(defender, time) or not _eligible(defender, actor, time):
                continue
            leaving = state["phase"] == "engaged" and state["primary"] == actor["id"]
            if state["phase"] in {"engaged", "returning"} and not leaving:
                continue
            if not leaving:
                reachable = self._reachability_crossing_delay(
                    defender, actor, model, route, speed, horizon
                )
                if reachable is not None:
                    earliest = (
                        reachable if earliest is None else min(earliest, reachable)
                    )
            radius = (
                model["parameters"]["leash"]["radius_tiles"]
                if leaving
                else model["aggro_radius"]
            )
            previous = center(actor)
            travelled = 0.0
            for point in route:
                segment = _distance(previous, point)
                if leaving:
                    reverse = segment_circle_entry(
                        point, previous, _anchor(model), radius
                    )
                    crossing = (
                        segment - reverse
                        if reverse is not None
                        and _distance(point, _anchor(model)) >= radius - EPSILON
                        else None
                    )
                else:
                    crossing = segment_circle_entry(
                        previous, point, _anchor(model), radius
                    )
                if crossing is not None:
                    delay = (travelled + crossing) / speed
                    if EPSILON < delay <= horizon + EPSILON:
                        earliest = delay if earliest is None else min(earliest, delay)
                        break
                travelled += segment
                if travelled > speed * horizon:
                    break
                previous = point
        return earliest

    def frame(self, actor):
        if actor["id"] not in self.states:
            return {}
        state = self.states[actor["id"]]
        return {
            "defending_hero_phase": state["phase"],
            "defending_hero_primary": state["primary"],
            "defending_hero_banner": self.models[actor["id"]]["banner"]["id"],
        }

    def result(self):
        return {
            "states": deepcopy(self.states),
            "banners": {
                actor_id: deepcopy(model["banner"])
                for actor_id, model in self.models.items()
            },
            "full_game_prediction": False,
        }
