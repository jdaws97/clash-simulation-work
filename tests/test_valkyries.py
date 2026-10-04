"""Geometric and movement checks for explicit, uncalibrated Valkyrie rules."""

from collections import defaultdict
from copy import deepcopy
from math import floor, hypot
import unittest

from clashlab.combat import PatternCombat
from clashlab.common import InputError
from clashlab.spatial import _blocked, _load_actors, _move, center, target_distance
from clashlab.valkyries import (
    ValkyrieRouting,
    compile_valkyrie,
    source_radial_impacts,
    validate_source_radial,
)
from clashlab.walls import WallRouting

from test_combat import synthetic_pattern
from test_spatial import synthetic_structure, synthetic_unit


SOURCE = "synthetic-placement-hypothesis-not-replay-calibrated"
WIDTH = 14
HEIGHT = 10


def placement_parameters(**changes):
    parameters = {
        "source": SOURCE,
        "neighbor_gap_tiles": 1,
        "samples_per_tile": 4,
        "maximum_extra_travel_seconds": 10,
    }
    parameters.update(changes)
    return parameters


def valkyrie(**changes):
    actor = synthetic_unit(
        "valkyrie",
        x=4.5,
        y=4.5,
        range=0.5,
        target_priorities=["defense", "building"],
        target_priority_tiers=[["defense", "building"]],
        minimum_range=0,
        attack_model=synthetic_pattern(
            "radial",
            radius=1,
            target_kinds=["defense", "building"],
            target_layers=["ground"],
        ),
        wall_behavior={"kind": "avoid", "source": SOURCE},
        entity_adapter={},
    )
    parameters = changes.pop("placement_parameters", placement_parameters())
    actor.update(changes)
    compile_valkyrie(actor, {"entity": "valkyrie", "valkyrie_parameters": parameters})
    return actor


def pair(second_x=8, second_y=4):
    return [
        synthetic_structure("primary", x=5, y=4, width=2, height=2),
        synthetic_structure("neighbor", x=second_x, y=second_y, width=2, height=2),
    ]


def setup(actors):
    actors = _load_actors({"actors": actors}, WIDTH, HEIGHT)
    walls = WallRouting(actors)
    routing = ValkyrieRouting(actors, walls.select_target)
    return actors, walls, routing


def select(routing, actor, actors, time=0):
    return routing.select_target(
        actor, actors, time, _blocked(actors, time), WIDTH, HEIGHT
    )


def move(actor, route, duration):
    (actor["x"], actor["y"]), actor["_remaining_path"] = _move(actor, route, duration)


def clearing_weapon(actor):
    return {
        "kind": "clear_obstructions",
        "source": SOURCE,
        "route_cost": "travel_seconds_plus_nominal_clearance",
        "weapon": {
            "damage": actor["damage"],
            "range": actor["range"],
            "attack_interval_seconds": actor["attack_interval_seconds"],
            "first_attack_seconds": actor["first_attack_seconds"],
            "timing": "instant",
            "cooldown": "shared_with_main_weapon",
            "source": SOURCE,
        },
    }


def eligible_damage(packet, actor, time):
    return PatternCombat._damage_eligible(None, packet, actor, time)


class ValkyrieGeometryTests(unittest.TestCase):
    def test_whirlwind_uses_source_and_building_footprints(self):
        actors, _, _ = setup(
            [
                valkyrie(x=3.5, y=4.5),
                synthetic_structure("primary", x=4, y=4, width=3, height=3),
                synthetic_structure("behind_source", x=2, y=4),
                synthetic_structure("beyond_primary", x=7, y=4),
                synthetic_structure("friendly", x=3, y=2, team="attack"),
                synthetic_unit("air", x=3.5, y=4.5, layer="air", movement="air"),
            ]
        )
        actor = actors["valkyrie"]
        packet = {
            "source": actor["id"],
            "source_team": actor["team"],
            "target": "primary",
            "primary_layer": "ground",
            "position": center(actors["primary"]),
            "launch_position": center(actor),
            "pattern": actor["attack_model"],
        }
        hits = source_radial_impacts(packet, actors, 0, eligible_damage)
        self.assertEqual(
            {target["id"] for target, _ in hits}, {"primary", "behind_source"}
        )
        self.assertGreater(
            target_distance(center(actors["primary"]), actors["behind_source"]), 1
        )

    def test_launched_swing_survives_primary_death_and_keeps_saved_origin(self):
        actors, _, _ = setup([valkyrie(x=7.5), *pair()])
        actor = actors["valkyrie"]
        packet = {
            "source": actor["id"],
            "source_team": actor["team"],
            "target": "primary",
            "primary_layer": "ground",
            "launch_position": center(actor),
            "pattern": actor["attack_model"],
        }
        actor["x"] = 0.5
        actor["hp"] = 0
        actors["primary"]["hp"] = 0
        hits = source_radial_impacts(packet, actors, 0, eligible_damage)
        self.assertEqual([target["id"] for target, _ in hits], ["neighbor"])


