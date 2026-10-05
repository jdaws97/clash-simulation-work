"""Explicit Mortar and Eagle hypotheses with separately timed released shells.

The snapshot supplies shell damage and timing fields, not their interpretation.
Burst cycles, acquisition, activation contribution, travel and shockwave overlap
therefore require named hypotheses. Unreleased shells use the shared attack
clock so Freeze and attack-rate effects preserve unfinished firing work.
"""

from copy import deepcopy
from math import hypot

from .common import InputError, identifier, integer, number, require
from .rates import attack_rate
from .spatial import EPSILON, _active, _eligible, center, target_distance


INDIRECT_RULES = {
    "indirect_shells": "one_projectile_per_due_shell_never_simultaneous_burst_allocation",
    "indirect_cycle": "explicit_snapshot_intershot_and_start_or_end_based_recovery",
    "indirect_minimum_range": "acquisition_annulus_only_released_splash_is_unrestricted",
    "indirect_freeze": "shared_attack_clock_pauses_unreleased_shells",
    "indirect_death": "cancel_unreleased_shells_keep_released_projectiles",
    "indirect_no_target": "hold_due_shell_until_an_eligible_primary_exists",
    "eagle_activation": "cumulative_explicit_deployed_actor_and_original_command_weights",
    "eagle_targeting": "declared_annulus_population_neighborhood_hp_then_distance_then_id",
    "eagle_burst_target": "retain_primary_until_ineligible_then_reacquire",
    "eagle_shockwave": "explicit_same_impact_additive_or_outer_ring_damage",
}
PARAMETER_FIELDS = {
    "source",
    "damage_basis",
    "minimum_range",
    "burst_timing",
    "targeting",
    "readiness_policy",
    "activation",
    "shockwave",
}
READINESS_POLICY = {
    "no_target": "hold_due_shell_until_eligible",
    "freeze": "pause_remaining_shared_attack_clock",
    "source_death": "cancel_unlaunched_shells_keep_released_projectiles",
}
SINGLE_TIMING = "snapshot_attackSpeed_single_shot_interval"
START_TIMING = (
    "snapshot_attackSpeed_inter_shot_and_timeBetweenBursts_start_to_start_hypothesis"
)
END_TIMING = (
    "snapshot_attackSpeed_inter_shot_and_timeBetweenBursts_last_to_next_hypothesis"
)
BURST_POLICY = "retain_primary_until_invalid_then_reacquire"


def _fields(value, fields, label):
    if not isinstance(value, dict) or set(value) != fields:
        raise InputError(f"{label} needs its complete explicit parameters")


def _targeting(parameters, eagle):
    fields = {"policy", "burst_policy"}
    if eagle:
        fields |= {"radius_tiles", "hitpoint_basis", "population"}
    _fields(parameters, fields, "Indirect targeting")
    if parameters["burst_policy"] != BURST_POLICY:
        raise InputError("Indirect burst target retention must be explicit")
    expected = (
        "maximum_neighborhood_hitpoints" if eagle else "nearest_eligible_retained"
    )
    if parameters["policy"] != expected:
        raise InputError("Unsupported indirect acquisition policy")
    if eagle:
        number(parameters["radius_tiles"], "Eagle density radius", 0)
        if parameters["hitpoint_basis"] not in {"current", "maximum"}:
            raise InputError("Eagle density requires current or maximum HP")
        if parameters["population"] != "eligible_in_acquisition_annulus":
            raise InputError("Eagle density population must be explicit")


def _weights(weights, label):
    if not isinstance(weights, dict):
        raise InputError(f"{label} must explicitly map IDs to contribution weights")
    for instance_id, weight in weights.items():
        identifier(instance_id, label)
        number(weight, label, 0)


