"""Engine v2 coverage matrix: every registry entity exercised in a battle.

For each troop, super troop, siege, summon, hero, spell, equipment and pet
the tool runs a short battle against a real reference base and records
whether the entity spawned/cast/activated without error and whether it did
anything measurable (damage dealt, buildings destroyed, effect applied).
Spells, equipment and pets are compared with the same battle without the
cast or item: "ok" means the end state differs from that baseline, "no
measurable effect" means it ran but changed nothing measured.

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


# What a spell, equipment or pet row measures at the end of its trial. The
# battle is deterministic (fixed seed), so the same trial without the cast
# (or without the item) is the baseline and the difference is the effect.
STATE = ("destruction", "building_hp", "defender_hp", "attackers", "attacker_dealt", "attacker_hp")
# spells that act on the attackers are cast on an attacking troop, those
# that disable defenses on the defense nearest it, the rest on the weakest
# defense
FRIENDLY = {"Healing Spell", "Rage Spell", "Jump Spell", "Haste Spell", "Clone Spell", "Invisibility Spell",
            "Recall Spell", "Ice Block Spell", "Angry Spell", "Totem Spell"}
DISABLE = {"Freeze Spell", "Overgrowth Spell", "Yellow Card"}


def _state(b):
    return (b.destruction(), sum(x.hp for x in b.buildings if x.alive), sum(u.hp for u in b.defenders if u.alive),
            len(b.attackers), sum(u.damage_dealt for u in b.attackers), sum(u.hp for u in b.attackers if u.alive))


def _effect(with_item, baseline):
    eff = {k: round(a - c, 1) for k, a, c in zip(STATE, with_item, baseline)}
    return eff, ("ok" if any(abs(v) >= 0.1 for v in eff.values()) else "no measurable effect")


def _spell_trial(name, th, cast=True):
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
    elif name in FRIENDLY or name in DISABLE:
        # on the most damaged troop (the group is spread out by now), or on
        # the defense nearest it (one that is likely firing)
        u = min((u for u in b.attackers if u.alive and not u.is_hero and u.kind != "pet"), key=lambda u: u.hp / u.max_hp)
        x, y = u.x, u.y
        if name in DISABLE:
            d = min((d for d in b.buildings if d.alive and d.is_defense), key=lambda d: (d.x - x) ** 2 + (d.y - y) ** 2)
            x, y = d.x, d.y
    else:
        x, y = tgt.x, tgt.y
    if cast:
        spells.cast_effect(b, name, x, y)  # unpaid: the probe has no spell inventory
    for _ in range(80):
        b.step()
    return _state(b)


def spell_rows(th):
    out = {}
    base: dict = {}  # no-spell baselines (Revive kills a hero first)
    for name, rec in stats.registry().items():
        if rec["kind"] != "spell":
            continue
        row = {"kind": "spell"}
        try:
            key = name == "Revive Spell"
            if key not in base:
                base[key] = _spell_trial(name, th, cast=False)
            row["effect"], row["status"] = _effect(_spell_trial(name, th), base[key])
        except Exception as e:  # noqa: BLE001
            row["status"] = "error"
            row["error"] = "".join(traceback.format_exception_only(type(e), e)).strip()[:200]
        out[name] = row
    return out


def _hero_trial(hero, th, loadout, item=None):
    """A lone hero with a loadout: 8 s in, its ability is activated, 10 s
    more. Returns (end state, hero unit, battle), or None for the state when
    `item` (equipment) is not in the kit."""
    b = _battle([hero], th, loadouts={hero: loadout}, max_time=40.0)
    for _ in range(80):
        b.step()
    u = next(x for x in b.attackers if x.is_hero)
    if item is not None and (u.kit is None or item not in u.kit.equip):
        return None, u, b
    if u.alive:
        heroes.activate(b, u)
    for _ in range(100):
        b.step()
    return _state(b), u, b


def equipment_rows(th):
    """Equipment: the hero with only that item vs the hero with none, both
    activated at the same moment. Pets: the Queen with Giant Arrow and the
    pet vs without a pet."""
    out = {}
    reg = stats.registry()
    base: dict = {}
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
                lo, lo0 = HeroLoadout(hero, (name,), None), HeroLoadout(hero, (), None)
            else:
                hero = "Archer Queen"
                lo, lo0 = HeroLoadout(hero, ("Giant Arrow",), name), HeroLoadout(hero, ("Giant Arrow",), None)
            st, u, b = _hero_trial(hero, th, lo, name if rec["kind"] == "equipment" else None)
            if st is None or u.kit is None:
                row["status"] = "not equipped"
            else:
                key = (rec["kind"], hero)
                if key not in base:
                    base[key] = _hero_trial(hero, th, lo0)[0]
                row["effect"], row["status"] = _effect(st, base[key])
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
    # the baselines are only meaningful if a repeated trial is identical
    if _spell_trial("Rage Spell", args.th, cast=False) != _spell_trial("Rage Spell", args.th, cast=False):
        print("WARNING: repeated no-spell trials differ; spell/equipment effects include noise")
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
