"""Bounded release-family checks using shared selection, receipts and health."""

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.damage_receipts import DamageReceipts
from clashlab.equipment_weapons import (
    OWNERS,
    POLICIES,
    EquipmentWeaponCombat,
    compile_equipment,
)
from clashlab.spatial import _apply_health, _load_actors, _select_target

from test_spatial import synthetic_unit, synthetic_structure


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-equipment-release-geometry-not-replay-calibration"


def gear(entity):
    return {
        "entity": entity,
        "level": 27 if entity in {"frost-flake", "meteor-staff"} else 18,
        "parameters": {
            "source": SOURCE,
            **POLICIES,
            "release_delay_seconds": 0.1,
            "projectile_speed_tiles_per_second": 10,
            "initial_range_tiles": 20,
            "bounce_range_tiles": 20,
            "first_passive_delay_seconds": 0,
            "cone_angle_degrees": 90,
            "fallback_unit_vector": [1, 0],
        },
    }


class EquipmentWeaponFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def runtime(self, entity, extra=None):
        model = compile_equipment(
            gear(entity), {"entity": OWNERS[entity], "town_hall": 18}, self.catalog
        )[0]
        source = synthetic_unit(
            "source",
            x=2,
            y=3,
            hitpoints=1000,
            range=1,
            hero_model={
                "entity": OWNERS[entity],
                "equipment": [model],
                "damage_multiplier": 1,
            },
            buff_class="hero",
            target_priorities=["defense", "building"],
            wall_behavior={"kind": "avoid", "source": SOURCE},
        )
        structures = extra or [
            synthetic_structure(
                f"target-{index}", x=4 + index * 2, y=3, hitpoints=10000
            )
            for index in range(5)
        ]
        actors = _load_actors({"actors": [source, *structures]}, 30, 20)
        return actors, EquipmentWeaponCombat(actors, _select_target, 30, 20)

    def settle(self, runtime, actors, time, trace):
        receipts = DamageReceipts()
        damage, healing = runtime.resolve(actors, time, trace, receipts)
        attribution = receipts.settle(actors, damage, time)
        _apply_health(actors, damage, defaultdict(float, healing), time)
        return damage, attribution

    def test_locked_chain_budget_protection_and_source_loss(self):
        for entity in ("seeking-shield", "electro-fangs"):
            actors, runtime = self.runtime(entity)
            trace = []
            actors["target-0"]["immune_until"] = 100
            if entity == "electro-fangs":
                actors["source"]["target"] = "target-0"
                runtime.weapon_launched("source", 0, trace)
            else:
                runtime.activate("source", actors, 0, trace)
                runtime.activate("source", actors, 0, trace)
            actors["source"]["hp"] = 0
            self.assertEqual(len(runtime.continuation_reasons(0)), 1)
            impacts = []
            for _ in range(8):
                if not runtime.packets:
                    break
                time = runtime.packets[0][0]
                damage, receipts = self.settle(runtime, actors, time, trace)
                impacts.extend(receipts)
            self.assertEqual(len(runtime.packets), 0)
            hit_events = [
                event for event in trace if event["event"] == "equipment_weapon_impact"
            ]
            self.assertEqual(len(hit_events), 4)
            self.assertEqual(
                len({key for event in hit_events for key in event["targets"]}), 4
            )
            self.assertEqual(actors["target-0"]["hp"], 10000)
            self.assertLess(actors["target-1"]["hp"], 10000)
            self.assertTrue(
                all(receipt["source_actor_id"] == "source" for receipt in impacts)
            )

    def test_distinct_freeze_volley_and_captured_cone_radial_release(self):
        for entity in ("frost-flake", "stun-blaster", "flame-blower"):
            targets = [
                synthetic_structure("front", x=5, y=3, hitpoints=10000),
                synthetic_structure("back", x=0, y=3, hitpoints=10000),
            ]
            actors, runtime = self.runtime(entity, targets)
            trace = []
            runtime.activate("source", actors, 0, trace)
            actors["source"]["hp"] = 0
            for _ in range(8):
                if not runtime.packets:
                    break
                self.settle(runtime, actors, runtime.packets[0][0], trace)
            self.assertLess(actors["front"]["hp"], 10000)
            if entity == "flame-blower":
                self.assertEqual(actors["back"]["hp"], 10000)
            else:
                self.assertGreater(actors["front"]["frozen_until"], 0)
                self.assertGreater(actors["back"]["frozen_until"], 0)

    def test_meteor_freeze_recall_grid_and_released_packet(self):
        actors, runtime = self.runtime("meteor-staff")
        trace = []
        actors["source"]["frozen_until"] = 6
        runtime.prepare(actors, 0, trace)
        runtime.prepare(actors, 5, trace)
        runtime.prepare(actors, 6, trace)
        self.assertEqual(len(runtime.packets), 0)
        actors["source"]["_recalled"] = True
        runtime.prepare(actors, 10, trace)
        actors["source"]["_recalled"] = False
        runtime.prepare(actors, 11, trace)
        self.assertEqual(len(runtime.packets), 0)
        runtime.prepare(actors, 15, trace)
        self.assertEqual(len(runtime.packets), 1)
        actors["source"]["hp"] = 0
        self.settle(runtime, actors, runtime.packets[0][0], trace)
        self.assertLess(actors["target-0"]["hp"], 10000)
        runtime.prepare(actors, 20, trace)
        self.assertEqual(len(runtime.packets), 0)


if __name__ == "__main__":
    unittest.main()
