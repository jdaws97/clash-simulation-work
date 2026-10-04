"""Prevent observed replay results from becoming fabricated timing calibration."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from clashlab.replay_evidence import summarize_checkpoint_dataset
from clashlab.replay_observations import ObservationError


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests/fixtures/replay-checkpoints-synthetic.json"


class ReplayEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.dataset = json.loads(DATA.read_text(encoding="utf-8"))
        self.frames = tempfile.TemporaryDirectory()
        self.addCleanup(self.frames.cleanup)
        for i, case in enumerate(self.dataset["replays"]):
            for j, point in enumerate(case["checkpoints"]):
                payload = f"synthetic checkpoint fixture {i} {j}\n".encode()
                (Path(self.frames.name) / point["evidence"]["frame"]).write_bytes(
                    payload
                )

    def test_synthetic_evidence_is_intact_and_not_calibration(self):
        result = summarize_checkpoint_dataset(self.dataset, self.frames.name)
        self.assertEqual(result["replay_count"], 2)
        self.assertEqual(result["checkpoint_count"], 8)
        self.assertEqual(result["calibrated_replay_count"], 0)
        self.assertIsNone(result["population_win_rate"])
        self.assertFalse(result["replays"][0]["town_hall_destroyed_from_final_score"])
        self.assertTrue(result["replays"][1]["town_hall_destroyed_from_final_score"])

    def test_countdown_cannot_be_promoted_to_elapsed_time(self):
        self.dataset["replays"][0]["checkpoints"][0]["battle_elapsed_seconds"] = 0
        with self.assertRaisesRegex(ObservationError, "battle elapsed"):
            summarize_checkpoint_dataset(self.dataset)

    def test_unknown_hud_values_stay_missing(self):
        result = summarize_checkpoint_dataset(self.dataset)
        self.assertFalse(result["verified_frame_hashes"])
        self.assertIsNone(
            self.dataset["replays"][0]["checkpoints"][0]["displayed_stars"]
        )

    def test_result_cannot_drop_after_observed_progress(self):
        self.dataset["replays"][0]["observed_outcome"]["destruction_percent"] = 80
        with self.assertRaisesRegex(ObservationError, "observed progress"):
            summarize_checkpoint_dataset(self.dataset)

    def test_replay_cut_requires_a_separate_case(self):
        self.dataset["replays"][0]["checkpoints"][3]["replay_remaining_seconds"] = 200
        with self.assertRaisesRegex(ObservationError, "unordered"):
            summarize_checkpoint_dataset(self.dataset)

    def test_wrong_terminal_frame_is_rejected(self):
        case = self.dataset["replays"][1]
        case["observed_outcome"]["evidence"] = deepcopy(
            case["checkpoints"][0]["evidence"]
        )
        with self.assertRaisesRegex(ObservationError, "final checkpoint"):
            summarize_checkpoint_dataset(self.dataset)

    def test_missing_and_tampered_frame_are_not_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ObservationError, "Missing or modified"):
                summarize_checkpoint_dataset(self.dataset, directory)

    def test_tampered_frame_is_rejected(self):
        point = self.dataset["replays"][0]["checkpoints"][0]
        (Path(self.frames.name) / point["evidence"]["frame"]).write_bytes(b"tampered")
        with self.assertRaisesRegex(ObservationError, "Missing or modified"):
            summarize_checkpoint_dataset(self.dataset, self.frames.name)

    def test_missing_digest_is_rejected(self):
        self.dataset["replays"][0]["checkpoints"][0]["evidence"].pop("sha256")
        with self.assertRaisesRegex(ObservationError, "SHA-256"):
            summarize_checkpoint_dataset(self.dataset)

    def test_frame_traversal_is_rejected_even_without_hash_check(self):
        point = self.dataset["replays"][0]["checkpoints"][0]
        point["evidence"]["frame"] = "../outside.jpg"
        with self.assertRaisesRegex(ObservationError, "inside"):
            summarize_checkpoint_dataset(self.dataset)


if __name__ == "__main__":
    unittest.main()
