"""Every defensive building's weapon, wiki-verified (mirror 2026-10-15).

Numbers per level come from the registry; behaviour constants below quote
the wiki page they come from. TH17/18 defenses are included so the engine can
also simulate the user's attacks on higher Town Halls.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import effects, stats
from .entities import Building, Pending, Unit, dist


class Weapon:
    __slots__ = (
        "owner",
        "kind",
        "targets",
        "range",
        "min_range",
        "interval",
        "damage",
        "cooldown",
        "target",
        "multi",
        "lock_time",
        "idle_until",
        "facing",
        "mode",
        "extra",
        "burst_left",
        "ammunition",
        "ammo_time",
    )

    def __init__(self, owner: Building, kind: str, *, targets="both", range_=10.0, min_range=0.0, interval=1.0, damage=0.0, extra=None):
        self.owner = owner
        self.kind = kind
        self.targets = targets
        self.range = range_
        self.min_range = min_range
        self.interval = interval
        self.damage = damage
        self.cooldown = 0.0
        self.target = None
        self.multi = []
        self.lock_time = 0.0
        self.idle_until = 0.0
        self.facing = 0.0
        self.mode = owner.mode
        self.extra = extra or {}
        self.burst_left = 0
        self.ammunition = None
        self.ammo_time = 0.0


FACINGS = {"N": -math.pi / 2, "NE": -math.pi / 4, "E": 0.0, "SE": math.pi / 4, "S": math.pi / 2, "SW": 3 * math.pi / 4, "W": math.pi, "NW": -3 * math.pi / 4}

# TH16 Giga Inferno (wiki "Town Hall/Giga Inferno (TH16)"): 300 DPS per target,
# 4 targets, range 10, death bomb 1,100 within 4.5 tiles plus a 12 s poison
# (180 max DPS, 50% movement and attack slow). Activates once the Town Hall is
# damaged or the base is 51% destroyed.
GIGA_INFERNO = {
    13: dict(dps=None, targets=5),
    16: dict(dps=300.0, targets=4, range=10.0, death=1100.0, death_radius=4.5, poison_dps=180.0, poison_time=12.0, slow=0.5),
}
# TH17-18 Inferno Artillery (wiki): range 12, 4 targets, 3.5 s, 210 per hit
# (L5) plus flame pools of 75 DPS for 6.8 s; always active.
# game data v18.200.9: TH17WeaponAreaDamage.Radius=250 -> 2.5 tiles.
INFERNO_ARTILLERY = dict(
    range=12.0,
    targets=4,
    interval=3.5,
    damage=210.0,
    pool_dps=75.0,
    pool_time=6.8,
    pool_radius=2.5,
    # game data v18.200.9: TH17WeaponAreaDamage.TimeBetweenHitsMS=400 -> 0.4 s.
    pool_gap=0.4,
    # game data v18.200.9: TH17WeaponAreaDamage.NumberOfHits=17 -> 17 applications.
    pool_hits=17,
)


# Eagle Artillery group targeting.
# game data v18.200.9: Eagle Artillery.TargetGroups=TRUE -> it aims at groups.
# game data v18.200.9: Eagle Artillery.TargetGroupsRadius=500 -> each candidate scores units within 5 tiles.
# The score is the sum of each unit's Characters/Heroes/Pets.csv
# EnemyGroupWeight (the weight a unit carries for enemy group targeting):
# game data v18.200.9: Barbarian King.EnemyGroupWeight=2500 -> 2500.
# game data v18.200.9: Archer Queen.EnemyGroupWeight=500 -> 500.
# game data v18.200.9: Golem.EnemyGroupWeight=3000 -> 3000.
# game data v18.200.9: Giant Giant.EnemyGroupWeight=3400 -> 3400.
# game data v18.200.9: Mighty Yak.EnemyGroupWeight=400 -> 400 (every pet).
# Wiki: Eagle Artillery agrees
# ("targets the area with the largest density of hitpoints"; it "will most
# likely lock onto the Barbarian King"). Engine names mapped to the CSV rows
# (P.E.K.K.A = PEKKA, Bat = Spell Bat, Ice Pup = Ice Hound Pup, ...); units
# with no matching row use 100, the most common value.
EAGLE_GROUP_RADIUS = 5.0
EAGLE_GROUP_WEIGHT = {
    "Apprentice Warden": 100, "Archer": 100, "Archer Queen": 500,
    "Azure Dragon": 5000, "Baby Dragon": 1000, "Balloon": 500, "Barbarian": 100,
    "Barbarian Kicker": 400, "Barbarian King": 2500, "Barcher": 200,
    "Bat": 100, "Battle Blimp": 100, "Battle Drill": 100, "Battle Ram": 500,
    "Bear": 1600, "Big Boy": 800, "Booger": 300, "Bowler": 500,
    "Broom Witch": 2000, "C.O.O.K.I.E": 1000, "Debt Collector": 50,
    "Dragon": 2000, "Dragon Duke": 2500, "Dragon Rider": 2500, "Druid": 1600,
    "Electro Dragon": 2000, "Electro Titan": 3000, "Electromite": 50,
    "Firecracker": 800, "Firemite": 50, "Flame Flinger": 100, "Frostmite": 100,
    "Furnace": 1800, "Giant": 500, "Giant Giant": 3400, "Giant Skeleton": 2000,
    "Giant Thrower": 600, "Goblin": 50, "Golem": 3000, "Golemite": 600,
    "Grand Warden": 500, "Headhunter": 100, "Healer": 30, "Henchman": 800,
    "Hog Rider": 500, "Hog Wizard": 600, "Ice Golem": 500, "Ice Hound": 1800,
    "Ice Minion": 100, "Ice Pup": 100, "Ice Wizard": 200, "Inferno Dragon": 1500,
    "K.A.N.E": 6000, "Lava Hound": 3000, "Lava Pup": 100, "Lavaloon": 1500,
    "Log Launcher": 100, "M.E.C.H.A": 1000, "Meteor Golem": 3000,
    "Meteormite": 1500, "Miner": 500, "Minion": 100, "Minion Prince": 2500,
    "P.E.K.K.A": 2000, "Party Wizard": 200, "Phoenix Egg": 0,
    "Pumpkin Barbarian": 100, "Ram Rider": 1000, "Rocket Balloon": 500,
    "Root Rider": 2000, "Royal Champion": 1000, "Royal Ghost": 100,
    "Siege Barracks": 100, "Skeleton": 100, "Skeleton Barrel": 500, "Snake": 100,
    "Snake Barrel": 500, "Sneaky Goblin": 200, "Spell Skeleton": 100,
    "Stone Slammer": 100, "Super Archer": 600, "Super Barbarian": 400,
    "Super Bowler": 2500, "Super Dragon": 4000, "Super Giant": 800,
    "Super Hog": 500, "Super Hog Rider": 1200, "Super Miner": 2400,
    "Super Minion": 1000, "Super Rider": 500, "Super Valkyrie": 1500,
    "Super Wall Breaker": 50, "Super Witch": 2500, "Super Wizard": 1000,
    "Super Yeti": 3500, "The Disarmer": 4000, "Thrower": 700, "Totem": 100,
    "Troop Launcher": 100, "Valkyrie": 500, "Wall Breaker": 50,
    "Wall Wrecker": 100, "Witch": 200, "Witch Golem": 4000, "Wizard": 200,
    "YEETer": 2500, "Yeti": 1800, "Yetimite": 50,
}


def _group_weight(unit):
    if unit.kind == "pet" and unit.name not in EAGLE_GROUP_WEIGHT:
        return 400
    return EAGLE_GROUP_WEIGHT.get(unit.name, 100)


def _eagle_pick(battle, w, pool):
    """Candidate whose 5-tile neighbourhood carries the most group weight;
    ties go to the nearest (the tie rule is not stated)."""
    b = w.owner
    t = battle.t

    def score(unit):
        return sum(
            _group_weight(other)
            for other in battle.attackers_near(unit.x, unit.y, EAGLE_GROUP_RADIUS)
            if other.targetable(t)
            and dist(other.x, other.y, unit.x, unit.y) <= EAGLE_GROUP_RADIUS
        )

    return max(pool, key=lambda a: (score(a), -dist(a.x, a.y, b.x, b.y)))


def _dmg(name, level, interval):
    d = stats.get(name, level, "Damage per Shot", "Damage per Hit", "Damage per Attack", default=None)
    if d is None:
        dps = stats.get(name, level, "dps", "Damage per Second", default=0.0)
        d = dps * interval
    return d


CRAFTED = {
    "cake": "Cake-A-Pult",
    "candle": "Hot Candle",
    "hunter": "Hero Hunter",
    "bell": "Hero Bell",
    "hook": "Hook Tower",
}


def crafted_level(name: str, town_hall: int) -> int:
    """Highest module level allowed at this Town Hall (wiki tables)."""
    best = 1
    for r in stats.record(name)["levels"]:
        lv = r.get("level")
        if not isinstance(lv, int):
            continue
        req = stats.num(stats.row(name, lv).get("Town Hall Level Required"), 99)
        if req <= town_hall:
            best = max(best, lv)
    return best


# Static tables (module level so tools/baselab/rust_export.py can export
# them to the Rust engine's catalog; a game patch edits them here only).
# Wiki: Crafting Station, phase 4 runs August 1 to December 31, 2026.
CRAFTING_PHASE = 4
CRAFTING_WINDOW = ("2026-08-01", "2026-12-31")
CRAFTED_MODES = ("cake", "candle", "hunter")
# Wiki: Spell Tower, mode unlock levels (Earthquake also needs TH17).
SPELL_TOWER_UNLOCKS = {"rage": 1, "poison": 2, "invis": 3, "eq": 4, "quake": 4, "earthquake": 4}
# Wiki: X-Bow, Inferno Tower, Eagle Artillery and Scattershot ammunition.
AMMUNITION = {"xbow": 1500, "inferno": 1000, "eagle": 90, "scatter": 90}
# Wiki: Town Hall/Inferno Artillery, five weapon levels.
ARTILLERY_DAMAGE = (140.0, 157.5, 175.0, 192.5, 210.0)
# Wiki: Cannon/Home Village, Archer Tower/Home Village and Mortar gear-up levels.
GEAR_MINIMUM = {"cannon": 7, "at": 10, "mortar": 8}
# game data v18.200.9: geared Cannon L7-21 AltProjectile rows use Cannonball5/7/
# 10/12/13/14/15/16.StartOffset=62/66/70/72/74/76/76/76 -> tiles by level.
GEARED_CANNON_OFFSETS = (
    0.62,
    0.66,
    0.66,
    0.70,
    0.70,
    0.72,
    0.74,
    0.76,
    0.76,
    0.76,
    0.76,
    0.76,
    0.76,
    0.76,
    0.76,
)
# Wiki: Archer Tower/Home Village, Fast Attack damage per shot, L10-21.
FAST_ARCHER_SHOTS = (31.5, 35, 37.5, 40, 45, 50, 52.5, 55, 60, 65, 69, 72.5)


def _attach_crafted(battle, b: Building):
    if battle.crafting_phase != CRAFTING_PHASE or not (
        CRAFTING_WINDOW[0] <= battle.crafting_date <= CRAFTING_WINDOW[1]
    ):
        raise ValueError("Only crafting phase 4 is supported")
    mode = b.mode
    if mode in (None, "none"):
        b.hp = b.max_hp = 1000.0  # Wiki: Crafting Station, unselected station.
        return
    if mode not in CRAFTED_MODES:
        raise ValueError("Crafted defense is unavailable in phase 4")
    name = CRAFTED[mode]
    cap = crafted_level(name, battle.town_hall)
    level = battle.defense_levels.get("crafting", cap)
    hp_level = battle.defense_levels.get("crafting:hitpoints", level)
    damage_level = battle.defense_levels.get("crafting:damage", level)
    effect_level = battle.defense_levels.get("crafting:effect", level)
    for selected in (hp_level, damage_level, effect_level):
        if not isinstance(selected, int) or not 1 <= selected <= cap:
            raise ValueError(f"Illegal {name} module level: {selected}")
    b.name, b.level = name, damage_level
    b.hp = b.max_hp = stats.get(name, hp_level, "Hitpoints")
    W = Weapon
    if mode == "cake":
        # Wiki: Cake-A-Pult, both-height delayed bomb and same-height impact.
        b.weapon = W(
            b,
            "cake",
            range_=12.0,
            min_range=3.0,
            interval=3.0,
            damage=stats.get(name, damage_level, "Damage per Hit"),
            extra={
                "splash": 2.5,
                "bomb": stats.get(name, effect_level, "Explosion Damage"),
                "bomb_radius": 2.5,
                "bomb_delay": 3.0,
            },
        )
    elif mode == "candle":
        # Wiki: Hot Candle, use the starts of the decay ranges.
        damage = stats.get(name, damage_level, "Damage per Hit")
        dps = stats.get(name, damage_level, "Damage per Second per Flame")
        b.weapon = W(
            b,
            "candle",
            range_=10.5,
            interval=damage / dps,
            damage=damage,
            extra={
                "targets": 6,
                "melt1": stats.get(
                    name, effect_level, "Total Seconds Active / First Decay"
                ),
                "melt2": stats.get(
                    name, effect_level, "Total Seconds Active / Second Decay"
                ),
            },
        )
    else:
        # Wiki: Hero Hunter, the poison module selects its Poison Spell level.
        b.weapon = W(
            b,
            "hunter",
            range_=9.5,
            interval=0.6,
            damage=stats.get(name, damage_level, "Damage per Hit"),
            extra={
                "poison_level": int(
                    stats.get(name, effect_level, "Poison Spell Level")
                ),
                "poison_time": 3.0,
            },
        )


def attach_weapon(battle, b: Building):
    key, name, lvl = b.key, b.name, b.level
    a = stats.attrs(name) if name in stats.registry() else {}
    W = Weapon
    if key == "th":
        th = battle.town_hall
        if th >= 18:
            return  # Guardians defend in place of weapons (wiki: Town Hall/Guardians)
        if th >= 17:
            ia = INFERNO_ARTILLERY
            b.weapon = W(
                b,
                "inferno_artillery",
                range_=ia["range"],
                interval=ia["interval"],
                damage=_artillery_damage(battle),
                extra=dict(ia),
            )
            battle.th_active = True
            b.is_defense = True
        elif th >= 13:
            g = GIGA_INFERNO[16]
            b.weapon = W(b, "giga_inferno", range_=g["range"], interval=0.128, damage=g["dps"] * 0.128, extra=dict(g))
            b.is_defense = True
        return
    if key == "ad":
        b.weapon = W(b, "single", targets="air", range_=10.0, interval=1.0, damage=_dmg(name, lvl, 1.0))
    elif key == "at":
        b.weapon = W(b, "single", range_=10.0, interval=0.5, damage=_dmg(name, lvl, 0.5))
    elif key == "cannon":
        b.weapon = W(b, "single", targets="ground", range_=9.0, interval=0.8, damage=_dmg(name, lvl, 0.8))
    elif key == "mat":
        # Wiki: Multi-Archer Tower, charges use the Damage per Shot column.
        # 3 archers; with fewer targets several archers focus one (wiki)
        per = stats.get(name, lvl, "Damage per Hit", "Damage per Shot")
        b.weapon = W(b, "multi_archer", range_=10.0, interval=0.6, damage=per)
    elif key == "ric":
        # One bounce to the nearest other ground unit within 3.5 tiles of the
        # target, in any direction (no direction field exists).
        # game data v18.200.9: Ricochet Cannon.ProjectileBounces=1 -> one bounce.
        # game data v18.200.9: MergedCannonProjectile.MaxBounceDistance=350 -> 3.5 tiles.
        # game data v18.200.9: MergedCannonProjectile.BounceDamageReductionPercent=30 -> 70%.
        # Wiki: Ricochet Cannon, the bounce may go to "a different unit closer
        # to the initial target".
        b.weapon = W(b, "ricochet", targets="ground", range_=9.0, interval=0.8, damage=stats.get(name, lvl, "Damage per Shot (Primary Target)", default=312.0),
                     extra={"bounce": stats.get(name, lvl, "Secondary Chain Damage", default=218.4), "bounce_range": 3.5})
    elif key == "bt":
        b.weapon = W(b, "splash", targets="ground", range_=6.0, interval=1.1, damage=_dmg(name, lvl, 1.1),
                     extra={"splash": 1.5, "death": stats.get(name, lvl, "Damage when destroyed", default=600.0), "death_radius": 2.75, "death_delay": 1.0})
    elif key == "wt":
        b.weapon = W(b, "splash", range_=7.0, interval=1.3, damage=_dmg(name, lvl, 1.3), extra={"splash": 1.0, "same_type": True})
    elif key == "mortar":
        # Wiki: Mortar, normal hits must not read the geared shell column.
        b.weapon = W(
            b,
            "mortar",
            targets="ground",
            range_=11.0,
            min_range=4.0,
            interval=5.0,
            damage=stats.get(name, lvl, "Damage per Hit", "Damage per Shot"),
            extra={"splash": 1.5},
        )
    elif key == "xbow":
        both = b.mode == "both"
        b.weapon = W(b, "single", targets="both" if both else "ground", range_=11.5 if both else 14.0, interval=0.128, damage=_dmg(name, lvl, 0.128))
    elif key == "tesla":
        b.weapon = W(b, "single", range_=7.0, interval=0.6, damage=_dmg(name, lvl, 0.6), extra={"trigger": 6.0})
    elif key == "inferno":
        if b.mode == "multi":
            # Wiki: Inferno Tower/Home Village lists the beam count per level.
            dps = stats.get(name, lvl, "Damage per Second per Target", default=120.0)
            b.weapon = W(
                b,
                "inferno_multi",
                range_=10.0,
                interval=0.128,
                damage=dps * 0.128,
                extra={"targets": int(stats.get(name, lvl, "Number of Targets"))},
            )
        else:
            ramp = [
                (0.0, stats.get(name, lvl, "Damage per Second / Initial", default=120.0)),
                (1.5, stats.get(name, lvl, "Damage per Second / After 1.5s", default=260.0)),
                (5.25, stats.get(name, lvl, "Damage per Second / After 5.25s", default=2600.0)),
            ]
            b.weapon = W(b, "inferno_single", range_=9.0, interval=0.128, extra={"ramp": ramp})
    elif key == "eagle":
        b.weapon = W(b, "eagle", range_=50.0, min_range=7.0, interval=10.0, damage=stats.get(name, lvl, "Damage per Hit", default=525.0),
                     extra={"activation": 200, "shells": 3, "gap": 0.75, "shock": stats.get(name, lvl, "Shockwave Damage", default=50.0), "splash": 0.75, "shock_radius": 3.0})
    elif key == "scatter":
        # Unresolved, first shot kept instant; these fields are not modelled:
        # game data v18.200.9: Scattershot.NewTargetAttackDelay=2200 -> 2.2 s on a new target.
        # game data v18.200.9: Scattershot.CoolDownOverride=1500 -> meaning unstated.
        # Neither table nor wiki says whether the 2.2 s applies to the first
        # target only or to every new one, or how it combines with AttackSpeed
        # 3228 and the cooldown. CoolDownOverride is also set, unmodelled, on
        # Air Sweeper (4800), Eagle Artillery (6992), Monolith (750) and Super
        # Wizard Tower (700); so are Inferno Tower AlternatePickNewTargetDelay=50
        # and Air Sweeper PrepareSpeed=600. Wiki: Scattershot, "the actual
        # attack speed is just 3.2 seconds".
        b.weapon = W(b, "scatter", range_=10.0, min_range=3.0, interval=3.2, damage=stats.get(name, lvl, "Damage per Shot*", default=576.0),
                     extra={"splash_max": 420.0, "splash_min": 150.0})
        hi = stats.text(name, lvl, "Damage per Shot*")
        if hi and "-" in str(hi):
            lo_, hi_ = [stats.num(x) for x in str(hi).split("-")]
            b.weapon.damage = hi_
            b.weapon.extra["inner_min"] = lo_
        sp = stats.text(name, lvl, "Splash Damage**")
        if sp and "-" in str(sp):
            lo_, hi_ = [stats.num(x) for x in str(sp).split("-")]
            b.weapon.extra.update(splash_min=lo_, splash_max=hi_)
    elif key == "mono":
        b.weapon = W(b, "monolith", range_=11.0, interval=1.5, damage=stats.get(name, lvl, "Base Damage per Shot", default=289.5),
                     extra={"pct": stats.get(name, lvl, "Bonus Damage per Shot", default=13.0) / 100.0})
    elif key == "sweeper":
        b.weapon = W(b, "sweeper", targets="air", range_=15.0, min_range=1.0, interval=5.0, extra={"push": stats.get(name, lvl, "Push Strength", default=4.0)})
        b.weapon.facing = FACINGS.get(b.mode or "E", 0.0)
    elif key == "bh":
        if lvl == 1:
            b.is_defense = False
            return
        b.weapon = W(b, "single", range_=7.0, interval=0.4, damage=_dmg(name, lvl, 0.4),
                     extra={"repair": stats.get(name, lvl, "Repair per Second", default=85.0), "repair_range": 7.0})
        b.is_defense = True
        position = (b.x, b.y)
        if battle.battle_mode == "multiplayer":
            # Wiki: Builder's Hut, Builders may start at their construction sites.
            position = battle.builder_starts.get(b.id, position)
        battle.builders.append(Builder(b, *position))
    elif key == "st":
        # Wiki: Spell Tower, per-mode infoboxes give Range 9 tiles (Rage, Poison,
        # Earthquake) and 4.5 tiles (Invisibility). Unresolved, kept at 9:
        # game data v18.200.9: Spell Tower.AttackRange=800 -> 8 tiles, matching no mode.
        # The modes are separate weapon-mode rows (UnlockWeaponMode=SpellTowerRage)
        # missing from the extracted tables, and every spell radius the wiki
        # gives matches spells.csv (Spell Tower Rage/Poison Radius=500,
        # Invisibility 450, Earthquake 470).
        b.weapon = W(b, "spell_tower", range_=9.0, interval=70.0)
        b.weapon.mode = b.mode or "rage"
        # Wiki: Spell Tower, Earthquake unlocks at level 4 and TH17.
        required = SPELL_TOWER_UNLOCKS.get(b.weapon.mode)
        if required is None or lvl < required:
            raise ValueError("Spell Tower mode is not unlocked")
        if required == 4 and battle.town_hall < 17:
            raise ValueError("Earthquake Spell Towers require Town Hall 17")
    elif key == "mgt":
        if b.mode == "long":
            b.weapon = W(b, "single", range_=12.0, interval=1.0, damage=stats.get(name, lvl, "Damage per Hit", default=390.0))
        else:
            b.weapon = W(b, "burst", range_=8.0, interval=0.383, damage=stats.get(name, lvl, "Damage per Hit**", default=170.4), extra={"shots": 4, "gap": 0.192})
    elif key == "firespitter":
        # game data v18.200.9: Firespitter.AttackSpeed=1000 -> 1 s.
        b.weapon = W(
            b,
            "firespitter",
            range_=16.0,
            interval=1.0,
            damage=stats.get(name, lvl, "Damage per Hit**", default=51.07),
            extra={"shots": 20, "gap": 0.064, "pierce": 2, "arc": math.radians(75)},
        )
        # Wiki: Firespitter, four orientations separated by 90 degrees.
        if b.mode not in (None, "N", "E", "S", "W"):
            raise ValueError("Firespitter facing must be N, E, S or W")
        b.weapon.facing = FACINGS[b.mode or "E"]
    elif key == "swt":
        # game data v18.200.9: Super Wizard Tower.ChainAttackDistance=400 -> 4 tiles.
        # game data v18.200.9: Super Wizard Tower.ChainAttackFactor=15 -> 15 chained units.
        # game data v18.200.9: Super Wizard Tower.ChainAttackDepth=1 -> every chain starts at the primary.
        # ChainAttackDelay=128 (0.128 s between chain hits) is not modelled.
        b.weapon = W(b, "super_wizard", range_=8.0, interval=1.3, damage=stats.get(name, lvl, "Damage per Hit (Primary)", default=416.0),
                     extra={"secondary": stats.get(name, lvl, "Damage per Hit (Secondary)", default=166.4), "chain": 15, "chain_range": 4.0})
    elif key == "revenge":
        b.weapon = W(b, "revenge", range_=11.0, interval=1.2, damage=stats.get(name, lvl, "Damage per Shot", default=500.0))
    elif key == "crafting":
        _attach_crafted(battle, b)
    if key in ("at", "cannon", "mortar"):
        _gear_up(battle, b)
    if key in AMMUNITION:
        capacity = AMMUNITION[key]
        rounds = battle.defense_ammo.get(b.id, battle.defense_ammo.get(key, capacity))
        if not isinstance(rounds, int) or not 0 <= rounds <= capacity:
            raise ValueError(f"Illegal {b.name} ammunition: {rounds}")
        b.weapon.ammunition = rounds


def _artillery_damage(battle):
    level = battle.defense_levels.get("th:weapon", 5)
    if level not in range(1, len(ARTILLERY_DAMAGE) + 1):
        raise ValueError("Inferno Artillery level must be between 1 and 5")
    return ARTILLERY_DAMAGE[level - 1]


def _gear_up(battle, b):
    if b.mode in (None, "normal"):
        return
    if b.mode not in ("geared", "burst", "fast"):
        raise ValueError(f"Unknown {b.name} mode: {b.mode}")
    minimum = GEAR_MINIMUM[b.key]
    if not isinstance(b.level, int):
        # Mortar's geared charge tables disagree about the required Town Hall.
        raise ValueError("Geared Mortar supercharge eligibility is unresolved")
    if b.level < minimum:
        raise ValueError(f"{b.name} is below its gear-up level")
    w = b.weapon
    if b.key == "at":
        w.range, w.interval, w.damage = 8.0, 0.25, FAST_ARCHER_SHOTS[b.level - minimum]
    elif b.key == "cannon":
        w.kind, w.range, w.interval = "burst", 7.0, 1.6
        w.damage = stats.get(b.name, b.level, "Damage per Hit**")
        w.extra.update(shots=4, gap=0.192)
    else:
        w.kind, w.interval = "mortar_burst", 4.0
        w.damage = stats.get(b.name, b.level, "Damage per Shot")
        w.extra.update(shots=3, gap=0.5)


def reveal_tesla(battle, b):
    if b.revealed or not b.alive:
        return
    b.revealed = True
    for unit in battle.attackers:
        unit.target = unit.wall_target = None
        unit.target_kind = None
        unit.extra.pop("next_engage", None)
    # Wiki: Hidden Tesla/Home Village, residual spell coverage survives reveal.
    for field in battle.fields:
        if not field.started <= battle.t < field.until:
            continue
        if b.edge_distance(field.x, field.y) > field.radius:
            continue
        if field.kind == "tesla_freeze":
            b.frozen_until = max(b.frozen_until, field.until)
        elif field.kind == "tesla_overgrowth":
            b.overgrown_until = max(b.overgrown_until, field.until)


def on_destroyed(battle, b: Building):
    if b.name == "Hero Bell":
        bell_tick(battle)
    w = b.weapon
    if w is None or b.extra.get("unavailable"):
        return
    if w.kind == "spell_tower" and w.cooldown <= 0:
        from . import spells

        near = _tower_candidates(battle, w)
        spells.tower_cast(battle, b, w.mode, near)
        w.cooldown = 70.0 if w.mode in ("rage", "poison") else 50.0
        w.extra.pop("trigger", None)
    if w.kind == "giga_inferno":
        g = w.extra
        battle.add_pending(
            Pending(
                battle.t + 1.0,
                b.x,
                b.y,
                g["death_radius"],
                g["death"],
                True,
                True,
                "th_death",
                actor=b,
                effect="death",
                extra={
                    "poison": {
                        "dps": g["poison_dps"],
                        "time": g["poison_time"],
                        "slow": g["slow"],
                        "radius": g["death_radius"],
                    }
                },
            )
        )
    elif b.key == "bt":
        battle.add_pending(
            Pending(
                battle.t + w.extra["death_delay"],
                b.x,
                b.y,
                w.extra["death_radius"],
                w.extra["death"],
                False,
                True,
                "bt_death",
                actor=b,
                effect="death",
            )
        )


def _visible(battle, w: Weapon, r: float):
    b = w.owner
    t = battle.t
    out = []
    for a in battle.attackers_near(b.x, b.y, r):
        if not a.targetable(t):
            continue
        if a.name != "Totem":
            if a.flying:
                if w.targets == "ground":
                    continue
            elif w.targets == "air":
                continue
        if w.min_range and dist(a.x, a.y, b.x, b.y) < w.min_range:
            continue
        out.append(a)
    return out


def _rage(battle, b):
    return b.rage_mult if battle.t < b.rage_until else 1.0


def _slow(battle, b):
    return effects.slow_mult(b, battle.t)


def act(battle, w: Weapon):
    b = w.owner
    t = battle.t
    dt = battle.DT
    if w.kind == "bh_repair_only":
        return
    if b.key == "tesla" and not b.revealed:
        if any(
            a.name != "Totem" and not a.underground
            for a in battle.attackers_near(b.x, b.y, w.extra["trigger"])
        ):
            reveal_tesla(battle, b)
        else:
            return
    if b.extra.get("unavailable") or w.ammunition == 0:
        return
    if t < b.stun_until and w.kind == "monolith":
        w.target = None
    if b.disabled(t):
        w.lock_time = 0.0
        if w.kind != "eagle":
            w.burst_left = 0
        return
    if w.kind == "giga_inferno" and not battle.th_active:
        return
    # cooldowns carry their remainder so intervals that are not multiples of
    # the tick (X-Bow 0.128 s, Firespitter 0.064 s) keep their true rate
    w.cooldown = max(w.cooldown - dt * _slow(battle, b), -dt)
    for _ in range(12):
        before = w.cooldown
        _act_once(battle, w)
        if w.ammunition == 0 or w.cooldown > 0 or w.cooldown == before:
            break


def _act_once(battle, w: Weapon):
    b = w.owner
    t = battle.t
    dt = battle.DT
    k = w.kind
    if k == "hook":
        if w.cooldown > 0:
            return
        candidates = _visible(battle, w, w.range)
        if not candidates:
            return
        target = min(candidates, key=lambda unit: dist(b.x, b.y, unit.x, unit.y))
        # Wiki: Hook Tower damages and stuns sieges without reeling them. Reeling
        # other units in is not modelled (its pull numbers are not stated), so
        # they take the hit and the stun only.
        battle.hit_unit(target, w.damage)
        target.stun_until = max(target.stun_until, t + w.extra["stun"])
        w.cooldown += w.interval
        return
    if k == "eagle":
        return _eagle(battle, w)
    if k == "sweeper":
        return _sweeper(battle, w)
    if k == "spell_tower":
        return _spell_tower(battle, w)
    rage = _rage(battle, b)
    if k == "candle":
        # Wiki: Hot Candle, August 31 history uses deployment; summary conflicts.
        first = battle.first_deploy_t
        if first is not None:
            active = battle.t - first
            w.extra["targets"] = 6 if active < w.extra["melt1"] else 4 if active < w.extra["melt2"] else 3
        return _multi(battle, w, rage)
    if k == "cake":
        return _cake(battle, w, rage)
    if k in ("multi_archer", "inferno_multi", "giga_inferno"):
        return _multi(battle, w, rage)
    if k == "inferno_artillery":
        return _inferno_artillery(battle, w, rage)
    if k == "super_wizard":
        return _super_wizard(battle, w, rage)
    if k == "firespitter":
        return _firespitter(battle, w, rage)
    # single-target families keep their target while valid
    tgt = w.target
    if tgt is not None:
        d = dist(tgt.x, tgt.y, b.x, b.y)
        if not tgt.alive or not tgt.targetable(t) or d > w.range or d < w.min_range:
            tgt = None
            w.lock_time = 0.0
    if tgt is None:
        if t < w.idle_until:
            return
        pool = _visible(battle, w, w.range)
        if not pool:
            w.idle_until = t + 0.25
            return
        if k == "hunter" and any(a.is_hero for a in pool):
            pool = [a for a in pool if a.is_hero]  # prioritises heroes (wiki)
        tgt = min(pool, key=lambda a: dist(a.x, a.y, b.x, b.y))
        w.target = tgt
        w.lock_time = 0.0
    if k == "inferno_single":
        w.lock_time += dt
        dps = 0.0
        for start, value in w.extra["ramp"]:
            if w.lock_time >= start:
                dps = value
        duration = dt * _slow(battle, b)
        if w.ammunition is not None:
            duration = min(duration, w.ammunition * w.interval - w.ammo_time)
        battle.hit_unit(tgt, dps * duration * rage)
        w.ammo_time += duration
        # Wiki: Inferno Tower, one round per 0.128 seconds at every charge stage.
        while w.ammo_time + 1e-9 >= w.interval:
            w.ammo_time -= w.interval
            w.ammunition -= 1
        return
    if w.cooldown > 0:
        return
    if k == "burst":
        if w.burst_left <= 0:
            w.burst_left = w.extra["shots"]
        if b.key == "mgt":
            # game data v18.200.9: merged_cat_cannon_projectile_lvl1.Speed=1200 -> 12 tiles/s.
            _projectile(battle, w, tgt, w.damage * rage, 12.0)
        elif b.key == "cannon":
            # game data v18.200.9: Cannonball16.Speed=1200, StartOffset=76
            # -> 12 tiles/s from 0.76 tiles; DontTrackTarget=FALSE -> tracking.
            offset = GEARED_CANNON_OFFSETS[b.level - GEAR_MINIMUM["cannon"]]
            _projectile(battle, w, tgt, w.damage * rage, 12.0, offset=offset)
        else:
            battle.hit_unit(tgt, w.damage * rage)
        w.burst_left -= 1
        w.cooldown += w.extra["gap"] if w.burst_left > 0 else w.interval
        return
    if k == "mortar_burst":
        if w.burst_left <= 0:
            w.burst_left = w.extra["shots"]
        _mortar_shell(battle, w, tgt, w.damage * rage)
        w.burst_left -= 1
        w.cooldown += w.extra["gap"] if w.burst_left else w.interval
        return
    if k == "revenge":
        _revenge(battle, w, tgt, rage)
        return
    w.cooldown += w.interval
    if w.ammunition is not None:
        w.ammunition -= 1
    dmg = w.damage * rage
    if k == "single":
        if b.key == "cannon":
            # game data v18.200.9: Cannonball.Speed=1200 -> 12 tiles/s.
            _projectile(battle, w, tgt, dmg, 12.0)
        elif b.key == "at":
            # game data v18.200.9: Tower Arrow.Speed=1800 -> 18 tiles/s.
            _projectile(battle, w, tgt, dmg, 18.0)
        elif b.key == "ad":
            # game data v18.200.9: Firework.Speed=800 -> 8 tiles/s.
            _projectile(battle, w, tgt, dmg, 8.0)
        elif b.key == "mgt":
            # game data v18.200.9: merged_cat_archer_projectile_lvl2.Speed=800,
            # StartOffset=150 -> 8 tiles/s from 1.5 tiles; DontTrackTarget=FALSE.
            _projectile(battle, w, tgt, dmg, 8.0, offset=1.5)
        else:
            battle.hit_unit(tgt, dmg)
    elif k == "monolith":
        # rage tower boosts only the base damage (wiki)
        # league modifiers do not boost the percentage bonus (wiki)
        battle.hit_unit(tgt, dmg + w.extra["pct"] * tgt.max_hp / battle.def_mult)
    elif k == "ricochet":
        battle.hit_unit(tgt, dmg)
        best, bd = None, w.extra["bounce_range"]
        for a in battle.attackers_near(tgt.x, tgt.y, bd):
            if a is not tgt and not a.flying and a.indirect_targetable(t):
                d = dist(a.x, a.y, tgt.x, tgt.y)
                if d <= bd:
                    bd, best = d, a
        if best is not None:
            battle.hit_unit(best, w.extra["bounce"] * rage)
    elif k == "splash":
        # Wizard Tower damages only the target's type; Bomb Tower ground only
        air = tgt.flying if w.extra.get("same_type") else w.targets in ("air", "both")
        ground = (not tgt.flying) if w.extra.get("same_type") else w.targets in ("ground", "both")
        if b.key == "wt":
            if b.level <= 4:
                # game data v18.200.9: wizardTower_projectile.Speed=500 -> 5 tiles/s.
                flight = dist(b.x, b.y, tgt.x, tgt.y) / 5.0
            else:
                # game data v18.200.9: ps_chr_WizardAttack_TowerProjectile_lvl2/3/4:
                # Speed=900, StartOffset=70 -> 9 tiles/s from 0.7 tiles;
                # DontTrackTarget=TRUE -> impact at the launch-time position.
                flight = max(0.0, dist(b.x, b.y, tgt.x, tgt.y) - 0.7) / 9.0
            battle.add_pending(
                Pending(
                    t + flight,
                    tgt.x,
                    tgt.y,
                    w.extra["splash"],
                    dmg,
                    air,
                    ground,
                    "wizard_tower",
                )
            )
        elif b.key == "bt":
            # game data v18.200.9: Bomb Tower Ammo1.Speed=800 -> 8 tiles/s.
            battle.add_pending(
                Pending(
                    t + dist(b.x, b.y, tgt.x, tgt.y) / 8.0,
                    tgt.x,
                    tgt.y,
                    w.extra["splash"],
                    dmg,
                    air,
                    ground,
                    "bt",
                )
            )
        else:
            battle.splash_units(tgt.x, tgt.y, w.extra["splash"], dmg, air, ground)
    elif k == "mortar":
        _mortar_shell(battle, w, tgt, dmg)
    elif k == "scatter":
        _scatter(battle, w, tgt, dmg, rage)
    elif k == "hunter":
        _hunter_hit(battle, w, tgt, rage)


def _projectile(battle, w, target, damage, speed, *, offset=0.0):
    flight = max(0.0, dist(w.owner.x, w.owner.y, target.x, target.y) - offset) / speed
    battle.add_pending(
        Pending(
            battle.t + flight,
            target.x,
            target.y,
            0.0,
            damage,
            target.flying,
            not target.flying,
            w.owner.key,
            extra={"direct": True},
            target=target,
        )
    )


def _mortar_shell(battle, w, target, damage):
    # game data v18.200.9: every Mortar level's Mortar Ammo projectile row has
    # Speed=500, StartOffset=20 -> 5 tiles/s from 0.2 tiles; FixedTravelTime=0,
    # DontTrackTarget=TRUE -> distance-based flight to the launch-time position.
    flight = max(0.0, dist(w.owner.x, w.owner.y, target.x, target.y) - 0.2) / 5.0
    battle.add_pending(
        Pending(
            battle.t + flight,
            target.x,
            target.y,
            w.extra["splash"],
            damage,
            False,
            True,
            "mortar",
            falloff=True,
            extra={"origin": (w.owner.x, w.owner.y)},
        )
    )


def _multi(battle, w: Weapon, rage):
    b = w.owner
    t = battle.t
    if w.cooldown > 0:
        return
    if w.kind == "multi_archer":
        n = 3
    elif w.kind == "giga_inferno":
        n = w.extra["targets"]
    else:
        n = w.extra["targets"]
    if w.kind == "candle":
        # Wiki: Hot Candle, all flames go to the nearest available targets.
        keep = sorted(
            _visible(battle, w, w.range),
            key=lambda a: (dist(a.x, a.y, b.x, b.y), a.spawned_at, a.id),
        )[:n]
    else:
        keep = [
            a
            for a in w.multi
            if a.alive and a.targetable(t) and dist(a.x, a.y, b.x, b.y) <= w.range
        ]
    if len(keep) < n:
        for a in sorted(_visible(battle, w, w.range), key=lambda a: dist(a.x, a.y, b.x, b.y)):
            if a not in keep:
                keep.append(a)
                if len(keep) >= n:
                    break
    w.multi = keep
    if not keep:
        return
    if w.kind in ("multi_archer", "candle"):
        keep.sort(key=lambda a: (dist(a.x, a.y, b.x, b.y), a.spawned_at, a.id))
        # Wiki: Multi-Archer Tower and Hot Candle, concentrate unused shots.
        arrows = [keep[i % len(keep)] for i in range(n)]
        if w.kind == "multi_archer" and len(keep) == 2:
            # Wiki: Multi-Archer Tower, the spare archer alternates between two
            # nearby targets. Proximity cutoff is unstated; alternate this pair.
            previous = w.extra.get("spare_target")
            spare = keep[1] if previous is keep[0] else keep[0]
            arrows[-1] = spare
            w.extra["spare_target"] = spare
        for a in arrows:
            if w.kind == "multi_archer":
                # game data v18.200.9: super_archer_tower_projectile.Speed=1800 -> 18 tiles/s.
                _projectile(battle, w, a, w.damage * rage, 18.0)
            else:
                battle.hit_unit(a, w.damage * rage)
        w.cooldown += w.interval
        return
    dmg = w.damage * rage
    if w.ammunition is not None:
        w.ammunition -= 1
    for a in keep:
        battle.hit_unit(a, dmg)
    w.cooldown += w.interval


def _cake(battle, w, rage):
    if w.cooldown > 0:
        return
    b = w.owner
    pool = _visible(battle, w, w.range)
    if not pool:
        return
    tgt = min(pool, key=lambda a: dist(a.x, a.y, b.x, b.y))
    battle.splash_units(tgt.x, tgt.y, w.extra["splash"], w.damage * rage, tgt.flying, not tgt.flying)
    battle.add_pending(Pending(battle.t + w.extra["bomb_delay"], tgt.x, tgt.y, w.extra["bomb_radius"], w.extra["bomb"] * rage, True, True, "cake"))
    w.cooldown += w.interval


def _hunter_hit(battle, w, tgt, rage):
    """Cards deal double damage to heroes and poison the target: Poison
    Spell slows at the module's spell level, damage wears off fast (wiki)."""
    battle.hit_unit(tgt, w.damage * rage * (2.0 if tgt.is_hero else 1.0))
    lvl = w.extra["poison_level"]
    slow = stats.get("Poison Spell", lvl, "Speed Decrease", default=50.0) / 100.0
    atk = stats.get("Poison Spell", lvl, "Attack Rate Decrease", default=70.0) / 100.0
    t = battle.t
    tgt.move_slow, tgt.move_slow_until = min(tgt.move_slow if t < tgt.move_slow_until else 1.0, 1.0 - slow), t + w.extra["poison_time"]
    tgt.atk_slow, tgt.atk_slow_until = min(tgt.atk_slow if t < tgt.atk_slow_until else 1.0, 1.0 - atk), t + w.extra["poison_time"]


