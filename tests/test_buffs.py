"""Selected continuous Rage/Haste conventions, independent of game validation."""

import unittest
from copy import deepcopy
from math import hypot
from pathlib import Path

from clashlab.buffs import (
    BUFF_CLASSES,
    BuffCombat,
    compile_buff_spell,
    damage_multiplier,
    healing_multiplier,
    movement_bonus,
)
from clashlab.adapters import compile_entity_scene
from clashlab.buff_rules import RULES, RULESET, SCOPE
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import EPSILON, center, simulate_spatial

from test_classic_integration import classic_instance
from test_full_battle import fixture as full_battle_fixture
from test_healing import healing_field, injured, support_scene
from test_spatial import synthetic_structure, synthetic_unit
from test_valkyrie_integration import building, valkyrie_sector
from test_walls import wall_scene


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "declared-continuous-buff-fixture-not-replay-validated"


def class_scaling():
    return {
        buff_class: {
            "damage_bonus_multiplier": 1,
            "movement_bonus_multiplier": 1,
            "healing_bonus_multiplier": 1,
        }
        for buff_class in BUFF_CLASSES
    }


def buff_parameters(entity="rage-spell"):
    return {
        "source": SOURCE,
        "caster_team": "attack",
        "radius_multiplier": 1,
        "duration_basis": (
            "snapshot_pulse_count_times_interval"
            if entity == "rage-spell"
            else "snapshot_spell_duration"
        ),
        "duration_multiplier": 1,
        "damage_statistic_basis": (
            "snapshot_damage_increase_is_bonus_percent"
            if entity == "rage-spell"
            else "haste_has_no_damage_bonus"
        ),
        "damage_bonus_multiplier": 1,
        "movement_statistic_basis": "snapshot_speed_increase_is_additive_catalog_units",
        "movement_bonus_multiplier": 1,
        "healing_scaling_basis": "damage_bonus_scales_source_healing",
        "membership_policy": "continuous_exact_crossings",
        "exit_linger_seconds": 0.25,
        "field_end_policy": "clear_immediately",
        "class_scaling": class_scaling(),
        "stacking_policy": "strongest_bonus_per_axis",
        "protection_policy": "beneficial_effects_ignore_damage_immunity",
        "source_persistence": "fixed_field_independent_of_caster",
    }


def buff_instance(entity="rage-spell", **changes):
    instance = {
        "id": "test-buff-cast",
        "entity": entity,
        "level": 6 if entity == "rage-spell" else 5,
        "town_hall": 16,
        "time_seconds": 1,
        "x": 5,
        "y": 5,
        "parameters": buff_parameters(entity),
    }
    instance.update(changes)
    return instance


def buff_field(field_id="rage", **changes):
    field = {
        "id": field_id,
        "kind": "area_buff",
        "entity": "rage-spell",
        "source": SOURCE,
        "statistics_source": SOURCE,
        "start_seconds": 0,
        "duration_seconds": 20,
        "area": {
            "x": 5,
            "y": 3,
            "radius": 1,
            "target_team": "attack",
            "target_kinds": ["unit"],
            "target_layers": ["ground", "air"],
        },
        "movement_bonus_tiles_per_second": 3,
        "damage_bonus_fraction": 1.8,
        "healing_bonus_fraction": 1.8,
        **{
            name: value
            for name, value in buff_parameters().items()
            if name
            in {
                "membership_policy",
                "exit_linger_seconds",
                "field_end_policy",
                "class_scaling",
                "stacking_policy",
                "protection_policy",
                "source_persistence",
            }
        },
    }
    field["exit_linger_seconds"] = 0
    field.update(changes)
    return field


def runtime_actor(actor_id="unit", **changes):
    actor = synthetic_unit(actor_id, x=5, y=3, speed=1)
    actor.update(
        hp=100,
        frozen_until=0,
        next_attack=0.75,
        buff_class="troop",
    )
    actor.update(changes)
    return actor


