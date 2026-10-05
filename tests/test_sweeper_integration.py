"""Finite gust movement interacts with the shared event scheduler."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle
from clashlab.spatial import simulate_spatial
from clashlab.sweeper_rules import RULES, SCOPE

from test_adapters import entity_instance
from test_buffs import buff_instance
from test_indirect_defenses import indirect_sector
from test_full_battle import fixture as battle_fixture
from test_sweepers import sweeper_instance


ROOT = Path(__file__).resolve().parents[1]


class SweeperIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def fixture(self, step=0.5):
        flyer = entity_instance(
            "flyer",
            "minion",
            12,
            "attack",
            x=8,
            y=5,
            first_attack_seconds=100,
        )
        # Hold ordinary movement in range, isolating the forced trajectory.
        flyer["modifiers"]["range_multiplier"] = 100
        return indirect_sector(
            self.catalog,
            [sweeper_instance(), flyer],
            scope=SCOPE,
            model_rules=deepcopy(RULES),
            duration_seconds=3,
            maximum_step_seconds=step,
            recording_interval_seconds=0.25,
        )

    def run_scene(self, specification):
        return simulate_spatial(
            compile_entity_scene(specification, self.catalog)["scene"]
        )

    def test_gust_moves_over_time_and_preserves_unfinished_attack_work(self):
        result = self.run_scene(self.fixture())
        frames = {
            round(frame["time_seconds"], 6): frame["actors"]
            for frame in result["frames"]
        }
        self.assertAlmostEqual(frames[1]["flyer"]["x"], 8)
        self.assertAlmostEqual(frames[1.5]["flyer"]["x"], 10)
        self.assertAlmostEqual(frames[2]["flyer"]["x"], 12)
        self.assertTrue(frames[2]["flyer"]["displacement_attack_locked"])
        self.assertFalse(frames[2.5]["flyer"]["displacement_attack_locked"])
        self.assertAlmostEqual(result["actors"]["flyer"]["next_attack"], 101.5)
        self.assertEqual(result["sweepers"]["launch_counts"], {"sweeper": 1})
        self.assertFalse(
            any(
                event.get("source") == "sweeper"
                and event.get("event") == "projectile_launch"
                for event in result["trace"]
            )
        )

    def test_released_gust_survives_source_death_and_moves_frozen_recipient(self):
        specification = self.fixture()
        specification["effects"] = [
            {
                "id": "destroy-source",
                "kind": "damage",
                "time_seconds": 0.75,
                "targets": ["sweeper"],
                "amount": 10000,
            },
            {
                "id": "freeze-recipient",
                "kind": "freeze",
                "time_seconds": 1.1,
                "targets": ["flyer"],
                "duration_seconds": 1,
            },
        ]
        result = self.run_scene(specification)
        middle = next(
            frame
            for frame in result["frames"]
            if abs(frame["time_seconds"] - 1.5) < 1e-8
        )
        self.assertAlmostEqual(middle["actors"]["flyer"]["x"], 10)
        self.assertGreater(middle["actors"]["flyer"]["frozen_until"], 1.5)
        self.assertAlmostEqual(result["actors"]["flyer"]["next_attack"], 101.5)
        self.assertAlmostEqual(result["actors"]["flyer"]["x"], 12)

    def test_forced_speed_controls_buff_entry_independent_of_step_size(self):
        traces = []
        for step in (0.01, 0.7):
            specification = self.fixture(step)
            field = buff_instance(time_seconds=0, x=10, y=5)
            field["parameters"]["radius_multiplier"] = 0.2
            field["parameters"]["exit_linger_seconds"] = 0
            specification["buff_spells"] = [field]
            result = self.run_scene(specification)
            traces.append(
                [
                    (round(event["time_seconds"], 7), event["event"])
                    for event in result["trace"]
                    if event.get("target") == "flyer"
                    and event["event"].startswith("buff_")
                ]
            )
            self.assertAlmostEqual(result["actors"]["flyer"]["x"], 12)
        self.assertEqual(traces[0], traces[1])
        self.assertTrue(traces[0])

    def test_old_scope_cannot_silently_accept_sweeper_behavior(self):
        specification = self.fixture()
        from clashlab.indirect_rules import RULES as OLD_RULES, SCOPE as OLD_SCOPE

        specification.update(scope=OLD_SCOPE, model_rules=deepcopy(OLD_RULES))
        with self.assertRaisesRegex(InputError, "Sweeper"):
            compile_entity_scene(specification, self.catalog)

    def test_full_battle_binds_facing_to_the_declared_layout(self):
        specification, account, army, layout = battle_fixture(self.catalog)
        scene = specification["entity_scene"]
        scene.update(scope=SCOPE, model_rules=deepcopy(RULES), buff_spells=[])
        scene["entities"].append(sweeper_instance(x=3, y=2))
        layout["inventory"]["air-sweeper"] = 1
        building = {
            "instance": "sweeper",
            "id": "air-sweeper",
            "level": 7,
            "x": 3,
            "y": 2,
            "mode": "normal",
            "counts_for_destruction": True,
            "settings": {"facing_degrees": 90},
        }
        layout["design_configuration"] = {
            "direction_convention": "draft_grid_north_zero_degrees_clockwise_not_verified_UI_orientation"
        }
        layout["buildings"].append(building)
        compile_full_battle(specification, account, army, layout, self.catalog)
        building["settings"]["facing_degrees"] = 180
        with self.assertRaisesRegex(InputError, "facing differs"):
            compile_full_battle(specification, account, army, layout, self.catalog)
        del building["settings"]["facing_degrees"]
        with self.assertRaisesRegex(InputError, "facing_degrees"):
            compile_full_battle(specification, account, army, layout, self.catalog)


if __name__ == "__main__":
    unittest.main()
