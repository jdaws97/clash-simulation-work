"""Heroes: equipment (all 42 pieces), pets, auras, abilities, defenders.

Every number is read from the registry row of the equipment/pet at its level
(wiki tables mirrored 2026-10-15). Defending heroes use no equipment (wiki:
"The Archer Queen does not use any Hero Equipment when defending").
"""

from __future__ import annotations

import math

from ..loadouts import HeroLoadout
from . import effects, spells, stats, units
from .entities import Building, Unit, Wall, dist

HEROES = {"Barbarian King", "Archer Queen", "Grand Warden", "Royal Champion", "Minion Prince", "Dragon Duke"}

DEFAULT_LOADOUTS = {
    "Archer Queen": HeroLoadout("Archer Queen", ("Giant Arrow", "Action Figure"), "Unicorn"),
    "Barbarian King": HeroLoadout("Barbarian King", ("Spiky Ball", "Earthquake Boots"), "Spirit Fox"),
    "Grand Warden": HeroLoadout("Grand Warden", ("Eternal Tome", "Rage Gem"), "Electro Owl"),
    "Royal Champion": HeroLoadout("Royal Champion", ("Rocket Spear", "Electro Boots"), "L.A.S.S.I"),
    "Minion Prince": HeroLoadout("Minion Prince", ("Dark Orb", "Meteor Staff"), "Angry Jelly"),
    "Dragon Duke": HeroLoadout("Dragon Duke", ("Rocket Backpack", "Fire Heart"), "Phoenix"),
}


def _col(name, level, *frags, default=0.0):
    keys = ["~" + f for f in frags]
    return stats.get(name, level, *keys, default=default)


class Kit:
    __slots__ = ("hero", "equip", "levels", "pet_name", "pet_level", "pet_unit", "regen", "hp_recovery", "phoenix", "doomed_at",
                 "spear_shots", "spear_bonus", "boots_until", "boots_dps", "reduction_until", "reduction", "heal_until", "heal_rate",
                 "next_meteor", "fox_next", "diggy_next", "crown_stage", "vamp", "frozen_arrow", "mono_arrow")

    def __init__(self):
        self.equip = []
        self.levels = {}
        self.pet_name = None
        self.pet_level = None
        self.pet_unit = None
        self.regen = 0.0
        self.hp_recovery = 0.0
        self.phoenix = False
        self.doomed_at = None
        self.spear_shots = 0
        self.spear_bonus = 0.0
        self.boots_until = 0.0
        self.boots_dps = 0.0
        self.reduction_until = 0.0
        self.reduction = 0.0
        self.heal_until = 0.0
        self.heal_rate = 0.0
        self.next_meteor = 0.0
        self.fox_next = 0.0
        self.diggy_next = 0.0
        self.crown_stage = 0
        self.vamp = 0.0
        self.frozen_arrow = None
        self.mono_arrow = None

    def has(self, name):
        return name in self.equip

    def lv(self, name):
        return self.levels[name]


def _pet_level(battle, hero, loadout, plan, town_hall):
    name = loadout.pet
    if not name:
        return None
    if name not in stats.registry() or stats.record(name)["kind"] != "pet":
        raise ValueError(f"{name} is not a pet")
    # Pet House unlocks and level caps come from the individual pet pages.
    maximum = stats.max_level(name, town_hall)
    if maximum is None:
        raise ValueError(f"{name} is unavailable at Town Hall {town_hall}")
    level = (getattr(plan, "pet_levels", {}) or {}).get(name, maximum)
    if level is None:
        level = maximum
    if (
        not isinstance(level, int)
        or isinstance(level, bool)
        or not 1 <= level <= maximum
    ):
        raise ValueError(f"Illegal {name} level {level} at Town Hall {town_hall}")
    stats.row(name, level)
    for unit in battle.attackers + battle.portal_stash:
        if unit is hero:
            continue
        if unit.kit is not None and unit.kit.pet_name == name:
            raise ValueError(f"{name} is already assigned to {unit.name}")
        if unit.kind == "pet" and unit.name == name and unit.owner is not hero:
            raise ValueError(f"{name} is already assigned to another Hero")
    if hero.pet is not None:
        raise ValueError(f"{hero.name} already has a pet")
    return level


def equip(battle, u: Unit, plan):
    loadouts = getattr(plan, "loadouts", None) or {}
    lo = loadouts.get(u.name) or DEFAULT_LOADOUTS.get(u.name)
    if lo is None:
        return
    th = getattr(plan, "town_hall", battle.town_hall)
    pet_level = _pet_level(battle, u, lo, plan, th)
    levels_override = getattr(plan, "equipment_levels", {}) or {}
    k = Kit()
    k.hero = u.name
    base_interval = u.interval
    passive_dps = passive_speed = 0.0
    for e in lo.equipment:
        if e not in stats.registry():
            continue
        lvl = levels_override.get(e) or stats.max_level(e, th)
        k.equip.append(e)
        k.levels[e] = lvl
        hp = _col(e, lvl, "hitpoint increase", "hp increase")
        dps = _col(e, lvl, "damage per second increase", "dps increase")
        aspd = _col(e, lvl, "hero boosts / attack speed increase", "hero boost / attack speed increase")
        u.max_hp += hp
        u.base_max_hp += hp
        u.hp += hp
        passive_dps += dps
        passive_speed += aspd / 100.0
        k.regen += _col(e, lvl, "self healing per second")
        k.hp_recovery += _col(e, lvl, "hp recovery increase", "health recovery increase")
        if e in ("Royal Gem", "Stun Blaster"):
            k.hp_recovery += _col(e, lvl, "health recovery")
        if e == "Vampstache":
            k.vamp = _col(e, lvl, "heal per hit")
        if e == "Frozen Arrow":
            k.frozen_arrow = (_col(e, lvl, "slow down") / 100.0, _col(e, lvl, "slow down duration"))
        if e == "Stick Horse":
            # Duration and speed tiers (wiki: Stick Horse).
            u.extra["horse_until"] = battle.t + _col(e, lvl, "ability duration")
            u.extra["horse_speed"] = _col(e, lvl, "movement speed increase") / 8.0
            u.extra["horse_attack"] = (
                _col(e, lvl, "ability attributes / attack speed increase") / 100.0
            )
            u.extra["horse_interval"] = base_interval
            # Gap-versus-jump routing constants: NUMBER NOT STATED.
        if e == "Monolith Arrow":
            # All three housing tiers (wiki: Monolith Arrow).
            k.mono_arrow = tuple(
                _col(e, lvl, column) / 100.0
                for column in (
                    "highest extra damage",
                    "extra damage (181-250",
                    "extra damage (251+",
                )
            )
            k.reduction = _col(e, lvl, "incoming damage reduction") / 100.0
            k.reduction_until = 1e9
    # Passive bonuses share the original interval (wiki: Barbarian King).
    u.dmg += passive_dps * base_interval
    u.interval = base_interval / (1.0 + passive_speed)
    if k.has("Noble Iron"):
        # Opening shots and range come from Noble Iron's level table.
        lv = k.lv("Noble Iron")
        k.spear_shots = int(_col("Noble Iron", lv, "number of attacks"))
        k.spear_bonus = _col("Noble Iron", lv, "damage per shot increase")
        u.extra["spear_base_range"] = u.range
        u.range = _col("Noble Iron", lv, "attack range")
    hero_level = u.level
    k.hp_recovery += stats.get(u.name, hero_level, "Health Recovery", default=0.0)
    if lo.pet:
        k.pet_name = lo.pet
        k.pet_level = pet_level
        k.phoenix = lo.pet == "Phoenix"
        _spawn_pet(battle, u, k)
    if k.has("Meteor Staff"):
        k.next_meteor = battle.t + _col(
            "Meteor Staff", k.lv("Meteor Staff"), "cooldown time"
        )
    u.kit = k


