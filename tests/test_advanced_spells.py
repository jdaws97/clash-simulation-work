"""Bounded synthetic lifecycle checks; callback contracts are not game calibration."""

from copy import deepcopy
from pathlib import Path
import json
from math import inf, nextafter
import unittest

from clashlab.advanced_spell_models import CONTRACT, POLICIES, compile_advanced_spell
from clashlab.advanced_spells import (
    AdvancedSpellCombat,
    armor_damage,
    compile_advanced_spell_reserves,
)
from clashlab.battle_resources import battle_resource_use
from clashlab.catalog import Catalog
from clashlab.common import InputError
from clashlab.rates import pause_attack_work
from clashlab.spatial import _select_target
from clashlab.full_battle import compile_full_battle
from clashlab.attack_spell_models import compile_attack_spell
from clashlab.recipe_spells import RecipeSpellCombat
from test_full_battle import fixture


ROOT = Path(__file__).resolve().parents[1]


def cast(catalog, entity, identity=None, time=0, **changes):
    parameters = {
        **POLICIES,
        "source": "synthetic-explicit-spell-policy",
        "status": CONTRACT,
        "impact_delay_seconds": 0,
        "spawn_interval_seconds": 0.1,
        "spawn_offsets": [[0, 0] for _ in range(60)],
        "movement_units_per_tile": 8,
        "skeleton_armor_minimum_level": 5,
        "bat_town_hall_damage_multiplier": 0.123,  # Deliberately synthetic; absent pinned statistic.
    }
    parameters.update(changes)
    return compile_advanced_spell(
        {
            "id": identity or entity,
            "entity": entity,
            "level": 1,
            "town_hall": 18,
            "time_seconds": time,
            "x": 10,
            "y": 10,
            "parameters": parameters,
        },
        catalog,
    )


def unit(identity="troop", **changes):
    actor = {
        "id": identity,
        "team": "attack",
        "kind": "unit",
        "layer": "ground",
        "movement": "ground",
        "spawn_seconds": 0,
        "hp": 20,
        "hitpoints": 100,
        "x": 10,
        "y": 10,
        "width": 0,
        "height": 0,
        "healing_class": "troop",
        "housing_space": 5,
        "target": None,
        "speed": 1,
        "damage": 10,
        "next_attack": 4,
        "immune_until": 0,
        "frozen_until": 0,
        "range": 0.5,
        "target_priorities": ["defense", "building"],
        "target_layers": ["ground"],
        "_target_ranks": {"defense": 0, "building": 0},
        "entity_adapter": {"entity": "synthetic-supported-troop", "level": 1},
    }
    actor.update(changes)
    return actor


class Callbacks:
    """Small declared kernel surrogate; intentionally no full-battle fidelity claim."""

    def __init__(self, actors):
        self.actors, self.revivals, self.expirations = actors, [], []

    def register(self, template, time, source):
        actor = template
        actor.update(hp=actor["hitpoints"], spawn_seconds=time, next_attack=time)
        return actor

    def reserves(self, models):
        for template in compile_advanced_spell_reserves(models, self.actors):
            actor = (
                deepcopy(template)
                if "spell_generated_model" in template
                else unit(
                    template["id"],
                    **{k: deepcopy(v) for k, v in template.items() if k != "id"},
                )
            )
            actor["hp"] = actor["hitpoints"]
            self.actors[actor["id"]] = actor

    def revive(self, actor, fraction, time, policy):
        self.revivals.append(actor["id"])
        actor.update(
            hp=actor["hitpoints"] * fraction,
            death_time=None,
            target=None,
            next_attack=max(actor["next_attack"], time),
        )

    def expire(self, actor, time):
        self.expirations.append(actor["id"])
        actor["hp"] = 0

    def status(self, actor, time, previous, current):
        # Existing shared helper consumes frozen_until. Integration extends its
        # union to _spell_pause_until; emulate only that union in this surrogate.
        original = actor["frozen_until"]
        actor["frozen_until"] = max(original, previous)
        pause_attack_work(actor, time, current)
        actor["frozen_until"] = original

    def arguments(self):
        return {
            "register_actor": self.register,
            "revive_actor": self.revive,
            "expire_actor": self.expire,
            "status_callback": self.status,
        }


class AdvancedSpellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_overlap_ice_pause_reduction_expiry_and_recipient_exclusions(self):
        actors = {key: unit(key) for key in ("troop", "hero", "pet", "siege", "enemy")}
        actors["hero"].update(hero_model={}, healing_class="hero")
        actors["pet"]["pet_model"] = {}
        actors["siege"]["siege_model"] = {}
        actors["enemy"]["team"] = "defense"
        first = cast(self.catalog, "ice-block-spell", "ice1")
        second = cast(self.catalog, "ice-block-spell", "ice2", time=2)
        second["quantities"]["incoming_damage_multiplier"] = 0.05
        callbacks = Callbacks(actors)
        runtime = AdvancedSpellCombat([first, second], actors, **callbacks.arguments())
        trace = []
        runtime.prepare(0, trace)
        actors["troop"]["x"] = 40  # Captured Ice membership persists outside radius.
        runtime.prepare(2, trace)
        self.assertEqual(
            actors["hero"]["next_attack"], 13
        )  # Four units of remaining work + union [0,9].
        self.assertAlmostEqual(
            actors["hero"]["_spell_incoming_damage_multiplier"], 0.05
        )
        self.assertEqual(actors["hero"]["_spell_pause_until"], 9)
        self.assertAlmostEqual(
            actors["troop"]["_spell_incoming_damage_multiplier"], 0.14
        )
        for key in ("pet", "siege", "enemy"):
            self.assertEqual(actors[key]["_spell_pause_until"], 0)
        runtime.prepare(7, trace)
        self.assertEqual(actors["troop"]["_spell_pause_until"], 0)
        runtime.prepare(9, trace)
        self.assertEqual(actors["hero"]["_spell_incoming_damage_multiplier"], 1)
        self.assertEqual(actors["hero"]["next_attack"], 13)
        self.assertEqual(
            len([e for e in trace if e["event"] == "attack_spell_cast"]), 2
        )

    def test_anger_continuous_crossing_linger_expiry_is_step_independent(self):
        results = []
        for step in (0.1, 1.0):
            actor = unit("troop", x=2, target="building")
            building = unit(
                "building",
                kind="building",
                team="defense",
                x=4,
                y=11,
                width=1,
                height=1,
            )
            defense = unit(
                "defense", kind="defense", team="defense", x=10, y=10, width=1, height=1
            )
            actors = {"troop": actor, "building": building, "defense": defense}
            runtime = AdvancedSpellCombat(
                [cast(self.catalog, "angry-spell")],
                actors,
                base_selector=_select_target,
            )
            trace = []
            runtime.prepare(0, trace)
            # Radius six: enter at x=4, leave at x=16. Test exact entry/exit.
            self.assertAlmostEqual(
                runtime.first_crossing_delay(actor, [(18, 10)], 0, 10, 2), 1
            )
            actor["x"] = 4
            runtime.prepare(1, trace)
            self.assertTrue(actor["_spell_defense_priority"])
            self.assertIsNone(actor["target"])
            selected, _ = runtime.select_target(actor, actors, 1, set(), 30, 30)
            self.assertEqual(selected["id"], "defense")
            self.assertEqual(actor["_target_ranks"], {"defense": 0, "building": 0})
            time = 1
            while time + step < 5 - 1e-8:
                time += step
                runtime.prepare(time, trace)
            runtime.prepare(5, trace)  # End-of-field contact retains exactly 7 s anger.
            self.assertEqual(runtime.anger_until["angry-spell", "troop"], 12)
            runtime.prepare(12, trace)
            selected, _ = runtime.select_target(actor, actors, 12, set(), 30, 30)
            self.assertEqual(selected["id"], "building")
            results.append(
                (actor["_spell_movement_bonus"], actor["_spell_defense_priority"])
            )
        self.assertEqual(results, [(0, False), (0, False)])

    def test_generated_counts_no_extra_army_spend_and_armor(self):
        models = [
            cast(self.catalog, entity) for entity in ("bat-spell", "skeleton-spell")
        ]
        actors, trace = {}, []
        callbacks = Callbacks(actors)
        callbacks.reserves(models)
        runtime = AdvancedSpellCombat(models, actors, **callbacks.arguments())
        runtime.prepare(0, trace)
        self.assertEqual(len(runtime.continuation_reasons(0)), 2)
        time = 0
        while (boundary := runtime.next_boundary(time)) is not None:
            time = boundary
            runtime.prepare(time, trace)
        self.assertEqual(
            len(actors), 19
        )  # Catalog level-1: seven bats, twelve skeletons.
        self.assertEqual(runtime.continuation_reasons(time), [])
        runtime.prepare(time, trace)
        self.assertEqual(
            len([e for e in trace if e["event"] == "spell_unit_spawn"]), 19
        )
        self.assertTrue(all(a["_spell_trap_trigger_exempt"] for a in actors.values()))
        bat = actors["bat-spell:spawn:0"]
        self.assertEqual((bat["damage"], bat["speed"], bat["layer"]), (60, 7, "air"))
        self.assertEqual(bat["_spell_resource_damage_multiplier"], 0.4)
        skeleton = actors["skeleton-spell:spawn:0"]
        self.assertEqual(skeleton["_spell_armor_hp"], 0)  # Explicit armor threshold.
        skeleton["_spell_armor_hp"] = 30
        self.assertEqual(armor_damage(skeleton, 50), 0)
        self.assertEqual(armor_damage(skeleton, 10), 10)
        bindings = {
            "attacker_bindings": {},
            "spell_bindings": [
                {"entity": m["entity"], "cast": {"time_seconds": m["time_seconds"]}}
                for m in models
            ],
            "planned_deployments": {},
        }
        resources = battle_resource_use(
            bindings, {"actors": actors, "trace": trace}, time
        )
        self.assertTrue(all(slot["spent"] for slot in resources["spell_slots"]))
        self.assertEqual(resources["deployed_attacker_ids"], [])

    def test_clone_housing_budget_fresh_hp_excludes_heroes_and_clones_expire(self):
        actors = {
            "troop": unit(),
            "hero": unit("hero", hero_model={}, healing_class="hero"),
        }
        callbacks = Callbacks(actors)
        models = [cast(self.catalog, "clone-spell")]
        callbacks.reserves(models)
        runtime = AdvancedSpellCombat(models, actors, **callbacks.arguments())
        trace = []
        runtime.prepare(0, trace)
        self.assertEqual(runtime.capacity["clone-spell"], 2)
        self.assertEqual(runtime.spawned["clone-spell"], 4)
        self.assertTrue(all(actors[key]["hp"] == 100 for key in runtime.clone_expiry))
        runtime.prepare(1, trace)
        self.assertEqual(runtime.spawned["clone-spell"], 4)
        actors["troop"]["hp"] = 0
        held = next(iter(runtime.clone_expiry))
        actors[held]["_recalled"] = True
        runtime.prepare(30, trace)
        self.assertEqual(len(callbacks.expirations), 4)
        self.assertEqual(actors["troop"]["hp"], 0)

    def test_revive_one_hero_per_cast_preserves_ability_and_absolute_status(self):
        actors = {
            key: unit(
                key,
                hp=0,
                hero_model={},
                healing_class="hero",
                death_time=0,
                ability_spent=True,
                immune_until=10,
            )
            for key in ("a", "b")
        }
        callbacks = Callbacks(actors)
        models = [
            cast(self.catalog, "revive-spell", "r1"),
            cast(self.catalog, "revive-spell", "r2", time=1),
        ]
        runtime = AdvancedSpellCombat(models, actors, **callbacks.arguments())
        trace = []
        runtime.prepare(0, trace)
        self.assertEqual(callbacks.revivals, ["a"])
        self.assertEqual(actors["a"]["hp"], 60)
        self.assertTrue(actors["a"]["ability_spent"])
        self.assertEqual(actors["a"]["immune_until"], 10)
        self.assertEqual(actors["a"]["next_attack"], 4)
        runtime.prepare(1, trace)
        self.assertEqual(callbacks.revivals, ["a", "b"])
        runtime.prepare(1, trace)
        self.assertEqual(len(callbacks.revivals), 2)

    def test_jump_only_live_enemy_walls_expire_and_contract_fail_closed(self):
        actors = {
            "troop": unit(),
            "wall": unit("wall", kind="wall", team="defense", x=11, width=1, height=1),
            "building": unit("building", kind="building", team="defense", x=11),
            "friendly": unit("friendly", kind="wall", x=11),
        }
        runtime = AdvancedSpellCombat([cast(self.catalog, "jump-spell")], actors)
        trace = []
        runtime.prepare(0, trace)
        self.assertEqual(runtime.jump_wall_cells(actors["troop"], 0), {(11, 10)})
        runtime.prepare(20, trace)
        self.assertEqual(runtime.jump_wall_cells(actors["troop"], 20), set())
        with self.assertRaisesRegex(InputError, "registration"):
            AdvancedSpellCombat([cast(self.catalog, "clone-spell")], actors)
        with self.assertRaisesRegex(InputError, "reconciliation"):
            AdvancedSpellCombat([cast(self.catalog, "revive-spell")], actors)
        with self.assertRaisesRegex(InputError, "opt-in"):
            cast(self.catalog, "jump-spell", status="verified_game_fidelity")
        delayed = cast(self.catalog, "jump-spell", impact_delay_seconds=1e-12)
        exact = AdvancedSpellCombat([delayed], actors)
        exact.prepare(0, [])
        self.assertEqual(exact.next_boundary(0), 1e-12)
        self.assertEqual(exact.resolved, set())
        exact.prepare(1e-12, [])
        self.assertEqual(exact.resolved, {"jump-spell"})
        delayed = cast(self.catalog, "jump-spell", time=100, impact_delay_seconds=1e-15)
        exact = AdvancedSpellCombat([delayed], actors)
        exact.prepare(100, [])
        self.assertEqual(exact.resolved, set())
        boundary = exact.next_boundary(100)
        self.assertEqual(boundary, nextafter(100, inf))
        exact.prepare(boundary, [])
        self.assertEqual(exact.resolved, {"jump-spell"})

    def test_old_scope_still_rejects_advanced_spell_inventory(self):
        # New shared bindings do not widen older schema capabilities.
        for entity in (
            "clone-spell",
            "jump-spell",
            "bat-spell",
            "skeleton-spell",
            "revive-spell",
            "ice-block-spell",
            "angry-spell",
        ):
            specification, account, army, layout = fixture(self.catalog)
            account["levels"][entity] = 1
            army["spells"] = [{"id": entity, "level": 1, "count": 1}]
            expected = "explicit v29 scope"
            with self.assertRaisesRegex(InputError, expected):
                compile_full_battle(specification, account, army, layout, self.catalog)

    def test_angry_clock_survives_real_recall_until_absolute_expiry(self):
        for return_time in (3, 9):
            actor = unit("held-troop", blocking=False)
            actors, trace = {actor["id"]: actor}, []
            angry = AdvancedSpellCombat(
                [cast(self.catalog, "angry-spell")],
                actors,
                base_selector=_select_target,
            )
            parameters = json.loads(
                (ROOT / "data/battle-policies/recipe-spells.json").read_text()
            )["recall-spell"]
            parameters["redeployment"] = {
                "time_seconds": return_time,
                "position": {"x": 20, "y": 10},
                "regions": [{"left": 19, "right": 21, "top": 9, "bottom": 11}],
                "source": "synthetic-open-redeployment-cell",
            }
            model = compile_attack_spell(
                {
                    "id": "recall",
                    "entity": "recall-spell",
                    "level": 1,
                    "town_hall": 18,
                    "time_seconds": 2,
                    "x": 20,
                    "y": 10,
                    "parameters": parameters,
                },
                self.catalog,
            )
            recall = RecipeSpellCombat([model], actors, 30, 30)
            angry.prepare(0, trace)
            actor["x"] = 20
            angry.prepare(1, trace)
            self.assertEqual(angry.anger_until["angry-spell", actor["id"]], 8)
            recall.prepare(2, trace)
            angry.prepare(2, trace)
            self.assertTrue(actor["_recalled"])
            self.assertEqual(angry.anger_until.get(("angry-spell", actor["id"])), 8)
            self.assertEqual(actor["_spell_movement_bonus"], 0)
            self.assertFalse(actor["_spell_defense_priority"])
            recall.prepare(return_time, trace)
            angry.prepare(return_time, trace)
            self.assertFalse(actor["_recalled"])
            self.assertEqual(actor["_spell_defense_priority"], return_time < 8)
            if return_time < 8:
                self.assertEqual(angry.anger_until["angry-spell", actor["id"]], 8)
                self.assertEqual(actor["_spell_movement_bonus"], 4.375)
                angry.prepare(8, trace)
            self.assertNotIn(("angry-spell", actor["id"]), angry.anger_until)
            self.assertEqual(actor["_spell_movement_bonus"], 0)
            self.assertFalse(actor["_spell_defense_priority"])
            self.assertEqual(
                len([e for e in trace if e["event"] == "recall_capture"]), 1
            )
            self.assertEqual(
                len([e for e in trace if e["event"] == "recall_redeployment"]), 1
            )

    def test_simultaneous_bat_clone_settles_once_independent_of_cross_family_ids(self):
        for clone_id, bat_id in (("a-clone", "z-bat"), ("z-clone", "a-bat")):
            actors, trace = {}, []
            callbacks = Callbacks(actors)
            models = [
                cast(self.catalog, "clone-spell", clone_id),
                cast(self.catalog, "bat-spell", bat_id),
            ]
            callbacks.reserves(models)
            runtime = AdvancedSpellCombat(models, actors, **callbacks.arguments())
            runtime.prepare(0, trace)
            once, trace_once = runtime.result(), deepcopy(trace)
            self.assertEqual(runtime.spawned.get(clone_id, 0), 22)
            self.assertEqual(runtime.spawned[bat_id], 1)
            self.assertEqual(runtime.capacity[clone_id], 0)
            self.assertEqual(set(runtime.clone_expiry.values()), {30})
            runtime.prepare(0, trace)
            self.assertEqual(runtime.result(), once)
            self.assertEqual(trace, trace_once)
            self.assertEqual(
                len([e for e in trace if e["event"] == "attack_spell_cast"]), 2
            )


if __name__ == "__main__":
    unittest.main()