def _scatter(battle, w, tgt, dmg, rage):
    """Primary hit plus a 90-degree cone behind the target with two falloff
    hitboxes (wiki: Scattershot, table footnotes): within 1 tile the shot's
    damage falls from the primary's maximum to the listed minimum at 1 tile;
    from 1 to 5 tiles the splash falls from its maximum to its minimum."""
    b = w.owner
    battle.hit_unit(tgt, dmg)
    ax, ay = tgt.x - b.x, tgt.y - b.y
    ang = math.atan2(ay, ax)
    smax, smin = w.extra["splash_max"] * rage, w.extra["splash_min"] * rage
    inner_min = w.extra.get("inner_min", w.extra["splash_max"]) * rage
    for a in battle.attackers_near(tgt.x, tgt.y, 5.0):
        if a is tgt or a.flying != tgt.flying or not a.alive or a.underground:
            continue
        dx, dy = a.x - tgt.x, a.y - tgt.y
        d = math.hypot(dx, dy)
        if d > 1e-6:
            off = abs((math.atan2(dy, dx) - ang + math.pi) % (2 * math.pi) - math.pi)
            if off > math.pi / 4:
                continue
        if d <= 1.0:
            # Wiki: Scattershot, "The minimum damage listed affects targets
            # 1 tile behind the point of impact" (Damage per Shot* footnote).
            amt = dmg - (dmg - inner_min) * d
        else:
            amt = smax - (smax - smin) * (d - 1.0) / 4.0
        battle.hit_unit(a, amt)


