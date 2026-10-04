"""One-use traps with exact entry boundaries along declared unit paths.

Trigger exclusions, delays and projectile policies are explicit hypotheses.
Traps occupy layout tiles but are neither targets nor destruction-count actors.
"""

from collections import defaultdict
from copy import deepcopy
from heapq import heappop, heappush
from math import hypot, sqrt

from .artillery import RULES as ARTILLERY_RULES
from .common import InputError, identifier, integer, number, require
from .geometry import footprint
from .rates import movement_speed, pause_attack_work
from .spatial import EPSILON, _active, center, target_distance


RULESET = "spatial-triggered-traps-kernel-v11"
SCOPE = "damage_traps_artillery_heroes_sector_without_pets_or_defending_troops"
RULES = {
    **ARTILLERY_RULES,
    "trap_trigger": "first_eligible_center_entry_in_explicit_radius_once",
    "trap_path_entry": "split_time_at_first_circle_entry_along_declared_polyline",
    "trap_trigger_tie": "distance_then_instance_id",
    "trap_phase": "commands_then_trap_damage_then_weapon_launches",
    "trap_projectile": "explicit_delay_plus_launch_distance_travel_time",
    "trap_protection": "invulnerability_blocks_damage_but_not_trigger",
    "trap_membership": "eligible_live_units_at_impact",
    "trap_geometry": "nonblocking_untargetable_excluded_from_destruction",
}
IMPACT_KINDS = {
    "bomb": "fixed_trap_center_splash",
    "giant-bomb": "fixed_trap_center_splash",
    "air-bomb": "locked_target_splash",
    "seeking-air-mine": "locked_target_single",
}
SUPPORTED_TRAP_IDS = frozenset(
    {*IMPACT_KINDS, "spring-trap", "skeleton-trap", "tornado-trap", "giga-bomb"}
)
SPRING_IMPACT = "fixed_trap_center_spring"
SPRING_CLASSES = {"troop", "hero", "siege", "pet", "other"}
SPRING_PARAMETERS = {
    "source",
    "arming_seconds",
    "delay_seconds",
    "trigger_radius_multiplier",
    "effect_radius_tiles",
    "allocation_policy",
    "protection_policy",
    "oversized_policy",
    "damage_multiplier",
    "non_troop_policies",
    "push",
    "damage_lockout_seconds",
    "lethal_damage_policy",
    "excluded_trigger_entities",
    "excluded_effect_entities",
}
PARAMETERS = {
    "source",
    "arming_seconds",
    "delay_seconds",
    "projectile_speed_tiles_per_second",
    "damage_multiplier",
    "trigger_radius_multiplier",
    "damage_radius_multiplier",
    "excluded_trigger_entities",
    "excluded_damage_entities",
    "dead_trigger_policy",
}


