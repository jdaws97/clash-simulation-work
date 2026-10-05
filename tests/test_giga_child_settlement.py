"""Bounded paid reproductions of the independent Giga/Barracks audit findings."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.attack_spell_rules import RULES, SCOPE
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.full_battle import compile_full_battle, simulate_full_battle
from clashlab.giga_responses import SELECTION, STATUS
from test_artillery import artillery_hall
from test_battle_termination import termination_policy
from test_giga_bombs import giga_instance, response
from test_siege_machines import release_command

SOURCE = "synthetic-giga-barracks-audit-correction-not-game-calibration"


def child_battle(catalog, step=0.25, delay=0.2, positive=True):
    from test_siege_domain_integration import SiegeDomainIntegrationTests

    fixture = SiegeDomainIntegrationTests()
    fixture.catalog = catalog
    inputs = fixture.inputs("siege-barracks")
    spec, _, _, layout = inputs
    scene = spec["entity_scene"]
    scene.update(
        scope=SCOPE,
        model_rules=deepcopy(RULES),
        pets=[],
        attack_spells=[],
        effects=[release_command(0.7)],
        maximum_step_seconds=step,
    )
    spec["termination_policy"] = termination_policy()
    scene["entities"][0] = artillery_hall(x=10, y=4, first_attack_seconds=100)
    layout["town_hall"] = 17
    layout["buildings"][0].update(level=17, mode="infernoArtillery")
    # Enumerate actual finite generated identities before adding the response
    # table; never derive child policy from its ordinary catalog identity.
    base = compile_full_battle(*inputs, catalog)["compiled"]["scene"]
    children = {a["id"]: a for a in base["actors"] if "barracks_member_model" in a}
    trap = giga_instance({}, town_hall=17, x=7, y=7)
    trap["parameters"].update(delay_seconds=delay, push_distance_tiles=0)
    scene["traps"].append(trap)
    layout["inventory"]["giga-bomb"] = 1
    layout["buildings"].append(
        {
            "instance": "giga",
            "id": "giga-bomb",
            "level": 3,
            "x": 7,
            "y": 7,
            "mode": "armed",
            "counts_for_destruction": False,
        }
    )
    scene["giga_bomb_response_binding"] = {
        "source": SOURCE,
        "status": STATUS,
        "selection": SELECTION,
        "actor_responses": {
            key: (
                response(25 if actor["entity_adapter"]["entity"] == "pekka" else 4)
                if positive
                else response(0, 0, 0)
            )
            for key, actor in children.items()
        },
        "entity_responses": {
            "archer": response("catalog_housing_space"),
            "siege-barracks": response(0),
            "pekka": response("catalog_housing_space"),
            "wizard": response("catalog_housing_space"),
        },
    }
    return inputs


class GigaChildSettlementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(Path(__file__).resolve().parents[1] / "data")

    def test_paid_child_release_triggers_and_settles_delayed_or_zero_blast_at_same_time(
        self,
    ):
        for delay in (0, 0.2):
            for step in (0.017, 0.25):
                inputs = child_battle(self.catalog, step, delay)
                original = deepcopy(inputs)
                result = simulate_full_battle(*inputs, self.catalog)
                self.assertEqual(inputs, original)
                combat = result["combat"]
                trigger = combat["giga_bombs"]["triggered"]["giga"]
                self.assertEqual(trigger["trigger_seconds"], 0)
                self.assertEqual(trigger["arrival_seconds"], delay)
                self.assertEqual(
                    trigger["trigger_weights"],
                    {"generated-pekka-0": 25, "generated-wizard-0": 4},
                )
                impacts = [
                    e for e in combat["trace"] if e.get("event") == "giga_bomb_impact"
                ]
                self.assertEqual(len(impacts), 1)
                self.assertEqual(impacts[0]["time_seconds"], delay)
                self.assertEqual(
                    combat["actors"]["generated-wizard-0"]["death_time"], delay
                )
                self.assertEqual(
                    impacts[0]["requested_damage"]["generated-wizard-0"], 1300
                )
                self.assertEqual(
                    result["resource_use"]["deployed_attacker_ids"],
                    ["payload", "siege"],
                )
                children = result["resource_use"]["generated_siege_units"]
                self.assertEqual(len(children), 7)
                self.assertEqual(children["generated-wizard-0"]["released_at"], 0)
                self.assertTrue(
                    all(
                        result["compiled"]["scene"]["giga_bomb_response_audit"][
                            "actor_selections"
                        ][key]
                        == {"actor": key}
                        for key in children
                    )
                )
                self.assertEqual(result["outcome"]["end_reason"], "declared_time_limit")

    def test_exact_zero_child_control_remains_quiet_and_catalog_fallback_rejects(self):
        for step in (0.017, 0.25):
            inputs = child_battle(self.catalog, step, positive=False)
            result = simulate_full_battle(*inputs, self.catalog)
            self.assertEqual(result["combat"]["giga_bombs"]["triggered"], {})
            self.assertIsNone(
                result["combat"]["actors"]["generated-wizard-0"]["death_time"]
            )
            for missing in ("all", "generated-wizard-5"):
                broken = deepcopy(inputs)
                binding = broken[0]["entity_scene"]["giga_bomb_response_binding"]
                if missing == "all":
                    binding["actor_responses"] = {}
                else:
                    binding["actor_responses"].pop(missing)
                with self.assertRaisesRegex(
                    InputError, "Missing explicit Giga response"
                ):
                    compile_full_battle(*broken, self.catalog)


if __name__ == "__main__":
    unittest.main()