def move_along_route(actor, route, distance):
    position = center(actor)
    remaining = list(route)
    while remaining:
        point = remaining[0]
        length = hypot(point[0] - position[0], point[1] - position[1])
        if length <= distance + EPSILON:
            distance = max(0, distance - length)
            position = point
            remaining.pop(0)
            continue
        fraction = distance / length
        position = tuple(
            position[index] + (point[index] - position[index]) * fraction
            for index in (0, 1)
        )
        break
    actor["x"], actor["y"] = position
    return remaining


def run_motion(actor, field, route, end, maximum_step):
    actors = {actor["id"]: actor}
    runtime = BuffCombat(actors, [field])
    trace = []
    time = 0.0
    iterations = 0
    runtime.prepare(actors, time, trace)
    while time < end - EPSILON:
        iterations += 1
        if iterations > 10000:
            raise AssertionError("Area buff solver failed to make forward progress")
        speed = actor["speed"] + movement_bonus(actor)
        speed *= actor.get("_hazard_movement_multiplier", 1)
        speed *= actor.get("_hit_status_movement_multiplier", 1)
        step = min(maximum_step, end - time)
        boundary = runtime.next_boundary(time)
        if boundary is not None:
            step = min(step, boundary - time)
        crossing = runtime.first_crossing_delay(actor, route, time, step, speed)
        if crossing is not None:
            step = min(step, crossing)
        route = move_along_route(actor, route, speed * step)
        time += step
        runtime.prepare(actors, time, trace)
    return runtime, trace, iterations


def integrated_scene(scene, fields):
    scene.update(
        ruleset=RULESET,
        model_rules=deepcopy(RULES),
        buff_fields=fields,
        traps=[],
        persistent_hazards=[],
        target_scoring={
            "selection": "arrival_time_then_footprint_distance",
            "source": SOURCE,
        },
    )
    scene.setdefault("healing_stacking", {"source": SOURCE, "groups": {}})
    for actor in scene["actors"]:
        if actor["kind"] == "unit":
            actor["buff_class"] = "troop"
            actor.setdefault("healing_class", "troop")
    return scene


def located_field(x, y=3.5, **changes):
    field = buff_field(**changes)
    field["area"].update(x=x, y=y, radius=0.1)
    return field


class BuffAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_rage_level_six_uses_bonus_percentage_and_additive_catalog_speed(self):
        field = compile_buff_spell(buff_instance(), self.catalog, 8)
        self.assertEqual(field["duration_seconds"], 18)
        self.assertEqual(field["area"]["radius"], 5)
        self.assertEqual(field["damage_bonus_fraction"], 1.8)
        self.assertEqual(field["healing_bonus_fraction"], 1.8)
        self.assertEqual(field["movement_bonus_tiles_per_second"], 3.75)
        self.assertEqual(field["entity_adapter"]["housing_space"], 2)
        self.assertEqual(
            field["entity_adapter"]["snapshot_verification"], "unverified_snapshot"
        )

    def test_haste_uses_positive_catalog_duration_and_retains_conflicting_evidence(
        self,
    ):
        field = compile_buff_spell(buff_instance("haste-spell"), self.catalog, 8)
        self.assertEqual(field["duration_seconds"], 30)
        self.assertEqual(field["area"]["radius"], 4)
        self.assertEqual(field["movement_bonus_tiles_per_second"], 6.5)
        self.assertEqual(field["damage_bonus_fraction"], 0)
        self.assertEqual(field["healing_bonus_fraction"], 0)
        self.assertEqual(field["entity_adapter"]["housing_space"], 1)
        evidence = field["entity_adapter"]["duration_evidence"]["excluded_reference"]
        self.assertEqual(evidence["value"], 0)
        self.assertIn("b8f42a707fe92d5293d46088bf536450ae422e7b", evidence["source"])

    def test_town_hall_caps_and_positive_conversion_are_required(self):
        for instance in (
            buff_instance(level=7),
            buff_instance(town_hall=6),
            buff_instance("haste-spell", level=6),
        ):
            with self.subTest(instance=instance), self.assertRaises(InputError):
                compile_buff_spell(instance, self.catalog, 8)
        with self.assertRaises(InputError):
            compile_buff_spell(buff_instance(), self.catalog, 0)

    def test_implicit_interpretations_and_incomplete_class_policies_are_rejected(self):
        for key, value in (
            ("membership_policy", "pulse_somehow"),
            ("movement_statistic_basis", "attack_speed_multiplier"),
            ("damage_statistic_basis", "total_damage_percent"),
            ("class_scaling", {"troop": class_scaling()["troop"]}),
        ):
            instance = buff_instance()
            instance["parameters"][key] = value
            with self.subTest(key=key), self.assertRaises(InputError):
                compile_buff_spell(instance, self.catalog, 8)

    def test_class_scaling_and_statistic_choices_are_copied_into_provenance(self):
        instance = buff_instance()
        instance["parameters"]["class_scaling"]["hero"] = {
            "damage_bonus_multiplier": 0.5,
            "movement_bonus_multiplier": 0.5,
            "healing_bonus_multiplier": 0.25,
        }
        field = compile_buff_spell(instance, self.catalog, 8)
        instance["parameters"]["class_scaling"]["hero"] = None
        self.assertEqual(field["class_scaling"]["hero"]["damage_bonus_multiplier"], 0.5)
        self.assertEqual(
            field["entity_adapter"]["parameters"]["class_scaling"],
            field["class_scaling"],
        )
        self.assertEqual(field["exit_linger_seconds"], 0.25)


