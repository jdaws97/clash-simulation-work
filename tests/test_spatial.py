"""Feedback checks for the declared synthetic spatial kernel, not game fidelity."""

import unittest
from copy import deepcopy

from clashlab.common import InputError
from clashlab.spatial import MODEL_RULES, RULESET, _ground_route, simulate_spatial


def synthetic_unit(actor_id="attacker", **changes):
    actor = {
        "id": actor_id,
        "source": "synthetic-spatial-contract-fixture",
        "team": "attack",
        "kind": "unit",
        "layer": "ground",
        "movement": "ground",
        "hitpoints": 100,
        "first_attack_seconds": 0,
        "spawn_seconds": 0,
        "damage": 100,
        "attack_interval_seconds": 1,
        "speed": 2,
        "range": 0.6,
        "blocking": False,
        "counts_for_destruction": False,
        "target_priorities": ["defense"],
        "target_layers": ["ground"],
        "x": 0.5,
        "y": 3.5,
        "width": 0,
        "height": 0,
    }
    actor.update(changes)
    return actor


def synthetic_structure(actor_id="tower", **changes):
    actor = {
        "id": actor_id,
        "source": "synthetic-spatial-contract-fixture",
        "team": "defense",
        "kind": "defense",
        "layer": "ground",
        "movement": "stationary",
        "hitpoints": 100,
        "first_attack_seconds": 0,
        "spawn_seconds": 0,
        "damage": 0,
        "attack_interval_seconds": 1,
        "speed": 0,
        "range": 0,
        "blocking": True,
        "counts_for_destruction": True,
        "target_priorities": ["unit"],
        "target_layers": ["ground", "air"],
        "x": 7,
        "y": 3,
        "width": 1,
        "height": 1,
    }
    actor.update(changes)
    return actor


def synthetic_scene(actors=None, effects=None, **changes):
    scene = {
        "id": "synthetic-spatial-contract-fixture",
        "ruleset": RULESET,
        "model_rules": deepcopy(MODEL_RULES),
        "unsupported_mechanics": [],
        "width": 9,
        "height": 7,
        "duration_seconds": 8,
        "maximum_step_seconds": 0.25,
        "recording_interval_seconds": 0.5,
        "actors": (
            [synthetic_unit(), synthetic_structure()] if actors is None else actors
        ),
        "effects": [] if effects is None else effects,
    }
    scene.update(changes)
    return scene


def barrier(opening=False):
    return [
        synthetic_structure(f"wall-{row}", kind="wall", x=4, y=row)
        for row in range(6 if opening else 7)
    ]


