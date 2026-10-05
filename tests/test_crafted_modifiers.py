"""Selected crafted weapons must receive the role profile in actual paid battles."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.battle_modifiers import apply_battle_modifiers
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial
from test_battle_modifiers import modifier_policy
from test_crafted_integration import crafted_battle, add_troop
from test_full_battle import add_hero


ROOT = Path(__file__).resolve().parents[1]


def profile_battle(
    catalog, variant, profile, *, hazard="scale_with_source_role", hero=False
):
    inputs = crafted_battle(
        catalog, variant, duration=3.2 if variant == "cake-a-pult" else 1.2
    )
    spec, account, army, layout = inputs
    scene = spec["entity_scene"]
    station, troop = scene["entities"][2:4]
    station["modifiers"]["hitpoints_multiplier"] = 1
    troop.update(entity="pekka", first_attack_seconds=100)
    army["troops"] = [{"id": "pekka", "level": 1, "count": 1}]
    account["levels"]["pekka"] = 1
    if variant == "cake-a-pult":
        add_troop(inputs, "pekka", "late", spawn=3.05)
    spec["battle_modifier_policy"] = modifier_policy(
        profile, impact_hazard_damage_policy=hazard
    )
    if hero:
        royal = add_hero(spec, army, account, "grand-warden")
        royal.update(x=1.5, y=6.5, first_attack_seconds=100)
        scene["defending_unit_responses"]["actors"][royal["id"]] = {
            "primary": "ignore",
            "collateral": "ignore",
        }
    return inputs


class CraftedModifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.rules = read_json(ROOT / "data/mode-rules.json")

    def test_paid_primary_and_cake_explosion_scale_once_with_unchanged_defense_hp_and_clocks(
        self,
    ):
        for variant in ("cake-a-pult", "hero-hunter", "hot-candle"):
            results = []
            for profile in ("none", "legend_i"):
                inputs = profile_battle(self.catalog, variant, profile)
                before = deepcopy(inputs)
                results.append(
                    simulate_full_battle(*inputs, self.catalog, mode_rules=self.rules)
                )
                self.assertEqual(inputs, before)
            neutral, ranked = results
            normal_actor = next(
                a
                for a in neutral["compiled"]["scene"]["actors"]
                if a["id"] == "station"
            )
            ranked_actor = next(
                a for a in ranked["compiled"]["scene"]["actors"] if a["id"] == "station"
            )
            self.assertEqual(ranked_actor["hitpoints"], normal_actor["hitpoints"])
            for field in ("attack_interval_seconds", "range", "minimum_range"):
                self.assertEqual(ranked_actor[field], normal_actor[field])
            for field in (
                "values",
                "statistics",
                "poison_row",
                "secondary_module_rows",
            ):
                self.assertEqual(
                    ranked_actor["crafted_defense_model"][field],
                    normal_actor["crafted_defense_model"][field],
                )
            first = {}
            for label, result in (("none", neutral), ("legend_i", ranked)):
                first[label] = {}
                for event in result["combat"]["trace"]:
                    if event.get("event") in {
                        "crafted_shot_impact",
                        "crafted_bomb_impact",
                    }:
                        first[label].setdefault(event["event"], event)
            self.assertIn("crafted_shot_impact", first["none"])
            for kind, original in first["none"].items():
                changed = first["legend_i"][kind]
                self.assertEqual(changed["time_seconds"], original["time_seconds"])
                self.assertAlmostEqual(changed["amount"], original["amount"] * 1.2)
            if variant == "cake-a-pult":
                self.assertAlmostEqual(
                    first["legend_i"]["crafted_shot_impact"]["amount"], 234
                )
                self.assertAlmostEqual(
                    first["legend_i"]["crafted_bomb_impact"]["amount"], 480
                )
            application = next(
                a
                for a in ranked["battle_modifier_audit"]["application"]["actors"]
                if a["id"] == "station"
            )
            self.assertIn(
                "crafted-role-profile-model-scaling-v1",
                ranked["battle_modifier_audit"]["application"]["capabilities"],
            )
            self.assertEqual(application["role"], "defense")
            damage_entry = next(
                s
                for s in application["statistics"]
                if s["path"] == ["crafted_defense_model", "damage_per_hit"]
            )
            self.assertEqual(damage_entry["multiplier"], 1.2)
            self.assertEqual(ranked["resource_use"], neutral["resource_use"])

    def test_hunter_hero_bonus_and_poison_follow_distinct_declared_scaling_policies(
        self,
    ):
        runs = {}
        for profile, hazard in (
            ("none", "scale_with_source_role"),
            ("legend_i", "scale_with_source_role"),
            ("legend_i", "unchanged"),
        ):
            result = simulate_full_battle(
                *profile_battle(
                    self.catalog, "hero-hunter", profile, hazard=hazard, hero=True
                ),
                self.catalog,
                mode_rules=self.rules,
            )
            events = result["combat"]["trace"]
            shot = next(e for e in events if e.get("event") == "crafted_shot_impact")
            self.assertEqual(shot["target"], "warden")
            pulse = next(
                e
                for e in events
                if e.get("event") == "hazard_pulse"
                and e["field"].startswith("crafted-poison")
            )
            model = next(
                a for a in result["compiled"]["scene"]["actors"] if a["id"] == "station"
            )["crafted_defense_model"]
            runs[(profile, hazard)] = (shot, pulse, model)
        normal, scaled, fixed = runs.values()
        self.assertAlmostEqual(scaled[0]["amount"], normal[0]["amount"] * 1.2)
        self.assertEqual(scaled[0]["amount"], fixed[0]["amount"])
        self.assertAlmostEqual(
            scaled[2]["poison_maximum_dps"], normal[2]["poison_maximum_dps"] * 1.2
        )
        self.assertEqual(
            fixed[2]["poison_maximum_dps"], normal[2]["poison_maximum_dps"]
        )
        self.assertAlmostEqual(
            scaled[1]["requested_damage_per_target"],
            normal[1]["requested_damage_per_target"] * 1.2,
        )
        self.assertEqual(
            fixed[1]["requested_damage_per_target"],
            normal[1]["requested_damage_per_target"],
        )
        self.assertEqual(scaled[1]["time_seconds"], normal[1]["time_seconds"])

    def test_profile_transform_preserves_raw_owner_guards_and_cannot_repeat(self):
        inputs = profile_battle(self.catalog, "cake-a-pult", "legend_i")
        compiled = compile_full_battle(*inputs, self.catalog, mode_rules=self.rules)[
            "compiled"
        ]["scene"]
        with self.assertRaises(InputError):
            apply_battle_modifiers(
                compiled, modifier_policy(), self.catalog, self.rules
            )
        station = next(a for a in compiled["actors"] if a["id"] == "station")
        station["crafted_defense_model"]["damage_per_hit"] = 1
        with self.assertRaises(InputError):
            simulate_spatial(compiled)
        del inputs[0]["battle_modifier_policy"]
        raw = compile_full_battle(*inputs, self.catalog)["compiled"]["scene"]
        next(a for a in raw["actors"] if a["id"] == "station")["crafted_defense_model"][
            "damage_per_hit"
        ] = 1
        with self.assertRaises(InputError):
            apply_battle_modifiers(raw, modifier_policy(), self.catalog, self.rules)


if __name__ == "__main__":
    unittest.main()
