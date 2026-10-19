"""Wiki-fact mechanic tests: tiny staged battles whose answer the wiki
states, run through the real engine. Each test reports measured vs expected
with its tolerance and wiki source. Check 2 in docs/SIM_ACCURACY.md.

Usage: python tools/baselab/mechanic_tests.py [-k name]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.engine import spells, stats  # noqa: E402
from baselab.engine.battle import Battle  # noqa: E402
from baselab.engine.plans import Deployment  # noqa: E402
from baselab.layout import Layout, Placement  # noqa: E402
from baselab.mechanics import MARGIN  # noqa: E402

OWN = json.loads((ROOT / "data" / "your-levels.json").read_text())
RESULTS = []


class Stage:
    """A plan that drops given units at given times and runs callbacks."""

    def __init__(self, drops, ticks=None, town_hall=16):
        self.drops = drops
        self.ticks = ticks or []
        self.town_hall = town_hall
        self.strength = 1.0
        self.loadouts = {}
        self.revives_left = 0

    def deployments(self, battle):
        return [Deployment(t, n, x + MARGIN, y + MARGIN, level=lv, town_hall=self.town_hall) for t, n, x, y, lv in self.drops]

    def has_pending(self):
        return False

    def on_tick(self, battle):
        for f in self.ticks:
            f(battle)


def layout(buildings, walls=()):
    lay = Layout("test", buildings=[Placement(k, x, y, m) for k, x, y, m in buildings], walls=set(walls), traps=[], cc_troops=[], heroes=[])
    lay.levels, lay.wall_level = dict(OWN["levels"]), OWN["wall_level"]
    return lay


def check(name, measured, expected, tol, source, unit=""):
    ok = abs(measured - expected) <= tol
    RESULTS.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name:42s} measured {measured:9.2f}{unit}  expected {expected:9.2f}{unit} +-{tol}{unit}  ({source})")


def unit_named(b, name):
    return next((u for u in b.attackers if u.name == name), None)


# ---------------------------------------------------------------- tests


def t_inferno_ramp():
    """Single-target Inferno: stage DPS at its level (wiki: Inferno Tower)."""
    lv = OWN["levels"].get("inferno") or stats.max_level("Inferno Tower", 16)
    row = stats.row("Inferno Tower", lv)
    s1, s2, s3 = (stats.num(row.get(k)) for k in ("Damage per Second / Initial", "Damage per Second / After 1.5s", "Damage per Second / After 5.25s"))
    lay = layout([("inferno", 20, 20, "single"), ("gs", 2, 40, None)])
    hp_log = []

    def tick(b):
        u = unit_named(b, "Golem")
        if u is not None:
            u.max_hp = u.hp = max(u.hp, 0) if b.t > 0 else u.hp
            hp_log.append((b.t, u.hp))
    b = Battle(lay, Stage([(0.0, "Golem", 21.0, 26.0, None)], [tick]), seed=0, town_hall=16)
    g = None
    b.max_time = 9.0
    # keep the Golem alive and still: huge HP, no movement
    orig = b.deploy

    def deploy(d):
        u = orig(d)
        u.hp = u.max_hp = u.base_max_hp = 1e7
        u.speed = 0.0
        return u
    b.deploy = deploy
    b.run()
    first = next((t for (t, h), (_, h0) in zip(hp_log[1:], hp_log) if h < h0), None)
    if first is None:
        check("Inferno single: fires at all", 0, 1, 0, "Inferno Tower")
        return

    def dps(a, c):
        pts = [(t, h) for t, h in hp_log if first + a <= t <= first + c]
        return (pts[0][1] - pts[-1][1]) / (pts[-1][0] - pts[0][0]) if len(pts) > 2 else 0.0
    check("Inferno single: DPS in first 1.5 s", dps(0.1, 1.3), s1, 0.15 * s1, "Inferno Tower stage 1")
    check("Inferno single: DPS 1.5-5.25 s", dps(1.7, 5.0), s2, 0.15 * s2, "Inferno Tower stage 2")
    check("Inferno single: DPS after 5.25 s", dps(5.6, 8.0), s3, 0.15 * s3, "Inferno Tower stage 3")


def _heal_test(target, rate_key, name):
    lv = OWN.get("attack_levels", {}).get("Healer") or stats.max_level("Healer", 16)
    want = stats.num(stats.row("Healer", lv).get(rate_key))
    lay = layout([("gs", 2, 2, None)])
    log = []

    def tick(b):
        u = unit_named(b, target)
        if u is not None:
            log.append((b.t, u.hp))
    from baselab.loadouts import HeroLoadout

    stage = Stage([(0.0, target, 38.0, 38.0, None), (0.0, "Healer", 37.0, 38.0, lv)], [tick])
    stage.loadouts = {target: HeroLoadout(target, (), None)}  # no equipment: measure the Healer alone
    b = Battle(lay, stage, seed=0, town_hall=16)
    orig = b.deploy

    def deploy(d):
        u = orig(d)
        if u.name == target:
            u.hp = u.max_hp * 0.3
            u.speed = 0.0
        return u
    b.deploy = deploy
    b.max_time = 8.0
    b.run()
    pts = [(t, h) for t, h in log if 2.0 <= t <= 7.5]
    rate = (pts[-1][1] - pts[0][1]) / (pts[-1][0] - pts[0][0]) if len(pts) > 2 else 0.0
    check(name, rate, want, 0.12 * want, f"Healer level {lv} {rate_key}", "/s")


def t_healer_troop():
    _heal_test("Root Rider", "Healing per Second", "Healer: heal rate on a troop")


def t_healer_hero():
    _heal_test("Royal Champion", "HPS on Heroes", "Healer: heal rate on a hero")


def t_root_rider_wall():
    """Root Riders break level 14-17 walls in about 0.8 s (wiki: Root Rider)."""
    wl = OWN["wall_level"]
    want = 0.0 if wl <= 10 else 0.4 if wl <= 13 else 0.8 if wl <= 17 else 1.2
    walls = {(x, 24) for x in range(14, 30)}
    lay = layout([("cannon", 20, 20, None)], walls)
    hits = {}
    b = Battle(lay, Stage([(0.0, "Root Rider", 21.0, 34.0, OWN.get("attack_levels", {}).get("Root Rider"))]), seed=0, town_hall=16)
    orig = b.hit_building

    def hit(o, amount, **kw):
        r = orig(o, amount, **kw)
        if getattr(o, "tx", None) is not None and r > 0:
            k = (o.tx, o.ty)
            hits.setdefault(k, [b.t, None])
            if not o.alive and hits[k][1] is None:
                hits[k][1] = b.t
        return r
    b.hit_building = hit
    b.max_time = 30.0
    b.run()
    times = [e - s for s, e in hits.values() if e is not None]
    check("Root Rider: time to break a wall", min(times) if times else 99.0, want, 0.25, f"Root Rider, wall level {wl}", "s")


def t_spell_durations():
    """Freeze stops a defense for its stated duration (wiki: Freeze Spell)."""
    lv = OWN.get("attack_levels", {}).get("Freeze Spell") or stats.max_level("Freeze Spell", 16)
    want = stats.get("Freeze Spell", lv, "Freeze Time", "Duration", default=None)
    if want is None:
        print(f"SKIP  Freeze: duration not in the stats table: {stats.row('Freeze Spell', lv)}")
        return
    lay = layout([("cannon", 20, 20, None), ("gs", 2, 2, None)])
    shots = []
    b = Battle(lay, Stage([(0.0, "Golem", 21.0, 26.0, None)], [lambda bb: bb.t == 0.5 and None]), seed=0, town_hall=16)
    cast = {"done": False}

    def tick(bb):
        if not cast["done"] and bb.t >= 1.0:
            spells.cast(bb, "Freeze Spell", 21.0 + MARGIN, 21.0 + MARGIN, level=lv)
            cast["done"] = True
    b.plan.ticks.append(tick)
    orig = b.hit_unit

    def hit(u, amount, **kw):
        r = orig(u, amount, **kw)
        if r > 0 and u.team == "atk":
            shots.append(b.t)
        return r
    b.hit_unit = hit
    orig_d = b.deploy

    def deploy(d):
        u = orig_d(d)
        u.hp = u.max_hp = 1e7
        u.speed = 0.0
        return u
    b.deploy = deploy
    b.max_time = 1.0 + want + 4.0
    b.run()
    gaps = [(a, c) for a, c in zip(shots, shots[1:]) if c - a > 1.5]
    gap = max((c - a for a, c in gaps), default=0.0)
    cannon = next(x for x in b.buildings if x.key == "cannon")
    # the silent gap is the freeze plus up to one normal reload
    check("Freeze: defense silent for the duration", gap - cannon.weapon.interval, want, 0.6, f"Freeze Spell level {lv}", "s")


TESTS = [t_inferno_ramp, t_healer_troop, t_healer_hero, t_root_rider_wall, t_spell_durations]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", default="")
    args = ap.parse_args()
    for t in TESTS:
        if args.k in t.__name__:
            try:
                t()
            except Exception as e:  # a crash is a failure, not a stop
                RESULTS.append(False)
                print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"== {sum(RESULTS)}/{len(RESULTS)} checks pass")


if __name__ == "__main__":
    main()
