"""Lock, interruption and launch-time damage checks, not game calibration."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.adapters import RAMP_SCOPE, compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.ramping import RAMP_RULES, RULESET
from clashlab.spatial import simulate_spatial

from test_adapters import entity_instance, sector
from test_healing import support_scene
from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "explicit-synthetic-ramp-not-current-Clash-validation"


def ramp_model(**changes):
    model = {
        "source": SOURCE,
        "clock_start": "first_weapon_launch",
        "freeze_policy": "reset",
        "protected_target_policy": "continue",
        "stages": [
            {"after_seconds": after, "damage_per_hit": damage, "source": SOURCE}
            for after, damage in ((0, 10), (1, 20), (2, 100))
        ],
    }
    model.update(changes)
    return model


def ramp_scene(**changes):
    scene = support_scene(
        [
            synthetic_unit(x=6.5, hitpoints=10000, damage=1, range=10, speed=1),
            synthetic_structure(
                damage=10, hitpoints=10000, range=9, attack_interval_seconds=0.5
            ),
        ],
        duration_seconds=3,
        maximum_step_seconds=0.1,
        recording_interval_seconds=0.25,
    )
    scene["ruleset"] = RULESET
    scene["model_rules"] = deepcopy(RAMP_RULES)
    scene["actors"][1]["ramp_model"] = ramp_model()
    scene.update(changes)
    return scene


def status_effect(kind, target, time, duration):
    return {
        "id": f"{kind}-{time}",
        "kind": kind,
        "targets": [target],
        "time_seconds": time,
        "duration_seconds": duration,
    }


def tower_impacts(result):
    return [
        event
        for event in result["trace"]
        if event.get("event") == "projectile_impact" and event["source"] == "tower"
    ]


class RampTests(unittest.TestCase):
    def test_uninterrupted_weapon_uses_stage_damage_at_each_launch(self):
        result = simulate_spatial(ramp_scene())
        self.assertEqual(
            [event["damage"] for event in tower_impacts(result)],
            [10, 10, 20, 20, 100, 100, 100],
        )
        self.assertEqual(result["actors"]["attacker"]["hp"], 9640)
        self.assertFalse(result["full_game_prediction"])

    def test_freeze_reset_and_pause_produce_different_restart_damage(self):
        scene = ramp_scene(effects=[status_effect("freeze", "tower", 1.5, 1)])
        reset = tower_impacts(simulate_spatial(scene))
        scene["actors"][1]["ramp_model"]["freeze_policy"] = "pause"
        paused = tower_impacts(simulate_spatial(scene))
        self.assertEqual(
            [event["time_seconds"] for event in reset], [0, 0.5, 1, 2.5, 3]
        )
        self.assertEqual(reset[-2]["damage"], 10)
        self.assertEqual(paused[-2]["damage"], 20)
        self.assertEqual(paused[-1]["damage"], 100)

    def test_invulnerability_blocks_damage_without_reset_under_continue_policy(self):
        scene = ramp_scene(
            effects=[status_effect("invulnerability", "attacker", 0.75, 1)]
        )
        result = simulate_spatial(scene)
        impacts = tower_impacts(result)
        self.assertTrue(impacts[2]["protected"])
        self.assertTrue(impacts[3]["protected"])
        self.assertEqual(impacts[4]["damage"], 100)
        scene["actors"][1]["ramp_model"]["protected_target_policy"] = "pause"
        paused = tower_impacts(simulate_spatial(scene))
        self.assertEqual(paused[4]["damage"], 20)

    def test_target_change_does_not_transfer_previous_heat_to_new_recipient(self):
        scene = ramp_scene()
        replacement = deepcopy(scene["actors"][0])
        replacement["id"] = "replacement"
        replacement["x"] = 5.5
        scene["actors"].append(replacement)
        scene["effects"] = [
            {
                "id": "kill-primary",
                "time_seconds": 1.25,
                "kind": "damage",
                "targets": ["attacker"],
                "amount": 10000,
            }
        ]
        impacts = tower_impacts(simulate_spatial(scene))
        replacement_hits = [
            event for event in impacts if event["target"] == "replacement"
        ]
        self.assertEqual(replacement_hits[0]["time_seconds"], 1.5)
        self.assertEqual(replacement_hits[0]["damage"], 10)

    def test_clock_origin_remains_explicit_when_initial_weapon_is_delayed(self):
        scene = ramp_scene()
        scene["actors"][1]["first_attack_seconds"] = 2.5
        first_launch = tower_impacts(simulate_spatial(scene))
        scene["actors"][1]["ramp_model"]["clock_start"] = "eligible_in_range_lock"
        in_range = tower_impacts(simulate_spatial(scene))
        self.assertEqual(first_launch[0]["damage"], 10)
        self.assertEqual(in_range[0]["damage"], 100)

    def test_leaving_range_resets_heat_before_the_same_unit_returns(self):
        scene = support_scene(
            [
                synthetic_unit(
                    x=6.5,
                    hitpoints=10000,
                    speed=1,
                    range=0.6,
                    target_priorities=["building", "defense"],
                    target_priority_tiers=[["building"], ["defense"]],
                ),
                synthetic_structure(
                    damage=10,
                    hitpoints=10000,
                    range=1.2,
                    attack_interval_seconds=0.25,
                ),
                synthetic_structure("decoy", kind="building", x=4, hitpoints=100),
            ],
            duration_seconds=3,
            maximum_step_seconds=0.025,
        )
        scene["ruleset"] = RULESET
        scene["model_rules"] = deepcopy(RAMP_RULES)
        scene["actors"][1]["ramp_model"] = ramp_model()
        result = simulate_spatial(scene)
        losses = [
            event
            for event in result["trace"]
            if event.get("event") == "weapon_ramp_reset"
            and event["reason"] == "lock_lost"
        ]
        self.assertTrue(losses)
        return_hit = next(
            event
            for event in tower_impacts(result)
            if event["time_seconds"] > losses[0]["time_seconds"]
        )
        self.assertEqual(return_hit["target"], "attacker")
        self.assertEqual(return_hit["damage"], 10)

    def test_launched_damage_is_not_rewritten_by_a_later_reset(self):
        scene = ramp_scene(duration_seconds=6)
        scene["actors"][1]["attack_model"]["projectile"] = {
            "timing": "launch_distance_delay",
            "speed_tiles_per_second": 0.5,
            "destination": "locked_actor_center_at_impact",
            "hit_radius": 0,
        }
        scene["effects"] = [status_effect("freeze", "tower", 2.25, 1)]
        impacts = tower_impacts(simulate_spatial(scene))
        self.assertEqual(
            next(event for event in impacts if event["time_seconds"] == 4)["damage"],
            100,
        )

    def test_legacy_ruleset_cannot_silently_ignore_a_ramp(self):
        from clashlab.healing import RULESET as SUPPORT_RULESET, SUPPORT_RULES

        scene = ramp_scene()
        scene["ruleset"] = SUPPORT_RULESET
        scene["model_rules"] = deepcopy(SUPPORT_RULES)
        with self.assertRaises(InputError):
            simulate_spatial(scene)

    def test_missing_or_invalid_interruption_and_stage_rules_are_rejected(self):
        for change in ("missing_policy", "duplicate_time", "wrong_initial_damage"):
            scene = ramp_scene()
            model = scene["actors"][1]["ramp_model"]
            if change == "missing_policy":
                del model["freeze_policy"]
            elif change == "duplicate_time":
                model["stages"][1]["after_seconds"] = 0
            else:
                model["stages"][0]["damage_per_hit"] = 11
            with self.subTest(change=change), self.assertRaises(InputError):
                simulate_spatial(scene)


class InfernoAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def inferno_sector(self, mode="normal"):
        tower = entity_instance(
            "inferno", "inferno-tower", 10, "defense", mode=mode, statistics_mode=mode
        )
        if mode == "normal":
            tower["ramp_parameters"] = {
                "source": SOURCE,
                "clock_start": "first_weapon_launch",
                "freeze_policy": "reset",
                "protected_target_policy": "continue",
                "middle_stage_after_seconds": 1.5,
                "maximum_stage_after_seconds": 5.25,
                "timing_source": "historical-2018-publication-not-current-certification",
            }
        else:
            tower["attack_parameters"]["allocation"] = "distinct_targets_only"
            tower["beam_parameters"] = {
                "cadence": "synchronized_volley_hypothesis",
                "source": SOURCE,
            }
        scene = sector(self.catalog, [tower])
        scene.update(
            {
                "scope": RAMP_SCOPE,
                "model_rules": deepcopy(RAMP_RULES),
                "healing_stacking": {"source": SOURCE, "groups": {}},
                "healing_spells": [],
            }
        )
        return scene

    def test_single_inferno_starts_at_initial_dps_instead_of_maximum(self):
        actor = compile_entity_scene(self.inferno_sector(), self.catalog)["scene"][
            "actors"
        ][0]
        self.assertAlmostEqual(actor["damage"], 15.36)
        self.assertEqual(
            [stage["damage_per_hit"] for stage in actor["ramp_model"]["stages"]],
            [15.36, 33.28, 332.8],
        )
        self.assertEqual(actor["hitpoints"], 4400)

    def test_multi_mode_uses_six_distinct_beams_without_single_ramp(self):
        actor = compile_entity_scene(self.inferno_sector("multiTarget"), self.catalog)[
            "scene"
        ]["actors"][0]
        self.assertNotIn("ramp_model", actor)
        self.assertEqual(actor["attack_model"]["projectiles_per_volley"], 6)
        self.assertAlmostEqual(actor["damage"], 15.36)

    def test_fixed_damage_or_missing_policy_cannot_bypass_inferno_adapter(self):
        scene = self.inferno_sector()
        del scene["entities"][0]["ramp_parameters"]
        with self.assertRaises(InputError):
            compile_entity_scene(scene, self.catalog)
        scene = self.inferno_sector("multiTarget")
        scene["entities"][0]["attack_parameters"][
            "allocation"
        ] = "cycle_distinct_targets_to_fill_volley"
        with self.assertRaises(InputError):
            compile_entity_scene(scene, self.catalog)


if __name__ == "__main__":
    unittest.main()
