"""Catalog quantities, declared bursts, and independent primary-centered fanout."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.advanced_defenses import (
    FANOUT_PATTERN,
    MULTI_GEAR_READINESS,
    MULTI_GEAR_TARGETING,
    MultiGearCombat,
    compile_multi_gear,
    compile_super_wizard,
    release_fanout_packets,
    validate_fanout_pattern,
)
from clashlab.battle_modifiers import apply_battle_modifiers
from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError, read_json
from clashlab.rates import rescale_remaining_cooldown
from clashlab.spatial import _apply_effects, _load_actors, _select_target

from test_adapters import entity_instance, projectile
from test_battle_modifiers import modifier_policy
from test_combat import synthetic_pattern
from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "declared-advanced-defense-fixture-not-replay-calibrated"


def advanced_projectile():
    return {**projectile(), "inactive_primary_policy": "fizzle"}


def multi_gear_instance(mode="fastAttack", **changes):
    instance = entity_instance(
        "multi-gear",
        "multi-gear-tower",
        2,
        "defense",
        town_hall=17,
        mode=mode,
        statistics_mode=mode,
        x=2,
        y=4,
        attack_parameters={"projectile": advanced_projectile()},
        multi_gear_parameters={
            "source": SOURCE,
            "damage_basis": "snapshot_damagePerShot_is_one_projectile",
            "burst_timing": (
                "snapshot_attackSpeed_is_one_shot_interval"
                if mode == "normal"
                else "snapshot_timeBetweenBursts_is_post_last_shot_gap"
            ),
            "targeting": MULTI_GEAR_TARGETING,
            "readiness_policy": MULTI_GEAR_READINESS,
        },
    )
    instance.update(changes)
    return instance


def fanout_parameters(**changes):
    parameters = {
        "anchor": "primary_center_at_primary_impact",
        "radius_tiles": 2,
        "distance_metric": "center_distance",
        "target_count_basis": "snapshot_count_is_secondary_count",
        "selection": "nearest_then_instance_id",
        "target_layer_policy": "both_declared_layers",
        "primary_protection": "continue_fanout",
        "secondary_protection": "protected_targets_consume_slots",
        "visibility": "exclude_currently_untargetable",
        "delay_seconds": 0,
        "selection_time": "live_candidates_at_primary_impact",
        "released_links": "independent_of_source_and_primary_after_selection",
        "secondary_destination": "locked_actor_center_at_impact",
        "inactive_secondary_policy": "fizzle",
    }
    parameters.update(changes)
    return parameters


def super_wizard_instance(**changes):
    instance = entity_instance(
        "super-wizard",
        "super-wizard-tower",
        1,
        "defense",
        town_hall=18,
        x=2,
        y=4,
        attack_parameters={"projectile": advanced_projectile()},
        super_wizard_parameters={
            "source": SOURCE,
            "damage_basis": "snapshot_primary_and_each_secondary_damagePerShot",
            "fanout": fanout_parameters(),
        },
    )
    instance.update(changes)
    return instance


def compiled_advanced(catalog, instance):
    entity_id = instance["entity"]
    row = catalog.level(entity_id, instance["level"])
    actor = synthetic_structure(
        instance["id"],
        source=catalog.records[entity_id]["source"],
        x=instance["x"],
        y=instance["y"],
        hitpoints=row["hitpoints"] * instance["modifiers"]["hitpoints_multiplier"],
        entity_adapter={
            "entity": entity_id,
            "level": instance["level"],
            "town_hall": instance["town_hall"],
            "modifiers": deepcopy(instance["modifiers"]),
        },
    )
    compiler = (
        compile_multi_gear if entity_id == "multi-gear-tower" else compile_super_wizard
    )
    return compiler(
        actor, instance, catalog.entity(entity_id), row, instance["modifiers"]
    )


def target(actor_id="primary", **changes):
    actor = synthetic_unit(
        actor_id,
        x=9.5,
        y=5.5,
        hitpoints=10000,
        minimum_range=0,
        attack_model=synthetic_pattern(),
    )
    actor.update(changes)
    return actor


class AdvancedDefenseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.mode_rules = read_json(ROOT / "data" / "mode-rules.json")

    def multi_runtime(self, instance=None, others=None):
        instance = multi_gear_instance() if instance is None else instance
        source = compiled_advanced(self.catalog, instance)
        actors = _load_actors({"actors": [source, *(others or [target()])]}, 40, 30)
        combat = PatternCombat(actors)
        return actors, MultiGearCombat(actors, _select_target, combat), combat, []

    def fanout_fixture(self, parameters=None, others=None):
        instance = super_wizard_instance()
        if parameters is not None:
            instance["super_wizard_parameters"]["fanout"] = parameters
        source = compiled_advanced(self.catalog, instance)
        actors = _load_actors({"actors": [source, target(), *(others or [])]}, 40, 30)
        pattern = source["attack_model"]
        packet = {
            "source": source["id"],
            "source_team": "defense",
            "target": "primary",
            "position": (9.5, 5.5),
            "launch_position": (3.5, 5.5),
            "primary_layer": "ground",
            "flat_damage": source["damage"],
            "pattern": pattern,
            "chain_index": 0,
            "visited": ["primary"],
        }
        combat = PatternCombat(actors)
        return actors, packet, combat

    def release(self, actors, packet, combat, time=0):
        return release_fanout_packets(
            packet, actors["primary"], actors, time, combat._damage_eligible
        )

    def test_multi_gear_modes_preserve_per_hit_quantities_and_source_disagreement(self):
        normal = compiled_advanced(self.catalog, multi_gear_instance("normal"))
        fast = compiled_advanced(self.catalog, multi_gear_instance())
        self.assertEqual(
            (normal["hitpoints"], normal["damage"], normal["range"]), (4200, 370, 12)
        )
        self.assertEqual(
            (fast["damage"], fast["range"], fast["attack_interval_seconds"]),
            (165.6, 8, 0.192),
        )
        audit = fast["entity_adapter"]["source_audit"]
        self.assertEqual(audit["extraction_attack_speed_raw"], 350)
        self.assertEqual(audit["catalog_displayed_dps"], 690)
        self.assertAlmostEqual(
            audit["derived_full_hit_dps_before_runtime_buffs"], 662.4 / 0.959
        )
        self.assertNotEqual(fast["damage"], 690 * 0.192)

    def test_four_shots_then_each_explicit_gap_interpretation(self):
        for extra, policy in (
            (0, "snapshot_timeBetweenBursts_is_post_last_shot_gap"),
            (
                0.192,
                "snapshot_timeBetweenBursts_is_extra_after_one_inter_shot_interval",
            ),
        ):
            with self.subTest(policy=policy):
                instance = multi_gear_instance()
                instance["multi_gear_parameters"]["burst_timing"] = policy
                actors, runtime, _, trace = self.multi_runtime(instance)
                source = actors["multi-gear"]
                times = []
                for _ in range(5):
                    time = source["next_attack"]
                    self.assertTrue(
                        runtime.launch(source, actors["primary"], actors, time, trace)
                    )
                    self.assertFalse(
                        runtime.launch(source, actors["primary"], actors, time, trace)
                    )
                    times.append(time)
                self.assertAlmostEqual(times[3], 0.576)
                self.assertAlmostEqual(times[4], 0.959 + extra)
                self.assertEqual(runtime.states[source["id"]]["burst_number"], 2)

    def test_normal_mode_has_one_shot_per_second(self):
        actors, runtime, combat, trace = self.multi_runtime(
            multi_gear_instance("normal")
        )
        source = actors["multi-gear"]
        runtime.launch(source, actors["primary"], actors, 0, trace)
        self.assertEqual(source["next_attack"], 1)
        self.assertEqual(combat.resolve(actors, 0, trace)["primary"], 370)

    def test_freeze_union_and_attack_rate_preserve_remaining_burst_work(self):
        actors, runtime, _, trace = self.multi_runtime()
        source = actors["multi-gear"]
        runtime.launch(source, actors["primary"], actors, 0, trace)
        _apply_effects(
            [
                {
                    "id": "freeze",
                    "kind": "freeze",
                    "targets": [source["id"]],
                    "duration_seconds": 1,
                }
            ],
            actors,
            0.1,
            trace,
        )
        self.assertAlmostEqual(source["next_attack"], 1.192)
        source["_hit_status_attack_rate"] = 0.5
        rescale_remaining_cooldown(source, 0.2, 1, 0.5)
        self.assertAlmostEqual(source["next_attack"], 1.284)
        self.assertFalse(runtime.launch(source, actors["primary"], actors, 1.2, trace))
        self.assertTrue(runtime.launch(source, actors["primary"], actors, 1.284, trace))
        self.assertEqual(runtime.states[source["id"]]["next_shot_index"], 2)

    def test_target_loss_preserves_shots_then_reacquires_in_declared_order(self):
        actors, runtime, _, trace = self.multi_runtime(
            others=[target(), target("backup", x=10)]
        )
        source = actors["multi-gear"]
        chosen, _ = runtime.select_target(source, actors, 0, set(), 40, 30)
        runtime.launch(source, chosen, actors, 0, trace)
        actors["backup"]["x"] = 8
        self.assertEqual(
            runtime.select_target(source, actors, 0.1, set(), 40, 30)[0]["id"],
            "primary",
        )
        actors["primary"]["hp"] = 0
        actors["backup"]["x"] = 30
        self.assertIsNone(runtime.select_target(source, actors, 0.2, set(), 40, 30)[0])
        self.assertEqual(runtime.states[source["id"]]["next_shot_index"], 1)
        actors["backup"]["x"] = 8
        chosen, _ = runtime.select_target(source, actors, 1, set(), 40, 30)
        runtime.launch(source, chosen, actors, 1, trace)
        self.assertEqual(runtime.states[source["id"]]["next_shot_index"], 2)

    def test_released_multi_gear_hit_survives_source_death_unreleased_shots_cancel(
        self,
    ):
        instance = multi_gear_instance()
        instance["attack_parameters"]["projectile"].update(
            timing="launch_distance_delay", speed_tiles_per_second=6
        )
        actors, runtime, combat, trace = self.multi_runtime(instance)
        source = actors["multi-gear"]
        runtime.launch(source, actors["primary"], actors, 0, trace)
        source["hp"] = 0
        runtime.prepare(actors, 0.2, trace)
        self.assertEqual(runtime.states[source["id"]]["cancelled_unreleased_shots"], 3)
        self.assertAlmostEqual(combat.resolve(actors, 1, trace)["primary"], 165.6)

    def test_missing_or_unrecognized_burst_and_fanout_policies_fail_closed(self):
        instances = []
        for field in ("burst_timing", "readiness_policy", "targeting"):
            instance = multi_gear_instance()
            del instance["multi_gear_parameters"][field]
            instances.append(instance)
        instance = super_wizard_instance()
        del instance["super_wizard_parameters"]["fanout"]["anchor"]
        instances.append(instance)
        instance = super_wizard_instance()
        instance["super_wizard_parameters"]["fanout"][
            "selection"
        ] = "electro_dragon_chain"
        instances.append(instance)
        instances.extend(
            [multi_gear_instance(town_hall=16), super_wizard_instance(supercharge=True)]
        )
        for instance in instances:
            with self.subTest(instance=instance), self.assertRaises(InputError):
                compiled_advanced(self.catalog, instance)

    def test_super_wizard_maps_primary_and_constant_secondary_damage_separately(self):
        actor = compiled_advanced(self.catalog, super_wizard_instance())
        self.assertEqual(
            (
                actor["hitpoints"],
                actor["damage"],
                actor["range"],
                actor["attack_interval_seconds"],
            ),
            (6000, 377, 8, 1.3),
        )
        self.assertEqual(actor["attack_model"]["kind"], FANOUT_PATTERN)
        self.assertAlmostEqual(
            actor["attack_model"]["secondary_damage_multiplier"], 0.4
        )
        instance = super_wizard_instance(level=2)
        instance["super_wizard_parameters"]["fanout"][
            "target_count_basis"
        ] = "snapshot_count_includes_primary"
        actor = compiled_advanced(self.catalog, instance)
        self.assertEqual(actor["attack_model"]["maximum_secondary_targets"], 14)
        self.assertEqual(actor["damage"], 416)

    def test_fanout_reaches_neighbors_of_primary_without_sequential_expansion(self):
        actors, packet, combat = self.fanout_fixture(
            others=[target("near", x=11), target("remote", x=12.5)]
        )
        released = self.release(actors, packet, combat)
        self.assertEqual([item[1]["target"] for item in released], ["near"])
        self.assertAlmostEqual(released[0][1]["flat_damage"], 150.8)
        self.assertEqual(released[0][1]["pattern"]["kind"], "single")

    def test_fanout_anchors_at_explicit_launch_or_impact_center(self):
        others = [target("old-neighbor", x=8), target("new-neighbor", x=15)]
        for anchor, expected in (
            ("primary_center_at_launch", "old-neighbor"),
            ("primary_center_at_primary_impact", "new-neighbor"),
        ):
            with self.subTest(anchor=anchor):
                actors, packet, combat = self.fanout_fixture(
                    fanout_parameters(anchor=anchor), others
                )
                actors["primary"]["x"] = 14
                self.assertEqual(
                    [
                        item[1]["target"]
                        for item in self.release(actors, packet, combat)
                    ],
                    [expected],
                )

    def test_fifteen_count_and_deterministic_nearest_or_strongest_selection(self):
        others = [
            target(f"neighbor-{index:02d}", x=10, hitpoints=100 + index)
            for index in range(18)
        ]
        for selection, expected in (
            (
                "nearest_then_instance_id",
                [f"neighbor-{index:02d}" for index in range(15)],
            ),
            (
                "highest_current_hp_then_distance_then_instance_id",
                [f"neighbor-{index:02d}" for index in range(17, 2, -1)],
            ),
        ):
            actors, packet, combat = self.fanout_fixture(
                fanout_parameters(selection=selection), list(reversed(others))
            )
            self.assertEqual(
                [item[1]["target"] for item in self.release(actors, packet, combat)],
                expected,
            )

    def test_primary_and_secondary_protection_are_independent_declared_policies(self):
        others = [target("protected", x=10), target("ordinary", x=10.5)]
        actors, packet, combat = self.fanout_fixture(others=others)
        actors["primary"]["immune_until"] = 1
        actors["protected"]["immune_until"] = 1
        self.assertEqual(len(self.release(actors, packet, combat)), 2)
        packet["pattern"]["fanout"]["primary_protection"] = "stop_fanout"
        self.assertEqual(self.release(actors, packet, combat), [])
        packet["pattern"]["fanout"].update(
            primary_protection="continue_fanout",
            secondary_protection="skip_protected_targets",
        )
        self.assertEqual(
            [item[1]["target"] for item in self.release(actors, packet, combat)],
            ["ordinary"],
        )

    def test_fanout_layer_visibility_and_exact_boundary_membership(self):
        others = [
            target("edge", x=11.5),
            target("outside", x=11.50001),
            target("air", x=10, layer="air", movement="air"),
            target("hidden", x=10),
        ]
        actors, packet, combat = self.fanout_fixture(others=others)
        actors["hidden"]["_spell_tower_untargetable_until"] = 1
        self.assertEqual(
            [item[1]["target"] for item in self.release(actors, packet, combat)],
            ["air", "edge"],
        )
        packet["pattern"]["fanout"]["target_layer_policy"] = "primary_target_layer_only"
        self.assertEqual(
            [item[1]["target"] for item in self.release(actors, packet, combat)],
            ["edge"],
        )

    def test_released_delayed_fanout_survives_primary_and_source_death(self):
        actors, packet, combat = self.fanout_fixture(
            fanout_parameters(delay_seconds=0.5), [target("neighbor", x=10)]
        )
        released = self.release(actors, packet, combat)
        for time, following in released:
            combat._queue(following, time)
        actors["super-wizard"]["hp"] = 0
        actors["primary"]["hp"] = 0
        actors["neighbor"]["x"] = 25
        trace = []
        self.assertFalse(combat.resolve(actors, 0.49, trace))
        self.assertAlmostEqual(combat.resolve(actors, 0.5, trace)["neighbor"], 150.8)

    def test_fixed_secondary_can_miss_and_dead_secondary_fizzles(self):
        for policy in ("move", "die"):
            actors, packet, combat = self.fanout_fixture(
                fanout_parameters(
                    delay_seconds=0.5,
                    secondary_destination="fixed_target_center_at_selection",
                ),
                [target("neighbor", x=10)],
            )
            for time, following in self.release(actors, packet, combat):
                combat._queue(following, time)
            if policy == "move":
                actors["neighbor"]["x"] = 12
            else:
                actors["neighbor"]["hp"] = 0
            trace = []
            self.assertFalse(combat.resolve(actors, 0.5, trace))
            self.assertEqual(
                trace[-1]["event"],
                "projectile_miss" if policy == "move" else "projectile_fizzle",
            )

    def test_profile_scales_primary_and_preserves_secondary_ratio(self):
        actor = compiled_advanced(self.catalog, super_wizard_instance())
        result = apply_battle_modifiers(
            {"actors": [actor]},
            modifier_policy("legend_i"),
            self.catalog,
            self.mode_rules,
        )
        modified = result["scene"]["actors"][0]
        self.assertAlmostEqual(modified["damage"], 377 * 1.2)
        self.assertAlmostEqual(
            modified["attack_model"]["secondary_damage_multiplier"], 0.4
        )

    def test_primary_fizzle_or_miss_cannot_release_fanout(self):
        for outcome in ("fizzle", "miss"):
            with self.subTest(outcome=outcome):
                actors, packet, combat = self.fanout_fixture(
                    others=[target("neighbor", x=10)]
                )
                projectile = actors["super-wizard"]["attack_model"]["projectile"]
                projectile.update(
                    timing="launch_distance_delay",
                    speed_tiles_per_second=12,
                    destination="fixed_target_center_at_launch",
                )
                combat = PatternCombat(actors)
                trace = []
                combat.launch(
                    actors["super-wizard"], actors["primary"], actors, 0, trace
                )
                if outcome == "fizzle":
                    actors["primary"]["hp"] = 0
                else:
                    actors["primary"]["x"] = 20
                self.assertFalse(combat.resolve(actors, 0.5, trace))
                self.assertEqual(trace[-1]["event"], f"projectile_{outcome}")
                self.assertFalse(
                    any(event["event"] == "fanout_release" for event in trace)
                )

    def test_fanout_pattern_rejects_generic_chain_and_unbounded_count(self):
        pattern = compiled_advanced(self.catalog, super_wizard_instance())[
            "attack_model"
        ]
        pattern["maximum_secondary_targets"] = 16
        with self.assertRaises(InputError):
            validate_fanout_pattern(pattern)
        with self.assertRaises(InputError):
            validate_fanout_pattern(synthetic_pattern("chain"))


if __name__ == "__main__":
    unittest.main()