PET_FOLLOW = 3.0


def _spawn_pet(battle, hero: Unit, k: Kit):
    from .specs import attack_range, movement_speed

    name, lvl = k.pet_name, k.pet_level
    a = stats.attrs(name)
    hp = stats.get(name, lvl, "hitpoints", "Hitpoints", default=2000.0)
    dps = stats.get(name, lvl, "dps", "Damage per Second", "~damage per second", default=0.0)
    if name == "Unicorn":
        dps = 0.0
    # Wiki: Spirit Fox L9's DPH conflicts with DPS; retain DPS-derived hits.
    interval = a.get("attack_interval") or a.get("attack_interval_ck") or 1.0
    battle._uid += 1
    from .specs import UnitSpec

    sp = UnitSpec(name, prefer="owner", walls="fly" if a.get("is_flying") else "ignore", engages_units=True)
    p = Unit(
        battle._uid,
        name,
        "pet",
        "atk",
        hero.x + 0.5,
        hero.y + 0.5,
        hp=hp,
        dmg=dps * interval,
        interval=interval,
        # Unicorn uses a separate label (wiki: Unicorn).
        range_=stats.num(a.get("raw", {}).get("Healing Range")) or attack_range(name),
        speed=movement_speed(name),
        housing=0,
        flying=bool(a.get("is_flying")),
        hits_air=bool(a.get("is_air_targeting", True)),
        hits_ground=True,
        spec=sp,
        level=lvl,
    )
    p.owner = hero
    p.spawned_at = battle.t
    if name == "Angry Jelly":
        # game data v18.200.9: Angry Jelly.AttackRange=500 -> 5 tiles.
        p.range = 5.0
        p.x, p.y = hero.x, hero.y
        # Angry Jelly: Brainwash lasts 25/30/35 seconds by pet level.
        p.extra["brainwash_until"] = battle.t + stats.get(
            name, lvl, "Brainwash Duration"
        )
    if name == "Spirit Fox":
        # Both are invisible on deployment (wiki: Spirit Fox).
        duration = stats.get(name, lvl, "Invisibility Duration")
        p.invisible_until = max(p.invisible_until, battle.t + duration)
        hero.invisible_until = max(hero.invisible_until, battle.t + duration)
        p.extra["fox_next"] = battle.t + duration + 6.0
    if name == "Diggy":
        p.underground = True
    if name == "Phoenix":
        from dataclasses import replace

        # game data v18.200.9: Phoenix.DamageRadius=30 -> 0.3 tiles.
        p.spec = replace(p.spec, attack="splash", splash=0.3)
        # starts as an egg: invulnerable, untargetable, does nothing until
        # its hero is first knocked out (wiki: Phoenix)
        p.extra["egg"] = True
        p.invisible_until = p.invuln_until = 1e9
    if name == "Mighty Yak":
        from dataclasses import replace

        # Normal wall pathing and twentyfold wall damage (wiki: Mighty Yak).
        p.spec = replace(p.spec, walls="normal", vs_walls=20.0)
    if name == "Greedy Raven":
        from dataclasses import replace

        p.spec = replace(p.spec, vs_resources=5.0)  # wiki: Greedy Raven
    if name == "Sneezy":
        p.extra["next_summon"] = battle.t + 10.0  # wiki: Sneezy
    if name == "Frosty":
        p.extra["next_summon"] = battle.t + stats.num(a["raw"]["Summon Cooldown"])
    battle.attackers.append(p)
    new_member(battle, p)
    k.pet_unit = p
    hero.pet = p


def act_pet(battle, p: Unit):
    from . import pets

    pets.act(battle, p)


def tick(battle, u: Unit):
    k: Kit = u.kit
    t = battle.t
    dt = battle.DT
    if k.doomed_at is not None:
        if t >= k.doomed_at:
            k.doomed_at = None
            u.invuln_until = 0.0
            u.alive = False
            u.hp = 0.0
            from . import spells

            spells.maybe_revive(battle, u)
            return
    heal = k.regen
    pet = k.pet_unit
    if pet is not None and pet.extra.get("suspended"):
        pet = None
    if heal:
        u.heal(heal * dt)
    if k.has("Meteor Staff") and t >= k.next_meteor:
        candidates = _targets(battle, defenses=True) or [
            b for b in battle.buildings if battle.building_targetable(b)
        ]
        if candidates:
            target = min(candidates, key=lambda b: dist(b.x, b.y, u.x, u.y))
            # Radius and cooldown from Meteor Staff; flight time is unstated.
            with effects.damage_source(battle, u, "meteor"):
                _blast(
                    battle,
                    target.x,
                    target.y,
                    stats.attrs("Meteor Staff")["radius"],
                    _col("Meteor Staff", k.lv("Meteor Staff"), "damage per hit"),
                )
        k.next_meteor = t + _col("Meteor Staff", k.lv("Meteor Staff"), "cooldown time")
    if k.has("Electro Boots"):
        due = u.extra.get("boots_next", t)
        if t >= due or math.isclose(t, due):
            # Five tiles, one pulse per 0.4 seconds (wiki: Electro Boots).
            _blast(
                battle,
                u.x,
                u.y,
                5.0,
                _col("Electro Boots", k.lv("Electro Boots"), "aura damage per hit"),
            )
            u.extra["boots_next"] = t + 0.4
    if t < k.heal_until:
        for a in battle.attackers_near(u.x, u.y, 7.0):
            if a.kind not in ("siege", "siege_idle"):
                a.heal(k.heal_rate * dt)


