"""Explicit directional splash geometry and distance falloff hypotheses.

The launch position fixes the firing direction even if the defense later dies.
Angles, band boundaries, layer filtering and projectile destinations still need
client or replay validation before these patterns predict Clash battles.
"""

from math import cos, hypot, radians

from .common import InputError, identifier, number, require
from .spatial import EPSILON, center, target_distance


LAYER_POLICIES = {"primary_target_layer_only", "all_declared_target_layers"}


def validate_directional_splash(geometry):
    if set(geometry) != {"source", "axis", "half_angle_degrees", "distance_bands"}:
        raise InputError("Directional splash needs every explicit geometry field")
    identifier(require(geometry, "source"), "directional splash evidence")
    if require(geometry, "axis") != "launch_source_to_impact_point":
        raise InputError("Directional splash requires the captured launch position")
    number(require(geometry, "half_angle_degrees"), "splash half angle", EPSILON, 90)
    bands = require(geometry, "distance_bands")
    if not isinstance(bands, list) or not bands:
        raise InputError("Directional splash needs explicit distance bands")
    previous_end = 0
    for band in bands:
        if set(band) != {"start", "end", "start_multiplier", "end_multiplier"}:
            raise InputError("Splash bands need distances and endpoint multipliers")
        start = number(band["start"], "band start", 0)
        end = number(band["end"], "band end", start + EPSILON)
        if abs(start - previous_end) > EPSILON:
            raise InputError("Splash bands must be contiguous and start at zero")
        number(band["start_multiplier"], "band initial multiplier", 0)
        number(band["end_multiplier"], "band final multiplier", 0)
        previous_end = end


def directional_multiplier(packet, point, actor):
    """Return a live center-based cone multiplier, or no splash membership."""
    geometry = packet["pattern"]["directional_splash"]
    origin = packet["launch_position"]
    axis_x, axis_y = point[0] - origin[0], point[1] - origin[1]
    axis_length = hypot(axis_x, axis_y)
    if axis_length <= EPSILON:
        raise InputError("Directional splash has no firing axis at zero distance")
    position = center(actor)
    dx, dy = position[0] - point[0], position[1] - point[1]
    distance = hypot(dx, dy)
    if distance > EPSILON:
        alignment = (dx * axis_x + dy * axis_y) / (distance * axis_length)
        if alignment + EPSILON < cos(radians(geometry["half_angle_degrees"])):
            return None
    for band in geometry["distance_bands"]:
        if distance <= band["end"] + EPSILON:
            fraction = min(
                1, max(0, (distance - band["start"]) / (band["end"] - band["start"]))
            )
            return band["start_multiplier"] + fraction * (
                band["end_multiplier"] - band["start_multiplier"]
            )
    return None


def directional_impacts(packet, point, actors, time, eligible):
    impacts = []
    for actor in actors.values():
        if not eligible(packet, actor, time):
            continue
        if (
            actor["id"] == packet["target"]
            and target_distance(point, actor)
            <= packet["pattern"]["projectile"]["hit_radius"] + EPSILON
        ):
            impacts.append((actor, 1))
            continue
        multiplier = directional_multiplier(packet, point, actor)
        if multiplier is not None:
            impacts.append((actor, multiplier))
    return impacts
