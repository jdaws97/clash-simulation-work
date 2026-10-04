"""Conditional Dragon Duke isolation, Revenge Deck, and Fire Heart behavior.

The catalog supplies named statistics. Missing geometry, event ordering and
membership rules remain explicit hypotheses, rather than implied game facts.
"""

from collections import defaultdict
from copy import deepcopy
from heapq import heappop, heappush
from math import floor, hypot, sqrt

from .common import InputError, identifier, integer, number, require
from .hero_extensions import (
    parameter_provenance,
    require_fields as _exact,
    require_values as _values,
    source_quantity as _quantity,
    validate_locked_projectile as _projectile,
    validate_parameter_provenance,
)
from .range_events import _position, _segments
from .rates import rescale_remaining_cooldown
from .spatial import EPSILON, _active, center, target_distance


EQUIPMENT = {"revenge-deck", "fire-heart"}
AIR_CLASSES = {"troop", "hero", "pet", "siege", "guardian"}
SAMPLED_MEMBERSHIP = "center_distance_sampled_inclusive_experimental"


def validate_isolation_update(parameters):
    policy = parameters.get("isolation_update")
    if policy is None and "isolation_update" not in parameters:
        if parameters["membership"] != "center_distance_inside_after_motion_hypothesis":
            raise InputError("Unsupported Duke intrinsic membership policy")
        return
    _exact(
        policy,
        {"mode", "source", "status", "interval_seconds", "clock", "between_samples"},
        "Experimental Duke isolation update",
    )
    identifier(policy["source"], "Duke isolation-update source")
    number(policy["interval_seconds"], "Duke isolation-update interval", 0.001)
    expected = {
        "mode": "fixed_cadence_experimental",
        "status": "explicit_uncalibrated_hypothesis",
        "clock": "deployment_anchored_resample_on_reactivation",
        "between_samples": "hold_all_membership_including_lifecycle_changes",
    }
    if any(policy[key] != value for key, value in expected.items()) or (
        parameters["membership"] != SAMPLED_MEMBERSHIP
    ):
        raise InputError("Unsupported experimental Duke isolation-update contract")


def compile_duke_intrinsic(instance, entity, catalog):
    if instance.get("entity") != "dragon-duke" or entity.get("id") != "dragon-duke":
        raise InputError("Duke intrinsic parameters require the matching catalog hero")
    parameters = deepcopy(require(instance, "duke_parameters"))
    model = {
        "entity": "dragon-duke",
        "source": catalog.records["dragon-duke"]["source"],
        "source_description": entity["description"],
        "parameter_provenance": parameter_provenance(parameters),
        "parameters": parameters,
        "nearby_range": number(entity["range"], "Duke nearby-air range", 0),
        "isolated_damage_multiplier": 2,
        "isolated_attack_rate_multiplier": 1.5,
        "isolated_trap_damage_multiplier": 0.5,
    }
    validate_duke_intrinsic(model)
    return model


