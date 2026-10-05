"""Hidden-defense lifecycle across actual solver phases and projectile damage."""

from copy import deepcopy
import unittest

from clashlab.engine_rules import RULES, RULESET
from clashlab.spatial import simulate_spatial

from test_hit_status import launches, status_scene
from test_spatial import synthetic_structure, synthetic_unit
from test_teslas import synthetic_tesla, tesla_parameters


def tesla_scene(actors, effects=None, **changes):
    scene = status_scene(actors, effects)
    scene.update(
        ruleset=RULESET,
        model_rules=deepcopy(RULES),
        width=20,
        height=12,
        duration_seconds=1.1,
        recording_interval_seconds=10,
    )
    scene.update(changes)
    return scene


def reveal_events(result):
    return [event for event in result["trace"] if event.get("event") == "tesla_reveal"]


class TeslaIntegrationTests(unittest.TestCase):
    def threshold_actors(self, **parameters):
        return [
            synthetic_unit(
                x=1.5,
                y=5,
                speed=1,
                range=20,
                damage=1000,
                hitpoints=10000,
            ),
            synthetic_structure("visible", x=3, y=4, hitpoints=1),
            synthetic_tesla(
                tesla_parameters(
                    trigger_radius_multiplier=0,
                    destruction_threshold_fraction=0.5,
                    **parameters,
                )
            ),
        ]

    def test_weapon_kill_reveals_and_fires_at_the_same_time_for_all_steps(self):
        for step in (0.01, 1):
            with self.subTest(step=step):
                result = simulate_spatial(
                    tesla_scene(self.threshold_actors(), maximum_step_seconds=step)
                )
                self.assertEqual(launches(result, "tesla"), [0, 0.6])
                self.assertEqual(len(reveal_events(result)), 1)
                self.assertEqual(reveal_events(result)[0]["time_seconds"], 0)
                self.assertEqual(
                    reveal_events(result)[0]["reason"], "declared_destruction_threshold"
                )
                self.assertAlmostEqual(result["actors"]["attacker"]["hp"], 9959.2)
                self.assertAlmostEqual(result["actors"]["tesla"]["death_time"], 1)

    def test_damage_command_cannot_destroy_dormant_tesla(self):
        actors = [
            synthetic_unit(x=1.5, target_priorities=[]),
            synthetic_tesla(tesla_parameters(trigger_radius_multiplier=0)),
        ]
        effects = [
            {
                "id": "damage-hidden",
                "kind": "damage",
                "time_seconds": 0,
                "targets": ["tesla"],
                "amount": 1000,
            }
        ]
        result = simulate_spatial(tesla_scene(actors, effects))
        self.assertEqual(result["actors"]["tesla"]["hp"], 600)
        self.assertEqual(result["actors"]["tesla"].get("_received_damage", 0), 0)
        self.assertFalse(reveal_events(result))
        self.assertFalse(launches(result, "tesla"))
        self.assertEqual(
            result["teslas"]["destruction_denominator_ids"]["tesla"], ["tesla"]
        )

    def test_splash_cannot_hit_dormant_tesla_before_threshold_resolution(self):
        actors = self.threshold_actors()
        scene = tesla_scene(actors, duration_seconds=0.01)
        scene["actors"][0]["attack_model"].update(kind="radial", radius=20)
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["visible"]["hp"], 0)
        self.assertEqual(result["actors"]["tesla"]["hp"], 600)
        self.assertEqual(len(reveal_events(result)), 1)

    def test_freeze_before_reveal_preserves_explicit_readiness_work(self):
        effects = [
            {
                "id": "freeze-hidden",
                "kind": "freeze",
                "time_seconds": 0,
                "targets": ["tesla"],
                "duration_seconds": 2,
            }
        ]
        actors = self.threshold_actors(first_attack_delay_seconds=0.3)
        actors[0]["attack_interval_seconds"] = 10
        result = simulate_spatial(tesla_scene(actors, effects, duration_seconds=2.9))
        self.assertEqual(launches(result, "tesla"), [2.3, 2.9])
        self.assertEqual(reveal_events(result)[0]["time_seconds"], 0)
        self.assertAlmostEqual(reveal_events(result)[0]["weapon_ready_seconds"], 2.3)

    def test_proximity_trigger_uses_exact_path_entry_with_large_steps(self):
        for step in (0.01, 1):
            with self.subTest(step=step):
                actors = [
                    synthetic_unit(
                        x=0.5,
                        y=3.5,
                        speed=6,
                        first_attack_seconds=100,
                        hitpoints=10000,
                    ),
                    synthetic_structure("destination", x=15, y=3),
                    synthetic_tesla(
                        tesla_parameters(trigger_radius_multiplier=0.25 / 6),
                        x=4,
                        y=4,
                        width=1,
                        height=1,
                    ),
                ]
                # Route crosses the reveal circle without touching its footprint.
                actors[-1]["tesla_model"]["trigger_radius"] = 1.25
                result = simulate_spatial(
                    tesla_scene(actors, maximum_step_seconds=step)
                )
                event = reveal_events(result)[0]
                self.assertAlmostEqual(event["time_seconds"], 3.25 / 6)
                self.assertAlmostEqual(launches(result, "tesla")[0], 3.25 / 6, places=7)


if __name__ == "__main__":
    unittest.main()
