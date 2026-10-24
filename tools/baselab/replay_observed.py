"""Replay a real defense in the sim with the attacker's OBSERVED plays.

The replay file (data/replays/*.json, read off a defense video) gives every
troop drop, spell and hero ability with its battle time and village tile.
The army comes from the battle-log share code (same build as
replay_log.py `to_build`), the base from the replay's layout with the
user's levels (data/your-levels.json). Nothing is decided by the sim's
attack brain: units drop, spells land and abilities fire exactly when the
video shows them; after that the engine plays the battle.

The sim is then compared with the video second by second: destruction
every 2 s, when the key defenses fell, and when each star came.

Usage: python tools/baselab/replay_observed.py data/replays/2026-10-21-maroon-machine.json
       [--seeds 6] [--strength calibrated|raw|both] [--trace SEED] [--out FILE]
Set BASELAB_CALIBRATION (e.g. data/meta-calibration-r8.json) for the
calibrated strength. Run as a script (multiprocessing on Windows).
"""

from __future__ import annotations

import argparse
import random
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.engine import heroes  # noqa: E402
from baselab.engine.plans import SPELL_NAMES, AttackPlan, Deployment  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.mechanics import MARGIN  # noqa: E402
from baselab.meta_armies import SIEGES, SPELL_KEYS, _loadouts  # noqa: E402
from decode_battlelog import decode  # noqa: E402
from replay_log import family_strength, to_build  # noqa: E402

KEY_KINDS = ("ad", "inferno", "eagle", "scatter", "th", "mono", "xbow")


class ObservedPlan(AttackPlan):
    """Drops, spells and hero abilities at observed times and tiles (layout
    coordinates; MARGIN is added here). Also records the destruction curve,
    key-defense deaths and star times while the battle runs."""

    def setup(self, replay: dict, key_index: dict):
        self.drops = replay["deployments"]
        self.casts = sorted(replay["spells"], key=lambda s: s["t"])
        self.abilities = sorted(replay["hero_abilities"], key=lambda a: a["t"])
        self.key_index = key_index  # battle building id -> label
        self.curve, self.falls, self.star_t = [], {}, {}
        self.missed = []
        self._next_sample = 0.0

    def deployments(self, battle):
        out = []
        for d in self.drops:
            for _ in range(d.get("count", 1)):
                cc = d["unit"] in SIEGES or "clan castle" in d.get("source", "")
                out.append(Deployment(d["t"], d["unit"], d["x"] + MARGIN, d["y"] + MARGIN, group="main",
                                      level=self.unit_levels.get(d["unit"]), town_hall=self.town_hall,
                                      source="cc" if cc else "army"))
        return out

    def has_pending(self):
        return False

    def has_offensive_pending(self, battle):
        return False

    def on_tick(self, battle):
        t = battle.t
        while self.casts and self.casts[0]["t"] <= t + 1e-9:
            s = self.casts.pop(0)
            origin = "donated" if "clan" in s["origin"] else "brewed"
            try:
                self.cast_spell(battle, s["spell"], s["x"] + MARGIN, s["y"] + MARGIN, origin=origin)
            except ValueError as e:
                self.missed.append(f"{s['spell']} at {s['t']}: {e}")
        while self.abilities and self.abilities[0]["t"] <= t + 1e-9:
            a = self.abilities.pop(0)
            u = next((h for h in battle.attackers if h.name == a["hero"] and h.is_hero), None)
            if u is None or not u.alive or u.ability_used:
                self.missed.append(f"{a['hero']} ability at {a['t']}: hero {'dead' if u is not None and not u.alive else 'used/absent'}")
            else:
                heroes.activate(battle, u)
        self._track(battle)

    def _track(self, battle):
        t = battle.t
        if t >= self._next_sample - 1e-9:
            self.curve.append((round(t, 1), battle.destruction()))
            self._next_sample += 0.5
        for b in battle.buildings:
            if b.id in self.key_index and not b.alive and b.id not in self.falls:
                self.falls[b.id] = round(t, 1)
        s = battle.stars()
        for k in range(1, s + 1):
            self.star_t.setdefault(k, round(t, 1))


