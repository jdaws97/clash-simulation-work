"""Explicit synthetic coverage recipes, not account loadouts or recommendations."""

from copy import deepcopy

from .attack_spell_rules import RULES, SCOPE
from .common import InputError
from .development_armies import benchmark_army, build_army_scene, _bind_responses
from .development_village import padded_layout, termination_policy
from .higher_town_halls import maximum_level
from .layout_battle_bridge import build_layout_scene
from .layout_evaluation import candidate_layout_sha256
from .planning import planning_account


def synthetic_attacker(template, catalog, town_hall, mode):
    account = deepcopy(template)
    if account.get("provenance", {}).get("synthetic") is not True:
        raise InputError(
            "Coverage generation requires a synthetic account, never a real profile"
        )
    account.update(
        id=f"synthetic-layout-ensemble-th{town_hall}",
        town_hall=town_hall,
        laboratory_level=maximum_level(catalog, "laboratory", town_hall),
    )
    castle = catalog.level(
        "clan-castle", maximum_level(catalog, "clan-castle", town_hall)
    )
    camp = catalog.level("army-camp", maximum_level(catalog, "army-camp", town_hall))
    camps = next(
        r["count"]
        for r in catalog.entity("army-camp")["availablePerTownHall"]
        if r["townHallLevel"] == town_hall
    )
    account["capacities"].update(
        army_housing=camp["housingSpace"] * camps,
        clan_castle_troops=castle["troopCapacity"],
        clan_castle_spells=castle["spellCapacity"],
        clan_castle_siege_storage=castle["siegeMachineCapacity"],
    )
    account["provenance"][
        "design"
    ] = "Synthetic per-TH camp/Lab/Castle caps; explicit benchmark equipment; not a player or current meta distribution"
    return planning_account(
        account,
        catalog,
        {
            "mode": mode,
            "recipient_level_rule": "unique_capacity_match",
            "super_troops": [],
        },
    )


def prepare_case(
    case,
    original,
    catalog,
    template,
    base_policies,
    army_policies,
    crafted_policy,
    mask_policy,
):
    layout = padded_layout(original)
    if case["candidate_id"] != original.get("candidate_id"):
        raise InputError("Case candidate label differs from source layout")
    if case.get("candidate_layout_sha256") != candidate_layout_sha256(layout):
        raise InputError("Register the canonical padded layout before preparing a case")
    account = synthetic_attacker(
        template, catalog, case["attacker_town_hall"], case["mode"]
    )
    army = benchmark_army(account, army_policies, case["family"])
    # Keep the established recipe identities/quantities: any capacity shortfall
    # is disclosed, not silently called a max-strength higher-TH army.
    # The legacy builder compiles heroes once solely to enumerate Mirror IDs
    # before it exposes a scene, and hardcodes TH16 on those temporary actors.
    # Use supported TH16 hero levels for that assembly-only pass, then restore
    # exact selected levels/TH before any authoritative compilation or scoring.
    assembly_army = deepcopy(army)
    for hero in assembly_army["heroes"]:
        hero["level"] = min(hero["level"], maximum_level(catalog, hero["id"], 16))
    scene = build_army_scene(
        layout,
        catalog,
        base_policies,
        army_policies,
        account,
        assembly_army,
        SCOPE,
        RULES,
        180,
    )
    defensive = build_layout_scene(
        layout, catalog, base_policies, crafted_policy, SCOPE, RULES, 180
    )
    attackers = [a for a in scene["entities"] if a["team"] == "attack"]
    hero_levels = {h["id"]: h["level"] for h in army["heroes"]}
    scene["entities"] = attackers + [
        a for a in defensive["entities"] if a["team"] == "defense"
    ]
    scene["traps"] = defensive["traps"]
    scene["attacking_reinforcements"]["receiver_town_hall"] = account["town_hall"]
    for actor in attackers:
        actor["town_hall"] = account["town_hall"]
        if actor["entity"] in hero_levels:
            actor["level"] = hero_levels[actor["entity"]]
    for pet in scene["pets"]:
        pet["town_hall"] = account["town_hall"]
    for collection in ("buff_spells", "freeze_spells"):
        for spell in scene[collection]:
            spell["town_hall"] = account["town_hall"]
    # Whole attack-plan reflection changes deployment/spell coordinates, not the
    # defender layout or directional settings. Receipts name this exact policy.
    if case["entry_policy"] not in {"west", "east"}:
        raise InputError("Coverage recipes currently implement west/east entry")
    if case["entry_policy"] == "east":
        for actor in attackers:
            actor["x"] = layout["width"] - actor["x"]
        for command in scene["effects"]:
            for point in command.get("positions", {}).values():
                point["x"] = layout["width"] - point["x"]
        for collection in ("buff_spells", "freeze_spells"):
            for spell in scene[collection]:
                spell["x"] = layout["width"] - spell["x"]
        for region in scene["attacking_reinforcements"]["deployment_policy"]["regions"]:
            region["left"], region["right"] = (
                layout["width"] - region["right"],
                layout["width"] - region["left"],
            )
    if case["ability_policy"] not in {"scheduled", "delayed_5s"}:
        raise InputError("Unknown ability policy")
    if case["ability_policy"] == "delayed_5s":
        for command in scene["effects"]:
            if command["kind"] == "hero_ability":
                command["time_seconds"] += 5
    _bind_responses(scene, attackers, scene["pets"], catalog)
    # A higher-TH Giga Bomb cannot retain the legacy dragon-only roster.
    # Its remaining family response model needs the integration owner's contract.
    if any(t["entity"] == "giga-bomb" for t in scene["traps"]):
        raise InputError(
            "Higher-TH mixed-army Giga Bomb response contract missing; do not retain legacy dragon-only weights"
        )
    scene["attack_spells"] = []
    specification = {
        "id": case["id"],
        "source": army_policies["source"],
        "time_limit_seconds": 180,
        "entity_scene": scene,
        "termination_policy": termination_policy(army, base_policies),
        "battle_modifier_policy": {
            "profile_id": "legend_i" if case["mode"] == "ranked" else "none",
            "policy_source": army_policies["source"],
            **{
                k: "unchanged"
                for k in (
                    "maximum_hp_damage_policy",
                    "trap_damage_policy",
                    "death_damage_policy",
                    "impact_hazard_damage_policy",
                    "equipment_aura_damage_policy",
                    "hero_summon_statistics_policy",
                    "healing_and_status_policy",
                )
            },
        },
    }
    return {
        "case": case,
        "layout": layout,
        "account": account,
        "army": army,
        "specification": specification,
        "deployment_policy": mask_policy,
        "assumptions": [
            "Synthetic fixed benchmark quantities; higher-TH army housing may be underfilled",
            "No opponent population weights",
            "Spell coordinates reflect with entry; ability schedule is fixed or +5 seconds",
            "Padded open board and static initial deployment mask are hypotheses",
            "Held-out entry/policy cases are synthetic robustness checks, not replay calibration",
            "Original user V3 and screenshot are not generator inputs",
            *army_policies["limitations"],
        ],
    }
