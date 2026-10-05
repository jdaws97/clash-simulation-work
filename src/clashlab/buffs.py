"""Fixed Rage/Haste fields with explicit continuous membership and lingering.

Catalog speedIncrease is selected as additive movement units, never attack
cadence. Damage/healing bonuses are captured by their callers at launch. The
runtime only maintains separate effect factors; it never rewrites base stats.
"""

from copy import deepcopy
from math import hypot, sqrt

from .common import InputError, identifier, integer, number, require
from .spatial import EPSILON, _active, center


BUFF_SPELLS = frozenset({"rage-spell", "haste-spell"})
BUFF_CLASSES = frozenset({"troop", "hero", "pet", "siege", "other"})
CLASS_FACTORS = {
    "damage_bonus_multiplier",
    "movement_bonus_multiplier",
    "healing_bonus_multiplier",
}
BUFF_RULES = {
    "area_buff_membership": "continuous_exact_polyline_entry_and_exit_with_explicit_linger",
    "area_buff_stack": "strongest_bonus_per_axis_across_rage_and_haste",
    "area_buff_speed": "add_catalog_speed_bonus_before_hazard_and_hit_status_slow_factors",
    "area_buff_damage": "capture_flat_weapon_damage_multiplier_at_launch",
    "area_buff_healing": "capture_emitting_healer_multiplier_at_launch_not_recipient_or_spell_healing",
    "area_buff_attack_clock": "no_attack_rate_or_cooldown_change",
    "area_buff_persistence": "fixed_cast_field_independent_of_caster_state",
}
PARAMETERS = {
    "source",
    "caster_team",
    "radius_multiplier",
    "duration_basis",
    "duration_multiplier",
    "damage_statistic_basis",
    "damage_bonus_multiplier",
    "movement_statistic_basis",
    "movement_bonus_multiplier",
    "healing_scaling_basis",
    "membership_policy",
    "exit_linger_seconds",
    "field_end_policy",
    "class_scaling",
    "stacking_policy",
    "protection_policy",
    "source_persistence",
}
EXTRACTION_SOURCE = (
    "https://raw.githubusercontent.com/ClashKingInc/ClashKingAssets/"
    "b8f42a707fe92d5293d46088bf536450ae422e7b/assets/static_data.json"
)


def damage_multiplier(actor):
    """Apply to flat emitted weapon damage exactly once at launch or wall hit."""
    ordinary = actor.get("_buff_damage_multiplier", 1)
    tower = actor.get("_spell_tower_damage_multiplier", 1)
    if actor.get("_spell_tower_rage_composition") == "strongest_with_other_sources":
        combined = max(ordinary, tower)
    else:
        combined = ordinary * tower
    return (
        combined
        * actor.get("_guardian_self_damage_multiplier", 1)
        * actor.get("_guardian_field_damage_multiplier", 1)
        * actor.get("_hero_damage_multiplier", 1)
        * actor.get("_recipe_damage_multiplier", 1)
        * actor.get("_equipment_child_damage_multiplier", 1)
        * actor.get("_equipment_field_damage_multiplier", 1)
    )


def healing_multiplier(actor):
    """Capture on an emitting healer's packet, never on its recipient."""
    return actor.get("_buff_healing_multiplier", 1)


def movement_bonus(actor):
    """Add before the shared movement slow factors; Freeze still gates movement."""
    return actor.get("_buff_movement_bonus", 0)


def _validate_policy(model):
    if model["membership_policy"] != "continuous_exact_crossings":
        raise InputError("Area buffs currently require continuous exact membership")
    if model["field_end_policy"] not in {
        "clear_immediately",
        "linger_from_field_end",
    }:
        raise InputError("Area buff field-end policy must be explicit")
    if model["stacking_policy"] != "strongest_bonus_per_axis":
        raise InputError("Area buffs require strongest-per-axis stacking")
    if model["protection_policy"] != "beneficial_effects_ignore_damage_immunity":
        raise InputError("Area buff immunity interaction must be explicit")
    if model["source_persistence"] != "fixed_field_independent_of_caster":
        raise InputError("Area buffs require a persistent fixed cast field")
    number(model["exit_linger_seconds"], "area buff exit linger", 0)
    scaling = model["class_scaling"]
    if not isinstance(scaling, dict) or set(scaling) != BUFF_CLASSES:
        raise InputError(
            "Area buffs need explicit troop, hero, pet, siege and other scaling"
        )
    for factors in scaling.values():
        if factors is None:
            continue
        if not isinstance(factors, dict) or set(factors) != CLASS_FACTORS:
            raise InputError(
                "Each buff class needs explicit damage, movement and healing factors"
            )
        for name, value in factors.items():
            number(value, name, 0)


