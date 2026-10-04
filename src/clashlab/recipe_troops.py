"""Recipe troop lifecycles under complete, explicitly uncalibrated contracts.

Catalog values are compiled once. Geometry, clocks and unresolved game behavior
are separate scenario inputs; nothing in this module is an implicit fallback.
"""

from collections import defaultdict
from copy import deepcopy
from math import floor, hypot

from .common import InputError, identifier, integer, number, require
from .battle_termination import continuation_fact
from .damage_receipts import record_damage
from .hit_status import validate_hit_status
from .rates import rescale_remaining_cooldown
from .spatial import EPSILON, _active, _ground_route, center, target_distance
from .spell_visibility import untargetable_until


RECIPE_TROOPS = frozenset(
    {
        "balloon",
        "rocket-balloon",
        "baby-dragon",
        "headhunter",
        "super-wall-breaker",
        "super-barbarian",
        "apprentice-warden",
    }
)
RECIPE_ADAPTERS = {
    "balloon": ("air", "radial"),
    "rocket-balloon": ("air", "radial"),
    "baby-dragon": ("air", "radial"),
    "headhunter": ("ground", "single"),
    "super-wall-breaker": ("ground", "radial"),
    "super-barbarian": ("ground", "single"),
    "apprentice-warden": ("ground", "single"),
}
BASE_FIELDS = {"source", "status", "stacking"}
EXTRA_FIELDS = {
    "balloon": {"death_radius_tiles", "death_delay_seconds", "death_scaling"},
    "rocket-balloon": {
        "death_radius_tiles",
        "death_delay_seconds",
        "death_scaling",
        "boost_duration_seconds",
        "boost_movement_multiplier",
        "boost_clock",
    },
    "baby-dragon": {
        "friendly_air_radius_tiles",
        "sample_interval_seconds",
        "membership",
        "sample_clock",
        "friendly_air_classes",
    },
    "headhunter": {
        "targeting",
        "target_layers",
        "slow_duration_seconds",
        "protection_policy",
        "poison_duration_seconds",
        "poison_interval_seconds",
        "poison_ramp_seconds",
        "poison_refresh",
        "poison_stacking",
        "poison_scaling",
        "poison_targets",
    },
    "super-wall-breaker": {
        "death_radius_tiles",
        "death_delay_seconds",
        "death_scaling",
        "wall_damage_multiplier",
        "targeting",
        "detonation",
    },
    "super-barbarian": {
        "boost_duration_seconds",
        "boost_movement_multiplier",
        "boost_clock",
        "boost_damage_multiplier",
    },
    "apprentice-warden": {
        "sample_interval_seconds",
        "sample_clock",
        "aura_membership",
        "aura_classes",
        "aura_stacking",
        "aura_health_accounting",
        "aura_source_loss",
        "aura_self",
        "other_life_aura",
        "following",
        "follow_classes",
        "follow_distance_tiles",
        "hero_housing_weight",
        "target_adoption",
        "no_follow_target",
    },
}


def _exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != fields:
        raise InputError(f"{label} requires exactly its complete declared fields")


