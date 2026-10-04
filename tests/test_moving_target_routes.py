"""A moving primary must not send a ground pursuer back to its tile center."""

import unittest

from clashlab.spatial import simulate_spatial

from test_spatial import synthetic_scene, synthetic_structure, synthetic_unit


class MovingTargetRouteTests(unittest.TestCase):
    def test_pursuer_keeps_forward_progress_while_primary_moves(self):
        for step in (0.01, 0.1, 0.25):
            chaser = synthetic_unit(
                "chaser",
                x=0.5,
                y=3.5,
                speed=2,
                target_priorities=["unit"],
                first_attack_seconds=100,
            )
            moving_target = synthetic_unit(
                "moving-target",
                team="defense",
                x=6.5,
                y=3.5,
                speed=1,
                target_priorities=["building"],
                first_attack_seconds=100,
            )
            destination = synthetic_structure(
                "destination",
                team="attack",
                kind="building",
                x=10,
                y=3,
                counts_for_destruction=False,
                target_priorities=[],
                target_layers=[],
            )
            scene = synthetic_scene(
                [chaser, moving_target, destination],
                width=12,
                height=7,
                duration_seconds=0.5,
                maximum_step_seconds=step,
                recording_interval_seconds=1,
            )
            result = simulate_spatial(scene)
            with self.subTest(maximum_step_seconds=step):
                # Both routes are horizontal, unobstructed and begin at cell
                # centers. Neither actor reaches attack range during this run.
                self.assertAlmostEqual(result["actors"]["moving-target"]["x"], 7)
                self.assertAlmostEqual(result["actors"]["chaser"]["x"], 1.5)
                self.assertAlmostEqual(result["actors"]["chaser"]["y"], 3.5)


if __name__ == "__main__":
    unittest.main()
