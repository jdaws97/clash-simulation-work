"""Conditional barrel carriers with conserved CC members and generated troops.

Quantities/cadence come from catalog named roles. Placement and flight are
declared hypotheses. No generated troop is charged to the army or attacking CC.
In-flight reserves persist when their carrier is manually released or destroyed.
"""

from collections import defaultdict
from copy import deepcopy

from .common import InputError, identifier, integer, number, require
from .reinforcements import ReinforcementCombat
from .siege_extensions import _GeneratedRelease
from .siege_machines import SiegeCombat, siege_time_after
from .spatial import EPSILON, _active, center, target_distance


BARREL_SIEGES = {"troop-launcher", "sky-wagon"}
CHILD_NAMES = {
    "barbarians": "barbarian",
    "archers": "archer",
    "giants": "giant",
    "wallBreakers": "wall-breaker",
    "minions": "minion",
    "balloons": "balloon",
    "babyDragons": "baby-dragon",
}


def barrel_generated_requirements(carrier_id, entity_id, row, catalog):
    """Exact source-level reserve manifests; unknown child rows fail explicitly."""
    if entity_id not in BARREL_SIEGES:
        raise InputError("Unsupported barrel carrier")
    barrel_count = integer(require(row, "barrelCount"), "source barrel count", 1)
    composition = require(row, "troopsSpawnedPerBarrel")
    expected = (
        {"barbarians", "archers", "giants", "wallBreakers"}
        if entity_id == "troop-launcher"
        else {"minions", "balloons", "babyDragons"}
    )
    if not isinstance(composition, dict) or set(composition) != expected:
        raise InputError("Unknown source barrel troop composition")
    rows = []
    for barrel in range(barrel_count):
        for name, count in composition.items():
            count = integer(count, "source generated count", 0)
            level = integer(
                (
                    require(row, "troopLevel")
                    if entity_id == "troop-launcher"
                    else require(require(row, "troopLevels"), name)
                ),
                "source generated level",
                1,
            )
            child = CHILD_NAMES[name]
            catalog.level(child, level)
            for ordinal in range(count):
                rows.append(
                    {
                        "actor_id": f"{carrier_id}-barrel-{barrel + 1}-{child}-{ordinal + 1}",
                        "entity": child,
                        "level": level,
                        "barrel_index": barrel,
                    }
                )
    return rows


def _validate_policy(policy):
    fields = {
        "source",
        "experimental",
        "targeting",
        "minimum_range_tiles",
        "maximum_range_tiles",
        "first_launch_delay_seconds",
        "flight_seconds",
        "impact_radius_tiles",
        "maximum_lifetime_seconds",
        "generated_release",
        "cc_per_barrel",
        "source_loss",
        "exhaustion",
        "no_target",
        "death_boundary_order",
    }
    if not isinstance(policy, dict) or set(policy) != fields:
        raise InputError("Barrel lifecycle requires all explicit experimental policies")
    identifier(policy["source"], "barrel hypothesis evidence")
    if policy["experimental"] is not True:
        raise InputError("Barrel geometry and timing are experimental")
    for key, expected in {
        "targeting": "nearest_active_ally_for_launcher_nearest_defense_for_wagon",
        "cc_per_barrel": "one_ordered_member",
        "source_loss": "launched_barrels_continue_cancel_unlaunched_generated",
        "exhaustion": "terminate_release_remaining_cc",
        "no_target": "wait_without_spending_barrel",
        "death_boundary_order": "termination_before_new_launch",
    }.items():
        if policy[key] != expected:
            raise InputError(f"Unsupported barrel {key}")
    maximum = number(policy["maximum_range_tiles"], "barrel maximum range", EPSILON)
    number(policy["minimum_range_tiles"], "barrel minimum range", 0, maximum)
    for key in ("first_launch_delay_seconds", "flight_seconds", "impact_radius_tiles"):
        number(policy[key], key, 0)
    if policy["maximum_lifetime_seconds"] is not None:
        number(policy["maximum_lifetime_seconds"], "barrel explicit lifetime", EPSILON)


