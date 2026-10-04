"""Catalog-connected Air Sweeper geometry and declared finite-motion physics."""

from copy import deepcopy
from math import cos, radians, sin
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.hazards import PulsedHazards
from clashlab.hit_status import HitStatusCombat
from clashlab.spatial import _apply_effects
from clashlab.sweepers import (
    LinearDisplacement,
    SweeperCombat,
    attack_locked,
    compile_air_sweeper,
)

from test_adapters import entity_instance
from test_hit_status import slow
from test_spatial import synthetic_structure, synthetic_unit
from test_townhalls import hazard


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "declared-sweeper-geometry-and-motion-not-replay-validated"


def sweeper_parameters(**changes):
    parameters = {
        "source": SOURCE,
        "orientation_degrees": 0,
        "orientation_basis": "clockwise_from_positive_x_in_screen_coordinates",
        "geometry_basis": "pinned_extraction_degrees_and_hundredths_of_a_tile",
        "blast_cone_degrees": 45,
        "blast_aim": "toward_primary",
        "recipient_policy": "capture_launch_candidates_recheck_fixed_cone_at_impact",
        "excluded_entities": [],
        "launch_delay_seconds": 0,
        "gust_speed_tiles_per_second": 3,
        "push_statistic_basis": "snapshot_push_strength_is_tiles",
        "push_distance_multiplier": 1,
        "push_direction": "away_from_captured_source",
        "push_speed_tiles_per_second": 4,
        "recovery_seconds": 0.5,
        "recipient_freeze_policy": "forced_motion_continues_while_frozen",
        "damage_immunity_policy": "damage_immunity_does_not_block_push",
        "released_gust_policy": "released_gust_independent_of_source_state",
        "overlap_policy": "replace_remaining_motion_keep_longest_pause",
        "board_policy": "clip_distance_along_ray_keep_nominal_speed",
        "collision_policy": "air_ignores_ground_footprints",
    }
    parameters.update(changes)
    return parameters


def sweeper_instance(**changes):
    instance = entity_instance(
        "sweeper",
        "air-sweeper",
        7,
        "defense",
        x=4,
        y=4,
        attack_parameters={},
        sweeper_parameters=sweeper_parameters(),
    )
    instance.update(changes)
    return instance


def compiled_sweeper(catalog, instance=None):
    instance = instance or sweeper_instance()
    if not catalog.available("air-sweeper", instance["level"], instance["town_hall"]):
        raise InputError("Air Sweeper level unavailable at the declared Town Hall")
    row = catalog.level("air-sweeper", instance["level"])
    modifiers = instance["modifiers"]
    actor = synthetic_structure(
        instance["id"],
        source=catalog.records["air-sweeper"]["source"],
        x=instance["x"],
        y=instance["y"],
        width=2,
        height=2,
        hitpoints=row["hitpoints"] * modifiers["hitpoints_multiplier"],
        first_attack_seconds=instance["first_attack_seconds"],
        entity_adapter={
            "entity": "air-sweeper",
            "level": instance["level"],
            "town_hall": instance["town_hall"],
            "snapshot_verification": catalog.records["air-sweeper"]["verification"],
        },
    )
    compile_air_sweeper(actor, instance, catalog.entity("air-sweeper"), row, modifiers)
    actor.update(
        hp=actor["hitpoints"],
        frozen_until=0,
        immune_until=0,
        next_attack=actor["first_attack_seconds"],
        target=None,
    )
    return actor


def air_unit(actor_id="air", **changes):
    actor = synthetic_unit(
        actor_id,
        x=8,
        y=5,
        layer="air",
        movement="air",
        speed=2,
        hp=100,
        maximum_hp=100,
        frozen_until=0,
        immune_until=0,
        next_attack=1.75,
        target="sweeper",
        entity_adapter={"entity": "minion"},
    )
    actor.update(changes)
    return actor


def events(trace, event):
    return [item for item in trace if item["event"] == event]


class SweeperAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_th16_level_seven_compiles_non_damaging_catalog_weapon(self):
        actor = compiled_sweeper(self.catalog)
        self.assertEqual(actor["hitpoints"], 1050)
        self.assertEqual(actor["damage"], 0)
        self.assertEqual(actor["attack_interval_seconds"], 5)
        self.assertEqual(actor["range"], 15)
        self.assertEqual(actor["minimum_range"], 1)
        self.assertEqual(actor["target_layers"], ["air"])
        self.assertEqual(actor["attack_model"]["kind"], "none")
        model = actor["sweeper_model"]
        self.assertEqual(model["push_distance_tiles"], 4)
        self.assertEqual(model["acquisition_cone_degrees"], 105)
        self.assertEqual(model["orientation_step_degrees"], 45)
        self.assertEqual(
            actor["entity_adapter"]["snapshot_verification"], "unverified_snapshot"
        )

    def test_level_strengths_and_th_caps_use_catalog_rows(self):
        for level, strength in ((1, 1.6), (4, 2.8), (7, 4)):
            with self.subTest(level=level):
                actor = compiled_sweeper(self.catalog, sweeper_instance(level=level))
                self.assertEqual(
                    actor["sweeper_model"]["push_distance_tiles"], strength
                )
        with self.assertRaises(InputError):
            compiled_sweeper(self.catalog, sweeper_instance(level=8))
        with self.assertRaisesRegex(InputError, "unavailable"):
            compiled_sweeper(self.catalog, sweeper_instance(town_hall=10))

    def test_geometry_reference_retains_raw_units_and_selected_mapping(self):
        actor = compiled_sweeper(self.catalog)
        evidence = actor["entity_adapter"]["sweeper_statistics"]["geometry_reference"]
        self.assertEqual(evidence["min_range"], 100)
        self.assertEqual(evidence["attack_range"], 1500)
        self.assertEqual(evidence["attack_speed"], 5000)
        self.assertEqual(evidence["selected_range_units_per_tile"], 100)
        self.assertIn("b8f42a707fe92d5293d46088bf536450ae422e7b", evidence["source"])
        self.assertIn(
            "not_replay_validated", actor["entity_adapter"]["behavior_verification"]
        )

    def test_missing_physics_and_unsupported_rotation_are_rejected(self):
        for failure in ("missing_speed", "rotation", "implicit_recipient_policy"):
            with self.subTest(failure=failure):
                instance = sweeper_instance()
                parameters = instance["sweeper_parameters"]
                if failure == "missing_speed":
                    parameters.pop("push_speed_tiles_per_second")
                elif failure == "rotation":
                    parameters["orientation_degrees"] = 22.5
                else:
                    parameters["recipient_policy"] = "whatever_the_game_does"
                with self.assertRaises(InputError):
                    compiled_sweeper(self.catalog, instance)

    def test_damage_modifiers_cannot_turn_sweeper_into_a_damaging_weapon(self):
        instance = sweeper_instance()
        instance["modifiers"]["damage_multiplier"] = 2
        with self.assertRaisesRegex(InputError, "non-damaging"):
            compiled_sweeper(self.catalog, instance)

    def test_model_and_provenance_are_independent_of_input_mutation(self):
        instance = sweeper_instance()
        actor = compiled_sweeper(self.catalog, instance)
        instance["sweeper_parameters"]["excluded_entities"].append("minion")
        self.assertEqual(actor["sweeper_model"]["excluded_entities"], [])
        self.assertEqual(
            actor["entity_adapter"]["sweeper_parameters"]["excluded_entities"], []
        )


class SweeperRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def runtime(self, targets=None, **parameters):
        instance = sweeper_instance(sweeper_parameters=sweeper_parameters(**parameters))
        source = compiled_sweeper(self.catalog, instance)
        actors = {source["id"]: source}
        actors.update({target["id"]: target for target in targets or [air_unit()]})
        return actors, SweeperCombat(actors, 30, 30), []

    def test_launch_flight_finite_push_and_recovery_have_distinct_boundaries(self):
        actors, runtime, trace = self.runtime()
        target = actors["air"]
        runtime.prepare(actors, 0, trace)
        self.assertEqual(runtime.next_boundary(0), 1)
        runtime.resolve(actors, 0.5, trace)
        self.assertEqual(target["x"], 8)
        runtime.resolve(actors, 1, trace)
        self.assertEqual(target["x"], 8)
        self.assertEqual(target["frozen_until"], 0)
        self.assertEqual(target["next_attack"], 3.25)
        self.assertEqual(runtime.next_boundary(1), 2)
        motion = runtime.forced_motion(target, 1)
        self.assertEqual(motion["route"], [(12, 5)])
        self.assertEqual(motion["speed_tiles_per_second"], 4)
        runtime.advance(actors, 1, 0.25, trace)
        self.assertEqual(target["x"], 9)
        runtime.advance(actors, 1.25, 0.75, trace)
        self.assertEqual(target["x"], 12)
        self.assertIsNone(runtime.forced_motion(target, 2))
        self.assertTrue(attack_locked(target, 2))
        self.assertEqual(runtime.next_boundary(2), 2.5)
        self.assertFalse(attack_locked(target, 2.5))
        self.assertEqual(target["hp"], 100)
        self.assertEqual(events(trace, "sweeper_impact")[0]["damage"], 0)

    def test_only_nearest_eligible_enemy_air_selects_the_primary(self):
        targets = [
            air_unit("z-tie", x=8),
            air_unit("a-tie", x=8),
            air_unit("near-ground", x=6.1, layer="ground", movement="ground"),
            air_unit("near-friend", x=6.2, team="defense"),
            air_unit("dead", x=6.3, hp=0),
            air_unit("hidden", x=6.4, _untargetable_until=2),
            air_unit("reserve", x=6.5, spawn_seconds="controlled"),
        ]
        actors, runtime, trace = self.runtime(targets)
        runtime.prepare(actors, 0, trace)
        launch = events(trace, "sweeper_launch")[0]
        self.assertEqual(launch["primary"], "a-tie")
        self.assertEqual(launch["recipients"], ["a-tie", "z-tie"])

    def test_minimum_range_maximum_range_and_acquisition_orientation(self):
        for point, expected in (
            ((5.5, 5), False),
            ((6, 5), True),
            ((20, 5), True),
            ((20.01, 5), False),
            ((5, 8), False),
            ((2, 5), False),
        ):
            with self.subTest(point=point):
                actors, runtime, trace = self.runtime(
                    [air_unit(x=point[0], y=point[1])]
                )
                runtime.prepare(actors, 0, trace)
                self.assertEqual(bool(events(trace, "sweeper_launch")), expected)
        actors, runtime, trace = self.runtime(
            [air_unit(x=5, y=8)], orientation_degrees=90
        )
        runtime.prepare(actors, 0, trace)
        self.assertEqual(events(trace, "sweeper_launch")[0]["angle_degrees"], 90)

    def test_acquisition_cone_boundary_and_narrow_blast_are_separate(self):
        edge = radians(52.5)
        target = air_unit(x=5 + 3 * cos(edge), y=5 + 3 * sin(edge))
        actors, runtime, trace = self.runtime([target])
        runtime.prepare(actors, 0, trace)
        self.assertAlmostEqual(
            events(trace, "sweeper_launch")[0]["angle_degrees"], 52.5
        )
        targets = [air_unit("primary"), air_unit("side", x=8, y=7)]
        actors, runtime, trace = self.runtime(targets)
        runtime.prepare(actors, 0, trace)
        self.assertEqual(events(trace, "sweeper_launch")[0]["recipients"], ["primary"])

    def test_gust_arrivals_use_individual_launch_distances(self):
        actors, runtime, trace = self.runtime(
            [air_unit("near", x=8), air_unit("far", x=11)], launch_delay_seconds=0.5
        )
        runtime.prepare(actors, 0, trace)
        packets = runtime.result()["pending_gusts"]
        self.assertEqual([packet["arrival_seconds"] for packet in packets], [1.5, 2.5])
        runtime.resolve(actors, 1.5, trace)
        self.assertIsNotNone(runtime.forced_motion(actors["near"], 1.5))
        self.assertIsNone(runtime.forced_motion(actors["far"], 1.5))

    def test_source_freeze_blocks_release_and_does_not_cancel_released_gust(self):
        actors, runtime, trace = self.runtime()
        actors["sweeper"]["frozen_until"] = 2
        runtime.prepare(actors, 0, trace)
        self.assertEqual(events(trace, "sweeper_launch"), [])
        runtime.prepare(actors, 2, trace)
        self.assertEqual(len(events(trace, "sweeper_launch")), 1)
        actors["sweeper"]["frozen_until"] = 10
        runtime.resolve(actors, 3, trace)
        self.assertIsNotNone(runtime.forced_motion(actors["air"], 3))

    def test_source_death_does_not_cancel_gust_or_motion(self):
        actors, runtime, trace = self.runtime()
        runtime.prepare(actors, 0, trace)
        actors["sweeper"]["hp"] = 0
        runtime.resolve(actors, 1, trace)
        runtime.advance(actors, 1, 1, trace)
        self.assertEqual(actors["air"]["x"], 12)
        runtime.prepare(actors, 5, trace)
        self.assertEqual(len(events(trace, "sweeper_launch")), 1)

    def test_dead_or_departed_recipients_miss_and_late_entrants_are_not_captured(self):
        targets = [air_unit("dead"), air_unit("departed"), air_unit("late", y=10)]
        actors, runtime, trace = self.runtime(targets)
        runtime.prepare(actors, 0, trace)
        actors["dead"]["hp"] = 0
        actors["departed"]["y"] = 10
        actors["late"]["y"] = 5
        runtime.resolve(actors, 1, trace)
        self.assertEqual(events(trace, "sweeper_impact"), [])
        self.assertEqual(len(events(trace, "sweeper_miss")), 2)
        self.assertEqual(runtime.result()["active_displacements"], {})

    def test_immunity_and_frozen_recipient_policies_are_explicit(self):
        for immunity_policy, freeze_policy, expected in (
            (
                "damage_immunity_does_not_block_push",
                "forced_motion_continues_while_frozen",
                True,
            ),
            (
                "damage_immunity_blocks_push",
                "forced_motion_continues_while_frozen",
                False,
            ),
            (
                "damage_immunity_does_not_block_push",
                "frozen_targets_ignore_new_push",
                False,
            ),
        ):
            with self.subTest(immunity=immunity_policy, freeze=freeze_policy):
                target = air_unit(immune_until=10, frozen_until=10, next_attack=11)
                actors, runtime, trace = self.runtime(
                    [target],
                    damage_immunity_policy=immunity_policy,
                    recipient_freeze_policy=freeze_policy,
                )
                runtime.prepare(actors, 0, trace)
                runtime.resolve(actors, 1, trace)
                self.assertEqual(bool(events(trace, "sweeper_impact")), expected)
                if expected:
                    runtime.advance(actors, 1, 0.5, trace)
                    self.assertEqual(target["x"], 10)
                    self.assertEqual(target["frozen_until"], 10)
                    self.assertEqual(target["next_attack"], 11)

    def test_cadence_launches_once_per_ready_cycle_without_dealing_damage(self):
        actors, runtime, trace = self.runtime()
        for time in (0, 0, 1, 4.9, 5, 5):
            runtime.prepare(actors, time, trace)
        self.assertEqual(
            [event["time_seconds"] for event in events(trace, "sweeper_launch")], [0, 5]
        )
        self.assertEqual(actors["air"]["hp"], 100)

    def test_declared_entity_exclusion_prevents_selection_and_capture(self):
        actors, runtime, trace = self.runtime(excluded_entities=["minion"])
        runtime.prepare(actors, 0, trace)
        self.assertEqual(events(trace, "sweeper_launch"), [])

    def test_flight_arrival_rechecks_protection_instead_of_capturing_at_launch(self):
        actors, runtime, trace = self.runtime(
            damage_immunity_policy="damage_immunity_blocks_push"
        )
        runtime.prepare(actors, 0, trace)
        actors["air"]["immune_until"] = 10
        runtime.resolve(actors, 1, trace)
        self.assertEqual(
            events(trace, "sweeper_miss")[0]["reason"], "damage_immunity_blocks_push"
        )


