"""Explicit, uncalibrated equipment contracts for comparative recipe runs.

The pinned catalog supplies equipment statistics. Missing summon statistics and
geometry are mandatory inputs, never borrowed from another troop implicitly.
"""

from collections import defaultdict
from copy import deepcopy
from heapq import heappop, heappush
from math import hypot, isclose

from .common import InputError, identifier, integer, number, require
from .hero_extensions import (
    parameter_provenance,
    require_fields,
    source_quantity,
    validate_parameter_provenance,
)
from .range_events import first_weapon_range_entry_delay
from .rates import rescale_remaining_cooldown, skip_elapsed_pulses
from .spatial import EPSILON, _active, center, target_distance
from .spell_visibility import untargetable_until


OWNERS = {
    "action-figure": "archer-queen",
    "giant-arrow": "archer-queen",
    "fireball": "grand-warden",
    "earthquake-boots": "barbarian-king",
}
COMMON = {
    "source_death": "activation_captures_effect_persisting_through_delay_and_death",
    "protection": "shared_damage_receipts",
}
POLICIES = {
    "action-figure": {
        "summon_lifetime": "until_death_independent_of_queen",
        "statistics_mapping": "explicit_summon_totals_before_parent_modifiers",
        "rage_trigger": "latch_once_at_or_below_half_maximum_hp_while_alive",
        "freeze": "regeneration_and_rage_clock_continue",
        "summon_class": "troop_for_buffs_healing_hazards_and_spring",
        "summon_targeting": "retained_defense_then_building_ground_only",
        "summon_attack": "source_center_splash_including_walls_shared_wall_clock",
        "summon_walls": "clear_before_crossing_nominal_clearance_route_cost",
        "regeneration": "queen_while_active_from_deployment_independent_of_activation",
        "spawn": "one_at_activation_at_explicit_offset_no_expiry",
    },
    "giant-arrow": {
        **COMMON,
        "direction": "current_live_target_center_else_explicit_unit_vector",
        "contact": "moving_disk_vs_live_footprint_once_per_actor",
        "visibility": "collateral_ignores_invisibility_excludes_hidden_tesla",
        "damage_scaling": "equipment_flat_damage_times_hero_profile_only",
        "targets": "enemy_buildings_defenses_walls_and_units_both_layers",
    },
    "fireball": {
        **COMMON,
        "selection": "nearest_visible_defense_footprint_then_instance_id",
        "no_target": "consume_shared_charge_without_projectile",
        "destination": "captured_target_center_even_if_target_dies",
        "membership": "live_footprints_at_impact",
        "visibility": "collateral_ignores_invisibility_excludes_hidden_tesla",
        "damage_scaling": "equipment_flat_damage_times_hero_profile_only",
        "targets": "enemy_buildings_defenses_walls_and_units_both_layers",
    },
    "earthquake-boots": {
        **COMMON,
        "membership": "activation_center_vs_live_ground_footprints",
        "damage_basis": "maximum_hp_fraction_allow_lethal_without_hero_scaling",
        "walls": "maximum_hp_damage_subject_to_shared_protection",
        "visibility": "collateral_ignores_invisibility_excludes_hidden_tesla",
    },
}
NUMERIC = {
    "action-figure": {
        "summon_statistics",
        "summon_offset",
        "first_attack_delay_seconds",
        "self_heal_interval_seconds",
        "first_self_heal_delay_seconds",
        "splash_radius_tiles",
        "rage_damage_multiplier",
        "rage_movement_multiplier",
        "rage_attack_rate_multiplier",
    },
    "giant-arrow": {
        "release_delay_seconds",
        "projectile_speed_tiles_per_second",
        "travel_distance_tiles",
        "fallback_unit_vector",
    },
    "fireball": {"release_delay_seconds", "projectile_speed_tiles_per_second"},
    "earthquake-boots": set(),
}
STAT_FIELDS = {
    "action-figure": {
        "invisibility_seconds",
        "summon_level",
        "self_healing_per_second",
    },
    "giant-arrow": {"projectile_damage", "radius_tiles"},
    "fireball": {"projectile_damage", "radius_tiles"},
    "earthquake-boots": {"radius_tiles", "building_fraction", "troop_fraction"},
}


