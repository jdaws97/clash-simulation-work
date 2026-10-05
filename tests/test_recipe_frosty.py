"""Conditional Frosty integration: summons, caps, slow clocks and failure bounds."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.hero_pets import PetCombat, compile_pet, validate_pet_deployment
from clashlab.recipe_frosty import compile_frostmite_reserves
from clashlab.spatial import _load_actors, _select_target, simulate_spatial

from test_adapters import entity_instance
from test_hero_pets import owner, pet_instance, target
from test_hero_roster_integration import roster_sector
from test_heroes import hero
from test_spatial import synthetic_scene


ROOT = Path(__file__).resolve().parents[1]


class FrostyRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def runtime(self, **changes):
        instance = pet_instance("frosty")
        instance["parameters"]["behavior"].update(changes)
        queen = owner()
        pet = compile_pet(instance, self.catalog, 8, {"hero": queen})
        scene = synthetic_scene(
            [queen, pet, target(), *compile_frostmite_reserves(pet)],
            width=24,
            height=16,
        )
        actors = _load_actors(scene, 24, 16)
        return actors, PetCombat(actors, 24, 16, _select_target)

    def test_capped_partial_batches_are_generated_once_and_survive_source_death(self):
        actors, pets = self.runtime(frostmite_lifetime_seconds=100, reserve_count=12)
        trace = []
        for time in (0, 8, 16, 24, 32, 40):
            pets.prepare(actors, time, trace)
        runtime = pets.frosty
        self.assertEqual(len(runtime.used), 10)
        self.assertEqual(trace[-1]["children"], [])
        actors["pet-frostmite-0"]["hp"] = 0
        pets.prepare(actors, 48, trace)
        self.assertEqual(len(runtime.used), 11)
        self.assertEqual(trace[-1]["children"], ["pet-frostmite-10"])
        actors["pet"]["hp"] = 0
        actors["hero"]["hp"] = 0
        pets.prepare(actors, 56, trace)
        self.assertEqual(len(runtime.used), 11)
        self.assertGreater(actors["pet-frostmite-10"]["hp"], 0)
        pets.prepare(actors, 148, trace)
        self.assertEqual(actors["pet-frostmite-10"]["hp"], 0)
        self.assertEqual(actors["pet-frostmite-10"]["death_time"], 148)
        with self.assertRaisesRegex(InputError, "parent's summon clock"):
            validate_pet_deployment(
                {"kind": "deploy", "targets": ["pet-frostmite-11"]}, actors
            )

    def test_freeze_recall_and_exhaustion_do_not_replay_or_partially_spawn(self):
        actors, pets = self.runtime(reserve_count=3, frostmite_lifetime_seconds=100)
        trace = []
        pets.prepare(actors, 0, trace)
        actors["pet"]["frozen_until"] = 10
        pets.prepare(actors, 8, trace)
        self.assertEqual(len(pets.frosty.used), 2)
        actors["pet"]["_recalled"] = True
        pets.prepare(actors, 16, trace)
        actors["pet"]["_recalled"] = False
        pets.prepare(actors, 19, trace)
        self.assertEqual(len(pets.frosty.used), 2)
        with self.assertRaisesRegex(InputError, "reserve exhausted"):
            pets.prepare(actors, 24, trace)
        self.assertEqual(len(pets.frosty.used), 2)
        self.assertEqual(actors["pet-frostmite-2"]["spawn_seconds"], "controlled")

    def test_full_solver_summon_and_slow_events_agree_at_two_steps(self):
        queen = hero("archer-queen", bare=True, id="hero", x=2.5, y=5.5)
        queen["hero_parameters"][
            "pet_policy"
        ] = "paired_pet_from_explicit_scene_assignment"
        queen["first_attack_seconds"] = 100
        cannon = entity_instance("cannon", "cannon", 21, "defense", x=7, y=4)
        cannon["first_attack_seconds"] = 100
        instance = pet_instance("frosty")
        instance["parameters"]["behavior"]["frostmite_lifetime_seconds"] = 6
        results = []
        for step in (0.031, 0.8):
            scene = compile_entity_scene(
                roster_sector(
                    self.catalog,
                    [deepcopy(queen), deepcopy(cannon)],
                    pets=[deepcopy(instance)],
                    duration_seconds=10,
                    maximum_step_seconds=step,
                ),
                self.catalog,
            )["scene"]
            result = simulate_spatial(scene)
            batches = [
                event
                for event in result["trace"]
                if event.get("event") == "frosty_summon_batch"
            ]
            self.assertEqual(len(batches), 2)
            for event, expected_time in zip(batches, (0, 8)):
                self.assertAlmostEqual(event["time_seconds"], expected_time, delta=1e-8)
            self.assertEqual([len(event["children"]) for event in batches], [2, 2])
            slows = [
                event
                for event in result["trace"]
                if event.get("event") == "hit_status_apply"
                and event.get("target") == "cannon"
            ]
            self.assertTrue(slows)
            self.assertTrue(
                any(event["source"] == "pet-frostmite-0" for event in slows)
            )
            self.assertTrue(any(event["source"] == "pet" for event in slows))
            self.assertAlmostEqual(
                result["actors"]["pet-frostmite-0"]["death_time"], 6, delta=1e-8
            )
            results.append(result)
        self.assertAlmostEqual(
            results[0]["actors"]["cannon"]["hp"],
            results[1]["actors"]["cannon"]["hp"],
            delta=1e-7,
        )
        self.assertEqual(
            results[0]["hero_pets"]["frosty"]["summoned_ids"],
            results[1]["hero_pets"]["frosty"]["summoned_ids"],
        )


if __name__ == "__main__":
    unittest.main()
