"""Declared spell quantities, independent clocks, recipients, and continuation."""

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.attack_spell_models import (
    ACQUISITION_POLICY,
    COLLISION_POLICY,
    STACKING_POLICY,
    compile_attack_spell,
    poison_fields,
    validate_spell_classifications,
)
from clashlab.attack_spells import AttackSpellCombat
from clashlab.battle_continuation import hazard_continuation
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.hazards import HAZARD_CLASSES, PulsedHazards
from clashlab.spatial import _apply_effects, _apply_health, _blocked, _load_actors
from clashlab.spell_visibility import untargetable_until

from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "explicit-attacking-spell-fixture-not-replay-calibrated"


def repeat_parameters(casts=8):
    return {
        "counter_scope": "shared_per_target_across_owned_and_received_earthquake_spells",
        "protected_hits": "do_not_advance_counter",
        "building_multipliers": [1 / (2 * index + 1) for index in range(casts)],
        "unit_multipliers": [1 / (2 * index + 1) for index in range(casts)],
        "wall_damage_multipliers": [1, 2, 3],
        "wall_combo": "catalog_four_counted_quakes_destroy_wall",
        "structure_hp_floor": 1,
        "unit_hp_floor": 0,
        "simultaneous_order": "arrival_then_cast_id_with_sequential_virtual_hp",
    }


def spell_parameters(entity):
    parameters = {
        "source": SOURCE,
        "caster_team": "attack",
        "radius_multiplier": 1,
        "impact_delay_seconds": 0,
        "geometry": "point_to_live_target_footprint",
        "hidden_tesla_policy": "exclude_hidden_teslas",
        "source_persistence": "released_cast_independent_of_attacker_survival",
    }
    if entity in {"lightning-spell", "earthquake-spell"}:
        parameters.update(
            damage_multiplier=1,
            excluded_entities=["gold-storage", "elixir-storage", "dark-elixir-storage"],
            unit_damage_multipliers={key: 1 for key in HAZARD_CLASSES},
        )
        if entity == "lightning-spell":
            parameters["excluded_entities"].append("clan-castle")
            parameters.update(
                damage_basis="snapshot_damage_is_one_total_impact",
                stun_basis="snapshot_stunTime_pauses_remaining_attack_work",
                stun_multiplier=1,
                status_protection="damage_immunity_does_not_block_status",
            )
        else:
            parameters.update(
                building_damage_basis="snapshot_buildingDamagePercent_of_maximum_hp",
                unit_damage_basis="snapshot_troopDamagePercent_of_maximum_hp_ground_only",
                missing_unit_damage_percent=None,
                repeated_hits=repeat_parameters(),
            )
    else:
        parameters.update(
            duration_basis="snapshot_spellDuration", duration_multiplier=1
        )
        if entity == "poison-spell":
            parameters.update(
                damage_basis="snapshot_maxDamagePerSecond_is_maximum_dps",
                damage_multiplier=1,
                pulse_interval_seconds=0.5,
                first_pulse_offset_seconds=0,
                growth_clock="explicit_field_age_hypothesis",
                growth_by_field_age=[
                    {"after_seconds": 0, "dps_multiplier": 0.25},
                    {"after_seconds": 1, "dps_multiplier": 1},
                ],
                exit_linger_seconds=0.25,
                status_protection="damage_immunity_does_not_block_status",
                class_scaling={
                    key: {
                        "damage_multiplier": 1,
                        "movement_reduction_multiplier": 1,
                        "attack_rate_reduction_multiplier": 1,
                    }
                    for key in HAZARD_CLASSES
                },
                stacking_policy="additive_damage_strongest_slow_across_shared_hazards",
                inactive_unit_policy="no_damage_or_status_while_inactive_or_underground",
            )
            parameters["class_scaling"]["guardian"].update(
                damage_multiplier=0.3,
                movement_reduction_multiplier=0.7,
                attack_rate_reduction_multiplier=0.7,
            )
        else:
            parameters.update(
                acquisition_policy=ACQUISITION_POLICY,
                collision_policy=COLLISION_POLICY,
                stacking_policy=STACKING_POLICY,
            )
            if entity == "invisibility-spell":
                parameters.update(
                    membership_policy="continuous_live_membership_no_linger",
                    recipient_policy="both_teams_except_walls_and_siege",
                    immunity_policy="acquisition_only_no_damage_immunity",
                )
            else:
                parameters.update(
                    membership_policy="capture_live_structures_at_arrival",
                    recipient_policy="defending_buildings_and_defenses_excluding_walls_and_units",
                    immunity_policy="full_damage_immunity_for_captured_structures",
                    disable_policy="freeze_shared_weapon_work_released_attacks_persist",
                    garrison_release_policy="garrison_release_continues_without_overgrowth_pause",
                    guardian_activation_policy="dormant_guardian_activation_continues",
                    builder_policy="reuse_explicit_hut_freeze_linkage",
                    trap_policy="traps_unaffected",
                )
    return parameters


