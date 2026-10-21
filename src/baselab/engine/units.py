"""Unit behaviour: strikes, healing, special abilities, death effects.

Each special ability cites the wiki fact it implements (mirror 2026-10-15).
Values marked 'assumed' are not stated on the wiki and should be checked
against replays.
"""

from __future__ import annotations

import math

import numpy as np

from . import effects, stats
from .specs import unit_numbers
from .entities import Building, Field, Pending, Unit, Wall, dist

RESOURCE_KEYS = {"gm", "ec", "dd", "gs", "es", "ds", "th", "cc"}


# ------------------------------------------------------------------ helpers
def add_rage(u, source, damage, speed, until):
    # Each source keeps its own expiry (wiki: Rage Spell/Home Village).
    u.extra.setdefault("rage_effects", {})[source] = (damage, speed, until)


def rage_boost(u, t):
    damage = u.rage_dmg if t < u.rage_until else 1.0
    speed = u.rage_spd if t < u.rage_until else 0.0
    for dmg, spd, until in u.extra.get("rage_effects", {}).values():
        if t < until:
            damage = max(damage, dmg)
            speed = max(speed, spd)
    return damage, speed


def haste_speed(u, t):
    speed = u.haste_spd if t < u.haste_until else 0.0
    for added, until in u.extra.get("haste_effects", {}).values():
        if t < until:
            speed = max(speed, added)
    return speed


def duke_alone(battle, u) -> bool:
    # Dragon Duke: Royal Rampage requires no other air units within 6 tiles.
    for a in battle.attackers_near(u.x, u.y, 6.0):
        if a is u or not a.flying or a.name == "Totem":
            continue
        if a.kind == "pet" and a.owner is u:
            # Dragon Duke: own pets count after defeat, except active Phoenix.
            phoenix = u.kit is not None and u.kit.doomed_at is not None
            if not a.extra.get("rampage_detached") or phoenix:
                continue
        return False
    return True


def segment_entry(x, y, tx, ty, target):
    """First contact with a square hitbox along a movement segment."""
    enter, leave = 0.0, 1.0
    for start, end, center in ((x, tx, target.x), (y, ty, target.y)):
        low = center - target.half_hit
        high = center + target.half_hit
        delta = end - start
        if delta == 0:
            if start < low or start > high:
                return None
            continue
        first, last = sorted(((low - start) / delta, (high - start) / delta))
        enter = max(enter, first)
        leave = min(leave, last)
    return enter if enter <= leave else None


_WARDEN = None


def warden_weights() -> dict:
    """Warden Weight table, vision radius and threshold (data/warden-weights.json,
    from the wiki's Template:Warden_Weight)."""
    global _WARDEN
    if _WARDEN is None:
        import json
        from pathlib import Path

        _WARDEN = json.loads((Path(__file__).resolve().parents[3] / "data" / "warden-weights.json").read_text())
    return _WARDEN