def validate_recipe_parameters(entity_id, parameters):
    if entity_id not in RECIPE_TROOPS:
        raise InputError("Unsupported recipe troop; no generic fallback")
    _exact(parameters, BASE_FIELDS | EXTRA_FIELDS[entity_id], entity_id)
    identifier(parameters["source"], "recipe behavior source")
    choices = {
        "status": "explicit_uncalibrated_hypothesis",
        "stacking": "multiply_independent_shared_factors",
        "death_scaling": "catalog_damage_times_scenario_modifier_no_temporary_buffs",
        "boost_clock": "elapsed_since_deployment_including_freeze",
        "membership": "sampled_center_distance_inclusive_hold_all_lifecycle_changes",
        "sample_clock": "deployment_anchored_resample_on_reactivation",
        "poison_refresh": "refresh_expiry_preserve_ramp_and_tick_clock",
        "poison_stacking": "additive_per_source_explicit_hypothesis",
        "poison_scaling": "catalog_max_dps_times_scenario_modifier_no_temporary_buffs",
        "poison_targets": "enemy_units_only_including_heroes",
        "detonation": "attack_packet_then_consume_then_one_death_blast",
        "aura_membership": "sampled_center_distance_inclusive",
        "aura_stacking": "strongest_apprentice_percentage_per_recipient",
        "aura_health_accounting": "preserve_current_hp_fraction_on_entry_and_exit",
        "aura_source_loss": "remove_immediately_on_death_or_inactivity",
        "aura_self": "exclude_all_apprentice_wardens",
        "other_life_aura": "reject_life_gem_or_unknown_life_aura_composition",
        "following": "largest_housing_cluster_then_distance_then_id_sampled",
        "target_adoption": "leader_target_only_if_already_in_weapon_range_else_follow",
        "no_follow_target": "shared_ordinary_enemy_selection",
    }
    for field, expected in choices.items():
        if field in parameters and parameters[field] != expected:
            raise InputError(f"Unsupported recipe {field}")
    for field in (
        "death_radius_tiles",
        "boost_duration_seconds",
        "boost_movement_multiplier",
        "friendly_air_radius_tiles",
        "slow_duration_seconds",
        "poison_duration_seconds",
        "poison_interval_seconds",
        "boost_damage_multiplier",
        "wall_damage_multiplier",
    ):
        if field in parameters:
            number(parameters[field], field, EPSILON)
    for field in ("death_delay_seconds", "poison_ramp_seconds"):
        if field in parameters:
            number(parameters[field], field, 0)
    if entity_id in {"baby-dragon", "apprentice-warden"}:
        number(parameters["sample_interval_seconds"], "troop sample interval", 0.001)
    if entity_id == "baby-dragon":
        classes = parameters["friendly_air_classes"]
        if (
            not isinstance(classes, list)
            or not classes
            or len(classes) != len(set(classes))
            or not set(classes) <= {"troop", "hero", "pet", "siege", "guardian"}
        ):
            raise InputError("Baby Dragon friendly-air classes must be explicit")
    if entity_id == "apprentice-warden":
        for field in ("aura_classes", "follow_classes"):
            classes = parameters[field]
            if (
                not isinstance(classes, list)
                or not classes
                or len(classes) != len(set(classes))
                or not set(classes) <= {"troop", "hero", "pet", "siege", "guardian"}
            ):
                raise InputError("Apprentice Warden classes must be explicit")
        number(
            parameters["follow_distance_tiles"],
            "Apprentice following distance",
            EPSILON,
        )
        number(parameters["hero_housing_weight"], "hero follow weight", EPSILON)
    if entity_id == "headhunter":
        if parameters["targeting"] != "visible_live_heroes_before_other_targets":
            raise InputError("Unsupported Headhunter targeting")
        if parameters["target_layers"] != ["ground", "air"]:
            raise InputError("Headhunter requires its explicit ground-and-air branch")
        if parameters["protection_policy"] not in {
            "damage_immunity_does_not_block_status",
            "damage_immunity_also_blocks_status",
        }:
            raise InputError("Unsupported Headhunter protection policy")
        if (
            parameters["poison_interval_seconds"]
            > parameters["poison_duration_seconds"]
        ):
            raise InputError("Poison duration must contain at least one complete pulse")
    if entity_id == "super-wall-breaker":
        if (
            parameters["targeting"]
            != "nearest_reachable_wall_then_structures_hypothesis"
        ):
            raise InputError(
                "Wall compartment selection requires an explicit hypothesis"
            )


