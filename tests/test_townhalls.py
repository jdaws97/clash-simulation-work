"""Town Hall lifecycle and persistent hazard feedback, without game certification."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.adapters import (
    TOWN_HALL_SCOPE,
    compile_entity_scene,
    simulate_entity_scene,
)
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.spatial import simulate_spatial
from clashlab.townhalls import RULESET, TOWN_HALL_RULES

from test_adapters import entity_instance, projectile, sector
from test_deaths import damage
from test_healing import support_scene
from test_spatial import synthetic_structure, synthetic_unit
from test_walls import breach_profile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "explicit-synthetic-Town-Hall-lifecycle-not-current-client-validation"


def lifecycle(initial_state="dormant", threshold=0.51):
    return {
        "source": SOURCE,
        "weapon_level": 1,
        "activation": {
            "source": SOURCE,
            "initial_state": initial_state,
            "destruction_threshold_fraction": threshold,
            "activation_delay_seconds": 0,
        },
        "death": {
            "source": SOURCE,
            "blast_delay_seconds": 1,
            "blast_damage_multiplier": 1,
            "blast_radius_multiplier": 1,
            "poison_delay_seconds": 1,
            "poison_radius_tiles": 4.5,
            "poison_max_dps_multiplier": 1,
            "poison_duration_multiplier": 1,
            "pulse_interval_seconds": 0.5,
            "first_pulse_offset_seconds": 0,
            "growth_by_field_age": [{"after_seconds": 0, "dps_multiplier": 1}],
            "exit_linger_seconds": 0,
            "protection_policy": "damage_immunity_does_not_block_status",
            "excluded_classes": ["siege"],
        },
    }


def hall(initial_state="dormant", level=16, **changes):
    return entity_instance(
        "hall",
        "town-hall",
        level,
        "defense",
        mode="gigaInferno",
        statistics_mode="weapon",
        attack_parameters={
            "projectile": projectile(),
            "allocation": "distinct_targets_only",
        },
        town_hall_parameters=lifecycle(initial_state),
        **changes,
    )


def town_hall_sector(catalog, entities, effects=None, **changes):
    scene = sector(catalog, entities)
    scene.update(
        scope=TOWN_HALL_SCOPE,
        model_rules=deepcopy(TOWN_HALL_RULES),
        persistent_hazards=[],
        healing_spells=[],
        healing_stacking={"source": SOURCE, "groups": {}},
        effects=[] if effects is None else effects,
        target_scoring={
            "selection": "legacy_route_or_footprint_distance",
            "source": SOURCE,
        },
    )
    scene.update(changes)
    return scene


def hazard(**changes):
    field = {
        "id": "poison",
        "source": SOURCE,
        "start_seconds": 0,
        "duration_seconds": 2,
        "pulse_interval_seconds": 0.5,
        "first_pulse_offset_seconds": 0,
        "maximum_dps": 10,
        "growth_by_field_age": [{"after_seconds": 0, "dps_multiplier": 1}],
        "area": {
            "x": 0.5,
            "y": 3.5,
            "radius": 20,
            "target_team": "attack",
            "target_kinds": ["unit"],
            "target_layers": ["ground", "air"],
        },
        "movement_multiplier": 0.5,
        "attack_rate_multiplier": 0.5,
        "exit_linger_seconds": 0,
        "protection_policy": "damage_immunity_does_not_block_status",
        "excluded_classes": ["siege"],
    }
    field.update(changes)
    return field


def hazard_scene(fields=None, actors=None, effects=None, **changes):
    if actors is None:
        actors = [synthetic_unit(damage=0), synthetic_structure(hitpoints=10000)]
    scene = support_scene(actors, effects, duration_seconds=2)
    scene.update(ruleset=RULESET, model_rules=deepcopy(TOWN_HALL_RULES))
    scene["persistent_hazards"] = [hazard()] if fields is None else fields
    scene["target_scoring"] = {
        "selection": "legacy_route_or_footprint_distance",
        "source": SOURCE,
    }
    for actor in scene["actors"]:
        if actor["kind"] == "unit":
            actor.setdefault("hazard_class", "troop")
    scene.update(changes)
    return scene


def attack_times(result, source="attacker"):
    return [
        event["time_seconds"]
        for event in result["trace"]
        if event.get("event") == "projectile_launch" and event["source"] == source
    ]


class TownHallAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_selected_weapon_and_death_statistics_are_separate(self):
        scene = town_hall_sector(
            self.catalog, [hall(), entity_instance("minion", "minion", 12, "attack")]
        )
        actor = compile_entity_scene(scene, self.catalog)["scene"]["actors"][0]
        self.assertEqual(actor["hitpoints"], 10000)
        self.assertEqual(actor["damage"], 38.4)
        self.assertEqual(actor["range"], 10)
        self.assertEqual(actor["attack_model"]["projectiles_per_volley"], 4)
        self.assertEqual(actor["death_model"]["effects"][0]["amount"], 1100)
        self.assertEqual(actor["town_hall_model"]["death_poison"]["maximum_dps"], 180)
        self.assertEqual(
            actor["town_hall_model"]["death_poison"]["duration_seconds"], 12
        )

    def test_dormant_weapon_does_not_fire_or_claim_a_defense_target_class(self):
        unit = entity_instance(
            "minion", "minion", 12, "attack", first_attack_seconds=100
        )
        result = simulate_entity_scene(
            town_hall_sector(self.catalog, [hall(), unit]), self.catalog
        )["combat"]
        self.assertEqual(result["actors"]["hall"]["kind"], "building")
        self.assertEqual(attack_times(result, "hall"), [])

    def test_actual_damage_activates_even_if_same_boundary_healing_restores_hp(self):
        unit = entity_instance(
            "minion", "minion", 12, "attack", first_attack_seconds=100
        )
        effects = [
            damage("hall", amount=10),
            {
                "id": "repair",
                "kind": "heal",
                "targets": ["hall"],
                "time_seconds": 0,
                "amount": 10,
            },
        ]
        result = simulate_entity_scene(
            town_hall_sector(self.catalog, [hall(), unit], effects), self.catalog
        )["combat"]
        self.assertEqual(result["actors"]["hall"]["hp"], 10000)
        self.assertEqual(
            result["town_halls_and_hazards"]["states"]["hall"]["reason"],
            "actual_damage_received",
        )
        self.assertEqual(len(attack_times(result, "hall")), 1)

    def test_declared_counted_destruction_fraction_activates_without_hall_damage(self):
        storage = entity_instance(
            "storage",
            "gold-storage",
            17,
            "defense",
            mode="passive",
            statistics_mode="none",
            attack_parameters={},
            inactive_attack_interval_seconds=1,
            x=2,
            y=8,
        )
        town = hall()
        town["town_hall_parameters"]["activation"][
            "destruction_threshold_fraction"
        ] = 0.5
        unit = entity_instance(
            "minion", "minion", 12, "attack", first_attack_seconds=100
        )
        result = simulate_entity_scene(
            town_hall_sector(self.catalog, [town, unit, storage], [damage("storage")]),
            self.catalog,
        )["combat"]
        self.assertEqual(
            result["town_halls_and_hazards"]["states"]["hall"]["reason"],
            "declared_destruction_threshold",
        )
        self.assertEqual(result["actors"]["hall"]["hp"], 10000)

    def test_four_beams_do_not_concentrate_on_one_available_target(self):
        unit = entity_instance(
            "minion", "minion", 12, "attack", first_attack_seconds=100
        )
        result = simulate_entity_scene(
            town_hall_sector(self.catalog, [hall("active"), unit]), self.catalog
        )["combat"]
        impacts = [
            event
            for event in result["trace"]
            if event.get("event") == "projectile_impact" and event["source"] == "hall"
        ]
        self.assertEqual(len(impacts), 1)
        self.assertEqual(impacts[0]["damage"], 38.4)

    def test_delayed_blast_and_poison_survive_hall_loss_and_release_once(self):
        tank = entity_instance(
            "tank",
            "pekka",
            11,
            "attack",
            first_attack_seconds=100,
            wall_parameters={"kind": "avoid", "source": SOURCE},
        )
        scene = town_hall_sector(
            self.catalog,
            [hall(), tank],
            [damage("hall", amount=20000)],
            duration_seconds=1.1,
        )
        result = simulate_entity_scene(scene, self.catalog)["combat"]
        self.assertEqual(result["actors"]["tank"]["hp"], 7700 - 1100 - 90)
        self.assertEqual(
            result["town_halls_and_hazards"]["death_poison_emitted"], ["hall"]
        )
        self.assertEqual(result["death_effects"]["emitted_instances"], ["hall"])

    def test_town_hall_requires_own_scope_and_cannot_be_passive(self):
        unit = entity_instance("minion", "minion", 12, "attack")
        with self.assertRaisesRegex(InputError, "explicit lifecycle"):
            compile_entity_scene(sector(self.catalog, [hall(), unit]), self.catalog)
        town = hall()
        town.update(mode="passive", statistics_mode="none", attack_parameters={})
        with self.assertRaisesRegex(InputError, "defensive weapon mode"):
            compile_entity_scene(
                town_hall_sector(self.catalog, [town, unit]), self.catalog
            )

    def test_higher_town_halls_and_missing_parameters_do_not_inherit_giga_model(self):
        unit = entity_instance("minion", "minion", 12, "attack")
        for level in (17, 18):
            with (
                self.subTest(level=level),
                self.assertRaisesRegex(InputError, "Missing town-hall mechanics"),
            ):
                compile_entity_scene(
                    town_hall_sector(
                        self.catalog, [hall(level=level, town_hall=level), unit]
                    ),
                    self.catalog,
                )
        town = hall()
        del town["town_hall_parameters"]["death"]["exit_linger_seconds"]
        with self.assertRaisesRegex(InputError, "explicit blast"):
            compile_entity_scene(
                town_hall_sector(self.catalog, [town, unit]), self.catalog
            )


class PersistentHazardTests(unittest.TestCase):
    def test_arrival_policy_prefers_an_immediately_attackable_target(self):
        for wall_profile in (None, breach_profile()):
            actors = [
                synthetic_unit(range=6, damage=1),
                synthetic_structure("near", x=5, hitpoints=10000),
                synthetic_structure("far", x=8, hitpoints=10000),
            ]
            scene = hazard_scene([], actors=actors, duration_seconds=0.01)
            scene["target_scoring"][
                "selection"
            ] = "arrival_time_then_footprint_distance"
            if wall_profile is not None:
                scene["actors"][0]["wall_behavior"] = wall_profile
            result = simulate_spatial(scene)
            self.assertEqual(result["actors"]["near"]["hp"], 9999)
            self.assertEqual(result["actors"]["far"]["hp"], 10000)

    def test_attack_slow_can_change_breach_versus_detour_choice(self):
        actors = [
            synthetic_unit(x=3.5, damage=1, wall_behavior=breach_profile()),
            synthetic_structure(hitpoints=10000),
            synthetic_structure("wall", kind="wall", x=4, counts_for_destruction=False),
        ]
        normal_scene = hazard_scene([], actors=deepcopy(actors), duration_seconds=0.01)
        slowed_scene = hazard_scene(
            [hazard(maximum_dps=0, movement_multiplier=1, attack_rate_multiplier=0.1)],
            actors=deepcopy(actors),
            duration_seconds=0.01,
        )
        for scene in (normal_scene, slowed_scene):
            scene["actors"][0]["wall_behavior"] = breach_profile()
        normal = simulate_spatial(normal_scene)
        slowed = simulate_spatial(slowed_scene)
        self.assertEqual(normal["actors"]["wall"]["hp"], 0)
        self.assertEqual(slowed["actors"]["wall"]["hp"], 100)

    def test_duration_pulses_total_the_declared_dps_without_an_endpoint_extra_hit(self):
        result = simulate_spatial(hazard_scene())
        self.assertEqual(result["actors"]["attacker"]["hp"], 80)
        pulses = [
            event for event in result["trace"] if event.get("event") == "hazard_pulse"
        ]
        self.assertEqual(len(pulses), 4)
        self.assertAlmostEqual(pulses[-1]["time_seconds"], 1.5)

    def test_growth_is_an_explicit_field_age_curve(self):
        field = hazard(
            growth_by_field_age=[
                {"after_seconds": 0, "dps_multiplier": 0.5},
                {"after_seconds": 1, "dps_multiplier": 1},
            ]
        )
        result = simulate_spatial(hazard_scene([field]))
        self.assertEqual(result["actors"]["attacker"]["hp"], 85)

    def test_immunity_blocks_damage_but_status_policy_can_keep_slow(self):
        protection = {
            "id": "protect",
            "kind": "invulnerability",
            "time_seconds": 0,
            "targets": ["attacker"],
            "duration_seconds": 1,
        }
        result = simulate_spatial(hazard_scene(effects=[protection]))
        self.assertEqual(result["actors"]["attacker"]["hp"], 90)
        self.assertEqual(
            result["frames"][0]["actors"]["attacker"]["hazard_attack_rate"], 0.5
        )
        field = hazard(protection_policy="damage_immunity_also_blocks_status")
        result = simulate_spatial(hazard_scene([field], effects=[protection]))
        self.assertEqual(
            result["frames"][0]["actors"]["attacker"]["hazard_attack_rate"], 1
        )

    def test_declared_siege_class_is_exempt_from_poison_damage_and_status(self):
        actors = [synthetic_unit(damage=0, hazard_class="siege"), synthetic_structure()]
        result = simulate_spatial(hazard_scene(actors=actors))
        self.assertEqual(result["actors"]["attacker"]["hp"], 100)
        self.assertEqual(
            result["frames"][0]["actors"]["attacker"]["hazard_attack_rate"], 1
        )

    def test_live_damage_area_accepts_a_later_controlled_deployment(self):
        actors = [
            synthetic_unit(damage=0, spawn_seconds="controlled"),
            synthetic_structure(),
        ]
        deploy = {
            "id": "enter",
            "kind": "deploy",
            "time_seconds": 1,
            "targets": ["attacker"],
            "positions": {"attacker": {"x": 0.5, "y": 3.5}},
        }
        result = simulate_spatial(hazard_scene(actors=actors, effects=[deploy]))
        self.assertEqual(result["actors"]["attacker"]["hp"], 90)

    def test_slow_changes_movement_then_recovers_when_the_field_expires(self):
        actors = [synthetic_unit(damage=1), synthetic_structure(hitpoints=10000)]
        result = simulate_spatial(
            hazard_scene([hazard(duration_seconds=1, maximum_dps=0)], actors=actors)
        )
        self.assertAlmostEqual(result["actors"]["attacker"]["x"], 3.5)

    def test_remaining_weapon_cooldown_is_rescaled_at_entry_and_expiry(self):
        actors = [
            synthetic_unit(damage=1, range=10),
            synthetic_structure(hitpoints=10000),
        ]
        field = hazard(start_seconds=0.5, duration_seconds=1, maximum_dps=0)
        result = simulate_spatial(
            hazard_scene([field], actors=actors, duration_seconds=3)
        )
        self.assertEqual(attack_times(result), [0, 1.5, 2.5])

    def test_freeze_and_slow_preserve_only_unfrozen_cooldown_progress(self):
        actors = [
            synthetic_unit(damage=1, range=10, attack_interval_seconds=2),
            synthetic_structure(hitpoints=10000),
        ]
        field = hazard(start_seconds=0.5, duration_seconds=1, maximum_dps=0)
        freeze = {
            "id": "freeze",
            "kind": "freeze",
            "time_seconds": 0.75,
            "targets": ["attacker"],
            "duration_seconds": 1,
        }
        result = simulate_spatial(
            hazard_scene([field], actors=actors, effects=[freeze], duration_seconds=3.2)
        )
        self.assertEqual(attack_times(result), [0, 3.125])

    def test_linger_starts_at_exact_field_expiry_not_previous_solver_frame(self):
        actors = [
            synthetic_unit(damage=1, range=10),
            synthetic_structure(hitpoints=10000),
        ]
        field = hazard(duration_seconds=1, maximum_dps=0, exit_linger_seconds=1)
        result = simulate_spatial(
            hazard_scene([field], actors=actors, duration_seconds=3)
        )
        changes = [
            event
            for event in result["trace"]
            if event.get("event") == "hazard_status_change"
        ]
        self.assertEqual(changes[-1]["time_seconds"], 2)

    def test_overlap_adds_damage_but_uses_strongest_status(self):
        first = hazard()
        second = hazard(
            id="second",
            maximum_dps=20,
            movement_multiplier=0.8,
            attack_rate_multiplier=0.8,
        )
        result = simulate_spatial(hazard_scene([first, second]))
        self.assertEqual(result["actors"]["attacker"]["hp"], 40)
        self.assertEqual(
            result["frames"][0]["actors"]["attacker"]["hazard_attack_rate"], 0.5
        )

    def test_missing_class_growth_or_wrong_ruleset_is_rejected(self):
        scene = hazard_scene()
        del scene["actors"][0]["hazard_class"]
        with self.assertRaisesRegex(InputError, "explicit class"):
            simulate_spatial(scene)
        field = hazard(growth_by_field_age=[])
        with self.assertRaisesRegex(InputError, "explicit field-age"):
            simulate_spatial(hazard_scene([field]))
        scene = hazard_scene()
        from clashlab.deaths import DEATH_RULES, RULESET as DEATH_RULESET

        scene.update(ruleset=DEATH_RULESET, model_rules=deepcopy(DEATH_RULES))
        with self.assertRaisesRegex(InputError, "own explicit ruleset"):
            simulate_spatial(scene)


if __name__ == "__main__":
    unittest.main()
