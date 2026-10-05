"""Finite observation gates over already admitted paid battle entitlements."""

from copy import deepcopy
from math import ceil, inf

from .common import InputError, identifier, number
from .spatial import _active


CAPABILITY = "paid-observation-scheduler-v1"
POLICIES = {
    "status": "explicit_uncalibrated_hypothesis",
    "same_time_settlement": "observe_before_commands_recheck_then_release_once",
    "clock_rounding": "exact_representable_deadlines_no_epsilon_early_release",
    "spell_timing": "preserve_relative_impact_and_recall_return_delays",
}
COLLECTIONS = {
    "entities",
    "effects",
    "freeze_spells",
    "healing_spells",
    "buff_spells",
    "attack_spells",
}


def exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise InputError(label + " requires exactly " + ", ".join(sorted(fields)))


def conditions(values, actors, limit):
    if not isinstance(values, list) or not 1 <= len(values) <= 16:
        raise InputError("Paid cues require 1..16 conditions")
    for cue in values:
        field = cue.get("field") if isinstance(cue, dict) else None
        if field not in {
            "time_seconds",
            "alive",
            "active",
            "hp_fraction",
            "target_actor",
        }:
            raise InputError("Unsupported paid observation field")
        exact(
            cue,
            {"field", "operator", "value"}
            | ({"actor_id"} if field != "time_seconds" else set()),
            "Paid cue",
        )
        if field != "time_seconds" and (
            not isinstance(cue["actor_id"], str) or cue["actor_id"] not in actors
        ):
            raise InputError("Paid cue references an unknown actor")
        op, value = cue["operator"], cue["value"]
        if op not in {"equals", "at_least", "at_most"}:
            raise InputError("Unsupported paid comparison")
        if field in {"alive", "active"}:
            if op != "equals" or not isinstance(value, bool):
                raise InputError("Paid boolean cues require boolean equality")
        elif field == "target_actor":
            if op != "equals" or not isinstance(value, str) or value not in actors:
                raise InputError("Paid target cues require a known actor equality")
        else:
            number(value, "paid cue value", 0, limit if field == "time_seconds" else 1)


def matches(values, actors, time):
    for cue in values:
        field, expected = cue["field"], cue["value"]
        if field == "time_seconds":
            actual = time
        else:
            actor = actors[cue["actor_id"]]
            if field == "alive":
                actual = actor["hp"] > 0
            elif field == "active":
                actual = _active(actor, time)
            elif field == "hp_fraction":
                actual = actor["hp"] / actor["maximum_hp"]
            else:
                target = actors.get(actor.get("target"))
                actual = (
                    actor["target"]
                    if _active(actor, time)
                    and target is not None
                    and _active(target, time)
                    else None
                )
        op = cue["operator"]
        if not (
            actual == expected
            if op == "equals"
            else actual >= expected if op == "at_least" else actual <= expected
        ):
            return False
    return True


