"""Attached Angry Jelly targeting override and finite separation lifecycle.

The pinned level supplies the duration. Attachment protection, early separation
on owner defeat and target invalidation are explicit experimental policies.
"""

from copy import deepcopy

from .common import InputError, identifier, number
from .spatial import center


POLICIES = {
    "experimental_policy": "jelly_attachment_v1_uncalibrated",
    "attachment": "inactive_pet_follows_owner_no_independent_damage_or_healing",
    "separation": "absolute_duration_or_owner_defeat_at_owner_center",
    "target_override": "defenses_before_buildings_invalidate_existing_primary",
    "owner_revival": "no_reattachment_or_duration_reset",
    "owner_recall": "absolute_expiry_separation_deferred_until_owner_returns",
}

PRIORITY_FIELDS = ("target_priorities", "target_priority_tiers", "_target_ranks")


def validate_behavior(behavior):
    if behavior != POLICIES:
        raise InputError(
            "Angry Jelly requires explicit experimental attachment policies"
        )


class JellyLifecycle:
    def __init__(self, actors):
        self.models = {}
        self.attached = {}
        self.finished = set()
        self.log = []
        for key, actor in actors.items():
            if actor.get("pet_model", {}).get("entity") != "angry-jelly":
                continue
            model = actor.get("jelly_model")
            if not isinstance(model, dict) or set(model) != {
                "source",
                "duration_seconds",
            }:
                raise InputError("Angry Jelly requires a pinned attachment duration")
            identifier(model["source"], "Jelly duration provenance")
            number(model["duration_seconds"], "Jelly attachment duration", 0)
            self.models[key] = model

    @staticmethod
    def _invalidate(actor):
        actor["target"] = None
        actor.pop("_path_signature", None)
        actor.pop("_remaining_path", None)

    def attach(self, pet_id, actors, states, time, trace):
        actor = actors[pet_id]
        owner = actors[actor["pet_model"]["hero_id"]]
        response = owner.get("defending_unit_response", {}).get("primary", "ignore")
        classes = {"defense", "building"}
        tiers = [["defense"], ["building"]]
        if response == "same_tier_as_buildings":
            classes.add("unit")
            tiers[1].append("unit")
        elif response == "after_buildings":
            classes.add("unit")
            tiers.append(["unit"])
        elif response != "ignore":
            raise InputError("Jelly override requires a bound defending-unit response")
        if set(owner["target_priorities"]) != classes:
            raise InputError(
                "Jelly override requires ordinary attacking hero target classes"
            )
        saved = {
            field: deepcopy(owner[field]) for field in PRIORITY_FIELDS if field in owner
        }
        self.attached[pet_id] = {
            "expires_at": time + self.models[pet_id]["duration_seconds"],
            "saved": saved,
        }
        owner["target_priority_tiers"] = tiers
        owner["target_priorities"] = [kind for tier in tiers for kind in tier]
        owner["_target_ranks"] = {
            kind: rank for rank, tier in enumerate(tiers) for kind in tier
        }
        self._invalidate(owner)
        actor["spawn_seconds"] = "controlled"
        states[pet_id]["phase"] = "attached"
        trace.append(
            {
                "time_seconds": time,
                "event": "jelly_attached",
                "pet": pet_id,
                "hero": owner["id"],
                "experimental": True,
            }
        )

    def prepare(self, actors, states, time, trace):
        for key, attachment in list(self.attached.items()):
            actor = actors[key]
            owner = actors[actor["pet_model"]["hero_id"]]
            actor["x"], actor["y"] = center(owner)
            if owner.get("_recalled", False) or actor.get("_recalled", False):
                continue
            if time < attachment["expires_at"] and owner["hp"] > 0:
                continue
            owner.update(attachment["saved"])
            for field in PRIORITY_FIELDS:
                if field not in attachment["saved"]:
                    owner.pop(field, None)
            self._invalidate(owner)
            actor["spawn_seconds"] = time
            actor["next_attack"] = time + actor["first_attack_seconds"]
            states[key]["phase"] = "active" if actor["hp"] > 0 else "dead"
            self.finished.add(key)
            del self.attached[key]
            entry = {
                "time_seconds": time,
                "event": "jelly_separated",
                "pet": key,
                "hero": owner["id"],
                "reason": "owner_defeat" if owner["hp"] <= 0 else "duration",
                "experimental": True,
            }
            trace.append(entry)
            self.log.append(deepcopy(entry))

    def next_boundary(self, time):
        values = [
            attachment["expires_at"]
            for attachment in self.attached.values()
            if attachment["expires_at"] > time
        ]
        return min(values) if values else None

    def result(self):
        return {"separations": self.log, "experimental": True, "game_calibrated": False}

    def continuation_reasons(self, actors):
        from .battle_termination import continuation_fact

        return [
            continuation_fact(
                "pending_release",
                f"pet:jelly:{key}",
                [key],
                not_before_seconds=attachment["expires_at"],
            )
            for key, attachment in self.attached.items()
            if not actors[key].get("_recalled", False)
            and not actors[actors[key]["pet_model"]["hero_id"]].get("_recalled", False)
            and actors[key]["hp"] > 0
        ]
