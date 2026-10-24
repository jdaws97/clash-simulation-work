"""Adaptive attacker: search an army's tactics against one base.

The army (troops, spells, heroes, loadouts) stays fixed; the tactics are a
vector of knobs applied to its AttackPlan:

  angle            attack side (radians, circular)
  funnel_scale     width of the hero funnel (multiplies the funnel laterals)
  funnel_shift     funnel moved left/right along the edge
  flank_lat        where the flank troops land
  spread           how tight the main wave is dropped (multiplies spread)
  support_spread   how tight the Healers/support land
  main_min         earliest main drop after the funnel starts (s)
  main_gap         latest main drop = main_min + gap (s)
  heroes_push      > 0.5: one funnel hero joins the push instead
  freeze_pick      which defense the Freezes go on first
  revive_delay     Revive timing after a hero falls (s)

Search: cross-entropy method (CEM). Each round samples `pop` tactic vectors
from a Gaussian (the side is uniform in round one), plays each against `k`
attacker-skill seeds (the same seeds for every vector, so they are compared
fairly), keeps the best 25% and refits the Gaussian to them. The best vector
is then re-scored on fresh seeds, so the reported rate is not the lucky
search draw.
"""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .evaluate import attacker_trophies, pool, skill
from .layout import Layout

FREEZE_OPTIONS = (
    (),
    ("inferno",),
    ("mono",),
    ("scatter",),
    ("eagle",),
    ("xbow",),
    ("inferno", "mono"),
    ("scatter", "inferno"),
)
KNOBS = [
    ("angle", 0.0, 2 * math.pi),
    ("funnel_scale", 0.4, 1.8),
    ("funnel_shift", -4.0, 4.0),
    ("flank_lat", -8.0, 8.0),
    ("spread", 0.4, 1.6),
    ("support_spread", 0.3, 2.0),
    ("main_min", 3.0, 14.0),
    ("main_gap", 2.0, 14.0),
    ("heroes_push", 0.0, 1.0),
    ("freeze_pick", 0.0, len(FREEZE_OPTIONS) - 1e-6),
    ("revive_delay", 0.5, 4.0),
    (
        "charge_pick",
        0.0,
        5.0 - 1e-6,
    ),  # 0 none, 1 Queen, 2 Royal Champion, 3 Dragon Duke, 4 Barbarian King
    ("charge_healers", 0.0, 5.99),
    ("charge_lat", -10.0, 10.0),
    ("charge_at", 0.0, 8.0),
    ("charge_recall_hp", 0.15, 0.7),
    ("charge_len", 8.0, 40.0),
    (
        "recall_funnel",
        0.0,
        1.0,
    ),  # > 0.5: Recall the charge and send it up the opposite flank
    (
        "split_main",
        0.0,
        1.4,
    ),  # > 0.05: main wave lands on two flanks this far apart (radians)
]
CHARGE_OPTIONS = (
    None,
    "Archer Queen",
    "Royal Champion",
    "Dragon Duke",
    "Barbarian King",
)
NAMES = [k[0] for k in KNOBS]
PLAYBOOK_KNOBS = {
    "angle",
    "funnel_scale",
    "spread",
    "support_spread",
    "freeze_pick",
    "revive_delay",
}
LO = np.array([k[1] for k in KNOBS])
HI = np.array([k[2] for k in KNOBS])
DEFAULT = np.array(
    [
        0.0,
        1.0,
        0.0,
        0.0,
        1.0,
        1.0,
        8.0,
        10.0,
        0.0,
        0.0,
        1.5,
        0.0,
        0.0,
        0.0,
        0.0,
        0.35,
        25.0,
        0.0,
        0.0,
    ]
)


def describe(vec) -> dict:
    d = dict(zip(NAMES, [round(float(v), 2) for v in vec]))
    d["angle_deg"] = round(math.degrees(vec[0]) % 360)
    d["freeze_first"] = list(FREEZE_OPTIONS[int(vec[9])])
    d["heroes_push"] = bool(vec[8] > 0.5)
    if len(vec) > 11:
        d["charge"] = CHARGE_OPTIONS[int(vec[11])]
    return d


