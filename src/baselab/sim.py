"""Fixed-step battle simulation.

One ``Battle`` runs one attack of an ``AttackPlan`` (armies.py) against one
``Layout`` and returns stars, destruction and a compact event summary. The model
is deliberately simple where the game is subtle; see mechanics.py for every
behavioural assumption.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from . import gamedata, hero_kit
from .layout import Layout
from .mechanics import (
    BEHAVIORS,
    BUILDING_TYPES,
    CC_TRIGGER_RADIUS,
    ENGAGE_RADIUS,
    EXTRA_UNITS,
    HERO_NAMES,
    MARGIN,
    SPELL_TOWER_MODES,
    TRAP_NAMES,
    WALL_PATH_COST,
    WORLD,
    Behavior,
    weapon_spec,
)
from .pathing import RES, Grid

DT = 0.1
MAX_TIME = 180.0
BUCKET = 4.0


def _dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


# ==========================================================================
# Entities
# ==========================================================================


class Building:
    __slots__ = (
        "id",
        "key",
        "kind",
        "x",
        "y",
        "size",
        "half_hit",
        "hp",
        "max_hp",
        "alive",
        "counted",
        "is_defense",
        "weapon",
        "mode",
        "frozen_until",
        "overgrown_until",
        "invisible_until",
        "rage_until",
        "rage_mult",
        "revealed",
    )

    def __init__(self, bid, key, x, y, size, hitbox, hp, mode):
        bt = BUILDING_TYPES[key]
        self.id = bid
        self.key = key
        self.kind = bt.kind
        self.size = size
        self.x = x + size / 2.0
        self.y = y + size / 2.0
        self.half_hit = hitbox / 2.0
        self.hp = hp
        self.max_hp = hp
        self.alive = True
        self.counted = bt.counted
        self.is_defense = bt.kind == "defense" or key == "th"
        self.weapon = None
        self.mode = mode
        self.frozen_until = 0.0
        self.overgrown_until = 0.0
        self.invisible_until = 0.0
        self.rage_until = 0.0
        self.rage_mult = 1.0
        self.revealed = True

    def edge_distance(self, x, y):
        dx = abs(x - self.x) - self.half_hit
        dy = abs(y - self.y) - self.half_hit
        dx = dx if dx > 0 else 0.0
        dy = dy if dy > 0 else 0.0
        return math.hypot(dx, dy)

    def disabled(self, t):
        return t < self.frozen_until or t < self.overgrown_until


class Wall:
    __slots__ = ("tx", "ty", "x", "y", "hp", "alive", "half_hit")

    def __init__(self, tx, ty, hp):
        self.tx = tx
        self.ty = ty
        self.x = tx + 0.5
        self.y = ty + 0.5
        self.hp = hp
        self.alive = True
        self.half_hit = 0.5

    def edge_distance(self, x, y):
        dx = max(0.0, abs(x - self.x) - 0.5)
        dy = max(0.0, abs(y - self.y) - 0.5)
        return math.hypot(dx, dy)


class Unit:
    __slots__ = (
        "id",
        "name",
        "team",
        "x",
        "y",
        "hp",
        "max_hp",
        "dps",
        "interval",
        "range",
        "speed",
        "housing",
        "flying",
        "hits_air",
        "hits_ground",
        "beh",
        "is_hero",
        "alive",
        "cooldown",
        "target",
        "target_kind",
        "wall_target",
        "group",
        "next_retarget",
        "rage_mult",
        "rage_until",
        "haste_until",
        "haste_mult",
        "slow_until",
        "slow_mult",
        "invisible_until",
        "invulnerable_until",
        "iceblock_until",
        "iceblock_red",
        "held_until",
        "ability_used",
        "ability_boost_until",
        "home",
        "leash",
        "released",
        "damage_dealt",
        "spawned_at",
        "stuck",
        "heal_rate",
        "dash_until",
        "dash_dir",
        "dashed",
        "decay",
        "dash_hit",
        "aura",
        "aura_mult",
        "aura_dmg",
        "kit",
        "follow",
        "dash_damage",
    )

    def __init__(self, uid, name, team, x, y, stats: dict, beh: Behavior, is_hero=False):
        self.id = uid
        self.name = name
        self.team = team
        self.x = x
        self.y = y
        self.hp = stats["hitpoints"]
        self.max_hp = stats["hitpoints"]
        self.dps = max(0.0, stats["dps"])
        self.heal_rate = -stats["dps"] if stats["dps"] < 0 else beh.heal_per_sec
        self.interval = stats["attack_interval"] or 1.0
        self.range = max(0.5, stats["attack_range"])
        self.speed = stats["speed"]
        self.housing = stats["housing"]
        self.flying = stats["flying"]
        self.hits_air = stats["hits_air"]
        self.hits_ground = stats["hits_ground"]
        self.beh = beh
        self.is_hero = is_hero
        self.alive = True
        self.cooldown = 0.0
        self.target = None
        self.target_kind = None
        self.wall_target = None
        self.group = "main"
        self.next_retarget = 0.0
        self.rage_mult = 1.0
        self.rage_until = 0.0
        self.haste_until = 0.0
        self.haste_mult = 1.0
        self.slow_until = 0.0
        self.slow_mult = 1.0
        self.invisible_until = 0.0
        self.invulnerable_until = 0.0
        self.iceblock_until = 0.0
        self.iceblock_red = 0.0
        self.held_until = 0.0
        self.ability_used = False
        self.ability_boost_until = 0.0
        self.home = None
        self.leash = 0.0
        self.released = True
        self.damage_dealt = 0.0
        self.spawned_at = 0.0
        self.stuck = 0.0
        self.dash_until = 0.0
        self.dash_dir = (0.0, 0.0)
        self.dashed = False
        self.decay = 0.0
        self.dash_hit = None
        self.aura = False
        self.aura_mult = 1.0
        self.aura_dmg = 1.0
        self.kit = None
        self.follow = None
        self.dash_damage = 1500.0


def unit_stats(name: str, *, town_hall: int | None = None, level: int | None = None) -> dict:
    if name in EXTRA_UNITS:
        return dict(EXTRA_UNITS[name])
    if name in HERO_NAMES:
        s = gamedata.hero(name, town_hall=town_hall, level=level)
    else:
        s = gamedata.troop(name, town_hall=town_hall, level=level)
    return dict(
        hitpoints=s.hitpoints,
        dps=s.dps,
        attack_interval=s.attack_interval,
        attack_range=s.attack_range,
        speed=s.speed,
        housing=s.housing,
        flying=s.flying,
        hits_air=s.hits_air,
        hits_ground=s.hits_ground,
    )


class Weapon:
    __slots__ = (
        "spec",
        "owner",
        "mode",
        "targets",
        "range",
        "min_range",
        "cooldown",
        "target",
        "multi",
        "lock_time",
        "active",
        "idle_check",
        "facing",
        "st_mode",
    )

    def __init__(self, owner: Building, spec):
        self.spec = spec
        self.owner = owner
        self.mode = spec.mode
        self.targets = spec.targets
        self.range = spec.range
        self.min_range = spec.min_range
        self.cooldown = 0.0
        self.target = None
        self.multi = []
        self.lock_time = 0.0
        self.active = True
        self.idle_check = 0.0
        self.facing = 0.0
        self.st_mode = None


@dataclass
class Trap:
    key: str
    x: float
    y: float
    trigger: float
    radius: float
    damage: float
    air: bool
    ground: bool
    armed: bool = True
    fuse: float = -1.0  # time at which it detonates once triggered
    mode: str | None = None


@dataclass
class Effect:
    kind: str
    x: float
    y: float
    radius: float
    until: float
    value: float = 0.0
    team: str = "atk"
    extra: dict = field(default_factory=dict)


@dataclass
class PendingDamage:
    at: float
    x: float
    y: float
    radius: float
    damage: float
    hits_air: bool
    hits_ground: bool
    src: str = "shells"
    falloff: bool = True


@dataclass
class Deployment:
    """One scheduled deployment, produced by an AttackPlan."""

    time: float
    name: str
    x: float
    y: float
    group: str = "main"
    level: int | None = None
    town_hall: int | None = None


@dataclass
class Result:
    stars: int
    destruction: float
    th_destroyed: bool
    time: float
    destroyed_keys: dict
    surviving_defenses: list
    units_left: int
    log: list

    @property
    def score(self) -> float:
        """Attacker-side score: stars dominate, destruction breaks ties."""
        return self.stars + self.destruction / 100.0


# ==========================================================================
# Battle
# ==========================================================================


class Battle:
    def __init__(self, layout: Layout, plan, *, seed: int = 0, town_hall: int = 16, record: bool = False):
        self.rng = random.Random(seed)
        self.DT = DT
        self.t = 0.0
        self.town_hall = town_hall
        self.record = record
        self.log: list = []
        self.frames: list = []
        self.grid = Grid(WORLD)
        self.buildings: list[Building] = []
        self.walls: dict[tuple[int, int], Wall] = {}
        self.traps: list[Trap] = []
        self.attackers: list[Unit] = []
        self.defenders: list[Unit] = []
        self.effects: list[Effect] = []
        self.pending: list[PendingDamage] = []
        self.deployed_housing = 0
        self._uid = 0
        self.cc_building = None
        self.cc_queue: list[str] = []
        self.cc_released = False
        self.th = None
        self._src = "?"
        self.damage_by_source: dict = {}
        self.revivals: list = []
        self.kills_by_source: dict = {}
        self._setup(layout)
        self.total_counted = sum(1 for b in self.buildings if b.counted)
        self.destroyed_counted = 0
        self.no_deploy = self._no_deploy_tiles(layout)
        self.plan = plan
        self.deployments: list[Deployment] = sorted(plan.deployments(self), key=lambda d: d.time)
        self._next_deploy = 0

    # ------------------------------------------------------------- setup
    def _setup(self, layout: Layout):
        th = self.town_hall
        hp_cache: dict = {}
        for i, p in enumerate(layout.buildings):
            bt = BUILDING_TYPES[p.key]
            if p.key not in hp_cache:
                if bt.name == "Hero Banner":
                    hp_cache[p.key] = (1.0, 2.0, 1.0)
                elif not bt.counted:
                    hp_cache[p.key] = (1000.0, bt.size, bt.size - 1)
                else:
                    s = gamedata.building(bt.name, th)
                    hp_cache[p.key] = (s.hitpoints, s.width, s.hitbox)
            hp, width, hitbox = hp_cache[p.key]
            b = Building(i, p.key, p.x + MARGIN, p.y + MARGIN, bt.size, hitbox, hp, p.mode)
            if bt.weapon_key:
                b.weapon = Weapon(b, weapon_spec(bt.weapon_key, th))
                if p.key == "inferno":
                    b.weapon.mode = "inferno_multi" if p.mode == "multi" else "inferno_single"
                    if p.mode == "multi":
                        b.weapon.range = b.weapon.spec.extra["multi_range"]
                elif p.key == "xbow" and p.mode == "both":
                    b.weapon.targets = "both"
                    b.weapon.range = b.weapon.spec.extra["both_range"]
                elif p.key == "sweeper":
                    b.weapon.facing = _facing_angle(p.mode)
                elif p.key == "st":
                    b.weapon.st_mode = p.mode or "rage"
                    b.weapon.range = SPELL_TOWER_MODES[b.weapon.st_mode]["range"]
                elif p.key == "tesla":
                    b.revealed = False
            if p.key == "banner":
                b.alive = False  # placement marker only
            if p.key == "cc":
                self.cc_building = b
            if p.key == "th":
                self.th = b
            self.buildings.append(b)
            if b.alive:
                self.grid.block_square(b.x, b.y, b.half_hit)
        wall_hp = gamedata.building("Wall", th).hitpoints
        for tx, ty in layout.walls:
            w = Wall(tx + MARGIN, ty + MARGIN, wall_hp)
            self.walls[(w.tx, w.ty)] = w
            self.grid.set_wall(w.tx, w.ty, True)
        for tp in layout.traps:
            stats = gamedata.trap(TRAP_NAMES[tp.key], th)
            size = 2 if tp.key == "giant" else 1
            cx, cy = tp.x + MARGIN + size / 2.0, tp.y + MARGIN + size / 2.0
            radius = stats["damage_radius"]
            if tp.key == "giant":
                radius = 4.0  # catalog: 4 tiles at TH16
            air, ground = stats["air"], stats["ground"]
            if tp.key == "skeleton":
                air = tp.mode == "air"
                ground = not air
            if tp.key == "tornado":
                air = ground = True
                radius = 3.0
            self.traps.append(
                Trap(tp.key, cx, cy, stats["trigger_radius"], radius, stats["damage"], air, ground, mode=tp.mode)
            )
        # Defending heroes stand on banners.
        banners = [b for b in self.buildings if b.key == "banner"]
        for hero_name, banner in zip(layout.heroes, banners):
            u = self._spawn(hero_name, "def", banner.x, banner.y, level=_DEFENDING_HERO_LEVELS.get(hero_name))
            u.home = (banner.x, banner.y)
            u.leash = 9.0
        self.cc_queue = list(layout.cc_troops)

    def _no_deploy_tiles(self, layout: Layout) -> set:
        blocked = set()
        occupied = set()
        for p in layout.buildings:
            occupied.update(p.tiles())
        occupied.update(layout.walls)
        for tx, ty in occupied:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    blocked.add((tx + dx + MARGIN, ty + dy + MARGIN))
        return blocked

    def can_deploy(self, x: float, y: float) -> bool:
        tx, ty = int(x), int(y)
        if not (0 <= tx < WORLD and 0 <= ty < WORLD):
            return False
        return (tx, ty) not in self.no_deploy

    # ------------------------------------------------------------- units
    def _spawn(self, name, team, x, y, *, level=None, town_hall=None, group="main") -> Unit:
        stats = unit_stats(name, town_hall=town_hall or self.town_hall, level=level)
        beh = BEHAVIORS.get(name, Behavior())
        self._uid += 1
        u = Unit(self._uid, name, team, x, y, stats, beh, is_hero=name in HERO_NAMES)
        u.group = group
        u.spawned_at = self.t
        if team == "atk":
            self.attackers.append(u)
        else:
            self.defenders.append(u)
        return u

    def deploy(self, d: Deployment) -> Unit:
        u = self._spawn(d.name, "atk", d.x, d.y, level=d.level, town_hall=d.town_hall, group=d.group)
        k = getattr(self.plan, "strength", 1.0)
        if k != 1.0:
            u.hp *= k
            u.max_hp *= k
            u.dps *= k
            u.heal_rate *= k
        if u.is_hero:
            hero_kit.equip(self, u, self.plan)
        self.deployed_housing += u.housing if not u.is_hero else 25
        if self.record:
            self.log.append((round(self.t, 1), "deploy", d.name, round(d.x, 1), round(d.y, 1)))
        return u

    def spawn_totem(self, x, y, hp, decay, radius):
        """Totem Spell: stuns nearby buildings, then soaks defensive fire."""
        stats = dict(
            hitpoints=hp,
            dps=0.0,
            attack_interval=1.0,
            attack_range=0.0,
            speed=0.0,
            housing=0,
            flying=False,
            hits_air=False,
            hits_ground=False,
        )
        self._uid += 1
        u = Unit(self._uid, "Totem", "atk", x, y, stats, Behavior(engages_units=False))
        u.group = "totem"
        u.decay = decay
        u.spawned_at = self.t
        self.attackers.append(u)
        for b in self.buildings:
            if b.alive and b.edge_distance(x, y) <= radius:
                b.frozen_until = max(b.frozen_until, self.t + 1.0)
                if b.weapon is not None and _dist(b.x, b.y, x, y) <= b.weapon.range:
                    b.weapon.target = u
                    b.weapon.lock_time = 0.0
        if self.record:
            self.log.append((round(self.t, 1), "spell", "totem", round(x, 1), round(y, 1)))
        return u

    # ----------------------------------------------------------- queries
    def alive_buildings(self):
        return [b for b in self.buildings if b.alive]

    def destruction(self) -> float:
        return 100.0 * self.destroyed_counted / max(1, self.total_counted)

    def stars(self) -> int:
        s = 0
        if self.destruction() >= 50.0:
            s += 1
        if self.th is not None and not self.th.alive:
            s += 1
        if self.destroyed_counted >= self.total_counted:
            s += 1
        return s

    def _targetable_building(self, b: Building) -> bool:
        if not b.alive:
            return False
        if self.t < b.overgrown_until:
            return False
        if b.key == "tesla" and not b.revealed:
            return False
        return True

    def choose_building(self, u: Unit):
        pref = u.beh.prefer
        best = None
        best_d = 1e9
        candidates = self.buildings
        if pref == "air_defense":
            pool = [b for b in candidates if b.key == "ad" and self._targetable_building(b)]
            if not pool:
                pref = "defense"
            else:
                candidates = pool
        if pref == "defense":
            pool = [b for b in candidates if b.is_defense and self._targetable_building(b)]
            if pool:
                candidates = pool
        for b in candidates:
            if not self._targetable_building(b) or not b.counted and b.key != "th":
                continue
            d = b.edge_distance(u.x, u.y)
            if d < best_d:
                best_d = d
                best = b
        return best

    def _hittable(self, attacker: Unit, victim: Unit) -> bool:
        if not victim.alive:
            return False
        return attacker.hits_air if victim.flying else attacker.hits_ground

    # ------------------------------------------------------------- damage
    def damage_unit(self, u: Unit, amount: float, source=None):
        if not u.alive or amount <= 0:
            return
        if source == "trap" and u.name == "Dragon Duke":
            amount *= 0.8  # July 2026: trap reduction cut to ~20%
        if self.t < u.invulnerable_until:
            return
        if self.t < u.iceblock_until:
            amount *= 1.0 - u.iceblock_red
        if u.team == "atk":
            amount *= u.aura_mult
            if u.kit is not None:
                amount *= hero_kit.damage_taken_mult(self, u)
        if u.team == "atk":
            src = source if source not in (None, "trap") else self._src
            self.damage_by_source[src] = self.damage_by_source.get(src, 0.0) + min(amount, u.hp)
        u.hp -= amount
        if u.hp <= 0:
            if u.team == "atk":
                self.kills_by_source[src] = self.kills_by_source.get(src, 0) + max(1, u.housing)
            self._kill_unit(u)

    def _kill_unit(self, u: Unit):
        u.alive = False
        u.hp = 0
        beh = u.beh
        if u.team == "atk" and u.is_hero:
            if u.kit is not None and hero_kit.on_death(self, u):
                return  # Phoenix: invincible revival, knocked out when it ends
            spells = getattr(self.plan, "spells", {})
            if spells.get("revive", 0) > 0:
                spells["revive"] -= 1
                self.revivals.append((self.t + 1.0, u))
        if beh.death_damage > 0:
            if u.team == "atk":
                self.splash_buildings(u.x, u.y, beh.death_radius, beh.death_damage)
            else:
                self.splash_units(u.x, u.y, beh.death_radius, beh.death_damage, True, True, team="atk")
        for name, count in beh.spawn_on_death:
            for k in range(count):
                ang = 2 * math.pi * k / count
                c = self._spawn(name, u.team, u.x + 0.6 * math.cos(ang), u.y + 0.6 * math.sin(ang), group=u.group)
                if name == "Lava Pup":
                    c.hp = c.max_hp = 150 if self.town_hall < 18 else 170
        if self.record:
            self.log.append((round(self.t, 1), "dies", u.name, u.team))

    def damage_building(self, b, amount: float):
        if not b.alive or amount <= 0:
            return
        b.hp -= amount
        if b.hp <= 0:
            self._destroy(b)

    def _destroy(self, b):
        b.alive = False
        b.hp = 0
        if isinstance(b, Wall):
            self.grid.set_wall(b.tx, b.ty, False)
            return
        self.grid.block_square(b.x, b.y, b.half_hit, False)
        if b.counted:
            self.destroyed_counted += 1
        if b.weapon is not None:
            spec = b.weapon.spec
            dmg = spec.extra.get("death_damage")
            if dmg:
                self.splash_units(b.x, b.y, spec.extra["death_radius"], dmg, True, b.key != "bt", team="atk")
        if self.record:
            self.log.append((round(self.t, 1), "destroyed", b.key, round(self.destruction(), 1)))

    def splash_buildings(self, x, y, radius, damage, *, include_walls=True):
        for b in self.buildings:
            if b.alive and b.edge_distance(x, y) <= radius:
                self.damage_building(b, damage)
        if include_walls and radius >= 0.5:
            r = int(radius) + 1
            for tx in range(int(x) - r, int(x) + r + 1):
                for ty in range(int(y) - r, int(y) + r + 1):
                    w = self.walls.get((tx, ty))
                    if w is not None and w.alive and w.edge_distance(x, y) <= radius:
                        self.damage_building(w, damage)

    def splash_units(self, x, y, radius, damage, hits_air, hits_ground, *, team="atk", falloff=False, source=None):
        pool = self.attackers if team == "atk" else self.defenders
        for u in pool:
            if not u.alive:
                continue
            if u.flying and not hits_air or not u.flying and not hits_ground:
                continue
            d = _dist(u.x, u.y, x, y)
            if d <= radius:
                amt = damage * (1.0 - 0.5 * d / radius) if falloff and radius > 0 else damage
                self.damage_unit(u, amt, source)

    # ------------------------------------------------------------- loop
    def run(self) -> Result:
        while self.t < MAX_TIME:
            self.step()
            if self.destroyed_counted >= self.total_counted:
                break
            pending = self.plan.has_pending() if hasattr(self.plan, 'has_pending') else False
            if self._next_deploy >= len(self.deployments) and not pending and not any(u.alive and u.name != "Totem" for u in self.attackers):
                if not self.pending:
                    break
        return self.result()

    def result(self) -> Result:
        destroyed: dict = {}
        surviving = []
        for b in self.buildings:
            if b.counted and not b.alive:
                destroyed[b.key] = destroyed.get(b.key, 0) + 1
            if b.alive and b.is_defense:
                surviving.append(b.key)
        return Result(
            stars=self.stars(),
            destruction=round(self.destruction(), 2),
            th_destroyed=self.th is not None and not self.th.alive,
            time=round(self.t, 1),
            destroyed_keys=destroyed,
            surviving_defenses=surviving,
            units_left=sum(1 for u in self.attackers if u.alive),
            log=self.log,
        )

    def step(self):
        t = self.t
        while self._next_deploy < len(self.deployments) and self.deployments[self._next_deploy].time <= t:
            self.deploy(self.deployments[self._next_deploy])
            self._next_deploy += 1
        self._buckets()
        self.plan.on_tick(self)
        self._apply_effects()
        self._resolve_pending()
        self._traps()
        self._castle()
        for u in self.attackers:
            if u.alive:
                self._act_attacker(u)
        self._separate()
        if self.revivals:
            self._revive()
        for b in self.buildings:
            if b.weapon is not None and b.alive:
                self._act_weapon(b.weapon)
        for u in self.defenders:
            if u.alive:
                self._act_defender(u)
        if len(self.attackers) > 120:
            self.attackers = [u for u in self.attackers if u.alive]
        if self.record and int(t * 10) % 5 == 0:
            self.frames.append(self._snapshot())
        self.t = round(t + DT, 6)

    def _snapshot(self):
        return {
            "t": round(self.t, 1),
            "u": [(u.name, round(u.x, 2), round(u.y, 2), round(u.hp / u.max_hp, 2), u.team) for u in self.attackers + self.defenders if u.alive],
            "dead": [b.id for b in self.buildings if not b.alive and b.key != "banner"],
            "walls": [k for k, w in self.walls.items() if not w.alive],
        }

    # -------------------------------------------------------- spatial index
    def _buckets(self):
        nb = int(WORLD / BUCKET) + 1
        self._nb = nb
        grid: dict = {}
        wardens = []
        for u in self.attackers:
            if u.alive:
                key = (int(u.x / BUCKET), int(u.y / BUCKET))
                grid.setdefault(key, []).append(u)
                u.aura_mult = 1.0
                u.aura_dmg = 1.0
                if u.name in ("Grand Warden", "Apprentice Warden"):
                    wardens.append(u)
        self._bucket_grid = grid
        for w in wardens:
            if w.name == "Apprentice Warden":
                pct, cap, rage = 0.26, 1e9, 0.0  # wiki L4 Apprentice Warden aura
            else:
                kit = w.kit
                pct = kit.passive("aura_hp_pct") if kit else 0.0
                cap = kit.passive("aura_hp_cap", 1e9) if kit else 0.0
                rage = kit.passive("aura_damage") if kit else 0.0
            for a in self.attackers_near(w.x, w.y, 7.0):
                if a is w or a.name == "Totem":
                    continue
                if pct:
                    bonus = min(pct * a.max_hp, cap)
                    a.aura_mult = min(a.aura_mult, a.max_hp / (a.max_hp + bonus))
                if rage and not a.is_hero:
                    a.aura_dmg = max(a.aura_dmg, 1.0 + rage)

    def _separate(self):
        """Push overlapping attackers apart so splash damage is not inflated
        by every unit standing on the same point."""
        for cell in self._bucket_grid.values():
            n = len(cell)
            if n < 2:
                continue
            for i in range(n):
                a = cell[i]
                if not a.alive or a.name == "Totem":
                    continue
                ra = 0.35 + 0.015 * min(30, a.housing)
                for j in range(i + 1, n):
                    b = cell[j]
                    if not b.alive or b.flying != a.flying or b.name == "Totem":
                        continue
                    rb = 0.35 + 0.015 * min(30, b.housing)
                    dx = b.x - a.x
                    dy = b.y - a.y
                    d2 = dx * dx + dy * dy
                    lim = ra + rb
                    if d2 >= lim * lim:
                        continue
                    d = math.sqrt(d2)
                    if d < 1e-6:
                        ang = (a.id * 2.399) % (2 * math.pi)
                        dx, dy, d = math.cos(ang), math.sin(ang), 1.0
                        push = lim * 0.25
                    else:
                        push = (lim - d) * 0.25
                    ux, uy = dx / d * push, dy / d * push
                    self._nudge(a, -ux, -uy)
                    self._nudge(b, ux, uy)

    def _nudge(self, u, dx, dy):
        nx, ny = u.x + dx, u.y + dy
        if not u.flying:
            i, j = self.grid.cell(nx, ny)
            if self.grid.blocked[i, j] or self.grid.wall[i, j]:
                return
        u.x = min(WORLD - 0.1, max(0.1, nx))
        u.y = min(WORLD - 0.1, max(0.1, ny))

    def attackers_near(self, x, y, r):
        grid = self._bucket_grid
        out = []
        r2 = r * r
        lo_i, hi_i = int((x - r) / BUCKET), int((x + r) / BUCKET)
        lo_j, hi_j = int((y - r) / BUCKET), int((y + r) / BUCKET)
        for i in range(lo_i, hi_i + 1):
            for j in range(lo_j, hi_j + 1):
                cell = grid.get((i, j))
                if cell:
                    for u in cell:
                        dx = u.x - x
                        dy = u.y - y
                        if dx * dx + dy * dy <= r2 and u.alive:
                            out.append(u)
        return out

    # ------------------------------------------------------------- effects
    def add_effect(self, e: Effect):
        self.effects.append(e)
        if self.record:
            self.log.append((round(self.t, 1), "spell", e.kind, round(e.x, 1), round(e.y, 1)))

    def _apply_effects(self):
        self._src = "effect"
        t = self.t
        keep = []
        for e in self.effects:
            if t > e.until:
                continue
            keep.append(e)
            if e.kind == "rage":
                for u in self.attackers_near(e.x, e.y, e.radius):
                    boost = e.value if not u.is_hero else 1.0 + (e.value - 1.0) / 2.0
                    u.rage_mult = max(u.rage_mult if t < u.rage_until else 1.0, boost)
                    u.rage_until = t + 1.0
                    u.haste_mult = max(u.haste_mult if t < u.haste_until else 1.0, 1.0 + e.extra["speed"])
                    u.haste_until = t + 1.0
            elif e.kind == "haste":
                for u in self.attackers_near(e.x, e.y, e.radius):
                    u.haste_mult = max(u.haste_mult if t < u.haste_until else 1.0, 1.0 + e.value)
                    u.haste_until = t + 1.0
            elif e.kind == "heal":
                for u in self.attackers_near(e.x, e.y, e.radius):
                    if u.flying and u.name != "Healer" and not u.is_hero and False:
                        continue
                    hps = e.extra["hero_hps"] if u.is_hero else e.value
                    u.hp = min(u.max_hp, u.hp + hps * DT)
            elif e.kind == "freeze":
                for b in self.buildings:
                    if b.alive and b.edge_distance(e.x, e.y) <= e.radius:
                        b.frozen_until = max(b.frozen_until, t + DT * 1.5)
                for u in self.defenders:
                    if u.alive and _dist(u.x, u.y, e.x, e.y) <= e.radius:
                        u.held_until = max(u.held_until, t + DT * 1.5)
            elif e.kind == "overgrowth":
                for b in self.buildings:
                    if b.alive and b.is_defense and b.edge_distance(e.x, e.y) <= e.radius:
                        b.overgrown_until = max(b.overgrown_until, t + DT * 1.5)
            elif e.kind == "invis":
                for u in self.attackers_near(e.x, e.y, e.radius):
                    u.invisible_until = max(u.invisible_until, t + DT * 1.5)
            elif e.kind == "iceblock":
                for u in self.attackers_near(e.x, e.y, e.radius):
                    u.iceblock_until = max(u.iceblock_until, t + DT * 1.5)
                    u.iceblock_red = e.value
            elif e.kind == "poison":  # attacker poison on defending troops
                for u in self.defenders:
                    if u.alive and _dist(u.x, u.y, e.x, e.y) <= e.radius:
                        self.damage_unit(u, e.value * DT)
                        u.slow_mult = 1.0 - e.extra.get("slow", 0.5)
                        u.slow_until = t + DT * 1.5
            elif e.kind == "def_poison":  # spell-tower poison on attackers
                for u in self.attackers_near(e.x, e.y, e.radius):
                    self.damage_unit(u, e.value * DT)
                    u.slow_mult = 1.0 - e.extra["slow"]
                    u.slow_until = t + DT * 1.5
            elif e.kind == "def_rage":
                for b in self.buildings:
                    if b.alive and b.weapon is not None and _dist(b.x, b.y, e.x, e.y) <= e.radius:
                        b.rage_mult = 1.0 + e.value
                        b.rage_until = t + DT * 1.5
            elif e.kind == "def_invis":
                for b in self.buildings:
                    if b.alive and b.is_defense and _dist(b.x, b.y, e.x, e.y) <= e.radius:
                        b.invisible_until = t + DT * 1.5
            elif e.kind == "tornado":
                for u in self.attackers_near(e.x, e.y, e.radius):
                    if u.is_hero:
                        continue
                    u.held_until = t + DT * 1.5
                    # pull towards the centre
                    u.x += (e.x - u.x) * 0.15
                    u.y += (e.y - u.y) * 0.15
                    self.damage_unit(u, e.value * DT)
        self.effects = keep

    def _resolve_pending(self):
        if not self.pending:
            return
        self._src = "shells"
        t = self.t
        rest = []
        for p in self.pending:
            if p.at <= t:
                self._src = p.src
                self.splash_units(p.x, p.y, p.radius, p.damage, p.hits_air, p.hits_ground, team="atk", falloff=p.falloff)
            else:
                rest.append(p)
        self.pending = rest

    # --------------------------------------------------------------- traps
    def _traps(self):
        t = self.t
        self._src = "trap"
        for tr in self.traps:
            if not tr.armed:
                continue
            if tr.fuse >= 0:
                if t >= tr.fuse:
                    self._detonate(tr)
                continue
            for u in self.attackers_near(tr.x, tr.y, tr.trigger):
                if u.flying and tr.air or not u.flying and tr.ground:
                    tr.fuse = t + (0.5 if tr.key in ("giant", "bomb", "airbomb") else 0.0)
                    if tr.fuse <= t:
                        self._detonate(tr, u)
                    break

    def _detonate(self, tr: Trap, trigger_unit: Unit | None = None):
        tr.armed = False
        self._src = "trap:" + tr.key
        t = self.t
        if self.record:
            self.log.append((round(t, 1), "trap", tr.key))
        if tr.key in ("bomb", "giant", "airbomb"):
            self.splash_units(tr.x, tr.y, tr.radius, tr.damage, tr.air, tr.ground, team="atk", source="trap")
        elif tr.key == "seeking":
            pool = [u for u in self.attackers_near(tr.x, tr.y, tr.trigger) if u.flying]
            if trigger_unit is not None and trigger_unit.flying:
                pool.append(trigger_unit)
            if pool:
                victim = max(pool, key=lambda u: u.hp)
                self.damage_unit(victim, tr.damage, "trap")
        elif tr.key == "spring":
            capacity = 18
            pool = sorted(
                (u for u in self.attackers_near(tr.x, tr.y, 1.2) if not u.flying and not u.is_hero),
                key=lambda u: -u.housing,
            )
            flung = False
            for u in pool:
                if 0 < u.housing <= capacity:
                    capacity -= u.housing
                    self._kill_unit(u)
                    flung = True
            if not flung and pool:
                self.damage_unit(pool[0], tr.damage)
        elif tr.key == "skeleton":
            for k in range(5):
                ang = 2 * math.pi * k / 5
                s = self._spawn("Skeleton", "def", tr.x + 0.7 * math.cos(ang), tr.y + 0.7 * math.sin(ang))
                if tr.mode == "air":
                    s.hits_air = True
                s.home = None
        elif tr.key == "tornado":
            self.add_effect(Effect("tornado", tr.x, tr.y, tr.radius, t + 7.0, value=8.0, team="def"))  # 55 total over 7 s (wiki)

    # -------------------------------------------------------------- castle
    def _castle(self):
        cc = self.cc_building
        if cc is None or self.cc_released or not self.cc_queue:
            return
        if self.attackers_near(cc.x, cc.y, CC_TRIGGER_RADIUS):
            self.cc_released = True
            for k, name in enumerate(self.cc_queue):
                ang = 2 * math.pi * k / max(1, len(self.cc_queue))
                u = self._spawn(name, "def", cc.x + 1.5 * math.cos(ang), cc.y + 1.5 * math.sin(ang), town_hall=16)
                u.spawned_at = self.t + 0.4 * k  # staggered release
                u.home = None

    # ------------------------------------------------------- attacker AI
    def _act_attacker(self, u: Unit):
        t = self.t
        if u.name == "Totem":
            u.hp -= u.decay * DT
            if u.hp <= 0:
                self._kill_unit(u)
            return
        if u.decay > 0:  # timed summons (Magic Mirror clones)
            u.hp -= u.decay * DT
            if u.hp <= 0:
                self._kill_unit(u)
                return
        if u.kit is not None:
            hero_kit.tick(self, u)
            if not u.alive:
                return
        if t < u.dash_until:
            self._dash(u)
            return
        if u.name == "Dragon Duke" and not u.dashed and t - u.spawned_at > 4.0:
            if u.kit is not None and u.kit.has("Rocket Backpack"):
                u.ability_used = True
                hero_kit.activate(self, u)
            else:
                self._start_dash(u)
            return
        if t < u.held_until:
            return
        u.cooldown -= DT
        beh = u.beh
        if u.heal_rate > 0:
            self._act_healer(u)
            return
        # hero ability: heal and boost when badly hurt (equipment abstracted)
        if u.is_hero and not u.ability_used:
            fire = False
            if u.name == "Grand Warden":
                near = [a for a in self.attackers_near(u.x, u.y, 7.0) if a.name != "Totem"]
                fire = u.hp < 0.4 * u.max_hp or (
                    len(near) >= 5 and sum(a.hp / a.max_hp for a in near) / len(near) < 0.7
                )
            elif u.hp < 0.5 * u.max_hp:
                fire = True
            elif t - u.spawned_at > 12.0 and u.target is not None and u.cooldown > 0:
                fire = True
            if fire:
                if u.kit is not None:
                    u.ability_used = True
                    hero_kit.activate(self, u)
                    if self.record:
                        self.log.append((round(t, 1), "ability", u.name))
                else:
                    self._hero_ability(u)
        target = u.target
        if target is not None:
            if not target.alive:
                target = None
            elif u.target_kind == "building" and not self._targetable_building(target):
                target = None
        # break off to fight defending troops that come close
        if beh.engages_units and u.target_kind != "unit" and t >= u.next_retarget:
            u.next_retarget = t + 0.5
            foe = self._nearest_defender(u, ENGAGE_RADIUS + u.range)
            if foe is not None:
                target = foe
                u.target_kind = "unit"
                u.wall_target = None
        if target is None:
            u.wall_target = None
            if beh.prefer == "wall":
                target = self._wall_breaker_target(u)
                u.target_kind = "wall" if target is not None else None
            elif beh.prefer == "heroes":
                foe = self._nearest_defender(u, 60.0, heroes_only=True)
                if foe is not None:
                    target, u.target_kind = foe, "unit"
            if target is None:
                target = self.choose_building(u)
                u.target_kind = "building" if target is not None else None
        u.target = target
        if target is None:
            return
        if u.wall_target is not None and u.wall_target.alive:
            self._attack_or_approach(u, u.wall_target, wall=True)
            return
        u.wall_target = None
        self._attack_or_approach(u, target)

    def _speed(self, u: Unit) -> float:
        t = self.t
        s = u.speed
        if t < u.haste_until:
            s *= u.haste_mult
        if t < u.slow_until:
            s *= u.slow_mult
        return s

    def _attack_or_approach(self, u: Unit, target, wall=False):
        if isinstance(target, Unit):
            d = _dist(u.x, u.y, target.x, target.y)
        else:
            d = target.edge_distance(u.x, u.y)
        if d <= u.range + 0.05:
            if u.cooldown <= 0:
                self._strike(u, target, wall)
                u.cooldown = u.interval
            return
        step = self._speed(u) * DT
        if u.flying or isinstance(target, Unit):
            self._move_straight(u, target.x, target.y, step)
            return
        if isinstance(target, Wall):
            self._move_straight(u, target.x, target.y, step)
            return
        wall_class = u.beh.wall_class
        reach = max(0.3, u.range - 0.05)
        key = (target.id, round(reach * 2) / 2.0, wall_class)
        dist = self.grid.field(key, target.x, target.y, target.half_hit, reach, WALL_PATH_COST[wall_class] / RES)
        nx, ny, is_wall, at_goal = self.grid.next_step(dist, u.x, u.y)
        if at_goal:
            # numerically in a goal cell but not quite in range: close in
            self._move_straight(u, target.x, target.y, step)
            return
        if is_wall and wall_class == "ignore":
            is_wall = False
        if is_wall:
            w = self.walls.get((int(nx), int(ny)))
            if w is not None and w.alive:
                u.wall_target = w
                if w.edge_distance(u.x, u.y) <= u.range + 0.05:
                    if u.cooldown <= 0:
                        self._strike(u, w, True)
                        u.cooldown = u.interval
                else:
                    self._move_straight(u, w.x, w.y, step)
                return
        if nx == u.x and ny == u.y:
            u.stuck += DT
            if u.stuck > 2.0:
                u.target = None
                u.stuck = 0.0
            return
        u.stuck = 0.0
        self._move_straight(u, nx, ny, step)

    def _move_straight(self, u, tx, ty, step):
        dx = tx - u.x
        dy = ty - u.y
        d = math.hypot(dx, dy)
        if d <= step or d == 0:
            u.x, u.y = tx, ty
        else:
            u.x += dx / d * step
            u.y += dy / d * step

    def _strike(self, u: Unit, target, wall=False):
        t = self.t
        mult = u.rage_mult if t < u.rage_until else 1.0
        if t < u.ability_boost_until:
            mult *= 1.5
        if t < u.slow_until:
            mult *= u.slow_mult
        if u.name == "Dragon Duke":
            alone = not any(
                a is not u and a.flying and a.name != "Totem" for a in self.attackers_near(u.x, u.y, 4.0)
            )
            if alone:
                mult *= 3.0  # Royal Rampage: +100% damage, +50% attack speed
        mult *= u.aura_dmg
        dmg = u.dps * u.interval * mult
        if u.kit is not None and not isinstance(target, Wall):
            dmg += hero_kit.strike_bonus(u, target)
        beh = u.beh
        if isinstance(target, Wall):
            amount = dmg * beh.wall_dps_mult
            if beh.prefer == "wall" and u.name.endswith("Wall Breaker"):
                # wall breakers blow up on contact
                self.splash_buildings(target.x, target.y, 2.0, amount)
                self._kill_unit(u)
                return
            self.damage_building(target, amount)
            u.damage_dealt += amount
            return
        if isinstance(target, Unit):
            self.damage_unit(target, dmg)
            if beh.splash > 0:
                for v in self.defenders:
                    if v is not target and v.alive and _dist(v.x, v.y, target.x, target.y) <= beh.splash:
                        if self._hittable(u, v):
                            self.damage_unit(v, dmg)
            return
        u.damage_dealt += dmg
        if beh.self_splash:
            self.splash_buildings(u.x, u.y, beh.splash + 0.5, dmg, include_walls=False)
            return
        self.damage_building(target, dmg)
        if u.kit is not None:
            hero_kit.on_hit_extra(self, u, target)
        if beh.splash > 0:
            for b in self.buildings:
                if b is not target and b.alive and b.edge_distance(target.x, target.y) <= beh.splash:
                    self.damage_building(b, dmg)
        if beh.chain > 0:
            hit = {target.id}
            cur = target
            amt = dmg
            for _ in range(beh.chain):
                amt *= beh.chain_falloff
                nxt = None
                nd = beh.chain_range
                for b in self.buildings:
                    if b.alive and b.id not in hit and b.counted:
                        d = _dist(b.x, b.y, cur.x, cur.y)
                        if d <= nd:
                            nd = d
                            nxt = b
                if nxt is None:
                    break
                hit.add(nxt.id)
                self.damage_building(nxt, amt)
                cur = nxt

    def _revive(self):
        keep = []
        for at, u in self.revivals:
            if self.t >= at:
                from .loadouts import REVIVE_PCT

                u.alive = True
                u.hp = REVIVE_PCT.get(getattr(self.plan, "town_hall", 16), 0.7) * u.max_hp
                u.target = None
                u.ability_used = False
                if u not in self.attackers:
                    self.attackers.append(u)
            else:
                keep.append((at, u))
        self.revivals = keep

    def _start_dash(self, u: Unit, damage: float = 1500.0):
        # Rocket Backpack: straight-line dash towards the nearest defense,
        # burning buildings on the way (wiki: 2,150 ability damage at L27).
        u.dashed = True
        u.dash_damage = damage
        defs = [b for b in self.buildings if b.alive and b.is_defense]
        if defs:
            near = min(defs, key=lambda b: _dist(b.x, b.y, u.x, u.y))
            tx, ty = near.x, near.y
        else:
            tx, ty = WORLD / 2, WORLD / 2
        dx, dy = tx - u.x, ty - u.y
        d = math.hypot(dx, dy) or 1.0
        u.dash_dir = (dx / d, dy / d)
        u.dash_until = self.t + 1.6
        u.dash_hit = set()
        u.invulnerable_until = max(u.invulnerable_until, self.t + 0.8)

    def _dash(self, u: Unit):
        u.x += u.dash_dir[0] * 6.0 * DT
        u.y += u.dash_dir[1] * 6.0 * DT
        u.x = min(WORLD - 0.5, max(0.5, u.x))
        u.y = min(WORLD - 0.5, max(0.5, u.y))
        for b in self.buildings:
            if b.alive and b.id not in u.dash_hit and b.edge_distance(u.x, u.y) <= 1.5:
                u.dash_hit.add(b.id)
                self.damage_building(b, u.dash_damage)

    def _hero_ability(self, u: Unit):
        """One activation per life. Equipment numbers are rough TH17-18
        approximations of the popular loadouts (assumed)."""
        u.ability_used = True
        u.hp = min(u.max_hp, u.hp + 0.35 * u.max_hp)
        u.ability_boost_until = self.t + 6.0
        tgt = u.target if isinstance(u.target, Building) else None
        if u.name == "Archer Queen":
            u.invisible_until = self.t + 4.0
            # Giant Arrow: pierces a line of buildings towards her target
            if tgt is not None:
                dx, dy = tgt.x - u.x, tgt.y - u.y
                d = math.hypot(dx, dy) or 1.0
                for b in self.buildings:
                    if not b.alive or not b.counted:
                        continue
                    px, py = b.x - u.x, b.y - u.y
                    along = (px * dx + py * dy) / d
                    if 0 < along < 14 and abs(px * dy - py * dx) / d < 1.5:
                        self.damage_building(b, 1500.0)
        elif u.name == "Barbarian King":
            if tgt is not None:  # Spiky Ball
                self.damage_building(tgt, 2500.0)
                self.splash_buildings(tgt.x, tgt.y, 3.0, 800.0, include_walls=False)
        elif u.name == "Grand Warden":
            for a in self.attackers_near(u.x, u.y, 7.0):
                a.invulnerable_until = self.t + 7.0  # Eternal Tome
        elif u.name == "Royal Champion":
            near = sorted(
                (b for b in self.buildings if b.alive and b.is_defense and _dist(b.x, b.y, u.x, u.y) < 10),
                key=lambda b: _dist(b.x, b.y, u.x, u.y),
            )[:4]
            for b in near:
                self.damage_building(b, 2000.0)  # Rocket Spear / Seeking Shield
        elif u.name == "Minion Prince":
            if tgt is not None:  # Dark Orb / Meteor Staff
                self.damage_building(tgt, 3000.0)
                self.splash_buildings(tgt.x, tgt.y, 2.0, 1200.0, include_walls=False)
        elif u.name == "Dragon Duke":
            u.hp = min(u.max_hp, u.hp + 0.25 * u.max_hp)
        if self.record:
            self.log.append((round(self.t, 1), "ability", u.name))

    def _act_healer(self, u: Unit):
        # follow and heal the most damaged nearby ground unit
        best = None
        best_score = 1e9
        if u.follow is not None and u.follow.alive:
            best = u.follow
            best_score = -1e9
        for a in ([] if best is not None else self.attackers):
            if not a.alive or a.flying or a is u or a.heal_rate > 0 or a.name == "Totem":
                continue
            missing = a.max_hp - a.hp
            d = _dist(a.x, a.y, u.x, u.y)
            score = d - min(8.0, missing / 300.0) - (3.0 if a.is_hero else 0.0)
            if score < best_score:
                best_score = score
                best = a
        if best is None:
            return
        d = _dist(best.x, best.y, u.x, u.y)
        if d > u.range:
            self._move_straight(u, best.x, best.y, self._speed(u) * DT)
            return
        mult = 1.0
        for a in self.attackers_near(best.x, best.y, 2.0):
            if a.flying or not a.alive:
                continue
            hps = u.heal_rate * (0.55 if a.is_hero else 1.0) * mult
            a.hp = min(a.max_hp, a.hp + hps * DT)

    def _nearest_defender(self, u: Unit, radius: float, heroes_only=False):
        best = None
        bd = radius
        for v in self.defenders:
            if not v.alive or v.spawned_at > self.t:
                continue
            if heroes_only and not v.is_hero:
                continue
            if not self._hittable(u, v):
                continue
            d = _dist(u.x, u.y, v.x, v.y)
            if d <= bd:
                bd = d
                best = v
        return best

    def _wall_breaker_target(self, u: Unit):
        # nearest wall that sits between the unit and the village centre
        best = None
        bd = 1e9
        cx = cy = WORLD / 2
        for w in self.walls.values():
            if not w.alive:
                continue
            d = _dist(u.x, u.y, w.x, w.y) + 0.3 * _dist(w.x, w.y, cx, cy)
            if d < bd:
                bd = d
                best = w
        return best

    # ------------------------------------------------------- defender AI
    def _act_defender(self, u: Unit):
        t = self.t
        self._src = "unit:" + u.name
        if u.spawned_at > t or t < u.held_until:
            return
        u.cooldown -= DT
        target = u.target if (u.target is not None and u.target.alive) else None
        if target is not None and t >= target.invisible_until:
            pass
        elif target is not None:
            target = None
        if target is None or t >= u.next_retarget:
            u.next_retarget = t + 0.5
            center = u.home if u.home is not None else (u.x, u.y)
            radius = u.leash if u.home is not None else 30.0
            best = None
            bd = 1e9
            for a in self.attackers_near(center[0], center[1], radius):
                if t < a.invisible_until or not self._hittable(u, a):
                    continue
                d = _dist(a.x, a.y, u.x, u.y)
                if d < bd:
                    bd = d
                    best = a
            target = best
        u.target = target
        if target is None:
            if u.home is not None:
                self._move_straight(u, u.home[0], u.home[1], u.speed * DT)
            return
        if u.is_hero and not u.ability_used and u.hp < 0.4 * u.max_hp:
            u.ability_used = True
            u.hp = min(u.max_hp, u.hp + 0.35 * u.max_hp)
        d = _dist(u.x, u.y, target.x, target.y)
        if d <= u.range + 0.3:
            if u.cooldown <= 0:
                mult = u.slow_mult if t < u.slow_until else 1.0
                dmg = u.dps * u.interval * mult
                self.damage_unit(target, dmg)
                if u.beh.splash > 0:
                    for a in self.attackers_near(target.x, target.y, u.beh.splash):
                        if a is not target and self._hittable(u, a):
                            self.damage_unit(a, dmg)
                u.cooldown = u.interval
            return
        speed = u.speed * (u.slow_mult if t < u.slow_until else 1.0)
        self._move_straight(u, target.x, target.y, speed * DT)

    # --------------------------------------------------------- defenses
    def _visible_attackers(self, w: Weapon, r: float):
        b = w.owner
        t = self.t
        out = []
        for a in self.attackers_near(b.x, b.y, r):
            if t < a.invisible_until:
                continue
            if a.name == "Totem":
                pass
            elif a.flying:
                if w.targets == "ground":
                    continue
            elif w.targets == "air":
                continue
            if w.min_range > 0 and _dist(a.x, a.y, b.x, b.y) < w.min_range:
                continue
            out.append(a)
        return out

    def _act_weapon(self, w: Weapon):
        b = w.owner
        t = self.t
        self._src = b.key
        w.cooldown -= DT
        if b.disabled(t):
            w.lock_time = 0.0
            return
        if b.key == "tesla" and not b.revealed:
            if self.attackers_near(b.x, b.y, w.spec.extra["hidden"]):
                b.revealed = True
            else:
                return
        mode = w.mode
        if mode == "eagle":
            self._eagle(w)
            return
        if mode == "sweeper":
            self._sweeper(w)
            return
        if mode == "spelltower":
            self._spell_tower(w)
            return
        rage = b.rage_mult if t < b.rage_until else 1.0
        if mode in ("multi", "inferno_multi", "giga"):
            if w.cooldown > 0:
                return
            n = w.spec.n_targets
            rng = w.range
            keep = [a for a in w.multi if a.alive and t >= a.invisible_until and _dist(a.x, a.y, b.x, b.y) <= rng]
            if len(keep) < n:
                for a in sorted(self._visible_attackers(w, rng), key=lambda a: _dist(a.x, a.y, b.x, b.y)):
                    if a not in keep:
                        keep.append(a)
                        if len(keep) >= n:
                            break
            w.multi = keep
            if not keep:
                return
            if mode == "inferno_multi":
                dmg = w.spec.extra["multi_dps"] * DT * rage
                w.cooldown = 0.0
            elif mode == "giga":
                dmg = w.spec.damage / w.spec.interval * DT * rage
                w.cooldown = 0.0
            else:
                dmg = w.spec.damage * rage
                w.cooldown = w.spec.interval
            for a in keep:
                self.damage_unit(a, dmg)
                if mode == "giga":
                    a.slow_mult = min(a.slow_mult if t < a.slow_until else 1.0, 1.0 - w.spec.extra["slow"])
                    a.slow_until = t + 0.3
            return
        # single-target families keep their target while it stays valid
        tgt = w.target
        if tgt is not None:
            d = _dist(tgt.x, tgt.y, b.x, b.y)
            if not tgt.alive or t < tgt.invisible_until or d > w.range or d < w.min_range:
                tgt = None
                w.lock_time = 0.0
        if tgt is None:
            if t < w.idle_check:
                return
            pool = self._visible_attackers(w, w.range)
            if not pool:
                w.idle_check = t + 0.3
                return
            tgt = min(pool, key=lambda a: _dist(a.x, a.y, b.x, b.y))
            w.target = tgt
            w.lock_time = 0.0
        w.target = tgt
        if mode == "inferno_single":
            w.lock_time += DT
            dps = 0.0
            for start, value in w.spec.extra["ramp"]:
                if w.lock_time >= start:
                    dps = value
            self.damage_unit(tgt, dps * DT * rage)
            return
        if w.cooldown > 0:
            return
        w.cooldown = w.spec.interval
        dmg = w.spec.damage * rage
        if mode == "single":
            self.damage_unit(tgt, dmg)
        elif mode == "monolith":
            self.damage_unit(tgt, dmg + w.spec.extra["pct_current_hp"] * max(0.0, tgt.hp))
        elif mode == "ricochet":
            self.damage_unit(tgt, dmg)
            best = None
            bd = w.spec.extra["bounce_range"]
            for a in self.attackers_near(tgt.x, tgt.y, bd):
                if a is not tgt and not a.flying and t >= a.invisible_until:
                    d = _dist(a.x, a.y, tgt.x, tgt.y)
                    if d <= bd:
                        bd = d
                        best = a
            if best is not None:
                self.damage_unit(best, w.spec.extra["bounce_damage"] * rage)
        elif mode == "splash":
            air = w.targets in ("air", "both")
            ground = w.targets in ("ground", "both")
            if "splash_damage" in w.spec.extra:
                self.damage_unit(tgt, dmg - w.spec.extra["splash_damage"] * rage)
                self.splash_units(tgt.x, tgt.y, w.spec.splash, w.spec.extra["splash_damage"] * rage, air, ground, falloff=True)
            else:
                self.splash_units(tgt.x, tgt.y, w.spec.splash, dmg, air, ground)
        elif mode == "shell":
            # mortar shells land where the target was; fast troops can dodge
            self.pending.append(
                PendingDamage(t + w.spec.extra["flight"], tgt.x, tgt.y, w.spec.splash, dmg, False, True, "mortar")
            )

    def _eagle(self, w: Weapon):
        b = w.owner
        if self.deployed_housing < w.spec.extra["activation_housing"]:
            return
        if w.cooldown > 0:
            return
        pool = self._visible_attackers(w, w.range)
        if not pool:
            return
        # favorite target "Any" (wiki): take the nearest eligible unit
        best = min(pool, key=lambda a: _dist(a.x, a.y, b.x, b.y))
        rage = b.rage_mult if self.t < b.rage_until else 1.0
        extra = w.spec.extra
        for k in range(extra["shells"]):
            at = self.t + 1.5 + k * extra["shell_gap"]
            x = best.x + self.rng.uniform(-0.6, 0.6)
            y = best.y + self.rng.uniform(-0.6, 0.6)
            main = (w.spec.damage - extra["shockwave"]) * rage
            self.pending.append(PendingDamage(at, x, y, w.spec.splash, main, True, True, "eagle", False))
            self.pending.append(PendingDamage(at, x, y, extra["shockwave_radius"], extra["shockwave"] * rage, True, True, "eagle", False))
        w.cooldown = w.spec.interval

    def _sweeper(self, w: Weapon):
        if w.cooldown > 0:
            return
        b = w.owner
        hit = False
        for a in self.attackers_near(b.x, b.y, w.range):
            if not a.flying:
                continue
            dx, dy = a.x - b.x, a.y - b.y
            d = math.hypot(dx, dy)
            if d < w.min_range or d == 0:
                continue
            ang = math.atan2(dy, dx)
            if abs(_angle_diff(ang, w.facing)) > math.pi / 3:
                continue
            push = w.spec.extra["push"] * (1.0 - 0.5 * d / w.range)
            a.x += dx / d * push
            a.y += dy / d * push
            hit = True
        if hit:
            w.cooldown = w.spec.interval

    def _spell_tower(self, w: Weapon):
        if w.cooldown > 0:
            return
        b = w.owner
        mode = SPELL_TOWER_MODES[w.st_mode]
        near = [a for a in self.attackers_near(b.x, b.y, mode["range"]) if self.t >= a.invisible_until]
        if not near:
            return
        t = self.t
        if w.st_mode == "rage":
            self.add_effect(Effect("def_rage", b.x, b.y, mode["radius"], t + mode["duration"], value=mode["damage_boost"], team="def"))
        elif w.st_mode == "poison":
            cx = sum(a.x for a in near) / len(near)
            cy = sum(a.y for a in near) / len(near)
            self.add_effect(
                Effect("def_poison", cx, cy, mode["radius"], t + mode["duration"], value=mode["dps"], team="def", extra={"slow": mode["slow"]})
            )
        elif w.st_mode == "invis":
            self.add_effect(Effect("def_invis", b.x, b.y, mode["radius"], t + mode["duration"], team="def"))
        w.cooldown = mode["recharge"]


def _angle_diff(a, b):
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return d


_FACINGS = {
    "N": -math.pi / 2,
    "NE": -math.pi / 4,
    "E": 0.0,
    "SE": math.pi / 4,
    "S": math.pi / 2,
    "SW": 3 * math.pi / 4,
    "W": math.pi,
    "NW": -3 * math.pi / 4,
}


def _facing_angle(mode):
    return _FACINGS.get(mode or "E", 0.0)


# Defending hero levels: the user's live account (Clash API via ClashKing
# proxy, 2026-10-14). Used for their own base's defense.
_DEFENDING_HERO_LEVELS = {
    "Barbarian King": 92,
    "Archer Queen": 93,
    "Grand Warden": 67,
    "Royal Champion": 41,
    "Minion Prince": 72,
    "Dragon Duke": 13,
}