def compile_barrel_siege(actor, instance, entity, row, modifiers, catalog, units):
    entity_id = entity["id"]
    if entity_id not in BARREL_SIEGES or entity["category"] != "siege-machine":
        raise InputError("Unsupported barrel siege")
    if (
        actor["team"] != "attack"
        or actor["counts_for_destruction"]
        or instance["mode"] != "normal"
        or instance["statistics_mode"] != "normal"
        or instance["attack_parameters"] != {}
        or any(
            key in instance
            for key in (
                "payload_member_parameters",
                "garrison_member_parameters",
                "barracks_member_parameters",
                "barrel_member_parameters",
                "hero_parameters",
                "wall_parameters",
            )
        )
    ):
        raise InputError("Barrel carrier requires an independent attacking siege role")
    parameters = deepcopy(require(instance, "siege_parameters"))
    if set(parameters) != {
        "source",
        "origin",
        "donor_town_hall",
        "payload_group_id",
        "behavior",
    }:
        raise InputError(
            "Barrel siege requires source, origin, donor, payload and behavior"
        )
    identifier(parameters["source"], "barrel source")
    identifier(parameters["payload_group_id"], "barrel payload group")
    if parameters["origin"] == "own":
        if parameters["donor_town_hall"] is not None:
            raise InputError("Owned barrel carrier cannot hide donor technology")
        technology = instance["town_hall"]
    elif parameters["origin"] == "donated":
        technology = integer(parameters["donor_town_hall"], "barrel donor Town Hall", 1)
    else:
        raise InputError("Unknown barrel origin")
    if not catalog.available(entity_id, instance["level"], technology):
        raise InputError("Barrel carrier unavailable at its source Town Hall")
    policy = parameters["behavior"]
    _validate_policy(policy)
    members = barrel_generated_requirements(actor["id"], entity_id, row, catalog)
    stationary = entity_id == "troop-launcher"
    lifetime = (
        number(row["lifetime"], "source launcher lifetime", EPSILON)
        if stationary
        else policy["maximum_lifetime_seconds"]
    )
    if stationary and policy["maximum_lifetime_seconds"] != lifetime:
        raise InputError("Launcher lifetime policy must retain source lifetime")
    interval = number(require(entity, "attackSpeed"), "source barrel cadence", EPSILON)
    damage = (
        0
        if stationary
        else number(require(row, "damagePerHit"), "source wagon impact", 0)
    )
    parameters.update(
        targeting={"hall_actor_id": None, "arrival_radius_tiles": None},
        termination={
            "manual_release": "destroy_and_release",
            "maximum_lifetime_seconds": lifetime,
            "decay": {
                "interval_seconds": 1,
                "maximum_hp_fraction_per_pulse": 0,
                "protection": "bypass_damage_immunity",
                "freeze": "clock_continues",
            },
        },
        death={"triggers": "hp_death_only", "effects": []},
    )
    actor.update(
        kind="unit",
        layer="ground" if stationary else "air",
        movement="stationary" if stationary else "air",
        speed=number(require(entity, "movementSpeed"), "source barrel speed", 0)
        / number(units, "movement units", EPSILON)
        * modifiers["movement_speed_multiplier"],
        damage=damage * modifiers["damage_multiplier"],
        attack_interval_seconds=interval * modifiers["attack_interval_multiplier"],
        range=policy["maximum_range_tiles"] * modifiers["range_multiplier"],
        minimum_range=policy["minimum_range_tiles"] * modifiers["range_multiplier"],
        blocking=False,
        width=0,
        height=0,
        target_priorities=[] if stationary else ["defense", "building"],
        target_priority_tiers=[] if stationary else [["defense"], ["building"]],
        target_layers=["ground"],
        healing_class="siege",
        buff_class="siege",
        hazard_class="siege",
        spring_class="siege",
        beneficial_field_immunity=True,
        attack_model={
            "kind": "siege_barrel",
            "source": parameters["source"],
            "entity": entity_id,
            "target_kinds": ["defense", "building", "wall"],
            "target_layers": ["ground"],
            "maximum_hp_fraction": 0,
        },
        siege_model={
            "entity": entity_id,
            "parameters": parameters,
            "generated_requirements": members,
            "barrel_count": row["barrelCount"],
            "reported_snapshot_dps": row.get("damagePerSecond"),
            "unmodified_hit_damage": damage,
            "death_effects": [],
        },
    )
    actor["entity_adapter"].update(
        behavior_verification="explicit_barrel_hypotheses_not_replay_validated"
    )
    if stationary:
        actor.pop("target_priority_tiers", None)
    return actor


