"""Full-army fixtures preserve inventory ownership and generated actor coverage."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import read_json
from clashlab.development_armies import benchmark_army, build_army_scene
from clashlab.development_village import termination_policy
from clashlab.full_battle import compile_full_battle
from clashlab.planning import planning_account
from clashlab.termination_rules import RULES, SCOPE

from test_full_battle import fixture


ROOT = Path(__file__).resolve().parents[1]


class DevelopmentArmyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.owned = read_json(ROOT / "profiles/sample-th16.json")
        cls.base = read_json(ROOT / "data/battle-policies/development-th16.json")
        cls.policies = read_json(
            ROOT / "data/battle-policies/development-full-army.json"
        )

    def build(self, family):
        account = planning_account(
            self.owned,
            self.catalog,
            {
                "mode": "ranked",
                "recipient_level_rule": "unique_capacity_match",
                "super_troops": [],
            },
        )
        _, _, _, layout = fixture(self.catalog)
        layout.update(width=56, height=56)
        layout["inventory"]["eagle-artillery"] = 1
        layout["buildings"].append(
            {
                "instance": "eagle",
                "id": "eagle-artillery",
                "level": 7,
                "x": 30,
                "y": 30,
                "mode": "normal",
                "counts_for_destruction": True,
            }
        )
        army = benchmark_army(account, self.policies, family)
        scene = build_army_scene(
            layout, self.catalog, self.base, self.policies, account, army, SCOPE, RULES
        )
        specification = {
            "id": "full-army-binding-check",
            "source": self.policies["source"],
            "time_limit_seconds": 180,
            "entity_scene": scene,
            "termination_policy": termination_policy(army, self.base),
        }
        return compile_full_battle(specification, account, army, layout, self.catalog)

    def test_both_armies_bind_every_generated_unit_and_separate_donor_inventory(self):
        for family in ("air", "ground"):
            with self.subTest(family=family):
                result = self.build(family)
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
                scene = result["compiled"]["scene"]
                actors = {actor["id"]: actor for actor in scene["actors"]}
                attack_ids = {
                    key for key, actor in actors.items() if actor["team"] == "attack"
                }
                self.assertEqual(
                    set(scene["defending_unit_responses"]["actors"]), attack_ids
                )
                self.assertEqual(
                    set(
                        actors["eagle"]["indirect_model"]["activation"]["actor_weights"]
                    ),
                    attack_ids,
                )
                self.assertEqual(
                    sum("pet_model" in actor for actor in actors.values()), 4
                )
                self.assertEqual(
                    sum("summon_model" in actor for actor in actors.values()), 2
                )
                bindings = validation["attacker_bindings"]
                self.assertEqual(
                    sum(
                        item["origin"] == "clan_castle_troops"
                        for item in bindings.values()
                    ),
                    6,
                )
                self.assertEqual(bindings["siege"]["origin"], "siege")
                spells = validation["spell_bindings"]
                self.assertEqual(
                    sum(item["origin"] == "clan_castle" for item in spells), 2
                )

    def test_builds_preserve_owned_account_and_saved_behavior_contracts(self):
        before = deepcopy((self.owned, self.base, self.policies))
        self.build("air")
        self.build("ground")
        self.assertEqual((self.owned, self.base, self.policies), before)


if __name__ == "__main__":
    unittest.main()
