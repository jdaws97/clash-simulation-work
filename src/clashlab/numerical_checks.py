"""Compare recorded solver outputs without treating score agreement as fidelity."""

from math import isclose, isfinite

from .common import InputError


OUTCOME_FIELDS = (
    "stars",
    "destruction",
    "town_hall_destroyed",
    "elapsed_seconds",
    "end_reason",
)


def _first_difference(first, second, tolerance, path=""):
    first_number = isinstance(first, (int, float)) and not isinstance(first, bool)
    second_number = isinstance(second, (int, float)) and not isinstance(second, bool)
    if first_number and second_number:
        if not isfinite(first) or not isfinite(second):
            raise InputError("Numerical comparisons require finite recorded values")
        if isclose(first, second, rel_tol=0, abs_tol=tolerance):
            return None
    elif type(first) is type(second):
        if isinstance(first, dict):
            if first.keys() != second.keys():
                return {
                    "path": path + "/keys",
                    "first": sorted(first),
                    "second": sorted(second),
                }
            for key in sorted(first):
                difference = _first_difference(
                    first[key], second[key], tolerance, f"{path}/{key}"
                )
                if difference is not None:
                    return difference
            return None
        if isinstance(first, list):
            for index, (left, right) in enumerate(zip(first, second)):
                difference = _first_difference(
                    left, right, tolerance, f"{path}/{index}"
                )
                if difference is not None:
                    return difference
            if len(first) == len(second):
                return None
            return {
                "path": path + "/length",
                "first": len(first),
                "second": len(second),
            }
        if first == second:
            return None
    return {"path": path, "first": first, "second": second}


def compare_battle_results(first, second, absolute_tolerance=1e-7):
    """Compare ordered events, matching frame times, final state and resources.

    Both inputs must come from the same scenario, horizon and runtime; callers
    retain that provenance separately. Agreement only covers recorded outputs
    within this absolute tolerance. It is not evidence of game calibration.
    """
    if (
        isinstance(absolute_tolerance, bool)
        or not isinstance(absolute_tolerance, (int, float))
        or not isfinite(absolute_tolerance)
        or absolute_tolerance <= 0
    ):
        raise InputError("Numerical tolerance must be finite and positive")
    tolerance = absolute_tolerance
    outcomes = [
        {key: result["outcome"][key] for key in OUTCOME_FIELDS}
        for result in (first, second)
    ]
    outcome_difference = _first_difference(*outcomes, tolerance)
    resource_difference = _first_difference(
        first["resource_use"], second["resource_use"], tolerance
    )
    final_actor_difference = _first_difference(
        first["combat"]["actors"], second["combat"]["actors"], tolerance
    )

    traces = [result["combat"]["trace"] for result in (first, second)]
    trace_difference = None
    equal_prefix = 0
    for index, (left, right) in enumerate(zip(*traces)):
        difference = _first_difference(left, right, tolerance)
        if difference is not None:
            trace_difference = {
                "index": index,
                "difference": difference,
                "first_event": left,
                "second_event": right,
            }
            break
        equal_prefix += 1
    if trace_difference is None and len(traces[0]) != len(traces[1]):
        trace_difference = {
            "index": equal_prefix,
            "difference": {
                "path": "/length",
                "first": len(traces[0]),
                "second": len(traces[1]),
            },
            "first_event": (
                traces[0][equal_prefix] if equal_prefix < len(traces[0]) else None
            ),
            "second_event": (
                traces[1][equal_prefix] if equal_prefix < len(traces[1]) else None
            ),
        }

    frames = [result["combat"]["frames"] for result in (first, second)]
    first_index = second_index = matched_frames = 0
    frame_difference = None
    while first_index < len(frames[0]) and second_index < len(frames[1]):
        left, right = frames[0][first_index], frames[1][second_index]
        first_time, second_time = left["time_seconds"], right["time_seconds"]
        if abs(first_time - second_time) <= tolerance:
            matched_frames += 1
            difference = _first_difference(left, right, tolerance)
            if frame_difference is None and difference is not None:
                frame_difference = {
                    "time_seconds": first_time,
                    "difference": difference,
                }
            first_index += 1
            second_index += 1
        elif first_time < second_time:
            first_index += 1
        else:
            second_index += 1
    frame_sampling_equal = matched_frames == len(frames[0]) == len(frames[1])
    differences = (
        outcome_difference,
        resource_difference,
        final_actor_difference,
        trace_difference,
        frame_difference,
    )
    agrees = (
        all(difference is None for difference in differences) and frame_sampling_equal
    )
    return {
        "status": "AGREES_ON_RECORDED_OUTPUTS" if agrees else "RECORDED_OUTPUTS_DIFFER",
        "absolute_tolerance": tolerance,
        "outcomes": outcomes,
        "outcome_difference": outcome_difference,
        "resource_difference": resource_difference,
        "final_actor_difference": final_actor_difference,
        "trace_lengths": [len(trace) for trace in traces],
        "equal_trace_prefix_length": equal_prefix,
        "first_trace_difference": trace_difference,
        "frame_counts": [len(items) for items in frames],
        "matched_frame_count": matched_frames,
        "frame_sampling_equal": frame_sampling_equal,
        "first_frame_difference": frame_difference,
        "replay_calibrated": False,
        "full_game_prediction": False,
    }
