"""Spells: every attacking spell, Spell Tower casts and defensive poison.

Numbers come from the registry row of the spell at its level; mechanics from
the wiki pages mirrored 2026-10-15. Values the wiki does not state are marked
'assumed'.
"""

from __future__ import annotations

import math

from ..mechanics import WORLD
from . import defense, effects, stats
from .entities import Building, Field, Unit, Wall, dist

LAND_DELAY = 0.5  # time for a spell bottle to land (assumed)
STORAGES = {"gs", "es", "ds"}
# Units that never trigger traps, Clan Castle troops or Spell Towers (wiki:
# Skeleton Spell, Bat Spell, Totem Spell pages).
NO_TRIGGER = {"Spell Skeleton", "Skeleton", "Bat", "Totem"}
POISON_LINGER = 6.0  # wiki: effect lasts 6 s after leaving the radius
POISON_RAMP = 4.0  # seconds to reach max damage per second (assumed)
# game data v18.200.9: Poison.HeroDamageMultiplier=5 -> 0.05x damage.
POISON_HERO_MULT = 0.05


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


def validate(plan, name, level, *, donated=False):
    if type(level) is not int or level <= 0:
        raise ValueError(f"Invalid {name} level {level}")
    stats.row(name, level)
    event = plan.event_ruleset
    if name in (
        "Santa's Surprise",
        "Bag of Frostmites",
        "Birthday Boom",
        "Yellow Card",
    ):
        if not event.get("version") or name not in event.get("spells", ()):
            raise ValueError(f"{name} requires an explicit event version")
        if donated and name in ("Santa's Surprise", "Birthday Boom"):
            raise ValueError(f"{name} cannot be donated")
        # Wiki: Bag of Frostmites and Yellow Card event unlocks.
        if name == "Bag of Frostmites" and event.get("sweet_elixir", 0) < 5500:
            raise ValueError("Bag of Frostmites requires 5,500 Sweet Elixir")
        if name == "Yellow Card" and event.get("event_currency", 0) < 3000:
            raise ValueError("Yellow Card requires 3,000 event currency")
        if name == "Birthday Boom" and event.get("birthday_damage") != "table":
            raise ValueError("Select Birthday Boom's table interpretation explicitly")
    if donated:
        castle = plan._building_level("Clan Castle", plan.clan_castle_level)
        lab = (
            stats.get("Clan Castle", castle, "~laboratory level cap", default=0)
            if castle
            else 0
        )
        if not lab:
            raise ValueError("Donated spells require a Clan Castle")
        town_hall = stats.required_town_hall("Laboratory", int(lab))
    else:
        town_hall = plan.town_hall
        lab = plan._building_level("Laboratory", plan.laboratory_level)
        raw = stats.attrs(name).get("raw", {})
        for factory, supplied in (
            ("Spell Factory", plan.spell_factory_level),
            ("Dark Spell Factory", plan.dark_spell_factory_level),
        ):
            required = stats.num(raw.get(factory + " Level Required"))
            if (
                required is not None
                and plan._building_level(factory, supplied) < required
            ):
                raise ValueError(f"{name} requires {factory} level {required:g}")
    stats.validate_level(name, level, town_hall)
    if stats.get(name, level, "Laboratory Level Required", default=0) > lab:
        raise ValueError(f"{name} level {level} exceeds Laboratory level {lab}")


# ------------------------------------------------------------------- cast
def cast(battle, name, x, y, level=None, *, origin=None):
    """Spend one spell instance and drop it at (x, y)."""
    return battle.plan.cast_spell(battle, name, x, y, level=level, origin=origin)


