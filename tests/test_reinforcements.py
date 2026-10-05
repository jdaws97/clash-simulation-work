"""Attacking CC resources, declared deployment regions and persistent releases."""

from copy import deepcopy
from inspect import signature
from pathlib import Path
import unittest

from clashlab.adapters import compile_actor
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.reinforcements import (
    ReinforcementCombat,
    compile_attacking_reinforcements,
    compile_received_spell,
    validate_reinforcement_inventory,
    validate_spell_origin_counts,
)
from clashlab.spatial import _load_actors
from clashlab.spells import compile_freeze_spell

from test_adapters import entity_instance
from test_full_battle import fixture, freeze_cast


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "explicit-attacking-reinforcement-fixture-not-game-calibration"


def payload_instance(actor_id="payload", entity="archer", **changes):
    instance = entity_instance(
        actor_id,
        entity,
        1,
        "attack",
        x=1.5,
        y=1.5,
        spawn_seconds="controlled",
        counts_for_destruction=False,
        payload_member_parameters={
            "source": SOURCE,
            "group_id": "reinforcements",
            "donor_town_hall": 18,
            "receiver_clan_castle_level": 12,
            "level_basis": "snapshot_receiver_lab_cap_with_unlock_floor",
        },
    )
    if entity not in {"minion", "dragon", "electro-dragon", "dragon-rider", "healer"}:
        instance["wall_parameters"] = {"kind": "avoid", "source": SOURCE}
    instance.update(changes)
    return instance


def compile_payload(instance, catalog):
    flags = {
        name: True
        for name in signature(compile_actor).parameters
        if name.startswith("allow_")
    }
    actor = compile_actor(instance, catalog, 8, **flags)
    actor["buff_class"] = "troop"
    return actor


def group_parameters(member_ids, carrier_id=None, **changes):
    parameters = {
        "id": "reinforcements",
        "source": SOURCE,
        "receiver_town_hall": 16,
        "receiver_clan_castle_level": 12,
        "member_ids": list(member_ids),
        "delivery": {
            "kind": "siege" if carrier_id else "direct",
            "carrier_id": carrier_id,
        },
        "release": {
            "initial_delay_seconds": 0.1,
            "interval_seconds": 0.2,
            "order": "declared_order",
            "offsets": {actor_id: {"x": 0, "y": 0} for actor_id in member_ids},
            "position_policy": "explicit_offset_then_nearest_clear_ground_cell",
            "maximum_displacement_tiles": 3,
            "blocked_position": "hold_member_until_legal_point_exists",
            "initial_state": "fresh_health_and_release_relative_attack_clock",
            "clock": "continues_after_carrier_loss",
        },
        "deployment_policy": {
            "source": SOURCE,
            "kind": "explicit_allowed_regions_hypothesis",
            "regions": [{"left": 0, "top": 0, "right": 5, "bottom": 20}],
            "point_policy": "inside_declared_region_and_clear_of_hostile_footprints",
        },
    }
    parameters.update(changes)
    return parameters


def target_actor(
    actor_id="target", kind="building", x=10, y=7, width=1, height=1, entity=None
):
    actor = {
        "id": actor_id,
        "source": SOURCE,
        "team": "defense",
        "kind": kind,
        "layer": "ground",
        "movement": "stationary",
        "speed": 0,
        "hitpoints": 100000,
        "damage": 0,
        "range": 0,
        "attack_interval_seconds": 1,
        "first_attack_seconds": 0,
        "spawn_seconds": 0,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "blocking": True,
        "counts_for_destruction": kind != "wall",
        "target_priorities": [],
        "target_layers": [],
        "attack_model": {"kind": "none", "source": SOURCE},
    }
    if entity is not None:
        actor["entity_adapter"] = {"entity": entity, "level": 16}
    return actor


