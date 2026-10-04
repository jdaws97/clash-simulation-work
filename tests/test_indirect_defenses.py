"""Catalog shell compilation plus coupled burst, activation and impact checks."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.battle_modifiers import apply_battle_modifiers
from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError, read_json
from clashlab.indirect_defenses import (
    END_TIMING,
    READINESS_POLICY,
    SINGLE_TIMING,
    START_TIMING,
    IndirectDefenseCombat,
)
from clashlab.indirect_rules import RULES, RULESET, SCOPE
from clashlab.spatial import _load_actors, _select_target, simulate_spatial

from test_adapters import entity_instance
from test_battle_modifiers import modifier_policy
from test_buffs import buff_instance
from test_valkyrie_integration import valkyrie_sector


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "explicit-indirect-fixture-not-game-calibration"


def indirect_instance(entity="mortar", instance_id="weapon", mode="normal", **changes):
    eagle = entity == "eagle-artillery"
    parameters = {
        "source": SOURCE,
        "damage_basis": "snapshot_damagePerShot_is_one_shell",
        "minimum_range": (
            {"basis": "snapshot_minRange", "multiplier": 1}
            if eagle
            else {"basis": "explicit_tiles_hypothesis", "value": 4}
        ),
        "burst_timing": (
            START_TIMING
            if eagle
            else END_TIMING if mode == "gearedUpBurst" else SINGLE_TIMING
        ),
        "targeting": {
            "policy": (
                "maximum_neighborhood_hitpoints"
                if eagle
                else "nearest_eligible_retained"
            ),
            "burst_policy": "retain_primary_until_invalid_then_reacquire",
            **(
                {
                    "radius_tiles": 2,
                    "hitpoint_basis": "current",
                    "population": "eligible_in_acquisition_annulus",
                }
                if eagle
                else {}
            ),
        },
        "readiness_policy": deepcopy(READINESS_POLICY),
        "activation": (
            {
                "source": SOURCE,
                "threshold_basis": "snapshot_activationHousingSpace",
                "threshold_multiplier": 1,
                "delay_seconds": 0,
                "actor_weights": {"tank": 200},
                "command_weights": {},
            }
            if eagle
            else None
        ),
        "shockwave": (
            {
                "source": SOURCE,
                "damage_basis": "snapshot_shockwaveDamagePerHit_is_additional_per_shell",
                "radius_tiles": 2,
                "overlap_policy": "additive_with_shell",
            }
            if eagle
            else None
        ),
    }
    instance = entity_instance(
        instance_id,
        entity,
        7 if eagle else 16,
        "defense",
        x=12,
        y=7,
        mode=mode,
        statistics_mode=mode,
        attack_parameters={
            "source": SOURCE,
            "projectile": {
                "timing": "launch_distance_delay",
                "speed_tiles_per_second": 8,
                "destination": "fixed_target_center_at_launch",
                "hit_radius": 0,
                "inactive_primary_policy": "resolve_at_fixed_launch_position",
            },
            "radius_multiplier": 1,
            "splash_layer_policy": "all_declared_target_layers",
        },
        indirect_parameters=parameters,
    )
    instance.update(changes)
    return instance


def fixed_tank(actor_id="tank", entity="pekka", **changes):
    instance = entity_instance(
        actor_id,
        entity,
        12 if entity == "minion" else 11,
        "attack",
        x=22,
        y=9,
        first_attack_seconds=100,
    )
    # A deliberately long range holds these test targets still without applying
    # artificial Freeze or changing the defense's cadence or activation inputs.
    instance["modifiers"]["range_multiplier"] = 100
    if entity != "minion":
        instance["wall_parameters"] = {"kind": "avoid", "source": SOURCE}
    instance.update(changes)
    return instance


def indirect_sector(catalog, entities, **changes):
    specification = valkyrie_sector(
        catalog,
        entities,
        scope=SCOPE,
        model_rules=deepcopy(RULES),
        buff_spells=[],
        width=65,
        height=24,
        duration_seconds=2,
        maximum_step_seconds=0.25,
        recording_interval_seconds=0.25,
    )
    specification.update(changes)
    return specification


def damage_command(actor_id, time, amount, command_id="kill"):
    return {
        "id": command_id,
        "kind": "damage",
        "time_seconds": time,
        "targets": [actor_id],
        "amount": amount,
    }


def events(result, kind, source="weapon"):
    return [
        event
        for event in result["trace"]
        if event.get("event") == kind and event.get("source") == source
    ]


class IndirectDefenseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def compile(self, entities, **changes):
        return compile_entity_scene(
            indirect_sector(self.catalog, entities, **changes), self.catalog
        )

    def run_scene(self, entities, **changes):
        return simulate_spatial(self.compile(entities, **changes)["scene"])

    def runtime(self, entities, **changes):
        scene = self.compile(entities, **changes)["scene"]
        actors = _load_actors(scene, scene["width"], scene["height"])
        combat = PatternCombat(actors)
        runtime = IndirectDefenseCombat(actors, combat, _select_target, scene)
        trace = []
        runtime.prepare(actors, 0, trace)
        return actors, combat, runtime, trace

    def test_normal_mortar_uses_shell_statistics_not_dps_and_explicit_dead_zone(self):
        compiled = self.compile([indirect_instance(), fixed_tank()])
        self.assertEqual(compiled["scope"], SCOPE)
        self.assertEqual(compiled["scene"]["ruleset"], RULESET)
        actor = compiled["scene"]["actors"][0]
        self.assertEqual(actor["hitpoints"], 2300)
        self.assertEqual(actor["damage"], 300)
        self.assertEqual(actor["attack_interval_seconds"], 5)
        self.assertEqual(actor["minimum_range"], 4)
        self.assertEqual(actor["attack_model"]["radius"], 1.5)
        self.assertEqual(actor["entity_adapter"]["snapshot_dps"], 60)
        self.assertEqual(actor["indirect_model"]["shots_per_burst"], 1)
        self.assertFalse(compiled["full_game_prediction"])

    def test_eagle_uses_per_shell_and_shockwave_statistics(self):
        actor = self.compile([indirect_instance("eagle-artillery"), fixed_tank()])[
            "scene"
        ]["actors"][0]
        self.assertEqual(actor["damage"], 525)
        self.assertEqual(actor["hitpoints"], 6200)
        self.assertEqual(actor["minimum_range"], 7)
        self.assertEqual(actor["attack_model"]["radius"], 0.75)
        self.assertAlmostEqual(
            actor["attack_model"]["shockwave_damage_ratio"] * actor["damage"], 50
        )
        self.assertEqual(actor["indirect_model"]["post_burst_seconds"], 8.5)

    def test_missing_or_ambiguous_indirect_inputs_are_rejected(self):
        for field in (
            "minimum_range",
            "damage_basis",
            "burst_timing",
            "targeting",
            "readiness_policy",
            "activation",
            "shockwave",
        ):
            instance = indirect_instance()
            del instance["indirect_parameters"][field]
            with self.subTest(field=field), self.assertRaises(InputError):
                self.compile([instance, fixed_tank()])
        for value in ("average_dps", "three_simultaneous_shells", "guess"):
            instance = indirect_instance(mode="gearedUpBurst")
            instance["indirect_parameters"]["burst_timing"] = value
            with self.subTest(value=value), self.assertRaises(InputError):
                self.compile([instance, fixed_tank()])
        instance = indirect_instance()
        instance["indirect_parameters"]["minimum_range"] = {
            "basis": "snapshot_minRange",
            "multiplier": 1,
        }
        with self.assertRaises(InputError):
            self.compile([instance, fixed_tank()])

    def test_burst_mode_requires_unlock_and_explicit_projectile_speed(self):
        instance = indirect_instance(mode="gearedUpBurst", level=7)
        with self.assertRaises(InputError):
            self.compile([instance, fixed_tank()])
        instance = indirect_instance()
        del instance["attack_parameters"]["projectile"]["speed_tiles_per_second"]
        with self.assertRaises(InputError):
            self.compile([instance, fixed_tank()])

    def test_eagle_cannot_exist_after_catalog_removes_it_at_town_hall_17(self):
        with self.assertRaises(InputError):
            self.compile(
                [indirect_instance("eagle-artillery", town_hall=17), fixed_tank()]
            )

    def test_mortar_minimum_range_outer_range_and_air_exclusion(self):
        for target in (
            fixed_tank(x=17, y=8.5),
            fixed_tank(x=25, y=8.5),
            fixed_tank(entity="minion"),
        ):
            with self.subTest(target=target):
                result = self.run_scene(
                    [indirect_instance(), target], duration_seconds=0.1
                )
                self.assertFalse(events(result, "projectile_launch"))
        for x in (17.5, 24.5):
            with self.subTest(boundary=x):
                result = self.run_scene(
                    [indirect_instance(), fixed_tank(x=x, y=8.5)], duration_seconds=0.1
                )
                self.assertEqual(len(events(result, "projectile_launch")), 1)

    def test_geared_mortar_schedules_three_separate_shells_and_recovery(self):
        for step in (0.01, 0.5):
            result = self.run_scene(
                [indirect_instance(mode="gearedUpBurst"), fixed_tank()],
                duration_seconds=5.6,
                maximum_step_seconds=step,
            )
            launches = events(result, "projectile_launch")
            self.assertEqual(
                [round(event["time_seconds"], 6) for event in launches],
                [0, 0.5, 1, 4.5, 5, 5.5],
            )
            self.assertEqual(
                [event["weapon_state"]["shell_number"] for event in launches],
                [1, 2, 3, 1, 2, 3],
            )

    def test_start_based_and_end_based_burst_mappings_are_distinct(self):
        instance = indirect_instance(mode="gearedUpBurst")
        instance["indirect_parameters"]["burst_timing"] = START_TIMING
        result = self.run_scene([instance, fixed_tank()], duration_seconds=4.1)
        self.assertEqual(
            [event["time_seconds"] for event in events(result, "projectile_launch")],
            [0, 0.5, 1, 3.5, 4],
        )

    def test_eagle_burst_does_not_flatten_to_volley_or_average_damage(self):
        result = self.run_scene(
            [indirect_instance("eagle-artillery"), fixed_tank()], duration_seconds=10.8
        )
        self.assertEqual(
            [event["time_seconds"] for event in events(result, "projectile_launch")],
            [0, 0.75, 1.5, 10, 10.75],
        )
        impacts = events(result, "projectile_impact")
        self.assertEqual([event["damage"] for event in impacts], [575, 575, 575])
        self.assertEqual([event["time_seconds"] for event in impacts], [1, 1.75, 2.5])

    def test_destroyed_mortar_cancels_unreleased_shells_but_flight_continues(self):
        result = self.run_scene(
            [indirect_instance(mode="gearedUpBurst"), fixed_tank(x=21.5, y=8.5)],
            effects=[damage_command("weapon", 0.25, 2300)],
            duration_seconds=2,
        )
        self.assertEqual(len(events(result, "projectile_launch")), 1)
        self.assertEqual(
            [event["time_seconds"] for event in events(result, "projectile_impact")],
            [1],
        )
        self.assertAlmostEqual(result["actors"]["tank"]["hp"], 7700 - 110.5)
        cancelled = events(result, "indirect_burst_cancelled")
        self.assertEqual(cancelled[0]["unreleased_shells"], 2)

    def test_freeze_mid_burst_pauses_shell_clock_without_stopping_flight(self):
        freeze = {
            "id": "freeze-source",
            "kind": "freeze",
            "time_seconds": 0.25,
            "targets": ["weapon"],
            "duration_seconds": 2,
        }
        result = self.run_scene(
            [indirect_instance(mode="gearedUpBurst"), fixed_tank(x=21.5, y=8.5)],
            effects=[freeze],
            duration_seconds=4.1,
        )
        self.assertEqual(
            [event["time_seconds"] for event in events(result, "projectile_launch")],
            [0, 2.5, 3],
        )
        self.assertEqual(
            [event["time_seconds"] for event in events(result, "projectile_impact")],
            [1, 3.5, 4],
        )

    def test_final_timestamp_projectile_kill_finalizes_cancelled_burst(self):
        killer = fixed_tank(first_attack_seconds=0.25)
        killer["modifiers"]["damage_multiplier"] = 20
        result = self.run_scene(
            [indirect_instance(mode="gearedUpBurst"), killer],
            duration_seconds=0.25,
        )
        self.assertEqual(result["actors"]["weapon"]["death_time"], 0.25)
        cancelled = events(result, "indirect_burst_cancelled")
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0]["time_seconds"], 0.25)
        state = result["indirect_defenses"]["states"]["weapon"]
        self.assertTrue(state["destroyed"])
        self.assertEqual(state["cancelled_shells"], 2)

    def test_fixed_destination_can_miss_a_moving_primary(self):
        target = fixed_tank(x=21.5, y=8.5)
        target["modifiers"]["range_multiplier"] = 1
        instance = indirect_instance()
        instance["attack_parameters"]["projectile"]["speed_tiles_per_second"] = 4
        result = self.run_scene(
            [instance, target], duration_seconds=2.1, maximum_step_seconds=0.01
        )
        self.assertEqual(len(events(result, "projectile_launch")), 1)
        self.assertFalse(events(result, "projectile_impact"))
        self.assertEqual(result["actors"]["tank"]["hp"], 7700)

    def test_released_splash_resolves_after_primary_dies(self):
        result = self.run_scene(
            [
                indirect_instance(),
                fixed_tank("a-primary", x=21.5, y=8.5),
                fixed_tank("neighbor", x=22.5, y=8.5),
            ],
            effects=[damage_command("a-primary", 0.5, 7700)],
            duration_seconds=1.1,
        )
        self.assertEqual(
            [event["target"] for event in events(result, "projectile_impact")],
            ["neighbor"],
        )
        self.assertEqual(result["actors"]["neighbor"]["hp"], 7400)

    def test_no_target_holds_due_shell_and_reacquires_when_reserve_deploys(self):
        result = self.run_scene(
            [
                indirect_instance(mode="gearedUpBurst"),
                fixed_tank("a-primary", x=21.5, y=8.5),
                fixed_tank("reserve", x=22.5, y=8.5, spawn_seconds=2),
            ],
            effects=[damage_command("a-primary", 0.25, 7700)],
            duration_seconds=2.6,
        )
        launches = events(result, "projectile_launch")
        self.assertEqual([event["time_seconds"] for event in launches], [0, 2, 2.5])
        self.assertEqual(
            [event["weapon_state"]["shell_number"] for event in launches], [1, 2, 3]
        )
        self.assertEqual(
            [event["target"] for event in launches], ["a-primary", "reserve", "reserve"]
        )

    def test_eagle_requires_complete_actor_and_original_command_weights(self):
        for actor_weights, command_weights in (
            ({}, {}),
            ({"tank": 200, "extra": 1}, {}),
            ({"tank": 200}, {}),
        ):
            instance = indirect_instance("eagle-artillery")
            instance["indirect_parameters"]["activation"].update(
                actor_weights=actor_weights, command_weights=command_weights
            )
            with (
                self.subTest(actor_weights=actor_weights),
                self.assertRaises(InputError),
            ):
                self.compile(
                    [instance, fixed_tank()], effects=[damage_command("tank", 1, 1)]
                )

    def test_eagle_counts_deployments_cumulatively_after_troop_death(self):
        instance = indirect_instance("eagle-artillery")
        instance["indirect_parameters"]["activation"].update(
            actor_weights={"early": 100, "late": 100, "reserve": 500},
            command_weights={"kill": 0},
            delay_seconds=0.5,
        )
        result = self.run_scene(
            [
                instance,
                fixed_tank("early"),
                fixed_tank("late", spawn_seconds=2),
                fixed_tank("reserve", spawn_seconds="controlled"),
            ],
            effects=[damage_command("early", 1, 7700)],
            duration_seconds=3.3,
        )
        activation = events(result, "eagle_activated")
        self.assertEqual(len(activation), 1)
        self.assertEqual(activation[0]["time_seconds"], 2)
        self.assertEqual(activation[0]["total_weight"], 200)
        self.assertEqual(
            [event["time_seconds"] for event in events(result, "projectile_launch")],
            [2.5, 3.25],
        )

    def test_original_area_command_counts_once_even_with_multiple_targets(self):
        instance = indirect_instance("eagle-artillery")
        instance["indirect_parameters"]["activation"].update(
            actor_weights={"tank": 0, "other": 0}, command_weights={"cast": 200}
        )
        cast = {
            "id": "cast",
            "kind": "area_invulnerability",
            "time_seconds": 0.5,
            "duration_seconds": 1,
            "area": {
                "x": 22,
                "y": 9,
                "radius": 3,
                "target_team": "attack",
                "target_kinds": ["unit"],
                "target_layers": ["ground", "air"],
            },
        }
        result = self.run_scene(
            [instance, fixed_tank(), fixed_tank("other", x=23)],
            effects=[cast],
            duration_seconds=0.6,
        )
        activation = events(result, "eagle_activated")[0]
        self.assertEqual(activation["time_seconds"], 0.5)
        self.assertEqual(activation["command_weight"], 200)

    def test_rage_cast_is_explicitly_weighted_at_field_start(self):
        instance = indirect_instance("eagle-artillery")
        instance["indirect_parameters"]["activation"].update(
            actor_weights={"tank": 0}, command_weights={"rage-cast": 200}
        )
        result = self.run_scene(
            [instance, fixed_tank()],
            buff_spells=[buff_instance(id="rage-cast", time_seconds=1)],
            duration_seconds=1.1,
        )
        activation = events(result, "eagle_activated")[0]
        self.assertEqual(activation["time_seconds"], 1)
        self.assertEqual(activation["command_weight"], 200)

    def test_activation_weights_must_not_silently_ignore_new_controller_commands(self):
        actors, combat, runtime, trace = self.runtime(
            [indirect_instance("eagle-artillery"), fixed_tank()]
        )
        with self.assertRaises(InputError):
            runtime.observe_commands([damage_command("tank", 1, 1)], 1, trace)

    def test_eagle_density_selects_cluster_over_nearest_and_breaks_ties_by_id(self):
        instance = indirect_instance("eagle-artillery")
        instance["indirect_parameters"]["activation"]["actor_weights"] = {
            "near": 200,
            "a-cluster": 0,
            "b-cluster": 0,
        }
        result = self.run_scene(
            [
                instance,
                fixed_tank("near", x=22),
                fixed_tank("a-cluster", x=28, y=8),
                fixed_tank("b-cluster", x=28, y=10),
            ],
            duration_seconds=0.1,
        )
        self.assertEqual(events(result, "projectile_launch")[0]["target"], "a-cluster")

    def test_burst_retains_primary_then_reacquires_after_death(self):
        instance = indirect_instance("eagle-artillery")
        instance["indirect_parameters"]["activation"]["actor_weights"] = {
            "tank": 200,
            "other": 0,
        }
        actors, combat, runtime, trace = self.runtime(
            [instance, fixed_tank(), fixed_tank("other", x=28)]
        )
        weapon = actors["weapon"]
        target, _ = runtime.select_target(weapon, actors, 0, set(), 65, 24)
        self.assertEqual(target["id"], "tank")
        runtime.launch(weapon, target, actors, 0, trace)
        actors["tank"]["hp"] = 1
        retained, _ = runtime.select_target(weapon, actors, 0.75, set(), 65, 24)
        self.assertEqual(retained["id"], "tank")
        actors["tank"]["hp"] = 0
        replacement, _ = runtime.select_target(weapon, actors, 0.75, set(), 65, 24)
        self.assertEqual(replacement["id"], "other")

    def test_eagle_shockwave_has_explicit_overlap_and_outer_radius(self):
        for policy, expected in (
            ("additive_with_shell", 575),
            ("outer_ring_only", 525),
        ):
            instance = indirect_instance("eagle-artillery")
            instance["indirect_parameters"]["targeting"]["radius_tiles"] = 0
            instance["indirect_parameters"]["shockwave"]["overlap_policy"] = policy
            instance["indirect_parameters"]["activation"]["actor_weights"] = {
                "tank": 200,
                "outer": 0,
                "beyond": 0,
            }
            result = self.run_scene(
                [
                    instance,
                    fixed_tank(),
                    fixed_tank("outer", x=23.5),
                    fixed_tank("beyond", x=24.1),
                ],
                duration_seconds=1.1,
            )
            hits = {
                event["target"]: event["damage"]
                for event in events(result, "projectile_impact")
            }
            with self.subTest(policy=policy):
                self.assertEqual(hits, {"tank": expected, "outer": 50})

    def test_shockwave_layer_policy_is_applied_by_shared_damage_filter(self):
        instance = indirect_instance("eagle-artillery")
        instance["indirect_parameters"]["activation"]["actor_weights"] = {
            "tank": 200,
            "air": 0,
        }
        instance["attack_parameters"][
            "splash_layer_policy"
        ] = "primary_target_layer_only"
        result = self.run_scene(
            [instance, fixed_tank(), fixed_tank("air", entity="minion", x=22.5)],
            duration_seconds=1.1,
        )
        self.assertEqual(
            [event["target"] for event in events(result, "projectile_impact")], ["tank"]
        )
        self.assertEqual(result["actors"]["air"]["hp"], 120)

    def test_role_profile_scales_shell_and_shockwave_once_without_scaling_activation(
        self,
    ):
        instance = indirect_instance("eagle-artillery")
        instance["indirect_parameters"]["activation"]["actor_weights"] = {
            "tank": 200,
            "outer": 0,
        }
        targets = [fixed_tank(), fixed_tank("outer", x=23.5)]
        for target in targets:
            target["modifiers"]["range_multiplier"] = 1
        compiled = self.compile([instance, *targets])["scene"]
        before = deepcopy(compiled)
        modified = apply_battle_modifiers(
            compiled,
            modifier_policy(),
            self.catalog,
            read_json(ROOT / "data" / "mode-rules.json"),
        )["scene"]
        self.assertEqual(compiled, before)
        original_weapon = compiled["actors"][0]
        changed_weapon = modified["actors"][0]
        self.assertEqual(changed_weapon["damage"], 630)
        self.assertEqual(
            changed_weapon["indirect_model"], original_weapon["indirect_model"]
        )
        self.assertEqual(
            changed_weapon["attack_model"], original_weapon["attack_model"]
        )
        actors = _load_actors(modified, 65, 24)
        combat = PatternCombat(actors)
        runtime = IndirectDefenseCombat(actors, combat, _select_target, modified)
        trace = []
        runtime.prepare(actors, 0, trace)
        runtime.launch(actors["weapon"], actors["tank"], actors, 0, trace)
        self.assertEqual(actors["weapon"]["next_attack"], 0.75)
        combat.resolve(actors, 1, trace)
        hits = {
            event["target"]: event["damage"]
            for event in trace
            if event["event"] == "projectile_impact"
        }
        self.assertAlmostEqual(hits["tank"], 690)
        self.assertAlmostEqual(hits["outer"], 60)
        self.assertEqual(runtime.states["weapon"]["total_weight"], 200)
        with self.assertRaises(InputError):
            apply_battle_modifiers(
                modified,
                modifier_policy(),
                self.catalog,
                read_json(ROOT / "data" / "mode-rules.json"),
            )


if __name__ == "__main__":
    unittest.main()
