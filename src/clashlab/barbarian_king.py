"""Explicit Spiky Ball, Giant Gauntlet and Stick Horse lifecycle hypotheses."""

from collections import defaultdict, deque
from copy import deepcopy
from heapq import heappop, heappush
from math import floor, hypot

from .spell_visibility import untargetable_until
from .common import InputError, identifier, integer, number, require
from .hero_extensions import (
    parameter_provenance,
    require_fields,
    require_values,
    source_quantity,
    validate_parameter_provenance,
)
from .rates import rescale_remaining_cooldown, skip_elapsed_pulses
from .spatial import EPSILON, _active, center, target_distance


EQUIPMENT = {"spiky-ball", "giant-gauntlet", "stick-horse"}


def compile_king_equipment(instance, hero, catalog, movement_units_per_tile=8):
    require_fields(instance, {"entity", "level", "parameters"}, "King equipment")
    entity_id = instance["entity"]
    if entity_id not in EQUIPMENT or hero["entity"] != "barbarian-king":
        raise InputError("Unsupported King equipment owner or item")
    level = integer(instance["level"], "King equipment level", 1)
    if not catalog.available(entity_id, level, hero["town_hall"]):
        raise InputError("King equipment level is unavailable at this Town Hall")
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
    if entity_id == "spiky-ball":
        model.update(
            damage_per_target=stats["projectileDamagePerTarget"],
            target_count=stats["numberOfTargets"],
        )
    elif entity_id == "giant-gauntlet":
        model.update(
            duration_seconds=source_quantity(stats["abilityDuration"], "s"),
            incoming_damage_multiplier=1
            - source_quantity(stats["incomingDamageReduction"], "%") / 100,
            splash_radius=entity["ability"]["areaDamageRadius"],
            self_healing_per_second=stats["selfHealingPerSecond"],
        )
    else:
        model.update(
            duration_seconds=source_quantity(stats["abilityDuration"], "s"),
            movement_bonus_tiles_per_second=stats["movementSpeedIncrease"]
            / number(movement_units_per_tile, "King movement conversion", EPSILON),
            attack_rate_multiplier=1
            + source_quantity(
                stats["attackSpeedIncrease"], "%", allow_leading_plus=True
            )
            / 100,
        )
    validate_king_equipment(model)
    return model, row


