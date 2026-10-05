"""Published profiles retain role differences and explicit scaling policies."""

import unittest
from pathlib import Path

from clashlab.common import InputError, read_json
from clashlab.modifiers import resolve_battle_modifiers


ROOT = Path(__file__).resolve().parents[1]


def configuration(profile, role, policy="unchanged"):
    return {
        "profile_id": profile,
        "entity_role": role,
        "maximum_hp_damage_policy": policy,
        "policy_source": "declared-contract-case-not-percent-weapon-validation",
    }


class ModifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = read_json(ROOT / "data/mode-rules.json")

    def test_legend_profiles_distinguish_defense_heroes_and_guardians(self):
        for profile, defense, guardian, attack in (
            ("legend_iii", 1.10, 1.05, 0.95),
            ("legend_ii", 1.15, 1.10, 0.90),
            ("legend_i", 1.20, 1.20, 0.80),
        ):
            expected = {
                "defense": (1, defense),
                "defending_hero": (defense, defense),
                "guardian": (guardian, guardian),
                "attacking_hero": (attack, attack),
            }
            for role, (hp, damage) in expected.items():
                with self.subTest(profile=profile, role=role):
                    result = resolve_battle_modifiers(
                        configuration(profile, role), self.rules
                    )
                    self.assertEqual(result["modifiers"]["hitpoints_multiplier"], hp)
                    self.assertEqual(result["modifiers"]["damage_multiplier"], damage)
                    self.assertEqual(
                        result["attacking_hero_equipment_level_reduction"],
                        {"common": 0, "epic": 0},
                    )

    def test_esport_reductions_are_reported_without_silent_equipment_clamps(self):
        result = resolve_battle_modifiers(
            configuration("esport", "attacking_hero"), self.rules
        )
        self.assertEqual(
            result["attacking_hero_equipment_level_reduction"], {"common": 3, "epic": 6}
        )
        self.assertTrue(result["equipment_statistic_reconciliation_required"])
        self.assertFalse(result["full_game_prediction"])

    def test_percent_weapon_scaling_follows_declared_policy(self):
        unchanged = resolve_battle_modifiers(
            configuration("legend_i", "defense"), self.rules
        )
        scaled = resolve_battle_modifiers(
            configuration("legend_i", "defense", "scale_with_damage"), self.rules
        )
        self.assertEqual(unchanged["modifiers"]["maximum_hp_damage_multiplier"], 1)
        self.assertEqual(scaled["modifiers"]["maximum_hp_damage_multiplier"], 1.2)
        self.assertEqual(scaled["modifiers"]["attack_interval_multiplier"], 1)

    def test_active_ranked_profile_is_distinct_from_historical_unmodified_fixture(self):
        selected = self.rules["battle_modifier_policy"]["current_user_scenarios"]
        self.assertEqual(selected, {"legend_i": "legend_i", "master_ii_cwl": "none"})
        self.assertEqual(
            self.rules["battle_modifier_policy"]["historical_scenario_profiles"],
            {"electro31": "none"},
        )
        self.assertEqual(self.rules["ranked"]["legend_i"]["modifiers"], "legend_i")
        result = resolve_battle_modifiers(
            configuration("none", "defending_hero"), self.rules
        )
        self.assertEqual(result["modifiers"]["damage_multiplier"], 1)
        self.assertEqual(result["modifiers"]["hitpoints_multiplier"], 1)

    def test_unknown_profile_role_or_missing_scaling_policy_are_rejected(self):
        invalid = [
            configuration("inferred_from_th18", "defense"),
            configuration("none", "unknown_role"),
        ]
        missing = configuration("none", "defense")
        del missing["maximum_hp_damage_policy"]
        invalid.append(missing)
        for case in invalid:
            with self.subTest(configuration=case), self.assertRaises(InputError):
                resolve_battle_modifiers(case, self.rules)


if __name__ == "__main__":
    unittest.main()
