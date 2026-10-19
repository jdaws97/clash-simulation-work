"""Compare complete architecture proposals and explicitly reduced combat probes."""

import json
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>Different base architectures · Clash Lab</title>
<style>
:root { color-scheme:dark; font:16px/1.5 system-ui; background:#10151c; color:#edf2f7; }
* { box-sizing:border-box; }
body { margin:0; }
main { max-width:1440px; margin:auto; padding:28px 24px 65px; }
h1 { font-size:34px; line-height:1.2; }
h2 { font-size:23px; }
a { color:#70e3c2; }
.card,.notice { background:#18212c; border:1px solid #3b4b5e; border-radius:12px; padding:18px; margin:18px 0; }
.notice { border-color:#be8f48; }
.muted,figcaption { color:#aebdcc; }
.controls { display:flex; flex-wrap:wrap; align-items:center; gap:16px; }
select,input { font:inherit; background:#10151c; color:#edf2f7; border:1px solid #53677d; padding:6px; border-radius:5px; }
#time { width:230px; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
canvas { width:100%; aspect-ratio:1; border:1px solid #344353; background:#111923; }
figure { margin:0; }
figcaption { margin-top:10px; min-height:48px; }
.table-scroll { overflow:auto; }
table { width:100%; border-collapse:collapse; font-size:14px; }
td,th { padding:9px; border-bottom:1px solid #344353; text-align:left; }
.small { font-size:14px; }
#load-status { min-height:24px; }
@media(max-width:900px) { .grid { grid-template-columns:1fr; } h1 { font-size:28px; } }
</style></head><body><main>
<p><a href="strategy.html">← Strategy and pipeline</a> · <a href="blueprints.html">Original grid and paired wall edits</a></p>
<h1>Different base architectures</h1>
<div class="notice"><strong>Eight full-inventory proposals now use four wall families.</strong><p>Staggered compartments, split cores, offset rings and stepped diamonds replace the single grid as candidate inputs. Every accepted candidate contains the same467 declared instances and325 walls. The44×44 envelope and proposed game settings remain unverified. Packing and overlap checks do not establish defensive strength.</p><p>The right map is an artificial mechanics experiment. The original study retains all walls and the Monolith, removing141 instances. The paired study also retains the Town Hall, removing140. Removed footprints become empty. Both use one Root Rider3, two Thrower2 troops and a source-linked Freeze7 command. This52-space group, removed defenses and synthetic responses cannot score the complete base or predict stars/trophies.</p><p>The added Town Hall changes its footprint, target role, weapon and death effects together. Blast/poison delays, activation threshold, poison geometry, damage growth and lingering are declared hypotheses. The damage curves are sensitivity inputs, not a measured poison model.</p></div>
<div class="card"><div class="controls">
<label>Proposal purpose <select id="mode"><option value="ranked">Ranked</option><option value="war-cwl">War/CWL</option></select></label>
<label>Wall family <select id="family"></select></label>
<label>Combat study <select id="study"><option value="town-hall">Walls + Monolith + Town Hall</option><option value="monolith">Original walls + Monolith</option></select></label>
<label>Poison hypothesis <select id="growth"><option value="constant_maximum">Constant maximum DPS</option><option value="two_stage">Two-stage field-age growth</option></select></label>
<label>Declared response <select id="response"><option value="timely">0.2-second joint response</option><option value="late">3.5-second joint response</option></select></label>
<label>Solver step <select id="step"><option value="0.1">0.1 seconds</option><option value="0.05">0.05 seconds</option></select></label>
<label>Probe time <input id="time" type="range" min="0" max="40" step="0.1" value="15"> <output id="time-label"></output></label>
</div><p id="load-status" class="muted" aria-live="polite">Loading the selected trace…</p><p class="small muted">Both maps use the same declared coordinates. The complete proposal repacks buildings as well as walls; comparisons across families therefore change more than wall topology. The controlled probe uses four-neighbor movement, declared wall attacks and live HP feedback. Its timing traces are test inputs, not measured human reaction distributions.</p></div>
<div class="grid"><figure><h2>Complete construction proposal</h2><canvas id="layout-map" width="880" height="880" aria-label="Complete architecture proposal"></canvas><figcaption id="layout-caption"></figcaption><p><a id="layout-json">Selected layout JSON</a></p></figure><figure><h2>Controlled wall-combat probe</h2><canvas id="combat-map" width="880" height="880" aria-label="Restricted wall and Monolith mechanics trace"></canvas><figcaption id="combat-caption"></figcaption><p><a id="combat-json">Selected combat trace</a> · <a id="probe-json">Explicit probe inputs/removals</a></p></figure></div>
<p class="small muted">Full map: greenTH, red defenses, tan walls, orange traps, purple banners, grey support/resource structures. Probe: goldR = Root Rider, blueT = Thrower, green openings = destroyed walls, magenta outline = recent wall impact, cyan = active Freeze, orange area = persistent poison. Removed structures are absent from the probe.</p>
<div class="card"><h2>Compare supported mechanics without selecting a base winner</h2><p>The original32 probes all clear the isolated Monolith. Adding the Town Hall can change routes and survival. That comparison still omits the other defenses, heroes, traps and garrison. A curve comparison only tests poison when the Town Hall dies and live troops enter the field.</p><div class="table-scroll"><table><thead><tr><th>Family</th><th>Response</th><th>Step</th><th>TownHallHP</th><th>MonolithHP</th><th>RootHP</th><th>ThrowerHP sum</th><th>Walls lost</th></tr></thead><tbody id="rows"></tbody></table></div><p id="case-count" class="small muted"></p><p><a href="town-hall-wall-combat.json">64-case Town Hall study</a> · <a href="architecture-wall-combat.json">32-case original mechanics summary</a> · <a href="architecture-search.json">All proposals and rejection records</a> · <a href="../examples/architecture-proposals-conditional.json">Declared architecture inputs</a></p></div>
<div class="notice"><h2>What the complete-village combat audit requires</h2><p id="audit-caption"></p><p>The audit examines every building type and instance, unknown destruction flags, defending heroes and the proposed CC. Unsupported structures cannot be disguised as passive buildings in the combat bridge. Conditional sector adapters still require complete behavior and held-out calibration. Ranked selection must use actual defender trophy value; war/CWL must use the strongest incoming stars/destruction result.</p><p><a href="architecture-combat-audits.json">Full-village audits for all eight candidates</a> · <a href="friendly-defense-tests.html">Friendly test protocol</a></p></div>
<div class="card"><h2>Separate Town Hall death and human Freeze diagnostic</h2><p>The64 paired wall cases never destroy the Town Hall, so they cannot validate poison. This additional16-case exercise uses one Root Rider and eight Throwers to destroy a Town Hall through actual troop weapons, then continue toward a Storage. It varies starting geometry, two poison growth hypotheses, two solver steps and two synthetic Freeze responses. The148-space group has no heroes or the rest of a village. Coincident point starts and already-ready troops are explicit artificial fixtures.</p><p>Freeze watches Town Hall health and rechecks whether it is still alive before execution. A late rejected command keeps its spell resource. The selected arrival-time target policy treats already-in-range targets as immediately attackable; both this policy and the legacy route/distance policy still need Clash AI calibration.</p><div class="table-scroll"><table><thead><tr><th>Thrower start</th><th>Response</th><th>Poison curve</th><th>Step</th><th>Hall dies at</th><th>Troop HP sum</th><th>Freeze outcome</th><th>Trace</th></tr></thead><tbody>__POISON_ROWS__</tbody></table></div><p><a href="town-hall-poison-entry.json">Complete death/entry summary and limitations</a></p></div>
</main><script type="application/json" id="payload">__PAYLOAD__</script><script>
"use strict";
const data = JSON.parse(document.getElementById("payload").textContent);
const entities = new Map(data.entities.map(entity => [entity.id, entity]));
const familyLabels = {staggered_compartments:"Staggered compartments",split_core:"Split core",offset_ring:"Offset ring",stepped_diamond:"Stepped diamond"};
for (const family of [...new Set(data.candidates.map(item => item.family))]) {
  const option = document.createElement("option");
  option.value = family;
  option.textContent = familyLabels[family] || family;
  document.getElementById("family").append(option);
}
let currentProbe = null;
let loadedKey = null;
let loadGeneration = 0;
function selectedCandidate() {
  return data.candidates.find(item => item.family === document.getElementById("family").value && item.id.startsWith(document.getElementById("mode").value + "-"));
}
function selectedCase() {
  const candidate = selectedCandidate();
  return selectedStudyCases().find(item => item.candidate === candidate.id && item.response_fixture === document.getElementById("response").value && item.maximum_step_seconds === Number(document.getElementById("step").value));
}
function selectedStudyCases() {
  if (document.getElementById("study").value === "monolith") {
    return data.cases;
  }
  return data.townHallCases.filter(item => item.poison_growth_hypothesis === document.getElementById("growth").value);
}
function box(context, x, y, width, height, color, label, scale) {
  context.fillStyle = color;
  context.fillRect(x * scale + 1, y * scale + 1, width * scale - 2, height * scale - 2);
  if (label) {
    context.fillStyle = "#10151c";
    context.textAlign = "center";
    context.font = "13px system-ui";
    context.fillText(label, (x + width / 2) * scale, (y + height / 2) * scale + 4);
  }
}
function emptyCanvas(id) {
  const canvas = document.getElementById(id);
  const context = canvas.getContext("2d");
  context.fillStyle = "#111923";
  context.fillRect(0, 0, canvas.width, canvas.height);
  return [context, canvas.width / selectedCandidate().blueprint.width];
}
function drawLayout() {
  const candidate = selectedCandidate();
  const [context, scale] = emptyCanvas("layout-map");
  for (const building of candidate.blueprint.buildings) {
    const entity = entities.get(building.id);
    const [width, height] = entity.size.split("x").map(Number);
    box(context, building.x, building.y, width, height, entity.color, entity.label, scale);
  }
  const metrics = candidate.analysis;
  document.getElementById("layout-caption").textContent = `${metrics.validation.building_count} instances · ${metrics.inventory_counts.wall} walls · Hall depth ${metrics.town_hall_boundary_distance_tiles} tiles · ${candidate.allocated_remainder_wall_count} walls allocated after declared outlines.`;
  document.getElementById("layout-json").href = `${candidate.id}.json`;
  const audit = data.audits.find(item => item.blueprint_id === candidate.analysis.blueprint_id);
  document.getElementById("audit-caption").textContent = `${audit.unsupported_entity_types.length} entity types lack even a conditional adapter, across ${audit.unsupported_instance_count} instances. ${audit.unknown_destruction_instances.length} destruction flags are unknown. Unsupported types: ${audit.unsupported_entity_types.join(", ")}. Full-village battle scoring remains unavailable.`;
}
function drawCombat() {
  const [context, scale] = emptyCanvas("combat-map");
  const time = Number(document.getElementById("time").value);
  document.getElementById("time-label").textContent = `${time.toFixed(1)}s`;
  if (!currentProbe || loadedKey !== selectedCase().artifact) {
    document.getElementById("combat-caption").textContent = "Loading the selected mechanics trace…";
    return;
  }
  const sample = currentProbe.result.human_combat.samples[0];
  const combat = sample.combat;
  const frame = combat.frames.reduce((previous, item) => item.time_seconds <= time + 0.000001 ? item : previous, combat.frames[0]);
  for (const [key, actor] of Object.entries(combat.actors)) {
    const state = frame.actors[key];
    if (actor.kind === "unit") {
      if (!state.active) {
        continue;
      }
      context.fillStyle = key === "root" ? "#ffcc72" : "#79bcff";
      context.beginPath();
      context.arc(state.x * scale, state.y * scale, key === "root" ? 7 : 5, 0, Math.PI * 2);
      context.fill();
      context.fillStyle = "#edf2f7";
      context.fillText(key === "root" ? "R" : "T", state.x * scale, state.y * scale - 10);
    } else if (state.hp > 0) {
      const isHall = actor.entity_adapter.entity === "town-hall";
      let fill = "#cb6975";
      let label = "MO";
      if (actor.kind === "wall") {
        fill = "#d6bb8b";
        label = "";
      } else if (isHall) {
        fill = "#70e3c2";
        label = "TH";
      }
      box(context, actor.x, actor.y, actor.width, actor.height, fill, label, scale);
    } else if (actor.kind === "wall") {
      context.strokeStyle = "#70e3c2";
      context.strokeRect(actor.x * scale, actor.y * scale, scale, scale);
    }
  }
  const hazardState = combat.town_halls_and_hazards;
  if (hazardState) {
    for (const field of Object.values(hazardState.hazards.fields)) {
      if (field.start_seconds <= time && time < field.start_seconds + field.duration_seconds) {
        context.fillStyle = "rgba(234,166,76,0.16)";
        context.strokeStyle = "#eaa64c";
        context.beginPath();
        context.arc(field.area.x * scale, field.area.y * scale, field.area.radius * scale, 0, Math.PI * 2);
        context.fill();
        context.stroke();
      }
    }
  }
  context.strokeStyle = "#f29aff";
  context.lineWidth = 3;
  for (const event of combat.trace) {
    if (event.event === "wall_impact" && event.time_seconds <= time && time - event.time_seconds <= 0.6) {
      const actor = combat.actors[event.target];
      context.strokeRect(actor.x * scale, actor.y * scale, scale, scale);
    }
  }
  for (const action of sample.control.actions) {
    if (action.action_id === "protect-root" && action.status === "command_applied" && action.time_seconds <= time && time < action.time_seconds + 5.5) {
      const area = action.commanded_area;
      context.strokeStyle = "#73efff";
      context.beginPath();
      context.arc(area.x * scale, area.y * scale, area.radius * scale, 0, Math.PI * 2);
      context.stroke();
    }
  }
  const wallsLost = currentProbe.retained_blueprint_instances.filter(key => key.startsWith("wall-") && frame.actors[key].hp <= 0).length;
  const hallState = frame.actors["town-hall-0"];
  const hallCaption = hallState ? `TownHallHP ${Math.round(hallState.hp)} (${hallState.town_hall_weapon_active ? "activated" : "dormant"}) · ` : "";
  const slowCaption = frame.actors.root.hazard_attack_rate !== undefined ? ` · Root attack rate ${frame.actors.root.hazard_attack_rate}` : "";
  document.getElementById("combat-caption").textContent = `At ${frame.time_seconds.toFixed(2)}s: ${hallCaption}MonolithHP ${Math.round(frame.actors["monolith-0"].hp)} · RootHP ${Math.round(frame.actors.root.hp)} · ThrowerHP ${Math.round(frame.actors["thrower-0"].hp + frame.actors["thrower-1"].hp)} · ${wallsLost} walls destroyed${slowCaption}. ${currentProbe.removed_blueprint_instances.length} original instances removed.`;
}
function table() {
  const rows = document.getElementById("rows");
  rows.replaceChildren();
  const selected = selectedStudyCases().filter(item => item.candidate.startsWith(document.getElementById("mode").value + "-"));
  for (const item of selected) {
    const row = document.createElement("tr");
    const values = [familyLabels[item.family], item.response_fixture, item.maximum_step_seconds, item.town_hall_hp_at_horizon === undefined ? "removed" : Math.round(item.town_hall_hp_at_horizon), Math.round(item.monolith_hp_at_horizon), Math.round(item.troop_hp_at_horizon.root), Math.round(item.troop_hp_at_horizon["thrower-0"] + item.troop_hp_at_horizon["thrower-1"]), item.walls_destroyed];
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    rows.append(row);
  }
  const exposed = selected.filter(item => item.poison_pulses_with_live_targets > 0).length;
  document.getElementById("case-count").textContent = `${selected.length} probes for this purpose and selected growth branch; ${data.cases.length} original cases and ${data.townHallCases.length} Town Hall cases. ${exposed} selected cases expose live troops to poison pulses. No opponent weights, player error distribution, defense winner or calibrated solver tolerance supplied.`;
}
async function update() {
  document.getElementById("growth").disabled = document.getElementById("study").value === "monolith";
  drawLayout();
  table();
  const summary = selectedCase();
  const generation = ++loadGeneration;
  currentProbe = null;
  drawCombat();
  document.getElementById("combat-json").href = summary.artifact;
  document.getElementById("probe-json").href = `../examples/${summary.artifact.replace("-combat.json", "-probe.json")}`;
  document.getElementById("load-status").textContent = "Loading the selected trace…";
  try {
    const response = await fetch(summary.artifact);
    if (!response.ok) {
      throw new Error(`HTTP${response.status}`);
    }
    const result = await response.json();
    if (generation !== loadGeneration) {
      return;
    }
    currentProbe = result;
    loadedKey = summary.artifact;
    document.getElementById("load-status").textContent = "Selected trace loaded. This is a controlled removal experiment, not full-base performance.";
    drawCombat();
  } catch (error) {
    if (generation === loadGeneration) {
      document.getElementById("load-status").textContent = `Could not load this trace: ${error.message}`;
    }
  }
}
for (const id of ["mode", "family", "response", "step", "study", "growth"]) {
  document.getElementById(id).addEventListener("change", update);
}
document.getElementById("time").addEventListener("input", drawCombat);
update();
</script></body></html>"""


def main():
    search = json.loads((ROOT / "reports/architecture-search.json").read_text())
    matrix = json.loads((ROOT / "reports/architecture-wall-combat.json").read_text())
    if not matrix["matrix_complete"] or len(matrix["cases"]) != 32:
        raise RuntimeError("The declared32-case probe matrix has not finished")
    if any(case["monolith_hp_at_horizon"] != 0 for case in matrix["cases"]):
        raise RuntimeError("The report's shared-clear fixture finding no longer holds")
    town_hall_matrix = json.loads(
        (ROOT / "reports/town-hall-wall-combat.json").read_text()
    )
    if not town_hall_matrix["matrix_complete"] or len(town_hall_matrix["cases"]) != 64:
        raise RuntimeError("The declared64-case Town Hall matrix has not finished")
    from build_blueprint_report import LABELS, color

    snapshot = json.loads((ROOT / "data/catalog.json").read_text())
    payload = {
        "candidates": search["candidates"],
        "cases": matrix["cases"],
        "townHallCases": town_hall_matrix["cases"],
        "audits": json.loads(
            (ROOT / "reports/architecture-combat-audits.json").read_text()
        ),
        "entities": [
            {
                "id": row["entity"]["id"],
                "size": row["entity"].get("size"),
                "color": color(row["entity"]),
                "label": LABELS.get(row["entity"]["id"], ""),
            }
            for row in snapshot["entries"]
            if row["entity"].get("size")
        ],
    }
    poison_study = json.loads(
        (ROOT / "reports/town-hall-poison-entry.json").read_text()
    )
    if (
        len(poison_study["cases"]) != 16
        or not poison_study["all_town_halls_destroyed_by_troop_weapons"]
    ):
        raise RuntimeError("The native Town Hall death diagnostic is incomplete")
    poison_rows = []
    for case in poison_study["cases"]:
        outcomes = ", ".join(action["status"] for action in case["control"])
        values = [
            case["entry"],
            case["response_fixture"],
            case["poison_growth_hypothesis"],
            case["maximum_step_seconds"],
            round(case["town_hall_death_seconds"], 2),
            round(sum(case["troop_hp_at_horizon"].values())),
            outcomes,
        ]
        cells = "".join(f"<td>{escape(str(value))}</td>" for value in values)
        artifact = escape(case["artifact"], quote=True)
        poison_rows.append(f'<tr>{cells}<td><a href="{artifact}">JSON</a></td></tr>')
    encoded = json.dumps(payload).replace("</", "<\\/")
    destination = ROOT / "reports/architectures.html"
    destination.write_text(
        PAGE.replace("__PAYLOAD__", encoded).replace(
            "__POISON_ROWS__", "".join(poison_rows)
        )
    )
    print(f"Saved {destination}")


if __name__ == "__main__":
    main()
