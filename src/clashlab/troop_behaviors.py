"""Reusable attacking targeting, concealment, finite ammunition and moving ramps.

This module is an opt-in experimental adapter. It refuses missing contracts and
does not promote catalog presence into battle support. Movement callers must use
the returned route and honor the burrow response flags in damage/trap dispatch.
"""

from copy import deepcopy

from .common import InputError, identifier, integer, number, require
from .spatial import EPSILON, _active, center, target_distance


BEHAVIOR_ENTITIES = frozenset(
    {
        "goblin",
        "sneaky-goblin",
        "super-giant",
        "wall-breaker",
        "miner",
        "super-miner",
        "super-minion",
        "inferno-dragon",
    }
)
FEATURES = {
    "goblin": {"resource"},
    "sneaky-goblin": {"resource", "cloak"},
    "super-giant": {"defense", "wall_bonus"},
    "wall-breaker": {"wall", "suicide"},
    "miner": {"burrow"},
    "super-miner": {"burrow", "ramp"},
    "super-minion": {"ammunition"},
    "inferno-dragon": {"ramp"},
}


def compile_troop_behavior(actor, instance, entity, row, modifiers):
    entity_id = entity["id"]
    if entity_id not in BEHAVIOR_ENTITIES or actor.get("team") != "attack":
        raise InputError("Behavior requires a registered attacking troop")
    parameters = deepcopy(require(instance, "troop_behavior_parameters"))
    if set(parameters) != {"source", "status", "features"}:
        raise InputError(
            "Troop behavior requires source, status and exact feature contracts"
        )
    identifier(parameters["source"], "troop behavior evidence")
    if (
        parameters["status"] != "explicit_uncalibrated_hypothesis"
        or set(parameters["features"]) != FEATURES[entity_id]
    ):
        raise InputError("Troop features or experimental status disagree with identity")
    for feature, values in parameters["features"].items():
        expected = {
            "resource": {"entity_ids", "damage_multiplier", "selection"},
            "cloak": {"duration_seconds", "clock", "collision"},
            "defense": {"selection"},
            "wall_bonus": {"damage_multiplier"},
            "wall": {"selection"},
            "suicide": {"trigger", "death_damage_policy"},
            "burrow": {"transition", "damage", "traps", "wall_policy"},
            "ramp": {"stage_seconds", "freeze", "protection", "clock"},
            "ammunition": {"shots", "range_tiles", "damage_multiplier", "consumption"},
        }[feature]
        if not isinstance(values, dict) or set(values) != expected:
            raise InputError("Incomplete troop feature: " + feature)
        if feature == "resource":
            if (
                values["selection"] != "nearest_reachable_preferred_then_ordinary"
                or not isinstance(values["entity_ids"], list)
                or not values["entity_ids"]
                or len(set(values["entity_ids"])) != len(values["entity_ids"])
            ):
                raise InputError(
                    "Resource targeting requires explicit unique identities and reachable fallback"
                )
            for key in values["entity_ids"]:
                identifier(key, "resource entity identity")
            number(values["damage_multiplier"], "resource damage bonus", EPSILON)
        elif feature == "cloak":
            number(values["duration_seconds"], "deployment cloak duration", EPSILON)
            if (
                values["clock"] != "first_deployment_continues_frozen"
                or values["collision"] != "unchanged"
            ):
                raise InputError("Unsupported deployment cloak policy")
        elif feature in {"defense", "wall"}:
            if values["selection"] != "nearest_reachable_preferred_then_ordinary":
                raise InputError("Target preference requires reachable fallback")
            if feature == "wall":
                actor["target_priorities"] = ["wall", "defense", "building"]
                actor["target_priority_tiers"] = [["wall"], ["defense", "building"]]
                actor["attack_model"]["target_kinds"] = ["wall", "defense", "building"]
        elif feature == "wall_bonus":
            number(values["damage_multiplier"], "wall damage bonus", EPSILON)
            wall = require(actor, "wall_behavior")
            if wall["kind"] != "clear_obstructions":
                raise InputError("Super Giant requires a shared wall clearing weapon")
            wall["weapon"]["damage"] *= values["damage_multiplier"]
        elif feature == "suicide":
            if values != {
                "trigger": "successful_weapon_launch_once",
                "death_damage_policy": "released_attack_only_suppress_death_blast_on_suicide",
            }:
                raise InputError(
                    "Wall Breaker self destruction must avoid a duplicated explosion"
                )
        elif feature == "burrow":
            if values != {
                "transition": "burrow_when_out_of_weapon_range_surface_in_range",
                "damage": "immune_underground_including_existing_projectiles",
                "traps": "do_not_trigger_underground",
                "wall_policy": "ignore_enemy_walls_preserve_other_obstacles",
            }:
                raise InputError("Unsupported experimental burrow response")
            actor["wall_behavior"] = {
                "kind": "jump_enemy_walls",
                "source": parameters["source"],
            }
        elif feature == "ramp":
            times = values["stage_seconds"]
            if (
                not isinstance(times, list)
                or len(times) != 3
                or times[0] != 0
                or not times[0] < times[1] < times[2]
            ):
                raise InputError(
                    "Moving ramp needs three increasing stage clocks starting at zero"
                )
            for value in times:
                number(value, "moving ramp stage time", 0)
            if (
                values["clock"] != "first_launch_same_target_in_range"
                or values["freeze"] not in {"reset", "pause"}
                or values["protection"] not in {"reset", "pause", "continue"}
            ):
                raise InputError("Moving ramp interruption policy must be explicit")
            parameters["ramp_damage"] = [
                number(
                    require(require(row, "stats"), mode)["dps"],
                    "catalog moving ramp DPS",
                    EPSILON,
                )
                * number(
                    require(entity, "attackSpeed"),
                    "catalog ramp pulse cadence",
                    EPSILON,
                )
                * modifiers["damage_multiplier"]
                for mode in ("normal", "stage2", "stage3")
            ]
            actor["damage"] = parameters["ramp_damage"][0]
        elif feature == "ammunition":
            integer(values["shots"], "long range shots", 1)
            number(values["range_tiles"], "long shot range", actor["range"])
            number(values["damage_multiplier"], "long shot damage multiplier", EPSILON)
            if values["consumption"] != "weapon_launch_including_fizzled_projectiles":
                raise InputError("Finite ammunition must be consumed on release")
    actor["troop_behavior_model"] = parameters
    return actor


