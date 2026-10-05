"""S1: paid equipped Queen and finite Mirror children under Ice/Angry."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial
from test_adapters import entity_instance
from test_advanced_spell_integration import spell_battle, SOURCE
from test_full_battle import add_hero, add_reserve, deployment, freeze_cast
from test_heroes import ability
from test_spell_lifecycle_integration import recall, add_cast


def mirror_battle(catalog, entity, step=0.25, duration=9):
    inputs = spell_battle(catalog, entity, step=step, duration=duration)
    add_hero(inputs[0], inputs[2], inputs[1], "archer-queen")
    scene = inputs[0]["entity_scene"]
    queen = scene["entities"][-1]
    queen.update(first_attack_seconds=100)
    queen["modifiers"]["hitpoints_multiplier"] = 50
    scene["entities"][0]["modifiers"]["hitpoints_multiplier"] = 100
    scene["effects"] = [ability("queen", 0)]
    return inputs


class MirrorSpellIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")

    def test_paid_queen_mirror_children_pause_and_resume_real_weapons_with_one_activation(
        self,
    ):
        for step in (0.017, 0.25):
            inputs = mirror_battle(self.catalog, "ice-block-spell", step)
            inputs[0]["entity_scene"]["attack_spells"][0]["time_seconds"] = 0.2
            result = simulate_full_battle(*inputs, self.catalog)
            combat = result["combat"]
            clone_ids = sorted(
                key for key in combat["actors"] if "-mirror-clone-" in key
            )
            self.assertEqual(len(clone_ids), 2)
            for key in clone_ids:
                hits = [
                    e
                    for e in combat["trace"]
                    if e.get("event") == "projectile_impact" and e.get("source") == key
                ]
                self.assertGreaterEqual(len(hits), 2)
                self.assertEqual(hits[0]["time_seconds"], 0)
                self.assertAlmostEqual(hits[1]["time_seconds"], 7.75)
                self.assertTrue(all(e["damage"] > 0 for e in hits))
                incoming = [
                    e
                    for e in combat["trace"]
                    if e.get("event") == "damage_received" and e["target_id"] == key
                ]
                self.assertTrue(incoming)
                for hit in incoming:
                    factor = 0.14 if 0.2 <= hit["time_seconds"] < 7.2 else 1
                    self.assertAlmostEqual(
                        hit["final_damage"], hit["requested_damage"] * factor
                    )
            self.assertEqual(combat["hero_abilities"]["hero_abilities_used"], ["queen"])
            self.assertEqual(
                result["resource_use"]["deployed_attacker_ids"], ["pekka-0", "queen"]
            )
            self.assertEqual(
                sum(slot["spent"] for slot in result["resource_use"]["spell_slots"]), 1
            )
            self.assertEqual(len(inputs[2]["heroes"][0]["equipment"]), 2)

    def test_paid_angry_children_use_fresh_membership_then_expire_while_recall_held_after_owner_death(
        self,
    ):
        for step in (0.017, 0.25):
            inputs = mirror_battle(self.catalog, "angry-spell", step, duration=40)
            spec, account, army, layout = inputs
            scene = spec["entity_scene"]
            queen = scene["entities"][-1]
            queen["modifiers"]["hitpoints_multiplier"] = 0.0001
            mirror = queen["hero_parameters"]["equipment"][1]
            mirror["parameters"]["clone_offsets"] = [
                {"dx": -8, "dy": -0.5},
                {"dx": -8, "dy": 0.5},
            ]
            scene["effects"] = [ability("queen", 1)]
            add_cast(inputs, freeze_cast(time=0))
            gold = entity_instance(
                "gold",
                "gold-storage",
                1,
                "defense",
                x=1,
                y=10,
                mode="passive",
                statistics_mode="none",
                attack_parameters={},
                inactive_attack_interval_seconds=1,
            )
            gold["modifiers"]["hitpoints_multiplier"] = 1000
            scene["entities"].append(gold)
            layout["inventory"]["gold-storage"] = 1
            layout["buildings"].append(
                {
                    "instance": "gold",
                    "id": "gold-storage",
                    "level": 1,
                    "x": 1,
                    "y": 10,
                    "mode": "passive",
                    "counts_for_destruction": True,
                }
            )
            compiled = compile_full_battle(*inputs, self.catalog)["compiled"]["scene"]
            child = next(a for a in compiled["actors"] if "-mirror-clone-" in a["id"])
            expiry = 1 + child["summon_model"]["duration_seconds"]
            spec["time_limit_seconds"] = scene["duration_seconds"] = expiry + 0.5
            recall(inputs, expiry - 0.2, expiry + 0.3, x=1.5)
            add_reserve(spec, army, account)
            command = deployment("reserve", expiry + 0.4)
            command["positions"]["reserve"] = {"x": 0.5, "y": 15.5}
            scene["effects"].append(command)
            result = simulate_full_battle(*inputs, self.catalog)
            combat = result["combat"]
            self.assertLess(combat["actors"]["queen"]["death_time"], expiry)
            children = {
                key: a for key, a in combat["actors"].items() if "-mirror-clone-" in key
            }
            self.assertEqual(len(children), 2)
            for key, child in children.items():
                self.assertEqual(child["death_time"], expiry)
                hits = [
                    e
                    for e in combat["trace"]
                    if e.get("event") == "projectile_impact" and e.get("source") == key
                ]
                self.assertTrue(hits)
                self.assertEqual(hits[0]["target"], "gold")
                self.assertTrue(
                    any(
                        e["time_seconds"] > combat["actors"]["queen"]["death_time"]
                        for e in hits
                    )
                )
                self.assertFalse(
                    any(
                        e.get("event") == "spell_priority_changed"
                        and e.get("actor") == key
                        and e["defenses_first"]
                        for e in combat["trace"]
                    )
                )
            self.assertEqual(combat["hero_abilities"]["hero_abilities_used"], ["queen"])
            self.assertEqual(
                result["resource_use"]["deployed_attacker_ids"],
                ["pekka-0", "queen", "reserve"],
            )
            self.assertEqual(
                sum(slot["spent"] for slot in result["resource_use"]["spell_slots"]), 3
            )
            self.assertEqual(result["outcome"]["end_reason"], "declared_time_limit")

    def test_forged_child_or_missing_new_policy_rejects_without_narrowing_legacy_ordinary_scope(
        self,
    ):
        live = simulate_full_battle(
            *mirror_battle(self.catalog, "angry-spell", duration=1), self.catalog
        )
        members = {
            e["actor"]
            for e in live["combat"]["trace"]
            if e.get("event") == "spell_priority_changed" and e["defenses_first"]
        }
        self.assertTrue({"queen-mirror-clone-0", "queen-mirror-clone-1"} <= members)
        inputs = mirror_battle(self.catalog, "ice-block-spell")
        raw = compile_full_battle(*inputs, self.catalog)["compiled"]["scene"]
        child = next(a for a in raw["actors"] if "-mirror-clone-" in a["id"])
        child["damage"] += 1
        with self.assertRaisesRegex(InputError, "fresh owner declaration"):
            simulate_spatial(raw)
        scene = inputs[0]["entity_scene"]
        scene["advanced_spell_binding"].pop("mirror_children")
        with self.assertRaisesRegex(InputError, "explicit mirror_children policy"):
            compile_full_battle(*inputs, self.catalog)
        ordinary = spell_battle(self.catalog, "ice-block-spell")
        ordinary[0]["entity_scene"]["advanced_spell_binding"].pop("mirror_children")
        simulate_full_battle(*ordinary, self.catalog)


if __name__ == "__main__":
    unittest.main()