def direct_command(time=0, x=1.5, y=7.5, command_id="deploy-cc"):
    return {
        "id": command_id,
        "kind": "clan_castle_deploy",
        "time_seconds": time,
        "group_id": "reinforcements",
        "position": {"x": x, "y": y},
    }


class ReinforcementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def runtime(self, instances=None, extra=None, parameters=None):
        instances = instances or [payload_instance()]
        actor_specs = [
            compile_payload(instance, self.catalog) for instance in instances
        ]
        actor_specs.extend(extra or [])
        actors = _load_actors({"actors": actor_specs}, 30, 20)
        parameters = parameters or group_parameters(
            [instance["id"] for instance in instances]
        )
        model = compile_attacking_reinforcements(parameters, self.catalog, actors)
        return actors, ReinforcementCombat(actors, model, 30, 20), []

    def test_payload_retains_ordinary_troop_statistics_and_role(self):
        actor = compile_payload(payload_instance(), self.catalog)
        self.assertEqual(actor["hitpoints"], 22)
        self.assertEqual(actor["damage"], 8)
        self.assertEqual(actor["attack_model"]["kind"], "single")
        self.assertEqual(actor["healing_class"], "troop")
        self.assertEqual(actor["buff_class"], "troop")
        self.assertNotIn("garrison_member_model", actor)

    def test_donor_and_receiver_lab_relations_are_separate(self):
        instance = payload_instance(entity="thrower")
        instance["payload_member_parameters"]["donor_town_hall"] = 15
        with self.assertRaises(InputError):
            compile_payload(instance, self.catalog)
        instance["payload_member_parameters"]["donor_town_hall"] = 18
        instance["payload_member_parameters"]["receiver_clan_castle_level"] = 1
        with self.assertRaises(InputError):
            compile_payload(instance, self.catalog)

    def test_received_super_troop_binds_parent_research_and_keeps_receiver_cap(self):
        parameters = read_json(ROOT / "data/battle-policies/recipe-troops.json")[
            "parameters"
        ]["rocket-balloon"]
        for level in (8, 10):
            instance = payload_instance(
                entity="rocket-balloon", level=level, recipe_parameters=parameters
            )
            instance.pop("wall_parameters")
            instance["attack_parameters"]["radius"] = 1.2
            with self.subTest(level=level):
                actor = compile_payload(instance, self.catalog)
                self.assertEqual(actor["entity_adapter"]["level"], level)
                instance["payload_member_parameters"]["receiver_clan_castle_level"] = 1
                with self.assertRaisesRegex(InputError, "receiver|laboratory"):
                    compile_payload(instance, self.catalog)

    def test_unsupported_payload_and_predeployed_member_fail_closed(self):
        with self.assertRaises(InputError):
            compile_payload(payload_instance(entity="witch"), self.catalog)
        with self.assertRaises(InputError):
            compile_payload(payload_instance(spawn_seconds=0), self.catalog)

    def test_direct_command_releases_once_in_declared_order(self):
        members = [payload_instance("first"), payload_instance("second")]
        actors, runtime, trace = self.runtime(members)
        runtime.apply_commands([direct_command()], 0, trace)
        self.assertAlmostEqual(runtime.next_boundary(0), 0.1)
        self.assertTrue(runtime.prepare(0.1, trace))
        self.assertFalse(runtime.prepare(0.1, trace))
        runtime.prepare(0.3, trace)
        self.assertEqual(runtime.state["released"], ["first", "second"])
        self.assertEqual(actors["first"]["spawn_seconds"], 0.1)
        self.assertEqual(actors["second"]["spawn_seconds"], 0.3)
        with self.assertRaises(InputError):
            runtime.apply_commands([direct_command(1, command_id="again")], 1, trace)

    def test_clear_point_outside_declared_region_is_not_treated_as_legal(self):
        _, runtime, trace = self.runtime()
        with self.assertRaises(InputError):
            runtime.apply_commands([direct_command(x=8.5)], 0, trace)
        self.assertFalse(runtime.result()["game_exclusion_zones_validated"])
        self.assertEqual(runtime.result()["deployment_policy"]["source"], SOURCE)

    def test_allowed_region_still_rejects_hostile_footprint(self):
        _, runtime, trace = self.runtime(extra=[target_actor(x=1, y=7)])
        with self.assertRaises(InputError):
            runtime.apply_commands([direct_command()], 0, trace)

    def test_scheduled_point_checks_current_footprints_only_when_executed(self):
        actors, runtime, trace = self.runtime(extra=[target_actor(x=1, y=7)])
        command = direct_command(time=1)
        runtime.validate_command(command)
        actors["target"]["hp"] = 0
        runtime.apply_commands([command], 1, trace)
        self.assertEqual(runtime.state["delivery_time"], 1)

    def test_ground_payload_uses_bounded_nearest_clear_cell_when_release_point_is_blocked(
        self,
    ):
        actors, runtime, trace = self.runtime(extra=[target_actor(x=10, y=7)])
        runtime.begin_release(0, {"x": 10.5, "y": 7.5}, "direct_command", None, trace)
        runtime.prepare(0.1, trace)
        self.assertEqual((actors["payload"]["x"], actors["payload"]["y"]), (10.5, 6.5))

    def test_no_legal_ground_point_keeps_payload_pending_until_clear(self):
        parameters = group_parameters(["payload"])
        parameters["release"]["maximum_displacement_tiles"] = 0
        actors, runtime, trace = self.runtime(
            extra=[target_actor(x=10, y=7)], parameters=parameters
        )
        runtime.begin_release(0, {"x": 10.5, "y": 7.5}, "direct_command", None, trace)
        runtime.prepare(0.1, trace)
        self.assertEqual(runtime.state["remaining"], ["payload"])
        self.assertEqual(actors["payload"]["spawn_seconds"], "controlled")
        actors["target"]["hp"] = 0
        runtime.prepare(1, trace)
        self.assertEqual(runtime.state["released"], ["payload"])
        self.assertEqual(actors["payload"]["spawn_seconds"], 1)

    def test_air_payload_preserves_declared_point_above_footprint(self):
        actors, runtime, trace = self.runtime(
            [payload_instance(entity="minion")], extra=[target_actor(x=10, y=7)]
        )
        runtime.begin_release(0, {"x": 10.5, "y": 7.5}, "direct_command", None, trace)
        runtime.prepare(0.1, trace)
        self.assertEqual((actors["payload"]["x"], actors["payload"]["y"]), (10.5, 7.5))

    def test_external_deployment_and_unbound_member_are_rejected(self):
        actors, runtime, trace = self.runtime()
        effect = {
            "id": "bad",
            "kind": "deploy",
            "time_seconds": 0,
            "targets": ["payload"],
            "positions": {"payload": {"x": 1.5, "y": 1.5}},
        }
        with self.assertRaises(InputError):
            runtime.validate_command(effect)
        actors["payload"]["spawn_seconds"] = 0
        with self.assertRaises(InputError):
            runtime.prepare(0, trace)
        actors, _, _ = self.runtime()
        parameters = group_parameters(["different"])
        with self.assertRaises(InputError):
            compile_attacking_reinforcements(parameters, self.catalog, actors)

    def test_payload_inventory_cannot_charge_ordinary_army_housing(self):
        actors, runtime, _ = self.runtime()
        _, account, army, _ = fixture(self.catalog)
        army["clan_castle"]["troops"] = [{"id": "archer", "level": 1, "count": 1}]
        bindings = validate_reinforcement_inventory(
            runtime.model, actors, army, account, self.catalog
        )
        self.assertEqual(bindings["payload"]["origin"], "clan_castle_troops")
        army["clan_castle"]["troops"] = []
        army["troops"].append({"id": "archer", "level": 1, "count": 1})
        with self.assertRaises(InputError):
            validate_reinforcement_inventory(
                runtime.model, actors, army, account, self.catalog
            )

    def test_confirmed_account_donation_cap_remains_authoritative(self):
        actors, runtime, _ = self.runtime()
        _, account, army, _ = fixture(self.catalog)
        army["clan_castle"]["troops"] = [{"id": "archer", "level": 1, "count": 1}]
        account["donation_levels"] = {}
        with self.assertRaises(InputError):
            validate_reinforcement_inventory(
                runtime.model, actors, army, account, self.catalog
            )

    def test_received_capacity_and_exact_count_are_enforced(self):
        members = [payload_instance(str(index), "pekka") for index in range(3)]
        with self.assertRaises(InputError):
            self.runtime(members)
        actors, runtime, _ = self.runtime()
        _, account, army, _ = fixture(self.catalog)
        army["clan_castle"]["troops"] = [{"id": "archer", "level": 1, "count": 2}]
        with self.assertRaises(InputError):
            validate_reinforcement_inventory(
                runtime.model, actors, army, account, self.catalog
            )

    def test_spell_origins_cannot_double_spend_or_borrow_an_own_spell(self):
        army = {
            "spells": [{"id": "freeze-spell", "level": 1, "count": 1}],
            "clan_castle": {"spells": [{"id": "rage-spell", "level": 1, "count": 1}]},
        }
        spells = [
            {
                "id": "own-freeze",
                "entity": "freeze-spell",
                "level": 1,
                "origin": "army",
            },
            {
                "id": "cc-rage",
                "entity": "rage-spell",
                "level": 1,
                "origin": "clan_castle",
            },
        ]
        self.assertEqual(
            validate_spell_origin_counts(army, spells)["cc-rage"]["origin"],
            "clan_castle_spells",
        )
        with self.assertRaises(InputError):
            validate_spell_origin_counts(army, [spells[0], spells[0]])
        with self.assertRaises(InputError):
            validate_spell_origin_counts(army, [{**spells[0], "origin": "clan_castle"}])
        with self.assertRaises(InputError):
            validate_spell_origin_counts(
                army, [{**spells[1], "entity": "poison-spell"}]
            )

    def test_unused_unsupported_and_duplicate_spell_inventory_are_rejected(self):
        for inventory in (
            [{"id": "unsupported-spell", "level": 1, "count": 1}],
            [{"id": "freeze-spell", "level": 1, "count": 1}] * 2,
        ):
            army = {"spells": inventory, "clan_castle": {"spells": []}}
            with self.assertRaises(InputError):
                validate_spell_origin_counts(army, [])
        self.assertEqual(
            validate_spell_origin_counts(
                {
                    "spells": [{"id": "clone-spell", "level": 1, "count": 1}],
                    "clan_castle": {"spells": []},
                },
                [],
            ),
            {},
        )

    def test_received_spell_uses_donor_level_with_separate_receiver_cap(self):
        instance = freeze_cast(town_hall=10)
        instance.update(
            level=7,
            origin="clan_castle",
            received_spell_parameters={
                "source": SOURCE,
                "donor_town_hall": 18,
                "receiver_clan_castle_level": 6,
                "level_basis": "snapshot_receiver_lab_cap_with_unlock_floor",
            },
        )
        with self.assertRaises(InputError):
            compile_freeze_spell(instance, self.catalog)
        result = compile_received_spell(instance, self.catalog, compile_freeze_spell)
        self.assertEqual(result["duration_seconds"], 5.5)
        self.assertEqual(result["entity_adapter"]["town_hall"], 10)
        self.assertEqual(result["entity_adapter"]["origin"], "clan_castle")
        instance["received_spell_parameters"]["receiver_clan_castle_level"] = 5
        with self.assertRaises(InputError):
            compile_received_spell(instance, self.catalog, compile_freeze_spell)
        instance["origin"] = "army"
        with self.assertRaises(InputError):
            compile_received_spell(instance, self.catalog, compile_freeze_spell)


if __name__ == "__main__":
    unittest.main()