def _activation(parameters, mode):
    _fields(
        parameters,
        {
            "source",
            "threshold_basis",
            "threshold_multiplier",
            "delay_seconds",
            "actor_weights",
            "command_weights",
        },
        "Eagle activation",
    )
    identifier(parameters["source"], "Eagle activation evidence")
    if parameters["threshold_basis"] != "snapshot_activationHousingSpace":
        raise InputError("Eagle activation threshold mapping must be explicit")
    threshold = number(
        require(mode, "activationHousingSpace"), "activation threshold", EPSILON
    )
    threshold *= number(parameters["threshold_multiplier"], "activation scale", EPSILON)
    number(parameters["delay_seconds"], "activation delay", 0)
    for field in ("actor_weights", "command_weights"):
        _weights(parameters[field], field)
    return {
        "source": parameters["source"],
        "threshold": threshold,
        "delay_seconds": parameters["delay_seconds"],
        "actor_weights": deepcopy(parameters["actor_weights"]),
        "command_weights": deepcopy(parameters["command_weights"]),
    }


def compile_indirect_defense(actor, instance, entity, row, modifiers):
    """Compile after common identity/HP validation, before generic defenses."""
    from .combat import validate_pattern

    entity_id = entity["id"]
    eagle = entity_id == "eagle-artillery"
    selected = require(instance, "mode")
    allowed_modes = {"normal"} if eagle else {"normal", "gearedUpBurst"}
    if (
        entity_id not in {"mortar", "eagle-artillery"}
        or instance["entity"] != entity_id
        or selected not in allowed_modes
        or instance["statistics_mode"] != selected
        or actor["team"] != "defense"
        or not actor["counts_for_destruction"]
        or actor["spawn_seconds"] != 0
        or "wall_parameters" in instance
    ):
        raise InputError(
            "Indirect weapons require a counted initial defense and matching mode"
        )
    mode = require(require(entity, "modes"), selected)
    availability = next(
        (
            entry["count"]
            for entry in entity.get("availablePerTownHall", [])
            if entry["townHallLevel"] == instance["town_hall"]
        ),
        None,
    )
    if availability == 0:
        raise InputError("Indirect defense is absent at the selected Town Hall")
    if instance["level"] < mode.get("availableFromLevel", 1):
        raise InputError("Indirect firing mode is not unlocked at this level")
    stats = require(require(row, "stats"), selected)
    parameters = require(instance, "indirect_parameters")
    _fields(parameters, PARAMETER_FIELDS, "Indirect weapon")
    identifier(parameters["source"], "indirect weapon evidence")
    if parameters["damage_basis"] != "snapshot_damagePerShot_is_one_shell":
        raise InputError("Indirect shell damage mapping must be explicit")
    if parameters["readiness_policy"] != READINESS_POLICY:
        raise InputError(
            "Indirect readiness needs explicit pause, death and no-target rules"
        )
    _targeting(parameters["targeting"], eagle)
    minimum = parameters["minimum_range"]
    if isinstance(minimum, dict) and minimum.get("basis") == "snapshot_minRange":
        _fields(minimum, {"basis", "multiplier"}, "Snapshot minimum range")
        minimum_range = number(require(mode, "minRange"), "catalog minimum range", 0)
        minimum_range *= number(minimum["multiplier"], "minimum-range scale", 0)
    else:
        _fields(minimum, {"basis", "value"}, "Explicit minimum range")
        if minimum["basis"] != "explicit_tiles_hypothesis":
            raise InputError("Missing catalog minimum range needs a tiles hypothesis")
        minimum_range = number(minimum["value"], "minimum range", 0)
    minimum_range *= modifiers["range_multiplier"]
    attack = require(instance, "attack_parameters")
    _fields(
        attack,
        {"source", "projectile", "radius_multiplier", "splash_layer_policy"},
        "Indirect attack",
    )
    identifier(attack["source"], "indirect attack evidence")
    projectile = attack["projectile"]
    _fields(
        projectile,
        {
            "timing",
            "speed_tiles_per_second",
            "destination",
            "hit_radius",
            "inactive_primary_policy",
        },
        "Indirect projectile",
    )
    if projectile["timing"] != "launch_distance_delay":
        raise InputError(
            "Indirect shells need explicit travel speed and impact location"
        )
    radius = number(require(mode, "splashRadius"), "catalog splash radius", EPSILON)
    radius *= number(attack["radius_multiplier"], "splash-radius scale", EPSILON)
    interval = number(require(mode, "attackSpeed"), "catalog shot interval", EPSILON)
    interval *= modifiers["attack_interval_multiplier"]
    shots = integer(mode.get("shotsPerBurst", 1), "shells per burst", 1)
    timing = parameters["burst_timing"]
    if shots == 1:
        if timing != SINGLE_TIMING:
            raise InputError("Single-shot Mortar needs an explicit attackSpeed mapping")
        recovery = interval
    else:
        if timing not in {START_TIMING, END_TIMING}:
            raise InputError("Burst-cycle start/end convention must be explicit")
        recovery = number(
            require(mode, "timeBetweenBursts"), "catalog burst interval", EPSILON
        )
        recovery *= modifiers["attack_interval_multiplier"]
        if timing == START_TIMING:
            recovery -= (shots - 1) * interval
        number(recovery, "post-burst recovery", EPSILON)
    damage = number(require(stats, "damagePerShot"), "catalog shell damage", EPSILON)
    damage *= modifiers["damage_multiplier"]
    number(damage, "modified shell damage", EPSILON)
    layers = ["ground", "air"] if eagle else ["ground"]
    pattern = {
        "kind": "eagle_shell" if eagle else "radial",
        "source": attack["source"],
        "target_kinds": ["unit"],
        "target_layers": layers,
        "maximum_hp_fraction": 0,
        "projectile": deepcopy(projectile),
        "radius": radius,
        "splash_layer_policy": attack["splash_layer_policy"],
    }
    activation = None
    if eagle:
        activation = _activation(parameters["activation"], mode)
        shockwave = parameters["shockwave"]
        _fields(
            shockwave,
            {"source", "damage_basis", "radius_tiles", "overlap_policy"},
            "Eagle shockwave",
        )
        identifier(shockwave["source"], "shockwave evidence")
        if (
            shockwave["damage_basis"]
            != "snapshot_shockwaveDamagePerHit_is_additional_per_shell"
        ):
            raise InputError("Eagle shockwave damage mapping must be explicit")
        pattern.update(
            shockwave_radius=shockwave["radius_tiles"],
            shockwave_damage_ratio=number(
                require(stats, "shockwaveDamagePerHit"), "catalog shockwave damage", 0
            )
            * modifiers["damage_multiplier"]
            / damage,
            shockwave_overlap_policy=shockwave["overlap_policy"],
        )
    elif parameters["activation"] is not None or parameters["shockwave"] is not None:
        raise InputError("Mortar activation and shockwave must explicitly be null")
    validate_pattern(pattern)
    dimensions = entity["size"].split("x")
    if len(dimensions) != 2 or any(not part.isdigit() for part in dimensions):
        raise InputError("Indirect defense needs its catalog rectangular footprint")
    width, height = (int(part) for part in dimensions)
    maximum_range = number(require(mode, "range"), "catalog weapon range", EPSILON)
    maximum_range *= modifiers["range_multiplier"]
    number(minimum_range, "minimum range", 0, maximum_range)
    actor.update(
        kind="defense",
        layer="ground",
        movement="stationary",
        speed=0,
        blocking=True,
        width=width,
        height=height,
        target_priorities=["unit"],
        target_priority_tiers=[["unit"]],
        target_layers=layers,
        minimum_range=minimum_range,
        range=maximum_range,
        damage=damage,
        attack_interval_seconds=interval,
        attack_model=pattern,
        indirect_model={
            "kind": entity_id,
            "source": parameters["source"],
            "shots_per_burst": shots,
            "inter_shot_seconds": interval,
            "post_burst_seconds": recovery,
            "uninterrupted_cycle_seconds": (shots - 1) * interval + recovery,
            "burst_timing": timing,
            "targeting": deepcopy(parameters["targeting"]),
            "readiness_policy": deepcopy(parameters["readiness_policy"]),
            "activation": activation,
        },
    )
    actor["entity_adapter"].update(
        indirect_parameters=deepcopy(parameters),
        attack_parameters=deepcopy(attack),
        shell_damage_statistic=f"stats.{selected}.damagePerShot",
        snapshot_dps=stats.get("dps"),
        behavior_verification="explicit_indirect_weapon_hypotheses_not_replay_validated",
    )
    return actor


