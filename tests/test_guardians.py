"""TH18 Hall/Guardian separation, exact lifecycle boundaries and role effects."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.battle_modifiers import apply_battle_modifiers
from clashlab.buffs import damage_multiplier
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.full_battle import (
    _bind_defenders,
    compile_full_battle,
    simulate_full_battle,
)
from clashlab.guardian_rules import RULES, RULESET, SCOPE
from clashlab.guardians import GuardianCombat
from clashlab.rates import movement_speed
from clashlab.hazards import PulsedHazards
from clashlab.spatial import _blocked, _load_actors, _select_target, simulate_spatial

from test_adapters import entity_instance, projectile
from test_battle_modifiers import modifier_policy
from test_defending_heroes import defender_instance, defender_sector
from test_full_battle import fixture as full_battle_fixture
from test_hit_status import ice_instance
from test_indirect_defenses import damage_command, fixed_tank
from test_townhalls import hazard
from test_spell_towers import spell_tower_instance


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "explicit-guardian-fixture-not-replay-calibration"


def guardian_instance(entity="longshot", **changes):
    shot = projectile()
    shot["inactive_primary_policy"] = "fizzle"
    instance = entity_instance(
        "guardian",
        entity,
        1,
        "defense",
        town_hall=18,
        x=19.5,
        y=11.5,
        spawn_seconds="controlled",
        counts_for_destruction=False,
        wall_parameters={"kind": "avoid", "source": SOURCE},
        attack_parameters={
            "projectile": shot,
            "splash_layer_policy": "all_declared_target_layers",
            "radius_multiplier": 1,
        },
        guardian_parameters={
            "source": SOURCE,
            "hall_id": "hall",
            "statistics_mapping": "snapshot_guardian_without_hero_equipment",
            "activation": {
                "trigger_radius_multiplier": 1,
                "trigger_layers": ["ground", "air"],
                "delay_seconds": 0.2,
                "trigger_loss": "latched",
                "freeze": "pause_activation_clock_at_hall_center",
                "hall_death": "activate",
            },
            "acquisition_radius_tiles": 12,
            "leash_radius_tiles": 22,
            "home": {"x": 19.5, "y": 11.5},
            "patrol": {"selection": "ordered_loop", "waypoints": []},
            "targeting": "nearest_reachable_retained_primary_or_received_damage_within_leash",
            "return": "home_before_reacquisition_preserve_attack_clock",
            "healing": "none",
            "death": "permanent_for_battle",
        },
    )
    if entity == "longshot":
        instance["death_parameters"] = {
            "source": SOURCE,
            "delay_seconds": 0.3,
            "damage_multiplier": 1,
            "radius_multiplier": 1,
            "target_layers": ["ground", "air"],
        }
    elif entity == "smasher":
        instance["smasher_parameters"] = {
            "source": SOURCE,
            "hall_rage": {
                "damage_basis": "snapshot_rageDamageIncrease_percent_bonus",
                "movement_basis": "snapshot_rageSpeedIncrease_additive_units",
                "duration": "until_permanent_death",
                "composition": "multiply_damage_add_movement_with_other_sources",
            },
            "dropped_rage": {
                "source": SOURCE,
                "radius_tiles": 5,
                "duration_seconds": 1,
                "damage_multiplier": 1.5,
                "movement_bonus_tiles_per_second": 1,
                "target_kinds": ["unit", "defense"],
                "target_layers": ["ground", "air"],
                "recipient_classes": ["defense", "defending_hero", "defending_troop"],
                "membership": "center_distance_continuous_no_linger",
                "composition": "multiply_damage_add_movement_with_other_sources",
                "persistence": "fixed_field_until_expiry_independent_of_hall",
            },
        }
    instance.update(changes)
    return instance


def guardian_hall(guardian=None, **changes):
    guardian = guardian or guardian_instance()
    instance = entity_instance(
        "hall",
        "town-hall",
        18,
        "defense",
        town_hall=18,
        x=20,
        y=10,
        mode="guardian",
        statistics_mode="none",
        attack_parameters={},
        guardian_binding={
            "source": SOURCE,
            "actor_id": guardian["id"],
            "entity": guardian["entity"],
            "level": guardian["level"],
        },
    )
    instance.update(changes)
    return instance


def guardian_sector(catalog, entities, **changes):
    return defender_sector(
        catalog, entities, scope=SCOPE, model_rules=deepcopy(RULES), **changes
    )


class GuardianTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def compile(self, entities, **changes):
        if not any(actor["team"] == "attack" for actor in entities):
            # Death-area validation requires the opposing team to exist. This
            # distant, stationary fixture unit stays outside Guardian triggers.
            entities = [*entities, fixed_tank(x=49.5, y=27.5)]
        return compile_entity_scene(
            guardian_sector(self.catalog, entities, **changes), self.catalog
        )

    def simulate(self, entities, **changes):
        return simulate_spatial(self.compile(entities, **changes)["scene"])

    def runtime(self, entities, **changes):
        scene = self.compile(entities, **changes)["scene"]
        actors = _load_actors(scene, scene["width"], scene["height"])
        runtime = GuardianCombat(actors, _select_target, scene)
        return actors, runtime, []

    def test_hall_is_weaponless_and_each_guardian_uses_distinct_catalog_statistics(
        self,
    ):
        for entity, hp, damage, speed, radius in (
            ("longshot", 7000, 594, 1.5, 1),
            ("smasher", 12000, 900, 2.5, 2.5),
        ):
            with self.subTest(entity=entity):
                guardian = guardian_instance(entity)
                scene = self.compile([guardian_hall(guardian), guardian])["scene"]
                hall, actor = scene["actors"][:2]
                self.assertEqual(scene["ruleset"], RULESET)
                self.assertEqual((hall["hitpoints"], hall["damage"]), (10800, 0))
                self.assertNotIn("town_hall_model", hall)
                self.assertNotIn("artillery_model", hall)
                self.assertEqual(
                    (actor["hitpoints"], actor["damage"], actor["speed"]),
                    (hp, damage, speed),
                )
                self.assertEqual(actor["attack_model"]["radius"], radius)
                self.assertEqual(actor["hazard_class"], "guardian")
                self.assertEqual(actor["healing_class"], "guardian")
                self.assertEqual(actor["buff_class"], "guardian")
                self.assertNotIn("hero_model", actor)
                self.assertFalse(actor["counts_for_destruction"])

    def test_th18_hall_and_guardian_are_both_required_once(self):
        guardian = guardian_instance()
        hall = guardian_hall(guardian)
        for entities in (
            [hall],
            [guardian],
            [hall, guardian, guardian_instance(id="extra")],
        ):
            with self.subTest(count=len(entities)):
                with self.assertRaisesRegex(InputError, "exactly one"):
                    self.compile(entities)

    def test_mismatched_binding_level_and_exterior_point_fail_closed(self):
        guardian = guardian_instance()
        hall = guardian_hall(guardian)
        hall["guardian_binding"]["level"] = 2
        with self.assertRaisesRegex(InputError, "runtime identity"):
            self.compile([hall, guardian])
        guardian["x"] = 21.5
        guardian["guardian_parameters"]["home"]["x"] = 21.5
        with self.assertRaisesRegex(InputError, "exterior"):
            self.compile([guardian_hall(guardian), guardian])

    def test_logger_absence_and_incomplete_smasher_rage_are_rejected(self):
        hall = guardian_hall()
        hall["guardian_binding"]["entity"] = "logger"
        with self.assertRaisesRegex(InputError, "Logger"):
            self.compile([hall, guardian_instance()])
        hall["guardian_binding"] = {"source": SOURCE, "absence": "upgrading"}
        with self.assertRaises(InputError):
            self.compile([hall])
        guardian = guardian_instance("smasher")
        del guardian["smasher_parameters"]["dropped_rage"]["radius_tiles"]
        with self.assertRaisesRegex(InputError, "complete explicit"):
            self.compile([guardian_hall(guardian), guardian])

    def test_emergence_is_step_invariant_and_dormant_unit_is_untargetable(self):
        entities = [guardian_hall(), guardian_instance(), fixed_tank(x=10.5, y=11.5)]
        for step in (0.01, 0.8):
            with self.subTest(step=step):
                result = self.simulate(
                    entities, maximum_step_seconds=step, duration_seconds=0.7
                )
                state = result["guardians"]["states"]["guardian"]
                self.assertAlmostEqual(state["triggered_at"], 0)
                self.assertAlmostEqual(state["emerged_at"], 0.2)
                launches = [
                    event
                    for event in result["trace"]
                    if event["event"] == "projectile_launch"
                    and event["source"] == "guardian"
                ]
                self.assertAlmostEqual(launches[0]["time_seconds"], 0.2)

    def test_freeze_before_trigger_prevents_activation_until_thaw(self):
        freeze = {
            "id": "freeze",
            "kind": "area_freeze",
            "time_seconds": 0,
            "duration_seconds": 0.5,
            "area": {
                "x": 22,
                "y": 12,
                "radius": 0.2,
                "target_team": "defense",
                "target_kinds": ["unit", "building"],
                "target_layers": ["ground", "air"],
            },
        }
        result = self.simulate(
            [guardian_hall(), guardian_instance(), fixed_tank(x=10.5, y=11.5)],
            effects=[freeze],
            duration_seconds=0.8,
        )
        state = result["guardians"]["states"]["guardian"]
        self.assertAlmostEqual(state["triggered_at"], 0.5)
        self.assertAlmostEqual(state["emerged_at"], 0.7)

    def test_overlapping_freeze_pauses_only_unfinished_emergence_work(self):
        effects = [
            {
                "id": "first",
                "kind": "freeze",
                "targets": ["hall"],
                "time_seconds": 0.1,
                "duration_seconds": 0.5,
            },
            {
                "id": "second",
                "kind": "freeze",
                "targets": ["hall"],
                "time_seconds": 0.2,
                "duration_seconds": 0.6,
            },
        ]
        result = self.simulate(
            [guardian_hall(), guardian_instance(), fixed_tank(x=10.5, y=11.5)],
            effects=effects,
            duration_seconds=1,
        )
        self.assertAlmostEqual(
            result["guardians"]["states"]["guardian"]["emerged_at"], 0.9
        )

    def test_latched_trigger_survives_enemy_loss_and_hall_death_triggers_idle_guardian(
        self,
    ):
        result = self.simulate(
            [guardian_hall(), guardian_instance(), fixed_tank(x=10.5, y=11.5)],
            effects=[damage_command("tank", 0.1, 10000000)],
            duration_seconds=0.4,
        )
        self.assertAlmostEqual(
            result["guardians"]["states"]["guardian"]["emerged_at"], 0.2
        )
        result = self.simulate(
            [guardian_hall(), guardian_instance()],
            effects=[damage_command("hall", 0.3, 10000000)],
            duration_seconds=0.7,
        )
        self.assertAlmostEqual(
            result["guardians"]["states"]["guardian"]["emerged_at"], 0.5
        )

    def test_external_deployment_and_missing_attacker_response_are_rejected(self):
        effect = {
            "id": "deploy",
            "kind": "deploy",
            "time_seconds": 0,
            "targets": ["guardian"],
            "positions": {"guardian": {"x": 19.5, "y": 11.5}},
        }
        with self.assertRaisesRegex(InputError, "only emerge"):
            self.compile([guardian_hall(), guardian_instance()], effects=[effect])
        with self.assertRaisesRegex(InputError, "every attacking"):
            self.compile(
                [guardian_hall(), guardian_instance(), fixed_tank()], responses={}
            )

    def test_longshot_death_blast_is_once_delayed_and_protection_is_respected(self):
        entities = [guardian_hall(), guardian_instance(), fixed_tank(x=18.5, y=11.5)]
        effects = [damage_command("guardian", 0.4, 100000)]
        result = self.simulate(entities, effects=effects, duration_seconds=1)
        tank = result["actors"]["tank"]
        self.assertAlmostEqual(tank["maximum_hp"] - tank["hp"], 594 + 1000)
        self.assertEqual(result["guardians"]["states"]["guardian"]["phase"], "dead")
        effects.append(
            {
                "id": "protect",
                "kind": "invulnerability",
                "time_seconds": 0.5,
                "targets": ["tank"],
                "duration_seconds": 1,
            }
        )
        protected = self.simulate(entities, effects=effects, duration_seconds=1)
        self.assertAlmostEqual(
            protected["actors"]["tank"]["maximum_hp"]
            - protected["actors"]["tank"]["hp"],
            594,
        )

    def test_smasher_hall_rage_scales_damage_and_speed_once_without_attack_rate_change(
        self,
    ):
        guardian = guardian_instance("smasher")
        actors, runtime, trace = self.runtime(
            [guardian_hall(guardian), guardian, fixed_tank(x=18.5, y=11.5)]
        )
        runtime.prepare(actors, 0, trace)
        runtime.prepare(actors, 0.2, trace)
        actor = actors["guardian"]
        actors["hall"]["hp"] = 0
        for time in (0.3, 0.4, 0.5):
            runtime.prepare(actors, time, trace)
        self.assertAlmostEqual(damage_multiplier(actor), 1.6)
        self.assertAlmostEqual(movement_speed(actor), 4)
        self.assertEqual(actor["damage"], 900)
        self.assertEqual(actor["attack_interval_seconds"], 1.8)
        self.assertEqual(
            sum(event["event"] == "smasher_hall_rage" for event in trace), 1
        )

    def test_smasher_death_field_persists_without_hall_and_expires_exactly(self):
        guardian = guardian_instance("smasher")
        cannon = entity_instance("cannon", "cannon", 1, "defense", x=16, y=8)
        actors, runtime, trace = self.runtime(
            [guardian_hall(guardian), guardian, cannon, fixed_tank(x=18.5, y=11.5)]
        )
        runtime.prepare(actors, 0, trace)
        runtime.prepare(actors, 0.2, trace)
        actors["guardian"]["hp"] = 0
        actors["hall"]["hp"] = 0
        runtime.prepare(actors, 0.3, trace)
        self.assertEqual(damage_multiplier(actors["cannon"]), 1.5)
        self.assertEqual(damage_multiplier(actors["tank"]), 1)
        self.assertEqual(runtime.next_boundary(0.3), 1.3)
        runtime.prepare(actors, 1.3, trace)
        self.assertEqual(damage_multiplier(actors["cannon"]), 1)
        self.assertEqual(len(runtime.fields), 1)

    def test_guardian_profile_and_death_damage_scale_separately_from_weaponless_hall(
        self,
    ):
        enemy = entity_instance(
            "enemy",
            "archer",
            1,
            "attack",
            x=49.5,
            y=27.5,
            wall_parameters={"kind": "avoid", "source": SOURCE},
        )
        scene = self.compile([guardian_hall(), guardian_instance(), enemy])["scene"]
        result = apply_battle_modifiers(
            scene,
            modifier_policy(),
            self.catalog,
            read_json(ROOT / "data" / "mode-rules.json"),
        )
        hall, actor = result["scene"]["actors"][:2]
        self.assertEqual(hall["hitpoints"], 10800)
        self.assertAlmostEqual(actor["hitpoints"], 8400)
        self.assertAlmostEqual(actor["damage"], 712.8)
        self.assertEqual(actor["death_model"]["effects"][0]["amount"], 1200)
        self.assertEqual(scene["actors"][1]["hitpoints"], 7000)
        simulate_spatial(result["scene"])

    def test_hall_layout_settings_bind_guardian_as_uncounted_actor(self):
        guardian = guardian_instance()
        hall = guardian_hall(guardian)
        layout = {
            "town_hall": 18,
            "buildings": [
                {
                    "instance": "hall",
                    "id": "town-hall",
                    "level": 18,
                    "x": 20,
                    "y": 10,
                    "counts_for_destruction": True,
                    "settings": {
                        "guardian": {
                            "actor_id": "guardian",
                            "entity": "longshot",
                            "level": 1,
                        }
                    },
                }
            ],
        }
        scene = {"entities": [hall, guardian], "traps": []}
        binding = _bind_defenders(layout, scene, self.catalog)
        self.assertEqual(binding["guardian"]["role"], "guardian")
        self.assertFalse(binding["guardian"]["counts_for_destruction"])
        layout["buildings"][0]["settings"]["guardian"]["level"] = 2
        with self.assertRaisesRegex(InputError, "bindings differ"):
            _bind_defenders(layout, scene, self.catalog)

    def test_exact_trigger_circle_crossing_uses_effective_speed(self):
        actors, runtime, trace = self.runtime(
            [guardian_hall(), guardian_instance(), fixed_tank(x=0.5, y=12)]
        )
        runtime.prepare(actors, 0, trace)
        self.assertAlmostEqual(
            runtime.first_crossing_delay(
                actors["tank"], [(10.5, 12)], 0, 3, effective_speed=2
            ),
            1.25,
        )

    def test_patrol_and_retained_target_return_preserve_cooldown(self):
        guardian = guardian_instance()
        guardian["guardian_parameters"]["activation"]["delay_seconds"] = 0
        guardian["guardian_parameters"]["patrol"]["waypoints"] = [
            {"x": 18.5, "y": 11.5, "wait_seconds": 0.4}
        ]
        tank = fixed_tank(x=3.5, y=11.5)
        actors, runtime, trace = self.runtime([guardian_hall(guardian), guardian, tank])
        runtime.prepare(actors, 0, trace)
        actor = actors["guardian"]
        target, route = runtime.select_target(
            actor, actors, 0, _blocked(actors, 0), 50, 28
        )
        self.assertIsNone(target)
        self.assertEqual(route[-1], (18.5, 11.5))
        actor.update(x=18.5, next_attack=7)
        runtime.select_target(actor, actors, 2 / 3, _blocked(actors, 2 / 3), 50, 28)
        self.assertAlmostEqual(runtime.next_boundary(2 / 3), 2 / 3 + 0.4)
        actors["tank"]["x"] = 10.5
        target, _ = runtime.select_target(
            actor, actors, 0.8, _blocked(actors, 0.8), 50, 28
        )
        self.assertEqual(target["id"], "tank")
        actors["tank"]["hp"] = 0
        target, route = runtime.select_target(
            actor, actors, 0.9, _blocked(actors, 0.9), 50, 28
        )
        self.assertIsNone(target)
        self.assertEqual(route[-1], (19.5, 11.5))
        self.assertEqual(actor["next_attack"], 7)

    def test_active_freeze_preserves_unfinished_attack_clock_across_steps(self):
        effect = {
            "id": "freeze",
            "kind": "freeze",
            "time_seconds": 1,
            "targets": ["guardian"],
            "duration_seconds": 0.5,
        }
        for step in (0.01, 0.8):
            result = self.simulate(
                [guardian_hall(), guardian_instance(), fixed_tank(x=10.5, y=11.5)],
                effects=[effect],
                duration_seconds=2.6,
                maximum_step_seconds=step,
            )
            launches = [
                event["time_seconds"]
                for event in result["trace"]
                if event.get("event") == "projectile_launch"
                and event["source"] == "guardian"
            ]
            self.assertEqual(len(launches), 2)
            self.assertAlmostEqual(launches[0], 0.2)
            self.assertAlmostEqual(launches[1], 2.5)

    def test_ice_golem_death_geometry_freezes_dormant_guardian(self):
        ice = ice_instance(x=22, y=9.5, first_attack_seconds=100)
        result = self.simulate(
            [guardian_hall(), guardian_instance(), ice],
            effects=[damage_command("ice", 0, 100000)],
            duration_seconds=0.5,
        )
        self.assertEqual(result["guardians"]["states"]["guardian"]["phase"], "dormant")
        freeze_events = [
            event
            for event in result["trace"]
            if event.get("event") == "guardian_activation_freeze"
        ]
        self.assertEqual(len(freeze_events), 1)
        self.assertGreater(freeze_events[0]["until_seconds"], 0.5)

    def test_longshot_projectile_survives_guardian_death(self):
        guardian = guardian_instance()
        guardian["attack_parameters"]["projectile"] = {
            "timing": "launch_distance_delay",
            "speed_tiles_per_second": 2,
            "destination": "fixed_target_center_at_launch",
            "hit_radius": 0,
            "inactive_primary_policy": "resolve_at_fixed_launch_position",
        }
        result = self.simulate(
            [guardian_hall(guardian), guardian, fixed_tank(x=10.5, y=11.5)],
            effects=[damage_command("guardian", 0.4, 100000)],
            duration_seconds=5,
        )
        self.assertAlmostEqual(
            result["actors"]["tank"]["maximum_hp"] - result["actors"]["tank"]["hp"], 594
        )
        impacts = [
            event
            for event in result["trace"]
            if event.get("event") == "projectile_impact"
            and event["source"] == "guardian"
        ]
        self.assertEqual(len(impacts), 1)
        self.assertAlmostEqual(impacts[0]["time_seconds"], 4.7)

    def test_guardian_splash_uses_explicit_ground_and_air_membership(self):
        enemies = [
            fixed_tank("ground", x=18.5, y=11.5),
            fixed_tank("air", entity="minion", x=18.5, y=12.2),
        ]
        enemies[1]["modifiers"]["hitpoints_multiplier"] = 10
        result = self.simulate(
            [guardian_hall(), guardian_instance(), *enemies], duration_seconds=0.3
        )
        for actor_id in ("ground", "air"):
            actor = result["actors"][actor_id]
            self.assertAlmostEqual(actor["maximum_hp"] - actor["hp"], 594)

    def test_guardian_hazard_scaling_requires_a_separate_class_and_preserves_status(
        self,
    ):
        guardian = guardian_instance()
        guardian["guardian_parameters"]["activation"]["delay_seconds"] = 0
        actors, runtime, trace = self.runtime(
            [guardian_hall(guardian), guardian, fixed_tank(x=18.5, y=11.5)]
        )
        runtime.prepare(actors, 0, trace)
        field = hazard(
            area={
                "x": 19.5,
                "y": 11.5,
                "radius": 2,
                "target_team": "defense",
                "target_kinds": ["unit"],
                "target_layers": ["ground", "air"],
            }
        )
        with self.assertRaisesRegex(InputError, "separate explicit"):
            PulsedHazards(actors, [field])
        field["guardian_damage_multiplier"] = 0.3
        hazards = PulsedHazards(actors, [field])
        hazards.prepare_status(actors, 0, trace)
        self.assertEqual(hazards.resolve(actors, 0, trace)["guardian"], 1.5)
        self.assertAlmostEqual(movement_speed(actors["guardian"]), 0.75)
        self.assertEqual(actors["guardian"]["_hazard_attack_rate"], 0.5)

    def test_rage_field_exact_exit_and_reentry_change_speed_at_contact(self):
        guardian = guardian_instance("smasher")
        defender = defender_instance(banner_x=4, banner_y=10)
        actors, runtime, trace = self.runtime(
            [guardian_hall(guardian), guardian, defender, fixed_tank(x=18.5, y=11.5)]
        )
        runtime.prepare(actors, 0, trace)
        runtime.prepare(actors, 0.2, trace)
        actors["guardian"]["hp"] = 0
        recipient = actors["defender"]
        recipient.update(x=23.5, y=11.5)
        runtime.prepare(actors, 0.3, trace)
        self.assertEqual(damage_multiplier(recipient), 1.5)
        speed = movement_speed(recipient)
        delay = runtime.first_crossing_delay(recipient, [(26.5, 11.5)], 0.3, 1, speed)
        self.assertAlmostEqual(delay, 1 / speed)
        recipient["x"] = 24.5
        runtime.prepare(actors, 0.3 + delay, trace)
        self.assertEqual(damage_multiplier(recipient), 1)
        self.assertAlmostEqual(movement_speed(recipient), speed - 1)
        # Reverse at the exact contact: a tiny positive boundary step switches
        # the directed side, without waiting for a coarse simulation step.
        reversal = runtime.first_crossing_delay(
            recipient, [(23.5, 11.5)], 0.3 + delay, 0.1, movement_speed(recipient)
        )
        self.assertGreater(reversal, 0)
        self.assertLess(reversal, 1e-6)
        recipient["x"] -= movement_speed(recipient) * reversal
        runtime.prepare(actors, 0.3 + delay + reversal, trace)
        self.assertEqual(damage_multiplier(recipient), 1.5)

    def test_guardian_is_separate_spell_tower_recipient_class(self):
        tower = spell_tower_instance("rage", x=15, y=7)
        tower["spell_tower_parameters"]["recipients"]["unit_classes"].append("guardian")
        result = self.simulate(
            [guardian_hall(), guardian_instance(), tower, fixed_tank(x=18.5, y=11.5)],
            duration_seconds=1.3,
        )
        self.assertGreater(
            result["frames"][-1]["actors"]["guardian"]["spell_tower_damage_multiplier"],
            1,
        )

    def test_th18_full_battle_binds_selected_guardian_without_extra_destruction_credit(
        self,
    ):
        specification, account, army, layout = full_battle_fixture(self.catalog)
        account["town_hall"] = 18
        layout.update(town_hall=18, width=50, height=28)
        guardian = guardian_instance("smasher")
        hall = guardian_hall(guardian)
        attackers = [
            actor
            for actor in specification["entity_scene"]["entities"]
            if actor["team"] == "attack"
        ]
        for actor in attackers:
            actor["town_hall"] = 18
        scene = guardian_sector(
            self.catalog, [hall, guardian, *attackers], duration_seconds=0.5
        )
        specification.update(entity_scene=scene, time_limit_seconds=0.5)
        layout["statistics_policy"] = deepcopy(scene["statistics_policy"])
        layout["buildings"] = [
            {
                "instance": "hall",
                "id": "town-hall",
                "level": 18,
                "x": 20,
                "y": 10,
                "mode": "guardian",
                "counts_for_destruction": True,
                "settings": {
                    "guardian": {
                        "actor_id": "guardian",
                        "entity": "smasher",
                        "level": 1,
                    }
                },
            }
        ]
        compiled = compile_full_battle(
            specification, account, army, layout, self.catalog
        )
        self.assertEqual(
            sum(
                actor["counts_for_destruction"]
                for actor in compiled["compiled"]["scene"]["actors"]
            ),
            1,
        )
        result = simulate_full_battle(
            specification, account, army, layout, self.catalog
        )
        self.assertEqual(result["outcome"]["counted_building_count"], 1)
        self.assertFalse(result["full_game_prediction"])


if __name__ == "__main__":
    unittest.main()
