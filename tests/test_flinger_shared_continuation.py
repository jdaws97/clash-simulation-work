"""Actual Flinger clocks across shared health/termination; synthetic contracts."""

from copy import deepcopy
from math import nextafter
import unittest

from clashlab.battle_continuation import (
    siege_continuation,
    runtime_continuation_reasons,
)
from clashlab.battle_termination import BattleTermination, continuation_fact
from clashlab.common import InputError
from clashlab.damage_receipts import DamageReceipts
from clashlab.full_battle import simulate_full_battle
from clashlab.spatial import _apply_health
from clashlab.termination_rules import RULES, SCOPE

from test_battle_termination import termination_policy, actor
import test_siege_lifecycle as lifecycle_fixtures
import test_siege_domain_integration as battle_fixtures
from test_siege_machines import release_command


class FlingerSharedContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lifecycle_fixtures.SiegeLifecycleTests.setUpClass()
        battle_fixtures.SiegeDomainIntegrationTests.setUpClass()

    def test_real_final_partial_clock_survives_until_exact_settlement(self):
        fixture = lifecycle_fixtures.SiegeLifecycleTests()
        instance = lifecycle_fixtures.extended_instance(
            fixture.catalog, "flame-flinger"
        )
        instance["siege_parameters"]["behavior"].update(
            flame_duration_seconds=0.3,
            flame_interval_seconds=0.1,
            flame_dps_fractions=[1],
        )
        actors, owner, _, trace = fixture.runtime(instance)
        actors["defense"].update(hp=10000, maximum_hp=10000)
        actors["ally"]["hp"] = 0
        receipts = DamageReceipts()
        owner.damage_receipts = receipts
        termination = BattleTermination(termination_policy(), ["defense"], {}, [], 4)
        owner.launch(actors["siege"], actors["defense"], actors, 0, trace)
        with self.assertRaisesRegex(InputError, "actual settled time"):
            siege_continuation(owner)
        time = 0
        positive_tails = []
        for _ in range(64):
            if time == 0.21:
                actors["siege"].update(hp=0, death_time=time)
            owner.prepare(actors, time, trace)
            # Controlled synthetic casualties isolate the released flame clock
            # from this reusable fixture's unrelated ally and CC troops.
            for key, value in actors.items():
                if (
                    value["team"] == "attack"
                    and key != "siege"
                    and value["spawn_seconds"] != "controlled"
                ):
                    value.update(hp=0, death_time=time)
            damage = owner.resolve(actors, time, trace)
            receipts.settle(actors, damage, time)
            _apply_health(actors, damage, {}, time)
            facts = runtime_continuation_reasons(
                time, actors, siege=owner, damage_receipts=receipts
            )
            self.assertEqual(
                facts,
                sorted(
                    owner.continuation_reasons(time), key=lambda f: (f["kind"], f["id"])
                ),
            )
            for fact in facts:
                start = fact["not_before_seconds"]
                if start is not None and 0 < start - time < 1e-10:
                    positive_tails.append((time, start))
            decision = termination.evaluate(time, actors, facts, settled=True)
            if decision is not None:
                break
            future = [
                point
                for point in (owner.next_boundary(time), 0.21)
                if point is not None and point > time
            ]
            self.assertTrue(future)
            time = min(future)
        else:
            self.fail("Flinger did not settle within bounded event budget")
        self.assertIn((0.5499999999999999, 0.55), positive_tails)
        self.assertEqual(decision["time_seconds"], 0.55)
        self.assertEqual(decision["end_reason"], "attack_force_exhausted")
        pulses = [e for e in trace if e.get("packet_kind") == "flame_pulse"]
        self.assertAlmostEqual(sum(e["damage"] for e in pulses), 40)
        self.assertTrue(any(0 < e["damage"] < 1e-10 for e in pulses))
        self.assertEqual(owner.result()["flame_damage_clocks"], {})
        self.assertEqual(owner.result()["active_flame_fields"], 0)

    def test_pending_damage_and_expiry_do_not_round_future_into_present(self):
        actors = {"dead": actor("dead", hp=0), "hall": actor("hall", team="defense")}
        now, future = 0.55, nextafter(0.55, float("inf"))
        for kind in ("pending_damage", "lingering_damage"):
            runtime = BattleTermination(termination_policy(), ["hall"], {}, [], 4)
            fact = continuation_fact(
                kind,
                "tail",
                ["dead"],
                not_before_seconds=future,
                expires_at_seconds=future,
            )
            self.assertIsNone(runtime.evaluate(now, actors, [fact], settled=True))
            if kind == "pending_damage":
                with self.assertRaisesRegex(InputError, "must settle"):
                    runtime.evaluate(future, actors, [fact], settled=True)
            else:
                self.assertEqual(
                    runtime.evaluate(future, actors, [fact], settled=True)[
                        "end_reason"
                    ],
                    "attack_force_exhausted",
                )

    def test_paid_flinger_short_fields_use_shared_clock_and_single_cc(self):
        fixture = battle_fixtures.SiegeDomainIntegrationTests()
        results = []
        for step in (0.017, 0.25):
            inputs = fixture.inputs("flame-flinger", duration=0.8)
            inputs[0]["termination_policy"] = termination_policy()
            scene = inputs[0]["entity_scene"]
            scene.update(
                scope=SCOPE,
                model_rules=deepcopy(RULES),
                pets=[],
                maximum_step_seconds=step,
                effects=[release_command(0.21)],
            )
            carrier = next(a for a in scene["entities"] if a["id"] == "siege")
            carrier["siege_parameters"]["behavior"].update(
                flame_duration_seconds=0.3,
                flame_interval_seconds=0.1,
                flame_dps_fractions=[1],
            )
            result = simulate_full_battle(*inputs, fixture.catalog)
            combat = result["combat"]
            flames = [
                e for e in combat["trace"] if e.get("packet_kind") == "flame_pulse"
            ]
            self.assertTrue(any(e["time_seconds"] > 0.21 for e in flames))
            self.assertEqual(
                result["resource_use"]["deployed_attacker_ids"], ["payload", "siege"]
            )
            self.assertEqual(
                result["resource_use"]["clan_castle_delivery"]["pending_member_ids"], []
            )
            self.assertEqual(combat["sieges"]["active_flame_fields"], 0)
            results.append([(e["time_seconds"], e["damage"]) for e in flames])
        self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    unittest.main()
