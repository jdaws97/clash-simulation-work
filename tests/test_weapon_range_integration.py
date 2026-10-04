"""Actual solver acquisition and attacks at non-grid-aligned range contact."""

import unittest

from clashlab.spatial import simulate_spatial
from test_spatial import synthetic_scene, synthetic_structure, synthetic_unit


class WeaponRangeIntegrationTests(unittest.TestCase):
    def test_moving_target_contact_keeps_positive_sub_tolerance_arrival(self):
        # The remaining distance can exceed the spatial range tolerance while
        # distance / speed is below that same numeric constant in seconds.
        # Dropping this arrival lets the moving target pull away repeatedly.
        death_times = []
        for step in (0.01, 0.0005):
            with self.subTest(step=step):
                result = simulate_spatial(
                    synthetic_scene(
                        [
                            synthetic_unit(
                                "pursuer",
                                x=12.288225569887006,
                                y=13.410715350815897,
                                layer="air",
                                movement="air",
                                speed=4,
                                range=2.75,
                                target_priorities=["unit"],
                            ),
                            synthetic_unit(
                                "runner",
                                team="defense",
                                x=14.5,
                                y=15.048861360687344,
                                speed=3,
                                range=0.5,
                                target_priorities=["building"],
                            ),
                            synthetic_structure(
                                "destination",
                                team="attack",
                                kind="building",
                                x=14,
                                y=20,
                                target_priorities=[],
                            ),
                        ],
                        width=30,
                        height=30,
                        duration_seconds=0.01,
                        maximum_step_seconds=step,
                        recording_interval_seconds=1,
                    )
                )
                death = result["actors"]["runner"]["death_time"]
                self.assertIsNotNone(death)
                self.assertLess(death, 0.0011)
                death_times.append(death)
        if len(death_times) == 2:
            self.assertAlmostEqual(*death_times, places=6)

    def test_stationary_defense_fires_on_exact_incoming_contact(self):
        for step in (1, 0.3, 0.1):
            with self.subTest(step=step):
                result = simulate_spatial(
                    synthetic_scene(
                        [
                            synthetic_unit(layer="air", movement="air", damage=1),
                            synthetic_structure(
                                x=3, damage=1, range=2.3, hitpoints=10000
                            ),
                        ],
                        duration_seconds=0.8,
                        recording_interval_seconds=10,
                        maximum_step_seconds=step,
                    )
                )
                hits = [
                    event for event in result["trace"] if event.get("source") == "tower"
                ]
                self.assertEqual(len(hits), 1)
                self.assertAlmostEqual(hits[0]["time_seconds"], (3.5 - 2.3 - 0.5) / 2)

    def test_cooling_weapon_retains_the_first_actor_that_enters_range(self):
        for step in (1, 0.3, 0.1):
            with self.subTest(step=step):
                result = simulate_spatial(
                    synthetic_scene(
                        [
                            synthetic_unit(
                                "slow",
                                x=1.9,
                                speed=1,
                                range=0.1,
                                layer="air",
                                movement="air",
                                damage=1,
                            ),
                            synthetic_unit(
                                "fast",
                                x=0.9,
                                speed=2,
                                range=0.1,
                                layer="air",
                                movement="air",
                                damage=1,
                            ),
                            synthetic_structure(
                                x=3,
                                first_attack_seconds=1,
                                damage=100,
                                range=1,
                                hitpoints=10000,
                            ),
                        ],
                        duration_seconds=1.1,
                        recording_interval_seconds=10,
                        maximum_step_seconds=step,
                    )
                )
                # Slow enters at 0.6, then fast at 0.8. Both are at the same
                # location when the shot becomes ready at 1.0; their names must
                # not replace the earlier acquisition with a later tie-break.
                hits = [
                    event for event in result["trace"] if event.get("source") == "tower"
                ]
                self.assertEqual([event["target"] for event in hits], ["slow"])
                self.assertAlmostEqual(hits[0]["time_seconds"], 1)

    def test_ground_weapon_contact_precedes_its_last_grid_waypoint(self):
        for step in (1, 0.3, 0.1):
            with self.subTest(step=step):
                result = simulate_spatial(
                    synthetic_scene(
                        [synthetic_unit(range=1.8), synthetic_structure()],
                        duration_seconds=3,
                        recording_interval_seconds=10,
                        maximum_step_seconds=step,
                    )
                )
                self.assertAlmostEqual(
                    result["actors"]["tower"]["death_time"], (7 - 1.8 - 0.5) / 2
                )
                self.assertAlmostEqual(result["actors"]["attacker"]["x"], 7 - 1.8)


if __name__ == "__main__":
    unittest.main()
