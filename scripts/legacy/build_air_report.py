"""Render declared air sectors without assigning whole-battle success rates."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text())


def report_data():
    cases = {}
    labels = {
        "electro": "E",
        "rider": "D",
        "entry-storage": "S1",
        "rear-storage": "S2",
        "ad-entry": "AD1",
        "ad-rear": "AD2",
        "archer": "AT",
    }
    for basis in ("per-impact", "total"):
        cases[basis] = {}
        for response in ("none", "timely", "late"):
            cases[basis][response] = {}
            for layout in ("compact", "separated"):
                result = read(
                    ROOT
                    / "reports/demo"
                    / f"entity-air-{layout}-{basis}-{response}.json"
                )
                sample = result["human_combat"]["samples"][0]
                combat = sample["combat"]
                cases[basis][response][layout] = {
                    "width": result["scene"]["width"],
                    "height": result["scene"]["height"],
                    "actors": [
                        {
                            key: actor[key]
                            for key in ("id", "kind", "width", "height", "hitpoints")
                        }
                        | {"label": labels[actor["id"]]}
                        for actor in result["scene"]["actors"]
                    ],
                    "frames": combat["frames"],
                    "trace": combat["trace"],
                    "final": combat["actors"],
                    "control": sample["control"],
                }
    return {
        "cases": cases,
        "resolution": read(ROOT / "reports/demo/air-resolution.json"),
        "quantity": read(ROOT / "reports/demo/air-death-quantity.json"),
    }


PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>Air defense diagnostics · Clash Lab</title>
  <style>
    :root { color-scheme:dark; --bg:#10151c; --panel:#18212c; --line:#344557;
      --text:#edf2f7; --muted:#b3c1cf; --accent:#70e3c2; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--text); font:16px/1.6 system-ui,sans-serif; }
    main { max-width:1180px; margin:auto; padding:28px 22px 70px; }
    h1 { font-size:clamp(30px,5vw,45px); line-height:1.15; }
    h2 { font-size:25px; line-height:1.3; margin:30px 0 15px; }
    h3 { font-size:19px; margin:0 0 12px; }
    p { margin:0 0 15px; }
    a { color:var(--accent); text-underline-offset:3px; }
    .muted, figcaption { color:var(--muted); }
    .card { padding:22px; border:1px solid var(--line); border-radius:10px; background:var(--panel); margin:18px 0; }
    .grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }
    figure { margin:0; }
    canvas { display:block; width:100%; border:1px solid var(--line); border-radius:7px; }
    figcaption { font-size:14px; margin:10px 0; }
    .controls { display:flex; align-items:center; flex-wrap:wrap; gap:10px; margin:18px 0; }
    select { background:#202d3c; color:var(--text); border:1px solid var(--line); border-radius:5px; padding:10px; font:inherit; }
    input[type=range] { width:180px; }
    .table-scroll { overflow:auto; }
    table { width:100%; border-collapse:collapse; }
    th, td { border-bottom:1px solid var(--line); padding:10px 8px; text-align:left; vertical-align:top; }
    th { color:var(--muted); font-size:14px; }
    .small { font-size:14px; }
    @media(max-width:720px) { .grid { grid-template-columns:1fr; } .card { padding:16px; } }
  </style>
</head>
<body>
<main>
  <p><a href="strategy.html">← Strategy and pipeline</a> · <a href="blueprints.html">Conditional full base drafts</a></p>
  <h1>Air defense diagnostics</h1>
  <p class="muted">One Electro Dragon7 and one Dragon Rider4 form the same55-space group in both layouts. Five structures retain identical levels and inventory. These arbitrary sectors are neither a full army nor your actual base; no stars, trophies, or triple probabilities are predicted.</p>
  <div class="card">
    <h2>Spacing and protection interact with the attack plan</h2>
    <p id="finding"></p>
    <p>The protection cue combines the Rider's HP with the rear Air Defense's selected target. A delayed command rechecks that relationship before spending the resource. These are synthetic responses to kernel state, not measured human vision or reactions.</p>
    <div class="controls">
      <label for="response">Response case</label>
      <select id="response"><option value="none">No intervention</option><option value="timely">Timely response</option><option value="late">Delayed response</option></select>
      <label for="quantity">Unresolved death quantity</label>
      <select id="quantity"><option value="per-impact">Snapshot value per test impact</option><option value="total">Snapshot value total for sequence</option></select>
      <label for="time">Synthetic time</label>
      <input id="time" type="range" min="0" max="40" step="0.1" value="9">
      <output id="time-label" for="time"></output>
    </div>
    <div class="grid">
      <figure><h3>Compact declared sector</h3><canvas id="compact" width="650" height="500" aria-label="Compact conditional air sector"></canvas><figcaption id="compact-caption"></figcaption></figure>
      <figure><h3>Separated declared sector</h3><canvas id="separated" width="650" height="500" aria-label="Separated conditional air sector"></canvas><figcaption id="separated-caption"></figcaption></figure>
    </div>
    <p class="small muted">E = Electro Dragon; D = Dragon Rider; AD1/AD2 = Air Defenses; AT = Archer Tower; S1/S2 = storages. Violet paths show recent recorded chain hits; orange rings show recent fixed death impacts; cyan circles show the applied generic Freeze. Crosses mark unit losses.</p>
    <div class="table-scroll"><table><thead><tr><th>Solver step</th><th>Layout</th><th>Rider lost at</th><th>Electro Dragon HP left</th><th>Structures remaining</th><th>Command</th></tr></thead><tbody id="study-rows"></tbody></table></div>
    <p class="small muted">The table filters36 runs by the selected response and quantity interpretation. Acceptance tolerance remains unspecified. Solver agreement does not certify game fidelity.</p>
    <p id="case-links"></p>
  </div>
  <div class="card">
    <h2>The quantity branch is inactive in these ordinary sector runs</h2>
    <p>The Electro Dragon survives all ordinary cases, so its death sequence is never emitted. Identical results across its two quantity interpretations therefore do not validate either interpretation. The Dragon Rider's crash is still emitted at its actual modeled defeat position.</p>
    <p>A separate artificial defeat diagnostic places three fixed test bolts over a Storage17 footprint. Per-impact and total-quantity branches produce different HP loss. The test does not establish the real bolt count, pattern, or mapping.</p>
    <table><thead><tr><th>Declared interpretation</th><th>Fixed test impacts</th><th>Storage HP after sequence</th><th>Requested damage per test impact</th></tr></thead><tbody id="quantity-rows"></tbody></table>
    <p>Supercell's <a href="https://supercell.com/en/games/clashofclans/blog/game-updates/december-2023-town-hall-16/">historical TH16 table</a> lists750 destruction damage for Electro Dragon7; the snapshot field is125. That difference may reflect different quantities or patch history. The ratio alone does not establish six bolts. The <a href="https://supercell.com/en/games/clashofclans/blog/game-updates/dragon-rider/">Dragon Rider introduction</a> also lists both target layers, while the snapshot lists ground. The latter is an explicitly selected hypothesis here.</p>
    <p><a href="demo/air-death-quantity.json">Quantity diagnostic summary</a> · <a href="demo/air-death-quantity-per-impact.json">Per-impact diagnostic</a> · <a href="demo/air-death-quantity-total.json">Total-quantity diagnostic</a></p>
  </div>
  <div class="card">
    <h2>Declared inputs and remaining validation</h2>
    <p>Chain range1, multipliers[1,0.8,0.6,0.4,0.2], instant shots, fixed three-bolt geometry, death delays/radii, and the two-second Freeze are diagnostic inputs. Absolute first-shot readiness is not a moving wind-up model. No random bolt offsets, unseen traps, heroes, equipment, pets, defending CC, Town Hall, or guardian behavior is supplied.</p>
    <p>For a useful friendly check, record a visible Electro Dragon lock and chain on the fixed TH16 layout, then its defeat and individual lightning impacts. Bind replay speed and game-clock anchors, troop/defense levels, protection and other damage sources. Ambiguous impacts stay unknown. Separate held-out footage is required before trusting predictions.</p>
    <p><a href="../examples/entity-air-compact-conditional.json">Compact sector inputs</a> · <a href="../examples/entity-air-separated-conditional.json">Separated sector inputs</a> · <a href="../examples/entity-air-compact-plan-synthetic.json">Compact protection plan</a> · <a href="../examples/entity-air-separated-plan-synthetic.json">Separated protection plan</a> · <a href="demo/air-resolution.json">Complete36-case study</a> · <a href="../data/mechanics-claims.json">Source claims and unresolved semantics</a> · <a href="friendly-defense-tests.html">Friendly test sheet</a></p>
  </div>
</main>
<script id="air-data" type="application/json">__DATA__</script>
<script>
  "use strict";
  const data = JSON.parse(document.getElementById("air-data").textContent);
  const response = document.getElementById("response");
  const quantity = document.getElementById("quantity");
  const slider = document.getElementById("time");

  function frameAt(study, time) {
    let selected = study.frames[0];
    for (const frame of study.frames) {
      if (frame.time_seconds <= time + 0.00001) {
        selected = frame;
      }
    }
    return selected;
  }

  function actorPoint(actor, state) {
    return [state.x + actor.width / 2, state.y + actor.height / 2];
  }

  function drawCase(layout, time) {
    const study = data.cases[quantity.value][response.value][layout];
    const frame = frameAt(study, time);
    const actors = Object.fromEntries(study.actors.map(actor => [actor.id, actor]));
    const canvas = document.getElementById(layout);
    const context = canvas.getContext("2d");
    const scale = canvas.width / study.width;
    context.fillStyle = "#111923";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.strokeStyle = "#24313f";
    context.lineWidth = 1;
    for (let x = 0; x <= study.width; x += 1) {
      context.beginPath();
      context.moveTo(x * scale, 0);
      context.lineTo(x * scale, canvas.height);
      context.stroke();
    }
    for (let y = 0; y <= study.height; y += 1) {
      context.beginPath();
      context.moveTo(0, y * scale);
      context.lineTo(canvas.width, y * scale);
      context.stroke();
    }
    for (const actor of study.actors) {
      const state = frame.actors[actor.id];
      const [x, y] = actorPoint(actor, state).map(value => value * scale);
      if (actor.kind !== "unit") {
        if (state.hp <= 0) {
          continue;
        }
        context.fillStyle = actor.kind === "defense" ? "#a1454f" : "#4c6384";
        context.fillRect(state.x * scale + 2, state.y * scale + 2, actor.width * scale - 4, actor.height * scale - 4);
      } else {
        context.strokeStyle = actor.id === "electro" ? "#cdb8ff" : "#ffd18b";
        context.fillStyle = context.strokeStyle;
        context.lineWidth = 3;
        context.beginPath();
        context.arc(x, y, 11, 0, Math.PI * 2);
        if (state.active) {
          context.fill();
        } else {
          context.stroke();
          context.beginPath();
          context.moveTo(x - 8, y - 8);
          context.lineTo(x + 8, y + 8);
          context.moveTo(x + 8, y - 8);
          context.lineTo(x - 8, y + 8);
          context.stroke();
        }
      }
      context.fillStyle = "#ffffff";
      context.font = "16px system-ui";
      context.textAlign = "center";
      context.fillText(actor.label, x, actor.kind === "unit" ? y - 18 : y + 5);
    }
    const previousTargets = new Map();
    for (const event of study.trace) {
      if (event.time_seconds > time + 0.00001 || time - event.time_seconds > 0.6) {
        continue;
      }
      if (event.event === "projectile_impact" && event.source === "electro") {
        const impactFrame = frameAt(study, event.time_seconds);
        const key = event.time_seconds;
        const sourceId = event.chain_index === 0 ? "electro" : previousTargets.get(key);
        if (!sourceId) {
          continue;
        }
        const first = actorPoint(actors[sourceId], impactFrame.actors[sourceId]);
        const second = actorPoint(actors[event.target], impactFrame.actors[event.target]);
        context.strokeStyle = "#cdb8ff";
        context.lineWidth = 3;
        context.beginPath();
        context.moveTo(first[0] * scale, first[1] * scale);
        context.lineTo(second[0] * scale, second[1] * scale);
        context.stroke();
        previousTargets.set(key, event.target);
      } else if (event.event === "death_effect_impact") {
        context.strokeStyle = "#ffac69";
        context.lineWidth = 3;
        context.beginPath();
        context.arc(event.area.x * scale, event.area.y * scale, event.area.radius * scale, 0, Math.PI * 2);
        context.stroke();
      }
    }
    for (const action of study.control.actions) {
      if (action.status !== "command_applied" || time < action.time_seconds || time >= action.time_seconds + 2) {
        continue;
      }
      const area = action.commanded_area;
      context.strokeStyle = "#73efff";
      context.lineWidth = 3;
      context.beginPath();
      context.arc(area.x * scale, area.y * scale, area.radius * scale, 0, Math.PI * 2);
      context.stroke();
    }
    const remaining = study.actors.filter(actor => actor.kind !== "unit" && frame.actors[actor.id].hp > 0).length;
    document.getElementById(`${layout}-caption`).textContent =
      `E HP: ${Math.round(frame.actors.electro.hp)} · D HP: ${Math.round(frame.actors.rider.hp)} · Structures standing: ${remaining} / 5`;
  }

  function appendRow(parent, values) {
    const row = document.createElement("tr");
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    parent.append(row);
  }

  function commandStatus(control) {
    if (control.actions.length) {
      return control.actions.map(action => action.status.replaceAll("_", " ")).join(", ");
    }
    return control.actions_pending_at_horizon.length ? "pending at horizon" : "cue not observed";
  }

  function update() {
    const time = Number(slider.value);
    document.getElementById("time-label").textContent = `${time.toFixed(1)} s`;
    drawCase("compact", time);
    drawCase("separated", time);
    const rows = document.getElementById("study-rows");
    rows.replaceChildren();
    for (const studyCase of data.resolution.cases) {
      if (studyCase.death_statistic_basis !== quantity.value || studyCase.response_fixture !== response.value) {
        continue;
      }
      const remaining = Object.values(studyCase.structure_hp_at_horizon).filter(hp => hp > 0).length;
      const death = studyCase.unit_death_times.rider;
      appendRow(rows, [studyCase.maximum_step_seconds.toFixed(3), studyCase.layout,
        death === null ? "alive at horizon" : `${death.toFixed(2)} s`,
        Math.round(studyCase.unit_hp_at_horizon.electro), `${remaining} / 5`, commandStatus(studyCase.control)]);
    }
    const links = document.getElementById("case-links");
    links.replaceChildren();
    for (const layout of ["compact", "separated"]) {
      const link = document.createElement("a");
      link.href = `demo/entity-air-${layout}-${quantity.value}-${response.value}.json`;
      link.textContent = `${layout} selected case`;
      if (links.childNodes.length) {
        links.append(document.createTextNode(" · "));
      }
      links.append(link);
    }
  }
  response.addEventListener("change", update);
  quantity.addEventListener("change", update);
  slider.addEventListener("input", update);

  const compact = data.cases["per-impact"].none.compact.final;
  const separated = data.cases["per-impact"].none.separated.final;
  document.getElementById("finding").textContent =
    `The baseline clears both declared sectors. The separated case leaves the Electro Dragon with ${Math.round(separated.electro.hp)} HP versus ${Math.round(compact.electro.hp)} in the compact case. Breaking the first chain does not by itself establish stronger defense: travel, defense targeting and crash position also change.`;
  for (const diagnostic of data.quantity.cases) {
    appendRow(document.getElementById("quantity-rows"), [diagnostic.basis, diagnostic.impact_count,
      diagnostic.remaining_storage_hp.toFixed(2), diagnostic.death_impacts.map(event => event.requested_damage_per_target.toFixed(2)).join(" / ")]);
  }
  update();
</script>
</body>
</html>
"""


def main():
    payload = json.dumps(report_data(), ensure_ascii=False).replace("<", "\\u003c")
    destination = ROOT / "reports/air-defense.html"
    destination.write_text(PAGE.replace("__DATA__", payload), encoding="utf-8")
    print(f"Saved {destination}")


if __name__ == "__main__":
    main()
