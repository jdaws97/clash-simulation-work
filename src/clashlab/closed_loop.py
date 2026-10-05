"""Empirical human responses coupled to the restricted spatial kernel.

These controls recompute cues after prior decisions change combat. They do not
establish real Clash visibility, mechanics, or player reaction distributions.
"""

from copy import deepcopy
from random import Random

from .common import InputError, identifier, integer, number, require
from .combat import AREA_EFFECTS, RULESET as PATTERN_RULESET, validate_area_effect
from .spatial import EPSILON, _active, center, simulate_spatial, target_distance
from .walls import RULESET as WALL_RULESET
from .healing import (
    AREA_COMMANDS as HEALING_AREA_COMMANDS,
    RULESET as SUPPORT_RULESET,
    validate_healing_field,
)
from .ramping import RULESET as RAMP_RULESET
from .deaths import RULESET as DEATH_RULESET
from .townhalls import RULESET as TOWN_HALL_RULESET
from .defense_patterns import RULESET as AREA_DEFENSE_RULESET
from .heroes import RULESET as HERO_RULESET, validate_ability_command
from .artillery import RULESET as ARTILLERY_RULESET
from .traps import RULESET as TRAP_RULESET
from .hit_status import RULESET as HIT_RULESET
from .engine_rules import RULESET as EXTENDED_RULESET
from .buff_rules import RULESET as BUFF_RULESET
from .indirect_rules import RULESET as INDIRECT_RULESET
from .sweeper_rules import RULESET as SWEEPER_RULESET
from .defending_hero_rules import RULESET as DEFENDING_HERO_RULESET
from .spell_tower_rules import RULESET as SPELL_TOWER_RULESET
from .builder_rules import RULESET as BUILDER_RULESET
from .garrison_rules import RULESET as GARRISON_RULESET
from .firespitter_rules import RULESET as FIRESPITTER_RULESET
from .trap_lifecycle_rules import RULESET as TRAP_LIFECYCLE_RULESET
from .guardian_rules import RULESET as GUARDIAN_RULESET
from .siege_rules import RULESET as SIEGE_RULESET
from .pet_rules import RULESET as PET_RULESET
from .advanced_defense_rules import RULESET as ADVANCED_DEFENSE_RULESET
from .hero_roster_rules import RULESET as HERO_ROSTER_RULESET
from .termination_rules import RULESET as TERMINATION_RULESET
from .attack_spell_rules import RULESET as ATTACK_SPELL_RULESET
from .hero_pets import validate_pet_deployment
from .garrisons import validate_garrison_deployment
from .reinforcements import validate_reinforcement_deployment


CONTROL_RULES = {
    "observation_phase": "before_commands_and_hits",
    "stream_transition": "next_observation_after_command_resolution",
    "resource_contention": "due_time_then_action_id",
    "pending_cue": "latched_with_explicit_execution_recheck",
}
ACTOR_FIELDS = {
    "hp",
    "hp_fraction",
    "alive",
    "active",
    "x",
    "y",
    "distance_to_actor",
    "target_actor",
}
AREA_KINDS = set(AREA_EFFECTS) | HEALING_AREA_COMMANDS
EFFECT_KINDS = {
    "damage",
    "heal",
    "freeze",
    "invulnerability",
    "deploy",
    "hero_ability",
    "clan_castle_deploy",
    "siege_release",
} | AREA_KINDS


def _condition_value(condition, actors, time):
    field = condition["field"]
    if field == "time_seconds":
        return time
    actor = actors[condition["actor_id"]]
    if field == "target_actor":
        target = actors.get(actor["target"])
        return (
            actor["target"]
            if _active(actor, time) and target is not None and _active(target, time)
            else None
        )
    if field == "alive":
        return actor["hp"] > 0
    if field == "active":
        return _active(actor, time)
    if field == "hp_fraction":
        return actor["hp"] / actor["maximum_hp"]
    if field == "distance_to_actor":
        return target_distance(center(actor), actors[condition["other_actor_id"]])
    return actor[field]


