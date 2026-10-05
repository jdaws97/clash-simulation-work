"""Finite spell lifecycles through paid ownership and ordinary battle settlement."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.advanced_spell_models import SPELL_CLASSES
from clashlab.attack_spell_models import ALL_SPELL_CLASSES
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial
from test_adapters import entity_instance
from test_advanced_spell_integration import spell_battle, SOURCE
from test_battle_termination import classification, termination_policy
from test_full_battle import add_hero, add_reserve, deployment, freeze_cast
from test_heroes import ability
from test_recipe_spells import recipe_cast


def add_cast(inputs, instance, kind=None):
    scene = inputs[0]["entity_scene"]
    entity = instance["entity"]
    scene["freeze_spells" if entity == "freeze-spell" else "attack_spells"].append(
        instance
    )
    inputs[1]["levels"][entity] = instance["level"]
    inputs[2]["spells"].append({"id": entity, "level": instance["level"], "count": 1})
    classifications = []
    for spell in inputs[2]["spells"]:
        current = ALL_SPELL_CLASSES.get(spell["id"], "support_only")
        classifications.append(
            classification(
                {"origin": "army", "entity": spell["id"], "level": spell["level"]},
                current,
                "ignore" if current == "support_only" else "while_unspent",
            )
        )
    inputs[0]["termination_policy"] = termination_policy(classifications)


def recall(inputs, time, return_at, x=3.5):
    model = recipe_cast("recall-spell", town_hall=16, x=x, y=5.5, time_seconds=time)
    model["parameters"]["impact_delay_seconds"] = 0
    model["parameters"]["redeployment"] = {
        "time_seconds": return_at,
        "position": {"x": x, "y": 5.5},
        "regions": [{"left": 0, "right": 10, "top": 0, "bottom": 16}],
        "source": SOURCE,
    }
    add_cast(inputs, model)


class SpellLifecycleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")

    def test_paid_simultaneous_bat_clone_closure_launches_owned_weapons_after_army_loss(
        self,
    ):
        for step in (0.017, 0.25):
            for clone_id, bat_id in (("a-clone", "z-bat"), ("z-clone", "a-bat")):
                inputs = spell_battle(
                    self.catalog, "clone-spell", step=step, duration=2
                )
                scene = inputs[0]["entity_scene"]
                scene["entities"][1]["id"] = "0-army"
                scene["attack_spells"][0]["id"] = clone_id
                bat = spell_battle(self.catalog, "bat-spell")[0]["entity_scene"][
                    "attack_spells"
                ][0]
                bat["id"] = bat_id
                add_cast(inputs, bat)
                result = simulate_full_battle(*inputs, self.catalog)
                combat = result["combat"]
                state = combat["attack_spells"]["advanced_spells"]
                self.assertEqual(state["generated_counts"][clone_id], 22)
                self.assertEqual(state["remaining_clone_capacity"][clone_id], 0)
                self.assertEqual(combat["actors"]["0-army"]["death_time"], 0)
                clone_ids = {
                    k for k, a in combat["actors"].items() if "spell_clone_model" in a
                }
                hits = [
                    e
                    for e in combat["trace"]
                    if e.get("event") == "projectile_impact"
                    and e.get("source") in clone_ids
                ]
                self.assertTrue(hits)
                self.assertTrue(
                    all(abs(e["damage"] - 60 * 0.123) < 1e-10 for e in hits)
                )
                self.assertLess(
                    combat["actors"]["hall"]["hp"],
                    combat["actors"]["hall"]["maximum_hp"],
                )
                self.assertEqual(
                    sum(s["spent"] for s in result["resource_use"]["spell_slots"]), 2
                )
                self.assertEqual(
                    result["resource_use"]["deployed_attacker_ids"], ["0-army"]
                )

    def test_paid_clone_source_loss_recall_held_absolute_expiry_and_finite_budget(self):
        for step in (0.017, 0.25):
            inputs = spell_battle(self.catalog, "clone-spell", step=step, duration=35)
            scene = inputs[0]["entity_scene"]
            troop = scene["entities"][1]
            troop.update(entity="minion", first_attack_seconds=0)
            troop.pop("wall_parameters")
            troop["modifiers"]["hitpoints_multiplier"] = 1
            inputs[1]["levels"]["minion"] = 1
            inputs[2]["troops"] = [{"id": "minion", "level": 1, "count": 1}]
            scene["attack_spells"][0]["parameters"]["spawn_offsets"] = [[-9, 0]] * 60
            scene["recording_interval_seconds"] = 1
            recall(inputs, 0.2, 33, x=0.5)
            result = simulate_full_battle(*inputs, self.catalog)
            combat = result["combat"]
            state = combat["attack_spells"]["advanced_spells"]
            clones = result["resource_use"]["generated_spell_units"]
            self.assertEqual(len(clones), 11)
            self.assertEqual(state["generated_counts"], {"spell": 11})
            self.assertEqual(state["remaining_clone_capacity"], {"spell": 0})
            self.assertTrue(all(v["released_at"] == 0 for v in clones.values()))
            self.assertLess(combat["actors"]["pekka-0"]["death_time"], 0.2)
            captures = [
                e for e in combat["trace"] if e.get("event") == "recall_capture"
            ]
            self.assertEqual(set(captures[0]["actors"]), set(clones))
            expired = [
                e for e in combat["trace"] if e.get("event") == "spell_clone_expired"
            ]
            self.assertEqual(len(expired), 11)
            self.assertTrue(all(e["time_seconds"] == 30 for e in expired))
            self.assertEqual(result["outcome"]["end_reason"], "attack_force_exhausted")
            self.assertEqual(result["outcome"]["elapsed_seconds"], 30)
            self.assertEqual(
                result["resource_use"]["deployed_attacker_ids"], ["pekka-0"]
            )
            self.assertEqual(
                sum(s["spent"] for s in result["resource_use"]["spell_slots"]), 2
            )
            raw = deepcopy(result["compiled"]["scene"])
            next(a for a in raw["actors"] if "spell_clone_model" in a)["damage"] += 1
            with self.assertRaisesRegex(InputError, "fresh source declaration"):
                simulate_spatial(raw)
            # An unrelated paid reserve keeps the battle alive beyond Recall's
            # return time. Expired held clones must stay in the owned group but
            # neither return alive nor create a new deployment entitlement.
            if step == 0.25:
                add_reserve(inputs[0], inputs[2], inputs[1])
                scene["entities"][-1]["modifiers"]["movement_speed_multiplier"] = 0.01
                command = deployment("reserve", 31)
                command["positions"]["reserve"] = {"x": 0.5, "y": 15.5}
                scene["effects"].append(command)
                retained = simulate_full_battle(*inputs, self.catalog)
                returns = [
                    e
                    for e in retained["combat"]["trace"]
                    if e.get("event") == "recall_redeployment"
                ]
                self.assertEqual(len(returns), 1)
                self.assertEqual(returns[0]["actors"], [])

    def test_paid_revive_same_hero_spent_ability_ice_work_and_absolute_passives(self):
        for step in (0.017, 0.25):
            inputs = spell_battle(self.catalog, "revive-spell", step=step, duration=10)
            scene = inputs[0]["entity_scene"]
            scene["attack_spells"][0]["parameters"]["impact_delay_seconds"] = 2.1
            add_hero(inputs[0], inputs[2], inputs[1])
            hero = scene["entities"][-1]
            hero.update(first_attack_seconds=0.1)
            hero["modifiers"]["hitpoints_multiplier"] = 0.0001
            scene["effects"] = [ability("royal", 0)]
            freeze = freeze_cast(time=0.1)
            freeze["parameters"]["duration_multiplier"] = 10
            add_cast(inputs, freeze)
            ice = spell_battle(self.catalog, "ice-block-spell", time=2.1)[0][
                "entity_scene"
            ]["attack_spells"][0]
            ice["id"] = "ice"
            add_cast(inputs, ice)
            result = simulate_full_battle(*inputs, self.catalog)
            combat = result["combat"]
            revivals = [
                e for e in combat["trace"] if e.get("event") == "spell_hero_revived"
            ]
            self.assertEqual(len(revivals), 1)
            self.assertEqual(
                (revivals[0]["actor"], revivals[0]["time_seconds"]), ("royal", 2.1)
            )
            self.assertAlmostEqual(
                revivals[0]["hp"], combat["actors"]["royal"]["maximum_hp"] * 0.6
            )
            shots = [
                e
                for e in combat["trace"]
                if e.get("event") == "projectile_launch" and e["source"] == "royal"
            ]
            self.assertTrue(shots)
            self.assertAlmostEqual(shots[0]["time_seconds"], 9.2)
            activations = [
                e for e in combat["trace"] if e.get("event") == "hero_ability"
            ]
            self.assertEqual([e["status"] for e in activations], ["activated"])
            pulses = [
                e["time_seconds"]
                for e in combat["trace"]
                if e.get("event") == "electro_boots_pulse"
            ]
            self.assertTrue(pulses)
            self.assertAlmostEqual(pulses[0], 2.4)
            self.assertEqual(len(pulses), len(set(pulses)))
            self.assertEqual(result["resource_use"]["used_hero_ability_ids"], ["royal"])
            self.assertEqual(
                sum(s["spent"] for s in result["resource_use"]["spell_slots"]), 3
            )
            invalid = deepcopy(inputs)
            invalid[0]["entity_scene"]["effects"].append(ability("royal", 2.2, "reuse"))
            with self.assertRaisesRegex(InputError, "one shared ability"):
                compile_full_battle(*invalid, self.catalog)

    def test_paid_angry_recall_return_before_after_expiry_restores_targeting(self):
        for step in (0.017, 0.25):
            for return_at, active in ((6, True), (9, False)):
                inputs = spell_battle(
                    self.catalog, "angry-spell", step=step, duration=return_at + 0.5
                )
                scene = inputs[0]["entity_scene"]
                scene["entities"][0]["town_hall_parameters"]["activation"][
                    "activation_delay_seconds"
                ] = 100
                scene["entities"][1].update(x=6.5, first_attack_seconds=0)
                scene["entities"][1]["modifiers"]["hitpoints_multiplier"] = 1
                scene["attack_spells"][0].update(x=6.5)
                scene["entities"].append(
                    entity_instance(
                        "gold",
                        "gold-storage",
                        1,
                        "defense",
                        x=2,
                        y=4,
                        mode="passive",
                        statistics_mode="none",
                        attack_parameters={},
                        inactive_attack_interval_seconds=1,
                    )
                )
                inputs[3]["inventory"]["gold-storage"] = 1
                inputs[3]["buildings"].append(
                    {
                        "instance": "gold",
                        "id": "gold-storage",
                        "level": 1,
                        "x": 2,
                        "y": 4,
                        "mode": "passive",
                        "counts_for_destruction": True,
                    }
                )
                recall(inputs, 1, return_at, x=6.5)
                result = simulate_full_battle(*inputs, self.catalog)
                combat = result["combat"]
                frame = next(
                    f
                    for f in combat["frames"]
                    if abs(f["time_seconds"] - return_at) < 1e-8
                )
                actor = frame["actors"]["pekka-0"]
                self.assertEqual(actor["spell_defense_priority"], active)
                self.assertEqual(actor["spell_movement_bonus"] > 0, active)
                shots = [
                    e
                    for e in combat["trace"]
                    if e.get("event") == "projectile_launch"
                    and e["source"] == "pekka-0"
                    and e["time_seconds"] >= return_at
                ]
                self.assertTrue(shots)
                self.assertEqual(shots[0]["target"], "hall" if active else "gold")
                self.assertEqual(
                    result["resource_use"]["deployed_attacker_ids"], ["pekka-0"]
                )
                self.assertEqual(
                    sum(s["spent"] for s in result["resource_use"]["spell_slots"]), 2
                )


if __name__ == "__main__":
    unittest.main()