def _eagle(battle, w: Weapon):
    if battle.deployed_housing < w.extra["activation"] or w.cooldown > 0:
        return
    b = w.owner
    # game data v18.200.9: Eagle Artillery.WakeUpSpeed=1125 -> 1.125 s.
    ready_at = w.extra.setdefault("wake_at", battle.t + 1.125)
    if battle.t < ready_at:
        return
    if w.burst_left <= 0:
        pool = [
            unit for unit in _visible(battle, w, w.range) if unit.name != "Yetimite"
        ]
        if not pool:
            return
        # Wiki: Eagle Artillery, it "recalculates its targets each volley".
        w.target = _eagle_pick(battle, w, pool)
        w.burst_left = w.extra["shells"]
    target = w.target
    if target is None or not target.alive:
        # the burst's target was cleared mid-burst (Totem or Invisibility
        # retargeting, or it died): pick again by group weight, or stop
        pool = [unit for unit in _visible(battle, w, w.range) if unit.name != "Yetimite"]
        if not pool:
            w.burst_left = 0
            return
        w.target = target = _eagle_pick(battle, w, pool)
    # Launch only the current shell; disabling the tower pauses later launches.
    # game data v18.200.9: Artillery Ammo7.FixedTravelTime=5000 -> 5 s.
    # Wiki: Eagle Artillery, Damage per Hit and Shockwave Damage are separate.
    for radius, damage, shock in (
        (w.extra["splash"], w.damage, False),
        (w.extra["shock_radius"], w.extra["shock"], True),
    ):
        battle.add_pending(
            Pending(
                battle.t + 5.0,
                target.x,
                target.y,
                radius,
                damage * _rage(battle, b),
                True,
                True,
                "eagle",
                extra={
                    "track": target,
                    "origin": (b.x, b.y),
                    "min_range": w.min_range,
                    "max_range": w.range,
                    # game data v18.200.9: Eagle Artillery.Pushback=50 -> 0.5 tiles.
                    "push": 0.5 if shock else 0.0,
                    # game data v18.200.9: Eagle Artillery.PushbackHousingLimit=3 -> 3 housing spaces.
                    "push_housing": 3,
                },
            )
        )
    if w.ammunition is not None:
        w.ammunition -= 1
    w.burst_left -= 1
    # Wiki: Eagle Artillery, 0.75-second launch gaps then 10 seconds.
    w.cooldown += w.extra["gap"] if w.burst_left else w.interval


