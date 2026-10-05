"""Finite owned split/throw/recombine forms for permanent Meteor Golem.

Official notes establish throwing over walls, recombination and Angry transfer.
Child statistics, throw geometry and HP/cooldown arithmetic are explicit opt-in
experiment contracts. Form identities are predeclared and never resurrected.
"""

from copy import deepcopy
from math import hypot

from .battle_termination import continuation_fact
from .common import InputError, identifier, integer, number, require
from .spatial import EPSILON, _active, _ground_route, center, target_distance


PERMANENT_DATA_ID = 4000177
INTRODUCTION_SOURCE = "https://supercell.com/en/games/clashofclans/blog/release-notes/town-hall-18-crash-lands-update/"
TRANSFER_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/release-notes/august-update-3/"
)


def compile_meteor_golem(actor, instance, entity, row):
    if (
        entity.get("id") != "meteor-golem"
        or entity.get("dataId") != PERMANENT_DATA_ID
        or actor.get("team") != "attack"
    ):
        raise InputError(
            "Meteor lifecycle requires the permanent attacking dataId 4000177, not seasonal 4000167"
        )
    model = deepcopy(require(instance, "meteor_parameters"))
    fields = {
        "source",
        "status",
        "group_id",
        "level",
        "split_trigger",
        "throw_speed_tiles_per_second",
        "throw_release_delay_seconds",
        "landing_position",
        "local_enemy_radius_tiles",
        "merge_range_tiles",
        "merge_delay_seconds",
        "partner_policy",
        "hp_policy",
        "status_policy",
        "merge_position",
        "reserve_exhaustion",
        "root_children",
        "merge_forms",
    }
    if set(model) != fields:
        raise InputError(
            "Meteor Golem requires complete split, throw, partner and recombination contracts"
        )
    identifier(model["source"], "Meteor Golem behavior evidence")
    identifier(model["group_id"], "Meteor form cohort")
    if (
        model["status"] != "explicit_uncalibrated_hypothesis"
        or model["level"] != row["level"]
    ):
        raise InputError(
            "Meteor lifecycle must match the selected level and remain experimental"
        )
    choices = {
        "split_trigger": "successful_weapon_launch_once",
        "landing_position": "primary_center_at_launch_wait_if_blocked",
        "partner_policy": "nearest_same_level_cohort_if_no_local_enemy",
        "hp_policy": "split_keep_hp_fraction_merge_weighted_hp_fraction",
        "status_policy": "shared_transfer_preserves_angry_effect_and_targeting",
        "merge_position": "midpoint_wait_if_blocked",
        "reserve_exhaustion": "reject_merge_with_no_finite_reserve",
    }
    for field, value in choices.items():
        if model[field] != value:
            raise InputError("Unsupported experimental Meteor " + field)
    number(model["throw_speed_tiles_per_second"], "Meteor throw speed", EPSILON)
    for field in (
        "throw_release_delay_seconds",
        "local_enemy_radius_tiles",
        "merge_range_tiles",
        "merge_delay_seconds",
    ):
        number(model[field], field, 0)
    pattern = require(actor, "attack_model")
    projectile = require(pattern, "projectile")
    if (
        pattern.get("kind") != "radial"
        or projectile.get("timing") != "launch_distance_delay"
        or projectile.get("speed_tiles_per_second")
        != model["throw_speed_tiles_per_second"]
        or projectile.get("delay_seconds", 0) != model["throw_release_delay_seconds"]
        or projectile.get("destination") != "fixed_target_center_at_launch"
        or projectile.get("inactive_primary_policy")
        != "resolve_at_fixed_launch_position"
    ):
        raise InputError(
            "Meteor landing weapon and thrown child's arrival must share an explicit fixed radial travel clock"
        )
    forms = require(model, "merge_forms")
    if not isinstance(forms, list):
        raise InputError("Meteor merges need an explicit finite form list")
    ids = {actor["id"]}
    for form in forms:
        if set(form) != {"id", "children"}:
            raise InputError(
                "Generated Meteor form needs a unique ID and its own child pair"
            )
        key = identifier(form["id"], "merged Meteor form ID")
        if key in ids:
            raise InputError("Meteor form identities cannot be reused")
        ids.add(key)
    for pair in [model["root_children"], *(form["children"] for form in forms)]:
        if not isinstance(pair, list) or len(pair) != 2:
            raise InputError(
                "Every declared Meteor form requires two explicit Meteormites"
            )
        for child in pair:
            if set(child) != {"actor", "source", "status", "level"}:
                raise InputError(
                    "Meteormite requires a complete child actor and level/statistic provenance"
                )
            identifier(child["source"], "Meteormite statistics evidence")
            if (
                child["status"] != "explicit_uncalibrated_hypothesis"
                or child["level"] != model["level"]
            ):
                raise InputError(
                    "Meteormite statistics must match level and retain experimental status"
                )
            template = child["actor"]
            key = identifier(require(template, "id"), "Meteormite actor ID")
            if key in ids:
                raise InputError(
                    "Meteor child identities must be unique across all forms"
                )
            ids.add(key)
            if (
                template.get("team") != "attack"
                or template.get("kind") != "unit"
                or template.get("movement") != "ground"
                or template.get("counts_for_destruction") is not False
            ):
                raise InputError(
                    "Meteormite must be a generated attacking ground actor"
                )
            if "army_binding" in template or "entity_adapter" in template:
                raise InputError(
                    "Meteormite cannot masquerade as paid or donated inventory"
                )
    actor["meteor_parameters"] = model
    actor["meteor_adult_model"] = {
        "root": actor["id"],
        "group_id": model["group_id"],
        "level": model["level"],
        "children": [child["actor"]["id"] for child in model["root_children"]],
        "generated": False,
    }
    actor["meteor_source_audit"] = {
        "permanent_data_id": PERMANENT_DATA_ID,
        "excluded_seasonal_data_id": 4000167,
        "introduction": INTRODUCTION_SOURCE,
        "angry_transfer_fix": TRANSFER_SOURCE,
        "missing_child_statistics": True,
        "hp_and_timing_policy": "explicit_uncalibrated_hypothesis",
    }
    return actor


