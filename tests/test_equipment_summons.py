"""Finite children checks through ordinary compilation and runtime actor loading."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json, write_json
from clashlab.equipment_summons import (
    OWNERS,
    POLICIES,
    EquipmentSummonCombat,
    compile_equipment,
    compile_reserves,
    validate_independent_deployment,
)
from clashlab.spatial import _load_actors
from test_adapters import entity_instance
from test_spatial import synthetic_unit

SOURCE = "synthetic-explicit-child-mapping-not-game-calibration"
ROOT = Path(__file__).resolve().parents[1]


class EquipmentSummonFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def model(self, entity):
        child_entity = "archer" if entity == "archer-puppet" else "barbarian"
        child = entity_instance(
            "prototype",
            child_entity,
            1,
            "attack",
            town_hall=18,
            wall_parameters={"kind": "avoid", "source": SOURCE},
        )
        count = self.catalog.level(entity, 1)["stats"][
            "summonedArchers" if entity == "archer-puppet" else "summonedBarbarians"
        ]
        parameters = {
            "source": SOURCE,
            **POLICIES,
            "child_statistics_status": "explicit_uncalibrated_hypothesis",
            "child_contract": {
                "kind": "ordinary_catalog_instance",
                "level": 1,
                "source": SOURCE,
                "actor_or_instance": child,
            },
            "spawn_offsets": [{"dx": 0, "dy": 0} for _ in range(count)],
            "first_attack_delay_seconds": 0.2,
            "damage_per_snake": 100,
            "self_heal_interval_seconds": 1,
            "first_self_heal_delay_seconds": 1,
        }
        return compile_equipment(
            {"entity": entity, "level": 1, "parameters": parameters},
            {"entity": OWNERS[entity], "town_hall": 18},
            self.catalog,
            8,
        )[0]

    def runtime(self, models):
        hero = synthetic_unit(
            "hero",
            x=2.5,
            y=2.5,
            hitpoints=1000,
            hero_model={"entity": "barbarian-king", "equipment": models},
        )
        reserves = compile_reserves(hero)
        actors = _load_actors({"actors": [hero, *reserves]}, 20, 20)
        return actors, EquipmentSummonCombat(actors, 20, 20)

    def test_ordinary_children_release_once_and_survive_owner_loss(self):
        for entity in ("archer-puppet", "barbarian-puppet"):
            model = self.model(entity)
            actors, runtime = self.runtime([model])
            trace = []
            runtime.activate("hero", actors, 0, trace)
            self.assertFalse(runtime.used)
            runtime.prepare(actors, 0, trace)
            self.assertEqual(len(runtime.used), model["count"])
            first = actors[sorted(runtime.used)[0]]
            self.assertEqual(first["next_attack"], 0.2)
            self.assertEqual(first["buff_class"], "troop")
            actors["hero"]["hp"] = 0
            runtime.prepare(actors, 20, trace)
            self.assertGreater(first["hp"], 0)
            if entity == "barbarian-puppet":
                self.assertEqual(first["_equipment_child_damage_multiplier"], 1)
            actors["hero"]["hp"] = 1000
            runtime.activate("hero", actors, 21, trace)
            runtime.prepare(actors, 21, trace)
            self.assertEqual(
                sum(row["event"] == "equipment_summon_release" for row in trace), 1
            )
            with self.assertRaises(InputError):
                validate_independent_deployment(
                    {"kind": "deploy", "targets": [first["id"]]}, actors
                )

    def test_snake_uses_unique_actual_nonlethal_receipts_and_finite_budget(self):
        model = self.model("barbarian-puppet")
        model.update(
            entity="snake-bracelet",
            ability_type="Passive",
            count=2,
            child_rage_seconds=0,
            owner_attack_rate=1.1,
        )
        model["parameters"]["spawn_offsets"] = [{"dx": 0, "dy": 0}] * 2
        actors, runtime = self.runtime([model])
        trace = []
        runtime.prepare(actors, 0, trace)
        receipt = {
            "target_id": "hero",
            "time_seconds": 1,
            "sequence": 1,
            "actual_health_loss": 150,
        }
        runtime.after_health(actors, [receipt, receipt], 1, trace)
        self.assertEqual(len(runtime.used), 1)
        runtime.after_health(actors, [{**receipt, "sequence": 2}], 1, trace)
        self.assertEqual(len(runtime.used), 2)
        actors["hero"]["hp"] = 0
        runtime.after_health(actors, [{**receipt, "sequence": 3}], 2, trace)
        self.assertEqual(len(runtime.used), 2)

    def test_unknown_equipment_lavaloon_fails_explicitly(self):
        with self.assertRaisesRegex(InputError, "seasonal LavaLoon cannot substitute"):
            compile_equipment(
                {"entity": "lavaloon-puppet", "level": 1, "parameters": {}},
                {"entity": "grand-warden", "town_hall": 18},
                self.catalog,
                8,
            )

    def test_result_json_roundtrip_preserves_finite_owner_inventory(self):
        heroes = [
            synthetic_unit(
                owner_id,
                x=2.5,
                y=2.5,
                hitpoints=1000,
                hero_model={
                    "entity": OWNERS[entity],
                    "equipment": [self.model(entity)],
                },
            )
            for owner_id, entity in (
                ("queen:alpha", "archer-puppet"),
                ("king:beta", "barbarian-puppet"),
            )
        ]
        reserves = [child for hero in heroes for child in compile_reserves(hero)]
        actors = _load_actors({"actors": [*heroes, *reserves]}, 20, 20)
        runtime = EquipmentSummonCombat(actors, 20, 20)
        original = deepcopy(runtime.children)
        trace = []
        runtime.activate("queen:alpha", actors, 0, trace)
        runtime.prepare(actors, 0, trace)
        first_child = runtime.children[("queen:alpha", "archer-puppet")][0]
        actors[first_child]["hp"] = 0
        actors["queen:alpha"]["hp"] = 0
        actors["king:beta"]["_recalled"] = True
        runtime.prepare(actors, 1, trace)
        exported = {"hero_roster": {"equipment_summons": runtime.result()}}
        with TemporaryDirectory(prefix="equipment-inventory-json-") as directory:
            path = Path(directory) / "battle-result.json"
            write_json(path, exported)
            self.assertEqual(read_json(path), exported)
        result = exported["hero_roster"]["equipment_summons"]
        self.assertEqual(
            result["finite_inventory_schema"], "owner_equipment_records_v1"
        )
        self.assertEqual(
            [
                (row["owner_id"], row["equipment_id"])
                for row in result["finite_inventory"]
            ],
            sorted(original),
        )
        released = []
        for row in result["finite_inventory"]:
            key = row["owner_id"], row["equipment_id"]
            self.assertEqual(row["child_ids"], original[key])
            self.assertFalse(
                set(row["released_child_ids"]) & set(row["remaining_child_ids"])
            )
            self.assertEqual(
                set(row["released_child_ids"]) | set(row["remaining_child_ids"]),
                set(original[key]),
            )
            released.extend(row["released_child_ids"])
        self.assertEqual(sorted(released), result["released_children"])
        self.assertIn(first_child, released)
        result["finite_inventory"][0]["child_ids"].clear()
        self.assertEqual(runtime.children, original)