def wall_breaker_target(battle, u):
    """Find connected walls protecting an actual building."""
    from . import spells

    if battle.wall_mode(u) == "ignore":
        return None
    walls = {
        key: wall
        for key, wall in battle.walls.items()
        if wall.alive and not spells.wall_jumped(battle, wall)
    }
    connected = set()
    unseen = set(walls)
    while unseen:
        todo = [unseen.pop()]
        component = set(todo)
        while todo:
            x, y = todo.pop()
            for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    component.add(neighbor)
                    todo.append(neighbor)
        # Wiki: Wall Breaker requires at least three connected walls.
        if len(component) >= 3:
            connected.update(component)
    buildings = sorted(
        (b for b in battle.buildings if battle.building_targetable(b)),
        key=lambda b: b.edge_distance(u.x, u.y),
    )
    if not buildings:
        return None
    from ..pathing import Grid, RES

    grid = battle.navigation_grid(u)
    access = Grid(grid.n // RES)
    access.blocked[:] = grid.blocked | grid.wall
    # Access means reaching a cell beside the hitbox, without crossing a wall.
    reach = 1.0 / RES
    open_costs = access.building_costs(
        u.x,
        u.y,
        0.0,
        np.array([b.x for b in buildings]),
        np.array([b.y for b in buildings]),
        np.array([b.half_hit for b in buildings]),
        reach,
    )
    for building, cost in zip(buildings, open_costs):
        if cost < 1e9:
            continue  # An opening already gives access to this building.
        route = grid.field(
            ("breaker", building.id),
            building.x,
            building.y,
            building.half_hit,
            reach,
            0.0,
        )
        x, y = u.x, u.y
        visited = set()
        while grid.cell(x, y) not in visited:
            visited.add(grid.cell(x, y))
            x, y, is_wall, at_goal = grid.next_step(route, x, y)
            if at_goal:
                break
            if is_wall:
                key = (int(x), int(y))
                if key in connected:
                    return walls[key]
                break
    return None


def follow_target(battle, u):
    """Grand Warden group mode (wiki: Grand Warden, Template:Warden_Weight): he
    sums the Warden Weight of friendly units within 13 tiles; at 20 or more he
    follows the building (or wall) most of that weight targets, otherwise he
    targets the nearest building himself (None here)."""
    ww = warden_weights()
    table, radius = ww["weights"], ww["vision_radius"]
    threshold = ww["threshold"]
    if u.name == "Apprentice Warden":
        # game data v18.200.9: Apprentice Warden.TargetGroupsRange=1300 -> 13 tiles.
        radius = 13.0
        # game data v18.200.9: Apprentice Warden.TargetGroupsMinWeight=1000 -> 10 Warden Weight.
        threshold = 10.0
        # The existing aggregate heuristic does not model group clustering.
    score: dict = {}
    total_weight = 0.0
    for a in battle.attackers_near(u.x, u.y, radius):
        if a is u or not a.alive or a.name in ("Totem", "Yetimite"):
            continue
        if a.is_hero:
            weight = ww["heroes"]
        elif a.kind == "pet":
            weight = ww["pets"]
        else:
            weight = table.get(a.name, 0.0)
        total_weight += weight
        target = (
            a.wall_target
            if a.wall_target is not None and a.wall_target.alive
            else a.target
        )
        if (
            target is None
            or not target.alive
            or not isinstance(target, (Building, Wall))
        ):
            continue
        score[target] = score.get(target, 0.0) + weight
    if total_weight < threshold or not score:
        return None
    return max(score.items(), key=lambda kv: kv[1])[0]


def rubble_target(battle, u):
    best, bd = None, 1e9
    for b in battle.buildings:
        if (
            b.alive
            or not b.counted
            or b.extra.get("rubble_taken")
            or battle.t < b.invisible_until
            or battle.t < b.overgrown_until
        ):
            continue
        claim = b.extra.get("rubble_claim")
        if claim not in (None, u.id) and any(
            witch.alive and witch.id == claim for witch in battle.attackers
        ):
            continue
        grid = battle.navigation_grid(u)
        field = grid.field(
            ("rubble", b.id, u.range), b.x, b.y, b.half_hit, u.range, math.inf
        )
        i, j = grid.cell(u.x, u.y)
        if not math.isfinite(float(field[i, j])) or field[i, j] >= 1e9:
            continue
        d = dist(u.x, u.y, b.x, b.y)
        if d < bd:
            bd, best = d, b
    return (best, "rubble") if best is not None else (None, None)


def smash_wall(battle, u, w):
    # Wiki: Root Rider deals 4000 wall damage every 0.4 seconds.
    clocks = u.extra.setdefault("wall_pulses", {})
    due = clocks.get(w.id, battle.t)
    if battle.t >= due or math.isclose(battle.t, due):
        battle.hit_building(w, 4000.0)
        clocks[w.id] = due + 0.4


# ------------------------------------------------------------------ spawning

def on_spawn(battle, u: Unit):
    if u.name == "Spell Skeleton":
        # Wiki: Skeleton Spell/Skeleton, 30 armor HP; overkill is discarded.
        u.extra["armor_hp"] = 30.0
    sp = u.spec
    t = battle.t
    # Speed boosts stay at the wiki's +52 and +16 (wiki units / 8). The
    # abilities' own SpeedBoost (318, 150) has no proven unit: it is neither
    # wiki units nor hundredths of a tile per second. The spell rows
    # TroopHaste (52, 4000 ms) and TroopRage (16, +70%, 8000 ms at level 2)
    # match the wiki exactly, but no game-data row links them to these troops.
    # game data v18.200.9: RocketBallonAbility.SpeedBoost=318 -> unit unresolved.
    # game data v18.200.9: RocketBallonAbility.DeactivateAfterTime=4000 -> 4 s.
    # game data v18.200.9: Super Barbarian Ability.SpeedBoost=150 -> unit unresolved.
    # game data v18.200.9: Super Barbarian Ability.DeactivateAfterTime=8000 -> 8 s.
    if "boosters" in sp.special:
        u.haste_spd = 52 / 8.0  # first 4 s, like a L5 Haste (wiki)
        u.haste_until = t + 4.0
    if "cloak" in sp.special:
        u.invisible_until = t + 5.0
    if "start_rage" in sp.special:
        # Wiki: Super Barbarian/Home Village, +70%, +16 speed, eight seconds.
        add_rage(u, "innate", 1.7, 16 / 8.0, t + 8.0)
    if "burrow" in sp.special:
        u.underground = u.team == "atk"
        if u.name == "Miner" and u.team == "def":
            u.speed = 2.5  # Wiki: Miner, defensive movement speed 20.
        if u.name == "Super Miner" and u.team == "def":
            # game data v18.200.9: Super Miner.Speed=400 -> 4 tiles/s before the ground penalty.
            # game data v18.200.9: UNDERGROUND_UNIT_GROUND_SPEED_PERCENTAGE.NumberValue=70 -> 70%.
            u.speed = 4.0 * 0.7
    if "yetimites" in sp.special:
        u.extra["mites"] = int(stats.get(u.name, u.level, "Yetimites spawned", default=14))
        u.extra["mite_dmg"] = 0.0
    if "electromites" in sp.special:
        u.extra["mites"] = int(stats.get(u.name, u.level, "Electromites spawned", default=14))
        u.extra["mite_dmg"] = 0.0
    if "furnace" in sp.special:
        u.extra["mites"] = int(stats.get(u.name, u.level, "Firemites Spawned", default=22))
        # Wiki: Furnace does not state startup or per-level spawn intervals.
        # Keep the existing timing approximation explicit.
        u.extra["next_mite"] = t + 1.0
        u.decay = u.max_hp / 60.0
    if "siege_barracks" in sp.special:
        u.decay = u.max_hp / 30.0
        u.extra["queue"] = ["P.E.K.K.A"] * int(stats.get(u.name, u.level, "Troops Spawned / P.E.K.K.As", default=2)) + ["Wizard"] * int(stats.get(u.name, u.level, "Troops Spawned / Wizards", default=12))
        u.extra["next"] = t + 0.5
    if "logs" in sp.special:
        u.decay = 156.0
        u.extra["next_log"] = t + 1.0
    if "flinger" in sp.special:
        u.decay = 17.0
    if u.name == "Druid":
        u.extra["bear_at"] = t + 30.0
    if "witch_skeletons" in sp.special:
        u.extra["next_summon"] = t + 3.0
        u.extra["skeletons"] = []
    if "big_boy" in sp.special:
        u.extra["next_summon"] = t + 4.0
    if "ruin_witch" in sp.special:
        u.extra["knights"] = 0
    if "long_shot" in sp.special:
        # Wiki: Super Minion; offense has eight Long Shots, defense three.
        u.extra["long_shots"] = 8 if u.team == "atk" else 3
        # Projectile speed is selected before consuming each Long Shot.
    if "burst" in sp.special:
        # Wiki: Super Dragon/Home Village.
        u.extra["burst_left"] = int(
            stats.num(stats.attrs(u.name)["raw"]["Shots per Burst"])
        )
    # Super Valkyrie's first wind-up is NUMBER NOT STATED (wiki: Super Valkyrie).
    # Keep the existing first-attack timing and ordinary interval.
    if "sky_wagon" in sp.special:
        u.extra["barrels"] = int(stats.get(u.name, u.level, "Barrel Count", default=5))
        u.extra["next"] = t + 2.0
    if "troop_launcher" in sp.special:
        u.extra["barrels"] = int(stats.get(u.name, u.level, "Barrel Count", default=7))
        u.extra["next"] = t + 2.0
        # Wiki: Troop Launcher states lifetime, but no HP-decay curve.
        u.extra["expires_at"] = t + stats.get(u.name, u.level, "Lifetime")


@effects.sourced("aura")
def pre_tick(battle, u: Unit) -> bool:
    """Per-tick upkeep. Returns True if the unit should do nothing else."""
    t = battle.t
    sp = u.spec
    if u.extra.get("leaping"):
        return True
    if u.name == "Meteormite" and try_merge_meteor(battle, u):
        return True
    if sp.attack == "beam" and u.target is not None:
        # Wiki: Inferno Dragon/Home Village; Sweeper range interruptions reset.
        if target_distance(u, u.target) > effective_range(u):
            reset_beam(u)
    if u.extra.get("mirror_clone") and t >= u.extra["expire_at"]:
        # Clones vanish at a fixed time, regardless of healing (wiki: Magic Mirror).
        u.alive = False
        u.hp = 0.0
        return True
    if t >= u.extra.get("expires_at", math.inf):
        battle.kill(u)
        return True
    if u.name == "Root Rider" and u.team == "atk":
        contacts = set()
        for wall in battle.walls.values():
            # contact starts when her body reaches the wall, half a tile before
            # her centre does: at normal speed walls "will be destroyed as she
            # passes through them" (wiki: Root Rider), which needs the 3 hits
            # (0.8 s) that a centre-only contact cuts to 2
            if wall.alive and wall.edge_distance(u.x, u.y) <= 0.5:
                contacts.add(wall.id)
                smash_wall(battle, u, wall)
        clocks = u.extra.get("wall_pulses", {})
        for key in list(clocks):
            if key not in contacts:
                clocks.pop(key)
    if u.name == "Totem" or u.decay > 0:
        u.hp -= u.decay * battle.DT
        if u.hp <= 0:
            battle.kill(u)
            return True
    if u.kind == "pet":
        from . import heroes

        heroes.pet_passives(battle, u)
        if u.can_act(t):
            u.cooldown = max(u.cooldown - battle.DT, -battle.DT)
            heroes.act_pet(battle, u)
        return True
    if u.kit is not None:
        from . import heroes

        heroes.tick(battle, u)
        if not u.alive:
            return True
        if u.dash is not None:
            if t >= u.frozen_until and t >= u.stun_until:
                heroes.dash_step(battle, u)
            return True
    if u.name == "Totem":
        return True
    # before the no-special return: the Giant Giant has no special tag (found by the 2026-10-18 audit)
    if u.name == "Giant Giant" and not u.extra.get("enraged") and u.hp <= 0.5 * u.max_hp:
        # enrages at half health: +50% damage, +12 speed for 20 s (wiki: Giant Giant)
        u.extra["enraged"] = True
        u.rage_dmg, u.rage_spd, u.rage_until = 1.5, 12.0 / 8.0, t + 20.0
    special = sp.special
    if not special:
        return False
    if "titan_aura" in special:
        due = u.extra.get("aura_next", t)
        if t >= due or math.isclose(t, due):
            # Wiki: Electro Titan pulses every 0.4 seconds, radius 3.5.
            damage = stats.get(u.name, u.level, "Aura Damage per Hit")
            u.extra["aura_next"] = due + 0.4
            pool = battle.defenders if u.team == "atk" else battle.attackers
            for foe in list(pool):
                if foe.alive and dist(u.x, u.y, foe.x, foe.y) <= 3.5:
                    # game data v18.200.9: Electro Titan Aura.HeroDamageMultiplier=25 -> heroes take 25%.
                    battle.hit_unit(foe, damage * 0.25 if foe.is_hero else damage)
            if u.team == "atk":
                for building in battle.buildings:
                    if (
                        building.alive
                        and building.counted
                        and building.edge_distance(u.x, u.y) <= 3.5
                    ):
                        battle.hit_building(building, damage)

    if u.name == "Druid" and t >= u.extra.get("bear_at", 1e9):
        _transform_bear(battle, u)
        return True
    if "ruin_witch" in special and u.team == "atk":
        vacuum = u.extra.get("vacuum")
        if vacuum is not None:
            rubble, started = vacuum
            # Wiki: Ruin Witch commits rubble after four seconds.
            if not u.extra.get("delivery_committed") and t >= started + 4.0:
                rubble.extra["rubble_taken"] = True
                u.extra["delivery_committed"] = True
                u.extra["knights"] += 1
                level = int(stats.get(u.name, u.level, "Ruin Knight Level"))
                battle.add_pending(
                    Pending(
                        started + 6.0,
                        u.x,
                        u.y,
                        0.0,
                        0.0,
                        False,
                        False,
                        "Ruin Witch",
                        team=u.team,
                        extra={"summon": ("Ruin Knight", level, u.group, u)},
                    )
                )
            if t >= started + 6.0:
                u.extra.pop("vacuum")
                u.extra.pop("delivery_committed", None)
                if u.extra["knights"] >= int(
                    stats.get(u.name, u.level, "Maximum Ruin Knights Summoned")
                ):
                    battle.kill(u)
            return True
        target = u.target
        if (
            target is not None
            and not target.alive
            and getattr(target, "counted", False)
            and not target.extra.get("rubble_taken")
            and target.edge_distance(u.x, u.y) <= u.range
            and u.can_act(t)
            and t >= u.held_until
        ):
            target.extra["rubble_claim"] = u.id
            u.extra["vacuum"] = (target, t)
            u.target = None
            return True

    if "witch_skeletons" in special and u.can_act(t) and t >= u.extra["next_summon"]:
        alive = [s for s in u.extra["skeletons"] if s.alive]
        cap = int(stats.get(u.name, u.level, "Maximum Skeletons Summoned", default=16))
        n = min(int(stats.get(u.name, u.level, "Skeletons per Summon", default=5)), cap - len(alive))
        for k in range(max(0, n)):
            s = battle.spawn(
                "Skeleton",
                u.team,
                u.x + 0.6 * math.cos(k),
                u.y + 0.6 * math.sin(k),
                level=int(stats.get(u.name, u.level, "Skeleton Level")),
                kind="summon",
                group=u.group,
                owner=u,
            )
            alive.append(s)
        u.extra["skeletons"] = alive
        # Wiki: Witch gives a seven-second summon cooldown.
        # Summon animation and first-summon delay remain unquantified.
        u.extra["next_summon"] = t + 7.0
        if n > 0:
            return True
    if "big_boy" in special and t >= u.extra["next_summon"]:
        bb = u.extra.get("bb")
        if bb is None or not bb.alive:
            u.extra["bb"] = battle.spawn("Big Boy", u.team, u.x + 0.5, u.y, level=1, kind="summon", group=u.group, owner=u)
        u.extra["next_summon"] = t + 5.0
    if (
        "furnace" in special
        and u.team == "def"
        and not any(a.targetable(t) and a.name != "Totem" for a in battle.attackers)
    ):
        u.extra["next_mite"] += battle.DT
    if "furnace" in special and t >= u.extra["next_mite"] and u.extra["mites"] > 0:
        u.extra["mites"] -= 1
        battle.spawn(
            "Firemite",
            u.team,
            u.x + 0.5,
            u.y + 0.5,
            level=u.level,
            kind="summon",
            group=u.group,
            owner=u,
        )
        u.extra["next_mite"] = t + 60.0 / 22.0
    if "siege_barracks" in special and t >= u.extra["next"] and u.extra["queue"]:
        name = u.extra["queue"].pop(0)
        # Wiki: Siege Barracks uses unboosted researched levels, or level one.
        researched = getattr(battle.plan, "troop_levels", {})
        level = researched.get(name, stats.max_level(name, battle.plan.town_hall)) or 1
        battle.spawn(
            name, u.team, u.x + 0.6, u.y + 0.6, level=level, kind="troop", group=u.group
        )
        # Startup and level-specific schedules are not stated by the wiki.
        u.extra["next"] = t + 30.0 / 14.0
    if "logs" in special and u.can_act(t) and t >= u.extra["next_log"]:
        _roll_log(battle, u)
        u.extra["next_log"] = t + 3.0
    if (
        "troop_launcher" in special
        and u.can_act(t)
        and t >= u.extra["next"]
        and u.extra["barrels"] > 0
    ):
        target = launcher_target(battle, u)
        if target is not None:
            launch_barrel(battle, u, target)

    if "blimp_bombs" in special and u.can_act(t) and t >= u.extra.get("next_bomb", 0.0):
        dmg = stats.get(u.name, u.level, "Damage per Attack", default=450.0)
        battle.splash_buildings(u.x, u.y, 1.5, dmg, walls=False)
        u.extra["next_bomb"] = t + 1.5
    return False


def update_burrow(battle, u, target):
    if "burrow" not in u.spec.special:
        return
    if u.team == "def":
        u.underground = False
        return
    was_underground = u.underground
    retreating = target is None or target_distance(u, target) > effective_range(u)
    if u.name == "Miner" and retreating and not was_underground:
        # game data v18.200.9: MINER_HIDE_TIME.NumberValue=1000 -> 1 s.
        # The random timer's distribution is unresolved; use the base component.
        hide_at = u.extra.setdefault("hide_at", battle.t + 1.0)
        u.held_until = max(u.held_until, hide_at)
        u.underground = battle.t >= hide_at
    else:
        u.underground = retreating
        hide_at = u.extra.pop("hide_at", None)
        if not retreating and hide_at is not None and u.held_until == hide_at:
            u.held_until = battle.t
    if u.name == "Battle Drill" and was_underground and not u.underground:
        # Wiki: Battle Drill destroys contacted walls on emergence.
        for wall in battle.walls.values():
            if wall.alive and math.isclose(wall.edge_distance(u.x, u.y), 0.0):
                battle.hit_building(wall, wall.hp)
        # Emergence stun radius and duration are not stated by its wiki page.


def _transform_bear(battle, u):
    u.alive = False
    bear = battle.spawn(
        "Bear", u.team, u.x, u.y, level=u.level, kind="summon", group=u.group, owner=u
    )
    bear.extra["from_druid"] = True


def _roll_log(battle, u):
    """Log Launcher: rolls a log towards the Town Hall; walls take x4, the log
    stops after hitting four buildings (wiki)."""
    th = battle.th
    tx, ty = (th.x, th.y) if th is not None else (25.0, 25.0)
    dx, dy = tx - u.x, ty - u.y
    d = math.hypot(dx, dy) or 1.0
    dx, dy = dx / d, dy / d
    dmg = stats.get(u.name, u.level, "Damage per Hit", default=690.0) * u.extra.get("strength", 1.0)
    wall_dmg = stats.get(u.name, u.level, "Damage per Hit vs. Walls", default=dmg * 4)
    # point-blank blast with every launch (wiki): structures and units right
    # next to the launcher
    pb = stats.get(u.name, u.level, "Point-Blank Damage*", "Point-Blank Damage", default=0.0)
    if pb:
        # Wiki: Log Launcher gives radius one and fourfold wall damage.
        battle.splash_buildings(u.x, u.y, 1.0, pb, walls=True, wall_mult=4.0)
        battle.splash_units(u.x, u.y, 1.0, pb, False, True, team="def")
    hit_b = set()
    hit_w = set()
    hit_units = set()
    for step in range(0, 41):  # logs travel up to 20 tiles (wiki)
        px, py = u.x + dx * step * 0.5, u.y + dy * step * 0.5
        for k in ((int(px), int(py)), (int(px + 0.5), int(py)), (int(px), int(py + 0.5))):
            w = battle.walls.get(k)
            if w is not None and w.alive and k not in hit_w:
                hit_w.add(k)
                battle.hit_building(w, wall_dmg)
        for b in battle.buildings:
            if b.alive and b.counted and b.id not in hit_b and b.edge_distance(px, py) < 0.8:
                hit_b.add(b.id)
                battle.hit_building(b, dmg)
                if len(hit_b) >= 4:
                    return
        # Log width and travel speed remain the existing approximations.
        for foe in battle.defenders:
            if (
                foe.alive
                and not foe.flying
                and foe not in hit_units
                and dist(px, py, foe.x, foe.y) < 0.8
            ):
                hit_units.add(foe)
                battle.hit_unit(foe, dmg, attacker=u)


# --------------------------------------------------------------- damage in
def on_damaged(battle, u: Unit, amount: float):
    sp = u.spec
    if "electromites" in sp.special:
        # One Electromite per 400 damage taken (wiki: Super Yeti/Electromite).
        # The Super Yeti page's "400, then every 800" has no game-data
        # counterpart: the ability row has the same layout as the Yeti's, whose
        # SpawnnedTroopsPerDamage=600 is the wiki's "for every 600 damage".
        # game data v18.200.9: SuperYetiSpawnYetiMites.SpawnnedTroopsPerDamage=400 -> one per 400 damage.
        u.extra["mite_dmg"] += amount
        threshold = u.extra.get("next_mite_damage", 400.0)
        while u.extra["mites"] > 0 and u.extra["mite_dmg"] >= threshold:
            u.extra["mites"] -= 1
            threshold += 400.0
            battle.spawn(
                "Electromite",
                u.team,
                u.x,
                u.y,
                level=u.level,
                kind="summon",
                group=u.group,
                owner=u,
            )
        u.extra["next_mite_damage"] = threshold
        return
    if "yetimites" in sp.special:
        # game data v18.200.9: YetiSpawnYetiMites.SpawnnedTroopsPerDamage=600 -> one per 600 damage.
        u.extra["mite_dmg"] += amount
        while u.extra["mites"] > 0 and u.extra["mite_dmg"] >= 600.0:
            u.extra["mite_dmg"] -= 600.0
            u.extra["mites"] -= 1
            battle.spawn(
                "Yetimite",
                u.team,
                u.x + 0.4,
                u.y + 0.4,
                level=u.level,
                kind="summon",
                group=u.group,
                owner=u,
            )


# ------------------------------------------------------------------- death
@effects.sourced("death")
def on_death(battle, u: Unit):
    sp = u.spec
    t = battle.t
    if sp.death_damage and not u.extra.get("suicided"):
        # Death damage hits ground only unless the unit sets DieDamageAffectsAir,
        # which only the Longshot does (Golem, Lava Hound, Dragon Rider, Rocket
        # Balloon, Stone Slammer leave it unset; wiki: Balloon, ground only).
        # game data v18.200.9: Longshot.DieDamageAffectsAir=TRUE -> also hits air.
        death_air = u.name == "Longshot"
        dmg = stats.get(u.name, u.level, sp.death_damage, default=0.0)
        if dmg and sp.death_delay > 0:
            # Delayed death damage (DieDamageDelay, cited per unit in specs.py)
            # lands where the unit died. Only the Wall Breakers, which have no
            # delay, carry a separate wall column.
            battle.add_pending(
                Pending(
                    t + sp.death_delay,
                    u.x,
                    u.y,
                    sp.death_radius or 1.2,
                    dmg,
                    death_air,
                    True,
                    u.name,
                    team="def" if u.team == "atk" else "atk",
                    extra={"buildings": dmg if u.team == "atk" else 0.0},
                    actor=u,
                    effect="death",
                )
            )
        elif dmg:
            if u.team == "atk":
                # Wall Breakers killed early still blast walls at x40 (wiki
                # "Damage when destroyed vs. Walls")
                wall_dmg = stats.get(u.name, u.level, sp.death_damage + " vs. Walls", sp.death_damage.replace("Damage when destroyed", "Damage when destroyed to Walls"), default=dmg)
                battle.splash_buildings(u.x, u.y, sp.death_radius or 1.2, dmg, walls=True, wall_mult=wall_dmg / dmg)
                battle.splash_units(
                    u.x, u.y, sp.death_radius or 1.2, dmg, death_air, True, team="def"
                )
            else:
                battle.splash_units(
                    u.x, u.y, sp.death_radius or 1.2, dmg, death_air, True, team="atk"
                )
    if sp.death_freeze:
        secs = stats.get(u.name, u.level, sp.death_freeze, default=0.0)
        if u.team == "def":
            secs = stats.get(u.name, u.level, sp.death_freeze.replace("On Offense", "On Defense"), default=secs / 2.5)
        r = sp.death_freeze_radius
        if u.name == "Ice Golem":
            if battle.offense_finished():
                return
            # Wiki: Ice Golem has separate offense/defense freeze radii.
            r = 7.5 if u.team == "atk" else 5.5
            # Every target gets the full freeze. The spells also carry a
            # shorter FreezeOuterTimeMS, but no game-data field or wiki text
            # says where the outer ring starts, so it is not applied.
            # game data v18.200.9: IceGolemFreeze.FreezeOuterTimeMS=6500 -> outer ring 6.5 s at level 9 (ring unknown).
            if u.team == "def":
                # The wiki's 3.5 s at levels 7-9 is not what the game data
                # chains to: the defensive Ice Golem's ability stops at level 6.
                # game data v18.200.9: Defensive Ice Golem.SpecialAbilitiesLevel=6 -> ability level 6 at troop levels 6-9.
                # game data v18.200.9: IceGolemOnDeathDEF.SelfSpell=IceGolemFreeze_DEF -> the defensive freeze spell.
                # game data v18.200.9: IceGolemFreeze_DEF.FreezeTimeMS=3250 -> 3.25 s at spell level 6.
                secs = (2.0, 2.25, 2.5, 2.75, 3.0, 3.25)[min(max(u.level, 1), 6) - 1]
        elif u.name == "Ice Hound":
            if u.team == "atk":
                # game data v18.200.9: IceHoundFreeze.Radius=650 -> 6.5 tiles.
                r = 6.5
            else:
                # A defending Ice Hound casts the defensive Ice Golem freeze:
                # game data v18.200.9: IceHoundOnDeathDEF.SelfSpell=IceGolemFreeze_DEF
                # game data v18.200.9: IceGolemFreeze_DEF.Radius=550 -> 5.5 tiles.
                r = 5.5
                # Its spell level is 1 to Ice Hound level 5, then 2 (2.25 s):
                # game data v18.200.9: IceGolemFreeze_DEF.FreezeTimeMS=2000 -> 2 s at level 1.
                secs = 2.0 if u.level <= 5 else 2.25
        if u.team == "atk":
            for b in battle.buildings:
                if b.alive and b.edge_distance(u.x, u.y) <= r:
                    b.frozen_until = max(b.frozen_until, t + secs)
            for f in battle.defenders_near(u.x, u.y, r):
                f.frozen_until = max(f.frozen_until, t + secs)
        else:
            for a in battle.attackers_near(u.x, u.y, r):
                a.frozen_until = max(a.frozen_until, t + secs)
    if sp.death_spawn:
        name, count = sp.death_spawn
        n = int(count) if isinstance(count, (int, float)) else int(stats.get(u.name, u.level, count, default=0))
        if u.team == "def" and isinstance(count, str):
            n = int(stats.get(u.name, u.level, count.replace("On Offense", "On Defense"), default=n))
        sub_level = stats.max_level(name, 18) or 1
        if name == "Golemite":
            sub_level = u.level
        for k in range(n):
            ang = 2 * math.pi * k / max(1, n)
            battle.spawn(
                name,
                u.team,
                u.x + 0.7 * math.cos(ang),
                u.y + 0.7 * math.sin(ang),
                level=min(sub_level, stats.max_level(name, 18) or sub_level),
                kind="summon",
                group=u.group,
                owner=u,
            )
    special = sp.special
    if "death_bolts" in special:
        txt = stats.text(u.name, u.level, "Damage when destroyed") or "0 x0"
        per = stats.num(txt) or 0.0
        n = 6
        # Keep the same radial sampling approximation as Santa's Surprise.
        for k in range(n):
            angle = battle.rng.random() * 2 * math.pi
            # game data v18.200.9: ElectroDragonDie.RandomRadius=250 -> 2.5 tiles.
            offset = battle.rng.random() * 2.5
            x, y = u.x + offset * math.cos(angle), u.y + offset * math.sin(angle)
            # game data v18.200.9: ElectroDragonDie.Radius=200 -> 2 tiles.
            if u.team == "atk":
                battle.splash_buildings(x, y, 2.0, per, walls=False)
            battle.splash_units(
                x,
                y,
                2.0,
                per,
                False,
                True,
                team="def" if u.team == "atk" else "atk",
            )
    if "smasher" in special and u.team == "def":
        # Sore Loser: drops a defensive Rage Spell like the Spell Tower's (wiki)
        battle.fields.append(Field("def_rage", u.x, u.y, 5.0, t + 18.0, team="def", value=1.6, started=t))
    if "death_rage" in special:
        # Wiki: Super Valkyrie and Rage Spell/Home Village; level-four potency.
        # game data v18.200.9: EliteValkyrieRage.NumberOfHits=60 -> 60 pulses.
        # game data v18.200.9: EliteValkyrieRage.TimeBetweenHitsMS=300 -> 0.3 s.
        # The last pulse is 59 * 0.3 = 17.7 seconds after the first.
        battle.fields.append(
            Field(
                "rage",
                u.x,
                u.y,
                4.0,
                t + 18.0,
                team=u.team,
                value=2.6,
                extra={
                    "speed": 26 / 8.0,
                    "defense_damage": 1.6,
                    "pulses": 60,
                    "gap": 0.3,
                    # game data v18.200.9: EliteValkyrieRage.BoostTimeMS=1000 -> 1 s.
                    "boost_time": 1.0,
                },
                started=t,
            )
        )
    if "hog_split" in special and u.team == "atk":
        _split_hog(battle, u)
    if ("yetimites" in special or "electromites" in special) and u.extra.get("mites", 0) > 0:
        # Super Yeti's remaining-child release is inherited from Yeti, unconfirmed.
        mite = "Yetimite" if "yetimites" in special else "Electromite"
        for k in range(u.extra["mites"]):
            battle.spawn(
                mite,
                u.team,
                u.x + 0.4 * math.cos(k),
                u.y + 0.4 * math.sin(k),
                level=u.level,
                kind="summon",
                group=u.group,
                owner=u,
            )
        u.extra["mites"] = 0
    if u.name == "Druid" and not u.extra.get("sprung"):
        _transform_bear(battle, u)
    if "siege_cc" in special and u.team == "atk":
        release_cc(battle, u)


# Wiki: Clan Castle, deployment order within each housing class.
CARGO_ORDER = (
    "Barbarian",
    "Archer",
    "Goblin",
    "Wall Breaker",
    "Minion",
    "Sneaky Goblin",
    "Wizard",
    "Giant",
    "Balloon",
    "Hog Rider",
    "Super Barbarian",
    "Bowler",
    "Miner",
    "Headhunter",
    "Valkyrie",
    "Super Wall Breaker",
    "Rocket Balloon",
    "Baby Dragon",
    "Super Giant",
    "Super Wizard",
    "Witch",
    "Super Archer",
    "Super Minion",
    "Super Hog Rider",
    "Healer",
    "Ice Golem",
    "Inferno Dragon",
    "Druid",
    "Thrower",
    "Yeti",
    "Furnace",
    "Dragon",
    "Super Valkyrie",
    "Apprentice Warden",
    "Root Rider",
    "Super Miner",
    "P.E.K.K.A",
    "Dragon Rider",
    "Golem",
    "Lava Hound",
    "Electro Dragon",
    "Super Bowler",
    "Electro Titan",
    "Super Yeti",
    "Meteor Golem",
    "Super Witch",
    "Ice Hound",
    "Super Dragon",
)


def cargo_entries(battle, entries, levels=None):
    levels = levels or {}
    result = []
    for entry in entries:
        item = {"name": entry} if isinstance(entry, str) else dict(entry)
        name = item.get("name") or item["type"]
        level = (
            item.get("level")
            or levels.get(name)
            or stats.max_level(name, battle.town_hall)
        )
        for _ in range(int(item.get("count", 1))):
            result.append(
                {
                    "name": name,
                    "level": level,
                    "source": item.get("source", "clan_castle"),
                }
            )
    order = {name: index for index, name in enumerate(CARGO_ORDER)}
    result.sort(
        key=lambda item: (
            unit_numbers(item["name"], item["level"])["housing"],
            order.get(item["name"], len(order)),
            item["level"],
        )
    )
    return result


def onboard_cargo(battle):
    if not hasattr(battle, "_onboard_cargo"):
        battle._onboard_cargo = cargo_entries(
            battle,
            getattr(battle.plan, "cc_troops", []),
            getattr(battle.plan, "cc_levels", {}),
        )
    return battle._onboard_cargo


def spawn_cargo(battle, entry, x, y, group, *, siege):
    child = battle.spawn(
        entry["name"],
        "atk",
        x,
        y,
        level=entry["level"],
        kind="troop",
        group=group,
    )
    child.extra["deployment_source"] = "siege" if siege else entry["source"]
    # Wiki: Super Barbarian/Home Village excludes siege delivery from initial Rage.
    if siege and "start_rage" in child.spec.special:
        child.extra.get("rage_effects", {}).pop("innate", None)
    return child


def release_cc_at(battle, x, y, group="main", *, siege=False):
    if getattr(battle.plan, "_cc_released", False):
        return
    cargo = onboard_cargo(battle)
    entries = list(cargo)
    cargo.clear()
    battle.plan._cc_released = True
    # Exit timing and geometry are not stated; preserve the existing placement.
    for index, entry in enumerate(entries):
        angle = 2 * math.pi * index / max(1, len(entries))
        spawn_cargo(
            battle,
            entry,
            x + 0.6 * math.cos(angle),
            y + 0.6 * math.sin(angle),
            group,
            siege=siege,
        )


def release_cc(battle, u):
    release_cc_at(battle, u.x, u.y, u.group, siege=True)


def inherit_clone(battle, parent, child):
    if not parent.extra.get("clone"):
        return
    child.extra["clone"] = True
    child.extra["clone_casts"] = set(parent.extra.get("clone_casts", ()))
    # Wiki: Clone Spell says descendants are cloned; lifetime inheritance is unstated.
    # Preserve the parent's deadline rather than inventing a fresh lifetime.
    child.extra["expire_at"] = parent.extra["expire_at"]
    battle._clones.append(child)


def split_meteor(battle, u, target):
    # Wiki: Meteor Golem splits into two children after throwing.
    level = u.level
    small = u.hp < u.max_hp * 0.01
    positions = [(target.x, target.y)] if small else [(u.x, u.y), (target.x, target.y)]
    for x, y in positions:
        child = battle.spawn(
            "Meteormite",
            u.team,
            x,
            y,
            level=level,
            kind="summon",
            group=u.group,
            owner=u,
        )
        quantum = child.max_hp * 0.01
        child.hp = 1.0 if small else math.floor((u.hp / 2.0) / quantum) * quantum
        child.extra["meteor_components"] = (("permanent", level),)
    u.alive = False
    # Merge approach, timing and immunity duration are not stated.


def try_merge_meteor(battle, u):
    if u.team != "atk" or u.extra.get("clone") or not u.can_act(battle.t):
        return False
    if (
        u.target is not None
        and u.target.alive
        and target_distance(u, u.target) <= u.range
    ):
        return False
    for other in battle.attackers:
        if (
            other is u
            or not other.alive
            or other.name != "Meteormite"
            or other.extra.get("clone")
            or other.level != u.level
            or other.extra.get("meteor_components") != u.extra.get("meteor_components")
            or other.x != u.x
            or other.y != u.y
        ):
            continue
        if (
            other.target is not None
            and other.target.alive
            and target_distance(other, other.target) <= other.range
        ):
            continue
        # Wiki: Meteor Golem/Meteormite, same-type idle children may combine.
        # Only coincident, same-level pairs are resolved; approach timing and
        # mixed-level selection are not stated.
        parent = battle.spawn(
            "Meteor Golem", "atk", u.x, u.y, level=u.level, group=u.group
        )
        quantum = parent.max_hp * 0.005
        parent.hp = max(1.0, math.floor((u.hp + other.hp) / quantum) * quantum)
        parent.extra["meteor_components"] = u.extra.get(
            "meteor_components", ()
        ) + other.extra.get("meteor_components", ())
        u.alive = other.alive = False
        # Recombination immunity duration is not stated.
        return True
    return False


def launcher_target(battle, u):
    excluded = {"Spell Skeleton", "Bat", "Totem", "Furnace", "Firemite"}
    candidates = [
        ally
        for ally in battle.attackers
        if ally is not u
        and ally.alive
        and not ally.extra.get("suspended")
        and ally.name not in excluded
        and ally.kind not in ("siege", "siege_idle")
        and (ally.is_hero or ally.housing >= 2)
    ]
    # Wiki: Troop Launcher requires two housing. Grouping radius is not stated;
    # only independently qualifying recipients are resolved here.
    return max(
        candidates,
        key=lambda ally: (25 if ally.is_hero else ally.housing, -ally.id),
        default=None,
    )


def launch_barrel(battle, u, target):
    if u.extra["barrels"] <= 0:
        return
    x, y = target.x, target.y
    u.extra["barrels"] -= 1
    if u.name == "Sky Wagon":
        # Wiki: Sky Wagon, counts and troop levels depend on the machine level.
        for name, column in (
            ("Minion", "Minions"),
            ("Balloon", "Balloon"),
            ("Baby Dragon", "Baby Dragon"),
        ):
            count = int(stats.get(u.name, u.level, "Troops Spawned / " + column))
            level = int(stats.get(u.name, u.level, "Troop Levels / " + column))
            for _ in range(count):
                battle.spawn(
                    name,
                    u.team,
                    x,
                    y,
                    level=level,
                    kind="summon",
                    group=u.group,
                    owner=u,
                )
        battle.hit_building(target, stats.get(u.name, u.level, "Damage per Hit*"))
    else:
        # Wiki: Troop Launcher, per-level barrel contents and six-point healing.
        level = int(stats.get(u.name, u.level, "Troop Level"))
        for name, column in (
            ("Barbarian", "Barbarians"),
            ("Archer", "Archers"),
            ("Giant", "Giants"),
            ("Wall Breaker", "Wall Breakers"),
        ):
            count = int(stats.get(u.name, u.level, "Troops Spawned / " + column))
            for _ in range(count):
                battle.spawn(
                    name,
                    u.team,
                    x,
                    y,
                    level=level,
                    kind="summon",
                    group=u.group,
                    owner=u,
                )
        for ally in battle.attackers:
            if (
                ally.alive
                and not ally.flying
                and ally.name
                not in ("Furnace", "Firemite", "Totem", "Spell Skeleton", "Bat")
                and ally.kind not in ("siege", "siege_idle")
                and dist(x, y, ally.x, ally.y) <= 1.0
            ):
                ally.heal(6.0)
    cargo = onboard_cargo(battle)
    if cargo:
        # Wiki: Launcher and Wagon carry at most one CC troop per barrel.
        spawn_cargo(battle, cargo.pop(0), x, y, u.group, siege=True)
        if not cargo:
            battle.plan._cc_released = True
    # Flight, startup and final-barrel ordering are unstated; retain immediate landing.
    u.extra["next"] = battle.t + u.interval
    if u.extra["barrels"] == 0:
        battle.kill(u)


def tantrum(battle, u):
    if "tantrum" not in u.spec.special:
        return False
    # Wiki: Baby Dragon checks allied air troops within 4.5 tiles.
    allies = battle.attackers if u.team == "atk" else battle.defenders
    return not any(
        ally is not u
        and ally.alive
        and ally.flying
        and battle.t >= ally.active_at
        and not ally.extra.get("suspended")
        and dist(u.x, u.y, ally.x, ally.y) <= 4.5
        for ally in allies
    )


# ------------------------------------------------------------------ strikes
# Spatial changes are limited to the audited troops.
SPATIAL_TROOPS = {
    "Valkyrie",
    "Wizard",
    "Witch",
    "Electro Dragon",
    "Bowler",
    "Dragon",
    "Baby Dragon",
    "Balloon",
    "Wall Breaker",
    "Yetimite",
    "Firemite",
    "Meteor Golem",
    "Stone Slammer",
    "Phoenix",
    "Flame Flinger",
    "Giant Giant",
    "Super Archer",
    "Super Wizard",
    "Super Bowler",
    "Super Dragon",
    "Super Witch",
    "Super Valkyrie",
    "Rocket Balloon",
    "Witch Golem",
    "Super Wall Breaker",
    "Electromite",
}


def valkyrie_position(battle, u, target):
    if u.name != "Valkyrie" or not isinstance(target, Building):
        return None
    saved = u.extra.get("spin_position")
    if saved is not None:
        first, second, position = saved
        if first is target and second.alive and battle.building_targetable(second):
            return position
    candidates = []
    for other in battle.buildings:
        if other is target or not battle.building_targetable(other):
            continue
        # Wiki: Valkyrie moves between buildings without running past one.
        px = min(target.x + target.half_hit, max(target.x - target.half_hit, other.x))
        py = min(target.y + target.half_hit, max(target.y - target.half_hit, other.y))
        qx = min(other.x + other.half_hit, max(other.x - other.half_hit, px))
        qy = min(other.y + other.half_hit, max(other.y - other.half_hit, py))
        x, y = (px + qx) / 2.0, (py + qy) / 2.0
        if (
            target.edge_distance(x, y) > u.range
            or other.edge_distance(x, y) > u.spec.splash
        ):
            continue
        if battle.grid.blocked[battle.grid.cell(x, y)]:
            continue
        if any(
            building.alive and segment_entry(u.x, u.y, x, y, building) is not None
            for building in battle.buildings
        ):
            continue
        candidates.append((dist(u.x, u.y, x, y), other, (x, y)))
    if not candidates:
        u.extra.pop("spin_position", None)
        return None
    _, other, position = min(candidates, key=lambda item: item[0])
    u.extra["spin_position"] = (target, other, position)
    return position


def attack_ready(battle, u, target):
    if u.name not in ("Frostmite", "Firemite"):
        return True
    if u.extra.get("attack_target") is not target:
        u.extra["attack_target"] = target
        # game data v18.200.9: Icemite.NewTargetAttackDelay=500 -> 0.5 s.
        # game data v18.200.9: Firemite Spawn.NewTargetAttackDelay=500 -> 0.5 s.
        u.extra["attack_ready_at"] = battle.t + 0.5
    return battle.t >= u.extra["attack_ready_at"]


def effective_range(u):
    if "long_shot" in u.spec.special and u.extra.get("long_shots", 0) > 0:
        return 10.25  # Wiki: Super Minion.
    return u.range


def target_distance(u, target):
    """Measure from the attacker centre to a building edge or a unit centre."""
    if isinstance(target, Unit):
        return dist(u.x, u.y, target.x, target.y)
    return target.edge_distance(u.x, u.y)


def attack_interval(u, battle=None):
    if battle is not None and tantrum(battle, u):
        # Wiki: Baby Dragon gains 50% attack rate during Tantrum.
        return u.interval / 1.5
    if "burst" not in u.spec.special:
        return u.interval
    # Wiki: Super Dragon/Home Village gives ten shots, 0.192s and 1.8s.
    # Burst timing and displayed DPS conflict; do not rescale the shots.
    raw = stats.attrs(u.name)["raw"]
    u.extra["burst_left"] -= 1
    if u.extra["burst_left"] > 0:
        return stats.num(raw["Time Between Shots"])
    u.extra["burst_left"] = int(stats.num(raw["Shots per Burst"]))
    return stats.num(raw["Time Between Bursts"])


def _split_hog(battle, u):
    # Wiki: Super Hog Rider; both children retain the parent level.
    battle.spawn(
        "Super Hog",
        u.team,
        u.x,
        u.y,
        level=u.level,
        kind="summon",
        group=u.group,
        owner=u,
    )
    heading = u.extra.get("heading")
    target = u.target
    if heading is None and target is None:
        target, _ = battle.choose_target(u)
    if heading is None and target is not None:
        dx, dy = target.x - u.x, target.y - u.y
        length = math.hypot(dx, dy)
        if length:
            heading = (dx / length, dy / length)
    # Facing before any movement/targeting is not supplied by this engine.
    dx, dy = heading if heading is not None else (0.0, 0.0)
    # Wiki: Super Hog Rider/Super Rider; five tiles backward.
    # Launch travel time/landing delay: NUMBER NOT STATED; place immediately.
    battle.spawn(
        "Super Rider",
        u.team,
        u.x - 5.0 * dx,
        u.y - 5.0 * dy,
        level=u.level,
        kind="summon",
        group=u.group,
        owner=u,
    )


def _attack_targets(battle, u, walls=False):
    targets = []
    if u.team == "atk":
        targets.extend(b for b in battle.buildings if b.alive and b.counted)
        if walls:
            targets.extend(w for w in battle.walls.values() if w.alive)
    pool = battle.defenders if u.team == "atk" else battle.attackers
    for v in pool:
        if (
            v.alive
            and not v.extra.get("suspended")
            and battle.t >= v.active_at
            and battle.can_hit(u, v)
        ):
            if not (u.spec.splash_ground_only and v.flying):
                targets.append(v)
    return targets


def _frost(battle, target, factor, seconds):
    """The frost effect: slower attacks, and for troops slower movement too
    (wiki: Ice Hound/Ice Pup, "affected targets will have reduced movement
    and attack speed"). The strongest active frost wins."""
    t = battle.t
    target.atk_slow = min(target.atk_slow if t < target.atk_slow_until else 1.0, factor)
    target.atk_slow_until = max(target.atk_slow_until, t + seconds)
    if isinstance(target, Unit):
        target.move_slow = min(target.move_slow if t < target.move_slow_until else 1.0, factor)
        target.move_slow_until = max(target.move_slow_until, t + seconds)


def _chill(battle, u, target):
    if u.extra.get("bouncing_frostmite"):
        # game data v18.200.9: BouncingFrostmite.FrostOnHitPercent=30 -> 30% slow.
        # game data v18.200.9: BouncingFrostmite.FrostOnHitTime=3000 -> 3 s.
        _frost(battle, target, 0.7, 3.0)
        return
    if u.name in ("Frosty", "Frostmite"):
        # game data v18.200.9: Frosty.FrostOnHitPercent=50 -> 50% slow.
        # game data v18.200.9: Icemite.FrostOnHitPercent=50 -> 50% slow.
        # game data v18.200.9: Frosty.FrostOnHitTime=4000 -> 4 s.
        # game data v18.200.9: Icemite.FrostOnHitTime=4000 -> 4 s.
        _frost(battle, target, 0.5, 4.0)
        return
    if not any(tag in u.spec.special for tag in ("ice_chill", "chill")):
        return
    # game data v18.200.9: Ice Golem.FrostOnHitPercent=50 -> 50% slow.
    # game data v18.200.9: Ice Golem.FrostOnHitTime=2000 -> 2 s.
    # game data v18.200.9: Ice Hound.FrostOnHitPercent=50 -> 50% slow.
    # game data v18.200.9: Defensive Ice Hound.FrostOnHitPercent=50 -> 50% slow.
    # game data v18.200.9: Ice Hound.FrostOnHitTime=2000 -> 2 s.
    # game data v18.200.9: Ice Hound Pup.FrostOnHitPercent=50 -> 50% slow.
    # game data v18.200.9: Ice Hound Pup.FrostOnHitTime=2000 -> 2 s.
    _frost(battle, target, 0.5, 2.0)


def _hit_target(battle, u, target, damage):
    damage *= _mult_vs(u, target, battle)
    if isinstance(target, Unit):
        battle.hit_unit(target, damage, attacker=u)
        _after_unit_hit(battle, u, target, damage)
    else:
        u.damage_dealt += battle.hit_building(target, damage)
    if not isinstance(target, Wall):
        _chill(battle, u, target)


def _area_hit(battle, u, x, y, radius, damage, walls=False, primary=None):
    targets = _attack_targets(battle, u, walls=walls)
    if primary is not None and primary.alive and primary not in targets:
        targets.append(primary)
    for v in targets:
        distance = (
            dist(x, y, v.x, v.y) if isinstance(v, Unit) else v.edge_distance(x, y)
        )
        if distance <= radius:
            _hit_target(battle, u, v, damage)


def _dragon_footprint(target, x, y):
    # Wiki: Super Dragon/Home Village; a 5x5 square with four corners removed.
    # Its relation to "about one tile" is uncertain; use the stated 21 tiles.
    half = getattr(target, "half_hit", 0.0)
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            if abs(dx) == 2 and abs(dy) == 2:
                continue
            if (
                abs(target.x - x - dx) <= half + 0.5
                and abs(target.y - y - dy) <= half + 0.5
            ):
                return True
    return False


def _spatial_strike(battle, u, target, damage):
    sp = u.spec
    if u.name == "Stone Slammer":
        # Wiki: Stone Slammer, primary radius one and full secondary radius two.
        _area_hit(
            battle, u, target.x, target.y, 1.0, damage, walls=True, primary=target
        )
        # Secondary hitbox maximum/minimum by level. Levels 1-5 equal the
        # wiki's "100-200" ... "300-600"; level 6 settles its "350?-700?".
        # game data v18.200.9: Stone Slammer.Damage2=700 -> 700 within two tiles at level 6.
        # game data v18.200.9: Stone Slammer.Damage2Min=350 -> 350 at three tiles at level 6.
        # game data v18.200.9: Stone Slammer.Damage2FalloffStart=200 -> falloff from 2 tiles.
        # game data v18.200.9: Stone Slammer.Damage2FalloffEnd=300 -> to 3 tiles.
        pair = {1: (100, 200), 2: (150, 300), 3: (200, 400), 4: (250, 500), 5: (300, 600), 6: (350, 700)}.get(u.level)
        if pair is not None:
            minimum, maximum = pair
            boost = damage / stats.get(u.name, u.level, "Damage per Hit / Hitbox 1")
            for victim in _attack_targets(battle, u, walls=True):
                distance = target_distance(target, victim)
                if distance <= 3.0:
                    # Wiki: Stone Slammer, maximum through two tiles, minimum at three.
                    fraction = max(0.0, distance - 2.0)
                    amount = (maximum - (maximum - minimum) * fraction) * boost
                    if isinstance(victim, Wall):
                        amount *= 25.0  # Wiki: Stone Slammer, outer wall multiplier.
                    _hit_target(battle, u, victim, amount)
    elif u.name in ("Yetimite", "Firemite"):
        u.extra["leaping"] = True
        # Wiki: Yeti/Yetimite and Furnace/Firemite have one 0.8-radius impact.
        # Preparation and leap timings are not stated; retain immediate impact.
        _area_hit(
            battle, u, target.x, target.y, sp.splash, damage, walls=True, primary=target
        )
        u.extra["suicided"] = True
        battle.kill(u)
    elif u.name == "Flame Flinger":
        # Wiki: Flame Flinger fires three shots per burst.
        # Offsets, flight and flame geometry are not stated; impacts stay immediate.
        # The impact splash reaches walls (x8, specs.py); the flame field's
        # own wall bonus (wiki) belongs to the unmodelled field.
        for _ in range(3):
            _area_hit(battle, u, target.x, target.y, sp.splash, damage, walls=True, primary=target)
    elif sp.attack == "suicide":
        # Wiki: Super Wall Breaker; arrival applies normal and death damage.
        # The blast is centred on the target (no SelfAsAoeCenter, unlike the
        # Balloon's), the death damage on the breaker (on_death).
        _area_hit(battle, u, target.x, target.y, sp.splash, damage, walls=True, primary=target)
        if u.name == "Wall Breaker":
            # No death damage when a Wall Breaker reaches his wall: the wiki's
            # level-12 example gives 110 to a building (his Damage alone, not
            # 110 + 66). The game data's flag would allow it:
            # game data v18.200.9: Wall Breaker.DieDamage=6 -> death damage set; NoDieDamageForSuicide unset.
            u.extra["suicided"] = True
        battle.kill(u)
    elif sp.attack == "chain":
        _hit_target(battle, u, target, damage)
        hit = {target}
        current = target
        amount = damage
        for _ in range(sp.chain):
            # Wiki: Super Wizard/Home Village; every secondary is 40%.
            amount = (
                damage * sp.chain_decay
                if sp.chain_from_primary
                else amount * sp.chain_decay
            )
            origin = target if sp.chain_from_primary else current
            candidates = []
            for v in _attack_targets(battle, u):
                if v in hit:
                    continue
                distance = target_distance(origin, v)
                if distance <= sp.chain_range:
                    candidates.append((distance, -v.max_hp, v))
            if not candidates:
                break
            current = min(candidates, key=lambda item: item[:2])[2]
            hit.add(current)
            _hit_target(battle, u, current, amount)
    elif sp.attack == "bounce":
        # Wiki: Super Bowler; three impacts, three tiles apart, radius 0.6.
        dx, dy = target.x - u.x, target.y - u.y
        length = math.hypot(dx, dy) or 1.0
        for k in range(sp.bounces + 1):
            x = target.x + dx / length * sp.bounce_gap * k
            y = target.y + dy / length * sp.bounce_gap * k
            _area_hit(
                battle,
                u,
                x,
                y,
                sp.splash,
                damage,
                walls=True,
                primary=target if k == 0 else None,
            )
    elif sp.attack == "pierce":
        _hit_target(battle, u, target, damage)
        dx, dy = target.x - u.x, target.y - u.y
        length = math.hypot(dx, dy) or 1.0
        # game data v18.200.9: Super Archer.PenetratingRadius=30 -> 0.3 tiles either side.
        # Wiki: Walls/Home Village supports penetration through walls.
        for v in _attack_targets(battle, u, walls=True):
            if v is target:
                continue
            px, py = v.x - u.x, v.y - u.y
            along = (px * dx + py * dy) / length
            width = getattr(v, "half_hit", 0.0) + 0.3
            if 0 < along <= sp.pierce and abs(px * dy - py * dx) / length <= width:
                _hit_target(battle, u, v, damage)
    elif u.name == "Super Dragon":
        # Wiki: Walls/Home Village also allows Dragon wall collateral.
        for v in _attack_targets(battle, u, walls=True):
            if _dragon_footprint(v, target.x, target.y):
                _hit_target(battle, u, v, damage)
    elif sp.attack == "spin":
        # Wiki: Valkyrie spins around herself with radius one, including walls.
        # The Super Valkyrie has the same area flags:
        # game data v18.200.9: Super Valkyrie.SelfAsAoeCenter=TRUE -> centred on herself.
        # game data v18.200.9: Super Valkyrie.DamageRadius=100 -> 1 tile.
        _area_hit(
            battle, u, u.x, u.y, sp.splash, damage, walls=True, primary=target
        )
    else:
        # Rocket Balloon/Super Witch/Witch Golem attack radii: NUMBER NOT STATED.
        # Retain their existing radii; Rocket death radius is a separate value.
        _area_hit(
            battle,
            u,
            target.x,
            target.y,
            sp.splash,
            damage,
            walls=True,
            primary=target,
        )


def _mult_vs(u, target, battle=None):
    sp = u.spec
    m = 1.0
    if isinstance(target, Wall):
        return sp.vs_walls
    if isinstance(target, Building):
        if u.name in ("Spell Skeleton", "Bat") and target.key in (
            "gs",
            "es",
            "ds",
            "th",
        ):
            m *= 0.15  # Wiki: Skeleton Spell/Skeleton and Bat Spell/Bat.
        if u.name == "Frostmite" and (
            target.key in ("gs", "es", "ds")
            or target.key == "th"
            and battle is not None
            and battle.is_defense_target(target)
        ):
            m *= 0.5  # Wiki: Frosty/Frostmite, half storage damage.
        if target.kind == "resource" or target.key in RESOURCE_KEYS:
            m *= sp.vs_resources
        defensive = target.is_defense
        if battle is not None:
            defensive = battle.is_defense_target(target)
        if defensive:
            m *= sp.vs_defenses
        m *= sp.vs_buildings
    elif isinstance(target, Unit) and target.is_hero:
        m *= sp.vs_heroes
    return m


def projectile_speed(u):
    level = u.level
    if u.name == "Royal Champion":
        # game data v18.200.9: AmazonQueen_javelin.Speed=1200 -> 12 tiles/s.
        return 12.0
    if u.name == "Minion Prince":
        # game data v18.200.9: MinionHeroAttackProjectile.Speed=1000 -> 10 tiles/s.
        return 10.0
    if u.name == "Longshot":
        # game data v18.200.9: GuardianRangedProjectile.Speed=1500 -> 15 tiles/s.
        return 15.0
    if u.name == "Wizard" and 1 <= level <= 3:
        # game data v18.200.9: ps_chr_WizardAttack_Projectile.Speed=500 -> 5 tiles/s.
        return 5.0
    if u.name == "Thrower" and 1 <= level <= 4:
        # game data v18.200.9: ThrowerProjectile4.Speed=700 -> 7 tiles/s.
        return 7.0
    if u.name == "Minion" and 1 <= level <= 14:
        # game data v18.200.9: gargoyle_projectile.Speed=380 -> 3.8 tiles/s.
        return 3.8
    if u.name in ("Witch", "Super Witch") and 1 <= level <= 8:
        # game data v18.200.9: Witch_projectile.Speed=500 -> 5 tiles/s.
        return 5.0
    if u.name == "Lava Hound" and 1 <= level <= 8:
        # game data v18.200.9: hound_projectile.Speed=200 -> 2 tiles/s.
        return 2.0
    if u.name == "Lava Pup":
        # game data v18.200.9: tinyhound_projectile.Speed=300 -> 3 tiles/s.
        return 3.0
    if u.name == "Super Archer" and 5 <= level <= 14:
        # game data v18.200.9: magic_archer_projectile.Speed=1400 -> 14 tiles/s.
        return 14.0
    if u.name == "Super Dragon" and 3 <= level <= 12:
        # game data v18.200.9: SuperDragonProjectile.Speed=480 -> 4.8 tiles/s.
        return 4.8
    if u.name == "Super Minion":
        if u.extra.get("long_shots", 0) > 0:
            # game data v18.200.9: super_gargoyle_projectile_big.Speed=600 -> 6 tiles/s.
            return 6.0
        # game data v18.200.9: super_gargoyle_projectile.Speed=400 -> 4 tiles/s.
        return 4.0
    if u.name == "Ice Pup":
        # game data v18.200.9: icy_tinyhound_projectile.Speed=300 -> 3 tiles/s.
        return 3.0
    if u.name == "Super Bowler" and 1 <= level <= 10:
        # game data v18.200.9: SuperBowlerProjectile.Speed=475 -> 4.75 tiles/s.
        return 4.75
    if u.name == "Bowler" and 1 <= level <= 10:
        # game data v18.200.9: trollBoulder_lvl1.Speed=475 -> 4.75 tiles/s.
        return 4.75
    if u.name == "Frostmite":
        # game data v18.200.9: FrostmiteJump.Speed=400 -> 4 tiles/s.
        return 4.0
    if u.name == "Firemite":
        # game data v18.200.9: FireSpiritJump1.Speed=400 -> 4 tiles/s.
        return 4.0
    if u.name == "Lavaloon Pup" and 1 <= level <= 11:
        # game data v18.200.9: GW_Lavaloon Pup Projectile.Speed=300 -> 3 tiles/s.
        return 3.0
    return None


def launch_projectile(battle, u, target, damage, speed, *, rocket=False):
    sp = u.spec
    length = dist(u.x, u.y, target.x, target.y)
    dx = (target.x - u.x) / (length or 1.0)
    dy = (target.y - u.y) / (length or 1.0)
    mode = "single"
    track = target
    extra = {}
    if sp.attack == "pierce":
        mode, track = "pierce", None
        extra = {
            "origin": (u.x, u.y),
            "direction": (dx, dy),
            "speed": speed,
            "travel": 0.0,
            "hit": set(),
        }
    elif sp.attack == "bounce":
        # Retain the existing collinear impact geometry.
        for index in range(sp.bounces + 1):
            travel = length + index * sp.bounce_gap
            battle.add_pending(
                Pending(
                    battle.t + travel / speed,
                    target.x + dx * index * sp.bounce_gap,
                    target.y + dy * index * sp.bounce_gap,
                    sp.splash,
                    damage,
                    u.hits_air,
                    u.hits_ground,
                    "unit:" + u.name,
                    team="def" if u.team == "atk" else "atk",
                    extra={"troop_impact": "area"},
                    actor=u,
                )
            )
        return
    elif u.name in ("Firemite", "Frostmite"):
        mode = "leap"
        u.extra["leaping"] = True
    elif u.name == "Super Dragon":
        mode, track = "dragon", None
    elif sp.attack == "splash":
        # These fireballs land at the firing-time position.
        mode, track = "area", None
    if rocket:
        mode = "rocket"
    elif u.name == "Longshot":
        mode, track = "longshot", target
    extra["troop_impact"] = mode
    battle.add_pending(
        Pending(
            battle.t + (battle.DT if mode == "pierce" else length / speed),
            target.x,
            target.y,
            sp.splash,
            damage,
            u.hits_air,
            u.hits_ground,
            "unit:" + u.name,
            team="def" if u.team == "atk" else "atk",
            extra=extra,
            actor=u,
            target=track,
        )
    )


def projectile_impact(battle, pending):
    u = pending.actor
    mode = pending.extra["troop_impact"]
    x, y = pending.x, pending.y
    if pending.target is not None:
        x, y = pending.target.x, pending.target.y
    if mode == "pierce":
        ox, oy = pending.extra["origin"]
        dx, dy = pending.extra["direction"]
        previous = pending.extra["travel"]
        travel = min(
            u.spec.pierce,
            (battle.t - pending.released_at) * pending.extra["speed"],
        )
        for victim in _attack_targets(battle, u, walls=True):
            if victim in pending.extra["hit"]:
                continue
            px, py = victim.x - ox, victim.y - oy
            along = px * dx + py * dy
            half = getattr(victim, "half_hit", 0.0)
            # game data v18.200.9: Super Archer.PenetratingRadius=30 -> 0.3 tiles either side.
            if (
                along + half >= previous
                and along - half <= travel
                and 0 < along <= u.spec.pierce
                and abs(px * dy - py * dx) <= half + 0.3
            ):
                pending.extra["hit"].add(victim)
                _hit_target(battle, u, victim, pending.damage)
        if travel < u.spec.pierce:
            pending.extra["travel"] = travel
            pending.at = round(battle.t + battle.DT, 6)
            battle.add_pending(pending)
        return
    if mode == "rocket":
        from . import heroes

        # Empowered hit and splash (wiki: Rocket Spear says 0.8 tiles).
        # game data v18.200.9: RocketSpears.DamageRadius=90 -> 0.9 tiles.
        target = pending.target
        if target.alive and (
            not isinstance(target, Unit) or target.indirect_targetable(battle.t)
        ):
            heroes._damage(battle, target, pending.damage)
            heroes._blast(battle, x, y, 0.9, pending.damage, exclude=target)
        return
    if mode == "longshot":
        for victim in _attack_targets(battle, u):
            if (
                isinstance(victim, Unit)
                and victim.flying == pending.target.flying
                and dist(victim.x, victim.y, x, y) <= pending.radius
            ):
                _hit_target(battle, u, victim, pending.damage)
        return
    if mode == "single":
        target = pending.target
        if target.alive and (
            not isinstance(target, Unit) or target.indirect_targetable(battle.t)
        ):
            _hit_target(battle, u, target, pending.damage)
        return
    if mode == "dragon":
        for victim in _attack_targets(battle, u, walls=True):
            if _dragon_footprint(victim, x, y):
                _hit_target(battle, u, victim, pending.damage)
        return
    _area_hit(battle, u, x, y, pending.radius, pending.damage, walls=True)
    if mode == "leap":
        u.x, u.y = x, y
        u.extra["suicided"] = True
        battle.kill(u)


@effects.sourced("attack")
def strike(battle, u: Unit, target):
    t = battle.t
    sp = u.spec
    if sp.attack == "none" and not (u.name == "Ruin Witch" and u.team == "def"):
        return
    rage, _ = rage_boost(u, t)
    rage = max(rage, u.aura_dmg, u.extra.get("bell_damage", 1.0))
    mult = 1.0
    if "royal_rampage" in sp.special and u.team == "atk" and duke_alone(battle, u):
        mult *= 2.0  # +100% damage; cadence is applied separately (wiki: Dragon Duke).
    if tantrum(battle, u):
        # Wiki: Baby Dragon, best damage bonus competes with Rage.
        rage = max(rage, 2.0)
    dmg = u.dmg * mult
    if "burst" in sp.special and u.extra.get("burst_target") is not target:
        interrupt_attack(u)
        u.extra["burst_target"] = target
    if sp.attack == "beam":
        dmg = _beam(battle, u, target) * mult
    ordinary = dmg
    dmg *= rage
    rocket = u.kit is not None and u.kit.has("Rocket Spear") and u.kit.spear_shots > 0
    if u.kit is not None:
        from . import heroes

        if t < u.extra.get("vial_until", 0.0):
            # Compare fixed Vial and Rage bonuses (wiki: Rage Spell/Home Village).
            vial = u.extra["vial_bonus"] * battle.atk_hero_mult
            dmg = max(dmg, ordinary + vial)
        dmg = max(dmg, ordinary + heroes.strike_bonus(battle, u, target))
    speed = projectile_speed(u)
    if rocket:
        # game data v18.200.9: RocketSpearProjectile.Speed=1200 -> 12 tiles/s.
        launch_projectile(battle, u, target, dmg, 12.0, rocket=True)
        return
    if "long_shot" in sp.special and u.extra.get("long_shots", 0) > 0:
        u.extra["long_shots"] -= 1
    if speed is not None:
        launch_projectile(battle, u, target, dmg, speed)
        return
    # Every area attack type goes through the spatial code; the building-only
    # copies of these attacks that used to follow had drifted from it and
    # were unreachable.
    if u.name in SPATIAL_TROOPS or sp.attack in ("suicide", "spin", "chain", "bounce", "pierce"):
        _spatial_strike(battle, u, target, dmg)
        if u.name == "Valkyrie" and not target.alive:
            u.target = u.wall_target = None
        if u.name == "Meteor Golem":
            split_meteor(battle, u, target)
        if u.name == "Electromite":
            # Wiki: Super Yeti/Electromite dissipates after its discharge.
            # Preparation pause: NUMBER NOT STATED; keep immediate preparation.
            battle.kill(u)
        return
    dmg *= _mult_vs(u, target, battle)
    if u.kit is not None:
        # Percentage damage ignores Rage and difficulty (wiki: Monolith Arrow).
        dmg += heroes.monolith_bonus(battle, u, target)
    if u.kit is not None and t < u.extra.get("gauntlet_until", 0.0):
        _gauntlet_hit(battle, u, target, dmg)
        heroes.on_hit_extra(battle, u, target)
        return
    if isinstance(target, Unit):
        battle.hit_unit(target, dmg, attacker=u)
        _after_unit_hit(battle, u, target, dmg)
        _chill(battle, u, target)
        if u.kit is not None:
            heroes.on_hit_extra(battle, u, target)
        if u.name in ("Miner", "Super Miner") and u.team == "atk" and not target.alive:
            u.target = None
            update_burrow(battle, u, None)
        return
    team_def = u.team == "def"
    if team_def:
        return
    u.damage_dealt += dmg
    if sp.attack == "splash":
        battle.hit_building(target, dmg)
        if sp.splash > 0:
            for b in battle.buildings:
                if b is not target and b.alive and b.edge_distance(target.x, target.y) <= sp.splash:
                    battle.hit_building(b, dmg)
    else:
        battle.hit_building(target, dmg)
    if isinstance(target, Building):
        _chill(battle, u, target)
    if u.kit is not None:
        from . import heroes

        heroes.on_hit_extra(battle, u, target)


def _gauntlet_hit(battle, u, target, dmg):
    # Ground splash reaches buildings behind walls (wiki: Giant Gauntlet).
    radius = u.extra["gauntlet_radius"]
    if isinstance(target, Unit):
        battle.hit_unit(target, dmg, attacker=u)
    else:
        u.damage_dealt += dmg
        battle.hit_building(target, dmg)
    for b in list(battle.buildings) + list(battle.walls.values()):
        if (
            b is not target
            and b.alive
            and b.edge_distance(target.x, target.y) <= radius
        ):
            battle.hit_building(b, dmg)
    for f in battle.defenders_near(target.x, target.y, radius):
        if f is not target and not f.flying and not f.underground:
            battle.hit_unit(f, dmg, attacker=u)


@effects.sourced("secondary")
def _after_unit_hit(battle, u, target, dmg):
    t = battle.t
    sp = u.spec
    if "logger" in sp.special:
        # Wiki: Logger, post-hit travel depends on level; pushback is 1.5 tiles.
        travel = stats.get(u.name, u.level, "Post-Hit Tile Range")
        push = stats.num(stats.attrs(u.name)["raw"]["Pushback Range"])
        # Collider widths and projectile timing remain unstated.
        dx, dy = target.x - u.x, target.y - u.y
        d = math.hypot(dx, dy) or 1.0
        dx, dy = dx / d, dy / d
        for v in battle.attackers_near(target.x, target.y, travel + sp.splash):
            if v is target or not v.alive or v.underground:
                continue
            px, py = v.x - target.x, v.y - target.y
            along = px * dx + py * dy
            if 0 < along <= travel and abs(px * dy - py * dx) <= 0.8:
                battle.hit_unit(v, dmg, attacker=u)
        for v in battle.attackers_near(target.x, target.y, travel + sp.splash):
            px, py = v.x - target.x, v.y - target.y
            if (px * dx + py * dy) >= -1.5 and abs(px * dy - py * dx) <= 1.5 and v.name != "Totem" and v.kind not in ("siege", "siege_idle"):
                battle._nudge(v, dx * push, dy * push)
                v.target = v.wall_target = None
                reset_beam(v)
    # Frost is applied by the callers (strike, _hit_target) after this.
    if "hh_poison" in sp.special and not (
        target.kind == "guardian" and target.extra.get("waiting")
    ):
        # game data v18.200.9: HeadhunterPoison.PoisonOnHitDuration=3000 -> 3 s.
        duration = 3.0 if u.level <= 3 else 2.0
        slow = stats.get("Headhunter", u.level, "Speed Decrease", default=46.0) / 100.0
        atk = stats.get("Headhunter", u.level, "Attack Rate Decrease", default=68.0) / 100.0
        from . import spells

        _, slow, atk = spells.poison_factors(target, 0.0, slow, atk)
        target.move_slow, target.move_slow_until = 1.0 - slow, t + duration
        target.atk_slow, target.atk_slow_until = 1.0 - atk, t + duration
        # Poison damage, accumulation and the residual tail remain unresolved.
    if (
        u.name not in SPATIAL_TROOPS
        and sp.attack in ("splash", "spin")
        and sp.splash > 0
        and "logger" not in sp.special
    ):
        pool = battle.defenders_near(target.x, target.y, sp.splash) if u.team == "atk" else battle.attackers_near(target.x, target.y, sp.splash)
        for v in pool:
            if (
                v is not target
                and battle.can_hit(u, v)
                # Wiki: Longshot, splash affects the primary victim's height.
                and (u.name != "Longshot" or v.flying == target.flying)
            ):
                battle.hit_unit(v, dmg, attacker=u)


def interrupt_attack(u):
    reset_beam(u)
    if "burst" in u.spec.special:
        # Wiki: Super Dragon/Home Village, each uninterrupted burst has ten shots.
        u.extra["burst_left"] = int(
            stats.num(stats.attrs(u.name)["raw"]["Shots per Burst"])
        )
        u.extra.pop("burst_target", None)


def reset_beam(u):
    u.extra.pop("beam_target", None)
    u.extra.pop("beam_time", None)
    u.extra.pop("beam_tick", None)


def track_beam(battle, u, target):
    if u.spec.attack != "beam":
        return
    last = u.extra.get("beam_tick")
    if u.extra.get("beam_target") is not target or last is None:
        u.extra["beam_time"] = 0.0
    elif battle.t - last <= battle.DT + 1e-9:
        u.extra["beam_time"] += battle.t - last
    else:
        u.extra["beam_time"] = 0.0
    u.extra["beam_target"] = target
    u.extra["beam_tick"] = battle.t


def _beam(battle, u, target):
    """Count only uninterrupted time in attack range."""
    if u.extra.get("beam_target") is not target:
        track_beam(battle, u, target)
    held = u.extra.get("beam_time", 0.0)
    if u.name == "Super Miner":
        # Wiki: Super Miner/Home Village.
        stages = [
            (0.0, "Damage per Second / Initial"),
            (1.5, "Damage per Second / After 1.5s"),
            (3.0, "Damage per Second / After 3s"),
        ]
    else:
        # Wiki: Inferno Dragon/Home Village; upper duplicate rows stay unresolved.
        stages = [
            (0.0, "Damage per Second / Initial"),
            (1.7, "Damage per Second / After 1.7s"),
            (3.2, "Damage per Second / After 3.2s"),
        ]
    dps = u.dmg / u.interval
    for start, col in stages:
        if held >= start or math.isclose(held, start):
            value = stats.get(u.name, u.level, col)
            if value is not None:
                dps = value
    return dps * u.interval


# ----------------------------------------------------------------- healing
# Wiki: Healer and Druid share this table, including Unicorn healing.
HEAL_STACK = (1.0, 1.0, 0.9, 0.9, 0.7, 0.4, 0.1, 0.0)


def _heal_eligible(battle, healer, ally, *, primary=False):
    if (
        ally is healer
        or not ally.alive
        or ally.team != healer.team
        or battle.t < ally.active_at
        or ally.extra.get("suspended")
        or ally.name in ("Totem", "Furnace")
        or ally.kind in ("siege", "siege_idle")
    ):
        return False
    if ally.flying and not healer.spec.heal_air:
        return False
    if primary and (
        ally.name == "Unicorn" or ally.spec.attack in ("heal", "heal_chain")
    ):
        return False
    if healer.name == "Healer" and ally.spec.attack in ("heal", "heal_chain"):
        return False
    if healer.name == "Druid" and not primary and ally.name == "Druid":
        return False
    if healer.team == "def" and not (
        ally.kind in ("cc", "hero", "summon", "trap_skeleton", "guardian")
        or ally.name == "Skeleton"
    ):
        return False
    return True


def heal_effectiveness(battle, healer, recipient):
    sources = recipient.extra.setdefault("healing_sources", {})
    for source in list(sources):
        if (
            not source.alive
            or not source.can_act(battle.t)
            or source.extra.get("suspended")
            or (
                source.name != "Unicorn"
                and isinstance(source.target, Unit)
                and dist(source.x, source.y, source.target.x, source.target.y)
                > source.range
            )
            or recipient not in source.extra.get("healing_targets", ())
        ):
            sources.pop(source)
    sources.setdefault(healer, battle.t)
    ordered = sorted(sources, key=lambda source: (sources[source], source.id))
    index = ordered.index(healer)
    return HEAL_STACK[min(index, len(HEAL_STACK) - 1)]


def act_healer(battle, u: Unit):
    """Heal friendly recipients using the troop's pulse and recipient rules."""
    t = battle.t
    sp = u.spec
    u.extra["healing_targets"] = set()
    if u.team == "def" and any(
        state["u"] is u and t < state["until"] for state in battle._poison.values()
    ):
        return  # Wiki: Healer does not move or heal while defending in Poison.
    allies = battle.attackers if u.team == "atk" else battle.defenders
    eligible = [
        ally for ally in allies if _heal_eligible(battle, u, ally, primary=True)
    ]
    if u.name == "Healer":
        # Wiki: Healer ignores groups of at most two housing.
        # Use the stated healing area; no wider clustering radius is known.
        eligible = [
            target
            for target in eligible
            if sum(
                25 if ally.is_hero else ally.housing
                for ally in allies
                if _heal_eligible(battle, u, ally)
                and dist(target.x, target.y, ally.x, ally.y) <= sp.splash
            )
            > 2
        ]
    target = u.target if u.target in eligible else None
    if u.follow in eligible:
        target = u.follow
    if target is None:
        candidates = eligible
        if u.team == "def":
            candidates = [ally for ally in candidates if ally.hp < ally.max_hp]
        target = min(
            candidates, key=lambda ally: dist(u.x, u.y, ally.x, ally.y), default=None
        )
    u.target = target
    u.target_kind = "unit"
    if target is None:
        return
    if dist(u.x, u.y, target.x, target.y) > u.range:
        battle.move_towards(u, target)
        return
    if sp.attack == "heal":
        recipients = [
            ally
            for ally in allies
            if _heal_eligible(battle, u, ally)
            and dist(target.x, target.y, ally.x, ally.y) <= sp.splash
        ]
    else:
        recipients = [target]
        current = target
        for _ in range(sp.chain):
            # Wiki: Druid bounces at most three tiles, to four recipients total.
            # The projectile row allows longer bounces; whether that cap is
            # the heal chain's link distance is not stated, so 3 stays.
            # game data v18.200.9: BattleDruidProjectile.MaxBounceDistance=450 -> 4.5 tiles (role unresolved).
            candidates = [
                ally
                for ally in allies
                if ally not in recipients
                and _heal_eligible(battle, u, ally)
                and ally.hp < ally.max_hp
                and dist(current.x, current.y, ally.x, ally.y) <= 3.0
            ]
            current = min(
                candidates,
                key=lambda ally: dist(current.x, current.y, ally.x, ally.y),
                default=None,
            )
            if current is None:
                break
            recipients.append(current)
    u.extra["healing_targets"] = set(recipients)
    effectiveness = {ally: heal_effectiveness(battle, u, ally) for ally in recipients}
    due = u.extra.get("heal_next", t)
    if t < due and not math.isclose(t, due):
        return
    # Wiki: Healer pulses every 0.7 seconds; Druid heals every one second.
    # The existing initial pulse phase is retained.
    u.extra["heal_next"] = t + u.interval
    if u.name == "Healer":
        rate = stats.get(u.name, u.level, "Healing per Pulse")
        hero_rate = stats.get(u.name, u.level, "HPP on Heroes")
    else:
        rate = stats.get(u.name, u.level, "Healing per Hit")
        hero_rate = stats.get(u.name, u.level, "Hero Healing")
    rage, _ = rage_boost(u, t)
    # game data v18.200.9: HealerEnergy.Speed=1200 -> 12 tiles/s.
    # game data v18.200.9: BattleDruidProjectile.Speed=1200 -> 12 tiles/s.
    flight = dist(u.x, u.y, target.x, target.y) / 12.0
    previous = target
    for index, ally in enumerate(recipients):
        if u.name == "Druid" and index:
            flight += dist(previous.x, previous.y, ally.x, ally.y) / 12.0
        previous = ally
        amount = (
            (hero_rate if ally.is_hero else rate)
            * max(rage, u.aura_dmg)
            * effectiveness[ally]
        )
        battle.add_pending(
            Pending(
                t + flight,
                ally.x,
                ally.y,
                0.0,
                0.0,
                False,
                False,
                "unit:" + u.name,
                team=u.team,
                extra={"healing": amount},
                actor=u,
                effect="heal",
                target=ally,
            )
        )
