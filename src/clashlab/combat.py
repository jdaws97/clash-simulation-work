"""Declared projectile, radial, chain, and multi-target combat patterns.

The generic patterns are building blocks for entity adapters. Selecting a pattern
does not prove the corresponding Clash entity uses these geometry/timing rules.
"""

from collections import defaultdict
from copy import deepcopy
from heapq import heappop, heappush
from math import hypot

from .spell_visibility import untargetable_until
from .common import InputError, identifier, integer, number, require
from .buffs import damage_multiplier
from .raven_lifecycle import launch_multiplier as raven_launch_multiplier
from .defense_upgrades import InfernoAmmunitionCombat
from .spatial import (
    EPSILON,
    MODEL_RULES,
    _active,
    _eligible,
    center,
    target_distance,
    target_priority,
)


RULESET = "spatial-projectile-pattern-kernel-v2"
COMBAT_RULES = {
    **MODEL_RULES,
    "hit_model": "explicit_actor_patterns_and_projectiles",
    "phase_order": "commands_then_launches_and_simultaneous_impacts_then_movement",
    "projectile_travel": "arrival_delay_computed_from_launch_distance",
    "projectile_freeze": "already_launched_projectiles_continue",
    "inactive_primary_at_impact": "fizzle",
    "area_range_metric": "point_to_target_footprint",
    "chain_health_state": "all_same_time_impacts_use_pre_damage_state",
    "command_resolution": "deploy_then_areas_then_status_then_damage_and_heal",
}
KINDS = {"unit", "defense", "building", "wall"}
LAYERS = {"ground", "air"}
PATTERNS = {
    "crafted_phase4_weapon",
    "none",
    "single",
    "radial",
    "source_radial",
    "directional_splash",
    "eagle_shell",
    "chain",
    "multi_target",
    "firespitter_ballistic_bullet",
    "siege_area",
    "siege_extended",
    "siege_barrel",
    "primary_centered_fanout",
}
AREA_EFFECTS = {
    "area_damage": "damage",
    "area_heal": "heal",
    "area_freeze": "freeze",
    "area_invulnerability": "invulnerability",
}


def footprint_distance(first, second):
    dx = max(
        first["x"] - second["x"] - second["width"],
        second["x"] - first["x"] - first["width"],
        0,
    )
    dy = max(
        first["y"] - second["y"] - second["height"],
        second["y"] - first["y"] - first["height"],
        0,
    )
    return hypot(dx, dy)


def _validate_values(values, allowed, label):
    if (
        not isinstance(values, list)
        or not values
        or len(values) != len(set(values))
        or not set(values) <= allowed
    ):
        raise InputError(f"{label} must contain unique supported values")


