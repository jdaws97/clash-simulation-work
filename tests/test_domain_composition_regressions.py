"""Synthetic Recall and Jelly composition contracts, not game calibration."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.attacking_extensions import SCOPE as EXTENSION_SCOPE
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.electro_titans import ElectroTitanCombat
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.jelly_lifecycle import JellyLifecycle, POLICIES, PRIORITY_FIELDS
from clashlab.pet_rules import RULES as PET_RULES, SCOPE as PET_SCOPE
from clashlab.spatial import _load_actors, _select_target

from test_adapters import entity_instance
from test_attack_spell_integration import attack_spell_battle
from test_electro_titans import aura_parameters, loaded, titan
from test_equipment_pet_lifecycles import SOURCE
from test_full_battle import fixture, add_hero
from test_hero_pets import pet_parameters
from test_recipe_spells import recipe_cast
from test_spatial import synthetic_structure, synthetic_unit


ROOT = Path(__file__).resolve().parents[1]


def titan_case(catalog, step, capture=None, return_time=1):
    casts = []
    if capture is not None:
        cast = recipe_cast("recall-spell", x=9.5, y=5.5, time_seconds=capture)
        cast["parameters"]["redeployment"] = {
            "time_seconds": return_time,
            "position": {"x": 2.5, "y": 2.5},
            "regions": [{"left": 0, "right": 4, "top": 0, "bottom": 4}],
            "source": SOURCE,
        }
        casts.append(cast)
    inputs = attack_spell_battle(catalog, casts)
    scene = inputs[0]["entity_scene"]
    actor = entity_instance(
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
    actor["modifiers"]["hitpoints_multiplier"] = 10
    scene.update(
        entities=[scene["entities"][0], actor],
        duration_seconds=1.21,
        maximum_step_seconds=step,
        recording_interval_seconds=0.25,
    )
    inputs[0]["time_limit_seconds"] = 1.21
    inputs[1]["levels"]["electro-titan"] = 4
    inputs[2]["troops"] = [{"id": "electro-titan", "level": 4, "count": 1}]
    return inputs


def jelly_case(catalog, primary, step):
    inputs = fixture(catalog, time_limit=0.5)
    scene = inputs[0]["entity_scene"]
    scene["entities"] = scene["entities"][:2]
    inputs[2]["troops"][0]["count"] = 1
    owner = add_hero(inputs[0], inputs[2], inputs[1])
    owner["hero_parameters"]["pet_policy"] = "paired_pet_from_explicit_scene_assignment"
    parameters = pet_parameters("lassi")
    parameters.update(
        target_retention="prefer_owner_primary_then_nearest",
        owner_death_policy="separate_then_independent_no_reattachment",
        ground_wall_policy="not_applicable_air",
        behavior=deepcopy(POLICIES),
    )
    scene.update(
        scope=PET_SCOPE,
        model_rules=deepcopy(PET_RULES),
        buff_spells=[],
        maximum_step_seconds=step,
        pets=[
            {
                "id": "paired",
                "entity": "angry-jelly",
                "level": 10,
                "town_hall": 16,
                "hero_id": owner["id"],
                "parameters": parameters,
            }
        ],
        defending_unit_responses={
            "source": SOURCE,
            "actors": {
                "pekka-0": {"primary": "ignore", "collateral": "ignore"},
                owner["id"]: {"primary": primary, "collateral": "allow"},
                "paired": {"primary": "ignore", "collateral": "ignore"},
            },
        },
    )
    inputs[1]["levels"]["angry-jelly"] = 10
    inputs[2]["heroes"][0]["pet"] = {"id": "angry-jelly", "level": 10}
    return inputs, owner["id"]


class DomainCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_paid_titan_recall_preserves_epoch_without_withdrawn_damage(self):
        for step in (0.25, 0.017):
            for capture, return_time, expected in (
                (None, 1, [0, 0.4, 0.8, 1.2]),
                (0.2, 1, [0, 1.2]),
                (0.2, 0.8, [0, 0.8, 1.2]),
                (0, 1, [1.2]),
            ):
                with self.subTest(step=step, capture=capture, return_time=return_time):
                    result = simulate_full_battle(
                        *titan_case(self.catalog, step, capture, return_time),
                        self.catalog,
                    )
                    trace = result["combat"]["trace"]
                    pulses = [
                        e for e in trace if e["event"] == "electro_titan_aura_pulse"
                    ]
                    self.assertEqual(
                        [round(e["time_seconds"], 9) for e in pulses], expected
                    )
                    self.assertEqual(
                        result["resource_use"]["deployed_attacker_ids"], ["titan"]
                    )
                    if capture is not None:
                        captures = [e for e in trace if e["event"] == "recall_capture"]
                        returns = [
                            e for e in trace if e["event"] == "recall_redeployment"
                        ]
                        self.assertEqual(len(captures), 1)
                        self.assertEqual(captures[0]["actors"], ["titan"])
                        self.assertEqual(captures[0]["capacity_used"], 32)
                        self.assertEqual(len(returns), 1)
                        self.assertEqual(returns[0]["additional_army_spend"], 0)
                        self.assertTrue(
                            all(
                                not e["targets"]
                                for e in pulses
                                if e["time_seconds"] >= return_time
                            )
                        )

        # The return does not bypass Freeze policy or conceal a later skipped
        # active pulse. Delayed first pulses retain their original epoch too.
        actor = titan(self.catalog)
        actor["aura_model"]["parameters"].update(
            first_pulse_delay_seconds=0.4, freeze_policy="skip_frozen_pulses"
        )
        actors = loaded([actor, synthetic_structure(x=6, y=4)])
        runtime = ElectroTitanCombat(actors)
        runtime.prepare(0)
        actors["titan"]["_recalled"] = True
        self.assertEqual(dict(runtime.resolve(0.2, [])), {})
        actors["titan"].update(_recalled=False, frozen_until=1.3)
        self.assertEqual(dict(runtime.resolve(1, [])), {})
        self.assertAlmostEqual(runtime.next_boundary(1), 1.2)
        frozen_pulse = runtime.next_boundary(1)
        self.assertEqual(dict(runtime.resolve(frozen_pulse, [])), {})
        self.assertEqual(
            runtime.resolve(runtime.next_boundary(frozen_pulse), [])["tower"], 55
        )
        with self.assertRaisesRegex(InputError, "boundary was skipped"):
            runtime.resolve(2.1, [])

    def test_jelly_composes_and_restores_explicit_defending_unit_policy(self):
        for primary in ("ignore", "same_tier_as_buildings", "after_buildings"):
            for step in (0.25, 0.017):
                inputs, owner_id = jelly_case(self.catalog, primary, step)
                result = simulate_full_battle(*inputs, self.catalog)
                self.assertEqual(
                    sum(
                        e["event"] == "jelly_attached"
                        for e in result["combat"]["trace"]
                    ),
                    1,
                )
            scene = compile_full_battle(*inputs, self.catalog)["compiled"]["scene"]
            actors = _load_actors(scene, 20, 20)
            owner = actors[owner_id]
            original = {field: deepcopy(owner[field]) for field in PRIORITY_FIELDS}
            response = deepcopy(owner["defending_unit_response"])
            collateral = owner["attack_model"]["defending_unit_collateral_policy"]
            runtime = JellyLifecycle(actors)
            states = {"paired": {"phase": "waiting"}}
            trace = []
            runtime.attach("paired", actors, states, 0, trace)
            expected = [["defense"], ["building"]]
            if primary == "same_tier_as_buildings":
                expected[1].append("unit")
            elif primary == "after_buildings":
                expected.append(["unit"])
            self.assertEqual(owner["target_priority_tiers"], expected)
            # Exercise real shared acquisition: defenses first, then a nearby
            # defending unit only when it shares the building tier.
            targets = loaded(
                [
                    synthetic_structure("defense", x=10, y=10),
                    synthetic_structure("building", kind="building", x=7, y=4),
                    synthetic_unit("guard", team="defense", x=5, y=4.5),
                ]
            )
            owner.update(x=4.5, y=4.5, movement="air", target=None)
            choices = {owner_id: owner, **targets}
            self.assertEqual(
                _select_target(owner, choices, 0, set(), 20, 20)[0]["id"], "defense"
            )
            targets["defense"]["hp"] = 0
            owner["target"] = None
            expected_target = (
                "guard" if primary == "same_tier_as_buildings" else "building"
            )
            self.assertEqual(
                _select_target(owner, choices, 0, set(), 20, 20)[0]["id"],
                expected_target,
            )
            expiry = runtime.models["paired"]["duration_seconds"]
            runtime.prepare(actors, states, expiry, trace)
            self.assertEqual(
                {field: owner[field] for field in PRIORITY_FIELDS}, original
            )
            self.assertEqual(owner["defending_unit_response"], response)
            self.assertEqual(
                owner["attack_model"]["defending_unit_collateral_policy"], collateral
            )
            self.assertIsNone(owner["target"])
            self.assertEqual(states["paired"]["phase"], "active")


if __name__ == "__main__":
    unittest.main()
