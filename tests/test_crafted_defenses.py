"""Representative conditional battle contracts; fixtures are not game calibration."""

from pathlib import Path
from copy import deepcopy
from collections import defaultdict
import json
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.combat import PatternCombat
from clashlab.crafted_selection import SEASON_POLICY
from clashlab.crafted_defenses import (
    SCOPE,
    CraftedDefenseCombat,
    compile_crafted_defense,
)
from clashlab.hazards import PulsedHazards
from clashlab.spatial import _load_actors, _apply_health
from test_adapters import entity_instance
from test_spatial import synthetic_structure, synthetic_unit, synthetic_scene


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-phase4-battle-contract-not-current-game-calibration"


def parameters(variant):
    names = {
        "cake-a-pult": ["Hitpoints", "Damage", "Explosion Damage"],
        "hero-hunter": ["Hitpoints", "Damage", "Poison Level"],
        "hot-candle": ["Hitpoints", "Damage", "Seconds Active"],
    }[variant]
    return {
        "source": SOURCE,
        "status": "explicit_uncalibrated_hypothesis",
        "scope": SCOPE,
        "variant": variant,
        "phase": 4,
        "availability_policy": SEASON_POLICY,
        "as_of_date": "2026-10-04",
        "rotation_policy": "explicit_phase4_selection_not_current_date_certified",
        "module_levels": {name: 1 for name in names},
        "module_statistics_policy": "pinned_catalog_crosschecked_secondary_module_rows",
        "projectile_delay_seconds": 0.1,
        "impact_position": "launch_sampled_primary_center",
        "minimum_range_policy": "launch_eligibility_only",
        "hero_selector": (
            "heroes_first_nearest_then_id"
            if variant == "hero-hunter"
            else "not_applicable"
        ),
        "candle": (
            {
                "second_decay_after_first_seconds": 10,
                "melt_clock": "battle_start_zero",
                "freeze": "melt_clock_continues_experimental",
                "launch_cap": "live_capacity_at_launch_distinct_targets",
            }
            if variant == "hot-candle"
            else None
        ),
        "poison": (
            {
                "membership": "impact_anchored_shared_hazard_experimental",
                "radius": 1,
                "pulse_interval_seconds": 0.5,
                "first_pulse_offset_seconds": 0,
                "growth_by_field_age": [{"after_seconds": 0, "dps_multiplier": 1}],
                "exit_linger_seconds": 0,
                "protection_policy": "damage_immunity_also_blocks_status",
                "excluded_classes": ["siege", "guardian"],
            }
            if variant == "hero-hunter"
            else None
        ),
    }


def loaded(raw):
    return _load_actors(synthetic_scene(raw, width=20, height=20), 20, 20)


class CraftedDefenseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        data = json.loads(
            (ROOT / "data/clashking-static-data.json").read_text(encoding="utf-8")
        )
        cls.secondary = next(
            e for e in data["buildings"] if e["name"] == "Crafting Station"
        )

    def crafted(self, variant, **changes):
        p = parameters(variant)
        p.update(changes)
        instance = entity_instance(
            "station",
            "crafting-station",
            1,
            "defense",
            town_hall=16,
            crafted_parameters=p,
        )
        actor = synthetic_structure(
            "station", x=1, y=1, entity_adapter={"entity": "crafting-station"}
        )
        return compile_crafted_defense(actor, instance, self.catalog, self.secondary)

    def test_cake_two_stage_live_splash_source_primary_death_and_continuation(self):
        actors = loaded(
            [
                self.crafted("cake-a-pult"),
                synthetic_unit("primary", x=7, y=2.5),
                synthetic_unit(
                    "air", x=8, y=2.5, layer="air", movement="air", hitpoints=1000
                ),
                synthetic_unit("entrant", x=15, y=2.5, hitpoints=300),
                synthetic_unit("friend", x=7, y=2.5, team="defense"),
            ]
        )
        runtime = CraftedDefenseCombat(actors, None)
        self.assertTrue(runtime.launch("station", 0, []))
        actors["station"].update(hp=0, death_time=0.05)
        actors["primary"].update(hp=0, death_time=0.05)
        landing = runtime.resolve(0.1, [])
        self.assertEqual(dict(landing), {"air": 195})
        _apply_health(actors, landing, defaultdict(float), 0.1)
        self.assertEqual(runtime.next_boundary(0.1), 3.1)
        self.assertEqual(runtime.continuation_reasons(0.1)[0]["source_team"], "defense")
        actors["air"]["x"] = 15
        actors["entrant"]["x"] = 7
        bomb = runtime.resolve(3.1, [])
        self.assertEqual(dict(bomb), {"entrant": 400})
        _apply_health(actors, bomb, defaultdict(float), 3.1)
        self.assertEqual(actors["entrant"]["hp"], 0)
        self.assertEqual(actors["entrant"]["death_time"], 3.1)
        self.assertFalse(runtime.launch("station", 3.1, []))
        self.assertEqual(runtime.result()["pending_count"], 0)

    def test_hunter_hero_priority_bonus_shared_poison_and_source_loss(self):
        actors = loaded(
            [
                self.crafted("hero-hunter"),
                synthetic_unit("troop", x=4, y=2.5, hazard_class="troop"),
                synthetic_unit(
                    "hero", x=8, y=2.5, healing_class="hero", hazard_class="hero"
                ),
            ]
        )
        hazards = PulsedHazards(actors, [])
        runtime = CraftedDefenseCombat(actors, hazards)
        self.assertEqual(
            [a["id"] for a in runtime.select_targets("station", 0)], ["hero"]
        )
        runtime.launch("station", 0, [])
        actors["station"].update(hp=0, death_time=0.05)
        self.assertAlmostEqual(runtime.resolve(0.1, [])["hero"], 145 * 0.6 * 2)
        self.assertEqual(len(hazards.fields), 1)
        hazards.prepare_status(actors, 0.1, [])
        self.assertAlmostEqual(actors["hero"]["_hazard_movement_multiplier"], 0.66)
        self.assertAlmostEqual(hazards.resolve(actors, 0.1, [])["hero"], 145 * 0.5)
        self.assertNotIn("troop", hazards.resolve(actors, 0.6, []))

    def test_candle_battle_start_decay_freeze_and_distinct_air_ground_targets(self):
        actors = loaded(
            [
                self.crafted("hot-candle"),
                *[
                    synthetic_unit(
                        "enemy-" + str(i),
                        x=5 + i * 0.2,
                        y=3,
                        layer="air" if i % 2 else "ground",
                        movement="air" if i % 2 else "ground",
                    )
                    for i in range(7)
                ],
            ]
        )
        runtime = CraftedDefenseCombat(actors, None)
        actors["station"]["frozen_until"] = 60
        self.assertFalse(runtime.launch("station", 58, []))
        self.assertEqual(runtime.capacity("station", 58), 6)
        self.assertEqual(runtime.next_boundary(58), 59)
        self.assertEqual(runtime.capacity("station", 59), 4)
        self.assertTrue(runtime.launch("station", 60, []))
        self.assertEqual(len(runtime.pending), 4)
        self.assertEqual(set(runtime.resolve(60.1, []).values()), {40})
        self.assertEqual(runtime.capacity("station", 69), 3)

    def test_unknown_historical_incomplete_and_unavailable_modules_fail_closed(self):
        actors = loaded([self.crafted("cake-a-pult")])
        with self.assertRaisesRegex(InputError, "dedicated Station runtime"):
            PatternCombat(actors).launch(
                actors["station"], actors["station"], actors, 0, []
            )
        with self.assertRaises(InputError):
            self.crafted("cake-a-pult", phase=3)
        with self.assertRaises(InputError):
            self.crafted("hot-candle", candle=None)
        with self.assertRaises(InputError):
            self.crafted(
                "hero-hunter",
                module_levels={"Hitpoints": 10, "Damage": 10, "Poison Level": 10},
            )
        with self.assertRaises(InputError):
            self.crafted(
                "cake-a-pult", rotation_policy="catalog_isCurrent_is_current_game"
            )