def make_plan(replay: dict, key_index: dict, *, levels: str = "engine", jitter: float = 0.0, seed: int = 0) -> ObservedPlan:
    """levels "engine": the attacker Town Hall's maximum levels (as in
    replay_log.py); "observed": the level badges read off the video
    (replay["observed_levels"]). jitter > 0 moves every drop and spell by up
    to that many tiles (seeded): the observed positions are approximate."""
    b = replay["battle"]
    th = b["attacker_th"]
    build, unknown = to_build(decode(b["armyShareCode"]), th, 0)
    spells = {SPELL_KEYS[n]: c for n, c in build["spells"].items()}
    cc_spells, cc_troops, siege = {}, [], None
    for n, c in build["cc"].items():
        if n in SIEGES:
            siege = n
        elif n in SPELL_KEYS:
            cc_spells[SPELL_KEYS[n]] = cc_spells.get(SPELL_KEYS[n], 0) + c
        else:
            cc_troops += [n] * c
    plan = ObservedPlan(town_hall=th, label="observed replay", spells=spells, cc_spells=cc_spells, cc_troops=cc_troops,
                        siege=siege, siege_donated=siege is not None, ground=False,
                        loadouts=_loadouts(build, build["heroes"]))
    plan.observed = True  # a real army from the battle log: legal by definition
    plan.real_battle = True  # plans.py require_legal: warn, do not fail
    if jitter > 0:
        rng = random.Random(seed)
        replay = dict(replay)
        for k in ("deployments", "spells"):
            replay[k] = [dict(e, x=e["x"] + rng.uniform(-jitter, jitter), y=e["y"] + rng.uniform(-jitter, jitter)) for e in replay[k]]
    plan.unit_levels = {}
    if levels == "observed":
        obs = {k: v for k, v in replay.get("observed_levels", {}).items() if isinstance(v, int)}
        plan.unit_levels = obs
        plan.spell_levels = {n: v for n, v in obs.items() if n.endswith("Spell")}
        plan.cc_spell_levels = dict(plan.spell_levels)
        plan.pet_levels = {n: v for n, v in obs.items() if n in ("Phoenix", "Unicorn", "L.A.S.S.I", "Poison Lizard")}
    plan.setup(replay, key_index)
    plan.build = build
    plan.unknown = unknown
    return plan


def layout_json(path: str) -> dict:
    own = json.loads((ROOT / "data" / "your-levels.json").read_text())
    lay = Layout.load(ROOT / path)
    lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
    return lay.to_json()


def key_labels(lj: dict) -> dict:
    return {i: f"{b['key']}({b['x']},{b['y']})" for i, b in enumerate(lj["buildings"]) if b["key"] in KEY_KINDS}


def run_one(args):
    from baselab.engine.battle import Battle

    replay, lj, seed, strength, record, levels, jitter = args
    keys = key_labels(lj)
    plan = make_plan(replay, keys, levels=levels, jitter=jitter, seed=seed)
    plan.strength = strength
    battle = Battle(Layout.from_json(lj), plan, seed=seed, town_hall=16, record=record)
    r = battle.run()
    plan._track(battle)
    plan.curve.append((round(battle.t, 1), battle.destruction()))
    out = dict(seed=seed, strength=strength, levels=levels, cfg=f"{levels} lv, str {strength:.2f}", stars=r.stars, pct=r.destruction, time=r.time, curve=plan.curve,
               falls={keys[i]: t for i, t in plan.falls.items()}, stars_t=plan.star_t, missed=plan.missed,
               units_left=r.units_left, damage_by_source={k: round(v) for k, v in battle.damage_by_source.items()},
               kills_by_source=dict(battle.kills_by_source))
    if record:
        out["log"] = [list(x) if isinstance(x, tuple) else x for x in battle.log]
    return out


