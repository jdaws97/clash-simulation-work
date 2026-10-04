"""Continuous-time local encounters with explicit targeting and protection.

This is an encounter model, not a reconstruction of the game engine. Movement,
walls, splash, spawning, and retargeting must be measured or supplied by another
adapter. No unsupported mechanic is silently replaced with generic damage.
"""

from collections import defaultdict
from copy import deepcopy
from heapq import heappop, heappush

from .common import InputError, identifier, number, require


SUPPORTED_EFFECTS = {"damage", "heal", "freeze", "invulnerability"}


def simulate_encounter(specification):
    horizon = number(require(specification, "duration_seconds"), "duration", 0)
    if horizon == 0:
        raise InputError("Encounter duration must be positive")
    unsupported = require(specification, "unsupported_mechanics")
    if unsupported:
        raise InputError(f"Missing combat adapters: {', '.join(unsupported)}")
    if require(specification, "same_time_policy") != "simultaneous_damage_then_heal":
        raise InputError(
            "The local encounter supports simultaneous damage then healing"
        )
    actors = {}
    for actor in require(specification, "actors"):
        actor_id = identifier(require(actor, "id"), "actor id")
        if actor_id in actors:
            raise InputError(f"Duplicate encounter actor: {actor_id}")
        hp = number(require(actor, "hitpoints"), "hitpoints", 0)
        if hp == 0:
            raise InputError("An actor needs positive initial hitpoints")
        actors[actor_id] = {
            "hp": hp,
            "maximum_hp": hp,
            "team": identifier(require(actor, "team"), "team"),
            "death_time": None,
        }
    if not actors:
        raise InputError("Encounter needs actors")
    events = []
    serial = 0
    for event in require(specification, "events"):
        event = deepcopy(event)
        time = number(require(event, "time_seconds"), "event time", 0)
        kind = require(event, "effect")
        if kind not in SUPPORTED_EFFECTS:
            raise InputError(f"Unsupported encounter effect: {kind}")
        if require(event, "target") not in actors:
            raise InputError("Encounter target is unknown")
        source = require(event, "source")
        if source not in actors and source != "external":
            raise InputError("Encounter source is unknown")
        if not isinstance(require(event, "requires_source_alive"), bool):
            raise InputError("Projectile/source survival rule must be explicit")
        if kind in {"damage", "heal"}:
            number(require(event, "amount"), "effect amount", 0)
        else:
            duration = number(require(event, "duration_seconds"), "effect duration", 0)
            if duration == 0:
                raise InputError("Protection duration must be positive")
        identifier(require(event, "id"), "event id")
        heappush(events, (time, serial, event))
        serial += 1
    if len({event[2]["id"] for event in events}) != len(events):
        raise InputError("Encounter event identifiers must be unique")
    freezes = defaultdict(list)
    immunity = defaultdict(list)
    trace = []
    while events:
        time = events[0][0]
        if time > horizon:
            break
        simultaneous = []
        while events and events[0][0] == time:
            simultaneous.append(heappop(events)[2])
        alive_before = {key for key, state in actors.items() if state["hp"] > 0}
        active = []
        for event in simultaneous:
            source = event["source"]
            if event["target"] not in alive_before:
                trace.append(
                    {
                        "time_seconds": time,
                        "id": event["id"],
                        "result": "target_already_dead",
                    }
                )
                continue
            if (
                event["requires_source_alive"]
                and source != "external"
                and source not in alive_before
            ):
                trace.append(
                    {
                        "time_seconds": time,
                        "id": event["id"],
                        "result": "source_already_dead",
                    }
                )
                continue
            active.append(event)
        for event in active:
            if event["effect"] == "freeze":
                freezes[event["target"]].append(
                    (time, time + event["duration_seconds"])
                )
            elif event["effect"] == "invulnerability":
                immunity[event["target"]].append(
                    (time, time + event["duration_seconds"])
                )
        damage = defaultdict(float)
        healing = defaultdict(float)
        for event in active:
            target = event["target"]
            source = event["source"]
            kind = event["effect"]
            result = "applied"
            if kind == "damage":
                frozen = any(start <= time < end for start, end in freezes[source])
                protected = any(start <= time < end for start, end in immunity[target])
                if frozen:
                    result = "source_frozen"
                elif protected:
                    result = "target_invulnerable"
                else:
                    damage[target] += event["amount"]
            elif kind == "heal":
                healing[target] += event["amount"]
            trace.append({"time_seconds": time, "id": event["id"], "result": result})
        for actor_id, state in actors.items():
            if actor_id not in alive_before:
                continue
            state["hp"] -= damage[actor_id]
            if state["hp"] <= 0:
                state["hp"] = 0
                state["death_time"] = time
            else:
                state["hp"] = min(state["maximum_hp"], state["hp"] + healing[actor_id])
    return {
        "status": "LOCAL_ENCOUNTER_MODEL_NOT_FULL_BATTLE_PREDICTION",
        "id": require(specification, "id"),
        "actors": actors,
        "trace": trace,
        "limitations": [
            "Incoming shots and targets are explicit inputs, not inferred pathfinding",
            "Freeze suppresses supplied shots; recovery of attack cooldown is not modeled",
            "Same-time policy is a declared model convention, not verified game scheduling",
            "No stars, destruction, or full-army win probabilities are inferred",
        ],
    }


def paired_interventions(specification, experiments):
    """Compare specified plan changes against identical local exposure events."""
    baseline = simulate_encounter(specification)
    variants = []
    known = {event["id"] for event in specification["events"]}
    for experiment in experiments:
        variant = deepcopy(specification)
        updates = require(experiment, "event_updates")
        if not set(updates) <= known:
            raise InputError("Intervention refers to an unknown event")
        for event in variant["events"]:
            if event["id"] in updates:
                event.update(updates[event["id"]])
        result = simulate_encounter(variant)
        differences = {
            key: state["hp"] - baseline["actors"][key]["hp"]
            for key, state in result["actors"].items()
        }
        variants.append(
            {
                "label": require(experiment, "label"),
                "result": result,
                "hp_difference": differences,
            }
        )
    return {
        "status": "MODEL_COUNTERFACTUAL_NOT_OBSERVED_CAUSAL_PROOF",
        "baseline": baseline,
        "variants": variants,
    }
