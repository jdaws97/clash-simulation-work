"""Public queueing primitive for prevalidated finite displacement trajectories."""

from math import hypot

from .common import InputError, identifier, number
from .rates import pause_attack_work
from .spatial import EPSILON, center


def enqueue_linear_displacement(
    displacement,
    actor,
    time,
    destination,
    speed,
    recovery_seconds,
    source_id,
    trace,
    requested_distance=None,
):
    """Share trajectory storage and attack-work pauses after caller-owned clipping.

    The mechanic calling this function owns recipient eligibility, protection,
    obstacle clipping and overlap priority. This primitive validates the bounded
    endpoint and finite timing, replaces existing motion, and preserves the union
    of unfinished attack work, Freeze, and previous displacement pauses.
    """
    number(time, "displacement start", 0)
    number(speed, "displacement speed", EPSILON)
    number(recovery_seconds, "displacement recovery", 0)
    identifier(source_id, "displacement source")
    if not isinstance(destination, (list, tuple)) or len(destination) != 2:
        raise InputError("Displacement endpoint needs two coordinates")
    destination = tuple(
        number(value, "displacement endpoint coordinate") for value in destination
    )
    if actor["kind"] != "unit" or actor["movement"] == "stationary":
        raise InputError("Only moving units may receive finite displacement")
    for position, extent, board_extent in (
        (destination[0], actor["width"], displacement.width),
        (destination[1], actor["height"], displacement.height),
    ):
        if position - extent / 2 < 0 or position + extent / 2 >= board_extent:
            raise InputError("Displacement endpoint is outside the board")
    origin = center(actor)
    distance = hypot(destination[0] - origin[0], destination[1] - origin[1])
    if requested_distance is None:
        requested_distance = distance
    number(requested_distance, "requested displacement distance", 0)
    if distance > requested_distance + EPSILON:
        raise InputError("Clipped displacement cannot exceed its requested distance")
    arrival = time + distance / speed
    pause_until = arrival + recovery_seconds
    pause_attack_work(actor, time, pause_until)
    actor["_displacement_pause_until"] = max(
        actor.get("_displacement_pause_until", 0), pause_until
    )
    previous = displacement.motions.pop(actor["id"], None)
    if distance > EPSILON:
        displacement.motions[actor["id"]] = {
            "source": source_id,
            "origin": origin,
            "destination": destination,
            "start_seconds": time,
            "arrival_seconds": arrival,
            "speed_tiles_per_second": speed,
        }
    actor.pop("_remaining_path", None)
    actor.pop("_path_signature", None)
    actor["target"] = None
    if "healing_target" in actor:
        actor["healing_target"] = None
    trace.append(
        {
            "event": "displacement_start",
            "time_seconds": time,
            "source": source_id,
            "target": actor["id"],
            "from_position": origin,
            "to_position": destination,
            "requested_distance": requested_distance,
            "actual_distance": distance,
            "arrival_seconds": arrival,
            "pause_until": actor["_displacement_pause_until"],
            "replaced_motion": previous is not None,
        }
    )
