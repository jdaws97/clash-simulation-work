"""Synthetic contact-cycle regression; no claim of calibrated Clash movement."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from clashlab import spatial
from clashlab.walls import RULESET, WALL_RULES
from test_combat import pattern_scene
from test_spatial import synthetic_scene, synthetic_structure, synthetic_unit
from test_walls import breach_profile
from test_buffs import integrated_scene, located_field
from test_healing import support_scene


def contact_cycle(step):
    """Synthetic four-owner geometry derived from the bounded stall diagnosis."""
    actors = [
        synthetic_unit(
            "archer",
            x=8.72536103591911,
            y=16.846156313267464,
            speed=3,
            range=3.5,
            damage=2,
            hitpoints=10000,
            first_attack_seconds=0.25,
            target_priorities=["unit"],
            target_layers=["air"],
        ),
        *[
            synthetic_unit(
                f"dragon-{index}",
                x=x,
                y=y,
                team="defense",
                layer="air",
                movement="air",
                speed=2,
                range=3,
                damage=10,
                hitpoints=10000,
                first_attack_seconds=0.15 + index * 0.2,
                attack_interval_seconds=0.4,
                target_priorities=["unit"],
            )
            for index, (x, y) in enumerate(
                (
                    (10.645671180996251, 19.783720065905936),
                    (10.634960812888934, 19.779316501834874),
                )
            )
        ],
        synthetic_unit(
            "giant",
            x=9.499528036777845,
            y=22.556147869629573,
            speed=1.65,
            range=1,
            damage=1,
            hitpoints=10000,
            target_priorities=["building"],
        ),
        synthetic_structure("goal", x=9, y=38, kind="building", hitpoints=10000),
    ]
    for actor in actors:
        if actor["movement"] == "ground":
            actor["wall_behavior"] = breach_profile()
            actor["wall_behavior"]["weapon"].update(
                damage=actor["damage"],
                range=actor["range"],
                attack_interval_seconds=actor["attack_interval_seconds"],
                first_attack_seconds=actor["first_attack_seconds"],
                cooldown="shared_with_main_weapon",
            )
    scene = pattern_scene(
        actors,
        width=56,
        height=56,
        duration_seconds=1,
        maximum_step_seconds=step,
        recording_interval_seconds=10,
    )
    scene.update(ruleset=RULESET, model_rules=deepcopy(WALL_RULES))
    return scene


class AirContactFollowingTests(unittest.TestCase):
    def test_four_owner_cycle_advances_and_preserves_ready_attacks_across_steps(self):
        outputs = []
        for step in (0.5, 0.07, 0.011):
            count = 0
            original = spatial._weapon_range_boundary

            def bounded(*args):
                nonlocal count
                count += 1
                self.assertLess(count, 1000, "Movement contacts failed to advance time")
                return original(*args)

            with (
                self.subTest(step=step),
                patch.object(spatial, "_weapon_range_boundary", bounded),
            ):
                result = spatial.simulate_spatial(contact_cycle(step))
                self.assertEqual(
                    result["air_contact_policy"], spatial.AIR_CONTACT_POLICY
                )
                self.assertEqual(result["frames"][-1]["time_seconds"], 1)
                for index in (0, 1):
                    launches = [
                        e["time_seconds"]
                        for e in result["trace"]
                        if e.get("source") == f"dragon-{index}"
                        and e.get("event") == "projectile_launch"
                    ]
                    expected = [
                        0.15 + index * 0.2 + tick * 0.4
                        for tick in range(3)
                        if 0.15 + index * 0.2 + tick * 0.4 <= 1
                    ]
                    self.assertEqual(len(launches), len(expected))
                    for actual, wanted in zip(launches, expected):
                        self.assertAlmostEqual(actual, wanted, places=8)
                self.assertEqual(result["actors"]["giant"]["hp"], 9950)
                outputs.append(result)
        for result in outputs[1:]:
            for key in ("giant", "dragon-0", "dragon-1"):
                for field in ("hp", "next_attack", "target"):
                    actual, expected = (
                        result["actors"][key][field],
                        outputs[0]["actors"][key][field],
                    )
                    if isinstance(actual, (int, float)):
                        self.assertAlmostEqual(actual, expected, places=7)
                    else:
                        self.assertEqual(actual, expected)
            # Existing weighted ground replanning depends on solver partitions.
            # Air contact must preserve its relative offset despite that drift.
            for key in ("dragon-0", "dragon-1"):
                for axis in ("x", "y"):
                    self.assertAlmostEqual(
                        result["actors"][key][axis] - result["actors"]["giant"][axis],
                        outputs[0]["actors"][key][axis]
                        - outputs[0]["actors"]["giant"][axis],
                        places=8,
                    )

    def test_source_freeze_keeps_motion_pause_and_resumes_unchanged_attack_clock(self):
        for step in (0.5, 0.013):
            result = spatial.simulate_spatial(
                synthetic_scene(
                    [
                        synthetic_unit(
                            "flyer",
                            x=2.5,
                            movement="air",
                            layer="air",
                            speed=4,
                            range=2,
                            damage=1,
                            first_attack_seconds=0.1,
                            attack_interval_seconds=0.5,
                            target_priorities=["unit"],
                        ),
                        synthetic_unit(
                            "runner",
                            x=4.5,
                            team="defense",
                            speed=1,
                            range=0.5,
                            hitpoints=100,
                            damage=1,
                            target_priorities=["building"],
                        ),
                        synthetic_structure(
                            "goal", x=20, team="attack", kind="building"
                        ),
                    ],
                    effects=[
                        dict(
                            id="pause",
                            kind="freeze",
                            targets=["flyer"],
                            time_seconds=0.2,
                            duration_seconds=0.1,
                        )
                    ],
                    width=24,
                    duration_seconds=0.9,
                    maximum_step_seconds=step,
                    recording_interval_seconds=0.1,
                )
            )
            hits = [
                e["time_seconds"] for e in result["trace"] if e.get("source") == "flyer"
            ]
            self.assertEqual(len(hits), 2)
            self.assertAlmostEqual(hits[0], 0.1)
            self.assertAlmostEqual(hits[1], 0.7)
            paused = [
                f["actors"]["flyer"]["x"]
                for f in result["frames"]
                if abs(f["time_seconds"] - 0.2) < 1e-8
                or abs(f["time_seconds"] - 0.3) < 1e-8
            ]
            self.assertEqual(len(paused), 2)
            self.assertAlmostEqual(*paused)

    def test_contact_following_does_not_override_other_movement_cases(self):
        scene = synthetic_scene(
            [
                synthetic_unit(
                    "flyer",
                    x=2.5,
                    movement="air",
                    layer="air",
                    speed=2,
                    range=2,
                    target_priorities=["unit"],
                ),
                synthetic_unit("runner", x=4.5, team="defense", speed=1),
            ]
        )
        actors = spatial._load_actors(scene, 9, 7)
        actors["flyer"]["target"] = "runner"
        for change in (
            "faster",
            "approaching",
            "interior",
            "paused",
            "forced",
            "board",
        ):
            current = deepcopy(actors)
            motions = {"flyer": ([], 0), "runner": ([(5.5, 3.5)], 1)}
            excluded = set()
            if change == "faster":
                motions["runner"] = ([(5.5, 3.5)], 3)
            if change == "approaching":
                motions["runner"] = ([(3.5, 3.5)], 1)
            if change == "interior":
                current["flyer"]["x"] = 3
            if change == "paused":
                del motions["flyer"]
            if change == "forced":
                excluded.add("flyer")
            if change == "board":
                motions["runner"] = ([(20, 3.5)], 1)
            expected = deepcopy(motions)
            spatial._air_contact_motions(current, motions, 0, 9, 7, excluded)
            with self.subTest(case=change):
                self.assertEqual(motions, expected)

    def test_following_crosses_buff_edges_at_actual_target_speed_before_attacks(self):
        for step in (0.5, 0.013):
            scene = support_scene(
                [
                    synthetic_unit(
                        "flyer",
                        x=2.5,
                        movement="air",
                        layer="air",
                        speed=4,
                        range=2,
                        damage=1,
                        first_attack_seconds=0.1,
                        attack_interval_seconds=0.5,
                        target_priorities=["unit"],
                    ),
                    synthetic_unit(
                        "runner",
                        x=4.5,
                        team="defense",
                        speed=1,
                        damage=1,
                        range=0.5,
                        hitpoints=100,
                        target_priorities=["building"],
                    ),
                    synthetic_structure("goal", x=20, team="attack", kind="building"),
                ],
                width=24,
                duration_seconds=1.2,
                maximum_step_seconds=step,
                recording_interval_seconds=10,
            )
            field = located_field(
                3.2,
                movement_bonus_tiles_per_second=3,
                damage_bonus_fraction=1,
                exit_linger_seconds=0,
            )
            result = spatial.simulate_spatial(integrated_scene(scene, [field]))
            hits = [
                event
                for event in result["trace"]
                if event.get("source") == "flyer"
                and event.get("event") == "projectile_impact"
            ]
            self.assertEqual([event["damage"] for event in hits], [1, 2, 1])
            for hit, expected in zip(hits, (0.1, 0.6, 1.1)):
                self.assertAlmostEqual(hit["time_seconds"], expected)
            self.assertEqual(result["actors"]["runner"]["hp"], 96)


if __name__ == "__main__":
    unittest.main()
