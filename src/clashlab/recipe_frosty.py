"""Conditional Frosty/Frostmite lifecycle with mandatory unknown-stat inputs."""

from copy import deepcopy
from math import floor

from .combat import validate_pattern
from .common import InputError, identifier, integer, number
from .hero_extensions import parameter_provenance, require_fields
from .hit_status import validate_hit_status
from .spatial import EPSILON, _active, center


POLICIES = {
    "summon_clock": "deployment_anchored_skip_missed_ticks_no_catchup",
    "freeze": "skip_due_summons_while_frozen_keep_grid",
    "cap": "living_children_only_partial_batch_no_replacement",
    "reserve_exhaustion": "reject_before_partial_spawn",
    "parent_death": "stop_new_summons_released_children_persist",
    "child_targeting": "defenses_only_retain_until_ineligible_then_nearest",
    "child_motion": "ordinary_ground_point_jump_enemy_walls_hypothesis",
    "child_lifetime": "timed_from_actual_spawn_existing_packets_persist",
    "child_status_class": "troop_for_healing_buffs_hazards_springs",
    "slow_membership": "all_successful_impacts_including_defending_units_hypothesis",
    "child_statistics_scaling": "independent_explicit_totals_before_declared_battle_profile",
}
BEHAVIOR_FIELDS = set(POLICIES) | {
    "source",
    "status",
    "on_hit_slow",
    "first_summon_delay_seconds",
    "reserve_count",
    "frostmite_statistics",
    "frostmite_spawn_offset",
    "frostmite_first_attack_delay_seconds",
    "frostmite_lifetime_seconds",
    "frostmite_projectile",
    "frostmite_on_hit_slow",
}


def validate_frosty_behavior(behavior):
    require_fields(behavior, BEHAVIOR_FIELDS, "Frosty behavior")
    identifier(behavior["source"], "Frosty behavior source")
    if behavior["status"] != "explicit_uncalibrated_hypothesis":
        raise InputError("Frosty missing mechanics must remain explicitly uncalibrated")
    if any(behavior[key] != value for key, value in POLICIES.items()):
        raise InputError("Unsupported Frosty lifecycle policy")
    validate_hit_status(behavior["on_hit_slow"])
    validate_hit_status(behavior["frostmite_on_hit_slow"])
    for field in ("first_summon_delay_seconds", "frostmite_first_attack_delay_seconds"):
        number(behavior[field], field, 0)
    number(behavior["frostmite_lifetime_seconds"], "Frostmite lifetime", EPSILON)
    integer(behavior["reserve_count"], "Frostmite finite reserve", 1, 512)
    require_fields(behavior["frostmite_spawn_offset"], {"dx", "dy"}, "Frostmite offset")
    for value in behavior["frostmite_spawn_offset"].values():
        number(value, "Frostmite spawn offset")
    stats = behavior["frostmite_statistics"]
    require_fields(
        stats,
        {
            "source",
            "status",
            "hitpoints",
            "damage_per_hit",
            "attack_interval_seconds",
            "range_tiles",
            "movement_tiles_per_second",
            "housing_space",
        },
        "Frostmite statistics",
    )
    identifier(stats["source"], "Frostmite statistic source")
    if stats["status"] != "explicit_uncalibrated_hypothesis":
        raise InputError("Frostmite statistics must identify their unverified branch")
    for field in (
        "hitpoints",
        "attack_interval_seconds",
        "range_tiles",
        "movement_tiles_per_second",
    ):
        number(stats[field], field, EPSILON)
    number(stats["damage_per_hit"], "Frostmite hit", 0)
    integer(stats["housing_space"], "Frostmite trap weight", 1)
    validate_pattern(
        {
            "kind": "single",
            "source": stats["source"],
            "target_kinds": ["defense"],
            "target_layers": ["ground"],
            "maximum_hp_fraction": 0,
            "projectile": behavior["frostmite_projectile"],
        }
    )


