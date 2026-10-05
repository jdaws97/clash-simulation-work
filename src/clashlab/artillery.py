"""TH17 projectiles and explicit impact-flame overlap hypotheses."""

from collections import defaultdict
from copy import deepcopy

from .common import InputError, identifier, integer, number, require
from .combat import validate_pattern
from .hazards import HAZARD_CLASSES
from .heroes import HERO_RULES
from .spatial import EPSILON, _active, target_distance


RULESET = "spatial-artillery-hero-area-kernel-v10"
SCOPE = "artillery_attacking_heroes_area_sector_without_pets_traps_or_defending_troops"
RULES = {
    **HERO_RULES,
    "th17_weapon": "always_active_four_projectiles_without_death_blast",
    "impact_flames": "explicit_resolved_projectile_trigger_at_resolved_impact_position",
    "flame_overlap": "explicit_independent_pool_clocks_or_maximum_dps_at_source_clock",
    "flame_pulses": "start_inclusive_end_exclusive_full_declared_pulse_amounts",
    "flame_phase": "existing_pulses_after_commands_new_impact_pulses_after_weapon_health",
    "flame_source_death": "released_projectiles_and_existing_pools_continue_hypothesis",
    "flame_source_freeze": "released_pools_keep_pulsing_hypothesis",
}
OVERLAP_POLICIES = {
    "additive_independent_pool_clocks",
    "maximum_active_pool_dps_at_source_clock",
}
TRIGGER_POLICIES = {
    "resolved_projectile_including_protected_primary",
    "only_unprotected_direct_hit",
}
FLAME_FIELDS = {
    "source",
    "radius",
    "duration_seconds",
    "maximum_dps",
    "growth_by_field_age",
    "pulse_interval_seconds",
    "first_pulse_offset_seconds",
    "excluded_classes",
    "overlap_policy",
    "pulse_clock_policy",
    "trigger_policy",
    "pool_on_projectile_miss",
    "fizzle_policy",
    "source_freeze_policy",
}


def validate_flame(model):
    if not isinstance(model, dict) or set(model) != FLAME_FIELDS:
        raise InputError("Artillery flame behavior must declare every supported field")
    identifier(model["source"], "artillery flame evidence")
    number(model["radius"], "flame radius", 0)
    duration = number(model["duration_seconds"], "flame duration", EPSILON)
    interval = number(model["pulse_interval_seconds"], "flame pulse interval", EPSILON)
    first = number(model["first_pulse_offset_seconds"], "first flame pulse", 0)
    if first >= duration or first > interval:
        raise InputError("The first flame pulse must fall within the first interval")
    number(model["maximum_dps"], "flame maximum DPS", 0)
    if model["overlap_policy"] not in OVERLAP_POLICIES:
        raise InputError("Artillery flame overlap must be explicitly selected")
    if model["pulse_clock_policy"] != "first_pool_then_continuous_while_any_pool_alive":
        raise InputError("Unsupported artillery flame group clock")
    if model["trigger_policy"] not in TRIGGER_POLICIES:
        raise InputError("Unsupported artillery flame impact trigger")
    if not isinstance(model["pool_on_projectile_miss"], bool):
        raise InputError("Missed projectile flame creation must be explicit")
    if model["fizzle_policy"] != "no_pool_when_primary_fizzles":
        raise InputError("Unsupported artillery flame fizzle behavior")
    if model["source_freeze_policy"] != "released_pools_keep_pulsing_hypothesis":
        raise InputError("Flames require their explicit source-Freeze policy")
    excluded = model["excluded_classes"]
    if (
        not isinstance(excluded, list)
        or any(not isinstance(value, str) for value in excluded)
        or len(excluded) != len(set(excluded))
        or not set(excluded) <= HAZARD_CLASSES
    ):
        raise InputError("Flame exclusions require unique explicit classes")
    growth = model["growth_by_field_age"]
    if not isinstance(growth, list) or not growth:
        raise InputError("Flame growth requires explicit field-age stages")
    previous_age = -1
    previous_amount = -1
    for stage in growth:
        if not isinstance(stage, dict) or set(stage) != {
            "after_seconds",
            "dps_multiplier",
        }:
            raise InputError("Flame stages require age and DPS multiplier")
        age = number(stage["after_seconds"], "flame stage age", 0)
        amount = number(stage["dps_multiplier"], "flame stage multiplier", 0, 1)
        if age <= previous_age or age >= duration or amount < previous_amount:
            raise InputError("Flame stages must increase within the pool lifetime")
        if previous_age == -1 and age != 0:
            raise InputError("Flame growth must begin explicitly at age zero")
        previous_age = age
        previous_amount = amount
    return model


