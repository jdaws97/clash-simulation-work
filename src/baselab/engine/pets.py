"""Pet targeting and support effects from the individual wiki pages."""

import math

from . import effects, stats, units
from .entities import Building, Pending, Unit, Wall, dist


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


def _hero(battle, pet):
    hero = pet.extra.get("diggy_hero", pet.owner)
    if (
        pet.name == "Diggy"
        and hero is not None
        and not hero.alive
        and "recalled" not in hero.extra
    ):
        # Seek another active Hero after defeat, not Recall (wiki: Diggy).
        hero = _nearest(
            pet,
            [
                ally
                for ally in battle.attackers
                if ally is not hero
                and ally.kind == "hero"
                and ally.alive
                and "recalled" not in ally.extra
                and not ally.extra.get("suspended")
                and battle.t >= ally.active_at
            ],
        )
        if hero is not None:
            pet.extra["diggy_hero"] = hero
    return hero


def _independent(battle, pet, buildings, defenders):
    from .battle import ENGAGE_RADIUS

    target = pet.target
    # Use ordinary defender awareness after owner loss (wiki: Pets).
    if battle.t < pet.aware_until or battle._ally_under_attack(pet):
        nearby = [
            defender
            for defender in defenders
            if dist(pet.x, pet.y, defender.x, defender.y) <= ENGAGE_RADIUS
        ]
        defender = _nearest(pet, nearby)
        if defender is not None:
            return defender
    if _valid(battle, pet, pet.wall_target):
        return pet.wall_target
    if target in buildings or target in defenders:
        return target
    target, _ = battle.choose_target(pet)
    return target if _valid(battle, pet, target) else None


def _target(battle, pet):
    hero = _hero(battle, pet)
    owner_present = hero is not None and hero.alive
    buildings = [b for b in battle.buildings if _valid(battle, pet, b)]
    defenders = [u for u in battle.defenders if _valid(battle, pet, u)]
    if pet.name == "Greedy Raven":
        resources = [
            building
            for building in battle.buildings
            if building.alive
            and (building.kind == "resource" or building.key in units.RESOURCE_KEYS)
        ]
        if resources:
            # Prefer resources near the Hero; no hard leash is stated.
            return _nearest(
                hero if owner_present else pet,
                [building for building in resources if _valid(battle, pet, building)],
            )
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
        # About 6.5 tiles from the Hero (wiki: Poison Lizard).
        nearby = defenders
        if owner_present:
            nearby = [u for u in defenders if dist(u.x, u.y, hero.x, hero.y) <= 6.5]
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
        # Owner-target pets follow the wall actually being attacked.
        if _valid(battle, pet, hero.wall_target):
            return hero.wall_target
        if pet.name == "Diggy" and isinstance(hero.target, Unit) and hero.target.flying:
            return _nearest(pet, buildings)
        if _valid(battle, pet, hero.target):
            return hero.target
        return None
    return _independent(battle, pet, buildings, defenders)


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
    summon_at = pet.extra.get("summon_at")
    if summon_at is not None and battle.t < summon_at:
        return True
    if summon_at is None and battle.t < pet.extra["next_summon"]:
        return battle.t < pet.extra.get("summon_until", 0.0)
    alive = [child for child in pet.extra.get("children", []) if child.alive]
    if pet.name == "Sneezy":
        name, level, count, cap, cooldown = (
            "Booger",
            pet.level,
            1,
            2,
            10.0,
        )  # wiki: Sneezy
        if summon_at is None:
            pet.extra["next_summon"] = battle.t + cooldown
            if len(alive) >= cap:
                return True
            # game data v18.200.9: Sneezy.SummonDelay=1000 -> 1 s.
            pet.extra["summon_at"] = battle.t + 1.0
            # game data v18.200.9: Sneezy.SummonTime=1500 -> 1.5 s.
            pet.extra["summon_until"] = battle.t + 1.5
            return True
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
    if pet.name == "Sneezy":
        pet.extra.pop("summon_at", None)
        return battle.t < pet.extra["summon_until"]
    pet.extra["next_summon"] = battle.t + cooldown
    return False


def _move(battle, pet, target):
    if battle.t < pet.held_until:
        return
    previous = pet.x, pet.y
    battle.move_towards(pet, target)
    if pet.name == "Mighty Yak" and (pet.x, pet.y) != previous:
        # Movement restarts the ram sequence (wiki: Mighty Yak).
        pet.extra["yak_first"] = True
        pet.cooldown = 0.0


