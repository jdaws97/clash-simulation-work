"""Distinct topologies, inventory preservation and visible rejected proposals."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.architectures import (
    architecture_wall_tiles,
    generate_architecture_candidates,
)
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json


ROOT = Path(__file__).resolve().parents[1]


class ArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_rectangles_and_stepped_bands_are_distinct_and_have_declared_counts(self):
        board = {"width": 20, "height": 20}
        rectangle = {
            "kind": "rectangle_outline",
            "source": "test",
            "top_left": [2, 2],
            "bottom_right": [5, 5],
        }
        band = {
            "kind": "manhattan_band",
            "source": "test",
            "center": [8, 8],
            "radius": 3,
            "thickness": 2,
        }
        rectangular_tiles = architecture_wall_tiles([rectangle], board)
        band_tiles = architecture_wall_tiles([band], board)
        self.assertEqual(len(rectangular_tiles), 12)
        self.assertEqual(len(band_tiles), 20)
        self.assertNotEqual(rectangular_tiles, band_tiles)
        self.assertNotIn((8, 8), band_tiles)

    def test_closed_polyline_and_rectangle_agree_without_duplicate_corner_walls(self):
        board = {"width": 12, "height": 12}
        polyline = {
            "kind": "orthogonal_polyline",
            "source": "test",
            "points": [[2, 2], [5, 2], [5, 5], [2, 5]],
            "closed": True,
        }
        tiles = architecture_wall_tiles([polyline, polyline], board)
        self.assertEqual(len(tiles), 12)

    def test_diagonal_segments_and_truncated_outside_bands_are_rejected(self):
        board = {"width": 12, "height": 12}
        diagonal = {
            "kind": "orthogonal_polyline",
            "source": "test",
            "points": [[2, 2], [5, 5]],
            "closed": False,
        }
        with self.assertRaisesRegex(InputError, "orthogonal"):
            architecture_wall_tiles([diagonal], board)
        band = {
            "kind": "manhattan_band",
            "source": "test",
            "center": [5, 5],
            "radius": 8,
            "thickness": 2,
        }
        with self.assertRaisesRegex(InputError, "leave"):
            architecture_wall_tiles([band], board)

    def test_search_preserves_full_inventory_and_records_invalid_proposal(self):
        configuration = read_json(ROOT / "examples/blueprint-ranked-configuration.json")
        components = [
            {
                "kind": "orthogonal_polyline",
                "source": "test",
                "points": [
                    [segment["x1"], segment["y1"]],
                    [segment["x2"], segment["y2"]],
                ],
                "closed": False,
            }
            for segment in configuration["wall_segments"]
        ]
        good = {
            "id": "reference-proposal",
            "family": "declared-reference",
            "configuration": configuration,
            "wall_components": components,
        }
        bad = deepcopy(good)
        bad["id"] = "outside-proposal"
        bad["wall_components"] = [
            {
                "kind": "manhattan_band",
                "source": "test",
                "center": [22, 22],
                "radius": 30,
                "thickness": 2,
            }
        ]
        result = generate_architecture_candidates(
            read_json(ROOT / "profiles/target-max-th16-inventory.json"),
            self.catalog,
            {
                "source": "paired-proposal-test",
                "maximum_candidates": 2,
                "geometry_probes": read_json(
                    ROOT / "examples/blueprint-probes-conditional.json"
                ),
                "proposals": [good, bad],
            },
        )
        self.assertEqual(result["accepted_count"], 1)
        self.assertEqual(result["rejected_count"], 1)
        self.assertEqual(len(result["candidates"][0]["blueprint"]["buildings"]), 467)
        self.assertIn("leave", result["rejections"][0]["reason"])
        self.assertFalse(result["performance_winner_selected"])
        self.assertFalse(result["full_game_prediction"])

    def test_search_limit_cannot_silently_drop_later_architectures(self):
        with self.assertRaisesRegex(InputError, "exceed"):
            generate_architecture_candidates(
                {},
                self.catalog,
                {
                    "source": "test",
                    "maximum_candidates": 1,
                    "proposals": [{}, {}],
                    "geometry_probes": {},
                },
            )


if __name__ == "__main__":
    unittest.main()
