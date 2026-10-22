"""Engine v2 battle loop.

Mechanics follow the wiki pages mirrored on 2026-10-15 (docs/WIKI_DIGEST.md).
Per-entity behaviour lives in sibling modules:

* defense.py - every defensive building's weapon, Builders, Spell Towers
* units.py   - troop special abilities, summons, death effects
* heroes.py  - hero equipment, pets, defending heroes
* spells.py  - all attacking spells and defensive spell fields
* traps.py   - traps
"""

from __future__ import annotations

import math
import os
import random

import numpy as np

from dataclasses import replace

from ..layout import Layout
from ..mechanics import BUILDING_TYPES, MARGIN, TRAP_NAMES, WORLD
from ..pathing import RES, Grid
from . import defense, effects, heroes, spells, stats, traps, units
from .entities import Building, Pending, Unit, Wall, dist
from .specs import spec, unit_numbers

# BASELAB_DT: time step for fast screening runs only (default 0.1 s; a
# coarser step changes results and must be validated against the full sim:
# tools/baselab/proof_proxy.py)
DT = float(os.environ.get("BASELAB_DT", "0.1"))
# BASELAB_FAST_END=1: end a battle once nothing attacking is alive or left to
# deploy, without idling to the time limit on Lightning/Earthquake the plan
# never casts. Stars and destruction are unchanged; only `time` of failed
# attacks differs. Opt-in for screening; the default follows the game rule.
FAST_END = os.environ.get("BASELAB_FAST_END") == "1"
MAX_TIME = 180.0  # Wiki: Multiplayer Battles, three minutes of combat.
SCOUT_TIME = 30.0  # Wiki: Multiplayer Battles, maximum scouting time.
BUCKET = 4.0
# game data v18.200.9: CHAR_VS_CHAR_RADIUS_FOR_ATTACKER.NumberValue=7 -> 7 tiles.
ENGAGE_RADIUS = 7.0
# game data v18.200.9: ALLIANCE_ALERT_RADIUS.NumberValue=700 -> 7 tiles.
AWARE_RADIUS = 7.0
# game data v18.200.9: Town Hall.CombatActivationDelay=500 -> the TH12-17
# weapon starts fighting 0.5 s after it is triggered (TH damaged or 51%).
TH_ACTIVATION_DELAY = 0.5
# game data v18.200.9: CLAN_CASTLE_RADIUS.NumberValue=13 -> 13 tiles (whole
# tiles, like CHAR_VS_CHAR_RADIUS_FOR_ATTACKER=7). The wiki Clan Castle
# infobox also gives "Trigger Radius 13 tiles"; its prose says 12.
CC_TRIGGER_RADIUS = 13.0
# Path goals are half-tile cells whose centres lie at least 0.25 tiles from a
# hitbox edge and up to 0.35 from a point, so a shorter reach left no goal
# cell and the unit never moved (Bear, wiki range 0.2, made 0 attacks in
# 4 Druid battles). Goals use at least the half-cell diagonal; the last
# stretch is walked straight and the attack still checks the true range.
GOAL_REACH_MIN = math.sqrt(0.5) / RES + 1e-6
# Wall path costs retain their existing heuristic ("smash" walks as "ignore").
WALL_COST = {"normal": 12.0, "ignore": 0.0, "fly": 0.0}

# Ranked difficulty modifiers (wiki "Ranked Battles"): defense DPS bonus,
# defending hero DPS/HP bonus, Guardian DPS/HP bonus, attacking hero penalty.
MODIFIERS = {
    None: (0.0, 0.0, 0.0, 0.0),
    "legend3": (0.10, 0.10, 0.05, 0.05),
    "legend2": (0.15, 0.15, 0.10, 0.10),
    "legend1": (0.20, 0.20, 0.20, 0.20),
}


def _research_name(name: str) -> str:
    """The researched troop behind a Super Troop's level (wiki: Clan Castle,
    Super Troops need the base troop's level)."""
    if stats.record(name)["kind"] == "super_troop":
        for column in stats.attrs(name).get("raw", {}):
            base = column.removesuffix(" Level Required")
            if (
                column.endswith(" Level Required")
                and base in stats.registry()
                and stats.record(base)["kind"] == "troop"
            ):
                return base
    return name


def _required_lab(research_name: str, level: int):
    # Wiki: troop research tables (Laboratory Level Required).
    required = stats.get(research_name, level, "Laboratory Level Required")
    if required is None:
        th = stats.required_town_hall(research_name, level)
        required = stats.max_level("Laboratory", int(th)) if th is not None else None
    return required


def donated_level(name: str, level: int | None, castle_level: int | None) -> int:
    """Level of a troop donated to a Clan Castle of castle_level.

    Wiki: Clan Castle, the Laboratory level cap restricts donated units to
    the highest level that Laboratory level allows; reinforcements come at
    the maximum the Castle allows. Higher donations are reduced, not refused.
    level None = the best donor level (the troop's maximum)."""
    if level is None:
        level = stats.max_level(name, 18) or 1
    lab_cap = (
        stats.get("Clan Castle", castle_level, "~Laboratory Level Cap")
        if castle_level
        else None
    )
    research = _research_name(name)
    required = _required_lab(research, level)
    if lab_cap is None or required is None:
        return level  # no cap data: keep the level as given
    while required > lab_cap and level > 1:
        level -= 1
        required = _required_lab(research, level)
        if required is None:
            break
    return level


