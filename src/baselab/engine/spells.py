"""Spells: every attacking spell, Spell Tower casts and defensive poison.

Numbers come from the registry row of the spell at its level; mechanics from
the wiki pages mirrored 2026-10-15. Values the wiki does not state are marked
'assumed'.
"""

from __future__ import annotations

import math

from . import defense, effects, stats
from .entities import Building, Field, Unit, Wall, dist
from .specs import SUBTROOP_HOUSING

LAND_DELAY = 0.5  # time for a spell bottle to land (assumed)
STORAGES = {"gs", "es", "ds"}
# Units that never trigger traps, Clan Castle troops or Spell Towers (wiki:
# Skeleton Spell, Bat Spell, Totem Spell pages).
NO_TRIGGER = {"Spell Skeleton", "Skeleton", "Bat", "Totem"}
POISON_LINGER = 6.0  # wiki: effect lasts 6 s after leaving the radius
POISON_RAMP = 4.0  # seconds to reach max damage per second (assumed)
POISON_HERO_MULT = 0.5  # "much less damage against Heroes" (assumed factor)


def _lvl(battle, name, level):
    if level:
        return level
    plan = battle.plan
    lv = (getattr(plan, "spell_levels", {}) or {}).get(name)
    return lv or stats.max_level(name, getattr(plan, "town_hall", battle.town_hall))


def _radius(name, level, default):
    r = stats.get(name, level, "radius", "Radius", default=None)
    if not r:
        r = stats.num(stats.attrs(name).get("raw", {}).get("Radius"), default)
    return r or default


def _affected(u: Unit) -> bool:
    return u.alive and u.kind not in ("siege", "siege_idle") and u.name != "Totem"


