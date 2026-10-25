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
       [--attacker generic|playbook] (or BASELAB_REPLAY_PLAYBOOKS=1)
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.evaluate import (
    CHARGE_HEALERS,
    SCOUT,
    STRENGTH,
    apply_charge,
    attacker_trophies,
    group_seed,
    pool,
    skill,
)  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.meta_armies import SPELL_KEYS, _share_troops, data, family_of  # noqa: E402
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
        if "#" in t:
            unknown.append(t)
            continue
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


def default_attacker():
    return (
        "playbook" if os.environ.get("BASELAB_REPLAY_PLAYBOOKS") == "1" else "generic"
    )


def attacker_for_build(build, attacker):
    """Return the actual attacker, resolved family and any generic fallback note."""
    from baselab.meta_armies import _playbook

    family = family_of(build)
    if attacker == "playbook":
        if family is None:
            return "generic", family, "unclassified army family"
        if _playbook(family) is None:
            return "generic", family, f"no cited playbook for {family}"
    return attacker, family, None


def replay_plan(build, angle, seed, attacker="generic"):
    from baselab.meta_armies import _playbook, compose

    kind, family, _note = attacker_for_build(build, attacker)
    if kind == "playbook":
        from baselab.engine.playbook import from_playbook

        # output/research/usage/dragon.md: cited family openings depend on the army.
        # https://www.youtube.com/watch?v=55I-qks9qdI
        # Match meta_armies.plan_for_build: fit the real build, never the example.
        plan = from_playbook(
            _playbook(family),
            angle=angle,
            seed=seed,
            th=build["th"],
            build=build,
            charge_side="left" if seed % 2 == 0 else "right",
        )
    else:
        plan = compose(build, angle=angle, seed=seed)
    plan.observed = True  # a real army from the battle log
    return plan


def replay_techniques(build, attacker):
    """Use evaluate.techniques' generic charges without inheriting its env switch."""
    out = [None]
    if attacker == "generic":
        for hero, healers in CHARGE_HEALERS.items():
            if hero in build.get("heroes", []):
                out.append(
                    (hero, min(healers, int(build.get("troops", {}).get("Healer", 0))))
                )
    return out


def battle_end_reason(battle):
    """Observe the finished battle; do not extend combat or spend inventory."""
    if battle.destroyed_counted >= battle.total_counted:
        return "all_buildings_destroyed"
    if battle.t >= battle.max_time:
        # output/fidelity/diag/d1.out: separate fighting from inventory-only waits.
        # output/research/usage/healer.md; https://clashofclans.fandom.com/wiki/Healer
        # Use Battle.offense_finished's live-unit exclusions, including idle siege.
        if any(
            unit.alive
            and unit.name not in ("Healer", "Unicorn", "Totem")
            and unit.kind != "siege_idle"
            for unit in battle.attackers
        ):
            return "timer_live_fighting_units"
        return "timer_inventory_only"
    return "exhausted_offense"


def _run(args):
    lj, build, angle, seed, strength, tech, attacker = args
    from baselab.engine.battle import Battle

    plan = replay_plan(build, angle, seed, attacker)
    if tech is not None:
        apply_charge(plan, tech)
    plan.strength = strength * skill(seed)
    layout = Layout.from_json(lj)
    battle = Battle(layout, plan, seed=seed, town_hall=layout.town_hall)
    r = battle.run()
    return r.stars, r.destruction, r.time, battle_end_reason(battle)


def current_strength(th, family):
    """Shared fitter/replay lookup: share-weighted geometric family strength."""
    for level in dict.fromkeys((th, 16)):
        values = [
            (
                STRENGTH[f"meta:{b['archetype']}-{b['th']}-{b['build']}"],
                b.get("share", 1.0),
            )
            for b in data()["builds"]
            if b["th"] == level
            and family_of(b) == family
            and f"meta:{b['archetype']}-{b['th']}-{b['build']}" in STRENGTH
        ]
        if values:
            total = sum(w for _, w in values)
            return math.exp(sum(w * math.log(v) for v, w in values) / total)
    fallback = {
        "dragon": "hydra",
        "thrower": "throwers",
        "electro-dragon": "edrag",
        "root-rider": "rootrider",
    }
    return STRENGTH.get(fallback.get(family), 1.0)


def family_strength(build) -> float:
    return current_strength(build.get("th"), family_of(build))


def battle_identity(battle):
    """Hash the fitter's deduplication identity, without exposing share codes."""
    identity = (
        battle["battleTimestamp"],
        battle["opponentTownHallLevel"],
        battle.get("armyShareCode") or "",
    )
    return hashlib.sha256(
        json.dumps(identity, separators=(",", ":")).encode()
    ).hexdigest()


