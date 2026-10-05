"""Hidden Tesla lifecycle contracts, explicitly distinct from game calibration."""

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.spatial import (
    _active,
    _apply_effects,
    _apply_health,
    _blocked,
    _eligible,
    _load_actors,
    _move,
    _select_target,
    _validate_ground_positions,
)
from clashlab.teslas import TeslaCombat, compile_hidden_tesla

from test_adapters import entity_instance
from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "explicit-synthetic-Tesla-hypothesis-not-current-game-calibration"


def tesla_parameters(**changes):
    parameters = {
        "source": SOURCE,
        "initial_state": "dormant",
        "trigger_radius_multiplier": 1,
        "trigger_layers": ["ground", "air"],
        "excluded_trigger_entities": [],
        "destruction_threshold_fraction": 0.51,
        "reveal_delay_seconds": 0,
        "first_attack_delay_seconds": 0,
        "footprint_policy": "always_blocking_hypothesis",
        "dormant_damage_policy": "immune_until_revealed",
        "reveal_clock_policy": "continues_while_frozen",
        "readiness_policy": "attack_work_after_reveal_and_current_freeze",
    }
    parameters.update(changes)
    return parameters


def synthetic_tesla(parameters=None, **changes):
    parameters = tesla_parameters() if parameters is None else deepcopy(parameters)
    scale = parameters.pop("trigger_radius_multiplier")
    actor = synthetic_structure(
        "tesla",
        x=7,
        y=4,
        width=2,
        height=2,
        hitpoints=600,
        damage=20.4,
        attack_interval_seconds=0.6,
        range=7,
        tesla_model={
            **parameters,
            "kind": "hidden_tesla",
            "trigger_radius": 6 * scale,
        },
    )
    actor.update(changes)
    return actor


def loaded(actors):
    return _load_actors({"actors": actors}, 20, 12)


class TeslaCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def compilation_inputs(self):
        actor = synthetic_tesla()
        del actor["tesla_model"]
        actor["attack_model"] = {"kind": "single"}
        actor["entity_adapter"] = {"entity": "hidden-tesla", "level": 1}
        instance = entity_instance(
            "tesla",
            "hidden-tesla",
            1,
            "defense",
            tesla_parameters=tesla_parameters(trigger_radius_multiplier=0.5),
        )
        return actor, instance, self.catalog.entity("hidden-tesla")

    def test_adds_catalog_trigger_range_without_recompiling_weapon_or_hp(self):
        actor, instance, entity = self.compilation_inputs()
        original = deepcopy(actor)
        result = compile_hidden_tesla(actor, instance, entity)
        self.assertIs(result, actor)
        self.assertEqual(result["tesla_model"]["trigger_radius"], 3)
        for field in (
            "damage",
            "hitpoints",
            "range",
            "attack_interval_seconds",
            "attack_model",
        ):
            self.assertEqual(result[field], original[field])
        self.assertEqual(
            result["entity_adapter"]["tesla_parameters"], instance["tesla_parameters"]
        )

    def test_rejects_missing_and_unsupported_lifecycle_policies(self):
        for field, value in (
            ("footprint_policy", "displace_units_somehow"),
            ("dormant_damage_policy", "takes_splash_damage"),
            ("reveal_clock_policy", "guess_freeze_behavior"),
            ("readiness_policy", "instant_after_freeze"),
            ("trigger_layers", ["water"]),
            ("destruction_threshold_fraction", 0),
        ):
            with self.subTest(field=field):
                actor, instance, entity = self.compilation_inputs()
                instance["tesla_parameters"][field] = value
                with self.assertRaises(InputError):
                    compile_hidden_tesla(actor, instance, entity)
        actor, instance, entity = self.compilation_inputs()
        del instance["tesla_parameters"]["footprint_policy"]
        with self.assertRaises(InputError):
            compile_hidden_tesla(actor, instance, entity)

    def test_rejects_unaccounted_or_late_spawning_structure(self):
        for field, value in (
            ("counts_for_destruction", False),
            ("spawn_seconds", 1),
            ("first_attack_seconds", 1),
        ):
            with self.subTest(field=field):
                actor, instance, entity = self.compilation_inputs()
                actor[field] = value
                with self.assertRaises(InputError):
                    compile_hidden_tesla(actor, instance, entity)


