"""Synthetic boundary evidence only; these fixtures are not game calibration."""

import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.dragon_duke import first_relative_circle_crossing
from test_dragon_duke import ROOT, air_ally, runtime


class DukeBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def relay(self, horizon):
        actors, _, duke = runtime(self.catalog, [air_ally(x=6.999)])
        time = 0.0
        trace = []
        for step in range(20):
            duke.prepare(actors, time, trace)
            isolated = actors["duke"]["_duke_isolated"]
            routes = {"ally": [(20, 10)]}
            speeds = {"ally": 2}
            if not isolated:
                routes["duke"] = [(20, 10)]
                speeds["duke"] = 2.5
            delay = duke.first_crossing_delay(actors, routes, speeds, time, horizon)
            self.assertIsNotNone(delay)
            for key, speed in speeds.items():
                actors[key]["x"] += speed * delay
            time += delay
        self.fail(f"relay failed to reject after {step + 1} events at {time}")

    def test_attracting_relay_rejects_instead_of_epsilon_stalling(self):
        for horizon in (0.01, 0.1, 1):
            with self.subTest(horizon=horizon):
                with self.assertRaisesRegex(
                    InputError,
                    "duke='duke', friendly_air='ally'.*contact dynamics policy",
                ):
                    self.relay(horizon)

    def test_membership_both_sides_and_inclusive_exact_contact(self):
        for offset, isolated in ((-1e-6, False), (0, False), (1e-6, True)):
            with self.subTest(offset=offset):
                actors, _, duke = runtime(self.catalog, [air_ally(x=13 + offset)])
                duke.prepare(actors, 0, [])
                self.assertEqual(actors["duke"]["_duke_isolated"], isolated)

    def test_committed_exit_with_continuing_motion_is_not_rejected(self):
        actors, _, duke = runtime(self.catalog, [air_ally(x=12)])
        duke.prepare(actors, 0, [])
        routes, speeds = {"ally": [(20, 10)]}, {"ally": 2}
        delay = duke.first_crossing_delay(actors, routes, speeds, 0, 1)
        self.assertAlmostEqual(delay, 0.5)
        actors["ally"]["x"] = 13
        duke.prepare(actors, delay, [])
        self.assertIsNone(duke.first_crossing_delay(actors, routes, speeds, delay, 1))

    def test_roundoff_contact_preserves_sustained_committed_side(self):
        # A near-zero root must not invent a brief opposite side before
        # sustained outward or inward movement at a committed contact.
        first = dict(x=0.0, y=0.0, width=0, height=0)
        for offset, destination, inside in ((-1e-15, 10, False), (1e-15, 0, True)):
            for horizon in (0.01, 0.1):
                with self.subTest(offset=offset, horizon=horizon):
                    second = dict(x=3 + offset, y=0.0, width=0, height=0)
                    self.assertIsNone(
                        first_relative_circle_crossing(
                            first,
                            second,
                            [],
                            [(destination, 0)],
                            0,
                            2,
                            3,
                            horizon,
                            inside,
                        )
                    )

    def test_later_physical_reversal_keeps_relevant_event(self):
        actors, _, duke = runtime(self.catalog, [air_ally(x=12)])
        duke.prepare(actors, 0, [])
        duke.first_crossing_delay(actors, {"ally": [(20, 10)]}, {"ally": 2}, 0, 1)
        actors["ally"]["x"] = 13
        duke.prepare(actors, 0.5, [])
        actors["ally"]["x"] = 14
        duke.prepare(actors, 1, [])
        delay = duke.first_crossing_delay(
            actors, {"ally": [(10, 10)]}, {"ally": 2}, 1, 1
        )
        self.assertAlmostEqual(delay, 0.5)

    def test_simultaneous_motion_matches_partitioned_contact_time(self):
        # Declared tolerance: 1e-9 seconds, substantially below all tested steps.
        for timestep in (0.1, 0.25, 1):
            first = dict(x=0.0, y=0.0, width=0, height=0)
            second = dict(x=8.0, y=0.0, width=0, height=0)
            time = 0.0
            for _ in range(30):
                event = first_relative_circle_crossing(
                    first, second, [(10, 0)], [(0, 0)], 1, 1, 3, timestep, False
                )
                if event:
                    self.assertAlmostEqual(
                        time + event["delay_seconds"], 2.5, delta=1e-9
                    )
                    self.assertTrue(event["inside_after"])
                    break
                first["x"] += timestep
                second["x"] -= timestep
                time += timestep
            else:
                self.fail("relevant entry omitted")


if __name__ == "__main__":
    unittest.main()
