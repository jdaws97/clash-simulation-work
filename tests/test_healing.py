"""Shared support/damage checks with explicit, synthetic healing conventions."""

import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from clashlab.adapters import (
    SUPPORT_SCOPE,
    compile_entity_scene,
    compile_healing_spell_field,
)
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.healing import RULESET, SUPPORT_RULES, SupportCombat
from clashlab.spatial import simulate_spatial

from test_adapters import entity_instance, projectile, sector
from test_closed_loop import one_trial, synthetic_plan, synthetic_profile
from test_combat import pattern_scene
from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-healing-conventions-not-measured-Clash-AI"


def healing_model(**changes):
    model = {
        "kind": "single",
        "source": SOURCE,
        "target_kinds": ["unit"],
        "target_layers": ["ground"],
        "target_classes": ["troop", "hero"],
        "amounts_by_class": {"troop": 20, "hero": 10},
        "projectile": projectile(),
        "stacking_group": "test-healers",
        "selector": {
            "source": SOURCE,
            "selection": "closest_eligible",
            "retention": "until_dead_or_ineligible",
            "follow_full_health_targets": True,
            "acquisition_range": "unbounded",
            "primary_target_ids": "all_eligible",
        },
    }
    model.update(changes)
    return model


def healer(actor_id="healer", **changes):
    actor = synthetic_unit(
        actor_id,
        x=5.5,
        layer="air",
        movement="air",
        damage=0,
        range=5,
        attack_interval_seconds=1,
    )
    actor.update(changes)
    return actor


def injured(amount=60, targets=None, time=0):
    return {
        "id": f"injury-{time}",
        "source": SOURCE,
        "kind": "damage",
        "time_seconds": time,
        "targets": targets or ["attacker"],
        "amount": amount,
    }


def support_scene(actors=None, effects=None, **changes):
    if actors is None:
        actors = [
            synthetic_unit(x=6.5, damage=1, range=1, attack_interval_seconds=100),
            healer(),
            synthetic_structure(hitpoints=10000),
        ]
    scene = pattern_scene(actors, effects, duration_seconds=0.05)
    scene["ruleset"] = RULESET
    scene["model_rules"] = deepcopy(SUPPORT_RULES)
    scene["healing_stacking"] = {
        "source": SOURCE,
        "groups": {
            "test-healers": {
                "source": SOURCE,
                "allocation": "instance_id",
                "tables": {"troop": [1, 0.5, 0.25], "hero": [1, 0.5, 0.25]},
            }
        },
    }
    for actor in scene["actors"]:
        if actor["kind"] == "unit":
            actor["healing_class"] = "troop"
            if actor["movement"] == "ground":
                actor["wall_behavior"] = {"kind": "avoid", "source": SOURCE}
        if actor["id"].startswith("healer"):
            actor["healing_model"] = healing_model()
    scene.update(changes)
    return scene


def healing_field(**changes):
    field = {
        "id": "heal-field",
        "source": SOURCE,
        "kind": "healing_field",
        "time_seconds": 0,
        "first_pulse_delay_seconds": 0,
        "pulse_count": 3,
        "pulse_interval_seconds": 1,
        "amounts_by_class": {"troop": 20, "hero": 10},
        "area": {
            "x": 6.5,
            "y": 3.5,
            "radius": 0.2,
            "target_team": "attack",
            "target_kinds": ["unit"],
            "target_layers": ["ground", "air"],
            "target_classes": ["troop", "hero"],
        },
    }
    field.update(changes)
    return field


