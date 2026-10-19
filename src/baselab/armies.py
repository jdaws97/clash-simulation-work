"""Attack plans: army compositions plus a phased attacker brain.

A plan works like a competent ranked attacker:

1. **Funnel** - heroes and flank troops go in on both sides of the chosen
   approach angle to clear the edge buildings that would drag the main army
   sideways.
2. **Main push** - once the funnel has done its work (or a time limit
   passes), the main army is deployed at the entry point whose nearest target
   leads deepest towards the core. Ground armies first roll a Log Launcher
   lane through the walls on that line.
3. **Support and spells** - healers/Warden follow the push; spells are cast
   reactively (freeze the scariest defense, totems into defense clusters,
   overgrowth on the core, rage when engaged, revive dead heroes).
4. **Cleanup** - leftover troops go to the far side.

Armies mirror what actually hits TH16-18 bases in ranked (docs/RESEARCH-2026-10.md).
Base search runs each army from several approach angles and keeps the best
results, like an attacker who scouts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .mechanics import SPELLS, WORLD
from .loadouts import HeroLoadout as L
from .sim import Battle, Deployment, Effect

CENTER = WORLD / 2.0

THREAT = {
    # rough worth of disabling each defense (freeze / overgrowth targeting)
    "inferno": 10,
    "scatter": 8,
    "eagle": 7,
    "th": 6,
    "xbow": 5,
    "mono": 5,
    "ad": 4,
    "ric": 4,
    "mat": 3,
    "wt": 3,
    "st": 3,
    "bt": 2,
    "at": 2,
    "tesla": 2,
    "cannon": 1,
    "bh": 1,
    "mortar": 1,
    "sweeper": 1,
}

HOUSING_CAP = {16: 320, 17: 340, 18: 352}


def edge_point(battle: Battle, angle: float, lateral: float = 0.0):
    """Closest legal deploy point walking in from `angle`, shifted sideways
    by `lateral` tiles."""
    dx, dy = math.cos(angle), math.sin(angle)
    px, py = -dy, dx
    last = None
    r = WORLD
    while r > 0:
        x = CENTER + px * lateral + dx * r
        y = CENTER + py * lateral + dy * r
        if 0.5 <= x < WORLD - 0.5 and 0.5 <= y < WORLD - 0.5:
            if battle.can_deploy(x, y):
                last = (x, y)
            elif last is not None:
                break
        r -= 0.5
    if last is None:
        last = (min(WORLD - 1.0, max(1.0, CENTER + dx * 24)), min(WORLD - 1.0, max(1.0, CENTER + dy * 24)))
    return last


def _cheb(x, y):
    return max(abs(x - CENTER), abs(y - CENTER))


@dataclass
class Wave:
    group: str
    units: list  # (name, count)
    spread: float = 2.5
    gap: float = 0.15


@dataclass
class AttackPlan:
    angle: float = 0.0
    town_hall: int = 18
    seed: int = 0
    label: str = "attack"
    funnel_heroes: list = field(default_factory=list)  # (name, lateral)
    flank: list = field(default_factory=list)  # (name, count, lateral)
    main: list = field(default_factory=list)  # list[Wave]
    support: list = field(default_factory=list)  # list[Wave], 2 s after main
    push_heroes: list = field(default_factory=list)  # deployed with main
    cleanup: list = field(default_factory=list)  # (name, count)
    spells: dict = field(default_factory=dict)
    ground: bool = True
    log_launcher: bool = False
    breaches: int = 0  # wall-access micro: Wall Breakers / spare logs / Jump / EQ
    zap_ad: tuple = (0, 0)  # (lightnings, quakes) opening on an air defense
    main_min: float = 8.0
    main_max: float = 22.0
    strength: float = 1.0
    loadouts: dict = field(default_factory=dict)
    _cast_log: list = field(default_factory=list)
    _next_brain: float = 0.0
    _phase: str = "funnel"
    _entry: tuple | None = None
    _main_at: float = 0.0
    _funnel_units: list = field(default_factory=list)

    # --------------------------------------------------------- deploying
    def deployments(self, battle: Battle):
        out = []
        th = self.town_hall
        for name, lateral in self.funnel_heroes:
            x, y = edge_point(battle, self.angle, lateral)
            out.append(Deployment(0.0, name, x, y, group="funnel", town_hall=th))
        t = 0.5
        for name, count, lateral in self.flank:
            for k in range(count):
                x, y = edge_point(battle, self.angle, lateral + (k - count / 2) * 0.6)
                out.append(Deployment(t, name, x, y, group="funnel", town_hall=th))
                t += 0.15
        return out

    def has_pending(self) -> bool:
        return self._phase != "done"

    def _drop(self, battle, name, x, y, group, jitter=0.0):
        if jitter:
            x += battle.rng.uniform(-jitter, jitter)
            y += battle.rng.uniform(-jitter, jitter)
        return battle.deploy(Deployment(battle.t, name, x, y, group=group, town_hall=self.town_hall))

    def _best_entry(self, battle):
        """Entry point (near the approach angle) whose nearest building
        leads deepest into the base."""
        best = None
        for lat in range(-5, 6):
            x, y = edge_point(battle, self.angle, float(lat))
            nearest = None
            nd = 1e9
            for b in battle.buildings:
                if not b.alive or not b.counted:
                    continue
                d = b.edge_distance(x, y)
                if d < nd:
                    nd = d
                    nearest = b
            if nearest is None:
                continue
            score = _cheb(nearest.x, nearest.y) + 0.15 * nd + 0.3 * abs(lat)
            if best is None or score < best[0]:
                best = (score, x, y)
        return (best[1], best[2]) if best else edge_point(battle, self.angle, 0.0)

    def _funnel_progress(self, battle):
        """Counted buildings destroyed near the entry corridor so far."""
        ex, ey = edge_point(battle, self.angle, 0.0)
        return sum(1 for b in battle.buildings if not b.alive and b.counted and math.hypot(b.x - ex, b.y - ey) < 10)

    def _launch_main(self, battle):
        self._entry = self._best_entry(battle)
        ex, ey = self._entry
        if self.log_launcher:
            self._roll_logs(battle, ex, ey)
        for wave in self.main:
            names = [n for n, c in wave.units for _ in range(c)]
            for i, name in enumerate(names):
                self._drop(battle, name, ex, ey, "main", jitter=wave.spread)
        for name in self.push_heroes:
            self._drop(battle, name, ex, ey, "main", jitter=0.5)
        self._main_at = battle.t
        self._phase = "support"

    def _roll_logs(self, battle, ex, ey):
        """Log Launcher: clears walls in a 2-tile lane from the entry towards
        the Town Hall and damages buildings it rolls over (assumed numbers)."""
        tx, ty = (battle.th.x, battle.th.y) if battle.th is not None else (CENTER, CENTER)
        dx, dy = tx - ex, ty - ey
        d = math.hypot(dx, dy) or 1.0
        dx, dy = dx / d, dy / d
        # Logs break after hitting four buildings (wiki), so high-HP buildings
        # near the edge stop the lane early.
        hit = set()
        for step in range(0, 40):
            px = ex + dx * step * 0.5
            py = ey + dy * step * 0.5
            for key, w in list(battle.walls.items()):
                if w.alive and abs(w.x - px) < 1.1 and abs(w.y - py) < 1.1:
                    battle.damage_building(w, 1e9)
            for b in battle.buildings:
                if b.alive and b.counted and b.id not in hit and b.edge_distance(px, py) < 1.0:
                    hit.add(b.id)
                    battle.damage_building(b, 900.0)
            if len(hit) >= 4:
                break

    def on_tick(self, battle: Battle):
        t = battle.t
        if self._phase == "funnel":
            if not self._zapped_done():
                self._zap(battle)
            ready = t >= self.main_max or (t >= self.main_min and self._funnel_progress(battle) >= 3)
            if ready:
                self._launch_main(battle)
        elif self._phase == "support" and t >= self._main_at + 2.0:
            ex, ey = self._entry
            for wave in self.support:
                for name, c in wave.units:
                    for _ in range(c):
                        self._drop(battle, name, ex, ey, "main", jitter=wave.spread)
            self._phase = "push"
        elif self._phase == "push" and t >= self._main_at + 35.0:
            if self.cleanup:
                ex, ey = edge_point(battle, self.angle + math.pi / 2, 0.0)
                for name, c in self.cleanup:
                    for _ in range(c):
                        self._drop(battle, name, ex, ey, "cleanup", jitter=2.0)
            self._phase = "done"
        if t >= self._next_brain:
            self._next_brain = t + 0.5
            if self._phase in ("support", "push", "done"):
                self.generic_spells(battle, self.main_units(battle))

    # ------------------------------------------------------------- spells
    _zap_done: bool = False

    def _zapped_done(self):
        return self._zap_done or self.zap_ad == (0, 0)

    def _zap(self, battle):
        self._zap_done = True
        lightnings, quakes = self.zap_ad
        ex, ey = edge_point(battle, self.angle, 0.0)
        ads = [b for b in battle.buildings if b.alive and b.key == "ad"]
        if not ads:
            return
        target = min(ads, key=lambda b: math.hypot(b.x - ex, b.y - ey))
        for _ in range(quakes):
            if self._have("eq"):
                self._use(battle, "eq", target.x, target.y)
        for _ in range(lightnings):
            if self._have("lightning") and target.alive:
                self._use(battle, "lightning", target.x, target.y)

    def _have(self, kind):
        return self.spells.get(kind, 0) > 0

    def _use(self, battle, kind, x, y):
        self.spells[kind] -= 1
        s = SPELLS[min(18, self.town_hall)][kind]
        t = battle.t
        if kind == "rage":
            battle.add_effect(Effect("rage", x, y, s["radius"], t + s["duration"], value=s["damage"], extra={"speed": s["speed"]}))
        elif kind == "heal":
            battle.add_effect(Effect("heal", x, y, s["radius"], t + s["duration"], value=s["hps"], extra={"hero_hps": s["hero_hps"]}))
        elif kind == "freeze":
            battle.add_effect(Effect("freeze", x, y, s["radius"], t + s["duration"]))
        elif kind == "invis":
            battle.add_effect(Effect("invis", x, y, s["radius"], t + s["duration"]))
        elif kind == "overgrowth":
            battle.add_effect(Effect("overgrowth", x, y, s["radius"], t + s["duration"]))
        elif kind == "haste":
            battle.add_effect(Effect("haste", x, y, s["radius"], t + s["duration"], value=s["speed"]))
        elif kind == "iceblock":
            battle.add_effect(Effect("iceblock", x, y, s["radius"], t + s["duration"], value=s["reduction"]))
        elif kind == "poison":
            battle.add_effect(Effect("poison", x, y, s["radius"], t + s["duration"], value=s["dps"], extra={"slow": s["slow"]}))
        elif kind == "lightning":
            for b in battle.buildings:
                if b.alive and b.edge_distance(x, y) <= s["radius"]:
                    battle.damage_building(b, s["damage"])
        elif kind == "eq":
            for b in battle.buildings:
                if b.alive and b.counted and b.edge_distance(x, y) <= s["radius"]:
                    battle.damage_building(b, b.max_hp * s["pct"])
        elif kind == "totem":
            battle.spawn_totem(x, y, s["hp"], s["decay"], s["radius"])
        self._cast_log.append((round(t, 1), kind))

    def _last(self, kind):
        for t, k in reversed(self._cast_log):
            if k == kind:
                return t
        return -100.0

    def main_units(self, battle, group="main"):
        return [u for u in battle.attackers if u.alive and u.group == group and u.name != "Totem"]

    def centroid(self, units):
        w = sum(max(1, u.housing) for u in units)
        x = sum(u.x * max(1, u.housing) for u in units) / w
        y = sum(u.y * max(1, u.housing) for u in units) / w
        return x, y

    def threats_near(self, battle, x, y, r):
        out = []
        t = battle.t
        for b in battle.buildings:
            if not b.alive or b.weapon is None:
                continue
            if t < b.frozen_until or t < b.overgrown_until:
                continue
            d = math.hypot(b.x - x, b.y - y)
            if d <= r:
                out.append((b, d))
        return out

    def _breach(self, battle, units):
        """Open walls where several main-push troops are stuck on them,
        standing in for the Wall Breakers / Jump / Earthquakes players use."""
        stuck = [u for u in units if u.wall_target is not None and u.wall_target.alive]
        if len(stuck) < 2:
            return
        for u in stuck:
            w = u.wall_target
            near = sum(1 for v in stuck if abs(v.wall_target.x - w.x) + abs(v.wall_target.y - w.y) <= 3)
            if near >= 2:
                for (tx, ty), wall in battle.walls.items():
                    if wall.alive and abs(wall.x - w.x) <= 1.6 and abs(wall.y - w.y) <= 1.6:
                        battle.damage_building(wall, 1e9)
                self.breaches -= 1
                self._cast_log.append((round(battle.t, 1), "breach"))
                return

    def generic_spells(self, battle, units):
        if not units:
            return
        t = battle.t
        if self.breaches > 0 and t - self._last("breach") > 3:
            self._breach(battle, units)
        cx, cy = self.centroid(units)
        avg_hp = sum(u.hp / u.max_hp for u in units) / len(units)
        engaged = sum(1 for u in units if u.target is not None and u.cooldown > 0)
        if self._have("freeze"):
            for b, d in sorted(self.threats_near(battle, cx, cy, 12), key=lambda bd: -THREAT.get(bd[0].key, 1)):
                if THREAT.get(b.key, 0) >= 5 and d <= b.weapon.range + 1.5 and b.weapon.target is not None:
                    self._use(battle, "freeze", b.x, b.y)
                    break
        if self._have("totem") and t - self._last("totem") > 5:
            hot = self.threats_near(battle, cx, cy, 10)
            if len(hot) >= 3:
                fx = sum(b.x for b, _ in hot) / len(hot)
                fy = sum(b.y for b, _ in hot) / len(hot)
                self._use(battle, "totem", cx + (fx - cx) * 0.5, cy + (fy - cy) * 0.5)
        if self._have("overgrowth"):
            best = None
            for b, d in self.threats_near(battle, cx, cy, 13):
                if THREAT.get(b.key, 0) < 4:
                    continue
                score = sum(THREAT.get(o.key, 1) for o, _ in self.threats_near(battle, b.x, b.y, 6))
                if best is None or score > best[0]:
                    best = (score, b)
            if best is not None and best[0] >= 18:
                self._use(battle, "overgrowth", best[1].x, best[1].y)
        if self._have("rage") and engaged >= max(2, len(units) // 2) and t - self._last("rage") > 9:
            self._use(battle, "rage", cx, cy)
        if self.ground and self._have("heal") and avg_hp < 0.6 and t - self._last("heal") > 6:
            self._use(battle, "heal", cx, cy)
        if self._have("invis") and avg_hp < 0.55 and t - self._last("invis") > 4:
            self._use(battle, "invis", cx, cy)
        if self._have("poison"):
            foes = [d for d in battle.defenders if d.alive and d.spawned_at <= t and math.hypot(d.x - cx, d.y - cy) < 7]
            if len(foes) >= 3:
                self._use(battle, "poison", sum(f.x for f in foes) / len(foes), sum(f.y for f in foes) / len(foes))


# ==========================================================================
# Armies. Housing: TH16 320, TH17 340, TH18 352; 11 spells + 3 CC spells.
# CC troops are folded into the main army; CC spells into the spell pool.
# ==========================================================================


def hydra(angle=0.0, town_hall=18, seed=0) -> AttackPlan:
    th = town_hall
    dragons, riders, rockets = {18: (8, 5, 6), 17: (8, 5, 4), 16: (8, 4, 5)}[th]
    return AttackPlan(
        angle=angle,
        town_hall=th,
        seed=seed,
        label="Hydra (Dragons + Dragon Riders)",
        funnel_heroes=[("Dragon Duke", -6.0), ("Archer Queen", 7.0)],
        flank=[("Rocket Balloon", rockets, -4.0)],
        main=[Wave("main", [("Dragon", dragons + 2), ("Dragon Rider", riders)], spread=3.0)],
        push_heroes=["Grand Warden", "Minion Prince"],
        cleanup=[("Minion", 4)],
        spells={"totem": 4, "freeze": 3, "rage": 1, "eq": 1, "poison": 1, "overgrowth": 1, "revive": 1},
        ground=False,
        loadouts={
            "Dragon Duke": L("Dragon Duke", ("Rocket Backpack", "Fire Heart"), "Phoenix"),
            "Archer Queen": L("Archer Queen", ("Giant Arrow", "Action Figure"), "Unicorn"),
            "Grand Warden": L("Grand Warden", ("Eternal Tome", "Rage Gem"), "Electro Owl"),
            "Minion Prince": L("Minion Prince", ("Dark Orb", "Meteor Staff"), "Angry Jelly"),
        },
        main_min=10.0,
        main_max=20.0,
    )


def throwers(angle=0.0, town_hall=18, seed=0) -> AttackPlan:
    th = town_hall
    n = {18: 13, 17: 12, 16: 11}[th]
    healers = {18: 10, 17: 9, 16: 8}[th]
    return AttackPlan(
        angle=angle,
        town_hall=th,
        seed=seed,
        label="Mass Throwers + Healers",
        funnel_heroes=[("Barbarian King", -6.0), ("Royal Champion", 6.0)],
        flank=[],
        main=[Wave("main", [("Ice Golem", 1), ("Giant", 2), ("Thrower", n)], spread=2.0)],
        support=[Wave("main", [("Healer", healers)], spread=1.0)],
        push_heroes=["Archer Queen", "Grand Warden"],
        cleanup=[("Archer", 4)],
        spells={"totem": 4, "rage": 1, "overgrowth": 1, "poison": 1, "freeze": 2, "invis": 1, "revive": 2},
        ground=True,
        log_launcher=True,
        breaches=3,
        loadouts={
            "Barbarian King": L("Barbarian King", ("Spiky Ball", "Earthquake Boots"), "Spirit Fox"),
            "Royal Champion": L("Royal Champion", ("Rocket Spear", "Electro Boots"), "Phoenix"),
            "Archer Queen": L("Archer Queen", ("Giant Arrow", "Healer Puppet"), "Unicorn"),
            "Grand Warden": L("Grand Warden", ("Eternal Tome", "Rage Gem"), "Electro Owl"),
        },
        main_min=8.0,
        main_max=18.0,
    )


def edrag(angle=0.0, town_hall=18, seed=0) -> AttackPlan:
    th = town_hall
    n = {18: 11, 17: 10, 16: 9}[th]
    return AttackPlan(
        angle=angle,
        town_hall=th,
        seed=seed,
        label="Electro Dragon spam",
        funnel_heroes=[("Dragon Duke", -6.0), ("Archer Queen", 6.0)],
        main=[Wave("main", [("Electro Dragon", n + 1), ("Balloon", 3)], spread=6.0, gap=0.3)],
        push_heroes=["Grand Warden", "Minion Prince"],
        spells={"lightning": 3, "eq": 1, "rage": 3, "freeze": 2, "totem": 3, "revive": 0},
        ground=False,
        zap_ad=(3, 1),
        loadouts={
            "Dragon Duke": L("Dragon Duke", ("Rocket Backpack", "Fire Heart"), "Phoenix"),
            "Archer Queen": L("Archer Queen", ("Giant Arrow", "Action Figure"), "Unicorn"),
            "Grand Warden": L("Grand Warden", ("Eternal Tome", "Life Gem"), "Electro Owl"),
            "Minion Prince": L("Minion Prince", ("Dark Orb", "Meteor Staff"), "Angry Jelly"),
        },
        main_min=5.0,
        main_max=12.0,
    )


def root_riders(angle=0.0, town_hall=18, seed=0) -> AttackPlan:
    th = town_hall
    rr = {18: 6, 17: 5, 16: 4}[th]
    return AttackPlan(
        angle=angle,
        town_hall=th,
        seed=seed,
        label="Root Riders + Valkyries",
        funnel_heroes=[("Royal Champion", -6.0), ("Barbarian King", 6.0)],
        flank=[("Rocket Balloon", 4, -4.0)],
        main=[Wave("main", [("Ice Golem", 2), ("Root Rider", rr + 1), ("Valkyrie", 8)], spread=2.0)],
        support=[Wave("main", [("Healer", 5), ("Apprentice Warden", 1)], spread=1.0)],
        push_heroes=["Archer Queen", "Grand Warden"],
        cleanup=[("Minion", 6)],
        spells={"invis": 3, "overgrowth": 1, "freeze": 2, "poison": 1, "rage": 2, "totem": 2, "revive": 1},
        ground=True,
        log_launcher=True,
        breaches=2,
        loadouts={
            "Royal Champion": L("Royal Champion", ("Rocket Spear", "Electro Boots"), "Phoenix"),
            "Barbarian King": L("Barbarian King", ("Spiky Ball", "Earthquake Boots"), "Spirit Fox"),
            "Archer Queen": L("Archer Queen", ("Giant Arrow", "Healer Puppet"), "Unicorn"),
            "Grand Warden": L("Grand Warden", ("Eternal Tome", "Life Gem"), "Diggy"),
        },
        main_min=8.0,
        main_max=18.0,
    )


ARMIES = {"hydra": hydra, "throwers": throwers, "edrag": edrag, "rootrider": root_riders}

# Share of TH18 same-TH ranked attacks (TrophyCoach, 2026-10-15) for the
# armies we model; renormalised when used as weights.
META_WEIGHTS = {"hydra": 0.271, "throwers": 0.260, "edrag": 0.115, "rootrider": 0.097}
