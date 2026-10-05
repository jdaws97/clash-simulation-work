"""Five material acceptance checks; no per-field test proliferation."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.crafted_selection import selection_projection
from clashlab.deployment_mask import deployment_mask
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.higher_town_halls import synthetic_layout
from clashlab.layout_battle_bridge import bind_selected_station, assert_crafted_compiled
from clashlab.layout_evaluation import summarize_cases
from clashlab.layout_generation import ORIGIN, select_generated_station, variations
from clashlab.layout_inventory import (
    selected_inventory,
    maximum_merges,
    inspect_inventory,
)
from test_crafted_season import seasonal_battle

ROOT = Path(__file__).resolve().parents[1]


class LayoutPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.craft = read_json(
            ROOT / "data/battle-policies/layout-search-crafted-experimental.json"
        )["variants"]

    def test_seasonal_inventory_merges_and_levels_across_three_town_halls(self):
        for th, total in ((16, 468), (17, 470), (18, 546)):
            selected = selection_projection(self.craft["cake-a-pult"]["parameters"])
            merged = maximum_merges(self.catalog, th)
            inventory = selected_inventory(self.catalog, th, merged, selected)
            self.assertEqual(sum(inventory.values()), total)
            self.assertEqual(inventory["crafting-station"], 1)
            self.assertEqual(inventory.get("eagle-artillery", 0), int(th == 16))
            partial = {**merged, "ricochet-cannon": merged["ricochet-cannon"] - 1}
            remaining = selected_inventory(self.catalog, th, partial, selected)
            self.assertEqual(remaining["cannon"], inventory.get("cannon", 0) + 2)
            bad = deepcopy(selected)
            bad["module_levels"]["Damage"] = 10 if th < 18 else 11
            with self.assertRaises(InputError):
                selected_inventory(self.catalog, th, merged, bad)

    def test_deployment_holes_do_not_use_hidden_teslas_or_traps_as_territory(self):
        policy = {
            "source": "synthetic-static-mask-control",
            "state": "initial_hidden_teslas",
            "rim": "one_tile_square",
            "hero_banners_block": True,
        }
        walls = [
            {"id": "wall", "instance": f"wall-{x}-{y}", "x": x, "y": y}
            for x in range(1, 10)
            for y in range(1, 10)
            if x in {1, 9} or y in {1, 9}
        ]
        layout = {"width": 11, "height": 11, "buildings": walls}
        empty = deployment_mask(layout, self.catalog, policy)
        layout["buildings"] += [
            {"id": "hidden-tesla", "instance": "tesla", "x": 4, "y": 4},
            {"id": "bomb", "instance": "trap", "x": 6, "y": 6},
        ]
        hidden = deployment_mask(layout, self.catalog, policy)
        self.assertEqual(hidden["free_cells"], empty["free_cells"])
        self.assertIn([5, 5], hidden["wall_enclosed_free_cells"])
        self.assertTrue(hidden["isolated_components"])
        layout["buildings"] = [{"id": "cannon", "instance": "visible", "x": 4, "y": 4}]
        square = deployment_mask(layout, self.catalog, policy)
        cross = deployment_mask(
            layout, self.catalog, {**policy, "rim": "one_tile_orthogonal"}
        )
        self.assertNotIn([3, 3], square["free_cells"])
        self.assertIn([3, 3], cross["free_cells"])
        self.assertFalse(square["game_legality_proven"])

    def test_generated_variations_preserve_inventory_and_reject_manual_parents(self):
        original = synthetic_layout(self.catalog, 18)
        selected = selection_projection(self.craft["hot-candle"]["parameters"])
        with self.assertRaisesRegex(InputError, "manual/V3"):
            select_generated_station(original, self.catalog, selected)
        original["generation_origin"] = ORIGIN
        parent = select_generated_station(original, self.catalog, selected)
        before = deepcopy(parent)
        a = variations(parent, self.catalog, seed=24, limit=2)
        self.assertEqual(a, variations(parent, self.catalog, seed=24, limit=2))
        self.assertEqual(parent, before)
        self.assertEqual(len(a), 2)
        for child in a:
            report = inspect_inventory(
                child, self.catalog, child["inventory_selection"]
            )
            self.assertEqual(report["building_count"], 546)
            self.assertEqual(
                child["generation_receipt"]["change_cost"]["moved_objects"], 2
            )
        bad = deepcopy(a[0])
        bad["buildings"][0]["width"] = 99
        with self.assertRaisesRegex(InputError, "dimensions"):
            inspect_inventory(bad, self.catalog, bad["inventory_selection"])

    def test_station_hook_compiles_and_executes_all_three_paid_crafted_weapons(self):
        base = read_json(ROOT / "data/battle-policies/development-th16.json")
        for variant, policy in self.craft.items():
            inputs = seasonal_battle(self.catalog, variant)
            spec, account, army, layout = inputs
            layout["inventory_selection"] = {
                "crafted": selection_projection(policy["parameters"])
            }
            spec["entity_scene"] = bind_selected_station(
                spec["entity_scene"], layout, self.catalog, base, policy
            )
            compiled = compile_full_battle(*inputs, self.catalog)
            self.assertTrue(
                assert_crafted_compiled(compiled, layout)["active_weapon_compiled"]
            )
            result = simulate_full_battle(*inputs, self.catalog)
            self.assertEqual(
                result["combat"]["crafted_defenses"]["variants"], {"station": variant}
            )
            self.assertEqual(result["outcome"]["end_reason"], "attack_force_exhausted")
            self.assertIsNotNone(result["combat"]["actors"]["army"]["death_time"])
            bad = deepcopy(policy)
            bad["parameters"]["module_levels"]["Damage"] += 1
            with self.assertRaisesRegex(InputError, "differ"):
                bind_selected_station(
                    spec["entity_scene"], layout, self.catalog, base, bad
                )

    def test_failed_cases_never_score_and_modes_classes_and_holdouts_stay_separate(
        self,
    ):
        case = {
            "id": "a",
            "candidate_id": "layout",
            "candidate_layout_sha256": "a" * 64,
            "mode": "ranked",
            "attacker_town_hall": 17,
            "defender_town_hall": 16,
            "split": "search",
            "family": "air",
            "entry_policy": "west",
            "ability_policy": "scheduled",
        }
        cases = [
            case,
            {**case, "id": "b", "entry_policy": "east"},
            {**case, "id": "c", "mode": "cwl"},
            {**case, "id": "d", "attacker_town_hall": 18},
            {**case, "id": "e", "split": "held_out"},
        ]
        outcome = {"stars": 2, "destruction": 80, "town_hall_destroyed": True}
        receipts = [
            {
                "case": case,
                "status": "completed",
                "completion_proven": True,
                "outcome": outcome,
            },
            {"case": cases[1], "status": "timeout", "outcome": None},
        ]
        report = summarize_cases(cases, receipts)
        self.assertEqual(len(report["groups"]), 4)
        ranked = next(g for g in report["groups"] if g["completed"])
        self.assertEqual(ranked["worst_observed_case"]["case"]["id"], "a")
        self.assertIsNone(ranked["full_grid_worst_case"])
        self.assertIsNone(ranked["unweighted_grid_mean"])
        self.assertIsNone(report["best_layout"])
        receipts[1]["outcome"] = outcome
        with self.assertRaisesRegex(InputError, "cannot carry"):
            summarize_cases(cases, receipts)


if __name__ == "__main__":
    unittest.main()