def compile_artillery(actor, instance, entity, row, modifiers):
    if (
        actor["entity_adapter"]["level"] != 17
        or actor["entity_adapter"]["town_hall"] != 17
        or instance["mode"] != "infernoArtillery"
        or instance["statistics_mode"] != "weapon"
        or actor["team"] != "defense"
        or not actor["counts_for_destruction"]
        or instance["spawn_seconds"] != 0
        or "wall_parameters" in instance
    ):
        raise InputError("Inferno Artillery requires an explicit defending TH17 weapon")
    parameters = require(instance, "town_hall_parameters")
    if set(parameters) != {"source", "weapon_level", "flame", "source_death_policy"}:
        raise InputError("Artillery cannot inherit Giga activation or death behavior")
    if (
        parameters["source_death_policy"]
        != "released_projectiles_and_pools_persist_hypothesis"
    ):
        raise InputError("Artillery requires its explicit source-death policy")
    identifier(parameters["source"], "artillery lifecycle evidence")
    weapon = require(row, "weapon")
    if weapon["name"] != "Inferno Artillery":
        raise InputError("The selected source does not contain Inferno Artillery")
    level = integer(parameters["weapon_level"], "artillery weapon level", 1)
    matches = [stats for stats in weapon["levels"] if stats["level"] == level]
    if len(matches) != 1:
        raise InputError("Artillery weapon level is absent from the selected source")
    attack = require(instance, "attack_parameters")
    if set(attack) != {"projectile", "allocation"}:
        raise InputError("Artillery requires explicit travel and volley allocation")
    if attack["allocation"] != "cycle_distinct_targets_to_fill_volley":
        raise InputError(
            "Four artillery projectiles require explicit repeated allocation"
        )
    flight = require(attack, "projectile")
    flight_fields = {"timing", "destination", "hit_radius", "inactive_primary_policy"}
    timing = require(flight, "timing")
    if timing == "instant":
        flight_fields.add("delay_seconds")
    elif timing == "launch_distance_delay":
        flight_fields.add("speed_tiles_per_second")
    else:
        raise InputError("Unsupported artillery projectile timing")
    if set(flight) != flight_fields:
        raise InputError(
            "Artillery projectile behavior must declare exact supported fields"
        )
    if flight["inactive_primary_policy"] != "fizzle":
        raise InputError(
            "This artillery scope requires declared primary fizzle behavior"
        )
    flame = require(parameters, "flame")
    expected = FLAME_FIELDS - {"duration_seconds", "maximum_dps"} | {
        "duration_multiplier",
        "maximum_dps_multiplier",
    }
    if not isinstance(flame, dict) or set(flame) != expected:
        raise InputError("Every unresolved artillery flame behavior must be explicit")
    compiled_flame = {
        key: deepcopy(value)
        for key, value in flame.items()
        if key not in {"duration_multiplier", "maximum_dps_multiplier"}
    }
    compiled_flame.update(
        duration_seconds=number(
            weapon["flameDuration"], "snapshot flame duration", EPSILON
        )
        * number(flame["duration_multiplier"], "flame duration modifier", EPSILON),
        maximum_dps=number(weapon["flameMaxDps"], "snapshot flame DPS", 0)
        * number(flame["maximum_dps_multiplier"], "flame damage modifier", 0),
    )
    validate_flame(compiled_flame)
    size = require(entity, "size")
    if not isinstance(size, str):
        raise InputError("The selected Town Hall source needs a rectangular footprint")
    footprint = size.split("x")
    if len(footprint) != 2 or any(not value.isdecimal() for value in footprint):
        raise InputError("The selected Town Hall source needs a rectangular footprint")
    width, height = [
        integer(int(value), "artillery footprint", 1) for value in footprint
    ]
    actor.update(
        kind="defense",
        layer="ground",
        movement="stationary",
        speed=0,
        width=width,
        height=height,
        blocking=True,
        damage=number(matches[0]["damagePerHit"], "artillery hit damage", 0)
        * modifiers["damage_multiplier"],
        attack_interval_seconds=number(
            weapon["attackSpeed"], "artillery interval", EPSILON
        )
        * modifiers["attack_interval_multiplier"],
        range=number(weapon["range"], "artillery range", 0)
        * modifiers["range_multiplier"],
        target_priorities=["unit"],
        target_priority_tiers=[["unit"]],
        target_layers=["ground", "air"],
        artillery_model={
            "source": parameters["source"],
            "kind": "th17_inferno_artillery_without_death_blast",
            "flame": compiled_flame,
            "source_death_policy": parameters["source_death_policy"],
        },
    )
    actor["attack_model"] = {
        "kind": "multi_target",
        "source": actor["source"],
        "target_kinds": ["unit"],
        "target_layers": ["ground", "air"],
        "maximum_hp_fraction": 0,
        "projectile": deepcopy(attack["projectile"]),
        "projectiles_per_volley": integer(
            weapon["targets"], "artillery projectiles", 1
        ),
        "allocation": attack["allocation"],
    }
    validate_pattern(actor["attack_model"])
    actor["entity_adapter"].update(
        weapon_level=level,
        lifecycle_parameters=deepcopy(parameters),
        selected_statistic="weapon.levels.damagePerHit and flameMaxDps/flameDuration",
        behavior_verification="conditional_artillery_not_replay_validated",
    )
    return actor


