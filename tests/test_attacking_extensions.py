"""Bounded cross-lifecycle checks; all child stats and geometry are synthetic."""

import unittest
from copy import deepcopy

from clashlab.common import InputError
from clashlab.combat import PatternCombat
from clashlab.spatial import _active, _apply_health, _load_actors
from clashlab.troop_behaviors import (
    AttackingTroopCombat,
    compile_troop_behavior,
    troop_damage_immune,
)
from clashlab.troop_projectiles import TroopLineCombat, compile_line_weapon
from clashlab.troop_summons import (
    TroopSummonCombat,
    compile_summon_model,
    compile_troop_reserves,
)

from test_spatial import synthetic_scene, synthetic_structure, synthetic_unit
from test_adapters import projectile


SOURCE = "synthetic-attacking-extension-contract-not-game-calibration"


def unit(key, **changes):
    actor = synthetic_unit(
        key,
        x=1.5,
        y=1.5,
        damage=20,
        range=2,
        minimum_range=0,
        target_priorities=["defense", "building"],
    )
    actor["attack_model"] = {
        "kind": "single",
        "source": SOURCE,
        "target_kinds": ["defense", "building"],
        "target_layers": ["ground"],
        "maximum_hp_fraction": 0,
        "projectile": projectile(),
    }
    actor.update(changes)
    return actor


def summon_parameters(trigger, count=2, **changes):
    model = {
        "source": SOURCE,
        "statistics_status": "explicit_uncalibrated_hypothesis",
        "trigger": trigger,
        "first_delay_seconds": 0,
        "interval_seconds": 7,
        "release_delay_seconds": 0.1,
        "batch_size": 1,
        "live_cap": 1,
        "total_cap": count,
        "damage_threshold": 20,
        "split_hp_fraction": 0.5,
        "death_remainder": "none",
        "freeze_policy": "skip_due_batches_clock_continues",
        "pending_source_loss": "released_batches_survive",
        "reserve_policy": "finite_precompiled_never_reuse_dead_actor",
        "lifetime_seconds": 0,
        "children": [
            {
                "actor": unit("child-" + str(index)),
                "offset_x": index * 0.1,
                "offset_y": 0,
                "source": SOURCE,
                "statistics_status": "explicit_uncalibrated_hypothesis",
            }
            for index in range(count)
        ],
    }
    model.update(changes)
    return model


def load(raw):
    return _load_actors(synthetic_scene(raw), 9, 7)


