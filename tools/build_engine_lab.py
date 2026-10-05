"""Build a compact, reproducible animation of the connected combat mechanics."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.adapters import compile_entity_scene
from clashlab.catalog import Catalog
from clashlab.common import read_json, write_json
from clashlab.extracted_branch import build_extracted_branch
from clashlab.hit_status import RULES, SCOPE
from clashlab.modifiers import resolve_battle_modifiers
from clashlab.spatial import simulate_spatial


SOURCE = "declared-connected-mechanics-example-not-replay-calibration"


def entity(instance_id, name, level, team, x, y):
    return {
        "id": instance_id,
        "entity": name,
        "level": level,
        "town_hall": 16,
        "mode": "normal",
        "statistics_mode": "normal",
        "supercharge": False,
        "team": team,
        "counts_for_destruction": team == "defense",
        "x": x,
        "y": y,
        "spawn_seconds": 0,
        "first_attack_seconds": 0,
        "modifiers": {
            "hitpoints_multiplier": 1,
            "damage_multiplier": 1,
            "maximum_hp_damage_multiplier": 1,
            "attack_interval_multiplier": 1,
            "range_multiplier": 1,
            "movement_speed_multiplier": 1,
            "source": SOURCE,
        },
        "attack_parameters": {
            "projectile": {
                "timing": "instant",
                "delay_seconds": 0,
                "destination": "locked_actor_center_at_impact",
                "hit_radius": 0,
            }
        },
    }


def ground_troop(instance_id, name, level, x, y, attack_range):
    troop = entity(instance_id, name, level, "attack", x, y)
    troop["wall_parameters"] = {
        "kind": "clear_obstructions",
        "source": SOURCE,
        "route_cost": "travel_seconds_plus_nominal_clearance",
        "cooldown": "shared_with_main_weapon",
        "range": attack_range,
        "first_attack_seconds": 0,
        "impact_timing": "instant",
    }
    return troop


def passive(instance_id, name, level, x, y):
    building = entity(instance_id, name, level, "defense", x, y)
    building.update(
        mode="passive",
        statistics_mode="none",
        attack_parameters={},
        inactive_attack_interval_seconds=1,
        counts_for_destruction=name != "wall",
    )
    return building


def scenario(catalog, profile_id):
    root = ground_troop("root", "root-rider", 3, 2.5, 10.5, 1)
    root["wall_parameters"].update(
        kind="penetrate_obstructions",
        cooldown="independent_from_main_weapon",
        range=0,
    )
    ice = ground_troop("ice", "ice-golem", 8, 1.5, 11.5, 1)
    ice["ice_parameters"] = {
        "source": SOURCE,
        "on_hit_slow": {
            "source": SOURCE,
            "duration_seconds": 2,
            "attack_rate_multiplier": 0.25,
            "movement_multiplier": 1,
            "protection_policy": "damage_immunity_does_not_block_status",
        },
        "death_delay_seconds": 0,
        "death_radius_multiplier": 1,
        "death_duration_multiplier": 1,
        "death_target_kinds": ["defense", "building"],
        "death_target_layers": ["ground"],
    }
    troops = [
        root,
        ice,
        ground_troop("thrower-a", "thrower", 2, 0.5, 8.5, 6),
        ground_troop("thrower-b", "thrower", 2, 0.5, 13.5, 6),
    ]
    for troop in troops[2:]:
        troop["wall_parameters"] = {"kind": "avoid", "source": SOURCE}
    cannon = entity("cannon", "cannon", 21, "defense", 12, 8)
    inferno = entity("inferno", "inferno-tower", 10, "defense", 18, 8)
    inferno["ramp_parameters"] = {
        "source": SOURCE,
        "clock_start": "first_weapon_launch",
        "freeze_policy": "reset",
        "protected_target_policy": "continue",
        "middle_stage_after_seconds": 1.5,
        "maximum_stage_after_seconds": 5.25,
        "timing_source": SOURCE,
    }
    xbow = entity("xbow", "x-bow", 10, "defense", 14, 14)
    defenses = [cannon, inferno, xbow]
    modifiers = resolve_battle_modifiers(
        {
            "profile_id": profile_id,
            "entity_role": "defense",
            "maximum_hp_damage_policy": "unchanged",
            "policy_source": SOURCE,
        },
        read_json(ROOT / "data/mode-rules.json"),
    )
    for defense in defenses:
        defense["modifiers"] = deepcopy(modifiers["modifiers"])
    walls = [passive(f"wall-{y}", "wall", 17, 8, y) for y in range(6, 17)]
    storage = passive("storage", "gold-storage", 17, 23, 10)
    specification = {
        "id": f"connected-ground-sector-{profile_id}",
        "scope": SCOPE,
        "model_rules": deepcopy(RULES),
        "statistics_policy": {
            "kind": "conditional_pinned_snapshot",
            "snapshot_commit": catalog.snapshot["snapshotCommit"],
        },
        "unit_conventions": {
            "movement_units_per_tile": 8,
            "catalog_attack_speed_unit": "seconds_per_hit",
            "source": SOURCE,
        },
        "unsupported_mechanics": [],
        "width": 28,
        "height": 22,
        "duration_seconds": 45,
        "maximum_step_seconds": 0.05,
        "recording_interval_seconds": 0.25,
        "entities": [*troops, *defenses, *walls, storage],
        "effects": [],
        "healing_stacking": {"source": SOURCE, "groups": {}},
        "healing_spells": [],
        "persistent_hazards": [],
        "target_scoring": {
            "selection": "arrival_time_then_footprint_distance",
            "source": SOURCE,
        },
        "traps": [
            {
                "id": "giant-bomb",
                "entity": "giant-bomb",
                "level": 10,
                "town_hall": 16,
                "team": "defense",
                "x": 10,
                "y": 10,
                "parameters": {
                    "source": SOURCE,
                    "arming_seconds": 0,
                    "delay_seconds": 0.5,
                    "projectile_speed_tiles_per_second": None,
                    "damage_multiplier": 1,
                    "trigger_radius_multiplier": 1,
                    "damage_radius_multiplier": 1,
                    "excluded_trigger_entities": [],
                    "excluded_damage_entities": [],
                    "dead_trigger_policy": "fizzle",
                },
            }
        ],
    }
    if "statistic_branch" in catalog.snapshot:
        specification["statistics_policy"].update(
            kind="conditional_extracted_fields",
            branch_policy=catalog.snapshot["statistic_branch"]["policy"],
        )
    return specification


def main():
    output = ROOT / "reports/engine-lab"
    output.mkdir(parents=True, exist_ok=True)
    base_catalog = Catalog.load(ROOT / "data")
    provenance = read_json(ROOT / "data/clashking-static-source.json")
    raw_bytes = (ROOT / "data/clashking-static-data.json").read_bytes()
    if hashlib.sha256(raw_bytes).hexdigest() != provenance["sha256"]:
        raise ValueError("Extracted source bytes do not match their pinned provenance")
    selected_catalog = build_extracted_branch(
        base_catalog,
        json.loads(raw_bytes),
        provenance,
        read_json(ROOT / "data/extracted-stat-selection.json"),
    )
    cases = []
    for source_name, catalog in (
        ("original", base_catalog),
        ("selected-extraction", selected_catalog),
    ):
        for profile in ("none", "legend_i"):
            specification = scenario(catalog, profile)
            case_id = f"{source_name}-{profile}"
            compiled = compile_entity_scene(specification, catalog)
            result = simulate_spatial(compiled["scene"])
            write_json(output / f"{case_id}-input.json", specification)
            write_json(output / f"{case_id}-trace.json", result)
            actors = {
                actor["id"]: {
                    **{
                        key: actor[key]
                        for key in ("kind", "team", "width", "height", "hitpoints")
                    },
                    "entity": actor["entity_adapter"]["entity"],
                }
                for actor in compiled["scene"]["actors"]
            }
            cases.append(
                {
                    "id": case_id,
                    "source": source_name,
                    "modifier": profile,
                    "width": specification["width"],
                    "height": specification["height"],
                    "duration": specification["duration_seconds"],
                    "actors": actors,
                    "traps": compiled["scene"]["traps"],
                    "frames": result["frames"],
                    "events": [
                        event
                        for event in result["trace"]
                        if event.get("event")
                        in {
                            "trap_trigger",
                            "trap_impact",
                            "hit_status_apply",
                            "death_effect_release",
                            "death_effect_impact",
                        }
                    ],
                    "summary": {
                        "remaining_troop_hp": round(
                            sum(
                                actor["hp"]
                                for actor in result["actors"].values()
                                if actor["team"] == "attack"
                            ),
                            1,
                        ),
                        "structures_destroyed": sum(
                            actor["hp"] == 0
                            for actor in result["actors"].values()
                            if actor["counts_for_destruction"]
                        ),
                        "counted_structures": sum(
                            actor["counts_for_destruction"]
                            for actor in result["actors"].values()
                        ),
                        "trap_triggers": len(result["traps"]["triggered"]),
                        "ice_death_time": result["actors"]["ice"]["death_time"],
                    },
                }
            )
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "CONTROLLED_SECTOR_MECHANICS_NOT_COMPLETE_ARMY_OR_VILLAGE",
        "full_game_prediction": False,
        "cases": cases,
        "selected_source": provenance,
        "statistics_branch": selected_catalog.snapshot["statistic_branch"],
        "assumptions": [
            "Four troops and a small declared defense sector; this is not a legal complete army or a full village.",
            "Ice Golem chill uses a declared 75% attack-rate reduction for 2 seconds; the timing and freeze geometry still require replay calibration.",
            "Legend I changes defense weapon damage by the published profile; trap damage scaling is held at 1 in this experiment.",
            "Weapons use instantaneous hits and the existing four-neighbor routing model; the animation is recorded solver output.",
            "No stars, triple probabilities or recommended layouts are inferred from this small sector.",
        ],
    }
    template = (ROOT / "tools/engine_lab.html").read_text(encoding="utf-8")
    encoded = json.dumps(report, ensure_ascii=True, separators=(",", ":")).replace(
        "<", "\\u003c"
    )
    (output / "index.html").write_text(
        template.replace("__LAB_DATA__", encoded), encoding="utf-8"
    )
    write_json(
        output / "summary.json",
        {key: value for key, value in report.items() if key != "cases"}
        | {
            "cases": [
                {
                    key: value
                    for key, value in case.items()
                    if key not in {"frames", "actors", "traps", "events"}
                }
                for case in cases
            ]
        },
    )
    print(
        json.dumps([{"id": case["id"], **case["summary"]} for case in cases], indent=2)
    )


if __name__ == "__main__":
    main()
