"""Termination hypotheses distinguish unspent inventory from latent combat work."""

from copy import deepcopy
import unittest

from clashlab.battle_termination import (
    BattleTermination,
    CompletionOnlyTermination,
    POLICY_ASSUMPTIONS,
    POLICY_MODE,
    continuation_fact,
    spell_slot_id,
)
from clashlab.common import InputError


SOURCE = "force-exhaustion-test-hypothesis-not-verified-live-game-rules"


def termination_policy(spell_inventory=()):
    return {
        "source": SOURCE,
        "mode": POLICY_MODE,
        "assumptions": deepcopy(POLICY_ASSUMPTIONS),
        "spell_inventory": deepcopy(list(spell_inventory)),
    }


def actor(actor_id="troop", hp=100, spawn=0, team="attack", **extra):
    return {
        "id": actor_id,
        "team": team,
        "kind": "unit" if team == "attack" else "building",
        "hp": hp,
        "spawn_seconds": spawn,
        "counts_for_destruction": team == "defense",
        **extra,
    }


def spell(entity="hypothetical-spell", origin="army", ordinal=1, cast=None):
    return {
        "entity": entity,
        "origin": origin,
        "level": 1,
        "ordinal": ordinal,
        "cast": cast,
    }


def classification(binding, kind, continuation):
    return {
        "origin": binding["origin"],
        "entity": binding["entity"],
        "level": binding["level"],
        "classification": kind,
        "continuation": continuation,
    }