def _validate_spring_parameters(parameters):
    if not isinstance(parameters, dict) or set(parameters) != SPRING_PARAMETERS:
        raise InputError("Spring Trap needs its complete explicit behavior parameters")
    identifier(parameters["source"], "Spring Trap behavior evidence")
    for field in (
        "arming_seconds",
        "delay_seconds",
        "trigger_radius_multiplier",
        "effect_radius_tiles",
        "damage_multiplier",
        "damage_lockout_seconds",
    ):
        number(parameters[field], field, 0)
    if parameters["allocation_policy"] not in {
        "highest_housing_single",
        "largest_housing_then_distance_then_id_skip_unfit",
    }:
        raise InputError("Unsupported Spring Trap allocation policy")
    if parameters["protection_policy"] not in {
        "damage_immunity_blocks_removal",
        "damage_immunity_does_not_block_removal",
    }:
        raise InputError("Spring Trap removal protection policy must be explicit")
    if parameters["oversized_policy"] not in {
        "ignore_without_trigger_or_damage",
        "damage_and_push",
    }:
        raise InputError("Unsupported Spring Trap oversized policy")
    if (
        parameters["allocation_policy"] != "highest_housing_single"
        and parameters["oversized_policy"] != "ignore_without_trigger_or_damage"
    ):
        raise InputError("Group-capacity Spring probes only support capacity removal")
    if parameters["lethal_damage_policy"] not in {
        "eject_without_death_effects",
        "actual_hp_death",
    }:
        raise InputError("Spring Trap lethal-damage policy must be explicit")
    policies = parameters["non_troop_policies"]
    if not isinstance(policies, dict) or set(policies) != SPRING_CLASSES - {"troop"}:
        raise InputError(
            "Spring Trap needs explicit hero, siege, pet and other policies"
        )
    for policy in policies.values():
        if policy is None:
            continue
        if not isinstance(policy, dict) or set(policy) != {
            "target_weight",
            "damage_multiplier",
            "push",
        }:
            raise InputError("Spring class policy needs target weight, damage and push")
        integer(policy["target_weight"], "Spring class target weight", 1)
        number(policy["damage_multiplier"], "Spring class damage multiplier", 0)
        if not isinstance(policy["push"], bool):
            raise InputError("Spring class push eligibility must be boolean")
    push = parameters["push"]
    if not isinstance(push, dict) or set(push) != {
        "distance_tiles",
        "pause_seconds",
        "direction",
        "coincident_direction",
        "collision_policy",
        "protection_policy",
    }:
        raise InputError("Spring push needs complete explicit displacement parameters")
    number(push["distance_tiles"], "Spring push distance", 0)
    number(push["pause_seconds"], "Spring push pause", 0)
    if push["direction"] != "away_from_trap":
        raise InputError("Unsupported Spring push direction")
    direction = push["coincident_direction"]
    if not isinstance(direction, list) or len(direction) != 2:
        raise InputError("Coincident Spring push direction needs two coordinates")
    for coordinate in direction:
        number(coordinate, "Spring push direction coordinate")
    if hypot(*direction) <= EPSILON:
        raise InputError("Coincident Spring push direction cannot be zero")
    if push["collision_policy"] != "cancel_if_segment_blocked_or_outside":
        raise InputError("Unsupported Spring push collision policy")
    if push["protection_policy"] not in {
        "damage_immunity_blocks_push",
        "damage_immunity_does_not_block_push",
    }:
        raise InputError("Spring push protection policy must be explicit")
    for field in ("excluded_trigger_entities", "excluded_effect_entities"):
        _entity_list(parameters[field], field)


def compile_spring_trap(instance, catalog):
    """Compile current single-target or explicitly selected legacy group probes.

    The 2025 publisher rework establishes the single-target/damage branches.
    Push geometry, protection, lockout and lethal effects remain declared inputs.
    """
    entity_id = require(instance, "entity")
    if entity_id != "spring-trap":
        raise InputError("Spring Trap compiler requires spring-trap")
    entity = catalog.entity(entity_id)
    level = integer(require(instance, "level"), "trap level", 1)
    town_hall = integer(require(instance, "town_hall"), "trap Town Hall", 1)
    if not catalog.available(entity_id, level, town_hall):
        raise InputError("Trap level is unavailable at the selected Town Hall")
    if require(instance, "team") != "defense":
        raise InputError("Spring Traps belong to the defending team")
    parameters = require(instance, "parameters")
    _validate_spring_parameters(parameters)
    for field in ("excluded_trigger_entities", "excluded_effect_entities"):
        for entity_name in parameters[field]:
            catalog.entity(entity_name)
    row = catalog.level(entity_id, level)
    width, height = footprint({"id": entity_id}, catalog)
    return {
        "id": identifier(require(instance, "id"), "trap instance"),
        "entity": entity_id,
        "level": level,
        "team": "defense",
        "statistics_source": catalog.records[entity_id]["source"],
        "x": integer(require(instance, "x"), "trap x", 0),
        "y": integer(require(instance, "y"), "trap y", 0),
        "width": width,
        "height": height,
        "target_layer": "ground",
        "impact_kind": SPRING_IMPACT,
        "trigger_radius": number(
            require(entity, "triggerRadius"), "trap trigger radius", 0
        )
        * parameters["trigger_radius_multiplier"],
        "spring_capacity": integer(
            require(row, "springCapacity"), "spring capacity", 1
        ),
        "damage": number(require(row, "damage"), "Spring Trap damage", 0)
        * parameters["damage_multiplier"],
        "projectile_speed_tiles_per_second": None,
        **deepcopy(parameters),
    }