class SpatialTests(unittest.TestCase):
    def test_ground_replanning_is_stable_at_free_grid_seams(self):
        target = synthetic_structure(x=14, y=33)
        for offset in (-1e-14, 0, 1e-14):
            actor = synthetic_unit(x=10 + offset, y=31.5, range=3)
            route = _ground_route(actor, target, set(), 56, 56)
            self.assertEqual(route[0], (10.5, 31.5))
        # Positions outside the numeric tolerance and occupied neighboring
        # cells must not be reassigned to the canonical cell.
        actor = synthetic_unit(x=10 - 1e-6, y=31.5, range=3)
        self.assertEqual(_ground_route(actor, target, set(), 56, 56)[0], (9.5, 31.5))
        actor["x"] = 10 - 1e-14
        self.assertEqual(
            _ground_route(actor, target, {(10, 31)}, 56, 56)[0], (9.5, 31.5)
        )

    def test_air_route_completion_attack_is_independent_of_coarse_step(self):
        for step in (0.3, 0.1):
            with self.subTest(step=step):
                result = simulate_spatial(
                    synthetic_scene(
                        [
                            synthetic_unit(layer="air", movement="air", range=0.8),
                            synthetic_structure(x=2),
                        ],
                        maximum_step_seconds=step,
                        duration_seconds=0.8,
                    )
                )
                self.assertAlmostEqual(result["actors"]["tower"]["death_time"], 0.35)
                self.assertAlmostEqual(result["actors"]["attacker"]["x"], 1.2)

    def test_ground_unit_keeps_progress_between_solver_steps(self):
        result = simulate_spatial(synthetic_scene())
        self.assertEqual(result["actors"]["tower"]["hp"], 0)
        # Contact is at x=7-0.6, before the final grid waypoint at x=6.5.
        self.assertAlmostEqual(
            result["actors"]["tower"]["death_time"], (7 - 0.6 - 0.5) / 2
        )
        positions = [frame["actors"]["attacker"]["x"] for frame in result["frames"]]
        self.assertEqual(positions, sorted(positions))
        self.assertAlmostEqual(result["actors"]["attacker"]["x"], 6.4)

    def test_ground_path_detours_through_real_gap(self):
        direct = simulate_spatial(synthetic_scene())
        detour = simulate_spatial(
            synthetic_scene([synthetic_unit(), synthetic_structure(), *barrier(True)])
        )
        self.assertEqual(detour["actors"]["tower"]["hp"], 0)
        self.assertGreater(
            detour["actors"]["tower"]["death_time"],
            direct["actors"]["tower"]["death_time"],
        )
        self.assertTrue(
            any(frame["actors"]["attacker"]["y"] >= 6 for frame in detour["frames"])
        )

    def test_unreachable_ground_target_is_not_attacked_through_walls(self):
        result = simulate_spatial(
            synthetic_scene([synthetic_unit(), synthetic_structure(), *barrier()])
        )
        self.assertEqual(result["actors"]["tower"]["hp"], 100)
        self.assertAlmostEqual(result["actors"]["attacker"]["x"], 0.5)
        self.assertEqual(result["trace"], [])

    def test_air_unit_crosses_same_wall_barrier(self):
        actors = [
            synthetic_unit(layer="air", movement="air"),
            synthetic_structure(),
            *barrier(),
        ]
        result = simulate_spatial(synthetic_scene(actors))
        self.assertEqual(result["actors"]["tower"]["hp"], 0)
        self.assertLess(result["actors"]["tower"]["death_time"], 4)

    def test_destroyed_blocker_reopens_path_and_changes_combat(self):
        actors = [synthetic_unit(), synthetic_structure(), *barrier()]
        scene = synthetic_scene(
            actors,
            [
                {
                    "id": "synthetic-core-clear",
                    "time_seconds": 1,
                    "kind": "damage",
                    "amount": 100,
                    "targets": ["wall-3"],
                }
            ],
        )
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["tower"]["hp"], 0)
        self.assertAlmostEqual(
            result["actors"]["tower"]["death_time"], 1 + (7 - 0.6 - 0.5) / 2
        )

    def test_mutual_lethal_hits_are_simultaneous_in_both_input_orders(self):
        actors = [
            synthetic_unit(x=6.5, damage=100),
            synthetic_structure(damage=100, range=2),
        ]
        for ordering in (actors, list(reversed(actors))):
            with self.subTest(order=[actor["id"] for actor in ordering]):
                result = simulate_spatial(synthetic_scene(ordering))
                self.assertEqual(result["actors"]["attacker"]["hp"], 0)
                self.assertEqual(result["actors"]["tower"]["hp"], 0)
                self.assertEqual(result["actors"]["attacker"]["death_time"], 0)
                self.assertEqual(result["actors"]["tower"]["death_time"], 0)

    def test_earlier_protection_changes_survival_with_recomputed_enemy_hits(self):
        actors = [
            synthetic_unit(x=6.5, hitpoints=60, damage=40),
            synthetic_structure(damage=30, range=2),
        ]
        baseline = simulate_spatial(synthetic_scene(actors))
        outcomes = {}
        for timing in (1, 2):
            outcomes[timing] = simulate_spatial(
                synthetic_scene(
                    actors,
                    [
                        {
                            "id": "synthetic-freeze",
                            "time_seconds": timing,
                            "kind": "freeze",
                            "duration_seconds": 2,
                            "targets": ["tower"],
                        }
                    ],
                )
            )
        self.assertEqual(baseline["actors"]["attacker"]["hp"], 0)
        self.assertEqual(outcomes[1]["actors"]["attacker"]["hp"], 30)
        self.assertEqual(outcomes[1]["actors"]["tower"]["hp"], 0)
        self.assertEqual(outcomes[2]["actors"]["attacker"]["hp"], 0)
        self.assertEqual(outcomes[2]["actors"]["tower"]["hp"], 20)

    def test_invulnerability_expiry_allows_hits_at_its_exact_boundary(self):
        scene = synthetic_scene(
            [
                synthetic_unit(x=6.5, damage=20, attack_interval_seconds=0.75),
                synthetic_structure(),
            ],
            [
                {
                    "id": "synthetic-protection",
                    "time_seconds": 0,
                    "kind": "invulnerability",
                    "duration_seconds": 1.5,
                    "targets": ["tower"],
                }
            ],
            duration_seconds=1.5,
        )
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["tower"]["hp"], 80)
        self.assertEqual(
            [hit["protected"] for hit in result["trace"] if "source" in hit],
            [True, True, False],
        )

    def test_stationary_defense_prefers_nearest_target_over_identifier(self):
        actors = [
            synthetic_unit("a-far", x=0.5, damage=0),
            synthetic_unit("z-near", x=6.5, damage=0),
            synthetic_structure(damage=20, range=9),
        ]
        result = simulate_spatial(synthetic_scene(actors, duration_seconds=0.25))
        self.assertEqual(result["actors"]["a-far"]["hp"], 100)
        self.assertEqual(result["actors"]["z-near"]["hp"], 80)

    def test_delayed_deployment_does_not_move_or_attack_early(self):
        result = simulate_spatial(
            synthetic_scene([synthetic_unit(spawn_seconds=1.75), synthetic_structure()])
        )
        self.assertAlmostEqual(
            result["actors"]["tower"]["death_time"], 1.75 + (7 - 0.6 - 0.5) / 2
        )
        for frame in result["frames"]:
            if frame["time_seconds"] < 1.75:
                self.assertFalse(frame["actors"]["attacker"]["active"])
                self.assertAlmostEqual(frame["actors"]["attacker"]["x"], 0.5)

    def test_zero_damage_unit_still_cannot_spawn_inside_blocking_building(self):
        scene = synthetic_scene(
            [synthetic_unit(x=7.5, damage=0), synthetic_structure()]
        )
        with self.assertRaisesRegex(InputError, "blocking footprint"):
            simulate_spatial(scene)

    def test_resolution_changes_are_checked_against_terminal_results(self):
        results = []
        for step in (0.5, 0.25, 0.125):
            scene = synthetic_scene(maximum_step_seconds=step)
            result = simulate_spatial(scene)
            results.append(result)
        for result in results:
            self.assertEqual(result["actors"]["tower"]["hp"], 0)
            self.assertAlmostEqual(
                result["actors"]["tower"]["death_time"], (7 - 0.6 - 0.5) / 2
            )
            self.assertFalse(result["full_game_prediction"])

    def test_unimplemented_mechanics_and_unselected_conventions_fail_closed(self):
        unsupported = synthetic_scene(unsupported_mechanics=["chain-damage"])
        with self.assertRaisesRegex(InputError, "not implemented"):
            simulate_spatial(unsupported)
        omitted = synthetic_scene()
        del omitted["model_rules"]["ground_path"]
        with self.assertRaisesRegex(InputError, "explicitly selected"):
            simulate_spatial(omitted)

    def test_game_entities_are_not_silently_replaced_by_generic_actors(self):
        scene = synthetic_scene()
        scene["actors"][0]["catalog_entity"] = "root-rider"
        with self.assertRaisesRegex(InputError, "behavior adapters"):
            simulate_spatial(scene)


if __name__ == "__main__":
    unittest.main()
