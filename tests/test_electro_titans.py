"""Independent Electro Titan aura contracts; fixtures are not replay evidence."""

import unittest
from copy import deepcopy
from pathlib import Path

from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.damage_receipts import DamageReceipts
from clashlab.electro_titans import ElectroTitanCombat, compile_electro_titan
from clashlab.spatial import _load_actors

from test_adapters import entity_instance, projectile
from test_spatial import synthetic_scene, synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-v30-policy-not-calibrated"


def aura_parameters(**changes):
    parameters = {
        "source": SOURCE,
        "first_pulse_delay_seconds": 0,
        "geometry": "source_center_to_target_footprint",
        "membership": "live_at_each_pulse",
        "freeze_policy": "continues_while_frozen",
        "visibility_policy": "hits_invisible",
        "damage_scaling": "source_damage_multiplier_at_pulse",
        "stacking": "additive_per_source",
        "protection": "shared_damage_immunity",
        "source_persistence": "living_deployed_source_only",
    }
    return {**parameters, **changes}


def titan(catalog, key="titan", level=4, **changes):
    instance = entity_instance(
        key, "electro-titan", level, "attack", aura_parameters=aura_parameters()
    )
    actor = synthetic_unit(key, x=4.5, y=4.5, damage=360, range=1.25)
    actor.update(
        {
            "source": catalog.records["electro-titan"]["source"],
            "entity_adapter": {"entity": "electro-titan", "level": level},
            "attack_model": {"kind": "single", "projectile": projectile()},
        }
    )
    actor.update(changes)
    return compile_electro_titan(
        actor,
        instance,
        catalog.entity("electro-titan"),
        catalog.level("electro-titan", level),
        instance["modifiers"],
    )


def loaded(actors):
    return _load_actors(synthetic_scene(actors, width=20, height=20), 20, 20)


class ElectroTitanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_aura_statistics_do_not_replace_weapon_or_inherit_weapon_cadence(self):
        actor = titan(self.catalog)
        self.assertEqual(actor["damage"], 360)
        self.assertEqual(actor["range"], 1.25)
        self.assertEqual(actor["aura_model"]["damage_per_pulse"], 55)
        self.assertEqual(actor["aura_model"]["interval_seconds"], 0.4)
        self.assertEqual(actor["aura_model"]["radius"], 3.5)

    def test_live_footprint_membership_air_ground_walls_and_friendly_filter(self):
        actors = loaded(
            [
                titan(self.catalog),
                synthetic_structure("edge", x=8, y=4, width=3, height=3),
                synthetic_structure("wall", kind="wall", x=4, y=6),
                synthetic_unit(
                    "air", x=4.5, y=7.5, team="defense", layer="air", movement="air"
                ),
                synthetic_unit("friend", x=4.5, y=5.5),
                synthetic_unit("outside", x=4.5, y=8.1, team="defense"),
            ]
        )
        runtime = ElectroTitanCombat(actors)
        self.assertEqual(dict(runtime.resolve(0, [])), {"air": 55, "edge": 55})
        actors["air"]["y"] = 15
        actors["outside"]["y"] = 5
        self.assertEqual(dict(runtime.resolve(0.4, [])), {"edge": 55, "outside": 55})

    def test_center_geometry_does_not_silently_use_large_footprint(self):
        actor = titan(self.catalog)
        actor["aura_model"]["parameters"]["geometry"] = "center_to_center"
        actors = loaded(
            [actor, synthetic_structure("edge", x=8, y=4, width=3, height=3)]
        )
        self.assertEqual(dict(ElectroTitanCombat(actors).resolve(0, [])), {})

    def test_freeze_skip_keeps_original_clock_and_visibility_policy(self):
        actor = titan(self.catalog)
        actor["aura_model"]["parameters"].update(
            freeze_policy="skip_frozen_pulses", visibility_policy="requires_targetable"
        )
        actors = loaded([actor, synthetic_structure(x=6, y=4)])
        runtime = ElectroTitanCombat(actors)
        actors["titan"]["frozen_until"] = 0.3
        self.assertEqual(dict(runtime.resolve(0, [])), {})
        self.assertEqual(runtime.next_boundary(0.3), 0.4)
        actors["tower"]["_untargetable_until"] = 0.5
        self.assertEqual(dict(runtime.resolve(0.4, [])), {})
        self.assertEqual(runtime.resolve(0.8, [])["tower"], 55)

    def test_source_death_stops_aura_without_lingering_pending_damage(self):
        actors = loaded([titan(self.catalog), synthetic_structure(x=6, y=4)])
        runtime = ElectroTitanCombat(actors)
        self.assertEqual(runtime.resolve(0, [])["tower"], 55)
        actors["titan"]["hp"] = 0
        self.assertEqual(dict(runtime.resolve(0.4, [])), {})
        self.assertIsNone(runtime.next_boundary(0.4))

    def test_aura_visibility_composes_every_concealment_source(self):
        for field in (
            "_untargetable_until",
            "_spell_tower_untargetable_until",
            "_attack_spell_untargetable_until",
        ):
            with self.subTest(field=field):
                actor = titan(self.catalog)
                actor["aura_model"]["parameters"][
                    "visibility_policy"
                ] = "requires_targetable"
                actors = loaded([actor, synthetic_structure(x=6, y=4)])
                actors["tower"][field] = 2
                runtime = ElectroTitanCombat(actors)
                self.assertEqual(dict(runtime.resolve(0, [])), {})
                runtime.models["titan"]["parameters"][
                    "visibility_policy"
                ] = "hits_invisible"
                self.assertEqual(runtime.resolve(0.4, [])["tower"], 55)

    def test_catalog_only_scaling_leaves_runtime_buff_out_of_aura_damage(self):
        actor = titan(self.catalog)
        actor["aura_model"]["parameters"]["damage_scaling"] = "catalog_aura_only"
        actors = loaded([actor, synthetic_structure(x=6, y=4)])
        actors["titan"]["_buff_damage_multiplier"] = 3
        actors["titan"]["_hero_damage_multiplier"] = 4
        self.assertEqual(ElectroTitanCombat(actors).resolve(0, [])["tower"], 55)

    def test_controlled_deployment_anchors_first_pulse_to_actual_release(self):
        actor = titan(self.catalog, spawn_seconds="controlled")
        actor["aura_model"]["parameters"]["first_pulse_delay_seconds"] = 0.2
        actors = loaded([actor, synthetic_structure(x=6, y=4)])
        runtime = ElectroTitanCombat(actors)
        self.assertIsNone(runtime.next_boundary(0))
        actors["titan"]["spawn_seconds"] = 3
        self.assertAlmostEqual(runtime.next_boundary(3), 3.2)
        self.assertEqual(runtime.resolve(3.2, [])["tower"], 55)

    def test_additive_and_strongest_stacking_preserve_receipt_ownership(self):
        for policy, expected in (
            ("additive_per_source", 165),
            ("strongest_due_source_per_recipient", 110),
        ):
            with self.subTest(policy=policy):
                first = titan(self.catalog, "a")
                second = titan(self.catalog, "b")
                for actor in (first, second):
                    actor["aura_model"]["parameters"]["stacking"] = policy
                actors = loaded(
                    [first, second, synthetic_structure(hitpoints=1000, x=6, y=4)]
                )
                actors["b"]["_buff_damage_multiplier"] = 2
                runtime = ElectroTitanCombat(actors)
                runtime.damage_receipts = DamageReceipts()
                damage = runtime.resolve(0, [])
                self.assertEqual(damage["tower"], expected)
                receipts = runtime.damage_receipts.settle(actors, damage, 0)
                self.assertTrue(
                    all(
                        item["source_team"] == "attack" and item["origin"] == "ability"
                        for item in receipts
                    )
                )
                self.assertEqual(
                    {item["source_actor_id"] for item in receipts},
                    {"a", "b"} if policy == "additive_per_source" else {"b"},
                )

    def test_damage_immunity_and_hidden_defense_share_receipt_protection(self):
        actors = loaded([titan(self.catalog), synthetic_structure(x=6, y=4)])
        runtime = ElectroTitanCombat(actors)
        runtime.damage_receipts = DamageReceipts()
        actors["tower"]["immune_until"] = 1
        damage = runtime.resolve(0, [])
        self.assertEqual(damage["tower"], 0)
        receipt = runtime.damage_receipts.settle(actors, damage, 0)[0]
        self.assertTrue(receipt["protected"])
        actors["tower"]["_tesla_hidden"] = True
        self.assertEqual(dict(runtime.resolve(0.4, [])), {})

    def test_malformed_policy_mixed_stacking_and_skipped_boundaries_reject(self):
        first = titan(self.catalog, "a")
        second = titan(self.catalog, "b")
        second["aura_model"]["parameters"][
            "stacking"
        ] = "strongest_due_source_per_recipient"
        with self.assertRaisesRegex(InputError, "shared stacking"):
            ElectroTitanCombat(loaded([first, second]))
        bad = deepcopy(first)
        bad["aura_model"]["parameters"].pop("freeze_policy")
        with self.assertRaises(InputError):
            ElectroTitanCombat(loaded([bad]))
        runtime = ElectroTitanCombat(loaded([first]))
        runtime.prepare(0)
        with self.assertRaisesRegex(InputError, "boundary was skipped"):
            runtime.resolve(0.1, [])


if __name__ == "__main__":
    unittest.main()
