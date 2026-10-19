"""Shared hero status accounting and damage provenance."""

from contextlib import contextmanager
from functools import wraps

from . import stats


@contextmanager
def damage_source(battle, actor, effect):
    previous = battle._src_obj, getattr(battle, "_effect", "attack")
    battle._src_obj, battle._effect = actor, effect
    try:
        yield
    finally:
        battle._src_obj, battle._effect = previous


def sourced(effect):
    def decorate(function):
        @wraps(function)
        def call(battle, actor, *args, **kwargs):
            with damage_source(battle, actor, effect):
                return function(battle, actor, *args, **kwargs)

        return call

    return decorate


def add_slow(target, source, movement, attack, until):
    target.extra.setdefault("slows", {})[source] = (movement, attack, until)


def slow_mult(target, t, *, movement=False):
    if movement:
        result = target.move_slow if t < target.move_slow_until else 1.0
    else:
        result = target.atk_slow if t < target.atk_slow_until else 1.0
    # Frozen Arrow stacks with Poison and frost (wiki: Frozen Arrow).
    for move, attack, until in target.extra.get("slows", {}).values():
        if t < until:
            result *= move if movement else attack
    return result


def invulnerable(unit, t):
    return t < unit.invuln_until or any(
        t < until for until in unit.extra.get("tomes", {}).values()
    )


def torch_stats(unit, t):
    speed, reduction = 0.0, 0.0
    for until, added_speed, reduced in unit.extra.get("torches", {}).values():
        if t < until:
            speed = max(speed, added_speed)
            reduction = max(reduction, reduced)
    return speed, reduction


def health_aura(unit, percentage, cap):
    capacity = min(unit.base_max_hp * percentage, cap)
    if capacity == unit.aura_bonus:
        return
    # Damage consumes bonus health first (wiki: Life Gem).
    remaining = unit.extra.pop("aura_hp", 0.0)
    unit.hp = max(0.0, unit.hp - remaining)
    unit.max_hp -= unit.aura_bonus
    grant = min(unit.hp * percentage, cap)
    unit.aura_bonus = capacity
    unit.max_hp += capacity
    unit.hp += grant
    unit.extra["aura_hp"] = grant


def record_death(battle, victim):
    if (
        victim.team != "atk"
        or victim.kind in ("siege", "siege_idle")
        or victim.extra.get("clone")
        or victim.extra.get("mirror_clone")
        or "recalled" in victim.extra
    ):
        return
    # Heroes and pets contribute 25 and 20 (wiki: Dark Crown).
    housing = 25 if victim.is_hero else 20 if victim.kind == "pet" else victim.housing
    if victim.name == "Totem":
        housing = 20  # wiki: Totem Spell
    for prince in battle.attackers:
        kit = prince.kit
        if (
            kit is not None
            and kit.has("Dark Crown")
            and prince is not victim
            and "recalled" not in prince.extra
        ):
            prince.extra["crown_housing"] = (
                prince.extra.get("crown_housing", 0) + housing
            )


def crown_buff(unit):
    kit = unit.kit
    if kit is None or not kit.has("Dark Crown"):
        return 0.0
    # Three stages at 60/120/180 housing (wiki: Dark Crown).
    stage = min(3, int(unit.extra.get("crown_housing", 0) // 60))
    kit.crown_stage = stage
    if not stage:
        return 0.0
    columns = (
        "first health & damage increase",
        "second health & damage increase",
        "max health increase",
    )
    return (
        stats.get("Dark Crown", kit.lv("Dark Crown"), "~" + columns[stage - 1]) / 100.0
    )
