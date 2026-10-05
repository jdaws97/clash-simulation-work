"""Render full tile drafts and export standalone SVG construction maps."""

import html
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from clashlab.blueprints import apply_blueprint_wall_edit, inspect_blueprint
from clashlab.catalog import Catalog
from clashlab.common import stable_id, write_json
from clashlab.wallprobes import inspect_wall_access


def wall_study(name, blueprint, catalog):
    """Bounded gap interventions, not architecture optimization or winners."""
    entries = {
        "ranked": [[0, 19], [43, 24], [19, 0], [24, 43]],
        "war-cwl": [[0, 19], [43, 24], [28, 0], [24, 43]],
    }
    specification = {
        "source": "declared-static-wall-probe-not-observed-Clash-troop-AI",
        "obstacle_policy": "all_non_trap_footprints_hypothesis",
        "route_policy": "four_neighbor_minimum_walls_then_steps_hypothesis",
        "entries": [
            {"id": direction, "cell": cell}
            for direction, cell in zip(
                ("west", "east", "north", "south"), entries[name]
            )
        ],
        "targets": ["town-hall-0", "monolith-0"],
        "profiles": [
            {
                "id": label,
                "movement": movement,
                "range_tiles": reach,
                "source": "explicit-generic-range-test-not-calibrated-unit-behavior",
            }
            for label, movement, reach in (
                ("Short reach / avoid walls", "ground_avoid", 1),
                ("Long reach / avoid walls", "ground_avoid", 4),
                ("Short reach / minimum breaches", "ground_minimum_breaches", 1),
                ("Short reach / bypass walls", "ground_ignore_walls", 1),
                ("Air / direct approach", "air_direct", 3),
            )
        ],
    }
    write_json(ROOT / f"examples/blueprint-{name}-wall-probes.json", specification)
    reference_access = inspect_wall_access(blueprint, catalog, specification)
    write_json(ROOT / f"reports/blueprint-{name}-wall-access.json", reference_access)
    variants = []
    wall_by_cell = {
        (item["x"], item["y"]): item
        for item in blueprint["buildings"]
        if item["id"] == "wall"
    }
    interventions = (
        (
            "north-core-gap",
            "Open north/core boundary",
            [(x, 15) for x in range(20, 23)],
        ),
        (
            "south-core-gap",
            "Open south/core boundary",
            [(x, 26) for x in range(20, 23)],
        ),
        ("west-core-gap", "Open west/core boundary", [(15, y) for y in range(20, 23)]),
    )
    for key, label, cells in interventions:
        operation = {
            "source": "declared-three-wall-relocation-probe-not-defense-recommendation",
            "base_id": stable_id(blueprint),
            "moves": [
                {"instance": wall_by_cell[cell]["instance"], "x": index + 1, "y": 0}
                for index, cell in enumerate(cells)
            ],
        }
        candidate = apply_blueprint_wall_edit(blueprint, catalog, operation)
        access = inspect_wall_access(candidate, catalog, specification)
        stem = f"blueprint-{name}-{key}"
        write_json(ROOT / f"examples/{stem}-operation.json", operation)
        write_json(ROOT / f"reports/{stem}.json", candidate)
        write_json(ROOT / f"reports/{stem}-wall-access.json", access)
        variants.append(
            {
                "label": label,
                "blueprint": candidate,
                "analysis": inspect_blueprint(
                    candidate,
                    catalog,
                    read(ROOT / "examples/blueprint-probes-conditional.json"),
                ),
                "wall_access": access,
                "artifact": f"{stem}.json",
            }
        )
    return reference_access, variants


LABELS = {
    "town-hall": "TH",
    "monolith": "MO",
    "eagle-artillery": "EA",
    "scattershot": "SS",
    "inferno-tower": "IT",
    "multi-archer-tower": "MA",
    "ricochet-cannon": "RC",
    "air-defense": "AD",
    "air-sweeper": "SW",
    "x-bow": "XB",
    "wizard-tower": "WT",
    "bomb-tower": "BT",
    "archer-tower": "AT",
    "cannon": "CN",
    "mortar": "MT",
    "hidden-tesla": "TE",
    "spell-tower": "ST",
    "clan-castle": "CC",
    "hero-banner": "HB",
    "builders-hut": "BH",
    "army-camp": "AC",
    "hero-hall": "HH",
}


