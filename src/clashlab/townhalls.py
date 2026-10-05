"""Conditional TH14–16 Giga Inferno activation, blast and persistent poison.

Town Hall weapon levels are separate from building levels. TH17 artillery and
TH18 guardians must supply their own behaviors rather than inherit this model.
"""

from copy import deepcopy
from collections import defaultdict

from .common import InputError, identifier, integer, number, require
from .deaths import DEATH_RULES
from .hazards import PulsedHazards, validate_hazard
from .spatial import EPSILON, _active, _apply_health, center


RULESET = "spatial-town-hall-hazards-kernel-v7"
TOWN_HALL_RULES = {
    **DEATH_RULES,
    "town_hall_activation": "explicit_initial_state_damage_or_declared_destruction_fraction",
    "town_hall_classification": "building_until_activation_then_defense",
    "town_hall_readiness": "activation_delay_after_current_freeze_end",
    "town_hall_death_poison": "released_once_from_actual_death_with_explicit_delay",
    "hazard_damage_growth": "piecewise_constant_explicit_field_age_curve",
    "hazard_membership": "live_unit_positions_at_solver_boundaries",
    "hazard_pulses": "start_inclusive_end_exclusive_full_declared_pulse_amounts",
    "hazard_overlap": "additive_damage_strongest_movement_and_attack_slow",
    "hazard_clock_changes": "rescale_remaining_unfrozen_cooldown_on_rate_change",
    "hazard_route_cost": "current_movement_and_attack_rates_in_nominal_clearance_cost",
    "hazard_phase": "settle_after_commands_and_after_weapon_health_before_movement",
    "hazard_linger": "explicit_duration_after_observed_exit_or_field_expiry",
    "target_scoring": "explicit_scene_policy_legacy_route_distance_or_arrival_time_then_distance",
}


