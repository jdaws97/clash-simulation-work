"""Conditional Druid healing chains and one-way generated Bear lifecycle.

The saved catalog contains no Bear child. Bear statistics must therefore be
provided explicitly and remain an uncalibrated hypothesis in every result.
The first-form catalog healing values are never reused as a Bear weapon.
"""

from copy import deepcopy
from math import floor, hypot

from .battle_termination import continuation_fact
from .common import InputError, identifier, integer, number, require
from .healing import SupportCombat, validate_healing_model
from .hero_pets import compile_pet_healing_policy
from .range_events import first_weapon_range_entry_delay
from .spatial import EPSILON, _active, _blocked, center, target_distance


DRUID_SOURCE = "https://supercell.com/en/games/clashofclans/blog/release-notes/june-update-full-patch-notes/"
BEAR_GAPS = {
    "status": "no_bear_child_in_saved_catalog_or_selected_extraction",
    "missing": [
        "complete_current_level_statistics",
        "attack_cadence",
        "range",
        "movement_speed",
    ],
    "primary_partial_source": "https://supercell.com/en/games/clashofclans/blog/news/january-balance-changes-3/",
    "partial_values": {
        "4": {"hitpoints": 2300, "dps": 185},
        "5": {"hitpoints": 2500, "dps": 205},
    },
    "verification": "historical_primary_note_not_complete_current_bear_statistics",
}
TRANSFORMATION_POLICIES = {
    "transformation_clock": "catalog_evolve_time_since_first_deployment",
    "freeze_timer_policy": "continues_while_frozen",
    "trigger_policy": "timeout_or_actual_hp_death_once",
    "damage_overflow_policy": "discard_at_form_boundary",
    "same_boundary_policy": "timeout_before_commands_and_damage",
    "status_transfer_policy": "clear_timed_state_recompute_continuous_fields",
    "spawn_policy": "same_position_wait_if_blocked",
    "modifier_policy": "apply_parent_troop_modifiers_to_bear_base_statistics",
}
BEAR_FIELDS = {
    "id",
    "source",
    "level",
    "statistics_status",
    "hitpoints",
    "damage_per_hit",
    "attack_interval_seconds",
    "range",
    "speed_tiles_per_second",
    "housing_space",
    "first_attack_delay_seconds",
    "wall_behavior",
}
CHAIN_FIELDS = {
    "source",
    "target_count_interpretation",
    "maximum_recipients",
    "hop_range_tiles",
    "hop_delay_seconds",
    "geometry",
    "selection",
    "membership",
    "repeats",
    "inactive_recipient",
    "source_persistence",
    "stacking_membership",
}


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise InputError(f"{label} requires every explicit field without extras")


def validate_druid_parameters(parameters, level):
    _fields(parameters, {"source", "bear", *TRANSFORMATION_POLICIES}, "Druid lifecycle")
    identifier(parameters["source"], "Druid lifecycle evidence")
    for field, expected in TRANSFORMATION_POLICIES.items():
        if parameters[field] != expected:
            raise InputError(f"Unsupported Druid {field}")
    bear = parameters["bear"]
    _fields(bear, BEAR_FIELDS, "Druid Bear statistics")
    identifier(bear["id"], "generated Bear ID")
    identifier(bear["source"], "Bear statistics evidence")
    if integer(bear["level"], "Bear level", 1) != level:
        raise InputError("Druid and generated Bear levels must match")
    if bear["statistics_status"] != "explicit_uncalibrated_hypothesis":
        raise InputError("Absent Bear catalog statistics cannot be marked calibrated")
    for field in (
        "hitpoints",
        "damage_per_hit",
        "attack_interval_seconds",
        "speed_tiles_per_second",
    ):
        number(bear[field], f"Bear {field}", EPSILON)
    for field in ("range", "first_attack_delay_seconds"):
        number(bear[field], f"Bear {field}", 0)
    integer(bear["housing_space"], "Bear response housing space", 1)
    wall = bear["wall_behavior"]
    if not isinstance(wall, dict) or wall.get("kind") not in {
        "avoid",
        "clear_obstructions",
    }:
        raise InputError("Bear must avoid or clear walls; its first form alone jumps")
    identifier(require(wall, "source"), "Bear wall evidence")
    if wall["kind"] == "avoid":
        _fields(wall, {"kind", "source"}, "Bear wall avoidance")
    else:
        _fields(wall, {"kind", "source", "route_cost"}, "Bear wall clearance")
        if wall["route_cost"] not in {
            "travel_seconds_only",
            "travel_seconds_plus_nominal_clearance",
        }:
            raise InputError("Bear wall route cost must be explicit")


