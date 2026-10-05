"""Finite, predeclared equipment children and attributed Snake Bracelet triggers.

Ordinary children compile through the ordinary adapter with an explicit level
mapping. Unavailable Henchman/Snake/equipment-LavaLoon child quantities require a
complete caller-declared actor with uncalibrated provenance; no seasonal row is
borrowed. All releases preserve identity, housing ownership and spent charges.
"""

from collections import defaultdict
from copy import deepcopy
from math import floor

from .combat import validate_pattern
from .common import InputError, identifier, integer, number
from .hero_extensions import source_quantity
from .rates import rescale_remaining_cooldown, skip_elapsed_pulses
from .spatial import EPSILON, _active, _blocked, center


OWNERS = {
    "archer-puppet": "archer-queen",
    "barbarian-puppet": "barbarian-king",
    "healer-puppet": "archer-queen",
    "hog-rider-puppet": "royal-champion",
    "henchmen-puppet": "minion-prince",
    "lavaloon-puppet": "grand-warden",
    "snake-bracelet": "barbarian-king",
}
CHILDREN = {
    "archer-puppet": "archer",
    "barbarian-puppet": "barbarian",
    "healer-puppet": "healer",
    "hog-rider-puppet": "hog-rider",
    "henchmen-puppet": "henchman",
    "lavaloon-puppet": "equipment-lavaloon",
    "snake-bracelet": "equipment-snake",
}
POLICIES = {
    "experimental_policy": "finite_equipment_children_v1_uncalibrated",
    "child_lifetime": "until_child_death_independent_of_parent",
    "reserve_exhaustion": "reject_before_any_partial_release",
    "statistics_mapping": "explicit_catalog_level_or_complete_unverified_child_actor",
    "damage_trigger": "actual_nonlethal_loss_since_last_spawn",
    "snake_cap": "catalog_maxSummonedSnakes_total_battle_experimental",
    "owner_heal_clock": "continue_deployed_even_frozen_skip_recall_ticks",
    "recall": "preserve_child_identity_and_expire_absolute_buffs",
    "spawn_phase": "after_same_boundary_ability_memberships_before_health_settlement",
}
FIELDS = {
    "entity",
    "level",
    "ability_type",
    "source",
    "parameters",
    "count",
    "child_level",
    "child_actor",
    "child_cloak_seconds",
    "owner_cloak_seconds",
    "child_rage_seconds",
    "child_damage_factor",
    "child_movement_bonus",
    "owner_self_heal_per_second",
    "owner_attack_rate",
}


