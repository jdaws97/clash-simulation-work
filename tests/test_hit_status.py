"""Attack work, expiry and Ice Golem deaths across coupled combat systems."""

from copy import deepcopy
from pathlib import Path
from math import nextafter
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.hit_status import HitStatusCombat, RULES, RULESET, SCOPE
from clashlab.spatial import _load_actors, simulate_spatial

from test_adapters import entity_instance
from test_deaths import damage
from test_spatial import synthetic_structure, synthetic_unit
from test_townhalls import hazard, town_hall_sector
from test_traps import trap_scene


SOURCE = "synthetic-chill-timing-not-current-game-calibration"


def slow(**changes):
    model = {
        "source": SOURCE,
        "duration_seconds": 2,
        "attack_rate_multiplier": 0.25,
        "movement_multiplier": 1,
        "protection_policy": "damage_immunity_does_not_block_status",
    }
    model.update(changes)
    return model


def ice_instance(**changes):
    return entity_instance(
        "ice",
        "ice-golem",
        8,
        "attack",
        wall_parameters={"kind": "avoid", "source": SOURCE},
        ice_parameters={
            "source": SOURCE,
            "on_hit_slow": slow(),
            "death_delay_seconds": 0,
            "death_radius_multiplier": 1,
            "death_duration_multiplier": 1,
            "death_target_kinds": ["defense", "building"],
            "death_target_layers": ["ground"],
        },
        **changes,
    )


def status_scene(actors=None, effects=None, **changes):
    if actors is None:
        actors = [
            synthetic_unit(
                x=6.5,
                damage=1,
                hitpoints=10000,
                attack_interval_seconds=100,
                on_hit_status=slow(),
            ),
            synthetic_structure(damage=1, range=10, hitpoints=10000),
        ]
    scene = trap_scene({}, actors, effects, traps=[])
    scene.update(
        ruleset=RULESET,
        model_rules=deepcopy(RULES),
        duration_seconds=5,
        maximum_step_seconds=1,
    )
    scene.update(changes)
    return scene


def launches(result, actor_id):
    return [
        round(event["time_seconds"], 8)
        for event in result["trace"]
        if event.get("event") == "projectile_launch" and event["source"] == actor_id
    ]


