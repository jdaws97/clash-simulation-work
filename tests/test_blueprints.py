"""Inventory, evidence and geometry checks for complete declared base drafts."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.blueprints import (
    apply_blueprint_swap,
    generate_blueprint,
    inspect_blueprint,
    screen_blueprint_swaps,
)
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json, stable_id
from clashlab.geometry import validate_layout


ROOT = Path(__file__).resolve().parents[1]


class BlueprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.target = read_json(ROOT / "profiles/target-max-th16-inventory.json")
        cls.configuration = read_json(
            ROOT / "examples/blueprint-ranked-configuration.json"
        )
        cls.blueprint = generate_blueprint(cls.target, cls.catalog, cls.configuration)

    def test_complete_target_preserves_every_wall_trap_and_merged_defense(self):
        result = inspect_blueprint(
            self.blueprint,
            self.catalog,
            read_json(ROOT / "examples/blueprint-probes-conditional.json"),
        )
        expected = {
            key: item["count"] for key, item in self.target["inventory"].items()
        }
        self.assertEqual(result["inventory_counts"], expected)
        self.assertEqual(result["validation"]["building_count"], 467)
        # Four X-Bows occupy 3x3 each; the old 4x4 source overstated this by 28.
        self.assertEqual(result["validation"]["occupied_tiles"], 1218)
        self.assertEqual(result["inventory_counts"]["wall"], 325)
        self.assertEqual(result["inventory_counts"]["archer-tower"], 4)
        self.assertEqual(result["inventory_counts"]["cannon"], 3)
        self.assertFalse(result["battle_ready"])

    def test_unknown_destruction_and_non_upgradable_banners_are_preserved(self):
        self.assertTrue(
            any(
                item["counts_for_destruction"] is None
                for item in self.blueprint["buildings"]
            )
        )
        banners = [
            item for item in self.blueprint["buildings"] if item["id"] == "hero-banner"
        ]
        self.assertTrue(all(item["level"] is None for item in banners))
        self.assertEqual(len({item["settings"]["hero"] for item in banners}), 4)
        self.assertFalse(
            validate_layout(self.blueprint, self.catalog, False)[
                "destruction_eligibility_complete"
            ]
        )
        with self.assertRaisesRegex(InputError, "Destruction eligibility"):
            validate_layout(self.blueprint, self.catalog)

    def test_board_and_statistic_evidence_cannot_silently_default(self):
        for field in ("verification", "source", "width"):
            configuration = deepcopy(self.configuration)
            del configuration["board"][field]
            with self.subTest(field=field), self.assertRaises(InputError):
                generate_blueprint(self.target, self.catalog, configuration)
        configuration = deepcopy(self.configuration)
        configuration["statistics_policy"]["snapshot_commit"] = "wrong"
        with self.assertRaisesRegex(InputError, "exact catalog snapshot"):
            generate_blueprint(self.target, self.catalog, configuration)

    def test_overlap_unknown_modes_and_absent_instances_fail_before_packing(self):
        configuration = deepcopy(self.configuration)
        configuration["fixed_placements"]["town-hall-0"] = [4, 4]
        with self.assertRaisesRegex(InputError, "overlaps"):
            generate_blueprint(self.target, self.catalog, configuration)
        configuration = deepcopy(self.configuration)
        configuration["modes"]["spell-tower-0"] = "unknown-mode"
        with self.assertRaisesRegex(InputError, "unknown defense mode"):
            generate_blueprint(self.target, self.catalog, configuration)
        configuration = deepcopy(self.configuration)
        configuration["fixed_placements"]["firespitter-0"] = [8, 8]
        with self.assertRaisesRegex(InputError, "absent target instance"):
            generate_blueprint(self.target, self.catalog, configuration)

    def test_th16_cannot_select_earthquake_tower_mode(self):
        blueprint = deepcopy(self.blueprint)
        tower = next(
            item for item in blueprint["buildings"] if item["id"] == "spell-tower"
        )
        tower["mode"] = "earthquake"
        with self.assertRaisesRegex(InputError, "not unlocked"):
            validate_layout(blueprint, self.catalog, False)
        self.assertNotIn(
            "earthquake", self.target["inventory"]["spell-tower"]["mode_choices"]
        )

    def test_missing_walls_and_consumed_parent_double_count_are_rejected(self):
        blueprint = deepcopy(self.blueprint)
        blueprint["buildings"] = [
            item for item in blueprint["buildings"] if item["instance"] != "wall-0"
        ]
        with self.assertRaisesRegex(InputError, "explicit inventory"):
            validate_layout(blueprint, self.catalog, False)
        blueprint = deepcopy(self.blueprint)
        extra = deepcopy(
            next(item for item in blueprint["buildings"] if item["id"] == "cannon")
        )
        extra.update(instance="extra-cannon", x=4, y=0)
        blueprint["buildings"].append(extra)
        blueprint["inventory"]["cannon"] += 1
        with self.assertRaisesRegex(InputError, "Merged defenses double-count"):
            validate_layout(blueprint, self.catalog, False)

    def test_geometry_probe_does_not_claim_performance_or_invent_weights(self):
        probes = read_json(ROOT / "examples/blueprint-probes-conditional.json")
        result = inspect_blueprint(self.blueprint, self.catalog, probes)
        self.assertEqual(result["maximum_key_anchors_under_declared_disc"], 5)
        self.assertEqual(result["town_hall_boundary_distance_tiles"], 19)
        self.assertNotIn("triple_rate", result)
        self.assertFalse(result["battle_ready"])
        self.assertEqual(
            self.blueprint["board_evidence"]["verification"], "declared_hypothesis"
        )

    def test_equal_footprint_swap_preserves_modes_inventory_and_unknown_flags(self):
        operation = {
            "source": "declared-swap-fixture",
            "base_id": stable_id(self.blueprint),
            "first": "monolith-0",
            "second": "air-defense-0",
        }
        candidate = apply_blueprint_swap(self.blueprint, self.catalog, operation)
        original = {item["instance"]: item for item in self.blueprint["buildings"]}
        changed = {item["instance"]: item for item in candidate["buildings"]}
        self.assertEqual(
            (changed["monolith-0"]["x"], changed["monolith-0"]["y"]),
            (original["air-defense-0"]["x"], original["air-defense-0"]["y"]),
        )
        self.assertEqual(changed["monolith-0"]["mode"], original["monolith-0"]["mode"])
        self.assertIsNone(changed["monolith-0"]["counts_for_destruction"])
        self.assertEqual(candidate["inventory"], self.blueprint["inventory"])
        self.assertFalse(candidate["full_game_prediction"])
        operation["base_id"] = "a-different-base"
        with self.assertRaisesRegex(InputError, "exact base blueprint"):
            apply_blueprint_swap(self.blueprint, self.catalog, operation)

    def test_incompatible_swaps_are_not_packed_or_silently_resized(self):
        operation = {
            "source": "declared-swap-fixture",
            "base_id": stable_id(self.blueprint),
            "first": "town-hall-0",
            "second": "monolith-0",
        }
        with self.assertRaisesRegex(InputError, "equal non-wall"):
            apply_blueprint_swap(self.blueprint, self.catalog, operation)

    def test_swap_search_returns_geometry_candidates_without_a_performance_winner(self):
        settings = {
            "source": "declared-search-fixture",
            "maximum_candidates": 5,
            "movable_instance_ids": ["monolith-0", "air-defense-0", "town-hall-0"],
            "probes": read_json(ROOT / "examples/blueprint-probes-conditional.json"),
        }
        result = screen_blueprint_swaps(self.blueprint, self.catalog, settings)
        self.assertEqual(result["candidate_count"], 1)
        self.assertFalse(result["performance_winner_selected"])
        self.assertEqual(
            result["candidates"][0]["operation"]["base_id"], stable_id(self.blueprint)
        )

    def test_gearing_policy_cannot_hide_selected_geared_modes(self):
        configuration = deepcopy(self.configuration)
        configuration["modes"]["cannon-0"] = "gearedUpBurst"
        with self.assertRaisesRegex(InputError, "no-gearing policy"):
            generate_blueprint(self.target, self.catalog, configuration)


if __name__ == "__main__":
    unittest.main()