def _sweeper(battle, w: Weapon):
    if w.cooldown > 0:
        return
    b = w.owner
    # swivels up to 45 degrees either side; the puff covers ~10 degrees (wiki)
    # Unresolved, kept: the wiki gives a 10, 30 or 60 degree puff (Air Sweeper
    # page, three places) and a 90 or 120 degree sector.
    # game data v18.200.9: Air Sweeper.ShockwaveArcLength=700 -> 7 tiles of arc (angle depends on distance).
    # game data v18.200.9: Air Sweeper.ShockwaveExpandRadius=250 -> meaning unstated.
    # game data v18.200.9: Air Sweeper.TargetingConeAngle=105 -> 105 degrees of targeting cone.
    # Read as 7 tiles of arc at 14-15 tiles, that is about 27-29 degrees (the
    # wiki's "30-degree angle"), but whether the arc stays 7 tiles as the wave
    # expands (so wider near the Sweeper) is not stated.
    cands = []
    for a in battle.attackers_near(b.x, b.y, w.range):
        if not a.flying or a.name == "Totem" or not a.targetable(battle.t):
            continue
        d = dist(a.x, a.y, b.x, b.y)
        if d < w.min_range:
            continue
        ang = math.atan2(a.y - b.y, a.x - b.x)
        # game data v18.200.9: Air Sweeper.TargetingConeAngle=105 -> +-52.5 degrees
        # (the wiki's 90, 120 and 60 degree descriptions conflict).
        if abs((ang - w.facing + math.pi) % (2 * math.pi) - math.pi) <= math.radians(52.5):
            cands.append((d, ang, a))
    if not cands:
        return
    _, aim, _ = min(cands, key=lambda c: c[0])  # ties must not compare units
    push = w.extra["push"]
    for a in battle.attackers_near(b.x, b.y, w.range):
        if not a.flying or a.name == "Totem":
            continue
        ang = math.atan2(a.y - b.y, a.x - b.x)
        if abs((ang - aim + math.pi) % (2 * math.pi) - math.pi) <= math.radians(5):
            battle._nudge(a, math.cos(ang) * push, math.sin(ang) * push)
            a.extra["pushed_at"] = battle.t
            # Wiki: Air Sweeper, knockback resets Inferno Dragon's charge.
            from . import units

            units.reset_beam(a)
    w.cooldown += w.interval


