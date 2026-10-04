"""Shared-kernel and full-battle ownership for attacking CC and siege carriers."""

from copy import deepcopy
from math import hypot
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.closed_loop import CONTROL_RULES, simulate_closed_loop
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, validate_battle_bindings
from clashlab.guardian_rules import RULES as OLD_RULES, SCOPE as OLD_SCOPE
from clashlab.siege_rules import RULES, SCOPE
from clashlab.spatial import simulate_spatial

from test_adapters import entity_instance
from test_buffs import buff_instance
from test_full_battle import fixture, freeze_cast
from test_reinforcements import (
    SOURCE,
    direct_command,
    group_parameters,
    payload_instance,
)
from test_siege_machines import release_command, siege_instance


ROOT = Path(__file__).resolve().parents[1]


def reinforcement_battle(catalog, siege=None, duration=1):
    specification, account, army, layout = fixture(catalog, time_limit=duration)
    scene = specification["entity_scene"]
    scene.update(scope=SCOPE, model_rules=deepcopy(RULES), buff_spells=[])
    scene["entities"] = [scene["entities"][0], payload_instance()]
    scene["entities"][0]["town_hall_parameters"]["activation"][
        "activation_delay_seconds"
    ] = 100
    army["troops"] = []
    army["clan_castle"]["troops"] = [{"id": "archer", "level": 1, "count": 1}]
    parameters = group_parameters(["payload"], "siege" if siege is not None else None)
    parameters["deployment_policy"]["regions"][0]["bottom"] = scene["height"]
    scene["attacking_reinforcements"] = parameters
    if siege is not None:
        scene["entities"].append(siege)
        army["siege"] = {
            "id": siege["entity"],
            "level": siege["level"],
            "origin": siege["siege_parameters"]["origin"],
        }
        account["levels"][siege["entity"]] = siege["level"]
    return specification, account, army, layout


def controlled_deployment(time=0.2):
    return {
        "id": "deploy-siege",
        "kind": "deploy",
        "time_seconds": time,
        "targets": ["siege"],
        "positions": {"siege": {"x": 1.5, "y": 7.5}},
    }


def coupled_control(action, conditions, placement_errors):
    action = {
        **action,
        "recheck_conditions_on_execution": True,
        "cost": {"delivery": 1},
    }
    action.pop("time_seconds", None)
    plan = {
        "id": "reinforcement-control",
        "observation_interval_seconds": 0.1,
        "control_rules": deepcopy(CONTROL_RULES),
        "failed_action_transition": "stop_stream",
        "resources": {"delivery": 1},
        "streams": [
            {
                "id": "delivery",
                "steps": [{"all_conditions": conditions, "action": action}],
            }
        ],
    }
    profile = {
        "plan_id": plan["id"],
        "observed_latency_traces": [
            {
                "source_replay": SOURCE,
                "responses": {
                    action["id"]: {
                        "latency_seconds": 0,
                        "missed": False,
                        "placement_errors": placement_errors,
                    }
                },
            }
        ],
    }
    return plan, profile


class SiegeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def simulate(self, specification):
        return simulate_spatial(
            compile_entity_scene(specification["entity_scene"], self.catalog)["scene"]
        )

    def test_direct_delivery_compiles_and_releases_at_exact_time(self):
        specification, account, army, layout = reinforcement_battle(self.catalog)
        specification["entity_scene"]["effects"] = [direct_command(time=0.4)]
        compiled = compile_full_battle(
            specification, account, army, layout, self.catalog
        )
        self.assertEqual(
            compiled["validation"]["attacker_bindings"]["payload"]["origin"],
            "clan_castle_troops",
        )
        result = simulate_spatial(compiled["compiled"]["scene"])
        self.assertAlmostEqual(result["actors"]["payload"]["spawn_seconds"], 0.5)
        self.assertEqual(
            result["sieges"]["reinforcements"]["group"]["delivery_reason"],
            "direct_command",
        )

    def test_manual_controlled_carrier_release_preserves_separate_resource_bindings(
        self,
    ):
        specification, account, army, layout = reinforcement_battle(
            self.catalog, siege_instance(spawn_seconds="controlled")
        )
        specification["entity_scene"]["effects"] = [
            controlled_deployment(),
            release_command(0.4),
        ]
        compiled = compile_full_battle(
            specification, account, army, layout, self.catalog
        )
        bindings = compiled["validation"]["attacker_bindings"]
        self.assertEqual(bindings["siege"]["origin"], "siege")
        self.assertEqual(bindings["payload"]["origin"], "clan_castle_troops")
        result = simulate_spatial(compiled["compiled"]["scene"])
        self.assertAlmostEqual(result["actors"]["payload"]["spawn_seconds"], 0.5)
        self.assertAlmostEqual(result["actors"]["siege"]["death_time"], 0.4)

    def test_post_health_carrier_death_releases_ready_attacker_at_same_timestamp(self):
        carrier = siege_instance(x=9.5, y=5.5)
        carrier["modifiers"]["hitpoints_multiplier"] = 0.001
        specification, _, _, _ = reinforcement_battle(
            self.catalog, carrier, duration=0.5
        )
        scene = specification["entity_scene"]
        scene["attacking_reinforcements"]["deployment_policy"]["regions"][0][
            "right"
        ] = 10
        scene["attacking_reinforcements"]["release"]["initial_delay_seconds"] = 0
        scene["entities"].append(
            entity_instance(
                "air-defense",
                "air-defense",
                13,
                "defense",
                x=15,
                y=5,
                first_attack_seconds=0.25,
            )
        )
        result = self.simulate(specification)
        self.assertAlmostEqual(result["actors"]["siege"]["death_time"], 0.25)
        self.assertAlmostEqual(result["actors"]["payload"]["spawn_seconds"], 0.25)
        launches = [
            event
            for event in result["trace"]
            if event.get("event") == "projectile_launch"
            and event.get("source") == "payload"
        ]
        self.assertTrue(launches)
        self.assertAlmostEqual(launches[0]["time_seconds"], 0.25)

    def test_blimp_arrival_is_independent_of_maximum_step(self):
        times = []
        expected = hypot(12 - 1.5, 6 - 7.5) / (18 / 8)
        for step in (0.01, 0.8):
            specification, _, _, _ = reinforcement_battle(
                self.catalog, siege_instance(first_attack_seconds=100), duration=6
            )
            specification["entity_scene"]["maximum_step_seconds"] = step
            result = self.simulate(specification)
            state = result["sieges"]["states"]["siege"]
            self.assertEqual(state["termination_reason"], "hall_arrival")
            times.append(state["terminated_at"])
        for time in times:
            self.assertAlmostEqual(time, expected, places=7)

    def test_wrecker_clears_wall_using_its_named_wall_damage(self):
        specification, _, _, _ = reinforcement_battle(
            self.catalog, siege_instance("wall-wrecker", y=6), duration=12
        )
        scene = specification["entity_scene"]
        scene["entities"].append(
            entity_instance(
                "wall",
                "wall",
                17,
                "defense",
                x=5,
                y=6,
                mode="passive",
                statistics_mode="none",
                attack_parameters={},
                inactive_attack_interval_seconds=1,
                counts_for_destruction=False,
            )
        )
        result = self.simulate(specification)
        impacts = [
            event
            for event in result["trace"]
            if event.get("event") == "siege_impact" and event["target"] == "wall"
        ]
        self.assertTrue(impacts)
        self.assertTrue(all(event["damage"] == 3250 for event in impacts))
        self.assertEqual(result["actors"]["wall"]["hp"], 0)
        self.assertEqual(
            result["sieges"]["states"]["siege"]["termination_reason"], "hall_arrival"
        )

    def test_beneficial_fields_exclude_siege_but_apply_to_released_troop(self):
        specification, _, _, _ = reinforcement_battle(
            self.catalog, siege_instance(), duration=0.6
        )
        scene = specification["entity_scene"]
        scene["buff_spells"] = [buff_instance(time_seconds=0, x=2, y=7, level=1)]
        scene["effects"] = [
            {
                "id": "injure",
                "kind": "damage",
                "time_seconds": 0.1,
                "targets": ["siege"],
                "amount": 100,
            },
            {
                "id": "heal",
                "kind": "heal",
                "time_seconds": 0.2,
                "targets": ["siege"],
                "amount": 100,
            },
            release_command(0.3),
        ]
        scene["recording_interval_seconds"] = 0.1
        result = self.simulate(specification)
        at_heal = next(
            frame["actors"]["siege"]
            for frame in result["frames"]
            if abs(frame["time_seconds"] - 0.2) < 1e-8
        )
        self.assertEqual(at_heal["hp"], 2900)
        self.assertEqual(at_heal["buff_damage_multiplier"], 1)
        payload = result["frames"][-1]["actors"]["payload"]
        self.assertGreater(payload["buff_damage_multiplier"], 1)

    def test_full_binding_rejects_external_payload_and_double_delivery(self):
        specification, account, army, layout = reinforcement_battle(self.catalog)
        command = controlled_deployment()
        command.update(targets=["payload"], positions={"payload": {"x": 1.5, "y": 1.5}})
        specification["entity_scene"]["effects"] = [command]
        with self.assertRaises(InputError):
            validate_battle_bindings(specification, account, army, layout, self.catalog)
        specification["entity_scene"]["effects"] = [
            direct_command(),
            direct_command(command_id="second"),
        ]
        with self.assertRaises(InputError):
            validate_battle_bindings(specification, account, army, layout, self.catalog)

    def test_received_spells_can_be_charged_without_a_troop_delivery_group(self):
        specification, account, army, layout = fixture(self.catalog)
        scene = specification["entity_scene"]
        scene.update(scope=SCOPE, model_rules=deepcopy(RULES), buff_spells=[])
        account["donation_levels"]["freeze-spell"] = 1
        army["spells"] = [{"id": "freeze-spell", "level": 1, "count": 1}]
        army["clan_castle"]["spells"] = [{"id": "freeze-spell", "level": 1, "count": 1}]
        own = freeze_cast("own")
        received = freeze_cast("received")
        received.update(
            origin="clan_castle",
            received_spell_parameters={
                "source": SOURCE,
                "donor_town_hall": 18,
                "receiver_clan_castle_level": 12,
                "level_basis": "snapshot_receiver_lab_cap_with_unlock_floor",
            },
        )
        scene["freeze_spells"] = [own, received]
        compiled = compile_full_battle(
            specification, account, army, layout, self.catalog
        )
        self.assertEqual(
            {binding["origin"] for binding in compiled["validation"]["spell_bindings"]},
            {"army", "clan_castle"},
        )
        received["origin"] = "army"
        received.pop("received_spell_parameters")
        with self.assertRaises(InputError):
            validate_battle_bindings(specification, account, army, layout, self.catalog)

    def test_old_scope_and_undeclared_payload_do_not_bypass_lifecycle(self):
        specification, _, _, _ = reinforcement_battle(self.catalog)
        scene = specification["entity_scene"]
        scene.update(scope=OLD_SCOPE, model_rules=deepcopy(OLD_RULES))
        with self.assertRaises(InputError):
            compile_entity_scene(scene, self.catalog)
        scene.update(scope=SCOPE, model_rules=deepcopy(RULES))
        scene.pop("attacking_reinforcements")
        with self.assertRaises(InputError):
            compile_entity_scene(scene, self.catalog)

    def test_raw_orphan_siege_pattern_requires_its_delivery_group(self):
        specification, _, _, _ = reinforcement_battle(self.catalog, siege_instance())
        scene = compile_entity_scene(specification["entity_scene"], self.catalog)[
            "scene"
        ]
        scene.pop("attacking_reinforcements")
        scene["actors"] = [
            actor for actor in scene["actors"] if "payload_member_model" not in actor
        ]
        for actor in scene["actors"]:
            actor.pop("siege_model", None)
        with self.assertRaisesRegex(InputError, "owned delivery group"):
            simulate_spatial(scene)

    def test_direct_closed_loop_control_uses_observed_position_error(self):
        specification, _, _, _ = reinforcement_battle(self.catalog)
        scene = compile_entity_scene(specification["entity_scene"], self.catalog)[
            "scene"
        ]
        conditions = [{"field": "time_seconds", "operator": "at_least", "value": 0.2}]
        plan, profile = coupled_control(
            direct_command(), conditions, {"position": {"dx": 0.5, "dy": 0}}
        )
        result = simulate_closed_loop(scene, plan, profile, seed=1, trials=1)[
            "samples"
        ][0]
        self.assertEqual(result["control"]["remaining_resources"]["delivery"], 0)
        self.assertEqual(
            result["combat"]["sieges"]["reinforcements"]["group"]["delivery_point"],
            {"x": 2, "y": 7.5},
        )

    def test_manual_closed_loop_release_rechecks_active_carrier(self):
        specification, _, _, _ = reinforcement_battle(self.catalog, siege_instance())
        scene = compile_entity_scene(specification["entity_scene"], self.catalog)[
            "scene"
        ]
        conditions = [
            {
                "actor_id": "siege",
                "field": "active",
                "operator": "equals",
                "value": True,
            },
            {"field": "time_seconds", "operator": "at_least", "value": 0.2},
        ]
        plan, profile = coupled_control(release_command(), conditions, {})
        result = simulate_closed_loop(scene, plan, profile, seed=1, trials=1)[
            "samples"
        ][0]
        self.assertAlmostEqual(result["combat"]["actors"]["siege"]["death_time"], 0.2)


if __name__ == "__main__":
    unittest.main()