def validate_duke_intrinsic(model):
    _exact(
        model,
        {
            "entity",
            "source",
            "parameters",
            "source_description",
            "parameter_provenance",
            "nearby_range",
            "isolated_damage_multiplier",
            "isolated_attack_rate_multiplier",
            "isolated_trap_damage_multiplier",
        },
        "Duke intrinsic model",
    )
    if model["entity"] != "dragon-duke":
        raise InputError("Duke intrinsic behavior cannot attach to another hero")
    identifier(model["source"], "Duke statistic source")
    number(model["nearby_range"], "Duke nearby range", 0)
    for field, expected in (
        ("isolated_damage_multiplier", 2),
        ("isolated_attack_rate_multiplier", 1.5),
        ("isolated_trap_damage_multiplier", 0.5),
    ):
        if model[field] != expected:
            raise InputError(
                "Duke intrinsic multipliers must match the source description"
            )
    parameters = model["parameters"]
    optional = (
        {"isolation_update"}
        if isinstance(parameters, dict) and "isolation_update" in parameters
        else set()
    )
    _exact(
        parameters,
        {
            "source",
            "friendly_air_radius_tiles",
            "friendly_air_classes",
            "friendly_air_visibility",
            "friendly_air_frozen",
            "friendly_air_inactive",
            "isolated_range_tiles",
            "nearby_projectile",
            "isolated_projectile",
            "membership",
            "stacking",
            "rampage_damage_scope",
        }
        | optional,
        "Duke intrinsic parameters",
    )
    identifier(parameters["source"], "Duke behavior source")
    number(parameters["friendly_air_radius_tiles"], "Duke friendly-air radius", EPSILON)
    number(parameters["isolated_range_tiles"], "Duke isolated range", 0)
    _values(
        parameters["friendly_air_classes"], AIR_CLASSES, "Duke friendly-air classes"
    )
    for field, expected in (
        ("friendly_air_visibility", "include_invisible"),
        ("friendly_air_frozen", "include_frozen"),
        ("friendly_air_inactive", "exclude_reserves_dead_and_phoenix_eggs"),
        ("stacking", "multiply_independent_damage_and_attack_rate_factors"),
        ("rampage_damage_scope", "ordinary_weapon_only_hypothesis"),
    ):
        if parameters[field] != expected:
            raise InputError("Unsupported Duke intrinsic policy")
    validate_isolation_update(parameters)
    _projectile(parameters["nearby_projectile"])
    _projectile(parameters["isolated_projectile"])
    validate_parameter_provenance(model)


def compile_duke_equipment(instance, hero, catalog):
    _exact(instance, {"entity", "level", "parameters"}, "Duke equipment")
    entity_id = instance["entity"]
    if entity_id not in EQUIPMENT or hero["entity"] != "dragon-duke":
        raise InputError("Unsupported Duke equipment owner or item")
    level = integer(instance["level"], "Duke equipment level", 1)
    if not catalog.available(entity_id, level, hero["town_hall"]):
        raise InputError("Duke equipment level is unavailable at this Town Hall")
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
    if entity_id == "revenge-deck":
        model.update(
            counter_damage=stats["counterDamage"],
            heal_per_counter=stats["healPerCounter"],
            counter_range=_quantity(entity["ability"]["maxCounterRange"], "tiles"),
            counter_cooldown_seconds=_quantity(
                entity["ability"]["counterCooldown"], "s"
            ),
        )
    else:
        model.update(
            self_healing_per_second=stats["selfHealingPerSecond"],
            death_damage=stats["damageOnDefeat"],
            death_radius=_quantity(entity["ability"]["damageRadius"], "tiles"),
        )
    validate_duke_equipment(model)
    return model, row