def cast_effect(battle, name, x, y, level=None):
    """Apply an unpaid spell effect for declared synthetic scenarios."""
    lv = _lvl(battle, name, level)
    battle.start_battle()
    if battle.first_deploy_t is None:
        battle.first_deploy_t = battle.t
    # Wiki: Revive Spell has no falling bottle animation.
    t = battle.t if name == "Revive Spell" else battle.t + LAND_DELAY
    if battle.record:
        battle.log.append((round(battle.t, 1), "spell", name, round(x, 1), round(y, 1)))
    f = None
    if name == "Lightning Spell":
        f = Field("lightning", x, y, _radius(name, lv, 2.0), t, value=stats.get(name, lv, "damage", "Damage", default=640.0))
    elif name == "Healing Spell":
        per = stats.get(name, lv, "Healing per Pulse", default=60.0)
        # Wiki: Healing Spell/Home Village, 41 pulses including both endpoints.
        f = Field(
            "heal", x, y, 5.0, t + 12.0, value=per, extra={"pulses": 41, "gap": 0.3}
        )
    elif name == "Rage Spell":
        inc = stats.get(name, lv, "Damage Increase", default=180.0) / 100.0
        spd = stats.get(name, lv, "Speed Increase", default=30.0) / 8.0
        f = Field(
            "rage",
            x,
            y,
            5.0,
            t + 18.0,
            value=1.0 + inc,
            extra={"speed": spd, "pulses": 60, "gap": 0.3},
        )  # Wiki: Rage Spell/Home Village.
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
        f = Field(
            "clone",
            x,
            y,
            3.5,
            t + 18.0,
            value=stats.get(name, lv, "Cloned Capacity", default=42.0),
        )
    # Wiki: Skeleton Spell and Bat Spell give 3.5; ClashKing gives 2.2.
    elif name == "Skeleton Spell":
        f = Field(
            "summon",
            x,
            y,
            3.5,
            t,
            value=stats.get(name, lv, "Skeletons generated", default=19.0),
            extra={"unit": "Spell Skeleton"},
        )
    elif name == "Bat Spell":
        f = Field(
            "summon",
            x,
            y,
            3.5,
            t,
            value=stats.get(name, lv, "Bats generated", default=22.0),
            extra={"unit": "Bat"},
        )
    elif name == "Bag of Frostmites":
        f = Field(
            "summon",
            x,
            y,
            1.75,
            t,
            value=stats.get(name, lv, "Frostmites spawned", default=17.0),
            extra={"unit": "Frostmite", "freeze": stats.get(name, lv, "Freeze Time")},
        )
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
        # Wiki: Santa's Surprise, five strikes at 0.1-second intervals.
        f = Field(
            "santa",
            x,
            y,
            # game data v18.200.9: Santas Surprise.RandomRadius=100 -> 1 tile.
            1.0,
            t + 0.4,
            value=stats.get(name, lv, "Damage per Strike", default=370.0),
            extra={"pulses": 5, "gap": 0.1},
        )
    elif name == "Birthday Boom":
        # Wiki: Birthday Boom, table interpretation; the scaling formula conflicts.
        f = Field(
            "birthday",
            x,
            y,
            2.5,
            t,
            value=stats.get(name, lv, "Damage"),
            extra={
                "town_hall": stats.get(name, lv, "Damage vs Town Hall"),
                "freeze": stats.get(name, lv, "Freeze Duration"),
            },
        )
    elif name == "Yellow Card":
        f = Field(
            "yellow", x, y, 7.0, t, value=stats.get(name, lv, "Duration")
        )  # Wiki: Yellow Card.
    else:
        raise KeyError(f"unknown spell {name}")
    f.started = t
    f.extra["name"] = name
    battle.fields.append(f)
    return f


# ------------------------------------------------------------------- tick
def tick(battle):
    t = battle.t
    keep = []
    fields = tuple(battle.fields)
    for f in fields:
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
    battle.fields = keep + battle.fields[len(fields) :]
    _poison_states(battle)
    _clone_expiry(battle)


