"""Aggregate housing, delayed live blasts, and shared finite Giga knockback."""

from pathlib import Path
import unittest

from clashlab.battle_modifiers import apply_battle_modifiers
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.displacements import enqueue_linear_displacement
from clashlab.giga_bombs import GigaBombCombat, POLICIES, compile_giga_bomb
from clashlab.spatial import _apply_health, _load_actors
from clashlab.sweepers import LinearDisplacement

from test_battle_modifiers import modifier_policy
from test_combat import synthetic_pattern
from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "declared-giga-bomb-fixture-not-replay-calibrated"


def response(weight=18, damage=1, push=1):
    return {
        "trigger_weight": weight,
        "damage_multiplier": damage,
        "push_multiplier": push,
    }


def giga_instance(responses=None, **changes):
    instance = {
        "id": "giga",
        "entity": "giga-bomb",
        "level": 3,
        "town_hall": 17,
        "team": "defense",
        "x": 9,
        "y": 9,
        "parameters": {
            **POLICIES,
            "source": SOURCE,
            "arming_seconds": 0,
            "delay_seconds": 0,
            "trigger_radius_multiplier": 1,
            "damage_radius_multiplier": 1,
            "damage_multiplier": 1,
            "trigger_visibility": "ignore_acquisition_visibility",
            "trigger_protection": "protected_units_contribute",
            "push_protection": "damage_immunity_does_not_block_push",
            "push_distance_tiles": 2,
            "push_speed_tiles_per_second": 4,
            "recovery_seconds": 0.2,
            "coincident_direction": [1, 0],
            "unit_responses": (
                responses if responses is not None else {"unit": response()}
            ),
        },
    }
    instance.update(changes)
    return instance


def unit(actor_id="unit", **changes):
    actor = synthetic_unit(
        actor_id,
        x=12,
        y=10,
        hitpoints=5000,
        minimum_range=0,
        attack_model=synthetic_pattern(),
    )
    actor.update(changes)
    return actor


class GigaBombTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.mode_rules = read_json(ROOT / "data" / "mode-rules.json")

    def runtime(self, instance=None, others=None):
        instance = giga_instance() if instance is None else instance
        actors = _load_actors(
            {"actors": others if others is not None else [unit()]}, 30, 30
        )
        motion = LinearDisplacement(30, 30)
        trap = compile_giga_bomb(instance, self.catalog)
        return actors, GigaBombCombat([trap], actors, 30, 30, motion), motion, []

    def test_compiler_uses_catalog_threshold_radii_damage_and_visible_trap_metadata(
        self,
    ):
        trap = compile_giga_bomb(giga_instance(), self.catalog)
        self.assertEqual(
            (
                trap["trigger_housing_space"],
                trap["trigger_radius"],
                trap["damage_radius"],
                trap["damage"],
            ),
            (18, 3.5, 4.5, 1300),
        )
        self.assertEqual(
            (trap["width"], trap["height"], trap["layout_visibility"]),
            (2, 2, "visible"),
        )
        self.assertFalse(trap["counts_for_destruction"])
        self.assertFalse(trap["blocking"])
        self.assertFalse(trap["targetable"])
        with self.assertRaises(InputError):
            compile_giga_bomb(giga_instance(level=4, town_hall=17), self.catalog)
        self.assertEqual(
            compile_giga_bomb(giga_instance(level=4, town_hall=18), self.catalog)[
                "damage"
            ],
            1400,
        )

    def test_aggregate_ground_and_air_weights_trigger_only_at_threshold(self):
        instance = giga_instance({"ground": response(8), "air": response(10)})
        actors, runtime, _, trace = self.runtime(
            instance, [unit("ground"), unit("air", x=20, layer="air", movement="air")]
        )
        self.assertFalse(runtime.update(actors, 0, trace))
        actors["air"]["x"] = 13.5
        damage = runtime.update(actors, 1, trace)
        self.assertEqual(dict(damage), {"air": 1300, "ground": 1300})
        self.assertEqual(runtime.triggered["giga"]["aggregate_trigger_weight"], 18)
        self.assertEqual(
            runtime.triggered["giga"]["trigger_weights"], {"air": 10, "ground": 8}
        )
        self.assertFalse(runtime.update(actors, 1, trace))

    def test_zero_weight_units_can_receive_blast_without_triggering_it(self):
        instance = giga_instance({"summon": response(0), "hero": response(18)})
        actors, runtime, _, trace = self.runtime(
            instance, [unit("summon"), unit("hero", spawn_seconds="controlled")]
        )
        self.assertFalse(runtime.update(actors, 0, trace))
        actors["hero"]["spawn_seconds"] = 1
        damage = runtime.update(actors, 1, trace)
        self.assertEqual(set(damage), {"hero", "summon"})
        self.assertEqual(runtime.triggered["giga"]["trigger_weights"], {"hero": 18})

    def test_response_map_must_include_reserves_generated_actors_and_no_extras(self):
        for responses in (
            {"unit": response()},
            {"unit": response(), "reserve": response(), "unrelated": response()},
        ):
            with (
                self.subTest(responses=responses),
                self.assertRaisesRegex(
                    InputError, "including reserves and generated actors"
                ),
            ):
                self.runtime(
                    giga_instance(responses),
                    [unit(), unit("reserve", spawn_seconds="controlled")],
                )
        instance = giga_instance(
            {"unit": response(), "mirror-copy": response(0), "pet": response(0)}
        )
        actors, runtime, _, _ = self.runtime(
            instance,
            [
                unit(),
                unit("mirror-copy", spawn_seconds="controlled"),
                unit("pet", spawn_seconds="controlled"),
            ],
        )
        self.assertEqual(
            set(runtime.models["giga"]["parameters"]["unit_responses"]), set(actors)
        )

    def test_delayed_blast_uses_live_membership_and_survives_trigger_death(self):
        instance = giga_instance({"trigger": response(), "late": response(0)})
        instance["parameters"]["delay_seconds"] = 1
        actors, runtime, _, trace = self.runtime(
            instance, [unit("trigger"), unit("late", x=20)]
        )
        self.assertFalse(runtime.update(actors, 0, trace))
        self.assertEqual(runtime.next_boundary(0), 1)
        actors["trigger"]["hp"] = 0
        actors["late"]["x"] = 14.5
        damage = runtime.update(actors, 1, trace)
        self.assertEqual(dict(damage), {"late": 1300})
        impact = [event for event in trace if event["event"] == "giga_bomb_impact"][0]
        self.assertEqual(impact["trigger_weights"], {"trigger": 18})
        self.assertEqual(impact["requested_damage"], {"late": 1300})

    def test_arming_delays_trigger_then_reports_pending_explosion(self):
        instance = giga_instance()
        instance["parameters"].update(arming_seconds=2, delay_seconds=0.5)
        actors, runtime, _, trace = self.runtime(instance)
        self.assertFalse(runtime.update(actors, 1, trace))
        self.assertEqual(runtime.next_boundary(1), 2)
        self.assertFalse(runtime.update(actors, 2, trace))
        self.assertEqual(runtime.next_boundary(2), 2.5)
        self.assertEqual(len(runtime.result()["pending_at_horizon"]), 1)

    def test_trigger_visibility_and_protection_are_explicit(self):
        instance = giga_instance()
        instance["parameters"].update(
            trigger_visibility="require_visible_units",
            trigger_protection="protected_units_do_not_contribute",
        )
        actors, runtime, _, trace = self.runtime(instance)
        actors["unit"]["_untargetable_until"] = 1
        actors["unit"]["immune_until"] = 2
        self.assertFalse(runtime.update(actors, 0, trace))
        self.assertFalse(runtime.update(actors, 1, trace))
        self.assertEqual(runtime.update(actors, 2, trace)["unit"], 1300)

    def test_blast_protection_and_push_protection_are_independent(self):
        for policy, pushed in (
            ("damage_immunity_does_not_block_push", True),
            ("damage_immunity_blocks_push", False),
        ):
            with self.subTest(policy=policy):
                instance = giga_instance()
                instance["parameters"]["push_protection"] = policy
                actors, runtime, motion, trace = self.runtime(instance)
                actors["unit"]["immune_until"] = 1
                self.assertFalse(runtime.update(actors, 0, trace))
                self.assertEqual("unit" in motion.motions, pushed)

    def test_finite_push_continues_while_frozen_and_pauses_attack_work_by_union(self):
        actors, runtime, motion, trace = self.runtime()
        actor = actors["unit"]
        actor["frozen_until"] = 0.25
        actor["next_attack"] = 0.45
        runtime.update(actors, 0, trace)
        self.assertAlmostEqual(actor["next_attack"], 0.9)
        self.assertAlmostEqual(actor["_displacement_pause_until"], 0.7)
        self.assertEqual(motion.forced_motion(actor, 0)["route"], [(14, 10)])
        motion.advance(actors, 0, 0.1, trace)
        self.assertAlmostEqual(actor["x"], 12.4)
        self.assertEqual(actor["frozen_until"], 0.25)

    def test_ground_push_clips_before_obstacle_while_air_passes_above(self):
        for layer, expected_distance in (("ground", 1), ("air", 5)):
            with self.subTest(layer=layer):
                instance = giga_instance()
                instance["parameters"]["push_distance_tiles"] = 5
                others = [
                    unit(x=13, layer=layer, movement=layer),
                    synthetic_structure(
                        "wall",
                        x=14,
                        y=9,
                        width=1,
                        height=3,
                        kind="wall",
                        counts_for_destruction=False,
                    ),
                ]
                actors, runtime, motion, trace = self.runtime(instance, others)
                runtime.update(actors, 0, trace)
                displacement = motion.motions["unit"]
                self.assertAlmostEqual(
                    displacement["destination"][0] - 13, expected_distance, places=6
                )
                if layer == "ground":
                    self.assertLess(displacement["destination"][0], 14)

    def test_coincident_direction_and_board_clipping_are_declared(self):
        instance = giga_instance()
        instance["parameters"].update(
            push_distance_tiles=100, coincident_direction=[0, -1]
        )
        actors, runtime, motion, trace = self.runtime(instance, [unit(x=10, y=10)])
        runtime.update(actors, 0, trace)
        destination = motion.motions["unit"]["destination"]
        self.assertEqual(destination[0], 10)
        self.assertGreaterEqual(destination[1], 0)
        self.assertLess(destination[1], 0.000001)

    def test_tornado_blocks_push_without_blocking_damage(self):
        actors, runtime, motion, trace = self.runtime()
        actors["unit"]["_tornado_capture_until"] = 5
        self.assertEqual(runtime.update(actors, 0, trace)["unit"], 1300)
        self.assertFalse(motion.motions)
        self.assertEqual(
            [event for event in trace if event["event"] == "giga_bomb_push_suppressed"][
                0
            ]["reason"],
            "tornado_priority",
        )

    def test_existing_gust_replaced_with_longest_pause_preserved(self):
        actors, runtime, motion, trace = self.runtime(
            others=[unit(layer="air", movement="air")]
        )
        actor = actors["unit"]
        motion.start(
            actor,
            0,
            (0, 1),
            {
                "push_distance_tiles": 5,
                "push_speed_tiles_per_second": 1,
                "recovery_seconds": 1,
            },
            "sweeper",
            trace,
        )
        old_next = actor["next_attack"]
        runtime.update(actors, 0, trace)
        self.assertEqual(motion.motions["unit"]["source"], "giga")
        self.assertEqual(actor["_displacement_pause_until"], 6)
        self.assertEqual(actor["next_attack"], old_next)

    def test_public_displacement_queue_validates_endpoint_and_preserves_state_on_error(
        self,
    ):
        actors, _, motion, trace = self.runtime()
        actor = actors["unit"]
        for destination, speed, distance in (
            ((30, 10), 4, 18),
            ((14, 10), 0, 2),
            ((14, 10), 4, 1),
        ):
            with (
                self.subTest(destination=destination, speed=speed),
                self.assertRaises(InputError),
            ):
                enqueue_linear_displacement(
                    motion,
                    actor,
                    0,
                    destination,
                    speed,
                    0.2,
                    "giga",
                    trace,
                    requested_distance=distance,
                )
            self.assertFalse(motion.motions)
            self.assertEqual(actor["next_attack"], 0)

    def test_trigger_contact_detects_route_entry_tangency_and_reentry(self):
        cases = [
            ((3, 10), [(15, 10)], 2, 1.75),
            ((5, 13.5), [(15, 13.5)], 5, 1),
            ((10, 10), [(16, 10), (10, 10)], 2, 4.25),
            ((13.5, 10), [(16, 10), (10, 10)], 2, 2.5),
        ]
        for position, route, speed, expected in cases:
            with self.subTest(position=position, route=route):
                actors, runtime, _, _ = self.runtime(
                    others=[unit(x=position[0], y=position[1])]
                )
                self.assertAlmostEqual(
                    runtime.first_crossing_delay(actors["unit"], route, 0, 10, speed),
                    expected,
                )

    def test_lethal_blast_uses_normal_death_and_cancels_its_captured_motion(self):
        actors, runtime, motion, trace = self.runtime(others=[unit(hitpoints=1000)])
        damage = runtime.update(actors, 0, trace)
        _apply_health(actors, damage, {}, 0)
        self.assertEqual(actors["unit"]["hp"], 0)
        self.assertEqual(actors["unit"]["death_time"], 0)
        self.assertNotIn("removal", actors["unit"])
        motion.advance(actors, 0, 0.1, trace)
        self.assertFalse(motion.motions)

    def test_battle_profile_scales_blast_once_preserving_weights_and_push(self):
        trap = compile_giga_bomb(giga_instance(), self.catalog)
        from test_advanced_defenses import compiled_advanced, multi_gear_instance

        tower = compiled_advanced(self.catalog, multi_gear_instance())
        result = apply_battle_modifiers(
            {"actors": [tower], "traps": [trap]},
            modifier_policy(),
            self.catalog,
            self.mode_rules,
        )
        scaled = result["scene"]["traps"][0]
        self.assertEqual(scaled["damage"], 1560)
        self.assertEqual(scaled["trigger_housing_space"], 18)
        self.assertEqual(scaled["parameters"]["push_distance_tiles"], 2)
        self.assertEqual(
            scaled["parameters"]["unit_responses"], trap["parameters"]["unit_responses"]
        )

    def test_missing_physics_or_response_policy_is_rejected(self):
        for field in ("collision_policy", "unit_responses", "trigger_weight_basis"):
            instance = giga_instance()
            del instance["parameters"][field]
            with self.subTest(field=field), self.assertRaises(InputError):
                compile_giga_bomb(instance, self.catalog)
        instance = giga_instance()
        instance["parameters"]["unit_responses"]["unit"]["trigger_weight"] = -1
        with self.assertRaises(InputError):
            compile_giga_bomb(instance, self.catalog)


if __name__ == "__main__":
    unittest.main()
