"""Actual termination time and lifecycle history determine spent resources."""

from copy import deepcopy
import unittest

from clashlab.battle_resources import battle_resource_use
from clashlab.common import InputError

from test_battle_termination import actor, spell


class BattleResourceTests(unittest.TestCase):
    def test_underground_pet_remains_deployed_after_controlled_spawn_transition(self):
        bindings = {
            "attacker_bindings": {
                "hero": {"origin": "army_heroes"},
                "diggy": {"origin": "assigned_hero_pet"},
            },
            "planned_deployments": {"hero": 0.2},
            "spell_bindings": [],
        }
        combat = {
            "actors": {
                "hero": actor("hero", hp=0),
                "diggy": actor("diggy", spawn="controlled"),
            },
            "hero_pets": {
                "pets": {"diggy": {"deployed_at": 0.2, "phase": "underground"}}
            },
            "trace": [],
        }
        result = battle_resource_use(bindings, combat, 1)
        self.assertEqual(result["deployed_attacker_ids"], ["diggy", "hero"])
        self.assertEqual(result["deployment_times_seconds"]["diggy"], 0.2)

    def test_future_deployment_and_support_spell_are_unspent_after_early_stop(self):
        bindings = {
            "attacker_bindings": {"reserve": {"origin": "army_troops"}},
            "planned_deployments": {"reserve": 5},
            "spell_bindings": [spell(cast={"cast_id": "late", "time_seconds": 6})],
        }
        combat = {
            "actors": {"reserve": actor("reserve", spawn="controlled")},
            "trace": [],
        }
        result = battle_resource_use(bindings, combat, 2)
        self.assertEqual(result["undeployed_attacker_ids"], ["reserve"])
        self.assertFalse(result["spell_slots"][0]["spent"])

    def test_blocked_payload_has_spent_delivery_but_no_member_deployment(self):
        bindings = {
            "attacker_bindings": {"payload": {"origin": "clan_castle_troops"}},
            "planned_deployments": {},
            "spell_bindings": [],
        }
        combat = {
            "actors": {"payload": actor("payload", spawn="controlled")},
            "sieges": {
                "reinforcements": {
                    "group": {
                        "delivery_time": 1,
                        "delivery_reason": "hp_death",
                        "remaining": ["payload"],
                    },
                    "members": {"payload": {"released_at": None}},
                }
            },
            "trace": [],
        }
        result = battle_resource_use(bindings, combat, 2)
        self.assertEqual(result["undeployed_attacker_ids"], ["payload"])
        self.assertEqual(
            result["clan_castle_delivery"],
            {
                "spent": True,
                "time_seconds": 1,
                "reason": "hp_death",
                "pending_member_ids": ["payload"],
            },
        )

    def test_boundary_deployment_cast_and_successful_ability_are_inclusive(self):
        bindings = {
            "attacker_bindings": {"hero": {"origin": "army_heroes"}},
            "planned_deployments": {"hero": 2},
            "spell_bindings": [spell(cast={"cast_id": "now", "time_seconds": 2})],
        }
        combat = {
            "actors": {"hero": actor("hero", spawn=2)},
            "trace": [
                {
                    "event": "hero_ability",
                    "hero_id": "hero",
                    "time_seconds": 2,
                    "status": "activated",
                },
                {
                    "event": "hero_ability",
                    "hero_id": "failed",
                    "time_seconds": 2,
                    "status": "rejected",
                },
                {
                    "event": "hero_ability",
                    "hero_id": "future",
                    "time_seconds": 3,
                    "status": "activated",
                },
            ],
        }
        before = deepcopy((bindings, combat))
        result = battle_resource_use(bindings, combat, 2)
        self.assertEqual(result["deployed_attacker_ids"], ["hero"])
        self.assertTrue(result["spell_slots"][0]["spent"])
        self.assertEqual(result["used_hero_ability_ids"], ["hero"])
        self.assertEqual((bindings, combat), before)

    def test_missing_pet_lifecycle_cannot_be_replaced_with_current_spawn_flag(self):
        bindings = {
            "attacker_bindings": {"pet": {"origin": "assigned_hero_pet"}},
            "planned_deployments": {},
            "spell_bindings": [],
        }
        combat = {"actors": {"pet": actor("pet")}, "trace": []}
        with self.assertRaisesRegex(InputError, "deployment lifecycle"):
            battle_resource_use(bindings, combat, 1)


if __name__ == "__main__":
    unittest.main()
