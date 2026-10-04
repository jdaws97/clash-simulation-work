"""Reactive tower modes, recharge, field membership and released-payload checks."""

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.buffs import BuffCombat, damage_multiplier
from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError
from clashlab.hazards import PulsedHazards
from clashlab.spatial import _apply_health, _load_actors, center
from clashlab.spell_towers import (
    SpellTowerCombat,
    compile_spell_tower,
    validate_spell_tower_model,
)

from test_adapters import entity_instance
from test_combat import synthetic_pattern
from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "explicit-reactive-spell-tower-fixture-not-client-calibration"
CLASSES = ["troop", "hero", "pet", "siege", "other"]


def tower_parameters(mode="rage"):
    effect = {
        "radius_multiplier": 1,
        "duration_multiplier": 1,
        "membership_policy": (
            "pulsed_damage_continuous_status_with_explicit_linger"
            if mode == "poison"
            else "continuous_inside_field_no_linger"
        ),
    }
    if mode == "rage":
        effect.update(
            damage_bonus_multiplier=1,
            stacking_policy="strongest_tower_bonus",
            other_rage_policy="multiply_with_other_sources",
            statistic_basis="snapshot_damageIncrease_is_bonus_percent_flat_weapons_only",
        )
    elif mode == "poison":
        effect.update(
            statistic_basis="snapshot_maxDps_and_slow_percentages",
            damage_multiplier=1,
            pulse_interval_seconds=0.5,
            first_pulse_offset_seconds=0,
            growth_by_field_age=[{"after_seconds": 0, "dps_multiplier": 1}],
            exit_linger_seconds=0.25,
            protection_policy="damage_immunity_does_not_block_status",
            excluded_classes=["siege"],
            stacking_policy="additive_damage_strongest_slow",
        )
    else:
        effect.update(
            acquisition_policy="block_primary_and_chain_acquisition_released_damage_continues",
            stacking_policy="union_of_live_fields",
            immunity_policy="does_not_grant_damage_immunity",
        )
    return {
        "source": SOURCE,
        "arming_seconds": 0,
        "trigger": {
            "policy": (
                "new_positive_allied_structure_damage"
                if mode == "invisibility"
                else "continuous_enemy_presence"
            ),
            "radius_multiplier": 1,
            "unit_classes": list(CLASSES),
            "target_layers": ["ground", "air"],
            "excluded_entities": [],
            "damage_scope": (
                "aggregate_actual_damage_without_source_attribution"
                if mode == "invisibility"
                else "not_applicable"
            ),
            "visibility_policy": "exclude_untargetable_enemies",
        },
        "cast": {
            "delay_seconds": 1.2,
            "targeting_policy": (
                "nearest_damaged_structure_then_id"
                if mode == "invisibility"
                else "nearest_enemy_center_then_id"
            ),
            "aim_policy": (
                "trigger_center_at_launch" if mode == "poison" else "source_center"
            ),
            "projectile_speed_tiles_per_second": None,
            "impact_delay_seconds": 0,
            "freeze_policy": "cancel_cast_and_retain_charge",
            "pending_trigger_policy": (
                "latched_damage_event"
                if mode == "invisibility"
                else "same_enemy_alive_visible_in_range"
            ),
        },
        "recharge": {"clock": "launch", "duration_multiplier": 1},
        "death": {
            "policy": "release_if_ready_at_death",
            "delay_seconds": 0,
            "frozen_policy": "release",
            "aim_policy": "source_center",
            "pending_cast_policy": "cancel_unlaunched_cast",
            "released_payload_policy": "persist_independent_of_source",
        },
        "recipients": {
            "target_kinds": (
                ["unit"] if mode == "poison" else ["defense", "building", "unit"]
            ),
            "target_layers": ["ground", "air"],
            "unit_classes": list(CLASSES),
            "excluded_entities": [],
            "geometry": "footprint_intersects_radius",
            "include_source": True,
        },
        "effect": effect,
    }


def spell_tower_instance(mode="rage", **changes):
    instance = entity_instance(
        "spell-tower",
        "spell-tower",
        3,
        "defense",
        mode=mode,
        statistics_mode="mode",
        x=6,
        y=4,
        attack_parameters={},
        spell_tower_parameters=tower_parameters(mode),
    )
    instance.update(changes)
    return instance