def on_damaged(battle, u: Unit, amount: float, source, effect="attack"):
    """Passive equipment reacting to damage taken.

    Snake Bracelet: a Snake per 300 damage taken, up to the summon cap.
    Revenge Deck: counters each attacker (defense or unit) once per 0.8 s,
    within 25 tiles, healing the Duke; never traps or spells (wiki).
    """
    k: Kit = u.kit
    t = battle.t
    if k.has("Snake Bracelet"):
        lv = k.lv("Snake Bracelet")
        cap = int(_col("Snake Bracelet", lv, "max summoned snakes", default=54))
        acc = u.extra.get("snake_dmg", 0.0) + amount
        made = u.extra.get("snakes", 0)
        snake_lv = int(_col("Snake Bracelet", lv, "snake level", default=10))
        while acc >= 300.0 and made < cap:
            acc -= 300.0
            made += 1
            battle.spawn("Snake", u.team, u.x + 0.4, u.y + 0.4, level=snake_lv, kind="summon", group=u.group)
        u.extra["snake_dmg"], u.extra["snakes"] = acc, made
    if (
        k.has("Revenge Deck")
        and source is not None
        and getattr(source, "alive", False)
        and effect not in ("trap", "spell", "death", "aura", "counter")
        and not (
            isinstance(source, Unit)
            and source.name == "Firemite"
            and effect == "secondary"
        )
        and not (
            isinstance(source, Unit)
            and source.name == "Electro Dragon"
            and effect == "chain"
        )
        and not (
            isinstance(source, Unit)
            and (
                source.spec.attack == "suicide"
                or source.name in ("Yetimite", "Electromite")
            )
        )
    ):
        if dist(source.x, source.y, u.x, u.y) > 25.0:
            return
        cds = u.extra.setdefault("revenge_cd", {})
        key = id(source)
        if t < cds.get(key, -1.0):
            return
        cds[key] = t + 0.8
        lv = k.lv("Revenge Deck")
        dmg = _col("Revenge Deck", lv, "counter damage", default=225.0)
        u.heal(_col("Revenge Deck", lv, "heal per counter"))
        with effects.damage_source(battle, u, "counter"):
            _damage(battle, source, dmg)


SPEAR_RANGE = 10.0  # Rocket Spear throw range in tiles (wiki: Rocket Spear statistics)


def damage_taken_mult(battle, u: Unit) -> float:
    k = u.kit
    _, torch_reduction = effects.torch_stats(u, battle.t)
    reduction = k.reduction if battle.t < k.reduction_until else 0.0
    return 1.0 - max(reduction, torch_reduction)


def strike_bonus(battle, u: Unit, target) -> float:
    k = u.kit
    bonus = 0.0
    if k.spear_shots > 0:
        k.spear_shots -= 1
        bonus += k.spear_bonus * battle.atk_hero_mult  # fixed boosts take the league penalty (wiki)
        if k.spear_shots == 0 and "spear_base_range" in u.extra:
            u.range = u.extra.pop("spear_base_range")
    if k.vamp and k.doomed_at is None:  # No healing during revival (wiki: Vampstache).
        u.heal(k.vamp)
    return bonus


def monolith_bonus(battle, u: Unit, target):
    tiers = u.kit.mono_arrow
    if not tiers:
        return 0.0
    # Thresholds are inclusive at 180 and 250 (wiki: Monolith Arrow).
    housing = battle.monolith_housing
    if housing <= 180:
        stage = 0
    elif housing <= 250:
        stage = 1
    else:
        stage = 2
    return tiers[stage] * target.max_hp


def on_hit_extra(battle, u: Unit, target):
    k = u.kit
    if k.has("Electro Fangs"):
        damage = _col("Electro Fangs", k.lv("Electro Fangs"), "damage per hit")
        count = int(_col("Electro Fangs", k.lv("Electro Fangs"), "number of targets"))
        # Each secondary chains within three tiles at 80% (wiki: Electro Fangs).
        previous, visited = target, {target}
        for _ in range(count):
            candidates = [
                candidate
                for candidate in _targets(battle)
                if candidate not in visited
                and _distance(candidate, previous.x, previous.y) <= 3.0
            ]
            if not candidates:
                break
            next_target = min(
                candidates, key=lambda a: _distance(a, previous.x, previous.y)
            )
            visited.add(next_target)
            _damage(battle, next_target, damage)
            previous = next_target
            damage *= 0.8
    if k.frozen_arrow and isinstance(target, (Building, Unit)):
        # Slow movement and attacks for the listed duration (wiki: Frozen Arrow).
        slow, duration = k.frozen_arrow
        effects.add_slow(
            target, ("Frozen Arrow", u.id), 1.0 - slow, 1.0 - slow, battle.t + duration
        )


def on_death(battle, u: Unit) -> bool:
    """Phoenix revival (invincible, then knocked out); Fire Heart blast."""
    if u.pet is not None:
        from . import pets

        pets.owner_defeated(battle, u.pet)
        u.pet.extra["rampage_detached"] = True
        if u.pet.name == "Angry Jelly":
            u.pet.extra["brainwash_until"] = battle.t
    if u.dash is not None:
        end_dash(battle, u)
    k: Kit = u.kit
    if k.has("Fire Heart") and not u.extra.get("fire_heart_done"):
        # explodes the first time he falls only, revived or not (wiki: Fire Heart)
        u.extra["fire_heart_done"] = True
        battle.splash_buildings(u.x, u.y, 4.0, _col("Fire Heart", k.lv("Fire Heart"), "damage on defeat"), walls=False)
    if k.phoenix and k.pet_unit is not None and k.pet_unit.alive:
        k.phoenix = False
        dur = stats.get("Phoenix", k.pet_level, "Revive Duration", default=8.5)
        u.hp = 1.0
        u.invuln_until = battle.t + dur
        k.doomed_at = battle.t + dur
        # the egg hatches: both are invincible for the revive, then the
        # Phoenix fights on as an air unit (wiki: Phoenix)
        egg = k.pet_unit
        egg.extra.pop("egg", None)
        egg.invisible_until = 0.0
        egg.invuln_until = battle.t + dur
        egg.extra["phoenix_until"] = egg.invuln_until
        return True
    return False