class BuffRuntimeTests(unittest.TestCase):
    def test_repeated_preparation_does_not_mutate_base_stats_or_attack_clocks(self):
        actor = runtime_actor()
        actors = {actor["id"]: actor}
        runtime = BuffCombat(actors, [buff_field()])
        trace = []
        for index in range(100):
            runtime.prepare(actors, index / 100, trace)
        self.assertEqual(actor["damage"], 100)
        self.assertEqual(actor["speed"], 1)
        self.assertEqual(actor["attack_interval_seconds"], 1)
        self.assertEqual(actor["next_attack"], 0.75)
        self.assertEqual(damage_multiplier(actor), 2.8)
        self.assertEqual(healing_multiplier(actor), 2.8)
        self.assertEqual(movement_bonus(actor), 3)
        self.assertEqual(
            len([event for event in trace if event["event"] == "buff_status_change"]),
            1,
        )

    def test_strongest_axis_is_selected_separately_and_weaker_field_survives(self):
        actor = runtime_actor()
        actors = {actor["id"]: actor}
        rage = buff_field(duration_seconds=2)
        weak = buff_field(
            "weak-rage", damage_bonus_fraction=0.5, healing_bonus_fraction=0.5
        )
        haste = buff_field(
            "haste",
            entity="haste-spell",
            damage_bonus_fraction=0,
            healing_bonus_fraction=0,
            movement_bonus_tiles_per_second=6,
            duration_seconds=1,
        )
        runtime = BuffCombat(actors, [weak, haste, rage])
        runtime.prepare(actors, 0, [])
        self.assertEqual(movement_bonus(actor), 6)
        self.assertEqual(damage_multiplier(actor), 2.8)
        runtime.prepare(actors, 1, [])
        self.assertEqual(movement_bonus(actor), 3)
        self.assertEqual(damage_multiplier(actor), 2.8)
        runtime.prepare(actors, 2, [])
        self.assertEqual(damage_multiplier(actor), 1.5)
        self.assertEqual(healing_multiplier(actor), 1.5)
        self.assertEqual(actor["_buff_fields"], ["weak-rage"])

    def test_class_scaling_air_ground_hostiles_and_immune_recipients(self):
        actors = {
            "troop": runtime_actor("troop"),
            "hero": runtime_actor("hero", buff_class="hero", protected_until=10),
            "pet": runtime_actor("pet", buff_class="pet", layer="air"),
            "siege": runtime_actor("siege", buff_class="siege"),
            "other": runtime_actor("other", buff_class="other"),
            "enemy": runtime_actor("enemy", team="defense"),
        }
        field = buff_field()
        field["class_scaling"]["hero"] = {
            "damage_bonus_multiplier": 0.5,
            "movement_bonus_multiplier": 0.5,
            "healing_bonus_multiplier": 0.25,
        }
        field["class_scaling"]["siege"] = None
        field["class_scaling"]["other"] = None
        runtime = BuffCombat(actors, [field])
        runtime.prepare(actors, 0, [])
        self.assertEqual(damage_multiplier(actors["troop"]), 2.8)
        self.assertEqual(damage_multiplier(actors["hero"]), 1.9)
        self.assertEqual(healing_multiplier(actors["hero"]), 1.45)
        self.assertEqual(movement_bonus(actors["hero"]), 1.5)
        self.assertEqual(movement_bonus(actors["pet"]), 3)
        for actor_id in ("siege", "other", "enemy"):
            self.assertEqual(damage_multiplier(actors[actor_id]), 1)
            self.assertEqual(movement_bonus(actors[actor_id]), 0)

    def test_delayed_cast_spawn_and_dead_units_receive_no_early_or_late_effect(self):
        actors = {
            "live": runtime_actor("live"),
            "later": runtime_actor("later", spawn_seconds=2),
            "reserve": runtime_actor("reserve", spawn_seconds="controlled"),
            "dead": runtime_actor("dead", hp=0),
        }
        runtime = BuffCombat(actors, [buff_field(start_seconds=1)])
        runtime.prepare(actors, 0, [])
        self.assertTrue(all(movement_bonus(actor) == 0 for actor in actors.values()))
        self.assertEqual(runtime.next_boundary(0), 1)
        runtime.prepare(actors, 1, [])
        self.assertEqual(movement_bonus(actors["live"]), 3)
        self.assertEqual(movement_bonus(actors["later"]), 0)
        actors["live"]["hp"] = 0
        runtime.prepare(actors, 2, [])
        self.assertEqual(movement_bonus(actors["live"]), 0)
        self.assertEqual(movement_bonus(actors["later"]), 3)
        self.assertEqual(movement_bonus(actors["reserve"]), 0)
        self.assertEqual(movement_bonus(actors["dead"]), 0)

    def test_exit_linger_expires_and_reentry_resets_it_without_extra_stacking(self):
        actor = runtime_actor()
        actors = {actor["id"]: actor}
        runtime = BuffCombat(actors, [buff_field(exit_linger_seconds=0.5)])
        runtime.prepare(actors, 0, [])
        actor["x"] = 7
        runtime.prepare(actors, 1, [])
        self.assertEqual(damage_multiplier(actor), 2.8)
        self.assertEqual(runtime.next_boundary(1), 1.5)
        actor["x"] = 5
        runtime.prepare(actors, 1.25, [])
        self.assertEqual(runtime.result()["lingering_exposures"], [])
        actor["x"] = 7
        runtime.prepare(actors, 2, [])
        runtime.prepare(actors, 2.5, [])
        self.assertEqual(damage_multiplier(actor), 1)
        self.assertEqual(runtime.result()["lingering_exposures"], [])

    def test_field_end_policy_selects_clear_or_final_linger(self):
        for policy, expected in (
            ("clear_immediately", 1),
            ("linger_from_field_end", 2.8),
        ):
            with self.subTest(policy=policy):
                actor = runtime_actor()
                actors = {actor["id"]: actor}
                field = buff_field(
                    duration_seconds=1,
                    exit_linger_seconds=0.5,
                    field_end_policy=policy,
                )
                runtime = BuffCombat(actors, [field])
                trace = []
                runtime.prepare(actors, 0, trace)
                runtime.prepare(actors, 1, trace)
                self.assertEqual(damage_multiplier(actor), expected)
                runtime.prepare(actors, 1.5, trace)
                self.assertEqual(damage_multiplier(actor), 1)
                self.assertEqual(runtime.result()["expired"], ["rage"])

    def test_caster_absence_does_not_delete_field_and_death_clears_linger(self):
        actor = runtime_actor()
        actors = {actor["id"]: actor}
        runtime = BuffCombat(actors, [buff_field(exit_linger_seconds=5)])
        runtime.prepare(actors, 0, [])
        actor["x"] = 7
        runtime.prepare(actors, 1, [])
        actor["hp"] = 0
        runtime.prepare(actors, 2, [])
        self.assertEqual(damage_multiplier(actor), 1)
        self.assertEqual(runtime.result()["lingering_exposures"], [])
        self.assertIn("rage", runtime.result()["fields"])

    def test_dynamic_cast_rejects_duplicate_or_retroactive_execution(self):
        actor = runtime_actor()
        actors = {actor["id"]: actor}
        runtime = BuffCombat(actors, [])
        runtime.prepare(actors, 2, [])
        with self.assertRaisesRegex(InputError, "retroactively"):
            runtime.schedule(buff_field(start_seconds=1), actors)
        runtime.schedule(buff_field(start_seconds=2), actors)
        runtime.prepare(actors, 2, [])
        self.assertEqual(damage_multiplier(actor), 2.8)
        with self.assertRaisesRegex(InputError, "only once"):
            runtime.schedule(buff_field(start_seconds=2), actors)

    def test_missing_recipient_class_or_haste_damage_is_rejected(self):
        actor = runtime_actor()
        actor.pop("buff_class")
        with self.assertRaisesRegex(InputError, "buff_class"):
            BuffCombat({actor["id"]: actor}, [buff_field()])
        with self.assertRaisesRegex(InputError, "only supply movement"):
            BuffCombat({}, [buff_field(entity="haste-spell")])


