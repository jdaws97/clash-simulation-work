"""Shared targeting and paid-resource tests for conditional recipe spells."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial

from test_adapters import entity_instance
from test_attack_spell_integration import attack_spell_battle, attack_spell_sector
from test_indirect_defenses import fixed_tank

ROOT = Path(__file__).resolve().parents[1]


def recipe_cast(entity, **changes):
    parameters = json.loads(
        (ROOT / "data/battle-policies/recipe-spells.json").read_text()
    )[entity]
    cast = {
        "id": entity,
        "entity": entity,
        "level": 1,
        "town_hall": 18,
        "time_seconds": 0,
        "x": 10,
        "y": 10,
        "parameters": parameters,
    }
    cast.update(changes)
    return cast


class RecipeSpellIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_totem_taunts_ground_and_air_weapons_once_without_army_capacity(self):
        cast = recipe_cast("totem-spell", x=10.5, y=10.5)
        cast["parameters"].update(
            impact_delay_seconds=0, landing_damage=0, landing_stun_seconds=0
        )
        entities = [
            entity_instance("ground", "cannon", 1, "defense", x=8, y=8),
            entity_instance("air", "air-defense", 1, "defense", x=12, y=8),
            fixed_tank(x=6.5, y=10.5),
        ]
        results = []
        for step in (0.031, 0.8):
            specification = attack_spell_sector(
                self.catalog,
                deepcopy(entities),
                [deepcopy(cast)],
                duration_seconds=2,
                maximum_step_seconds=step,
            )
            result = simulate_spatial(
                compile_entity_scene(specification, self.catalog)["scene"]
            )
            launches = [
                event
                for event in result["trace"]
                if event.get("event") == "projectile_launch"
                and event.get("source") in {"air", "ground"}
            ]
            self.assertEqual({event["source"] for event in launches}, {"air", "ground"})
            self.assertEqual(
                {event["target"] for event in launches}, {"totem-spell:totem"}
            )
            self.assertEqual(
                len(
                    [
                        event
                        for event in result["trace"]
                        if event.get("event") == "totem_landed"
                    ]
                ),
                1,
            )
            results.append(result["actors"]["totem-spell:totem"]["hp"])
        self.assertAlmostEqual(*results, places=7)
        inputs = attack_spell_battle(
            self.catalog, [recipe_cast("totem-spell", x=9.5, y=5.5)]
        )
        compiled = compile_full_battle(*inputs, self.catalog)
        self.assertIn("totem-spell:totem", compiled["generated_summon_ids"])
        self.assertNotIn(
            "totem-spell:totem", compiled["validation"]["attacker_bindings"]
        )

    def test_recall_withdrawal_redeploy_preserves_hp_and_spends_original_army_once(
        self,
    ):
        cast = recipe_cast("recall-spell", x=9.5, y=5.5, time_seconds=0.2)
        cast["parameters"]["redeployment"] = {
            "time_seconds": 1,
            "position": {"x": 2.5, "y": 2.5},
            "regions": [{"left": 0, "right": 4, "top": 0, "bottom": 4}],
            "source": "synthetic-open-deployment-test",
        }
        inputs = attack_spell_battle(self.catalog, [cast])
        specification = inputs[0]
        attacker = specification["entity_scene"]["entities"][1]
        attacker["modifiers"]["hitpoints_multiplier"] = 10
        attacker["first_attack_seconds"] = 100
        specification["entity_scene"]["recording_interval_seconds"] = 0.25
        result = simulate_full_battle(*inputs, self.catalog)
        events = result["combat"]["trace"]
        capture = [event for event in events if event.get("event") == "recall_capture"]
        returns = [
            event for event in events if event.get("event") == "recall_redeployment"
        ]
        self.assertEqual(len(capture), 1)
        self.assertEqual(capture[0]["capacity_used"], 25)
        self.assertEqual(len(returns), 1)
        self.assertEqual(returns[0]["additional_army_spend"], 0)
        frames = result["combat"]["frames"]
        withdrawn = [
            frame["actors"]["pekka-0"]
            for frame in frames
            if 0.25 <= frame["time_seconds"] < 1
        ]
        self.assertTrue(withdrawn)
        self.assertTrue(
            all(not actor["active"] and actor["hp"] > 0 for actor in withdrawn)
        )
        returned = next(
            frame["actors"]["pekka-0"]
            for frame in frames
            if abs(frame["time_seconds"] - 1) < 1e-8
        )
        self.assertEqual(returned["hp"], withdrawn[-1]["hp"])
        self.assertEqual(result["combat"]["actors"]["pekka-0"]["spawn_seconds"], 0)
        self.assertEqual(result["resource_use"]["deployed_attacker_ids"], ["pekka-0"])
        self.assertEqual(
            sum(slot["spent"] for slot in result["resource_use"]["spell_slots"]), 1
        )
        bad = deepcopy(inputs)
        bad[0]["entity_scene"]["attack_spells"][0]["parameters"]["redeployment"][
            "position"
        ] = {"x": 10.5, "y": 5.5}
        with self.assertRaisesRegex(InputError, "legal regions"):
            simulate_full_battle(*bad, self.catalog)

    def test_totem_intervening_damage_keeps_exact_expiry_and_rejects_forged_reserve(
        self,
    ):
        cast = recipe_cast("totem-spell")
        cast["parameters"].update(
            impact_delay_seconds=0, landing_damage=0, landing_stun_seconds=0
        )
        specification = attack_spell_sector(
            self.catalog, [fixed_tank()], [cast], duration_seconds=0.2
        )
        scene = compile_entity_scene(specification, self.catalog)["scene"]
        quantities = scene["attack_spell_models"][0]["quantities"]
        scene["effects"] = [
            {
                "id": "intervening-hit",
                "kind": "damage",
                "time_seconds": 0.03,
                "targets": ["totem-spell:totem"],
                "amount": quantities["hitpoints"]
                - quantities["decay_per_second"] * 0.08,
            }
        ]
        for step in (0.007, 0.2):
            with self.subTest(step=step):
                result = simulate_spatial(
                    {**deepcopy(scene), "maximum_step_seconds": step}
                )
                self.assertAlmostEqual(
                    result["actors"]["totem-spell:totem"]["death_time"], 0.08, places=8
                )
        for field, value in (
            ("hitpoints", quantities["hitpoints"] * 2),
            ("beneficial_field_immunity", False),
        ):
            forged = deepcopy(scene)
            next(a for a in forged["actors"] if a["id"] == "totem-spell:totem")[
                field
            ] = value
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(InputError, "paid spell contract"),
            ):
                simulate_spatial(forged)


if __name__ == "__main__":
    unittest.main()
