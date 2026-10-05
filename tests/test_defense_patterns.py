"""Directional splash, finite ammunition and actual-death blast checks."""

import unittest
from copy import deepcopy
from math import sqrt
from pathlib import Path

from clashlab.adapters import compile_entity_scene, simulate_entity_scene
from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat, validate_pattern
from clashlab.common import InputError
from clashlab.defense_patterns import SCOPE as AREA_SCOPE, RULES as AREA_RULES
from clashlab.spatial import _load_actors, simulate_spatial

from test_adapters import entity_instance, projectile, sector
from test_combat import pattern_scene
from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "declared-splash-fixture-not-current-Clash-calibration"


def area_parameters():
    flight = projectile()
    flight["inactive_primary_policy"] = "fizzle"
    return {
        "projectile": flight,
        "splash_layer_policy": "primary_target_layer_only",
        "radius_multiplier": 1,
        "source": SOURCE,
    }


def cone_parameters():
    parameters = area_parameters()
    del parameters["radius_multiplier"]
    parameters["cone_parameters"] = {
        "statistic_basis": "two_linear_distance_bands_from_snapshot_hypothesis",
        "axis": "launch_source_to_impact_point",
        "half_angle_degrees": 45,
        "near_band_end": 1,
        "far_band_end": 5,
        "source": SOURCE,
    }
    return parameters


def scatter_instance(**changes):
    return entity_instance(
        "scatter",
        "scattershot",
        5,
        "defense",
        attack_parameters=cone_parameters(),
        ammunition_parameters={"initial_rounds": 90, "source": SOURCE},
        **changes,
    )


def bomb_instance(**changes):
    return entity_instance(
        "bomb",
        "bomb-tower",
        11,
        "defense",
        attack_parameters=area_parameters(),
        bomb_death_parameters={
            "source": SOURCE,
            "delay_seconds": 0.5,
            "radius": 3.5,
            "damage_multiplier": 1,
            "target_layers": ["ground"],
        },
        **changes,
    )


def area_sector(catalog, entities):
    specification = sector(catalog, entities)
    specification.update(
        scope=AREA_SCOPE,
        model_rules=deepcopy(AREA_RULES),
        healing_stacking={"source": SOURCE, "groups": {}},
        healing_spells=[],
        persistent_hazards=[],
        target_scoring={
            "selection": "arrival_time_then_footprint_distance",
            "source": SOURCE,
        },
    )
    for instance in specification["entities"]:
        if instance["entity"] == "pekka":
            instance["wall_parameters"] = {"kind": "avoid", "source": SOURCE}
    return specification


def cone_combat(layer_policy="primary_target_layer_only"):
    units = [
        synthetic_unit(name, x=x, y=y, hitpoints=2000, first_attack_seconds=1000)
        for name, x, y in (
            ("primary", 8.5, 5.5),
            ("near", 8, 5.5),
            ("far", 5.5, 5.5),
            ("angular-boundary", 7.5, 6.5),
            ("radial-boundary", 3.5, 5.5),
            ("outside", 3.4, 5.5),
            ("front", 9.5, 5.5),
            ("side", 8.5, 7.5),
        )
    ]
    units.append(synthetic_unit("air", x=8, y=5.5, layer="air", movement="air"))
    shooter = synthetic_structure(
        "scatter", x=14, y=5, damage=576, range=20, attack_interval_seconds=1000
    )
    scene = pattern_scene([shooter, *units], width=20, height=12)
    scene["actors"][0]["attack_model"] = {
        "kind": "directional_splash",
        "source": SOURCE,
        "target_kinds": ["unit"],
        "target_layers": ["ground", "air"],
        "maximum_hp_fraction": 0,
        "projectile": projectile(),
        "splash_layer_policy": layer_policy,
        "directional_splash": {
            "source": SOURCE,
            "axis": "launch_source_to_impact_point",
            "half_angle_degrees": 45,
            "distance_bands": [
                {
                    "start": 0,
                    "end": 1,
                    "start_multiplier": 1,
                    "end_multiplier": 420 / 576,
                },
                {
                    "start": 1,
                    "end": 5,
                    "start_multiplier": 420 / 576,
                    "end_multiplier": 150 / 576,
                },
            ],
        },
    }
    actors = _load_actors(scene, 20, 12)
    return actors, PatternCombat(actors)


class DefensePatternTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_cone_hits_behind_with_falloff_and_excludes_front_side_and_other_layer(
        self,
    ):
        actors, combat = cone_combat()
        trace = []
        combat.launch(actors["scatter"], actors["primary"], actors, 0, trace)
        damage = combat.resolve(actors, 0, trace)
        self.assertEqual(
            set(damage),
            {"primary", "near", "far", "angular-boundary", "radial-boundary"},
        )
        self.assertEqual(damage["primary"], 576)
        self.assertAlmostEqual(damage["near"], 498)
        self.assertAlmostEqual(damage["far"], 285)
        self.assertAlmostEqual(
            damage["angular-boundary"], 420 - (sqrt(2) - 1) / 4 * 270
        )
        self.assertAlmostEqual(damage["radial-boundary"], 150)

    def test_cross_layer_branch_is_explicit_and_uses_same_geometry(self):
        actors, combat = cone_combat("all_declared_target_layers")
        combat.launch(actors["scatter"], actors["primary"], actors, 0, [])
        damage = combat.resolve(actors, 0, [])
        self.assertAlmostEqual(damage["air"], damage["near"])

    def test_fixed_impact_survives_primary_and_source_death_using_launch_axis(self):
        actors, _ = cone_combat()
        actors["scatter"]["attack_model"]["projectile"] = {
            "timing": "launch_distance_delay",
            "speed_tiles_per_second": 2,
            "destination": "fixed_target_center_at_launch",
            "hit_radius": 0,
            "inactive_primary_policy": "resolve_at_fixed_launch_position",
        }
        combat = PatternCombat(actors)
        combat.launch(actors["scatter"], actors["primary"], actors, 0, [])
        for name in ("scatter", "primary"):
            actors[name]["hp"] = 0
            actors[name]["death_time"] = 1
            actors[name]["x"] = 0
        damage = combat.resolve(actors, 3, [])
        self.assertNotIn("primary", damage)
        self.assertAlmostEqual(damage["near"], 498)
        self.assertAlmostEqual(damage["far"], 285)

    def test_legacy_fizzle_branch_remains_available(self):
        actors, combat = cone_combat()
        combat.launch(actors["scatter"], actors["primary"], actors, 0, [])
        actors["primary"]["hp"] = 0
        actors["primary"]["death_time"] = 0
        trace = []
        self.assertEqual(dict(combat.resolve(actors, 0, trace)), {})
        self.assertEqual(trace[0]["event"], "projectile_fizzle")

    def test_protection_of_primary_does_not_protect_secondary_units(self):
        actors, combat = cone_combat()
        actors["primary"]["immune_until"] = 10
        combat.launch(actors["scatter"], actors["primary"], actors, 0, [])
        damage = combat.resolve(actors, 0, [])
        self.assertNotIn("primary", damage)
        self.assertAlmostEqual(damage["near"], 498)

    def test_newcomer_membership_is_checked_at_impact(self):
        actors, combat = cone_combat()
        actors["outside"]["x"] = 20
        combat.launch(actors["scatter"], actors["primary"], actors, 0, [])
        actors["outside"]["x"] = 5.5
        damage = combat.resolve(actors, 0, [])
        self.assertAlmostEqual(damage["outside"], 285)

    def test_moving_primary_can_miss_fixed_point_without_canceling_cone(self):
        actors, _ = cone_combat()
        actors["scatter"]["attack_model"]["projectile"].update(
            destination="fixed_target_center_at_launch",
            inactive_primary_policy="resolve_at_fixed_launch_position",
        )
        combat = PatternCombat(actors)
        combat.launch(actors["scatter"], actors["primary"], actors, 0, [])
        actors["primary"]["x"] = 11.5
        damage = combat.resolve(actors, 0, [])
        self.assertNotIn("primary", damage)
        self.assertAlmostEqual(damage["near"], 498)

    def test_finite_ammunition_limits_launches_and_reports_depletion_once(self):
        actors, _ = cone_combat()
        actors["scatter"]["weapon_ammunition"] = {"initial_rounds": 2, "source": SOURCE}
        combat = PatternCombat(actors)
        trace = []
        for time in range(5):
            combat.launch(actors["scatter"], actors["primary"], actors, time, trace)
        self.assertEqual(
            sum(event["event"] == "projectile_launch" for event in trace), 2
        )
        self.assertEqual(sum(event["event"] == "weapon_depleted" for event in trace), 1)
        self.assertEqual(combat.result()["ammunition_remaining"], {"scatter": 0})

    def test_scattershot_maps_level_falloff_minimum_range_and_capacity(self):
        spec = area_sector(self.catalog, [scatter_instance()])
        actor = compile_entity_scene(spec, self.catalog)["scene"]["actors"][0]
        self.assertEqual(actor["hitpoints"], 5410)
        self.assertEqual(actor["damage"], 576)
        self.assertEqual(actor["minimum_range"], 3)
        self.assertEqual(actor["weapon_ammunition"]["initial_rounds"], 90)
        self.assertEqual(
            actor["attack_model"]["directional_splash"]["distance_bands"][1][
                "end_multiplier"
            ],
            150 / 576,
        )

    def test_scattershot_rejects_missing_geometry_or_ammunition_and_over_capacity(self):
        for field in ("ammunition_parameters", "attack_parameters"):
            instance = scatter_instance()
            del instance[field]
            with self.assertRaises(InputError):
                compile_entity_scene(
                    area_sector(self.catalog, [instance]), self.catalog
                )
        instance = scatter_instance()
        instance["ammunition_parameters"]["initial_rounds"] = 91
        with self.assertRaises(InputError):
            compile_entity_scene(area_sector(self.catalog, [instance]), self.catalog)

    def test_scattershot_does_not_fire_inside_its_blind_zone(self):
        tank = entity_instance("tank", "pekka", 11, "attack", first_attack_seconds=1000)
        result = simulate_entity_scene(
            area_sector(self.catalog, [tank, scatter_instance()]), self.catalog
        )
        self.assertEqual(result["combat"]["actors"]["tank"]["hp"], 7700)
        self.assertFalse(
            any(
                event.get("event") == "projectile_launch"
                for event in result["combat"]["trace"]
            )
        )

    def test_wizard_tower_maps_radius_and_ground_primary_does_not_hit_air_branch(self):
        wizard = entity_instance(
            "wizard", "wizard-tower", 16, "defense", attack_parameters=area_parameters()
        )
        tank = entity_instance("tank", "pekka", 11, "attack", first_attack_seconds=1000)
        air = entity_instance("air", "minion", 12, "attack", first_attack_seconds=1000)
        result = simulate_entity_scene(
            area_sector(self.catalog, [tank, air, wizard]), self.catalog
        )
        actor = result["combat"]["actors"]["wizard"]
        self.assertEqual(actor["attack_model"]["radius"], 1)
        self.assertAlmostEqual(actor["damage"], 132.6)
        # Equal-distance targets use instance identifiers; choose the ground one.
        wizard_spec = area_sector(self.catalog, [tank, air, wizard])
        wizard_spec["entities"][1]["id"] = "z-air"
        result = simulate_entity_scene(wizard_spec, self.catalog)
        self.assertAlmostEqual(result["combat"]["actors"]["tank"]["hp"], 7700 - 132.6)
        self.assertEqual(result["combat"]["actors"]["z-air"]["hp"], 120)

    def test_bomb_tower_requires_death_scope_and_cannot_hide_its_blast(self):
        instance = bomb_instance()
        with self.assertRaisesRegex(InputError, "death-effects"):
            compile_entity_scene(sector(self.catalog, [instance]), self.catalog)

    def test_bomb_tower_actual_death_releases_delayed_ground_blast_once(self):
        tank = entity_instance("tank", "pekka", 11, "attack", first_attack_seconds=1000)
        air = entity_instance("air", "minion", 12, "attack", first_attack_seconds=1000)
        spec = area_sector(
            self.catalog, [tank, air, bomb_instance(first_attack_seconds=1000)]
        )
        spec.update(
            healing_stacking={"source": SOURCE, "groups": {}},
            healing_spells=[],
            duration_seconds=1,
            effects=[
                {
                    "id": "destroy-bomb-tower",
                    "kind": "damage",
                    "time_seconds": 0.2,
                    "targets": ["bomb"],
                    "amount": 2700,
                }
            ],
        )
        for instance in spec["entities"][:2]:
            if instance["entity"] == "pekka":
                instance["wall_parameters"] = {"kind": "avoid", "source": SOURCE}
        result = simulate_entity_scene(spec, self.catalog)["combat"]
        self.assertAlmostEqual(result["actors"]["tank"]["hp"], 7700 - 600)
        self.assertEqual(result["actors"]["air"]["hp"], 120)
        blasts = [
            event
            for event in result["trace"]
            if event.get("event") == "death_effect_impact"
        ]
        self.assertEqual(len(blasts), 1)
        self.assertAlmostEqual(blasts[0]["time_seconds"], 0.7)

    def test_invalid_cone_band_layer_and_dead_primary_choices_are_rejected(self):
        actors, _ = cone_combat()
        pattern = actors["scatter"]["attack_model"]
        cases = [deepcopy(pattern) for _ in range(3)]
        cases[0]["directional_splash"]["distance_bands"][1]["start"] = 2
        cases[1]["splash_layer_policy"] = "unknown"
        cases[2]["projectile"][
            "inactive_primary_policy"
        ] = "resolve_at_fixed_launch_position"
        for candidate in cases:
            with self.assertRaises(InputError):
                validate_pattern(candidate)

    def test_legacy_spatial_rules_cannot_silently_enable_new_projectile_semantics(self):
        actors, _ = cone_combat()
        inputs = [
            {key: value for key, value in actor.items() if not key.startswith("_")}
            for actor in actors.values()
        ]
        scene = pattern_scene(inputs, width=20, height=12)
        scene["actors"][0]["attack_model"] = actors["scatter"]["attack_model"]
        with self.assertRaisesRegex(InputError, "v8 ruleset"):
            simulate_spatial(scene)