class Battle:
    DT = DT

    def __init__(
        self,
        layout: Layout,
        plan,
        *,
        seed: int = 0,
        town_hall: int = 16,
        record: bool = False,
        defense_levels: dict | None = None,
        hero_levels: dict | None = None,
        cc_troops: list | None = None,
        cc_level: dict | None = None,
        max_time: float = MAX_TIME,
        modifier: str | None = None,
        defense_ammo: dict | None = None,
        allow_synthetic_cc: bool = False,
        builder_starts: dict | None = None,
        battle_mode: str = "ranked",
        upgrading=(),
        crafting_phase: int = 4,
        crafting_date: str = "2026-10-15",
        scouting: bool = False,
    ):
        self.rng = random.Random(seed)
        self.modifier = modifier
        d, h, g, a = MODIFIERS[modifier]
        self.def_mult, self.def_hero_mult, self.guardian_mult, self.atk_hero_mult = 1.0 + d, 1.0 + h, 1.0 + g, 1.0 - a
        self.portal_stash: list = []
        self.first_destroy_t = None
        self.first_deploy_t = None
        self.defense_ammo = defense_ammo or {}
        self.allow_synthetic_cc = allow_synthetic_cc
        self.battle_mode = battle_mode
        self.upgrading = set(upgrading)
        self.crafting_phase = crafting_phase
        self.crafting_date = crafting_date
        self.builders = []
        self.builder_starts = builder_starts or {}
        self.portal_ready_at = 0.0
        self.t = 0.0
        # Existing plans use combat-relative times and start without scouting.
        self.scouting = scouting
        self.scout_time = 0.0
        self.ended = False
        self.town_hall = town_hall
        self.record = record
        self.max_time = max_time
        self.log: list = []
        self.frames: list = []
        self.grid = Grid(WORLD)
        self.buildings: list[Building] = []
        self.walls: dict[tuple[int, int], Wall] = {}
        self.traps = []
        self.attackers: list[Unit] = []
        self.defenders: list[Unit] = []
        self.fields = []
        self.pending: list[Pending] = []
        self.deployed_housing = 0
        self.monolith_housing = 0
        self._uid = 0
        self.cc_building = None
        self.cc_queue: list = []
        self.cc_released = False
        self.th = None
        self._th_on_at = None  # when the Town Hall weapon fights (None: dormant)
        # explicit levels win; otherwise the layout's owner's levels; else max
        self.defense_levels = {**(layout.levels or {}), **(defense_levels or {})}
        self.hero_levels = {**(layout.hero_levels or {}), **(hero_levels or {})}
        self.wall_level = layout.wall_level
        self.cc_level = cc_level or {}
        self.damage_by_source: dict = {}
        self.kills_by_source: dict = {}
        self._src = "?"
        self._src_obj = None  # building or unit currently attacking
        self._effect = "attack"
        self._poison: dict = {}
        self._clones: list = []
        self._setup(layout, cc_troops)
        self.total_counted = sum(1 for b in self.buildings if b.counted)
        self.destroyed_counted = 0
        self.no_deploy = self._no_deploy_tiles(layout)
        self.plan = plan
        self._onboard_cargo = self._attack_cargo(plan)
        self.deployments = sorted(plan.deployments(self), key=lambda d: d.time)
        self._next_deploy = 0
        self._bucket_grid: dict = {}

    # ======================================================= town hall weapon
    @property
    def th_active(self) -> bool:
        """The Town Hall weapon fights and counts as a defense."""
        return self._th_on_at is not None and self.t >= self._th_on_at

    @th_active.setter
    def th_active(self, value: bool):
        # Direct assignment: always-on weapons (TH17 Inferno Artillery) and
        # unavailable Town Halls; triggers go through trigger_th().
        self._th_on_at = -math.inf if value else None

    def trigger_th(self):
        """The Giga weapon emerges (wiki: Town Hall Giga Weapons, when the
        Town Hall is damaged or 51% is destroyed) and fights after
        TH_ACTIVATION_DELAY; it used to fight in the same tick."""
        if (
            self._th_on_at is None
            and self.th is not None
            and self.th.weapon is not None
            and not self.th.extra.get("unavailable")
        ):
            self._th_on_at = self.t + TH_ACTIVATION_DELAY

    # ================================================================ setup
    def level_of(self, key: str, name: str) -> int:
        level = self.defense_levels.get(key, stats.max_level(name, self.town_hall))
        if level is None:
            raise ValueError(f"{name} is unavailable at Town Hall {self.town_hall}")
        return stats.validate_level(name, level, self.town_hall)

    def _setup(self, layout: Layout, cc_troops):
        th = self.town_hall
        for i, p in enumerate(layout.buildings):
            bt = BUILDING_TYPES[p.key]
            x, y = p.x + MARGIN, p.y + MARGIN
            if p.key == "banner":
                b = Building(i, p.key, bt.name, "other", x, y, bt.size, 1.0, 1.0, counted=False)
                b.alive = False
                self.buildings.append(b)
                continue
            if p.key == "th":
                level = th
                hp = stats.get("Town Hall", level, "hitpoints", default=10000.0)
            elif p.key == "crafting" or (not bt.counted and bt.name not in stats.registry()):
                level, hp = 1, 1000.0  # Crafting Station: set by defense._attach_crafted
            else:
                level = self.level_of(p.key, bt.name)
                hp = stats.get(bt.name, level, "hitpoints", "Hitpoints", default=1000.0)
            a = stats.attrs(bt.name) if bt.name in stats.registry() else {}
            hitbox = a.get("hitbox") or max(1, bt.size - 1)
            is_def = bt.kind == "defense"
            b = Building(i, p.key, bt.name, bt.kind, x, y, bt.size, hitbox, hp, counted=bt.counted, is_defense=is_def, mode=p.mode, level=level)
            if bt.weapon_key or p.key in ("th", "bh"):
                defense.attach_weapon(self, b)
            b.extra["unavailable"] = (
                self.battle_mode == "multiplayer"
                and p.key != "crafting"
                and (p.key in self.upgrading or i in self.upgrading)
            )
            if b.extra["unavailable"] and p.key == "th":
                self.th_active = False
            if p.key == "tesla":
                b.revealed = False
            if p.key == "th":
                self.th = b
            if p.key == "cc":
                self.cc_building = b
            self.buildings.append(b)
            self.grid.block_square(b.x, b.y, b.half_hit)
        # sorted: a set's iteration order depends on its insertion history, and
        # the wall order is a result (splash and area hits visit walls in it),
        # so the same layout must always give the same order (and the Rust
        # engine, which builds battles from layouts, reproduces it).
        for tx, ty in sorted(layout.walls):
            level = layout.wall_levels.get(
                (tx, ty), self.wall_level or stats.max_level("Wall", th)
            )
            stats.validate_level("Wall", level, th)
            # Wiki: Wall/Home Village, Hitpoints by segment level.
            wall_hp = stats.get("Wall", level, "Hitpoints")
            w = Wall(tx + MARGIN, ty + MARGIN, wall_hp)
            self.walls[(w.tx, w.ty)] = w
            self.grid.set_wall(w.tx, w.ty, True)
        for tp in layout.traps:
            self.traps.append(traps.make_trap(self, tp))
        banners = [b for b in self.buildings if b.key == "banner"]
        for hero_name, banner in zip(layout.heroes, banners):
            heroes.spawn_defending_hero(self, hero_name, banner)
        if (
            th >= 18
            and self.th is not None
            and layout.guardian
            and not (
                self.battle_mode == "multiplayer"
                and ("guardian" in self.upgrading or self.th.extra.get("unavailable"))
            )
        ):
            heroes.spawn_guardian(self, layout.guardian, self.th)
        entries = list(cc_troops if cc_troops is not None else layout.cc_troops)
        levels = dict(self.cc_level)
        for entry in entries:
            name = (
                entry if isinstance(entry, str) else entry.get("name") or entry["type"]
            )
            levels.setdefault(name, stats.max_level(name, 18))
        self.cc_queue = units.cargo_entries(self, entries, levels)
        if self.cc_building is not None and not self.allow_synthetic_cc:
            # Wiki: Clan Castle, capacity belongs to the actual Castle level.
            capacity = stats.get(
                "Clan Castle", self.cc_building.level, "Troop Capacity"
            )
            housing = sum(
                unit_numbers(entry["name"], entry["level"])["housing"]
                for entry in self.cc_queue
            )
            if housing > capacity:
                raise ValueError(
                    f"Defending Clan Castle housing {housing} exceeds {capacity}"
                )
            for entry in self.cc_queue:
                name = entry["name"]
                if stats.record(name)["kind"] not in ("troop", "super_troop"):
                    raise ValueError(f"{name} cannot be donated to a Clan Castle")
                stats.row(name, entry["level"])
                entry["level"] = donated_level(
                    name, entry["level"], self.cc_building.level
                )

    def _attack_cargo(self, plan) -> list:
        """The attacker's Clan Castle troops (released by a siege or the
        Castle drop), at levels the attacker's own Castle allows (wiki: Clan
        Castle, Laboratory level cap). They used to take the defending Town
        Hall's maximum level. Read by units.onboard_cargo."""
        castle = getattr(plan, "clan_castle_level", None)
        if castle is None:
            castle = stats.max_level(
                "Clan Castle", getattr(plan, "town_hall", None) or self.town_hall
            )
        given = getattr(plan, "cc_levels", None) or {}
        entries = []
        for entry in getattr(plan, "cc_troops", None) or []:
            item = {"name": entry} if isinstance(entry, str) else dict(entry)
            name = item.get("name") or item["type"]
            # a given level is only reduced to the cap
            item["level"] = donated_level(
                name, item.get("level") or given.get(name), castle
            )
            entries.append(item)
        return units.cargo_entries(self, entries)

    def _no_deploy_tiles(self, layout: Layout) -> set:
        """No-spawn zone: one tile around every structure (wiki: Walls);
        Hidden Teslas make none (wiki: Hidden Tesla). Hero banners always
        count. Destroyed buildings and walls stop blocking (see can_deploy)."""
        self._banner_tiles = set()
        for p in layout.buildings:
            if p.key == "banner":
                self._banner_tiles.update((tx + MARGIN, ty + MARGIN) for tx, ty in p.tiles())
        self._nd_version = None
        return self._live_no_deploy()

    def _live_no_deploy(self) -> set:
        if self._nd_version == self.grid.version:
            return self._nd_cache
        occupied = set(self._banner_tiles)
        for b in self.buildings:
            if not b.alive or b.key in ("tesla", "banner"):
                continue
            x0, y0 = int(round(b.x - b.size / 2.0)), int(round(b.y - b.size / 2.0))
            for dx in range(b.size):
                for dy in range(b.size):
                    occupied.add((x0 + dx, y0 + dy))
        for key, w in self.walls.items():
            if w.alive:
                occupied.add(key)
        blocked = set()
        for tx, ty in occupied:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    blocked.add((tx + dx, ty + dy))
        self._nd_cache, self._nd_version = blocked, self.grid.version
        return blocked

    def can_deploy(self, x: float, y: float) -> bool:
        if not (0 <= x < WORLD and 0 <= y < WORLD):
            return False
        tx, ty = int(x), int(y)
        return (tx, ty) not in self._live_no_deploy()

    def deploy_tiles(self) -> list:
        """Every legal drop tile right now (tile centres), corridors and open
        pockets included; cached per grid version."""
        if getattr(self, "_dt_version", None) == self.grid.version:
            return self._dt_cache
        blocked = self._live_no_deploy()
        self._dt_cache = [(x + 0.5, y + 0.5) for x in range(WORLD) for y in range(WORLD) if (x, y) not in blocked]
        self._dt_version = self.grid.version
        return self._dt_cache

    def inside_spots(self) -> list:
        """Legal drop tiles enclosed by standing walls (holes in the base),
        as tile centres. Players drop into these (wiki: Walls - avoid gaps
        wider than two squares)."""
        blocked = self._live_no_deploy()
        walls = {k for k, w in self.walls.items() if w.alive}
        seen = set()
        q = [(i, j) for i in range(WORLD) for j in (0, WORLD - 1)] + [(j, i) for i in range(WORLD) for j in (0, WORLD - 1)]
        seen.update(q)
        while q:
            x, y = q.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if 0 <= n[0] < WORLD and 0 <= n[1] < WORLD and n not in walls and n not in seen:
                    seen.add(n)
                    q.append(n)
        return [(x + 0.5, y + 0.5) for x in range(WORLD) for y in range(WORLD) if (x, y) not in seen and (x, y) not in blocked and (x, y) not in walls]

    # ================================================================ units
    def spawn(self, name, team, x, y, *, level=None, kind="troop", group="main", owner=None, town_hall=None) -> Unit:
        th = town_hall or self.town_hall
        if level is None:
            level = stats.max_level(name, th) or 1
        nums = unit_numbers(name, level)
        sp = heroes.summon_spec(name, spec(name))
        self._uid += 1
        u = Unit(
            self._uid, name, kind, team, x, y,
            hp=nums["hp"], dmg=nums["dmg"], interval=nums["interval"], range_=nums["range"], speed=nums["speed"],
            housing=nums["housing"], flying=nums["flying"] if sp.walls != "fly" else True,
            hits_air=nums["hits_air"], hits_ground=nums["hits_ground"], spec=sp, level=level,
        )
        u.group = group
        u.owner = owner
        u.spawned_at = self.t
        u.active_at = self.t
        # Facing begins towards the village and follows movement and attacks.
        u.extra["facing"] = (WORLD / 2.0 - x, WORLD / 2.0 - y)
        if u.extra["facing"] == (0.0, 0.0):
            u.extra["facing"] = (1.0, 0.0)
        u.is_hero = kind in ("hero", "hero_clone")  # wiki: Magic Mirror
        (self.attackers if team == "atk" else self.defenders).append(u)
        units.on_spawn(self, u)
        if team == "atk":
            heroes.new_member(self, u)
        if owner is not None:
            units.inherit_clone(self, owner, u)
        return u

    def deploy(self, d) -> Unit:
        if not self.can_deploy(d.x, d.y):
            # the game will not place a troop on a no-drop tile: the drop lands
            # on the nearest legal tile instead (plans add a little scatter)
            x, y = min(self.deploy_tiles(), key=lambda p: (p[0] - d.x) ** 2 + (p[1] - d.y) ** 2)
            d = replace(d, x=x, y=y)
        self.start_battle()
        if self.first_deploy_t is None:
            self.first_deploy_t = self.t
        kind = "hero" if d.name in heroes.HEROES else ("siege" if stats.record(d.name)["kind"] == "siege" else "troop")
        u = self.spawn(d.name, "atk", d.x, d.y, level=d.level, kind=kind, group=d.group, town_hall=d.town_hall)
        k = getattr(self.plan, "strength", 1.0)
        if u.name == "Grand Warden":
            mode = getattr(d, "mode", None)
            if mode is None:
                mode = "ground" if getattr(self.plan, "ground", True) else "air"
            if mode not in ("air", "ground"):
                raise ValueError("Grand Warden mode must be air or ground")
            u.flying = mode == "air"
            if u.flying and os.environ.get("BASELAB_FLYER_RANGE", "gamedata") == "gamedata":
                # game data v18.200.9: Grand Warden.AltAttackRange=650 -> 6.5 tiles in air mode.
                from .specs import _game_ranges

                u.range = _game_ranges().get(u.name + "|alt", u.range)
        if k != 1.0:
            u.hp *= k
            u.max_hp *= k
            u.base_max_hp *= k
            u.dmg *= k
            # read by damage taken from the tables at use (Log Launcher logs),
            # which this scaling of u.dmg does not reach
            u.extra["strength"] = k
        if u.is_hero:
            heroes.equip(self, u, self.plan)
            if self.atk_hero_mult != 1.0:  # league penalty incl. equipment boosts (wiki)
                m = self.atk_hero_mult
                u.hp *= m
                u.max_hp *= m
                u.base_max_hp *= m
                u.dmg *= m
        source = getattr(d, "source", "army")
        # Wiki: Eagle Artillery counts siege as one and direct reinforcements as zero.
        if source not in ("cc", "clan_castle"):
            if kind == "siege":
                self.deployed_housing += 1
            elif u.is_hero:
                self.deployed_housing += 25
            else:
                self.deployed_housing += u.housing
        if kind == "siege" and getattr(self.plan, "siege_donated", False):
            source = "donated_siege"
        u.extra["deployment_source"] = source
        if source == "army" and stats.record(d.name)["kind"] in (
            "troop",
            "hero",
            "siege",
        ):
            # Heroes count 25; own siege counts 1 (wiki: Monolith Arrow).
            if u.is_hero:
                self.monolith_housing += 25
            elif kind == "siege":
                self.monolith_housing += 1
            else:
                self.monolith_housing += u.housing
        if self.record:
            self.log.append((round(self.t, 1), "deploy", d.name, round(d.x, 1), round(d.y, 1)))
        return u

    # ============================================================== queries
    def raw_destruction(self) -> float:
        return 100.0 * self.destroyed_counted / max(1, self.total_counted)

    def destruction(self) -> float:
        # Wiki: Multiplayer Battles rounds damage up to the next percent.
        total = max(1, self.total_counted)
        return (100 * self.destroyed_counted + total - 1) // total

    def stars(self) -> int:
        s = 0
        if self.destruction() >= 50.0:
            s += 1
        if self.th is not None and not self.th.alive:
            s += 1
        if self.destroyed_counted >= self.total_counted:
            s += 1
        return s

    def building_targetable(self, b) -> bool:
        if not b.alive or not b.counted and b.key not in ("th",):
            return False
        t = self.t
        if (
            t < b.overgrown_until
            or t < b.invisible_until
            or t < b.extra.get("yellow_until", 0.0)
        ):
            return False
        if b.key == "tesla" and not b.revealed:
            return False
        return True

    def is_defense_target(self, b) -> bool:
        if b.key == "th":
            # Wiki: Town Hall 18 has no weapon or defensive classification.
            return b.weapon is not None and self.th_active
        return b.is_defense

    def attackers_near(self, x, y, r):
        grid = self._bucket_grid
        out = []
        r2 = r * r
        for i in range(int((x - r) / BUCKET), int((x + r) / BUCKET) + 1):
            for j in range(int((y - r) / BUCKET), int((y + r) / BUCKET) + 1):
                cell = grid.get((i, j))
                if cell:
                    for u in cell:
                        dx = u.x - x
                        dy = u.y - y
                        if (
                            dx * dx + dy * dy <= r2
                            and u.alive
                            and not u.extra.get("suspended")
                        ):
                            out.append(u)
        return out

    def defenders_near(self, x, y, r):
        r2 = r * r
        return [u for u in self.defenders if u.alive and (u.x - x) ** 2 + (u.y - y) ** 2 <= r2]

    def can_hit(self, attacker: Unit, victim: Unit) -> bool:
        if not victim.alive or victim.underground or victim.extra.get("leaping"):
            return False
        if victim.name == "Totem":
            return True  # counts as both ground and air (wiki)
        return attacker.hits_air if victim.flying else attacker.hits_ground

    # =============================================================== damage
    def hit_unit(self, u: Unit, amount: float, *, src=None, kind="normal", attacker=None):
        if not u.alive or amount <= 0:
            return 0.0
        t = self.t
        if u.underground and kind != "th_poison":
            return 0.0  # Wiki: Miner permits Town Hall death Poison underground.
        source = attacker if attacker is not None else self._src_obj
        effect = kind if kind != "normal" else self._effect
        if kind == "th_poison":
            effect = "poison"
        if (
            effects.invulnerable(u, t)
            or u.attached(t)
            or u.extra.get("suspended")
            or u.extra.get("leaping")
        ):
            return 0.0
        if u.dash is not None and effect not in ("poison", "spell"):
            return 0.0
        if "recalled" in u.extra:
            return 0.0
        if kind == "trap" and u.name == "Dragon Duke" and units.duke_alone(self, u):
            # Wiki: Dragon Duke, 20% (history: 50% -> 40% May 26 2026 -> 20%
            # July 14 2026). game data v18.200.9 DragonDukeRageWhenAlone.
            # TrapShieldProtectionPercent=50 predates both changes.
            amount *= 0.8
        # Wiki: Ice Block Spell, the strongest active damage reduction wins.
        red = u.dmg_taken_mult if t < u.dmg_taken_until else 1.0
        red = min(red, 1.0 - effects.torch_stats(u, t)[1])
        if u.kit is not None:
            red = min(red, heroes.damage_taken_mult(self, u))
        if t < u.iceblock_until:
            red = min(red, 1.0 - u.iceblock_red)
        for reduction, until in u.extra.get("iceblocks", {}).values():
            if t < until:
                red = min(red, 1.0 - reduction)
        amount *= red
        if (
            self.def_mult != 1.0
            and u.team == "atk"
            and isinstance(source, Building)
            and effect not in ("death", "counter", "spell", "poison")
        ):
            amount *= self.def_mult
        armor = u.extra.get("armor_hp", 0.0)
        if armor > 0:
            u.extra["armor_hp"] = max(0.0, armor - amount)
            amount = min(armor, amount)
        if u.team == "atk":
            s = src or self._src
            self.damage_by_source[s] = self.damage_by_source.get(s, 0.0) + min(amount, u.hp)
        if armor <= 0:
            remaining_bonus = u.extra.get("aura_hp", 0.0)
            u.extra["aura_hp"] = max(0.0, remaining_bonus - amount)
            u.hp -= amount
        u.last_hit = t
        u.extra["last_damage_source"] = source
        if (
            isinstance(source, Unit)
            and source.team != u.team
            and u.team == "atk"
            and effect in ("attack", "secondary", "chain")
        ):
            u.aware_until = t + 2.0
            u.extra["troop_hit_at"] = t
        units.on_damaged(self, u, amount)
        if u.kit is not None and u.alive:
            heroes.on_damaged(self, u, amount, source, effect)
        if (
            u.hp <= 0
            and u.team == "atk"
            and u.is_hero
            and u.kit is not None
            and not u.ability_used
            and u.alive
            and getattr(self.plan, "auto_ability_on_ko", True)
        ):
            # an unused ability fires on its own when the hero is about to be
            # defeated (wiki: Royal Champion, "Automatically use Hero
            # Abilities on KO", on by default)
            u.hp = 1.0
            heroes.activate(self, u)
            if self.record:
                self.log.append((round(self.t, 1), "ability", u.name, "on KO"))
        if u.hp <= 0:
            if u.team == "atk":
                s = src or self._src
                self.kills_by_source[s] = self.kills_by_source.get(s, 0) + max(1, u.housing)
            self.kill(u)
        return amount

    def kill(self, u: Unit):
        if not u.alive:
            return
        effects.record_death(self, u)
        if u.kit is not None and heroes.on_death(self, u):
            return
        u.alive = False
        u.hp = 0.0
        heroes.summon_death(self, u)
        units.on_death(self, u)
        if u.is_hero and u.team == "atk":
            spells.maybe_revive(self, u)
        if self.record:
            self.log.append((round(self.t, 1), "dies", u.name, u.team))

    def hit_building(self, b, amount: float, *, src=None, kind="normal"):
        if not b.alive or amount <= 0:
            return 0.0
        if isinstance(b, Building):
            if self.t < b.overgrown_until:
                return 0.0
            # Meteor Staff does not trigger Invisibility Towers.
            if self._effect != "meteor":
                b.last_hit = self.t
            source = self._src_obj
            if (
                isinstance(source, Unit)
                and source.team == "atk"
                and self._effect not in ("meteor", "spell", "poison")
            ):
                # Wiki: Spell Tower, surviving units and equipment can trigger Invisibility.
                for tower in self.buildings:
                    weapon = tower.weapon
                    if (
                        tower.alive
                        and weapon is not None
                        and weapon.kind == "spell_tower"
                        and weapon.mode == "invis"
                        and weapon.cooldown <= 0
                        and dist(tower.x, tower.y, b.x, b.y) <= 4.5
                        and (b.hp > amount or tower is b)
                    ):
                        weapon.extra.setdefault("hit_triggers", {}).setdefault(
                            source, self.t
                        )
            if b is self.th:
                self.trigger_th()
        b.hp -= amount
        if b.hp <= 0:
            self.destroy(b)
        return amount

    def destroy(self, b):
        if not b.alive:
            return
        b.alive = False
        b.hp = 0.0
        if isinstance(b, Wall):
            self.grid.set_wall(b.tx, b.ty, False)
            return
        self.grid.block_square(b.x, b.y, b.half_hit, False)
        if b.counted:
            self.destroyed_counted += 1
            if self.first_destroy_t is None:
                self.first_destroy_t = self.t
        defense.on_destroyed(self, b)
        if self.destruction() >= 51.0:
            self.trigger_th()
            for o in self.buildings:
                if o.key == "tesla":
                    defense.reveal_tesla(self, o)
        if self.record:
            self.log.append((round(self.t, 1), "destroyed", b.key, round(self.destruction(), 1)))

    def splash_buildings(self, x, y, radius, damage, *, walls=True, exclude=None, kind="normal", wall_mult=1.0):
        for b in self.buildings:
            if b.alive and b is not exclude and b.edge_distance(x, y) <= radius:
                self.hit_building(b, damage, kind=kind)
        if walls and radius >= 0.5:
            r = int(radius) + 1
            for tx in range(int(x) - r, int(x) + r + 1):
                for ty in range(int(y) - r, int(y) + r + 1):
                    w = self.walls.get((tx, ty))
                    if w is not None and w.alive and w.edge_distance(x, y) <= radius:
                        self.hit_building(w, damage * wall_mult, kind=kind)

    def splash_units(self, x, y, radius, damage, hits_air, hits_ground, *, team="atk", falloff=False, src=None, kind="normal", exclude=None):
        pool = self.attackers_near(x, y, radius) if team == "atk" else self.defenders_near(x, y, radius)
        for u in pool:
            if u is exclude or u.underground:
                continue
            if u.name != "Totem":
                if u.flying and not hits_air or not u.flying and not hits_ground:
                    continue
            d = dist(u.x, u.y, x, y)
            amt = damage * (1.0 - 0.5 * d / radius) if falloff and radius > 0 else damage
            self.hit_unit(u, amt, src=src, kind=kind)

    def add_pending(self, p: Pending):
        if p.actor is None:
            p.actor = self._src_obj
        if p.effect is None:
            p.effect = self._effect
        if p.target is None:
            p.target = p.extra.get("track")
        if p.released_at is None:
            p.released_at = self.t
        self.pending.append(p)

    # ================================================================= loop
    def start_battle(self):
        if self.ended:
            raise ValueError("Battle has ended")
        self.scouting = False

    def end_battle(self):
        # Wiki: Multiplayer Battles, End Battle takes effect immediately.
        self.ended = True

    def run(self):
        validate = getattr(self.plan, "require_legal", None)
        if validate is not None:
            validate()
        while not self.ended and (self.scouting or self.t < self.max_time):
            self.step()
            if self.scouting:
                continue
            if self.destroyed_counted >= self.total_counted:
                break
            if self.offense_finished():
                break
        self.ended = True
        return self.result()

    def offense_finished(self):
        # Wiki: Healer, the battle ends once no non-healing troops are alive
        # or left to deploy and no Lightning or Earthquake Spells are left
        # to deploy. So a plan that never casts its spare Lightning or
        # Earthquake runs to max_time after a wipe (a player would cast them
        # or end the battle). Stars and destruction are unchanged, and a
        # 3-star ends at 100% first, so the time to 3-star is not affected;
        # only `time` of failed attacks reads 180 (tools/baselab/ab_test.py
        # counts those as timeouts, not wipes).
        if any(
            u.alive
            and u.name not in ("Healer", "Unicorn", "Totem")
            and u.kind != "siege_idle"
            for u in self.attackers
        ):
            return False
        if any(d.name != "Healer" for d in self.deployments[self._next_deploy :]):
            return False
        pending = getattr(self.plan, "has_offensive_pending", None)
        if pending is not None:
            if pending(self):
                return False
        elif self.plan.has_pending():
            return False
        if not FAST_END and any(
            getattr(self.plan, "spells", {}).get(key, 0) for key in ("lightning", "eq")
        ):
            return False
        if any(
            isinstance(p.actor, Unit) and p.actor.team == "atk"
            # game data v18.200.9: Earthquake.NumberOfHits=5 -> wait for every hit.
            or "quake" in p.extra and p.team == "def"
            for p in self.pending
        ) or any(
            f.kind
            in (
                "lightning",
                "quake",
                "rolling_log",
                "revive_cast",
                "revive_due",
                "summon",
                "santa",
                "birthday",
            )
            for f in self.fields
        ):
            return False
        return True

    def release_siege(self, name=None):
        for unit in self.attackers:
            if (
                unit.alive
                and unit.kind == "siege"
                and (name is None or unit.name == name)
            ):
                self.kill(unit)
                return True
        return False

    def result(self):
        from .result import Result

        if self.record and getattr(self, "_onboard_cargo", None):
            self.log.append((round(self.t, 1), "onboard_cc", list(self._onboard_cargo)))

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
        if self.ended or self.t >= self.max_time:
            return
        if self.scouting:
            self.scout_time = min(SCOUT_TIME, self.scout_time + DT)
            if self.scout_time >= SCOUT_TIME:
                self.start_battle()
            return
        t = self.t
        while self._next_deploy < len(self.deployments) and self.deployments[self._next_deploy].time <= t:
            self.deploy(self.deployments[self._next_deploy])
            self._next_deploy += 1
        self._buckets()
        self.plan.on_tick(self)
        if self.ended:
            return
        self._src_obj = None
        self._src = "spell"
        self._effect = "spell"
        spells.tick(self)
        self._resolve_pending()
        self._src = "trap"
        self._src_obj = None
        self._effect = "trap"
        traps.tick(self)
        self._castle()
        heroes.guardians_tick(self)
        defense.bell_tick(self)
        defense.builders_tick(self)
        for u in list(self.attackers):
            if u.alive:
                with effects.damage_source(self, u, "attack"):
                    self._act_attacker(u)
        self._separate()
        for b in self.buildings:
            if b.alive and b.weapon is not None:
                self._src = b.key
                with effects.damage_source(self, b, "attack"):
                    defense.act(self, b.weapon)
        for u in list(self.defenders):
            if u.alive:
                self._src = "unit:" + u.name
                with effects.damage_source(self, u, "attack"):
                    self._act_defender(u)
        self._src_obj = None
        if int(round(t * 10)) % 50 == 0:
            self.grid.prune()
        if len(self.attackers) > 160:
            self.attackers = [
                u
                for u in self.attackers
                if u.alive or u.is_hero or "recalled" in u.extra
            ]
        if len(self.defenders) > 80:
            self.defenders = [u for u in self.defenders if u.alive]
        if self.record and int(round(t * 10)) % 5 == 0:
            self.frames.append(self._snapshot())
        self.t = round(t + DT, 6)

    def _snapshot(self):
        return {
            "t": round(self.t, 1),
            "u": [(u.name, round(u.x, 2), round(u.y, 2), round(u.hp / max(1.0, u.max_hp), 2), u.team) for u in self.attackers + self.defenders if u.alive],
            "dead": [b.id for b in self.buildings if not b.alive and b.key != "banner"],
            "walls": [k for k, w in self.walls.items() if not w.alive],
        }

    def _resolve_pending(self):
        t = self.t
        due = [p for p in self.pending if p.at <= t]
        self.pending = [p for p in self.pending if p.at > t]
        for pending in due:
            # game data v18.200.9: SkeletonTrap.TimeBetweenSpawnsMs=150 -> staggered births.
            if "trap_skeleton" in pending.extra:
                traps.spawn_skeleton(
                    self, pending.extra["trap_skeleton"], pending.x, pending.y
                )
                continue
            if pending.extra.get("summon"):
                name, level, group, owner = pending.extra["summon"]
                self.spawn(
                    name,
                    pending.team,
                    pending.x,
                    pending.y,
                    level=level,
                    kind="summon",
                    group=group,
                    owner=owner,
                )
                continue
            # Released attacks keep their origin through invisibility and death.
            with effects.damage_source(self, pending.actor, pending.effect):
                self._src = pending.src
                if "quake" in pending.extra:
                    # game data v18.200.9: Earthquake.TimeBetweenHitsMS=400.
                    spells.quake_hit(self, pending.extra["quake"])
                    continue
                if "hero_impact" in pending.extra:
                    heroes.projectile_impact(self, pending)
                    continue
                if pending.extra.get("direct"):
                    target = pending.target
                    if isinstance(target, Unit):
                        if target.indirect_targetable(t):
                            self.hit_unit(target, pending.damage)
                    elif target.alive:
                        self.hit_building(target, pending.damage)
                    continue
                if "troop_impact" in pending.extra:
                    units.projectile_impact(self, pending)
                    continue
                if "healing" in pending.extra:
                    pending.target.heal(pending.extra["healing"])
                    continue
                x, y = pending.x, pending.y
                if pending.target is not None:
                    x, y = pending.target.x, pending.target.y
                if pending.src == "eagle":
                    # Wiki: Eagle Artillery, shells land at the annulus boundary.
                    ox, oy = pending.extra["origin"]
                    dx, dy = x - ox, y - oy
                    distance = math.hypot(dx, dy)
                    if distance == 0:
                        dx, dy = pending.x - ox, pending.y - oy
                        distance = math.hypot(dx, dy)
                    landing = min(
                        pending.extra["max_range"],
                        max(pending.extra["min_range"], distance),
                    )
                    x, y = ox + dx * landing / distance, oy + dy * landing / distance
                self.splash_units(
                    x,
                    y,
                    pending.radius,
                    pending.damage,
                    pending.hits_air,
                    pending.hits_ground,
                    team=pending.team,
                    falloff=pending.falloff,
                    src=pending.src,
                    # Air Bomb shells are trap damage (Dragon Duke reduction).
                    kind="trap" if str(pending.src).startswith("trap:") else "normal",
                )
                if pending.extra.get("push"):
                    for unit in self.attackers_near(x, y, pending.radius):
                        if (
                            unit.alive
                            and not unit.is_hero
                            and unit.kind not in ("pet", "siege", "siege_idle")
                            and 0 < unit.housing <= pending.extra["push_housing"]
                            and not unit.underground
                        ):
                            dx, dy = unit.x - x, unit.y - y
                            distance = math.hypot(dx, dy)
                            if not distance:
                                ox, oy = pending.extra["origin"]
                                dx, dy = x - ox, y - oy
                                distance = math.hypot(dx, dy)
                            if distance:
                                push = pending.extra["push"]
                                self._nudge(
                                    unit, push * dx / distance, push * dy / distance
                                )
                                unit.target = unit.wall_target = None
                if pending.src == "mortar":
                    # Wiki: Barbarian/Home Village states two tiles of knockback.
                    # Travel duration and exact direction convention are unstated.
                    for unit in self.attackers_near(x, y, pending.radius):
                        if (
                            unit.alive
                            and not unit.flying
                            and not unit.is_hero
                            and unit.kind not in ("pet", "siege", "siege_idle")
                            # game data v18.200.9: Mortar.PushbackHousingLimit=3 -> 3 housing spaces.
                            and 0 < unit.housing <= 3
                            and not unit.underground
                        ):
                            origin_x, origin_y = pending.extra.get("origin", (x, y))
                            dx, dy = unit.x - origin_x, unit.y - origin_y
                            distance = math.hypot(dx, dy)
                            if distance:
                                self._nudge(
                                    unit, 2.0 * dx / distance, 2.0 * dy / distance
                                )
                            unit.target = unit.wall_target = None
                if pending.extra.get("buildings"):
                    self.splash_buildings(
                        x, y, pending.radius, pending.extra["buildings"]
                    )
                if pending.extra.get("poison"):
                    spells.add_defensive_poison(
                        self, x, y, pending.extra["poison"], origin="town_hall"
                    )

    # ======================================================== spatial index
    def _buckets(self):
        grid: dict = {}
        for u in self.attackers:
            if u.alive:
                grid.setdefault((int(u.x / BUCKET), int(u.y / BUCKET)), []).append(u)
        self._bucket_grid = grid
        heroes.apply_auras(self)

    def _separate(self):
        for cell in self._bucket_grid.values():
            n = len(cell)
            if n < 2:
                continue
            for i in range(n):
                a = cell[i]
                if not a.alive or a.speed <= 0:
                    continue
                ra = 0.35 + 0.015 * min(30, a.housing)
                for j in range(i + 1, n):
                    b = cell[j]
                    if not b.alive or b.flying != a.flying or b.speed <= 0:
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
        if self.t < u.extra.get("tornado_wall_until", 0.0):
            return
        nx, ny = u.x + dx, u.y + dy
        if not u.flying:
            i, j = self.grid.cell(nx, ny)
            if self.navigation_grid(u).blocked[i, j] or (
                self.navigation_grid(u).wall[i, j] and self.wall_mode(u) == "normal"
            ):
                return
        u.x = min(WORLD - 0.1, max(0.1, nx))
        u.y = min(WORLD - 0.1, max(0.1, ny))

    # ================================================================ castle
    def _castle(self):
        castle = self.cc_building
        if (
            castle is None
            or self.cc_released
            or not self.cc_queue
            or not castle.alive
            or castle.mode == "sleep"
            or self.t < getattr(self, "_next_cc_exit", 0.0)
        ):
            return
        intruders = [
            unit
            for unit in self.attackers_near(castle.x, castle.y, CC_TRIGGER_RADIUS)
            if unit.name not in spells.NO_TRIGGER
            and unit.targetable(self.t)
            and unit.dash is None
        ]
        for index, entry in enumerate(self.cc_queue):
            numbers = unit_numbers(entry["name"], entry["level"])
            if not any(
                numbers["hits_air"] if unit.flying else numbers["hits_ground"]
                for unit in intruders
            ):
                continue
            self.cc_queue.pop(index)
            # Exit geometry and spacing are retained approximations, not wiki values.
            self.spawn(
                entry["name"],
                "def",
                castle.x + 1.5,
                castle.y,
                level=entry["level"],
                kind="cc",
            )
            self._next_cc_exit = self.t + 0.3
            self.cc_released = not self.cc_queue
            return

    # ========================================================== attacker AI
    def _preferred_pool(self, u):
        pref = u.spec.prefer
        if pref not in ("defense", "air_defense", "resource", "wall", "building"):
            return None
        if pref == "wall":
            return [w for w in self.walls.values() if w.alive]
        pool = [b for b in self.buildings if self.building_targetable(b)]
        if pref in ("defense", "air_defense"):
            return [b for b in pool if self.is_defense_target(b)]
        if pref == "resource":
            # Wiki: Sneaky Goblin includes the Town Hall and Clan Castle.
            return [
                b for b in pool if b.kind == "resource" or b.key in units.RESOURCE_KEYS
            ]
        return pool

    def _act_attacker(self, u: Unit):
        t = self.t
        if heroes.summon_tick(self, u):
            return
        if units.pre_tick(self, u):
            units.interrupt_attack(u)
            return
        if not u.can_act(t) or t < u.held_until and u.speed > 0 and u.target is None:
            units.interrupt_attack(u)
            return
        u.cooldown = max(u.cooldown - DT, -DT)
        sp = u.spec
        if sp.attack in ("heal", "heal_chain"):
            units.act_healer(self, u)
            return
        if sp.prefer == "none":
            return
        # Wiki: Angry Spell, affected units ignore defending troops and Heroes.
        angry = t < u.extra.get("angry_until", 0.0)
        target = u.target
        if angry and isinstance(target, Unit):
            target = None
        if target is not None:
            if not target.alive and u.target_kind != "destination":
                target = None
            elif (
                u.target_kind == "building"
                and not self.building_targetable(target)
                and (sp.prefer != "th" or not self._siege_blocks(target))
            ):
                target = None
            elif (
                sp.prefer == "th"
                and u.target_kind == "destination"
                and not u.flying
                and t >= u.extra.get("next_blocker_check", 0.0)
            ):
                # A building that turns visible again can stand in the way.
                u.extra["next_blocker_check"] = t + 0.5
                target = None
            elif u.target_kind == "unit" and not target.targetable(t):
                target = None
        if sp.prefer == "wall" and isinstance(target, Wall):
            if units.wall_breaker_target(self, u) is not target:
                target = None
                u.wall_target = None
        if sp.prefer == "heroes" and not angry:
            hero = self._nearest_defender(u, math.inf, heroes_only=True)
            if hero is not None:
                target, u.target_kind, u.wall_target = hero, "unit", None
        preferred = self._preferred_pool(u)
        engages = sp.engages_units
        if sp.prefer in ("defense", "air_defense"):
            engages = engages or self._defenses_gone()
        if preferred is not None:
            if u.extra.get("preferred_remaining", False) and not preferred:
                # Wiki preferred-target templates: finish the current building.
                if isinstance(target, Building):
                    u.extra["finish_preferred"] = target
            u.extra["preferred_remaining"] = bool(preferred)
            finishing = target is not None and target is u.extra.get("finish_preferred")
            retaliation = (
                u.name == "Royal Champion" or u.pet is not None and u.pet.attached(t)
            )  # Wiki: Royal Champion and Angry Jelly permit retaliation.
            engages = retaliation or not preferred and not finishing
            if preferred and isinstance(target, Unit) and not retaliation:
                target = None
        if target is None:
            u.target_kind = None
            units.interrupt_attack(u)
        # game data v18.200.9: AngryJellyGivenMaster.FightWithGroups=FALSE.
        # Wiki: Angry Spell, affected Wardens also target defenses directly.
        if (
            u.name in ("Grand Warden", "Apprentice Warden")
            and not angry
            and not (u.pet is not None and u.pet.attached(t))
        ):
            followed = units.follow_target(self, u)
            grouped = u.extra.get("warden_group", False)
            if followed is not None:
                target = followed
                u.target_kind = "wall" if isinstance(followed, Wall) else "building"
                u.wall_target = None
            elif followed is None and grouped:
                target = None
            u.extra["warden_group"] = followed is not None
        elif u.name in ("Grand Warden", "Apprentice Warden"):
            u.extra["warden_group"] = False
        if (
            engages
            and not angry
            and u.target_kind != "unit"
            and t >= u.extra.get("next_engage", 0.0)
        ):
            u.extra["next_engage"] = t + 0.5
            if t < u.aware_until or self._ally_under_attack(u):
                foe = self._nearest_defender(u, ENGAGE_RADIUS)
                if foe is not None:
                    target, u.target_kind, u.wall_target = foe, "unit", None
        if target is None:
            u.wall_target = None
            target, u.target_kind = self.choose_target(u)
        # Wiki: Angry Spell, even Dragons ignore nearer defending units.
        if (
            u.name == "Dragon"
            and not angry
            and target is not None
            and not isinstance(target, Unit)
        ):
            # Wiki: Dragon, Dragons attack the Barbarian King and Clan Castle
            # troops that cannot target air "if these troops are the closest
            # target", so this needs no awareness (such a foe can never make
            # them aware); foes that can hit air make them aware anyway.
            foe = self._nearest_defender(u, ENGAGE_RADIUS)
            if foe is not None and units.target_distance(
                u, foe
            ) < units.target_distance(u, target):
                target, u.target_kind = foe, "unit"
        if target is not None and target is not u.target:
            units.new_target_windup(u)
        u.target = target
        units.update_burrow(self, u, target)
        if target is None:
            units.interrupt_attack(u)
            return
        if t < u.extra.get("horse_until", 0.0):
            u.wall_target = None
        if (
            u.wall_target is not None
            and (
                spells.wall_jumped(self, u.wall_target) or self.wall_mode(u) == "ignore"
            )
            and u.kind != "siege"
        ):
            u.wall_target = None
        if u.wall_target is not None and u.wall_target.alive:
            self._engage(u, u.wall_target)
            return
        u.wall_target = None
        self._engage(u, target)

    def _ally_under_attack(self, u):
        for a in self.attackers_near(u.x, u.y, AWARE_RADIUS):
            if (
                a is not u
                and self.t - a.extra.get("troop_hit_at", -math.inf) < 1.0
                and a.name != "Totem"
            ):
                return True
        return False

    def _defenses_gone(self):
        return not any(b.alive and self.is_defense_target(b) for b in self.buildings)

    def choose_target(self, u: Unit):
        """Target selection by preferred target (wiki unit pages)."""
        pref = u.spec.prefer
        t = self.t
        if u.pet is not None and u.pet.attached(t):
            # Brainwash permits ordinary retaliation (wiki: Angry Jelly).
            pref = "defense"
        if t < u.extra.get("angry_until", 0.0):
            pref = "defense"  # Angry Spell: target any defense (wiki)
        if pref == "heroes":
            hero = self._nearest_defender(u, math.inf, heroes_only=True)
            if hero is not None:
                return hero, "unit"
            pref = "any"
        if pref == "wall":
            w = units.wall_breaker_target(self, u)
            if w is not None:
                return w, "wall"
            pref = "any"  # Wiki: Wall Breaker and Super Wall Breaker fall back to buildings.
        if pref == "th" and self.th is not None:
            # Wiki: Wall Wrecker/Blimp/Log Launcher keep the Town Hall destination.
            if not u.flying:
                blockers = []
                for blocker in list(self.buildings) + list(self.walls.values()):
                    if (
                        blocker is self.th
                        or not blocker.alive
                        or not self._siege_blocks(blocker)
                    ):
                        continue
                    entry = units.segment_entry(u.x, u.y, self.th.x, self.th.y, blocker)
                    if entry is not None:
                        blockers.append((entry, blocker))
                if blockers:
                    blocker = min(blockers, key=lambda item: item[0])[1]
                    return blocker, "wall" if isinstance(blocker, Wall) else "building"
            return self.th, "destination"
        if pref == "follow":
            b = units.follow_target(self, u)
            if b is not None:
                return b, "wall" if isinstance(b, Wall) else "building"
            pref = "any"
        if pref == "rubble":
            return units.rubble_target(self, u)
        pool = None
        if pref == "air_defense":
            pool = [b for b in self.buildings if b.key == "ad" and self.building_targetable(b)]
            if not pool:
                pref = "defense"
                pool = None
        if pref == "defense" and pool is None:
            pool = [b for b in self.buildings if self.is_defense_target(b) and self.building_targetable(b)]
        if pref == "resource" and pool is None:
            pool = [
                b
                for b in self.buildings
                if (b.kind == "resource" or b.key in units.RESOURCE_KEYS)
                and self.building_targetable(b)
            ]

        if not pool:
            pool = [b for b in self.buildings if self.building_targetable(b)]
        if not pool:
            # Wiki: Angry Spell, no retaliation even after all buildings are gone.
            if (
                t >= u.extra.get("angry_until", 0.0)
                and u.spec.engages_units
                and (t < u.aware_until or self._ally_under_attack(u))
            ):
                foe = self._nearest_defender(u, ENGAGE_RADIUS)
                if foe is not None:
                    return foe, "unit"
            return None, None
        if (
            not u.flying
            and self.wall_mode(u) == "normal"
            and not u.underground
            and len(pool) > 1
            and u.name != "Wall Breaker"
        ):
            return self._path_target(u, pool), "building"
        best = None
        bd = 1e9
        for b in pool:
            d = b.edge_distance(u.x, u.y)
            if d < bd:
                bd, best = d, b
        return (best, "building") if best is not None else (None, None)

    def _siege_blocks(self, b) -> bool:
        """Whether a Town Hall-bound ground siege stops to attack b.

        Overgrown buildings still stop it (wiki: Overgrowth Spell, the Wall
        Wrecker and Log Launcher attack them for no damage and get stuck).
        Invisible buildings do not (wiki: Invisibility Spell, untargetable
        by anything; Town Hall-targeting Siege Machines continue their
        advance), nor does a Hidden Tesla that has not popped up (it pops up
        once the siege comes near; defense.reveal_tesla then retargets).
        Yellow Card suspension is unstated for sieges and still blocks."""
        if isinstance(b, Wall):
            return True
        if b.key == "tesla" and not b.revealed:
            return False
        return self.t >= b.invisible_until

    def _path_target(self, u: Unit, pool):
        """Ground troops pick the building that is cheapest to reach, walls
        counting as a detour (wiki: walled compartments without access are
        often ignored by ground troops)."""
        xs = np.fromiter((b.x for b in pool), dtype=np.float64, count=len(pool))
        ys = np.fromiter((b.y for b in pool), dtype=np.float64, count=len(pool))
        hs = np.fromiter((b.half_hit for b in pool), dtype=np.float64, count=len(pool))
        reach = max(units.effective_range(u), GOAL_REACH_MIN)
        costs = self.navigation_grid(u).building_costs(
            u.x, u.y, WALL_COST["normal"] / RES, xs, ys, hs, reach
        )
        k = int(np.argmin(costs))
        if costs[k] >= 1e8:  # unreachable even through walls: fall back to nearest
            return min(pool, key=lambda b: b.edge_distance(u.x, u.y))
        return pool[k]

    def _nearest_defender(self, u: Unit, radius: float, heroes_only=False):
        best = None
        bd = radius
        t = self.t
        for v in self.defenders:
            if not v.alive or t < v.active_at or t < v.invisible_until:
                continue
            if heroes_only and not v.is_hero:
                continue
            if not self.can_hit(u, v):
                continue
            d = dist(u.x, u.y, v.x, v.y)
            if d <= bd:
                bd, best = d, v
        return best

    def wall_mode(self, u: Unit):
        if u.team == "def":
            return "ignore"  # Wiki: Clan Castle defenders jump over walls.
        if u.kind not in ("siege", "siege_idle") and self.t < u.extra.get(
            "jump_until", 0.0
        ):
            return "ignore"
        if (
            self.t < u.extra.get("horse_until", 0.0)
            or effects.torch_stats(u, self.t)[1]
        ):
            return "ignore"
        if u.extra.get("torches") and not u.flying:
            cell = self.grid.cell(u.x, u.y)
            if self.grid.wall[cell]:
                return "ignore"  # Finish leaving a wall after Torch expires.
        return u.spec.walls

    def navigation_grid(self, u):
        if u.kind in ("siege", "siege_idle"):
            return self.grid
        fields = tuple(
            field
            for field in self.fields
            if field.kind == "jump" and field.started <= self.t < field.until
        )
        if not fields:
            return self.grid
        # id() alone can repeat once an expired field is freed, which would
        # reuse the old spell's jumped walls; the field's place and time cannot.
        key = (
            self.grid.version,
            tuple((id(f), f.x, f.y, f.radius, f.started) for f in fields),
        )
        if getattr(self, "_jump_grid_key", None) != key:
            grid = Grid(WORLD)
            grid.blocked[:] = self.grid.blocked
            grid.wall[:] = self.grid.wall
            for wall in self.walls.values():
                if wall.alive and spells.wall_jumped(self, wall):
                    grid.set_wall(wall.tx, wall.ty, False)
            self._jump_grid_key = key
            self._jump_grid = grid
        return self._jump_grid

    def speed_of(self, u: Unit) -> float:
        t = self.t
        s = u.speed
        # rage and haste speed boosts do not stack; the larger applies (wiki)
        _, rage_speed = units.rage_boost(u, t)
        horse_speed = (
            u.extra["horse_speed"] if t < u.extra.get("horse_until", 0.0) else 0.0
        )
        s += max(
            rage_speed,
            units.haste_speed(u, t),
            horse_speed,
            effects.torch_stats(u, t)[0],
        )
        s *= effects.slow_mult(u, t, movement=True)
        return s

    def _engage(self, u: Unit, target):
        if (target.x, target.y) != (u.x, u.y):
            u.extra["facing"] = (target.x - u.x, target.y - u.y)
        if u.target_kind == "destination":
            # Wiki: Wall Wrecker/Log Launcher break apart on reaching the Town
            # Hall (or its remains). A ground machine cannot enter the hitbox,
            # so it arrives within its attack range of the edge (game data
            # v18.200.9: Wall Wrecker AttackRange=150, Log Launcher 100); it
            # used to walk through the hitbox to the exact centre first.
            # The Battle Blimp too: video of real attacks shows it stopping
            # 1-2 tiles outside the Town Hall's edge and blowing up there
            # (docs/VIDEO_MEASUREMENTS.md, XtLqXV-ab6U @174.5), i.e. within
            # its game data AttackRange=150 of the edge, like the ground
            # machines (it used to fly to the exact centre).
            arrived = target.edge_distance(u.x, u.y) <= u.range
            if arrived:
                self.kill(u)
            else:
                self.move_straight(u, target.x, target.y, self.speed_of(u) * DT)
            return
        position = units.valkyrie_position(self, u, target)
        # Wiki: Valkyrie, move between buildings to attack multiple targets.
        # A 0.3-tile arrival tolerance exceeds a pair's 0.235-tile separation
        # nudge; the actual attack range below still gates every strike.
        if position is not None and dist(u.x, u.y, *position) > 0.3:
            units.interrupt_attack(u)
            if self.t >= u.held_until:
                self.move_towards(u, target, position=position)
            return
        d = units.target_distance(u, target)
        reach = units.effective_range(u)
        if u.name == "Super Hog Rider":
            dx, dy = target.x - u.x, target.y - u.y
            length = math.hypot(dx, dy)
            if length:
                u.extra["heading"] = (dx / length, dy / length)
        if u.name == "Super Miner" and u.team == "atk":
            u.underground = d > reach
        if d <= reach:
            if u.name == "Sky Wagon":
                if not isinstance(target, Building) or not self.is_defense_target(
                    target
                ):
                    return
                if self.t >= u.extra["next"]:
                    units.launch_barrel(self, u, target)
                return
            if not units.attack_ready(self, u, target):
                return
            units.track_beam(self, u, target)
            if u.team == "atk" and "burrow" in u.spec.special:
                u.underground = False
            if self.t < u.extra.get("attack_lock_until", 0.0):
                return  # casting an ability that disables attacks (Seeking Shield)
            if u.cooldown <= 0 and self.t >= u.held_until or u.cooldown <= 0 and u.range >= 1.0:
                units.strike(self, u, target)
                slow = effects.slow_mult(u, self.t)
                interval = units.attack_interval(u, self)
                if self.t < u.extra.get("horse_until", 0.0):
                    # Speed bonuses add as in the paired examples (wiki: Stick Horse).
                    base_interval = u.extra["horse_interval"]
                    passive_speed = base_interval / u.interval
                    interval = base_interval / (passive_speed + u.extra["horse_attack"])
                if self.t < u.extra.get("haste_attack_until", 0.0):
                    interval /= u.extra["haste_attack"]
                if u.name == "Dragon Duke" and units.duke_alone(self, u):
                    interval /= 1.5  # wiki: Dragon Duke, Royal Rampage
                u.cooldown += interval / max(0.05, slow)
                if u.name == "Valkyrie" and not target.alive:
                    # Wiki: Valkyrie, a kill resets her attack pattern; the next
                    # target uses NewTargetAttackDelay=600 ms (game data v18.200.9).
                    u.cooldown = 0.0
            return
        units.interrupt_attack(u)
        if self.t < u.held_until:
            return
        self.move_towards(u, target)

    def move_towards(self, u: Unit, target, *, position=None):
        step = self.speed_of(u) * DT
        if step <= 0:
            return
        tx, ty = position if position is not None else (target.x, target.y)
        mode = self.wall_mode(u)
        if u.name == "Ruin Witch" and u.team == "atk":
            mode = "normal"
        if mode == "smash":
            mode = "ignore"
        if u.flying or mode == "fly" or u.underground or u.spec.prefer == "th":
            self.move_straight(u, tx, ty, step)
            return
        # Coordinate goals cover one grid cell; attack reach stays exact.
        reach = units.effective_range(u) if position is None else 1.0 / RES
        reach = max(reach, GOAL_REACH_MIN)
        grid = self.navigation_grid(u)
        half = getattr(target, "half_hit", 0.0) if position is None else 0.0
        identity = ("unit", target.id) if isinstance(target, Unit) else target.id
        key = (identity, tx, ty, reach, mode)
        field_ = grid.field(key, tx, ty, half, reach, WALL_COST[mode] / RES)
        nx, ny, is_wall, at_goal = grid.next_step(field_, u.x, u.y)
        if at_goal:
            cell = grid.cell(u.x, u.y)
            # On a goal cell, close the last bit straight. A unit standing
            # inside a hitbox (cargo or a drop over a building or Hidden
            # Tesla) has no path value at all and used to freeze there
            # until that building fell; it walks straight out instead.
            if field_[cell] == 0.0 or grid.blocked[cell]:
                self.move_straight(u, tx, ty, step)
            return
        if is_wall and mode in ("ignore",):
            is_wall = False
        if is_wall:
            w = self.walls.get((int(nx), int(ny)))
            if w is not None and w.alive:
                if u.name == "Ruin Witch" and u.team == "atk":
                    u.target = None
                    return
                u.wall_target = w
                return
        if nx == u.x and ny == u.y:
            u.stuck += DT
            if u.stuck > 2.0:
                u.target = None
                u.stuck = 0.0
            return
        u.stuck = 0.0
        left = step - math.hypot(nx - u.x, ny - u.y)
        self.move_straight(u, nx, ny, step)
        # A tick's movement used to end at the next half-tile waypoint, which
        # capped path-following ground units at 5 tiles/s and cost 5-30% of
        # speed from 3.5 tiles/s up (raged or hasted troops); the rest of the
        # step now continues along the path. Walls stop it for the next tick.
        for _ in range(4):
            if left <= 1e-9 or u.x != nx or u.y != ny:
                break
            nx, ny, is_wall, at_goal = grid.next_step(field_, u.x, u.y)
            if at_goal or is_wall and mode != "ignore" or (nx == u.x and ny == u.y):
                break
            d = math.hypot(nx - u.x, ny - u.y)
            self.move_straight(u, nx, ny, left)
            left -= d

    def move_straight(self, u, tx, ty, step):
        if self.t < u.extra.get("tornado_wall_until", 0.0):
            return
        dx = tx - u.x
        dy = ty - u.y
        if dx or dy:
            u.extra["facing"] = dx, dy
        d = math.hypot(dx, dy)
        if d and u.name == "Super Hog Rider":
            u.extra["heading"] = (dx / d, dy / d)
        if d <= step or d == 0:
            u.x, u.y = tx, ty
        else:
            u.x += dx / d * step
            u.y += dy / d * step

    # ========================================================== defender AI
    def _act_defender(self, u: Unit):
        t = self.t
        if u.name == "Barbarian King" and u.home is not None:
            distance = dist(u.x, u.y, *u.home)
            if distance > u.leash:
                u.x = u.home[0] + (u.x - u.home[0]) * u.leash / distance
                u.y = u.home[1] + (u.y - u.home[1]) * u.leash / distance
        if t < u.active_at:
            return
        if units.pre_tick(self, u):
            units.interrupt_attack(u)
            return
        if not u.can_act(t) or t < u.held_until:
            units.interrupt_attack(u)
            return
        if u.spec.attack in ("heal", "heal_chain"):
            units.act_healer(self, u)
            return
        if u.spec.attack == "none" and u.name != "Ruin Witch":
            return
        u.cooldown = max(u.cooldown - DT, -DT)
        target = u.target if (u.target is not None and u.target.alive and u.target.targetable(t)) else None
        if u.spec.prefer == "heroes" and target is not None and not target.is_hero:
            target = None
        if u.name == "Barbarian King" and target is not None:
            if dist(target.x, target.y, *u.home) > u.leash:
                target = None
        if (
            target is None
            or u.name != "Barbarian King"
            and t >= u.extra.get("next_retarget", 0.0)
        ):
            u.extra["next_retarget"] = t + 0.5
            center = u.home if u.home is not None else (u.x, u.y)
            radius = u.leash if u.home is not None else math.inf
            best, bd = None, math.inf
            for a in self.attackers:
                if dist(center[0], center[1], a.x, a.y) > radius:
                    continue
                if not a.targetable(t) or not self.can_hit(u, a):
                    continue
                if (
                    u.spec.prefer == "heroes"
                    and any(
                        hero.is_hero and hero.targetable(t) and self.can_hit(u, hero)
                        for hero in self.attackers
                    )
                    and not a.is_hero
                ):
                    continue
                d = dist(a.x, a.y, u.x, u.y)
                if d < bd:
                    bd, best = d, a
            target = best
        if target is not None and target is not u.target:
            units.new_target_windup(u)
        u.target = target
        if target is None:
            units.interrupt_attack(u)
            if spells.escape_poison(self, u):
                return
            if u.home is not None:
                u.extra["patrol_state"] = (
                    "returning" if (u.x, u.y) != u.home else "patrolling"
                )
                self.move_towards(u, u, position=u.home)
            return
        heroes.defending_hero_ability(self, u)
        d = dist(u.x, u.y, target.x, target.y)
        reach = units.effective_range(u)
        if d <= reach:
            if not units.attack_ready(self, u, target):
                return
            units.track_beam(self, u, target)
            if u.cooldown <= 0:
                units.strike(self, u, target)
                slow = effects.slow_mult(u, t)
                u.cooldown += units.attack_interval(u, self) / max(0.05, slow)
                if u.name == "Valkyrie" and not target.alive:
                    # Wiki: Valkyrie, kills reset the defending attack cycle too.
                    u.cooldown = 0.0
            return
        units.interrupt_attack(u)
        # Defenders jump walls while navigating around buildings (wiki: Clan Castle).
        self.move_towards(u, target)


def run_battle(layout: Layout, plan, **kw):
    return Battle(layout, plan, **kw).run()
