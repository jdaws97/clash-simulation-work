"""Finite equipment release queues and passive meteor/chain weapons.

Pinned rows supply damage, target budgets and status durations. Projectile
clocks, cone geometry and launch semantics are explicit experimental inputs.
Target selection delegates to the supplied base selector after ability filters.
"""

from collections import defaultdict
from copy import deepcopy
from heapq import heappop, heappush
from math import cos, hypot, radians

from .common import InputError, identifier, integer, number
from .damage_receipts import record_damage
from .hero_extensions import source_quantity
from .rates import pause_attack_work, skip_elapsed_pulses
from .spatial import EPSILON, _active, _eligible, center, target_distance


OWNERS = {
    "seeking-shield": "royal-champion",
    "frost-flake": "royal-champion",
    "meteor-staff": "minion-prince",
    "electro-fangs": "dragon-duke",
    "stun-blaster": "dragon-duke",
    "flame-blower": "dragon-duke",
}
POLICIES = {
    "experimental_policy": "equipment_release_queues_v1_uncalibrated",
    "selection": "filtered_base_selector_air_proxy_nearest_footprint",
    "damage_scaling": "pinned_flat_equipment_times_hero_profile_at_release",
    "source_loss": "released_packets_persist_death_recall_or_freeze",
    "status_protection": "damage_immunity_does_not_block_status",
    "passive_freeze": "suppress_new_releases_skip_missed_absolute_grid",
    "chain_primary": "extra_damage_on_primary_then_decay_to_distinct_links",
    "stun_representation": "shared_freeze_attack_and_movement_pause_experimental",
}
NUMERIC = {
    "release_delay_seconds",
    "projectile_speed_tiles_per_second",
    "initial_range_tiles",
    "bounce_range_tiles",
    "first_passive_delay_seconds",
    "cone_angle_degrees",
    "fallback_unit_vector",
}
FIELDS = {
    "entity",
    "level",
    "ability_type",
    "source",
    "parameters",
    "kind",
    "damage",
    "target_count",
    "chain_decay",
    "chain_range",
    "radius",
    "freeze_duration",
    "passive_interval",
}


def validate_equipment(model):
    if (
        not isinstance(model, dict)
        or set(model) != FIELDS
        or model["entity"] not in OWNERS
    ):
        raise InputError("Equipment weapon requires a complete supported model")
    identifier(model["source"], "equipment weapon statistic provenance")
    integer(model["level"], "equipment weapon level", 1)
    passive = model["entity"] in {"meteor-staff", "electro-fangs"}
    if model["ability_type"] != ("Passive" if passive else "Active"):
        raise InputError("Equipment weapon activation mismatch")
    parameters = model["parameters"]
    if not isinstance(parameters, dict) or set(parameters) != {
        "source",
        *POLICIES,
        *NUMERIC,
    }:
        raise InputError(
            "Equipment weapon needs every explicit experimental geometry/clock input"
        )
    identifier(parameters["source"], "equipment weapon behavior evidence")
    if any(parameters[key] != value for key, value in POLICIES.items()):
        raise InputError("Unsupported equipment release policy")
    for field in NUMERIC - {"fallback_unit_vector"}:
        number(
            parameters[field],
            field,
            EPSILON if field == "projectile_speed_tiles_per_second" else 0,
        )
    number(parameters["cone_angle_degrees"], "equipment cone angle", EPSILON, 360)
    vector = parameters["fallback_unit_vector"]
    if (
        not isinstance(vector, list)
        or len(vector) != 2
        or abs(hypot(*(number(value, "fallback direction") for value in vector)) - 1)
        > EPSILON
    ):
        raise InputError("Equipment fallback direction requires a unit vector")
    integer(model["target_count"], "equipment target budget", 1)
    for field in (
        "damage",
        "chain_range",
        "radius",
        "freeze_duration",
        "passive_interval",
    ):
        number(model[field], field, 0)
    number(model["chain_decay"], "equipment chain decay", 0, 1)
    if model["entity"] == "meteor-staff":
        number(model["passive_interval"], "meteor interval", EPSILON)


