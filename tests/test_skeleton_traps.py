"""Layer-specific finite release and honest Skeleton statistic provenance."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.skeleton_traps import (
    STATISTIC_BASIS,
    SkeletonTrapCombat,
    compile_skeleton_reserves,
    compile_skeleton_trap,
)
from clashlab.spatial import _load_actors

from test_spatial import synthetic_scene, synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "declared-skeleton-trap-development-hypothesis-not-replay-calibration"


def skeleton_parameters(count=5, **changes):
    parameters = {
        "source": SOURCE,
        "arming_seconds": 0,
        "trigger_radius_multiplier": 1,
        "excluded_trigger_entities": [],
        "release_delay_seconds": 0.3,
        "release_interval_seconds": 0.1,
        "spawn_offsets": [{"dx": 0, "dy": 0} for _ in range(count)],
        "first_attack_delay_seconds": 0.2,
        "statistics_basis": STATISTIC_BASIS,
        "unit_lifetime_policy": "persist_until_killed_or_battle_end",
        "trigger_loss_policy": "complete_release_after_trigger_even_if_enemy_leaves_or_dies",
        "trap_freeze_policy": "release_clock_independent_of_unit_freeze",
        "spawn_policy": "declared_offsets_must_be_clear",
        "ground_wall_policy": "avoid_all_blocking_walls_and_structures",
        "released_targeting_policy": "nearest_retained_hostile_units_anywhere",
    }
    parameters.update(changes)
    return parameters


def skeleton_instance(**changes):
    instance = {
        "id": "skeleton-trap",
        "entity": "skeleton-trap",
        "level": 4,
        "town_hall": 16,
        "team": "defense",
        "mode": "ground",
        "x": 5,
        "y": 3,
        "parameters": skeleton_parameters(),
    }
    instance.update(changes)
    return instance


class SkeletonTrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def runtime(self, instance=None, targets=None):
        instance = instance or skeleton_instance()
        trap = compile_skeleton_trap(instance, self.catalog, 8)
        reserves = compile_skeleton_reserves(trap)
        targets = (
            targets
            if targets is not None
            else [synthetic_unit("enemy", x=1.5, y=3.5, damage=0)]
        )
        scene = synthetic_scene([*targets, *reserves], width=15, height=10)
        actors = _load_actors(scene, 15, 10)
        return trap, actors, SkeletonTrapCombat([trap], actors, 15, 10), []

    def test_th16_count_level_and_unarmored_statistics_are_separate_sources(self):
        trap, actors, _, _ = self.runtime()
        self.assertEqual(trap["level"], 4)
        self.assertEqual(trap["skeleton_level"], 1)
        self.assertEqual(len(trap["unit_ids"]), 5)
        self.assertEqual(trap["trigger_radius"], 5)
        skeleton = actors[trap["unit_ids"][0]]
        self.assertEqual(skeleton["hp"], 30)
        self.assertEqual(skeleton["damage"], 25)
        self.assertEqual(skeleton["attack_interval_seconds"], 1)
        self.assertEqual(skeleton["speed"], 3)
        self.assertEqual(skeleton["range"], 0.4)
        self.assertEqual(skeleton["housing_space"], 1)
        self.assertNotIn("armor", skeleton)
        self.assertNotIn("armorHitpoints", skeleton)
        self.assertIn("skeleton-spell", skeleton["source"])
        self.assertIn("skeleton-trap", trap["statistics_source"])

    def test_air_mode_changes_trigger_movement_and_weapon_layer_together(self):
        trap, actors, runtime, trace = self.runtime(
            skeleton_instance(mode="air"),
            [synthetic_unit("flyer", x=1.5, y=3.5, layer="air", movement="air")],
        )
        runtime.prepare(actors, 0, trace)
        self.assertEqual(runtime.states[trap["id"]]["trigger_id"], "flyer")
        for actor_id in trap["unit_ids"]:
            actor = actors[actor_id]
            self.assertEqual(actor["layer"], "air")
            self.assertEqual(actor["movement"], "air")
            self.assertEqual(actor["target_layers"], ["air"])
            self.assertEqual(actor["attack_model"]["target_layers"], ["air"])
            self.assertNotIn("wall_behavior", actor)

    def test_release_clock_is_finite_and_independent_of_trigger_loss(self):
        trap, actors, runtime, trace = self.runtime()
        runtime.prepare(actors, 0, trace)
        self.assertAlmostEqual(runtime.next_boundary(0), 0.3)
        self.assertTrue(
            all(
                actors[actor_id]["spawn_seconds"] == "controlled"
                for actor_id in trap["unit_ids"]
            )
        )
        actors["enemy"]["hp"] = 0
        for time in (0.3, 0.4, 0.5, 0.6, 0.7, 1, 20):
            runtime.prepare(actors, time, trace)
        releases = [
            event for event in trace if event["event"] == "skeleton_trap_release"
        ]
        self.assertEqual(len(releases), 5)
        self.assertEqual(
            [round(event["time_seconds"], 5) for event in releases],
            [0.3, 0.4, 0.5, 0.6, 0.7],
        )
        self.assertAlmostEqual(actors[trap["unit_ids"][0]]["next_attack"], 0.5)
        self.assertIsNone(runtime.next_boundary(20))

    def test_zero_interval_releases_all_units_once_at_the_same_boundary(self):
        instance = skeleton_instance(
            parameters=skeleton_parameters(
                release_delay_seconds=0, release_interval_seconds=0
            )
        )
        trap, actors, runtime, trace = self.runtime(instance)
        runtime.prepare(actors, 0, trace)
        runtime.prepare(actors, 0, trace)
        releases = [
            event for event in trace if event["event"] == "skeleton_trap_release"
        ]
        self.assertEqual(len(releases), 5)
        self.assertTrue(
            all(actors[actor_id]["spawn_seconds"] == 0 for actor_id in trap["unit_ids"])
        )
        self.assertEqual(
            sum(actor["counts_for_destruction"] for actor in actors.values()), 0
        )
        self.assertTrue(
            all(
                actors[actor_id]["target_priorities"] == ["unit"]
                for actor_id in trap["unit_ids"]
            )
        )

    def test_ground_air_friendliness_and_invisibility_control_triggering(self):
        targets = [
            synthetic_unit("air", x=5.5, y=3.5, layer="air", movement="air"),
            synthetic_unit("friendly", x=5.5, y=3.5, team="defense"),
            synthetic_unit("hidden", x=5.5, y=3.5),
        ]
        trap, actors, runtime, trace = self.runtime(targets=targets)
        actors["hidden"]["_untargetable_until"] = 1
        runtime.prepare(actors, 0, trace)
        self.assertIsNone(runtime.states[trap["id"]]["trigger_seconds"])
        runtime.prepare(actors, 1, trace)
        self.assertEqual(runtime.states[trap["id"]]["trigger_id"], "hidden")

    def test_target_exclusion_does_not_hide_another_eligible_attacker(self):
        instance = skeleton_instance(
            parameters=skeleton_parameters(excluded_trigger_entities=["archer"])
        )
        targets = [
            synthetic_unit("archer", x=5.5, y=3.5, entity_adapter={"entity": "archer"}),
            synthetic_unit(
                "barbarian", x=4.5, y=3.5, entity_adapter={"entity": "barbarian"}
            ),
        ]
        trap, actors, runtime, trace = self.runtime(instance, targets)
        runtime.prepare(actors, 0, trace)
        self.assertEqual(runtime.states[trap["id"]]["trigger_id"], "barbarian")

    def test_entry_uses_the_passed_motion_speed_and_arming_boundary(self):
        instance = skeleton_instance(
            x=8,
            parameters=skeleton_parameters(
                arming_seconds=1, trigger_radius_multiplier=0.2
            ),
        )
        _, actors, runtime, trace = self.runtime(
            instance, [synthetic_unit("enemy", x=0.5, y=3.5)]
        )
        self.assertEqual(runtime.next_boundary(0), 1)
        self.assertIsNone(
            runtime.first_crossing_delay(actors["enemy"], [(10.5, 3.5)], 0, 10, 2)
        )
        runtime.prepare(actors, 1, trace)
        self.assertAlmostEqual(
            runtime.first_crossing_delay(actors["enemy"], [(10.5, 3.5)], 1, 10, 2), 3.5
        )

    def test_missing_mode_policy_count_and_higher_skeleton_statistics_fail_closed(self):
        variants = []
        missing_mode = skeleton_instance()
        missing_mode.pop("mode")
        variants.append(missing_mode)
        missing_policy = skeleton_instance()
        missing_policy["parameters"].pop("statistics_basis")
        variants.append(missing_policy)
        variants.append(skeleton_instance(parameters=skeleton_parameters(count=4)))
        variants.append(skeleton_instance(level=5, town_hall=18))
        for instance in variants:
            with self.subTest(instance=instance), self.assertRaises(InputError):
                compile_skeleton_trap(instance, self.catalog, 8)

    def test_reserve_tampering_and_spawn_obstruction_are_rejected(self):
        trap, actors, _, _ = self.runtime()
        for change in (
            {"counts_for_destruction": True},
            {"spawn_seconds": 0},
            {"target_priorities": ["building"]},
        ):
            changed = deepcopy(actors)
            changed[trap["unit_ids"][0]].update(change)
            with self.subTest(change=change), self.assertRaises(InputError):
                SkeletonTrapCombat([trap], changed, 15, 10)
        obstacle = synthetic_structure("wall", x=6, y=3, width=1, height=1)
        instance = skeleton_instance(
            parameters=skeleton_parameters(
                spawn_offsets=[{"dx": 1, "dy": 0} for _ in range(5)]
            )
        )
        with self.assertRaisesRegex(InputError, "spawn point"):
            self.runtime(instance, [obstacle])


if __name__ == "__main__":
    unittest.main()
