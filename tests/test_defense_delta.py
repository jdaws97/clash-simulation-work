"""Bounded defensive ownership and source-row integration checks."""

import unittest
from pathlib import Path

from clashlab.adapters import compile_actor
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.defense_upgrades import (
    compile_supercharged_defense,
    attach_inferno_ammunition,
    InfernoAmmunitionCombat,
)
from clashlab.defending_cc_extensions import (
    SCOPE,
    compile_defending_extension,
    compile_defending_reserves,
    DefendingSummonCombat,
)
from clashlab.defending_heroes import compile_defending_hero, DefendingHeroCombat
from clashlab.combat import PatternCombat

from test_adapters import entity_instance
from test_attacking_extensions import unit, summon_parameters, load, SOURCE
from test_garrisons import member_instance
from test_defending_heroes import defender_instance
from test_spatial import synthetic_structure, synthetic_unit
from test_electro_titans import titan, loaded
from clashlab.defending_troop_runtime import DefendingTitanCombat, DefendingDruidCombat
from test_druids import compiled_druid


ROOT = Path(__file__).resolve().parents[1]


class DefenseDeltaTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog.load(ROOT / "data")

    def test_absolute_supercharge_reuses_existing_weapon_without_mutating_catalog(self):
        entity = self.catalog.entity("air-defense")
        base = max(
            row["level"] for row in entity["levels"] if not row.get("supercharge")
        )
        selected = self.catalog.level("air-defense", 1, True)
        instance = entity_instance(
            "charged", "air-defense", base, "defense", town_hall=18, supercharge=True
        )
        instance["supercharge_parameters"] = {
            "source": SOURCE,
            "status": "explicit_uncalibrated_hypothesis",
            "tier": 1,
            "base_level": base,
            "statistics_mapping": "absolute_pinned_supercharge_row",
        }
        actor = compile_supercharged_defense(instance, self.catalog, 8, compile_actor)
        self.assertEqual(actor["hitpoints"], selected["hitpoints"])
        self.assertEqual(actor["entity_adapter"]["supercharge_source_row"], selected)
        self.assertTrue(self.catalog.level("air-defense", 1, True)["supercharge"])
        self.assertEqual(actor["attack_model"]["target_layers"], ["air"])
        instance["level"] = base - 1
        with self.assertRaises(InputError):
            compile_supercharged_defense(instance, self.catalog, 8, compile_actor)

    def test_inferno_partial_beams_freeze_and_no_second_clock(self):
        raw = synthetic_structure("inferno", entity_adapter={"entity": "inferno-tower"})
        attach_inferno_ammunition(
            raw,
            {
                "source": SOURCE,
                "status": "explicit_uncalibrated_hypothesis",
                "initial_rounds": 2,
                "consumption": "one_round_per_released_beam",
                "reload": "none_during_battle",
                "depleted_lock": "clear_target_no_new_launches",
            },
        )
        actor = load([raw])["inferno"]
        runtime = InfernoAmmunitionCombat({"inferno": actor})
        actor["frozen_until"] = 1
        self.assertEqual(runtime.reserve_launch(actor, ["a", "b", "c"], 0, []), [])
        self.assertEqual(runtime.remaining["inferno"], 2)
        clock = actor["next_attack"]
        self.assertEqual(
            runtime.reserve_launch(actor, ["a", "b", "c"], 1, []), ["a", "b"]
        )
        self.assertEqual(actor["next_attack"], clock)
        self.assertEqual(runtime.reserve_launch(actor, ["c"], 1, []), [])

    def test_hound_uses_defense_count_children_survive_parent_loss_and_attack_units(
        self,
    ):
        entity = self.catalog.entity("lava-hound")
        row = self.catalog.level("lava-hound", 1)
        row["pupsOnDefense"], row["pupsOnOffense"] = 2, 3
        actor = unit(
            "hound",
            movement="air",
            layer="air",
            spawn_seconds="controlled",
            counts_for_destruction=False,
            entity_adapter={"entity": "lava-hound", "level": 1},
            death_model={
                "effects": [
                    {
                        "kind": "area_damage",
                        "amount": row["stats"]["normal"]["deathDamage"],
                        "area": {"target_team": "defense", "target_kinds": ["unit"]},
                    }
                ]
            },
        )
        instance = member_instance(entity="lava-hound")
        instance["summon_parameters"] = summon_parameters(
            "actual_death", batch_size=2, live_cap=2
        )
        instance["defending_extension_parameters"] = {
            "source": SOURCE,
            "status": "explicit_uncalibrated_hypothesis",
            "abilities": {},
            "target_layers": ["ground", "air"],
            "wall_policy": "not_applicable",
            "hound_quantity_basis": "pupsOnDefense",
            "ice_hound_freeze_basis": "not_applicable",
        }
        compile_defending_extension(
            actor,
            instance,
            entity,
            row,
            instance["modifiers"],
            self.catalog,
            8,
            enabled_scope=SCOPE,
        )
        self.assertEqual(row["pupsOnOffense"], 3)
        children = compile_defending_reserves([actor])
        self.assertEqual(len(children), 2)
        target = unit("enemy", x=2, y=1)
        actors = load([actor, target, *children])
        actors["hound"].update(spawn_seconds=0, hp=0, death_time=0.2)
        clear = [False]
        runtime = DefendingSummonCombat(actors, lambda *args: clear[0])
        runtime.prepare(0.2, [])
        self.assertEqual(
            {fact["source_team"] for fact in runtime.continuation_reasons(0.3)},
            {"defense"},
        )
        clear[0] = True
        runtime.prepare(0.4, [])
        self.assertEqual(len(runtime.releases), 2)
        combat = PatternCombat(actors)
        combat.launch(actors["child-0"], actors["enemy"], actors, 0.4, [])
        self.assertEqual(combat.resolve(actors, 0.4, [])["enemy"], 20)
        self.assertFalse(children[0]["counts_for_destruction"])

    def test_duke_base_role_requires_explicit_intrinsic_suppression(self):
        instance = defender_instance("dragon-duke", mode="air")
        instance.pop("wall_parameters", None)
        entity, row = self.catalog.entity("dragon-duke"), self.catalog.level(
            "dragon-duke", 1
        )
        actor = synthetic_unit(
            "defender",
            x=instance["x"],
            y=instance["y"],
            team="defense",
            counts_for_destruction=False,
            entity_adapter={"entity": "dragon-duke"},
        )
        with self.assertRaises(InputError):
            compile_defending_hero(
                actor, instance, entity, row, instance["modifiers"], self.catalog, 8
            )
        instance["defending_duke_parameters"] = {
            "source": SOURCE,
            "status": "explicit_uncalibrated_hypothesis",
            "intrinsic_policy": "suppressed_pending_defensive_eligibility_evidence",
        }
        compile_defending_hero(
            actor, instance, entity, row, instance["modifiers"], self.catalog, 8
        )
        self.assertEqual(actor["movement"], "air")
        self.assertNotIn("hero_model", actor)
        self.assertEqual(actor["damage"], row["damagePerHit"])

    def test_defending_titan_live_aura_reuses_shared_pulses_and_filters(self):
        actor = titan(self.catalog)
        actor.update(
            team="defense",
            counts_for_destruction=False,
            defending_extension_model={"entity": "electro-titan"},
            garrison_member_model={"entity": "electro-titan"},
        )
        actor["aura_model"]["target_kinds"] = ["unit"]
        actors = loaded(
            [
                actor,
                synthetic_unit("enemy", x=5, y=5),
                synthetic_unit("friend", team="defense", x=5, y=5),
                synthetic_structure("building", team="attack", x=5, y=5),
            ]
        )
        runtime = DefendingTitanCombat(actors)
        self.assertEqual(dict(runtime.resolve(0, [])), {"enemy": 55})
        actors["enemy"]["y"] = 15
        self.assertEqual(dict(runtime.resolve(0.4, [])), {})

    def test_defending_druid_transform_preserves_finite_bear_ownership(self):
        parent = compiled_druid(self.catalog)[0]
        parent.update(
            team="defense",
            counts_for_destruction=False,
            defending_extension_model={
                "entity": "druid",
                "parameters": {"source": SOURCE},
            },
            garrison_member_model={"parameters": {"castle_id": "castle"}},
        )
        reserves = compile_defending_reserves([parent])
        actors = loaded([parent, *reserves])
        runtime = DefendingDruidCombat(actors)
        runtime.prepare(0, [])
        runtime.prepare(30, [])
        self.assertEqual(actors["druid-bear"]["team"], "defense")
        self.assertEqual(actors["druid-bear"]["spawn_seconds"], 30)
        self.assertEqual(actors["druid-bear"]["attack_model"]["target_kinds"], ["unit"])
        self.assertEqual(actors["druid-bear"]["damage"], 80)
        self.assertFalse(actors["druid-bear"]["counts_for_destruction"])
        with self.assertRaises(InputError):
            runtime.validate_command({"kind": "deploy", "targets": ["druid-bear"]})