@effects.sourced("ability")
def activate(battle, u: Unit):
    """The hero ability: heals the hero's health recovery and fires every
    active equipment effect at once."""
    k: Kit = u.kit
    if k is None or u.ability_used or not u.alive:
        return
    t = battle.t
    u.ability_used = True
    u.heal(k.hp_recovery)
    tgt = u.target
    if isinstance(tgt, Building) and not battle.building_targetable(tgt):
        tgt = None
    elif isinstance(tgt, Unit) and not tgt.targetable(t):
        tgt = None
    # Fireball precedes summons; Backpack fixes Flame Blower's facing (wiki).
    ordering = {"Fireball": 0, "Rocket Backpack": 1, "Lavaloon Puppet": 3}
    for e in sorted(k.equip, key=lambda name: ordering.get(name, 2)):
        lv = k.lv(e)
        if e == "Giant Arrow":
            dmg = _col(e, lv, "projectile damage")
            # One-tile radius and double Air Defense damage (wiki: Giant Arrow).
            _line(
                battle,
                u,
                tgt,
                75.0,
                1.0,
                lambda b: dmg * (2.0 if getattr(b, "key", None) == "ad" else 1.0),
            )
        elif e == "Spiky Ball":
            # Projectile damage and target count (wiki: Spiky Ball).
            dmg = _col(e, lv, "projectile damage")
            n = int(_col(e, lv, "number of targets"))
            hit = set()
            cand = _ball_targets(battle, hit)
            cur = None
            if tgt in cand:
                cur = tgt
            elif cand:
                cur = min(cand, key=lambda b: dist(b.x, b.y, u.x, u.y))
            for _ in range(n):
                if cur is None:
                    break
                hit.add(cur)
                if isinstance(cur, Unit):
                    battle.hit_unit(cur, dmg)
                else:
                    battle.hit_building(cur, dmg)
                cand = _ball_targets(battle, hit)
                cur = min(cand, key=lambda b: dist(b.x, b.y, cur.x, cur.y)) if cand else None

        elif e == "Earthquake Boots":
            # Damage percentages and eight-tile radius (wiki: Earthquake Boots).
            pct = _col(e, lv, "building damage %") / 100.0
            for b in battle.buildings:
                if b.alive and b.counted and b.edge_distance(u.x, u.y) <= 8.0:
                    battle.hit_building(b, b.max_hp * pct / (2 * b.eq_hits + 1))
                    b.eq_hits += 1
            for key, w in list(battle.walls.items()):
                if w.alive and dist(w.x, w.y, u.x, u.y) <= 8.0:
                    battle.hit_building(w, 1e9)  # boots destroy walls instantly (wiki)
            troop_pct = _col(e, lv, "troop damage %") / 100.0
            for f in battle.defenders_near(u.x, u.y, 8.0):
                if f.flying:
                    continue
                if f.kind == "trap_skeleton":
                    # Immunity versus nonlethal damage is unresolved (wiki: Earthquake Boots).
                    continue
                spells.quake_unit(battle, f, troop_pct)
        elif e == "Giant Gauntlet":
            k.reduction = _col(e, lv, "incoming damage reduction") / 100.0
            # Duration and ground splash radius (wiki: Giant Gauntlet).
            k.reduction_until = t + _col(e, lv, "ability duration")
            u.extra["gauntlet_until"] = k.reduction_until
            u.extra["gauntlet_radius"] = 2.5  # wiki: Giant Gauntlet
            # A separate primary range increase is NUMBER NOT STATED.
        elif e in ("Barbarian Puppet", "Archer Puppet", "Hog Rider Puppet", "Healer Puppet", "Lavaloon Puppet"):
            _puppet(battle, u, e, lv)
        elif e == "Rage Vial":
            # Independent ten-second effect (wiki: Rage Vial).
            units.add_rage(
                u,
                e,
                1.0 + _col(e, lv, "damage increase") / 100.0,
                _col(e, lv, "movement speed increase") / 8.0,
                t + 10.0,
            )
        elif e == "Invisibility Vial":
            # Every shot in this time window is boosted (wiki: Invisibility Vial).
            dur = _col(e, lv, "ability duration")
            _invisible(u, t + dur)
            u.extra["vial_until"] = t + dur
            u.extra["vial_bonus"] = _col(e, lv, "damage per shot increase")
        elif e == "Magic Mirror":
            for j in range(int(_col(e, lv, "clones", default=2))):
                c = battle.spawn(
                    "Archer Queen",
                    "atk",
                    u.x + 0.6 * (j - 0.5),
                    u.y + 0.4,
                    level=u.level,
                    kind="hero_clone",
                    group=u.group,
                )
                # Fixed health, damage and lifetime (wiki: Magic Mirror).
                c.hp = c.max_hp = c.base_max_hp = _col(e, lv, "clone health")
                c.dmg = _col(e, lv, "clone dps") * c.interval
                c.hp *= battle.atk_hero_mult
                c.max_hp *= battle.atk_hero_mult
                c.base_max_hp *= battle.atk_hero_mult
                c.dmg *= battle.atk_hero_mult
                c.extra["mirror_clone"] = True
                c.extra["expire_at"] = t + _col(e, lv, "clone duration")
                c.ability_used = True
            _invisible(u, t + 1.0)  # wiki: Magic Mirror
        elif e == "Action Figure":
            gg_lv = int(_col(e, lv, "giant giant level", default=10))
            battle.spawn("Giant Giant", "atk", u.x + 0.5, u.y + 0.5, level=gg_lv, kind="summon", group=u.group)
            _invisible(
                u, t + 1.0
            )  # "turning invisible for 1 second" (wiki: Action Figure)
        elif e == "Eternal Tome":
            dur = _col(e, lv, "ability duration", default=8.0)
            u.extra["tome_until"] = t + dur
            _moving_auras(battle, u)
        elif e == "Healing Tome":
            k.heal_rate = _col(e, lv, "healing per second")
            k.heal_until = t + _col(e, lv, "ability duration", default=20.0)
        elif e == "Fireball":
            candidates = _targets(battle, defenses=True) or _targets(battle)
            target = (
                min(candidates, key=lambda a: _distance(a, u.x, u.y))
                if candidates
                else None
            )
            # Wiki: Invisibility Spell and Overgrowth Spell, top-corner fallback.
            x, y = (target.x, target.y) if target is not None else (0.0, 0.0)
            _blast(
                battle,
                x,
                y,
                _col(e, lv, "damage radius"),
                _col(e, lv, "projectile damage"),
            )
        elif e == "Heroic Torch":
            dur = _col(e, lv, "ability duration", default=27.5)
            red = _col(e, lv, "incoming damage reduction") / 100.0
            u.extra["torch_until"] = t + dur
            u.extra["torch_reduction"] = red
            u.extra["torch_speed"] = (
                _col(e, lv, "ability attributes / speed increase") / 8.0
            )
            _moving_auras(battle, u)
        elif e == "Seeking Shield":
            dmg = _col(e, lv, "projectile damage")
            previous, visited = u, set()
            for _ in range(4):  # wiki: Seeking Shield
                candidates = [
                    a for a in _targets(battle, defenses=True) if a not in visited
                ]
                if not candidates:
                    candidates = [a for a in _targets(battle) if a not in visited]
                if not candidates:
                    # Targetless Shield flies to the top corner (wiki: Overgrowth Spell).
                    u.extra["shield_destination"] = (0.0, 0.0)
                    break
                target = min(
                    candidates, key=lambda a: _distance(a, previous.x, previous.y)
                )
                visited.add(target)
                _damage(battle, target, dmg)
                previous = target
        elif e == "Rocket Spear":
            k.spear_shots = int(_col(e, lv, "number of attacks", default=9))
            k.spear_bonus = _col(e, lv, "damage per shot increase")
            # the spears are thrown from 10 tiles (wiki: Rocket Spear, Attack
            # Range), so she outranges most defenses until they run out
            if "spear_base_range" not in u.extra:
                u.extra["spear_base_range"] = u.range
            u.range = SPEAR_RANGE
        elif e == "Electro Boots":
            k.boots_dps = _col(e, lv, "aura damage per second")
            k.boots_until = 0.0  # passive aura (see hero_tick); nothing to start here
        elif e == "Haste Vial":
            dur = _col(e, lv, "ability duration", default=10.0)
            u.extra.setdefault("haste_effects", {})[e] = (
                _col(e, lv, "speed increase") / 8.0,
                t + dur,
            )
            u.extra["haste_attack_until"] = t + dur
            u.extra["haste_attack"] = (
                1.0 + _col(e, lv, "ability attributes / attack speed increase") / 100.0
            )
            u.cooldown = 0.0
        elif e == "Frost Flake":
            n = int(_col(e, lv, "number of targets", default=7))
            visited = set()
            for _ in range(n):
                candidates = [
                    a for a in _targets(battle, defenses=True) if a not in visited
                ]
                if not candidates:
                    candidates = [a for a in _targets(battle) if a not in visited]
                if not candidates:
                    break
                target = min(candidates, key=lambda a: _distance(a, u.x, u.y))
                visited.add(target)
                _damage(battle, target, _col(e, lv, "projectile damage"))
                # A complete stop for the listed duration (wiki: Frost Flake).
                target.frozen_until = max(
                    target.frozen_until, t + _col(e, lv, "slow down duration")
                )
        elif e == "Dark Orb":
            slow = _col(e, lv, "slow down") / 100.0
            centre = tgt if tgt is not None else u
            # Five-tile footprint; moving travel parameters are unstated (wiki: Dark Orb).
            for target in _targets(battle):
                if _distance(target, centre.x, centre.y) <= 5.0:
                    _damage(battle, target, _col(e, lv, "projectile damage"))
                    effects.add_slow(
                        target,
                        (e, u.id),
                        1.0 - slow,
                        1.0 - slow,
                        t + _col(e, lv, "slow down duration"),
                    )
        elif e == "Metal Pants":
            k.reduction = _col(e, lv, "incoming damage reduction") / 100.0
            k.reduction_until = t + _col(e, lv, "ability duration", default=15.0)
        elif e == "Henchmen Puppet":
            for j in range(2):
                battle.spawn("Henchman", "atk", u.x + 0.5 * j, u.y + 0.5, level=int(_col(e, lv, "henchmen level", default=7)), kind="summon", group=u.group)
            _invisible(u, t + 1.0)  # wiki: Henchmen Puppet
        elif e == "Portal Pendant":
            _portal(battle, u, lv)
        elif e == "Rocket Backpack":
            start_dash(battle, u, _col(e, lv, "ability damage"))
        elif e == "Stun Blaster":
            dur = _col(e, lv, "stun duration", default=7.5)
            # Radius and stun from Stun Blaster; pulse timing is unstated.
            for target in _targets(battle):
                if isinstance(target, Building) and target.key in units.RESOURCE_KEYS:
                    continue
                if _distance(target, u.x, u.y) <= stats.attrs(e)["radius"]:
                    target.stun_until = max(target.stun_until, t + dur)
                    _damage(battle, target, _col(e, lv, "ability total damage"))
        elif e == "Flame Blower":
            dmg = _col(e, lv, "ability damage")
            u.extra["flame_direction"] = (
                u.dash["dir"] if u.dash is not None else u.extra["facing"]
            )
            # Extent and victims (wiki: Flame Blower); cone angle is unstated.
            _blast(battle, u.x, u.y, stats.attrs(e)["radius"], dmg)
    if battle.record:
        battle.log.append((round(t, 1), "ability", u.name))