def _tower_candidates(battle, w):
    from . import spells

    # Wiki: Spell Tower, Offensive Strategies: a Skeleton Spell can trigger Poison.
    return [
        unit
        for unit in _visible(battle, w, w.range)
        if (
            unit.name not in spells.NO_TRIGGER
            or (w.mode == "poison" and unit.name == "Spell Skeleton")
        )
        and (w.mode not in ("eq", "quake", "earthquake") or not unit.flying)
    ]


def _spell_tower(battle, w: Weapon):
    from . import spells

    if w.cooldown > 0:
        return
    t = battle.t
    trigger = w.extra.get("trigger")
    if w.mode == "invis":
        triggers = {
            unit: since
            for unit, since in w.extra.get("hit_triggers", {}).items()
            if unit.alive
        }
        w.extra["hit_triggers"] = triggers
        if not triggers:
            return
        unit = min(triggers, key=triggers.get)
        since = triggers[unit]
    else:
        near = _tower_candidates(battle, w)
        if trigger is None or trigger[0] not in near:
            w.extra.pop("trigger", None)
            if near:
                w.extra["trigger"] = (near[0], t)
            return
        unit, since = trigger
    if t - since < 1.2:  # Wiki: Spell Tower, continuous activation time.
        return
    spells.tower_cast(battle, w.owner, w.mode, [unit])
    w.extra.pop("trigger", None)
    w.extra.pop("hit_triggers", None)
    w.cooldown += 70.0 if w.mode in ("rage", "poison") else 50.0