def compile_equipment(instance, hero, catalog):
    if set(instance) != {"entity", "level", "parameters"}:
        raise InputError("Equipment weapon instance is incomplete")
    entity_id = instance["entity"]
    if entity_id not in OWNERS or OWNERS[entity_id] != hero["entity"]:
        raise InputError("Equipment weapon owner mismatch")
    level = integer(instance["level"], "equipment weapon level", 1)
    if not catalog.available(entity_id, level, hero["town_hall"]):
        raise InputError("Equipment weapon unavailable at selected Town Hall")
    entity = catalog.entity(entity_id)
    row = catalog.level(entity_id, level)
    stats = row["stats"]
    parameters = deepcopy(instance["parameters"])
    model = {
        "entity": entity_id,
        "level": level,
        "ability_type": entity["abilityType"],
        "source": catalog.records[entity_id]["source"],
        "parameters": parameters,
        "kind": "locked",
        "damage": 0,
        "target_count": 1,
        "chain_decay": 1,
        "chain_range": 0,
        "radius": 0,
        "freeze_duration": 0,
        "passive_interval": 0,
    }
    if entity_id == "seeking-shield":
        model.update(
            damage=stats["projectileDamage"],
            target_count=entity["ability"]["numberOfTargets"],
            chain_range=parameters["bounce_range_tiles"],
        )
    elif entity_id == "frost-flake":
        model.update(
            damage=stats["projectileDamage"],
            target_count=stats["numberOfTargets"],
            freeze_duration=source_quantity(stats["slowDownDuration"], "s"),
            kind="distinct_volley",
        )
    elif entity_id == "meteor-staff":
        model.update(
            damage=stats["damagePerHit"],
            passive_interval=source_quantity(stats["cooldownTime"], "s"),
        )
    elif entity_id == "electro-fangs":
        if entity["ability"]["chainDamageDecay"] != "-20%":
            raise InputError("Electro Fangs decay requires explicit source mapping")
        model.update(
            damage=stats["damagePerHit"],
            target_count=stats["numberOfTargets"],
            chain_decay=0.8,
            chain_range=source_quantity(entity["ability"]["chainDistance"], "tiles"),
        )
    else:
        model.update(
            kind="cone" if entity_id == "flame-blower" else "radial",
            radius=source_quantity(entity["ability"]["damageRadius"], "tiles"),
            damage=(
                stats["abilityDamage"]
                if entity_id == "flame-blower"
                else stats["abilityTotalDamage"]
            ),
            freeze_duration=(
                source_quantity(stats["stunDuration"], "s")
                if entity_id == "stun-blaster"
                else 0
            ),
        )
    validate_equipment(model)
    return model, row