def compile_meteor_reserves(raw_actors):
    result, ids = [], {actor["id"] for actor in raw_actors}
    for root in raw_actors:
        if "meteor_parameters" not in root:
            continue
        model = root["meteor_parameters"]
        forms = [
            {"id": root["id"], "children": model["root_children"]},
            *model["merge_forms"],
        ]
        for index, form in enumerate(forms):
            if index:
                adult = deepcopy(root)
                for field in (
                    "meteor_parameters",
                    "army_binding",
                    "payload_member_model",
                ):
                    adult.pop(field, None)
                adult.update(
                    id=form["id"],
                    spawn_seconds="controlled",
                    summon_model={
                        "kind": "meteor_recombined_form",
                        "parent": root["id"],
                    },
                )
                adult["meteor_adult_model"] = {
                    "root": root["id"],
                    "group_id": model["group_id"],
                    "level": model["level"],
                    "children": [child["actor"]["id"] for child in form["children"]],
                    "generated": True,
                }
                if adult["id"] in ids:
                    raise InputError(
                        "Generated Meteor form collides with an existing actor"
                    )
                ids.add(adult["id"])
                result.append(adult)
            for child in form["children"]:
                mite = deepcopy(child["actor"])
                if mite["id"] in ids:
                    raise InputError("Meteormite collides with an existing actor")
                ids.add(mite["id"])
                mite.update(
                    spawn_seconds="controlled",
                    x=root["x"],
                    y=root["y"],
                    summon_model={"kind": "meteor_mite", "parent": form["id"]},
                )
                mite["meteor_mite_model"] = {
                    "root": root["id"],
                    "adult_form": form["id"],
                    "group_id": model["group_id"],
                    "level": child["level"],
                    "source": child["source"],
                    "status": child["status"],
                }
                result.append(mite)
    return result