def validate_pattern(pattern):
    from .advanced_defenses import FANOUT_PATTERN, validate_fanout_pattern
    from .indirect_defenses import validate_eagle_shell
    from .splash import LAYER_POLICIES, validate_directional_splash
    from .valkyries import validate_source_radial
    from .siege_machines import validate_siege_pattern
    from .siege_extensions import validate_extended_siege_pattern
    from .siege_barrels import validate_barrel_pattern
    from .firespitters import (
        PATTERN as FIRESPITTER_PATTERN,
        validate_firespitter_pattern,
    )

    kind = require(pattern, "kind")
    if kind not in PATTERNS:
        raise InputError("Unsupported attack pattern")
    identifier(require(pattern, "source"), "attack-pattern evidence")
    if kind == "crafted_phase4_weapon":
        if set(pattern) != {"kind", "source"}:
            raise InputError(
                "Crafted weapon tag requires exact dedicated dispatch contract"
            )
        return
    if kind == "siege_extended":
        validate_extended_siege_pattern(pattern)
        return
    if kind == "siege_barrel":
        validate_barrel_pattern(pattern)
        return
    if kind == FANOUT_PATTERN:
        validate_fanout_pattern(pattern)
        return
    if kind == "siege_area":
        validate_siege_pattern(pattern)
        return
    if kind == FIRESPITTER_PATTERN:
        validate_firespitter_pattern(pattern)
        return
    if kind == "none":
        return
    _validate_values(require(pattern, "target_kinds"), KINDS, "pattern target kinds")
    _validate_values(require(pattern, "target_layers"), LAYERS, "pattern target layers")
    number(require(pattern, "maximum_hp_fraction"), "maximum-HP damage fraction", 0)
    projectile = require(pattern, "projectile")
    if require(projectile, "timing") == "instant":
        number(require(projectile, "delay_seconds"), "instant projectile delay", 0, 0)
    elif projectile["timing"] == "launch_distance_delay":
        number(
            require(projectile, "speed_tiles_per_second"), "projectile speed", EPSILON
        )
        number(projectile.get("delay_seconds", 0), "projectile release delay", 0)
    else:
        raise InputError("Unsupported projectile timing")
    if require(projectile, "destination") not in {
        "locked_actor_center_at_impact",
        "fixed_target_center_at_launch",
        "fixed_source_center_at_launch",
    }:
        raise InputError("Projectile destination rule must be explicit")
    number(require(projectile, "hit_radius"), "projectile hit radius", 0)
    if "inactive_primary_policy" in projectile:
        policy = projectile["inactive_primary_policy"]
        if policy not in {"fizzle", "resolve_at_fixed_launch_position"}:
            raise InputError("Unsupported inactive-primary projectile policy")
        if policy == "resolve_at_fixed_launch_position" and (
            kind not in {"radial", "source_radial", "directional_splash", "eagle_shell"}
            or projectile["destination"]
            not in {"fixed_target_center_at_launch", "fixed_source_center_at_launch"}
        ):
            raise InputError("Independent area impacts require a fixed destination")
    if "splash_layer_policy" in pattern:
        if (
            kind not in {"radial", "source_radial", "directional_splash", "eagle_shell"}
            or pattern["splash_layer_policy"] not in LAYER_POLICIES
        ):
            raise InputError(
                "Splash layer filtering needs an explicit supported policy"
            )
    if (
        projectile["destination"] == "fixed_source_center_at_launch"
        and kind != "source_radial"
    ):
        raise InputError("Only source-centered swings may select a source destination")
    if kind == "source_radial":
        validate_source_radial(pattern)
    elif kind == "eagle_shell":
        validate_eagle_shell(pattern)
    elif kind == "radial":
        number(require(pattern, "radius"), "radial attack radius", 0)
    elif kind == "directional_splash":
        if require(pattern, "splash_layer_policy") not in LAYER_POLICIES:
            raise InputError("Directional splash requires explicit layer filtering")
        validate_directional_splash(require(pattern, "directional_splash"))
    elif kind == "chain":
        multipliers = require(pattern, "damage_multipliers")
        if not isinstance(multipliers, list) or not multipliers:
            raise InputError("Chain needs explicit per-link damage multipliers")
        for value in multipliers:
            number(value, "chain damage multiplier", 0)
        number(require(pattern, "jump_range"), "chain jump range", 0)
        number(require(pattern, "jump_delay_seconds"), "chain jump delay", 0)
        if require(pattern, "jump_metric") not in {
            "center_distance",
            "footprint_distance",
        }:
            raise InputError("Chain distance convention must be explicit")
        if require(pattern, "tie_break") not in {
            "distance_then_instance_id",
            "distance_then_highest_current_hp_then_instance_id",
        }:
            raise InputError("Unsupported chain tie rule")
        if not isinstance(require(pattern, "allow_protected_links"), bool):
            raise InputError("Chain traversal through protection must be explicit")
    elif kind == "multi_target":
        integer(
            require(pattern, "projectiles_per_volley"), "volley projectile count", 1
        )
        if require(pattern, "allocation") not in {
            "distinct_targets_only",
            "cycle_distinct_targets_to_fill_volley",
        }:
            raise InputError("Multi-target allocation must be explicit")


def validate_area_effect(effect, actors):
    identifier(require(effect, "id"), "area-effect id")
    number(require(effect, "time_seconds"), "area-effect time", 0)
    if require(effect, "kind") not in AREA_EFFECTS:
        raise InputError("Unsupported area effect")
    area = require(effect, "area")
    number(require(area, "x"), "area x")
    number(require(area, "y"), "area y")
    number(require(area, "radius"), "area radius", 0)
    teams = {actor["team"] for actor in actors.values()}
    if require(area, "target_team") not in teams:
        raise InputError("Area effect needs an explicit known target team")
    _validate_values(require(area, "target_kinds"), KINDS, "area target kinds")
    _validate_values(require(area, "target_layers"), LAYERS, "area target layers")
    if effect["kind"] in {"area_damage", "area_heal"}:
        number(require(effect, "amount"), "area amount", 0)
    else:
        number(require(effect, "duration_seconds"), "area duration", EPSILON)


