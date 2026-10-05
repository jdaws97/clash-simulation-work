"""Fixed-line piercing and finite boulder bounces with live impact membership.

Direction, width, bounce spacing and travel clocks are explicit hypotheses. A
released projectile survives source loss; the ordinary weapon launch is consumed
once. Damage is returned to the shared simultaneous-health settlement.
"""

from collections import defaultdict
from copy import deepcopy
from heapq import heappop, heappush
from math import hypot, nextafter, inf, isfinite

from .battle_termination import continuation_fact
from .buffs import damage_multiplier
from .common import InputError, identifier, number, require
from .damage_receipts import record_damage
from .spatial import EPSILON, _active, center, target_distance
from .spell_visibility import untargetable_until


LINE_ENTITIES = frozenset({"super-archer", "bowler", "super-bowler"})


def compile_line_weapon(actor, instance, entity):
    entity_id = entity["id"]
    if entity_id not in LINE_ENTITIES or actor.get("team") != "attack":
        raise InputError("Line weapon requires a registered attacking troop")
    model = deepcopy(require(instance, "line_weapon_parameters"))
    if set(model) != {
        "source",
        "status",
        "kind",
        "distance_tiles",
        "radius_tiles",
        "speed_tiles_per_second",
        "release_delay_seconds",
        "bounce_offsets_tiles",
        "damage_multipliers",
        "membership",
        "repeats",
        "source_persistence",
    }:
        raise InputError("Line weapons require complete geometry and timing")
    identifier(model["source"], "line weapon evidence")
    if model["status"] != "explicit_uncalibrated_hypothesis":
        raise InputError("Line geometry has not been calibrated")
    expected = "piercing" if entity_id == "super-archer" else "bounce"
    if (
        model["kind"] != expected
        or model["membership"] != "live_at_each_impact"
        or model["repeats"] != "one_hit_per_actor_per_launch"
        or model["source_persistence"] != "released_projectile_survives"
    ):
        raise InputError("Unsupported line projectile lifecycle")
    for field in ("distance_tiles", "speed_tiles_per_second"):
        number(model[field], field, EPSILON)
    for field in ("radius_tiles", "release_delay_seconds"):
        number(model[field], field, 0)
    expected_count = {"super-archer": 1, "bowler": 2, "super-bowler": 3}[entity_id]
    if (
        len(model["damage_multipliers"]) != expected_count
        or len(model["bounce_offsets_tiles"]) != expected_count
    ):
        raise InputError("Projectile impact count disagrees with troop identity")
    previous = -1
    for offset in model["bounce_offsets_tiles"]:
        number(offset, "boulder impact offset", 0)
        if offset <= previous:
            raise InputError("Bounce offsets must increase")
        previous = offset
    if model["bounce_offsets_tiles"][0] != 0:
        raise InputError("First impact must be at the primary target")
    for value in model["damage_multipliers"]:
        number(value, "line weapon damage multiplier", 0)
    actor["troop_line_model"] = model
    return actor


def segment_contact(start, end, actor, radius):
    """Slab intersection against a footprint expanded by declared shot width."""
    lower, upper = 0.0, 1.0
    for origin, destination, minimum, maximum in (
        (start[0], end[0], actor["x"] - radius, actor["x"] + actor["width"] + radius),
        (start[1], end[1], actor["y"] - radius, actor["y"] + actor["height"] + radius),
    ):
        delta = destination - origin
        if abs(delta) <= EPSILON:
            if not minimum - EPSILON <= origin <= maximum + EPSILON:
                return None
        else:
            first, last = sorted(
                ((minimum - origin) / delta, (maximum - origin) / delta)
            )
            lower, upper = max(lower, first), min(upper, last)
            if lower > upper + EPSILON:
                return None
    return max(0.0, lower)