@dataclass
class Builder:
    owner: Building
    x: float
    y: float
    target: Building | None = None
    cooldown: float = 0.0
    frozen_until: float = 0.0
    stun_until: float = 0.0
    repair_slow: float = 1.0
    slow_until: float = 0.0
    rage_until: float = 0.0
    rage_speed: float = 0.0
    repair_boost: float = 1.0


def builder_spell(battle, field):
    t = battle.t
    for builder in battle.builders:
        if not builder.owner.alive:
            continue
        if dist(builder.x, builder.y, field.x, field.y) > field.radius:
            continue
        if field.kind == "tesla_freeze":
            builder.frozen_until = max(builder.frozen_until, field.until)
        elif field.kind == "freeze":
            builder.frozen_until = max(builder.frozen_until, t + field.value)
        elif field.kind == "poison":
            builder.repair_slow = 1.0 - field.extra["atk"]
            builder.slow_until = min(field.until, t + battle.DT)
        elif field.kind in ("lightning", "totem"):
            builder.target = None
            if field.kind == "lightning":
                # game data v18.200.9: Lightning.StunTimeMS=100 -> 0.1 s.
                duration = 0.1
            else:
                # game data v18.200.9: Totem.StunTimeMS=200 -> 0.2 s.
                duration = 0.2
            builder.stun_until = max(builder.stun_until, t + duration)
        elif field.kind == "def_rage" or (field.kind == "rage" and field.team == "def"):
            # Wiki: Spell Tower; Builder repair doubles without faster attacks.
            builder.repair_boost = 2.0
            builder.rage_speed = field.extra.get("speed", 30.0 / 8.0)
            builder.rage_until = min(field.until, t + battle.DT)


