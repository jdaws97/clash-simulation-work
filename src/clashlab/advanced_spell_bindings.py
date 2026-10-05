"""Shared owners for explicitly experimental permanent spell lifecycles."""

from copy import deepcopy
from math import floor

from .advanced_spell_models import (
    SUPPORTED_SPELLS,
    SHARED_BOUND_SPELLS as BOUND_SPELLS,
    spell_clock_after,
)
from .advanced_spells import (
    AdvancedSpellCombat,
    compile_advanced_spell_reserves,
    generated_template,
    troop_or_hero,
)
from .common import InputError, identifier, integer
from .rates import attack_resume_time, pause_attack_work
from .spatial import _active, _blocked, _ground_route


MIRROR_POLICY = "finite_owned_core_queen_children_fresh_membership_absolute_expiry"

BINDING_POLICIES = {
    "mirror_children": MIRROR_POLICY,
    "status": "explicit_uncalibrated_shared_spell_binding_v1",
    "spawn_geometry": "declared_in_board_clear_ground_point_no_automatic_relocation",
    "clone_lifecycles": "fresh_original_entity_compiler_or_spell_template_reject_unknown_owner",
    "damage_reduction": "multiply_ice_with_existing_reductions_after_flat_reduction",
    "shield_hit_order": "shared_packet_registration_order_breaking_hit_overflow_discarded",
    "movement_composition": "add_spell_bonus_before_existing_movement_multipliers",
    "jump_linger": "catalog_boostTime_after_field_expiry_then_finish_planned_wall_exit",
    "jump_displaced_exit": "shared_ground_route_to_nearest_clear_cell_after_forced_motion_no_teleport",
    "revival": "same_identity_preserve_spent_charges_and_absolute_statuses_resume_unfinished_work",
    "ice_lifecycles": "ordinary_weapons_and_core_hero_absolute_passives_reject_secondary_lifecycles",
    "shared_lifecycles": "ordinary_troop_clones_core_hero_revive_and_angry_reject_secondary_models",
}


def validate_binding(binding):
    expected = {"source", *BINDING_POLICIES}
    if not isinstance(binding, dict) or set(binding) not in (
        expected,
        expected - {"mirror_children"},
    ):
        raise InputError("Advanced spells require the complete shared binding contract")
    identifier(binding["source"], "advanced spell integration evidence")
    if any(
        binding[key] != value
        for key, value in BINDING_POLICIES.items()
        if key in binding
    ):
        raise InputError("Unsupported advanced spell integration policy")


def secondary_models(actor):
    return {key for key in actor if key.endswith("_model")} - {
        "attack_model",
        "spell_generated_model",
        "spell_clone_model",
    }


def core_hero(actor):
    model = actor.get("hero_model", {})
    return model.get("entity") in {
        "royal-champion",
        "archer-queen",
        "grand-warden",
    } and all(
        item["entity"]
        in {
            "rocket-spear",
            "electro-boots",
            "invisibility-vial",
            "magic-mirror",
            "eternal-tome",
            "healing-tome",
        }
        for item in model.get("equipment", [])
    )