def _ball_targets(battle, hit):
    buildings = [
        b for b in battle.buildings if b not in hit and battle.building_targetable(b)
    ]
    if buildings:
        return buildings
    # Buildings take priority over ground troops (wiki: Spiky Ball).
    return [
        f
        for f in battle.defenders
        if f not in hit and not f.flying and f.targetable(battle.t)
    ]


def _line(battle, u, tgt, length, width, dmg_fn):
    if tgt is None:
        dx, dy = u.extra["facing"]
    else:
        dx, dy = tgt.x - u.x, tgt.y - u.y
    d = math.hypot(dx, dy) or 1.0
    # The arrow hits structures and ground or air defenders (wiki: Giant Arrow).
    targets = (
        list(battle.buildings) + list(battle.walls.values()) + list(battle.defenders)
    )
    for b in targets:
        if not b.alive or isinstance(b, Building) and not b.counted:
            continue
        if isinstance(b, Unit) and b.underground:
            continue
        px, py = b.x - u.x, b.y - u.y
        along = (px * dx + py * dy) / d
        if (
            0 < along < length
            and abs(px * dy - py * dx) / d <= getattr(b, "half_hit", 0.0) + width
        ):
            if isinstance(b, Unit):
                battle.hit_unit(b, dmg_fn(b))
            else:
                battle.hit_building(b, dmg_fn(b))


