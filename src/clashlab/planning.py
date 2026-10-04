"""Derive explicit planned activations and recipient-specific reinforcement caps."""

from .boosts import effective_account
from .common import InputError, integer, require


def planning_account(account, catalog, specification):
    permissions = require(account, "planning_permissions")
    if require(permissions, "any_legal_reinforcement") is not True:
        raise InputError(
            "The unrestricted reinforcement planning policy is unconfirmed"
        )
    result = effective_account(account, catalog, require(specification, "mode"))
    capacities = account["capacities"]
    if require(specification, "recipient_level_rule") != "unique_capacity_match":
        raise InputError("Recipient level must use the explicit unique-capacity rule")
    matches = [
        row
        for row in catalog.entity("clan-castle")["levels"]
        if catalog.available("clan-castle", row["level"], account["town_hall"])
        and row["troopCapacity"] == require(capacities, "clan_castle_troops")
        and row["spellCapacity"] == require(capacities, "clan_castle_spells")
        and row["siegeMachineCapacity"]
        == require(capacities, "clan_castle_siege_storage")
    ]
    if len(matches) != 1:
        raise InputError(
            "Confirmed capacities do not uniquely identify the Clan Castle tier"
        )
    castle = matches[0]
    laboratory_cap = integer(require(castle, "labLevelCap"), "recipient Lab cap", 1)
    donation_levels = {}
    unverified_fields = []
    for entity_id in catalog.records:
        entity = catalog.entity(entity_id)
        if entity["category"] not in {"troop", "spell", "siege-machine"}:
            continue
        eligible = []
        for row in entity["levels"]:
            if row.get("supercharge"):
                continue
            source_row = row
            if entity.get("troopType") == "super":
                source_row = catalog.level(entity["parentTroop"], row["level"])
            laboratory = source_row.get("laboratoryRequired")
            if laboratory is None:
                unverified_fields.append({"entity": entity_id, "level": row["level"]})
                continue
            if laboratory <= laboratory_cap:
                eligible.append(row["level"])
        if eligible:
            donation_levels[entity_id] = max(eligible)
    result["donation_levels"] = donation_levels
    selected = require(specification, "super_troops")
    if len(selected) != len(set(selected)):
        raise InputError("Planned Super Troop activations must be unique")
    if selected and require(permissions, "any_legal_super_activation") is not True:
        raise InputError("Free selection of planned Super Troops is unconfirmed")
    if len(selected) > integer(
        require(capacities, "max_active_super_troops"), "Super Troop slots", 0
    ):
        raise InputError(
            "Planned activation exceeds the explicit Super Troop slot limit"
        )
    for entity_id in selected:
        entity = catalog.entity(entity_id)
        if entity.get("troopType") != "super":
            raise InputError(f"Activation is not a Super Troop: {entity_id}")
        parent_id = entity["parentTroop"]
        owned = integer(require(account["levels"], parent_id), "owned parent level", 0)
        if owned < entity["regularLevelRequired"]:
            raise InputError("A Power Potion cannot supply a missing activation unlock")
        parent_effective = require(result["levels"], parent_id)
        levels = [
            row["level"]
            for row in entity["levels"]
            if row["level"] <= parent_effective
            and catalog.available(entity_id, row["level"], account["town_hall"])
        ]
        if not levels:
            raise InputError(f"No supported planned activation level: {entity_id}")
        result["levels"][entity_id] = max(levels)
    result["active_super_troops"] = selected
    result["planning_evidence"] = {
        "recipient_clan_castle_level": castle["level"],
        "recipient_level_basis": (
            "Unique snapshot match of entered troop/spell/siege storage capacities "
            f"{capacities['clan_castle_troops']}/{capacities['clan_castle_spells']}/"
            f"{capacities['clan_castle_siege_storage']} at TH{account['town_hall']}"
        ),
        "recipient_lab_cap": laboratory_cap,
        "source": catalog.records["clan-castle"]["source"],
        "unverified_donation_lab_fields": unverified_fields,
        "status": "EXPLICIT_PLANNING_POLICY_WITH_UNVERIFIED_SNAPSHOT_CAPS",
        "current_activations_or_purchases_performed": False,
    }
    return result
