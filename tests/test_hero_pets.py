"""Source-bound pets with explicit clocks, ownership and individual lifecycles."""

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat, expand_area_effects
from clashlab.common import InputError
from clashlab.hazards import PulsedHazards
from clashlab.hero_pets import (
    OWNER_DEATH_POLICIES,
    SUPPORTED_PETS,
    TARGET_RETENTION,
    PetCombat,
    compile_pet,
    compile_pets,
    validate_pet_deployment,
)
from clashlab.rates import attack_rate
from clashlab.spatial import (
    EPSILON,
    _active,
    _apply_effects,
    _apply_health,
    _blocked,
    _eligible,
    _load_actors,
    _move,
    _select_target,
    center,
    target_distance,
)
from clashlab.walls import WallRouting

from test_spatial import synthetic_scene, synthetic_structure, synthetic_unit
from test_townhalls import hazard


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "explicit-paired-pet-development-contract-not-replay-calibration"


def projectile():
    return {
        "timing": "instant",
        "delay_seconds": 0,
        "destination": "locked_actor_center_at_impact",
        "hit_radius": 0,
    }


def pet_parameters(entity, **changes):
    behaviors = {
        "unicorn": {
            "healing_basis": "catalog_healingPerPulse_per_catalog_attackSpeed_scaled_by_source_pet_buff",
            "stacking_policy": "independent_additive_without_healer_diminishing_returns",
            "protection_policy": "healing_ignores_damage_invulnerability",
            "overheal_policy": "cap_at_maximum_without_resurrection",
        },
        "spirit-fox": {
            "initial_cloak_delay_seconds": 0.5,
            "visible_interval_seconds": 2,
            "duration_basis": "catalog_invisibilityDuration",
            "recipient_policy": "pet_and_active_owner_regardless_distance",
            "cloak_policy": "acquisition_only_existing_projectiles_and_splash_still_hit",
            "freeze_clock_policy": "continue_periodic_clock_while_frozen",
        },
        "phoenix": {
            "duration_basis": "catalog_reviveDuration",
            "revival_health_policy": "one_hp_sentinel_unhealable_during_temporary_life",
            "splash_radius_tiles": 1.25,
            "shield_recipients": "hero_and_hatched_phoenix",
            "shield_status_policy": "freeze_and_cloak_remain_independent",
            "hatch_position_policy": "current_owner_center",
            "expiry_policy": "owner_defeated_even_if_healed_or_other_protection_remains",
            "ability_policy": "preserve_used_state_without_reactivation",
            "egg_policy": "inactive_unhittable_unhealable_nonattacking_owner_follower",
        },
        "diggy": {
            "burrow_windup_seconds": 0.2,
            "emerge_delay_seconds": 0.1,
            "stun_policy": "first_successful_hit_each_emergence",
            "stun_duration_basis": "catalog_stunDuration",
            "stun_target_kinds": ["defense", "building"],
            "stun_protection_policy": "damage_immunity_does_not_block_stun",
            "underground_status_policy": "inactive_untargetable_undamageable_no_new_status",
            "underground_path_policy": "straight_segment_through_obstacles_to_clear_surface_point",
            "freeze_policy": "surface_freeze_delays_dive_underground_movement_continues",
            "target_motion_policy": "fixed_destination_revalidate_after_arrival",
        },
        "electro-owl": {
            "chain_damage_basis": "catalog_negative_percent_decay_per_jump",
            "jump_range_tiles": 2,
            "jump_delay_seconds": 0.1,
            "jump_metric": "footprint_distance",
            "tie_break": "distance_then_instance_id",
            "allow_protected_links": True,
        },
        "lassi": {},
    }
    parameters = {
        "source": SOURCE,
        "spawn_offset": {"dx": 0, "dy": 0},
        "first_attack_delay_seconds": 0.2,
        "follow_distance_tiles": 1,
        "target_retention": TARGET_RETENTION[entity],
        "owner_death_policy": OWNER_DEATH_POLICIES[entity],
        "pet_death_policy": "stop_future_actions_existing_effects_persist",
        "ground_wall_policy": (
            "not_applicable_air"
            if entity in {"electro-owl", "phoenix"}
            else "jump_enemy_walls"
        ),
        "incoming_status_policy": "independent_from_owner_ordinary_unit_effects",
        "projectile": None if entity == "unicorn" else projectile(),
        "behavior": behaviors[entity],
    }
    parameters.update(changes)
    return parameters


