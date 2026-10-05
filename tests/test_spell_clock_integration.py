"""Paid Ice clocks and the independently reported Jump/Tornado composition."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial
from test_advanced_spell_integration import spell_battle, jump_battle, SOURCE
from test_attack_spells import spell_parameters
from test_battle_termination import classification, termination_policy
from test_defending_troop_roles import special_member
from test_garrisons import castle_instance
from test_full_battle import add_hero
from test_equipment_weapons import gear
from test_tornado_traps import tornado_instance, tornado_parameters


def ice_battle(catalog, step, *, time=0.5, duration=11):
    inputs = spell_battle(
        catalog, "ice-block-spell", time=time, step=step, duration=duration
    )
    troop = inputs[0]["entity_scene"]["entities"][1]
    troop["modifiers"]["hitpoints_multiplier"] = 1
    troop["first_attack_seconds"] = 0
    return inputs


def launches(combat, actor="pekka-0"):
    return [
        e["time_seconds"]
        for e in combat["trace"]
        if e.get("event") == "projectile_launch" and e["source"] == actor
    ]


def ice_freeze_battle(catalog, step, ice_at, freeze_at, duration_multiplier):
    inputs = ice_battle(catalog, step, time=ice_at, duration=14)
    scene = inputs[0]["entity_scene"]
    member = special_member("ice-golem")
    member.update(x=9.5, y=6.5, first_attack_seconds=100)
    member["modifiers"]["hitpoints_multiplier"] = 0.001
    member["modifiers"]["movement_speed_multiplier"] = 0.0001
    member["ice_parameters"]["death_duration_multiplier"] = duration_multiplier
    castle = castle_instance([member], x=15, y=10)
    scene["entities"].extend([castle, member])
    scene["defending_unit_responses"] = {
        "source": SOURCE,
        "actors": {"pekka-0": {"primary": "ignore", "collateral": "ignore"}},
    }
    scene["attack_spells"].append(
        {
            "id": "paid-lightning",
            "entity": "lightning-spell",
            "level": 1,
            "town_hall": 16,
            "time_seconds": freeze_at,
            "x": 9.5,
            "y": 6.5,
            "parameters": spell_parameters("lightning-spell"),
        }
    )
    inputs[1]["levels"]["lightning-spell"] = 1
    inputs[2]["spells"].append({"id": "lightning-spell", "level": 1, "count": 1})
    inputs[3]["inventory"]["clan-castle"] = 1
    inputs[3]["buildings"].append(
        {
            "instance": "castle",
            "id": "clan-castle",
            "level": 12,
            "x": 15,
            "y": 10,
            "mode": "garrison",
            "counts_for_destruction": True,
            "settings": {
                "garrison": [
                    {
                        "entity": "ice-golem",
                        "level": 1,
                        "count": 1,
                        "donor_town_hall": 16,
                    }
                ]
            },
        }
    )
    inputs[0]["termination_policy"] = termination_policy(
        [
            classification(
                {"origin": "army", "entity": "ice-block-spell", "level": 1},
                "support_only",
                "ignore",
            ),
            classification(
                {"origin": "army", "entity": "lightning-spell", "level": 1},
                "damage",
                "while_unspent",
            ),
        ]
    )
    return inputs


class SpellClockIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")

    def test_paid_ice_union_retains_work_and_reduction_ends_independently(self):
        for step in (0.017, 0.25):
            inputs = ice_battle(self.catalog, step)
            scene = inputs[0]["entity_scene"]
            second = deepcopy(scene["attack_spells"][0])
            second.update(id="second-ice", time_seconds=2)
            scene["attack_spells"].append(second)
            inputs[2]["spells"][0]["count"] = 2
            result = simulate_full_battle(*inputs, self.catalog)
            combat = result["combat"]
            shots = launches(combat)
            self.assertEqual(len(shots), 2)
            self.assertEqual(shots[0], 0)
            self.assertAlmostEqual(shots[1], 10.3)
            hits = [
                e
                for e in combat["trace"]
                if e.get("event") == "damage_received" and e["target_id"] == "pekka-0"
            ]
            self.assertTrue(hits)
            for hit in hits:
                factor = 0.14 if 0.5 <= hit["time_seconds"] < 9 else 1
                self.assertAlmostEqual(
                    hit["final_damage"], hit["requested_damage"] * factor
                )
            self.assertEqual(
                sum(s["spent"] for s in result["resource_use"]["spell_slots"]), 2
            )
            self.assertEqual(result["resource_use"]["generated_spell_units"], {})
            self.assertEqual(result["outcome"]["end_reason"], "declared_time_limit")

    def test_paid_ice_stops_movement_then_resumes_and_does_not_hold_dead_army(self):
        for step in (0.017, 0.25):
            inputs = ice_battle(self.catalog, step, time=0, duration=9)
            scene = inputs[0]["entity_scene"]
            scene["entities"][1].update(x=7.5)
            scene["attack_spells"][0].update(x=7.5)
            scene["recording_interval_seconds"] = 0.5
            result = simulate_full_battle(*inputs, self.catalog)
            for frame in result["combat"]["frames"]:
                if frame["time_seconds"] <= 7:
                    self.assertEqual(frame["actors"]["pekka-0"]["x"], 7.5)
            self.assertGreater(result["combat"]["actors"]["pekka-0"]["x"], 9)
            self.assertTrue(launches(result["combat"]))
            inputs = spell_battle(
                self.catalog, "ice-block-spell", step=step, duration=9
            )
            lost = simulate_full_battle(*inputs, self.catalog)
            self.assertEqual(lost["outcome"]["end_reason"], "attack_force_exhausted")
            self.assertLess(lost["outcome"]["elapsed_seconds"], 7)
            self.assertEqual(
                sum(s["spent"] for s in lost["resource_use"]["spell_slots"]), 1
            )
        inputs = ice_battle(self.catalog, 0.25)
        add_hero(inputs[0], inputs[2], inputs[1])
        inputs[0]["entity_scene"]["entities"][-1]["hero_parameters"]["equipment"][0] = (
            gear("seeking-shield")
        )
        inputs[2]["heroes"][0]["equipment"][0]["id"] = "seeking-shield"
        inputs[2]["heroes"][0]["equipment"][0]["level"] = 18
        inputs[1]["levels"]["seeking-shield"] = 18
        with self.assertRaisesRegex(InputError, "Ice Block secondary lifecycle"):
            simulate_full_battle(*inputs, self.catalog)

    def test_paid_defensive_death_freeze_overlap_both_orders_keeps_work(self):
        for step in (0.017, 0.25):
            for ice_at, freeze_at, multiplier in (
                (0.5, 1, 4),
                (2, 0.5, 1),
            ):
                inputs = ice_freeze_battle(
                    self.catalog, step, ice_at, freeze_at, multiplier
                )
                result = simulate_full_battle(*inputs, self.catalog)
                combat = result["combat"]
                self.assertAlmostEqual(
                    combat["actors"]["member"]["death_time"], freeze_at
                )
                member = next(
                    a
                    for a in result["compiled"]["scene"]["actors"]
                    if a["id"] == "member"
                )
                freeze_end = (
                    freeze_at + member["death_model"]["effects"][0]["duration_seconds"]
                )
                expected = 1.8 + max(ice_at + 7, freeze_end) - min(ice_at, freeze_at)
                shots = launches(combat)
                self.assertEqual(shots[0], 0)
                self.assertAlmostEqual(shots[1], expected)
                hits = [
                    e
                    for e in combat["trace"]
                    if e.get("event") == "damage_received"
                    and e["target_id"] == "pekka-0"
                    and e["time_seconds"] >= ice_at + 7
                ]
                self.assertTrue(hits)
                self.assertTrue(
                    all(
                        abs(e["final_damage"] - e["requested_damage"]) < 1e-8
                        for e in hits
                    )
                )
                self.assertEqual(
                    sum(s["spent"] for s in result["resource_use"]["spell_slots"]), 2
                )
                self.assertEqual(
                    result["resource_use"]["deployed_attacker_ids"], ["pekka-0"]
                )

    def test_paid_jump_tornado_capture_expiry_and_post_release_legal_exit(self):
        for step in (0.017, 0.25):
            inputs = jump_battle(self.catalog, step, duration=40)
            scene = inputs[0]["entity_scene"]
            scene["entities"][1]["modifiers"]["movement_speed_multiplier"] = 0.05
            scene["recording_interval_seconds"] = 0.5
            scene["traps"] = [
                tornado_instance(
                    x=9, y=5, parameters=tornado_parameters(arming_seconds=20)
                )
            ]
            inputs[3]["inventory"]["tornado-trap"] = 1
            inputs[3]["buildings"].append(
                {
                    "instance": "tornado",
                    "id": "tornado-trap",
                    "level": 3,
                    "x": 9,
                    "y": 5,
                    "counts_for_destruction": False,
                }
            )
            result = simulate_full_battle(*inputs, self.catalog)
            combat = result["combat"]
            captures = [
                e for e in combat["trace"] if e.get("event") == "tornado_capture"
            ]
            self.assertEqual(len(captures), 1)
            self.assertEqual(captures[0]["time_seconds"], 20)
            previous = None
            for frame in combat["frames"]:
                point = frame["actors"]["pekka-0"]
                self.assertFalse(10 <= point["x"] < 14 and 4 <= point["y"] < 8)
                if 21 <= frame["time_seconds"] <= 27:
                    self.assertAlmostEqual(point["x"], 8.5)
                if previous and frame["time_seconds"] >= 27:
                    dt = frame["time_seconds"] - previous[0]
                    self.assertLessEqual(abs(point["x"] - previous[1]), 0.1 * dt + 1e-8)
                previous = frame["time_seconds"], point["x"]
            state = combat["attack_spells"]["advanced_spells"]
            self.assertEqual(state["pending_wall_exit_ids"], [])
            self.assertEqual(state["jump_wall_exemptions"], {})
            self.assertTrue(
                all(combat["actors"][f"wall-{y}"]["hp"] > 0 for y in range(16))
            )
            self.assertEqual(
                sum(s["spent"] for s in result["resource_use"]["spell_slots"]), 1
            )


if __name__ == "__main__":
    unittest.main()
