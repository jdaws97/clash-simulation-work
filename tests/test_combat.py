"""Coupled pattern/flight checks with explicit synthetic conventions."""

import unittest
from copy import deepcopy

from clashlab.combat import COMBAT_RULES, RULESET
from clashlab.common import InputError
from clashlab.spatial import simulate_spatial

from test_spatial import synthetic_scene, synthetic_structure, synthetic_unit


def synthetic_pattern(kind="single", **changes):
    pattern = {
        "kind": kind,
        "source": "synthetic-pattern-fixture-not-verified-Clash-semantics",
        "target_kinds": ["unit", "building", "defense", "wall"],
        "target_layers": ["ground", "air"],
        "maximum_hp_fraction": 0,
        "projectile": {
            "timing": "instant",
            "delay_seconds": 0,
            "destination": "locked_actor_center_at_impact",
            "hit_radius": 0,
        },
    }
    if kind == "radial":
        pattern["radius"] = 1.5
    elif kind == "chain":
        pattern.update(
            {
                "damage_multipliers": [1, 0.5, 0.25],
                "jump_range": 1.1,
                "jump_delay_seconds": 0,
                "jump_metric": "footprint_distance",
                "tie_break": "distance_then_instance_id",
                "allow_protected_links": True,
            }
        )
    elif kind == "multi_target":
        pattern.update(
            {
                "projectiles_per_volley": 3,
                "allocation": "cycle_distinct_targets_to_fill_volley",
            }
        )
    pattern.update(changes)
    return pattern


def pattern_scene(actors, effects=None, **changes):
    actors = deepcopy(actors)
    for actor in actors:
        actor["minimum_range"] = 0
        actor["attack_model"] = (
            synthetic_pattern() if actor["damage"] else synthetic_pattern("none")
        )
    scene = synthetic_scene(actors, effects, duration_seconds=1.25)
    scene["ruleset"] = RULESET
    scene["model_rules"] = deepcopy(COMBAT_RULES)
    scene.update(changes)
    return scene


def delayed_projectile_scene():
    scene = pattern_scene(
        [
            synthetic_unit(x=6.5, damage=100, attack_interval_seconds=1000),
            synthetic_structure(),
        ]
    )
    scene["actors"][0]["attack_model"]["projectile"] = {
        "timing": "launch_distance_delay",
        "speed_tiles_per_second": 1,
        "destination": "locked_actor_center_at_impact",
        "hit_radius": 0,
    }
    return scene


