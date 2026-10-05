"""One battle-wide profile from the full-battle and command-line entry points."""

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

from clashlab import cli
from clashlab.battle_modifiers import apply_battle_modifiers
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json
from clashlab.full_battle import (
    compile_full_battle,
    simulate_full_battle,
    validate_battle_bindings,
)
from clashlab.indirect_rules import RULES as INDIRECT_RULES, SCOPE as INDIRECT_SCOPE

from test_battle_modifiers import modifier_policy
from test_full_battle import add_hero, fixture
from test_heroes import ability


ROOT = Path(__file__).resolve().parents[1]


class BattleModifierIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.rules = read_json(ROOT / "data" / "mode-rules.json")

    def policy_fixture(self, duration=0.2):
        inputs = fixture(self.catalog, time_limit=duration)
        inputs[0]["battle_modifier_policy"] = modifier_policy()
        return inputs

    def test_compile_applies_profile_once_and_exposes_the_same_audit(self):
        inputs = self.policy_fixture()
        specification, account, army, _ = inputs
        add_hero(specification, army, account)
        untouched = deepcopy(inputs)
        baseline_inputs = deepcopy(inputs)
        del baseline_inputs[0]["battle_modifier_policy"]
        baseline = compile_full_battle(*baseline_inputs, self.catalog)
        with patch(
            "clashlab.full_battle.apply_battle_modifiers",
            wraps=apply_battle_modifiers,
        ) as apply:
            result = compile_full_battle(*inputs, self.catalog, mode_rules=self.rules)
        apply.assert_called_once()
        self.assertEqual(inputs, untouched)
        audit = result["battle_modifier_audit"]
        self.assertEqual(audit, result["compiled"]["battle_modifier_audit"])
        self.assertEqual(audit["selection"], "role_aware_battle_profile")
        self.assertEqual(audit["profile_id"], "legend_i")
        original = {
            item["id"]: item for item in baseline["compiled"]["scene"]["actors"]
        }
        changed = {item["id"]: item for item in result["compiled"]["scene"]["actors"]}
        self.assertEqual(changed["pekka-0"], original["pekka-0"])
        self.assertAlmostEqual(
            changed["hall"]["damage"], original["hall"]["damage"] * 1.2
        )
        self.assertAlmostEqual(
            changed["royal"]["damage"], original["royal"]["damage"] * 0.8
        )
        self.assertAlmostEqual(
            changed["royal"]["hitpoints"], original["royal"]["hitpoints"] * 0.8
        )
        self.assertFalse(result["full_game_prediction"])
        self.assertEqual(len(audit["application"]["actors"]), len(changed))

    def test_simulation_retains_profile_audit_and_live_hero_scaling(self):
        inputs = self.policy_fixture()
        specification, account, army, _ = inputs
        royal = add_hero(specification, army, account)
        specification["entity_scene"]["effects"] = [ability(royal["id"])]
        result = simulate_full_battle(*inputs, self.catalog, mode_rules=self.rules)
        self.assertEqual(result["battle_modifier_audit"]["profile_id"], "legend_i")
        for role in result["battle_modifier_audit"]["application"][
            "resolved_roles"
        ].values():
            self.assertTrue(role["source"].endswith("the-sound-of-clash-update/"))
            self.assertEqual(role["checked_on"], "2026-10-04")
            self.assertEqual(role["source_published_on"], "2026-04-27")
            self.assertEqual(
                role["verification"], "published_profile_not_client_session_observation"
            )
        self.assertEqual(result["resource_use"]["used_hero_ability_ids"], ["royal"])
        compiled = next(
            actor
            for actor in result["compiled"]["scene"]["actors"]
            if actor["id"] == "royal"
        )
        self.assertEqual(
            result["combat"]["actors"]["royal"]["maximum_hp"], compiled["hitpoints"]
        )
        self.assertEqual(compiled["hero_model"]["damage_multiplier"], 0.8)
        self.assertEqual(result["outcome"]["time_limit_seconds"], 0.2)

    def test_completion_resimulation_does_not_apply_profile_again(self):
        inputs = self.policy_fixture(duration=5)
        with patch(
            "clashlab.full_battle.apply_battle_modifiers",
            wraps=apply_battle_modifiers,
        ) as apply:
            result = simulate_full_battle(*inputs, self.catalog, mode_rules=self.rules)
        apply.assert_called_once()
        self.assertEqual(result["outcome"]["stars"], 3)
        self.assertLess(result["outcome"]["elapsed_seconds"], 5)
        hall = result["compiled"]["scene"]["actors"][0]
        hall_changes = result["battle_modifier_audit"]["application"]["actors"][0][
            "statistics"
        ]
        damage = next(change for change in hall_changes if change["path"] == ["damage"])
        self.assertEqual(hall["damage"], damage["before"] * 1.2)

    def test_legacy_specs_keep_independent_actor_modifiers_without_rules(self):
        inputs = fixture(self.catalog, time_limit=0.2)
        inputs[0]["entity_scene"]["entities"][1]["modifiers"]["damage_multiplier"] = 2
        result = compile_full_battle(*inputs, self.catalog)
        audit = result["battle_modifier_audit"]
        self.assertEqual(audit["selection"], "independent_entity_modifiers")
        self.assertIsNone(audit["profile_id"])
        self.assertIsNone(audit["application"])
        self.assertEqual(audit["actor_modifiers"]["pekka-0"]["damage_multiplier"], 2)
        self.assertEqual(result["compiled"]["battle_modifier_audit"], audit)
        simulation = simulate_full_battle(*inputs, self.catalog)
        self.assertEqual(simulation["battle_modifier_audit"], audit)

    def test_rules_are_required_only_for_an_explicit_profile(self):
        inputs = self.policy_fixture()
        for operation in (compile_full_battle, simulate_full_battle):
            with (
                self.subTest(operation=operation.__name__),
                self.assertRaisesRegex(InputError, "requires explicit mode_rules"),
            ):
                operation(*inputs, self.catalog)
        del inputs[0]["battle_modifier_policy"]
        result = compile_full_battle(*inputs, self.catalog, mode_rules={})
        self.assertEqual(
            result["battle_modifier_audit"]["selection"], "independent_entity_modifiers"
        )

    def test_policy_cannot_mix_non_neutral_inputs_or_reduce_unrepresented_gear(self):
        inputs = self.policy_fixture()
        inputs[0]["entity_scene"]["entities"][0]["modifiers"]["damage_multiplier"] = 1.2
        with self.assertRaisesRegex(InputError, "neutral actor"):
            compile_full_battle(*inputs, self.catalog, mode_rules=self.rules)
        inputs = self.policy_fixture()
        specification, account, army, _ = inputs
        add_hero(specification, army, account)
        specification["battle_modifier_policy"] = modifier_policy("esport")
        with self.assertRaisesRegex(InputError, "owned and effective equipment"):
            compile_full_battle(*inputs, self.catalog, mode_rules=self.rules)

    def test_binding_validation_permits_only_the_named_optional_policy(self):
        inputs = self.policy_fixture()
        result = validate_battle_bindings(*inputs, self.catalog)
        self.assertTrue(result["complete_declared_coverage"])
        inputs[0]["profile_id"] = "legend_i"
        with self.assertRaisesRegex(InputError, "optionally one battle modifier"):
            validate_battle_bindings(*inputs, self.catalog)

    def test_indirect_scope_is_accepted_with_global_profile(self):
        inputs = self.policy_fixture()
        scene = inputs[0]["entity_scene"]
        scene.update(
            scope=INDIRECT_SCOPE, model_rules=deepcopy(INDIRECT_RULES), buff_spells=[]
        )
        result = simulate_full_battle(*inputs, self.catalog, mode_rules=self.rules)
        self.assertTrue(result["validation"]["complete_declared_coverage"])
        self.assertEqual(result["battle_modifier_audit"]["profile_id"], "legend_i")

    def run_cli(self, command, inputs, override=None, rules=None):
        paths = {
            "specification": Path("battle-specification.json"),
            "account": Path("battle-account.json"),
            "army": Path("battle-army.json"),
            "layout": Path("battle-layout.json"),
        }
        files = {paths[name]: item for name, item in zip(paths, inputs)}
        data = ROOT / "data"
        if "battle_modifier_policy" in inputs[0]:
            files[override or data / "mode-rules.json"] = (
                self.rules if rules is None else rules
            )
        argv = [
            "clashlab",
            "--data",
            str(data),
            "--output",
            "battle-result.json",
            command,
            *(str(value) for value in paths.values()),
        ]
        if override:
            argv.extend(["--mode-rules", str(override)])
        with (
            patch("sys.argv", argv),
            patch.object(cli.Catalog, "load", return_value=self.catalog),
            patch.object(
                cli, "read_json", side_effect=lambda path: deepcopy(files[path])
            ) as reads,
            patch.object(cli, "write_json") as write,
            redirect_stdout(StringIO()),
        ):
            cli.main()
        write.assert_called_once()
        return write.call_args.args[1], [call.args[0] for call in reads.call_args_list]

    def test_cli_loads_rules_for_compile_and_simulation_profiles(self):
        for command in ("compile-full-battle", "full-battle"):
            with self.subTest(command=command):
                result, reads = self.run_cli(command, self.policy_fixture())
                self.assertIn(ROOT / "data" / "mode-rules.json", reads)
                self.assertEqual(
                    result["battle_modifier_audit"]["profile_id"], "legend_i"
                )
                self.assertEqual("outcome" in result, command == "full-battle")

    def test_cli_uses_explicit_rules_override_and_skips_rules_for_legacy_specs(self):
        rules = deepcopy(self.rules)
        rules["battle_modifier_profiles"]["legend_i"]["roles"]["defense"][
            "damage_multiplier"
        ] = 1.3
        override = Path("alternative-mode-rules.json")
        result, reads = self.run_cli(
            "compile-full-battle", self.policy_fixture(), override, rules
        )
        self.assertIn(override, reads)
        self.assertNotIn(ROOT / "data" / "mode-rules.json", reads)
        resolved = result["battle_modifier_audit"]["application"]["resolved_roles"]
        self.assertEqual(resolved["defense"]["modifiers"]["damage_multiplier"], 1.3)
        legacy = fixture(self.catalog, time_limit=0.2)
        result, reads = self.run_cli("compile-full-battle", legacy, override)
        self.assertNotIn(override, reads)
        self.assertNotIn(ROOT / "data" / "mode-rules.json", reads)
        self.assertEqual(
            result["battle_modifier_audit"]["selection"], "independent_entity_modifiers"
        )


if __name__ == "__main__":
    unittest.main()