class TroopLineCombat:
    def __init__(self, actors):
        self.actors = actors
        self.models = {
            key: deepcopy(actor["troop_line_model"])
            for key, actor in actors.items()
            if "troop_line_model" in actor
        }
        self.pending = []
        self.serial = 0
        self.resolved = []
        self.damage_eligible = None

    def launch(self, actor, target, time, trace, flat_damage=None):
        model = self.models[actor["id"]]
        origin, point = center(actor), center(target)
        distance = hypot(point[0] - origin[0], point[1] - origin[1])
        if distance <= EPSILON:
            raise InputError("A line weapon requires a nonzero launch direction")
        direction = (
            (point[0] - origin[0]) / distance,
            (point[1] - origin[1]) / distance,
        )
        self.serial += 1
        launch_id = self.serial
        visited = set()
        for index, offset in enumerate(model["bounce_offsets_tiles"]):
            travel = distance + offset
            position = (
                point[0] + offset * direction[0],
                point[1] + offset * direction[1],
            )
            if model["kind"] == "piercing":
                travel = model["distance_tiles"]
                position = (
                    origin[0] + travel * direction[0],
                    origin[1] + travel * direction[1],
                )
            due = (
                time
                + model["release_delay_seconds"]
                + travel / model["speed_tiles_per_second"]
            )
            if not isfinite(due):
                raise InputError("Line projectile impact clock must remain finite")
            if due <= time:
                due = nextafter(time, inf)
            packet = {
                "pattern": deepcopy(actor["attack_model"]),
                "source_team": actor["team"],
                "primary_layer": target["layer"],
                "source": actor["id"],
                "target": target["id"],
                "origin": origin,
                "position": position,
                "launch_id": launch_id,
                "visited": visited,
                "index": index,
                "damage": (actor["damage"] if flat_damage is None else flat_damage)
                * damage_multiplier(actor)
                * model["damage_multipliers"][index],
                "model": model,
                "team": actor["team"],
                "layers": list(actor["target_layers"]),
                "kinds": list(actor["target_priorities"]),
            }
            heappush(self.pending, (due, launch_id * 4 + index, packet))
        trace.append(
            {
                "time_seconds": time,
                "event": "troop_line_launch",
                "source": actor["id"],
                "target": target["id"],
                "launch_id": launch_id,
            }
        )

    def resolve(self, time, trace):
        damage = defaultdict(float)
        while self.pending and self.pending[0][0] <= time:
            _, _, packet = heappop(self.pending)
            model = packet["model"]
            recipients = []
            for key, actor in self.actors.items():
                if (
                    key in packet["visited"]
                    or actor["team"] == packet["team"]
                    or not _active(actor, time)
                    or (
                        self.damage_eligible is None
                        and (
                            actor["kind"] not in packet["kinds"]
                            or actor["layer"] not in packet["layers"]
                        )
                    )
                    or (
                        self.damage_eligible is not None
                        and not self.damage_eligible(packet, actor, time)
                    )
                    or untargetable_until(actor) > time + EPSILON
                ):
                    continue
                if model["kind"] == "piercing":
                    fraction = segment_contact(
                        packet["origin"],
                        packet["position"],
                        actor,
                        model["radius_tiles"],
                    )
                    if fraction is not None:
                        recipients.append((fraction, key, actor))
                elif (
                    target_distance(packet["position"], actor)
                    <= model["radius_tiles"] + EPSILON
                ):
                    recipients.append((0, key, actor))
            for _, key, actor in sorted(recipients, key=lambda item: item[:2]):
                packet["visited"].add(key)
                resolved = record_damage(
                    self,
                    actor,
                    packet["damage"],
                    time,
                    source_id=packet["source"],
                    source_actor_id=packet["source"],
                    source_team=packet["team"],
                    origin="weapon",
                )
                damage[key] += resolved
                event = {
                    "time_seconds": time,
                    "event": "troop_line_impact",
                    "source": packet["source"],
                    "target": key,
                    "impact_index": packet["index"],
                    "amount": resolved,
                }
                trace.append(event)
                self.resolved.append(deepcopy(event))
        return damage

    def next_boundary(self, time):
        return (
            self.pending[0][0] if self.pending and self.pending[0][0] > time else None
        )

    def continuation_reasons(self, time):
        return [
            continuation_fact(
                "pending_damage",
                "troop-line:" + str(serial),
                [packet["source"]],
                not_before_seconds=due,
            )
            for due, serial, packet in self.pending
        ]

    def result(self):
        return {
            "status": "EXPLICIT_UNCALIBRATED_LINE_WEAPONS",
            "pending_count": len(self.pending),
            "impacts": deepcopy(self.resolved),
        }
