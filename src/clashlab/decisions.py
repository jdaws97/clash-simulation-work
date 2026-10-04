"""Provider-independent tactical decision contracts and offline benchmarking.

This module never calls a paid API or delivers input to the game. Model answers
are evaluated against annotated action labels, not substituted for battle results.
"""

import json
from collections import defaultdict
from math import isclose
from statistics import mean

from .common import InputError, identifier, integer, number, require


TIMING_STAGES = (
    "state_age_at_request_ms",
    "request_round_trip_ms",
    "validation_and_queue_ms",
    "input_delivery_ms",
)


def _validate_case(case):
    identifier(require(case, "id"), "decision case id")
    for field in ("state_source", "patch_id", "session_id", "scenario_id"):
        identifier(require(case, field), field)
    if require(case, "fold") not in {"train", "validation", "test"}:
        raise InputError("Decision cases require an explicit evaluation fold")
    if not isinstance(require(case, "state"), dict):
        raise InputError("Decision state must be a structured object")
    actions = require(case, "allowed_actions")
    if not actions:
        raise InputError("Decision cases need explicitly legal action choices")
    ids = set()
    for action in actions:
        action_id = identifier(require(action, "id"), "legal action id")
        if action_id in ids:
            raise InputError("Legal action IDs must be unique")
        ids.add(action_id)
        identifier(require(action, "description"), "action description")
        identifier(require(action, "legality_source"), "action legality evidence")
    if require(case, "fallback_action_id") not in ids:
        raise InputError("Fallback must be one of the explicitly legal choices")
    number(require(case, "decision_deadline_ms"), "decision deadline", 0)
    identifier(require(case, "deadline_source"), "deadline evidence")
    return ids


def build_jev_request(case, configuration):
    """Prepare the documented Choice request without transmitting state."""
    action_ids = _validate_case(case)
    maximum = integer(
        require(configuration, "maximum_choice_options"), "option cap", 2, 255
    )
    if not 2 <= len(action_ids) <= maximum:
        raise InputError(
            "Jev request needs 2..configured-cap options; decompose larger choices"
        )
    model = identifier(require(configuration, "model"), "requested model")
    instructions = identifier(
        require(configuration, "instructions"), "decision instructions"
    )
    return {
        "status": "PREPARED_REQUEST_ONLY_NOT_SENT",
        "case_id": case["id"],
        "documented_endpoint": "https://api.typesafe.ai/v1/systemone",
        "request": {
            "model": model,
            "state": json.dumps(case["state"], sort_keys=True, allow_nan=False),
            "questions": {
                "action": {
                    "type": "choice",
                    "instructions": instructions,
                    "criteria": {
                        action["id"]: action["description"]
                        for action in case["allowed_actions"]
                    },
                }
            },
        },
        "network_requests_performed": 0,
        "state_source": case["state_source"],
    }


def validate_choice(case, answer):
    action_ids = _validate_case(case)
    if not isinstance(answer, dict):
        raise InputError("Provider answer must be a structured object")
    choice = require(answer, "choice")
    if choice not in action_ids:
        raise InputError("Provider chose an action outside the legal set")
    probabilities = require(answer, "probabilities")
    if not isinstance(probabilities, dict):
        raise InputError("Choice probabilities must be a mapping")
    if set(probabilities) != action_ids:
        raise InputError(
            "Probability distribution must cover exactly the legal choices"
        )
    for probability in probabilities.values():
        number(probability, "choice probability", 0, 1)
    if not isclose(sum(probabilities.values()), 1, rel_tol=0, abs_tol=1e-8):
        raise InputError(
            "Choice probabilities must sum to one; no silent normalization"
        )
    number(require(answer, "confidence"), "reported confidence statistic", 0, 1)
    return next(action for action in case["allowed_actions"] if action["id"] == choice)


def normalize_jev_response(case, response, timing, source):
    answer = require(require(response, "answers"), "action")
    if require(answer, "type") != "choice":
        raise InputError("Jev action response must be a Choice")
    validate_choice(case, answer)
    model = identifier(require(response, "model"), "returned model version")
    identifier(source, "response evidence")
    for stage in TIMING_STAGES:
        number(require(timing, stage), stage, 0)
    return {
        "case_id": case["id"],
        "provider_model_id": "typesafe/" + model,
        "response_source": source,
        "answer": answer,
        "timing_ms": timing,
    }