class TeslaLifecycleTests(unittest.TestCase):
    def system(self, extra=None, parameters=None):
        actors = loaded([synthetic_tesla(parameters), *(extra or [])])
        return actors, TeslaCombat(actors, _select_target), []

    def test_dormant_actor_is_alive_counted_untargetable_and_cannot_fire(self):
        actors, combat, trace = self.system([synthetic_unit(x=0.5, y=5)])
        combat.prepare(actors, 0, trace)
        tesla, unit = actors["tesla"], actors["attacker"]
        self.assertTrue(_active(tesla, 0))
        self.assertTrue(tesla["counts_for_destruction"])
        self.assertIn((7, 4), _blocked(actors, 0))
        self.assertFalse(_eligible(unit, tesla, 0))
        self.assertEqual(
            combat.select_target(tesla, actors, 0, _blocked(actors, 0), 20, 12),
            (None, None),
        )
        self.assertEqual(trace, [])

    def test_ground_and_air_contact_reveal_at_inclusive_radius(self):
        for layer in ("ground", "air"):
            with self.subTest(layer=layer):
                unit = synthetic_unit(x=2, y=5, movement=layer, layer=layer)
                actors, combat, trace = self.system([unit])
                combat.prepare(actors, 0, trace)
                self.assertFalse(actors["tesla"]["_tesla_hidden"])
                self.assertTrue(_eligible(actors["attacker"], actors["tesla"], 0))
                self.assertEqual(combat.states["tesla"]["trigger_id"], "attacker")
                self.assertEqual(
                    [event["event"] for event in trace],
                    ["tesla_trigger", "tesla_reveal"],
                )

    def test_friendly_dead_unspawned_and_excluded_units_do_not_trigger(self):
        units = [
            synthetic_unit("friendly", x=2, y=5, team="defense"),
            synthetic_unit("dead", x=2, y=5),
            synthetic_unit("later", x=2, y=5, spawn_seconds=5),
            synthetic_unit("controlled", x=2, y=5, spawn_seconds="controlled"),
            synthetic_unit("excluded", x=2, y=5, entity_adapter={"entity": "minion"}),
        ]
        actors, combat, trace = self.system(
            units, tesla_parameters(excluded_trigger_entities=["minion"])
        )
        actors["dead"].update(hp=0, death_time=0)
        combat.prepare(actors, 0, trace)
        self.assertEqual(trace, [])
        actors["excluded"]["entity_adapter"]["entity"] = "archer"
        actors["excluded"]["immune_until"] = 10
        combat.prepare(actors, 1, trace)
        self.assertEqual(combat.states["tesla"]["trigger_id"], "excluded")

    def test_explicit_layer_filter_and_distance_then_id_tie(self):
        units = [
            synthetic_unit("z", x=2, y=5, movement="air", layer="air"),
            synthetic_unit("a", x=2, y=5, movement="air", layer="air"),
            synthetic_unit("near_ground", x=5, y=5),
        ]
        actors, combat, trace = self.system(
            units, tesla_parameters(trigger_layers=["air"])
        )
        combat.prepare(actors, 0, trace)
        self.assertEqual(combat.states["tesla"]["trigger_id"], "a")

    def test_threshold_includes_hidden_tesla_but_excludes_walls_traps_and_units(self):
        extras = [
            synthetic_structure("building", kind="building", x=12),
            synthetic_structure("wall", kind="wall", x=13),
            synthetic_structure("trap", x=14, entity_adapter={"entity": "bomb"}),
            synthetic_unit("counted-unit", team="defense", counts_for_destruction=True),
            synthetic_structure("enemy-building", x=15, team="attack"),
        ]
        actors, combat, trace = self.system(
            extras, tesla_parameters(destruction_threshold_fraction=0.5)
        )
        for key in ("wall", "trap", "counted-unit", "enemy-building"):
            actors[key].update(hp=0, death_time=0)
        combat.prepare(actors, 0, trace)
        self.assertEqual(trace, [])
        self.assertEqual(
            combat.result()["destruction_denominator_ids"]["tesla"],
            ["tesla", "building"],
        )
        actors["building"].update(hp=0, death_time=1)
        combat.prepare(actors, 1, trace)
        self.assertEqual(
            combat.states["tesla"]["reason"], "declared_destruction_threshold"
        )
        self.assertEqual(trace[0]["destruction_fraction"], 0.5)

    def test_delayed_reveal_does_not_cancel_when_trigger_dies_and_occurs_once(self):
        parameters = tesla_parameters(
            reveal_delay_seconds=0.75, first_attack_delay_seconds=0.25
        )
        actors, combat, trace = self.system([synthetic_unit(x=2, y=5)], parameters)
        combat.prepare(actors, 0, trace)
        self.assertEqual(combat.next_boundary(0), 0.75)
        self.assertEqual(combat.states["tesla"]["phase"], "revealing")
        self.assertFalse(_eligible(actors["attacker"], actors["tesla"], 0.5))
        self.assertEqual(
            combat.select_target(
                actors["tesla"], actors, 0.5, _blocked(actors, 0.5), 20, 12
            ),
            (None, None),
        )
        actors["attacker"].update(hp=0, death_time=0.25)
        combat.prepare(actors, 0.5, trace)
        self.assertTrue(actors["tesla"]["_tesla_hidden"])
        combat.prepare(actors, 0.75, trace)
        self.assertEqual(actors["tesla"]["next_attack"], 1)
        combat.prepare(actors, 1, trace)
        combat.prepare(actors, 2, trace)
        self.assertEqual(sum(event["event"] == "tesla_reveal" for event in trace), 1)
        self.assertIsNone(combat.next_boundary(2))

    def test_freeze_does_not_pause_reveal_but_readiness_resumes_attack_work(self):
        parameters = tesla_parameters(
            reveal_delay_seconds=1, first_attack_delay_seconds=0.5
        )
        actors, combat, trace = self.system([synthetic_unit(x=2, y=5)], parameters)
        combat.prepare(actors, 0, trace)
        _apply_effects(
            [
                {
                    "id": "freeze",
                    "kind": "freeze",
                    "targets": ["tesla"],
                    "duration_seconds": 4,
                }
            ],
            actors,
            0.5,
            trace,
        )
        actors["tesla"]["_hit_status_attack_rate"] = 0.5
        combat.prepare(actors, 1, trace)
        self.assertEqual(combat.states["tesla"]["revealed_at"], 1)
        self.assertEqual(actors["tesla"]["next_attack"], 5.5)
        self.assertTrue(_eligible(actors["attacker"], actors["tesla"], 1))

    def test_revealed_tesla_dies_normally_and_releases_footprint(self):
        actors, combat, trace = self.system([synthetic_unit(x=2, y=5)])
        combat.prepare(actors, 0, trace)
        _apply_health(actors, defaultdict(float, tesla=1000), defaultdict(float), 1)
        combat.prepare(actors, 1, trace)
        self.assertEqual(actors["tesla"]["death_time"], 1)
        self.assertEqual(combat.states["tesla"]["phase"], "destroyed")
        self.assertNotIn((7, 4), _blocked(actors, 1))
        self.assertEqual(combat.destruction_fraction("tesla", actors), 1)

    def test_destroyed_pending_actor_cannot_reveal_or_fire(self):
        actors, combat, trace = self.system(
            [synthetic_unit(x=2, y=5)], tesla_parameters(reveal_delay_seconds=1)
        )
        combat.prepare(actors, 0, trace)
        actors["tesla"].update(hp=0, death_time=0.5)
        combat.prepare(actors, 0.5, trace)
        combat.prepare(actors, 1, trace)
        self.assertIsNone(combat.next_boundary(0.5))
        self.assertIsNone(combat.states["tesla"]["revealed_at"])
        self.assertEqual(len(trace), 1)

    def test_always_blocking_policy_rejects_initial_ground_overlap(self):
        actors, _, _ = self.system([synthetic_unit(x=7.5, y=4.5)])
        with self.assertRaisesRegex(InputError, "blocking footprint"):
            _validate_ground_positions(actors, _blocked(actors, 0), 0)

    def test_reveal_blocking_policy_allows_hidden_passage_but_rejects_reveal_overlap(
        self,
    ):
        parameters = tesla_parameters(
            footprint_policy="blocks_on_reveal_reject_ground_overlap",
            reveal_delay_seconds=1,
        )
        actors, combat, trace = self.system([synthetic_unit(x=7.5, y=4.5)], parameters)
        _validate_ground_positions(actors, _blocked(actors, 0), 0)
        combat.prepare(actors, 0, trace)
        self.assertNotIn((7, 4), _blocked(actors, 0))
        with self.assertRaisesRegex(InputError, "displacement is unsupported"):
            combat.prepare(actors, 1, trace)
        self.assertTrue(actors["tesla"]["_tesla_hidden"])

    def test_air_overlap_does_not_block_reveal(self):
        parameters = tesla_parameters(
            footprint_policy="blocks_on_reveal_reject_ground_overlap"
        )
        actors, combat, trace = self.system(
            [synthetic_unit(x=7.5, y=4.5, movement="air", layer="air")], parameters
        )
        combat.prepare(actors, 0, trace)
        self.assertIn((7, 4), _blocked(actors, 0))
        self.assertEqual(combat.states["tesla"]["phase"], "revealed")

    def test_declared_initial_revealed_state_bypasses_reveal_delay(self):
        actors, combat, trace = self.system(
            parameters=tesla_parameters(
                initial_state="revealed",
                reveal_delay_seconds=10,
                first_attack_delay_seconds=0.5,
            )
        )
        self.assertFalse(actors["tesla"]["_tesla_hidden"])
        self.assertTrue(actors["tesla"]["blocking"])
        combat.prepare(actors, 0, trace)
        self.assertEqual(combat.states["tesla"]["revealed_at"], 0)
        self.assertEqual(actors["tesla"]["next_attack"], 0.5)