def validate_equipment(model):
    if (
        not isinstance(model, dict)
        or set(model) != FIELDS
        or model["entity"] not in OWNERS
    ):
        raise InputError("Equipment summon requires a complete supported model")
    if model["entity"] == "lavaloon-puppet":
        raise InputError(
            "Equipment LavaLoon bomb/death/Lava Pup ownership requires a source-complete child adapter"
        )
    identifier(model["source"], "equipment summon statistic source")
    integer(model["level"], "equipment summon level", 1)
    integer(model["count"], "finite equipment child budget", 1, 512)
    integer(model["child_level"], "equipment child level", 1)
    parameters = model["parameters"]
    expected = {
        "source",
        *POLICIES,
        "child_statistics_status",
        "child_contract",
        "spawn_offsets",
        "first_attack_delay_seconds",
        "damage_per_snake",
        "self_heal_interval_seconds",
        "first_self_heal_delay_seconds",
    }
    if not isinstance(parameters, dict) or set(parameters) != expected:
        raise InputError(
            "Equipment children require complete explicit source/statistic/lifecycle contracts"
        )
    identifier(parameters["source"], "equipment child mapping source")
    if parameters[
        "child_statistics_status"
    ] != "explicit_uncalibrated_hypothesis" or any(
        parameters[key] != value for key, value in POLICIES.items()
    ):
        raise InputError(
            "Unresolved equipment child mappings must remain opt-in uncalibrated"
        )
    offsets = parameters["spawn_offsets"]
    if not isinstance(offsets, list) or len(offsets) != model["count"]:
        raise InputError(
            "Every finite equipment child needs an explicit release offset"
        )
    for offset in offsets:
        if not isinstance(offset, dict) or set(offset) != {"dx", "dy"}:
            raise InputError("Equipment child offset requires dx and dy")
        for value in offset.values():
            number(value, "equipment child offset")
    for field in ("first_attack_delay_seconds", "first_self_heal_delay_seconds"):
        number(parameters[field], field, 0)
    for field in ("damage_per_snake", "self_heal_interval_seconds"):
        number(parameters[field], field, EPSILON)
    actor = model["child_actor"]
    if (
        not isinstance(actor, dict)
        or actor.get("team") != "attack"
        or actor.get("kind") != "unit"
        or actor.get("counts_for_destruction")
        or "hero_model" in actor
        or "pet_model" in actor
    ):
        raise InputError(
            "Equipment children require ordinary attacking nonhero/nonpet actors"
        )
    identifier(actor.get("source"), "child statistic source")
    validate_pattern(actor.get("attack_model"))
    if model["entity"] == "healer-puppet" and "healing_model" not in actor:
        raise InputError("Healer Puppet requires the full ordinary healer lifecycle")
    if model["entity"] == "lavaloon-puppet" and "death_model" not in actor:
        raise InputError(
            "Equipment LavaLoon bomb/death/child behavior requires a complete explicit death model"
        )
    if model["ability_type"] != (
        "Passive" if model["entity"] == "snake-bracelet" else "Active"
    ):
        raise InputError("Equipment summon activation type mismatch")
    for field in (
        "child_cloak_seconds",
        "owner_cloak_seconds",
        "child_rage_seconds",
        "child_movement_bonus",
        "owner_self_heal_per_second",
    ):
        number(model[field], field, 0)
    number(model["child_damage_factor"], "child damage factor", 1)
    number(model["owner_attack_rate"], "summon equipment passive cadence", 1)


