"""Coupled breach/follower checks for explicit, unvalidated motion profiles."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.adapters import (
    WALL_SCOPE,
    compile_entity_scene,
    simulate_entity_closed_loop,
    simulate_entity_scene,
)
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.spatial import simulate_spatial
from clashlab.walls import RULESET, WALL_RULES, WallRouting

from test_adapters import entity_instance, sector
from test_combat import pattern_scene
from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]


def breach_profile(kind="clear_obstructions", **changes):
    profile = {
        "kind": kind,
        "source": "synthetic-wall-motion-hypothesis-not-Clash-calibration",
        "route_cost": "travel_seconds_plus_nominal_clearance",
        "weapon": {
            "damage": 100,
            "range": 0.6,
            "attack_interval_seconds": 0.4,
            "first_attack_seconds": 0,
            "timing": "instant",
            "cooldown": "independent_from_main_weapon",
            "source": "synthetic-wall-weapon-not-player-data",
        },
    }
    profile.update(changes)
    return profile


def wall_scene(kind="clear_obstructions", wall_hp=300, **changes):
    actors = [
        synthetic_unit("breacher", x=3.5, hitpoints=1000, damage=50),
        synthetic_unit("follower", hitpoints=1000, damage=10),
        synthetic_structure(hitpoints=50000),
        *[
            synthetic_structure(
                f"wall-{row}",
                x=4,
                y=row,
                kind="wall",
                hitpoints=wall_hp,
                counts_for_destruction=False,
            )
            for row in range(7)
        ],
    ]
    scene = pattern_scene(actors, duration_seconds=4, maximum_step_seconds=0.05)
    scene["ruleset"] = RULESET
    scene["model_rules"] = deepcopy(WALL_RULES)
    scene["actors"][0]["wall_behavior"] = breach_profile(kind)
    scene["actors"][1]["wall_behavior"] = {
        "kind": "avoid",
        "source": "synthetic-follow-existing-opening-only",
    }
    scene.update(changes)
    return scene


def wall_parameters(kind="clear_obstructions"):
    return {
        "kind": kind,
        "route_cost": "travel_seconds_plus_nominal_clearance",
        "cooldown": "independent_from_main_weapon",
        "range": 1,
        "first_attack_seconds": 0,
        "impact_timing": "instant",
        "source": "explicit-unvalidated-Root-Rider-motion-hypothesis",
    }


class WallRoutingTests(unittest.TestCase):
    def test_cached_routes_react_to_live_wall_hp_rates_and_mutable_route_consumption(
        self,
    ):
        actor = synthetic_unit(x=0.5, y=1.5, range=0)
        actor["wall_behavior"] = breach_profile()
        target = synthetic_structure(x=2.5, y=1.5, width=0, height=0)
        walls = {(1, 1): {"hp": 300}}

        def route():
            return WallRouting._virtual_route(actor, target, walls, set(), 3, 3)

        detour, cost = route()
        self.assertEqual(cost, 2)
        self.assertEqual(detour, [(0.5, 0.5), (1.5, 0.5), (2.5, 0.5), (2.5, 1.5)])
        detour.clear()
        self.assertEqual(len(route()[0]), 4)
        walls[(1, 1)]["hp"] = 100
        self.assertEqual(route(), ([(1.5, 1.5), (2.5, 1.5)], 1.4))
        walls[(1, 1)]["hp"] = 300
        self.assertEqual(route()[1], 2)
        for field in ("_buff_damage_multiplier", "_hazard_attack_rate"):
            actor[field] = 3
            points, cost = route()
            self.assertEqual(points, [(1.5, 1.5), (2.5, 1.5)])
            self.assertAlmostEqual(cost, 1.4)
            del actor[field]
            self.assertEqual(route()[1], 2)
        actor["speed"] = 1
        self.assertEqual(route(), ([(1.5, 1.5), (2.5, 1.5)], 3.2))

    def test_breach_opens_a_shared_route_and_followers_reach_the_defense(self):
        result = simulate_spatial(wall_scene())
        self.assertAlmostEqual(result["actors"]["wall-3"]["death_time"], 0.8)
        self.assertGreater(result["actors"]["follower"]["x"], 4)
        shots = [
            event
            for event in result["trace"]
            if event.get("event") == "projectile_launch"
            and event["source"] == "follower"
        ]
        self.assertTrue(shots)
        self.assertGreaterEqual(shots[0]["time_seconds"], 0.8)
        wall_hits = [
            event for event in result["trace"] if event.get("event") == "wall_impact"
        ]
        self.assertEqual(len(wall_hits), 3)
        self.assertTrue(
            all(event["intended_primary_target"] == "tower" for event in wall_hits)
        )
        self.assertFalse(result["full_game_prediction"])

    def test_losing_breacher_before_final_hit_leaves_followers_outside(self):
        scene = wall_scene()
        scene["effects"] = [
            {
                "id": "lose-breacher",
                "kind": "damage",
                "time_seconds": 0.6,
                "targets": ["breacher"],
                "amount": 1000,
            }
        ]
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["wall-3"]["hp"], 100)
        self.assertEqual(result["actors"]["follower"]["x"], 0.5)

    def test_short_melee_follower_reaches_footprint_edge_after_breach(self):
        scene = wall_scene()
        scene["actors"][1]["range"] = 0.4
        result = simulate_spatial(scene)
        self.assertAlmostEqual(result["actors"]["follower"]["x"], 6.6)
        self.assertTrue(
            any(
                event.get("event") == "projectile_launch"
                and event["source"] == "follower"
                for event in result["trace"]
            )
        )

    def test_short_melee_weapon_can_approach_and_clear_a_wall(self):
        scene = wall_scene(wall_hp=50)
        breacher = scene["actors"][0]
        breacher["range"] = 0.4
        weapon = breacher["wall_behavior"]["weapon"]
        weapon.update(
            {
                "damage": 50,
                "range": 0.4,
                "cooldown": "shared_with_main_weapon",
                "attack_interval_seconds": 1,
            }
        )
        result = simulate_spatial(scene)
        self.assertAlmostEqual(result["actors"]["wall-3"]["death_time"], 0.05)
        self.assertGreater(result["actors"]["breacher"]["x"], 4)

    def test_penetration_and_clear_before_crossing_are_distinct_hypotheses(self):
        stopped = simulate_spatial(wall_scene(wall_hp=10000, duration_seconds=1))
        crossing = simulate_spatial(
            wall_scene("penetrate_obstructions", wall_hp=10000, duration_seconds=1)
        )
        self.assertEqual(stopped["actors"]["breacher"]["x"], 3.5)
        self.assertGreater(crossing["actors"]["breacher"]["x"], 5)
        self.assertGreater(crossing["actors"]["wall-3"]["hp"], 0)
        self.assertEqual(crossing["actors"]["follower"]["x"], 0.5)

    def test_overlapping_freezes_pause_independent_wall_weapon_without_double_extension(
        self,
    ):
        scene = wall_scene(duration_seconds=2)
        scene["effects"] = [
            {
                "id": "first-freeze",
                "kind": "freeze",
                "time_seconds": 0.2,
                "targets": ["breacher"],
                "duration_seconds": 0.5,
            },
            {
                "id": "overlapping-freeze",
                "kind": "freeze",
                "time_seconds": 0.3,
                "targets": ["breacher"],
                "duration_seconds": 0.6,
            },
        ]
        result = simulate_spatial(scene)
        times = [
            event["time_seconds"]
            for event in result["trace"]
            if event.get("event") == "wall_impact"
        ]
        self.assertEqual(len(times), 3)
        for actual, expected in zip(times, [0, 1.1, 1.5]):
            self.assertAlmostEqual(actual, expected)

    def test_wall_protection_prevents_damage_and_still_spends_the_hit_clock(self):
        scene = wall_scene(duration_seconds=0.8)
        scene["effects"] = [
            {
                "id": "protect-wall",
                "kind": "invulnerability",
                "time_seconds": 0,
                "targets": ["wall-3"],
                "duration_seconds": 0.5,
            }
        ]
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["wall-3"]["hp"], 200)
        impacts = [
            event for event in result["trace"] if event.get("event") == "wall_impact"
        ]
        self.assertEqual([event["protected"] for event in impacts], [True, True, False])

    def test_shared_clock_prevents_an_extra_main_hit_after_opening(self):
        scene = wall_scene(wall_hp=50, duration_seconds=1.25)
        scene["actors"][2]["x"] = 5
        weapon = scene["actors"][0]["wall_behavior"]["weapon"]
        weapon["damage"] = 50
        weapon["range"] = 0.8
        weapon["cooldown"] = "shared_with_main_weapon"
        weapon["attack_interval_seconds"] = 1
        result = simulate_spatial(scene)
        shots = [
            event
            for event in result["trace"]
            if event.get("event") == "projectile_launch"
            and event["source"] == "breacher"
        ]
        self.assertTrue(shots)
        self.assertAlmostEqual(shots[0]["time_seconds"], 1)

    def test_allied_walls_are_not_penetrable_or_weapon_targets(self):
        scene = wall_scene("penetrate_obstructions")
        for actor in scene["actors"]:
            if actor["kind"] == "wall":
                actor["team"] = "attack"
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["breacher"]["x"], 3.5)
        self.assertFalse(
            any(event.get("event") == "wall_impact" for event in result["trace"])
        )

    def test_wall_hits_and_projectiles_share_simultaneous_health_application(self):
        scene = wall_scene(wall_hp=150, duration_seconds=0.05)
        scene["actors"][1]["x"] = 3.5
        scene["actors"][1]["wall_behavior"] = breach_profile()
        result = simulate_spatial(scene)
        hits = [
            event for event in result["trace"] if event.get("event") == "wall_impact"
        ]
        self.assertEqual(len(hits), 2)
        self.assertEqual(result["actors"]["wall-3"]["death_time"], 0)

    def test_unknown_motion_missing_ground_profile_and_legacy_silent_fallback_rejected(
        self,
    ):
        original = wall_scene()
        cases = [deepcopy(original) for _ in range(3)]
        cases[0]["actors"][0]["wall_behavior"]["kind"] = "pretend-actual-game"
        del cases[1]["actors"][1]["wall_behavior"]
        cases[2]["ruleset"] = "spatial-projectile-pattern-kernel-v2"
        for scene in cases:
            with self.assertRaises(InputError):
                simulate_spatial(scene)


class WallEntityAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def scene(self):
        entities = [
            entity_instance(
                "root",
                "root-rider",
                3,
                "attack",
                x=3.5,
                wall_parameters=wall_parameters(),
            ),
            entity_instance(
                "wall",
                "wall",
                17,
                "defense",
                x=4,
                y=5,
                mode="passive",
                statistics_mode="none",
                attack_parameters={},
                inactive_attack_interval_seconds=1,
                counts_for_destruction=False,
            ),
        ]
        spec = sector(self.catalog, entities)
        spec["scope"] = WALL_SCOPE
        spec["model_rules"] = deepcopy(WALL_RULES)
        return spec

    def test_selected_root_and_wall_stats_remain_separate_from_motion_hypothesis(self):
        compiled = compile_entity_scene(self.scene(), self.catalog)
        root, wall = compiled["scene"]["actors"]
        self.assertEqual(root["hitpoints"], 6500)
        self.assertEqual(root["damage"], 253)
        self.assertEqual(root["wall_behavior"]["weapon"]["damage"], 4000)
        self.assertEqual(
            root["wall_behavior"]["weapon"]["attack_interval_seconds"], 0.4
        )
        self.assertEqual(root["target_priority_tiers"], [["defense"], ["building"]])
        self.assertEqual(wall["hitpoints"], 12000)
        self.assertFalse(compiled["full_game_prediction"])
        self.assertEqual(
            root["entity_adapter"]["wall_behavior_verification"],
            "selected_hypothesis_not_replay_validated",
        )

    def test_wall_parameters_cannot_be_omitted_or_used_to_disable_root_breaching(self):
        cases = [self.scene(), self.scene()]
        del cases[0]["entities"][0]["wall_parameters"]
        cases[1]["entities"][0]["wall_parameters"] = {
            "kind": "avoid",
            "source": "unsupported-shortcut",
        }
        for scene in cases:
            with self.assertRaises(InputError):
                compile_entity_scene(scene, self.catalog)

    def test_root_prefers_defense_over_a_closer_resource_building(self):
        scene = self.scene()
        scene["entities"] = [
            scene["entities"][0],
            entity_instance(
                "defense", "cannon", 21, "defense", x=10, first_attack_seconds=10
            ),
            entity_instance(
                "resource",
                "elixir-storage",
                17,
                "defense",
                x=4,
                mode="passive",
                statistics_mode="none",
                attack_parameters={},
                inactive_attack_interval_seconds=1,
            ),
        ]
        result = simulate_entity_scene(scene, self.catalog)
        self.assertEqual(result["combat"]["actors"]["root"]["target"], "defense")

    def test_protection_timing_changes_breach_and_followup_deployment_with_same_entities(
        self,
    ):
        scene = read_json(ROOT / "examples/entity-wall-sector-conditional.json")
        scene["duration_seconds"] = 6
        outcomes = {}
        for response in ("timely", "late"):
            result = simulate_entity_closed_loop(
                scene,
                self.catalog,
                read_json(ROOT / "examples/entity-wall-plan-synthetic.json"),
                read_json(ROOT / "examples" / f"entity-wall-{response}-synthetic.json"),
                seed=7,
                trials=1,
            )
            outcomes[response] = result["human_combat"]["samples"][0]
        early = outcomes["timely"]
        late = outcomes["late"]
        self.assertEqual(early["combat"]["actors"]["wall-5"]["hp"], 0)
        self.assertIsInstance(
            early["combat"]["actors"]["follower-0"]["spawn_seconds"], float
        )
        self.assertEqual(late["combat"]["actors"]["wall-5"]["hp"], 4000)
        self.assertEqual(
            late["combat"]["actors"]["follower-0"]["spawn_seconds"], "controlled"
        )
        self.assertEqual(late["control"]["actions"][0]["status"], "cue_no_longer_valid")
        self.assertEqual(late["control"]["remaining_resources"]["protection_cast"], 1)


if __name__ == "__main__":
    unittest.main()
