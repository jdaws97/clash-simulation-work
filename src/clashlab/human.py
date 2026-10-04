"""Resample whole observed error traces, preserving correlated human mistakes."""

from random import Random

from .common import InputError, identifier, integer, number, require


def perturb_plan(plan, profile, seed, trials):
    random = Random(integer(seed, "seed", 0))
    integer(trials, "trials", 1)
    actions = require(plan, "actions")
    action_ids = [identifier(action["id"], "action id") for action in actions]
    if len(action_ids) != len(set(action_ids)):
        raise InputError("Plan action identifiers must be unique")
    if require(profile, "plan_id") != require(plan, "id"):
        raise InputError("Human profile must match the plan being sampled")
    traces = require(profile, "observed_error_traces")
    if not traces:
        raise InputError(
            "No observed human-error traces; no noise distribution invented"
        )
    for trace in traces:
        identifier(require(trace, "source_replay"), "source replay")
        if set(trace["errors"]) != set(action_ids):
            raise InputError("Every observed trace needs all plan actions")
    samples = []
    for trial in range(trials):
        trace = random.choice(traces)
        events = []
        dropped = []
        for action in actions:
            error = trace["errors"][action["id"]]
            if not isinstance(error["missed"], bool):
                raise InputError("Missed actions must be explicitly true or false")
            if error["missed"]:
                dropped.append(action["id"])
                continue
            time = number(action["time_seconds"], "planned time", 0)
            actual_time = time + number(error["time_error_seconds"], "timing error")
            if actual_time < 0:
                raise InputError("Observed error puts an action before the battle")
            actual_x = number(action["x"], "planned x") + number(
                error["dx_tiles"], "x error"
            )
            actual_y = number(action["y"], "planned y") + number(
                error["dy_tiles"], "y error"
            )
            events.append(
                {**action, "time_seconds": actual_time, "x": actual_x, "y": actual_y}
            )
        events.sort(key=lambda action: action["time_seconds"])
        samples.append(
            {
                "trial": trial,
                "trace_source": trace["source_replay"],
                "events": events,
                "missed_actions": dropped,
            }
        )
    return {
        "status": "PLAN_PERTURBATIONS_ONLY_NOT_BATTLE_OUTCOMES",
        "seed": seed,
        "samples": samples,
        "limitations": [
            "Whole-trace empirical distribution; no Gaussian or perfect-timing prior",
            "Transfer to different plans requires newly measured or explicitly mapped traces",
            "Coordinates require a verified deployment-zone check before combat execution",
        ],
    }
