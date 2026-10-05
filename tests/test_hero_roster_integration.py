"""Extended heroes through common command, damage, movement and death phases."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.advanced_defense_rules import RULES as OLD_RULES, SCOPE as OLD_SCOPE
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.dragon_duke import CONTACT_POLICY
from clashlab.full_battle import compile_full_battle
from clashlab.hero_roster_rules import RULES, RULESET, SCOPE, SAMPLED_DUKE_ISOLATION
from clashlab.spatial import simulate_spatial

from test_adapters import entity_instance
from test_barbarian_king import king_equipment
from test_dragon_duke import duke_equipment, duke_parameters
from test_hero_pets import pet_instance
from test_full_battle import fixture as full_battle_fixture
from test_heroes import ability, hero
from test_indirect_defenses import damage_command, indirect_sector
from test_minion_prince import prince_equipment
from test_spell_towers import spell_tower_instance
from test_spring_traps import spring_instance
from test_traps import trap_instance
from test_valkyrie_integration import building
from test_walls import wall_parameters


ROOT = Path(__file__).resolve().parents[1]


def extended_hero(entity="dragon-duke", items=None, **changes):
    levels = {"barbarian-king": 91, "minion-prince": 72, "dragon-duke": 12}
    instance = hero("archer-queen", bare=True, id="hero", x=5.5, y=5.5)
    instance.update(entity=entity, level=levels[entity])
    if entity != "barbarian-king":
        instance["mode"] = "air"
        instance.pop("wall_parameters")
    if entity == "dragon-duke":
        instance["duke_parameters"] = duke_parameters()
    if items:
        instance["hero_parameters"].update(
            equipment=items, loadout_policy="exact_two_equipment"
        )
    instance.update(changes)
    return instance


def roster_sector(catalog, entities, **changes):
    return indirect_sector(
        catalog, entities, scope=SCOPE, model_rules=deepcopy(RULES), **changes
    )


def events(result, name):
    return [event for event in result["trace"] if event.get("event") == name]


class HeroRosterIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def compile(self, entities, **changes):
        return compile_entity_scene(
            roster_sector(self.catalog, entities, **changes), self.catalog
        )["scene"]

    def test_sampled_duke_advances_attracting_contact_independent_of_maximum_step(self):
        duke = extended_hero(x=10, y=5.5)
        ally = entity_instance("ally", "minion", 12, "attack", x=6.999, y=5.5)
        ally["modifiers"]["movement_speed_multiplier"] = 0.5
        specification = roster_sector(
            self.catalog, [duke, ally, building("storage", 14)], duration_seconds=3
        )
        continuous = simulate_spatial(
            compile_entity_scene(specification, self.catalog)["scene"]
        )
        contact = continuous["extended_heroes"]["dragon_duke"]
        self.assertEqual(contact["isolation_contact_policy"], CONTACT_POLICY)
        self.assertGreater(contact["contact_motion_applications"]["hero"], 0)
        self.assertFalse(contact["game_calibrated"])
        self.assertGreater(continuous["actors"]["hero"]["x"], 10)
        self.assertEqual(
            [change["isolated"] for change in contact["isolation_changes"]],
            [True, False],
        )
        policy = read_json(
            ROOT / "data/battle-policies/experimental-duke-isolation.json"
        )
        duke["duke_parameters"].update(policy)
        # Both the actor policy and scene convention must opt in explicitly.
        with self.assertRaisesRegex(InputError, "conventions"):
            compile_entity_scene(specification, self.catalog)
        specification["model_rules"]["duke_isolation"] = SAMPLED_DUKE_ISOLATION
        results = []
        for step in (0.017, 0.8):
            specification["maximum_step_seconds"] = step
            result = simulate_spatial(
                compile_entity_scene(specification, self.catalog)["scene"]
            )
            changes = events(result, "dragon_duke_isolation_changed")
            self.assertGreater(len(changes), 2)
            self.assertLessEqual(len(changes), 31)
            for change in changes:
                ticks = change["time_seconds"] / 0.1
                self.assertAlmostEqual(ticks, round(ticks), delta=1e-8)
            summary = result["extended_heroes"]["dragon_duke"][
                "experimental_isolation_updates"
            ]["hero"]
            self.assertEqual(summary["sample_count"], 31)
            self.assertEqual(summary["status"], "explicit_uncalibrated_hypothesis")
            results.append(result)
        self.assertAlmostEqual(
            results[0]["actors"]["hero"]["x"],
            results[1]["actors"]["hero"]["x"],
            delta=1e-8,
        )
        self.assertAlmostEqual(
            results[0]["actors"]["storage"]["hp"],
            results[1]["actors"]["storage"]["hp"],
            delta=1e-8,
        )

    def test_catalog_heroes_and_equipment_enter_only_their_explicit_scope(self):
        definitions = [
            (
                "barbarian-king",
                [
                    king_equipment("spiky-ball", 20),
                    king_equipment("giant-gauntlet", 12),
                ],
            ),
            (
                "minion-prince",
                [prince_equipment("metal-pants", 5), prince_equipment("noble-iron", 1)],
            ),
            (
                "dragon-duke",
                [duke_equipment("revenge-deck", 20), duke_equipment("fire-heart", 18)],
            ),
        ]
        for entity, items in definitions:
            with self.subTest(entity=entity):
                actor = extended_hero(entity, items)
                specification = roster_sector(
                    self.catalog, [actor, building("storage", 12)]
                )
                scene = compile_entity_scene(specification, self.catalog)["scene"]
                result = simulate_spatial(scene)
                self.assertEqual(result["ruleset"], RULESET)
                self.assertFalse(
                    result["extended_heroes"][entity.replace("-", "_")][
                        "game_calibrated"
                    ]
                )
                specification.update(scope=OLD_SCOPE, model_rules=deepcopy(OLD_RULES))
                with self.assertRaisesRegex(InputError, "v27"):
                    compile_entity_scene(specification, self.catalog)

    def test_prince_captures_five_boosted_packets_and_rescales_final_cooldown(self):
        observations = []
        for step in (0.017, 0.8):
            prince = extended_hero(
                "minion-prince",
                [prince_equipment("metal-pants", 5), prince_equipment("noble-iron", 1)],
            )
            prince["attack_parameters"]["projectile"].update(
                timing="launch_distance_delay",
                delay_seconds=1,
                speed_tiles_per_second=1000000,
            )
            storage = building("storage", 9)
            storage["modifiers"]["hitpoints_multiplier"] = 100
            result = simulate_spatial(
                self.compile(
                    [prince, storage], duration_seconds=5.1, maximum_step_seconds=step
                )
            )
            launches = [
                event
                for event in events(result, "projectile_launch")
                if event["source"] == "hero"
            ]
            impacts = [
                event
                for event in events(result, "projectile_impact")
                if event["source"] == "hero"
            ]
            observations.append(
                [
                    (round(event["time_seconds"], 8), event["damage"])
                    for event in impacts
                ]
            )
            self.assertEqual(len(launches), 7)
            self.assertAlmostEqual(launches[5]["time_seconds"], 4 * 0.85 / 1.06 + 0.85)
            self.assertEqual(
                result["extended_heroes"]["minion_prince"][
                    "noble_iron_launches_remaining"
                ]["hero"],
                0,
            )
            self.assertAlmostEqual(impacts[4]["damage"] - impacts[5]["damage"], 350)
        self.assertEqual(observations[0], observations[1])

    def test_duke_counter_uses_source_attributed_actual_damage(self):
        duke = extended_hero(
            items=[duke_equipment("revenge-deck", 20), duke_equipment("fire-heart", 18)]
        )
        duke["modifiers"]["damage_multiplier"] = 0.000001
        tower = entity_instance("tower", "archer-tower", 1, "defense", x=9, y=4)
        result = simulate_spatial(self.compile([duke, tower], duration_seconds=0.1))
        receipts = events(result, "hero_received_damage")
        weapon = next(receipt for receipt in receipts if receipt["origin"] == "weapon")
        self.assertEqual(weapon["source_actor_id"], "tower")
        self.assertGreater(weapon["actual_health_loss"], 0)
        self.assertEqual(len(events(result, "revenge_deck_counter_launched")), 1)
        self.assertEqual(
            result["actors"]["hero"]["hp"], result["actors"]["hero"]["maximum_hp"]
        )

    def test_duke_trap_reduction_depends_on_friendly_air_membership(self):
        losses = []
        for nearby in (False, True):
            duke = extended_hero(x=5.5, y=5.5)
            duke["modifiers"]["movement_speed_multiplier"] = 0.000001
            entities = [duke, building("storage", 12)]
            if nearby:
                ally = entity_instance("ally", "minion", 12, "attack", x=6, y=5.5)
                ally["modifiers"]["movement_speed_multiplier"] = 0.000001
                entities.append(ally)
            trap = trap_instance("air-bomb", x=5, y=5)
            result = simulate_spatial(
                self.compile(entities, traps=[trap], duration_seconds=0.01)
            )
            receipt = next(
                event
                for event in events(result, "hero_received_damage")
                if event["origin"] == "trap"
            )
            losses.append(receipt["actual_health_loss"])
        self.assertAlmostEqual(losses[0] * 2, losses[1])
        self.assertGreater(losses[0], 0)

    def test_shared_manual_charge_and_king_reduction_apply_once(self):
        king = extended_hero(
            "barbarian-king",
            [king_equipment("spiky-ball", 20), king_equipment("giant-gauntlet", 12)],
        )
        effects = [
            ability("hero"),
            ability("hero", 0.1, "duplicate"),
            damage_command("hero", 0, 1000, "injury"),
        ]
        result = simulate_spatial(
            self.compile(
                [king, building("storage", 9)], effects=effects, duration_seconds=0.2
            )
        )
        receipt = next(
            event
            for event in events(result, "hero_received_damage")
            if event["source_id"] == "injury"
        )
        self.assertAlmostEqual(receipt["actual_health_loss"], 600)
        self.assertEqual(
            [event["status"] for event in events(result, "hero_ability")],
            ["activated", "ability_already_used"],
        )
        self.assertEqual(len(events(result, "spiky_ball_launch")), 1)

    def test_both_duke_air_radius_entry_and_exit_are_exact_in_shared_motion(self):
        for step in (0.017, 0.8):
            duke = extended_hero(x=10, y=5.5)
            duke["modifiers"]["movement_speed_multiplier"] = 0.4
            ally = entity_instance("ally", "minion", 12, "attack", x=1, y=5.5)
            result = simulate_spatial(
                self.compile(
                    [duke, ally, building("storage", 30)],
                    duration_seconds=4.1,
                    maximum_step_seconds=step,
                )
            )
            transitions = events(result, "dragon_duke_isolation_changed")
            self.assertEqual(
                [event["isolated"] for event in transitions], [True, False, True]
            )
            self.assertEqual(
                [round(event["time_seconds"], 8) for event in transitions], [0, 2, 4]
            )

    def test_dark_orb_first_contact_is_exact_while_prince_is_frozen(self):
        for step in (0.017, 0.8):
            prince = extended_hero(
                "minion-prince",
                [prince_equipment("metal-pants", 5), prince_equipment("dark-orb", 12)],
                x=0.5,
            )
            effects = [
                ability("hero"),
                {
                    "id": "freeze-owner",
                    "kind": "freeze",
                    "time_seconds": 0,
                    "targets": ["hero"],
                    "duration_seconds": 5,
                },
            ]
            result = simulate_spatial(
                self.compile(
                    [prince, building("storage", 8)],
                    effects=effects,
                    duration_seconds=2,
                    maximum_step_seconds=step,
                )
            )
            contacts = events(result, "dark_orb_contact")
            self.assertEqual(len(contacts), 1)
            self.assertAlmostEqual(contacts[0]["time_seconds"], 1.75)
            self.assertEqual(contacts[0]["damage"], 100)
            self.assertEqual(result["actors"]["hero"]["x"], 0.5)

    def test_pants_reduces_the_ordinary_weapon_receipt_without_reducing_source(self):
        prince = extended_hero(
            "minion-prince",
            [prince_equipment("metal-pants", 5), prince_equipment("dark-orb", 12)],
        )
        tower = entity_instance("tower", "archer-tower", 1, "defense", x=9, y=4)
        result = simulate_spatial(
            self.compile(
                [prince, tower], effects=[ability("hero")], duration_seconds=0.1
            )
        )
        receipt = next(
            event
            for event in events(result, "hero_received_damage")
            if event["origin"] == "weapon"
        )
        self.assertAlmostEqual(
            receipt["final_damage"], receipt["requested_damage"] * 0.5
        )
        self.assertEqual(
            result["actors"]["tower"]["damage"], receipt["requested_damage"]
        )

    def test_full_battle_binds_new_hero_and_owned_gear(self):
        specification, account, army, layout = full_battle_fixture(self.catalog)
        duke = extended_hero(
            items=[
                duke_equipment("revenge-deck", 20),
                duke_equipment("fire-heart", 18),
            ],
            x=9.5,
        )
        items = duke["hero_parameters"]["equipment"]
        scene = specification["entity_scene"]
        scene.update(scope=SCOPE, model_rules=deepcopy(RULES), buff_spells=[])
        scene["entities"].append(duke)
        account["levels"].update(
            {"dragon-duke": 12, "revenge-deck": 20, "fire-heart": 18}
        )
        account["hero_availability"]["dragon-duke"] = True
        army["heroes"].append(
            {
                "id": "dragon-duke",
                "level": 12,
                "mode": "air",
                "pet": None,
                "equipment": [
                    {"id": item["entity"], "level": item["level"]} for item in items
                ],
            }
        )
        compiled = compile_full_battle(
            specification,
            account,
            army,
            layout,
            self.catalog,
            read_json(ROOT / "data/mode-rules.json"),
        )
        self.assertEqual(compiled["compiled"]["scope"], SCOPE)
        self.assertIn(
            "hero",
            {actor["id"] for actor in compiled["compiled"]["scene"]["actors"]},
        )

    def test_phoenix_defers_fire_heart_until_actual_final_defeat(self):
        duke = extended_hero(
            items=[duke_equipment("revenge-deck", 20), duke_equipment("fire-heart", 18)]
        )
        duke["hero_parameters"][
            "pet_policy"
        ] = "paired_pet_from_explicit_scene_assignment"
        duke["modifiers"]["damage_multiplier"] = 0.000001
        effects = [damage_command("hero", 0.5, 1000000)]
        scene = self.compile(
            [duke, building("storage", 12)],
            pets=[pet_instance("phoenix")],
            effects=effects,
            duration_seconds=9,
        )
        result = simulate_spatial(scene)
        releases = events(result, "fire_heart_death_released")
        self.assertEqual(len(releases), 1)
        self.assertGreater(releases[0]["time_seconds"], 0.5)
        self.assertEqual(
            releases[0]["time_seconds"], result["actors"]["hero"]["death_time"]
        )
        self.assertEqual(len(events(result, "fire_heart_death_impact")), 1)

    def test_poison_tower_hazard_keeps_its_live_actor_identity_for_revenge(self):
        duke = extended_hero(
            items=[duke_equipment("revenge-deck", 20), duke_equipment("fire-heart", 18)]
        )
        duke["modifiers"]["damage_multiplier"] = 0.000001
        tower = spell_tower_instance("poison", x=8)
        tower["spell_tower_parameters"]["cast"]["delay_seconds"] = 0
        result = simulate_spatial(self.compile([duke, tower], duration_seconds=0.1))
        receipts = [
            event
            for event in events(result, "hero_received_damage")
            if event["origin"] == "hazard"
        ]
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["source_actor_id"], "spell-tower")
        self.assertEqual(receipts[0]["source_team"], "defense")
        self.assertGreater(receipts[0]["actual_health_loss"], 0)
        self.assertEqual(len(events(result, "revenge_deck_counter_launched")), 1)

    def test_spring_direct_health_mutation_records_reduced_actual_damage(self):
        king = extended_hero(
            "barbarian-king",
            [king_equipment("spiky-ball", 20), king_equipment("giant-gauntlet", 12)],
        )
        trap = spring_instance(x=5, y=5)
        trap["parameters"]["lethal_damage_policy"] = "actual_hp_death"
        trap["parameters"]["non_troop_policies"]["hero"] = {
            "target_weight": 1,
            "damage_multiplier": 1,
            "push": False,
        }
        result = simulate_spatial(
            self.compile(
                [king, building("storage", 12)],
                traps=[trap],
                effects=[ability("hero")],
                duration_seconds=0.01,
            )
        )
        receipt = next(
            event
            for event in events(result, "hero_received_damage")
            if event["origin"] == "trap"
        )
        self.assertEqual(receipt["source_id"], "spring")
        self.assertAlmostEqual(
            receipt["actual_health_loss"], receipt["requested_damage"] * 0.6
        )
        self.assertAlmostEqual(
            result["actors"]["hero"]["maximum_hp"] - result["actors"]["hero"]["hp"],
            receipt["actual_health_loss"],
        )

    def test_gauntlet_wall_swing_hits_neighbor_without_second_main_launch(self):
        king = extended_hero(
            "barbarian-king",
            [king_equipment("spiky-ball", 20), king_equipment("giant-gauntlet", 12)],
        )
        king["wall_parameters"] = wall_parameters()
        king["wall_parameters"]["cooldown"] = "shared_with_main_weapon"
        king["modifiers"]["movement_speed_multiplier"] = 0.01
        wall = building(
            "wall", 6, entity="wall", level=17, y=5, counts_for_destruction=False
        )
        wall["modifiers"]["hitpoints_multiplier"] = 0.000001
        result = simulate_spatial(
            self.compile(
                [king, wall, building("storage", 8)],
                effects=[ability("hero")],
                duration_seconds=0.01,
            )
        )
        hits = events(result, "wall_impact")
        self.assertEqual(len(hits), 1)
        self.assertEqual(set(hits[0]["targets"]), {"wall", "storage"})
        self.assertFalse(events(result, "projectile_launch"))
        self.assertAlmostEqual(
            result["actors"]["storage"]["maximum_hp"]
            - result["actors"]["storage"]["hp"],
            result["actors"]["hero"]["damage"],
        )


if __name__ == "__main__":
    unittest.main()
