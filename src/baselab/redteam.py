"""Red team: the best way a scouting player attacks one base with one army.

Scouting (evaluate.scouted, tools/baselab/playbook_check.py) lets the
attacker pick the best of a few fixed sides. Real players read the base
more closely: an exact entry, where the Queen's Giant Arrow goes, which
defense the Rocket Balloons snipe, when to start the main push. A base
search scored against the fixed script finds bases that only beat the
script, so this module searches the choices a player has *inside the
army's cited playbook* (data/playbooks/<family>.json) and nothing else:

  angle         entry side, 16 sides then +-11.25 degrees around the best
  charge side   which flank opens the charge (left / right)
  flank_offset  how far the flanks sit from the main entry (0.6 / 0.9 / 1.2 rad)
  step anchors  a step that targets a building (`building:<key>`, `th`,
                `threat:main`) may target any building that some playbook
                step with the same action and unit/spell targets
                (e.g. Rocket Balloons on at / mortar / ad / bt / xbow)
  ability aim   Giant Arrow and Fireball targets named by the playbooks'
                steps or base-reading rules (READING below, quote-checked
                against the playbook JSON at load)
  timing        the wait before the main push (0.5x / 1x / 1.5x the
                measured median gap, docs/SIM_ACCURACY.md check 6) and the
                Invisibility cadence on a charging hero (both 4 s and 10 s
                are cited)

No new actions or troop uses are introduced. Search (Budget):
  1. coarse     16 sides x 2 flanks on 5 seeds (common random numbers)
  2. halving    best 8 get 10 seeds, best 3 get 20 seeds
  3. refine     one coordinate-descent pass from the best: every single
                change above, screened on the first 5 seeds; a change that
                beats the incumbent there by > `min_gain` is replayed on
                all 20 search seeds and kept only if it still wins there
  4. fresh      the pick replayed on 10 unseen seeds (no winner's curse);
                this is the number reported and scored
Refinement stops early when the coarse winner already three-stars every
search seed, and when `max_battles` would be exceeded.

Seeds map to the five attacker-skill quantiles (evaluate.skill), so every
5 consecutive seeds cover all skills once. Score: expected attacker
trophies (evaluate.attacker_trophies), ties broken by destruction.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

from .evaluate import STRENGTH, attacker_trophies, pool, skill

ROOT = Path(__file__).resolve().parents[2]

# seeds: each block of 5 covers the 5 skill quantiles (seed % 5) once
SEARCH_SEEDS = tuple(range(1000, 1020))
FRESH_SEEDS = tuple(range(5000, 5020))

# Ability targets cited by the playbooks' base-reading rules (family, words
# that must appear in one of that playbook's base_reading rules). Checked
# at load: a target whose rule is not found is dropped.
READING = {
    "Giant Arrow": {
        "ad": ("electro-dragon", "Align the opening Giant Arrow through two Air Defenses"),
        "sweeper": ("electro-dragon", "Use Giant Arrow to remove Air Sweepers"),
        "cc": ("super-minion-air", "Giant Arrow line through valuable defenses, especially the Clan Castle"),
        "revenge": ("super-minion-air", "especially the Clan Castle, Revenge Tower or Monolith"),
        "mono": ("super-minion-air", "especially the Clan Castle, Revenge Tower or Monolith"),
        "st": ("root-rider", "Use Giant Arrow during the Queen's funnel to trigger Invisibility Spell Towers"),
    },
    # "Choose the Fireball area for both funnel pathing and clustered
    # defensive value" (druid-ruin-witch), "the target varies with the
    # layout" (super-minion-air): the heavy defenses (plans.THREAT >= 5)
    "Fireball": {
        **{k: ("druid-ruin-witch", "Choose the Fireball area for both funnel pathing and clustered defensive value")
           for k in ("inferno", "scatter", "eagle", "xbow", "mono", "mgt", "swt")},
    },
}


@dataclass(frozen=True)
class Attack:
    angle: float
    side: str = "left"
    flank_offset: float = 0.9
    overrides: tuple = ()  # ((step id, field, value), ...) sorted

    def with_override(self, sid, fld, value):
        o = {(a, b): c for a, b, c in self.overrides}
        o[(sid, fld)] = value
        return replace(self, overrides=tuple(sorted(((a, b, c) for (a, b), c in o.items()), key=lambda x: (x[0], x[1]))))

    def override_dict(self):
        out: dict = {}
        for sid, fld, v in self.overrides:
            out.setdefault(sid, {})[fld] = v
        return out

    def describe(self):
        d = {"angle_deg": round(math.degrees(self.angle) % 360, 1), "charge_side": self.side,
             "flank_offset": self.flank_offset}
        if self.overrides:
            d["steps"] = {f"{s}.{f}": v for s, f, v in self.overrides}
        return d


@dataclass
class Budget:
    sides: int = 16
    coarse_seeds: int = 5
    halving: tuple = ((8, 10), (3, 20))  # (keep, seeds) per round
    refine_seeds: int = 5  # screening seeds for each single change
    min_gain: float = 0.5  # trophies a change must add to be kept
    fresh_seeds: int = 10
    max_battles: int = 500  # hard cap on search battles (fresh replay not counted)


@dataclass
class RedTeamResult:
    army: str
    attack: Attack
    search_trophies: float  # on the search seeds (optimistic: it was picked there)
    fresh_trophies: float  # on unseen seeds: the honest estimate
    fresh: list  # [(stars, pct, th destroyed, time)] per fresh seed (evaluate.run_batch order)
    coarse_best: Attack
    battles: int
    seconds: float
    log: list = field(default_factory=list)
    sides: dict = field(default_factory=dict)  # coarse: angle deg -> best-flank trophies

    @property
    def three_star(self):
        return sum(r[0] >= 3 for r in self.fresh) / len(self.fresh)

    @property
    def pct(self):
        return sum(r[1] for r in self.fresh) / len(self.fresh)


# ----------------------------------------------------------------- plans
def _build(army):
    from .meta_armies import build_by_id

    return build_by_id(army[5:] if army.startswith("meta:") else army)


def playbook_for(army):
    from .meta_armies import _playbook, family_of

    fam = family_of(_build(army))
    return fam, (_playbook(fam) if fam else None)


def make_attack_plan(army: str, attack: Attack, seed: int):
    from .engine.playbook import from_playbook

    build = _build(army)
    _fam, pb = playbook_for(army)
    if pb is None:
        raise ValueError(f"{army}: no cited playbook")
    return from_playbook(pb, angle=attack.angle, seed=seed, th=build["th"], build=build,
                         flank_offset=attack.flank_offset, charge_side=attack.side,
                         overrides=attack.override_dict())


def _run(job):
    lj, army, attack, seed, strength, modifier = job
    from .engine.battle import Battle
    from .layout import Layout

    lay = Layout.from_json(lj)
    plan = make_attack_plan(army, attack, seed)
    plan.strength = strength * skill(seed)
    r = Battle(lay, plan, seed=seed, town_hall=lay.town_hall, modifier=modifier).run()
    return (r.stars, r.destruction, r.th_destroyed, r.time)


# ------------------------------------------------------------ the choices
@lru_cache(maxsize=1)
def _cited_anchors():
    """(action, what) -> every building/th/threat:main anchor some playbook
    step (or variant step) uses for it."""
    out: dict = {}
    for f in sorted((ROOT / "data" / "playbooks").glob("*.json")):
        if f.stem.startswith("test-"):
            continue
        pb = json.loads(f.read_text(encoding="utf-8"))
        steps = list(pb["steps"]) + [s for v in pb.get("variants", []) for s in v.get("steps", [])]
        for s in steps:
            at = str(s.get("at", ""))
            if at.startswith("building:") or at in ("th", "threat:main"):
                out.setdefault((s["action"], s.get("what")), set()).add(at)
            if s["action"] == "ability" and str(s.get("aim", "")).startswith("building:"):
                out.setdefault(("aim", s.get("what")), set()).add(s["aim"])
    return out


@lru_cache(maxsize=1)
def _reading_targets():
    """READING with every rule verified in its playbook's base_reading."""
    from .meta_armies import _playbook

    ok: dict = {}
    for equip, rows in READING.items():
        for key, (fam, words) in rows.items():
            pb = _playbook(fam) or {}
            rules = [str(r.get("rule", r)) if isinstance(r, dict) else str(r) for r in pb.get("base_reading", [])]
            if any(words in r for r in rules):
                ok.setdefault(equip, set()).add("building:" + key)
    return ok


