"""Where a base loses: traced battles for attack-aware search moves.

Runs a scenario set with light tracing and aggregates, weighted by how well
each attack went (stars + destruction), so the losing battles dominate:

- ``wall_heat``: village tiles of walls the attackers broke.
- ``ground`` / ``air``: attacker traffic per tile (sampled every 0.5 s).
- ``early``: per building (layout index), how early it fell (1 = at once,
  0 = never), i.e. which defenses the winning attacks strip first.

Used by ``optimize.guided_move``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .evaluate import STRENGTH, run_batch, skill
from .layout import Layout
from .mechanics import MARGIN, VILLAGE


def _trace_one(args):
    layout_json, sc, strength = args
    from .engine.battle import Battle
    from .meta_armies import make_plan

    layout = Layout.from_json(layout_json)
    plan = make_plan(sc.army, sc.angle, sc.town_hall, sc.seed)
    if sc.tactic is not None:
        from .tactics import apply

        apply(plan, sc.tactic)
    if sc.charge is not None:
        from .evaluate import apply_charge

        apply_charge(plan, sc.charge)
    plan.strength = strength * skill(sc.seed)
    b = Battle(layout, plan, seed=sc.seed, town_hall=layout.town_hall, modifier=sc.modifier)
    fell: dict = {}
    orig = b.destroy

    def destroy(obj):
        if obj.alive and isinstance(getattr(obj, "id", None), int):
            fell.setdefault(obj.id, b.t)
        return orig(obj)

    b.destroy = destroy
    ground, air = Counter(), Counter()
    cls = {c: Counter() for c in TRAFFIC}
    k = 0
    # the same loop and end rules as Battle.run, so the traced battle is the
    # battle evaluate() scores (it ends with Healers alone or lingers for
    # unspent Lightning / Earthquake exactly as run() does)
    validate = getattr(b.plan, "require_legal", None)
    if validate is not None:
        validate()
    while not b.ended and (b.scouting or b.t < b.max_time):
        b.step()
        k += 1
        if k % 5 == 0:
            for u in b.attackers:
                if u.alive:
                    t = (int(u.x - MARGIN), int(u.y - MARGIN))
                    if 0 <= t[0] < VILLAGE and 0 <= t[1] < VILLAGE:
                        (air if u.flying else ground)[t] += 1
                        if u.kind in ("pet", "siege_idle") or u.name == "Totem":
                            continue
                        if u.is_hero:
                            cls["hero_air" if u.flying else "hero_ground"][t] += 1
                        elif u.name == "Healer":
                            cls["healer"][t] += 1
                        else:
                            cls["air_mass" if u.flying else "ground_mass"][t] += getattr(u, "housing", 1) or 1
        if b.scouting:
            continue
        if b.destroyed_counted >= b.total_counted:
            break
        if b.offense_finished():
            break
    b.ended = True
    r = b.result()
    walls = [(x - MARGIN, y - MARGIN) for (x, y), w in b.walls.items() if not w.alive]
    return r.stars, r.destruction, b.t, fell, walls, dict(ground), dict(air), {c: dict(v) for c, v in cls.items()}


# attacker traffic classes, by what a trap can punish (sampled every 0.5 s;
# the mass classes count housing space, so a tile crossed by a Valkyrie pack
# outweighs one crossed by a lone Archer)
TRAFFIC = ("hero_ground", "hero_air", "healer", "ground_mass", "air_mass")

# which traffic a trap is proposed onto (a search heuristic only: every
# placement is still judged by simulated battles)
TRAP_TRAFFIC = {
    "giant": {"ground_mass": 1.0, "hero_ground": 0.5},
    "bomb": {"ground_mass": 1.0},
    "spring": {"ground_mass": 1.0},
    "airbomb": {"air_mass": 1.0, "healer": 1.0},
    "seeking": {"healer": 1.0, "hero_air": 1.0, "air_mass": 0.3},
    "tornado": {"hero_ground": 1.0, "ground_mass": 0.5},
    "skeleton:ground": {"hero_ground": 1.0, "ground_mass": 0.3},
    "skeleton:air": {"healer": 1.0, "hero_air": 1.0, "air_mass": 0.3},
}


@dataclass
class Diagnosis:
    wall_heat: Counter = field(default_factory=Counter)
    ground: Counter = field(default_factory=Counter)
    air: Counter = field(default_factory=Counter)
    early: dict = field(default_factory=dict)
    battles: int = 0
    traffic: dict = field(default_factory=lambda: {c: Counter() for c in TRAFFIC})

    def trap_tiles(self, key: str, mode: str | None = None, n: int = 60):
        """Hot tiles for one trap type, from the traffic it punishes."""
        mix = TRAP_TRAFFIC.get(f"{key}:{mode}") or TRAP_TRAFFIC.get(key)
        if not mix:
            return self.hot_tiles("air" if key in ("airbomb", "seeking") else "ground", n)
        c: Counter = Counter()
        for cl, w in mix.items():
            tot = sum(self.traffic[cl].values()) or 1.0
            for t, v in self.traffic[cl].items():
                c[t] += w * v / tot
        return c.most_common(n)

    def hot_tiles(self, kind: str, n: int = 80):
        c = {"ground": self.ground, "air": self.air, "wall": self.wall_heat}[kind]
        return c.most_common(n)


def diagnose(layout: Layout, scenarios, *, strength=None, parallel=True) -> Diagnosis:
    strength = strength or STRENGTH
    lj = layout.to_json()
    jobs = [(lj, sc, strength.get(sc.army, 1.0)) for sc in scenarios]
    if parallel and len(jobs) >= 4:
        from .evaluate import pool

        res = list(pool().map(_trace_one, jobs, chunksize=1))
    else:
        res = [_trace_one(j) for j in jobs]
    d = Diagnosis(battles=len(res))
    early: Counter = Counter()
    wsum = 0.0
    for sc, (stars, pct, t_end, fell, walls, ground, air, cls) in zip(scenarios, res):
        w = sc.weight * (stars + pct / 100.0) ** 2  # successful attacks dominate
        wsum += w
        for t in walls:
            d.wall_heat[t] += w
        for t, n in ground.items():
            d.ground[t] += w * n
        for t, n in air.items():
            d.air[t] += w * n
        for cl, cnt in cls.items():
            for t, n in cnt.items():
                d.traffic[cl][t] += w * n
        for i, tf in fell.items():
            early[i] += w * (1.0 - tf / max(1.0, t_end))
    if wsum > 0:
        d.early = {i: v / wsum for i, v in early.items()}
    return d


__all__ = ["Diagnosis", "diagnose", "run_batch"]