def validate_eagle_shell(pattern):
    """Validate additional fields after the shared projectile/layer validator."""
    number(require(pattern, "radius"), "Eagle shell radius", EPSILON)
    number(
        require(pattern, "shockwave_radius"),
        "Eagle shockwave radius",
        pattern["radius"],
    )
    number(
        require(pattern, "shockwave_damage_ratio"), "Eagle shockwave damage ratio", 0
    )
    if require(pattern, "shockwave_overlap_policy") not in {
        "additive_with_shell",
        "outer_ring_only",
    }:
        raise InputError("Eagle shell/shockwave overlap rule must be explicit")


def eagle_shell_impacts(packet, point, actors, time, damage_eligible):
    """Combine the shell and shockwave before shared simultaneous health damage."""
    pattern = packet["pattern"]
    impacts = []
    for actor in actors.values():
        if not damage_eligible(packet, actor, time):
            continue
        distance = target_distance(point, actor)
        inner = distance <= pattern["radius"] + EPSILON
        outer = distance <= pattern["shockwave_radius"] + EPSILON
        multiplier = 1 if inner else 0
        if outer and (
            not inner or pattern["shockwave_overlap_policy"] == "additive_with_shell"
        ):
            multiplier += pattern["shockwave_damage_ratio"]
        if multiplier > 0:
            impacts.append((actor, multiplier))
    return impacts