def builders_tick(battle):
    groups = {}
    t = battle.t
    for builder in battle.builders:
        b = builder.owner
        if not b.alive or b.extra.get("unavailable"):
            continue
        target = builder.target

        def available(other):
            return (
                other.alive
                and other.counted
                and other.hp < other.max_hp
                and t >= other.invisible_until
                and t >= other.overgrown_until
                and dist(other.x, other.y, b.x, b.y) <= b.weapon.extra["repair_range"]
            )

        if target is None or not available(target):
            pool = [other for other in battle.buildings if available(other)]
            # Initial selection priority is unstated; retain the existing heuristic.
            target = min(pool, key=lambda other: other.hp / other.max_hp, default=None)
            builder.target = target
        if target is None or t < max(builder.frozen_until, builder.stun_until):
            continue
        # Wiki: Builder's Hut, display speed 20 and a 0.75-second repair interval.
        speed = stats.attrs(b.name)["speed_display"] / 8.0
        boost = builder.repair_boost if t < builder.rage_until else 1.0
        if t < builder.rage_until:
            speed += builder.rage_speed
        # game data v18.200.9: Defending Builder.AttackRange=50 -> 0.5 tiles.
        # Keep the existing center-distance convention.
        reach = 0.5
        distance = dist(builder.x, builder.y, target.x, target.y)
        if distance > reach:
            step = min(speed * battle.DT, distance - reach)
            builder.x += (target.x - builder.x) * step / distance
            builder.y += (target.y - builder.y) * step / distance
            if distance - step > reach:
                continue
        slow = builder.repair_slow if t < builder.slow_until else 1.0
        builder.cooldown = max(builder.cooldown - battle.DT * slow, -battle.DT)
        groups.setdefault(target, []).append((builder, boost))
    for target, builders in groups.items():
        # Wiki: Builder's Hut, marginal repair effectiveness for five Builders.
        weights = (1.0, 1.0, 0.9, 0.9, 0.7)
        amounts = [
            stats.get(builder.owner.name, builder.owner.level, "Repair per Hit") * boost
            for builder, boost in builders
        ]
        # Wiki: Builder's Hut, unequal hut levels also lose repair output;
        # which Builder gets the reduction matters. The order is unstated,
        # so assign the existing marginal weights in battle.builders order.
        for index, ((builder, _), amount) in enumerate(zip(builders, amounts)):
            efficiency = weights[min(index, len(weights) - 1)]
            if builder.cooldown <= 0:
                target.hp = min(target.max_hp, target.hp + amount * efficiency)
                builder.cooldown += 0.75


