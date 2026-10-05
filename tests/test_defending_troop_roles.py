"""Small cross-role lifecycle checks; all fixtures are synthetic."""

from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.spatial import simulate_spatial
from clashlab.full_battle import compile_full_battle

from test_garrisons import SOURCE, castle_instance, garrison_sector, member_instance
from test_hit_status import slow
from test_indirect_defenses import damage_command, fixed_tank
from test_garrison_integration import full_fixture


ROOT = Path(__file__).resolve().parents[1]


def special_member(entity, level=1):
    member = member_instance(entity=entity, level=level)
    if entity == "hog-rider":
        member["wall_parameters"]["kind"] = "jump_enemy_walls"
    if entity == "ice-golem":
        member["ice_parameters"] = {
            "source": SOURCE,
            "on_hit_slow": slow(),
            "death_delay_seconds": 0,
            "death_radius_multiplier": 1,
            "death_duration_multiplier": 1,
            "death_target_kinds": ["unit"],
            "death_target_layers": ["ground", "air"],
        }
    if entity in {"electro-dragon", "dragon-rider"}:
        member["death_parameters"] = {
            "source": SOURCE,
            "statistic_basis": (
                "snapshot_single_blast"
                if entity == "dragon-rider"
                else "snapshot_deathDamage_is_total_hypothesis"
            ),
            "damage_multiplier": 1,
            "impacts": [
                {
                    "id": "blast",
                    "source": SOURCE,
                    "delay_seconds": 0.05,
                    "offset_x": 0,
                    "offset_y": 0,
                    "radius": 3,
                    "target_kinds": ["unit"],
                    "target_layers": ["ground"],
                    "damage_fraction": 1,
                }
            ],
        }
        if entity == "electro-dragon":
            member["readiness_policy"] = {
                "selection": "absolute_first_attack_seconds_hypothesis",
                "source": SOURCE,
            }
            member["attack_parameters"].update(
                jump_metric="center_distance",
                jump_delay_seconds=0.02,
                tie_break="distance_then_instance_id",
                allow_protected_links=True,
                damage_multipliers=[1, 0.8],
                jump_range=3,
            )
        else:
            member["target_layer_policy"] = {
                "selection": "snapshot_ground_only_hypothesis",
                "source": SOURCE,
            }
    return member


class DefendingTroopRoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def compile(self, member, **changes):
        entities = [castle_instance([member]), member, fixed_tank(x=17.5, y=11.5)]
        return compile_entity_scene(
            garrison_sector(self.catalog, entities, **changes), self.catalog
        )["scene"]

    def test_shared_special_weapons_preserve_status_death_chain_and_wall_traversal(
        self,
    ):
        for entity in (
            "ice-golem",
            "electro-dragon",
            "dragon-rider",
            "giant",
            "hog-rider",
        ):
            with self.subTest(entity=entity):
                scene = self.compile(special_member(entity))
                member = scene["actors"][1]
                self.assertEqual(member["team"], "defense")
                self.assertEqual(member["target_priorities"], ["unit"])
                self.assertEqual(member["spawn_seconds"], "controlled")
                self.assertFalse(member["counts_for_destruction"])
                for effect in member.get("death_model", {}).get("effects", []):
                    self.assertEqual(effect["area"]["target_team"], "attack")
                    self.assertEqual(effect["area"]["target_kinds"], ["unit"])
                if entity == "ice-golem":
                    effect = member["death_model"]["effects"][0]
                    self.assertEqual(effect["area"]["radius"], 5.5)
                    self.assertEqual(
                        effect["duration_seconds"],
                        self.catalog.level(entity, 1)["deathFreezeTimeOnDefense"],
                    )
                    self.assertIn("on_hit_status", member)
                if entity == "electro-dragon":
                    self.assertEqual(member["attack_model"]["kind"], "chain")
                if entity == "hog-rider":
                    self.assertEqual(
                        member["wall_behavior"]["kind"], "jump_enemy_walls"
                    )

    def test_defensive_ice_freeze_occurs_after_actual_member_death(self):
        scene = self.compile(
            special_member("ice-golem"),
            duration_seconds=0.65,
            effects=[damage_command("member", 0.3, 100000, "kill-ice")],
        )
        result = simulate_spatial(scene)
        self.assertEqual(result["garrisons"]["members"]["member"]["phase"], "dead")
        self.assertGreater(result["actors"]["tank"]["frozen_until"], 0.3)
        emitted = result["death_effects"]["emitted_instances"]
        self.assertEqual(emitted.count("member"), 1)
        self.assertEqual(
            result["garrisons"]["castles"]["castle"]["released"], ["member"]
        )

    def test_full_battle_binds_special_cc_to_defense_without_paid_army_inventory(self):
        arguments = full_fixture(self.catalog)
        scene = arguments[0]["entity_scene"]
        replacement = special_member("ice-golem")
        replacement.update(x=3.5, y=11.5)
        scene["entities"] = [
            replacement if actor["id"] == "member" else actor
            for actor in scene["entities"]
        ]
        arguments[3]["buildings"][-1]["settings"]["garrison"][0]["entity"] = "ice-golem"
        compiled = compile_full_battle(*arguments, self.catalog)
        binding = compiled["validation"]["defender_bindings"]["member"]
        self.assertEqual(binding["role"], "defending_garrison")
        self.assertFalse(binding["counts_for_destruction"])
        self.assertEqual(arguments[2]["clan_castle"]["troops"], [])


if __name__ == "__main__":
    unittest.main()