def compile_buff_spell(instance, catalog, movement_units_per_tile):
    """Compile one paid cast; army inventory/capacity validation stays upstream.

    Numeric interpretation and class scaling are deliberately selected inputs.
    Continuous membership is a declared model, not a claim to reproduce pulses.
    """
    entity_id = require(instance, "entity")
    if entity_id not in BUFF_SPELLS:
        raise InputError("Area buff compiler supports Rage and Haste Spell")
    level = integer(require(instance, "level"), "buff spell level", 1)
    town_hall = integer(
        require(instance, "town_hall"),
        "buff spell Town Hall",
        1,
        catalog.maximum_town_hall,
    )
    if not catalog.available(entity_id, level, town_hall):
        raise InputError("Buff spell level is unavailable at the declared Town Hall")
    conversion = number(movement_units_per_tile, "movement units per tile", EPSILON)
    parameters = require(instance, "parameters")
    if not isinstance(parameters, dict) or set(parameters) != PARAMETERS:
        raise InputError(
            "Area buff spells require every explicit behavior and statistic policy"
        )
    identifier(parameters["source"], "buff behavior evidence")
    if parameters["caster_team"] != "attack":
        raise InputError("This adapter supports attacking area buff spells")
    _validate_policy(parameters)
    for field in ("radius_multiplier", "duration_multiplier"):
        number(parameters[field], field, EPSILON)
    for field in ("damage_bonus_multiplier", "movement_bonus_multiplier"):
        number(parameters[field], field, 0)
    if (
        parameters["movement_statistic_basis"]
        != "snapshot_speed_increase_is_additive_catalog_units"
    ):
        raise InputError(
            "Buff movement needs an explicit additive catalog-unit interpretation"
        )
    if parameters["healing_scaling_basis"] not in {
        "damage_bonus_scales_source_healing",
        "no_healing_boost",
    }:
        raise InputError("Rage healing output interpretation must be explicit")
    entity = catalog.entity(entity_id)
    row = catalog.level(entity_id, level)
    if entity_id == "rage-spell":
        if parameters["duration_basis"] != "snapshot_pulse_count_times_interval":
            raise InputError("Rage duration needs its explicit pulse-count mapping")
        if (
            parameters["damage_statistic_basis"]
            != "snapshot_damage_increase_is_bonus_percent"
        ):
            raise InputError(
                "Rage damageIncrease must explicitly mean a bonus percentage"
            )
        duration = integer(require(entity, "numberOfPulses"), "Rage pulse count", 1)
        duration *= number(
            require(entity, "timeBetweenPulses"), "Rage pulse interval", EPSILON
        )
        damage_bonus = (
            number(require(row, "damageIncrease"), "Rage damage bonus percentage", 0)
            / 100
        )
    else:
        if parameters["duration_basis"] != "snapshot_spell_duration":
            raise InputError(
                "Haste duration must use the declared positive spellDuration"
            )
        if parameters["damage_statistic_basis"] != "haste_has_no_damage_bonus":
            raise InputError("Haste cannot acquire a Rage damage bonus")
        duration = number(
            require(row, "spellDuration"), "Haste spell duration", EPSILON
        )
        damage_bonus = 0
    damage_bonus *= parameters["damage_bonus_multiplier"]
    healing_bonus = (
        damage_bonus
        if parameters["healing_scaling_basis"] == "damage_bonus_scales_source_healing"
        else 0
    )
    return {
        "id": identifier(require(instance, "id"), "buff cast id"),
        "kind": "area_buff",
        "entity": entity_id,
        "source": parameters["source"],
        "statistics_source": catalog.records[entity_id]["source"],
        "start_seconds": number(require(instance, "time_seconds"), "buff cast time", 0),
        "duration_seconds": duration * parameters["duration_multiplier"],
        "area": {
            "x": number(require(instance, "x"), "buff center x", 0),
            "y": number(require(instance, "y"), "buff center y", 0),
            "radius": number(
                row.get("radius", entity.get("radius")), "buff radius", EPSILON
            )
            * parameters["radius_multiplier"],
            "target_team": "attack",
            "target_kinds": ["unit"],
            "target_layers": ["ground", "air"],
        },
        "movement_bonus_tiles_per_second": number(
            require(row, "speedIncrease"), "buff catalog movement bonus", 0
        )
        / conversion
        * parameters["movement_bonus_multiplier"],
        "damage_bonus_fraction": damage_bonus,
        "healing_bonus_fraction": healing_bonus,
        **{
            name: deepcopy(parameters[name])
            for name in (
                "membership_policy",
                "exit_linger_seconds",
                "field_end_policy",
                "class_scaling",
                "stacking_policy",
                "protection_policy",
                "source_persistence",
            )
        },
        "entity_adapter": {
            "entity": entity_id,
            "level": level,
            "town_hall": town_hall,
            "housing_space": integer(
                require(entity, "housingSpace"), "spell housing space", 1
            ),
            "snapshot_verification": catalog.records[entity_id]["verification"],
            "behavior_verification": "declared_continuous_field_and_class_scaling_not_replay_validated",
            "parameters": deepcopy(parameters),
            "movement_units_per_tile": conversion,
            "selected_unscaled_duration_seconds": duration,
            "duration_evidence": (
                {
                    "catalog_fields": "numberOfPulses * timeBetweenPulses",
                    "snapshot_boost_time_not_automatically_used_as_linger": entity.get(
                        "boostTime"
                    ),
                }
                if entity_id == "rage-spell"
                else {
                    "catalog_fields": "spellDuration",
                    "excluded_reference": {
                        "source": EXTRACTION_SOURCE,
                        "entity_data_id": 26000011,
                        "field": "levels[].duration",
                        "value": 0,
                        "decision": "extraction_zero_does_not_replace_positive_catalog_duration",
                    },
                }
            ),
        },
    }


