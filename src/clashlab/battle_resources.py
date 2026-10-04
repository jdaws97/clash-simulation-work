"""Resource receipts clipped to the actual settled battle termination boundary."""

from copy import deepcopy

from .battle_termination import EPSILON, USER_DEPLOYABLE_ORIGINS
from .common import InputError, number, require


def battle_resource_use(bindings, combat, elapsed):
    """Retain deployment history when a pet later becomes controlled underground."""
    number(elapsed, "resource accounting elapsed time", 0)
    actors = require(combat, "actors")
    pets = combat.get("hero_pets", {}).get("pets", {})
    reinforcements = combat.get("sieges", {}).get("reinforcements")
    payload_members = reinforcements["members"] if reinforcements is not None else {}
    deployment_times = {}
    for actor_id, binding in bindings["attacker_bindings"].items():
        if actor_id not in actors:
            raise InputError("Resource accounting is missing its bound attacker")
        origin = binding["origin"]
        if origin in USER_DEPLOYABLE_ORIGINS:
            deployed_at = bindings["planned_deployments"].get(actor_id)
        elif origin == "assigned_hero_pet":
            if actor_id not in pets:
                raise InputError(
                    "Pet resource accounting needs its deployment lifecycle"
                )
            deployed_at = pets[actor_id]["deployed_at"]
        elif origin == "clan_castle_troops":
            if actor_id not in payload_members:
                raise InputError(
                    "Payload resource accounting needs its release lifecycle"
                )
            deployed_at = payload_members[actor_id]["released_at"]
        else:
            raise InputError("Resource accounting requires a supported bound origin")
        if deployed_at is not None:
            number(deployed_at, "resource deployment time", 0)
        deployment_times[actor_id] = (
            deployed_at
            if deployed_at is not None and deployed_at <= elapsed + EPSILON
            else None
        )
    result = {
        "deployed_attacker_ids": sorted(
            actor_id for actor_id, time in deployment_times.items() if time is not None
        ),
        "undeployed_attacker_ids": sorted(
            actor_id for actor_id, time in deployment_times.items() if time is None
        ),
        "deployment_times_seconds": deployment_times,
        "spell_slots": [
            {
                **deepcopy(binding),
                "spent": binding["cast"] is not None
                and binding["cast"]["time_seconds"] <= elapsed + EPSILON,
            }
            for binding in bindings["spell_bindings"]
        ],
        "used_hero_ability_ids": sorted(
            {
                event["hero_id"]
                for event in combat["trace"]
                if event.get("event") == "hero_ability"
                and event["status"] == "activated"
                and event["time_seconds"] <= elapsed + EPSILON
            }
        ),
    }
    if reinforcements is not None:
        group = reinforcements["group"]
        delivered_at = group["delivery_time"]
        spent = delivered_at is not None and delivered_at <= elapsed + EPSILON
        result["clan_castle_delivery"] = {
            "spent": spent,
            "time_seconds": delivered_at if spent else None,
            "reason": group["delivery_reason"] if spent else None,
            "pending_member_ids": sorted(group["remaining"]),
        }
    return result
