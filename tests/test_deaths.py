"""Death event release, geometry and quantity contracts; no game certification."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.adapters import DEATH_SCOPE, compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.deaths import DEATH_RULES, RULESET
from clashlab.spatial import simulate_spatial

from test_adapters import entity_instance, sector
from test_healing import support_scene
from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-death-pattern-not-measured-Clash-behavior"


def death_model(delay=0, amount=50, **changes):
    model = {
        "kind": "fixed_area_sequence_at_death",
        "geometry": "offsets_from_source_center_at_death",
        "source": SOURCE,
        "effects": [
            {
                "id": "blast",
                "source": SOURCE,
                "kind": "area_damage",
                "delay_seconds": delay,
                "amount": amount,
                "area": {
                    "offset_x": 0,
                    "offset_y": 0,
                    "radius": 1,
                    "target_team": "defense",
                    "target_kinds": ["defense", "building"],
                    "target_layers": ["ground"],
                },
            }
        ],
    }
    model.update(changes)
    return model


def damage(actor_id="attacker", time=0, amount=10000):
    return {
        "id": f"kill-{actor_id}-{time}",
        "kind": "damage",
        "targets": [actor_id],
        "time_seconds": time,
        "amount": amount,
    }


def death_scene(actors=None, effects=None, **changes):
    if actors is None:
        actors = [synthetic_unit(x=6.5, damage=1, range=10), synthetic_structure()]
    scene = support_scene(actors, effects, duration_seconds=2)
    scene["ruleset"] = RULESET
    scene["model_rules"] = deepcopy(DEATH_RULES)
    scene["actors"][0]["death_model"] = death_model()
    scene.update(changes)
    return scene


class DeathTests(unittest.TestCase):
    def test_command_kill_releases_one_immediate_blast_without_posthumous_weapon(self):
        result = simulate_spatial(death_scene(effects=[damage()]))
        self.assertEqual(result["actors"]["tower"]["hp"], 50)
        self.assertEqual(result["actors"]["attacker"]["death_time"], 0)
        released = [
            event
            for event in result["trace"]
            if event.get("event") == "death_effect_release"
        ]
        self.assertEqual(len(released), 1)
        self.assertEqual(result["death_effects"]["emitted_instances"], ["attacker"])
        self.assertFalse(
            any(
                event.get("event") == "projectile_launch"
                and event["source"] == "attacker"
                for event in result["trace"]
            )
        )

    def test_weapon_death_preserves_the_already_launched_hit_before_the_blast(self):
        scene = death_scene(
            [
                synthetic_unit(x=6.5, damage=10, range=10),
                synthetic_structure(damage=100, range=10, attack_interval_seconds=100),
            ]
        )
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["tower"]["hp"], 40)
        self.assertEqual(result["actors"]["attacker"]["death_time"], 0)

    def test_delayed_damage_checks_protection_at_impact(self):
        scene = death_scene(
            effects=[
                damage(),
                {
                    "id": "protect",
                    "kind": "invulnerability",
                    "time_seconds": 0.5,
                    "targets": ["tower"],
                    "duration_seconds": 1,
                },
            ]
        )
        scene["actors"][0]["death_model"] = death_model(delay=1)
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["tower"]["hp"], 100)
        self.assertEqual(result["death_effects"]["pending_effects_at_horizon"], [])

    def test_future_spawn_can_enter_a_death_area_before_its_impact(self):
        newcomer = synthetic_unit(
            "newcomer",
            team="defense",
            x=6.5,
            damage=0,
            spawn_seconds="controlled",
            layer="air",
            movement="air",
        )
        scene = death_scene(
            [
                synthetic_unit(x=6.5, damage=1, range=10),
                synthetic_structure(),
                newcomer,
            ],
            [
                damage(),
                {
                    "id": "enter",
                    "kind": "deploy",
                    "time_seconds": 0.5,
                    "targets": ["newcomer"],
                    "positions": {"newcomer": {"x": 6.5, "y": 3.5}},
                },
            ],
        )
        model = death_model(delay=1)
        model["effects"][0]["area"].update(
            {"target_kinds": ["unit"], "target_layers": ["air"], "radius": 0.1}
        )
        scene["actors"][0]["death_model"] = model
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["newcomer"]["hp"], 50)
        self.assertEqual(result["actors"]["tower"]["hp"], 100)

    def test_offset_is_anchored_to_death_position_after_movement(self):
        scene = death_scene(
            [
                synthetic_unit(damage=1),
                synthetic_structure(),
                synthetic_structure("receiver", x=4),
            ],
            [damage(time=1)],
        )
        scene["actors"][0]["death_model"]["effects"][0]["area"].update(
            {"offset_x": 2, "radius": 0.1}
        )
        result = simulate_spatial(scene)
        self.assertAlmostEqual(result["actors"]["attacker"]["x"], 2.5)
        self.assertEqual(result["actors"]["receiver"]["hp"], 50)
        release = next(
            event
            for event in result["trace"]
            if event.get("event") == "death_effect_release"
        )
        self.assertAlmostEqual(release["area"]["x"], 4.5)

    def test_same_time_deaths_share_one_damage_generation(self):
        scene = death_scene(effects=[damage(), damage("second")])
        second = deepcopy(scene["actors"][0])
        second["id"] = "second"
        scene["actors"].append(second)
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["tower"]["death_time"], 0)
        impacts = [
            event
            for event in result["trace"]
            if event.get("event") == "death_effect_impact"
        ]
        self.assertEqual(len(impacts), 2)
        self.assertTrue(all(event["targets"] == ["tower"] for event in impacts))

    def test_death_cascade_settles_each_instance_once_without_resurrection(self):
        scene = death_scene(
            [
                synthetic_unit(x=6.5, damage=1, range=10),
                synthetic_structure(),
                synthetic_unit("survivor", x=6.5, damage=1, range=10),
            ],
            [damage()],
        )
        scene["actors"][0]["death_model"] = death_model(amount=100)
        retaliation = death_model(amount=100)
        retaliation["effects"][0]["area"].update(
            {"target_team": "attack", "target_kinds": ["unit"], "radius": 2}
        )
        scene["actors"][1]["death_model"] = retaliation
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["survivor"]["death_time"], 0)
        self.assertEqual(
            result["death_effects"]["emitted_instances"], ["attacker", "tower"]
        )

    def test_frozen_source_still_releases_its_delayed_death_effect(self):
        scene = death_scene(
            effects=[
                {
                    "id": "frozen",
                    "kind": "freeze",
                    "time_seconds": 0,
                    "targets": ["attacker"],
                    "duration_seconds": 3,
                },
                damage(time=0.25),
            ]
        )
        model = death_model(delay=0.75)
        effect = model["effects"][0]
        effect.update({"kind": "area_freeze", "duration_seconds": 1})
        del effect["amount"]
        scene["actors"][0]["death_model"] = model
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["tower"]["frozen_until"], 2)

    def test_effects_beyond_horizon_remain_pending_without_forced_impact(self):
        scene = death_scene(effects=[damage()])
        scene["actors"][0]["death_model"] = death_model(delay=5)
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["tower"]["hp"], 100)
        self.assertEqual(
            result["death_effects"]["pending_effects_at_horizon"][0]["arrival_seconds"],
            5,
        )

    def test_legacy_rules_cannot_ignore_death_behavior(self):
        from clashlab.healing import RULESET as SUPPORT_RULESET, SUPPORT_RULES

        scene = death_scene()
        scene["ruleset"] = SUPPORT_RULESET
        scene["model_rules"] = deepcopy(SUPPORT_RULES)
        with self.assertRaises(InputError):
            simulate_spatial(scene)

    def test_undeclared_randomness_duplicate_ids_and_unsupported_lifecycle_rejected(
        self,
    ):
        for change in ("random", "duplicate", "summon"):
            scene = death_scene()
            model = scene["actors"][0]["death_model"]
            if change == "random":
                model["random_offsets"] = True
            elif change == "duplicate":
                model["effects"].append(deepcopy(model["effects"][0]))
            else:
                model["effects"][0]["kind"] = "summon"
            with self.subTest(change=change), self.assertRaises(InputError):
                simulate_spatial(scene)


def air_death_parameters(entity_id, basis=None):
    return {
        "source": SOURCE,
        "statistic_basis": basis
        or (
            "snapshot_single_blast"
            if entity_id == "dragon-rider"
            else "snapshot_deathDamage_is_per_impact_hypothesis"
        ),
        "damage_multiplier": 1,
        "impacts": [
            {
                "id": "impact-0",
                "source": SOURCE,
                "delay_seconds": 0,
                "offset_x": 0,
                "offset_y": 0,
                "radius": 2,
                "target_kinds": ["defense", "building"],
                "target_layers": ["ground"],
                "damage_fraction": 1,
            }
        ],
    }


class AirAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def air_sector(self, entity_id):
        troop = entity_instance(
            "air", entity_id, 4 if entity_id == "dragon-rider" else 7, "attack"
        )
        troop["death_parameters"] = air_death_parameters(entity_id)
        if entity_id == "electro-dragon":
            troop["readiness_policy"] = {
                "selection": "absolute_first_attack_seconds_hypothesis",
                "source": SOURCE,
            }
            troop["attack_parameters"].update(
                {
                    "damage_multipliers": [1, 0.8, 0.6, 0.4, 0.2],
                    "jump_range": 1,
                    "jump_metric": "footprint_distance",
                    "jump_delay_seconds": 0,
                    "tie_break": "distance_then_instance_id",
                    "allow_protected_links": True,
                }
            )
        else:
            troop["target_layer_policy"] = {
                "selection": "snapshot_ground_only_hypothesis",
                "source": SOURCE,
            }
        structure = entity_instance(
            "tower", "cannon", 21, "defense", first_attack_seconds=100
        )
        spec = sector(self.catalog, [troop, structure])
        spec.update(
            {
                "scope": DEATH_SCOPE,
                "model_rules": deepcopy(DEATH_RULES),
                "healing_stacking": {"source": SOURCE, "groups": {}},
                "healing_spells": [],
            }
        )
        return spec

    def test_electro_dragon_imports_chain_statistics_and_explicit_death_mapping(self):
        compiled = compile_entity_scene(self.air_sector("electro-dragon"), self.catalog)
        actor = compiled["scene"]["actors"][0]
        self.assertEqual(actor["hitpoints"], 5700)
        self.assertEqual(actor["damage"], 1540)
        self.assertEqual(actor["speed"], 1.625)
        self.assertEqual(actor["death_model"]["effects"][0]["amount"], 125)
        self.assertEqual(len(actor["attack_model"]["damage_multipliers"]), 5)
        self.assertFalse(compiled["full_game_prediction"])

    def test_total_quantity_branch_requires_complete_declared_damage_allocation(self):
        spec = self.air_sector("electro-dragon")
        parameters = spec["entities"][0]["death_parameters"]
        parameters["statistic_basis"] = "snapshot_deathDamage_is_total_hypothesis"
        second = deepcopy(parameters["impacts"][0])
        second["id"] = "impact-1"
        parameters["impacts"].append(second)
        with self.assertRaises(InputError):
            compile_entity_scene(spec, self.catalog)
        for impact in parameters["impacts"]:
            impact["damage_fraction"] = 0.5
        actor = compile_entity_scene(spec, self.catalog)["scene"]["actors"][0]
        self.assertEqual(
            [effect["amount"] for effect in actor["death_model"]["effects"]],
            [62.5, 62.5],
        )

    def test_dragon_rider_keeps_defense_preference_and_explicit_layer_branch(self):
        spec = self.air_sector("dragon-rider")
        actor = compile_entity_scene(spec, self.catalog)["scene"]["actors"][0]
        self.assertEqual(actor["target_priority_tiers"], [["defense"], ["building"]])
        self.assertEqual(actor["target_layers"], ["ground"])
        self.assertEqual(actor["death_model"]["effects"][0]["amount"], 1000)
        spec["entities"][0]["target_layer_policy"][
            "selection"
        ] = "historical_ground_and_air_hypothesis"
        actor = compile_entity_scene(spec, self.catalog)["scene"]["actors"][0]
        self.assertEqual(actor["target_layers"], ["ground", "air"])

    def test_missing_death_mapping_readiness_and_excessive_chain_cannot_pass(self):
        for change in ("death", "readiness", "chain"):
            spec = self.air_sector("electro-dragon")
            troop = spec["entities"][0]
            if change == "death":
                del troop["death_parameters"]
            elif change == "readiness":
                del troop["readiness_policy"]
            else:
                troop["attack_parameters"]["damage_multipliers"].append(0.1)
            with self.subTest(change=change), self.assertRaises(InputError):
                compile_entity_scene(spec, self.catalog)


if __name__ == "__main__":
    unittest.main()
