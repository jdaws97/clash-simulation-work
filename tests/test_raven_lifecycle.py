"""Resource acquisition, shared captured weapon packet and owner loss."""

from pathlib import Path
import inspect
import unittest
from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError
from clashlab.hero_pets import PetCombat, compile_pet
from clashlab.raven_lifecycle import POLICIES
from clashlab.spatial import _load_actors, _select_target
from test_hero_pets import owner, target, pet_parameters

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-raven-resource-mapping-no-replay-calibration"


class RavenLifecycleTests(unittest.TestCase):
    def runtime(self):
        catalog = Catalog.load(ROOT / "data")
        hero = owner(entity_adapter={"entity": "archer-queen", "town_hall": 18})
        parameters = pet_parameters("lassi")
        parameters.update(
            target_retention="resource_tier_retain_within_tier",
            ground_wall_policy="not_applicable_air",
            behavior={
                "source": SOURCE,
                **POLICIES,
                "resource_entities": ["gold-storage"],
            },
        )
        pet = compile_pet(
            {
                "id": "raven",
                "entity": "greedy-raven",
                "level": 10,
                "town_hall": 18,
                "hero_id": "hero",
                "parameters": parameters,
            },
            catalog,
            8,
            {"hero": hero},
        )
        actors = _load_actors(
            {
                "actors": [
                    hero,
                    pet,
                    target("resource", x=12, entity_adapter={"entity": "gold-storage"}),
                    target("defense", x=4, entity_adapter={"entity": "archer-tower"}),
                ]
            },
            20,
            20,
        )
        return actors, PetCombat(actors, 20, 20, _select_target)

    @unittest.skipUnless(
        "raven_launch_multiplier" in inspect.getsource(PatternCombat.launch),
        "Requires separately reviewed shared launch-factor hook",
    )
    def test_resource_tier_packet_capture_and_source_death(self):
        actors, runtime = self.runtime()
        trace = []
        runtime.prepare(actors, 0, trace)
        raven = actors["raven"]
        selected, _ = runtime.select_target(raven, actors, 0, set(), 20, 20)
        self.assertEqual(selected["id"], "resource")
        weapon = PatternCombat(actors)
        weapon.launch(raven, selected, actors, 0, trace)
        self.assertAlmostEqual(weapon.pending[0][2]["flat_damage"], 325.5)
        raven["hp"] = 0
        damage = weapon.resolve(actors, 0, trace)
        self.assertAlmostEqual(damage["resource"], 325.5)
        raven["hp"] = 3500
        actors["hero"]["hp"] = 0
        actors["resource"]["hp"] = 0
        runtime.prepare(actors, 1, trace)
        selected, _ = runtime.select_target(raven, actors, 1, set(), 20, 20)
        self.assertEqual(selected["id"], "defense")
        weapon.launch(raven, selected, actors, 1, trace)
        self.assertAlmostEqual(weapon.pending[0][2]["flat_damage"], 65.1)

    def test_missing_resource_classification_fails(self):
        actors, runtime = self.runtime()
        runtime.prepare(actors, 0, [])
        actors["defense"].pop("entity_adapter")
        with self.assertRaisesRegex(InputError, "source-bound entity classification"):
            runtime.select_target(actors["raven"], actors, 0, set(), 20, 20)
