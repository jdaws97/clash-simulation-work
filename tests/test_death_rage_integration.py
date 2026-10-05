"""Paid Super Valkyrie death/Recall/continuation without a free Rage charge."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.attacking_extensions import SCOPE
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial
from test_adapters import entity_instance, projectile
from test_advanced_spell_integration import spell_battle, SOURCE
from test_battle_termination import classification, termination_policy
from test_full_battle import add_reserve, deployment
from test_remaining_troops import rage_field
from test_spell_lifecycle_integration import recall
from test_valkyries import placement_parameters


def death_battle(catalog, step, *, duration=3.7):
    inputs = spell_battle(catalog, "ice-block-spell", step=step, duration=duration)
    spec, account, army, layout = inputs
    scene = spec["entity_scene"]
    scene.pop("advanced_spell_binding")
    scene["attack_spells"] = []
    scene["entities"][1]["first_attack_seconds"] = 0
    scene["entities"][1]["modifiers"]["hitpoints_multiplier"] = 50
    army["spells"] = [{"id": "rage-spell", "level": 1, "count": 1}]
    account["levels"].update({"rage-spell": 1, "super-valkyrie": 7})
    account["active_super_troops"] = ["super-valkyrie"]
    army["troops"].append({"id": "super-valkyrie", "level": 7, "count": 1})
    parent = entity_instance(
        "super-valk",
        "super-valkyrie",
        7,
        "attack",
        town_hall=16,
        x=9.5,
        y=5.5,
        first_attack_seconds=0,
        wall_parameters={"kind": "avoid", "source": SOURCE},
        attack_parameters={"radius": 1.5, "projectile": projectile()},
        attacking_extension_scope=SCOPE,
        valkyrie_parameters=placement_parameters(maximum_extra_travel_seconds=0),
        death_buff_parameters={
            "source": SOURCE,
            "status": "explicit_uncalibrated_hypothesis",
            "release_delay_seconds": 0.1,
            "field": rage_field(),
            "trigger": "actual_hp_death_once",
            "origin": "generated_troop_effect_not_paid_spell",
        },
    )
    parent["modifiers"]["hitpoints_multiplier"] = 0.0001
    scene["entities"].append(parent)
    spec["termination_policy"] = termination_policy(
        [
            classification(
                {"origin": "army", "entity": "rage-spell", "level": 1},
                "support_only",
                "ignore",
            )
        ]
    )
    return inputs


class DeathRageIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")

    def test_death_field_has_one_owner_actual_weapon_damage_expiry_and_no_spell_spend(
        self,
    ):
        for step in (0.017, 0.25):
            for delay in (0.1, 5e-11):
                with self.subTest(step=step, delay=delay):
                    inputs = death_battle(self.catalog, step)
                    inputs[0]["entity_scene"]["entities"][-1]["death_buff_parameters"][
                        "release_delay_seconds"
                    ] = delay
                    result = simulate_full_battle(*inputs, self.catalog)
                    combat = result["combat"]
                    self.assertEqual(combat["actors"]["super-valk"]["death_time"], 0)
                    emitted = [
                        e
                        for e in combat["trace"]
                        if e.get("event") == "troop_death_rage_released"
                    ]
                    self.assertEqual(len(emitted), 1)
                    self.assertEqual(emitted[0]["time_seconds"], delay)
                    self.assertEqual(
                        combat["troop_death_buffs"]["fields"],
                        {"super-valk": "super-valk:death-rage"},
                    )
                    field = combat["buffs"]["fields"]["super-valk:death-rage"]
                    self.assertEqual(field["generated_effect_owner"], "super-valk")
                    self.assertIn("super-valk:death-rage", combat["buffs"]["expired"])
                    hits = [
                        e
                        for e in combat["trace"]
                        if e.get("event") == "projectile_impact"
                        and e.get("source") == "pekka-0"
                    ]
                    self.assertEqual(len(hits), 3)
                    damage = combat["actors"]["pekka-0"]["damage"]
                    self.assertEqual(
                        [e["damage"] for e in hits], [damage, 2 * damage, damage]
                    )
                    self.assertEqual(
                        result["resource_use"]["spell_slots"][0]["spent"], False
                    )
                    self.assertEqual(
                        len(result["resource_use"]["deployed_attacker_ids"]), 2
                    )
                    self.assertEqual(
                        result["resource_use"]["generated_troop_effects"][
                            "super-valk:death-rage"
                        ]["released_at"],
                        delay,
                    )
                    self.assertEqual(
                        result["outcome"]["end_reason"], "declared_time_limit"
                    )

    def test_recall_is_not_death_pending_buff_does_not_keep_empty_army_alive_and_raw_guards_hold(
        self,
    ):
        for step in (0.017, 0.25):
            for reserve in (False, True):
                inputs = death_battle(self.catalog, step, duration=2)
                spec, account, army, _ = inputs
                scene = spec["entity_scene"]
                scene["entities"] = [
                    a for a in scene["entities"] if a["id"] != "pekka-0"
                ]
                army["troops"] = [
                    item for item in army["troops"] if item["id"] == "super-valkyrie"
                ]
                recall(inputs, 0, 1, x=9.5)
                if reserve:
                    add_reserve(spec, army, account)
                    command = deployment("reserve", 1.5)
                    command["positions"]["reserve"] = {"x": 0.5, "y": 15.5}
                    scene["effects"] = [command]
                result = simulate_full_battle(*inputs, self.catalog)
                combat = result["combat"]
                self.assertEqual(combat["actors"]["super-valk"]["death_time"], 1)
                emitted = [
                    e
                    for e in combat["trace"]
                    if e.get("event") == "troop_death_rage_released"
                ]
                self.assertEqual(len(emitted), int(reserve))
                if reserve:
                    self.assertAlmostEqual(emitted[0]["time_seconds"], 1.1)
                else:
                    self.assertEqual(
                        result["outcome"]["end_reason"], "attack_force_exhausted"
                    )
                    self.assertEqual(result["outcome"]["elapsed_seconds"], 1)
                self.assertEqual(
                    sum(s["spent"] for s in result["resource_use"]["spell_slots"]), 1
                )
        inputs = death_battle(self.catalog, 0.25)
        raw = compile_full_battle(*inputs, self.catalog)["compiled"]["scene"]
        owner = next(a for a in raw["actors"] if a["id"] == "super-valk")
        owner.pop("troop_death_buff_model")
        with self.assertRaisesRegex(InputError, "Death Rage requires"):
            simulate_spatial(raw)
        inputs[0]["entity_scene"]["entities"][-1].pop("attacking_extension_scope")
        with self.assertRaisesRegex(InputError, "explicit attacking extension"):
            compile_full_battle(*inputs, self.catalog)


if __name__ == "__main__":
    unittest.main()
