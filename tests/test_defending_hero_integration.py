"""Canonical layout banner settings bind the actual defending hero lifecycle."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.defending_hero_rules import RULES, SCOPE
from clashlab.full_battle import (
    compile_full_battle,
    compute_battle_outcome,
    simulate_full_battle,
)

from test_defending_heroes import SOURCE, defender_instance
from test_full_battle import fixture


ROOT = Path(__file__).resolve().parents[1]


class DefendingHeroIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def fixture(self, entity="barbarian-king", counted=False):
        inputs = fixture(self.catalog, time_limit=0.1)
        specification, _, _, layout = inputs
        scene = specification["entity_scene"]
        scene.update(scope=SCOPE, model_rules=deepcopy(RULES), buff_spells=[])
        defender = defender_instance(
            entity,
            instance_id="banner:defender",
            banner_id="banner",
            banner_x=2,
            banner_y=2,
            counts_for_destruction=counted,
        )
        if counted:
            defender["defending_hero_parameters"][
                "destruction_policy"
            ] = "statue_counts_hypothesis"
        scene["entities"].append(defender)
        scene["defending_unit_responses"] = {
            "source": SOURCE,
            "actors": {
                item["id"]: {"primary": "same_tier_as_buildings", "collateral": "allow"}
                for item in scene["entities"]
                if item["team"] == "attack"
            },
        }
        layout["inventory"]["hero-banner"] = 1
        layout["buildings"].append(
            {
                "instance": "banner",
                "id": "hero-banner",
                "level": None,
                "x": 2,
                "y": 2,
                "counts_for_destruction": counted,
                "settings": {"hero": entity, "level": 1},
            }
        )
        return inputs

    def test_mobile_defender_binds_without_consuming_attack_army_or_destruction_slot(
        self,
    ):
        inputs = self.fixture()
        result = simulate_full_battle(*inputs, self.catalog)
        binding = result["validation"]["defender_bindings"]["banner:defender"]
        self.assertEqual(binding["source_layout_instance"], "banner")
        self.assertEqual(binding["entity"], "barbarian-king")
        self.assertIn("banner:defender", result["combat"]["actors"])
        self.assertEqual(result["outcome"]["counted_building_count"], 1)
        self.assertIn("banner", result["outcome"]["excluded_instance_ids"])
        self.assertEqual(result["generated_summon_ids"], [])

    def test_wrong_hero_level_banner_or_canonical_actor_id_is_rejected(self):
        for change in ("hero", "level", "banner", "actor"):
            with self.subTest(change=change):
                inputs = self.fixture()
                scene = inputs[0]["entity_scene"]
                defender = scene["entities"][-1]
                if change == "hero":
                    inputs[3]["buildings"][-1]["settings"]["hero"] = "archer-queen"
                elif change == "level":
                    inputs[3]["buildings"][-1]["settings"]["level"] = 2
                elif change == "banner":
                    defender["defending_hero_parameters"]["banner"]["x"] = 3
                else:
                    defender["id"] = "unbound-defender"
                with self.assertRaises(InputError):
                    compile_full_battle(*inputs, self.catalog)

    def test_statue_destruction_uses_actor_death_but_reports_layout_instance(self):
        inputs = self.fixture("grand-warden", counted=True)
        result = simulate_full_battle(*inputs, self.catalog)
        self.assertEqual(result["outcome"]["counted_building_count"], 2)
        combat = deepcopy(result["combat"])
        # This synthetic death state has no observed termination receipt.
        combat.pop("termination")
        for actor_id in ("hall", "banner:defender"):
            combat["actors"][actor_id].update(hp=0, death_time=0.05)
        outcome = compute_battle_outcome(inputs[3], combat, 0.1)
        self.assertEqual(outcome["stars"], 3)
        self.assertEqual(outcome["destroyed_instance_ids"], ["banner", "hall"])


if __name__ == "__main__":
    unittest.main()
