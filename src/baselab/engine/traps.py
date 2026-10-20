"""Traps: Bomb, Giant Bomb, Air Bomb, Seeking Air Mine, Spring Trap,
Skeleton Trap, Tornado Trap and the TH17+ Giga Bomb.

Damage, radii and capacities come from the registry at the defender's trap
level (checked equal to game data v18.200.9 Traps.csv for TH16-17; Giant
Bomb level 12 at TH18 is wiki-only). Timing, trigger eligibility, pushes and
projectiles follow game data v18.200.9 where it states them, else the wiki
pages mirrored 2026-10-15.
"""

from __future__ import annotations

import math

from ..mechanics import MARGIN, TRAP_NAMES, TRAP_SIZES
from . import stats
from .entities import Field, Pending, Trap, dist

# Trigger-to-effect delay. game data v18.200.9 Traps.csv ActionFrame (the
# frame of the triggered animation on which the trap acts): Bomb=35,
# GiantBomb=37, GigaBomb=38, AirBomb=7, SeekingAirMine=7, TornadoTrap=8,
# SpringTrap=5. The wiki states only the Bomb's delay ("approximately 1.5
# seconds", wiki: Bomb), so frames are converted at that rate (1.5 s / 35
# frames, about 24 frames/s). Skeleton Trap gives its delay in ms instead.
_FRAME_S = 1.5 / 35
FUSE = {
    "bomb": 35 * _FRAME_S,
    "giant": 37 * _FRAME_S,
    "giga": 38 * _FRAME_S,
    "airbomb": 7 * _FRAME_S,
    "seeking": 7 * _FRAME_S,
    "tornado": 8 * _FRAME_S,
    # Spring: ActionFrame=5 gives 0.21 s, but the wiki's "speed 32 or above
    # ... move across it unaffected" needs a longer delay or smaller victim
    # radius than the data shows; the earlier assumed 0.3 s is kept.
    "spring": 0.3,
    # game data v18.200.9: Traps.csv SkeletonTrap.SpawnInitialDelayMs=600 -> 0.6 s.
    "skeleton": 0.6,
}
# game data v18.200.9: TriggersTraps=FALSE in Characters.csv (Spell
# Shielded/Unshielded Skeleton, Skeleton, Spell Bat, Totem, Yetimite,
# Electromite, Firemite Spawn, Icemite = Frostmite, Booger) and Pets.csv
# (Electro Owl, Poison Lizard). Engine names are used here.
NO_TRIGGER = {
    "Spell Skeleton",
    "Skeleton",
    "Bat",
    "Totem",
    "Yetimite",  # also wiki: Yeti/Yetimite history, Jan 16 2020
    "Electromite",
    "Firemite",
    "Frostmite",
    "Booger",  # also wiki: Sneezy/Booger
    "Electro Owl",  # also wiki: Electro Owl
    "Poison Lizard",
}
# Snake Bracelet snakes are NOT excluded: game data v18.200.9 Characters.csv
# BK Equipment Snake.TriggersTraps=TRUE (the wiki's Snake Bracelet/Snake
# strategy text says they cannot; the game data is followed).

