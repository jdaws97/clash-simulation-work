"""Bounded source/ownership crossings for remaining troop capabilities."""

import unittest

from clashlab.buffs import BUFF_CLASSES, BuffCombat, damage_multiplier
from clashlab.combat import PatternCombat
from clashlab.common import InputError
from clashlab.meteor_golems import (
    MeteorGolemCombat,
    compile_meteor_golem,
    compile_meteor_reserves,
)
from clashlab.ruin_witches import (
    RuinWitchCombat,
    compile_ruin_witch,
    compile_ruin_knights,
)
from clashlab.spatial import _active, _blocked, _select_target
from clashlab.troop_child_effects import TroopChildEffectCombat, compile_firemite_pool
from clashlab.troop_death_buffs import TroopDeathBuffCombat, compile_super_valkyrie

from test_attacking_extensions import SOURCE, load, unit
from test_spatial import synthetic_structure
from test_adapters import projectile


def knight(index):
    actor = unit("knight-" + str(index), range=1, buff_class="troop")
    actor["target_priority_tiers"] = [["defense", "building"]]
    actor["wall_behavior"] = {
        "kind": "clear_obstructions",
        "source": SOURCE,
        "route_cost": "travel_seconds_plus_nominal_clearance",
        "weapon": {
            "damage": 20,
            "range": 1,
            "attack_interval_seconds": 1,
            "first_attack_seconds": 0,
            "timing": "instant",
            "cooldown": "shared_with_main_weapon",
            "source": SOURCE,
        },
    }
    return {
        "actor": actor,
        "source": SOURCE,
        "status": "explicit_uncalibrated_hypothesis",
        "level": 4,
        "wall_damage_multiplier": 2,
    }


def ruin():
    actor = unit("ruin", range=1)
    parameters = {
        "source": SOURCE,
        "status": "explicit_uncalibrated_hypothesis",
        "behavior_revision": "august_2026_no_decay",
        "work_seconds": 4,
        "work_range_tiles": 1,
        "summon_delay_seconds": 2,
        "followthrough_seconds": 2,
        "maximum_knights": 10,
        "work_freeze": "pause_work",
        "after_consumption_clock": "absolute_continues_frozen_and_after_death",
        "rubble_geometry": "destroyed_building_footprint",
        "selection": "closest_reachable_footprint_then_instance_id",
        "reservation": "exclusive_at_work_start_consume_at_completion",
        "spawn_front_distance_tiles": 0.25,
        "fallback_facing_degrees": 0,
        "blocked_release": "wait_at_captured_front_point",
        "knight_hp_decay": "none",
        "children": [knight(index) for index in range(10)],
    }
    compile_ruin_witch(
        actor,
        {"ruin_parameters": parameters},
        {"id": "ruin-witch"},
        {
            "ruinKnightLevel": 4,
            "maximumRuinKnightsSummoned": 8,
            "stats": {"normal": {"damagePerShot": 56}},
        },
    )
    return actor


def meteor():
    actor = unit("meteor", range=5)
    actor["attack_model"] = {
        "kind": "radial",
        "source": SOURCE,
        "target_kinds": ["defense", "building"],
        "target_layers": ["ground"],
        "maximum_hp_fraction": 0,
        "radius": 0.5,
        "projectile": {
            "timing": "launch_distance_delay",
            "speed_tiles_per_second": 2,
            "delay_seconds": 0,
            "destination": "fixed_target_center_at_launch",
            "hit_radius": 0,
            "inactive_primary_policy": "resolve_at_fixed_launch_position",
        },
    }

    def child(key):
        return {
            "actor": unit(key),
            "source": SOURCE,
            "status": "explicit_uncalibrated_hypothesis",
            "level": 3,
        }

    parameters = {
        "source": SOURCE,
        "status": "explicit_uncalibrated_hypothesis",
        "group_id": "synthetic-meteor-cohort",
        "level": 3,
        "split_trigger": "successful_weapon_launch_once",
        "throw_speed_tiles_per_second": 2,
        "throw_release_delay_seconds": 0,
        "landing_position": "primary_center_at_launch_wait_if_blocked",
        "local_enemy_radius_tiles": 2,
        "merge_range_tiles": 1,
        "merge_delay_seconds": 1,
        "partner_policy": "nearest_same_level_cohort_if_no_local_enemy",
        "hp_policy": "split_keep_hp_fraction_merge_weighted_hp_fraction",
        "status_policy": "shared_transfer_preserves_angry_effect_and_targeting",
        "merge_position": "midpoint_wait_if_blocked",
        "reserve_exhaustion": "reject_merge_with_no_finite_reserve",
        "root_children": [child("mite-a"), child("mite-b")],
        "merge_forms": [
            {"id": "merged", "children": [child("next-a"), child("next-b")]}
        ],
    }
    compile_meteor_golem(
        actor,
        {"meteor_parameters": parameters},
        {"id": "meteor-golem", "dataId": 4000177},
        {"level": 3},
    )
    return actor