def troop_damage_multiplier(source, recipient):
    feature = source.get("troop_behavior_model", {}).get("features", {}).get("resource")
    if (
        feature
        and recipient.get("entity_adapter", {}).get("entity") in feature["entity_ids"]
    ):
        return feature["damage_multiplier"]
    return 1.0


def troop_damage_immune(actor):
    """Damage receipt and trap owners must consult this before health settlement."""
    return actor.get("_troop_burrowed", False)


class AttackingTroopCombat:
    def __init__(self, actors):
        self.actors = actors
        self.models = {
            key: deepcopy(actor["troop_behavior_model"])
            for key, actor in actors.items()
            if "troop_behavior_model" in actor
        }
        self.states = {
            key: {
                "deployed_at": None,
                "shots": 0,
                "base_range": actors[key]["range"],
                "base_damage": actors[key]["damage"],
                "target": None,
                "elapsed": 0.0,
                "last_time": None,
                "running": False,
                "launched": False,
                "retired": False,
            }
            for key in self.models
        }
        self.events = []

    def select_target(
        self, actor, actors, time, blocked, width, height, ordinary_selector
    ):
        model = self.models.get(actor["id"])
        if model is None:
            return ordinary_selector(actor, actors, time, blocked, width, height)
        features = model["features"]
        preferred = {}
        for key, candidate in actors.items():
            if candidate["team"] == actor["team"] or not _active(candidate, time):
                continue
            entity = candidate.get("entity_adapter", {}).get("entity")
            if (
                (
                    "resource" in features
                    and entity in features["resource"]["entity_ids"]
                )
                or ("defense" in features and candidate["kind"] == "defense")
                or ("wall" in features and candidate["kind"] == "wall")
            ):
                preferred[key] = candidate
        if preferred:
            candidates = {
                key: candidate
                for key, candidate in actors.items()
                if candidate["team"] == actor["team"] or key in preferred
            }
            selected = ordinary_selector(
                actor, candidates, time, blocked, width, height
            )
            if selected[0] is not None:
                return selected
        return ordinary_selector(actor, actors, time, blocked, width, height)

    def prepare(self, time, select_target, trace):
        for key, model in self.models.items():
            actor, state, features = (
                self.actors[key],
                self.states[key],
                model["features"],
            )
            if not _active(actor, time):
                actor["_troop_burrowed"] = False
                state["running"] = False
                continue
            if state["deployed_at"] is None:
                state["deployed_at"] = actor["spawn_seconds"]
            if "cloak" in features:
                actor["_untargetable_until"] = max(
                    actor.get("_untargetable_until", 0),
                    state["deployed_at"] + features["cloak"]["duration_seconds"],
                )
            if "ammunition" in features:
                actor["range"] = (
                    features["ammunition"]["range_tiles"]
                    if state["shots"] < features["ammunition"]["shots"]
                    else state["base_range"]
                )
            target = select_target(actor)
            in_range = (
                target is not None
                and target_distance(center(actor), target) <= actor["range"] + EPSILON
            )
            if "burrow" in features:
                burrowed = target is not None and not in_range
                if burrowed != actor.get("_troop_burrowed", False):
                    event = {
                        "time_seconds": time,
                        "event": "troop_burrow" if burrowed else "troop_emerge",
                        "source": key,
                    }
                    trace.append(event)
                    self.events.append(deepcopy(event))
                actor["_troop_burrowed"] = burrowed
                actor["_troop_trap_eligible"] = not burrowed
            if "ramp" not in features:
                continue
            if state["running"] and state["last_time"] is not None:
                state["elapsed"] += time - state["last_time"]
            state["last_time"] = time
            target_id = target["id"] if in_range else None
            policy = "continue"
            if actor.get("frozen_until", 0) > time + EPSILON:
                policy = features["ramp"]["freeze"]
            elif in_range and target.get("immune_until", 0) > time + EPSILON:
                policy = features["ramp"]["protection"]
            if target_id != state["target"] or policy == "reset":
                state["elapsed"] = 0.0
                state["launched"] = False
            state["target"] = target_id
            state["running"] = in_range and state["launched"] and policy == "continue"

    def launch_damage(self, actor_id):
        model, state = self.models[actor_id], self.states[actor_id]
        features = model["features"]
        damage = state["base_damage"]
        if "ramp" in features:
            stage = max(
                index
                for index, after in enumerate(features["ramp"]["stage_seconds"])
                if after <= state["elapsed"] + EPSILON
            )
            damage = model["ramp_damage"][stage]
        if (
            "ammunition" in features
            and state["shots"] < features["ammunition"]["shots"]
        ):
            damage *= features["ammunition"]["damage_multiplier"]
        return damage

    def on_launch(self, actor_id, time, trace):
        state, model, actor = (
            self.states[actor_id],
            self.models[actor_id],
            self.actors[actor_id],
        )
        state["shots"] += 1
        state["launched"] = True
        state["running"] = "ramp" in model["features"]
        state["last_time"] = time
        if "suicide" in model["features"] and not state["retired"]:
            state["retired"] = True
            actor["hp"] = 0
            actor["death_time"] = time
            actor["_troop_suicide_attack"] = True
            trace.append(
                {
                    "time_seconds": time,
                    "event": "wall_breaker_attack_retirement",
                    "source": actor_id,
                }
            )

    def next_boundary(self, time):
        boundaries = []
        for key, model in self.models.items():
            state = self.states[key]
            if not _active(self.actors[key], time):
                continue
            if "cloak" in model["features"] and state["deployed_at"] is not None:
                boundaries.append(
                    state["deployed_at"]
                    + model["features"]["cloak"]["duration_seconds"]
                )
            if state["running"]:
                boundaries.extend(
                    time + (after - state["elapsed"])
                    for after in model["features"]["ramp"]["stage_seconds"]
                    if after > state["elapsed"]
                )
        return min((value for value in boundaries if value > time), default=None)

    def result(self):
        return {
            "status": "EXPLICIT_UNCALIBRATED_ATTACKING_TROOP_BEHAVIORS",
            "states": deepcopy(self.states),
            "events": deepcopy(self.events),
        }
