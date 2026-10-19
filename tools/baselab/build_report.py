"""Build the results report page (output/report/index.html) from run outputs.

Every number on the page is read from: output/final-defense.json,
output/army-recommendations-typical.json, output/army-recommendations.json,
data/baselab-calibration.json and the base layouts.

Usage: python tools/baselab/build_report.py
"""

from __future__ import annotations

import html
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.layout import Layout  # noqa: E402
from baselab.mechanics import BUILDING_TYPES, TRAP_NAMES  # noqa: E402

OUT = ROOT / "output" / "report"

ARMY_NAMES = {
    "throwers": "Mass Throwers + Healers",
    "hydra": "Hydra (Dragons + Dragon Riders)",
    "rootrider": "Root Riders + Valkyries",
    "edrag": "Electro Dragons",
    "hydra_portal": "Hydra + Portal Pendant",
    "rr_throwers": "Root Riders + Throwers (new)",
    "druid_rr": "Your Druid / Root Rider army",
    "rocket_minion": "Your Rocket Balloon / Super Minion army",
}
BASE_NAMES = {
    "ranked-winner": "New ranked base",
    "war-winner": "New war base",
    "your-base": "Your current base",
    "real-l1x": "Human base l1x",
    "real-l3x": "Human base l3x",
    "real-l5x": "Human base l5x",
    "real-l6x": "Human base l6x",
}


def e(s):
    return html.escape(str(s))


def pct(v):
    return f"{100 * v:.0f}%"


