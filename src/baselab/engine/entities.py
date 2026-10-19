"""Battle entities for engine v2.

Units cover every moving or stationary combatant: attacking troops, heroes,
pets, siege machines, summons, Totems, Clan Castle troops, Skeleton Trap
skeletons, defending heroes and Guardians. Status effects are explicit
fields with expiry times so their interactions stay readable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


class Building:
    __slots__ = (
        "id", "key", "name", "kind", "x", "y", "size", "half_hit", "hp", "max_hp", "alive",
        "counted", "is_defense", "weapon", "mode", "level",
        "frozen_until", "stun_until", "overgrown_until", "invisible_until",
        "atk_slow_until", "atk_slow", "rage_until", "rage_mult", "eq_hits",
        "revealed", "active", "last_hit", "extra",
    )

    def __init__(self, bid, key, name, kind, x, y, size, hitbox, hp, *, counted=True, is_defense=False, mode=None, level=None):
        self.id = bid
        self.key = key
        self.name = name
        self.kind = kind
        self.size = size
        self.x = x + size / 2.0
        self.y = y + size / 2.0
        self.half_hit = hitbox / 2.0
        self.hp = hp
        self.max_hp = hp
        self.alive = True
        self.counted = counted
        self.is_defense = is_defense
        self.weapon = None
        self.mode = mode
        self.level = level
        self.frozen_until = 0.0
        self.stun_until = 0.0
        self.overgrown_until = 0.0
        self.invisible_until = 0.0
        self.atk_slow_until = 0.0
        self.atk_slow = 1.0
        self.rage_until = 0.0
        self.rage_mult = 1.0
        self.eq_hits = 0
        self.revealed = True
        self.active = True
        self.last_hit = -100.0
        self.extra = {}

    def edge_distance(self, x, y):
        dx = abs(x - self.x) - self.half_hit
        dy = abs(y - self.y) - self.half_hit
        dx = dx if dx > 0 else 0.0
        dy = dy if dy > 0 else 0.0
        return math.hypot(dx, dy)

    def disabled(self, t):
        return (
            t < self.frozen_until
            or t < self.stun_until
            or t < self.overgrown_until
            or t < self.extra.get("yellow_until", 0.0)
        )


class Wall:
    __slots__ = ("tx", "ty", "x", "y", "hp", "max_hp", "alive", "half_hit", "eq_hits", "id", "key")

    def __init__(self, tx, ty, hp):
        self.tx = tx
        self.ty = ty
        self.x = tx + 0.5
        self.y = ty + 0.5
        self.hp = hp
        self.max_hp = hp
        self.alive = True
        self.half_hit = 0.5
        self.eq_hits = 0
        self.id = ("wall", tx, ty)
        self.key = "wall"

    def edge_distance(self, x, y):
        dx = max(0.0, abs(x - self.x) - 0.5)
        dy = max(0.0, abs(y - self.y) - 0.5)
        return math.hypot(dx, dy)


class Unit:
    __slots__ = (
        "id", "name", "kind", "team", "level", "x", "y", "hp", "max_hp", "base_max_hp",
        "dmg", "interval", "range", "speed", "housing", "flying", "hits_air", "hits_ground",
        "spec", "alive", "cooldown", "target", "target_kind", "wall_target", "group",
        "spawned_at", "active_at", "stuck",
        # statuses
        "frozen_until", "stun_until", "held_until", "invisible_until", "invuln_until",
        "move_slow", "move_slow_until", "atk_slow", "atk_slow_until",
        "rage_dmg", "rage_spd", "rage_until", "haste_spd", "haste_until",
        "iceblock_red", "iceblock_until", "dmg_taken_mult", "dmg_taken_until",
        "aura_bonus", "aura_dmg", "underground", "aware_until", "last_hit",
        "poison_stack",
        # hero / pet / misc
        "is_hero", "kit", "pet", "owner", "follow", "home", "leash", "ability_used",
        "decay", "dash", "extra", "damage_dealt",
    )

    def __init__(self, uid, name, kind, team, x, y, *, hp, dmg, interval, range_, speed, housing,
                 flying, hits_air, hits_ground, spec, level=None):
        self.id = uid
        self.name = name
        self.kind = kind
        self.team = team
        self.level = level
        self.x = x
        self.y = y
        self.hp = hp
        self.max_hp = hp
        self.base_max_hp = hp
        self.dmg = dmg  # damage per hit
        self.interval = interval
        self.range = range_
        self.speed = speed
        self.housing = housing
        self.flying = flying
        self.hits_air = hits_air
        self.hits_ground = hits_ground
        self.spec = spec
        self.alive = True
        self.cooldown = 0.0
        self.target = None
        self.target_kind = None
        self.wall_target = None
        self.group = "main"
        self.spawned_at = 0.0
        self.active_at = 0.0
        self.stuck = 0.0
        self.frozen_until = 0.0
        self.stun_until = 0.0
        self.held_until = 0.0
        self.invisible_until = 0.0
        self.invuln_until = 0.0
        self.move_slow = 1.0
        self.move_slow_until = 0.0
        self.atk_slow = 1.0
        self.atk_slow_until = 0.0
        self.rage_dmg = 1.0
        self.rage_spd = 0.0
        self.rage_until = 0.0
        self.haste_spd = 0.0
        self.haste_until = 0.0
        self.iceblock_red = 0.0
        self.iceblock_until = 0.0
        self.dmg_taken_mult = 1.0
        self.dmg_taken_until = 0.0
        self.aura_bonus = 0.0
        self.aura_dmg = 1.0
        self.underground = False
        self.aware_until = 0.0
        self.last_hit = -100.0
        self.poison_stack = 0
        self.is_hero = False
        self.kit = None
        self.pet = None
        self.owner = None
        self.follow = None
        self.home = None
        self.leash = 0.0
        self.ability_used = False
        self.decay = 0.0
        self.dash = None
        self.extra = {}
        self.damage_dealt = 0.0

    def heal(self, amount):
        # Phoenix forbids every source of healing during temporary revival.
        if (
            not self.alive
            or "recalled" in self.extra
            or self.kit is not None
            and self.kit.doomed_at is not None
        ):
            return 0.0
        gained = max(0.0, min(amount, self.max_hp - self.hp))
        self.hp += gained
        if self.aura_bonus:
            self.extra["aura_hp"] = max(
                self.extra.get("aura_hp", 0.0), self.hp - self.base_max_hp
            )
        return gained

    def attached(self, t):
        return (
            self.name == "Angry Jelly"
            and self.owner is not None
            and self.owner.alive
            and t < self.extra.get("brainwash_until", 0.0)
        )

    def can_act(self, t):
        return (
            not self.extra.get("suspended")
            and t >= self.extra.get("yellow_until", 0.0)
            and t >= self.frozen_until
            and t >= self.stun_until
            and t >= self.active_at
        )

    def indirect_targetable(self, t):
        # Invisibility and Yellow Card prevent direct selection, not secondary hits.
        return (
            self.alive
            and not self.extra.get("suspended")
            and not self.underground
            and not self.extra.get("leaping")
            and not self.attached(t)
            and t >= self.active_at
        )

    def targetable(self, t):
        return (
            self.alive
            and not self.extra.get("suspended")
            and self.dash is None
            and not self.extra.get("leaping")
            and not self.attached(t)
            and t >= self.extra.get("yellow_until", 0.0)
            and t >= self.invisible_until
            and not self.underground
            and t >= self.active_at
        )


@dataclass
class Trap:
    key: str
    name: str
    x: float
    y: float
    level: int
    trigger: float
    radius: float
    damage: float
    air: bool
    ground: bool
    armed: bool = True
    fuse_at: float = -1.0
    mode: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class Field:
    """A spell or effect area that applies every tick until `until`."""

    kind: str
    x: float
    y: float
    radius: float
    until: float
    team: str = "atk"
    value: float = 0.0
    extra: dict = field(default_factory=dict)
    started: float = 0.0


@dataclass
class Pending:
    """A delayed impact (mortar shell, eagle shell, death bomb, air bomb)."""

    at: float
    x: float
    y: float
    radius: float
    damage: float
    hits_air: bool
    hits_ground: bool
    src: str
    falloff: bool = False
    team: str = "atk"  # who gets hurt
    extra: dict = field(default_factory=dict)
    actor: object | None = None
    effect: str | None = None
    target: object | None = None
    released_at: float | None = None