# game data v18.200.9: Spells.csv TornadoTrap.TornadoForce1..5 (ground) and
# TornadoForceAir1..5 (air) by weight 1..5: 400/300/200/100/100 and
# 500/400/300/200/150, read as hundredths of a tile per second.
TORNADO_FORCE = {False: (4.0, 3.0, 2.0, 1.0, 1.0), True: (5.0, 4.0, 3.0, 2.0, 1.5)}
# game data v18.200.9: TornadoTrap.TornadoInnerRadius=70 -> 0.7 tiles,
# TornadoInnerForcePercent=100, TornadoOuterForcePercent=65.
TORNADO_INNER, TORNADO_INNER_PCT, TORNADO_OUTER_PCT = 0.7, 1.0, 0.65
# game data v18.200.9: Traps.csv Bomb/GiantBomb.Pushback=100 and
# PushbackHousingLimit=3, the same values as Mortar, whose push the wiki
# states as 2 tiles (wiki: Barbarian, Mortar knocks Barbarians back 2 tiles).
TRAP_PUSH = 2.0
# game data v18.200.9: Traps.csv GigaBomb.RadialThrowDistance=200 -> 2 tiles,
# RadialThrowRadius=450 -> 4.5 tiles.
GIGA_THROW = 2.0


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
        # Totem Spell: Spring and Dark Crown interaction weight;
        # game data v18.200.9: Characters.csv Totem.HousingSpace=20.
        return 20
    if u.is_hero:
        return 25  # game data v18.200.9: Heroes.csv HousingSpace=25 (every hero).
    if u.kind == "pet":
        return 20  # game data v18.200.9: Pets.csv HousingSpace=20 (every pet).
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
        # game data v18.200.9: DragonDukeDeadlyDash*.TriggersTraps=FALSE (wiki: Rocket Backpack).
        return False
    if tr.key == "seeking":
        if u.kind in ("siege", "siege_idle") and u.flying:
            return True  # Seeking Air Mine: aerial sieges are explicit targets.
        if _housing(u) < 5:
            # game data v18.200.9: Traps.csv SeekingAirMine.MinTriggerHousingLimit=5.
            return False
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
    # Restore the damage label afterwards: later untagged hits in the same
    # tick (Clan Castle, Guardians, attackers) must not be credited to traps.
    prev = battle._src
    try:
        _fire_effect(battle, tr)
    finally:
        battle._src = prev


