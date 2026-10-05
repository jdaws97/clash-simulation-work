"""Shared target, splash and wall routes for conditional classic-troop adapters."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.classic_troops import CLASSIC_PATTERNS, compile_classic_troop
from clashlab.common import InputError
from clashlab.spatial import simulate_spatial

from test_deaths import damage
from test_spatial import synthetic_structure, synthetic_unit
from test_traps import trap_scene


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-classic-troop-conventions-not-replay-calibration"


def classic_scene(actors, effects=None, **changes):
    scene = trap_scene({}, actors, effects, traps=[], **changes)
    for original, compiled in zip(actors, scene["actors"]):
        for field in ("attack_model", "wall_behavior"):
            if field in original:
                compiled[field] = deepcopy(original[field])
    return scene


def wall_column(team="defense", kind="wall", rows=7):
    return [
        synthetic_structure(
            f"obstacle-{row}",
            x=4,
            y=row,
            kind=kind,
            team=team,
            hitpoints=10000,
            counts_for_destruction=False,
        )
        for row in range(rows)
    ]


class ClassicTroopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def inputs(self, entity_id):
        entity = self.catalog.entity(entity_id)
        row = self.catalog.level(entity_id, 1)
        wall = {
            "kind": "jump_enemy_walls" if entity_id == "hog-rider" else "avoid",
            "source": SOURCE,
        }
        instance = {"entity": entity_id, "wall_parameters": wall}
        layers = ["ground", "air"] if entity_id == "wizard" else ["ground"]
        pattern = {
            "kind": CLASSIC_PATTERNS[entity_id],
            "source": SOURCE,
            "target_kinds": ["defense", "building"],
            "target_layers": layers,
            "maximum_hp_fraction": 0,
            "projectile": {
                "timing": "instant",
                "delay_seconds": 0,
                "destination": "locked_actor_center_at_impact",
                "hit_radius": 0,
            },
        }
        if entity_id == "wizard":
            instance["wizard_parameters"] = {
                "source": SOURCE,
                "splash_layer_policy": "all_declared_target_layers",
            }
            pattern["radius"] = 1
            pattern["projectile"]["inactive_primary_policy"] = "fizzle"
        actor = synthetic_unit(
            entity_id,
            source=self.catalog.records[entity_id]["source"],
            hitpoints=row["hitpoints"],
            damage=row["stats"]["normal"]["damagePerShot"],
            range=entity["range"],
            speed=entity["movementSpeed"] / 8,
            attack_interval_seconds=entity["attackSpeed"],
            target_layers=layers,
            minimum_range=0,
            attack_model=pattern,
            wall_behavior=deepcopy(wall),
            entity_adapter={"entity": entity_id},
        )
        return actor, instance, entity

    def actor(self, entity_id, **changes):
        actor, instance, entity = self.inputs(entity_id)
        compile_classic_troop(actor, instance, entity)
        actor.update(changes)
        return actor

    def test_compiler_preserves_catalog_statistics_and_adds_spring_metadata(self):
        for entity_id in CLASSIC_PATTERNS:
            with self.subTest(entity=entity_id):
                actor, instance, entity = self.inputs(entity_id)
                statistics = {
                    field: actor[field]
                    for field in (
                        "hitpoints",
                        "damage",
                        "range",
                        "speed",
                        "attack_interval_seconds",
                    )
                }
                self.assertIs(compile_classic_troop(actor, instance, entity), actor)
                for field, expected in statistics.items():
                    self.assertEqual(actor[field], expected)
                self.assertEqual(actor["spring_class"], "troop")
                self.assertEqual(actor["housing_space"], entity["housingSpace"])
                self.assertEqual(actor["movement"], "ground")

    def test_giant_and_hog_prefer_defense_then_fall_back_after_it_dies(self):
        for entity_id in ("giant", "hog-rider"):
            with self.subTest(entity=entity_id):
                actor = self.actor(entity_id, x=5.5)
                storage = synthetic_structure(
                    "storage", kind="building", x=5, y=4, hitpoints=1
                )
                defense = synthetic_structure(hitpoints=1)
                result = simulate_spatial(
                    classic_scene([actor, storage, defense], duration_seconds=5)
                )
                targets = [
                    event["target"]
                    for event in result["trace"]
                    if event.get("event") == "projectile_launch"
                    and event["source"] == entity_id
                ]
                self.assertEqual(targets, ["tower", "storage"])
                self.assertEqual(result["actors"]["tower"]["hp"], 0)
                self.assertEqual(result["actors"]["storage"]["hp"], 0)

    def test_giant_can_fall_back_when_all_defenses_are_unreachable(self):
        actor = self.actor("giant", x=2.5)
        storage = synthetic_structure("storage", kind="building", x=3, hitpoints=1)
        result = simulate_spatial(
            classic_scene(
                [actor, storage, synthetic_structure(), *wall_column()],
                duration_seconds=0.1,
            )
        )
        self.assertEqual(result["actors"]["storage"]["hp"], 0)
        self.assertEqual(result["actors"]["tower"]["hp"], 100)

    def test_wizard_uses_nearest_structure_without_defense_preference(self):
        actor = self.actor("wizard", x=4.5)
        actor["attack_model"]["radius"] = 0.25
        storage = synthetic_structure("storage", kind="building", x=5, hitpoints=1000)
        result = simulate_spatial(
            classic_scene(
                [actor, storage, synthetic_structure()], duration_seconds=0.01
            )
        )
        launch = next(
            event
            for event in result["trace"]
            if event.get("event") == "projectile_launch"
        )
        self.assertEqual(launch["target"], "storage")
        self.assertEqual(result["actors"]["storage"]["hp"], 925)
        self.assertEqual(result["actors"]["tower"]["hp"], 100)

    def test_hog_jumps_enemy_wall_column_without_damage_or_air_reclassification(self):
        hog = self.actor("hog-rider")
        giant = self.actor("giant")
        result = simulate_spatial(
            classic_scene(
                [hog, giant, synthetic_structure(hitpoints=60), *wall_column()],
                duration_seconds=3,
                recording_interval_seconds=0.1,
            )
        )
        self.assertEqual(result["actors"]["tower"]["hp"], 0)
        self.assertGreater(result["actors"]["hog-rider"]["x"], 4)
        self.assertEqual(result["actors"]["hog-rider"]["layer"], "ground")
        self.assertEqual(result["actors"]["giant"]["x"], 0.5)
        self.assertTrue(
            all(result["actors"][f"obstacle-{row}"]["hp"] == 10000 for row in range(7))
        )
        self.assertFalse(
            any(event.get("event") == "wall_impact" for event in result["trace"])
        )
        self.assertTrue(
            any(
                4 <= frame["actors"]["hog-rider"]["x"] < 5 for frame in result["frames"]
            )
        )

    def test_hog_cannot_jump_friendly_walls_or_solid_building_columns(self):
        for kind in ("wall", "building"):
            with self.subTest(kind=kind):
                result = simulate_spatial(
                    classic_scene(
                        [
                            self.actor("hog-rider"),
                            synthetic_structure(),
                            *wall_column("attack", kind),
                        ],
                        duration_seconds=3,
                    )
                )
                self.assertEqual(result["actors"]["hog-rider"]["x"], 0.5)
                self.assertEqual(result["actors"]["tower"]["hp"], 100)

    def test_hog_routes_around_solid_building_footprints_through_real_opening(self):
        result = simulate_spatial(
            classic_scene(
                [
                    self.actor("hog-rider"),
                    synthetic_structure(hitpoints=60),
                    *wall_column("attack", "building", rows=6),
                ],
                duration_seconds=7,
                recording_interval_seconds=0.1,
            )
        )
        self.assertEqual(result["actors"]["tower"]["hp"], 0)
        self.assertTrue(
            any(frame["actors"]["hog-rider"]["y"] >= 6 for frame in result["frames"])
        )
        for frame in result["frames"]:
            actor = frame["actors"]["hog-rider"]
            self.assertFalse(4 <= actor["x"] < 5 and actor["y"] < 6)

    def test_melee_uses_catalog_range_against_target_footprint(self):
        for entity_id in ("giant", "hog-rider"):
            for inside in (True, False):
                with self.subTest(entity=entity_id, inside=inside):
                    actor = self.actor(entity_id)
                    actor["x"] = 7 - actor["range"] - (0 if inside else 0.01)
                    result = simulate_spatial(
                        classic_scene(
                            [actor, synthetic_structure(hitpoints=1000)],
                            duration_seconds=0.001,
                        )
                    )
                    self.assertEqual(
                        result["actors"]["tower"]["hp"],
                        1000 - actor["damage"] if inside else 1000,
                    )

    def test_ground_melee_cannot_acquire_an_air_layer_target(self):
        for entity_id in ("giant", "hog-rider"):
            result = simulate_spatial(
                classic_scene(
                    [self.actor(entity_id, x=6.5), synthetic_structure(layer="air")],
                    duration_seconds=0.1,
                )
            )
            self.assertEqual(result["actors"]["tower"]["hp"], 100)
            self.assertIsNone(result["actors"][entity_id]["target"])

    def test_wizard_can_acquire_either_layer_and_filter_splash_by_primary_layer(self):
        # Layered stationary fixtures isolate the shared damage filter; they do
        # not add defending-troop acquisition or aggro to the entity scene scope.
        for primary_layer in ("ground", "air"):
            for policy in ("all_declared_target_layers", "primary_target_layer_only"):
                with self.subTest(primary=primary_layer, policy=policy):
                    actor, instance, entity = self.inputs("wizard")
                    actor["x"] = 3.5
                    instance["wizard_parameters"]["splash_layer_policy"] = policy
                    compile_classic_troop(actor, instance, entity)
                    primary = synthetic_structure(
                        "primary", x=5, layer=primary_layer, hitpoints=1000
                    )
                    neighbor = synthetic_structure(
                        "neighbor",
                        x=6,
                        layer="air" if primary_layer == "ground" else "ground",
                        hitpoints=1000,
                    )
                    result = simulate_spatial(
                        classic_scene([actor, primary, neighbor], duration_seconds=0.01)
                    )
                    self.assertEqual(result["actors"]["primary"]["hp"], 925)
                    self.assertEqual(
                        result["actors"]["neighbor"]["hp"],
                        925 if policy == "all_declared_target_layers" else 1000,
                    )

    def test_wizard_delayed_impact_uses_live_membership_and_late_protection(self):
        wizard = self.actor("wizard", x=3.5)
        wizard["attack_model"]["projectile"] = {
            "timing": "launch_distance_delay",
            "speed_tiles_per_second": 2,
            "destination": "locked_actor_center_at_impact",
            "hit_radius": 0,
            "inactive_primary_policy": "fizzle",
        }
        primary = synthetic_structure("primary", x=5, hitpoints=1000)
        late = synthetic_structure(
            "late", x=6, hitpoints=1000, spawn_seconds=0.5, blocking=False
        )
        dead = synthetic_structure("dead", x=5, y=4, hitpoints=1000)
        friendly = synthetic_structure(
            "friendly", x=6, y=4, team="attack", hitpoints=1000
        )
        effects = [
            damage("wizard", time=0.5),
            damage("dead", time=0.5),
            {
                "id": "protect-late",
                "kind": "invulnerability",
                "targets": ["late"],
                "time_seconds": 0.5,
                "duration_seconds": 2,
            },
        ]
        result = simulate_spatial(
            classic_scene(
                [wizard, primary, late, dead, friendly], effects, duration_seconds=1.1
            )
        )
        self.assertEqual(result["actors"]["primary"]["hp"], 925)
        self.assertEqual(result["actors"]["late"]["hp"], 1000)
        self.assertEqual(result["actors"]["friendly"]["hp"], 1000)
        impacts = [
            event
            for event in result["trace"]
            if event.get("event") == "projectile_impact"
        ]
        self.assertEqual({event["target"] for event in impacts}, {"primary", "late"})
        self.assertTrue(
            next(event for event in impacts if event["target"] == "late")["protected"]
        )
        self.assertEqual({event["time_seconds"] for event in impacts}, {1})

    def test_wizard_fixed_and_locked_target_death_policies_remain_explicit(self):
        for fizzle in (True, False):
            wizard, instance, entity = self.inputs("wizard")
            wizard["x"] = 3.5
            wizard["attack_model"]["projectile"] = {
                "timing": "launch_distance_delay",
                "speed_tiles_per_second": 2,
                "destination": (
                    "locked_actor_center_at_impact"
                    if fizzle
                    else "fixed_target_center_at_launch"
                ),
                "hit_radius": 0,
                "inactive_primary_policy": (
                    "fizzle" if fizzle else "resolve_at_fixed_launch_position"
                ),
            }
            compile_classic_troop(wizard, instance, entity)
            result = simulate_spatial(
                classic_scene(
                    [
                        wizard,
                        synthetic_structure("primary", x=5),
                        synthetic_structure("neighbor", x=6),
                    ],
                    [damage("primary", time=0.5)],
                    duration_seconds=1.1,
                )
            )
            self.assertEqual(result["actors"]["neighbor"]["hp"], 100 if fizzle else 25)

    def test_wizard_cannot_infer_splash_radius_from_range_or_damage_type(self):
        actor, instance, entity = self.inputs("wizard")
        actor["attack_model"].pop("radius")
        self.assertEqual(entity["range"], 3)
        self.assertEqual(entity["damageType"], "splash")
        with self.assertRaisesRegex(InputError, "radius"):
            compile_classic_troop(actor, instance, entity)
        actor, instance, entity = self.inputs("wizard")
        compile_classic_troop(actor, instance, entity)
        self.assertEqual(actor["range"], 3)
        self.assertEqual(actor["attack_model"]["radius"], 1)

    def test_hog_rejects_ordinary_avoidance_and_hidden_wall_weapons(self):
        for parameters in (
            {"kind": "avoid", "source": SOURCE},
            {"kind": "jump_enemy_walls", "source": SOURCE, "weapon": {}},
        ):
            actor, instance, entity = self.inputs("hog-rider")
            instance["wall_parameters"] = parameters
            with self.assertRaisesRegex(InputError, "enemy-wall jumping"):
                compile_classic_troop(actor, instance, entity)

    def test_wizard_requires_layer_and_projectile_death_policies(self):
        for omitted in ("wizard_parameters", "inactive_primary_policy"):
            actor, instance, entity = self.inputs("wizard")
            if omitted == "wizard_parameters":
                instance.pop(omitted)
            else:
                actor["attack_model"]["projectile"].pop(omitted)
            with self.assertRaises(InputError):
                compile_classic_troop(actor, instance, entity)
        actor, instance, entity = self.inputs("wizard")
        instance["wizard_parameters"]["splash_layer_policy"] = "implicit"
        with self.assertRaises(InputError):
            compile_classic_troop(actor, instance, entity)

    def test_compiler_rejects_wrong_entity_or_ground_layer_and_delayed_melee(self):
        actor, instance, entity = self.inputs("giant")
        instance["entity"] = "wizard"
        with self.assertRaises(InputError):
            compile_classic_troop(actor, instance, entity)
        actor, instance, entity = self.inputs("hog-rider")
        actor["layer"] = "air"
        with self.assertRaises(InputError):
            compile_classic_troop(actor, instance, entity)
        actor, instance, entity = self.inputs("giant")
        actor["attack_model"]["projectile"]["timing"] = "launch_distance_delay"
        actor["attack_model"]["projectile"]["speed_tiles_per_second"] = 1
        with self.assertRaises(InputError):
            compile_classic_troop(actor, instance, entity)


if __name__ == "__main__":
    unittest.main()
