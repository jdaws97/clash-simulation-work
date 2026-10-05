"""Reproduce a bound 320-space army benchmark against a declared TH16 inventory.

This is a development fixture, not a recommended army or a complete modern base.
It intentionally uses no heroes, pets, siege or Clan Castle contents so that all
declared resources have implemented runtime behavior.
"""

from collections import Counter
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.catalog import Catalog
from clashlab.common import read_json, write_json
from clashlab.sweeper_rules import RULES, SCOPE
from clashlab.full_battle import simulate_full_battle

from build_engine_lab import SOURCE, entity, ground_troop, passive, scenario


def town_hall():
    hall = entity("hall", "town-hall", 16, "defense", 33, 19)
    hall.update(
        mode="gigaInferno",
        statistics_mode="weapon",
        attack_parameters={
            **hall["attack_parameters"],
            "allocation": "distinct_targets_only",
        },
        town_hall_parameters={
            "source": SOURCE,
            "weapon_level": 1,
            "activation": {
                "source": SOURCE,
                "initial_state": "dormant",
                "destruction_threshold_fraction": 0.51,
                "activation_delay_seconds": 0,
            },
            "death": {
                "source": SOURCE,
                "blast_delay_seconds": 1,
                "blast_damage_multiplier": 1,
                "blast_radius_multiplier": 1,
                "poison_delay_seconds": 1,
                "poison_radius_tiles": 4.5,
                "poison_max_dps_multiplier": 1,
                "poison_duration_multiplier": 1,
                "pulse_interval_seconds": 0.5,
                "first_pulse_offset_seconds": 0,
                "growth_by_field_age": [{"after_seconds": 0, "dps_multiplier": 1}],
                "exit_linger_seconds": 0,
                "protection_policy": "damage_immunity_does_not_block_status",
                "excluded_classes": ["siege"],
            },
        },
    )
    return hall


def make_army():
    return {
        "troops": [
            {"id": "giant", "level": 11, "count": 8},
            {"id": "hog-rider", "level": 12, "count": 8},
            {"id": "wizard", "level": 11, "count": 10},
            {"id": "pekka", "level": 10, "count": 8},
        ],
        "spells": [
            {"id": "healing-spell", "level": 9, "count": 3},
            {"id": "freeze-spell", "level": 7, "count": 5},
        ],
        "heroes": [],
        "siege": None,
        "clan_castle": {"troops": [], "spells": []},
    }


def troops_and_deployments(army, catalog):
    troops = []
    commands = []
    for group, item in enumerate(army["troops"]):
        positions = {}
        for ordinal in range(item["count"]):
            actor_id = f"{item['id']}-{ordinal + 1}"
            x, y = 0.5, 7.5 + 2.5 * ordinal
            troop = ground_troop(
                actor_id,
                item["id"],
                item["level"],
                x,
                y,
                catalog.entity(item["id"])["range"],
            )
            troop["spawn_seconds"] = "controlled"
            if item["id"] == "hog-rider":
                troop["wall_parameters"] = {
                    "kind": "jump_enemy_walls",
                    "source": SOURCE,
                }
            if item["id"] == "wizard":
                troop["wall_parameters"] = {"kind": "avoid", "source": SOURCE}
                troop["attack_parameters"].update(radius=1.5)
                troop["attack_parameters"]["projectile"].update(
                    inactive_primary_policy="fizzle"
                )
                troop["wizard_parameters"] = {
                    "source": SOURCE,
                    "splash_layer_policy": "all_declared_target_layers",
                }
            troops.append(troop)
            positions[actor_id] = {"x": x, "y": y}
        commands.append(
            {
                "id": f"deploy-{item['id']}",
                "kind": "deploy",
                "time_seconds": group * 2,
                "targets": list(positions),
                "positions": positions,
            }
        )
    return troops, commands


def defenders(catalog):
    reference = scenario(catalog, "none")
    prototypes = {
        item["entity"]: item
        for item in reference["entities"]
        if item["entity"] in {"cannon", "inferno-tower", "x-bow"}
    }
    result = [town_hall()]
    placements = {
        "cannon": [(x, y) for y in (5, 12) for x in (12, 19, 26)],
        "inferno-tower": [(x, 19) for x in (12, 19, 26)],
        "x-bow": [(x, 26) for x in (12, 19, 26, 33)],
    }
    for name, points in placements.items():
        for index, (x, y) in enumerate(points):
            actor = deepcopy(prototypes[name])
            actor.update(id=f"{name}-{index + 1}", x=x, y=y)
            result.append(actor)
    for index, y in enumerate((6, 14, 22, 30)):
        result.append(passive(f"storage-{index + 1}", "gold-storage", 17, 5, y))
    for y in range(4, 37):
        if y not in {14, 15, 24, 25}:
            result.append(passive(f"wall-{y}", "wall", 17, 10, y))
    return result


