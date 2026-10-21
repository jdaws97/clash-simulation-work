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
            spells.cast_effect(bb, "Freeze Spell", 21.0 + MARGIN, 21.0 + MARGIN, lv)
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


def _trap_battle(traps_, drops, max_time):
    """Traps on an empty lawn (one far storage); dropped units stand still
    with huge HP. Returns the battle and a log of (t, unit, damage, src)."""
    from baselab.layout import TrapPlacement

    lay = layout([("gs", 2, 2, None)])
    lay.traps = [TrapPlacement(k, x, y, m) for k, x, y, m in traps_]
    hits = []
    b = Battle(lay, Stage(drops), seed=0, town_hall=16)
    orig_d, orig_h = b.deploy, b.hit_unit

    def deploy(d):
        u = orig_d(d)
        u.hp = u.max_hp = u.base_max_hp = 1e6
        u.speed = 0.0
        return u

    def hit(u, amount, **kw):
        r = orig_h(u, amount, **kw)
        if r > 0:
            hits.append((b.t, u, r, kw.get("src") or b._src))
        return r
    b.deploy, b.hit_unit = deploy, hit
    b.max_time = max_time
    b.run()
    return b, hits


def t_bomb_and_giant_bomb():
    """Bomb detonates 1.5 s after a troop comes within 1 tile (wiki: Bomb
    history, "Reduced detonation delay from 2 seconds to 1.5 seconds"). A
    Giant Bomb hits every ground troop within its damage radius for its
    level's damage and none outside (wiki: Giant Bomb statistics)."""
    b, hits = _trap_battle([("bomb", 20, 20, None)], [(0.0, "Golem", 20.5, 20.5, None)], 4.0)
    first = next((t for t, u, r, s in hits if s == "trap:bomb"), 99.0)
    check("Bomb: detonation delay", first, 1.5, 0.15, "Bomb", "s")
    from baselab.engine import traps as trapmod
    from baselab.layout import TrapPlacement

    probe = Battle(layout([("gs", 2, 2, None)]), Stage([]), seed=0, town_hall=16)
    tr = trapmod.make_trap(probe, TrapPlacement("giant", 20, 20))
    c = 21.0  # 2x2 Giant Bomb at (20,20): centre (21,21) in tile coordinates
    drops = [
        (0.0, "Valkyrie", c + 1.0, c, None),
        (0.0, "Valkyrie", c, c - 1.0, None),
        (0.5, "Valkyrie", c + tr.radius - 0.1, c, None),
        (0.5, "Valkyrie", c, c + tr.radius + 0.2, None),
    ]
    b, hits = _trap_battle([("giant", 20, 20, None)], drops, 4.0)
    per = {}
    for t, u, r, s in hits:
        if s == "trap:giant":
            per[id(u)] = per.get(id(u), 0.0) + r
    valks = [u for u in b.attackers if u.name == "Valkyrie"]
    inside = [per.get(id(u), 0.0) for u in valks[:3]]
    outside = per.get(id(valks[3]), 0.0) if len(valks) > 3 else -1.0
    check("Giant Bomb: damage to Valkyries inside", min(inside), tr.damage, 0.5, f"Giant Bomb level {tr.level}, radius {tr.radius}")
    check("Giant Bomb: no damage just outside radius", outside, 0.0, 0.0, "Giant Bomb")


def t_seeking_threshold():
    """Seeking Air Mine: a Balloon (5 housing) triggers it and takes the
    mine's damage; a Minion (2 housing) neither triggers nor is hit (wiki:
    Seeking Air Mine; game data MinTriggerHousingLimit=5)."""
    drops = [(0.0, "Balloon", 10.5, 10.5, None), (0.0, "Minion", 30.5, 30.5, None)]
    b, hits = _trap_battle([("seeking", 10, 10, None), ("seeking", 30, 30, None)], drops, 4.0)
    loon = sum(r for t, u, r, s in hits if u.name == "Balloon" and s == "trap:seeking")
    minion = sum(r for t, u, r, s in hits if u.name == "Minion" and s == "trap:seeking")
    check("Seeking Air Mine: Balloon takes the mine", loon, b.traps[0].damage, 0.5, f"Seeking Air Mine level {b.traps[0].level}")
    check("Seeking Air Mine: Minion cannot trigger", minion + (0.0 if b.traps[1].armed else 1.0), 0.0, 0.0, "Seeking Air Mine")


def t_life_gem_radius():
    """Grand Warden Life Gem: +min(%, cap) max HP within 9 tiles (game data
    Life Gem Aura.Radius=900), nothing beyond."""
    from baselab.loadouts import HeroLoadout

    lv = stats.max_level("Life Gem", 16)
    pct = stats.get("Life Gem", lv, "~% hp increase") / 100.0
    cap = stats.get("Life Gem", lv, "~max hp increase")
    stage = Stage([(0.0, "Grand Warden", 38.0, 38.0, None), (0.0, "Golem", 29.5, 38.0, None), (0.0, "Golem", 38.0, 28.5, None)])
    stage.loadouts = {"Grand Warden": HeroLoadout("Grand Warden", ("Life Gem",), None)}
    b = Battle(layout([("gs", 2, 2, None)]), stage, seed=0, town_hall=16)
    orig = b.deploy

    def deploy(d):
        u = orig(d)
        u.speed = 0.0
        return u
    b.deploy = deploy
    b.max_time = 1.0
    b.run()
    inside, outside = [u for u in b.attackers if u.name == "Golem"]
    check("Life Gem: bonus HP at 8.5 tiles", inside.max_hp - inside.base_max_hp, min(pct * inside.base_max_hp, cap), 0.5, f"Life Gem level {lv}")
    check("Life Gem: no bonus at 9.5 tiles", outside.max_hp - outside.base_max_hp, 0.0, 0.0, "Life Gem Aura radius 9")


def t_raged_walk():
    """A raged Hog Rider walks at its speed plus the Rage Spell's speed
    increase (wiki: Rage Spell, speed in wiki units / 8 tiles per second);
    path movement once stopped at each half-tile waypoint (capped 5 t/s)."""
    from baselab.engine import units

    lv = OWN.get("attack_levels", {}).get("Rage Spell") or stats.max_level("Rage Spell", 16)
    boost = stats.get("Rage Spell", lv, "Speed Increase") / 8.0
    b = Battle(layout([("gs", 40, 20, None)]), Stage([(0.0, "Hog Rider", 4.0, 21.5, None)]), seed=0, town_hall=16)
    b.step()
    hog = unit_named(b, "Hog Rider")
    units.add_rage(hog, "test", 1.0, boost, 1e9)
    b.step()
    x0 = hog.x
    for _ in range(20):
        b.step()
    want = b.speed_of(hog)
    check("Raged Hog Rider: walking speed", (hog.x - x0) / 2.0, want, 0.1, f"Rage Spell level {lv}, +{boost:.2f} t/s", " t/s")


TESTS = [t_inferno_ramp, t_healer_troop, t_healer_hero, t_root_rider_wall, t_spell_durations, t_bomb_and_giant_bomb, t_seeking_threshold, t_life_gem_radius, t_raged_walk]


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
