"""Owned attacking summons with finite reserves and explicit experimental timing.

Reserves are compiled before simulation, so existing combat/status registries see
every actor. Child statistics and geometry must be supplied; catalog descriptions
alone cannot establish complete current child weapons.
"""

from copy import deepcopy

from .battle_termination import continuation_fact
from .common import InputError, identifier, integer, number, require
from .spatial import EPSILON, _active, center


SUMMON_ENTITIES = frozenset(
    {
        "witch",
        "super-witch",
        "golem",
        "lava-hound",
        "ice-hound",
        "yeti",
        "super-yeti",
        "super-hog-rider",
        "furnace",
    }
)
TRIGGERS = {
    "witch": "periodic",
    "super-witch": "periodic",
    "golem": "actual_death",
    "lava-hound": "actual_death",
    "ice-hound": "actual_death",
    "yeti": "damage_threshold",
    "super-yeti": "damage_threshold",
    "super-hog-rider": "hp_threshold",
    "furnace": "periodic",
}


def compile_summon_model(actor, instance, entity, row):
    entity_id = entity["id"]
    if entity_id not in SUMMON_ENTITIES or actor.get("team") != "attack":
        raise InputError("Summons require a registered attacking troop")
    parameters = deepcopy(require(instance, "summon_parameters"))
    fields = {
        "source",
        "statistics_status",
        "trigger",
        "first_delay_seconds",
        "interval_seconds",
        "release_delay_seconds",
        "batch_size",
        "live_cap",
        "total_cap",
        "damage_threshold",
        "split_hp_fraction",
        "death_remainder",
        "freeze_policy",
        "pending_source_loss",
        "reserve_policy",
        "lifetime_seconds",
        "children",
    }
    if set(parameters) != fields:
        raise InputError("Summons require the complete explicit lifecycle contract")
    identifier(parameters["source"], "summon behavior evidence")
    if parameters["statistics_status"] != "explicit_uncalibrated_hypothesis":
        raise InputError("Incomplete child/timing sources cannot be marked calibrated")
    if parameters["trigger"] != TRIGGERS[entity_id]:
        raise InputError("Summon trigger disagrees with this troop identity")
    for field in (
        "first_delay_seconds",
        "release_delay_seconds",
        "damage_threshold",
        "lifetime_seconds",
    ):
        number(parameters[field], field, 0)
    number(parameters["interval_seconds"], "summon interval", EPSILON)
    number(parameters["split_hp_fraction"], "split HP fraction", 0, 1)
    for field in ("batch_size", "live_cap", "total_cap"):
        integer(parameters[field], field, 1)
    if parameters["batch_size"] > parameters["live_cap"]:
        raise InputError("Summon batch exceeds its live cap")
    if parameters["freeze_policy"] != "skip_due_batches_clock_continues":
        raise InputError("Unsupported summon freeze policy")
    if parameters["pending_source_loss"] != "released_batches_survive":
        raise InputError("Unsupported pending summon persistence")
    if parameters["reserve_policy"] != "finite_precompiled_never_reuse_dead_actor":
        raise InputError("Generated actor identities cannot be recycled")
    if parameters["death_remainder"] not in {"release_remaining", "none"}:
        raise InputError("Summon death remainder must be explicit")
    if entity_id in {"yeti", "super-yeti"} and parameters["damage_threshold"] <= 0:
        raise InputError("Damage summons require a positive threshold")
    if entity_id == "witch":
        if parameters["batch_size"] != require(row, "skeletonsPerSummon") or parameters[
            "live_cap"
        ] != require(row, "maxSkeletons"):
            raise InputError("Witch batch/cap must match the selected catalog level")
        if parameters["interval_seconds"] != require(entity, "summonCooldown"):
            raise InputError("Witch cadence must match the catalog summonCooldown")
    if entity_id == "super-witch" and (
        parameters["batch_size"] != 1 or parameters["live_cap"] != 1
    ):
        raise InputError("Super Witch owns one living Big Boy")
    quantity_field = {
        "golem": "golemitesSpawned",
        "lava-hound": "pupsOnOffense",
        "ice-hound": "pupsOnOffense",
        "furnace": "firemitesSpawned",
    }.get(entity_id)
    if quantity_field and parameters["total_cap"] != require(row, quantity_field):
        raise InputError("Summon total must match the attacking catalog quantity")
    if entity_id == "furnace" and parameters["lifetime_seconds"] != require(
        entity, "lifetime"
    ):
        raise InputError("Furnace lifetime must match the catalog")
    children = parameters["children"]
    if not isinstance(children, list) or len(children) != parameters["total_cap"]:
        raise InputError("Every generated child requires a finite precompiled reserve")
    ids = set()
    for child in children:
        if set(child) != {
            "actor",
            "offset_x",
            "offset_y",
            "source",
            "statistics_status",
        }:
            raise InputError(
                "Child requires an actor, offsets and statistics provenance"
            )
        identifier(child["source"], "child statistics evidence")
        if child["statistics_status"] != "explicit_uncalibrated_hypothesis":
            raise InputError("Child statistics must retain their experimental status")
        template = child["actor"]
        key = identifier(require(template, "id"), "child actor ID")
        if key in ids or key == actor["id"]:
            raise InputError("Generated child IDs must be unique")
        ids.add(key)
        if (
            template.get("team") != "attack"
            or template.get("kind") != "unit"
            or template.get("counts_for_destruction") is not False
        ):
            raise InputError(
                "Child must be an attacking unit outside destruction inventory"
            )
        for field in ("hitpoints", "attack_interval_seconds"):
            number(require(template, field), "child " + field, EPSILON)
        number(child["offset_x"], "child horizontal offset")
        number(child["offset_y"], "child vertical offset")
        if "entity_adapter" in template or "army_binding" in template:
            raise InputError(
                "A generated reserve cannot masquerade as donated or paid inventory"
            )
    actor["troop_summon_model"] = parameters
    return actor