def pet_instance(entity="unicorn", **changes):
    instance = {
        "id": "pet",
        "entity": entity,
        "level": 15 if entity in {"lassi", "electro-owl"} else 10,
        "town_hall": 16,
        "hero_id": "hero",
        "parameters": pet_parameters(entity),
    }
    instance.update(changes)
    return instance


def owner(actor_id="hero", **changes):
    actor = synthetic_unit(
        actor_id,
        x=2.5,
        y=3.5,
        damage=0,
        hitpoints=1000,
        target_priorities=["defense", "building"],
        target_layers=["ground", "air"],
        healing_class="hero",
        hazard_class="hero",
        buff_class="hero",
        hero_model={"source": SOURCE},
        wall_behavior={"kind": "avoid", "source": SOURCE},
        entity_adapter={"entity": "archer-queen", "town_hall": 16},
        attack_model={"kind": "none", "source": SOURCE},
        minimum_range=0,
    )
    actor.update(changes)
    return actor


def target(actor_id="tower", **changes):
    actor = synthetic_structure(
        actor_id,
        x=8,
        y=3,
        hitpoints=10000,
        attack_model={"kind": "none", "source": SOURCE},
        minimum_range=0,
    )
    actor.update(changes)
    return actor


def advance_component(pets, actors, end, maximum_step=0.7, time=0):
    """Exercise routing and pet boundaries while leaving enemy weapon tests separate."""
    trace = []
    while True:
        pets.prepare(actors, time, trace)
        healing = pets.resolve_healing(actors, time, trace)
        for actor_id in list(healing):
            if not pets.healing_allowed(actors[actor_id], time):
                healing[actor_id] = 0
        _apply_health(actors, defaultdict(float), healing, time)
        if time >= end - EPSILON:
            return trace
        boundary = pets.next_boundary(time)
        next_time = min(end, time + maximum_step)
        if boundary is not None:
            next_time = min(next_time, boundary)
        routes = {}
        blocked = _blocked(actors, time)
        for pet_id in pets.models:
            actor = actors[pet_id]
            if _active(actor, time) and actor["frozen_until"] <= time + EPSILON:
                _, route = pets.select_target(
                    actor, actors, time, blocked, pets.width, pets.height
                )
                if route is not None:
                    routes[pet_id] = route
                    crossing = pets.first_crossing_delay(
                        actor, route, time, next_time - time, actor["speed"]
                    )
                    if crossing is not None:
                        next_time = min(next_time, time + crossing)
        for pet_id, route in routes.items():
            position, remaining = _move(actors[pet_id], route, next_time - time)
            actors[pet_id]["x"], actors[pet_id]["y"] = position
            if actors[pet_id]["movement"] == "ground":
                actors[pet_id]["_remaining_path"] = remaining
        pets.advance(actors, time, next_time - time, trace)
        time = next_time


class HeroPetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def runtime(self, entity="unicorn", instance=None, hero=None, others=None):
        hero = owner() if hero is None else hero
        others = [target()] if others is None else others
        definitions = {item["id"]: item for item in [hero, *others]}
        pet = compile_pet(
            instance or pet_instance(entity), self.catalog, 8, definitions
        )
        actors = _load_actors(
            synthetic_scene([hero, *others, pet], width=24, height=16), 24, 16
        )
        walls = WallRouting(actors)
        return actors, PetCombat(actors, 24, 16, walls.select_target), []

    def test_catalog_quantities_and_pet_roles_are_not_hero_statistics(self):
        expected = {
            "unicorn": (1950, 0, 1, 2, 2.5),
            "diggy": (5000, 165, 1.1, 4, 0.8),
            "phoenix": (4200, 250, 1, 2, 2.5),
            "spirit-fox": (2800, 288, 1.6, 3, 2.5),
            "lassi": (4500, 360, 0.9, 4, 0.6),
            "electro-owl": (3000, 238, 1.4, 2.5, 6),
        }
        for entity, statistics in expected.items():
            with self.subTest(entity=entity):
                actors, pets, _ = self.runtime(entity)
                actor = actors["pet"]
                self.assertEqual(
                    tuple(
                        actor[field]
                        for field in (
                            "hp",
                            "damage",
                            "attack_interval_seconds",
                            "speed",
                            "range",
                        )
                    ),
                    statistics,
                )
                self.assertEqual(actor["spawn_seconds"], "controlled")
                self.assertEqual(
                    {
                        actor[field]
                        for field in (
                            "healing_class",
                            "hazard_class",
                            "buff_class",
                            "spring_class",
                        )
                    },
                    {"pet"},
                )
                self.assertFalse(actor["counts_for_destruction"])
                self.assertIn(entity, pets.models["pet"]["statistics_source"])
                self.assertIn("assignment", pets.models["pet"]["publisher_sources"])
        self.assertEqual(SUPPORTED_PETS, set(expected))

    def test_owl_range_disagreement_is_retained_and_frosty_fails_with_source_gap(self):
        actors, pets, _ = self.runtime("electro-owl")
        self.assertEqual(actors["pet"]["range"], 6)
        conflict = pets.models["pet"]["statistic_disagreements"][0]
        self.assertEqual(conflict["extraction_tiles"], 5.5)
        instance = pet_instance()
        instance["entity"] = "frosty"
        with self.assertRaisesRegex(InputError, "Frostmite"):
            compile_pet(instance, self.catalog, 8, {"hero": owner()})

    def test_levels_ownership_duplicates_and_missing_hypotheses_fail_closed(self):
        for field, value in (("level", 15), ("town_hall", 13), ("hero_id", "missing")):
            instance = pet_instance()
            instance[field] = value
            with self.subTest(field=field), self.assertRaises(InputError):
                compile_pet(instance, self.catalog, 8, {"hero": owner()})
        for entity in SUPPORTED_PETS:
            instance = pet_instance(entity)
            del instance["parameters"]["owner_death_policy"]
            with self.subTest(entity=entity), self.assertRaises(InputError):
                compile_pet(instance, self.catalog, 8, {"hero": owner()})
        heroes = {"hero": owner(), "second": owner("second")}
        for assignments in (
            [pet_instance(), pet_instance("diggy", id="second-pet")],
            [pet_instance(), pet_instance(id="second-pet", hero_id="second")],
            [pet_instance(id="hero")],
        ):
            with self.assertRaises(InputError):
                compile_pets(assignments, heroes, self.catalog, 8)

    def test_pet_follows_owner_deployment_and_cannot_be_deployed_independently(self):
        actors, pets, trace = self.runtime(hero=owner(spawn_seconds="controlled"))
        pets.prepare(actors, 0, trace)
        self.assertFalse(_active(actors["pet"], 0))
        deploy = {
            "id": "deploy",
            "kind": "deploy",
            "time_seconds": 1,
            "targets": ["pet"],
            "positions": {"pet": {"x": 4, "y": 4}},
        }
        with self.assertRaisesRegex(InputError, "independently"):
            validate_pet_deployment(deploy, actors)
        actors["hero"].update(spawn_seconds=1, x=4.5, y=5.5)
        pets.prepare(actors, 1, trace)
        self.assertEqual(center(actors["pet"]), (4.5, 5.5))
        self.assertEqual(actors["pet"]["spawn_seconds"], 1)
        self.assertAlmostEqual(actors["pet"]["next_attack"], 1.2)

    def test_unicorn_heals_only_owner_uses_emitter_buff_and_caps_without_resurrection(
        self,
    ):
        other = owner("other", x=2.5)
        actors, pets, trace = self.runtime(others=[other])
        actors["hero"]["hp"] = 900
        actors["other"]["hp"] = 100
        pets.prepare(actors, 0, trace)
        actors["pet"]["_buff_healing_multiplier"] = 2
        healing = pets.resolve_healing(actors, 0.2, trace)
        self.assertEqual(dict(healing), {"hero": 140})
        _apply_health(actors, defaultdict(float), healing, 0.2)
        self.assertEqual(actors["hero"]["hp"], 1000)
        self.assertEqual(actors["other"]["hp"], 100)
        actors["hero"].update(hp=0, death_time=0.3)
        healing = pets.resolve_healing(actors, 1.2, trace)
        self.assertEqual(dict(healing), {"other": 140})
        self.assertEqual(actors["hero"]["hp"], 0)

    def test_unicorn_moves_into_range_and_has_a_deterministic_pulse_clock(self):
        observations = []
        for step in (0.01, 0.7):
            actors, pets, trace = self.runtime(others=[])
            pets.prepare(actors, 0, trace)
            actors["hero"]["x"] = 8.5
            actors["hero"]["hp"] = 100
            self.assertEqual(dict(pets.resolve_healing(actors, 0.2, trace)), {})
            trace = advance_component(pets, actors, 3, step)
            observations.append(
                (
                    round(actors["pet"]["x"], 7),
                    actors["hero"]["hp"],
                    [
                        round(event["time_seconds"], 6)
                        for event in trace
                        if event["event"] == "pet_healing_pulse"
                    ],
                )
            )
        self.assertEqual(observations[0], observations[1])

    def test_unicorn_fallback_prefers_living_hero_then_troop(self):
        troop = synthetic_unit(
            "troop",
            x=2.5,
            healing_class="troop",
            wall_behavior={"kind": "avoid", "source": SOURCE},
        )
        actors, pets, trace = self.runtime(others=[owner("other", x=10.5), troop])
        pets.prepare(actors, 0, trace)
        actors["hero"].update(hp=0, death_time=0)
        pets.select_target(actors["pet"], actors, 0, _blocked(actors, 0), 24, 16)
        self.assertEqual(actors["pet"]["healing_target"], "other")
        actors["other"].update(hp=0, death_time=0)
        pets.select_target(actors["pet"], actors, 0, _blocked(actors, 0), 24, 16)
        self.assertEqual(actors["pet"]["healing_target"], "troop")

    def test_unicorn_freeze_is_independent_of_owner_and_preserves_attack_work(self):
        actors, pets, trace = self.runtime()
        pets.prepare(actors, 0, trace)
        _apply_effects(
            [
                {
                    "id": "freeze",
                    "kind": "freeze",
                    "targets": ["pet"],
                    "duration_seconds": 1,
                }
            ],
            actors,
            0.1,
            trace,
        )
        self.assertEqual(actors["hero"]["frozen_until"], 0)
        self.assertAlmostEqual(actors["pet"]["next_attack"], 1.2)
        self.assertEqual(dict(pets.resolve_healing(actors, 0.5, trace)), {})
        self.assertEqual(dict(pets.resolve_healing(actors, 1.2, trace)), {"hero": 70})

    def test_fox_cloak_changes_acquisition_but_not_existing_projectile_damage(self):
        shot = {
            "kind": "single",
            "source": SOURCE,
            "target_kinds": ["unit"],
            "target_layers": ["ground"],
            "maximum_hp_fraction": 0,
            "projectile": {
                "timing": "launch_distance_delay",
                "speed_tiles_per_second": 5,
                "destination": "locked_actor_center_at_impact",
                "hit_radius": 0,
            },
        }
        tower = target(
            damage=100, range=20, attack_model=shot, target_layers=["ground"]
        )
        actors, pets, trace = self.runtime("spirit-fox", others=[tower])
        pets.prepare(actors, 0, trace)
        combat = PatternCombat(actors)
        combat.launch(actors["tower"], actors["hero"], actors, 0, trace)
        pets.prepare(actors, 0.5, trace)
        self.assertFalse(_eligible(actors["tower"], actors["hero"], 0.5))
        self.assertEqual(actors["hero"]["immune_until"], 0)
        impacts = combat.resolve(actors, 2, trace)
        self.assertEqual(impacts["hero"], 100)

    def test_fox_periodic_clock_continues_while_frozen_and_becomes_self_only(self):
        actors, pets, trace = self.runtime("spirit-fox")
        pets.prepare(actors, 0, trace)
        _apply_effects(
            [
                {
                    "kind": "freeze",
                    "id": "freeze",
                    "targets": ["pet"],
                    "duration_seconds": 8,
                }
            ],
            actors,
            0,
            trace,
        )
        pets.prepare(actors, 0.5, trace)
        self.assertEqual(actors["hero"]["_untargetable_until"], 4.5)
        self.assertEqual(pets.next_boundary(0.5), 4.5)
        actors["hero"].update(hp=0, death_time=1)
        pets.prepare(actors, 6.5, trace)
        cloak = [event for event in trace if event.get("event") == "pet_cloak"]
        self.assertEqual(cloak[-1]["targets"], ["pet"])
        self.assertEqual(actors["pet"]["_untargetable_until"], 10.5)
        self.assertEqual(actors["hero"]["_untargetable_until"], 4.5)

    def test_dead_fox_stops_new_cloaks_but_does_not_remove_existing_owner_cloak(self):
        actors, pets, trace = self.runtime("spirit-fox")
        pets.prepare(actors, 0, trace)
        pets.prepare(actors, 0.5, trace)
        actors["pet"].update(hp=0, death_time=1)
        pets.prepare(actors, 1, trace)
        self.assertEqual(actors["hero"]["_untargetable_until"], 4.5)
        pets.prepare(actors, 6.5, trace)
        self.assertEqual(pets.states["pet"]["cloak_count"], 1)

    def test_phoenix_egg_is_inactive_and_ignores_damage_freeze_and_healing(self):
        actors, pets, trace = self.runtime("phoenix")
        pets.prepare(actors, 0, trace)
        self.assertFalse(_active(actors["pet"], 0))
        _apply_effects(
            [
                {"id": "damage", "kind": "damage", "targets": ["pet"], "amount": 10000},
                {
                    "id": "freeze",
                    "kind": "freeze",
                    "targets": ["pet"],
                    "duration_seconds": 2,
                },
            ],
            actors,
            0,
            trace,
        )
        self.assertEqual(actors["pet"]["hp"], 4200)
        self.assertEqual(actors["pet"]["frozen_until"], 0)
        actors["hero"]["x"] = 6.5
        pets.prepare(actors, 0.1, trace)
        self.assertEqual(center(actors["pet"]), center(actors["hero"]))

    def test_phoenix_intercepts_one_defeat_and_forces_expiry_despite_other_shield(self):
        actors, pets, trace = self.runtime("phoenix")
        pets.prepare(actors, 0, trace)
        hero = actors["hero"]
        hero.update(hp=0, death_time=1, ability_already_used=True)
        self.assertTrue(pets.intercept_lethal(hero, 1, trace))
        self.assertEqual(hero["hp"], 1)
        self.assertIsNone(hero["death_time"])
        self.assertFalse(pets.healing_allowed(hero, 2))
        self.assertTrue(hero["ability_already_used"])
        self.assertEqual(actors["pet"]["spawn_seconds"], 1)
        self.assertAlmostEqual(actors["pet"]["next_attack"], 1.2)
        self.assertEqual((hero["immune_until"], actors["pet"]["immune_until"]), (9, 9))
        hero["immune_until"] = 20
        pets.prepare(actors, 9, trace)
        self.assertEqual((hero["hp"], hero["death_time"]), (0, 9))
        self.assertFalse(pets.intercept_lethal(hero, 9, trace))
        self.assertTrue(_active(actors["pet"], 9))

    def test_phoenix_pet_death_does_not_cancel_owner_expiry_or_resurrect_pet(self):
        actors, pets, trace = self.runtime("phoenix")
        pets.prepare(actors, 0, trace)
        actors["hero"]["hp"] = 0
        pets.intercept_lethal(actors["hero"], 1, trace)
        actors["pet"].update(hp=0, death_time=2)
        pets.prepare(actors, 9, trace)
        self.assertEqual(actors["hero"]["hp"], 0)
        self.assertEqual(actors["pet"]["hp"], 0)
        self.assertEqual(pets.states["pet"]["phase"], "dead")

    def test_diggy_burrows_finitely_through_a_building_then_surfaces_outside_it(self):
        obstacle = target("obstacle", x=4, y=3)
        actors, pets, trace = self.runtime("diggy", others=[obstacle, target()])
        actors["hero"]["target"] = "tower"
        pets.prepare(actors, 0, trace)
        self.assertEqual(center(actors["pet"]), (2.5, 3.5))
        self.assertFalse(_active(actors["pet"], 0))
        pets.advance(actors, 0, 0.5, trace)
        self.assertAlmostEqual(actors["pet"]["x"], 4.5)
        self.assertFalse(_active(actors["pet"], 0.5))
        surface = pets.states["pet"]["burrow"]["surface_seconds"]
        self.assertAlmostEqual(surface, 1.275)
        pets.advance(actors, 0.5, surface - 0.5, trace)
        pets.prepare(actors, surface, trace)
        self.assertTrue(_active(actors["pet"], surface))
        self.assertAlmostEqual(actors["pet"]["x"], 7.2)
        self.assertAlmostEqual(actors["pet"]["next_attack"], surface + 0.2)

    def test_diggy_underground_rejects_poison_freeze_damage_and_acquisition(self):
        actors, pets, trace = self.runtime("diggy")
        pets.prepare(actors, 0, trace)
        self.assertFalse(_eligible(actors["tower"], actors["pet"], 0))
        _apply_effects(
            [
                {
                    "id": "freeze",
                    "kind": "freeze",
                    "targets": ["pet"],
                    "duration_seconds": 10,
                },
                {"id": "damage", "kind": "damage", "targets": ["pet"], "amount": 10000},
            ],
            actors,
            0,
            trace,
        )
        field = hazard()
        field["area"].update(x=2.5, y=3.5)
        field["area"]["target_team"] = "attack"
        field["area"]["radius"] = 20
        field["excluded_classes"] = []
        hazards = PulsedHazards(actors, [field])
        hazards.prepare_status(actors, 0, trace)
        self.assertNotIn("pet", hazards.resolve(actors, 0, trace))
        self.assertEqual(actors["pet"]["hp"], 5000)
        self.assertEqual(actors["pet"]["frozen_until"], 0)
        self.assertEqual(actors["pet"].get("_hazard_movement_multiplier"), 1)

    def test_diggy_stuns_only_first_successful_hit_after_emergence(self):
        actors, pets, trace = self.runtime("diggy")
        actors["hero"]["target"] = "tower"
        pets.prepare(actors, 0, trace)
        surface = pets.states["pet"]["burrow"]["surface_seconds"]
        pets.advance(actors, 0, surface, trace)
        pets.prepare(actors, surface, trace)
        tower = actors["tower"]
        tower["next_attack"] = surface + 1
        packet = {"source": "pet"}
        pets.impact(packet, tower, actors, surface + 0.2, trace)
        self.assertAlmostEqual(tower["frozen_until"], surface + 3.2)
        self.assertAlmostEqual(tower["next_attack"], surface + 4)
        pets.impact(packet, tower, actors, surface + 1.3, trace)
        self.assertAlmostEqual(tower["frozen_until"], surface + 3.2)

    def test_diggy_zero_distance_zero_delay_emerges_during_same_prepare(self):
        instance = pet_instance("diggy")
        instance["parameters"]["behavior"]["emerge_delay_seconds"] = 0
        actors, pets, trace = self.runtime(
            "diggy", instance=instance, hero=owner(x=2.2), others=[target(x=3)]
        )
        pets.prepare(actors, 0, trace)
        self.assertTrue(_active(actors["pet"], 0))
        self.assertEqual(pets.states["pet"]["phase"], "active")
        self.assertIsNone(pets.states["pet"]["burrow"])
        self.assertEqual(actors["pet"]["next_attack"], 0.2)

    def test_diggy_follows_owner_underground_without_an_enemy(self):
        actors, pets, trace = self.runtime("diggy", others=[])
        pets.prepare(actors, 0, trace)
        actors["hero"]["x"] = 10.5
        pets.prepare(actors, 0, trace)
        self.assertFalse(pets.states["pet"]["burrow"]["will_surface"])
        pets.advance(actors, 0, 0.5, trace)
        self.assertAlmostEqual(actors["pet"]["x"], 4.5)
        self.assertFalse(_active(actors["pet"], 0.5))
        arrival = pets.states["pet"]["burrow"]["arrival_seconds"]
        pets.advance(actors, 0.5, arrival - 0.5, trace)
        pets.prepare(actors, arrival, trace)
        self.assertAlmostEqual(actors["pet"]["x"], 9.5)
        self.assertFalse(_active(actors["pet"], arrival))
        self.assertIsNone(pets.states["pet"]["burrow"])
        self.assertEqual(pets.states["pet"]["phase"], "underground")

    def test_diggy_revalidates_dead_target_after_emergence(self):
        actors, pets, trace = self.runtime(
            "diggy", others=[target(), target("second", x=11)]
        )
        actors["hero"]["target"] = "tower"
        pets.prepare(actors, 0, trace)
        surface = pets.states["pet"]["burrow"]["surface_seconds"]
        actors["tower"].update(hp=0, death_time=0.2)
        pets.advance(actors, 0, surface, trace)
        pets.prepare(actors, surface, trace)
        self.assertIsNotNone(pets.states["pet"]["dive_at"])
        pets.prepare(actors, surface + 0.2, trace)
        self.assertEqual(pets.states["pet"]["burrow"]["target"], "second")
        self.assertFalse(_active(actors["pet"], surface + 0.2))

    def test_diggy_surface_accepts_ordinary_poison_and_freeze(self):
        actors, pets, trace = self.runtime("diggy")
        pets.prepare(actors, 0, trace)
        surface = pets.states["pet"]["burrow"]["surface_seconds"]
        pets.advance(actors, 0, surface, trace)
        pets.prepare(actors, surface, trace)
        field = hazard()
        field["start_seconds"] = surface
        field["area"].update(x=7.2, y=3.5, radius=20, target_team="attack")
        field["excluded_classes"] = []
        hazards = PulsedHazards(actors, [field])
        hazards.prepare_status(actors, surface, trace)
        self.assertLess(actors["pet"]["_hazard_movement_multiplier"], 1)
        self.assertIn("pet", hazards.resolve(actors, surface, trace))
        _apply_effects(
            [
                {
                    "id": "freeze",
                    "kind": "freeze",
                    "targets": ["pet"],
                    "duration_seconds": 2,
                }
            ],
            actors,
            surface,
            trace,
        )
        self.assertAlmostEqual(actors["pet"]["frozen_until"], surface + 2)

    def test_forged_runtime_pet_quantities_layers_and_patterns_are_rejected(self):
        cases = [
            ("spirit-fox", "cloak_duration_seconds", 0),
            ("phoenix", "revival_duration_seconds", -1),
            ("unicorn", "stun_duration_seconds", 3),
        ]
        for entity, field, value in cases:
            with self.subTest(entity=entity, field=field):
                actors, _, _ = self.runtime(entity)
                actors["pet"]["pet_model"][field] = value
                with self.assertRaises(InputError):
                    PetCombat(actors, 24, 16, _select_target)
        for entity, field, value in (
            ("electro-owl", "layer", "ground"),
            ("unicorn", "damage", 100),
            ("diggy", "speed", 0),
        ):
            with self.subTest(entity=entity, field=field):
                actors, _, _ = self.runtime(entity)
                actors["pet"][field] = value
                with self.assertRaises(InputError):
                    PetCombat(actors, 24, 16, _select_target)

    def test_diggy_rebonds_after_owner_defeat_without_becoming_another_pet_assignment(
        self,
    ):
        actors, pets, trace = self.runtime(
            "diggy", others=[target(), owner("other", x=3.5)]
        )
        pets.prepare(actors, 0, trace)
        actors["hero"].update(hp=0, death_time=0.2)
        pets.prepare(actors, 0.2, trace)
        self.assertEqual(pets.states["pet"]["bonded_hero_id"], "other")
        self.assertEqual(pets.models["pet"]["hero_id"], "hero")
        self.assertEqual(
            len([event for event in trace if event["event"] == "pet_rebond"]), 1
        )

    def test_diggy_surface_freeze_delays_next_dive_and_death_stops_lifecycle(self):
        actors, pets, trace = self.runtime("diggy")
        pets.prepare(actors, 0, trace)
        surface = pets.states["pet"]["burrow"]["surface_seconds"]
        pets.advance(actors, 0, surface, trace)
        pets.prepare(actors, surface, trace)
        _apply_effects(
            [
                {
                    "id": "freeze",
                    "kind": "freeze",
                    "targets": ["pet"],
                    "duration_seconds": 1,
                }
            ],
            actors,
            surface,
            trace,
        )
        actors["tower"].update(hp=0, death_time=surface)
        pets.prepare(actors, surface + 0.5, trace)
        self.assertIsNone(pets.states["pet"]["dive_at"])
        self.assertTrue(_active(actors["pet"], surface + 0.5))
        actors["pet"].update(hp=0, death_time=surface + 0.5)
        pets.prepare(actors, surface + 2, trace)
        self.assertEqual(pets.states["pet"]["phase"], "dead")

    def test_lassi_jumps_enemy_walls_and_prefers_the_owner_neighborhood(self):
        barrier = [
            target(
                f"wall-{index}", x=4, y=index, kind="wall", counts_for_destruction=False
            )
            for index in range(16)
        ]
        actors, pets, trace = self.runtime(
            "lassi",
            hero=owner(x=6.5),
            others=[*barrier, target("near-hero", x=8), target("near-pet", x=1)],
        )
        pets.prepare(actors, 0, trace)
        actors["pet"]["x"] = 2.5
        selected, route = pets.select_target(
            actors["pet"], actors, 0, _blocked(actors, 0), 24, 16
        )
        self.assertEqual(selected["id"], "near-hero")
        self.assertTrue(
            any(floor_point == 4 for floor_point in (int(point[0]) for point in route))
        )

    def test_owl_follows_owner_primary_and_chain_damage_uses_catalog_decay(self):
        actors, pets, trace = self.runtime(
            "electro-owl", others=[target(), target("second", x=10)]
        )
        actors["hero"]["target"] = "tower"
        pets.prepare(actors, 0, trace)
        selected, _ = pets.select_target(
            actors["pet"], actors, 0, _blocked(actors, 0), 24, 16
        )
        self.assertEqual(selected["id"], "tower")
        combat = PatternCombat(actors)
        combat.launch(actors["pet"], selected, actors, 0.2, trace)
        damage = combat.resolve(actors, 0.2, trace)
        self.assertEqual(damage["tower"], 238)
        damage = combat.resolve(actors, 0.3, trace)
        self.assertAlmostEqual(damage["second"], 190.4)


if __name__ == "__main__":
    unittest.main()