def validate_buff_field(field, actors):
    for key in ("id", "source", "statistics_source"):
        identifier(require(field, key), f"buff {key}")
    if field.get("kind") != "area_buff" or field.get("entity") not in BUFF_SPELLS:
        raise InputError("Area buff field must identify a supported Rage or Haste cast")
    number(require(field, "start_seconds"), "buff start", 0)
    number(require(field, "duration_seconds"), "buff duration", EPSILON)
    for name in (
        "movement_bonus_tiles_per_second",
        "damage_bonus_fraction",
        "healing_bonus_fraction",
    ):
        number(require(field, name), name, 0)
    if field["entity"] == "haste-spell" and (
        field["damage_bonus_fraction"] != 0 or field["healing_bonus_fraction"] != 0
    ):
        raise InputError("Haste fields can only supply movement bonuses")
    for key in (
        "membership_policy",
        "exit_linger_seconds",
        "field_end_policy",
        "class_scaling",
        "stacking_policy",
        "protection_policy",
        "source_persistence",
    ):
        require(field, key)
    _validate_policy(field)
    area = require(field, "area")
    if not isinstance(area, dict) or set(area) != {
        "x",
        "y",
        "radius",
        "target_team",
        "target_kinds",
        "target_layers",
    }:
        raise InputError("Area buffs require explicit geometry and target filters")
    number(area["x"], "buff area x", 0)
    number(area["y"], "buff area y", 0)
    number(area["radius"], "buff area radius", EPSILON)
    if area["target_team"] != "attack" or area["target_kinds"] != ["unit"]:
        raise InputError(
            "Area buffs apply to attacking units, not buildings or hostile targets"
        )
    layers = area["target_layers"]
    if (
        not isinstance(layers, list)
        or set(layers) != {"ground", "air"}
        or len(layers) != 2
    ):
        raise InputError("Rage and Haste require both explicit unit target layers")
    for actor in actors.values():
        if actor["kind"] == "unit" and actor["team"] == area["target_team"]:
            if actor.get("buff_class") not in BUFF_CLASSES:
                raise InputError(
                    "Every allied buff recipient needs an explicit buff_class"
                )


