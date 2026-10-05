"""Only an ordinary retained in-range weapon may omit unrelated contact events."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from clashlab.spatial import (
    _load_actors,
    _retained_primary_stays_in_range,
    _weapon_range_boundary,
    simulate_spatial,
)
from test_combat import pattern_scene
from test_spatial import synthetic_structure, synthetic_unit


def scene():
    return pattern_scene(
        [
            synthetic_unit(
                "primary",
                x=2.5,
                layer="air",
                movement="air",
                hitpoints=10000,
                range=2,
                damage=1,
            ),
            synthetic_unit(
                "entrant",
                x=9,
                layer="air",
                movement="air",
                hitpoints=10000,
                range=2,
                damage=1,
            ),
            synthetic_structure("tower", x=0, hitpoints=10000, range=5, damage=1),
        ],
        width=14,
        height=7,
        duration_seconds=3,
        maximum_step_seconds=3,
        recording_interval_seconds=10,
    )


class RetainedContactEventTests(unittest.TestCase):
    def test_irrelevant_entry_is_not_an_event_but_every_shot_and_final_state_is_preserved(
        self,
    ):
        with patch(
            "clashlab.spatial._weapon_range_boundary", wraps=_weapon_range_boundary
        ) as queries:
            optimized = simulate_spatial(scene())
            optimized_times = [call.args[2] for call in queries.call_args_list]
        with (
            patch(
                "clashlab.spatial._retained_primary_stays_in_range", return_value=False
            ),
            patch(
                "clashlab.spatial._weapon_range_boundary", wraps=_weapon_range_boundary
            ) as queries,
        ):
            original = simulate_spatial(scene())
            original_times = [call.args[2] for call in queries.call_args_list]
        self.assertEqual(optimized, original)
        self.assertIn(1.75, original_times)
        self.assertNotIn(1.75, optimized_times)
        self.assertLess(len(optimized_times), len(original_times))

    def test_unacquired_outgoing_minimum_range_or_secondary_owner_keeps_contact_events(
        self,
    ):
        spec = scene()
        actors = _load_actors(spec, 14, 7)
        tower = actors["tower"]
        tower["target"] = "primary"
        self.assertTrue(_retained_primary_stays_in_range(tower, actors, {}, 0, 1))
        for changes, motions in (
            ({"target": None}, {}),
            ({}, {"primary": ([(12, 3.5)], 10)}),
            ({"_minimum_range": 2.1}, {}),
            ({"recipe_model": {}}, {}),
            ({"attack_model": {"kind": "multi_target"}}, {}),
        ):
            candidate = deepcopy(tower)
            candidate.update(changes)
            self.assertFalse(
                _retained_primary_stays_in_range(candidate, actors, motions, 0, 1)
            )


if __name__ == "__main__":
    unittest.main()
