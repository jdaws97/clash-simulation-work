"""Synthetic lifecycle, targeting and damage invariants; no replay calibration."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.deaths import DeathCombat
from clashlab.recipe_troops import (
    RECIPE_ADAPTERS,
    RECIPE_TROOPS,
    RecipeTroopCombat,
    compile_recipe_troop,
    recipe_damage_multiplier,
    recipe_status_eligible,
    recipe_target_eligible,
)

from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-recipe-troop-contract-not-observed-gameplay"


def runtime_actor(actor):
    actor.update(
        hp=actor["hitpoints"],
        maximum_hp=actor["hitpoints"],
        death_time=None,
        target=None,
        next_attack=actor["first_attack_seconds"],
        frozen_until=0,
        immune_until=0,
    )
    return actor


class RecipeTroopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.policies = json.loads(
            (ROOT / "data/battle-policies/recipe-troops.json").read_text()
        )["parameters"]

    def inputs(self, entity_id):
        entity = self.catalog.entity(entity_id)
        row = entity["levels"][0]
        movement, kind = RECIPE_ADAPTERS[entity_id]
        pattern = {
            "kind": kind,
            "source": SOURCE,
            "target_kinds": ["defense", "building"],
            "target_layers": ["ground"],
            "maximum_hp_fraction": 0,
            "projectile": {
                "timing": "instant",
                "delay_seconds": 0,
                "destination": "locked_actor_center_at_impact",
                "hit_radius": 0,
            },
        }
        if kind == "radial":
            pattern["radius"] = 1.2
        actor = synthetic_unit(
            entity_id,
            source=self.catalog.records[entity_id]["source"],
            layer=movement,
            movement=movement,
            hitpoints=row["hitpoints"],
            damage=row["stats"]["normal"]["damagePerShot"],
            speed=entity["movementSpeed"] / 8,
            range=entity["range"],
            attack_interval_seconds=entity["attackSpeed"],
            minimum_range=0,
            attack_model=pattern,
            entity_adapter={"entity": entity_id},
            target_priorities=["defense", "building"],
            target_priority_tiers=[["defense", "building"]],
            buff_class="troop",
        )
        instance = {
            "entity": entity_id,
            "statistics_mode": "normal",
            "recipe_parameters": deepcopy(self.policies[entity_id]),
        }
        if movement == "ground":
            instance["wall_parameters"] = {
                "kind": "jump_enemy_walls" if entity_id == "headhunter" else "avoid",
                "source": SOURCE,
            }
        return actor, instance, entity, row

    def troop(self, entity_id):
        actor, instance, entity, row = self.inputs(entity_id)
        compile_recipe_troop(actor, instance, entity, row, {"damage_multiplier": 1})
        if entity_id == "headhunter":
            actor["target_priorities"].append("unit")
        return runtime_actor(actor)

    def test_complete_contract_required_and_statistics_resource_identity_preserved(
        self,
    ):
        for entity_id in sorted(RECIPE_TROOPS):
            with self.subTest(entity=entity_id):
                actor, instance, entity, row = self.inputs(entity_id)
                original = {
                    key: actor[key]
                    for key in (
                        "damage",
                        "speed",
                        "range",
                        "attack_interval_seconds",
                        "hitpoints",
                    )
                }
                compile_recipe_troop(
                    actor, instance, entity, row, {"damage_multiplier": 1}
                )
                self.assertEqual({key: actor[key] for key in original}, original)
                self.assertEqual(actor["housing_space"], entity["housingSpace"])
                self.assertEqual(
                    actor["recipe_troop_model"]["source"],
                    self.catalog.records[entity_id]["source"],
                )
                for key in list(instance["recipe_parameters"]):
                    broken = deepcopy(instance)
                    del broken["recipe_parameters"][key]
                    with self.assertRaises(InputError):
                        compile_recipe_troop(
                            deepcopy(actor),
                            broken,
                            entity,
                            row,
                            {"damage_multiplier": 1},
                        )
        actor, instance, entity, row = self.inputs("balloon")
        instance["entity"] = "unimplemented-troop"
        with self.assertRaises(InputError):
            compile_recipe_troop(actor, instance, entity, row, {"damage_multiplier": 1})

    def test_deployment_clocks_freeze_and_sampled_lifecycle_preserve_attack_work(self):
        rocket = self.troop("rocket-balloon")
        rocket.update(spawn_seconds="controlled")
        runtime = RecipeTroopCombat({rocket["id"]: rocket})
        runtime.prepare(0, [])
        self.assertEqual(rocket["_recipe_movement_multiplier"], 1)
        rocket.update(spawn_seconds=3, frozen_until=10)
        runtime.prepare(3, [])
        self.assertEqual(rocket["_recipe_movement_multiplier"], 4)
        self.assertEqual(runtime.next_boundary(3), 7)
        runtime.prepare(7, [])
        self.assertEqual(rocket["_recipe_movement_multiplier"], 1)

        baby = self.troop("baby-dragon")
        baby.update(next_attack=4, frozen_until=2)
        ally = runtime_actor(
            synthetic_unit(
                "air-ally",
                layer="air",
                movement="air",
                x=0.5,
                buff_class="troop",
                spawn_seconds="controlled",
            )
        )
        runtime = RecipeTroopCombat({baby["id"]: baby, ally["id"]: ally})
        trace = []
        runtime.prepare(0, trace)
        self.assertAlmostEqual(baby["next_attack"], 2 + 2 / 1.5)
        self.assertEqual(baby["_recipe_damage_multiplier"], 2)
        expected_clock = baby["next_attack"]
        runtime.prepare(0, trace)
        self.assertEqual(baby["next_attack"], expected_clock)
        ally["spawn_seconds"] = 0.05
        runtime.prepare(0.05, trace)
        self.assertEqual(baby["_recipe_damage_multiplier"], 2)
        runtime.prepare(0.1, trace)
        self.assertAlmostEqual(baby["next_attack"], 4)
        self.assertEqual(baby["_recipe_damage_multiplier"], 1)
        ally.update(hp=0, death_time=0.11)
        runtime.prepare(0.15, trace)
        self.assertEqual(baby["_recipe_damage_multiplier"], 1)
        runtime.prepare(0.2, trace)
        self.assertEqual(baby["_recipe_damage_multiplier"], 2)
        with self.assertRaisesRegex(InputError, "sample boundary was skipped"):
            runtime.prepare(0.4, trace)

    def test_balloon_and_wall_breaker_death_release_exactly_once(self):
        for entity_id in ("balloon", "super-wall-breaker"):
            with self.subTest(entity=entity_id):
                troop = self.troop(entity_id)
                wall = runtime_actor(
                    synthetic_structure("wall", x=1, y=3, kind="wall", hitpoints=20000)
                )
                building = runtime_actor(
                    synthetic_structure(
                        "building", x=0, y=4, kind="building", hitpoints=20000
                    )
                )
                actors = {actor["id"]: actor for actor in (troop, wall, building)}
                runtime = RecipeTroopCombat(actors)
                deaths = DeathCombat(actors)
                trace = []
                if entity_id == "super-wall-breaker":
                    runtime.launched(entity_id, 0, trace)
                    with self.assertRaisesRegex(InputError, "second attack"):
                        runtime.launched(entity_id, 0, trace)
                    self.assertEqual(recipe_damage_multiplier(troop, wall), 40)
                    self.assertEqual(recipe_damage_multiplier(troop, building), 1)
                else:
                    troop.update(hp=0, death_time=0)
                deaths.settle(actors, 0, trace)
                snapshots = {key: actor["hp"] for key, actor in actors.items()}
                deaths.settle(actors, 0, trace)
                self.assertEqual(
                    snapshots, {key: actor["hp"] for key, actor in actors.items()}
                )
                death_damage = self.catalog.entity(entity_id)["levels"][0]["stats"][
                    "normal"
                ]["deathDamage"]
                self.assertEqual(building["hp"], 20000 - death_damage)
                self.assertEqual(
                    wall["hp"],
                    20000
                    - (death_damage * 40 if entity_id == "super-wall-breaker" else 0),
                )
                self.assertEqual(deaths.result()["emitted_instances"], [entity_id])

    def test_headhunter_priority_poison_refresh_and_source_death(self):
        hunter = self.troop("headhunter")
        hero = runtime_actor(
            synthetic_unit(
                "hero", team="defense", hero_model={"entity": "archer-queen"}
            )
        )
        ordinary = runtime_actor(synthetic_unit("ordinary", team="defense"))
        structure = runtime_actor(synthetic_structure())
        actors = {actor["id"]: actor for actor in (hunter, hero, ordinary, structure)}
        runtime = RecipeTroopCombat(actors)
        trace = []
        runtime.prepare(0, trace)
        self.assertTrue(recipe_target_eligible(hunter, hero))
        self.assertFalse(recipe_target_eligible(hunter, ordinary))
        self.assertEqual(recipe_damage_multiplier(hunter, hero), 4)
        self.assertEqual(recipe_damage_multiplier(hunter, ordinary), 1)
        self.assertFalse(recipe_status_eligible(hunter, structure))
        self.assertTrue(recipe_status_eligible(hunter, hero))
        packet = {"source": hunter["id"]}
        runtime.impact(packet, structure, actors, 0, trace)
        self.assertEqual(runtime.poison, {})
        runtime.impact(packet, hero, actors, 0, trace)
        self.assertAlmostEqual(runtime.resolve(0.25, trace)[hero["id"]], 13.75)
        runtime.impact(packet, hero, actors, 0.4, trace)
        self.assertAlmostEqual(runtime.resolve(0.5, trace)[hero["id"]], 27.5)
        hunter.update(hp=0, death_time=0.5)
        self.assertTrue(runtime.continuation_reasons(0.5))
        hero["immune_until"] = 0.9
        self.assertEqual(runtime.resolve(0.75, trace)[hero["id"]], 0)
        self.assertAlmostEqual(runtime.resolve(1, trace)[hero["id"]], 55)
        self.assertAlmostEqual(runtime.resolve(1.25, trace)[hero["id"]], 55)
        self.assertAlmostEqual(runtime.resolve(1.4, trace)[hero["id"]], 33)
        self.assertFalse(runtime.continuation_reasons(1.4))
        self.assertEqual(runtime.poison, {})
        hunter.update(hp=1, death_time=None)
        hero.update(hp=0, death_time=1.4)
        runtime.prepare(1.4, trace)
        self.assertTrue(recipe_target_eligible(hunter, ordinary))

    def test_apprentice_following_and_hp_aura_have_no_healing_cycle_or_resurrection(
        self,
    ):
        apprentice = self.troop("apprentice-warden")
        ally = runtime_actor(
            synthetic_unit("ally", x=6, y=3.5, housing_space=20, buff_class="troop")
        )
        target = runtime_actor(synthetic_structure("target", x=4, y=3))
        actors = {actor["id"]: actor for actor in (apprentice, ally, target)}
        runtime = RecipeTroopCombat(actors)
        runtime.base_selector = lambda *args: (None, None)
        trace = []
        runtime.prepare(0, trace)
        self.assertEqual(ally["maximum_hp"], 120)
        self.assertEqual(ally["hp"], 120)
        self.assertEqual(apprentice["maximum_hp"], apprentice["hitpoints"])
        enemy, route = runtime.select_target(apprentice, actors, 0, {(4, 3)}, 20, 10)
        self.assertIsNone(enemy)
        self.assertTrue(route)
        ally["target"] = target["id"]
        enemy, route = runtime.select_target(apprentice, actors, 0, {(4, 3)}, 20, 10)
        self.assertIs(enemy, target)
        self.assertEqual(route, [])
        ally["hp"] = 60
        ally["x"] = 15
        runtime.prepare(0.1, trace)
        self.assertEqual(ally["hp"], 50)
        self.assertEqual(ally["maximum_hp"], 100)
        ally["x"] = 6
        runtime.prepare(0.2, trace)
        self.assertEqual(ally["hp"], 60)
        self.assertEqual(ally["maximum_hp"], 120)
        apprentice.update(hp=0, death_time=0.21)
        runtime.prepare(0.21, trace)
        self.assertEqual(ally["hp"], 50)
        self.assertEqual(ally["maximum_hp"], 100)
        ally.update(hp=0, death_time=0.22)
        apprentice.update(hp=10, death_time=None)
        runtime.prepare(0.22, trace)
        self.assertEqual(ally["hp"], 0)
        self.assertEqual(ally["maximum_hp"], 100)


if __name__ == "__main__":
    unittest.main()
