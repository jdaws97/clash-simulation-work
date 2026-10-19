"""Attacking hero equipment and pet effects, applied through sim hooks.

Numbers come from loadouts.py (wiki-verified). Simplifications are noted
inline; anything not listed is ignored rather than guessed.
"""

from __future__ import annotations

import math

from .loadouts import COMMON_LOADOUTS, EQUIPMENT, PETS, HeroLoadout


def _dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


class Kit:
    """Per-hero runtime state."""

    __slots__ = (
        "loadout",
        "equipment",
        "pet",
        "regen",
        "phoenix_ready",
        "doomed_at",
        "spear_shots",
        "boots_until",
        "gauntlet_until",
        "gauntlet_red",
        "heal_aura_until",
        "next_fox",
        "next_diggy",
        "next_meteor",
        "pet_dps",
    )

    def __init__(self, loadout: HeroLoadout):
        self.loadout = loadout
        self.equipment = [EQUIPMENT[e] for e in loadout.equipment if e in EQUIPMENT]
        self.pet = PETS.get(loadout.pet) if loadout.pet else None
        self.regen = sum(e.regen for e in self.equipment)
        self.phoenix_ready = self.pet is not None and self.pet.name == "Phoenix"
        self.doomed_at = None
        self.spear_shots = 0
        self.boots_until = 0.0
        self.gauntlet_until = 0.0
        self.gauntlet_red = 0.0
        self.heal_aura_until = 0.0
        self.next_fox = 6.0
        self.next_diggy = 4.0
        self.next_meteor = 5.0
        # pets that just fight alongside: fold their DPS into the hero
        self.pet_dps = 0.0
        if self.pet is not None and self.pet.name in ("Electro Owl", "L.A.S.S.I", "Angry Jelly", "Frosty", "Phoenix", "Spirit Fox", "Diggy"):
            mult = 1.6 if self.pet.name == "Electro Owl" else 1.0  # owl chains to a 2nd target
            self.pet_dps = self.pet.dps * mult

    def has(self, name):
        return any(e.name == name for e in self.equipment)

    def passive(self, key, default=0.0):
        for e in self.equipment:
            if key in e.passive:
                return e.passive[key]
        return default


def equip(battle, u, plan) -> None:
    """Apply passive boosts when a hero is deployed."""
    loadouts = getattr(plan, "loadouts", None) or {}
    lo = loadouts.get(u.name) or COMMON_LOADOUTS.get(u.name)
    if lo is None:
        return
    kit = Kit(lo)
    u.kit = kit
    hp = sum(e.hp for e in kit.equipment)
    u.max_hp += hp
    u.hp += hp
    u.dps += sum(e.dps for e in kit.equipment) + kit.pet_dps
    t = battle.t
    kit.next_fox += t
    kit.next_diggy += t
    kit.next_meteor += t


def tick(battle, u) -> None:
    """Per-tick passive effects for a living attacking hero."""
    kit = u.kit
    t = battle.t
    dt = battle.DT
    if kit.doomed_at is not None and t >= kit.doomed_at:
        kit.doomed_at = None
        u.invulnerable_until = 0.0
        battle._kill_unit(u)
        return
    heal = kit.regen
    if kit.pet is not None and kit.pet.name == "Unicorn":
        heal += kit.pet.effect["heal_hero"]
    if heal and kit.doomed_at is None:
        u.hp = min(u.max_hp, u.hp + heal * dt)
    engaged = u.target is not None and u.cooldown > 0
    if kit.pet is not None and kit.pet.name == "Spirit Fox" and engaged and t >= kit.next_fox:
        u.invisible_until = max(u.invisible_until, t + kit.pet.effect["invis"])
        kit.next_fox = t + kit.pet.effect["invis"] + kit.pet.effect["cooldown"]
    if kit.pet is not None and kit.pet.name == "Diggy" and engaged and t >= kit.next_diggy:
        tgt = u.target
        if getattr(tgt, "weapon", None) is not None:
            tgt.frozen_until = max(tgt.frozen_until, t + kit.pet.effect["stun"])
        kit.next_diggy = t + kit.pet.effect["cooldown"]
    meteor = kit.passive("meteor")
    if meteor and engaged and t >= kit.next_meteor and hasattr(u.target, "edge_distance"):
        battle.damage_building(u.target, meteor)
        kit.next_meteor = t + kit.passive("cooldown", 5.0)
    if t < kit.boots_until:
        for f in battle.defenders:
            if f.alive and _dist(f.x, f.y, u.x, u.y) <= 3.0:
                battle.damage_unit(f, 200 * dt)
        for b in battle.buildings:
            if b.alive and b.counted and b.edge_distance(u.x, u.y) <= 2.0:
                battle.damage_building(b, 200 * dt)
    if t < kit.heal_aura_until:
        for a in battle.attackers_near(u.x, u.y, 7.0):
            a.hp = min(a.max_hp, a.hp + 150 * dt)


def strike_bonus(u, target) -> float:
    """Extra damage added to a hero's normal hit."""
    kit = u.kit
    bonus = 0.0
    if kit.spear_shots > 0:
        kit.spear_shots -= 1
        bonus += 980.0
    return bonus


