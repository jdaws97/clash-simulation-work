"""Explicit season access and independent module limits, not October certification."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.adapters import compile_actor
from clashlab.common import InputError
from clashlab.crafted_selection import (
    SEASON_POLICY,
    SEASON_SOURCE,
    selection_projection,
)
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.geometry import validate_layout
from clashlab.spatial import simulate_spatial
from test_crafted_integration import crafted_battle
from test_townhalls import hall


def seasonal_battle(catalog, variant, step=0.25):
    inputs = crafted_battle(catalog, variant, step=step)
    scene, layout = inputs[0]["entity_scene"], inputs[3]
    scene["entities"] = [
        hall(level=16, town_hall=16, x=40, y=20),
        *scene["entities"][2:],
    ]
    scene["entities"][1]["town_hall"] = 16
    layout["town_hall"] = 16
    layout["buildings"][0].update(level=16, mode="gigaInferno")
    layout["buildings"][0].pop("settings")
    return inputs


class CraftedSeasonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")

    def test_paid_th16_selected_station_has_one_footprint_released_work_and_actual_outcome(
        self,
    ):
        for variant in ("cake-a-pult", "hero-hunter", "hot-candle"):
            for step in (0.017, 0.25):
                inputs = seasonal_battle(self.catalog, variant, step)
                result = simulate_full_battle(*inputs, self.catalog)
                combat = result["combat"]
                self.assertEqual(combat["actors"]["station"]["death_time"], 0)
                self.assertAlmostEqual(combat["actors"]["army"]["death_time"], 0.1)
                self.assertEqual(
                    result["outcome"]["end_reason"], "attack_force_exhausted"
                )
                self.assertEqual(result["outcome"]["counted_building_count"], 2)
                self.assertEqual(
                    result["outcome"]["destroyed_instance_ids"], ["station"]
                )
                self.assertEqual(
                    result["resource_use"]["deployed_attacker_ids"], ["army"]
                )
                self.assertEqual(
                    combat["crafted_defenses"]["variants"], {"station": variant}
                )
                availability = combat["crafted_defenses"]["availability"]["station"]
                self.assertEqual(availability["source"], SEASON_SOURCE)
                self.assertEqual(availability["selected_town_hall"], 16)
                self.assertFalse(availability["current_date_rotation_verified"])
                geometry = validate_layout(inputs[3], self.catalog)
                self.assertEqual(
                    geometry["occupied_tiles"], 25
                )  # 4x4 Hall + 3x3 Station.
                self.assertEqual(set(geometry["seasonal_stations"]), {"station"})

    def test_all_th11_to_18_share_geometry_gate_but_module_levels_remain_independent(
        self,
    ):
        inputs = seasonal_battle(self.catalog, "cake-a-pult")
        layout = inputs[3]
        station = inputs[0]["entity_scene"]["entities"][1]
        for town_hall in range(11, 19):
            layout["town_hall"] = layout["buildings"][0]["level"] = town_hall
            layout["buildings"][0]["mode"] = "passive"
            selected = layout["buildings"][1]["settings"]["crafted"]
            maximum = town_hall - 10 if town_hall < 18 else 10
            selected["module_levels"] = {
                "Hitpoints": maximum,
                "Damage": 1,
                "Explosion Damage": maximum,
            }
            geometry = validate_layout(layout, self.catalog)
            self.assertEqual(geometry["building_count"], 2)
            self.assertEqual(geometry["occupied_tiles"], 25)
            station["town_hall"] = town_hall
            station["crafted_parameters"]["module_levels"] = deepcopy(
                selected["module_levels"]
            )
            actor = compile_actor(station, self.catalog, 8, allow_hero_extensions=True)
            self.assertEqual(
                actor["crafted_defense_model"]["availability"]["selected_town_hall"],
                town_hall,
            )
            if town_hall < 18:
                selected["module_levels"]["Damage"] = maximum + 1
                with self.assertRaisesRegex(InputError, "module is unavailable"):
                    validate_layout(layout, self.catalog)
        self.assertFalse(self.catalog.available("crafting-station", 1, 16))
        self.assertTrue(self.catalog.available("crafting-station", 1, 18))

    def test_season_selection_cannot_bypass_inventory_source_level_mode_or_raw_contract(
        self,
    ):
        inputs = seasonal_battle(self.catalog, "cake-a-pult")
        layout = inputs[3]
        station = inputs[0]["entity_scene"]["entities"][1]
        raw = compile_full_battle(*inputs, self.catalog)["compiled"]["scene"]
        compiled = next(a for a in raw["actors"] if a["id"] == "station")
        compiled["entity_adapter"]["town_hall"] = 18
        with self.assertRaisesRegex(InputError, "availability differs"):
            simulate_spatial(raw)
        bad = deepcopy(layout)
        extra = deepcopy(bad["buildings"][1])
        extra.update(instance="second-station", x=12)
        bad["buildings"].append(extra)
        bad["inventory"]["crafting-station"] = 2
        with self.assertRaisesRegex(InputError, "inventory limit"):
            validate_layout(bad, self.catalog)
        for changes in (
            {"availability_policy": "all_seasons_all_levels"},
            {"phase": 3},
            {"as_of_date": "2026-07-31"},
            {"module_levels": {"Hitpoints": 1, "Damage": 7, "Explosion Damage": 1}},
        ):
            bad = deepcopy(inputs)
            selected = bad[0]["entity_scene"]["entities"][1]["crafted_parameters"]
            selected.update(changes)
            bad[3]["buildings"][1]["settings"]["crafted"] = selection_projection(
                selected
            )
            with self.assertRaises(InputError):
                compile_full_battle(*bad, self.catalog)
        for mode in ("passive", "invented"):
            bad = deepcopy(layout)
            bad["buildings"][1]["mode"] = mode
            with self.assertRaises(InputError):
                validate_layout(bad, self.catalog)
        bad = deepcopy(layout)
        bad["town_hall"] = bad["buildings"][0]["level"] = 10
        bad["buildings"][0]["mode"] = "passive"
        with self.assertRaises(InputError):
            validate_layout(bad, self.catalog)
        station["crafted_parameters"].pop("availability_policy")
        layout["buildings"][1]["settings"]["crafted"].pop("availability_policy")
        with self.assertRaisesRegex(InputError, "TH11\\+ availability"):
            compile_full_battle(*inputs, self.catalog)
        legacy = crafted_battle(self.catalog, "cake-a-pult")
        legacy[0]["entity_scene"]["entities"][2]["crafted_parameters"].pop(
            "availability_policy"
        )
        legacy[3]["buildings"][1]["settings"]["crafted"].pop("availability_policy")
        simulate_full_battle(*legacy, self.catalog)


if __name__ == "__main__":
    unittest.main()