def compile_frosty_model(entity, row, source, behavior):
    validate_frosty_behavior(behavior)
    return {
        "source": source,
        "summon_interval_seconds": number(
            entity["summonCooldown"], "Frosty summon interval", EPSILON
        ),
        "summons_per_batch": integer(
            row["frostmitesPerSummon"], "Frosty summon batch", 1
        ),
        "maximum_living_summons": integer(row["maxFrostmites"], "Frosty living cap", 1),
        "behavior": deepcopy(behavior),
        "parameter_provenance": parameter_provenance(behavior),
    }


def validate_frosty_model(model):
    require_fields(
        model,
        {
            "source",
            "summon_interval_seconds",
            "summons_per_batch",
            "maximum_living_summons",
            "behavior",
            "parameter_provenance",
        },
        "Frosty runtime model",
    )
    identifier(model["source"], "Frosty source")
    number(model["summon_interval_seconds"], "Frosty interval", EPSILON)
    count = integer(model["summons_per_batch"], "Frosty summon batch", 1)
    cap = integer(model["maximum_living_summons"], "Frosty living cap", 1)
    if count > cap:
        raise InputError("Frosty summon batch exceeds living cap")
    validate_frosty_behavior(model["behavior"])
    if model["parameter_provenance"] != parameter_provenance(model["behavior"]):
        raise InputError("Frosty behavior provenance does not match its contract")


def compile_frostmite_reserves(pet):
    if pet.get("pet_model", {}).get("entity") != "frosty":
        return []
    model = pet["frosty_model"]
    validate_frosty_model(model)
    behavior = model["behavior"]
    stats = behavior["frostmite_statistics"]
    reserves = []
    for index in range(behavior["reserve_count"]):
        actor = deepcopy(pet)
        actor.pop("pet_model")
        actor.pop("frosty_model")
        actor.pop("entity_adapter")
        actor.update(
            id=f"{pet['id']}-frostmite-{index}",
            source=stats["source"],
            hitpoints=stats["hitpoints"],
            damage=stats["damage_per_hit"],
            attack_interval_seconds=stats["attack_interval_seconds"],
            range=stats["range_tiles"],
            speed=stats["movement_tiles_per_second"],
            first_attack_seconds=behavior["frostmite_first_attack_delay_seconds"],
            healing_class="troop",
            hazard_class="troop",
            buff_class="troop",
            spring_class="troop",
            housing_space=stats["housing_space"],
            target_priorities=["defense"],
            target_priority_tiers=[["defense"]],
            target_layers=["ground"],
        )
        actor["attack_model"] = {
            "kind": "single",
            "source": stats["source"],
            "target_kinds": ["defense"],
            "target_layers": ["ground"],
            "maximum_hp_fraction": 0,
            "projectile": deepcopy(behavior["frostmite_projectile"]),
        }
        actor["wall_behavior"] = {
            "kind": "jump_enemy_walls",
            "source": behavior["source"],
        }
        actor["on_hit_status"] = deepcopy(behavior["frostmite_on_hit_slow"])
        actor["summon_model"] = {
            "kind": "frostmite",
            "parent": pet["id"],
            "hero_id": pet["pet_model"]["hero_id"],
            "source": stats["source"],
            "index": index,
            "lifetime_seconds": behavior["frostmite_lifetime_seconds"],
        }
        reserves.append(actor)
    return reserves


