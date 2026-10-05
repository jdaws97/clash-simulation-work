"""Conditional TH18 Guardians with explicit emergence, routes and death effects.

The Hall is a weaponless building. Its single selected Guardian is a separate
defending unit and never a second destruction credit. Catalog quantities do not
establish emergence geometry, defensive AI or the Smasher's dropped rage field;
those remain required, named hypotheses rather than replay-calibrated behavior.
"""

from collections import deque
from copy import deepcopy
from math import floor, hypot

from .common import InputError, identifier, integer, number, require
from .defending_heroes import validate_defending_unit_responses
from .rates import movement_speed
from .spatial import EPSILON, _active, _eligible, _ground_route, _route_length, center
from .spatial import target_distance


GUARDIANS = {"longshot", "smasher", "logger"}
GUARDIAN_RULES = {
    "th18_hall": "weaponless_counted_building_with_exactly_one_selected_guardian",
    "guardian_role": "separate_defending_unit_excluded_from_destruction_and_hero_equipment",
    "guardian_activation": "hall_center_trigger_or_hall_death_then_explicit_latched_emergence_delay",
    "guardian_freeze": "dormant_hall_center_freeze_pauses_activation_clock_and_prevents_activation",
    "guardian_routes": "explicit_ordered_patrol_retained_primary_and_leash_avoiding_all_blocking_cells",
    "guardian_return": "explicit_exterior_home_point_no_reacquisition_until_arrival",
    "guardian_healing": "no_automatic_regeneration_or_resurrection",
    "longshot_death": "snapshot_damage_and_radius_with_explicit_delay_filters_and_scaling",
    "smasher_hall_rage": "snapshot_percent_damage_and_additive_movement_until_permanent_death",
    "smasher_death_rage": "explicit_fixed_field_quantities_recipients_and_multiplicative_damage_additive_movement",
    "guardian_verification": "conditional_hypotheses_not_full_game_or_replay_validated",
}
PARAMETERS = {
    "source",
    "hall_id",
    "statistics_mapping",
    "activation",
    "acquisition_radius_tiles",
    "leash_radius_tiles",
    "home",
    "patrol",
    "targeting",
    "return",
    "healing",
    "death",
}
RECIPIENT_CLASSES = {
    "defense",
    "building",
    "wall",
    "guardian",
    "defending_hero",
    "defending_troop",
}


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise InputError(f"{label} requires its complete explicit parameters")


def _values(values, allowed, label):
    if (
        not isinstance(values, list)
        or not values
        or len(values) != len(set(values))
        or not set(values) <= allowed
    ):
        raise InputError(f"{label} requires unique supported values")


def _point(value, label):
    _fields(value, {"x", "y"}, label)
    for axis in ("x", "y"):
        number(value[axis], label, 0)
    return value["x"], value["y"]


def _distance(first, second):
    return hypot(first[0] - second[0], first[1] - second[1])


def validate_binding(binding):
    """Absence is intentionally unsupported, including upgrade omission."""
    _fields(binding, {"source", "actor_id", "entity", "level"}, "TH18 Guardian binding")
    identifier(binding["source"], "Guardian binding evidence")
    identifier(binding["actor_id"], "Guardian actor ID")
    if binding["entity"] not in GUARDIANS:
        raise InputError("TH18 requires a selected supported Guardian")
    integer(binding["level"], "Guardian binding level", 1, 5)


def _validate_parameters(parameters):
    _fields(parameters, PARAMETERS, "Guardian")
    identifier(parameters["source"], "Guardian evidence")
    identifier(parameters["hall_id"], "Guardian Town Hall ID")
    policies = {
        "statistics_mapping": "snapshot_guardian_without_hero_equipment",
        "targeting": "nearest_reachable_retained_primary_or_received_damage_within_leash",
        "return": "home_before_reacquisition_preserve_attack_clock",
        "healing": "none",
        "death": "permanent_for_battle",
    }
    for field, expected in policies.items():
        if parameters[field] != expected:
            raise InputError(f"Unsupported Guardian {field}")
    activation = parameters["activation"]
    _fields(
        activation,
        {
            "trigger_radius_multiplier",
            "trigger_layers",
            "delay_seconds",
            "trigger_loss",
            "freeze",
            "hall_death",
        },
        "Guardian activation",
    )
    number(activation["trigger_radius_multiplier"], "Guardian trigger scale", EPSILON)
    number(activation["delay_seconds"], "Guardian emergence delay", 0)
    _values(activation["trigger_layers"], {"ground", "air"}, "Guardian trigger layers")
    if (
        activation["trigger_loss"] != "latched"
        or activation["freeze"] != "pause_activation_clock_at_hall_center"
        or activation["hall_death"] != "activate"
    ):
        raise InputError("Unsupported Guardian activation hypothesis")
    acquisition = number(
        parameters["acquisition_radius_tiles"], "Guardian acquisition radius", EPSILON
    )
    leash = number(parameters["leash_radius_tiles"], "Guardian leash radius", EPSILON)
    if leash <= acquisition:
        raise InputError("Guardian leash must exceed acquisition radius")
    _point(parameters["home"], "Guardian exterior home")
    patrol = parameters["patrol"]
    _fields(patrol, {"waypoints", "selection"}, "Guardian patrol")
    if patrol["selection"] != "ordered_loop" or not isinstance(
        patrol["waypoints"], list
    ):
        raise InputError("Guardian patrol requires explicit ordered waypoints")
    for waypoint in patrol["waypoints"]:
        _fields(waypoint, {"x", "y", "wait_seconds"}, "Guardian waypoint")
        _point({axis: waypoint[axis] for axis in ("x", "y")}, "Guardian waypoint")
        number(waypoint["wait_seconds"], "Guardian waypoint wait", 0)