def validate_chain(chain, catalog_target_count=None):
    _fields(chain, CHAIN_FIELDS, "Druid healing chain")
    identifier(chain["source"], "Druid chain evidence")
    maximum = integer(chain["maximum_recipients"], "Druid maximum recipients", 1, 5)
    if chain["target_count_interpretation"] not in {
        "catalog_counts_all_recipients",
        "catalog_counts_secondary_bounces",
    }:
        raise InputError("Druid numberOfTargets interpretation must be explicit")
    if catalog_target_count is not None:
        expected = catalog_target_count + (
            chain["target_count_interpretation"] == "catalog_counts_secondary_bounces"
        )
        if maximum != expected:
            raise InputError(
                "Druid recipient count differs from its selected catalog interpretation"
            )
    number(chain["hop_range_tiles"], "Druid hop range", 0)
    number(chain["hop_delay_seconds"], "Druid hop delay", 0)
    if chain["geometry"] not in {
        "recipient_center_to_target_footprint",
        "center_to_center",
    }:
        raise InputError("Druid hop geometry must be explicit")
    if chain["selection"] not in {
        "nearest_then_instance_id",
        "lowest_hp_fraction_then_distance",
    }:
        raise InputError("Druid hop selection must be explicit")
    for field, expected in {
        "membership": "choose_next_at_current_recipient_impact",
        "repeats": "each_actor_at_most_once_per_projectile",
        "inactive_recipient": "fizzle_remaining_chain",
        "source_persistence": "launched_chain_survives_transformation_and_source_loss",
        "stacking_membership": "predicted_current_chain_plus_due_packets",
    }.items():
        if chain[field] != expected:
            raise InputError(f"Unsupported Druid chain {field}")