def compile_trap(instance, catalog, movement_units_per_tile=None):
    entity_id = require(instance, "entity")
    if entity_id == "giga-bomb":
        from .giga_bombs import compile_giga_bomb

        return compile_giga_bomb(instance, catalog)
    if entity_id == "skeleton-trap":
        from .skeleton_traps import compile_skeleton_trap

        return compile_skeleton_trap(instance, catalog, movement_units_per_tile)
    if entity_id == "tornado-trap":
        from .tornado_traps import compile_tornado_trap

        return compile_tornado_trap(instance, catalog)
    if entity_id == "spring-trap":
        return compile_spring_trap(instance, catalog)
    return compile_damage_trap(instance, catalog)


def _entity_list(value, label):
    if not isinstance(value, list) or len(value) != len(set(value)):
        raise InputError(f"{label} must be an explicit unique list")
    for item in value:
        identifier(item, label)
    return value


def compile_damage_trap(instance, catalog):
    entity_id = require(instance, "entity")
    if entity_id not in IMPACT_KINDS:
        raise InputError(
            "This adapter supports Bomb, Giant Bomb, Air Bomb and Seeking Air Mine"
        )
    entity = catalog.entity(entity_id)
    level = integer(require(instance, "level"), "trap level", 1)
    town_hall = integer(require(instance, "town_hall"), "trap Town Hall", 1)
    if not catalog.available(entity_id, level, town_hall):
        raise InputError("Trap level is unavailable at the selected Town Hall")
    parameters = require(instance, "parameters")
    if not isinstance(parameters, dict) or set(parameters) != PARAMETERS:
        raise InputError(
            "Trap timing, exclusions, scaling and dead-target policy must be explicit"
        )
    source = identifier(parameters["source"], "trap behavior evidence")
    for field in (
        "arming_seconds",
        "delay_seconds",
        "damage_multiplier",
        "trigger_radius_multiplier",
        "damage_radius_multiplier",
    ):
        number(parameters[field], field, 0)
    speed = parameters["projectile_speed_tiles_per_second"]
    if speed is not None:
        number(speed, "trap projectile speed", EPSILON)
    if entity_id in {"bomb", "giant-bomb"} and speed is not None:
        raise InputError("Ground bombs use a fixed delay, not projectile travel")
    for field in ("excluded_trigger_entities", "excluded_damage_entities"):
        for excluded in _entity_list(parameters[field], field):
            catalog.entity(excluded)
    if parameters["dead_trigger_policy"] not in {"fizzle", "fixed_trigger_position"}:
        raise InputError("Unsupported trap dead-trigger policy")
    row = catalog.level(entity_id, level)
    width, height = footprint({"id": entity_id}, catalog)
    radius = 0
    if entity_id != "seeking-air-mine":
        radius = number(
            row.get("damageRadius", entity.get("damageRadius")), "trap damage radius", 0
        )
    if require(instance, "team") != "defense":
        raise InputError("Damage traps belong to the defending team")
    return {
        "id": identifier(require(instance, "id"), "trap instance"),
        "entity": entity_id,
        "level": level,
        "team": "defense",
        "source": source,
        "statistics_source": catalog.records[entity_id]["source"],
        "x": integer(require(instance, "x"), "trap x", 0),
        "y": integer(require(instance, "y"), "trap y", 0),
        "width": width,
        "height": height,
        "target_layer": require(entity, "targetType"),
        "trigger_radius": number(
            require(entity, "triggerRadius"), "trap trigger radius", 0
        )
        * parameters["trigger_radius_multiplier"],
        "damage_radius": radius * parameters["damage_radius_multiplier"],
        "damage": number(require(row, "damage"), "trap damage", 0)
        * parameters["damage_multiplier"],
        "impact_kind": IMPACT_KINDS[entity_id],
        **{
            key: deepcopy(parameters[key])
            for key in PARAMETERS
            - {
                "source",
                "damage_multiplier",
                "trigger_radius_multiplier",
                "damage_radius_multiplier",
            }
        },
    }


