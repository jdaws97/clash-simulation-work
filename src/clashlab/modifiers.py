"""Resolve an explicitly selected published battle-modifier profile.

The profile does not establish mode equivalence or validate an entity adapter.
Percent-of-maximum-HP weapon scaling is a separate, explicit caller policy.
"""

from .common import InputError, identifier, integer, number, require


ROLES = {"defense", "defending_hero", "guardian", "attacking_hero"}


def resolve_battle_modifiers(configuration, rules):
    profile_id = identifier(require(configuration, "profile_id"), "modifier profile")
    profiles = require(rules, "battle_modifier_profiles")
    if profile_id not in profiles:
        raise InputError(
            "Unknown battle modifier; no profile is inferred from Town Hall"
        )
    role = require(configuration, "entity_role")
    if role not in ROLES:
        raise InputError("Modifier role needs an explicit supported entity class")
    policy = require(configuration, "maximum_hp_damage_policy")
    if policy not in {"unchanged", "scale_with_damage"}:
        raise InputError("Percent-of-maximum-HP damage scaling must be explicit")
    policy_source = identifier(
        require(configuration, "policy_source"), "weapon scaling evidence"
    )
    profile = profiles[profile_id]
    selected = require(require(profile, "roles"), role)
    source = identifier(require(profile, "source"), "published modifier source")
    damage = number(require(selected, "damage_multiplier"), "mode damage multiplier", 0)
    hp = number(require(selected, "hitpoints_multiplier"), "mode HP multiplier", 0)
    equipment = require(profile, "equipment_level_reduction")
    for rarity in ("common", "epic"):
        integer(require(equipment, rarity), "equipment level reduction", 0)
    return {
        "status": "PUBLISHED_PROFILE_WITH_EXPLICIT_WEAPON_SCALING_POLICY",
        "profile_id": profile_id,
        "entity_role": role,
        "source": source,
        "checked_on": profile.get("checked_on", rules["retrieved_on"]),
        "source_published_on": profile.get("source_published_on"),
        "verification": profile.get("verification", "unspecified_profile_evidence"),
        "modifiers": {
            "hitpoints_multiplier": hp,
            "damage_multiplier": damage,
            "maximum_hp_damage_multiplier": (
                damage if policy == "scale_with_damage" else 1
            ),
            "attack_interval_multiplier": 1,
            "range_multiplier": 1,
            "movement_speed_multiplier": 1,
            "source": source,
        },
        "maximum_hp_damage_policy": policy,
        "policy_source": policy_source,
        "attacking_hero_equipment_level_reduction": dict(equipment),
        "equipment_statistic_reconciliation_required": role == "attacking_hero"
        and any(equipment.values()),
        "full_game_prediction": False,
        "limitations": [
            "The caller must select the actual battle profile; a TH level does not select a modifier",
            "Equipment reductions are reported separately and are not applied to unknown gear statistics or level floors",
            "Percent-of-maximum-HP weapon scaling follows the stated caller policy, not an inferred Monolith rule",
            "Friendly mode, active potions, client patch and replay equivalence still need recording",
        ],
    }
