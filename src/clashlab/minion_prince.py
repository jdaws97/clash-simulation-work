"""Conditional Prince protection, opening weapon boosts and travelling Dark Orb."""

from collections import defaultdict
from copy import deepcopy
from math import hypot, isclose

from .common import InputError, identifier, integer, number, require
from .hero_extensions import (
    parameter_provenance,
    require_fields,
    require_values,
    source_quantity,
    validate_parameter_provenance,
)
from .hit_status import PROTECTION_POLICIES
from .range_events import first_weapon_range_entry_delay
from .rates import rescale_remaining_cooldown
from .spatial import EPSILON, _active, center, target_distance


EQUIPMENT = {"metal-pants", "noble-iron", "dark-orb"}


def compile_prince_equipment(instance, hero, catalog):
    require_fields(instance, {"entity", "level", "parameters"}, "Prince equipment")
    entity_id = instance["entity"]
    if entity_id not in EQUIPMENT or hero["entity"] != "minion-prince":
        raise InputError("Unsupported Prince equipment owner or item")
    level = integer(instance["level"], "Prince equipment level", 1)
    if not catalog.available(entity_id, level, hero["town_hall"]):
        raise InputError("Prince equipment level is unavailable at this Town Hall")
    entity = catalog.entity(entity_id)
    row = catalog.level(entity_id, level)
    stats = row["stats"]
    model = {
        "entity": entity_id,
        "level": level,
        "ability_type": entity["abilityType"],
        "source": catalog.records[entity_id]["source"],
        "source_description": entity["description"],
        "parameter_provenance": parameter_provenance(instance["parameters"]),
        "behavior_source": require(instance["parameters"], "source"),
        "parameters": deepcopy(instance["parameters"]),
    }
    if entity_id == "metal-pants":
        model.update(
            duration_seconds=source_quantity(stats["abilityDuration"], "s"),
            incoming_damage_multiplier=1
            - number(
                stats["incomingDamageReduction"], "Pants numeric reduction", 0, 100
            )
            / 100,
        )
    elif entity_id == "noble-iron":
        model.update(
            damage_per_hit_increase=stats["damagePerShotIncrease"],
            boosted_launches=stats["numberOfAttacks"],
            attack_range=stats["attackRange"],
            attack_rate_multiplier=1
            + number(stats["attackSpeedIncrease"], "Iron numeric attack speed", 0)
            / 100,
        )
    else:
        model.update(
            projectile_damage=stats["projectileDamage"],
            slow_multiplier=1
            - number(stats["slowDownPercent"], "Orb slow percentage", 0, 100 - EPSILON)
            / 100,
            slow_duration_seconds=source_quantity(stats["slowDownDuration"], "s"),
        )
    validate_prince_equipment(model)
    return model, row


