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
    k = 0
    while b.t < b.max_time:
        b.step()
        k += 1
        if k % 5 == 0:
            for u in b.attackers:
                if u.alive:
                    t = (int(u.x - MARGIN), int(u.y - MARGIN))
                    if 0 <= t[0] < VILLAGE and 0 <= t[1] < VILLAGE:
                        (air if u.flying else ground)[t] += 1
        if b.destroyed_counted >= b.total_counted:
            break
        if b._next_deploy >= len(b.deployments) and not b.plan.has_pending():
            if not any(u.alive and u.name != "Totem" and u.kind != "siege_idle" for u in b.attackers) and not b.pending:
                break
    r = b.result()
    walls = [(x - MARGIN, y - MARGIN) for (x, y), w in b.walls.items() if not w.alive]
    return r.stars, r.destruction, b.t, fell, walls, dict(ground), dict(air)


@dataclass
class Diagnosis:
    wall_heat: Counter = field(default_factory=Counter)
    ground: Counter = field(default_factory=Counter)
    air: Counter = field(default_factory=Counter)
    early: dict = field(default_factory=dict)
    battles: int = 0

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
    for sc, (stars, pct, t_end, fell, walls, ground, air) in zip(scenarios, res):
        w = sc.weight * (stars + pct / 100.0) ** 2  # successful attacks dominate
        wsum += w
        for t in walls:
            d.wall_heat[t] += w
        for t, n in ground.items():
            d.ground[t] += w * n
        for t, n in air.items():
            d.air[t] += w * n
        for i, tf in fell.items():
            early[i] += w * (1.0 - tf / max(1.0, t_end))
    if wsum > 0:
        d.early = {i: v / wsum for i, v in early.items()}
    return d


__all__ = ["Diagnosis", "diagnose", "run_batch"]
