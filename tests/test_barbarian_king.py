"""King equipment release timing, splash and temporary wall-crossing behavior."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.barbarian_king import (
    BarbarianKingCombat,
    compile_king_equipment,
    validate_king_equipment,
)
from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError
from clashlab.damage_receipts import DamageReceipts
from clashlab.spatial import _load_actors

from test_dragon_duke import projectile
from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "declared-king-equipment-fixture-not-current-game-calibration"


def king_equipment(entity, level):
    parameters = {"source": SOURCE}
    if entity == "spiky-ball":
        parameters.update(
            initial_range_tiles=20,
            bounce_range_tiles=6,
            projectile_speed_tiles_per_second=10,
            first_delay_seconds=0.1,
            bounce_delay_seconds=0.1,
            selection="nearest_footprint_then_instance_id_without_revisits",
            target_kinds=["defense", "building"],
            target_layers=["ground"],
            visibility="exclude_hidden_teslas_and_invisible_buildings_at_each_launch",
            protected_targets="eligible_and_consume_target_slot",
            target_budget="consume_slot_on_launch_even_if_target_dies",
            inactive_target="continue_from_captured_target_center_without_damage",
            source_death="released_ball_persists",
            damage_scaling="equipment_flat_damage_times_hero_profile_only_hypothesis",
        )
    elif entity == "giant-gauntlet":
        parameters.update(
            splash_center="king_center_at_instant_launch_hypothesis",
            splash_target_kinds=["defense", "building", "wall", "unit"],
            splash_target_layers=["ground"],
            wall_swing="same_area_geometry_and_shared_main_attack_clock",
            self_heal_interval_seconds=0.5,
            first_self_heal_delay_seconds=0.5,
            self_heal_lifetime="while_deployed_independent_of_active_duration",
            freeze="duration_and_healing_clock_continue_while_frozen",
            damage_reduction_stacking="multiply_independent_incoming_damage_factors",
        )
    elif entity == "stick-horse":
        parameters.update(
            trigger="one_duration_from_actual_deployment",
            freeze="duration_continues_while_frozen",
            expiry_inside_wall="finish_retained_crossing_or_nearest_clear_cardinal_exit",
            bonus_stacking="add_movement_bonus_multiply_independent_attack_rate",
        )
    return {"entity": entity, "level": level, "parameters": parameters}


def king_actor(catalog, items=None, **changes):
    if items is None:
        items = [king_equipment("spiky-ball", 20), king_equipment("giant-gauntlet", 12)]
    models = [
        compile_king_equipment(
            item, {"entity": "barbarian-king", "town_hall": 16}, catalog
        )[0]
        for item in items
    ]
    actor = synthetic_unit(
        "king",
        x=5.5,
        y=5.5,
        range=1,
        damage=697.2,
        hitpoints=10965,
        attack_interval_seconds=1.2,
        target_priorities=["defense", "building"],
        healing_class="hero",
        hazard_class="hero",
        buff_class="hero",
        minimum_range=0,
        wall_behavior={"kind": "avoid", "source": SOURCE},
        attack_model={
            "kind": "single",
            "source": SOURCE,
            "target_kinds": ["defense", "building"],
            "target_layers": ["ground"],
            "maximum_hp_fraction": 0,
            "projectile": projectile(),
        },
        hero_model={
            "entity": "barbarian-king",
            "equipment": models,
            "damage_multiplier": 1,
            "range_multiplier": 1,
        },
        entity_adapter={"modifiers": {"movement_speed_multiplier": 1}},
    )
    actor.update(changes)
    return actor


def runtime(catalog, others=None, items=None, king_changes=None):
    king = king_actor(catalog, items, **(king_changes or {}))
    actors = _load_actors({"actors": [king, *(others or [])]}, 50, 50)
    for actor in actors.values():
        actor["minimum_range"] = 0
        if "attack_model" not in actor:
            actor["attack_model"] = {"kind": "none", "source": SOURCE}
            actor["damage"] = 0
    combat = PatternCombat(actors)
    king_runtime = BarbarianKingCombat(actors, combat, lambda *args: (None, []))
    return actors, combat, king_runtime


def horse_items():
    return [king_equipment("spiky-ball", 20), king_equipment("stick-horse", 11)]


class BarbarianKingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_source_named_stats_and_explicit_geometry_contract(self):
        actor = king_actor(self.catalog)
        ball, gauntlet = actor["hero_model"]["equipment"]
        self.assertEqual((ball["damage_per_target"], ball["target_count"]), (2500, 7))
        self.assertEqual(
            (gauntlet["duration_seconds"], gauntlet["splash_radius"]), (16, 2.5)
        )
        self.assertEqual(gauntlet["incoming_damage_multiplier"], 0.6)
        horse = compile_king_equipment(
            king_equipment("stick-horse", 11),
            {"entity": "barbarian-king", "town_hall": 16},
            self.catalog,
        )[0]
        self.assertEqual(horse["duration_seconds"], 18)
        self.assertAlmostEqual(horse["movement_bonus_tiles_per_second"], 14.3 / 8)
        self.assertAlmostEqual(horse["attack_rate_multiplier"], 1.11)
        invalid = deepcopy(ball)
        invalid["parameters"].pop("bounce_range_tiles")
        with self.assertRaises(InputError):
            validate_king_equipment(invalid)
        with self.assertRaises(InputError):
            compile_king_equipment(
                king_equipment("snake-bracelet", 12),
                {"entity": "barbarian-king", "town_hall": 16},
                self.catalog,
            )

    def test_spiky_ball_chooses_ground_buildings_and_excludes_hidden_sources(self):
        structures = [
            synthetic_structure("first", x=8, y=5),
            synthetic_structure("hidden", x=6, y=5),
            synthetic_structure("invisible", x=5, y=6),
            synthetic_structure(
                "wall", x=5, y=4, kind="wall", counts_for_destruction=False
            ),
            synthetic_unit("defender", team="defense", x=5.5, y=5.7),
        ]
        actors, _, king = runtime(self.catalog, structures)
        actors["hidden"]["_tesla_hidden"] = True
        actors["invisible"]["_spell_tower_untargetable_until"] = 10
        king.activate("king", actors, 0, [])
        self.assertEqual(king.packets[0][2]["target"], "first")
        self.assertAlmostEqual(king.packets[0][0], 0.4)

    def test_spiky_ball_uses_seven_distinct_slots_and_persists_after_king_death(self):
        buildings = [
            synthetic_structure(
                f"building-{index}", x=8 + index * 2, y=5, hitpoints=10000
            )
            for index in range(8)
        ]
        actors, _, king = runtime(self.catalog, buildings)
        trace = []
        king.activate("king", actors, 0, trace)
        self.assertFalse(king.activate("king", actors, 0, trace))
        actors["king"].update(hp=0, death_time=0.01)
        actors["building-1"]["immune_until"] = 100
        damaged = {}
        while king.packets:
            time = king.packets[0][0]
            damage, _ = king.resolve(actors, time, trace)
            damaged.update(damage)
        impacts = [entry for entry in trace if entry["event"] == "spiky_ball_impact"]
        self.assertEqual(len(impacts), 7)
        self.assertEqual(len({entry["target"] for entry in impacts}), 7)
        self.assertEqual(damaged["building-1"], 0)
        self.assertEqual(damaged["building-6"], 2500)
        self.assertNotIn("building-7", damaged)

    def test_dead_ball_target_consumes_slot_and_next_bounce_uses_captured_position(
        self,
    ):
        buildings = [
            synthetic_structure("first", x=8, y=5),
            synthetic_structure("second", x=11, y=5),
        ]
        actors, _, king = runtime(self.catalog, buildings)
        king.activate("king", actors, 0, [])
        actors["first"].update(hp=0, death_time=0.1, x=40)
        damage, _ = king.resolve(actors, 0.4, [])
        self.assertEqual(damage["first"], 0)
        self.assertEqual(king.packets[0][2]["target"], "second")
        self.assertEqual(king.packets[0][2]["remaining"], 5)
        self.assertAlmostEqual(king.packets[0][0], 0.8)

    def test_gauntlet_activation_changes_splash_and_mitigation_but_not_base_damage(
        self,
    ):
        actors, _, king = runtime(self.catalog)
        actor = actors["king"]
        king.prepare(actors, 0, [], 50, 50)
        self.assertEqual(actor["attack_model"]["kind"], "single")
        king.activate("king", actors, 1, [])
        king.prepare(actors, 1, [], 50, 50)
        self.assertEqual(actor["damage"], 697.2)
        self.assertEqual(actor["attack_model"]["kind"], "source_radial")
        ledger = DamageReceipts()
        self.assertEqual(
            ledger.register(
                actor,
                100,
                1,
                source_id="cannon",
                source_team="defense",
                origin="weapon",
            ),
            60,
        )
        king.prepare(actors, 17, [], 50, 50)
        self.assertEqual(actor["attack_model"]["kind"], "single")
        self.assertEqual(actor["_hero_incoming_damage_multiplier"], 1)

    def test_gauntlet_splash_is_source_centered_and_ground_only(self):
        others = [
            synthetic_structure("primary", x=6, y=5, hitpoints=5000),
            synthetic_structure("behind", x=3, y=5, hitpoints=5000),
            synthetic_structure("target_far_side", x=9, y=5, hitpoints=5000),
            synthetic_unit(
                "air", team="defense", x=5.5, y=5.6, layer="air", movement="air"
            ),
        ]
        actors, combat, king = runtime(self.catalog, others)
        king.activate("king", actors, 0, [])
        king.prepare(actors, 0, [], 50, 50)
        combat.launch(actors["king"], actors["primary"], actors, 0, [])
        damage = combat.resolve(actors, 0, [])
        self.assertEqual(damage["primary"], 697.2)
        self.assertEqual(damage["behind"], 697.2)
        self.assertEqual(damage["target_far_side"], 0)
        self.assertEqual(damage["air"], 0)

    def test_gauntlet_wall_swing_includes_primary_once_and_honors_unit_collateral(self):
        others = [
            synthetic_structure(
                "wall", x=6, y=5, kind="wall", counts_for_destruction=False
            ),
            synthetic_structure("near", x=7, y=5),
            synthetic_unit("defender", team="defense", x=5.5, y=6),
        ]
        actors, _, king = runtime(self.catalog, others)
        king.base_patterns["king"]["defending_unit_collateral_policy"] = "ignore"
        king.activate("king", actors, 0, [])
        king.prepare(actors, 0, [], 50, 50)
        targets = king.wall_impacts(actors["king"], actors["wall"], actors, 0)
        self.assertEqual(sorted(target["id"] for target in targets), ["near", "wall"])
        self.assertIsNone(king.wall_impacts(actors["king"], actors["wall"], actors, 16))

    def test_gauntlet_heals_before_activation_while_frozen_and_after_active_duration(
        self,
    ):
        actors, _, king = runtime(self.catalog)
        actors["king"]["frozen_until"] = 100
        king.prepare(actors, 0, [], 50, 50)
        self.assertEqual(king.resolve(actors, 0.5, [])[1]["king"], 14)
        king.activate("king", actors, 1, [])
        king.prepare(actors, 17, [], 50, 50)
        king.heal_next["king"] = 17
        self.assertEqual(king.resolve(actors, 17, [])[1]["king"], 14)

    def test_gauntlet_rejects_attack_range_that_would_omit_primary(self):
        with self.assertRaisesRegex(InputError, "in-range primary"):
            runtime(self.catalog, king_changes={"range": 3})

    def test_stick_horse_clock_starts_on_real_deployment_and_bonuses_expire_during_freeze(
        self,
    ):
        actors, _, king = runtime(
            self.catalog,
            items=horse_items(),
            king_changes={"spawn_seconds": "controlled"},
        )
        actor = actors["king"]
        king.prepare(actors, 0, [], 50, 50)
        self.assertIsNone(king.horse_until["king"])
        actor.update(spawn_seconds=2, frozen_until=30, next_attack=31.2)
        king.prepare(actors, 2, [], 50, 50)
        self.assertEqual(king.horse_until["king"], 20)
        self.assertEqual(actor["wall_behavior"]["kind"], "jump_enemy_walls")
        self.assertAlmostEqual(actor["_hero_movement_bonus"], 14.3 / 8)
        self.assertAlmostEqual(actor["next_attack"], 30 + 1.2 / 1.11)
        king.prepare(actors, 20, [], 50, 50)
        self.assertEqual(actor["wall_behavior"]["kind"], "avoid")
        self.assertEqual(actor["_hero_movement_bonus"], 0)
        self.assertAlmostEqual(actor["next_attack"], 31.2)

    def test_horse_expiry_inside_wall_finishes_retained_crossing_without_bonuses(self):
        wall = synthetic_structure(
            "wall", x=5, y=5, kind="wall", counts_for_destruction=False
        )
        actors, _, king = runtime(
            self.catalog, [wall], horse_items(), {"x": 5.2, "y": 5.5}
        )
        actor = actors["king"]
        king.prepare(actors, 0, [], 50, 50)
        actor["_remaining_path"] = [(5.5, 5.5), (6.5, 5.5), (8.5, 5.5)]
        king.prepare(actors, 18, [], 50, 50)
        self.assertEqual(actor["_hero_attack_rate"], 1)
        self.assertEqual(actor["_hero_movement_bonus"], 0)
        self.assertEqual(actor["wall_behavior"]["kind"], "jump_enemy_walls")
        target, route = king.select_target(actor, actors, 18, {(5, 5)}, 50, 50)
        self.assertIsNone(target)
        self.assertEqual(route, [(5.5, 5.5), (6.5, 5.5)])
        actor["x"] = 6.1
        king.prepare(actors, 18.45, [], 50, 50)
        self.assertEqual(actor["wall_behavior"]["kind"], "jump_enemy_walls")
        actor["x"] = 6.5
        king.prepare(actors, 18.65, [], 50, 50)
        self.assertEqual(actor["wall_behavior"]["kind"], "avoid")
        self.assertNotIn("king", king.egress)

    def test_horse_expiry_without_target_finds_clear_exit_around_solid_building(self):
        objects = [
            synthetic_structure(
                "wall", x=5, y=5, kind="wall", counts_for_destruction=False
            ),
            synthetic_structure("solid", x=4, y=5),
        ]
        actors, _, king = runtime(self.catalog, objects, horse_items())
        king.prepare(actors, 0, [], 50, 50)
        king.prepare(actors, 18, [], 50, 50)
        self.assertEqual(king.egress["king"], [(5.5, 4.5)])


if __name__ == "__main__":
    unittest.main()
