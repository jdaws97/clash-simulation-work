"""Whole declared-army/layout execution, accounting and computed outcomes."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.engine_rules import RULES, SCOPE
from clashlab.full_battle import (
    compile_full_battle,
    compute_battle_outcome,
    simulate_full_battle,
    validate_battle_bindings,
)

from test_adapters import entity_instance, sector
from test_heroes import ability, hero
from test_townhalls import hall
from test_traps import trap_instance


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "complete-underfilled-declaration-fixture-not-modern-village-calibration"


def freeze_cast(cast_id="freeze", time=0, town_hall=16):
    return {
        "id": cast_id,
        "entity": "freeze-spell",
        "level": 1,
        "town_hall": town_hall,
        "time_seconds": time,
        "x": 12,
        "y": 6,
        "parameters": {
            "source": SOURCE,
            "duration_multiplier": 1,
            "radius_multiplier": 1,
            "caster_team": "attack",
        },
    }


def deployment(actor_id, time, command_id="deploy"):
    return {
        "id": command_id,
        "kind": "deploy",
        "time_seconds": time,
        "targets": [actor_id],
        "positions": {actor_id: {"x": 9.5, "y": 5.5}},
    }


def fixture(catalog, town_hall=16, time_limit=5):
    account = {
        "id": "resolved-fixture-account",
        "town_hall": town_hall,
        "capacities": {
            "army_housing": 300 if town_hall == 14 else 320,
            "spell_housing": 11,
            "clan_castle_troops": 50,
            "clan_castle_spells": 3,
            "hero_slots": 4,
            "siege_deployments": 1,
            "max_active_super_troops": 2,
        },
        "levels": {"pekka": 1, "archer": 1, "freeze-spell": 1},
        "donation_levels": {"archer": 1},
        "hero_availability": {},
        "active_super_troops": [],
    }
    army = {
        "troops": [{"id": "pekka", "level": 1, "count": 12}],
        "spells": [],
        "heroes": [],
        "siege": None,
        "clan_castle": {"troops": [], "spells": []},
    }
    defenders = [hall(level=town_hall, town_hall=town_hall, x=10, y=4)]
    attackers = [
        entity_instance(
            f"pekka-{index}",
            "pekka",
            1,
            "attack",
            town_hall=town_hall,
            x=9.5,
            y=5.5,
            wall_parameters={"kind": "avoid", "source": SOURCE},
        )
        for index in range(12)
    ]
    scene = sector(catalog, [*defenders, *attackers])
    scene.update(
        scope=SCOPE,
        model_rules=deepcopy(RULES),
        width=20,
        height=16,
        duration_seconds=time_limit,
        maximum_step_seconds=0.25,
        recording_interval_seconds=1,
        persistent_hazards=[],
        healing_spells=[],
        freeze_spells=[],
        healing_stacking={"source": SOURCE, "groups": {}},
        target_scoring={
            "selection": "arrival_time_then_footprint_distance",
            "source": SOURCE,
        },
        traps=[],
    )
    layout = {
        "id": "complete-declared-underfilled-layout",
        "source": SOURCE,
        "town_hall": town_hall,
        "width": 20,
        "height": 16,
        "inventory": {"town-hall": 1},
        "statistics_policy": deepcopy(scene["statistics_policy"]),
        "buildings": [
            {
                "instance": "hall",
                "id": "town-hall",
                "level": town_hall,
                "x": 10,
                "y": 4,
                "mode": "gigaInferno",
                "counts_for_destruction": True,
            }
        ],
    }
    specification = {
        "id": "complete-declared-battle-fixture",
        "source": SOURCE,
        "time_limit_seconds": time_limit,
        "entity_scene": scene,
    }
    return specification, account, army, layout


def add_reserve(specification, army, account):
    army["troops"].append({"id": "archer", "level": 1, "count": 1})
    specification["entity_scene"]["entities"].append(
        entity_instance(
            "reserve",
            "archer",
            1,
            "attack",
            town_hall=account["town_hall"],
            x=1.5,
            y=1.5,
            spawn_seconds="controlled",
            wall_parameters={"kind": "avoid", "source": SOURCE},
        )
    )


def add_hero(specification, army, account, entity="royal-champion"):
    instance = hero(entity, x=9.5, y=5.5)
    specification["entity_scene"]["entities"].append(instance)
    items = instance["hero_parameters"]["equipment"]
    army["heroes"].append(
        {
            "id": entity,
            "level": instance["level"],
            "mode": instance["mode"],
            "pet": None,
            "equipment": [
                {"id": item["entity"], "level": item["level"]} for item in items
            ],
        }
    )
    account["levels"][entity] = instance["level"]
    account["levels"].update({item["entity"]: item["level"] for item in items})
    account["hero_availability"][entity] = True
    return instance


def scored_state(count=4, destroyed=(), death_time=1):
    buildings = [
        {
            "instance": f"building-{index}",
            "id": "town-hall" if index == 0 else "barracks",
            "counts_for_destruction": True,
        }
        for index in range(count)
    ]
    buildings.extend(
        [
            {"instance": "wall", "id": "wall", "counts_for_destruction": False},
            {"instance": "bomb", "id": "bomb", "counts_for_destruction": False},
        ]
    )
    actors = {
        building["instance"]: {
            "team": "defense",
            "counts_for_destruction": True,
            "hp": 0 if index in destroyed else 100,
            "death_time": death_time if index in destroyed else None,
        }
        for index, building in enumerate(buildings[:count])
    }
    actors["wall"] = {
        "team": "defense",
        "counts_for_destruction": False,
        "hp": 0,
        "death_time": 0,
    }
    return {"buildings": buildings}, {"actors": actors}


class CompleteBattleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_supported_complete_declarations_run_at_th14_th15_and_th16(self):
        for town_hall in (14, 15, 16):
            with self.subTest(town_hall=town_hall):
                inputs = fixture(self.catalog, town_hall)
                untouched = deepcopy(inputs)
                result = simulate_full_battle(*inputs, self.catalog)
                self.assertEqual(inputs, untouched)
                self.assertEqual(result["outcome"]["stars"], 3)
                self.assertEqual(result["outcome"]["destruction"], 100)
                self.assertAlmostEqual(
                    result["outcome"]["completion_time_seconds"], 1.8
                )
                self.assertFalse(result["full_game_prediction"])
                self.assertTrue(result["validation"]["complete_declared_coverage"])
                self.assertEqual(
                    result["validation"]["inventory_scope"],
                    "explicit_declared_inventory_not_maximal_village",
                )
                self.assertEqual(len(result["validation"]["attacker_bindings"]), 12)
                self.assertEqual(
                    result["validation"]["army"]["used"]["army_housing"], 300
                )
                self.assertEqual(
                    len(result["resource_use"]["deployed_attacker_ids"]), 12
                )
                self.assertTrue(
                    all(
                        event["time_seconds"] <= 1.8 + 1e-9
                        for event in result["combat"]["trace"]
                    )
                )

    def test_timeout_scores_surviving_town_hall_without_inventing_stars(self):
        result = simulate_full_battle(
            *fixture(self.catalog, time_limit=0.5), self.catalog
        )
        self.assertEqual(result["outcome"]["stars"], 0)
        self.assertFalse(result["outcome"]["town_hall_destroyed"])
        self.assertEqual(result["outcome"]["end_reason"], "declared_time_limit")
        self.assertEqual(result["outcome"]["elapsed_seconds"], 0.5)
        self.assertGreater(result["combat"]["actors"]["hall"]["hp"], 0)

    def test_time_zero_completion_keeps_later_deployment_and_cast_unspent(self):
        specification, account, army, layout = fixture(self.catalog)
        account["levels"]["pekka"] = 11
        army["troops"][0]["level"] = 11
        for item in specification["entity_scene"]["entities"]:
            if item["team"] == "attack":
                item["level"] = 11
        add_reserve(specification, army, account)
        specification["entity_scene"]["effects"] = [deployment("reserve", 3)]
        army["spells"] = [{"id": "freeze-spell", "level": 1, "count": 2}]
        specification["entity_scene"]["freeze_spells"] = [freeze_cast(time=4)]
        result = simulate_full_battle(
            specification, account, army, layout, self.catalog
        )
        self.assertEqual(result["outcome"]["stars"], 3)
        self.assertEqual(result["outcome"]["completion_time_seconds"], 0)
        self.assertEqual(result["resource_use"]["undeployed_attacker_ids"], ["reserve"])
        self.assertTrue(
            all(not item["spent"] for item in result["resource_use"]["spell_slots"])
        )
        self.assertEqual(
            result["combat"]["actors"]["reserve"]["spawn_seconds"], "controlled"
        )
        self.assertEqual(
            result["combat"]["actors"]["pekka-0"]["hp"],
            self.catalog.level("pekka", 11)["hitpoints"],
        )
        self.assertTrue(
            all(event["time_seconds"] == 0 for event in result["combat"]["trace"])
        )

    def test_unplanned_reserve_troop_and_unused_spell_still_count_against_capacity(
        self,
    ):
        specification, account, army, layout = fixture(self.catalog)
        add_reserve(specification, army, account)
        army["spells"] = [{"id": "freeze-spell", "level": 1, "count": 2}]
        specification["entity_scene"]["freeze_spells"] = [freeze_cast()]
        result = simulate_full_battle(
            specification, account, army, layout, self.catalog
        )
        self.assertEqual(result["validation"]["army"]["used"]["army_housing"], 301)
        self.assertEqual(result["validation"]["army"]["used"]["spell_housing"], 2)
        self.assertEqual(result["validation"]["reserved_attacker_ids"], ["reserve"])
        self.assertEqual(result["resource_use"]["undeployed_attacker_ids"], ["reserve"])
        self.assertEqual(
            sum(item["spent"] for item in result["resource_use"]["spell_slots"]), 1
        )

    def test_post_completion_deployment_does_not_evaluate_unused_blocked_position(self):
        specification, account, army, layout = fixture(self.catalog)
        add_reserve(specification, army, account)
        layout["inventory"]["wall"] = 1
        layout["buildings"].append(
            {
                "instance": "wall",
                "id": "wall",
                "level": 1,
                "x": 0,
                "y": 0,
                "counts_for_destruction": False,
            }
        )
        specification["entity_scene"]["entities"].append(
            entity_instance(
                "wall",
                "wall",
                1,
                "defense",
                x=0,
                y=0,
                mode="passive",
                statistics_mode="none",
                attack_parameters={},
                inactive_attack_interval_seconds=1,
                counts_for_destruction=False,
            )
        )
        command = deployment("reserve", 3)
        command["positions"]["reserve"] = {"x": 0.5, "y": 0.5}
        specification["entity_scene"]["effects"] = [command]
        result = simulate_full_battle(
            specification, account, army, layout, self.catalog
        )
        self.assertAlmostEqual(result["outcome"]["completion_time_seconds"], 1.8)
        self.assertEqual(result["resource_use"]["undeployed_attacker_ids"], ["reserve"])
        self.assertGreater(result["combat"]["actors"]["wall"]["hp"], 0)

    def test_every_wall_and_trap_is_bound_but_neither_changes_destruction_denominator(
        self,
    ):
        specification, account, army, layout = fixture(self.catalog)
        layout["inventory"].update(wall=1, bomb=1)
        for instance, entity, x, y in (("wall", "wall", 0, 0), ("bomb", "bomb", 0, 2)):
            layout["buildings"].append(
                {
                    "instance": instance,
                    "id": entity,
                    "level": 1,
                    "x": x,
                    "y": y,
                    "counts_for_destruction": False,
                }
            )
        specification["entity_scene"]["entities"].append(
            entity_instance(
                "wall",
                "wall",
                1,
                "defense",
                x=0,
                y=0,
                mode="passive",
                statistics_mode="none",
                attack_parameters={},
                inactive_attack_interval_seconds=1,
                counts_for_destruction=False,
            )
        )
        specification["entity_scene"]["traps"] = [trap_instance(id="bomb", x=0, y=2)]
        result = simulate_full_battle(
            specification, account, army, layout, self.catalog
        )
        self.assertEqual(
            set(result["validation"]["defender_bindings"]), {"hall", "wall", "bomb"}
        )
        self.assertEqual(result["outcome"]["counted_building_count"], 1)
        self.assertEqual(result["outcome"]["excluded_instance_ids"], ["bomb", "wall"])
        self.assertEqual(result["outcome"]["stars"], 3)
        self.assertNotIn("bomb", result["combat"]["actors"])
        self.assertEqual(result["combat"]["traps"]["untriggered"], ["bomb"])

    def test_equipped_hero_clones_come_from_lifecycle_without_free_army_slots(self):
        specification, account, army, layout = fixture(self.catalog, time_limit=0.2)
        queen = add_hero(specification, army, account, "archer-queen")
        specification["entity_scene"]["effects"] = [ability(queen["id"])]
        result = simulate_full_battle(
            specification, account, army, layout, self.catalog
        )
        self.assertEqual(len(result["generated_summon_ids"]), 2)
        self.assertEqual(len(result["validation"]["attacker_bindings"]), 13)
        self.assertEqual(result["validation"]["army"]["used"]["army_housing"], 300)
        self.assertEqual(result["resource_use"]["used_hero_ability_ids"], [queen["id"]])
        self.assertTrue(
            all(
                result["combat"]["actors"][actor_id]["spawn_seconds"] == 0
                for actor_id in result["generated_summon_ids"]
            )
        )


class CompleteBattleBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_omitted_extra_or_wrong_level_troop_cannot_change_the_declared_army(self):
        for change in ("omit", "extra", "level"):
            inputs = fixture(self.catalog)
            entities = inputs[0]["entity_scene"]["entities"]
            if change == "omit":
                entities.pop()
            elif change == "extra":
                extra = deepcopy(entities[-1])
                extra["id"] = "extra-attacker"
                entities.append(extra)
            else:
                entities[-1]["level"] = 2
            with (
                self.subTest(change=change),
                self.assertRaisesRegex(InputError, "exactly match every army troop"),
            ):
                compile_full_battle(*inputs, self.catalog)

    def test_defender_identity_geometry_level_mode_and_destruction_are_exact(self):
        for field, value in (
            ("id", "different"),
            ("level", 15),
            ("x", 9),
            ("town_hall", 15),
            ("counts_for_destruction", False),
            ("mode", "passive"),
        ):
            inputs = fixture(self.catalog)
            inputs[0]["entity_scene"]["entities"][0][field] = value
            with self.subTest(field=field), self.assertRaises(InputError):
                compile_full_battle(*inputs, self.catalog)

    def test_missing_or_extra_layout_inventory_cannot_be_silently_subselected(self):
        for change in ("missing_defender", "extra_defender", "missing_wall"):
            inputs = fixture(self.catalog)
            entities = inputs[0]["entity_scene"]["entities"]
            if change == "missing_defender":
                entities.pop(0)
            elif change == "extra_defender":
                extra = deepcopy(entities[0])
                extra["id"] = "extra-hall"
                entities.append(extra)
            else:
                inputs[3]["inventory"]["wall"] = 1
            with self.subTest(change=change), self.assertRaises(InputError):
                compile_full_battle(*inputs, self.catalog)

    def test_capacity_and_account_level_validation_precede_execution(self):
        for change in ("capacity", "owned_level"):
            inputs = fixture(self.catalog)
            if change == "capacity":
                inputs[1]["capacities"]["army_housing"] = 299
            else:
                inputs[1]["levels"]["pekka"] = 0
            with self.subTest(change=change), self.assertRaises(InputError):
                compile_full_battle(*inputs, self.catalog)

    def test_duplicate_deployment_cannot_spend_the_same_reserve_twice(self):
        specification, account, army, layout = fixture(self.catalog)
        add_reserve(specification, army, account)
        specification["entity_scene"]["effects"] = [
            deployment("reserve", 0, "first"),
            deployment("reserve", 1, "second"),
        ]
        with self.assertRaisesRegex(InputError, "once only"):
            compile_full_battle(specification, account, army, layout, self.catalog)

    def test_free_spell_wrong_level_excess_count_and_duplicate_cast_ids_fail(self):
        for change in ("free", "wrong_level", "too_many", "duplicate_id"):
            inputs = fixture(self.catalog)
            scene = inputs[0]["entity_scene"]
            inputs[2]["spells"] = [{"id": "freeze-spell", "level": 1, "count": 1}]
            scene["freeze_spells"] = [freeze_cast()]
            if change == "free":
                inputs[2]["spells"] = []
            elif change == "wrong_level":
                scene["freeze_spells"][0]["level"] = 2
            else:
                scene["freeze_spells"].append(
                    freeze_cast(
                        "freeze" if change == "duplicate_id" else "extra", time=1
                    )
                )
            with self.subTest(change=change), self.assertRaises(InputError):
                compile_full_battle(*inputs, self.catalog)

    def test_unbudgeted_damage_fields_and_post_limit_actions_are_rejected(self):
        for change in ("raw_damage", "hazard", "late_spell", "duration"):
            inputs = fixture(self.catalog)
            scene = inputs[0]["entity_scene"]
            if change == "raw_damage":
                scene["effects"] = [
                    {
                        "id": "free-damage",
                        "kind": "damage",
                        "time_seconds": 0,
                        "targets": ["hall"],
                        "amount": 10000,
                    }
                ]
            elif change == "hazard":
                scene["persistent_hazards"] = [{"id": "unpaid-damage-field"}]
            elif change == "late_spell":
                inputs[2]["spells"] = [{"id": "freeze-spell", "level": 1, "count": 1}]
                scene["freeze_spells"] = [freeze_cast(time=6)]
            else:
                scene["duration_seconds"] = 6
            with self.subTest(change=change), self.assertRaises(InputError):
                compile_full_battle(*inputs, self.catalog)

    def test_bare_hero_wrong_equipment_and_duplicate_ability_cannot_replace_loadout(
        self,
    ):
        for change in ("bare", "gear", "ability"):
            inputs = fixture(self.catalog)
            instance = add_hero(inputs[0], inputs[2], inputs[1])
            if change == "bare":
                instance["hero_parameters"][
                    "loadout_policy"
                ] = "bare_hero_controlled_probe"
                instance["hero_parameters"]["equipment"] = []
            elif change == "gear":
                instance["hero_parameters"]["equipment"][0]["level"] -= 1
            else:
                inputs[0]["entity_scene"]["effects"] = [
                    ability(instance["id"], 0, "one"),
                    ability(instance["id"], 1, "two"),
                ]
            with self.subTest(change=change), self.assertRaises(InputError):
                compile_full_battle(*inputs, self.catalog)

    def test_unsupported_reserved_spell_clan_castle_siege_and_pet_are_not_omitted(self):
        for change in ("spell", "castle", "siege", "pet"):
            inputs = fixture(self.catalog)
            account, army = inputs[1], inputs[2]
            if change == "spell":
                army["spells"] = [{"id": "rage-spell", "level": 1, "count": 1}]
                account["levels"]["rage-spell"] = 1
            elif change == "castle":
                army["clan_castle"]["troops"] = [
                    {"id": "archer", "level": 1, "count": 1}
                ]
            elif change == "siege":
                army["siege"] = {"id": "log-launcher", "level": 1, "origin": "own"}
                account["levels"]["log-launcher"] = 1
            else:
                add_hero(inputs[0], army, account)
                army["heroes"][0]["pet"] = {"id": "phoenix", "level": 1}
                account["levels"]["phoenix"] = 1
            with (
                self.subTest(change=change),
                self.assertRaisesRegex(InputError, "adapter"),
            ):
                compile_full_battle(*inputs, self.catalog)

    def test_unknown_entity_scene_channels_cannot_hide_unbound_commands(self):
        inputs = fixture(self.catalog)
        inputs[0]["entity_scene"]["extra_spells"] = [freeze_cast()]
        with self.assertRaisesRegex(InputError, "unbound"):
            validate_battle_bindings(*inputs, self.catalog)


class BattleOutcomeTests(unittest.TestCase):
    def test_town_hall_fifty_percent_and_full_destruction_award_separate_stars(self):
        for destroyed, stars, percentage in (
            ((0,), 1, 25),
            ((1, 2), 1, 50),
            ((0, 1), 2, 50),
            ((0, 1, 2, 3), 3, 100),
        ):
            layout, combat = scored_state(destroyed=destroyed)
            with self.subTest(destroyed=destroyed):
                outcome = compute_battle_outcome(layout, combat, 5)
                self.assertEqual(outcome["stars"], stars)
                self.assertEqual(outcome["destruction"], percentage)
                self.assertEqual(outcome["excluded_instance_ids"], ["bomb", "wall"])

    def test_percentage_is_not_rounded_up_to_award_a_star(self):
        layout, combat = scored_state(count=101, destroyed=tuple(range(1, 51)))
        outcome = compute_battle_outcome(layout, combat, 5)
        self.assertEqual(outcome["destroyed_building_count"], 50)
        self.assertLess(outcome["destruction"], 50)
        self.assertEqual(outcome["stars"], 0)

    def test_only_deaths_at_or_before_inclusive_time_limit_count(self):
        for death_time, expected in ((5, 3), (5.01, 0)):
            layout, combat = scored_state(
                count=1, destroyed=(0,), death_time=death_time
            )
            with self.subTest(death_time=death_time):
                self.assertEqual(
                    compute_battle_outcome(layout, combat, 5)["stars"], expected
                )

    def test_missing_defender_or_contradictory_death_record_is_rejected(self):
        for change in ("missing", "live_death", "dead_without_time"):
            layout, combat = scored_state(count=1, destroyed=(0,))
            if change == "missing":
                combat["actors"].pop("building-0")
            elif change == "live_death":
                combat["actors"]["building-0"]["hp"] = 100
            else:
                combat["actors"]["building-0"]["death_time"] = None
            with self.subTest(change=change), self.assertRaises(InputError):
                compute_battle_outcome(layout, combat, 5)


if __name__ == "__main__":
    unittest.main()