def validate_duke_equipment(model):
    common = {
        "entity",
        "level",
        "ability_type",
        "source",
        "behavior_source",
        "parameters",
        "source_description",
        "parameter_provenance",
    }
    entity_id = require(model, "entity")
    additions = {
        "revenge-deck": {
            "counter_damage",
            "heal_per_counter",
            "counter_range",
            "counter_cooldown_seconds",
        },
        "fire-heart": {"self_healing_per_second", "death_damage", "death_radius"},
    }
    if entity_id not in additions:
        raise InputError("Unsupported Duke equipment runtime entity")
    _exact(model, common | additions[entity_id], "Duke equipment runtime model")
    if model["ability_type"] != "Passive":
        raise InputError("Duke Deck and Heart use passive equipment behavior")
    integer(model["level"], "runtime Duke equipment level", 1)
    identifier(model["source"], "runtime Duke equipment source")
    identifier(model["behavior_source"], "runtime Duke behavior source")
    for field in additions[entity_id]:
        number(
            model[field], field, EPSILON if field == "counter_cooldown_seconds" else 0
        )
    parameters = model["parameters"]
    common_parameters = {"source", "damage_scaling"}
    if entity_id == "revenge-deck":
        fields = {
            "projectile",
            "trigger",
            "source_origins",
            "counter_timing",
            "cooldown",
            "heal",
            "freeze",
            "ineligible_source",
            "source_death",
        }
        policies = {
            "trigger": "positive_actual_hp_loss_from_live_hostile_actor",
            "counter_timing": "after_same_timestamp_health_if_duke_survives",
            "cooldown": "shared_across_sources_first_receipt_order_no_catchup",
            "heal": "on_counter_launch",
            "freeze": "block_counter_without_retaining_receipts",
            "ineligible_source": "discard_receipt",
            "source_death": "released_counter_persists",
        }
    else:
        fields = {
            "self_heal_interval_seconds",
            "first_self_heal_delay_seconds",
            "freeze",
            "death_delay_seconds",
            "death_target_kinds",
            "death_target_layers",
            "protection",
            "lethal_trigger",
            "removal_trigger",
            "death_position",
        }
        policies = {
            "freeze": "healing_clock_continues_while_frozen",
            "protection": "respect_invulnerability",
            "lethal_trigger": "actual_death_after_lethal_interception",
            "removal_trigger": "exclude_physical_ejection_include_phoenix_final_defeat",
            "death_position": "capture_center_at_actual_death",
        }
    _exact(parameters, common_parameters | fields, "Duke equipment parameters")
    identifier(parameters["source"], "Duke equipment parameter source")
    validate_parameter_provenance(model)
    if (
        parameters["damage_scaling"]
        != "equipment_flat_damage_times_hero_profile_only_hypothesis"
    ):
        raise InputError("Duke equipment damage scaling must be explicit")
    for field, expected in policies.items():
        if parameters[field] != expected:
            raise InputError("Unsupported Duke equipment lifecycle policy")
    if entity_id == "revenge-deck":
        _projectile(parameters["projectile"])
        _values(
            parameters["source_origins"],
            {"weapon", "trap", "hazard", "death", "ability", "scripted"},
            "Revenge Deck triggering origins",
        )
    else:
        interval = number(
            parameters["self_heal_interval_seconds"], "Heart heal interval", EPSILON
        )
        number(
            parameters["first_self_heal_delay_seconds"],
            "Heart first heal delay",
            0,
            interval,
        )
        number(parameters["death_delay_seconds"], "Heart death delay", 0)
        _values(
            parameters["death_target_kinds"],
            {"unit", "defense", "building", "wall"},
            "Heart target kinds",
        )
        _values(
            parameters["death_target_layers"], {"ground", "air"}, "Heart target layers"
        )


def first_relative_circle_crossing(
    first,
    second,
    first_route,
    second_route,
    first_speed,
    second_speed,
    radius,
    horizon,
    currently_inside,
):
    """Find an entry or exit of a moving circle with the declared after-side.

    Tangency does not change sustained membership. A start exactly on an edge
    may produce a two-epsilon delay, avoiding a zero-time boundary loop.
    """
    if horizon <= EPSILON:
        return None
    # Look just beyond the search limit to classify an exact endpoint contact.
    # Finite routes still stop at their final waypoint within this extension.
    extended_horizon = horizon + EPSILON * 256
    first_segments = _segments(first, first_route, first_speed, extended_horizon)
    second_segments = _segments(second, second_route, second_speed, extended_horizon)
    first_index = second_index = 0
    state = currently_inside
    while first_index < len(first_segments) and second_index < len(second_segments):
        a = first_segments[first_index]
        b = second_segments[second_index]
        start, end = max(a[0], b[0]), min(a[1], b[1])
        pa, pb = _position(a, start), _position(b, start)
        delta = (pa[0] - pb[0], pa[1] - pb[1])
        velocity = (a[3][0] - b[3][0], a[3][1] - b[3][1])
        speed_squared = velocity[0] ** 2 + velocity[1] ** 2
        contacts = [0.0, end - start]
        if speed_squared > EPSILON**2:
            projection = delta[0] * velocity[0] + delta[1] * velocity[1]
            constant = delta[0] ** 2 + delta[1] ** 2 - radius**2
            discriminant = projection**2 - speed_squared * constant
            if discriminant >= -EPSILON:
                root = sqrt(max(discriminant, 0))
                for numerator in (-projection - root, -projection + root):
                    offset = numerator / speed_squared
                    if -EPSILON <= offset <= end - start + EPSILON:
                        # Roundoff at a committed contact can create a tiny
                        # interval between zero and the same quadratic root.
                        # Classifying that interval invents an opposite side.
                        # Canonicalize contacts within the existing time
                        # resolution before choosing sustained after-sides.
                        if abs(offset) <= EPSILON:
                            offset = 0.0
                        elif abs(offset - (end - start)) <= EPSILON:
                            offset = end - start
                        contacts.append(max(0.0, min(end - start, offset)))
        contacts = sorted(set(contacts))
        for index, offset in enumerate(contacts):
            if index + 1 < len(contacts):
                probe = (offset + contacts[index + 1]) / 2
                inside_after = (
                    hypot(
                        delta[0] + velocity[0] * probe,
                        delta[1] + velocity[1] * probe,
                    )
                    <= radius
                )
            elif end >= extended_horizon - EPSILON:
                inside_after = (
                    hypot(
                        delta[0] + velocity[0] * offset,
                        delta[1] + velocity[1] * offset,
                    )
                    <= radius
                )
            else:
                continue
            if inside_after != state:
                delay = max(start + offset, 2 * EPSILON)
                if delay <= horizon + EPSILON:
                    return {
                        "delay_seconds": delay,
                        "inside_after": inside_after,
                        "first_position": _position(a, min(start + offset, end)),
                        "second_position": _position(b, min(start + offset, end)),
                    }
            state = inside_after
        if a[1] <= end + EPSILON:
            first_index += 1
        if b[1] <= end + EPSILON:
            second_index += 1
    return None