def compile_equipment(instance, hero, catalog, conversion):
    if set(instance) != {"entity", "level", "parameters"}:
        raise InputError("Equipment summon instance requires complete fields")
    entity_id = instance["entity"]
    if entity_id not in OWNERS or hero["entity"] != OWNERS[entity_id]:
        raise InputError("Equipment summon hero mismatch")
    level = integer(instance["level"], "summon gear level", 1)
    if not catalog.available(entity_id, level, hero["town_hall"]):
        raise InputError("Summon equipment unavailable at selected Town Hall")
    entity, row = catalog.entity(entity_id), catalog.level(entity_id, level)
    if entity_id == "lavaloon-puppet":
        raise InputError(
            "Equipment LavaLoon child statistics, bomb geometry, death burst and finite Lava Pup ownership require a source-complete child adapter; seasonal LavaLoon cannot substitute"
        )
    stats = row["stats"]
    parameters = deepcopy(instance["parameters"])
    if not isinstance(parameters, dict) or "child_contract" not in parameters:
        raise InputError(
            "Missing source-backed child contract; catalog presence cannot substitute for summon behavior"
        )
    contract = parameters["child_contract"]
    if not isinstance(contract, dict) or set(contract) != {
        "kind",
        "level",
        "source",
        "actor_or_instance",
    }:
        raise InputError(
            "Child contract requires kind, level, source and actor_or_instance"
        )
    identifier(contract["source"], "child identity/level mapping evidence")
    child_level = integer(contract["level"], "child level", 1)
    expected_levels = {
        "healer-puppet": "healerLevel",
        "hog-rider-puppet": "hogRiderLevel",
        "henchmen-puppet": "henchmenLevel",
        "lavaloon-puppet": "lavaloonLevel",
        "snake-bracelet": "snakeLevel",
    }
    if (
        entity_id in expected_levels
        and child_level != stats[expected_levels[entity_id]]
    ):
        raise InputError("Child level differs from pinned equipment row")
    counts = {
        "archer-puppet": "summonedArchers",
        "barbarian-puppet": "summonedBarbarians",
        "healer-puppet": "summonedHealers",
        "hog-rider-puppet": "summonedHogRiders",
        "lavaloon-puppet": "summonedLavaloons",
        "snake-bracelet": "maxSummonedSnakes",
    }
    count = (
        entity["ability"]["henchmenCount"]
        if entity_id == "henchmen-puppet"
        else stats[counts[entity_id]]
    )
    if entity_id in {
        "archer-puppet",
        "barbarian-puppet",
        "healer-puppet",
        "hog-rider-puppet",
    }:
        from .adapters import compile_actor

        child = deepcopy(contract["actor_or_instance"])
        if (
            contract["kind"] != "ordinary_catalog_instance"
            or child.get("entity") != CHILDREN[entity_id]
            or child.get("level") != child_level
            or child.get("town_hall") != hero["town_hall"]
        ):
            raise InputError(
                "Ordinary equipment child must select its exact catalog identity/level"
            )
        child["spawn_seconds"] = "controlled"
        child["counts_for_destruction"] = False
        child["team"] = "attack"
        actor = compile_actor(
            child,
            catalog,
            conversion,
            allow_walls=True,
            allow_support=True,
            allow_deaths=True,
            allow_hit_status=True,
            allow_extended=True,
            allow_hero_extensions=True,
        )
        actor["housing_space"] = integer(
            catalog.entity(CHILDREN[entity_id])["housingSpace"],
            "equipment child trap weight",
            1,
        )
    else:
        if contract["kind"] != "complete_uncalibrated_child_actor_not_seasonal_alias":
            raise InputError(
                "Unavailable equipment child stats cannot be borrowed from seasonal identities"
            )
        actor = deepcopy(contract["actor_or_instance"])
    model = {
        "entity": entity_id,
        "level": level,
        "ability_type": entity["abilityType"],
        "source": catalog.records[entity_id]["source"],
        "parameters": parameters,
        "count": count,
        "child_level": child_level,
        "child_actor": actor,
        "child_cloak_seconds": 0,
        "owner_cloak_seconds": 0,
        "child_rage_seconds": 0,
        "child_damage_factor": 1,
        "child_movement_bonus": 0,
        "owner_self_heal_per_second": number(
            stats.get("selfHealingPerSecond", 0), "equipment self healing", 0
        ),
        "owner_attack_rate": 1,
    }
    if entity_id == "archer-puppet":
        model["child_cloak_seconds"] = source_quantity(
            stats["archerInvisibilityDuration"], "s"
        )
    elif entity_id == "barbarian-puppet":
        model.update(
            child_rage_seconds=number(
                entity["ability"]["barbarianRageDuration"],
                "Barbarian child rage duration",
                0,
            ),
            child_damage_factor=1
            + source_quantity(
                stats["barbarianDamageIncrease"], "%", allow_leading_plus=True
            )
            / 100,
            child_movement_bonus=number(
                stats["barbarianSpeedIncrease"], "Barbarian child movement units", 0
            )
            / number(conversion, "movement conversion", EPSILON),
        )
    elif entity_id in {"hog-rider-puppet", "henchmen-puppet"}:
        key = (
            "invisibility"
            if entity_id == "hog-rider-puppet"
            else "invisibilityDuration"
        )
        model["owner_cloak_seconds"] = source_quantity(entity["ability"][key], "s")
    elif entity_id == "snake-bracelet":
        model["owner_attack_rate"] = (
            1
            + source_quantity(
                stats["attackSpeedIncrease"], "%", allow_leading_plus=True
            )
            / 100
        )
    validate_equipment(model)
    return model, row


def validate_independent_deployment(command, actors):
    if command.get("kind") == "deploy" and any(
        actors.get(key, {}).get("summon_model", {}).get("kind") == "equipment_child"
        for key in command.get("targets", [])
    ):
        raise InputError(
            "Equipment reserves can only deploy through their owning ability/damage lifecycle"
        )