class FiniteDisplacementTests(unittest.TestCase):
    def model(self, **changes):
        model = {
            "push_distance_tiles": 4,
            "push_speed_tiles_per_second": 4,
            "recovery_seconds": 0.5,
        }
        model.update(changes)
        return model

    def test_coarse_and_fine_advancement_have_same_linear_path_and_final_position(self):
        for steps in ([0.25, 0.75], [0.25, 0.25, 0.25, 0.25]):
            target = air_unit()
            runtime = LinearDisplacement(30, 30)
            trace = []
            runtime.start(target, 0, (1, 0), self.model(), "sweeper", trace)
            time = 0
            for duration in steps:
                runtime.advance({target["id"]: target}, time, duration, trace)
                time += duration
                self.assertAlmostEqual(target["x"], 8 + 4 * time)
            self.assertEqual(target["x"], 12)
            self.assertEqual(len(events(trace, "displacement_arrive")), 1)

    def test_board_clipping_preserves_direction_speed_and_legal_position(self):
        target = air_unit(x=19.5, y=5)
        runtime = LinearDisplacement(20, 20)
        trace = []
        runtime.start(target, 0, (1, 0), self.model(), "sweeper", trace)
        event = events(trace, "displacement_start")[0]
        self.assertAlmostEqual(event["actual_distance"], 0.5)
        self.assertAlmostEqual(event["arrival_seconds"], 0.125)
        self.assertAlmostEqual(event["pause_until"], 0.625)
        self.assertEqual(runtime.forced_motion(target, 0)["speed_tiles_per_second"], 4)
        runtime.advance({target["id"]: target}, 0, event["arrival_seconds"], trace)
        self.assertLess(target["x"], 20)
        self.assertEqual(target["y"], 5)

    def test_air_can_pass_ground_walls_but_ground_recipients_are_rejected(self):
        target = air_unit()
        wall = synthetic_structure("wall", x=9, y=4, width=1, height=3, hp=100)
        runtime = LinearDisplacement(30, 30)
        trace = []
        runtime.start(target, 0, (1, 0), self.model(), "sweeper", trace)
        runtime.advance({"air": target, "wall": wall}, 0, 1, trace)
        self.assertEqual(target["x"], 12)
        ground = air_unit("ground", layer="ground", movement="ground")
        with self.assertRaisesRegex(InputError, "ground recipient"):
            runtime.start(ground, 0, (1, 0), self.model(), "sweeper", trace)
        self.assertEqual(ground["x"], 8)

    def test_push_invalidates_cached_attack_and_healing_routes(self):
        target = air_unit(
            _remaining_path=[(9, 5)],
            _path_signature=("old",),
            healing_target="old-target",
        )
        runtime = LinearDisplacement(30, 30)
        runtime.start(target, 0, (1, 0), self.model(), "sweeper", [])
        self.assertNotIn("_remaining_path", target)
        self.assertNotIn("_path_signature", target)
        self.assertIsNone(target["target"])
        self.assertIsNone(target["healing_target"])

    def test_overlapping_push_replaces_motion_and_extends_only_new_pause_work(self):
        target = air_unit(next_attack=0.75, _wall_next_attack=0.5)
        actors = {target["id"]: target}
        runtime = LinearDisplacement(30, 30)
        trace = []
        runtime.start(target, 0, (1, 0), self.model(), "first", trace)
        runtime.advance(actors, 0, 0.5, trace)
        self.assertEqual(target["x"], 10)
        runtime.start(target, 0.5, (-1, 0), self.model(), "second", trace)
        self.assertEqual(target["_displacement_pause_until"], 2)
        self.assertEqual(target["next_attack"], 2.75)
        self.assertEqual(target["_wall_next_attack"], 2.5)
        self.assertTrue(events(trace, "displacement_start")[-1]["replaced_motion"])
        runtime.advance(actors, 0.5, 1, trace)
        self.assertEqual(target["x"], 6)
        self.assertEqual(target["frozen_until"], 0)

    def test_shorter_replacement_keeps_longer_existing_pause(self):
        target = air_unit(next_attack=0.75)
        actors = {target["id"]: target}
        runtime = LinearDisplacement(30, 30)
        runtime.start(target, 0, (1, 0), self.model(recovery_seconds=5), "first", [])
        runtime.advance(actors, 0, 0.5, [])
        runtime.start(target, 0.5, (-1, 0), self.model(), "second", [])
        self.assertEqual(target["_displacement_pause_until"], 6)
        self.assertEqual(target["next_attack"], 6.75)

    def test_recipient_death_cancels_remaining_motion_and_pause(self):
        target = air_unit()
        actors = {target["id"]: target}
        runtime = LinearDisplacement(30, 30)
        trace = []
        runtime.start(target, 0, (1, 0), self.model(), "sweeper", trace)
        runtime.advance(actors, 0, 0.5, trace)
        target["hp"] = 0
        runtime.advance(actors, 0.5, 0.5, trace)
        self.assertEqual(target["x"], 10)
        self.assertEqual(target["_displacement_pause_until"], 0)
        self.assertEqual(runtime.motions, {})
        self.assertEqual(
            events(trace, "displacement_cancel")[0]["reason"], "recipient_inactive"
        )


class SweeperCrossingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def runtime(self, target, **parameters):
        instance = sweeper_instance(sweeper_parameters=sweeper_parameters(**parameters))
        source = compiled_sweeper(self.catalog, instance)
        actors = {source["id"]: source, target["id"]: target}
        return actors, SweeperCombat(actors, 40, 40)

    def test_outer_range_entry_is_exact_and_uses_supplied_forced_speed(self):
        target = air_unit(x=25)
        actors, runtime = self.runtime(target)
        self.assertAlmostEqual(
            runtime.first_crossing_delay(target, [(10, 5)], 0, 10, 2), 2.5
        )
        self.assertAlmostEqual(
            runtime.first_crossing_delay(target, [(10, 5)], 0, 10, 5), 1
        )
        actors["sweeper"]["next_attack"] = 5
        self.assertIsNone(runtime.first_crossing_delay(target, [(10, 5)], 0, 10, 2))

    def test_inner_dead_zone_departure_is_exact(self):
        target = air_unit(x=5.5)
        _, runtime = self.runtime(target)
        self.assertAlmostEqual(
            runtime.first_crossing_delay(target, [(10, 5)], 0, 10, 2), 0.25
        )

    def test_cone_edge_entry_and_polyline_path_length_are_exact(self):
        angle = radians(52.5)
        edge_y = 5 + 3 * sin(angle) / cos(angle)
        target = air_unit(x=8, y=12)
        _, runtime = self.runtime(target)
        expected = (12 - edge_y) / 2
        delay = runtime.first_crossing_delay(target, [(8, 5)], 0, 10, 2)
        self.assertAlmostEqual(delay, expected)
        target = air_unit(x=25, y=5)
        _, runtime = self.runtime(target)
        delay = runtime.first_crossing_delay(
            target, [(25, 5), (23, 5), (10, 5)], 0, 10, 2
        )
        self.assertAlmostEqual(delay, 2.5)

    def test_dead_frozen_wrong_layer_and_zero_speed_do_not_schedule_acquisition(self):
        target = air_unit(x=25)
        actors, runtime = self.runtime(target)
        actors["sweeper"]["frozen_until"] = 10
        self.assertIsNone(runtime.first_crossing_delay(target, [(10, 5)], 0, 10, 2))
        actors["sweeper"]["frozen_until"] = 0
        self.assertIsNone(runtime.first_crossing_delay(target, [(10, 5)], 0, 10, 0))
        target["layer"] = "ground"
        self.assertIsNone(runtime.first_crossing_delay(target, [(10, 5)], 0, 10, 2))
        target["layer"] = "air"
        actors["sweeper"]["hp"] = 0
        self.assertIsNone(runtime.first_crossing_delay(target, [(10, 5)], 0, 10, 2))


