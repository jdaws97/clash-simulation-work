"""Reactive towers through compilation, coupled scheduling and battle profiles."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene, partial_adapter_status
from clashlab.battle_modifiers import apply_battle_modifiers
from clashlab.catalog import Catalog
from clashlab.closed_loop import simulate_closed_loop
from clashlab.common import InputError, read_json
from clashlab.defending_hero_rules import RULES as OLD_RULES, SCOPE as OLD_SCOPE
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial
from clashlab.spell_tower_rules import RULES, RULESET, SCOPE

from test_adapters import entity_instance
from test_battle_modifiers import modifier_policy
from test_closed_loop import area_plan_and_profile
from test_combat import synthetic_pattern
from test_full_battle import fixture
from test_indirect_defenses import damage_command, fixed_tank, indirect_sector
from test_spell_towers import spell_tower_instance


ROOT = Path(__file__).resolve().parents[1]


def tower_sector(catalog, entities, **changes):
    return indirect_sector(
        catalog, entities, scope=SCOPE, model_rules=deepcopy(RULES), **changes
    )


def events(result, kind, source=None):
    return [
        event
        for event in result["trace"]
        if event.get("event") == kind
        and (source is None or event.get("source") == source)
    ]


def cannon(**changes):
    return entity_instance("cannon", "cannon", 1, "defense", x=9, y=4, **changes)


class SpellTowerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.mode_rules = read_json(ROOT / "data" / "mode-rules.json")

    def compile(self, entities, **changes):
        return compile_entity_scene(
            tower_sector(self.catalog, entities, **changes), self.catalog
        )

    def run_scene(self, entities, **changes):
        return simulate_spatial(self.compile(entities, **changes)["scene"])

    def tank(self, **changes):
        return fixed_tank(x=13.5, y=5.5, **changes)

    def test_registered_modes_are_level_gated_and_earthquake_needs_new_scope(self):
        entity = self.catalog.entity("spell-tower")
        self.assertTrue(partial_adapter_status(entity, 1, mode="rage")["available"])
        self.assertFalse(partial_adapter_status(entity, 1, mode="poison")["available"])
        self.assertTrue(
            partial_adapter_status(entity, 4, mode="earthquake")["available"]
        )
        self.assertFalse(
            partial_adapter_status(entity, 3, mode="earthquake")["available"]
        )
        for mode in ("rage", "poison", "invisibility"):
            compiled = self.compile([spell_tower_instance(mode), self.tank()])
            self.assertEqual(compiled["scene"]["ruleset"], RULESET)
            actor = compiled["scene"]["actors"][0]
            self.assertEqual(actor["attack_model"]["kind"], "none")
            self.assertEqual(actor["hitpoints"], 3100)
            self.assertFalse(compiled["full_game_prediction"])
        with self.assertRaises(InputError):
            self.compile([spell_tower_instance("earthquake", level=4, town_hall=17)])

    def test_old_scope_rejects_raw_and_compiled_tower_models(self):
        entities = [spell_tower_instance(), self.tank()]
        specification = tower_sector(self.catalog, entities)
        specification.update(scope=OLD_SCOPE, model_rules=deepcopy(OLD_RULES))
        with self.assertRaisesRegex(InputError, "v18"):
            compile_entity_scene(specification, self.catalog)
        scene = self.compile(entities)["scene"]
        scene.update(
            ruleset="spatial-defending-heroes-kernel-v17",
            model_rules=deepcopy(OLD_RULES),
        )
        with self.assertRaisesRegex(InputError, "v18"):
            simulate_spatial(scene)

    def test_rage_cast_boundary_boosts_weapon_once_without_firing_a_weapon(self):
        entities = [spell_tower_instance(), cannon(), self.tank()]
        for step in (0.7, 0.04):
            result = self.run_scene(
                entities, duration_seconds=2, maximum_step_seconds=step
            )
            releases = events(result, "spell_tower_field_release")
            self.assertEqual([event["time_seconds"] for event in releases], [1.2])
            hits = events(result, "projectile_impact", "cannon")
            baseline = self.catalog.level("cannon", 1)["stats"]["normal"][
                "damagePerShot"
            ]
            self.assertTrue(any(event["time_seconds"] < 1.2 for event in hits))
            self.assertTrue(any(event["time_seconds"] > 1.2 for event in hits))
            for event in hits:
                factor = 1.6 if event["time_seconds"] >= 1.2 else 1
                self.assertAlmostEqual(event["damage"], baseline * factor)
            self.assertFalse(events(result, "projectile_launch", "spell-tower"))
            self.assertIn(
                "spell_tower_state", result["frames"][-1]["actors"]["spell-tower"]
            )

    def test_freeze_cancels_cast_and_restarts_after_thaw(self):
        result = self.run_scene(
            [spell_tower_instance(), self.tank()],
            duration_seconds=4,
            maximum_step_seconds=0.9,
            effects=[
                {
                    "id": "freeze-cast",
                    "kind": "freeze",
                    "time_seconds": 0.5,
                    "targets": ["spell-tower"],
                    "duration_seconds": 1,
                }
            ],
        )
        self.assertEqual(len(events(result, "spell_tower_cast_cancelled")), 1)
        self.assertAlmostEqual(
            events(result, "spell_tower_launch")[0]["time_seconds"], 2.7
        )

    def test_poison_first_pulse_settles_at_release_and_survives_source_death(self):
        tower = spell_tower_instance("poison")
        result = self.run_scene(
            [tower, self.tank()],
            duration_seconds=2.3,
            maximum_step_seconds=0.8,
            effects=[damage_command("spell-tower", 1.3, 10000)],
        )
        pulses = events(result, "hazard_pulse")
        self.assertEqual(
            [round(event["time_seconds"], 6) for event in pulses], [1.2, 1.7, 2.2]
        )
        self.assertEqual(
            result["spell_towers"]["states"]["spell-tower"]["released_count"], 1
        )
        self.assertEqual(
            result["actors"]["tank"]["maximum_hp"] - result["actors"]["tank"]["hp"], 90
        )

    def test_ready_death_release_and_first_pulse_share_the_death_timestamp(self):
        tower = spell_tower_instance("poison")
        result = self.run_scene(
            [tower, self.tank()],
            duration_seconds=0.3,
            effects=[damage_command("spell-tower", 0.1, 10000)],
        )
        self.assertEqual(
            events(result, "spell_tower_field_release")[0]["time_seconds"], 0.1
        )
        self.assertEqual(events(result, "hazard_pulse")[0]["time_seconds"], 0.1)
        self.assertEqual(
            result["spell_towers"]["states"]["spell-tower"]["released_count"], 1
        )

    def test_invisibility_stops_new_primary_attacks_without_granting_immunity(self):
        tower = spell_tower_instance("invisibility")
        tower["spell_tower_parameters"]["cast"]["delay_seconds"] = 0
        tank = self.tank(first_attack_seconds=0)
        durable_cannon = cannon(first_attack_seconds=100)
        durable_cannon["modifiers"]["hitpoints_multiplier"] = 10
        result = self.run_scene([tower, durable_cannon, tank], duration_seconds=3)
        launches = events(result, "projectile_launch", "tank")
        self.assertEqual(len(launches), 1)
        self.assertEqual(result["actors"]["cannon"]["immune_until"], 0)
        self.assertGreater(
            result["frames"][-1]["actors"]["cannon"]["spell_tower_untargetable_until"],
            3,
        )

    def test_released_projectile_hits_after_invisibility_begins(self):
        tower = spell_tower_instance("invisibility")
        tower["spell_tower_parameters"]["cast"]["delay_seconds"] = 0
        tank = self.tank(first_attack_seconds=0)
        tank["attack_parameters"]["projectile"] = {
            "timing": "launch_distance_delay",
            "speed_tiles_per_second": 2,
            "destination": "locked_actor_center_at_impact",
            "hit_radius": 0,
        }
        result = self.run_scene(
            [tower, cannon(first_attack_seconds=100), tank],
            duration_seconds=2,
            effects=[damage_command("cannon", 0.1, 1)],
        )
        hits = events(result, "projectile_impact", "tank")
        self.assertEqual(len(hits), 1)
        self.assertGreater(hits[0]["time_seconds"], 0.1)
        self.assertGreater(hits[0]["damage"], 0)
        self.assertEqual(len(events(result, "projectile_launch", "tank")), 1)

    def test_poison_global_profile_scales_once_and_preserves_status_and_inputs(self):
        tower = spell_tower_instance("poison")
        tank = entity_instance(
            "tank", "minion", 12, "attack", x=13.5, y=5.5, first_attack_seconds=100
        )
        original = self.compile([tower, tank], duration_seconds=1.3)["scene"]
        unchanged = deepcopy(original)
        result = apply_battle_modifiers(
            original, modifier_policy(), self.catalog, self.mode_rules
        )
        self.assertEqual(original, unchanged)
        changed = result["scene"]["actors"][0]["spell_tower_model"]["effect"]
        self.assertEqual(changed["maximum_dps"], 72)
        self.assertEqual(changed["movement_multiplier"], 0.65)
        self.assertEqual(changed["attack_rate_multiplier"], 0.75)
        combat = simulate_spatial(result["scene"])
        self.assertEqual(
            events(combat, "hazard_pulse")[0]["requested_damage_per_target"], 36
        )
        paths = [
            change["path"]
            for change in result["application"]["actors"][0]["statistics"]
        ]
        self.assertEqual(paths.count(["spell_tower_model", "effect", "maximum_dps"]), 1)
        with self.assertRaises(InputError):
            apply_battle_modifiers(
                result["scene"], modifier_policy(), self.catalog, self.mode_rules
            )
        unchanged_policy = modifier_policy(impact_hazard_damage_policy="unchanged")
        unchanged_result = apply_battle_modifiers(
            original, unchanged_policy, self.catalog, self.mode_rules
        )
        self.assertEqual(
            unchanged_result["scene"]["actors"][0]["spell_tower_model"]["effect"][
                "maximum_dps"
            ],
            60,
        )

    def test_pre_scaled_poison_rejects_global_profile(self):
        tower = spell_tower_instance("poison")
        tower["spell_tower_parameters"]["effect"]["damage_multiplier"] = 1.2
        tank = entity_instance("tank", "minion", 12, "attack", x=13.5, y=5.5)
        scene = self.compile([tower, tank])["scene"]
        with self.assertRaisesRegex(InputError, "neutral"):
            apply_battle_modifiers(
                scene, modifier_policy(), self.catalog, self.mode_rules
            )

    def test_full_battle_includes_bound_tower_and_modifier_audit(self):
        inputs = fixture(self.catalog, time_limit=0.2)
        specification, _, _, layout = inputs
        tower = spell_tower_instance("poison", x=5, y=8)
        tower["spell_tower_parameters"]["cast"]["delay_seconds"] = 0
        scene = specification["entity_scene"]
        scene.update(scope=SCOPE, model_rules=deepcopy(RULES), buff_spells=[])
        scene["entities"].append(tower)
        layout["inventory"]["spell-tower"] = 1
        layout["buildings"].append(
            {
                "instance": tower["id"],
                "id": "spell-tower",
                "level": 3,
                "x": 5,
                "y": 8,
                "mode": "poison",
                "counts_for_destruction": True,
            }
        )
        specification["battle_modifier_policy"] = modifier_policy()
        compiled = compile_full_battle(
            *inputs, self.catalog, mode_rules=self.mode_rules
        )
        self.assertEqual(compiled["compiled"]["scope"], SCOPE)
        result = simulate_full_battle(*inputs, self.catalog, mode_rules=self.mode_rules)
        self.assertEqual(result["battle_modifier_audit"]["profile_id"], "legend_i")
        self.assertEqual(
            result["combat"]["spell_towers"]["states"]["spell-tower"]["launched_count"],
            1,
        )
        self.assertFalse(result["full_game_prediction"])

    def test_closed_loop_area_control_is_accepted_and_cancels_pending_cast(self):
        tower = spell_tower_instance(id="tower")
        scene = self.compile(
            [tower, self.tank(actor_id="attacker")], duration_seconds=3
        )["scene"]
        plan, profile = area_plan_and_profile()
        step = plan["streams"][0]["steps"][0]
        step["all_conditions"] = [
            {
                "actor_id": "attacker",
                "field": "active",
                "operator": "equals",
                "value": True,
            }
        ]
        step["action"]["area"].update(x=7, y=5, radius=2)
        result = simulate_closed_loop(scene, plan, profile, seed=7, trials=1)[
            "samples"
        ][0]
        self.assertEqual(len(events(result["combat"], "spell_tower_cast_cancelled")), 1)
        self.assertEqual(result["control"]["remaining_resources"]["freeze_casts"], 0)

    def test_invisibility_blocks_fresh_chain_links(self):
        tower = spell_tower_instance("invisibility")
        tower["spell_tower_parameters"]["cast"]["delay_seconds"] = 0
        outside = entity_instance(
            "outside", "cannon", 10, "defense", x=13, y=4, first_attack_seconds=100
        )
        tank = self.tank(first_attack_seconds=0.2)
        tank["x"] = 17.5
        scene = self.compile(
            [tower, cannon(first_attack_seconds=100), outside, tank],
            duration_seconds=0.3,
            effects=[damage_command("cannon", 0.1, 1)],
        )["scene"]
        attacker = next(actor for actor in scene["actors"] if actor["id"] == "tank")
        attacker["attack_model"] = synthetic_pattern("chain", jump_range=10)
        attacker["damage"] = 10
        result = simulate_spatial(scene)
        hits = events(result, "projectile_impact", "tank")
        self.assertEqual([event["target"] for event in hits], ["outside"])

    def test_moving_enemy_triggers_at_circle_entry_between_solver_steps(self):
        times = []
        for step in (0.9, 0.025):
            attacker = entity_instance(
                "moving", "minion", 12, "attack", x=20.5, y=5, first_attack_seconds=100
            )
            result = self.run_scene(
                [spell_tower_instance(), attacker],
                duration_seconds=3,
                maximum_step_seconds=step,
                recording_interval_seconds=3,
            )
            launch = events(result, "spell_tower_launch")[0]
            times.append(launch["time_seconds"])
        self.assertAlmostEqual(times[0], times[1], places=7)
        self.assertAlmostEqual(times[0], 2.325, places=7)


if __name__ == "__main__":
    unittest.main()