def compile_reserves(hero):
    reserves = []
    for item in hero.get("hero_model", {}).get("equipment", []):
        if item["entity"] not in OWNERS:
            continue
        validate_equipment(item)
        for index, offset in enumerate(item["parameters"]["spawn_offsets"]):
            actor = deepcopy(item["child_actor"])
            for field in ("entity_adapter", "hero_model", "pet_model"):
                actor.pop(field, None)
            actor.update(
                id=f"{hero['id']}:{item['entity']}:{index}",
                spawn_seconds="controlled",
                first_attack_seconds=item["parameters"]["first_attack_delay_seconds"],
                counts_for_destruction=False,
                healing_class="troop",
                hazard_class="troop",
                buff_class="troop",
                spring_class="troop",
            )
            if "housing_space" not in actor:
                raise InputError(
                    "Equipment child requires explicit source-backed trap/Giga housing weight"
                )
            actor["summon_model"] = {
                "kind": "equipment_child",
                "origin": "hero_equipment",
                "parent": hero["id"],
                "equipment": item["entity"],
                "index": index,
                "level": item["child_level"],
                "offset": deepcopy(offset),
                "source": item["parameters"]["child_contract"]["source"],
            }
            reserves.append(actor)
    return reserves


class EquipmentSummonCombat:
    def __init__(self, actors, width, height):
        self.models = {}
        self.children = {}
        self.used = set()
        self.activated = set()
        self.receipts_seen = set()
        self.loss = defaultdict(float)
        self.rage_expiry = {}
        self.heal_next = {}
        self.pending_release = {}
        self.width, self.height = width, height
        for key, actor in actors.items():
            for item in actor.get("hero_model", {}).get("equipment", []):
                if item["entity"] not in OWNERS:
                    continue
                validate_equipment(item)
                self.models[(key, item["entity"])] = deepcopy(item)
                expected = [
                    child
                    for child in compile_reserves(actor)
                    if child["summon_model"]["equipment"] == item["entity"]
                ]
                self.children[(key, item["entity"])] = [
                    child["id"] for child in expected
                ]
                for child in expected:
                    actual = actors.get(child["id"])
                    if (
                        actual is None
                        or actual.get("summon_model") != child["summon_model"]
                        or actual["spawn_seconds"] != "controlled"
                    ):
                        raise InputError(
                            "Equipment summon requires the complete predeclared, correctly owned reserve pool"
                        )
                if item["owner_self_heal_per_second"]:
                    self.heal_next[key] = None

    def _spawn(self, key, count, actors, time, trace):
        model = self.models[key]
        available = [child for child in self.children[key] if child not in self.used]
        if len(available) < count:
            raise InputError("Equipment summon finite reserve exhausted before release")
        owner = actors[key[0]]
        positions = []
        for child_id in available[:count]:
            offset = actors[child_id]["summon_model"]["offset"]
            x, y = center(owner)
            x, y = x + offset["dx"], y + offset["dy"]
            if not (0 <= x < self.width and 0 <= y < self.height):
                raise InputError("Equipment child release lies outside the board")
            child = actors[child_id]
            if child["movement"] == "ground" and (floor(x), floor(y)) in _blocked(
                actors, time
            ):
                jumping_enemy_wall = child.get("wall_behavior", {}).get(
                    "kind"
                ) == "jump_enemy_walls" and any(
                    actor["kind"] == "wall"
                    and actor["team"] != child["team"]
                    and _active(actor, time)
                    and (floor(actor["x"]), floor(actor["y"])) == (floor(x), floor(y))
                    for actor in actors.values()
                )
                if not jumping_enemy_wall:
                    raise InputError(
                        "Equipment child release occupies a blocked footprint"
                    )
            positions.append((child_id, x, y))
        for child_id, x, y in positions:
            actor = actors[child_id]
            actor.update(
                x=x,
                y=y,
                spawn_seconds=time,
                next_attack=time + model["parameters"]["first_attack_delay_seconds"],
            )
            actor["_untargetable_until"] = max(
                actor.get("_untargetable_until", 0), time + model["child_cloak_seconds"]
            )
            self.used.add(child_id)
            if model["child_rage_seconds"]:
                self.rage_expiry[child_id] = (time + model["child_rage_seconds"], key)
                actor["_equipment_child_damage_multiplier"] = model[
                    "child_damage_factor"
                ]
                actor["_equipment_child_movement_bonus"] = model["child_movement_bonus"]
        trace.append(
            {
                "time_seconds": time,
                "event": "equipment_summon_release",
                "source": key[0],
                "equipment": key[1],
                "children": available[:count],
                "experimental": True,
            }
        )

    def activate(self, hero_id, actors, time, trace):
        if hero_id in self.activated or not _active(actors[hero_id], time):
            return
        self.activated.add(hero_id)
        for key, model in self.models.items():
            if key[0] != hero_id or model["ability_type"] != "Active":
                continue
            self.pending_release[key] = {"count": model["count"], "time": time}
            actors[hero_id]["_untargetable_until"] = max(
                actors[hero_id].get("_untargetable_until", 0),
                time + model["owner_cloak_seconds"],
            )

    def prepare(self, actors, time, trace):
        for key, release in list(self.pending_release.items()):
            if release["time"] != time:
                raise InputError(
                    "Equipment activation releases must settle at their captured boundary"
                )
            self._spawn(key, release["count"], actors, time, trace)
            del self.pending_release[key]
        for child_id, (expiry, _) in list(self.rage_expiry.items()):
            if expiry <= time:
                actors[child_id]["_equipment_child_damage_multiplier"] = 1
                actors[child_id]["_equipment_child_movement_bonus"] = 0
                del self.rage_expiry[child_id]
        for key, model in self.models.items():
            owner = actors[key[0]]
            if model["entity"] == "snake-bracelet":
                old = owner.get("_equipment_summon_attack_rate", 1)
                if old != model["owner_attack_rate"]:
                    rescale_remaining_cooldown(
                        owner, time, old, model["owner_attack_rate"]
                    )
                owner["_equipment_summon_attack_rate"] = model["owner_attack_rate"]
            if (
                key[0] in self.heal_next
                and self.heal_next[key[0]] is None
                and _active(owner, time)
            ):
                self.heal_next[key[0]] = (
                    owner["spawn_seconds"]
                    + model["parameters"]["first_self_heal_delay_seconds"]
                )

    def after_health(self, actors, receipts, time, trace):
        for receipt in receipts:
            key = receipt["target_id"], "snake-bracelet"
            unique = (receipt["time_seconds"], receipt["sequence"])
            if key not in self.models or unique in self.receipts_seen:
                continue
            self.receipts_seen.add(unique)
            if not _active(actors[key[0]], time):
                continue
            self.loss[key] += number(
                receipt["actual_health_loss"], "actual Snake trigger loss", 0
            )
            model = self.models[key]
            remaining = sum(child not in self.used for child in self.children[key])
            threshold = model["parameters"]["damage_per_snake"]
            count = min(floor(self.loss[key] / threshold), remaining)
            if count:
                self._spawn(key, count, actors, time, trace)
                self.loss[key] -= count * threshold

    def resolve(self, actors, time, trace, receipts):
        healing = defaultdict(float)
        for key, model in self.models.items():
            if not model["owner_self_heal_per_second"]:
                continue
            owner = actors[key[0]]
            clock = self.heal_next[key[0]]
            interval = model["parameters"]["self_heal_interval_seconds"]
            if owner.get("_recalled", False):
                self.heal_next[key[0]] = skip_elapsed_pulses(clock, interval, time)
            elif clock is not None and _active(owner, time) and clock <= time:
                healing[key[0]] += model["owner_self_heal_per_second"] * interval
                self.heal_next[key[0]] = time + interval
        return {}, healing

    def next_boundary(self, time):
        values = [expiry for expiry, _ in self.rage_expiry.values() if expiry > time]
        values.extend(
            clock
            for clock in self.heal_next.values()
            if clock is not None and clock > time
        )
        return min(values) if values else None

    def result(self):
        return {
            "released_children": sorted(self.used),
            "finite_inventory_schema": "owner_equipment_records_v1",
            "finite_inventory": [
                {
                    "owner_id": owner_id,
                    "equipment_id": equipment_id,
                    "child_ids": list(children),
                    "released_child_ids": [
                        child for child in children if child in self.used
                    ],
                    "remaining_child_ids": [
                        child for child in children if child not in self.used
                    ],
                }
                for (owner_id, equipment_id), children in sorted(self.children.items())
            ],
            "experimental": True,
            "calibrated": False,
        }