def on_hit_extra(battle, u, target) -> None:
    """Electro Fangs: each hit chains 400 to up to 4 nearby targets."""
    kit = u.kit
    dmg = kit.passive("fang_damage")
    if not dmg or not hasattr(target, "edge_distance"):
        return
    hits = 0
    for b in battle.buildings:
        if b is target or not b.alive or not b.counted:
            continue
        if b.edge_distance(target.x, target.y) <= 3.0:
            battle.damage_building(b, dmg)
            hits += 1
            if hits >= kit.passive("fang_targets", 4) - 1:
                break


def damage_taken_mult(battle, u) -> float:
    kit = u.kit
    if battle.t < kit.gauntlet_until:
        return 1.0 - kit.gauntlet_red
    return 1.0


def on_death(battle, u) -> bool:
    """Return True if the hero is saved (Phoenix)."""
    kit = u.kit
    if kit.phoenix_ready:
        kit.phoenix_ready = False
        dur = kit.pet.effect["revive"]
        u.alive = True
        u.hp = 1.0
        u.invulnerable_until = battle.t + dur
        kit.doomed_at = battle.t + dur
        return True
    death = kit.passive("death_damage")
    if death:
        battle.splash_buildings(u.x, u.y, 3.0, death, include_walls=False)
    return False


def activate(battle, u) -> None:
    """The hero ability button: fires both equipped actives together."""
    kit = u.kit
    t = battle.t
    tgt = u.target if hasattr(u.target, "edge_distance") and not hasattr(u.target, "tx") else None
    for e in kit.equipment:
        a = e.active
        if not a:
            continue
        if "arrow" in a and tgt is not None:
            dx, dy = tgt.x - u.x, tgt.y - u.y
            d = math.hypot(dx, dy) or 1.0
            for b in battle.buildings:
                if not b.alive or not b.counted:
                    continue
                px, py = b.x - u.x, b.y - u.y
                along = (px * dx + py * dy) / d
                if 0 < along < 40 and abs(px * dy - py * dx) / d < 1.5:
                    battle.damage_building(b, a["arrow"] * (a["arrow_ad_mult"] if b.key == "ad" else 1.0))
        if "healers" in a:
            for k in range(a["healers"]):
                h = battle._spawn("Healer", "atk", u.x - 0.5 + 0.4 * k, u.y - 0.5, level=a["healer_level"], group=u.group)
                h.follow = u
        if "clones" in a:
            for k in range(a["clones"]):
                c = battle._spawn("Archer Queen", "atk", u.x + 0.6 * (k - 0.5), u.y + 0.4, level=10, group=u.group)
                c.hp = c.max_hp = a["clone_hp"]
                c.dps = a["clone_dps"]
                c.is_hero = False
                c.decay = a["clone_hp"] / a["clone_time"]
        if "giant_giant" in a:
            gg = battle._spawn("Giant", "atk", u.x, u.y, group=u.group)
            gg.hp = gg.max_hp = 6000.0  # Giant Giant L10 (assumed HP)
            gg.dps = 300.0
        if "invis" in a:
            u.invisible_until = max(u.invisible_until, t + a["invis"])
        if "spiky" in a and tgt is not None:
            cur = tgt
            hit = set()
            for _ in range(a["targets"]):
                if cur is None:
                    break
                hit.add(cur.id)
                battle.damage_building(cur, a["spiky"])
                nxt = None
                nd = 6.0
                for b in battle.buildings:
                    if b.alive and b.counted and b.id not in hit:
                        d = _dist(b.x, b.y, cur.x, cur.y)
                        if d < nd:
                            nd, nxt = d, b
                cur = nxt
        if "quake_pct" in a:
            for b in battle.buildings:
                if b.alive and b.counted and b.edge_distance(u.x, u.y) <= a["radius"]:
                    battle.damage_building(b, b.max_hp * a["quake_pct"])
        if "reduction" in a:
            kit.gauntlet_until = t + a["duration"]
            kit.gauntlet_red = a["reduction"]
        if "tome" in a:
            for f in battle.attackers_near(u.x, u.y, 7.0):
                f.invulnerable_until = max(f.invulnerable_until, t + a["tome"])
        if "heal_aura" in a:
            kit.heal_aura_until = t + a["duration"]
        if "fireball" in a and tgt is not None:
            for b in battle.buildings:
                if b.alive and b.edge_distance(tgt.x, tgt.y) <= a["radius"]:
                    battle.damage_building(b, a["fireball"] if b is tgt else a["fireball"] * 0.5)
        if "spear_bonus" in a:
            kit.spear_shots = a["attacks"]
        if "aura_dps" in a:
            kit.boots_until = t + a["duration"]
        if "shield" in a:
            near = sorted(
                (b for b in battle.buildings if b.alive and b.is_defense),
                key=lambda b: _dist(b.x, b.y, u.x, u.y),
            )[: a["targets"]]
            for b in near:
                battle.damage_building(b, a["shield"])
        if "orb_slow" in a and tgt is not None:
            tgt.frozen_until = max(tgt.frozen_until, t + 2.0)  # Dark Orb slow ~ partial disable
        if "dash" in a:
            battle._start_dash(u, damage=a["dash"])
        if "cone" in a and tgt is not None:
            for b in battle.buildings:
                if b.alive and b.counted and b.edge_distance(u.x, u.y) <= 4.0:
                    battle.damage_building(b, a["cone"])