def spell_instance(entity="lightning-spell", **changes):
    instance = {
        "id": entity,
        "entity": entity,
        "level": 7 if entity == "earthquake-spell" else 1,
        "town_hall": 18,
        "time_seconds": 0,
        "x": 10,
        "y": 10,
        "parameters": spell_parameters(entity),
    }
    instance.update(changes)
    return instance


def unit(actor_id="unit", **changes):
    return synthetic_unit(
        actor_id,
        **{
            "team": "defense",
            "x": 12,
            "y": 10,
            "hitpoints": 10000,
            "hazard_class": "defending_troop",
            **changes,
        },
    )


def building(actor_id="building", **changes):
    return synthetic_structure(
        actor_id,
        **{
            "x": 8,
            "y": 9,
            "width": 2,
            "height": 2,
            "hitpoints": 10000,
            "kind": "building",
            "first_attack_seconds": 1,
            "entity_adapter": {"entity": "barracks"},
            **changes,
        },
    )


class AttackSpellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def runtime(self, instances=None, actor_specs=None):
        models = [
            compile_attack_spell(instance, self.catalog)
            for instance in (instances or [spell_instance()])
        ]
        actors = _load_actors({"actors": actor_specs or [building(), unit()]}, 40, 30)
        hazards = PulsedHazards(actors, [])
        runtime = AttackSpellCombat(models, actors, hazards)
        return actors, runtime, hazards, []

    def step(self, actors, runtime, hazards, trace, time):
        runtime.prepare(actors, time, trace)
        _apply_health(
            actors, runtime.resolve(actors, time, trace), defaultdict(float), time
        )
        hazards.prepare_status(actors, time, trace)
        _apply_health(
            actors, hazards.resolve(actors, time, trace), defaultdict(float), time
        )

    def test_compilers_bind_each_distinct_catalog_quantity(self):
        lightning = compile_attack_spell(spell_instance(level=13), self.catalog)
        self.assertEqual(lightning["quantities"], {"damage": 720, "stun_seconds": 0.1})
        self.assertEqual(lightning["radius"], 2)
        quake = compile_attack_spell(
            spell_instance("earthquake-spell", level=8), self.catalog
        )
        self.assertEqual(
            quake["quantities"], {"building_fraction": 0.29, "unit_fraction": 0.145}
        )
        self.assertEqual(quake["radius"], 4.7)
        poison = compile_attack_spell(
            spell_instance("poison-spell", level=12), self.catalog
        )
        self.assertEqual(
            poison["quantities"],
            {
                "duration_seconds": 16,
                "maximum_dps": 380,
                "movement_reduction": 0.52,
                "attack_rate_reduction": 0.74,
            },
        )
        invisible = compile_attack_spell(
            spell_instance("invisibility-spell", level=4), self.catalog
        )
        overgrown = compile_attack_spell(
            spell_instance("overgrowth-spell", level=5), self.catalog
        )
        self.assertEqual(invisible["quantities"]["duration_seconds"], 4.25)
        self.assertEqual(overgrown["quantities"]["duration_seconds"], 26)
        self.assertEqual(overgrown["entity_adapter"]["housing_space"], 2)
        self.assertIn(
            "not_used",
            poison["entity_adapter"]["source_audit"]["extraction_duration_zero"],
        )

    def test_unknown_family_level_and_missing_critical_contract_fail_closed(self):
        for entity, field in (
            ("lightning-spell", "excluded_entities"),
            ("earthquake-spell", "repeated_hits"),
            ("poison-spell", "pulse_interval_seconds"),
            ("poison-spell", "growth_clock"),
            ("invisibility-spell", "collision_policy"),
            ("overgrowth-spell", "garrison_release_policy"),
        ):
            instance = spell_instance(entity)
            del instance["parameters"][field]
            with (
                self.subTest(entity=entity, field=field),
                self.assertRaises(InputError),
            ):
                compile_attack_spell(instance, self.catalog)
        for instance in (
            spell_instance("jump-spell"),
            spell_instance(level=99),
            spell_instance(town_hall=2),
        ):
            with self.assertRaises(InputError):
                compile_attack_spell(instance, self.catalog)

    def test_old_quake_levels_require_numeric_missing_unit_damage_hypothesis(self):
        instance = spell_instance("earthquake-spell", level=1)
        with self.assertRaises(InputError):
            compile_attack_spell(instance, self.catalog)
        instance["parameters"].update(
            unit_damage_basis="explicit_missing_troop_damage_hypothesis_ground_only",
            missing_unit_damage_percent=0,
        )
        model = compile_attack_spell(instance, self.catalog)
        self.assertEqual(model["quantities"]["unit_fraction"], 0)
        instance["parameters"]["missing_unit_damage_percent"] = None
        with self.assertRaisesRegex(InputError, "explicit numeric"):
            compile_attack_spell(instance, self.catalog)

    def test_lightning_is_one_total_hit_stuns_and_respects_explicit_immunities(self):
        actors, runtime, hazards, trace = self.runtime(
            actor_specs=[
                building(),
                unit(),
                unit("friendly", team="attack"),
                building(
                    "storage", x=11, y=8, entity_adapter={"entity": "gold-storage"}
                ),
                building("castle", x=7, y=12, entity_adapter={"entity": "clan-castle"}),
            ]
        )
        self.step(actors, runtime, hazards, trace, 0)
        self.assertEqual(actors["building"]["hp"], 9850)
        self.assertEqual(actors["unit"]["hp"], 9850)
        self.assertEqual(actors["building"]["next_attack"], 1.1)
        for key in ("storage", "castle", "friendly"):
            self.assertEqual(actors[key]["hp"], 10000)
            self.assertEqual(actors[key]["frozen_until"], 0)
        self.step(actors, runtime, hazards, trace, 0.05)
        self.assertEqual(actors["unit"]["hp"], 9850)

    def test_lightning_overlap_freeze_preserves_union_and_protection_is_explicit(self):
        for policy, expected_end in (
            ("damage_immunity_does_not_block_status", 0.25),
            ("damage_immunity_also_blocks_status", 0.2),
        ):
            instance = spell_instance(time_seconds=0.15)
            instance["parameters"]["status_protection"] = policy
            actors, runtime, hazards, trace = self.runtime([instance])
            _apply_effects(
                [
                    {
                        "id": "frozen",
                        "kind": "freeze",
                        "targets": ["building"],
                        "duration_seconds": 0.2,
                    },
                    {
                        "id": "immune",
                        "kind": "invulnerability",
                        "targets": ["building"],
                        "duration_seconds": 1,
                    },
                ],
                actors,
                0,
                trace,
            )
            self.step(actors, runtime, hazards, trace, 0.15)
            self.assertEqual(actors["building"]["hp"], 10000)
            self.assertAlmostEqual(actors["building"]["frozen_until"], expected_end)
            self.assertAlmostEqual(actors["building"]["next_attack"], 1 + expected_end)

    def test_geometry_policy_changes_structure_membership_at_exact_boundary(self):
        for geometry, expected in (
            ("point_to_live_target_footprint", 9850),
            ("live_center_distance", 10000),
        ):
            instance = spell_instance()
            instance["parameters"]["geometry"] = geometry
            actors, runtime, hazards, trace = self.runtime(
                [instance], [building(x=12, y=9), unit(x=20)]
            )
            self.step(actors, runtime, hazards, trace, 0)
            self.assertEqual(actors["building"]["hp"], expected)

    def test_delayed_lightning_selects_live_recipients_and_survives_army_death(self):
        instance = spell_instance()
        instance["parameters"]["impact_delay_seconds"] = 0.5
        actors, runtime, hazards, trace = self.runtime(
            [instance], [building(), unit(), unit("attacker", team="attack", x=20)]
        )
        self.step(actors, runtime, hazards, trace, 0)
        actors["unit"]["x"] = 20
        actors["attacker"].update(hp=0, death_time=0.1)
        self.assertEqual(
            runtime.continuation_reasons(0.1)[0]["not_before_seconds"], 0.5
        )
        self.step(actors, runtime, hazards, trace, 0.5)
        self.assertEqual(actors["building"]["hp"], 9850)
        self.assertEqual(actors["unit"]["hp"], 10000)
        self.assertEqual(runtime.continuation_reasons(0.5), [])

    def test_quake_shared_repeated_counts_use_maximum_hp_and_ground_units_only(self):
        instances = [
            spell_instance("earthquake-spell", id=f"quake-{index}", time_seconds=index)
            for index in range(2)
        ]
        actors, runtime, hazards, trace = self.runtime(
            instances, [building(), unit(), unit("air", layer="air", movement="air")]
        )
        actors["building"]["hp"] = 5000
        self.step(actors, runtime, hazards, trace, 0)
        self.step(actors, runtime, hazards, trace, 1)
        self.assertAlmostEqual(actors["building"]["hp"], 5000 - 2900 - 2900 / 3)
        self.assertAlmostEqual(actors["unit"]["hp"], 10000 - 1000 - 1000 / 3)
        self.assertEqual(actors["air"]["hp"], 10000)
        self.assertEqual(runtime.result()["quake_hits"], {"building": 2, "unit": 2})

    def test_quake_four_wall_hits_and_nonlethal_building_floor(self):
        instances = [
            spell_instance("earthquake-spell", id=f"q-{index}", time_seconds=index)
            for index in range(4)
        ]
        for instance in instances:
            instance["parameters"]["repeated_hits"]["wall_damage_multipliers"] = [
                0.1,
                0.1,
                0.1,
            ]
        actors, runtime, hazards, trace = self.runtime(
            instances,
            [
                building(),
                building(
                    "wall",
                    kind="wall",
                    counts_for_destruction=False,
                    width=1,
                    height=1,
                    x=11,
                    y=9,
                ),
            ],
        )
        actors["building"]["hp"] = 200
        for time in range(3):
            self.step(actors, runtime, hazards, trace, time)
        self.assertEqual(actors["wall"]["hp"], 9130)
        self.assertEqual(actors["building"]["hp"], 1)
        self.step(actors, runtime, hazards, trace, 3)
        self.assertEqual(actors["wall"]["hp"], 0)
        self.assertEqual(actors["wall"]["death_time"], 3)
        self.assertEqual(actors["building"]["hp"], 1)

    def test_quake_same_time_order_and_tables_are_explicit(self):
        first = spell_instance("earthquake-spell", id="a", level=1)
        first["parameters"].update(
            unit_damage_basis="explicit_missing_troop_damage_hypothesis_ground_only",
            missing_unit_damage_percent=0,
        )
        second = spell_instance("earthquake-spell", id="b")
        actors, runtime, hazards, trace = self.runtime([second, first])
        self.step(actors, runtime, hazards, trace, 0)
        self.assertAlmostEqual(actors["building"]["hp"], 10000 - 1450 - 2900 / 3)
        self.assertEqual(actors["unit"]["hp"], 9000)
        first["parameters"]["repeated_hits"]["building_multipliers"] = [1]
        with self.assertRaisesRegex(InputError, "every declared cast"):
            self.runtime([first, second])
        first["parameters"]["repeated_hits"] = repeat_parameters()
        first["parameters"]["repeated_hits"]["unit_hp_floor"] = 1
        with self.assertRaisesRegex(InputError, "same repeated-hit contract"):
            self.runtime([first, second])

    def test_protected_quake_counter_can_advance_or_remain_unchanged(self):
        for policy, expected in (
            ("advance_counter", 10000 - 2900 / 3),
            ("do_not_advance_counter", 7100),
        ):
            instances = [
                spell_instance("earthquake-spell", id=f"q-{index}", time_seconds=index)
                for index in range(2)
            ]
            for instance in instances:
                instance["parameters"]["repeated_hits"]["protected_hits"] = policy
            actors, runtime, hazards, trace = self.runtime(instances)
            actors["building"]["immune_until"] = 0.5
            self.step(actors, runtime, hazards, trace, 0)
            self.step(actors, runtime, hazards, trace, 1)
            self.assertAlmostEqual(actors["building"]["hp"], expected)

    def test_poison_partition_scales_guardian_damage_and_slow_independently_once(self):
        instance = spell_instance("poison-spell", level=10)
        actors, runtime, hazards, trace = self.runtime(
            [instance],
            [
                unit(),
                unit("guardian", hazard_class="guardian"),
                unit("hero", hazard_class="hero"),
            ],
        )
        self.step(actors, runtime, hazards, trace, 0)
        self.assertAlmostEqual(10000 - actors["unit"]["hp"], 340 * 0.25 * 0.5)
        self.assertAlmostEqual(10000 - actors["guardian"]["hp"], 340 * 0.25 * 0.5 * 0.3)
        self.assertAlmostEqual(
            actors["guardian"]["_hazard_attack_rate"], 1 - 0.72 * 0.7
        )
        self.assertAlmostEqual(
            actors["guardian"]["_hazard_movement_multiplier"], 1 - 0.5 * 0.7
        )
        self.step(actors, runtime, hazards, trace, 0.5)
        self.step(actors, runtime, hazards, trace, 1)
        self.assertAlmostEqual(10000 - actors["unit"]["hp"], 340 * 0.5 * 1.5)

    def test_poison_immunity_does_not_implicitly_remove_slow_or_damage_buildings(self):
        instance = spell_instance("poison-spell")
        actors, runtime, hazards, trace = self.runtime([instance])
        actors["unit"]["immune_until"] = 1
        self.step(actors, runtime, hazards, trace, 0)
        self.assertEqual(actors["unit"]["hp"], 10000)
        self.assertEqual(actors["building"]["hp"], 10000)
        self.assertEqual(actors["unit"]["_hazard_attack_rate"], 0.65)
        self.assertEqual(actors["building"].get("_hazard_attack_rate"), 1)

    def test_poison_fields_add_damage_but_take_strongest_status_and_linger(self):
        instances = [
            spell_instance("poison-spell", id=f"p-{index}") for index in range(2)
        ]
        actors, runtime, hazards, trace = self.runtime(instances)
        self.step(actors, runtime, hazards, trace, 0)
        self.assertEqual(actors["unit"]["hp"], 10000 - 2 * 90 * 0.25 * 0.5)
        self.assertEqual(actors["unit"]["_hazard_attack_rate"], 0.65)
        actors["unit"]["x"] = 20
        self.step(actors, runtime, hazards, trace, 0.1)
        self.assertEqual(actors["unit"]["_hazard_attack_rate"], 0.65)
        self.step(actors, runtime, hazards, trace, 0.35)
        self.assertEqual(actors["unit"]["_hazard_attack_rate"], 1)

    def test_poison_never_starts_before_cast_and_positive_pulses_own_continuation(self):
        instance = spell_instance("poison-spell", time_seconds=1)
        actors, runtime, hazards, trace = self.runtime([instance])
        self.step(actors, runtime, hazards, trace, 0)
        self.assertFalse(hazards.fields)
        self.assertFalse(hazard_continuation(hazards, 0, actors))
        self.step(actors, runtime, hazards, trace, 1)
        facts = hazard_continuation(hazards, 1, actors)
        self.assertTrue(facts)
        self.assertTrue(all(fact["source_team"] == "attack" for fact in facts))
        self.assertEqual(runtime.continuation_reasons(1), [])

    def test_poison_rejects_guessed_pulse_count_and_growth_beyond_expiry(self):
        instance = spell_instance("poison-spell")
        instance["parameters"]["number_of_pulses"] = 16
        with self.assertRaises(InputError):
            compile_attack_spell(instance, self.catalog)
        del instance["parameters"]["number_of_pulses"]
        instance["parameters"]["growth_by_field_age"][1]["after_seconds"] = 16
        with self.assertRaises(InputError):
            compile_attack_spell(instance, self.catalog)

    def test_invisibility_both_teams_excludes_walls_siege_and_preserves_obstacles(self):
        actors, runtime, hazards, trace = self.runtime(
            [spell_instance("invisibility-spell")],
            [
                building(),
                unit(),
                unit("attacker", team="attack"),
                unit("siege", team="attack", hazard_class="siege"),
                building(
                    "wall",
                    kind="wall",
                    counts_for_destruction=False,
                    width=1,
                    height=1,
                    x=11,
                    y=9,
                ),
            ],
        )
        blocked = _blocked(actors, 0)
        self.step(actors, runtime, hazards, trace, 0)
        for key in ("building", "unit", "attacker"):
            self.assertEqual(untargetable_until(actors[key]), 3.5)
            self.assertEqual(actors[key]["immune_until"], 0)
        self.assertEqual(untargetable_until(actors["wall"]), 0)
        self.assertEqual(untargetable_until(actors["siege"]), 0)
        self.assertEqual(_blocked(actors, 0), blocked)

    def test_invisibility_union_exits_and_other_sources_are_independent(self):
        first = spell_instance("invisibility-spell", id="first")
        second = spell_instance("invisibility-spell", id="second", time_seconds=1)
        actors, runtime, hazards, trace = self.runtime([first, second])
        self.step(actors, runtime, hazards, trace, 0)
        actors["unit"]["_untargetable_until"] = 6
        self.step(actors, runtime, hazards, trace, 1)
        self.step(actors, runtime, hazards, trace, 3.5)
        self.assertEqual(actors["unit"]["_attack_spell_untargetable_until"], 4.5)
        actors["unit"]["x"] = 20
        self.step(actors, runtime, hazards, trace, 3.6)
        self.assertEqual(actors["unit"]["_attack_spell_untargetable_until"], 0)
        self.assertEqual(untargetable_until(actors["unit"]), 6)

    def test_invisibility_applies_to_new_deployments_and_clears_retained_targets(self):
        actors, runtime, hazards, trace = self.runtime(
            [spell_instance("invisibility-spell")],
            [building(), unit(spawn_seconds="controlled")],
        )
        self.step(actors, runtime, hazards, trace, 0)
        self.assertEqual(untargetable_until(actors["unit"]), 0)
        actors["unit"]["spawn_seconds"] = 0.1
        actors["building"]["target"] = "unit"
        self.step(actors, runtime, hazards, trace, 0.1)
        self.assertEqual(untargetable_until(actors["unit"]), 3.5)
        self.assertIsNone(actors["building"]["target"])

    def test_invisibility_circle_entry_exit_and_reversal_are_exact(self):
        actors, runtime, hazards, trace = self.runtime(
            [spell_instance("invisibility-spell")], [building(), unit(x=4)]
        )
        self.step(actors, runtime, hazards, trace, 0)
        actor = actors["unit"]
        delay = runtime.first_crossing_delay(actor, [(18, 10)], 0, 3, 4)
        self.assertEqual(delay, 0.5)
        actor["x"] = 6
        self.step(actors, runtime, hazards, trace, 0.5)
        self.assertGreater(untargetable_until(actor), 0.5)
        delay = runtime.first_crossing_delay(actor, [(18, 10)], 0.5, 3, 4)
        self.assertEqual(delay, 2)
        actor["x"] = 14
        self.step(actors, runtime, hazards, trace, 2.5)
        self.assertEqual(untargetable_until(actor), 0)
        reversal = runtime.first_crossing_delay(actor, [(10, 10)], 2.5, 0.5, 4)
        self.assertGreater(reversal, 0)
        self.assertLess(reversal, 1e-7)
        actor["x"] -= 4 * reversal
        self.step(actors, runtime, hazards, trace, 2.5 + reversal)
        self.assertGreater(untargetable_until(actor), 2.5)

    def test_overgrowth_captures_structures_protects_and_leaves_garrison_clock_running(
        self,
    ):
        actors, runtime, hazards, trace = self.runtime(
            [spell_instance("overgrowth-spell")],
            [
                building(),
                building("castle", x=11, y=9, garrison_model={"test": True}),
                unit(x=15),
                building(
                    "wall",
                    kind="wall",
                    counts_for_destruction=False,
                    width=1,
                    height=1,
                    x=11,
                    y=12,
                ),
            ],
        )
        before = _blocked(actors, 0)
        self.step(actors, runtime, hazards, trace, 0)
        self.assertEqual(
            runtime.result()["overgrowth_recipients"]["overgrowth-spell"],
            ["building", "castle"],
        )
        self.assertEqual(actors["building"]["frozen_until"], 22)
        self.assertEqual(actors["building"]["next_attack"], 23)
        self.assertEqual(actors["castle"]["frozen_until"], 0)
        self.assertEqual(actors["castle"]["next_attack"], 1)
        self.assertEqual(actors["castle"]["immune_until"], 22)
        self.assertEqual(actors["unit"]["immune_until"], 0)
        self.assertEqual(untargetable_until(actors["wall"]), 0)
        self.assertEqual(_blocked(actors, 0), before)
        self.assertEqual(runtime.continuation_reasons(0), [])

    def test_same_time_overgrowth_blocks_lightning_but_invisibility_does_not(self):
        for status, expected in (
            ("overgrowth-spell", 10000),
            ("invisibility-spell", 9850),
        ):
            actors, runtime, hazards, trace = self.runtime(
                [
                    spell_instance(id="a-lightning"),
                    spell_instance(status, id="z-status"),
                ]
            )
            self.step(actors, runtime, hazards, trace, 0)
            self.assertEqual(actors["building"]["hp"], expected)

    def test_hidden_teslas_and_dormant_units_are_excluded_without_death_side_effects(
        self,
    ):
        actors, runtime, hazards, trace = self.runtime(
            actor_specs=[building(), unit(spawn_seconds="controlled")]
        )
        actors["building"]["_tesla_hidden"] = True
        self.step(actors, runtime, hazards, trace, 0)
        for actor in actors.values():
            self.assertEqual(actor["hp"], 10000)
            self.assertEqual(actor["frozen_until"], 0)
            self.assertIsNone(actor["death_time"])

    def test_termination_classifications_bind_mechanism_not_a_freeform_label(self):
        policy = {
            "spell_inventory": [
                {"entity": "lightning-spell", "classification": "damage"},
                {"entity": "invisibility-spell", "classification": "support_only"},
            ]
        }
        validate_spell_classifications(policy)
        policy["spell_inventory"][1]["classification"] = "damage"
        with self.assertRaises(InputError):
            validate_spell_classifications(policy)


if __name__ == "__main__":
    unittest.main()