def _fire_effect(battle, tr: Trap):
    tr.armed = False
    t = battle.t
    battle._src = "trap:" + tr.key
    src = battle._src
    if battle.record:
        battle.log.append((round(t, 1), "trap", tr.key))
    k = tr.key
    if k in ("bomb", "giant"):
        battle.splash_units(tr.x, tr.y, tr.radius, tr.damage, tr.air, tr.ground, team="atk", src=src, kind="trap")
        # Bomb/Giant Bomb: surviving ground troops of housing <=3 are knocked
        # away from the blast, even through Tome (wiki: Bomb; Giant Bomb).
        # TRAP_PUSH is the Mortar-equivalent 2 tiles; the wiki's smaller push
        # for larger housing is NUMBER NOT STATED, so all <=3 get 2 tiles.
        for u in battle.attackers_near(tr.x, tr.y, tr.radius):
            if (
                u.alive
                and not u.is_hero
                and u.kind not in ("pet", "siege", "siege_idle")
                and _effect_target(tr, u, t)
                and u.name != "Totem"
                and 0 < u.housing <= 3
            ):
                d = dist(u.x, u.y, tr.x, tr.y)
                if d > 0:
                    battle._nudge(u, TRAP_PUSH * (u.x - tr.x) / d, TRAP_PUSH * (u.y - tr.y) / d)
                u.target = u.wall_target = None
    elif k == "airbomb":
        # Opening time: FUSE (ActionFrame=7).
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
        # game data v18.200.9: Projectiles.csv AirTrapBalloon.Speed=250 -> 2.5 tiles/s,
        # DontTrackTarget=TRUE: it flies to the acquired location.
        flight = dist(tr.x, tr.y, u.x, u.y) / 2.5
        battle.add_pending(
            Pending(
                t + flight,
                u.x,
                u.y,
                tr.radius,
                tr.damage,
                True,
                False,
                src,
                effect="trap",
            )
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
                # Radial throw of GIGA_THROW tiles (game data RadialThrowDistance);
                # a unit exactly at the centre is blasted upwards instead
                # (wiki: Giga Bomb). The wiki's longer throw for farther ground
                # units and the airtime are NUMBER NOT STATED.
                d = dist(u.x, u.y, tr.x, tr.y)
                if d > 0:
                    battle._nudge(u, GIGA_THROW * (u.x - tr.x) / d, GIGA_THROW * (u.y - tr.y) / d)
                u.target = None
                u.wall_target = None
    elif k == "seeking":
        u = tr.extra.get("trigger_unit")
        if u is None or not u.alive or not _effect_target(tr, u, t):
            return  # Seeking Air Mine: a committed dead target wastes the mine.
        # Opening time: FUSE (ActionFrame=7); then the homing flight.
        tr.extra["state"] = "flight"
        tr.extra["projectile"] = (tr.x, tr.y)
    elif k == "spring":
        # Spring Trap: select among units still in the stated trigger radius
        # (wiki). game data v18.200.9 EjectRadius=200 is not used: with it no
        # fast troop could pass, contrary to the wiki; F11 stays open.
        cands = [
            a
            for a in battle.attackers_near(tr.x, tr.y, tr.trigger)
            if _effect_target(tr, a, t)
        ]
        if not cands:
            return
        # game data v18.200.9: SpringTrap.TargetHighestHousing=TRUE (also wiki).
        u = max(cands, key=lambda a: (_housing(a), -dist(a.x, a.y, tr.x, tr.y)))
        # game data v18.200.9: AttemptEjectBeforeDamage=TRUE, EjectHousingLimit=capacity;
        # Pets.csv CantBeEjected=TRUE for every pet.
        special = u.is_hero or u.kind in ("pet", "siege", "siege_idle")
        if not special and 0 < u.housing <= tr.extra["capacity"]:
            battle.kills_by_source[src] = battle.kills_by_source.get(src, 0) + u.housing
            u.extra["sprung"] = True  # Spring Trap: Druid cannot become a Bear.
            battle.kill(u)  # flung off the map; death effects still happen (wiki: Ice Golem)
            return
        # game data v18.200.9: SpringTrap.Hero/Pet/SiegeDamageReductionPercent=50 (also wiki).
        dmg = tr.damage * (0.5 if special else 1.0)
        battle.hit_unit(u, dmg, src=src, kind="trap")
        if u.alive and u.kind not in ("siege", "siege_idle"):
            u.stun_until = max(u.stun_until, t + 1.0)  # "stun them for a short while" (assumed 1 s)
    elif k == "skeleton":
        n = tr.extra["count"]
        for j in range(n):
            ang = 2 * math.pi * j / max(1, n)
            s = battle.spawn("Skeleton", "def", tr.x + 0.7 * math.cos(ang), tr.y + 0.7 * math.sin(ang), level=tr.extra["skel_level"], kind="trap_skeleton")
            # game data v18.200.9: Traps.csv SkeletonTrap.TimeBetweenSpawnsMs=150 -> 0.15 s apart.
            s.active_at = t + 0.15 * j
            # Skeleton Trap: dedicated Skeleton stats, indexed by Skeleton level;
            # matches game data v18.200.9 Characters.csv Trap Skeleton / Trap Air
            # Skeleton: Hitpoints=30|45, AttackSpeed=700, DPS=25|30, Speed=300/220,
            # IsFlying FALSE/TRUE, AirTargets FALSE/TRUE.
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
    # game data v18.200.9: Projectiles.csv LargeDarkElixirBalloon.Speed=350 -> 3.5 tiles/s,
    # DontTrackTarget=FALSE: it homes on its committed target.
    step = 3.5 * battle.DT
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
        # Tornado Trap: heroes/pets weigh 5; sieges weigh 1 (also game data
        # v18.200.9: Globals.csv TORNADO_SIEGE_FORCE_TIER=1).
        if u.is_hero or u.kind == "pet":
            weight = 5
        elif u.kind in ("siege", "siege_idle"):
            if u.speed <= 0:
                continue
            weight = 1
        else:
            weight = min(5, max(1, math.ceil(u.housing / 3)))
        # Pull speed: the game-data force for this weight (air table for
        # flying units), 100% inside TORNADO_INNER and 65% at the edge.
        # Assumed: the force is the pull speed toward the centre, linear in
        # between; the rotation (TornadoRotationSpeed=-180) is not modelled.
        d = dist(u.x, u.y, f.x, f.y)
        if d > TORNADO_INNER:
            frac = min(1.0, (d - TORNADO_INNER) / max(1e-9, f.radius - TORNADO_INNER))
            pct = TORNADO_INNER_PCT + (TORNADO_OUTER_PCT - TORNADO_INNER_PCT) * frac
            speed = TORNADO_FORCE[bool(u.flying)][weight - 1] * pct
            step = min(d - TORNADO_INNER, speed * battle.DT)
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
