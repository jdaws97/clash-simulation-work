"""Independent siege routes, named damage quantities and payload termination."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.battle_modifiers import apply_battle_modifiers
from clashlab.reinforcements import (
    ReinforcementCombat,
    compile_attacking_reinforcements,
    validate_reinforcement_inventory,
)
from clashlab.siege_machines import (
    DEATH_STATISTICS,
    SIEGE_MACHINES,
    TARGETING_KINDS,
    SiegeCombat,
    _range_entry,
    compile_siege,
)
from clashlab.spatial import _blocked, _load_actors, _select_target

from test_adapters import entity_instance
from test_battle_modifiers import modifier_policy
from test_full_battle import fixture
from test_reinforcements import (
    SOURCE,
    compile_payload,
    group_parameters,
    payload_instance,
    target_actor,
)


ROOT = Path(__file__).resolve().parents[1]


def siege_instance(entity="battle-blimp", **changes):
    targeted_hall = entity != "stone-slammer"
    instance = entity_instance(
        "siege",
        entity,
        1,
        "attack",
        x=1.5,
        y=7.5,
        attack_parameters={},
        siege_parameters={
            "source": SOURCE,
            "origin": "own",
            "donor_town_hall": None,
            "payload_group_id": "reinforcements",
            "statistics_mapping": "snapshot_damagePerHit_and_entity_attackSpeed",
            "range_tiles": 0.8 if entity == "wall-wrecker" else 3,
            "targeting": {
                "kind": TARGETING_KINDS[entity],
                "hall_actor_id": "hall" if targeted_hall else None,
                "arrival_radius_tiles": (
                    (3 if entity == "wall-wrecker" else 0) if targeted_hall else None
                ),
                "hall_loss": (
                    "continue_to_captured_anchor" if targeted_hall else "not_applicable"
                ),
                "ineligible_blocker": (
                    "wait_until_targetable"
                    if entity == "wall-wrecker"
                    else "not_applicable"
                ),
            },
            "weapon": {
                "projectile": {
                    "timing": "instant",
                    "delay_seconds": 0,
                    "destination": "fixed_target_center_at_launch",
                    "inactive_primary_policy": "resolve_at_fixed_launch_position",
                },
                "zones": [
                    {
                        "inner_radius_tiles": 0,
                        "outer_radius_tiles": 1,
                        "damage_multiplier": 1,
                        "wall_damage_multiplier": 1,
                    }
                ],
                "zone_composition": "strongest_per_recipient",
                "zone_membership": "minimum_point_to_footprint_distance",
                "wall_damage_basis": (
                    "snapshot_damageVsWalls_ratio"
                    if entity == "wall-wrecker"
                    else "explicit_zone_multiplier"
                ),
            },
            "termination": {
                "manual_release": "destroy_and_release",
                "maximum_lifetime_seconds": None,
                "decay": {
                    "interval_seconds": 1,
                    "maximum_hp_fraction_per_pulse": 0,
                    "protection": "bypass_damage_immunity",
                    "freeze": "clock_continues",
                },
            },
            "death": {
                "triggers": "all_terminations",
                "overlap": "sum_explicit_effects",
                "effects": [
                    {
                        "statistic": statistic,
                        "delay_seconds": 0,
                        "inner_radius_tiles": 0,
                        "outer_radius_tiles": 2,
                        "damage_multiplier": 1,
                        "target_kinds": ["building", "defense", "wall"],
                        "target_layers": ["ground"],
                    }
                    for statistic in sorted(DEATH_STATISTICS[entity])
                ],
            },
            "spell_response": {
                "beneficial_fields": "immune_to_healing_rage_and_haste",
                "hostile_effects": "explicit_shared_status_and_hazard_policies",
            },
        },
    )
    instance.update(changes)
    return instance


def compiled_siege(instance, catalog):
    entity = catalog.entity(instance["entity"])
    row = catalog.level(instance["entity"], instance["level"])
    modifiers = instance["modifiers"]
    actor = {
        "id": instance["id"],
        "source": catalog.records[instance["entity"]]["source"],
        "team": instance["team"],
        "hitpoints": row["hitpoints"] * modifiers["hitpoints_multiplier"],
        "first_attack_seconds": instance["first_attack_seconds"],
        "spawn_seconds": instance["spawn_seconds"],
        "x": instance["x"],
        "y": instance["y"],
        "counts_for_destruction": instance["counts_for_destruction"],
        "minimum_range": 0,
        "entity_adapter": {
            "entity": instance["entity"],
            "level": instance["level"],
            "town_hall": instance["town_hall"],
            "modifiers": deepcopy(modifiers),
        },
    }
    return compile_siege(actor, instance, entity, row, modifiers, catalog, 8)


def release_command(time=0.2):
    return {
        "id": "release",
        "kind": "siege_release",
        "time_seconds": time,
        "target": "siege",
    }


class SiegeMachineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def runtime(self, instance=None, extra=None, parameters=None, payloads=None):
        instance = instance or siege_instance()
        payloads = payloads if payloads is not None else [payload_instance()]
        actors = [
            compiled_siege(instance, self.catalog),
            target_actor("hall", x=20, y=5, width=4, height=4, entity="town-hall"),
        ]
        actors.extend(compile_payload(member, self.catalog) for member in payloads)
        actors.extend(extra or [])
        actors = _load_actors({"actors": actors}, 30, 20)
        parameters = parameters or group_parameters(
            [member["id"] for member in payloads], "siege"
        )
        model = compile_attacking_reinforcements(parameters, self.catalog, actors)
        payload = ReinforcementCombat(actors, model, 30, 20)
        runtime = SiegeCombat(actors, _select_target, payload, 30, 20)
        trace = []
        runtime.prepare(actors, 0, trace)
        return actors, runtime, payload, trace

    def select(self, actors, runtime, time=0):
        return runtime.select_target(
            actors["siege"], actors, time, _blocked(actors, time), 30, 20
        )

    def test_three_sieges_use_named_statistics_and_distinct_siege_role(self):
        for entity, hp, damage, cadence in (
            ("battle-blimp", 3000, 150, 1.5),
            ("stone-slammer", 5600, 1000, 2.5),
            ("wall-wrecker", 5500, 325, 1.3),
        ):
            with self.subTest(entity=entity):
                actor = compiled_siege(siege_instance(entity), self.catalog)
                self.assertEqual(actor["hitpoints"], hp)
                self.assertEqual(actor["damage"], damage)
                self.assertEqual(actor["attack_interval_seconds"], cadence)
                self.assertEqual(actor["healing_class"], "siege")
                self.assertEqual(actor["buff_class"], "siege")
                self.assertTrue(actor["beneficial_field_immunity"])
                self.assertEqual(actor["attack_model"]["kind"], "siege_area")

    def test_blimp_keeps_flying_while_bomb_target_is_in_range(self):
        actors, runtime, _, trace = self.runtime(extra=[target_actor(x=3, y=7)])
        target, route = self.select(actors, runtime)
        self.assertEqual(target["id"], "target")
        self.assertEqual(route, [(22, 7)])
        runtime.launch(actors["siege"], target, actors, 0, trace)
        self.assertEqual(runtime.resolve(actors, 0, trace)["target"], 150)
        self.assertEqual(self.select(actors, runtime)[1], route)
        self.assertAlmostEqual(actors["siege"]["next_attack"], 1.5)

    def test_blimp_arrival_boundary_and_dead_hall_keep_captured_destination(self):
        actors, runtime, payload, trace = self.runtime()
        actors["siege"].update(x=10, y=7)
        actors["hall"]["hp"] = 0
        _, route = self.select(actors, runtime)
        self.assertEqual(route, [(22, 7)])
        self.assertAlmostEqual(
            runtime.first_crossing_delay(actors["siege"], route, 0, 10, 2), 6
        )
        actors["siege"].update(x=22, y=7)
        runtime.prepare(actors, 6, trace)
        self.assertEqual(runtime.states["siege"]["termination_reason"], "hall_arrival")
        self.assertEqual(payload.state["delivery_point"], {"x": 22, "y": 7})

    def test_blimp_range_entry_uses_rounded_footprint_contact(self):
        target = target_actor(x=10, y=7)
        self.assertAlmostEqual(_range_entry((1, 7.5), (15, 7.5), target, 3), 6)
        self.assertIsNone(_range_entry((1, 1), (15, 1), target, 3))
        actors, runtime, _, _ = self.runtime(extra=[target])
        actors["siege"].update(x=1, y=7.5)
        self.assertAlmostEqual(
            runtime.first_crossing_delay(actors["siege"], [(15, 7.5)], 0, 10, 2), 3
        )

    def test_wrecker_stops_at_first_wall_then_first_structure(self):
        wall = target_actor("wall", kind="wall", x=10, y=7)
        structure = target_actor("building", x=14, y=7)
        actors, runtime, _, _ = self.runtime(
            siege_instance("wall-wrecker", y=7), extra=[wall, structure]
        )
        target, route = self.select(actors, runtime)
        self.assertEqual(target["id"], "wall")
        self.assertAlmostEqual(route[-1][0], 9.2)
        actors["wall"]["hp"] = 0
        target, route = self.select(actors, runtime)
        self.assertEqual(target["id"], "building")
        self.assertAlmostEqual(route[-1][0], 13.2)

    def test_wrecker_wall_statistic_does_not_scale_neighboring_buildings(self):
        actors, runtime, _, trace = self.runtime(
            siege_instance("wall-wrecker"),
            extra=[
                target_actor("wall", kind="wall", x=10, y=7),
                target_actor("building", x=11, y=7),
            ],
        )
        actors["siege"].update(x=9.2, y=7.5)
        runtime.launch(actors["siege"], actors["wall"], actors, 0, trace)
        damage = runtime.resolve(actors, 0, trace)
        self.assertEqual(damage["wall"], 3250)
        self.assertEqual(damage["building"], 325)

    def test_wrecker_waits_at_an_ineligible_physical_blocker(self):
        actors, runtime, _, _ = self.runtime(
            siege_instance("wall-wrecker", y=7),
            extra=[target_actor("obstacle", x=10, y=7)],
        )
        actors["obstacle"]["_spell_tower_untargetable_until"] = 10
        self.assertEqual(self.select(actors, runtime), (None, []))
        self.assertEqual(runtime.states["siege"]["blocker"], "obstacle")

    def test_slammer_prioritizes_defense_then_retains_target(self):
        actors, runtime, _, _ = self.runtime(
            siege_instance("stone-slammer"),
            extra=[
                target_actor("near-building", x=4, y=7),
                target_actor("far-defense", kind="defense", x=12, y=7),
            ],
        )
        self.assertEqual(self.select(actors, runtime)[0]["id"], "far-defense")
        actors["near-building"]["kind"] = "defense"
        self.assertEqual(self.select(actors, runtime)[0]["id"], "far-defense")
        actors["far-defense"]["hp"] = 0
        self.assertEqual(self.select(actors, runtime)[0]["id"], "near-building")

    def test_slammer_uses_strongest_weapon_zone_instead_of_adding_overlaps(self):
        instance = siege_instance("stone-slammer")
        instance["siege_parameters"]["weapon"]["zones"].append(
            {
                "inner_radius_tiles": 0,
                "outer_radius_tiles": 3,
                "damage_multiplier": 0.1,
                "wall_damage_multiplier": 10,
            }
        )
        actors, runtime, _, trace = self.runtime(
            instance,
            extra=[
                target_actor("primary", kind="defense", x=3, y=7),
                target_actor("wall", kind="wall", x=5, y=7),
            ],
        )
        runtime.launch(actors["siege"], actors["primary"], actors, 0, trace)
        damage = runtime.resolve(actors, 0, trace)
        self.assertEqual(damage["primary"], 1000)
        self.assertEqual(damage["wall"], 1000)

    def test_named_slammer_death_hitboxes_are_independent_of_ordinary_hit(self):
        actors, runtime, _, trace = self.runtime(
            siege_instance("stone-slammer"), extra=[target_actor(x=3, y=7)]
        )
        actors["siege"]["hp"] = 0
        runtime.prepare(actors, 0.2, trace)
        self.assertEqual(runtime.resolve(actors, 0.2, trace)["target"], 300)
        self.assertEqual(actors["siege"]["damage"], 1000)

    def test_manual_release_terminates_once_and_payload_survives_carrier_death(self):
        payloads = [payload_instance("first"), payload_instance("second")]
        actors, runtime, payload, trace = self.runtime(payloads=payloads)
        runtime.apply_commands([release_command()], 0.2, trace)
        runtime.prepare(actors, 0.3, trace)
        runtime.prepare(actors, 0.5, trace)
        self.assertEqual(payload.state["released"], ["first", "second"])
        self.assertEqual(actors["siege"]["hp"], 0)
        self.assertEqual(actors["first"]["spawn_seconds"], 0.3)
        self.assertEqual(
            runtime.states["siege"]["termination_reason"], "manual_release"
        )
        with self.assertRaises(InputError):
            runtime.apply_commands([release_command(0.6)], 0.6, trace)

    def test_scheduled_manual_release_is_validated_before_carrier_deployment(self):
        actors, runtime, _, trace = self.runtime(
            siege_instance(spawn_seconds="controlled")
        )
        runtime.validate_command(release_command(1))
        with self.assertRaises(InputError):
            runtime.apply_commands([release_command(1)], 1, trace)
        actors["siege"]["spawn_seconds"] = 0.5
        runtime.apply_commands([release_command(1)], 1, trace)
        self.assertEqual(runtime.states["siege"]["deployed_at"], 0.5)
        self.assertEqual(runtime.states["siege"]["terminated_at"], 1)

    def test_death_on_initial_deployment_still_delivers_payload_once(self):
        actors, runtime, payload, trace = self.runtime()
        runtime.states["siege"]["phase"] = "undeployed"
        actors["siege"]["hp"] = 0
        runtime.prepare(actors, 0, trace)
        runtime.prepare(actors, 0, trace)
        self.assertEqual(runtime.states["siege"]["termination_reason"], "hp_death")
        self.assertEqual(
            sum(event["event"] == "payload_delivery" for event in trace), 1
        )
        self.assertEqual(payload.state["remaining"], ["payload"])

    def test_manual_release_can_explicitly_omit_hp_death_only_blast(self):
        instance = siege_instance()
        instance["siege_parameters"]["death"]["triggers"] = "hp_death_only"
        actors, runtime, _, trace = self.runtime(
            instance, extra=[target_actor(x=3, y=7)]
        )
        runtime.apply_commands([release_command()], 0.2, trace)
        self.assertEqual(dict(runtime.resolve(actors, 0.2, trace)), {})

    def test_actual_death_blast_uses_captured_position_and_survives_freeze(self):
        instance = siege_instance()
        instance["siege_parameters"]["death"]["effects"][0]["delay_seconds"] = 0.5
        actors, runtime, _, trace = self.runtime(
            instance, extra=[target_actor(x=3, y=7)]
        )
        actors["siege"]["frozen_until"] = 10
        actors["siege"]["hp"] = 0
        runtime.prepare(actors, 0.2, trace)
        actors["siege"]["x"] = 20
        self.assertEqual(runtime.resolve(actors, 0.7, trace)["target"], 700)

    def test_projectile_survives_carrier_termination(self):
        instance = siege_instance()
        instance["siege_parameters"]["weapon"]["projectile"].update(
            timing="launch_distance_delay", speed_tiles_per_second=2
        )
        actors, runtime, _, trace = self.runtime(
            instance, extra=[target_actor(x=3, y=7)]
        )
        runtime.launch(actors["siege"], actors["target"], actors, 0, trace)
        runtime.apply_commands([release_command(0.1)], 0.1, trace)
        runtime.resolve(actors, 0.1, trace)
        self.assertEqual(runtime.resolve(actors, 1, trace)["target"], 150)

    def test_decay_and_expiry_are_explicit_boundaries_independent_of_freeze(self):
        instance = siege_instance("stone-slammer")
        instance["siege_parameters"]["termination"]["maximum_lifetime_seconds"] = 2.5
        instance["siege_parameters"]["termination"]["decay"][
            "maximum_hp_fraction_per_pulse"
        ] = 0.25
        actors, runtime, _, trace = self.runtime(instance)
        actors["siege"].update(frozen_until=10, immune_until=10)
        self.assertEqual(runtime.next_boundary(0), 1)
        runtime.prepare(actors, 1, trace)
        self.assertEqual(actors["siege"]["hp"], 4200)
        runtime.prepare(actors, 2, trace)
        self.assertEqual(actors["siege"]["hp"], 2800)
        self.assertEqual(runtime.next_boundary(2), 2.5)
        runtime.prepare(actors, 2.5, trace)
        self.assertEqual(
            runtime.states["siege"]["termination_reason"], "lifetime_expired"
        )

    def test_missing_source_death_geometry_and_other_siege_are_rejected(self):
        instance = siege_instance("stone-slammer")
        instance["siege_parameters"]["death"]["effects"].pop()
        with self.assertRaises(InputError):
            compiled_siege(instance, self.catalog)
        instance = siege_instance()
        instance["entity"] = "log-launcher"
        with self.assertRaises(InputError):
            compiled_siege(instance, self.catalog)

    def test_direct_and_siege_delivery_cannot_both_spend_one_payload(self):
        parameters = group_parameters(["payload"])
        with self.assertRaises(InputError):
            self.runtime(parameters=parameters)
        actors, runtime, payload, trace = self.runtime()
        from test_reinforcements import direct_command

        with self.assertRaises(InputError):
            payload.apply_commands([direct_command()], 0, trace)

    def test_siege_slot_identity_and_origin_are_charged_separately(self):
        actors, runtime, payload, _ = self.runtime()
        _, account, army, _ = fixture(self.catalog)
        army["clan_castle"]["troops"] = [{"id": "archer", "level": 1, "count": 1}]
        army["siege"] = {"id": "battle-blimp", "level": 1, "origin": "own"}
        account["levels"]["battle-blimp"] = 1
        bindings = validate_reinforcement_inventory(
            payload.model, actors, army, account, self.catalog
        )
        self.assertEqual(bindings["siege"]["origin"], "siege")
        army["siege"]["id"] = "wall-wrecker"
        account["levels"]["wall-wrecker"] = 1
        with self.assertRaises(InputError):
            validate_reinforcement_inventory(
                payload.model, actors, army, account, self.catalog
            )

    def test_donated_siege_checks_receiving_castle_and_confirmed_account_cap(self):
        instance = siege_instance()
        instance["siege_parameters"].update(origin="donated", donor_town_hall=18)
        actors, _, payload, _ = self.runtime(instance)
        _, account, army, _ = fixture(self.catalog)
        army["clan_castle"]["troops"] = [{"id": "archer", "level": 1, "count": 1}]
        army["siege"] = {"id": "battle-blimp", "level": 1, "origin": "donated"}
        with self.assertRaises(InputError):
            validate_reinforcement_inventory(
                payload.model, actors, army, account, self.catalog
            )
        account["donation_levels"]["battle-blimp"] = 1
        validate_reinforcement_inventory(
            payload.model, actors, army, account, self.catalog
        )
        instance["town_hall"] = 10
        parameters = group_parameters([], "siege")
        parameters.update(receiver_town_hall=10, receiver_clan_castle_level=6)
        self.runtime(instance, parameters=parameters, payloads=[])
        parameters["receiver_clan_castle_level"] = 5
        with self.assertRaises(InputError):
            self.runtime(instance, parameters=parameters, payloads=[])

    def test_battle_profile_does_not_treat_siege_or_payload_as_a_hero(self):
        siege = compiled_siege(siege_instance(), self.catalog)
        payload = compile_payload(payload_instance(), self.catalog)
        mode_rules = read_json(ROOT / "data/mode-rules.json")
        applied = apply_battle_modifiers(
            {"actors": [siege, payload], "traps": []},
            modifier_policy(),
            self.catalog,
            mode_rules,
        )
        actors = {actor["id"]: actor for actor in applied["scene"]["actors"]}
        self.assertEqual(actors["siege"]["hitpoints"], 3000)
        self.assertEqual(actors["siege"]["damage"], 150)
        self.assertEqual(actors["payload"]["hitpoints"], 22)
        self.assertEqual(actors["payload"]["damage"], 8)


if __name__ == "__main__":
    unittest.main()