class MeteorGolemCombat:
    def __init__(
        self,
        actors,
        combat,
        can_release,
        transfer_statuses,
        *,
        capture_statuses=None,
        apply_status_receipt=None,
        has_target_override=None,
    ):
        if not callable(transfer_statuses):
            raise InputError(
                "Meteor forms require shared status transfer, including Angry targeting"
            )
        if (
            not callable(capture_statuses)
            or not callable(apply_status_receipt)
            or not callable(has_target_override)
        ):
            raise InputError(
                "Meteor requires capture/apply hooks for external actor-keyed spell/status ledgers; actor fields alone are insufficient"
            )
        self.capture_statuses = capture_statuses
        self.apply_status_receipt = apply_status_receipt
        self.has_target_override = has_target_override
        self.actors, self.combat, self.can_release, self.transfer_statuses = (
            actors,
            combat,
            can_release,
            transfer_statuses,
        )
        self.models = {
            key: deepcopy(actor["meteor_parameters"])
            for key, actor in actors.items()
            if "meteor_parameters" in actor
        }
        self.adults = {
            key: deepcopy(actor["meteor_adult_model"])
            for key, actor in actors.items()
            if "meteor_adult_model" in actor
        }
        self.mites = {
            key: deepcopy(actor["meteor_mite_model"])
            for key, actor in actors.items()
            if "meteor_mite_model" in actor
        }
        self.split, self.allocated, self.retired, self.pending, self.transitions = (
            set(),
            set(),
            set(),
            [],
            [],
        )
        self.transition_receipts = []
        group_levels = {}
        for key, model in self.adults.items():
            group = model["group_id"]
            if group in group_levels and group_levels[group] != model["level"]:
                raise InputError("A Meteor cohort cannot silently mix levels")
            group_levels[group] = model["level"]
            for child_id in model["children"]:
                if (
                    child_id not in self.mites
                    or self.mites[child_id]["adult_form"] != key
                ):
                    raise InputError(
                        "Meteor children must be preloaded with exact form ownership"
                    )

    def validate_command(self, command):
        if command.get("kind") == "deploy":
            for key in command.get("targets", []):
                if (
                    key in self.mites
                    or self.adults.get(key, {}).get("generated")
                    or key in self.split
                ):
                    raise InputError(
                        "Meteor generated/retired form identities cannot be independently deployed"
                    )

    def launch(self, actor, target, time, trace, flat_damage=None):
        key = actor["id"]
        if key not in self.adults or key in self.split or not _active(actor, time):
            raise InputError("Meteor split/throw requires a living unsplit adult form")
        model = self.models[self.adults[key]["root"]]
        # The ordinary declared projectile owns the throw's weapon damage. The
        # integrator must consume the ordinary cooldown once and avoid duplication.
        self.combat.launch(
            actor, target, self.actors, time, trace, flat_damage=flat_damage
        )
        self.split.add(key)
        fraction = actor["hp"] / actor["maximum_hp"]
        origin, landing = center(actor), center(target)
        distance = hypot(landing[0] - origin[0], landing[1] - origin[1])
        receipt = self._capture_transition(
            [actor], self.adults[key]["children"], time, "split_throw", fraction
        )
        for index, child_id in enumerate(self.adults[key]["children"]):
            position = origin if index == 0 else landing
            due = (
                time
                if index == 0
                else time
                + model["throw_release_delay_seconds"]
                + distance / model["throw_speed_tiles_per_second"]
            )
            self.pending.append(
                {
                    "actor": child_id,
                    "sources": [key],
                    "receipt": receipt,
                    "due": due,
                    "position": position,
                    "hp_fraction": fraction,
                    "reason": "split_local" if index == 0 else "throw_landing",
                }
            )
        actor["spawn_seconds"] = "controlled"
        actor["_meteor_form_retired"] = True
        event = {
            "time_seconds": time,
            "event": "meteor_split_throw",
            "source": key,
            "children": list(self.adults[key]["children"]),
        }
        trace.append(event)
        self.transitions.append(deepcopy(event))

    def select_target(
        self, actor, actors, time, blocked, width, height, ordinary_selector
    ):
        if actor["id"] not in self.mites:
            return ordinary_selector(actor, actors, time, blocked, width, height)
        if not _active(actor, time):
            return None, []
        actor.pop("_meteor_partner", None)
        selected, route = ordinary_selector(actor, actors, time, blocked, width, height)
        model = self.models[self.mites[actor["id"]]["root"]]
        if selected is not None and (
            self.has_target_override(actor, time)
            or target_distance(center(actor), selected)
            <= model["local_enemy_radius_tiles"]
        ):
            return selected, route
        group = self.mites[actor["id"]]["group_id"]
        partners = sorted(
            (
                hypot(
                    center(candidate)[0] - center(actor)[0],
                    center(candidate)[1] - center(actor)[1],
                ),
                key,
                candidate,
            )
            for key, candidate in actors.items()
            if key in self.mites
            and key != actor["id"]
            and key not in self.retired
            and self.mites[key]["group_id"] == group
            and _active(candidate, time)
        )
        for _, key, partner in partners:
            mover = dict(actor)
            mover["range"] = model["merge_range_tiles"]
            mover.pop("_route_signature", None)
            mover.pop("_remaining_path", None)
            partner_route = _ground_route(mover, partner, blocked, width, height)
            if partner_route is not None:
                actor["_meteor_partner"] = key
                return partner, partner_route
        return selected, route

    def _capture_transition(self, sources, target_ids, time, kind, hp_fraction):
        owners = sorted(
            {
                owner
                for actor in sources
                for owner in actor.get("_meteor_paid_owners", [actor["id"]])
            }
        )
        external = self.capture_statuses([actor["id"] for actor in sources], time)
        if not isinstance(external, dict):
            raise InputError(
                "External Meteor status capture must return an explicit receipt dictionary"
            )
        receipt = {
            "id": "meteor-transition:" + str(len(self.transition_receipts) + 1),
            "kind": kind,
            "time_seconds": time,
            "source_actor_ids": [actor["id"] for actor in sources],
            "target_actor_ids": list(target_ids),
            "paid_origin_actor_ids": owners,
            "hp_fraction": hp_fraction,
            "status_snapshots": deepcopy(sources),
            "external_status_snapshot": deepcopy(external),
        }
        self.transition_receipts.append(receipt)
        return receipt

    def _begin_merge(self, first_id, second_id, time, trace):
        first, second = self.actors[first_id], self.actors[second_id]
        group = self.mites[first_id]["group_id"]
        reserve_ids = sorted(
            key
            for key, model in self.adults.items()
            if model["generated"]
            and model["group_id"] == group
            and key not in self.allocated
        )
        if not reserve_ids:
            raise InputError(
                "Meteor finite recombination reserves exhausted; add explicit forms or reject this experiment"
            )
        adult_id = reserve_ids[0]
        self.allocated.add(adult_id)
        model = self.models[self.adults[adult_id]["root"]]
        fraction = (first["hp"] + second["hp"]) / (
            first["maximum_hp"] + second["maximum_hp"]
        )
        position = (
            (center(first)[0] + center(second)[0]) / 2,
            (center(first)[1] + center(second)[1]) / 2,
        )
        receipt = self._capture_transition(
            [first, second], [adult_id], time, "recombination", fraction
        )
        self.pending.append(
            {
                "actor": adult_id,
                "sources": [first_id, second_id],
                "receipt": receipt,
                "due": time + model["merge_delay_seconds"],
                "position": position,
                "hp_fraction": fraction,
                "reason": "recombination",
            }
        )
        for actor in (first, second):
            self.retired.add(actor["id"])
            actor["spawn_seconds"] = "controlled"
            actor["_meteor_form_retired"] = True
        event = {
            "time_seconds": time,
            "event": "meteor_merge_started",
            "sources": [first_id, second_id],
            "target": adult_id,
        }
        trace.append(event)
        self.transitions.append(deepcopy(event))

    def prepare(self, time, trace):
        for first_id in sorted(self.mites):
            first = self.actors[first_id]
            second_id = first.get("_meteor_partner")
            if (
                first_id in self.retired
                or second_id not in self.mites
                or second_id in self.retired
                or not _active(first, time)
                or not _active(self.actors[second_id], time)
            ):
                continue
            second = self.actors[second_id]
            if (
                second.get("_meteor_partner") != first_id
                or first.get("frozen_until", 0) > time
                or second.get("frozen_until", 0) > time
            ):
                continue
            model = self.models[self.mites[first_id]["root"]]
            if (
                hypot(
                    center(first)[0] - center(second)[0],
                    center(first)[1] - center(second)[1],
                )
                <= model["merge_range_tiles"] + EPSILON
            ):
                self._begin_merge(first_id, second_id, time, trace)
        waiting = []
        for item in self.pending:
            actor = self.actors[item["actor"]]
            x, y = item["position"]
            if item["due"] > time or not self.can_release(actor, x, y, time):
                waiting.append(item)
                continue
            if item["hp_fraction"] <= 0 or actor.get("death_time") is not None:
                raise InputError(
                    "Meteor form release cannot revive a dead or zero-HP identity"
                )
            actor.update(
                x=x,
                y=y,
                spawn_seconds=time,
                hp=actor["maximum_hp"] * min(item["hp_fraction"], 1),
                next_attack=time + actor["first_attack_seconds"],
            )
            if "_wall_next_attack" in actor:
                actor["_wall_next_attack"] = actor["next_attack"]
            # Read immutable transition-time actor snapshots. Later retirement or
            # source-keyed status cleanup cannot erase an already released Angry
            # assignment. The spell owner retains absolute expiry and cast IDs.
            self.transfer_statuses(
                deepcopy(item["receipt"]["status_snapshots"]), actor, time
            )
            self.apply_status_receipt(deepcopy(item["receipt"]), actor, time)
            actor["_meteor_paid_owners"] = list(
                item["receipt"]["paid_origin_actor_ids"]
            )
            actor["_meteor_lineage"] = list(item["sources"])
            event = {
                "time_seconds": time,
                "event": "meteor_form_release",
                "sources": list(item["sources"]),
                "target": actor["id"],
                "reason": item["reason"],
                "hp_fraction": item["hp_fraction"],
            }
            trace.append(event)
            self.transitions.append(deepcopy(event))
        self.pending = waiting

    def next_boundary(self, time):
        return min(
            (item["due"] for item in self.pending if item["due"] > time), default=None
        )

    def continuation_reasons(self, time):
        return [
            continuation_fact(
                "pending_release",
                "meteor:" + item["actor"],
                [item["actor"]],
                not_before_seconds=item["due"],
            )
            for item in self.pending
        ]

    def result(self):
        pending = [
            {key: deepcopy(value) for key, value in item.items() if key != "receipt"}
            for item in self.pending
        ]
        receipts = [
            {
                key: deepcopy(value)
                for key, value in receipt.items()
                if key not in {"status_snapshots", "external_status_snapshot"}
            }
            for receipt in self.transition_receipts
        ]
        return {
            "status": "EXPLICIT_UNCALIBRATED_METEOR_FORM_ARITHMETIC",
            "split_forms": sorted(self.split),
            "allocated_merge_forms": sorted(self.allocated),
            "retired_mites": sorted(self.retired),
            "pending": pending,
            "transition_receipts": receipts,
            "transitions": deepcopy(self.transitions),
        }