def _puppet(battle, u, e, lv):
    table = {
        "Barbarian Puppet": ("Barbarian", "summoned barbarians"),
        "Archer Puppet": ("Archer", "summoned archers"),
        "Hog Rider Puppet": ("Hog Rider", "summoned hog riders"),
        "Healer Puppet": ("Healer", "summoned healers"),
        "Lavaloon Puppet": ("Lavaloon", "summoned lavaloons"),
    }
    if e == "Hog Rider Puppet":
        _invisible(u, battle.t + 1.0)  # wiki: Hog Rider Puppet
    troop, col = table[e]
    n = int(_col(e, lv, col, default=1))
    lvl_col = {"Hog Rider Puppet": "hog rider level", "Healer Puppet": "healer level", "Lavaloon Puppet": "lavaloon level"}.get(e)
    level = int(_col(e, lv, lvl_col)) if lvl_col else None
    if e in ("Barbarian Puppet", "Archer Puppet"):
        # Puppets use researched troop levels (wiki: Barbarian Puppet; Archer Puppet).
        level = (getattr(battle.plan, "troop_levels", {}) or {}).get(troop)
    for j in range(n):
        ang = 2 * math.pi * j / max(1, n)
        s = battle.spawn(troop, "atk", u.x + 0.6 * math.cos(ang), u.y + 0.6 * math.sin(ang), level=level, kind="summon", group=u.group)
        if e == "Archer Puppet":
            s.invisible_until = battle.t + _col(e, lv, "archer invisibility duration", default=6.0)
        if e == "Barbarian Puppet":
            # Twenty-second rage (wiki: Barbarian Puppet).
            units.add_rage(
                s,
                e,
                1.0 + _col(e, lv, "barbarian damage increase") / 100.0,
                _col(e, lv, "barbarian speed increase") / 8.0,
                battle.t + 20.0,
            )


def start_dash(battle, u, damage):
    from ..mechanics import WORLD

    # Through the village centre at 15 tiles/s (wiki: Rocket Backpack).
    dx, dy = WORLD / 2.0 - u.x, WORLD / 2.0 - u.y
    distance = math.hypot(dx, dy)
    if distance == 0.0:
        dx, dy = u.extra["facing"]
        distance = math.hypot(dx, dy)
    dx, dy = dx / distance, dy / distance
    limits = []
    for position, direction in ((u.x, dx), (u.y, dy)):
        if direction > 0:
            limits.append((WORLD - 0.5 - position) / direction)
        elif direction < 0:
            limits.append((0.5 - position) / direction)
    travel = max(0.0, min(limits))
    u.extra["facing"] = dx, dy
    u.dash = {
        "dir": (dx, dy),
        "until": battle.t + travel / 15.0,
        "end": (u.x + dx * travel, u.y + dy * travel),
        "hit": set(),
        "damage": damage,
    }
    pet = u.pet
    if pet is not None and pet.alive:
        pet.extra["suspended"] = True
        u.dash["pet"] = pet
        if pet in battle.attackers:
            battle.attackers.remove(pet)


def end_dash(battle, u):
    pet = u.dash.get("pet")
    u.dash = None
    if pet is not None:
        pet.extra.pop("suspended", None)
        if pet.alive:
            pet.x, pet.y = u.x, u.y
            if pet not in battle.attackers:
                battle.attackers.append(pet)


def dash_step(battle, u):
    dsh = u.dash
    remaining = max(0.0, dsh["until"] - battle.t)
    step = 15.0 * min(battle.DT, remaining)  # wiki: Rocket Backpack
    u.x += dsh["dir"][0] * step
    u.y += dsh["dir"][1] * step
    # Keep the existing footprint until the four-tile area is established.
    for b in battle.buildings:
        if b.alive and b.id not in dsh["hit"] and b.edge_distance(u.x, u.y) <= 1.5:
            dsh["hit"].add(b.id)
            battle.hit_building(b, dsh["damage"])
    if battle.t + battle.DT >= dsh["until"]:
        u.x, u.y = dsh["end"]
        end_dash(battle, u)


def _distance(target, x, y):
    if isinstance(target, Unit):
        return dist(target.x, target.y, x, y)
    return target.edge_distance(x, y)


def _targets(battle, *, defenses=False):
    buildings = [
        b
        for b in battle.buildings
        if battle.building_targetable(b)
        and (not defenses or battle.is_defense_target(b))
    ]
    if defenses:
        return buildings
    return buildings + [u for u in battle.defenders if u.targetable(battle.t)]


def _damage(battle, target, damage):
    if isinstance(target, Unit):
        battle.hit_unit(target, damage)
    else:
        battle.hit_building(target, damage)


def _blast(battle, x, y, radius, damage, *, exclude=None):
    # Secondary blasts retain Overgrowth immunity, including enemy troops.
    for target in list(battle.buildings) + list(battle.defenders):
        if (
            target is exclude
            or not target.alive
            or isinstance(target, Unit)
            and target.underground
        ):
            continue
        if isinstance(target, Building) and not target.counted:
            continue
        if _distance(target, x, y) <= radius:
            _damage(battle, target, damage)


def _moving_auras(battle, warden, members=None):
    t = battle.t
    # Keep the existing membership radius; the equipment pages do not verify it.
    if members is None:
        members = battle.attackers_near(warden.x, warden.y, 7.0)
    for ally in members:
        if ally.name == "Totem":
            continue
        until = warden.extra.get("tome_until", 0.0)
        if t < until:
            # One second after leaving, bounded by expiry (wiki: Eternal Tome).
            ally.extra.setdefault("tomes", {})[warden.id] = min(until, t + 1.0)
        until = warden.extra.get("torch_until", 0.0)
        if t < until and ally.kind not in ("siege", "siege_idle"):
            speed = warden.extra["torch_speed"]
            if ally.is_hero and ally is not warden:
                speed /= 2.0  # wiki: Heroic Torch
            ally.extra.setdefault("torches", {})[warden.id] = (
                min(until, t + 1.0),
                speed,
                warden.extra["torch_reduction"],
            )


