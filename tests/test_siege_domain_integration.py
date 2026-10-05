"""Paid carrier, finite generated troops and released damage in full battles."""

from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import simulate_full_battle, compile_full_battle
from test_adapters import entity_instance
from test_siege_integration import reinforcement_battle
from test_siege_lifecycle import extended_instance, SOURCE
from test_siege_machines import release_command


ROOT = Path(__file__).resolve().parents[1]


class SiegeDomainIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def inputs(self, entity, duration=0.8):
        carrier = extended_instance(self.catalog, entity)
        carrier["town_hall"] = 16
        inputs = reinforcement_battle(self.catalog, carrier, duration)
        if entity == "siege-barracks":
            carrier.update(x=9.5, y=5.5)
            scene = inputs[0]["entity_scene"]
            scene["attacking_reinforcements"]["deployment_policy"]["regions"][0][
                "right"
            ] = scene["width"]
            for item in carrier["siege_parameters"]["behavior"]["schedule"]:
                member = entity_instance(
                    item["actor_id"],
                    item["entity"],
                    item["level"],
                    "attack",
                    town_hall=16,
                    x=9.5,
                    y=5.5,
                    spawn_seconds="controlled",
                    wall_parameters={"kind": "avoid", "source": SOURCE},
                    barracks_member_parameters={
                        "source": SOURCE,
                        "carrier_id": "siege",
                        "level_basis": "attacker_confirmed_troop_level",
                    },
                )
                if item["entity"] == "wizard":
                    member["attack_parameters"]["radius"] = 1
                    member["attack_parameters"]["projectile"][
                        "inactive_primary_policy"
                    ] = "fizzle"
                    member["wizard_parameters"] = {
                        "source": SOURCE,
                        "splash_layer_policy": "all_declared_target_layers",
                    }
                inputs[0]["entity_scene"]["entities"].append(member)
                inputs[1]["levels"][item["entity"]] = item["level"]
        return inputs

    def test_flinger_released_flames_survive_manual_release_with_single_cc(self):
        for step in (0.017, 0.25):
            with self.subTest(step=step):
                inputs = self.inputs("flame-flinger")
                inputs[0]["entity_scene"].update(
                    maximum_step_seconds=step, effects=[release_command(0.15)]
                )
                result = simulate_full_battle(*inputs, self.catalog)
                combat = result["combat"]
                self.assertAlmostEqual(combat["actors"]["siege"]["death_time"], 0.15)
                self.assertLess(
                    combat["actors"]["hall"]["hp"],
                    combat["actors"]["hall"]["maximum_hp"],
                )
                flames = [
                    e
                    for e in combat["trace"]
                    if e.get("event") == "extended_siege_impact"
                    and e.get("packet_kind") == "flame_pulse"
                ]
                self.assertTrue(any(e["time_seconds"] > 0.15 for e in flames))
                self.assertEqual(
                    result["resource_use"]["deployed_attacker_ids"],
                    ["payload", "siege"],
                )
                self.assertFalse(
                    result["resource_use"]["clan_castle_delivery"]["pending_member_ids"]
                )

    def test_barracks_children_fight_and_keep_separate_generated_accounting(self):
        for step in (0.017, 0.25):
            with self.subTest(step=step):
                inputs = self.inputs("siege-barracks")
                inputs[0]["entity_scene"].update(
                    maximum_step_seconds=step, effects=[release_command(0.7)]
                )
                result = simulate_full_battle(*inputs, self.catalog)
                combat = result["combat"]
                generated = result["resource_use"]["generated_siege_units"]
                released = [
                    key
                    for key, state in generated.items()
                    if state["released_at"] is not None
                ]
                self.assertEqual(
                    sorted(released), ["generated-pekka-0", "generated-wizard-0"]
                )
                self.assertEqual(
                    result["resource_use"]["deployed_attacker_ids"],
                    ["payload", "siege"],
                )
                self.assertFalse(result["resource_use"]["undeployed_attacker_ids"])
                launches = [
                    e
                    for e in combat["trace"]
                    if e.get("event") == "projectile_launch"
                    and e.get("source") in released
                ]
                self.assertTrue(launches)
                self.assertLess(
                    combat["actors"]["hall"]["hp"],
                    combat["actors"]["hall"]["maximum_hp"],
                )
                self.assertTrue(
                    all(combat["actors"][key]["hp"] > 0 for key in released)
                )
                self.assertFalse(
                    result["resource_use"]["clan_castle_delivery"]["pending_member_ids"]
                )

    def test_barracks_rejects_unconfirmed_child_level_and_player_deployment(self):
        inputs = self.inputs("siege-barracks")
        inputs[1]["levels"]["wizard"] = 2
        with self.assertRaisesRegex(InputError, "confirmed attacker research"):
            compile_full_battle(*inputs, self.catalog)
        inputs[1]["levels"]["wizard"] = 1
        inputs[0]["entity_scene"]["effects"] = [
            {
                "id": "bad",
                "kind": "deploy",
                "time_seconds": 0.1,
                "targets": ["generated-wizard-0"],
                "positions": {"generated-wizard-0": {"x": 1.5, "y": 7.5}},
            }
        ]
        with self.assertRaises(InputError):
            compile_full_battle(*inputs, self.catalog)


if __name__ == "__main__":
    unittest.main()
