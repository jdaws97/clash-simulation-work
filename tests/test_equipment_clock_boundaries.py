"""Exact RE-1/RE-2 reproductions and bounded strict-clock controls."""

from math import inf, nextafter
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.damage_receipts import DamageReceipts
from clashlab.hit_status import HitStatusCombat
from clashlab.poison_lizard import PoisonLizardExposure
from clashlab.rocket_backpack import RocketBackpackMotion
from test_remaining_equipment_contracts import (
    actors_for,
    lizard_parameters,
    rocket_parameters,
    settle,
)
from test_spatial import synthetic_unit


ROOT = Path(__file__).resolve().parents[1]


class EquipmentClockBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def lizard(self, duration=2):
        actors = actors_for(
            [
                synthetic_unit("pet"),
                synthetic_unit("victim", team="defense", hitpoints=1000),
            ]
        )
        parameters = lizard_parameters()
        parameters["duration_seconds"] = duration
        runtime = PoisonLizardExposure(
            self.catalog,
            {"pet": {"level": 10, "town_hall": 16, "parameters": parameters}},
            {"victim": "troop"},
            HitStatusCombat(actors),
        )
        return actors, runtime, DamageReceipts(), []

    @staticmethod
    def hit(actors, runtime, time, trace, key="initial-hit"):
        runtime.impact(
            key,
            {"source": "pet", "source_team": "attack"},
            actors["victim"],
            actors,
            time,
            trace,
        )

    def rocket(self, speed=10):
        actors = actors_for(
            [synthetic_unit("duke", x=0.5, layer="air", movement="air")]
        )
        actors["duke"]["hero_model"] = {"entity": "dragon-duke"}
        parameters = rocket_parameters()
        parameters["speed_tiles_per_second"] = speed
        return actors, RocketBackpackMotion(
            self.catalog, "duke", 27, 16, parameters, 14, 10
        )

    def test_re1_neighbor_cannot_beat_recall_or_consume_expiry_refresh(self):
        # Exact auditor schedule, then the immediate predecessor float too.
        for neighbor in (None, 0.24999999995, nextafter(0.25, 0)):
            with self.subTest(neighbor=neighbor):
                actors, runtime, receipts, trace = self.lizard()
                self.hit(actors, runtime, 0, trace)
                if neighbor is not None:
                    settle(
                        actors,
                        receipts,
                        runtime.resolve(actors, neighbor, trace, receipts),
                        neighbor,
                    )
                self.assertEqual(actors["victim"]["hp"], 1000)
                self.assertEqual(runtime.next_boundary(), 0.25)
                actors["victim"]["_recalled"] = True
                settle(
                    actors,
                    receipts,
                    runtime.resolve(actors, 0.25, trace, receipts),
                    0.25,
                )
                self.assertEqual(actors["victim"]["hp"], 1000)
                self.assertEqual(
                    [e for e in trace if e["event"] == "poison_lizard_pulse"], []
                )
                self.assertEqual(runtime.next_boundary(), 0.5)
        actors, runtime, receipts, trace = self.lizard(duration=0.5)
        self.hit(actors, runtime, 0, trace)
        with self.assertRaises(InputError):
            runtime.resolve(actors, nextafter(0.25, inf), trace, receipts)
        settle(actors, receipts, runtime.resolve(actors, 0.25, trace, receipts), 0.25)
        self.assertEqual(actors["victim"]["hp"], 992.5)
        self.assertEqual(runtime.resolve(actors, 0.25, trace, receipts), {})
        early = 0.49999999995
        self.assertEqual(runtime.resolve(actors, early, trace, receipts), {})
        self.assertEqual(runtime.next_boundary(), 0.5)
        self.hit(actors, runtime, early, trace, "refresh-before-expiry")
        exposure = runtime.exposures["pet", "victim"]
        self.assertEqual(exposure["starts_at"], 0)
        self.assertEqual(exposure["next_pulse"], 0.5)
        settle(actors, receipts, runtime.resolve(actors, 0.5, trace, receipts), 0.5)
        self.assertEqual(actors["victim"]["hp"], 977.5)
        settle(actors, receipts, runtime.resolve(actors, 0.75, trace, receipts), 0.75)
        expiry = exposure["expires_at"]
        self.assertEqual(
            runtime.resolve(actors, nextafter(expiry, 0), trace, receipts), {}
        )
        self.assertEqual(runtime.next_boundary(), expiry)
        self.assertEqual(runtime.resolve(actors, expiry, trace, receipts), {})
        self.assertEqual(runtime.exposures, {})

    def test_re2_demands_survive_predecessors_and_end_only_at_deadline(self):
        for early in (0.94999999995, nextafter(0.95, 0)):
            with self.subTest(early=early):
                actors, runtime = self.rocket()
                trace = []
                runtime.activate("paid-charge", actors["duke"], 0, trace)
                end = runtime.next_boundary()
                before = runtime.demands(early)
                runtime.resolve(actors, early, trace, DamageReceipts())
                self.assertEqual(runtime.demands(early), before)
                self.assertTrue(runtime.demands(early)["forced_motion"])
                self.assertEqual(runtime.next_boundary(), end)
                self.assertFalse(
                    any(e["event"] == "rocket_backpack_end" for e in trace)
                )
                with self.assertRaises(InputError):
                    runtime.resolve(
                        actors, nextafter(end, inf), trace, DamageReceipts()
                    )
                runtime.resolve(actors, end, trace, DamageReceipts())
                self.assertEqual(runtime.position(end), (10, 3.5))
                self.assertFalse(runtime.demands(end)["damage_immunity"])
                self.assertEqual(
                    [
                        e["time_seconds"]
                        for e in trace
                        if e["event"] == "rocket_backpack_end"
                    ],
                    [end],
                )
                runtime.resolve(actors, end, trace, DamageReceipts())
                self.assertEqual(
                    sum(e["event"] == "rocket_backpack_end" for e in trace), 1
                )
        # A positive remaining Freeze interval is still an interruption.
        actors, runtime = self.rocket()
        runtime.activate("paid-charge", actors["duke"], 0, [])
        actors["duke"]["frozen_until"] = nextafter(0.1, inf)
        runtime.prepare(actors["duke"], 0.1, [])
        self.assertFalse(runtime.demands(0.1)["forced_motion"])

    def test_re2_nonadvancing_and_overflow_clocks_reject_before_activation(self):
        # Exact reviewer input previously accepted and crashed in position(100).
        actors, runtime = self.rocket(1e18)
        trace = []
        with self.assertRaises(InputError):
            runtime.activate("paid-charge", actors["duke"], 100, trace)
        self.assertIsNone(runtime.state)
        self.assertIsNone(runtime.activation_id)
        self.assertEqual(trace, [])
        # Same finite speed with a representable start is valid, even below
        # geometric EPSILON: clocks have no arbitrary minimum-duration window.
        runtime.activate("paid-charge", actors["duke"], 0, trace)
        end = runtime.next_boundary()
        self.assertGreater(end, 0)
        runtime.resolve(actors, nextafter(end, 0), trace, DamageReceipts())
        self.assertTrue(runtime.demands(nextafter(end, 0))["forced_motion"])
        runtime.resolve(actors, end, trace, DamageReceipts())
        self.assertEqual(runtime.position(end), (10, 3.5))
        # Derived overflow is invalid even when each provided number is finite.
        parameters = rocket_parameters()
        parameters.update(endpoint_tiles=[1e308, 3.5], speed_tiles_per_second=1e-10)
        runtime = RocketBackpackMotion(
            self.catalog, "duke", 27, 16, parameters, 1e308, 10
        )
        with self.assertRaises(InputError):
            runtime.activate("overflow", actors["duke"], 0, [])
        self.assertIsNone(runtime.state)
        actors, runtime, receipts, trace = self.lizard()
        with self.assertRaises(InputError):
            self.hit(actors, runtime, 2**53, trace)
        self.assertEqual(runtime.exposures, {})