def replay_seed(identity, seed_index, side, angles):
    """All sides share skill; five consecutive seeds cover all five quantiles."""
    offset = int(identity[:8], 16)
    return 5 * offset * angles + group_seed(
        offset + seed_index, seed_index, side, angles
    )


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
    *,
    historical_only: bool = False,
) -> tuple[dict, str, dict | None]:
    """Load a frozen defense, or a historical/current fallback as requested."""
    if base_override is None:
        entry = snapshot_for_battle(history, battle_time)
        if entry is not None:
            # docs/GAP_ANALYSIS.md:45-47: today's upgrades are not historical defense.
            frozen = load_snapshot(entry)
            return Layout.from_json(frozen).to_json(), entry["layout"], entry
    if historical_only:
        # docs/GAP_ANALYSIS.md:45-48: fitting must never borrow today's levels.
        day = timestamp(battle_time).date().isoformat()
        periods = [
            p
            for p in history.get("periods", [])
            if p["from"] <= day and (p.get("to") is None or day <= p["to"])
        ]
        if len(periods) != 1 or not periods[0].get("layout"):
            raise ValueError("missing_or_ambiguous_history")
        base = periods[0]["layout"]
        layout = Layout.load(ROOT / base)
        if not layout.levels or not layout.hero_levels or not layout.wall_level:
            raise ValueError("missing_historical_levels")
        return layout.to_json(), base, None
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
    ap.add_argument(
        "--attacker",
        choices=["playbook", "generic"],
        default=default_attacker(),
        help="attacker policy (default: generic; BASELAB_REPLAY_PLAYBOOKS=1 selects playbook)",
    )
    ap.add_argument("--strength", choices=["calibrated", "raw"], default="calibrated")
    ap.add_argument("--out")
    ap.add_argument("--exclude-unknown", action="store_true")
    ap.add_argument(
        "--report", action="store_true", help="include exclusion counts in JSON output"
    )
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
    excluded_unknown = 0
    for n, b in enumerate(items):
        if b.get("battleType") != "ranked" or b["attack"]:
            continue
        day = b["battleTimestamp"][:8]
        if not args.since <= day <= args.until:
            continue
        identity = battle_identity(b)
        try:
            code = b.get("armyShareCode") or ""
            _share_troops(code)  # Like the fitter, reject missing/undecodable camps.
            build, unknown = to_build(decode(code), b["opponentTownHallLevel"], n)
        except (KeyError, TypeError, ValueError):
            excluded_unknown += 1
            continue
        if args.exclude_unknown and unknown:
            excluded_unknown += 1
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
        st = family_strength(build) if args.strength == "calibrated" else 1.0
        attacker, family, fallback = attacker_for_build(build, args.attacker)
        techs = replay_techniques(build, attacker) if args.techniques else [None]
        jobs, keys = [], []
        for k in range(args.angles):
            for s in range(args.seeds):
                for tech in techs:
                    jobs.append(
                        (
                            lj,
                            build,
                            2 * math.pi * k / args.angles + 0.21,
                            replay_seed(identity, s, k, args.angles),
                            st,
                            tech,
                            attacker,
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
            battle_id=identity,
            day=day,
            th=b["opponentTownHallLevel"],
            army=main_troop,
            attacker=attacker,
            attacker_family=family,
            attacker_fallback=fallback,
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
            sim_end_reasons=[r[3] for r in picked],
            # Count actual runs before scouting repeats winners across side pairs.
            sim_end_reason_counts=dict(Counter(r[3] for r in res)),
            battleTimestamp=battle_time,
            snapshot_id=entry["id"] if entry else None,
            current_levels_fallback=entry is None,
        )
        rows.append(row)
        print(
            f"{day} TH{row['th']} {main_troop:16s} real {b['stars']}* {b['destructionPercentage']:3d}% | sim P(3*) {p3:4.0%} "
            f"E[stars] {es:.2f} E[%] {ep:5.1f}  time real {b.get('battleTime')}s sim-3* {sim_t3 or 0:.0f}s  str {st:.2f} "
            f"attacker {attacker}{' (fallback: ' + fallback + ')' if fallback else ''} "
            f"{'unknown: ' + ','.join(unknown) if unknown else ''}",
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
    attacker_counts = dict(Counter(row["attacker"] for row in rows))
    fallback_notes = dict(
        Counter(row["attacker_fallback"] for row in rows if row["attacker_fallback"])
    )
    print(
        f"== engine: python; attacker requested: {args.attacker}; "
        f"attacker counts (defenses): {attacker_counts}; fallback notes: {fallback_notes}; "
        f"excluded unknown/undecodable armies: {excluded_unknown}",
        flush=True,
    )
    if args.out:
        report = {
            "rows": rows,
            "excluded_unknown": excluded_unknown,
            "engine": "python",
            "attacker": args.attacker,
            "attacker_counts": attacker_counts,
            "attacker_fallback_counts": fallback_notes,
        }
        Path(args.out).write_text(json.dumps(report if args.report else rows, indent=1))


if __name__ == "__main__":
    main()