def _validate_dropped_rage(parameters):
    _fields(
        parameters,
        {
            "source",
            "radius_tiles",
            "duration_seconds",
            "damage_multiplier",
            "movement_bonus_tiles_per_second",
            "target_kinds",
            "target_layers",
            "recipient_classes",
            "membership",
            "composition",
            "persistence",
        },
        "Smasher dropped rage",
    )
    identifier(parameters["source"], "Smasher dropped rage evidence")
    number(parameters["radius_tiles"], "dropped rage radius", EPSILON)
    number(parameters["duration_seconds"], "dropped rage duration", EPSILON)
    number(parameters["damage_multiplier"], "dropped rage damage multiplier", 1)
    number(
        parameters["movement_bonus_tiles_per_second"], "dropped rage movement bonus", 0
    )
    _values(
        parameters["target_kinds"],
        {"unit", "defense", "building", "wall"},
        "dropped rage kinds",
    )
    _values(parameters["target_layers"], {"ground", "air"}, "dropped rage layers")
    _values(
        parameters["recipient_classes"], RECIPIENT_CLASSES, "dropped rage recipients"
    )
    if (
        parameters["membership"] != "center_distance_continuous_no_linger"
        or parameters["composition"]
        != "multiply_damage_add_movement_with_other_sources"
        or parameters["persistence"] != "fixed_field_until_expiry_independent_of_hall"
    ):
        raise InputError("Unsupported Smasher dropped rage hypothesis")


def compile_th18_hall(actor, instance, entity, row, modifiers):
    if (
        entity["id"] != "town-hall"
        or instance["level"] != 18
        or row.get("weapon") is not None
        or instance["town_hall"] != 18
        or actor["team"] != "defense"
        or actor["spawn_seconds"] != 0
        or actor["first_attack_seconds"] != 0
        or not actor["counts_for_destruction"]
        or instance["mode"] != "guardian"
        or instance["statistics_mode"] != "none"
        or require(instance, "attack_parameters") != {}
        or any(
            key in instance
            for key in ("wall_parameters", "town_hall_parameters", "death_parameters")
        )
    ):
        raise InputError("TH18 must be an initially counted, weaponless Guardian Hall")
    binding = require(instance, "guardian_binding")
    validate_binding(binding)
    width, height = (int(part) for part in entity["size"].split("x"))
    actor.update(
        kind="building",
        layer="ground",
        movement="stationary",
        speed=0,
        damage=0,
        range=0,
        attack_interval_seconds=1,
        blocking=True,
        width=width,
        height=height,
        target_priorities=[],
        target_layers=[],
        attack_model={"kind": "none", "source": binding["source"]},
        guardian_hall_model={"binding": deepcopy(binding)},
    )
    actor["entity_adapter"].update(
        guardian_binding=deepcopy(binding),
        behavior_verification="weaponless_th18_with_explicit_guardian_binding",
    )
    return actor


