"""Real catalog compilation and v13 combat for Giant, Wizard and Hog Rider."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.engine_rules import RULESET, SCOPE
from clashlab.spatial import simulate_spatial

from test_adapters import entity_instance, projectile, sector
from test_valkyrie_integration import building, valkyrie_sector


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "conditional-classic-integration-fixture-not-game-calibration"
TH16_LEVELS = {"giant": 12, "wizard": 12, "hog-rider": 13}


def classic_instance(entity_id, **changes):
    instance = entity_instance(
        entity_id,
        entity_id,
        TH16_LEVELS[entity_id],
        "attack",
        x=4.5,
        y=5.5,
        wall_parameters={
            "kind": "jump_enemy_walls" if entity_id == "hog-rider" else "avoid",
            "source": SOURCE,
        },
    )
    if entity_id == "wizard":
        shot = projectile()
        shot["inactive_primary_policy"] = "fizzle"
        instance["attack_parameters"] = {"projectile": shot, "radius": 1.5}
        instance["wizard_parameters"] = {
            "source": SOURCE,
            "splash_layer_policy": "all_declared_target_layers",
        }
    instance.update(changes)
    return instance


def launches(result, source):
    return [
        event
        for event in result["trace"]
        if event.get("event") == "projectile_launch" and event["source"] == source
    ]


class ClassicIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def compile_scene(self, entities, **changes):
        specification = valkyrie_sector(self.catalog, entities, **changes)
        return compile_entity_scene(specification, self.catalog)

    def test_th16_caps_compile_snapshot_statistics_and_simulate_real_hits(self):
        expected = {
            "giant": (2400, 188, 2, 1.5, 1, 5),
            "wizard": (290, 412.5, 1.5, 2, 3, 4),
            "hog-rider": (1380, 213, 1, 3, 0.6, 5),
        }
        for entity_id, values in expected.items():
            with self.subTest(entity=entity_id):
                compiled = self.compile_scene(
                    [classic_instance(entity_id), building("storage", 5)]
                )
                self.assertEqual(compiled["scope"], SCOPE)
                self.assertEqual(compiled["scene"]["ruleset"], RULESET)
                self.assertFalse(compiled["full_game_prediction"])
                actor = compiled["scene"]["actors"][0]
                for field, value in zip(
                    (
                        "hitpoints",
                        "damage",
                        "attack_interval_seconds",
                        "speed",
                        "range",
                        "housing_space",
                    ),
                    values,
                ):
                    self.assertEqual(actor[field], value)
                self.assertEqual(actor["spring_class"], "troop")
                self.assertEqual(
                    actor["entity_adapter"]["level"], TH16_LEVELS[entity_id]
                )
                self.assertEqual(actor["entity_adapter"]["town_hall"], 16)
                self.assertEqual(
                    actor["entity_adapter"]["snapshot_verification"],
                    "unverified_snapshot",
                )
                result = simulate_spatial(compiled["scene"])
                self.assertEqual(len(launches(result, entity_id)), 1)
                self.assertAlmostEqual(
                    result["actors"]["storage"]["hp"], 4050 - values[1]
                )

    def test_levels_above_th16_caps_are_rejected_for_each_troop(self):
        for entity_id, maximum in TH16_LEVELS.items():
            with (
                self.subTest(entity=entity_id),
                self.assertRaisesRegex(InputError, "unavailable"),
            ):
                self.compile_scene(
                    [
                        classic_instance(entity_id, level=maximum + 1),
                        building("storage", 5),
                    ]
                )

    def test_wizard_geometry_and_protection_are_target_centered(self):
        specification = self.compile_scene(
            [
                classic_instance("wizard"),
                building("a-primary", 5),
                building("behind-wizard", 1),
                building("beyond-primary", 8),
            ],
            effects=[
                {
                    "id": "protect-neighbor",
                    "kind": "invulnerability",
                    "time_seconds": 0,
                    "duration_seconds": 1,
                    "targets": ["beyond-primary"],
                }
            ],
        )
        wizard = specification["scene"]["actors"][0]
        self.assertEqual(wizard["range"], 3)
        self.assertEqual(wizard["attack_model"]["radius"], 1.5)
        self.assertEqual(wizard["attack_model"]["target_layers"], ["ground", "air"])
        result = simulate_spatial(specification["scene"])
        self.assertEqual(launches(result, "wizard")[0]["target"], "a-primary")
        impacts = [
            event
            for event in result["trace"]
            if event.get("event") == "projectile_impact" and event["source"] == "wizard"
        ]
        self.assertEqual(
            {event["target"] for event in impacts}, {"a-primary", "beyond-primary"}
        )
        self.assertTrue(
            next(event for event in impacts if event["target"] == "beyond-primary")[
                "protected"
            ]
        )
        self.assertEqual(result["actors"]["behind-wizard"]["hp"], 4050)
        self.assertEqual(result["actors"]["beyond-primary"]["hp"], 4050)
        self.assertEqual(result["actors"]["a-primary"]["hp"], 4050 - 412.5)

    def test_wizard_cannot_omit_or_hide_geometry_and_projectile_policies(self):
        variants = []
        missing_radius = classic_instance("wizard")
        missing_radius["attack_parameters"].pop("radius")
        variants.append(missing_radius)
        missing_parameters = classic_instance("wizard")
        missing_parameters.pop("wizard_parameters")
        variants.append(missing_parameters)
        missing_layer = classic_instance("wizard")
        missing_layer["wizard_parameters"].pop("splash_layer_policy")
        variants.append(missing_layer)
        unknown_layer = classic_instance("wizard")
        unknown_layer["wizard_parameters"][
            "splash_layer_policy"
        ] = "infer_from_damage_type"
        variants.append(unknown_layer)
        missing_dead_policy = classic_instance("wizard")
        missing_dead_policy["attack_parameters"]["projectile"].pop(
            "inactive_primary_policy"
        )
        variants.append(missing_dead_policy)
        wrong_center = classic_instance("wizard")
        wrong_center["attack_parameters"]["projectile"][
            "destination"
        ] = "fixed_source_center_at_launch"
        variants.append(wrong_center)
        for index, actor in enumerate(variants):
            with self.subTest(case=index), self.assertRaises(InputError):
                self.compile_scene([actor, building("storage", 5)])

    def test_giant_prefers_farther_defense_then_falls_back_to_storage(self):
        cannon = entity_instance(
            "cannon", "cannon", 1, "defense", x=7, y=4, first_attack_seconds=100
        )
        cannon["modifiers"]["hitpoints_multiplier"] = 0.1
        cannon["modifiers"]["source"] = SOURCE
        compiled = self.compile_scene(
            [classic_instance("giant"), building("storage", 1), cannon],
            duration_seconds=4,
        )
        giant = compiled["scene"]["actors"][0]
        self.assertEqual(giant["target_priority_tiers"], [["defense"], ["building"]])
        result = simulate_spatial(compiled["scene"])
        self.assertEqual(
            [event["target"] for event in launches(result, "giant")],
            ["cannon", "storage"],
        )
        self.assertEqual(result["actors"]["cannon"]["hp"], 0)
        self.assertEqual(result["actors"]["storage"]["hp"], 4050 - 188)

    def test_hog_crosses_real_enemy_walls_while_giant_remains_blocked(self):
        walls = [
            building(
                f"wall-{y}",
                6,
                entity="wall",
                level=1,
                y=y,
                counts_for_destruction=False,
            )
            for y in range(12)
        ]
        cannon = entity_instance(
            "cannon", "cannon", 1, "defense", x=9, y=4, first_attack_seconds=100
        )
        compiled = self.compile_scene(
            [classic_instance("hog-rider"), classic_instance("giant"), cannon, *walls],
            duration_seconds=2.5,
            recording_interval_seconds=0.1,
        )
        hog = compiled["scene"]["actors"][0]
        self.assertEqual(hog["wall_behavior"]["kind"], "jump_enemy_walls")
        result = simulate_spatial(compiled["scene"])
        self.assertEqual(result["actors"]["cannon"]["hp"], 0)
        self.assertEqual(result["actors"]["giant"]["x"], 4.5)
        self.assertGreater(result["actors"]["hog-rider"]["x"], 7)
        self.assertEqual(result["actors"]["hog-rider"]["layer"], "ground")
        self.assertTrue(
            all(result["actors"][f"wall-{y}"]["hp"] == 100 for y in range(12))
        )
        self.assertFalse(
            any(event.get("event") == "wall_impact" for event in result["trace"])
        )
        self.assertTrue(
            any(
                6 <= frame["actors"]["hog-rider"]["x"] < 7 for frame in result["frames"]
            )
        )

    def test_hog_requires_jump_and_wizard_parameters_cannot_attach_to_giant(self):
        hog = classic_instance(
            "hog-rider", wall_parameters={"kind": "avoid", "source": SOURCE}
        )
        with self.assertRaises(InputError):
            self.compile_scene([hog, building("storage", 5)])
        giant = classic_instance("giant")
        giant["wizard_parameters"] = deepcopy(
            classic_instance("wizard")["wizard_parameters"]
        )
        with self.assertRaises(InputError):
            self.compile_scene([giant, building("storage", 5)])

    def test_wizard_and_hog_cannot_enter_older_wall_free_scope(self):
        for entity_id in ("wizard", "hog-rider"):
            actor = classic_instance(entity_id)
            actor.pop("wall_parameters")
            with self.subTest(entity=entity_id), self.assertRaises(InputError):
                compile_entity_scene(
                    sector(self.catalog, [actor, building("storage", 5)]), self.catalog
                )


if __name__ == "__main__":
    unittest.main()