class CombatTests(unittest.TestCase):
    def test_projectile_arrives_after_launch_and_survives_firing_actor_death(self):
        scene = delayed_projectile_scene()
        scene["effects"] = [
            {
                "id": "kill-source",
                "time_seconds": 0.5,
                "kind": "damage",
                "targets": ["attacker"],
                "amount": 100,
            }
        ]
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["attacker"]["death_time"], 0.5)
        self.assertEqual(result["actors"]["tower"]["death_time"], 1)
        launch = next(
            event
            for event in result["trace"]
            if event.get("event") == "projectile_launch"
        )
        self.assertEqual(launch["time_seconds"], 0)
        self.assertEqual(launch["arrival_seconds"], 1)

    def test_freezing_source_after_release_does_not_stop_existing_projectile(self):
        scene = delayed_projectile_scene()
        scene["effects"] = [
            {
                "id": "late-freeze",
                "time_seconds": 0.5,
                "kind": "freeze",
                "targets": ["attacker"],
                "duration_seconds": 2,
            }
        ]
        self.assertEqual(simulate_spatial(scene)["actors"]["tower"]["hp"], 0)

    def test_protection_is_checked_at_impact_instead_of_only_at_launch(self):
        scene = delayed_projectile_scene()
        scene["effects"] = [
            {
                "id": "protect-before-impact",
                "time_seconds": 0.5,
                "kind": "invulnerability",
                "targets": ["tower"],
                "duration_seconds": 1,
            }
        ]
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["tower"]["hp"], 100)
        impact = next(
            event
            for event in result["trace"]
            if event.get("event") == "projectile_impact"
        )
        self.assertTrue(impact["protected"])

    def test_fixed_position_and_locked_target_differ_when_target_moves(self):
        scene = pattern_scene(
            [
                synthetic_unit(damage=1, hitpoints=100),
                synthetic_structure(damage=20, range=9, attack_interval_seconds=1000),
            ]
        )
        projectile = {
            "timing": "launch_distance_delay",
            "speed_tiles_per_second": 7,
            "destination": "fixed_target_center_at_launch",
            "hit_radius": 0,
        }
        scene["actors"][1]["attack_model"]["projectile"] = projectile
        fixed = simulate_spatial(scene)
        scene["actors"][1]["attack_model"]["projectile"][
            "destination"
        ] = "locked_actor_center_at_impact"
        locked = simulate_spatial(scene)
        self.assertEqual(fixed["actors"]["attacker"]["hp"], 100)
        self.assertEqual(locked["actors"]["attacker"]["hp"], 80)

    def test_radial_damage_reaches_footprint_edge_and_excludes_allies(self):
        actors = [
            synthetic_unit(x=2.5, damage=100, attack_interval_seconds=1000),
            synthetic_structure("primary", x=3, hitpoints=1000),
            synthetic_structure("edge", x=5, width=3, hitpoints=1000),
            synthetic_structure("outside", x=5, y=5, hitpoints=1000),
            synthetic_structure("ally", x=4, hitpoints=1000, team="attack"),
        ]
        scene = pattern_scene(actors)
        scene["actors"][0]["attack_model"] = synthetic_pattern("radial")
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["primary"]["hp"], 900)
        self.assertEqual(result["actors"]["edge"]["hp"], 900)
        self.assertEqual(result["actors"]["outside"]["hp"], 1000)
        self.assertEqual(result["actors"]["ally"]["hp"], 1000)

    def test_chain_decays_and_stops_when_layout_breaks_declared_jump_distance(self):
        actors = [
            synthetic_unit(x=2.5, damage=100, attack_interval_seconds=1000),
            synthetic_structure("primary", x=3, hitpoints=1000),
            synthetic_structure("middle", x=5, hitpoints=1000),
            synthetic_structure("last", x=7, hitpoints=1000),
        ]
        scene = pattern_scene(actors)
        scene["actors"][0]["attack_model"] = synthetic_pattern("chain")
        connected = simulate_spatial(scene)
        self.assertEqual(connected["actors"]["primary"]["hp"], 900)
        self.assertEqual(connected["actors"]["middle"]["hp"], 950)
        self.assertEqual(connected["actors"]["last"]["hp"], 975)
        scene["actors"][-1]["y"] = 6
        separated = simulate_spatial(scene)
        self.assertEqual(separated["actors"]["last"]["hp"], 1000)

    def test_chain_tie_rule_can_choose_higher_hp_without_silently_assuming_it(self):
        actors = [
            synthetic_unit(x=2.5, damage=100, attack_interval_seconds=1000),
            synthetic_structure("primary", x=3, hitpoints=1000),
            synthetic_structure("a-low", x=3, y=1, hitpoints=1000),
            synthetic_structure("z-high", x=3, y=5, hitpoints=1500),
        ]
        scene = pattern_scene(actors)
        pattern = synthetic_pattern(
            "chain",
            damage_multipliers=[1, 0.5],
            jump_range=2,
            jump_metric="center_distance",
        )
        scene["actors"][0]["attack_model"] = pattern
        identifier_tie = simulate_spatial(scene)
        pattern["tie_break"] = "distance_then_highest_current_hp_then_instance_id"
        hp_tie = simulate_spatial(scene)
        self.assertEqual(identifier_tie["actors"]["a-low"]["hp"], 950)
        self.assertEqual(hp_tie["actors"]["a-low"]["hp"], 1000)
        self.assertEqual(hp_tie["actors"]["z-high"]["hp"], 1450)

    def test_chain_continuation_through_protection_is_an_explicit_choice(self):
        actors = [
            synthetic_unit(x=2.5, damage=100, attack_interval_seconds=1000),
            synthetic_structure("primary", x=3, hitpoints=1000),
            synthetic_structure("middle", x=5, hitpoints=1000),
            synthetic_structure("last", x=7, hitpoints=1000),
        ]
        effects = [
            {
                "id": "shield-middle",
                "time_seconds": 0,
                "kind": "invulnerability",
                "targets": ["middle"],
                "duration_seconds": 2,
            }
        ]
        scene = pattern_scene(actors, effects)
        scene["actors"][0]["attack_model"] = synthetic_pattern("chain")
        continues = simulate_spatial(scene)
        scene["actors"][0]["attack_model"]["allow_protected_links"] = False
        stops = simulate_spatial(scene)
        self.assertEqual(continues["actors"]["middle"]["hp"], 1000)
        self.assertEqual(continues["actors"]["last"]["hp"], 975)
        self.assertEqual(stops["actors"]["last"]["hp"], 1000)

    def test_multi_target_volley_concentrates_extra_shots_when_fewer_targets_exist(
        self,
    ):
        for targets, expected in ((1, [40]), (2, [60, 80]), (3, [80, 80, 80])):
            actors = [
                synthetic_unit(f"unit-{index}", x=5.5 - index, damage=0)
                for index in range(targets)
            ]
            actors.append(
                synthetic_structure(damage=20, range=9, attack_interval_seconds=1000)
            )
            scene = pattern_scene(actors)
            scene["actors"][-1]["attack_model"] = synthetic_pattern("multi_target")
            result = simulate_spatial(scene)
            self.assertEqual(
                [result["actors"][f"unit-{index}"]["hp"] for index in range(targets)],
                expected,
            )

    def test_minimum_range_excludes_near_target_but_allows_far_target(self):
        scene = pattern_scene(
            [
                synthetic_unit("near", x=6.5, damage=0),
                synthetic_unit("far", x=0.5, damage=0),
                synthetic_structure(damage=20, range=9, attack_interval_seconds=1000),
            ]
        )
        scene["actors"][-1]["minimum_range"] = 3
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["near"]["hp"], 100)
        self.assertEqual(result["actors"]["far"]["hp"], 80)

    def test_percentage_damage_uses_maximum_hp_not_remaining_hp(self):
        scene = pattern_scene(
            [
                synthetic_unit(x=6.5, damage=10, attack_interval_seconds=1000),
                synthetic_structure(),
            ],
            [
                {
                    "id": "prior-damage",
                    "time_seconds": 0,
                    "kind": "damage",
                    "targets": ["tower"],
                    "amount": 50,
                }
            ],
        )
        scene["actors"][0]["attack_model"]["maximum_hp_fraction"] = 0.2
        self.assertEqual(simulate_spatial(scene)["actors"]["tower"]["hp"], 20)

    def test_deployment_precedes_same_time_area_healing_and_damage(self):
        scene = pattern_scene(
            [
                synthetic_unit("main", spawn_seconds="controlled", x=6.5, damage=0),
                synthetic_structure(),
            ],
            [
                {
                    "id": "deploy",
                    "time_seconds": 0,
                    "kind": "deploy",
                    "targets": ["main"],
                    "positions": {"main": {"x": 6.5, "y": 3.5}},
                },
                {
                    "id": "hurt",
                    "time_seconds": 0,
                    "kind": "damage",
                    "targets": ["main"],
                    "amount": 40,
                },
                {
                    "id": "heal-area",
                    "time_seconds": 0,
                    "kind": "area_heal",
                    "area": {
                        "x": 6.5,
                        "y": 3.5,
                        "radius": 0.1,
                        "target_team": "attack",
                        "target_kinds": ["unit"],
                        "target_layers": ["ground"],
                    },
                    "amount": 20,
                },
            ],
        )
        self.assertEqual(simulate_spatial(scene)["actors"]["main"]["hp"], 80)

    def test_projectiles_beyond_horizon_are_reported_and_do_not_hit_early(self):
        scene = delayed_projectile_scene()
        scene["duration_seconds"] = 0.5
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["tower"]["hp"], 100)
        self.assertEqual(len(result["combat"]["pending_projectiles_at_horizon"]), 1)

    def test_missing_pattern_and_unsupported_moving_kiting_fail_closed(self):
        scene = delayed_projectile_scene()
        del scene["actors"][0]["attack_model"]
        with self.assertRaisesRegex(InputError, "attack_model"):
            simulate_spatial(scene)
        scene = delayed_projectile_scene()
        scene["actors"][0]["minimum_range"] = 0.1
        with self.assertRaisesRegex(InputError, "kiting adapter"):
            simulate_spatial(scene)


if __name__ == "__main__":
    unittest.main()
