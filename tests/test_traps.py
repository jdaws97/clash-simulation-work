"""Trap lifecycle and movement boundaries, separate from game calibration."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene, simulate_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.spatial import _load_actors, simulate_spatial
from clashlab.traps import (
    RULES,
    RULESET,
    SCOPE,
    TrapCombat,
    compile_damage_trap,
    segment_circle_entry,
)

from test_adapters import entity_instance
from test_combat import pattern_scene
from test_defense_patterns import area_sector
from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-trap-lifecycle-not-current-game-calibration"


def trap_instance(entity="bomb", **changes):
    instance = {
        "id": "trap",
        "entity": entity,
        "level": 1,
        "town_hall": 16,
        "team": "defense",
        "x": 4,
        "y": 3,
        "parameters": {
            "source": SOURCE,
            "arming_seconds": 0,
            "delay_seconds": 0,
            "projectile_speed_tiles_per_second": None,
            "damage_multiplier": 1,
            "trigger_radius_multiplier": 1,
            "damage_radius_multiplier": 1,
            "excluded_trigger_entities": [],
            "excluded_damage_entities": [],
            "dead_trigger_policy": "fizzle",
        },
    }
    instance.update(changes)
    return instance


def trap_scene(trap, actors=None, effects=None, **changes):
    if actors is None:
        actors = [synthetic_unit(x=4.5, target_priorities=[]), synthetic_structure()]
    scene = pattern_scene(actors, effects)
    for actor in scene["actors"]:
        if actor["kind"] == "unit":
            actor.update(healing_class="troop", hazard_class="troop")
        if actor["movement"] == "ground":
            actor["wall_behavior"] = {"kind": "avoid", "source": SOURCE}
    scene.update(
        ruleset=RULESET,
        model_rules=deepcopy(RULES),
        traps=[trap],
        healing_stacking={"source": SOURCE, "groups": {}},
        persistent_hazards=[],
        target_scoring={
            "selection": "legacy_route_or_footprint_distance",
            "source": SOURCE,
        },
    )
    scene.update(changes)
    return scene


class DamageTrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def model(self, entity="bomb", **changes):
        model = compile_damage_trap(trap_instance(entity), self.catalog)
        model.update(damage=40, trigger_radius=1, damage_radius=0.5)
        model.update(changes)
        return model

    def test_trap_fires_once_and_is_not_a_destruction_actor(self):
        result = simulate_spatial(trap_scene(self.model(), duration_seconds=3))
        self.assertEqual(result["actors"]["attacker"]["hp"], 60)
        self.assertNotIn("trap", result["actors"])
        self.assertEqual(result["traps"]["resolved"], ["trap"])
        self.assertEqual(
            sum(event.get("event") == "trap_trigger" for event in result["trace"]), 1
        )

    def test_ground_bomb_ignores_air_unit_and_friendly_unit(self):
        actors = [
            synthetic_unit(x=4.5, target_priorities=[]),
            synthetic_unit(
                "air", x=4.5, movement="air", layer="air", target_priorities=[]
            ),
            synthetic_unit("friendly", x=4.5, team="defense", target_priorities=[]),
            synthetic_structure(),
        ]
        result = simulate_spatial(trap_scene(self.model(), actors))
        self.assertEqual(result["actors"]["attacker"]["hp"], 60)
        self.assertEqual(result["actors"]["air"]["hp"], 100)
        self.assertEqual(result["actors"]["friendly"]["hp"], 100)

    def test_protection_consumes_trap_without_applying_damage(self):
        effects = [
            {
                "id": "protect",
                "kind": "invulnerability",
                "targets": ["attacker"],
                "time_seconds": 0,
                "duration_seconds": 0.5,
            }
        ]
        result = simulate_spatial(trap_scene(self.model(), effects=effects))
        self.assertEqual(result["actors"]["attacker"]["hp"], 100)
        self.assertEqual(result["traps"]["resolved"], ["trap"])

    def test_delayed_ground_blast_uses_live_impact_membership(self):
        actors = [
            synthetic_unit(x=4.5, speed=4, first_attack_seconds=100),
            synthetic_structure(),
        ]
        result = simulate_spatial(trap_scene(self.model(delay_seconds=1), actors))
        self.assertEqual(result["actors"]["attacker"]["hp"], 100)
        impact = next(
            event for event in result["trace"] if event.get("event") == "trap_impact"
        )
        self.assertEqual(impact["targets"], [])
        self.assertEqual(impact["impact_position"], (4.5, 3.5))

    def test_small_trap_is_not_skipped_by_a_large_movement_step(self):
        times = []
        for step in (0.01, 1):
            actors = [
                synthetic_unit(speed=6, first_attack_seconds=100),
                synthetic_structure(),
            ]
            scene = trap_scene(
                self.model(trigger_radius=0.25),
                actors,
                maximum_step_seconds=step,
                recording_interval_seconds=5,
                duration_seconds=1,
            )
            result = simulate_spatial(scene)
            self.assertEqual(result["actors"]["attacker"]["hp"], 60)
            times.append(result["traps"]["triggered"]["trap"]["trigger_seconds"])
        self.assertAlmostEqual(times[0], 0.625)
        self.assertAlmostEqual(times[1], times[0])

    def test_late_arming_is_an_event_boundary(self):
        result = simulate_spatial(
            trap_scene(self.model(arming_seconds=0.7), maximum_step_seconds=1)
        )
        self.assertAlmostEqual(
            result["traps"]["triggered"]["trap"]["trigger_seconds"], 0.7
        )

    def test_seek_projectile_follows_live_target_and_hits_only_that_target(self):
        actors = [
            synthetic_unit(
                "first",
                x=3.5,
                movement="air",
                layer="air",
                speed=2,
                first_attack_seconds=100,
            ),
            synthetic_unit(
                "second", x=3.5, movement="air", layer="air", target_priorities=[]
            ),
            synthetic_structure(),
        ]
        model = self.model(
            "seeking-air-mine", trigger_radius=2, projectile_speed_tiles_per_second=1
        )
        result = simulate_spatial(trap_scene(model, actors))
        self.assertEqual(result["actors"]["first"]["hp"], 60)
        self.assertEqual(result["actors"]["second"]["hp"], 100)
        impact = next(
            event for event in result["trace"] if event.get("event") == "trap_impact"
        )
        self.assertAlmostEqual(impact["time_seconds"], 1)
        self.assertAlmostEqual(impact["impact_position"][0], 5.5)

    def test_dead_seeking_target_fizzles_without_retargeting(self):
        actors = [
            synthetic_unit(
                "first", x=4.5, movement="air", layer="air", target_priorities=[]
            ),
            synthetic_unit(
                "second", x=4.5, movement="air", layer="air", target_priorities=[]
            ),
            synthetic_structure(),
        ]
        effects = [
            {
                "id": "kill",
                "kind": "damage",
                "targets": ["first"],
                "time_seconds": 0.2,
                "amount": 100,
            }
        ]
        result = simulate_spatial(
            trap_scene(
                self.model("seeking-air-mine", delay_seconds=0.5), actors, effects
            )
        )
        self.assertEqual(result["actors"]["second"]["hp"], 100)
        self.assertTrue(
            any(event.get("event") == "trap_fizzle" for event in result["trace"])
        )

    def test_excluded_trigger_does_not_consume_trap(self):
        actor = synthetic_unit(
            x=4.5,
            movement="air",
            layer="air",
            target_priorities=[],
            entity_adapter={"entity": "minion"},
        )
        result = simulate_spatial(
            trap_scene(
                self.model("seeking-air-mine", excluded_trigger_entities=["minion"]),
                [actor, synthetic_structure()],
            )
        )
        self.assertEqual(result["traps"]["untriggered"], ["trap"])

    def test_trigger_crossing_follows_corners_not_the_chord(self):
        model = self.model(x=2, y=2, trigger_radius=0.5)
        scene = trap_scene(model, [synthetic_unit(x=0.5, y=0.5), synthetic_structure()])
        actors = _load_actors(scene, 9, 7)
        traps = TrapCombat([model], actors, 9, 7)
        self.assertIsNone(
            traps.first_crossing_delay(
                actors["attacker"], [(0.5, 4.5), (4.5, 4.5)], 0, 5
            )
        )
        self.assertIsNotNone(
            segment_circle_entry((0.5, 0.5), (4.5, 4.5), (2.5, 2.5), 0.5)
        )

    def test_trap_layout_cannot_overlap_a_blocking_structure(self):
        with self.assertRaisesRegex(InputError, "overlap"):
            simulate_spatial(trap_scene(self.model(x=7, y=3)))

    def test_catalog_adapter_and_scope_are_wired_to_engine(self):
        entities = [
            entity_instance(
                "archer",
                "archer",
                12,
                "attack",
                x=4.5,
                y=3.5,
                wall_parameters={"kind": "avoid", "source": SOURCE},
            )
        ]
        scene = area_sector(self.catalog, entities)
        scene.update(scope=SCOPE, model_rules=deepcopy(RULES), traps=[trap_instance()])
        result = simulate_entity_scene(scene, self.catalog)
        self.assertEqual(result["combat"]["traps"]["resolved"], ["trap"])
        self.assertFalse(result["full_game_prediction"])
        older = area_sector(self.catalog, entities)
        older["traps"] = []
        with self.assertRaisesRegex(InputError, "trap scope"):
            compile_entity_scene(older, self.catalog)


if __name__ == "__main__":
    unittest.main()