def owned_mirror_children(actors, binding):
    """Admit only the finite fresh children of a supported equipped Queen."""
    from .heroes import compile_mirror_clones

    owned = set()
    for parent in actors.values():
        if not core_hero(parent) or not any(
            item["entity"] == "magic-mirror"
            for item in parent.get("hero_model", {}).get("equipment", [])
        ):
            continue
        if binding.get("mirror_children") != MIRROR_POLICY:
            raise InputError(
                "Ice/Angry Magic Mirror requires the explicit mirror_children policy"
            )
        if parent.get("entity_adapter", {}).get("entity") != "archer-queen":
            raise InputError("Magic Mirror spells require a compiled core Queen owner")
        expected = {child["id"]: child for child in compile_mirror_clones(parent)}
        actual = {
            key: child
            for key, child in actors.items()
            if child.get("summon_model", {}).get("parent") == parent["id"]
            and child["summon_model"].get("equipment") == "magic-mirror"
        }
        if set(actual) != set(expected):
            raise InputError(
                "Magic Mirror children differ from their finite owner roster"
            )
        for key, child in actual.items():
            template = expected[key]
            for field in (
                "source",
                "team",
                "kind",
                "layer",
                "movement",
                "spawn_seconds",
                "counts_for_destruction",
                "blocking",
                "width",
                "height",
                "hitpoints",
                "damage",
                "speed",
                "range",
                "attack_interval_seconds",
                "first_attack_seconds",
                "healing_class",
                "hazard_class",
                "summon_model",
                "wall_behavior",
                "target_layers",
                "hero_model",
                "entity_adapter",
            ):
                if child.get(field) != template.get(field):
                    raise InputError(
                        "Magic Mirror child differs from fresh owner declaration: "
                        + field
                    )
            pattern = deepcopy(child["attack_model"])
            expected_pattern = deepcopy(template["attack_model"])
            # Responses can differ per actor; the shared response validator owns
            # these two fields, not the source hero's acquisition declaration.
            for value in (pattern, expected_pattern):
                value.pop("target_kinds", None)
                value.pop("defending_unit_collateral_policy", None)
            if pattern != expected_pattern:
                raise InputError(
                    "Magic Mirror child weapon differs from its declaration"
                )
            owned.add(key)
    return owned


def compile_reserves(models, actors, instances, compile_instance):
    """Compile Clone from original declarations, never from live actor state."""
    models = [m for m in models if m["entity"] in SUPPORTED_SPELLS]
    requests = compile_advanced_spell_reserves(models, actors)
    originals = {instance["id"]: instance for instance in instances}
    generated = {r["id"]: r for r in requests if "spell_generated_model" in r}
    result = []
    for request in requests:
        if "spell_clone_model" not in request:
            result.append(request)
            continue
        source_id = request["spell_clone_model"]["source_id"]
        if source_id in originals:
            original = deepcopy(originals[source_id])
            if actors[source_id].get("summon_model") or any(
                key in original
                for key in ("barracks_member_parameters", "payload_member_parameters")
            ):
                raise InputError(
                    f"Clone source requires a separately bound lifecycle: {source_id}"
                )
            original.update(
                id=request["id"],
                spawn_seconds="controlled",
                x=request["x"],
                y=request["y"],
            )
            actor = compile_instance(original)
        elif source_id in generated:
            # This is a fresh output of generated_template, before any runtime
            # is constructed. Preserve its weapon/armor/exemption contract.
            actor = deepcopy(generated[source_id])
            actor.pop("spell_generated_model")
        else:
            raise InputError(f"Clone source has no bound fresh compiler: {source_id}")
        if secondary_models(actor):
            raise InputError(
                f"Clone secondary lifecycle requires explicit binding: {source_id}"
            )
        actor.update(
            id=request["id"],
            spawn_seconds="controlled",
            x=request["x"],
            y=request["y"],
            spell_clone_model=deepcopy(request["spell_clone_model"]),
        )
        result.append(actor)
    for actor in result:
        effects = {
            key.removeprefix("_spell_"): actor.pop(key)
            for key in list(actor)
            if key.startswith("_spell_")
        }
        if effects:
            actor["spell_unit_effects"] = effects
    return result


