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

Each defense uses the frozen snapshot covering its timestamp, from
data/live/base-history.json. When none is recorded, use today's levels with
a warning and the legacy layout for that day (or today's layout if unknown).
--base replays every defense on one layout with today's levels instead.

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

from baselab.evaluate import (
    SCOUT,
    STRENGTH,
    apply_charge,
    attacker_trophies,
    group_seed,
    pool,
    skill,
    techniques,
)  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.meta_armies import SPELL_KEYS  # noqa: E402
from decode_battlelog import decode  # noqa: E402
from snapshot import (
    load_snapshot,
    read_battles,
    snapshot_for_battle,
    timestamp,
)  # noqa: E402


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
    build = {
        "archetype": f"log-{n}",
        "build": 1,
        "th": th,
        "share": 1.0,
        "three_star": 0.0,
        "troops": {t: c for t, c in troops.items() if not t.startswith("troop#")},
        "spells": spells,
        "cc": cc,
        "heroes": heroes,
        "loadouts": loadouts,
    }
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
    layout = Layout.from_json(lj)
    r = Battle(layout, plan, seed=seed, town_hall=layout.town_hall).run()
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
    # The attacker's own Town Hall first (TH17 attackers were scored with TH16
    # strengths before 2026-10-24), then TH16 as before.
    for th in (build.get("th"), 16):
        vals = [v for k, v in STRENGTH.items() if k.startswith(f"meta:{key}-{th}-")]
        if vals:
            return sum(vals) / len(vals)
    return 1.0


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


def defensive_setup(
    history: dict,
    battle_time: str,
    own: dict | None = None,
    base_override: str | None = None,
) -> tuple[dict, str, dict | None]:
    """Load a frozen defense, or the explicitly identified current-level fallback."""
    if base_override is None:
        entry = snapshot_for_battle(history, battle_time)
        if entry is not None:
            # docs/GAP_ANALYSIS.md:45-47: today's upgrades are not historical defense.
            frozen = load_snapshot(entry)
            return Layout.from_json(frozen).to_json(), entry["layout"], entry
    if own is None:
        own = json.loads((ROOT / "data/your-levels.json").read_text(encoding="utf-8"))
    day = timestamp(battle_time).strftime("%Y%m%d")
    base = base_override or base_for_day(history.get("periods", []), day)
    base = base or "data/reference-bases/your-base.json"
    path = Path(base)
    layout = Layout.load(path if path.is_absolute() else ROOT / path)
    layout.levels = dict(own["levels"])
    for key, value in own.get("trap_levels", {}).items():
        layout.levels[f"trap:{key}"] = value
    layout.wall_level = own["wall_level"]
    layout.hero_levels = dict(own["hero_levels"])
    if "wall_levels" in own:
        layout.wall_levels = {
            (wall["x"], wall["y"]): wall["level"] for wall in own["wall_levels"]
        }
    if "cc_troops" in own:
        layout.cc_troops = own["cc_troops"]
    if "heroes" in own:
        layout.heroes = own["heroes"]
    return layout.to_json(), base, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument(
        "--base",
        help="replay every defense on this layout with today's levels (default: the live snapshot at battle time)",
    )
    ap.add_argument("--since", default="00000000")
    ap.add_argument("--until", default="99999999")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--angles", type=int, default=8)
    ap.add_argument("--techniques", action="store_true")
    ap.add_argument("--strength", choices=["calibrated", "raw"], default="calibrated")
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.angles < SCOUT:
        ap.error(
            f"--angles must be at least SCOUT={SCOUT} (the attacker scouts that many sides)"
        )
    history = {} if args.base else json.loads(HISTORY.read_text(encoding="utf-8"))
    own = None
    layouts: dict = {}
    # a battle log file from the API, or the growing archive (snapshot_log.py)
    items = read_battles(Path(args.log))
    rows = []
    for n, b in enumerate(items):
        if b.get("battleType") != "ranked" or b["attack"]:
            continue
        day = b["battleTimestamp"][:8]
        if not args.since <= day <= args.until:
            continue
        battle_time = b["battleTimestamp"]
        entry = None if args.base else snapshot_for_battle(history, battle_time)
        cache_key = ("snapshot", entry["id"]) if entry else ("fallback", args.base, day)
        if cache_key not in layouts:
            if entry is None and own is None:
                own = json.loads(
                    (ROOT / "data/your-levels.json").read_text(encoding="utf-8")
                )
            layouts[cache_key] = defensive_setup(
                history, battle_time, own=own, base_override=args.base
            )
        lj, base, entry = layouts[cache_key]
        if entry is None:
            reason = (
                "--base override"
                if args.base
                else "no frozen snapshot covers this battle"
            )
            print(
                f"WARNING: {battle_time}: {reason}; using today's account levels on {base}. "
                "Historical CC troops and hero assignments are unverified.",
                flush=True,
            )
        build, unknown = to_build(
            decode(b.get("armyShareCode", "")), b["opponentTownHallLevel"], n
        )
        st = family_strength(build) if args.strength == "calibrated" else 1.0
        techs = techniques(build) if args.techniques else [None]
        jobs, keys = [], []
        for k in range(args.angles):
            for s in range(args.seeds):
                for tech in techs:
                    jobs.append(
                        (
                            lj,
                            build,
                            2 * math.pi * k / args.angles + 0.21,
                            5000 * (n + 1) + group_seed(n + s, s, k, args.angles),
                            st,
                            tech,
                        )
                    )
                    keys.append((s, k))
        res = list(pool().map(_run, jobs, chunksize=2))
        sides: dict = {}
        for key, r in zip(keys, res):
            sides.setdefault(key, []).append(r)
        per_seed: dict = {}
        for (s, k), rs in sides.items():
            per_seed.setdefault(s, []).append(
                max(rs, key=lambda r: (attacker_trophies(r[0], r[1]), r[1]))
            )
        picked = []
        for rs in per_seed.values():
            for combo in itertools.combinations(rs, SCOUT):
                picked.append(
                    max(combo, key=lambda r: (attacker_trophies(r[0], r[1]), r[1]))
                )
        p3 = float(np.mean([r[0] >= 3 for r in picked]))
        es = float(np.mean([r[0] for r in picked]))
        ep = float(np.mean([r[1] for r in picked]))
        t3 = [r[2] for r in picked if r[0] >= 3]
        sim_t3 = float(np.mean(t3)) if t3 else None
        main_troop = (
            max(build["troops"].items(), key=lambda kv: kv[1])[0]
            if build["troops"]
            else "?"
        )
        row = dict(
            n=n,
            day=day,
            th=b["opponentTownHallLevel"],
            army=main_troop,
            real_stars=b["stars"],
            real_pct=b["destructionPercentage"],
            p3=p3,
            stars=es,
            pct=ep,
            strength=round(st, 2),
            unknown=unknown,
            base=base,
            real_time=b.get("battleTime"),
            sim_time_3star=sim_t3,
            # User (TH16 ranked, 2026-10-24): failed attacks should run as long
            # as real ones, often to the 180 s timer.
            sim_time_median=float(np.median([r[2] for r in picked])),
            sim_timeout=float(np.mean([r[2] >= 179.5 for r in picked])),
            sim_times=[round(r[2], 1) for r in picked],
            sim_stars=[r[0] for r in picked],
            battleTimestamp=battle_time,
            snapshot_id=entry["id"] if entry else None,
            current_levels_fallback=entry is None,
        )
        rows.append(row)
        print(
            f"{day} TH{row['th']} {main_troop:16s} real {b['stars']}* {b['destructionPercentage']:3d}% | sim P(3*) {p3:4.0%} "
            f"E[stars] {es:.2f} E[%] {ep:5.1f}  time real {b.get('battleTime')}s sim-3* {sim_t3 or 0:.0f}s  str {st:.2f} {'unknown: ' + ','.join(unknown) if unknown else ''}",
            flush=True,
        )
    if rows:
        brier = np.mean([(r["p3"] - (r["real_stars"] >= 3)) ** 2 for r in rows])
        mae = np.mean([abs(r["pct"] - r["real_pct"]) for r in rows])
        star_err = np.mean([r["stars"] - r["real_stars"] for r in rows])
        base_rate = np.mean([r["real_stars"] >= 3 for r in rows])
        brier_base = np.mean([(base_rate - (r["real_stars"] >= 3)) ** 2 for r in rows])
        print(
            f"== {len(rows)} defenses: real 3* {base_rate:.0%}, sim mean P(3*) {np.mean([r['p3'] for r in rows]):.0%}; "
            f"Brier {brier:.3f} (always-guess-the-average {brier_base:.3f}); destruction MAE {mae:.1f} pts; "
            f"star bias {star_err:+.2f} (sim minus real)",
            flush=True,
        )
        tt = [
            (r["sim_time_3star"], r["real_time"])
            for r in rows
            if r["real_stars"] >= 3 and r["sim_time_3star"] and r["real_time"]
        ]
        if tt:
            ratio = np.mean([a / b for a, b in tt])
            print(
                f"== time to 3-star on {len(tt)} real 3-star defenses: sim/real {ratio:.2f} (1.00 = same speed; check 6 target 0.85-1.15)",
                flush=True,
            )
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