def validate_paid_plan(plan, specification, compiled):
    exact(
        plan,
        {"source", "observation_interval_seconds", "events", "funnel", *POLICIES},
        "Paid observation plan",
    )
    identifier(plan["source"], "paid observation evidence")
    if any(plan[key] != value for key, value in POLICIES.items()):
        raise InputError("Unsupported paid observation policy")
    limit = specification["time_limit_seconds"]
    interval = number(
        plan["observation_interval_seconds"], "observation interval", 1e-10
    )
    if ceil(limit / interval) > 10000:
        raise InputError("Paid observation grid exceeds its 10000-boundary budget")
    scene = specification["entity_scene"]
    actors = {actor["id"] for actor in compiled["scene"]["actors"]}
    scheduled = {}
    for collection in COLLECTIONS:
        for row in scene.get(collection, []):
            if collection == "entities" and (
                row["team"] != "attack" or row["spawn_seconds"] == "controlled"
            ):
                continue
            scheduled[collection, row["id"]] = row
    events = plan["events"]
    if not isinstance(events, list) or not 1 <= len(events) <= 512:
        raise InputError("Paid plan requires 1..512 finite events")
    ids, seen = set(), set()
    for event in events:
        exact(event, {"id", "selector", "at_seconds", "all_conditions"}, "Paid event")
        key = identifier(event["id"], "paid event ID")
        if key in ids:
            raise InputError("Duplicate paid event ID")
        ids.add(key)
        exact(event["selector"], {"collection", "id"}, "Paid selector")
        identifier(event["selector"]["collection"], "paid collection")
        identifier(event["selector"]["id"], "paid action identity")
        selector = event["selector"]["collection"], event["selector"]["id"]
        if selector not in scheduled or selector in seen:
            raise InputError("Paid event requires one unique admitted scheduled action")
        seen.add(selector)
        row = scheduled[selector]
        earliest = number(event["at_seconds"], "paid earliest time", 0, limit)
        if (
            row["spawn_seconds" if selector[0] == "entities" else "time_seconds"]
            != earliest
        ):
            raise InputError("Paid earliest time differs from admitted action")
        conditions(event["all_conditions"], actors, limit)
        for cue in event["all_conditions"]:
            if cue["field"] == "time_seconds" and not matches([cue], {}, earliest):
                raise InputError("Paid clock cue contradicts earliest time")
    if seen != set(scheduled):
        raise InputError(
            "Paid plan must cover every scheduled actor, command and spell"
        )
    funnel = plan["funnel"]
    if not isinstance(funnel, dict) or not isinstance(funnel.get("required"), bool):
        raise InputError("Paid funnel requirement must be explicit")
    if not funnel["required"]:
        exact(funnel, {"required", "reason"}, "Non-funnel control")
        identifier(funnel["reason"], "non-funnel reason")
    else:
        exact(
            funnel,
            {
                "required",
                "prerequisites",
                "commit_event_ids",
                "deadline_seconds",
                "contingencies",
            },
            "Paid funnel",
        )
        conditions(funnel["prerequisites"], actors, limit)
        if all(cue["field"] == "time_seconds" for cue in funnel["prerequisites"]):
            raise InputError("Funnel prerequisites require a battlefield-state cue")
        number(funnel["deadline_seconds"], "funnel deadline", 0, limit)
        commits = funnel["commit_event_ids"]
        if (
            not isinstance(commits, list)
            or not commits
            or not all(isinstance(key, str) for key in commits)
            or len(set(commits)) != len(commits)
            or not set(commits) <= ids
        ):
            raise InputError("Funnel commit IDs must be unique paid events")
        if any(
            event["at_seconds"] > funnel["deadline_seconds"]
            for event in events
            if event["id"] in commits
        ):
            raise InputError("Main commitment cannot start after its funnel deadline")
        branches = funnel["contingencies"]
        if not isinstance(branches, list) or len(branches) != 2:
            raise InputError("Funnel requires both failure and Hall-bait contingencies")
        labels, reserved = set(), set(commits)
        for branch in branches:
            exact(
                branch,
                {"trigger", "all_conditions", "response", "event_ids"},
                "Funnel contingency",
            )
            label = branch["trigger"]
            if label not in {"funnel_failed", "hall_bait_detected"} or label in labels:
                raise InputError("Funnel contingency labels must be distinct")
            labels.add(label)
            conditions(branch["all_conditions"], actors, limit)
            if all(cue["field"] == "time_seconds" for cue in branch["all_conditions"]):
                raise InputError("Funnel contingency requires a battlefield-state cue")
            targets = branch["event_ids"]
            if (
                not isinstance(targets, list)
                or not all(isinstance(key, str) for key in targets)
                or len(set(targets)) != len(targets)
                or not set(targets) <= ids
                or reserved.intersection(targets)
            ):
                raise InputError(
                    "Alternate commands require distinct paid reservations"
                )
            reserved.update(targets)
            if branch["response"] == "hold_commit":
                if targets:
                    raise InputError("Holding a commit cannot spend alternate events")
            elif branch["response"] != "alternate_events" or not targets:
                raise InputError("Unsupported funnel response")
    return {
        "capability": CAPABILITY,
        "source": plan["source"],
        "event_ids": sorted(ids),
        "observation_interval_seconds": interval,
        "full_game_prediction": False,
    }


