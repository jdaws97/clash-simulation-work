"""Conditional Druid component tests with explicitly synthetic Bear statistics."""

import unittest
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.druids import (
    TRANSFORMATION_POLICIES,
    DruidCombat,
    DruidSupportCombat,
    compile_druid,
    compile_druid_forms,
)
from clashlab.spatial import _apply_health, _load_actors, _select_target

from test_adapters import entity_instance, projectile
from test_healing import healing_model, support_scene
from test_spatial import synthetic_scene, synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-v30-druid-fixture-not-current-client-statistics"


def druid_parameters(key="druid", level=4):
    return {
        "source": SOURCE,
        **TRANSFORMATION_POLICIES,
        "bear": {
            "id": f"{key}-bear",
            "source": SOURCE,
            "level": level,
            "statistics_status": "explicit_uncalibrated_hypothesis",
            "hitpoints": 1000,
            "damage_per_hit": 80,
            "attack_interval_seconds": 1,
            "range": 0.5,
            "speed_tiles_per_second": 1,
            "housing_space": 10,
            "first_attack_delay_seconds": 0.1,
            "wall_behavior": {"kind": "avoid", "source": SOURCE},
        },
    }


def druid_healing():
    return {
        "source": SOURCE,
        "projectile": projectile(),
        "selector": healing_model()["selector"],
        "stacking_group": "test-healers",
        "amount_multiplier": 1,
        "chain": {
            "source": SOURCE,
            "target_count_interpretation": "catalog_counts_secondary_bounces",
            "maximum_recipients": 5,
            "hop_range_tiles": 2,
            "hop_delay_seconds": 0.25,
            "geometry": "recipient_center_to_target_footprint",
            "selection": "nearest_then_instance_id",
            "membership": "choose_next_at_current_recipient_impact",
            "repeats": "each_actor_at_most_once_per_projectile",
            "inactive_recipient": "fizzle_remaining_chain",
            "source_persistence": "launched_chain_survives_transformation_and_source_loss",
            "stacking_membership": "predicted_current_chain_plus_due_packets",
        },
    }


def druid_instance(key="druid", **changes):
    instance = entity_instance(
        key,
        "druid",
        4,
        "attack",
        x=1.5,
        y=2.5,
        attack_parameters={},
        wall_parameters={"kind": "jump_enemy_walls", "source": SOURCE},
        healing_parameters=druid_healing(),
        druid_parameters=druid_parameters(key),
    )
    instance.update(changes)
    return instance


def compiled_druid(catalog, instance=None):
    instance = instance or druid_instance()
    actor = synthetic_unit(instance["id"])
    for key in (
        "team",
        "x",
        "y",
        "spawn_seconds",
        "first_attack_seconds",
        "counts_for_destruction",
    ):
        actor[key] = instance[key]
    actor.update(
        {
            "source": catalog.records["druid"]["source"],
            "hitpoints": catalog.level("druid", instance["level"])["hitpoints"]
            * instance["modifiers"]["hitpoints_multiplier"],
            "minimum_range": 0,
            "entity_adapter": {"entity": "druid", "level": instance["level"]},
        }
    )
    actor = compile_druid(
        actor,
        instance,
        catalog.entity("druid"),
        catalog.level("druid", instance["level"]),
        instance["modifiers"],
        8,
    )
    return [actor, *compile_druid_forms([actor])]


def loaded(actors):
    return _load_actors(synthetic_scene(actors, width=20, height=20), 20, 20)


def recipient(key, x, **changes):
    return synthetic_unit(key, x=x, y=2.5, healing_class="troop", **changes)


def health(actors, damage, healing, time, interceptor, trace):
    _apply_health(
        actors,
        defaultdict(float, damage),
        defaultdict(float, healing),
        time,
        interceptor,
        trace=trace,
    )


class DruidTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_catalog_first_form_and_separate_explicit_bear_statistics(self):
        first, bear = compiled_druid(self.catalog)
        self.assertEqual(
            first["healing_model"]["amounts_by_class"], {"troop": 95, "hero": 104.5}
        )
        self.assertEqual(first["druid_model"]["evolve_seconds"], 30)
        self.assertEqual(first["damage"], 0)
        self.assertEqual(first["wall_behavior"]["kind"], "jump_enemy_walls")
        self.assertEqual(bear["damage"], 80)
        self.assertEqual(bear["hitpoints"], 1000)
        self.assertEqual(bear["target_priority_tiers"], [["defense"], ["building"]])
        self.assertEqual(bear["spawn_seconds"], "controlled")
        self.assertEqual(bear["summon_model"]["parent"], "druid")
        self.assertEqual(
            bear["druid_form_statistics"]["statistics_status"],
            "explicit_uncalibrated_hypothesis",
        )

    def test_missing_bear_invalid_level_and_unselected_chain_count_reject(self):
        for mutation in ("missing", "level", "calibrated", "count", "jump"):
            instance = druid_instance()
            bear = instance["druid_parameters"]["bear"]
            if mutation == "missing":
                bear.pop("speed_tiles_per_second")
            elif mutation == "level":
                bear["level"] = 3
            elif mutation == "calibrated":
                bear["statistics_status"] = "catalog_verified"
            elif mutation == "count":
                instance["healing_parameters"]["chain"]["maximum_recipients"] = 4
            else:
                bear["wall_behavior"]["kind"] = "jump_enemy_walls"
            with self.subTest(mutation=mutation), self.assertRaises(InputError):
                compiled_druid(self.catalog, instance)

    def test_bear_modifiers_are_applied_once_without_changing_healing(self):
        instance = druid_instance()
        instance["modifiers"].update(
            hitpoints_multiplier=2, damage_multiplier=3, movement_speed_multiplier=1.5
        )
        first, bear = compiled_druid(self.catalog, instance)
        self.assertEqual(first["healing_model"]["amounts_by_class"]["troop"], 95)
        self.assertEqual(bear["hitpoints"], 2000)
        self.assertEqual(bear["damage"], 240)
        self.assertEqual(bear["speed"], 1.5)

    def test_timeout_is_deployment_relative_and_continues_through_freeze(self):
        actors = loaded(
            compiled_druid(self.catalog, druid_instance(spawn_seconds="controlled"))
        )
        runtime = DruidCombat(actors)
        trace = []
        runtime.prepare(0, trace)
        self.assertIsNone(runtime.next_boundary(0))
        actors["druid"]["spawn_seconds"] = 4
        actors["druid"]["frozen_until"] = 100
        actors["druid"]["immune_until"] = 100
        runtime.prepare(4, trace)
        self.assertEqual(runtime.next_boundary(4), 34)
        runtime.prepare(34, trace)
        self.assertEqual(actors["druid"]["death_time"], 34)
        self.assertEqual(actors["druid-bear"]["spawn_seconds"], 34)
        self.assertEqual(actors["druid-bear"]["next_attack"], 34.1)
        self.assertEqual(actors["druid-bear"]["frozen_until"], 0)
        self.assertEqual(actors["druid-bear"]["immune_until"], 0)

    def test_actual_lethal_damage_discards_overflow_and_never_duplicates_form(self):
        actors = loaded(compiled_druid(self.catalog))
        runtime = DruidCombat(actors)
        trace = []
        runtime.prepare(0, trace)
        health(
            actors, {"druid": 9000}, {"druid": 1000}, 2, runtime.intercept_lethal, trace
        )
        self.assertEqual(actors["druid"]["hp"], 0)
        self.assertEqual(actors["druid-bear"]["hp"], 1000)
        runtime.prepare(30, trace)
        self.assertEqual(
            sum(item["event"] == "druid_bear_release" for item in trace), 1
        )
        health(actors, {"druid-bear": 10000}, {}, 31, runtime.intercept_lethal, trace)
        runtime.prepare(31, trace)
        self.assertEqual(runtime.states["druid"]["phase"], "dead")

    def test_timeout_and_death_same_boundary_emit_one_bear(self):
        actors = loaded(compiled_druid(self.catalog))
        runtime = DruidCombat(actors)
        trace = []
        runtime.prepare(0, trace)
        runtime.prepare(30, trace)
        health(actors, {"druid": 10000}, {}, 30, runtime.intercept_lethal, trace)
        self.assertEqual(
            sum(item["event"] == "druid_bear_release" for item in trace), 1
        )

    def test_nondeath_removal_does_not_spawn_bear(self):
        actors = loaded(compiled_druid(self.catalog))
        runtime = DruidCombat(actors)
        runtime.prepare(0, [])
        actors["druid"]["hp"] = 0
        actors["druid"]["death_time"] = 1
        runtime.prepare(1, [])
        self.assertEqual(runtime.states["druid"]["phase"], "removed_without_bear")
        self.assertEqual(actors["druid-bear"]["spawn_seconds"], "controlled")
        self.assertEqual(runtime.continuation_reasons(1), [])

    def test_blocked_form_release_retains_latent_ownership_until_wall_clears(self):
        actors = loaded(
            [
                *compiled_druid(self.catalog),
                synthetic_structure("wall", kind="wall", x=1, y=2),
            ]
        )
        runtime = DruidCombat(actors)
        runtime.prepare(0, [])
        trace = []
        runtime.prepare(30, trace)
        self.assertEqual(runtime.states["druid"]["phase"], "pending_bear")
        facts = runtime.continuation_reasons(30)
        self.assertEqual(facts[0]["kind"], "pending_release")
        self.assertEqual(facts[0]["actor_ids"], ["druid", "druid-bear"])
        actors["wall"]["hp"] = 0
        runtime.prepare(31, trace)
        self.assertEqual(actors["druid-bear"]["spawn_seconds"], 31)
        self.assertEqual(runtime.continuation_reasons(31), [])

    def test_generated_form_cannot_be_independently_deployed_or_reparented(self):
        actors = loaded(compiled_druid(self.catalog))
        runtime = DruidCombat(actors)
        with self.assertRaisesRegex(InputError, "independently deployed"):
            runtime.validate_command({"kind": "deploy", "targets": ["druid-bear"]})
        actors["druid-bear"]["druid_form_model"]["parent"] = "other"
        with self.assertRaisesRegex(InputError, "matching ownership"):
            DruidCombat(actors)

    def test_chain_hops_both_layers_without_siege_or_repeat_recipients(self):
        actors = loaded(
            [
                *compiled_druid(self.catalog),
                recipient("a", 2.5),
                recipient("b", 3.5, layer="air", movement="air"),
                recipient("c", 4.5),
                recipient("siege", 3, beneficial_field_immunity=True),
            ]
        )
        specification = support_scene()
        runtime = DruidSupportCombat(actors, specification, _select_target)
        trace = []
        runtime.launch(actors["druid"], actors["a"], 0, trace)
        self.assertEqual(dict(runtime.resolve(actors, 0, trace)), {"a": 95})
        self.assertEqual(dict(runtime.resolve(actors, 0.25, trace)), {"b": 95})
        self.assertEqual(dict(runtime.resolve(actors, 0.5, trace)), {"c": 95})
        self.assertIsNone(runtime.next_boundary())
        self.assertEqual(
            [item["target"] for item in trace if item["event"] == "druid_chain_link"],
            ["a", "b", "c"],
        )

    def test_chain_survives_source_transform_and_captures_emitter_buff_once(self):
        actors = loaded(
            [*compiled_druid(self.catalog), recipient("a", 2.5), recipient("b", 3.5)]
        )
        support = DruidSupportCombat(actors, support_scene(), _select_target)
        lifecycle = DruidCombat(actors)
        lifecycle.prepare(0, [])
        actors["druid"]["_buff_healing_multiplier"] = 2
        support.launch(actors["druid"], actors["a"], 0, [])
        self.assertEqual(support.resolve(actors, 0, [])["a"], 190)
        health(actors, {"druid": 10000}, {}, 0.1, lifecycle.intercept_lethal, [])
        actors["druid"]["_buff_healing_multiplier"] = 1
        actors["b"]["_buff_healing_multiplier"] = 7
        self.assertEqual(support.resolve(actors, 0.25, [])["b"], 190)

    def test_dead_recipient_fizzles_remaining_chain(
        self,
    ):
        actors = loaded(
            [
                *compiled_druid(self.catalog),
                recipient("a", 2.5),
                recipient("b", 3.5),
                recipient("c", 5),
            ]
        )
        runtime = DruidSupportCombat(actors, support_scene(), _select_target)
        runtime.launch(actors["druid"], actors["a"], 0, [])
        runtime.resolve(actors, 0, [])
        actors["b"]["hp"] = 0
        self.assertEqual(dict(runtime.resolve(actors, 0.25, [])), {})
        self.assertIsNone(runtime.next_boundary())

    def test_shared_healer_stacking_combines_ordinary_and_chain_due_packets(self):
        ordinary = recipient("a-healer", 1, damage=0)
        ordinary["healing_model"] = healing_model()
        actors = loaded(
            [*compiled_druid(self.catalog), ordinary, recipient("target", 2.5)]
        )
        runtime = DruidSupportCombat(actors, support_scene(), _select_target)
        runtime.launch(actors["a-healer"], actors["target"], 0, [])
        runtime.launch(actors["druid"], actors["target"], 0, [])
        self.assertEqual(runtime.resolve(actors, 0, [])["target"], 20 + 95 * 0.5)

    def test_hero_and_pet_healing_remain_separate_amounts(self):
        instance = druid_instance()
        instance["healing_parameters"].update(
            pet_healing_basis="hero_catalog_pulse", pet_healing_multiplier=0.5
        )
        actors = loaded(
            [
                *compiled_druid(self.catalog, instance),
                recipient("hero", 2.5),
                recipient("pet", 3.5),
            ]
        )
        actors["hero"]["healing_class"] = "hero"
        actors["pet"]["healing_class"] = "pet"
        specification = support_scene()
        specification["healing_stacking"]["groups"]["test-healers"]["tables"]["pet"] = [
            1
        ]
        runtime = DruidSupportCombat(actors, specification, _select_target)
        runtime.launch(actors["druid"], actors["hero"], 0, [])
        self.assertEqual(runtime.resolve(actors, 0, [])["hero"], 104.5)
        self.assertEqual(runtime.resolve(actors, 0.25, [])["pet"], 52.25)

    def test_catalog_count_interpretation_caps_each_chain_without_repeated_healing(
        self,
    ):
        for interpretation, maximum in (
            ("catalog_counts_all_recipients", 4),
            ("catalog_counts_secondary_bounces", 5),
        ):
            with self.subTest(interpretation=interpretation):
                instance = druid_instance()
                instance["healing_parameters"]["chain"].update(
                    target_count_interpretation=interpretation,
                    maximum_recipients=maximum,
                    hop_delay_seconds=0,
                )
                actors = loaded(
                    [
                        *compiled_druid(self.catalog, instance),
                        *(
                            recipient(f"target-{index}", 3 + index / 10)
                            for index in range(6)
                        ),
                    ]
                )
                runtime = DruidSupportCombat(actors, support_scene(), _select_target)
                runtime.launch(actors["druid"], actors["target-0"], 0, [])
                healing = runtime.resolve(actors, 0, [])
                self.assertEqual(
                    set(healing), {f"target-{index}" for index in range(maximum)}
                )
                self.assertEqual(set(healing.values()), {95})

    def test_later_hop_selects_from_live_positions_at_intermediate_impact(self):
        actors = loaded(
            [
                *compiled_druid(self.catalog),
                recipient("a", 2.5),
                recipient("b", 3.5),
                recipient("c", 4.5),
                recipient("d", 5),
            ]
        )
        runtime = DruidSupportCombat(actors, support_scene(), _select_target)
        trace = []
        runtime.launch(actors["druid"], actors["a"], 0, trace)
        runtime.resolve(actors, 0, trace)
        actors["c"]["x"] = 15
        runtime.resolve(actors, 0.25, trace)
        self.assertEqual(runtime.resolve(actors, 0.5, trace), {"d": 95})
        self.assertEqual(
            [
                item["next_target"]
                for item in trace
                if item["event"] == "druid_chain_link"
            ],
            ["b", "d", None],
        )

    def test_first_form_jumps_enemy_wall_barrier_to_follow_a_distant_ally(self):
        barrier = [
            synthetic_structure(f"wall-{index}", kind="wall", x=4, y=index)
            for index in range(20)
        ]
        actors = loaded(
            [*compiled_druid(self.catalog), recipient("ally", 11.5), *barrier]
        )
        runtime = DruidSupportCombat(actors, support_scene(), _select_target)
        target, route = runtime.select_target(
            actors["druid"], actors, 0, {(4, index) for index in range(20)}, 20, 20
        )
        self.assertEqual(target["id"], "ally")
        self.assertIsNotNone(route)
        self.assertTrue(any(4 <= point[0] < 5 for point in route))

    def test_contact_with_moving_ally_uses_relative_motion(self):
        actors = loaded([*compiled_druid(self.catalog), recipient("ally", 7.5)])
        actors["druid"]["range"] = 2
        runtime = DruidSupportCombat(actors, support_scene(), _select_target)
        actors["druid"]["healing_target"] = "ally"
        motions = {"druid": ([(16.5, 2.5)], 3), "ally": ([(12.5, 2.5)], 1)}
        self.assertAlmostEqual(runtime.first_crossing_delay(actors, motions, 0, 3), 2)
        actors["druid"]["frozen_until"] = 10
        self.assertIsNone(runtime.first_crossing_delay(actors, motions, 0, 3))

    def test_actual_deployment_and_lethal_health_batch_still_create_one_form(self):
        actors = loaded(
            compiled_druid(self.catalog, druid_instance(spawn_seconds="controlled"))
        )
        runtime = DruidCombat(actors)
        actors["druid"]["spawn_seconds"] = 4
        trace = []
        health(actors, {"druid": 10000}, {}, 4, runtime.intercept_lethal, trace)
        runtime.prepare(4, trace)
        self.assertEqual(actors["druid-bear"]["spawn_seconds"], 4)
        self.assertEqual(runtime.states["druid"]["deployed_at"], 4)
        self.assertEqual(sum(item["event"] == "druid_transform" for item in trace), 1)

    def test_transformation_event_cannot_be_skipped_by_a_coarse_component_step(self):
        actors = loaded(compiled_druid(self.catalog))
        runtime = DruidCombat(actors)
        runtime.prepare(0, [])
        with self.assertRaisesRegex(InputError, "boundary was skipped"):
            runtime.prepare(31, [])


if __name__ == "__main__":
    unittest.main()
