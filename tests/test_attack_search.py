"""Four bounded acceptance cases for search integrity, not game calibration."""

from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from clashlab.attack_search import (
    SCHEMA,
    CRAFTED_PROFILE_HOOK,
    PAID_CONTROL_HOOK,
    digest,
    enumerate_joint_candidates,
    evaluate_candidate,
    prepare_candidate,
    scenario_environment,
    validate_candidate_scenario,
)
from clashlab.attack_search_runner import (
    cache_identity,
    fingerprints,
    run_search,
    validate_result,
)
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json, write_json
from test_battle_modifiers import modifier_policy
from test_crafted_season import seasonal_battle
from test_full_battle import fixture


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "original-synthetic-search-control-no-guide-no-game-calibration"


def manifest_from_inputs(inputs, profile="legend_i", crafted=False):
    spec, account, army, layout = deepcopy(inputs)
    scene = spec.pop("entity_scene")
    spec["battle_modifier_policy"] = modifier_policy(profile)
    events = []
    for collection in (
        "entities",
        "effects",
        "freeze_spells",
        "healing_spells",
        "buff_spells",
        "attack_spells",
    ):
        for row in scene.get(collection, []):
            if collection == "entities" and (
                row["team"] != "attack" or row["spawn_seconds"] == "controlled"
            ):
                continue
            time = row["spawn_seconds" if collection == "entities" else "time_seconds"]
            events.append(
                {
                    "id": collection + ":" + row["id"],
                    "selector": {"collection": collection, "id": row["id"]},
                    "at_seconds": time,
                    "all_conditions": [
                        {"field": "time_seconds", "operator": "at_least", "value": time}
                    ],
                }
            )
    return {
        "schema": SCHEMA,
        "id": "small-paid-search-control",
        "context": {
            "mode": "ranked" if profile == "legend_i" else "war",
            "league": "Legend I" if profile == "legend_i" else None,
            "profile_id": profile,
            "scenario_id": "synthetic-underfilled-inventory",
        },
        "account": account,
        "layout": layout,
        "battle": spec,
        "scenario_environment": scenario_environment(scene),
        "opponent_inventory": {
            "kind": "synthetic_declared",
            "crafted_status": "selected" if crafted else "synthetic_omitted",
            "source": SOURCE,
        },
        "mechanics": {
            "allow_experimental": True,
            "assumptions": [
                "Pinned unverified snapshot; explicit kernel geometry, targeting, launch and deployment conventions",
                "Role modifier policies are explicit hypotheses, not current-client calibration",
            ],
            "evidence_gaps": [
                "No held-out whole-battle calibration",
                "Synthetic partial inventory is not a representative TH16/17/18 opponent; current crafted rotation unverified",
            ],
        },
        "budget": {"maximum_candidates": 4, "timeout_seconds": 10},
        "army_options": [
            {
                "id": "roster-control",
                "army": army,
                "entity_scene": scene,
                "provenance": {"kind": "original_generated", "source": SOURCE},
            }
        ],
        "plan_options": [
            {
                "id": "immediate",
                "events": events,
                "funnel": {
                    "required": False,
                    "reason": "Synthetic single contact control; no funnel conclusion",
                },
                "provenance": {"kind": "original_generated", "source": SOURCE},
            }
        ],
    }


def small_grid(catalog):
    result = manifest_from_inputs(fixture(catalog))
    roster = deepcopy(result["army_options"][0])
    roster["id"] = "upgraded-roster-control"
    result["account"]["levels"]["pekka"] = 11
    roster["army"]["troops"][0]["level"] = 11
    for actor in roster["entity_scene"]["entities"]:
        if actor["team"] == "attack":
            actor["level"] = 11
    result["army_options"].append(roster)
    plan = deepcopy(result["plan_options"][0])
    plan["id"] = "delayed-control"
    for event in plan["events"]:
        event["at_seconds"] = 4
        event["all_conditions"][0]["value"] = 4
        event["position"] = {"x": 9.5, "y": 6.5}
    result["plan_options"].append(plan)
    return result


