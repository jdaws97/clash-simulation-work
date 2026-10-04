"""Access changes and wall edits with explicit synthetic routing policies."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.blueprints import apply_blueprint_wall_edit
from clashlab.catalog import Catalog
from clashlab.common import InputError, stable_id
from clashlab.wallprobes import inspect_wall_access


ROOT = Path(__file__).resolve().parents[1]


class WallProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def setUp(self):
        cells = {
            (x, y)
            for x in range(4, 10)
            for y in range(4, 10)
            if x in {4, 9} or y in {4, 9}
        }
        buildings = [
            {
                "instance": "town-hall-0",
                "id": "town-hall",
                "level": 16,
                "x": 5,
                "y": 5,
                "counts_for_destruction": True,
            }
        ]
        for index, (x, y) in enumerate(sorted(cells)):
            buildings.append(
                {
                    "instance": f"wall-{index}",
                    "id": "wall",
                    "level": 17,
                    "x": x,
                    "y": y,
                    "counts_for_destruction": False,
                }
            )
        self.base = {
            "width": 14,
            "height": 14,
            "town_hall": 16,
            "inventory": {"town-hall": 1, "wall": len(cells)},
            "buildings": buildings,
        }
        self.specification = {
            "source": "synthetic-wall-access-check",
            "obstacle_policy": "all_non_trap_footprints_hypothesis",
            "route_policy": "four_neighbor_minimum_walls_then_steps_hypothesis",
            "entries": [{"id": "west", "cell": [0, 6]}],
            "targets": ["town-hall-0"],
            "profiles": [
                {
                    "id": movement,
                    "movement": movement,
                    "range_tiles": 0.2,
                    "source": "synthetic-short-range-hypothesis",
                }
                for movement in (
                    "ground_avoid",
                    "ground_minimum_breaches",
                    "ground_ignore_walls",
                    "air_direct",
                )
            ],
        }

    def results(self, base=None):
        result = inspect_wall_access(
            base or self.base, self.catalog, self.specification
        )
        return result, {route["profile"]: route for route in result["routes"]}

    def open_wall(self):
        wall = next(
            item for item in self.base["buildings"] if (item["x"], item["y"]) == (4, 6)
        )
        return {
            "source": "declared-single-gap-probe",
            "base_id": stable_id(self.base),
            "moves": [{"instance": wall["instance"], "x": 12, "y": 12}],
        }

    def test_enclosure_blocks_short_reach_but_air_and_wall_bypass_reach_target(self):
        result, routes = self.results()
        self.assertEqual(result["wall_only_enclosed_region_sizes_tiles"], [16])
        self.assertFalse(routes["ground_avoid"]["reachable"])
        self.assertEqual(
            len(routes["ground_minimum_breaches"]["wall_instances_crossed"]), 1
        )
        self.assertTrue(routes["ground_ignore_walls"]["reachable"])
        self.assertTrue(routes["air_direct"]["reachable"])
        self.assertFalse(result["full_game_prediction"])

    def test_opening_changes_ground_access_preserving_air_distance_and_all_instances(
        self,
    ):
        _, original = self.results()
        candidate = apply_blueprint_wall_edit(self.base, self.catalog, self.open_wall())
        result, changed = self.results(candidate)
        self.assertEqual(candidate["inventory"], self.base["inventory"])
        self.assertEqual(len(candidate["buildings"]), len(self.base["buildings"]))
        self.assertEqual(result["wall_only_enclosed_region_sizes_tiles"], [])
        self.assertTrue(changed["ground_avoid"]["reachable"])
        self.assertEqual(
            changed["ground_minimum_breaches"]["wall_instances_crossed"], []
        )
        self.assertEqual(original["air_direct"], changed["air_direct"])
        self.assertEqual(self.base["buildings"][0], candidate["buildings"][0])

    def test_range_can_reach_across_wall_without_asserting_unit_targeting(self):
        self.specification["profiles"][0]["range_tiles"] = 2
        _, routes = self.results()
        self.assertTrue(routes["ground_avoid"]["reachable"])
        self.assertEqual(routes["ground_avoid"]["wall_instances_crossed"], [])

    def test_blocked_entries_and_missing_or_invented_policies_fail_closed(self):
        self.specification["entries"][0]["cell"] = [4, 6]
        with self.assertRaisesRegex(InputError, "occupies an obstacle"):
            self.results()
        self.specification["entries"][0]["cell"] = [0, 6]
        del self.specification["route_policy"]
        with self.assertRaisesRegex(InputError, "route_policy"):
            self.results()

    def test_wall_edit_rejects_wrong_base_nonwall_and_overlap(self):
        operation = self.open_wall()
        wrong_base = deepcopy(operation)
        wrong_base["base_id"] = "another-base"
        with self.assertRaisesRegex(InputError, "exact base"):
            apply_blueprint_wall_edit(self.base, self.catalog, wrong_base)
        operation["moves"][0]["instance"] = "town-hall-0"
        with self.assertRaisesRegex(InputError, "wall instances"):
            apply_blueprint_wall_edit(self.base, self.catalog, operation)
        operation = self.open_wall()
        operation["moves"][0].update(x=5, y=5)
        with self.assertRaisesRegex(InputError, "Overlap"):
            apply_blueprint_wall_edit(self.base, self.catalog, operation)

    def test_wall_edit_rejects_duplicate_moves_and_bounds(self):
        operation = self.open_wall()
        operation["moves"].append(deepcopy(operation["moves"][0]))
        with self.assertRaisesRegex(InputError, "unique"):
            apply_blueprint_wall_edit(self.base, self.catalog, operation)
        operation = self.open_wall()
        operation["moves"][0]["x"] = 14
        with self.assertRaisesRegex(InputError, "outside board"):
            apply_blueprint_wall_edit(self.base, self.catalog, operation)

    def test_static_probe_cannot_silently_ignore_defensive_damage_weights(self):
        self.specification["profiles"][0]["defense_dps_weight"] = 100
        with self.assertRaisesRegex(InputError, "hide combat"):
            self.results()


if __name__ == "__main__":
    unittest.main()
