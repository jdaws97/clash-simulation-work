"""Traps: Bomb, Giant Bomb, Air Bomb, Seeking Air Mine, Spring Trap,
Skeleton Trap, Tornado Trap and the TH17+ Giga Bomb.

Damage, radii and capacities come from the registry at the defender's trap
level; behaviour from the wiki pages mirrored 2026-10-15.
"""

from __future__ import annotations

import math

from ..mechanics import MARGIN, TRAP_NAMES, TRAP_SIZES
from . import stats
from .entities import Field, Trap, dist

FUSE = {"bomb": 1.5, "giant": 0.5, "airbomb": 0.5, "spring": 0.3, "seeking": 0.5, "giga": 0.5, "skeleton": 0.0, "tornado": 0.0}  # assumed
NO_TRIGGER = {
    "Spell Skeleton",
    "Skeleton",
    "Bat",
    "Totem",
    "Snake",
    "Electro Owl",  # wiki: Electro Owl
    "Booger",  # wiki: Sneezy/Booger
}  # wiki: Snake Bracelet/Snake
TORNADO_PULL = 3.0  # tiles/s for a unit of weight 1; divided by weight (assumed)


def _raw(name, key, default):
    return stats.num(stats.attrs(name).get("raw", {}).get(key), default)


def make_trap(battle, tp) -> Trap:
    name = TRAP_NAMES[tp.key]
    lv = battle.defense_levels.get("trap:" + tp.key) or stats.max_level(name, battle.town_hall) or 1
    size = TRAP_SIZES.get(tp.key, 1)
    x, y = tp.x + MARGIN + size / 2.0, tp.y + MARGIN + size / 2.0
    trigger = _raw(name, "Trigger Radius", 1.5)
    radius = stats.get(name, lv, "Damage Radius", default=None) or _raw(name, "Damage Radius", 0.0)
    dmg = stats.get(name, lv, "damage", "Damage", default=0.0)
    targets = (stats.attrs(name).get("raw", {}).get("Unit Type Targeted") or "Ground").lower()
    air, ground = "air" in targets, "ground" in targets
    tr = Trap(tp.key, name, x, y, lv, trigger, radius, dmg, air, ground, mode=tp.mode)
    if tp.key == "skeleton":
        air = tp.mode == "air"
        tr.air, tr.ground = air, not air
        tr.extra["count"] = int(stats.get(name, lv, "Spawned Units", default=4))
        tr.extra["skel_level"] = int(stats.get(name, lv, "Skeleton Level", default=1))
    elif tp.key == "spring":
        tr.extra["capacity"] = stats.get(name, lv, "Spring Capacity", default=18.0)
    elif tp.key == "tornado":
        tr.air = tr.ground = True
        tr.radius = radius or 3.0
        tr.extra["time"] = stats.get(name, lv, "Duration", default=7.0)
        # Tornado Trap: 39/47/55 one-damage pulses over 5/6/7 seconds.
        tr.extra["pulses"] = int(stats.get(name, lv, "Total Damage"))
    elif tp.key == "giga":
        tr.air = tr.ground = True
        tr.extra["housing"] = _raw(name, "Trigger Housing Space", 18.0)
    return tr


def _housing(u):
    if u.name == "Totem":
        return 20  # Totem Spell: Spring and Dark Crown interaction weight.
    if u.is_hero:
        return 25
    if u.kind == "pet":
        return 20
    return max(0, u.housing)


def _effect_target(tr: Trap, u, t) -> bool:
    if not u.alive or u.underground or u.attached(t) or u.extra.get("suspended"):
        return False
    if u.name == "Totem":
        return True
    return tr.air if u.flying else tr.ground


def _eligible(tr: Trap, u, t=0.0) -> bool:
    if not _effect_target(tr, u, t) or u.name in NO_TRIGGER:
        return False
    if u.name == "Dragon Duke" and u.dash is not None:
        return False  # Rocket Backpack: no new activation during the dash.
    if tr.key == "spring" and u.name == "Yetimite":
        return False  # Spring Trap: Yetimites cannot initiate a Spring.
    if tr.key == "seeking":
        if u.kind in ("siege", "siege_idle") and u.flying:
            return True  # Seeking Air Mine: aerial sieges are explicit targets.
        if _housing(u) < 5:
            return False  # Seeking Air Mine: ordinary air troops need 5 housing.
    return True


def tick(battle):
    t = battle.t
    for tr in battle.traps:
        if tr.extra.get("state") == "flight":
            _seeking_step(battle, tr)
            continue
        if not tr.armed:
            continue
        if tr.fuse_at >= 0:
            if t >= tr.fuse_at:
                _fire(battle, tr)
            continue
        near = [
            u
            for u in battle.attackers_near(tr.x, tr.y, tr.trigger)
            if _eligible(tr, u, t)
        ]
        if not near:
            continue
        if tr.key == "giga" and sum(_housing(u) for u in near) < tr.extra["housing"]:
            continue
        tr.extra["trigger_unit"] = min(near, key=lambda u: dist(u.x, u.y, tr.x, tr.y))
        tr.fuse_at = t + FUSE[tr.key]
        if tr.fuse_at <= t:
            _fire(battle, tr)


