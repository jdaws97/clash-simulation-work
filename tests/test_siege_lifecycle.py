"""Synthetic lifecycle crossings; inert child fixtures do not certify troop AI.

Stationary carriers are initialized at the domain boundary because the shared
loader's stationary-point change is owned by the integration lead.
"""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.reinforcements import (
    ReinforcementCombat,
    compile_attacking_reinforcements,
)
from clashlab.siege_barrels import (
    barrel_generated_requirements,
    attach_barrel_member,
    StreamedReinforcementCombat,
)
from clashlab.siege_lifecycle import (
    compile_permanent_siege,
    permanent_siege_runtime,
    validate_siege_choices,
    siege_effect_eligible,
)
from clashlab.siege_extensions import attach_barracks_member
from clashlab.spatial import _load_actors, _select_target

from test_adapters import entity_instance
from test_reinforcements import (
    SOURCE,
    compile_payload,
    group_parameters,
    payload_instance,
    target_actor,
)
from test_siege_machines import release_command


ROOT = Path(__file__).resolve().parents[1]


def release_policy(ids, displacement=3):
    return {
        "offsets": {key: {"x": 0, "y": 0} for key in ids},
        "maximum_displacement_tiles": displacement,
        "position_policy": "explicit_offset_then_nearest_clear_ground_cell",
        "blocked_position": "hold_member_until_legal_point_exists",
    }


def barrel_instance(catalog, entity="troop-launcher", flight=0.5):
    row = catalog.level(entity, 1)
    children = barrel_generated_requirements("siege", entity, row, catalog)
    return entity_instance(
        "siege",
        entity,
        1,
        "attack",
        town_hall=18,
        x=1.5,
        y=7.5,
        attack_parameters={},
        siege_experimental_opt_in=True,
        siege_parameters={
            "source": SOURCE,
            "origin": "own",
            "donor_town_hall": None,
            "payload_group_id": "reinforcements",
            "behavior": {
                "source": SOURCE,
                "experimental": True,
                "targeting": "nearest_active_ally_for_launcher_nearest_defense_for_wagon",
                "minimum_range_tiles": 0,
                "maximum_range_tiles": 10,
                "first_launch_delay_seconds": 0,
                "flight_seconds": flight,
                "impact_radius_tiles": 1,
                "maximum_lifetime_seconds": row.get("lifetime"),
                "generated_release": release_policy(
                    [child["actor_id"] for child in children]
                ),
                "cc_per_barrel": "one_ordered_member",
                "source_loss": "launched_barrels_continue_cancel_unlaunched_generated",
                "exhaustion": "terminate_release_remaining_cc",
                "no_target": "wait_without_spending_barrel",
                "death_boundary_order": "termination_before_new_launch",
            },
        },
    )


def extended_instance(catalog, entity):
    parameters = {
        "source": SOURCE,
        "origin": "own",
        "donor_town_hall": None,
        "payload_group_id": "reinforcements",
        "range_tiles": 0 if entity == "siege-barracks" else 10,
        "minimum_range_tiles": 0,
        "targeting": {
            "hall_actor_id": None,
            "arrival_radius_tiles": None,
            "hall_loss": "not_applicable",
        },
        "termination": {
            "decay_basis": {
                "siege-barracks": "snapshot_hitpoints_over_entity_lifetime",
                "flame-flinger": "snapshot_hpDecayPerSecond",
                "battle-drill": "none",
            }[entity],
            "decay_interval_seconds": 1,
            "lifetime_basis": (
                "none" if entity == "battle-drill" else "snapshot_lifetime"
            ),
        },
        "spell_response": {
            "beneficial_fields": "immune_to_healing_rage_and_haste",
            "hostile_effects": "explicit_shared_status_and_hazard_policies",
        },
    }
    if entity == "flame-flinger":
        parameters["behavior"] = {
            "kind": "incendiary_burst",
            "shot_offsets_seconds": [0, 0.1, 0.2],
            "impact_delay_seconds": 0,
            "projectile_speed_tiles_per_second": 100,
            "impact_radius_tiles": 1,
            "flame_radius_tiles": 1,
            "flame_duration_seconds": 2,
            "flame_interval_seconds": 0.5,
            "flame_dps_fractions": [0.5, 1],
            "flame_composition": "strongest_per_source_sum_between_sources",
            "source_loss": "launched_impacts_and_flames_continue",
            "burst_cancellation": "cancel_unlaunched_on_death_or_freeze",
            "membership": "pulse_time_minimum_point_to_footprint_distance",
            "statistics_mapping": "damagePerHit_per_spirit_flameMaxDps_per_source",
        }
    elif entity == "battle-drill":
        parameters["range_tiles"] = 1
        parameters["behavior"] = {
            "kind": "burrow_surface_stun",
            "stun_seconds": 2,
            "stun_radius_tiles": 0,
            "stun_source": SOURCE,
            "stun_composition": "maximum_remaining_duration_defenses_only",
            "travel": "direct_burrow_ignoring_blocking_footprints",
            "underground_effects": "exclude_direct_splash_status_hazard_and_trap_effects",
            "retarget": "retained_eligible_defense_then_other_structure",
        }
    else:
        row = catalog.level(entity, 1)
        schedule = [
            {
                "actor_id": f"generated-{name}-{ordinal}",
                "entity": name,
                "level": 1,
                "delay_seconds": ordinal,
            }
            for name, count in (
                ("pekka", row["pekkasSpawned"]),
                ("wizard", row["wizardsSpawned"]),
            )
            for ordinal in range(count)
        ]
        schedule.sort(key=lambda member: member["delay_seconds"])
        parameters["behavior"] = {
            "kind": "stationary_generation",
            "schedule": schedule,
            "release": release_policy([member["actor_id"] for member in schedule]),
            "generation_clock": "continues_during_freeze",
            "termination": "cancel_unproduced_preserve_produced",
            "simultaneous_boundary": "carrier_termination_precedes_generation",
            "level_basis": "attacker_confirmed_troop_level",
        }
    return entity_instance(
        "siege",
        entity,
        1,
        "attack",
        town_hall=18,
        x=1.5,
        y=7.5,
        attack_parameters={},
        siege_experimental_opt_in=True,
        siege_parameters=parameters,
    )