def read(path):
    return json.loads(path.read_text())


def color(entity):
    if entity["id"] == "town-hall":
        return "#70e3c2"
    if entity["category"] == "wall":
        return "#d6bb8b"
    if entity["category"] == "trap":
        return "#ffb15c"
    if entity["id"] == "hero-banner":
        return "#cdb8ff"
    if entity["category"] == "defense":
        return "#cb6975"
    return "#687f94"


def svg_map(name, blueprint, entities):
    scale = 20
    margin = 35
    width = blueprint["width"] * scale + margin * 2
    height = blueprint["height"] * scale + margin * 2 + 45
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#10151c"/>',
        f'<text x="{margin}" y="23" fill="#edf2f7" font-family="sans-serif" font-size="16">{html.escape(name)} — declared {blueprint["width"]}×{blueprint["height"]} draft; game legality unverified</text>',
        f'<g transform="translate({margin},{margin + 10})">',
    ]
    for building in blueprint["buildings"]:
        entity = entities[building["id"]]
        bw, bh = (int(value) for value in entity["size"].split("x"))
        x, y = building["x"] * scale, building["y"] * scale
        label = LABELS.get(building["id"], "")
        text = html.escape(
            f"{building['instance']}: level {building['level']}, tile ({building['x']},{building['y']}), mode {building.get('mode', 'none')}"
        )
        parts.append(
            f'<rect x="{x + 1}" y="{y + 1}" width="{bw * scale - 2}" height="{bh * scale - 2}" fill="{color(entity)}" stroke="#10151c"><title>{text}</title></rect>'
        )
        if label and entity["category"] != "wall":
            parts.append(
                f'<text x="{x + bw * scale / 2}" y="{y + bh * scale / 2 + 4}" text-anchor="middle" fill="#10151c" font-family="sans-serif" font-size="13">{label}</text>'
            )
    for coordinate in range(0, blueprint["width"] + 1, 5):
        parts.append(
            f'<text x="{coordinate * scale}" y="-5" text-anchor="middle" fill="#aebdcc" font-family="sans-serif" font-size="10">{coordinate}</text>'
        )
    for coordinate in range(0, blueprint["height"] + 1, 5):
        parts.append(
            f'<text x="-5" y="{coordinate * scale + 4}" text-anchor="end" fill="#aebdcc" font-family="sans-serif" font-size="10">{coordinate}</text>'
        )
    parts.extend(["</g>", "</svg>"])
    (ROOT / "reports" / f"blueprint-{name}.svg").write_text("\n".join(parts))


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>TH16 base drafts · Clash Lab</title>
<style>
:root {
  color-scheme: dark;
  font: 16px/1.55 system-ui;
  --bg: #10151c;
  --panel: #18212c;
  --text: #edf2f7;
  --muted: #aebdcc;
  --accent: #70e3c2;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
}
main {
  max-width: 1320px;
  margin: auto;
  padding: 30px 22px 70px;
}
h1 { font-size: 36px; line-height: 1.2; }
h2 { font-size: 24px; }
a { color: var(--accent); }
.notice, .card {
  border: 1px solid #3b4b5e;
  border-radius: 12px;
  padding: 20px;
  background: var(--panel);
  margin: 18px 0;
}
.notice { border-color: #be8f48; }
.muted { color: var(--muted); }
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}
canvas {
  width: 100%;
  aspect-ratio: 1;
  background: #111923;
  border: 1px solid #344353;
}
.metric { margin: 10px 0; color: var(--muted); }
select, input, button {
  font: inherit;
  padding: 7px;
  background: #10151c;
  color: var(--text);
  border: 1px solid #53677d;
  border-radius: 5px;
}
table { border-collapse: collapse; width: 100%; font-size: 14px; }
td, th {
  padding: 9px;
  border-bottom: 1px solid #344353;
  text-align: left;
}
.table-wrap { overflow: auto; max-height: 480px; }
#details { min-height: 58px; }
figure { margin: 0; }
figcaption { margin-top: 10px; }
.legend { color: var(--muted); font-size: 14px; }
label { white-space: nowrap; }
@media (max-width: 850px) {
  .grid { grid-template-columns: 1fr; }
  h1 { font-size: 28px; }
}
</style></head><body><main>
<p><a href="strategy.html">← Strategy and pipeline report</a> · <a href="architectures.html">Compare four different wall architectures →</a></p><h1>Original grid and paired wall diagnostics</h1>
<div class="notice"><strong>The repeated 3×3 design is a fixed starting template, not an optimized base.</strong><p>I supplied horizontal and vertical wall lines at tiles 4, 15, 26 and 37. Building swaps kept that wall geometry fixed. The earlier full-base screen measured Hall depth and disc concentration; it did not score wall-driven troop movement. The separate combat sector has conditional breach/routing mechanics, but full-village attack scoring is still unfinished.</p><p>The 44×44 board is an explicit draft envelope awaiting confirmation. Each map places 467 declared instances, including 325 walls and 44 traps. Unknown destruction flags remain null. The new gap controls and route overlay below expose structural effects; they do not establish a best defense.</p></div>
<div class="card"><div class="controls"><label><input type="checkbox" id="walls" checked> Walls</label><label><input type="checkbox" id="traps" checked> Traps</label><label><input type="checkbox" id="grid"> Tile grid</label><label>Disc probe centered on <select id="anchor"><option value="">None</option></select></label></div><p class="muted">Hover a building for coordinates/settings. Click one to retain its details. The six-tile disc is a declared geometric probe; it does not model Fireball targeting, damage or collision. Comparison uses matched anchor types/indices.</p><p id="details" aria-live="polite">Select a building to inspect it.</p></div>
<div class="card"><h2>Wall access diagnostics</h2><div class="controls"><label>Entry <select id="route-entry"><option value="west">West</option><option value="east">East</option><option value="north">North</option><option value="south">South</option></select></label><label>Target <select id="route-target"><option value="town-hall-0">Town Hall</option><option value="monolith-0">Monolith</option></select></label><label>Movement/range probe <select id="route-profile"></select></label><label><input type="checkbox" id="routes" checked> Show route</label></div><p class="muted">Cyan = a route to the selected target in an unchanged village; magenta = wall tiles crossed by that route. Ground movement uses four neighbors, with minimum wall count before route length. Ranges 1/4/3 are declared generic test values. These routes do not predict troop target choice, breach time, damage exposure, funneling or retargeting. Air uses a straight approach that ignores walls. Enclosed-region counts use walls alone, ignoring buildings.</p><p>Gap probes move three walls to spare northern tiles, keeping every instance and building position. They test access changes and are not proposed finished bases. <a href="blueprint-ranked-wall-access.json">Ranked route JSON</a> · <a href="blueprint-war-cwl-wall-access.json">War/CWL route JSON</a></p></div>
<div class="grid"><figure><h2>Ranked: Town Hall denial hypothesis</h2><p><label>Wall geometry <select id="ranked-walls"><option value="">Fixed grid reference</option></select></label></p><p><label>Inspect position swap <select id="ranked-swap"><option value="">Reference layout</option></select></label></p><canvas id="ranked-map" width="880" height="880" aria-label="Ranked TH16 proposed tile layout"></canvas><figcaption id="ranked-metrics" class="metric"></figcaption><p id="ranked-route-metrics" class="metric"></p><p><a id="ranked-selected-artifact" href="blueprint-ranked.json">Selected tile JSON</a> · <a href="blueprint-ranked.svg">Reference SVG</a> · <a href="blueprint-ranked-analysis.json">Geometry audit</a> · <a href="blueprint-ranked-swap-search.json">59 building swaps</a></p></figure><figure><h2>War/CWL: distributed anchors hypothesis</h2><p><label>Wall geometry <select id="war-cwl-walls"><option value="">Fixed grid reference</option></select></label></p><p><label>Inspect position swap <select id="war-cwl-swap"><option value="">Reference layout</option></select></label></p><canvas id="war-cwl-map" width="880" height="880" aria-label="War and CWL TH16 proposed tile layout"></canvas><figcaption id="war-cwl-metrics" class="metric"></figcaption><p id="war-cwl-route-metrics" class="metric"></p><p><a id="war-cwl-selected-artifact" href="blueprint-war-cwl.json">Selected tile JSON</a> · <a href="blueprint-war-cwl.svg">Reference SVG</a> · <a href="blueprint-war-cwl-analysis.json">Geometry audit</a> · <a href="blueprint-war-cwl-swap-search.json">59 building swaps</a></p></figure></div>
<p class="legend">TH Town Hall · MO Monolith · EA Eagle · SS Scattershot · IT Inferno · MA Multi-Archer · RC Ricochet · AD Air Defense · SW Sweeper · XB X-Bow · ST Spell Tower · CC Clan Castle · HB Hero Banner. Green = Town Hall; red = defense; tan = walls; orange = traps; purple = banners; grey = support/resource buildings.</p>
<div class="card"><h2>Why the layouts differ</h2><p>Electro31 defense values actual defender trophies and Town Hall survival. Its Town Hall sits deeper in the declared map, with important support nearby. That concentrates value for an attacker who can reach or remove the cluster.</p><p>War/CWL is assessed by the strongest incoming attack, with stars first and destruction second. Its Hall and major damage anchors occupy different compartments. In the declared disc probe, the largest key-anchor group is smaller. This is a spacing observation, not proof that it resists triples.</p><p>Both candidates still need competent air and Thrower attacks, charges that protect their support, and scouting/adapted follow-ups. Defensive CC contents should be tested separately. No opponent mix weights or human error distribution are invented.</p></div>
<div class="card"><h2>Construction coordinates</h2><div class="controls"><label>Layout <select id="table-layout"><option value="ranked">Ranked</option><option value="war-cwl">War/CWL</option></select></label><label>Filter <input id="filter" placeholder="monolith, air-defense, trap…"></label><label><input type="checkbox" id="table-walls"> Include wall rows</label></div><p class="muted">Coordinates are top-left tile origins in the declared map, with x increasing right and y increasing down. Sweeper angles use north=0° and clockwise rotation; the game's UI mapping still needs verification.</p><div class="table-wrap"><table><thead><tr><th>Instance</th><th>Level</th><th>Tile</th><th>Mode/settings</th><th>Destruction</th></tr></thead><tbody id="rows"></tbody></table></div><p id="row-count"></p></div>
<div class="notice"><h2>Before these become game-ready bases</h2><p>Confirm board boundaries and full inventory; verify destruction flags, modes, gearing/supercharge applicability and the actual defensive state; place and check the drafts in the editor; run friendly challenges; calibrate the complete combat model and evaluate held-out ranked/war/CWL encounters. Each layout has 59 inventory-preserving position-swap proposals. Lower disc concentration may also remove useful Town Hall support; the screen selects no performance winner. Geometry checks alone cannot establish a great base.</p><p><a href="../examples/blueprint-ranked-configuration.json">Ranked design inputs</a> · <a href="../examples/blueprint-war-cwl-configuration.json">War/CWL design inputs</a> · <a href="../examples/blueprint-probes-conditional.json">Explicit probe inputs</a></p></div>
</main><script id="payload" type="application/json">__PAYLOAD__</script><script>
"use strict";
const data = JSON.parse(document.getElementById("payload").textContent);
const entities = new Map(data.entities.map(entity => [entity.id, entity]));
const keyEntities = new Set(data.probes.key_entities);
const anchorControl = document.getElementById("anchor");
for (const profile of data.cases.ranked.wall_access.specification.profiles) {
  const option = document.createElement("option");
  option.value = profile.id;
  option.textContent = profile.id;
  option.selected = profile.movement === "ground_minimum_breaches";
  document.getElementById("route-profile").append(option);
}
for (const name of ["ranked", "war-cwl"]) {
  const wallSelect = document.getElementById(`${name}-walls`);
  data.cases[name].wall_variants.forEach((variant, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = variant.label;
    wallSelect.append(option);
  });
  wallSelect.addEventListener("change", () => {
    document.getElementById(`${name}-swap`).value = "";
    document.getElementById(`${name}-swap`).disabled = wallSelect.value !== "";
    redraw();
    table();
  });
  const select = document.getElementById(`${name}-swap`);
  data.cases[name].search.candidates.forEach((candidate, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = `${candidate.operation.first} ↔ ${candidate.operation.second}`;
    select.append(option);
  });
  select.addEventListener("change", () => {
    redraw();
    table();
  });
}
function selectedCase(name) {
  const reference = data.cases[name];
  const wallSelection = document.getElementById(`${name}-walls`).value;
  if (wallSelection !== "") {
    return reference.wall_variants[Number(wallSelection)];
  }
  const selection = document.getElementById(`${name}-swap`).value;
  if (selection === "") {
    return reference;
  }
  const candidate = reference.search.candidates[Number(selection)];
  const first = reference.blueprint.buildings.find(item => item.instance === candidate.operation.first);
  const second = reference.blueprint.buildings.find(item => item.instance === candidate.operation.second);
  const buildings = reference.blueprint.buildings.map(item => {
    if (item.instance === first.instance) {
      return {...item, x: second.x, y: second.y};
    }
    if (item.instance === second.instance) {
      return {...item, x: first.x, y: first.y};
    }
    return item;
  });
  return {
    blueprint: {...reference.blueprint, buildings},
    analysis: {...reference.analysis, ...candidate}
  };
}
for (const building of data.cases.ranked.blueprint.buildings) {
  if (keyEntities.has(building.id)) {
    const option = document.createElement("option");
    option.value = building.instance;
    option.textContent = building.instance;
    anchorControl.append(option);
  }
}
function geometry(building) {
  const [width, height] = entities.get(building.id).size.split("x").map(Number);
  return {x: building.x, y: building.y, width, height};
}
function detail(building, name) {
  const level = building.level === null ? "no upgrade level" : `level ${building.level}`;
  const eligibility = building.counts_for_destruction === null ? "destruction flag unknown" : `counts for destruction: ${building.counts_for_destruction}`;
  return `${name}: ${building.instance} · ${level} · tile (${building.x}, ${building.y}) · ${building.mode || "no weapon mode"} · ${JSON.stringify(building.settings || {})} · ${eligibility}`;
}
function draw(name) {
  const study = selectedCase(name);
  const canvas = document.getElementById(`${name}-map`);
  canvas.width = study.blueprint.width * 20;
  canvas.height = study.blueprint.height * 20;
  canvas.style.aspectRatio = `${study.blueprint.width} / ${study.blueprint.height}`;
  const context = canvas.getContext("2d");
  const scale = canvas.width / study.blueprint.width;
  context.fillStyle = "#111923";
  context.fillRect(0, 0, canvas.width, canvas.height);
  if (document.getElementById("grid").checked) {
    context.strokeStyle = "#24313f";
    context.lineWidth = 1;
    for (let index = 0; index <= study.blueprint.width; index += 1) {
      context.beginPath();
      context.moveTo(index * scale, 0);
      context.lineTo(index * scale, canvas.height);
      context.stroke();
    }
    for (let index = 0; index <= study.blueprint.height; index += 1) {
      context.beginPath();
      context.moveTo(0, index * scale);
      context.lineTo(canvas.width, index * scale);
      context.stroke();
    }
  }
  for (const building of study.blueprint.buildings) {
    const entity = entities.get(building.id);
    if (entity.category === "wall" && !document.getElementById("walls").checked) {
      continue;
    }
    if (entity.category === "trap" && !document.getElementById("traps").checked) {
      continue;
    }
    const box = geometry(building);
    context.fillStyle = entity.color;
    context.fillRect(
      box.x * scale + 1, box.y * scale + 1,
      box.width * scale - 2, box.height * scale - 2
    );
    if (building.id === "air-sweeper") {
      const angle = (building.settings.facing_degrees - 90) * Math.PI / 180;
      const cx = (box.x + box.width / 2) * scale;
      const cy = (box.y + box.height / 2) * scale;
      context.strokeStyle = "#ffffff";
      context.beginPath();
      context.moveTo(cx, cy);
      context.lineTo(cx + Math.cos(angle) * 30, cy + Math.sin(angle) * 30);
      context.stroke();
    }
    if (entity.label) {
      context.fillStyle = "#10151c";
      context.font = "14px system-ui";
      context.textAlign = "center";
      context.fillText(
        entity.label,
        (box.x + box.width / 2) * scale,
        (box.y + box.height / 2) * scale + 5
      );
    }
  }
  const anchor = study.blueprint.buildings.find(building => building.instance === anchorControl.value);
  if (anchor) {
    const box = geometry(anchor);
    const radius = data.probes.footprint_disc_radius_tiles;
    context.strokeStyle = "#73efff";
    context.lineWidth = 3;
    context.beginPath();
    context.arc(
      (box.x + box.width / 2) * scale,
      (box.y + box.height / 2) * scale,
      radius * scale,
      0,
      Math.PI * 2
    );
    context.stroke();
    const centerX = box.x + box.width / 2;
    const centerY = box.y + box.height / 2;
    for (const building of study.blueprint.buildings) {
      if (!keyEntities.has(building.id)) {
        continue;
      }
      const covered = geometry(building);
      const dx = Math.max(covered.x - centerX, centerX - covered.x - covered.width, 0);
      const dy = Math.max(covered.y - centerY, centerY - covered.y - covered.height, 0);
      if (Math.hypot(dx, dy) <= radius) {
        context.strokeRect(covered.x * scale, covered.y * scale, covered.width * scale, covered.height * scale);
      }
    }
  }
  document.getElementById(`${name}-metrics`).textContent = `${study.analysis.validation.building_count} instances · ${study.analysis.inventory_counts.wall} walls · Hall depth ${study.analysis.town_hall_boundary_distance_tiles} tiles · maximum key anchors under declared disc: ${study.analysis.maximum_key_anchors_under_declared_disc}`;
  const access = study.wall_access;
  const caption = document.getElementById(`${name}-route-metrics`);
  const artifact = document.getElementById(`${name}-selected-artifact`);
  artifact.hidden = document.getElementById(`${name}-swap`).value !== "";
  artifact.href = study.artifact || `blueprint-${name}.json`;
  if (!access) {
    caption.textContent = "Route diagnostics have not been recomputed for this building swap. Export and inspect it with the CLI.";
    return;
  }
  const route = access.routes.find(item =>
    item.entry === document.getElementById("route-entry").value &&
    item.target === document.getElementById("route-target").value &&
    item.profile === document.getElementById("route-profile").value
  );
  const regions = access.wall_only_enclosed_region_sizes_tiles.length;
  caption.textContent = route.reachable
    ? `${regions} wall-only enclosed regions · route distance ${route.distance_tiles.toFixed(2)} tiles · ${route.wall_instances_crossed.length} wall tiles crossed. Static geometry; no attack score.`
    : `${regions} wall-only enclosed regions · target unreachable under the selected static profile with other buildings intact. No attack score.`;
  if (!document.getElementById("routes").checked || !route.reachable) {
    return;
  }
  context.strokeStyle = "#73efff";
  context.lineWidth = 4;
  context.beginPath();
  route.route_points.forEach((point, index) => {
    if (index === 0) {
      context.moveTo(point[0] * scale, point[1] * scale);
    } else {
      context.lineTo(point[0] * scale, point[1] * scale);
    }
  });
  context.stroke();
  context.strokeStyle = "#f29aff";
  for (const wallId of route.wall_instances_crossed) {
    const wall = study.blueprint.buildings.find(item => item.instance === wallId);
    context.strokeRect(wall.x * scale, wall.y * scale, scale, scale);
  }
}
function redraw() {
  draw("ranked");
  draw("war-cwl");
}
function locate(event, name) {
  const canvas = event.currentTarget;
  const rect = canvas.getBoundingClientRect();
  const blueprint = selectedCase(name).blueprint;
  const x = (event.clientX - rect.left) / rect.width * blueprint.width;
  const y = (event.clientY - rect.top) / rect.height * blueprint.height;
  return blueprint.buildings.find(building => {
    const entity = entities.get(building.id);
    if (entity.category === "wall" && !document.getElementById("walls").checked) {
      return false;
    }
    if (entity.category === "trap" && !document.getElementById("traps").checked) {
      return false;
    }
    const box = geometry(building);
    return x >= box.x && y >= box.y && x < box.x + box.width && y < box.y + box.height;
  });
}
for (const name of ["ranked","war-cwl"]) {
  const canvas = document.getElementById(`${name}-map`);
  canvas.addEventListener("mousemove", event => {
    const building = locate(event,name);
    canvas.title = building ? detail(building,name) : "Empty tile";
  });
  canvas.addEventListener("click", event => {
    const building = locate(event,name);
    document.getElementById("details").textContent = building ? detail(building,name) : `${name}: empty tile`;
  });
}
for (const id of ["walls", "traps", "grid", "anchor", "routes", "route-entry", "route-target", "route-profile"]) {
  document.getElementById(id).addEventListener("change", redraw);
}
function table() {
  const blueprint = selectedCase(document.getElementById("table-layout").value).blueprint;
  const query = document.getElementById("filter").value.toLowerCase();
  const rows = document.getElementById("rows");
  rows.replaceChildren();
  let count = 0;
  for (const building of blueprint.buildings) {
    if (!document.getElementById("table-walls").checked && building.id === "wall") {
      continue;
    }
    if (!building.instance.toLowerCase().includes(query)) {
      continue;
    }
    const tr = document.createElement("tr");
    const values = [
      building.instance,
      building.level === null ? "unlevelled" : building.level,
      `(${building.x}, ${building.y})`,
      [building.mode || "", JSON.stringify(building.settings || {})].join(" "),
      building.counts_for_destruction === null ? "unknown" : String(building.counts_for_destruction)
    ];
    for (const value of values) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }
    rows.append(tr);
    count += 1;
  }
  document.getElementById("row-count").textContent=`${count} matching instances`;
}
for (const id of ["table-layout", "filter", "table-walls"]) {
  const event = id === "filter" ? "input" : "change";
  document.getElementById(id).addEventListener(event, table);
}
redraw();
table();
</script></body></html>"""


def main():
    snapshot = read(ROOT / "data/catalog.json")
    entities = {item["entity"]["id"]: item["entity"] for item in snapshot["entries"]}
    cases = {}
    catalog = Catalog.load(ROOT / "data")
    for name in ("ranked", "war-cwl"):
        blueprint = read(ROOT / f"reports/blueprint-{name}.json")
        cases[name] = {
            "blueprint": blueprint,
            "analysis": read(ROOT / f"reports/blueprint-{name}-analysis.json"),
            "search": read(ROOT / f"reports/blueprint-{name}-swap-search.json"),
        }
        access, variants = wall_study(name, blueprint, catalog)
        cases[name]["wall_access"] = access
        cases[name]["wall_variants"] = variants
        svg_map(name, blueprint, entities)
    payload = {
        "cases": cases,
        "probes": read(ROOT / "examples/blueprint-probes-conditional.json"),
        "entities": [
            {
                "id": key,
                "category": value["category"],
                "size": value.get("size"),
                "label": LABELS.get(key, ""),
                "color": color(value),
            }
            for key, value in entities.items()
            if value.get("size")
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    destination = ROOT / "reports/blueprints.html"
    destination.write_text(PAGE.replace("__PAYLOAD__", encoded))
    print(f"Saved {destination} and both SVG maps")


if __name__ == "__main__":
    main()
