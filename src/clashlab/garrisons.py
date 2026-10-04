"""Conditional defending Clan Castle troops with explicit release hypotheses.

The catalog supplies capacity and troop statistics. It does not establish the
release order, clock, spawn geometry or defending targeting behavior. Those
choices remain declared inputs and are never advertised as replay calibrated.
"""

from copy import deepcopy
from math import floor, hypot

from .common import InputError, identifier, integer, number, require
from .defending_heroes import validate_defending_unit_responses
from .rates import movement_speed
from .spatial import EPSILON, _active, _eligible, center
from .traps import segment_circle_entry


GARRISON_MEMBERS = {
    "barbarian": ("ground", "single"),
    "archer": ("ground", "single"),
    "pekka": ("ground", "single"),
    "minion": ("air", "single"),
    "thrower": ("ground", "single"),
    "wizard": ("ground", "radial"),
    "dragon": ("air", "radial"),
    "electro-dragon": ("air", "chain"),
    "dragon-rider": ("air", "single"),
    "ice-golem": ("ground", "single"),
    "giant": ("ground", "single"),
    "hog-rider": ("ground", "single"),
}
SHARED_GARRISON_MEMBERS = frozenset(
    {"electro-dragon", "dragon-rider", "ice-golem", "giant", "hog-rider"}
)
GARRISON_RULES = {
    "garrison_statistics": "snapshot_troop_statistics_without_attacking_equipment_or_special_abilities",
    "garrison_capacity": "snapshot_troop_capacity_and_explicit_donor_receiver_level_validation",
    "garrison_trigger": "eligible_visible_hostile_unit_center_inside_scaled_snapshot_radius",
    "garrison_release": "declared_order_among_currently_eligible_members_with_explicit_delays",
    "garrison_freeze": "pause_remaining_shared_castle_release_clock",
    "garrison_positions": "explicit_exterior_points_clear_of_initial_blocking_footprints",
    "garrison_targeting": "retained_hostile_units_with_shared_route_scoring_and_no_leash",
    "garrison_castle_death": "cancel_unreleased_members_keep_released_members_and_projectiles",
    "garrison_destruction": "only_the_castle_counts_members_are_excluded",
}
CASTLE_PARAMETERS = {
    "source",
    "member_ids",
    "capacity_basis",
    "trigger_radius_multiplier",
    "trigger_layers",
    "release",
    "castle_death",
    "released_targeting",
    "released_idle",
    "death",
}
MEMBER_PARAMETERS = {"source", "castle_id", "donor_town_hall", "level_basis"}


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise InputError(f"{label} requires its complete explicit parameters")


def _validate_castle_parameters(parameters):
    _fields(parameters, CASTLE_PARAMETERS, "Garrison")
    identifier(parameters["source"], "garrison evidence")
    policies = {
        "capacity_basis": "snapshot_troopCapacity",
        "castle_death": "cancel_unreleased_keep_released",
        "released_targeting": "nearest_retained_hostile_units_anywhere",
        "released_idle": "hold_position",
        "death": "permanent_for_battle",
    }
    for field, expected in policies.items():
        if parameters[field] != expected:
            raise InputError(f"Unsupported garrison {field}")
    members = parameters["member_ids"]
    if not isinstance(members, list) or len(members) != len(set(members)):
        raise InputError("Garrison needs an ordered list of unique member IDs")
    for member_id in members:
        identifier(member_id, "garrison member ID")
    number(parameters["trigger_radius_multiplier"], "garrison trigger scale", EPSILON)
    layers = parameters["trigger_layers"]
    if (
        not isinstance(layers, list)
        or not layers
        or len(layers) != len(set(layers))
        or not set(layers) <= {"ground", "air"}
    ):
        raise InputError("Garrison trigger layers must be explicit and unique")
    release = parameters["release"]
    _fields(
        release,
        {
            "initial_delay_seconds",
            "interval_seconds",
            "order",
            "trigger_loss",
            "freeze",
            "positions",
            "position_policy",
        },
        "Garrison release",
    )
    number(release["initial_delay_seconds"], "garrison initial delay", 0)
    number(release["interval_seconds"], "garrison release interval", EPSILON)
    if (
        release["order"] != "declared_order_among_eligible_members"
        or release["trigger_loss"] != "hold_until_current_eligible_enemy"
        or release["freeze"] != "pause_remaining_shared_release_clock"
        or release["position_policy"] != "explicit_exterior_points"
    ):
        raise InputError("Unsupported garrison release hypothesis")
    positions = release["positions"]
    if not isinstance(positions, dict) or set(positions) != set(members):
        raise InputError("Garrison needs one explicit exterior point per member")
    for point in positions.values():
        _fields(point, {"x", "y"}, "Garrison release point")
        for axis in ("x", "y"):
            number(point[axis], "garrison release coordinate", 0)