def act(battle, pet):
    hero = _hero(battle, pet)
    present = hero is not None and hero.alive
    if pet.extra.get("hero_present", True) and not present:
        # Abandon obsolete walls on knockout or Recall (wiki: L.A.S.S.I).
        pet.target = pet.wall_target = None
    pet.extra["hero_present"] = present
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
                due = pet.extra.get("heal_next", t)
                if t >= due or math.isclose(t, due):
                    # One-second pulses; first-pulse offset is unstated (wiki: Unicorn).
                    effectiveness = units.heal_effectiveness(battle, pet, target)
                    target.heal(
                        stats.get("Unicorn", pet.level, "Healing per Pulse")
                        * effectiveness
                    )
                    pet.extra["heal_next"] = t + stats.num(
                        stats.attrs("Unicorn")["raw"]["Healing Speed"]
                    )
            else:
                _move(battle, pet, target)
        return
    if _summon(battle, pet):
        return
    if pet.name == "Sneezy" and not pet.extra.get("owner_defeated"):
        if present and dist(pet.x, pet.y, hero.x, hero.y) > pet.range:
            _move(battle, pet, hero)
        return
    target = _target(battle, pet)
    pet.target = target
    if target is None:
        if pet.name == "Diggy":
            pet.underground = True
        if present and not pet.attached(t):
            _move(battle, pet, hero)
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
            _move(battle, pet, target)
        return
    if pet.name == "Diggy" and pet.underground:
        pet.underground = False
        if isinstance(target, Building) and battle.is_defense_target(target):
            target.stun_until = max(
                target.stun_until, t + stats.get("Diggy", pet.level, "Stun Duration")
            )
    if pet.name == "Mighty Yak" and pet.extra.get("yak_first", True):
        # Initial windup is 0.5 seconds (wiki: Mighty Yak).
        pet.extra["yak_first"] = False
        pet.cooldown = 0.5 / max(0.05, effects.slow_mult(pet, t))
        pet.extra["yak_second"] = True
    if pet.cooldown > 0 and not math.isclose(t + pet.cooldown, t):
        return
    with effects.damage_source(battle, pet, "attack"):
        units.strike(battle, pet, target)
    interval = pet.interval
    if pet.name == "Mighty Yak" and pet.extra.pop("yak_second", False):
        interval = 1.6  # Second strike after moving (wiki: Mighty Yak).
    delay = interval / max(0.05, effects.slow_mult(pet, t))
    if pet.name == "Mighty Yak":
        pet.cooldown = delay
    else:
        pet.cooldown += delay
    if pet.name == "Poison Lizard" and isinstance(target, Unit):
        from . import spells

        movement = stats.get(pet.name, pet.level, "Poison Speed Decrease") / 100.0
        attack = stats.get(pet.name, pet.level, "Poison Attack Rate Decrease") / 100.0
        _, movement, attack = spells.poison_factors(target, 0.0, movement, attack)
        # game data v18.200.9: LizardPetPoison.PoisonOnHitDuration=3000 -> 3 s.
        if not (target.kind == "guardian" and target.extra.get("waiting")):
            target.move_slow, target.move_slow_until = 1.0 - movement, t + 3.0
            target.atk_slow, target.atk_slow_until = 1.0 - attack, t + 3.0
        # Poison dose accumulation and residual damage remain unresolved.
    if pet.name == "Electro Owl":
        # Two targets, with 80% damage on the second (wiki: Electro Owl).
        candidates = [
            candidate
            for candidate in battle.buildings + battle.defenders
            if candidate is not target
            and _valid(battle, pet, candidate)
            and _owl_link(target, candidate)
        ]
        second = _nearest(target, candidates)
        if second is not None:
            boost = max(
                units.rage_boost(pet, t)[0],
                pet.aura_dmg,
                pet.extra.get("bell_damage", 1.0),
            )
            damage = pet.dmg * boost * 0.8
            # game data v18.200.9: Electro Owl.ChainAttackDelay=128 -> 0.128 s.
            battle.add_pending(
                Pending(
                    t + 0.128,
                    second.x,
                    second.y,
                    0.0,
                    damage,
                    False,
                    True,
                    pet.name,
                    extra={"direct": True},
                    actor=pet,
                    effect="chain",
                    target=second,
                )
            )


def _owl_link(first, second):
    if not isinstance(first, Building) or not isinstance(second, Building):
        return False
    # game data v18.200.9: Electro Owl.ChainAttackDistance=300 -> 3 tiles.
    # Keep the existing building-edge geometry and eligibility.
    dx = max(0.0, abs(first.x - second.x) - (first.size + second.size) / 2.0)
    dy = max(0.0, abs(first.y - second.y) - (first.size + second.size) / 2.0)
    return (dx * dx + dy * dy) ** 0.5 < 3.0


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
    if pet.name == "Angry Jelly":
        # game data v18.200.9: AngryJellyAbility.AttackRange=700 -> 7 tiles.
        # game data v18.200.9: Angry Jelly.AttackRange=500 -> 5 tiles.
        pet.range = 7.0 if pet.attached(t) else 5.0
    if pet.attached(t):
        pet.x, pet.y = hero.x, hero.y
