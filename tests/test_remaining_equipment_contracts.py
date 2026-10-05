"""Six bounded domain acceptance probes; synthetic, not full-battle calibration."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError
from clashlab.damage_receipts import DamageReceipts
from clashlab.dark_crown import DarkCrownLedger, POLICIES as CROWN
from clashlab.hit_status import HitStatusCombat
from clashlab.monolith_arrow import MonolithArrowLedger, POLICIES as MONOLITH
from clashlab.poison_lizard import (
    PoisonLizardExposure,
    POLICIES as LIZARD,
    compile_model as compile_lizard,
)
from clashlab.rocket_backpack import (
    RocketBackpackMotion,
    POLICIES as ROCKET,
    compile_model as compile_rocket,
)
from clashlab.spatial import _apply_health, _load_actors

from test_spatial import synthetic_unit, synthetic_structure
from test_hero_pets import projectile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-gap-lifecycle-acceptance-not-game-calibration"


def parameters(policies, **values):
    return {"source": SOURCE, **policies, **values}


def lizard_parameters():
    return parameters(
        LIZARD,
        duration_seconds=2,
        pulse_seconds=0.25,
        defender_radius_tiles=6,
        ramp_knots=[
            {"seconds": 0, "fraction_of_max_dps": 0},
            {"seconds": 1, "fraction_of_max_dps": 1},
        ],
    )


def rocket_parameters():
    return parameters(
        ROCKET,
        endpoint_tiles=[10, 3.5],
        speed_tiles_per_second=10,
        damage_source="pinned_extraction_post_may_2026",
        profile_factor=1,
    )


def actors_for(items):
    for actor in items:
        actor["minimum_range"] = 0
        actor.setdefault(
            "attack_model",
            (
                {"kind": "none", "source": SOURCE}
                if actor["damage"] == 0
                else {
                    "kind": "single",
                    "source": SOURCE,
                    "target_kinds": actor["target_priorities"],
                    "target_layers": actor["target_layers"],
                    "maximum_hp_fraction": 0,
                    "projectile": projectile(),
                }
            ),
        )
    return _load_actors({"actors": items}, 14, 10)


def settle(actors, receipts, damage, time):
    settled = receipts.settle(actors, damage, time)
    _apply_health(actors, damage, {}, time)
    return settled


def run_lizard(catalog, step):
    actors = actors_for(
        [
            synthetic_unit(
                "lizard",
                damage=10,
                target_priorities=["unit", "defense"],
                target_layers=["ground", "air"],
                attack_model={
                    "kind": "single",
                    "source": SOURCE,
                    "target_kinds": ["unit", "defense"],
                    "target_layers": ["ground", "air"],
                    "maximum_hp_fraction": 0,
                    "projectile": projectile(),
                },
            ),
            synthetic_unit("defender", team="defense", hitpoints=1000, x=4, damage=0),
            synthetic_structure("building", x=8, hitpoints=10000),
        ]
    )
    status = HitStatusCombat(actors)
    runtime = PoisonLizardExposure(
        catalog,
        {"lizard": {"level": 10, "town_hall": 16, "parameters": lizard_parameters()}},
        {"defender": "hero", "building": "building"},
        status,
    )
    combat = PatternCombat(actors)
    receipts = DamageReceipts()
    combat.damage_receipts = receipts
    trace, all_receipts = [], []
    time = 0
    actions = [0, 0.5, 0.75, 1, 1.5, 2.5]
    fired = set()
    while time <= 2.5 + 1e-10:
        event = next(
            (t for t in actions if abs(t - time) < 1e-10 and t not in fired), None
        )
        if event is not None:
            fired.add(event)
            if event in {0, 0.5}:
                combat.launch(actors["lizard"], actors["defender"], actors, time, trace)
                damage = combat.resolve(
                    actors,
                    time,
                    trace,
                    status_callback=lambda packet, target, actors, t, trace: runtime.impact(
                        f"impact-{event}", packet, target, actors, t, trace
                    ),
                )
                all_receipts.extend(settle(actors, receipts, damage, time))
                # Replaying a receipt must not extend expiry or add damage.
                runtime.impact(
                    f"impact-{event}",
                    {"source": "lizard", "source_team": "attack"},
                    actors["defender"],
                    actors,
                    time,
                    trace,
                )
            elif event == 0.75:
                amount = receipts.register(
                    actors["lizard"],
                    10000,
                    time,
                    source_id="defender",
                    source_team="defense",
                    origin="weapon",
                )
                all_receipts.extend(settle(actors, receipts, {"lizard": amount}, time))
            elif event == 1:
                actors["defender"]["_recalled"] = True
            elif event == 1.5:
                actors["defender"]["_recalled"] = False
        damage = runtime.resolve(actors, time, trace, receipts)
        all_receipts.extend(settle(actors, receipts, damage, time))
        runtime.after_health(actors)
        status.prepare(actors, time, trace)
        if time >= 2.5 - 1e-10:
            break
        future = [time + step, 2.5, *(t for t in actions if t > time + 1e-10)]
        if runtime.next_boundary() is not None:
            future.append(runtime.next_boundary())
        time = min(future)
    return {
        "hp": actors["defender"]["hp"],
        "pulses": [
            e["time_seconds"] for e in trace if e["event"] == "poison_lizard_pulse"
        ],
        "poison_loss": sum(
            r["actual_health_loss"]
            for r in all_receipts
            if r["source_id"] == "poison-lizard:lizard"
        ),
        "source_hp": actors["lizard"]["hp"],
        "slow": actors["defender"]["_hit_status_attack_rate"],
        "continuation": runtime.continuation_reasons(),
        "result": runtime.result(),
    }


def run_rocket(catalog, step):
    actors = actors_for(
        [
            synthetic_unit("duke", x=0.5, layer="air", movement="air"),
            synthetic_structure("first", x=4, hitpoints=10000),
            synthetic_structure("second", x=8, hitpoints=10000),
        ]
    )
    actors["duke"]["hero_model"] = {"entity": "dragon-duke"}
    actors["first"]["immune_until"] = 1  # One protected contact, never re-hit.
    runtime = RocketBackpackMotion(catalog, "duke", 27, 16, rocket_parameters(), 14, 10)
    receipts = DamageReceipts()
    trace, all_receipts = [], []
    runtime.activate("shared-charge", actors["duke"], 0, trace)
    time = 0
    while True:
        x, y = runtime.position(time)
        actors["duke"].update(x=x, y=y)
        damage = runtime.resolve(actors, time, trace, receipts)
        all_receipts.extend(settle(actors, receipts, damage, time))
        boundary = runtime.next_boundary()
        if boundary is None:
            break
        crossing = runtime.first_crossing_delay(
            actors, {}, {}, time, min(step, boundary - time)
        )
        time = min(
            time + step, boundary, time + crossing if crossing is not None else boundary
        )
    return {
        "contacts": [
            (e["target"], e["time_seconds"])
            for e in trace
            if e["event"] == "rocket_backpack_contact"
        ],
        "hp": {key: actors[key]["hp"] for key in ("first", "second")},
        "loss": sum(r["actual_health_loss"] for r in all_receipts),
        "demands": runtime.demands(time),
        "result": runtime.result(),
    }


class RemainingEquipmentContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_lizard_shared_hit_refresh_source_loss_recall_expiry_two_steps(self):
        results = [run_lizard(self.catalog, step) for step in (0.017, 0.25)]
        for result in results:
            self.assertAlmostEqual(result["hp"], 815)
            self.assertAlmostEqual(result["poison_loss"], 165)
            self.assertEqual(result["source_hp"], 0)
            self.assertEqual(result["slow"], 1)
            self.assertEqual(result["continuation"], [])
            self.assertEqual(len(result["pulses"]), 7)
            json.dumps(result)
        for a, b in zip(results[0]["pulses"], results[1]["pulses"]):
            self.assertAlmostEqual(a, b)

    def test_lizard_protection_building_exclusion_death_revival_and_clock_guard(self):
        actors = actors_for(
            [
                synthetic_unit("lizard"),
                synthetic_unit("enemy", team="defense", hitpoints=1000),
                synthetic_structure("building"),
            ]
        )
        status, receipts, trace = HitStatusCombat(actors), DamageReceipts(), []
        runtime = PoisonLizardExposure(
            self.catalog,
            {
                "lizard": {
                    "level": 10,
                    "town_hall": 16,
                    "parameters": lizard_parameters(),
                }
            },
            {"enemy": "troop", "building": "building"},
            status,
        )
        packet = {"source": "lizard", "source_team": "attack"}
        actors["enemy"]["immune_until"] = 0.5
        for key in ("enemy", "building"):
            runtime.impact(key, packet, actors[key], actors, 0, trace)
        status.prepare(actors, 0, trace)
        self.assertEqual(actors["enemy"]["_hit_status_attack_rate"], 0.5)
        self.assertEqual(actors["building"]["_hit_status_attack_rate"], 1)
        self.assertEqual(len(runtime.exposures), 1)
        with self.assertRaises(InputError):
            runtime.resolve(actors, 0.6, trace, receipts)
        loss = runtime.resolve(actors, 0.25, trace, receipts)
        settled = settle(actors, receipts, loss, 0.25)
        self.assertEqual(settled[0]["actual_health_loss"], 0)
        actors["enemy"]["immune_until"] = 0
        amount = receipts.register(
            actors["enemy"],
            10000,
            0.25,
            source_id="kill",
            source_team="attack",
            origin="weapon",
        )
        settle(actors, receipts, {"enemy": amount}, 0.25)
        runtime.after_health(actors)
        actors["enemy"]["hp"] = 500
        status.prepare(actors, 0.25, trace)
        self.assertIsNone(runtime.next_boundary())
        self.assertEqual(actors["enemy"]["_hit_status_attack_rate"], 1)
        self.assertEqual(
            runtime.preferred_targets(
                "lizard", actors["lizard"], actors, "building", 0.25
            ),
            ["enemy"],
        )

    def test_rocket_exact_contacts_protection_and_receipts_two_steps(self):
        results = [run_rocket(self.catalog, step) for step in (0.017, 0.25)]
        for result in results:
            self.assertEqual(result["hp"], {"first": 10000, "second": 7850})
            self.assertEqual(result["loss"], 2150)
            self.assertEqual([k for k, _ in result["contacts"]], ["first", "second"])
            self.assertAlmostEqual(result["contacts"][0][1], 0.15)
            self.assertAlmostEqual(result["contacts"][1][1], 0.55)
            self.assertFalse(result["demands"]["damage_immunity"])
            self.assertEqual(result["demands"]["position"], (10, 3.5))
            json.dumps(result)

    def test_rocket_cancellation_single_charge_and_conflicting_sources(self):
        for reason in ("death", "recall", "freeze"):
            actors = actors_for([synthetic_unit("duke", layer="air", movement="air")])
            owner = actors["duke"]
            owner["hero_model"] = {"entity": "dragon-duke"}
            runtime = RocketBackpackMotion(
                self.catalog, "duke", 27, 16, rocket_parameters(), 14, 10
            )
            runtime.activate("charge", owner, 0, [])
            self.assertTrue(runtime.demands(0)["preserve_attack_work"])
            if reason == "death":
                owner["hp"] = 0
            elif reason == "recall":
                owner["_recalled"] = True
            else:
                owner["frozen_until"] = 2
            runtime.prepare(owner, 0.1, [])
            self.assertFalse(runtime.demands(0.1)["forced_motion"])
            self.assertEqual(runtime.position(1), runtime.position(0.1))
            self.assertFalse(runtime.activate("charge", owner, 0.2, []))
            with self.assertRaises(InputError):
                runtime.activate("new-charge", owner, 0.2, [])
        historical = rocket_parameters()
        historical["damage_source"] = "pinned_catalog_historical"
        self.assertEqual(
            compile_rocket(self.catalog, 27, 16, historical)["damage"], 2200
        )
        historical.pop("damage_source")
        with self.assertRaises(InputError):
            compile_rocket(self.catalog, 27, 16, historical)
        with self.assertRaises(InputError):
            compile_lizard(self.catalog, 10, 16, {"source": SOURCE})

    def test_monolith_180_181_250_251_exclusions_recall_and_captured_packet(self):
        inventory = {
            "queen": {"membership": "hero", "housing_space": 25},
            "main": {"membership": "army_troop", "housing_space": 155},
            "siege": {"membership": "siege", "housing_space": 1},
            "tail": {"membership": "army_troop", "housing_space": 69},
            "last": {"membership": "army_troop", "housing_space": 1},
            **{
                key: {"membership": key, "housing_space": 0}
                for key in ("pet", "castle", "generated", "spell")
            },
        }
        runtime = MonolithArrowLedger(
            self.catalog, "queen", 27, 16, parameters(MONOLITH), inventory
        )
        actors = actors_for(
            [synthetic_unit("queen", damage=100), synthetic_structure(hitpoints=10000)]
        )
        actors["queen"]["hero_model"] = {"entity": "archer-queen"}
        for key in ("queen", "main", "pet", "castle", "generated", "spell"):
            runtime.deploy("deploy-" + key, key, 0)
        self.assertEqual(runtime.total_housing, 180)
        captured = runtime.capture_launch(actors["queen"], actors["tower"], 0)
        self.assertAlmostEqual(captured["additional_damage"], 1400)
        # Ordinary shared projectile gets the captured bonus; later tiers and
        # source death cannot change it. Central launch wiring is still absent.
        actors["queen"].pop("hero_model")
        actors["queen"]["attack_model"] = {
            "kind": "single",
            "source": SOURCE,
            "target_kinds": ["defense"],
            "target_layers": ["ground"],
            "maximum_hp_fraction": 0,
            "projectile": {
                **projectile(),
                "timing": "launch_distance_delay",
                "speed_tiles_per_second": 10,
            },
        }
        combat, receipts = PatternCombat(actors), DamageReceipts()
        combat.damage_receipts = receipts
        combat.launch(
            actors["queen"],
            actors["tower"],
            actors,
            0,
            [],
            flat_damage=100 + captured["additional_damage"],
        )
        for time, (key, expected) in enumerate(
            (("siege", 0.1), ("tail", 0.1), ("last", 0.05)), 1
        ):
            runtime.deploy("deploy-" + key, key, time / 10)
            self.assertEqual(runtime.fraction, expected)
        self.assertFalse(runtime.deploy("recall-return", "main", 0.5))
        self.assertEqual(runtime.total_housing, 251)
        actors["queen"]["hp"] = 0
        arrival = combat.pending[0][0]
        damage = combat.resolve(actors, arrival, [])
        settle(actors, receipts, damage, arrival)
        self.assertEqual(actors["tower"]["hp"], 8500)
        self.assertEqual(runtime.incoming_multiplier, 0.9)
        json.dumps(runtime.result())

    def test_dark_crown_settled_deaths_stage_cap_owner_loss_and_no_hidden_defaults(
        self,
    ):
        params = parameters(
            CROWN, thresholds=[10, 20, 30], death_weights={"a": 10, "b": 25, "c": 50}
        )
        runtime = DarkCrownLedger(self.catalog, "prince", 27, 16, params)
        actors = actors_for([synthetic_unit(key) for key in ("prince", "a", "b", "c")])
        actors["prince"]["hero_model"] = {"entity": "minion-prince"}
        receipts = DamageReceipts()
        for index, key in enumerate(("a", "b", "c")):
            time = index + 1
            amount = receipts.register(
                actors[key],
                1000,
                time,
                source_id="tower",
                source_team="defense",
                origin="weapon",
            )
            settle(actors, receipts, {key: amount}, time)
            runtime.defeat(key, actors[key], actors["prince"], time)
            runtime.defeat(key, actors[key], actors["prince"], time)
            self.assertEqual(runtime.stage, 1 if key == "a" else 3)
        self.assertEqual(runtime.weight, 85)
        self.assertEqual(runtime.modifiers()["maximum_hp_factor"], 1.3)
        self.assertEqual(runtime.modifiers()["outgoing_damage_factor"], 1.3)
        self.assertAlmostEqual(runtime.modifiers()["attack_rate_factor"], 1.11)
        # Crown does not clobber Life Gem's shared HP state.
        self.assertEqual(actors["prince"]["maximum_hp"], 100)
        unavailable = DarkCrownLedger(self.catalog, "prince", 27, 16, params)
        actors["prince"]["_recalled"] = True
        self.assertFalse(
            unavailable.defeat("held-death", actors["b"], actors["prince"], 3)
        )
        actors["prince"]["_recalled"] = False
        self.assertFalse(
            unavailable.defeat("returned-old-death", actors["b"], actors["prince"], 4)
        )
        self.assertEqual(unavailable.stage, 0)
        actors["prince"]["hp"] = 0
        self.assertFalse(
            unavailable.defeat("owner-dead", actors["c"], actors["prince"], 4)
        )
        actors["prince"]["hp"] = 10
        self.assertEqual(runtime.stage, 3)
        actors["a"]["hp"] = 1
        with self.assertRaises(InputError):
            runtime.defeat("false-recall", actors["a"], actors["prince"], 4)
        params.pop("thresholds")
        with self.assertRaises(InputError):
            DarkCrownLedger(self.catalog, "prince", 27, 16, params)
        json.dumps(runtime.result())
