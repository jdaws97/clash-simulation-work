"""Full higher-TH inventory, resource binding, and honest unsupported inputs."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.full_battle import compile_full_battle
from clashlab.higher_town_halls import synthetic_layout, validate_higher_layout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_higher_th_example import prepare


class HigherTownHallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_complete_th_specific_inventory_and_legal_th16_resources(self):
        for th, objects, walls in ((17, 469, 325), (18, 546, 400)):
            with self.subTest(th=th):
                spec, account, army, layout, validation = prepare(th, "ranked")
                self.assertTrue(validation["merge_conservation"])
                self.assertEqual(len(layout["buildings"]), objects)
                self.assertEqual(layout["inventory"]["wall"], walls)
                self.assertEqual(layout["inventory"].get("cannon", 0), 0)
                self.assertEqual(layout["inventory"].get("eagle-artillery", 0), 0)
                self.assertEqual(layout["inventory"]["archer-tower"], 2)
                self.assertEqual(
                    layout["inventory"]["wizard-tower"], 5 if th == 17 else 2
                )
                compiled = compile_full_battle(
                    spec,
                    account,
                    army,
                    layout,
                    self.catalog,
                    read_json(ROOT / "data/mode-rules.json"),
                )
                self.assertEqual(
                    compiled["validation"]["army"]["used"]["army_housing"], 320
                )
                self.assertEqual(
                    compiled["validation"]["army"]["used"]["spell_housing"], 11
                )
                defenders = [
                    a
                    for a in spec["entity_scene"]["entities"]
                    if a["team"] == "defense"
                ]
                self.assertTrue(all(a["town_hall"] == th for a in defenders))
                hall = next(a for a in defenders if a["entity"] == "town-hall")
                self.assertEqual(hall["level"], th)
                self.assertEqual(
                    hall["mode"], "infernoArtillery" if th == 17 else "guardian"
                )
                self.assertFalse(compiled["full_game_prediction"])

    def test_missing_objects_and_consumed_merge_parent_cannot_pass(self):
        layout = synthetic_layout(self.catalog, 18)
        layout["buildings"].pop()
        with self.assertRaises(InputError):
            validate_higher_layout(layout, self.catalog)
        layout = synthetic_layout(self.catalog, 18)
        layout["inventory"]["cannon"] = 1
        with self.assertRaises(InputError):
            validate_higher_layout(layout, self.catalog)

    def test_real_inputs_preserve_coordinates_and_reject_unimplemented_choices(self):
        layout = synthetic_layout(self.catalog, 18)
        layout["higher_th_configuration"]["coordinate_provenance"] = {
            "kind": "entered_coordinates",
            "source": "synthetic-test-of-entered-route",
        }
        original = deepcopy(layout)
        spec, account, army, padded, _ = prepare(18, "cwl", layout)
        self.assertEqual(layout, original)
        for entered, output in zip(layout["buildings"], padded["buildings"]):
            self.assertEqual(
                (entered["x"] + 6, entered["y"] + 6), (output["x"], output["y"])
            )
        army["troops"][0]["count"] = 17
        with self.assertRaisesRegex(InputError, "overflow"):
            compile_full_battle(spec, account, army, padded, self.catalog)
        for selected in ("logger", "crafted_weapon", "skeleton_level_5"):
            bad = deepcopy(layout)
            if selected == "logger":
                next(b for b in bad["buildings"] if b["id"] == "town-hall")["settings"][
                    "guardian"
                ]["entity"] = "logger"
            elif selected == "crafted_weapon":
                bad["higher_th_configuration"]["crafting"] = "hero-bell"
            else:
                next(b for b in bad["buildings"] if b["id"] == "skeleton-trap")[
                    "level"
                ] = 5
            with self.subTest(selected=selected), self.assertRaises(InputError):
                s, a, r, l, _ = prepare(18, "ranked", bad)
                compile_full_battle(s, a, r, l, self.catalog)
