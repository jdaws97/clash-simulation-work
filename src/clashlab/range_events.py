"""Exact weapon-range contacts along declared piecewise linear movement.

This is a numerical boundary helper for the existing point-to-footprint range
convention. It does not select targets or establish the game's range convention.
Both paths are finite: after their final waypoint, their actors remain still.
"""

from math import hypot, sqrt


EPSILON = 1e-10


def _center(actor):
    return actor["x"] + actor["width"] / 2, actor["y"] + actor["height"] / 2


def _segments(actor, route, speed, horizon):
    position = _center(actor)
    time = 0.0
    segments = []
    if speed > EPSILON:
        for point in route:
            dx, dy = point[0] - position[0], point[1] - position[1]
            distance = hypot(dx, dy)
            if distance <= EPSILON:
                position = tuple(point)
                continue
            duration = min(distance / speed, horizon - time)
            velocity = (dx / distance * speed, dy / distance * speed)
            segments.append((time, time + duration, position, velocity))
            position = (
                position[0] + velocity[0] * duration,
                position[1] + velocity[1] * duration,
            )
            time += duration
            if time >= horizon - EPSILON:
                return segments
    if time < horizon:
        segments.append((time, horizon, position, (0.0, 0.0)))
    return segments


def _position(segment, time):
    start, _, position, velocity = segment
    return (
        position[0] + velocity[0] * (time - start),
        position[1] + velocity[1] * (time - start),
    )


def _distance(position, half_width, half_height):
    return hypot(
        max(abs(position[0]) - half_width, 0),
        max(abs(position[1]) - half_height, 0),
    )


def _contacts(position, velocity, half_width, half_height, radius, duration):
    """Intersect a line with the sides and corner arcs of a rounded rectangle."""
    candidates = []
    for axis, side, extent in (
        (0, half_width + radius, half_height),
        (1, half_height + radius, half_width),
    ):
        if abs(velocity[axis]) <= EPSILON:
            continue
        other = 1 - axis
        for sign in (-1, 1):
            time = (sign * side - position[axis]) / velocity[axis]
            if -EPSILON <= time <= duration + EPSILON:
                coordinate = position[other] + velocity[other] * time
                if abs(coordinate) <= extent + EPSILON:
                    candidates.append(max(0.0, min(duration, time)))
    speed_squared = velocity[0] ** 2 + velocity[1] ** 2
    if speed_squared <= EPSILON**2 or radius <= EPSILON:
        return candidates
    for x_sign in (-1, 1):
        for y_sign in (-1, 1):
            corner = (x_sign * half_width, y_sign * half_height)
            delta = (position[0] - corner[0], position[1] - corner[1])
            linear = 2 * (delta[0] * velocity[0] + delta[1] * velocity[1])
            constant = delta[0] ** 2 + delta[1] ** 2 - radius**2
            discriminant = linear**2 - 4 * speed_squared * constant
            if discriminant < -EPSILON:
                continue
            root = sqrt(max(0.0, discriminant))
            for numerator in (-linear - root, -linear + root):
                time = numerator / (2 * speed_squared)
                if not -EPSILON <= time <= duration + EPSILON:
                    continue
                point = (
                    position[0] + velocity[0] * time,
                    position[1] + velocity[1] * time,
                )
                if (
                    x_sign * (point[0] - corner[0]) >= -EPSILON
                    and y_sign * (point[1] - corner[1]) >= -EPSILON
                ):
                    candidates.append(max(0.0, min(duration, time)))
    return candidates


def first_weapon_range_entry_delay(
    source,
    target,
    source_route,
    target_route,
    source_speed,
    target_speed,
    horizon,
    *,
    minimum_range=0,
):
    """Return first positive entry into the source's legal weapon-range band.

    Eligibility, readiness, Freeze and forced-movement policy belong to the
    caller. A target already in range does not create a zero-time event. Tangent
    contacts count because the existing kernel permits inclusive range contact.
    This helper must not be used to decide whether a moving actor should chase.
    """
    if horizon <= EPSILON:
        return None
    maximum_range = source["range"]
    half_width, half_height = target["width"] / 2, target["height"] / 2

    def eligible(position):
        distance = _distance(position, half_width, half_height)
        return minimum_range - EPSILON <= distance <= maximum_range + EPSILON

    source_segments = _segments(source, source_route, source_speed, horizon)
    target_segments = _segments(target, target_route, target_speed, horizon)
    source_index = target_index = 0
    was_eligible = None
    while source_index < len(source_segments) and target_index < len(target_segments):
        source_segment = source_segments[source_index]
        target_segment = target_segments[target_index]
        start = max(source_segment[0], target_segment[0])
        end = min(source_segment[1], target_segment[1])
        source_position = _position(source_segment, start)
        target_position = _position(target_segment, start)
        position = (
            source_position[0] - target_position[0],
            source_position[1] - target_position[1],
        )
        velocity = (
            source_segment[3][0] - target_segment[3][0],
            source_segment[3][1] - target_segment[3][1],
        )
        if was_eligible is None:
            was_eligible = eligible(position)
        contacts = _contacts(
            position, velocity, half_width, half_height, maximum_range, end - start
        )
        if minimum_range > EPSILON:
            contacts.extend(
                _contacts(
                    position,
                    velocity,
                    half_width,
                    half_height,
                    minimum_range,
                    end - start,
                )
            )
        checkpoints = sorted(set([0.0, end - start, *contacts]))
        for index, offset in enumerate(checkpoints):
            point = (
                position[0] + velocity[0] * offset,
                position[1] + velocity[1] * offset,
            )
            at_contact = eligible(point)
            if start + offset > EPSILON and at_contact and not was_eligible:
                return start + offset
            if index + 1 < len(checkpoints):
                midpoint = (offset + checkpoints[index + 1]) / 2
                was_eligible = eligible(
                    (
                        position[0] + velocity[0] * midpoint,
                        position[1] + velocity[1] * midpoint,
                    )
                )
        if source_segment[1] <= end + EPSILON:
            source_index += 1
        if target_segment[1] <= end + EPSILON:
            target_index += 1
    return None