def _apply(battle, f: Field) -> bool:
    """Apply one tick of a field. Returns False when the field is spent."""
    t = battle.t
    dt = battle.DT
    k = f.kind
    if (
        k
        in (
            "poison",
            "def_poison",
            "def_rage",
            "def_burn",
            "rage",
            "haste",
            "invis",
            "def_invis",
            "angry",
        )
        and t >= f.until
    ):
        return False
    if k in ("lightning", "freeze", "poison", "def_rage") or (
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
    if k == "birthday":
        for building in battle.buildings:
            if (
                building.alive
                and not (building.key == "tesla" and not building.revealed)
                and building.edge_distance(f.x, f.y) <= f.radius
            ):
                damage = f.extra["town_hall"] if building.key == "th" else f.value
                battle.hit_building(building, damage)
                building.frozen_until = max(
                    building.frozen_until, t + f.extra["freeze"]
                )
                _retarget(building)
        for wall in battle.walls.values():
            if wall.alive and wall.edge_distance(f.x, f.y) <= f.radius:
                battle.hit_building(wall, f.value)
        for unit in battle.defenders_near(f.x, f.y, f.radius):
            battle.hit_unit(unit, f.value)
            unit.frozen_until = max(unit.frozen_until, t + f.extra["freeze"])
            _retarget(unit)
        return False
    if k == "yellow":
        targets = [
            building
            for building in battle.buildings
            if building.alive
            and building.weapon is not None
            and building.weapon.kind != "bh_repair_only"
            and not building.extra.get("unavailable")
            and (building.key != "tesla" or building.revealed)
            and (building.is_defense or building.key == "th")
            and building.edge_distance(f.x, f.y) <= f.radius
        ]
        targets.extend(
            unit for unit in battle.defenders_near(f.x, f.y, f.radius) if unit.is_hero
        )
        if targets:
            target = min(
                targets,
                key=lambda target: (
                    target.edge_distance(f.x, f.y)
                    if isinstance(target, Building)
                    else dist(target.x, target.y, f.x, f.y)
                ),
            )
            # Overlap timing is unstated; retain the current suspension deadline.
            if t >= target.extra.get("yellow_until", 0.0):
                target.extra["yellow_until"] = t + f.value
                _retarget(target)
        return False
    if k == "santa":
        for at in _pulses(f, t):
            # The radial distribution and wall interaction are unstated.
            # Keep the existing radial sampling and listed building/unit victims.
            ang = battle.rng.random() * 2 * math.pi
            r = battle.rng.random() * f.radius
            sx, sy = f.x + r * math.cos(ang), f.y + r * math.sin(ang)
            # game data v18.200.9: Santas Surprise.Radius=150 -> 1.5 tiles.
            for building in battle.buildings:
                if building.alive and building.edge_distance(sx, sy) <= 1.5:
                    battle.hit_building(building, f.value)
            for unit in battle.defenders_near(sx, sy, 1.5):
                battle.hit_unit(unit, f.value)
        return f.extra.get("delivered", 0) < f.extra["pulses"]
    if k == "heal":
        for at in _pulses(f, t):
            for unit in battle.attackers_near(f.x, f.y, f.radius):
                if unit.alive and unit.kind not in ("siege", "siege_idle"):
                    # Wiki: Healing Spell/Home Village, heroes receive 55%.
                    unit.heal(f.value * (0.55 if unit.is_hero else 1.0))
        return f.extra.get("delivered", 0) < f.extra["pulses"]
    if k == "rage":
        pulses = _pulses(f, t) if "pulses" in f.extra else [t]
        if not pulses:
            return t < f.until
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
            units.add_rage(
                u,
                _source(battle, f),
                1.0 + inc,
                spd,
                pulses[-1] + f.extra.get("boost_time", 1.0),
            )
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
                    b.rage_until = max(
                        b.rage_until,
                        pulses[-1] + f.extra.get("boost_time", 1.0),
                    )
        return True
    if k == "def_burn":
        # Application pulses remain separate from the existing damage approximation.
        if "pulses" not in f.extra or _pulses(f, t):
            f.extra["victims"] = {
                unit.id for unit in battle.attackers_near(f.x, f.y, f.radius)
            }
        # Wiki: Inferno Artillery, pools neither stack nor gain difficulty damage.
        for u in battle.attackers_near(f.x, f.y, f.radius):
            if (
                not u.alive
                or u.underground
                or u.extra.get("burn_tick") == t
                or u.id not in f.extra.get("victims", ())
            ):
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
                u,
                _source(battle, f),
                1.0 + (f.value - 1.0) * factor,
                30.0 / 8.0 * factor,
                until,
            )
        return True
    if k == "haste":
        # game data v18.200.9: Haste.TimeBetweenHitsMS=250 -> 0.25 s.
        pulse = _application(f, t, 0.25)
        if pulse is None:
            return True
        for u in battle.attackers_near(f.x, f.y, f.radius):
            if _affected(u):
                spd = f.extra["speed"] * (0.5 if u.is_hero else 1.0)
                # game data v18.200.9: Haste.BoostTimeMS=1000 -> 1 s.
                u.extra.setdefault("haste_effects", {})[_source(battle, f)] = (
                    spd,
                    pulse + 1.0,
                )
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
                source=_source(battle, f),
                source_until=f.until,
            )
        return True
    if k == "def_poison":
        gap = f.extra.get("gap", dt)
        if _application(f, t, gap) is None:
            return True
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
                    source=_source(battle, f),
                    source_until=f.until,
                    refresh=f.extra.get("gap", 0.2),
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
        # game data v18.200.9: Clone.TimeBetweenHitsMS=300 -> 0.3 s.
        if _application(f, t, 0.3) is None:
            return True
        cap = f.value
        # Wiki: Clone Spell permits repeated copies and cloning existing clones.
        sources = sorted(
            battle.attackers_near(f.x, f.y, f.radius), key=lambda unit: unit.spawned_at
        )
        for source in sources:
            if (
                not _affected(source)
                or source.is_hero
                or source.kind == "pet"
                or _source(battle, f) in source.extra.get("clone_casts", ())
            ):
                continue
            housing = interaction_housing(source)
            while housing <= cap:
                cap -= housing
                # The random distribution is unstated; choose a free tile in the circle.
                spots = _spawn_spots(battle, f.x, f.y, f.radius, flying=source.flying)
                if not spots:
                    return False
                x, y = battle.rng.choice(spots)
                child = battle.spawn(
                    source.name,
                    "atk",
                    x,
                    y,
                    level=source.level,
                    kind="summon",
                    group=source.group,
                )
                child.extra["clone_casts"] = source.extra.get("clone_casts", set()) | {
                    _source(battle, f)
                }
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
        if "freeze" in f.extra:
            freeze = Field(
                "freeze", f.x, f.y, f.radius, t, value=f.extra["freeze"], started=t
            )
            _apply(battle, freeze)
            battle.fields.append(freeze)
        spots = _spawn_spots(battle, f.x, f.y, f.radius, flying=name == "Bat")
        if not spots:
            return False  # cast on walls: no free tiles, spell wasted (wiki)
        for j in range(n):
            sx, sy = spots[j % len(spots)]
            child = battle.spawn(name, "atk", sx, sy, kind="summon", group="spell")
            if f.extra.get("name") == "Bag of Frostmites":
                from dataclasses import replace

                child.extra["bouncing_frostmite"] = True
                # game data v18.200.9: BouncingFrostmite.DamageRadius=80 -> 0.8 tiles.
                child.spec = replace(child.spec, splash=0.8)
        return False
    if k == "invis":
        until = _invisibility_until(f, t)
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
        until = _invisibility_until(f, t)
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
            if _affected(u) and not u.underground:
                until = t + f.extra["time"]
                u.extra.setdefault("iceblocks", {})[_source(battle, f)] = (
                    f.value,
                    until,
                )
                u.frozen_until = max(u.frozen_until, until)
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