def validate_king_equipment(model):
    entity_id = require(model, "entity")
    additions = {
        "spiky-ball": {"damage_per_target", "target_count"},
        "giant-gauntlet": {
            "duration_seconds",
            "incoming_damage_multiplier",
            "splash_radius",
            "self_healing_per_second",
        },
        "stick-horse": {
            "duration_seconds",
            "movement_bonus_tiles_per_second",
            "attack_rate_multiplier",
        },
    }
    if entity_id not in additions:
        raise InputError("Unsupported King equipment runtime entity")
    require_fields(
        model,
        {
            "entity",
            "level",
            "ability_type",
            "source",
            "behavior_source",
            "parameters",
            "source_description",
            "parameter_provenance",
        }
        | additions[entity_id],
        "King equipment runtime model",
    )
    expected_type = "Passive" if entity_id == "stick-horse" else "Active"
    if model["ability_type"] != expected_type:
        raise InputError("King equipment activation type does not match its behavior")
    integer(model["level"], "runtime King equipment level", 1)
    identifier(model["source"], "runtime King statistic source")
    identifier(model["behavior_source"], "runtime King behavior source")
    for field in additions[entity_id]:
        if field == "target_count":
            integer(model[field], "Spiky Ball targets", 1)
        else:
            minimum = (
                EPSILON
                if field
                in {"duration_seconds", "splash_radius", "attack_rate_multiplier"}
                else 0
            )
            number(
                model[field],
                field,
                minimum,
                1 if field == "incoming_damage_multiplier" else None,
            )
    parameters = model["parameters"]
    fields = {"source"}
    if entity_id == "spiky-ball":
        fields |= {
            "initial_range_tiles",
            "bounce_range_tiles",
            "projectile_speed_tiles_per_second",
            "first_delay_seconds",
            "bounce_delay_seconds",
            "selection",
            "target_kinds",
            "target_layers",
            "visibility",
            "protected_targets",
            "target_budget",
            "inactive_target",
            "source_death",
            "damage_scaling",
        }
        policies = {
            "selection": "nearest_footprint_then_instance_id_without_revisits",
            "visibility": "exclude_hidden_teslas_and_invisible_buildings_at_each_launch",
            "protected_targets": "eligible_and_consume_target_slot",
            "target_budget": "consume_slot_on_launch_even_if_target_dies",
            "inactive_target": "continue_from_captured_target_center_without_damage",
            "source_death": "released_ball_persists",
            "damage_scaling": "equipment_flat_damage_times_hero_profile_only_hypothesis",
        }
    elif entity_id == "giant-gauntlet":
        fields |= {
            "splash_center",
            "splash_target_kinds",
            "splash_target_layers",
            "wall_swing",
            "self_heal_interval_seconds",
            "first_self_heal_delay_seconds",
            "self_heal_lifetime",
            "freeze",
            "damage_reduction_stacking",
        }
        policies = {
            "splash_center": "king_center_at_instant_launch_hypothesis",
            "wall_swing": "same_area_geometry_and_shared_main_attack_clock",
            "self_heal_lifetime": "while_deployed_independent_of_active_duration",
            "freeze": "duration_and_healing_clock_continue_while_frozen",
            "damage_reduction_stacking": "multiply_independent_incoming_damage_factors",
        }
    else:
        fields |= {"trigger", "freeze", "expiry_inside_wall", "bonus_stacking"}
        policies = {
            "trigger": "one_duration_from_actual_deployment",
            "freeze": "duration_continues_while_frozen",
            "expiry_inside_wall": "finish_retained_crossing_or_nearest_clear_cardinal_exit",
            "bonus_stacking": "add_movement_bonus_multiply_independent_attack_rate",
        }
    require_fields(parameters, fields, "King equipment parameters")
    identifier(parameters["source"], "King equipment parameter source")
    validate_parameter_provenance(model)
    for field, expected in policies.items():
        if parameters[field] != expected:
            raise InputError("Unsupported King equipment lifecycle policy")
    if entity_id == "spiky-ball":
        for field in (
            "initial_range_tiles",
            "bounce_range_tiles",
            "first_delay_seconds",
            "bounce_delay_seconds",
        ):
            number(parameters[field], field, 0)
        number(
            parameters["projectile_speed_tiles_per_second"], "Spiky Ball speed", EPSILON
        )
        if parameters["target_kinds"] != ["defense", "building"] or parameters[
            "target_layers"
        ] != ["ground"]:
            raise InputError(
                "Spiky Ball explicitly targets ground buildings and defenses"
            )
    elif entity_id == "giant-gauntlet":
        require_values(
            parameters["splash_target_kinds"],
            {"unit", "defense", "building", "wall"},
            "Gauntlet splash kinds",
        )
        if not {"defense", "building", "wall"} <= set(
            parameters["splash_target_kinds"]
        ):
            raise InputError(
                "Gauntlet splash must cover King primary buildings and walls"
            )
        if parameters["splash_target_layers"] != ["ground"]:
            raise InputError("Gauntlet splash uses explicit ground-only King damage")
        interval = number(
            parameters["self_heal_interval_seconds"], "Gauntlet heal interval", EPSILON
        )
        number(
            parameters["first_self_heal_delay_seconds"],
            "Gauntlet first heal delay",
            0,
            interval,
        )


def _enemy_wall(actor, king, time):
    return (
        actor["kind"] == "wall"
        and actor["team"] != king["team"]
        and _active(actor, time)
    )


