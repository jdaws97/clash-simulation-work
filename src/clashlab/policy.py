"""Cue-driven human plans over explicitly supplied battlefield observations."""

from copy import deepcopy
from random import Random

from .common import InputError, identifier, integer, number, require


def _condition_matches(condition, observation):
    field = identifier(require(condition, "field"), "observation field")
    actual = require(require(observation, "state"), field)
    expected = require(condition, "value")
    operator = require(condition, "operator")
    if operator == "equals":
        if type(actual) is not type(expected):
            raise InputError(f"Cue value type mismatch: {field}")
        return actual == expected
    actual = number(actual, field)
    expected = number(expected, "cue threshold")
    if operator == "at_least":
        return actual >= expected
    if operator == "at_most":
        return actual <= expected
    raise InputError(f"Unsupported cue operator: {operator}")


def simulate_policy(plan, observations, profile, seed, trials):
    """Schedule responses to observed cues using whole measured latency traces.

    This is an open-loop review: supplied observations do not change when a new
    action is scheduled. A full battle adapter must provide that feedback before
    the result can establish a better attack outcome.
    """
    plan_id = identifier(require(plan, "id"), "plan id")
    if require(profile, "plan_id") != plan_id:
        raise InputError("Latency traces must match the intended policy plan")
    if require(plan, "observation_interpolation") != "none":
        raise InputError("Only explicitly observed cue times are supported")
    if require(plan, "concurrency_model") != "independent_streams_joint_latency_trace":
        raise InputError(
            "Concurrency must declare independent jobs with joint latencies"
        )
    missed_transition = require(plan, "missed_action_transition")
    if missed_transition not in {"advance", "stop_stream"}:
        raise InputError("Missed actions require an explicit advance/stop policy")
    streams = require(plan, "streams")
    if not streams:
        raise InputError("At least one human job stream is required")
    action_ids = set()
    stream_ids = set()
    fields = set()
    for stream in streams:
        stream_id = identifier(require(stream, "id"), "stream id")
        if stream_id in stream_ids or not require(stream, "steps"):
            raise InputError("Streams must be unique and contain steps")
        stream_ids.add(stream_id)
        for step in stream["steps"]:
            action = require(step, "action")
            action_id = identifier(require(action, "id"), "action id")
            identifier(require(action, "kind"), "action kind")
            if action_id in action_ids:
                raise InputError("Policy action identifiers must be unique")
            action_ids.add(action_id)
            if not require(step, "all_conditions"):
                raise InputError("Every action requires explicit readiness conditions")
            for condition in step["all_conditions"]:
                fields.add(identifier(require(condition, "field"), "cue field"))
                operator = require(condition, "operator")
                if operator not in {"equals", "at_least", "at_most"}:
                    raise InputError(f"Unsupported cue operator: {operator}")
                value = require(condition, "value")
                if operator != "equals":
                    number(value, "cue threshold")
    if not observations:
        raise InputError("Battlefield observations are required")
    previous = -1
    for observation in observations:
        time = number(require(observation, "time_seconds"), "observation time", 0)
        if time <= previous:
            raise InputError("Observation times must be strictly increasing")
        previous = time
        identifier(require(observation, "source"), "observation source")
        for field in fields:
            require(require(observation, "state"), field)
    episodes = require(profile, "observed_latency_traces")
    if not episodes:
        raise InputError(
            "No measured human latency traces; no distribution is invented"
        )
    for episode in episodes:
        identifier(require(episode, "source_replay"), "trace source")
        responses = require(episode, "responses")
        if set(responses) != action_ids:
            raise InputError("Each latency trace must cover every intended action")
        for response in responses.values():
            number(require(response, "latency_seconds"), "observed latency", 0)
            if not isinstance(require(response, "missed"), bool):
                raise InputError("A missed-action observation must be boolean")
    random = Random(integer(seed, "seed", 0))
    samples = []
    for trial in range(integer(trials, "trials", 1)):
        episode = random.choice(episodes)
        events = []
        unscheduled = []
        for stream in streams:
            available_at = 0.0
            stopped = False
            for step in stream["steps"]:
                action = step["action"]
                ready = None
                if not stopped:
                    ready = next(
                        (
                            observation
                            for observation in observations
                            if observation["time_seconds"] >= available_at
                            and all(
                                _condition_matches(condition, observation)
                                for condition in step["all_conditions"]
                            )
                        ),
                        None,
                    )
                if ready is None:
                    unscheduled.append(action["id"])
                    stopped = True
                    continue
                response = episode["responses"][action["id"]]
                effective_time = ready["time_seconds"] + response["latency_seconds"]
                if effective_time > observations[-1]["time_seconds"]:
                    unscheduled.append(action["id"])
                    stopped = True
                    continue
                event = deepcopy(action)
                event.update(
                    {
                        "stream_id": stream["id"],
                        "cue_time_seconds": ready["time_seconds"],
                        "time_seconds": effective_time,
                        "missed": response["missed"],
                        "cue_source": ready["source"],
                    }
                )
                events.append(event)
                available_at = effective_time
                if response["missed"] and missed_transition == "stop_stream":
                    stopped = True
        events.sort(key=lambda event: (event["time_seconds"], event["id"]))
        samples.append(
            {
                "trial": trial,
                "source_trace": episode["source_replay"],
                "events": events,
                "unscheduled_actions": unscheduled,
            }
        )
    return {
        "status": "CUE_RESPONSE_REVIEW_WITH_FIXED_OBSERVATIONS",
        "plan_id": plan_id,
        "samples": samples,
        "observations_are_recomputed_after_interventions": False,
        "outcome_predictions": None,
        "limitations": [
            "A full combat adapter must recompute battlefield state after changed actions",
            "No interpolation between supplied observations or invention of human reaction distributions",
            "Joint latency traces preserve measured attention delays; strategic choices are explicit plan alternatives",
            "Coordinates, target validity, resource spending, and game input resolution require a battle adapter",
        ],
    }
