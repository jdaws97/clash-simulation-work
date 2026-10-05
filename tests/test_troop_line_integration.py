"""Finite line weapons in paid battles; declared synthetic geometry only."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.attacking_extensions import SCOPE
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial
from clashlab.troop_line_bindings import LINE_POLICIES
from test_adapters import entity_instance
from test_advanced_spell_integration import spell_battle
from test_battle_termination import termination_policy
from test_garrisons import castle_instance, member_instance
from test_spell_lifecycle_integration import recall
from clashlab.defending_cc_extensions import SCOPE as DEFENSE_SCOPE

SOURCE = "synthetic-line-family-vertical-not-game-calibration"


def line_instance(catalog, entity="bowler", actor_id="line", **changes):
    level = min(row["level"] for row in catalog.entity(entity)["levels"])
    count = {"bowler": 2, "super-bowler": 3, "super-archer": 1}[entity]
    return entity_instance(
        actor_id,
        entity,
        level,
        "attack",
        x=9.5,
        y=6,
        wall_parameters={"kind": "avoid", "source": SOURCE},
        attacking_extension_scope=SCOPE,
        line_binding={"source": SOURCE, "target_layers": ["ground"], **LINE_POLICIES},
        line_weapon_parameters={
            "source": SOURCE,
            "status": "explicit_uncalibrated_hypothesis",
            "kind": "piercing" if entity == "super-archer" else "bounce",
            "distance_tiles": 9,
            "radius_tiles": 0.1,
            "speed_tiles_per_second": 2,
            "release_delay_seconds": 0,
            "bounce_offsets_tiles": [4 * i for i in range(count)],
            "damage_multipliers": [1] * count,
            "membership": "live_at_each_impact",
            "repeats": "one_hit_per_actor_per_launch",
            "source_persistence": "released_projectile_survives",
        },
        **changes,
    )


def line_battle(catalog, entity="bowler", step=0.25):
    inputs = spell_battle(catalog, "ice-block-spell", step=step, duration=7)
    spec, account, army, layout = inputs
    scene = spec["entity_scene"]
    scene.pop("advanced_spell_binding")
    scene["attack_spells"] = []
    army["spells"] = []
    spec["termination_policy"] = termination_policy()
    parent = line_instance(catalog, entity)
    parent["modifiers"]["hitpoints_multiplier"] = 0.0001
    scene["entities"] = [scene["entities"][0], parent]
    scene["entities"][0]["modifiers"]["hitpoints_multiplier"] = 0.0001
    level = parent["level"]
    account["levels"][entity] = level
    account["active_super_troops"] = [entity] if entity.startswith("super-") else []
    army["troops"] = [{"id": entity, "level": level, "count": 1}]
    gold = entity_instance(
        "gold",
        "gold-storage",
        1,
        "defense",
        x=15,
        y=5,
        mode="passive",
        statistics_mode="none",
        attack_parameters={},
        inactive_attack_interval_seconds=1,
    )
    gold["modifiers"]["hitpoints_multiplier"] = 100
    scene["entities"].append(gold)
    layout["inventory"]["gold-storage"] = 1
    layout["buildings"].append(
        {
            "instance": "gold",
            "id": "gold-storage",
            "level": 1,
            "x": 15,
            "y": 5,
            "mode": "passive",
            "counts_for_destruction": True,
        }
    )
    return inputs


class TroopLineIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")

    def test_paid_family_released_shots_survive_source_and_primary_loss_then_exhaust(
        self,
    ):
        for entity in ("bowler", "super-bowler", "super-archer"):
            for step in (0.017, 0.25):
                with self.subTest(entity=entity, step=step):
                    result = simulate_full_battle(
                        *line_battle(self.catalog, entity, step), self.catalog
                    )
                    combat = result["combat"]
                    self.assertEqual(combat["actors"]["line"]["death_time"], 0)
                    self.assertIsNotNone(combat["actors"]["hall"]["death_time"])
                    shots = [
                        e
                        for e in combat["trace"]
                        if e.get("event") == "troop_line_launch"
                    ]
                    self.assertEqual(len(shots), 1)
                    self.assertFalse(
                        any(
                            e.get("event") == "projectile_launch"
                            and e.get("source") == "line"
                            for e in combat["trace"]
                        )
                    )
                    hits = combat["troop_lines"]["impacts"]
                    self.assertEqual([e["target"] for e in hits], ["hall", "gold"])
                    self.assertTrue(all(e["amount"] > 0 for e in hits))
                    self.assertEqual(combat["troop_lines"]["pending_count"], 0)
                    self.assertEqual(
                        result["outcome"]["end_reason"], "attack_force_exhausted"
                    )
                    expected = {
                        "bowler": 3.25,
                        "super-bowler": 5.25,
                        "super-archer": 4.5,
                    }[entity]
                    self.assertAlmostEqual(
                        result["outcome"]["elapsed_seconds"], expected
                    )
                    self.assertEqual(
                        result["resource_use"]["deployed_attacker_ids"], ["line"]
                    )
                    self.assertEqual(result["resource_use"]["spell_slots"], [])

    def test_defending_castle_release_uses_one_owner_actual_damage_and_defensive_continuation(
        self,
    ):
        for step in (0.017, 0.25):
            inputs = line_battle(self.catalog, step=step)
            spec, account, army, layout = inputs
            scene = spec["entity_scene"]
            hall = scene["entities"][0]
            hall["town_hall_parameters"]["activation"].update(
                initial_state="dormant", activation_delay_seconds=100
            )
            hall["modifiers"]["hitpoints_multiplier"] = 1
            attacker = entity_instance(
                "pekka",
                "pekka",
                1,
                "attack",
                x=14.5,
                y=11.5,
                first_attack_seconds=0.4,
                wall_parameters={"kind": "avoid", "source": SOURCE},
            )
            attacker["modifiers"].update(hitpoints_multiplier=0.001, range_multiplier=4)
            member = line_instance(self.catalog, actor_id="member")
            member.update(
                team="defense",
                spawn_seconds="controlled",
                x=14.5,
                y=9.5,
                garrison_member_parameters={
                    "source": SOURCE,
                    "castle_id": "castle",
                    "donor_town_hall": 16,
                    "level_basis": "snapshot_receiver_lab_cap_with_unlock_floor",
                },
                defending_extension_scope=DEFENSE_SCOPE,
                defending_extension_parameters={
                    "source": SOURCE,
                    "status": "explicit_uncalibrated_hypothesis",
                    "abilities": {},
                    "target_layers": ["ground"],
                    "wall_policy": "avoid",
                    "hound_quantity_basis": "not_applicable",
                    "ice_hound_freeze_basis": "not_applicable",
                },
            )
            castle = castle_instance([member], x=15, y=10)
            castle["modifiers"]["hitpoints_multiplier"] = 0.0001
            scene["entities"] = [hall, attacker, castle, member]
            scene["defending_unit_responses"] = {
                "source": SOURCE,
                "actors": {
                    "pekka": {
                        "primary": "same_tier_as_buildings",
                        "collateral": "allow",
                    }
                },
            }
            army["troops"] = [{"id": "pekka", "level": 1, "count": 1}]
            layout["inventory"] = {"town-hall": 1, "clan-castle": 1}
            layout["buildings"] = [
                layout["buildings"][0],
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
                                "entity": "bowler",
                                "level": member["level"],
                                "count": 1,
                                "donor_town_hall": 16,
                            }
                        ]
                    },
                },
            ]
            result = simulate_full_battle(*inputs, self.catalog)
            combat = result["combat"]
            self.assertAlmostEqual(combat["actors"]["castle"]["death_time"], 0.4)
            self.assertEqual(
                [
                    e["member"]
                    for e in combat["trace"]
                    if e.get("event") == "garrison_released"
                ],
                ["member"],
            )
            hits = combat["troop_lines"]["impacts"]
            self.assertEqual([e["target"] for e in hits], ["pekka"])
            self.assertAlmostEqual(hits[0]["time_seconds"], 1.2)
            self.assertGreater(hits[0]["amount"], 0)
            self.assertEqual(result["outcome"]["end_reason"], "attack_force_exhausted")
            self.assertAlmostEqual(result["outcome"]["elapsed_seconds"], 1.2)
            self.assertEqual(combat["troop_lines"]["pending_count"], 1)
            self.assertEqual(result["resource_use"]["deployed_attacker_ids"], ["pekka"])

    def test_shared_protection_consumes_one_hit_and_exact_sub_epsilon_impact_is_not_skipped(
        self,
    ):
        raw = compile_full_battle(*line_battle(self.catalog), self.catalog)["compiled"][
            "scene"
        ]
        raw["effects"] = [
            {
                "id": "protection",
                "kind": "invulnerability",
                "targets": ["gold"],
                "time_seconds": 0,
                "duration_seconds": 6,
            }
        ]
        owner = next(a for a in raw["actors"] if a["id"] == "line")
        owner["troop_line_model"]["radius_tiles"] = 10
        owner["entity_adapter"]["line_weapon_parameters"]["radius_tiles"] = 10
        raw["effects"][0]["duration_seconds"] = 2
        result = simulate_spatial(raw)
        self.assertEqual(
            [
                e["amount"]
                for e in result["troop_lines"]["impacts"]
                if e["target"] == "gold"
            ],
            [0],
        )
        inputs = line_battle(self.catalog)
        model = inputs[0]["entity_scene"]["entities"][1]["line_weapon_parameters"]
        model["speed_tiles_per_second"] = 1e12
        result = simulate_full_battle(*inputs, self.catalog)
        self.assertEqual(
            [e["time_seconds"] for e in result["combat"]["troop_lines"]["impacts"]],
            [2.5e-12, 6.5e-12],
        )
        self.assertEqual(result["outcome"]["elapsed_seconds"], 6.5e-12)

    def test_recall_keeps_released_packet_and_collateral_response_is_shared(self):
        inputs = line_battle(self.catalog)
        inputs[0]["entity_scene"]["entities"][1]["modifiers"][
            "hitpoints_multiplier"
        ] = 50
        recall(inputs, 0.1, 6, x=9.5)
        result = simulate_full_battle(*inputs, self.catalog)
        hits = result["combat"]["troop_lines"]["impacts"]
        self.assertEqual(
            [(e["target"], e["time_seconds"]) for e in hits if e["time_seconds"] < 6],
            [("hall", 1.25), ("gold", 3.25)],
        )
        self.assertEqual(result["resource_use"]["deployed_attacker_ids"], ["line"])
        self.assertEqual(
            sum(s["spent"] for s in result["resource_use"]["spell_slots"]), 1
        )
        for collateral in ("ignore", "allow"):
            inputs = line_battle(self.catalog)
            spec, account, army, layout = inputs
            scene = spec["entity_scene"]
            scene["entities"][1]["line_weapon_parameters"]["radius_tiles"] = 5
            tank = entity_instance(
                "tank",
                "pekka",
                1,
                "attack",
                x=14.5,
                y=9.5,
                first_attack_seconds=100,
                wall_parameters={"kind": "avoid", "source": SOURCE},
            )
            member = member_instance(x=14.5, y=6, first_attack_seconds=100)
            castle = castle_instance([member], x=15, y=10)
            scene["entities"].extend([tank, castle, member])
            scene["defending_unit_responses"] = {
                "source": SOURCE,
                "actors": {
                    "line": {"primary": "ignore", "collateral": collateral},
                    "tank": {"primary": "ignore", "collateral": "ignore"},
                },
            }
            army["troops"].append({"id": "pekka", "level": 1, "count": 1})
            layout["inventory"]["clan-castle"] = 1
            layout["buildings"].append(
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
                                "entity": "archer",
                                "level": 1,
                                "count": 1,
                                "donor_town_hall": 16,
                            }
                        ]
                    },
                }
            )
            result = simulate_full_battle(*inputs, self.catalog)
            hits = [
                e
                for e in result["combat"]["troop_lines"]["impacts"]
                if e["target"] == "member"
            ]
            self.assertEqual(len(hits), int(collateral == "allow"))
            if hits:
                self.assertGreater(hits[0]["amount"], 0)

    def test_raw_owner_and_model_mismatch_fail_closed(self):
        inputs = line_battle(self.catalog)
        raw = compile_full_battle(*inputs, self.catalog)["compiled"]["scene"]
        for field in ("troop_line_model", "entity_adapter"):
            changed = deepcopy(raw)
            owner = next(a for a in changed["actors"] if a["id"] == "line")
            owner.pop(field)
            with self.assertRaisesRegex(InputError, "Line weapon requires"):
                simulate_spatial(changed)
        inputs[0]["entity_scene"]["entities"][1].pop("line_binding")
        with self.assertRaises(InputError):
            compile_full_battle(*inputs, self.catalog)


if __name__ == "__main__":
    unittest.main()
