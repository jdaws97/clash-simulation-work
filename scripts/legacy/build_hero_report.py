"""Generate declared hero probes, preserving execution and context separately."""

import json
import sys
from copy import deepcopy
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.adapters import simulate_entity_closed_loop, simulate_entity_scene
from clashlab.catalog import Catalog
from clashlab.closed_loop import CONTROL_RULES
from clashlab.heroes import HERO_RULES, SCOPE


SOURCE = "declared-hero-study-not-current-game-or-player-calibration"


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def instance(identifier, entity, level, team, x, y):
    template = read(ROOT / "examples/entity-protection-sector-conditional.json")
    actor = deepcopy(template["entities"][0])
    actor.update(
        id=identifier,
        entity=entity,
        level=level,
        team=team,
        counts_for_destruction=team == "defense",
        x=x,
        y=y,
        first_attack_seconds=0,
    )
    return actor


def equipment(entity, level):
    parameters = {"source": SOURCE}
    if entity == "magic-mirror":
        parameters.update(
            clone_offsets=[{"dx": 0, "dy": -0.5}, {"dx": 0, "dy": 0.5}],
            clone_statistics="snapshot_clone_totals_without_equipment_hypothesis",
            source_death_policy="released_clones_persist_until_expiry",
            first_attack_delay_seconds=0,
        )
    elif entity == "rocket-spear":
        parameters["splash_layer_policy"] = "all_declared_target_layers"
    elif entity == "electro-boots":
        parameters.update(
            first_aura_pulse_delay_seconds=0.4,
            self_heal_interval_seconds=0.5,
            first_self_heal_delay_seconds=0.5,
            frozen_passives_policy="continue_while_frozen_hypothesis",
            aura_target_kinds=["defense", "building", "unit"],
            aura_target_layers=["ground", "air"],
        )
    elif entity in {"eternal-tome", "healing-tome"}:
        parameters.update(radius=3, membership="snapshot_at_activation")
        if entity == "healing-tome":
            parameters.update(
                membership="snapshot_at_activation_buff_follows_recipient",
                pulse_interval_seconds=0.5,
                first_pulse_delay_seconds=0.5,
                healing_multipliers_by_class={"troop": 1, "hero": 1},
            )
    return {"entity": entity, "level": level, "parameters": parameters}


def hero(entity, x=7.5, y=5.5):
    loadouts = {
        "archer-queen": ("queen", 95, [("invisibility-vial", 7), ("magic-mirror", 20)]),
        "royal-champion": ("royal", 45, [("rocket-spear", 21), ("electro-boots", 23)]),
        "grand-warden": ("warden", 70, [("eternal-tome", 18), ("healing-tome", 15)]),
    }
    identifier, level, items = loadouts[entity]
    actor = instance(identifier, entity, level, "attack", x, y)
    actor["mode"] = "ground"
    actor["hero_parameters"] = {
        "source": SOURCE,
        "equipment": [equipment(name, level) for name, level in items],
        "loadout_policy": "exact_two_equipment",
        "recovery_basis": "snapshot_base_and_equipment_recovery_on_activation_hypothesis",
        "activation_policy": "manual_only_controlled_probe",
        "pet_policy": "omitted_for_controlled_probe",
        "targeting_policy": (
            "independent_targeting_without_army_following_controlled_probe"
            if entity == "grand-warden"
            else "retained_building_targeting_hypothesis"
        ),
        "statistics_mapping": "base_and_equipment_additions_before_modifiers",
    }
    actor["wall_parameters"] = {
        "kind": "avoid" if entity == "archer-queen" else "jump_enemy_walls",
        "source": SOURCE,
    }
    return actor


def sector(catalog, identifier, actors, duration=12):
    return {
        "id": identifier,
        "scope": SCOPE,
        "model_rules": deepcopy(HERO_RULES),
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
        "width": 14,
        "height": 12,
        "duration_seconds": duration,
        "maximum_step_seconds": 0.05,
        "recording_interval_seconds": 0.1,
        "entities": actors,
        "effects": [],
        "healing_stacking": {"source": SOURCE, "groups": {}},
        "healing_spells": [],
        "persistent_hazards": [],
        "target_scoring": {
            "selection": "arrival_time_then_footprint_distance",
            "source": SOURCE,
        },
    }


