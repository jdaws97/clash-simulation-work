"""Paid advanced spell verticals under explicit synthetic integration policies."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.advanced_spell_bindings import BINDING_POLICIES
from clashlab.advanced_spell_models import SPELL_CLASSES
from clashlab.attack_spell_rules import RULES, SCOPE
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.spatial import simulate_spatial
from test_advanced_spells import cast
from test_battle_termination import classification, termination_policy
from test_full_battle import fixture
from test_adapters import entity_instance
from test_traps import trap_instance
from test_garrisons import castle_instance, member_instance

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-advanced-spell-shared-contract-not-game-calibration"


def spell_battle(catalog, entity, *, level=1, time=0, step=0.25, duration=1.2):
    model = cast(catalog, entity, time=time)
    instance = {
        "id": "spell",
        "entity": entity,
        "level": level,
        "town_hall": 16,
        "time_seconds": time,
        "x": 9.5,
        "y": 5.5,
        "parameters": deepcopy(model["parameters"]),
    }
    instance["parameters"]["spawn_interval_seconds"] = 0.05
    inputs = fixture(catalog, time_limit=duration)
    scene = inputs[0]["entity_scene"]
    scene.update(
        scope=SCOPE,
        model_rules=deepcopy(RULES),
        pets=[],
        buff_spells=[],
        attack_spells=[instance],
        maximum_step_seconds=step,
        recording_interval_seconds=0.05,
        advanced_spell_binding={"source": SOURCE, **BINDING_POLICIES},
    )
    scene["entities"] = scene["entities"][:2]
    scene["entities"][0]["town_hall_parameters"]["activation"].update(
        initial_state="active", activation_delay_seconds=0
    )
    scene["entities"][1]["modifiers"]["hitpoints_multiplier"] = 0.0001
    scene["entities"][1]["first_attack_seconds"] = 100
    inputs[2]["troops"][0]["count"] = 1
    inputs[2]["spells"] = [{"id": entity, "level": level, "count": 1}]
    inputs[1]["levels"][entity] = level
    kind = SPELL_CLASSES[entity]
    inputs[0]["termination_policy"] = termination_policy(
        [
            classification(
                {"origin": "army", "entity": entity, "level": level},
                kind,
                "ignore" if kind == "support_only" else "while_unspent",
            )
        ]
    )
    return inputs


def jump_battle(catalog, step, selected=True, duration=4):
    inputs = spell_battle(catalog, "jump-spell", step=step, duration=duration)
    scene = inputs[0]["entity_scene"]
    scene["entities"][0]["town_hall_parameters"]["activation"][
        "activation_delay_seconds"
    ] = 100
    troop = scene["entities"][1]
    troop.update(x=6.5, y=5.5, first_attack_seconds=0)
    troop["modifiers"]["hitpoints_multiplier"] = 1
    scene["attack_spells"][0].update(x=8.5, y=5.5)
    inputs[3]["inventory"]["wall"] = 16
    for y in range(16):
        key = f"wall-{y}"
        scene["entities"].append(
            entity_instance(
                key,
                "wall",
                1,
                "defense",
                x=8,
                y=y,
                mode="passive",
                statistics_mode="none",
                attack_parameters={},
                inactive_attack_interval_seconds=1,
                counts_for_destruction=False,
            )
        )
        inputs[3]["buildings"].append(
            {
                "instance": key,
                "id": "wall",
                "level": 1,
                "x": 8,
                "y": y,
                "mode": "passive",
                "counts_for_destruction": False,
            }
        )
    if not selected:
        scene["attack_spells"] = []
        scene.pop("advanced_spell_binding")
        inputs[2]["spells"] = []
        inputs[0]["termination_policy"] = termination_policy()
    return inputs


class AdvancedSpellIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_paid_bat_skeleton_release_after_army_loss_and_fight_without_extra_spend(
        self,
    ):
        for entity, level in (("bat-spell", 1), ("skeleton-spell", 5)):
            for step in (0.017, 0.25):
                with self.subTest(entity=entity, step=step):
                    inputs = spell_battle(
                        self.catalog, entity, level=level, time=1e-12, step=step
                    )
                    inputs[0]["entity_scene"]["attack_spells"][0]["parameters"][
                        "impact_delay_seconds"
                    ] = 0.1
                    result = simulate_full_battle(*inputs, self.catalog)
                    combat = result["combat"]
                    model = result["compiled"]["scene"]["attack_spell_models"][0]
                    reserves = result["resource_use"]["generated_spell_units"]
                    self.assertEqual(len(reserves), model["quantities"]["count"])
                    self.assertTrue(
                        all(r["released_at"] is not None for r in reserves.values())
                    )
                    self.assertEqual(
                        result["resource_use"]["deployed_attacker_ids"], ["pekka-0"]
                    )
                    self.assertEqual(
                        sum(
                            slot["spent"]
                            for slot in result["resource_use"]["spell_slots"]
                        ),
                        1,
                    )
                    self.assertEqual(combat["actors"]["pekka-0"]["death_time"], 0)
                    self.assertTrue(
                        any(
                            e.get("event") == "projectile_launch"
                            and e.get("source") in reserves
                            for e in combat["trace"]
                        )
                    )
                    self.assertLess(
                        combat["actors"]["hall"]["hp"],
                        combat["actors"]["hall"]["maximum_hp"],
                    )
                    casts = [
                        e
                        for e in combat["trace"]
                        if e.get("event") == "attack_spell_cast"
                    ]
                    self.assertEqual(casts[0]["time_seconds"], 1e-12)

    def test_unowned_reserve_missing_policy_and_unbound_families_reject(self):
        inputs = spell_battle(self.catalog, "bat-spell")
        missing = deepcopy(inputs)
        missing[0]["entity_scene"].pop("advanced_spell_binding")
        with self.assertRaisesRegex(InputError, "advanced_spell_binding"):
            compile_full_battle(*missing, self.catalog)
        raw = compile_full_battle(*inputs, self.catalog)["compiled"]["scene"]
        forged = deepcopy(raw)
        forged["effects"] = [
            {
                "id": "steal-reserve",
                "kind": "deploy",
                "time_seconds": 0,
                "targets": ["spell:spawn:0"],
                "positions": {"spell:spawn:0": {"x": 2.5, "y": 2.5}},
            }
        ]
        with self.assertRaisesRegex(InputError, "cannot be player deployments"):
            simulate_spatial(forged)
        for entity in ("clone-spell", "revive-spell", "angry-spell"):
            with (
                self.subTest(entity=entity),
                self.assertRaisesRegex(InputError, "advanced_spell_binding"),
            ):
                missing = spell_battle(self.catalog, entity)
                missing[0]["entity_scene"].pop("advanced_spell_binding")
                compile_full_battle(*missing, self.catalog)

    def test_paid_jump_crosses_live_wall_without_crossing_buildings(self):
        for step in (0.017, 0.25):
            for selected in (True, False):
                inputs = jump_battle(self.catalog, step, selected)
                result = simulate_full_battle(*inputs, self.catalog)
                actor = result["combat"]["actors"]["pekka-0"]
                self.assertEqual(actor["x"] > 9, selected)
                self.assertEqual(
                    result["combat"]["actors"]["hall"]["hp"] < 10000, selected
                )
                self.assertTrue(
                    all(
                        result["combat"]["actors"][f"wall-{y}"]["hp"] > 0
                        for y in range(16)
                    )
                )
                for frame in result["combat"]["frames"]:
                    point = frame["actors"]["pekka-0"]
                    self.assertFalse(10 <= point["x"] < 14 and 4 <= point["y"] < 8)

    def test_skeleton_armor_breaking_packet_discards_overflow_and_immunity_preserves_armor(
        self,
    ):
        for step in (0.017, 0.25):
            inputs = spell_battle(self.catalog, "skeleton-spell", level=5, step=step)
            result = simulate_full_battle(*inputs, self.catalog)
            hits = [
                e
                for e in result["combat"]["trace"]
                if e.get("event") == "damage_received"
                and e["target_id"] == "spell:spawn:0"
            ]
            self.assertGreater(hits[0]["requested_damage"], hits[0]["armor_before"])
            self.assertEqual(
                (
                    hits[0]["armor_after"],
                    hits[0]["final_damage"],
                    hits[0]["actual_health_loss"],
                ),
                (0, 0, 0),
            )
            self.assertEqual(hits[1]["actual_health_loss"], 30)
            # A declared kernel disturbance isolates protection ordering; this
            # is not claimed as a player command or an additional paid battle.
            raw = deepcopy(result["compiled"]["scene"])
            hall = next(a for a in raw["actors"] if a["id"] == "hall")
            hall["town_hall_model"]["activation"]["activation_delay_seconds"] = 0.1
            raw["effects"] = [
                {
                    "id": "protection-control",
                    "kind": "invulnerability",
                    "time_seconds": 0.001,
                    "duration_seconds": 0.3,
                    "targets": ["spell:spawn:0"],
                }
            ]
            protected = simulate_spatial(raw)
            hits = [
                e
                for e in protected["trace"]
                if e.get("event") == "damage_received"
                and e["target_id"] == "spell:spawn:0"
            ]
            self.assertTrue(hits[0]["protected"])
            self.assertEqual(
                (hits[0]["armor_before"], hits[0]["armor_after"]), (30, 30)
            )
            self.assertTrue(
                any(not e["protected"] and e.get("armor_after") == 0 for e in hits)
            )

    def test_paid_bat_uses_explicit_hall_and_pinned_resource_damage_factors(self):
        for target_kind in ("hall", "resource"):
            inputs = spell_battle(self.catalog, "bat-spell")
            scene = inputs[0]["entity_scene"]
            scene["entities"][0]["town_hall_parameters"]["activation"].update(
                initial_state="dormant", activation_delay_seconds=100
            )
            if target_kind == "resource":
                scene["attack_spells"][0].update(x=3.5, y=5.5)
                scene["entities"].append(
                    entity_instance(
                        "gold",
                        "gold-storage",
                        1,
                        "defense",
                        x=4,
                        y=4,
                        mode="passive",
                        statistics_mode="none",
                        attack_parameters={},
                        inactive_attack_interval_seconds=1,
                    )
                )
                inputs[3]["inventory"]["gold-storage"] = 1
                inputs[3]["buildings"].append(
                    {
                        "instance": "gold",
                        "id": "gold-storage",
                        "level": 1,
                        "x": 4,
                        "y": 4,
                        "mode": "passive",
                        "counts_for_destruction": True,
                    }
                )
            result = simulate_full_battle(*inputs, self.catalog)
            target = "hall" if target_kind == "hall" else "gold"
            hits = [
                e
                for e in result["combat"]["trace"]
                if e.get("event") == "projectile_impact"
                and e.get("source", "").startswith("spell:spawn:")
                and e["target"] == target
            ]
            self.assertTrue(hits)
            self.assertTrue(
                all(
                    abs(e["damage"] - 60 * (0.123 if target == "hall" else 0.4)) < 1e-10
                    for e in hits
                )
            )

    def test_paid_spell_units_do_not_trigger_bombs_or_castle_but_ordinary_troop_does(
        self,
    ):
        for entity, trap_id in (("skeleton-spell", "bomb"), ("bat-spell", "air-bomb")):
            for ordinary in (False, True):
                inputs = spell_battle(self.catalog, entity, duration=0.4)
                scene = inputs[0]["entity_scene"]
                troop = scene["entities"][1]
                troop.update(x=9.5 if ordinary else 0.5, y=5.5 if ordinary else 0.5)
                troop["modifiers"]["hitpoints_multiplier"] = 1
                if entity == "bat-spell" and ordinary:
                    troop.update(entity="minion")
                    troop["modifiers"]["hitpoints_multiplier"] = 100
                    troop.pop("wall_parameters")
                    inputs[2]["troops"] = [{"id": "minion", "level": 1, "count": 1}]
                    inputs[1]["levels"]["minion"] = 1
                scene["entities"][0]["town_hall_parameters"]["activation"][
                    "activation_delay_seconds"
                ] = 100
                member = member_instance(x=14.5, y=11.5)
                castle = castle_instance([member], x=15, y=10)
                scene["entities"].extend([castle, member])
                count = cast(self.catalog, entity)["quantities"]["count"]
                scene["defending_unit_responses"] = {
                    "source": SOURCE,
                    "actors": {
                        key: {"primary": "ignore", "collateral": "ignore"}
                        for key in [
                            "pekka-0",
                            *[f"spell:spawn:{i}" for i in range(count)],
                        ]
                    },
                }
                scene["traps"] = [trap_instance(trap_id, x=9, y=5)]
                inputs[3]["inventory"].update({"clan-castle": 1, trap_id: 1})
                inputs[3]["buildings"].extend(
                    [
                        {
                            "instance": "castle",
                            "id": "clan-castle",
                            "level": 12,
                            "x": 15,
                            "y": 10,
                            "mode": "garrison",
                            "counts_for_destruction": True,
                            "settings": {
                                "garrison": [
                                    {
                                        "entity": "archer",
                                        "level": 1,
                                        "count": 1,
                                        "donor_town_hall": 16,
                                    }
                                ]
                            },
                        },
                        {
                            "instance": "trap",
                            "id": trap_id,
                            "level": 1,
                            "x": 9,
                            "y": 5,
                            "counts_for_destruction": False,
                        },
                    ]
                )
                result = simulate_full_battle(*inputs, self.catalog)
                self.assertEqual(
                    result["combat"]["actors"]["member"]["spawn_seconds"]
                    != "controlled",
                    ordinary,
                )
                triggers = [
                    e
                    for e in result["combat"]["trace"]
                    if e.get("event") == "trap_trigger"
                ]
                self.assertEqual(bool(triggers), ordinary)

    def test_paid_jump_expiry_inside_wall_finishes_exit_and_removes_exemption(self):
        positions = []
        for step in (0.017, 0.25):
            inputs = jump_battle(self.catalog, step, duration=35)
            scene = inputs[0]["entity_scene"]
            scene["entities"][1]["modifiers"]["movement_speed_multiplier"] = 0.05
            scene["recording_interval_seconds"] = 0.5
            result = simulate_full_battle(*inputs, self.catalog)
            model = result["compiled"]["scene"]["attack_spell_models"][0]
            self.assertEqual(
                model["quantities"], {"duration_seconds": 20, "exit_linger_seconds": 1}
            )
            frame = next(
                f for f in result["combat"]["frames"] if f["time_seconds"] == 21
            )
            self.assertTrue(8 < frame["actors"]["pekka-0"]["x"] < 9)
            actor = result["combat"]["actors"]["pekka-0"]
            self.assertGreater(actor["x"], 9)
            state = result["combat"]["attack_spells"]["advanced_spells"]
            self.assertEqual(state["jump_wall_exemptions"], {})
            self.assertEqual(state["pending_wall_exit_ids"], [])
            self.assertEqual(
                sum(slot["spent"] for slot in result["resource_use"]["spell_slots"]), 1
            )
            positions.append(actor["x"])
        self.assertAlmostEqual(*positions)

    def test_spell_reserve_effect_forgery_and_blocked_ground_spawn_reject(self):
        inputs = spell_battle(self.catalog, "skeleton-spell", level=5)
        raw = compile_full_battle(*inputs, self.catalog)["compiled"]["scene"]
        reserve = next(a for a in raw["actors"] if a["id"] == "spell:spawn:0")
        reserve["spell_unit_effects"]["armor_hp"] = 9000
        with self.assertRaisesRegex(InputError, "effects differ"):
            simulate_spatial(raw)
        inputs[0]["entity_scene"]["attack_spells"][0].update(x=11.5, y=5.5)
        with self.assertRaisesRegex(InputError, "clear declared ground spawn"):
            simulate_full_battle(*inputs, self.catalog)


if __name__ == "__main__":
    unittest.main()