def segment_circle_entry(start, end, circle, radius):
    """Distance to first circle contact on a segment, or None for a miss."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = hypot(dx, dy)
    offset_x, offset_y = start[0] - circle[0], start[1] - circle[1]
    if hypot(offset_x, offset_y) <= radius + EPSILON:
        return 0.0
    if length <= EPSILON:
        return None
    projection = (offset_x * dx + offset_y * dy) / length
    discriminant = projection * projection - (
        offset_x * offset_x + offset_y * offset_y - radius * radius
    )
    if discriminant < -EPSILON:
        return None
    entry = -projection - sqrt(max(discriminant, 0))
    if -EPSILON <= entry <= length + EPSILON:
        return max(entry, 0)
    return None


def _segment_meets_rectangle(start, end, rectangle):
    """Inclusive slab intersection for the conservative push-collision policy."""
    entry, exit_time = 0.0, 1.0
    for coordinate, destination, low, high in zip(
        start, end, rectangle[:2], rectangle[2:]
    ):
        delta = destination - coordinate
        if abs(delta) <= EPSILON:
            if coordinate < low or coordinate > high:
                return False
            continue
        first = (low - coordinate) / delta
        second = (high - coordinate) / delta
        entry = max(entry, min(first, second))
        exit_time = min(exit_time, max(first, second))
        if entry > exit_time + EPSILON:
            return False
    return True


class TrapCombat:
    def __init__(self, models, actors, width, height, lethal_interceptor=None):
        if not isinstance(models, list):
            raise InputError("Traps must be an explicit list")
        self.models = {}
        self.lethal_interceptor = lethal_interceptor
        self.width = width
        self.height = height
        occupied = {
            (x, y)
            for actor in actors.values()
            if actor["blocking"]
            for x in range(actor["x"], actor["x"] + actor["width"])
            for y in range(actor["y"], actor["y"] + actor["height"])
        }
        for original in models:
            trap = deepcopy(original)
            trap_id = identifier(require(trap, "id"), "trap instance")
            if trap_id in self.models or trap_id in actors:
                raise InputError("Trap and actor instance IDs must be unique")
            identifier(require(trap, "source"), "trap behavior source")
            identifier(require(trap, "team"), "trap team")
            entity_id = require(trap, "entity")
            expected_impact = (
                SPRING_IMPACT
                if entity_id == "spring-trap"
                else IMPACT_KINDS.get(entity_id)
            )
            if expected_impact is None or trap["impact_kind"] != expected_impact:
                raise InputError("Trap entity must use its supported impact pattern")
            if require(trap, "target_layer") not in {"ground", "air"}:
                raise InputError("Trap targeting needs one supported layer")
            for field in (
                "damage",
                "trigger_radius",
                "arming_seconds",
                "delay_seconds",
            ):
                number(require(trap, field), field, 0)
            if "projectile_speed_tiles_per_second" not in trap:
                raise InputError(
                    "Trap projectile speed must be explicit, including null"
                )
            speed = trap["projectile_speed_tiles_per_second"]
            if speed is not None:
                number(speed, "trap projectile speed", EPSILON)
            if entity_id == "spring-trap":
                _validate_spring_parameters(
                    {field: require(trap, field) for field in SPRING_PARAMETERS}
                )
                integer(require(trap, "spring_capacity"), "spring capacity", 1)
                if trap["target_layer"] != "ground" or speed is not None:
                    raise InputError(
                        "Spring Traps require ground targets and fixed delay"
                    )
                self._validate_spring_actors(trap, actors)
            else:
                number(require(trap, "damage_radius"), "damage_radius", 0)
                if require(trap, "dead_trigger_policy") not in {
                    "fizzle",
                    "fixed_trigger_position",
                }:
                    raise InputError("Unsupported trap dead-trigger policy")
                for field in ("excluded_trigger_entities", "excluded_damage_entities"):
                    _entity_list(require(trap, field), field)
            x = integer(require(trap, "x"), "trap x", 0)
            y = integer(require(trap, "y"), "trap y", 0)
            trap_width = integer(require(trap, "width"), "trap width", 1)
            trap_height = integer(require(trap, "height"), "trap height", 1)
            if x + trap_width > width or y + trap_height > height:
                raise InputError("Trap footprint is outside the board")
            cells = {
                (tx, ty)
                for tx in range(x, x + trap_width)
                for ty in range(y, y + trap_height)
            }
            if cells & occupied:
                raise InputError(
                    "Trap footprints cannot overlap structures or other traps"
                )
            occupied |= cells
            self.models[trap_id] = trap
        self.triggered = {}
        self.resolved = set()
        self.pending = []
        self.serial = 0
        self.removals = []
        self.last_spring_damage = {}

    @staticmethod
    def _validate_spring_actors(trap, actors):
        for actor in actors.values():
            if (
                actor["kind"] != "unit"
                or actor["layer"] != "ground"
                or actor["team"] == trap["team"]
            ):
                continue
            spring_class = require(actor, "spring_class")
            if spring_class not in SPRING_CLASSES:
                raise InputError("Unsupported unit Spring Trap classification")
            if spring_class == "troop":
                integer(
                    require(actor, "housing_space"), "Spring troop housing space", 1
                )

    @staticmethod
    def _spring_weight(trap, actor):
        if actor["spring_class"] == "troop":
            return actor["housing_space"]
        policy = trap["non_troop_policies"][actor["spring_class"]]
        return policy["target_weight"] if policy is not None else None

    @staticmethod
    def eligible(trap, actor, time, phase):
        entity_id = actor.get("entity_adapter", {}).get("entity")
        if trap["entity"] == "spring-trap" and phase != "trigger":
            phase = "effect"
        eligible = (
            _active(actor, time)
            and actor["kind"] == "unit"
            and actor["team"] != trap["team"]
            and actor["layer"] == trap["target_layer"]
            and entity_id not in trap[f"excluded_{phase}_entities"]
        )
        if not eligible or trap["entity"] != "spring-trap":
            return eligible
        weight = TrapCombat._spring_weight(trap, actor)
        if weight is None:
            return False
        if trap["oversized_policy"] == "ignore_without_trigger_or_damage":
            return (
                actor["spring_class"] == "troop" and weight <= trap["spring_capacity"]
            )
        return True

    def update(self, actors, time, trace):
        for trap_id, trap in sorted(self.models.items()):
            if trap_id in self.triggered or time + EPSILON < trap["arming_seconds"]:
                continue
            origin = center(trap)
            candidates = [
                actor
                for actor in actors.values()
                if self.eligible(trap, actor, time, "trigger")
                and hypot(center(actor)[0] - origin[0], center(actor)[1] - origin[1])
                <= trap["trigger_radius"] + EPSILON
            ]
            if not candidates:
                continue
            target = min(
                candidates,
                key=lambda actor: (
                    hypot(center(actor)[0] - origin[0], center(actor)[1] - origin[1]),
                    actor["id"],
                ),
            )
            arrival = time + trap["delay_seconds"]
            speed = trap["projectile_speed_tiles_per_second"]
            if speed is not None:
                arrival += (
                    hypot(center(target)[0] - origin[0], center(target)[1] - origin[1])
                    / speed
                )
            event = {
                "trap_id": trap_id,
                "trigger_id": target["id"],
                "trigger_position": center(target),
                "trigger_seconds": time,
                "arrival_seconds": arrival,
            }
            self.triggered[trap_id] = deepcopy(event)
            self.serial += 1
            heappush(self.pending, (arrival, self.serial, event))
            trace.append(
                {"event": "trap_trigger", "time_seconds": time, **deepcopy(event)}
            )
        damage = defaultdict(float)
        while self.pending and self.pending[0][0] <= time + EPSILON:
            _, _, event = heappop(self.pending)
            trap = self.models[event["trap_id"]]
            if trap["entity"] == "spring-trap":
                self._resolve_spring(trap, actors, time, trace)
                self.resolved.add(trap["id"])
                continue
            target = actors[event["trigger_id"]]
            target_alive = _active(target, time)
            if trap["impact_kind"] == "fixed_trap_center_splash":
                impact = center(trap)
            elif target_alive:
                impact = center(target)
            elif (
                trap["dead_trigger_policy"] == "fixed_trigger_position"
                and trap["impact_kind"] == "locked_target_splash"
            ):
                impact = event["trigger_position"]
            else:
                self.resolved.add(trap["id"])
                trace.append(
                    {
                        "event": "trap_fizzle",
                        "time_seconds": time,
                        "trap_id": trap["id"],
                        "trigger_id": target["id"],
                    }
                )
                continue
            if trap["impact_kind"] == "locked_target_single":
                recipients = (
                    [target] if self.eligible(trap, target, time, "damage") else []
                )
            else:
                recipients = [
                    actor
                    for actor in actors.values()
                    if self.eligible(trap, actor, time, "damage")
                    and target_distance(impact, actor)
                    <= trap["damage_radius"] + EPSILON
                ]
            for actor in recipients:
                from .damage_receipts import record_damage

                resolved = record_damage(
                    self,
                    actor,
                    trap["damage"],
                    time,
                    source_id=trap["id"],
                    source_team="defense",
                    origin="trap",
                )
                if resolved > 0:
                    damage[actor["id"]] += resolved
            self.resolved.add(trap["id"])
            trace.append(
                {
                    "event": "trap_impact",
                    "time_seconds": time,
                    "trap_id": trap["id"],
                    "impact_position": impact,
                    "targets": sorted(actor["id"] for actor in recipients),
                    "protected_targets": sorted(
                        actor["id"]
                        for actor in recipients
                        if actor["immune_until"] > time + EPSILON
                    ),
                    "requested_damage_per_target": trap["damage"],
                }
            )
        return damage

    def _remove(self, trap, actor, time, reason, trace, previous_hp=None):
        removal = {
            "actor_id": actor["id"],
            "trap_id": trap["id"],
            "time_seconds": time,
            "reason": reason,
            "hitpoints_before_removal": (
                actor["hp"] if previous_hp is None else previous_hp
            ),
        }
        # HP zero makes all existing activity/healing checks reject this actor.
        # Leaving death_time unset distinguishes ejection from an HP death.
        actor["hp"] = 0
        actor["target"] = None
        actor["removal"] = deepcopy(removal)
        actor.pop("_remaining_path", None)
        actor.pop("_path_signature", None)
        if "healing_target" in actor:
            actor["healing_target"] = None
        self.removals.append(removal)
        trace.append({"event": "spring_removal", **deepcopy(removal)})

    def _push(self, trap, actor, actors, time, trace):
        push = trap["push"]
        protected = actor["immune_until"] > time + EPSILON
        if protected and push["protection_policy"] == "damage_immunity_blocks_push":
            return
        origin = center(trap)
        start = center(actor)
        direction = (start[0] - origin[0], start[1] - origin[1])
        if hypot(*direction) <= EPSILON:
            direction = push["coincident_direction"]
        length = hypot(*direction)
        displacement = tuple(
            component / length * push["distance_tiles"] for component in direction
        )
        destination = tuple(start[index] + displacement[index] for index in (0, 1))
        new_x = actor["x"] + displacement[0]
        new_y = actor["y"] + displacement[1]
        blocked = not (
            0 <= new_x < self.width
            and 0 <= new_y < self.height
            and new_x + actor["width"] <= self.width
            and new_y + actor["height"] <= self.height
        )
        if not blocked and push["distance_tiles"] > EPSILON:
            for obstacle in actors.values():
                if not obstacle["blocking"] or not _active(obstacle, time):
                    continue
                rectangle = (
                    obstacle["x"] - actor["width"] / 2,
                    obstacle["y"] - actor["height"] / 2,
                    obstacle["x"] + obstacle["width"] + actor["width"] / 2,
                    obstacle["y"] + obstacle["height"] + actor["height"] / 2,
                )
                if _segment_meets_rectangle(start, destination, rectangle):
                    blocked = True
                    break
        if not blocked:
            actor["x"] = new_x
            actor["y"] = new_y
            actor.pop("_remaining_path", None)
            actor.pop("_path_signature", None)
        # Reuse the kernel's pause clock; overlapping pauses extend, never add.
        pause_end = time + push["pause_seconds"]
        pause_attack_work(actor, time, pause_end)
        actor["frozen_until"] = max(actor["frozen_until"], pause_end)
        trace.append(
            {
                "event": "spring_push",
                "time_seconds": time,
                "trap_id": trap["id"],
                "actor_id": actor["id"],
                "from_position": start,
                "requested_position": destination,
                "to_position": center(actor),
                "displacement_blocked": blocked,
                "paused_until": actor["frozen_until"],
            }
        )

    def _damage_and_push(self, trap, actor, actors, time, trace):
        previous_hit = self.last_spring_damage.get(actor["id"])
        if (
            previous_hit is not None
            and time <= previous_hit + trap["damage_lockout_seconds"] + EPSILON
        ):
            trace.append(
                {
                    "event": "spring_damage_suppressed",
                    "time_seconds": time,
                    "trap_id": trap["id"],
                    "actor_id": actor["id"],
                }
            )
            return
        self.last_spring_damage[actor["id"]] = time
        class_policy = trap["non_troop_policies"].get(actor["spring_class"])
        multiplier = class_policy["damage_multiplier"] if class_policy else 1
        amount = trap["damage"] * multiplier
        previous_hp = actor["hp"]
        from .damage_receipts import record_damage

        resolved = record_damage(
            self,
            actor,
            amount,
            time,
            source_id=trap["id"],
            source_team="defense",
            origin="trap",
            apply_immediately=True,
        )
        applied = min(previous_hp, resolved)
        actor["hp"] -= applied
        actor["_received_damage"] = actor.get("_received_damage", 0) + applied
        trace.append(
            {
                "event": "spring_damage",
                "time_seconds": time,
                "trap_id": trap["id"],
                "actor_id": actor["id"],
                "requested_damage": amount,
                "applied_damage": applied,
                "protected": actor["immune_until"] > time + EPSILON,
            }
        )
        if actor["hp"] == 0:
            if trap["lethal_damage_policy"] == "actual_hp_death":
                rescued = (
                    self.lethal_interceptor is not None
                    and self.lethal_interceptor(actor, time, trace)
                )
                if not rescued:
                    actor["death_time"] = time
            else:
                self._remove(
                    trap, actor, time, "lethal_spring_damage", trace, previous_hp
                )
        if actor["hp"] > 0 and (class_policy is None or class_policy["push"]):
            self._push(trap, actor, actors, time, trace)

    def _resolve_spring(self, trap, actors, time, trace):
        origin = center(trap)
        candidates = [
            actor
            for actor in actors.values()
            if self.eligible(trap, actor, time, "effect")
            and hypot(center(actor)[0] - origin[0], center(actor)[1] - origin[1])
            <= trap["effect_radius_tiles"] + EPSILON
        ]
        candidates.sort(
            key=lambda actor: (
                -self._spring_weight(trap, actor),
                hypot(center(actor)[0] - origin[0], center(actor)[1] - origin[1]),
                actor["id"],
            )
        )
        if trap["allocation_policy"] == "highest_housing_single":
            candidates = candidates[:1]
        remaining = trap["spring_capacity"]
        removed = []
        protected = []
        over_capacity = []
        damaged = []
        for actor in candidates:
            weight = self._spring_weight(trap, actor)
            if actor["spring_class"] == "troop" and weight <= remaining:
                if (
                    actor["immune_until"] > time + EPSILON
                    and trap["protection_policy"] == "damage_immunity_blocks_removal"
                ):
                    protected.append(actor["id"])
                    continue
                remaining -= weight
                removed.append(actor["id"])
                self._remove(trap, actor, time, "spring_capacity", trace)
            elif trap["oversized_policy"] == "damage_and_push":
                damaged.append(actor["id"])
                self._damage_and_push(trap, actor, actors, time, trace)
            else:
                over_capacity.append(actor["id"])
        trace.append(
            {
                "event": "spring_resolution",
                "time_seconds": time,
                "trap_id": trap["id"],
                "impact_position": origin,
                "allocation_policy": trap["allocation_policy"],
                "candidate_order": [actor["id"] for actor in candidates],
                "removed_targets": removed,
                "damage_branch_targets": damaged,
                "protected_targets": protected,
                "skipped_capacity_targets": over_capacity,
                "capacity_used": trap["spring_capacity"] - remaining,
                "capacity_remaining": remaining,
            }
        )

    def next_boundary(self, time):
        boundaries = [self.pending[0][0]] if self.pending else []
        boundaries.extend(
            trap["arming_seconds"]
            for trap_id, trap in self.models.items()
            if trap_id not in self.triggered and trap["arming_seconds"] > time + EPSILON
        )
        return min(boundaries) if boundaries else None

    def first_crossing_delay(self, actor, route, time, horizon, effective_speed=None):
        speed = movement_speed(actor) if effective_speed is None else effective_speed
        if speed <= EPSILON:
            return None
        earliest = None
        for trap_id, trap in self.models.items():
            if (
                trap_id in self.triggered
                or trap["arming_seconds"] > time + EPSILON
                or not self.eligible(trap, actor, time, "trigger")
            ):
                continue
            previous = center(actor)
            distance = 0.0
            for point in route:
                entry = segment_circle_entry(
                    previous, point, center(trap), trap["trigger_radius"]
                )
                if entry is not None:
                    delay = (distance + entry) / speed
                    if EPSILON < delay <= horizon + EPSILON:
                        earliest = (
                            min(delay, earliest) if earliest is not None else delay
                        )
                    break
                distance += hypot(point[0] - previous[0], point[1] - previous[1])
                if distance > speed * horizon:
                    break
                previous = point
        return earliest

    def result(self):
        return {
            "triggered": deepcopy(self.triggered),
            "resolved": sorted(self.resolved),
            "untriggered": sorted(set(self.models) - set(self.triggered)),
            "pending_at_horizon": [deepcopy(event) for _, _, event in self.pending],
            **(
                {
                    "spring_removals": deepcopy(self.removals),
                    "spring_resolution_order": (
                        "arrival_then_trigger_serial_before_accumulated_damage_traps"
                    ),
                }
                if any(trap["entity"] == "spring-trap" for trap in self.models.values())
                else {}
            ),
        }