class ArtilleryCombat:
    """Keep released pool geometry, source clocks and health effects separate."""

    def __init__(self, actors):
        self.models = {}
        self.pools = {}
        self.source_clocks = {}
        self.sequence = 0
        for actor_id, actor in actors.items():
            if "artillery_model" not in actor:
                continue
            model = actor["artillery_model"]
            if not isinstance(model, dict) or set(model) != {
                "source",
                "kind",
                "flame",
                "source_death_policy",
            }:
                raise InputError("Artillery models cannot hide unimplemented behavior")
            if (
                model["kind"] != "th17_inferno_artillery_without_death_blast"
                or model["source_death_policy"]
                != "released_projectiles_and_pools_persist_hypothesis"
                or actor["kind"] != "defense"
                or actor["movement"] != "stationary"
                or actor["team"] != "defense"
                or not actor["counts_for_destruction"]
                or "death_model" in actor
                or "town_hall_model" in actor
                or actor["attack_model"]["kind"] != "multi_target"
                or actor["attack_model"]["projectiles_per_volley"] != 4
                or actor["attack_model"]["allocation"]
                != "cycle_distinct_targets_to_fill_volley"
            ):
                raise InputError(
                    "Artillery requires its distinct always-active lifecycle"
                )
            identifier(model["source"], "runtime artillery evidence")
            self.models[actor_id] = deepcopy(validate_flame(model["flame"]))
        if self.models and any(
            actor["kind"] == "unit" and actor.get("hazard_class") not in HAZARD_CLASSES
            for actor in actors.values()
        ):
            raise InputError("Artillery-exposed units need explicit hazard classes")

    @staticmethod
    def _live(pool, time):
        return (
            pool["start_seconds"] <= time + EPSILON
            and time < pool["expiry_seconds"] - EPSILON
        )

    @staticmethod
    def _inside(pool, actor, time):
        return (
            _active(actor, time)
            and actor["team"] == "attack"
            and actor["kind"] == "unit"
            and actor["layer"] in {"ground", "air"}
            and actor["hazard_class"] not in pool["model"]["excluded_classes"]
            and target_distance(pool["position"], actor)
            <= pool["model"]["radius"] + EPSILON
        )

    def impact(self, event, actors, time, trace):
        source = event["source"]
        if source not in self.models:
            return
        model = self.models[source]
        if event["hit_count"] == 0 and not model["pool_on_projectile_miss"]:
            return
        if model["trigger_policy"] == "only_unprotected_direct_hit" and (
            event["hit_count"] == 0 or event["primary_protected"]
        ):
            return
        active_before = any(
            pool["source"] == source and self._live(pool, time)
            for pool in self.pools.values()
        )
        self.sequence += 1
        pool_id = f"{source}:impact-flame:{self.sequence}"
        self.pools[pool_id] = {
            "id": pool_id,
            "source": source,
            "position": tuple(event["position"]),
            "start_seconds": time,
            "expiry_seconds": time + model["duration_seconds"],
            "next_pulse_seconds": time + model["first_pulse_offset_seconds"],
            "model": deepcopy(model),
        }
        if not active_before:
            self.source_clocks[source] = time + model["first_pulse_offset_seconds"]
        trace.append(
            {
                "time_seconds": time,
                "event": "artillery_flame_release",
                "source": source,
                "pool": pool_id,
                "position": {"x": event["position"][0], "y": event["position"][1]},
                "expiry_seconds": self.pools[pool_id]["expiry_seconds"],
                "primary_protected": event["primary_protected"],
                "direct_hit_count": event["hit_count"],
            }
        )

    @staticmethod
    def _dps(pool, time):
        multiplier = 0
        for stage in pool["model"]["growth_by_field_age"]:
            if stage["after_seconds"] <= time - pool["start_seconds"] + EPSILON:
                multiplier = stage["dps_multiplier"]
        return pool["model"]["maximum_dps"] * multiplier

    def resolve(self, actors, time, trace):
        from .damage_receipts import record_damage

        damage = defaultdict(float)
        for source, model in self.models.items():
            live = [
                pool
                for pool in self.pools.values()
                if pool["source"] == source and self._live(pool, time)
            ]
            if not live:
                continue
            interval = model["pulse_interval_seconds"]
            if model["overlap_policy"] == "additive_independent_pool_clocks":
                batches = [
                    [pool]
                    for pool in live
                    if pool["next_pulse_seconds"] <= time + EPSILON
                ]
            elif self.source_clocks[source] <= time + EPSILON:
                batches = [live]
            else:
                batches = []
            for pools in batches:
                amounts = {}
                protected = []
                for actor_id, actor in actors.items():
                    values = [
                        self._dps(pool, time)
                        for pool in pools
                        if self._inside(pool, actor, time)
                    ]
                    if not values:
                        continue
                    amount = max(values) * interval
                    amounts[actor_id] = amount
                    if actor["immune_until"] > time + EPSILON:
                        protected.append(actor_id)
                    resolved = record_damage(
                        self,
                        actor,
                        amount,
                        time,
                        source_id=source,
                        source_actor_id=source,
                        source_team=actors[source]["team"],
                        origin="hazard",
                    )
                    if resolved > 0:
                        damage[actor_id] += resolved
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "artillery_flame_pulse",
                        "source": source,
                        "pools": [pool["id"] for pool in pools],
                        "requested_damage": amounts,
                        "protected_targets": protected,
                        "overlap_policy": model["overlap_policy"],
                    }
                )
                if model["overlap_policy"] == "additive_independent_pool_clocks":
                    pools[0]["next_pulse_seconds"] += interval
                else:
                    self.source_clocks[source] += interval
        return damage

    def next_boundary(self, time):
        boundaries = []
        for pool in self.pools.values():
            boundaries.append(pool["expiry_seconds"])
            if self._live(pool, time):
                if (
                    pool["model"]["overlap_policy"]
                    == "additive_independent_pool_clocks"
                ):
                    boundaries.append(pool["next_pulse_seconds"])
                else:
                    boundaries.append(self.source_clocks[pool["source"]])
        future = [boundary for boundary in boundaries if boundary > time + EPSILON]
        return min(future) if future else None

    def frame(self, actor, time):
        return {
            "artillery_flame_pools": [
                pool["id"]
                for pool in self.pools.values()
                if self._live(pool, time) and self._inside(pool, actor, time)
            ]
        }

    def result(self):
        return {
            "pools": deepcopy(self.pools),
            "source_clocks": deepcopy(self.source_clocks),
            "full_game_prediction": False,
            "current_client_verified": False,
        }
