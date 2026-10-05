"""Defending Clan Castle release clocks, role bindings and persistent troops."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.garrison_rules import RULES, RULESET, SCOPE
from clashlab.garrisons import GARRISON_MEMBERS, SHARED_GARRISON_MEMBERS, GarrisonCombat
from clashlab.spatial import _blocked, _load_actors, _select_target, simulate_spatial

from test_adapters import entity_instance, projectile
from test_defending_heroes import defender_sector
from test_indirect_defenses import damage_command, fixed_tank


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "explicit-garrison-fixture-not-replay-calibration"


def member_instance(member_id="member", entity="archer", castle_id="castle", **changes):
    instance = entity_instance(
        member_id,
        entity,
        1,
        "defense",
        x=19.5,
        y=11.5,
        spawn_seconds="controlled",
        counts_for_destruction=False,
        garrison_member_parameters={
            "source": SOURCE,
            "castle_id": castle_id,
            "donor_town_hall": 16,
            "level_basis": "snapshot_receiver_lab_cap_with_unlock_floor",
        },
    )
    if GARRISON_MEMBERS.get(entity, ("ground",))[0] == "ground":
        instance["wall_parameters"] = {"kind": "avoid", "source": SOURCE}
    if entity in {"wizard", "dragon"}:
        instance["attack_parameters"].update(
            radius=1, splash_layer_policy="primary_target_layer_only"
        )
        instance["attack_parameters"]["projectile"][
            "inactive_primary_policy"
        ] = "fizzle"
    instance.update(changes)
    return instance


def castle_instance(members, **changes):
    instance = entity_instance(
        "castle",
        "clan-castle",
        12,
        "defense",
        x=20,
        y=10,
        mode="garrison",
        statistics_mode="none",
        attack_parameters={},
        garrison_parameters={
            "source": SOURCE,
            "member_ids": [member["id"] for member in members],
            "capacity_basis": "snapshot_troopCapacity",
            "trigger_radius_multiplier": 1,
            "trigger_layers": ["ground", "air"],
            "release": {
                "initial_delay_seconds": 0.2,
                "interval_seconds": 0.3,
                "order": "declared_order_among_eligible_members",
                "trigger_loss": "hold_until_current_eligible_enemy",
                "freeze": "pause_remaining_shared_release_clock",
                "positions": {
                    member["id"]: {"x": member["x"], "y": member["y"]}
                    for member in members
                },
                "position_policy": "explicit_exterior_points",
            },
            "castle_death": "cancel_unreleased_keep_released",
            "released_targeting": "nearest_retained_hostile_units_anywhere",
            "released_idle": "hold_position",
            "death": "permanent_for_battle",
        },
    )
    instance.update(changes)
    return instance


def garrison_sector(catalog, entities, **changes):
    return defender_sector(
        catalog, entities, scope=SCOPE, model_rules=deepcopy(RULES), **changes
    )


class GarrisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def compile(self, entities, **changes):
        return compile_entity_scene(
            garrison_sector(self.catalog, entities, **changes), self.catalog
        )

    def runtime(self, entities, **changes):
        scene = self.compile(entities, **changes)["scene"]
        actors = _load_actors(scene, scene["width"], scene["height"])
        return actors, GarrisonCombat(actors, _select_target, scene), []

    def simulate(self, entities, **changes):
        return simulate_spatial(self.compile(entities, **changes)["scene"])

    def test_seven_defending_troops_use_catalog_statistics_and_exclude_destruction(
        self,
    ):
        for entity in set(GARRISON_MEMBERS) - SHARED_GARRISON_MEMBERS:
            with self.subTest(entity=entity):
                member = member_instance(entity=entity)
                compiled = self.compile([castle_instance([member]), member])
                actor = compiled["scene"]["actors"][1]
                row = self.catalog.level(entity, 1)
                self.assertEqual(actor["hitpoints"], row["hitpoints"])
                self.assertEqual(
                    actor["damage"], row["stats"]["normal"]["damagePerShot"]
                )
                self.assertEqual(actor["spawn_seconds"], "controlled")
                self.assertFalse(actor["counts_for_destruction"])
                self.assertEqual(compiled["scene"]["ruleset"], RULESET)

    def test_release_order_and_delays_are_step_invariant(self):
        members = [member_instance("first"), member_instance("second")]
        entities = [castle_instance(members), *members, fixed_tank(x=10.5, y=11.5)]
        for step in (0.01, 0.8):
            with self.subTest(step=step):
                result = self.simulate(
                    entities, maximum_step_seconds=step, duration_seconds=0.7
                )
                released = [
                    event
                    for event in result["trace"]
                    if event["event"] == "garrison_released"
                ]
                self.assertEqual(
                    [event["member"] for event in released], ["first", "second"]
                )
                self.assertAlmostEqual(released[0]["time_seconds"], 0.2)
                self.assertAlmostEqual(released[1]["time_seconds"], 0.5)

    def test_castle_freeze_pauses_remaining_release_clock(self):
        member = member_instance()
        effect = {
            "id": "freeze",
            "kind": "freeze",
            "targets": ["castle"],
            "time_seconds": 0.1,
            "duration_seconds": 0.5,
        }
        result = self.simulate(
            [castle_instance([member]), member, fixed_tank(x=10.5, y=11.5)],
            effects=[effect],
            duration_seconds=1,
        )
        self.assertAlmostEqual(
            result["garrisons"]["members"]["member"]["released_at"], 0.7
        )

    def test_castle_death_cancels_reserves_but_released_members_keep_fighting(self):
        members = [member_instance("first"), member_instance("second")]
        result = self.simulate(
            [castle_instance(members), *members, fixed_tank(x=17.5, y=11.5)],
            effects=[damage_command("castle", 0.3, 100000)],
            duration_seconds=1.4,
        )
        self.assertEqual(result["garrisons"]["members"]["second"]["phase"], "cancelled")
        self.assertEqual(result["actors"]["second"]["spawn_seconds"], "controlled")
        self.assertEqual(result["garrisons"]["members"]["first"]["phase"], "released")
        self.assertLess(
            result["actors"]["tank"]["hp"], result["actors"]["tank"]["maximum_hp"] - 8
        )

    def test_release_eligibility_skips_ground_only_member_for_air_trigger(self):
        members = [
            member_instance("ground", "barbarian"),
            member_instance("both", "archer"),
        ]
        result = self.simulate(
            [
                castle_instance(members),
                *members,
                fixed_tank(entity="minion", x=10.5, y=11.5),
            ],
            duration_seconds=0.7,
        )
        self.assertEqual(result["garrisons"]["castles"]["castle"]["released"], ["both"])
        self.assertEqual(result["actors"]["ground"]["spawn_seconds"], "controlled")

    def test_trigger_loss_holds_mature_clock_until_a_current_enemy_returns(self):
        member = member_instance()
        actors, runtime, trace = self.runtime(
            [castle_instance([member]), member, fixed_tank(x=10.5, y=11.5)]
        )
        runtime.prepare(actors, 0, trace)
        actors["tank"]["x"] = 1
        runtime.prepare(actors, 0.2, trace)
        self.assertEqual(actors["member"]["spawn_seconds"], "controlled")
        actors["tank"]["x"] = 10.5
        runtime.prepare(actors, 1, trace)
        self.assertEqual(actors["member"]["spawn_seconds"], 1)

    def test_invisibility_and_layer_policies_prevent_trigger(self):
        member = member_instance(entity="barbarian")
        actors, runtime, trace = self.runtime(
            [castle_instance([member]), member, fixed_tank(x=10.5, y=11.5)]
        )
        actors["tank"]["_untargetable_until"] = 2
        runtime.prepare(actors, 0, trace)
        self.assertEqual(runtime.states["castle"]["phase"], "dormant")
        actors["tank"]["_untargetable_until"] = 0
        actors["tank"]["_spell_tower_untargetable_until"] = 2
        runtime.prepare(actors, 0, trace)
        self.assertEqual(runtime.states["castle"]["phase"], "dormant")

    def test_exact_circle_entry_supports_forced_motion_while_frozen(self):
        member = member_instance()
        actors, runtime, _ = self.runtime(
            [
                castle_instance([member]),
                member,
                fixed_tank(entity="minion", x=1.5, y=11.5),
            ]
        )
        actor = actors["tank"]
        self.assertAlmostEqual(
            runtime.first_crossing_delay(actor, [(15, 11.5)], 0, 5, 2), 3.5
        )
        actor["frozen_until"] = 10
        self.assertIsNone(runtime.first_crossing_delay(actor, [(15, 11.5)], 0, 5, 2))
        self.assertAlmostEqual(
            runtime.first_crossing_delay(
                actor, [(15, 11.5)], 0, 5, 2, forced_motion=True
            ),
            3.5,
        )

    def test_released_target_retention_then_idle_has_no_return_leash(self):
        member = member_instance(entity="minion")
        actors, runtime, trace = self.runtime(
            [castle_instance([member]), member, fixed_tank(x=10.5, y=11.5)]
        )
        runtime.prepare(actors, 0, trace)
        runtime.prepare(actors, 0.2, trace)
        actor = actors["member"]
        target, route = runtime.select_target(
            actor, actors, 0.2, _blocked(actors, 0.2), 50, 28
        )
        self.assertEqual(target["id"], "tank")
        actors["tank"]["x"] = 1
        target, route = runtime.select_target(
            actor, actors, 0.3, _blocked(actors, 0.3), 50, 28
        )
        self.assertEqual(target["id"], "tank")
        actors["tank"]["hp"] = 0
        self.assertEqual(
            runtime.select_target(actor, actors, 0.4, _blocked(actors, 0.4), 50, 28),
            (None, None),
        )

    def test_capacity_donor_level_and_receiver_unlock_floor_are_enforced(self):
        members = [member_instance(str(index), "pekka") for index in range(3)]
        with self.assertRaises(InputError):
            self.compile([castle_instance(members), *members])
        member = member_instance(entity="thrower")
        member["garrison_member_parameters"]["donor_town_hall"] = 15
        with self.assertRaises(InputError):
            self.compile([castle_instance([member]), member])
        member["garrison_member_parameters"]["donor_town_hall"] = 16
        with self.assertRaises(InputError):
            self.compile([castle_instance([member], level=1), member])

    def test_missing_member_duplicate_owner_or_unsafe_release_is_rejected(self):
        member = member_instance()
        castle = castle_instance([member])
        bad = [
            [castle],
            [castle, {**deepcopy(castle), "id": "other", "x": 30}, member],
            [castle, {**member, "x": 21.5}],
        ]
        for entities in bad:
            with self.subTest(entities=entities), self.assertRaises(InputError):
                self.compile(entities)
        castle["garrison_parameters"]["release"]["positions"]["member"]["x"] = 21.5
        member["x"] = 21.5
        with self.assertRaises(InputError):
            self.compile([castle, member])

    def test_external_reserve_deployment_is_rejected_before_and_during_runtime(self):
        member = member_instance()
        effect = {
            "id": "bad",
            "kind": "deploy",
            "time_seconds": 0,
            "targets": ["member"],
            "positions": {"member": {"x": 19.5, "y": 11.5}},
        }
        with self.assertRaises(InputError):
            self.compile([castle_instance([member]), member], effects=[effect])
        actors, runtime, trace = self.runtime([castle_instance([member]), member])
        actors["member"]["spawn_seconds"] = 0
        with self.assertRaises(InputError):
            runtime.prepare(actors, 0, trace)

    def test_empty_castle_is_explicitly_supported_and_old_scope_bypass_fails(self):
        result = self.simulate([castle_instance([])], duration_seconds=0.01)
        self.assertEqual(result["garrisons"]["castles"]["castle"]["phase"], "empty")
        from clashlab.builder_rules import RULES as OLD_RULES, SCOPE as OLD_SCOPE

        scene = garrison_sector(self.catalog, [castle_instance([])])
        scene.update(scope=OLD_SCOPE, model_rules=deepcopy(OLD_RULES))
        with self.assertRaises(InputError):
            compile_entity_scene(scene, self.catalog)

    def test_unsupported_special_defenders_fail_closed(self):
        member = member_instance(entity="ice-golem")
        with self.assertRaises(InputError):
            self.compile([castle_instance([member]), member])


if __name__ == "__main__":
    unittest.main()
