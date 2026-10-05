"""Compare explicit TH17 flame hypotheses and human Freeze response delays."""

import json
from copy import deepcopy
from html import escape
from pathlib import Path

from build_hero_report import ability, hero, instance, sector
from clashlab.adapters import simulate_entity_closed_loop
from clashlab.artillery import RULES, SCOPE
from clashlab.catalog import Catalog
from clashlab.closed_loop import CONTROL_RULES
from clashlab.spells import compile_freeze_spell


ROOT = Path(__file__).resolve().parent
SOURCE = "declared-artillery-study-not-current-game-or-player-calibration"
OFFICIAL_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/game-updates/"
    "the-town-hall-17-update-is-here-2/"
)
OVERLAP_POLICIES = {
    "maximum": "maximum_active_pool_dps_at_source_clock",
    "additive": "additive_independent_pool_clocks",
}


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def artillery_hall(overlap):
    hall = instance("hall", "town-hall", 17, "defense", 8, 4)
    hall.update(town_hall=17, mode="infernoArtillery", statistics_mode="weapon")
    hall["attack_parameters"] = {
        "allocation": "cycle_distinct_targets_to_fill_volley",
        "projectile": {
            "timing": "instant",
            "delay_seconds": 0,
            "destination": "locked_actor_center_at_impact",
            "hit_radius": 0,
            "inactive_primary_policy": "fizzle",
        },
    }
    hall["town_hall_parameters"] = {
        "source": SOURCE,
        "weapon_level": 5,
        "source_death_policy": "released_projectiles_and_pools_persist_hypothesis",
        "flame": {
            "source": SOURCE,
            "radius": 1.5,
            "duration_multiplier": 1,
            "maximum_dps_multiplier": 1,
            "growth_by_field_age": [{"after_seconds": 0, "dps_multiplier": 1}],
            "pulse_interval_seconds": 0.1,
            "first_pulse_offset_seconds": 0,
            "excluded_classes": ["siege"],
            "overlap_policy": OVERLAP_POLICIES[overlap],
            "pulse_clock_policy": "first_pool_then_continuous_while_any_pool_alive",
            "trigger_policy": "resolved_projectile_including_protected_primary",
            "pool_on_projectile_miss": True,
            "fizzle_policy": "no_pool_when_primary_fizzles",
            "source_freeze_policy": "released_pools_keep_pulsing_hypothesis",
        },
    }
    return hall


def charge_scene(catalog, overlap):
    royal = hero("royal-champion")
    storage = instance("storage", "gold-storage", 17, "defense", 16, 4)
    storage.update(
        town_hall=17,
        mode="passive",
        statistics_mode="none",
        attack_parameters={},
        inactive_attack_interval_seconds=1,
    )
    scene = sector(
        catalog,
        f"royal-artillery-{overlap}-conditional",
        [royal, artillery_hall(overlap), storage],
        duration=14,
    )
    scene.update(
        scope=SCOPE,
        model_rules=deepcopy(RULES),
        width=24,
        height=16,
        recording_interval_seconds=0.25,
        effects=[ability("royal")],
    )
    return scene


def response_inputs(catalog, cue_fraction):
    freeze = compile_freeze_spell(
        {
            "id": "hall-freeze",
            "entity": "freeze-spell",
            "level": 7,
            "town_hall": 16,
            "time_seconds": 0,
            "x": 10,
            "y": 6,
            "parameters": {
                "duration_multiplier": 1,
                "radius_multiplier": 1,
                "caster_team": "attack",
                "source": SOURCE,
            },
        },
        catalog,
    )
    freeze.pop("time_seconds")
    freeze.update(recheck_conditions_on_execution=True, cost={"freeze-casts": 1})
    plan = {
        "id": f"synthetic-royal-artillery-freeze-response-{cue_fraction}",
        "control_rules": deepcopy(CONTROL_RULES),
        "observation_interval_seconds": 0.1,
        "failed_action_transition": "advance",
        "resources": {"freeze-casts": 1},
        "streams": [
            {
                "id": "hall-protection",
                "steps": [
                    {
                        "all_conditions": [
                            {
                                "field": "active",
                                "actor_id": "hall",
                                "operator": "equals",
                                "value": True,
                            },
                            {
                                "field": "active",
                                "actor_id": "royal",
                                "operator": "equals",
                                "value": True,
                            },
                            {
                                "field": "hp_fraction",
                                "actor_id": "royal",
                                "operator": "at_most",
                                "value": cue_fraction,
                            },
                        ],
                        "action": freeze,
                    }
                ],
            }
        ],
    }
    profiles = {}
    for name, latency in (("timely", 0.2), ("delayed", 3.5), ("late", 4.5)):
        profiles[name] = {
            "plan_id": plan["id"],
            "observed_latency_traces": [
                {
                    "source_replay": f"synthetic-{name}-not-measured-player-evidence",
                    "responses": {
                        "hall-freeze": {
                            "latency_seconds": latency,
                            "missed": False,
                            "placement_errors": {"area": {"dx": 0, "dy": 0}},
                        }
                    },
                }
            ],
        }
    return plan, profiles