class ValkyrieRoutingTests(unittest.TestCase):
    def assert_clear_segments(self, origin, route, blocked):
        previous = origin
        for point in route:
            distance = hypot(point[0] - previous[0], point[1] - previous[1])
            samples = max(1, int(distance / 0.05) + 1)
            for index in range(samples + 1):
                fraction = index / samples
                x = previous[0] + (point[0] - previous[0]) * fraction
                y = previous[1] + (point[1] - previous[1]) * fraction
                self.assertTrue(0 <= x < WIDTH and 0 <= y < HEIGHT)
                self.assertNotIn((floor(x), floor(y)), blocked)
            previous = point

    def test_in_range_primary_is_retained_while_moving_between_buildings(self):
        actors, _, routing = setup([valkyrie(), *pair()])
        actor = actors["valkyrie"]
        primary, route = select(routing, actor, actors)
        self.assertEqual(primary["id"], "primary")
        self.assertLessEqual(target_distance(center(actor), primary), actor["range"])
        self.assertTrue(route)
        self.assertFalse(routing.attack_ready(actor))
        self.assertNotIn("_path_signature", actor)
        self.assert_clear_segments(center(actor), route, _blocked(actors, 0))
        point = route[-1]
        self.assertTrue(7 <= point[0] < 8)
        self.assertLessEqual(target_distance(point, primary), 0.5)
        self.assertLessEqual(target_distance(point, actors["neighbor"]), 1)
        self.assertAlmostEqual(
            target_distance(point, primary), target_distance(point, actors["neighbor"])
        )

    def test_fractional_steps_reach_placement_without_recentering_or_stalling(self):
        actors, _, routing = setup([valkyrie(), *pair()])
        actor = actors["valkyrie"]
        original_point = None
        for step in range(120):
            primary, route = select(routing, actor, actors, step * 0.07)
            self.assertEqual(primary["id"], "primary")
            frame = routing.frame(actor)
            if original_point is None:
                original_point = frame["valkyrie_placement"]
            self.assertEqual(frame["valkyrie_placement"], original_point)
            if routing.attack_ready(actor):
                break
            previous = center(actor)
            move(actor, route, 0.07)
            self.assertGreater(
                hypot(actor["x"] - previous[0], actor["y"] - previous[1]), 0
            )
        self.assertTrue(routing.attack_ready(actor))
        self.assertLessEqual(target_distance(center(actor), actors["neighbor"]), 1)

    def test_touching_buildings_use_external_seam_instead_of_blocked_interior(self):
        actors, _, routing = setup([valkyrie(x=4.5, y=3.5), *pair(second_x=7)])
        actor = actors["valkyrie"]
        _, route = select(routing, actor, actors)
        self.assert_clear_segments(center(actor), route, _blocked(actors, 0))
        self.assertAlmostEqual(route[-1][0], 7)
        self.assertLess(route[-1][1], 4)
        self.assertLessEqual(target_distance(route[-1], actors["primary"]), 0.5)
        self.assertLessEqual(target_distance(route[-1], actors["neighbor"]), 1)

    def test_diagonal_neighbors_can_share_a_reachable_corner_approach(self):
        actor = valkyrie(x=4.5, y=6.5)
        actors, _, routing = setup([actor, *pair(second_x=7, second_y=6)])
        actor = actors["valkyrie"]
        _, route = select(routing, actor, actors)
        self.assert_clear_segments(center(actor), route, _blocked(actors, 0))
        self.assertLessEqual(target_distance(route[-1], actors["primary"]), 0.5)
        self.assertLessEqual(target_distance(route[-1], actors["neighbor"]), 1)

    def test_explicit_zero_detour_budget_keeps_ordinary_melee_position(self):
        actors, _, routing = setup(
            [
                valkyrie(
                    placement_parameters=placement_parameters(
                        maximum_extra_travel_seconds=0
                    )
                ),
                *pair(),
            ]
        )
        actor = actors["valkyrie"]
        primary, route = select(routing, actor, actors)
        self.assertEqual(primary["id"], "primary")
        self.assertEqual(route, [])
        self.assertTrue(routing.attack_ready(actor))
        self.assertEqual(routing.frame(actor), {})

    def test_unreachable_pair_does_not_replace_reachable_primary(self):
        barriers = [
            synthetic_structure(
                f"wall-{y}", x=7, y=y, kind="wall", counts_for_destruction=False
            )
            for y in range(HEIGHT)
        ]
        actors, _, routing = setup([valkyrie(), *pair(), *barriers])
        actor = actors["valkyrie"]
        primary, route = select(routing, actor, actors)
        self.assertEqual(primary["id"], "primary")
        self.assertEqual(route, [])
        self.assertTrue(routing.attack_ready(actor))

    def test_clear_wall_motion_keeps_primary_and_uses_shared_obstruction_hits(self):
        actor = valkyrie(x=2.5)
        actor["wall_behavior"] = clearing_weapon(actor)
        barriers = [
            synthetic_structure(
                f"wall-{y}", x=4, y=y, kind="wall", counts_for_destruction=False
            )
            for y in range(HEIGHT)
        ]
        actors, walls, routing = setup([actor, *pair(), *barriers])
        actor = actors["valkyrie"]
        trace = []
        cleared = False
        for step in range(120):
            time = step * 0.1
            primary, route = select(routing, actor, actors, time)
            self.assertEqual(primary["id"], "primary")
            blocked = _blocked(actors, time)
            self.assert_clear_segments(center(actor), route, blocked)
            damage = defaultdict(float)
            walls.wall_hit(actor, actors, time, damage, trace)
            for target_id, amount in damage.items():
                actors[target_id]["hp"] = max(0, actors[target_id]["hp"] - amount)
                cleared = True
            if routing.attack_ready(actor):
                break
            move(actor, route, 0.1)
        self.assertTrue(cleared)
        self.assertTrue(routing.attack_ready(actor))
        self.assertGreater(actor["x"], 7)
        self.assertTrue(
            all(event["intended_primary_target"] == "primary" for event in trace)
        )
        self.assertTrue(
            all(event["cooldown"] == "shared_with_main_weapon" for event in trace)
        )

    def test_wall_clearing_route_is_independent_of_movement_step_size(self):
        positions = []
        for step_size in (0.01, 0.25):
            actor = valkyrie()
            actor["wall_behavior"] = clearing_weapon(actor)
            actors, _, routing = setup([actor, *pair()])
            actor = actors["valkyrie"]
            for step in range(round(2 / step_size)):
                _, route = select(routing, actor, actors, step * step_size)
                self.assert_clear_segments(center(actor), route, _blocked(actors, 0))
                move(actor, route, step_size)
            positions.append(center(actor))
        self.assertAlmostEqual(positions[0][0], positions[1][0])
        self.assertAlmostEqual(positions[0][1], positions[1][1])
        self.assertGreater(positions[0][0], 7)

    def test_sealed_gap_becomes_reachable_only_after_wall_opens(self):
        structures = [
            synthetic_structure("primary", x=5, y=0, width=2, height=8),
            synthetic_structure("neighbor", x=8, y=0, width=2, height=8),
            synthetic_structure(
                "gate", x=7, y=8, kind="wall", counts_for_destruction=False
            ),
        ]
        actors, _, routing = setup([valkyrie(), *structures])
        actor = actors["valkyrie"]
        primary, route = select(routing, actor, actors)
        self.assertEqual(primary["id"], "primary")
        self.assertEqual(route, [])
        self.assertEqual(routing.frame(actor), {})
        actors["gate"]["hp"] = 0
        primary, route = select(routing, actor, actors)
        self.assertEqual(primary["id"], "primary")
        self.assertTrue(route)
        self.assertFalse(routing.attack_ready(actor))
        self.assert_clear_segments(center(actor), route, _blocked(actors, 0))
        self.assertGreaterEqual(route[-1][0], 7)
        self.assertLess(route[-1][0], 8)

    def test_destroyed_neighbor_invalidates_placement_and_dead_primary_retargets(self):
        actors, _, routing = setup([valkyrie(), *pair()])
        actor = actors["valkyrie"]
        select(routing, actor, actors)
        self.assertFalse(routing.attack_ready(actor))
        actors["neighbor"]["hp"] = 0
        primary, route = select(routing, actor, actors)
        self.assertEqual(primary["id"], "primary")
        self.assertEqual(route, [])
        self.assertTrue(routing.attack_ready(actor))
        actors["neighbor"]["hp"] = actors["neighbor"]["maximum_hp"]
        actors["primary"]["hp"] = 0
        primary, _ = select(routing, actor, actors)
        self.assertEqual(primary["id"], "neighbor")
        self.assertEqual(routing.frame(actor), {})

    def test_non_valkyrie_targeting_is_forwarded_without_changes(self):
        actor = synthetic_unit(wall_behavior={"kind": "avoid", "source": SOURCE})
        actors = _load_actors({"actors": [actor, *pair()]}, WIDTH, HEIGHT)
        walls = WallRouting(actors)
        routing = ValkyrieRouting(actors, walls.select_target)
        actor = actors["attacker"]
        ordinary = walls.select_target(
            actor, actors, 0, _blocked(actors, 0), WIDTH, HEIGHT
        )
        self.assertEqual(select(routing, actor, actors), ordinary)
        self.assertTrue(routing.attack_ready(actor))