def _repeats_cited(what):
    out = set()
    for f in sorted((ROOT / "data" / "playbooks").glob("*.json")):
        if f.stem.startswith("test-"):
            continue
        pb = json.loads(f.read_text(encoding="utf-8"))
        for s in list(pb["steps"]) + [s for v in pb.get("variants", []) for s in v.get("steps", [])]:
            if s.get("what") == what and s.get("every"):
                out.add(float(s["every"]))
    return out


def step_knobs(army: str, keys: set) -> list:
    """[(step id, field, [alternative values])] for this army's fitted
    playbook on a base with building `keys`. The step's current value is
    not listed (the incumbent already has it)."""
    plan = make_attack_plan(army, Attack(0.0), 0)
    present = {"th", "threat:main"} | {"building:" + k for k in keys}
    cited = _cited_anchors()
    reading = _reading_targets()
    knobs = []
    for st in plan.steps:
        if st.get("uncited"):
            continue
        act, what, at = st["action"], st.get("what"), str(st.get("at", ""))
        if act in ("deploy", "spell") and (at.startswith("building:") or at in ("th", "threat:main")):
            alts = sorted((cited.get((act, what), set()) & present) - {at})
            if alts:
                knobs.append((st["id"], "at", alts))
        if act == "ability":
            lo = plan.loadouts.get(what)
            equip = set(lo.equipment) if lo is not None else set()
            cur = st.get("aim")
            # only heroes carrying an aimable equipment piece get choices:
            # targets cited by a step for this hero plus the base-reading
            # targets for the equipment it carries
            cands = set()
            if equip & {"Giant Arrow", "Fireball"}:
                cands = set(cited.get(("aim", what), set()))
                for e in ("Giant Arrow", "Fireball"):
                    if e in equip:
                        cands |= reading.get(e, set())
            alts = sorted((cands & present) - {cur})
            if alts:
                knobs.append((st["id"], "aim", alts + ([None] if cur else [])))
        if st.get("every") and act == "spell":
            # Invisibility on a hero: the 10 s cycle is cited only with a
            # Spirit Fox covering the gaps (from_playbook), so a hero without
            # one keeps the 4 s chain
            hero = at.split(":", 1)[1] if ":" in at else None
            lo = plan.loadouts.get(hero) if hero else None
            if what != "Invisibility Spell" or (lo is not None and lo.pet == "Spirit Fox"):
                alts = sorted(_repeats_cited(what) - {float(st["every"])})
                if alts:
                    knobs.append((st["id"], "every", alts))
    # the wait before the main push: the first cited main-army deploy that
    # follows another step after a measured gap (top level or in "all")
    for st in plan.steps:
        w = st.get("when") or {}
        if st["action"] != "deploy" or st.get("uncited") or st.get("at", "edge:main") != "edge:main" \
                or st.get("what") in ("Archer", "Minion") or not isinstance(w, dict):
            continue
        parts = [w] if "after" in w else [x for x in w.get("all", []) if isinstance(x, dict) and "after" in x]
        d = max((float(x.get("delay", 0.0)) for x in parts), default=0.0)
        if d > 0:
            knobs.append((st["id"], "delay", [round(0.5 * d, 2), round(1.5 * d, 2)]))
            break
    return knobs