def ability(identifier):
    return {
        "id": f"{identifier}-ability",
        "kind": "hero_ability",
        "hero_id": identifier,
        "time_seconds": 0,
    }


def response_inputs():
    plan = {
        "id": "synthetic-queen-half-health-response",
        "control_rules": deepcopy(CONTROL_RULES),
        "observation_interval_seconds": 0.1,
        "failed_action_transition": "advance",
        "resources": {"queen-ability": 1},
        "streams": [
            {
                "id": "queen",
                "steps": [
                    {
                        "all_conditions": [
                            {
                                "field": "active",
                                "actor_id": "queen",
                                "operator": "equals",
                                "value": True,
                            },
                            {
                                "field": "hp_fraction",
                                "actor_id": "queen",
                                "operator": "at_most",
                                "value": 0.5,
                            },
                        ],
                        "action": {
                            "id": "queen-ability",
                            "kind": "hero_ability",
                            "hero_id": "queen",
                            "recheck_conditions_on_execution": True,
                            "cost": {"queen-ability": 1},
                        },
                    }
                ],
            }
        ],
    }
    profiles = {}
    for name, latency in (("timely", 0.2), ("delayed", 3.5)):
        profiles[name] = {
            "plan_id": plan["id"],
            "observed_latency_traces": [
                {
                    "source_replay": f"synthetic-{name}-not-measured-player-evidence",
                    "responses": {
                        "queen-ability": {
                            "latency_seconds": latency,
                            "missed": False,
                            "placement_errors": {},
                        }
                    },
                }
            ],
        }
    return plan, profiles


