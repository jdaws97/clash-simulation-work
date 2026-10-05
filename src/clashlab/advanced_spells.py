"""Paid spell lifecycles with explicit kernel registration/revival boundaries.

Callbacks are mandatory for generated combatants and revived heroes: writing HP
alone does not register weapons, reset death observers, or resume hero combat.
"""

from copy import deepcopy
from math import hypot, inf, nextafter

from .advanced_spell_models import (
    SPELL_CLASSES,
    spell_clock_after,
    validate_advanced_spell,
)
from .battle_termination import continuation_fact
from .buffs import _circle_events
from .common import InputError, integer, number
from .spatial import EPSILON, _active, center


PREPARE_PHASE = {
    "bat-spell": 0,
    "skeleton-spell": 0,
    "revive-spell": 1,
    "clone-spell": 2,
    "ice-block-spell": 3,
    "angry-spell": 3,
    "jump-spell": 3,
}


def troop_or_hero(actor):
    return (
        actor["team"] == "attack"
        and actor["kind"] == "unit"
        and not any(
            key in actor for key in ("pet_model", "siege_model", "spell_decoy_model")
        )
        and actor.get("healing_class") in {"troop", "hero"}
    )


def generated_template(model, index):
    """Compiler-owned ordinary weapon templates; no extra army inventory spend."""
    q = model["quantities"]
    bat = model["entity"] == "bat-spell"
    dx, dy = model["parameters"]["spawn_offsets"][index]
    kinds = ["defense", "building"] if bat else ["defense", "building", "unit"]
    source = model["statistics_source"]
    result = {
        "id": f"{model['id']}:spawn:{index}",
        "source": source,
        "team": "attack",
        "kind": "unit",
        "layer": "air" if bat else "ground",
        "movement": "air" if bat else "ground",
        "spawn_seconds": "controlled",
        "first_attack_seconds": 0,
        "x": model["position"][0] + dx,
        "y": model["position"][1] + dy,
        "width": 0,
        "height": 0,
        "blocking": False,
        "counts_for_destruction": False,
        "hitpoints": q["hitpoints"],
        "damage": q["damage"],
        "attack_interval_seconds": q["attack_interval_seconds"],
        "speed": q["speed"],
        "range": q["range"],
        "minimum_range": 0,
        "target_priorities": kinds,
        "target_priority_tiers": [["defense"], ["building"]] if bat else [kinds],
        "target_layers": ["ground"],
        "healing_class": "troop",
        "buff_class": "troop",
        "hazard_class": "troop",
        "spring_class": "other",
        "housing_space": 1,
        "spell_generated_model": {
            "cast_id": model["id"],
            "entity": model["entity"],
            "index": index,
        },
        "_spell_trap_trigger_exempt": True,
        "_spell_garrison_trigger_exempt": True,
        "_spell_armor_hp": q["armor_hitpoints"],
        "_spell_resource_damage_multiplier": q["resource_damage_multiplier"],
        "_spell_town_hall_damage_multiplier": q["town_hall_damage_multiplier"],
        "attack_model": {
            "kind": "single",
            "source": source,
            "target_kinds": kinds,
            "target_layers": ["ground"],
            "maximum_hp_fraction": 0,
            "projectile": {
                "timing": "instant",
                "delay_seconds": 0,
                "destination": "locked_actor_center_at_impact",
                "hit_radius": 0,
            },
        },
        "entity_adapter": {
            **deepcopy(model["entity_adapter"]),
            "generated_unit": "bat" if bat else "skeleton",
            "modifiers": {
                "source": source,
                **{
                    key: 1
                    for key in (
                        "hitpoints_multiplier",
                        "damage_multiplier",
                        "maximum_hp_damage_multiplier",
                        "attack_interval_multiplier",
                        "range_multiplier",
                        "movement_speed_multiplier",
                    )
                },
            },
        },
    }
    if not bat:
        result["wall_behavior"] = {"kind": "avoid", "source": source}
    return result


