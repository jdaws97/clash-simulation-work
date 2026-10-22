"""Inputs and checks for the Rust engine port (rust/).

The Python engine stays the reference. Python builds each battle (layout,
levels, weapons, traps, Clan Castle, defending heroes, attack plan) and
exports its starting state; the Rust engine runs it. Static data the engine
reads mid-battle comes from a catalog regenerated after every game patch.

  catalog --out rust/data/catalog.json
      the processed registry (stats.registry(), what stats.get reads), every
      unit spec and summon spec, unit_numbers for every unit at every level,
      and the building/trap tables from mechanics.py
  battle  --stage S --k K --out output/parity/battle-S-K.json
      starting state of parity scenario K of stage S (see SCENARIOS)
  trace   --stage S --k K --out output/parity/trace-py-S-K.txt
      the Python engine's per-tick trace of that battle, compared with the
      Rust trace by tools/baselab/trace_diff.py

Trace format, one record per line: `T <t>` before each step, then after it
`U <team> <id> <name> <x> <y> <hp>` for every living unit (attackers then
defenders, list order), `B <id> <hp>` for each building whose hp changed,
`W <tx> <ty> <hp>` for walls, `E <log entry>` for new log events. Floats
are written as the 16 hex digits of their IEEE-754 bits (exact; the diff
tool decodes them).

Usage: python tools/baselab/rust_export.py catalog|battle|trace ...
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("BASELAB_PLAYBOOKS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))


def fbits(x) -> str:
    return "%016x" % struct.unpack("<Q", struct.pack("<d", float(x)))[0]


# ------------------------------------------------------------------ generic dump
def dump(obj, depth=0):
    """JSON-able copy of engine state. Engine objects inside other objects
    become references ({"$building": id}, {"$wall": [tx, ty]}, {"$unit": id},
    {"$trap": index}) so the Rust side can rebuild the links."""
    from baselab.engine.entities import Building, Pending, Trap, Unit, Wall
    from baselab.engine.entities import Field as EField

    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        return obj  # json.dumps writes Infinity/NaN, which rust/src/json.rs reads
    if depth > 0:
        if isinstance(obj, Building):
            return {"$building": obj.id}
        if isinstance(obj, Wall):
            return {"$wall": [obj.tx, obj.ty]}
        if isinstance(obj, Unit):
            return {"$unit": obj.id, "team": obj.team}
    if isinstance(obj, dict):
        return {(k if isinstance(k, str) else json.dumps(dump(k, 1))): dump(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [dump(v, depth + 1) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted((dump(v, depth + 1) for v in obj), key=repr)
    if dataclasses.is_dataclass(obj):
        out = {"$type": type(obj).__name__}
        out.update({f.name: dump(getattr(obj, f.name), depth + 1) for f in dataclasses.fields(obj)})
        return out
    slots = getattr(type(obj), "__slots__", None)
    if slots is not None or hasattr(obj, "__dict__"):
        names = list(slots or []) + list(getattr(obj, "__dict__", {}))
        out = {"$type": type(obj).__name__}
        for name in names:
            if hasattr(obj, name):
                v = getattr(obj, name)
                if callable(v) and not isinstance(v, type):
                    raise TypeError(f"cannot export callable {type(obj).__name__}.{name}")
                out[name] = dump(v, depth + 1)
        return out
    raise TypeError(f"cannot export {type(obj).__name__}")


# ------------------------------------------------------------------ catalog
def catalog():
    from baselab import mechanics
    from baselab.engine import heroes, specs, stats
    from baselab.engine import units as engine_units

    reg = stats.registry()
    units, numbers = {}, {}
    for name, rec in reg.items():
        if rec.get("kind") in ("troop", "super_troop", "siege", "hero", "pet", "summon", "spell") or name in specs.SPECS:
            try:
                sp = specs.spec(name)
            except Exception:  # noqa: BLE001 - names without a spec are not units
                continue
            units[name] = {"spec": dump(sp), "summon_spec": dump(heroes.summon_spec(name, sp))}
            for entry in rec.get("levels", []):
                level = entry.get("level")
                if isinstance(level, int):
                    try:
                        numbers[f"{name}|{level}"] = dump(specs.unit_numbers(name, level))
                    except Exception:  # noqa: BLE001 - incomplete rows stay absent
                        pass
    return {
        "note": "Rust engine catalog, exported by tools/baselab/rust_export.py catalog",
        "registry": reg,
        "units": units,
        "unit_numbers": numbers,
        "building_types": {k: dump(v) for k, v in mechanics.BUILDING_TYPES.items()},
        # tables the engine reads from data files mid-battle
        "new_target_delays": engine_units._new_target_delays(),
        "warden_weights": engine_units.warden_weights(),
        "game_ranges": specs._game_ranges(),
        "trap_names": dump(mechanics.TRAP_NAMES),
        "trap_sizes": dump(mechanics.TRAP_SIZES),
        "world": mechanics.WORLD,
        "margin": mechanics.MARGIN,
    }


# ------------------------------------------------------------------ battles
def own_layout(path):
    from baselab.layout import Layout

    lv = json.loads((ROOT / "data" / "your-levels.json").read_text())
    lay = Layout.load(ROOT / path)
    lay.levels, lay.wall_level, lay.hero_levels = dict(lv["levels"]), lv["wall_level"], dict(lv["hero_levels"])
    return lay


def edge_drops(army, angle, seed, gap=0.2):
    """Fixed drops along the edge facing `angle` (layout coords), like the
    Rust spike: [(time, name, x, y, level)]."""
    import random

    rng = random.Random(seed)
    out, k = [], 0
    for name, n in army:
        for i in range(n):
            lat = (i - (n - 1) / 2) * 1.2 + rng.uniform(-0.4, 0.4)
            x = 22.0 + math.cos(angle) * 23.5 - math.sin(angle) * lat
            y = 22.0 + math.sin(angle) * 23.5 + math.cos(angle) * lat
            out.append((gap * k, name, min(43.5, max(0.5, x)), min(43.5, max(0.5, y)), None))
            k += 1
    return out


# Stage 1: battle core, every defense and trap, Clan Castle defenders; plain
# troops dropped at fixed times; no heroes on either side, no spells.
STAGE1_ARMIES = [
    [("P.E.K.K.A", 4), ("Valkyrie", 16), ("Wizard", 12), ("Archer", 12)],
    [("Dragon", 10), ("Balloon", 10), ("Minion", 12)],
    [("Giant", 10), ("Valkyrie", 12), ("Dragon", 6), ("Wizard", 10), ("Barbarian", 12)],
]
STAGE1_BASES = ["data/reference-bases/your-base.json", "data/reference-bases/real-l6x.json"]


# Stage 2: the rest of the user's armies' troops, their summons, and siege
# machines releasing attacker Clan Castle cargo (fixed drops, no heroes or
# spells): (army drops, siege, cargo).
STAGE2_ARMIES = [
    ([("Ice Golem", 2), ("Root Rider", 4), ("Valkyrie", 8), ("Healer", 5), ("Apprentice Warden", 1)],
     "Siege Barracks", ["Super Hog Rider"] * 4 + ["Minion"]),
    ([("Ice Golem", 1), ("Druid", 2), ("Ruin Witch", 2), ("Root Rider", 2), ("Valkyrie", 3), ("Healer", 5), ("Archer", 3)],
     "Log Launcher", ["Ice Golem", "Ice Golem", "Root Rider"]),
    ([("Rocket Balloon", 6), ("Super Minion", 3), ("Balloon", 4), ("Minion", 6), ("Super Hog Rider", 4)], None, []),
]


def scenario(stage, k):
    """Python Battle for parity scenario k of a stage (not yet run)."""
    from baselab.engine.battle import Battle
    from mechanic_tests import Stage

    if stage == 1:
        n_sides = 4
        army = STAGE1_ARMIES[k % len(STAGE1_ARMIES)]
        base = STAGE1_BASES[(k // len(STAGE1_ARMIES)) % len(STAGE1_BASES)]
        side = k // (len(STAGE1_ARMIES) * len(STAGE1_BASES)) % n_sides
        angle, seed = 2 * math.pi * side / n_sides + 0.1 + 0.37 * k, 200 + k
        lay = own_layout(base)
        lay.heroes = []
        return Battle(lay, Stage(edge_drops(army, angle, seed)), seed=seed, town_hall=16)
    if stage == 2:
        n_sides = 4
        army, siege, cargo = STAGE2_ARMIES[k % len(STAGE2_ARMIES)]
        base = STAGE1_BASES[(k // len(STAGE2_ARMIES)) % len(STAGE1_BASES)]
        side = k // (len(STAGE2_ARMIES) * len(STAGE1_BASES)) % n_sides
        angle, seed = 2 * math.pi * side / n_sides + 0.1 + 0.37 * k, 300 + k
        lay = own_layout(base)
        lay.heroes = []
        drops = edge_drops(army + ([(siege, 1)] if siege else []), angle, seed)
        plan = Stage(drops)
        plan.cc_troops = list(cargo)  # read by Battle._attack_cargo
        return Battle(lay, plan, seed=seed, town_hall=16)
    raise ValueError(f"no stage {stage}")


def battle_state(b):
    """Starting state of a constructed, not yet stepped Battle."""
    skip = {"plan", "log", "frames", "grid", "rng", "_bucket_grid", "deployments", "_dt_cache", "_nd_cache"}
    scalars = {}
    for k, v in vars(b).items():
        if k in skip or k in ("buildings", "walls", "traps", "attackers", "defenders", "fields", "pending"):
            continue
        scalars[k] = dump(v, 1)
    from baselab.engine import battle as B
    from baselab.engine import playbook, units

    version, state, gauss = b.rng.getstate()
    return {
        # random.Random internal state: 624 words and the index (getstate()[1])
        "rng_state": list(state),
        "env": {"dt": B.DT, "fast_end": B.FAST_END, "windup": units.WINDUP,
                "pace": float(os.environ.get("BASELAB_PACE", "1.0")),
                "pace_tap": playbook.PACE_TAP, "pace_switch": playbook.PACE_SWITCH, "pace_ability": playbook.PACE_ABILITY},
        "scalars": scalars,
        "buildings": [dump(x) for x in b.buildings],
        "walls": [dump(w) for w in b.walls.values()],
        "traps": [dump(t) for t in b.traps],
        "attackers": [dump(u) for u in b.attackers],
        "defenders": [dump(u) for u in b.defenders],
        "fields": [dump(f) for f in b.fields],
        "pending": [dump(p) for p in b.pending],
        "deployments": [dump(d) for d in b.deployments],
        "plan": dump(b.plan),
        "plan_type": type(b.plan).__name__,
    }


def trace(b, max_ticks=10**9):
    lines, last_b, last_w, nlog = [], {}, {}, 0
    b.record = True
    ticks = 0
    while not b.ended and b.t < b.max_time and ticks < max_ticks:
        lines.append(f"T {fbits(b.t)}")
        b.step()
        ticks += 1
        for team, pool in (("atk", b.attackers), ("def", b.defenders)):
            for u in pool:
                if u.alive:
                    lines.append(f"U {team} {u.id} {u.name.replace(' ', '_')} {fbits(u.x)} {fbits(u.y)} {fbits(u.hp)}")
        for x in b.buildings:
            if last_b.get(x.id, x.max_hp) != x.hp:
                last_b[x.id] = x.hp
                lines.append(f"B {x.id} {fbits(x.hp)}")
        for w in b.walls.values():
            if last_w.get((w.tx, w.ty), w.max_hp) != w.hp:
                last_w[(w.tx, w.ty)] = w.hp
                lines.append(f"W {w.tx} {w.ty} {fbits(w.hp)}")
        for entry in b.log[nlog:]:
            lines.append("E " + json.dumps(dump(list(entry), 1)))
        nlog = len(b.log)
        if b.destroyed_counted >= b.total_counted or b.offense_finished():
            break
    r = b.result()
    lines.append(f"R {r.stars} {r.destruction} {fbits(r.time)} {r.units_left}")
    return lines


def parity(stage, n, start=0):
    """Export scenarios start..start+n-1 of a stage, trace them in both
    engines, and report the first difference of each (rust/ must be built)."""
    import subprocess

    from trace_diff import first_difference

    exe = ROOT / "rust" / "target" / "release" / "baselab-engine.exe"
    d = ROOT / "output" / "parity"
    d.mkdir(parents=True, exist_ok=True)
    same = 0
    for k in range(start, start + n):
        bj, py, rs = d / f"battle-{stage}-{k}.json", d / f"trace-py-{stage}-{k}.txt", d / f"trace-rs-{stage}-{k}.txt"
        b = scenario(stage, k)
        bj.write_text(json.dumps(battle_state(b)))
        py.write_text("\n".join(trace(scenario(stage, k))) + "\n")
        run = subprocess.run([str(exe), "trace", str(bj), str(rs)], capture_output=True, text=True)
        if run.returncode != 0:
            msg = (run.stderr.strip().splitlines() or ["?"])[-1]
            print(f"  {k:3d}  RUST FAILED: {msg[:200]}")
            continue
        diff = first_difference(py.read_text().split("\n"), rs.read_text().split("\n"))
        if diff is None:
            same += 1
            print(f"  {k:3d}  identical   {py.read_text().splitlines()[-1]}")
        else:
            print(f"  {k:3d}  DIFFERS {diff}")
    print(f"stage {stage}: {same}/{n} identical")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("catalog"); c.add_argument("--out", required=True)
    pa = sub.add_parser("parity"); pa.add_argument("--stage", type=int, required=True)
    pa.add_argument("--n", type=int, default=24); pa.add_argument("--start", type=int, default=0)
    for name in ("battle", "trace"):
        p = sub.add_parser(name); p.add_argument("--stage", type=int, required=True); p.add_argument("--k", type=int, default=0)
        p.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cmd == "parity":
        parity(args.stage, args.n, args.start)
        return
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.cmd == "catalog":
        data = catalog()
        out.write_text(json.dumps(data))
        print(f"catalog: {len(data['registry'])} registry entries, {len(data['units'])} units, "
              f"{len(data['unit_numbers'])} unit levels -> {out} ({out.stat().st_size // 1024} KB)")
    elif args.cmd == "battle":
        b = scenario(args.stage, args.k)
        out.write_text(json.dumps(battle_state(b), indent=1))
        print(f"stage {args.stage} scenario {args.k}: {len(b.buildings)} buildings, {len(b.walls)} walls, "
              f"{len(b.traps)} traps, {len(b.deployments)} deployments -> {out}")
    else:
        b = scenario(args.stage, args.k)
        lines = trace(b)
        out.write_text("\n".join(lines) + "\n")
        print(f"stage {args.stage} scenario {args.k}: {len(lines)} trace lines; {lines[-1]} -> {out}")


if __name__ == "__main__":
    main()