def _fire(battle, tr: Trap):
    tr.armed = False
    t = battle.t
    battle._src = "trap:" + tr.key
    src = battle._src
    if battle.record:
        battle.log.append((round(t, 1), "trap", tr.key))
    k = tr.key
    if k in ("bomb", "giant"):
        battle.splash_units(tr.x, tr.y, tr.radius, tr.damage, tr.air, tr.ground, team="atk", src=src, kind="trap")
        # Bomb/Giant Bomb: housing <=3 can be pushed, even through Tome.
        for u in battle.attackers_near(tr.x, tr.y, tr.radius):
            if (
                u.alive
                and not u.is_hero
                and u.kind not in ("pet", "siege", "siege_idle")
                and _effect_target(tr, u, t)
                and 0 < u.housing <= 3
            ):
                u.extra["trap_knockback_at"] = t
        # Knockback distance/speed are NUMBER NOT STATED; only record eligibility.
    elif k == "airbomb":
        # Air Bomb: opening time and flight speed are NUMBER NOT STATED.
        # Resolve the existing fuse at the acquired target; flight remains unresolved.
        u = tr.extra.get("trigger_unit")
        # Air Bomb: replacements can be within twice the trigger radius.
        radius = tr.trigger if u is not None and u.alive else 2 * tr.trigger
        cands = [
            a for a in battle.attackers_near(tr.x, tr.y, radius) if _eligible(tr, a, t)
        ]
        if u is not None and u.alive and _effect_target(tr, u, t):
            cands.append(u)
        if not cands:
            return
        u = min(cands, key=lambda a: dist(a.x, a.y, tr.x, tr.y))
        battle.splash_units(
            u.x,
            u.y,
            tr.radius,
            tr.damage,
            True,
            False,
            team="atk",
            src=src,
            kind="trap",
        )
    elif k == "giga":
        pool = [u for u in battle.attackers_near(tr.x, tr.y, tr.radius) if u.name != "Totem" and not u.underground]
        battle.splash_units(tr.x, tr.y, tr.radius, tr.damage, True, True, team="atk", src=src, kind="trap")
        for u in pool:
            if (
                u.alive
                and u.kind not in ("siege", "siege_idle")
                and _effect_target(tr, u, t)
            ):
                if not u.flying and u.x == tr.x and u.y == tr.y:
                    u.extra["giga_launch_at"] = t  # Giga Bomb: center launch event.
                # Giga Bomb: displacement function and airtime are NUMBER NOT STATED.
                u.target = None
                u.wall_target = None
    elif k == "seeking":
        u = tr.extra.get("trigger_unit")
        if u is None or not u.alive or not _effect_target(tr, u, t):
            return  # Seeking Air Mine: a committed dead target wastes the mine.
        # Seeking Air Mine: opening time is NUMBER NOT STATED; retain the fuse.
        tr.extra["state"] = "flight"
        tr.extra["projectile"] = (tr.x, tr.y)
    elif k == "spring":
        # Spring Trap: select among units still in the stated trigger radius.
        # Delay/current effect geometry are NUMBER NOT STATED; no historical radius.
        cands = [
            a
            for a in battle.attackers_near(tr.x, tr.y, tr.trigger)
            if _effect_target(tr, a, t)
        ]
        if not cands:
            return
        u = max(cands, key=lambda a: (_housing(a), -dist(a.x, a.y, tr.x, tr.y)))  # highest housing first (wiki)
        special = u.is_hero or u.kind in ("pet", "siege", "siege_idle")
        if not special and 0 < u.housing <= tr.extra["capacity"]:
            battle.kills_by_source[src] = battle.kills_by_source.get(src, 0) + u.housing
            u.extra["sprung"] = True  # Spring Trap: Druid cannot become a Bear.
            battle.kill(u)  # flung off the map; death effects still happen (wiki: Ice Golem)
            return
        dmg = tr.damage * (0.5 if special else 1.0)  # halved vs heroes, pets, sieges (wiki)
        battle.hit_unit(u, dmg, src=src, kind="trap")
        if u.alive and u.kind not in ("siege", "siege_idle"):
            u.stun_until = max(u.stun_until, t + 1.0)  # "stun them for a short while" (assumed 1 s)
    elif k == "skeleton":
        n = tr.extra["count"]
        for j in range(n):
            ang = 2 * math.pi * j / max(1, n)
            s = battle.spawn("Skeleton", "def", tr.x + 0.7 * math.cos(ang), tr.y + 0.7 * math.sin(ang), level=tr.extra["skel_level"], kind="trap_skeleton")
            # Skeleton Trap: dedicated Skeleton stats, indexed by Skeleton level.
            lv = tr.extra["skel_level"]
            s.hp = s.max_hp = s.base_max_hp = stats.get(tr.name, lv, "Hitpoints")
            s.dmg = stats.get(tr.name, lv, "Damage per Hit")
            s.interval = _raw(tr.name, "Attack Speed", None)
            s.range = _raw(tr.name, "Range", None)
            s.flying = tr.mode == "air"
            s.hits_air, s.hits_ground = s.flying, not s.flying
            s.speed = 2.2 if s.flying else 3.0  # Skeleton Trap: 17.6/24 display speed.
    elif k == "tornado":
        f = Field(
            "tornado",
            tr.x,
            tr.y,
            tr.radius,
            t + tr.extra["time"],
            team="def",
            extra={"pulses": tr.extra["pulses"], "delivered": 0},
            started=t,
        )
        battle.fields.append(f)
        tornado_tick(battle, f)


