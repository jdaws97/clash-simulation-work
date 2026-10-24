"""Run many battles in parallel and turn them into base scores.

Scoring follows the real ranked rules (docs/RESEARCH-2026-10.md): the defender
earns ``40 - attacker_trophies``. For war the score is the probability of
*not* conceding three stars, with stars and destruction as tie-breakers.
"""

from __future__ import annotations

import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace

from .layout import Layout


# docs/GOAL.md:5: judge selected layouts on battles outside their search.
# Group IDs become 5 * (group * n_angles + side) + skill, so check RNG seeds too.
VALIDATION_SEED_GROUPS = range(8, 10)
HOLDOUT_SEED_GROUPS = range(21, 24)  # evolve_bases.py and qd_search.py hold-outs
FINAL_SEED_GROUPS = range(101, 104)  # beyond validation and funnel/qd selection


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
        # docs/SIM_ACCURACY.md: round 8 is the measured calibration checkpoint.
        m = Path(
            os.environ.get("BASELAB_CALIBRATION")
            or Path(__file__).resolve().parents[2] / "data" / "meta-calibration-r8.json"
        )
        # skip entries without a strength (notes, metadata) instead of
        # dropping the whole file on the first KeyError
        base.update(
            {
                "meta:" + k: v["strength"]
                for k, v in json.loads(m.read_text()).items()
                if isinstance(v, dict) and "strength" in v
            }
        )
    except (OSError, ValueError, KeyError):
        pass
    # builds decoded from the account's real attackers (data/observed-armies.json)
    # borrow their archetype's calibration: TH16 builds first (calibrated), else
    # any Town Hall's; 1.0 when the archetype has none
    try:
        o = Path(__file__).resolve().parents[2] / "data" / "observed-armies.json"
        data = json.loads(o.read_text(encoding="utf-8"))
        for b in data["builds"] if isinstance(data, dict) else data:
            key = f"meta:{b['archetype']}-{b['th']}-{b['build']}"
            if key in base:
                continue
            fam = [
                v for k, v in base.items() if k.startswith(f"meta:{b['archetype']}-16-")
            ] or [
                v
                for k, v in base.items()
                if k.startswith(f"meta:{b['archetype']}-") and not k.startswith(key)
            ]
            base[key] = sum(fam) / len(fam) if fam else 1.0
    except (OSError, ValueError, KeyError):
        pass
    # new strategies (data/custom-armies.json) borrow their family's calibration
    try:
        c = Path(__file__).resolve().parents[2] / "data" / "custom-armies.json"
        for b in json.loads(c.read_text(encoding="utf-8"))["builds"]:
            fam = [
                v
                for k, v in base.items()
                if k.startswith(f"meta:{b.get('family')}-16-")
            ]
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
        # Wiki: Ranked Battles, 16 at 50%, +1 per 3% above 50%, 32 at 98%.
        return 16 + max(0, int((pct - 50) // 3))
    if stars == 1:
        # Wiki: Ranked Battles, "A 1% 1-star will earn 5 trophies, with one
        # trophy awarded for every 9% earned" (91% -> 15), counted above 1%
        # like the 2-star rule counts above 50%.
        return min(15, 5 + int(max(0.0, pct - 1) // 9))
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
    tactic: tuple | None = (
        None  # adaptive-attacker knobs (tactics.py); sets the side too
    )
    charge: tuple | None = (
        None  # (hero, healers): the build is played as a hero charge (Invisibility + Recall)
    )
    # Bug hunt r2-d #7: full scouting is independent of the seed/group number.
    full_scout: bool = False


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
            out.append(
                (hero, min(healers, int(build.get("troops", {}).get("Healer", 0))))
            )
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


def group_seed(j: int, s: int, k: int, n: int) -> int:
    """Seed of side k (of n) in group j (equal-weight groups, e.g. one build
    against several bases): the quantile cycles through SKILL_ORDER."""
    return 5 * (s * n + k) + SKILL_ORDER[j % len(SKILL_ORDER)]


def _assign_skill(scenarios):
    """Scenario seeds come in as m = s * n_sides + k; each scouting group
    is replayed at every quantile q with seed 5 * m + q and weight / 5.
    Sides and techniques share a quantile only within their own group."""
    # Bug hunt r2-d #1: balance all five quantiles within every army and seed.
    out = []
    for sc in scenarios:
        for q in range(len(_Z)):
            out.append(
                replace(
                    sc,
                    seed=len(_Z) * sc.seed + q,
                    group=len(_Z) * sc.group + q,
                    weight=sc.weight / len(_Z),
                )
            )
    return out


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
    r = Battle(
        layout, plan, seed=sc.seed, town_hall=layout.town_hall, modifier=sc.modifier
    ).run()
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
    """jobs: list of (layout_json, Scenario, strength). Returns result tuples.
    BASELAB_ENGINE=rust runs them in the Rust engine (rust_bridge.py)."""
    if os.environ.get("BASELAB_ENGINE") == "rust":
        from .rust_bridge import run_batch as rust_batch

        return rust_batch(jobs, threads=None if parallel else 1)
    if not parallel or len(jobs) < 4:
        return [_run_one(j) for j in jobs]
    return list(
        pool().map(
            _run_one, jobs, chunksize=max(1, len(jobs) // (4 * (os.cpu_count() or 2)))
        )
    )


def angles(n: int, offset: float = 0.0):
    return [offset + 2 * math.pi * k / n for k in range(n)]


def ranked_scenarios(n_angles=8, seeds=(0,), mix=None, angle_offset=0.0):
    """Legacy scripted TH17/TH18 mix, normalized to unit total weight.

    optimize_base.py, final_eval.py and the guided A/B probes still use this;
    ranked evolution uses meta_scenarios() and the observed opponent mix.
    """
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
    tot = sum(mix.values())
    out = []
    for (army, th), w in mix.items():
        for k, a in enumerate(
            angles(n_angles, offset=0.37 * th + 0.11 * len(army) + angle_offset)
        ):
            for s in seeds:
                out.append(
                    Scenario(
                        army,
                        th,
                        a,
                        s * n_angles + k,
                        w / tot / (n_angles * len(seeds)),
                        group=s,
                    )
                )
    return _assign_skill(out)


def target_scenarios(town_hall: int, n_angles=8, seeds=(0,), modifier=None):
    """Same-TH attackers against a TH17/TH18 base, weighted by the TH18
    ranked meta shares (TrophyCoach); used to build strong attack targets."""
    mix = {"hydra": 0.271, "throwers": 0.260, "edrag": 0.115, "rootrider": 0.097}
    tot = sum(mix.values())
    out = []
    for army, w in mix.items():
        for k, a in enumerate(
            angles(n_angles, offset=0.23 * len(army) + 0.1 * town_hall)
        ):
            for s in seeds:
                out.append(
                    Scenario(
                        army,
                        town_hall,
                        a,
                        s * n_angles + k,
                        w / tot / (n_angles * len(seeds)),
                        modifier,
                        group=s,
                    )
                )
    return _assign_skill(out)


META_MIX_INFO = {}
_META_MIX_PRINTED = False


def _meta_th_mix(mode, th_mix):
    from .meta_armies import ranked_observations

    if th_mix is not None:
        mix, source = dict(th_mix), "th_mix argument"
    elif mode != "ranked":
        mix, source = {16: 1.0}, "same-TH war"
    elif "BASELAB_TH_MIX" in os.environ:
        mix = {}
        source = "BASELAB_TH_MIX"
        try:
            for item in os.environ[source].split(","):
                key, value = item.split(":")
                th = int(key)
                if th in mix:
                    raise ValueError("duplicate Town Hall")
                mix[th] = float(value)
        except ValueError as exc:
            raise ValueError("BASELAB_TH_MIX must look like '16:0.3,17:0.7'") from exc
    else:
        observed = ranked_observations()
        if observed["available"]:
            # data/live/battles.jsonl: fold TH <=16 / >=18, then add one per TH.
            counts = observed["th_counts"]
            mix = {th: count + 1 for th, count in counts.items()}
            source = "ranked defenses + one per TH"
        else:
            mix, source = {18: 0.65, 17: 0.35}, "default (battle log missing)"
    if not mix:
        raise ValueError("th_mix must contain a positive Town Hall weight")
    for th, weight in mix.items():
        if type(th) is not int or not math.isfinite(weight) or weight < 0:
            raise ValueError(
                "th_mix needs integer Town Halls and finite nonnegative weights"
            )
    total = sum(mix.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("th_mix must have a finite positive total weight")
    return {th: weight / total for th, weight in mix.items() if weight > 0}, source


def _record_meta_mix(mode, th_mix, source, libraries):
    from .meta_armies import family_of, ranked_observations

    global _META_MIX_PRINTED
    observed = ranked_observations() if mode == "ranked" else None
    missing = {}
    if observed is not None:
        for th, builds in libraries.items():
            available = {family_of(b) for b, _ in builds}
            missing[th] = {
                family: count
                for family, count in observed["family_counts"].get(th, {}).items()
                if family not in available
            }
    build_shares = {
        th: {f"{b['archetype']}-{b['th']}-{b['build']}": w for b, w in builds}
        for th, builds in libraries.items()
    }
    META_MIX_INFO.clear()
    META_MIX_INFO.update(
        mode=mode,
        source=source,
        th_mix=dict(th_mix),
        observations=observed,
        build_shares=build_shares,
        missing_families=missing,
        family_mix_rule="add-one families; local weight n/(n+10); renormalize saved families",
    )
    if _META_MIX_PRINTED:
        return
    th_summary = ", ".join(f"TH{th}={w:.1%}" for th, w in th_mix.items())
    build_summary = "; ".join(
        f"TH{th}[" + ", ".join(f"{bid}={w:.1%}" for bid, w in shares.items()) + "]"
        for th, shares in build_shares.items()
    )
    notes = []
    if observed is not None:
        notes.append(f"ranked defense counts={observed['th_counts']}")
        notes.append(f"missing saved families={missing}")
        if any(observed["unclassified"].values()):
            notes.append(f"unclassified={observed['unclassified']}")
        if any(observed["decode_failures"].values()):
            notes.append(f"undecodable={observed['decode_failures']}")
        if observed["invalid_rows"]:
            notes.append(f"invalid log rows={observed['invalid_rows']}")
    details = "; ".join([source, *notes])
    # stderr preserves callers that write JSON results to stdout.
    print(
        f"meta_scenarios({mode}): {th_summary}; builds within TH: {build_summary}; {details}",
        file=sys.stderr,
    )
    _META_MIX_PRINTED = True


MAX_SIDES = 64  # meta_scenarios(budget=...): sides per build and seed stride


def meta_scenarios(
    mode="ranked",
    n_angles=8,
    seeds=(0,),
    modifier=None,
    th_mix=None,
    techniques_on=False,
    angle_offset=0.0,
    budget=None,
):
    """Scenarios from saved meta builds (meta_armies.py). Ranked Town Halls
    use smoothed defense-log counts; BASELAB_TH_MIX overrides the log, and an
    explicit th_mix takes precedence. A missing log retains the 65/35 TH18/17
    default. War uses TH16. META_MIX_INFO records counts and conditional build
    shares for the latest call; the first call prints its mix once to stderr.

    Ranked family shares blend add-one observed counts with the TH18 prior
    (local weight n/(n+10)); only saved families are simulated, renormalized.
    Saved builds keep their relative shares within each family.

    The approach angles depend only on the build and `n_angles`, not on the
    seeds, so a hold-out set needs `angle_offset` (e.g. half an angle step)
    to face sides the search never saw. Every seed covers all five skill
    quantiles (_assign_skill); fresh seeds change the charge flank
    (seed % 2) and jitter.

    budget (battles) gives each build sides in proportion to its weight, at
    least two so best-of-SCOUT stays a choice, instead of n_angles each:
    uniform sides spend most battles on rare builds (effective sample size
    140 of 320; output/speedproof/exp_alloc_decisions.py). Seeds then use
    m = s * MAX_SIDES + k, disjoint from every n_angles set's seeds."""
    from .meta_armies import library

    th_mix, source = _meta_th_mix(mode, th_mix)
    libraries = {}
    for th in th_mix:
        libraries[th] = library(th, ranked=mode == "ranked")
        if not libraries[th]:
            raise ValueError(f"no saved meta builds for attacker TH{th}")
    from .meta_armies import PLAYBOOK_FAMILY, _playbook, playbooks_on

    if playbooks_on():
        # Cited playbooks only (the Rust engine runs PlaybookPlan, not the
        # scripted AttackPlan): builds whose family has no playbook are left
        # out and their weight goes to the Town Hall's other builds.
        for th, builds in libraries.items():
            kept = [
                (b, w)
                for b, w in builds
                if PLAYBOOK_FAMILY.get(b["archetype"])
                and _playbook(PLAYBOOK_FAMILY[b["archetype"]]) is not None
            ]
            dropped = sorted({b["archetype"] for b, _ in builds} - {b["archetype"] for b, _ in kept})
            if dropped:
                META_MIX_INFO.setdefault("no_playbook", {})[th] = dropped
                print(f"meta_scenarios: TH{th} without a cited playbook, left out: {', '.join(dropped)}", file=sys.stderr)
            if kept:
                total = sum(w for _, w in kept)
                libraries[th] = [(b, w / total) for b, w in kept]
    out = []
    stride = n_angles
    if budget is not None:
        stride = MAX_SIDES
        units = budget / (len(_Z) * len(seeds))
    for th, tw in th_mix.items():
        for b, w in libraries[th]:
            bid = f"meta:{b['archetype']}-{b['th']}-{b['build']}"
            techs = techniques(b) if techniques_on else [None]
            sides = n_angles
            if budget is not None:
                sides = min(MAX_SIDES, max(SCOUT, round(units * tw * w / len(techs))))
            for k, a in enumerate(
                angles(sides, offset=0.31 * th + 0.07 * len(bid) + angle_offset)
            ):
                for s in seeds:
                    for tech in techs:
                        out.append(
                            Scenario(
                                bid,
                                th,
                                a,
                                s * stride + k,
                                tw * w / (sides * len(seeds) * len(techs)),
                                modifier,
                                group=s,
                                charge=tech,
                            )
                        )
    _record_meta_mix(mode, th_mix, source, libraries)
    return _assign_skill(out)


def with_modifier(scenarios, modifier):
    return [replace(sc, modifier=modifier) for sc in scenarios]


def side_scenarios(
    armies, seeds, share, n_sides=8, charge="Royal Champion", charge_len=25.0
):
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
                # Bug hunt r2-d #7: preserve this caller's inspect-every-side rule.
                out.append(
                    Scenario(
                        army,
                        th,
                        float(v[0]),
                        s * n_sides + k,
                        share / (len(armies) * len(seeds) * n_sides),
                        None,
                        g,
                        tuple(map(float, v)),
                        full_scout=True,
                    )
                )
    return _assign_skill(out)


def adaptive_scenarios(archive, mode, seeds, share, weights=None):
    """Scenarios for tuned attack tactics found against earlier leaders
    (archive: {(army, th): [tactic vec, ...]}). Each (tactic, seed) is its
    own group, so no scouting is applied on top (the tactic already chose its
    side). Weights add up to `share`, split by the meta weights."""
    meta = (
        {"hydra": 0.271, "throwers": 0.260, "edrag": 0.115, "rootrider": 0.097}
        if mode == "ranked"
        else {"hydra": 0.375, "edrag": 0.257, "rootrider": 0.146, "throwers": 0.061}
    )
    if weights:
        meta = weights
    keys = [k for k, v in archive.items() if v]
    tot = sum(meta.get(a, 0.05) for a, _ in keys) or 1.0
    out = []
    g = 1000
    for army, th in keys:
        vecs = archive[(army, th)]
        for v in vecs:
            for s in seeds:
                g += 1
                out.append(
                    Scenario(
                        army,
                        th,
                        float(v[0]),
                        s,
                        share * meta.get(army, 0.05) / tot / (len(vecs) * len(seeds)),
                        None,
                        g,
                        tuple(map(float, v)),
                    )
                )
    # Bug hunt r2-d #4: search and validation use the same five skill quantiles.
    return _assign_skill(out)


def blend(scripted, adaptive, share):
    """Scripted scenarios scaled to 1 - share, plus the adaptive ones."""
    if not adaptive:
        return list(scripted)
    w = sum(sc.weight for sc in scripted) or 1.0
    return [replace(sc, weight=sc.weight / w * (1 - share)) for sc in scripted] + list(
        adaptive
    )


def war_scenarios(n_angles=8, seeds=(0,), angle_offset=0.0):
    """TH16 attackers (war/CWL is mostly same-TH), TH16 same-TH meta weights."""
    mix = {
        ("hydra", 16): 0.375,
        ("edrag", 16): 0.257,
        ("rootrider", 16): 0.146,
        ("throwers", 16): 0.061,
    }
    tot = sum(mix.values())
    out = []
    for (army, th), w in mix.items():
        for k, a in enumerate(angles(n_angles, offset=0.29 * len(army) + angle_offset)):
            for s in seeds:
                out.append(
                    Scenario(
                        army,
                        th,
                        a,
                        s * n_angles + k,
                        w / tot / (n_angles * len(seeds)),
                        group=s,
                    )
                )
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


def evaluate(
    layout: Layout, scenarios, *, strength=None, parallel=True, mode="ranked"
) -> Evaluation:
    strength = strength or STRENGTH
    if os.environ.get("BASELAB_REDTEAM") == "1":
        # opt-in: playbook armies attack with their red-team best attack
        # (redteam.py, docs/REDTEAM.md); a few hundred battles per army
        from .redteam import redteam_rows

        # the red team picks its attack by this mode's objective (war: 3 stars first)
        rt_sc, rt_r, scenarios, _found = redteam_rows(
            layout, scenarios, strength, mode=mode
        )
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
        "summary": [
            ev.ranked_trophies,
            ev.three_star_rate,
            ev.avg_stars,
            ev.avg_destruction,
            ev.th_kill_rate,
        ],
        "battles": [
            [
                sc.army,
                sc.town_hall,
                round(sc.angle, 3),
                sc.seed,
                sc.weight,
                sc.modifier,
                r[0],
                r[1],
                r[2],
            ]
            for sc, r in zip(scenarios, results)
        ],
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
        groups.setdefault(
            (sc.army, sc.town_hall, sc.modifier, sc.group, sc.full_scout), []
        ).append((sc, r))
    out = []
    for rows in groups.values():
        wg = sum(sc.weight for sc, _ in rows)
        # Bug hunt r2-d #7: only explicit full-scout attackers inspect every side.
        # sides are scouted; on each scouted side the attacker also picks the
        # best of its techniques (scripted plan or a hero charge)
        sides: dict = {}
        for row in rows:
            sides.setdefault(round(row[0].angle, 6), []).append(row)
        sides_l = list(sides.values())
        k = len(sides_l) if rows[0][0].full_scout else min(scout, len(sides_l))
        combos = list(itertools.combinations(sides_l, k))
        for combo in combos:
            sc, r = max(
                (x for side in combo for x in side),
                key=lambda x: (attacker_trophies(x[1][0], x[1][1]), x[1][1]),
            )
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
        a = per_army.setdefault(
            key, {"n": 0, "stars": 0.0, "pct": 0.0, "three": 0.0, "troph": 0.0}
        )
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