def compile_recipe_equipment(instance, hero, catalog):
    require_fields(instance, {"entity", "level", "parameters"}, "Recipe equipment")
    entity_id = instance["entity"]
    if entity_id not in OWNERS or hero["entity"] != OWNERS[entity_id]:
        raise InputError("Recipe equipment belongs to a different hero")
    level = integer(instance["level"], "recipe equipment level", 1)
    if not catalog.available(entity_id, level, hero["town_hall"]):
        raise InputError("Recipe equipment level is unavailable at this Town Hall")
    entity = catalog.entity(entity_id)
    row = catalog.level(entity_id, level)
    stats = row["stats"]
    parameters = deepcopy(instance["parameters"])
    model = {
        "entity": entity_id,
        "level": level,
        "ability_type": entity["abilityType"],
        "source": catalog.records[entity_id]["source"],
        "source_description": entity["description"],
        "behavior_source": require(parameters, "source"),
        "parameters": parameters,
        "parameter_provenance": parameter_provenance(parameters),
    }
    if entity_id == "action-figure":
        model.update(
            invisibility_seconds=source_quantity(
                entity["ability"]["invisibilityDuration"], "s"
            ),
            summon_level=stats["giantGiantLevel"],
            self_healing_per_second=stats["selfHealingPerSecond"],
        )
    elif entity_id in {"giant-arrow", "fireball"}:
        model.update(
            projectile_damage=stats["projectileDamage"],
            radius_tiles=source_quantity(
                (
                    entity["ability"]["damageRadius"]
                    if entity_id == "giant-arrow"
                    else stats["damageRadius"]
                ),
                "tile" if entity_id == "giant-arrow" else "tiles",
            ),
        )
    else:
        model.update(
            radius_tiles=entity["ability"]["abilityRadius"],
            building_fraction=source_quantity(stats["buildingDamagePercent"], "%")
            / 100,
            troop_fraction=source_quantity(stats["troopDamagePercent"], "%") / 100,
        )
    validate_recipe_equipment(model)
    return model, row


def validate_recipe_equipment(model):
    entity = require(model, "entity")
    if entity not in OWNERS:
        raise InputError("Unsupported recipe equipment")
    require_fields(
        model,
        {
            "entity",
            "level",
            "ability_type",
            "source",
            "source_description",
            "behavior_source",
            "parameters",
            "parameter_provenance",
        }
        | STAT_FIELDS[entity],
        "Recipe equipment runtime model",
    )
    integer(model["level"], "recipe equipment level", 1)
    if model["ability_type"] != "Active":
        raise InputError("Recipe equipment shares the hero's active ability charge")
    identifier(model["source"], "recipe statistic source")
    identifier(model["behavior_source"], "recipe behavior source")
    validate_parameter_provenance(model)
    parameters = model["parameters"]
    require_fields(
        parameters,
        {"source"} | set(POLICIES[entity]) | NUMERIC[entity],
        "Recipe equipment parameters",
    )
    if any(parameters[key] != value for key, value in POLICIES[entity].items()):
        raise InputError("Unsupported recipe equipment lifecycle policy")
    for field in STAT_FIELDS[entity]:
        number(model[field], field, 0, 1 if field.endswith("fraction") else None)
    for field in NUMERIC[entity] - {
        "summon_statistics",
        "summon_offset",
        "fallback_unit_vector",
    }:
        number(parameters[field], field, 0 if "delay" in field else EPSILON)
    if entity == "giant-arrow":
        vector = parameters["fallback_unit_vector"]
        require_fields(vector, {"x", "y"}, "Arrow fallback unit vector")
        if not isclose(
            hypot(number(vector["x"], "arrow x"), number(vector["y"], "arrow y")),
            1,
            abs_tol=EPSILON,
        ):
            raise InputError("Arrow fallback direction must have unit length")
    if entity == "action-figure":
        integer(model["summon_level"], "Giant Giant level", 1)
        stats = parameters["summon_statistics"]
        require_fields(
            stats,
            {
                "source",
                "status",
                "identity_mapping",
                "level",
                "hitpoints",
                "damage_per_hit",
                "attack_interval_seconds",
                "range_tiles",
                "movement_tiles_per_second",
                "housing_space",
            },
            "Explicit Giant Giant statistics",
        )
        identifier(stats["source"], "Giant Giant statistic evidence")
        if (
            stats["status"] != "explicit_uncalibrated_hypothesis"
            or stats["identity_mapping"]
            != "caller_declared_equipment_summon_not_verified_seasonal_identity"
        ):
            raise InputError(
                "Giant Giant statistics need explicit unresolved identity provenance"
            )
        if integer(stats["level"], "summon level", 1) != model["summon_level"]:
            raise InputError("Action Figure and Giant Giant statistic levels disagree")
        for field in {
            "hitpoints",
            "damage_per_hit",
            "attack_interval_seconds",
            "movement_tiles_per_second",
        }:
            number(stats[field], field, EPSILON)
        number(stats["range_tiles"], "summon range", 0)
        integer(stats["housing_space"], "summon trap housing class", 1)
        require_fields(
            parameters["summon_offset"], {"dx", "dy"}, "Action Figure offset"
        )
        for value in parameters["summon_offset"].values():
            number(value, "summon offset")
        if parameters["splash_radius_tiles"] < stats["range_tiles"]:
            raise InputError(
                "Giant Giant source splash must include its primary target"
            )
        if (
            parameters["first_self_heal_delay_seconds"]
            > parameters["self_heal_interval_seconds"]
        ):
            raise InputError("First Action Figure heal must fall within first interval")