def summarize(sample, overlap, cue_fraction, response, step, filename):
    combat = sample["combat"]
    actions = sample["control"]["actions"]
    action = actions[0] if actions else {}
    pulses = [
        event
        for event in combat["trace"]
        if event.get("event") == "artillery_flame_pulse"
    ]
    hall_death = combat["actors"]["hall"]["death_time"]
    return {
        "overlap": overlap,
        "cue_hp_fraction": cue_fraction,
        "response": response,
        "maximum_step_seconds": step,
        "royal_hp": combat["actors"]["royal"]["hp"],
        "royal_death_time": combat["actors"]["royal"]["death_time"],
        "hall_hp": combat["actors"]["hall"]["hp"],
        "hall_death_time": hall_death,
        "storage_hp": combat["actors"]["storage"]["hp"],
        "freeze_status": action.get("status", "cue_not_observed"),
        "cue_time_seconds": action.get("cue_time_seconds"),
        "execution_time_seconds": action.get("time_seconds"),
        "freeze_resource_remaining": sample["control"]["remaining_resources"][
            "freeze-casts"
        ],
        "flame_pools_created": len(combat["artillery_flames"]["pools"]),
        "flame_pulses_after_hall_death": sum(
            hall_death is not None and event["time_seconds"] > hall_death
            for event in pulses
        ),
        "result": filename,
    }


