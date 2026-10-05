"""Moving enemy pursuit must use relative contact, not stale range-edge arrivals."""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from clashlab.catalog import Catalog
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial, _weapon_range_boundary, _route
from test_spatial import synthetic_scene, synthetic_structure, synthetic_unit
from test_advanced_spell_integration import spell_battle
from test_adapters import entity_instance
from test_battle_termination import termination_policy
from test_garrisons import castle_instance, member_instance, SOURCE
from test_walls import wall_parameters


class AirPursuitContactTests(unittest.TestCase):
    def test_relative_enemy_contact_has_bounded_frontiers_with_freeze_control(self):
        for frozen in (False, True):
            expected = 5 / 3 if frozen else 1
            for step in (2, 0.31, 0.017):
                spec = synthetic_scene(
                    [
                        synthetic_unit(
                            "pursuer",
                            x=0.5,
                            layer="air",
                            movement="air",
                            speed=4,
                            range=2,
                            target_priorities=["unit"],
                        ),
                        synthetic_unit(
                            "runner",
                            x=5.5,
                            team="defense",
                            speed=1,
                            range=0.5,
                            first_attack_seconds=100,
                            target_priorities=["building"],
                        ),
                        synthetic_structure(
                            "destination",
                            x=20,
                            team="attack",
                            kind="building",
                            hitpoints=10000,
                            target_priorities=[],
                        ),
                    ],
                    width=24,
                    duration_seconds=expected + 0.01,
                    maximum_step_seconds=step,
                    recording_interval_seconds=10,
                )
                if frozen:
                    spec["effects"] = [
                        dict(
                            id="freeze",
                            kind="freeze",
                            targets=["pursuer"],
                            time_seconds=0.2,
                            duration_seconds=0.5,
                        )
                    ]
                with patch(
                    "clashlab.spatial._weapon_range_boundary",
                    wraps=_weapon_range_boundary,
                ) as boundaries:
                    result = simulate_spatial(spec)
                self.assertAlmostEqual(
                    result["actors"]["runner"]["death_time"], expected, places=8
                )
                if step == 2:
                    self.assertLessEqual(boundaries.call_count, 7)

    def test_stationary_enemy_and_nonweapon_allied_routes_retain_range_endpoints(self):
        actor = synthetic_unit(layer="air", movement="air", range=2)
        target = synthetic_unit("other", x=5.5, team="defense")
        self.assertEqual(_route(actor, target, set(), 20, 20), [(5.5, 3.5)])
        target["movement"] = "stationary"
        self.assertEqual(_route(actor, target, set(), 20, 20), [(3.5, 3.5)])
        target.update(movement="ground", team="attack")
        self.assertEqual(_route(actor, target, set(), 20, 20), [(3.5, 3.5)])

    def test_paid_root_and_owned_defending_dragon_contact_preserves_release_resources_and_outcome(
        self,
    ):
        catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")
        for step in (2, 0.017):
            inputs = spell_battle(catalog, "ice-block-spell", duration=3, step=step)
            spec, account, army, layout = inputs
            scene = spec["entity_scene"]
            scene.pop("advanced_spell_binding")
            scene.update(attack_spells=[], width=40, recording_interval_seconds=10)
            spec["termination_policy"] = termination_policy()
            town_hall = scene["entities"][0]
            town_hall.update(x=25)
            root = entity_instance(
                "root",
                "root-rider",
                1,
                "attack",
                x=5.5,
                y=5.5,
                wall_parameters=wall_parameters(),
            )
            root["modifiers"]["hitpoints_multiplier"] = 0.0001
            dragon = member_instance(entity="dragon", x=0.5, y=5.5)
            dragon["modifiers"]["movement_speed_multiplier"] = 2
            castle = castle_instance([dragon], x=0, y=10)
            castle["garrison_parameters"]["release"]["initial_delay_seconds"] = 0
            scene["entities"] = [town_hall, root, castle, dragon]
            scene["defending_unit_responses"] = dict(
                source=SOURCE,
                actors={"root": {"primary": "ignore", "collateral": "ignore"}},
            )
            army.update(troops=[dict(id="root-rider", level=1, count=1)], spells=[])
            account["levels"]["root-rider"] = 1
            layout.update(width=40, inventory={"town-hall": 1, "clan-castle": 1})
            layout["buildings"][0]["x"] = 25
            layout["buildings"].append(
                dict(
                    instance="castle",
                    id="clan-castle",
                    level=12,
                    x=0,
                    y=10,
                    mode="garrison",
                    counts_for_destruction=True,
                    settings={
                        "garrison": [
                            dict(entity="dragon", level=1, count=1, donor_town_hall=16)
                        ]
                    },
                )
            )
            compiled = compile_full_battle(*deepcopy(inputs), catalog)["compiled"][
                "scene"
            ]
            actors = {a["id"]: a for a in compiled["actors"]}
            expected = (5 - actors["member"]["range"]) / (
                actors["member"]["speed"] - actors["root"]["speed"]
            )
            with patch(
                "clashlab.spatial._weapon_range_boundary", wraps=_weapon_range_boundary
            ) as boundaries:
                result = simulate_full_battle(*inputs, catalog)
            self.assertAlmostEqual(
                result["combat"]["actors"]["root"]["death_time"], expected
            )
            self.assertEqual(result["combat"]["actors"]["member"]["spawn_seconds"], 0)
            self.assertEqual(result["resource_use"]["deployed_attacker_ids"], ["root"])
            self.assertEqual(result["outcome"]["counted_building_count"], 2)
            self.assertEqual(result["outcome"]["end_reason"], "attack_force_exhausted")
            if step == 2:
                self.assertLessEqual(boundaries.call_count, 4)


if __name__ == "__main__":
    unittest.main()
