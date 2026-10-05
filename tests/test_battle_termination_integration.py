"""Real kernel termination occurs once, after settled state and before later work."""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from clashlab.adapters import compile_entity_scene
from clashlab.battle_termination import BattleTermination
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import (
    compile_full_battle,
    compute_battle_outcome,
    simulate_full_battle,
)
from clashlab.hero_roster_rules import RULES as OLD_RULES, SCOPE as OLD_SCOPE
from clashlab.spatial import simulate_spatial
from clashlab.termination_rules import RULES, RULESET, SCOPE

from test_battle_termination import classification, termination_policy
from test_barbarian_king import king_equipment
from test_combat import delayed_projectile_scene
from test_deaths import damage, death_model, death_scene
from test_dragon_duke import duke_equipment
from test_full_battle import add_hero, add_reserve, fixture, freeze_cast
from test_hero_pets import pet_instance
from test_hero_roster_integration import extended_hero, roster_sector
from test_heroes import ability
from test_minion_prince import prince_equipment
from test_pet_integration import command, pet_sector
from test_siege_integration import reinforcement_battle
from test_siege_machines import siege_instance
from test_townhalls import hazard, hazard_scene
from test_valkyrie_integration import building


ROOT = Path(__file__).resolve().parents[1]


def observer(scene, counted_ids, bindings=None):
    return BattleTermination(
        termination_policy(), counted_ids, bindings or {}, [], scene["duration_seconds"]
    )


class BattleTerminationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def full_fixture(self):
        specification, account, army, layout = fixture(self.catalog, time_limit=10)
        scene = specification["entity_scene"]
        scene.update(scope=SCOPE, model_rules=deepcopy(RULES), buff_spells=[])
        scene["entities"] = scene["entities"][:2]
        army["troops"][0]["count"] = 1
        scene["entities"][0]["town_hall_parameters"]["activation"][
            "initial_state"
        ] = "active"
        scene["entities"][0]["town_hall_parameters"]["activation"][
            "activation_delay_seconds"
        ] = 0.5
        scene["entities"][1]["modifiers"]["hitpoints_multiplier"] = 0.0001
        specification["termination_policy"] = termination_policy()
        return specification, account, army, layout

    def test_force_exhaustion_skips_future_support_cast_and_records_exact_terminal_frame(
        self,
    ):
        inputs = self.full_fixture()
        specification, account, army, _ = inputs
        cast = freeze_cast("too-late", 8)
        specification["entity_scene"]["freeze_spells"] = [cast]
        army["spells"] = [{"id": "freeze-spell", "level": 1, "count": 1}]
        specification["termination_policy"] = termination_policy(
            [
                classification(
                    {"origin": "army", "entity": "freeze-spell", "level": 1},
                    "support_only",
                    "ignore",
                )
            ]
        )
        with patch(
            "clashlab.full_battle.simulate_spatial", wraps=simulate_spatial
        ) as simulate:
            result = simulate_full_battle(*inputs, self.catalog)
        self.assertEqual(simulate.call_count, 1)
        self.assertEqual(result["outcome"]["end_reason"], "attack_force_exhausted")
        self.assertAlmostEqual(result["outcome"]["elapsed_seconds"], 0.5)
        self.assertAlmostEqual(result["combat"]["frames"][-1]["time_seconds"], 0.5)
        self.assertFalse(result["resource_use"]["spell_slots"][0]["spent"])
        self.assertTrue(
            all(event["time_seconds"] <= 0.5 for event in result["combat"]["trace"])
        )
        self.assertEqual(result["combat"]["ruleset"], RULESET)

    def test_unspent_user_reserve_keeps_battle_running_to_time_limit(self):
        inputs = self.full_fixture()
        specification, account, army, _ = inputs
        add_reserve(specification, army, account)
        result = simulate_full_battle(*inputs, self.catalog)
        self.assertEqual(result["outcome"]["end_reason"], "declared_time_limit")
        self.assertEqual(result["outcome"]["elapsed_seconds"], 10)
        self.assertIn("reserve", result["resource_use"]["undeployed_attacker_ids"])
        self.assertIn(
            {"kind": "undeployed_army", "id": "reserve", "origin": "army_troops"},
            result["combat"]["termination"]["decision"]["continuation_reasons"],
        )

    def test_full_battle_records_underground_diggy_as_already_deployed(self):
        inputs = self.full_fixture()
        specification, account, army, _ = inputs
        scene = specification["entity_scene"]
        specification["time_limit_seconds"] = 1
        scene["duration_seconds"] = 1
        queen = add_hero(specification, army, account, entity="archer-queen")
        queen.update(x=1.5, y=1.5)
        queen["hero_parameters"][
            "pet_policy"
        ] = "paired_pet_from_explicit_scene_assignment"
        army["heroes"][-1]["pet"] = {"id": "diggy", "level": 10}
        account["levels"]["diggy"] = 10
        scene["pets"] = [pet_instance("diggy", hero_id=queen["id"])]
        result = simulate_full_battle(*inputs, self.catalog)
        self.assertEqual(
            result["combat"]["actors"]["pet"]["spawn_seconds"], "controlled"
        )
        self.assertEqual(
            result["combat"]["hero_pets"]["pets"]["pet"]["phase"], "underground"
        )
        self.assertIn("pet", result["resource_use"]["deployed_attacker_ids"])
        self.assertEqual(result["resource_use"]["deployment_times_seconds"]["pet"], 0)

    def test_v28_full_battle_requires_policy_and_complete_spell_classification(self):
        inputs = self.full_fixture()
        specification, _, army, _ = inputs
        policy = specification.pop("termination_policy")
        with self.assertRaisesRegex(InputError, "termination_policy"):
            compile_full_battle(*inputs, self.catalog)
        specification["termination_policy"] = policy
        army["spells"] = [{"id": "freeze-spell", "level": 1, "count": 1}]
        with self.assertRaisesRegex(InputError, "termination classification"):
            compile_full_battle(*inputs, self.catalog)

    def test_outcome_rejects_stale_termination_receipt_for_a_changed_death_state(self):
        inputs = self.full_fixture()
        result = simulate_full_battle(*inputs, self.catalog)
        combat = deepcopy(result["combat"])
        combat["actors"]["hall"].update(hp=0, death_time=0.25)
        with self.assertRaisesRegex(InputError, "disagrees with complete destruction"):
            compute_battle_outcome(inputs[3], combat, 10)

    def test_old_scope_defaults_remain_time_limit_and_reject_opt_in_policy(self):
        inputs = self.full_fixture()
        specification = inputs[0]
        specification["entity_scene"].update(
            scope=OLD_SCOPE, model_rules=deepcopy(OLD_RULES)
        )
        with self.assertRaisesRegex(InputError, "v28"):
            compile_full_battle(*inputs, self.catalog)
        del specification["termination_policy"]
        result = simulate_full_battle(*inputs, self.catalog)
        self.assertEqual(result["outcome"]["end_reason"], "declared_time_limit")
        self.assertEqual(result["outcome"]["elapsed_seconds"], 10)

    def test_all_counted_destruction_takes_priority_and_legacy_completion_never_replays(
        self,
    ):
        for opt_in in (False, True):
            with self.subTest(opt_in=opt_in):
                inputs = self.full_fixture()
                specification, account, army, _ = inputs
                specification["entity_scene"]["entities"][1]["modifiers"][
                    "damage_multiplier"
                ] = 10000
                add_reserve(specification, army, account)
                if not opt_in:
                    specification["entity_scene"].update(
                        scope=OLD_SCOPE, model_rules=deepcopy(OLD_RULES)
                    )
                    del specification["termination_policy"]
                with patch(
                    "clashlab.full_battle.simulate_spatial", wraps=simulate_spatial
                ) as simulate:
                    result = simulate_full_battle(*inputs, self.catalog)
                self.assertEqual(simulate.call_count, 1)
                self.assertEqual(result["outcome"]["elapsed_seconds"], 0)
                self.assertEqual(
                    result["outcome"]["end_reason"], "all_counted_buildings_destroyed"
                )
                self.assertIn(
                    "reserve", result["resource_use"]["undeployed_attacker_ids"]
                )

    def test_projectile_survives_last_attacker_and_finishes_before_later_effect(self):
        scene = delayed_projectile_scene()
        scene["duration_seconds"] = 3
        scene["recording_interval_seconds"] = 2
        scene["effects"] = [
            damage(time=0.5),
            {
                "id": "later-freeze",
                "time_seconds": 2,
                "kind": "freeze",
                "targets": ["tower"],
                "duration_seconds": 1,
            },
        ]
        result = simulate_spatial(scene, termination=observer(scene, ["tower"]))
        self.assertEqual(result["actors"]["attacker"]["death_time"], 0.5)
        self.assertEqual(result["actors"]["tower"]["death_time"], 1)
        self.assertEqual(result["termination"]["decision"]["time_seconds"], 1)
        self.assertEqual(result["frames"][-1]["time_seconds"], 1)
        self.assertEqual(result["actors"]["tower"]["frozen_until"], 0)

    def test_delayed_attacking_death_packet_continues_until_nonlethal_impact(self):
        scene = death_scene(
            effects=[damage(time=0.5)], duration_seconds=5, recording_interval_seconds=2
        )
        scene["actors"][0]["death_model"] = death_model(delay=1, amount=20)
        result = simulate_spatial(scene, termination=observer(scene, ["tower"]))
        self.assertEqual(
            result["termination"]["decision"]["end_reason"], "attack_force_exhausted"
        )
        self.assertEqual(result["termination"]["decision"]["time_seconds"], 1.5)
        self.assertEqual(result["frames"][-1]["time_seconds"], 1.5)

    def test_phoenix_rescue_settles_before_exhaustion_and_bird_death_does_not_end_owner_life(
        self,
    ):
        scene = pet_sector(
            self.catalog,
            "phoenix",
            scope=SCOPE,
            model_rules=deepcopy(RULES),
            duration_seconds=10,
            effects=[command("damage", 0.5, 100000, "kill-owner")],
        )
        compiled = compile_entity_scene(scene, self.catalog)["scene"]
        compiled["effects"].append(
            {
                "id": "remove-bird-after-protection",
                "kind": "damage",
                "time_seconds": 8.5,
                "targets": ["pet"],
                "amount": 100000,
            }
        )
        result = simulate_spatial(compiled, termination=observer(compiled, ["storage"]))
        self.assertEqual(result["actors"]["hero"]["death_time"], 8.5)
        self.assertEqual(result["termination"]["decision"]["time_seconds"], 8.5)
        self.assertEqual(
            result["termination"]["decision"]["end_reason"], "attack_force_exhausted"
        )
        self.assertEqual(
            len(
                [
                    event
                    for event in result["trace"]
                    if event.get("event") == "phoenix_hatched"
                ]
            ),
            1,
        )

    def test_diggy_underground_continues_when_last_surface_attacker_dies(self):
        scene = pet_sector(
            self.catalog,
            "diggy",
            scope=SCOPE,
            model_rules=deepcopy(RULES),
            duration_seconds=2,
            effects=[command("damage", 0.5, 100000, "kill-owner")],
        )
        compiled = compile_entity_scene(scene, self.catalog)["scene"]
        result = simulate_spatial(compiled, termination=observer(compiled, ["storage"]))
        self.assertEqual(result["actors"]["hero"]["death_time"], 0.5)
        self.assertEqual(
            result["termination"]["decision"]["end_reason"], "declared_time_limit"
        )
        self.assertTrue(
            any(event.get("event") == "pet_emerged" for event in result["trace"])
        )

    def test_blocked_payload_after_siege_death_keeps_actual_kernel_running(self):
        specification, _, _, _ = reinforcement_battle(
            self.catalog, siege=siege_instance(), duration=2
        )
        scene = specification["entity_scene"]
        scene.update(scope=SCOPE, model_rules=deepcopy(RULES))
        blocker = building("blocker", 3, y=6)
        blocker["modifiers"]["hitpoints_multiplier"] = 1000
        scene["entities"].append(blocker)
        scene["attacking_reinforcements"]["release"]["maximum_displacement_tiles"] = 0
        scene["effects"] = [damage("siege", time=1)]
        compiled = compile_entity_scene(scene, self.catalog)["scene"]
        result = simulate_spatial(
            compiled, termination=observer(compiled, ["hall", "blocker"])
        )
        self.assertEqual(result["actors"]["siege"]["death_time"], 1)
        self.assertEqual(result["actors"]["payload"]["spawn_seconds"], "controlled")
        decision = result["termination"]["decision"]
        self.assertEqual(decision["end_reason"], "declared_time_limit")
        self.assertEqual(
            [fact["kind"] for fact in decision["continuation_reasons"]],
            ["pending_release"],
        )

    def test_static_owned_damage_continues_until_last_pulse_but_slow_linger_does_not(
        self,
    ):
        for dps, expected_end in ((10, 1.5), (0, 0.25)):
            with self.subTest(dps=dps):
                scene = hazard_scene(
                    fields=[
                        hazard(
                            source_team="attack",
                            maximum_dps=dps,
                            exit_linger_seconds=20,
                        )
                    ],
                    effects=[damage(time=0.25)],
                    duration_seconds=5,
                )
                result = simulate_spatial(scene, termination=observer(scene, ["tower"]))
                self.assertEqual(
                    result["termination"]["decision"]["time_seconds"], expected_end
                )
                self.assertEqual(
                    result["termination"]["decision"]["end_reason"],
                    "attack_force_exhausted",
                )
        scene["persistent_hazards"][0].pop("source_team")
        with self.assertRaisesRegex(InputError, "source_team"):
            simulate_spatial(scene, termination=observer(scene, ["tower"]))

    def test_released_king_ball_and_duke_death_damage_finish_after_owner_death(self):
        definitions = [
            (
                "barbarian-king",
                [
                    king_equipment("spiky-ball", 20),
                    king_equipment("giant-gauntlet", 12),
                ],
                0.2,
                "spiky_ball_impact",
            ),
            (
                "dragon-duke",
                [duke_equipment("revenge-deck", 20), duke_equipment("fire-heart", 18)],
                0.5,
                "fire_heart_death_impact",
            ),
        ]
        for entity, equipment, death_time, impact_kind in definitions:
            with self.subTest(entity=entity):
                hero = extended_hero(entity, equipment)
                storage = building("storage", 9)
                storage["modifiers"]["hitpoints_multiplier"] = 100
                scene = roster_sector(
                    self.catalog,
                    [hero, storage],
                    duration_seconds=3,
                    effects=[ability("hero"), damage("hero", death_time, 1000000)],
                )
                scene.update(scope=SCOPE, model_rules=deepcopy(RULES))
                compiled = compile_entity_scene(scene, self.catalog)["scene"]
                result = simulate_spatial(
                    compiled, termination=observer(compiled, ["storage"])
                )
                impacts = [
                    event
                    for event in result["trace"]
                    if event.get("event") == impact_kind
                ]
                self.assertEqual(len(impacts), 1)
                self.assertGreater(impacts[0]["time_seconds"], death_time)
                self.assertAlmostEqual(
                    result["termination"]["decision"]["time_seconds"],
                    impacts[0]["time_seconds"],
                )
                self.assertEqual(
                    result["termination"]["decision"]["end_reason"],
                    "attack_force_exhausted",
                )

    def test_dark_orb_continues_after_prince_death_and_status_does_not_extend_expiry(
        self,
    ):
        observations = []
        for step in (0.017, 0.8):
            prince = extended_hero(
                "minion-prince",
                [prince_equipment("metal-pants", 5), prince_equipment("dark-orb", 12)],
                x=0.5,
            )
            storage = building("storage", 8)
            storage["modifiers"]["hitpoints_multiplier"] = 100
            effects = [
                ability("hero"),
                {
                    "id": "freeze-owner",
                    "kind": "freeze",
                    "time_seconds": 0,
                    "targets": ["hero"],
                    "duration_seconds": 10,
                },
                damage("hero", 0.2, 1000000),
            ]
            scene = roster_sector(
                self.catalog,
                [prince, storage],
                duration_seconds=8,
                effects=effects,
                maximum_step_seconds=step,
            )
            scene.update(scope=SCOPE, model_rules=deepcopy(RULES))
            compiled = compile_entity_scene(scene, self.catalog)["scene"]
            result = simulate_spatial(
                compiled, termination=observer(compiled, ["storage"])
            )
            contacts = [
                event["time_seconds"]
                for event in result["trace"]
                if event.get("event") == "dark_orb_contact"
            ]
            self.assertTrue(contacts)
            self.assertGreater(min(contacts), 0.2)
            self.assertAlmostEqual(result["termination"]["decision"]["time_seconds"], 5)
            observations.append(
                (
                    result["actors"]["storage"]["hp"],
                    [round(value, 8) for value in contacts],
                )
            )
        self.assertEqual(observations[0], observations[1])


if __name__ == "__main__":
    unittest.main()
