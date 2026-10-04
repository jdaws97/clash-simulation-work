"""Role-specific roster coverage must not promote defense into attack support."""

from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import read_json
from clashlab.defending_heroes import DEFENDING_HEROES
from clashlab.garrisons import GARRISON_MEMBERS
from clashlab.engine_coverage import build_engine_coverage


ROOT = Path(__file__).resolve().parents[1]


class EngineCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = build_engine_coverage(
            Catalog.load(ROOT / "data"),
            read_json(ROOT / "data/clashking-static-data.json"),
            read_json(ROOT / "data/clashking-static-source.json"),
            read_json(ROOT / "data/extracted-stat-selection.json"),
        )
        cls.rows = {row["id"]: row for row in cls.report["entities"]}

    def test_five_supported_defenders_are_conditional_in_all_opponent_roles(self):
        for entity_id in DEFENDING_HEROES:
            row = self.rows[entity_id]
            for town_hall in ("16", "17", "18"):
                with self.subTest(entity=entity_id, town_hall=town_hall):
                    self.assertEqual(
                        row["opponent_status_by_town_hall"][town_hall],
                        "available_defending_conditional_mechanics",
                    )
                    role = row["opponent_behavior_by_town_hall"][town_hall]
                    self.assertEqual(role["status"], "conditional_mechanics")
                    self.assertTrue(role["registry"]["available"])
                    self.assertFalse(role["replay_calibrated"])
                    self.assertFalse(role["complete_battle_ready"])
            self.assertEqual(
                row["behavior"]["defending_hero_behavior"],
                "conditional_banner_bound_defending_behavior",
            )

    def test_king_and_minion_prince_have_separate_conditional_attacking_roles(self):
        for entity_id in ("barbarian-king", "minion-prince"):
            with self.subTest(entity=entity_id):
                behavior = self.rows[entity_id]["behavior"]
                self.assertEqual(behavior["status"], "conditional_mechanics")
                self.assertTrue(behavior["registry"]["available"])
                self.assertIn("extended_hero_roster", behavior["registry"]["scope"])
                self.assertEqual(
                    behavior["defending_role"]["status"], "conditional_mechanics"
                )
        counted_attack_options = sum(
            row["th16_attack_eligible"]
            and row["behavior"]["status"] == "conditional_mechanics"
            for row in self.rows.values()
        )
        self.assertEqual(
            self.report["summary"]["th16_attack_with_conditional_mechanics"],
            counted_attack_options,
        )

    def test_dragon_duke_attack_support_does_not_imply_defense_support(self):
        row = self.rows["dragon-duke"]
        self.assertEqual(row["behavior"]["status"], "conditional_mechanics")
        self.assertTrue(row["behavior"]["registry"]["available"])
        for town_hall in ("16", "17", "18"):
            self.assertEqual(
                row["opponent_behavior_by_town_hall"][town_hall]["status"],
                "missing_behavior",
            )
            self.assertFalse(
                row["opponent_behavior_by_town_hall"][town_hall]["registry"][
                    "available"
                ]
            )

    def test_banner_is_bound_metadata_without_a_normal_damageable_adapter(self):
        row = self.rows["hero-banner"]
        self.assertEqual(row["behavior"]["status"], "not_battle_actor")
        self.assertFalse(row["behavior"]["registry"]["available"])
        self.assertIn("separate defending hero", row["behavior"]["implemented"])
        for town_hall in ("16", "17", "18"):
            self.assertEqual(
                row["opponent_status_by_town_hall"][town_hall],
                "available_defending_banner_metadata",
            )
        village_blocker = self.report["prioritized_blockers"][0]
        self.assertNotIn("hero-banner", village_blocker["remaining_entities"])

    def test_warden_role_explains_statue_and_explicit_destruction_policy(self):
        role = self.rows["grand-warden"]["behavior"]["defending_role"]
        self.assertIn("Stationary Warden statue", role["implemented"])
        self.assertIn("counted/excluded", role["implemented"])

    def test_spell_tower_modes_require_lifecycle_and_do_not_promote_earthquake(self):
        row = self.rows["spell-tower"]
        modes = {mode["id"]: mode for mode in row["mode_variants"]}
        for mode in ("rage", "poison", "invisibility"):
            self.assertTrue(modes[mode]["conditional_weapon_registered"])
            self.assertTrue(modes[mode]["requires_entity_lifecycle"])
        self.assertFalse(modes["earthquake"]["conditional_weapon_registered"])
        self.assertIn("Earthquake remains unsupported", row["behavior"]["implemented"])

    def test_role_coverage_does_not_infer_calibration_or_complete_battle_readiness(
        self,
    ):
        self.assertEqual(
            self.report["summary"]["defending_heroes_with_conditional_mechanics"], 5
        )
        self.assertEqual(self.report["summary"]["replay_calibrated"], 0)
        self.assertEqual(self.report["summary"]["complete_battle_ready"], 0)
        self.assertFalse(self.report["scope"]["complete_battle_ready"])
        for row in self.rows.values():
            self.assertFalse(row["behavior"]["replay_calibrated"])
            self.assertFalse(row["behavior"]["complete_battle_ready"])

    def test_garrison_roles_are_conditional_donor_candidates_not_confirmed_receipts(
        self,
    ):
        for entity_id in GARRISON_MEMBERS:
            row = self.rows[entity_id]
            self.assertEqual(
                row["behavior"]["defending_role"]["status"], "conditional_mechanics"
            )
            self.assertIsNone(row["behavior"]["defending_hero_behavior"])
            for town_hall in ("16", "17", "18"):
                self.assertEqual(
                    row["opponent_status_by_town_hall"][town_hall],
                    "garrison_donor_candidate_conditional_mechanics",
                )
                role = row["opponent_behavior_by_town_hall"][town_hall]
                self.assertIn(
                    "does not certify a received level", " ".join(role["remaining"])
                )
                self.assertFalse(role["replay_calibrated"])
        self.assertEqual(
            self.report["summary"][
                "defending_garrison_troops_with_conditional_mechanics"
            ],
            7,
        )
        self.assertEqual(
            self.report["summary"]["defending_heroes_with_conditional_mechanics"], 5
        )

    def test_castle_and_builder_lifecycles_are_removed_from_missing_entity_list(self):
        remaining = self.report["prioritized_blockers"][0]["remaining_entities"]
        for entity_id in ("clan-castle", "builders-hut"):
            self.assertNotIn(entity_id, remaining)
            self.assertEqual(
                self.rows[entity_id]["behavior"]["status"], "conditional_mechanics"
            )
        self.assertIn(
            "seven defending troop", self.rows["clan-castle"]["behavior"]["implemented"]
        )


if __name__ == "__main__":
    unittest.main()
