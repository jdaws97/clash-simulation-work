"""Conditional Spring Trap removal, reworked damage and displacement contracts."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.hit_status import RULES as STATUS_RULES, RULESET as STATUS_RULESET
from clashlab.hit_status import compile_ice_golem
from clashlab.spatial import _load_actors, simulate_spatial
from clashlab.traps import (
    SUPPORTED_TRAP_IDS,
    TrapCombat,
    compile_spring_trap,
    compile_trap,
)

from test_deaths import damage, death_model
from test_hit_status import ice_instance
from test_spatial import synthetic_structure, synthetic_unit
from test_traps import trap_instance, trap_scene


SOURCE = "synthetic-spring-policies-not-current-game-calibration"
ROOT = Path(__file__).resolve().parents[1]


def spring_instance(**changes):
    instance = {
        "id": "spring",
        "entity": "spring-trap",
        "level": 5,
        "town_hall": 16,
        "team": "defense",
        "x": 4,
        "y": 3,
        "parameters": {
            "source": SOURCE,
            "arming_seconds": 0,
            "delay_seconds": 0,
            "trigger_radius_multiplier": 1,
            "effect_radius_tiles": 1,
            "allocation_policy": "highest_housing_single",
            "protection_policy": "damage_immunity_does_not_block_removal",
            "oversized_policy": "damage_and_push",
            "damage_multiplier": 1,
            "non_troop_policies": {
                "hero": None,
                "siege": None,
                "pet": None,
                "other": None,
            },
            "push": {
                "distance_tiles": 1,
                "pause_seconds": 1,
                "direction": "away_from_trap",
                "coincident_direction": [-1, 0],
                "collision_policy": "cancel_if_segment_blocked_or_outside",
                "protection_policy": "damage_immunity_blocks_push",
            },
            "damage_lockout_seconds": 0.5,
            "lethal_damage_policy": "eject_without_death_effects",
            "excluded_trigger_entities": [],
            "excluded_effect_entities": [],
        },
    }
    instance.update(changes)
    return instance


def spring_unit(actor_id="attacker", **changes):
    actor = synthetic_unit(
        actor_id,
        x=4.5,
        spring_class="troop",
        housing_space=1,
        target_priorities=[],
    )
    actor.update(changes)
    return actor


def protection(actor_id="attacker", duration=5):
    return {
        "id": f"protect-{actor_id}",
        "kind": "invulnerability",
        "targets": [actor_id],
        "time_seconds": 0,
        "duration_seconds": duration,
    }


class SpringTrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def model(self, parameters=None, **changes):
        instance = spring_instance()
        instance["parameters"].update(parameters or {})
        model = compile_spring_trap(instance, self.catalog)
        model.update(changes)
        return model

    def simulate(self, model=None, units=None, effects=None, **changes):
        if model is None:
            model = self.model()
        if units is None:
            units = [spring_unit()]
        changes.setdefault("duration_seconds", 3)
        return simulate_spatial(
            trap_scene(
                model,
                [*units, synthetic_structure()],
                effects,
                **changes,
            )
        )

    def runtime(self, model, units):
        scene = trap_scene(model, [*units, synthetic_structure()])
        actors = _load_actors(scene, 9, 7)
        return TrapCombat([model], actors, 9, 7), actors

    def test_general_compiler_preserves_existing_damage_models(self):
        from clashlab.traps import compile_damage_trap

        self.assertIn("spring-trap", SUPPORTED_TRAP_IDS)
        instance = trap_instance()
        self.assertEqual(
            compile_trap(instance, self.catalog),
            compile_damage_trap(instance, self.catalog),
        )
        model = compile_trap(spring_instance(), self.catalog)
        self.assertEqual(model["spring_capacity"], 18)
        self.assertEqual(model["damage"], 400)
        self.assertIn("spring-trap", model["statistics_source"])

    def test_capacity_boundary_is_removal_without_hp_death_or_damage(self):
        result = self.simulate(units=[spring_unit(housing_space=18)])
        actor = result["actors"]["attacker"]
        self.assertEqual(actor["hp"], 0)
        self.assertIsNone(actor["death_time"])
        self.assertEqual(actor["removal"]["reason"], "spring_capacity")
        self.assertEqual(actor["removal"]["hitpoints_before_removal"], 100)
        self.assertEqual(result["traps"]["resolved"], ["spring"])
        self.assertNotIn("spring", result["actors"])
        self.assertFalse(
            any(frame["actors"]["attacker"]["active"] for frame in result["frames"])
        )

    def test_current_policy_selects_only_largest_nearby_unit(self):
        units = [
            spring_unit("small", housing_space=5),
            spring_unit("large", housing_space=10, x=5),
        ]
        result = self.simulate(units=units)
        self.assertEqual(result["actors"]["small"]["hp"], 100)
        self.assertEqual(result["actors"]["large"]["hp"], 0)

    def test_group_capacity_allocates_deterministically_and_skips_unfit(self):
        model = self.model(
            parameters={
                "allocation_policy": "largest_housing_then_distance_then_id_skip_unfit",
                "oversized_policy": "ignore_without_trigger_or_damage",
            },
            spring_capacity=10,
        )
        units = [
            spring_unit("b-six", housing_space=6),
            spring_unit("a-six", housing_space=6),
            spring_unit("four", housing_space=4),
        ]
        for ordered in (units, list(reversed(units))):
            result = self.simulate(model, ordered)
            resolution = next(
                event
                for event in result["trace"]
                if event.get("event") == "spring_resolution"
            )
            self.assertEqual(resolution["removed_targets"], ["a-six", "four"])
            self.assertEqual(resolution["skipped_capacity_targets"], ["b-six"])
            self.assertEqual(resolution["capacity_used"], 10)
            self.assertEqual(result["actors"]["b-six"]["hp"], 100)

    def test_single_target_ties_use_distance_then_id(self):
        units = [
            spring_unit("far", housing_space=5, x=5),
            spring_unit("b", housing_space=5),
            spring_unit("a", housing_space=5),
        ]
        result = self.simulate(units=units)
        self.assertEqual(result["actors"]["a"]["hp"], 0)
        self.assertEqual(result["actors"]["b"]["hp"], 100)
        self.assertEqual(result["actors"]["far"]["hp"], 100)

    def test_air_friendlies_and_explicitly_excluded_classes_do_not_trigger(self):
        units = [
            spring_unit("air", layer="air", movement="air"),
            spring_unit("friendly", team="defense"),
            *[
                spring_unit(category, spring_class=category)
                for category in ("hero", "siege", "pet", "other")
            ],
        ]
        result = self.simulate(units=units)
        self.assertEqual(result["traps"]["untriggered"], ["spring"])
        self.assertTrue(
            all(result["actors"][unit["id"]]["hp"] == 100 for unit in units)
        )

    def test_explicit_class_damage_cannot_capacity_eject_hero(self):
        model = self.model()
        model["non_troop_policies"]["hero"] = {
            "target_weight": 1,
            "damage_multiplier": 0.5,
            "push": False,
        }
        result = self.simulate(
            model, [spring_unit(spring_class="hero", hitpoints=1000)]
        )
        actor = result["actors"]["attacker"]
        self.assertEqual(actor["hp"], 800)
        self.assertNotIn("removal", actor)
        self.assertEqual(actor["x"], 4.5)
        self.assertEqual(actor["frozen_until"], 0)

    def test_missing_or_invalid_housing_metadata_fails_closed(self):
        for field, value in (
            ("housing_space", 0),
            ("housing_space", 1.5),
            ("spring_class", "unknown"),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(InputError):
                    self.simulate(units=[spring_unit(**{field: value})])
        actor = spring_unit()
        actor.pop("housing_space")
        with self.assertRaisesRegex(InputError, "housing_space"):
            self.simulate(units=[actor])

    def test_legacy_oversized_units_do_not_trigger_or_take_damage(self):
        model = self.model(
            parameters={"oversized_policy": "ignore_without_trigger_or_damage"}
        )
        result = self.simulate(model, [spring_unit(housing_space=19)])
        self.assertEqual(result["traps"]["untriggered"], ["spring"])
        self.assertEqual(result["actors"]["attacker"]["hp"], 100)

    def test_protection_policy_is_explicit_and_always_consumes_trigger(self):
        for blocks in (True, False):
            model = self.model(
                parameters={
                    "protection_policy": (
                        "damage_immunity_blocks_removal"
                        if blocks
                        else "damage_immunity_does_not_block_removal"
                    )
                }
            )
            result = self.simulate(model, effects=[protection(duration=1)])
            self.assertEqual(result["actors"]["attacker"]["hp"], 100 if blocks else 0)
            self.assertEqual(len(result["traps"]["triggered"]), 1)
            self.assertEqual(result["traps"]["resolved"], ["spring"])

    def test_delayed_resolution_reselects_live_nearby_members(self):
        model = self.model(parameters={"delay_seconds": 1})
        units = [
            spring_unit("trigger"),
            spring_unit("late", housing_space=10, spawn_seconds=0.5),
        ]
        result = self.simulate(model, units, effects=[damage("trigger", time=0.2)])
        self.assertEqual(
            result["traps"]["triggered"]["spring"]["trigger_id"], "trigger"
        )
        self.assertEqual(result["actors"]["late"]["removal"]["time_seconds"], 1)

    def test_movement_crossing_does_not_skip_small_spring(self):
        times = []
        for step in (0.01, 1):
            model = self.model(trigger_radius=0.25)
            actor = spring_unit(
                x=0.5, speed=6, first_attack_seconds=100, target_priorities=["defense"]
            )
            result = self.simulate(model, [actor], maximum_step_seconds=step)
            times.append(result["actors"]["attacker"]["removal"]["time_seconds"])
        self.assertAlmostEqual(times[0], 0.625)
        self.assertAlmostEqual(times[1], times[0])

    def test_removed_ice_golem_cannot_attack_heal_or_release_death_freeze(self):
        actor = spring_unit(
            housing_space=15,
            target_priorities=["defense"],
            range=10,
            entity_adapter={"entity": "ice-golem"},
        )
        instance = ice_instance()
        compile_ice_golem(
            actor,
            instance,
            self.catalog.entity("ice-golem"),
            self.catalog.level("ice-golem", 8),
        )
        effects = [
            damage(time=0.2),
            {
                "id": "heal-removed",
                "kind": "heal",
                "targets": ["attacker"],
                "time_seconds": 0.5,
                "amount": 10000,
            },
        ]
        result = self.simulate(
            units=[actor],
            effects=effects,
            ruleset=STATUS_RULESET,
            model_rules=deepcopy(STATUS_RULES),
        )
        self.assertEqual(result["actors"]["attacker"]["hp"], 0)
        self.assertIsNone(result["actors"]["attacker"]["death_time"])
        self.assertEqual(result["death_effects"]["emitted_instances"], [])
        self.assertEqual(result["actors"]["tower"]["hp"], 100)
        self.assertEqual(result["actors"]["tower"]["frozen_until"], 0)
        self.assertFalse(
            any(
                event.get("event") == "projectile_launch"
                and event.get("source") == "attacker"
                for event in result["trace"]
            )
        )

    def test_oversized_root_rider_takes_damage_and_push_then_resumes(self):
        actor = spring_unit(
            housing_space=20, hitpoints=1000, range=10, target_priorities=["defense"]
        )
        result = self.simulate(units=[actor], maximum_step_seconds=1)
        actual = result["actors"]["attacker"]
        self.assertEqual(actual["hp"], 600)
        self.assertEqual(actual["x"], 3.5)
        launches = [
            event["time_seconds"]
            for event in result["trace"]
            if event.get("event") == "projectile_launch"
            and event["source"] == "attacker"
        ]
        self.assertEqual(launches, [1])

    def test_push_collision_cancels_whole_segment_and_keeps_pause(self):
        model = self.model()
        model["push"]["distance_tiles"] = 3
        units = [spring_unit(housing_space=20, hitpoints=1000)]
        runtime, actors = self.runtime(model, units)
        obstacle = deepcopy(actors["tower"])
        obstacle.update(id="blocker", x=2, y=3)
        actors["blocker"] = obstacle
        trace = []
        runtime.update(actors, 0, trace)
        self.assertEqual(actors["attacker"]["x"], 4.5)
        self.assertEqual(actors["attacker"]["frozen_until"], 1)
        event = next(item for item in trace if item.get("event") == "spring_push")
        self.assertTrue(event["displacement_blocked"])

    def test_moving_ground_unit_rebuilds_cached_route_after_successful_push(self):
        for step in (0.01, 1):
            actor = spring_unit(
                x=0.5,
                housing_space=20,
                hitpoints=1000,
                range=0.5,
                target_priorities=["defense"],
            )
            result = self.simulate(
                units=[actor], duration_seconds=5, maximum_step_seconds=step
            )
            push = next(
                event
                for event in result["trace"]
                if event.get("event") == "spring_push"
            )
            self.assertFalse(push["displacement_blocked"])
            self.assertAlmostEqual(push["time_seconds"], 1.5)
            self.assertAlmostEqual(push["from_position"][0], 3.5)
            self.assertAlmostEqual(push["to_position"][0], 2.5)
            self.assertAlmostEqual(result["actors"]["attacker"]["x"], 6.5)
            self.assertAlmostEqual(result["actors"]["tower"]["death_time"], 4.5)

    def test_push_board_boundary_cancels_displacement(self):
        model = self.model(x=0)
        runtime, actors = self.runtime(
            model, [spring_unit(x=0.5, housing_space=20, hitpoints=1000)]
        )
        runtime.update(actors, 0, [])
        self.assertEqual(actors["attacker"]["x"], 0.5)
        self.assertEqual(actors["attacker"]["hp"], 600)

    def test_damage_immunity_and_push_immunity_are_separate(self):
        for blocks in (True, False):
            model = self.model()
            model["push"]["protection_policy"] = (
                "damage_immunity_blocks_push"
                if blocks
                else "damage_immunity_does_not_block_push"
            )
            result = self.simulate(
                model,
                [spring_unit(housing_space=20, hitpoints=1000)],
                effects=[protection()],
            )
            self.assertEqual(result["actors"]["attacker"]["hp"], 1000)
            self.assertEqual(result["actors"]["attacker"]["x"], 4.5 if blocks else 3.5)

    def test_lethal_damage_policy_distinguishes_ejection_and_actual_death(self):
        for actual_death in (True, False):
            model = self.model(
                parameters={
                    "lethal_damage_policy": (
                        "actual_hp_death"
                        if actual_death
                        else "eject_without_death_effects"
                    )
                }
            )
            actor = spring_unit(housing_space=20, death_model=death_model())
            result = self.simulate(model, [actor])
            self.assertEqual(result["actors"]["attacker"]["hp"], 0)
            self.assertEqual(
                result["death_effects"]["emitted_instances"],
                ["attacker"] if actual_death else [],
            )
            self.assertEqual(
                result["actors"]["attacker"]["death_time"], 0 if actual_death else None
            )

    def test_nearby_springs_do_not_stack_damage_within_declared_lockout(self):
        first = self.model(x=3)
        second = self.model(id="spring-second")
        for model in (first, second):
            model["push"]["distance_tiles"] = 0
        result = self.simulate(
            first,
            [spring_unit(x=4, housing_space=20, hitpoints=1000)],
            traps=[first, second],
        )
        self.assertEqual(result["actors"]["attacker"]["hp"], 600)
        self.assertEqual(result["traps"]["resolved"], ["spring", "spring-second"])
        self.assertEqual(
            sum(
                event.get("event") == "spring_damage_suppressed"
                for event in result["trace"]
            ),
            1,
        )

    def test_damage_lockout_expires_at_declared_boundary_across_solver_steps(self):
        first = self.model(x=2, trigger_radius=5, effect_radius_tiles=5)
        second = self.model(
            id="second",
            x=3,
            arming_seconds=0.25,
            trigger_radius=5,
            effect_radius_tiles=5,
        )
        third = self.model(
            id="third", arming_seconds=1, trigger_radius=5, effect_radius_tiles=5
        )
        models = [first, second, third]
        for model in models:
            model["push"]["distance_tiles"] = 0
        for step in (0.01, 1):
            result = self.simulate(
                first,
                [spring_unit(housing_space=20, hitpoints=1000)],
                traps=models,
                maximum_step_seconds=step,
            )
            self.assertEqual(result["actors"]["attacker"]["hp"], 200)
            hits = [
                event["time_seconds"]
                for event in result["trace"]
                if event.get("event") == "spring_damage"
            ]
            self.assertEqual(hits, [0, 1])

    def test_push_pause_does_not_double_count_existing_freeze(self):
        freeze = {
            "id": "freeze",
            "kind": "freeze",
            "time_seconds": 0,
            "targets": ["attacker"],
            "duration_seconds": 2,
        }
        actor = spring_unit(
            housing_space=20,
            hitpoints=1000,
            target_priorities=["defense"],
            range=10,
        )
        result = self.simulate(units=[actor], effects=[freeze])
        launches = [
            event["time_seconds"]
            for event in result["trace"]
            if event.get("event") == "projectile_launch"
            and event["source"] == "attacker"
        ]
        self.assertEqual(launches, [2])

    def test_same_time_bomb_cannot_turn_capacity_ejection_into_death(self):
        bomb = compile_trap(trap_instance(x=3), self.catalog)
        bomb.update(damage=10000, trigger_radius=2, damage_radius=2)
        spring = self.model()
        actor = spring_unit(death_model=death_model())
        result = self.simulate(spring, [actor], traps=[bomb, spring])
        self.assertIsNone(result["actors"]["attacker"]["death_time"])
        self.assertEqual(result["death_effects"]["emitted_instances"], [])
        self.assertEqual(
            result["actors"]["attacker"]["removal"]["reason"], "spring_capacity"
        )

    def test_bad_policies_or_unavailable_levels_are_rejected(self):
        for field in (
            "allocation_policy",
            "protection_policy",
            "oversized_policy",
            "lethal_damage_policy",
        ):
            with self.subTest(field=field):
                with self.assertRaises(InputError):
                    self.model(parameters={field: "implicit"})
        with self.assertRaises(InputError):
            compile_spring_trap(spring_instance(level=13, town_hall=16), self.catalog)
        with self.assertRaises(InputError):
            self.model(parameters={"push": {}})
        with self.assertRaises(InputError):
            self.model(
                parameters={
                    "allocation_policy": "largest_housing_then_distance_then_id_skip_unfit"
                }
            )


if __name__ == "__main__":
    unittest.main()
