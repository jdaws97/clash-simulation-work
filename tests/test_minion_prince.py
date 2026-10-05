"""Prince equipment mappings and continuous Dark Orb contacts."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError
from clashlab.damage_receipts import DamageReceipts
from clashlab.hit_status import HitStatusCombat
from clashlab.minion_prince import (
    MinionPrinceCombat,
    compile_prince_equipment,
    validate_prince_equipment,
)
from clashlab.spatial import _load_actors

from test_dragon_duke import projectile
from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "declared-prince-behavior-fixture-not-game-calibration"


def prince_equipment(entity, level):
    parameters = {"source": SOURCE}
    if entity == "metal-pants":
        parameters.update(
            reduction_mapping="snapshot_numeric_percent_reduction_hypothesis",
            freeze="duration_continues_while_frozen",
            stacking="multiply_independent_incoming_damage_factors",
        )
    elif entity == "noble-iron":
        parameters.update(
            attack_speed_mapping="snapshot_numeric_percent_attack_rate_bonus_hypothesis",
            count_policy="spend_one_per_main_weapon_launch_including_misses",
            trigger="first_launches_after_actual_deployment",
            stacking="add_profile_scaled_hit_damage_multiply_independent_attack_rate",
        )
    elif entity == "dark-orb":
        parameters.update(
            direction="captured_retained_target_center_or_explicit_fallback",
            fallback_unit_vector={"x": 1, "y": 0},
            travel_distance_tiles=20,
            radius_tiles=0.5,
            projectile_speed_tiles_per_second=4,
            release_delay_seconds=0,
            geometry="moving_circle_to_target_footprint_hypothesis",
            target_kinds=["unit", "defense", "building", "wall"],
            target_layers=["ground", "air"],
            hit_policy="one_contact_per_target_then_expire_after_final_position",
            obstacles="passes_through_buildings_and_walls",
            visibility="released_orb_ignores_invisibility_but_excludes_hidden_teslas",
            protection_policy="damage_immunity_also_blocks_status",
            slow_mapping="snapshot_percent_reduction_of_movement_and_attack_rate_hypothesis",
            source_death="released_orb_and_slow_persist",
            freeze="released_orb_continues_while_source_frozen",
            damage_scaling="equipment_flat_damage_times_hero_profile_only_hypothesis",
        )
    return {"entity": entity, "level": level, "parameters": parameters}


def prince_actor(catalog, items=None, **changes):
    if items is None:
        items = [prince_equipment("metal-pants", 5), prince_equipment("dark-orb", 12)]
    models = [
        compile_prince_equipment(
            item, {"entity": "minion-prince", "town_hall": 16}, catalog
        )[0]
        for item in items
    ]
    actor = synthetic_unit(
        "prince",
        x=0.5,
        y=5,
        range=4.5,
        layer="air",
        movement="air",
        damage=561.85,
        hitpoints=3224,
        attack_interval_seconds=0.85,
        target_layers=["ground", "air"],
        target_priorities=["defense", "building"],
        healing_class="hero",
        hazard_class="hero",
        buff_class="hero",
        attack_model={
            "kind": "single",
            "source": SOURCE,
            "target_kinds": ["defense", "building"],
            "target_layers": ["ground", "air"],
            "maximum_hp_fraction": 0,
            "projectile": projectile(2),
        },
        hero_model={
            "entity": "minion-prince",
            "equipment": models,
            "damage_multiplier": 1,
            "range_multiplier": 1,
        },
    )
    actor.update(changes)
    return actor


def runtime(catalog, others=None, items=None, changes=None):
    actors = _load_actors(
        {"actors": [prince_actor(catalog, items, **(changes or {})), *(others or [])]},
        50,
        50,
    )
    for actor in actors.values():
        actor["minimum_range"] = 0
        if "attack_model" not in actor:
            actor["attack_model"] = {"kind": "none", "source": SOURCE}
            actor["damage"] = 0
    combat = PatternCombat(actors)
    status = HitStatusCombat(actors)
    return actors, combat, status, MinionPrinceCombat(actors, combat, status)


class MinionPrinceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_source_rows_and_parameter_specific_provenance(self):
        actor = prince_actor(self.catalog)
        pants, orb = actor["hero_model"]["equipment"]
        self.assertEqual(pants["incoming_damage_multiplier"], 0.5)
        self.assertEqual(pants["duration_seconds"], 10)
        self.assertEqual(
            (
                orb["projectile_damage"],
                orb["slow_multiplier"],
                orb["slow_duration_seconds"],
            ),
            (100, 0.6, 13),
        )
        self.assertEqual(
            orb["source_description"], self.catalog.entity("dark-orb")["description"]
        )
        self.assertEqual(
            orb["parameter_provenance"]["radius_tiles"],
            {"source": SOURCE, "status": "explicit_uncalibrated_hypothesis"},
        )
        iron = compile_prince_equipment(
            prince_equipment("noble-iron", 1),
            {"entity": "minion-prince", "town_hall": 16},
            self.catalog,
        )[0]
        self.assertEqual(
            (
                iron["damage_per_hit_increase"],
                iron["boosted_launches"],
                iron["attack_range"],
            ),
            (350, 5, 10),
        )
        self.assertAlmostEqual(iron["attack_rate_multiplier"], 1.06)

    def test_unknown_numeric_mapping_hidden_geometry_and_missing_summons_rejected(self):
        model = prince_actor(self.catalog)["hero_model"]["equipment"][0]
        model["parameters"]["reduction_mapping"] = "numeric_means_flat_damage_block"
        with self.assertRaises(InputError):
            validate_prince_equipment(model)
        for name in ("dark-crown", "henchmen-puppet"):
            with self.assertRaises(InputError):
                compile_prince_equipment(
                    prince_equipment(name, 1),
                    {"entity": "minion-prince", "town_hall": 16},
                    self.catalog,
                )
        orb = prince_equipment("dark-orb", 12)
        orb["parameters"]["fallback_unit_vector"] = {"x": 2, "y": 0}
        with self.assertRaisesRegex(InputError, "unit vector"):
            compile_prince_equipment(
                orb, {"entity": "minion-prince", "town_hall": 16}, self.catalog
            )

    def test_pants_shared_activation_mitigation_and_frozen_expiry(self):
        actors, _, _, prince = runtime(self.catalog)
        actor = actors["prince"]
        prince.activate("prince", actors, 1, [])
        self.assertFalse(prince.activate("prince", actors, 1, []))
        actor["frozen_until"] = 20
        prince.prepare(actors, 1, [])
        value = DamageReceipts().register(
            actor, 100, 1, source_id="cannon", source_team="defense", origin="weapon"
        )
        self.assertEqual(value, 50)
        prince.prepare(actors, 11, [])
        self.assertEqual(actor["_hero_incoming_damage_multiplier"], 1)

    def test_noble_iron_five_launches_preserve_captured_projectile_boosts(self):
        items = [prince_equipment("metal-pants", 5), prince_equipment("noble-iron", 1)]
        actors, combat, _, prince = runtime(
            self.catalog,
            [synthetic_structure("target", x=8, y=5, hitpoints=10000)],
            items,
        )
        actor = actors["prince"]
        actor["next_attack"] = 0.85
        prince.prepare(actors, 0, [])
        self.assertAlmostEqual(actor["next_attack"], 0.85 / 1.06)
        self.assertEqual(actor["range"], 10)
        for index in range(5):
            combat.launch(actor, actors["target"], actors, index, [])
            prince.weapon_launched("prince", index, [])
            actor["next_attack"] = index + 0.85 / 1.06
            prince.prepare(actors, index, [])
        self.assertEqual(prince.iron_remaining["prince"], 0)
        self.assertEqual(actor["range"], 4.5)
        self.assertAlmostEqual(actor["damage"], 561.85)
        self.assertAlmostEqual(actor["next_attack"], 4.85)
        self.assertTrue(
            all(
                abs(packet[2]["flat_damage"] - 911.85) < 1e-8
                for packet in combat.pending
            )
        )

    def test_controlled_prince_does_not_start_opening_boost_early(self):
        items = [prince_equipment("metal-pants", 5), prince_equipment("noble-iron", 1)]
        actors, _, _, prince = runtime(
            self.catalog, items=items, changes={"spawn_seconds": "controlled"}
        )
        actor = actors["prince"]
        prince.prepare(actors, 0, [])
        self.assertNotIn("_hero_attack_rate", actor)
        actor.update(spawn_seconds=2, next_attack=2.85)
        prince.prepare(actors, 2, [])
        self.assertAlmostEqual(actor["next_attack"], 2 + 0.85 / 1.06)
        self.assertEqual(prince.iron_remaining["prince"], 5)

    def test_orb_first_contact_is_analytic_and_step_invariant(self):
        times = []
        for step in (0.01, 0.8):
            actors, _, status, prince = runtime(
                self.catalog, [synthetic_structure("target", x=8, y=5, hitpoints=10000)]
            )
            trace = []
            prince.activate("prince", actors, 0, trace)
            time = 0
            total_damage = 0
            while time <= 5 + 1e-9:
                total_damage += prince.resolve(actors, time, trace)["target"]
                status.prepare(actors, time, trace)
                if time >= 5 - 1e-9:
                    break
                horizon = min(step, 5 - time)
                crossing = prince.first_crossing_delay(actors, {}, {}, time, horizon)
                time += horizon if crossing is None else crossing
            contact = [entry for entry in trace if entry["event"] == "dark_orb_contact"]
            self.assertEqual(len(contact), 1)
            self.assertEqual(total_damage, 100)
            times.append(contact[0]["time_seconds"])
        self.assertAlmostEqual(times[0], 1.75)
        self.assertAlmostEqual(times[1], 1.75)

    def test_orb_relative_contact_catches_fast_moving_target(self):
        target = synthetic_unit("target", team="defense", x=10, y=5)
        actors, _, _, prince = runtime(self.catalog, [target])
        prince.activate("prince", actors, 0, [])
        crossing = prince.first_crossing_delay(
            actors, {"target": [(0, 5)]}, {"target": 2}, 0, 2
        )
        self.assertAlmostEqual(crossing, 1.5)
        actors["target"]["x"] = 7
        self.assertEqual(prince.resolve(actors, crossing, [])["target"], 100)

    def test_orb_capture_direction_delay_and_flight_ignore_source_death_and_freeze(
        self,
    ):
        item = prince_equipment("dark-orb", 12)
        item["parameters"]["release_delay_seconds"] = 0.5
        actors, _, _, prince = runtime(
            self.catalog,
            [synthetic_structure("target", x=0, y=10)],
            [prince_equipment("metal-pants", 5), item],
        )
        actors["prince"]["target"] = "target"
        prince.activate("prince", actors, 0, [])
        self.assertEqual(prince.orbs[0]["direction"], (0, 1))
        actors["prince"].update(x=30, y=30, hp=0, death_time=0.2, frozen_until=100)
        self.assertEqual(prince.resolve(actors, 0.4, [])["target"], 0)
        self.assertEqual(prince.resolve(actors, 1.625, [])["target"], 100)

    def test_orb_applies_one_slow_and_preserves_remaining_frozen_attack_work(self):
        actors, _, status, prince = runtime(
            self.catalog, [synthetic_structure("target", x=8, y=5)]
        )
        target = actors["target"]
        target.update(frozen_until=3, next_attack=4)
        prince.activate("prince", actors, 0, [])
        prince.resolve(actors, 1.75, [])
        status.prepare(actors, 1.75, [])
        self.assertAlmostEqual(target["next_attack"], 3 + 1 / 0.6)
        self.assertEqual(target["_hit_status_movement_multiplier"], 0.6)
        self.assertEqual(prince.resolve(actors, 1.76, [])["target"], 0)
        self.assertEqual(status.exposures[("target", "prince")]["expires_at"], 14.75)

    def test_protection_policy_controls_slow_without_allowing_damage(self):
        for policy, should_slow in (
            ("damage_immunity_also_blocks_status", False),
            ("damage_immunity_does_not_block_status", True),
        ):
            orb = prince_equipment("dark-orb", 12)
            orb["parameters"]["protection_policy"] = policy
            actors, _, status, prince = runtime(
                self.catalog,
                [synthetic_structure("target", x=8, y=5)],
                [prince_equipment("metal-pants", 5), orb],
            )
            actors["target"]["immune_until"] = 10
            prince.activate("prince", actors, 0, [])
            self.assertEqual(prince.resolve(actors, 1.75, [])["target"], 0)
            self.assertEqual(bool(status.exposures), should_slow)

    def test_dark_orb_passes_walls_but_ignores_declared_unit_collateral(self):
        targets = [
            synthetic_structure(
                "wall", x=4, y=5, kind="wall", counts_for_destruction=False
            ),
            synthetic_structure("behind", x=8, y=5),
            synthetic_unit("defender", team="defense", x=8, y=5),
        ]
        actors, _, _, prince = runtime(self.catalog, targets)
        actors["prince"]["attack_model"]["defending_unit_collateral_policy"] = "ignore"
        prince.activate("prince", actors, 0, [])
        self.assertEqual(prince.resolve(actors, 0.75, [])["wall"], 100)
        damage = prince.resolve(actors, 1.75, [])
        self.assertEqual(damage["behind"], 100)
        self.assertEqual(damage["defender"], 0)

    def test_final_orb_position_contacts_then_expires(self):
        orb = prince_equipment("dark-orb", 12)
        orb["parameters"]["travel_distance_tiles"] = 2
        target = synthetic_structure("target", x=3, y=5)
        actors, _, _, prince = runtime(
            self.catalog, [target], [prince_equipment("metal-pants", 5), orb]
        )
        prince.activate("prince", actors, 0, [])
        self.assertEqual(prince.resolve(actors, 0.5, [])["target"], 100)
        self.assertEqual(prince.result()["pending_dark_orbs"], 0)
        self.assertEqual(prince.resolve(actors, 1, [])["target"], 0)


if __name__ == "__main__":
    unittest.main()