def compile_druid(actor, instance, entity, row, modifiers, movement_units_per_tile):
    if (
        entity.get("id") != "druid"
        or actor["team"] != "attack"
        or actor["counts_for_destruction"]
        or instance["mode"] != "normal"
        or instance["statistics_mode"] != "normal"
        or require(instance, "attack_parameters") != {}
    ):
        raise InputError(
            "Druid requires a normal attacking healer and explicit Bear form"
        )
    parameters = require(instance, "druid_parameters")
    validate_druid_parameters(parameters, instance["level"])
    if parameters["bear"]["id"] == actor["id"]:
        raise InputError("Druid and generated Bear need distinct IDs")
    wall = require(instance, "wall_parameters")
    _fields(wall, {"kind", "source"}, "Druid wall jumping")
    if wall["kind"] != "jump_enemy_walls":
        raise InputError("Druid healing form must declare enemy-wall jumping")
    identifier(wall["source"], "Druid jump evidence")
    healing = require(instance, "healing_parameters")
    base_fields = {
        "source",
        "projectile",
        "selector",
        "stacking_group",
        "amount_multiplier",
        "chain",
    }
    if (
        not isinstance(healing, dict)
        or set(healing) - {"pet_healing_basis", "pet_healing_multiplier"} != base_fields
    ):
        raise InputError("Druid healing needs explicit chain, targeting and stacking")
    validate_chain(
        healing["chain"],
        integer(require(entity, "numberOfTargets"), "catalog Druid target count", 1),
    )
    amount_multiplier = number(
        healing["amount_multiplier"], "Druid healing multiplier", EPSILON
    )
    stats = require(require(row, "stats"), "normal")
    model = {
        "kind": "druid_chain",
        "target_kinds": ["unit"],
        "target_layers": ["ground", "air"],
        "target_classes": ["troop", "hero"],
        "amounts_by_class": {
            "troop": number(require(stats, "healingPerPulse"), "Druid troop healing", 0)
            * amount_multiplier,
            "hero": number(
                require(stats, "healingPerPulseOnHeroes"), "Druid hero healing", 0
            )
            * amount_multiplier,
        },
        **{
            key: deepcopy(healing[key])
            for key in ("source", "projectile", "selector", "stacking_group", "chain")
        },
    }
    pet_policy, pet_amount = compile_pet_healing_policy(
        healing, model["amounts_by_class"]["troop"], model["amounts_by_class"]["hero"]
    )
    if pet_policy is not None:
        model["pet_healing_policy"] = pet_policy
        if pet_policy["basis"] != "explicitly_excluded":
            model["target_classes"].append("pet")
            model["amounts_by_class"]["pet"] = pet_amount
    actor.update(
        {
            "kind": "unit",
            "layer": "ground",
            "movement": "ground",
            "speed": number(require(entity, "movementSpeed"), "Druid speed", EPSILON)
            / movement_units_per_tile
            * modifiers["movement_speed_multiplier"],
            "blocking": False,
            "width": 0,
            "height": 0,
            "damage": 0,
            "attack_interval_seconds": number(
                require(entity, "attackSpeed"), "Druid healing cadence", EPSILON
            )
            * modifiers["attack_interval_multiplier"],
            "range": number(require(entity, "range"), "Druid healing range", 0)
            * modifiers["range_multiplier"],
            "target_priorities": [],
            "target_layers": [],
            "attack_model": {"kind": "none", "source": actor["source"]},
            "healing_model": model,
            "wall_behavior": deepcopy(wall),
            "healing_class": "troop",
            "hazard_class": "troop",
            "buff_class": "troop",
            "spring_class": "troop",
            "housing_space": integer(
                require(entity, "housingSpace"), "Druid housing space", 1
            ),
            "druid_model": {
                "parameters": deepcopy(parameters),
                "evolve_seconds": number(
                    require(entity, "evolveTime"), "catalog Druid evolve time", EPSILON
                ),
                "bear_id": parameters["bear"]["id"],
                "catalog_target_count": entity["numberOfTargets"],
                "modifiers": deepcopy(modifiers),
            },
        }
    )
    actor["entity_adapter"].update(
        {
            "druid_parameters": deepcopy(parameters),
            "bear_source_audit": deepcopy(BEAR_GAPS),
            "healing_statistic": "catalog normal healingPerPulse and healingPerPulseOnHeroes",
            "behavior_verification": "explicit_uncalibrated_healing_and_transformation_hypothesis",
        }
    )
    return actor


