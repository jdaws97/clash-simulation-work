"""Catalog-compiled Valkyries across routing, impacts, deaths, and cooldowns."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.engine_rules import RULES, RULESET, SCOPE
from clashlab.spatial import center, simulate_spatial, target_distance

from test_adapters import entity_instance, projectile, sector


SOURCE = "conditional-Valkyrie-integration-fixture-not-game-calibration"
ROOT = Path(__file__).resolve().parents[1]


def valkyrie_instance(**changes):
    instance = entity_instance(
        "valkyrie",
        "valkyrie",
        11,
        "attack",
        x=4.5,
        y=5.5,
        attack_parameters={"projectile": projectile(), "radius": 1.5},
        wall_parameters={"kind": "avoid", "source": SOURCE},
        valkyrie_parameters={
            "source": SOURCE,
            "neighbor_gap_tiles": 1,
            "samples_per_tile": 4,
            "maximum_extra_travel_seconds": 10,
        },
    )
    instance.update(changes)
    return instance


def building(instance_id, x, entity="gold-storage", level=17, **changes):
    instance = entity_instance(
        instance_id,
        entity,
        level,
        "defense",
        x=x,
        y=4,
        mode="passive",
        statistics_mode="none",
        attack_parameters={},
        inactive_attack_interval_seconds=1,
    )
    instance.update(changes)
    return instance


def valkyrie_sector(catalog, entities, **changes):
    specification = sector(catalog, entities)
    specification.update(
        scope=SCOPE,
        model_rules=deepcopy(RULES),
        traps=[],
        persistent_hazards=[],
        healing_spells=[],
        healing_stacking={"source": SOURCE, "groups": {}},
        target_scoring={
            "selection": "arrival_time_then_footprint_distance",
            "source": SOURCE,
        },
        duration_seconds=0.01,
        maximum_step_seconds=0.01,
        recording_interval_seconds=1,
    )
    specification.update(changes)
    return specification


def events(result, kind):
    return [
        event
        for event in result["trace"]
        if event.get("event") == kind and event.get("source") == "valkyrie"
    ]


class ValkyrieIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def compile_scene(self, entities, **changes):
        specification = valkyrie_sector(self.catalog, entities, **changes)
        return compile_entity_scene(specification, self.catalog)

    def test_th16_level11_uses_pinned_catalog_statistics_and_explicit_geometry(self):
        compiled = self.compile_scene([valkyrie_instance(), building("primary", 5)])
        actor = compiled["scene"]["actors"][0]
        self.assertEqual(compiled["scope"], SCOPE)
        self.assertEqual(compiled["scene"]["ruleset"], RULESET)
        self.assertFalse(compiled["full_game_prediction"])
        self.assertEqual(actor["entity_adapter"]["level"], 11)
        self.assertEqual(actor["entity_adapter"]["town_hall"], 16)
        self.assertEqual(actor["hitpoints"], 2600)
        self.assertAlmostEqual(actor["damage"], 428.4)
        self.assertEqual(actor["attack_interval_seconds"], 1.8)
        self.assertEqual(actor["speed"], 3)
        self.assertEqual(actor["range"], 0.5)
        self.assertEqual(actor["attack_model"]["kind"], "source_radial")
        self.assertEqual(actor["attack_model"]["radius"], 1.5)
        self.assertEqual(
            actor["attack_model"]["projectile"]["destination"],
            "fixed_source_center_at_launch",
        )
        self.assertEqual(
            actor["entity_adapter"]["snapshot_verification"], "unverified_snapshot"
        )
        result = simulate_spatial(compiled["scene"])
        self.assertEqual(len(events(result, "projectile_launch")), 1)

    def test_th16_cannot_compile_level12_or_omit_explicit_splash_radius(self):
        for actor in (
            valkyrie_instance(level=12),
            valkyrie_instance(attack_parameters={"projectile": projectile()}),
        ):
            with self.subTest(actor=actor), self.assertRaises(InputError):
                self.compile_scene([actor, building("primary", 5)])

    def test_source_center_hits_behind_valkyrie_without_hitting_beyond_primary(self):
        compiled = self.compile_scene(
            [
                valkyrie_instance(),
                building("a-primary", 5),
                building("behind-source", 1),
                building("beyond-primary", 8),
            ]
        )
        initial = {actor["id"]: actor for actor in compiled["scene"]["actors"]}
        primary_center = center(initial["a-primary"])
        self.assertGreater(
            target_distance(primary_center, initial["behind-source"]), 1.5
        )
        self.assertLessEqual(
            target_distance(primary_center, initial["beyond-primary"]), 1.5
        )
        result = simulate_spatial(compiled["scene"])
        launches = events(result, "projectile_launch")
        self.assertEqual(len(launches), 1)
        self.assertEqual(launches[0]["target"], "a-primary")
        self.assertEqual(
            {event["target"] for event in events(result, "projectile_impact")},
            {"a-primary", "behind-source"},
        )
        for target_id in ("a-primary", "behind-source"):
            self.assertAlmostEqual(
                result["actors"][target_id]["hp"],
                initial[target_id]["hitpoints"] - 428.4,
            )
        self.assertEqual(
            result["actors"]["beyond-primary"]["hp"],
            initial["beyond-primary"]["hitpoints"],
        )

    def test_repositioning_defers_first_swing_and_preserves_path_across_step_sizes(
        self,
    ):
        first_attacks = []
        for wall_kind in ("avoid", "clear_obstructions"):
            early_positions = []
            for step in (0.01, 0.25):
                with self.subTest(wall_kind=wall_kind, maximum_step_seconds=step):
                    actor = valkyrie_instance()
                    if wall_kind == "clear_obstructions":
                        actor["wall_parameters"] = self.clearing_parameters()
                    entities = [
                        actor,
                        building("a-primary", 5),
                        building("neighbor", 9),
                    ]
                    compiled = self.compile_scene(
                        entities,
                        duration_seconds=2,
                        maximum_step_seconds=step,
                        recording_interval_seconds=10,
                    )
                    early = simulate_spatial(compiled["scene"])
                    self.assertFalse(events(early, "projectile_launch"))
                    early_positions.append(center(early["actors"]["valkyrie"]))
                    compiled["scene"]["duration_seconds"] = 6
                    result = simulate_spatial(compiled["scene"])
                    launches = events(result, "projectile_launch")
                    self.assertGreaterEqual(len(launches), 2)
                    first_attacks.append(launches[0]["time_seconds"])
                    # This fixture's four-neighbor exterior route is 6.5 tiles;
                    # launch checks occur at solver boundaries after arrival.
                    self.assertGreaterEqual(launches[0]["time_seconds"], 6.5 / 3 - 1e-9)
                    self.assertLessEqual(
                        launches[0]["time_seconds"], 6.5 / 3 + step + 1e-9
                    )
                    for previous, following in zip(launches, launches[1:]):
                        self.assertAlmostEqual(
                            following["time_seconds"] - previous["time_seconds"], 1.8
                        )
                    hits_at_first_swing = {
                        event["target"]
                        for event in events(result, "projectile_impact")
                        if abs(event["time_seconds"] - launches[0]["time_seconds"])
                        < 1e-9
                    }
                    self.assertEqual(hits_at_first_swing, {"a-primary", "neighbor"})
            self.assertAlmostEqual(early_positions[0][0], early_positions[1][0])
            self.assertAlmostEqual(early_positions[0][1], early_positions[1][1])
        self.assertLessEqual(max(first_attacks) - min(first_attacks), 0.25 + 1e-9)

    def test_one_building_dying_does_not_duplicate_swing_or_reset_cooldown(self):
        for primary_dies in (True, False):
            with self.subTest(primary_dies=primary_dies):
                fragile = building(
                    "a-primary" if primary_dies else "neighbor",
                    5 if primary_dies else 1,
                    entity="barracks",
                    level=1,
                )
                survivor = building(
                    "neighbor" if primary_dies else "a-primary",
                    1 if primary_dies else 5,
                )
                compiled = self.compile_scene(
                    [valkyrie_instance(), fragile, survivor], duration_seconds=3.7
                )
                result = simulate_spatial(compiled["scene"])
                launches = events(result, "projectile_launch")
                self.assertEqual(
                    [round(event["time_seconds"], 8) for event in launches],
                    [0, 1.8, 3.6],
                )
                self.assertEqual(launches[0]["target"], "a-primary")
                self.assertTrue(
                    all(event["target"] == survivor["id"] for event in launches[1:])
                )
                self.assertEqual(result["actors"][fragile["id"]]["death_time"], 0)
                impacts = events(result, "projectile_impact")
                self.assertEqual(
                    sum(event["target"] == fragile["id"] for event in impacts), 1
                )
                self.assertEqual(
                    sum(event["target"] == survivor["id"] for event in impacts), 3
                )
                self.assertAlmostEqual(
                    result["actors"][survivor["id"]]["hp"], 4050 - 3 * 428.4
                )
                self.assertAlmostEqual(result["actors"]["valkyrie"]["x"], 4.5)
                self.assertAlmostEqual(result["actors"]["valkyrie"]["y"], 5.5)

    @staticmethod
    def clearing_parameters():
        return {
            "kind": "clear_obstructions",
            "source": SOURCE,
            "route_cost": "travel_seconds_plus_nominal_clearance",
            "cooldown": "shared_with_main_weapon",
            "range": 0.5,
            "first_attack_seconds": 0,
            "impact_timing": "instant",
        }

    def test_wall_and_main_hits_share_clock_without_inventing_wall_splash(self):
        walls = [
            building(
                f"wall-{y}",
                4,
                entity="wall",
                level=1,
                y=y,
                counts_for_destruction=False,
            )
            for y in range(12)
        ]
        compiled = self.compile_scene(
            [
                valkyrie_instance(x=3.5, wall_parameters=self.clearing_parameters()),
                building("primary", 5),
                *walls,
            ],
            duration_seconds=2,
        )
        result = simulate_spatial(compiled["scene"])
        wall_hits = events(result, "wall_impact")
        launches = events(result, "projectile_launch")
        self.assertEqual(len(wall_hits), 1)
        self.assertEqual(wall_hits[0]["time_seconds"], 0)
        self.assertEqual(wall_hits[0]["cooldown"], "shared_with_main_weapon")
        self.assertEqual(len(launches), 1)
        self.assertAlmostEqual(launches[0]["time_seconds"], 1.8)
        destroyed_walls = [
            actor
            for actor in result["actors"].values()
            if actor["kind"] == "wall" and actor["hp"] == 0
        ]
        self.assertEqual(len(destroyed_walls), 1)
        self.assertAlmostEqual(result["actors"]["primary"]["hp"], 4050 - 428.4)


if __name__ == "__main__":
    unittest.main()
