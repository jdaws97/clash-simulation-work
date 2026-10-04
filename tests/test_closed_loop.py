"""Human feedback and finite-resource checks using labeled synthetic responses."""

import unittest
from copy import deepcopy

from clashlab.closed_loop import CONTROL_RULES, simulate_closed_loop
from clashlab.common import InputError

from test_spatial import synthetic_scene, synthetic_structure, synthetic_unit
from test_combat import pattern_scene


def health_cue():
    return [
        {
            "actor_id": "attacker",
            "field": "hp_fraction",
            "operator": "at_most",
            "value": 0.5,
        },
        {
            "actor_id": "attacker",
            "field": "active",
            "operator": "equals",
            "value": True,
        },
    ]


def synthetic_plan():
    return {
        "id": "synthetic-coupled-human-plan",
        "observation_interval_seconds": 0.25,
        "control_rules": deepcopy(CONTROL_RULES),
        "failed_action_transition": "stop_stream",
        "resources": {"freeze_casts": 1},
        "streams": [
            {
                "id": "protect-charge",
                "steps": [
                    {
                        "all_conditions": health_cue(),
                        "action": {
                            "id": "protect",
                            "kind": "freeze",
                            "targets": ["tower"],
                            "duration_seconds": 2,
                            "recheck_conditions_on_execution": True,
                            "cost": {"freeze_casts": 1},
                        },
                    }
                ],
            }
        ],
    }


def synthetic_profile(latency=0.25, missed=False):
    return {
        "plan_id": "synthetic-coupled-human-plan",
        "observed_latency_traces": [
            {
                "source_replay": "synthetic-response-fixture-not-player-evidence",
                "responses": {
                    "protect": {
                        "latency_seconds": latency,
                        "missed": missed,
                        "placement_errors": {},
                    }
                },
            }
        ],
    }


def charge_scene():
    return synthetic_scene(
        [
            synthetic_unit(x=6.5, hitpoints=60, damage=40),
            synthetic_structure(damage=30, range=2),
        ]
    )


def one_trial(scene, plan, profile):
    return simulate_closed_loop(scene, plan, profile, seed=7, trials=1)["samples"][0]


def area_plan_and_profile(dx=0):
    plan = synthetic_plan()
    action = plan["streams"][0]["steps"][0]["action"]
    action["kind"] = "area_freeze"
    del action["targets"]
    action["area"] = {
        "x": 7.5,
        "y": 3.5,
        "radius": 0.25,
        "target_team": "defense",
        "target_kinds": ["defense"],
        "target_layers": ["ground"],
    }
    profile = synthetic_profile()
    profile["observed_latency_traces"][0]["responses"]["protect"][
        "placement_errors"
    ] = {"area": {"dx": dx, "dy": 0}}
    return plan, profile