def compile_guardian(actor, instance, entity, row, modifiers, movement_units_per_tile):
    from .combat import validate_pattern
    from .splash import LAYER_POLICIES

    entity_id = entity["id"]
    if entity_id not in GUARDIANS or entity["category"] != "guardian":
        raise InputError(
            "Guardian requires a supported entity adapter; Logger remains unavailable"
        )
    if (
        actor["team"] != "defense"
        or actor["spawn_seconds"] != "controlled"
        or actor["counts_for_destruction"]
        or instance["town_hall"] != 18
        or instance["mode"] != "normal"
        or instance["statistics_mode"] != "normal"
        or any(
            key in instance
            for key in (
                "hero_parameters",
                "defending_hero_parameters",
                "equipment",
                "pet",
                "garrison_member_parameters",
                "target_layer_policy",
                "readiness_policy",
            )
        )
    ):
        raise InputError(
            "Guardians require a controlled, uncounted TH18 defending role without hero equipment"
        )
    parameters = require(instance, "guardian_parameters")
    _validate_parameters(parameters)
    home = _point(parameters["home"], "Guardian exterior home")
    if (actor["x"], actor["y"]) != home:
        raise InputError(
            "Guardian reserve must start at its explicit exterior emergence point"
        )
    wall = require(instance, "wall_parameters")
    _fields(wall, {"kind", "source"}, "Guardian wall policy")
    if wall["kind"] != "avoid":
        raise InputError(
            "Conditional Guardian ground movement avoids all blocking cells"
        )
    identifier(wall["source"], "Guardian wall evidence")
    attack = require(instance, "attack_parameters")
    if entity_id == "logger":
        from .logger_guardian import compile_logger_weapon

        return compile_logger_weapon(
            actor, instance, entity, row, modifiers, movement_units_per_tile
        )
    _fields(
        attack,
        {"projectile", "splash_layer_policy", "radius_multiplier"},
        "Guardian attack",
    )
    if attack["splash_layer_policy"] not in LAYER_POLICIES:
        raise InputError("Guardian splash layer policy must be explicit")
    if "inactive_primary_policy" not in attack["projectile"]:
        raise InputError("Guardian projectile needs explicit inactive-primary behavior")
    radius_multiplier = number(
        attack["radius_multiplier"], "Guardian splash radius scale", EPSILON
    )
    mode = entity["mode"]
    actor.update(
        kind="unit",
        layer="ground",
        movement="ground",
        blocking=False,
        width=0,
        height=0,
        speed=number(mode["movementSpeed"], "Guardian movement speed", EPSILON)
        / movement_units_per_tile
        * modifiers["movement_speed_multiplier"],
        damage=number(
            row["stats"]["normal"]["damagePerShot"], "Guardian damage per shot", EPSILON
        )
        * modifiers["damage_multiplier"],
        range=number(mode["range"], "Guardian range", 0)
        * modifiers["range_multiplier"],
        attack_interval_seconds=number(
            mode["attackSpeed"], "Guardian attack interval", EPSILON
        )
        * modifiers["attack_interval_multiplier"],
        target_priorities=["unit"],
        target_layers=["ground", "air"],
        wall_behavior=deepcopy(wall),
        buff_class="guardian",
        hazard_class="guardian",
        healing_class="guardian",
        attack_model={
            "kind": "radial",
            "source": parameters["source"],
            "target_kinds": ["unit"],
            "target_layers": ["ground", "air"],
            "maximum_hp_fraction": 0,
            "projectile": deepcopy(attack["projectile"]),
            "splash_layer_policy": attack["splash_layer_policy"],
            "radius": number(mode["damageRadius"], "Guardian damage radius", EPSILON)
            * radius_multiplier,
        },
        guardian_model={
            "entity": entity_id,
            "level": instance["level"],
            "parameters": deepcopy(parameters),
            "trigger_radius": number(
                mode["triggerRadius"], "Guardian trigger radius", EPSILON
            )
            * parameters["activation"]["trigger_radius_multiplier"],
        },
    )
    validate_pattern(actor["attack_model"])
    if entity_id == "longshot":
        death = require(instance, "death_parameters")
        _fields(
            death,
            {
                "source",
                "delay_seconds",
                "damage_multiplier",
                "radius_multiplier",
                "target_layers",
            },
            "Longshot final blast",
        )
        identifier(death["source"], "Longshot death evidence")
        number(death["delay_seconds"], "Longshot death delay", 0)
        number(death["damage_multiplier"], "Longshot death damage scale", 0)
        number(death["radius_multiplier"], "Longshot death radius scale", EPSILON)
        _values(death["target_layers"], {"ground", "air"}, "Longshot death layers")
        actor["death_model"] = {
            "kind": "fixed_area_sequence_at_death",
            "geometry": "offsets_from_source_center_at_death",
            "source": death["source"],
            "effects": [
                {
                    "id": "final-blow",
                    "source": death["source"],
                    "kind": "area_damage",
                    "delay_seconds": death["delay_seconds"],
                    "amount": number(row["deathDamage"], "Longshot death damage", 0)
                    * death["damage_multiplier"],
                    "area": {
                        "offset_x": 0,
                        "offset_y": 0,
                        "radius": number(
                            mode["deathDamageRadius"], "Longshot death radius", EPSILON
                        )
                        * death["radius_multiplier"],
                        "target_team": "attack",
                        "target_kinds": ["unit"],
                        "target_layers": deepcopy(death["target_layers"]),
                    },
                }
            ],
        }
        actor["entity_adapter"]["death_parameters"] = deepcopy(death)
        if "smasher_parameters" in instance:
            raise InputError("Longshot cannot select Smasher abilities")
    else:
        if "death_parameters" in instance:
            raise InputError("Smasher death uses its explicit dropped rage field")
        rage = require(instance, "smasher_parameters")
        _fields(rage, {"source", "hall_rage", "dropped_rage"}, "Smasher abilities")
        identifier(rage["source"], "Smasher ability evidence")
        if rage["hall_rage"] != {
            "damage_basis": "snapshot_rageDamageIncrease_percent_bonus",
            "movement_basis": "snapshot_rageSpeedIncrease_additive_units",
            "duration": "until_permanent_death",
            "composition": "multiply_damage_add_movement_with_other_sources",
        }:
            raise InputError(
                "Smasher self-rage statistic interpretation must be explicit"
            )
        _validate_dropped_rage(rage["dropped_rage"])
        actor["guardian_model"].update(
            self_rage_damage_multiplier=1
            + number(entity["rageDamageIncrease"], "Smasher rage damage percent", 0)
            / 100,
            self_rage_movement_bonus=number(
                entity["rageSpeedIncrease"], "Smasher rage movement", 0
            )
            / movement_units_per_tile
            * modifiers["movement_speed_multiplier"],
            dropped_rage=deepcopy(rage["dropped_rage"]),
        )
    actor["entity_adapter"].update(
        guardian_parameters=deepcopy(parameters),
        behavior_verification="explicit_guardian_hypotheses_not_replay_validated",
    )
    return actor