def compile_giga_inferno(actor, instance, entity, row, modifiers):
    level = actor["entity_adapter"]["level"]
    if level != actor["entity_adapter"]["town_hall"]:
        raise InputError(
            "Town Hall building level must match its declared village level"
        )
    if level not in {14, 15, 16}:
        raise InputError(
            "Town Hall level requires artillery, guardian or earlier weapon mechanics"
        )
    if (
        instance["mode"] != "gigaInferno"
        or instance["statistics_mode"] != "weapon"
        or actor["team"] != "defense"
        or not actor["counts_for_destruction"]
        or instance["spawn_seconds"] != 0
        or instance["first_attack_seconds"] != 0
        or "wall_parameters" in instance
    ):
        raise InputError(
            "Giga Inferno needs explicit defensive weapon mode and activation readiness"
        )
    parameters = require(instance, "town_hall_parameters")
    if set(parameters) != {"source", "weapon_level", "activation", "death"}:
        raise InputError("Every Town Hall lifecycle parameter must be explicit")
    identifier(parameters["source"], "Town Hall lifecycle evidence")
    weapon = require(row, "weapon")
    if not isinstance(weapon, dict) or weapon["name"] != "Giga Inferno":
        raise InputError("Selected Town Hall does not have a Giga Inferno weapon")
    weapon_level = integer(parameters["weapon_level"], "Town Hall weapon level", 1)
    selected = [value for value in weapon["levels"] if value["level"] == weapon_level]
    if len(selected) != 1:
        raise InputError("Town Hall weapon level is absent from the selected source")
    stats = selected[0]
    attack = require(instance, "attack_parameters")
    if (
        set(attack) != {"projectile", "allocation"}
        or attack["allocation"] != "distinct_targets_only"
    ):
        raise InputError(
            "Giga Inferno beams require distinct targets and explicit projectile timing"
        )
    if (
        modifiers["maximum_hp_damage_multiplier"] != 1
        or modifiers["movement_speed_multiplier"] != 1
    ):
        raise InputError(
            "Town Hall cannot use irrelevant proportional-damage or movement modifiers"
        )
    actor.update(
        {
            "kind": "building",
            "layer": "ground",
            "movement": "stationary",
            "speed": 0,
            "blocking": True,
            "width": 4,
            "height": 4,
            "damage": number(stats["damagePerHit"], "Giga Inferno hit", EPSILON)
            * modifiers["damage_multiplier"],
            "attack_interval_seconds": number(
                weapon["attackSpeed"], "Giga Inferno cadence", EPSILON
            )
            * modifiers["attack_interval_multiplier"],
            "range": number(weapon["range"], "Giga Inferno range", 0)
            * modifiers["range_multiplier"],
            "target_priorities": ["unit"],
            "target_layers": ["ground", "air"],
            "attack_model": {
                "kind": "multi_target",
                "source": actor["source"],
                "target_kinds": ["unit"],
                "target_layers": ["ground", "air"],
                "maximum_hp_fraction": 0,
                "projectile": deepcopy(attack["projectile"]),
                "projectiles_per_volley": integer(
                    weapon["targets"], "Giga Inferno beam count", 1
                ),
                "allocation": attack["allocation"],
            },
        }
    )
    death = parameters["death"]
    expected = {
        "source",
        "blast_delay_seconds",
        "blast_damage_multiplier",
        "blast_radius_multiplier",
        "poison_delay_seconds",
        "poison_radius_tiles",
        "poison_max_dps_multiplier",
        "poison_duration_multiplier",
        "pulse_interval_seconds",
        "first_pulse_offset_seconds",
        "growth_by_field_age",
        "exit_linger_seconds",
        "protection_policy",
        "excluded_classes",
    }
    if set(death) != expected:
        raise InputError(
            "Town Hall death needs explicit blast and persistent poison settings"
        )
    source = identifier(death["source"], "Town Hall death evidence")
    blast_delay = number(death["blast_delay_seconds"], "Town Hall blast delay", 0)
    poison_delay = number(death["poison_delay_seconds"], "Town Hall poison delay", 0)
    radius = number(weapon["deathDamageRadius"], "Town Hall blast radius", 0) * number(
        death["blast_radius_multiplier"], "blast radius modifier", EPSILON
    )
    blast_damage = number(weapon["deathDamage"], "Town Hall blast damage", 0) * number(
        death["blast_damage_multiplier"], "blast damage modifier", 0
    )
    area = {
        "target_team": "attack",
        "target_kinds": ["unit"],
        "target_layers": ["ground", "air"],
    }
    actor["death_model"] = {
        "kind": "fixed_area_sequence_at_death",
        "geometry": "offsets_from_source_center_at_death",
        "source": source,
        "effects": [
            {
                "id": "giga-blast",
                "source": source,
                "kind": "area_damage",
                "delay_seconds": blast_delay,
                "amount": blast_damage,
                "area": {**area, "offset_x": 0, "offset_y": 0, "radius": radius},
            }
        ],
    }
    point = center(actor)
    poison = {
        "id": f"{actor['id']}:giga-poison",
        "source": source,
        "start_seconds": 0,
        "duration_seconds": number(
            weapon["deathPoisonDuration"], "Town Hall poison duration", EPSILON
        )
        * number(
            death["poison_duration_multiplier"], "poison duration modifier", EPSILON
        ),
        "maximum_dps": number(
            weapon["deathPoisonMaxDps"], "Town Hall poison max DPS", 0
        )
        * number(death["poison_max_dps_multiplier"], "poison damage modifier", 0),
        "area": {
            **area,
            "x": point[0],
            "y": point[1],
            "radius": number(
                death["poison_radius_tiles"], "Town Hall poison radius", 0
            ),
        },
        "movement_multiplier": 1
        - number(weapon["deathSpeedDecrease"], "poison movement decrease", 0, 100)
        / 100,
        "attack_rate_multiplier": 1
        - number(weapon["deathAttackRateDecrease"], "poison attack decrease", 0, 100)
        / 100,
        **{
            key: deepcopy(death[key])
            for key in (
                "pulse_interval_seconds",
                "first_pulse_offset_seconds",
                "growth_by_field_age",
                "exit_linger_seconds",
                "protection_policy",
                "excluded_classes",
            )
        },
    }
    actor["town_hall_model"] = {
        "kind": "giga_inferno_with_death_poison",
        "source": parameters["source"],
        "activation": deepcopy(parameters["activation"]),
        "poison_delay_seconds": poison_delay,
        "death_poison": poison,
    }
    actor["entity_adapter"]["weapon_level"] = weapon_level
    actor["entity_adapter"]["lifecycle_parameters"] = deepcopy(parameters)
    actor["entity_adapter"][
        "selected_statistic"
    ] = "weapon.levels.damagePerHit and separate blast/poison statistics"
    actor["entity_adapter"][
        "behavior_verification"
    ] = "conditional_Giga_lifecycle_not_replay_validated"
    return actor


def validate_town_hall_model(actor, actors):
    model = require(actor, "town_hall_model")
    if set(model) != {
        "kind",
        "source",
        "activation",
        "poison_delay_seconds",
        "death_poison",
    }:
        raise InputError(
            "Town Hall behavior must declare its complete supported lifecycle"
        )
    if model["kind"] != "giga_inferno_with_death_poison":
        raise InputError(
            "This Town Hall model cannot substitute for artillery or guardians"
        )
    identifier(model["source"], "Town Hall behavior source")
    if (
        actor["movement"] != "stationary"
        or actor["kind"] != "building"
        or not actor["counts_for_destruction"]
    ):
        raise InputError("Dormant Town Hall must be a counted stationary building")
    activation = model["activation"]
    if set(activation) != {
        "source",
        "initial_state",
        "destruction_threshold_fraction",
        "activation_delay_seconds",
    }:
        raise InputError(
            "Town Hall activation state, threshold and readiness must be explicit"
        )
    identifier(activation["source"], "Town Hall activation evidence")
    if activation["initial_state"] not in {"dormant", "active"}:
        raise InputError("Town Hall initial weapon state must be declared")
    number(
        activation["destruction_threshold_fraction"],
        "Town Hall destruction threshold",
        EPSILON,
        1,
    )
    number(activation["activation_delay_seconds"], "Town Hall activation delay", 0)
    number(model["poison_delay_seconds"], "Town Hall poison delay", 0)
    validate_hazard(model["death_poison"], actors)
    return model