def tower(key="tower", **changes):
    return synthetic_structure(
        key, minimum_range=0, attack_model={"kind": "none", "source": SOURCE}, **changes
    )


def rage_field():
    return {
        "id": "template",
        "source": SOURCE,
        "statistics_source": SOURCE,
        "kind": "area_buff",
        "entity": "rage-spell",
        "start_seconds": 0,
        "duration_seconds": 2,
        "movement_bonus_tiles_per_second": 0,
        "damage_bonus_fraction": 1,
        "healing_bonus_fraction": 0,
        "membership_policy": "continuous_exact_crossings",
        "exit_linger_seconds": 0,
        "field_end_policy": "clear_immediately",
        "class_scaling": {
            key: {
                "damage_bonus_multiplier": 1,
                "movement_bonus_multiplier": 1,
                "healing_bonus_multiplier": 1,
            }
            for key in BUFF_CLASSES
        },
        "stacking_policy": "strongest_bonus_per_axis",
        "protection_policy": "beneficial_effects_ignore_damage_immunity",
        "source_persistence": "fixed_field_independent_of_caster",
        "area": {
            "x": 0,
            "y": 0,
            "radius": 3,
            "target_team": "attack",
            "target_kinds": ["unit"],
            "target_layers": ["ground", "air"],
        },
    }


