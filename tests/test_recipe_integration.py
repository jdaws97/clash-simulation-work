"""Paid v29 recipe packages through the complete battle boundary.

Small, explicitly underfilled synthetic layouts keep this a battle integration
check rather than another recommendation or game-calibration claim.
"""

from copy import deepcopy
from inspect import signature
from pathlib import Path
import unittest

from clashlab.adapters import compile_actor
from clashlab.attack_spell_rules import RULES, SCOPE
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.heroes import compile_mirror_clones
from clashlab.recipe_troops import RECIPE_ADAPTERS

from test_adapters import entity_instance
from test_battle_termination import classification, termination_policy
from test_defending_heroes import defender_instance
from test_full_battle import fixture, freeze_cast
from test_heroes import ability
from test_recipe_equipment import equipped_hero, recipe_item
from test_reinforcements import direct_command, group_parameters


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-paid-recipe-integration-not-game-calibration"
TROOP_POLICIES = read_json(ROOT / "data/battle-policies/recipe-troops.json")[
    "parameters"
]


def recipe_instance(catalog, entity, actor_id=None, **changes):
    level = catalog.entity(entity)["levels"][0]["level"]
    actor = entity_instance(actor_id or entity, entity, level, "attack", x=6.5, y=8.5)
    movement, pattern = RECIPE_ADAPTERS[entity]
    actor["recipe_parameters"] = deepcopy(TROOP_POLICIES[entity])
    if pattern == "radial":
        actor["attack_parameters"]["radius"] = 1.2
    if movement == "ground":
        actor["wall_parameters"] = {
            "kind": (
                "jump_enemy_walls"
                if entity in {"headhunter", "apprentice-warden"}
                else "avoid"
            ),
            "source": SOURCE,
        }
    actor.update(changes)
    return actor


def recipe_battle(catalog, family, step=0.25):
    specification, account, army, layout = fixture(catalog, time_limit=4)
    scene = specification["entity_scene"]
    hall = scene["entities"][0]
    hall["town_hall_parameters"]["activation"]["activation_delay_seconds"] = 100
    hall["modifiers"]["hitpoints_multiplier"] = 10
    names = (
        ("balloon", "rocket-balloon", "baby-dragon", "super-wall-breaker", "headhunter")
        if family == "air"
        else ("super-barbarian", "rocket-balloon", "apprentice-warden", "headhunter")
    )
    troops = [recipe_instance(catalog, name) for name in names]
    hunter = next(actor for actor in troops if actor["entity"] == "headhunter")
    hunter.update(x=8.5, y=3.5)
    if family == "air":
        next(
            actor for actor in troops if actor["entity"] == "super-wall-breaker"
        ).update(x=7.5, y=5.5)
    else:
        next(
            actor for actor in troops if actor["entity"] == "apprentice-warden"
        ).update(x=1.5, y=8.5)
    army["troops"] = [
        {"id": actor["entity"], "level": actor["level"], "count": 1} for actor in troops
    ]
    account["levels"].update({actor["entity"]: actor["level"] for actor in troops})
    account["active_super_troops"] = [
        name for name in names if catalog.entity(name).get("troopType") == "super"
    ]

    queen = equipped_hero(
        "archer-queen",
        [recipe_item("action-figure", 27), recipe_item("giant-arrow", 18)],
        id="queen",
        x=1.5,
        y=11.5,
    )
    equipment = queen["hero_parameters"]["equipment"]
    army["heroes"] = [
        {
            "id": "archer-queen",
            "level": queen["level"],
            "mode": "ground",
            "pet": None,
            "equipment": [
                {"id": item["entity"], "level": item["level"]} for item in equipment
            ],
        }
    ]
    account["levels"]["archer-queen"] = queen["level"]
    account["levels"].update({item["entity"]: item["level"] for item in equipment})
    account["hero_availability"]["archer-queen"] = True

    payload = recipe_instance(
        catalog, "balloon", "cc-balloon", x=1.5, y=8.5, spawn_seconds="controlled"
    )
    payload["payload_member_parameters"] = {
        "source": SOURCE,
        "group_id": "reinforcements",
        "donor_town_hall": 18,
        "receiver_clan_castle_level": 12,
        "level_basis": "snapshot_receiver_lab_cap_with_unlock_floor",
    }
    army["clan_castle"]["troops"] = [
        {"id": "balloon", "level": payload["level"], "count": 1}
    ]
    account["donation_levels"]["balloon"] = payload["level"]
    owned = freeze_cast("own-freeze", 0.2)
    received = freeze_cast("cc-freeze", 0.4)
    received.update(
        origin="clan_castle",
        received_spell_parameters={
            key: value
            for key, value in payload["payload_member_parameters"].items()
            if key != "group_id"
        },
    )
    army["spells"] = [{"id": "freeze-spell", "level": 1, "count": 1}]
    army["clan_castle"]["spells"] = deepcopy(army["spells"])
    account["donation_levels"]["freeze-spell"] = 1
    specification["termination_policy"] = termination_policy(
        [
            classification(
                {"origin": origin, "entity": "freeze-spell", "level": 1},
                "support_only",
                "ignore",
            )
            for origin in ("army", "clan_castle")
        ]
    )

    defender = defender_instance(
        instance_id="banner:defender", banner_id="banner", banner_x=8, banner_y=0
    )
    wall = entity_instance(
        "wall",
        "wall",
        1,
        "defense",
        mode="passive",
        statistics_mode="none",
        x=8,
        y=5,
        counts_for_destruction=False,
        attack_parameters={},
        inactive_attack_interval_seconds=1,
    )
    layout["inventory"].update({"hero-banner": 1, "wall": 1})
    layout["buildings"].extend(
        [
            {
                "instance": "banner",
                "id": "hero-banner",
                "level": None,
                "x": 8,
                "y": 0,
                "counts_for_destruction": False,
                "settings": {"hero": "barbarian-king", "level": 1},
            },
            {
                "instance": "wall",
                "id": "wall",
                "level": 1,
                "x": 8,
                "y": 5,
                "counts_for_destruction": False,
            },
        ]
    )
    attackers = [*troops, queen, payload]
    flags = {
        name: True
        for name in signature(compile_actor).parameters
        if name.startswith("allow_")
    }
    generated = compile_mirror_clones(compile_actor(queen, catalog, 8, **flags))
    group = group_parameters([payload["id"]])
    group["deployment_policy"]["regions"][0]["bottom"] = scene["height"]
    scene.update(
        scope=SCOPE,
        model_rules=deepcopy(RULES),
        maximum_step_seconds=step,
        entities=[*attackers, hall, defender, wall],
        buff_spells=[],
        attack_spells=[],
        freeze_spells=[owned, received],
        attacking_reinforcements=group,
        effects=[direct_command(0.1, y=8.5), ability("queen", 0.5)],
        defending_unit_responses={
            "source": SOURCE,
            "actors": {
                actor["id"]: {
                    "primary": "same_tier_as_buildings",
                    "collateral": "allow",
                }
                for actor in [*attackers, *generated]
            },
        },
    )
    return specification, account, army, layout


class RecipeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_paid_air_package_consumption_generated_summon_and_separate_cc_receipts(
        self,
    ):
        inputs = recipe_battle(self.catalog, "air")
        result = simulate_full_battle(*inputs, self.catalog)
        validation = result["validation"]
        expected_housing = sum(
            self.catalog.entity(item["id"])["housingSpace"] * item["count"]
            for item in inputs[2]["troops"]
        )
        self.assertEqual(validation["army"]["used"]["army_housing"], expected_housing)
        self.assertEqual(validation["army"]["used"]["clan_castle_troops"], 5)
        self.assertEqual(result["resource_use"]["used_hero_ability_ids"], ["queen"])
        self.assertTrue(
            all(slot["spent"] for slot in result["resource_use"]["spell_slots"])
        )
        self.assertEqual(
            {slot["origin"] for slot in result["resource_use"]["spell_slots"]},
            {"army", "clan_castle"},
        )
        self.assertIn("cc-balloon", result["resource_use"]["deployed_attacker_ids"])
        giant_id = "queen-action-figure-giant"
        self.assertIn(giant_id, result["generated_summon_ids"])
        self.assertNotIn(giant_id, result["resource_use"]["deployed_attacker_ids"])
        trace = result["combat"]["trace"]
        self.assertEqual(
            sum(event.get("event") == "recipe_troop_consumed" for event in trace), 1
        )
        self.assertEqual(
            sum(
                event.get("event") == "projectile_launch"
                and event.get("source") == "super-wall-breaker"
                for event in trace
            ),
            1,
        )
        releases = [
            event["effect_id"]
            for event in trace
            if event.get("event") == "death_effect_release"
            and event.get("source") == "super-wall-breaker"
        ]
        self.assertEqual(len(releases), 2)
        self.assertEqual(len(set(releases)), 2)
        self.assertEqual(
            sum(event.get("event") == "giant_arrow_released" for event in trace), 1
        )
        self.assertFalse(result["full_game_prediction"])
        for field, value in (
            ("army_housing", expected_housing - 1),
            ("clan_castle_troops", 4),
            ("clan_castle_spells", 0),
        ):
            bad = deepcopy(inputs)
            bad[1]["capacities"][field] = value
            with self.assertRaises(InputError):
                compile_full_battle(*bad, self.catalog)

    def test_ground_package_live_hero_priority_and_apprentice_follow_at_two_steps(self):
        observations = []
        for step in (0.25, 0.125):
            inputs = recipe_battle(self.catalog, "ground", step)
            result = simulate_full_battle(*inputs, self.catalog)
            combat = result["combat"]
            trace = combat["trace"]
            launches = [
                event
                for event in trace
                if event.get("event") == "projectile_launch"
                and event.get("source") == "headhunter"
            ]
            self.assertTrue(launches)
            self.assertEqual(launches[0]["target"], "banner:defender")
            self.assertTrue(
                any(event.get("event") == "headhunter_poison_pulse" for event in trace)
            )
            self.assertTrue(
                any(event.get("event") == "apprentice_life_aura" for event in trace)
            )
            self.assertGreater(combat["actors"]["apprentice-warden"]["x"], 1.5)
            observations.append(
                [
                    (event["target"], round(event["time_seconds"], 7))
                    for event in launches
                ]
            )
        self.assertEqual(observations[0], observations[1])


if __name__ == "__main__":
    unittest.main()
