"""Advanced defense models through the shared spatial lifecycle and event queue."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.advanced_defense_rules import RULES, RULESET, SCOPE
from clashlab.battle_modifiers import apply_battle_modifiers
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.pet_rules import RULES as OLD_RULES, SCOPE as OLD_SCOPE
from clashlab.spatial import simulate_spatial

from test_advanced_defenses import multi_gear_instance, super_wizard_instance
from test_giga_bombs import giga_instance, response
from test_indirect_defenses import fixed_tank, indirect_sector
from test_battle_modifiers import modifier_policy
from test_closed_loop import one_trial, synthetic_plan, synthetic_profile
from test_full_battle import fixture as full_battle_fixture
from test_guardians import guardian_hall, guardian_instance
from test_hero_pets import pet_instance
from test_pet_integration import paired_hero
from test_spell_towers import spell_tower_instance
from test_valkyrie_integration import building


ROOT = Path(__file__).resolve().parents[1]


def advanced_sector(catalog, entities, **changes):
    return indirect_sector(
        catalog, entities, scope=SCOPE, model_rules=deepcopy(RULES), **changes
    )


def events(result, name):
    return [event for event in result["trace"] if event.get("event") == name]


class AdvancedDefenseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.mode_rules = read_json(ROOT / "data" / "mode-rules.json")

    def simulate(self, entities, **changes):
        scene = compile_entity_scene(
            advanced_sector(self.catalog, entities, **changes), self.catalog
        )["scene"]
        return simulate_spatial(scene)

    def test_multi_gear_launch_cadence_is_independent_of_solver_step(self):
        for step in (0.017, 0.8):
            result = self.simulate(
                [multi_gear_instance(), fixed_tank(x=9.5, y=5.5)],
                duration_seconds=1,
                maximum_step_seconds=step,
            )
            launches = events(result, "projectile_launch")
            self.assertEqual(result["ruleset"], RULESET)
            self.assertEqual(
                [round(event["time_seconds"], 6) for event in launches],
                [0, 0.192, 0.384, 0.576, 0.959],
            )
            self.assertEqual(
                result["multi_gear"]["states"]["multi-gear"]["launched_shots"], 5
            )

    def test_super_wizard_releases_secondary_once_around_primary(self):
        result = self.simulate(
            [
                super_wizard_instance(),
                fixed_tank("primary", x=9.5, y=5.5),
                fixed_tank("near", x=11, y=5.5),
                fixed_tank("remote", x=12.5, y=5.5),
            ],
            duration_seconds=0.1,
        )
        impacts = events(result, "projectile_impact")
        self.assertEqual([event["target"] for event in impacts], ["primary", "near"])
        self.assertEqual(impacts[0]["damage"], 377)
        self.assertAlmostEqual(impacts[1]["damage"], 150.8)
        self.assertEqual(impacts[1]["fanout_link"]["primary"], "primary")

    def test_giga_bomb_remains_separate_from_targetable_actors(self):
        trap = giga_instance({"tank": response()})
        result = self.simulate(
            [multi_gear_instance(first_attack_seconds=100), fixed_tank(x=12, y=10)],
            traps=[trap],
            duration_seconds=0.6,
        )
        self.assertNotIn("giga", result["actors"])
        self.assertEqual(result["giga_bombs"]["resolved"], ["giga"])
        self.assertEqual(events(result, "giga_bomb_trigger")[0]["time_seconds"], 0)
        self.assertAlmostEqual(result["actors"]["tank"]["x"], 14)

    def test_delayed_fanout_survives_source_and_primary_death_in_shared_loop(self):
        tower = super_wizard_instance()
        tower["super_wizard_parameters"]["fanout"]["delay_seconds"] = 0.5
        result = self.simulate(
            [
                tower,
                fixed_tank("primary", x=9.5, y=5.5),
                fixed_tank("near", x=11, y=5.5),
            ],
            effects=[
                {
                    "id": "kill-source-and-primary",
                    "kind": "damage",
                    "time_seconds": 0.2,
                    "targets": ["super-wizard", "primary"],
                    "amount": 1000000,
                }
            ],
            duration_seconds=0.6,
        )
        self.assertEqual(result["actors"]["super-wizard"]["hp"], 0)
        self.assertEqual(result["actors"]["primary"]["hp"], 0)
        impacts = events(result, "projectile_impact")
        self.assertEqual([event["target"] for event in impacts], ["primary", "near"])
        self.assertEqual(impacts[-1]["time_seconds"], 0.5)
        self.assertAlmostEqual(impacts[-1]["damage"], 150.8)

    def test_profile_and_runtime_rage_scale_each_fanout_packet_once(self):
        rage = spell_tower_instance(x=6, y=8)
        rage["spell_tower_parameters"]["cast"]["delay_seconds"] = 0
        attackers = [
            fixed_tank("primary", x=9.5, y=5.5),
            fixed_tank("near", x=11, y=5.5),
        ]
        for attacker in attackers:
            attacker["modifiers"]["range_multiplier"] = 1
        scene = compile_entity_scene(
            advanced_sector(
                self.catalog,
                [super_wizard_instance(first_attack_seconds=0.1), rage, *attackers],
                effects=[
                    {
                        "id": "hold-targets",
                        "kind": "freeze",
                        "time_seconds": 0,
                        "targets": ["primary", "near"],
                        "duration_seconds": 1,
                    }
                ],
                duration_seconds=0.2,
            ),
            self.catalog,
        )["scene"]
        scene = apply_battle_modifiers(
            scene, modifier_policy("legend_i"), self.catalog, self.mode_rules
        )["scene"]
        result = simulate_spatial(scene)
        impacts = events(result, "projectile_impact")
        self.assertEqual([event["target"] for event in impacts], ["primary", "near"])
        self.assertAlmostEqual(impacts[0]["damage"], 377 * 1.2 * 1.6)
        self.assertAlmostEqual(impacts[1]["damage"], 150.8 * 1.2 * 1.6)

    def test_giga_aggregate_contact_and_motion_are_solver_step_independent(self):
        observations = []
        for step in (0.017, 0.8):
            moving = fixed_tank("air", entity="minion", x=3, y=10)
            moving["modifiers"].update(range_multiplier=0.01, hitpoints_multiplier=100)
            result = self.simulate(
                [
                    building("storage", 20, y=9),
                    fixed_tank("ground", x=12, y=10),
                    moving,
                ],
                traps=[giga_instance({"ground": response(8), "air": response(10)})],
                duration_seconds=2,
                maximum_step_seconds=step,
            )
            trigger = events(result, "giga_bomb_trigger")[0]
            observations.append(
                (
                    round(trigger["time_seconds"], 8),
                    trigger["aggregate_trigger_weight"],
                    round(result["actors"]["air"]["x"], 6),
                    result["actors"]["air"]["hp"],
                )
            )
        self.assertEqual(observations[0], observations[1])
        self.assertAlmostEqual(observations[0][0], 3.5 / 4, places=8)
        self.assertEqual(observations[0][1], 18)

    def test_giga_requires_generated_pet_response_and_uses_phoenix_interception(self):
        trap = giga_instance({"hero": response()}, x=2, y=3)
        specification = advanced_sector(
            self.catalog,
            [paired_hero(), building("storage", 9, y=3)],
            pets=[pet_instance("phoenix")],
            traps=[trap],
            duration_seconds=0.1,
        )
        with self.assertRaisesRegex(InputError, "missing=\\['pet'\\]"):
            compile_entity_scene(specification, self.catalog)
        trap["parameters"]["unit_responses"]["pet"] = response(0)
        scene = compile_entity_scene(specification, self.catalog)["scene"]
        scene["actors"][0]["hitpoints"] = 1
        result = simulate_spatial(scene)
        self.assertEqual(len(events(result, "phoenix_hatched")), 1)
        self.assertEqual(result["actors"]["hero"]["hp"], 1)
        self.assertIsNone(result["actors"]["hero"]["death_time"])

    def test_closed_loop_accepts_advanced_scope_and_delays_shared_burst_clock(self):
        scene = compile_entity_scene(
            advanced_sector(
                self.catalog,
                [multi_gear_instance(), fixed_tank("attacker", x=9.5, y=5.5)],
                duration_seconds=0.6,
            ),
            self.catalog,
        )["scene"]
        plan = synthetic_plan()
        step = plan["streams"][0]["steps"][0]
        step["all_conditions"] = [
            {
                "field": "time_seconds",
                "operator": "at_least",
                "value": 0.25,
            }
        ]
        step["action"].update(targets=["multi-gear"], duration_seconds=0.2)
        sample = one_trial(scene, plan, synthetic_profile(latency=0))
        launches = events(sample["combat"], "projectile_launch")
        self.assertEqual(
            [round(event["time_seconds"], 6) for event in launches], [0, 0.192, 0.584]
        )

    def full_battle(self):
        specification, account, army, layout = full_battle_fixture(self.catalog)
        account["town_hall"] = 18
        layout.update(town_hall=18, width=65, height=24)
        guardian = guardian_instance("smasher")
        hall = guardian_hall(guardian)
        attackers = [
            actor
            for actor in specification["entity_scene"]["entities"]
            if actor["team"] == "attack"
        ]
        for actor in attackers:
            actor["town_hall"] = 18
        multi = multi_gear_instance(town_hall=18)
        wizard = super_wizard_instance(x=12, y=3)
        trap = giga_instance(
            {actor["id"]: response(25) for actor in attackers}, town_hall=18, y=6
        )
        scene = advanced_sector(
            self.catalog,
            [hall, guardian, multi, wizard, *attackers],
            traps=[trap],
            duration_seconds=0.1,
            defending_unit_responses={
                "source": "explicit-advanced-defenses-fixture-response-policy",
                "actors": {
                    actor["id"]: {"primary": "ignore", "collateral": "ignore"}
                    for actor in attackers
                },
            },
        )
        specification.update(entity_scene=scene, time_limit_seconds=0.1)
        layout["statistics_policy"] = deepcopy(scene["statistics_policy"])
        layout["buildings"] = [
            {
                "instance": item["id"],
                "id": item["entity"],
                "level": item["level"],
                "x": item["x"],
                "y": item["y"],
                "counts_for_destruction": item.get("counts_for_destruction", False),
                **({"mode": item["mode"]} if "mode" in item else {}),
            }
            for item in (hall, multi, wizard, trap)
        ]
        layout["buildings"][0]["settings"] = {
            "guardian": {
                "actor_id": "guardian",
                "entity": "smasher",
                "level": 1,
            }
        }
        layout["inventory"] = {
            item["entity"]: 1 for item in (hall, multi, wizard, trap)
        }
        return specification, account, army, layout

    def test_full_battle_binds_modes_and_uncounted_visible_giga(self):
        specification, account, army, layout = self.full_battle()
        compiled = compile_full_battle(
            specification, account, army, layout, self.catalog
        )
        self.assertEqual(compiled["compiled"]["scene"]["ruleset"], RULESET)
        result = simulate_full_battle(
            specification, account, army, layout, self.catalog
        )
        self.assertEqual(result["outcome"]["counted_building_count"], 3)
        for mode in (None, "normal"):
            altered = deepcopy(layout)
            multi = altered["buildings"][1]
            if mode is None:
                del multi["mode"]
            else:
                multi["mode"] = mode
            with self.assertRaises(InputError):
                compile_full_battle(specification, account, army, altered, self.catalog)

    def test_old_scope_rejects_advanced_weapons_and_giga(self):
        for entities, traps in (
            ([multi_gear_instance(), fixed_tank()], []),
            ([super_wizard_instance(), fixed_tank()], []),
            ([fixed_tank()], [giga_instance({"tank": response()})]),
        ):
            specification = indirect_sector(
                self.catalog,
                entities,
                traps=traps,
                scope=OLD_SCOPE,
                model_rules=deepcopy(OLD_RULES),
            )
            with self.assertRaisesRegex(InputError, "v26"):
                compile_entity_scene(specification, self.catalog)
