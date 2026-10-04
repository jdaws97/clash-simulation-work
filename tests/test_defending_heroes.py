"""Defending hero statistics, targeting, movement boundaries and recovery."""

from copy import deepcopy
from math import sqrt
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.battle_modifiers import apply_battle_modifiers
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.defending_hero_rules import RULES, RULESET, SCOPE
from clashlab.defending_heroes import DefendingHeroCombat
from clashlab.spatial import _load_actors, _select_target, simulate_spatial

from test_adapters import entity_instance, projectile
from test_battle_modifiers import modifier_policy
from test_indirect_defenses import damage_command, fixed_tank, indirect_sector
from test_valkyrie_integration import building


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "explicit-defending-hero-fixture-not-game-calibration"


def defender_instance(
    entity="barbarian-king",
    instance_id="defender",
    banner_id="banner",
    banner_x=20,
    banner_y=10,
    **changes,
):
    statue = entity == "grand-warden"
    mode = "statue" if statue else "air" if entity == "minion-prince" else "ground"
    instance = entity_instance(
        instance_id,
        entity,
        1,
        "defense",
        mode=mode,
        statistics_mode="normal",
        counts_for_destruction=False,
        x=banner_x if statue else banner_x + 1,
        y=banner_y if statue else banner_y + 1,
        defending_hero_parameters={
            "source": SOURCE,
            "statistics_mapping": "snapshot_base_defending_no_equipment_hypothesis",
            "equipment_policy": "none_on_defense",
            "pet_policy": "none_on_defense",
            "ability_policy": "no_active_defending_ability",
            "destruction_policy": (
                "statue_excluded_hypothesis" if statue else "hero_excluded_hypothesis"
            ),
            "banner": {
                "id": banner_id,
                "x": banner_x,
                "y": banner_y,
                "footprint_policy": "nonblocking_indestructible_anchor",
            },
            "aggro": {
                "radius_basis": "snapshot_searchRadius",
                "radius_multiplier": 1,
                "trigger": "altar_radius_or_received_damage",
                "retaliation": "nearest_eligible_within_leash",
            },
            "leash": {
                "radius_tiles": 14,
                "loss_policy": "return_when_primary_dead_ineligible_outside_leash_or_unreachable",
            },
            "patrol": {"waypoints": [], "selection": "ordered_loop"},
            "return": {
                "reacquire": "only_after_arrival",
                "attack_clock": "preserve_shared_cooldown",
            },
            "healing": {
                "amount_per_pulse": 20,
                "interval_seconds": 0.5,
                "delay_after_combat_seconds": 1,
                "location": "at_banner_only",
                "freeze": "pulse_clock_continues_skip_while_frozen",
                "first_pulse": "one_interval_after_home_and_combat_delay",
            },
            "death": "permanent_for_battle",
        },
    )
    if mode == "ground":
        instance["wall_parameters"] = {"kind": "avoid", "source": SOURCE}
    instance.update(changes)
    return instance


def defender_sector(catalog, entities, responses=None, **changes):
    specification = indirect_sector(
        catalog, entities, scope=SCOPE, model_rules=deepcopy(RULES), width=50, height=28
    )
    specification["defending_unit_responses"] = {
        "source": SOURCE,
        "actors": (
            responses
            if responses is not None
            else {
                instance["id"]: {"primary": "ignore", "collateral": "ignore"}
                for instance in entities
                if instance["team"] == "attack"
            }
        ),
    }
    specification.update(changes)
    return specification


def events(result, kind, source="defender"):
    return [
        event
        for event in result["trace"]
        if event.get("event") == kind and event.get("source") == source
    ]


class DefendingHeroTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def compile(self, entities, **changes):
        return compile_entity_scene(
            defender_sector(self.catalog, entities, **changes), self.catalog
        )

    def run_scene(self, entities, **changes):
        return simulate_spatial(self.compile(entities, **changes)["scene"])

    def runtime(self, entities, **changes):
        scene = self.compile(entities, **changes)["scene"]
        actors = _load_actors(scene, 50, 28)
        runtime = DefendingHeroCombat(actors, _select_target, scene)
        trace = []
        runtime.prepare(actors, 0, trace)
        return actors, runtime, trace

    def test_all_five_defenders_use_snapshot_base_without_attack_equipment(self):
        for entity in (
            "barbarian-king",
            "archer-queen",
            "royal-champion",
            "grand-warden",
            "minion-prince",
        ):
            with self.subTest(entity=entity):
                compiled = self.compile([defender_instance(entity)])
                actor = compiled["scene"]["actors"][0]
                stats = self.catalog.level(entity, 1)
                self.assertEqual(actor["hitpoints"], stats["hitpoints"])
                self.assertEqual(actor["damage"], stats["damagePerHit"])
                self.assertNotIn("hero_model", actor)
                self.assertEqual(
                    actor["defending_hero_model"]["aggro_radius"],
                    self.catalog.entity(entity)["searchRadius"],
                )
                self.assertEqual(compiled["scene"]["ruleset"], RULESET)
                self.assertFalse(compiled["full_game_prediction"])

    def test_attack_loadout_and_guessed_recovery_are_rejected(self):
        for field, value in (("hero_parameters", {}), ("equipment", []), ("pet", None)):
            instance = defender_instance()
            instance[field] = value
            with self.subTest(field=field), self.assertRaises(InputError):
                self.compile([instance])
        instance = defender_instance()
        del instance["defending_hero_parameters"]["healing"]["amount_per_pulse"]
        with self.assertRaises(InputError):
            self.compile([instance])

    def test_banner_requires_unique_hero_and_nonoverlapping_legal_footprint(self):
        bad_scenes = [
            [
                defender_instance(),
                defender_instance(
                    instance_id="duplicate", banner_id="other", banner_x=25
                ),
            ],
            [
                defender_instance(),
                defender_instance(
                    "archer-queen", instance_id="queen", banner_id="other", banner_x=21
                ),
            ],
            [defender_instance(), building("overlap", 20, y=10)],
            [defender_instance(banner_x=49)],
        ]
        for entities in bad_scenes:
            with self.subTest(entities=entities), self.assertRaises(InputError):
                self.compile(entities)

    def test_banner_slot_limit_and_initial_anchor_are_enforced(self):
        entities = [
            defender_instance(
                entity,
                instance_id=entity,
                banner_id=entity + "-banner",
                banner_x=5 + index * 7,
            )
            for index, entity in enumerate(
                (
                    "barbarian-king",
                    "archer-queen",
                    "royal-champion",
                    "grand-warden",
                    "minion-prince",
                )
            )
        ]
        with self.assertRaises(InputError):
            self.compile(entities)
        with self.assertRaises(InputError):
            self.compile([defender_instance(x=22)])

    def test_warden_is_separate_statue_with_explicit_destruction_policy(self):
        for counted in (False, True):
            instance = defender_instance("grand-warden", counts_for_destruction=counted)
            instance["defending_hero_parameters"]["destruction_policy"] = (
                "statue_counts_hypothesis" if counted else "statue_excluded_hypothesis"
            )
            compiled = self.compile([instance])
            actor = compiled["scene"]["actors"][0]
            self.assertEqual(actor["kind"], "defense")
            self.assertEqual(actor["movement"], "stationary")
            self.assertEqual((actor["width"], actor["height"]), (2, 2))
            self.assertEqual(actor["counts_for_destruction"], counted)
            self.assertEqual(len(compiled["scene"]["actors"]), 1)
        with self.assertRaises(InputError):
            self.compile(
                [defender_instance("grand-warden", counts_for_destruction=True)]
            )

    def test_king_cannot_acquire_air_but_queen_can(self):
        for entity, count in (("barbarian-king", 0), ("archer-queen", 1)):
            result = self.run_scene(
                [defender_instance(entity), fixed_tank(entity="minion", x=24, y=11)],
                duration_seconds=0.01,
            )
            with self.subTest(entity=entity):
                self.assertEqual(len(events(result, "defending_hero_acquired")), count)

    def test_attackers_explicitly_choose_primary_priority(self):
        for policy, expected in (
            ("same_tier_as_buildings", "defender"),
            ("after_buildings", "store"),
            ("ignore", "store"),
        ):
            result = self.run_scene(
                [
                    defender_instance(),
                    fixed_tank(x=22, y=11, first_attack_seconds=0),
                    building("store", 32, y=10),
                ],
                responses={"tank": {"primary": policy, "collateral": "ignore"}},
                duration_seconds=0.01,
            )
            with self.subTest(policy=policy):
                self.assertEqual(
                    events(result, "projectile_launch", "tank")[0]["target"], expected
                )

    def test_missing_primary_or_collateral_response_cannot_be_silently_inferred(self):
        for responses in (
            {},
            {"tank": {"primary": "ignore"}},
            {"tank": {"primary": "ignore", "collateral": "guess"}},
        ):
            with self.subTest(responses=responses), self.assertRaises(InputError):
                self.compile([defender_instance(), fixed_tank()], responses=responses)

    def test_primary_ignore_and_collateral_allow_are_independent(self):
        for collateral, expected_hits in (
            ("allow", {"store", "defender"}),
            ("ignore", {"store"}),
        ):
            dragon = entity_instance(
                "dragon",
                "dragon",
                1,
                "attack",
                x=31.5,
                y=11.5,
                attack_parameters={"projectile": projectile(), "radius": 4},
            )
            result = self.run_scene(
                [
                    defender_instance("archer-queen", banner_x=29),
                    dragon,
                    building("store", 32, y=10),
                ],
                responses={"dragon": {"primary": "ignore", "collateral": collateral}},
                duration_seconds=0.01,
            )
            with self.subTest(collateral=collateral):
                self.assertEqual(
                    {
                        event["target"]
                        for event in events(result, "projectile_impact", "dragon")
                    },
                    expected_hits,
                )

    def test_aggro_entry_is_exact_across_solver_step_sizes(self):
        for step in (0.01, 0.8):
            tank = fixed_tank(x=34.5, y=11)
            tank["modifiers"]["range_multiplier"] = 1
            result = self.run_scene(
                [defender_instance("grand-warden"), tank],
                duration_seconds=2.1,
                maximum_step_seconds=step,
                recording_interval_seconds=5,
            )
            acquired = events(result, "defending_hero_acquired")
            with self.subTest(step=step):
                self.assertEqual(len(acquired), 1)
                # Ground routing first reaches its cell center (34.5,11.5),
                # travelling 0.5 tile, then heads west. The circle intersects
                # that horizontal leg at x=21+sqrt(10**2-0.5**2).
                expected = (0.5 + 34.5 - (21 + sqrt(100 - 0.25))) / 2
                self.assertAlmostEqual(acquired[0]["time_seconds"], expected, places=8)

    def test_forced_frozen_air_motion_can_cross_aggro_at_explicit_speed(self):
        actors, runtime, trace = self.runtime(
            [defender_instance("grand-warden"), fixed_tank(entity="minion", x=35, y=11)]
        )
        target = actors["tank"]
        target["frozen_until"] = 10
        route = [(25, 11)]
        self.assertIsNone(runtime.first_crossing_delay(target, route, 0, 10))
        self.assertAlmostEqual(
            runtime.first_crossing_delay(
                target, route, 0, 10, effective_speed=4, forced_motion=True
            ),
            1,
        )

    def test_acquisition_waits_for_exact_reachable_firing_cell_contact(self):
        for step in (1, 0.3, 0.1):
            target = fixed_tank(entity="minion", x=14.7, y=11.5)
            target["modifiers"]["range_multiplier"] = 1
            walls = [
                building(
                    f"wall-{row}",
                    20,
                    entity="wall",
                    level=17,
                    y=row,
                    counts_for_destruction=False,
                )
                for row in range(28)
            ]
            compiled = self.compile(
                [
                    defender_instance("archer-queen", banner_x=23),
                    target,
                    building("destination", 35, y=10),
                    *walls,
                ],
                duration_seconds=0.9,
                maximum_step_seconds=step,
                recording_interval_seconds=2,
            )
            result = simulate_spatial(compiled["scene"])
            acquired = events(result, "defending_hero_acquired")
            with self.subTest(step=step):
                self.assertEqual(len(acquired), 1)
                # The Queen cannot cross the wall at x=20. The first reachable
                # firing center is (21.5, 11.5), with five tiles of range.
                # The Minion is already inside aggro and travels at four tiles/s.
                self.assertAlmostEqual(acquired[0]["time_seconds"], 0.45, places=8)

    def test_reachability_cache_invalidates_after_obstacle_destruction(self):
        target = fixed_tank(entity="minion", x=14.7, y=11.5)
        target["modifiers"]["range_multiplier"] = 1
        walls = [
            building(
                f"wall-{row}",
                20,
                entity="wall",
                level=17,
                y=row,
                counts_for_destruction=False,
            )
            for row in range(28)
        ]
        actors, runtime, trace = self.runtime(
            [defender_instance("archer-queen", banner_x=23), target, *walls]
        )
        target = actors["tank"]
        self.assertAlmostEqual(
            runtime.first_crossing_delay(target, [(19, 11.5)], 0, 1), 0.45
        )
        actors["wall-11"]["hp"] = 0
        runtime.prepare(actors, 0, trace)
        self.assertIsNone(runtime.first_crossing_delay(target, [(19, 11.5)], 0, 1))
        selected, _ = runtime.select_target(
            actors["defender"], actors, 0, runtime.blocked, 50, 28
        )
        self.assertEqual(selected["id"], "tank")

    def test_leash_exit_is_an_exact_movement_boundary(self):
        actors, runtime, trace = self.runtime(
            [
                defender_instance("minion-prince"),
                fixed_tank(entity="minion", x=30, y=11),
            ]
        )
        defender, target = actors["defender"], actors["tank"]
        selected, _ = runtime.select_target(defender, actors, 0, set(), 50, 28)
        self.assertEqual(selected["id"], "tank")
        self.assertAlmostEqual(
            runtime.first_crossing_delay(target, [(40, 11)], 0, 10, effective_speed=2),
            2.5,
        )
        target["x"] = 35
        selected, _ = runtime.select_target(defender, actors, 2.5, set(), 50, 28)
        self.assertIsNone(selected)
        self.assertNotEqual(runtime.states["defender"]["phase"], "engaged")

    def test_air_defender_returns_and_heals_on_scheduled_home_pulses(self):
        for step in (0.01, 0.8):
            result = self.run_scene(
                [defender_instance("minion-prince"), fixed_tank(x=28, y=11)],
                effects=[
                    damage_command("defender", 0, 50, "injure"),
                    damage_command("tank", 1, 7700),
                ],
                duration_seconds=3.6,
                maximum_step_seconds=step,
                recording_interval_seconds=5,
            )
            heals = events(result, "defending_hero_heal")
            with self.subTest(step=step):
                self.assertEqual(
                    [round(event["time_seconds"], 8) for event in heals], [2.5, 3, 3.5]
                )
                self.assertEqual([event["amount"] for event in heals], [20, 20, 10])
                self.assertEqual(
                    (
                        result["actors"]["defender"]["x"],
                        result["actors"]["defender"]["y"],
                    ),
                    (21, 11),
                )
                self.assertEqual(result["actors"]["defender"]["hp"], 200)

    def test_freeze_skips_healing_pulses_without_catchup(self):
        result = self.run_scene(
            [defender_instance("minion-prince"), fixed_tank(x=28, y=11)],
            effects=[
                damage_command("defender", 0, 50, "injure"),
                damage_command("tank", 1, 7700),
                {
                    "id": "freeze",
                    "kind": "freeze",
                    "time_seconds": 2.2,
                    "targets": ["defender"],
                    "duration_seconds": 0.6,
                },
            ],
            duration_seconds=4.1,
        )
        self.assertEqual(
            [event["time_seconds"] for event in events(result, "defending_hero_heal")],
            [3, 3.5, 4],
        )

    def test_dead_defender_never_regenerates_or_respawns(self):
        result = self.run_scene(
            [defender_instance("minion-prince"), fixed_tank(x=28, y=11)],
            effects=[
                damage_command("defender", 0, 50, "injure"),
                damage_command("tank", 1, 7700),
                damage_command("defender", 2.4, 1000, "kill-defender"),
            ],
            duration_seconds=4,
        )
        self.assertEqual(result["actors"]["defender"]["hp"], 0)
        self.assertFalse(events(result, "defending_hero_heal"))
        self.assertEqual(
            result["defending_heroes"]["states"]["defender"]["phase"], "dead"
        )

    def test_ordered_air_patrol_arrival_and_wait_are_step_invariant(self):
        positions = []
        for step in (0.01, 0.8):
            instance = defender_instance("minion-prince")
            instance["defending_hero_parameters"]["patrol"]["waypoints"] = [
                {"x": 24, "y": 11, "wait_seconds": 0.5},
                {"x": 21, "y": 11, "wait_seconds": 0.5},
            ]
            result = self.run_scene(
                [instance],
                duration_seconds=2.5,
                maximum_step_seconds=step,
                recording_interval_seconds=5,
            )
            positions.append(
                (result["actors"]["defender"]["x"], result["actors"]["defender"]["y"])
            )
            phases = events(result, "defending_hero_phase")
            waits = [
                event["time_seconds"]
                for event in phases
                if event["to"] == "patrol_wait"
            ]
            self.assertEqual([round(time, 8) for time in waits], [1, 2.5])
        self.assertEqual(positions, [(21, 11), (21, 11)])

    def test_damage_triggers_retaliation_outside_ordinary_aggro(self):
        result = self.run_scene(
            [defender_instance("archer-queen"), fixed_tank(x=33, y=11)],
            effects=[damage_command("defender", 0.5, 1)],
            duration_seconds=0.6,
        )
        self.assertEqual(
            [
                event["time_seconds"]
                for event in events(result, "defending_hero_acquired")
            ],
            [0.5],
        )

    def test_defending_hero_profile_scales_combat_once_without_equipment_or_healing_scaling(
        self,
    ):
        scene = self.compile([defender_instance()])["scene"]
        original = deepcopy(scene["actors"][0])
        modified = apply_battle_modifiers(
            scene,
            modifier_policy("esport"),
            self.catalog,
            read_json(ROOT / "data" / "mode-rules.json"),
        )
        actor = modified["scene"]["actors"][0]
        self.assertAlmostEqual(actor["damage"], original["damage"] * 1.25)
        self.assertAlmostEqual(actor["hitpoints"], original["hitpoints"] * 1.25)
        self.assertEqual(
            actor["defending_hero_model"], original["defending_hero_model"]
        )
        self.assertEqual(modified["application"]["actors"][0]["role"], "defending_hero")

    def test_raw_scenes_cannot_bypass_bound_defending_unit_responses(self):
        base = self.compile([defender_instance(), fixed_tank()])["scene"]
        variants = []
        scene = deepcopy(base)
        del scene["defending_unit_responses"]
        variants.append(scene)
        scene = deepcopy(base)
        del scene["actors"][1]["defending_unit_response"]
        variants.append(scene)
        scene = deepcopy(base)
        scene["actors"][1]["attack_model"]["defending_unit_collateral_policy"] = "allow"
        variants.append(scene)
        scene = deepcopy(base)
        scene["actors"][1]["target_priorities"].append("unit")
        scene["actors"][1]["target_priority_tiers"][-1].append("unit")
        scene["actors"][1]["attack_model"]["target_kinds"].append("unit")
        variants.append(scene)
        for index, scene in enumerate(variants):
            with self.subTest(variant=index), self.assertRaises(InputError):
                simulate_spatial(scene)

    def test_radial_primary_is_hurt_when_other_defender_collateral_is_ignored(self):
        dragon = entity_instance(
            "dragon",
            "dragon",
            1,
            "attack",
            x=22,
            y=11,
            attack_parameters={"projectile": projectile(), "radius": 4},
        )
        result = self.run_scene(
            [
                defender_instance(),
                defender_instance(
                    "archer-queen",
                    instance_id="queen",
                    banner_id="queen-banner",
                    banner_x=23,
                ),
                dragon,
            ],
            responses={
                "dragon": {"primary": "same_tier_as_buildings", "collateral": "ignore"}
            },
            duration_seconds=0.01,
        )
        self.assertEqual(
            events(result, "projectile_launch", "dragon")[0]["target"], "defender"
        )
        self.assertEqual(
            [
                event["target"]
                for event in events(result, "projectile_impact", "dragon")
            ],
            ["defender"],
        )

    def test_ground_patrol_routes_around_a_wall_and_arrives_at_an_exact_boundary(self):
        for step in (0.01, 0.8):
            defender = defender_instance()
            defender["defending_hero_parameters"]["patrol"]["waypoints"] = [
                {"x": 24.5, "y": 11.5, "wait_seconds": 1},
                {"x": 21, "y": 11, "wait_seconds": 1},
            ]
            wall = entity_instance(
                "wall",
                "wall",
                17,
                "defense",
                x=22,
                y=11,
                mode="passive",
                statistics_mode="none",
                counts_for_destruction=False,
                attack_parameters={},
                inactive_attack_interval_seconds=1,
            )
            result = self.run_scene(
                [defender, wall],
                duration_seconds=3,
                maximum_step_seconds=step,
                recording_interval_seconds=5,
            )
            waiting = [
                event
                for event in events(result, "defending_hero_phase")
                if event["to"] == "patrol_wait"
            ]
            with self.subTest(step=step):
                self.assertEqual(len(waiting), 1)
                self.assertAlmostEqual(
                    waiting[0]["time_seconds"], (sqrt(0.5) + 5) / 2, places=8
                )
                self.assertEqual(
                    (
                        result["actors"]["defender"]["x"],
                        result["actors"]["defender"]["y"],
                    ),
                    (24.5, 11.5),
                )

    def test_freeze_preserves_remaining_defender_attack_work(self):
        freeze = {
            "id": "freeze",
            "kind": "freeze",
            "time_seconds": 0.25,
            "targets": ["defender"],
            "duration_seconds": 2,
        }
        result = self.run_scene(
            [defender_instance(), fixed_tank(x=22, y=11)],
            effects=[freeze],
            duration_seconds=3.3,
        )
        self.assertEqual(
            [
                round(event["time_seconds"], 8)
                for event in events(result, "projectile_launch")
            ],
            [0, 3.2],
        )

    def test_released_defender_projectile_survives_source_death(self):
        defender = defender_instance("archer-queen")
        defender["attack_parameters"]["projectile"] = {
            "timing": "launch_distance_delay",
            "speed_tiles_per_second": 1,
            "destination": "locked_actor_center_at_impact",
            "hit_radius": 0,
        }
        result = self.run_scene(
            [defender, fixed_tank(x=24, y=11)],
            effects=[damage_command("defender", 0.25, 10000)],
            duration_seconds=3.1,
        )
        self.assertEqual(len(events(result, "projectile_launch")), 1)
        self.assertEqual(
            [event["time_seconds"] for event in events(result, "projectile_impact")],
            [3],
        )
        self.assertEqual(result["actors"]["tank"]["hp"], 7700 - 102)


if __name__ == "__main__":
    unittest.main()