def _matches(condition, actors, time):
    actual = _condition_value(condition, actors, time)
    expected = condition["value"]
    if condition["operator"] == "equals":
        return actual == expected
    if condition["operator"] == "at_least":
        return actual >= expected
    return actual <= expected


def _validate_condition(condition, actor_ids):
    field = require(condition, "field")
    if field not in ACTOR_FIELDS | {"time_seconds"}:
        raise InputError(f"Unsupported coupled cue field: {field}")
    if field != "time_seconds" and require(condition, "actor_id") not in actor_ids:
        raise InputError("Cue references an unknown actor")
    if field == "distance_to_actor":
        if require(condition, "other_actor_id") not in actor_ids:
            raise InputError("Distance cue references an unknown actor")
    operator = require(condition, "operator")
    if operator not in {"equals", "at_least", "at_most"}:
        raise InputError("Unsupported coupled cue operator")
    expected = require(condition, "value")
    if field == "target_actor":
        if (
            operator != "equals"
            or not isinstance(expected, str)
            or expected not in actor_ids
        ):
            raise InputError(
                "Target-lock cues require equality with a known actor instance"
            )
    elif field in {"alive", "active"}:
        if operator != "equals" or not isinstance(expected, bool):
            raise InputError("Boolean cues need an explicit boolean equality")
    else:
        number(expected, "cue threshold")


