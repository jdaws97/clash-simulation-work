"""Paid donated carrier, finite real children, flight and single streamed CC."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.attack_spell_rules import RULES, SCOPE
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.siege_barrels import barrel_generated_requirements
from clashlab.spatial import simulate_spatial

from test_adapters import entity_instance
from test_battle_termination import termination_policy, classification
from test_full_battle import freeze_cast
from test_recipe_integration import recipe_instance
from test_siege_integration import reinforcement_battle
from test_siege_lifecycle import barrel_instance
from test_siege_machines import release_command


ROOT = Path(__file__).resolve().parents[1]


def wagon_battle(catalog, duration=1.1, flight=0.5, level=1):
    carrier = barrel_instance(catalog, "sky-wagon", flight)
    carrier.update(town_hall=16, level=level, x=9.5, y=5.5)
    carrier["siege_parameters"].update(origin="donated", donor_town_hall=18)
    members = barrel_generated_requirements(
        "siege", "sky-wagon", catalog.level("sky-wagon", level), catalog
    )
    carrier["siege_parameters"]["behavior"]["generated_release"]["offsets"] = {
        m["actor_id"]: {"x": -3, "y": 0} for m in members
    }
    spec, account, army, layout = reinforcement_battle(catalog, carrier, duration)
    spec["termination_policy"] = termination_policy()
    scene = spec["entity_scene"]
    scene.update(scope=SCOPE, model_rules=deepcopy(RULES), attack_spells=[])
    scene["attacking_reinforcements"]["deployment_policy"]["regions"][0]["right"] = (
        scene["width"]
    )
    scene["attacking_reinforcements"]["release"]["offsets"]["payload"] = {
        "x": -3,
        "y": 0,
    }
    # Give children time to attack after the independently settled barrel hit.
    scene["entities"][0]["modifiers"]["hitpoints_multiplier"] = 100
    account["donation_levels"]["sky-wagon"] = level
    account["levels"].pop("sky-wagon")
    for member in members:
        name, actor_id = member["entity"], member["actor_id"]
        child = (
            entity_instance(actor_id, name, member["level"], "attack")
            if name == "minion"
            else recipe_instance(catalog, name, actor_id)
        )
        child.update(
            level=member["level"],
            town_hall=16,
            spawn_seconds="controlled",
            x=9.5,
            y=5.5,
            barrel_member_parameters={
                "carrier_id": "siege",
                "barrel_index": member["barrel_index"],
            },
        )
        scene["entities"].append(child)
    return spec, account, army, layout


class SkyWagonIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_paid_carrier_loss_preserves_flight_real_weapons_and_separate_resources(
        self,
    ):
        for step in (0.25, 0.017):
            inputs = wagon_battle(self.catalog)
            inputs[0]["entity_scene"].update(
                maximum_step_seconds=step, effects=[release_command(0.1)]
            )
            result = simulate_full_battle(*inputs, self.catalog)
            combat = result["combat"]
            self.assertEqual(combat["actors"]["siege"]["death_time"], 0.1)
            generated = result["resource_use"]["generated_siege_units"]
            released = {
                key
                for key, state in generated.items()
                if state["released_at"] is not None
            }
            expected = {
                m["actor_id"]
                for m in barrel_generated_requirements(
                    "siege",
                    "sky-wagon",
                    self.catalog.level("sky-wagon", 1),
                    self.catalog,
                )
                if m["barrel_index"] == 0
            }
            self.assertEqual(released, expected)
            self.assertEqual(len(generated), 16)
            self.assertTrue(
                all(generated[key]["released_at"] == 0.5 for key in released)
            )
            self.assertTrue(
                all(
                    state["phase"] == "cancelled"
                    for key, state in generated.items()
                    if key not in released
                )
            )
            self.assertEqual(
                result["resource_use"]["deployed_attacker_ids"], ["payload", "siege"]
            )
            self.assertEqual(
                result["resource_use"]["deployment_times_seconds"]["payload"], 0.5
            )
            self.assertFalse(
                result["resource_use"]["clan_castle_delivery"]["pending_member_ids"]
            )
            claims = [
                e for e in combat["trace"] if e.get("event") == "payload_barrel_claimed"
            ]
            self.assertEqual(len(claims), 1)
            impacts = [
                e for e in combat["trace"] if e.get("event") == "siege_barrel_impact"
            ]
            self.assertEqual(impacts[0]["time_seconds"], 0.5)
            launches = {
                e["source"]
                for e in combat["trace"]
                if e.get("event") == "projectile_launch"
            }
            self.assertTrue(released <= launches)
            self.assertEqual(result["outcome"]["counted_building_count"], 1)
            self.assertEqual(result["outcome"]["end_reason"], "declared_time_limit")

    def test_unlaunched_termination_does_not_create_generated_resources(self):
        inputs = wagon_battle(self.catalog, duration=0.3)
        inputs[0]["entity_scene"]["effects"] = [release_command(0)]
        result = simulate_full_battle(*inputs, self.catalog)
        self.assertTrue(
            all(
                v["phase"] == "cancelled"
                for v in result["resource_use"]["generated_siege_units"].values()
            )
        )
        self.assertFalse(
            any(
                e.get("event") == "siege_barrel_launch"
                for e in result["combat"]["trace"]
            )
        )
        self.assertEqual(
            result["resource_use"]["deployed_attacker_ids"], ["payload", "siege"]
        )

    def test_hp_death_keeps_last_released_packet_and_continuation(self):
        inputs = wagon_battle(self.catalog, duration=1.1)
        hall = inputs[0]["entity_scene"]["entities"][0]
        hall["town_hall_parameters"]["activation"].update(
            initial_state="active", activation_delay_seconds=0
        )
        hall["modifiers"]["damage_multiplier"] = 100000
        result = simulate_full_battle(*inputs, self.catalog)
        combat = result["combat"]
        self.assertEqual(combat["actors"]["siege"]["death_time"], 0)
        self.assertEqual(
            combat["sieges"]["states"]["siege"]["termination_reason"], "hp_death"
        )
        self.assertTrue(
            any(
                e.get("event") == "siege_barrel_impact" and e["time_seconds"] == 0.5
                for e in combat["trace"]
            )
        )
        self.assertGreaterEqual(result["outcome"]["elapsed_seconds"], 0.5)
        self.assertEqual(
            result["resource_use"]["deployment_times_seconds"]["payload"], 0.5
        )

        protected = deepcopy(inputs)
        protected[0]["entity_scene"]["freeze_spells"] = [freeze_cast("save-carrier", 0)]
        protected[2]["spells"] = [{"id": "freeze-spell", "level": 1, "count": 1}]
        protected[0]["termination_policy"] = termination_policy(
            [
                classification(
                    {"origin": "army", "entity": "freeze-spell", "level": 1},
                    "support_only",
                    "ignore",
                )
            ]
        )
        frozen = simulate_full_battle(*protected, self.catalog)
        self.assertIsNone(frozen["combat"]["actors"]["siege"]["death_time"])
        self.assertTrue(frozen["resource_use"]["spell_slots"][0]["spent"])
        self.assertEqual(
            frozen["resource_use"]["deployment_times_seconds"]["payload"], 0.5
        )

    def test_finite_exhaustion_releases_all_barrels_once_with_one_cc_owner(self):
        inputs = wagon_battle(self.catalog, duration=24.6)
        inputs[0]["entity_scene"]["maximum_step_seconds"] = 1
        result = simulate_full_battle(*inputs, self.catalog)
        events = result["combat"]["trace"]
        launches = [e for e in events if e.get("event") == "siege_barrel_launch"]
        self.assertEqual([e["time_seconds"] for e in launches], [0, 8, 16, 24])
        self.assertEqual([e["barrel_index"] for e in launches], [0, 1, 2, 3])
        generated = result["resource_use"]["generated_siege_units"]
        self.assertEqual(len(generated), 16)
        self.assertTrue(all(v["released_at"] is not None for v in generated.values()))
        self.assertEqual(result["combat"]["actors"]["siege"]["death_time"], 24)
        self.assertEqual(
            len([e for e in events if e.get("event") == "payload_barrel_claimed"]), 1
        )
        self.assertEqual(
            result["resource_use"]["deployed_attacker_ids"], ["payload", "siege"]
        )

    def test_positive_tiny_flight_sets_actual_hall_outcome_after_launch(self):
        inputs = wagon_battle(self.catalog, duration=0.1, flight=1e-12)
        inputs[0]["entity_scene"]["entities"][0]["modifiers"][
            "hitpoints_multiplier"
        ] = 0.0001
        result = simulate_full_battle(*inputs, self.catalog)
        self.assertEqual(result["outcome"]["stars"], 3)
        self.assertEqual(result["outcome"]["elapsed_seconds"], 1e-12)
        self.assertEqual(
            result["resource_use"]["deployment_times_seconds"]["payload"], 1e-12
        )
        impacts = [
            e
            for e in result["combat"]["trace"]
            if e.get("event") == "siege_barrel_impact"
        ]
        self.assertEqual(impacts[0]["time_seconds"], 1e-12)

    def test_complete_source_manifest_and_donation_are_required_without_player_child_deployment(
        self,
    ):
        for mutation in (
            "missing",
            "level",
            "owner",
            "paid",
            "donation",
            "deployment",
            "opt_in",
        ):
            inputs = wagon_battle(self.catalog)
            scene = inputs[0]["entity_scene"]
            child = scene["entities"][-1]
            if mutation == "missing":
                scene["entities"].pop()
            elif mutation == "level":
                child["level"] -= 1
            elif mutation == "owner":
                child["barrel_member_parameters"]["carrier_id"] = "other"
            elif mutation == "paid":
                inputs[2]["troops"] = [
                    {"id": child["entity"], "level": child["level"], "count": 1}
                ]
                inputs[1]["levels"][child["entity"]] = child["level"]
            elif mutation == "donation":
                inputs[1]["donation_levels"].pop("sky-wagon")
            elif mutation == "opt_in":
                scene["entities"][2]["siege_experimental_opt_in"] = False
            else:
                scene["effects"] = [
                    {
                        "id": "bad",
                        "kind": "deploy",
                        "time_seconds": 0,
                        "targets": [child["id"]],
                        "positions": {child["id"]: {"x": 1.5, "y": 1.5}},
                    }
                ]
            with self.subTest(mutation=mutation), self.assertRaises(InputError):
                compile_full_battle(*inputs, self.catalog)
        inputs = wagon_battle(self.catalog)
        compiled = compile_full_battle(*inputs, self.catalog)["compiled"]["scene"]
        for mutation in ("owner", "child_owner"):
            forged = deepcopy(compiled)
            if mutation == "owner":
                next(a for a in forged["actors"] if a["id"] == "siege")["attack_model"][
                    "entity"
                ] = "troop-launcher"
            else:
                next(a for a in forged["actors"] if "barrel_member_model" in a)[
                    "summon_model"
                ] = {"owner": "other"}
            with self.subTest(raw=mutation), self.assertRaises(InputError):
                simulate_spatial(forged)
        del compiled["attacking_reinforcements"]
        with self.assertRaises(InputError):
            simulate_spatial(compiled)


if __name__ == "__main__":
    unittest.main()