# ----------------------------------------------------------------- search
class _Evaluator:
    """Caches (attack, seed) -> result and counts battles."""

    def __init__(self, lj, army, strength, parallel=True, modifier=None):
        self.lj, self.army, self.strength, self.parallel, self.modifier = lj, army, strength, parallel, modifier
        self.cache: dict = {}
        self.battles = 0

    def run(self, attacks, seeds):
        todo = [(a, s) for a in attacks for s in seeds if (a, s) not in self.cache]
        todo = list(dict.fromkeys(todo))
        if todo:
            jobs = [(self.lj, self.army, a, s, self.strength, self.modifier) for a, s in todo]
            if self.parallel and len(jobs) > 1:
                res = list(pool().map(_run, jobs, chunksize=1))
            else:
                res = [_run(j) for j in jobs]
            self.cache.update(zip(todo, res))
            self.battles += len(todo)

    def score(self, attack, seeds):
        rs = [self.cache[(attack, s)] for s in seeds]
        return (sum(attacker_trophies(r[0], r[1]) for r in rs) / len(rs), sum(r[1] for r in rs) / len(rs))


def redteam(layout, army: str, budget: Budget | None = None, *, parallel=True, verbose=False,
            modifier=None, strength=None) -> RedTeamResult:
    """The best attack (by expected attacker trophies) the army's cited
    playbook allows against `layout`, with its fresh-seed replay."""
    b = budget or Budget()
    t0 = time.time()
    lj = layout.to_json()
    ev = _Evaluator(lj, army, (strength or STRENGTH).get(army, 1.0), parallel, modifier)
    log = []

    def note(msg):
        log.append(msg)
        if verbose:
            print(f"  [{army}] {msg}", flush=True)

    # 1-2. coarse sides and flanks, then successive halving on seeds
    cands = [Attack(2 * math.pi * k / b.sides + 0.1, side) for k in range(b.sides) for side in ("left", "right")]
    seeds = SEARCH_SEEDS[: b.coarse_seeds]
    ev.run(cands, seeds)
    sides = {}  # entry angle (deg) -> best-flank trophies on the coarse seeds
    for a in cands:
        k = round(math.degrees(a.angle) % 360, 1)
        sides[k] = max(sides.get(k, 0.0), ev.score(a, seeds)[0])
    for keep, n in b.halving:
        cands = sorted(cands, key=lambda a: ev.score(a, seeds), reverse=True)[:keep]
        seeds = SEARCH_SEEDS[:n]
        ev.run(cands, seeds)
    cands = sorted(cands, key=lambda a: ev.score(a, seeds), reverse=True)
    coarse = cands[0]
    note(f"coarse {coarse.describe()} {ev.score(coarse, seeds)[0]:.1f} tr on {len(seeds)} seeds ({ev.battles} battles)")

    # 3. one coordinate-descent pass over the playbook's choices
    rseeds = SEARCH_SEEDS[: b.refine_seeds]
    keys = {bb.key for bb in layout.buildings}
    half = math.pi / b.sides
    best = coarse
    final_seeds = SEARCH_SEEDS[: max([n for _k, n in b.halving] + [b.coarse_seeds])]
    ev.run([best], rseeds + final_seeds)
    groups = [("angle", [best.angle - half, best.angle + half]),
              ("flank_offset", [x for x in (0.6, 1.2) if x != best.flank_offset])]
    groups += [((sid, fld), alts) for sid, fld, alts in step_knobs(army, keys)]
    if ev.score(coarse, seeds)[0] >= attacker_trophies(3, 100):
        note("three stars on every search seed: nothing to refine")
        groups = []
    for name, alts in groups:
        if ev.battles + len(alts) * len(rseeds) + len(final_seeds) > b.max_battles:
            note(f"budget reached before {name}")
            break
        if name == "angle":
            trial = [replace(best, angle=a) for a in alts]
        elif name == "flank_offset":
            trial = [replace(best, flank_offset=x) for x in alts]
        else:
            trial = [best.with_override(name[0], name[1], v) for v in alts]
        ev.run(trial, rseeds)
        top = max(trial, key=lambda a: ev.score(a, rseeds))
        if ev.score(top, rseeds)[0] - ev.score(best, rseeds)[0] <= b.min_gain:
            continue
        ev.run([top], final_seeds)
        gain = ev.score(top, final_seeds)[0] - ev.score(best, final_seeds)[0]
        if gain > b.min_gain:
            note(f"{name}: +{gain:.1f} tr on {len(final_seeds)} seeds -> {top.describe()}")
            best = top
        else:
            note(f"{name}: screened +, but {gain:+.1f} tr on {len(final_seeds)} seeds; not kept")
    search_tr = ev.score(best, final_seeds)[0]
    n_search = ev.battles

    # 4. fresh seeds
    fs = FRESH_SEEDS[: b.fresh_seeds]
    ev.run([best], fs)
    fresh = [ev.cache[(best, s)] for s in fs]
    fresh_tr = sum(attacker_trophies(r[0], r[1]) for r in fresh) / len(fresh)
    note(f"pick {best.describe()} search {search_tr:.1f} fresh {fresh_tr:.1f} tr ({n_search} search battles)")
    return RedTeamResult(army, best, search_tr, fresh_tr, fresh, coarse, ev.battles, time.time() - t0, log, sides)


