"""Catalog turret statistics and explicit travelling defensive-builder repair."""

from copy import deepcopy
from math import hypot
from pathlib import Path
import unittest

from clashlab.builder_huts import BuilderHutCombat, compile_builder_hut
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.hazards import PulsedHazards
from clashlab.spatial import EPSILON, center

from test_adapters import entity_instance, projectile
from test_spatial import synthetic_structure
from test_townhalls import hazard


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "declared-travelling-builder-fixture-not-replay-validated"


def builder_parameters(**changes):
    parameters = {
        "source": SOURCE,
        "acquisition_range_basis": "catalog_builder_range_is_home_hut_acquisition_radius",
        "acquisition_range_multiplier": 1,
        "contact_repair_range_tiles": 0.5,
        "repair_amount_multiplier": 1,
        "repair_interval_multiplier": 1,
        "movement_speed_multiplier": 1,
        "first_repair_delay_seconds": 0.75,
        "target_kinds": ["defense", "building"],
        "excluded_entities": [],
        "selection": "nearest_path_then_instance_id",
        "retention": "until_full_destroyed_or_ineligible",
        "self_hut_policy": "exclude_self_hut",
        "path_policy": "four_neighbor_avoid_structures",
        "idle_policy": "wait_at_current_position",
        "hut_freeze_linkage": "worker_independent_of_hut_freeze",
        "worker_freeze_policy": "pause_movement_and_unfinished_repair_work",
        "stacking_policy": "additive_independent_workers",
        "repair_boost_policy": "ignore_troop_hero_and_hut_damage_healing_bonuses",
        "hut_death_policy": "retire_worker_immediately",
        "lethal_damage_policy": "incoming_lethal_damage_prevents_source_and_target_repair",
    }
    parameters.update(changes)
    return parameters


def hut_instance(**changes):
    instance = entity_instance(
        "hut",
        "builders-hut",
        6,
        "defense",
        x=2,
        y=2,
        attack_parameters={"projectile": projectile()},
        builder_parameters=builder_parameters(),
    )
    instance.update(changes)
    return instance


def compiled_hut(catalog, instance=None):
    instance = instance or hut_instance()
    if not catalog.available("builders-hut", instance["level"], instance["town_hall"]):
        raise InputError("Builder's Hut level is unavailable at declared Town Hall")
    row = catalog.level("builders-hut", instance["level"])
    actor = synthetic_structure(
        instance["id"],
        source=catalog.records["builders-hut"]["source"],
        x=instance["x"],
        y=instance["y"],
        hitpoints=row["hitpoints"] * instance["modifiers"]["hitpoints_multiplier"],
        first_attack_seconds=instance["first_attack_seconds"],
        entity_adapter={
            "entity": "builders-hut",
            "level": instance["level"],
            "town_hall": instance["town_hall"],
            "snapshot_verification": catalog.records["builders-hut"]["verification"],
        },
    )
    compile_builder_hut(
        actor, instance, catalog.entity("builders-hut"), row, instance["modifiers"], 8
    )
    actor.update(
        hp=actor["hitpoints"],
        maximum_hp=actor["hitpoints"],
        frozen_until=0,
        immune_until=0,
        next_attack=actor["first_attack_seconds"],
        target=None,
    )
    return actor


def repair_target(actor_id="target", **changes):
    actor = synthetic_structure(
        actor_id,
        x=7,
        y=2,
        width=2,
        height=2,
        hitpoints=1000,
        hp=500,
        maximum_hp=1000,
        frozen_until=0,
        immune_until=0,
        next_attack=100,
        entity_adapter={"entity": "cannon"},
    )
    actor.update(changes)
    return actor