def expand_area_effects(effects, actors, time):
    expanded = []
    for effect in effects:
        if effect["kind"] not in AREA_EFFECTS:
            expanded.append(effect)
            continue
        validate_area_effect(effect, actors)
        area = effect["area"]
        point = area["x"], area["y"]
        translated = deepcopy(effect)
        translated["kind"] = AREA_EFFECTS[effect["kind"]]
        translated["targets"] = [
            actor["id"]
            for actor in actors.values()
            if _active(actor, time)
            and actor["team"] == area["target_team"]
            and actor["kind"] in area["target_kinds"]
            and actor["layer"] in area["target_layers"]
            and target_distance(point, actor) <= area["radius"] + EPSILON
        ]
        expanded.append(translated)
    return expanded


class PatternCombat:
    """Event queue whose impacts remain live after the firing actor dies."""

    def __init__(self, actors):
        self.patterns = {}
        self.ammunition = {}
        self.depletion_reported = set()
        self.inferno_ammunition = InfernoAmmunitionCombat(actors)
        self.pending = []
        self.serial = 0
        for actor in actors.values():
            minimum = number(
                require(actor, "minimum_range"),
                "minimum attack range",
                0,
                actor["range"],
            )
            if actor["movement"] != "stationary" and minimum != 0:
                raise InputError("Moving minimum-range weapons need a kiting adapter")
            actor["_minimum_range"] = minimum
            pattern = deepcopy(require(actor, "attack_model"))
            validate_pattern(pattern)
            if (pattern["kind"] in {"none", "crafted_phase4_weapon"}) != (
                actor["damage"] == 0
            ):
                raise InputError("Non-attacking actors need the explicit none pattern")
            if pattern["kind"] not in {"none", "crafted_phase4_weapon"}:
                if not set(actor["target_priorities"]) <= set(pattern["target_kinds"]):
                    raise InputError("Attack pattern omits a primary target kind")
                if not set(actor["target_layers"]) <= set(pattern["target_layers"]):
                    raise InputError("Attack pattern omits a primary target layer")
            self.patterns[actor["id"]] = pattern
            if "weapon_ammunition" in actor:
                ammunition = actor["weapon_ammunition"]
                if (
                    set(ammunition) != {"initial_rounds", "source"}
                    or pattern["kind"] == "none"
                ):
                    raise InputError(
                        "Finite ammunition requires an explicit attacking weapon"
                    )
                identifier(ammunition["source"], "ammunition evidence")
                self.ammunition[actor["id"]] = integer(
                    ammunition["initial_rounds"], "initial ammunition", 0
                )

    def _queue(self, packet, time):
        self.serial += 1
        heappush(self.pending, (time, self.serial, packet))

    def _targets_for_volley(self, actor, primary, actors, time):
        pattern = self.patterns[actor["id"]]
        if pattern["kind"] != "multi_target":
            return [primary]
        alternatives = [
            target
            for target in actors.values()
            if target["id"] != primary["id"]
            and _eligible(actor, target, time)
            and actor["_minimum_range"] - EPSILON
            <= target_distance(center(actor), target)
            <= actor["range"] + EPSILON
        ]
        alternatives.sort(
            key=lambda target: (
                target_priority(actor, target["kind"]),
                target_distance(center(actor), target),
                target["id"],
            )
        )
        maximum = pattern["projectiles_per_volley"]
        distinct = [primary, *alternatives][:maximum]
        if pattern["allocation"] == "distinct_targets_only":
            return distinct
        return [distinct[index % len(distinct)] for index in range(maximum)]

    def launch(
        self, actor, primary, actors, time, trace, flat_damage=None, weapon_state=None
    ):
        pattern = self.patterns[actor["id"]]
        if pattern["kind"] == "crafted_phase4_weapon":
            raise InputError("Crafted weapons require their dedicated Station runtime")
        if pattern["kind"] in {"siege_area", "siege_extended", "siege_barrel"}:
            raise InputError("Siege weapons require their dedicated carrier runtime")
        if pattern["kind"] == "firespitter_ballistic_bullet":
            raise InputError(
                "Firespitter bullets require their dedicated shot-stream runtime"
            )
        if actor["id"] in self.ammunition:
            if self.ammunition[actor["id"]] == 0:
                if actor["id"] not in self.depletion_reported:
                    trace.append(
                        {
                            "time_seconds": time,
                            "event": "weapon_depleted",
                            "source": actor["id"],
                        }
                    )
                    self.depletion_reported.add(actor["id"])
                return
            self.ammunition[actor["id"]] -= 1
        targets = self._targets_for_volley(actor, primary, actors, time)
        targets = self.inferno_ammunition.reserve_launch(actor, targets, time, trace)
        for target in targets:
            projectile = pattern["projectile"]
            destination = (
                center(actor) if pattern["kind"] == "source_radial" else center(target)
            )
            distance = hypot(
                destination[0] - center(actor)[0], destination[1] - center(actor)[1]
            )
            delay = (
                0
                if projectile["timing"] == "instant"
                else projectile.get("delay_seconds", 0)
                + distance / projectile["speed_tiles_per_second"]
            )
            packet = {
                "source": actor["id"],
                "source_team": actor["team"],
                "target": target["id"],
                "position": destination,
                "launch_position": center(actor),
                "primary_layer": target["layer"],
                "flat_damage": (actor["damage"] if flat_damage is None else flat_damage)
                * damage_multiplier(actor)
                * (
                    actor.get("_spell_town_hall_damage_multiplier", 1)
                    if target.get("entity_adapter", {}).get("entity") == "town-hall"
                    else (
                        actor.get("_spell_resource_damage_multiplier", 1)
                        if target.get("entity_adapter", {}).get("catalog_category")
                        == "resource"
                        else 1
                    )
                )
                * raven_launch_multiplier(actor, target),
                "pattern": pattern,
                "chain_index": 0,
                "visited": [target["id"]],
            }
            if "on_hit_status" in actor:
                packet["on_hit_status"] = deepcopy(actor["on_hit_status"])
            self._queue(packet, time + delay)
            trace.append(
                {
                    "time_seconds": time,
                    "event": "projectile_launch",
                    "source": actor["id"],
                    "target": target["id"],
                    "arrival_seconds": time + delay,
                    **(
                        {"weapon_state": deepcopy(weapon_state)}
                        if weapon_state is not None
                        else {}
                    ),
                }
            )

    def _damage_eligible(self, packet, actor, time):
        from .defending_heroes import defending_collateral_eligible

        pattern = packet["pattern"]
        return (
            _active(actor, time)
            and defending_collateral_eligible(packet, actor)
            and not actor.get("_tesla_hidden", False)
            and actor["team"] != packet["source_team"]
            and actor["kind"] in pattern["target_kinds"]
            and (
                actor["layer"] in pattern["target_layers"]
                or "spell_decoy_model" in actor
            )
            and (
                pattern.get("splash_layer_policy") != "primary_target_layer_only"
                or actor["layer"] == packet["primary_layer"]
            )
        )

    def _next_chain_target(self, packet, primary, actors, time):
        pattern = packet["pattern"]
        choices = []
        for target in actors.values():
            if untargetable_until(target) > time + EPSILON:
                continue
            if target["id"] in packet["visited"] or not self._damage_eligible(
                packet, target, time
            ):
                continue
            if (
                not pattern["allow_protected_links"]
                and target["immune_until"] > time + EPSILON
            ):
                continue
            if pattern["jump_metric"] == "footprint_distance":
                distance = footprint_distance(primary, target)
            else:
                first = center(primary)
                second = center(target)
                distance = hypot(first[0] - second[0], first[1] - second[1])
            if distance > pattern["jump_range"] + EPSILON:
                continue
            hp_tie = (
                -target["hp"]
                if pattern["tie_break"]
                == "distance_then_highest_current_hp_then_instance_id"
                else 0
            )
            choices.append((distance, hp_tie, target["id"], target))
        return min(choices, key=lambda item: item[:3])[-1] if choices else None

    def resolve(self, actors, time, trace, impact_callback=None, status_callback=None):
        from .damage_receipts import record_damage
        from .advanced_defenses import FANOUT_PATTERN, release_fanout_packets
        from .indirect_defenses import eagle_shell_impacts
        from .splash import directional_impacts
        from .valkyries import source_radial_impacts

        damage = defaultdict(float)
        while self.pending and self.pending[0][0] <= time + EPSILON:
            _, _, packet = heappop(self.pending)
            target = actors[packet["target"]]
            pattern = packet["pattern"]
            if (
                not _active(target, time)
                and pattern["projectile"].get("inactive_primary_policy", "fizzle")
                == "fizzle"
            ):
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "projectile_fizzle",
                        "source": packet["source"],
                        "target": target["id"],
                    }
                )
                continue
            if pattern["projectile"]["destination"] == "locked_actor_center_at_impact":
                point = center(target)
            else:
                point = packet["position"]
            if pattern["kind"] == "source_radial":
                impacts = source_radial_impacts(
                    packet, actors, time, self._damage_eligible
                )
                targets = [actor for actor, _ in impacts]
            elif pattern["kind"] == "eagle_shell":
                impacts = eagle_shell_impacts(
                    packet, point, actors, time, self._damage_eligible
                )
                targets = [actor for actor, _ in impacts]
            elif pattern["kind"] == "radial":
                targets = [
                    actor
                    for actor in actors.values()
                    if self._damage_eligible(packet, actor, time)
                    and target_distance(point, actor) <= pattern["radius"] + EPSILON
                ]
                impacts = [(actor, 1) for actor in targets]
            elif pattern["kind"] == "directional_splash":
                impacts = directional_impacts(
                    packet, point, actors, time, self._damage_eligible
                )
                targets = [actor for actor, _ in impacts]
            elif (
                target_distance(point, target)
                <= pattern["projectile"]["hit_radius"] + EPSILON
            ):
                targets = [target]
                impacts = [
                    (
                        target,
                        (
                            pattern["damage_multipliers"][packet["chain_index"]]
                            if pattern["kind"] == "chain"
                            else 1
                        ),
                    )
                ]
            else:
                targets = []
                impacts = []
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "projectile_miss",
                        "source": packet["source"],
                        "target": target["id"],
                    }
                )
            if impact_callback is not None and packet["chain_index"] == 0:
                impact_callback(
                    {
                        "source": packet["source"],
                        "primary_target": target["id"],
                        "position": point,
                        "hit_count": len(impacts),
                        "primary_protected": target["immune_until"] > time + EPSILON,
                    },
                    actors,
                    time,
                    trace,
                )
            for impacted, multiplier in impacts:
                from .recipe_troops import recipe_damage_multiplier
                from .wall_breakers import wall_blast_multiplier

                if status_callback is not None:
                    status_callback(packet, impacted, actors, time, trace)
                amount = (
                    (
                        packet["flat_damage"]
                        + impacted["maximum_hp"] * pattern["maximum_hp_fraction"]
                    )
                    * multiplier
                    * recipe_damage_multiplier(actors[packet["source"]], impacted)
                    * wall_blast_multiplier(actors[packet["source"]], impacted)
                )
                protected = impacted["immune_until"] > time + EPSILON
                resolved = record_damage(
                    self,
                    impacted,
                    amount,
                    time,
                    source_id=packet["source"],
                    source_actor_id=packet["source"],
                    source_team=packet["source_team"],
                    origin="weapon",
                )
                if resolved > 0:
                    damage[impacted["id"]] += resolved
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "projectile_impact",
                        "source": packet["source"],
                        "target": impacted["id"],
                        "damage": amount,
                        "protected": protected,
                        "chain_index": packet["chain_index"],
                        **(
                            {"fanout_link": deepcopy(packet["fanout_link"])}
                            if "fanout_link" in packet
                            else {}
                        ),
                        **(
                            {
                                "splash_multiplier": multiplier,
                                "impact_position": {"x": point[0], "y": point[1]},
                            }
                            if pattern["kind"] == "directional_splash"
                            else {}
                        ),
                    }
                )
            if pattern["kind"] == FANOUT_PATTERN and targets:
                released = release_fanout_packets(
                    packet, target, actors, time, self._damage_eligible
                )
                for arrival, following in released:
                    self._queue(following, arrival)
                trace.append(
                    {
                        "event": "fanout_release",
                        "time_seconds": time,
                        "source": packet["source"],
                        "primary": target["id"],
                        "secondary_targets": [
                            following["target"] for _, following in released
                        ],
                        "arrival_seconds": time + pattern["fanout"]["delay_seconds"],
                        "anchor_policy": pattern["fanout"]["anchor"],
                    }
                )
            if pattern["kind"] != "chain" or not targets:
                continue
            if (
                not pattern["allow_protected_links"]
                and target["immune_until"] > time + EPSILON
            ):
                continue
            next_index = packet["chain_index"] + 1
            if next_index >= len(pattern["damage_multipliers"]):
                continue
            next_target = self._next_chain_target(packet, target, actors, time)
            if next_target is not None:
                following = deepcopy(packet)
                following["chain_index"] = next_index
                following["target"] = next_target["id"]
                following["position"] = center(next_target)
                following["visited"].append(next_target["id"])
                self._queue(following, time + pattern["jump_delay_seconds"])
        return damage

    def next_boundary(self):
        return self.pending[0][0] if self.pending else None

    def result(self):
        return {
            **(
                {"inferno_ammunition": self.inferno_ammunition.result()}
                if self.inferno_ammunition.models
                else {}
            ),
            **(
                {"ammunition_remaining": dict(self.ammunition)}
                if self.ammunition
                else {}
            ),
            "pending_projectiles_at_horizon": [
                {
                    "arrival_seconds": time,
                    "source": packet["source"],
                    "target": packet["target"],
                }
                for time, _, packet in self.pending
            ],
        }
