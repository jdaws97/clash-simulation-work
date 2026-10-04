"""Duke source mappings, moving isolation boundaries and damage-aware passives."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError
from clashlab.damage_receipts import DamageReceipts
from clashlab.dragon_duke import (
    DragonDukeCombat,
    compile_duke_equipment,
    compile_duke_intrinsic,
    first_relative_circle_crossing,
    validate_duke_equipment,
    validate_duke_intrinsic,
)
from clashlab.spatial import _apply_health, _load_actors

from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "declared-duke-behavior-fixture-not-game-calibration"


def projectile(speed=None):
    result = {
        "timing": "instant" if speed is None else "launch_distance_delay",
        "delay_seconds": 0,
        "destination": "locked_actor_center_at_impact",
        "hit_radius": 0,
    }
    if speed is not None:
        result["speed_tiles_per_second"] = speed
    return result


def duke_parameters():
    return {
        "source": SOURCE,
        "friendly_air_radius_tiles": 3,
        "friendly_air_classes": ["troop", "hero", "pet", "siege", "guardian"],
        "friendly_air_visibility": "include_invisible",
        "friendly_air_frozen": "include_frozen",
        "friendly_air_inactive": "exclude_reserves_dead_and_phoenix_eggs",
        "isolated_range_tiles": 4,
        "nearby_projectile": projectile(),
        "isolated_projectile": projectile(10),
        "membership": "center_distance_inside_after_motion_hypothesis",
        "stacking": "multiply_independent_damage_and_attack_rate_factors",
        "rampage_damage_scope": "ordinary_weapon_only_hypothesis",
    }


def duke_equipment(entity, level):
    parameters = {
        "source": SOURCE,
        "damage_scaling": "equipment_flat_damage_times_hero_profile_only_hypothesis",
    }
    if entity == "revenge-deck":
        parameters.update(
            projectile=projectile(10),
            trigger="positive_actual_hp_loss_from_live_hostile_actor",
            source_origins=["weapon", "hazard", "death", "ability"],
            counter_timing="after_same_timestamp_health_if_duke_survives",
            cooldown="shared_across_sources_first_receipt_order_no_catchup",
            heal="on_counter_launch",
            freeze="block_counter_without_retaining_receipts",
            ineligible_source="discard_receipt",
            source_death="released_counter_persists",
        )
    else:
        parameters.update(
            self_heal_interval_seconds=0.5,
            first_self_heal_delay_seconds=0.5,
            freeze="healing_clock_continues_while_frozen",
            death_delay_seconds=0.2,
            death_target_kinds=["defense", "building", "unit"],
            death_target_layers=["ground", "air"],
            protection="respect_invulnerability",
            lethal_trigger="actual_death_after_lethal_interception",
            removal_trigger="exclude_physical_ejection_include_phoenix_final_defeat",
            death_position="capture_center_at_actual_death",
        )
    return {"entity": entity, "level": level, "parameters": parameters}


def duke_actor(catalog, items=None, **changes):
    if items is None:
        items = [duke_equipment("revenge-deck", 20), duke_equipment("fire-heart", 18)]
    instance = {
        "entity": "dragon-duke",
        "town_hall": 16,
        "duke_parameters": duke_parameters(),
    }
    models = [compile_duke_equipment(item, instance, catalog)[0] for item in items]
    actor = synthetic_unit(
        "duke",
        x=10,
        y=10,
        layer="air",
        movement="air",
        range=1.25,
        damage=417.6,
        hitpoints=9925,
        attack_interval_seconds=1.2,
        target_layers=["ground", "air"],
        target_priorities=["defense", "building"],
        healing_class="hero",
        buff_class="hero",
        hazard_class="hero",
        attack_model={
            "kind": "single",
            "source": SOURCE,
            "target_kinds": ["defense", "building"],
            "target_layers": ["ground", "air"],
            "maximum_hp_fraction": 0,
            "projectile": projectile(),
        },
        hero_model={
            "entity": "dragon-duke",
            "equipment": models,
            "damage_multiplier": 1,
            "range_multiplier": 1,
        },
        duke_model=compile_duke_intrinsic(
            instance, catalog.entity("dragon-duke"), catalog
        ),
    )
    actor.update(changes)
    return actor


def air_ally(**changes):
    actor = synthetic_unit(
        "ally", x=10, y=10, layer="air", movement="air", buff_class="troop"
    )
    actor.update(changes)
    return actor


def runtime(catalog, others=None, items=None):
    actors = _load_actors(
        {"actors": [duke_actor(catalog, items), *(others or [])]}, 50, 50
    )
    for actor in actors.values():
        actor["minimum_range"] = 0
        if "attack_model" not in actor:
            actor["attack_model"] = {"kind": "none", "source": SOURCE}
            if actor["damage"] > 0:
                actor["attack_model"].update(
                    kind="single",
                    target_kinds=actor["target_priorities"],
                    target_layers=actor["target_layers"],
                    maximum_hp_fraction=0,
                    projectile=projectile(),
                )
    patterns = PatternCombat(actors)
    return actors, patterns, DragonDukeCombat(actors, patterns)


def attributed_hit(
    actors, target="duke", source="cannon", amount=10, time=0, origin="weapon"
):
    ledger = DamageReceipts()
    value = ledger.register(
        actors[target],
        amount,
        time,
        source_id=source,
        source_actor_id=source,
        source_team=actors[source]["team"],
        origin=origin,
    )
    damage = {target: value}
    receipts = ledger.settle(actors, damage, time)
    from collections import defaultdict

    _apply_health(actors, defaultdict(float, damage), defaultdict(float), time)
    return receipts


class DragonDukeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_source_stat_mapping_and_explicit_missing_geometry(self):
        actor = duke_actor(self.catalog)
        self.assertEqual(actor["duke_model"]["isolated_damage_multiplier"], 2)
        self.assertEqual(actor["duke_model"]["isolated_attack_rate_multiplier"], 1.5)
        deck, heart = actor["hero_model"]["equipment"]
        self.assertEqual((deck["counter_damage"], deck["heal_per_counter"]), (195, 49))
        self.assertEqual(
            (deck["counter_range"], deck["counter_cooldown_seconds"]), (25, 0.8)
        )
        self.assertEqual((heart["death_damage"], heart["death_radius"]), (3000, 4))
        self.assertEqual(heart["self_healing_per_second"], 175)
        bad = deepcopy(actor["duke_model"])
        bad["parameters"].pop("friendly_air_radius_tiles")
        with self.assertRaises(InputError):
            validate_duke_intrinsic(bad)
        bad = deepcopy(deck)
        bad["parameters"]["source_origins"].append("revenge_counter")
        with self.assertRaises(InputError):
            validate_duke_equipment(bad)
        bad = deepcopy(heart)
        bad["parameters"]["death_delay_seconds"] = -1
        with self.assertRaises(InputError):
            validate_duke_equipment(bad)

    def test_isolation_changes_weapon_and_rescales_only_unfinished_attack_work(self):
        actors, _, duke = runtime(self.catalog, [air_ally()])
        actor = actors["duke"]
        trace = []
        duke.prepare(actors, 0, trace)
        self.assertFalse(actor["_duke_isolated"])
        self.assertEqual(actor["range"], 1.25)
        actor["frozen_until"] = 3
        actor["next_attack"] = 4.2
        actor["_wall_next_attack"] = 5.4
        actors["ally"]["x"] = 14
        duke.prepare(actors, 1, trace)
        self.assertTrue(actor["_duke_isolated"])
        self.assertEqual(actor["_hero_damage_multiplier"], 2)
        self.assertEqual(actor["_hero_trap_damage_multiplier"], 0.5)
        self.assertAlmostEqual(actor["next_attack"], 3.8)
        self.assertAlmostEqual(actor["_wall_next_attack"], 4.6)
        self.assertEqual(actor["range"], 4)
        self.assertEqual(
            actor["attack_model"]["projectile"]["timing"], "launch_distance_delay"
        )
        actors["ally"]["x"] = 10
        duke.prepare(actors, 2, trace)
        self.assertAlmostEqual(actor["next_attack"], 4.2)
        self.assertEqual(actor["_hero_attack_rate"], 1)

    def test_membership_includes_invisible_frozen_air_but_excludes_reserves_and_ground(
        self,
    ):
        actors, _, duke = runtime(self.catalog, [air_ally()])
        ally = actors["ally"]
        ally["_untargetable_until"] = 10
        ally["frozen_until"] = 10
        duke.prepare(actors, 0, [])
        self.assertFalse(actors["duke"]["_duke_isolated"])
        for change in (
            {"spawn_seconds": "controlled"},
            {"spawn_seconds": 0, "layer": "ground"},
            {"layer": "air", "hp": 0},
        ):
            with self.subTest(change=change):
                ally.update(change)
                duke.prepare(actors, 0, [])
                self.assertTrue(actors["duke"]["_duke_isolated"])

    def test_relative_entry_exit_and_exact_endpoint_boundaries(self):
        first = {"x": 0, "y": 0, "width": 0, "height": 0}
        second = {"x": 8, "y": 0, "width": 0, "height": 0}
        crossing = first_relative_circle_crossing(
            first, second, [(10, 0)], [(0, 0)], 1, 1, 3, 3, False
        )
        self.assertAlmostEqual(crossing["delay_seconds"], 2.5)
        self.assertTrue(crossing["inside_after"])
        second["x"] = 2
        crossing = first_relative_circle_crossing(
            first, second, [], [(8, 0)], 0, 2, 3, 0.5, True
        )
        self.assertAlmostEqual(crossing["delay_seconds"], 0.5)
        self.assertFalse(crossing["inside_after"])
        second["x"] = 5
        crossing = first_relative_circle_crossing(
            first, second, [], [(3, 0)], 0, 2, 3, 1, False
        )
        self.assertAlmostEqual(crossing["delay_seconds"], 1)
        self.assertTrue(crossing["inside_after"])

    def test_tangent_and_equal_velocity_do_not_toggle_isolation(self):
        first = {"x": 0, "y": 0, "width": 0, "height": 0}
        second = {"x": -5, "y": 3, "width": 0, "height": 0}
        self.assertIsNone(
            first_relative_circle_crossing(
                first, second, [], [(5, 3)], 0, 1, 3, 10, False
            )
        )
        second.update(x=2, y=0)
        self.assertIsNone(
            first_relative_circle_crossing(
                first, second, [(10, 0)], [(12, 0)], 1, 1, 3, 10, True
            )
        )

    def test_waypoint_stop_and_reversal_preserve_first_crossing(self):
        first = {"x": 0, "y": 0, "width": 0, "height": 0}
        second = {"x": 2, "y": 0, "width": 0, "height": 0}
        crossing = first_relative_circle_crossing(
            first, second, [(1, 0)], [(2.5, 0), (2.5, 0), (10, 0)], 1, 1, 3, 5, True
        )
        self.assertAlmostEqual(crossing["delay_seconds"], 2)
        self.assertFalse(crossing["inside_after"])

    def test_runtime_contact_hint_changes_isolation_at_boundary(self):
        actors, _, duke = runtime(self.catalog, [air_ally(x=12)])
        duke.prepare(actors, 0, [])
        delay = duke.first_crossing_delay(
            actors, {"ally": [(20, 10)]}, {"ally": 2}, 0, 0.5
        )
        self.assertAlmostEqual(delay, 0.5)
        actors["ally"]["x"] = 13
        duke.prepare(actors, 0.5, [])
        self.assertTrue(actors["duke"]["_duke_isolated"])
        self.assertIsNone(
            duke.first_crossing_delay(
                actors, {"ally": [(20, 10)]}, {"ally": 2}, 0.5, 0.5
            )
        )

    def test_counter_uses_actual_attacker_and_shared_cooldown(self):
        cannon = synthetic_structure("cannon", x=12, y=10)
        wizard = synthetic_structure("wizard", x=15, y=10)
        actors, _, duke = runtime(self.catalog, [cannon, wizard])
        trace = []
        duke.prepare(actors, 0, trace)
        receipts = attributed_hit(actors, amount=10)
        healing = duke.after_health(actors, receipts, 0, trace)
        self.assertEqual(healing["duke"], 49)
        self.assertEqual(duke.packets[0][2]["target"], "cannon")
        self.assertEqual(duke.packets[0][2]["damage"], 195)
        receipts = attributed_hit(actors, source="wizard", time=0.1)
        self.assertEqual(duke.after_health(actors, receipts, 0.1, trace)["duke"], 0)
        receipts = attributed_hit(actors, source="wizard", time=0.8)
        self.assertEqual(duke.after_health(actors, receipts, 0.8, trace)["duke"], 49)

    def test_protected_frozen_dead_far_and_recursive_sources_do_not_counter(self):
        for case in (
            "protected",
            "frozen",
            "dead_source",
            "far",
            "recursive",
            "dead_duke",
        ):
            with self.subTest(case=case):
                actors, _, duke = runtime(
                    self.catalog, [synthetic_structure("cannon", x=12, y=10)]
                )
                if case == "protected":
                    actors["duke"]["immune_until"] = 1
                if case == "frozen":
                    actors["duke"]["frozen_until"] = 1
                if case == "far":
                    actors["cannon"]["x"] = 40
                if case == "dead_duke":
                    actors["duke"]["hp"] = 1
                receipts = attributed_hit(
                    actors,
                    origin="revenge_counter" if case == "recursive" else "weapon",
                )
                if case == "dead_source":
                    actors["cannon"]["hp"] = 0
                self.assertEqual(duke.after_health(actors, receipts, 0, [])["duke"], 0)
                self.assertFalse(
                    any(
                        packet[2]["kind"] == "revenge_counter"
                        for packet in duke.packets
                    )
                )

    def test_released_counter_survives_duke_death_and_respects_target_protection(self):
        for protected in (False, True):
            actors, _, duke = runtime(
                self.catalog, [synthetic_structure("cannon", x=12, y=10)]
            )
            duke.after_health(actors, attributed_hit(actors), 0, [])
            actors["duke"].update(hp=0, death_time=0.01)
            if protected:
                actors["cannon"]["immune_until"] = 2
            damage, _ = duke.resolve(actors, 1, [])
            self.assertEqual(damage["cannon"], 0 if protected else 195)

    def test_heart_heals_on_its_clock_while_frozen_and_not_before_release(self):
        actors, _, duke = runtime(self.catalog)
        actors["duke"]["spawn_seconds"] = "controlled"
        duke.prepare(actors, 0, [])
        self.assertIsNone(duke.heal_next["duke"])
        actors["duke"].update(spawn_seconds=2, frozen_until=4)
        duke.prepare(actors, 2, [])
        self.assertEqual(duke.next_boundary(2), 2.5)
        self.assertEqual(duke.resolve(actors, 2.49, [])[1]["duke"], 0)
        self.assertEqual(duke.resolve(actors, 2.5, [])[1]["duke"], 87.5)
        self.assertEqual(duke.next_boundary(2.5), 3)

    def test_heart_death_position_protection_collateral_and_no_double_release(self):
        targets = [
            synthetic_structure("near", x=13, y=10, hitpoints=5000),
            synthetic_structure("far", x=20, y=10, hitpoints=5000),
            synthetic_structure("immune", x=10, y=13, hitpoints=5000),
            synthetic_unit("defender", team="defense", x=10, y=11, hitpoints=5000),
        ]
        actors, _, duke = runtime(self.catalog, targets)
        actors["duke"]["attack_model"]["defending_unit_collateral_policy"] = "ignore"
        actors["immune"]["immune_until"] = 2
        actors["duke"].update(hp=0, death_time=1)
        duke.after_health(actors, [], 1, [])
        duke.after_health(actors, [], 1, [])
        self.assertEqual(len(duke.packets), 1)
        actors["duke"]["x"] = 25
        damage, _ = duke.resolve(actors, 1.2, [])
        self.assertEqual(damage["near"], 3000)
        self.assertEqual(damage["far"], 0)
        self.assertEqual(damage["immune"], 0)
        self.assertEqual(damage["defender"], 0)

    def test_phoenix_interception_defers_heart_but_final_defeat_triggers(self):
        actors, _, duke = runtime(self.catalog)
        actors["duke"].update(hp=1, death_time=None)
        duke.after_health(actors, [], 1, [])
        self.assertEqual(len(duke.packets), 0)
        actors["duke"].update(hp=0, death_time=9)
        duke.after_health(actors, [], 9, [])
        self.assertEqual(len(duke.packets), 1)
        self.assertAlmostEqual(duke.packets[0][0], 9.2)

    def test_physical_removal_does_not_release_heart(self):
        actors, _, duke = runtime(self.catalog)
        actors["duke"].update(hp=0, death_time=None, removal={"reason": "ejected"})
        duke.after_health(actors, [], 1, [])
        self.assertEqual(len(duke.packets), 0)


if __name__ == "__main__":
    unittest.main()