def compile_druid_forms(actors):
    """Generate separately owned Bear reserves; they are never army inventory."""
    result = []
    ids = {actor["id"] for actor in actors}
    for parent in actors:
        if "druid_model" not in parent:
            continue
        model = parent["druid_model"]
        specification = model["parameters"]["bear"]
        key = specification["id"]
        if key in ids:
            raise InputError("Generated Bear IDs must be unique scene actors")
        ids.add(key)
        modifiers = model["modifiers"]
        damage = specification["damage_per_hit"] * modifiers["damage_multiplier"]
        interval = (
            specification["attack_interval_seconds"]
            * modifiers["attack_interval_multiplier"]
        )
        reach = specification["range"] * modifiers["range_multiplier"]
        wall = deepcopy(specification["wall_behavior"])
        if wall["kind"] == "clear_obstructions":
            wall["weapon"] = {
                "damage": damage,
                "range": reach,
                "attack_interval_seconds": interval,
                "first_attack_seconds": specification["first_attack_delay_seconds"],
                "timing": "instant",
                "cooldown": "shared_with_main_weapon",
                "source": specification["source"],
            }
        result.append(
            {
                "id": key,
                "source": specification["source"],
                "team": parent["team"],
                "kind": "unit",
                "layer": "ground",
                "movement": "ground",
                "hitpoints": specification["hitpoints"]
                * modifiers["hitpoints_multiplier"],
                "damage": damage,
                "attack_interval_seconds": interval,
                "range": reach,
                "minimum_range": 0,
                "speed": specification["speed_tiles_per_second"]
                * modifiers["movement_speed_multiplier"],
                "first_attack_seconds": specification["first_attack_delay_seconds"],
                "spawn_seconds": "controlled",
                "x": parent["x"],
                "y": parent["y"],
                "width": 0,
                "height": 0,
                "blocking": False,
                "counts_for_destruction": False,
                "target_priorities": ["defense", "building"],
                "target_priority_tiers": [["defense"], ["building"]],
                "target_layers": ["ground"],
                "attack_model": {
                    "kind": "single",
                    "source": specification["source"],
                    "target_kinds": ["defense", "building"],
                    "target_layers": ["ground"],
                    "maximum_hp_fraction": 0,
                    "projectile": {
                        "timing": "instant",
                        "delay_seconds": 0,
                        "destination": "locked_actor_center_at_impact",
                        "hit_radius": 0,
                    },
                },
                "wall_behavior": wall,
                "healing_class": "troop",
                "hazard_class": "troop",
                "buff_class": "troop",
                "spring_class": "troop",
                "housing_space": specification["housing_space"],
                "summon_model": {"kind": "druid_bear", "parent": parent["id"]},
                "druid_form_model": {
                    "parent": parent["id"],
                    "level": specification["level"],
                    "parameters": deepcopy(specification),
                },
                "druid_form_statistics": {
                    "level": specification["level"],
                    "generated_by": parent["id"],
                    "statistics_status": specification["statistics_status"],
                    "source_audit": deepcopy(BEAR_GAPS),
                    "modifiers": deepcopy(modifiers),
                },
            }
        )
    return result


