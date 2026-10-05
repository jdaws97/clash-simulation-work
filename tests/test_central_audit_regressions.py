"""Bounded independent-audit regressions; synthetic, never game calibration."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene, partial_adapter_status
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import simulate_full_battle
from clashlab.hero_roster_rules import RULES, SCOPE
from clashlab.recipe_troops import RecipeTroopCombat
from clashlab.spatial import simulate_spatial
from clashlab.troop_summons import compile_summon_model

from test_adapters import entity_instance
from test_attacking_extensions import unit, summon_parameters
from test_defense_variants import logger
from test_equipment_auras import gear
from test_domain_composition_regressions import titan_case
from test_full_battle import fixture, add_hero
from test_guardians import guardian_hall, guardian_instance, guardian_sector
from test_indirect_defenses import fixed_tank
import test_recipe_troops as recipe_fixtures
import test_siege_machines as siege_fixtures
from test_spatial import synthetic_scene, synthetic_structure


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "independent-synthetic-defense-audit-not-game-calibration"
spec = importlib.util.spec_from_file_location(
    "battle_replay_packer", ROOT / "tools/render_battle_replay.py"
)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def inferno_battle(catalog, rounds, consumption):
    inputs = fixture(catalog, time_limit=0.3)
    inputs[0]["entity_scene"].update(
        scope=SCOPE, model_rules=deepcopy(RULES), pets=[], buff_spells=[]
    )
    tower = entity_instance(
        "inferno",
        "inferno-tower",
        1,
        "defense",
        x=4,
        y=4,
        mode="multiTarget",
        statistics_mode="multiTarget",
        beam_parameters={"source": SOURCE, "cadence": "synchronized_volley_hypothesis"},
        inferno_ammunition_parameters={
            "source": SOURCE,
            "status": "explicit_uncalibrated_hypothesis",
            "initial_rounds": rounds,
            "consumption": consumption,
            "reload": "none_during_battle",
            "depleted_lock": "clear_target_no_new_launches",
        },
    )
    tower["attack_parameters"]["allocation"] = "distinct_targets_only"
    inputs[0]["entity_scene"]["entities"].append(tower)
    inputs[3]["inventory"]["inferno-tower"] = 1
    inputs[3]["buildings"].append(
        {
            "instance": "inferno",
            "id": "inferno-tower",
            "level": 1,
            "x": 4,
            "y": 4,
            "mode": "multiTarget",
            "counts_for_destruction": True,
        }
    )
    return inputs


class CentralAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_paid_titan_positive_clock_reaches_shared_solver_exactly(self):
        for step in (0.017, 0.25):
            inputs = titan_case(self.catalog, step)
            inputs[0]["entity_scene"]["entities"][1]["aura_parameters"][
                "first_pulse_delay_seconds"
            ] = 1e-12
            result = simulate_full_battle(*inputs, self.catalog)
            pulses = [
                e
                for e in result["combat"]["trace"]
                if e.get("event") == "electro_titan_aura_pulse"
            ]
            self.assertEqual(pulses[0]["time_seconds"], 1e-12)
            self.assertEqual(len(pulses), 4)

    def test_apprentice_excludes_real_siege_without_excluding_ordinary_troop(self):
        siege_fixtures.SiegeMachineTests.setUpClass()
        recipe_fixtures.RecipeTroopTests.setUpClass()
        actors, _, _, trace = siege_fixtures.SiegeMachineTests().runtime()
        helper = recipe_fixtures.RecipeTroopTests()
        apprentice = helper.troop("apprentice-warden")
        ordinary = helper.troop("headhunter")
        for actor in (apprentice, ordinary):
            actor.update(x=actors["siege"]["x"], y=actors["siege"]["y"])
            actors[actor["id"]] = actor
        siege_hp = actors["siege"]["maximum_hp"]
        troop_hp = ordinary["maximum_hp"]
        runtime = RecipeTroopCombat(actors)
        runtime.prepare(0, trace)
        self.assertEqual(actors["siege"]["maximum_hp"], siege_hp)
        self.assertEqual(actors["siege"]["hp"], siege_hp)
        self.assertGreater(ordinary["maximum_hp"], troop_hp)
        self.assertEqual(ordinary["hp"], ordinary["maximum_hp"])

    def test_raw_golem_summon_contract_cannot_silently_disappear(self):
        parent = unit("golem")
        compile_summon_model(
            parent,
            {"summon_parameters": summon_parameters("actual_death")},
            {"id": "golem"},
            {"golemitesSpawned": 2},
        )
        raw = synthetic_scene(
            [parent, synthetic_structure("tower", x=2, y=1, hitpoints=200)],
            duration_seconds=0.2,
            effects=[
                {
                    "id": "kill-parent",
                    "kind": "damage",
                    "time_seconds": 0,
                    "targets": ["golem"],
                    "amount": 1000,
                }
            ],
        )
        with self.assertRaisesRegex(
            InputError, "Unbound troop lifecycle.*troop_summon_model"
        ):
            simulate_spatial(raw)

    def test_finite_inferno_controls_actual_paid_full_battle_beams(self):
        for step in (0.017, 0.25):
            for policy, rounds, expected in (
                ("one_round_per_released_beam", 0, 0),
                ("one_round_per_released_beam", 2, 2),
                ("one_round_per_synchronized_weapon_pulse", 1, 5),
            ):
                inputs = inferno_battle(self.catalog, rounds, policy)
                inputs[0]["entity_scene"]["maximum_step_seconds"] = step
                result = simulate_full_battle(*inputs, self.catalog)
                beams = [
                    e
                    for e in result["combat"]["trace"]
                    if e.get("event") == "projectile_launch"
                    and e.get("source") == "inferno"
                ]
                self.assertEqual(len(beams), expected)
                self.assertEqual(
                    result["combat"]["combat"]["inferno_ammunition"][
                        "ammunition_remaining"
                    ],
                    {"inferno": 0},
                )
                self.assertIsNone(result["combat"]["actors"]["inferno"]["target"])
        # Omitting the optional hypothesis retains the ordinary defense.
        inputs = inferno_battle(self.catalog, 0, "one_round_per_released_beam")
        inputs[0]["entity_scene"]["entities"][-1].pop("inferno_ammunition_parameters")
        result = simulate_full_battle(*inputs, self.catalog)
        self.assertEqual(
            sum(
                e.get("event") == "projectile_launch" and e.get("source") == "inferno"
                for e in result["combat"]["trace"]
            ),
            15,
        )

    def test_logger_discovery_matches_explicit_shared_kernel_rejection(self):
        status = partial_adapter_status(self.catalog.entity("logger"), 1, mode="normal")
        self.assertFalse(status["available"])
        self.assertTrue(status["missing"])
        raw = logger(self.catalog)
        instance = guardian_instance("logger", attack_parameters={})
        instance["logger_parameters"] = raw["entity_adapter"]["logger_parameters"]
        scene = guardian_sector(
            self.catalog, [guardian_hall(instance), instance, fixed_tank()]
        )
        with self.assertRaisesRegex(InputError, "Logger shared projectile.*not bound"):
            compile_entity_scene(scene, self.catalog)

    def test_life_gem_frames_and_replay_keep_historical_hp_denominators(self):
        for owner_loss in (False, True):
            inputs = fixture(self.catalog, time_limit=0.3)
            warden = add_hero(inputs[0], inputs[2], inputs[1], "grand-warden")
            items = [gear("rage-gem"), gear("life-gem")]
            warden["hero_parameters"]["equipment"] = items
            inputs[2]["heroes"][0]["equipment"] = [
                {"id": x["entity"], "level": x["level"]} for x in items
            ]
            inputs[1]["levels"].update({x["entity"]: x["level"] for x in items})
            scene = inputs[0]["entity_scene"]
            scene["entities"][0]["town_hall_parameters"]["activation"][
                "initial_state"
            ] = "active"
            scene.update(
                scope=SCOPE,
                model_rules=deepcopy(RULES),
                pets=[],
                buff_spells=[],
                maximum_step_seconds=0.1,
                recording_interval_seconds=0.1,
                effects=[],
            )
            for actor in scene["entities"]:
                if actor["team"] == "attack":
                    actor["first_attack_seconds"] = 100
            result = simulate_full_battle(*inputs, self.catalog)
            if owner_loss:
                # A controlled kernel disturbance tests historical frames
                # after aura removal; it is not a player battle command.
                disturbed = deepcopy(result["compiled"]["scene"])
                disturbed["effects"] = [
                    {
                        "id": "owner-loss",
                        "kind": "damage",
                        "time_seconds": 0.15,
                        "targets": [warden["id"]],
                        "amount": 1000000,
                    }
                ]
                result["combat"] = simulate_spatial(disturbed)
            packed = replay.pack_case(result, "synthetic-life-gem")
            frames = packed["frames"]
            self.assertEqual(frames[0]["actors"]["pekka-0"]["maximum_hp"], 4200)
            state = frames[-1]["actors"]["pekka-0"]
            self.assertEqual(state["maximum_hp"], 3000 if owner_loss else 4200)
            self.assertLess(state["hp"] / state["maximum_hp"], 1)
            if not owner_loss:
                self.assertAlmostEqual(state["hp"], 4084.8)
                self.assertAlmostEqual(
                    state["hp"] / state["maximum_hp"], 0.9725714285714286
                )
            changes = [
                e
                for e in result["combat"]["trace"]
                if e.get("event") == "equipment_life_hp_change"
                and e["target"] == "pekka-0"
            ]
            self.assertEqual(changes[0]["maximum_hp"], 4200)
            if owner_loss:
                self.assertEqual(changes[-1]["maximum_hp"], 3000)


if __name__ == "__main__":
    unittest.main()
