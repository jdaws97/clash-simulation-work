"""Run many battles in parallel and turn them into base scores.

Scoring follows the real ranked rules (docs/RESEARCH-2026-10.md): the defender
earns ``40 - attacker_trophies``. For war the score is the probability of
*not* conceding three stars, with stars and destruction as tie-breakers.
"""

from __future__ import annotations

import math
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace

from .layout import Layout

# Per-army strength multipliers on attacking unit HP and DPS, fitted so that
# simulated same-TH 3-star rates on typical generated bases match TrophyCoach's
# real ranked rates (see tools/baselab/calibrate.py). 1.0 = raw game stats.
def _load_strength():
    import json
    from pathlib import Path

    f = Path(__file__).resolve().parents[2] / "data" / "baselab-calibration.json"
    base = {"hydra": 1.0, "throwers": 1.0, "edrag": 1.0, "rootrider": 1.0}
    try:
        base.update({k: v["strength"] for k, v in json.loads(f.read_text()).items()})
    except (OSError, ValueError, KeyError):
        pass
    # real meta builds (tools/baselab/calibrate_meta.py), keyed "meta:<build id>"
    try:
        m = Path(os.environ.get("BASELAB_CALIBRATION") or Path(__file__).resolve().parents[2] / "data" / "meta-calibration.json")
        base.update({"meta:" + k: v["strength"] for k, v in json.loads(m.read_text()).items()})
    except (OSError, ValueError, KeyError):
        pass
    # new strategies (data/custom-armies.json) borrow their family's calibration
    try:
        c = Path(__file__).resolve().parents[2] / "data" / "custom-armies.json"
        for b in json.loads(c.read_text(encoding="utf-8"))["builds"]:
            fam = [v for k, v in base.items() if k.startswith(f"meta:{b.get('family')}-16-")]
            base["custom:" + b["archetype"]] = sum(fam) / len(fam) if fam else 1.0
    except (OSError, ValueError, KeyError):
        pass
    return base


STRENGTH = _load_strength()