class BarbarianKingCombat:
    """King equipment hooks sharing the common hero's single ability charge."""

    def __init__(self, actors, combat, select_target):
        self.equipment = {}
        self.base_patterns = {}
        self.base_walls = {}
        self.activated = set()
        self.gauntlet_until = {}
        self.heal_next = {}
        self.horse_until = {}
        self.egress = {}
        self.packets = []
        self.sequence = 0
        self.log = []
        self.combat = combat
        self.ordinary_select_target = select_target
        for key, actor in actors.items():
            if actor.get("hero_model", {}).get("entity") != "barbarian-king":
                continue
            if (
                actor["team"] != "attack"
                or actor["layer"] != "ground"
                or actor["movement"] != "ground"
            ):
                raise InputError("King equipment requires the attacking ground hero")
            if actor["wall_behavior"]["kind"] not in {"avoid", "clear_obstructions"}:
                raise InputError(
                    "The King needs an ordinary wall policy beneath Stick Horse"
                )
            if (
                actor["wall_behavior"]["kind"] == "clear_obstructions"
                and actor["wall_behavior"]["weapon"]["cooldown"]
                != "shared_with_main_weapon"
            ):
                raise InputError("King wall swings share the main weapon clock")
            self.equipment[key] = {}
            self.base_patterns[key] = deepcopy(actor["attack_model"])
            self.base_walls[key] = deepcopy(actor["wall_behavior"])
            self.heal_next[key] = None
            self.horse_until[key] = None
            for item in actor["hero_model"]["equipment"]:
                if item["entity"] == "earthquake-boots":
                    from .recipe_equipment import validate_recipe_equipment

                    validate_recipe_equipment(item)
                    continue
                if item["entity"] in {"rage-vial", "vampstache"}:
                    from .equipment_lifecycles import validate_equipment

                    validate_equipment(item)
                    continue
                validate_king_equipment(item)
                if item["entity"] in self.equipment[key]:
                    raise InputError("King equipment cannot be duplicated")
                self.equipment[key][item["entity"]] = deepcopy(item)
            gauntlet = self.equipment[key].get("giant-gauntlet")
            if gauntlet is not None:
                wall_range = actor["wall_behavior"].get("weapon", {}).get("range", 0)
                if max(actor["range"], wall_range) > gauntlet["splash_radius"]:
                    raise InputError(
                        "Gauntlet splash must include each in-range primary"
                    )

    def _ball_target(self, point, king_team, actors, time, model, visited, radius):
        parameters = model["parameters"]
        choices = []
        for actor in actors.values():
            if (
                actor["id"] in visited
                or not _active(actor, time)
                or actor["team"] == king_team
                or actor["kind"] not in parameters["target_kinds"]
                or actor["movement"] != "stationary"
                or actor["layer"] not in parameters["target_layers"]
                or actor.get("_tesla_hidden", False)
                or untargetable_until(actor) > time + EPSILON
            ):
                continue
            distance = target_distance(point, actor)
            if distance <= radius + EPSILON:
                choices.append((distance, actor["id"], actor))
        return min(choices, key=lambda item: item[:2])[-1] if choices else None

    def _queue_ball(self, packet, target, time, first, trace):
        parameters = packet["equipment"]["parameters"]
        delay = (
            parameters["first_delay_seconds"]
            if first
            else parameters["bounce_delay_seconds"]
        )
        point = center(target)
        delay += (
            hypot(point[0] - packet["point"][0], point[1] - packet["point"][1])
            / parameters["projectile_speed_tiles_per_second"]
        )
        packet = {
            **deepcopy(packet),
            "target": target["id"],
            "point": point,
            "remaining": packet["remaining"] - 1,
            "visited": [*packet["visited"], target["id"]],
        }
        heappush(self.packets, (time + delay, self.sequence, packet))
        self.sequence += 1
        trace.append(
            {
                "event": "spiky_ball_launch",
                "time_seconds": time,
                "source": packet["source"],
                "target": target["id"],
                "arrival_seconds": time + delay,
                "targets_remaining": packet["remaining"],
            }
        )

    def activate(self, hero_id, actors, time, trace):
        if (
            hero_id not in self.equipment
            or hero_id in self.activated
            or not _active(actors[hero_id], time)
        ):
            return False
        self.activated.add(hero_id)
        king = actors[hero_id]
        gauntlet = self.equipment[hero_id].get("giant-gauntlet")
        if gauntlet is not None:
            self.gauntlet_until[hero_id] = time + gauntlet["duration_seconds"]
        ball = self.equipment[hero_id].get("spiky-ball")
        if ball is not None:
            target = self._ball_target(
                center(king),
                king["team"],
                actors,
                time,
                ball,
                [],
                ball["parameters"]["initial_range_tiles"],
            )
            if target is not None:
                self._queue_ball(
                    {
                        "source": hero_id,
                        "source_team": king["team"],
                        "equipment": ball,
                        "point": center(king),
                        "remaining": ball["target_count"],
                        "visited": [],
                        "damage": ball["damage_per_target"]
                        * king["hero_model"]["damage_multiplier"],
                    },
                    target,
                    time,
                    True,
                    trace,
                )
        return True

    def _restore_wall_policy(self, king):
        base = deepcopy(self.base_walls[king["id"]])
        if base["kind"] == "clear_obstructions":
            base["weapon"]["damage"] = king["damage"]
        king["wall_behavior"] = base
        king.pop("_remaining_path", None)
        king.pop("_path_signature", None)

    def _egress_route(self, king, actors, time, width, height):
        walls = {
            (floor(actor["x"]), floor(actor["y"]))
            for actor in actors.values()
            if _enemy_wall(actor, king, time)
        }
        current = floor(king["x"]), floor(king["y"])
        retained = king.get("_remaining_path", [])
        route = []
        for point in retained:
            route.append(point)
            if (floor(point[0]), floor(point[1])) not in walls:
                return route
        solid = set()
        for actor in actors.values():
            if (
                not _active(actor, time)
                or not actor["blocking"]
                or _enemy_wall(actor, king, time)
            ):
                continue
            for x in range(floor(actor["x"]), floor(actor["x"] + actor["width"])):
                for y in range(floor(actor["y"]), floor(actor["y"] + actor["height"])):
                    solid.add((x, y))
        pending = deque([current])
        previous = {current: None}
        destination = None
        while pending:
            cell = pending.popleft()
            if cell not in walls and cell not in solid:
                destination = cell
                break
            x, y = cell
            for neighbor in sorted(((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y))):
                if (
                    neighbor in previous
                    or neighbor in solid
                    or not (0 <= neighbor[0] < width and 0 <= neighbor[1] < height)
                ):
                    continue
                previous[neighbor] = cell
                pending.append(neighbor)
        if destination is None:
            raise InputError("Expired Stick Horse has no legal declared wall exit")
        cells = []
        while destination != current:
            cells.append(destination)
            destination = previous[destination]
        return [(x + 0.5, y + 0.5) for x, y in reversed(cells)]

    def prepare(self, actors, time, trace, width, height):
        for key, equipment in self.equipment.items():
            king = actors[key]
            if not _active(king, time):
                continue
            gauntlet = equipment.get("giant-gauntlet")
            gauntlet_active = self.gauntlet_until.get(key, 0) > time + EPSILON
            king["_hero_incoming_damage_multiplier"] = (
                gauntlet["incoming_damage_multiplier"] if gauntlet_active else 1
            )
            pattern = deepcopy(self.base_patterns[key])
            if gauntlet_active:
                parameters = gauntlet["parameters"]
                pattern.update(
                    kind="source_radial",
                    radius=gauntlet["splash_radius"],
                    target_kinds=list(parameters["splash_target_kinds"]),
                    target_layers=list(parameters["splash_target_layers"]),
                    projectile={
                        "timing": "instant",
                        "delay_seconds": 0,
                        "destination": "fixed_source_center_at_launch",
                        "hit_radius": 0,
                        "inactive_primary_policy": "resolve_at_fixed_launch_position",
                    },
                )
            king["attack_model"] = pattern
            self.combat.patterns[key] = pattern
            if gauntlet is not None and self.heal_next[key] is None:
                self.heal_next[key] = (
                    king["spawn_seconds"]
                    + gauntlet["parameters"]["first_self_heal_delay_seconds"]
                )
            horse = equipment.get("stick-horse")
            if horse is None:
                continue
            if self.horse_until[key] is None:
                self.horse_until[key] = (
                    king["spawn_seconds"] + horse["duration_seconds"]
                )
            riding = self.horse_until[key] > time + EPSILON
            new_rate = horse["attack_rate_multiplier"] if riding else 1
            old_rate = king.get("_hero_attack_rate", 1)
            if abs(old_rate - new_rate) > EPSILON:
                rescale_remaining_cooldown(king, time, old_rate, new_rate)
            king["_hero_attack_rate"] = new_rate
            multiplier = king["entity_adapter"]["modifiers"][
                "movement_speed_multiplier"
            ]
            king["_hero_movement_bonus"] = (
                horse["movement_bonus_tiles_per_second"] * multiplier if riding else 0
            )
            if riding:
                king["wall_behavior"] = {
                    "kind": "jump_enemy_walls",
                    "source": horse["behavior_source"],
                }
                continue
            pending_exit = self.egress.get(key)
            if pending_exit:
                destination = pending_exit[-1]
                if (
                    hypot(
                        center(king)[0] - destination[0],
                        center(king)[1] - destination[1],
                    )
                    > EPSILON
                ):
                    king["wall_behavior"] = {
                        "kind": "jump_enemy_walls",
                        "source": horse["behavior_source"],
                    }
                    continue
                self.egress.pop(key)
                self._restore_wall_policy(king)
                trace.append(
                    {
                        "event": "stick_horse_expired",
                        "time_seconds": time,
                        "source": key,
                    }
                )
                continue
            walls = [
                actor for actor in actors.values() if _enemy_wall(actor, king, time)
            ]
            in_wall = any(
                actor["x"] <= king["x"] < actor["x"] + actor["width"]
                and actor["y"] <= king["y"] < actor["y"] + actor["height"]
                for actor in walls
            )
            if in_wall:
                if key not in self.egress:
                    self.egress[key] = self._egress_route(
                        king, actors, time, width, height
                    )
                    trace.append(
                        {
                            "event": "stick_horse_finishing_wall_exit",
                            "time_seconds": time,
                            "source": key,
                            "route": list(self.egress[key]),
                        }
                    )
                king["wall_behavior"] = {
                    "kind": "jump_enemy_walls",
                    "source": horse["behavior_source"],
                }
            elif king["wall_behavior"]["kind"] == "jump_enemy_walls":
                self.egress.pop(key, None)
                self._restore_wall_policy(king)
                trace.append(
                    {
                        "event": "stick_horse_expired",
                        "time_seconds": time,
                        "source": key,
                    }
                )

    def select_target(self, actor, actors, time, blocked, width, height):
        if actor["id"] not in self.egress:
            return self.ordinary_select_target(
                actor, actors, time, blocked, width, height
            )
        route = self.egress[actor["id"]]
        while (
            route
            and hypot(center(actor)[0] - route[0][0], center(actor)[1] - route[0][1])
            <= EPSILON
        ):
            route.pop(0)
        return None, list(route)

    def wall_impacts(self, actor, primary, actors, time):
        """Return a Gauntlet wall swing for the shared wall clock to emit once."""
        if (
            actor["id"] not in self.equipment
            or self.gauntlet_until.get(actor["id"], 0) <= time + EPSILON
        ):
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
            and target["layer"] in pattern["target_layers"]
            and not target.get("_tesla_hidden", False)
            and target_distance(center(actor), target) <= pattern["radius"] + EPSILON
            and defending_collateral_eligible(packet, target)
        ]

    def resolve(self, actors, time, trace, receipts=None):
        damage = defaultdict(float)
        healing = defaultdict(float)
        for key, clock in self.heal_next.items():
            if clock is not None and actors[key].get("_recalled", False):
                interval = self.equipment[key]["giant-gauntlet"]["parameters"][
                    "self_heal_interval_seconds"
                ]
                self.heal_next[key] = skip_elapsed_pulses(clock, interval, time)
                continue
            if (
                clock is None
                or clock > time + EPSILON
                or not _active(actors[key], time)
            ):
                continue
            gauntlet = self.equipment[key]["giant-gauntlet"]
            interval = gauntlet["parameters"]["self_heal_interval_seconds"]
            healing[key] += gauntlet["self_healing_per_second"] * interval
            self.heal_next[key] += interval
        while self.packets and self.packets[0][0] <= time + EPSILON:
            _, _, packet = heappop(self.packets)
            target = actors[packet["target"]]
            applied = 0
            if _active(target, time):
                if receipts is not None:
                    applied = receipts.register(
                        target,
                        packet["damage"],
                        time,
                        source_id=packet["source"],
                        source_actor_id=packet["source"],
                        source_team=packet["source_team"],
                        origin="ability",
                    )
                elif target["immune_until"] <= time + EPSILON:
                    applied = packet["damage"]
                damage[target["id"]] += applied
            trace.append(
                {
                    "event": "spiky_ball_impact",
                    "time_seconds": time,
                    "source": packet["source"],
                    "target": target["id"],
                    "damage": applied,
                }
            )
            if packet["remaining"] <= 0:
                continue
            candidate = self._ball_target(
                packet["point"],
                packet["source_team"],
                actors,
                time,
                packet["equipment"],
                packet["visited"],
                packet["equipment"]["parameters"]["bounce_range_tiles"],
            )
            if candidate is not None:
                self._queue_ball(packet, candidate, time, False, trace)
        return damage, healing

    def next_boundary(self, time):
        values = list(self.gauntlet_until.values())
        values.extend(value for value in self.horse_until.values() if value is not None)
        values.extend(value for value in self.heal_next.values() if value is not None)
        if self.packets:
            values.append(self.packets[0][0])
        future = [value for value in values if value > time + EPSILON]
        return min(future) if future else None

    def frame(self, actor_id, actor):
        if actor_id not in self.equipment:
            return {}
        return {
            "king_gauntlet_until_seconds": self.gauntlet_until.get(actor_id),
            "king_stick_horse_until_seconds": self.horse_until.get(actor_id),
            "king_finishing_wall_exit": actor_id in self.egress,
        }

    def result(self):
        return {
            "active_equipment_used_for": sorted(self.activated),
            "pending_spiky_ball_packets": len(self.packets),
            "finishing_wall_exit": sorted(self.egress),
            "game_calibrated": False,
        }