def _validate_model(actor):
    model = require(actor, "indirect_model")
    _fields(
        model,
        {
            "kind",
            "source",
            "shots_per_burst",
            "inter_shot_seconds",
            "post_burst_seconds",
            "uninterrupted_cycle_seconds",
            "burst_timing",
            "targeting",
            "readiness_policy",
            "activation",
        },
        "Indirect runtime model",
    )
    if model["kind"] not in {"mortar", "eagle-artillery"}:
        raise InputError("Unsupported indirect weapon model")
    identifier(model["source"], "indirect model evidence")
    shots = integer(model["shots_per_burst"], "burst shell count", 1)
    interval = number(model["inter_shot_seconds"], "shell interval", EPSILON)
    recovery = number(model["post_burst_seconds"], "burst recovery", EPSILON)
    cycle = number(model["uninterrupted_cycle_seconds"], "burst cycle", EPSILON)
    if abs(cycle - (shots - 1) * interval - recovery) > EPSILON:
        raise InputError("Indirect burst clock is inconsistent")
    if model["burst_timing"] not in (
        {SINGLE_TIMING} if shots == 1 else {START_TIMING, END_TIMING}
    ):
        raise InputError("Indirect burst clock requires a supported timing mapping")
    if model["readiness_policy"] != READINESS_POLICY:
        raise InputError("Indirect runtime readiness must use the declared policy")
    eagle = model["kind"] == "eagle-artillery"
    _targeting(model["targeting"], eagle)
    if (
        actor["kind"] != "defense"
        or actor["team"] != "defense"
        or actor["movement"] != "stationary"
        or actor["layer"] != "ground"
        or not actor["counts_for_destruction"]
        or not actor["blocking"]
        or actor["spawn_seconds"] != 0
        or actor["attack_model"]["kind"] != ("eagle_shell" if eagle else "radial")
    ):
        raise InputError("Indirect runtime requires a counted stationary defense")
    activation = model["activation"]
    if eagle:
        _fields(
            activation,
            {
                "source",
                "threshold",
                "delay_seconds",
                "actor_weights",
                "command_weights",
            },
            "Eagle activation model",
        )
        identifier(activation["source"], "Eagle activation evidence")
        number(activation["threshold"], "Eagle activation threshold", EPSILON)
        number(activation["delay_seconds"], "Eagle activation delay", 0)
        _weights(activation["actor_weights"], "Eagle actor contribution")
        _weights(activation["command_weights"], "Eagle command contribution")
    elif activation is not None:
        raise InputError("Mortar cannot have Eagle activation weights")
    return model