def attacker_trophies(stars: int, pct: float) -> int:
    """Trophies an attacker takes in ranked (Fandom 'Ranked Battles')."""
    if stars >= 3:
        return 40
    if stars == 2:
        return 16 + max(0, int((pct - 50) // 3))
    if stars == 1:
        return 5 + int(pct // 9)
    return min(4, int(pct // 10))


def defender_trophies(stars: int, pct: float) -> int:
    if stars == 0:
        return 40
    return 40 - attacker_trophies(stars, pct)


@dataclass(frozen=True)
class Scenario:
    army: str
    town_hall: int
    angle: float
    seed: int = 0
    weight: float = 1.0
    modifier: str | None = None  # ranked league modifier: legend3/legend2/legend1
    group: int = 0  # scenarios of one army/TH/group differ only by approach angle
    tactic: tuple | None = None  # adaptive-attacker knobs (tactics.py); sets the side too
    charge: tuple | None = None  # (hero, healers): the build is played as a hero charge (Invisibility + Recall)


# Hero charges a player can run with a build, as (hero, Healers sent with
# it). Royal Champion and flying heroes charge without Healers (the user:
# "2 healers in a RC charge won't do anything"; Healers can't heal flyers).
# A Queen charge takes 4 Healers (Queen Charge guides).
CHARGE_HEALERS = {"Royal Champion": 0, "Archer Queen": 4, "Dragon Duke": 0}


def techniques(build: dict) -> list:
    """The plays a player picks from after scouting: the scripted plan, plus a
    hero charge with each charge hero the build brings.

    A build played from its cited playbook (BASELAB_PLAYBOOKS=1) has only its
    own plan: PlaybookPlan.setup_charge is a no-op (the playbook carries its
    cited charges), so a charge scenario would replay the same battle."""
    from .meta_armies import _playbook, family_of, playbooks_on

    out = [None]
    if playbooks_on() and (fam := family_of(build)) and _playbook(fam) is not None:
        return out
    for hero, healers in CHARGE_HEALERS.items():
        if hero in build.get("heroes", []):
            out.append((hero, min(healers, int(build.get("troops", {}).get("Healer", 0)))))
    return out


def apply_charge(plan, charge):
    hero, healers = charge
    if plan.setup_charge(hero, healers, 0.0, 0.0):
        plan.charge_recall_hp = 0.35
        plan.charge_len = 25.0
    return plan


# Real attackers scout and pick a side. Modelled as: the attacker looks at
# SCOUT random approach angles and attacks from the one that pays best.
# SCOUT = 2 reproduces the user's real ranked defenses (13 logged attacks:
# about 5 trophies and 77% three-starred; simulated 4.1 and 72%), where
# 1 gave 10.0 / 46% and 3 gave 1.6 / 86%.
SCOUT = 2


# Attacker skill varies between real players. Each scenario seed maps to one
# of five fixed skill quantiles (normal z-scores), scaling the army strength
# by exp(SKILL_SPREAD * z). This turns the sharp win/lose threshold of a
# single deterministic battle into a smooth probability.
SKILL_SPREAD = 0.15
_Z = (-1.28, -0.52, 0.0, 0.52, 1.28)


def skill(seed: int) -> float:
    return math.exp(SKILL_SPREAD * _Z[seed % len(_Z)])


# Skill belongs to the attacker, not to the side: every side one scouting
# group compares is played at the same quantile, so "best of SCOUT sides"
# picks the best side, not the luckier attacker. (Before 2026-10-20 the seed
# was s * 7 + k, so the 8 sides of one group ran at mixed quantiles and the
# scout partly picked the stronger attacker.) The quantile now varies between
# groups. The battle seed is 5 * m + q with m = s * n_sides + k (distinct per
# side and seed; m % 2 still alternates the playbook charge flank with the
# side) and q the group's quantile, so seed % 5 is still the skill.
SKILL_ORDER = (1, 3, 2, 0, 4)  # 2 or 3 consecutive entries average to the median
_Z_VAR = sum(z * z for z in _Z) / len(_Z)


def group_seed(j: int, s: int, k: int, n: int) -> int:
    """Seed of side k (of n) in group j (equal-weight groups, e.g. one build
    against several bases): the quantile cycles through SKILL_ORDER."""
    return 5 * (s * n + k) + SKILL_ORDER[j % len(SKILL_ORDER)]


def _skill_patterns(n: int) -> list:
    """Quantile multisets for the n groups of one army: symmetric around the
    median (mean z 0) when n >= 2, any single quantile when n == 1."""
    import itertools

    q = len(_Z)
    if n == 1:
        return [(i,) for i in range(q)]
    return [p for p in itertools.combinations_with_replacement(range(q), n)
            if all(p.count(i) == p.count(q - 1 - i) for i in range(q // 2))]


def _assign_skill(scenarios):
    """Scenario seeds come in as m = s * n_sides + k; each scouting group
    (army, Town Hall, modifier, group) gets one quantile q and every seed
    becomes 5 * m + q. The groups of one army take a set of quantiles
    symmetric around the median, so no army is played systematically weak
    or strong; armies are placed heaviest first on the set that keeps the
    weighted quantile shares closest to 1/5 each, with the weighted mean and
    variance of z closest to those of the five quantiles. Ties rotate with
    the seed."""
    armies: dict = {}
    for sc in scenarios:
        g = armies.setdefault((sc.army, sc.town_hall, sc.modifier), {})
        g.setdefault(sc.group, [0.0, sc.seed])[0] += sc.weight
    tot = sum(w for g in armies.values() for w, _m in g.values()) or 1.0
    fill = [0.0] * len(_Z)
    q_of = {}
    for key in sorted(armies, key=lambda a: (-sum(w for w, _m in armies[a].values()), str(a))):
        gs = sorted(armies[key])
        ws = [armies[key][g][0] / tot for g in gs]

        def cost(p):
            f = list(fill)
            for q, w in zip(p, ws):
                f[q] += w
            mean = sum(x * z for x, z in zip(f, _Z))
            spread = sum(x * (z * z - _Z_VAR) for x, z in zip(f, _Z))
            return round(sum((x - 1 / len(_Z)) ** 2 for x in f) + mean ** 2 + spread ** 2, 12)

        pats = _skill_patterns(len(gs))
        r = armies[key][gs[0]][1] % len(pats)
        pats = pats[r:] + pats[:r]
        p = min(pats, key=cost)
        for g, q, w in zip(gs, p, ws):
            fill[q] += w
            q_of[key + (g,)] = q
    return [replace(sc, seed=5 * sc.seed + q_of[(sc.army, sc.town_hall, sc.modifier, sc.group)]) for sc in scenarios]


def _run_one(args):
    from .engine.battle import Battle
    from .meta_armies import make_plan

    layout_json, sc, strength = args
    layout = Layout.from_json(layout_json)
    plan = make_plan(sc.army, sc.angle, sc.town_hall, sc.seed)
    if sc.tactic is not None:
        from .tactics import apply

        apply(plan, sc.tactic)
    if sc.charge is not None:
        apply_charge(plan, sc.charge)
    plan.strength = strength * skill(sc.seed)
    r = Battle(layout, plan, seed=sc.seed, town_hall=layout.town_hall, modifier=sc.modifier).run()
    return (r.stars, r.destruction, r.th_destroyed, r.time)


_POOL = None


def pool():
    global _POOL
    if _POOL is None:
        # BASELAB_WORKERS caps the pool when several jobs share the machine
        n = int(os.environ.get("BASELAB_WORKERS") or max(1, (os.cpu_count() or 2) - 1))
        _POOL = ProcessPoolExecutor(max_workers=n)
    return _POOL


def run_batch(jobs, *, parallel=True):
    """jobs: list of (layout_json, Scenario, strength). Returns result tuples."""
    if not parallel or len(jobs) < 4:
        return [_run_one(j) for j in jobs]
    return list(pool().map(_run_one, jobs, chunksize=max(1, len(jobs) // (4 * (os.cpu_count() or 2)))))


def angles(n: int, offset: float = 0.0):
    return [offset + 2 * math.pi * k / n for k in range(n)]


def ranked_scenarios(n_angles=8, seeds=(0,), mix=None, angle_offset=0.0):
    """TH17/TH18 attackers, weighted by the real ranked meta."""
    mix = mix or {
        ("hydra", 18): 0.27,
        ("throwers", 18): 0.26,
        ("edrag", 18): 0.115,
        ("rootrider", 18): 0.10,
        ("hydra", 17): 0.12,
        ("throwers", 17): 0.06,
        ("edrag", 17): 0.07,
        ("rootrider", 17): 0.05,
    }
    out = []
    for (army, th), w in mix.items():
        for k, a in enumerate(angles(n_angles, offset=0.37 * th + 0.11 * len(army) + angle_offset)):
            for s in seeds:
                out.append(Scenario(army, th, a, s * n_angles + k, w / (n_angles * len(seeds)), group=s))
    return _assign_skill(out)


def target_scenarios(town_hall: int, n_angles=8, seeds=(0,), modifier=None):
    """Same-TH attackers against a TH17/TH18 base, weighted by the TH18
    ranked meta shares (TrophyCoach); used to build strong attack targets."""
    mix = {"hydra": 0.271, "throwers": 0.260, "edrag": 0.115, "rootrider": 0.097}
    tot = sum(mix.values())
    out = []
    for army, w in mix.items():
        for k, a in enumerate(angles(n_angles, offset=0.23 * len(army) + 0.1 * town_hall)):
            for s in seeds:
                out.append(Scenario(army, town_hall, a, s * n_angles + k, w / tot / (n_angles * len(seeds)), modifier, group=s))
    return _assign_skill(out)


def meta_scenarios(mode="ranked", n_angles=8, seeds=(0,), modifier=None, th_mix=None, techniques_on=False, angle_offset=0.0):
    """Scenarios from the real meta builds (meta_armies.py). Ranked: TH18 and
    TH17 attackers (65/35 by default); war: TH16. Within a Town Hall each build
    is weighted by archetype share x build share.

    The approach angles depend only on the build and `n_angles`, not on the
    seeds, so a hold-out set needs `angle_offset` (e.g. half an angle step)
    to face sides the search never saw; the seed alone changes only the
    skill quantile (seed % 5, one per build and seed: _assign_skill), the
    charge flank (seed % 2) and jitter."""
    from .meta_armies import library

    th_mix = th_mix or ({18: 0.65, 17: 0.35} if mode == "ranked" else {16: 1.0})
    out = []
    for th, tw in th_mix.items():
        for b, w in library(th):
            bid = f"meta:{b['archetype']}-{b['th']}-{b['build']}"
            techs = techniques(b) if techniques_on else [None]
            for k, a in enumerate(angles(n_angles, offset=0.31 * th + 0.07 * len(bid) + angle_offset)):
                for s in seeds:
                    for tech in techs:
                        out.append(Scenario(bid, th, a, s * n_angles + k, tw * w / (n_angles * len(seeds) * len(techs)), modifier, group=s, charge=tech))
    return _assign_skill(out)


def with_modifier(scenarios, modifier):
    return [replace(sc, modifier=modifier) for sc in scenarios]


def side_scenarios(armies, seeds, share, n_sides=8, charge="Royal Champion", charge_len=25.0):
    """Charge attacks from every side, scored on the base's weakest side:
    each (army, seed) is one full-scout group (see scouted), so the attacker
    takes its best of `n_sides` sides. Royal Champion charge under
    Invisibility with a Recall (how the user plays it). Weights add up to
    `share`, split evenly between the armies."""
    import math as _m

    from .tactics import CHARGE_OPTIONS, DEFAULT, NAMES

    out = []
    g = 5000
    for army, th in armies:
        for s in seeds:
            g += 1
            for k in range(n_sides):
                v = DEFAULT.copy()
                v[0] = 2 * _m.pi * k / n_sides + 0.1
                if charge:
                    v[NAMES.index("charge_pick")] = CHARGE_OPTIONS.index(charge) + 0.5
                    v[NAMES.index("charge_healers")] = 0.5
                    v[NAMES.index("charge_len")] = charge_len
                out.append(Scenario(army, th, float(v[0]), s * n_sides + k, share / (len(armies) * len(seeds) * n_sides), None, g, tuple(map(float, v))))
    return _assign_skill(out)


def adaptive_scenarios(archive, mode, seeds, share, weights=None):
    """Scenarios for tuned attack tactics found against earlier leaders
    (archive: {(army, th): [tactic vec, ...]}). Each (tactic, seed) is its
    own group, so no scouting is applied on top (the tactic already chose its
    side). Weights add up to `share`, split by the meta weights."""
    meta = {"hydra": 0.271, "throwers": 0.260, "edrag": 0.115, "rootrider": 0.097} if mode == "ranked" else         {"hydra": 0.375, "edrag": 0.257, "rootrider": 0.146, "throwers": 0.061}
    if weights:
        meta = weights
    keys = [k for k, v in archive.items() if v]
    tot = sum(meta.get(a, 0.05) for a, _ in keys) or 1.0
    out = []
    g = 1000
    for (army, th) in keys:
        vecs = archive[(army, th)]
        for v in vecs:
            for s in seeds:
                g += 1
                out.append(Scenario(army, th, float(v[0]), s, share * meta.get(army, 0.05) / tot / (len(vecs) * len(seeds)), None, g, tuple(map(float, v))))
    return out


def blend(scripted, adaptive, share):
    """Scripted scenarios scaled to 1 - share, plus the adaptive ones."""
    if not adaptive:
        return list(scripted)
    w = sum(sc.weight for sc in scripted) or 1.0
    return [replace(sc, weight=sc.weight / w * (1 - share))
            for sc in scripted] + list(adaptive)


def war_scenarios(n_angles=8, seeds=(0,), angle_offset=0.0):
    """TH16 attackers (war/CWL is mostly same-TH), TH16 same-TH meta weights."""
    mix = {("hydra", 16): 0.375, ("edrag", 16): 0.257, ("rootrider", 16): 0.146, ("throwers", 16): 0.061}
    tot = sum(mix.values())
    out = []
    for (army, th), w in mix.items():
        for k, a in enumerate(angles(n_angles, offset=0.29 * len(army) + angle_offset)):
            for s in seeds:
                out.append(Scenario(army, th, a, s * n_angles + k, w / tot / (n_angles * len(seeds)), group=s))
    return _assign_skill(out)


@dataclass
class Evaluation:
    ranked_trophies: float  # expected defender trophies per ranked defense
    three_star_rate: float
    avg_stars: float
    avg_destruction: float
    th_kill_rate: float
    per_army: dict
    worst_side: dict

    def summary(self) -> str:
        return (
            f"def trophies {self.ranked_trophies:5.1f}/40 | 3* {self.three_star_rate:5.1%} | "
            f"avg {self.avg_stars:.2f}* {self.avg_destruction:5.1f}% | TH killed {self.th_kill_rate:5.1%}"
        )


def evaluate(layout: Layout, scenarios, *, strength=None, parallel=True) -> Evaluation:
    strength = strength or STRENGTH
    if os.environ.get("BASELAB_REDTEAM") == "1":
        # opt-in: playbook armies attack with their red-team best attack
        # (redteam.py, docs/REDTEAM.md); a few hundred battles per army
        from .redteam import redteam_rows

        rt_sc, rt_r, scenarios, _found = redteam_rows(layout, scenarios, strength)
        lj = layout.to_json()
        jobs = [(lj, sc, strength.get(sc.army, 1.0)) for sc in scenarios]
        results = run_batch(jobs, parallel=parallel) if jobs else []
        return summarise(rt_sc + list(scenarios), rt_r + [tuple(r) for r in results])
    lj = layout.to_json()
    jobs = [(lj, sc, strength.get(sc.army, 1.0)) for sc in scenarios]
    results = run_batch(jobs, parallel=parallel)
    ev = summarise(scenarios, results)
    _log_eval(lj, scenarios, results, ev)
    return ev


def _log_eval(lj, scenarios, results, ev):
    """Training data for a learned score predictor (surrogate): with
    BASELAB_EVAL_LOG set, every evaluated layout and its battle results are
    appended as one JSON line."""
    path = os.environ.get("BASELAB_EVAL_LOG")
    if not path:
        return
    import json

    row = {
        "layout": lj,
        "summary": [ev.ranked_trophies, ev.three_star_rate, ev.avg_stars, ev.avg_destruction, ev.th_kill_rate],
        "battles": [[sc.army, sc.town_hall, round(sc.angle, 3), sc.seed, sc.weight, sc.modifier, r[0], r[1], r[2]] for sc, r in zip(scenarios, results)],
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + chr(10))


def scouted(scenarios, results, scout=None):
    """Expected outcome when the attacker scouts `scout` random sides and
    picks the best one: every combination of that many angles within a
    group, weighted equally. Returns (scenario, result, weight) rows."""
    import itertools

    scout = SCOUT if scout is None else scout
    if scout <= 1:
        return [(sc, r, sc.weight) for sc, r in zip(scenarios, results)]
    groups: dict = {}
    for sc, r in zip(scenarios, results):
        groups.setdefault((sc.army, sc.town_hall, sc.modifier, sc.group), []).append((sc, r))
    out = []
    for rows in groups.values():
        wg = sum(sc.weight for sc, _ in rows)
        # groups from 5000 up are "full scout" attackers: they look at every side
        # and take the best, so the defender is scored on its weakest side
        # sides are scouted; on each scouted side the attacker also picks the
        # best of its techniques (scripted plan or a hero charge)
        sides: dict = {}
        for row in rows:
            sides.setdefault(round(row[0].angle, 6), []).append(row)
        sides_l = list(sides.values())
        k = len(sides_l) if rows[0][0].group >= 5000 else min(scout, len(sides_l))
        combos = list(itertools.combinations(sides_l, k))
        for combo in combos:
            sc, r = max((x for side in combo for x in side), key=lambda x: (attacker_trophies(x[1][0], x[1][1]), x[1][1]))
            out.append((sc, r, wg / len(combos)))
    return out


def summarise(scenarios, results, scout=None) -> Evaluation:
    rows = scouted(scenarios, results, scout)
    scenarios = [sc for sc, _r, _w in rows]
    results = [r for _sc, r, _w in rows]
    weights = [w for _sc, _r, w in rows]
    W = sum(weights)
    troph = three = stars = pct = thk = 0.0
    per_army: dict = {}
    worst: dict = {}
    for sc, (s, p, th, _t), w0 in zip(scenarios, results, weights):
        w = w0 / W
        troph += w * defender_trophies(s, p)
        three += w * (s >= 3)
        stars += w * s
        pct += w * p
        thk += w * th
        key = f"{sc.army}@TH{sc.town_hall}"
        a = per_army.setdefault(key, {"n": 0, "stars": 0.0, "pct": 0.0, "three": 0.0, "troph": 0.0})
        a["n"] += w0
        a["stars"] += w0 * s
        a["pct"] += w0 * p
        a["three"] += w0 * (s >= 3)
        a["troph"] += w0 * defender_trophies(s, p)
        cur = worst.get(key)
        if cur is None or (s, p) > (cur[0], cur[1]):
            worst[key] = (s, p, round(sc.angle, 2))
    for a in per_army.values():
        n = a.pop("n")
        for k in a:
            a[k] = round(a[k] / n, 3)
    return Evaluation(troph, three, stars, pct, thk, per_army, worst)