def _source(battle, field):
    source = field.extra.get("source")
    if source is None:
        battle._field_serial = getattr(battle, "_field_serial", 0) + 1
        source = ("field", battle._field_serial)
        field.extra["source"] = source
    return source


def _application(field, t, gap):
    at = field.extra.get("next_apply", field.started)
    if at > t and not math.isclose(at, t):
        return None
    while at + gap < t or math.isclose(at + gap, t):
        at += gap
    field.extra["next_apply"] = at + gap
    return at


def _pulses(field, t):
    delivered = field.extra.get("delivered", 0)
    due = []
    while delivered < field.extra["pulses"]:
        at = field.started + delivered * field.extra["gap"]
        if at > t and not math.isclose(at, t):
            break
        due.append(at)
        delivered += 1
    field.extra["delivered"] = delivered
    return due


def _invisibility_until(field, t):
    # Wiki: Invisibility Spell, immediate coverage with successive 0.25-second effects.
    return min(field.until, t + 0.25)


def _expire(battle, f: Field):
    pass


def wall_jumped(battle, wall):
    return any(
        field.kind == "jump"
        and field.started <= battle.t < field.until
        and dist(wall.x, wall.y, field.x, field.y) <= field.radius
        for field in battle.fields
    )


def _spawn_spots(battle, x, y, r, *, flying=False):
    spots = []
    for tx in range(int(x - r), int(x + r) + 1):
        for ty in range(int(y - r), int(y + r) + 1):
            cx, cy = tx + 0.5, ty + 0.5
            if dist(cx, cy, x, y) > r:
                continue
            if not (0 <= cx < WORLD and 0 <= cy < WORLD):
                continue
            if flying:
                spots.append((cx, cy))
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
    refresh=0.2,
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
    st["until"] = t + (POISON_LINGER if u.team == "def" else refresh)
    if source_until is not None:
        st["until"] = min(st["until"], source_until + linger)
    st["slow"], st["atk"] = slow, atk


