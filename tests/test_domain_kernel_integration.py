"""Shared-kernel acceptance for explicit synthetic domain contracts."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import simulate_full_battle
from clashlab.pet_rules import RULES as PET_RULES, SCOPE as PET_SCOPE
from clashlab.spatial import simulate_spatial
from clashlab.yak_lifecycle import POLICIES as YAK_POLICIES
from clashlab.jelly_lifecycle import POLICIES as JELLY_POLICIES

from test_adapters import entity_instance
from test_advanced_defense_integration import advanced_sector
from test_equipment_pet_lifecycles import SOURCE
from test_electro_titans import aura_parameters
from test_full_battle import fixture, add_hero
from test_hero_pets import pet_parameters
from test_indirect_defenses import fixed_tank
from test_spell_towers import spell_tower_instance


ROOT = Path(__file__).resolve().parents[1]


class DomainKernelIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def simulate(self, entities, **changes):
        scene = compile_entity_scene(
            advanced_sector(self.catalog, entities, **changes), self.catalog
        )["scene"]
        return simulate_spatial(scene)

    def test_titan_aura_is_bound_to_paid_troop_and_shared_health(self):
        from clashlab.attacking_extensions import SCOPE as EXTENSION_SCOPE
        from clashlab.hero_roster_rules import RULES, SCOPE

        for step in (0.017, 0.3):
            inputs = fixture(self.catalog, time_limit=0.7)
            scene = inputs[0]["entity_scene"]
            hall = scene["entities"][0]
            titan = entity_instance(
                "titan",
                "electro-titan",
                4,
                "attack",
                x=9.5,
                y=5.5,
                first_attack_seconds=100,
                wall_parameters={"kind": "avoid", "source": SOURCE},
                attacking_extension_scope=EXTENSION_SCOPE,
                aura_parameters=aura_parameters(),
            )
            scene.update(
                scope=SCOPE,
                model_rules=deepcopy(RULES),
                buff_spells=[],
                pets=[],
                maximum_step_seconds=step,
                entities=[hall, titan],
            )
            inputs[1]["levels"]["electro-titan"] = 4
            inputs[2]["troops"] = [{"id": "electro-titan", "level": 4, "count": 1}]
            result = simulate_full_battle(*inputs, self.catalog)
            pulses = [
                e
                for e in result["combat"]["trace"]
                if e.get("event") == "electro_titan_aura_pulse"
            ]
            self.assertEqual([e["time_seconds"] for e in pulses], [0, 0.4])
            target = result["combat"]["actors"]["hall"]
            self.assertAlmostEqual(target["maximum_hp"] - target["hp"], 110)
            self.assertEqual(result["resource_use"]["deployed_attacker_ids"], ["titan"])
            self.assertFalse(result["resource_use"]["undeployed_attacker_ids"])
            titan.pop("attacking_extension_scope")
            with self.assertRaisesRegex(InputError, "explicit attacking extension"):
                simulate_full_battle(*inputs, self.catalog)

    def test_explicit_xbow_rounds_stop_shared_weapon_without_refill(self):
        bow = entity_instance(
            "bow",
            "x-bow",
            1,
            "defense",
            x=2,
            y=4,
            defense_ammunition_parameters={
                "source": SOURCE,
                "status": "experimental_not_replay_calibrated",
                "initial_rounds": 2,
                "reload": "none_during_battle",
            },
        )
        for step in (0.017, 0.5):
            result = self.simulate(
                [bow, fixed_tank(x=9.5, y=5.5)],
                duration_seconds=1,
                maximum_step_seconds=step,
            )
            launches = [
                e
                for e in result["trace"]
                if e.get("event") == "projectile_launch" and e["source"] == "bow"
            ]
            self.assertEqual(len(launches), 2)

    def test_geared_cannon_shared_launches_preserve_burst_gap_at_two_steps(self):
        cannon = entity_instance(
            "cannon",
            "cannon",
            20,
            "defense",
            x=2,
            y=4,
            mode="gearedUpBurst",
            statistics_mode="gearedUpBurst",
            geared_cannon_parameters={
                "source": SOURCE,
                "status": "experimental_not_replay_calibrated",
                "burst_timing": "snapshot_timeBetweenBursts_is_post_last_shot_gap",
                "targeting": "retain_eligible_primary_reacquire_per_shot",
                "freeze": "pause_remaining_shot_clock_preserve_burst_index",
            },
        )
        for step in (0.017, 0.8):
            result = self.simulate(
                [cannon, fixed_tank(x=6.5, y=5.5)],
                duration_seconds=2.2,
                maximum_step_seconds=step,
            )
            launches = [
                event
                for event in result["trace"]
                if event.get("event") == "projectile_launch"
                and event["source"] == "cannon"
            ]
            self.assertEqual(
                [round(event["time_seconds"], 6) for event in launches],
                [0, 0.192, 0.384, 0.576, 2.176],
            )
            self.assertEqual(
                result["geared_cannons"]["states"]["cannon"]["launched_shots"], 5
            )

    def test_earthquake_tower_released_damage_reaches_shared_health(self):
        tower = spell_tower_instance("earthquake", level=4, town_hall=17)
        parameters = tower["spell_tower_parameters"]
        parameters["effect"] = {
            "radius_multiplier": 1,
            "duration_multiplier": 1,
            "membership_policy": "one_pulse_at_released_payload_arrival",
            "status": "experimental_not_replay_calibrated",
            "statistic_basis": "snapshot_troopDamagePercent_of_current_maximum_hp",
            "damage_fraction_multiplier": 1,
            "stacking_policy": "independent_additive_single_pulses",
        }
        parameters["recipients"].update(
            target_kinds=["unit"], target_layers=["ground", "air"]
        )
        parameters["cast"].update(delay_seconds=0, impact_delay_seconds=0.25)
        parameters["death"]["policy"] = "none"
        for step in (0.017, 0.8):
            result = self.simulate(
                [tower, fixed_tank(x=9.5, y=5.5)],
                duration_seconds=0.5,
                maximum_step_seconds=step,
                effects=[
                    {
                        "id": "kill-tower",
                        "kind": "damage",
                        "time_seconds": 0.1,
                        "targets": ["spell-tower"],
                        "amount": 1000000,
                    }
                ],
            )
            impacts = [
                event
                for event in result["trace"]
                if event.get("event") == "spell_tower_quake_impact"
            ]
            self.assertEqual(len(impacts), 1)
            self.assertEqual(impacts[0]["time_seconds"], 0.25)
            target = result["actors"]["tank"]
            self.assertAlmostEqual(target["hp"], target["maximum_hp"] * 0.7)
            self.assertEqual(result["actors"]["spell-tower"]["hp"], 0)

    def test_full_battle_pet_owner_loss_and_resource_identity(self):
        for entity in ("mighty-yak", "angry-jelly"):
            for step in (0.017, 0.25):
                inputs = fixture(self.catalog, time_limit=0.5)
                owner = add_hero(inputs[0], inputs[2], inputs[1])
                owner["modifiers"]["hitpoints_multiplier"] = 0.001
                for instance in inputs[0]["entity_scene"]["entities"]:
                    if instance["entity"] == "pekka":
                        instance.update(x=0.5, y=0.5, first_attack_seconds=100)
                    elif instance["entity"] == "town-hall":
                        instance["town_hall_parameters"]["activation"][
                            "initial_state"
                        ] = "active"
                owner["hero_parameters"][
                    "pet_policy"
                ] = "paired_pet_from_explicit_scene_assignment"
                parameters = pet_parameters("lassi")
                if entity == "mighty-yak":
                    parameters.update(
                        target_retention="independent_wall_routing_experimental",
                        owner_death_policy="independent_combat_one_owner_defeat_rage",
                        ground_wall_policy="clear_obstructions",
                        behavior=deepcopy(YAK_POLICIES),
                    )
                    level, event_name = 15, "yak_owner_defeat_rage"
                else:
                    parameters.update(
                        target_retention="prefer_owner_primary_then_nearest",
                        owner_death_policy="separate_then_independent_no_reattachment",
                        ground_wall_policy="not_applicable_air",
                        behavior=deepcopy(JELLY_POLICIES),
                    )
                    level, event_name = 10, "jelly_separated"
                scene = inputs[0]["entity_scene"]
                scene.update(
                    scope=PET_SCOPE,
                    model_rules=deepcopy(PET_RULES),
                    buff_spells=[],
                    maximum_step_seconds=step,
                    pets=[
                        {
                            "id": "paired",
                            "entity": entity,
                            "level": level,
                            "town_hall": 16,
                            "hero_id": owner["id"],
                            "parameters": parameters,
                        }
                    ],
                    effects=[],
                )
                inputs[1]["levels"][entity] = level
                inputs[2]["heroes"][0]["pet"] = {"id": entity, "level": level}
                result = simulate_full_battle(*inputs, self.catalog)
                events = [
                    e for e in result["combat"]["trace"] if e.get("event") == event_name
                ]
                self.assertEqual(len(events), 1)
                self.assertEqual(
                    events[0]["time_seconds"],
                    result["combat"]["actors"][owner["id"]]["death_time"],
                )
                self.assertIn("paired", result["resource_use"]["deployed_attacker_ids"])
                self.assertFalse(result["resource_use"]["undeployed_attacker_ids"])


if __name__ == "__main__":
    unittest.main()
