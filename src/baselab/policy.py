"""Learned attacker policy: values for the brain's decision thresholds
(engine/plans.py POLICY), trained across many bases.

The active policy lives in data/attacker-policy.json (absent = the
hand-written defaults). evaluate.py and tactics.py apply it to every plan.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from .engine.plans import POLICY
from .evaluate import STRENGTH, skill
from .layout import Layout

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = ROOT / "data" / "attacker-policy.json"
NAMES = list(POLICY)
LO = np.array([POLICY[k][1] for k in NAMES])
HI = np.array([POLICY[k][2] for k in NAMES])
DEFAULT = np.array([POLICY[k][0] for k in NAMES])


def to_dict(vec) -> dict:
    return {k: float(v) for k, v in zip(NAMES, vec)}


def to_vec(d: dict) -> np.ndarray:
    return np.array([float(d.get(k, POLICY[k][0])) for k in NAMES])


@lru_cache(maxsize=1)
def active() -> dict:
    """The adopted policy (per army when trained that way: {"*": {...}, "hydra": {...}})."""
    if ACTIVE.exists():
        return json.loads(ACTIVE.read_text())
    return {}


def for_army(army: str) -> dict:
    a = {k: v for k, v in active().items() if not k.startswith("_")}
    return dict(a.get(army) or a.get("*") or {})


def run_job(args):
    """One battle with an explicit policy dict. args: (layout_json, army,
    attacker TH, angle, seed, policy dict)."""
    lj, army, th, angle, seed, pol = args
    from .engine.battle import Battle
    from .meta_armies import make_plan

    lay = Layout.from_json(lj)
    plan = make_plan(army, angle, th, seed)
    plan.pol = {**plan.pol, **pol}  # on top of the adopted policy (real builds carry it)
    plan.strength = STRENGTH.get(army, 1.0) * skill(seed)
    r = Battle(lay, plan, seed=seed, town_hall=lay.town_hall).run()
    return r.stars, r.destruction
