"""Legal levels and source-linked Freeze commands in conditional sectors."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.adapters import compile_actor, compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.spells import compile_freeze_spell


ROOT = Path(__file__).resolve().parents[1]


class FreezeSpellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def setUp(self):
        self.spell = {
            "id": "freeze-test",
            "entity": "freeze-spell",
            "level": 7,
            "town_hall": 16,
            "time_seconds": 0.25,
            "x": 8,
            "y": 5,
            "parameters": {
                "duration_multiplier": 1,
                "radius_multiplier": 1,
                "caster_team": "attack",
                "source": "explicit-synthetic-unmodified-Freeze",
            },
        }

    def test_level_seven_uses_snapshot_radius_duration_and_one_spell_space(self):
        result = compile_freeze_spell(self.spell, self.catalog)
        self.assertEqual(result["duration_seconds"], 5.5)
        self.assertEqual(result["area"]["radius"], 3.5)
        self.assertEqual(result["entity_adapter"]["housing_space"], 1)
        self.assertEqual(
            result["entity_adapter"]["snapshot_verification"], "unverified_snapshot"
        )

    def test_level_eight_requires_th18_and_unresolved_modifiers_must_be_explicit(self):
        self.spell["level"] = 8
        with self.assertRaisesRegex(InputError, "unavailable"):
            compile_freeze_spell(self.spell, self.catalog)
        self.spell["town_hall"] = 18
        self.assertEqual(
            compile_freeze_spell(self.spell, self.catalog)["duration_seconds"], 6
        )
        del self.spell["parameters"]["duration_multiplier"]
        with self.assertRaisesRegex(InputError, "explicit"):
            compile_freeze_spell(self.spell, self.catalog)

    def test_freeze_is_a_command_and_cannot_be_compiled_as_a_normal_actor(self):
        with self.assertRaisesRegex(InputError, "command list"):
            compile_actor(self.spell, self.catalog, 8)

    def test_entity_scene_accepts_command_list_and_rejects_null_list(self):
        scene = read_json(ROOT / "examples/entity-wall-sector-conditional.json")
        scene["freeze_spells"] = [deepcopy(self.spell)]
        compiled = compile_entity_scene(scene, self.catalog)
        self.assertEqual(compiled["scene"]["effects"][-1]["kind"], "area_freeze")
        scene["freeze_spells"] = None
        with self.assertRaisesRegex(InputError, "explicit list"):
            compile_entity_scene(scene, self.catalog)


if __name__ == "__main__":
    unittest.main()