def validate_barrel_pattern(pattern):
    if (
        not isinstance(pattern, dict)
        or set(pattern)
        != {
            "kind",
            "source",
            "entity",
            "target_kinds",
            "target_layers",
            "maximum_hp_fraction",
        }
        or pattern["kind"] != "siege_barrel"
        or pattern["entity"] not in BARREL_SIEGES
        or pattern["target_kinds"] != ["defense", "building", "wall"]
        or pattern["target_layers"] != ["ground"]
        or pattern["maximum_hp_fraction"] != 0
    ):
        raise InputError("Barrel weapon requires its dedicated siege runtime")
    identifier(pattern["source"], "barrel weapon evidence")


def attach_barrel_member(actor, instance):
    parameters = deepcopy(require(instance, "barrel_member_parameters"))
    if set(parameters) != {"carrier_id", "barrel_index"}:
        raise InputError("Generated barrel member requires carrier and barrel index")
    identifier(parameters["carrier_id"], "generated barrel carrier")
    integer(parameters["barrel_index"], "generated barrel index", 0)
    if (
        actor["team"] != "attack"
        or actor["kind"] != "unit"
        or actor["spawn_seconds"] != "controlled"
        or actor["counts_for_destruction"]
        or any(
            key in actor
            for key in (
                "siege_model",
                "payload_member_model",
                "garrison_member_model",
                "hero_model",
                "barracks_member_model",
            )
        )
    ):
        raise InputError(
            "Generated barrel actor must be an independent controlled reserve"
        )
    actor["barrel_member_model"] = parameters
    return actor


