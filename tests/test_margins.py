"""Check conditional damage thresholds without claiming game fidelity."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.margins import RULES, damage_margins


ROOT = Path(__file__).resolve().parents[1]


def conditional_case():
    return {
        "id": "conditional-th16-scatter-damage",
        "purpose": "An explicitly unrounded, fully covered, unprotected damage case",
        "model_rules": deepcopy(RULES),
        "fireball_level": 24,
        "earthquake_level": 7,
        "targets": [
            {
                "id": "scatter",
                "entity": "scattershot",
                "level": 5,
                "town_hall": 16,
                "supercharge": False,
                "maximum_hp_multiplier": 1,
                "initial_hp_fraction": 1,
            }
        ],
        "hit_sequence": [
            {
                "id": "first-quake",
                "kind": "earthquake",
                "source": "test-condition-not-replay-evidence",
                "covered": {"scatter": True},
                "blocked_by_protection": {"scatter": False},
                "effective_hit_multiplier": {"scatter": 1},
                "multiplier_source": "declared-fresh-first-quake-case",
            },
            {
                "id": "fireball",
                "kind": "fireball",
                "source": "test-condition-not-replay-evidence",
                "covered": {"scatter": True},
                "blocked_by_protection": {"scatter": False},
                "damage_multiplier": 1,
            },
        ],
    }


def repair_event(amount):
    return {
        "id": "conditional-repair",
        "kind": "repair",
        "source": "declared-delivered-repair-not-inferred-builder-AI",
        "delivered_hp": {"scatter": amount},
    }


class DamageMarginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def run_case(self, case):
        return damage_margins(case, self.catalog)

    def test_one_repair_pulse_overturns_thin_scatter_kill_margin(self):
        case = conditional_case()
        baseline = self.run_case(case)["targets"]["scatter"]
        self.assertEqual(baseline["hp"], 0)
        self.assertAlmostEqual(
            baseline["timeline"][-1]["damage_margin_before_hit"], 58.9
        )
        case["hit_sequence"].insert(1, repair_event(63.75))
        repaired = self.run_case(case)["targets"]["scatter"]
        self.assertAlmostEqual(repaired["hp"], 4.85)
        self.assertIsNone(repaired["destroyed_at_event"])

    def test_repair_cap_and_hit_order_change_remaining_health(self):
        case = conditional_case()
        case["hit_sequence"].insert(1, repair_event(3000))
        quake_first = self.run_case(case)["targets"]["scatter"]
        self.assertAlmostEqual(quake_first["hp"], 1510)
        self.assertAlmostEqual(quake_first["timeline"][1]["delivered_repair"], 1568.9)
        case["hit_sequence"].reverse()
        fireball_first = self.run_case(case)["targets"]["scatter"]
        self.assertAlmostEqual(fireball_first["hp"], 2941.1)

    def test_missed_quake_and_blocked_fireball_do_not_get_credited(self):
        case = conditional_case()
        case["hit_sequence"][0]["covered"]["scatter"] = False
        self.assertEqual(self.run_case(case)["targets"]["scatter"]["hp"], 1510)
        case["hit_sequence"][0]["covered"]["scatter"] = True
        case["hit_sequence"][1]["blocked_by_protection"]["scatter"] = True
        self.assertAlmostEqual(self.run_case(case)["targets"]["scatter"]["hp"], 3841.1)

    def test_hp_modifier_is_applied_to_maximum_hp_before_percent_damage(self):
        case = conditional_case()
        case["targets"][0]["maximum_hp_multiplier"] = 1.1
        target = self.run_case(case)["targets"]["scatter"]
        self.assertAlmostEqual(target["maximum_hp"], 5951)
        self.assertAlmostEqual(target["hp"], 325.21)

    def test_repeated_quake_requires_explicit_effective_multiplier(self):
        case = conditional_case()
        second = deepcopy(case["hit_sequence"][0])
        second["id"] = "second-quake"
        del second["effective_hit_multiplier"]
        case["hit_sequence"].insert(1, second)
        with self.assertRaisesRegex(InputError, "effective_hit_multiplier"):
            self.run_case(case)

    def test_repair_cannot_revive_destroyed_defense(self):
        case = conditional_case()
        case["hit_sequence"].append(repair_event(500))
        target = self.run_case(case)["targets"]["scatter"]
        self.assertEqual(target["hp"], 0)
        self.assertEqual(target["timeline"][-1]["result"], "already_destroyed")

    def test_supercharge_and_unavailable_defense_level_fail_closed(self):
        case = conditional_case()
        case["targets"][0]["supercharge"] = True
        with self.assertRaisesRegex(InputError, "stage adapter"):
            self.run_case(case)
        case["targets"][0]["supercharge"] = False
        case["targets"][0]["level"] = 7
        with self.assertRaisesRegex(InputError, "unavailable"):
            self.run_case(case)

    def test_missing_coverage_and_boolean_numeric_inputs_are_rejected(self):
        case = conditional_case()
        case["hit_sequence"][0]["covered"] = {}
        with self.assertRaisesRegex(InputError, "every target"):
            self.run_case(case)
        case = conditional_case()
        case["targets"][0]["maximum_hp_multiplier"] = True
        with self.assertRaisesRegex(InputError, "number"):
            self.run_case(case)

    def test_snapshot_provenance_and_conditional_status_are_retained(self):
        result = self.run_case(conditional_case())
        self.assertFalse(result["full_game_prediction"])
        self.assertEqual(result["fireball"]["verification"], "unverified_snapshot")
        self.assertEqual(result["fireball"]["damage"], 3900)
        self.assertEqual(
            result["declared_hit_sequence"][0]["effective_hit_multiplier"],
            {"scatter": 1},
        )


if __name__ == "__main__":
    unittest.main()
