"""Pet targeting and support effects from the individual wiki pages."""

from . import effects, spells, stats, units
from .entities import Building, Unit, Wall, dist


def _valid(battle, pet, target):
    if isinstance(target, Unit):
        return target.targetable(battle.t) and battle.can_hit(pet, target)
    if isinstance(target, Wall):
        return target.alive and pet.hits_ground
    return target is not None and battle.building_targetable(target)


def _nearest(pet, candidates):
    return min(
        candidates,
        key=lambda target: dist(pet.x, pet.y, target.x, target.y),
        default=None,
    )


def _target(battle, pet):
    hero = pet.owner
    owner_present = hero is not None and hero.alive
    buildings = [b for b in battle.buildings if _valid(battle, pet, b)]
    defenders = [u for u in battle.defenders if _valid(battle, pet, u)]
    if pet.name == "Greedy Raven":
        resources = [b for b in buildings if b.key in units.RESOURCE_KEYS]
        if resources:
            if owner_present:
                resources = [
                    b for b in resources if b.edge_distance(hero.x, hero.y) <= pet.range
                ]
            return _nearest(pet, resources)
    if pet.attached(battle.t):
        return _nearest(
            pet,
            [
                b
                for b in buildings
                if battle.is_defense_target(b)
                and b.edge_distance(pet.x, pet.y) <= pet.range
            ],
        )
    if pet.name == "Angry Jelly" and owner_present:
        source = hero.extra.get("last_damage_source")
        if isinstance(source, Building) and _valid(battle, pet, source):
            if source.edge_distance(pet.x, pet.y) <= pet.range:
                return source
    if pet.name == "Poison Lizard":
        # Defenders in the Hero's range take priority (wiki: Poison Lizard).
        nearby = defenders
        if owner_present:
            nearby = [
                u for u in defenders if dist(u.x, u.y, hero.x, hero.y) <= hero.range
            ]
        if nearby:
            return _nearest(pet, nearby)
    if pet.name == "Sneezy":
        return _nearest(
            pet, [b for b in buildings if battle.is_defense_target(b)] or buildings
        )
    if owner_present:
        if pet.name == "Mighty Yak":
            if hero.target is not pet.extra.get("hero_target"):
                pet.wall_target = None
                pet.extra["hero_target"] = hero.target
            if _valid(battle, pet, hero.wall_target):
                return hero.wall_target
            if _valid(battle, pet, pet.wall_target):
                return pet.wall_target
        preference = stats.attrs(pet.name).get("preferred_target", "")
        if preference.startswith("Within "):
            radius = stats.num(preference)
            candidates = [
                target
                for target in buildings + defenders
                if dist(target.x, target.y, hero.x, hero.y) <= radius
            ]
            return _nearest(pet, candidates)
        if pet.name == "Diggy" and _valid(battle, pet, hero.wall_target):
            return hero.wall_target
        if _valid(battle, pet, hero.target):
            return hero.target
        return None
    return _nearest(pet, buildings + defenders)


def owner_defeated(battle, pet):
    if not pet.alive or pet.extra.get("owner_defeated"):
        return
    pet.extra["owner_defeated"] = True
    raw = stats.attrs(pet.name).get("raw", {})
    if pet.name in ("Mighty Yak", "Sneezy"):
        # Duration, damage and movement from Mighty Yak/Sneezy.
        units.add_rage(
            pet,
            pet.name,
            1.0 + stats.num(raw["Rage Damage Increase"]) / 100.0,
            stats.num(raw.get("Rage Speed Increase"), 0.0) / 8.0,
            battle.t + stats.num(raw["Rage Duration"]),
        )
    if pet.name == "Sneezy":
        pet.range = 1.5  # wiki: Sneezy, attack range after owner defeat
    pet.target = pet.wall_target = None


def _summon(battle, pet):
    if pet.name not in ("Frosty", "Sneezy"):
        return False
    if battle.t < pet.extra["next_summon"]:
        return False
    alive = [child for child in pet.extra.get("children", []) if child.alive]
    if pet.name == "Sneezy":
        name, level, count, cap, cooldown = (
            "Booger",
            pet.level,
            1,
            2,
            10.0,
        )  # wiki: Sneezy
    else:
        name, level = "Frostmite", 1
        count = int(stats.get("Frosty", pet.level, "Frostmites per Summon"))
        cap = int(stats.get("Frosty", pet.level, "Maximum Frostmites Summoned"))
        cooldown = stats.num(stats.attrs("Frosty")["raw"]["Summon Cooldown"])
    for _ in range(min(count, max(0, cap - len(alive)))):
        child = battle.spawn(
            name,
            pet.team,
            pet.x,
            pet.y,
            level=level,
            kind="summon",
            owner=pet,
            group=pet.group,
        )
        if name == "Booger":
            child.flying = True  # wiki: Sneezy/Booger
        alive.append(child)
    pet.extra["children"] = alive
    pet.extra["next_summon"] = battle.t + cooldown
    # Sneezy pauses to summon; the pause length is not stated.
    return pet.name == "Sneezy"