class DruidSupportCombat(SupportCombat):
    """Use shared healer stacking for successive, live-selected Druid hops."""

    def __init__(self, actors, specification, base_selector):
        self.actors = actors
        chain_models = {}
        ordinary = dict(actors)
        for key, actor in actors.items():
            model = actor.get("healing_model", {})
            if model.get("kind") != "druid_chain":
                continue
            if "druid_model" not in actor:
                raise InputError(
                    "Druid healing requires its complete transformation lifecycle"
                )
            validate_chain(
                require(model, "chain"),
                require(actor["druid_model"], "catalog_target_count"),
            )
            projectile = require(model, "projectile")
            if (
                projectile.get("destination")
                not in {
                    "locked_actor_center_at_impact",
                    "fixed_target_center_at_launch",
                }
                or projectile.get("delay_seconds", 0) != 0
            ):
                raise InputError(
                    "Druid projectiles require a target destination without an extra release delay"
                )
            if model.get("target_layers") != ["ground", "air"] or "siege" in model.get(
                "target_classes", []
            ):
                raise InputError(
                    "Druid chains heal both layers and exclude siege machines"
                )
            normalized = {**deepcopy(model), "kind": "single"}
            normalized.pop("chain")
            validate_healing_model(normalized, actors)
            ordinary[key] = {**actor, "healing_model": normalized}
            chain_models[key] = deepcopy(model)
        super().__init__(ordinary, specification, base_selector)
        self.models.update(chain_models)
        for key in self.models:
            actors[key]["healing_target"] = None

    def select_target(self, actor, actors, time, blocked, width, height):
        if self.models.get(actor["id"], {}).get("kind") == "druid_chain":
            walls = {
                (item["x"], item["y"])
                for item in actors.values()
                if item["kind"] == "wall"
                and item["team"] != actor["team"]
                and _active(item, time)
            }
            blocked = blocked - walls
        return super().select_target(actor, actors, time, blocked, width, height)

    def launch(self, actor, target, time, trace):
        super().launch(actor, target, time, trace)
        if self.models[actor["id"]]["kind"] == "druid_chain":
            packet = next(
                packet for _, serial, packet in self.pending if serial == self.serial
            )
            packet["visited"] = []
            packet["hop_index"] = 0

    def _next_recipient(self, source, current, model, visited, actors, time):
        chain = model["chain"]
        choices = []
        for candidate in actors.values():
            if candidate["id"] in visited or not self._eligible_recipient(
                model, source, candidate, time
            ):
                continue
            distance = (
                target_distance(center(current), candidate)
                if chain["geometry"] == "recipient_center_to_target_footprint"
                else hypot(
                    center(current)[0] - center(candidate)[0],
                    center(current)[1] - center(candidate)[1],
                )
            )
            if distance <= chain["hop_range_tiles"] + EPSILON:
                injury = (
                    candidate["hp"] / candidate["maximum_hp"]
                    if chain["selection"] == "lowest_hp_fraction_then_distance"
                    else 0
                )
                choices.append((injury, distance, candidate["id"], candidate))
        return min(choices, key=lambda item: item[:3])[-1] if choices else None

    def _packet_recipients(self, packet, actors, time, trace):
        model = self.models[packet["source"]]
        if model["kind"] != "druid_chain":
            return super()._packet_recipients(packet, actors, time, trace)
        source = actors[packet["source"]]
        target = actors[packet["target"]]
        point = (
            center(target)
            if model["projectile"]["destination"] == "locked_actor_center_at_impact"
            else packet["position"]
        )
        if (
            not self._eligible_recipient(model, source, target, time)
            or target_distance(point, target)
            > model["projectile"]["hit_radius"] + EPSILON
        ):
            trace.append(
                {
                    "event": "druid_chain_fizzle",
                    "time_seconds": time,
                    "source": source["id"],
                    "target": target["id"],
                }
            )
            return []
        visited = [*packet["visited"], target["id"]]
        chain = model["chain"]
        following = None
        if len(visited) < chain["maximum_recipients"]:
            following = self._next_recipient(
                source, target, model, visited, actors, time
            )
        if following is not None:
            self._queue(
                {
                    **packet,
                    "target": following["id"],
                    "position": center(following),
                    "visited": visited,
                    "hop_index": packet["hop_index"] + 1,
                },
                time + chain["hop_delay_seconds"],
            )
        trace.append(
            {
                "event": "druid_chain_link",
                "time_seconds": time,
                "source": source["id"],
                "target": target["id"],
                "hop_index": packet["hop_index"],
                "next_target": following["id"] if following is not None else None,
            }
        )
        return [target]

    def _assigned_contributors(self, group_id, target, actors, time):
        # Base radial/single contributors retain their original conventions.
        ordinary = {
            key: model
            for key, model in self.models.items()
            if model["kind"] != "druid_chain"
        }
        chains = self.models
        self.models = ordinary
        try:
            contributors = super()._assigned_contributors(
                group_id, target, actors, time
            )
        finally:
            self.models = chains
        for key, model in self.models.items():
            if model["kind"] != "druid_chain" or model["stacking_group"] != group_id:
                continue
            source = actors[key]
            current = actors.get(source.get("healing_target"))
            if (
                not _active(source, time)
                or source["frozen_until"] > time + EPSILON
                or current is None
                or not self._eligible_recipient(model, source, current, time)
                or target_distance(center(source), current) > source["range"] + EPSILON
            ):
                continue
            visited = []
            while (
                current is not None
                and len(visited) < model["chain"]["maximum_recipients"]
            ):
                visited.append(current["id"])
                current = self._next_recipient(
                    source, current, model, visited, actors, time
                )
            if target["id"] in visited:
                contributors.add(key)
        return contributors

    def first_crossing_delay(self, actors, motions, time, horizon):
        """Locate exact contact with moving allies for the shared healing clock."""
        crossing = None
        for source_id, model in self.models.items():
            source = actors[source_id]
            target = actors.get(source.get("healing_target"))
            if (
                not _active(source, time)
                or source["frozen_until"] > time + EPSILON
                or target is None
                or not self._eligible_primary(model, source, target, time)
            ):
                continue
            source_route, source_speed = motions.get(source_id, ((), 0))
            target_route, target_speed = motions.get(target["id"], ((), 0))
            candidate = first_weapon_range_entry_delay(
                source,
                target,
                source_route,
                target_route,
                source_speed,
                target_speed,
                horizon if crossing is None else min(horizon, crossing),
            )
            if candidate is not None:
                crossing = candidate if crossing is None else min(crossing, candidate)
        return crossing


