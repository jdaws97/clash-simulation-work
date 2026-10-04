"""Replay-conditioned, session-cluster bootstrap evaluations."""

from collections import defaultdict
from random import Random

from .common import InputError, identifier, integer, number, require
from .scoring import outcome_metrics, strongest_attack, validate_outcome


METRICS = (
    "triple_rate",
    "stars",
    "destruction",
    "town_hall_survival",
    "attacker_trophies_lower",
    "attacker_trophies_upper",
    "defender_trophies_lower",
    "defender_trophies_upper",
)


def validate_replays(rows):
    seen = set()
    for row in rows:
        replay_id = identifier(require(row, "id"), "replay id")
        if replay_id in seen:
            raise InputError(f"Duplicate replay would inflate evidence: {replay_id}")
        seen.add(replay_id)
        for field in (
            "army_id",
            "base_id",
            "plan_id",
            "scenario_id",
            "human_profile_id",
            "patch_id",
            "modifier_id",
            "session_id",
            "encounter_id",
            "source",
        ):
            identifier(require(row, field), field)
        if row["mode"] not in {"ranked", "war", "cwl", "friendly"}:
            raise InputError("Unknown replay mode")
        integer(require(row, "attacker_town_hall"), "attacker Town Hall", 1)
        integer(require(row, "defender_town_hall"), "defender Town Hall", 1)
        if row["fold"] not in {"train", "validation", "test"}:
            raise InputError("Replay fold must be train, validation, or test")
        validate_outcome(row)
    for field in ("session_id", "encounter_id"):
        assigned = {}
        for row in rows:
            previous = assigned.setdefault(row[field], row["fold"])
            if previous != row["fold"]:
                raise InputError(f"{field} appears in multiple folds: {row[field]}")
    return rows


def _units(rows, perspective, mode):
    if perspective == "defense" and mode in {"war", "cwl"}:
        encounters = defaultdict(list)
        for row in rows:
            encounters[row["encounter_id"]].append(row)
        units = []
        for encounter_rows in encounters.values():
            sessions = {row["session_id"] for row in encounter_rows}
            if len(sessions) != 1:
                raise InputError(
                    "A war/CWL base encounter must have one clustering session"
                )
            units.append(strongest_attack(encounter_rows))
        return units
    return rows


def _mean_metrics(units):
    if not units:
        raise InputError("Cannot summarize an empty replay group")
    values = [outcome_metrics(row) for row in units]
    return {
        metric: sum(value[metric] for value in values) / len(values)
        for metric in METRICS
    }