def spell_casts():
    healing = []
    for index, (time, x, y) in enumerate(((20, 16, 17), (40, 26, 22))):
        healing.append(
            {
                "id": f"heal-{index + 1}",
                "entity": "healing-spell",
                "level": 9,
                "town_hall": 16,
                "time_seconds": time,
                "x": x,
                "y": y,
                "parameters": {
                    "source": SOURCE,
                    "first_pulse_delay_seconds": 0.1,
                    "amount_multiplier": 1,
                    "radius_multiplier": 1,
                    "pulse_interval_multiplier": 1,
                    "target_team": "attack",
                    "target_layers": ["ground", "air"],
                },
            }
        )
    freezing = []
    for index, (time, x, y) in enumerate(((15, 13, 20), (30, 20, 20), (50, 34, 21))):
        freezing.append(
            {
                "id": f"freeze-{index + 1}",
                "entity": "freeze-spell",
                "level": 7,
                "town_hall": 16,
                "time_seconds": time,
                "x": x,
                "y": y,
                "parameters": {
                    "source": SOURCE,
                    "duration_multiplier": 1,
                    "radius_multiplier": 1,
                    "caster_team": "attack",
                },
            }
        )
    return healing, freezing


def build_case(catalog, army, profile):
    scene = scenario(catalog, "none")
    troops, commands = troops_and_deployments(army, catalog)
    buildings = defenders(catalog)
    healing, freezing = spell_casts()
    scene.update(
        id=f"bound-th16-development-{profile}",
        scope=SCOPE,
        model_rules=deepcopy(RULES),
        buff_spells=[],
        width=44,
        height=44,
        duration_seconds=180,
        maximum_step_seconds=0.1,
        recording_interval_seconds=1,
        entities=[*troops, *buildings],
        effects=commands,
        healing_spells=healing,
        freeze_spells=freezing,
    )
    scene["traps"][0].update(x=17, y=17)
    placements = []
    for instance in [*buildings, *scene["traps"]]:
        placement = {
            "instance": instance["id"],
            "id": instance["entity"],
            "level": instance["level"],
            "x": instance["x"],
            "y": instance["y"],
            "counts_for_destruction": instance.get("counts_for_destruction", False),
        }
        if "mode" in instance and instance["mode"] != "passive":
            placement["mode"] = instance["mode"]
        placements.append(placement)
    layout = {
        "id": "underfilled-th16-development-inventory",
        "width": 44,
        "height": 44,
        "town_hall": 16,
        "inventory": dict(Counter(item["id"] for item in placements)),
        "buildings": placements,
    }
    specification = {
        "id": scene["id"],
        "source": SOURCE,
        "time_limit_seconds": 180,
        "entity_scene": scene,
        "battle_modifier_policy": {
            "profile_id": profile,
            "policy_source": SOURCE,
            "maximum_hp_damage_policy": "unchanged",
            "trap_damage_policy": "unchanged",
            "death_damage_policy": "unchanged",
            "impact_hazard_damage_policy": "unchanged",
            "equipment_aura_damage_policy": "unchanged",
            "hero_summon_statistics_policy": "unchanged",
            "healing_and_status_policy": "unchanged",
        },
    }
    return specification, layout


def main():
    catalog = Catalog.load(ROOT / "data")
    account = read_json(ROOT / "profiles/sample-th16.json")
    army = make_army()
    destination = ROOT / "reports/bound-battle"
    destination.mkdir(parents=True, exist_ok=True)
    write_json(destination / "army.json", army)
    summaries = []
    for profile in ("none", "legend_i"):
        specification, layout = build_case(catalog, army, profile)
        write_json(destination / f"{profile}-input.json", specification)
        write_json(destination / "layout.json", layout)
        result = simulate_full_battle(
            specification,
            account,
            army,
            layout,
            catalog,
            mode_rules=read_json(ROOT / "data/mode-rules.json"),
        )
        write_json(destination / f"{profile}-result.json", result)
        summaries.append(
            {
                "profile": profile,
                "outcome": result["outcome"],
                "resources": result["resource_use"],
                "army_validation": result["validation"]["army"],
            }
        )
        print(profile, result["outcome"])
    write_json(
        destination / "summary.json",
        {
            "status": "DEVELOPMENT_BENCHMARK_NOT_ARMY_OR_BASE_RECOMMENDATION",
            "army_housing": 320,
            "spell_housing": 11,
            "declared_inventory_is_maximal": False,
            "heroes_siege_pets_castles_selected": False,
            "cases": summaries,
        },
    )


if __name__ == "__main__":
    main()
