"""Declared nearby-side contact dynamics; synthetic, not game calibration."""

from copy import deepcopy
import unittest

from clashlab.catalog import Catalog
from clashlab.dragon_duke import CONTACT_POLICY, first_relative_circle_crossing
from clashlab.spatial import (
    EPSILON,
    _air_contact_motions,
    _move,
    _route,
    _weapon_range_boundary,
)
from test_dragon_duke import ROOT, air_ally, runtime
from test_spatial import synthetic_structure


class DukeContactDynamicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def actors(self, ally_x=7):
        actors, combat, duke = runtime(
            self.catalog,
            [
                air_ally(x=ally_x),
                synthetic_structure(
                    "goal", x=13, y=9, width=2, height=2, hitpoints=10000
                ),
            ],
            items=[],
        )
        actors["duke"].update(speed=2.5, target="goal", next_attack=1)
        return actors, combat, duke

    def test_entry_and_exit_approaches_resolve_with_finite_motion_and_same_cooldown(
        self,
    ):
        for start in (6.99, 7.1):
            results = []
            for step in (1, 0.1, 0.017):
                actors, _, duke = self.actors(start)
                trace = []
                now = 0.0
                count = 0
                while now < 0.9 - 1e-10:
                    count += 1
                    self.assertLess(count, 150)
                    duke.prepare(actors, now, trace)
                    route = _route(actors["duke"], actors["goal"], set(), 50, 50)
                    motions = {
                        "duke": (route, 2.5 if route else 0),
                        "ally": ([(20, 10)], 2),
                    }
                    duke.resolve_contact_motions(
                        actors, motions, now, 50, 50, set(), trace
                    )
                    end = min(now + step, 0.9)
                    end = _weapon_range_boundary(
                        actors, motions, now, end, {"ally", "goal"}
                    )
                    crossing = duke.first_crossing_delay(
                        actors,
                        {k: v[0] for k, v in motions.items()},
                        {k: v[1] for k, v in motions.items()},
                        now,
                        end - now,
                    )
                    if crossing is not None:
                        end = min(end, now + crossing)
                    self.assertGreater(end, now)
                    positions = {
                        key: _move(actors[key], path, end - now, speed=speed)[0]
                        for key, (path, speed) in motions.items()
                    }
                    for key, (x, y) in positions.items():
                        actors[key].update(x=x, y=y)
                    now = end
                duke.prepare(actors, now, trace)
                self.assertFalse(actors["duke"]["_duke_isolated"])
                self.assertEqual(actors["duke"]["_hero_damage_multiplier"], 1)
                self.assertEqual(
                    duke.result()["isolation_contact_policy"], CONTACT_POLICY
                )
                self.assertGreater(duke.contact_motion_counts["duke"], 0)
                before = actors["duke"]["next_attack"]
                actors["ally"]["hp"] = 0
                duke.prepare(actors, now, trace)
                self.assertTrue(actors["duke"]["_duke_isolated"])
                self.assertAlmostEqual(
                    actors["duke"]["next_attack"], now + (before - now) / 1.5
                )
                self.assertEqual(actors["duke"]["_hero_damage_multiplier"], 2)
                results.append((actors["duke"]["x"], before))
            for actual in results[1:]:
                for a, b in zip(actual, results[0]):
                    self.assertAlmostEqual(a, b, places=8)

    def test_unsupported_contact_plans_keep_normal_motion_and_guard_path(self):
        for variant in (
            "forced",
            "paused",
            "extra_friend",
            "moving_enemy",
            "faster",
            "outside",
        ):
            actors, _, duke = self.actors()
            if variant == "extra_friend":
                actors["extra"] = deepcopy(actors["ally"])
                actors["extra"].update(id="extra", x=9)
            if variant == "moving_enemy":
                actors["goal"]["movement"] = "air"
            if variant == "outside":
                actors["ally"]["x"] = 6.99
            duke.prepare(actors, 0, [])
            motions = {"duke": ([(20, 10)], 2.5), "ally": ([(20, 10)], 2)}
            excluded = {"duke"} if variant == "forced" else set()
            if variant == "paused":
                del motions["duke"]
            if variant == "faster":
                motions["ally"] = ([(20, 10)], 4)
            original = deepcopy(motions)
            duke.resolve_contact_motions(actors, motions, 0, 50, 50, excluded, [])
            with self.subTest(variant=variant):
                self.assertEqual(motions, original)

    def test_established_contact_stops_and_restarts_without_isolation_switch(self):
        actors, _, duke = self.actors()
        trace = []
        for now, ally_motion, expected_speed in (
            (0, ([(20, 10)], 2), 2),
            (0.01, ([], 0), 0),
            (0.02, ([(20, 10)], 2), 2),
        ):
            duke.prepare(actors, now, trace)
            motions = {"duke": ([(20, 10)], 2.5), "ally": ally_motion}
            duke.resolve_contact_motions(actors, motions, now, 50, 50, set(), trace)
            self.assertEqual(motions["duke"][1], expected_speed)
            self.assertIsNone(
                duke.first_crossing_delay(
                    actors,
                    {k: v[0] for k, v in motions.items()},
                    {k: v[1] for k, v in motions.items()},
                    now,
                    0.01,
                )
            )
            for key, (route, speed) in motions.items():
                position, _ = _move(actors[key], route, 0.01, speed=speed)
                actors[key].update(x=position[0], y=position[1])
            self.assertFalse(actors["duke"]["_duke_isolated"])
            self.assertEqual(actors["duke"]["next_attack"], 1)
        # A fresh contact with a stationary ally does not acquire this state.
        actors, _, duke = self.actors()
        duke.prepare(actors, 0, [])
        motions = {"duke": ([(20, 10)], 2.5), "ally": ([], 0)}
        duke.resolve_contact_motions(actors, motions, 0, 50, 50, set(), [])
        self.assertEqual(motions["duke"][1], 2.5)

    def test_neutral_translation_does_not_invent_a_roundoff_circle_crossing(self):
        for offset in (-1e-15, 0, 1e-15):
            for inside in (False, True):
                a = dict(x=0, y=0, width=0, height=0)
                b = dict(x=3 + offset, y=0, width=0, height=0)
                self.assertIsNone(
                    first_relative_circle_crossing(
                        a, b, [(10, 0)], [(13 + offset, 0)], 1, 1, 3, 0.1, inside
                    )
                )

    def test_nonzero_slow_crossings_update_isolation_and_cooldown_without_contact(self):
        for entering in (False, True):
            for drift in (EPSILON / 4, EPSILON / 2):
                for horizon in (0.5, 10, 180):
                    with self.subTest(entering=entering, drift=drift, horizon=horizon):
                        actors, _, duke = self.actors()
                        actors["goal"]["x"] = 30  # Outside both Duke weapon ranges.
                        speed = 1 - drift if entering else 1 + drift
                        actors["duke"]["speed"] = speed
                        duke.boundary_sides[("duke", "ally")] = dict(
                            inside_after=not entering,
                            time_seconds=0,
                            first_position=(10, 10),
                            second_position=(7, 10),
                        )
                        duke.prepare(actors, 0, [])
                        before = actors["duke"]["next_attack"]
                        motions = {"duke": ([(25, 10)], speed), "ally": ([(25, 10)], 1)}
                        self.assertFalse(
                            duke.resolve_contact_motions(
                                actors, motions, 0, 50, 50, set(), []
                            )
                        )
                        # The synthetic initial after-side is not a previously
                        # committed motion event, so remove it before querying.
                        duke.boundary_sides.clear()
                        delay = duke.first_crossing_delay(
                            actors,
                            {k: v[0] for k, v in motions.items()},
                            {k: v[1] for k, v in motions.items()},
                            0,
                            horizon,
                        )
                        self.assertEqual(delay, 2 * EPSILON)
                        for key, (route, effective_speed) in motions.items():
                            point, _ = _move(
                                actors[key], route, delay, speed=effective_speed
                            )
                            actors[key].update(x=point[0], y=point[1])
                        duke.prepare(actors, delay, [])
                        self.assertEqual(actors["duke"]["_duke_isolated"], not entering)
                        self.assertEqual(
                            actors["duke"]["_hero_damage_multiplier"],
                            1 if entering else 2,
                        )
                        ratio = 1.5 if entering else 1 / 1.5
                        self.assertAlmostEqual(
                            actors["duke"]["next_attack"],
                            delay + (before - delay) * ratio,
                        )

    def test_entering_second_friend_does_not_reverse_committed_entry(self):
        actors, _, duke = self.actors()
        duke.prepare(actors, 0, [])
        motions = {"duke": ([(20, 10)], 2.5), "ally": ([(20, 10)], 2)}
        duke.resolve_contact_motions(actors, motions, 0, 50, 50, set(), [])
        actors["extra"] = deepcopy(actors["ally"])
        actors["extra"]["id"] = "extra"
        duke.boundary_sides[("duke", "extra")] = dict(
            inside_after=True,
            time_seconds=0.01,
            first_position=(10, 10),
            second_position=(7, 10),
        )
        duke.prepare(actors, 0.01, [])
        motions = {
            "duke": ([(20, 10)], 2.5),
            "ally": ([(20, 10)], 2),
            "extra": ([(20, 10)], 2.25),
        }
        duke.resolve_contact_motions(actors, motions, 0.01, 50, 50, set(), [])
        self.assertEqual(motions["duke"][1], 2)
        self.assertEqual(duke.active_contacts, {("duke", "ally")})
        self.assertIsNone(
            duke.first_crossing_delay(
                actors,
                {k: v[0] for k, v in motions.items()},
                {k: v[1] for k, v in motions.items()},
                0.01,
                0.01,
            )
        )

    def test_ground_target_following_resolves_before_duke_and_his_follower(self):
        actors, _, duke = self.actors()
        actors["ground"] = deepcopy(actors["ally"])
        actors["ground"].update(
            id="ground", team="defend", x=10, movement="ground", layer="ground"
        )
        actors["ally"].update(
            target="ground",
            range=3,
            damage=1,
            attack_model={"kind": "single"},
            target_priorities=["unit"],
            target_layers=["ground"],
        )
        actors["follower"] = deepcopy(actors["ally"])
        actors["follower"].update(
            id="follower",
            team="defend",
            target="duke",
            target_layers=["air"],
            speed=3,
        )
        duke.prepare(actors, 0, [])
        original = {
            "duke": ([(20, 10)], 2.5),
            "ally": ([], 0),
            "ground": ([(20, 10)], 1),
            "follower": ([], 0),
        }
        motions = deepcopy(original)
        _air_contact_motions(actors, motions, 0, 50, 50)
        self.assertEqual(motions["follower"][1], 2.5)
        contacts = duke.resolve_contact_motions(
            actors,
            motions,
            0,
            50,
            50,
            set(),
            [],
            original,
        )
        self.assertEqual(contacts, {"duke"})
        motions = {**original, **{key: motions[key] for key in contacts}}
        _air_contact_motions(actors, motions, 0, 50, 50)
        self.assertEqual(
            [motions[k][1] for k in ("ally", "duke", "follower")], [1, 1, 1]
        )

    def test_nonpartner_crossing_is_delivered_once_without_isolation_or_motion_relay(
        self,
    ):
        for entering in (False, True):
            with self.subTest(entering=entering):
                self.nonpartner_crossing(entering)

    def nonpartner_crossing(self, entering):
        actors, _, duke = self.actors()
        trace = []
        duke.prepare(actors, 0, trace)
        motions = {"duke": ([(20, 10)], 2.5), "ally": ([(20, 10)], 2)}
        duke.resolve_contact_motions(actors, motions, 0, 50, 50, set(), trace)
        actors["extra"] = deepcopy(actors["ally"])
        actors["extra"]["id"] = "extra"
        duke.boundary_sides[("duke", "extra")] = dict(
            inside_after=not entering,
            time_seconds=0.01,
            first_position=(10, 10),
            second_position=(7, 10),
        )
        now = 0.01
        for expected_crossing in (True, False):
            duke.prepare(actors, now, trace)
            motions = {
                "duke": ([(20, 10)], 2.5),
                "ally": ([], 0) if entering else ([(20, 10)], 2),
                "extra": ([(20, 10)], 1),
            }
            duke.resolve_contact_motions(actors, motions, now, 50, 50, set(), trace)
            delay = duke.first_crossing_delay(
                actors,
                {k: v[0] for k, v in motions.items()},
                {k: v[1] for k, v in motions.items()},
                now,
                0.01,
            )
            self.assertEqual(delay is not None, expected_crossing)
            self.assertFalse(actors["duke"]["_duke_isolated"])
            self.assertEqual(actors["duke"]["next_attack"], 1)
            self.assertEqual(motions["duke"][1], 0 if entering else 2)
            if delay is not None:
                self.assertEqual(
                    duke.crossing_hints[("duke", "extra")]["inside_after"], entering
                )
                for key, (route, speed) in motions.items():
                    point, _ = _move(actors[key], route, delay, speed=speed)
                    actors[key].update(x=point[0], y=point[1])
                now += delay

    def test_committed_entry_keeps_translation_and_updates_weapon_follower(self):
        # Synthetic geometry derived from a captured two-epsilon entry. Its
        # slight penetration is a committed crossing, not a larger radius.
        actors, _, duke = self.actors()
        actors["duke"].update(x=46.404460931810085, y=31.89003031291636)
        actors["ally"].update(x=46.16025503383779, y=34.88007437253419)
        actors["goal"].update(x=44, y=28)
        pair = ("duke", "ally")
        duke.boundary_sides[pair] = dict(
            inside_after=True,
            time_seconds=0,
            first_position=(46.404460931810085, 31.89003031291636),
            second_position=(46.16025503419188, 34.880074372720244),
        )
        # A hostile airborne weapon touching the Duke must follow the final
        # resolved motion, not his original faster nearby pursuit proposal.
        actors["follower"] = deepcopy(actors["ally"])
        actors["follower"].update(
            id="follower",
            team="defend",
            target="duke",
            range=3,
            speed=3,
            x=actors["duke"]["x"] + 3,
            y=actors["duke"]["y"],
            damage=1,
            attack_model={"kind": "single"},
            target_layers=["air"],
            target_priorities=["unit"],
        )
        trace = []
        for now in (0, 0.01):
            duke.prepare(actors, now, trace)
            motions = {
                "duke": ([(46.261574012535384, 31.22232525784512)], 2.5),
                "ally": ([(43.5, 33.482245150226674)], 2),
                "follower": ([], 0),
            }
            duke.resolve_contact_motions(actors, motions, now, 56, 56, set(), trace)
            self.assertEqual(motions["duke"][1], 2)
            _air_contact_motions(actors, motions, now, 56, 56)
            self.assertEqual(motions["follower"][1], 2)
            self.assertIsNone(
                duke.first_crossing_delay(
                    actors,
                    {k: v[0] for k, v in motions.items()},
                    {k: v[1] for k, v in motions.items()},
                    now,
                    0.01,
                )
            )
            for key, (route, speed) in motions.items():
                position, _ = _move(actors[key], route, 0.01, speed=speed)
                actors[key].update(x=position[0], y=position[1])


if __name__ == "__main__":
    unittest.main()
