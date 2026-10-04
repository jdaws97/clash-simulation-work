"""Damage provenance, mitigation and actual-loss allocation at health boundaries."""

import unittest

from clashlab.common import InputError
from clashlab.damage_receipts import DamageReceipts


def recipient(**changes):
    actor = {"id": "duke", "hp": 100, "immune_until": 0}
    actor.update(changes)
    return actor


class DamageReceiptTests(unittest.TestCase):
    def test_protection_and_independent_mitigation_apply_once(self):
        actor = recipient(
            _hero_incoming_damage_multiplier=0.6,
            _hero_trap_damage_multiplier=0.5,
        )
        ledger = DamageReceipts()
        total = ledger.register(
            actor, 100, 0, source_id="bomb", source_team="defense", origin="trap"
        )
        self.assertEqual(total, 30)
        settled = ledger.settle({"duke": actor}, {"duke": total}, 0)
        self.assertEqual(settled[0]["actual_health_loss"], 30)
        self.assertEqual(settled[0]["requested_damage"], 100)
        actor["immune_until"] = 2
        self.assertEqual(
            ledger.register(
                actor, 100, 1, source_id="bomb", source_team="defense", origin="trap"
            ),
            0,
        )
        protected = ledger.settle({"duke": actor}, {"duke": 0}, 1)
        self.assertTrue(protected[0]["protected"])
        self.assertEqual(protected[0]["actual_health_loss"], 0)

    def test_packet_order_assigns_overkill_without_counting_future_healing(self):
        actor = recipient(hp=70)
        ledger = DamageReceipts()
        for source in ("archer", "cannon", "wizard"):
            ledger.register(
                actor,
                50,
                0,
                source_id=source,
                source_actor_id=source,
                source_team="defense",
                origin="weapon",
            )
        receipts = ledger.settle({"duke": actor}, {"duke": 150}, 0)
        self.assertEqual([item["actual_health_loss"] for item in receipts], [50, 20, 0])
        self.assertEqual(
            [item["source_actor_id"] for item in receipts],
            ["archer", "cannon", "wizard"],
        )
        self.assertEqual(actor["hp"], 70)
        ledger.assert_settled()

    def test_missing_or_double_attribution_fails_closed(self):
        actor = recipient()
        ledger = DamageReceipts()
        with self.assertRaisesRegex(InputError, "does not match"):
            ledger.settle(
                {"duke": actor}, {"duke": 20}, 0, require_attribution_for={"duke"}
            )
        ledger.register(
            actor, 20, 0, source_id="cannon", source_team="defense", origin="weapon"
        )
        with self.assertRaisesRegex(InputError, "does not match"):
            ledger.settle({"duke": actor}, {"duke": 40}, 0)
        self.assertEqual(len(ledger.pending), 1)
        with self.assertRaisesRegex(InputError, "cannot be discarded"):
            ledger.assert_settled()

    def test_batches_cannot_cross_time_or_invent_source_origin(self):
        actor = recipient()
        ledger = DamageReceipts()
        ledger.register(
            actor, 20, 0, source_id="cannon", source_team="defense", origin="weapon"
        )
        with self.assertRaisesRegex(InputError, "advancing time"):
            ledger.register(
                actor, 20, 1, source_id="cannon", source_team="defense", origin="weapon"
            )
        with self.assertRaisesRegex(InputError, "differs"):
            ledger.settle({"duke": actor}, {"duke": 20}, 1)
        with self.assertRaisesRegex(InputError, "supported origin"):
            DamageReceipts().register(
                actor,
                20,
                0,
                source_id="cannon",
                source_team="defense",
                origin="guessed_from_trace",
            )

    def test_selected_recipients_allow_unrelated_ordinary_damage_in_same_batch(self):
        duke = recipient()
        cannon = recipient(id="cannon", hp=500)
        ledger = DamageReceipts({"duke"})
        ledger.register(
            duke, 20, 0, source_id="cannon", source_team="defense", origin="weapon"
        )
        ledger.register(
            cannon, 50, 0, source_id="duke", source_team="attack", origin="weapon"
        )
        receipts = ledger.settle(
            {"duke": duke, "cannon": cannon}, {"duke": 20, "cannon": 200}, 0
        )
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["target_id"], "duke")

    def test_immediate_trap_damage_joins_next_health_callback_without_double_counting(
        self,
    ):
        actor = recipient(hp=100, _hero_trap_damage_multiplier=0.5)
        ledger = DamageReceipts({"duke"})
        amount = ledger.register(
            actor,
            80,
            0,
            source_id="spring",
            source_team="defense",
            origin="trap",
            apply_immediately=True,
        )
        actor["hp"] -= amount
        ledger.register(
            actor, 80, 0, source_id="cannon", source_team="defense", origin="weapon"
        )
        receipts = ledger.settle({"duke": actor}, {"duke": 80}, 0)
        self.assertEqual([item["actual_health_loss"] for item in receipts], [40, 60])
        self.assertEqual(actor["hp"], 60)
        ledger.assert_settled()


if __name__ == "__main__":
    unittest.main()