class StreamedReinforcementCombat(ReinforcementCombat):
    """One finite CC inventory with per-member flight/release positions."""

    def __init__(self, actors, model, width, height):
        super().__init__(actors, model, width, height)
        self.deliveries = {}

    def claim_barrel(self, launch_time, arrival_time, point, carrier_id, trace):
        if carrier_id != self.parameters["delivery"]["carrier_id"]:
            raise InputError("Barrel does not own attacking CC")
        members = [
            member
            for member in self.state["remaining"]
            if member not in self.deliveries
        ]
        if not members:
            return None
        member = members[0]
        self._stage(member, launch_time, arrival_time, point, "barrel", trace)
        return member

    def _stage(self, member, time, arrival, point, reason, trace):
        number(time, "payload launch time", 0)
        number(arrival, "payload arrival time", time)
        if set(point) != {"x", "y"}:
            raise InputError("Payload arrival requires an explicit point")
        for value in point.values():
            number(value, "payload coordinate")
        if member in self.deliveries:
            raise InputError("A CC member cannot be spent twice")
        self.deliveries[member] = {
            "arrival": arrival,
            "point": deepcopy(point),
            "reason": reason,
        }
        self.member_states[member].update(phase="in_flight", launched_at=time)
        if self.state["delivery_time"] is None:
            self.state.update(
                delivery_time=time,
                delivery_reason=reason,
                delivery_point=deepcopy(point),
            )
        self.state.update(
            phase="releasing",
            next_release=min(value["arrival"] for value in self.deliveries.values()),
        )
        trace.append(
            {
                "time_seconds": time,
                "event": "payload_barrel_claimed",
                "member": member,
                "reason": reason,
                "arrival_seconds": arrival,
            }
        )

    def begin_release(self, time, point, reason, carrier_id, trace):
        if carrier_id != self.parameters["delivery"]["carrier_id"]:
            raise InputError("Terminating carrier does not own this CC")
        staged = False
        for ordinal, member in enumerate(
            member
            for member in self.state["remaining"]
            if member not in self.deliveries
        ):
            arrival = siege_time_after(
                time,
                self.parameters["release"]["initial_delay_seconds"]
                + ordinal * self.parameters["release"]["interval_seconds"],
            )
            self._stage(member, time, arrival, point, reason, trace)
            staged = True
        if not self.state["remaining"] and self.state["delivery_time"] is None:
            self.state.update(
                phase="empty",
                delivery_time=time,
                delivery_reason=reason,
                delivery_point=deepcopy(point),
            )
            staged = True
        return staged

    def _release_point(self, member_id, time):
        delivery = self.deliveries.get(member_id)
        if delivery is None:
            return None
        previous = self.state["delivery_point"]
        self.state["delivery_point"] = delivery["point"]
        try:
            return super()._release_point(member_id, time)
        finally:
            self.state["delivery_point"] = previous

    def prepare(self, time, trace, allow_release=True):
        changed = False
        for member, state in self.member_states.items():
            actor = self.actors[member]
            if (
                state["phase"] in {"reserve", "in_flight"}
                and actor["spawn_seconds"] != "controlled"
            ):
                raise InputError("Streamed CC reserve was externally deployed")
            if state["phase"] == "released" and not _active(actor, time):
                state["phase"] = "dead"
            delivery = self.deliveries.get(member)
            if (
                not allow_release
                or state["phase"] != "in_flight"
                or delivery["arrival"] > time
            ):
                continue
            point = self._release_point(member, time)
            if point is None:
                continue
            if actor["hp"] != actor["maximum_hp"]:
                raise InputError("In-flight CC member carries unexplained damage")
            actor.update(
                spawn_seconds=time,
                x=point[0],
                y=point[1],
                target=None,
                next_attack=time + actor["first_attack_seconds"],
            )
            state.update(phase="released", released_at=time)
            self.state["remaining"].remove(member)
            self.state["released"].append(member)
            trace.append(
                {
                    "time_seconds": time,
                    "event": "payload_released",
                    "group": self.parameters["id"],
                    "member": member,
                    "x": point[0],
                    "y": point[1],
                }
            )
            changed = True
        due = [
            self.deliveries[member]["arrival"]
            for member in self.state["remaining"]
            if member in self.deliveries
        ]
        self.state.update(
            next_release=min(due) if due else None,
            phase=(
                "empty"
                if not self.state["remaining"]
                else "releasing" if due else "waiting_for_delivery"
            ),
        )
        return changed

    def next_boundary(self, time):
        due = [
            self.deliveries[member]["arrival"]
            for member in self.state["remaining"]
            if member in self.deliveries and self.deliveries[member]["arrival"] > time
        ]
        return min(due) if due else None

    def release_ready(self, time):
        return any(
            self.deliveries[member]["arrival"] <= time
            and self._release_point(member, time) is not None
            for member in self.state["remaining"]
            if member in self.deliveries
        )

    def result(self):
        return {**super().result(), "deliveries": deepcopy(self.deliveries)}


