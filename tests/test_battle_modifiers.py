"""Battle-wide role scaling, secondary policies and runtime cache agreement."""

from copy import deepcopy
from pathlib import Path
import unittest

from clashlab.adapters import compile_entity_scene
from clashlab.artillery import ArtilleryCombat
from clashlab.battle_modifiers import MARKER, apply_battle_modifiers
from clashlab.catalog import Catalog
from clashlab.combat import PatternCombat
from clashlab.common import InputError, read_json
from clashlab.heroes import HeroCombat
from clashlab.ramping import RampCombat
from clashlab.spatial import _load_actors, simulate_spatial
from clashlab.traps import compile_trap
from clashlab.sweeper_rules import RULES as SWEEPER_RULES, SCOPE as SWEEPER_SCOPE

from test_adapters import entity_instance, sector
from test_artillery import artillery_hall, artillery_sector
from test_defense_patterns import area_sector, bomb_instance
from test_heroes import ability, hero, hero_sector
import test_ramping
from test_spring_traps import spring_instance
from test_townhalls import hall, town_hall_sector
from test_traps import trap_instance
from test_sweepers import sweeper_instance


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "explicit-battle-modifier-fixture-not-game-calibration"


def modifier_policy(profile="legend_i", **changes):
    policy = {
        "profile_id": profile,
        "policy_source": SOURCE,
        "maximum_hp_damage_policy": "unchanged",
        "trap_damage_policy": "scale_with_defense",
        "death_damage_policy": "scale_with_source_role",
        "impact_hazard_damage_policy": "scale_with_source_role",
        "equipment_aura_damage_policy": "scale_with_source_role",
        "hero_summon_statistics_policy": "inherit_parent_role",
        "healing_and_status_policy": "unchanged",
    }
    policy.update(changes)
    return policy


class BattleModifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.rules = read_json(ROOT / "data" / "mode-rules.json")

    def compile(self, specification):
        return compile_entity_scene(specification, self.catalog)["scene"]

    def apply(self, scene, policy=None):
        return apply_battle_modifiers(
            scene,
            modifier_policy() if policy is None else policy,
            self.catalog,
            self.rules,
        )

    def cannon_scene(self):
        return self.compile(
            sector(self.catalog, [entity_instance("cannon", "cannon", 21, "defense")])
        )

    def test_role_aware_legend_i_preserves_troops_and_passive_structures(self):
        instances = [
            hero(bare=True),
            entity_instance("cannon", "cannon", 21, "defense"),
            entity_instance("troop", "barbarian", 12, "attack", x=2.5),
            entity_instance(
                "store",
                "gold-storage",
                17,
                "defense",
                x=0,
                y=0,
                mode="passive",
                statistics_mode="none",
                attack_parameters={},
                inactive_attack_interval_seconds=1,
            ),
        ]
        before = self.compile(hero_sector(self.catalog, instances))
        result = self.apply(before)
        original = {actor["id"]: actor for actor in before["actors"]}
        modified = {actor["id"]: actor for actor in result["scene"]["actors"]}
        for field in ("damage", "hitpoints"):
            self.assertAlmostEqual(
                modified["royal"][field], original["royal"][field] * 0.8
            )
        self.assertAlmostEqual(
            modified["cannon"]["damage"], original["cannon"]["damage"] * 1.2
        )
        self.assertEqual(
            modified["cannon"]["hitpoints"], original["cannon"]["hitpoints"]
        )
        self.assertEqual(modified["troop"], original["troop"])
        self.assertEqual(modified["store"], original["store"])
        self.assertFalse(result["full_game_prediction"])

    def test_catalog_category_and_team_distinguish_defending_heroes_and_guardians(self):
        # These synthetic identity probes only test role selection; the full
        # battle compiler still rejects unsupported defender/guardian mechanics.
        actor = self.compile(hero_sector(self.catalog, [hero(bare=True)]))["actors"][0]
        actor["team"] = "defense"
        defending = self.apply({"actors": [actor]}, modifier_policy("esport"))
        self.assertEqual(
            defending["application"]["actors"][0]["role"], "defending_hero"
        )
        self.assertAlmostEqual(
            defending["scene"]["actors"][0]["damage"], actor["damage"] * 1.25
        )
        self.assertAlmostEqual(
            defending["scene"]["actors"][0]["hitpoints"], actor["hitpoints"] * 1.25
        )
        guardian_id = next(
            name
            for name, record in self.catalog.records.items()
            if record["entity"]["category"] == "guardian"
        )
        actor["entity_adapter"]["entity"] = guardian_id
        actor.pop("hero_model")
        guarding = self.apply({"actors": [actor]}, modifier_policy("legend_i"))
        self.assertEqual(guarding["application"]["actors"][0]["role"], "guardian")
        self.assertAlmostEqual(
            guarding["scene"]["actors"][0]["hitpoints"], actor["hitpoints"] * 1.2
        )
        actor["team"] = "attack"
        with self.assertRaisesRegex(InputError, "defending guardian"):
            self.apply({"actors": [actor]})

    def test_non_attacking_sweeper_does_not_require_maximum_hp_weapon_term(self):
        from test_indirect_defenses import indirect_sector

        before = self.compile(
            indirect_sector(
                self.catalog,
                [sweeper_instance()],
                scope=SWEEPER_SCOPE,
                model_rules=deepcopy(SWEEPER_RULES),
            )
        )
        actor = self.apply(before)["scene"]["actors"][0]
        self.assertEqual(actor["attack_model"]["kind"], "none")
        self.assertNotIn("maximum_hp_fraction", actor["attack_model"])
        self.assertEqual(actor["damage"], 0)
        self.assertEqual(actor["hitpoints"], before["actors"][0]["hitpoints"])
        self.assertEqual(actor["sweeper_model"], before["actors"][0]["sweeper_model"])

    def test_percent_maximum_hp_policy_changes_only_selected_component(self):
        scene = self.compile(
            sector(self.catalog, [entity_instance("mono", "monolith", 3, "defense")])
        )
        base = scene["actors"][0]
        unchanged = self.apply(scene)["scene"]["actors"][0]
        scaled = self.apply(
            scene, modifier_policy(maximum_hp_damage_policy="scale_with_damage")
        )["scene"]["actors"][0]
        self.assertEqual(
            unchanged["attack_model"]["maximum_hp_fraction"],
            base["attack_model"]["maximum_hp_fraction"],
        )
        self.assertAlmostEqual(
            scaled["attack_model"]["maximum_hp_fraction"],
            base["attack_model"]["maximum_hp_fraction"] * 1.2,
        )
        self.assertEqual(scaled["damage"], unchanged["damage"])

    def test_ramp_initial_damage_and_cached_stages_agree(self):
        fixture = test_ramping.InfernoAdapterTests()
        fixture.catalog = self.catalog
        scene = self.compile(fixture.inferno_sector())
        changed = self.apply(scene)["scene"]
        actors = _load_actors(changed, 14, 12)
        runtime = RampCombat(actors)
        self.assertEqual(
            runtime.models["inferno"]["stages"][0]["damage_per_hit"],
            actors["inferno"]["damage"],
        )
        for original, scaled in zip(
            scene["actors"][0]["ramp_model"]["stages"],
            runtime.models["inferno"]["stages"],
        ):
            self.assertAlmostEqual(
                scaled["damage_per_hit"], original["damage_per_hit"] * 1.2
            )
            self.assertEqual(scaled["after_seconds"], original["after_seconds"])

    def test_actual_simulation_uses_scaled_cannon_damage_once(self):
        scene = self.compile(
            sector(
                self.catalog,
                [
                    entity_instance("cannon", "cannon", 21, "defense"),
                    entity_instance(
                        "tank", "pekka", 11, "attack", first_attack_seconds=10
                    ),
                ],
            )
        )
        baseline = simulate_spatial(scene)
        modified = simulate_spatial(self.apply(scene)["scene"])
        base_loss = scene["actors"][1]["hitpoints"] - baseline["actors"]["tank"]["hp"]
        scaled_loss = scene["actors"][1]["hitpoints"] - modified["actors"]["tank"]["hp"]
        self.assertGreater(base_loss, 0)
        self.assertAlmostEqual(scaled_loss, base_loss * 1.2)

    def test_hero_prepare_uses_scaled_base_and_unscaled_source_bonus_once(self):
        scene = self.compile(hero_sector(self.catalog, [hero()]))
        changed = self.apply(scene)["scene"]
        original = scene["actors"][0]
        actors = _load_actors(changed, 14, 12)
        runtime = HeroCombat(actors, PatternCombat(actors))
        runtime.expand_commands([ability("royal")], actors, 0, [])
        runtime.prepare(actors, 0, [])
        bonus = original["hero_model"]["equipment"][0]["damage_per_hit_increase"]
        expected = (original["damage"] + bonus) * 0.8
        self.assertAlmostEqual(actors["royal"]["damage"], expected)
        runtime.prepare(actors, 0.1, [])
        self.assertAlmostEqual(actors["royal"]["damage"], expected)
        self.assertEqual(
            actors["royal"]["attack_interval_seconds"],
            original["attack_interval_seconds"],
        )
        self.assertEqual(
            runtime.models["royal"]["health_recovery"],
            original["hero_model"]["health_recovery"],
        )

    def test_electro_boots_aura_policy_preserves_healing_and_owned_levels(self):
        scene = self.compile(hero_sector(self.catalog, [hero()]))
        original = scene["actors"][0]["hero_model"]["equipment"][1]
        scaled = self.apply(scene)["scene"]["actors"][0]["hero_model"]["equipment"][1]
        unchanged = self.apply(
            scene, modifier_policy(equipment_aura_damage_policy="unchanged")
        )["scene"]["actors"][0]["hero_model"]["equipment"][1]
        self.assertAlmostEqual(scaled["aura_damage"], original["aura_damage"] * 0.8)
        self.assertEqual(unchanged, original)
        self.assertEqual(
            scaled["self_healing_per_second"], original["self_healing_per_second"]
        )
        self.assertEqual(scaled["level"], original["level"])

    def test_wall_weapon_and_vial_bonus_stay_in_sync_after_prepare(self):
        queen = hero("archer-queen")
        queen["wall_parameters"] = {
            "kind": "clear_obstructions",
            "source": SOURCE,
            "route_cost": "travel_seconds_plus_nominal_clearance",
            "cooldown": "shared_with_main_weapon",
            "range": 5,
            "first_attack_seconds": 0,
            "impact_timing": "instant",
        }
        scene = self.compile(hero_sector(self.catalog, [queen]))
        changed = self.apply(scene)["scene"]
        actors = _load_actors(changed, 14, 12)
        runtime = HeroCombat(actors, PatternCombat(actors))
        base = scene["actors"][0]
        self.assertAlmostEqual(
            actors["queen"]["wall_behavior"]["weapon"]["damage"], base["damage"] * 0.8
        )
        runtime.expand_commands([ability("queen")], actors, 0, [])
        runtime.prepare(actors, 0, [])
        bonus = base["hero_model"]["equipment"][0]["damage_per_hit_increase"]
        self.assertAlmostEqual(
            actors["queen"]["wall_behavior"]["weapon"]["damage"],
            (base["damage"] + bonus) * 0.8,
        )

    def test_mirror_summons_inherit_exactly_once_or_explicitly_remain_unchanged(self):
        scene = self.compile(hero_sector(self.catalog, [hero("archer-queen")]))
        scaled = self.apply(scene)["scene"]["actors"]
        unchanged = self.apply(
            scene, modifier_policy(hero_summon_statistics_policy="unchanged")
        )["scene"]["actors"]
        self.assertGreater(len(scaled), 1)
        for original, changed, kept in zip(
            scene["actors"][1:], scaled[1:], unchanged[1:]
        ):
            for field in ("damage", "hitpoints"):
                self.assertAlmostEqual(changed[field], original[field] * 0.8)
            self.assertEqual(kept, original)

    def test_esport_rejects_equipped_attackers_without_mutation(self):
        scene = self.compile(hero_sector(self.catalog, [hero()]))
        original = deepcopy(scene)
        with self.assertRaisesRegex(InputError, "owned and effective equipment"):
            self.apply(scene, modifier_policy("esport"))
        self.assertEqual(scene, original)
        bare = self.compile(hero_sector(self.catalog, [hero(bare=True)]))
        result = self.apply(bare, modifier_policy("esport"))
        self.assertAlmostEqual(
            result["scene"]["actors"][0]["damage"], bare["actors"][0]["damage"] * 0.8
        )

    def test_trap_policy_scales_damage_only_including_spring(self):
        scene = self.cannon_scene()
        scene["traps"] = [
            compile_trap(trap_instance(), self.catalog),
            compile_trap(spring_instance(), self.catalog),
        ]
        scaled = self.apply(scene)["scene"]["traps"]
        unchanged = self.apply(scene, modifier_policy(trap_damage_policy="unchanged"))[
            "scene"
        ]["traps"]
        for original, changed, kept in zip(scene["traps"], scaled, unchanged):
            self.assertAlmostEqual(changed["damage"], original["damage"] * 1.2)
            self.assertEqual(kept["damage"], original["damage"])
            for field in original.keys() - {"damage"}:
                self.assertEqual(changed[field], original[field])

    def test_death_blast_and_town_hall_poison_have_separate_explicit_policy(self):
        for specification in (
            area_sector(
                self.catalog,
                [bomb_instance(), entity_instance("minion", "minion", 12, "attack")],
            ),
            town_hall_sector(
                self.catalog,
                [hall(), entity_instance("minion", "minion", 12, "attack")],
            ),
        ):
            with self.subTest(id=specification["entities"][0]["entity"]):
                scene = self.compile(specification)
                original = scene["actors"][0]
                scaled = self.apply(scene)["scene"]["actors"][0]
                kept = self.apply(
                    scene, modifier_policy(death_damage_policy="unchanged")
                )["scene"]["actors"][0]
                amount = original["death_model"]["effects"][0]["amount"]
                self.assertAlmostEqual(
                    scaled["death_model"]["effects"][0]["amount"], amount * 1.2
                )
                self.assertEqual(kept["death_model"], original["death_model"])
                if "town_hall_model" in original:
                    poison = original["town_hall_model"]["death_poison"]
                    self.assertAlmostEqual(
                        scaled["town_hall_model"]["death_poison"]["maximum_dps"],
                        poison["maximum_dps"] * 1.2,
                    )
                    self.assertEqual(kept["town_hall_model"]["death_poison"], poison)
                    self.assertEqual(
                        scaled["town_hall_model"]["activation"],
                        original["town_hall_model"]["activation"],
                    )

    def test_th17_flame_is_scaled_in_runtime_cache_once(self):
        scene = self.compile(artillery_sector(self.catalog, [artillery_hall()]))
        changed = self.apply(scene)["scene"]
        runtime = ArtilleryCombat(_load_actors(changed, 14, 12))
        original = scene["actors"][0]["artillery_model"]["flame"]
        self.assertAlmostEqual(
            runtime.models["hall"]["maximum_dps"], original["maximum_dps"] * 1.2
        )
        self.assertEqual(
            runtime.models["hall"]["duration_seconds"], original["duration_seconds"]
        )
        kept = self.apply(
            scene, modifier_policy(impact_hazard_damage_policy="unchanged")
        )["scene"]["actors"][0]
        self.assertEqual(kept["artillery_model"]["flame"], original)

    def test_scene_effects_and_independent_hazards_remain_unchanged(self):
        scene = self.cannon_scene()
        scene["effects"] = [{"kind": "damage", "amount": 12}]
        scene["persistent_hazards"] = [{"maximum_dps": 15}]
        scene["buff_fields"] = [{"damage_multiplier": 2}]
        result = self.apply(scene)["scene"]
        for field in ("effects", "persistent_hazards", "buff_fields"):
            self.assertEqual(result[field], scene[field])

    def test_none_profile_preserves_all_statistics_and_reports_paths(self):
        scene = self.compile(hero_sector(self.catalog, [hero()]))
        saved = deepcopy(scene)
        result = self.apply(scene, modifier_policy("none"))
        self.assertEqual(scene, saved)
        actor = result["scene"]["actors"][0]
        for change in result["application"]["actors"][0]["statistics"]:
            self.assertEqual(change["before"], change["after"])
            value = actor
            for field in change["path"]:
                value = value[field]
            self.assertEqual(value, change["after"])
        self.assertEqual(actor["hitpoints"], saved["actors"][0]["hitpoints"])

    def test_application_ledger_matches_every_changed_statistic(self):
        scene = self.compile(hero_sector(self.catalog, [hero()]))
        result = self.apply(scene)
        actor = result["scene"]["actors"][0]
        for change in result["application"]["actors"][0]["statistics"]:
            value = actor
            for field in change["path"]:
                value = value[field]
            self.assertEqual(value, change["after"])
            self.assertEqual(value, change["before"] * change["multiplier"])
        self.assertEqual(actor["entity_adapter"]["modifiers"]["damage_multiplier"], 0.8)

    def test_double_application_and_mixed_profile_actors_are_rejected(self):
        changed = self.apply(self.cannon_scene())["scene"]
        with self.assertRaisesRegex(InputError, "scene twice"):
            self.apply(changed)
        del changed[MARKER]
        with self.assertRaisesRegex(InputError, "actor twice"):
            self.apply(changed, modifier_policy("legend_ii"))

    def test_non_neutral_actor_and_secondary_scaling_are_rejected(self):
        for field in ("damage_multiplier", "hitpoints_multiplier", "range_multiplier"):
            scene = self.cannon_scene()
            scene["actors"][0]["entity_adapter"]["modifiers"][field] = 1.2
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(InputError, "neutral actor"),
            ):
                self.apply(scene)
        for specification, path in (
            (
                town_hall_sector(
                    self.catalog,
                    [hall(), entity_instance("minion", "minion", 12, "attack")],
                ),
                ("lifecycle_parameters", "death", "blast_damage_multiplier"),
            ),
            (
                artillery_sector(self.catalog, [artillery_hall()]),
                ("lifecycle_parameters", "flame", "maximum_dps_multiplier"),
            ),
        ):
            scene = self.compile(specification)
            values = scene["actors"][0]["entity_adapter"]
            for component in path[:-1]:
                values = values[component]
            values[path[-1]] = 1.2
            with self.assertRaisesRegex(InputError, "death and hazard"):
                self.apply(scene)

    def test_pre_scaled_trap_and_runtime_state_are_rejected(self):
        scene = self.cannon_scene()
        trap = compile_trap(trap_instance(), self.catalog)
        trap["damage"] *= 1.2
        scene["traps"] = [trap]
        with self.assertRaisesRegex(InputError, "neutral trap"):
            self.apply(scene)
        scene = self.cannon_scene()
        scene["actors"][0]["hp"] = 500
        with self.assertRaisesRegex(InputError, "before runtime"):
            self.apply(scene)

    def test_trap_cannot_override_global_profile_or_role(self):
        scene = self.cannon_scene()
        scene["traps"] = [compile_trap(trap_instance(), self.catalog)]
        scene["traps"][0]["profile_id"] = "legend_iii"
        with self.assertRaisesRegex(InputError, "Per-trap"):
            self.apply(scene)

    def test_inconsistent_per_actor_profile_and_role_overrides_are_rejected(self):
        for container_name in ("actor", "adapter"):
            for field in ("profile_id", "entity_role"):
                scene = self.cannon_scene()
                container = scene["actors"][0]
                if container_name == "adapter":
                    container = container["entity_adapter"]
                container[field] = "attacking_hero"
                with (
                    self.subTest(container=container_name, field=field),
                    self.assertRaisesRegex(InputError, "overrides"),
                ):
                    self.apply(scene)

    def test_policy_requires_complete_supported_choices(self):
        for change in (
            {"trap_damage_policy": "infer"},
            {"trap_damage_policy": []},
            {"healing_and_status_policy": "scale"},
            {"profile_id": "unknown"},
        ):
            with self.subTest(change=change), self.assertRaises(InputError):
                self.apply(self.cannon_scene(), modifier_policy(**change))
        policy = modifier_policy()
        del policy["trap_damage_policy"]
        with self.assertRaisesRegex(InputError, "every explicit"):
            self.apply(self.cannon_scene(), policy)


if __name__ == "__main__":
    unittest.main()