class DisplacementClockTests(unittest.TestCase):
    def push(self, runtime, actor, time, distance=4):
        runtime.start(
            actor,
            time,
            (1, 0),
            {
                "push_distance_tiles": distance,
                "push_speed_tiles_per_second": 4,
                "recovery_seconds": 1,
            },
            "sweeper",
            [],
        )

    def freeze(self, actor, time, duration):
        _apply_effects(
            [
                {
                    "id": "freeze-recipient",
                    "kind": "freeze",
                    "targets": [actor["id"]],
                    "duration_seconds": duration,
                }
            ],
            {actor["id"]: actor},
            time,
            [],
        )

    def test_freeze_then_push_extends_only_the_uncovered_pause_tail(self):
        actor = air_unit(next_attack=1, _wall_next_attack=2)
        runtime = LinearDisplacement(30, 30)
        self.freeze(actor, 0, 3)
        self.push(runtime, actor, 2)
        self.assertEqual(actor["frozen_until"], 3)
        self.assertEqual(actor["_displacement_pause_until"], 4)
        self.assertEqual(actor["next_attack"], 5)
        self.assertEqual(actor["_wall_next_attack"], 6)

    def test_push_then_freeze_extends_only_the_uncovered_pause_tail(self):
        actor = air_unit(next_attack=1, _wall_next_attack=2)
        runtime = LinearDisplacement(30, 30)
        self.push(runtime, actor, 0)
        self.freeze(actor, 1, 3)
        self.assertEqual(actor["frozen_until"], 4)
        self.assertEqual(actor["_displacement_pause_until"], 2)
        self.assertEqual(actor["next_attack"], 5)
        self.assertEqual(actor["_wall_next_attack"], 6)

    def test_contained_freeze_adds_no_time_to_longer_displacement_pause(self):
        actor = air_unit(next_attack=1)
        runtime = LinearDisplacement(30, 30)
        self.push(runtime, actor, 0)
        self.freeze(actor, 0.5, 0.5)
        self.assertEqual(actor["next_attack"], 3)
        self.assertEqual(actor["frozen_until"], 1)
        self.assertEqual(actor["_displacement_pause_until"], 2)

    def test_chill_during_displacement_scales_only_attack_work_and_not_forced_speed(
        self,
    ):
        actor = air_unit(next_attack=1, _wall_next_attack=2)
        actors = {actor["id"]: actor}
        runtime = LinearDisplacement(30, 30)
        self.push(runtime, actor, 0)
        statuses = HitStatusCombat(actors)
        statuses.impact(
            {
                "source": "ice",
                "on_hit_status": slow(
                    duration_seconds=0.5,
                    attack_rate_multiplier=0.5,
                    movement_multiplier=0.25,
                ),
            },
            actor,
            actors,
            0.25,
            [],
        )
        statuses.prepare(actors, 0.25, [])
        self.assertEqual(actor["next_attack"], 4)
        self.assertEqual(actor["_wall_next_attack"], 6)
        self.assertEqual(
            runtime.forced_motion(actor, 0.25)["speed_tiles_per_second"], 4
        )
        statuses.prepare(actors, 0.75, [])
        self.assertEqual(actor["next_attack"], 3)
        self.assertEqual(actor["_wall_next_attack"], 4)
        runtime.advance(actors, 0, 1, [])
        self.assertEqual(actor["x"], 12)

    def test_hazard_and_chill_during_pause_compose_without_scaling_pause_duration(self):
        actor = air_unit(next_attack=1, hazard_class="troop")
        actors = {actor["id"]: actor}
        runtime = LinearDisplacement(30, 30)
        self.push(runtime, actor, 0)
        hazards = PulsedHazards(
            actors,
            [hazard(start_seconds=0.25, duration_seconds=0.5, maximum_dps=0)],
        )
        statuses = HitStatusCombat(actors)
        statuses.impact(
            {"source": "ice", "on_hit_status": slow(duration_seconds=1)},
            actor,
            actors,
            0.25,
            [],
        )
        hazards.prepare_status(actors, 0.25, [])
        statuses.prepare(actors, 0.25, [])
        self.assertEqual(actor["next_attack"], 10)
        self.assertEqual(actor["_displacement_pause_until"], 2)
        hazards.prepare_status(actors, 0.75, [])
        self.assertEqual(actor["next_attack"], 6)
        statuses.prepare(actors, 1.25, [])
        self.assertEqual(actor["next_attack"], 3)


if __name__ == "__main__":
    unittest.main()