def funnel_contract(event_id):
    # Structural fixture only; these labels are never scored as actual readiness.
    state = {"field": "alive", "actor_id": "hall", "operator": "equals", "value": False}
    return {
        "required": True,
        "prerequisites": [state],
        "commit_event_ids": [event_id],
        "deadline_seconds": 3,
        "contingencies": [
            {
                "trigger": trigger,
                "all_conditions": [{**state, "value": True}],
                "response": "hold_commit",
                "event_ids": [],
            }
            for trigger in ("funnel_failed", "hall_bait_detected")
        ],
    }


class AttackSearchAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.rules = read_json(ROOT / "data/mode-rules.json")

    def candidate(self, manifest):
        return enumerate_joint_candidates(manifest, self.rules)["candidates"][0]

    def test_paid_joint_grid_cache_and_unscored_timeout_failure(self):
        manifest = small_grid(self.catalog)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cold = run_search(manifest, ROOT / "data", root / "cold", root / "cache")
            warm = run_search(manifest, ROOT / "data", root / "warm", root / "cache")
            self.assertEqual(
                [r["result"]["status"] for r in cold["rows"]], ["completed"] * 4
            )
            self.assertEqual(
                [r["result"]["objective"]["stars"] for r in cold["rows"]], [3, 0, 3, 3]
            )
            self.assertTrue(all(r["cache_hit"] for r in warm["rows"]))
            self.assertEqual(
                [r["result"] for r in cold["rows"]], [r["result"] for r in warm["rows"]]
            )
            self.assertEqual(cold["recommendations"], [])
            self.assertTrue(
                all(
                    r["result"]["modifier_audit"]["profile_id"] == "legend_i"
                    for r in cold["rows"]
                )
            )
            self.assertFalse(cold["comparisons"][0]["time_comparable"])
            manifest["budget"] = {"maximum_candidates": 1, "timeout_seconds": 0.001}
            timed = run_search(
                manifest, ROOT / "data", root / "timeout", root / "cache"
            )
            self.assertEqual(timed["rows"][0]["result"]["status"], "timeout")
            self.assertIsNone(timed["rows"][0]["result"]["objective"])
            self.assertEqual(timed["comparisons"], [])
            manifest["budget"]["timeout_seconds"] = 9
            with patch(
                "clashlab.attack_search_runner.subprocess.run",
                return_value=subprocess.CompletedProcess([], 7),
            ):
                failed = run_search(
                    manifest, ROOT / "data", root / "failed", root / "cache"
                )
            self.assertEqual(failed["rows"][0]["result"]["status"], "failed")
            self.assertIsNone(failed["rows"][0]["result"]["objective"])
            # Neither timeout nor failed attempt is saved as a scored cache entry.
            self.assertEqual(len(list((root / "cache").glob("*.json"))), 4)
            # Exact P2 injection: preserve exit zero, write JSON [], then continue
            # to the next real paid candidate instead of aborting orchestration.
            real_run = subprocess.run
            calls = []

            def malformed_then_real(command, **kwargs):
                calls.append(command)
                if len(calls) == 1:
                    write_json(Path(command[-1]), [])
                    return subprocess.CompletedProcess(command, 0)
                return real_run(command, **kwargs)

            manifest["budget"] = {"maximum_candidates": 2, "timeout_seconds": 10}
            with patch(
                "clashlab.attack_search_runner.subprocess.run",
                side_effect=malformed_then_real,
            ):
                resumed = run_search(
                    manifest,
                    ROOT / "data",
                    root / "malformed",
                    root / "malformed-cache",
                )
            self.assertEqual(
                [r["result"]["status"] for r in resumed["rows"]],
                ["failed", "completed"],
            )
            self.assertIsNone(resumed["rows"][0]["result"]["objective"])
            self.assertTrue((root / "malformed/report.json").exists())
            self.assertEqual(resumed["comparisons"], [])
            self.assertEqual(len(list((root / "malformed-cache").glob("*.json"))), 1)
            malformed = [
                None,
                [],
                {},
                {"status": "unknown", "objective": None},
                {"status": "failed", "objective": {}},
            ]
            wrong_outcome = deepcopy(cold["rows"][0]["result"])
            wrong_outcome["outcome"] = []
            malformed.append(wrong_outcome)
            for receipt in malformed:
                checked = validate_result(receipt, cold["scenario_sha256"])
                self.assertEqual(checked["status"], "failed")
                self.assertIsNone(checked["objective"])

    def test_manifest_reproducibility_hash_boundaries_and_legal_admission(self):
        manifest = small_grid(self.catalog)
        first = enumerate_joint_candidates(manifest, self.rules)
        self.assertEqual(
            first, enumerate_joint_candidates(deepcopy(manifest), self.rules)
        )
        manifest["budget"]["maximum_candidates"] = 3
        capped = enumerate_joint_candidates(manifest, self.rules)
        self.assertEqual(capped["candidates"], first["candidates"][:3])
        self.assertFalse(capped["complete"])
        # Freeze complete non-attack policy, not just the Hall's structural fields.
        for field, value in (
            ("target_scoring", {"selection": "changed"}),
            ("traps", [{"id": "hidden-extra"}]),
            ("future_defense_policy", {"enabled": False}),
        ):
            drift = deepcopy(first["candidates"][0])
            drift["roster"]["entity_scene"][field] = value
            with self.assertRaisesRegex(InputError, "pinned scenario environment"):
                validate_candidate_scenario(drift)
        drift = deepcopy(first["candidates"][0])
        drift["roster"]["entity_scene"]["entities"][0]["town_hall_parameters"][
            "activation"
        ]["activation_delay_seconds"] = 35
        pinned_fingerprints = fingerprints(ROOT / "data")
        with (
            patch(
                "clashlab.attack_search_runner.fingerprints",
                return_value=pinned_fingerprints,
            ),
            patch(
                "clashlab.attack_search_runner._cache_read",
                side_effect=AssertionError("Scenario drift reached cache"),
            ),
            patch(
                "clashlab.attack_search_runner.subprocess.run",
                side_effect=AssertionError("Scenario drift executed"),
            ),
        ):
            invalid = deepcopy(manifest)
            invalid["army_options"] = [drift["roster"]]
            invalid["budget"]["maximum_candidates"] = 1
            with tempfile.TemporaryDirectory() as folder:
                report = run_search(
                    invalid,
                    ROOT / "data",
                    Path(folder) / "drift",
                    Path(folder) / "cache",
                )
                self.assertEqual(report["rows"][0]["result"]["status"], "rejected")
                self.assertIsNone(report["rows"][0]["result"]["objective"])
                self.assertEqual(report["comparisons"], [])
                self.assertFalse((Path(folder) / "cache").exists())
        candidate = first["candidates"][0]
        fp = fingerprints(ROOT / "data")
        key = cache_identity(candidate, fp, 10, self.rules)
        for changed in (
            {**fp, "code_sha256": "other"},
            {**fp, "data_sha256": "other"},
            {**fp, "runtime": {"python": "other"}},
        ):
            self.assertNotEqual(
                digest(key), digest(cache_identity(candidate, changed, 10, self.rules))
            )
        other = deepcopy(candidate)
        other["context"]["mode"] = "war"
        self.assertNotEqual(
            digest(key), digest(cache_identity(other, fp, 10, self.rules))
        )
        other = deepcopy(candidate)
        other["plan"]["events"][0]["at_seconds"] = 0.1
        self.assertNotEqual(
            digest(key), digest(cache_identity(other, fp, 10, self.rules))
        )
        self.assertNotEqual(
            digest(key), digest(cache_identity(candidate, fp, 9, self.rules))
        )
        candidate["roster"]["army"]["troops"][0]["count"] += 1
        with self.assertRaises(InputError):
            prepare_candidate(candidate, self.catalog, self.rules)
        manifest["context"]["profile_id"] = "none"
        with self.assertRaisesRegex(InputError, "Legend I"):
            enumerate_joint_candidates(manifest, self.rules)

    def test_funnel_spell_and_ability_cues_and_unknown_crafted_fail_closed(self):
        manifest = manifest_from_inputs(fixture(self.catalog))
        candidate = self.candidate(manifest)
        candidate["plan"]["funnel"] = funnel_contract(
            candidate["plan"]["events"][0]["id"]
        )
        result = evaluate_candidate(candidate, self.catalog, self.rules)
        self.assertEqual(result["dependencies"], [PAID_CONTROL_HOOK])
        self.assertIsNone(result["objective"])
        candidate["plan"]["funnel"]["contingencies"].pop()
        with self.assertRaisesRegex(InputError, "both failure"):
            prepare_candidate(candidate, self.catalog, self.rules)
        th18 = deepcopy(manifest)
        th18["layout"]["town_hall"] = 18
        candidate = self.candidate(th18)
        with self.assertRaisesRegex(InputError, "TH18"):
            prepare_candidate(candidate, self.catalog, self.rules)
        unknown = deepcopy(manifest)
        unknown["opponent_inventory"].update(
            kind="current_opponent", crafted_status="unknown"
        )
        candidate = self.candidate(unknown)
        self.assertEqual(
            evaluate_candidate(candidate, self.catalog, self.rules)["status"],
            "blocked_dependency",
        )
        unknown["opponent_inventory"]["crafted_status"] = "synthetic_omitted"
        candidate = self.candidate(unknown)
        with self.assertRaisesRegex(InputError, "synthetic"):
            prepare_candidate(candidate, self.catalog, self.rules)
        # Supported, paid spell and hero ability slots retain their cue obligations.
        from test_full_battle import add_hero, freeze_cast
        from test_heroes import ability

        inputs = fixture(self.catalog)
        hero = add_hero(inputs[0], inputs[2], inputs[1])
        inputs[0]["entity_scene"]["effects"] = [ability(hero["id"])]
        inputs[2]["spells"] = [{"id": "freeze-spell", "level": 1, "count": 1}]
        inputs[0]["entity_scene"]["freeze_spells"] = [freeze_cast()]
        candidate = self.candidate(manifest_from_inputs(inputs))
        for event in candidate["plan"]["events"]:
            if event["selector"]["collection"] in {"effects", "freeze_spells"}:
                event["all_conditions"].append(
                    {
                        "field": "active",
                        "actor_id": hero["id"],
                        "operator": "equals",
                        "value": True,
                    }
                )
        result = evaluate_candidate(candidate, self.catalog, self.rules)
        self.assertEqual(result["dependencies"], [PAID_CONTROL_HOOK])
        self.assertIsNone(result["objective"])

    def test_selected_crafted_weapons_execute_th16_seasonal_paid_control(self):
        for variant in ("cake-a-pult", "hero-hunter", "hot-candle"):
            inputs = seasonal_battle(self.catalog, variant)
            station = next(
                row
                for row in inputs[0]["entity_scene"]["entities"]
                if row["id"] == "station"
            )
            station["modifiers"]["hitpoints_multiplier"] = 1
            manifest = manifest_from_inputs(inputs, profile="none", crafted=True)
            result = evaluate_candidate(
                self.candidate(manifest), self.catalog, self.rules
            )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(
                result["crafted_runtime"]["variants"], {"station": variant}
            )
            self.assertEqual(
                result["crafted_runtime"]["availability"]["station"][
                    "selected_town_hall"
                ],
                16,
            )
            self.assertGreater(result["crafted_event_counts"]["crafted_launch"], 0)
            self.assertGreater(result["crafted_event_counts"]["crafted_shot_impact"], 0)
            self.assertEqual(result["outcome"]["end_reason"], "attack_force_exhausted")
            ranked = manifest_from_inputs(inputs, profile="legend_i", crafted=True)
            scaled = evaluate_candidate(
                self.candidate(ranked), self.catalog, self.rules
            )
            self.assertEqual(scaled["status"], "completed")
            self.assertIn(
                CRAFTED_PROFILE_HOOK,
                scaled["modifier_audit"]["application"]["capabilities"],
            )
            self.assertGreater(scaled["crafted_event_counts"]["crafted_shot_impact"], 0)
            if variant == "cake-a-pult":
                candidate = self.candidate(ranked)
                _, compiled, _ = prepare_candidate(candidate, self.catalog, self.rules)
                compiled["battle_modifier_audit"]["application"]["capabilities"] = []
                with patch(
                    "clashlab.attack_search.compile_full_battle", return_value=compiled
                ):
                    blocked = evaluate_candidate(candidate, self.catalog, self.rules)
                self.assertEqual(blocked["dependencies"], [CRAFTED_PROFILE_HOOK])
                self.assertIsNone(blocked["objective"])


if __name__ == "__main__":
    unittest.main()