class DragonDukeCombat:
    """Composition hooks for the common hero ability and health lifecycle."""

    def __init__(self, actors, combat):
        self.models = {}
        self.equipment = {}
        self.base_patterns = {}
        self.membership = {}
        self.crossing_hints = {}
        self.boundary_sides = {}
        self.sample_next = {}
        self.sample_nearby = {}
        self.sample_counts = defaultdict(int)
        self.heal_next = {}
        self.counter_ready = {}
        self.dead = set()
        self.heart_released = set()
        self.packets = []
        self.sequence = 0
        self.log = []
        self.combat = combat
        for key, actor in actors.items():
            if actor.get("hero_model", {}).get("entity") != "dragon-duke":
                if "duke_model" in actor:
                    raise InputError("Duke intrinsic model requires its matching hero")
                continue
            model = deepcopy(require(actor, "duke_model"))
            validate_duke_intrinsic(model)
            if (
                actor["team"] != "attack"
                or actor["layer"] != "air"
                or actor["kind"] != "unit"
            ):
                raise InputError("Duke requires the attacking flying hero role")
            self.models[key] = model
            self.base_patterns[key] = deepcopy(actor["attack_model"])
            self.equipment[key] = {}
            for item in actor["hero_model"]["equipment"]:
                validate_duke_equipment(item)
                if item["entity"] in self.equipment[key]:
                    raise InputError("Duke equipment cannot be duplicated")
                self.equipment[key][item["entity"]] = deepcopy(item)
            self.heal_next[key] = None
            self.counter_ready[key] = 0

    @staticmethod
    def _air_class(actor):
        if "pet_model" in actor:
            return "pet"
        if "hero_model" in actor:
            return "hero"
        return actor.get("buff_class", actor.get("healing_class"))

    def _friendly(self, duke, other, time, parameters):
        return (
            other["id"] != duke["id"]
            and _active(other, time)
            and other["team"] == duke["team"]
            and other["kind"] == "unit"
            and other["layer"] == "air"
            and not other.get("_pet_phoenix_egg", False)
            and self._air_class(other) in parameters["friendly_air_classes"]
        )

    def _inside(self, key, duke, other, radius):
        side = self.boundary_sides.get(key)
        if side is not None:
            if (
                hypot(*(center(duke)[i] - side["first_position"][i] for i in (0, 1)))
                <= EPSILON * 128
                and hypot(
                    *(center(other)[i] - side["second_position"][i] for i in (0, 1))
                )
                <= EPSILON * 128
            ):
                return side["inside_after"]
            self.boundary_sides.pop(key)
        return (
            hypot(
                center(duke)[0] - center(other)[0], center(duke)[1] - center(other)[1]
            )
            <= radius + EPSILON
        )

    def prepare(self, actors, time, trace):
        for key, hint in list(self.crossing_hints.items()):
            if hint["time_seconds"] <= time + EPSILON:
                if abs(hint["time_seconds"] - time) <= EPSILON:
                    self.boundary_sides[key] = hint
                self.crossing_hints.pop(key)
        for key, model in self.models.items():
            duke = actors[key]
            if not _active(duke, time):
                self.sample_next.pop(key, None)
                continue
            parameters = model["parameters"]
            policy = parameters.get("isolation_update")
            sample_due = (
                policy is None
                or key not in self.sample_next
                or time >= self.sample_next[key] - EPSILON
            )
            if sample_due:
                nearby = []
                for other_id, other in actors.items():
                    pair = (key, other_id)
                    inside = self._friendly(
                        duke, other, time, parameters
                    ) and self._inside(
                        pair, duke, other, parameters["friendly_air_radius_tiles"]
                    )
                    self.membership[pair] = inside
                    if inside:
                        nearby.append(other_id)
                if policy is not None:
                    self.sample_nearby[key] = nearby
                    self.sample_counts[key] += 1
                    interval = policy["interval_seconds"]
                    # Integer ticks prevent accumulated clock drift. Missed
                    # inactive ticks are skipped, never replayed as combat.
                    tick = floor((time - duke["spawn_seconds"] + EPSILON) / interval)
                    self.sample_next[key] = (
                        duke["spawn_seconds"] + (tick + 1) * interval
                    )
            else:
                nearby = self.sample_nearby[key]
            isolated = not nearby
            previous = duke.get("_duke_isolated")
            new_rate = model["isolated_attack_rate_multiplier"] if isolated else 1
            old_rate = duke.get("_hero_attack_rate", 1)
            if abs(old_rate - new_rate) > EPSILON:
                rescale_remaining_cooldown(duke, time, old_rate, new_rate)
            duke["_hero_attack_rate"] = new_rate
            duke["_hero_damage_multiplier"] = (
                model["isolated_damage_multiplier"] if isolated else 1
            )
            duke["_hero_trap_damage_multiplier"] = (
                model["isolated_trap_damage_multiplier"] if isolated else 1
            )
            duke["_duke_isolated"] = isolated
            duke["range"] = (
                parameters["isolated_range_tiles"]
                if isolated
                else model["nearby_range"]
            ) * duke["hero_model"]["range_multiplier"]
            pattern = deepcopy(self.base_patterns[key])
            pattern["projectile"] = deepcopy(
                parameters["isolated_projectile"]
                if isolated
                else parameters["nearby_projectile"]
            )
            duke["attack_model"] = pattern
            self.combat.patterns[key] = pattern
            if previous != isolated:
                entry = {
                    "event": "dragon_duke_isolation_changed",
                    "time_seconds": time,
                    "source": key,
                    "isolated": isolated,
                    "nearby_friendly_air": sorted(nearby),
                }
                if policy is not None:
                    entry["isolation_update_mode"] = policy["mode"]
                    entry["isolation_sample_count"] = self.sample_counts[key]
                trace.append(entry)
                self.log.append(deepcopy(entry))
            heart = self.equipment[key].get("fire-heart")
            if heart is not None and self.heal_next[key] is None:
                self.heal_next[key] = (
                    duke["spawn_seconds"]
                    + heart["parameters"]["first_self_heal_delay_seconds"]
                )

    def first_crossing_delay(self, actors, routes, speeds, time, horizon):
        earliest = None
        for key, model in self.models.items():
            duke = actors[key]
            if not _active(duke, time):
                continue
            parameters = model["parameters"]
            if "isolation_update" in parameters:
                # This explicitly selected model changes membership only at
                # sample boundaries, scheduled through next_boundary().
                continue
            for other_id, other in actors.items():
                pair = (key, other_id)
                self.crossing_hints.pop(pair, None)
                if not self._friendly(duke, other, time, parameters):
                    continue
                crossing = first_relative_circle_crossing(
                    duke,
                    other,
                    routes.get(key, []),
                    routes.get(other_id, []),
                    speeds.get(key, 0),
                    speeds.get(other_id, 0),
                    parameters["friendly_air_radius_tiles"],
                    horizon,
                    self.membership.get(
                        pair,
                        self._inside(
                            pair, duke, other, parameters["friendly_air_radius_tiles"]
                        ),
                    ),
                )
                if crossing is None:
                    continue
                # A committed after-side must remain compatible with the next
                # motion. Opposing vector fields can otherwise produce an
                # infinite relay of two-epsilon events at the same contact.
                # Reject this unresolved boundary policy instead of inventing
                # hysteresis, skipping a crossing, or changing actor motion.
                side = self.boundary_sides.get(pair)
                if (
                    side is not None
                    and crossing["inside_after"] != side["inside_after"]
                    and time - side["time_seconds"] <= EPSILON * 128
                    and all(
                        hypot(
                            crossing[field][0] - side[field][0],
                            crossing[field][1] - side[field][1],
                        )
                        <= EPSILON * 128
                        for field in ("first_position", "second_position")
                    )
                ):
                    raise InputError(
                        "Unsupported Dragon Duke isolation boundary chatter: "
                        f"duke={key!r}, friendly_air={other_id!r}, "
                        f"time_seconds={time!r}, "
                        f"radius_tiles={parameters['friendly_air_radius_tiles']!r}, "
                        "membership=center_distance_inside_after_motion_hypothesis; "
                        "new motion immediately reverses a committed crossing. "
                        "A declared contact dynamics policy is required."
                    )
                delay = crossing.pop("delay_seconds")
                self.crossing_hints[pair] = {**crossing, "time_seconds": time + delay}
                earliest = delay if earliest is None else min(earliest, delay)
        return earliest

    def _queue(self, packet):
        heappush(self.packets, (packet["arrival_seconds"], self.sequence, packet))
        self.sequence += 1

    def after_health(self, actors, receipts, time, trace):
        """Run after real health changes and the pet lethal-interception hook."""
        healing = defaultdict(float)
        for receipt in receipts:
            key = receipt["target_id"]
            deck = self.equipment.get(key, {}).get("revenge-deck")
            if deck is None or receipt["actual_health_loss"] <= EPSILON:
                continue
            duke = actors[key]
            source_id = receipt["source_actor_id"]
            source = actors.get(source_id)
            if (
                not _active(duke, time)
                or duke["frozen_until"] > time + EPSILON
                or self.counter_ready[key] > time + EPSILON
                or source is None
                or not _active(source, time)
                or source["team"] == duke["team"]
                or receipt["source_team"] != source["team"]
                or receipt["origin"] not in deck["parameters"]["source_origins"]
                or target_distance(center(duke), source)
                > deck["counter_range"] + EPSILON
            ):
                continue
            projectile = deck["parameters"]["projectile"]
            delay = projectile["delay_seconds"]
            if projectile["timing"] == "launch_distance_delay":
                delay += (
                    hypot(
                        center(duke)[0] - center(source)[0],
                        center(duke)[1] - center(source)[1],
                    )
                    / projectile["speed_tiles_per_second"]
                )
            self._queue(
                {
                    "kind": "revenge_counter",
                    "arrival_seconds": time + delay,
                    "source": key,
                    "source_team": duke["team"],
                    "target": source_id,
                    "damage": deck["counter_damage"]
                    * duke["hero_model"]["damage_multiplier"],
                }
            )
            self.counter_ready[key] = time + deck["counter_cooldown_seconds"]
            healing[key] += deck["heal_per_counter"]
            trace.append(
                {
                    "event": "revenge_deck_counter_launched",
                    "time_seconds": time,
                    "source": key,
                    "target": source_id,
                    "trigger_receipt": receipt["sequence"],
                    "arrival_seconds": time + delay,
                }
            )
        for key in self.models:
            duke = actors[key]
            if key in self.dead or duke["hp"] > 0 or duke.get("death_time") is None:
                continue
            self.dead.add(key)
            heart = self.equipment[key].get("fire-heart")
            if heart is None or duke.get("removal") is not None:
                continue
            self._queue(
                {
                    "kind": "fire_heart_death",
                    "arrival_seconds": time
                    + heart["parameters"]["death_delay_seconds"],
                    "source": key,
                    "source_team": duke["team"],
                    "point": center(duke),
                    "damage": heart["death_damage"]
                    * duke["hero_model"]["damage_multiplier"],
                    "radius": heart["death_radius"],
                    "target_kinds": heart["parameters"]["death_target_kinds"],
                    "target_layers": heart["parameters"]["death_target_layers"],
                    "collateral_policy": duke["attack_model"].get(
                        "defending_unit_collateral_policy", "allow"
                    ),
                }
            )
            self.heart_released.add(key)
            trace.append(
                {
                    "event": "fire_heart_death_released",
                    "time_seconds": time,
                    "source": key,
                }
            )
        return healing

    def resolve(self, actors, time, trace, receipts=None):
        damage = defaultdict(float)
        healing = defaultdict(float)
        for key, clock in self.heal_next.items():
            if (
                clock is None
                or clock > time + EPSILON
                or not _active(actors[key], time)
            ):
                continue
            heart = self.equipment[key]["fire-heart"]
            interval = heart["parameters"]["self_heal_interval_seconds"]
            healing[key] += heart["self_healing_per_second"] * interval
            self.heal_next[key] += interval
        while self.packets and self.packets[0][0] <= time + EPSILON:
            _, _, packet = heappop(self.packets)
            targets = []
            if packet["kind"] == "revenge_counter":
                candidate = actors[packet["target"]]
                if _active(candidate, time):
                    targets = [candidate]
            else:
                from .defending_heroes import defending_collateral_eligible

                for candidate in actors.values():
                    if (
                        _active(candidate, time)
                        and candidate["team"] != packet["source_team"]
                        and candidate["kind"] in packet["target_kinds"]
                        and candidate["layer"] in packet["target_layers"]
                        and target_distance(packet["point"], candidate)
                        <= packet["radius"] + EPSILON
                        and defending_collateral_eligible(
                            {
                                "pattern": {
                                    "defending_unit_collateral_policy": packet[
                                        "collateral_policy"
                                    ]
                                },
                                "target": None,
                            },
                            candidate,
                        )
                    ):
                        targets.append(candidate)
            for target in targets:
                amount = packet["damage"]
                if receipts is not None:
                    amount = receipts.register(
                        target,
                        amount,
                        time,
                        source_id=packet["source"],
                        source_actor_id=packet["source"],
                        source_team=packet["source_team"],
                        origin=(
                            "revenge_counter"
                            if packet["kind"] == "revenge_counter"
                            else "death"
                        ),
                    )
                elif target["immune_until"] > time + EPSILON:
                    amount = 0
                damage[target["id"]] += amount
            trace.append(
                {
                    "event": packet["kind"] + "_impact",
                    "time_seconds": time,
                    "source": packet["source"],
                    "targets": [target["id"] for target in targets],
                }
            )
        return damage, healing

    def next_boundary(self, time):
        values = [clock for clock in self.heal_next.values() if clock is not None]
        values.extend(self.sample_next.values())
        if self.packets:
            values.append(self.packets[0][0])
        future = [value for value in values if value > time + EPSILON]
        return min(future) if future else None

    def frame(self, actor_id, actor):
        if actor_id not in self.models:
            return {}
        return {
            "duke_isolated": actor.get("_duke_isolated"),
            "duke_counter_ready_seconds": self.counter_ready[actor_id],
            "duke_heart_next_heal_seconds": self.heal_next[actor_id],
        }

    def result(self):
        result = {
            "isolation_changes": deepcopy(self.log),
            "death_effects_released_for": sorted(self.heart_released),
            "pending_packets": len(self.packets),
            "game_calibrated": False,
        }
        sampled = {
            key: {
                **deepcopy(model["parameters"]["isolation_update"]),
                "sample_count": self.sample_counts[key],
            }
            for key, model in self.models.items()
            if "isolation_update" in model["parameters"]
        }
        if sampled:
            result["experimental_isolation_updates"] = sampled
        return result