def _death_model(actor, entity_id, stats, parameters, modifiers):
    source = parameters["source"]
    amount = number(require(stats, "deathDamage"), "catalog death damage", 0)
    amount *= modifiers["damage_multiplier"]
    partitions = [("structures", ["unit", "defense", "building"], 1)]
    if entity_id == "super-wall-breaker":
        partitions.append(("walls", ["wall"], parameters["wall_damage_multiplier"]))
    effects = []
    for suffix, kinds, multiplier in partitions:
        effects.append(
            {
                "id": f"{entity_id}-death-{suffix}",
                "source": source,
                "kind": "area_damage",
                "delay_seconds": parameters["death_delay_seconds"],
                "amount": amount * multiplier,
                "area": {
                    "offset_x": 0,
                    "offset_y": 0,
                    "radius": parameters["death_radius_tiles"],
                    "target_team": "defense",
                    "target_kinds": kinds,
                    "target_layers": ["ground"],
                },
            }
        )
    actor["death_model"] = {
        "kind": "fixed_area_sequence_at_death",
        "geometry": "offsets_from_source_center_at_death",
        "source": source,
        "effects": effects,
    }


def compile_recipe_troop(actor, instance, entity, row, modifiers):
    """Attach after ordinary catalog statistics and explicit attack geometry.

    The registry must select RECIPE_ADAPTERS and require lifecycle/hit-status/wall
    support. Headhunter's scenario defending-unit response is bound afterwards.
    """
    entity_id = require(instance, "entity")
    parameters = deepcopy(require(instance, "recipe_parameters"))
    validate_recipe_parameters(entity_id, parameters)
    movement, pattern = RECIPE_ADAPTERS[entity_id]
    if (
        entity.get("id") != entity_id
        or entity.get("category") != "troop"
        or actor.get("entity_adapter", {}).get("entity") != entity_id
        or actor.get("team") != "attack"
        or actor.get("kind") != "unit"
        or actor.get("movement") != movement
        or actor.get("layer") != movement
        or actor.get("attack_model", {}).get("kind") != pattern
        or instance.get("statistics_mode", "normal") != "normal"
    ):
        raise InputError(
            "Recipe troop requires matching normal catalog actor and weapon"
        )
    if actor["attack_model"]["maximum_hp_fraction"] != 0:
        raise InputError("Recipe troop cannot hide maximum-HP damage")
    stats = require(require(row, "stats"), "normal")
    statistics = {}
    layers = (
        ["ground", "air"]
        if entity_id in {"baby-dragon", "headhunter", "apprentice-warden"}
        else ["ground"]
    )
    actor["target_layers"] = layers
    actor["attack_model"]["target_layers"] = list(layers)
    actor["spring_class"] = "troop"
    actor["housing_space"] = integer(
        require(entity, "housingSpace"), "catalog housing", 1
    )
    if entity_id in {"balloon", "rocket-balloon", "super-wall-breaker"}:
        _death_model(actor, entity_id, stats, parameters, modifiers)
        actor["target_priority_tiers"] = [["defense"], ["building"]]
    if entity_id == "baby-dragon":
        enraged = require(row["stats"], "enraged")
        normal_hit = number(require(stats, "damagePerShot"), "normal hit", EPSILON)
        normal_dps = number(require(stats, "dps"), "normal DPS", EPSILON)
        rage_hit = number(require(enraged, "damagePerShot"), "enraged hit", EPSILON)
        rage_dps = number(require(enraged, "dps"), "enraged DPS", EPSILON)
        statistics = {
            "damage_multiplier": rage_hit / normal_hit,
            "attack_rate_multiplier": (rage_dps / rage_hit) / (normal_dps / normal_hit),
        }
    if entity_id == "apprentice-warden":
        statistics = {
            "aura_radius": number(
                require(entity, "auraRange"), "catalog Life Aura radius", EPSILON
            ),
            "aura_hp_fraction": number(
                require(row, "auraHpIncrease"), "catalog Life Aura percent", EPSILON
            )
            / 100,
        }
        wall = require(instance, "wall_parameters")
        _exact(wall, {"kind", "source"}, "Apprentice Warden wall traversal")
        if wall["kind"] not in {"avoid", "jump_enemy_walls"}:
            raise InputError(
                "Apprentice following requires explicit avoid or jump policy"
            )
        identifier(wall["source"], "Apprentice wall policy source")
        actor["wall_behavior"] = deepcopy(wall)
    if entity_id == "headhunter":
        statistics = {
            "hero_damage_multiplier": number(
                require(stats, "dpsOnHeroes"), "hero DPS", 0
            )
            / number(require(stats, "dps"), "normal DPS", EPSILON),
            "poison_max_dps": number(require(row, "poisonMaxDps"), "poison max DPS", 0)
            * modifiers["damage_multiplier"],
        }
        actor["on_hit_status"] = {
            "source": parameters["source"],
            "duration_seconds": parameters["slow_duration_seconds"],
            "attack_rate_multiplier": 1
            - number(
                require(row, "poisonAttackRateDecrease"),
                "poison attack slow",
                0,
                99.999,
            )
            / 100,
            "movement_multiplier": 1
            - number(
                require(row, "poisonSpeedDecrease"), "poison movement slow", 0, 99.999
            )
            / 100,
            "protection_policy": parameters["protection_policy"],
        }
        validate_hit_status(actor["on_hit_status"])
        wall = require(instance, "wall_parameters")
        _exact(wall, {"kind", "source"}, "Headhunter jump")
        if wall["kind"] != "jump_enemy_walls":
            raise InputError("Headhunter requires enemy-wall traversal")
        identifier(wall["source"], "Headhunter wall source")
        actor["wall_behavior"] = deepcopy(wall)
    if entity_id == "super-wall-breaker":
        actor["target_priorities"] = ["wall", "defense", "building"]
        actor["target_priority_tiers"] = [["wall"], ["defense", "building"]]
        actor["attack_model"]["target_kinds"] = list(actor["target_priorities"])
        projectile = actor["attack_model"]["projectile"]
        if (
            projectile.get("timing") != "instant"
            or projectile.get("delay_seconds") != 0
        ):
            raise InputError(
                "Super Wall Breaker requires an instant source-centered blast"
            )
        actor["attack_model"]["kind"] = "source_radial"
        projectile.update(
            destination="fixed_source_center_at_launch",
            inactive_primary_policy="resolve_at_fixed_launch_position",
        )
        wall = require(instance, "wall_parameters")
        _exact(wall, {"kind", "source"}, "Super Wall Breaker wall routing")
        if wall["kind"] != "avoid":
            raise InputError(
                "Wall Breaker targets walls; it cannot use a second wall weapon"
            )
        identifier(wall["source"], "Super Wall Breaker wall source")
        actor["wall_behavior"] = deepcopy(wall)
    actor["recipe_troop_model"] = {
        "entity": entity_id,
        "source": actor["source"],
        "parameters": parameters,
        "statistics": statistics,
    }
    actor["entity_adapter"]["recipe_behavior"] = deepcopy(actor["recipe_troop_model"])
    return actor