def validate_prince_equipment(model):
    entity_id = require(model, "entity")
    additions = {
        "metal-pants": {"duration_seconds", "incoming_damage_multiplier"},
        "noble-iron": {
            "damage_per_hit_increase",
            "boosted_launches",
            "attack_range",
            "attack_rate_multiplier",
        },
        "dark-orb": {"projectile_damage", "slow_multiplier", "slow_duration_seconds"},
    }
    if entity_id not in additions:
        raise InputError("Unsupported Prince equipment runtime entity")
    require_fields(
        model,
        {
            "entity",
            "level",
            "ability_type",
            "source",
            "source_description",
            "parameter_provenance",
            "behavior_source",
            "parameters",
        }
        | additions[entity_id],
        "Prince equipment runtime model",
    )
    integer(model["level"], "runtime Prince equipment level", 1)
    identifier(model["source"], "runtime Prince statistic source")
    identifier(model["behavior_source"], "runtime Prince behavior source")
    expected_type = "Passive" if entity_id == "noble-iron" else "Active"
    if model["ability_type"] != expected_type:
        raise InputError("Prince equipment activation type does not match its behavior")
    for field in additions[entity_id]:
        if field == "boosted_launches":
            integer(model[field], "Noble Iron boosted launches", 1)
        else:
            minimum = (
                EPSILON
                if field
                in {
                    "duration_seconds",
                    "attack_rate_multiplier",
                    "slow_multiplier",
                    "slow_duration_seconds",
                }
                else 0
            )
            maximum = (
                1
                if field in {"incoming_damage_multiplier", "slow_multiplier"}
                else None
            )
            number(model[field], field, minimum, maximum)
    parameters = model["parameters"]
    fields = {"source"}
    if entity_id == "metal-pants":
        fields |= {"reduction_mapping", "freeze", "stacking"}
        policies = {
            "reduction_mapping": "snapshot_numeric_percent_reduction_hypothesis",
            "freeze": "duration_continues_while_frozen",
            "stacking": "multiply_independent_incoming_damage_factors",
        }
    elif entity_id == "noble-iron":
        fields |= {"attack_speed_mapping", "count_policy", "trigger", "stacking"}
        policies = {
            "attack_speed_mapping": "snapshot_numeric_percent_attack_rate_bonus_hypothesis",
            "count_policy": "spend_one_per_main_weapon_launch_including_misses",
            "trigger": "first_launches_after_actual_deployment",
            "stacking": "add_profile_scaled_hit_damage_multiply_independent_attack_rate",
        }
    else:
        fields |= {
            "direction",
            "fallback_unit_vector",
            "travel_distance_tiles",
            "radius_tiles",
            "projectile_speed_tiles_per_second",
            "release_delay_seconds",
            "geometry",
            "target_kinds",
            "target_layers",
            "hit_policy",
            "obstacles",
            "visibility",
            "protection_policy",
            "slow_mapping",
            "source_death",
            "freeze",
            "damage_scaling",
        }
        policies = {
            "direction": "captured_retained_target_center_or_explicit_fallback",
            "geometry": "moving_circle_to_target_footprint_hypothesis",
            "hit_policy": "one_contact_per_target_then_expire_after_final_position",
            "obstacles": "passes_through_buildings_and_walls",
            "visibility": "released_orb_ignores_invisibility_but_excludes_hidden_teslas",
            "slow_mapping": "snapshot_percent_reduction_of_movement_and_attack_rate_hypothesis",
            "source_death": "released_orb_and_slow_persist",
            "freeze": "released_orb_continues_while_source_frozen",
            "damage_scaling": "equipment_flat_damage_times_hero_profile_only_hypothesis",
        }
    require_fields(parameters, fields, "Prince equipment parameters")
    identifier(parameters["source"], "Prince equipment parameter source")
    validate_parameter_provenance(model)
    for field, expected in policies.items():
        if parameters[field] != expected:
            raise InputError("Unsupported Prince equipment lifecycle policy")
    if entity_id == "dark-orb":
        for field in (
            "travel_distance_tiles",
            "radius_tiles",
            "projectile_speed_tiles_per_second",
        ):
            number(parameters[field], field, EPSILON)
        number(parameters["release_delay_seconds"], "Dark Orb release delay", 0)
        vector = parameters["fallback_unit_vector"]
        require_fields(vector, {"x", "y"}, "Dark Orb fallback heading")
        number(vector["x"], "Dark Orb fallback x")
        number(vector["y"], "Dark Orb fallback y")
        if not isclose(
            hypot(vector["x"], vector["y"]), 1, rel_tol=1e-10, abs_tol=EPSILON
        ):
            raise InputError("Dark Orb fallback must be an explicit unit vector")
        require_values(
            parameters["target_kinds"],
            {"unit", "defense", "building", "wall"},
            "Dark Orb target kinds",
        )
        require_values(
            parameters["target_layers"], {"ground", "air"}, "Dark Orb target layers"
        )
        if parameters["protection_policy"] not in PROTECTION_POLICIES:
            raise InputError(
                "Dark Orb protection and slowing relationship must be explicit"
            )


