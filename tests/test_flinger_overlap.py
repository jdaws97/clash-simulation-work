"""Adversarial source composition and control clocks, using exact boundaries."""

import unittest

import test_siege_lifecycle as lifecycle_fixtures


class FlingerOverlapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lifecycle_fixtures.SiegeLifecycleTests.setUpClass()

    def probe(self, offsets, fractions=None, kill_at=None, protected=False):
        fixture = lifecycle_fixtures.SiegeLifecycleTests()
        instance = lifecycle_fixtures.extended_instance(
            fixture.catalog, "flame-flinger"
        )
        policy = instance["siege_parameters"]["behavior"]
        policy.update(
            shot_offsets_seconds=offsets, flame_dps_fractions=fractions or [1]
        )
        actors, runtime, _, trace = fixture.runtime(instance)
        if protected:
            actors["defense"]["immune_until"] = 100
        runtime.launch(actors["siege"], actors["defense"], actors, 0, trace)
        damage = runtime.resolve(actors, 0, trace)
        time = 0
        checkpoints = {1, 2}
        if kill_at is not None:
            checkpoints.add(kill_at)
        for _ in range(64):
            boundary = runtime.next_boundary(time)
            candidates = [point for point in checkpoints if point > time]
            if boundary is not None:
                candidates.append(boundary)
            if not candidates or min(candidates) > 3.1:
                break
            boundary = min(candidates)
            self.assertGreater(boundary, time)
            time = boundary
            if time == kill_at:
                actors["siege"]["hp"] = 0
            runtime.prepare(actors, time, trace)
            for target, amount in runtime.resolve(actors, time, trace).items():
                damage[target] += amount
        else:
            self.fail("Bounded Flinger probe failed to make finite event progress")
        pulses = [
            event
            for event in trace
            if event.get("packet_kind") == "flame_pulse"
            and event["target"] == "defense"
        ]
        self.assertEqual(runtime.result()["active_flame_fields"], 0)
        self.assertEqual(runtime.result()["flame_damage_clocks"], {})
        self.assertFalse(
            any(
                fact["id"].startswith("flinger-source:")
                for fact in runtime.continuation_reasons(time)
            )
        )
        return actors, runtime, trace, pulses, damage

    def test_staggered_and_aligned_fields_share_one_source_rate_and_exact_union(self):
        for offsets, expected in (([0, 0.1, 0.2], 176), ([0, 0.5, 1], 240)):
            with self.subTest(offsets=offsets):
                _, runtime, _, pulses, _ = self.probe(offsets)
                self.assertEqual(
                    runtime.models["siege"]["statistics"]["flame_max_dps"], 80
                )
                self.assertAlmostEqual(
                    sum(event["damage"] for event in pulses), expected
                )
                self.assertAlmostEqual(
                    sum(
                        event["damage"]
                        for event in pulses
                        if 1 < event["time_seconds"] <= 2
                    ),
                    80,
                )
                for event in pulses:
                    interval = event["flame_interval"]
                    self.assertLessEqual(
                        event["damage"],
                        80 * (interval["end"] - interval["start"]) + 1e-9,
                    )

    def test_source_loss_preserves_launched_field_clock_and_cancels_only_unlaunched(
        self,
    ):
        _, _, trace, pulses, _ = self.probe([0, 0.1, 0.2], kill_at=0.21)
        self.assertAlmostEqual(sum(event["damage"] for event in pulses), 176)
        self.assertTrue(all(event["time_seconds"] > 0.21 for event in pulses))
        self.assertFalse(
            any(
                event["event"] == "flinger_unlaunched_shot_cancelled" for event in trace
            )
        )
        _, _, trace, pulses, _ = self.probe([0, 0.1, 0.2], kill_at=0.01)
        self.assertAlmostEqual(sum(event["damage"] for event in pulses), 160)
        self.assertEqual(
            sum(
                event["event"] == "flinger_unlaunched_shot_cancelled" for event in trace
            ),
            2,
        )

    def test_ramp_protection_and_opaque_continuation_contract(self):
        _, _, _, pulses, _ = self.probe([0, 0.1, 0.2], fractions=[0.5, 1])
        self.assertAlmostEqual(sum(event["damage"] for event in pulses), 156)
        _, _, _, pulses, damage = self.probe([0, 0.1, 0.2], protected=True)
        self.assertTrue(all(event["protected"] for event in pulses))
        self.assertEqual(damage["defense"], 0)
        fixture = lifecycle_fixtures.SiegeLifecycleTests()
        actors, runtime, _, trace = fixture.runtime(
            lifecycle_fixtures.extended_instance(fixture.catalog, "flame-flinger")
        )
        runtime.launch(actors["siege"], actors["defense"], actors, 0, trace)
        # Future launch intentions are not forged damage receipts. The shared
        # consumer binding remains a lead-owned integration requirement.
        facts = runtime.continuation_reasons(0)
        self.assertEqual(len(facts), 3)
        self.assertTrue(all(fact["source_team"] == "attack" for fact in facts))
        actors["siege"]["hp"] = 0
        runtime.prepare(actors, 0, trace)
        self.assertEqual(runtime.continuation_reasons(0), [])


if __name__ == "__main__":
    unittest.main()