def main():
    catalog = Catalog.load(ROOT / "data")
    plan, profiles = response_inputs()
    write(ROOT / "examples/entity-hero-queen-plan-synthetic.json", plan)
    for name, profile in profiles.items():
        write(ROOT / f"examples/entity-hero-queen-{name}-synthetic.json", profile)
    rows = []
    for context in ("monolith-only", "monolith-cannon"):
        actors = [
            hero("archer-queen"),
            instance("mono", "monolith", 3, "defense", 8, 4),
        ]
        if context == "monolith-cannon":
            actors.append(instance("cannon", "cannon", 21, "defense", 8, 8))
        spec = sector(catalog, f"queen-{context}-conditional", actors)
        write(ROOT / f"examples/entity-hero-queen-{context}-conditional.json", spec)
        for response, profile in profiles.items():
            for step in (0.1, 0.05, 0.025):
                spec["maximum_step_seconds"] = step
                result = simulate_entity_closed_loop(spec, catalog, plan, profile, 7, 1)
                sample = result["human_combat"]["samples"][0]
                combat = sample["combat"]
                filename = f"hero-queen-{context}-{response}-{str(step).replace('.', 'p')}.json"
                write(ROOT / "reports" / filename, result)
                rows.append(
                    {
                        "context": context,
                        "response": response,
                        "maximum_step_seconds": step,
                        "queen_hp": combat["actors"]["queen"]["hp"],
                        "queen_death_time": combat["actors"]["queen"]["death_time"],
                        "monolith_hp": combat["actors"]["mono"]["hp"],
                        "cannon_hp": combat["actors"].get("cannon", {}).get("hp"),
                        "ability_status": sample["control"]["actions"][0]["status"],
                        "cue_time_seconds": sample["control"]["actions"][0][
                            "cue_time_seconds"
                        ],
                        "execution_time_seconds": sample["control"]["actions"][0][
                            "time_seconds"
                        ],
                        "ability_resource_remaining": sample["control"][
                            "remaining_resources"
                        ]["queen-ability"],
                        "result": filename,
                    }
                )
    royal = hero("royal-champion", x=2.5)
    target = instance("target", "cannon", 21, "defense", 11, 4)
    target["first_attack_seconds"] = 1000
    target["modifiers"]["hitpoints_multiplier"] = 100
    spec = sector(catalog, "royal-range-conditional", [royal, target], duration=13)
    spec["effects"] = [ability("royal")]
    write(ROOT / "examples/entity-hero-royal-range-conditional.json", spec)
    write(ROOT / "reports/hero-royal-range.json", simulate_entity_scene(spec, catalog))
    archer = instance("near", "archer", 12, "attack", 6.5, 5.5)
    archer["wall_parameters"] = {"kind": "avoid", "source": SOURCE}
    spec = sector(
        catalog,
        "warden-membership-conditional",
        [hero("grand-warden"), archer],
        duration=1,
    )
    spec["effects"] = [ability("warden")]
    write(ROOT / "examples/entity-hero-warden-membership-conditional.json", spec)
    write(
        ROOT / "reports/hero-warden-membership.json",
        simulate_entity_scene(spec, catalog),
    )
    summary = {
        "status": "CONDITIONAL_HERO_CONTEXT_AND_RESPONSE_STUDY_NOT_GAME_PREDICTION",
        "full_game_prediction": False,
        "measured_player_latency": False,
        "automatic_hero_activation_modeled": False,
        "pet_behavior_modeled": False,
        "hero_levels": "TH16 strategic potion caps from the pinned profile",
        "equipment_levels": "Selected owned levels from the user's photographs",
        "loadout_is_optimal": False,
        "source": SOURCE,
        "cases": rows,
    }
    write(ROOT / "reports/hero-study.json", summary)
    table = "".join(
        "<tr>"
        + "".join(
            f"<td>{escape(str(row[key]))}</td>"
            for key in (
                "context",
                "response",
                "maximum_step_seconds",
                "ability_status",
                "cue_time_seconds",
                "execution_time_seconds",
                "queen_hp",
                "monolith_hp",
                "cannon_hp",
            )
        )
        + "</tr>"
        for row in rows
    )
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Hero response probes</title>
<style>body{{max-width:1100px;margin:36px auto;padding:0 20px;font:17px/1.6 system-ui;
background:#10151c;color:#e4eaf1}}a{{color:#86c7ff}}table{{border-collapse:collapse;width:100%}}
td,th{{padding:10px;text-align:left;border-bottom:1px solid #465468}}.scroll{{overflow:auto}}</style>
</head><body><p>Clash Lab: synthetic hero study</p>
<h1>Hero decisions depend on incoming pressure</h1>
<p>These controlled Queen95 probes use synthetic Invisibility Vial7 and Magic Mirror20 inputs.
The composition stays fixed while incoming defenses and response latency change.
The 0.2- and 3.5-second delays are synthetic inputs, not measurements of your execution.</p>
<p>Manual ability control is isolated here. Automatic activation and pets are absent.
This does not predict what would happen to an actual Queen left without a manual press.
Warden following behavior, traps, defending troops and full-battle outcomes remain unresolved.</p>
<div class="scroll"><table><thead><tr><th>Defenses</th><th>Response</th><th>Step (s)</th>
<th>Ability result</th><th>Cue (s)</th><th>Execution (s)</th><th>Queen HP</th>
<th>Monolith HP</th><th>Cannon HP</th></tr></thead>
<tbody>{table}</tbody></table></div>
<p>In this declared model the delayed press remains usable against the isolated Monolith,
but arrives after the Queen dies under crossfire. Additional damage also triggers the
half-health cue earlier, so remaining HP alone cannot rank defensive strength.</p>
<p>Solver-step comparisons check numerical sensitivity. They do not establish game accuracy,
tripling probability, or an optimal loadout. Actual equipment interactions still need replay calibration.</p>
<p><a href="hero-study.json">Cases and result files</a> ·
<a href="../build_hero_report.py">Reproduce the study</a></p></body></html>"""
    (ROOT / "reports/hero-study.html").write_text(page)
    print(f"Wrote {len(rows)} context/response/step cases and two equipment probes.")


if __name__ == "__main__":
    main()