class BattleTerminationTests(unittest.TestCase):
    def make_runtime(
        self, attackers=(), bindings=None, spells=(), policies=(), limit=10
    ):
        actors = {item["id"]: item for item in attackers}
        actors["hall"] = actor("hall", team="defense")
        runtime = BattleTermination(
            termination_policy(policies), ["hall"], bindings or {}, list(spells), limit
        )
        return runtime, actors

    def test_frozen_invisible_protected_and_support_attackers_continue(self):
        runtime, actors = self.make_runtime(
            [
                actor(
                    "support",
                    damage=0,
                    speed=0,
                    frozen_until=8,
                    immune_until=9,
                    _untargetable_until=7,
                )
            ]
        )
        self.assertIsNone(runtime.evaluate(1, actors, settled=True))
        self.assertEqual(
            runtime.last_reasons, [{"kind": "active_attacker", "id": "support"}]
        )
        actors["support"]["hp"] = 0
        self.assertEqual(
            runtime.evaluate(2, actors, settled=True)["end_reason"],
            "attack_force_exhausted",
        )

    def test_bound_user_inventory_continues_without_a_deployment_command(self):
        runtime, actors = self.make_runtime(
            [actor("reserve", spawn="controlled")],
            {"reserve": {"origin": "army_troops"}},
        )
        self.assertIsNone(runtime.evaluate(0, actors, settled=True))
        self.assertEqual(runtime.last_reasons[0]["kind"], "undeployed_army")
        decision = runtime.evaluate(10, actors, settled=True)
        self.assertEqual(decision["end_reason"], "declared_time_limit")

    def test_scheduled_owned_hero_and_siege_are_reserves_before_deployment(self):
        runtime, actors = self.make_runtime(
            [actor("hero", spawn=3), actor("carrier", spawn="controlled")],
            {"hero": {"origin": "army_heroes"}, "carrier": {"origin": "siege"}},
        )
        reasons = runtime.continuation_reasons(1, actors)
        self.assertEqual([item["kind"] for item in reasons], ["undeployed_army"] * 2)
        reasons = runtime.continuation_reasons(3, actors)
        self.assertEqual(
            [item["kind"] for item in reasons], ["active_attacker", "undeployed_army"]
        )

    def test_generated_controlled_units_are_not_unspent_army_resources(self):
        runtime, actors = self.make_runtime(
            [
                actor(
                    "mirror", spawn="controlled", summon_model={"parent": "dead-hero"}
                ),
                actor("pet", spawn="controlled", pet_model={}),
                actor("payload", spawn="controlled", payload_member_model={}),
            ],
            {
                "pet": {"origin": "assigned_hero_pet"},
                "payload": {"origin": "clan_castle_troops"},
            },
        )
        self.assertEqual(
            runtime.evaluate(0, actors, settled=True)["end_reason"],
            "attack_force_exhausted",
        )

    def test_generated_actor_cannot_masquerade_as_bound_user_inventory(self):
        runtime, actors = self.make_runtime(
            [actor("mirror", spawn="controlled", summon_model={"parent": "hero"})],
            {"mirror": {"origin": "army_troops"}},
        )
        with self.assertRaisesRegex(InputError, "Generated actors"):
            runtime.evaluate(0, actors, settled=True)

    def test_released_generated_unit_becomes_an_active_attacker(self):
        runtime, actors = self.make_runtime(
            [actor("mirror", summon_model={"parent": "hero"})]
        )
        self.assertIsNone(runtime.evaluate(0, actors, settled=True))
        self.assertEqual(runtime.last_reasons[0]["kind"], "active_attacker")

    def test_pending_blocked_payload_continues_after_carrier_death(self):
        runtime, actors = self.make_runtime(
            [actor("carrier", hp=0), actor("payload", spawn="controlled")],
            {
                "carrier": {"origin": "siege"},
                "payload": {"origin": "clan_castle_troops"},
            },
        )
        fact = continuation_fact(
            "pending_release", "payload-group", ["payload"], not_before_seconds=1
        )
        self.assertIsNone(runtime.evaluate(5, actors, [fact], settled=True))
        self.assertEqual(runtime.last_reasons, [fact])
        self.assertEqual(
            runtime.evaluate(10, actors, [fact], settled=True)["end_reason"],
            "declared_time_limit",
        )

    def test_latent_diggy_and_phoenix_lifecycle_require_runtime_ownership(self):
        runtime, actors = self.make_runtime([actor("pet", spawn="controlled")])
        fact = continuation_fact(
            "latent_attacker", "pet-lifecycle", ["pet"], expires_at_seconds=4
        )
        self.assertIsNone(runtime.evaluate(2, actors, [fact], settled=True))
        self.assertEqual(
            runtime.evaluate(4, actors, [fact], settled=True)["end_reason"],
            "attack_force_exhausted",
        )

    def test_launched_attacking_packet_continues_after_source_death(self):
        runtime, actors = self.make_runtime([actor("troop", hp=0)])
        fact = continuation_fact(
            "pending_damage", "projectile:1", ["troop"], not_before_seconds=3
        )
        self.assertIsNone(runtime.evaluate(2, actors, [fact], settled=True))
        self.assertEqual(
            runtime.evaluate(3, actors, settled=True)["end_reason"],
            "attack_force_exhausted",
        )

    def test_defensive_projectile_and_status_only_effect_do_not_prolong(self):
        runtime, actors = self.make_runtime()
        defensive = continuation_fact(
            "pending_damage",
            "defense-shot",
            ["hall"],
            source_team="defense",
            not_before_seconds=3,
        )
        decision = runtime.evaluate(2, actors, [defensive], settled=True)
        self.assertEqual(decision["end_reason"], "attack_force_exhausted")
        runtime, actors = self.make_runtime()
        status = continuation_fact("pending_freeze", "freeze-only")
        with self.assertRaisesRegex(InputError, "continuation kind"):
            runtime.evaluate(2, actors, [status], settled=True)

    def test_lingering_damage_keeps_run_until_its_last_supported_future_damage(self):
        runtime, actors = self.make_runtime()
        fact = continuation_fact("lingering_damage", "burn", expires_at_seconds=4)
        self.assertIsNone(runtime.evaluate(3, actors, [fact], settled=True))
        self.assertEqual(
            runtime.evaluate(4, actors, [fact], settled=True)["end_reason"],
            "attack_force_exhausted",
        )

    def test_future_support_spell_does_not_continue_or_get_marked_as_cast(self):
        binding = spell(cast={"cast_id": "future-support", "time_seconds": 8})
        runtime, actors = self.make_runtime(
            spells=[binding],
            policies=[classification(binding, "support_only", "ignore")],
        )
        decision = runtime.evaluate(2, actors, settled=True)
        self.assertEqual(decision["time_seconds"], 2)
        self.assertEqual(decision["end_reason"], "attack_force_exhausted")
        self.assertEqual(runtime.spell_bindings[0]["cast"]["time_seconds"], 8)

    def test_spell_names_do_not_determine_classification(self):
        binding = spell("healing-spell")
        runtime, actors = self.make_runtime(
            spells=[binding],
            policies=[classification(binding, "damage", "while_unspent")],
        )
        self.assertIsNone(runtime.evaluate(0, actors, settled=True))
        self.assertEqual(runtime.last_reasons[0]["classification"], "damage")

    def test_damage_and_summon_reserves_follow_explicit_choice(self):
        for kind in ("damage", "summon"):
            for choice in ("ignore", "while_unspent"):
                with self.subTest(kind=kind, choice=choice):
                    binding = spell()
                    runtime, actors = self.make_runtime(
                        spells=[binding],
                        policies=[classification(binding, kind, choice)],
                    )
                    decision = runtime.evaluate(2, actors, settled=True)
                    self.assertEqual(decision is None, choice == "while_unspent")

    def test_recall_and_revive_require_actual_runtime_eligibility_when_selected(self):
        for kind in ("recall", "revive"):
            with self.subTest(kind=kind):
                binding = spell()
                runtime, actors = self.make_runtime(
                    spells=[binding],
                    policies=[classification(binding, kind, "while_runtime_eligible")],
                )
                with self.assertRaisesRegex(InputError, "runtime eligibility"):
                    runtime.evaluate(2, actors, settled=True)
                slot = spell_slot_id(binding)
                self.assertIsNone(
                    runtime.evaluate(
                        2, actors, spell_eligibility={slot: True}, settled=True
                    )
                )
                self.assertEqual(
                    runtime.evaluate(
                        3, actors, spell_eligibility={slot: False}, settled=True
                    )["end_reason"],
                    "attack_force_exhausted",
                )

    def test_spell_origins_and_ordinals_keep_independent_charges(self):
        own = spell(cast={"cast_id": "own-cast", "time_seconds": 1})
        donated = spell(origin="clan_castle")
        runtime, actors = self.make_runtime(
            spells=[own, donated],
            policies=[
                classification(item, "damage", "while_unspent")
                for item in (own, donated)
            ],
        )
        reasons = runtime.continuation_reasons(1, actors)
        self.assertEqual([item["id"] for item in reasons], [spell_slot_id(donated)])

    def test_missing_duplicate_extra_and_support_prolonging_policies_are_rejected(self):
        binding = spell()
        ordinary = classification(binding, "support_only", "ignore")
        candidates = [
            [],
            [ordinary, ordinary],
            [ordinary, classification(spell("extra"), "damage", "ignore")],
            [classification(binding, "support_only", "while_unspent")],
        ]
        for policies in candidates:
            with self.subTest(policies=policies):
                with self.assertRaises(InputError):
                    self.make_runtime(spells=[binding], policies=policies)

    def test_all_counted_destruction_has_priority_over_reserves_and_time_limit(self):
        runtime, actors = self.make_runtime(
            [actor("reserve", spawn="controlled")],
            {"reserve": {"origin": "army_troops"}},
        )
        actors["hall"]["hp"] = 0
        decision = runtime.evaluate(10, actors, settled=True)
        self.assertEqual(decision["end_reason"], "all_counted_buildings_destroyed")

    def test_final_attacker_death_at_time_limit_selects_force_exhaustion(self):
        runtime, actors = self.make_runtime([actor(hp=0)])
        self.assertEqual(
            runtime.evaluate(10, actors, settled=True)["end_reason"],
            "attack_force_exhausted",
        )

    def test_complete_destruction_does_not_need_unused_revival_eligibility(self):
        binding = spell()
        runtime, actors = self.make_runtime(
            spells=[binding],
            policies=[classification(binding, "revive", "while_runtime_eligible")],
        )
        actors["hall"]["hp"] = 0
        self.assertEqual(
            runtime.evaluate(2, actors, settled=True)["end_reason"],
            "all_counted_buildings_destroyed",
        )

    def test_unsettled_boundary_and_due_damage_cannot_produce_an_early_stop(self):
        runtime, actors = self.make_runtime([actor(hp=0)])
        with self.assertRaisesRegex(InputError, "fully settled"):
            runtime.evaluate(1, actors, settled=False)
        fact = continuation_fact(
            "pending_damage", "due-projectile", ["troop"], not_before_seconds=1
        )
        with self.assertRaisesRegex(InputError, "must settle"):
            runtime.evaluate(1, actors, [fact], settled=True)
        fact["expires_at_seconds"] = 1
        with self.assertRaisesRegex(InputError, "must settle"):
            runtime.evaluate(1, actors, [fact], settled=True)

    def test_provider_ownership_identity_and_expiry_are_validated(self):
        invalid = [
            continuation_fact(
                "pending_damage", "foreign-source", ["hall"], not_before_seconds=3
            ),
            continuation_fact(
                "lingering_damage",
                "invalid-expiry",
                not_before_seconds=3,
                expires_at_seconds=2,
            ),
        ]
        for fact in invalid:
            with self.subTest(fact=fact):
                runtime, actors = self.make_runtime()
                with self.assertRaises(InputError):
                    runtime.evaluate(1, actors, [fact], settled=True)
        runtime, actors = self.make_runtime()
        fact = continuation_fact("pending_damage", "duplicated", not_before_seconds=3)
        with self.assertRaisesRegex(InputError, "Duplicate runtime"):
            runtime.evaluate(1, actors, [fact, fact], settled=True)

    def test_evaluation_is_observational_and_preserves_hypothesis_in_result(self):
        runtime, actors = self.make_runtime([actor(hp=0)])
        before = deepcopy(actors)
        decision = runtime.evaluate(2, actors, settled=True)
        self.assertEqual(actors, before)
        decision["end_reason"] = "modified-return-copy"
        result = runtime.result()
        self.assertEqual(result["decision"]["end_reason"], "attack_force_exhausted")
        self.assertEqual(result["policy"]["source"], SOURCE)
        self.assertEqual(result["policy_status"], "explicit_uncalibrated_hypothesis")

    def test_legacy_observer_does_not_end_when_the_last_attacker_dies(self):
        actors = {"troop": actor(hp=0), "hall": actor("hall", team="defense")}
        runtime = CompletionOnlyTermination(["hall"], 10)
        self.assertFalse(runtime.requires_runtime_facts)
        self.assertIsNone(runtime.evaluate(1, actors, settled=True))
        self.assertEqual(
            runtime.evaluate(10, actors, settled=True)["end_reason"],
            "declared_time_limit",
        )

    def test_legacy_observer_detects_completion_at_the_settled_boundary(self):
        actors = {"hall": actor("hall", team="defense")}
        runtime = CompletionOnlyTermination(["hall"], 10)
        self.assertIsNone(runtime.evaluate(0, actors, settled=True))
        actors["hall"]["hp"] = 0
        self.assertEqual(
            runtime.evaluate(0.75, actors, settled=True),
            {
                "time_seconds": 0.75,
                "end_reason": "all_counted_buildings_destroyed",
                "continuation_reasons": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
