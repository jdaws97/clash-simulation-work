"""Paid mixed roster with finite generated identities and explicit trap responses."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.giga_responses import STATUS, SELECTION
from clashlab.spatial import simulate_spatial
from test_crafted_integration import crafted_battle, add_troop
from test_full_battle import add_hero, deployment
from test_giga_bombs import giga_instance, response
from test_hero_pets import pet_instance
from test_heroes import ability

SOURCE = "synthetic-complete-giga-roster-not-game-calibration"


def mixed_battle(catalog, step=0.25):
    inputs = crafted_battle(catalog, "cake-a-pult", duration=0.4, step=step)
    spec, account, army, layout = inputs
    scene = spec["entity_scene"]
    scene["entities"][2]["first_attack_seconds"] = 100
    scene["entities"][3]["first_attack_seconds"] = 100
    scene["entities"][3]["modifiers"]["hitpoints_multiplier"] = 100
    add_troop(inputs, "pekka", "tank")
    add_troop(inputs, "archer", "reserve", spawn="controlled")
    queen = add_hero(spec, army, account, "archer-queen")
    queen.update(x=2.5, y=5.5, first_attack_seconds=100)
    queen["modifiers"]["hitpoints_multiplier"] = 100
    queen["hero_parameters"]["pet_policy"] = "paired_pet_from_explicit_scene_assignment"
    pet = pet_instance("unicorn")
    pet["hero_id"] = "queen"
    scene["pets"] = [pet]
    army["heroes"][0]["pet"] = {"id": "unicorn", "level": pet["level"]}
    account["levels"]["unicorn"] = pet["level"]
    release = deployment("reserve", 0.15)
    release["positions"]["reserve"] = {"x": 2.5, "y": 5.5}
    scene["effects"] = [ability("queen", 0), release]
    for key in ("queen", "pet", "queen-mirror-clone-0", "queen-mirror-clone-1"):
        scene["defending_unit_responses"]["actors"][key] = {
            "primary": "ignore",
            "collateral": "ignore",
        }
    # Exact finite Mirror identities are owned by the equipped Queen compiler.
    base = compile_full_battle(*inputs, catalog)["compiled"]["scene"]
    children = [a["id"] for a in base["actors"] if "summon_model" in a]
    trap = giga_instance({}, town_hall=18, x=1, y=7)
    trap["parameters"].update(delay_seconds=0.2, push_distance_tiles=0)
    scene["traps"].append(trap)
    layout["inventory"]["giga-bomb"] = 1
    layout["buildings"].append(
        {
            "instance": "giga",
            "id": "giga-bomb",
            "level": 3,
            "x": 1,
            "y": 7,
            "mode": "armed",
            "counts_for_destruction": False,
        }
    )
    scene["giga_bomb_response_binding"] = {
        "source": SOURCE,
        "status": STATUS,
        "selection": SELECTION,
        "actor_responses": {key: response(0, 0.5, 0) for key in children},
        "entity_responses": {
            "archer": response("catalog_housing_space"),
            "pekka": response("catalog_housing_space"),
            "archer-queen": response(25),
            "unicorn": response(0),
        },
    }
    return inputs


class GigaResponseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")

    def test_paid_mixed_roster_reserves_pets_and_mirror_receive_one_live_delayed_blast(
        self,
    ):
        for step in (0.017, 0.25):
            inputs = mixed_battle(self.catalog, step)
            before = deepcopy(inputs)
            result = simulate_full_battle(*inputs, self.catalog)
            self.assertEqual(inputs, before)
            scene = result["compiled"]["scene"]
            audit = scene["giga_bomb_response_audit"]
            expected = {
                a["id"]
                for a in scene["actors"]
                if a["team"] == "attack" and a["kind"] == "unit"
            }
            self.assertEqual(set(audit["responses"]), expected)
            self.assertEqual(audit["responses"]["tank"]["trigger_weight"], 25)
            self.assertEqual(audit["responses"]["reserve"]["trigger_weight"], 1)
            self.assertEqual(audit["responses"]["pet"]["trigger_weight"], 0)
            combat = result["combat"]
            trigger = combat["giga_bombs"]["triggered"]["giga"]
            self.assertNotIn("reserve", trigger["trigger_weights"])
            self.assertEqual(combat["giga_bombs"]["resolved"], ["giga"])
            hits = [e for e in combat["trace"] if e.get("event") == "giga_bomb_impact"]
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["time_seconds"], 0.2)
            self.assertEqual(set(hits[0]["requested_damage"]), expected)
            for key in expected:
                self.assertEqual(
                    hits[0]["requested_damage"][key],
                    1300 * audit["responses"][key]["damage_multiplier"],
                )
            self.assertEqual(combat["actors"]["reserve"]["death_time"], 0.2)
            army_actor = combat["actors"]["army"]
            self.assertEqual(army_actor["maximum_hp"] - army_actor["hp"], 1300)
            self.assertIn("reserve", result["resource_use"]["deployed_attacker_ids"])
            self.assertEqual(
                result["combat"]["hero_abilities"]["hero_abilities_used"], ["queen"]
            )
            self.assertEqual(result["outcome"]["end_reason"], "declared_time_limit")

    def test_missing_generated_response_and_stale_or_ambiguous_maps_fail_closed(self):
        inputs = mixed_battle(self.catalog)
        for change in ("missing_child", "stale", "legacy", "missing_pet"):
            altered = deepcopy(inputs)
            scene = altered[0]["entity_scene"]
            binding = scene["giga_bomb_response_binding"]
            if change == "missing_child":
                binding["actor_responses"].pop(next(iter(binding["actor_responses"])))
            elif change == "stale":
                binding["actor_responses"]["old-dragon"] = response(20)
            elif change == "legacy":
                scene["traps"][0]["parameters"]["unit_responses"]["old-dragon"] = (
                    response(20)
                )
            else:
                binding["entity_responses"].pop("unicorn")
            with (
                self.subTest(change=change),
                self.assertRaisesRegex(InputError, "Giga"),
            ):
                compile_full_battle(*altered, self.catalog)
        raw = compile_full_battle(*inputs, self.catalog)["compiled"]["scene"]
        raw["traps"][0]["parameters"]["unit_responses"].pop("reserve")
        with self.assertRaisesRegex(InputError, "cover all attacking units"):
            simulate_spatial(raw)


if __name__ == "__main__":
    unittest.main()
