"""Rust port spike: identical inputs for the Python and Rust engines.

Scenario: the user's base with only cannon / archer tower / mortar / wizard
tower / air defense / single Inferno / X-Bow as defenses (other defenses
removed), walls kept, Town Hall weapon off, no Clan Castle troops, defending
heroes or traps; attackers are Valkyries and Dragons dropped from one side.

  export  --n 32 --out rust/spike/scenarios.txt
      every number the Python engine resolved (buildings, weapons, walls,
      unit stats, drops) for N scenarios (8 sides x seeds)
  python  --n 32 --out output/spike-python.json
      runs the Python engine on the same scenarios: stars, destruction,
      time, when each building fell; single-process wall time per battle
  compare output/spike-python.json output/spike-rust.json
      agreement and speed

Usage: python tools/baselab/rust_spike.py export|python|compare ...
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

KEEP_DEF = {"cannon", "at", "mortar", "wt", "ad", "inferno", "xbow"}
DEFENSE_KEYS = {"inferno", "eagle", "scatter", "xbow", "mono", "ad", "mat", "ric", "wt", "bt", "mortar", "at", "cannon",
                "sweeper", "tesla", "st", "crafting", "guardian", "dsf", "sf"}
ARMY = [("Valkyrie", 8), ("Dragon", 8)]


def spike_layout():
    from baselab.layout import Layout
    from proof_scorer import own

    lay = own(Layout.load(ROOT / "data/reference-bases/your-base.json"))
    lay.buildings = [b for b in lay.buildings if b.key not in DEFENSE_KEYS or b.key in KEEP_DEF]
    for b in lay.buildings:
        if b.key == "inferno":
            b.mode = "single"
    lay.traps = []
    lay.cc_troops = []
    lay.heroes = []
    if hasattr(lay, "guardian"):
        lay.guardian = None
    return lay


def scenarios(n):
    """(angle, seed) pairs: 8 sides, n/8 seeds each."""
    return [(2 * math.pi * (i % 8) / 8 + 0.1, 100 + i // 8) for i in range(n)]


def drops(angle, seed):
    """Drop points along the edge facing `angle` (layout coords; the engine
    snaps them to the nearest legal tile)."""
    import random

    rng = random.Random(seed)
    out = []
    c = 22.0
    k = 0
    for name, n in ARMY:
        for i in range(n):
            lat = (i - (n - 1) / 2) * 1.2 + rng.uniform(-0.4, 0.4)
            x = c + math.cos(angle) * 23.5 - math.sin(angle) * lat
            y = c + math.sin(angle) * 23.5 + math.cos(angle) * lat
            out.append((0.2 * k, name, min(43.5, max(0.5, x)), min(43.5, max(0.5, y)), None))
            k += 1
    return out


def make_battle(lay, angle, seed, record=False):
    from baselab.engine.battle import Battle
    from mechanic_tests import Stage

    b = Battle(lay, Stage(drops(angle, seed)), seed=seed, town_hall=16, record=record)
    if b.th is not None:
        b.th.weapon = None  # Town Hall weapon off in the spike
    for bl in b.buildings:
        if bl.key not in KEEP_DEF:
            bl.weapon = None  # armed Builder's Huts etc. off: only the 7 spike defenses fire
            bl.is_defense = False
    b.builders = []  # no Builder's Hut repair either
    return b


def _jsonable(v):
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    return repr(v)


PROJ_SPEED = {"cannon": 12.0, "at": 18.0, "ad": 8.0}  # defense.py single-target projectiles


def export(n, out):
    """Plain-text inputs (one record per line, whitespace-separated) so the
    Rust side needs no JSON crate. Drops carry the raw drop point and the
    tick index at which the Python engine deploys them."""
    from baselab.engine import battle as B
    from baselab.engine import units as U

    lay = spike_layout()
    b0 = make_battle(lay, 0.1, 100)
    lines = [f"dt {B.DT!r}", f"max_time {b0.max_time!r}", f"world {B.WORLD}"]
    probe = make_battle(lay, 0.1, 100)
    while probe.t < 4.0:
        probe.step()
    delays = U._new_target_delays()
    for name, _ in ARMY:
        u = next(x for x in probe.attackers if x.name == name)
        lines.append(" ".join(map(str, ["unit", name, repr(u.max_hp), repr(u.dmg), repr(u.interval), repr(u.range), repr(u.speed),
                                        u.housing, int(u.flying), int(u.hits_air), int(u.hits_ground), repr(float(u.spec.splash)),
                                        repr(float(delays.get(name, u.interval)))])))
    for bl in b0.buildings:
        w = bl.weapon
        if w is None:
            kind, rest = "none", []
        else:
            kind = {"single": "single", "splash": "splash", "mortar": "mortar", "inferno_single": "inferno"}[w.kind]
            ramp = w.extra.get("ramp", [(0.0, 0.0)] * 3)
            proj = PROJ_SPEED.get(bl.key, 0.0)
            if bl.key == "wt" and bl.level <= 4:
                proj = 5.0
            rest = [w.targets, repr(w.range), repr(w.min_range or 0.0), repr(w.interval), repr(float(w.damage or 0.0)),
                    -1 if w.ammunition is None else w.ammunition, repr(proj), repr(float(w.extra.get("splash", 0.0))),
                    repr(float(w.extra.get("flight", 0.0))), int(w.kind == "mortar"), int(bool(w.extra.get("same_type")))]
            rest += [repr(float(v)) for pair in ramp for v in pair]
        lines.append(" ".join(map(str, ["building", bl.id, bl.key, repr(bl.x), repr(bl.y), repr(bl.half_hit), repr(bl.hp), bl.size,
                                        int(bl.counted), kind] + rest)))
    for w in b0.walls.values():  # wall-dictionary order matters for splash order
        lines.append(f"wall {w.tx} {w.ty} {w.hp!r}")
    nscen = 0
    for k, (a, s) in enumerate(scenarios(n)):
        b = make_battle(lay, a, s)
        deps = b.deployments
        ts, t, tick = [], 0.0, 0
        for d in deps:
            while not d.time <= t:  # the step() comparison, on the step() clock
                t = round(t + B.DT, 6); tick += 1
            # raw drop point: legality changes as buildings fall, so the engine snaps it
            ts.append(f"drop {tick} {d.name} {d.x!r} {d.y!r}")
        lines.append(f"scenario {k} {a!r} {s} {len(ts)}")
        lines += ts
        nscen += 1
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text("\n".join(lines) + "\n")
    print(f"exported {len(b0.buildings)} buildings, {len(b0.walls)} walls, {nscen} scenarios -> {out}")


def run_python(n, out):
    lay = spike_layout()
    rows, t0 = [], time.time()
    for a, s in scenarios(n):
        b = make_battle(lay, a, s)
        fell = {}
        orig = b.destroy

        def destroy(obj, b=b, fell=fell, orig=orig):
            if obj.alive and isinstance(getattr(obj, "id", None), int):
                fell[obj.id] = round(b.t, 2)
            return orig(obj)

        b.destroy = destroy
        r = b.run()
        rows.append({"angle": a, "seed": s, "stars": r.stars, "destruction": r.destruction, "time": round(r.time, 2),
                     "fell": fell, "units_left": r.units_left})
    dt = (time.time() - t0) / n
    Path(out).write_text(json.dumps({"engine": "python", "seconds_per_battle": dt, "rows": rows}, indent=1))
    print(f"python: {n} battles, {dt * 1000:.0f} ms per battle (single process) -> {out}")


def trace(k, out, ticks):
    """Per-tick state of scenario k (unit positions/hp, building and wall hp
    changes) to diff against the Rust engine's trace and find the first tick
    where the two engines part."""
    lay = spike_layout()
    a, s = scenarios(k + 1)[k]
    b = make_battle(lay, a, s)
    lines, last = [], {}
    for _ in range(ticks):
        if b.ended or b.t >= b.max_time:
            break
        t = b.t
        b.step()
        lines.append(f"T {t!r}")
        for u in b.attackers:
            if u.alive:
                lines.append(f"U {u.id} {float(u.x)!r} {float(u.y)!r} {float(u.hp)!r} {float(u.cooldown)!r}")
        for bl in list(b.buildings) + list(b.walls.values()):
            key = bl.id if isinstance(bl.id, int) else f"w{bl.tx},{bl.ty}"
            if last.get(key, bl.max_hp) != bl.hp:
                last[key] = bl.hp
                lines.append(f"B {key} {float(bl.hp)!r}")
        if b.destroyed_counted >= b.total_counted:
            break
    Path(out).write_text("\n".join(lines) + "\n")
    print(f"trace of scenario {k}: {len(lines)} lines -> {out}")


def compare(a, b):
    import numpy as np

    A, B = json.loads(Path(a).read_text()), json.loads(Path(b).read_text())
    ra, rb = A["rows"], B["rows"]
    print(f"speed: python {A['seconds_per_battle'] * 1000:.1f} ms, rust {B['seconds_per_battle'] * 1000:.2f} ms per battle "
          f"(single thread) -> {A['seconds_per_battle'] / B['seconds_per_battle']:.0f}x")
    da = np.array([r["destruction"] for r in ra]); db = np.array([r["destruction"] for r in rb])
    sa = np.array([r["stars"] for r in ra]); sb = np.array([r["stars"] for r in rb])
    ta = np.array([r["time"] for r in ra]); tb = np.array([r["time"] for r in rb])
    print(f"destruction mean {da.mean():.1f} vs {db.mean():.1f}; per-battle |diff| mean {np.abs(da - db).mean():.1f}, corr {np.corrcoef(da, db)[0, 1]:.2f}")
    print(f"stars mean {sa.mean():.2f} vs {sb.mean():.2f}; same stars in {(sa == sb).mean():.0%}")
    print(f"time mean {ta.mean():.1f} vs {tb.mean():.1f}")
    same = 0
    tot = 0
    for x, y in zip(ra, rb):
        for k, t in x["fell"].items():
            if k in y["fell"]:
                tot += 1
                same += abs(t - y["fell"][k]) <= 1.0
    print(f"building fall times within 1 s: {same}/{tot}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export"); e.add_argument("--n", type=int, default=32); e.add_argument("--out", required=True)
    p = sub.add_parser("python"); p.add_argument("--n", type=int, default=32); p.add_argument("--out", required=True)
    c = sub.add_parser("compare"); c.add_argument("a"); c.add_argument("b")
    tr = sub.add_parser("trace"); tr.add_argument("--k", type=int, default=0); tr.add_argument("--ticks", type=int, default=1800)
    tr.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cmd == "export":
        export(args.n, args.out)
    elif args.cmd == "python":
        run_python(args.n, args.out)
    elif args.cmd == "trace":
        trace(args.k, args.out, args.ticks)
    else:
        compare(args.a, args.b)


if __name__ == "__main__":
    main()