def compile_action_figure_summons(actor):
    summons = []
    for equipment in actor["hero_model"]["equipment"]:
        if equipment["entity"] != "action-figure":
            continue
        validate_recipe_equipment(equipment)
        parameters = equipment["parameters"]
        stats = parameters["summon_statistics"]
        modifiers = actor["entity_adapter"]["modifiers"]
        summon = deepcopy(actor)
        summon.pop("hero_model")
        summon.pop("entity_adapter")
        summon.update(
            id=f"{actor['id']}-action-figure-giant",
            source=stats["source"],
            spawn_seconds="controlled",
            hitpoints=stats["hitpoints"] * modifiers["hitpoints_multiplier"],
            damage=stats["damage_per_hit"] * modifiers["damage_multiplier"],
            attack_interval_seconds=stats["attack_interval_seconds"]
            * modifiers["attack_interval_multiplier"],
            range=stats["range_tiles"] * modifiers["range_multiplier"],
            speed=stats["movement_tiles_per_second"]
            * modifiers["movement_speed_multiplier"],
            healing_class="troop",
            hazard_class="troop",
            buff_class="troop",
            spring_class="troop",
            housing_space=stats["housing_space"],
            target_priorities=["defense", "building"],
            target_priority_tiers=[["defense"], ["building"]],
            target_layers=["ground"],
        )
        summon["attack_model"] = {
            "kind": "source_radial",
            "source": parameters["source"],
            "radius": parameters["splash_radius_tiles"],
            "target_kinds": ["defense", "building", "wall", "unit"],
            "target_layers": ["ground"],
            "maximum_hp_fraction": 0,
            "projectile": {
                "timing": "instant",
                "delay_seconds": 0,
                "destination": "fixed_source_center_at_launch",
                "hit_radius": 0,
                "inactive_primary_policy": "resolve_at_fixed_launch_position",
            },
        }
        summon["wall_behavior"] = {
            "kind": "clear_obstructions",
            "source": parameters["source"],
            "route_cost": "travel_seconds_plus_nominal_clearance",
            "weapon": {
                "damage": summon["damage"],
                "attack_interval_seconds": summon["attack_interval_seconds"],
                "range": summon["range"],
                "first_attack_seconds": summon["first_attack_seconds"],
                "cooldown": "shared_with_main_weapon",
                "timing": "instant",
                "source": parameters["source"],
            },
        }
        summon["summon_model"] = {
            "parent": actor["id"],
            "equipment": "action-figure",
            "source": stats["source"],
            "offset": deepcopy(parameters["summon_offset"]),
            "first_attack_delay_seconds": parameters["first_attack_delay_seconds"],
            "rage_damage_multiplier": parameters["rage_damage_multiplier"],
            "rage_movement_multiplier": parameters["rage_movement_multiplier"],
            "rage_attack_rate_multiplier": parameters["rage_attack_rate_multiplier"],
            "lifetime": parameters["summon_lifetime"],
        }
        summons.append(summon)
    return summons