def _hero(target):
    return "defending_hero_model" in target or "hero_model" in target


def recipe_target_eligible(actor, target):
    """Additional eligibility only; shared life/visibility/layer gates still apply."""
    preferred = actor.get("_recipe_priority_targets")
    return not preferred or target["id"] in preferred


def recipe_damage_multiplier(source, target):
    """Target-specific factor, applied once to each ordinary weapon impact."""
    model = source.get("recipe_troop_model", {})
    if model.get("entity") == "headhunter" and _hero(target):
        return model["statistics"]["hero_damage_multiplier"]
    if model.get("entity") == "super-wall-breaker" and target["kind"] == "wall":
        return model["parameters"]["wall_damage_multiplier"]
    return 1


def recipe_status_eligible(source, target):
    """Headhunter poison slow cannot silently affect structures."""
    return source.get("recipe_troop_model", {}).get("entity") != "headhunter" or (
        target["kind"] == "unit" and target["team"] != source["team"]
    )


class RecipeTroopCombat:
    """Deployment boosts, sampled isolation, poison and one-shot consumption."""

    def __init__(self, actors):
        self.actors = actors
        self.models = {}
        self.samples = {}
        self.consumed = set()
        self.poison = {}
        self.events = []
        self.apprentices = {}
        self.base_selector = None
        for key, actor in actors.items():
            if "recipe_troop_model" not in actor:
                continue
            model = deepcopy(actor["recipe_troop_model"])
            _exact(
                model,
                {"entity", "source", "parameters", "statistics"},
                "Recipe troop model",
            )
            entity_id = model["entity"]
            validate_recipe_parameters(entity_id, model["parameters"])
            identifier(model["source"], "recipe statistic source")
            movement, _ = RECIPE_ADAPTERS[entity_id]
            if (
                actor.get("entity_adapter", {}).get("entity") != entity_id
                or actor["kind"] != "unit"
                or actor["team"] != "attack"
                or actor["movement"] != movement
                or actor["layer"] != movement
            ):
                raise InputError("Recipe runtime ownership mismatch")
            fields = (
                {"damage_multiplier", "attack_rate_multiplier"}
                if entity_id == "baby-dragon"
                else (
                    {"hero_damage_multiplier", "poison_max_dps"}
                    if entity_id == "headhunter"
                    else (
                        {"aura_radius", "aura_hp_fraction"}
                        if entity_id == "apprentice-warden"
                        else set()
                    )
                )
            )
            _exact(model["statistics"], fields, "Recipe troop statistics")
            for name, value in model["statistics"].items():
                number(value, name, EPSILON)
            if entity_id == "headhunter":
                if "unit" not in actor["target_priorities"]:
                    raise InputError(
                        "Headhunter requires explicit defending-unit targeting"
                    )
                validate_hit_status(require(actor, "on_hit_status"))
            self.models[key] = model
            if entity_id == "apprentice-warden":
                self.apprentices[key] = {"next": None, "members": [], "leader": None}
        if self.apprentices and any(
            item.get("entity") == "life-gem"
            for actor in actors.values()
            for item in actor.get("hero_model", {}).get("equipment", [])
        ):
            raise InputError(
                "Apprentice Warden/Life Gem composition needs an additional contract"
            )

    def _sample(self, key, actor, model, time):
        parameters = model["parameters"]
        interval = parameters["sample_interval_seconds"]
        state = self.samples.get(key)
        if state is not None and time + EPSILON < state["next"]:
            return state["isolated"]
        if state is not None and state["next"] < time - EPSILON:
            raise InputError("Baby Dragon isolation sample boundary was skipped")
        nearby = []
        for other in self.actors.values():
            air_class = (
                "pet"
                if "pet_model" in other
                else (
                    "hero"
                    if "hero_model" in other
                    else other.get(
                        "buff_class",
                        other.get("healing_class", other.get("spring_class")),
                    )
                )
            )
            if (
                other["id"] == key
                or not _active(other, time)
                or other["team"] != actor["team"]
                or other["kind"] != "unit"
                or other["layer"] != "air"
                or other.get("_pet_phoenix_egg", False)
                or air_class not in parameters["friendly_air_classes"]
            ):
                continue
            first, second = center(actor), center(other)
            if (
                hypot(first[0] - second[0], first[1] - second[1])
                <= parameters["friendly_air_radius_tiles"] + EPSILON
            ):
                nearby.append(other["id"])
        tick = floor((time - actor["spawn_seconds"] + EPSILON) / interval)
        self.samples[key] = {
            "next": actor["spawn_seconds"] + (tick + 1) * interval,
            "isolated": not nearby,
            "nearby": sorted(nearby),
        }
        return not nearby

    def prepare(self, time, trace):
        for key, model in sorted(self.models.items()):
            actor = self.actors[key]
            active = _active(actor, time)
            damage, attack, movement = 1, 1, 1
            entity_id = model["entity"]
            parameters = model["parameters"]
            if not active:
                self.samples.pop(key, None)
            elif entity_id == "baby-dragon" and self._sample(key, actor, model, time):
                damage = model["statistics"]["damage_multiplier"]
                attack = model["statistics"]["attack_rate_multiplier"]
            elif entity_id in {"rocket-balloon", "super-barbarian"}:
                if (
                    time
                    < actor["spawn_seconds"]
                    + parameters["boost_duration_seconds"]
                    - EPSILON
                ):
                    movement = parameters["boost_movement_multiplier"]
                    damage = parameters.get("boost_damage_multiplier", 1)
            if entity_id == "headhunter":
                actor["_recipe_priority_targets"] = sorted(
                    target["id"]
                    for target in self.actors.values()
                    if active
                    and _hero(target)
                    and _active(target, time)
                    and target["team"] != actor["team"]
                    and target["layer"] in actor["target_layers"]
                    and untargetable_until(target) <= time + EPSILON
                )
            old = (
                actor.get("_recipe_damage_multiplier", 1),
                actor.get("_recipe_attack_rate", 1),
                actor.get("_recipe_movement_multiplier", 1),
            )
            current = damage, attack, movement
            if old[1] != attack:
                rescale_remaining_cooldown(actor, time, old[1], attack)
            actor["_recipe_damage_multiplier"] = damage
            actor["_recipe_attack_rate"] = attack
            actor["_recipe_movement_multiplier"] = movement
            if current != old:
                event = {
                    "event": "recipe_troop_state",
                    "time_seconds": time,
                    "source": key,
                    "damage_multiplier": damage,
                    "attack_rate_multiplier": attack,
                    "movement_multiplier": movement,
                }
                trace.append(event)
                self.events.append(deepcopy(event))
        if self.apprentices:
            self._prepare_apprentices(time, trace)

    @staticmethod
    def _class(actor):
        if "pet_model" in actor:
            return "pet"
        if _hero(actor):
            return "hero"
        return actor.get(
            "buff_class", actor.get("healing_class", actor.get("spring_class"))
        )

    def _apprentice_eligible(self, source, target, classes, time):
        return (
            target["id"] not in self.apprentices
            and _active(target, time)
            and target["team"] == source["team"]
            and target["kind"] == "unit"
            and self._class(target) in classes
            and not target.get("_pet_phoenix_egg", False)
        )

    @staticmethod
    def _distance(first, second):
        a, b = center(first), center(second)
        return hypot(a[0] - b[0], a[1] - b[1])

    def _prepare_apprentices(self, time, trace):
        for key, state in self.apprentices.items():
            source = self.actors[key]
            model = self.models[key]
            parameters = model["parameters"]
            if not _active(source, time):
                state.update(next=None, members=[], leader=None)
                continue
            if state["next"] is not None and state["next"] > time + EPSILON:
                continue
            if state["next"] is not None and state["next"] < time - EPSILON:
                raise InputError("Apprentice aura/follow sample boundary was skipped")
            radius = model["statistics"]["aura_radius"]
            state["members"] = sorted(
                target["id"]
                for target in self.actors.values()
                if self._apprentice_eligible(
                    source, target, parameters["aura_classes"], time
                )
                and self._distance(source, target) <= radius + EPSILON
            )
            followers = [
                target
                for target in self.actors.values()
                if self._apprentice_eligible(
                    source, target, parameters["follow_classes"], time
                )
            ]
            weights = {}
            for target in followers:
                weight = (
                    parameters["hero_housing_weight"]
                    if self._class(target) == "hero"
                    else require(target, "housing_space")
                )
                weights[target["id"]] = number(
                    weight, "army following housing weight", EPSILON
                )
            leader = min(
                followers,
                key=lambda target: (
                    -sum(
                        weights[other["id"]]
                        for other in followers
                        if self._distance(target, other) <= radius + EPSILON
                    ),
                    self._distance(source, target),
                    target["id"],
                ),
                default=None,
            )
            state["leader"] = leader["id"] if leader else None
            interval = parameters["sample_interval_seconds"]
            tick = floor((time - source["spawn_seconds"] + EPSILON) / interval)
            state["next"] = source["spawn_seconds"] + (tick + 1) * interval
        bonuses = defaultdict(float)
        for key, state in self.apprentices.items():
            for target_id in state["members"]:
                if _active(self.actors[target_id], time):
                    bonuses[target_id] = max(
                        bonuses[target_id],
                        self.models[key]["statistics"]["aura_hp_fraction"],
                    )
        for key, actor in self.actors.items():
            old = actor.get("_recipe_life_hp_multiplier", 1)
            new = 1 + bonuses[key] if _active(actor, time) else 1
            if abs(old - new) <= EPSILON:
                continue
            # Scale both quantities together; repeated membership cycles cannot
            # manufacture healing or resurrect an actor at zero health.
            actor["maximum_hp"] *= new / old
            actor["hp"] *= new / old
            actor["_recipe_life_hp_multiplier"] = new
            event = {
                "event": "apprentice_life_aura",
                "time_seconds": time,
                "target": key,
                "maximum_hp": actor["maximum_hp"],
                "hp": actor["hp"],
                "multiplier": new,
            }
            trace.append(event)
            self.events.append(deepcopy(event))

    def select_target(self, actor, actors, time, blocked, width, height):
        if self.base_selector is None:
            raise InputError(
                "Recipe troop target selector must be bound to the shared selector"
            )
        state = self.apprentices.get(actor["id"])
        if state is None:
            return self.base_selector(actor, actors, time, blocked, width, height)
        if not _active(actor, time):
            return None, None
        leader = actors.get(state["leader"])
        if leader is None or not _active(leader, time):
            return self.base_selector(actor, actors, time, blocked, width, height)
        target = actors.get(leader.get("target"))
        if (
            target is not None
            and _active(target, time)
            and target["team"] != actor["team"]
            and target["kind"] in actor["target_priorities"]
            and target["layer"] in actor["target_layers"]
            and untargetable_until(target) <= time + EPSILON
            and target_distance(center(actor), target) <= actor["range"] + EPSILON
        ):
            actor["target"] = target["id"]
            return target, []
        actor["target"] = None
        planning = dict(actor)
        planning["range"] = self.models[actor["id"]]["parameters"][
            "follow_distance_tiles"
        ]
        solid = blocked
        if actor["wall_behavior"]["kind"] == "jump_enemy_walls":
            solid = blocked - {
                (target["x"], target["y"])
                for target in actors.values()
                if target["kind"] == "wall"
                and target["team"] != actor["team"]
                and _active(target, time)
            }
        return None, _ground_route(planning, leader, solid, width, height)

    def launched(self, source_id, time, trace):
        if self.models.get(source_id, {}).get("entity") != "super-wall-breaker":
            return
        if source_id in self.consumed:
            raise InputError("Super Wall Breaker attempted to release a second attack")
        actor = self.actors[source_id]
        if not _active(actor, time):
            raise InputError("Inactive Super Wall Breaker cannot release an attack")
        self.consumed.add(source_id)
        actor["hp"] = 0
        actor["death_time"] = time
        actor["target"] = None
        trace.append(
            {
                "event": "recipe_troop_consumed",
                "time_seconds": time,
                "source": source_id,
                "reason": "super_wall_breaker_attack_release",
            }
        )

    def impact(self, packet, target, actors, time, trace):
        model = self.models.get(packet["source"])
        if (
            model is None
            or model["entity"] != "headhunter"
            or target["kind"] != "unit"
            or not _active(target, time)
        ):
            return
        parameters = model["parameters"]
        if (
            parameters["protection_policy"] == "damage_immunity_also_blocks_status"
            and target["immune_until"] > time + EPSILON
        ):
            return
        key = packet["source"], target["id"]
        exposure = self.poison.get(key)
        if exposure is None or exposure["expiry"] < time - EPSILON:
            exposure = {
                "start": time,
                "last": time,
                "next": time + parameters["poison_interval_seconds"],
            }
            self.poison[key] = exposure
        exposure["expiry"] = time + parameters["poison_duration_seconds"]
        trace.append(
            {
                "event": "headhunter_poison_apply",
                "time_seconds": time,
                "source": key[0],
                "target": key[1],
                "expires_at": exposure["expiry"],
            }
        )

    def resolve(self, time, trace):
        damage = defaultdict(float)
        for key, exposure in list(sorted(self.poison.items())):
            source_id, target_id = key
            target = self.actors[target_id]
            if not _active(target, time):
                del self.poison[key]
                continue
            scheduled = min(exposure["next"], exposure["expiry"])
            if scheduled > time + EPSILON:
                continue
            if scheduled < time - EPSILON:
                raise InputError("Headhunter poison damage boundary was skipped")
            model = self.models[source_id]
            parameters = model["parameters"]
            ramp = parameters["poison_ramp_seconds"]
            factor = min((time - exposure["start"]) / ramp, 1) if ramp else 1
            requested = (
                model["statistics"]["poison_max_dps"]
                * factor
                * (time - exposure["last"])
            )
            damage[target_id] += record_damage(
                self,
                target,
                requested,
                time,
                source_id=f"{source_id}:poison",
                source_actor_id=source_id,
                source_team=self.actors[source_id]["team"],
                origin="hazard",
            )
            trace.append(
                {
                    "event": "headhunter_poison_pulse",
                    "time_seconds": time,
                    "source": source_id,
                    "target": target_id,
                    "requested_damage": requested,
                }
            )
            exposure["last"] = time
            exposure["next"] = time + parameters["poison_interval_seconds"]
            if exposure["expiry"] <= time + EPSILON:
                del self.poison[key]
        return dict(damage)

    def next_boundary(self, time):
        candidates = [
            min(state["next"], state["expiry"]) for state in self.poison.values()
        ]
        candidates.extend(
            state["next"]
            for state in self.apprentices.values()
            if state["next"] is not None
        )
        for key, model in self.models.items():
            actor = self.actors[key]
            if not _active(actor, time):
                continue
            if key in self.samples:
                candidates.append(self.samples[key]["next"])
            if model["entity"] in {"rocket-balloon", "super-barbarian"}:
                expires = (
                    actor["spawn_seconds"]
                    + model["parameters"]["boost_duration_seconds"]
                )
                if expires > time + EPSILON:
                    candidates.append(expires)
        return min(candidates) if candidates else None

    def result(self):
        return {
            "models": deepcopy(self.models),
            "state_changes": deepcopy(self.events),
            "apprentice_states": deepcopy(self.apprentices),
            "consumed_instances": sorted(self.consumed),
            "active_poison": [
                {"source": source, "target": target, **deepcopy(state)}
                for (source, target), state in sorted(self.poison.items())
            ],
        }

    def continuation_reasons(self, time):
        return [
            continuation_fact(
                "pending_damage",
                f"headhunter-poison:{source}:{target}",
                [source],
                source_team=self.actors[source]["team"],
                not_before_seconds=min(state["next"], state["expiry"]),
            )
            for (source, target), state in sorted(self.poison.items())
            if _active(self.actors[target], time)
            and state["expiry"] > time + EPSILON
            and self.models[source]["statistics"]["poison_max_dps"] > 0
        ]