class RemainingTroopTests(unittest.TestCase):
    def test_knight_reserves_enter_shared_wall_router_and_bad_cost_rejects(self):
        from clashlab.walls import WallRouting

        parent = ruin()
        actors = load([parent, *compile_ruin_knights([parent])])
        WallRouting(actors)
        self.assertEqual(actors["knight-0"]["wall_behavior"]["weapon"]["damage"], 40)
        self.assertTrue(actors["knight-0"]["_terminal_ground_approach"])
        parent["ruin_witch_model"]["children"][0]["actor"]["wall_behavior"][
            "route_cost"
        ] = "weapon_time_plus_travel"
        # Recompile the supplied explicit profile rather than silently rewriting it.
        with self.assertRaisesRegex(InputError, "route cost"):
            compile_ruin_witch(
                unit("bad-ruin"),
                {"ruin_parameters": parent["ruin_witch_model"]},
                {"id": "ruin-witch"},
                {"ruinKnightLevel": 4},
            )

    def test_ruin_consumption_pending_survives_death_and_blocked_spawn(self):
        raw = ruin()
        actors = load([raw, tower("rubble", x=2, y=1), *compile_ruin_knights([raw])])
        actors["rubble"].update(hp=0, death_time=0)
        clear = [False]
        runtime = RuinWitchCombat(actors, 9, 7, lambda *args: clear[0])
        trace = []
        runtime.prepare(0, trace)
        self.assertEqual(runtime.next_boundary(0), 4)
        runtime.prepare(4, trace)
        self.assertEqual(runtime.next_boundary(4), 6)
        actors["ruin"].update(hp=0, death_time=5)
        runtime.prepare(6, trace)
        self.assertEqual(len(runtime.continuation_reasons(6)), 1)
        clear[0] = True
        runtime.prepare(7, trace)
        runtime.prepare(7, trace)
        self.assertEqual(len(runtime.releases), 1)
        self.assertEqual(actors["knight-0"]["hp"], 100)
        runtime.prepare(20, trace)
        self.assertEqual(actors["knight-0"]["hp"], 100)
        self.assertEqual(actors["ruin"]["damage"], 0)
        self.assertEqual(actors["ruin"]["ruin_source_audit"]["selected_cap"], 10)

    def test_ruin_work_freeze_pause_and_cap_despawn_without_death(self):
        raw = ruin()
        rubble = [
            tower("rubble-" + str(index), x=2, y=1, blocking=False)
            for index in range(10)
        ]
        actors = load([raw, *rubble, *compile_ruin_knights([raw])])
        for actor in actors.values():
            if actor["id"].startswith("rubble-"):
                actor.update(hp=0, death_time=0)
        runtime = RuinWitchCombat(actors, 9, 7, lambda *args: True)
        runtime.prepare(0, [])
        actors["ruin"]["frozen_until"] = 3
        runtime.prepare(1, [])
        runtime.prepare(3, [])
        self.assertEqual(runtime.next_boundary(3), 6)
        runtime.prepare(6, [])
        runtime.prepare(8, [])
        runtime.prepare(10, [])
        for cycle in range(1, 10):
            runtime.prepare(10 + (cycle - 1) * 8 + 4, [])
            runtime.prepare(10 + (cycle - 1) * 8 + 6, [])
            runtime.prepare(10 + cycle * 8, [])
        self.assertEqual(len(runtime.releases), 10)
        self.assertEqual(runtime.states["ruin"]["phase"], "spent")
        self.assertIsNone(actors["ruin"]["death_time"])
        self.assertFalse(_active(actors["ruin"], 100))
        with self.assertRaises(InputError):
            runtime.validate_command({"kind": "deploy", "targets": ["ruin"]})

    def test_meteor_throw_merge_preserves_snapshot_angry_and_paid_identity(self):
        raw = meteor()
        actors = load(
            [raw, tower(x=4, y=1, hitpoints=200), *compile_meteor_reserves([raw])]
        )
        actors["meteor"].update(
            hp=60, _angry_until=17, _angry_cast="cast-1", _angry_target="tower"
        )

        def transfer(sources, recipient, time):
            winner = max(sources, key=lambda actor: actor.get("_angry_until", 0))
            if winner.get("_angry_until", 0) > time:
                for field in ("_angry_until", "_angry_cast", "_angry_target"):
                    recipient[field] = winner[field]

        combat = PatternCombat(actors)
        ledger = {"meteor": {"cast": "external-cast", "expires": 17}}

        def capture(keys, time):
            return {key: dict(ledger[key]) for key in keys if key in ledger}

        def apply_receipt(receipt, recipient, time):
            states = list(receipt["external_status_snapshot"].values())
            if states:
                winner = max(states, key=lambda state: state["expires"])
                if winner["expires"] > time:
                    ledger[recipient["id"]] = dict(winner)

        runtime = MeteorGolemCombat(
            actors,
            combat,
            lambda *args: True,
            transfer,
            capture_statuses=capture,
            apply_status_receipt=apply_receipt,
            has_target_override=lambda actor, time: actor.get("_angry_until", 0) > time,
        )
        runtime.launch(actors["meteor"], actors["tower"], 0, [])
        actors["meteor"]["_angry_until"] = 0
        ledger.pop("meteor")
        runtime.prepare(0, [])
        runtime.prepare(2, [])
        self.assertEqual(actors["mite-a"]["_angry_until"], 17)
        self.assertEqual(actors["mite-b"]["_angry_cast"], "cast-1")
        actors["tower"].update(hp=0, death_time=2)
        actors["mite-b"]["x"] = actors["mite-a"]["x"] + 0.25
        for key in ("mite-a", "mite-b"):
            runtime.select_target(
                actors[key], actors, 2, _blocked(actors, 2), 9, 7, _select_target
            )
        runtime.prepare(2, [])
        actors["mite-a"]["_angry_until"] = 0
        actors["mite-b"]["_angry_until"] = 0
        ledger.pop("mite-a")
        ledger.pop("mite-b")
        runtime.prepare(3, [])
        self.assertEqual(actors["merged"]["_angry_until"], 17)
        self.assertEqual(actors["merged"]["hp"], 60)
        self.assertEqual(actors["merged"]["_meteor_paid_owners"], ["meteor"])
        self.assertEqual(ledger["merged"], {"cast": "external-cast", "expires": 17})
        self.assertEqual(len(runtime.result()["transition_receipts"]), 2)
        self.assertFalse(_active(actors["meteor"], 3))
        self.assertFalse(_active(actors["mite-a"], 3))
        with self.assertRaises(InputError):
            runtime.validate_command({"kind": "deploy", "targets": ["merged"]})

    def test_super_valkyrie_releases_owned_rage_once_and_expiry_clears(self):
        actor = unit(
            "super-valk",
            range=0.6,
            buff_class="troop",
            entity_adapter={"entity": "super-valkyrie"},
        )
        actor["attack_model"].update(kind="radial", radius=1.5)
        actor["wall_behavior"] = {"kind": "avoid", "source": SOURCE}
        instance = {
            "entity": "super-valkyrie",
            "valkyrie_parameters": {
                "source": SOURCE,
                "neighbor_gap_tiles": 1,
                "samples_per_tile": 2,
                "maximum_extra_travel_seconds": 1,
            },
            "death_buff_parameters": {
                "source": SOURCE,
                "status": "explicit_uncalibrated_hypothesis",
                "release_delay_seconds": 0,
                "field": rage_field(),
                "trigger": "actual_hp_death_once",
                "origin": "generated_troop_effect_not_paid_spell",
            },
        }
        compile_super_valkyrie(actor, instance, {"id": "super-valkyrie"})
        actors = load([actor, unit("ally", buff_class="troop")])
        buffs = BuffCombat(actors, [])
        runtime = TroopDeathBuffCombat(actors, buffs)
        actors["super-valk"].update(hp=0, death_time=1)
        runtime.prepare(1, [])
        runtime.prepare(1, [])
        buffs.prepare(actors, 1, [])
        self.assertEqual(damage_multiplier(actors["ally"]), 2)
        self.assertEqual(len(buffs.fields), 1)
        buffs.prepare(actors, 3, [])
        self.assertEqual(damage_multiplier(actors["ally"]), 1)
        self.assertEqual(
            actors["super-valk"]["entity_adapter"]["entity"], "super-valkyrie"
        )

    def test_firemite_pool_survives_child_death_and_hits_building_with_protection(self):
        actor = unit("firemite")
        model = {
            "source": SOURCE,
            "status": "explicit_uncalibrated_hypothesis",
            "trigger": "first_successful_weapon_impact_once",
            "source_persistence": "fixed_pool_survives_child_and_furnace_loss",
            "duration_seconds": 2,
            "pulse_interval_seconds": 0.5,
            "first_pulse_offset_seconds": 0,
            "maximum_dps": 20,
            "radius_tiles": 2,
            "target_kinds": ["defense", "building"],
            "target_layers": ["ground"],
            "visibility": "hits_invisible",
            "damage_scaling": "capture_child_damage_multiplier_at_launch",
        }
        compile_firemite_pool(actor, model)
        actors = load([actor, tower(x=2, y=1, hitpoints=200)])
        actors["firemite"]["_buff_damage_multiplier"] = 2
        runtime = TroopChildEffectCombat(actors)
        runtime.on_launch("firemite", 1, 0)
        actors["firemite"].update(hp=0, death_time=0.1, _buff_damage_multiplier=1)
        runtime.on_impact("firemite", 1, (2, 1), 0.2, [])
        runtime.on_impact("firemite", 1, (2, 1), 0.2, [])
        actors["tower"]["immune_until"] = 0.4
        self.assertEqual(runtime.resolve(0.2, [])["tower"], 0)
        self.assertEqual(runtime.resolve(0.7, [])["tower"], 20)
        self.assertEqual(len(runtime.fields), 1)
        self.assertEqual(actors["firemite"]["death_time"], 0.1)
        self.assertEqual(len(runtime.continuation_reasons(0.7)), 1)


if __name__ == "__main__":
    unittest.main()