class RecipeEquipmentCombat:
    """Shared-charge equipment and generated troop state, never army inventory."""

    def __init__(self, actors):
        self.equipment = {}
        self.activated = set()
        self.packets = []
        self.sequence = 0
        self.arrows = []
        self.heal_next = {}
        self.raged = set()
        self.summons = {}
        for key, actor in actors.items():
            equipment = {
                item["entity"]: item
                for item in actor.get("hero_model", {}).get("equipment", [])
                if item["entity"] in OWNERS
            }
            if equipment:
                for item in equipment.values():
                    validate_recipe_equipment(item)
                self.equipment[key] = equipment
            if "action-figure" in equipment:
                self.heal_next[key] = None
        for key, actor in actors.items():
            summon = actor.get("summon_model", {})
            if summon.get("equipment") != "action-figure":
                continue
            parent = summon.get("parent")
            model = self.equipment.get(parent, {}).get("action-figure")
            if model is None or key != f"{parent}-action-figure-giant":
                raise InputError(
                    "Action Figure reserve needs its selected Queen equipment"
                )
            expected = compile_action_figure_summons(actors[parent])[0]["summon_model"]
            if summon != expected or actor["team"] != actors[parent]["team"]:
                raise InputError(
                    "Action Figure reserve contract disagrees with its parent"
                )
            if any(
                actor.get(field) != "troop"
                for field in (
                    "healing_class",
                    "hazard_class",
                    "buff_class",
                    "spring_class",
                )
            ):
                raise InputError(
                    "Action Figure reserve needs explicit troop class bindings"
                )
            self.summons[key] = summon

    def _queue(self, arrival, packet):
        heappush(self.packets, (arrival, self.sequence, packet))
        self.sequence += 1

    def activate(self, hero_id, actors, time, trace):
        if (
            hero_id not in self.equipment
            or hero_id in self.activated
            or not _active(actors[hero_id], time)
        ):
            return
        self.activated.add(hero_id)
        hero = actors[hero_id]
        origin = center(hero)
        for entity, model in self.equipment[hero_id].items():
            parameters = model["parameters"]
            packet = {
                "source": hero_id,
                "source_team": hero["team"],
                "equipment": entity,
                "origin": origin,
                "model": model,
                "damage": model.get("projectile_damage", 0)
                * hero["hero_model"]["damage_multiplier"],
                "collateral_policy": hero["attack_model"].get(
                    "defending_unit_collateral_policy", "allow"
                ),
            }
            if entity == "fireball":
                candidates = [
                    target
                    for target in actors.values()
                    if _active(target, time)
                    and target["team"] != hero["team"]
                    and target["kind"] == "defense"
                    and not target.get("_tesla_hidden", False)
                    and untargetable_until(target) <= time + EPSILON
                ]
                if not candidates:
                    trace.append(
                        {
                            "event": "fireball_no_target",
                            "source": hero_id,
                            "time_seconds": time,
                        }
                    )
                    continue
                distances = {
                    target["id"]: target_distance(origin, target)
                    for target in candidates
                }
                nearest = min(distances.values())
                target = min(
                    (
                        target
                        for target in candidates
                        if distances[target["id"]] <= nearest + EPSILON
                    ),
                    key=lambda target: target["id"],
                )
                destination = center(target)
                arrival = (
                    time
                    + parameters["release_delay_seconds"]
                    + hypot(destination[0] - origin[0], destination[1] - origin[1])
                    / parameters["projectile_speed_tiles_per_second"]
                )
                self._queue(
                    arrival, {**packet, "point": destination, "target": target["id"]}
                )
                trace.append(
                    {
                        "event": "fireball_released",
                        "time_seconds": time,
                        "source": hero_id,
                        "target": target["id"],
                        "point": destination,
                        "arrival_seconds": arrival,
                    }
                )
            elif entity == "giant-arrow":
                vector = parameters["fallback_unit_vector"]
                direction = (vector["x"], vector["y"])
                target = actors.get(hero.get("target"))
                if (
                    target is not None
                    and _active(target, time)
                    and target["team"] != hero["team"]
                ):
                    point = center(target)
                    delta = (point[0] - origin[0], point[1] - origin[1])
                    length = hypot(*delta)
                    if length > EPSILON:
                        direction = (delta[0] / length, delta[1] / length)
                starts = time + parameters["release_delay_seconds"]
                ends = (
                    starts
                    + parameters["travel_distance_tiles"]
                    / parameters["projectile_speed_tiles_per_second"]
                )
                self.arrows.append(
                    {
                        **packet,
                        "direction": direction,
                        "starts_at": starts,
                        "ends_at": ends,
                        "visited": set(),
                        "finished": False,
                    }
                )
                trace.append(
                    {
                        "event": "giant_arrow_released",
                        "time_seconds": time,
                        "source": hero_id,
                        "origin": origin,
                        "direction": direction,
                        "starts_at": starts,
                        "ends_at": ends,
                    }
                )
            elif entity == "earthquake-boots":
                self._queue(time, {**packet, "point": origin})

    def prepare(self, actors, time, trace):
        for key, clock in self.heal_next.items():
            if clock is None and _active(actors[key], time):
                self.heal_next[key] = (
                    time
                    + self.equipment[key]["action-figure"]["parameters"][
                        "first_self_heal_delay_seconds"
                    ]
                )
        for key, summon in self.summons.items():
            actor = actors[key]
            if (
                key in self.raged
                or not _active(actor, time)
                or actor["hp"] > actor["maximum_hp"] / 2 + EPSILON
            ):
                continue
            self.raged.add(key)
            actor["damage"] *= summon["rage_damage_multiplier"]
            actor["speed"] *= summon["rage_movement_multiplier"]
            if actor["wall_behavior"]["kind"] == "clear_obstructions":
                actor["wall_behavior"]["weapon"]["damage"] = actor["damage"]
            old_rate = actor.get("_hero_attack_rate", 1)
            new_rate = old_rate * summon["rage_attack_rate_multiplier"]
            rescale_remaining_cooldown(actor, time, old_rate, new_rate)
            actor["_hero_attack_rate"] = new_rate
            trace.append(
                {
                    "event": "action_figure_rage",
                    "time_seconds": time,
                    "source": key,
                    "hp": actor["hp"],
                }
            )

    def wall_impacts(self, actor, primary, actors, time):
        if actor["id"] not in self.summons:
            return None
        from .defending_heroes import defending_collateral_eligible

        pattern = actor["attack_model"]
        packet = {"pattern": pattern, "target": primary["id"]}
        return [
            target
            for target in actors.values()
            if _active(target, time)
            and target["team"] != actor["team"]
            and target["kind"] in pattern["target_kinds"]
            and target["layer"] == "ground"
            and not target.get("_tesla_hidden", False)
            and target_distance(center(actor), target) <= pattern["radius"] + EPSILON
            and defending_collateral_eligible(packet, target)
        ]

    @staticmethod
    def _eligible(packet, target, time):
        return (
            _active(target, time)
            and target["team"] != packet["source_team"]
            and not target.get("_tesla_hidden", False)
            and not (
                target["kind"] == "unit"
                and target["team"] == "defense"
                and packet["collateral_policy"] == "ignore"
            )
        )

    @staticmethod
    def _position(arrow, time):
        distance = (
            max(0, min(time, arrow["ends_at"]) - arrow["starts_at"])
            * arrow["model"]["parameters"]["projectile_speed_tiles_per_second"]
        )
        return tuple(
            arrow["origin"][axis] + arrow["direction"][axis] * distance
            for axis in (0, 1)
        )

    @staticmethod
    def _damage(packet, target, amount, time, receipts):
        if receipts is not None:
            return receipts.register(
                target,
                amount,
                time,
                source_id=packet["source"],
                source_actor_id=packet["source"],
                source_team=packet["source_team"],
                origin="ability",
            )
        return amount if target["immune_until"] <= time + EPSILON else 0

    def resolve(self, actors, time, trace, receipts=None):
        damage = defaultdict(float)
        healing = defaultdict(float)
        for key, clock in self.heal_next.items():
            if clock is not None and actors[key].get("_recalled", False):
                interval = self.equipment[key]["action-figure"]["parameters"][
                    "self_heal_interval_seconds"
                ]
                self.heal_next[key] = skip_elapsed_pulses(clock, interval, time)
                continue
            if (
                clock is not None
                and clock <= time + EPSILON
                and _active(actors[key], time)
            ):
                model = self.equipment[key]["action-figure"]
                interval = model["parameters"]["self_heal_interval_seconds"]
                healing[key] += model["self_healing_per_second"] * interval
                self.heal_next[key] += interval
        while self.packets and self.packets[0][0] <= time + EPSILON:
            _, _, packet = heappop(self.packets)
            model = packet["model"]
            targets = {}
            for key, target in actors.items():
                if (
                    not self._eligible(packet, target, time)
                    or target_distance(packet["point"], target)
                    > model["radius_tiles"] + EPSILON
                ):
                    continue
                amount = packet["damage"]
                if packet["equipment"] == "earthquake-boots":
                    if target["layer"] != "ground":
                        continue
                    fraction = (
                        1
                        if target["kind"] == "wall"
                        else (
                            model["troop_fraction"]
                            if target["kind"] == "unit"
                            else model["building_fraction"]
                        )
                    )
                    amount = target["maximum_hp"] * fraction
                applied = self._damage(packet, target, amount, time, receipts)
                damage[key] += applied
                targets[key] = applied
            trace.append(
                {
                    "event": packet["equipment"].replace("-", "_") + "_impact",
                    "time_seconds": time,
                    "source": packet["source"],
                    "point": packet["point"],
                    "damage_by_target": targets,
                }
            )
        for arrow in self.arrows:
            if arrow["finished"] or time < arrow["starts_at"] - EPSILON:
                continue
            point = self._position(arrow, time)
            for key, target in actors.items():
                if (
                    key in arrow["visited"]
                    or not self._eligible(arrow, target, time)
                    or target_distance(point, target)
                    > arrow["model"]["radius_tiles"] + EPSILON
                ):
                    continue
                arrow["visited"].add(key)
                applied = self._damage(arrow, target, arrow["damage"], time, receipts)
                damage[key] += applied
                trace.append(
                    {
                        "event": "giant_arrow_contact",
                        "time_seconds": time,
                        "source": arrow["source"],
                        "target": key,
                        "damage": applied,
                    }
                )
            if time >= arrow["ends_at"] - EPSILON:
                arrow["finished"] = True
        return damage, healing

    def first_crossing_delay(self, actors, routes, speeds, time, horizon):
        earliest = None
        for arrow in self.arrows:
            if (
                arrow["finished"]
                or time < arrow["starts_at"] - EPSILON
                or time >= arrow["ends_at"] - EPSILON
            ):
                continue
            point = self._position(arrow, time)
            source = {
                "x": point[0],
                "y": point[1],
                "width": 0,
                "height": 0,
                "range": arrow["model"]["radius_tiles"],
            }
            for key, target in actors.items():
                if key in arrow["visited"] or not self._eligible(arrow, target, time):
                    continue
                delay = first_weapon_range_entry_delay(
                    source,
                    target,
                    [self._position(arrow, arrow["ends_at"])],
                    routes.get(key, []),
                    arrow["model"]["parameters"]["projectile_speed_tiles_per_second"],
                    speeds.get(key, 0),
                    min(horizon, arrow["ends_at"] - time),
                )
                if delay is not None:
                    earliest = delay if earliest is None else min(earliest, delay)
        return earliest

    def next_boundary(self, time):
        values = [clock for clock in self.heal_next.values() if clock is not None]
        if self.packets:
            values.append(self.packets[0][0])
        for arrow in self.arrows:
            if not arrow["finished"]:
                values.extend((arrow["starts_at"], arrow["ends_at"]))
        future = [value for value in values if value > time + EPSILON]
        return min(future) if future else None

    def continuation_reasons(self):
        from .battle_termination import continuation_fact

        reasons = [
            continuation_fact(
                "pending_damage",
                f"hero:recipe:{sequence}",
                [packet["source"]],
                not_before_seconds=arrival,
            )
            for arrival, sequence, packet in self.packets
        ]
        reasons.extend(
            continuation_fact(
                "lingering_damage",
                f"hero:giant_arrow:{index}",
                [arrow["source"]],
                not_before_seconds=arrow["starts_at"],
                expires_at_seconds=arrow["ends_at"],
            )
            for index, arrow in enumerate(self.arrows)
            if not arrow["finished"]
        )
        return reasons

    def result(self):
        return {
            "active_equipment_used_for": sorted(self.activated),
            "raged_summons": sorted(self.raged),
            "pending_packets": len(self.packets),
            "pending_arrows": sum(not arrow["finished"] for arrow in self.arrows),
            "game_calibrated": False,
        }