def _inferno_artillery(battle, w, rage):
    if w.cooldown > 0:
        return
    b = w.owner
    pool = sorted(_visible(battle, w, w.range), key=lambda a: dist(a.x, a.y, b.x, b.y))[: w.extra["targets"]]
    if not pool:
        return
    from .entities import Field

    # Wiki: Town Hall/Inferno Artillery, distribute four single-target projectiles.
    for index in range(w.extra["targets"]):
        a = pool[index % len(pool)]
        battle.hit_unit(a, w.damage * rage)
        battle.fields.append(
            Field(
                "def_burn",
                a.x,
                a.y,
                w.extra["pool_radius"],
                battle.t + w.extra["pool_time"],
                team="def",
                value=w.extra["pool_dps"],
                extra={"pulses": w.extra["pool_hits"], "gap": w.extra["pool_gap"]},
                started=battle.t,
            )
        )
    w.cooldown += w.interval


def _super_wizard(battle, w, rage):
    if w.cooldown > 0:
        return
    b = w.owner
    tgt = w.target
    if tgt is not None and (
        not tgt.alive
        or not tgt.targetable(battle.t)
        or dist(tgt.x, tgt.y, b.x, b.y) > w.range
    ):
        tgt = None
    if tgt is None:
        pool = _visible(battle, w, w.range)
        if not pool:
            w.target = None
            return
        # game data v18.200.9: Super Wizard Tower.RandomizeTarget=TRUE -> a new
        # target is drawn at random from the units in range (uniform: no
        # weighting is stated); it is kept while valid like other defenses.
        pool.sort(key=lambda a: a.id)
        tgt = w.target = battle.rng.choice(pool)
    battle.hit_unit(tgt, w.damage * rage)
    hit = {tgt.id}
    for _ in range(w.extra["chain"]):
        nxt, nd = None, w.extra["chain_range"]
        for a in battle.attackers_near(tgt.x, tgt.y, nd):
            if a.id not in hit and a.indirect_targetable(battle.t):
                d = dist(a.x, a.y, tgt.x, tgt.y)
                if d <= nd:
                    nd, nxt = d, a
        if nxt is None:
            break
        hit.add(nxt.id)
        battle.hit_unit(nxt, w.extra["secondary"] * rage)
    w.cooldown += w.interval


def _firespitter(battle, w, rage):
    b = w.owner
    t = battle.t
    if w.cooldown > 0:
        return
    tgt = w.target
    arc = w.extra["arc"]
    in_sector = (
        tgt is not None
        and abs(
            (math.atan2(tgt.y - b.y, tgt.x - b.x) - w.facing + math.pi) % (2 * math.pi)
            - math.pi
        )
        <= arc
    )
    if (
        tgt is None
        or not tgt.alive
        or not tgt.targetable(t)
        or dist(tgt.x, tgt.y, b.x, b.y) > w.range
        or not in_sector
    ):
        w.burst_left = 0
        cands = []
        for a in _visible(battle, w, w.range):
            ang = math.atan2(a.y - b.y, a.x - b.x)
            if abs((ang - w.facing + math.pi) % (2 * math.pi) - math.pi) <= arc:
                cands.append((dist(a.x, a.y, b.x, b.y), a))
        if not cands:
            return
        tgt = min(cands, key=lambda c: c[0])[1]
        w.target = tgt
    if w.burst_left <= 0:
        w.burst_left = w.extra["shots"]
    # Each ball flies in a straight line through the target and hits the
    # first two units on its path, in path order, so a unit in front of the
    # target is hit first (and two in front spare the target).
    # game data v18.200.9: Firespitter.PenetratingProjectile=TRUE -> the ball passes through units.
    # game data v18.200.9: GatlingGunAmmo.MaxHitObjects=2 -> two units per ball (also wiki: Firespitter).
    # game data v18.200.9: Firespitter.PenetratingRadius=50 -> units within 0.5 tiles of the line.
    # game data v18.200.9: GatlingGunAmmo.Speed=2000 -> 20 tiles/s.
    # game data v18.200.9: GatlingGunAmmo.StartOffset=170 -> 1.7 tiles.
    # Unresolved, kept: the reach past the target stays 2 tiles, because
    # game data v18.200.9: Firespitter.PenetratingExtraRange=100 -> 1 tile past the target or past the range.
    # GatlingGunAmmo TargetPosRandomRadius=768 (aim scatter, unit unclear) is
    # not modelled.
    length = dist(tgt.x, tgt.y, b.x, b.y)
    ux, uy = (tgt.x - b.x) / max(length, 1e-9), (tgt.y - b.y) / max(length, 1e-9)
    path = [(length, tgt.id, tgt)]
    for a in battle.attackers_near(b.x, b.y, length + 2.0):
        if a is tgt or not a.indirect_targetable(t):
            continue
        along = (a.x - b.x) * ux + (a.y - b.y) * uy
        if not 1.7 <= along <= length + 2.0:
            continue
        if abs((a.x - b.x) * uy - (a.y - b.y) * ux) > 0.5:
            continue
        path.append((along, a.id, a))
    for _, _, a in sorted(path, key=lambda p: p[:2])[:2]:
        _projectile(battle, w, a, w.damage * rage, 20.0, offset=1.7)
    w.burst_left -= 1
    w.cooldown += w.extra["gap"] if w.burst_left > 0 else w.interval


def _revenge(battle, w, tgt, rage):
    # Wiki: Revenge Tower, stages after 5, 25 and 50 destroyed buildings.
    destroyed = battle.destroyed_counted
    if destroyed < 5:
        return
    stage = 3 if destroyed >= 50 else 2 if destroyed >= 25 else 1
    if stage == 1:
        battle.hit_unit(tgt, w.damage * rage)
        w.cooldown += 1.2
        return
    columns = (
        "Damage per Shot (Primary)",
        "Damage per Shot (Secondary)",
        "Damage per Shot (Tertiary)",
    )
    current, hit = tgt, {tgt.id}
    battle.hit_unit(tgt, stats.get(w.owner.name, w.owner.level, columns[0]) * rage)
    for column in columns[1:stage]:
        next_target = next(
            (
                unit
                for unit in battle.attackers_near(current.x, current.y, 2.0)
                if unit.id not in hit and unit.indirect_targetable(battle.t)
            ),
            None,
        )
        if next_target is None:
            break
        battle.hit_unit(
            next_target, stats.get(w.owner.name, w.owner.level, column) * rage
        )
        hit.add(next_target.id)
        current = next_target
    w.cooldown += 0.6 if stage == 2 else 0.35


def bell_tick(battle):
    # game data v18.200.9: HeroBoosterAttackAbility.ActiveAfterTime=2200 -> 2.2 s.
    # game data v18.200.9: HeroBoosterEffectAbility.ActiveAfterTime=2200 -> 2.2 s.
    bells = [
        b
        for b in battle.buildings
        if b.alive and b.name == "Hero Bell" and battle.t >= 2.2
    ]
    for hero in battle.defenders:
        if not hero.alive or not hero.is_hero:
            continue
        damage_boost = health_boost = 0.0
        for bell in bells:
            if dist(hero.x, hero.y, bell.x, bell.y) > stats.attrs("Hero Bell")["range"]:
                continue
            # Module percentages and radius (wiki: Hero Bell).
            damage_level = battle.defense_levels.get("crafting:damage", bell.level)
            health_level = battle.defense_levels.get("crafting:health", bell.level)
            damage_boost = max(
                damage_boost,
                stats.get("Hero Bell", damage_level, "Hero DPS Boost") / 100.0,
            )
            health_boost = max(
                health_boost,
                stats.get("Hero Bell", health_level, "Hero HP Boost") / 100.0,
            )
        previous = hero.extra.get("bell_health", 1.0)
        multiplier = 1.0 + health_boost
        hero.hp *= multiplier / previous
        hero.max_hp *= multiplier / previous
        hero.extra["bell_health"] = multiplier
        if damage_boost:
            # game data v18.200.9: SeasonalDefenseHeroBoosterRageAura.BoostTimeMS=1000 -> 1 s.
            hero.extra["bell_damage"] = 1.0 + damage_boost
            hero.extra["bell_damage_until"] = battle.t + 1.0
        elif battle.t >= hero.extra.get("bell_damage_until", 0.0):
            hero.extra["bell_damage"] = 1.0
