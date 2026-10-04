"""Primary field provenance, immutable snapshots, and unresolved-value gates."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.stat_layers import build_statistic_branch


ROOT = Path(__file__).resolve().parents[1]


class StatisticBranchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.claims = read_json(ROOT / "data/primary-stat-claims.json")
        cls.policy = read_json(ROOT / "examples/primary-stat-policy.json")

    def test_known_equipment_changes_apply_without_mutating_the_pinned_snapshot(self):
        branch = build_statistic_branch(self.catalog, self.claims, self.policy)
        self.assertEqual(
            branch.level("giant-arrow", 18)["stats"]["projectileDamage"], 1500
        )
        self.assertEqual(
            self.catalog.level("giant-arrow", 18)["stats"]["projectileDamage"], 2000
        )
        self.assertEqual(
            branch.level("fire-heart", 18)["stats"]["selfHealingPerSecond"], 150
        )
        self.assertEqual(branch.level("fire-heart", 18)["stats"]["dpsIncrease"], 23)
        self.assertFalse(
            branch.snapshot["statistic_branch"]["full_current_patch_verified"]
        )
        self.assertNotIn("statistic_branch", self.catalog.snapshot)

    def test_unpublished_intermediate_arrow_levels_are_not_interpolated(self):
        branch = build_statistic_branch(self.catalog, self.claims, self.policy)
        self.assertEqual(
            branch.level("giant-arrow", 17), self.catalog.level("giant-arrow", 17)
        )
        provenance = branch.records["giant-arrow"]["field_provenance"]
        self.assertEqual({row["level"] for row in provenance}, {9, 12, 15, 18})

    def test_source_branch_changes_unlock_availability_only_when_selected(self):
        branch = build_statistic_branch(self.catalog, self.claims, self.policy)
        self.assertTrue(self.catalog.available("spell-tower", 4, 17))
        self.assertFalse(branch.available("spell-tower", 4, 17))
        self.assertTrue(branch.available("spell-tower", 4, 18))

    def test_unknown_intervening_snapshot_value_is_not_overwritten(self):
        catalog = deepcopy(self.catalog)
        catalog.level("giant-arrow", 18)["stats"]["projectileDamage"] = 1700
        with self.assertRaisesRegex(InputError, "review intervening"):
            build_statistic_branch(catalog, self.claims, self.policy)

    def test_same_date_conflicting_primary_values_require_resolution(self):
        claims = deepcopy(self.claims)
        alternative = deepcopy(claims[3])
        alternative["id"] = "conflicting-primary-claim"
        alternative["value"] = 1600
        claims.append(alternative)
        policy = deepcopy(self.policy)
        policy["selected_claim_ids"].append(alternative["id"])
        with self.assertRaisesRegex(InputError, "same-date"):
            build_statistic_branch(self.catalog, claims, policy)

    def test_future_claim_missing_selection_and_missing_mapping_are_rejected(self):
        policy = deepcopy(self.policy)
        policy["as_of"] = "2026-01-01"
        with self.assertRaisesRegex(InputError, "after its as-of"):
            build_statistic_branch(self.catalog, self.claims, policy)
        policy = deepcopy(self.policy)
        policy["selected_claim_ids"] = []
        with self.assertRaisesRegex(InputError, "explicitly selected"):
            build_statistic_branch(self.catalog, self.claims, policy)
        claims = deepcopy(self.claims)
        claims[3]["path"] = ["stats", "unmapped_damage_semantics"]
        with self.assertRaisesRegex(InputError, "explicit input"):
            build_statistic_branch(self.catalog, claims, self.policy)

    def test_branch_cannot_be_reapplied_as_if_it_were_an_immutable_snapshot(self):
        branch = build_statistic_branch(self.catalog, self.claims, self.policy)
        with self.assertRaisesRegex(InputError, "immutable base"):
            build_statistic_branch(branch, self.claims, self.policy)


if __name__ == "__main__":
    unittest.main()