class BuffCrossingTests(unittest.TestCase):
    def test_exact_enter_exit_and_linger_match_fine_steps(self):
        for linger, expected_x in ((0, 8), (0.5, 9.5)):
            results = []
            for step in (6, 0.037):
                actor = runtime_actor(x=0.5)
                _, trace, _ = run_motion(
                    actor,
                    buff_field(exit_linger_seconds=linger),
                    [(20, 3)],
                    6,
                    step,
                )
                self.assertAlmostEqual(actor["x"], expected_x)
                memberships = [
                    event for event in trace if event["event"] == "buff_membership"
                ]
                self.assertEqual(
                    [event["inside"] for event in memberships], [True, False]
                )
                self.assertAlmostEqual(memberships[0]["time_seconds"], 3.5)
                self.assertAlmostEqual(memberships[1]["time_seconds"], 4)
                results.append(actor["x"])
            self.assertAlmostEqual(*results)

    def test_additive_bonus_changes_different_base_speeds_by_same_amount(self):
        for base_speed in (1, 3):
            actor = runtime_actor(speed=base_speed)
            _, _, _ = run_motion(actor, buff_field(), [(20, 3)], 0.1, 0.1)
            self.assertAlmostEqual(actor["x"], 5 + (base_speed + 3) * 0.1)

    def test_polyline_entry_uses_path_distance_and_updated_speed_for_exit(self):
        actor = runtime_actor(x=1, y=1)
        actors = {actor["id"]: actor}
        field = buff_field()
        field["area"]["x"] = 4
        runtime = BuffCombat(actors, [field])
        runtime.prepare(actors, 0, [])
        route = [(1, 1), (4, 1), (4, 6)]
        delay = runtime.first_crossing_delay(actor, route, 0, 10, 1)
        self.assertAlmostEqual(delay, 4)
        route = move_along_route(actor, route, delay)
        runtime.prepare(actors, delay, [])
        self.assertEqual(movement_bonus(actor), 3)
        self.assertAlmostEqual(
            runtime.first_crossing_delay(actor, route, delay, 10, 4), 0.5
        )

    def test_tangent_contact_does_not_grant_or_linger_a_buff(self):
        actor = runtime_actor(x=0, y=2)
        _, trace, iterations = run_motion(
            actor, buff_field(exit_linger_seconds=1), [(10, 2)], 10, 10
        )
        self.assertEqual(actor["x"], 10)
        self.assertEqual(movement_bonus(actor), 0)
        self.assertFalse(any(event["event"] == "buff_membership" for event in trace))
        self.assertLess(iterations, 5)

    def test_polyline_vertex_touch_and_retreat_does_not_grant_linger(self):
        for step in (10, 0.037):
            actor = runtime_actor(x=1, y=1)
            field = buff_field(exit_linger_seconds=1)
            field["area"]["x"] = 4
            _, trace, _ = run_motion(actor, field, [(4, 2), (4, 2), (1, 1)], 10, step)
            self.assertEqual(movement_bonus(actor), 0)
            self.assertFalse(
                any(event["event"] == "buff_membership" for event in trace)
            )

    def test_starting_on_outward_boundary_makes_positive_progress(self):
        actor = runtime_actor(x=6)
        _, trace, iterations = run_motion(actor, buff_field(), [(20, 3)], 1, 1)
        self.assertAlmostEqual(actor["x"], 7)
        self.assertLess(iterations, 5)
        changes = [event for event in trace if event["event"] == "buff_membership"]
        self.assertEqual([event["inside"] for event in changes], [True, False])

    def test_edge_reversal_can_reenter_after_exiting(self):
        actor = runtime_actor()
        actors = {actor["id"]: actor}
        runtime = BuffCombat(actors, [buff_field()])
        runtime.prepare(actors, 0, [])
        exit_delay = runtime.first_crossing_delay(actor, [(7, 3)], 0, 1, 4)
        actor["x"] = 6
        runtime.prepare(actors, exit_delay, [])
        self.assertEqual(movement_bonus(actor), 0)
        entry_delay = runtime.first_crossing_delay(actor, [(5, 3)], exit_delay, 1, 1)
        self.assertGreater(entry_delay, EPSILON)
        move_along_route(actor, [(5, 3)], entry_delay)
        runtime.prepare(actors, exit_delay + entry_delay, [])
        self.assertEqual(movement_bonus(actor), 3)

    def test_poison_slow_composes_after_bonus_and_freeze_blocks_crossing(self):
        actor = runtime_actor(x=0.5, _hazard_movement_multiplier=0.5)
        _, trace, _ = run_motion(actor, buff_field(), [(20, 3)], 9, 9)
        events = [event for event in trace if event["event"] == "buff_membership"]
        self.assertAlmostEqual(events[0]["time_seconds"], 7)
        self.assertAlmostEqual(events[1]["time_seconds"], 8)
        self.assertAlmostEqual(actor["x"], 6.5)
        actor["frozen_until"] = 10
        runtime = BuffCombat({actor["id"]: actor}, [buff_field()])
        runtime.prepare({actor["id"]: actor}, 9, [])
        self.assertIsNone(runtime.first_crossing_delay(actor, [(5, 3)], 9, 1, 0.5))

    def test_zero_length_route_and_stationary_unit_have_no_crossing(self):
        actor = runtime_actor()
        runtime = BuffCombat({actor["id"]: actor}, [buff_field()])
        runtime.prepare({actor["id"]: actor}, 0, [])
        self.assertIsNone(runtime.first_crossing_delay(actor, [(5, 3)], 0, 10, 4))
        self.assertIsNone(runtime.first_crossing_delay(actor, [(20, 3)], 0, 10, 0))