# ----------------------------------------------------------------- auras
def apply_auras(battle):
    """Select the strongest life and damage buffs without changing base stats."""
    want = {}
    combatants = battle.attackers + battle.defenders
    for unit in combatants:
        boost = effects.crown_buff(unit)
        unit.aura_dmg = 1.0 + boost
        if boost:
            want[unit.id] = (boost, math.inf)
    wardens = [
        unit
        for unit in combatants
        if unit.alive and unit.name in ("Grand Warden", "Apprentice Warden")
    ]
    for warden in wardens:
        if warden.name == "Apprentice Warden":
            percentage = (
                stats.get("Apprentice Warden", warden.level, "Aura HP Increase") / 100.0
            )
            cap, rage = math.inf, 0.0
        else:
            kit = warden.kit
            percentage = cap = rage = 0.0
            _moving_auras(battle, warden)
            if kit is not None and kit.has("Life Gem"):
                percentage = (
                    _col("Life Gem", kit.lv("Life Gem"), "% hp increase") / 100.0
                )
                cap = _col("Life Gem", kit.lv("Life Gem"), "max hp increase")
            if kit is not None and kit.has("Rage Gem"):
                rage = _col("Rage Gem", kit.lv("Rage Gem"), "% damage increase") / 100.0
        # Wiki: Apprentice Warden grants its seven-tile aura on either team.
        allies = battle.attackers if warden.team == "atk" else battle.defenders
        for ally in allies:
            if not ally.alive or dist(ally.x, ally.y, warden.x, warden.y) > 7.0:
                continue
            if (
                ally is warden
                or ally.name == "Totem"
                or ally.kind in ("siege", "siege_idle")
            ):
                continue
            if percentage:
                previous_pct, previous_cap = want.get(ally.id, (0.0, 0.0))
                if min(percentage * ally.base_max_hp, cap) > min(
                    previous_pct * ally.base_max_hp, previous_cap
                ):
                    want[ally.id] = percentage, cap
            # Heroes receive half the damage increase (wiki: Rage Gem).
            increase = rage / 2.0 if ally.is_hero else rage
            ally.aura_dmg = max(ally.aura_dmg, 1.0 + increase)
    for ally in combatants:
        if ally.alive:
            effects.health_aura(ally, *want.get(ally.id, (0.0, 0.0)))


# --------------------------------------------------------- defending heroes
def spawn_defending_hero(battle, name, banner):
    lvl = battle.hero_levels.get(name) or stats.max_level(name, battle.town_hall)
    u = battle.spawn(name, "def", banner.x, banner.y, level=lvl, kind="hero")
    u.is_hero = True
    m = battle.def_hero_mult
    if m != 1.0:
        u.hp *= m
        u.max_hp *= m
        u.base_max_hp *= m
        u.dmg *= m
    u.home = (banner.x, banner.y)
    u.leash = (
        7.0
        if name == "Barbarian King"
        else stats.attrs(name).get("search_radius") or 9.0
    )  # wiki: Barbarian King
    if name in ("Minion Prince", "Dragon Duke"):
        u.flying = True


# ---------------------------------------------------------------- guardians
def spawn_guardian(battle, name, th):
    """TH18: the selected Guardian waits on the Town Hall and jumps down
    when an attacker enters its trigger radius (wiki: Town Hall/Guardians)."""
    lvl = battle.defense_levels.get("guardian") or stats.max_level(name, 18) or 1
    u = battle.spawn(name, "def", th.x, th.y + 1.0, level=lvl, kind="guardian")
    raw = stats.attrs(name).get("raw", {})
    u.home = (th.x, th.y)
    u.leash = stats.num(raw.get("Patrol Radius") or raw.get("Search Radius"), 12.0)
    u.extra["trigger"] = stats.num(raw.get("Trigger Radius"), 14.0)
    u.extra["waiting"] = True
    u.active_at = 1e9
    m = battle.guardian_mult
    if m != 1.0:
        u.hp *= m
        u.max_hp *= m
        u.base_max_hp *= m
        u.dmg *= m
    battle.guardian = u


def guardians_tick(battle):
    g = getattr(battle, "guardian", None)
    if g is None or not g.alive:
        return
    t = battle.t
    th = battle.th
    if g.extra.get("waiting"):
        th_down = th is not None and not th.alive
        near = any(a.name != "Totem" and t >= a.invisible_until and not a.underground for a in battle.attackers_near(g.x, g.y, g.extra["trigger"]))
        if near or th_down:
            g.extra["waiting"] = False
            g.active_at = t + 0.5  # jump down
    if "smasher" in g.spec.special and th is not None and not th.alive and not g.extra.get("enraged"):
        g.extra["enraged"] = True  # +60% damage and speed for the rest of the battle (wiki)
        g.dmg *= 1.6
        g.speed *= 1.6


# ----------------------------------------------------------- portal pendant
def _portal(battle, u, lv):
    e = "Portal Pendant"
    radius = _col(e, lv, "portal tile radius")
    capacity = _col(e, lv, "recall capacity")
    candidates = [
        ally
        for ally in battle.attackers_near(u.x, u.y, radius)
        if ally is not u
        and ally.name != "Totem"
        and ally.kind not in ("siege", "siege_idle")
        and not _free_pet(ally, battle.t)
    ]
    candidates.sort(
        key=lambda ally: (not ally.is_hero, -_housing(ally), ally.spawned_at)
    )
    taken = [u]
    for ally in candidates:
        housing = _housing(ally)
        if housing <= capacity:
            capacity -= housing
            taken.append(ally)
    heal = _col(e, lv, "healing on redeploy") / 100.0
    duration = _col(e, lv, "haste on redeploy")
    # Redeployment speed is stated on Portal Pendant's statistics page.
    speed = stats.num(stats.attrs(e)["raw"].get("Redeploy Speed Increase"), 56.0) / 8.0
    stash(battle, taken, (heal, duration, speed))


def _housing(unit):
    # Recall interaction housing (wiki: Portal Pendant).
    return spells.interaction_housing(unit)


def _free_pet(unit, t):
    # Sneezy travels free while her paired Hero can fight (wiki: Sneezy).
    return unit.kind == "pet" and (
        unit.extra.get("egg")
        or unit.attached(t)
        or unit.name == "Sneezy"
        and unit.owner is not None
        and unit.owner.alive
    )


def stash(battle, taken, bonuses):
    for unit in list(taken):
        if unit.dash is not None:
            end_dash(battle, unit)
        pet = unit.pet
        if (
            pet is not None
            and pet.alive
            and _free_pet(pet, battle.t)
            and pet not in taken
        ):
            taken.append(pet)
    for unit in taken:
        if "recalled" in unit.extra:
            continue
        unit.extra["recalled"] = battle.t
        unit.extra["portal"] = bonuses
        unit.alive = False
        battle.portal_stash.append(unit)
    # The player chooses when to redeploy; no mandatory delay is stated.
    battle.portal_ready_at = battle.t


