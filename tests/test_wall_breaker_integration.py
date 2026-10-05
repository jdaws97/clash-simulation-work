"""Paid ordinary Wall Breaker lifecycle under explicit synthetic blast hypotheses."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.attacking_extensions import SCOPE
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial
from clashlab.wall_breakers import POLICIES
from test_adapters import entity_instance, projectile
from test_advanced_spell_integration import spell_battle
from test_battle_termination import classification, termination_policy
from test_full_battle import freeze_cast

SOURCE = "synthetic-wall-breaker-lifecycle-not-game-calibration"


def breaker_instance(actor_id="breaker", level=1, **changes):
    return entity_instance(
        actor_id,
        "wall-breaker",
        level,
        "attack",
        x=9.5,
        y=5.5,
        wall_parameters={"kind": "avoid", "source": SOURCE},
        attack_parameters={"radius": 2, "projectile": projectile()},
        attacking_extension_scope=SCOPE,
        troop_behavior_parameters={
            "source": SOURCE,
            "status": "explicit_uncalibrated_hypothesis",
            "features": {
                "wall": {"selection": "nearest_reachable_preferred_then_ordinary"},
                "suicide": {
                    "trigger": "successful_weapon_launch_once",
                    "death_damage_policy": "released_attack_only_suppress_death_blast_on_suicide",
                },
            },
        },
        wall_breaker_parameters={
            "source": SOURCE,
            "wall_damage_multiplier": 2,
            "death_radius_tiles": 2,
            **POLICIES,
        },
        **changes,
    )


def breaker_battle(catalog, step=0.25, killed_before_launch=False, freeze=False):
    inputs = spell_battle(catalog, "ice-block-spell", step=step, duration=3)
    spec, account, army, layout = inputs
    scene = spec["entity_scene"]
    scene.pop("advanced_spell_binding")
    scene["attack_spells"] = []
    scene["freeze_spells"] = [freeze_cast()] if freeze else []
    army["spells"] = [{"id": "freeze-spell", "level": 1, "count": 1}] if freeze else []
    army["troops"] = [{"id": "wall-breaker", "level": 1, "count": 1}]
    account["levels"]["wall-breaker"] = 1
    spec["termination_policy"] = termination_policy(
        [
            classification(
                {"origin": "army", "entity": "freeze-spell", "level": 1},
                "support_only",
                "ignore",
            )
        ]
        if freeze
        else []
    )
    scene["entities"] = [
        scene["entities"][0],
        breaker_instance(first_attack_seconds=1 if killed_before_launch else 0),
    ]
    wall = entity_instance(
        "wall",
        "wall",
        1,
        "defense",
        x=9,
        y=6,
        mode="passive",
        statistics_mode="none",
        counts_for_destruction=False,
        attack_parameters={},
        inactive_attack_interval_seconds=1,
    )
    scene["entities"].append(wall)
    layout["inventory"]["wall"] = 1
    layout["buildings"].append(
        {
            "instance": "wall",
            "id": "wall",
            "level": 1,
            "x": 9,
            "y": 6,
            "mode": "passive",
            "counts_for_destruction": False,
        }
    )
    return inputs


class WallBreakerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")

    def test_paid_contact_blast_consumes_once_targets_wall_and_never_adds_death_blast(
        self,
    ):
        for step in (0.017, 0.25):
            result = simulate_full_battle(
                *breaker_battle(self.catalog, step), self.catalog
            )
            combat = result["combat"]
            wall, hall = (combat["actors"][key] for key in ("wall", "hall"))
            self.assertEqual(wall["maximum_hp"] - wall["hp"], 20)
            self.assertEqual(hall["maximum_hp"] - hall["hp"], 10)
            launches = [
                e
                for e in combat["trace"]
                if e.get("event") == "projectile_launch"
                and e.get("source") == "breaker"
            ]
            self.assertEqual(len(launches), 1)
            self.assertEqual(launches[0]["target"], "wall")
            self.assertFalse(
                any(
                    e.get("event") == "death_effect_release"
                    and e.get("source") == "breaker"
                    for e in combat["trace"]
                )
            )
            self.assertEqual(combat["troop_behaviors"]["states"]["breaker"]["shots"], 1)
            self.assertEqual(combat["actors"]["breaker"]["death_time"], 0)
            self.assertEqual(
                result["resource_use"]["deployed_attacker_ids"], ["breaker"]
            )
            self.assertEqual(result["outcome"]["end_reason"], "attack_force_exhausted")
            self.assertEqual(result["outcome"]["elapsed_seconds"], 0)

    def test_prelaunch_hp_death_releases_separate_blast_freeze_control_preserves_attack(
        self,
    ):
        for step in (0.017, 0.25):
            for frozen in (False, True):
                result = simulate_full_battle(
                    *breaker_battle(self.catalog, step, True, frozen), self.catalog
                )
                combat = result["combat"]
                wall, hall = (combat["actors"][key] for key in ("wall", "hall"))
                self.assertEqual(wall["maximum_hp"] - wall["hp"], 20 if frozen else 12)
                self.assertEqual(hall["maximum_hp"] - hall["hp"], 10 if frozen else 6)
                self.assertEqual(
                    combat["troop_behaviors"]["states"]["breaker"]["shots"], int(frozen)
                )
                self.assertEqual(
                    result["outcome"]["elapsed_seconds"], 1 if frozen else 0
                )
                self.assertEqual(
                    sum(s["spent"] for s in result["resource_use"]["spell_slots"]),
                    int(frozen),
                )
                self.assertEqual(
                    result["outcome"]["end_reason"], "attack_force_exhausted"
                )

    def test_missing_policy_and_raw_detached_or_modified_owner_fail_closed(self):
        inputs = breaker_battle(self.catalog)
        raw = compile_full_battle(*inputs, self.catalog)["compiled"]["scene"]
        for field in ("wall_breaker_model", "troop_behavior_model", "death_model"):
            altered = deepcopy(raw)
            next(a for a in altered["actors"] if a["id"] == "breaker").pop(field)
            with self.assertRaisesRegex(InputError, "Wall Breaker requires"):
                simulate_spatial(altered)
        altered = deepcopy(raw)
        next(a for a in altered["actors"] if a["id"] == "breaker")["damage"] *= 2
        with self.assertRaisesRegex(InputError, "Wall Breaker requires"):
            simulate_spatial(altered)
        inputs[0]["entity_scene"]["entities"][1]["wall_breaker_parameters"].pop(
            "same_time_settlement"
        )
        with self.assertRaisesRegex(InputError, "complete blast"):
            compile_full_battle(*inputs, self.catalog)

    def test_paid_moving_contact_settles_destruction_before_force_exhaustion(self):
        outcomes = []
        for step in (0.017, 0.25):
            inputs = breaker_battle(self.catalog, step)
            hall, breaker, _ = inputs[0]["entity_scene"]["entities"]
            hall["town_hall_parameters"]["activation"].update(
                initial_state="dormant", activation_delay_seconds=100
            )
            hall["modifiers"]["hitpoints_multiplier"] = 0.0001
            breaker["x"] = 6.5
            result = simulate_full_battle(*inputs, self.catalog)
            self.assertEqual(
                result["outcome"]["end_reason"], "all_counted_buildings_destroyed"
            )
            self.assertGreater(result["outcome"]["elapsed_seconds"], 0)
            self.assertEqual(result["outcome"]["stars"], 3)
            self.assertEqual(
                result["combat"]["troop_behaviors"]["states"]["breaker"]["shots"], 1
            )
            outcomes.append(result["outcome"]["elapsed_seconds"])
        self.assertAlmostEqual(*outcomes)


if __name__ == "__main__":
    unittest.main()
