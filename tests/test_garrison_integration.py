"""Garrisons in complete declared battles and shared projectile/field phases."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.garrison_rules import RULES, SCOPE
from clashlab.spatial import simulate_spatial

from test_full_battle import fixture
from test_garrisons import SOURCE, castle_instance, garrison_sector, member_instance
from test_indirect_defenses import damage_command, fixed_tank


ROOT = Path(__file__).resolve().parents[1]


def full_fixture(catalog):
    specification, account, army, layout = fixture(catalog, time_limit=0.7)
    member = member_instance(x=3.5, y=11.5)
    castle = castle_instance([member], x=4, y=10)
    scene = specification["entity_scene"]
    scene.update(scope=SCOPE, model_rules=deepcopy(RULES), buff_spells=[])
    scene["entities"].extend([castle, member])
    scene["defending_unit_responses"] = {
        "source": SOURCE,
        "actors": {
            actor["id"]: {"primary": "same_tier_as_buildings", "collateral": "allow"}
            for actor in scene["entities"]
            if actor["team"] == "attack"
        },
    }
    layout["inventory"]["clan-castle"] = 1
    layout["buildings"].append(
        {
            "instance": "castle",
            "id": "clan-castle",
            "level": 12,
            "x": 4,
            "y": 10,
            "counts_for_destruction": True,
            "settings": {
                "garrison": [
                    {"entity": "archer", "level": 1, "count": 1, "donor_town_hall": 16}
                ]
            },
        }
    )
    return specification, account, army, layout


class GarrisonIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_full_battle_binds_defending_roster_independently_of_attacking_cc(self):
        arguments = full_fixture(self.catalog)
        compiled = compile_full_battle(*arguments, self.catalog)
        binding = compiled["validation"]["defender_bindings"]["member"]
        self.assertEqual(binding["role"], "defending_garrison")
        self.assertFalse(binding["counts_for_destruction"])
        self.assertEqual(arguments[2]["clan_castle"]["troops"], [])
        result = simulate_full_battle(*arguments, self.catalog)
        self.assertEqual(
            result["combat"]["garrisons"]["castles"]["castle"]["released"], ["member"]
        )

    def test_roster_count_level_donor_and_missing_settings_fail_closed(self):
        for field, value in (("count", 2), ("level", 2), ("donor_town_hall", 17)):
            with self.subTest(field=field):
                arguments = full_fixture(self.catalog)
                arguments[3]["buildings"][-1]["settings"]["garrison"][0][field] = value
                with self.assertRaises(InputError):
                    compile_full_battle(*arguments, self.catalog)
        arguments = full_fixture(self.catalog)
        arguments[3]["buildings"][-1]["settings"] = {}
        with self.assertRaises(InputError):
            compile_full_battle(*arguments, self.catalog)

    def test_unbound_reserve_and_hidden_legacy_requirements_are_rejected(self):
        arguments = full_fixture(self.catalog)
        arguments[0]["entity_scene"]["entities"].append(member_instance("extra", x=3.5))
        with self.assertRaises(InputError):
            compile_full_battle(*arguments, self.catalog)
        arguments = full_fixture(self.catalog)
        arguments[3]["design_configuration"] = {"defensive_castle": {"troops": []}}
        with self.assertRaises(InputError):
            compile_full_battle(*arguments, self.catalog)

    def test_released_projectile_survives_member_and_castle_death(self):
        member = member_instance()
        member["attack_parameters"]["projectile"] = {
            "timing": "launch_distance_delay",
            "delay_seconds": 0,
            "speed_tiles_per_second": 2,
            "destination": "locked_actor_center_at_impact",
            "hit_radius": 0,
        }
        scene = garrison_sector(
            self.catalog,
            [castle_instance([member]), member, fixed_tank(x=17.5, y=11.5)],
            effects=[
                damage_command("member", 0.3, 100000, "kill-member"),
                damage_command("castle", 0.3, 100000, "kill-castle"),
            ],
            duration_seconds=1.3,
        )
        result = simulate_spatial(compile_entity_scene(scene, self.catalog)["scene"])
        self.assertEqual(result["garrisons"]["members"]["member"]["phase"], "dead")
        self.assertEqual(
            result["actors"]["tank"]["maximum_hp"] - result["actors"]["tank"]["hp"], 8
        )

    def test_actual_air_route_triggers_at_exact_circle_boundary(self):
        member = member_instance()
        attacker = fixed_tank(entity="minion", x=1.5, y=11.5)
        attacker["modifiers"]["range_multiplier"] = 1
        for step in (0.01, 0.8):
            scene = garrison_sector(
                self.catalog,
                [castle_instance([member]), member, attacker],
                duration_seconds=2.1,
                maximum_step_seconds=step,
            )
            result = simulate_spatial(
                compile_entity_scene(scene, self.catalog)["scene"]
            )
            trigger = next(
                event
                for event in result["trace"]
                if event["event"] == "garrison_triggered"
            )
            self.assertAlmostEqual(trigger["time_seconds"], 1.75)
            self.assertAlmostEqual(
                result["garrisons"]["members"]["member"]["released_at"], 1.95
            )


if __name__ == "__main__":
    unittest.main()
