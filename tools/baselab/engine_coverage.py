"""Engine v2 coverage matrix: every registry entity exercised in a battle.

For each troop, super troop, siege, summon, hero, spell, equipment and pet
the tool runs a short battle against a real reference base and records
whether the entity spawned/cast/activated without error and whether it did
anything measurable (damage dealt, buildings destroyed, effect applied).

Usage: python tools/baselab/engine_coverage.py [--th 18] [--out output/coverage.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.layout import Layout  # noqa: E402
from baselab.loadouts import HeroLoadout  # noqa: E402
from baselab.engine import heroes, spells, stats  # noqa: E402
from baselab.engine.battle import Battle  # noqa: E402
from baselab.engine.plans import Deployment, edge_point  # noqa: E402
from baselab.engine.specs import SPECS  # noqa: E402

BASE = ROOT / "data" / "reference-bases" / "real-l1x.json"


class Probe:
    """Minimal plan: deploys a list of units at one edge point."""

    def __init__(self, units, town_hall, loadouts=None, angle=0.8):
        self.units = units
        self.town_hall = town_hall
        self.loadouts = loadouts or {}
        self.angle = angle
        self.strength = 1.0
        self.cc_troops = ["Archer"] * 5
        self.revives_left = 0
        self.recalled = []

    def deployments(self, battle):
        x, y = edge_point(battle, self.angle, 0.0)
        return [Deployment(0.2 * i, n, x, y, group="main", town_hall=self.town_hall) for i, n in enumerate(self.units)]

    def has_pending(self):
        return False

    def on_tick(self, battle):
        pass


def _battle(units, th, loadouts=None, max_time=60.0):
    lay = Layout.load(BASE)
    return Battle(lay, Probe(units, th, loadouts), seed=1, town_hall=16, max_time=max_time)


def _measure(b):
    dealt = sum(u.damage_dealt for u in b.attackers)
    return {"destruction": round(b.destruction(), 1), "dealt": round(dealt), "spawned": len(b.attackers)}


def unit_rows(th):
    out = {}
    reg = stats.registry()
    for name, rec in reg.items():
        if rec["kind"] not in ("troop", "super_troop", "siege", "summon", "hero"):
            continue
        row = {"kind": rec["kind"], "spec": name in SPECS}
        try:
            if stats.max_level(name, th) is None:
                row["status"] = "no level at TH"
            else:
                n = 1 if rec["kind"] in ("hero", "siege") else 3
                b = _battle([name] * n, th, max_time=40.0)
                b.run()
                row.update(_measure(b))
                row["status"] = "ok" if row["dealt"] > 0 or row["destruction"] > 0 else "no effect"
        except Exception as e:  # noqa: BLE001
            row["status"] = "error"
            row["error"] = "".join(traceback.format_exception_only(type(e), e)).strip()[:200]
        out[name] = row
    return out


def spell_rows(th):
    out = {}
    for name, rec in stats.registry().items():
        if rec["kind"] != "spell":
            continue
        row = {"kind": "spell"}
        try:
            b = _battle(["Barbarian King", "Archer Queen"] + ["Valkyrie"] * 4 + ["Dragon"] * 2, th, max_time=30.0)
            for _ in range(60):
                b.step()
            tgt = min((x for x in b.buildings if x.alive and x.is_defense), key=lambda x: x.hp)
            if name == "Revive Spell":
                q = next(u for u in b.attackers if u.is_hero)
                b.kill(q)
                x, y = q.x, q.y
            elif name == "Poison Spell" and b.defenders:
                d = next((u for u in b.defenders if u.alive), None)
                x, y = (d.x, d.y) if d else (tgt.x, tgt.y)
            else:
                x, y = tgt.x, tgt.y
            before = (b.destruction(), sum(u.hp for u in b.defenders if u.alive), len(b.attackers))
            spells.cast_effect(b, name, x, y)  # unpaid: the probe has no spell inventory
            for _ in range(80):
                b.step()
            after = (b.destruction(), sum(u.hp for u in b.defenders if u.alive), len(b.attackers))
            row["status"] = "ok"
            row["delta"] = [round(a - c, 1) for a, c in zip(after, before)]
        except Exception as e:  # noqa: BLE001
            row["status"] = "error"
            row["error"] = "".join(traceback.format_exception_only(type(e), e)).strip()[:200]
        out[name] = row
    return out


def equipment_rows(th):
    out = {}
    reg = stats.registry()
    for name, rec in reg.items():
        if rec["kind"] not in ("equipment", "pet"):
            continue
        hero = rec["attrs"].get("hero") or rec["attrs"].get("raw", {}).get("User")
        row = {"kind": rec["kind"], "hero": hero}
        try:
            if rec["kind"] == "equipment":
                if hero not in heroes.HEROES:
                    row["status"] = "unknown hero"
                    out[name] = row
                    continue
                lo = {hero: HeroLoadout(hero, (name,), None)}
            else:
                hero = "Archer Queen"
                lo = {hero: HeroLoadout(hero, ("Giant Arrow",), name)}
            b = _battle([hero], th, loadouts=lo, max_time=40.0)
            for _ in range(80):
                b.step()
            u = next(x for x in b.attackers if x.is_hero)
            if u.kit is None or (rec["kind"] == "equipment" and name not in u.kit.equip):
                row["status"] = "not equipped"
            else:
                d0 = b.destruction()
                if u.alive:
                    heroes.activate(b, u)
                for _ in range(100):
                    b.step()
                row["status"] = "ok"
                row["destruction_gain"] = round(b.destruction() - d0, 1)
                if rec["kind"] == "pet":
                    # the pet stays in battle.attackers even after its hero is
                    # knocked out (which clears kit.pet_unit)
                    row["pet_spawned"] = any(x.kind == "pet" and x.name == name for x in b.attackers)
                    if not row["pet_spawned"]:
                        row["status"] = "pet not spawned"
        except Exception as e:  # noqa: BLE001
            row["status"] = "error"
            row["error"] = "".join(traceback.format_exception_only(type(e), e)).strip()[:200]
        out[name] = row
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--th", type=int, default=18)
    ap.add_argument("--out", default=str(ROOT / "output" / "coverage.json"))
    args = ap.parse_args()
    report = {"units": unit_rows(args.th), "spells": spell_rows(args.th), "equipment": equipment_rows(args.th)}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=1))
    for section, rows in report.items():
        counts: dict = {}
        for r in rows.values():
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        print(section, counts)
        for n, r in rows.items():
            if r["status"] != "ok":
                print("   ", n, r)


if __name__ == "__main__":
    main()