def _seeking_step(battle, tr: Trap):
    u = tr.extra["trigger_unit"]
    if not u.alive or not _effect_target(tr, u, battle.t):
        tr.extra["state"] = "spent"
        return
    x, y = tr.extra["projectile"]
    d = dist(x, y, u.x, u.y)
    step = 3.5 * battle.DT  # Seeking Air Mine: projectile speed is 3.5 tiles/s.
    if d <= step:
        tr.extra["projectile"] = (u.x, u.y)
        tr.extra["state"] = "spent"
        battle.hit_unit(u, tr.damage, src="trap:seeking", kind="trap")
    else:
        tr.extra["projectile"] = (
            x + (u.x - x) / d * step,
            y + (u.y - y) / d * step,
        )


def tornado_tick(battle, f: Field):
    """Deliver the wiki pulse budget independently of the solver interval."""
    t = battle.t
    # Tornado Trap: each pulse deals 1 damage, at 0.128-second intervals.
    delivered = f.extra["delivered"]
    while delivered < f.extra["pulses"]:
        at = f.started + delivered * 0.128
        if at > min(t, f.until):
            break
        try:
            battle.t = at
            for u in battle.attackers_near(f.x, f.y, f.radius):
                if not u.underground:
                    battle.hit_unit(u, 1.0, src="trap:tornado", kind="trap")
        finally:
            battle.t = t
        delivered += 1
    f.extra["delivered"] = delivered
    if t >= f.until:
        return
    for u in battle.attackers_near(f.x, f.y, f.radius):
        if not u.alive or u.underground or u.attached(t) or u.extra.get("suspended"):
            continue
        if t < u.extra.get("tornado_wall_until", 0.0):
            continue
        if u.name in ("Totem", "Miner", "Super Miner", "Diggy", "Battle Drill"):
            continue  # Tornado Trap: damage and displacement exemptions differ.
        # Tornado Trap: heroes/pets weigh 5; mobile sieges weigh 1.
        if u.is_hero or u.kind == "pet":
            weight = 5
        elif u.kind in ("siege", "siege_idle"):
            if u.speed <= 0:
                continue
            weight = 1
        else:
            weight = min(5, max(1, math.ceil(u.housing / 3)))
        # Tornado Trap: angular/pull speeds, air multiplier and capture geometry
        # are NUMBER NOT STATED; the existing pull remains an approximation.
        d = dist(u.x, u.y, f.x, f.y)
        if d > 0.3:
            step = min(d - 0.3, TORNADO_PULL / weight * battle.DT)
            nx = u.x + (f.x - u.x) / d * step
            ny = u.y + (f.y - u.y) / d * step
            _tornado_move(battle, u, nx, ny, f.until)


def _tornado_move(battle, u, nx, ny, until):
    if u.flying:
        u.x, u.y = nx, ny
        return
    first = None
    for w in battle.walls.values():
        if not w.alive:
            continue
        enter, leave = 0.0, 1.0
        for start, end, center in ((u.x, nx, w.x), (u.y, ny, w.y)):
            low, high = center - w.half_hit, center + w.half_hit
            delta = end - start
            if delta == 0:
                if start < low or start > high:
                    leave = -1.0
                    break
                continue
            a, b = sorted(((low - start) / delta, (high - start) / delta))
            enter, leave = max(enter, a), min(leave, b)
        if enter <= leave and (first is None or enter < first):
            first = enter
    if first is None:
        u.x, u.y = nx, ny
        return
    # Tornado Trap: ground units caught on walls stay until the field ends.
    u.extra["tornado_wall_until"] = max(u.extra.get("tornado_wall_until", 0.0), until)
    u.x = math.nextafter(u.x + (nx - u.x) * first, u.x)
    u.y = math.nextafter(u.y + (ny - u.y) * first, u.y)
