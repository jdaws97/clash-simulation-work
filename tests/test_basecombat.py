"""An artificial wall probe must never masquerade as the complete village."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.basecombat import (
    compile_wall_mechanics_probe,
    inspect_blueprint_combat,
    simulate_wall_mechanics_probe,
)
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.adapters import TOWN_HALL_SCOPE
from clashlab.townhalls import TOWN_HALL_RULES

from test_townhalls import lifecycle


ROOT = Path(__file__).resolve().parents[1]


class BaseCombatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.base = read_json(ROOT / "tests/fixtures/blueprint-th16-synthetic.json")
        cls.probe = read_json(ROOT / "tests/fixtures/wall-probe-synthetic.json")

    def test_full_audit_retains_traps_heroes_and_unverified_town_hall_requirements(
        self,
    ):
        result = inspect_blueprint_combat(self.base, self.catalog)
        hall = next(
            group
            for group in result["required_entities"]
            if group["entity"] == "town-hall"
        )
        self.assertTrue(hall["conditional_adapter"]["available"])
        self.assertFalse(hall["complete_village_behavior_verified"])
        self.assertIn("hero-banner", result["unsupported_entity_types"])
        self.assertTrue(result["unknown_destruction_instances"])
        self.assertEqual(len(result["defending_hero_requirements"]), 4)
        self.assertFalse(result["full_game_prediction"])

    def test_probe_retains_all_walls_and_records_every_removed_instance(self):
        result = compile_wall_mechanics_probe(self.base, self.catalog, self.probe)
        self.assertEqual(len(result["retained_blueprint_instances"]), 326)
        self.assertEqual(len(result["removed_blueprint_instances"]), 141)
        self.assertIn("town-hall-0", result["removed_blueprint_instances"])
        self.assertTrue(
            result["removed_footprints_become_empty_in_this_artificial_experiment"]
        )
        self.assertFalse(result["full_game_prediction"])

    def test_incomplete_removal_partition_or_wrong_base_cannot_compile(self):
        probe = deepcopy(self.probe)
        probe["removed_instance_ids"].pop()
        with self.assertRaisesRegex(InputError, "exactly once"):
            compile_wall_mechanics_probe(self.base, self.catalog, probe)
        probe = deepcopy(self.probe)
        probe["blueprint_id"] = "another-base"
        with self.assertRaisesRegex(InputError, "exact blueprint"):
            compile_wall_mechanics_probe(self.base, self.catalog, probe)

    def test_geometry_override_and_complete_army_claim_are_rejected(self):
        probe = deepcopy(self.probe)
        probe["parameters_by_entity"]["wall"]["x"] = 0
        with self.assertRaisesRegex(InputError, "override blueprint"):
            compile_wall_mechanics_probe(self.base, self.catalog, probe)
        probe = deepcopy(self.probe)
        probe["troop_group_is_complete_army"] = True
        with self.assertRaisesRegex(InputError, "complete army"):
            compile_wall_mechanics_probe(self.base, self.catalog, probe)

    def test_unsupported_town_hall_cannot_be_inserted_as_passive_structure(self):
        probe = deepcopy(self.probe)
        probe["structure_instance_ids"].append("town-hall-0")
        probe["removed_instance_ids"].remove("town-hall-0")
        probe["destruction_flags"]["by_instance"]["town-hall-0"] = True
        probe["parameters_by_entity"]["town-hall"] = deepcopy(
            probe["parameters_by_entity"]["monolith"]
        )
        with self.assertRaisesRegex(InputError, "Town Hall requires"):
            compile_wall_mechanics_probe(self.base, self.catalog, probe)

    def test_simulation_result_stays_bound_to_geometry_and_nested_human_result(self):
        probe = deepcopy(self.probe)
        probe["scene_template"]["duration_seconds"] = 0.2
        result = simulate_wall_mechanics_probe(self.base, self.catalog, probe)
        sample = result["result"]["human_combat"]["samples"][0]
        self.assertIn("monolith-0", sample["combat"]["actors"])
        self.assertEqual(len(sample["combat"]["actors"]), 329)
        self.assertFalse(sample["combat"]["full_game_prediction"])

    def test_native_town_hall_retains_blueprint_geometry_and_its_own_lifecycle(self):
        probe = deepcopy(self.probe)
        probe["structure_instance_ids"].append("town-hall-0")
        probe["removed_instance_ids"].remove("town-hall-0")
        probe["destruction_flags"]["by_instance"]["town-hall-0"] = True
        parameters = deepcopy(probe["parameters_by_entity"]["monolith"])
        parameters["statistics_mode"] = "weapon"
        parameters["attack_parameters"]["allocation"] = "distinct_targets_only"
        parameters["town_hall_parameters"] = lifecycle()
        probe["parameters_by_entity"]["town-hall"] = parameters
        probe["scene_template"].update(
            scope=TOWN_HALL_SCOPE,
            model_rules=deepcopy(TOWN_HALL_RULES),
            persistent_hazards=[],
            healing_spells=[],
            healing_stacking={"source": "explicit-test-no-healing", "groups": {}},
            duration_seconds=0.2,
            target_scoring={
                "selection": "legacy_route_or_footprint_distance",
                "source": "explicit-test-policy",
            },
        )
        result = simulate_wall_mechanics_probe(self.base, self.catalog, probe)
        actor = result["result"]["human_combat"]["samples"][0]["combat"]["actors"][
            "town-hall-0"
        ]
        building = next(
            item for item in self.base["buildings"] if item["instance"] == "town-hall-0"
        )
        self.assertEqual((actor["x"], actor["y"]), (building["x"], building["y"]))
        self.assertEqual(actor["entity_adapter"]["level"], 16)
        self.assertIn("town_hall_model", actor)
        self.assertEqual(len(result["removed_blueprint_instances"]), 140)


if __name__ == "__main__":
    unittest.main()
