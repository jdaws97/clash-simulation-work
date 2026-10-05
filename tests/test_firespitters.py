"""Firespitter cone, burst work, released bullets and swept live collisions."""

from copy import deepcopy
from math import radians, sqrt, tan
from pathlib import Path
import unittest

from clashlab.battle_modifiers import apply_battle_modifiers
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.firespitters import (
    BURST_TIMING,
    EXTRACTED_GEOMETRY,
    PATTERN,
    PROJECTILE_POLICIES,
    READINESS_POLICY,
    TARGETING,
    FirespitterCombat,
    compile_firespitter,
    validate_firespitter_pattern,
)
from clashlab.rates import rescale_remaining_cooldown
from clashlab.spatial import _apply_effects, _load_actors, _select_target

from test_adapters import entity_instance
from test_battle_modifiers import modifier_policy
from test_combat import synthetic_pattern
from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "explicit-firespitter-fixture-not-replay-calibrated"


def firespitter_parameters():
    return {
        "source": SOURCE,
        "geometry_basis": "pinned_extraction_degrees_and_hundredths_of_a_tile",
        "orientation_basis": "clockwise_from_positive_x_in_screen_coordinates",
        "orientation_degrees": 0,
        "damage_basis": "snapshot_damagePerShot_is_one_bullet",
        "burst_timing": BURST_TIMING,
        "targeting": {**TARGETING, "excluded_entities": []},
        "spread": {
            "kind": "explicit_per_burst_angle_sequence",
            "angle_offsets_degrees": [0] * 20,
            "sequence_policy": "restart_after_completed_burst",
        },
        "projectile": {
            **PROJECTILE_POLICIES,
            "speed_tiles_per_second": 10,
            "hit_radius_tiles": 0.25,
            "maximum_travel_range_multiplier": 1,
        },
        "readiness_policy": READINESS_POLICY,
    }


def firespitter_instance(**changes):
    instance = entity_instance(
        "firespitter",
        "firespitter",
        2,
        "defense",
        town_hall=17,
        x=2,
        y=4,
        attack_parameters={},
        firespitter_parameters=firespitter_parameters(),
    )
    instance.update(changes)
    return instance


def compiled_firespitter(catalog, instance=None):
    instance = firespitter_instance() if instance is None else instance
    row = catalog.level("firespitter", instance["level"])
    actor = synthetic_structure(
        instance["id"],
        source=catalog.records["firespitter"]["source"],
        x=instance["x"],
        y=instance["y"],
        hitpoints=row["hitpoints"] * instance["modifiers"]["hitpoints_multiplier"],
        entity_adapter={
            "entity": "firespitter",
            "level": instance["level"],
            "town_hall": instance["town_hall"],
            "modifiers": deepcopy(instance["modifiers"]),
        },
    )
    return compile_firespitter(
        actor, instance, catalog.entity("firespitter"), row, instance["modifiers"]
    )


def target(actor_id="primary", **changes):
    return synthetic_unit(
        actor_id,
        x=10.5,
        y=5.5,
        hitpoints=10000,
        minimum_range=0,
        attack_model=synthetic_pattern(),
        **changes,
    )


class FirespitterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.mode_rules = read_json(ROOT / "data" / "mode-rules.json")

    def runtime(self, instance=None, others=None):
        actor = compiled_firespitter(self.catalog, instance)
        actors = _load_actors(
            {"actors": [actor, *(others if others is not None else [target()])]}, 40, 30
        )
        return actors, FirespitterCombat(actors, _select_target), []

    def launch(self, actors, runtime, trace, time=0, target_id="primary"):
        return runtime.launch(
            actors["firespitter"], actors[target_id], actors, time, trace
        )

    def test_catalog_shot_quantities_and_extraction_conflicts_remain_visible(self):
        actor = compiled_firespitter(self.catalog)
        self.assertEqual(actor["hitpoints"], 5000)
        self.assertEqual(actor["damage"], 49)
        self.assertEqual(actor["range"], 16)
        self.assertEqual(actor["attack_interval_seconds"], 0.064)
        self.assertEqual(actor["firespitter_model"]["post_burst_seconds"], 1.0167)
        self.assertEqual(actor["attack_model"]["kind"], PATTERN)
        audit = actor["entity_adapter"]["source_audit"]
        self.assertEqual(audit["catalog_displayed_dps"], 437)
        self.assertEqual(audit["extraction_displayed_dps"], 438)
        self.assertEqual(audit["extracted_geometry"], EXTRACTED_GEOMETRY)
        self.assertAlmostEqual(
            audit["derived_full_hit_dps_before_runtime_buffs"], 980 / 2.2327
        )
        self.assertNotEqual(actor["damage"], 437 * 0.064)

    def test_required_policies_orientation_and_stream_shape_are_validated(self):
        variants = []
        instance = firespitter_instance()
        del instance["firespitter_parameters"]["spread"]
        variants.append(instance)
        for field, value in (
            ("orientation_degrees", 45),
            ("burst_timing", "generic_dps"),
        ):
            instance = firespitter_instance()
            instance["firespitter_parameters"][field] = value
            variants.append(instance)
        instance = firespitter_instance()
        instance["firespitter_parameters"]["spread"]["angle_offsets_degrees"] = [0] * 19
        variants.append(instance)
        instance = firespitter_instance()
        instance["firespitter_parameters"]["projectile"]["speed_tiles_per_second"] = 0
        variants.append(instance)
        variants.extend(
            [firespitter_instance(mode="cone"), firespitter_instance(town_hall=16)]
        )
        for instance in variants:
            with self.subTest(instance=instance), self.assertRaises(InputError):
                compiled_firespitter(self.catalog, instance)

    def test_constructor_revalidates_full_spread_and_dedicated_pattern(self):
        actor = compiled_firespitter(self.catalog)
        actor["firespitter_model"]["spread"]["angle_offsets_degrees"].pop()
        actors = _load_actors({"actors": [actor, target()]}, 40, 30)
        with self.assertRaisesRegex(InputError, "exactly one"):
            FirespitterCombat(actors, _select_target)
        with self.assertRaises(InputError):
            validate_firespitter_pattern(synthetic_pattern("radial"))

    def test_twenty_shots_then_post_last_shot_gap_without_double_launch(self):
        actors, runtime, trace = self.runtime()
        source = actors["firespitter"]
        times = []
        for _ in range(21):
            time = source["next_attack"]
            self.assertTrue(self.launch(actors, runtime, trace, time))
            self.assertFalse(self.launch(actors, runtime, trace, time))
            times.append(time)
        self.assertAlmostEqual(times[19], 19 * 0.064)
        self.assertAlmostEqual(times[20], 19 * 0.064 + 1.0167)
        state = runtime.states["firespitter"]
        self.assertEqual(state["burst_number"], 2)
        self.assertEqual(state["next_shot_index"], 1)
        self.assertEqual(state["launched_shots"], 21)

    def test_cone_orientation_filters_layers_distance_and_visibility(self):
        instance = firespitter_instance()
        instance["firespitter_parameters"]["orientation_degrees"] = 90
        ground = target("ground")
        ground.update(x=3.5, y=12)
        air = target("air", movement="air", layer="air")
        air.update(x=3.5, y=10)
        rear = target("rear")
        rear.update(x=3.5, y=2)
        actors, runtime, _ = self.runtime(instance, [ground, air, rear])
        source = actors["firespitter"]
        selected, _ = runtime.select_target(source, actors, 0, set(), 40, 30)
        self.assertEqual(selected["id"], "air")
        actors["air"]["_spell_tower_untargetable_until"] = 1
        selected, _ = runtime.select_target(source, actors, 0, set(), 40, 30)
        self.assertEqual(selected["id"], "ground")
        actors["air"]["_spell_tower_untargetable_until"] = 0
        selected, _ = runtime.select_target(source, actors, 0, set(), 40, 30)
        self.assertEqual(
            selected["id"],
            "ground",
            "Live primary is retained even when another becomes closer",
        )
        actors["ground"]["y"] = 25
        selected, _ = runtime.select_target(source, actors, 0, set(), 40, 30)
        self.assertEqual(selected["id"], "air")

    def test_bullet_first_contact_has_explicit_travel_time(self):
        actors, runtime, trace = self.runtime()
        self.launch(actors, runtime, trace)
        arrival = runtime.next_boundary(0)
        self.assertAlmostEqual(arrival, (7 - 0.25) / 10)
        self.assertFalse(runtime.resolve(actors, arrival - 0.01, trace))
        damage = runtime.resolve(actors, arrival, trace)
        self.assertEqual(damage["primary"], 49)
        self.assertFalse(runtime.bullets)
        self.assertEqual(runtime.hit_count, 1)

    def test_spread_miss_can_hit_an_air_unit_behind_ground_primary(self):
        instance = firespitter_instance()
        instance["firespitter_parameters"]["spread"]["angle_offsets_degrees"][0] = 10
        behind = target("behind", movement="air", layer="air")
        behind.update(x=11.5, y=5.5 + 8 * tan(radians(10)))
        actors, runtime, trace = self.runtime(instance, [target(), behind])
        self.launch(actors, runtime, trace)
        arrival = runtime.next_boundary(0)
        damage = runtime.resolve(actors, arrival, trace)
        self.assertEqual(dict(damage), {"behind": 49})
        self.assertEqual(trace[-1]["primary"], "primary")
        self.assertEqual(trace[-1]["target"], "behind")

    def test_source_and_primary_death_do_not_delete_released_bullet(self):
        behind = target("behind")
        behind["x"] = 13.5
        actors, runtime, trace = self.runtime(others=[target(), behind])
        self.launch(actors, runtime, trace)
        for actor_id in ("firespitter", "primary"):
            actors[actor_id].update(hp=0, death_time=0.1)
        runtime.prepare(actors, 0.1, trace)
        self.assertEqual(runtime.states["firespitter"]["cancelled_shots"], 19)
        self.assertFalse(self.launch(actors, runtime, trace, 0.2, "behind"))
        arrival = runtime.next_boundary(0.1)
        damage = runtime.resolve(actors, arrival, trace)
        self.assertEqual(dict(damage), {"behind": 49})

    def test_protection_consumes_bullet_and_invisibility_does_not_protect_collision(
        self,
    ):
        behind = target("behind")
        behind["x"] = 13.5
        actors, runtime, trace = self.runtime(others=[target(), behind])
        self.launch(actors, runtime, trace)
        actors["primary"]["immune_until"] = 2
        actors["primary"]["_untargetable_until"] = 2
        actors["primary"]["_spell_tower_untargetable_until"] = 2
        arrival = runtime.next_boundary(0)
        self.assertFalse(runtime.resolve(actors, arrival, trace))
        self.assertTrue(trace[-1]["protected"])
        self.assertFalse(runtime.bullets)
        self.assertEqual(runtime.hit_count, 1)

    def test_no_collision_expires_at_finite_distance(self):
        instance = firespitter_instance()
        instance["firespitter_parameters"]["spread"]["angle_offsets_degrees"][0] = 90
        actors, runtime, trace = self.runtime(instance)
        self.launch(actors, runtime, trace)
        self.assertAlmostEqual(runtime.next_boundary(0), 1.6)
        self.assertFalse(runtime.resolve(actors, 1.6, trace))
        self.assertEqual(runtime.miss_count, 1)

    def test_projectile_state_and_rage_damage_are_captured_at_launch(self):
        actors, runtime, trace = self.runtime()
        source = actors["firespitter"]
        source["_buff_damage_multiplier"] = 2
        source["_spell_tower_damage_multiplier"] = 1.6
        source["_spell_tower_rage_composition"] = "multiply_with_other_sources"
        self.launch(actors, runtime, trace)
        source["damage"] = 99999
        source["_buff_damage_multiplier"] = 1
        source["_spell_tower_damage_multiplier"] = 1
        source["target_layers"] = ["air"]
        runtime.models["firespitter"]["projectile"]["hit_radius_tiles"] = 100
        runtime.models["firespitter"]["projectile"]["speed_tiles_per_second"] = 1
        arrival = runtime.next_boundary(0)
        self.assertAlmostEqual(arrival, 0.675)
        self.assertAlmostEqual(
            runtime.resolve(actors, arrival, trace)["primary"], 49 * 3.2
        )

    def test_target_loss_preserves_partial_burst_and_freeze_preserves_attack_work(self):
        actors, runtime, trace = self.runtime()
        self.launch(actors, runtime, trace)
        _apply_effects(
            [
                {
                    "id": "freeze",
                    "kind": "freeze",
                    "targets": ["firespitter"],
                    "duration_seconds": 1,
                }
            ],
            actors,
            0.02,
            trace,
        )
        self.assertAlmostEqual(actors["firespitter"]["next_attack"], 1.064)
        self.assertFalse(self.launch(actors, runtime, trace, 0.5))
        actors["primary"]["_untargetable_until"] = 2
        self.assertFalse(self.launch(actors, runtime, trace, 1.064))
        self.assertEqual(runtime.states["firespitter"]["next_shot_index"], 1)
        self.assertTrue(self.launch(actors, runtime, trace, 2))
        self.assertEqual(runtime.states["firespitter"]["next_shot_index"], 2)

    def test_attack_slow_rescales_unfinished_work_without_retiming_released_bullet(
        self,
    ):
        actors, runtime, trace = self.runtime()
        self.launch(actors, runtime, trace)
        source = actors["firespitter"]
        rescale_remaining_cooldown(source, 0.02, 1, 0.5)
        source["_hit_status_attack_rate"] = 0.5
        self.assertAlmostEqual(source["next_attack"], 0.108)
        self.assertAlmostEqual(runtime.next_boundary(0.02), 0.675)
        self.assertTrue(self.launch(actors, runtime, trace, 0.108))
        self.assertAlmostEqual(source["next_attack"], 0.236)

    def test_moving_recipient_crosses_live_bullet_between_solver_boundaries(self):
        primary = target()
        primary["x"] = 15.5
        moving = target("moving")
        moving.update(x=8.5, y=2.5)
        actors, runtime, trace = self.runtime(others=[primary, moving])
        self.launch(actors, runtime, trace)
        delay = runtime.first_crossing_delay(actors["moving"], [(8.5, 8.5)], 0, 1, 6)
        expected = (sqrt(34) - 0.25) / sqrt(136)
        self.assertAlmostEqual(delay, expected)
        actors["moving"]["y"] += 6 * delay
        damage = runtime.resolve(actors, delay, trace)
        self.assertEqual(dict(damage), {"moving": 49})

    def test_forced_motion_crossing_is_not_suppressed_by_freeze(self):
        primary = target()
        primary["x"] = 15.5
        moving = target("moving", movement="air", layer="air")
        moving.update(x=8.5, y=2.5)
        actors, runtime, trace = self.runtime(others=[primary, moving])
        actors["moving"]["frozen_until"] = 10
        self.launch(actors, runtime, trace)
        delay = runtime.first_crossing_delay(actors["moving"], [(8.5, 8.5)], 0, 1, 6)
        self.assertIsNotNone(delay)
        actors["moving"]["y"] += 6 * delay
        self.assertEqual(runtime.resolve(actors, delay, trace)["moving"], 49)

    def test_moving_primary_evades_stale_static_contact_boundary(self):
        actors, runtime, trace = self.runtime()
        self.launch(actors, runtime, trace)
        route = [(10.5, 15.5)]
        self.assertIsNone(
            runtime.first_crossing_delay(actors["primary"], route, 0, 0.7, 10)
        )
        boundary = runtime.next_boundary(0)
        actors["primary"]["y"] += 10 * boundary
        self.assertFalse(runtime.resolve(actors, boundary, trace))
        self.assertTrue(runtime.bullets)

    def test_cone_entry_is_detected_on_a_later_route_segment(self):
        unit = target()
        unit.update(x=22.5, y=5.5)
        actors, runtime, _ = self.runtime(others=[unit])
        delay = runtime.first_crossing_delay(
            actors["primary"], [(22.5, 6.5), (18.5, 6.5)], 0, 3, 2
        )
        expected = (1 + 19 - sqrt(16 * 16 - 1)) / 2
        self.assertAlmostEqual(delay, expected)

    def test_live_spawn_can_intercept_an_existing_bullet_and_ties_use_id(self):
        late = target("a-late", spawn_seconds="controlled")
        late.update(x=8.5, y=5.5)
        later = target("b-late", spawn_seconds="controlled")
        later.update(x=8.5, y=5.5)
        actors, runtime, trace = self.runtime(others=[target(), late, later])
        self.launch(actors, runtime, trace)
        for actor_id in ("a-late", "b-late"):
            actors[actor_id]["spawn_seconds"] = 0.2
        arrival = runtime.next_boundary(0.2)
        damage = runtime.resolve(actors, arrival, trace)
        self.assertEqual(dict(damage), {"a-late": 49})

    def test_global_profile_scales_weapon_once_before_launch_and_preserves_cadence(
        self,
    ):
        actor = compiled_firespitter(self.catalog)
        scene = {"actors": [actor], "traps": []}
        applied = apply_battle_modifiers(
            scene, modifier_policy(), self.catalog, self.mode_rules
        )
        changed = applied["scene"]["actors"][0]
        self.assertEqual(changed["hitpoints"], 5000)
        self.assertAlmostEqual(changed["damage"], 58.8)
        self.assertEqual(changed["firespitter_model"], actor["firespitter_model"])
        actors = _load_actors({"actors": [changed, target()]}, 40, 30)
        runtime = FirespitterCombat(actors, _select_target)
        trace = []
        self.launch(actors, runtime, trace)
        damage = runtime.resolve(actors, runtime.next_boundary(0), trace)
        self.assertAlmostEqual(damage["primary"], 58.8)
        self.assertEqual(actors["firespitter"]["next_attack"], 0.064)
        self.assertFalse(runtime.result()["full_game_prediction"])


if __name__ == "__main__":
    unittest.main()
