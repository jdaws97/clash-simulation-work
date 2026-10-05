"""Explicit Tornado damage quantities and finite collision-aware trajectories."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.spatial import EPSILON, _load_actors, center
from clashlab.sweepers import LinearDisplacement
from clashlab.tornado_traps import TornadoTrapCombat, compile_tornado_trap

from test_spatial import synthetic_scene, synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "declared-tornado-development-physics-not-replay-calibration"


def tornado_parameters(**changes):
    parameters = {
        "source": SOURCE,
        "arming_seconds": 0,
        "delay_seconds": 0,
        "duration_multiplier": 1,
        "trigger_radius_multiplier": 1,
        "effect_radius_multiplier": 1,
        "damage_multiplier": 1,
        "damage_quantity": "catalog_damage_is_total_over_duration",
        "pulse_interval_seconds": 1,
        "excluded_trigger_entities": [],
        "excluded_effect_entities": [],
        "pull_speed_tiles_per_second": 2,
        "orbit_radius_tiles": 1,
        "orbit_vertices": 8,
        "orbit_period_seconds": 2,
        "orbit_direction": "clockwise",
        "recovery_seconds": 0,
        "recipient_speed_policy": "same_declared_pull_speed_for_all_included_units",
        "motion_policy": "finite_inward_pull_then_regular_polygon_orbit",
        "attack_policy": "pause_unfinished_attack_work_until_release",
        "freeze_policy": "forced_motion_continues_while_frozen",
        "damage_immunity_policy": "blocks_damage_only",
        "effect_visibility_policy": "affect_invisible_units_after_visible_trigger",
        "sweeper_overlap_policy": "tornado_priority_cancel_existing_and_reject_new_gusts",
        "tornado_overlap_policy": "earliest_active_tornado_then_instance_id",
        "collision_policy": "clip_before_ground_obstacles_or_board_edge_then_hold",
    }
    parameters.update(changes)
    return parameters


def tornado_instance(**changes):
    instance = {
        "id": "tornado",
        "entity": "tornado-trap",
        "level": 3,
        "town_hall": 16,
        "team": "defense",
        "x": 5,
        "y": 5,
        "parameters": tornado_parameters(),
    }
    instance.update(changes)
    return instance


def flyer(actor_id="flyer", **changes):
    actor = synthetic_unit(
        actor_id,
        x=7.5,
        y=5.5,
        layer="air",
        movement="air",
        hitpoints=1000,
        first_attack_seconds=100,
    )
    actor.update(changes)
    return actor


def run_runtime(runtime, actors, end, maximum_step=1, time=0):
    trace = []
    while True:
        runtime.prepare(actors, time, trace)
        for actor_id, amount in runtime.resolve(actors, time, trace).items():
            actors[actor_id]["hp"] = max(0, actors[actor_id]["hp"] - amount)
        if time >= end - EPSILON:
            return trace
        boundary = runtime.next_boundary(time)
        next_time = min(end, time + maximum_step)
        if boundary is not None:
            next_time = min(next_time, boundary)
        runtime.advance(actors, time, next_time - time, trace)
        time = next_time


class TornadoTrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def runtime(self, instance=None, targets=None, sweeper_motion=None):
        trap = compile_tornado_trap(instance or tornado_instance(), self.catalog)
        targets = [flyer()] if targets is None else targets
        actors = _load_actors(synthetic_scene(targets, width=16, height=12), 16, 12)
        runtime = TornadoTrapCombat([trap], actors, 16, 12, sweeper_motion)
        return trap, actors, runtime

    def test_catalog_duration_and_damage_remain_distinct_from_selected_quantity(self):
        trap, _, _ = self.runtime()
        self.assertEqual(trap["damage"], 55)
        self.assertEqual(trap["duration_seconds"], 7)
        self.assertEqual(trap["trigger_radius"], 3)
        self.assertEqual(trap["effect_radius"], 3)
        self.assertEqual(
            trap["parameters"]["damage_quantity"],
            "catalog_damage_is_total_over_duration",
        )

    def test_total_dps_and_pulse_branches_include_the_final_partial_interval(self):
        for quantity, expected in (
            ("catalog_damage_is_total_over_duration", 55),
            ("catalog_damage_is_damage_per_second", 385),
            ("catalog_damage_is_each_pulse", 165),
        ):
            with self.subTest(quantity=quantity):
                instance = tornado_instance(
                    parameters=tornado_parameters(
                        damage_quantity=quantity, pulse_interval_seconds=2.5
                    )
                )
                _, actors, runtime = self.runtime(instance)
                trace = run_runtime(runtime, actors, 7)
                self.assertAlmostEqual(actors["flyer"]["hp"], 1000 - expected)
                pulses = [event for event in trace if event["event"] == "tornado_pulse"]
                self.assertEqual(
                    [event["time_seconds"] for event in pulses], [2.5, 5, 7]
                )
                self.assertEqual(runtime.captures, {})

    def test_pull_and_orbit_are_finite_and_do_not_teleport_to_the_trap(self):
        _, actors, runtime = self.runtime()
        trace = []
        runtime.prepare(actors, 0, trace)
        self.assertEqual(center(actors["flyer"]), (7.5, 5.5))
        self.assertAlmostEqual(runtime.next_boundary(0), 0.5)
        runtime.advance(actors, 0, 0.25, trace)
        self.assertAlmostEqual(actors["flyer"]["x"], 7)
        runtime.advance(actors, 0.25, 0.25, trace)
        self.assertAlmostEqual(actors["flyer"]["x"], 6.5)
        self.assertAlmostEqual(actors["flyer"]["y"], 5.5)
        self.assertEqual(runtime.captures["flyer"]["phase"], "orbiting")
        runtime.advance(actors, 0.5, 0.25, trace)
        self.assertAlmostEqual(actors["flyer"]["x"], 5.5 + 2**-0.5)
        self.assertAlmostEqual(actors["flyer"]["y"], 5.5 + 2**-0.5)
        self.assertAlmostEqual(actors["flyer"]["next_attack"], 107)
        self.assertEqual(actors["flyer"]["frozen_until"], 0)

    def test_coarse_and_fine_steps_agree_on_motion_damage_and_attack_work(self):
        results = []
        for step in (0.013, 2):
            _, actors, runtime = self.runtime()
            trace = run_runtime(runtime, actors, 7, step)
            results.append(
                (
                    tuple(round(value, 8) for value in center(actors["flyer"])),
                    round(actors["flyer"]["hp"], 8),
                    actors["flyer"]["next_attack"],
                    [
                        round(event["time_seconds"], 8)
                        for event in trace
                        if event["event"] == "tornado_pulse"
                    ],
                )
            )
        self.assertEqual(results[0], results[1])

    def test_freeze_does_not_stop_existing_forced_motion(self):
        _, actors, runtime = self.runtime()
        trace = []
        runtime.prepare(actors, 0, trace)
        actors["flyer"]["frozen_until"] = 3
        runtime.advance(actors, 0, 0.25, trace)
        self.assertAlmostEqual(actors["flyer"]["x"], 7)
        self.assertIsNotNone(runtime.forced_motion(actors["flyer"], 0.25))

    def test_damage_immunity_can_block_damage_without_blocking_capture(self):
        _, actors, runtime = self.runtime()
        actors["flyer"]["immune_until"] = 10
        run_runtime(runtime, actors, 1)
        self.assertIn("flyer", runtime.captures)
        self.assertEqual(actors["flyer"]["hp"], 1000)
        self.assertNotEqual(center(actors["flyer"]), (7.5, 5.5))

    def test_ground_motion_stops_before_a_wall_and_air_ignores_it(self):
        wall = synthetic_structure("wall", x=7, y=5, width=1, height=1)
        for layer in ("ground", "air"):
            with self.subTest(layer=layer):
                _, actors, runtime = self.runtime(
                    targets=[flyer(layer=layer, movement=layer, x=8.5), deepcopy(wall)]
                )
                trace = run_runtime(runtime, actors, 1)
                holds = [
                    event
                    for event in trace
                    if event["event"] == "tornado_collision_hold"
                ]
                if layer == "ground":
                    self.assertEqual(len(holds), 1)
                    self.assertGreater(actors["flyer"]["x"], 8)
                    self.assertAlmostEqual(actors["flyer"]["x"], 8)
                    self.assertEqual(
                        runtime.forced_motion(actors["flyer"], 1)["route"], []
                    )
                else:
                    self.assertEqual(holds, [])
                    self.assertAlmostEqual(actors["flyer"]["x"], 6.5)

    def test_orbit_cannot_move_outside_the_board(self):
        _, actors, runtime = self.runtime(tornado_instance(x=0), [flyer(x=2.5)])
        trace = run_runtime(runtime, actors, 3)
        self.assertGreaterEqual(actors["flyer"]["x"], 0)
        self.assertTrue(
            any(event["event"] == "tornado_collision_hold" for event in trace)
        )
        self.assertEqual(runtime.captures["flyer"]["phase"], "held")

    def test_capture_cancels_existing_sweeper_without_double_counting_pause(self):
        motion = LinearDisplacement(16, 12)
        _, actors, runtime = self.runtime(sweeper_motion=motion)
        trace = []
        motion.start(
            actors["flyer"],
            0,
            (1, 0),
            {
                "push_distance_tiles": 4,
                "push_speed_tiles_per_second": 4,
                "recovery_seconds": 0,
            },
            "sweeper",
            trace,
        )
        self.assertIn("flyer", motion.motions)
        runtime.prepare(actors, 0, trace)
        self.assertEqual(motion.motions, {})
        self.assertEqual(center(actors["flyer"]), (7.5, 5.5))
        self.assertAlmostEqual(actors["flyer"]["next_attack"], 107)
        self.assertTrue(runtime.blocks_sweeper(actors["flyer"], 0))
        capture = next(event for event in trace if event["event"] == "tornado_capture")
        self.assertTrue(capture["replaced_sweeper"])

    def test_inflight_sweeper_entry_is_a_capture_boundary(self):
        motion = LinearDisplacement(16, 12)
        _, actors, runtime = self.runtime(
            tornado_instance(x=10), [flyer(x=5.5)], motion
        )
        trace = []
        motion.start(
            actors["flyer"],
            0,
            (1, 0),
            {
                "push_distance_tiles": 4,
                "push_speed_tiles_per_second": 4,
                "recovery_seconds": 0,
            },
            "sweeper",
            trace,
        )
        forced = motion.forced_motion(actors["flyer"], 0)
        entry = runtime.first_crossing_delay(
            actors["flyer"], forced["route"], 0, 1, forced["speed_tiles_per_second"]
        )
        self.assertAlmostEqual(entry, 0.5)
        motion.advance(actors, 0, entry, trace)
        runtime.prepare(actors, entry, trace)
        self.assertEqual(center(actors["flyer"]), (7.5, 5.5))
        self.assertEqual(motion.motions, {})
        self.assertAlmostEqual(runtime.captures["flyer"]["release_seconds"], 7.5)

    def test_trigger_persists_if_primary_dies_before_activation(self):
        instance = tornado_instance(parameters=tornado_parameters(delay_seconds=1))
        _, actors, runtime = self.runtime(
            instance, [flyer("first"), flyer("second", x=9)]
        )
        trace = []
        runtime.prepare(actors, 0, trace)
        actors["first"]["hp"] = 0
        actors["second"]["x"] = 7.5
        runtime.prepare(actors, 1, trace)
        self.assertIn("second", runtime.captures)
        self.assertEqual(runtime.states["tornado"]["end_seconds"], 8)

    def test_tornado_overlap_is_independent_of_model_input_order(self):
        outcomes = []
        first = compile_tornado_trap(tornado_instance(id="a-first", x=5), self.catalog)
        second = compile_tornado_trap(
            tornado_instance(id="b-second", x=6), self.catalog
        )
        for models in ([first, second], [second, first]):
            actors = _load_actors(
                synthetic_scene([flyer()], width=16, height=12), 16, 12
            )
            runtime = TornadoTrapCombat(models, actors, 16, 12)
            runtime.prepare(actors, 0, [])
            outcomes.append(runtime.captures["flyer"]["trap_id"])
        self.assertEqual(outcomes, ["a-first", "a-first"])

    def test_missing_quantity_or_overlap_policy_is_rejected(self):
        for field in ("damage_quantity", "sweeper_overlap_policy", "collision_policy"):
            instance = tornado_instance()
            instance["parameters"].pop(field)
            with self.subTest(field=field), self.assertRaises(InputError):
                compile_tornado_trap(instance, self.catalog)


if __name__ == "__main__":
    unittest.main()
