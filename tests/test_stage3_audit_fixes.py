"""Shared health, scope and initial-state regressions; synthetic contracts only."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.advanced_defense_rules import (
    RULES as DEFENSE_RULES,
    SCOPE as DEFENSE_SCOPE,
)
from clashlab.attack_spell_rules import RULES as SPELL_RULES, SCOPE as SPELL_SCOPE
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.engine_rules import RULES as OLD_RULES, SCOPE as OLD_SCOPE
from clashlab.full_battle import simulate_full_battle
from clashlab.hero_roster_rules import RULES, SCOPE
from clashlab.spatial import _apply_health, _load_actors, simulate_spatial

from test_artillery import artillery_hall
from test_battle_termination import termination_policy
from test_central_audit_regressions import inferno_battle
from test_domain_composition_regressions import titan_case
from test_equipment_pet_lifecycles import gear as owner_gear
from test_equipment_weapons import gear as weapon_gear
from test_full_battle import fixture, add_hero
from test_heroes import ability
from test_spell_towers import spell_tower_instance
from test_spatial import synthetic_unit, synthetic_structure


ROOT = Path(__file__).resolve().parents[1]


def quake_instance(delay, town_hall=17):
    tower = spell_tower_instance("earthquake", level=4, town_hall=town_hall)
    parameters = tower["spell_tower_parameters"]
    parameters["effect"] = {
        "radius_multiplier": 1,
        "duration_multiplier": 1,
        "membership_policy": "one_pulse_at_released_payload_arrival",
        "status": "experimental_not_replay_calibrated",
        "statistic_basis": "snapshot_troopDamagePercent_of_current_maximum_hp",
        "damage_fraction_multiplier": 1,
        "stacking_policy": "independent_additive_single_pulses",
    }
    parameters["recipients"].update(
        target_kinds=["unit"], target_layers=["ground", "air"]
    )
    parameters["cast"].update(delay_seconds=0, impact_delay_seconds=delay)
    parameters["death"]["policy"] = "none"
    return tower


def shield_battle(catalog, step, initial="active", cast_time=0):
    inputs = fixture(catalog, time_limit=1.5)
    scene = inputs[0]["entity_scene"]
    owner = add_hero(inputs[0], inputs[2], inputs[1])
    shield = weapon_gear("seeking-shield")
    shield["parameters"]["release_delay_seconds"] = 0.5
    items = [shield, owner_gear("haste-vial")]
    owner["hero_parameters"]["equipment"] = items
    owner["modifiers"]["hitpoints_multiplier"] = 0.01
    inputs[2]["heroes"][0]["equipment"] = [
        {"id": item["entity"], "level": item["level"]} for item in items
    ]
    inputs[1]["levels"].update({item["entity"]: item["level"] for item in items})
    scene["entities"][0]["town_hall_parameters"]["activation"][
        "initial_state"
    ] = initial
    for actor in scene["entities"]:
        if actor["team"] == "attack":
            actor["first_attack_seconds"] = 100
            if actor["entity"] != "royal-champion":
                actor.update(x=0.5, y=0.5)
    scene.update(
        scope=SCOPE,
        model_rules=deepcopy(RULES),
        pets=[],
        buff_spells=[],
        maximum_step_seconds=step,
        effects=[ability(owner["id"], cast_time)],
    )
    return inputs


class Stage3AuditFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_sparse_health_defaults_only_known_omitted_recipients(self):
        actors = _load_actors(
            {"actors": [synthetic_unit(), synthetic_structure()]}, 9, 7
        )
        ids = list(actors)
        before = {key: value["hp"] for key, value in actors.items()}
        _apply_health(actors, {ids[0]: 3}, {}, 0)
        self.assertEqual(actors[ids[0]]["hp"], before[ids[0]] - 3)
        self.assertEqual(actors[ids[1]]["hp"], before[ids[1]])
        _apply_health(actors, {}, {ids[0]: 1}, 0)
        self.assertEqual(actors[ids[0]]["hp"], before[ids[0]] - 2)
        for damage, healing in (
            ({"unknown": 0}, {}),
            ({}, {"unknown": 1}),
            ({ids[0]: -1}, {}),
            ({}, {ids[0]: float("nan")}),
        ):
            saved = deepcopy(actors)
            with self.assertRaises(InputError):
                _apply_health(actors, damage, healing, 0)
            self.assertEqual(actors, saved)

    def test_paid_quake_live_source_and_unaffected_hall(self):
        for step in (0.017, 0.25):
            inputs = fixture(self.catalog, town_hall=17, time_limit=0.5)
            inputs[0]["termination_policy"] = termination_policy()
            specimen = titan_case(self.catalog, step)[0]["entity_scene"]["entities"][1]
            specimen["town_hall"] = 17
            scene = inputs[0]["entity_scene"]
            scene.update(
                scope=SPELL_SCOPE,
                model_rules=deepcopy(SPELL_RULES),
                buff_spells=[],
                pets=[],
                attack_spells=[],
                maximum_step_seconds=step,
                entities=[
                    artillery_hall(x=10, y=4, first_attack_seconds=100),
                    specimen,
                    quake_instance(0.25),
                ],
            )
            inputs[1]["levels"]["electro-titan"] = 4
            inputs[2]["troops"] = [{"id": "electro-titan", "level": 4, "count": 1}]
            inputs[3]["buildings"][0]["mode"] = "infernoArtillery"
            inputs[3]["inventory"]["spell-tower"] = 1
            inputs[3]["buildings"].append(
                {
                    "instance": "spell-tower",
                    "id": "spell-tower",
                    "level": 4,
                    "x": 6,
                    "y": 4,
                    "mode": "earthquake",
                    "counts_for_destruction": True,
                }
            )
            result = simulate_full_battle(*inputs, self.catalog)
            combat = result["combat"]
            quakes = [
                e
                for e in combat["trace"]
                if e.get("event") == "spell_tower_quake_impact"
            ]
            self.assertEqual([e["time_seconds"] for e in quakes], [0.25])
            self.assertGreater(combat["actors"]["spell-tower"]["hp"], 0)
            self.assertGreater(combat["actors"]["hall"]["hp"], 0)
            self.assertEqual(combat["actors"]["titan"]["hp"], 60900)
            self.assertEqual(result["resource_use"]["deployed_attacker_ids"], ["titan"])

    def test_quake_titan_strict_positive_order_and_lethal_suppression(self):
        for step in (0.017, 0.25):
            for titan_delay, quake_delay, lethal in (
                (1e-12, 2e-12, False),
                (2e-12, 1e-12, False),
                (1e-12, 1e-12, False),
                (1e-12, 1e-12, True),
            ):
                scene = titan_case(self.catalog, step)[0]["entity_scene"]
                scene["duration_seconds"] = 0.01
                scene["entities"][1]["aura_parameters"][
                    "first_pulse_delay_seconds"
                ] = titan_delay
                scene["entities"].append(quake_instance(quake_delay))
                compiled = compile_entity_scene(scene, self.catalog)["scene"]
                if lethal:
                    titan = next(a for a in compiled["actors"] if a["id"] == "titan")
                    compiled["effects"] = [
                        {
                            "id": "prior-injury",
                            "kind": "damage",
                            "time_seconds": 0,
                            "targets": ["titan"],
                            "amount": titan["hitpoints"] * 0.8,
                        }
                    ]
                result = simulate_spatial(compiled)
                events = [
                    e
                    for e in result["trace"]
                    if e.get("event")
                    in {"electro_titan_aura_pulse", "spell_tower_quake_impact"}
                ]
                quakes = [
                    e for e in events if e.get("event") == "spell_tower_quake_impact"
                ]
                pulses = [
                    e for e in events if e.get("event") == "electro_titan_aura_pulse"
                ]
                self.assertEqual([e["time_seconds"] for e in quakes], [quake_delay])
                self.assertEqual(
                    [e["time_seconds"] for e in pulses], [] if lethal else [titan_delay]
                )
                times = [e["time_seconds"] for e in events]
                self.assertEqual(times, sorted(times))
                if lethal:
                    self.assertEqual(result["actors"]["titan"]["hp"], 0)

    def test_inferno_raw_scope_guard_and_valid_controls(self):
        inputs = inferno_battle(self.catalog, 0, "one_round_per_released_beam")
        scene = inputs[0]["entity_scene"]
        scene.update(scope=DEFENSE_SCOPE, model_rules=deepcopy(DEFENSE_RULES))
        compiled = compile_entity_scene(scene, self.catalog)["scene"]
        control = simulate_spatial(compiled)
        self.assertEqual(
            control["combat"]["inferno_ammunition"]["ammunition_remaining"],
            {"inferno": 0},
        )
        model = next(a for a in compiled["actors"] if a["id"] == "inferno")[
            "inferno_ammunition_model"
        ]
        scene["entities"][-1].pop("inferno_ammunition_parameters")
        scene.update(scope=OLD_SCOPE, model_rules=deepcopy(OLD_RULES))
        scene.pop("pets")
        scene.pop("buff_spells")
        ordinary = compile_entity_scene(scene, self.catalog)["scene"]
        result = simulate_spatial(ordinary)
        self.assertEqual(
            sum(
                e.get("event") == "projectile_launch" and e.get("source") == "inferno"
                for e in result["trace"]
            ),
            15,
        )
        next(a for a in ordinary["actors"] if a["id"] == "inferno")[
            "inferno_ammunition_model"
        ] = model
        with self.assertRaisesRegex(InputError, "explicit v26 ruleset"):
            simulate_spatial(ordinary)

    def test_initial_active_hall_precedes_shield_selection_and_source_loss(self):
        for step in (0.017, 0.25):
            for cast_time in (0, 0.01):
                result = simulate_full_battle(
                    *shield_battle(self.catalog, step, cast_time=cast_time),
                    self.catalog,
                )
                combat = result["combat"]
                activation = next(
                    e
                    for e in combat["trace"]
                    if e.get("event") == "town_hall_activation"
                )
                impacts = [
                    e
                    for e in combat["trace"]
                    if e.get("event") == "equipment_weapon_impact"
                ]
                self.assertEqual(activation["time_seconds"], 0)
                self.assertEqual(len(impacts), 1)
                self.assertLess(
                    combat["actors"]["royal"]["death_time"], impacts[0]["time_seconds"]
                )
                self.assertEqual(combat["actors"]["hall"]["hp"], 7500)

    def test_dormant_hall_is_not_activated_by_shield_selection(self):
        result = simulate_full_battle(
            *shield_battle(self.catalog, 0.25, initial="dormant"), self.catalog
        )
        self.assertFalse(
            any(
                e.get("event") in {"equipment_weapon_impact", "town_hall_activation"}
                for e in result["combat"]["trace"]
            )
        )
        self.assertEqual(result["combat"]["actors"]["hall"]["hp"], 10000)


if __name__ == "__main__":
    unittest.main()