class MinionPrinceCombat:
    """Shared-charge hooks and independently travelling, single-contact orbs."""

    def __init__(self, actors, combat, hit_status):
        self.equipment = {}
        self.base_weapons = {}
        self.activated = set()
        self.pants_until = {}
        self.iron_remaining = {}
        self.orbs = []
        self.combat = combat
        self.hit_status = hit_status
        for key, actor in actors.items():
            if actor.get("hero_model", {}).get("entity") != "minion-prince":
                continue
            if (
                actor["team"] != "attack"
                or actor["kind"] != "unit"
                or actor["movement"] != "air"
                or actor["layer"] != "air"
            ):
                raise InputError("Prince equipment requires the attacking flying hero")
            self.equipment[key] = {}
            self.base_weapons[key] = {
                field: deepcopy(actor[field])
                for field in ("damage", "range", "attack_model")
            }
            for item in actor["hero_model"]["equipment"]:
                from .equipment_summons import (
                    OWNERS as SUMMON_OWNERS,
                    validate_equipment as validate_summon,
                )

                if item["entity"] in SUMMON_OWNERS:
                    validate_summon(item)
                    continue
                from .equipment_weapons import OWNERS, validate_equipment

                if item["entity"] in OWNERS:
                    validate_equipment(item)
                    continue
                validate_prince_equipment(item)
                if item["entity"] in self.equipment[key]:
                    raise InputError("Prince equipment cannot be duplicated")
                self.equipment[key][item["entity"]] = deepcopy(item)
            iron = self.equipment[key].get("noble-iron")
            self.iron_remaining[key] = (
                iron["boosted_launches"] if iron is not None else 0
            )
            if "dark-orb" in self.equipment[key] and hit_status is None:
                raise InputError("Dark Orb requires the shared impact-status lifecycle")

    def prepare(self, actors, time, trace):
        for key, equipment in self.equipment.items():
            prince = actors[key]
            if not _active(prince, time):
                continue
            pants = equipment.get("metal-pants")
            active_pants = self.pants_until.get(key, 0) > time + EPSILON
            prince["_hero_incoming_damage_multiplier"] = (
                pants["incoming_damage_multiplier"] if active_pants else 1
            )
            base = self.base_weapons[key]
            prince["damage"] = base["damage"]
            prince["range"] = base["range"]
            iron = equipment.get("noble-iron")
            boosting = self.iron_remaining[key] > 0
            new_rate = iron["attack_rate_multiplier"] if boosting else 1
            old_rate = prince.get("_hero_attack_rate", 1)
            if abs(new_rate - old_rate) > EPSILON:
                rescale_remaining_cooldown(prince, time, old_rate, new_rate)
            prince["_hero_attack_rate"] = new_rate
            if boosting:
                prince["damage"] += (
                    iron["damage_per_hit_increase"]
                    * prince["hero_model"]["damage_multiplier"]
                )
                prince["range"] = (
                    iron["attack_range"] * prince["hero_model"]["range_multiplier"]
                )

    def activate(self, hero_id, actors, time, trace):
        if (
            hero_id not in self.equipment
            or hero_id in self.activated
            or not _active(actors[hero_id], time)
        ):
            return False
        self.activated.add(hero_id)
        prince = actors[hero_id]
        pants = self.equipment[hero_id].get("metal-pants")
        if pants is not None:
            self.pants_until[hero_id] = time + pants["duration_seconds"]
        model = self.equipment[hero_id].get("dark-orb")
        if model is None:
            return True
        parameters = model["parameters"]
        origin = center(prince)
        target = actors.get(prince.get("target"))
        direction = parameters["fallback_unit_vector"]
        vector = (direction["x"], direction["y"])
        if (
            target is not None
            and _active(target, time)
            and target["team"] != prince["team"]
        ):
            target_point = center(target)
            delta = target_point[0] - origin[0], target_point[1] - origin[1]
            length = hypot(*delta)
            if length > EPSILON:
                vector = delta[0] / length, delta[1] / length
        starts = time + parameters["release_delay_seconds"]
        travel_time = (
            parameters["travel_distance_tiles"]
            / parameters["projectile_speed_tiles_per_second"]
        )
        self.orbs.append(
            {
                "source": hero_id,
                "source_team": prince["team"],
                "model": model,
                "origin": origin,
                "direction": vector,
                "starts_at": starts,
                "ends_at": starts + travel_time,
                "visited": set(),
                "finished": False,
                "damage": model["projectile_damage"]
                * prince["hero_model"]["damage_multiplier"],
                "collateral_policy": prince["attack_model"].get(
                    "defending_unit_collateral_policy", "allow"
                ),
            }
        )
        trace.append(
            {
                "event": "dark_orb_released",
                "time_seconds": time,
                "source": hero_id,
                "origin": origin,
                "direction": vector,
                "starts_at": starts,
                "ends_at": starts + travel_time,
            }
        )
        return True

    def weapon_launched(self, actor_id, time, trace):
        if self.iron_remaining.get(actor_id, 0) > 0:
            self.iron_remaining[actor_id] -= 1
            trace.append(
                {
                    "event": "noble_iron_launch_spent",
                    "time_seconds": time,
                    "source": actor_id,
                    "remaining": self.iron_remaining[actor_id],
                }
            )

    @staticmethod
    def _position(orb, time):
        distance = max(0, min(time, orb["ends_at"]) - orb["starts_at"])
        distance *= orb["model"]["parameters"]["projectile_speed_tiles_per_second"]
        return tuple(
            orb["origin"][axis] + orb["direction"][axis] * distance for axis in (0, 1)
        )

    @staticmethod
    def _eligible(orb, target, time):
        parameters = orb["model"]["parameters"]
        return (
            _active(target, time)
            and target["team"] != orb["source_team"]
            and target["id"] not in orb["visited"]
            and target["kind"] in parameters["target_kinds"]
            and target["layer"] in parameters["target_layers"]
            and not target.get("_tesla_hidden", False)
            and not (
                target["kind"] == "unit"
                and target["team"] == "defense"
                and orb["collateral_policy"] == "ignore"
            )
        )

    def resolve(self, actors, time, trace, receipts=None):
        damage = defaultdict(float)
        for orb in self.orbs:
            if orb["finished"] or time < orb["starts_at"] - EPSILON:
                continue
            point = self._position(orb, time)
            model = orb["model"]
            parameters = model["parameters"]
            for target in actors.values():
                if (
                    not self._eligible(orb, target, time)
                    or target_distance(point, target)
                    > parameters["radius_tiles"] + EPSILON
                ):
                    continue
                orb["visited"].add(target["id"])
                amount = orb["damage"]
                if receipts is not None:
                    amount = receipts.register(
                        target,
                        amount,
                        time,
                        source_id=orb["source"],
                        source_actor_id=orb["source"],
                        source_team=orb["source_team"],
                        origin="ability",
                    )
                elif target["immune_until"] > time + EPSILON:
                    amount = 0
                damage[target["id"]] += amount
                self.hit_status.impact(
                    {
                        "source": orb["source"],
                        "on_hit_status": {
                            "source": model["behavior_source"],
                            "duration_seconds": model["slow_duration_seconds"],
                            "attack_rate_multiplier": model["slow_multiplier"],
                            "movement_multiplier": model["slow_multiplier"],
                            "protection_policy": parameters["protection_policy"],
                        },
                    },
                    target,
                    actors,
                    time,
                    trace,
                )
                trace.append(
                    {
                        "event": "dark_orb_contact",
                        "time_seconds": time,
                        "source": orb["source"],
                        "target": target["id"],
                        "position": point,
                        "damage": amount,
                    }
                )
            if time >= orb["ends_at"] - EPSILON:
                orb["finished"] = True
        return damage

    def first_crossing_delay(self, actors, routes, speeds, time, horizon):
        earliest = None
        for orb in self.orbs:
            if (
                orb["finished"]
                or time < orb["starts_at"] - EPSILON
                or time >= orb["ends_at"] - EPSILON
            ):
                continue
            point = self._position(orb, time)
            parameters = orb["model"]["parameters"]
            source = {
                "x": point[0],
                "y": point[1],
                "width": 0,
                "height": 0,
                "range": parameters["radius_tiles"],
            }
            endpoint = self._position(orb, orb["ends_at"])
            available = min(horizon, orb["ends_at"] - time)
            for target in actors.values():
                if not self._eligible(orb, target, time):
                    continue
                delay = first_weapon_range_entry_delay(
                    source,
                    target,
                    [endpoint],
                    routes.get(target["id"], []),
                    parameters["projectile_speed_tiles_per_second"],
                    speeds.get(target["id"], 0),
                    available,
                )
                if delay is not None:
                    earliest = delay if earliest is None else min(earliest, delay)
        return earliest

    def next_boundary(self, time):
        values = list(self.pants_until.values())
        for orb in self.orbs:
            if not orb["finished"]:
                values.extend((orb["starts_at"], orb["ends_at"]))
        future = [value for value in values if value > time + EPSILON]
        return min(future) if future else None

    def frame(self, actor_id, actor):
        if actor_id not in self.equipment:
            return {}
        return {
            "prince_metal_pants_until_seconds": self.pants_until.get(actor_id),
            "prince_noble_iron_launches_remaining": self.iron_remaining[actor_id],
        }

    def result(self):
        return {
            "active_equipment_used_for": sorted(self.activated),
            "noble_iron_launches_remaining": dict(self.iron_remaining),
            "pending_dark_orbs": sum(not orb["finished"] for orb in self.orbs),
            "game_calibrated": False,
        }