def run_workers(actors, runtime, end, maximum_step=10):
    time = 0.0
    trace = []
    iterations = 0
    while True:
        iterations += 1
        if iterations > 10000:
            raise AssertionError("Builder scheduler failed to make forward progress")
        runtime.prepare(actors, time, trace)
        for actor_id, amount in runtime.resolve(actors, time, trace).items():
            actor = actors[actor_id]
            actor["hp"] = min(actor["maximum_hp"], actor["hp"] + amount)
        runtime.prepare(actors, time, trace)
        if time >= end - EPSILON:
            return trace
        boundary = runtime.next_boundary(time)
        next_time = min(end, time + maximum_step)
        if boundary is not None:
            next_time = min(next_time, boundary)
        runtime.advance(actors, time, next_time - time, trace)
        time = next_time


def events(trace, event):
    return [item for item in trace if item.get("event") == event]


class BuilderAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_th16_level_six_keeps_turret_and_worker_statistics_separate(self):
        actor = compiled_hut(self.catalog)
        self.assertEqual(actor["hitpoints"], 1900)
        self.assertEqual(actor["damage"], 60)
        self.assertEqual(actor["range"], 7)
        self.assertEqual(actor["attack_interval_seconds"], 0.4)
        self.assertEqual(actor["target_layers"], ["ground", "air"])
        self.assertEqual(actor["attack_model"]["kind"], "single")
        model = actor["builder_hut_model"]
        self.assertEqual(model["repair_amount"], 63.75)
        self.assertEqual(model["repair_interval_seconds"], 0.75)
        self.assertEqual(model["movement_speed_tiles_per_second"], 2.5)
        self.assertEqual(model["acquisition_range_tiles"], 7)
        self.assertEqual(model["contact_repair_range_tiles"], 0.5)

    def test_level_one_is_passive_and_cannot_gain_a_worker(self):
        instance = hut_instance(level=1, attack_parameters={})
        instance.pop("builder_parameters")
        actor = compiled_hut(self.catalog, instance)
        self.assertEqual(actor["kind"], "building")
        self.assertEqual(actor["damage"], 0)
        self.assertNotIn("builder_hut_model", actor)
        self.assertEqual(BuilderHutCombat({actor["id"]: actor}, 20, 20).workers, {})
        with self.assertRaisesRegex(InputError, "Level-one"):
            compiled_hut(self.catalog, hut_instance(level=1, attack_parameters={}))

    def test_town_hall_caps_and_behavior_only_builder_mode_are_rejected(self):
        for instance in (
            hut_instance(level=7),
            hut_instance(town_hall=13),
            hut_instance(mode="builder", statistics_mode="builder"),
        ):
            with self.subTest(instance=instance), self.assertRaises(InputError):
                compiled_hut(self.catalog, instance)

    def test_turret_modifiers_do_not_silently_change_repair_amount(self):
        instance = hut_instance()
        instance["modifiers"].update(
            damage_multiplier=3, attack_interval_multiplier=2, range_multiplier=2
        )
        actor = compiled_hut(self.catalog, instance)
        self.assertEqual(actor["damage"], 180)
        self.assertEqual(actor["range"], 14)
        self.assertEqual(actor["attack_interval_seconds"], 0.8)
        self.assertEqual(actor["builder_hut_model"]["repair_amount"], 63.75)
        self.assertEqual(actor["builder_hut_model"]["repair_interval_seconds"], 0.75)

    def test_missing_travel_policy_and_magical_ranged_repair_are_rejected(self):
        for failure in ("no_path", "repair_range", "walls"):
            with self.subTest(failure=failure):
                instance = hut_instance()
                parameters = instance["builder_parameters"]
                if failure == "no_path":
                    parameters.pop("path_policy")
                elif failure == "repair_range":
                    parameters["contact_repair_range_tiles"] = 7
                else:
                    parameters["target_kinds"].append("wall")
                with self.assertRaises(InputError):
                    compiled_hut(self.catalog, instance)

    def test_publisher_and_numeric_provenance_are_copied_not_current_certification(
        self,
    ):
        instance = hut_instance()
        actor = compiled_hut(self.catalog, instance)
        instance["builder_parameters"]["excluded_entities"].append("cannon")
        self.assertEqual(actor["builder_hut_model"]["excluded_entities"], [])
        self.assertEqual(
            actor["entity_adapter"]["snapshot_verification"], "unverified_snapshot"
        )
        self.assertIn(
            "supercell.com",
            actor["entity_adapter"]["builder_statistics"]["publisher_behavior_source"],
        )


class BuilderWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def runtime(self, targets=None, shared_hazards=None, **parameters):
        hut = compiled_hut(
            self.catalog,
            hut_instance(builder_parameters=builder_parameters(**parameters)),
        )
        actors = {hut["id"]: hut}
        actors.update(
            {
                actor["id"]: actor
                for actor in (targets if targets is not None else [repair_target()])
            }
        )
        return actors, BuilderHutCombat(actors, 20, 20, shared_hazards), []

    def test_repair_requires_actual_travel_then_a_repair_swing(self):
        actors, runtime, trace = self.runtime()
        runtime.prepare(actors, 0, trace)
        arrival = runtime.next_boundary(0)
        self.assertAlmostEqual(arrival, (hypot(0.5, 0.5) + 3) / 2.5)
        self.assertEqual(runtime.resolve(actors, 0, trace), {})
        runtime.advance(actors, 0, arrival, trace)
        runtime.prepare(actors, arrival, trace)
        self.assertEqual(runtime.resolve(actors, arrival, trace), {})
        self.assertAlmostEqual(runtime.next_boundary(arrival), arrival + 0.75)
        amounts = runtime.resolve(actors, arrival + 0.75, trace)
        self.assertEqual(amounts, {"target": 63.75})
        self.assertEqual(actors["target"]["hp"], 500)
        self.assertEqual(actors["hut"]["next_attack"], 0)

    def test_coarse_and_fine_steps_match_arrival_repairs_and_final_health(self):
        outcomes = []
        for step in (10, 0.031):
            actors, runtime, _ = self.runtime()
            trace = run_workers(actors, runtime, 4, step)
            outcomes.append(
                (
                    actors["target"]["hp"],
                    [
                        round(event["time_seconds"], 7)
                        for event in events(trace, "builder_repair")
                    ],
                )
            )
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0][0], 691.25)

    def test_self_hut_repair_is_an_explicit_policy(self):
        for policy, expected in (("exclude_self_hut", None), ("allow_self_hut", "hut")):
            with self.subTest(policy=policy):
                actors, runtime, trace = self.runtime([], self_hut_policy=policy)
                actors["hut"]["hp"] -= 100
                runtime.prepare(actors, 0, trace)
                self.assertEqual(runtime.states["hut"]["target"], expected)
                self.assertEqual(
                    bool(runtime.resolve(actors, 0.75, trace)), expected is not None
                )

    def test_walls_units_enemy_full_dead_excluded_and_out_of_radius_are_not_targets(
        self,
    ):
        targets = [
            repair_target("wall", x=5, kind="wall"),
            repair_target("unit", x=5, kind="unit", blocking=False),
            repair_target("enemy", x=5, team="attack"),
            repair_target("full", x=5, hp=1000),
            repair_target("dead", x=5, hp=0),
            repair_target("far", x=15),
            repair_target("excluded", x=5),
        ]
        actors, runtime, trace = self.runtime(targets, excluded_entities=["cannon"])
        runtime.prepare(actors, 0, trace)
        self.assertIsNone(runtime.states["hut"]["target"])
        self.assertEqual(runtime.resolve(actors, 10, trace), {})

    def test_friendly_wall_traversal_policy_changes_reachability_but_never_repairs_walls(
        self,
    ):
        walls = [
            repair_target(f"wall-{row}", x=6, y=row, width=1, height=1, kind="wall")
            for row in range(20)
        ]
        for policy, expected in (
            ("four_neighbor_avoid_structures", None),
            ("four_neighbor_ignore_friendly_walls", "target"),
        ):
            with self.subTest(policy=policy):
                actors, runtime, trace = self.runtime(
                    [repair_target(), *deepcopy(walls)], path_policy=policy
                )
                runtime.prepare(actors, 0, trace)
                self.assertEqual(runtime.states["hut"]["target"], expected)

    def test_retention_keeps_target_until_full_then_reselects(self):
        targets = [
            repair_target("a-first"),
            repair_target("b-second", x=2, y=7, hp=1000),
        ]
        actors, runtime, trace = self.runtime(targets)
        runtime.prepare(actors, 0, trace)
        actors["b-second"]["hp"] = 100
        runtime.prepare(actors, 0.1, trace)
        self.assertEqual(runtime.states["hut"]["target"], "a-first")
        actors["a-first"]["hp"] = 1000
        runtime.prepare(actors, 0.2, trace)
        self.assertEqual(runtime.states["hut"]["target"], "b-second")

    def test_multiple_workers_add_repairs_and_ignore_hut_or_recipient_heal_bonuses(
        self,
    ):
        parameters = builder_parameters(
            contact_repair_range_tiles=1, first_repair_delay_seconds=0
        )
        first = compiled_hut(self.catalog, hut_instance(builder_parameters=parameters))
        second = compiled_hut(
            self.catalog, hut_instance(id="hut-two", x=5, builder_parameters=parameters)
        )
        target = repair_target(x=4, width=1, _buff_healing_multiplier=100)
        first["_buff_healing_multiplier"] = 50
        second["_buff_damage_multiplier"] = 99
        actors = {actor["id"]: actor for actor in (first, second, target)}
        runtime = BuilderHutCombat(actors, 20, 20)
        trace = []
        runtime.prepare(actors, 0, trace)
        self.assertEqual(runtime.resolve(actors, 0, trace), {"target": 127.5})
        self.assertEqual(len(events(trace, "builder_repair")), 2)
        self.assertEqual(set(actors), {"hut", "hut-two", "target"})
        self.assertTrue(
            all(
                not state["targetable"]
                for state in runtime.result()["workers"].values()
            )
        )

    def test_hut_death_retires_worker_and_pending_lethal_damage_blocks_repair(self):
        for dying in ("hut", "target"):
            with self.subTest(dying=dying):
                actors, runtime, trace = self.runtime(first_repair_delay_seconds=0)
                runtime.prepare(actors, 0, trace)
                arrival = runtime.next_boundary(0)
                runtime.advance(actors, 0, arrival, trace)
                runtime.prepare(actors, arrival, trace)
                self.assertEqual(
                    runtime.resolve(
                        actors, arrival, trace, {dying: actors[dying]["hp"]}
                    ),
                    {},
                )
        actors["hut"]["hp"] = 0
        runtime.prepare(actors, arrival, trace)
        self.assertEqual(runtime.states["hut"]["phase"], "retired")
        self.assertEqual(runtime.resolve(actors, arrival + 10, trace), {})
        self.assertIsNone(runtime.next_boundary(arrival))

    def test_area_freeze_hits_roaming_worker_by_position_without_freezing_home_hut(
        self,
    ):
        actors, runtime, trace = self.runtime()
        runtime.prepare(actors, 0, trace)
        arrival = runtime.next_boundary(0)
        runtime.advance(actors, 0, arrival, trace)
        runtime.prepare(actors, arrival, trace)
        worker = runtime.workers["hut::builder"]
        runtime.apply_effects(
            [
                {
                    "id": "freeze-worker",
                    "kind": "area_freeze",
                    "duration_seconds": 1,
                    "area": {
                        "x": worker["x"],
                        "y": worker["y"],
                        "radius": 0.1,
                        "target_team": "defense",
                        "target_kinds": ["defense"],
                        "target_layers": ["ground"],
                    },
                }
            ],
            actors,
            arrival + 0.25,
            trace,
        )
        self.assertEqual(actors["hut"]["frozen_until"], 0)
        self.assertAlmostEqual(worker["frozen_until"], arrival + 1.25)
        self.assertAlmostEqual(worker["next_attack"], arrival + 1.75)
        self.assertEqual(runtime.resolve(actors, arrival + 1, trace), {})
        self.assertEqual(
            runtime.resolve(actors, arrival + 1.75, trace), {"target": 63.75}
        )

    def test_direct_hut_freeze_is_independent_unless_linkage_is_selected(self):
        for linkage, expected in (
            ("worker_independent_of_hut_freeze", 0),
            ("hut_freeze_also_pauses_worker", 5),
        ):
            with self.subTest(linkage=linkage):
                actors, runtime, trace = self.runtime(hut_freeze_linkage=linkage)
                actors["hut"]["frozen_until"] = 5
                runtime.prepare(actors, 0, trace)
                self.assertEqual(
                    runtime.workers["hut::builder"]["frozen_until"], expected
                )
                runtime.apply_effects(
                    [
                        {
                            "id": "freeze-hut",
                            "kind": "freeze",
                            "targets": ["hut"],
                            "duration_seconds": 5,
                        }
                    ],
                    actors,
                    0,
                    trace,
                )
                self.assertEqual(
                    runtime.workers["hut::builder"]["frozen_until"], expected
                )

    def test_freeze_during_travel_pauses_real_position_and_moves_arrival_boundary(self):
        actors, runtime, trace = self.runtime()
        runtime.prepare(actors, 0, trace)
        initial_arrival = runtime.next_boundary(0)
        runtime.advance(actors, 0, 0.5, trace)
        point = center(runtime.workers["hut::builder"])
        runtime.freeze(["hut::builder"], 0.5, 1, trace)
        runtime.advance(actors, 0.5, 1, trace)
        self.assertEqual(center(runtime.workers["hut::builder"]), point)
        runtime.prepare(actors, 1.5, trace)
        self.assertAlmostEqual(runtime.next_boundary(1.5), initial_arrival + 1)


class BuilderPoisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def field(self):
        field = hazard(
            duration_seconds=20,
            maximum_dps=999999,
            movement_multiplier=0.5,
            attack_rate_multiplier=0.5,
        )
        field["area"].update(x=5, y=3.5, radius=0.5, target_team="defense")
        return field

    def test_shared_poison_uses_status_only_workers_and_exact_crossings(self):
        outcomes = []
        for step in (10, 0.019):
            hut = compiled_hut(self.catalog)
            target = repair_target()
            actors = {actor["id"]: actor for actor in (hut, target)}
            shared = PulsedHazards(actors, [self.field()])
            runtime = BuilderHutCombat(actors, 20, 20, shared)
            trace = run_workers(actors, runtime, 5, step)
            worker = runtime.workers["hut::builder"]
            self.assertEqual(worker["hp"], 1)
            self.assertFalse(
                any(event.get("event") == "hazard_pulse" for event in trace)
            )
            self.assertEqual(runtime.result()["status_only_fields"], ["poison"])
            outcomes.append(
                (
                    target["hp"],
                    [
                        (round(event["time_seconds"], 6), event["attack_rate"])
                        for event in events(trace, "hazard_status_change")
                    ],
                )
            )
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual([rate for _, rate in outcomes[0][1]], [0.5, 1])

    def test_worker_exclusion_and_opposing_poison_team_are_respected(self):
        for failure in ("excluded", "opposing_team"):
            with self.subTest(failure=failure):
                hut = compiled_hut(self.catalog)
                target = repair_target()
                actors = {actor["id"]: actor for actor in (hut, target)}
                field = self.field()
                if failure == "excluded":
                    field["excluded_classes"].append("builder")
                else:
                    field["area"]["target_team"] = "attack"
                    # The real shared provider also contains attacking actors.
                    actors["team-anchor"] = repair_target(
                        "team-anchor", team="attack", hp=1000
                    )
                shared = PulsedHazards(actors, [field])
                runtime = BuilderHutCombat(actors, 20, 20, shared)
                trace = run_workers(actors, runtime, 3)
                self.assertEqual(events(trace, "hazard_status_change"), [])


if __name__ == "__main__":
    unittest.main()