class HitStatusTests(unittest.TestCase):
    def test_neighboring_observation_preserves_slow_until_exact_shared_expiry(self):
        for before in (2 - 5e-11, nextafter(2, 0)):
            scene = status_scene(
                recording_interval_seconds=before, maximum_step_seconds=before
            )
            actors = _load_actors(scene, scene["width"], scene["height"])
            runtime = HitStatusCombat(actors)
            trace = []
            source = scene["actors"][0]["id"]
            runtime.impact(
                {"source": source, "on_hit_status": slow()},
                actors["tower"],
                actors,
                0,
                trace,
            )
            runtime.prepare(actors, 0, trace)
            runtime.prepare(actors, before, trace)
            self.assertEqual(actors["tower"]["_hit_status_attack_rate"], 0.25)
            self.assertEqual(runtime.next_boundary(), 2)
            runtime.prepare(actors, 2, trace)
            self.assertEqual(actors["tower"]["_hit_status_attack_rate"], 1)
            self.assertIsNone(runtime.next_boundary())
            result = simulate_spatial(scene)
            expiries = [
                e
                for e in result["trace"]
                if e.get("event") == "hit_status_change"
                and e["target"] == "tower"
                and not e["sources"]
            ]
            self.assertEqual([e["time_seconds"] for e in expiries], [2])
            self.assertEqual(launches(result, "tower"), [0, 2.5, 3.5, 4.5])

    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")

    def test_expiry_preserves_unfinished_attack_work_and_splits_solver_steps(self):
        for step in (0.01, 1):
            with self.subTest(step=step):
                result = simulate_spatial(status_scene(maximum_step_seconds=step))
                self.assertEqual(launches(result, "tower"), [0, 2.5, 3.5, 4.5])
                self.assertEqual(result["hit_statuses"], [])

    def test_two_slows_do_not_multiply_and_weaker_slow_resumes(self):
        scene = status_scene(duration_seconds=5)
        scene["actors"][0]["on_hit_status"] = slow(duration_seconds=1)
        second = deepcopy(scene["actors"][0])
        second.update(
            id="second",
            on_hit_status=slow(attack_rate_multiplier=0.5, duration_seconds=4),
        )
        scene["actors"].append(second)
        result = simulate_spatial(scene)
        self.assertEqual(launches(result, "tower"), [0, 2.5, 4.25])

    def test_repeated_hits_refresh_duration_without_compounding_strength(self):
        scene = status_scene(duration_seconds=5)
        scene["actors"][0]["attack_interval_seconds"] = 1
        result = simulate_spatial(scene)
        self.assertEqual(launches(result, "tower"), [0, 4])
        self.assertEqual(len(result["hit_statuses"]), 1)
        self.assertEqual(result["hit_statuses"][0]["expires_at"], 7)

    def test_freeze_pauses_slowed_work_and_expiry_during_freeze_is_exact(self):
        effect = {
            "id": "freeze-tower",
            "kind": "freeze",
            "time_seconds": 1,
            "targets": ["tower"],
            "duration_seconds": 3,
        }
        result = simulate_spatial(status_scene(effects=[effect]))
        self.assertEqual(launches(result, "tower"), [0, 4.75])

    def test_immunity_policy_controls_status_without_changing_blocked_damage(self):
        protection = {
            "id": "protect",
            "kind": "invulnerability",
            "time_seconds": 0,
            "targets": ["tower"],
            "duration_seconds": 5,
        }
        for blocks, expected in (
            (True, [0, 1, 2, 3, 4, 5]),
            (False, [0, 2.5, 3.5, 4.5]),
        ):
            scene = status_scene(effects=[protection])
            if blocks:
                scene["actors"][0]["on_hit_status"][
                    "protection_policy"
                ] = "damage_immunity_also_blocks_status"
            result = simulate_spatial(scene)
            self.assertEqual(result["actors"]["tower"]["hp"], 10000)
            self.assertEqual(launches(result, "tower"), expected)

    def test_existing_chill_survives_source_death(self):
        scene = status_scene(effects=[damage(time=0.5)])
        witness = synthetic_unit("witness", x=6.5, damage=0, hitpoints=10000, range=0)
        # Rebuild through the fixture so the added actor receives its pattern and classes.
        scene = status_scene([*scene["actors"], witness], scene["effects"])
        result = simulate_spatial(scene)
        self.assertEqual(result["actors"]["attacker"]["death_time"], 0.5)
        self.assertEqual(launches(result, "tower"), [0, 2.5, 3.5, 4.5])

    def test_released_slow_projectile_survives_source_death(self):
        scene = status_scene(effects=[damage(time=0.5)], duration_seconds=4)
        scene["actors"][0]["attack_model"]["projectile"].update(
            timing="launch_distance_delay",
            speed_tiles_per_second=1,
        )
        witness = deepcopy(scene["actors"][0])
        witness.update(id="witness", damage=0, range=0)
        witness["attack_model"] = {"kind": "none", "source": SOURCE}
        witness.pop("on_hit_status")
        scene["actors"].append(witness)
        result = simulate_spatial(scene)
        applications = [
            event
            for event in result["trace"]
            if event.get("event") == "hit_status_apply"
        ]
        self.assertEqual(len(applications), 1)
        self.assertEqual(applications[0]["time_seconds"], 1)
        self.assertEqual(launches(result, "tower"), [0, 1, 3.5])

    def test_hit_slow_composes_with_poison_without_double_rescaling(self):
        attacker = synthetic_unit(x=6.5, damage=1, hitpoints=10000)
        tower = synthetic_structure(
            damage=1,
            range=10,
            hitpoints=10000,
            attack_interval_seconds=100,
            on_hit_status=slow(),
        )
        scene = status_scene([attacker, tower])
        field = hazard(
            duration_seconds=2,
            maximum_dps=0,
            attack_rate_multiplier=0.5,
            movement_multiplier=1,
        )
        field["area"].update(x=6.5, y=3.5, radius=10)
        scene["persistent_hazards"] = [field]
        result = simulate_spatial(scene)
        self.assertEqual(launches(result, "attacker"), [0, 2.75, 3.75, 4.75])

    def test_movement_slow_expires_at_boundary(self):
        mover = synthetic_unit(x=0.5, damage=1, hitpoints=10000, speed=2)
        tower = synthetic_structure(
            range=10,
            damage=1,
            attack_interval_seconds=100,
            on_hit_status=slow(attack_rate_multiplier=1, movement_multiplier=0.5),
        )
        result = simulate_spatial(status_scene([mover, tower], duration_seconds=3))
        self.assertAlmostEqual(result["actors"]["attacker"]["x"], 4.5)

    def test_ice_golem_adapter_preserves_stats_and_freezes_on_actual_death(self):
        tower = entity_instance("tower", "cannon", 21, "defense")
        scene = town_hall_sector(
            self.catalog, [ice_instance(), tower], [damage("ice", time=0.5)]
        )
        scene.update(
            scope=SCOPE, model_rules=deepcopy(RULES), traps=[], duration_seconds=1
        )
        compiled = compile_entity_scene(scene, self.catalog)["scene"]
        ice = compiled["actors"][0]
        self.assertEqual(ice["hitpoints"], 4200)
        self.assertEqual(ice["damage"], 104)
        self.assertEqual(ice["target_priority_tiers"], [["defense"], ["building"]])
        result = simulate_spatial(compiled)
        self.assertEqual(result["actors"]["tower"]["frozen_until"], 9)
        self.assertEqual(result["death_effects"]["emitted_instances"], ["ice"])

    def test_legacy_scope_cannot_silently_omit_ice_golem_lifecycle(self):
        scene = town_hall_sector(
            self.catalog,
            [ice_instance(), entity_instance("tower", "cannon", 21, "defense")],
        )
        with self.assertRaisesRegex(InputError, "Ice Golem requires"):
            compile_entity_scene(scene, self.catalog)

    def test_invalid_zero_rate_is_rejected(self):
        scene = status_scene()
        scene["actors"][0]["on_hit_status"]["attack_rate_multiplier"] = 0
        with self.assertRaises(InputError):
            simulate_spatial(scene)


if __name__ == "__main__":
    unittest.main()