def _validate_member_parameters(parameters, maximum_town_hall):
    _fields(parameters, MEMBER_PARAMETERS, "Garrison member")
    identifier(parameters["source"], "garrison member evidence")
    identifier(parameters["castle_id"], "garrison castle ID")
    integer(parameters["donor_town_hall"], "donor Town Hall", 1, maximum_town_hall)
    if parameters["level_basis"] != "snapshot_receiver_lab_cap_with_unlock_floor":
        raise InputError(
            "Garrison received level needs the explicit laboratory mapping"
        )


def _receiver_lab_requirement(entity_id, row, catalog):
    """Make level-one zero-lab rows respect their snapshot initial unlock.

    This conservative mapping is a named hypothesis, not a claim about donation
    server rules. A missing unlock/laboratory relation fails closed.
    """
    entity = catalog.entity(entity_id)
    source_row = row
    first_level = 1
    if entity.get("troopType") == "super":
        # Super rows name their parent level and omit duplicated research data.
        # Use that exact parent's row, as the existing planning cap already does.
        source_row = catalog.level(require(entity, "parentTroop"), row["level"])
        first_level = min(
            item["level"]
            for item in entity["levels"]
            if not item.get("supercharge", False)
        )
    research_lab = integer(
        require(source_row, "laboratoryRequired"), "troop research laboratory", 0
    )
    initial_town_hall = catalog.town_hall_requirement(entity_id, first_level)
    laboratories = [
        level["level"]
        for level in catalog.entity("laboratory")["levels"]
        if not level.get("supercharge", False)
        and require(level, "townHallRequired") <= initial_town_hall
    ]
    return max(research_lab, max(laboratories, default=0))


def compile_garrison_castle(actor, instance, entity, row, modifiers):
    """Compile the counted castle; members are separately compiled reserves."""
    if (
        entity["id"] != "clan-castle"
        or actor["team"] != "defense"
        or actor["spawn_seconds"] != 0
        or actor["first_attack_seconds"] != 0
        or not actor["counts_for_destruction"]
        or instance["mode"] != "garrison"
        or instance["statistics_mode"] != "none"
        or require(instance, "attack_parameters") != {}
        or "wall_parameters" in instance
    ):
        raise InputError(
            "A garrison needs an initially active, counted, passive castle"
        )
    parameters = require(instance, "garrison_parameters")
    _validate_castle_parameters(parameters)
    width, height = (int(part) for part in entity["size"].split("x"))
    actor.update(
        kind="building",
        layer="ground",
        movement="stationary",
        speed=0,
        damage=0,
        range=0,
        attack_interval_seconds=parameters["release"]["interval_seconds"],
        blocking=True,
        width=width,
        height=height,
        target_priorities=[],
        target_layers=[],
        attack_model={"kind": "none", "source": parameters["source"]},
        garrison_model={
            "entity": "clan-castle",
            "capacity": integer(require(row, "troopCapacity"), "garrison capacity", 0),
            "laboratory_cap": integer(
                require(row, "labLevelCap"), "receiver lab cap", 0
            ),
            "trigger_radius": number(
                require(entity, "triggerRadius"), "castle radius", EPSILON
            )
            * parameters["trigger_radius_multiplier"],
            "town_hall": instance["town_hall"],
            "parameters": deepcopy(parameters),
        },
    )
    actor["entity_adapter"].update(
        garrison_parameters=deepcopy(parameters),
        behavior_verification="explicit_garrison_hypotheses_not_replay_validated",
    )
    return actor