class SupportCombatTests(unittest.TestCase):
    def test_moving_ally_contact_is_one_relative_arrival_with_freeze_control(self):
        for step in (2, 0.31, 0.017):
            for freeze in (False, True):
                with self.subTest(step=step, freeze=freeze):
                    effects = [injured()]
                    if freeze:
                        effects.append(
                            {
                                "id": "pause-healer",
                                "kind": "freeze",
                                "time_seconds": 0.2,
                                "duration_seconds": 0.5,
                                "targets": ["healer"],
                            }
                        )
                    expected = 2 if freeze else 1
                    scene = support_scene(
                        actors=[
                            synthetic_unit(x=6.5, speed=1, range=0.5, damage=1),
                            healer(x=0.5, speed=2),
                            synthetic_structure(x=18, hitpoints=10000),
                        ],
                        effects=effects,
                        width=22,
                        duration_seconds=expected + 0.05,
                        recording_interval_seconds=10,
                        maximum_step_seconds=step,
                    )
                    boundaries = []
                    prepare = SupportCombat.prepare_targets

                    def counted(runtime, actors, now, *args):
                        boundaries.append(now)
                        return prepare(runtime, actors, now, *args)

                    with patch.object(SupportCombat, "prepare_targets", counted):
                        result = simulate_spatial(scene)
                    heals = [
                        e for e in result["trace"] if e.get("event") == "healing_launch"
                    ]
                    self.assertEqual(len(heals), 1)
                    self.assertAlmostEqual(heals[0]["time_seconds"], expected)
                    self.assertEqual(heals[0]["target"], "attacker")
                    self.assertEqual(result["actors"]["attacker"]["hp"], 60)
                    if step == 2:
                        self.assertLess(len(boundaries), 12)

    def test_class_specific_pulse_and_health_cap(self):
        for healing_class, expected in (("troop", 60), ("hero", 50)):
            with self.subTest(healing_class=healing_class):
                scene = support_scene(effects=[injured()])
                scene["actors"][0]["healing_class"] = healing_class
                self.assertEqual(
                    simulate_spatial(scene)["actors"]["attacker"]["hp"], expected
                )
        scene = support_scene(effects=[injured(5)])
        self.assertEqual(simulate_spatial(scene)["actors"]["attacker"]["hp"], 100)

    def test_healer_follows_a_moving_ground_ally_without_attacking_enemies(self):
        scene = support_scene(duration_seconds=2)
        scene["actors"][0].update(x=0.5, range=0.5)
        scene["actors"][1].update(x=0.5, y=0.5, range=1)
        result = simulate_spatial(scene)
        self.assertGreater(result["actors"]["healer"]["x"], 0.5)
        self.assertEqual(result["actors"]["healer"]["healing_target"], "attacker")
        self.assertFalse(
            any(
                e.get("event") == "projectile_launch" and e.get("source") == "healer"
                for e in result["trace"]
            )
        )

    def test_ground_only_healing_does_not_heal_air_allies_or_enemies(self):
        scene = support_scene(effects=[injured(60, ["attacker", "enemy", "healer"])])
        scene["actors"][0].update(layer="air", movement="air")
        scene["actors"][0].pop("wall_behavior")
        enemy = deepcopy(scene["actors"][0])
        enemy.update(
            id="enemy", team="defense", layer="ground", movement="ground", x=6.5, y=2.5
        )
        enemy["wall_behavior"] = {"kind": "avoid", "source": SOURCE}
        scene["actors"].append(enemy)
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["attacker"]["hp"], 40)
        self.assertEqual(result["actors"]["enemy"]["hp"], 40)
        self.assertEqual(result["actors"]["healer"]["hp"], 40)
        self.assertIsNone(result["actors"]["healer"]["healing_target"])

    def test_stacking_is_independent_of_input_order(self):
        scene = support_scene(effects=[injured()])
        second = deepcopy(scene["actors"][1])
        second["id"] = "healer-two"
        scene["actors"].append(second)
        first = simulate_spatial(scene)
        scene["actors"].reverse()
        second_result = simulate_spatial(scene)
        self.assertEqual(first["actors"]["attacker"]["hp"], 70)
        self.assertEqual(second_result["actors"]["attacker"]["hp"], 70)
        weights = [
            e["stacking_weight"]
            for e in first["trace"]
            if e.get("event") == "healing_impact"
        ]
        self.assertEqual(sorted(weights), [0.5, 1])

    def test_radial_healing_reaches_nearby_allies_outside_primary_filter(self):
        scene = support_scene(effects=[injured(60, ["attacker", "nearby"])])
        nearby = deepcopy(scene["actors"][0])
        nearby.update(id="nearby", x=6.5, y=4)
        scene["actors"].append(nearby)
        model = scene["actors"][1]["healing_model"]
        model.update(kind="radial", radius=0.6)
        model["selector"]["primary_target_ids"] = ["attacker"]
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["attacker"]["hp"], 60)
        self.assertEqual(result["actors"]["nearby"]["hp"], 60)

    def test_retention_can_keep_an_original_target_despite_a_more_injured_ally(self):
        for retention, expected in (
            ("until_dead_or_ineligible", "attacker"),
            ("reselect_each_boundary", "nearby"),
        ):
            scene = support_scene(duration_seconds=1.1)
            nearby = deepcopy(scene["actors"][0])
            nearby.update(id="nearby", x=6.5, y=4.5)
            scene["actors"].append(nearby)
            model = scene["actors"][1]["healing_model"]
            model["selector"].update(
                retention=retention, selection="lowest_hp_fraction_then_distance"
            )
            scene["effects"] = [injured(60, ["nearby"], time=0.5)]
            result = simulate_spatial(scene)
            self.assertEqual(result["actors"]["healer"]["healing_target"], expected)

    def test_missing_or_short_stacking_table_does_not_default_to_full_healing(self):
        scene = support_scene()
        second = deepcopy(scene["actors"][1])
        second["id"] = "healer-two"
        scene["actors"].append(second)
        scene["healing_stacking"]["groups"]["test-healers"]["tables"]["troop"] = [1]
        with self.assertRaisesRegex(InputError, "cover all contributors"):
            simulate_spatial(scene)
        del scene["healing_stacking"]
        with self.assertRaisesRegex(InputError, "healing_stacking"):
            simulate_spatial(scene)

    def test_released_healing_arrives_after_healer_death_or_freeze(self):
        for kind in ("damage", "freeze"):
            scene = support_scene(effects=[injured()], duration_seconds=1.1)
            scene["actors"][1]["healing_model"]["projectile"] = {
                "timing": "launch_distance_delay",
                "speed_tiles_per_second": 1,
                "destination": "locked_actor_center_at_impact",
                "hit_radius": 0,
            }
            stop = {
                "id": "stop-healer",
                "kind": kind,
                "time_seconds": 0.5,
                "targets": ["healer"],
            }
            stop["amount" if kind == "damage" else "duration_seconds"] = (
                100 if kind == "damage" else 3
            )
            scene["effects"].append(stop)
            result = simulate_spatial(scene)
            self.assertEqual(result["actors"]["attacker"]["hp"], 60)
            impact = next(
                e for e in result["trace"] if e.get("event") == "healing_impact"
            )
            self.assertAlmostEqual(impact["time_seconds"], 1)

    def test_dead_primary_fizzles_and_retargets_after_loss(self):
        scene = support_scene(duration_seconds=1.1)
        scene["actors"][1]["healing_model"]["projectile"] = {
            "timing": "launch_distance_delay",
            "speed_tiles_per_second": 1,
            "destination": "locked_actor_center_at_impact",
            "hit_radius": 0,
        }
        scene["actors"].append(deepcopy(scene["actors"][0]))
        scene["actors"][-1].update(id="replacement", x=6.5, y=2.5)
        scene["effects"] = [injured(100, time=0.5)]
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["healer"]["healing_target"], "replacement")
        self.assertTrue(
            any(e.get("event") == "healing_fizzle" for e in result["trace"])
        )

    def test_freeze_pauses_remaining_healing_clock(self):
        scene = support_scene(duration_seconds=3)
        scene["effects"] = [
            {
                "id": "pause",
                "time_seconds": 0.25,
                "kind": "freeze",
                "targets": ["healer"],
                "duration_seconds": 1,
            }
        ]
        times = [
            e["time_seconds"]
            for e in simulate_spatial(scene)["trace"]
            if e.get("event") == "healing_launch"
        ]
        self.assertEqual(times, [0, 2, 3])

    def test_simultaneous_lethal_weapon_damage_wins_over_healing(self):
        scene = support_scene(effects=[injured(60)])
        scene["actors"][2].update(damage=40, range=10)
        scene["actors"][2]["attack_model"] = deepcopy(
            pattern_scene([synthetic_structure(damage=40)])["actors"][0]["attack_model"]
        )
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["attacker"]["hp"], 0)
        self.assertTrue(
            any(e.get("event") == "healing_impact" for e in result["trace"])
        )

    def test_field_membership_recomputed_after_movement_and_deployment(self):
        scene = support_scene(
            actors=[
                synthetic_unit(x=0.5, damage=1),
                synthetic_structure(hitpoints=10000),
            ],
            duration_seconds=2,
        )
        reserve = deepcopy(scene["actors"][0])
        reserve.update(id="reserve", spawn_seconds="controlled", x=1.5, damage=0)
        reserve["attack_model"] = {"kind": "none", "source": SOURCE}
        scene["actors"].append(reserve)
        field = healing_field()
        field["area"].update(x=1.5, radius=0.2)
        scene["effects"] = [
            field,
            {
                "id": "deploy-reserve",
                "kind": "deploy",
                "time_seconds": 1,
                "targets": ["reserve"],
                "positions": {"reserve": {"x": 1.5, "y": 3.5}},
            },
        ]
        pulses = [
            e
            for e in simulate_spatial(scene)["trace"]
            if e.get("event") == "healing_field_pulse"
        ]
        self.assertEqual(pulses[0]["targets"], [])
        self.assertEqual(pulses[1]["targets"], ["reserve"])
        self.assertEqual(pulses[2]["targets"], ["reserve"])

    def test_explicit_field_delay_count_and_pending_horizon(self):
        scene = support_scene(
            actors=[synthetic_unit(x=6.5, damage=0), synthetic_structure()],
            effects=[injured(), healing_field(first_pulse_delay_seconds=0.25)],
            duration_seconds=0.2,
        )
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["attacker"]["hp"], 40)
        self.assertEqual(
            result["support"]["fields"]["heal-field"]["pulses_delivered"], 0
        )
        self.assertEqual(
            result["support"]["pending_healing_at_horizon"][0]["arrival_seconds"], 0.25
        )
        scene["duration_seconds"] = 5
        self.assertEqual(
            simulate_spatial(scene)["support"]["fields"]["heal-field"][
                "pulses_delivered"
            ],
            3,
        )

    def test_human_field_placement_spends_spell_even_when_it_misses(self):
        scene = support_scene(
            actors=[
                synthetic_unit(x=6.5, hitpoints=100, damage=0),
                synthetic_structure(),
            ],
            effects=[injured()],
            duration_seconds=1,
        )
        plan = synthetic_plan()
        plan["resources"] = {"heal_casts": 1}
        action = healing_field(pulse_count=1)
        action.pop("time_seconds")
        action.update(
            id="protect", recheck_conditions_on_execution=True, cost={"heal_casts": 1}
        )
        plan["streams"][0]["steps"][0]["action"] = action
        profile = synthetic_profile(latency=0.1)
        response = profile["observed_latency_traces"][0]["responses"]["protect"]
        response["placement_errors"] = {"area": {"dx": 0, "dy": 0}}
        accurate = one_trial(scene, plan, profile)
        response["placement_errors"]["area"]["dx"] = 1
        missed = one_trial(scene, plan, profile)
        self.assertEqual(accurate["combat"]["actors"]["attacker"]["hp"], 60)
        self.assertEqual(missed["combat"]["actors"]["attacker"]["hp"], 40)
        self.assertEqual(missed["control"]["remaining_resources"]["heal_casts"], 0)

    def test_unsupported_healing_chain_and_legacy_fallback_are_rejected(self):
        scene = support_scene()
        scene["actors"][1]["healing_model"]["kind"] = "chain"
        with self.assertRaisesRegex(InputError, "complete behavior"):
            simulate_spatial(scene)
        from clashlab.walls import RULESET as WALL_RULESET, WALL_RULES

        scene["ruleset"] = WALL_RULESET
        scene["model_rules"] = deepcopy(WALL_RULES)
        with self.assertRaisesRegex(InputError, "explicit support"):
            simulate_spatial(scene)


class HealingAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_healer_statistics_compile_with_separate_class_pulses(self):
        instance = entity_instance(
            "healer", "healer", 9, "attack", attack_parameters={}
        )
        model = healing_model(kind="radial", radius=1)
        instance["healing_parameters"] = {
            key: model[key]
            for key in (
                "kind",
                "radius",
                "projectile",
                "selector",
                "stacking_group",
                "source",
            )
        }
        instance["healing_parameters"]["amount_multiplier"] = 1
        spec = sector(self.catalog, [instance])
        spec.update(
            scope=SUPPORT_SCOPE,
            model_rules=deepcopy(SUPPORT_RULES),
            healing_spells=[],
            healing_stacking=support_scene()["healing_stacking"],
        )
        actor = compile_entity_scene(spec, self.catalog)["scene"]["actors"][0]
        self.assertEqual(actor["hitpoints"], 1900)
        self.assertEqual(actor["speed"], 2)
        self.assertEqual(actor["attack_interval_seconds"], 0.7)
        self.assertEqual(
            actor["healing_model"]["amounts_by_class"], {"troop": 56, "hero": 52.5}
        )
        spec["scope"] = (
            "wall_free_sector_without_heroes_pets_traps_defending_troops_or_town_hall"
        )
        from clashlab.combat import COMBAT_RULES

        spec["model_rules"] = deepcopy(COMBAT_RULES)
        with self.assertRaisesRegex(InputError, "support-and-wall"):
            compile_entity_scene(spec, self.catalog)

    def test_spell_uses_41_pulses_and_preserves_total_hero_healing(self):
        instance = {
            "id": "heal",
            "entity": "healing-spell",
            "level": 10,
            "town_hall": 16,
            "time_seconds": 1,
            "x": 4,
            "y": 4,
            "parameters": {
                "source": SOURCE,
                "first_pulse_delay_seconds": 0.1,
                "amount_multiplier": 1,
                "radius_multiplier": 1,
                "pulse_interval_multiplier": 1,
                "target_team": "attack",
                "target_layers": ["ground", "air"],
            },
        }
        field = compile_healing_spell_field(instance, self.catalog)
        self.assertEqual(field["pulse_count"], 41)
        self.assertEqual(field["pulse_interval_seconds"], 0.3)
        self.assertEqual(field["amounts_by_class"], {"troop": 60, "hero": 33})
        self.assertEqual(field["area"]["radius"], 5)
        del instance["parameters"]["first_pulse_delay_seconds"]
        with self.assertRaisesRegex(InputError, "every unresolved"):
            compile_healing_spell_field(instance, self.catalog)

    def test_druid_cannot_be_compiled_as_an_ordinary_healer(self):
        spec = sector(self.catalog, [entity_instance("druid", "druid", 4, "attack")])
        spec.update(scope=SUPPORT_SCOPE, model_rules=deepcopy(SUPPORT_RULES))
        with self.assertRaisesRegex(InputError, "Bear statistics"):
            compile_entity_scene(spec, self.catalog)


if __name__ == "__main__":
    unittest.main()
