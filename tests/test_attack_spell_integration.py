"""Paid attacking spells participate in shared targeting, clocks and accounting."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene, partial_adapter_status
from clashlab.attack_spell_models import SPELL_CLASSES
from clashlab.attack_spell_rules import RULES, RULESET, SCOPE
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial
from clashlab.termination_rules import RULES as OLD_RULES, SCOPE as OLD_SCOPE

from test_adapters import entity_instance
from test_attack_spells import SOURCE, spell_instance
from test_battle_termination import classification, termination_policy
from test_builder_huts import hut_instance
from test_defending_heroes import defender_sector
from test_full_battle import fixture
from test_garrisons import castle_instance, member_instance
from test_guardians import guardian_instance, guardian_hall
from test_indirect_defenses import fixed_tank, indirect_instance
from test_valkyrie_integration import building


ROOT = Path(__file__).resolve().parents[1]


def attack_spell_sector(catalog, entities, casts=(), **changes):
    return defender_sector(
        catalog,
        entities,
        scope=SCOPE,
        model_rules=deepcopy(RULES),
        attack_spells=list(casts),
        **changes,
    )


def attack_spell_battle(catalog, casts=()):
    specification, account, army, layout = fixture(catalog, time_limit=10)
    scene = specification["entity_scene"]
    scene.update(
        scope=SCOPE,
        model_rules=deepcopy(RULES),
        buff_spells=[],
        attack_spells=list(casts),
    )
    scene["entities"] = scene["entities"][:2]
    army["troops"][0]["count"] = 1
    hall = scene["entities"][0]
    hall["town_hall_parameters"]["activation"].update(
        initial_state="active", activation_delay_seconds=0.5
    )
    scene["entities"][1]["modifiers"]["hitpoints_multiplier"] = 0.0001
    policies = []
    for cast in casts:
        entity = cast["entity"]
        cast["town_hall"] = account["town_hall"]
        account["levels"][entity] = cast["level"]
        account["donation_levels"][entity] = cast["level"]
        inventory = (
            army["spells"]
            if cast.get("origin", "army") == "army"
            else army["clan_castle"]["spells"]
        )
        entry = next(
            (
                item
                for item in inventory
                if item["id"] == entity and item["level"] == cast["level"]
            ),
            None,
        )
        if entry is None:
            inventory.append({"id": entity, "level": cast["level"], "count": 1})
            policies.append(
                classification(
                    {
                        "origin": cast.get("origin", "army"),
                        "entity": entity,
                        "level": cast["level"],
                    },
                    SPELL_CLASSES[entity],
                    "while_unspent" if SPELL_CLASSES[entity] == "damage" else "ignore",
                )
            )
        else:
            entry["count"] += 1
    specification["termination_policy"] = termination_policy(policies)
    return specification, account, army, layout


class AttackSpellIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def simulate(self, entities, casts, **changes):
        compiled = compile_entity_scene(
            attack_spell_sector(self.catalog, entities, casts, **changes), self.catalog
        )
        return simulate_spatial(compiled["scene"])

    def test_each_family_requires_v29_and_cast_collection(self):
        for entity in SPELL_CLASSES:
            with self.subTest(entity=entity):
                self.assertTrue(
                    partial_adapter_status(self.catalog.entity(entity))["available"]
                )
                spec = attack_spell_sector(
                    self.catalog, [fixed_tank()], [spell_instance(entity)]
                )
                spec.update(scope=OLD_SCOPE, model_rules=deepcopy(OLD_RULES))
                with self.assertRaisesRegex(InputError, "v29"):
                    compile_entity_scene(spec, self.catalog)
        spec = attack_spell_sector(self.catalog, [fixed_tank()])
        del spec["attack_spells"]
        with self.assertRaisesRegex(InputError, "attack_spells"):
            compile_entity_scene(spec, self.catalog)

    def test_lightning_hits_before_defense_launch_and_settles_health(self):
        cannon = entity_instance("cannon", "cannon", 1, "defense", x=10, y=10)
        cannon["modifiers"]["hitpoints_multiplier"] = 0.1
        result = self.simulate([cannon, fixed_tank(x=15.5, y=10.5)], [spell_instance()])
        self.assertEqual(result["ruleset"], RULESET)
        self.assertEqual(result["actors"]["cannon"]["death_time"], 0)
        self.assertFalse(
            any(
                event.get("event") == "attack_launch"
                and event.get("source") == "cannon"
                for event in result["trace"]
            )
        )

    def test_received_origin_binds_and_budget_donor_and_classification_fail_closed(
        self,
    ):
        owned = spell_instance(id="owned", x=12, y=6)
        donated = spell_instance(
            id="received",
            x=12,
            y=6,
            origin="clan_castle",
            received_spell_parameters={
                "source": SOURCE,
                "donor_town_hall": 18,
                "receiver_clan_castle_level": 12,
                "level_basis": "snapshot_receiver_lab_cap_with_unlock_floor",
            },
        )
        inputs = attack_spell_battle(self.catalog, [owned, donated])
        compiled = compile_full_battle(*inputs, self.catalog)
        self.assertEqual(
            {item["origin"] for item in compiled["validation"]["spell_bindings"]},
            {"army", "clan_castle"},
        )
        models = compiled["compiled"]["scene"]["attack_spell_models"]
        self.assertEqual(models[1]["entity_adapter"]["origin"], "clan_castle")
        bad = deepcopy(inputs)
        bad[2]["spells"][0]["count"] = 0
        with self.assertRaises(InputError):
            compile_full_battle(*bad, self.catalog)
        bad = deepcopy(inputs)
        bad[0]["entity_scene"]["attack_spells"][1]["received_spell_parameters"][
            "donor_town_hall"
        ] = 1
        with self.assertRaises(InputError):
            compile_full_battle(*bad, self.catalog)
        bad = deepcopy(inputs)
        bad[0]["termination_policy"]["spell_inventory"][0].update(
            classification="support_only", continuation="ignore"
        )
        with self.assertRaisesRegex(InputError, "classification"):
            compile_full_battle(*bad, self.catalog)

    def test_released_lightning_outlives_last_attacker_and_spends_at_cast(self):
        cast = spell_instance(x=12, y=6)
        cast["parameters"]["impact_delay_seconds"] = 2
        result = simulate_full_battle(
            *attack_spell_battle(self.catalog, [cast]), self.catalog
        )
        self.assertEqual(result["outcome"]["end_reason"], "attack_force_exhausted")
        self.assertEqual(result["outcome"]["elapsed_seconds"], 2)
        self.assertTrue(result["resource_use"]["spell_slots"][0]["spent"])
        self.assertEqual(result["combat"]["actors"]["pekka-0"]["death_time"], 0.5)

    def test_poison_continues_only_through_last_positive_pulse(self):
        cast = spell_instance("poison-spell", x=0, y=0)
        cast["parameters"]["duration_multiplier"] = 1.25 / 16
        result = simulate_full_battle(
            *attack_spell_battle(self.catalog, [cast]), self.catalog
        )
        self.assertEqual(result["outcome"]["elapsed_seconds"], 1)

    def test_support_fields_and_future_support_casts_do_not_extend_exhaustion(self):
        for entity in ("invisibility-spell", "overgrowth-spell"):
            for cast_time in (0, 8):
                with self.subTest(entity=entity, cast_time=cast_time):
                    cast = spell_instance(entity, time_seconds=cast_time, x=0, y=0)
                    result = simulate_full_battle(
                        *attack_spell_battle(self.catalog, [cast]), self.catalog
                    )
                    self.assertEqual(result["outcome"]["elapsed_seconds"], 0.5)
                    self.assertEqual(
                        result["resource_use"]["spell_slots"][0]["spent"],
                        cast_time == 0,
                    )

    def test_unspent_damage_spell_requires_new_scope_even_without_a_cast(self):
        inputs = attack_spell_battle(self.catalog, [spell_instance()])
        scene = inputs[0]["entity_scene"]
        scene.update(scope=OLD_SCOPE, model_rules=deepcopy(OLD_RULES))
        del scene["attack_spells"]
        with self.assertRaisesRegex(InputError, "v29"):
            compile_full_battle(*inputs, self.catalog)

    def test_overgrowth_keeps_castle_release_running_and_invisibility_cloaks_new_member(
        self,
    ):
        member = member_instance(first_attack_seconds=10)
        castle = castle_instance([member])
        tank = fixed_tank(x=15.5, y=11.5)
        overgrowth = spell_instance("overgrowth-spell", x=21, y=11)
        invisibility = spell_instance("invisibility-spell", x=21, y=11)
        result = self.simulate(
            [castle, member, tank], [overgrowth, invisibility], duration_seconds=0.3
        )
        self.assertAlmostEqual(result["actors"]["member"]["spawn_seconds"], 0.2)
        member_frame = result["frames"][-1]["actors"]["member"]
        self.assertGreater(member_frame["attack_spell_untargetable_until"], 0.3)
        self.assertEqual(result["actors"]["castle"]["frozen_until"], 0)

    def test_poison_slows_new_garrison_member_before_its_first_weapon_work(self):
        member = member_instance()
        castle = castle_instance([member])
        tank = fixed_tank(x=15.5, y=11.5)
        poison = spell_instance("poison-spell", x=21, y=11)
        result = self.simulate([castle, member, tank], [poison], duration_seconds=0.3)
        changes = [
            event
            for event in result["trace"]
            if event.get("event") == "hazard_status_change"
            and event.get("target") == "member"
        ]
        self.assertEqual(changes[0]["time_seconds"], 0.2)
        self.assertLess(changes[0]["attack_rate"], 1)

    def test_overgrowth_does_not_pause_guardian_emergence(self):
        guardian = guardian_instance()
        hall = guardian_hall(guardian)
        tank = fixed_tank(x=15.5, y=11.5)
        result = self.simulate(
            [hall, guardian, tank],
            [spell_instance("overgrowth-spell", x=21, y=11)],
            duration_seconds=0.3,
        )
        self.assertAlmostEqual(result["actors"]["guardian"]["spawn_seconds"], 0.2)

    def test_eagle_counts_paid_spell_once_at_cast_time(self):
        eagle = indirect_instance("eagle-artillery")
        activation = eagle["indirect_parameters"]["activation"]
        activation["actor_weights"] = {"tank": 0}
        activation["command_weights"] = {"paid": 200}
        cast = spell_instance(id="paid", time_seconds=0.5, x=0, y=0)
        result = self.simulate([eagle, fixed_tank()], [cast], duration_seconds=1)
        state = result["indirect_defenses"]["states"]["weapon"]
        self.assertTrue(state["activated"])
        self.assertEqual(state["total_weight"], 200)
        self.assertEqual(
            result["indirect_defenses"]["counted_command_ids"]["weapon"], ["paid"]
        )

    def test_visibility_and_overgrowth_preserve_previously_released_defense_hit(self):
        for entity in ("invisibility-spell", "overgrowth-spell"):
            with self.subTest(entity=entity):
                cannon = entity_instance("cannon", "cannon", 1, "defense", x=10, y=10)
                cannon["attack_parameters"]["projectile"] = {
                    "timing": "launch_distance_delay",
                    "speed_tiles_per_second": 8,
                    "destination": "locked_actor_center_at_impact",
                    "hit_radius": 0,
                }
                tank = fixed_tank(x=15.5, y=11.5)
                cast = spell_instance(
                    entity,
                    time_seconds=0.25,
                    x=15.5 if entity == "invisibility-spell" else 11.5,
                    y=11.5,
                )
                # Keep the Invisibility field away from the cannon so only the
                # retained target becomes untargetable; Overgrowth disables it.
                cast["parameters"]["radius_multiplier"] = 0.25
                outputs = [
                    self.simulate(
                        [cannon, tank],
                        [cast],
                        duration_seconds=1.2,
                        maximum_step_seconds=step,
                    )
                    for step in (1, 0.02)
                ]
                for result in outputs:
                    expected_damage = result["actors"]["cannon"]["damage"]
                    self.assertAlmostEqual(
                        result["actors"]["tank"]["maximum_hp"]
                        - result["actors"]["tank"]["hp"],
                        expected_damage,
                    )
                self.assertEqual(
                    outputs[0]["actors"]["tank"]["hp"],
                    outputs[1]["actors"]["tank"]["hp"],
                )

    def test_poison_internal_builder_status_uses_only_explicit_builder_class(self):
        hut = hut_instance()
        tank = fixed_tank(x=15.5, y=11.5)
        poison = spell_instance("poison-spell", x=3, y=3)
        result = self.simulate([hut, tank], [poison], duration_seconds=0.1)
        self.assertEqual(
            result["builders"]["status_only_fields"], ["poison-spell:poison:builder"]
        )
        statuses = [
            event
            for event in result["trace"]
            if event.get("event") == "hazard_status_change"
            and event.get("target") == "hut::builder"
        ]
        self.assertEqual(len(statuses), 1)
        self.assertLess(statuses[0]["attack_rate"], 1)

    def test_unspent_damage_cast_keeps_exhausted_army_open_until_cast(self):
        cast = spell_instance(time_seconds=2, x=12, y=6)
        result = simulate_full_battle(
            *attack_spell_battle(self.catalog, [cast]), self.catalog
        )
        self.assertEqual(result["combat"]["actors"]["pekka-0"]["death_time"], 0.5)
        self.assertEqual(result["outcome"]["elapsed_seconds"], 2)
        self.assertEqual(
            result["combat"]["attack_spells"]["launched"], ["lightning-spell"]
        )


if __name__ == "__main__":
    unittest.main()