def compile_carrier(instance, catalog):
    entity = catalog.entity(instance["entity"])
    row = catalog.level(instance["entity"], instance["level"])
    actor = {
        "id": instance["id"],
        "source": catalog.records[instance["entity"]]["source"],
        "team": "attack",
        "hitpoints": row["hitpoints"],
        "first_attack_seconds": 0,
        "spawn_seconds": instance["spawn_seconds"],
        "x": instance["x"],
        "y": instance["y"],
        "counts_for_destruction": False,
        "entity_adapter": {
            "entity": entity["id"],
            "level": instance["level"],
            "town_hall": instance["town_hall"],
        },
    }
    return compile_permanent_siege(
        actor, instance, entity, row, instance["modifiers"], catalog, 8
    )


def inert_child(child, air=False):
    """Deliberately inert synthetic troop; only release ownership is under test."""
    actor = target_actor(child["actor_id"])
    actor.update(
        team="attack",
        kind="unit",
        layer="air" if air else "ground",
        movement="air" if air else "ground",
        speed=1,
        x=1.5,
        y=1.5,
        width=0,
        height=0,
        blocking=False,
        counts_for_destruction=False,
        spawn_seconds="controlled",
        entity_adapter={"entity": child["entity"], "level": child["level"]},
    )
    return actor


class SiegeLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def runtime(self, instance, payload_count=2, blocked=False):
        carrier = compile_carrier(instance, self.catalog)
        children = []
        if "generated_requirements" in carrier["siege_model"]:
            for child in carrier["siege_model"]["generated_requirements"]:
                actor = inert_child(child, air=instance["entity"] == "sky-wagon")
                attach_barrel_member(
                    actor,
                    {
                        "barrel_member_parameters": {
                            "carrier_id": "siege",
                            "barrel_index": child["barrel_index"],
                        }
                    },
                )
                children.append(actor)
        elif instance["entity"] == "siege-barracks":
            for child in instance["siege_parameters"]["behavior"]["schedule"]:
                actor = inert_child(child)
                attach_barracks_member(
                    actor,
                    {
                        "level": 1,
                        "town_hall": 18,
                        "barracks_member_parameters": {
                            "source": SOURCE,
                            "carrier_id": "siege",
                            "level_basis": "attacker_confirmed_troop_level",
                        },
                    },
                    self.catalog.entity(child["entity"]),
                    self.catalog.level(child["entity"], 1),
                    self.catalog,
                )
                children.append(actor)
        payloads = [
            payload_instance(f"payload-{index}") for index in range(payload_count)
        ]
        ally = inert_child({"actor_id": "ally", "entity": "archer", "level": 1})
        ally.update(spawn_seconds=0, x=4.5, y=7.5)
        extras = [ally, target_actor("defense", kind="defense", x=6, y=7)]
        if blocked:
            extras.append(target_actor("blocker", x=4, y=7))
        # Shared stationary-point validation is an integration requirement. The
        # loader initializes a moving point, then the domain fixture restores
        # the already-compiled stationary role. No production code does this.
        loaded_carrier = deepcopy(carrier)
        stationary = carrier["movement"] == "stationary"
        if stationary:
            loaded_carrier.update(movement="ground", speed=1)
        actors = _load_actors(
            {
                "actors": [
                    loaded_carrier,
                    *children,
                    *(compile_payload(member, self.catalog) for member in payloads),
                    *extras,
                ]
            },
            30,
            20,
        )
        if stationary:
            actors["siege"].update(movement="stationary", speed=0)
        parameters = group_parameters([member["id"] for member in payloads], "siege")
        if blocked:
            parameters["release"]["maximum_displacement_tiles"] = 0
        model = compile_attacking_reinforcements(parameters, self.catalog, actors)
        runtime = permanent_siege_runtime(
            actors, _select_target, ReinforcementCombat(actors, model, 30, 20), 30, 20
        )
        trace = []
        runtime.prepare(actors, 0, trace)
        return actors, runtime, runtime.reinforcements, trace

    def test_stored_choices_are_not_multiple_deployments_and_unknowns_reject(self):
        choices = [
            {"id": entity, "level": 1, "origin": "own"}
            for entity in ("siege-barracks", "troop-launcher", "sky-wagon")
        ]
        self.assertEqual(
            validate_siege_choices(choices, choices[1], self.catalog),
            {"stored_count": 3, "deployable_count": 1},
        )
        with self.assertRaises(InputError):
            validate_siege_choices(
                choices,
                {"id": "battle-blimp", "level": 1, "origin": "own"},
                self.catalog,
            )
        instance = barrel_instance(self.catalog)
        instance["siege_experimental_opt_in"] = False
        with self.assertRaises(InputError):
            compile_carrier(instance, self.catalog)

    def test_launcher_launch_manual_loss_and_finite_cc_conservation(self):
        actors, runtime, payload, trace = self.runtime(barrel_instance(self.catalog))
        target, route = runtime.select_target(actors["siege"], actors, 0, set(), 30, 20)
        self.assertEqual((target["id"], route), ("ally", []))
        runtime.launch(actors["siege"], target, actors, 0, trace)
        self.assertEqual(payload.member_states["payload-0"]["phase"], "in_flight")
        runtime.apply_commands([release_command(0.1)], 0.1, trace)
        runtime.prepare(actors, 0.2, trace)
        self.assertEqual(payload.member_states["payload-1"]["phase"], "released")
        self.assertEqual(payload.member_states["payload-0"]["phase"], "in_flight")
        runtime.prepare(actors, 0.5, trace)
        self.assertEqual(len(payload.state["released"]), 2)
        self.assertEqual(len(set(payload.state["released"])), 2)
        self.assertEqual(
            sum(member["phase"] == "released" for member in runtime.generated.values()),
            7,
        )
        self.assertEqual(
            sum(
                member["phase"] == "cancelled" for member in runtime.generated.values()
            ),
            28,
        )
        self.assertFalse(
            payload.begin_release(0.5, {"x": 1, "y": 1}, "duplicate", "siege", trace)
        )
        with self.assertRaises(InputError):
            runtime.apply_commands([release_command(0.5)], 0.5, trace)

    def test_launcher_no_ally_waits_and_expiry_releases_only_cc(self):
        actors, runtime, payload, trace = self.runtime(barrel_instance(self.catalog))
        actors["ally"]["hp"] = 0
        target, route = runtime.select_target(actors["siege"], actors, 0, set(), 30, 20)
        self.assertIsNone(target)
        self.assertEqual(route, [])
        runtime.prepare(actors, 80, trace)
        self.assertEqual(
            runtime.states["siege"]["termination_reason"], "lifetime_expired"
        )
        runtime.prepare(actors, 80.4, trace)
        self.assertEqual(len(payload.state["released"]), 2)
        self.assertTrue(
            all(member["phase"] == "cancelled" for member in runtime.generated.values())
        )
        self.assertEqual(runtime.continuation_reasons(80.4), [])

    def test_wagon_exhaustion_preserves_flights_and_launch_damage_after_loss(self):
        actors, runtime, payload, trace = self.runtime(
            barrel_instance(self.catalog, "sky-wagon"), payload_count=6
        )
        for time in (0, 8, 16, 24):
            runtime.prepare(actors, time, trace)
            runtime.launch(actors["siege"], actors["defense"], actors, time, trace)
        self.assertEqual(
            runtime.states["siege"]["termination_reason"], "barrels_exhausted"
        )
        self.assertEqual(runtime.states["siege"]["weapon_launches"], 4)
        self.assertTrue(runtime.continuation_reasons(24))
        self.assertGreater(runtime.resolve(actors, 24.5, trace)["defense"], 0)
        runtime.prepare(actors, 24.6, trace)
        self.assertEqual(len(payload.state["released"]), 6)
        self.assertEqual(
            sum(member["phase"] == "released" for member in runtime.generated.values()),
            16,
        )
        self.assertEqual(runtime.continuation_reasons(24.6), [])

    def test_tiny_positive_flight_is_not_resolved_at_launch(self):
        actors, runtime, payload, trace = self.runtime(
            barrel_instance(self.catalog, flight=1e-12)
        )
        runtime.launch(actors["siege"], actors["ally"], actors, 0, trace)
        runtime.prepare(actors, 0, trace)
        self.assertEqual(payload.member_states["payload-0"]["phase"], "in_flight")
        self.assertEqual(runtime.next_boundary(0), 1e-12)
        runtime.prepare(actors, 1e-12, trace)
        self.assertEqual(payload.member_states["payload-0"]["phase"], "released")

    def test_blocked_cc_holds_its_capture_and_cannot_spend_twice(self):
        actors, runtime, payload, trace = self.runtime(
            barrel_instance(self.catalog), blocked=True
        )
        runtime.launch(actors["siege"], actors["ally"], actors, 0, trace)
        runtime.prepare(actors, 0.5, trace)
        self.assertEqual(payload.member_states["payload-0"]["phase"], "in_flight")
        actors["blocker"]["hp"] = 0
        runtime.prepare(actors, 0.5, trace)
        self.assertEqual(payload.member_states["payload-0"]["released_at"], 0.5)
        self.assertEqual(
            (actors["payload-0"]["x"], actors["payload-0"]["y"]), (4.5, 7.5)
        )
        with self.assertRaises(InputError):
            payload.claim_barrel(1, 2, {"x": 1, "y": 1}, "other-carrier", trace)

    def test_flinger_launched_impacts_fields_survive_carrier_and_stun_draft_attribution(
        self,
    ):
        actors, runtime, _, trace = self.runtime(
            extended_instance(self.catalog, "flame-flinger")
        )
        runtime.launch(actors["siege"], actors["defense"], actors, 0, trace)
        runtime.resolve(actors, 0, trace)
        actors["siege"]["hp"] = 0
        runtime.prepare(actors, 0.01, trace)
        self.assertGreater(runtime.resolve(actors, 0.5, trace)["defense"], 0)
        self.assertGreater(runtime.resolve(actors, 1, trace)["defense"], 0)
        self.assertTrue(runtime.continuation_reasons(1))
        runtime.resolve(actors, 3, trace)
        self.assertEqual(runtime.continuation_reasons(3), [])
        cancelled = [
            event
            for event in trace
            if event["event"] == "flinger_unlaunched_shot_cancelled"
        ]
        self.assertEqual(len(cancelled), 2)

    def test_barracks_generation_freeze_termination_order_and_drill_surface(self):
        actors, runtime, payload, trace = self.runtime(
            extended_instance(self.catalog, "siege-barracks")
        )
        actors["siege"]["frozen_until"] = 10
        runtime.prepare(actors, 1, trace)
        self.assertEqual(
            sum(
                state["phase"] == "released"
                for state in runtime.generated["siege"]["members"].values()
            ),
            3,
        )
        runtime.apply_commands([release_command(2)], 2, trace)
        runtime.prepare(actors, 2, trace)
        self.assertEqual(
            sum(
                state["phase"] == "cancelled"
                for state in runtime.generated["siege"]["members"].values()
            ),
            4,
        )
        runtime.prepare(actors, 2.1, trace)
        runtime.prepare(actors, 2.5, trace)
        self.assertEqual(len(payload.state["released"]), 2)
        actors, runtime, _, trace = self.runtime(
            extended_instance(self.catalog, "battle-drill")
        )
        self.assertTrue(actors["siege"]["_siege_underground"])
        self.assertFalse(siege_effect_eligible(actors["siege"], "defense_targeting"))
        self.assertFalse(siege_effect_eligible(actors["siege"], "trap"))
        policy = actors["siege"]["siege_model"]["parameters"]["behavior"]
        policy.pop("underground_effects")
        with self.assertRaises(InputError):
            siege_effect_eligible(actors["siege"], "trap")
        actors["siege"].update(x=5.5, y=7.5)
        runtime.prepare(actors, 1, trace)
        self.assertFalse(actors["siege"]["_siege_underground"])
        self.assertEqual(actors["defense"]["frozen_until"], 3)
        self.assertFalse(siege_effect_eligible(actors["siege"], "spell"))


if __name__ == "__main__":
    unittest.main()