def _quantile(values, probability):
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def evaluate_candidates(rows, configuration):
    validate_replays(rows)
    perspective = require(configuration, "perspective")
    if perspective not in {"attack", "defense"}:
        raise InputError("Perspective must be attack or defense")
    mode = require(configuration, "mode")
    if mode not in {"ranked", "war", "cwl", "friendly"}:
        raise InputError("Unknown evaluation mode")
    fold = require(configuration, "fold")
    if fold not in {"train", "validation", "test"}:
        raise InputError("Unknown evaluation fold")
    weights = require(configuration, "scenario_weights")
    if not weights:
        raise InputError(
            "Opponent mixture is unknown; qualitative descriptions are not percentages"
        )
    for name, weight in weights.items():
        identifier(name, "scenario id")
        number(weight, "scenario weight", 0, 1)
    if abs(sum(weights.values()) - 1) > 1e-9:
        raise InputError("Explicit scenario weights must sum to one")
    minimum = integer(require(configuration, "minimum_sessions"), "minimum sessions", 1)
    iterations = integer(
        require(configuration, "bootstrap_iterations"), "bootstrap iterations", 2
    )
    confidence = number(require(configuration, "confidence_level"), "confidence", 0, 1)
    if confidence in (0, 1):
        raise InputError("Confidence must be strictly between zero and one")
    random = Random(integer(require(configuration, "seed"), "seed", 0))
    field = "army_id" if perspective == "attack" else "base_id"
    requested = require(configuration, "candidate_ids")
    if not requested or len(requested) != len(set(requested)):
        raise InputError("Candidate identifiers must be a nonempty unique list")
    selected = [
        row
        for row in rows
        if row["mode"] == mode
        and row["fold"] == fold
        and row["patch_id"] == require(configuration, "patch_id")
        and row["modifier_id"] == require(configuration, "modifier_id")
        and row["human_profile_id"] == require(configuration, "human_profile_id")
    ]
    evaluated = []
    unsupported = []
    for candidate_id in requested:
        groups = {}
        gaps = []
        plan_ids = require(configuration, "plan_ids_by_candidate")
        plan_id = require(plan_ids, candidate_id)
        for scenario, weight in weights.items():
            if weight == 0:
                continue
            matching = [
                row
                for row in selected
                if row[field] == candidate_id
                and row["scenario_id"] == scenario
                and row["plan_id"] == plan_id
            ]
            units = _units(matching, perspective, mode)
            sessions = defaultdict(list)
            for unit in units:
                sessions[unit["session_id"]].append(unit)
            if len(sessions) < minimum:
                gaps.append(
                    {
                        "scenario": scenario,
                        "sessions": len(sessions),
                        "required": minimum,
                    }
                )
            groups[scenario] = (units, list(sessions.values()))
        if gaps:
            unsupported.append(
                {
                    "candidate_id": candidate_id,
                    "status": "INSUFFICIENT_MATCHED_EVIDENCE",
                    "gaps": gaps,
                }
            )
            continue
        point = {metric: 0.0 for metric in METRICS}
        for scenario, (units, _) in groups.items():
            summary = _mean_metrics(units)
            for metric in METRICS:
                point[metric] += weights[scenario] * summary[metric]
        samples = {metric: [] for metric in METRICS}
        for iteration in range(iterations):
            estimate = {metric: 0.0 for metric in METRICS}
            for scenario, (_, sessions) in groups.items():
                sampled_units = []
                for draw in range(len(sessions)):
                    sampled_units.extend(random.choice(sessions))
                summary = _mean_metrics(sampled_units)
                for metric in METRICS:
                    estimate[metric] += weights[scenario] * summary[metric]
            for metric in METRICS:
                samples[metric].append(estimate[metric])
        tail = (1 - confidence) / 2
        intervals = {
            metric: [_quantile(values, tail), _quantile(values, 1 - tail)]
            for metric, values in samples.items()
        }
        evaluated.append(
            {
                "candidate_id": candidate_id,
                "point_estimates": point,
                "cluster_bootstrap_intervals": intervals,
                "evidence": {
                    scenario: {"units": len(units), "sessions": len(sessions)}
                    for scenario, (units, sessions) in groups.items()
                },
                "warnings": [
                    "Conditional on represented opponents, patch, plan, and human profile",
                    "A zero-width bootstrap interval does not imply certainty or zero unseen risk",
                    "New armies or layouts are unsupported until measured or validated in a combat model",
                    "Observed outcomes describe army, plan, execution, and opponent jointly; they do not isolate army strength",
                ],
            }
        )
    if perspective == "attack":
        order = lambda result: (
            result["point_estimates"]["triple_rate"],
            result["point_estimates"]["stars"],
            result["point_estimates"]["destruction"],
        )
    elif mode == "ranked":
        order = lambda result: (
            result["point_estimates"]["defender_trophies_lower"],
            result["point_estimates"]["defender_trophies_upper"],
            result["point_estimates"]["town_hall_survival"],
        )
    else:
        order = lambda result: (
            -result["point_estimates"]["stars"],
            -result["point_estimates"]["destruction"],
        )
    evaluated.sort(key=order, reverse=True)
    return {
        "method": "MATCHED_REPLAY_SESSION_CLUSTER_BOOTSTRAP",
        "configuration": configuration,
        "evaluated": evaluated,
        "unsupported": unsupported,
        "selection_warning": "Point-estimate order is exploratory; validate selections on unseen bases and sessions",
    }
