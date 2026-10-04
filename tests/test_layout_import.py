"""Memory disagreement and missing slots must not become simulated certainty."""

from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.layout_import import (
    preview_layout,
    resolve_layout_objects,
    select_home_observations,
)


class LayoutImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")
        cls.inventory = {"town-hall": {"count": 1}, "wall": {"count": 2}}
        cls.transform = {"level_offset": 1, "coordinate_offset": 3, "board_size": 44}

    def observation(self, **changes):
        fields = {"id": 500000000, "data": 1000001, "lvl": 15, "x": 3, "y": 43}
        fields.update(changes)
        return {"fields": fields, "copies_seen": 100}

    def preview(self, candidates, slot="home_xy"):
        return preview_layout(
            resolve_layout_objects(candidates),
            self.catalog,
            self.inventory,
            slot,
            self.transform,
        )

    def test_conflict_cannot_be_outvoted_by_copy_count(self):
        first = self.observation()
        second = self.observation(x=9)
        second["copies_seen"] = 1
        result = self.preview([first, second])
        self.assertEqual(result["records"], [])
        self.assertEqual(
            result["rejected_records"][0]["missing_or_conflicting_fields"], ["x"]
        )

    def test_saved_slot_never_falls_back_to_home(self):
        result = self.preview([self.observation()], "l4x")
        self.assertEqual(result["records"], [])
        self.assertEqual(result["missing_inventory"]["town-hall"], 1)

    def test_partial_agreement_keeps_observed_slot_and_reports_gaps(self):
        result = self.preview(
            [self.observation(l4x=[21, 23]), self.observation()], "l4x"
        )
        self.assertEqual(result["records"][0]["raw_position"], [21, 23])
        self.assertEqual(result["records"][0]["level_hypothesis"], 16)
        self.assertEqual(result["missing_inventory"], {"wall": 2})
        self.assertFalse(result["active_slot_verified"])
        self.assertNotIn("buildings", result)

    def test_irrelevant_slot_conflict_does_not_erase_home_but_is_visible(self):
        result = self.preview(
            [self.observation(l4x=[21, 23]), self.observation(l4x=[22, 23])]
        )
        self.assertEqual(len(result["records"]), 1)
        self.assertIn("l4x", result["records"][0]["unresolved_fields"])

    def test_sensitive_fields_are_not_retained(self):
        result = resolve_layout_objects([self.observation(token="not-for-export")])
        self.assertNotIn("token", result[0]["agreed_fields"])

    def test_reused_builder_id_does_not_corrupt_home_identity(self):
        observations = [
            self.observation(),
            self.observation(data=1000033, x=10, y=10),
            self.observation(id=500000001, data=1999999),
        ]
        selected = select_home_observations(observations, self.catalog)
        self.assertEqual(len(selected), 1)
        result = self.preview(selected)
        self.assertEqual(result["records"][0]["id"], "town-hall")
        self.assertEqual(result["records"][0]["unresolved_fields"], {})

    def test_unplaced_objects_are_not_projected_into_board(self):
        result = self.preview([self.observation(l4x=[-1, -1])], "l4x")
        self.assertEqual(result["records"], [])
        self.assertEqual(result["rejected_records"][0]["reason"], "UNPLACED_SENTINEL")

    def test_observed_extra_structure_is_visible_without_rewriting_target_inventory(
        self,
    ):
        result = self.preview([self.observation(data=1000097, lvl=0, x=21, y=31)])
        self.assertEqual(result["records"][0]["id"], "crafting-station")
        self.assertEqual(result["excess_inventory"], {"crafting-station": 1})
        self.assertNotIn("crafting-station", self.inventory)

    def test_adjacent_live_xbow_positions_fit_the_corrected_footprint(self):
        result = self.preview(
            [
                self.observation(data=1000021, lvl=9, x=23, y=41),
                self.observation(id=500000001, data=1000021, lvl=9, x=23, y=44),
            ]
        )
        self.assertEqual(result["catalog_footprint_overlaps"], [])
        self.assertEqual(result["out_of_bounds"], [])
        self.assertEqual(result["records"][0]["width"], 3)


if __name__ == "__main__":
    unittest.main()
