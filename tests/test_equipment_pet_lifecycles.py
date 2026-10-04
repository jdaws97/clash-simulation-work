"""Bounded synthetic integration contracts, never replay calibration."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError
from clashlab.equipment_lifecycles import POLICIES, compile_equipment
from clashlab.full_battle import compile_full_battle
from clashlab.hero_pets import PetCombat, compile_pet
from clashlab.heroes import HeroCombat
from clashlab.spatial import _apply_health, _load_actors
from clashlab.walls import WallRouting
from clashlab.yak_lifecycle import POLICIES as YAK_POLICIES
from clashlab.jelly_lifecycle import POLICIES as JELLY_POLICIES

from test_full_battle import add_hero, fixture
from test_hero_pets import owner, projectile, target, pet_parameters
from test_heroes import ability, hero, loaded_runtime


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-owner-equipment-lifecycle-not-game-calibration"


def gear(entity, level=18):
    return {
        "entity": entity,
        "level": level,
        "parameters": {"source": SOURCE, **POLICIES},
    }


class EquipmentPetLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_shared_charge_haste_expiry_and_pair_order(self):
        results = []
        for reverse in (False, True):
            instance = hero()
            items = [gear("haste-vial"), instance["hero_parameters"]["equipment"][0]]
            instance["hero_parameters"]["equipment"] = items[::-1] if reverse else items
            actors, combat, runtime = loaded_runtime(self.catalog, [instance])
            royal = actors["royal"]
            base_speed = royal["speed"]
            base_interval = royal["attack_interval_seconds"]
            trace = []
            runtime.prepare(actors, 0, trace)
            self.assertAlmostEqual(
                royal["attack_interval_seconds"], base_interval / 1.16
            )
            royal["next_attack"] = 2
            runtime.expand_commands([ability("royal")], actors, 0, trace)
            runtime.prepare(actors, 0, trace)
            self.assertAlmostEqual(royal["next_attack"], 1)
            self.assertAlmostEqual(
                royal["attack_interval_seconds"], base_interval / 2.32
            )
            self.assertGreater(royal["speed"], base_speed)
            self.assertEqual(runtime.next_boundary(0), 10)
            runtime.expand_commands([ability("royal", 1)], actors, 1, trace)
            self.assertEqual(trace[-1]["status"], "ability_already_used")
            runtime.prepare(actors, 10, trace)
            self.assertAlmostEqual(royal["speed"], base_speed)
            self.assertAlmostEqual(
                royal["attack_interval_seconds"], base_interval / 1.16
            )
            results.append((royal["damage"], runtime.rocket_remaining["royal"]))
        self.assertEqual(results[0], results[1])

    def test_rage_vampstache_receipts_death_and_revival(self):
        models = [
            compile_equipment(
                gear(entity),
                {"entity": "barbarian-king", "town_hall": 16},
                self.catalog,
                8,
            )[0]
            for entity in ("rage-vial", "vampstache")
        ]
        instance = hero(bare=True)
        actors, combat, runtime = loaded_runtime(self.catalog, [instance])
        actor = actors["royal"]
        actor["hero_model"].update(
            entity="barbarian-king",
            equipment=models,
            loadout_policy="exact_two_equipment",
        )
        actor["target_layers"] = ["ground"]
        runtime = HeroCombat(actors, combat, allow_hero_extensions=True)
        original = actor["damage"]
        actor["hp"] -= 500
        trace = []
        runtime.expand_commands([ability("royal")], actors, 0, trace)
        runtime.prepare(actors, 0, trace)
        self.assertAlmostEqual(actor["damage"], original * 2.55)
        runtime.weapon_launched("royal", 0, trace)
        damage, healing = runtime.resolve_passives(actors, 0, trace)
        self.assertEqual(healing["royal"], 300)
        _apply_health(actors, damage, healing, 0)
        self.assertEqual(actor["hp"], actor["hitpoints"] - 200)
        runtime.weapon_launched("royal", 1, trace)
        actor["hp"] = 0
        self.assertEqual(runtime.resolve_passives(actors, 1, trace)[1], {})
        actor["hp"] = 1
        runtime.expand_commands([ability("royal", 2)], actors, 2, trace)
        self.assertEqual(trace[-1]["status"], "ability_already_used")
        runtime.prepare(actors, 10, trace)
        self.assertEqual(actor["damage"], original)

    def test_full_battle_pet_inventory_bindings(self):
        from clashlab.pet_rules import RULES, SCOPE

        for entity in ("mighty-yak", "angry-jelly"):
            inputs = fixture(self.catalog)
            instance = add_hero(inputs[0], inputs[2], inputs[1])
            instance["hero_parameters"][
                "pet_policy"
            ] = "paired_pet_from_explicit_scene_assignment"
            parameters = pet_parameters("lassi")
            if entity == "mighty-yak":
                parameters.update(
                    target_retention="independent_wall_routing_experimental",
                    owner_death_policy="independent_combat_one_owner_defeat_rage",
                    ground_wall_policy="clear_obstructions",
                    behavior=deepcopy(YAK_POLICIES),
                )
                level = 15
            else:
                parameters.update(
                    target_retention="prefer_owner_primary_then_nearest",
                    owner_death_policy="separate_then_independent_no_reattachment",
                    ground_wall_policy="not_applicable_air",
                    behavior=deepcopy(JELLY_POLICIES),
                )
                level = 10
            scene = inputs[0]["entity_scene"]
            scene.update(
                scope=SCOPE,
                model_rules=deepcopy(RULES),
                buff_spells=[],
                pets=[
                    {
                        "id": "paired",
                        "entity": entity,
                        "level": level,
                        "town_hall": 16,
                        "hero_id": instance["id"],
                        "parameters": parameters,
                    }
                ],
            )
            inputs[1]["levels"][entity] = level
            inputs[2]["heroes"][0]["pet"] = {"id": entity, "level": level}
            self.assertIsInstance(compile_full_battle(*inputs, self.catalog), dict)

    def test_full_battle_compiler_accepts_exact_haste_loadout(self):
        inputs = fixture(self.catalog)
        instance = add_hero(inputs[0], inputs[2], inputs[1])
        instance["hero_parameters"]["equipment"][1] = gear("haste-vial")
        inputs[2]["heroes"][0]["equipment"][1] = {"id": "haste-vial", "level": 18}
        inputs[1]["levels"]["haste-vial"] = 18
        compiled = compile_full_battle(*inputs, self.catalog)
        self.assertIsInstance(compiled, dict)

    def test_yak_deployment_wall_weapon_owner_defeat_and_no_retrigger(self):
        hero_actor = owner()
        parameters = pet_parameters("lassi")
        parameters.update(
            target_retention="independent_wall_routing_experimental",
            owner_death_policy="independent_combat_one_owner_defeat_rage",
            ground_wall_policy="clear_obstructions",
            behavior=deepcopy(YAK_POLICIES),
        )
        pet = compile_pet(
            {
                "id": "yak",
                "entity": "mighty-yak",
                "level": 15,
                "town_hall": 16,
                "hero_id": "hero",
                "parameters": parameters,
            },
            self.catalog,
            8,
            {"hero": hero_actor},
        )
        actors = _load_actors({"actors": [hero_actor, pet, target()]}, 20, 20)
        walls = WallRouting(actors)
        runtime = PetCombat(actors, 20, 20, walls.select_target)
        trace = []
        runtime.prepare(actors, 0, trace)
        self.assertEqual(actors["yak"]["spawn_seconds"], 0)
        self.assertEqual(actors["yak"]["wall_behavior"]["weapon"]["damage"], 4872)
        base_damage = actors["yak"]["damage"]
        actors["hero"]["hp"] = 0
        runtime.prepare(actors, 1, trace)
        self.assertAlmostEqual(actors["yak"]["damage"], base_damage * 1.7)
        self.assertAlmostEqual(
            actors["yak"]["wall_behavior"]["weapon"]["damage"], 4872 * 1.7
        )
        actors["hero"]["hp"] = 1
        runtime.prepare(actors, 9, trace)
        self.assertEqual(actors["yak"]["damage"], base_damage)
        actors["hero"]["hp"] = 0
        runtime.prepare(actors, 10, trace)
        self.assertEqual(actors["yak"]["damage"], base_damage)
        self.assertEqual(
            sum(item["event"] == "yak_owner_defeat_rage" for item in trace), 1
        )
        self.assertIsNotNone(
            runtime.select_target(actors["yak"], actors, 10, set(), 20, 20)[0]
        )

    def test_jelly_attachment_recall_expiry_and_source_loss(self):
        for early_defeat in (False, True):
            hero_actor = owner()
            parameters = pet_parameters("lassi")
            parameters.update(
                target_retention="prefer_owner_primary_then_nearest",
                owner_death_policy="separate_then_independent_no_reattachment",
                ground_wall_policy="not_applicable_air",
                behavior=deepcopy(JELLY_POLICIES),
            )
            pet = compile_pet(
                {
                    "id": "jelly",
                    "entity": "angry-jelly",
                    "level": 10,
                    "town_hall": 16,
                    "hero_id": "hero",
                    "parameters": parameters,
                },
                self.catalog,
                8,
                {"hero": hero_actor},
            )
            actors = _load_actors({"actors": [hero_actor, pet, target()]}, 20, 20)
            walls = WallRouting(actors)
            runtime = PetCombat(actors, 20, 20, walls.select_target)
            original = deepcopy(actors["hero"]["_target_ranks"])
            trace = []
            runtime.prepare(actors, 0, trace)
            self.assertEqual(runtime.states["jelly"]["phase"], "attached")
            self.assertEqual(
                actors["hero"]["_target_ranks"], {"defense": 0, "building": 1}
            )
            self.assertEqual(actors["jelly"]["spawn_seconds"], "controlled")
            self.assertEqual(runtime.jelly.next_boundary(0), 35)
            self.assertEqual(len(runtime.continuation_reasons(0)), 1)
            actors["hero"]["frozen_until"] = 50
            if early_defeat:
                actors["hero"]["hp"] = 0
                release_time = 1
            else:
                actors["hero"]["_recalled"] = True
                runtime.prepare(actors, 35, trace)
                self.assertEqual(runtime.states["jelly"]["phase"], "attached")
                self.assertEqual(runtime.continuation_reasons(35), [])
                actors["hero"]["_recalled"] = False
                release_time = 36
            runtime.prepare(actors, release_time, trace)
            self.assertEqual(runtime.states["jelly"]["phase"], "active")
            self.assertEqual(actors["jelly"]["spawn_seconds"], release_time)
            self.assertEqual(actors["hero"]["_target_ranks"], original)
            actors["hero"]["hp"] = 1
            runtime.prepare(actors, release_time + 1, trace)
            self.assertEqual(
                sum(event["event"] == "jelly_separated" for event in trace), 1
            )

    def test_unknown_policy_fails_closed(self):
        item = gear("rage-vial")
        item["parameters"].pop("experimental_policy")
        with self.assertRaises(InputError):
            compile_equipment(
                item, {"entity": "barbarian-king", "town_hall": 16}, self.catalog, 8
            )

    def test_frozen_arrow_impact_source_loss_and_refresh(self):
        from clashlab.adapters import compile_entity_scene
        from clashlab.hit_status import HitStatusCombat
        from test_heroes import hero_sector

        queen = hero("archer-queen")
        queen["hero_parameters"]["equipment"][1] = gear("frozen-arrow", 27)
        compiled = compile_entity_scene(
            hero_sector(self.catalog, [queen]), self.catalog
        )
        queen_actor = compiled["scene"]["actors"][0]
        actors = _load_actors({"actors": [queen_actor, target()]}, 20, 20)
        runtime = HitStatusCombat(actors)
        actor = actors["queen"]
        victim = actors["tower"]
        victim["next_attack"] = 2
        packet = {"source": "queen", "on_hit_status": deepcopy(actor["on_hit_status"])}
        trace = []
        runtime.impact(packet, victim, actors, 0, trace)
        actor["hp"] = 0
        runtime.prepare(actors, 0, trace)
        self.assertAlmostEqual(victim["_hit_status_attack_rate"], 0.35)
        self.assertAlmostEqual(victim["next_attack"], 2 / 0.35)
        runtime.impact(packet, victim, actors, 1, trace)
        runtime.prepare(actors, 1, trace)
        self.assertEqual(len(runtime.exposures), 1)
        runtime.prepare(actors, 4, trace)
        self.assertEqual(victim["_hit_status_attack_rate"], 1)


if __name__ == "__main__":
    unittest.main()
