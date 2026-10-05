"""Paid TH16 attacks against one explicitly selected conditional TH18 Station."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.crafted_bindings import SHARED_POLICIES, SELECTION_FIELDS
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial
from test_adapters import entity_instance
from test_advanced_spell_integration import spell_battle
from test_battle_termination import termination_policy
from test_crafted_defenses import parameters, SOURCE
from test_full_battle import add_hero, deployment, freeze_cast
from test_guardians import guardian_instance, guardian_hall
from test_heroes import ability
from test_spell_lifecycle_integration import add_cast


def crafted_battle(catalog, variant, *, duration=4, step=0.25):
    inputs = spell_battle(catalog, "ice-block-spell", step=step, duration=duration)
    spec, account, army, layout = inputs
    scene = spec["entity_scene"]
    scene.pop("advanced_spell_binding")
    scene.update(attack_spells=[], width=50, height=28)
    spec["termination_policy"] = termination_policy()
    army.update(spells=[], troops=[{"id": "archer", "level": 1, "count": 1}])
    guardian = guardian_instance("longshot", x=39.5, y=21.5)
    guardian["guardian_parameters"]["home"] = {"x": 39.5, "y": 21.5}
    hall = guardian_hall(guardian, x=40, y=20)
    station = entity_instance(
        "station",
        "crafting-station",
        1,
        "defense",
        town_hall=18,
        x=6,
        y=4,
        attack_parameters={},
        crafted_parameters=parameters(variant),
        crafted_shared_binding={"source": SOURCE, **SHARED_POLICIES},
    )
    station["modifiers"]["hitpoints_multiplier"] = 0.00001
    archer = entity_instance(
        "army",
        "archer",
        1,
        "attack",
        x=2.5,
        y=5.5,
        wall_parameters={"kind": "avoid", "source": SOURCE},
    )
    scene["entities"] = [hall, guardian, station, archer]
    scene["defending_unit_responses"] = {
        "source": SOURCE,
        "actors": {"army": {"primary": "ignore", "collateral": "ignore"}},
    }
    layout.update(
        town_hall=18,
        width=50,
        height=28,
        inventory={"town-hall": 1, "crafting-station": 1},
        buildings=[
            {
                "instance": "hall",
                "id": "town-hall",
                "level": 18,
                "x": 40,
                "y": 20,
                "mode": "guardian",
                "counts_for_destruction": True,
                "settings": {
                    "guardian": {
                        "actor_id": "guardian",
                        "entity": "longshot",
                        "level": 1,
                    }
                },
            },
            {
                "instance": "station",
                "id": "crafting-station",
                "level": 1,
                "x": 6,
                "y": 4,
                "mode": "normal",
                "counts_for_destruction": True,
                "settings": {
                    "crafted": {
                        key: deepcopy(station["crafted_parameters"][key])
                        for key in SELECTION_FIELDS
                    }
                },
            },
        ],
    )
    return inputs


def add_troop(inputs, entity, actor_id, *, x=2.5, y=5.5, spawn=0):
    scene, account, army = inputs[0]["entity_scene"], inputs[1], inputs[2]
    unit = entity_instance(
        actor_id,
        entity,
        1,
        "attack",
        x=x,
        y=y,
        spawn_seconds=spawn,
        first_attack_seconds=100,
        **(
            {"wall_parameters": {"kind": "avoid", "source": SOURCE}}
            if entity != "minion"
            else {}
        ),
    )
    scene["entities"].append(unit)
    scene["defending_unit_responses"]["actors"][actor_id] = {
        "primary": "ignore",
        "collateral": "ignore",
    }
    account["levels"][entity] = 1
    entry = next((t for t in army["troops"] if t["id"] == entity), None)
    if entry:
        entry["count"] += 1
    else:
        army["troops"].append({"id": entity, "level": 1, "count": 1})
    return unit


class CraftedIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")

    def test_paid_cake_lands_after_station_death_and_bomb_hits_later_owned_deployment(
        self,
    ):
        for step in (0.017, 0.25):
            inputs = crafted_battle(self.catalog, "cake-a-pult", step=step)
            add_troop(inputs, "minion", "air", x=1.5)
            add_troop(inputs, "pekka", "late", spawn="controlled")
            command = deployment("late", 2.5)
            command["positions"]["late"] = {"x": 2.5, "y": 5.5}
            inputs[0]["entity_scene"]["effects"] = [command]
            result = simulate_full_battle(*inputs, self.catalog)
            combat = result["combat"]
            self.assertEqual(combat["actors"]["station"]["death_time"], 0)
            self.assertAlmostEqual(combat["actors"]["army"]["death_time"], 0.1)
            landings = [
                e for e in combat["trace"] if e.get("event") == "crafted_shot_impact"
            ]
            self.assertEqual({e["target"] for e in landings}, {"army", "air"})
            bombs = [
                e for e in combat["trace"] if e.get("event") == "crafted_bomb_impact"
            ]
            self.assertEqual([e["target"] for e in bombs], ["late"])
            self.assertEqual(bombs[0]["amount"], 400)
            self.assertAlmostEqual(bombs[0]["time_seconds"], 3.1)
            self.assertEqual(result["outcome"]["counted_building_count"], 2)
            self.assertEqual(result["outcome"]["destroyed_instance_ids"], ["station"])
            self.assertEqual(
                result["resource_use"]["deployed_attacker_ids"], ["air", "army", "late"]
            )
            self.assertEqual(combat["crafted_defenses"]["pending_count"], 0)

    def test_paid_hunter_selects_hero_and_poison_settles_at_hit_after_source_loss_with_protection_control(
        self,
    ):
        for protected in (False, True):
            inputs = crafted_battle(self.catalog, "hero-hunter", duration=3.2)
            add_hero(inputs[0], inputs[2], inputs[1], "grand-warden")
            warden = inputs[0]["entity_scene"]["entities"][-1]
            warden.update(x=1.5, y=6.5, first_attack_seconds=100)
            scene = inputs[0]["entity_scene"]
            scene["defending_unit_responses"]["actors"]["warden"] = {
                "primary": "ignore",
                "collateral": "ignore",
            }
            if protected:
                scene["effects"] = [ability("warden", 0)]
            result = simulate_full_battle(*inputs, self.catalog)
            combat = result["combat"]
            launches = [
                e for e in combat["trace"] if e.get("event") == "crafted_launch"
            ]
            self.assertEqual([e["targets"] for e in launches], [["warden"]])
            impacts = [
                e for e in combat["trace"] if e.get("event") == "crafted_shot_impact"
            ]
            self.assertEqual([e["target"] for e in impacts], ["warden"])
            self.assertEqual(impacts[0]["amount"], 0 if protected else 174)
            pulses = [
                e
                for e in combat["trace"]
                if e.get("event") == "hazard_pulse"
                and e["field"].startswith("crafted-poison-")
            ]
            self.assertAlmostEqual(pulses[0]["time_seconds"], 0.1)
            self.assertIn(
                "warden",
                pulses[0]["protected_targets"] if protected else pulses[0]["targets"],
            )
            slow = [
                e
                for e in combat["trace"]
                if e.get("event") == "hazard_status_change"
                and e.get("target") == "warden"
                and e["movement_multiplier"] < 1
            ]
            self.assertEqual(bool(slow), not protected)
            self.assertEqual(combat["actors"]["station"]["death_time"], 0)
            self.assertEqual(len(result["resource_use"]["deployed_attacker_ids"]), 2)

    def test_paid_candle_freeze_crosses_battle_zero_melt_and_launches_distinct_live_capacity(
        self,
    ):
        for step in (0.25, 1.7):
            inputs = crafted_battle(
                self.catalog, "hot-candle", duration=61.2, step=step
            )
            scene = inputs[0]["entity_scene"]
            station, archer = scene["entities"][2:4]
            station["modifiers"]["hitpoints_multiplier"] = 100
            station["first_attack_seconds"] = 58.5
            archer["first_attack_seconds"] = 100
            archer["modifiers"]["hitpoints_multiplier"] = 100
            scene["recording_interval_seconds"] = 5
            for i in range(6):
                unit = add_troop(
                    inputs,
                    "minion" if i % 2 else "archer",
                    "extra-" + str(i),
                    y=4.2 + i * 0.4,
                )
                unit["modifiers"]["hitpoints_multiplier"] = 100
            freeze = freeze_cast(time=58)
            freeze.update(x=7.5, y=5.5)
            add_cast(inputs, freeze)
            result = simulate_full_battle(*inputs, self.catalog)
            launches = [
                e
                for e in result["combat"]["trace"]
                if e.get("event") == "crafted_launch"
            ]
            self.assertEqual(len(launches), 1)
            self.assertAlmostEqual(launches[0]["time_seconds"], 61)
            self.assertEqual(len(set(launches[0]["targets"])), 4)
            self.assertEqual(
                {
                    result["combat"]["actors"][key]["layer"]
                    for key in launches[0]["targets"]
                },
                {"ground", "air"},
            )
            impacts = [
                e
                for e in result["combat"]["trace"]
                if e.get("event") == "crafted_shot_impact"
            ]
            self.assertEqual(len(impacts), 4)
            self.assertTrue(all(e["amount"] == 40 for e in impacts))
            self.assertEqual(len(result["resource_use"]["deployed_attacker_ids"]), 7)
            self.assertEqual(
                sum(s["spent"] for s in result["resource_use"]["spell_slots"]), 1
            )

    def test_range_entry_and_tiny_impact_clocks_are_exact_without_generic_fallback(
        self,
    ):
        for step in (0.017, 1.7):
            inputs = crafted_battle(self.catalog, "hero-hunter", step=step)
            station, archer = inputs[0]["entity_scene"]["entities"][2:4]
            station.update(x=16)
            station["modifiers"]["hitpoints_multiplier"] = 100
            archer.update(x=0.5, first_attack_seconds=100)
            inputs[3]["buildings"][1]["x"] = 16
            result = simulate_full_battle(*inputs, self.catalog)
            launches = [
                e
                for e in result["combat"]["trace"]
                if e.get("event") == "crafted_launch"
            ]
            self.assertEqual(len(launches), 1)
            self.assertAlmostEqual(launches[0]["time_seconds"], 2.5)
            self.assertAlmostEqual(result["outcome"]["elapsed_seconds"], 2.6)
        inputs = crafted_battle(self.catalog, "hero-hunter")
        inputs[0]["entity_scene"]["entities"][2]["crafted_parameters"][
            "projectile_delay_seconds"
        ] = 5e-11
        result = simulate_full_battle(*inputs, self.catalog)
        hits = [
            e
            for e in result["combat"]["trace"]
            if e.get("event") == "crafted_shot_impact"
        ]
        self.assertEqual(hits[0]["time_seconds"], 5e-11)
        self.assertEqual(result["outcome"]["elapsed_seconds"], 5e-11)
        self.assertFalse(
            any(
                e.get("event") == "projectile_launch" and e.get("source") == "station"
                for e in result["combat"]["trace"]
            )
        )

    def test_selected_layout_and_raw_model_require_matching_single_owner(self):
        inputs = crafted_battle(self.catalog, "cake-a-pult")
        raw = compile_full_battle(*inputs, self.catalog)["compiled"]["scene"]
        actor = next(a for a in raw["actors"] if a["id"] == "station")
        actor["crafted_defense_model"]["damage_per_hit"] *= 2
        with self.assertRaisesRegex(InputError, "compiled Station contract"):
            simulate_spatial(raw)
        inputs[3]["buildings"][1]["settings"]["crafted"]["as_of_date"] = "2026-10-03"
        with self.assertRaisesRegex(InputError, "Layout crafted selection"):
            compile_full_battle(*inputs, self.catalog)


if __name__ == "__main__":
    unittest.main()