def compile_garrison_member(
    actor, instance, entity, row, modifiers, catalog, movement_units_per_tile
):
    """Compile a defender independently of the attacking-troop role adapter."""
    from .combat import validate_pattern
    from .splash import LAYER_POLICIES

    entity_id = entity["id"]
    if entity_id not in GARRISON_MEMBERS or entity["category"] != "troop":
        raise InputError(
            "This garrison troop needs an entity-specific defending adapter"
        )
    if (
        actor["team"] != "defense"
        or actor["spawn_seconds"] != "controlled"
        or actor["counts_for_destruction"]
        or instance["mode"] != "normal"
        or instance["statistics_mode"] != "normal"
        or any(
            key in instance
            for key in (
                "hero_parameters",
                "defending_hero_parameters",
                "equipment",
                "pet",
            )
        )
    ):
        raise InputError(
            "Garrison members require non-counted controlled defensive reserves"
        )
    parameters = require(instance, "garrison_member_parameters")
    _validate_member_parameters(parameters, catalog.maximum_town_hall)
    if not catalog.available(
        entity_id, instance["level"], parameters["donor_town_hall"]
    ):
        raise InputError("Garrison member level is unavailable to its declared donor")
    if entity_id in SHARED_GARRISON_MEMBERS:
        from .defending_troop_roles import compile_shared_garrison_member

        return compile_shared_garrison_member(
            actor, instance, entity, row, catalog, movement_units_per_tile
        )
    movement, pattern_kind = GARRISON_MEMBERS[entity_id]
    expected_damage_type = "splash" if pattern_kind == "radial" else "single"
    if entity["damageType"] != expected_damage_type or entity["targetType"] not in {
        "ground",
        "both",
    }:
        raise InputError("Snapshot garrison weapon requires another adapter")
    layers = ["ground", "air"] if entity["targetType"] == "both" else ["ground"]
    attack = require(instance, "attack_parameters")
    fields = (
        {"projectile", "radius", "splash_layer_policy"}
        if pattern_kind == "radial"
        else {"projectile"}
    )
    _fields(attack, fields, "Garrison weapon")
    pattern = {
        "kind": pattern_kind,
        "source": actor["source"],
        "target_kinds": ["unit"],
        "target_layers": list(layers),
        "maximum_hp_fraction": 0,
        "projectile": deepcopy(attack["projectile"]),
    }
    if pattern_kind == "radial":
        pattern["radius"] = number(attack["radius"], "garrison splash radius", 0)
        if attack["splash_layer_policy"] not in LAYER_POLICIES:
            raise InputError("Garrison splash needs an explicit supported layer policy")
        pattern["splash_layer_policy"] = attack["splash_layer_policy"]
        require(pattern["projectile"], "inactive_primary_policy")
    validate_pattern(pattern)
    if movement == "ground":
        wall = require(instance, "wall_parameters")
        _fields(wall, {"kind", "source"}, "Garrison ground walls")
        if wall["kind"] != "avoid":
            raise InputError(
                "Garrison ground movement explicitly avoids all blocking walls"
            )
        identifier(wall["source"], "garrison wall evidence")
        actor["wall_behavior"] = deepcopy(wall)
    elif "wall_parameters" in instance:
        raise InputError("Flying garrison members cannot select ground wall behavior")
    housing = integer(require(entity, "housingSpace"), "garrison housing", 1)
    actor.update(
        kind="unit",
        layer=movement,
        movement=movement,
        speed=number(require(entity, "movementSpeed"), "garrison movement", EPSILON)
        / movement_units_per_tile
        * modifiers["movement_speed_multiplier"],
        damage=number(
            require(require(row, "stats")["normal"], "damagePerShot"),
            "garrison hit",
            EPSILON,
        )
        * modifiers["damage_multiplier"],
        attack_interval_seconds=number(
            require(entity, "attackSpeed"), "garrison cadence", EPSILON
        )
        * modifiers["attack_interval_multiplier"],
        range=number(require(entity, "range"), "garrison range", EPSILON)
        * modifiers["range_multiplier"],
        blocking=False,
        width=0,
        height=0,
        target_priorities=["unit"],
        target_priority_tiers=[["unit"]],
        target_layers=layers,
        healing_class="troop",
        hazard_class="troop",
        spring_class="troop",
        housing_space=housing,
        attack_model=pattern,
        garrison_member_model={
            "entity": entity_id,
            "level": instance["level"],
            "town_hall": instance["town_hall"],
            "housing_space": housing,
            "laboratory_required": _receiver_lab_requirement(entity_id, row, catalog),
            "parameters": deepcopy(parameters),
        },
    )
    actor["entity_adapter"].update(
        garrison_member_parameters=deepcopy(parameters),
        behavior_verification="explicit_defending_garrison_hypotheses_not_replay_validated",
    )
    return actor