class EquipmentWeaponCombat:
    def __init__(self, actors, base_selector, width, height):
        self.actors = actors
        self.base_selector = base_selector
        self.width, self.height = width, height
        self.items = {}
        self.used = set()
        self.packets = []
        self.sequence = 0
        self.meteor_next = {}
        self.log = []
        for key, actor in actors.items():
            for item in actor.get("hero_model", {}).get("equipment", []):
                if item["entity"] not in OWNERS:
                    continue
                validate_equipment(item)
                if actor["hero_model"]["entity"] != OWNERS[item["entity"]]:
                    raise InputError("Equipment release runtime owner mismatch")
                self.items[(key, item["entity"])] = deepcopy(item)
                if item["entity"] == "meteor-staff":
                    self.meteor_next[key] = None

    def _select(self, proxy, point, actors, time, reach, visited, kinds=("defense",)):
        source = deepcopy(proxy)
        source.update(
            x=point[0],
            y=point[1],
            width=0,
            height=0,
            movement="air",
            range=reach,
            target=None,
            target_priorities=list(kinds),
            target_priority_tiers=[list(kinds)],
            _target_ranks={kind: 0 for kind in kinds},
        )
        source.pop("hero_model", None)
        source.pop("wall_behavior", None)
        source.pop("_remaining_path", None)
        source.pop("_path_signature", None)
        choices = {
            key: actor
            for key, actor in actors.items()
            if key not in visited
            and actor["kind"] in kinds
            and _eligible(source, actor, time)
            and not actor.get("_tesla_hidden", False)
            and target_distance(point, actor) <= reach
        }
        target, _ = self.base_selector(
            source, choices, time, set(), self.width, self.height
        )
        return target

    def _enqueue(self, packet, release_time, delay):
        arrival = release_time + delay
        if delay > 0 and arrival <= release_time:
            raise InputError("Equipment arrival delay is not representable")
        self.sequence += 1
        heappush(self.packets, (arrival, self.sequence, packet))

    def _queue_locked(self, packet, target, time):
        parameters = packet["model"]["parameters"]
        point = center(target)
        delay = (
            parameters["release_delay_seconds"]
            + hypot(point[0] - packet["point"][0], point[1] - packet["point"][1])
            / parameters["projectile_speed_tiles_per_second"]
        )
        packet = deepcopy(packet)
        packet.update(
            target=target["id"],
            captured_point=point,
            remaining=packet["remaining"] - 1,
            visited=[*packet["visited"], target["id"]],
        )
        self._enqueue(packet, time, delay)

    def _release(self, hero_id, model, actors, time, trace, primary=None):
        hero = actors[hero_id]
        proxy = deepcopy(hero)
        proxy.update(hp=1, spawn_seconds=0, _recalled=False, damage=1)
        packet = {
            "source": hero_id,
            "source_team": hero["team"],
            "source_actor": proxy,
            "model": deepcopy(model),
            "damage": model["damage"] * hero["hero_model"]["damage_multiplier"],
            "point": center(hero),
            "remaining": model["target_count"],
            "visited": [],
        }
        if model["kind"] in {"radial", "cone"}:
            target = actors.get(hero.get("target"))
            vector = model["parameters"]["fallback_unit_vector"]
            if target is not None and _active(target, time):
                origin, destination = center(hero), center(target)
                dx, dy = destination[0] - origin[0], destination[1] - origin[1]
                length = hypot(dx, dy)
                if length > 0:
                    vector = [dx / length, dy / length]
            packet["direction"] = vector
            self._enqueue(packet, time, model["parameters"]["release_delay_seconds"])
        elif primary is not None:
            self._queue_locked(packet, primary, time)
        elif model["kind"] == "distinct_volley":
            for _ in range(model["target_count"]):
                target = self._select(
                    proxy,
                    packet["point"],
                    actors,
                    time,
                    model["parameters"]["initial_range_tiles"],
                    packet["visited"],
                )
                if target is None:
                    break
                single = deepcopy(packet)
                single["remaining"] = 1
                self._queue_locked(single, target, time)
                packet["visited"].append(target["id"])
        else:
            target = self._select(
                proxy,
                packet["point"],
                actors,
                time,
                model["parameters"]["initial_range_tiles"],
                [],
            )
            if target is not None:
                self._queue_locked(packet, target, time)
        entry = {
            "time_seconds": time,
            "event": "equipment_weapon_release",
            "source": hero_id,
            "equipment": model["entity"],
            "experimental": True,
        }
        trace.append(entry)
        self.log.append(deepcopy(entry))

    def activate(self, hero_id, actors, time, trace):
        if hero_id in self.used or not _active(actors[hero_id], time):
            return
        self.used.add(hero_id)
        for key, model in self.items.items():
            if key[0] == hero_id and model["ability_type"] == "Active":
                self._release(hero_id, model, actors, time, trace)

    def prepare(self, actors, time, trace):
        for hero_id, clock in self.meteor_next.items():
            model = self.items[(hero_id, "meteor-staff")]
            actor = actors[hero_id]
            if clock is None:
                if not _active(actor, time):
                    continue
                clock = (
                    actor["spawn_seconds"]
                    + model["parameters"]["first_passive_delay_seconds"]
                )
            if actor.get("_recalled", False) or actor["frozen_until"] > time:
                self.meteor_next[hero_id] = skip_elapsed_pulses(
                    clock, model["passive_interval"], time
                )
            elif _active(actor, time) and clock <= time:
                self._release(hero_id, model, actors, time, trace)
                self.meteor_next[hero_id] = time + model["passive_interval"]
            else:
                self.meteor_next[hero_id] = clock

    def weapon_launched(self, hero_id, time, trace):
        model = self.items.get((hero_id, "electro-fangs"))
        hero = self.actors.get(hero_id)
        if model is not None and hero is not None and _active(hero, time):
            primary = self.actors.get(hero.get("target"))
            if primary is not None and _active(primary, time):
                self._release(hero_id, model, self.actors, time, trace, primary)

    def resolve(self, actors, time, trace, receipts):
        self.damage_receipts = receipts
        damage = defaultdict(float)
        while self.packets and self.packets[0][0] <= time:
            arrival, sequence, packet = heappop(self.packets)
            model = packet["model"]
            if model["kind"] in {"radial", "cone"}:
                recipients = []
                for actor in actors.values():
                    if (
                        not _active(actor, time)
                        or actor["team"] == packet["source_team"]
                        or actor.get("_tesla_hidden", False)
                    ):
                        continue
                    if (
                        actor["kind"] not in {"defense", "building", "unit", "wall"}
                        or target_distance(packet["point"], actor) > model["radius"]
                    ):
                        continue
                    if model["kind"] == "cone":
                        point = center(actor)
                        dx, dy = (
                            point[0] - packet["point"][0],
                            point[1] - packet["point"][1],
                        )
                        distance = hypot(dx, dy)
                        if distance and (
                            dx * packet["direction"][0] + dy * packet["direction"][1]
                        ) / distance < cos(
                            radians(model["parameters"]["cone_angle_degrees"] / 2)
                        ):
                            continue
                    recipients.append(actor)
            else:
                target = actors.get(packet["target"])
                recipients = (
                    [target]
                    if target is not None
                    and _active(target, time)
                    and not target.get("_tesla_hidden", False)
                    else []
                )
            for target in recipients:
                damage[target["id"]] += record_damage(
                    self,
                    target,
                    packet["damage"],
                    time,
                    source_id=packet["source"] + ":" + model["entity"],
                    source_actor_id=packet["source"],
                    source_team=packet["source_team"],
                    origin="ability",
                )
                if model["freeze_duration"]:
                    until = time + model["freeze_duration"]
                    pause_attack_work(target, time, until)
                    target["frozen_until"] = max(target["frozen_until"], until)
            if model["kind"] == "locked" and packet["remaining"] > 0:
                point = (
                    center(recipients[0]) if recipients else packet["captured_point"]
                )
                kinds = (
                    ("defense", "building")
                    if model["entity"] == "electro-fangs"
                    else ("defense",)
                )
                target = self._select(
                    packet["source_actor"],
                    point,
                    actors,
                    time,
                    model["chain_range"],
                    packet["visited"],
                    kinds,
                )
                if target is not None:
                    packet["point"] = point
                    packet["damage"] *= model["chain_decay"]
                    self._queue_locked(packet, target, time)
            trace.append(
                {
                    "time_seconds": time,
                    "event": "equipment_weapon_impact",
                    "equipment": model["entity"],
                    "source": packet["source"],
                    "targets": [target["id"] for target in recipients],
                    "sequence": sequence,
                }
            )
        return damage, {}

    def next_boundary(self, time):
        values = [arrival for arrival, _, _ in self.packets if arrival > time]
        values.extend(
            clock
            for key, clock in self.meteor_next.items()
            if clock is not None and clock > time and _active(self.actors[key], time)
        )
        return min(values) if values else None

    def continuation_reasons(self, time):
        from .battle_termination import continuation_fact

        return [
            continuation_fact(
                "pending_damage",
                f"equipment:{sequence}",
                [packet["source"]],
                not_before_seconds=arrival,
            )
            for arrival, sequence, packet in self.packets
            if packet["source_team"] == "attack" and packet["damage"] > 0
        ]

    def result(self):
        return {
            "releases": self.log,
            "pending_packets": len(self.packets),
            "experimental": True,
            "calibrated": False,
        }