# ------------------------------------------------------------------- cast
def cast(battle, name, x, y, level=None):
    """Drop an attacking spell at (x, y)."""
    lv = _lvl(battle, name, level)
    battle.start_battle()
    if battle.first_deploy_t is None:
        battle.first_deploy_t = battle.t
    t = battle.t + LAND_DELAY
    if battle.record:
        battle.log.append((round(battle.t, 1), "spell", name, round(x, 1), round(y, 1)))
    f = None
    if name == "Lightning Spell":
        f = Field("lightning", x, y, _radius(name, lv, 2.0), t, value=stats.get(name, lv, "damage", "Damage", default=640.0))
    elif name == "Healing Spell":
        per = stats.get(name, lv, "Healing per Pulse", default=60.0)
        f = Field("heal", x, y, 5.0, t + 12.3, value=per / 0.3)
    elif name == "Rage Spell":
        inc = stats.get(name, lv, "Damage Increase", default=180.0) / 100.0
        spd = stats.get(name, lv, "Speed Increase", default=30.0) / 8.0
        f = Field("rage", x, y, 5.0, t + 18.0, value=1.0 + inc, extra={"speed": spd})
    elif name == "Jump Spell":
        f = Field("jump", x, y, _radius(name, lv, 3.5), t + stats.get(name, lv, "duration", default=60.0), extra={"cleared": []})
    elif name == "Freeze Spell":
        f = Field("freeze", x, y, 3.5, t, value=stats.get(name, lv, "Freeze Time", default=2.0 + 0.5 * lv))
    elif name == "Poison Spell":
        dur = stats.num(stats.attrs(name).get("raw", {}).get("Spell Duration"), 16.0)
        f = Field("poison", x, y, 4.0, t + dur, value=stats.get(name, lv, "Max damage per second", default=340.0),
                  extra={"slow": stats.get(name, lv, "Speed Decrease", default=50.0) / 100.0,
                         "atk": stats.get(name, lv, "Attack Rate Decrease", default=72.0) / 100.0})
    elif name == "Earthquake Spell":
        f = Field("quake", x, y, _radius(name, lv, 4.7), t, value=stats.get(name, lv, "Building Damage %", default=29.0) / 100.0,
                  extra={"troop": stats.get(name, lv, "Troop Damage %", default=0.0) / 100.0})
    elif name == "Haste Spell":
        dur = stats.get(name, lv, "Spell Duration", default=30.0)
        f = Field("haste", x, y, _radius(name, lv, 4.0), t + dur, extra={"speed": stats.get(name, lv, "Speed Increase", default=52.0) / 8.0})
    elif name == "Clone Spell":
        f = Field("clone", x, y, 3.5, t + 18.0, value=stats.get(name, lv, "Cloned Capacity", default=42.0), extra={"done": set()})
    elif name == "Skeleton Spell":
        f = Field("summon", x, y, 2.2, t, value=stats.get(name, lv, "Skeletons generated", default=19.0), extra={"unit": "Spell Skeleton"})
    elif name == "Bat Spell":
        f = Field("summon", x, y, 2.2, t, value=stats.get(name, lv, "Bats generated", default=22.0), extra={"unit": "Bat"})
    elif name == "Bag of Frostmites":
        f = Field("summon", x, y, 1.75, t, value=stats.get(name, lv, "Frostmites spawned", default=17.0), extra={"unit": "Frostmite"})
    elif name == "Invisibility Spell":
        f = Field("invis", x, y, 4.0, t + stats.get(name, lv, "Duration", default=4.25))
    elif name == "Recall Spell":
        f = Field("recall", x, y, 5.0, t, value=stats.get(name, lv, "Recalled Capacity", default=107.0))
    elif name == "Overgrowth Spell":
        f = Field("overgrowth", x, y, 6.0, t, value=stats.get(name, lv, "Duration", default=25.0))
    elif name == "Revive Spell":
        f = Field("revive_cast", x, y, 8.0, t, value=stats.get(name, lv, "Hero Heal %", default=70.0) / 100.0)
    elif name == "Ice Block Spell":
        f = Field("iceblock", x, y, 5.0, t, value=stats.get(name, lv, "Incoming Damage Reduction", default=92.0) / 100.0,
                  extra={"time": stats.get(name, lv, "Duration", default=7.0)})
    elif name == "Totem Spell":
        f = Field("totem", x, y, 5.0, t, value=stats.get(name, lv, "Totem Hitpoints", default=11000.0))
    elif name == "Angry Spell":
        f = Field("angry", x, y, 6.0, t + stats.get(name, lv, "Duration", default=5.0), value=stats.get(name, lv, "Anger Duration", default=8.0))
    elif name == "Santa's Surprise":
        f = Field("santa", x, y, 4.0, t, value=stats.get(name, lv, "Damage per Strike", default=370.0))
    else:
        raise KeyError(f"unknown spell {name}")
    f.started = t
    f.extra["name"] = name
    battle.fields.append(f)
    # Wiki: Eagle Artillery, each spell housing space contributes five.
    battle.deployed_housing += 5 * stats.attrs(name)["housing"]
    return f


# ------------------------------------------------------------------- tick
def tick(battle):
    t = battle.t
    keep = []
    for f in battle.fields:
        if t < f.started:
            keep.append(f)
            continue
        if f.kind == "tornado" and t >= f.until:
            from . import traps

            # Tornado Trap: drain remaining pulses without an extra expiry tick.
            traps.tornado_tick(battle, f)
            _expire(battle, f)
            continue
        alive = _apply(battle, f)
        if alive and t < f.until:
            keep.append(f)
        else:
            _expire(battle, f)
    battle.fields = keep
    _poison_states(battle)
    _clone_expiry(battle)


