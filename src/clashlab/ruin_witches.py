"""Rubble consumption and delayed owned Knights under explicit revision policies.

Official June 2026 behavior is reconciled with the August cap/no-decay change.
The saved numeric catalogs have no Ruin Knight child, so child actors remain
complete caller-sourced experimental inputs rather than invented current stats.
"""

from copy import deepcopy
from math import cos, hypot, radians, sin

from .battle_termination import continuation_fact
from .common import InputError, identifier, integer, number, require
from .spatial import EPSILON, _active, _blocked, _ground_route, center, target_distance
from .spell_visibility import untargetable_until


JUNE_SOURCE = "https://supercell.com/en/games/clashofclans/blog/release-notes/the-anime-fury-update-is-here/"
AUGUST_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/release-notes/august-update-3/"
)
REVISION_CAPS = {"june_2026_historical": 8, "august_2026_no_decay": 10}


def compile_ruin_witch(actor, instance, entity, row):
    if (
        entity.get("id") != "ruin-witch"
        or actor.get("team") != "attack"
        or actor.get("kind") != "unit"
    ):
        raise InputError("Ruin Witch requires its attacking unit identity")
    model = deepcopy(require(instance, "ruin_parameters"))
    expected = {
        "source",
        "status",
        "behavior_revision",
        "work_seconds",
        "work_range_tiles",
        "summon_delay_seconds",
        "followthrough_seconds",
        "maximum_knights",
        "work_freeze",
        "after_consumption_clock",
        "rubble_geometry",
        "selection",
        "reservation",
        "spawn_front_distance_tiles",
        "fallback_facing_degrees",
        "blocked_release",
        "knight_hp_decay",
        "children",
    }
    if set(model) != expected:
        raise InputError("Ruin Witch requires a complete rubble/form contract")
    identifier(model["source"], "Ruin Witch behavior evidence")
    if model["status"] != "explicit_uncalibrated_hypothesis":
        raise InputError("Rubble geometry and child statistics are not calibrated")
    revision = model["behavior_revision"]
    if (
        revision not in REVISION_CAPS
        or model["maximum_knights"] != REVISION_CAPS[revision]
    ):
        raise InputError(
            "Choose explicit June eight-Knight or August ten-Knight behavior"
        )
    if (
        model["work_seconds"],
        model["summon_delay_seconds"],
        model["followthrough_seconds"],
    ) != (4, 2, 2):
        raise InputError(
            "Ruin Witch clocks must retain official four/two/two-second phases"
        )
    choices = {
        "work_freeze": "pause_work",
        "after_consumption_clock": "absolute_continues_frozen_and_after_death",
        "rubble_geometry": "destroyed_building_footprint",
        "selection": "closest_reachable_footprint_then_instance_id",
        "reservation": "exclusive_at_work_start_consume_at_completion",
        "blocked_release": "wait_at_captured_front_point",
        "knight_hp_decay": "none",
    }
    for field, value in choices.items():
        if model[field] != value:
            raise InputError("Unsupported Ruin Witch " + field)
    if revision != "august_2026_no_decay":
        raise InputError(
            "Historical Knight HP decay lacks a numeric contract; only the current no-decay revision is implemented"
        )
    number(model["spawn_front_distance_tiles"], "Knight front distance", 0)
    number(model["fallback_facing_degrees"], "Ruin Witch fallback facing")
    children = model["children"]
    if not isinstance(children, list) or len(children) != model["maximum_knights"]:
        raise InputError("All ten Knights need finite precompiled owned reserves")
    ids = set()
    for child in children:
        if set(child) != {
            "actor",
            "source",
            "status",
            "level",
            "wall_damage_multiplier",
        }:
            raise InputError(
                "Knight reserve needs exact actor/level/statistic/wall provenance"
            )
        identifier(child["source"], "Knight statistics evidence")
        if child["status"] != "explicit_uncalibrated_hypothesis" or integer(
            child["level"], "Knight level", 1
        ) != require(row, "ruinKnightLevel"):
            raise InputError(
                "Knight level must match the selected Witch and preserve experimental stats"
            )
        template = child["actor"]
        key = identifier(require(template, "id"), "Knight actor ID")
        if key == actor["id"] or key in ids:
            raise InputError("Knight reserve identities must be unique")
        ids.add(key)
        if (
            template.get("team") != "attack"
            or template.get("kind") != "unit"
            or template.get("layer") != "ground"
            or template.get("counts_for_destruction") is not False
        ):
            raise InputError("Knight must be an attacking generated ground unit")
        if template.get("target_priority_tiers") != [
            ["defense", "building"]
        ] or template.get("target_priorities") != ["defense", "building"]:
            raise InputError(
                "Knight targets nearest buildings without a defense-priority tier"
            )
        bonus = number(child["wall_damage_multiplier"], "Knight wall bonus", 1)
        if bonus == 1:
            raise InputError("Official Knight behavior requires extra wall damage")
        wall = require(template, "wall_behavior")
        from .walls import ROUTE_COSTS

        if wall.get("route_cost") not in ROUTE_COSTS:
            raise InputError("Knight needs a shared WallRouting route cost convention")
        if wall.get("kind") != "clear_obstructions":
            raise InputError(
                "Knight needs explicit wall clearing and wall damage bonus"
            )
        wall["weapon"]["damage"] *= bonus
        if (
            "entity_adapter" in template
            or "army_binding" in template
            or "lifetime_seconds" in template
            or "hp_decay_model" in template
        ):
            raise InputError(
                "Knight cannot impersonate paid inventory or silently inherit removed HP decay"
            )
    actor.update(
        damage=0,
        range=number(model["work_range_tiles"], "Ruin Witch rubble work range", 0),
        target_priorities=[],
        target_layers=[],
        attack_model={"kind": "none", "source": actor["source"]},
        wall_behavior={"kind": "avoid", "source": model["source"]},
    )
    actor.pop("target_priority_tiers", None)
    actor["ruin_witch_model"] = model
    actor["ruin_source_audit"] = {
        "june_source": JUNE_SOURCE,
        "august_source": AUGUST_SOURCE,
        "saved_catalog_cap": row.get("maximumRuinKnightsSummoned"),
        "selected_cap": model["maximum_knights"],
        "discarded_weapon_statistics": deepcopy(row.get("stats")),
        "child_statistics": "not_present_in_saved_catalog_or_extraction",
    }
    return actor