def validate_garrison_deployment(effect, actors):
    """Call for scheduled and controller commands before external deployments."""
    if effect.get("kind") == "deploy" and any(
        "garrison_member_model" in actors.get(actor_id, {})
        for actor_id in effect.get("targets", [])
    ):
        raise InputError(
            "Garrison reserves can only be released by their linked castle"
        )


class GarrisonCombat:
    """Castle release scheduler; released units use the shared pursuit solver."""

    def __init__(self, actors, select_target, specification):
        self.actors = actors
        self.ordinary_select_target = select_target
        self.models = {}
        self.members = {}
        self.states = {}
        self.member_states = {}
        width, height = specification["width"], specification["height"]
        for actor_id, actor in actors.items():
            if "garrison_model" in actor:
                model = deepcopy(actor["garrison_model"])
                _fields(
                    model,
                    {
                        "entity",
                        "capacity",
                        "laboratory_cap",
                        "trigger_radius",
                        "town_hall",
                        "parameters",
                    },
                    "Garrison runtime model",
                )
                _validate_castle_parameters(model["parameters"])
                for field in ("capacity", "laboratory_cap"):
                    integer(model[field], field, 0)
                integer(model["town_hall"], "receiver Town Hall", 1)
                number(model["trigger_radius"], "runtime castle radius", EPSILON)
                if (
                    model["entity"] != "clan-castle"
                    or actor["team"] != "defense"
                    or actor["kind"] != "building"
                    or actor["movement"] != "stationary"
                    or actor["spawn_seconds"] != 0
                    or not actor["counts_for_destruction"]
                    or not actor["blocking"]
                    or actor["damage"] != 0
                    or actor["attack_model"]["kind"] != "none"
                    or actor["target_priorities"]
                    or actor["first_attack_seconds"] != 0
                ):
                    raise InputError("Invalid runtime garrison castle role")
                self.models[actor_id] = model
                self.states[actor_id] = {
                    "phase": (
                        "dormant" if model["parameters"]["member_ids"] else "empty"
                    ),
                    "triggered_at": None,
                    "remaining": list(model["parameters"]["member_ids"]),
                    "released": [],
                    "cancelled": [],
                }
            if "garrison_member_model" in actor:
                model = deepcopy(actor["garrison_member_model"])
                _fields(
                    model,
                    {
                        "entity",
                        "level",
                        "town_hall",
                        "housing_space",
                        "laboratory_required",
                        "parameters",
                    },
                    "Garrison member runtime model",
                )
                _validate_member_parameters(model["parameters"], 18)
                if model["entity"] not in GARRISON_MEMBERS:
                    raise InputError("Unsupported runtime garrison member")
                for field in ("level", "town_hall", "housing_space"):
                    integer(model[field], field, 1)
                integer(model["laboratory_required"], "received laboratory", 0)
                movement, pattern_kind = GARRISON_MEMBERS[model["entity"]]
                layers = (
                    ["ground"]
                    if model["entity"]
                    in {"barbarian", "pekka", "ice-golem", "giant", "hog-rider"}
                    else ["ground", "air"]
                )
                if model["entity"] == "dragon-rider":
                    layers = actor["target_layers"]
                    if layers not in (["ground"], ["ground", "air"]):
                        raise InputError(
                            "Unsupported defending Dragon Rider layer policy"
                        )
                if (
                    actor["team"] != "defense"
                    or actor["kind"] != "unit"
                    or actor["movement"] != movement
                    or actor["layer"] != movement
                    or actor["counts_for_destruction"]
                    or actor["spawn_seconds"] != "controlled"
                    or actor["target_priorities"] != ["unit"]
                    or actor["target_layers"] != layers
                    or actor["attack_model"]["kind"] != pattern_kind
                    or actor["attack_model"]["target_kinds"] != ["unit"]
                    or actor["attack_model"]["target_layers"] != layers
                    or actor.get("housing_space") != model["housing_space"]
                    or (
                        movement == "ground"
                        and actor.get("wall_behavior", {}).get("kind")
                        != (
                            "jump_enemy_walls"
                            if model["entity"] == "hog-rider"
                            else "avoid"
                        )
                    )
                ):
                    raise InputError("Invalid runtime garrison member role or weapon")
                self.members[actor_id] = model
                self.member_states[actor_id] = {"phase": "reserve", "released_at": None}
        if self.models or self.members:
            validate_defending_unit_responses(actors, specification)
        claimed = set()
        blocking_cells = {
            (x, y)
            for actor in actors.values()
            if actor["blocking"]
            for x in range(actor["x"], actor["x"] + actor["width"])
            for y in range(actor["y"], actor["y"] + actor["height"])
        }
        for castle_id, model in self.models.items():
            members = model["parameters"]["member_ids"]
            if claimed & set(members) or not set(members) <= set(self.members):
                raise InputError(
                    "Each declared garrison member must exist in exactly one castle"
                )
            claimed.update(members)
            housing = 0
            for member_id in members:
                member = self.members[member_id]
                if (
                    member["parameters"]["castle_id"] != castle_id
                    or member["town_hall"] != model["town_hall"]
                    or member["laboratory_required"] > model["laboratory_cap"]
                ):
                    raise InputError(
                        "Garrison member linkage or receiver laboratory cap is invalid"
                    )
                housing += member["housing_space"]
                point = model["parameters"]["release"]["positions"][member_id]
                if (
                    not (0 <= point["x"] < width and 0 <= point["y"] < height)
                    or (floor(point["x"]), floor(point["y"])) in blocking_cells
                    or (actors[member_id]["x"], actors[member_id]["y"])
                    != (point["x"], point["y"])
                ):
                    raise InputError(
                        "Garrison reserve must start at its clear exterior release point"
                    )
            if housing > model["capacity"]:
                raise InputError("Garrison contents exceed snapshot troop capacity")
        if claimed != set(self.members):
            raise InputError("Every garrison member needs a declared existing castle")
        for effect in specification.get("effects", []):
            validate_garrison_deployment(effect, actors)

    def _trigger(self, castle_id, member_id, time):
        castle = self.actors[castle_id]
        member = self.actors[member_id]
        model = self.models[castle_id]
        origin = center(castle)
        choices = []
        for target in self.actors.values():
            if (
                not _eligible(member, target, time)
                or target["layer"] not in model["parameters"]["trigger_layers"]
            ):
                continue
            distance = hypot(target["x"] - origin[0], target["y"] - origin[1])
            if distance <= model["trigger_radius"] + EPSILON:
                choices.append((distance, target["id"]))
        return min(choices)[1] if choices else None

    def prepare(self, actors, time, trace, allow_release=True):
        """Run before targeting; post-health calls pass allow_release=False."""
        for member_id, state in self.member_states.items():
            actor = actors[member_id]
            if (
                state["phase"] in {"reserve", "cancelled"}
                and actor["spawn_seconds"] != "controlled"
            ):
                raise InputError("Garrison reserve was externally deployed")
            if state["phase"] == "released" and not _active(actor, time):
                state["phase"] = "dead"
        for castle_id, model in self.models.items():
            castle = actors[castle_id]
            state = self.states[castle_id]
            if not _active(castle, time):
                for member_id in state["remaining"]:
                    self.member_states[member_id]["phase"] = "cancelled"
                if state["phase"] != "destroyed":
                    trace.append(
                        {
                            "time_seconds": time,
                            "event": "garrison_castle_destroyed",
                            "source": castle_id,
                            "cancelled": list(state["remaining"]),
                        }
                    )
                state["cancelled"].extend(state["remaining"])
                state["remaining"] = []
                state["phase"] = "destroyed"
                continue
            if not allow_release or not state["remaining"]:
                continue
            choice = None
            for member_id in state["remaining"]:
                trigger_id = self._trigger(castle_id, member_id, time)
                if trigger_id is not None:
                    choice = member_id, trigger_id
                    break
            if choice is None:
                continue
            release = model["parameters"]["release"]
            if state["triggered_at"] is None:
                state["triggered_at"] = time
                state["phase"] = "releasing"
                castle["next_attack"] = (
                    max(time, castle["frozen_until"]) + release["initial_delay_seconds"]
                )
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "garrison_triggered",
                        "source": castle_id,
                        "target": choice[1],
                    }
                )
            if (
                castle["frozen_until"] > time + EPSILON
                or castle["next_attack"] > time + EPSILON
            ):
                continue
            member_id, trigger_id = choice
            member = actors[member_id]
            point = release["positions"][member_id]
            member.update(spawn_seconds=time, x=point["x"], y=point["y"], target=None)
            member["next_attack"] = time + member["first_attack_seconds"]
            self.member_states[member_id].update(phase="released", released_at=time)
            state["remaining"].remove(member_id)
            state["released"].append(member_id)
            state["phase"] = "releasing" if state["remaining"] else "empty"
            castle["next_attack"] = time + release["interval_seconds"]
            trace.append(
                {
                    "time_seconds": time,
                    "event": "garrison_released",
                    "source": castle_id,
                    "member": member_id,
                    "trigger": trigger_id,
                    "x": member["x"],
                    "y": member["y"],
                }
            )

    def select_target(self, actor, actors, time, blocked, width, height):
        if (
            actor["id"] in self.members
            and self.member_states[actor["id"]]["phase"] != "released"
        ):
            return None, None
        return self.ordinary_select_target(actor, actors, time, blocked, width, height)

    def next_boundary(self, time):
        pending = [
            max(
                self.actors[castle_id]["next_attack"],
                self.actors[castle_id]["frozen_until"],
            )
            for castle_id, state in self.states.items()
            if state["phase"] == "releasing"
            and self.actors[castle_id]["next_attack"] > time + EPSILON
        ]
        return min(pending) if pending else None

    def first_crossing_delay(
        self, actor, route, time, horizon, effective_speed=None, forced_motion=False
    ):
        speed = (
            movement_speed(actor)
            if effective_speed is None
            else number(effective_speed, "garrison crossing speed", 0)
        )
        if speed <= EPSILON or (
            actor["frozen_until"] > time + EPSILON and not forced_motion
        ):
            return None
        earliest = None
        for castle_id, model in self.models.items():
            castle = self.actors[castle_id]
            state = self.states[castle_id]
            if (
                not _active(castle, time)
                or actor["layer"] not in model["parameters"]["trigger_layers"]
                or not any(
                    _eligible(self.actors[member_id], actor, time)
                    for member_id in state["remaining"]
                )
            ):
                continue
            previous = center(actor)
            travelled = 0.0
            for point in route:
                crossing = segment_circle_entry(
                    previous, point, center(castle), model["trigger_radius"]
                )
                if crossing is not None:
                    delay = (travelled + crossing) / speed
                    if EPSILON < delay <= horizon + EPSILON:
                        earliest = delay if earliest is None else min(earliest, delay)
                        break
                travelled += hypot(point[0] - previous[0], point[1] - previous[1])
                if travelled > speed * horizon:
                    break
                previous = point
        return earliest

    def frame(self, actor):
        actor_id = actor["id"]
        if actor_id in self.states:
            return {
                "garrison_phase": self.states[actor_id]["phase"],
                "garrison_remaining": len(self.states[actor_id]["remaining"]),
            }
        if actor_id in self.members:
            return {
                "garrison_member_phase": self.member_states[actor_id]["phase"],
                "garrison_castle": self.members[actor_id]["parameters"]["castle_id"],
            }
        return {}

    def result(self):
        return {
            "castles": deepcopy(self.states),
            "members": deepcopy(self.member_states),
            "full_game_prediction": False,
        }