class FrostyCombat:
    """Spawn only declared children; cap counts and lifecycle remain auditable."""

    def __init__(self, actors, width, height):
        self.actors = actors
        self.width = width
        self.height = height
        self.models = {}
        self.children = {}
        self.next_summon = {}
        self.origins = {}
        self.used = set()
        self.expiry = {}
        for key, actor in actors.items():
            if actor.get("pet_model", {}).get("entity") != "frosty":
                if "frosty_model" in actor:
                    raise InputError("Frosty model requires the corresponding pet")
                continue
            model = actor.get("frosty_model")
            validate_frosty_model(model)
            if (
                actor["pet_model"]["parameters"]["behavior"] != model["behavior"]
                or actor.get("on_hit_status") != model["behavior"]["on_hit_slow"]
            ):
                raise InputError("Frosty pet and summon contracts disagree")
            self.models[key] = model
            self.next_summon[key] = None
            reserves = compile_frostmite_reserves(actor)
            self.children[key] = [reserve["id"] for reserve in reserves]
            for expected in reserves:
                child = actors.get(expected["id"])
                if (
                    child is None
                    or child.get("summon_model") != expected["summon_model"]
                    or child["spawn_seconds"] != "controlled"
                    or child["team"] != actor["team"]
                ):
                    raise InputError(
                        "Frosty requires its complete generated reserve pool"
                    )
                if any(
                    child.get(field) != "troop"
                    for field in (
                        "healing_class",
                        "hazard_class",
                        "buff_class",
                        "spring_class",
                    )
                ):
                    raise InputError("Frostmites require explicit troop class bindings")
                if (
                    child.get("on_hit_status") != expected["on_hit_status"]
                    or child.get("wall_behavior") != expected["wall_behavior"]
                ):
                    raise InputError(
                        "Frostmite slow and movement contracts disagree with parent"
                    )
        expected_ids = {key for values in self.children.values() for key in values}
        actual_ids = {
            key
            for key, actor in actors.items()
            if actor.get("summon_model", {}).get("kind") == "frostmite"
        }
        if expected_ids != actual_ids:
            raise InputError(
                "Frostmite reserves must belong to exactly one Frosty pool"
            )

    def prepare(self, actors, time, trace):
        for key, expiry in list(self.expiry.items()):
            if expiry <= time + EPSILON:
                actor = actors[key]
                if actor["hp"] > 0:
                    actor["hp"] = 0
                    actor["death_time"] = time
                    trace.append(
                        {
                            "event": "frostmite_expired",
                            "time_seconds": time,
                            "source": key,
                        }
                    )
                self.expiry.pop(key)
        for pet_id, model in self.models.items():
            pet = actors[pet_id]
            behavior = model["behavior"]
            clock = self.next_summon[pet_id]
            if clock is None:
                if not _active(pet, time):
                    continue
                self.origins[pet_id] = time + behavior["first_summon_delay_seconds"]
                clock = self.origins[pet_id]
                self.next_summon[pet_id] = clock
            if clock > time + EPSILON:
                continue
            interval = model["summon_interval_seconds"]
            tick = floor((time - self.origins[pet_id] + EPSILON) / interval)
            self.next_summon[pet_id] = self.origins[pet_id] + (tick + 1) * interval
            if (
                not _active(pet, time)
                or pet["frozen_until"] > time + EPSILON
                or time > clock + EPSILON
            ):
                continue
            living = sum(
                actors[key]["hp"] > 0 and key in self.used
                for key in self.children[pet_id]
            )
            count = min(
                model["summons_per_batch"], model["maximum_living_summons"] - living
            )
            available = [key for key in self.children[pet_id] if key not in self.used]
            if len(available) < count:
                raise InputError(
                    "Frostmite reserve exhausted; increase explicit reserve_count"
                )
            x, y = center(pet)
            offset = behavior["frostmite_spawn_offset"]
            x += offset["dx"]
            y += offset["dy"]
            if count and not (0 <= x < self.width and 0 <= y < self.height):
                raise InputError("Frostmite spawn lies outside the declared board")
            for key in available[:count]:
                actor = actors[key]
                actor.update(
                    x=x,
                    y=y,
                    spawn_seconds=time,
                    next_attack=time + behavior["frostmite_first_attack_delay_seconds"],
                )
                self.used.add(key)
                self.expiry[key] = time + behavior["frostmite_lifetime_seconds"]
            trace.append(
                {
                    "event": "frosty_summon_batch",
                    "time_seconds": time,
                    "source": pet_id,
                    "children": available[:count],
                    "living_before": living,
                    "living_cap": model["maximum_living_summons"],
                }
            )

    def next_boundary(self, time):
        values = list(self.expiry.values())
        values.extend(
            clock
            for key, clock in self.next_summon.items()
            if clock is not None and self.actors[key]["hp"] > 0
        )
        future = [value for value in values if value > time + EPSILON]
        return min(future) if future else None

    def frame(self, actor_id):
        if actor_id not in self.used:
            return {}
        return {"frostmite_expiry_seconds": self.expiry.get(actor_id)}

    def result(self):
        return {
            "summoned_ids": sorted(self.used),
            "expiry_seconds": deepcopy(self.expiry),
            "game_calibrated": False,
        }