class TeslaMovementBoundaryTests(unittest.TestCase):
    def system(self, layer="air", speed=2):
        parameters = tesla_parameters(
            trigger_radius_multiplier=0.2, reveal_delay_seconds=0.35
        )
        actors = loaded(
            [
                synthetic_tesla(parameters),
                synthetic_unit(x=0, y=5, speed=speed, movement=layer, layer=layer),
            ]
        )
        return actors, TeslaCombat(actors, _select_target)

    def test_polyline_entry_accounts_for_prior_segments_and_horizon(self):
        actors, combat = self.system()
        unit = actors["attacker"]
        route = [(0, 2), (8, 2), (8, 5)]
        self.assertAlmostEqual(combat.first_crossing_delay(unit, route, 0, 10), 6.4)
        self.assertIsNone(combat.first_crossing_delay(unit, route, 0, 6))
        self.assertIsNone(combat.first_crossing_delay(unit, [(15, 2)], 0, 10))

    def test_crossing_respects_current_movement_slow_and_freeze(self):
        actors, combat = self.system()
        unit = actors["attacker"]
        unit["_hazard_movement_multiplier"] = 0.5
        unit["_hit_status_movement_multiplier"] = 0.5
        self.assertAlmostEqual(
            combat.first_crossing_delay(unit, [(10, 5)], 0, 20), 13.6
        )
        unit["frozen_until"] = 2
        self.assertIsNone(combat.first_crossing_delay(unit, [(10, 5)], 0, 20))

    def test_boundary_split_keeps_trigger_and_reveal_times_stable_across_step_sizes(
        self,
    ):
        observed = []
        for step in (1.0, 0.07):
            actors, combat = self.system()
            unit = actors["attacker"]
            trace = []
            time = 0.0
            while time < 5:
                combat.prepare(actors, time, trace)
                if combat.states["tesla"]["revealed_at"] is not None:
                    break
                horizon = step
                reveal_at = combat.next_boundary(time)
                if reveal_at is not None:
                    horizon = min(horizon, reveal_at - time)
                crossing = combat.first_crossing_delay(unit, [(12, 5)], time, horizon)
                if crossing is not None:
                    horizon = min(horizon, crossing)
                (unit["x"], unit["y"]), _ = _move(unit, [(12, 5)], horizon)
                time += horizon
            state = combat.states["tesla"]
            observed.append((state["triggered_at"], state["revealed_at"]))
        for trigger, reveal in observed:
            self.assertAlmostEqual(trigger, 3.4)
            self.assertAlmostEqual(reveal, 3.75)


if __name__ == "__main__":
    unittest.main()
