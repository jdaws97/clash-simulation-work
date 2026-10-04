"""Hero loadouts, shared activations, live membership and human delay checks."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.adapters import (
    compile_entity_scene,
    simulate_entity_scene,
    simulate_entity_closed_loop,
)
from clashlab.catalog import Catalog
from clashlab.closed_loop import CONTROL_RULES
from clashlab.combat import PatternCombat, expand_area_effects
from clashlab.common import InputError
from clashlab.heroes import HERO_RULES, SCOPE, HeroCombat, validate_ability_command
from clashlab.spatial import _apply_effects, _eligible, _load_actors, simulate_spatial

from test_adapters import entity_instance
from test_defense_patterns import area_sector


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "declared-hero-fixture-not-current-game-or-player-calibration"


def equipment(entity, level):
    parameters = {"source": SOURCE}
    if entity == "magic-mirror":
        parameters.update(
            clone_offsets=[{"dx": 0, "dy": -0.5}, {"dx": 0, "dy": 0.5}],
            clone_statistics="snapshot_clone_totals_without_equipment_hypothesis",
            source_death_policy="released_clones_persist_until_expiry",
            first_attack_delay_seconds=0,
        )
    elif entity == "rocket-spear":
        parameters["splash_layer_policy"] = "all_declared_target_layers"
    elif entity == "electro-boots":
        parameters.update(
            first_aura_pulse_delay_seconds=0.4,
            self_heal_interval_seconds=0.5,
            first_self_heal_delay_seconds=0.5,
            frozen_passives_policy="continue_while_frozen_hypothesis",
            aura_target_kinds=["defense", "building", "unit"],
            aura_target_layers=["ground", "air"],
        )
    elif entity in {"eternal-tome", "healing-tome"}:
        parameters.update(radius=3, membership="snapshot_at_activation")
        if entity == "healing-tome":
            parameters.update(
                membership="snapshot_at_activation_buff_follows_recipient",
                pulse_interval_seconds=0.5,
                first_pulse_delay_seconds=0.5,
                healing_multipliers_by_class={"troop": 1, "hero": 1},
            )
    return {"entity": entity, "level": level, "parameters": parameters}


def hero(entity="royal-champion", bare=False, **changes):
    names = {
        "royal-champion": ("royal", 45, [("rocket-spear", 21), ("electro-boots", 23)]),
        "archer-queen": ("queen", 95, [("invisibility-vial", 7), ("magic-mirror", 20)]),
        "grand-warden": ("warden", 70, [("eternal-tome", 18), ("healing-tome", 15)]),
    }
    instance_id, level, items = names[entity]
    instance = entity_instance(
        instance_id,
        entity,
        level,
        "attack",
        mode="ground",
        hero_parameters={
            "source": SOURCE,
            "equipment": (
                [] if bare else [equipment(name, level) for name, level in items]
            ),
            "loadout_policy": (
                "bare_hero_controlled_probe" if bare else "exact_two_equipment"
            ),
            "recovery_basis": "snapshot_base_and_equipment_recovery_on_activation_hypothesis",
            "activation_policy": "manual_only_controlled_probe",
            "pet_policy": "omitted_for_controlled_probe",
            "targeting_policy": (
                "independent_targeting_without_army_following_controlled_probe"
                if entity == "grand-warden"
                else "retained_building_targeting_hypothesis"
            ),
            "statistics_mapping": "base_and_equipment_additions_before_modifiers",
        },
        wall_parameters={
            "kind": "avoid" if entity == "archer-queen" else "jump_enemy_walls",
            "source": SOURCE,
        },
    )
    instance.update(changes)
    if instance["mode"] == "air":
        instance.pop("wall_parameters", None)
    return instance


def hero_sector(catalog, entities, duration=0.1, effects=None):
    specification = area_sector(catalog, entities)
    specification.update(
        id="conditional-hero-equipment-fixture",
        scope=SCOPE,
        model_rules=deepcopy(HERO_RULES),
        duration_seconds=duration,
        maximum_step_seconds=0.05,
        recording_interval_seconds=0.05,
        effects=[] if effects is None else effects,
    )
    for instance in entities:
        if instance["entity"] in {"archer", "barbarian", "thrower"}:
            instance["wall_parameters"] = {"kind": "avoid", "source": SOURCE}
    return specification


def ability(hero_id, time=0, command_id="activate"):
    return {
        "id": command_id,
        "kind": "hero_ability",
        "hero_id": hero_id,
        "time_seconds": time,
    }


def loaded_runtime(catalog, entities):
    compiled = compile_entity_scene(hero_sector(catalog, entities), catalog)
    actors = _load_actors(compiled["scene"], 14, 12)
    combat = PatternCombat(actors)
    return actors, combat, HeroCombat(actors, combat)


class HeroEquipmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_equipment_additions_precede_explicit_modifiers(self):
        royal = hero()
        royal["modifiers"]["hitpoints_multiplier"] = 2
        royal["modifiers"]["damage_multiplier"] = 1.5
        result = compile_entity_scene(hero_sector(self.catalog, [royal]), self.catalog)
        actor = result["scene"]["actors"][0]
        self.assertEqual(actor["hitpoints"], (4038 + 550 + 600) * 2)
        self.assertAlmostEqual(actor["damage"], (654 + 144 * 1.2) * 1.5)
        self.assertEqual(actor["healing_class"], "hero")
        self.assertEqual(actor["hazard_class"], "hero")
        self.assertEqual(actor["range"], 3)
        self.assertEqual(actor["hero_model"]["equipment"][0]["boosted_launches"], 9)

    def test_missing_or_foreign_loadouts_and_unimplemented_policies_are_rejected(self):
        for change in (
            {"equipment": [equipment("rocket-spear", 21)]},
            {
                "equipment": [
                    equipment("rocket-spear", 21),
                    equipment("rocket-spear", 21),
                ]
            },
            {
                "equipment": [
                    equipment("royal-gem", 1),
                    equipment("invisibility-vial", 7),
                ]
            },
            {"activation_policy": "automatic"},
            {"pet_policy": "spirit-fox"},
            {"recovery_basis": "infer_from_field_name"},
        ):
            with self.subTest(change=change):
                instance = hero()
                instance["hero_parameters"].update(change)
                with self.assertRaises(InputError):
                    compile_entity_scene(
                        hero_sector(self.catalog, [instance]), self.catalog
                    )

    def test_bare_probe_is_explicit_and_old_scopes_cannot_activate_heroes(self):
        bare = hero(bare=True)
        result = compile_entity_scene(hero_sector(self.catalog, [bare]), self.catalog)
        self.assertEqual(result["scene"]["actors"][0]["hitpoints"], 4038)
        with self.assertRaises(InputError):
            compile_entity_scene(area_sector(self.catalog, [bare]), self.catalog)
        scene = deepcopy(result["scene"])
        from clashlab.defense_patterns import RULESET, RULES

        scene.update(ruleset=RULESET, model_rules=deepcopy(RULES))
        with self.assertRaises(InputError):
            simulate_spatial(scene)

    def test_cloak_blocks_acquisition_and_keeps_area_and_released_damage(self):
        cannon = entity_instance("cannon", "cannon", 21, "defense")
        cannon["attack_parameters"]["projectile"] = {
            "timing": "launch_distance_delay",
            "speed_tiles_per_second": 2,
            "delay_seconds": 0,
            "destination": "locked_actor_center_at_impact",
            "hit_radius": 0,
        }
        actors, combat, runtime = loaded_runtime(
            self.catalog, [hero("archer-queen"), cannon]
        )
        queen = actors["queen"]
        self.assertTrue(_eligible(actors["cannon"], queen, 0))
        trace = []
        combat.launch(actors["cannon"], queen, actors, 0, trace)
        runtime.expand_commands([ability("queen", 0.1)], actors, 0.1, trace)
        runtime.prepare(actors, 0.1, trace)
        self.assertFalse(_eligible(actors["cannon"], queen, 0.1))
        self.assertTrue(_eligible(actors["cannon"], queen, 5.5))
        self.assertAlmostEqual(queen["damage"], 573.75 + 920)
        damage = combat.resolve(actors, 1, trace)
        self.assertAlmostEqual(damage["queen"], actors["cannon"]["damage"])
        area = {
            "id": "splash",
            "kind": "area_damage",
            "time_seconds": 0.1,
            "amount": 10,
            "area": {
                "x": queen["x"],
                "y": queen["y"],
                "radius": 1,
                "target_team": "attack",
                "target_kinds": ["unit"],
                "target_layers": ["ground"],
            },
        }
        self.assertIn("queen", expand_area_effects([area], actors, 0.1)[0]["targets"])

    def test_both_active_items_share_one_charge_and_clones_have_separate_stats(self):
        result = simulate_entity_scene(
            hero_sector(
                self.catalog,
                [hero("archer-queen")],
                effects=[ability("queen"), ability("queen", 0.05, "again")],
            ),
            self.catalog,
        )
        combat = result["combat"]
        self.assertEqual(
            [item["status"] for item in combat["hero_abilities"]["activations"]],
            ["activated", "ability_already_used"],
        )
        self.assertEqual(combat["actors"]["queen-mirror-clone-0"]["hitpoints"], 2338)
        self.assertEqual(combat["actors"]["queen-mirror-clone-0"]["damage"], 556 * 0.75)
        self.assertEqual(combat["actors"]["queen-mirror-clone-0"]["spawn_seconds"], 0)
        self.assertEqual(combat["hero_abilities"]["hero_abilities_used"], ["queen"])

    def test_clones_persist_after_parent_death_and_expire_without_resurrection(self):
        effects = [
            ability("queen", 0.2),
            {
                "id": "defeat-parent",
                "kind": "damage",
                "time_seconds": 0.3,
                "targets": ["queen"],
                "amount": 5000,
            },
        ]
        result = simulate_entity_scene(
            hero_sector(
                self.catalog, [hero("archer-queen")], duration=25.3, effects=effects
            ),
            self.catalog,
        )
        frames = result["combat"]["frames"]
        after_death = next(frame for frame in frames if frame["time_seconds"] > 0.31)
        self.assertEqual(after_death["actors"]["queen"]["hp"], 0)
        self.assertGreater(after_death["actors"]["queen-mirror-clone-0"]["hp"], 0)
        clone = result["combat"]["actors"]["queen-mirror-clone-0"]
        self.assertAlmostEqual(clone["death_time"], 25.2)
        self.assertEqual(clone["hp"], 0)
        self.assertFalse(clone["counts_for_destruction"])

    def test_clone_cannot_activate_another_hero_ability(self):
        actors, _, _ = loaded_runtime(self.catalog, [hero("archer-queen")])
        with self.assertRaises(InputError):
            validate_ability_command(ability("queen-mirror-clone-0"), actors)

    def test_rocket_spear_spends_nine_launches_then_restores_ordinary_weapon(self):
        cannon = entity_instance(
            "target", "cannon", 21, "defense", first_attack_seconds=1000
        )
        cannon["modifiers"]["hitpoints_multiplier"] = 100
        spec = hero_sector(
            self.catalog, [hero(), cannon], duration=11, effects=[ability("royal")]
        )
        result = simulate_entity_scene(spec, self.catalog)["combat"]
        impacts = [
            event
            for event in result["trace"]
            if event.get("event") == "projectile_impact" and event["source"] == "royal"
        ]
        self.assertEqual(len(impacts), 10)
        self.assertAlmostEqual(impacts[0]["damage"], 826.8 + 840)
        self.assertAlmostEqual(impacts[-1]["damage"], 826.8)
        self.assertEqual(
            result["hero_abilities"]["rocket_spear_launches_remaining"]["royal"], 0
        )
        self.assertEqual(result["actors"]["royal"]["range"], 3)

    def test_tomes_capture_membership_and_healing_follows_recipients_after_source_death(
        self,
    ):
        archer = entity_instance("near", "archer", 12, "attack", x=6.5, y=5.5)
        distant = entity_instance("late", "archer", 12, "attack", x=1.5, y=1.5)
        actors, _, runtime = loaded_runtime(
            self.catalog, [hero("grand-warden"), archer, distant]
        )
        trace = []
        commands = runtime.expand_commands([ability("warden")], actors, 0, trace)
        _apply_effects(commands, actors, 0, trace)
        self.assertAlmostEqual(actors["near"]["immune_until"], 8.2)
        self.assertEqual(actors["late"]["immune_until"], 0)
        actors["near"]["x"] = 1
        actors["near"]["y"] = 1
        actors["late"]["x"] = 7
        actors["late"]["y"] = 5
        actors["warden"]["hp"] = 0
        runtime.prepare(actors, 0.5, trace)
        _, healing = runtime.resolve_passives(actors, 0.5, trace)
        self.assertEqual(healing["near"], 70)
        self.assertEqual(healing["late"], 0)
        self.assertEqual(healing["warden"], 0)

    def test_royal_champion_moves_again_when_the_last_long_range_spear_is_spent(self):
        royal = hero(x=2.5, y=5.5)
        target = entity_instance(
            "target", "cannon", 21, "defense", x=11, y=4, first_attack_seconds=1000
        )
        target["modifiers"]["hitpoints_multiplier"] = 100
        result = simulate_entity_scene(
            hero_sector(
                self.catalog, [royal, target], duration=13, effects=[ability("royal")]
            ),
            self.catalog,
        )["combat"]
        before = max(
            (frame for frame in result["frames"] if frame["time_seconds"] < 9.5),
            key=lambda frame: frame["time_seconds"],
        )
        self.assertEqual(before["actors"]["royal"]["x"], 2.5)
        self.assertGreater(result["actors"]["royal"]["x"], 7)
        impacts = [
            event
            for event in result["trace"]
            if event.get("event") == "projectile_impact" and event["source"] == "royal"
        ]
        self.assertGreater(len(impacts), 9)
        self.assertAlmostEqual(impacts[9]["damage"], 826.8)

    def test_launched_spear_keeps_its_bonus_after_the_ability_counter_reaches_zero(
        self,
    ):
        royal = hero()
        royal["attack_parameters"]["projectile"].update(
            timing="launch_distance_delay",
            speed_tiles_per_second=1,
        )
        target = entity_instance(
            "target", "cannon", 21, "defense", first_attack_seconds=1000
        )
        target["modifiers"]["hitpoints_multiplier"] = 100
        result = simulate_entity_scene(
            hero_sector(
                self.catalog, [royal, target], duration=13, effects=[ability("royal")]
            ),
            self.catalog,
        )["combat"]
        impacts = [
            event
            for event in result["trace"]
            if event.get("event") == "projectile_impact" and event["source"] == "royal"
        ]
        self.assertGreater(impacts[8]["time_seconds"], 11.5)
        self.assertAlmostEqual(impacts[8]["damage"], 1666.8)
        self.assertAlmostEqual(impacts[9]["damage"], 826.8)

    def test_boots_use_the_explicit_aura_layer_policy(self):
        royal = hero()
        royal["hero_parameters"]["equipment"][1]["parameters"]["aura_target_layers"] = [
            "ground"
        ]
        target = entity_instance("air-layer-probe", "archer", 12, "attack")
        actors, _, runtime = loaded_runtime(self.catalog, [royal, target])
        actors[target["id"]].update(team="defense", layer="air")
        runtime.prepare(actors, 0, [])
        damage, _ = runtime.resolve_passives(actors, 0.4, [])
        self.assertEqual(damage[target["id"]], 0)
        royal["hero_parameters"]["equipment"][1]["parameters"]["aura_target_layers"] = [
            "ground",
            "air",
        ]
        actors, _, runtime = loaded_runtime(self.catalog, [royal, target])
        actors[target["id"]].update(team="defense", layer="air")
        runtime.prepare(actors, 0, [])
        damage, _ = runtime.resolve_passives(actors, 0.4, [])
        self.assertEqual(damage[target["id"]], 74)

    def test_boots_recompute_moving_membership_and_continue_under_declared_freeze_policy(
        self,
    ):
        target = entity_instance(
            "target", "cannon", 21, "defense", first_attack_seconds=1000
        )
        actors, _, runtime = loaded_runtime(self.catalog, [hero(), target])
        trace = []
        actors["royal"]["frozen_until"] = 2
        runtime.prepare(actors, 0, trace)
        damage, _ = runtime.resolve_passives(actors, 0.4, trace)
        self.assertEqual(damage["target"], 74)
        actors["royal"]["x"] = 1
        actors["royal"]["y"] = 1
        damage, _ = runtime.resolve_passives(actors, 0.8, trace)
        self.assertEqual(damage["target"], 0)

    def test_wall_jump_preserves_walls_and_ground_layer(self):
        royal = hero(bare=True, x=3.5, first_attack_seconds=1000)
        target = entity_instance(
            "target", "cannon", 21, "defense", x=10, y=4, first_attack_seconds=1000
        )
        walls = [
            entity_instance(
                f"wall-{y}",
                "wall",
                17,
                "defense",
                x=6,
                y=y,
                mode="passive",
                statistics_mode="none",
                attack_parameters={},
                inactive_attack_interval_seconds=1,
                counts_for_destruction=False,
            )
            for y in range(12)
        ]
        result = simulate_entity_scene(
            hero_sector(self.catalog, [royal, target, *walls], duration=2), self.catalog
        )["combat"]
        self.assertGreaterEqual(result["actors"]["royal"]["x"], 7)
        self.assertEqual(result["actors"]["royal"]["layer"], "ground")
        self.assertTrue(all(result["actors"][f"wall-{y}"]["hp"] > 0 for y in range(12)))

    def test_royal_gem_recovery_is_part_of_the_shared_activation(self):
        royal = hero()
        royal["hero_parameters"]["equipment"] = [
            equipment("royal-gem", 1),
            equipment("electro-boots", 23),
        ]
        result = compile_entity_scene(hero_sector(self.catalog, [royal]), self.catalog)
        self.assertEqual(
            result["scene"]["actors"][0]["hero_model"]["health_recovery"], 1300 + 1200
        )

    def test_default_equipment_zero_blacksmith_marker_uses_hero_unlock(self):
        self.assertTrue(self.catalog.available("royal-gem", 1, 16))
        self.assertFalse(self.catalog.available("royal-gem", 1, 12))
        self.assertTrue(self.catalog.available("invisibility-vial", 1, 9))
        self.assertTrue(self.catalog.available("invisibility-vial", 1, 8))
        self.assertFalse(self.catalog.available("invisibility-vial", 1, 7))

    def test_native_runtime_rejects_unimplemented_fields_and_foreign_equipment(self):
        compiled = compile_entity_scene(
            hero_sector(self.catalog, [hero()]), self.catalog
        )["scene"]
        for mutation in (
            "unknown-model-field",
            "wrong-type",
            "unknown-parameter",
            "foreign-owner",
            "unsupported-policy",
        ):
            scene = deepcopy(compiled)
            model = scene["actors"][0]["hero_model"]
            if mutation == "unknown-model-field":
                model["equipment"][0]["automatic_activation"] = True
            elif mutation == "wrong-type":
                model["equipment"][0]["ability_type"] = "Passive"
            elif mutation == "unknown-parameter":
                model["equipment"][0]["parameters"]["infer_splash_layers"] = True
            elif mutation == "foreign-owner":
                model["entity"] = "archer-queen"
            else:
                model["equipment"][1]["parameters"]["frozen_passives_policy"] = "pause"
            with self.subTest(mutation=mutation), self.assertRaises(InputError):
                simulate_spatial(scene)

    def test_human_delay_is_rechecked_before_spending_the_charge(self):
        queen = hero("archer-queen")
        mono = entity_instance("mono", "monolith", 3, "defense")
        cannon = entity_instance("cannon", "cannon", 21, "defense", x=8, y=8)
        specification = hero_sector(self.catalog, [queen, mono, cannon], duration=12)
        action = {
            "id": "queen-ability",
            "kind": "hero_ability",
            "hero_id": "queen",
            "recheck_conditions_on_execution": True,
            "cost": {"queen-ability": 1},
        }
        plan = {
            "id": "queen-response",
            "control_rules": deepcopy(CONTROL_RULES),
            "observation_interval_seconds": 0.1,
            "failed_action_transition": "advance",
            "resources": {"queen-ability": 1},
            "streams": [
                {
                    "id": "queen",
                    "steps": [
                        {
                            "all_conditions": [
                                {
                                    "field": "active",
                                    "actor_id": "queen",
                                    "operator": "equals",
                                    "value": True,
                                },
                                {
                                    "field": "hp_fraction",
                                    "actor_id": "queen",
                                    "operator": "at_most",
                                    "value": 0.5,
                                },
                            ],
                            "action": action,
                        }
                    ],
                }
            ],
        }
        samples = []
        for latency in (0.2, 3.5):
            profile = {
                "plan_id": plan["id"],
                "observed_latency_traces": [
                    {
                        "source_replay": SOURCE,
                        "responses": {
                            "queen-ability": {
                                "latency_seconds": latency,
                                "missed": False,
                                "placement_errors": {},
                            }
                        },
                    }
                ],
            }
            samples.append(
                simulate_entity_closed_loop(
                    specification, self.catalog, plan, profile, 7, 1
                )["human_combat"]["samples"][0]
            )
        self.assertEqual(
            samples[0]["control"]["actions"][0]["status"], "command_applied"
        )
        self.assertEqual(
            samples[1]["control"]["actions"][0]["status"], "cue_no_longer_valid"
        )
        self.assertEqual(
            samples[1]["control"]["remaining_resources"]["queen-ability"], 1
        )
        self.assertFalse(
            samples[1]["combat"]["hero_abilities"]["automatic_activation_modeled"]
        )


if __name__ == "__main__":
    unittest.main()
