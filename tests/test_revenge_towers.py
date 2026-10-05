"""Impactful experimental lifecycle, freeze, packet and failure checks."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.advanced_defenses import MultiGearCombat
from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError, read_json
from clashlab.spatial import _load_actors, _select_target, simulate_spatial
from clashlab.pet_rules import RULESET as PET_RULESET, RULES as PET_RULES

from test_adapters import entity_instance
from test_advanced_defense_integration import advanced_sector
from test_indirect_defenses import fixed_tank
from test_spatial import synthetic_structure


ROOT = Path(__file__).resolve().parents[1]


def tower_instance():
    parameters = read_json(ROOT / "data/battle-policies/experimental-higher-th.json")[
        "revenge_tower"
    ]
    return entity_instance(
        "revenge", "revenge-tower", 2, "defense", town_hall=18, x=2, y=4, **parameters
    )


def victims():
    return [
        synthetic_structure(
            f"victim-{i}",
            x=20 + i % 10,
            y=15 + i // 10,
            kind="building",
            minimum_range=0,
            target_priorities=[],
            target_layers=[],
            attack_model={"kind": "none", "source": "synthetic-lifecycle-test"},
        )
        for i in range(50)
    ]


class RevengeTowerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def scene(self, tower=None, others=None):
        scene = compile_entity_scene(
            advanced_sector(
                self.catalog,
                [tower or tower_instance(), *(others or [fixed_tank(x=9.5, y=5.5)])],
            ),
            self.catalog,
        )["scene"]
        scene["actors"].extend(victims())
        return scene

    def test_missing_mapping_and_nonexperimental_mode_fail_strict(self):
        for field in ("verification", "phase_modes", "hp_multipliers", "chain"):
            tower = tower_instance()
            tower["revenge_parameters"].pop(field)
            with self.subTest(field=field), self.assertRaises(InputError):
                self.scene(tower)
        tower = tower_instance()
        tower["revenge_parameters"]["verification"] = "verified"
        with self.assertRaises(InputError):
            self.scene(tower)

    def test_raw_revenge_model_cannot_bypass_older_scope(self):
        scene = self.scene()
        scene.update(ruleset=PET_RULESET, model_rules=deepcopy(PET_RULES))
        with self.assertRaisesRegex(InputError, "Advanced TH17/18 defenses"):
            simulate_spatial(scene)

    def test_thresholds_hp_fraction_freeze_clock_and_no_resurrection(self):
        actors = _load_actors(self.scene(), 40, 30)
        combat = PatternCombat(actors)
        runtime = MultiGearCombat(actors, _select_target, combat)
        tower = actors["revenge"]
        tower["hp"] /= 2
        trace = []
        for i in range(4):
            actors[f"victim-{i}"].update(hp=0, death_time=0)
        # A dead uncounted troop must not trip the building threshold.
        actors["tank"].update(hp=0, death_time=0)
        runtime.prepare(actors, 0, trace)
        self.assertTrue(runtime.revenge.dormant(tower))
        self.assertEqual(tower["damage"], 0)
        actors["victim-4"].update(hp=0, death_time=0.5)
        runtime.prepare(actors, 0.5, trace)
        self.assertEqual(tower["damage"], 500)
        self.assertAlmostEqual(tower["hp"], 6200 * 1.15 / 2)
        tower.update(frozen_until=3, next_attack=4)
        for i in range(5, 25):
            actors[f"victim-{i}"].update(hp=0, death_time=1)
        runtime.prepare(actors, 1, trace)
        self.assertAlmostEqual(tower["next_attack"], 3.5)
        self.assertEqual(tower["damage"], 250)
        self.assertEqual(combat.patterns["revenge"]["damage_multipliers"], [1, 0.6])
        for i in range(25, 50):
            actors[f"victim-{i}"].update(hp=0, death_time=2)
        runtime.prepare(actors, 2, trace)
        self.assertAlmostEqual(tower["hp"] / tower["maximum_hp"], 0.5)
        self.assertEqual(
            combat.patterns["revenge"]["damage_multipliers"], [1, 0.6, 0.36]
        )
        self.assertEqual([e["phase"] for e in trace], [1, 2, 3])
        tower.update(hp=0, death_time=2.1)
        runtime.prepare(actors, 2.1, trace)
        self.assertEqual(tower["hp"], 0)
        self.assertTrue(
            runtime.result()["revenge_towers"]["states"]["revenge"]["destroyed"]
        )

    def test_released_phase_three_chain_survives_source_death_and_step_change(self):
        outcomes = []
        for step in (0.017, 0.8):
            tower = tower_instance()
            tower["attack_parameters"]["projectile"].update(
                timing="launch_distance_delay",
                speed_tiles_per_second=10,
                delay_seconds=0,
            )
            tower["revenge_parameters"]["chain"]["jump_delay_seconds"] = 0.1
            targets = [
                fixed_tank(name, x=x, y=5.5)
                for name, x in (("primary", 9.5), ("secondary", 11), ("tertiary", 12.5))
            ]
            scene = self.scene(tower, targets)
            scene.update(duration_seconds=1.3, maximum_step_seconds=step)
            scene["effects"] = [
                {
                    "id": "threshold",
                    "kind": "damage",
                    "time_seconds": 0,
                    "targets": [v["id"] for v in victims()],
                    "amount": 1000,
                },
                {
                    "id": "hold",
                    "kind": "freeze",
                    "time_seconds": 0,
                    "targets": [t["id"] for t in targets],
                    "duration_seconds": 2,
                },
                {
                    "id": "destroy-tower",
                    "kind": "damage",
                    "time_seconds": 0.36,
                    "targets": ["revenge"],
                    "amount": 100000,
                },
            ]
            result = simulate_spatial(scene)
            impacts = [
                e
                for e in result["trace"]
                if e.get("event") == "projectile_impact"
                and e.get("source") == "revenge"
            ]
            self.assertEqual(
                [(e["target"], e["damage"]) for e in impacts],
                [("primary", 250), ("secondary", 150), ("tertiary", 90)],
            )
            self.assertEqual(result["actors"]["revenge"]["hp"], 0)
            outcomes.append(
                [(round(e["time_seconds"], 8), e["damage"]) for e in impacts]
            )
        self.assertEqual(*outcomes)