class SharedAdvancedSpells:
    def __init__(self, models, actors, binding, width, height, selector, pets=None):
        validate_binding(binding)
        self.actors, self.width, self.height, self.pets = actors, width, height, pets
        self.release_history = {}
        self.dead_work = {}
        self.jump_cells, self.jump_exit = {}, {}
        self.jump_displaced = set()
        selected = [m for m in models if m["entity"] in SUPPORTED_SPELLS]
        unbound = sorted({m["entity"] for m in selected} - BOUND_SPELLS)
        if unbound:
            raise InputError("Advanced spells are not yet bound: " + ", ".join(unbound))
        by_id = {m["id"]: m for m in selected}
        entities = {m["entity"] for m in selected}
        mirror_children = (
            owned_mirror_children(actors, binding)
            if entities & {"ice-block-spell", "angry-spell"}
            else set()
        )
        for actor in actors.values():
            if "revive-spell" in entities and "hero_model" in actor:
                if not core_hero(actor) or secondary_models(actor) - {"hero_model"}:
                    raise InputError(
                        "Revive secondary hero lifecycle requires explicit binding"
                    )
            if "angry-spell" in entities and troop_or_hero(actor):
                extra = secondary_models(actor) - (
                    {"hero_model"} if core_hero(actor) else set()
                )
                if actor["id"] in mirror_children:
                    extra.discard("summon_model")
                if extra or "defense" not in actor["target_priorities"]:
                    raise InputError(
                        "Angry secondary targeting/lifecycle requires explicit binding"
                    )
            if any(
                m["entity"] == "ice-block-spell" for m in selected
            ) and troop_or_hero(actor):
                secondary = {key for key in actor if key.endswith("_model")} - {
                    "attack_model",
                    "spell_generated_model",
                    "spell_clone_model",
                }
                if core_hero(actor):
                    secondary.discard("hero_model")
                if actor["id"] in mirror_children:
                    secondary.discard("summon_model")
                if secondary:
                    raise InputError(
                        "Ice Block secondary lifecycle requires explicit binding: "
                        + actor["id"]
                        + " ("
                        + ", ".join(sorted(secondary))
                        + ")"
                    )
            if "spell_clone_model" in actor:
                marker = actor["spell_clone_model"]
                if not isinstance(marker, dict) or set(marker) != {
                    "cast_id",
                    "source_id",
                    "index",
                }:
                    raise InputError("Clone requires complete finite ownership")
                identifier(marker["cast_id"], "Clone owning cast")
                identifier(marker["source_id"], "Clone source identity")
                integer(marker["index"], "Clone finite reserve index", 0)
                model = by_id.get(marker["cast_id"])
                source = actors.get(marker["source_id"])
                if model is None or model["entity"] != "clone-spell" or source is None:
                    raise InputError("Clone reserve has no owning spell/source")
                if (
                    secondary_models(actor)
                    or secondary_models(source)
                    or "spell_clone_model" in source
                ):
                    raise InputError(
                        "Clone secondary lifecycle requires explicit binding"
                    )
                # A fresh clone has the original declaration's weapon/statistics,
                # never its runtime HP, status, cooldown or ownership state.
                for field in (
                    "entity_adapter",
                    "attack_model",
                    "hitpoints",
                    "damage",
                    "speed",
                    "range",
                    "attack_interval_seconds",
                    "first_attack_seconds",
                    "housing_space",
                    "wall_behavior",
                    "on_hit_status",
                    "spell_unit_effects",
                ):
                    if actor.get(field) != source.get(field):
                        raise InputError(
                            "Clone reserve differs from its fresh source declaration: "
                            + field
                        )
                if "spell_unit_effects" in actor:
                    actor.update(
                        {
                            "_spell_" + k: v
                            for k, v in actor["spell_unit_effects"].items()
                        }
                    )
                continue
            marker = actor.get("spell_generated_model")
            if marker is not None:
                if (
                    not isinstance(marker, dict)
                    or set(marker) != {"cast_id", "entity", "index"}
                    or marker.get("cast_id") not in by_id
                ):
                    raise InputError("Generated spell actor has no owning cast")
                model = by_id[marker["cast_id"]]
                if (
                    model["entity"] not in {"bat-spell", "skeleton-spell"}
                    or marker["entity"] != model["entity"]
                ):
                    raise InputError("Generated spell actor has the wrong spell family")
                index = integer(
                    marker["index"],
                    "spell reserve index",
                    0,
                    model["quantities"]["count"] - 1,
                )
                template = generated_template(model, index)
                if actor["id"] != template["id"]:
                    raise InputError(
                        "Generated spell identity differs from its finite reserve"
                    )
                expected = {
                    k.removeprefix("_spell_"): v
                    for k, v in template.items()
                    if k.startswith("_spell_")
                }
                if actor.get("spell_unit_effects") != expected:
                    raise InputError(
                        "Generated spell effects differ from their owning cast"
                    )
                actor.update({"_spell_" + k: v for k, v in expected.items()})
            elif "spell_unit_effects" in actor:
                raise InputError("Spell unit effects require their generated owner")
        self.runtime = AdvancedSpellCombat(
            selected,
            actors,
            register_actor=self.register,
            revive_actor=self.revive,
            expire_actor=self.expire,
            status_callback=self.status,
            base_selector=selector,
        )

    def register(self, actor, time, source_id):
        if (
            actor["id"] in self.release_history
            or actor["spawn_seconds"] != "controlled"
        ):
            raise InputError("Spell reserve cannot be released twice")
        if not (0 <= actor["x"] < self.width and 0 <= actor["y"] < self.height):
            raise InputError("Spell reserve spawn is outside the board")
        if actor["movement"] == "ground" and (
            floor(actor["x"]),
            floor(actor["y"]),
        ) in _blocked(self.actors, time):
            raise InputError("Spell reserve needs a clear declared ground spawn point")
        actor["spawn_seconds"] = time
        actor["next_attack"] = spell_clock_after(time, actor["first_attack_seconds"])
        if "_wall_next_attack" in actor:
            actor["_wall_next_attack"] = spell_clock_after(
                time, actor["wall_behavior"]["weapon"]["first_attack_seconds"]
            )
        self.release_history[actor["id"]] = {
            "released_at": time,
            "source_id": source_id,
        }
        return actor

    def observe_deaths(self):
        for key, actor in self.actors.items():
            if "hero_model" not in actor or actor["hp"] > 0 or key in self.dead_work:
                continue
            death = actor["death_time"]
            if death is None:
                continue
            resume = attack_resume_time(actor, death)
            self.dead_work[key] = {
                clock: max(actor[clock] - resume, 0)
                for clock in ("next_attack", "_wall_next_attack")
                if clock in actor
            }

    def revive(self, actor, fraction, time, policy):
        if actor["hp"] > 0 or actor["death_time"] is None or "hero_model" not in actor:
            raise InputError("Revive needs a defeated deployed hero")
        if "death_model" in actor:
            raise InputError("Revive of a hero with an extra death model is unbound")
        if self.pets is not None:
            pet_id = self.pets.phoenix_by_hero.get(actor["id"])
            if (
                pet_id is not None
                and self.pets.states[pet_id]["temporary_life_until"] is not None
            ):
                raise InputError(
                    "Revive cannot replace an unsettled Phoenix temporary life"
                )
        self.observe_deaths()
        work = self.dead_work.pop(actor["id"])
        actor.update(hp=actor["maximum_hp"] * fraction, death_time=None, target=None)
        for field in ("_remaining_path", "_path_signature"):
            actor.pop(field, None)
        for clock, remaining in work.items():
            actor[clock] = spell_clock_after(attack_resume_time(actor, time), remaining)

    def expire(self, actor, time):
        if actor["hp"] <= 0:
            # Retiring a lifetime must not erase an earlier actual HP death.
            return
        # No death timestamp: the ordinary death owner cannot emit a new blast.
        # Already released packets retain their original source ownership.
        actor.update(
            hp=0,
            death_time=None,
            target=None,
            _spell_silent_expiry=True,
        )
        actor.pop("_remaining_path", None)
        actor.pop("_path_signature", None)

    @staticmethod
    def status(actor, time, previous, new):
        pause_attack_work(actor, time, new)

    def _prepare_jump(self, time):
        for key, actor in self.actors.items():
            if actor["movement"] != "ground" or not troop_or_hero(actor):
                continue
            cells = set(self.runtime.jump_wall_cells(actor, time))
            for model in self.runtime.models.values():
                if (
                    model["entity"] != "jump-spell"
                    or model["id"] not in self.runtime.resolved
                ):
                    continue
                end = spell_clock_after(
                    model["arrival_seconds"], model["quantities"]["duration_seconds"]
                )
                linger_end = spell_clock_after(
                    end, model["quantities"]["exit_linger_seconds"]
                )
                if end <= time < linger_end and _active(actor, time):
                    cells.update(
                        (w["x"], w["y"])
                        for w in self.actors.values()
                        if w["kind"] == "wall"
                        and w["team"] != actor["team"]
                        and _active(w, time)
                        and self.runtime._inside(model, w)
                    )
            old = self.jump_cells.get(key, set())
            cell = floor(actor["x"]), floor(actor["y"])
            if old != cells:
                if cell in old - cells and _active(actor, time):
                    path = actor.get("_remaining_path", [])
                    exit_path = []
                    for point in path:
                        exit_path.append(point)
                        if (floor(point[0]), floor(point[1])) not in old:
                            break
                    if (
                        not exit_path
                        or (floor(exit_path[-1][0]), floor(exit_path[-1][1])) in old
                    ):
                        exit_path = self._jump_exit_route(actor, time, old)
                    self.jump_exit[key] = (exit_path, old)
                    actor["_remaining_path"] = exit_path
                actor.pop("_path_signature", None)
                actor["target"] = None
            if key in self.jump_exit:
                _, previous_cells = self.jump_exit[key]
                if cell not in previous_cells or not _active(actor, time):
                    del self.jump_exit[key]
                    self.jump_displaced.discard(key)
                else:
                    displaced = actor.get("_displacement_pause_until", 0) > time
                    if displaced or key in self.jump_displaced:
                        exit_path = self._jump_exit_route(actor, time, previous_cells)
                        self.jump_exit[key] = (exit_path, previous_cells)
                        actor["_remaining_path"] = exit_path
                        if displaced:
                            self.jump_displaced.add(key)
                        else:
                            self.jump_displaced.discard(key)
                    cells |= previous_cells
            self.jump_cells[key] = cells
            actor["_spell_jump_cells"] = sorted(cells)

    def _jump_exit_route(self, actor, time, cells):
        # Reuse the same four-neighbor router, retaining only the already granted
        # wall exemption. Buildings, ungranted walls and board bounds remain solid.
        path = _ground_route(
            actor,
            None,
            _blocked(self.actors, time) - cells,
            self.width,
            self.height,
            exit_cells=cells,
        )
        if not path:
            raise InputError("Jump wall exit has no reachable clear cell")
        return path

    def prepare(self, time, trace):
        self.observe_deaths()
        self.runtime.prepare(time, trace)
        self._prepare_jump(time)

    def select_target(self, actor, actors, time, blocked, width, height):
        if actor["id"] in self.jump_exit:
            return None, list(
                actor.get("_remaining_path", self.jump_exit[actor["id"]][0])
            )
        return self.runtime.select_target(actor, actors, time, blocked, width, height)

    def next_boundary(self, time):
        values = [self.runtime.next_boundary(time)]
        for model in self.runtime.models.values():
            if model["entity"] == "jump-spell":
                q = model["quantities"]
                values.append(
                    spell_clock_after(
                        spell_clock_after(
                            model["arrival_seconds"], q["duration_seconds"]
                        ),
                        q["exit_linger_seconds"],
                    )
                )
        return min((v for v in values if v is not None and v > time), default=None)

    def result(self):
        return {
            **self.runtime.result(),
            "release_history": deepcopy(self.release_history),
            "ice_members": {
                key: sorted(members)
                for key, members in self.runtime.ice_members.items()
            },
            "jump_wall_exemptions": {
                key: sorted(cells) for key, cells in self.jump_cells.items() if cells
            },
            "pending_wall_exit_ids": sorted(self.jump_exit),
            "reserves": {
                key: {
                    "owner": deepcopy(
                        actor.get(
                            "spell_generated_model", actor.get("spell_clone_model")
                        )
                    ),
                    **deepcopy(
                        self.release_history.get(
                            key, {"released_at": None, "source_id": None}
                        )
                    ),
                }
                for key, actor in self.actors.items()
                if "spell_generated_model" in actor or "spell_clone_model" in actor
            },
        }
