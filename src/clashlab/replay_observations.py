"""Compare timestamped replay observations with a simulator event trace.

Video time is not battle time: commentary, cuts, pauses and speed changes must
be represented by separate clock segments. No fitted win rate is produced.
"""

import argparse
import json
from math import isfinite
from pathlib import Path


class ObservationError(ValueError):
    """An observation lacks enough context for the requested comparison."""


def finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObservationError(f"{label} must be a finite number")
    if not isfinite(value):
        raise ObservationError(f"{label} must be a finite number")
    return value


def validate_segments(segments):
    if not segments:
        raise ObservationError(
            "At least one measured video-to-battle segment is needed"
        )
    previous_end = -1
    for segment in segments:
        start = finite_number(segment["video_start"], "video start")
        end = finite_number(segment["video_end"], "video end")
        battle = finite_number(segment["battle_elapsed_start"], "battle elapsed start")
        speed = finite_number(segment["speed"], "replay speed")
        if start < 0 or end <= start or battle < 0 or speed < 0:
            raise ObservationError("Clock segments need valid ordered bounds")
        if start < previous_end:
            raise ObservationError("Video clock segments overlap or are unordered")
        if not segment.get("evidence"):
            raise ObservationError("Clock segments need a measured clock/speed source")
        previous_end = end


def map_video_interval(segments, earliest, latest):
    """Map a visual uncertainty interval contained within one continuous segment."""
    validate_segments(segments)
    earliest = finite_number(earliest, "earliest video time")
    latest = finite_number(latest, "latest video time")
    if earliest < 0 or latest < earliest:
        raise ObservationError("Observation interval is reversed or negative")
    candidates = [
        segment
        for segment in segments
        if segment["video_start"] <= earliest <= latest <= segment["video_end"]
    ]
    if len(candidates) != 1:
        raise ObservationError(
            "Observation crosses a cut, speed change, or missing segment"
        )
    segment = candidates[0]
    if segment["speed"] == 0:
        raise ObservationError("A paused image cannot establish when an event occurred")
    offset = segment["battle_elapsed_start"]
    return [
        offset + (point - segment["video_start"]) * segment["speed"]
        for point in (earliest, latest)
    ]


def compare_observations(case, predictions, simulation_context):
    """Report event residuals only after exact patch/mode/modifier checks.

    Each event key includes entity, kind, and occurrence number so repeated
    attacks are not matched to the wrong projectile. Events absent from the
    simulation remain explicit missing evidence, never zero-error matches.
    """
    for field in ("patch_id", "mode", "modifier_id"):
        value = case.get(field)
        if not value or value == "unknown":
            raise ObservationError(
                f"Replay {field} is unknown; cannot calibrate timing"
            )
        if simulation_context.get(field) != value:
            raise ObservationError(f"Replay and simulator {field} differ")
    if case.get("review_method") != "visual_frames":
        raise ObservationError("Timing calibration requires visual frame observations")
    if not case.get("source_url") or not case.get("selection_method"):
        raise ObservationError("Replay source and selection method must be explicit")
    segments = case["clock_segments"]
    validate_segments(segments)
    predicted = {}
    for item in predictions:
        key = event_key(item)
        if key in predicted:
            raise ObservationError("Duplicate predicted event key")
        when = finite_number(item["battle_elapsed_seconds"], "predicted event time")
        if when < 0:
            raise ObservationError("Predicted event time cannot be negative")
        predicted[key] = when
    seen = set()
    results = []
    for event in case["events"]:
        key = event_key(event)
        if key in seen:
            raise ObservationError("Duplicate observed event key")
        seen.add(key)
        if not event.get("evidence"):
            raise ObservationError("Each event needs a frame or clip reference")
        interval = map_video_interval(segments, *event["video_interval_seconds"])
        result = {"key": list(key), "observed_battle_interval": interval}
        if key not in predicted:
            result.update(status="missing_prediction", error_seconds=None)
        else:
            when = predicted[key]
            residual = when - min(max(when, interval[0]), interval[1])
            status = "within_observed_interval"
            if residual < 0:
                status = "too_early"
            elif residual > 0:
                status = "too_late"
            result.update(
                status=status,
                predicted_battle_seconds=when,
                error_seconds=residual,
            )
        results.append(result)
    if not results:
        raise ObservationError("No observed events to compare")
    return {
        "status": "EVENT_COMPARISON_NOT_FULL_BATTLE_VALIDATION",
        "events": results,
        "observed_event_count": len(results),
        "matched_event_count": sum(
            item["error_seconds"] is not None for item in results
        ),
        "selection_method": case["selection_method"],
        "population_win_rate": None,
        "current_meta_validated": False,
    }


def event_key(event):
    entity = event.get("entity_id")
    kind = event.get("kind")
    occurrence = event.get("occurrence")
    if (
        not isinstance(entity, str)
        or not entity
        or not isinstance(kind, str)
        or not kind
    ):
        raise ObservationError("Each event needs entity and kind identifiers")
    if type(occurrence) is not int or occurrence < 1:
        raise ObservationError("Event occurrence must be a positive integer")
    return entity, kind, occurrence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("simulation_context", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output path to preserve prior evidence")
    inputs = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (args.case, args.predictions, args.simulation_context)
    ]
    try:
        result = compare_observations(*inputs)
    except ObservationError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(f"Compared {result['observed_event_count']} observed events.")


if __name__ == "__main__":
    main()
