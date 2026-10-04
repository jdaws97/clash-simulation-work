"""Synthetic boundary evidence only; these fixtures are not game calibration."""

from copy import deepcopy
import json
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.dragon_duke import DragonDukeCombat, first_relative_circle_crossing
from clashlab.hero_extensions import parameter_provenance
from test_dragon_duke import ROOT, air_ally, runtime


class DukeBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def sampled_runtime(self):
        actors, combat, _ = runtime(self.catalog, [air_ally(x=6.999)], items=[])
        model = actors["duke"]["duke_model"]
        model["parameters"].update(
            json.loads(
                (
                    ROOT / "data/battle-policies/experimental-duke-isolation.json"
                ).read_text()
            )
        )
        model["parameter_provenance"] = parameter_provenance(model["parameters"])
        return actors, combat, DragonDukeCombat(actors, combat)

    def test_sampled_policy_requires_complete_experimental_contract(self):
        actors, combat, _ = self.sampled_runtime()
        for field, value in (
            ("interval_seconds", 0),
            ("interval_seconds", float("nan")),
            ("status", "game_calibrated"),
            ("source", ""),
        ):
            with self.subTest(field=field, value=value):
                altered = deepcopy(actors)
                model = altered["duke"]["duke_model"]
                model["parameters"]["isolation_update"][field] = value
                model["parameter_provenance"] = parameter_provenance(
                    model["parameters"]
                )
                with self.assertRaises(InputError):
                    DragonDukeCombat(altered, combat)

    def test_sample_clock_holds_state_and_applies_lifecycle_and_cooldown_once(self):
        actors, _, duke = self.sampled_runtime()
        actors["duke"]["spawn_seconds"] = 1.3
        actors["duke"]["next_attack"] = 3.0
        trace = []
        duke.prepare(actors, 1.3, trace)
        self.assertAlmostEqual(duke.next_boundary(1.3), 1.4)
        self.assertTrue(actors["duke"]["_duke_isolated"])
        cooldown = actors["duke"]["next_attack"]
        actors["ally"]["x"] = 7.1
        for _ in range(2):
            duke.prepare(actors, 1.35, trace)
            self.assertTrue(actors["duke"]["_duke_isolated"])
            self.assertEqual(actors["duke"]["next_attack"], cooldown)
        duke.prepare(actors, 1.4, trace)
        self.assertFalse(actors["duke"]["_duke_isolated"])
        self.assertAlmostEqual(
            actors["duke"]["next_attack"], 1.4 + (cooldown - 1.4) * 1.5
        )
        cooldown = actors["duke"]["next_attack"]
        actors["ally"]["hp"] = 0
        duke.prepare(actors, 1.4, trace)
        duke.prepare(actors, 1.45, trace)
        self.assertFalse(actors["duke"]["_duke_isolated"])
        self.assertEqual(actors["duke"]["next_attack"], cooldown)
        duke.prepare(actors, 1.5, trace)
        self.assertTrue(actors["duke"]["_duke_isolated"])
        self.assertEqual(duke.sample_counts["duke"], 3)
        actors["duke"]["hp"] = 0
        duke.prepare(actors, 1.55, trace)
        self.assertIsNone(duke.next_boundary(1.55))
        actors["duke"]["hp"] = 1
        duke.prepare(actors, 1.67, trace)
        self.assertAlmostEqual(duke.next_boundary(1.67), 1.7)
        self.assertEqual(duke.sample_counts["duke"], 4)

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
