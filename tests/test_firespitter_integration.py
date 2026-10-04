"""Firespitter shot streams through the shared scheduler and full-battle binding."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import (
    ADAPTER_VERSION,
    compile_entity_scene,
    partial_adapter_status,
)
from clashlab.catalog import Catalog
from clashlab.closed_loop import simulate_closed_loop
from clashlab.combat import PatternCombat
from clashlab.common import InputError, read_json
from clashlab.firespitter_rules import RULES, RULESET, SCOPE
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.garrison_rules import (
    RULES as OLD_RULES,
    RULESET as OLD_RULESET,
    SCOPE as OLD_SCOPE,
)
from clashlab.spatial import _load_actors, simulate_spatial

from test_adapters import entity_instance
from test_artillery import artillery_hall
from test_battle_modifiers import modifier_policy
from test_closed_loop import area_plan_and_profile
from test_firespitters import SOURCE, firespitter_instance
from test_full_battle import fixture
from test_indirect_defenses import damage_command, fixed_tank, indirect_sector
from test_spell_towers import spell_tower_instance


ROOT = Path(__file__).resolve().parents[1]


def firespitter_sector(catalog, entities, **changes):
    return indirect_sector(
        catalog, entities, scope=SCOPE, model_rules=deepcopy(RULES), **changes
    )


def events(result, kind, source="firespitter"):
    return [
        event
        for event in result["trace"]
        if event.get("event") == kind and event.get("source") == source
    ]


def full_fixture(catalog):
    inputs = fixture(catalog, town_hall=17, time_limit=0.8)
    specification, _, _, layout = inputs
    scene = specification["entity_scene"]
    scene.update(scope=SCOPE, model_rules=deepcopy(RULES), buff_spells=[])
    scene["entities"][0] = artillery_hall(x=10, y=4, first_attack_seconds=100)
    layout["buildings"][0]["mode"] = "infernoArtillery"
    tower = firespitter_instance(x=2, y=8)
    scene["entities"].append(tower)
    layout["inventory"]["firespitter"] = 1
    layout["buildings"].append(
        {
            "instance": "firespitter",
            "id": "firespitter",
            "level": 2,
            "x": 2,
            "y": 8,
            "mode": "normal",
            "counts_for_destruction": True,
            "settings": {"facing_degrees": 0},
        }
    )
    layout["design_configuration"] = {
        "direction_convention": "clockwise_from_positive_x_in_screen_coordinates"
    }
    return inputs


class FirespitterIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.mode_rules = read_json(ROOT / "data" / "mode-rules.json")

    def compile(self, entities, **changes):
        return compile_entity_scene(
            firespitter_sector(self.catalog, entities, **changes), self.catalog
        )

    def run_scene(self, entities, **changes):
        return simulate_spatial(self.compile(entities, **changes)["scene"])

    def tank(self, actor_id="tank"):
        return fixed_tank(actor_id, x=10.5, y=5.5, town_hall=17)

    def test_registered_component_requires_v21_and_cannot_fall_back_to_generic_shot(
        self,
    ):
        entities = [firespitter_instance(), self.tank()]
        compiled = self.compile(entities)
        self.assertEqual(compiled["scene"]["ruleset"], RULESET)
        self.assertEqual(compiled["adapter_version"], ADAPTER_VERSION)
        self.assertTrue(
            partial_adapter_status(self.catalog.entity("firespitter"))["available"]
        )
        specification = firespitter_sector(self.catalog, entities)
        specification.update(scope=OLD_SCOPE, model_rules=deepcopy(OLD_RULES))
        with self.assertRaisesRegex(InputError, "v21"):
            compile_entity_scene(specification, self.catalog)
        scene = deepcopy(compiled["scene"])
        scene.update(ruleset=OLD_RULESET, model_rules=deepcopy(OLD_RULES))
        with self.assertRaisesRegex(InputError, "v21"):
            simulate_spatial(scene)
        actors = _load_actors(
            compiled["scene"], compiled["scene"]["width"], compiled["scene"]["height"]
        )
        combat = PatternCombat(actors)
        with self.assertRaisesRegex(InputError, "dedicated"):
            combat.launch(actors["firespitter"], actors["tank"], actors, 0, [])

    def test_coupled_scheduler_launches_twenty_shots_then_gap_and_resolves_flight(self):
        result = self.run_scene(
            [firespitter_instance(), self.tank()],
            duration_seconds=2.24,
            maximum_step_seconds=0.9,
            recording_interval_seconds=1,
        )
        launches = events(result, "firespitter_launch")
        self.assertEqual(len(launches), 21)
        self.assertAlmostEqual(launches[19]["time_seconds"], 1.216)
        self.assertAlmostEqual(launches[20]["time_seconds"], 2.2327)
        impacts = events(result, "firespitter_impact")
        self.assertAlmostEqual(impacts[0]["time_seconds"], 0.675)
        self.assertTrue(all(event["damage"] == 49 for event in impacts))
        self.assertFalse(events(result, "projectile_launch"))
        self.assertEqual(
            result["actors"]["tank"]["maximum_hp"] - result["actors"]["tank"]["hp"],
            len(impacts) * 49,
        )
        self.assertIn(
            "firespitter_state", result["frames"][-1]["actors"]["firespitter"]
        )

    def test_source_death_cancels_unreleased_shots_but_preserves_bullets(self):
        results = []
        for step in (0.9, 0.02):
            result = self.run_scene(
                [firespitter_instance(), self.tank()],
                duration_seconds=1,
                maximum_step_seconds=step,
                effects=[damage_command("firespitter", 0.1, 10000)],
            )
            impacts = events(result, "firespitter_impact")
            self.assertEqual(len(impacts), 2)
            self.assertTrue(all(event["time_seconds"] > 0.1 for event in impacts))
            self.assertEqual(
                result["firespitters"]["states"]["firespitter"]["cancelled_shots"], 18
            )
            results.append(result["actors"]["tank"]["hp"])
        self.assertEqual(results[0], results[1])

    def test_shared_freeze_clock_pauses_burst_without_pausing_flight(self):
        result = self.run_scene(
            [firespitter_instance(), self.tank()],
            duration_seconds=1.08,
            maximum_step_seconds=0.5,
            effects=[
                {
                    "id": "freeze",
                    "kind": "freeze",
                    "time_seconds": 0.02,
                    "targets": ["firespitter"],
                    "duration_seconds": 1,
                }
            ],
        )
        launches = events(result, "firespitter_launch")
        self.assertEqual(len(launches), 2)
        self.assertAlmostEqual(launches[1]["time_seconds"], 1.064)
        self.assertAlmostEqual(
            events(result, "firespitter_impact")[0]["time_seconds"], 0.675
        )

    def test_moving_targets_and_range_entry_are_stable_across_solver_steps(self):
        results = []
        for step in (0.9, 0.01):
            attacker = entity_instance(
                "moving",
                "minion",
                12,
                "attack",
                town_hall=17,
                x=30.5,
                y=5.5,
                first_attack_seconds=100,
            )
            attacker["modifiers"]["hitpoints_multiplier"] = 100
            result = self.run_scene(
                [firespitter_instance(), attacker],
                duration_seconds=5,
                maximum_step_seconds=step,
                recording_interval_seconds=5,
            )
            launches = events(result, "firespitter_launch")
            self.assertAlmostEqual(launches[0]["time_seconds"], 2.75)
            results.append(
                (
                    result["actors"]["moving"]["hp"],
                    [
                        event["time_seconds"]
                        for event in events(result, "firespitter_impact")
                    ],
                )
            )
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(len(results[0][1]), len(results[1][1]))
        for coarse, fine in zip(results[0][1], results[1][1]):
            self.assertAlmostEqual(coarse, fine, places=7)

    def test_rage_is_captured_on_each_bullet_once_and_persists_after_expiry(self):
        rage = spell_tower_instance(x=2, y=1, town_hall=17)
        rage["spell_tower_parameters"]["cast"]["delay_seconds"] = 0
        rage["spell_tower_parameters"]["effect"]["duration_multiplier"] = 0.01
        result = self.run_scene(
            [firespitter_instance(), rage, self.tank()],
            duration_seconds=1,
            maximum_step_seconds=0.5,
        )
        launches = events(result, "firespitter_launch")
        first = launches[0]
        self.assertAlmostEqual(first["damage"], 49 * 1.6)
        self.assertAlmostEqual(
            events(result, "firespitter_impact")[0]["damage"], first["damage"]
        )
        later = next(event for event in launches if event["time_seconds"] > 0.18)
        self.assertEqual(later["damage"], 49)

    def test_full_battle_binds_orientation_and_preserves_modifier_source_audit(self):
        inputs = full_fixture(self.catalog)
        inputs[0]["battle_modifier_policy"] = modifier_policy()
        compiled = compile_full_battle(
            *inputs, self.catalog, mode_rules=self.mode_rules
        )
        actor = next(
            item
            for item in compiled["compiled"]["scene"]["actors"]
            if item["id"] == "firespitter"
        )
        self.assertAlmostEqual(actor["damage"], 49 * 1.2)
        self.assertEqual(
            actor["entity_adapter"]["source_audit"]["extraction_displayed_dps"], 438
        )
        result = simulate_full_battle(*inputs, self.catalog, mode_rules=self.mode_rules)
        self.assertAlmostEqual(
            events(result["combat"], "firespitter_launch")[0]["damage"], 49 * 1.2
        )
        self.assertEqual(result["battle_modifier_audit"]["profile_id"], "legend_i")
        self.assertFalse(result["full_game_prediction"])

    def test_layout_facing_missing_mismatched_or_wrong_convention_rejects(self):
        for fault in ("missing", "mismatched", "convention"):
            inputs = full_fixture(self.catalog)
            if fault == "missing":
                del inputs[3]["buildings"][-1]["settings"]
            elif fault == "mismatched":
                inputs[3]["buildings"][-1]["settings"]["facing_degrees"] = 90
            else:
                inputs[3]["design_configuration"]["direction_convention"] = "guess"
            with self.subTest(fault=fault), self.assertRaises(InputError):
                compile_full_battle(*inputs, self.catalog)
        inputs = full_fixture(self.catalog)
        inputs[3]["design_configuration"][
            "direction_convention"
        ] = "draft_grid_north_zero_degrees_clockwise_not_verified_UI_orientation"
        inputs[3]["buildings"][-1]["settings"]["facing_degrees"] = 90
        compile_full_battle(*inputs, self.catalog)

    def test_closed_loop_area_control_remains_supported_in_v21(self):
        scene = self.compile(
            [firespitter_instance(id="tower"), self.tank("attacker")],
            duration_seconds=3,
        )["scene"]
        plan, profile = area_plan_and_profile()
        step = plan["streams"][0]["steps"][0]
        step["all_conditions"] = [
            {
                "actor_id": "attacker",
                "field": "active",
                "operator": "equals",
                "value": True,
            }
        ]
        step["action"]["area"].update(x=3.5, y=5.5, radius=2)
        result = simulate_closed_loop(scene, plan, profile, seed=7, trials=1)[
            "samples"
        ][0]
        self.assertEqual(result["control"]["remaining_resources"]["freeze_casts"], 0)
        launches = events(result["combat"], "firespitter_launch", "tower")
        self.assertFalse(any(0.25 < event["time_seconds"] < 2.25 for event in launches))


if __name__ == "__main__":
    unittest.main()
