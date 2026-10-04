"""Impactful synthetic boundary checks; no full-battle calibration claim."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.builder_huts import BuilderHutCombat
from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError
from clashlab.defense_variants import GearedCannonCombat, compile_geared_cannon
from clashlab.guardians import compile_guardian
from clashlab.logger_guardian import LoggerCombat
from clashlab.rates import pause_attack_work
from clashlab.spatial import _load_actors
from clashlab.spell_towers import SpellTowerCombat

from test_adapters import entity_instance
from test_builder_huts import compiled_hut, repair_target
from test_combat import synthetic_pattern
from test_guardians import guardian_instance
from test_spatial import synthetic_structure, synthetic_unit
from test_spell_towers import spell_tower_instance, tower_actor, target_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-defense-lifecycle-not-calibration"


def cannon(catalog):
    instance = entity_instance(
        "cannon",
        "cannon",
        20,
        "defense",
        mode="gearedUpBurst",
        statistics_mode="gearedUpBurst",
    )
    instance["geared_cannon_parameters"] = {
        "source": SOURCE,
        "status": "experimental_not_replay_calibrated",
        "burst_timing": "snapshot_timeBetweenBursts_is_post_last_shot_gap",
        "targeting": "retain_eligible_primary_reacquire_per_shot",
        "freeze": "pause_remaining_shot_clock_preserve_burst_index",
    }
    actor = synthetic_structure("cannon", x=8, y=4, entity_adapter={"entity": "cannon"})
    return compile_geared_cannon(
        actor,
        instance,
        catalog.entity("cannon"),
        catalog.level("cannon", 20),
        instance["modifiers"],
    )


def logger(catalog):
    instance = guardian_instance("logger", attack_parameters={})
    instance["logger_parameters"] = {
        "source": SOURCE,
        "status": "experimental_not_replay_calibrated",
        "speed_tiles_per_second": 10,
        "corridor_half_width_tiles": 0.5,
        "collision": "launch_sampled_centers_once_per_log",
        "trajectory": "fixed_planar_ray_to_primary_then_snapshot_postHitTileRange",
        "source_loss": "released_logs_persist",
        "target_motion": "hit_if_still_inside_corridor_at_sampled_arrival",
        "pushback": "delegated_shared_clipped_linear_displacement",
        "protected_pushback": "suppress",
        "death": "no_extra_effect_explicit_uncalibrated_hypothesis",
    }
    actor = synthetic_unit(
        "guardian",
        team="defense",
        spawn_seconds="controlled",
        x=19.5,
        y=11.5,
        entity_adapter={"entity": "logger"},
    )
    compile_guardian(
        actor,
        instance,
        catalog.entity("logger"),
        catalog.level("logger", 1),
        instance["modifiers"],
        8,
    )
    actor.update(
        spawn_seconds=0,
        hp=8000,
        maximum_hp=8000,
        frozen_until=0,
        immune_until=0,
        next_attack=0,
    )
    return actor


class DefenseVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_cannon_freeze_midburst_preserves_shot_index_and_gap(self):
        target = synthetic_unit(
            "target", x=12.5, y=5.5, minimum_range=0, attack_model=synthetic_pattern()
        )
        actors = _load_actors({"actors": [cannon(self.catalog), target]}, 30, 30)
        combat = PatternCombat(actors)
        runtime = GearedCannonCombat(actors, combat)
        actor, target = actors["cannon"], actors["target"]
        trace = []
        self.assertTrue(runtime.launch(actor, target, actors, 0, trace))
        pause_attack_work(actor, 0.1, 0.6)
        actor["frozen_until"] = 0.6
        self.assertFalse(runtime.launch(actor, target, actors, 0.3, trace))
        self.assertAlmostEqual(actor["next_attack"], 0.692)
        for time in (0.692, 0.884, 1.076):
            self.assertTrue(runtime.launch(actor, target, actors, time, trace))
        self.assertEqual(runtime.states["cannon"]["next_shot_index"], 0)
        self.assertAlmostEqual(actor["next_attack"], 2.676)
        actor["hp"] = 0
        runtime.prepare(actors, 1.1, trace)
        self.assertTrue(runtime.states["cannon"]["destroyed"])
        self.assertEqual(runtime.states["cannon"]["cancelled_shots"], 0)

    def test_logger_released_hits_survive_source_loss_and_push_only_unprotected_targets(
        self,
    ):
        actor = logger(self.catalog)

        def target(key, x, **changes):
            return synthetic_unit(
                key,
                x=x,
                y=11.5,
                hp=2000,
                maximum_hp=2000,
                frozen_until=0,
                immune_until=0,
                **changes,
            )

        primary = target("primary", 16.5)
        secondary = target("secondary", 14.5, layer="air", movement="air")
        secondary["immune_until"] = 1
        actors = {value["id"]: value for value in (actor, primary, secondary)}
        pushes = []
        runtime = LoggerCombat(actors, lambda *args: pushes.append(args[0]["id"]))
        trace = []
        self.assertTrue(runtime.launch(actor, primary, actors, 0, trace))
        actor["hp"] = 0
        self.assertAlmostEqual(runtime.next_boundary(0), 0.3)
        self.assertEqual(runtime.resolve(actors, 0.3, trace), {"primary": 575})
        self.assertEqual(runtime.resolve(actors, 0.5, trace), {"secondary": 0})
        self.assertEqual(pushes, ["primary"])
        self.assertEqual(runtime.resolve(actors, 0.5, trace), {})
        self.assertEqual(runtime.result()["pending_impacts"], 0)

    def test_logger_without_displacement_or_experimental_geometry_fails(self):
        actor = logger(self.catalog)
        with self.assertRaises(InputError):
            LoggerCombat({actor["id"]: actor}, None)
        actor["logger_model"]["parameters"]["status"] = "verified"
        with self.assertRaises(InputError):
            LoggerCombat({actor["id"]: actor}, lambda *args: None)

    def test_lightning_resets_builder_target_without_making_worker_an_actor(self):
        hut, target = compiled_hut(self.catalog), repair_target()
        actors = {hut["id"]: hut, target["id"]: target}
        runtime = BuilderHutCombat(actors, 20, 20)
        trace = []
        runtime.prepare(actors, 0, trace)
        worker_id = runtime.states["hut"]["worker_id"]
        self.assertEqual(runtime.states["hut"]["target"], "target")

        runtime.lightning_reset(
            [worker_id], actors, 0.2, trace, "restart_declared_first_repair_delay"
        )
        self.assertIsNone(runtime.states["hut"]["target"])
        self.assertEqual(runtime.states["hut"]["route"], [])
        self.assertNotIn(worker_id, actors)
        self.assertGreater(runtime.workers[worker_id]["next_attack"], 0.2)
        runtime.prepare(actors, 0.2, trace)
        self.assertEqual(runtime.states["hut"]["target"], "target")

    def test_earthquake_tower_released_pulse_survives_source_loss_and_respects_immunity(
        self,
    ):
        instance = spell_tower_instance("earthquake", level=4, town_hall=17)
        parameters = instance["spell_tower_parameters"]
        parameters["effect"] = {
            "radius_multiplier": 1,
            "duration_multiplier": 1,
            "membership_policy": "one_pulse_at_released_payload_arrival",
            "status": "experimental_not_replay_calibrated",
            "statistic_basis": "snapshot_troopDamagePercent_of_current_maximum_hp",
            "damage_fraction_multiplier": 1,
            "stacking_policy": "independent_additive_single_pulses",
        }
        parameters["recipients"].update(
            target_kinds=["unit"], target_layers=["ground", "air"]
        )
        parameters["cast"].update(delay_seconds=0, impact_delay_seconds=0.25)
        parameters["death"]["policy"] = "none"
        actors = _load_actors(
            {
                "actors": [
                    tower_actor(self.catalog, instance),
                    target_unit("victim", x=8.5),
                    target_unit("protected", x=9.5),
                ]
            },
            30,
            30,
        )
        actors["protected"]["immune_until"] = 1
        runtime = SpellTowerCombat(actors, None)
        trace = []
        runtime.prepare(actors, 0, trace)
        self.assertEqual(runtime.resolve(actors, 0, trace), {})
        actors["spell-tower"].update(hp=0, death_time=0.1)
        runtime.prepare(actors, 0.25, trace)
        self.assertEqual(
            runtime.resolve(actors, 0.25, trace), {"protected": 0, "victim": 300}
        )
        self.assertEqual(runtime.resolve(actors, 0.25, trace), {})
        self.assertFalse(runtime.fields)
        # A representable positive arrival must survive the spatial tolerance.
        parameters["cast"]["impact_delay_seconds"] = 1e-12
        tiny_actors = _load_actors(
            {
                "actors": [
                    tower_actor(self.catalog, instance),
                    target_unit("victim", x=8.5),
                ]
            },
            30,
            30,
        )
        tiny_runtime = SpellTowerCombat(tiny_actors, None)
        tiny_runtime.prepare(tiny_actors, 0, [])
        self.assertEqual(tiny_runtime.resolve(tiny_actors, 0, []), {})
        self.assertEqual(tiny_runtime.next_boundary(0), 1e-12)
        tiny_runtime.prepare(tiny_actors, 1e-12, [])
        self.assertEqual(tiny_runtime.resolve(tiny_actors, 1e-12, []), {"victim": 300})


if __name__ == "__main__":
    unittest.main()
