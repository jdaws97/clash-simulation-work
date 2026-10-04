"""Continuation facts come from actual queued work and owned lifecycle state."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.battle_continuation import (
    death_continuation,
    hazard_continuation,
    pattern_continuation,
    pet_continuation,
    reinforcement_continuation,
    runtime_continuation_reasons,
    siege_continuation,
)
from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError
from clashlab.damage_receipts import DamageReceipts
from clashlab.deaths import DeathCombat
from clashlab.hazards import PulsedHazards
from clashlab.hero_pets import PetCombat, compile_pet
from clashlab.reinforcements import (
    ReinforcementCombat,
    compile_attacking_reinforcements,
)
from clashlab.siege_machines import SiegeCombat
from clashlab.spatial import _apply_health, _load_actors, _select_target
from clashlab.walls import WallRouting

from test_combat import delayed_projectile_scene
from test_deaths import death_model, death_scene
from test_hero_pets import owner, pet_instance, target
from test_reinforcements import (
    compile_payload,
    group_parameters,
    payload_instance,
    target_actor,
)
from test_siege_machines import compiled_siege, siege_instance
from test_townhalls import hazard, hazard_scene


ROOT = Path(__file__).resolve().parents[1]


class BattleContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_actual_weapon_queue_retains_attack_packet_after_source_death(self):
        scene = delayed_projectile_scene()
        actors = _load_actors(scene, scene["width"], scene["height"])
        combat = PatternCombat(actors)
        combat.launch(actors["attacker"], actors["tower"], actors, 0, [])
        actors["attacker"]["hp"] = 0
        facts = pattern_continuation(combat)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["actor_ids"], ["attacker"])
        self.assertEqual(facts[0]["not_before_seconds"], 1)
        damage = combat.resolve(actors, 1, [])
        _apply_health(actors, damage, {}, 1)
        self.assertEqual(actors["tower"]["hp"], 0)
        self.assertEqual(pattern_continuation(combat), [])

    def test_zero_flat_fractional_packet_counts_but_zero_damage_packet_does_not(self):
        scene = delayed_projectile_scene()
        scene["actors"][0]["attack_model"]["maximum_hp_fraction"] = 0.1
        actors = _load_actors(scene, scene["width"], scene["height"])
        combat = PatternCombat(actors)
        combat.launch(actors["attacker"], actors["tower"], actors, 0, [], flat_damage=0)
        self.assertEqual(len(pattern_continuation(combat)), 1)
        combat.pending[0][2]["pattern"]["maximum_hp_fraction"] = 0
        self.assertEqual(pattern_continuation(combat), [])

    def test_delayed_death_blast_continues_but_freeze_and_zero_blast_do_not(self):
        for kind, amount, expected in (
            ("area_damage", 50, 1),
            ("area_damage", 0, 0),
            ("area_freeze", None, 0),
        ):
            with self.subTest(kind=kind, amount=amount):
                scene = death_scene()
                model = death_model(delay=2, amount=amount)
                if kind == "area_freeze":
                    model["effects"][0].update(kind=kind, duration_seconds=2)
                    del model["effects"][0]["amount"]
                scene["actors"][0]["death_model"] = model
                actors = _load_actors(scene, scene["width"], scene["height"])
                runtime = DeathCombat(actors)
                actors["attacker"].update(hp=0, death_time=1)
                runtime.settle(actors, 1, [])
                facts = death_continuation(runtime, actors)
                self.assertEqual(len(facts), expected)
                if expected:
                    self.assertEqual(facts[0]["not_before_seconds"], 3)

    def payload_runtime(self, carrier=False, blocked=False):
        payload = compile_payload(payload_instance(), self.catalog)
        definitions = [payload]
        carrier_id = "siege" if carrier else None
        if carrier:
            definitions.append(compiled_siege(siege_instance(), self.catalog))
            definitions.append(
                target_actor("hall", x=20, y=5, width=4, height=4, entity="town-hall")
            )
        if blocked:
            definitions.append(target_actor("blocker", x=1, y=7))
        actors = _load_actors({"actors": definitions}, 30, 20)
        parameters = group_parameters(["payload"], carrier_id)
        if blocked:
            parameters["release"]["maximum_displacement_tiles"] = 0
        model = compile_attacking_reinforcements(parameters, self.catalog, actors)
        return actors, ReinforcementCombat(actors, model, 30, 20)

    def test_direct_undeployed_cc_and_blocked_release_are_real_continuations(self):
        actors, runtime = self.payload_runtime(blocked=True)
        self.assertEqual(
            reinforcement_continuation(runtime)[0]["actor_ids"], ["payload"]
        )
        runtime.begin_release(0, {"x": 1.5, "y": 7.5}, "direct_command", None, [])
        self.assertFalse(runtime.prepare(1, []))
        self.assertIsNone(runtime.next_boundary(1))
        self.assertEqual(
            reinforcement_continuation(runtime)[0]["not_before_seconds"], 0.1
        )
        actors["blocker"].update(hp=0, death_time=2)
        self.assertTrue(runtime.prepare(2, []))
        self.assertEqual(reinforcement_continuation(runtime), [])

    def test_actual_siege_death_retains_payload_and_released_death_damage(self):
        actors, payload = self.payload_runtime(carrier=True)
        siege = SiegeCombat(actors, _select_target, payload, 30, 20)
        trace = []
        siege.prepare(actors, 0, trace)
        actors["siege"].update(hp=0, death_time=1)
        siege.prepare(actors, 1, trace, allow_release=False)
        self.assertEqual(payload.state["phase"], "releasing")
        self.assertEqual(len(reinforcement_continuation(payload)), 1)
        self.assertEqual(len(siege_continuation(siege)), 1)
        siege.resolve(actors, 1, trace)
        self.assertEqual(siege_continuation(siege), [])

    def pet_runtime(self, entity, hero=None):
        hero = owner() if hero is None else hero
        enemy = target()
        pet = compile_pet(
            pet_instance(entity),
            self.catalog,
            8,
            {hero["id"]: hero, enemy["id"]: enemy},
        )
        actors = _load_actors({"actors": [hero, enemy, pet]}, 24, 16)
        walls = WallRouting(actors)
        return actors, PetCombat(actors, 24, 16, walls.select_target)

    def test_diggy_underground_after_owner_death_is_a_latent_attacker(self):
        actors, runtime = self.pet_runtime("diggy")
        runtime.prepare(actors, 0, [])
        self.assertEqual(runtime.states["pet"]["phase"], "underground")
        actors["hero"].update(hp=0, death_time=0.1)
        self.assertEqual(pet_continuation(runtime)[0]["actor_ids"], ["pet"])
        arrival = runtime.states["pet"]["burrow"]["surface_seconds"]
        runtime.advance(actors, 0, arrival, [])
        runtime.prepare(actors, arrival, [])
        self.assertEqual(runtime.states["pet"]["phase"], "active")
        self.assertEqual(pet_continuation(runtime), [])

    def test_waiting_pet_and_orphaned_phoenix_egg_do_not_become_reserve_inventory(self):
        actors, runtime = self.pet_runtime("phoenix", owner(spawn_seconds="controlled"))
        self.assertEqual(pet_continuation(runtime), [])
        actors["hero"]["spawn_seconds"] = 0
        runtime.prepare(actors, 0, [])
        self.assertEqual(pet_continuation(runtime)[0]["actor_ids"], ["pet"])
        actors["hero"].update(hp=0, death_time=1)
        self.assertEqual(pet_continuation(runtime), [])

    def hazard_runtime(self, owner_team="attack", **changes):
        scene = hazard_scene(fields=[hazard(**changes)])
        actors = _load_actors(scene, scene["width"], scene["height"])
        runtime = PulsedHazards(actors, scene["persistent_hazards"])
        # The v28 compiler will require ownership on external field inputs;
        # until integration, this tags the already-validated runtime field.
        runtime.fields["poison"]["source_team"] = owner_team
        return actors, runtime

    def test_hazard_future_positive_pulse_continues_without_any_current_target(self):
        actors, runtime = self.hazard_runtime()
        actors["attacker"]["hp"] = 0
        runtime.resolve(actors, 0, [])
        facts = hazard_continuation(runtime, 0)
        self.assertEqual(facts[0]["not_before_seconds"], 0.5)
        for time in (0.5, 1, 1.5):
            runtime.resolve(actors, time, [])
        self.assertEqual(hazard_continuation(runtime, 1.5), [])

    def test_slow_linger_and_defensive_damage_do_not_continue_attacking_force(self):
        for owner_team, damage in (("attack", 0), ("defense", 10), ("environment", 10)):
            with self.subTest(owner_team=owner_team, damage=damage):
                actors, runtime = self.hazard_runtime(
                    owner_team, maximum_dps=damage, exit_linger_seconds=20
                )
                runtime.resolve(actors, 0, [])
                runtime.exposure_expiry["poison", "attacker"] = 20
                self.assertEqual(hazard_continuation(runtime, 0), [])

    def test_hazard_growth_must_have_a_positive_pulse_before_expiry(self):
        actors, runtime = self.hazard_runtime(
            duration_seconds=2,
            growth_by_field_age=[
                {"after_seconds": 0, "dps_multiplier": 0},
                {"after_seconds": 1.6, "dps_multiplier": 1},
            ],
        )
        runtime.resolve(actors, 0, [])
        self.assertEqual(hazard_continuation(runtime, 0), [])
        runtime.fields["poison"]["growth_by_field_age"][1]["after_seconds"] = 1.5
        self.assertEqual(hazard_continuation(runtime, 0)[0]["not_before_seconds"], 1.5)

    def test_unknown_hazard_ownership_is_not_inferred_from_its_targets(self):
        actors, runtime = self.hazard_runtime()
        runtime.resolve(actors, 0, [])
        del runtime.fields["poison"]["source_team"]
        with self.assertRaisesRegex(InputError, "source_team"):
            hazard_continuation(runtime, 0)

    def test_lifecycle_hazard_uses_its_actual_source_actor_even_after_death(self):
        actors, runtime = self.hazard_runtime()
        runtime.resolve(actors, 0, [])
        del runtime.fields["poison"]["source_team"]
        runtime.source_actor_ids = {"poison": "attacker"}
        actors["attacker"].update(hp=0, death_time=0)
        fact = hazard_continuation(runtime, 0, actors)[0]
        self.assertEqual(fact["actor_ids"], ["attacker"])
        self.assertEqual(fact["source_team"], "attack")
        runtime.fields["poison"]["source_team"] = "defense"
        with self.assertRaisesRegex(InputError, "team disagree"):
            hazard_continuation(runtime, 0, actors)

    def test_receipts_must_be_settled_before_continuation_observation(self):
        scene = delayed_projectile_scene()
        actors = _load_actors(scene, scene["width"], scene["height"])
        receipts = DamageReceipts()
        receipts.register(
            actors["attacker"],
            5,
            0,
            source_id="tower",
            source_team="defense",
            origin="weapon",
        )
        with self.assertRaisesRegex(InputError, "Pending damage receipts"):
            runtime_continuation_reasons(0, actors, damage_receipts=receipts)
        receipts.settle(actors, {"attacker": 5}, 0)
        self.assertEqual(
            runtime_continuation_reasons(0, actors, damage_receipts=receipts), []
        )

    def test_collecting_facts_never_advances_runtime_or_mutates_actors(self):
        actors, payload = self.payload_runtime()
        before = deepcopy((actors, payload.state))
        facts = runtime_continuation_reasons(0, actors, reinforcements=payload)
        self.assertEqual(len(facts), 1)
        self.assertEqual((actors, payload.state), before)


if __name__ == "__main__":
    unittest.main()