def apply(plan, vec):
    from .engine.plans import Wave
    from .engine.playbook import PlaybookPlan

    v = dict(zip(NAMES, vec))
    plan.angle = float(v["angle"]) % (2 * math.pi)
    if isinstance(plan, PlaybookPlan):
        # output/rustfirst/c-bughunt.out #8: generic waves/charges are not read
        # by the step executor. Only tune fields the fitted steps actually use.
        unsupported = [
            name
            for i, name in enumerate(NAMES)
            if name in v and name not in PLAYBOOK_KNOBS and v[name] != DEFAULT[i]
        ]
        if unsupported:
            raise ValueError(
                "Playbook does not execute generic tactic knobs: "
                + ", ".join(unsupported)
            )
        plan.flank_offset *= float(v["funnel_scale"])
        plan.freeze_first = FREEZE_OPTIONS[int(v["freeze_pick"])]
        plan.revive_delay = float(v["revive_delay"])
        for step in plan.steps:
            if step["action"] != "deploy" or step.get("what") in plan.loadouts:
                continue
            name = "support_spread" if step.get("what") == "Healer" else "spread"
            scale = float(v[name])
            if scale != DEFAULT[NAMES.index(name)]:
                step["spread"] = max(0.1, step.get("spread", 1.0) * scale)
        return plan
    plan.funnel_heroes = [
        (n, lat * v["funnel_scale"] + v["funnel_shift"])
        for n, lat in plan.funnel_heroes
    ]
    if v["heroes_push"] > 0.5 and len(plan.funnel_heroes) > 1:
        # the first funnel hero walks in with the push instead
        name, _ = plan.funnel_heroes[0]
        plan.funnel_heroes = plan.funnel_heroes[1:]
        plan.push_heroes = [name] + list(plan.push_heroes)
    plan.flank = [(n, c, float(v["flank_lat"])) for n, c, _lat in plan.flank]
    plan.main = [
        Wave(w.group, w.units, spread=max(0.5, w.spread * v["spread"]))
        for w in plan.main
    ]
    plan.support = [
        Wave(w.group, w.units, spread=float(v["support_spread"])) for w in plan.support
    ]
    plan.main_min = float(v["main_min"])
    plan.main_max = float(v["main_min"] + v["main_gap"])
    plan.freeze_first = FREEZE_OPTIONS[int(v["freeze_pick"])]
    plan.revive_delay = float(v["revive_delay"])
    hero = CHARGE_OPTIONS[int(v.get("charge_pick", 0.0))]
    if hero:
        plan.setup_charge(
            hero,
            int(v["charge_healers"]),
            float(v["charge_lat"]),
            float(v["charge_at"]),
        )
        plan.charge_recall_hp = float(v.get("charge_recall_hp", 0.35))
        plan.charge_len = float(v.get("charge_len", 25.0))
        plan.recall_funnel = bool(v.get("recall_funnel", 0.0) > 0.5)
    plan.split_main = float(v.get("split_main", 0.0))
    return plan


def _run(args):
    lj, army, th, vec, seed, strength, modifier, user = args
    from .engine.battle import Battle
    from .meta_armies import make_plan

    plan = make_plan(army, 0.0, th, seed)
    if user:
        root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(root / "tools" / "baselab"))
        from recommend_armies import account, personalise

        plan = personalise(plan, account(th))
    apply(plan, vec)
    plan.strength = strength * skill(seed)
    lay = Layout.from_json(lj)
    # the defending Town Hall sets TH stats and the TH18 Guardian (bug until 2026-10-15: the attacker TH was passed)
    r = Battle(lay, plan, seed=seed, town_hall=lay.town_hall, modifier=modifier).run()
    return r.stars, r.destruction


def fitness(stars, pct):
    """Stars first, destruction as the tie-break (0..4)."""
    return stars + pct / 100.0


@dataclass
class AttackResult:
    vec: np.ndarray
    search_fit: float
    three_star: float
    avg_stars: float
    avg_pct: float
    trophies: float
    n: int

    def summary(self):
        return f"3* {self.three_star:5.1%} | avg {self.avg_stars:.2f}* {self.avg_pct:5.1f}% | att trophies {self.trophies:4.1f} (n={self.n})"


def play(layout, army, th, vecs, seeds, *, modifier=None, user=False, strength=None):
    lj = layout.to_json()
    # Army discovery compares raw game stats. Calibration is an explicit input;
    # inherited family fits must not change which inventory wins the search.
    st = (strength if strength is not None else {}).get(army, 1.0)
    jobs = [
        (lj, army, th, tuple(map(float, v)), s, st, modifier, user)
        for v in vecs
        for s in seeds
    ]
    res = list(pool().map(_run, jobs, chunksize=1))
    k = len(seeds)
    return [res[i * k : (i + 1) * k] for i in range(len(vecs))]


def score(layout, army, th, vec, seeds, **kw) -> AttackResult:
    rows = play(layout, army, th, [vec], seeds, **kw)[0]
    n = len(rows)
    return AttackResult(
        np.array(vec),
        0.0,
        sum(s >= 3 for s, _ in rows) / n,
        sum(s for s, _ in rows) / n,
        sum(p for _, p in rows) / n,
        sum(attacker_trophies(s, p) for s, p in rows) / n,
        n,
    )