def at(curve, t):
    v = 0
    for tt, p in curve:
        if tt <= t + 1e-9:
            v = p
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replay")
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--strength", choices=["calibrated", "raw", "both"], default="both")
    ap.add_argument("--levels", choices=["engine", "observed", "both"], default="both")
    ap.add_argument("--jitter", type=float, default=1.5, help="tiles of random position error per seed (seed 0 offset: none)")
    ap.add_argument("--trace", type=int, help="also run this seed (observed levels, raw strength, no jitter) with record=True")
    ap.add_argument("--out")
    args = ap.parse_args()
    replay = json.loads(Path(args.replay).read_text(encoding="utf-8"))
    lj = layout_json(replay["source"]["layout"])
    probe = make_plan(replay, {})
    cal = family_strength(probe.build)
    strengths = {"calibrated": [cal], "raw": [1.0], "both": [cal, 1.0]}[args.strength]
    levels = {"engine": ["engine"], "observed": ["observed"], "both": ["engine", "observed"]}[args.levels]
    print(f"army: {probe.build['troops']} spells {probe.build['spells']} cc {probe.build['cc']} heroes {probe.build['heroes']}"
          f"{' unknown: ' + ','.join(probe.unknown) if probe.unknown else ''}; calibrated strength {cal:.2f}", flush=True)
    jobs = [(replay, lj, 1000 + s, st, False, lv, args.jitter if s else 0.0) for lv in levels for st in strengths for s in range(args.seeds)]
    from baselab.evaluate import pool

    res = list(pool().map(run_one, jobs))
    cfgs = list(dict.fromkeys(r["cfg"] for r in res))
    groups = {c: [r for r in res if r["cfg"] == c] for c in cfgs}
    if args.trace is not None:
        res.append(run_one((replay, lj, args.trace, 1.0, True, "observed", 0.0)))
    real = replay
    real_curve = [(c["t"], c["pct"]) for c in real["destruction_every_2s"]]
    print()
    print("== destruction % every 4 s: real vs sim, mean [min-max] over seeds")
    print("   t real | " + " | ".join(f"{c:24s}" for c in cfgs))
    for t in range(0, 88, 4):
        cells = []
        for c in cfgs:
            v = [at(r["curve"], t) for r in groups[c]]
            cells.append(f"{sum(v) / len(v):5.1f} [{min(v):3d}-{max(v):3d}]          ")
        print(f"{t:4d} {at(real_curve, t):4d} | " + " | ".join(cells))
    print()
    print("== key defenses: real fall time vs sim median (n fell / n)")
    print(f"  {'':16s} {'real':>12s} | " + " | ".join(f"{c:24s}" for c in cfgs))
    for f in real["key_defense_falls"]:
        lab = f"{f['key']}({f['x']},{f['y']})"
        cells = []
        for c in cfgs:
            ts = sorted(r["falls"].get(lab, 999) for r in groups[c])
            med = ts[len(ts) // 2]
            cells.append(f"{'-' if med == 999 else med:>6} ({sum(1 for x in ts if x < 999)}/{len(ts)})           ")
        print(f"  {lab:16s} {f['t']:6.1f} +-{f['plus_minus_s']:<3} | " + " | ".join(cells))
    print()
    print("== stars")
    for s in real["stars"]:
        cells = []
        for c in cfgs:
            ts = sorted(r["stars_t"].get(s["star"], r["stars_t"].get(str(s["star"]), 999)) for r in groups[c])
            cells.append(f"median {'-' if ts[len(ts) // 2] == 999 else ts[len(ts) // 2]} ({sum(1 for x in ts if x < 999)}/{len(ts)})")
        print(f"  star {s['star']}: real {s['t']:5.1f} | " + " | ".join(cells))
    for c in cfgs:
        print(f"  {c}: " + ", ".join(f"{r['stars']}* {r['pct']}% {r['time']}s" for r in groups[c]))
    missed = sorted({m for r in res for m in r["missed"]})
    if missed:
        print("  not executed:", "; ".join(missed))
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=0))


if __name__ == "__main__":
    main()
