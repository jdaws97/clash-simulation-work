"""Entity-mapping checks for explicitly conditional wall-free sectors."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.adapters import (
    SCOPE,
    WALL_SCOPE,
    compile_entity_scene,
    simulate_entity_closed_loop,
    simulate_entity_scene,
)
from clashlab.catalog import Catalog
from clashlab.combat import COMBAT_RULES
from clashlab.common import InputError
from clashlab.spatial import simulate_spatial
from clashlab.stat_layers import build_statistic_branch
from clashlab.common import read_json
from clashlab.closed_loop import CONTROL_RULES


ROOT = Path(__file__).resolve().parents[1]


def projectile():
    return {
        "timing": "instant",
        "delay_seconds": 0,
        "destination": "locked_actor_center_at_impact",
        "hit_radius": 0,
    }


def entity_instance(instance_id, entity_id, level, team, **changes):
    instance = {
        "id": instance_id,
        "entity": entity_id,
        "level": level,
        "town_hall": 16,
        "mode": "normal",
        "statistics_mode": "normal",
        "supercharge": False,
        "team": team,
        "counts_for_destruction": team == "defense",
        "x": 7.5 if team == "attack" else 8,
        "y": 5.5 if team == "attack" else 4,
        "spawn_seconds": 0,
        "first_attack_seconds": 0,
        "modifiers": {
            "hitpoints_multiplier": 1,
            "damage_multiplier": 1,
            "maximum_hp_damage_multiplier": 1,
            "attack_interval_multiplier": 1,
            "range_multiplier": 1,
            "movement_speed_multiplier": 1,
            "source": "declared-no-modifier-conditional-fixture",
        },
        "attack_parameters": {"projectile": projectile()},
    }
    instance.update(changes)
    return instance


def sector(catalog, entities):
    return {
        "id": "conditional-catalog-sector-fixture",
        "scope": SCOPE,
        "model_rules": deepcopy(COMBAT_RULES),
        "statistics_policy": {
            "kind": "conditional_pinned_snapshot",
            "snapshot_commit": catalog.snapshot["snapshotCommit"],
        },
        "unit_conventions": {
            "movement_units_per_tile": 8,
            "catalog_attack_speed_unit": "seconds_per_hit",
            "source": "declared-fixture-conversion-not-current-game-verification",
        },
        "unsupported_mechanics": [],
        "width": 14,
        "height": 12,
        "duration_seconds": 0.05,
        "maximum_step_seconds": 0.01,
        "recording_interval_seconds": 0.05,
        "entities": entities,
        "effects": [],
    }


class EntityAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_thrower_imports_selected_level_and_explicit_conversion(self):
        spec = sector(
            self.catalog, [entity_instance("thrower", "thrower", 2, "attack")]
        )
        compiled = compile_entity_scene(spec, self.catalog)
        actor = compiled["scene"]["actors"][0]
        self.assertEqual(actor["hitpoints"], 2350)
        self.assertEqual(actor["damage"], 525)
        self.assertEqual(actor["attack_interval_seconds"], 2.5)
        self.assertEqual(actor["speed"], 2.25)
        self.assertEqual(actor["range"], 6)
        self.assertEqual(
            actor["entity_adapter"]["snapshot_verification"], "unverified_snapshot"
        )
        self.assertFalse(compiled["full_game_prediction"])

    def test_monolith_uses_target_maximum_hp_bonus_in_addition_to_flat_damage(self):
        entities = [
            entity_instance("tank", "pekka", 11, "attack"),
            entity_instance("mono", "monolith", 3, "defense"),
        ]
        result = simulate_entity_scene(sector(self.catalog, entities), self.catalog)
        tank = result["combat"]["actors"]["tank"]
        self.assertAlmostEqual(tank["hp"], 7700 - 289.5 - 1001)

    def test_multi_archer_concentrates_three_arrows_on_single_minion(self):
        tower = entity_instance("multi", "multi-archer-tower", 2, "defense")
        tower["attack_parameters"][
            "allocation"
        ] = "cycle_distinct_targets_to_fill_volley"
        spec = sector(
            self.catalog, [entity_instance("minion", "minion", 12, "attack"), tower]
        )
        result = simulate_entity_scene(spec, self.catalog)
        self.assertEqual(result["combat"]["actors"]["minion"]["hp"], 0)
        impacts = [
            event
            for event in result["combat"]["trace"]
            if event.get("event") == "projectile_impact" and event["source"] == "multi"
        ]
        self.assertEqual(len(impacts), 3)
        self.assertEqual(sum(event["damage"] for event in impacts), 195)

    def test_xbow_mode_controls_ground_versus_air_eligibility(self):
        bow = entity_instance("bow", "x-bow", 11, "defense")
        spec = sector(
            self.catalog, [entity_instance("minion", "minion", 12, "attack"), bow]
        )
        ground = simulate_entity_scene(spec, self.catalog)
        self.assertEqual(ground["combat"]["actors"]["minion"]["hp"], 120)
        bow["mode"] = "airAndGround"
        both = simulate_entity_scene(spec, self.catalog)
        self.assertLess(both["combat"]["actors"]["minion"]["hp"], 120)

    def test_ordinary_unit_prefers_nearer_passive_building_over_farther_defense(self):
        entities = [
            entity_instance("archer", "archer", 12, "attack", x=2.5),
            entity_instance(
                "cannon", "cannon", 21, "defense", x=10, first_attack_seconds=10
            ),
            entity_instance(
                "barracks",
                "barracks",
                18,
                "defense",
                x=4,
                mode="passive",
                statistics_mode="none",
                attack_parameters={},
                inactive_attack_interval_seconds=1,
            ),
        ]
        result = simulate_entity_scene(sector(self.catalog, entities), self.catalog)
        shot = next(
            event
            for event in result["combat"]["trace"]
            if event.get("event") == "projectile_launch" and event["source"] == "archer"
        )
        self.assertEqual(shot["target"], "barracks")

    def test_special_entity_cannot_be_downgraded_to_an_ordinary_weapon(self):
        for entity_id, level, message in (
            ("root-rider", 3, "wall"),
            ("electro-dragon", 7, "death-effects sector scope"),
            ("ruin-witch", 2, "timed summons"),
            ("inferno-tower", 10, "ramp"),
        ):
            with self.subTest(entity=entity_id):
                spec = sector(
                    self.catalog,
                    [entity_instance("special", entity_id, level, "attack")],
                )
                with self.assertRaisesRegex(InputError, message):
                    compile_entity_scene(spec, self.catalog)

    def test_ricochet_damage_ratio_comes_from_selected_level(self):
        cannon = entity_instance("ricochet", "ricochet-cannon", 2, "defense")
        cannon["attack_parameters"].update(
            {
                "jump_metric": "footprint_distance",
                "jump_delay_seconds": 0.1,
                "tie_break": "distance_then_instance_id",
                "allow_protected_links": True,
            }
        )
        compiled = compile_entity_scene(sector(self.catalog, [cannon]), self.catalog)
        pattern = compiled["scene"]["actors"][0]["attack_model"]
        self.assertEqual(pattern["damage_multipliers"][0], 1)
        self.assertAlmostEqual(pattern["damage_multipliers"][1], 0.7)
        self.assertEqual(pattern["jump_range"], 3.5)
        self.assertEqual(pattern["jump_delay_seconds"], 0.1)

    def test_missing_dragon_splash_radius_is_not_invented(self):
        spec = sector(self.catalog, [entity_instance("dragon", "dragon", 11, "attack")])
        with self.assertRaisesRegex(InputError, "exactly cover"):
            compile_entity_scene(spec, self.catalog)

    def test_missing_conversion_snapshot_mismatch_and_full_village_scope_are_rejected(
        self,
    ):
        original = sector(
            self.catalog, [entity_instance("archer", "archer", 12, "attack")]
        )
        cases = [deepcopy(original) for _ in range(3)]
        del cases[0]["unit_conventions"]["movement_units_per_tile"]
        cases[1]["statistics_policy"]["snapshot_commit"] = "wrong-commit"
        cases[2]["scope"] = "full-village"
        for spec in cases:
            with self.assertRaises(InputError):
                compile_entity_scene(spec, self.catalog)

    def test_unavailable_level_and_burst_cannon_mode_require_more_than_raw_stats(self):
        spec = sector(
            self.catalog, [entity_instance("thrower", "thrower", 4, "attack")]
        )
        with self.assertRaisesRegex(InputError, "unavailable"):
            compile_entity_scene(spec, self.catalog)
        spec = sector(
            self.catalog,
            [entity_instance("burst", "cannon", 21, "defense", mode="gearedUpBurst")],
        )
        with self.assertRaisesRegex(InputError, "behavior adapter"):
            compile_entity_scene(spec, self.catalog)

    def test_priority_tiers_cannot_silently_default_when_null_or_omit_a_kind(self):
        spec = sector(self.catalog, [entity_instance("archer", "archer", 12, "attack")])
        compiled = compile_entity_scene(spec, self.catalog)
        actor = compiled["scene"]["actors"][0]
        actor["target_priority_tiers"] = None
        with self.assertRaisesRegex(InputError, "explicit input"):
            simulate_spatial(compiled["scene"])
        actor["target_priority_tiers"] = [["defense"]]
        with self.assertRaisesRegex(InputError, "exactly partition"):
            simulate_spatial(compiled["scene"])

    def test_coverage_exposes_partial_adapter_separately_from_full_battle_readiness(
        self,
    ):
        coverage = {row["id"]: row for row in self.catalog.coverage()}
        self.assertTrue(coverage["thrower"]["conditional_sector_adapter"]["available"])
        self.assertFalse(
            coverage["thrower"]["conditional_sector_adapter"]["replay_validated"]
        )
        self.assertTrue(
            coverage["root-rider"]["conditional_sector_adapter"]["available"]
        )
        self.assertEqual(
            coverage["root-rider"]["conditional_sector_adapter"]["scope"], WALL_SCOPE
        )
        self.assertEqual(
            coverage["thrower"]["full_battle_adapter"],
            "REQUIRES_IMPLEMENTATION_AND_REPLAY_VALIDATION",
        )

    def test_entity_statistics_and_human_response_delay_change_survival_together(self):
        spec = sector(
            self.catalog,
            [
                entity_instance("archer", "archer", 12, "attack"),
                entity_instance(
                    "mono", "monolith", 3, "defense", first_attack_seconds=0.25
                ),
            ],
        )
        spec["duration_seconds"] = 1.25
        plan = {
            "id": "synthetic-source-linked-protection",
            "observation_interval_seconds": 0.05,
            "control_rules": deepcopy(CONTROL_RULES),
            "failed_action_transition": "stop_stream",
            "resources": {"freeze": 1},
            "streams": [
                {
                    "id": "protect",
                    "steps": [
                        {
                            "all_conditions": [
                                {
                                    "actor_id": "archer",
                                    "field": "active",
                                    "operator": "equals",
                                    "value": True,
                                }
                            ],
                            "action": {
                                "id": "freeze",
                                "kind": "freeze",
                                "targets": ["mono"],
                                "duration_seconds": 2,
                                "recheck_conditions_on_execution": True,
                                "cost": {"freeze": 1},
                            },
                        }
                    ],
                }
            ],
        }
        profile = {
            "plan_id": plan["id"],
            "observed_latency_traces": [
                {
                    "source_replay": "synthetic-protection-response-not-measured-player-evidence",
                    "responses": {
                        "freeze": {
                            "latency_seconds": 0.1,
                            "missed": False,
                            "placement_errors": {},
                        }
                    },
                }
            ],
        }
        timely = simulate_entity_closed_loop(spec, self.catalog, plan, profile, 7, 1)
        profile["observed_latency_traces"][0]["responses"]["freeze"][
            "latency_seconds"
        ] = 0.5
        late = simulate_entity_closed_loop(spec, self.catalog, plan, profile, 7, 1)
        self.assertEqual(
            timely["human_combat"]["samples"][0]["combat"]["actors"]["archer"]["hp"], 68
        )
        self.assertEqual(
            late["human_combat"]["samples"][0]["combat"]["actors"]["archer"]["hp"], 0
        )
        self.assertFalse(timely["full_game_prediction"])

    def test_source_branch_cannot_be_mislabeled_as_raw_or_used_without_its_policy(self):
        policy = read_json(ROOT / "examples/primary-stat-policy.json")
        branch = build_statistic_branch(
            self.catalog, read_json(ROOT / "data/primary-stat-claims.json"), policy
        )
        spec = sector(self.catalog, [entity_instance("archer", "archer", 12, "attack")])
        with self.assertRaisesRegex(InputError, "unchanged snapshot"):
            compile_entity_scene(spec, branch)
        spec["statistics_policy"].update(
            {"kind": "conditional_primary_publications", "branch_policy": policy}
        )
        self.assertEqual(
            compile_entity_scene(spec, branch)["statistic_branch"]["policy"], policy
        )
        with self.assertRaisesRegex(InputError, "exact selected source branch"):
            compile_entity_scene(spec, self.catalog)


if __name__ == "__main__":
    unittest.main()