class TownHallCombat:
    """Gate the live weapon and settle independently persistent death hazards."""

    def __init__(self, actors, fields, select_target):
        self.models = {
            actor["id"]: deepcopy(validate_town_hall_model(actor, actors))
            for actor in actors.values()
            if "town_hall_model" in actor
        }
        self.states = {
            key: {"activated_at": None, "reason": None} for key in self.models
        }
        self.death_poison_emitted = set()
        self.hazards = PulsedHazards(actors, fields)
        self.ordinary_select_target = select_target

    def prepare(self, actors, time, trace, *, initial_state_only=False):
        for actor_id, model in self.models.items():
            actor = actors[actor_id]
            state = self.states[actor_id]
            if not _active(actor, time) or state["activated_at"] is not None:
                continue
            if initial_state_only and model["activation"]["initial_state"] != "active":
                continue
            counted = [
                item
                for item in actors.values()
                if item["team"] == actor["team"] and item["counts_for_destruction"]
            ]
            fraction = sum(item["death_time"] is not None for item in counted) / len(
                counted
            )
            activation = model["activation"]
            reason = None
            if activation["initial_state"] == "active":
                reason = "declared_initial_active_state"
            elif actor.get("_received_damage", 0) > 0:
                reason = "actual_damage_received"
            elif fraction >= activation["destruction_threshold_fraction"] - EPSILON:
                reason = "declared_destruction_threshold"
            if reason is None:
                continue
            state.update(activated_at=time, reason=reason)
            actor["kind"] = "defense"
            actor["next_attack"] = max(
                time + activation["activation_delay_seconds"],
                actor["frozen_until"] + activation["activation_delay_seconds"],
            )
            trace.append(
                {
                    "time_seconds": time,
                    "event": "town_hall_activation",
                    "source": actor_id,
                    "reason": reason,
                    "destruction_fraction": fraction,
                    "weapon_ready_seconds": actor["next_attack"],
                }
            )
        if not initial_state_only:
            self.hazards.prepare_status(actors, time, trace)

    def select_target(self, actor, actors, time, blocked, width, height):
        if (
            actor["id"] in self.states
            and self.states[actor["id"]]["activated_at"] is None
        ):
            return None, None
        return self.ordinary_select_target(actor, actors, time, blocked, width, height)

    def settle(
        self, actors, time, trace, deaths, effect_observer=None, health_handler=None
    ):
        while True:
            deaths.settle(actors, time, trace, effect_observer, health_handler)
            for actor_id, model in self.models.items():
                actor = actors[actor_id]
                if actor["death_time"] is None or actor_id in self.death_poison_emitted:
                    continue
                self.death_poison_emitted.add(actor_id)
                field = deepcopy(model["death_poison"])
                field["start_seconds"] = (
                    actor["death_time"] + model["poison_delay_seconds"]
                )
                point = center(actor)
                field["area"]["x"], field["area"]["y"] = point
                self.hazards.schedule(field, actors, source_actor_id=actor_id)
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "town_hall_poison_release",
                        "source": actor_id,
                        "field": field["id"],
                        "start_seconds": field["start_seconds"],
                        "area": deepcopy(field["area"]),
                    }
                )
            damage = self.hazards.resolve(actors, time, trace)
            if not damage:
                break
            (health_handler or _apply_health)(actors, damage, defaultdict(float), time)
        self.prepare(actors, time, trace)

    def next_boundary(self, time):
        return self.hazards.next_boundary(time)

    def frame(self, actor):
        result = self.hazards.frame(actor)
        if actor["id"] in self.states:
            result["town_hall_weapon_active"] = (
                self.states[actor["id"]]["activated_at"] is not None
            )
            result["town_hall_activation_reason"] = self.states[actor["id"]]["reason"]
        return result

    def result(self):
        return {
            "states": deepcopy(self.states),
            "death_poison_emitted": sorted(self.death_poison_emitted),
            "hazards": self.hazards.result(),
            "activation_denominator": "declared counted defending structures in this scene",
            "full_game_prediction": False,
        }