def validate_guardian_deployment(effect, actors):
    if effect.get("kind") == "deploy" and any(
        "guardian_model" in actors.get(actor_id, {})
        for actor_id in effect.get("targets", [])
    ):
        raise InputError(
            "A Guardian can only emerge through its linked Town Hall lifecycle"
        )


def _recipient_class(actor):
    if "guardian_model" in actor:
        return "guardian"
    if "defending_hero_model" in actor:
        return "defending_hero"
    if actor["kind"] == "unit":
        return "defending_troop"
    return actor["kind"]


class GuardianCombat:
    """One linked Guardian, persistent routes and explicit rage membership."""

    def __init__(self, actors, select_target, specification):
        self.actors = actors
        self.ordinary_select_target = select_target
        self.models = {}
        self.states = {}
        self.fields = []
        self.crossing_hints = {}
        self.boundary_sides = {}
        self.trace = None
        self.width, self.height = specification["width"], specification["height"]
        halls = {
            key: actor
            for key, actor in actors.items()
            if "guardian_hall_model" in actor
        }
        guardians = {
            key: actor for key, actor in actors.items() if "guardian_model" in actor
        }
        if not halls and not guardians:
            return
        if len(halls) != 1 or len(guardians) != 1:
            raise InputError(
                "A TH18 scene needs exactly one Hall and one selected Guardian"
            )
        validate_defending_unit_responses(actors, specification)
        hall_id, hall = next(iter(halls.items()))
        _fields(hall["guardian_hall_model"], {"binding"}, "Guardian Hall runtime")
        binding = hall["guardian_hall_model"]["binding"]
        validate_binding(binding)
        guardian_id, actor = next(iter(guardians.items()))
        model = deepcopy(actor["guardian_model"])
        expected = {"entity", "level", "parameters", "trigger_radius"}
        if model.get("entity") == "smasher":
            expected |= {
                "self_rage_damage_multiplier",
                "self_rage_movement_bonus",
                "dropped_rage",
            }
        _fields(model, expected, "Guardian runtime model")
        _validate_parameters(model["parameters"])
        number(model["trigger_radius"], "Guardian runtime trigger radius", EPSILON)
        if (
            model["entity"] not in GUARDIANS
            or binding["actor_id"] != guardian_id
            or (binding["entity"], binding["level"])
            != (model["entity"], model["level"])
            or model["parameters"]["hall_id"] != hall_id
            or hall["team"] != "defense"
            or hall["kind"] != "building"
            or hall["spawn_seconds"] != 0
            or not hall["counts_for_destruction"]
            or hall["damage"] != 0
            or hall["attack_model"]["kind"] != "none"
            or not hall["blocking"]
            or "town_hall_model" in hall
            or actor["team"] != "defense"
            or actor["kind"] != "unit"
            or actor["spawn_seconds"] != "controlled"
            or actor["counts_for_destruction"]
            or actor["movement"] != "ground"
            or actor["layer"] != "ground"
            or actor["blocking"]
            or actor["target_priorities"] != ["unit"]
            or actor["target_layers"] != ["ground", "air"]
            or actor["attack_model"]["kind"]
            != ("logger_rolling_log" if model["entity"] == "logger" else "radial")
            or actor["attack_model"]["target_kinds"] != ["unit"]
            or actor["attack_model"]["target_layers"] != ["ground", "air"]
            or actor.get("wall_behavior", {}).get("kind") != "avoid"
            or actor.get("buff_class") != "guardian"
            or actor.get("hazard_class") != "guardian"
            or "hero_model" in actor
            or "defending_hero_model" in actor
            or (model["entity"] == "longshot" and "death_model" not in actor)
            or (model["entity"] == "smasher" and "death_model" in actor)
            or (model["entity"] == "logger" and "logger_model" not in actor)
        ):
            raise InputError(
                "Invalid Guardian runtime identity, Hall link, role or weapon (including Logger binding)"
            )
        if model["entity"] == "smasher":
            number(
                model["self_rage_damage_multiplier"], "runtime Smasher rage damage", 1
            )
            number(
                model["self_rage_movement_bonus"], "runtime Smasher rage movement", 0
            )
            _validate_dropped_rage(model["dropped_rage"])
        origin = center(hall)
        model["origin"] = origin
        home = _point(model["parameters"]["home"], "Guardian home")
        if center(actor) != home:
            raise InputError(
                "Guardian runtime emergence position differs from its home"
            )
        blocked = {
            (x, y)
            for other in actors.values()
            if other["blocking"]
            for x in range(other["x"], other["x"] + other["width"])
            for y in range(other["y"], other["y"] + other["height"])
        }
        for point in [
            home,
            *[
                (waypoint["x"], waypoint["y"])
                for waypoint in model["parameters"]["patrol"]["waypoints"]
            ],
        ]:
            if (
                not (0 <= point[0] < self.width and 0 <= point[1] < self.height)
                or (floor(point[0]), floor(point[1])) in blocked
                or _distance(point, origin)
                >= model["parameters"]["leash_radius_tiles"] - EPSILON
            ):
                raise InputError(
                    "Guardian home and patrol must be exterior points inside the board and leash"
                )
        self.models[guardian_id] = model
        self.states[guardian_id] = {
            "phase": "dormant",
            "triggered_at": None,
            "emerged_at": None,
            "activation_due": None,
            "activation_frozen_until": 0,
            "primary": None,
            "waypoint_index": 0,
            "wait_until": None,
            "route_arrival": None,
            "received_damage": 0,
            "retaliation_pending": False,
            "self_rage": False,
            "death_field_created": False,
        }
        for effect in specification.get("effects", []):
            validate_guardian_deployment(effect, actors)

    def _phase(self, actor_id, phase, time):
        state = self.states[actor_id]
        if state["phase"] != phase:
            previous = state["phase"]
            state["phase"] = phase
            if self.trace is not None:
                self.trace.append(
                    {
                        "time_seconds": time,
                        "event": "guardian_phase",
                        "source": actor_id,
                        "from": previous,
                        "to": phase,
                    }
                )

    def _trigger(self, actor, model, time):
        choices = [
            (_distance(model["origin"], center(target)), target["id"])
            for target in self.actors.values()
            if _eligible(actor, target, time)
            and target["layer"] in model["parameters"]["activation"]["trigger_layers"]
            and _distance(model["origin"], center(target))
            <= model["trigger_radius"] + EPSILON
        ]
        return min(choices)[1] if choices else None

    def apply_effects(self, effects, actors, time, trace):
        """Observe original area commands before generic inactive-unit filtering."""
        for actor_id, model in self.models.items():
            state = self.states[actor_id]
            if state["phase"] not in {"dormant", "emerging"}:
                continue
            for effect in effects:
                applies = False
                if effect["kind"] not in {"freeze", "area_freeze"}:
                    continue
                if "area" not in effect:
                    applies = bool(
                        {actor_id, model["parameters"]["hall_id"]}
                        & set(effect["targets"])
                    )
                else:
                    area = effect["area"]
                    applies = (
                        area["target_team"] == "defense"
                        and "ground" in area["target_layers"]
                        and bool({"unit", "building"} & set(area["target_kinds"]))
                        and _distance(model["origin"], (area["x"], area["y"]))
                        <= area["radius"] + EPSILON
                    )
                if applies:
                    until = time + effect["duration_seconds"]
                    extension = max(
                        until - max(time, state["activation_frozen_until"]), 0
                    )
                    if state["activation_due"] is not None:
                        state["activation_due"] += extension
                    state["activation_frozen_until"] = max(
                        until, state["activation_frozen_until"]
                    )
                    trace.append(
                        {
                            "time_seconds": time,
                            "event": "guardian_activation_freeze",
                            "source": actor_id,
                            "until_seconds": state["activation_frozen_until"],
                        }
                    )

    def prepare(self, actors, time, trace, allow_emergence=True):
        self.trace = trace
        for actor_id, model in self.models.items():
            actor, state = actors[actor_id], self.states[actor_id]
            hall = actors[model["parameters"]["hall_id"]]
            if (
                state["phase"] in {"dormant", "emerging"}
                and actor["spawn_seconds"] != "controlled"
            ):
                raise InputError("Guardian reserve was externally deployed")
            if (
                model["entity"] == "smasher"
                and hall["hp"] <= 0
                and actor["hp"] > 0
                and not state["self_rage"]
            ):
                state["self_rage"] = True
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "smasher_hall_rage",
                        "source": actor_id,
                        "hall": hall["id"],
                    }
                )
            actor["_guardian_self_damage_multiplier"] = (
                model.get("self_rage_damage_multiplier", 1) if state["self_rage"] else 1
            )
            actor["_guardian_self_movement_bonus"] = (
                model.get("self_rage_movement_bonus", 0) if state["self_rage"] else 0
            )
            if state["emerged_at"] is not None and actor["hp"] <= 0:
                self._phase(actor_id, "dead", time)
                state.update(primary=None, wait_until=None, route_arrival=None)
                actor["target"] = None
                if model["entity"] == "smasher" and not state["death_field_created"]:
                    state["death_field_created"] = True
                    field = {
                        **deepcopy(model["dropped_rage"]),
                        "guardian": actor_id,
                        "origin": center(actor),
                        "starts_at": time,
                        "ends_at": time + model["dropped_rage"]["duration_seconds"],
                    }
                    self.fields.append(field)
                    trace.append(
                        {
                            "time_seconds": time,
                            "event": "smasher_death_rage",
                            "source": actor_id,
                            "x": actor["x"],
                            "y": actor["y"],
                            "ends_at": field["ends_at"],
                        }
                    )
                continue
            if state["phase"] == "dead":
                if actor["hp"] > 0:
                    raise InputError("A Guardian cannot resurrect")
                continue
            if state["phase"] in {"dormant", "emerging"}:
                frozen_until = state["activation_frozen_until"]
                if state["triggered_at"] is None and frozen_until <= time + EPSILON:
                    trigger = self._trigger(actor, model, time)
                    if trigger is not None or hall["hp"] <= 0:
                        state["triggered_at"] = time
                        state["activation_due"] = (
                            time + model["parameters"]["activation"]["delay_seconds"]
                        )
                        self._phase(actor_id, "emerging", time)
                        trace.append(
                            {
                                "time_seconds": time,
                                "event": "guardian_triggered",
                                "source": actor_id,
                                "trigger": trigger,
                                "hall_destroyed": hall["hp"] <= 0,
                            }
                        )
                if (
                    allow_emergence
                    and state["activation_due"] is not None
                    and max(state["activation_due"], frozen_until) <= time + EPSILON
                ):
                    actor.update(
                        spawn_seconds=time,
                        next_attack=time + actor["first_attack_seconds"],
                        target=None,
                    )
                    state["emerged_at"] = time
                    state["activation_due"] = None
                    self._phase(actor_id, "guarding", time)
                    trace.append(
                        {
                            "time_seconds": time,
                            "event": "guardian_emerged",
                            "source": actor_id,
                            "x": actor["x"],
                            "y": actor["y"],
                        }
                    )
            received = actor.get("_received_damage", 0)
            if received > state["received_damage"] + EPSILON:
                state["retaliation_pending"] = True
            state["received_damage"] = received
        self._update_fields(actors, time, trace)

    def emergence_ready(self, time):
        return any(
            state["phase"] == "emerging"
            and state["activation_due"] is not None
            and max(state["activation_due"], state["activation_frozen_until"])
            <= time + EPSILON
            for state in self.states.values()
        )

    def _update_fields(self, actors, time, trace):
        for key, hint in list(self.crossing_hints.items()):
            if hint["time_seconds"] > time + EPSILON:
                continue
            if (
                abs(hint["time_seconds"] - time) <= EPSILON
                and _distance(center(actors[key[1]]), hint["position"]) <= EPSILON * 128
            ):
                self.boundary_sides[key] = hint
            self.crossing_hints.pop(key)
        for actor in actors.values():
            factor, bonus = 1.0, 0.0
            sources = []
            for field in self.fields:
                if (
                    field["starts_at"] <= time + EPSILON < field["ends_at"]
                    and _active(actor, time)
                    and actor["team"] == "defense"
                    and actor["kind"] in field["target_kinds"]
                    and actor["layer"] in field["target_layers"]
                    and _recipient_class(actor) in field["recipient_classes"]
                    and self._field_inside(field, actor)
                ):
                    factor *= field["damage_multiplier"]
                    bonus += field["movement_bonus_tiles_per_second"]
                    sources.append(field["guardian"])
            previous = actor.get("_guardian_field_sources", [])
            actor["_guardian_field_damage_multiplier"] = factor
            actor["_guardian_field_movement_bonus"] = bonus
            actor["_guardian_field_sources"] = sources
            if previous != sources:
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "guardian_rage_membership",
                        "target": actor["id"],
                        "sources": sources,
                    }
                )

    def _field_inside(self, field, actor):
        key = field["guardian"], actor["id"]
        side = self.boundary_sides.get(key)
        if side is not None:
            if _distance(center(actor), side["position"]) <= EPSILON * 128:
                return side["inside_after"]
            self.boundary_sides.pop(key)
        return (
            _distance(center(actor), field["origin"]) <= field["radius_tiles"] + EPSILON
        )

    def _bounded_blocks(self, actor, model, blocked, width, height):
        radius = model["parameters"]["leash_radius_tiles"]
        outside = {
            (x, y)
            for x in range(width)
            for y in range(height)
            if _distance((x + 0.5, y + 0.5), model["origin"]) >= radius - EPSILON
        }
        outside.discard((floor(actor["x"]), floor(actor["y"])))
        return blocked | outside

    def _route(
        self,
        actor,
        model,
        blocked,
        width,
        height,
        target=None,
        goal=None,
        remember=True,
    ):
        if (
            target is not None
            and target_distance(center(actor), target) <= actor["range"] + EPSILON
        ):
            route, key = [], None
        elif goal is not None and _distance(center(actor), goal) <= EPSILON:
            route, key = [], None
        else:
            solid = self._bounded_blocks(actor, model, blocked, width, height)
            key = (
                ("combat", target["id"], actor["range"], frozenset(solid))
                if target is not None
                else ("point", goal, frozenset(solid))
            )
            remaining = actor.get("_remaining_path", [])
            if (
                actor.get("_guardian_path_key") == key
                and remaining
                and (
                    target is None
                    or target_distance(remaining[-1], target)
                    <= actor["range"] + EPSILON
                )
            ):
                return list(remaining)
            probe, prefix = actor, []
            if actor.get("_guardian_path_key") is not None and remaining:
                point = remaining[0]
                if (floor(point[0]), floor(point[1])) not in solid and _distance(
                    center(actor), point
                ) > EPSILON:
                    probe, prefix = {**actor, "x": point[0], "y": point[1]}, [point]
            if target is not None:
                route = _ground_route(
                    {**probe, "_terminal_ground_approach": False},
                    target,
                    solid,
                    width,
                    height,
                )
            else:
                route = self._point_route(probe, goal, solid, width, height)
            if route is not None:
                route = prefix + route
        if remember:
            actor["_guardian_path_key"] = key
            actor["_remaining_path"] = list(route) if route is not None else []
        return route

    @staticmethod
    def _point_route(actor, goal, blocked, width, height):
        start = floor(actor["x"]), floor(actor["y"])
        destination = floor(goal[0]), floor(goal[1])
        if destination in blocked:
            return None
        pending, previous = deque([start]), {start: None}
        while pending:
            cell = pending.popleft()
            if cell == destination:
                break
            x, y = cell
            for neighbor in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y)):
                if (
                    0 <= neighbor[0] < width
                    and 0 <= neighbor[1] < height
                    and neighbor not in blocked
                    and neighbor not in previous
                ):
                    previous[neighbor] = cell
                    pending.append(neighbor)
        if destination not in previous:
            return None
        cells, cursor = [], destination
        while cursor != start:
            cells.append((cursor[0] + 0.5, cursor[1] + 0.5))
            cursor = previous[cursor]
        route = list(reversed(cells))
        start_center = start[0] + 0.5, start[1] + 0.5
        if start != destination and _distance(center(actor), start_center) > EPSILON:
            route.insert(0, start_center)
        if not route or _distance(route[-1], goal) > EPSILON:
            route.append(goal)
        return route

    def _remember_arrival(self, actor, state, route, time):
        state["route_arrival"] = None
        speed = movement_speed(actor)
        if route and speed > EPSILON and actor["frozen_until"] <= time + EPSILON:
            state["route_arrival"] = time + _route_length(actor, route) / speed
        return route

    def _eligible_primary(self, actor, target, model, time):
        return (
            target is not None
            and _eligible(actor, target, time)
            and _distance(model["origin"], center(target))
            < model["parameters"]["leash_radius_tiles"] - EPSILON
        )

    def select_target(self, actor, actors, time, blocked, width, height):
        if actor["id"] not in self.models:
            return self.ordinary_select_target(
                actor, actors, time, blocked, width, height
            )
        actor_id = actor["id"]
        model, state = self.models[actor_id], self.states[actor_id]
        if not _active(actor, time):
            return None, None
        state["route_arrival"] = None
        if state["phase"] == "engaged":
            target = actors.get(state["primary"])
            route = (
                self._route(actor, model, blocked, width, height, target=target)
                if self._eligible_primary(actor, target, model, time)
                else None
            )
            if route is not None:
                actor["target"] = target["id"]
                return target, self._remember_arrival(actor, state, route, time)
            state.update(primary=None, wait_until=None)
            actor["target"] = None
            self._phase(actor_id, "returning", time)
        if state["phase"] == "returning":
            home = _point(model["parameters"]["home"], "Guardian home")
            if _distance(center(actor), home) > EPSILON:
                route = self._route(actor, model, blocked, width, height, goal=home)
                return None, self._remember_arrival(actor, state, route, time)
            self._phase(actor_id, "guarding", time)
        radius = (
            model["parameters"]["leash_radius_tiles"]
            if state["retaliation_pending"]
            else model["parameters"]["acquisition_radius_tiles"]
        )
        choices = []
        for target in actors.values():
            if (
                not self._eligible_primary(actor, target, model, time)
                or _distance(model["origin"], center(target)) > radius + EPSILON
            ):
                continue
            route = self._route(
                actor, model, blocked, width, height, target=target, remember=False
            )
            if route is not None:
                choices.append(
                    (target_distance(center(actor), target), target["id"], target)
                )
        state["retaliation_pending"] = False
        if choices:
            _, _, target = min(choices, key=lambda choice: choice[:2])
            state.update(primary=target["id"], wait_until=None)
            actor["target"] = target["id"]
            self._phase(actor_id, "engaged", time)
            route = self._route(actor, model, blocked, width, height, target=target)
            return target, self._remember_arrival(actor, state, route, time)
        actor["target"] = None
        waypoints = model["parameters"]["patrol"]["waypoints"]
        for _ in range(len(waypoints)):
            waypoint = waypoints[state["waypoint_index"]]
            goal = waypoint["x"], waypoint["y"]
            if _distance(center(actor), goal) > EPSILON:
                self._phase(actor_id, "patrolling", time)
                route = self._route(actor, model, blocked, width, height, goal=goal)
                return None, self._remember_arrival(actor, state, route, time)
            if state["wait_until"] is None:
                state["wait_until"] = time + waypoint["wait_seconds"]
            if state["wait_until"] > time + EPSILON:
                self._phase(actor_id, "patrol_wait", time)
                return None, []
            state["waypoint_index"] = (state["waypoint_index"] + 1) % len(waypoints)
            state["wait_until"] = None
        return None, []

    def next_boundary(self, time):
        pending = [
            state[field]
            for state in self.states.values()
            for field in (
                "activation_due",
                "activation_frozen_until",
                "wait_until",
                "route_arrival",
            )
            if state[field] is not None and state[field] > time + EPSILON
        ]
        pending += [
            field["ends_at"]
            for field in self.fields
            if field["ends_at"] > time + EPSILON
        ]
        return min(pending) if pending else None

    def first_crossing_delay(
        self, actor, route, time, horizon, effective_speed=None, forced_motion=False
    ):
        from .buffs import _circle_events

        speed = (
            movement_speed(actor)
            if effective_speed is None
            else number(effective_speed, "Guardian crossing speed", 0)
        )
        if speed <= EPSILON or (
            actor["frozen_until"] > time + EPSILON and not forced_motion
        ):
            return None
        circles = []
        for guardian_id, model in self.models.items():
            state = self.states[guardian_id]
            if not _eligible(self.actors[guardian_id], actor, time):
                continue
            if state["phase"] in {"dormant", "emerging"}:
                if (
                    actor["layer"]
                    in model["parameters"]["activation"]["trigger_layers"]
                ):
                    circles.append((model["origin"], model["trigger_radius"], None))
            elif state["phase"] == "engaged" and state["primary"] == actor["id"]:
                circles.append(
                    (model["origin"], model["parameters"]["leash_radius_tiles"], None)
                )
            elif state["phase"] not in {"dead", "returning", "engaged"}:
                circles.append(
                    (
                        model["origin"],
                        model["parameters"]["acquisition_radius_tiles"],
                        None,
                    )
                )
        for field in self.fields:
            if (
                time + EPSILON < field["ends_at"]
                and actor["team"] == "defense"
                and actor["kind"] in field["target_kinds"]
                and actor["layer"] in field["target_layers"]
                and _recipient_class(actor) in field["recipient_classes"]
            ):
                circles.append((field["origin"], field["radius_tiles"], field))
        earliest = None
        for origin, radius, field in circles:
            key = (field["guardian"], actor["id"]) if field is not None else None
            if key is not None:
                self.crossing_hints.pop(key, None)
            current_inside = (
                self._field_inside(field, actor) if field is not None else None
            )
            previous, travelled = center(actor), 0.0
            found = False
            for point_index, point in enumerate(route):
                segment = _distance(previous, point)
                for contact, inside_after in _circle_events(
                    previous, point, origin, radius
                ):
                    if key is not None:
                        if abs(contact - segment) <= EPSILON:
                            for following in route[point_index + 1 :]:
                                dx, dy = (
                                    following[0] - point[0],
                                    following[1] - point[1],
                                )
                                if hypot(dx, dy) <= EPSILON:
                                    continue
                                inside_after = (point[0] - origin[0]) * dx + (
                                    point[1] - origin[1]
                                ) * dy < -EPSILON
                                break
                        if inside_after == current_inside:
                            continue
                        if travelled + contact <= speed * EPSILON:
                            contact = max(contact, speed * EPSILON * 2)
                    delay = (travelled + contact) / speed
                    if EPSILON < delay <= horizon + EPSILON:
                        if contact > segment + EPSILON:
                            continue
                        earliest = delay if earliest is None else min(earliest, delay)
                        if key is not None:
                            fraction = min(contact / segment, 1)
                            position = tuple(
                                previous[index]
                                + (point[index] - previous[index]) * fraction
                                for index in (0, 1)
                            )
                            self.crossing_hints[key] = {
                                "time_seconds": time + delay,
                                "position": position,
                                "inside_after": inside_after,
                            }
                        found = True
                        break
                if found:
                    break
                travelled += segment
                if travelled > speed * horizon:
                    break
                previous = point
        return earliest

    def frame(self, actor):
        if actor["id"] not in self.states:
            return (
                {"guardian_rage_sources": actor.get("_guardian_field_sources", [])}
                if actor.get("_guardian_field_sources")
                else {}
            )
        state = self.states[actor["id"]]
        return {
            "guardian_phase": state["phase"],
            "guardian_primary": state["primary"],
            "guardian_self_rage": state["self_rage"],
        }

    def result(self):
        return {
            "states": deepcopy(self.states),
            "rage_fields": deepcopy(self.fields),
            "full_game_prediction": False,
        }