class BarrelSiegeCombat(SiegeCombat):
    """Carrier lifecycle using the existing kernel hooks and independent flights."""

    def __init__(self, actors, select_target, reinforcements, width, height):
        self.actors, self.ordinary_select_target, self.reinforcements = (
            actors,
            select_target,
            reinforcements,
        )
        self.width, self.height = width, height
        self.models, self.states, self.generated = {}, {}, {}
        self.pending, self.serial = [], 0
        if not isinstance(reinforcements, StreamedReinforcementCombat):
            raise InputError("Barrel runtime requires a streamed single-owner CC")
        carriers = [actor for actor in actors.values() if "siege_model" in actor]
        if len(carriers) != 1:
            raise InputError("Barrel runtime requires exactly one selected carrier")
        actor = carriers[0]
        model = deepcopy(actor["siege_model"])
        if model["entity"] not in BARREL_SIEGES:
            raise InputError("Unknown barrel carrier identity")
        integer(model["barrel_count"], "compiled barrel capacity", 1)
        requirements = require(model, "generated_requirements")
        if not isinstance(requirements, list) or not requirements:
            raise InputError("Barrel carrier requires finite generated reserves")
        parameters = model["parameters"]
        validate_barrel_pattern(actor["attack_model"])
        _validate_policy(parameters["behavior"])
        if parameters["payload_group_id"] != reinforcements.parameters[
            "id"
        ] or reinforcements.parameters["delivery"] != {
            "kind": "siege",
            "carrier_id": actor["id"],
        }:
            raise InputError("Barrel carrier does not own the single attacking CC")
        if (
            actor["team"] != "attack"
            or actor["kind"] != "unit"
            or actor["counts_for_destruction"]
            or actor["blocking"]
            or not actor.get("beneficial_field_immunity")
            or actor["layer"]
            != ("ground" if model["entity"] == "troop-launcher" else "air")
            or actor["movement"]
            != ("stationary" if model["entity"] == "troop-launcher" else "air")
        ):
            raise InputError("Invalid barrel carrier combat role")
        self.models[actor["id"]] = model
        self.states[actor["id"]] = {
            "phase": "undeployed",
            "deployed_at": None,
            "terminated_at": None,
            "termination_reason": None,
            "anchor": None,
            "next_decay": None,
            "expires_at": None,
            "route_arrival": None,
            "blocker": None,
            "weapon_launches": 0,
        }
        expected = set()
        for entry in requirements:
            if not isinstance(entry, dict) or set(entry) != {
                "actor_id",
                "entity",
                "level",
                "barrel_index",
            }:
                raise InputError(
                    "Generated barrel manifest requires exact ownership fields"
                )
            identifier(entry["actor_id"], "generated barrel ID")
            integer(entry["level"], "generated barrel level", 1)
            integer(
                entry["barrel_index"],
                "generated barrel index",
                0,
                model["barrel_count"] - 1,
            )
            if entry["actor_id"] in expected:
                raise InputError("Generated barrel manifest cannot repeat a child")
            member = actors.get(entry["actor_id"])
            if (
                member is None
                or member.get("barrel_member_model")
                != {"carrier_id": actor["id"], "barrel_index": entry["barrel_index"]}
                or member.get("entity_adapter", {}).get("entity") != entry["entity"]
                or member["entity_adapter"]["level"] != entry["level"]
                or member["spawn_seconds"] != "controlled"
                or member["team"] != "attack"
                or member["kind"] != "unit"
                or member["counts_for_destruction"]
                or any(
                    key in member
                    for key in (
                        "payload_member_model",
                        "garrison_member_model",
                        "siege_model",
                    )
                )
            ):
                raise InputError(
                    "Missing, mismatched or multiply owned generated barrel actor"
                )
            expected.add(entry["actor_id"])
            self.generated[entry["actor_id"]] = {
                **entry,
                "phase": "unproduced",
                "arrival": None,
                "point": None,
                "released_at": None,
            }
        declared = {
            key for key, member in actors.items() if "barrel_member_model" in member
        }
        if expected != declared:
            raise InputError("Every generated barrel actor must have exactly one owner")
        release = parameters["behavior"]["generated_release"]
        if (
            not isinstance(release, dict)
            or set(release)
            != {
                "offsets",
                "maximum_displacement_tiles",
                "position_policy",
                "blocked_position",
            }
            or set(release["offsets"]) != expected
            or release["position_policy"]
            != "explicit_offset_then_nearest_clear_ground_cell"
            or release["blocked_position"] != "hold_member_until_legal_point_exists"
        ):
            raise InputError(
                "Generated barrel placement requires exact offsets and blocked policy"
            )
        number(release["maximum_displacement_tiles"], "barrel displacement", 0)
        for offset in release["offsets"].values():
            if set(offset) != {"x", "y"}:
                raise InputError("Generated barrel offsets require x and y")
            for value in offset.values():
                number(value, "generated offset")
        self.placement = _GeneratedRelease(actors, release, width, height)

    def _activate(self, actor_id, time, trace):
        previous = self.states[actor_id]["phase"]
        super()._activate(actor_id, time, trace)
        if previous == "undeployed" and self.states[actor_id]["phase"] == "active":
            self.actors[actor_id]["next_attack"] = siege_time_after(
                self.states[actor_id]["deployed_at"],
                self.models[actor_id]["parameters"]["behavior"][
                    "first_launch_delay_seconds"
                ],
            )

    def validate_command(self, command, time=None):
        if command.get("kind") == "deploy" and set(command.get("targets", [])) & set(
            self.generated
        ):
            raise InputError("Generated barrel reserves cannot be externally deployed")
        return super().validate_command(command, time)

    def _terminate(self, actor_id, time, reason, trace):
        changed = super()._terminate(actor_id, time, reason, trace)
        if changed:
            for state in self.generated.values():
                if state["phase"] == "unproduced":
                    state["phase"] = "cancelled"
        return changed

    def apply_commands(self, commands, time, trace):
        for command in commands:
            self.validate_command(command, time)
        return super().apply_commands(commands, time, trace)

    def select_target(self, actor, actors, time, blocked, width, height):
        if actor["id"] not in self.models:
            return self.ordinary_select_target(
                actor, actors, time, blocked, width, height
            )
        if self.states[actor["id"]]["phase"] != "active" or not _active(actor, time):
            return None, []
        if self.models[actor["id"]]["entity"] == "sky-wagon":
            target, route = self.ordinary_select_target(
                actor, actors, time, blocked, width, height
            )
            return target, self._remember_arrival(actor, route, time)
        candidates = [
            (target_distance(center(actor), ally), ally["id"], ally)
            for ally in actors.values()
            if ally["id"] != actor["id"]
            and ally["team"] == "attack"
            and ally["kind"] in {"unit", "hero"}
            and _active(ally, time)
            and not ally.get("_siege_underground", False)
            and actor["minimum_range"] - EPSILON
            <= target_distance(center(actor), ally)
            <= actor["range"] + EPSILON
        ]
        target = min(candidates, key=lambda item: item[:2])[2] if candidates else None
        actor["target"] = target["id"] if target else None
        return target, []

    def launch(self, actor, target, actors, time, trace):
        state = self.states[actor["id"]]
        model = self.models[actor["id"]]
        if (
            state["phase"] != "active"
            or not _active(actor, time)
            or actor["frozen_until"] > time + EPSILON
            or actor["next_attack"] > time + EPSILON
            or state["weapon_launches"] >= model["barrel_count"]
        ):
            raise InputError(
                "Barrel launch violates carrier lifetime, status, cadence or capacity"
            )
        distance = target_distance(center(actor), target)
        stationary = model["entity"] == "troop-launcher"
        if (
            not _active(target, time)
            or (target["team"] == actor["team"]) != stationary
            or distance > actor["range"] + EPSILON
            or distance < actor["minimum_range"] - EPSILON
        ):
            raise InputError(
                "Barrel target is outside its explicit eligibility or range"
            )
        if not stationary and target["kind"] not in {"defense", "building"}:
            raise InputError("Sky Wagon must target a structure")
        policy = model["parameters"]["behavior"]
        arrival = siege_time_after(time, policy["flight_seconds"])
        point = {"x": center(target)[0], "y": center(target)[1]}
        index = state["weapon_launches"]
        for member in self.generated.values():
            if member["barrel_index"] == index:
                member.update(phase="in_flight", arrival=arrival, point=deepcopy(point))
        self.reinforcements.claim_barrel(time, arrival, point, actor["id"], trace)
        if actor["damage"]:
            self._queue(
                arrival,
                {
                    "source": actor["id"],
                    "source_team": actor["team"],
                    "point": point,
                    "amount": actor["damage"],
                    "radius": policy["impact_radius_tiles"],
                },
            )
        state["weapon_launches"] += 1
        actor["next_attack"] = siege_time_after(time, actor["attack_interval_seconds"])
        trace.append(
            {
                "time_seconds": time,
                "event": "siege_barrel_launch",
                "source": actor["id"],
                "target": target["id"],
                "barrel_index": index,
                "arrival_seconds": arrival,
            }
        )
        if state["weapon_launches"] == model["barrel_count"]:
            self._terminate(actor["id"], time, "barrels_exhausted", trace)

    def prepare(self, actors, time, trace, allow_release=True):
        changed = super().prepare(actors, time, trace, allow_release=allow_release)
        for member_id, state in self.generated.items():
            actor = actors[member_id]
            if (
                state["phase"] in {"unproduced", "in_flight", "cancelled"}
                and actor["spawn_seconds"] != "controlled"
            ):
                raise InputError("Generated barrel reserve was externally deployed")
            if state["phase"] == "released" and not _active(actor, time):
                state["phase"] = "dead"
            if (
                not allow_release
                or state["phase"] != "in_flight"
                or state["arrival"] > time
            ):
                continue
            self.placement.state["delivery_point"] = state["point"]
            point = self.placement._release_point(member_id, time)
            if point is None:
                continue
            if actor["hp"] != actor["maximum_hp"]:
                raise InputError("In-flight generated troop carries unexplained damage")
            actor.update(
                spawn_seconds=time,
                x=point[0],
                y=point[1],
                target=None,
                next_attack=time + actor["first_attack_seconds"],
            )
            state.update(phase="released", released_at=time)
            trace.append(
                {
                    "time_seconds": time,
                    "event": "barrel_generated_released",
                    "source": actor["barrel_member_model"]["carrier_id"],
                    "member": member_id,
                    "x": point[0],
                    "y": point[1],
                }
            )
            changed = True
        return changed

    def resolve(self, actors, time, trace):
        from heapq import heappop
        from .damage_receipts import record_damage

        damage = defaultdict(float)
        while self.pending and self.pending[0][0] <= time:
            _, _, packet = heappop(self.pending)
            point = packet["point"]
            for target in actors.values():
                if (
                    _active(target, time)
                    and target["team"] != packet["source_team"]
                    and target["kind"] in {"defense", "building", "wall"}
                    and not target.get("_tesla_hidden", False)
                    and target["layer"] == "ground"
                    and target_distance((point["x"], point["y"]), target)
                    <= packet["radius"] + EPSILON
                ):
                    actual = record_damage(
                        self,
                        target,
                        packet["amount"],
                        time,
                        source_id=packet["source"],
                        source_actor_id=packet["source"],
                        source_team=packet["source_team"],
                        origin="weapon",
                    )
                    damage[target["id"]] += actual
                    trace.append(
                        {
                            "time_seconds": time,
                            "event": "siege_barrel_impact",
                            "source": packet["source"],
                            "target": target["id"],
                            "damage": actual,
                        }
                    )
        return damage

    def next_boundary(self, time):
        inherited = super().next_boundary(time)
        boundaries = [inherited] if inherited is not None else []
        boundaries.extend(
            state["arrival"]
            for state in self.generated.values()
            if state["phase"] == "in_flight" and state["arrival"] > time
        )
        return min(boundaries) if boundaries else None

    def release_ready(self, time):
        if self.reinforcements.release_ready(time):
            return True
        for member_id, state in self.generated.items():
            if state["phase"] == "in_flight" and state["arrival"] <= time:
                self.placement.state["delivery_point"] = state["point"]
                if self.placement._release_point(member_id, time) is not None:
                    return True
        return False

    def frame(self, actor):
        frame = super().frame(actor)
        if actor["id"] in self.generated:
            frame["barrel_member_phase"] = self.generated[actor["id"]]["phase"]
        return frame

    def result(self):
        return {
            **super().result(),
            "generated": deepcopy(self.generated),
            "full_game_prediction": False,
            "experimental_barrel_policy": True,
        }

    def continuation_reasons(self, time):
        from .battle_termination import continuation_fact

        facts = [
            continuation_fact(
                "pending_damage",
                f"siege:{serial}",
                [packet["source"]],
                source_team=packet["source_team"],
                not_before_seconds=arrival,
            )
            for arrival, serial, packet in self.pending
            if packet["amount"] > 0
        ]
        facts.extend(
            continuation_fact(
                "pending_release",
                f"barrel:{member_id}",
                [member_id],
                not_before_seconds=state["arrival"],
            )
            for member_id, state in self.generated.items()
            if state["phase"] == "in_flight"
        )
        return facts
