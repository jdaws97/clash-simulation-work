"""Conditional equipment across shared activation, live impacts and summons."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError, read_json
from clashlab.hero_roster import HeroRosterCombat
from clashlab.heroes import HeroCombat
from clashlab.recipe_equipment import RecipeEquipmentCombat
from clashlab.spatial import _load_actors, _select_target, simulate_spatial

from test_adapters import entity_instance
from test_barbarian_king import king_equipment
from test_hero_roster_integration import extended_hero, roster_sector
from test_heroes import ability, equipment, hero
from test_indirect_defenses import damage_command
from test_valkyrie_integration import building


ROOT = Path(__file__).resolve().parents[1]
POLICY = read_json(ROOT / "data/battle-policies/recipe-equipment.json")["parameters"]


def recipe_item(entity, level):
    return {"entity": entity, "level": level, "parameters": deepcopy(POLICY[entity])}


def equipped_hero(entity, items, **changes):
    result = (
        extended_hero(entity) if entity == "barbarian-king" else hero(entity, bare=True)
    )
    result["hero_parameters"].update(
        equipment=items, loadout_policy="exact_two_equipment"
    )
    result.update(changes)
    return result


class RecipeEquipmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def compile(self, entities, **changes):
        return compile_entity_scene(
            roster_sector(self.catalog, entities, **changes), self.catalog
        )["scene"]

    def test_recalled_passive_clocks_skip_elapsed_pulses_without_heal_or_charge_reset(
        self,
    ):
        royal = hero()
        queen = equipped_hero(
            "archer-queen",
            [recipe_item("action-figure", 27), equipment("magic-mirror", 20)],
        )
        king = equipped_hero(
            "barbarian-king",
            [king_equipment("giant-gauntlet", 27), king_equipment("spiky-ball", 27)],
        )
        scene = self.compile([royal, queen, king])
        actors = _load_actors(scene, scene["width"], scene["height"])
        combat = PatternCombat(actors)
        common = HeroCombat(actors, combat, allow_hero_extensions=True)
        common.extensions = HeroRosterCombat(
            actors, combat, None, _select_target, scene["width"], scene["height"]
        )
        trace = []
        hero_ids = ("royal", "queen", "hero")
        common.expand_commands(
            [ability(key, command_id=f"activate-{key}") for key in hero_ids],
            actors,
            0,
            trace,
        )
        common.prepare(actors, 0, trace)
        for key in hero_ids:
            actors[key]["hp"] = actors[key]["maximum_hp"] / 2
            actors[key]["_recalled"] = True
        self.assertEqual(common.resolve_passives(actors, 4.2, trace), ({}, {}))
        self.assertEqual(common.extensions.resolve(actors, 4.2, trace, None), ({}, {}))
        clocks = [
            *common.passive_next["royal"].values(),
            common.extensions.king.heal_next["hero"],
            common.extensions.recipe.heal_next["queen"],
        ]
        self.assertTrue(all(clock > 4.2 for clock in clocks))
        for key in hero_ids:
            actors[key]["_recalled"] = False
        self.assertEqual(common.resolve_passives(actors, 4.21, trace), ({}, {}))
        self.assertEqual(common.extensions.resolve(actors, 4.21, trace, None), ({}, {}))
        self.assertEqual(common.used, set(hero_ids))
        self.assertTrue(
            all(actors[key]["hp"] == actors[key]["maximum_hp"] / 2 for key in hero_ids)
        )

    def test_arrow_shared_charge_pierces_once_and_survives_queen_at_two_steps(self):
        queen = equipped_hero(
            "archer-queen",
            [recipe_item("giant-arrow", 18), equipment("invisibility-vial", 7)],
            x=1.5,
            y=5.5,
        )
        results = []
        for step in (0.017, 0.8):
            scene = self.compile(
                [queen, building("first", 5), building("second", 11)],
                duration_seconds=2,
                maximum_step_seconds=step,
                effects=[
                    ability("queen"),
                    ability("queen", 0.01, "duplicate"),
                    damage_command("queen", 0.02, 1e6),
                ],
            )
            result = simulate_spatial(scene)
            contacts = [
                event
                for event in result["trace"]
                if event.get("event") == "giant_arrow_contact"
            ]
            self.assertEqual([item["target"] for item in contacts], ["first", "second"])
            self.assertTrue(all(item["damage"] == 2000 for item in contacts))
            self.assertTrue(all(item["time_seconds"] > 0.02 for item in contacts))
            self.assertEqual(
                len(
                    [
                        item
                        for item in result["trace"]
                        if item.get("event") == "giant_arrow_released"
                    ]
                ),
                1,
            )
            results.append(contacts)
        for first, second in zip(*results):
            self.assertAlmostEqual(
                first["time_seconds"], second["time_seconds"], delta=1e-8
            )

    def test_fireball_and_tome_activate_together_and_use_captured_impact_position(self):
        warden = equipped_hero(
            "grand-warden",
            [recipe_item("fireball", 27), equipment("eternal-tome", 18)],
            x=1.5,
            y=5.5,
        )
        defense = entity_instance("defense", "cannon", 21, "defense", x=6, y=4)
        scene = self.compile([warden, defense, building("nearby", 10)])
        actors = _load_actors(scene, scene["width"], scene["height"])
        combat = PatternCombat(actors)
        common = HeroCombat(actors, combat, allow_hero_extensions=True)
        common.extensions = HeroRosterCombat(
            actors, combat, None, _select_target, scene["width"], scene["height"]
        )
        trace = []
        commands = common.expand_commands([ability("warden")], actors, 0, trace)
        self.assertEqual(
            len(
                [
                    command
                    for command in commands
                    if command["kind"] == "invulnerability"
                ]
            ),
            1,
        )
        runtime = common.extensions.recipe
        arrival = runtime.packets[0][0]
        actors["warden"]["hp"] = 0
        actors["defense"]["hp"] = 0
        damage, _ = runtime.resolve(actors, arrival, trace)
        self.assertEqual(damage["nearby"], 4100)
        self.assertNotIn("defense", damage)
        self.assertFalse(runtime.packets)
        self.assertFalse(runtime.continuation_reasons())

    def test_action_figure_generated_lifetime_classes_regeneration_and_latched_rage(
        self,
    ):
        queen = equipped_hero(
            "archer-queen",
            [recipe_item("action-figure", 27), equipment("magic-mirror", 20)],
            x=1.5,
            y=5.5,
        )
        scene = self.compile([queen, building("target", 10)], duration_seconds=0.1)
        actors = _load_actors(scene, scene["width"], scene["height"])
        giant_id = "queen-action-figure-giant"
        giant = actors[giant_id]
        self.assertNotIn("entity_adapter", giant)
        self.assertEqual(giant["spawn_seconds"], "controlled")
        self.assertEqual(giant["hitpoints"], 18500)
        self.assertEqual(giant["housing_space"], 50)
        self.assertEqual(giant["buff_class"], "troop")
        combat = PatternCombat(actors)
        common = HeroCombat(actors, combat, allow_hero_extensions=True)
        common.extensions = HeroRosterCombat(
            actors, combat, None, _select_target, scene["width"], scene["height"]
        )
        trace = []
        expanded = common.expand_commands([ability("queen")], actors, 0, trace)
        deployments = [command for command in expanded if command["kind"] == "deploy"]
        self.assertEqual(
            sorted(len(command["targets"]) for command in deployments), [1, 2]
        )
        self.assertNotIn(giant_id, common.clone_expiry)
        self.assertEqual(len(common.clone_expiry), 2)
        self.assertEqual(common.used, {"queen"})
        runtime = common.extensions.recipe
        _, healing = runtime.resolve(actors, 1, trace)
        self.assertEqual(healing["queen"], 40)
        giant["spawn_seconds"] = 0
        giant["hp"] = giant["maximum_hp"] / 2
        giant["next_attack"] = 4
        actors["queen"]["hp"] = 0
        runtime.prepare(actors, 2, trace)
        self.assertEqual(giant["damage"], 2100)
        self.assertAlmostEqual(giant["next_attack"], 2 + 2 / 1.5)
        giant["hp"] = giant["maximum_hp"]
        runtime.prepare(actors, 3, trace)
        self.assertEqual(giant["damage"], 2100)
        self.assertEqual(
            len(
                [event for event in trace if event.get("event") == "action_figure_rage"]
            ),
            1,
        )
        bad = deepcopy(queen)
        bad["hero_parameters"]["equipment"][0]["parameters"]["summon_statistics"][
            "level"
        ] = 9
        with self.assertRaisesRegex(InputError, "levels disagree"):
            self.compile([bad])

    def test_earthquake_uses_maximum_hp_ground_membership_and_shared_protection(self):
        king = equipped_hero(
            "barbarian-king",
            [recipe_item("earthquake-boots", 18), king_equipment("spiky-ball", 27)],
            x=1.5,
            y=5.5,
        )
        scene = self.compile([king, building("target", 5)])
        actors = _load_actors(scene, scene["width"], scene["height"])
        runtime = RecipeEquipmentCombat(actors)
        target = actors["target"]
        target["hp"] = target["maximum_hp"] / 2
        wall = deepcopy(target)
        wall.update(id="wall", kind="wall", maximum_hp=100, hp=10)
        air = deepcopy(target)
        air.update(id="air", kind="unit", layer="air")
        protected = deepcopy(target)
        protected.update(id="protected", immune_until=100)
        actors.update(wall=wall, air=air, protected=protected)
        trace = []
        runtime.activate("hero", actors, 0, trace)
        damage, _ = runtime.resolve(actors, 0, trace)
        self.assertEqual(damage["target"], target["maximum_hp"] * 0.4)
        self.assertEqual(damage["wall"], 100)
        self.assertEqual(damage["protected"], 0)
        self.assertNotIn("air", damage)


if __name__ == "__main__":
    unittest.main()
