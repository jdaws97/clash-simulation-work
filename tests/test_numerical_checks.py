"""Verification must catch differences hidden by identical star outcomes."""

from copy import deepcopy
import unittest

from clashlab.common import InputError
from clashlab.numerical_checks import compare_battle_results


def result():
    return {
        "outcome": {
            "stars": 2,
            "destruction": 55,
            "town_hall_destroyed": True,
            "elapsed_seconds": 60,
            "end_reason": "declared_time_limit",
        },
        "resource_use": {"unspent_spell_space": 2},
        "combat": {
            "actors": {"queen": {"x": 3, "hp": 100}},
            "trace": [
                {
                    "time_seconds": 1,
                    "event": "projectile_launch",
                    "source": "queen",
                    "target": "tower",
                }
            ],
            "frames": [{"time_seconds": 1, "actors": {"queen": {"x": 3, "hp": 100}}}],
        },
    }


class NumericalChecksTests(unittest.TestCase):
    def test_binary_roundoff_does_not_create_false_divergence(self):
        first, second = result(), result()
        second["combat"]["trace"][0]["time_seconds"] += 1e-12
        second["combat"]["frames"][0]["time_seconds"] += 1e-12
        self.assertEqual(
            compare_battle_results(first, second)["status"],
            "AGREES_ON_RECORDED_OUTPUTS",
        )

    def test_same_stars_and_final_state_do_not_hide_timing_difference(self):
        first, second = result(), result()
        second["combat"]["trace"][0]["time_seconds"] += 0.01
        comparison = compare_battle_results(first, second)
        self.assertIsNone(comparison["outcome_difference"])
        self.assertEqual(comparison["status"], "RECORDED_OUTPUTS_DIFFER")
        self.assertEqual(
            comparison["first_trace_difference"]["difference"]["path"], "/time_seconds"
        )

    def test_transient_frame_difference_is_detected_with_same_final_state(self):
        first, second = result(), result()
        second["combat"]["frames"][0]["actors"]["queen"]["x"] += 0.1
        comparison = compare_battle_results(first, second)
        self.assertIsNone(comparison["final_actor_difference"])
        self.assertEqual(
            comparison["first_frame_difference"]["difference"]["path"],
            "/actors/queen/x",
        )

    def test_unmatched_recording_times_do_not_claim_full_agreement(self):
        first, second = result(), result()
        second["combat"]["frames"].append(
            {"time_seconds": 2, "actors": {"queen": {"x": 3, "hp": 100}}}
        )
        comparison = compare_battle_results(first, second)
        self.assertFalse(comparison["frame_sampling_equal"])
        self.assertEqual(comparison["matched_frame_count"], 1)

    def test_extra_tail_event_is_not_lost_by_zip_comparison(self):
        first, second = result(), result()
        second["combat"]["trace"].append({"event": "death", "time_seconds": 2})
        comparison = compare_battle_results(first, second)
        self.assertEqual(comparison["equal_trace_prefix_length"], 1)
        self.assertIsNone(comparison["first_trace_difference"]["first_event"])

    def test_boolean_and_number_are_different_semantic_values(self):
        first, second = result(), result()
        second["outcome"]["town_hall_destroyed"] = 1
        self.assertIsNotNone(
            compare_battle_results(first, second)["outcome_difference"]
        )

    def test_invalid_tolerance_or_nonfinite_recorded_numbers_are_rejected(self):
        for tolerance in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(tolerance=tolerance), self.assertRaises(InputError):
                compare_battle_results(result(), result(), tolerance)
        first = result()
        first["combat"]["actors"]["queen"]["hp"] = float("nan")
        with self.assertRaises(InputError):
            compare_battle_results(first, deepcopy(first))


if __name__ == "__main__":
    unittest.main()