def compile_ruin_knights(raw_actors):
    result = []
    ids = {actor["id"] for actor in raw_actors}
    for parent in raw_actors:
        for child in parent.get("ruin_witch_model", {}).get("children", []):
            actor = deepcopy(child["actor"])
            if actor["id"] in ids:
                raise InputError("Generated Knight collides with an existing actor")
            ids.add(actor["id"])
            actor.update(
                spawn_seconds="controlled",
                x=parent["x"],
                y=parent["y"],
                summon_model={"kind": "ruin_knight", "parent": parent["id"]},
            )
            actor["ruin_knight_statistics"] = {
                key: child[key]
                for key in ("source", "status", "level", "wall_damage_multiplier")
            }
            result.append(actor)
    return result


class RuinWitchCombat:
    def __init__(self, actors, width, height, can_release):
        self.actors, self.width, self.height, self.can_release = (
            actors,
            width,
            height,
            can_release,
        )
        self.models = {
            key: deepcopy(actor["ruin_witch_model"])
            for key, actor in actors.items()
            if "ruin_witch_model" in actor
        }
        self.states = {
            key: {
                "phase": "idle",
                "rubble": None,
                "elapsed": 0.0,
                "last_time": None,
                "running": False,
                "used": 0,
                "resume_at": None,
            }
            for key in self.models
        }
        self.reserved, self.consumed, self.pending, self.releases = {}, set(), [], []
        for key, model in self.models.items():
            for child in model["children"]:
                reserve = actors.get(child["actor"]["id"])
                if reserve is None or reserve.get("summon_model") != {
                    "kind": "ruin_knight",
                    "parent": key,
                }:
                    raise InputError(
                        "Ruin Knight reserves must be loaded and owned before runtime construction"
                    )

    def validate_command(self, command):
        if command.get("kind") == "deploy":
            for key in command.get("targets", []):
                actor = self.actors.get(key, {})
                if actor.get("summon_model", {}).get(
                    "kind"
                ) == "ruin_knight" or actor.get("_ruin_despawned"):
                    raise InputError(
                        "Generated Knights and spent Ruin Witches cannot be independently deployed"
                    )

    def _rubble_eligible(self, source_id, actor, time):
        return (
            actor["team"] != self.actors[source_id]["team"]
            and actor["kind"] in {"building", "defense"}
            and actor.get("death_time") is not None
            and actor["death_time"] <= time
            and actor["id"] not in self.consumed
            and self.reserved.get(actor["id"], source_id) == source_id
            and untargetable_until(actor) <= time
        )

    def select_target(self, actor, actors, time, blocked, width, height):
        key = actor["id"]
        if (
            key not in self.models
            or not _active(actor, time)
            or self.states[key]["phase"] in {"followthrough", "spent"}
        ):
            return None, []
        if self.states[key]["phase"] == "work":
            target = actors.get(self.states[key]["rubble"])
            return (
                (target, [])
                if target is not None and self._rubble_eligible(key, target, time)
                else (None, [])
            )
        for _, candidate_id, candidate in sorted(
            (target_distance(center(actor), candidate), candidate_id, candidate)
            for candidate_id, candidate in actors.items()
            if self._rubble_eligible(key, candidate, time)
        ):
            # Reuse the shared ground route; no wall-clearing or enemy-wall jump.
            mover = dict(actor)
            mover.pop("_remaining_path", None)
            mover.pop("_route_signature", None)
            route = _ground_route(mover, candidate, blocked, width, height)
            if route is not None:
                return candidate, route
        return None, []

    def _consume(self, key, time, trace):
        model, state, actor = self.models[key], self.states[key], self.actors[key]
        rubble = self.actors[state["rubble"]]
        self.consumed.add(rubble["id"])
        self.reserved.pop(rubble["id"], None)
        x, y = center(actor)
        tx, ty = center(rubble)
        distance = hypot(tx - x, ty - y)
        facing = radians(model["fallback_facing_degrees"])
        dx, dy = (
            ((tx - x) / distance, (ty - y) / distance)
            if distance > EPSILON
            else (cos(facing), sin(facing))
        )
        child_id = model["children"][state["used"]]["actor"]["id"]
        state["used"] += 1
        due = time + model["summon_delay_seconds"]
        self.pending.append(
            {
                "parent": key,
                "child": child_id,
                "due": due,
                "x": x + dx * model["spawn_front_distance_tiles"],
                "y": y + dy * model["spawn_front_distance_tiles"],
            }
        )
        state.update(
            phase="followthrough",
            resume_at=due + model["followthrough_seconds"],
            running=False,
        )
        trace.append(
            {
                "time_seconds": time,
                "event": "ruin_rubble_consumed",
                "source": key,
                "rubble": rubble["id"],
                "knight": child_id,
            }
        )

    def prepare(self, time, trace):
        blocked = _blocked(self.actors, time)
        for key in sorted(self.models):
            model, state, actor = self.models[key], self.states[key], self.actors[key]
            if state["phase"] == "work":
                if state["running"] and state["last_time"] is not None:
                    state["elapsed"] += time - state["last_time"]
                state["last_time"] = time
                rubble = self.actors.get(state["rubble"])
                if (
                    not _active(actor, time)
                    or rubble is None
                    or not self._rubble_eligible(key, rubble, time)
                ):
                    self.reserved.pop(state["rubble"], None)
                    state.update(phase="idle", rubble=None, running=False, elapsed=0.0)
                elif state["elapsed"] >= model["work_seconds"]:
                    self._consume(key, time, trace)
                else:
                    state["running"] = actor.get("frozen_until", 0) <= time
            if state["phase"] == "followthrough" and time >= state["resume_at"]:
                if state["used"] == model["maximum_knights"]:
                    state["phase"] = "spent"
                    if actor.get("death_time") is None:
                        actor["spawn_seconds"] = "controlled"
                        actor["_ruin_despawned"] = True
                        trace.append(
                            {
                                "time_seconds": time,
                                "event": "ruin_witch_despawn",
                                "source": key,
                            }
                        )
                else:
                    state.update(phase="idle", rubble=None)
            if (
                state["phase"] == "idle"
                and _active(actor, time)
                and actor.get("frozen_until", 0) <= time
            ):
                target, _ = self.select_target(
                    actor, self.actors, time, blocked, self.width, self.height
                )
                if (
                    target is not None
                    and target_distance(center(actor), target)
                    <= actor["range"] + EPSILON
                ):
                    self.reserved[target["id"]] = key
                    state.update(
                        phase="work",
                        rubble=target["id"],
                        elapsed=0.0,
                        last_time=time,
                        running=True,
                    )
                    trace.append(
                        {
                            "time_seconds": time,
                            "event": "ruin_work_started",
                            "source": key,
                            "rubble": target["id"],
                        }
                    )
            actor["_ruin_movement_locked"] = state["phase"] in {
                "work",
                "followthrough",
                "spent",
            }
        waiting = []
        for item in self.pending:
            child = self.actors[item["child"]]
            if item["due"] > time or not self.can_release(
                child, item["x"], item["y"], time
            ):
                waiting.append(item)
                continue
            child.update(
                x=item["x"],
                y=item["y"],
                spawn_seconds=time,
                hp=child["maximum_hp"],
                death_time=None,
                frozen_until=0,
                immune_until=0,
                next_attack=time + child["first_attack_seconds"],
            )
            if "_wall_next_attack" in child:
                child["_wall_next_attack"] = child["next_attack"]
            event = {
                "time_seconds": time,
                "event": "ruin_knight_release",
                "source": item["parent"],
                "target": item["child"],
            }
            trace.append(event)
            self.releases.append(deepcopy(event))
        self.pending = waiting

    def next_boundary(self, time):
        boundaries = [item["due"] for item in self.pending]
        for key, state in self.states.items():
            if state["phase"] == "work" and state["running"]:
                boundaries.append(
                    time + (self.models[key]["work_seconds"] - state["elapsed"])
                )
            elif state["phase"] == "followthrough":
                boundaries.append(state["resume_at"])
        return min((value for value in boundaries if value > time), default=None)

    def continuation_reasons(self, time):
        return [
            continuation_fact(
                "pending_release",
                "ruin:" + item["child"],
                [item["child"]],
                not_before_seconds=item["due"],
            )
            for item in self.pending
        ]

    def result(self):
        return {
            "status": "EXPLICIT_UNCALIBRATED_RUBBLE_AND_KNIGHT_GEOMETRY",
            "states": deepcopy(self.states),
            "consumed_rubble": sorted(self.consumed),
            "pending": deepcopy(self.pending),
            "releases": deepcopy(self.releases),
        }
