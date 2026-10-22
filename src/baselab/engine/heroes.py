"""Heroes: equipment (all 42 pieces), pets, auras, abilities, defenders.

Every number is read from the registry row of the equipment/pet at its level
(wiki tables mirrored 2026-10-15). Defending heroes use no equipment (wiki:
"The Archer Queen does not use any Hero Equipment when defending").
"""

from __future__ import annotations

import math

from ..loadouts import HeroLoadout
from . import effects, spells, stats, units
from .entities import Building, Pending, Unit, Wall, dist
from .specs import game_data

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
                 "spear_shots", "spear_bonus", "reduction_until", "reduction", "heal_until", "heal_rate",
                 "next_meteor", "crown_stage", "vamp", "frozen_arrow", "mono_arrow")

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
        self.reduction_until = 0.0
        self.reduction = 0.0
        self.heal_until = 0.0
        self.heal_rate = 0.0
        self.next_meteor = 0.0
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
        if not getattr(plan, "observed", False):
            raise ValueError(f"{name} is unavailable at Town Hall {town_hall}")
        # a real attacker brought it, so our unlock data is behind: use its
        # highest known level
        maximum = max(r["level"] for r in stats.record(name)["levels"])
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
    if lo.hero != u.name:
        raise ValueError(f"Loadout for {lo.hero} cannot be applied to {u.name}")
    # game data v18.200.9: heroes.csv ItemSlotCount=2 -> two slots per home Hero.
    if len(lo.equipment) > 2:
        raise ValueError(f"{u.name} can equip at most 2 equipment items")
    equipped = set()
    for equipment in lo.equipment:
        if equipment in equipped:
            raise ValueError(f"Duplicate equipment for {u.name}: {equipment}")
        equipped.add(equipment)
        if (
            equipment not in stats.registry()
            or stats.record(equipment)["kind"] != "equipment"
        ):
            raise ValueError(f"{equipment} is not hero equipment")
        # Wiki: Hero Equipment, each piece's User identifies its eligible Hero.
        owner = stats.attrs(equipment).get("raw", {}).get("User")
        if owner != u.name:
            raise ValueError(f"{equipment} belongs to {owner}, not {u.name}")
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
        if e == "Electro Boots":
            # game data v18.200.9: Electro Boots Aura.HitTimeMS=400 -> 0.4 s.
            u.extra["boots_next"] = battle.t + 0.4
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
        # game data v18.200.9: pets.csv AttackRange / 100 -> tiles; Electro Owl=550.
        range_=a.get("range_ck", attack_range(name)),
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
            spells.maybe_revive(battle, u)
            if battle.record:
                # The Phoenix revival ended: the hero is knocked out for good.
                battle.log.append((round(t, 1), "dies", u.name, u.team))
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
            # Radius and cooldown from Meteor Staff. The meteor falls for the
            # spell's deploy time (its pre-deploy effect is the projectile, the
            # deploy effect the impact) and lands where the target stood, so
            # it is wasted on a defense destroyed meanwhile (wiki: Meteor
            # Staff). ChargingTimeMS=300 may add to the fall; not applied.
            # game data v18.200.9: MPMeteorStaffSpell.DeployTimeMS=800 -> impact 0.8 s after the cast.
            with effects.damage_source(battle, u, "meteor"):
                battle.add_pending(
                    Pending(
                        t + 0.8,
                        target.x,
                        target.y,
                        stats.attrs("Meteor Staff")["radius"],
                        _col("Meteor Staff", k.lv("Meteor Staff"), "damage per hit"),
                        True,
                        True,
                        u.name,
                        extra={"hero_impact": "blast"},
                        actor=u,
                        effect="meteor",
                    )
                )
        k.next_meteor = t + _col("Meteor Staff", k.lv("Meteor Staff"), "cooldown time")
    if k.has("Electro Boots"):
        due = u.extra.get("boots_next", t)
        if t >= due or math.isclose(t, due):
            # One pulse per 0.4 seconds (wiki: Electro Boots). The wiki says
            # 5 tiles; the game data (as for the Electro Titan's aura) says:
            # game data v18.200.9: Electro Boots Aura.Radius=450 -> 4.5 tiles.
            # game data v18.200.9: Electro Boots Aura.HeroDamageMultiplier=25 -> heroes take 25%.
            _blast(
                battle,
                u.x,
                u.y,
                4.5,
                _col("Electro Boots", k.lv("Electro Boots"), "aura damage per hit"),
                hero_mult=0.25,
            )
            u.extra["boots_next"] = t + 0.4
    if t < k.heal_until:
        # game data v18.200.9: Healing Tome Aura.Radius=900 -> 9 tiles.
        for a in battle.attackers_near(u.x, u.y, 9.0):
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
        # game data v18.200.9: DragonCrownExplosion immunity flags unset -> troops, heroes and walls too.
        damage = _col("Fire Heart", k.lv("Fire Heart"), "damage on defeat")
        battle.splash_buildings(u.x, u.y, 4.0, damage, walls=True)
        battle.splash_units(u.x, u.y, 4.0, damage, True, True, team="def")
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
                dmg,
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
            if cur is not None and n > 0:
                hit.add(cur)
                # game data v18.200.9: BarbarianKingGearFootball.Speed=1500 -> 15 tiles/s.
                battle.add_pending(
                    Pending(
                        t + dist(u.x, u.y, cur.x, cur.y) / 15.0,
                        u.x,
                        u.y,
                        0.0,
                        dmg,
                        False,
                        True,
                        u.name,
                        extra={"hero_impact": "ball", "remaining": n, "visited": hit},
                        actor=u,
                        target=cur,
                    )
                )

        elif e == "Earthquake Boots":
            # Damage percentages and eight-tile radius (wiki: Earthquake Boots).
            # All five hits apply at once, as for the Earthquake Spell. The
            # spell row spaces them 0.4 s apart after ChargingTimeMS=300 and
            # HitTimeMS=400, but how those two combine into a first-hit time
            # is not stated, so the timing is left instant.
            # game data v18.200.9: Earthquake Boots Spell.TimeBetweenHitsMS=400 -> 0.4 s between hits.
            pct = _col(e, lv, "building damage %") / 100.0
            for b in battle.buildings:
                if b.alive and b.counted and b.edge_distance(u.x, u.y) <= 8.0:
                    battle.hit_building(b, b.max_hp * pct / (2 * b.eq_hits + 1))
                    b.eq_hits += 1
            for key, w in list(battle.walls.items()):
                if w.alive and dist(w.x, w.y, u.x, u.y) <= 8.0:
                    battle.hit_building(w, 1e9)  # boots destroy walls instantly (wiki)
            # The wiki's troop column is half the building column, but the
            # game data agrees with it only at level 1. Five hits per quake:
            # game data v18.200.9: Earthquake Boots Spell.NumberOfHits=5 -> five hits.
            # Per-hit troop permil by spell level, keyed by the per-hit building
            # permil (the building column matches the wiki at every level):
            # game data v18.200.9: Earthquake Boots Spell.BuildingDamagePermil=80 -> 8% per hit at level 7.
            # game data v18.200.9: Earthquake Boots Spell.TroopDamagePermil=20 -> 2% per hit at level 7.
            troop_permil = {20: 10, 40: 12, 60: 14, 68: 14, 72: 16, 76: 18, 80: 20}.get(round(pct * 200))
            troop_pct = (
                troop_permil * 5 / 1000.0
                if troop_permil is not None
                else _col(e, lv, "troop damage %") / 100.0
            )
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
            # game data v18.200.9: GrandWardenInvulnerability L18.DeactivateAfterTime=7200 -> 7.2 s emission.
            ability = game_data("special_abilities", "GrandWardenInvulnerability", lv)
            dur = float(ability["DeactivateAfterTime"]) / 1000.0
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
            # game data v18.200.9: vfx_chr_gw_Fireball_lvl1.FixedTravelTime=1500 -> 1.5 s.
            battle.add_pending(
                Pending(
                    t + 1.5,
                    x,
                    y,
                    _col(e, lv, "damage radius"),
                    _col(e, lv, "projectile damage"),
                    True,
                    True,
                    u.name,
                    extra={"hero_impact": "blast"},
                )
            )
        elif e == "Heroic Torch":
            # game data v18.200.9: GWHeroicTorch L10.DeactivateAfterTime=26500 -> 26.5 s emission.
            ability = game_data("special_abilities", "GWHeroicTorch", lv // 3 + 1)
            dur = float(ability["DeactivateAfterTime"]) / 1000.0
            red = _col(e, lv, "incoming damage reduction") / 100.0
            u.extra["torch_until"] = t + dur
            u.extra["torch_reduction"] = red
            u.extra["torch_speed"] = (
                _col(e, lv, "ability attributes / speed increase") / 8.0
            )
            _moving_auras(battle, u)
        elif e == "Seeking Shield":
            # game data v18.200.9: Seeking Shield ability DisableAttacking=TRUE,
            # DeactivateAfterTime=1200 -> no ordinary attacks for 1.2 s.
            u.extra["attack_lock_until"] = t + 1.2
            # game data v18.200.9: RoyalChampionShieldBounce.PreActivationDelayTime=933 -> 0.933 s.
            battle.add_pending(
                Pending(
                    t + 0.933,
                    u.x,
                    u.y,
                    0.0,
                    _col(e, lv, "projectile damage"),
                    True,
                    True,
                    u.name,
                    extra={"hero_impact": "shield", "remaining": 4, "visited": set()},
                )
            )
        elif e == "Rocket Spear":
            k.spear_shots = int(_col(e, lv, "number of attacks", default=9))
            k.spear_bonus = _col(e, lv, "damage per shot increase")
            # the spears are thrown from 10 tiles (wiki: Rocket Spear, Attack
            # Range), so she outranges most defenses until they run out
            if "spear_base_range" not in u.extra:
                u.extra["spear_base_range"] = u.range
            u.range = SPEAR_RANGE
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
            # The cooldown carries on (resetting it gave 20 throws in 10 s; wiki:
            # Haste Vial, at most 19).
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
            dx, dy = u.extra["facing"]
            length = math.hypot(dx, dy) or 1.0
            # game data v18.200.9: vfx_projectile_DarkOrb.Speed=1250 -> 12.5 tiles/s.
            # game data v18.200.9: vfx_projectile_DarkOrb.MaxTravelTime=1250 -> 1.25 s.
            # game data v18.200.9: MinionAttackAbility.PenetratingRadius=500 -> 5 tiles.
            battle.add_pending(
                Pending(
                    t,
                    u.x,
                    u.y,
                    5.0,
                    _col(e, lv, "projectile damage"),
                    True,
                    True,
                    u.name,
                    extra={
                        "hero_impact": "orb",
                        "direction": (dx / length, dy / length),
                        "speed": 12.5,
                        "until": t + 1.25,
                        "last_at": t,
                        "visited": set(),
                        "slow": _col(e, lv, "slow down") / 100.0,
                        "duration": _col(e, lv, "slow down duration"),
                    },
                )
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
            dx, dy = u.extra["flame_direction"]
            facing = math.atan2(dy, dx)
            # game data v18.200.9: DragonDukeFireBlast.ConeAngle=60 -> 60 degrees.
            half_angle = math.radians(60.0) / 2.0
            for target in _targets(battle):
                angle = math.atan2(target.y - u.y, target.x - u.x)
                offset = abs((angle - facing + math.pi) % (2 * math.pi) - math.pi)
                if (
                    offset <= half_angle
                    and _distance(target, u.x, u.y) <= stats.attrs(e)["radius"]
                ):
                    _damage(battle, target, dmg)
    if battle.record:
        battle.log.append((round(t, 1), "ability", u.name))


def projectile_impact(battle, pending):
    mode = pending.extra["hero_impact"]
    if mode == "blast":
        _blast(battle, pending.x, pending.y, pending.radius, pending.damage)
        return
    if mode == "puppet":
        _puppet(
            battle,
            pending.actor,
            pending.extra["equipment"],
            pending.extra["level"],
            first=pending.extra["first"],
            at=pending.at,
        )
        return
    if mode == "ball":
        target = pending.target
        pending.x, pending.y = target.x, target.y
        if target.alive and (
            not isinstance(target, Unit) or target.indirect_targetable(battle.t)
        ):
            _damage(battle, target, pending.damage)
        pending.extra["remaining"] -= 1
        if not pending.extra["remaining"]:
            return
        candidates = _ball_targets(battle, pending.extra["visited"])
        if not candidates:
            return
        target = min(
            candidates,
            key=lambda target: dist(pending.x, pending.y, target.x, target.y),
        )
        pending.extra["visited"].add(target)
        # game data v18.200.9: BarbarianKingGearFootball.Speed=1500 -> each bounce travels at 15 tiles/s.
        pending.at = battle.t + dist(pending.x, pending.y, target.x, target.y) / 15.0
        pending.target = target
        battle.add_pending(pending)
        return
    if mode == "arrow":
        state = pending.extra
        dx, dy = state["direction"]
        previous = state["travel"]
        travel = min(state["length"], (battle.t - pending.released_at) * 35.0)
        # Wiki: Giant Arrow, passes through structures, walls and ground/air defenders.
        targets = (
            list(battle.buildings)
            + list(battle.walls.values())
            + list(battle.defenders)
        )
        for target in targets:
            if not target.alive or target in state["visited"]:
                continue
            if isinstance(target, Building) and not target.counted:
                continue
            if isinstance(target, Unit) and not target.indirect_targetable(battle.t):
                continue
            px, py = target.x - pending.x, target.y - pending.y
            along = px * dx + py * dy
            half = getattr(target, "half_hit", 0.0)
            if (
                along + half >= previous
                and along - half <= travel
                and 0 < along < state["length"]
                and abs(px * dy - py * dx) <= half + pending.radius
            ):
                state["visited"].add(target)
                # Wiki: Giant Arrow, double damage to Air Defenses.
                damage = pending.damage * (
                    2.0 if getattr(target, "key", None) == "ad" else 1.0
                )
                _damage(battle, target, damage)
        if travel < state["length"]:
            state["travel"] = travel
            pending.at = round(battle.t + battle.DT, 6)
            battle.add_pending(pending)
        return
    if mode == "shield":
        target = pending.target
        if target is not None:
            pending.x, pending.y = target.x, target.y
            if target.alive:
                _damage(battle, target, pending.damage)
            pending.extra["remaining"] -= 1
        if not pending.extra["remaining"]:
            return
        visited = pending.extra["visited"]
        candidates = [
            target
            for target in _targets(battle, defenses=True)
            if target not in visited
        ]
        if not candidates:
            candidates = [
                target for target in _targets(battle) if target not in visited
            ]
        if not candidates:
            pending.actor.extra["shield_destination"] = (0.0, 0.0)
            return
        target = min(
            candidates, key=lambda target: _distance(target, pending.x, pending.y)
        )
        visited.add(target)
        # game data v18.200.9: AmazonQueen_shield.Speed=2000 -> 20 tiles/s.
        pending.at = battle.t + dist(pending.x, pending.y, target.x, target.y) / 20.0
        pending.target = target
        battle.add_pending(pending)
        return
    if mode == "orb":
        state = pending.extra
        at = min(battle.t, state["until"])
        distance = max(0.0, at - state["last_at"]) * state["speed"]
        dx, dy = state["direction"]
        for target in _targets(battle):
            if target in state["visited"]:
                continue
            along = (target.x - pending.x) * dx + (target.y - pending.y) * dy
            along = min(distance, max(0.0, along))
            x, y = pending.x + dx * along, pending.y + dy * along
            if _distance(target, x, y) > pending.radius:
                continue
            state["visited"].add(target)
            _damage(battle, target, pending.damage)
            slow = 1.0 - state["slow"]
            effects.add_slow(
                target,
                ("Dark Orb", pending.actor.id),
                slow,
                slow,
                battle.t + state["duration"],
            )
        pending.x += dx * distance
        pending.y += dy * distance
        state["last_at"] = at
        if at < state["until"]:
            pending.at = min(battle.t + battle.DT, state["until"])
            battle.add_pending(pending)


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


def _line(battle, u, tgt, length, width, damage):
    if tgt is None:
        dx, dy = u.extra["facing"]
    else:
        dx, dy = tgt.x - u.x, tgt.y - u.y
    d = math.hypot(dx, dy) or 1.0
    # game data v18.200.9: QueenPierceProjectile.Speed=3500 -> 35 tiles/s.
    battle.add_pending(
        Pending(
            battle.t + battle.DT,
            u.x,
            u.y,
            width,
            damage,
            True,
            True,
            u.name,
            extra={
                "hero_impact": "arrow",
                "direction": (dx / d, dy / d),
                "length": length,
                "travel": 0.0,
                "visited": set(),
            },
            actor=u,
        )
    )


def _puppet(battle, u, e, lv, *, first=0, at=None):
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
    # game data v18.200.9: BarbarianKingSpawnBarbarians.SpawnnedTroopsPerHit=5, SpawnDelayBetweenHitsMS=500.
    # game data v18.200.9: ArcherQueenSpawnArchers.SpawnnedTroopsPerHit=5, SpawnDelayBetweenHitsMS=1000.
    # game data v18.200.9: GrandWardenSummonLavaloon.SpawnnedTroopsPerHit=1, SpawnDelayBetweenHitsMS=250.
    batch, delay = {
        "Barbarian Puppet": (5, 0.5),
        "Archer Puppet": (5, 1.0),
        "Lavaloon Puppet": (1, 0.25),
    }.get(e, (n, 0.0))
    for j in range(first, min(first + batch, n)):
        ang = 2 * math.pi * j / max(1, n)
        # the attacker's own Town Hall caps an unknown researched level (the
        # spawn fallback is the battle's, i.e. the defender's, Town Hall)
        s = battle.spawn(troop, "atk", u.x + 0.6 * math.cos(ang), u.y + 0.6 * math.sin(ang), level=level, kind="summon",
                         group=u.group, town_hall=getattr(battle.plan, "town_hall", None))
        if e == "Archer Puppet":
            # Wiki: Recall Spell, Archer Puppet's equipment invisibility pauses.
            _invisible(
                s, battle.t + _col(e, lv, "archer invisibility duration", default=6.0)
            )
        if e == "Barbarian Puppet":
            # Twenty-second rage (wiki: Barbarian Puppet).
            units.add_rage(
                s,
                e,
                1.0 + _col(e, lv, "barbarian damage increase") / 100.0,
                _col(e, lv, "barbarian speed increase") / 8.0,
                battle.t + 20.0,
            )
    if first + batch < n:
        battle.add_pending(
            Pending(
                (battle.t if at is None else at) + delay,
                u.x,
                u.y,
                0.0,
                0.0,
                False,
                False,
                u.name,
                extra={
                    "hero_impact": "puppet",
                    "equipment": e,
                    "level": lv,
                    "first": first + batch,
                },
                actor=u,
            )
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
    # The dash also hits defending troops and heroes, ground and air:
    # game data v18.200.9: DragonDukeDeadlyDashMapCenter.ActAsPenetratingRadius=150 -> 1.5 tiles.
    # game data v18.200.9: DragonDukeDeadlyDashMapCenter.ActAsPenetratingAirTargets=TRUE -> air too.
    for f in battle.defenders_near(u.x, u.y, 1.5):
        if ("unit", f.id) not in dsh["hit"] and f.alive and not f.underground:
            dsh["hit"].add(("unit", f.id))
            battle.hit_unit(f, dsh["damage"], attacker=u)
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


def _blast(battle, x, y, radius, damage, *, exclude=None, hero_mult=1.0):
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
            hero = isinstance(target, Unit) and target.is_hero
            _damage(battle, target, damage * hero_mult if hero else damage)


def _moving_auras(battle, warden, members=None):
    t = battle.t
    # game data v18.200.9: Eternal Tome Aura.Radius=900 -> 9 tiles.
    # game data v18.200.9: Heroic Torch Aura.Radius=900 -> 9 tiles.
    if members is None:
        members = battle.attackers_near(warden.x, warden.y, 9.0)
    for ally in members:
        if ally.name == "Totem":
            continue
        until = warden.extra.get("tome_until", 0.0)
        if t < until:
            # game data v18.200.9: Eternal Tome Aura.ShieldTime=1000 -> 1 s after the last aura tick.
            ally.extra.setdefault("tomes", {})[warden.id] = t + 1.0
        until = warden.extra.get("torch_until", 0.0)
        if t < until and ally.kind not in ("siege", "siege_idle"):
            speed = warden.extra["torch_speed"]
            if ally.is_hero and ally is not warden:
                speed /= 2.0  # wiki: Heroic Torch
            # game data v18.200.9: Heroic Torch Aura.ShieldTime=1000, BoostTimeMS=1000 -> 1 s tail.
            ally.extra.setdefault("torches", {})[warden.id] = (
                t + 1.0,
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
        # game data v18.200.9: Rage Gem Aura.BoostTimeMS=1000 -> retain each source's last tick for 1 s.
        for until, increase in unit.extra.get("rage_auras", {}).values():
            if battle.t < until:
                unit.aura_dmg = max(unit.aura_dmg, 1.0 + increase)
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
            # game data v18.200.9: Apprentice Aura.Radius=700 -> 7 tiles.
            radius = 7.0
        else:
            # game data v18.200.9: Life Gem Aura.Radius=900 -> 9 tiles.
            # game data v18.200.9: Rage Gem Aura.Radius=900 -> 9 tiles.
            radius = 9.0
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
        # Wiki: Apprentice Warden grants its aura on either team.
        allies = battle.attackers if warden.team == "atk" else battle.defenders
        for ally in allies:
            if not ally.alive or dist(ally.x, ally.y, warden.x, warden.y) > radius:
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
            if increase:
                # game data v18.200.9: Rage Gem Aura.BoostTimeMS=1000 -> per-recipient expiry.
                ally.extra.setdefault("rage_auras", {})[warden.id] = (
                    battle.t + 1.0,
                    increase,
                )
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
    # Wiki: Recall Spell and Portal Pendant, active equipment timers pause.
    for key in (
        "gauntlet_until",
        "attack_lock_until",
        "boots_next",
        "horse_until",
        "vial_until",
        "tome_until",
        "torch_until",
        "haste_attack_until",
        "angry_until",
        # Wiki: Portal Pendant, Angry Jelly's effect pauses pending redeployment.
        "brainwash_until",
    ):
        if key in unit.extra:
            unit.extra[key] += elapsed
    # Wiki: Recall Spell, clone lifetimes and active equipment effects pause.
    if unit.extra.get("clone") or unit.extra.get("mirror_clone"):
        unit.extra["expire_at"] += elapsed
    # Wiki: Recall Spell, recipient Tome/Torch effects and equipment cooldowns pause.
    for source, until in list(unit.extra.get("tomes", {}).items()):
        unit.extra["tomes"][source] = until + elapsed
    for source, (until, speed, reduction) in list(
        unit.extra.get("torches", {}).items()
    ):
        unit.extra["torches"][source] = until + elapsed, speed, reduction
    for source, until in list(unit.extra.get("revenge_cd", {}).items()):
        unit.extra["revenge_cd"][source] = until + elapsed
    for source, (damage, speed, until) in list(
        unit.extra.get("rage_effects", {}).items()
    ):
        if source in ("Rage Vial", "Barbarian Puppet"):
            unit.extra["rage_effects"][source] = damage, speed, until + elapsed
    haste = unit.extra.get("haste_effects", {})
    # Wiki: Portal Pendant, its redeployment haste is an active equipment effect.
    for source in ("Haste Vial", "Portal Pendant"):
        if source in haste:
            speed, until = haste[source]
            haste[source] = speed, until + elapsed
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
        # Wiki: Recall Spell, preserve the Meteor Staff equipment cooldown too.
        for attribute in ("reduction_until", "heal_until", "next_meteor"):
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
    # game data v18.200.9: GW Equipment Lavaloon.AttackSpeed=2500 -> normal 2.5 s attack cadence.
    # Wiki: Poison Spell, attack slows also affect these troop attacks.
    interval = units.attack_interval(unit, battle)
    if battle.t < unit.extra.get("haste_attack_until", 0.0):
        interval /= unit.extra["haste_attack"]
    interval /= max(0.05, effects.slow_mult(unit, battle.t))
    due = unit.extra.get("bomb_next", unit.spawned_at + interval)
    if battle.t >= due:
        # Each bomb splashes ground targets around the Lavaloon itself; the
        # initial phase is unstated.
        # game data v18.200.9: GW Equipment Lavaloon.DamageRadius=180 -> 1.8 tiles.
        # game data v18.200.9: GW Equipment Lavaloon.SelfAsAoeCenter=TRUE -> centred on itself.
        # Wiki: Rage Spell/Home Village and Rage Gem, use the strongest damage buff.
        rage, _ = units.rage_boost(unit, battle.t)
        damage = unit.dmg * max(rage, unit.aura_dmg, unit.extra.get("bell_damage", 1.0))
        units._area_hit(battle, unit, unit.x, unit.y, 1.8, damage, walls=True)
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
        unit.extra["bomb_next"] = battle.t + interval
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
    # game data v18.200.9: GW Equipment Lavaloon.DieDamageRadius=200 -> 2 tiles.
    # game data v18.200.9: GW Equipment Lavaloon.DieDamageDelay=416 -> 0.416 s.
    damage = stats.get("Lavaloon", unit.level, "Damage when Destroyed")
    battle.add_pending(
        Pending(
            battle.t + 0.416,
            unit.x,
            unit.y,
            2.0,
            damage,
            False,
            True,
            unit.name,
            team="def" if unit.team == "atk" else "atk",
            extra={"buildings": damage if unit.team == "atk" else 0.0},
            actor=unit,
            effect="death",
        )
    )


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
            and dist(warden.x, warden.y, unit.x, unit.y) <= 9.0
        ):
            _moving_auras(battle, warden, (unit,))


def pet_passives(battle, unit):
    from . import pets

    pets.passives(battle, unit)