def defense_table(fd):
    sets = [("ranked", "Electro (ranked now)"), ("ranked_legend3", "Legend III"), ("ranked_legend1", "Legend I"), ("war", "War (TH16 attackers)")]
    rows = []
    for key in ("ranked-winner", "war-winner", "your-base", "real-l3x", "real-l5x", "real-l6x", "real-l1x"):
        r = fd[key]
        cls = ' class="hi"' if key in ("ranked-winner", "war-winner") else (' class="you"' if key == "your-base" else "")
        cells = "".join(
            f'<td><span class="big">{r[s]["defender_trophies"]:.1f}</span><span class="sub">{pct(r[s]["three_star"])} 3★ · TH down {pct(r[s]["th_killed"])}</span></td>'
            for s, _ in sets
        )
        holes = r.get("holes", 0)
        cells += f'<td class="num">{holes}</td>'
        rows.append(f"<tr{cls}><th scope=\"row\">{e(BASE_NAMES[key])}</th>{cells}</tr>")
    head = "".join(f"<th scope=\"col\">{e(n)}</th>" for _, n in sets) + '<th scope="col">Drop holes inside walls</th>'
    return f'<div class="scroll"><table class="def"><thead><tr><th scope="col">Base</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def per_army_table(fd, key, sname):
    pa = fd[key][sname]["per_army"]
    rows = []
    for k in sorted(pa, key=lambda k: (k.split("@")[1], k)):
        v = pa[k]
        army, th = k.split("@")
        rows.append(f"<tr><td>{e(ARMY_NAMES.get(army, army))}</td><td>{e(th)}</td><td class=\"num\">{v['troph']:.1f}</td><td class=\"num\">{pct(v['three'])}</td><td class=\"num\">{v['stars']:.2f}</td><td class=\"num\">{v['pct']:.0f}%</td></tr>")
    return ('<div class="scroll"><table class="mini"><thead><tr><th>Attacking army</th><th>TH</th><th>Trophies you keep</th><th>3★</th><th>Avg ★</th><th>Avg %</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def attack_table(rec):
    cols = [("TH16/none", "TH16"), ("TH17/none", "TH17"), ("TH18/none", "TH18"), ("TH16/legend1", "TH16 · Legend I"), ("TH17/legend1", "TH17 · Legend I"), ("TH18/legend1", "TH18 · Legend I")]
    order = sorted(rec["armies"], key=lambda n: -(rec["armies"][n]["results"]["TH16/none"]["avg_stars"] + rec["armies"][n]["results"]["TH17/none"]["avg_stars"]))
    rows = []
    for n in order:
        r = rec["armies"][n]["results"]
        cls = ' class="hi"' if n == order[0] else ""
        cells = "".join(f'<td><span class="big">{r[c]["avg_stars"]:.2f}★</span><span class="sub">{pct(r[c]["three_star"])} 3★ · {r[c]["avg_destruction"]:.0f}%</span></td>' for c, _ in cols)
        rows.append(f"<tr{cls}><th scope=\"row\">{e(ARMY_NAMES.get(n, n))}</th>{cells}</tr>")
    head = "".join(f"<th scope=\"col\">{e(h)}</th>" for _, h in cols)
    return f'<div class="scroll"><table class="def"><thead><tr><th scope="col">Army (your levels)</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>', order


def settings(lay: Layout):
    modes = {}
    for b in lay.buildings:
        if b.mode:
            modes.setdefault(BUILDING_TYPES[b.key].name, []).append(b.mode)
    sk_air = sum(1 for t in lay.traps if t.key == "skeleton" and t.mode == "air")
    sk = sum(1 for t in lay.traps if t.key == "skeleton")
    items = [f"<li><b>{e(k)}</b>: {e(', '.join(v))}</li>" for k, v in sorted(modes.items())]
    items.append(f"<li><b>Skeleton Traps</b>: {sk_air} air, {sk - sk_air} ground</li>")
    items.append(f"<li><b>Clan Castle (as simulated)</b>: {e(', '.join(lay.cc_troops))}</li>")
    return "<ul class=\"settings\">" + "".join(items) + "</ul>"


def build_list(lay: Layout):
    rows = []
    for b in sorted(lay.buildings, key=lambda b: (BUILDING_TYPES[b.key].kind != "defense", BUILDING_TYPES[b.key].name, b.x, b.y)):
        bt = BUILDING_TYPES[b.key]
        rows.append(f"<tr><td>{e(bt.name)}</td><td class=\"num\">{b.x}</td><td class=\"num\">{b.y}</td><td class=\"num\">{bt.size}×{bt.size}</td><td>{e(b.mode or '')}</td></tr>")
    for t in sorted(lay.traps, key=lambda t: (TRAP_NAMES[t.key], t.x, t.y)):
        rows.append(f"<tr class=\"trap\"><td>{e(TRAP_NAMES[t.key])}</td><td class=\"num\">{t.x}</td><td class=\"num\">{t.y}</td><td class=\"num\">{2 if t.key in ('giant', 'giga') else 1}×{2 if t.key in ('giant', 'giga') else 1}</td><td>{e(t.mode or '')}</td></tr>")
    walls = ", ".join(f"({x},{y})" for x, y in sorted(lay.walls))
    return ('<details><summary>Build list: every building and trap with its tile</summary>'
            '<p class="note">Tile (x, y): (0, 0) is the top corner of the village; x runs down-right, y runs down-left; a building of size s covers x…x+s−1 and y…y+s−1. The grid labels on the picture use the same numbers.</p>'
            '<div class="scroll"><table class="mini"><thead><tr><th>Building / trap</th><th>x</th><th>y</th><th>Size</th><th>Mode</th></tr></thead><tbody>'
            + "".join(rows) + f'</tbody></table></div><p class="note"><b>{len(lay.walls)} walls</b>: {walls}</p></details>')


def main():
    sys.path.insert(0, str(ROOT / "tools" / "baselab"))
    from army_guide import card  # noqa: E402
    from recommend_armies import CANDIDATES, account, personalise  # noqa: E402

    OUT.mkdir(parents=True, exist_ok=True)
    fd = json.loads((ROOT / "output" / "final-defense.json").read_text())
    rec = json.loads((ROOT / "output" / "army-recommendations-typical.json").read_text())
    l1x_test = json.loads((ROOT / "output" / "thrower-base" / "attack-l1x.json").read_text())
    cal = json.loads((ROOT / "data" / "baselab-calibration.json").read_text())
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    ranked = Layout.load(ROOT / "output" / "bases" / "ranked-winner.json")
    war = Layout.load(ROOT / "output" / "bases" / "war-winner.json")
    yours = Layout.load(ROOT / "data" / "reference-bases" / "your-base.json")
    for src, dst in ((ROOT / "output" / "bases" / "ranked-winner.png", "ranked-base.png"), (ROOT / "output" / "bases" / "war-winner.png", "war-base.png"),
                     (ROOT / "data" / "reference-bases" / "your-base.png", "your-base.png")):
        shutil.copy(src, OUT / dst)
    atk_table, order = attack_table(rec)
    best = order[0]
    lv = account(16)
    cards = []
    for k, name in enumerate(order):
        plan = personalise(CANDIDATES[name][0](town_hall=16), lv)
        r16 = rec["armies"][name]["results"]["TH16/none"]
        cards.append(f'<details{" open" if k == 0 else ""}><summary>{e(ARMY_NAMES[name])} · {r16["avg_stars"]:.2f}★ avg on TH16, {pct(r16["three_star"])} three-stars</summary>{card(plan, lv)}</details>')
    l1x_rows = []
    for name, a in sorted(l1x_test["armies"].items(), key=lambda kv: -kv[1]["results"]["TH16/legend1"]["avg_stars"]):
        r = a["results"]
        l1x_rows.append(f"<tr><td>{e(ARMY_NAMES[name])}</td>" + "".join(
            f'<td><span class="big">{r[c]["avg_stars"]:.2f}★</span><span class="sub">{pct(r[c]["three_star"])} 3★ · {r[c]["avg_destruction"]:.0f}%</span></td>' for c in ("TH16/none", "TH16/legend1")) + "</tr>")
    r, w, y = fd["ranked-winner"], fd["war-winner"], fd["your-base"]
    th16, th17 = rec["armies"][best]["results"]["TH16/none"], rec["armies"][best]["results"]["TH17/none"]
    weak = [k for k, v in own["levels"].items() if k in ("ad", "xbow", "inferno", "scatter", "tesla", "wt", "mortar", "bt", "cc", "ric")]
    def tile(kind, lay, key, sname, y_s):
        v = fd[key][sname]
        yv = fd["your-base"][sname]
        if lay.name == "your-base" or v["defender_trophies"] - yv["defender_trophies"] < 0.5:
            return (f'<div class="tile"><span class="k">{kind} base</span><span class="v">Keep yours <small>for now</small></span>'
                    f'<p>No layout tested beat your current base here: {yv["defender_trophies"]:.1f} trophies kept, {pct(yv["three_star"])} three-starred. A deeper search is running.</p></div>')
        return (f'<div class="tile"><span class="k">{kind} base</span><span class="v">{v["defender_trophies"]:.1f} <small>trophies kept per defense</small></span>'
                f'<p>Your current base keeps {yv["defender_trophies"]:.1f}. Three-starred {pct(v["three_star"])} of the time, against {pct(yv["three_star"])} for your current base. Open drop tiles inside its walls: {fd[key]["holes"]}.</p></div>')

    r_tile = tile("Ranked", ranked, "ranked-winner", "ranked", None)
    w_tile = tile("War", war, "war-winner", "war", None)
    page = TEMPLATE_HEAD + BODY.format(r_tile=r_tile, w_tile=w_tile, 
        r_troph=f"{r['ranked']['defender_trophies']:.1f}", r_3=pct(r["ranked"]["three_star"]),
        y_troph=f"{y['ranked']['defender_trophies']:.1f}", y_3=pct(y["ranked"]["three_star"]),
        w_3=pct(w["war"]["three_star"]), yw_3=pct(y["war"]["three_star"]), w_troph=f"{w['war']['defender_trophies']:.1f}",
        best=e(ARMY_NAMES[best]), b16=f"{th16['avg_stars']:.2f}", b16_3=pct(th16["three_star"]), b17=f"{th17['avg_stars']:.2f}", b17_3=pct(th17["three_star"]),
        defense_table=defense_table(fd),
        ranked_settings=settings(ranked), war_settings=settings(war), your_settings=settings(yours),
        ranked_build=build_list(ranked), war_build=build_list(war),
        ranked_per_army=per_army_table(fd, "ranked-winner", "ranked"), war_per_army=per_army_table(fd, "war-winner", "war"),
        attack_table=atk_table, cards="".join(cards), l1x_rows="".join(l1x_rows),
        k_hydra=cal["hydra"]["strength"], k_edrag=cal["edrag"]["strength"], k_thr=cal["throwers"]["strength"], k_rr=cal["rootrider"]["strength"],
        log_troph=f"{y['logmix']['defender_trophies']:.1f}", log_3=pct(y["logmix"]["three_star"]), log_th=pct(y["logmix"]["th_killed"]),
        holes_r=fd["ranked-winner"]["holes"], holes_w=fd["war-winner"]["holes"], holes_y=fd["your-base"]["holes"],
        your_levels=", ".join(f"{BUILDING_TYPES[k].name} {own['levels'][k]}" for k in sorted(weak)),
    )
    (OUT / "index.html").write_text(page, encoding="utf-8")
    print("wrote", OUT / "index.html")


TEMPLATE_HEAD = """<title>Clash Lab TH16 Results</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: one reading column of verdict tiles, comparison tables and base plans; plans break wider than the text */
:root {
  --bg: #f3f4ef; --surface: #ffffff; --ink: #1d2420; --muted: #5b665e; --line: #d9ddd3;
  --accent: #6b3fd4; --accent-soft: #ece6fb; --good: #1f7a4d; --good-soft: #e3f3ea; --you: #a35a00; --you-soft: #fbefdc;
  --display: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif;
  --body: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #121614; --surface: #1a201c; --ink: #e6ebe4; --muted: #9aa69c; --line: #2c352f;
  --accent: #a98bff; --accent-soft: #2a2340; --good: #5fd39a; --good-soft: #17301f; --you: #f0a54a; --you-soft: #33260f; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #121614; --surface: #1a201c; --ink: #e6ebe4; --muted: #9aa69c; --line: #2c352f;
  --accent: #a98bff; --accent-soft: #2a2340; --good: #5fd39a; --good-soft: #17301f; --you: #f0a54a; --you-soft: #33260f; color-scheme: dark; }
body { background: var(--bg); color: var(--ink); font: 400 15px/1.6 var(--body); }
.wrap { max-width: 1080px; margin: 0 auto; padding-inline: 20px; padding-block: 40px 80px; display: grid; gap: 56px; }
header { display: grid; gap: 10px; }
.eyebrow { font: 500 12px/1 var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
h1 { font: 800 clamp(30px, 5vw, 48px)/1.05 var(--display); margin: 0; text-wrap: balance; letter-spacing: -.01em; }
h2 { font: 700 26px/1.2 var(--display); margin: 0 0 6px; text-wrap: balance; }
h3 { font: 600 18px/1.3 var(--body); margin: 0; }
p { margin: 0; max-width: 68ch; }
.lede { font-size: 17px; color: var(--muted); }
section { display: grid; gap: 18px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }
.tile { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 18px; display: grid; gap: 8px; align-content: start; min-width: 0; }
.tile .k { font: 500 12px/1 var(--mono); letter-spacing: .06em; text-transform: uppercase; color: var(--accent); }
.tile .v { font: 800 30px/1.1 var(--display); font-variant-numeric: tabular-nums; }
.tile .v small { font: 500 15px var(--body); color: var(--muted); }
.tile p { font-size: 14px; color: var(--muted); }
.scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
thead th { font: 500 12px/1.3 var(--mono); letter-spacing: .04em; text-transform: uppercase; color: var(--muted); white-space: nowrap; }
tbody tr:last-child > * { border-bottom: 0; }
table.def td { min-width: 128px; }
.big { display: block; font: 600 18px/1.2 var(--mono); }
.sub { display: block; font-size: 12.5px; color: var(--muted); white-space: nowrap; }
tr.hi { background: var(--good-soft); } tr.hi th { color: var(--good); }
tr.you { background: var(--you-soft); } tr.you th { color: var(--you); }
table.mini td, table.mini th { padding: 6px 10px; font-size: 13.5px; }
.num { font-family: var(--mono); text-align: right; }
tr.trap td { color: var(--muted); }
.plan { display: grid; gap: 14px; }
.plan img { width: 100%; height: auto; border-radius: 10px; border: 1px solid var(--line); background: var(--surface); }
.plan-meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }
.plan-meta > div { min-width: 0; display: grid; gap: 8px; align-content: start; }
ul { margin: 0; padding-left: 20px; display: grid; gap: 4px; }
.settings li { font-size: 14px; }
details { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
details[open] { display: grid; gap: 12px; }
summary { cursor: pointer; font-weight: 600; color: var(--accent); }
summary:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.note { font-size: 13.5px; color: var(--muted); }
.callout { background: var(--accent-soft); border-radius: 10px; padding: 16px 18px; display: grid; gap: 8px; }
.cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }
.cols > div { min-width: 0; display: grid; gap: 10px; align-content: start; }
a { color: var(--accent); }

.army { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
.army-block { display: grid; gap: 8px; align-content: start; min-width: 0; }
h4 { font: 600 14px/1.3 var(--body); margin: 0; color: var(--accent); }
ol.steps { margin: 0; padding-left: 22px; display: grid; gap: 8px; max-width: 78ch; }
ol.steps ul { margin-top: 6px; }
</style>
"""


BODY = """
<div class="wrap">
<header>
  <span class="eyebrow">jdawzzy · TH16 · Electro 31 · simulated 15 Oct 2026</span>
  <h1>Clash Lab TH16 Results</h1>
  <p class="lede">A ranked base, a war base and an attack plan for your account. Every number comes from battles the base search never saw. The simulator models every troop, spell, hero, equipment piece, pet, defense, trap, Crafted Defense and TH18 Guardian at current game stats, and it uses your real building and hero levels.</p>
</header>

<section aria-labelledby="verdict">
  <h2 id="verdict">The short version</h2>
  <div class="tiles">
    {r_tile}
    {w_tile}
    <div class="tile"><span class="k">Attack with</span><span class="v">{best}</span><p>At your levels: {b16} stars on average against TH16 ({b16_3} three-stars) and {b17} against TH17 ({b17_3}). Best of the 8 armies tested. The full army and a step-by-step plan are below.</p></div>
  </div>
</section>

<section aria-labelledby="defense">
  <h2 id="defense">Defense: how each base holds up</h2>
  <p>The large number is trophies you keep per ranked defense, out of 40 (40 minus what the attacker takes). Below it: three-star rate and how often the Town Hall falls. Attackers scout two sides and attack the better one, as real players do.</p>
  <ul>
    <li><b>Ranked:</b> the live TH17/TH18 meta (Hydra, Throwers, E-Drag, Root Riders), weighted by how often each army is used. Each is built from a real attack on your base as a legal loadout: 320–352 camp space, 50–55 Clan Castle troops, spells and Clan Castle spells.</li>
    <li><b>Legend III and Legend I:</b> the same attacks with Supercell's difficulty modifiers. Legend I gives defenses +20% damage and cuts attacking heroes by 20%.</li>
    <li><b>War:</b> TH16 attackers.</li>
  </ul>
  {defense_table}
  <p class="note">Each cell is 192 battles (96 for war): 12 approach angles × 2 skill seeds per army, then scored with the scouting model. The "saved layout" rows are bases recovered from your game's layout slots; l1x is the thrower base you sent.</p>
</section>

<section aria-labelledby="ranked">
  <h2 id="ranked">Ranked base</h2>
  <div class="plan">
    <img src="ranked-base.png" alt="Isometric plan of the recommended TH16 ranked base, with tile coordinates on the edges">
    <div class="plan-meta">
      <div><h3>Settings</h3>{ranked_settings}</div>
      <div><h3>Against each army</h3>{ranked_per_army}</div>
    </div>
    {ranked_build}
  </div>
</section>

<section aria-labelledby="war">
  <h2 id="war">War base</h2>
  <div class="plan">
    <img src="war-base.png" alt="Isometric plan of the recommended TH16 war base">
    <div class="plan-meta">
      <div><h3>Settings</h3>{war_settings}</div>
      <div><h3>Against each army</h3>{war_per_army}</div>
    </div>
    {war_build}
  </div>
</section>

<section aria-labelledby="current">
  <h2 id="current">Your current base, checked against reality</h2>
  <div class="cols">
    <div>
      <p>Rebuilt from game-memory slot <code>l4x</code> and checked tile by tile against your screenshot IMG_4219. The memory slot also holds your real building levels, and your Town Hall reads exactly 16, which confirms the decoding. These defenses are one level below the TH16 cap: {your_levels}. Walls are mostly level 16.</p>
      <p><b>Against the attacks you actually got</b> (5 TH16s and 8 TH17s): the simulator gives <b>{log_troph} trophies per defense, {log_3} three-starred, Town Hall down {log_th}.</b> Your real log shows about 5 trophies, 77% three-starred and the Town Hall down 85%.</p>
      <p>Open drop tiles inside your walls: {holes_y}. Your Cake-A-Pult fills a 3×3 gap in your core; without it, the simulator three-stars your base 86% of the time.</p>
      {your_settings}
    </div>
    <img src="your-base.png" alt="Isometric plan of your current base as digitized" style="width:100%;border-radius:10px;border:1px solid var(--line)">
  </div>
</section>

<section aria-labelledby="attack">
  <h2 id="attack">Attack: what to bring</h2>
  <p>Every army runs at your real levels from the Clash API: heroes, equipment, pets, troops and spells, including Portal Pendant at level 1. The targets are your four saved TH16 layouts plus three generated TH17 and three TH18 bases. The large number is average stars, with three-star rate and destruction below it.</p>
  {attack_table}
  <h3>Every army in full</h3>
  <p class="note">Each card lists the army camps, Clan Castle request, spells, Clan Castle spells and hero loadout, then the attack in order: funnel, push, spells, abilities and cleanup. These are the exact rules the simulated attacker follows, so the steps and the results match.</p>
  {cards}
</section>

<section aria-labelledby="l1x">
  <h2 id="l1x">The thrower base you can't three-star at Legend I</h2>
  <p>It's your saved layout l1x. Single wall pieces spaced two tiles apart cover all of its open ground. Each one blocks deploys within one tile, so every army has to drop at the map edge and walk in, and no single defense is a weak point. 16 attacks per army:</p>
  <div class="scroll"><table class="def"><thead><tr><th>Army (your levels)</th><th>Electro</th><th>Legend I</th></tr></thead><tbody>{l1x_rows}</tbody></table></div>
  <p class="note">The Legend I modifier is what makes the difference, which matches your experience.</p>
</section>

<section aria-labelledby="trust">
  <h2 id="trust">How far to trust this</h2>
  <div class="cols">
    <div>
      <h3>Checked</h3>
      <ul>
        <li>Every defense's delivered DPS matches its wiki table within about 3%, Crafted Defenses included.</li>
        <li>All 111 units, 20 spells and 55 equipment pieces and pets run without errors. Stats come from the game files and current wiki tables.</li>
        <li>On your own base, at your real levels, the simulator reproduces your real ranked defenses.</li>
        <li>Calibrated to TrophyCoach's real three-star rates with near face-value strength: Hydra {k_hydra}, E-Drag {k_edrag}, Throwers {k_thr}, Root Riders {k_rr}.</li>
        <li>Attackers drop into any gap of 3×3 tiles or more, use drop space that opens as buildings fall, and scout two sides.</li>
      </ul>
    </div>
    <div>
      <h3>Limits</h3>
      <ul>
        <li>Your Cake-A-Pult module levels aren't in game memory; level 3 is assumed, and it changes little.</li>
        <li>About 15 game values the wiki doesn't publish are educated guesses: trap fuse delays, some pet cooldowns and a few equipment durations. They're listed in the repo.</li>
        <li>Your logged attacks are only 13, so the real-world check has wide error bars.</li>
        <li>Before using a new base in war, test it in a few friendly challenges against clanmates who run these armies.</li>
      </ul>
    </div>
  </div>
</section>
</div>
"""


if __name__ == "__main__":
    main()
