"""Meaningful contract checks; all synthetic fixtures are explicitly labeled."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.army import enumerate_counts, validate_army
from clashlab.boosts import effective_account
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.encounter import paired_interventions, simulate_encounter
from clashlab.evaluation import _units, evaluate_candidates, validate_replays
from clashlab.execution import review_execution
from clashlab.experiments import design_campaign, evaluate_strata
from clashlab.geometry import mutate_layout, validate_layout
from clashlab.human import perturb_plan
from clashlab.ingest import git_blob_sha
from clashlab.policy import simulate_policy
from clashlab.planning import planning_account
from clashlab.scoring import outcome_metrics, strongest_attack, validate_outcome


ROOT = Path(__file__).resolve().parents[1]


def synthetic_replay(replay_id, stars, destruction, session="session-1"):
    return {
        "id": replay_id,
        "army_id": "army-a",
        "base_id": "base-a",
        "plan_id": "plan-a",
        "scenario_id": "scenario-a",
        "human_profile_id": "synthetic-profile",
        "patch_id": "synthetic-patch",
        "modifier_id": "none",
        "session_id": session,
        "encounter_id": "encounter-" + session,
        "source": "synthetic-test-fixture",
        "mode": "cwl",
        "fold": "test",
        "attacker_town_hall": 16,
        "defender_town_hall": 18,
        "stars": stars,
        "destruction": destruction,
        "town_hall_destroyed": stars >= 2,
    }


def synthetic_encounter():
    return {
        "id": "synthetic-exposure",
        "duration_seconds": 10,
        "unsupported_mechanics": [],
        "same_time_policy": "simultaneous_damage_then_heal",
        "actors": [
            {"id": "attacker", "team": "attack", "hitpoints": 100},
            {"id": "tower", "team": "defense", "hitpoints": 100},
        ],
        "events": [
            {
                "id": "shot",
                "time_seconds": 2,
                "effect": "damage",
                "amount": 100,
                "target": "attacker",
                "source": "tower",
                "requires_source_alive": True,
            },
            {
                "id": "freeze",
                "time_seconds": 3,
                "effect": "freeze",
                "duration_seconds": 2,
                "target": "tower",
                "source": "external",
                "requires_source_alive": False,
            },
        ],
    }


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.account = read_json(ROOT / "profiles/sample-th16.json")
        cls.planned = read_json(ROOT / "examples/planned-account.json")
        cls.army = read_json(ROOT / "examples/root-fireball-druid-experiment.json")

    def test_scoring_preserves_real_defense_award(self):
        result = outcome_metrics(
            {
                "stars": 1,
                "destruction": 83,
                "town_hall_destroyed": False,
                "attacker_trophies": 14,
            }
        )
        self.assertEqual(result["defender_trophies_lower"], 26)
        self.assertEqual(result["defender_trophies_upper"], 26)

    def test_scoring_rejects_inconsistent_hall_and_stars(self):
        with self.assertRaises(InputError):
            validate_outcome(
                {"stars": 1, "destruction": 90, "town_hall_destroyed": True}
            )

    def test_three_stars_require_full_destruction(self):
        with self.assertRaises(InputError):
            validate_outcome(
                {"stars": 3, "destruction": 99, "town_hall_destroyed": True}
            )

    def test_war_and_cwl_use_best_incoming_attack(self):
        rows = [synthetic_replay("r1", 1, 90), synthetic_replay("r2", 2, 60)]
        self.assertEqual(strongest_attack(rows)["id"], "r2")
        self.assertEqual(len(_units(rows, "defense", "cwl")), 1)
        self.assertEqual(_units(rows, "defense", "war")[0]["stars"], 2)

    def test_session_split_leakage_is_rejected(self):
        rows = [synthetic_replay("r1", 1, 90), synthetic_replay("r2", 2, 60)]
        rows[1]["fold"] = "train"
        with self.assertRaises(InputError):
            validate_replays(rows)

    def test_no_probability_for_missing_candidate_stratum(self):
        configuration = {
            "perspective": "attack",
            "mode": "cwl",
            "fold": "test",
            "scenario_weights": {"scenario-a": 1},
            "minimum_sessions": 2,
            "bootstrap_iterations": 20,
            "confidence_level": 0.95,
            "seed": 1,
            "candidate_ids": ["army-a", "unseen-army"],
            "patch_id": "synthetic-patch",
            "modifier_id": "none",
            "human_profile_id": "synthetic-profile",
            "plan_ids_by_candidate": {"army-a": "plan-a", "unseen-army": "plan-b"},
        }
        rows = [
            synthetic_replay("r1", 3, 100, "s1"),
            synthetic_replay("r2", 2, 90, "s2"),
        ]
        result = evaluate_candidates(rows, configuration)
        self.assertEqual(result["evaluated"][0]["point_estimates"]["triple_rate"], 0.5)
        self.assertEqual(result["unsupported"][0]["candidate_id"], "unseen-army")

    def test_potions_do_not_max_equipment_or_unlock_new_troops(self):
        account = effective_account(self.account, self.catalog, "ranked")
        self.assertEqual(account["levels"]["grand-warden"], 70)
        self.assertEqual(account["levels"]["fireball"], 24)
        self.assertNotIn("meteor-golem", account["levels"])

    def test_planning_caps_follow_confirmed_recipient_capacity_and_parent_unlock(self):
        specification = {
            "mode": "ranked",
            "recipient_level_rule": "unique_capacity_match",
            "super_troops": ["super-wall-breaker"],
        }
        planned = planning_account(self.account, self.catalog, specification)
        self.assertEqual(
            planned["planning_evidence"]["recipient_clan_castle_level"], 12
        )
        self.assertEqual(planned["levels"]["super-wall-breaker"], 12)
        self.assertEqual(planned["levels"]["fireball"], 24)
        self.assertEqual(planned["donation_levels"]["dragon-rider"], 6)
        locked = deepcopy(self.account)
        locked["levels"].pop("super-wall-breaker")
        locked["levels"]["wall-breaker"] = 6
        with self.assertRaises(InputError):
            planning_account(locked, self.catalog, specification)

    def test_planning_never_assumes_an_unmatched_castle_tier(self):
        account = deepcopy(self.account)
        account["capacities"]["clan_castle_troops"] = 49
        specification = {
            "mode": "ranked",
            "recipient_level_rule": "unique_capacity_match",
            "super_troops": [],
        }
        with self.assertRaises(InputError):
            planning_account(account, self.catalog, specification)

    def test_planning_derives_a_higher_th_recipient_without_th16_constants(self):
        account = deepcopy(self.account)
        account["town_hall"] = 17
        account["laboratory_level"] = 15
        account["capacities"]["clan_castle_troops"] = 55
        specification = {
            "mode": "ranked",
            "recipient_level_rule": "unique_capacity_match",
            "super_troops": [],
        }
        planned = planning_account(account, self.catalog, specification)
        self.assertEqual(
            planned["planning_evidence"]["recipient_clan_castle_level"], 13
        )

    def test_army_capacity_and_donation_evidence(self):
        self.assertEqual(
            validate_army(self.army, self.planned, self.catalog)["used"][
                "army_housing"
            ],
            320,
        )
        overflow = deepcopy(self.army)
        overflow["troops"][0]["count"] += 1
        with self.assertRaises(InputError):
            validate_army(overflow, self.planned, self.catalog)
        donated = deepcopy(self.army)
        donated["clan_castle"]["troops"] = [{"id": "archer", "level": 12, "count": 1}]
        unknown_donations = deepcopy(self.planned)
        unknown_donations["donation_levels"] = {}
        with self.assertRaises(InputError):
            validate_army(donated, unknown_donations, self.catalog)

    def test_illegal_hero_and_duplicate_pet_are_rejected(self):
        army = deepcopy(self.army)
        army["heroes"][0]["mode"] = "air"
        with self.assertRaises(InputError):
            validate_army(army, self.planned, self.catalog)
        army = deepcopy(self.army)
        army["heroes"][1]["pet"] = deepcopy(army["heroes"][0]["pet"])
        with self.assertRaises(InputError):
            validate_army(army, self.planned, self.catalog)

    def test_boolean_hero_and_siege_levels_are_not_numeric_levels(self):
        army = deepcopy(self.army)
        army["heroes"][0]["level"] = True
        with self.assertRaises(InputError):
            validate_army(army, self.planned, self.catalog)
        army = deepcopy(self.army)
        army["siege"]["level"] = True
        with self.assertRaises(InputError):
            validate_army(army, self.planned, self.catalog)

    def test_enumerator_obeys_housing_space(self):
        pool = [{"id": "dragon", "level": 11, "minimum": 0, "maximum": 3}]
        results = list(enumerate_counts(pool, 40, self.catalog, "troop", True))
        self.assertEqual(results, [[{"id": "dragon", "level": 11, "count": 2}]])

    def test_human_samples_preserve_correlated_whole_traces(self):
        plan = {
            "id": "plan",
            "actions": [
                {"id": "a", "time_seconds": 10, "x": 0, "y": 0},
                {"id": "b", "time_seconds": 20, "x": 0, "y": 0},
            ],
        }
        profile = {
            "plan_id": "plan",
            "observed_error_traces": [
                {
                    "source_replay": "synthetic",
                    "errors": {
                        "a": {
                            "missed": False,
                            "time_error_seconds": 2,
                            "dx_tiles": 1,
                            "dy_tiles": 0,
                        },
                        "b": {
                            "missed": False,
                            "time_error_seconds": 3,
                            "dx_tiles": 1,
                            "dy_tiles": 0,
                        },
                    },
                }
            ],
        }
        samples = perturb_plan(plan, profile, 1, 3)["samples"]
        for sample in samples:
            self.assertEqual(
                [event["time_seconds"] for event in sample["events"]], [12, 23]
            )
        profile["observed_error_traces"] = []
        with self.assertRaises(InputError):
            perturb_plan(plan, profile, 1, 3)

    def test_earlier_protection_changes_local_survival(self):
        result = paired_interventions(
            synthetic_encounter(),
            [
                {
                    "label": "protect-before-shot",
                    "event_updates": {"freeze": {"time_seconds": 1}},
                }
            ],
        )
        self.assertEqual(result["baseline"]["actors"]["attacker"]["hp"], 0)
        self.assertEqual(
            result["variants"][0]["result"]["actors"]["attacker"]["hp"], 100
        )

    def test_unknown_mechanics_block_encounter_predictions(self):
        scenario = synthetic_encounter()
        scenario["unsupported_mechanics"] = ["unverified-chain-targeting"]
        with self.assertRaises(InputError):
            simulate_encounter(scenario)

    def test_simultaneous_damage_has_no_actor_order_bias(self):
        scenario = synthetic_encounter()
        scenario["events"] = [
            scenario["events"][0],
            {
                "id": "countershot",
                "time_seconds": 2,
                "effect": "damage",
                "amount": 100,
                "target": "tower",
                "source": "attacker",
                "requires_source_alive": True,
            },
        ]
        result = simulate_encounter(scenario)
        self.assertTrue(all(state["hp"] == 0 for state in result["actors"].values()))

    def test_layout_mutations_preserve_inventory_and_legality(self):
        layout = {
            "width": 16,
            "height": 16,
            "town_hall": 16,
            "inventory": {"town-hall": 1, "gold-storage": 1},
            "buildings": [
                {
                    "instance": "th",
                    "id": "town-hall",
                    "level": 16,
                    "x": 0,
                    "y": 0,
                    "counts_for_destruction": True,
                },
                {
                    "instance": "gold",
                    "id": "gold-storage",
                    "level": 16,
                    "x": 8,
                    "y": 8,
                    "counts_for_destruction": True,
                },
            ],
        }
        validate_layout(layout, self.catalog)
        result = mutate_layout(
            layout,
            self.catalog,
            {
                "seed": 1,
                "attempts": 20,
                "maximum_candidates": 5,
                "movable_instances": ["gold"],
                "operations": ["move"],
            },
        )
        self.assertTrue(result["candidates"])
        for candidate in result["candidates"]:
            self.assertEqual(candidate["layout"]["inventory"], layout["inventory"])
            validate_layout(candidate["layout"], self.catalog)
        overlapping = deepcopy(layout)
        overlapping["buildings"][1].update({"x": 1, "y": 1})
        with self.assertRaises(InputError):
            validate_layout(overlapping, self.catalog)

    def test_official_balance_conflict_is_reported(self):
        audit = self.catalog.audit(read_json(ROOT / "data/balance-claims.json"))
        self.assertFalse(audit["battle_ready"])
        self.assertTrue(
            any(
                row.get("entity") == "giant-arrow"
                and row["kind"] == "official_balance_conflict"
                for row in audit["findings"]
            )
        )

    def test_th16_merged_towers_consume_their_parent_inventory(self):
        buildings = []
        entity_ids = ["town-hall"] + ["archer-tower"] * 5 + ["multi-archer-tower"] * 2
        for index, entity_id in enumerate(entity_ids):
            building = {
                "instance": f"synthetic-building-{index}",
                "id": entity_id,
                "level": 16 if entity_id == "town-hall" else 1,
                "x": index * 5,
                "y": 0,
                "counts_for_destruction": True,
            }
            modes = self.catalog.entity(entity_id).get("modes")
            if modes:
                building["mode"] = next(iter(modes))
            buildings.append(building)
        layout = {
            "width": 44,
            "height": 16,
            "town_hall": 16,
            "inventory": {"town-hall": 1, "archer-tower": 5, "multi-archer-tower": 2},
            "buildings": buildings,
        }
        with self.assertRaisesRegex(InputError, "double-count"):
            validate_layout(layout, self.catalog)
        layout["buildings"].pop(1)
        layout["inventory"]["archer-tower"] = 4
        validate_layout(layout, self.catalog)

    def test_execution_reviews_keep_causal_claims_unproven(self):
        for review in read_json(
            ROOT / "tests/fixtures/execution-review-synthetic.json"
        ):
            result = review_execution(review)
            self.assertEqual(
                result["status"], "EXECUTION_REVIEW_WITH_TESTABLE_HYPOTHESES"
            )

    def test_execution_reviews_reject_missing_evidence_and_causal_certainty(self):
        review = read_json(ROOT / "tests/fixtures/execution-review-synthetic.json")[0]
        missing = deepcopy(review)
        missing["hypotheses"][0]["evidence_ids"] = []
        with self.assertRaisesRegex(InputError, "linked observations"):
            review_execution(missing)
        certain = deepcopy(review)
        certain["hypotheses"][0]["causal_status"] = "PROVEN_CAUSE"
        with self.assertRaisesRegex(InputError, "counterfactual cause"):
            review_execution(certain)

    def test_blob_hash_uses_git_object_framing(self):
        self.assertEqual(
            git_blob_sha(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a"
        )

    def test_spell_tower_mode_requires_its_unlock_level(self):
        layout = read_json(ROOT / "examples/layout-synthetic.json")
        layout["inventory"].pop("gold-storage")
        layout["inventory"]["spell-tower"] = 1
        tower = layout["buildings"][1]
        tower.update({"id": "spell-tower", "level": 3, "mode": "earthquake"})
        with self.assertRaises(InputError):
            validate_layout(layout, self.catalog)
        tower["mode"] = "invisibility"
        validate_layout(layout, self.catalog)

    def test_campaign_balances_arms_and_rejects_held_out_base_leakage(self):
        specification = {
            "id": "synthetic-campaign",
            "seed": 2,
            "repeats_per_case": 2,
            "maximum_trials": 4,
            "mode": "friendly",
            "patch_id": "synthetic-patch",
            "modifier_id": "none",
            "arms": [
                {
                    "id": "a",
                    "army_id": "army-a",
                    "plan_id": "early",
                    "human_profile_id": "me",
                },
                {
                    "id": "b",
                    "army_id": "army-a",
                    "plan_id": "late",
                    "human_profile_id": "me",
                },
            ],
            "cases": [
                {
                    "id": "case",
                    "base_id": "base",
                    "scenario_id": "scenario",
                    "attacker_town_hall": 16,
                    "defender_town_hall": 18,
                    "fold": "train",
                }
            ],
        }
        result = design_campaign(specification)
        for block in {trial["session_id"] for trial in result["trials"]}:
            members = [
                trial["arm_id"]
                for trial in result["trials"]
                if trial["session_id"] == block
            ]
            self.assertEqual(set(members), {"a", "b"})
        self.assertTrue(all(trial["stars"] is None for trial in result["trials"]))
        duplicate = deepcopy(specification["cases"][0])
        duplicate.update({"id": "new-case", "fold": "test"})
        specification["cases"].append(duplicate)
        with self.assertRaises(InputError):
            design_campaign(specification)

    def test_separate_scenarios_do_not_invent_a_population_mix(self):
        configuration = {
            "perspective": "attack",
            "mode": "cwl",
            "fold": "test",
            "scenario_ids": ["scenario-a", "unseen-scenario"],
            "minimum_sessions": 1,
            "bootstrap_iterations": 20,
            "confidence_level": 0.95,
            "seed": 1,
            "candidate_ids": ["army-a"],
            "patch_id": "synthetic-patch",
            "modifier_id": "none",
            "human_profile_id": "synthetic-profile",
            "plan_ids_by_candidate": {"army-a": "plan-a"},
        }
        result = evaluate_strata([synthetic_replay("r1", 3, 100)], configuration)
        self.assertIsNone(result["overall_ranking"])
        self.assertFalse(result["population_mixture_assumed"])
        self.assertEqual(
            result["reports"][1]["evaluation"]["unsupported"][0]["gaps"][0]["sessions"],
            0,
        )

    def policy_fixture(self):
        plan = {
            "id": "synthetic-cue-plan",
            "observation_interpolation": "none",
            "concurrency_model": "independent_streams_joint_latency_trace",
            "missed_action_transition": "advance",
            "streams": [
                {
                    "id": "setup-job",
                    "steps": [
                        {
                            "all_conditions": [
                                {
                                    "field": "target_matches",
                                    "operator": "equals",
                                    "value": True,
                                }
                            ],
                            "action": {"id": "setup", "kind": "hero_ability"},
                        }
                    ],
                },
                {
                    "id": "main-job",
                    "steps": [
                        {
                            "all_conditions": [
                                {
                                    "field": "route_cleared",
                                    "operator": "equals",
                                    "value": True,
                                }
                            ],
                            "action": {"id": "entry", "kind": "deploy_main"},
                        }
                    ],
                },
            ],
        }
        observations = [
            {
                "time_seconds": 0,
                "source": "synthetic-frame-0",
                "state": {"target_matches": False, "route_cleared": False},
            },
            {
                "time_seconds": 5,
                "source": "synthetic-frame-5",
                "state": {"target_matches": True, "route_cleared": False},
            },
            {
                "time_seconds": 10,
                "source": "synthetic-frame-10",
                "state": {"target_matches": True, "route_cleared": True},
            },
            {
                "time_seconds": 15,
                "source": "synthetic-frame-15",
                "state": {"target_matches": True, "route_cleared": True},
            },
        ]
        profile = {
            "plan_id": plan["id"],
            "observed_latency_traces": [
                {
                    "source_replay": "synthetic-latency-fixture",
                    "responses": {
                        "setup": {"latency_seconds": 1, "missed": False},
                        "entry": {"latency_seconds": 2, "missed": False},
                    },
                }
            ],
        }
        return plan, observations, profile

    def test_policy_uses_readiness_cues_and_measured_latencies(self):
        plan, observations, profile = self.policy_fixture()
        result = simulate_policy(plan, observations, profile, 1, 3)
        for sample in result["samples"]:
            self.assertEqual(
                [event["time_seconds"] for event in sample["events"]], [6, 12]
            )
        self.assertFalse(result["observations_are_recomputed_after_interventions"])
        self.assertIsNone(result["outcome_predictions"])

    def test_policy_refuses_unknown_cues_and_unmeasured_reactions(self):
        plan, observations, profile = self.policy_fixture()
        observations[0]["state"].pop("target_matches")
        with self.assertRaises(InputError):
            simulate_policy(plan, observations, profile, 1, 1)
        plan, observations, profile = self.policy_fixture()
        profile["observed_latency_traces"] = []
        with self.assertRaises(InputError):
            simulate_policy(plan, observations, profile, 1, 1)

    def test_policy_does_not_interpolate_unobserved_readiness(self):
        plan, observations, profile = self.policy_fixture()
        observations[1]["state"]["target_matches"] = False
        result = simulate_policy(plan, observations, profile, 1, 1)
        self.assertEqual(result["samples"][0]["events"][0]["time_seconds"], 11)

    def test_policy_does_not_execute_beyond_observation_horizon(self):
        plan, observations, profile = self.policy_fixture()
        profile["observed_latency_traces"][0]["responses"]["entry"][
            "latency_seconds"
        ] = 20
        result = simulate_policy(plan, observations, profile, 1, 1)
        self.assertEqual(result["samples"][0]["unscheduled_actions"], ["entry"])


if __name__ == "__main__":
    unittest.main()
