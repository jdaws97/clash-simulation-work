"""Analytic range boundaries independent of the solver's maximum step."""

from math import cos, hypot, pi, sin, sqrt
from random import Random
import unittest

from clashlab.range_events import first_weapon_range_entry_delay


def actor(x, y, radius=1, width=0, height=0):
    return {"x": x, "y": y, "range": radius, "width": width, "height": height}


class WeaponRangeEventsTests(unittest.TestCase):
    def test_straight_approaches_match_independent_distance_bisection(self):
        random = Random(23026)
        for case in range(160):
            width = random.choice((0, random.uniform(0.1, 8)))
            height = random.choice((0, random.uniform(0.1, 8)))
            radius = random.uniform(0.1, 8)
            angle = random.uniform(-pi, pi)
            center_x, center_y = random.uniform(-20, 20), random.uniform(-20, 20)
            distance = hypot(width, height) + radius + random.uniform(1, 10)
            start = (
                center_x + distance * cos(angle),
                center_y + distance * sin(angle),
            )
            speed = random.uniform(0.1, 12)
            horizon = distance / speed
            target = actor(
                center_x - width / 2, center_y - height / 2, width=width, height=height
            )
            lower, upper = 0.0, horizon
            for _ in range(60):
                time = (lower + upper) / 2
                remaining = distance - time * speed
                x, y = remaining * cos(angle), remaining * sin(angle)
                footprint_distance = hypot(
                    max(abs(x) - width / 2, 0), max(abs(y) - height / 2, 0)
                )
                if footprint_distance > radius:
                    lower = time
                else:
                    upper = time
            with self.subTest(case=case):
                actual = first_weapon_range_entry_delay(
                    actor(*start, radius=radius),
                    target,
                    [(center_x, center_y)],
                    [],
                    speed,
                    0,
                    horizon,
                )
                self.assertIsNotNone(actual)
                self.assertAlmostEqual(actual, upper, delta=1e-8)

    def test_collinear_subdivision_and_zero_length_waypoints_preserve_entry(self):
        source, target = actor(0, 0, radius=0.5), actor(8, 0)
        expected = first_weapon_range_entry_delay(
            source,
            target,
            [(8, 0)],
            [(0, 0)],
            2,
            3,
            3,
        )
        self.assertAlmostEqual(expected, 1.5)
        source_route = [(0, 0), (0.4, 0), (1.8, 0), (1.8, 0), (3, 0), (8, 0)]
        target_route = [(8, 0), (7, 0), (6.5, 0), (6.5, 0), (0, 0)]
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                source, target, source_route, target_route, 2, 3, 3
            ),
            expected,
        )

    def test_contact_exactly_at_both_route_ends_is_included(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 0),
                actor(4, 0),
                [(1, 0)],
                [(2, 0)],
                1,
                2,
                1,
            ),
            1,
        )

    def test_minimum_range_boundary_exit_and_reentry(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 0, radius=5),
                actor(2, 0),
                [],
                [(0.5, 0), (3, 0)],
                0,
                1,
                4,
                minimum_range=2,
            ),
            3,
        )

    def test_zero_width_legal_band_still_has_an_inclusive_contact(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 0, radius=2),
                actor(4, 0),
                [],
                [(0, 0)],
                0,
                2,
                2,
                minimum_range=2,
            ),
            1,
        )

    def test_tangent_corner_then_travel_along_rectangle_side(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 2),
                actor(3, 3, width=2, height=2),
                [(8, 2)],
                [],
                1,
                0,
                8,
            ),
            3,
        )

    def test_zero_range_point_and_degenerate_rectangle_contacts(self):
        for target in (actor(2, 0), actor(2, -1, width=0, height=2)):
            with self.subTest(target=target):
                self.assertAlmostEqual(
                    first_weapon_range_entry_delay(
                        actor(0, 0, radius=0),
                        target,
                        [(4, 0)],
                        [],
                        2,
                        0,
                        2,
                    ),
                    1,
                )

    def test_fixed_weapon_center_accounts_for_its_own_footprint(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 0, width=4, height=2),
                actor(7, 1),
                [],
                [(2, 1)],
                0,
                2,
                3,
            ),
            2,
        )

    def test_velocity_scaling_preserves_geometry_and_rescales_time(self):
        source, target = actor(0, 0, radius=0.8), actor(4, 1)
        source_route, target_route = [(2, 0), (2, 3)], [(4, 0), (0, 0)]
        baseline = first_weapon_range_entry_delay(
            source, target, source_route, target_route, 2, 2, 3
        )
        for scale in (0.2, 0.7, 4.3):
            with self.subTest(scale=scale):
                self.assertAlmostEqual(
                    first_weapon_range_entry_delay(
                        source,
                        target,
                        source_route,
                        target_route,
                        2 * scale,
                        2 * scale,
                        3 / scale,
                    ),
                    baseline / scale,
                )

    def test_departing_from_initial_contact_has_no_positive_entry_event(self):
        # This contract intentionally leaves one-sided pursuit/range-exit
        # semantics to the scheduler. It cannot schedule a zero-time event.
        self.assertIsNone(
            first_weapon_range_entry_delay(
                actor(0, 0),
                actor(1, 0),
                [],
                [(3, 0)],
                0,
                1,
                2,
            )
        )

    def test_non_grid_aligned_air_arrival(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 0), actor(1.7, 0), [(2, 0)], [], 2, 0, 1
            ),
            0.35,
        )

    def test_stationary_weapon_acquires_a_moving_recipient(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 0), actor(1.7, 0), [], [(0, 0)], 0, 2, 1
            ),
            0.35,
        )

    def test_two_moving_actors_use_relative_velocity(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 0), actor(4, 0), [(5, 0)], [(-1, 0)], 1, 3, 1
            ),
            0.75,
        )

    def test_matching_velocities_never_close_the_gap(self):
        self.assertIsNone(
            first_weapon_range_entry_delay(
                actor(0, 0), actor(4, 0), [(5, 0)], [(9, 0)], 2, 2, 1
            )
        )

    def test_range_uses_target_footprint_instead_of_center(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 1), actor(3, 0, width=2, height=2), [(5, 1)], [], 2, 0, 2
            ),
            1,
        )

    def test_rounded_corner_not_expanded_square(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 0), actor(3, 3, width=2, height=2), [(5, 5)], [], 1, 0, 5
            ),
            sqrt(18) - 1,
        )

    def test_both_routes_can_change_velocity_at_different_times(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 0, radius=0.8),
                actor(4, 1),
                [(2, 0), (2, 3)],
                [(4, 0), (0, 0)],
                2,
                2,
                3,
            ),
            1 + (4 - sqrt(4.48)) / 16,
        )

    def test_finished_route_stays_still(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 0), actor(4, 0), [(1, 0)], [(0, 0)], 2, 1, 4
            ),
            2,
        )

    def test_minimum_range_emergence(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 0, radius=5),
                actor(0.5, 0),
                [],
                [(5, 0)],
                0,
                2,
                2,
                minimum_range=2,
            ),
            0.75,
        )

    def test_tangent_contact_is_an_inclusive_range_event(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 0), actor(-2, 1), [], [(2, 1)], 0, 2, 2
            ),
            1,
        )

    def test_initial_in_range_has_no_zero_time_boundary(self):
        self.assertIsNone(
            first_weapon_range_entry_delay(
                actor(0, 0), actor(1, 0), [], [(0, 0)], 0, 1, 1
            )
        )

    def test_exit_then_reentry_across_route_turn(self):
        self.assertAlmostEqual(
            first_weapon_range_entry_delay(
                actor(0, 0), actor(0.5, 0), [], [(2, 0), (0, 0)], 0, 1, 4
            ),
            2.5,
        )

    def test_no_entry_beyond_horizon(self):
        self.assertIsNone(
            first_weapon_range_entry_delay(
                actor(0, 0), actor(4, 0), [], [(0, 0)], 0, 1, 2
            )
        )


if __name__ == "__main__":
    unittest.main()