class PaidObservationController:
    """Holds owned commands and models; the existing runtimes settle every release."""

    paid_observation = True

    def __init__(self, plan, specification, battle):
        validate_paid_plan(plan, specification, battle["compiled"])
        self.plan, self.scene = deepcopy(plan), deepcopy(specification["entity_scene"])
        self.bindings = deepcopy(battle["validation"])
        self.spell_slots = {}
        for slot in self.bindings["spell_bindings"]:
            if slot["cast"] is not None:
                self.spell_slots[slot["cast"]["cast_id"]] = (
                    slot,
                    deepcopy(slot["cast"]),
                )
                slot["cast"] = None
        self.bindings["planned_deployments"] = {
            key: None for key in self.bindings["planned_deployments"]
        }
        self.events = {event["id"]: event for event in self.plan["events"]}
        self.states = {key: "pending" for key in self.events}
        interval, limit = (
            plan["observation_interval_seconds"],
            specification["time_limit_seconds"],
        )
        grid = {
            i * interval
            for i in range(ceil(limit / interval) + 1)
            if i * interval <= limit
        }
        grid.add(limit)
        grid.update(event["at_seconds"] for event in self.events.values())
        if plan["funnel"]["required"]:
            grid.add(plan["funnel"]["deadline_seconds"])
        self.grid, self.cursor = sorted(grid), 0
        self.actions, self.decisions = [], []
        self.choice = None
        self.held = {}
        self.bound = False
        self.termination = None

    def bind_runtime(
        self, actors, effects, buffs, attack_spells, heroes, reinforcements, sieges
    ):
        if self.bound:
            raise InputError("Paid controller can bind its runtime once")
        self.bound = True
        self.actors, self.buffs, self.heroes = actors, buffs, heroes
        self.reinforcements, self.sieges = reinforcements, sieges
        effects_by_id = {effect["id"]: effect for effect in effects}
        spell_owners = []
        if attack_spells is not None:
            spell_owners = [attack_spells, attack_spells.recipe]
            if attack_spells.advanced is not None:
                spell_owners.append(attack_spells.advanced.runtime)
        for key, event in self.events.items():
            collection, identity = (
                event["selector"][field] for field in ("collection", "id")
            )
            if collection == "entities":
                actor = actors[identity]
                if (
                    actor["team"] != "attack"
                    or identity not in self.bindings["attacker_bindings"]
                ):
                    raise InputError("Paid deployment must own its bound army actor")
                actor["spawn_seconds"] = "controlled"
                command = {
                    "id": "paid-spawn:" + key,
                    "kind": "deploy",
                    "targets": [identity],
                    "time_seconds": event["at_seconds"],
                    "positions": {identity: {"x": actor["x"], "y": actor["y"]}},
                }
                self.held[key] = ("command", command, None)
            elif collection in {"effects", "freeze_spells", "healing_spells"}:
                if identity not in effects_by_id:
                    raise InputError("Paid event lacks its compiled command")
                self.held[key] = (
                    "command",
                    deepcopy(effects_by_id.pop(identity)),
                    None,
                )
            elif collection == "buff_spells":
                self.held[key] = ("buff", buffs.fields.pop(identity), buffs)
            else:
                owners = [owner for owner in spell_owners if identity in owner.models]
                if len(owners) != 1:
                    raise InputError(
                        "Paid spell must resolve one shared lifecycle owner"
                    )
                owner = owners[0]
                self.held[key] = ("spell", owner.models.pop(identity), owner)
        return [effect for effect in effects if effect["id"] in effects_by_id]

    def next_boundary(self):
        return self.grid[self.cursor] if self.cursor < len(self.grid) else inf

    def _ready(self, key, time, actors):
        event = self.events[key]
        return (
            self.states[key] == "pending"
            and event["at_seconds"] <= time
            and matches(event["all_conditions"], actors, time)
        )

    def _branch(self, time, actors):
        funnel = self.plan["funnel"]
        if not funnel["required"] or self.choice is not None:
            return
        chosen = None
        for branch in funnel["contingencies"]:
            if (
                branch["trigger"] == "funnel_failed"
                and time < funnel["deadline_seconds"]
            ):
                continue
            if matches(branch["all_conditions"], actors, time):
                chosen = branch["trigger"]
                break
        if (
            chosen is None
            and time <= funnel["deadline_seconds"]
            and matches(funnel["prerequisites"], actors, time)
            and self._executable_commit(time, actors)
        ):
            chosen = "main"
        if chosen is None and time >= funnel["deadline_seconds"]:
            chosen = "deadline_hold"
        if chosen is not None:
            self.choice = chosen
            self.decisions.append({"time_seconds": time, "choice": chosen})
            for branch in funnel["contingencies"]:
                if branch["trigger"] != chosen:
                    for key in branch["event_ids"]:
                        self.states[key] = "suppressed_unspent"
            if chosen != "main":
                for key in funnel["commit_event_ids"]:
                    self.states[key] = "suppressed_unspent"

    def _executable_commit(self, time, actors):
        funnel = self.plan["funnel"]
        alternates = {
            key for branch in funnel["contingencies"] for key in branch["event_ids"]
        }
        deploying = set()
        for key, (kind, template, _) in self.held.items():
            if (
                key not in alternates
                and kind == "command"
                and template["kind"] == "deploy"
                and self._ready(key, time, actors)
                and self._can_execute(template, time, actors, deploying)
            ):
                deploying.update(template["targets"])
        return any(
            self._ready(key, time, actors)
            and (
                self.held[key][0] != "command"
                or self._can_execute(
                    self.held[key][1],
                    time,
                    actors,
                    deploying - set(self.held[key][1].get("targets", [])),
                )
            )
            for key in funnel["commit_event_ids"]
        )

    def _allowed(self, key, time, actors):
        funnel = self.plan["funnel"]
        if not funnel["required"]:
            return True
        if key in funnel["commit_event_ids"]:
            return (
                self.choice == "main"
                and time <= funnel["deadline_seconds"]
                and matches(funnel["prerequisites"], actors, time)
            )
        for branch in funnel["contingencies"]:
            if key in branch["event_ids"]:
                return self.choice == branch["trigger"] and matches(
                    branch["all_conditions"], actors, time
                )
        return True

    def _can_execute(self, command, time, actors, deploying):
        kind = command["kind"]
        if kind == "deploy":
            return all(
                actors[key]["hp"] > 0
                and actors[key]["spawn_seconds"] == "controlled"
                and key not in deploying
                for key in command["targets"]
            )
        if kind == "hero_ability":
            key = command["hero_id"]
            return (
                actors[key]["hp"] > 0
                and (_active(actors[key], time) or key in deploying)
                and key not in self.heroes.used
            )
        if kind == "siege_release":
            key = command["target"]
            return (
                actors[key]["hp"] > 0
                and (_active(actors[key], time) or key in deploying)
                and self.reinforcements.state["delivery_time"] is None
            )
        if kind == "clan_castle_deploy":
            return self.reinforcements.state["delivery_time"] is None
        return True

    def commands(self, time, actors):
        if time < self.next_boundary():
            return []
        while self.cursor < len(self.grid) and self.grid[self.cursor] <= time:
            self.cursor += 1
        self._branch(time, actors)
        pending = [
            key
            for key in self.events
            if self._ready(key, time, actors) and self._allowed(key, time, actors)
        ]
        pending.sort(
            key=lambda key: (
                0 if self.held[key][1].get("kind") == "deploy" else 1,
                self.events[key]["at_seconds"],
                key,
            )
        )
        commands, deploying = [], set()
        for key in pending:
            if not self._ready(key, time, actors) or not self._allowed(
                key, time, actors
            ):
                continue
            kind, template, owner = self.held[key]
            value = deepcopy(template)
            if kind == "command":
                if not self._can_execute(value, time, actors, deploying):
                    continue
                value["time_seconds"] = time
                commands.append(value)
                if value["kind"] == "deploy":
                    for actor_id in value["targets"]:
                        deploying.add(actor_id)
                        self.bindings["planned_deployments"][actor_id] = time
            elif kind == "buff":
                value["start_seconds"] = time
                owner.schedule(value, actors)
            else:
                original_time = value["time_seconds"]
                value["time_seconds"] = time
                delay = value["arrival_seconds"] - original_time
                value["arrival_seconds"] = number(
                    time + delay, "delayed paid spell arrival", time
                )
                if delay > 0 and value["arrival_seconds"] <= time:
                    raise InputError("Delayed paid spell impact clock must advance")
                if (
                    value["entity"] == "recall-spell"
                    and value["parameters"]["redeployment"] is not None
                ):
                    returned = (
                        value["parameters"]["redeployment"]["time_seconds"]
                        - original_time
                        + time
                    )
                    if returned <= value["arrival_seconds"]:
                        raise InputError(
                            "Delayed Recall return clock must follow capture"
                        )
                    value["parameters"]["redeployment"]["time_seconds"] = number(
                        returned, "delayed Recall return", time
                    )
                owner.models[value["id"]] = value
            selector = self.events[key]["selector"]
            if selector["collection"] not in {"entities", "effects"}:
                slot, original = self.spell_slots[selector["id"]]
                slot["cast"] = {**deepcopy(original), "time_seconds": time}
                if self.termination is not None and hasattr(
                    self.termination, "spell_bindings"
                ):
                    for other in self.termination.spell_bindings:
                        if all(
                            other[field] == slot[field]
                            for field in ("origin", "entity", "level", "ordinal")
                        ):
                            other["cast"] = deepcopy(slot["cast"])
            self.states[key] = "released"
            self.actions.append(
                {
                    "event_id": key,
                    "selector": deepcopy(selector),
                    "time_seconds": time,
                    "earliest_seconds": self.events[key]["at_seconds"],
                    "status": "released_once",
                }
            )
        return commands

    def result(self):
        return {
            "capability": CAPABILITY,
            "policies": deepcopy(POLICIES),
            "actions": deepcopy(self.actions),
            "funnel_decisions": deepcopy(self.decisions),
            "event_states": deepcopy(self.states),
            "observations": self.cursor,
            "execution_bindings": deepcopy(self.bindings),
            "full_game_prediction": False,
        }