class IndirectDefenseCombat:
    """Own launches through the shared next_attack clock, one shell at a time."""

    def __init__(self, actors, combat, select_target, specification):
        self.models = {
            actor["id"]: deepcopy(_validate_model(actor))
            for actor in actors.values()
            if "indirect_model" in actor
        }
        self.combat = combat
        self.ordinary_select_target = select_target
        self.states = {}
        self.counted_actors = {}
        self.counted_commands = {}
        self.paid_casts = {
            field["id"]: field["start_seconds"]
            for field in specification.get("buff_fields", [])
        }
        for model in specification.get("attack_spell_models", []):
            if model["id"] in self.paid_casts:
                raise InputError("Paid spell cast IDs must be distinct")
            self.paid_casts[model["id"]] = model["time_seconds"]
        command_ids = {
            effect["id"]
            for effect in specification["effects"]
            if effect["kind"] != "deploy"
        }
        if command_ids & set(self.paid_casts):
            raise InputError(
                "Eagle contribution command and paid cast IDs must be distinct"
            )
        command_ids |= set(self.paid_casts)
        for actor_id, model in self.models.items():
            activation = model["activation"]
            if activation is not None:
                attacker_ids = {
                    target["id"]
                    for target in actors.values()
                    if target["kind"] == "unit"
                    and target["team"] != actors[actor_id]["team"]
                }
                if set(activation["actor_weights"]) != attacker_ids:
                    raise InputError(
                        "Eagle weights must explicitly cover every opposing unit, including reserves"
                    )
                if set(activation["command_weights"]) != command_ids:
                    raise InputError(
                        "Eagle weights must explicitly cover every original non-deployment command"
                    )
            self.states[actor_id] = {
                "activated": activation is None,
                "activation_time": None,
                "actor_weight": 0,
                "command_weight": 0,
                "total_weight": 0,
                "next_shell_index": 0,
                "burst_number": 0,
                "burst_primary": None,
                "launched_shells": 0,
                "cancelled_shells": 0,
                "destroyed": False,
            }
            self.counted_actors[actor_id] = set()
            self.counted_commands[actor_id] = set()

    def observe_commands(self, commands, time, trace):
        """Count original cast/ability commands once, before area expansion."""
        for actor_id, model in self.models.items():
            activation = model["activation"]
            if activation is None:
                continue
            for command in commands:
                if command["kind"] == "deploy":
                    continue
                command_id = command["id"]
                if command_id not in activation["command_weights"]:
                    raise InputError(
                        f"Eagle activation has no explicit weight for command {command_id}"
                    )
                if command_id in self.counted_commands[actor_id]:
                    continue
                self.counted_commands[actor_id].add(command_id)
                self.states[actor_id]["command_weight"] += activation[
                    "command_weights"
                ][command_id]

    def prepare(self, actors, time, trace):
        for actor_id, model in self.models.items():
            actor = actors[actor_id]
            state = self.states[actor_id]
            if actor["hp"] <= 0 and not state["destroyed"]:
                state["destroyed"] = True
                if state["next_shell_index"]:
                    remaining = model["shots_per_burst"] - state["next_shell_index"]
                    state["cancelled_shells"] += remaining
                    trace.append(
                        {
                            "time_seconds": time,
                            "event": "indirect_burst_cancelled",
                            "source": actor_id,
                            "unreleased_shells": remaining,
                            "reason": "source_destroyed",
                        }
                    )
                state["next_shell_index"] = 0
                state["burst_primary"] = None
            activation = model["activation"]
            if activation is None:
                continue
            for cast_id, start in self.paid_casts.items():
                if (
                    start <= time + EPSILON
                    and cast_id not in self.counted_commands[actor_id]
                ):
                    self.counted_commands[actor_id].add(cast_id)
                    state["command_weight"] += activation["command_weights"][cast_id]
            for target in actors.values():
                if target["kind"] != "unit" or target["team"] == actor["team"]:
                    continue
                target_id = target["id"]
                if target_id not in activation["actor_weights"]:
                    raise InputError(
                        "New opposing unit has no explicit Eagle contribution weight"
                    )
                spawn = target["spawn_seconds"]
                if (
                    spawn != "controlled"
                    and spawn <= time + EPSILON
                    and target_id not in self.counted_actors[actor_id]
                ):
                    self.counted_actors[actor_id].add(target_id)
                    state["actor_weight"] += activation["actor_weights"][target_id]
            state["total_weight"] = state["actor_weight"] + state["command_weight"]
            if (
                not state["activated"]
                and not state["destroyed"]
                and state["total_weight"] + EPSILON >= activation["threshold"]
            ):
                state["activated"] = True
                state["activation_time"] = time
                actor["next_attack"] = max(
                    actor["next_attack"],
                    max(time, actor["frozen_until"])
                    + activation["delay_seconds"] / attack_rate(actor),
                )
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "eagle_activated",
                        "source": actor_id,
                        "actor_weight": state["actor_weight"],
                        "command_weight": state["command_weight"],
                        "total_weight": state["total_weight"],
                        "threshold": activation["threshold"],
                        "first_shell_ready_seconds": actor["next_attack"],
                    }
                )

    @staticmethod
    def _acquirable(actor, target, time):
        return (
            target is not None
            and _eligible(actor, target, time)
            and actor["_minimum_range"] - EPSILON
            <= target_distance(center(actor), target)
            <= actor["range"] + EPSILON
        )

    def select_target(self, actor, actors, time, blocked, width, height):
        actor_id = actor["id"]
        if actor_id not in self.models:
            return self.ordinary_select_target(
                actor, actors, time, blocked, width, height
            )
        model = self.models[actor_id]
        state = self.states[actor_id]
        if not _active(actor, time) or not state["activated"]:
            actor["target"] = None
            return None, None
        retained = actors.get(state["burst_primary"])
        if state["next_shell_index"] and self._acquirable(actor, retained, time):
            actor["target"] = retained["id"]
            return retained, []
        if model["kind"] == "mortar":
            return self.ordinary_select_target(
                actor, actors, time, blocked, width, height
            )
        candidates = [
            target
            for target in actors.values()
            if self._acquirable(actor, target, time)
        ]
        targeting = model["targeting"]
        hp_field = "hp" if targeting["hitpoint_basis"] == "current" else "maximum_hp"
        choices = []
        for candidate in candidates:
            point = center(candidate)
            density = sum(
                target[hp_field]
                for target in candidates
                if hypot(center(target)[0] - point[0], center(target)[1] - point[1])
                <= targeting["radius_tiles"] + EPSILON
            )
            choices.append(
                (
                    -density,
                    target_distance(center(actor), candidate),
                    candidate["id"],
                    candidate,
                )
            )
        target = min(choices, key=lambda choice: choice[:3])[-1] if choices else None
        actor["target"] = target["id"] if target else None
        return (target, []) if target else (None, None)

    def launch(self, actor, primary, actors, time, trace):
        actor_id = actor["id"]
        model = self.models[actor_id]
        state = self.states[actor_id]
        if (
            not _active(actor, time)
            or not state["activated"]
            or actor["frozen_until"] > time + EPSILON
            or actor["next_attack"] > time + EPSILON
            or not self._acquirable(actor, primary, time)
        ):
            return
        index = state["next_shell_index"]
        if index == 0:
            state["burst_number"] += 1
        state["burst_primary"] = primary["id"]
        self.combat.launch(
            actor,
            primary,
            actors,
            time,
            trace,
            weapon_state={
                "kind": model["kind"],
                "burst_number": state["burst_number"],
                "shell_number": index + 1,
                "shells_per_burst": model["shots_per_burst"],
            },
        )
        state["launched_shells"] += 1
        state["next_shell_index"] = (index + 1) % model["shots_per_burst"]
        interval = (
            model["inter_shot_seconds"]
            if state["next_shell_index"]
            else model["post_burst_seconds"]
        )
        actor["next_attack"] = time + interval / attack_rate(actor)
        if state["next_shell_index"] == 0:
            state["burst_primary"] = None

    def frame(self, actor):
        if actor["id"] not in self.states:
            return {}
        state = self.states[actor["id"]]
        return {
            "indirect_activated": state["activated"],
            "indirect_next_shell_index": state["next_shell_index"],
            "indirect_burst_number": state["burst_number"],
            "eagle_cumulative_weight": state["total_weight"],
        }

    def result(self):
        return {
            "states": deepcopy(self.states),
            "counted_actor_ids": {
                key: sorted(value) for key, value in self.counted_actors.items()
            },
            "counted_command_ids": {
                key: sorted(value) for key, value in self.counted_commands.items()
            },
            "full_game_prediction": False,
        }
