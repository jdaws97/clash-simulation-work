"""Replay the user's real ranked defenses in the sim: the accuracy test.

Each defense in the live battle log comes with the attacker's exact army
(share code). For every one, the sim plays that army (attacker Town Hall's
max levels, as their levels are unknown) against the base that was up,
from every side and several skill seeds, with scouting and technique choice
as in evaluate.py. It reports the sim's predicted 3-star chance, expected
stars and destruction next to what really happened, and summary errors:

  Brier score on 3-star (lower is better; 0.25 = coin flip)
  mean absolute error on destruction %
  calibration: mean predicted 3-star vs real 3-star rate

Each defense is replayed on the layout that was up that day, from
data/live/base-history.json (days with no known layout are skipped and
listed); --base replays every defense on one layout instead.

Usage: python tools/baselab/replay_log.py BATTLELOG.json [--base data/reference-bases/your-base.json]
       [--since 20261012] [--until 20261016] [--seeds 3] [--techniques] [--strength calibrated|raw]
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.evaluate import SCOUT, STRENGTH, apply_charge, attacker_trophies, pool, skill, techniques  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.meta_armies import SPELL_KEYS  # noqa: E402
from decode_battlelog import decode  # noqa: E402


def to_build(army: dict, th: int, n: int) -> tuple[dict, list]:
    """A meta_armies build dict from a decoded share code. Returns (build,
    names the engine does not know)."""
    unknown = []
    troops = {t: c for c, t in army.get("troops", [])}
    spells = {}
    for c, s in army.get("spells", []):
        if s in SPELL_KEYS:
            spells[s] = spells.get(s, 0) + c
        else:
            unknown.append(s)
    cc = {}
    for c, t in army.get("cc_troops", []) + army.get("cc_spells", []):
        if t.endswith("Spell") and t not in SPELL_KEYS:
            unknown.append(t)
            continue
        cc[t] = cc.get(t, 0) + c
    heroes, loadouts = [], {}
    for h in army.get("heroes", []):
        if h["hero"].startswith(("hero#", "unparsed:")):
            unknown.append(h["hero"])
            continue
        heroes.append(h["hero"])
        eq = [e for e in h.get("equipment", []) if not e.startswith("equipment#")]
        unknown += [e for e in h.get("equipment", []) if e.startswith("equipment#")]
        pet = h.get("pet")
        if pet and pet.startswith("pet#"):
            unknown.append(pet)
            pet = None
        # the log is the truth: a hero shown without equipment or pet gets
        # none, never the sim's default loadout (it could clash with another
        # hero's real pet)
        loadouts[h["hero"]] = (eq + [None, None])[:2] + [pet]
    for t in troops:
        if t.startswith("troop#"):
            unknown.append(t)
    build = {"archetype": f"log-{n}", "build": 1, "th": th, "share": 1.0, "three_star": 0.0,
             "troops": {t: c for t, c in troops.items() if not t.startswith("troop#")},
             "spells": spells, "cc": cc, "heroes": heroes, "loadouts": loadouts}
    return build, unknown


def _run(args):
    lj, build, angle, seed, strength, tech = args
    from baselab.engine.battle import Battle
    from baselab.meta_armies import plan_for_build

    plan = plan_for_build(build, angle=angle, seed=seed)
    plan.observed = True  # a real army from the battle log
    if tech is not None:
        apply_charge(plan, tech)
    plan.strength = strength * skill(seed)
    r = Battle(Layout.from_json(lj), plan, seed=seed, town_hall=16).run()
    return r.stars, r.destruction, r.time


def family_strength(build) -> float:
    """Calibrated strength of the closest meta archetype (by main troop)."""
    t = build["troops"]
    key = None
    if "Root Rider" in t:
        key = "root-rider"
    elif "Thrower" in t:
        key = "mass-thrower"
    elif "Electro Dragon" in t:
        key = "e-drag-spam"
    elif "Dragon" in t:
        key = "mass-dragons"
    if key is None:
        return 1.0
    vals = [v for k, v in STRENGTH.items() if k.startswith(f"meta:{key}-16-")]
    return sum(vals) / len(vals) if vals else 1.0


HISTORY = ROOT / "data" / "live" / "base-history.json"


def base_for_day(periods: list, day: str):
    """The layout up on a battle day ("YYYYMMDD", the log's UTC date) from
    the base-history periods (inclusive; "to": null = still up). None when
    no period covers the day or its layout is unknown."""
    d = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
    for p in periods:
        if p["from"] <= d and (p.get("to") is None or d <= p["to"]):
            return p.get("layout")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--base", help="replay every defense on this layout (default: the layout up that day, base-history.json)")
    ap.add_argument("--since", default="00000000")
    ap.add_argument("--until", default="99999999")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--angles", type=int, default=8)
    ap.add_argument("--techniques", action="store_true")
    ap.add_argument("--strength", choices=["calibrated", "raw"], default="calibrated")
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.angles < SCOUT:
        ap.error(f"--angles must be at least SCOUT={SCOUT} (the attacker scouts that many sides)")
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    periods = None if args.base else json.loads(HISTORY.read_text(encoding="utf-8"))["periods"]
    layouts: dict = {}

    def layout_json(path):
        if path not in layouts:
            lay = Layout.load(Path(path) if Path(path).is_absolute() else ROOT / path)
            lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
            layouts[path] = lay.to_json()
        return layouts[path]

    skipped = []
    text = Path(args.log).read_text(encoding="utf-8")
    # a battle log file from the API, or the growing archive (snapshot_log.py)
    items = [json.loads(x) for x in text.splitlines() if x.strip()] if args.log.endswith(".jsonl") else json.loads(text)["items"]
    rows = []
    for n, b in enumerate(items):
        if b.get("battleType") != "ranked" or b["attack"]:
            continue
        day = b["battleTimestamp"][:8]
        if not args.since <= day <= args.until:
            continue
        base = args.base or base_for_day(periods, day)
        if base is None:
            skipped.append(day)
            continue
        lj = layout_json(base)
        build, unknown = to_build(decode(b.get("armyShareCode", "")), b["opponentTownHallLevel"], n)
        st = family_strength(build) if args.strength == "calibrated" else 1.0
        techs = techniques(build) if args.techniques else [None]
        jobs, keys = [], []
        for k in range(args.angles):
            for s in range(args.seeds):
                for tech in techs:
                    jobs.append((lj, build, 2 * math.pi * k / args.angles + 0.21, 1000 + n * 31 + s * 7 + k, st, tech))
                    keys.append((s, k))
        res = list(pool().map(_run, jobs, chunksize=2))
        sides: dict = {}
        for key, r in zip(keys, res):
            sides.setdefault(key, []).append(r)
        per_seed: dict = {}
        for (s, k), rs in sides.items():
            per_seed.setdefault(s, []).append(max(rs, key=lambda r: (attacker_trophies(r[0], r[1]), r[1])))
        picked = []
        for rs in per_seed.values():
            for combo in itertools.combinations(rs, SCOUT):
                picked.append(max(combo, key=lambda r: (attacker_trophies(r[0], r[1]), r[1])))
        p3 = float(np.mean([r[0] >= 3 for r in picked]))
        es = float(np.mean([r[0] for r in picked]))
        ep = float(np.mean([r[1] for r in picked]))
        t3 = [r[2] for r in picked if r[0] >= 3]
        sim_t3 = float(np.mean(t3)) if t3 else None
        main_troop = max(build["troops"].items(), key=lambda kv: kv[1])[0] if build["troops"] else "?"
        row = dict(n=n, day=day, th=b["opponentTownHallLevel"], army=main_troop, real_stars=b["stars"], real_pct=b["destructionPercentage"],
                   p3=p3, stars=es, pct=ep, strength=round(st, 2), unknown=unknown, base=base,
                   real_time=b.get("battleTime"), sim_time_3star=sim_t3)
        rows.append(row)
        print(f"{day} TH{row['th']} {main_troop:16s} real {b['stars']}* {b['destructionPercentage']:3d}% | sim P(3*) {p3:4.0%} "
              f"E[stars] {es:.2f} E[%] {ep:5.1f}  time real {b.get('battleTime')}s sim-3* {sim_t3 or 0:.0f}s  str {st:.2f} {'unknown: ' + ','.join(unknown) if unknown else ''}", flush=True)
    if skipped:
        print(f"== skipped {len(skipped)} defenses with no known layout in {HISTORY.name}: {', '.join(skipped)}", flush=True)
    if rows:
        brier = np.mean([(r["p3"] - (r["real_stars"] >= 3)) ** 2 for r in rows])
        mae = np.mean([abs(r["pct"] - r["real_pct"]) for r in rows])
        star_err = np.mean([r["stars"] - r["real_stars"] for r in rows])
        base_rate = np.mean([r["real_stars"] >= 3 for r in rows])
        brier_base = np.mean([(base_rate - (r["real_stars"] >= 3)) ** 2 for r in rows])
        print(f"== {len(rows)} defenses: real 3* {base_rate:.0%}, sim mean P(3*) {np.mean([r['p3'] for r in rows]):.0%}; "
              f"Brier {brier:.3f} (always-guess-the-average {brier_base:.3f}); destruction MAE {mae:.1f} pts; "
              f"star bias {star_err:+.2f} (sim minus real)", flush=True)
        tt = [(r["sim_time_3star"], r["real_time"]) for r in rows if r["real_stars"] >= 3 and r["sim_time_3star"] and r["real_time"]]
        if tt:
            ratio = np.mean([a / b for a, b in tt])
            print(f"== time to 3-star on {len(tt)} real 3-star defenses: sim/real {ratio:.2f} (1.00 = same speed; check 6 target 0.85-1.15)", flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