class BuffIntegrationTests(unittest.TestCase):
    def test_rage_changes_weapon_damage_without_changing_attack_cadence(self):
        scene = support_scene(
            actors=[
                synthetic_unit(x=6.5, damage=10, range=1),
                synthetic_structure(hitpoints=10000),
            ],
            duration_seconds=2.1,
        )
        result = simulate_spatial(
            integrated_scene(scene, [located_field(6.5, duration_seconds=0.5)])
        )
        self.assertAlmostEqual(result["actors"]["tower"]["hp"], 10000 - 28 - 10 - 10)
        launches = [
            event["time_seconds"]
            for event in result["trace"]
            if event.get("event") == "projectile_launch"
            and event["source"] == "attacker"
        ]
        self.assertEqual(launches, [0, 1, 2])

    def test_launched_rage_damage_survives_field_expiry_and_source_death(self):
        scene = support_scene(
            actors=[
                synthetic_unit(x=6.5, attack_interval_seconds=100),
                synthetic_structure(hitpoints=1000),
            ],
            effects=[injured(100, time=0.5)],
            duration_seconds=1.1,
        )
        scene["actors"][0]["attack_model"]["projectile"] = {
            "timing": "launch_distance_delay",
            "speed_tiles_per_second": 1,
            "destination": "locked_actor_center_at_impact",
            "hit_radius": 0,
        }
        result = simulate_spatial(
            integrated_scene(scene, [located_field(6.5, duration_seconds=0.25)])
        )
        self.assertEqual(result["actors"]["attacker"]["hp"], 0)
        self.assertAlmostEqual(result["actors"]["tower"]["hp"], 720)

    def test_healing_bonus_is_captured_on_emitter_and_never_on_recipient(self):
        for field_x, expected_hp in ((5.5, 96), (6.5, 60)):
            with self.subTest(field_x=field_x):
                scene = support_scene(effects=[injured()], duration_seconds=1.1)
                healer = scene["actors"][1]
                healer["attack_interval_seconds"] = 100
                healer["healing_model"]["projectile"] = {
                    "timing": "launch_distance_delay",
                    "speed_tiles_per_second": 1,
                    "destination": "locked_actor_center_at_impact",
                    "hit_radius": 0,
                }
                result = simulate_spatial(
                    integrated_scene(
                        scene, [located_field(field_x, duration_seconds=0.25)]
                    )
                )
                self.assertAlmostEqual(result["actors"]["attacker"]["hp"], expected_hp)

    def test_rage_does_not_multiply_healing_spell_pulses(self):
        scene = support_scene(
            actors=[
                synthetic_unit(x=6.5, damage=1, range=1),
                synthetic_structure(hitpoints=1000),
            ],
            effects=[injured(), healing_field(pulse_count=1)],
        )
        result = simulate_spatial(integrated_scene(scene, [located_field(6.5)]))
        self.assertEqual(result["actors"]["attacker"]["hp"], 60)

    def test_spatial_solver_splits_motion_at_exact_entry_and_exit(self):
        positions = []
        for step in (6, 0.037):
            scene = support_scene(
                actors=[
                    synthetic_unit(
                        x=0.5,
                        speed=1,
                        damage=1,
                        layer="air",
                        movement="air",
                        range=0.1,
                    ),
                    synthetic_structure(x=12, hitpoints=1000),
                ],
                width=20,
                duration_seconds=6,
                maximum_step_seconds=step,
                recording_interval_seconds=6,
            )
            field = buff_field()
            field["area"]["y"] = 3.5
            result = simulate_spatial(integrated_scene(scene, [field]))
            positions.append(result["actors"]["attacker"]["x"])
        self.assertAlmostEqual(positions[0], 8)
        self.assertAlmostEqual(*positions)

    def test_wall_hits_capture_rage_bonus_without_changing_wall_cooldown(self):
        scene = integrated_scene(
            wall_scene(wall_hp=500, duration_seconds=0.41),
            [located_field(3.5)],
        )
        result = simulate_spatial(scene)
        self.assertAlmostEqual(result["actors"]["wall-3"]["death_time"], 0.4)
        impacts = [
            event for event in result["trace"] if event.get("event") == "wall_impact"
        ]
        self.assertEqual(len(impacts), 2)
        self.assertAlmostEqual(impacts[0]["time_seconds"], 0)
        self.assertAlmostEqual(impacts[1]["time_seconds"], 0.4)
        self.assertTrue(all(abs(event["damage"] - 280) < EPSILON for event in impacts))

    def test_catalog_spell_and_troop_compile_into_real_buffed_weapon_damage(self):
        catalog = Catalog.load(ROOT / "data")
        instance = buff_instance(time_seconds=0, x=4.5, y=5.5)
        specification = valkyrie_sector(
            catalog,
            [classic_instance("giant"), building("storage", 5)],
            scope=SCOPE,
            model_rules=deepcopy(RULES),
            buff_spells=[instance],
        )
        compiled = compile_entity_scene(specification, catalog)
        self.assertEqual(compiled["scene"]["actors"][0]["buff_class"], "troop")
        result = simulate_spatial(compiled["scene"])
        self.assertAlmostEqual(result["actors"]["storage"]["hp"], 4050 - 188 * 2.8)
        self.assertFalse(result["full_game_prediction"])


class BuffFullBattleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def battle(self, casts=None):
        specification, account, army, layout = full_battle_fixture(self.catalog)
        scene = specification["entity_scene"]
        scene.update(scope=SCOPE, model_rules=deepcopy(RULES), buff_spells=casts or [])
        account["levels"].update({"rage-spell": 6, "haste-spell": 5})
        army["spells"] = [
            {"id": "rage-spell", "level": 6, "count": 2},
            {"id": "haste-spell", "level": 5, "count": 1},
        ]
        return specification, account, army, layout

    def test_paid_rage_and_haste_share_inventory_and_late_cast_remains_unspent(self):
        casts = [
            buff_instance(id="paid-rage", time_seconds=0, x=9.5, y=5.5),
            buff_instance(
                "haste-spell", id="later-haste", time_seconds=4, x=9.5, y=5.5
            ),
        ]
        inputs = self.battle(casts)
        untouched = deepcopy(inputs)
        result = simulate_full_battle(*inputs, self.catalog)
        self.assertEqual(inputs, untouched)
        self.assertEqual(result["validation"]["army"]["used"]["spell_housing"], 5)
        slots = result["resource_use"]["spell_slots"]
        self.assertEqual(len(slots), 3)
        self.assertEqual(sum(slot["spent"] for slot in slots), 1)
        spent = next(slot for slot in slots if slot["spent"])
        self.assertEqual(spent["cast"]["cast_id"], "paid-rage")
        self.assertEqual(result["combat"]["buffs"]["started"], ["paid-rage"])
        self.assertFalse(result["full_game_prediction"])

    def test_owned_but_uncast_buffs_do_not_create_free_effects(self):
        result = simulate_full_battle(*self.battle(), self.catalog)
        self.assertEqual(result["combat"]["buffs"]["fields"], {})
        self.assertEqual(result["combat"]["buffs"]["started"], [])
        self.assertTrue(
            all(not slot["spent"] for slot in result["resource_use"]["spell_slots"])
        )
        self.assertAlmostEqual(result["outcome"]["completion_time_seconds"], 1.8)

    def test_casts_cannot_exceed_owned_identity_level_or_count(self):
        for failure in ("missing_inventory", "wrong_level", "excess_count"):
            with self.subTest(failure=failure):
                inputs = self.battle([buff_instance(time_seconds=0)])
                specification, _, army, _ = inputs
                army["spells"] = [{"id": "rage-spell", "level": 6, "count": 1}]
                if failure == "missing_inventory":
                    army["spells"] = []
                elif failure == "wrong_level":
                    specification["entity_scene"]["buff_spells"][0]["level"] = 5
                else:
                    specification["entity_scene"]["buff_spells"].append(
                        buff_instance(id="extra-rage", time_seconds=1)
                    )
                with self.assertRaisesRegex(InputError, "exceeds the declared army"):
                    compile_full_battle(*inputs, self.catalog)

    def test_raw_fields_cannot_bypass_catalog_spell_inventory(self):
        inputs = self.battle()
        inputs[0]["entity_scene"]["buff_fields"] = [buff_field()]
        with self.assertRaisesRegex(InputError, "unknown|Unsupported|unsupported"):
            compile_full_battle(*inputs, self.catalog)

    def test_overfilled_spell_housing_is_rejected_before_execution(self):
        inputs = self.battle()
        inputs[2]["spells"] = [{"id": "rage-spell", "level": 6, "count": 6}]
        with self.assertRaises(InputError):
            compile_full_battle(*inputs, self.catalog)


if __name__ == "__main__":
    unittest.main()