def render(rows):
    columns = (
        "overlap",
        "cue_hp_fraction",
        "response",
        "maximum_step_seconds",
        "freeze_status",
        "cue_time_seconds",
        "execution_time_seconds",
        "royal_hp",
        "royal_death_time",
        "hall_death_time",
        "flame_pools_created",
        "flame_pulses_after_hall_death",
    )
    headings = "".join(f"<th>{escape(name.replace('_', ' '))}</th>" for name in columns)
    table = "".join(
        f'<tr data-overlap="{escape(row["overlap"])}" '
        f'data-cue="{row["cue_hp_fraction"]}" '
        f'data-response="{escape(row["response"])}">'
        + "".join(f"<td>{escape(str(row[name]))}</td>" for name in columns)
        + f'<td><a href="{escape(row["result"])}">JSON</a></td></tr>'
        for row in rows
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Royal Champion vs TH17 artillery: response study</title>
<style>
body{{max-width:1250px;margin:32px auto;padding:0 20px;font:16px/1.6 system-ui;
background:#111821;color:#e5edf5}}a{{color:#91ceff}}table{{border-collapse:collapse}}
th,td{{border:1px solid #455362;padding:7px;text-align:left}}th{{background:#223142}}
.scroll{{overflow-x:auto}}.notice{{padding:16px;background:#293447}}
label{{display:inline-block;margin:0 20px 16px 0}}select{{margin-left:8px;padding:6px}}
</style></head><body>
<p><a href="strategy.html">Strategy lab</a> · <a href="artillery-study.json">Study inputs and cases</a></p>
<h1>Protecting an RC charge from TH17 artillery</h1>
<p class="notice">Conditional sector experiment. Current client accuracy, complete
army performance and your response latency remain unverified.</p>
<p>The same RC45, Spear21 and Boots23 attacks a TH17 Town Hall and then a storage.
Her ability is pressed at zero. One Freeze becomes eligible when the RC falls to
90% or 65% HP while both she and the Town Hall remain active. Response delays are
declared controls: 0.2, 3.5 and 4.5 seconds. This is not an optimized cue or a
measurement of your reactions.</p>
<p>In both hypotheses, released flames continue after their source is frozen or
destroyed. The experiment varies whether overlapping pools add their damage or
apply only the strongest active pool. Both policies are unresolved. It also
compares solver steps of 0.1, 0.05 and 0.025 seconds.</p>
<p>With the 65% cue, even the timely cast arrives after the second volley, so it
does not change the final outcome here. The earlier 90% cue tests whether changing
the protection plan matters more than improving response speed alone.</p>
<p>Inspect the cue, actual cast, surviving HP and post-destruction flame pulses
together. Destroying the Town Hall does not by itself demonstrate a safe charge
under the declared persistence policy.</p>
<label>Overlap<select id="overlap-filter"><option value="">Both hypotheses</option>
<option value="maximum">Maximum active pool</option><option value="additive">Additive pools</option></select></label>
<label>Cue<select id="cue-filter"><option value="">Both cues</option>
<option value="0.9">90% HP</option><option value="0.65">65% HP</option></select></label>
<label>Response<select id="response-filter"><option value="">All delays</option>
<option value="timely">0.2 seconds</option><option value="delayed">3.5 seconds</option>
<option value="late">4.5 seconds</option></select></label>
<div class="scroll"><table><thead><tr>{headings}<th>Evidence</th></tr></thead>
<tbody>{table}</tbody></table></div>
<h2>Evidence and limits</h2>
<p>The <a href="{OFFICIAL_SOURCE}">official TH17 introduction</a> describes an
always-active weapon firing four direct-hit projectiles, with repeats when fewer
targets are present, and leaving ground flames that affect ground and flying
troops. It says the Town Hall has no destruction bomb.</p>
<p>That historical description does not verify the current numerical snapshot,
flame stacking, persistence, pulse cadence, geometry or growth. Here projectile
travel is instantaneous, radius is 1.5 tiles, flame damage begins at the pinned
maximum and pulses every 0.1 seconds. Those choices are experiment inputs.
Giga Bomb, other defenses, pets, traps, defending troops and full-village paths
are absent. This cannot estimate a triple rate or establish your best army.</p>
<script>
const filters = {{
    overlap: document.getElementById("overlap-filter"),
    cue: document.getElementById("cue-filter"),
    response: document.getElementById("response-filter")
}};
function updateRows() {{
    for (const row of document.querySelectorAll("tbody tr")) {{
        row.hidden = Object.entries(filters).some(([key, control]) =>
            control.value && row.dataset[key] !== control.value);
    }}
}}
for (const control of Object.values(filters)) {{
    control.addEventListener("change", updateRows);
}}
</script>
</body></html>"""


def main():
    catalog = Catalog.load(ROOT / "data")
    rows = []
    for overlap in OVERLAP_POLICIES:
        scene = charge_scene(catalog, overlap)
        write(ROOT / f"examples/entity-artillery-{overlap}-conditional.json", scene)
        for cue_fraction in (0.9, 0.65):
            plan, profiles = response_inputs(catalog, cue_fraction)
            cue_label = str(cue_fraction).replace(".", "p")
            write(
                ROOT / f"examples/entity-artillery-{cue_label}-plan-synthetic.json",
                plan,
            )
            for response, profile in profiles.items():
                write(
                    ROOT
                    / f"examples/entity-artillery-{cue_label}-{response}-synthetic.json",
                    profile,
                )
                for step in (0.1, 0.05, 0.025):
                    scene["maximum_step_seconds"] = step
                    result = simulate_entity_closed_loop(
                        scene, catalog, plan, profile, 7, 1
                    )
                    filename = (
                        f"artillery-{overlap}-{cue_label}-{response}-"
                        f"{str(step).replace('.', 'p')}.json"
                    )
                    write(ROOT / "reports" / filename, result)
                    rows.append(
                        summarize(
                            result["human_combat"]["samples"][0],
                            overlap,
                            cue_fraction,
                            response,
                            step,
                            filename,
                        )
                    )
    summary = {
        "status": "CONDITIONAL_ARTILLERY_RESPONSE_STUDY_NOT_GAME_PREDICTION",
        "source": SOURCE,
        "official_behavior_source": OFFICIAL_SOURCE,
        "full_game_prediction": False,
        "current_client_verified": False,
        "measured_player_latency": False,
        "flame_overlap_verified": False,
        "flame_persistence_verified": False,
        "loadout_is_optimal": False,
        "cases": rows,
    }
    write(ROOT / "reports/artillery-study.json", summary)
    (ROOT / "reports/artillery-study.html").write_text(render(rows))
    print(json.dumps({"cases": len(rows), "report": "reports/artillery-study.html"}))


if __name__ == "__main__":
    main()
