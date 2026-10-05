"""Paid commands, actual shared state cues and finite exclusive commitments."""

from copy import deepcopy
from math import nextafter
from pathlib import Path
import unittest
import tempfile

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.paid_control import COLLECTIONS, POLICIES
from test_advanced_spell_integration import spell_battle
from test_battle_termination import classification, termination_policy
from test_full_battle import add_hero, add_reserve, deployment, freeze_cast
from test_heroes import ability
from test_hero_pets import pet_instance
from clashlab.attack_spell_rules import RULES, SCOPE
from test_buffs import buff_instance
from test_reinforcements import direct_command
from test_siege_integration import reinforcement_battle, controlled_deployment
from test_siege_machines import siege_instance, release_command
from test_spell_lifecycle_integration import recall
from test_attack_search import manifest_from_inputs
from clashlab.attack_search_runner import run_search

SOURCE = "synthetic-paid-observation-contract-not-game-calibration"


def cue(actor, field="hp_fraction", operator="at_most", value=0.999):
    return {"actor_id": actor, "field": field, "operator": operator, "value": value}


def attach_plan(inputs, overrides=None):
    spec = inputs[0]
    events = []
    for collection in sorted(COLLECTIONS):
        for row in spec["entity_scene"].get(collection, []):
            if collection == "entities" and (
                row["team"] != "attack" or row["spawn_seconds"] == "controlled"
            ):
                continue
            time = row["spawn_seconds" if collection == "entities" else "time_seconds"]
            key = collection + ":" + row["id"]
            events.append(
                {
                    "id": key,
                    "selector": {"collection": collection, "id": row["id"]},
                    "at_seconds": time,
                    "all_conditions": (overrides or {}).get(
                        key,
                        [
                            {
                                "field": "time_seconds",
                                "operator": "at_least",
                                "value": time,
                            }
                        ],
                    ),
                }
            )
    spec["paid_observation_plan"] = {
        "source": SOURCE,
        **POLICIES,
        "observation_interval_seconds": 0.1,
        "events": events,
        "funnel": {"required": False, "reason": "synthetic partial inventory control"},
    }
    return spec["paid_observation_plan"]


def control_battle(catalog, step=0.25, duration=1):
    inputs = spell_battle(catalog, "ice-block-spell", step=step, duration=duration)
    spec, account, army, _ = inputs
    scene = spec["entity_scene"]
    scene.pop("advanced_spell_binding")
    scene["attack_spells"] = []
    scene["entities"][1]["modifiers"]["hitpoints_multiplier"] = 1
    scene["freeze_spells"] = [freeze_cast()]
    army["spells"] = [{"id": "freeze-spell", "level": 1, "count": 1}]
    spec["termination_policy"] = termination_policy(
        [
            classification(
                {"origin": "army", "entity": "freeze-spell", "level": 1},
                "support_only",
                "ignore",
            )
        ]
    )
    return inputs


class PaidObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")

    def test_health_cue_delays_paid_freeze_ability_and_deployment_once(self):
        for step in (0.017, 0.25):
            inputs = control_battle(self.catalog, step)
            spec, account, army, _ = inputs
            owner = add_hero(spec, army, account)
            owner["first_attack_seconds"] = 100
            owner["hero_parameters"][
                "pet_policy"
            ] = "paired_pet_from_explicit_scene_assignment"
            army["heroes"][0]["pet"] = {"id": "unicorn", "level": 10}
            account["levels"]["unicorn"] = 10
            spec["entity_scene"]["pets"] = [
                pet_instance("unicorn", hero_id=owner["id"])
            ]
            add_reserve(spec, army, account)
            spec["entity_scene"]["effects"] = [
                deployment("reserve", 0),
                ability(owner["id"], 0),
            ]
            gated = {"freeze_spells:freeze", "effects:deploy", "effects:ability"}
            # Ability helper owns its exact command ID.
            ability_id = spec["entity_scene"]["effects"][1]["id"]
            gated.add("effects:" + ability_id)
            gated.add("entities:" + owner["id"])
            attach_plan(inputs, {key: [cue("pekka-0")] for key in gated})
            before = deepcopy(inputs)
            result = simulate_full_battle(*inputs, self.catalog)
            self.assertEqual(inputs, before)
            actions = {
                e["event_id"]: e["time_seconds"]
                for e in result["paid_observation"]["actions"]
            }
            self.assertEqual(actions["freeze_spells:freeze"], 0.1)
            self.assertEqual(actions["effects:" + ability_id], 0.1)
            self.assertEqual(result["combat"]["actors"]["pet"]["spawn_seconds"], 0.1)
            self.assertEqual(
                result["resource_use"]["deployment_times_seconds"]["reserve"], 0.1
            )
            self.assertEqual(
                result["resource_use"]["used_hero_ability_ids"], [owner["id"]]
            )
            slots = result["resource_use"]["spell_slots"]
            self.assertEqual(len(slots), 1)
            self.assertTrue(slots[0]["spent"])
            self.assertEqual(slots[0]["cast"]["time_seconds"], 0.1)
            self.assertEqual(result["combat"]["actors"]["hall"]["frozen_until"], 2.6)
            self.assertEqual(result["outcome"]["end_reason"], "declared_time_limit")

    def test_funnel_main_alternate_and_hold_keep_exclusive_paid_reserves(self):
        for choice in ("main", "alternate", "hold"):
            inputs = control_battle(self.catalog)
            spec, account, army, _ = inputs
            add_reserve(spec, army, account)
            spec["entity_scene"]["effects"] = [deployment("reserve", 0.1)]
            plan = attach_plan(inputs)
            plan["funnel"] = {
                "required": True,
                "prerequisites": [
                    cue("pekka-0", value=0.999 if choice == "main" else 0)
                ],
                "commit_event_ids": ["effects:deploy"],
                "deadline_seconds": 0.2,
                "contingencies": [
                    {
                        "trigger": "funnel_failed",
                        "all_conditions": [cue("pekka-0")],
                        "response": (
                            "alternate_events"
                            if choice == "alternate"
                            else "hold_commit"
                        ),
                        "event_ids": (
                            ["freeze_spells:freeze"] if choice == "alternate" else []
                        ),
                    },
                    {
                        "trigger": "hall_bait_detected",
                        "all_conditions": [cue("hall", "alive", "equals", False)],
                        "response": "hold_commit",
                        "event_ids": [],
                    },
                ],
            }
            # In controls without an alternate, the paid spell is explicitly gated off.
            if choice != "alternate":
                next(e for e in plan["events"] if e["id"] == "freeze_spells:freeze")[
                    "all_conditions"
                ] = [cue("hall", "alive", "equals", False)]
            result = simulate_full_battle(*inputs, self.catalog)
            expected = {
                "main": "main",
                "alternate": "funnel_failed",
                "hold": "funnel_failed",
            }[choice]
            self.assertEqual(
                result["paid_observation"]["funnel_decisions"][0]["choice"], expected
            )
            resources = result["resource_use"]
            self.assertEqual(
                resources["deployment_times_seconds"]["reserve"],
                0.1 if choice == "main" else None,
            )
            self.assertEqual(
                resources["spell_slots"][0]["spent"], choice == "alternate"
            )
            if choice == "alternate":
                self.assertEqual(
                    resources["spell_slots"][0]["cast"]["time_seconds"], 0.2
                )
            self.assertEqual(result["outcome"]["end_reason"], "declared_time_limit")

    def test_delayed_generated_spell_survives_army_loss_and_missing_or_duplicate_paid_selectors_reject(
        self,
    ):
        for step in (0.017, 0.25):
            inputs = spell_battle(self.catalog, "bat-spell", step=step, duration=1.2)
            plan = attach_plan(
                inputs,
                {"attack_spells:spell": [cue("pekka-0", "alive", "equals", False)]},
            )
            result = simulate_full_battle(*inputs, self.catalog)
            self.assertEqual(result["combat"]["actors"]["pekka-0"]["death_time"], 0)
            self.assertEqual(
                result["resource_use"]["spell_slots"][0]["cast"]["time_seconds"], 0.1
            )
            generated = result["resource_use"]["generated_spell_units"]
            self.assertTrue(generated)
            self.assertTrue(
                all(
                    s["released_at"] is not None and s["released_at"] >= 0.1
                    for s in generated.values()
                )
            )
            self.assertTrue(
                any(
                    e.get("event") == "projectile_launch"
                    and e.get("source") in generated
                    for e in result["combat"]["trace"]
                )
            )
            for broken in ("missing", "duplicate"):
                altered = deepcopy(inputs)
                events = altered[0]["paid_observation_plan"]["events"]
                if broken == "missing":
                    events.pop()
                else:
                    duplicate = deepcopy(events[0])
                    duplicate["id"] += "-duplicate"
                    events.append(duplicate)
                with self.assertRaisesRegex(InputError, "Paid"):
                    compile_full_battle(*altered, self.catalog)

    def test_paid_direct_and_carrier_delivery_recheck_shared_group_and_release_once(
        self,
    ):
        for carrier in (False, True):
            for step in (0.017, 0.25):
                inputs = reinforcement_battle(
                    self.catalog,
                    siege_instance(spawn_seconds="controlled") if carrier else None,
                )
                spec, account, army, _ = inputs
                scene = spec["entity_scene"]
                scene.update(
                    scope=SCOPE,
                    model_rules=deepcopy(RULES),
                    pets=[],
                    attack_spells=[],
                    maximum_step_seconds=step,
                )
                # Keep a paid undeployed reserve, so the admission gate cannot be
                # confused with force exhaustion before the carrier is deployed.
                add_reserve(spec, army, account)
                scene["effects"] = (
                    [controlled_deployment(0.2), release_command(0.2)]
                    if carrier
                    else [direct_command(0.2)]
                )
                spec["termination_policy"] = termination_policy()
                attach_plan(inputs)
                result = simulate_full_battle(*inputs, self.catalog)
                group = result["combat"]["sieges"]["reinforcements"]["group"]
                self.assertEqual(group["delivery_time"], 0.2)
                self.assertAlmostEqual(
                    result["combat"]["actors"]["payload"]["spawn_seconds"], 0.3
                )
                self.assertEqual(
                    sum(
                        e["selector"]["collection"] == "effects"
                        for e in result["paid_observation"]["actions"]
                    ),
                    2 if carrier else 1,
                )
                if carrier:
                    self.assertEqual(
                        result["combat"]["actors"]["siege"]["death_time"], 0.2
                    )
                self.assertEqual(result["outcome"]["end_reason"], "declared_time_limit")

    def test_delayed_buff_and_recall_use_shared_membership_and_relative_return(self):
        for step in (0.017, 0.25):
            inputs = control_battle(self.catalog, step)
            spec, account, army, _ = inputs
            scene = spec["entity_scene"]
            scene["freeze_spells"] = []
            scene["entities"][1]["first_attack_seconds"] = 0.7
            army["spells"] = []
            rage = buff_instance(id="rage", time_seconds=0, x=9.5, y=5.5)
            scene["buff_spells"] = [rage]
            account["levels"]["rage-spell"] = 6
            army["spells"].append({"id": "rage-spell", "level": 6, "count": 1})
            recall(inputs, 0, 0.5, x=9.5)
            attach_plan(
                inputs,
                {
                    "buff_spells:rage": [cue("pekka-0")],
                    "attack_spells:recipe-cast": [cue("pekka-0")],
                },
            )
            # Recipe fixture identity is part of the paid declaration.
            for event in spec["paid_observation_plan"]["events"]:
                if event["selector"]["collection"] == "attack_spells":
                    event["all_conditions"] = [cue("pekka-0")]
            result = simulate_full_battle(*inputs, self.catalog)
            self.assertTrue(
                all(
                    slot["cast"]["time_seconds"] == 0.1
                    for slot in result["resource_use"]["spell_slots"]
                )
            )
            captures = [
                e
                for e in result["combat"]["trace"]
                if e.get("event") == "recall_capture"
            ]
            returns = [
                e
                for e in result["combat"]["trace"]
                if e.get("event") == "recall_redeployment"
            ]
            self.assertEqual(captures[0]["time_seconds"], 0.1)
            self.assertIn("pekka-0", captures[0]["actors"])
            self.assertEqual(returns[0]["time_seconds"], 0.6)
            self.assertTrue(
                any(
                    e.get("event") == "buff_status_change"
                    and e.get("target") == "pekka-0"
                    and e["damage_multiplier"] > 1
                    for e in result["combat"]["trace"]
                )
            )
            self.assertTrue(
                any(
                    e.get("event") == "projectile_launch"
                    and e.get("source") == "pekka-0"
                    and e["time_seconds"] >= 0.6
                    for e in result["combat"]["trace"]
                )
            )
            self.assertEqual(result["outcome"]["elapsed_seconds"], 1)

    def test_positive_and_final_deadlines_are_exact_and_alternate_cue_is_rechecked(
        self,
    ):
        for deadline in (5e-12, 1.0):
            inputs = control_battle(self.catalog, step=0.25)
            scene = inputs[0]["entity_scene"]
            scene["freeze_spells"][0]["time_seconds"] = deadline
            if deadline == 1:
                inputs[0]["entity_scene"]["maximum_step_seconds"] = nextafter(1.0, 0)
            attach_plan(inputs)
            result = simulate_full_battle(*inputs, self.catalog)
            self.assertEqual(
                result["resource_use"]["spell_slots"][0]["cast"]["time_seconds"],
                deadline,
            )
            self.assertEqual(result["outcome"]["elapsed_seconds"], 1)
        inputs = control_battle(self.catalog)
        spec, account, army, _ = inputs
        add_reserve(spec, army, account)
        spec["entity_scene"]["effects"] = [deployment("reserve", 0.1)]
        spec["entity_scene"]["freeze_spells"][0]["time_seconds"] = 0.2
        plan = attach_plan(inputs)
        plan["funnel"] = {
            "required": True,
            "prerequisites": [cue("hall", "alive", "equals", False)],
            "commit_event_ids": ["effects:deploy"],
            "deadline_seconds": 0.3,
            "contingencies": [
                {
                    "trigger": "funnel_failed",
                    "all_conditions": [cue("hall", "alive", "equals", False)],
                    "response": "hold_commit",
                    "event_ids": [],
                },
                {
                    "trigger": "hall_bait_detected",
                    "all_conditions": [cue("pekka-0", value=1, operator="equals")],
                    "response": "alternate_events",
                    "event_ids": ["freeze_spells:freeze"],
                },
            ],
        }
        result = simulate_full_battle(*inputs, self.catalog)
        self.assertEqual(
            result["paid_observation"]["funnel_decisions"],
            [{"time_seconds": 0, "choice": "hall_bait_detected"}],
        )
        self.assertFalse(result["resource_use"]["spell_slots"][0]["spent"])
        self.assertIsNone(result["resource_use"]["deployment_times_seconds"]["reserve"])

    def test_search_requires_policy_then_runs_same_paid_observation_and_cache(self):
        inputs = control_battle(self.catalog)
        plan = attach_plan(inputs, {"freeze_spells:freeze": [cue("pekka-0")]})
        inputs[0].pop("paid_observation_plan")
        manifest = manifest_from_inputs(inputs)
        original = manifest["plan_options"][0]
        original["events"] = deepcopy(plan["events"])
        opted = deepcopy(original)
        opted["id"] = "explicit-paid-state-cues"
        opted["observation_policy"] = {
            key: deepcopy(value)
            for key, value in plan.items()
            if key not in {"events", "funnel"}
        }
        manifest["plan_options"].append(opted)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = Path(__file__).resolve().parents[1] / "data"
            result = run_search(manifest, data, root / "cold", root / "cache")
            self.assertEqual(
                [row["result"]["status"] for row in result["rows"]],
                ["blocked_dependency", "completed"],
            )
            paid = result["rows"][1]["result"]
            self.assertEqual(
                paid["resource_use"]["spell_slots"][0]["cast"]["time_seconds"], 0.1
            )
            self.assertEqual(
                paid["paid_observation"]["capability"], "paid-observation-scheduler-v1"
            )
            repeated = run_search(manifest, data, root / "warm", root / "cache")
            self.assertTrue(repeated["rows"][1]["cache_hit"])
            self.assertEqual(repeated["rows"][1]["result"], paid)
            self.assertEqual(result["recommendations"], [])


if __name__ == "__main__":
    unittest.main()