class AttackingExtensionsTests(unittest.TestCase):
    def test_death_split_survives_blocked_release_and_children_attack(self):
        parent = unit("parent")
        compile_summon_model(
            parent,
            {"summon_parameters": summon_parameters("actual_death")},
            {"id": "golem"},
            {"golemitesSpawned": 2},
        )
        target = synthetic_structure(
            "tower",
            x=2,
            y=1,
            hitpoints=200,
            minimum_range=0,
            attack_model={"kind": "none", "source": SOURCE},
        )
        actors = load([parent, target, *compile_troop_reserves([parent])])
        clear = [False]
        runtime = TroopSummonCombat(actors, lambda *args: clear[0])
        trace = []
        runtime.prepare(0, trace)
        actors["parent"].update(hp=0, death_time=0.2)
        runtime.prepare(0.2, trace)
        runtime.prepare(0.4, trace)
        self.assertEqual(len(runtime.pending), 2)
        self.assertEqual(len(runtime.continuation_reasons(0.4)), 2)
        clear[0] = True
        runtime.prepare(0.5, trace)
        runtime.prepare(0.5, trace)
        self.assertEqual(len(runtime.releases), 2)
        self.assertTrue(_active(actors["child-0"], 0.5))
        combat = PatternCombat(actors)
        combat.launch(actors["child-0"], actors["tower"], actors, 0.5, trace)
        damage = combat.resolve(actors, 0.5, trace)
        self.assertEqual(damage["tower"], 20)
        with self.assertRaises(InputError):
            runtime.validate_command({"kind": "deploy", "targets": ["child-0"]})

    def test_live_cap_replacement_and_freeze_clock(self):
        parent = unit("parent")
        compile_summon_model(
            parent,
            {"summon_parameters": summon_parameters("periodic")},
            {"id": "super-witch"},
            {},
        )
        actors = load([parent, *compile_troop_reserves([parent])])
        runtime = TroopSummonCombat(actors, lambda *args: True)
        trace = []
        for time in (0, 0.1, 7):
            runtime.prepare(time, trace)
        self.assertEqual(len(runtime.releases), 1)
        actors["child-0"].update(hp=0, death_time=8)
        actors["parent"]["frozen_until"] = 15
        runtime.prepare(14, trace)
        self.assertEqual(runtime.next_boundary(14), 21)
        runtime.prepare(21, trace)
        runtime.prepare(21.1, trace)
        self.assertEqual(len(runtime.releases), 2)
        self.assertIsNone(runtime.next_boundary(22))

    def test_effective_damage_budget_and_parent_death_once(self):
        parent = unit("parent")
        compile_summon_model(
            parent,
            {
                "summon_parameters": summon_parameters(
                    "damage_threshold",
                    count=3,
                    live_cap=3,
                    death_remainder="release_remaining",
                )
            },
            {"id": "yeti"},
            {},
        )
        actors = load([parent, *compile_troop_reserves([parent])])
        runtime = TroopSummonCombat(actors, lambda *args: True)
        trace = []
        runtime.prepare(0, trace)
        runtime.record_damage("parent", 45)
        runtime.prepare(1, trace)
        self.assertEqual(len(runtime.pending), 2)
        actors["parent"].update(hp=0, death_time=1)
        runtime.prepare(1, trace)
        runtime.prepare(1.1, trace)
        runtime.prepare(2, trace)
        self.assertEqual(len(runtime.releases), 3)

    def test_burrow_surface_and_finite_ammunition(self):
        miner = unit("miner")
        features = {
            "burrow": {
                "transition": "burrow_when_out_of_weapon_range_surface_in_range",
                "damage": "immune_underground_including_existing_projectiles",
                "traps": "do_not_trigger_underground",
                "wall_policy": "ignore_enemy_walls_preserve_other_obstacles",
            }
        }
        compile_troop_behavior(
            miner,
            {
                "troop_behavior_parameters": {
                    "source": SOURCE,
                    "status": "explicit_uncalibrated_hypothesis",
                    "features": features,
                }
            },
            {"id": "miner"},
            {},
            {},
        )
        actors = load([miner, synthetic_structure("tower", x=7, y=1)])
        runtime = AttackingTroopCombat(actors)
        runtime.prepare(0, lambda actor: actors["tower"], [])
        self.assertTrue(troop_damage_immune(actors["miner"]))
        actors["miner"]["x"] = 6
        runtime.prepare(1, lambda actor: actors["tower"], [])
        self.assertFalse(troop_damage_immune(actors["miner"]))
        minion = unit("minion")
        compile_troop_behavior(
            minion,
            {
                "troop_behavior_parameters": {
                    "source": SOURCE,
                    "status": "explicit_uncalibrated_hypothesis",
                    "features": {
                        "ammunition": {
                            "shots": 2,
                            "range_tiles": 8,
                            "damage_multiplier": 2,
                            "consumption": "weapon_launch_including_fizzled_projectiles",
                        }
                    },
                }
            },
            {"id": "super-minion"},
            {},
            {},
        )
        actors = load([minion])
        runtime = AttackingTroopCombat(actors)
        runtime.prepare(0, lambda actor: None, [])
        self.assertEqual(runtime.launch_damage("minion"), 40)
        for time in (0, 1):
            runtime.on_launch("minion", time, [])
        runtime.prepare(2, lambda actor: None, [])
        self.assertEqual(actors["minion"]["range"], 2)
        self.assertEqual(runtime.launch_damage("minion"), 20)

    def test_boulder_packets_survive_source_and_primary_death(self):
        parent = unit("bowler")
        model = {
            "source": SOURCE,
            "status": "explicit_uncalibrated_hypothesis",
            "kind": "bounce",
            "distance_tiles": 8,
            "radius_tiles": 0.25,
            "speed_tiles_per_second": 2,
            "release_delay_seconds": 0,
            "bounce_offsets_tiles": [0, 3],
            "damage_multipliers": [1, 1],
            "membership": "live_at_each_impact",
            "repeats": "one_hit_per_actor_per_launch",
            "source_persistence": "released_projectile_survives",
        }
        compile_line_weapon(parent, {"line_weapon_parameters": model}, {"id": "bowler"})
        actors = load(
            [
                parent,
                synthetic_structure("first", x=3, y=1, hitpoints=200),
                synthetic_structure("second", x=6, y=1, hitpoints=200),
            ]
        )
        runtime = TroopLineCombat(actors)
        trace = []
        runtime.launch(actors["bowler"], actors["first"], 0, trace)
        actors["bowler"].update(hp=0, death_time=0)
        actors["first"].update(hp=0, death_time=0)
        runtime.resolve(1, trace)
        damage = runtime.resolve(3, trace)
        self.assertEqual(damage["second"], 20)
        self.assertEqual(len(runtime.resolved), 1)
        self.assertFalse(runtime.continuation_reasons(3))

    def test_moving_ramp_reset_preserves_weapon_cooldown_and_base_dps_mapping(self):
        actor = unit("inferno", attack_interval_seconds=0.25)
        parameters = {
            "source": SOURCE,
            "status": "explicit_uncalibrated_hypothesis",
            "features": {
                "ramp": {
                    "stage_seconds": [0, 2, 4],
                    "freeze": "reset",
                    "protection": "pause",
                    "clock": "first_launch_same_target_in_range",
                }
            },
        }
        compile_troop_behavior(
            actor,
            {"troop_behavior_parameters": parameters},
            {"id": "inferno-dragon", "attackSpeed": 0.5},
            {
                "stats": {
                    "normal": {"dps": 20},
                    "stage2": {"dps": 40},
                    "stage3": {"dps": 80},
                }
            },
            {"damage_multiplier": 1},
        )
        actors = load([actor, synthetic_structure("tower", x=2, y=1)])
        runtime = AttackingTroopCombat(actors)
        runtime.prepare(0, lambda actor: actors["tower"], [])
        self.assertEqual(runtime.launch_damage("inferno"), 10)
        runtime.on_launch("inferno", 0, [])
        actors["inferno"]["next_attack"] = 0.25
        self.assertEqual(runtime.next_boundary(0), 2)
        runtime.prepare(2, lambda actor: actors["tower"], [])
        self.assertEqual(runtime.launch_damage("inferno"), 20)
        actors["inferno"]["frozen_until"] = 5
        runtime.prepare(3, lambda actor: actors["tower"], [])
        self.assertEqual(runtime.launch_damage("inferno"), 10)
        self.assertEqual(actors["inferno"]["next_attack"], 0.25)

    def test_positive_sub_epsilon_release_is_not_discarded(self):
        parent = unit("parent")
        model = summon_parameters("actual_death", release_delay_seconds=1e-12)
        compile_summon_model(
            parent,
            {"summon_parameters": model},
            {"id": "golem"},
            {"golemitesSpawned": 2},
        )
        actors = load([parent, *compile_troop_reserves([parent])])
        runtime = TroopSummonCombat(actors, lambda *args: True)
        runtime.prepare(0, [])
        actors["parent"].update(hp=0, death_time=0)
        runtime.prepare(0, [])
        self.assertEqual(runtime.next_boundary(0), 1e-12)
        self.assertEqual(len(runtime.releases), 0)
        runtime.prepare(1e-12, [])
        self.assertEqual(len(runtime.releases), 2)


if __name__ == "__main__":
    unittest.main()