def validate_druid_deployment(command, actors):
    if command.get("kind") == "deploy" and any(
        "druid_form_model" in actors[key] for key in command.get("targets", [])
    ):
        raise InputError("Generated Druid Bear forms cannot be independently deployed")


class DruidCombat:
    """Retire the healer once, then release its separately owned Bear."""

    def __init__(self, actors):
        self.actors = actors
        self.models = {}
        self.states = {}
        self.release_revision = 0
        children = set()
        for key, actor in actors.items():
            if "druid_model" not in actor:
                continue
            model = deepcopy(actor["druid_model"])
            level = actor.get("entity_adapter", {}).get("level")
            validate_druid_parameters(require(model, "parameters"), level)
            number(
                require(model, "evolve_seconds"), "Druid transformation delay", EPSILON
            )
            child_id = require(model, "bear_id")
            child = actors.get(child_id)
            if (
                child is None
                or child_id in children
                or child.get("druid_form_model", {}).get("parent") != key
                or child.get("spawn_seconds") != "controlled"
                or child.get("team") != actor["team"]
                or actor["team"] != "attack"
            ):
                raise InputError(
                    "Every Druid needs one unique controlled Bear with matching ownership"
                )
            if (
                any(
                    participant.get("kind") != "unit"
                    or participant.get("movement") != "ground"
                    or participant.get("layer") != "ground"
                    or participant.get("counts_for_destruction")
                    for participant in (actor, child)
                )
                or actor.get("healing_model", {}).get("kind") != "druid_chain"
                or actor["damage"] != 0
                or actor.get("wall_behavior", {}).get("kind") != "jump_enemy_walls"
                or child["druid_form_model"].get("parameters")
                != model["parameters"]["bear"]
                or child.get("summon_model") != {"kind": "druid_bear", "parent": key}
            ):
                raise InputError(
                    "Druid forms must preserve their declared roles and child statistics"
                )
            children.add(child_id)
            self.models[key] = model
            self.states[key] = {
                "phase": "waiting_for_deployment",
                "deployed_at": None,
                "transform_at": None,
                "transformed_at": None,
                "reason": None,
                "released_at": None,
                "position": None,
            }
        if {
            key for key, actor in actors.items() if "druid_form_model" in actor
        } != children:
            raise InputError("Generated Bear forms require exactly one owning Druid")

    def validate_command(self, command):
        validate_druid_deployment(command, self.actors)

    def _transform(self, key, time, reason, trace):
        state = self.states[key]
        if state["phase"] != "healer":
            return False
        actor = self.actors[key]
        state.update(
            {
                "phase": "pending_bear",
                "transformed_at": time,
                "reason": reason,
                "position": center(actor),
            }
        )
        actor["hp"] = 0
        actor["death_time"] = time
        actor["target"] = None
        actor["healing_target"] = None
        trace.append(
            {
                "event": "druid_transform",
                "time_seconds": time,
                "source": key,
                "bear": self.models[key]["bear_id"],
                "reason": reason,
            }
        )
        self._release(key, time, trace)
        return True

    def _release(self, key, time, trace):
        state = self.states[key]
        if state["phase"] != "pending_bear":
            return False
        x, y = state["position"]
        if (floor(x), floor(y)) in _blocked(self.actors, time):
            return False
        model = self.models[key]
        bear = self.actors[model["bear_id"]]
        bear["x"], bear["y"] = x, y
        bear["spawn_seconds"] = time
        bear["hp"] = bear["maximum_hp"]
        bear["death_time"] = None
        bear["frozen_until"] = 0
        bear["immune_until"] = 0
        delay = model["parameters"]["bear"]["first_attack_delay_seconds"]
        bear["next_attack"] = time + delay
        if "_wall_next_attack" in bear:
            bear["_wall_next_attack"] = time + delay
        state.update({"phase": "bear", "released_at": time})
        self.release_revision += 1
        trace.append(
            {
                "event": "druid_bear_release",
                "time_seconds": time,
                "source": key,
                "bear": bear["id"],
                "position": {"x": x, "y": y},
            }
        )
        return True

    def prepare(self, time, trace):
        changed = False
        for key, state in self.states.items():
            actor = self.actors[key]
            if state["phase"] == "waiting_for_deployment" and _active(actor, time):
                state.update(
                    {
                        "phase": "healer",
                        "deployed_at": actor["spawn_seconds"],
                        "transform_at": actor["spawn_seconds"]
                        + self.models[key]["evolve_seconds"],
                    }
                )
            if state["phase"] == "healer":
                if actor["hp"] <= 0:
                    # Only the health interceptor authorizes first-form death.
                    # Ejection/removal must never silently create a Bear.
                    state["phase"] = "removed_without_bear"
                elif state["transform_at"] <= time + EPSILON:
                    if state["transform_at"] < time - EPSILON:
                        raise InputError("Druid transformation boundary was skipped")
                    changed |= self._transform(key, time, "timeout", trace)
            changed |= self._release(key, time, trace)
            if (
                state["phase"] == "bear"
                and self.actors[self.models[key]["bear_id"]]["hp"] <= 0
            ):
                state["phase"] = "dead"
        return changed

    def intercept_lethal(self, actor, time, trace):
        key = actor["id"]
        if key in self.states:
            state = self.states[key]
            spawn = actor["spawn_seconds"]
            if (
                state["phase"] == "waiting_for_deployment"
                and spawn != "controlled"
                and spawn <= time + EPSILON
            ):
                state.update(
                    {
                        "phase": "healer",
                        "deployed_at": spawn,
                        "transform_at": spawn + self.models[key]["evolve_seconds"],
                    }
                )
            self._transform(key, time, "actual_hp_death", trace)
        # The first form is retired; interception never rescues that actor.
        return False

    def next_boundary(self, time):
        return min(
            (
                state["transform_at"]
                for state in self.states.values()
                if state["phase"] == "healer" and state["transform_at"] > time + EPSILON
            ),
            default=None,
        )

    def continuation_reasons(self, time):
        return [
            continuation_fact(
                "pending_release",
                f"druid-bear:{key}",
                [key, self.models[key]["bear_id"]],
                source_team=self.actors[key]["team"],
                not_before_seconds=state["transformed_at"],
            )
            for key, state in self.states.items()
            if state["phase"] == "pending_bear"
        ]

    def frame(self, actor):
        owner_id = (
            actor["id"]
            if actor["id"] in self.models
            else actor.get("druid_form_model", {}).get("parent")
        )
        if owner_id not in self.states:
            return {}
        return {
            "druid_owner": owner_id,
            "druid_lifecycle_phase": self.states[owner_id]["phase"],
            "druid_transform_at": self.states[owner_id]["transform_at"],
        }

    def result(self):
        return {
            "druids": deepcopy(self.states),
            "bear_source_audit": deepcopy(BEAR_GAPS),
            "replay_validated": False,
        }