def optimize(
    layout,
    army,
    th,
    *,
    iters=6,
    pop=24,
    k=6,
    elite=0.25,
    seed=0,
    modifier=None,
    user=False,
    final_seeds=12,
    select_seeds=8,
    log=None,
    strength=None,
) -> AttackResult:
    """CEM over the knobs, made robust against lucky draws (checked
    2026-10-15: with 3 fixed seeds two search runs disagreed by 30 points
    and Hydra came out worse than the scripted plan):
    - each round plays `k` skill seeds, fresh every round;
    - every round's top 3 and the scripted plan at 8 sides stay candidates;
    - the pick is made on `select_seeds` new seeds, so the tuned attacker is
      never worse than a scouting player with the scripted plan;
    - the reported rate uses another `final_seeds` fresh seeds."""
    rng = np.random.default_rng(seed)
    from .engine.playbook import PlaybookPlan
    from .meta_armies import make_plan

    scripted = isinstance(make_plan(army, 0.0, th, 0), PlaybookPlan)
    inactive = [
        i for i, name in enumerate(NAMES) if scripted and name not in PLAYBOOK_KNOBS
    ]
    mu, sd = DEFAULT.copy(), (HI - LO) / 4
    pool_v = []
    for i in range(8):
        v = DEFAULT.copy()
        v[0] = 2 * math.pi * i / 8 + 0.1
        pool_v.append(v)
    best_f = -1.0
    for it in range(iters):
        seeds = [1000 + seed * 997 + it * k + i for i in range(k)]
        V = mu + sd * rng.standard_normal((pop, len(KNOBS)))
        if it == 0:
            V[:, 0] = rng.uniform(0, 2 * math.pi, pop)
            V[0] = DEFAULT
            V[0, 0] = rng.uniform(0, 2 * math.pi)
        V[:, 0] %= 2 * math.pi
        V[:, 1:] = np.clip(V[:, 1:], LO[1:], HI[1:])
        V[:, inactive] = DEFAULT[inactive]
        rows = play(
            layout, army, th, V, seeds, modifier=modifier, user=user, strength=strength
        )
        F = np.array([np.mean([fitness(s, p) for s, p in r]) for r in rows])
        order = np.argsort(-F)
        n_el = max(2, int(pop * elite))
        E = V[order[:n_el]]
        best_f = max(best_f, float(F[order[0]]))
        pool_v += [V[i].copy() for i in order[:3]]
        # circular mean for the side
        a = math.atan2(np.sin(E[:, 0]).mean(), np.cos(E[:, 0]).mean()) % (2 * math.pi)
        spread_a = math.sqrt(
            max(
                1e-6,
                -2
                * math.log(
                    max(
                        1e-9, math.hypot(np.sin(E[:, 0]).mean(), np.cos(E[:, 0]).mean())
                    )
                ),
            )
        )
        mu = np.concatenate([[a], E[:, 1:].mean(0)])
        sd = np.concatenate(
            [
                [max(0.08, spread_a)],
                np.maximum(E[:, 1:].std(0), (HI[1:] - LO[1:]) * 0.03),
            ]
        )
        if log:
            log(
                f"    {army} it {it}: best {F[order[0]]:.2f} mean-elite {F[order[:n_el]].mean():.2f}  side {math.degrees(a):.0f}deg"
            )
    sel = [3000 + seed * 101 + i for i in range(select_seeds)]
    rows = play(
        layout, army, th, pool_v, sel, modifier=modifier, user=user, strength=strength
    )
    Fs = [np.mean([fitness(s, p) for s, p in r]) for r in rows]
    best_v = pool_v[int(np.argmax(Fs))]
    final = score(
        layout,
        army,
        th,
        best_v,
        [5000 + seed * 100 + i for i in range(max(1, final_seeds))],
        modifier=modifier,
        user=user,
        strength=strength,
    )
    final.search_fit = best_f
    return final


def baseline(
    layout, army, th, *, n_sides=8, seeds=(0, 1, 2), modifier=None, user=False
) -> AttackResult:
    """The scripted plan at evenly spaced sides, for comparison."""
    vecs = []
    for i in range(n_sides):
        v = DEFAULT.copy()
        v[0] = 2 * math.pi * i / n_sides + 0.1
        vecs.append(v)
    rows = [
        r
        for rr in play(
            layout,
            army,
            th,
            vecs,
            [5000 + s for s in seeds],
            modifier=modifier,
            user=user,
        )
        for r in rr
    ]
    n = len(rows)
    return AttackResult(
        DEFAULT,
        0.0,
        sum(s >= 3 for s, _ in rows) / n,
        sum(s for s, _ in rows) / n,
        sum(p for _, p in rows) / n,
        sum(attacker_trophies(s, p) for s, p in rows) / n,
        n,
    )
