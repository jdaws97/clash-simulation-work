"""Paired pets through shared health, movement, acquisition and army binding."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.full_battle import compile_full_battle
from clashlab.pet_rules import RULES, RULESET, SCOPE
from clashlab.siege_rules import RULES as OLD_RULES, SCOPE as OLD_SCOPE
from clashlab.spatial import simulate_spatial

from test_adapters import entity_instance
from test_battle_modifiers import modifier_policy
from test_full_battle import add_hero, fixture
from test_hero_pets import SOURCE, pet_instance
from test_healing import healing_model, support_scene
from test_heroes import ability, hero
from test_indirect_defenses import indirect_sector
from test_spring_traps import spring_instance
from test_townhalls import hall
from test_valkyrie_integration import building


ROOT = Path(__file__).resolve().parents[1]


def paired_hero(**changes):
    instance = hero("archer-queen", bare=True, id="hero", x=2.5, y=3.5)
    instance["hero_parameters"][
        "pet_policy"
    ] = "paired_pet_from_explicit_scene_assignment"
    instance["modifiers"]["damage_multiplier"] = 0.000001
    instance["modifiers"]["range_multiplier"] = 100
    instance.update(changes)
    return instance


def pet_sector(catalog, entity="unicorn", **changes):
    scene = indirect_sector(
        catalog,
        [paired_hero(), building("storage", 9, y=3)],
        scope=SCOPE,
        model_rules=deepcopy(RULES),
        pets=[pet_instance(entity)],
        duration_seconds=3,
        maximum_step_seconds=0.8,
        recording_interval_seconds=0.5,
        width=24,
        height=16,
    )
    scene.update(changes)
    return scene


def events(result, kind):
    return [event for event in result["trace"] if event.get("event") == kind]


def command(kind, time, amount, command_id):
    return {
        "id": command_id,
        "kind": kind,
        "time_seconds": time,
        "targets": ["hero"],
        "amount": amount,
    }


class PetIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.mode_rules = read_json(ROOT / "data" / "mode-rules.json")

    def compile(self, entity="unicorn", **changes):
        return compile_entity_scene(
            pet_sector(self.catalog, entity, **changes), self.catalog
        )["scene"]

    def test_pet_deploys_with_controlled_owner_and_cannot_spend_an_extra_command(self):
        owner = paired_hero(spawn_seconds="controlled")
        deployment = {
            "id": "deploy-owner",
            "kind": "deploy",
            "time_seconds": 0.4,
            "targets": ["hero"],
            "positions": {"hero": {"x": 2.5, "y": 3.5}},
        }
        scene = self.compile(
            entities=[owner, building("storage", 9, y=3)], effects=[deployment]
        )
        result = simulate_spatial(scene)
        self.assertEqual(result["ruleset"], RULESET)
        self.assertEqual(events(result, "pet_deployed")[0]["time_seconds"], 0.4)
        self.assertEqual(result["actors"]["pet"]["buff_class"], "pet")
        self.assertFalse(result["actors"]["pet"]["counts_for_destruction"])
        scene["effects"].append(
            {
                "id": "deploy-pet",
                "kind": "deploy",
                "time_seconds": 0,
                "targets": ["pet"],
                "positions": {"pet": {"x": 2.5, "y": 3.5}},
            }
        )
        with self.assertRaisesRegex(InputError, "independently deployed"):
            simulate_spatial(scene)

    def test_unicorn_contact_and_healing_pulses_do_not_depend_on_step_size(self):
        observations = []
        for step in (0.017, 0.8):
            instance = pet_instance("unicorn")
            instance["parameters"]["spawn_offset"]["dx"] = -5
            scene = self.compile(
                pets=[instance],
                entities=[paired_hero(x=7.5), building("storage", 14, y=3)],
                effects=[command("damage", 0, 1000, "injure-owner")],
                maximum_step_seconds=step,
                recording_interval_seconds=1,
            )
            result = simulate_spatial(scene)
            observations.append(
                (
                    result["actors"]["hero"]["hp"],
                    [
                        round(event["time_seconds"], 8)
                        for event in events(result, "pet_healing_pulse")
                    ],
                )
            )
        self.assertEqual(observations[0], observations[1])
        self.assertEqual(observations[0][1], [1.25, 2.25])

    def test_phoenix_intercepts_aggregated_damage_blocks_healing_and_expires(self):
        effects = [
            command("damage", 0.5, 100000, "damage-a"),
            command("damage", 0.5, 100000, "damage-b"),
            command("heal", 0.5, 100000, "same-time-heal"),
            command("heal", 1, 100000, "later-heal"),
            command("damage", 1.5, 100000, "later-damage"),
        ]
        scene = self.compile("phoenix", effects=effects, duration_seconds=9)
        result = simulate_spatial(scene)
        hatches = events(result, "phoenix_hatched")
        self.assertEqual(len(hatches), 1)
        self.assertEqual(hatches[0]["time_seconds"], 0.5)
        self.assertEqual(result["actors"]["hero"]["death_time"], 8.5)
        self.assertGreater(result["actors"]["pet"]["hp"], 0)
        temporary_frames = [
            frame["actors"]["hero"]["hp"]
            for frame in result["frames"]
            if 0.5 <= frame["time_seconds"] < 8.5
        ]
        self.assertTrue(temporary_frames)
        self.assertEqual(set(temporary_frames), {1})

    def test_unicorn_contact_uses_the_moving_owner_trajectory(self):
        observations = []
        for step in (0.017, 0.8):
            owner = paired_hero(x=7.5)
            owner["modifiers"]["range_multiplier"] = 0.2
            instance = pet_instance()
            instance["parameters"]["spawn_offset"]["dx"] = -5
            scene = self.compile(
                entities=[owner, building("storage", 14, y=3)],
                pets=[instance],
                maximum_step_seconds=step,
                recording_interval_seconds=1,
                duration_seconds=5,
                effects=[command("damage", 0, 1000, "injure-owner")],
            )
            result = simulate_spatial(scene)
            observations.append(
                (
                    result["actors"]["hero"]["hp"],
                    [
                        round(event["time_seconds"], 7)
                        for event in events(result, "pet_healing_pulse")
                    ],
                )
            )
        self.assertEqual(observations[0], observations[1])
        self.assertEqual(observations[0][1], [4, 5])

    def test_fox_cloak_prevents_reacquisition_but_keeps_launched_projectile(self):
        cannon = entity_instance("cannon", "cannon", 1, "defense", x=8, y=3)
        cannon["attack_parameters"]["projectile"] = {
            "timing": "launch_distance_delay",
            "speed_tiles_per_second": 5,
            "destination": "locked_actor_center_at_impact",
            "hit_radius": 0,
        }
        scene = self.compile(
            "spirit-fox",
            entities=[paired_hero(), cannon],
            duration_seconds=2,
        )
        result = simulate_spatial(scene)
        launches = [
            event
            for event in events(result, "projectile_launch")
            if event["source"] == "cannon"
        ]
        self.assertEqual(len(launches), 1)
        impacts = [
            event
            for event in events(result, "projectile_impact")
            if event["source"] == "cannon"
        ]
        self.assertEqual(len(impacts), 1)
        self.assertGreater(impacts[0]["time_seconds"], 0.5)
        self.assertFalse(impacts[0]["protected"])
        self.assertEqual(result["actors"]["hero"]["immune_until"], 0)
        self.assertEqual(
            result["frames"][-1]["actors"]["hero"]["untargetable_until"], 4.5
        )

    def test_diggy_emergence_and_first_hit_stun_are_shared_scheduler_boundaries(self):
        observations = []
        for step in (0.017, 0.8):
            cannon = entity_instance("cannon", "cannon", 1, "defense", x=8, y=3)
            scene = self.compile(
                "diggy",
                entities=[paired_hero(), cannon],
                maximum_step_seconds=step,
                recording_interval_seconds=1,
            )
            result = simulate_spatial(scene)
            observations.append(
                (
                    [
                        round(event["time_seconds"], 8)
                        for event in events(result, "pet_emerged")
                    ],
                    [
                        round(event["time_seconds"], 8)
                        for event in events(result, "pet_emergence_stun")
                    ],
                    result["actors"]["cannon"]["hp"],
                )
            )
        self.assertEqual(observations[0], observations[1])
        self.assertEqual(observations[0][:2], ([1.275], [1.475]))

    def test_old_scope_and_missing_assignment_policy_fail_closed(self):
        scene = pet_sector(self.catalog)
        scene.update(scope=OLD_SCOPE, model_rules=deepcopy(OLD_RULES))
        with self.assertRaises(InputError):
            compile_entity_scene(scene, self.catalog)
        scene = pet_sector(self.catalog)
        scene["entities"][0]["hero_parameters"][
            "pet_policy"
        ] = "omitted_for_controlled_probe"
        with self.assertRaises(InputError):
            compile_entity_scene(scene, self.catalog)

    def test_phoenix_intercepts_town_hall_death_blast_before_poison_damage(self):
        destroy_hall = {
            "id": "destroy-hall",
            "kind": "damage",
            "time_seconds": 0.2,
            "targets": ["hall"],
            "amount": 1000000,
        }
        scene = self.compile(
            "phoenix",
            entities=[paired_hero(x=3.5), hall(x=5, y=3)],
            effects=[destroy_hall],
        )
        scene["actors"][0]["hitpoints"] = 1
        result = simulate_spatial(scene)
        self.assertEqual(len(events(result, "phoenix_hatched")), 1)
        self.assertAlmostEqual(
            events(result, "phoenix_hatched")[0]["time_seconds"], 1.2
        )
        self.assertEqual(result["actors"]["hero"]["hp"], 1)
        self.assertIsNone(result["actors"]["hero"]["death_time"])
        self.assertTrue(events(result, "death_effect_impact"))

    def test_phoenix_rescues_spring_hp_death_but_not_ejection(self):
        for death_policy in ("actual_hp_death", "eject_without_death_effects"):
            with self.subTest(policy=death_policy):
                trap = spring_instance(x=2, y=3)
                trap["parameters"]["lethal_damage_policy"] = death_policy
                trap["parameters"]["non_troop_policies"]["hero"] = {
                    "target_weight": 1,
                    "damage_multiplier": 1,
                    "push": True,
                }
                scene = self.compile("phoenix", traps=[trap], duration_seconds=0.1)
                scene["actors"][0]["hitpoints"] = 1
                result = simulate_spatial(scene)
                if death_policy == "actual_hp_death":
                    self.assertEqual(len(events(result, "phoenix_hatched")), 1)
                    self.assertEqual(result["actors"]["hero"]["hp"], 1)
                else:
                    self.assertFalse(events(result, "phoenix_hatched"))
                    self.assertEqual(result["actors"]["hero"]["hp"], 0)
                    self.assertIsNone(result["actors"]["hero"]["death_time"])

    def test_full_army_pet_binding_and_profile_leave_pet_statistics_independent(self):
        specification, account, army, layout = fixture(self.catalog, time_limit=1)
        owner = add_hero(specification, army, account)
        owner["hero_parameters"][
            "pet_policy"
        ] = "paired_pet_from_explicit_scene_assignment"
        army["heroes"][0]["pet"] = {"id": "unicorn", "level": 10}
        account["levels"]["unicorn"] = 10
        scene = specification["entity_scene"]
        scene.update(
            scope=SCOPE,
            model_rules=deepcopy(RULES),
            buff_spells=[],
            pets=[pet_instance("unicorn", hero_id=owner["id"])],
        )
        specification["battle_modifier_policy"] = modifier_policy("legend_i")
        compiled = compile_full_battle(
            specification, account, army, layout, self.catalog, self.mode_rules
        )
        pet = next(
            actor
            for actor in compiled["compiled"]["scene"]["actors"]
            if actor["id"] == "pet"
        )
        self.assertEqual(pet["hitpoints"], 1950)
        self.assertEqual(pet["pet_model"]["healing_per_pulse"], 70)
        self.assertEqual(
            compiled["validation"]["attacker_bindings"]["pet"]["origin"],
            "assigned_hero_pet",
        )
        for field, value in (
            ("level", 9),
            ("town_hall", 15),
            ("hero_id", "pekka-0"),
            ("id", owner["id"]),
        ):
            with self.subTest(field=field):
                changed = deepcopy(specification)
                changed["entity_scene"]["pets"][0][field] = value
                with self.assertRaises(InputError):
                    compile_full_battle(
                        changed, account, army, layout, self.catalog, self.mode_rules
                    )
        missing = deepcopy(specification)
        missing["entity_scene"]["pets"] = []
        with self.assertRaisesRegex(InputError, "exactly one scene assignment"):
            compile_full_battle(
                missing, account, army, layout, self.catalog, self.mode_rules
            )
        account["levels"]["unicorn"] = 9
        with self.assertRaisesRegex(InputError, "Unavailable owned level"):
            compile_full_battle(
                specification, account, army, layout, self.catalog, self.mode_rules
            )

    def test_healer_pet_healing_needs_an_explicit_quantity_and_stacking_class(self):
        healer = entity_instance(
            "healer", "healer", 9, "attack", x=2.5, y=3.5, attack_parameters={}
        )
        model = healing_model(kind="radial", radius=1)
        healer["healing_parameters"] = {
            field: deepcopy(model[field])
            for field in (
                "kind",
                "radius",
                "projectile",
                "selector",
                "stacking_group",
                "source",
            )
        }
        parameters = healer["healing_parameters"]
        parameters["amount_multiplier"] = 1
        parameters["selector"]["primary_target_ids"] = ["pet"]
        stacking = support_scene()["healing_stacking"]
        stacking["groups"]["test-healers"]["tables"]["pet"] = [1]
        specification = pet_sector(
            self.catalog,
            entities=[paired_hero(), healer, building("storage", 9, y=3)],
            healing_stacking=stacking,
            effects=[
                {
                    "id": "injure-pet",
                    "kind": "damage",
                    "time_seconds": 0,
                    "targets": ["pet"],
                    "amount": 200,
                }
            ],
            duration_seconds=0.05,
        )
        with self.assertRaisesRegex(InputError, "explicit pet healing policy"):
            compile_entity_scene(specification, self.catalog)
        parameters.update(
            pet_healing_basis="hero_catalog_pulse", pet_healing_multiplier=1
        )
        scene = compile_entity_scene(specification, self.catalog)["scene"]
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["pet"]["hp"], 1802.5)
        self.assertEqual(result["actors"]["pet"]["healing_class"], "pet")

    def test_healing_spell_pet_mapping_and_explicit_exclusion_are_honored(self):
        cast = {
            "id": "heal",
            "entity": "healing-spell",
            "level": 10,
            "town_hall": 16,
            "time_seconds": 0,
            "x": 2.5,
            "y": 3.5,
            "parameters": {
                "source": SOURCE,
                "first_pulse_delay_seconds": 0.1,
                "amount_multiplier": 1,
                "radius_multiplier": 1,
                "pulse_interval_multiplier": 1,
                "target_team": "attack",
                "target_layers": ["ground", "air"],
            },
        }
        specification = pet_sector(
            self.catalog,
            healing_spells=[cast],
            duration_seconds=0.2,
            effects=[
                {
                    "id": "injure-pet",
                    "kind": "damage",
                    "time_seconds": 0,
                    "targets": ["pet"],
                    "amount": 200,
                }
            ],
        )
        with self.assertRaisesRegex(InputError, "explicit pet healing policy"):
            compile_entity_scene(specification, self.catalog)
        for basis, multiplier, expected in (
            ("ordinary_catalog_pulse", 0.5, 1780),
            ("explicitly_excluded", 0, 1750),
        ):
            cast["parameters"].update(
                pet_healing_basis=basis, pet_healing_multiplier=multiplier
            )
            scene = compile_entity_scene(specification, self.catalog)["scene"]
            result = simulate_spatial(scene)
            self.assertEqual(result["actors"]["pet"]["hp"], expected)

    def test_healing_tome_requires_a_pet_multiplier_and_heals_that_distinct_class(self):
        warden = hero("grand-warden", id="hero", x=2.5, y=3.5)
        warden["hero_parameters"][
            "pet_policy"
        ] = "paired_pet_from_explicit_scene_assignment"
        warden["modifiers"]["range_multiplier"] = 100
        specification = pet_sector(
            self.catalog,
            entities=[warden, building("storage", 9, y=3)],
            effects=[
                ability("hero"),
                {
                    "id": "injure-pet",
                    "kind": "damage",
                    "time_seconds": 0.1,
                    "targets": ["pet"],
                    "amount": 200,
                },
            ],
            duration_seconds=0.6,
        )
        with self.assertRaisesRegex(InputError, "explicit pet multiplier"):
            compile_entity_scene(specification, self.catalog)
        tome = next(
            item
            for item in warden["hero_parameters"]["equipment"]
            if item["entity"] == "healing-tome"
        )
        tome["parameters"]["healing_multipliers_by_class"]["pet"] = 0.5
        # Eternal Tome grants damage protection; direct injury before activation
        # gives Healing Tome a real wound without bypassing protection semantics.
        specification["effects"][0]["time_seconds"] = 0.2
        scene = compile_entity_scene(specification, self.catalog)["scene"]
        scene["duration_seconds"] = 0.8
        model = next(
            item
            for item in scene["actors"][0]["hero_model"]["equipment"]
            if item["entity"] == "healing-tome"
        )
        expected = 1750 + model["healing_per_second"] * 0.5 * 0.5
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["pet"]["hp"], expected)
        self.assertIn("pet", events(result, "healing_tome_pulse")[0]["targets"])


if __name__ == "__main__":
    unittest.main()