def _circle_events(start, end, origin, radius):
    """Return directed circle contacts by segment distance, including tangency."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = hypot(dx, dy)
    if length <= EPSILON:
        return []
    offset_x, offset_y = start[0] - origin[0], start[1] - origin[1]
    projection = (offset_x * dx + offset_y * dy) / length
    discriminant = projection * projection - (
        offset_x * offset_x + offset_y * offset_y - radius * radius
    )
    if discriminant < -EPSILON:
        return []
    root = sqrt(max(discriminant, 0))
    contacts = [(-projection - root, root > EPSILON)]
    if root > EPSILON:
        contacts.append((-projection + root, False))
    return [
        (max(distance, 0), inside_after)
        for distance, inside_after in contacts
        if -EPSILON <= distance <= length + EPSILON
    ]


class BuffCombat:
    """Continuous fixed fields; strongest bonuses survive weaker-source expiry."""

    def __init__(self, actors, fields):
        if not isinstance(fields, list):
            raise InputError("Area buffs must be an explicit list of casts")
        self.fields = {}
        self.inside = {}
        self.linger_until = {}
        self.boundary_sides = {}
        self.crossing_hints = {}
        self.started = set()
        self.expired = set()
        self.last_time = None
        for field in fields:
            self.schedule(field, actors)

    def schedule(self, field, actors):
        validate_buff_field(field, actors)
        if field["id"] in self.fields:
            raise InputError("A buff cast ID can be scheduled only once")
        if (
            self.last_time is not None
            and field["start_seconds"] < self.last_time - EPSILON
        ):
            raise InputError("A buff cannot be cast retroactively")
        self.fields[field["id"]] = deepcopy(field)

    @staticmethod
    def _live(field, time):
        return (
            field["start_seconds"] <= time + EPSILON
            and time < field["start_seconds"] + field["duration_seconds"] - EPSILON
        )

    @staticmethod
    def _eligible(field, actor, time):
        return (
            _active(actor, time)
            and not actor.get("beneficial_field_immunity", False)
            and actor["kind"] == "unit"
            and actor["team"] == field["area"]["target_team"]
            and actor["layer"] in field["area"]["target_layers"]
            and field["class_scaling"].get(actor.get("buff_class")) is not None
        )

    def _geometry_inside(self, field, actor):
        key = field["id"], actor["id"]
        point = center(actor)
        side = self.boundary_sides.get(key)
        if side is not None:
            if (
                hypot(point[0] - side["position"][0], point[1] - side["position"][1])
                <= EPSILON * 128
            ):
                return side["inside_after"]
            self.boundary_sides.pop(key)
        area = field["area"]
        return (
            hypot(point[0] - area["x"], point[1] - area["y"])
            <= area["radius"] + EPSILON
        )

    def _consume_crossings(self, actors, time):
        for key, hint in list(self.crossing_hints.items()):
            if hint["time_seconds"] > time + EPSILON:
                continue
            actor = actors[key[1]]
            point = center(actor)
            if (
                abs(hint["time_seconds"] - time) <= EPSILON
                and hypot(
                    point[0] - hint["position"][0], point[1] - hint["position"][1]
                )
                <= EPSILON * 128
            ):
                self.boundary_sides[key] = hint
            self.crossing_hints.pop(key)

    def prepare(self, actors, time, trace):
        number(time, "buff preparation time", 0)
        if self.last_time is not None and time < self.last_time - EPSILON:
            raise InputError("Area buff runtime cannot move backward in time")
        self._consume_crossings(actors, time)
        self.last_time = time
        for field_id, field in sorted(self.fields.items()):
            end = field["start_seconds"] + field["duration_seconds"]
            if (
                field["start_seconds"] <= time + EPSILON
                and field_id not in self.started
            ):
                self.started.add(field_id)
                trace.append(
                    {
                        "event": "buff_field_start",
                        "time_seconds": time,
                        "field_id": field_id,
                    }
                )
            if end <= time + EPSILON and field_id not in self.expired:
                self.expired.add(field_id)
                trace.append(
                    {
                        "event": "buff_field_expire",
                        "time_seconds": time,
                        "field_id": field_id,
                    }
                )
        for actor in actors.values():
            movement, damage, healing = 0, 0, 0
            active_fields = []
            for field_id, field in sorted(self.fields.items()):
                key = field_id, actor["id"]
                eligible = self._eligible(field, actor, time)
                live = self._live(field, time)
                inside = eligible and live and self._geometry_inside(field, actor)
                was_inside = self.inside.get(key, False)
                end = field["start_seconds"] + field["duration_seconds"]
                if inside:
                    self.linger_until.pop(key, None)
                elif was_inside and eligible:
                    expiry = min(time, end) + field["exit_linger_seconds"]
                    if field["field_end_policy"] == "clear_immediately":
                        expiry = min(expiry, end)
                    self.linger_until[key] = expiry
                if not eligible or (
                    not live and field["field_end_policy"] == "clear_immediately"
                ):
                    self.linger_until.pop(key, None)
                self.inside[key] = inside
                if inside != was_inside:
                    trace.append(
                        {
                            "event": "buff_membership",
                            "time_seconds": time,
                            "field_id": field_id,
                            "target": actor["id"],
                            "inside": inside,
                        }
                    )
                lingering = self.linger_until.get(key, 0) > time + EPSILON
                if not inside and not lingering:
                    self.linger_until.pop(key, None)
                    continue
                factors = field["class_scaling"][actor["buff_class"]]
                movement = max(
                    movement,
                    field["movement_bonus_tiles_per_second"]
                    * factors["movement_bonus_multiplier"],
                )
                damage = max(
                    damage,
                    field["damage_bonus_fraction"] * factors["damage_bonus_multiplier"],
                )
                healing = max(
                    healing,
                    field["healing_bonus_fraction"]
                    * factors["healing_bonus_multiplier"],
                )
                active_fields.append(field_id)
            previous = (
                movement_bonus(actor),
                actor.get("_buff_damage_multiplier", 1),
                healing_multiplier(actor),
                actor.get("_buff_fields", []),
            )
            current = (movement, 1 + damage, 1 + healing, active_fields)
            if previous != current:
                trace.append(
                    {
                        "event": "buff_status_change",
                        "time_seconds": time,
                        "target": actor["id"],
                        "movement_bonus_tiles_per_second": movement,
                        "damage_multiplier": 1 + damage,
                        "healing_multiplier": 1 + healing,
                        "fields": list(active_fields),
                    }
                )
            actor["_buff_movement_bonus"] = movement
            actor["_buff_damage_multiplier"] = 1 + damage
            actor["_buff_healing_multiplier"] = 1 + healing
            actor["_buff_fields"] = active_fields

    def next_boundary(self, time):
        boundaries = list(self.linger_until.values())
        for field in self.fields.values():
            boundaries.extend(
                (
                    field["start_seconds"],
                    field["start_seconds"] + field["duration_seconds"],
                )
            )
        future = [value for value in boundaries if value > time + EPSILON]
        return min(future) if future else None

    def first_crossing_delay(
        self, actor, route, time, horizon, effective_speed, forced_motion=False
    ):
        """Split motion using the exact same speed as the caller's next movement.

        Contact hints disambiguate an exit at the inclusive circle boundary.
        A boundary departure uses at most two numerical epsilon seconds, so
        starting exactly on the edge cannot cause zero-time solver oscillation.
        """
        speed = number(effective_speed, "effective movement speed", 0)
        if speed <= EPSILON or (
            not forced_motion and actor["frozen_until"] > time + EPSILON
        ):
            return None
        earliest = None
        for field_id, field in sorted(self.fields.items()):
            if not self._live(field, time) or not self._eligible(field, actor, time):
                continue
            key = field_id, actor["id"]
            self.crossing_hints.pop(key, None)
            previous = center(actor)
            traveled = 0.0
            area = field["area"]
            current_inside = self.inside.get(key, self._geometry_inside(field, actor))
            found = False
            for point_index, point in enumerate(route):
                length = hypot(point[0] - previous[0], point[1] - previous[1])
                for contact, inside_after in _circle_events(
                    previous, point, (area["x"], area["y"]), area["radius"]
                ):
                    if abs(contact - length) <= EPSILON:
                        for following in route[point_index + 1 :]:
                            next_dx = following[0] - point[0]
                            next_dy = following[1] - point[1]
                            if hypot(next_dx, next_dy) <= EPSILON:
                                continue
                            inward_projection = (point[0] - area["x"]) * next_dx + (
                                point[1] - area["y"]
                            ) * next_dy
                            inside_after = inward_projection < -EPSILON
                            break
                    if inside_after == current_inside:
                        continue
                    distance = traveled + contact
                    if distance <= speed * EPSILON:
                        contact = max(contact, speed * EPSILON * 2)
                        distance = traveled + contact
                    delay = distance / speed
                    if (
                        delay <= EPSILON
                        or delay > horizon + EPSILON
                        or contact > length + EPSILON
                    ):
                        continue
                    fraction = min(contact / length, 1)
                    position = tuple(
                        previous[index] + (point[index] - previous[index]) * fraction
                        for index in (0, 1)
                    )
                    self.crossing_hints[key] = {
                        "time_seconds": time + delay,
                        "position": position,
                        "inside_after": inside_after,
                    }
                    earliest = min(earliest, delay) if earliest is not None else delay
                    found = True
                    break
                if found:
                    break
                traveled += length
                if traveled > speed * horizon:
                    break
                previous = point
        return earliest

    @staticmethod
    def frame(actor):
        if actor["kind"] != "unit":
            return {}
        return {
            "buff_movement_bonus": movement_bonus(actor),
            "buff_damage_multiplier": damage_multiplier(actor),
            "buff_healing_multiplier": healing_multiplier(actor),
            "buff_fields": list(actor.get("_buff_fields", [])),
        }

    def result(self):
        return {
            "fields": deepcopy(self.fields),
            "started": sorted(self.started),
            "expired": sorted(self.expired),
            "lingering_exposures": [
                {"field_id": key[0], "target": key[1], "expires_at": expiry}
                for key, expiry in sorted(self.linger_until.items())
            ],
        }