def compile_troop_reserves(actors):
    """Return raw actors for _load_actors before any runtime registry is built."""
    result = []
    ids = {actor["id"] for actor in actors}
    for parent in actors:
        for child in parent.get("troop_summon_model", {}).get("children", []):
            reserve = deepcopy(child["actor"])
            if reserve["id"] in ids:
                raise InputError("Troop reserves collide with existing scene IDs")
            ids.add(reserve["id"])
            reserve.update(
                {
                    "spawn_seconds": "controlled",
                    "x": parent["x"],
                    "y": parent["y"],
                    "summon_model": {
                        "kind": "attacking_troop_child",
                        "parent": parent["id"],
                    },
                }
            )
            reserve["troop_child_statistics"] = {
                "source": child["source"],
                "status": child["statistics_status"],
            }
            result.append(reserve)
    return result


class TroopSummonCombat:
    """Release owned reserves after settled health; released children act normally."""

    def __init__(self, actors, can_release):
        self.actors = actors
        self.can_release = can_release
        self.models = {
            key: deepcopy(actor["troop_summon_model"])
            for key, actor in actors.items()
            if "troop_summon_model" in actor
        }
        self.states = {}
        self.pending = []
        self.releases = []
        for key, model in self.models.items():
            for child in model["children"]:
                reserve = actors.get(child["actor"]["id"])
                if (
                    reserve is None
                    or reserve.get("summon_model", {}).get("parent") != key
                ):
                    raise InputError(
                        "Summon reserves must be loaded and owned before runtime construction"
                    )
            self.states[key] = {
                "deployed_at": None,
                "next_due": None,
                "used": 0,
                "damage": 0.0,
                "thresholds": 0,
                "dead_seen": False,
                "split": False,
                "expired": False,
            }

    def validate_command(self, command):
        if command.get("kind") == "deploy" and any(
            self.actors.get(key, {}).get("summon_model", {}).get("kind")
            == "attacking_troop_child"
            for key in command.get("targets", [])
        ):
            raise InputError(
                "Generated troop children cannot be independently deployed"
            )

    def record_damage(self, actor_id, effective_hp_loss):
        """Call once per settled receipt; healing never replenishes summon budget."""
        if actor_id in self.states:
            self.states[actor_id]["damage"] += number(
                effective_hp_loss, "effective summon-triggering HP loss", 0
            )

    def _living_and_pending(self, key, time):
        living = sum(
            _active(self.actors[child["actor"]["id"]], time)
            for child in self.models[key]["children"]
        )
        return living + sum(item["parent"] == key for item in self.pending)

    def _queue(self, key, count, time, reason, ignore_live_cap=False):
        model, state, parent = self.models[key], self.states[key], self.actors[key]
        capacity = model["total_cap"] - state["used"]
        if not ignore_live_cap:
            capacity = min(
                capacity, model["live_cap"] - self._living_and_pending(key, time)
            )
        count = max(0, min(count, capacity))
        x, y = center(parent)
        for _ in range(count):
            child = model["children"][state["used"]]
            state["used"] += 1
            self.pending.append(
                {
                    "parent": key,
                    "child": child["actor"]["id"],
                    "due": time + model["release_delay_seconds"],
                    "x": x + child["offset_x"],
                    "y": y + child["offset_y"],
                    "reason": reason,
                }
            )

    def prepare(self, time, trace):
        for key, model in self.models.items():
            actor, state = self.actors[key], self.states[key]
            spawn = actor.get("spawn_seconds")
            if (
                state["deployed_at"] is None
                and isinstance(spawn, (int, float))
                and spawn <= time
            ):
                state["deployed_at"] = spawn
                state["next_due"] = spawn + model["first_delay_seconds"]
            if state["deployed_at"] is None:
                continue
            if (
                model["lifetime_seconds"] > 0
                and not state["expired"]
                and _active(actor, time)
                and time >= state["deployed_at"] + model["lifetime_seconds"]
            ):
                state["expired"] = True
                actor["hp"] = 0
                actor["death_time"] = time
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "troop_lifetime_expired",
                        "source": key,
                    }
                )
            dead = actor.get("death_time") is not None
            if dead and not state["dead_seen"]:
                state["dead_seen"] = True
                if (
                    model["trigger"] == "actual_death"
                    or model["death_remainder"] == "release_remaining"
                ):
                    self._queue(key, model["total_cap"], time, "actual_death", True)
            if not _active(actor, time):
                continue
            if model["trigger"] == "periodic" and state["next_due"] <= time:
                if actor.get("frozen_until", 0) <= time + EPSILON:
                    self._queue(key, model["batch_size"], time, "periodic")
                # Advance arithmetically, avoiding unbounded catch-up loops.
                missed = max(
                    1, int((time - state["next_due"]) / model["interval_seconds"]) + 1
                )
                state["next_due"] += missed * model["interval_seconds"]
            elif model["trigger"] == "damage_threshold":
                thresholds = int(
                    (state["damage"] + EPSILON) / model["damage_threshold"]
                )
                due = max(0, thresholds - state["thresholds"])
                self._queue(key, due * model["batch_size"], time, "effective_damage")
                state["thresholds"] = thresholds
            elif (
                model["trigger"] == "hp_threshold"
                and not state["split"]
                and actor["hp"]
                <= actor["maximum_hp"] * model["split_hp_fraction"] + EPSILON
            ):
                state["split"] = True
                self._queue(key, model["total_cap"], time, "mounted_split", True)
                actor["hp"] = 0
                actor["death_time"] = time
                actor["_troop_form_retired"] = True
        waiting = []
        for item in self.pending:
            child = self.actors[item["child"]]
            if item["due"] > time or not self.can_release(
                child, item["x"], item["y"], time
            ):
                waiting.append(item)
                continue
            child.update(
                {
                    "x": item["x"],
                    "y": item["y"],
                    "spawn_seconds": time,
                    "death_time": None,
                    "hp": child["maximum_hp"],
                    "next_attack": time + child["first_attack_seconds"],
                    "frozen_until": 0,
                    "immune_until": 0,
                }
            )
            if "_wall_next_attack" in child:
                child["_wall_next_attack"] = child["next_attack"]
            child.pop("_remaining_path", None)
            event = {
                "time_seconds": time,
                "event": "troop_child_released",
                "source": item["parent"],
                "target": item["child"],
                "reason": item["reason"],
            }
            trace.append(event)
            self.releases.append(deepcopy(event))
        self.pending = waiting

    def next_boundary(self, time):
        boundaries = [item["due"] for item in self.pending if item["due"] > time]
        for key, state in self.states.items():
            if not _active(self.actors[key], time) or state["deployed_at"] is None:
                continue
            model = self.models[key]
            if model["trigger"] == "periodic" and state["used"] < model["total_cap"]:
                boundaries.append(state["next_due"])
            if model["lifetime_seconds"] and not state["expired"]:
                boundaries.append(state["deployed_at"] + model["lifetime_seconds"])
        return min((value for value in boundaries if value > time), default=None)

    def continuation_reasons(self, time):
        return [
            continuation_fact(
                "pending_release",
                "troop:" + item["child"],
                [item["child"]],
                source_team="attack",
                not_before_seconds=item["due"],
            )
            for item in self.pending
        ]

    def result(self):
        return {
            "status": "EXPLICIT_UNCALIBRATED_TROOP_SUMMONS",
            "states": deepcopy(self.states),
            "pending": deepcopy(self.pending),
            "releases": deepcopy(self.releases),
        }
