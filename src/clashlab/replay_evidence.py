"""Validate observed scoreboard checkpoints without inventing a battle clock."""

from hashlib import sha256
from pathlib import Path
import re

from .replay_observations import ObservationError


def _integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ObservationError(f"{label} must be an integer in {minimum}..{maximum}")
    return value


def _check_evidence(evidence, frame_root):
    if not isinstance(evidence, dict):
        raise ObservationError("Each checkpoint and outcome needs frame evidence")
    frame = evidence.get("frame")
    digest = evidence.get("sha256")
    if not isinstance(frame, str) or not frame:
        raise ObservationError("Frame evidence needs a relative filename")
    if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
        raise ObservationError("Frame evidence needs a SHA-256 digest")
    relative = Path(frame)
    if relative.is_absolute() or ".." in relative.parts:
        raise ObservationError(
            "Evidence frames must stay inside their report directory"
        )
    if frame_root is not None:
        root = Path(frame_root).resolve()
        target = (root / relative).resolve()
        if not target.is_relative_to(root):
            raise ObservationError("Evidence frame escapes the report directory")
        if not target.is_file() or sha256(target.read_bytes()).hexdigest() != digest:
            raise ObservationError(f"Missing or modified evidence frame: {frame}")


def summarize_checkpoint_dataset(dataset, frame_root=None):
    """Check source integrity and summarize observations, never prediction accuracy.

    The schema intentionally has no precise video timestamps, elapsed battle
    times or inferred modifier identity. Those belong in a separate measured
    clock case accepted by replay_observations.compare_observations.
    """
    if dataset.get("schema_version") != "replay-checkpoints-v1":
        raise ObservationError("Unsupported replay checkpoint schema")
    if dataset.get("review_method") != "visual_frames":
        raise ObservationError("Replay checkpoints require visual frame review")
    if not dataset.get("selection_method") or not dataset.get("clock_policy"):
        raise ObservationError("Selection and clock policies must be explicit")
    source_ids = [source.get("id") for source in dataset.get("sources", [])]
    if not source_ids or len(set(source_ids)) != len(source_ids):
        raise ObservationError("Source video identifiers must be unique")
    summaries = []
    seen = set()
    for case in dataset.get("replays", []):
        identifier = case.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ObservationError("Replay identifiers must be nonempty and unique")
        seen.add(identifier)
        if case.get("video_id") not in source_ids:
            raise ObservationError("Replay refers to an unknown source video")
        if case.get("user_role") not in {"attacker", "defender"}:
            raise ObservationError("The user's replay role must be explicit")
        checkpoints = case.get("checkpoints", [])
        if not checkpoints:
            raise ObservationError("Replay needs at least one observed checkpoint")
        last_sequence = -1
        last_remaining = float("inf")
        last_damage = -1
        last_stars = -1
        for point in checkpoints:
            sequence = _integer(point.get("sequence"), "Sequence", 1, 1000000)
            remaining = _integer(
                point.get("replay_remaining_seconds"), "Replay countdown", 0, 3600
            )
            if sequence <= last_sequence or remaining > last_remaining:
                raise ObservationError("Checkpoint sequence or countdown is unordered")
            last_sequence, last_remaining = sequence, remaining
            if point.get("battle_elapsed_seconds") is not None:
                raise ObservationError(
                    "Checkpoint countdown cannot imply battle elapsed"
                )
            if point.get("displayed_replay_speed") not in {1, 2, 4}:
                raise ObservationError("Checkpoint requires the visible replay speed")
            for field, upper, previous in (
                ("displayed_destruction_percent", 100, last_damage),
                ("displayed_stars", 3, last_stars),
            ):
                value = point.get(field)
                if value is None:
                    continue
                _integer(value, field, 0, upper)
                if value < previous:
                    raise ObservationError(f"Observed {field} cannot go backward")
                if field == "displayed_destruction_percent":
                    last_damage = value
                else:
                    last_stars = value
            _check_evidence(point.get("evidence"), frame_root)
        outcome = case.get("observed_outcome", {})
        damage = _integer(
            outcome.get("destruction_percent"), "Final destruction", 0, 100
        )
        stars = _integer(outcome.get("stars"), "Final stars", 0, 3)
        if damage < last_damage or stars < last_stars:
            raise ObservationError("Final result cannot precede observed progress")
        if (damage == 100) != (stars == 3) or (stars >= 2 and damage < 50):
            raise ObservationError("Final stars contradict final destruction")
        if stars == 0 and damage >= 50:
            raise ObservationError("Final result lacks the destruction-threshold star")
        if outcome.get("evidence_kind") not in {"battle_log", "replay_terminal"}:
            raise ObservationError(
                "Final result needs terminal replay or battle-log evidence"
            )
        _check_evidence(outcome.get("evidence"), frame_root)
        if outcome["evidence_kind"] == "replay_terminal":
            last = checkpoints[-1]
            if (
                last["replay_remaining_seconds"] != 0
                or last["displayed_destruction_percent"] != damage
                or last["displayed_stars"] != stars
                or last["evidence"]["frame"] != outcome["evidence"]["frame"]
            ):
                raise ObservationError(
                    "Terminal result must match the final checkpoint"
                )
        missing = []
        for field in ("patch_id", "mode", "modifier_id"):
            if case.get(field) in {None, "unknown", ""}:
                missing.append(field)
        for field in ("exact_layout_binding", "exact_army_equipment_binding"):
            if not case.get(field):
                missing.append(field)
        missing.append("measured_video_to_battle_clock")
        summaries.append(
            {
                "id": identifier,
                "checkpoint_count": len(checkpoints),
                "observed_destruction_percent": damage,
                "observed_stars": stars,
                "town_hall_destroyed_from_final_score": stars >= 2
                or (stars == 1 and damage < 50),
                "calibration_ready": False,
                "missing_for_replay_comparison": missing,
            }
        )
    if not summaries:
        raise ObservationError("Dataset has no reviewed replays")
    return {
        "status": "OBSERVATIONS_ONLY_NOT_REPLAY_CALIBRATION",
        "replay_count": len(summaries),
        "checkpoint_count": sum(case["checkpoint_count"] for case in summaries),
        "verified_frame_hashes": frame_root is not None,
        "calibrated_replay_count": 0,
        "population_win_rate": None,
        "replays": summaries,
    }
