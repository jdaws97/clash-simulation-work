"""Portable v29 combined-army lifecycle and explicit rejection regression."""

from collections import Counter
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_full_army_regression import fingerprint, inputs
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle


class FullArmyRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arguments = inputs()
        cls.first = simulate_full_battle(*deepcopy(cls.arguments))
        cls.second = simulate_full_battle(*deepcopy(cls.arguments))

    def test_identical_inputs_have_identical_canonical_outcome_events_and_receipts(
        self,
    ):
        for field in ("outcome", "resource_use"):
            self.assertEqual(
                fingerprint(self.first[field]), fingerprint(self.second[field])
            )
        self.assertEqual(
            fingerprint(self.first["combat"]["trace"]),
            fingerprint(self.second["combat"]["trace"]),
        )
        self.assertEqual(self.first["outcome"]["elapsed_seconds"], 16)
        self.assertEqual(self.first["outcome"]["end_reason"], "declared_time_limit")

    def test_dynamic_resource_receipts_cover_every_selected_actor_once(self):
        result = self.first
        validation = result["validation"]
        self.assertEqual(
            validation["army"]["used"],
            {
                "army_housing": 320,
                "spell_housing": 11,
                "clan_castle_troops": 50,
                "clan_castle_spells": 3,
            },
        )
        bindings = validation["attacker_bindings"]
        self.assertEqual(
            Counter(item["origin"] for item in bindings.values()),
            {
                "army_troops": 16,
                "army_heroes": 4,
                "assigned_hero_pet": 4,
                "siege": 1,
                "clan_castle_troops": 6,
            },
        )
        receipts = result["resource_use"]
        self.assertEqual(set(receipts["deployed_attacker_ids"]), set(bindings))
        self.assertEqual(len(receipts["deployed_attacker_ids"]), len(bindings))
        self.assertEqual(receipts["undeployed_attacker_ids"], [])
        self.assertEqual(
            receipts["clan_castle_delivery"],
            {
                "spent": True,
                "time_seconds": 6.0,
                "reason": "manual_release",
                "pending_member_ids": [],
            },
        )
        releases = [
            event
            for event in result["combat"]["trace"]
            if event.get("event") == "payload_released"
        ]
        self.assertEqual(
            Counter(event["member"] for event in releases),
            {key: 1 for key in bindings if key.startswith("cc-")},
        )
        for event in releases:
            self.assertEqual(
                receipts["deployment_times_seconds"][event["member"]],
                event["time_seconds"],
            )
        self.assertEqual(
            receipts["used_hero_ability_ids"],
            ["archer-queen", "grand-warden", "royal-champion"],
        )
        self.assertEqual(sum(slot["spent"] for slot in receipts["spell_slots"]), 2)
        self.assertEqual(
            sum(
                slot["origin"] == "clan_castle" and slot["spent"]
                for slot in receipts["spell_slots"]
            ),
            0,
        )

    def test_generated_clones_and_pets_preserve_owner_and_inventory_separation(self):
        actors = self.first["compiled"]["scene"]["actors"]
        clones = [actor for actor in actors if "summon_model" in actor]
        self.assertEqual(len(clones), 2)
        for actor in clones:
            self.assertEqual(actor["summon_model"]["parent"], "archer-queen")
            self.assertNotIn(actor["id"], self.first["validation"]["attacker_bindings"])
        pets = [actor for actor in actors if "pet_model" in actor]
        self.assertEqual(
            {actor["pet_model"]["hero_id"] for actor in pets},
            {"archer-queen", "grand-warden", "royal-champion", "dragon-duke"},
        )
        for pet in pets:
            times = self.first["resource_use"]["deployment_times_seconds"]
            self.assertEqual(times[pet["id"]], times[pet["pet_model"]["hero_id"]])
        deployments = [
            event
            for event in self.first["combat"]["trace"]
            if event.get("effect_id") == "ability-archer-queen-mirror"
        ]
        self.assertEqual(len(deployments), 1)
        self.assertEqual(
            set(deployments[0]["targets"]), {actor["id"] for actor in clones}
        )

    def test_illegal_and_unsupported_selected_resources_are_rejected(self):
        for mutation in (
            "overflow",
            "unknown",
            "donor-level",
            "duplicate-pet",
            "duplicate-deployment",
            "unsupported-spell",
        ):
            with self.subTest(mutation=mutation):
                specification, account, army, layout, catalog = deepcopy(self.arguments)
                if mutation == "overflow":
                    army["troops"][0]["count"] += 1
                elif mutation == "unknown":
                    army["troops"][0]["id"] = "unsupported-synthetic-troop"
                elif mutation == "donor-level":
                    army["clan_castle"]["troops"][0]["level"] += 100
                elif mutation == "duplicate-pet":
                    army["heroes"][1]["pet"] = deepcopy(army["heroes"][0]["pet"])
                elif mutation == "duplicate-deployment":
                    command = deepcopy(specification["entity_scene"]["effects"][0])
                    command["id"] = "duplicate-synthetic-deployment"
                    specification["entity_scene"]["effects"].append(command)
                else:
                    army["spells"][0]["id"] = "unsupported-synthetic-spell"
                with self.assertRaises(InputError):
                    compile_full_battle(specification, account, army, layout, catalog)


if __name__ == "__main__":
    unittest.main()
