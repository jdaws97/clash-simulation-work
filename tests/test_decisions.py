"""Decision validity and whole-path latency checks; no live model is queried."""

import unittest
from copy import deepcopy

from clashlab.common import InputError
from clashlab.decisions import (
    benchmark_decisions,
    build_jev_request,
    normalize_jev_response,
)


def synthetic_case(case_id="cue-1", session="synthetic-session-1"):
    return {
        "id": case_id,
        "state_source": "synthetic-tactical-cue-fixture-not-game-observation",
        "patch_id": "synthetic-not-game-patch",
        "session_id": session,
        "scenario_id": "synthetic-core-threat",
        "fold": "test",
        "state": {"damage_group_threatened": True, "freeze_available": True},
        "allowed_actions": [
            {
                "id": "freeze-tower",
                "description": "Protect the threatened synthetic damage group",
                "legality_source": "synthetic-fixture-resource-and-target-check",
            },
            {
                "id": "wait",
                "description": "Spend no resource and wait for another observation",
                "legality_source": "synthetic-fixture-no-input-action",
            },
        ],
        "fallback_action_id": "wait",
        "decision_deadline_ms": 1000,
        "deadline_source": "synthetic-threat-window-not-a-measured-Clash-deadline",
        "reference_choice": "freeze-tower",
        "reference_source": "synthetic-test-label-not-an-expert-Clash-label",
    }


def synthetic_response(case_id="cue-1", **timing_changes):
    timing = {
        "state_age_at_request_ms": 50,
        "request_round_trip_ms": 100,
        "validation_and_queue_ms": 20,
        "input_delivery_ms": 30,
    }
    timing.update(timing_changes)
    return {
        "case_id": case_id,
        "provider_model_id": "synthetic-provider/not-real-Jev-results",
        "response_source": "synthetic-response-and-timing-fixture",
        "answer": {
            "type": "choice",
            "choice": "freeze-tower",
            "probabilities": {"freeze-tower": 0.8, "wait": 0.2},
            "confidence": 0.6,
        },
        "timing_ms": timing,
    }


def synthetic_configuration():
    return {
        "fold": "test",
        "patch_id": "synthetic-not-game-patch",
        "minimum_sessions": 2,
    }


class DecisionTests(unittest.TestCase):
    def test_fast_inference_can_still_miss_whole_path_deadline(self):
        cases = [synthetic_case(), synthetic_case("cue-2", "synthetic-session-2")]
        responses = [
            synthetic_response(),
            synthetic_response("cue-2", input_delivery_ms=1500),
        ]
        report = benchmark_decisions(cases, responses, synthetic_configuration())
        result = report["evaluated"][0]
        self.assertEqual(result["reference_agreement_all_responses"], 1)
        self.assertEqual(result["deadline_fraction_valid_responses"], 0.5)
        self.assertEqual(result["usable_correct_before_deadline_all_responses"], 0.5)
        self.assertEqual(result["measurements"][1]["total_state_to_input_ms"], 1670)
        self.assertIsNone(report["battle_success_predictions"])

    def test_illegal_answer_is_counted_as_a_failure_not_removed_from_accuracy(self):
        cases = [synthetic_case(), synthetic_case("cue-2", "synthetic-session-2")]
        invalid = synthetic_response("cue-2")
        invalid["answer"]["choice"] = "undeclared-ability"
        result = benchmark_decisions(
            cases, [synthetic_response(), invalid], synthetic_configuration()
        )["evaluated"][0]
        self.assertEqual(result["invalid_response_count"], 1)
        self.assertEqual(result["reference_agreement_all_responses"], 0.5)

    def test_missing_latency_stage_does_not_default_to_zero(self):
        response = synthetic_response()
        del response["timing_ms"]["input_delivery_ms"]
        with self.assertRaisesRegex(InputError, "input_delivery_ms"):
            benchmark_decisions(
                [synthetic_case()], [response], synthetic_configuration()
            )

    def test_missing_matched_case_is_reported(self):
        cases = [synthetic_case(), synthetic_case("cue-2", "synthetic-session-2")]
        result = benchmark_decisions(
            cases, [synthetic_response()], synthetic_configuration()
        )["evaluated"][0]
        self.assertEqual(result["missing_case_ids"], ["cue-2"])
        self.assertEqual(result["status"], "INCOMPLETE_CASE_OR_SESSION_COVERAGE")

    def test_session_fold_leakage_is_rejected(self):
        first = synthetic_case()
        second = synthetic_case("cue-2")
        second["fold"] = "train"
        with self.assertRaisesRegex(InputError, "leaks"):
            benchmark_decisions(
                [first, second], [synthetic_response()], synthetic_configuration()
            )

    def test_probability_distribution_is_not_silently_normalized(self):
        response = synthetic_response()
        response["answer"]["probabilities"]["freeze-tower"] = 0.9
        result = benchmark_decisions(
            [synthetic_case()], [response], synthetic_configuration()
        )["evaluated"][0]
        self.assertEqual(result["invalid_response_count"], 1)
        self.assertEqual(result["reference_agreement_all_responses"], 0)

    def test_request_preparation_is_explicit_and_has_no_network_side_effect(self):
        result = build_jev_request(
            synthetic_case(),
            {
                "model": "explicitly-selected-model",
                "maximum_choice_options": 255,
                "instructions": "Choose one legal action from the supplied state.",
            },
        )
        self.assertEqual(result["network_requests_performed"], 0)
        self.assertEqual(result["request"]["model"], "explicitly-selected-model")
        self.assertEqual(
            set(result["request"]["questions"]["action"]["criteria"]),
            {"freeze-tower", "wait"},
        )

    def test_larger_choice_set_requires_explicit_decomposition(self):
        case = synthetic_case()
        for index in range(254):
            case["allowed_actions"].append(
                {
                    "id": f"extra-{index}",
                    "description": "synthetic option",
                    "legality_source": "synthetic-only",
                }
            )
        with self.assertRaisesRegex(InputError, "decompose"):
            build_jev_request(
                case,
                {
                    "model": "explicit-model",
                    "maximum_choice_options": 255,
                    "instructions": "Choose.",
                },
            )

    def test_normalization_keeps_returned_model_version_and_confidence_separate(self):
        response = synthetic_response()
        normalized = normalize_jev_response(
            synthetic_case(),
            {
                "model": "synthetic-returned-version",
                "answers": {"action": response["answer"]},
            },
            response["timing_ms"],
            "synthetic-sdk-shape-fixture",
        )
        self.assertEqual(
            normalized["provider_model_id"], "typesafe/synthetic-returned-version"
        )
        self.assertEqual(normalized["answer"]["confidence"], 0.6)
        self.assertEqual(normalized["answer"]["probabilities"]["freeze-tower"], 0.8)


if __name__ == "__main__":
    unittest.main()
