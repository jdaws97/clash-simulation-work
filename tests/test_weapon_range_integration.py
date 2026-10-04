"""Actual solver acquisition and attacks at non-grid-aligned range contact."""

import unittest

from clashlab.spatial import simulate_spatial
from test_spatial import synthetic_scene, synthetic_structure, synthetic_unit


class WeaponRangeIntegrationTests(unittest.TestCase):
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
