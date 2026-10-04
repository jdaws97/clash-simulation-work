"""Travelling Builder workers share combat phases without becoming actors."""

from copy import deepcopy
from math import hypot
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.builder_rules import RULES, SCOPE
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial

from test_adapters import entity_instance
from test_battle_modifiers import modifier_policy
from test_builder_huts import SOURCE, hut_instance
from test_buffs import buff_instance
from test_full_battle import fixture as battle_fixture
from test_heroes import ability, hero
from test_hit_status import ice_instance
from test_indirect_defenses import indirect_sector
from test_spring_traps import spring_instance


ROOT = Path(__file__).resolve().parents[1]
FIRST_REPAIR = (hypot(0.5, 0.5) + 3) / 2.5 + 0.75


def damage(actor_id, amount, time=0, effect_id="injure"):
    return {
        "id": effect_id,
        "kind": "damage",
        "time_seconds": time,
        "targets": [actor_id],
        "amount": amount,
    }


class BuilderIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.mode_rules = read_json(ROOT / "data" / "mode-rules.json")

    def fixture(self, step=0.5, **changes):
        cannon = entity_instance(
            "cannon", "cannon", 1, "defense", x=7, y=2, first_attack_seconds=100
        )
        archer = entity_instance(
            "archer",
            "archer",
            1,
            "attack",
            x=11.5,
            y=3.5,
            first_attack_seconds=100,
            wall_parameters={"kind": "avoid", "source": SOURCE},
        )
        archer["modifiers"]["range_multiplier"] = 100
        return indirect_sector(
            self.catalog,
            [hut_instance(first_attack_seconds=100), cannon, archer],
            scope=SCOPE,
            model_rules=deepcopy(RULES),
            duration_seconds=3,
            maximum_step_seconds=step,
            recording_interval_seconds=0.25,
            effects=[damage("cannon", 200)],
            **changes,
        )

    def run_scene(self, specification):
        return simulate_spatial(
            compile_entity_scene(specification, self.catalog)["scene"]
        )

    def test_moving_worker_repairs_in_the_same_health_phase_as_weapon_damage(self):
        outcomes = []
        for step in (0.017, 0.8):
            specification = self.fixture(step)
            archer = specification["entities"][-1]
            archer["first_attack_seconds"] = FIRST_REPAIR
            archer["modifiers"]["attack_interval_multiplier"] = 100
            compiled = compile_entity_scene(specification, self.catalog)
            by_id = {actor["id"]: actor for actor in compiled["scene"]["actors"]}
            result = simulate_spatial(compiled["scene"])
            repairs = [
                event
                for event in result["trace"]
                if event.get("event") == "builder_repair"
            ]
            self.assertEqual(len(repairs), 2)
            self.assertAlmostEqual(repairs[0]["time_seconds"], FIRST_REPAIR)
            expected = (
                by_id["cannon"]["hitpoints"]
                - 200
                - by_id["archer"]["damage"]
                + 2 * 63.75
            )
            self.assertAlmostEqual(result["actors"]["cannon"]["hp"], expected)
            self.assertNotIn("hut::builder", result["actors"])
            early = next(
                frame for frame in result["frames"] if frame["time_seconds"] == 1
            )
            builder = early["actors"]["hut"]["builder"]
            self.assertEqual(builder["phase"], "moving")
            self.assertGreater(builder["x"], 3)
            self.assertLess(builder["x"], 6.5)
            outcomes.append(
                (
                    result["actors"]["cannon"]["hp"],
                    [round(event["time_seconds"], 7) for event in repairs],
                )
            )
        self.assertEqual(outcomes[0], outcomes[1])

    def test_ice_golem_death_freezes_worker_at_its_roaming_position(self):
        specification = self.fixture()
        specification["duration_seconds"] = 10
        ice = ice_instance(x=6.5, y=3.5, first_attack_seconds=100)
        ice["modifiers"]["range_multiplier"] = 100
        ice["ice_parameters"]["death_radius_multiplier"] = 0.1
        ice["ice_parameters"]["death_duration_multiplier"] = 0.2
        specification["entities"].append(ice)
        specification["effects"].append(damage("ice", 100000, 2, "kill-ice"))
        compiled = compile_entity_scene(specification, self.catalog)
        duration = next(
            actor for actor in compiled["scene"]["actors"] if actor["id"] == "ice"
        )["death_model"]["effects"][0]["duration_seconds"]
        result = simulate_spatial(compiled["scene"])
        frozen = [
            event for event in result["trace"] if event.get("event") == "builder_freeze"
        ]
        self.assertEqual(len(frozen), 1)
        self.assertEqual(frozen[0]["worker"], "hut::builder")
        self.assertEqual(frozen[0]["time_seconds"], 2)
        first = next(
            event for event in result["trace"] if event.get("event") == "builder_repair"
        )
        self.assertAlmostEqual(first["time_seconds"], FIRST_REPAIR + duration)
        frame = next(frame for frame in result["frames"] if frame["time_seconds"] == 2)
        self.assertEqual(frame["actors"]["hut"]["frozen_until"], 0)
        self.assertEqual(
            frame["actors"]["hut"]["builder"]["frozen_until"], 2 + duration
        )

    def test_original_area_freeze_reaches_internal_worker_without_actor_membership(
        self,
    ):
        specification = self.fixture()
        specification["duration_seconds"] = 4
        specification["effects"].append(
            {
                "id": "freeze-worker",
                "kind": "area_freeze",
                "time_seconds": 2,
                "duration_seconds": 1,
                "area": {
                    "x": 6.5,
                    "y": 3.5,
                    "radius": 0.1,
                    "target_team": "defense",
                    "target_kinds": ["defense"],
                    "target_layers": ["ground"],
                },
            }
        )
        result = self.run_scene(specification)
        first = next(
            event for event in result["trace"] if event.get("event") == "builder_repair"
        )
        self.assertAlmostEqual(first["time_seconds"], FIRST_REPAIR + 1)
        self.assertEqual(result["actors"]["hut"]["frozen_until"], 0)

    def test_old_scope_cannot_silently_gain_builder_behavior(self):
        from clashlab.spell_tower_rules import RULES as OLD_RULES, SCOPE as OLD_SCOPE

        specification = self.fixture()
        specification.update(scope=OLD_SCOPE, model_rules=deepcopy(OLD_RULES))
        with self.assertRaisesRegex(InputError, "Builder"):
            compile_entity_scene(specification, self.catalog)

    def test_full_battle_profile_scales_turret_and_keeps_worker_out_of_bindings(self):
        inputs = battle_fixture(self.catalog, time_limit=0.2)
        specification, _, _, layout = inputs
        specification["battle_modifier_policy"] = modifier_policy()
        scene = specification["entity_scene"]
        scene.update(scope=SCOPE, model_rules=deepcopy(RULES), buff_spells=[])
        scene["entities"].append(hut_instance(first_attack_seconds=100))
        layout["inventory"]["builders-hut"] = 1
        layout["buildings"].append(
            {
                "instance": "hut",
                "id": "builders-hut",
                "level": 6,
                "x": 2,
                "y": 2,
                "mode": "normal",
                "counts_for_destruction": True,
            }
        )
        compiled = compile_full_battle(
            *inputs, self.catalog, mode_rules=self.mode_rules
        )
        actors = {
            actor["id"]: actor for actor in compiled["compiled"]["scene"]["actors"]
        }
        self.assertEqual(actors["hut"]["hitpoints"], 1900)
        self.assertAlmostEqual(actors["hut"]["damage"], 60 * 1.2)
        self.assertEqual(actors["hut"]["builder_hut_model"]["repair_amount"], 63.75)
        self.assertEqual(
            actors["hut"]["builder_hut_model"]["repair_interval_seconds"], 0.75
        )
        result = simulate_full_battle(*inputs, self.catalog, mode_rules=self.mode_rules)
        self.assertNotIn("hut::builder", result["combat"]["actors"])
        self.assertEqual(set(result["combat"]["builders"]["workers"]), {"hut"})
        self.assertEqual(result["battle_modifier_audit"]["profile_id"], "legend_i")

    def test_mirror_clones_inherit_buff_class_without_catalog_identity(self):
        specification = self.fixture()
        specification["duration_seconds"] = 0.25
        queen = hero("archer-queen", x=11.5, y=4.5, first_attack_seconds=100)
        mirror = next(
            equipment
            for equipment in queen["hero_parameters"]["equipment"]
            if equipment["entity"] == "magic-mirror"
        )
        mirror["parameters"]["first_attack_delay_seconds"] = 100
        specification["entities"].append(queen)
        specification["effects"].append(ability("queen"))
        specification["buff_spells"] = [buff_instance(time_seconds=0, x=11.5, y=4.5)]
        specification["traps"] = [spring_instance(x=20, y=10)]
        compiled = compile_entity_scene(specification, self.catalog)
        clones = [
            actor for actor in compiled["scene"]["actors"] if "summon_model" in actor
        ]
        self.assertEqual(len(clones), 2)
        for clone in clones:
            self.assertNotIn("entity_adapter", clone)
            self.assertEqual(clone["buff_class"], "hero")
            self.assertEqual(clone["spring_class"], "other")
        result = simulate_spatial(compiled["scene"])
        for clone in clones:
            actor = result["actors"][clone["id"]]
            self.assertEqual(actor["spawn_seconds"], 0)
            frame = result["frames"][-1]["actors"][clone["id"]]
            self.assertGreater(frame["buff_damage_multiplier"], 1)


if __name__ == "__main__":
    unittest.main()