class ClosedLoopTests(unittest.TestCase):
    def test_target_lock_cue_waits_for_a_live_defense_to_select_the_unit(self):
        scene = pattern_scene(charge_scene()["actors"], duration_seconds=2)
        scene["actors"][0]["hitpoints"] = 1000
        scene["actors"][1]["hitpoints"] = 1000
        plan = synthetic_plan()
        plan["streams"][0]["steps"][0]["all_conditions"] = [
            {
                "actor_id": "tower",
                "field": "target_actor",
                "operator": "equals",
                "value": "attacker",
            }
        ]
        sample = one_trial(scene, plan, synthetic_profile(latency=0))
        self.assertFalse(sample["control"]["observations"][0]["cues"]["protect"])
        self.assertEqual(sample["control"]["actions"][0]["cue_time_seconds"], 0.25)
        self.assertEqual(sample["control"]["remaining_resources"]["freeze_casts"], 0)

    def test_target_lock_cue_rejects_missing_actor_and_non_equality_threshold(self):
        for value, operator in (
            ("missing", "equals"),
            ("attacker", "at_least"),
            ([], "equals"),
        ):
            plan = synthetic_plan()
            plan["streams"][0]["steps"][0]["all_conditions"] = [
                {
                    "actor_id": "tower",
                    "field": "target_actor",
                    "operator": operator,
                    "value": value,
                }
            ]
            with (
                self.subTest(value=value, operator=operator),
                self.assertRaises(InputError),
            ):
                one_trial(charge_scene(), plan, synthetic_profile())

    def test_area_placement_error_changes_survival_without_changing_army(self):
        scene = pattern_scene(charge_scene()["actors"], duration_seconds=8)
        accurate = one_trial(scene, *area_plan_and_profile())
        displaced = one_trial(scene, *area_plan_and_profile(dx=1))
        self.assertGreater(accurate["combat"]["actors"]["attacker"]["hp"], 0)
        self.assertEqual(displaced["combat"]["actors"]["attacker"]["hp"], 0)
        self.assertEqual(
            displaced["control"]["actions"][0]["status"], "command_applied"
        )
        effect = next(
            event
            for event in displaced["combat"]["trace"]
            if event.get("effect_id") == "protect"
        )
        self.assertEqual(effect["targets"], [])
        self.assertEqual(effect["area"]["x"], 8.5)
        self.assertEqual(displaced["control"]["remaining_resources"]["freeze_casts"], 0)

    def test_missing_area_placement_measurement_is_not_treated_as_perfect(self):
        scene = pattern_scene(charge_scene()["actors"])
        plan, profile = area_plan_and_profile()
        profile["observed_latency_traces"][0]["responses"]["protect"][
            "placement_errors"
        ] = {}
        with self.assertRaisesRegex(InputError, "placement errors"):
            one_trial(scene, plan, profile)

    def test_area_action_does_not_accept_preselected_target_membership(self):
        scene = pattern_scene(charge_scene()["actors"])
        plan, profile = area_plan_and_profile()
        plan["streams"][0]["steps"][0]["action"]["targets"] = ["tower"]
        with self.assertRaisesRegex(InputError, "recomputed"):
            one_trial(scene, plan, profile)

    def test_single_target_ruleset_rejects_area_control(self):
        plan, profile = area_plan_and_profile()
        with self.assertRaisesRegex(InputError, "Unsupported"):
            one_trial(charge_scene(), plan, profile)

    def test_measured_response_delay_changes_recomputed_combat_outcome(self):
        plan = synthetic_plan()
        timely = one_trial(charge_scene(), plan, synthetic_profile())
        late = one_trial(charge_scene(), plan, synthetic_profile(latency=1.5))
        self.assertEqual(timely["combat"]["actors"]["attacker"]["hp"], 30)
        self.assertEqual(timely["combat"]["actors"]["tower"]["hp"], 0)
        self.assertEqual(late["combat"]["actors"]["attacker"]["hp"], 0)
        self.assertEqual(late["combat"]["actors"]["tower"]["hp"], 20)
        self.assertEqual(late["control"]["actions"][0]["status"], "cue_no_longer_valid")
        self.assertAlmostEqual(
            timely["control"]["actions"][0]["cue_time_seconds"], 0.25
        )
        self.assertAlmostEqual(timely["control"]["actions"][0]["time_seconds"], 0.5)

    def test_next_job_waits_for_result_changed_by_prior_protection(self):
        scene = charge_scene()
        scene["actors"].append(synthetic_unit("main", spawn_seconds="controlled"))
        plan = synthetic_plan()
        plan["resources"]["main_deployment"] = 1
        plan["streams"].append(
            {
                "id": "main-entry",
                "steps": [
                    {
                        "all_conditions": [
                            {
                                "actor_id": "tower",
                                "field": "alive",
                                "operator": "equals",
                                "value": False,
                            }
                        ],
                        "action": {
                            "id": "deploy-main",
                            "kind": "deploy",
                            "targets": ["main"],
                            "recheck_conditions_on_execution": True,
                            "cost": {"main_deployment": 1},
                        },
                    }
                ],
            }
        )
        profile = synthetic_profile()
        profile["observed_latency_traces"][0]["responses"]["deploy-main"] = {
            "latency_seconds": 0.25,
            "missed": False,
            "placement_errors": {"main": {"dx": 0, "dy": 0.25}},
        }
        timely = one_trial(scene, plan, profile)
        self.assertAlmostEqual(timely["combat"]["actors"]["main"]["spawn_seconds"], 2.5)
        self.assertAlmostEqual(timely["combat"]["actors"]["main"]["y"], 3.75)
        late_profile = deepcopy(profile)
        late_profile["observed_latency_traces"][0]["responses"]["protect"][
            "latency_seconds"
        ] = 1.5
        late = one_trial(scene, plan, late_profile)
        self.assertEqual(
            late["combat"]["actors"]["main"]["spawn_seconds"], "controlled"
        )
        self.assertIn("deploy-main", late["control"]["unresolved_actions"])

    def test_missed_action_keeps_resource_and_does_not_apply_freeze(self):
        result = one_trial(
            charge_scene(), synthetic_plan(), synthetic_profile(missed=True)
        )
        self.assertEqual(result["control"]["remaining_resources"]["freeze_casts"], 1)
        self.assertEqual(result["control"]["actions"][0]["status"], "missed")
        self.assertEqual(result["combat"]["actors"]["attacker"]["hp"], 0)

    def test_parallel_jobs_share_finite_resource_in_declared_order(self):
        plan = synthetic_plan()
        second = deepcopy(plan["streams"][0])
        second["id"] = "parallel-protect"
        second["steps"][0]["action"]["id"] = "protect-b"
        plan["streams"].append(second)
        profile = synthetic_profile()
        profile["observed_latency_traces"][0]["responses"]["protect-b"] = deepcopy(
            profile["observed_latency_traces"][0]["responses"]["protect"]
        )
        result = one_trial(charge_scene(), plan, profile)
        self.assertEqual(
            [action["status"] for action in result["control"]["actions"]],
            ["command_applied", "resources_exhausted"],
        )
        self.assertEqual(result["control"]["remaining_resources"]["freeze_casts"], 0)

    def test_missing_player_responses_do_not_invent_a_distribution(self):
        profile = synthetic_profile()
        profile["observed_latency_traces"] = []
        with self.assertRaisesRegex(InputError, "no human distribution"):
            simulate_closed_loop(charge_scene(), synthetic_plan(), profile, 7, 1)

    def test_unobserved_placement_error_is_required_for_deployment(self):
        scene = charge_scene()
        scene["actors"][0]["spawn_seconds"] = "controlled"
        plan = synthetic_plan()
        step = plan["streams"][0]["steps"][0]
        step["all_conditions"] = [
            {"field": "time_seconds", "operator": "at_least", "value": 0}
        ]
        step["action"]["kind"] = "deploy"
        step["action"]["targets"] = ["attacker"]
        del step["action"]["duration_seconds"]
        with self.assertRaisesRegex(InputError, "placement errors"):
            one_trial(scene, plan, synthetic_profile())

    def test_pending_action_never_executes_beyond_combat_horizon(self):
        scene = charge_scene()
        scene["duration_seconds"] = 0.75
        result = one_trial(scene, synthetic_plan(), synthetic_profile(latency=1.5))
        self.assertEqual(result["control"]["actions"], [])
        self.assertEqual(result["control"]["actions_pending_at_horizon"], ["protect"])

    def test_boolean_cues_do_not_accept_numeric_values(self):
        plan = synthetic_plan()
        plan["streams"][0]["steps"][0]["all_conditions"][1]["value"] = 1
        with self.assertRaisesRegex(InputError, "boolean equality"):
            one_trial(charge_scene(), plan, synthetic_profile())

    def test_profile_must_match_the_intended_plan(self):
        profile = synthetic_profile()
        profile["plan_id"] = "different-plan"
        with self.assertRaisesRegex(InputError, "intended coupled plan"):
            one_trial(charge_scene(), synthetic_plan(), profile)


if __name__ == "__main__":
    unittest.main()