class SpatialController:
    """One sampled joint response trace and explicit finite action resources."""

    def __init__(self, plan, episode, actor_specs):
        self.plan = deepcopy(plan)
        self.episode = deepcopy(episode)
        self.interval = number(
            require(plan, "observation_interval_seconds"),
            "observation interval",
            EPSILON,
        )
        if require(plan, "control_rules") != CONTROL_RULES:
            raise InputError("All coupled control conventions must be explicit")
        self.failed_transition = require(plan, "failed_action_transition")
        if self.failed_transition not in {"advance", "stop_stream"}:
            raise InputError("Failed actions need an explicit stream transition")
        self.resources = deepcopy(require(plan, "resources"))
        for resource, capacity in self.resources.items():
            identifier(resource, "resource name")
            number(capacity, "resource capacity", 0)
        self.actor_specs = {actor["id"]: actor for actor in actor_specs}
        self.streams = require(self.plan, "streams")
        if not self.streams:
            raise InputError("Coupled controls need action streams")
        self.actions = {}
        stream_ids = set()
        for stream in self.streams:
            stream_id = identifier(require(stream, "id"), "stream id")
            if stream_id in stream_ids or not require(stream, "steps"):
                raise InputError("Streams must be unique and contain steps")
            stream_ids.add(stream_id)
            for step in stream["steps"]:
                self._validate_step(step)
        self._validate_episode()
        self.cursors = {stream["id"]: 0 for stream in self.streams}
        self.waiting = set()
        self.stopped = set()
        self.pending = []
        self.next_observation = 0.0
        self.log = []
        self.observations = []

    def _validate_step(self, step):
        conditions = require(step, "all_conditions")
        if not conditions:
            raise InputError("Actions need explicit readiness conditions")
        for condition in conditions:
            _validate_condition(condition, set(self.actor_specs))
        action = require(step, "action")
        action_id = identifier(require(action, "id"), "action id")
        if action_id in self.actions:
            raise InputError("Coupled action IDs must be unique")
        kind = require(action, "kind")
        if kind not in EFFECT_KINDS:
            raise InputError(
                "Unsupported coupled action; a mechanic adapter is required"
            )
        if kind == "hero_ability":
            validate_ability_command(action, self.actor_specs)
            active_condition = {
                "actor_id": action["hero_id"],
                "field": "active",
                "operator": "equals",
                "value": True,
            }
            if (
                active_condition not in conditions
                or action.get("recheck_conditions_on_execution") is not True
            ):
                raise InputError(
                    "Human hero activation must recheck an explicit active-hero cue"
                )
        elif kind == "siege_release":
            target = require(action, "target")
            if (
                target not in self.actor_specs
                or "siege_model" not in self.actor_specs[target]
            ):
                raise InputError("Manual siege release requires a declared carrier")
            active_condition = {
                "actor_id": target,
                "field": "active",
                "operator": "equals",
                "value": True,
            }
            if (
                active_condition not in conditions
                or action.get("recheck_conditions_on_execution") is not True
            ):
                raise InputError(
                    "Manual siege release must recheck its active-carrier cue"
                )
        elif kind == "clan_castle_deploy":
            identifier(require(action, "group_id"), "attacking reinforcement group")
            position = require(action, "position")
            if set(position) != {"x", "y"}:
                raise InputError(
                    "Direct reinforcement controls need one deployment point"
                )
            number(position["x"], "reinforcement deployment x", 0)
            number(position["y"], "reinforcement deployment y", 0)
        elif kind in AREA_KINDS:
            if "targets" in action:
                raise InputError("Area membership must be recomputed, not preselected")
            validator = (
                validate_healing_field
                if kind in HEALING_AREA_COMMANDS
                else validate_area_effect
            )
            validator({**action, "time_seconds": 0}, self.actor_specs)
        else:
            targets = require(action, "targets")
            if (
                not targets
                or len(targets) != len(set(targets))
                or not set(targets) <= set(self.actor_specs)
            ):
                raise InputError("Actions need unique known target instances")
            if kind in {"damage", "heal"}:
                number(require(action, "amount"), "action amount", 0)
            elif kind in {"freeze", "invulnerability"}:
                number(require(action, "duration_seconds"), "action duration", EPSILON)
            elif any(
                self.actor_specs[target]["spawn_seconds"] != "controlled"
                for target in targets
            ):
                raise InputError("Deploy actions need controlled undeployed actors")
        validate_garrison_deployment(action, self.actor_specs)
        validate_reinforcement_deployment(action, self.actor_specs)
        validate_pet_deployment(action, self.actor_specs)
        if not isinstance(require(action, "recheck_conditions_on_execution"), bool):
            raise InputError("Execution cue rechecking must be explicit")
        for resource, amount in require(action, "cost").items():
            if resource not in self.resources:
                raise InputError(f"Undeclared action resource: {resource}")
            number(amount, "action resource cost", 0)
        self.actions[action_id] = action

    def _validate_episode(self):
        identifier(require(self.episode, "source_replay"), "response trace source")
        responses = require(self.episode, "responses")
        if set(responses) != set(self.actions):
            raise InputError(
                "Each joint response trace must cover every intended action"
            )
        for action_id, response in responses.items():
            number(require(response, "latency_seconds"), "observed response latency", 0)
            if not isinstance(require(response, "missed"), bool):
                raise InputError("Missed response must be an observed boolean")
            errors = require(response, "placement_errors")
            action = self.actions[action_id]
            if action["kind"] == "deploy":
                required_targets = set(action["targets"])
            elif action["kind"] == "clan_castle_deploy":
                required_targets = {"position"}
            elif action["kind"] in AREA_KINDS:
                required_targets = {"area"}
            else:
                required_targets = set()
            if set(errors) != required_targets:
                raise InputError(
                    "Deployment/area needs explicit observed placement errors"
                )
            for error in errors.values():
                number(require(error, "dx"), "observed horizontal placement error")
                number(require(error, "dy"), "observed vertical placement error")

    def _observe(self, time, actors):
        observation = {"time_seconds": time, "cues": {}}
        for stream in self.streams:
            stream_id = stream["id"]
            cursor = self.cursors[stream_id]
            if (
                stream_id in self.waiting
                or stream_id in self.stopped
                or cursor >= len(stream["steps"])
            ):
                continue
            step = stream["steps"][cursor]
            action = step["action"]
            ready = all(
                _matches(condition, actors, time)
                for condition in step["all_conditions"]
            )
            observation["cues"][action["id"]] = ready
            if not ready:
                continue
            response = self.episode["responses"][action["id"]]
            self.pending.append(
                {
                    "stream_id": stream_id,
                    "step": step,
                    "cue_time_seconds": time,
                    "time_seconds": time + response["latency_seconds"],
                    "response": response,
                }
            )
            self.waiting.add(stream_id)
        self.observations.append(observation)
        while self.next_observation <= time + EPSILON:
            self.next_observation += self.interval

    def _resolve(self, pending, time, actors):
        action = pending["step"]["action"]
        response = pending["response"]
        conditions = pending["step"]["all_conditions"]
        status = "command_applied"
        if response["missed"]:
            status = "missed"
        elif action["recheck_conditions_on_execution"] and not all(
            _matches(condition, actors, time) for condition in conditions
        ):
            status = "cue_no_longer_valid"
        elif any(self.resources[key] < value for key, value in action["cost"].items()):
            status = "resources_exhausted"
        command = None
        if status == "command_applied":
            for resource, amount in action["cost"].items():
                self.resources[resource] -= amount
            command = deepcopy(action)
            command["time_seconds"] = time
            if action["kind"] in {"clan_castle_deploy", "siege_release"}:
                command.pop("cost")
                command.pop("recheck_conditions_on_execution")
            if action["kind"] == "deploy":
                command["positions"] = {
                    target: {
                        "x": self.actor_specs[target]["x"]
                        + response["placement_errors"][target]["dx"],
                        "y": self.actor_specs[target]["y"]
                        + response["placement_errors"][target]["dy"],
                    }
                    for target in action["targets"]
                }
            elif action["kind"] in AREA_KINDS:
                error = response["placement_errors"]["area"]
                command["area"]["x"] += error["dx"]
                command["area"]["y"] += error["dy"]
            elif action["kind"] == "clan_castle_deploy":
                error = response["placement_errors"]["position"]
                command["position"]["x"] += error["dx"]
                command["position"]["y"] += error["dy"]
        stream_id = pending["stream_id"]
        self.waiting.remove(stream_id)
        self.cursors[stream_id] += 1
        if status != "command_applied" and self.failed_transition == "stop_stream":
            self.stopped.add(stream_id)
        action_log = {
            "action_id": action["id"],
            "stream_id": stream_id,
            "cue_time_seconds": pending["cue_time_seconds"],
            "time_seconds": time,
            "status": status,
            "remaining_resources": deepcopy(self.resources),
        }
        if command is not None:
            if "area" in command:
                action_log["commanded_area"] = deepcopy(command["area"])
            elif "positions" in command:
                action_log["commanded_positions"] = deepcopy(command["positions"])
            elif "position" in command:
                action_log["commanded_position"] = deepcopy(command["position"])
        self.log.append(action_log)
        return command

    def commands(self, time, actors):
        if time >= self.next_observation - EPSILON:
            self._observe(time, actors)
        due = [item for item in self.pending if item["time_seconds"] <= time + EPSILON]
        self.pending = [
            item for item in self.pending if item["time_seconds"] > time + EPSILON
        ]
        due.sort(key=lambda item: (item["time_seconds"], item["step"]["action"]["id"]))
        commands = []
        for pending in due:
            command = self._resolve(pending, time, actors)
            if command is not None:
                commands.append(command)
        return commands

    def next_boundary(self):
        return min(
            [self.next_observation, *[item["time_seconds"] for item in self.pending]]
        )

    def result(self):
        return {
            "actions": self.log,
            "observations": self.observations,
            "remaining_resources": self.resources,
            "actions_pending_at_horizon": [
                item["step"]["action"]["id"] for item in self.pending
            ],
            "unresolved_actions": [
                step["action"]["id"]
                for stream in self.streams
                for step in stream["steps"][self.cursors[stream["id"]] :]
            ],
        }