def evaluate_redteam(layout, armies, budget: Budget | None = None, *, verbose=False, modifier=None):
    """Base score against red-team attackers, for a base search to call.
    `armies`: [(army id, weight)], each with a cited playbook. Returns
    (Evaluation, {army: RedTeamResult}); the Evaluation is summarise() over
    the fresh-seed battles of each army's best attack."""
    from .evaluate import Scenario, summarise

    scs = [Scenario(a, _build(a)["th"], 0.0, 0, w, modifier) for a, w in armies]
    sc, res, rest, found = redteam_rows(layout, scs, budget=budget, verbose=verbose)
    if rest:
        raise ValueError(f"no cited playbook for {[s.army for s in rest]}")
    return summarise(sc, res), {k[0]: r for k, r in found.items()}


# ------------------------------------------- opt-in mode for evaluate()
def budget_from_env() -> Budget:
    """BASELAB_REDTEAM_BATTLES caps the search battles per base and army."""
    import os

    b = Budget()
    if os.environ.get("BASELAB_REDTEAM_BATTLES"):
        b.max_battles = int(os.environ["BASELAB_REDTEAM_BATTLES"])
    return b


def redteam_rows(layout, scenarios, strength=None, budget: Budget | None = None, verbose=False):
    """BASELAB_REDTEAM=1 in evaluate.evaluate(): every scenario army with a
    cited playbook is replaced by its red-team attack. Its total scenario
    weight (per army, Town Hall and league modifier) is spread over the
    fresh-seed battles of the best attack, each in its own scouting group so
    summarise() takes them as they are (hero-charge techniques and tuned
    tactics of those armies are absorbed: the red team plays the playbook).
    Returns (scenarios, results) for those rows, the scenarios left for the
    normal path (armies without a playbook) and {(army, th, modifier):
    RedTeamResult}."""
    keyed: dict = {}
    rest = []
    for sc in scenarios:
        if sc.army.startswith(("meta:", "custom:")) and playbook_for(sc.army)[1] is not None:
            keyed.setdefault((sc.army, sc.town_hall, sc.modifier), [sc, 0.0])[1] += sc.weight
        else:
            rest.append(sc)
    out_sc, out_r, found = [], [], {}
    g = 900000
    for key, (sc0, w) in keyed.items():
        r = redteam(layout, key[0], budget or budget_from_env(), modifier=key[2], strength=strength, verbose=verbose)
        found[key] = r
        for seed, res in zip(FRESH_SEEDS, r.fresh):
            g += 1
            out_sc.append(replace(sc0, angle=r.attack.angle, seed=seed, weight=w / len(r.fresh), group=g,
                                  tactic=None, charge=None))
            out_r.append(res)
    return out_sc, out_r, rest, found