def tower_actor(catalog, instance):
    row = catalog.level("spell-tower", instance["level"])
    actor = synthetic_structure(
        instance["id"],
        source=catalog.records["spell-tower"]["source"],
        x=instance["x"],
        y=instance["y"],
        hitpoints=row["hitpoints"],
        minimum_range=0,
        entity_adapter={
            "entity": "spell-tower",
            "level": instance["level"],
            "modifiers": deepcopy(instance["modifiers"]),
        },
    )
    return compile_spell_tower(
        actor, instance, catalog.entity("spell-tower"), row, instance["modifiers"]
    )


def target_unit(actor_id="attacker", **changes):
    actor = synthetic_unit(
        actor_id,
        x=12.5,
        y=5.5,
        hitpoints=1000,
        buff_class="troop",
        hazard_class="troop",
        minimum_range=0,
        attack_model=synthetic_pattern(),
    )
    actor.update(changes)
    return actor


def defender(actor_id="cannon", **changes):
    actor = synthetic_structure(
        actor_id,
        x=9,
        y=4,
        width=2,
        height=2,
        hitpoints=1000,
        damage=100,
        range=9,
        minimum_range=0,
        attack_model=synthetic_pattern(),
    )
    actor.update(changes)
    return actor


class SpellTowerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def runtime(self, mode="rage", instance=None, others=None):
        tower = tower_actor(
            self.catalog, spell_tower_instance(mode) if instance is None else instance
        )
        members = [target_unit(), defender()] if others is None else others
        actors = _load_actors({"actors": [tower, *members]}, 30, 24)
        hazards = PulsedHazards(actors, [])
        return actors, hazards, SpellTowerCombat(actors, hazards)

    def test_catalog_quantities_are_selected_per_mode_without_hp_level_scaling(self):
        for mode, duration, recharge in (
            ("rage", 18, 70),
            ("poison", 12, 70),
            ("invisibility", 4.5, 50),
        ):
            with self.subTest(mode=mode):
                instance = spell_tower_instance(mode)
                actor = tower_actor(self.catalog, instance)
                model = actor["spell_tower_model"]
                self.assertEqual(model["effect"]["duration_seconds"], duration)
                self.assertEqual(model["recharge"]["duration_seconds"], recharge)
                self.assertEqual(actor["hitpoints"], 3100)
                self.assertEqual(actor["damage"], 0)
                self.assertEqual(actor["attack_model"]["kind"], "none")
                self.assertEqual(actor["target_priorities"], [])
        rage = tower_actor(self.catalog, spell_tower_instance())["spell_tower_model"]
        self.assertEqual(rage["effect"]["damage_bonus_fraction"], 0.6)
        poison = tower_actor(self.catalog, spell_tower_instance("poison"))[
            "spell_tower_model"
        ]
        self.assertEqual(poison["effect"]["maximum_dps"], 60)
        self.assertEqual(poison["effect"]["movement_multiplier"], 0.65)
        self.assertEqual(poison["effect"]["attack_rate_multiplier"], 0.75)

    def test_locked_modes_earthquake_and_missing_behavior_are_rejected(self):
        for mode, level in (("poison", 1), ("invisibility", 2), ("earthquake", 4)):
            with self.subTest(mode=mode), self.assertRaises(InputError):
                tower_actor(self.catalog, spell_tower_instance(mode, level=level))
        instance = spell_tower_instance()
        del instance["spell_tower_parameters"]["death"]
        with self.assertRaisesRegex(InputError, "every explicit"):
            tower_actor(self.catalog, instance)
        instance = spell_tower_instance()
        instance["modifiers"]["damage_multiplier"] = 1.2
        with self.assertRaisesRegex(InputError, "non-HP actor modifiers"):
            tower_actor(self.catalog, instance)

    def test_rage_waits_for_cast_and_rearms_at_explicit_catalog_clock(self):
        actors, _, towers = self.runtime()
        trace = []
        self.assertFalse(towers.prepare(actors, 0, trace))
        self.assertEqual(towers.next_boundary(0), 1.2)
        self.assertTrue(towers.prepare(actors, 1.2, trace))
        self.assertEqual(damage_multiplier(actors["cannon"]), 1.6)
        self.assertEqual(damage_multiplier(actors["attacker"]), 1)
        self.assertEqual(towers.states["spell-tower"]["ready_at"], 71.2)
        self.assertEqual(towers.next_boundary(1.2), 19.2)
        towers.prepare(actors, 19.2, trace)
        self.assertEqual(damage_multiplier(actors["cannon"]), 1)
        towers.prepare(actors, 71.2, trace)
        self.assertEqual(towers.states["spell-tower"]["phase"], "casting")
        towers.prepare(actors, 72.4, trace)
        self.assertEqual(towers.states["spell-tower"]["launched_count"], 2)
        self.assertEqual(towers.states["spell-tower"]["released_count"], 2)

    def test_departure_and_invisibility_cancel_pending_presence_cast(self):
        for change in ("outside", "invisible", "dead"):
            with self.subTest(change=change):
                actors, _, towers = self.runtime()
                trace = []
                towers.prepare(actors, 0, trace)
                target = actors["attacker"]
                if change == "outside":
                    target["x"] = 25
                elif change == "invisible":
                    target["_untargetable_until"] = 5
                else:
                    target.update(hp=0, death_time=0.5)
                towers.prepare(actors, 0.5, trace)
                towers.prepare(actors, 1.2, trace)
                self.assertEqual(towers.states["spell-tower"]["phase"], "armed")
                self.assertFalse(towers.fields)
                self.assertEqual(towers.states["spell-tower"]["ready_at"], 0)

    def test_freeze_cancels_cast_but_recharge_is_a_wall_clock(self):
        actors, _, towers = self.runtime()
        trace = []
        towers.prepare(actors, 0, trace)
        actors["spell-tower"]["frozen_until"] = 4
        towers.prepare(actors, 0.5, trace)
        self.assertEqual(towers.states["spell-tower"]["phase"], "armed")
        towers.prepare(actors, 4, trace)
        towers.prepare(actors, 5.2, trace)
        self.assertEqual(towers.states["spell-tower"]["ready_at"], 75.2)
        actors["spell-tower"]["frozen_until"] = 80
        towers.prepare(actors, 75.2, trace)
        self.assertEqual(towers.states["spell-tower"]["launched_count"], 1)
        towers.prepare(actors, 80, trace)
        self.assertEqual(towers.states["spell-tower"]["launch_at"], 81.2)

    def test_poison_aims_at_launch_then_survives_source_and_target_changes(self):
        instance = spell_tower_instance("poison")
        instance["spell_tower_parameters"]["cast"][
            "projectile_speed_tiles_per_second"
        ] = 2
        instance["spell_tower_parameters"]["recharge"]["clock"] = "field_release"
        actors, hazards, towers = self.runtime(instance=instance)
        trace = []
        towers.prepare(actors, 0, trace)
        actors["attacker"]["x"] = 11
        towers.prepare(actors, 1.2, trace)
        packet = towers.pending[0][2]
        expected_point = center(actors["attacker"])
        self.assertEqual(packet["position"], expected_point)
        release = packet["start_seconds"]
        self.assertAlmostEqual(towers.states["spell-tower"]["ready_at"], release + 70)
        actors["spell-tower"].update(hp=0, death_time=1.3)
        actors["attacker"].update(x=25, hp=0, death_time=1.3)
        towers.prepare(actors, 1.3, trace)
        self.assertEqual(len(towers.pending), 1)
        towers.prepare(actors, release, trace)
        field = hazards.fields[packet["id"]]
        self.assertEqual((field["area"]["x"], field["area"]["y"]), expected_point)
        self.assertEqual(towers.states["spell-tower"]["released_count"], 1)

    def test_poison_uses_shared_damage_and_status_with_protection(self):
        actors, hazards, towers = self.runtime("poison")
        trace = []
        towers.prepare(actors, 0, trace)
        towers.prepare(actors, 1.2, trace)
        hazards.prepare_status(actors, 1.2, trace)
        self.assertEqual(actors["attacker"]["_hazard_movement_multiplier"], 0.65)
        self.assertEqual(actors["attacker"]["_hazard_attack_rate"], 0.75)
        damage = hazards.resolve(actors, 1.2, trace)
        self.assertEqual(damage["attacker"], 30)
        _apply_health(actors, damage, defaultdict(float), 1.2)
        self.assertEqual(actors["attacker"]["hp"], 970)
        actors["attacker"]["immune_until"] = 5
        self.assertEqual(hazards.resolve(actors, 1.7, trace)["attacker"], 0)
        hazards.prepare_status(actors, 1.7, trace)
        self.assertEqual(actors["attacker"]["_hazard_attack_rate"], 0.75)

    def test_invisibility_requires_new_damage_and_preserves_damage_immunity(self):
        actors, _, towers = self.runtime("invisibility")
        trace = []
        towers.prepare(actors, 0, trace)
        self.assertEqual(towers.states["spell-tower"]["phase"], "armed")
        actors["cannon"]["_received_damage"] = 10
        towers.prepare(actors, 0.5, trace)
        self.assertEqual(towers.states["spell-tower"]["trigger_id"], "cannon")
        towers.prepare(actors, 1.7, trace)
        self.assertEqual(actors["cannon"]["_spell_tower_untargetable_until"], 6.2)
        self.assertEqual(actors["cannon"]["immune_until"], 0)
        self.assertEqual(actors["attacker"]["_spell_tower_untargetable_until"], 0)
        towers.prepare(actors, 6.2, trace)
        self.assertEqual(actors["cannon"]["_spell_tower_untargetable_until"], 0)
        towers.prepare(actors, 51.7, trace)
        self.assertEqual(towers.states["spell-tower"]["phase"], "armed")
        actors["cannon"]["_received_damage"] = 20
        towers.prepare(actors, 52, trace)
        self.assertEqual(towers.states["spell-tower"]["phase"], "casting")

    def test_invisible_targets_still_receive_already_launched_damage(self):
        actors, _, towers = self.runtime("invisibility")
        combat = PatternCombat(actors)
        trace = []
        actors["cannon"]["_received_damage"] = 10
        towers.prepare(actors, 0, trace)
        combat.launch(actors["attacker"], actors["cannon"], actors, 0, trace)
        towers.prepare(actors, 1.2, trace)
        self.assertGreater(actors["cannon"]["_spell_tower_untargetable_until"], 1.2)
        damage = combat.resolve(actors, 1.2, trace)
        self.assertEqual(damage["cannon"], 100)

    def test_death_release_is_once_and_ready_only_policy_respects_spent_charge(self):
        for launched in (False, True):
            with self.subTest(launched=launched):
                actors, _, towers = self.runtime()
                trace = []
                towers.prepare(actors, 0, trace)
                if launched:
                    towers.prepare(actors, 1.2, trace)
                actors["spell-tower"].update(hp=0, death_time=1.3)
                towers.prepare(actors, 1.3, trace)
                towers.prepare(actors, 1.3, trace)
                state = towers.states["spell-tower"]
                self.assertEqual(state["launched_count"], 1)
                self.assertEqual(state["released_count"], 1)
                self.assertEqual(state["death_release_queued"], not launched)
                self.assertEqual(state["phase"], "destroyed")

    def test_death_release_policy_can_be_unconditional_delayed_or_suppressed(self):
        for policy, frozen, expected in (
            ("release_once_regardless_of_recharge", False, 2),
            ("none", False, 1),
            ("release_once_regardless_of_recharge", True, 1),
        ):
            instance = spell_tower_instance()
            instance["spell_tower_parameters"]["death"].update(
                policy=policy, delay_seconds=0.5, frozen_policy="suppress"
            )
            actors, _, towers = self.runtime(instance=instance)
            towers.prepare(actors, 0, [])
            towers.prepare(actors, 1.2, [])
            actors["spell-tower"].update(
                hp=0, death_time=2, frozen_until=5 if frozen else 0
            )
            towers.prepare(actors, 2, [])
            towers.prepare(actors, 2.5, [])
            self.assertEqual(towers.states["spell-tower"]["released_count"], expected)

    def test_strongest_tower_rage_and_explicit_other_source_composition(self):
        actors, hazards, _ = self.runtime()
        second = tower_actor(self.catalog, spell_tower_instance(id="second", x=6, y=8))
        second["spell_tower_model"]["effect"]["damage_bonus_fraction"] = 0.3
        second = _load_actors({"actors": [second]}, 30, 24)["second"]
        actors["second"] = second
        towers = SpellTowerCombat(actors, hazards)
        towers.prepare(actors, 0, [])
        towers.prepare(actors, 1.2, [])
        self.assertEqual(actors["cannon"]["_spell_tower_damage_multiplier"], 1.6)
        actors["cannon"]["_buff_damage_multiplier"] = 2
        self.assertEqual(damage_multiplier(actors["cannon"]), 3.2)
        actors["cannon"][
            "_spell_tower_rage_composition"
        ] = "strongest_with_other_sources"
        self.assertEqual(damage_multiplier(actors["cannon"]), 2)

    def test_tower_rage_does_not_create_spurious_buff_status_changes(self):
        actors, _, towers = self.runtime()
        ordinary = BuffCombat(actors, [])
        towers.prepare(actors, 0, [])
        towers.prepare(actors, 1.2, [])
        trace = []
        ordinary.prepare(actors, 1.2, trace)
        ordinary.prepare(actors, 1.3, trace)
        self.assertFalse(
            [event for event in trace if event["event"] == "buff_status_change"]
        )
        self.assertEqual(damage_multiplier(actors["cannon"]), 1.6)

    def test_invisibility_overlaps_without_clobbering_hero_or_tesla_flags(self):
        actors, _, towers = self.runtime("invisibility")
        actors["cannon"]["_untargetable_until"] = 20
        actors["cannon"]["_received_damage"] = 10
        towers.prepare(actors, 0, [])
        towers.prepare(actors, 1.2, [])
        towers.prepare(actors, 5.7, [])
        self.assertEqual(actors["cannon"]["_spell_tower_untargetable_until"], 0)
        self.assertEqual(actors["cannon"]["_untargetable_until"], 20)

    def test_geometry_and_exclusions_are_explicit(self):
        for geometry, expected in (
            ("center_in_radius", 1),
            ("footprint_intersects_radius", 1.6),
        ):
            instance = spell_tower_instance()
            instance["spell_tower_parameters"]["recipients"]["geometry"] = geometry
            actors, _, towers = self.runtime(
                instance=instance, others=[target_unit(), defender(x=11, y=4, width=4)]
            )
            towers.prepare(actors, 0, [])
            towers.prepare(actors, 1.2, [])
            self.assertEqual(damage_multiplier(actors["cannon"]), expected)
        instance = spell_tower_instance("invisibility")
        instance["spell_tower_parameters"]["recipients"]["include_source"] = False
        actors, _, towers = self.runtime(instance=instance)
        actors["cannon"]["_received_damage"] = 10
        towers.prepare(actors, 0, [])
        towers.prepare(actors, 1.2, [])
        self.assertEqual(actors["spell-tower"]["_spell_tower_untargetable_until"], 0)
        self.assertGreater(actors["cannon"]["_spell_tower_untargetable_until"], 0)

    def test_exact_trigger_entry_exit_and_forced_motion_crossings(self):
        actors, _, towers = self.runtime(others=[target_unit(x=20, y=5), defender()])
        unit = actors["attacker"]
        unit["frozen_until"] = 5
        delay = towers.first_crossing_delay(unit, [(10, 5)], 0, 10, 2)
        self.assertEqual(delay, 2)
        unit["x"] = 16
        towers.prepare(actors, 2, [])
        self.assertEqual(towers.states["spell-tower"]["phase"], "casting")
        unit["x"] = 15
        towers.prepare(actors, 2.5, [])
        delay = towers.first_crossing_delay(unit, [(20, 5)], 2.5, 5, 2)
        self.assertEqual(delay, 0.5)
        unit["x"] = 16
        towers.prepare(actors, 3, [])
        self.assertEqual(towers.states["spell-tower"]["phase"], "armed")
        self.assertIsNone(towers.first_crossing_delay(unit, [(20, 5)], 3, 5, 2))

    def test_runtime_model_and_hazard_validation_reject_inconsistent_inputs(self):
        actor = tower_actor(self.catalog, spell_tower_instance())
        actor["damage"] = 1
        with self.assertRaisesRegex(InputError, "without a weapon"):
            validate_spell_tower_model(actor)
        instance = spell_tower_instance("poison")
        instance["spell_tower_parameters"]["effect"]["growth_by_field_age"] = []
        with self.assertRaisesRegex(InputError, "growth curve"):
            self.runtime(instance=instance)
        actors, _, towers = self.runtime()
        towers.prepare(actors, 2, [])
        with self.assertRaisesRegex(InputError, "backward"):
            towers.prepare(actors, 1, [])

    def test_polyline_touch_and_turn_inside_does_not_cancel_cast(self):
        actors, _, towers = self.runtime(others=[target_unit(x=15, y=5), defender()])
        towers.prepare(actors, 0, [])
        crossing = towers.first_crossing_delay(
            actors["attacker"], [(16, 5), (15, 5)], 0, 5, 2
        )
        self.assertIsNone(crossing)
        self.assertEqual(towers.states["spell-tower"]["phase"], "casting")

    def test_poison_exit_reaches_shared_hazard_membership_without_large_step_delay(
        self,
    ):
        actors, hazards, towers = self.runtime("poison")
        towers.prepare(actors, 0, [])
        towers.prepare(actors, 1.2, [])
        unit = actors["attacker"]
        delay = towers.first_crossing_delay(unit, [(22.5, 5.5)], 1.2, 10, 2)
        self.assertEqual(delay, 2.5)
        unit["x"] = 17.5
        towers.prepare(actors, 3.7, [])
        hazards.prepare_status(actors, 3.7, [])
        departure = towers.first_crossing_delay(unit, [(22.5, 5.5)], 3.7, 1, 2)
        self.assertGreater(departure, 0)
        self.assertLess(departure, 0.000001)
        unit["x"] += departure * 2
        towers.prepare(actors, 3.7 + departure, [])
        hazards.prepare_status(actors, 3.7 + departure, [])
        field_id = next(iter(hazards.fields))
        self.assertFalse(hazards.previous_membership[field_id, "attacker"])

    def test_invisibility_moving_defender_leaves_field_without_losing_other_cloak(self):
        ally = target_unit(
            "defender",
            team="defense",
            x=10.5,
            y=5,
            hazard_class="hero",
            buff_class="hero",
        )
        actors, _, towers = self.runtime(
            "invisibility", others=[target_unit(), defender(), ally]
        )
        actors["cannon"]["_received_damage"] = 10
        actors["defender"]["_untargetable_until"] = 20
        towers.prepare(actors, 0, [])
        towers.prepare(actors, 1.2, [])
        ally = actors["defender"]
        self.assertGreater(ally["_spell_tower_untargetable_until"], 1.2)
        delay = towers.first_crossing_delay(ally, [(15, 5)], 1.2, 5, 2)
        self.assertEqual(delay, 0.5)
        ally["x"] = 11.5
        towers.prepare(actors, 1.7, [])
        self.assertEqual(ally["_spell_tower_untargetable_until"], 0)
        self.assertEqual(ally["_untargetable_until"], 20)

    def test_inconsistent_rage_composition_is_rejected(self):
        actors, hazards, _ = self.runtime()
        second = tower_actor(self.catalog, spell_tower_instance(id="second", x=6, y=8))
        second["spell_tower_model"]["effect"][
            "other_rage_policy"
        ] = "strongest_with_other_sources"
        actors["second"] = _load_actors({"actors": [second]}, 30, 24)["second"]
        with self.assertRaisesRegex(InputError, "same other-source composition"):
            SpellTowerCombat(actors, hazards)

    def test_rage_boost_is_captured_once_for_flat_damage_without_scaling_hp_bonus(self):
        actors, _, towers = self.runtime()
        actors["cannon"]["attack_model"]["maximum_hp_fraction"] = 0.1
        combat = PatternCombat(actors)
        towers.prepare(actors, 0, [])
        towers.prepare(actors, 1.2, [])
        combat.launch(actors["cannon"], actors["attacker"], actors, 1.2, [])
        towers.prepare(actors, 19.2, [])
        self.assertEqual(damage_multiplier(actors["cannon"]), 1)
        self.assertEqual(combat.resolve(actors, 19.2, [])["attacker"], 260)
        combat.launch(actors["cannon"], actors["attacker"], actors, 19.2, [])
        self.assertEqual(combat.resolve(actors, 19.2, [])["attacker"], 200)

    def test_overlapping_invisibility_remains_until_last_field_expires(self):
        actors, hazards, _ = self.runtime("invisibility")
        actors["spell-tower"]["spell_tower_model"]["effect"]["duration_seconds"] = 1
        second = tower_actor(
            self.catalog, spell_tower_instance("invisibility", id="second", x=8, y=6)
        )
        actors["second"] = _load_actors({"actors": [second]}, 30, 24)["second"]
        towers = SpellTowerCombat(actors, hazards)
        actors["cannon"]["_received_damage"] = 10
        towers.prepare(actors, 0, [])
        towers.prepare(actors, 1.2, [])
        self.assertEqual(actors["cannon"]["_spell_tower_untargetable_until"], 5.7)
        towers.prepare(actors, 2.2, [])
        self.assertEqual(actors["cannon"]["_spell_tower_untargetable_until"], 5.7)
        towers.prepare(actors, 5.7, [])
        self.assertEqual(actors["cannon"]["_spell_tower_untargetable_until"], 0)


if __name__ == "__main__":
    unittest.main()