def _poison_states(battle):
    t = battle.t
    dead = []
    active = {}
    for key, state in battle._poison.items():
        unit = state["u"]
        if t >= state["until"] or not unit.alive and "recalled" not in unit.extra:
            dead.append(key)
            continue
        if "recalled" in unit.extra:
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
    if origin == "tower":
        # game data v18.200.9: Spell Tower Poison.TimeBetweenHitsMS=400 -> 0.4 s.
        f.extra["gap"] = 0.4
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
def interaction_housing(unit):
    # Wiki: Clone Spell and Recall Spell, effective housing differs from training.
    if unit.is_hero:
        return 25
    if unit.kind == "pet":
        return 20
    weights = {
        "Skeleton": 1,
        "Spell Skeleton": 1,
        "Bat": 1,
        "Frostmite": 1,
        "Lava Pup": 2,
        "Ice Pup": 2,
        "Yetimite": 2,
        "Golemite": 6,
        "Big Boy": 10,
    }
    return weights.get(unit.name, max(1, unit.housing))


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
    cands = list(
        {
            unit.id: unit
            for unit in battle.attackers_near(f.x, f.y, f.radius)
            if _affected(unit)
            and unit.kind in ("troop", "hero", "hero_clone", "pet", "summon")
        }.values()
    )
    cands.sort(key=lambda u: (not u.is_hero, -interaction_housing(u), u.spawned_at))
    taken = []
    for u in cands:
        h = interaction_housing(u)
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

    # Wiki: Totem Spell, search an unoccupied tile in a 7x7 circle.
    spots = _spawn_spots(battle, f.x, f.y, 7.0 / 2.0)
    if not spots:
        return
    x, y = min(spots, key=lambda point: dist(*point, f.x, f.y))
    defense.builder_spell(battle, f)
    battle._uid += 1
    sp = UnitSpec("Totem", prefer="none", walls="fly")
    u = Unit(
        battle._uid,
        "Totem",
        "summon",
        "atk",
        x,
        y,
        hp=f.value,
        dmg=0.0,
        interval=1.0,
        range_=0.0,
        speed=0.0,
        housing=20,
        flying=False,
        hits_air=False,
        hits_ground=False,
        spec=sp,
        level=1,
    )
    u.decay = stats.num(stats.attrs("Totem Spell").get("raw", {}).get("Hitpoint Decay per Second"), 334.0)
    u.spawned_at = u.active_at = battle.t
    battle.attackers.append(u)
    # Wiki: Totem Spell, only defenders in the landing area retarget.
    # game data v18.200.9: Totem.StunTimeMS=200 -> 0.2 s.
    until = battle.t + 0.2
    for b in battle.buildings:
        if b.alive and b.weapon is not None and b.edge_distance(f.x, f.y) <= f.radius:
            b.stun_until = max(b.stun_until, until)
            _retarget(b)
    for d in battle.defenders_near(f.x, f.y, f.radius):
        d.stun_until = max(d.stun_until, until)
        _retarget(d)


def maybe_revive(battle, u):
    """Mark an actual KO; the attacker policy decides whether to spend a spell."""
    if not u.is_hero or u.team != "atk" or u.extra.get("mirror_clone"):
        return
    u.extra["revivable"] = True
    u.extra["ko_at"] = battle.t
    # Wiki: Revive Spell, pets never recouple after their Hero is defeated.
    if u.pet is not None:
        u.pet.extra["rampage_detached"] = True
        u.pet.owner = None
        u.pet = None
    if u.kit is not None:
        u.kit.pet_unit = None


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
