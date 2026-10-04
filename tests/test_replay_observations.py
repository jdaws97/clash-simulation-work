"""Replay-clock, provenance and missing-evidence regression cases."""

from copy import deepcopy
import unittest

from clashlab.replay_observations import (
    ObservationError,
    compare_observations,
    map_video_interval,
)


CONTEXT = {"patch_id": "synthetic-fixture", "mode": "friendly", "modifier_id": "hard"}
SEGMENTS = [
    {
        "video_start": 100,
        "video_end": 110,
        "battle_elapsed_start": 40,
        "speed": 2,
        "evidence": "synthetic-clock-fixture",
    },
    {
        "video_start": 110,
        "video_end": 120,
        "battle_elapsed_start": 60,
        "speed": 1,
        "evidence": "synthetic-speed-change",
    },
]
EVENT = {
    "entity_id": "fixture-dragon-1",
    "kind": "projectile_impact",
    "occurrence": 1,
    "video_interval_seconds": [102, 103],
    "evidence": "synthetic-before-and-after-frames",
}


def case():
    return {
        **CONTEXT,
        "source_url": "https://example.org/synthetic-fixture",
        "selection_method": "synthetic-test-only",
        "review_method": "visual_frames",
        "clock_segments": deepcopy(SEGMENTS),
        "events": [deepcopy(EVENT)],
    }


class ReplayObservationTests(unittest.TestCase):
    def test_video_clock_is_scaled_to_battle_elapsed(self):
        self.assertEqual(map_video_interval(SEGMENTS, 102, 103), [44, 46])

    def test_intervals_across_speed_change_are_rejected(self):
        with self.assertRaisesRegex(ObservationError, "crosses"):
            map_video_interval(SEGMENTS, 109, 111)

    def test_zero_width_boundary_is_ambiguous(self):
        with self.assertRaises(ObservationError):
            map_video_interval(SEGMENTS, 110, 110)

    def test_paused_frame_cannot_establish_event_time(self):
        segments = deepcopy(SEGMENTS)
        segments[0]["speed"] = 0
        with self.assertRaisesRegex(ObservationError, "paused"):
            map_video_interval(segments, 102, 103)

    def test_mode_patch_and_modifier_must_match(self):
        for field in CONTEXT:
            for value in ["unknown", "different", None]:
                with self.subTest(field=field, value=value):
                    altered = case()
                    altered[field] = value
                    with self.assertRaises(ObservationError):
                        compare_observations(altered, [], CONTEXT)

    def test_transcript_claim_is_not_a_measured_frame(self):
        altered = case()
        altered["review_method"] = "transcript"
        with self.assertRaises(ObservationError):
            compare_observations(altered, [], CONTEXT)

    def test_missing_prediction_is_not_zero_error(self):
        result = compare_observations(case(), [], CONTEXT)
        self.assertIsNone(result["events"][0]["error_seconds"])
        self.assertEqual(result["matched_event_count"], 0)
        self.assertIsNone(result["population_win_rate"])

    def test_residual_is_distance_from_uncertainty_interval(self):
        for time, error, status in [
            (43, -1, "too_early"),
            (45, 0, "within_observed_interval"),
            (49, 3, "too_late"),
        ]:
            prediction = {**EVENT, "battle_elapsed_seconds": time}
            result = compare_observations(case(), [prediction], CONTEXT)["events"][0]
            self.assertEqual(result["error_seconds"], error)
            self.assertEqual(result["status"], status)

    def test_repeated_shot_does_not_match_wrong_occurrence(self):
        prediction = {**EVENT, "occurrence": 2, "battle_elapsed_seconds": 45}
        result = compare_observations(case(), [prediction], CONTEXT)
        self.assertEqual(result["matched_event_count"], 0)

    def test_duplicate_events_are_rejected(self):
        altered = case()
        altered["events"].append(deepcopy(EVENT))
        with self.assertRaisesRegex(ObservationError, "Duplicate"):
            compare_observations(altered, [], CONTEXT)

    def test_nan_clock_cannot_produce_nan_score(self):
        with self.assertRaises(ObservationError):
            map_video_interval(SEGMENTS, float("nan"), 103)


if __name__ == "__main__":
    unittest.main()