def _apply(battle, f: Field) -> bool:
    """Apply one tick of a field. Returns False when the field is spent."""
    t = battle.t
    dt = battle.DT
    k = f.kind
    if k in ("poison", "def_poison", "def_rage", "def_burn") and t >= f.until:
        return False
    if k in ("lightning", "freeze", "poison", "totem", "def_rage") or (
        k == "rage" and f.team == "def"
    ):
        defense.builder_spell(battle, f)
    if k in ("tesla_freeze", "tesla_overgrowth"):
        if t >= f.until:
            return False
        if k == "tesla_freeze":
            defense.builder_spell(battle, f)
        for building in battle.buildings:
            if (
                building.alive
                and building.key == "tesla"
                and building.revealed
                and building.edge_distance(f.x, f.y) <= f.radius
            ):
                if k == "tesla_freeze":
                    building.frozen_until = max(building.frozen_until, f.until)
                else:
                    building.overgrown_until = max(building.overgrown_until, f.until)
        return True
    if k == "lightning":
        battle._src = "spell"
        for b in battle.buildings:
            if (
                b.alive
                and b.key not in STORAGES | {"th", "cc"}
                and not (b.key == "tesla" and not b.revealed)
                and b.edge_distance(f.x, f.y) <= f.radius
            ):
                battle.hit_building(b, f.value)
                if b.weapon is not None:
                    # Wiki: Lightning Spell/Home Village, Stun Time.
                    duration = stats.num(
                        stats.attrs("Lightning Spell")["raw"]["Stun Time"]
                    )
                    b.stun_until = max(b.stun_until, t + duration)
                    _retarget(b)
        for key, w in battle.walls.items():
            if w.alive and w.edge_distance(f.x, f.y) <= f.radius:
                battle.hit_building(w, f.value)
        for u in battle.defenders_near(f.x, f.y, f.radius):
            battle.hit_unit(u, f.value)
            duration = stats.num(stats.attrs("Lightning Spell")["raw"]["Stun Time"])
            u.stun_until = max(u.stun_until, t + duration)
            _retarget(u)
        return False
    if k == "santa":
        for j in range(5):
            ang = battle.rng.random() * 2 * math.pi
            r = battle.rng.random() * f.radius
            sx, sy = f.x + r * math.cos(ang), f.y + r * math.sin(ang)
            for b in battle.buildings:
                if b.alive and b.edge_distance(sx, sy) <= 1.0:
                    battle.hit_building(b, f.value)
            for u in battle.defenders_near(sx, sy, 1.0):
                battle.hit_unit(u, f.value)
        return False
    if k == "heal":
        for u in battle.attackers_near(f.x, f.y, f.radius):
            if _affected(u):
                rate = f.value * (0.55 if u.is_hero else 1.0)  # heroes heal at 55% (wiki)
                u.heal(rate * dt)
        return True
    if k == "rage":
        pool = (
            battle.attackers_near(f.x, f.y, f.radius)
            if f.team == "atk"
            else battle.defenders_near(f.x, f.y, f.radius)
        )
        for u in pool:
            if not _affected(u):
                continue
            inc = f.value - 1.0
            spd = f.extra["speed"]
            if u.is_hero:
                inc, spd = inc * 0.5, spd * 0.5  # heroes get half (wiki)
            from . import units

            # One-second lingering boost per field (wiki: Rage Spell/Home Village).
            units.add_rage(u, id(f), 1.0 + inc, spd, t + 1.0)
        if f.team == "def" and "defense_damage" in f.extra:
            # Wiki: Super Valkyrie; friendly defenses get +60%, separately.
            for b in battle.buildings:
                if (
                    b.alive
                    and b.weapon is not None
                    and b.edge_distance(f.x, f.y) <= f.radius
                ):
                    b.rage_mult = max(
                        b.rage_mult if t < b.rage_until else 1.0,
                        f.extra["defense_damage"],
                    )
                    b.rage_until = max(b.rage_until, t + 1.0)
        return True
    if k == "def_burn":
        # Wiki: Inferno Artillery, pools neither stack nor gain difficulty damage.
        for u in battle.attackers_near(f.x, f.y, f.radius):
            if not u.alive or u.underground or u.extra.get("burn_tick") == t:
                continue
            damage = max(
                field.value
                for field in battle.fields
                if field.kind == "def_burn"
                and field.started <= t < field.until
                and dist(u.x, u.y, field.x, field.y) <= field.radius
            )
            u.extra["burn_tick"] = t
            battle.hit_unit(u, damage * dt, src="th")
        return True
    if k == "tornado":
        from . import traps

        traps.tornado_tick(battle, f)
        return True
    if k == "def_rage":
        from . import units

        until = min(f.until, t + dt)
        for b in battle.buildings:
            if b.alive and b.weapon is not None and b.edge_distance(f.x, f.y) <= f.radius:
                b.rage_mult, b.rage_until = f.value, until
        for u in battle.defenders_near(f.x, f.y, f.radius):
            # Wiki: Spell Tower, heroes receive half the damage and movement bonus.
            factor = 0.5 if u.is_hero else 1.0
            units.add_rage(
                u, id(f), 1.0 + (f.value - 1.0) * factor, 30.0 / 8.0 * factor, until
            )
        return True
    if k == "haste":
        for u in battle.attackers_near(f.x, f.y, f.radius):
            if _affected(u):
                spd = f.extra["speed"] * (0.5 if u.is_hero else 1.0)
                u.haste_spd = max(u.haste_spd if t < u.haste_until else 0.0, spd)
                u.haste_until = max(u.haste_until, t + 1.0)
        return True
    if k == "jump":
        if t >= f.until:
            return False
        for u in battle.attackers_near(f.x, f.y, f.radius):
            if _affected(u) and not u.flying:
                # Wiki: Jump Spell/Home Village, one-second boost time.
                u.extra["jump_until"] = max(u.extra.get("jump_until", 0.0), t + 1.0)
                u.wall_target = None
        return True

    if k == "freeze":
        for b in battle.buildings:
            if b.alive and b.weapon is not None and b.edge_distance(f.x, f.y) <= f.radius:
                if b.key == "tesla" and not b.revealed:
                    continue  # hidden teslas cannot be frozen (wiki)
                b.frozen_until = max(b.frozen_until, t + f.value)
        for u in battle.defenders_near(f.x, f.y, f.radius):
            u.frozen_until = max(u.frozen_until, t + f.value)
        f.kind, f.until = "tesla_freeze", t + f.value
        return True
    if k == "poison":
        for u in battle.defenders_near(f.x, f.y, f.radius):
            _poison(
                battle,
                u,
                f.value,
                f.extra["slow"],
                f.extra["atk"],
                POISON_HERO_MULT if u.is_hero else 1.0,
                ramp=True,
                source=id(f),
                source_until=f.until,
            )
        return True
    if k == "def_poison":
        for u in battle.attackers_near(f.x, f.y, f.radius):
            if _affected(u) or (
                f.extra.get("origin") == "town_hall" and u.name == "Stone Slammer"
            ):
                _poison(
                    battle,
                    u,
                    f.value,
                    f.extra["slow"],
                    f.extra.get("atk", 0.0),
                    1.0,
                    ramp=f.extra.get("ramp", False),
                    origin=f.extra.get("origin", "tower"),
                    source=id(f),
                    source_until=f.until,
                )
        return True
    if k == "quake":
        pct = f.value
        for b in battle.buildings:
            if (
                b.alive
                and b.counted
                and b.key not in STORAGES
                and not (b.key == "tesla" and not b.revealed)
                and b.edge_distance(f.x, f.y) <= f.radius
            ):
                b.eq_hits += 1
                battle.hit_building(b, b.max_hp * pct / (2 * b.eq_hits - 1))  # 1, 1/3, 1/5 ... (wiki)
        for key, w in battle.walls.items():
            if w.alive and w.edge_distance(f.x, f.y) <= f.radius:
                w.eq_hits += 1
                n = w.eq_hits
                # wiki: nth quake does 1/n plus 5(n-1)^2 % of max HP on walls
                # (L7 29%: three quakes 78%, four quakes 130%).
                battle.hit_building(w, w.max_hp * (pct / n + 0.05 * (n - 1) ** 2))
        if f.extra["troop"]:
            for u in battle.defenders_near(f.x, f.y, f.radius):
                if not u.flying:
                    quake_unit(battle, u, f.extra["troop"])
        return False
    if k == "def_quake":
        for u in battle.attackers_near(f.x, f.y, f.radius):
            if _affected(u) and not u.flying:
                n = u.extra.get("eq_n", 0) + 1
                u.extra["eq_n"] = n
                battle.hit_unit(u, u.max_hp * f.value / (2 * n - 1), src="spell_tower")
        return False
    if k == "clone":
        cap = f.value
        # Wiki: Clone Spell permits repeated copies and cloning existing clones.
        sources = sorted(
            battle.attackers_near(f.x, f.y, f.radius), key=lambda unit: unit.spawned_at
        )
        for source in sources:
            if not _affected(source) or source.is_hero or source.kind == "pet":
                continue
            housing = max(1, source.housing)
            while housing <= cap:
                cap -= housing
                child = battle.spawn(
                    source.name,
                    "atk",
                    source.x + 0.3,
                    source.y + 0.3,
                    level=source.level,
                    kind="summon",
                    group=source.group,
                )
                child.extra["clone"] = True
                child.extra["expire_at"] = t + 30.0  # Wiki: Clone Spell.
                if "start_rage" in child.spec.special:
                    child.extra.get("rage_effects", {}).pop("innate", None)
                battle._clones.append(child)
        f.value = cap
        return cap > 0

    if k == "summon":
        n = int(f.value)
        name = f.extra["unit"]
        spots = _spawn_spots(battle, f.x, f.y, f.radius)
        if not spots:
            return False  # cast on walls: no free tiles, spell wasted (wiki)
        for j in range(n):
            sx, sy = spots[j % len(spots)]
            battle.spawn(name, "atk", sx + 0.1 * (j % 3), sy + 0.1 * (j // 3 % 3), kind="summon", group="spell")
        return False
    if k == "invis":
        until = t + 2 * dt
        for u in battle.attackers_near(f.x, f.y, f.radius):
            if u.kind not in ("siege", "siege_idle"):
                u.invisible_until = max(u.invisible_until, until)
        for u in battle.defenders_near(f.x, f.y, f.radius):
            u.invisible_until = max(u.invisible_until, until)
        if f.team == "atk":
            for b in battle.buildings:
                if b.alive and b.edge_distance(f.x, f.y) <= f.radius:
                    b.invisible_until = max(b.invisible_until, until)
        return True
    if k == "def_invis":
        until = t + 2 * dt
        for b in battle.buildings:
            if b.alive and b.edge_distance(f.x, f.y) <= f.radius:
                b.invisible_until = max(b.invisible_until, until)
        for u in battle.defenders_near(f.x, f.y, f.radius):
            u.invisible_until = max(u.invisible_until, until)
        for u in battle.attackers_near(f.x, f.y, f.radius):
            if u.kind not in ("siege", "siege_idle"):
                u.invisible_until = max(u.invisible_until, until)
        return True
    if k == "recall":
        _recall(battle, f)
        return False
    if k == "overgrowth":
        for b in battle.buildings:
            if (
                b.alive
                and not (b.key == "tesla" and not b.revealed)
                and b.edge_distance(f.x, f.y) <= f.radius
            ):
                b.overgrown_until = max(b.overgrown_until, t + f.value)
        f.kind, f.until = "tesla_overgrowth", t + f.value
        return True
    if k == "iceblock":
        for u in battle.attackers_near(f.x, f.y, f.radius):
            if _affected(u) and u.dash is None:
                u.iceblock_red, u.iceblock_until = f.value, t + f.extra["time"]
                u.frozen_until = max(u.frozen_until, t + f.extra["time"])
        return False
    if k == "totem":
        _totem(battle, f)
        return False
    if k == "angry":
        for u in battle.attackers_near(f.x, f.y, f.radius):
            sp = u.spec
            if not u.alive or sp.attack in ("heal", "heal_chain") or sp.prefer in ("defense", "air_defense") and u.name not in ("Lava Hound", "Ice Hound"):
                continue
            if u.name in ("Ruin Witch", "Totem") or u.kind in ("siege", "siege_idle"):
                continue
            if "angry_until" not in u.extra or u.extra["angry_until"] < t + f.value - 0.5:
                u.extra["angry_until"] = t + f.value
                if u.target_kind != "building" or not getattr(u.target, "is_defense", False):
                    u.target = None
        return True
    if k == "revive_cast":
        best, bd = None, f.radius
        for u in battle.attackers:
            if u.is_hero and not u.alive and u.extra.get("revivable"):
                d = dist(u.x, u.y, f.x, f.y)
                if d <= bd:
                    best, bd = u, d
        if best is not None:
            _revive(battle, best, f.value)
        return False
    if k == "revive_due":
        u = f.extra["hero"]
        if not u.alive and u.extra.get("revivable"):
            _revive(battle, u, f.value)
        return False
    return False


def quake_unit(battle, u, pct):
    # Shared 1, 1/3, 1/5 sequence (wiki: Earthquake Boots; Earthquake Spell).
    n = u.extra.get("eq_n", 0)
    battle.hit_unit(u, u.max_hp * pct / (2 * n + 1))
    u.extra["eq_n"] = n + 1


def _expire(battle, f: Field):
    pass


def wall_jumped(battle, wall):
    return any(
        field.kind == "jump"
        and field.started <= battle.t < field.until
        and dist(wall.x, wall.y, field.x, field.y) <= field.radius
        for field in battle.fields
    )


def _spawn_spots(battle, x, y, r):
    spots = []
    for tx in range(int(x - r), int(x + r) + 1):
        for ty in range(int(y - r), int(y + r) + 1):
            cx, cy = tx + 0.5, ty + 0.5
            if dist(cx, cy, x, y) > r:
                continue
            w = battle.walls.get((tx, ty))
            if w is not None and w.alive:
                continue
            i, j = battle.grid.cell(cx, cy)
            if battle.grid.blocked[i, j]:
                continue
            spots.append((cx, cy))
    return spots


# ----------------------------------------------------------------- poison
def poison_factors(unit, damage, movement, attack):
    # Wiki: Town Hall/Guardians, rooftop immunity and 30% poison effects.
    if unit.kind == "guardian":
        if unit.extra.get("waiting"):
            return 0.0, 0.0, 0.0
        return damage * 0.3, movement * 0.3, attack * 0.3
    return damage, movement, attack


def _poison(
    battle,
    u,
    max_dps,
    slow,
    atk,
    mult,
    *,
    ramp,
    origin="spell",
    source=None,
    source_until=None,
):
    t = battle.t
    if u.kind == "guardian" and u.extra.get("waiting"):
        return
    damage, slow, atk = poison_factors(u, max_dps * mult, slow, atk)
    key = (u.id, origin, source)
    st = battle._poison.get(key)
    if st is None:
        st = battle._poison[key] = {"u": u, "since": t, "dps": 0.0, "origin": origin}
    st["dps"] = damage
    st["ramp"] = ramp
    linger = POISON_LINGER if u.team == "def" else 0.0
    st["until"] = t + (POISON_LINGER if u.team == "def" else 0.2)
    if source_until is not None:
        st["until"] = min(st["until"], source_until + linger)
    st["slow"], st["atk"] = slow, atk


def _poison_states(battle):
    t = battle.t
    dead = []
    active = {}
    for key, state in battle._poison.items():
        unit = state["u"]
        if not unit.alive or t >= state["until"]:
            dead.append(key)
            continue
        origin = state.get("origin", "spell")
        if unit.underground and origin != "town_hall":
            continue
        fraction = (
            min(1.0, (t - state["since"] + battle.DT) / POISON_RAMP)
            if state["ramp"]
            else 1.0
        )
        damage = state["dps"] * fraction
        previous = active.get(unit.id)
        if previous is None:
            active[unit.id] = [unit, damage, origin, state["slow"], state["atk"]]
        else:
            if damage > previous[1]:
                previous[1:3] = damage, origin
            previous[3] = max(previous[3], state["slow"])
            previous[4] = max(previous[4], state["atk"])
    for unit, damage, origin, movement, attack in active.values():
        battle._src = "spell" if unit.team == "def" else "poison"
        kind = "th_poison" if origin == "town_hall" else "poison"
        battle.hit_unit(unit, damage * battle.DT, src=battle._src, kind=kind)
        effects.add_slow(
            unit, "poison", 1.0 - movement, 1.0 - attack, t + 2 * battle.DT
        )
    for key in dead:
        battle._poison.pop(key, None)


def add_defensive_poison(battle, x, y, cfg, *, origin="tower"):
    """Giga Inferno death poison / Poison Spell Tower cloud."""
    if origin == "town_hall" and battle.town_hall == 16:
        # Wiki: Town Hall/Giga Inferno gives 50% attack slowdown on death Poison.
        cfg = {**cfg, "atk": 0.5}
    f = Field(
        "def_poison",
        x,
        y,
        cfg.get("radius", 5.0),
        battle.t + cfg.get("time", 12.0),
        team="def",
        value=cfg["dps"],
        extra={
            "slow": cfg.get("slow", 0.35),
            "atk": cfg.get("atk", 0.0),
            "ramp": cfg.get("ramp", False),
            "origin": origin,
        },
        started=battle.t,
    )
    battle.fields.append(f)


# ------------------------------------------------------------ spell tower
def tower_cast(battle, b: Building, mode, near=None):
    """Spell Tower modes: rage on itself (+60% for 18 s, r5), poison at the
    target (60 dps max, -35% speed, -25% attack rate, 12 s, r5), invisibility
    on itself (4.5 s, r4.5), earthquake at the target (30% troop HP, r4.7,
    ground only, TH17+) - wiki infoboxes."""
    t = battle.t
    if battle.record:
        battle.log.append((round(t, 1), "spell_tower", mode))
    tgt = None
    if near:
        if mode in ("eq", "quake", "earthquake"):
            near = [unit for unit in near if not unit.flying]
        tgt = min(near, key=lambda a: dist(a.x, a.y, b.x, b.y), default=None)
    x, y = (tgt.x, tgt.y) if tgt is not None else (b.x, b.y)
    if mode == "rage":
        battle.fields.append(Field("def_rage", b.x, b.y, 5.0, t + 18.0, team="def", value=1.6, started=t))
    elif mode == "poison":
        add_defensive_poison(
            battle,
            x,
            y,
            {
                "dps": 60.0,
                "time": 12.0,
                "slow": 0.35,
                "atk": 0.25,
                "radius": 5.0,
                "ramp": True,
            },
        )
    elif mode == "invis":
        battle.fields.append(Field("def_invis", b.x, b.y, 4.5, t + 4.5, team="def", started=t))
    elif mode in ("eq", "quake", "earthquake"):
        battle.fields.append(
            Field(
                "def_quake", x, y, 4.7, t + 0.3, team="def", value=0.30, started=t + 0.3
            )
        )


def escape_poison(battle, unit):
    # Wiki: Poison Spell; idle defenders flee, except Heroes and Healers.
    # Human Druid behavior is unresolved; Bears follow the ordinary rule.
    if unit.is_hero or unit.name in ("Healer", "Druid") or unit.speed <= 0:
        return False
    clouds = [
        field
        for field in battle.fields
        if field.kind == "poison" and field.started <= battle.t < field.until
    ]
    if not any(
        dist(unit.x, unit.y, field.x, field.y) <= field.radius for field in clouds
    ):
        unit.extra.pop("poison_exit", None)
        return False
    from ..pathing import RES

    grid = battle.navigation_grid(unit)
    key = (grid.version, tuple(id(field) for field in clouds))
    saved = unit.extra.get("poison_exit")
    if saved is None or saved[0] != key:
        costs = None if unit.flying else grid.source_field(unit.x, unit.y, 0.0)
        candidates = []
        for i in range(grid.n):
            for j in range(grid.n):
                if costs is not None and (grid.blocked[i, j] or costs[i, j] >= 1e9):
                    continue
                x, y = (i + 0.5) / RES, (j + 0.5) / RES
                if all(dist(x, y, field.x, field.y) > field.radius for field in clouds):
                    cost = dist(unit.x, unit.y, x, y) if costs is None else costs[i, j]
                    candidates.append((cost, x, y))
        if not candidates:
            return False
        _, x, y = min(candidates)
        saved = unit.extra["poison_exit"] = (key, (x, y))
    battle.move_towards(unit, unit, position=saved[1])
    return True


# ------------------------------------------------------------------- misc
def _retarget(target):
    from . import units

    if isinstance(target, Building):
        weapon = target.weapon
        if weapon is not None:
            weapon.target = None
            weapon.multi = []
            weapon.lock_time = 0.0
            weapon.burst_left = 0
    else:
        target.target = target.wall_target = None
        units.interrupt_attack(target)


def _recall(battle, f):
    """Heroes first, then highest housing, then earliest deployed; heroes and
    pets count 25 and 20 housing (wiki)."""
    from . import heroes

    cap = f.value
    cands = [
        u
        for u in battle.attackers_near(f.x, f.y, f.radius)
        if u.alive
        and (
            u.kind in ("troop", "hero", "hero_clone", "pet")
            or u.kind == "summon"
            and (
                u.name in SUBTROOP_HOUSING
                or u.name == "Skeleton"
                and u.owner is not None
                and u.owner.name == "Witch Golem"
            )
        )
    ]
    cands.sort(key=lambda u: (not u.is_hero, -(25 if u.is_hero else 20 if u.kind == "pet" else u.housing), u.spawned_at))
    taken = []
    for u in cands:
        h = 25 if u.is_hero else 20 if u.kind == "pet" else u.housing
        if heroes._free_pet(u, battle.t) or u in taken:
            continue
        if h > cap:
            continue
        cap -= h
        taken.append(u)
        if (
            u.is_hero
            and u.pet is not None
            and u.pet.alive
            and (u.pet.extra.get("egg") or u.pet.attached(battle.t))
            and u.pet not in taken
        ):
            taken.append(u.pet)
    # recalled units keep their health and go back on the bar; the plan
    # redeploys them (same path as the Portal Pendant, without its bonuses)
    heroes.stash(battle, taken, (0.0, 0.0, 0.0))


def _totem(battle, f):
    from .specs import UnitSpec

    battle._uid += 1
    sp = UnitSpec("Totem", prefer="none", walls="fly")
    u = Unit(battle._uid, "Totem", "summon", "atk", f.x, f.y, hp=f.value, dmg=0.0, interval=1.0, range_=0.0, speed=0.0,
             housing=0, flying=False, hits_air=False, hits_ground=False, spec=sp, level=1)
    u.decay = stats.num(stats.attrs("Totem Spell").get("raw", {}).get("Hitpoint Decay per Second"), 334.0)
    u.spawned_at = u.active_at = battle.t
    battle.attackers.append(u)
    # Wiki: Totem Spell, only defenders in the landing area retarget.
    # Stun duration is not stated; do not borrow another spell's duration.
    for b in battle.buildings:
        if b.alive and b.weapon is not None and b.edge_distance(f.x, f.y) <= f.radius:
            _retarget(b)
    for d in battle.defenders_near(f.x, f.y, f.radius):
        _retarget(d)


def maybe_revive(battle, u):
    """Called when an attacking hero is knocked out. Marks it revivable and,
    if the plan carries Revive Spells, schedules one (the plan's delay)."""
    if not u.is_hero or u.team != "atk" or u.extra.get("mirror_clone"):
        return
    u.extra["revivable"] = True
    plan = battle.plan
    left = getattr(plan, "revives_left", 0)
    if left <= 0:
        return
    plan.revives_left = left - 1
    lv = _lvl(battle, "Revive Spell", None)
    pct = stats.get("Revive Spell", lv, "Hero Heal %", default=70.0) / 100.0
    delay = getattr(plan, "revive_delay", 1.5)
    battle.fields.append(Field("revive_due", u.x, u.y, 0.0, battle.t + delay, value=pct, extra={"hero": u}, started=battle.t + delay))


def _revive(battle, u, pct):
    u.alive = True
    u.extra["revivable"] = False
    u.hp = u.max_hp * pct
    u.target = None
    u.wall_target = None
    u.cooldown = 0.0
    u.frozen_until = u.stun_until = 0.0
    if battle.record:
        battle.log.append((round(battle.t, 1), "revive", u.name))


def _clone_expiry(battle):
    if not battle._clones:
        return
    t = battle.t
    keep = []
    for c in battle._clones:
        if "recalled" in c.extra:
            keep.append(c)
        elif c.alive and t >= c.extra["expire_at"]:
            c.alive = False  # clones vanish without death effects (assumed)
        elif c.alive or c in battle.portal_stash:
            keep.append(c)
    battle._clones = keep
