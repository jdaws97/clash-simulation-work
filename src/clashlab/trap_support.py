"""Shared geometry for explicit nonblocking trap lifecycle runtimes."""

from math import hypot

from .spell_visibility import untargetable_until
from .common import InputError, integer, number, require
from .spatial import EPSILON, _active, center
from .traps import segment_circle_entry


def validate_trap_footprints(traps, actors, width, height):
    """Validate all supplied families together without adding blocking actors."""
    occupied = set()
    for actor in actors.values():
        if not actor["blocking"]:
            continue
        occupied.update(
            (x, y)
            for x in range(actor["x"], actor["x"] + actor["width"])
            for y in range(actor["y"], actor["y"] + actor["height"])
        )
    ids = set(actors)
    for trap in traps:
        trap_id = require(trap, "id")
        if trap_id in ids:
            raise InputError("Trap and actor identities must be unique")
        ids.add(trap_id)
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
            raise InputError("Trap footprints cannot overlap structures or other traps")
        occupied |= cells


def eligible_trap_unit(actor, team, layers, excluded_entities, time):
    return (
        _active(actor, time)
        and not actor.get("_spell_trap_trigger_exempt", False)
        and actor["kind"] == "unit"
        and actor["team"] != team
        and actor["layer"] in layers
        and untargetable_until(actor) <= time + EPSILON
        and actor.get("entity_adapter", {}).get("entity") not in excluded_entities
    )


def circle_entry_delay(actor, route, origin, radius, horizon, speed):
    """First positive entry along either ordinary or externally forced motion."""
    number(speed, "trap entry motion speed", 0)
    if speed <= EPSILON:
        return None
    previous = center(actor)
    traveled = 0.0
    for point in route:
        entry = segment_circle_entry(previous, point, origin, radius)
        if entry is not None:
            delay = (traveled + entry) / speed
            return delay if EPSILON < delay <= horizon + EPSILON else None
        traveled += hypot(point[0] - previous[0], point[1] - previous[1])
        if traveled > horizon * speed + EPSILON:
            break
        previous = point
    return None
