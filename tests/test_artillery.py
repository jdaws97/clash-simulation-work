"""Conditional TH17 impacts, flame clocks and survivor behavior."""

import unittest
from copy import deepcopy
from math import hypot
from pathlib import Path

from clashlab.adapters import compile_entity_scene, simulate_entity_scene
from clashlab.artillery import RULES, RULESET, SCOPE, ArtilleryCombat
from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError
from clashlab.heroes import HERO_RULES, RULESET as HERO_RULESET
from clashlab.spatial import _load_actors, simulate_spatial

from test_adapters import entity_instance, projectile
from test_defense_patterns import area_sector


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "declared-artillery-contract-fixture-not-current-game-calibration"


def flame_parameters(overlap="maximum_active_pool_dps_at_source_clock", **changes):
    parameters = {
        "source": SOURCE,
        "radius": 1,
        "duration_multiplier": 1,
        "maximum_dps_multiplier": 1,
        "growth_by_field_age": [{"after_seconds": 0, "dps_multiplier": 1}],
        "pulse_interval_seconds": 0.5,
        "first_pulse_offset_seconds": 0,
        "excluded_classes": ["siege"],
        "overlap_policy": overlap,
        "pulse_clock_policy": "first_pool_then_continuous_while_any_pool_alive",
        "trigger_policy": "resolved_projectile_including_protected_primary",
        "pool_on_projectile_miss": True,
        "fizzle_policy": "no_pool_when_primary_fizzles",
        "source_freeze_policy": "released_pools_keep_pulsing_hypothesis",
    }
    parameters.update(changes)
    return parameters


def artillery_hall(flame=None, **changes):
    flight = projectile()
    flight["inactive_primary_policy"] = "fizzle"
    instance = entity_instance(
        "hall",
        "town-hall",
        17,
        "defense",
        town_hall=17,
        mode="infernoArtillery",
        statistics_mode="weapon",
        attack_parameters={
            "projectile": flight,
            "allocation": "cycle_distinct_targets_to_fill_volley",
        },
        town_hall_parameters={
            "source": SOURCE,
            "weapon_level": 5,
            "flame": flame_parameters() if flame is None else flame,
            "source_death_policy": "released_projectiles_and_pools_persist_hypothesis",
        },
    )
    instance.update(changes)
    return instance


def recipient(name="unit", **changes):
    instance = entity_instance(
        name, "minion", 12, "attack", first_attack_seconds=1000, **changes
    )
    instance["modifiers"]["hitpoints_multiplier"] = 100
    return instance


def artillery_sector(catalog, entities, duration=0.1, effects=None):
    scene = area_sector(catalog, entities)
    scene.update(
        scope=SCOPE,
        model_rules=deepcopy(RULES),
        duration_seconds=duration,
        maximum_step_seconds=0.05,
        recording_interval_seconds=0.05,
        effects=[] if effects is None else effects,
    )
    return scene


def damage(target, time, amount):
    return {
        "id": f"synthetic-hit-{target}-{time}",
        "kind": "damage",
        "targets": [target],
        "time_seconds": time,
        "amount": amount,
    }


def protect(target, time=0, duration=2):
    return {
        "id": "synthetic-protection",
        "kind": "invulnerability",
        "targets": [target],
        "time_seconds": time,
        "duration_seconds": duration,
    }


def native_scene(catalog, entities, duration=0.1, effects=None):
    return compile_entity_scene(
        artillery_sector(catalog, entities, duration, effects), catalog
    )["scene"]


class ArtilleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_th17_is_separate_from_giga_and_uses_selected_source_statistics(self):
        scene = artillery_sector(self.catalog, [artillery_hall(), recipient()])
        actor = compile_entity_scene(scene, self.catalog)["scene"]["actors"][0]
        self.assertEqual(actor["hitpoints"], 10400)
        self.assertEqual(actor["damage"], 210)
        self.assertEqual(actor["attack_interval_seconds"], 3.5)
        self.assertEqual((actor["width"], actor["height"]), (4, 4))
        self.assertEqual(actor["attack_model"]["projectiles_per_volley"], 4)
        self.assertNotIn("death_model", actor)
        self.assertNotIn("town_hall_model", actor)
        model = actor["artillery_model"]["flame"]
        self.assertEqual(model["maximum_dps"], 75)
        self.assertEqual(model["duration_seconds"], 6.8)

    def test_weapon_is_immediately_active_and_repeats_four_shots_on_one_target(self):
        result = simulate_entity_scene(
            artillery_sector(self.catalog, [artillery_hall(), recipient()]),
            self.catalog,
        )["combat"]
        launches = [
            event
            for event in result["trace"]
            if event.get("event") == "projectile_launch"
        ]
        self.assertEqual(len(launches), 4)
        self.assertEqual({event["time_seconds"] for event in launches}, {0})
        initial_hp = self.catalog.level("minion", 12)["hitpoints"] * 100
        self.assertAlmostEqual(result["actors"]["unit"]["hp"], initial_hp - 840 - 37.5)
        self.assertEqual(len(result["artillery_flames"]["pools"]), 4)
        self.assertEqual(
            len(result["frames"][0]["actors"]["unit"]["artillery_flame_pools"]), 4
        )

    def test_four_targets_receive_distinct_direct_hits_without_direct_splash(self):
        units = [recipient(f"unit-{index}", x=6.5, y=4.5 + index) for index in range(4)]
        hall = artillery_hall(flame_parameters(radius=0.2, maximum_dps_multiplier=0))
        result = simulate_entity_scene(
            artillery_sector(self.catalog, [hall, *units]), self.catalog
        )["combat"]
        impacts = [
            event
            for event in result["trace"]
            if event.get("event") == "projectile_impact"
        ]
        self.assertEqual(len(impacts), 4)
        self.assertEqual(
            {event["target"] for event in impacts}, {unit["id"] for unit in units}
        )
        self.assertEqual({event["damage"] for event in impacts}, {210})

    def test_three_targets_use_balanced_repeated_allocation(self):
        units = [recipient(f"unit-{index}", x=6.5, y=4.5 + index) for index in range(3)]
        hall = artillery_hall(flame_parameters(maximum_dps_multiplier=0))
        result = simulate_entity_scene(
            artillery_sector(self.catalog, [hall, *units]), self.catalog
        )["combat"]
        hits = {unit["id"]: 0 for unit in units}
        for event in result["trace"]:
            if event.get("event") == "projectile_impact":
                hits[event["target"]] += 1
        self.assertEqual(sorted(hits.values()), [1, 1, 2])

    def test_overlap_hypotheses_change_flame_damage_without_changing_direct_hits(self):
        outcomes = {}
        for policy in (
            "additive_independent_pool_clocks",
            "maximum_active_pool_dps_at_source_clock",
        ):
            result = simulate_entity_scene(
                artillery_sector(
                    self.catalog,
                    [artillery_hall(flame_parameters(policy)), recipient()],
                ),
                self.catalog,
            )["combat"]
            outcomes[policy] = result["actors"]["unit"]["hp"]
        self.assertAlmostEqual(
            outcomes["maximum_active_pool_dps_at_source_clock"]
            - outcomes["additive_independent_pool_clocks"],
            3 * 37.5,
        )

    def test_protected_impact_creates_flames_only_under_selected_trigger_policy(self):
        for policy, expected in (
            ("resolved_projectile_including_protected_primary", 4),
            ("only_unprotected_direct_hit", 0),
        ):
            scene = artillery_sector(
                self.catalog,
                [artillery_hall(flame_parameters(trigger_policy=policy)), recipient()],
                effects=[protect("unit")],
            )
            result = simulate_entity_scene(scene, self.catalog)["combat"]
            self.assertEqual(len(result["artillery_flames"]["pools"]), expected)
            self.assertEqual(
                result["actors"]["unit"]["hp"], result["actors"]["unit"]["maximum_hp"]
            )

    def test_released_projectiles_and_pools_continue_after_source_death(self):
        hall = artillery_hall()
        flight = hall["attack_parameters"]["projectile"]
        flight.pop("delay_seconds")
        flight.update(
            timing="launch_distance_delay", speed_tiles_per_second=hypot(2.5, 0.5)
        )
        scene = artillery_sector(
            self.catalog,
            [hall, recipient()],
            duration=2,
            effects=[damage("hall", 0.5, 10401)],
        )
        result = simulate_entity_scene(scene, self.catalog)["combat"]
        self.assertEqual(result["actors"]["hall"]["hp"], 0)
        releases = [
            event
            for event in result["trace"]
            if event.get("event") == "artillery_flame_release"
        ]
        self.assertEqual(len(releases), 4)
        self.assertEqual({event["time_seconds"] for event in releases}, {1})
        pulses = [
            event
            for event in result["trace"]
            if event.get("event") == "artillery_flame_pulse"
        ]
        self.assertEqual([event["time_seconds"] for event in pulses], [1, 1.5, 2])
        initial_hp = self.catalog.level("minion", 12)["hitpoints"] * 100
        self.assertAlmostEqual(
            result["actors"]["unit"]["hp"], initial_hp - 840 - 3 * 37.5
        )
        self.assertFalse(
            any(event.get("event") == "town_hall_death" for event in result["trace"])
        )

    def test_dead_primary_fizzles_without_creating_a_flame(self):
        hall = artillery_hall()
        flight = hall["attack_parameters"]["projectile"]
        flight.pop("delay_seconds")
        flight.update(
            timing="launch_distance_delay", speed_tiles_per_second=hypot(2.5, 0.5)
        )
        scene = artillery_sector(
            self.catalog,
            [hall, recipient()],
            duration=1.5,
            effects=[damage("unit", 0.5, 100000)],
        )
        result = simulate_entity_scene(scene, self.catalog)["combat"]
        self.assertEqual(result["artillery_flames"]["pools"], {})
        self.assertEqual(
            sum(event.get("event") == "projectile_fizzle" for event in result["trace"]),
            4,
        )

    def test_nonstacking_clock_does_not_restart_when_another_pool_arrives(self):
        scene = native_scene(self.catalog, [artillery_hall(), recipient()])
        actors = _load_actors(scene, 14, 12)
        runtime = ArtilleryCombat(actors)
        event = {
            "source": "hall",
            "primary_target": "unit",
            "position": (7.5, 5.5),
            "hit_count": 1,
            "primary_protected": False,
        }
        trace = []
        runtime.impact(event, actors, 0, trace)
        self.assertEqual(runtime.resolve(actors, 0, trace)["unit"], 37.5)
        runtime.impact(event, actors, 0.2, trace)
        self.assertEqual(runtime.resolve(actors, 0.2, trace), {})
        self.assertEqual(runtime.resolve(actors, 0.5, trace)["unit"], 37.5)
        self.assertEqual(runtime.source_clocks["hall"], 1)

    def test_missed_fixed_destination_shots_follow_explicit_pool_policy(self):
        for create_pool in (False, True):
            hall = artillery_hall(flame_parameters(pool_on_projectile_miss=create_pool))
            flight = hall["attack_parameters"]["projectile"]
            flight.pop("delay_seconds")
            flight.update(
                timing="launch_distance_delay",
                speed_tiles_per_second=hypot(2.5, 0.5),
                destination="fixed_target_center_at_launch",
            )
            scene = native_scene(self.catalog, [hall, recipient()])
            actors = _load_actors(scene, 14, 12)
            combat = PatternCombat(actors)
            runtime = ArtilleryCombat(actors)
            trace = []
            combat.launch(actors["hall"], actors["unit"], actors, 0, trace)
            actors["unit"]["x"] = 5.5
            direct_damage = combat.resolve(actors, 1, trace, runtime.impact)
            self.assertEqual(direct_damage, {})
            self.assertEqual(len(runtime.pools), 4 if create_pool else 0)
            self.assertTrue(
                all(pool["position"] == (7.5, 5.5) for pool in runtime.pools.values())
            )

    def test_nonstacking_growth_uses_strongest_live_pool_without_resetting_age(self):
        growth = [
            {"after_seconds": 0, "dps_multiplier": 0.25},
            {"after_seconds": 1, "dps_multiplier": 1},
        ]
        scene = native_scene(
            self.catalog,
            [artillery_hall(flame_parameters(growth_by_field_age=growth)), recipient()],
        )
        actors = _load_actors(scene, 14, 12)
        runtime = ArtilleryCombat(actors)
        event = {
            "source": "hall",
            "primary_target": "unit",
            "position": (7.5, 5.5),
            "hit_count": 1,
            "primary_protected": False,
        }
        trace = []
        runtime.impact(event, actors, 0, trace)
        self.assertEqual(runtime.resolve(actors, 0, trace)["unit"], 9.375)
        self.assertEqual(runtime.resolve(actors, 0.5, trace)["unit"], 9.375)
        runtime.impact(event, actors, 1, trace)
        self.assertEqual(runtime.resolve(actors, 1, trace)["unit"], 37.5)

    def test_delayed_protection_changes_survival_without_changing_the_army(self):
        final_hp = {}
        for label, activation in (("timely", 0), ("late", 0.1)):
            hall = artillery_hall()
            unit = recipient()
            unit["modifiers"]["hitpoints_multiplier"] = 1
            scene = artillery_sector(
                self.catalog,
                [hall, unit],
                duration=0.5,
                effects=[protect("unit", activation)],
            )
            result = simulate_entity_scene(scene, self.catalog)["combat"]
            final_hp[label] = result["actors"]["unit"]["hp"]
        self.assertEqual(final_hp["late"], 0)
        self.assertGreater(final_hp["timely"], 0)

    def test_unknown_projectile_fields_are_not_silently_ignored(self):
        hall = artillery_hall()
        hall["attack_parameters"]["projectile"]["splash_radius"] = 3
        with self.assertRaisesRegex(InputError, "exact supported fields"):
            compile_entity_scene(
                artillery_sector(self.catalog, [hall, recipient()]), self.catalog
            )

    def test_source_freeze_does_not_cancel_fields_under_declared_policy(self):
        freeze = {
            "id": "synthetic-source-freeze",
            "kind": "freeze",
            "targets": ["hall"],
            "time_seconds": 0.5,
            "duration_seconds": 5,
        }
        result = simulate_entity_scene(
            artillery_sector(
                self.catalog,
                [artillery_hall(), recipient()],
                duration=2,
                effects=[freeze],
            ),
            self.catalog,
        )["combat"]
        initial_hp = self.catalog.level("minion", 12)["hitpoints"] * 100
        self.assertAlmostEqual(
            result["actors"]["unit"]["hp"], initial_hp - 840 - 5 * 37.5
        )

    def test_membership_uses_live_position_and_both_layers_but_excludes_declared_siege(
        self,
    ):
        scene = native_scene(
            self.catalog,
            [
                artillery_hall(),
                recipient("air"),
                recipient("ground"),
                recipient("siege"),
            ],
        )
        actors = _load_actors(scene, 14, 12)
        actors["ground"]["layer"] = "ground"
        actors["siege"]["hazard_class"] = "siege"
        runtime = ArtilleryCombat(actors)
        trace = []
        runtime.impact(
            {
                "source": "hall",
                "primary_target": "air",
                "position": (7.5, 5.5),
                "hit_count": 1,
                "primary_protected": False,
            },
            actors,
            0,
            trace,
        )
        self.assertEqual(set(runtime.resolve(actors, 0, trace)), {"air", "ground"})
        actors["air"]["x"] = 1
        self.assertEqual(set(runtime.resolve(actors, 0.5, trace)), {"ground"})
        actors["air"]["x"] = 7.5
        self.assertEqual(set(runtime.resolve(actors, 1, trace)), {"air", "ground"})

    def test_protection_advances_clock_and_expiry_is_exclusive(self):
        scene = native_scene(self.catalog, [artillery_hall(), recipient()])
        actors = _load_actors(scene, 14, 12)
        actors["unit"]["immune_until"] = 1
        runtime = ArtilleryCombat(actors)
        trace = []
        runtime.impact(
            {
                "source": "hall",
                "primary_target": "unit",
                "position": (7.5, 5.5),
                "hit_count": 1,
                "primary_protected": True,
            },
            actors,
            0,
            trace,
        )
        self.assertEqual(runtime.resolve(actors, 0, trace), {})
        self.assertEqual(runtime.resolve(actors, 0.5, trace), {})
        self.assertEqual(runtime.resolve(actors, 1, trace)["unit"], 37.5)
        self.assertEqual(runtime.resolve(actors, 6.8, trace), {})
        self.assertEqual(
            runtime.frame(actors["unit"], 6.8)["artillery_flame_pools"], []
        )

    def test_unspecified_flame_behavior_and_giga_parameters_are_rejected(self):
        for field in flame_parameters():
            parameters = flame_parameters()
            del parameters[field]
            with self.subTest(field=field), self.assertRaises(InputError):
                compile_entity_scene(
                    artillery_sector(
                        self.catalog, [artillery_hall(parameters), recipient()]
                    ),
                    self.catalog,
                )
        hall = artillery_hall()
        hall["town_hall_parameters"]["activation"] = {"initial_state": "dormant"}
        with self.assertRaisesRegex(InputError, "cannot inherit Giga"):
            compile_entity_scene(
                artillery_sector(self.catalog, [hall, recipient()]), self.catalog
            )

    def test_artillery_models_cannot_silently_run_under_a_previous_ruleset(self):
        scene = native_scene(self.catalog, [artillery_hall(), recipient()])
        scene["ruleset"] = HERO_RULESET
        scene["model_rules"] = deepcopy(HERO_RULES)
        with self.assertRaisesRegex(InputError, "Artillery"):
            simulate_spatial(scene)


if __name__ == "__main__":
    unittest.main()