class ValkyrieCompilerTests(unittest.TestCase):
    def test_compiler_preserves_catalog_derived_stats_and_declares_source_origin(self):
        actor = valkyrie(damage=123, speed=3, attack_interval_seconds=1.8)
        self.assertEqual(
            (actor["damage"], actor["speed"], actor["attack_interval_seconds"]),
            (123, 3, 1.8),
        )
        self.assertEqual(actor["attack_model"]["kind"], "source_radial")
        self.assertEqual(
            actor["attack_model"]["projectile"]["destination"],
            "fixed_source_center_at_launch",
        )

    def test_missing_invalid_or_unrecognized_placement_inputs_fail_closed(self):
        cases = [
            {},
            placement_parameters(samples_per_tile=0),
            placement_parameters(samples_per_tile=1.5),
            placement_parameters(maximum_extra_travel_seconds=-1),
            placement_parameters(neighbor_gap_tiles=float("inf")),
            placement_parameters(guess_game_defaults=True),
        ]
        for parameters in cases:
            with self.subTest(parameters=parameters), self.assertRaises(InputError):
                valkyrie(placement_parameters=parameters)

    def test_radius_smaller_than_primary_range_and_delayed_swings_are_rejected(self):
        with self.assertRaises(InputError):
            valkyrie(attack_model=synthetic_pattern("radial", radius=0.25))
        pattern = synthetic_pattern("radial", radius=1)
        pattern["projectile"] = {
            "timing": "launch_distance_delay",
            "speed_tiles_per_second": 4,
            "destination": "fixed_target_center_at_launch",
            "hit_radius": 0,
        }
        with self.assertRaises(InputError):
            valkyrie(attack_model=pattern)

    def test_source_radial_cannot_silently_use_a_target_center(self):
        pattern = deepcopy(valkyrie()["attack_model"])
        pattern["projectile"]["destination"] = "locked_actor_center_at_impact"
        with self.assertRaises(InputError):
            validate_source_radial(pattern)


if __name__ == "__main__":
    unittest.main()