def act(battle, pet):
    hero = pet.owner
    present = hero is not None and hero.alive
    t = battle.t
    passives(battle, pet)
    if pet.extra.get("egg"):
        if present:
            # The egg keeps up with a faster Hero (wiki: Phoenix).
            speed = max(battle.speed_of(pet), battle.speed_of(hero))
            battle.move_straight(pet, hero.x, hero.y, speed * battle.DT)
        return
    if pet.name == "Unicorn":
        pet.extra["healing_targets"] = set()
        target = (
            hero
            if present
            else _nearest(
                pet,
                [
                    ally
                    for ally in battle.attackers
                    if ally.alive
                    and ally is not pet
                    and ally.hp < ally.max_hp
                    and ally.kind not in ("siege", "siege_idle")
                    and ally.spec.attack not in ("heal", "heal_chain")
                ],
            )
        )
        pet.target = target
        if target is not None:
            # Heal at 2.5 tiles, including flying Heroes (wiki: Unicorn).
            if dist(pet.x, pet.y, target.x, target.y) <= 2.5:
                pet.extra["healing_targets"] = {target}
                effectiveness = units.heal_effectiveness(battle, pet, target)
                target.heal(
                    stats.get("Unicorn", pet.level, "Healing per Second")
                    * battle.DT
                    * effectiveness
                )
            else:
                battle.move_towards(pet, target)
        return
    if _summon(battle, pet):
        return
    if pet.name == "Sneezy" and not pet.extra.get("owner_defeated"):
        if present and dist(pet.x, pet.y, hero.x, hero.y) > pet.range:
            battle.move_towards(pet, hero)
        return
    target = _target(battle, pet)
    pet.target = target
    if target is None:
        if pet.name == "Diggy":
            pet.underground = True
        if present and not pet.attached(t):
            battle.move_towards(pet, hero)
        return
    distance = (
        target.edge_distance(pet.x, pet.y)
        if not isinstance(target, Unit)
        else dist(pet.x, pet.y, target.x, target.y)
    )
    if distance > pet.range:
        if pet.name == "Diggy":
            pet.underground = True
        if not pet.attached(t):
            battle.move_towards(pet, target)
            if pet.name == "Mighty Yak":
                pet.extra["moved"] = True
        return
    if pet.name == "Diggy" and pet.underground:
        pet.underground = False
        if isinstance(target, Building) and battle.is_defense_target(target):
            target.stun_until = max(
                target.stun_until, t + stats.get("Diggy", pet.level, "Stun Duration")
            )
    if pet.cooldown > 0:
        return
    with effects.damage_source(battle, pet, "attack"):
        units.strike(battle, pet, target)
    interval = pet.interval
    if pet.name == "Mighty Yak" and pet.extra.pop("moved", False):
        interval = 1.6  # Second strike after moving (wiki: Mighty Yak).
    pet.cooldown += interval / max(0.05, effects.slow_mult(pet, t))
    if pet.name == "Poison Lizard" and isinstance(target, Unit):
        # The poison affects troops and Heroes only (wiki: Poison Lizard).
        spells._poison(
            battle,
            target,
            stats.get(pet.name, pet.level, "Poison Max Damage per Second"),
            stats.get(pet.name, pet.level, "Poison Speed Decrease") / 100.0,
            stats.get(pet.name, pet.level, "Poison Attack Rate Decrease") / 100.0,
            1.0,
            ramp=True,
        )
    if pet.name == "Electro Owl":
        # Two targets, with 80% damage on the second (wiki: Electro Owl).
        candidates = [
            target
            for target in battle.buildings + battle.defenders
            if target is not pet.target
            and _valid(battle, pet, target)
            and _owl_link(pet.target, target)
        ]
        second = min(
            candidates, key=lambda a: dist(a.x, a.y, target.x, target.y), default=None
        )
        if second is not None:
            damage = pet.dmg * max(units.rage_boost(pet, t)[0], pet.aura_dmg) * 0.8
            if isinstance(second, Unit):
                battle.hit_unit(second, damage, attacker=pet, kind="chain")
            else:
                battle.hit_building(second, damage)


def _owl_link(first, second):
    if not isinstance(first, Building) or not isinstance(second, Building):
        return False
    # Two empty tiles between buildings stop a chain (wiki: Electro Owl).
    dx = max(0.0, abs(first.x - second.x) - (first.size + second.size) / 2.0)
    dy = max(0.0, abs(first.y - second.y) - (first.size + second.size) / 2.0)
    return (dx * dx + dy * dy) ** 0.5 < 2.0


def passives(battle, pet):
    hero = pet.owner
    present = hero is not None and hero.alive
    t = battle.t
    if pet.name == "Spirit Fox" and t >= pet.extra["fox_next"]:
        duration = stats.get("Spirit Fox", pet.level, "Invisibility Duration")
        pet.invisible_until = max(pet.invisible_until, t + duration)
        if present:
            hero.invisible_until = max(hero.invisible_until, t + duration)
        pet.extra["fox_next"] = t + duration + 6.0  # wiki: Spirit Fox
    if pet.attached(t):
        pet.x, pet.y = hero.x, hero.y