def compile_advanced_spell_reserves(models, actors):
    """Predeclare finite children for kernel compilation before combat starts.

    Clone requests require the lead's normal entity compiler (including supported
    troop lifecycle) and cannot be passed directly as generic raw actors.
    """
    reserves = []
    sources = dict(actors)
    for model in models:
        if model["entity"] in {"bat-spell", "skeleton-spell"}:
            children = [
                generated_template(model, index)
                for index in range(model["quantities"]["count"])
            ]
            reserves.extend(children)
            sources.update({item["id"]: item for item in children})
    for model in models:
        if model["entity"] == "clone-spell":
            for key, source in sorted(sources.items()):
                if (
                    not troop_or_hero(source)
                    or source.get("healing_class") != "troop"
                    or "spell_clone_model" in source
                ):
                    continue
                weight = integer(
                    source.get("housing_space"), "Clone needs explicit troop housing", 1
                )
                count = model["quantities"]["capacity"] // weight
                if count > len(model["parameters"]["spawn_offsets"]):
                    raise InputError(
                        "Clone needs enough declared offsets for its finite reserves"
                    )
                for index in range(count):
                    dx, dy = model["parameters"]["spawn_offsets"][index]
                    reserves.append(
                        {
                            "id": f"{model['id']}:clone:{key}:{index}",
                            "entity_adapter": deepcopy(source["entity_adapter"]),
                            "spawn_seconds": "controlled",
                            "x": model["position"][0] + dx,
                            "y": model["position"][1] + dy,
                            "spell_clone_model": {
                                "cast_id": model["id"],
                                "source_id": key,
                                "index": index,
                            },
                            "clone_state_policy": model["parameters"]["clone_state"],
                        }
                    )
    if len({item["id"] for item in reserves}) != len(reserves):
        raise InputError("Duplicate spell reserve identity")
    return reserves


