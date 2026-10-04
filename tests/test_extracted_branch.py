"""Independent source quantities, exact selections and reproducible branches."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.extracted_branch import build_extracted_branch
from clashlab.source_audit import audit_extracted_source

from test_adapters import entity_instance, sector


ROOT = Path(__file__).resolve().parents[1]


class ExtractedBranchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.extracted = read_json(ROOT / "data/clashking-static-data.json")
        cls.provenance = read_json(ROOT / "data/clashking-static-source.json")
        cls.selection = read_json(ROOT / "data/extracted-stat-selection.json")

    def branch(self, selection=None, extracted=None):
        return build_extracted_branch(
            self.catalog,
            self.extracted if extracted is None else extracted,
            self.provenance,
            self.selection if selection is None else selection,
        )

    def test_dps_change_updates_shot_damage_without_mutating_original(self):
        branch = self.branch()
        row = branch.level("thrower", 3)
        self.assertEqual(row["hitpoints"], 2500)
        self.assertEqual(row["stats"]["normal"]["dps"], 220)
        self.assertEqual(row["stats"]["normal"]["damagePerShot"], 550)
        self.assertEqual(branch.entity("thrower")["movementSpeed"], 16)
        self.assertEqual(self.catalog.level("thrower", 3)["hitpoints"], 2600)
        self.assertEqual(self.catalog.entity("thrower")["movementSpeed"], 18)
        self.assertEqual(branch.level("thrower", 2), self.catalog.level("thrower", 2))
        self.assertFalse(
            branch.snapshot["statistic_branch"]["full_current_patch_verified"]
        )

    def test_sector_requires_exact_extraction_policy_and_uses_changed_speed(self):
        branch = self.branch()
        scene = sector(
            branch,
            [
                entity_instance("thrower", "thrower", 2, "attack"),
                entity_instance("tower", "cannon", 21, "defense"),
            ],
        )
        with self.assertRaisesRegex(InputError, "unchanged snapshot"):
            compile_entity_scene(scene, branch)
        scene["statistics_policy"].update(
            kind="conditional_extracted_fields",
            branch_policy=branch.snapshot["statistic_branch"]["policy"],
        )
        compiled = compile_entity_scene(scene, branch)
        self.assertEqual(compiled["scene"]["actors"][0]["speed"], 2)
        scene["statistics_policy"]["kind"] = "conditional_primary_publications"
        with self.assertRaises(InputError):
            compile_entity_scene(scene, branch)

    def test_changed_original_value_or_conflicting_interval_requires_review(self):
        selection = deepcopy(self.selection)
        selection[0]["expected_catalog_value"] = 123
        with self.assertRaisesRegex(InputError, "changed since"):
            self.branch(selection=selection)
        extracted = deepcopy(self.extracted)
        thrower = next(
            item for item in extracted["troops"] if item["name"] == "Thrower"
        )
        thrower["attack_speed"] = 2600
        with self.assertRaisesRegex(InputError, "Conflicting attack intervals"):
            self.branch(extracted=extracted)

    def test_ambiguous_fields_cannot_be_silently_overridden(self):
        selection = [
            {
                "entity": "dragon",
                "level": None,
                "field": "range",
                "expected_catalog_value": 3,
            }
        ]
        with self.assertRaisesRegex(InputError, "only maps"):
            self.branch(selection)

    def test_audit_compares_initial_inferno_dps_and_excludes_burst_intervals(self):
        report = audit_extracted_source(self.catalog, self.extracted, self.provenance)
        differences = report["differences"]
        self.assertFalse(any(row["entity"] == "inferno-tower" for row in differences))
        self.assertFalse(
            any(
                row["entity"] == "eagle-artillery" and row["field"] == "attackSpeed"
                for row in differences
            )
        )
        self.assertTrue(
            any(
                row["entity"] == "thrower"
                and row["field"] == "movement_tiles_per_second"
                and row["extracted_value"] == 2
                for row in differences
            )
        )
        self.assertEqual(len(report["semantic_exclusions"]), 10)


if __name__ == "__main__":
    unittest.main()