def simulate_closed_loop(scene, plan, profile, seed, trials):
    plan_id = identifier(require(plan, "id"), "coupled plan id")
    if require(profile, "plan_id") != plan_id:
        raise InputError("Response traces must match the intended coupled plan")
    episodes = require(profile, "observed_latency_traces")
    if not episodes:
        raise InputError(
            "No measured response traces; no human distribution is invented"
        )
    for episode in episodes:
        validator = SpatialController(plan, episode, require(scene, "actors"))
        if require(scene, "ruleset") not in {
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        } and any(
            action["kind"] in {"clan_castle_deploy", "siege_release"}
            for action in validator.actions.values()
        ):
            raise InputError("Reinforcement controls require the explicit v24 ruleset")
        if require(scene, "ruleset") not in {
            PATTERN_RULESET,
            WALL_RULESET,
            SUPPORT_RULESET,
            RAMP_RULESET,
            DEATH_RULESET,
            TOWN_HALL_RULESET,
            AREA_DEFENSE_RULESET,
            HERO_RULESET,
            ARTILLERY_RULESET,
            TRAP_RULESET,
            HIT_RULESET,
            EXTENDED_RULESET,
            BUFF_RULESET,
            INDIRECT_RULESET,
            SWEEPER_RULESET,
            DEFENDING_HERO_RULESET,
            SPELL_TOWER_RULESET,
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        } and any(
            action["kind"] in AREA_KINDS for action in validator.actions.values()
        ):
            raise InputError(
                "Unsupported area control for the selected spatial ruleset"
            )
        if require(scene, "ruleset") not in {
            SUPPORT_RULESET,
            RAMP_RULESET,
            DEATH_RULESET,
            TOWN_HALL_RULESET,
            AREA_DEFENSE_RULESET,
            HERO_RULESET,
            ARTILLERY_RULESET,
            TRAP_RULESET,
            HIT_RULESET,
            EXTENDED_RULESET,
            BUFF_RULESET,
            INDIRECT_RULESET,
            SWEEPER_RULESET,
            DEFENDING_HERO_RULESET,
            SPELL_TOWER_RULESET,
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        } and any(
            action["kind"] in HEALING_AREA_COMMANDS
            for action in validator.actions.values()
        ):
            raise InputError("Persistent healing controls require the support ruleset")
        if require(scene, "ruleset") not in {
            HERO_RULESET,
            ARTILLERY_RULESET,
            TRAP_RULESET,
            HIT_RULESET,
            EXTENDED_RULESET,
            BUFF_RULESET,
            INDIRECT_RULESET,
            SWEEPER_RULESET,
            DEFENDING_HERO_RULESET,
            SPELL_TOWER_RULESET,
            BUILDER_RULESET,
            GARRISON_RULESET,
            FIRESPITTER_RULESET,
            TRAP_LIFECYCLE_RULESET,
            GUARDIAN_RULESET,
            SIEGE_RULESET,
            PET_RULESET,
            ADVANCED_DEFENSE_RULESET,
            HERO_ROSTER_RULESET,
            TERMINATION_RULESET,
            ATTACK_SPELL_RULESET,
        } and any(
            action["kind"] == "hero_ability" for action in validator.actions.values()
        ):
            raise InputError("Hero ability controls require the hero/equipment ruleset")
    random = Random(integer(seed, "seed", 0))
    samples = []
    for trial in range(integer(trials, "trials", 1)):
        episode = random.choice(episodes)
        controller = SpatialController(plan, episode, scene["actors"])
        result = simulate_spatial(scene, controller)
        samples.append(
            {
                "trial": trial,
                "source_trace": episode["source_replay"],
                "control": controller.result(),
                "combat": result,
            }
        )
    return {
        "status": "CLOSED_LOOP_SPATIAL_EXPERIMENT_NOT_VALIDATED_CLASH_BATTLE",
        "plan_id": plan_id,
        "observations_are_recomputed_after_interventions": True,
        "full_game_prediction": False,
        "samples": samples,
        "limitations": [
            "Only the explicitly selected restricted spatial mechanics are simulated",
            "Kernel health/position/target-lock observations are not a verified model of player visibility",
            "Empirical response traces must match the intended plan; synthetic traces establish no player distribution",
            "Fixed-point area commands recompute membership at execution; persistent/moving auras and verified spell/equipment adapters remain required",
            "Deployment zones and game input constraints still require verification",
        ],
    }