class AdvancedSpellCombat:
    """Own casting, fields, finite summons, clone budgets and status expiry.

    register_actor(reserve, time, source_actor_id) activates a PRECOMPILED reserve
    registered in actors and all applicable weapon/lifecycle owners. The name
    denotes runtime-owner registration, never unbounded dynamic actor creation.
    revive_actor(actor, health_fraction, time, policy) must revive that same actor
    and reconcile death observers/hero runtime without restoring spent abilities.
    expire_actor(actor, time) removes the clone without ordinary death effects.
    """

    def __init__(
        self,
        models,
        actors,
        *,
        register_actor=None,
        revive_actor=None,
        expire_actor=None,
        base_selector=None,
        status_callback=None,
    ):
        self.models = {}
        for model in models:
            if model["entity"] not in SPELL_CLASSES:
                raise InputError("Unsupported permanent spell runtime")
            validate_advanced_spell(model)
            if model["id"] in self.models:
                raise InputError("Duplicate paid spell cast ID")
            self.models[model["id"]] = deepcopy(model)
        self.actors = actors
        self.register_actor, self.revive_actor, self.expire_actor = (
            register_actor,
            revive_actor,
            expire_actor,
        )
        self.base_selector = base_selector
        self.status_callback = status_callback
        entities = {model["entity"] for model in models}
        if (
            entities & {"clone-spell", "bat-spell", "skeleton-spell"}
            and register_actor is None
        ):
            raise InputError("Generated spells require kernel actor registration")
        if "clone-spell" in entities and expire_actor is None:
            raise InputError("Clone expiry requires a kernel despawn callback")
        if "revive-spell" in entities and revive_actor is None:
            raise InputError("Revive requires hero/death lifecycle reconciliation")
        if "ice-block-spell" in entities and status_callback is None:
            raise InputError(
                "Ice Block requires shared remaining-attack-work status application"
            )
        if "angry-spell" in entities and base_selector is None:
            raise InputError("Angry requires shared targeting delegation")
        self.launched, self.resolved, self.expired = set(), set(), set()
        self.spawned, self.capacity, self.clone_expiry, self.clone_counts = (
            {},
            {},
            {},
            {},
        )
        self.ice_members, self.anger_until, self.anger_inside = {}, {}, {}
        self.boundary_sides, self.crossing_hints = {}, {}
        self.last_time = None
        self._validate_reserves()

    def _validate_reserves(self):
        expected = set()
        for key, model in self.models.items():
            if model["entity"] in {"bat-spell", "skeleton-spell"}:
                for index in range(model["quantities"]["count"]):
                    identity = f"{key}:spawn:{index}"
                    expected.add(identity)
                    actor = self.actors.get(identity)
                    if (
                        actor is None
                        or actor.get("spell_generated_model")
                        != {"cast_id": key, "entity": model["entity"], "index": index}
                        or actor["spawn_seconds"] != "controlled"
                    ):
                        raise InputError(
                            "Finite spell summon reserve is missing or unowned"
                        )
            elif model["entity"] == "clone-spell":
                for request in compile_advanced_spell_reserves([model], self.actors):
                    identity = request["id"]
                    expected.add(identity)
                    actor = self.actors.get(identity)
                    if (
                        actor is None
                        or actor.get("spell_clone_model")
                        != request["spell_clone_model"]
                        or actor["spawn_seconds"] != "controlled"
                    ):
                        raise InputError("Finite Clone reserve is missing or unowned")
        actual = {
            key
            for key, actor in self.actors.items()
            if actor.get(
                "spell_generated_model", actor.get("spell_clone_model", {})
            ).get("cast_id")
            in self.models
        }
        if actual != expected:
            raise InputError(
                "Spell reserves must exactly match finite compiled ownership"
            )

    def _inside(self, model, actor):
        key = model["id"], actor["id"]
        hint = self.boundary_sides.get(key)
        point = center(actor)
        if (
            hint
            and hypot(point[0] - hint["position"][0], point[1] - hint["position"][1])
            <= EPSILON * 10
        ):
            return hint["inside_after"]
        return (
            hypot(point[0] - model["position"][0], point[1] - model["position"][1])
            <= model["radius"] + EPSILON
        )

    def _clone(self, model, time, trace):
        remaining = self.capacity.setdefault(
            model["id"], model["quantities"]["capacity"]
        )
        choices = sorted(
            (
                hypot(
                    center(a)[0] - model["position"][0],
                    center(a)[1] - model["position"][1],
                ),
                key,
            )
            for key, a in self.actors.items()
            if troop_or_hero(a)
            and a.get("healing_class") == "troop"
            and "spell_clone_model" not in a
            and _active(a, time)
            and self._inside(model, a)
        )
        for _, key in choices:
            source = self.actors[key]
            weight = integer(
                source.get("housing_space"), "Clone needs explicit troop housing", 1
            )
            while weight <= remaining:
                index = self.clone_counts.get((model["id"], key), 0)
                offsets = model["parameters"]["spawn_offsets"]
                if index >= len(offsets):
                    raise InputError(
                        "Clone exhausted explicitly declared spawn positions"
                    )
                clone_id = f"{model['id']}:clone:{key}:{index}"
                # A kernel callback recompiles the original entity with its independently
                # supported lifecycle. Copying the source dictionary would copy runtime state.
                reserve = self.actors.get(clone_id)
                if reserve is None or reserve["spawn_seconds"] != "controlled":
                    raise InputError("Clone reserve exhausted or already released")
                clone = self.register_actor(reserve, time, key)
                self._registered(clone, clone_id)
                self.clone_expiry[clone_id] = spell_clock_after(
                    time, model["quantities"]["lifespan_seconds"]
                )
                remaining -= weight
                self.clone_counts[model["id"], key] = index + 1
                self.spawned[model["id"]] = self.spawned.get(model["id"], 0) + 1
                self.capacity[model["id"]] = remaining
                trace.append(
                    {
                        "event": "spell_clone_spawn",
                        "time_seconds": time,
                        "cast_id": model["id"],
                        "actor": clone_id,
                        "source": key,
                        "remaining_capacity": remaining,
                    }
                )

    def _registered(self, actor, expected):
        if (
            not isinstance(actor, dict)
            or actor.get("id") != expected
            or self.actors.get(expected) is not actor
            or not _active(actor, self.last_time)
        ):
            raise InputError("Kernel callback did not register the generated actor")

    def prepare(self, time, trace):
        number(time, "spell runtime time", 0)
        if self.last_time is not None and time < self.last_time:
            raise InputError("Spell runtime cannot move backward")
        self.last_time = time
        for key, hint in list(self.crossing_hints.items()):
            if hint["time_seconds"] <= time:
                self.boundary_sides[key] = hint
                del self.crossing_hints[key]
        for clone_id, end in list(self.clone_expiry.items()):
            if end <= time:
                actor = self.actors[clone_id]
                self.expire_actor(actor, time)
                if _active(actor, time):
                    raise InputError("Clone despawn callback left the actor active")
                del self.clone_expiry[clone_id]
                trace.append(
                    {
                        "event": "spell_clone_expired",
                        "time_seconds": time,
                        "actor": clone_id,
                    }
                )
        # Finite dependency closure: primary releases/revivals cannot depend on
        # Clone; Clone excludes every clone reserve as a source. One ordered sweep
        # therefore reaches a fixed point before statuses capture membership.
        # Cast IDs only break ties within a phase, never decide source availability.
        for key, model in sorted(
            self.models.items(),
            key=lambda item: (
                PREPARE_PHASE[item[1]["entity"]],
                item[1]["time_seconds"],
                item[0],
            ),
        ):
            if model["time_seconds"] > time:
                continue
            if key not in self.launched:
                self.launched.add(key)
                trace.append(
                    {
                        "event": "attack_spell_cast",
                        "time_seconds": time,
                        "cast_id": key,
                        "entity": model["entity"],
                    }
                )
            arrival = model["arrival_seconds"]
            if arrival > time:
                continue
            entity, q = model["entity"], model["quantities"]
            if key not in self.resolved:
                self.resolved.add(key)
                trace.append(
                    {
                        "event": "advanced_spell_arrival",
                        "time_seconds": time,
                        "cast_id": key,
                    }
                )
                if entity == "ice-block-spell":
                    self.ice_members[key] = {
                        actor_id
                        for actor_id, a in self.actors.items()
                        if troop_or_hero(a)
                        and _active(a, time)
                        and self._inside(model, a)
                    }
                if entity == "revive-spell":
                    choices = sorted(
                        (
                            hypot(
                                center(a)[0] - model["position"][0],
                                center(a)[1] - model["position"][1],
                            ),
                            actor_id,
                        )
                        for actor_id, a in self.actors.items()
                        if troop_or_hero(a)
                        and "hero_model" in a
                        and a["hp"] <= 0
                        and a["spawn_seconds"] != "controlled"
                        and a["spawn_seconds"] <= time + EPSILON
                        and not a.get("_recalled")
                        and self._inside(model, a)
                    )
                    if choices:
                        actor = self.actors[choices[0][1]]
                        self.revive_actor(
                            actor,
                            q["health_fraction"],
                            time,
                            model["parameters"]["revive_state"],
                        )
                        if not _active(actor, time):
                            raise InputError(
                                "Revive callback failed to restore active hero combat"
                            )
                        trace.append(
                            {
                                "event": "spell_hero_revived",
                                "time_seconds": time,
                                "cast_id": key,
                                "actor": actor["id"],
                                "hp": actor["hp"],
                            }
                        )
            if entity in {"bat-spell", "skeleton-spell"}:
                index = self.spawned.get(key, 0)
                interval = model["parameters"]["spawn_interval_seconds"]
                while (
                    index < q["count"]
                    and spell_clock_after(arrival, index * interval) <= time
                ):
                    reserve = self.actors[f"{key}:spawn:{index}"]
                    actor = self.register_actor(reserve, time, None)
                    self._registered(actor, reserve["id"])
                    index += 1
                    self.spawned[key] = index
                    trace.append(
                        {
                            "event": "spell_unit_spawn",
                            "time_seconds": time,
                            "cast_id": key,
                            "actor": actor["id"],
                        }
                    )
            elif entity == "clone-spell" and time < spell_clock_after(
                arrival, q["duration_seconds"]
            ):
                self._clone(model, time, trace)
            elif entity == "angry-spell":
                live = time < spell_clock_after(arrival, q["duration_seconds"])
                for actor in self.actors.values():
                    member = key, actor["id"]
                    eligible = troop_or_hero(actor) and _active(actor, time)
                    inside = live and eligible and self._inside(model, actor)
                    if inside:
                        self.anger_until[member] = spell_clock_after(
                            time, q["anger_seconds"]
                        )
                    elif self.anger_inside.get(member, False) and eligible:
                        self.anger_until[member] = spell_clock_after(
                            min(
                                time, spell_clock_after(arrival, q["duration_seconds"])
                            ),
                            q["anger_seconds"],
                        )
                    elif not troop_or_hero(actor):
                        # Recall/death/undeployment suppress membership, not the
                        # absolute status clock retained for return or revival.
                        self.anger_until.pop(member, None)
                    self.anger_inside[member] = inside
            if (
                "duration_seconds" in q
                and time >= spell_clock_after(arrival, q["duration_seconds"])
                and key not in self.expired
            ):
                self.expired.add(key)
                trace.append(
                    {
                        "event": "advanced_spell_field_expired",
                        "time_seconds": time,
                        "cast_id": key,
                    }
                )
        self._statuses(time, trace)

    def _statuses(self, time, trace):
        for actor in self.actors.values():
            pauses, reductions, bonuses = [], [], []
            for key, members in self.ice_members.items():
                model = self.models[key]
                end = spell_clock_after(
                    model["arrival_seconds"], model["quantities"]["duration_seconds"]
                )
                if actor["id"] in members and end > time:
                    pauses.append(end)
                    reductions.append(model["quantities"]["incoming_damage_multiplier"])
            for (key, actor_id), end in self.anger_until.items():
                if actor_id == actor["id"] and end > time:
                    bonuses.append(self.models[key]["quantities"]["movement_bonus"])
            angry = bool(bonuses) and _active(actor, time)
            if angry != actor.get("_spell_defense_priority", False):
                actor["target"] = None
                actor.pop("_remaining_path", None)
                actor.pop("_path_signature", None)
                trace.append(
                    {
                        "event": "spell_priority_changed",
                        "time_seconds": time,
                        "actor": actor["id"],
                        "defenses_first": angry,
                    }
                )
            # Kernel consumes these independently; no overwriting hero/rage/freeze state.
            new_pause = max(pauses, default=0)
            old_pause = actor.get("_spell_pause_until", 0)
            if new_pause != old_pause and self.status_callback is not None:
                self.status_callback(actor, time, old_pause, new_pause)
            actor["_spell_pause_until"] = new_pause
            actor["_spell_incoming_damage_multiplier"] = min(reductions, default=1)
            actor["_spell_movement_bonus"] = max(bonuses, default=0) if angry else 0
            actor["_spell_defense_priority"] = angry
        for key, end in list(self.anger_until.items()):
            if end <= time:
                del self.anger_until[key]

    def select_target(self, actor, actors, time, blocked, width, height):
        """Angry adds a defense tier and delegates all eligibility/routing."""
        if self.base_selector is None:
            raise InputError("Angry targeting requires the shared base selector")
        if not actor.get("_spell_defense_priority"):
            return self.base_selector(actor, actors, time, blocked, width, height)
        original = actor.get("target_priority_tiers")
        ranks = actor.get("_target_ranks")
        if ranks is None:
            raise InputError("Angry requires kernel-initialized target ranks")
        allowed = actor["target_priorities"]
        if "defense" not in allowed:
            raise InputError(
                "Angry cannot override a weapon incapable of targeting defenses"
            )
        actor["target_priority_tiers"] = [
            ["defense"],
            *(deepcopy(original) if original else [list(allowed)]),
        ]
        actor["_target_ranks"] = {
            kind: 0 if kind == "defense" else rank + 1 for kind, rank in ranks.items()
        }
        retained = actors.get(actor.get("target"))
        if retained is not None and retained["kind"] != "defense":
            actor["target"] = None
        try:
            return self.base_selector(actor, actors, time, blocked, width, height)
        finally:
            actor["_target_ranks"] = ranks
            if original is None:
                actor.pop("target_priority_tiers", None)
            else:
                actor["target_priority_tiers"] = original

    def jump_wall_cells(self, actor, time):
        """Per-actor collision exemption; retains every building footprint."""
        if (
            not troop_or_hero(actor)
            or actor["movement"] != "ground"
            or not _active(actor, time)
        ):
            return set()
        cells = set()
        for key in self.resolved:
            model = self.models[key]
            if model["entity"] != "jump-spell" or time >= spell_clock_after(
                model["arrival_seconds"], model["quantities"]["duration_seconds"]
            ):
                continue
            for wall in self.actors.values():
                if (
                    wall["kind"] == "wall"
                    and wall["team"] != actor["team"]
                    and _active(wall, time)
                    and self._inside(model, wall)
                ):
                    cells.add((wall["x"], wall["y"]))
        return cells

    def next_boundary(self, time):
        boundaries = list(self.clone_expiry.values()) + list(self.anger_until.values())
        for key, model in self.models.items():
            boundaries.extend([model["time_seconds"], model["arrival_seconds"]])
            q = model["quantities"]
            if "duration_seconds" in q:
                boundaries.append(
                    spell_clock_after(model["arrival_seconds"], q["duration_seconds"])
                )
            if (
                model["entity"] in {"bat-spell", "skeleton-spell"}
                and self.spawned.get(key, 0) < q["count"]
            ):
                boundaries.append(
                    spell_clock_after(
                        model["arrival_seconds"],
                        self.spawned.get(key, 0)
                        * model["parameters"]["spawn_interval_seconds"],
                    )
                )
        return min((value for value in boundaries if value > time), default=None)

    def first_crossing_delay(
        self, actor, route, time, horizon, effective_speed, forced_motion=False
    ):
        """Exact motion contacts for Clone/Angry; caller must split at this delay."""
        if not troop_or_hero(actor) or effective_speed <= EPSILON:
            return None
        earliest = None
        for key in self.resolved:
            model = self.models[key]
            if (
                model["entity"] not in {"clone-spell", "angry-spell"}
                or key in self.expired
            ):
                continue
            self.crossing_hints.pop((key, actor["id"]), None)
            point, traveled = center(actor), 0
            for endpoint in route:
                length = hypot(endpoint[0] - point[0], endpoint[1] - point[1])
                for contact, inside_after in _circle_events(
                    point, endpoint, model["position"], model["radius"]
                ):
                    delay = (traveled + contact) / effective_speed
                    if delay > horizon:
                        continue
                    if delay <= 0:
                        if self._inside(model, actor) == inside_after:
                            continue
                        delay = nextafter(time, inf) - time
                    if time + delay <= time:
                        delay = nextafter(time, inf) - time
                    if delay > horizon:
                        continue
                    if earliest is None or delay < earliest:
                        earliest = delay
                    fraction = contact / length if length > EPSILON else 0
                    self.crossing_hints[key, actor["id"]] = {
                        "time_seconds": time + delay,
                        "position": (
                            point[0] + (endpoint[0] - point[0]) * fraction,
                            point[1] + (endpoint[1] - point[1]) * fraction,
                        ),
                        "inside_after": inside_after,
                    }
                    break
                else:
                    traveled += length
                    point = endpoint
                    continue
                break
        return earliest

    def continuation_reasons(self, time):
        facts = []
        for key in self.launched:
            model = self.models[key]
            if (
                model["entity"] in {"bat-spell", "skeleton-spell"}
                and self.spawned.get(key, 0) < model["quantities"]["count"]
            ):
                facts.append(
                    continuation_fact(
                        "pending_release",
                        "spell:" + key,
                        not_before_seconds=spell_clock_after(
                            model["arrival_seconds"],
                            self.spawned.get(key, 0)
                            * model["parameters"]["spawn_interval_seconds"],
                        ),
                    )
                )
            elif model["entity"] == "revive-spell" and key not in self.resolved:
                eligible = [
                    actor["id"]
                    for actor in self.actors.values()
                    if troop_or_hero(actor)
                    and "hero_model" in actor
                    and actor["hp"] <= 0
                    and actor["spawn_seconds"] != "controlled"
                    and actor["spawn_seconds"] <= time
                    and not actor.get("_recalled")
                    and self._inside(model, actor)
                ]
                if eligible:
                    facts.append(
                        continuation_fact(
                            "latent_attacker",
                            "spell:" + key,
                            eligible,
                            not_before_seconds=model["arrival_seconds"],
                        )
                    )
        return facts

    def result(self):
        return {
            "launched": sorted(self.launched),
            "resolved": sorted(self.resolved),
            "expired_fields": sorted(self.expired),
            "generated_counts": dict(self.spawned),
            "remaining_clone_capacity": dict(self.capacity),
            "clone_expiry": dict(self.clone_expiry),
            "status": "opt_in_experimental_permanent_spells_v1",
        }


def armor_damage(actor, amount):
    """Opt-in one-hit shield: overflow from the breaking hit is discarded."""
    number(amount, "shield damage", 0)
    armor = actor.get("_spell_armor_hp", 0)
    if armor > 0 and amount > 0:
        actor["_spell_armor_hp"] = max(armor - amount, 0)
        return 0
    return amount
