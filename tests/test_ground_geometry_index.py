"""Geometry acceleration must preserve routes, health and paid battle events."""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from clashlab.catalog import Catalog
from clashlab.full_battle import simulate_full_battle
from clashlab.spatial import (
    EPSILON,
    ground_attack_point,
    ground_attack_points,
    target_distance,
    _ground_attack_points,
    simulate_spatial,
)
from test_adapters import entity_instance
from test_advanced_spell_integration import jump_battle
from test_walls import wall_parameters, wall_scene


class GroundGeometryIndexTests(unittest.TestCase):
    def test_index_matches_direct_terminal_and_center_geometry_at_edges_seams_and_ranges(
        self,
    ):
        for x, y, width, height in (
            (0, 0, 0, 0),
            (7, 4, 3, 2),
            (6.999999999999998, 3.25, 0, 0),
            (11.75, 9.125, 0.5, 0.75),
            (17, 13, 3, 3),
        ):
            target = dict(x=x, y=y, width=width, height=height)
            for reach in (0, 0.4, 1, 5, 13):
                for terminal in (False, True):
                    points = ground_attack_points(
                        target, reach, 20, 16, terminal=terminal
                    )
                    for cx in range(20):
                        for cy in range(16):
                            cell = cx, cy
                            if terminal:
                                expected = ground_attack_point(cell, target, reach)
                            else:
                                expected = cx + 0.5, cy + 0.5
                                if target_distance(expected, target) > reach + EPSILON:
                                    expected = None
                            self.assertEqual(points.get(cell), expected)
        self.assertIsNone(ground_attack_points(target, 100, 300, 300))
        self.assertEqual(_ground_attack_points.cache_info().maxsize, 256)

    def test_live_wall_health_freeze_and_breach_motion_match_direct_search_exactly(
        self,
    ):
        for kind in ("clear_obstructions", "penetrate_obstructions"):
            scene = wall_scene(kind, duration_seconds=4)
            scene["effects"] = [
                dict(
                    id="freeze",
                    kind="freeze",
                    time_seconds=0.2,
                    targets=["breacher"],
                    duration_seconds=0.65,
                )
            ]
            indexed = simulate_spatial(deepcopy(scene))
            with patch("clashlab.spatial._ground_attack_points", return_value=None):
                direct = simulate_spatial(deepcopy(scene))
            self.assertEqual(indexed, direct)
            self.assertLess(indexed["actors"]["wall-3"]["hp"], 300)
            if kind == "clear_obstructions":
                self.assertIsNotNone(indexed["actors"]["wall-3"]["death_time"])

    def test_paid_root_breach_and_follower_have_identical_receipts_clocks_resources_and_outcome(
        self,
    ):
        catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")
        for step in (0.017, 0.25):
            inputs = jump_battle(catalog, step, selected=False, duration=15)
            spec, account, army, _ = inputs
            scene = spec["entity_scene"]
            scene["entities"][0]["modifiers"]["hitpoints_multiplier"] = 0.02
            scene["entities"][1].update(x=0.5, first_attack_seconds=0)
            root = entity_instance(
                "root",
                "root-rider",
                1,
                "attack",
                x=0.5,
                y=5.5,
                wall_parameters=wall_parameters(),
            )
            scene["entities"].append(root)
            army["troops"].append(dict(id="root-rider", level=1, count=1))
            account["levels"]["root-rider"] = 1
            indexed = simulate_full_battle(*deepcopy(inputs), catalog)
            with (
                patch("clashlab.spatial._ground_attack_points", return_value=None),
                patch(
                    "clashlab.spatial._retained_primary_stays_in_range",
                    return_value=False,
                ),
            ):
                direct = simulate_full_battle(*deepcopy(inputs), catalog)
            self.assertEqual(indexed, direct)
            self.assertTrue(indexed["outcome"]["town_hall_destroyed"])
            self.assertEqual(
                indexed["resource_use"]["deployed_attacker_ids"], ["pekka-0", "root"]
            )
            self.assertTrue(
                any(e.get("event") == "wall_impact" for e in indexed["combat"]["trace"])
            )


if __name__ == "__main__":
    unittest.main()