def benchmark_decisions(cases, responses, configuration):
    """Compare matching held-out labels and measured full-path response times."""
    fold = require(configuration, "fold")
    patch = identifier(require(configuration, "patch_id"), "benchmark patch")
    minimum_sessions = integer(
        require(configuration, "minimum_sessions"), "minimum sessions", 1
    )
    case_by_id = {}
    session_folds = defaultdict(set)
    for case in cases:
        action_ids = _validate_case(case)
        if case["id"] in case_by_id:
            raise InputError("Decision case IDs must be unique")
        reference = require(case, "reference_choice")
        if reference not in action_ids:
            raise InputError("Reference action must belong to the legal set")
        identifier(require(case, "reference_source"), "reference label source")
        session_folds[case["session_id"]].add(case["fold"])
        case_by_id[case["id"]] = case
    if any(len(folds) > 1 for folds in session_folds.values()):
        raise InputError("Decision session leaks across evaluation folds")
    selected = {
        case_id: case
        for case_id, case in case_by_id.items()
        if case["fold"] == fold and case["patch_id"] == patch
    }
    if not selected:
        raise InputError("No decision cases match the requested fold and patch")
    grouped = defaultdict(dict)
    for response in responses:
        provider = identifier(
            require(response, "provider_model_id"), "resolved provider/model id"
        )
        identifier(require(response, "response_source"), "response evidence")
        case_id = require(response, "case_id")
        if case_id not in case_by_id:
            raise InputError("Response references an unknown case")
        if case_id not in selected:
            continue
        if case_id in grouped[provider]:
            raise InputError(
                "Each provider gets one response per case in this benchmark"
            )
        grouped[provider][case_id] = response
    evaluated = []
    for provider, by_case in sorted(grouped.items()):
        measurements = []
        for case_id, response in by_case.items():
            case = selected[case_id]
            try:
                action = validate_choice(case, require(response, "answer"))
            except InputError as error:
                measurements.append(
                    {"case_id": case_id, "valid": False, "reason": str(error)}
                )
                continue
            timing = require(response, "timing_ms")
            total = sum(
                number(require(timing, stage), stage, 0) for stage in TIMING_STAGES
            )
            probabilities = response["answer"]["probabilities"]
            reference = case["reference_choice"]
            brier = sum(
                (probability - (1 if choice == reference else 0)) ** 2
                for choice, probability in probabilities.items()
            )
            measurements.append(
                {
                    "case_id": case_id,
                    "valid": True,
                    "choice": action["id"],
                    "reference_agreement": action["id"] == reference,
                    "selected_action_probability": probabilities[action["id"]],
                    "reported_confidence_statistic": response["answer"]["confidence"],
                    "reference_label_brier": brier,
                    "total_state_to_input_ms": total,
                    "deadline_ms": case["decision_deadline_ms"],
                    "within_deadline": total <= case["decision_deadline_ms"],
                }
            )
        valid = [item for item in measurements if item["valid"]]
        sessions = {selected[case_id]["session_id"] for case_id in by_case}
        missing = sorted(set(selected) - set(by_case))
        supported = not missing and len(sessions) >= minimum_sessions
        evaluated.append(
            {
                "provider_model_id": provider,
                "status": (
                    "COMPLETE_MATCHED_LABEL_BENCHMARK"
                    if supported
                    else "INCOMPLETE_CASE_OR_SESSION_COVERAGE"
                ),
                "sessions": len(sessions),
                "missing_case_ids": missing,
                "invalid_response_count": len(measurements) - len(valid),
                "reference_agreement_all_responses": (
                    sum(item["reference_agreement"] for item in valid)
                    / len(measurements)
                ),
                "deadline_fraction_valid_responses": (
                    mean(item["within_deadline"] for item in valid) if valid else None
                ),
                "usable_correct_before_deadline_all_responses": (
                    sum(
                        item["reference_agreement"] and item["within_deadline"]
                        for item in valid
                    )
                    / len(measurements)
                ),
                "mean_reference_label_brier": (
                    mean(item["reference_label_brier"] for item in valid)
                    if valid
                    else None
                ),
                "measurements": measurements,
            }
        )
    return {
        "status": "OFFLINE_DECISION_LABEL_AND_LATENCY_BENCHMARK",
        "evaluated": evaluated,
        "network_requests_performed": 0,
        "battle_success_predictions": None,
        "limitations": [
            "Agreement is with supplied action labels, not verified optimal actions or triple outcomes",
            "Reported confidence is a provider statistic, not a measured Clash success probability",
            "Latency requires state age, request round trip, validation/queue time and actual input delivery",
            "A live adapter must recheck current state and action legality before executing",
        ],
    }