def _resume_timers(unit, now):
    elapsed = now - unit.extra.pop("recalled")
    # Only these equipment/clone/Angry/Phoenix timers pause (wiki: Portal Pendant).
    for key in (
        "horse_until",
        "vial_until",
        "tome_until",
        "torch_until",
        "haste_attack_until",
        "angry_until",
    ):
        if key in unit.extra:
            unit.extra[key] += elapsed
    if unit.extra.get("clone"):
        unit.extra["expire_at"] += elapsed
    for source, (damage, speed, until) in list(
        unit.extra.get("rage_effects", {}).items()
    ):
        if source in ("Rage Vial", "Barbarian Puppet"):
            unit.extra["rage_effects"][source] = damage, speed, until + elapsed
    haste = unit.extra.get("haste_effects", {})
    if "Haste Vial" in haste:
        speed, until = haste["Haste Vial"]
        haste["Haste Vial"] = speed, until + elapsed
    until = unit.extra.get("equipment_invisible_until")
    if until is not None:
        unit.extra["equipment_invisible_until"] = until + elapsed
        unit.invisible_until = max(unit.invisible_until, until + elapsed)
    until = unit.extra.get("phoenix_until")
    if until is not None:
        unit.extra["phoenix_until"] = until + elapsed
        unit.invuln_until = max(unit.invuln_until, until + elapsed)
    kit = unit.kit
    if kit is not None:
        for attribute in ("reduction_until", "heal_until"):
            until = getattr(kit, attribute)
            if until:
                setattr(kit, attribute, until + elapsed)
        if kit.doomed_at is not None:
            kit.doomed_at += elapsed
            unit.invuln_until = kit.doomed_at


def portal_redeploy(battle, x, y):
    if not battle.can_deploy(x, y):
        raise ValueError("Portal redeployment requires a legal deployment tile")
    t = battle.t
    ordered = sorted(
        battle.portal_stash, key=lambda unit: (-_housing(unit), unit.spawned_at)
    )
    for unit in ordered:
        _resume_timers(unit, t)
        if unit.extra.get("mirror_clone") and t >= unit.extra["expire_at"]:
            unit.hp = 0.0
            continue
        heal, duration, speed = unit.extra.pop("portal")
        unit.x, unit.y = x, y
        unit.alive = True
        if unit not in battle.attackers:
            battle.attackers.append(unit)
        unit.heal(heal * unit.max_hp)
        if duration > 0:
            unit.extra.setdefault("haste_effects", {})["Portal Pendant"] = (
                speed,
                t + duration,
            )
        unit.target = unit.wall_target = None
        if unit.extra.get("clone") and unit not in battle._clones:
            battle._clones.append(unit)
    if battle.record:
        battle.log.append(
            (round(t, 1), "portal", len(ordered), round(x, 1), round(y, 1))
        )
    battle.portal_stash = []
    battle._buckets()


def defending_hero_ability(battle, u):
    # Defending heroes do not use abilities or equipment (wiki).
    return


def is_hero(name):
    return name in HEROES


def summon_tick(battle, unit):
    if unit.name != "Lavaloon":
        return False
    if not unit.can_act(battle.t):
        return True
    target = unit.target
    if target is None or not target.alive or not battle.building_targetable(target):
        target, unit.target_kind = battle.choose_target(unit)
        unit.target = target
    # Bomb cadence is the attack interval (wiki: Lavaloon Puppet/Lavaloon).
    due = unit.extra.get("bomb_next", unit.spawned_at + unit.interval)
    if battle.t >= due:
        # Direct hits are known; bomb splash radius and initial phase are unstated.
        for building in battle.buildings:
            if (
                building.alive
                and building.counted
                and building.edge_distance(unit.x, unit.y) == 0.0
            ):
                battle.hit_building(building, unit.dmg)
        battle.spawn(
            "Lavaloon Pup",
            unit.team,
            unit.x,
            unit.y,
            level=unit.level,
            kind="summon",
            group=unit.group,
            owner=unit,
        )
        unit.extra["bomb_next"] = battle.t + unit.interval
    if target is not None and _distance(target, unit.x, unit.y) > unit.range:
        battle.move_towards(unit, target)
    return True


def summon_death(battle, unit):
    if unit.name != "Lavaloon":
        return
    count = int(
        stats.get("Lavaloon", unit.level, "Lavaloon Pups Spawned (After Death)")
    )
    for _ in range(count):
        battle.spawn(
            "Lavaloon Pup",
            unit.team,
            unit.x,
            unit.y,
            level=unit.level,
            kind="summon",
            group=unit.group,
            owner=unit,
        )
    # Death damage is tabulated; its unstated radius prevents an area blast.


def _invisible(unit, until):
    unit.invisible_until = max(unit.invisible_until, until)
    unit.extra["equipment_invisible_until"] = max(
        unit.extra.get("equipment_invisible_until", 0.0), until
    )


def summon_spec(name, specification):
    from dataclasses import replace

    # Equipment and pet summons use their own wiki behavior.
    if name == "Henchman":
        return replace(specification, walls="fly")
    if name == "Lavaloon":
        return replace(specification, prefer="air_defense")
    if name == "Booger":
        return replace(specification, walls="fly")  # wiki: Sneezy/Booger
    if name == "Frostmite":
        return replace(
            specification, prefer="defense", walls="ignore", engages_units=False
        )
    return specification


def new_member(battle, unit):
    from .battle import BUCKET

    if unit.name == "Frostmite":
        unit.housing = 1  # wiki: Frosty/Frostmite
    elif unit.name == "Booger":
        unit.housing = 4  # wiki: Sneezy/Booger
    if hasattr(battle, "_bucket_grid"):
        cell = (int(unit.x / BUCKET), int(unit.y / BUCKET))
        members = battle._bucket_grid.setdefault(cell, [])
        if unit not in members:
            members.append(unit)
    for warden in battle.attackers:
        if (
            warden.alive
            and warden.name == "Grand Warden"
            and dist(warden.x, warden.y, unit.x, unit.y) <= 7.0
        ):
            _moving_auras(battle, warden, (unit,))


def pet_passives(battle, unit):
    from . import pets

    pets.passives(battle, unit)
