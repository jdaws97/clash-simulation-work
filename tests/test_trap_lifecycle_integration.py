"""Trap-owned reserves and forced trajectories through the actual battle kernel."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.firespitter_rules import (
    RULES as OLD_RULES,
    RULESET as OLD_RULESET,
    SCOPE as OLD_SCOPE,
)
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial
from clashlab.trap_lifecycle_rules import RULES, RULESET, SCOPE

from test_adapters import entity_instance
from test_battle_modifiers import modifier_policy
from test_buffs import buff_instance
from test_full_battle import fixture
from test_indirect_defenses import fixed_tank, indirect_sector
from test_skeleton_traps import SOURCE, skeleton_instance
from test_sweepers import sweeper_instance
from test_tornado_traps import tornado_instance, tornado_parameters
from test_traps import trap_instance


ROOT = Path(__file__).resolve().parents[1]


def trap_sector(catalog, entities, traps, **changes):
    return indirect_sector(
        catalog,
        entities,
        scope=SCOPE,
        model_rules=deepcopy(RULES),
        traps=traps,
        defending_unit_responses={
            "source": SOURCE,
            "actors": {
                actor["id"]: {
                    "primary": "same_tier_as_buildings",
                    "collateral": "allow",
                }
                for actor in entities
                if actor["team"] == "attack"
            },
        },
        **changes,
    )


def events(result, kind):
    return [event for event in result["trace"] if event.get("event") == kind]


def full_fixture(catalog):
    inputs = fixture(catalog, time_limit=0.8)
    specification, _, _, layout = inputs
    scene = specification["entity_scene"]
    scene.update(scope=SCOPE, model_rules=deepcopy(RULES), buff_spells=[])
    scene["defending_unit_responses"] = {
        "source": SOURCE,
        "actors": {
            actor["id"]: {"primary": "same_tier_as_buildings", "collateral": "allow"}
            for actor in scene["entities"]
            if actor["team"] == "attack"
        },
    }
    scene["traps"] = [
        skeleton_instance(x=7, y=5),
        tornado_instance(x=8, y=6),
    ]
    for trap in scene["traps"]:
        layout["inventory"][trap["entity"]] = 1
        layout["buildings"].append(
            {
                "instance": trap["id"],
                "id": trap["entity"],
                "level": trap["level"],
                "x": trap["x"],
                "y": trap["y"],
                "counts_for_destruction": False,
                **(
                    {"settings": {"target_layer": trap["mode"]}}
                    if trap["entity"] == "skeleton-trap"
                    else {}
                ),
            }
        )
    return inputs


class TrapLifecycleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.mode_rules = read_json(ROOT / "data" / "mode-rules.json")

    def compile(self, entities, traps, **changes):
        return compile_entity_scene(
            trap_sector(self.catalog, entities, traps, **changes), self.catalog
        )["scene"]

    def run_scene(self, entities, traps, **changes):
        return simulate_spatial(self.compile(entities, traps, **changes))

    def test_skeleton_release_freeze_and_combat_share_the_scheduler(self):
        first_id = "skeleton-trap::skeleton:0"
        result = self.run_scene(
            [fixed_tank(x=6, y=3.5)],
            [skeleton_instance()],
            effects=[
                {
                    "id": "freeze-first-skeleton",
                    "kind": "freeze",
                    "time_seconds": 0.35,
                    "targets": [first_id],
                    "duration_seconds": 1,
                }
            ],
            duration_seconds=1.6,
            maximum_step_seconds=0.8,
        )
        release_times = [
            event["time_seconds"] for event in events(result, "skeleton_trap_release")
        ]
        self.assertEqual(
            [round(value, 6) for value in release_times], [0.3, 0.4, 0.5, 0.6, 0.7]
        )
        launches = events(result, "projectile_launch")
        first_launch = next(event for event in launches if event["source"] == first_id)
        self.assertAlmostEqual(first_launch["time_seconds"], 1.5)
        self.assertTrue(any(event["time_seconds"] < 1 for event in launches))
        self.assertLess(
            result["actors"]["tank"]["hp"], result["actors"]["tank"]["maximum_hp"]
        )
        self.assertEqual(result["actors"][first_id]["buff_class"], "troop")
        self.assertFalse(result["actors"][first_id]["counts_for_destruction"])

    def test_air_route_crossing_releases_at_the_same_time_for_coarse_and_fine_steps(
        self,
    ):
        observations = []
        for step in (0.017, 0.8):
            flyer = fixed_tank(entity="minion", x=1.5, y=3.5)
            flyer["modifiers"]["range_multiplier"] = 1
            tower = entity_instance(
                "tower", "cannon", 21, "defense", x=20, y=3, first_attack_seconds=100
            )
            result = self.run_scene(
                [flyer, tower],
                [skeleton_instance(mode="air", x=10)],
                duration_seconds=1.8,
                maximum_step_seconds=step,
                recording_interval_seconds=2,
            )
            observations.append(
                [
                    round(event["time_seconds"], 7)
                    for event in events(result, "skeleton_trap_release")
                ]
            )
            self.assertAlmostEqual(
                result["skeleton_traps"]["states"]["skeleton-trap"]["trigger_seconds"],
                1,
            )
        self.assertEqual(observations[0], observations[1])
        self.assertEqual(observations[0], [1.3, 1.4, 1.5, 1.6, 1.7])

    def test_trap_reserves_cannot_be_externally_deployed_and_require_responses(self):
        scene = trap_sector(
            self.catalog, [fixed_tank(x=6, y=3.5)], [skeleton_instance()]
        )
        del scene["defending_unit_responses"]
        with self.assertRaisesRegex(InputError, "defending_unit_responses"):
            compile_entity_scene(scene, self.catalog)
        compiled = self.compile([fixed_tank(x=6, y=3.5)], [skeleton_instance()])
        actor_id = "skeleton-trap::skeleton:0"
        compiled["effects"] = [
            {
                "id": "external-deploy",
                "kind": "deploy",
                "time_seconds": 0,
                "targets": [actor_id],
                "positions": {actor_id: {"x": 5.5, "y": 3.5}},
            }
        ]
        with self.assertRaisesRegex(InputError, "Skeleton.*deploy|deploy.*Skeleton"):
            simulate_spatial(compiled)

    def test_tornado_capture_rejects_an_inflight_gust_and_freeze_does_not_stop_motion(
        self,
    ):
        result = self.run_scene(
            [sweeper_instance(), fixed_tank(entity="minion", x=8, y=5)],
            [tornado_instance(x=10)],
            effects=[
                {
                    "id": "freeze-flyer",
                    "kind": "freeze",
                    "time_seconds": 0.1,
                    "targets": ["tank"],
                    "duration_seconds": 2,
                }
            ],
            duration_seconds=1.5,
            recording_interval_seconds=0.5,
        )
        misses = events(result, "sweeper_miss")
        self.assertEqual(misses[0]["reason"], "tornado_capture_rejects_new_gust")
        self.assertFalse(events(result, "sweeper_impact"))
        self.assertNotEqual(result["actors"]["tank"]["x"], 8)
        self.assertGreater(result["actors"]["tank"]["frozen_until"], 1.5)
        self.assertEqual(result["sweepers"]["active_displacements"], {})
        self.assertIn("tornado", result["frames"][-1]["actors"]["tank"])

    def test_later_tornado_cancels_active_sweeper_motion_without_position_jump(self):
        result = self.run_scene(
            [sweeper_instance(), fixed_tank(entity="minion", x=8, y=5)],
            [
                tornado_instance(
                    x=10, parameters=tornado_parameters(arming_seconds=1.25)
                )
            ],
            duration_seconds=1.25,
            recording_interval_seconds=0.25,
        )
        captures = events(result, "tornado_capture")
        self.assertEqual(len(captures), 1)
        self.assertEqual(captures[0]["time_seconds"], 1.25)
        self.assertTrue(captures[0]["replaced_sweeper"])
        self.assertAlmostEqual(result["actors"]["tank"]["x"], 9)
        self.assertEqual(result["sweepers"]["active_displacements"], {})

    def test_tornado_damage_motion_and_buff_crossings_do_not_depend_on_maximum_step(
        self,
    ):
        observations = []
        for step in (0.013, 2):
            field = buff_instance(time_seconds=0, x=6.5, y=5.5)
            field["parameters"].update(radius_multiplier=0.15, exit_linger_seconds=0)
            result = self.run_scene(
                [fixed_tank(entity="minion", x=7.5, y=5.5)],
                [tornado_instance()],
                duration_seconds=7,
                maximum_step_seconds=step,
                recording_interval_seconds=8,
                buff_spells=[field],
            )
            actor = result["actors"]["tank"]
            observations.append(
                (
                    round(actor["x"], 7),
                    round(actor["y"], 7),
                    round(actor["hp"], 7),
                    [
                        (round(event["time_seconds"], 7), event["event"])
                        for event in result["trace"]
                        if event["event"].startswith("buff_")
                        and event.get("target") == "tank"
                    ],
                )
            )
            self.assertAlmostEqual(actor["maximum_hp"] - actor["hp"], 55)
            self.assertEqual(result["tornado_traps"]["captures"], {})
        self.assertEqual(observations[0], observations[1])
        self.assertTrue(observations[0][-1])

    def test_capture_starts_at_protection_expiry_when_selected_policy_blocks_it(self):
        result = self.run_scene(
            [fixed_tank(entity="minion", x=7.5, y=5.5)],
            [
                tornado_instance(
                    parameters=tornado_parameters(
                        damage_immunity_policy="blocks_damage_and_capture"
                    )
                )
            ],
            effects=[
                {
                    "id": "protect",
                    "kind": "invulnerability",
                    "time_seconds": 0,
                    "targets": ["tank"],
                    "duration_seconds": 0.35,
                }
            ],
            duration_seconds=0.4,
            maximum_step_seconds=1,
            recording_interval_seconds=1,
        )
        self.assertAlmostEqual(
            events(result, "tornado_capture")[0]["time_seconds"], 0.35
        )

    def test_full_battle_binds_modes_and_generated_reserves_outside_destruction(self):
        arguments = full_fixture(self.catalog)
        compiled = compile_full_battle(*arguments, self.catalog)
        self.assertEqual(len(compiled["generated_summon_ids"]), 5)
        self.assertFalse(
            set(compiled["generated_summon_ids"])
            & set(compiled["validation"]["defender_bindings"])
        )
        result = simulate_full_battle(*arguments, self.catalog)
        self.assertEqual(result["outcome"]["counted_building_count"], 1)
        self.assertEqual(
            result["combat"]["skeleton_traps"]["states"]["skeleton-trap"]["released"], 5
        )
        arguments[3]["buildings"][-2]["settings"]["target_layer"] = "air"
        with self.assertRaisesRegex(InputError, "target layer"):
            compile_full_battle(*arguments, self.catalog)

    def test_role_profile_scales_tornado_damage_once_and_leaves_skeleton_statistics(
        self,
    ):
        arguments = full_fixture(self.catalog)
        arguments[0]["battle_modifier_policy"] = modifier_policy()
        compiled = compile_full_battle(*arguments, self.catalog, self.mode_rules)
        scene = compiled["compiled"]["scene"]
        tornado = next(
            trap for trap in scene["traps"] if trap["entity"] == "tornado-trap"
        )
        self.assertAlmostEqual(tornado["damage"], 66)
        for actor in scene["actors"]:
            if "trap_summon_model" in actor:
                self.assertEqual((actor["hitpoints"], actor["damage"]), (30, 25))
        simulate_spatial(scene)

    def test_cross_family_overlap_and_old_rulesets_fail_closed(self):
        entities = [fixed_tank(x=7.5, y=5.5)]
        specification = trap_sector(self.catalog, entities, [tornado_instance()])
        specification.update(scope=OLD_SCOPE, model_rules=deepcopy(OLD_RULES))
        with self.assertRaisesRegex(InputError, "v22"):
            compile_entity_scene(specification, self.catalog)
        scene = self.compile(entities, [tornado_instance()])
        self.assertEqual(scene["ruleset"], RULESET)
        scene.update(ruleset=OLD_RULESET, model_rules=deepcopy(OLD_RULES))
        with self.assertRaisesRegex(InputError, "v22"):
            simulate_spatial(scene)
        with self.assertRaisesRegex(InputError, "overlap"):
            self.compile(
                entities, [tornado_instance(), trap_instance("bomb", x=5, y=5)]
            )


if __name__ == "__main__":
    unittest.main()
