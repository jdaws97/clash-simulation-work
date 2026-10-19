"""Attack plans built from real meta army builds (data/meta-armies-*.json,
TrophyCoach ranked data: exact compositions with their real 3-star rates).

`compose(build)` turns one build into an AttackPlan by role:
  siege          a siege machine from troops or Clan Castle
  funnel heroes  King / Duke / Champion clear the sides first (2 of them)
  push heroes    the rest (Warden, Queen, Minion Prince) go in with the push
  flank          small Balloon / Baby Dragon / Rocket Balloon groups
  main           the bulk of the army (and Ice Golems, Headhunters, Titans)
  support        Healers and Apprentice Wardens, dropped on the push
  cleanup        Archers, Minions and Barbarians (snipes, distractions, lures)
  breakers       Wall Breakers and Super Wall Breakers
  spells         by key; Lightning is used to zap Air Defenses first
The brain and the learned policy (engine/plans.py) decide everything during
the battle. `library(th)` lists the builds for one Town Hall with weights
(archetype share x build share within the archetype).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .engine import stats
from .engine.heroes import DEFAULT_LOADOUTS, HEROES
from .engine.plans import SPELL_NAMES, AttackPlan, Wave

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "meta-armies-2026-10-15.json"
CUSTOM = ROOT / "data" / "custom-armies.json"  # new strategies to test (ids "custom:<name>")
SPELL_KEYS = {v: k for k, v in SPELL_NAMES.items()}
SIEGES = {"Log Launcher", "Sky Wagon", "Siege Barracks", "Troop Launcher", "Stone Slammer", "Battle Blimp",
          "Wall Wrecker", "Battle Drill", "Flame Flinger"}
SUPPORT = {"Healer", "Apprentice Warden"}
BREAKERS = {"Wall Breaker", "Super Wall Breaker"}
CLEANUP = {"Archer", "Minion", "Barbarian", "Goblin"}
FLANK = {"Balloon", "Baby Dragon", "Rocket Balloon"}
FUNNEL_ORDER = ("Barbarian King", "Dragon Duke", "Royal Champion")


@lru_cache(maxsize=1)
def data():
    return json.loads(DATA.read_text(encoding="utf-8"))


def _flying(name):
    a = stats.attrs(name) if name in stats.registry() else {}
    return bool(a.get("flying") or a.get("is_flying"))


def compose(build: dict, angle: float = 0.0, seed: int = 0) -> AttackPlan:
    th = build["th"]
    troops = dict(build["troops"])
    cc = dict(build.get("cc", {}))
    siege = next((n for n in troops if n in SIEGES), None)
    if siege:
        troops.pop(siege)
    else:
        siege = next((n for n in cc if n in SIEGES), None)
    cc_troops = []
    cc_spells = {}
    for n, c in cc.items():
        if n == siege:
            continue
        if n in SPELL_KEYS:
            cc_spells[SPELL_KEYS[n]] = cc_spells.get(SPELL_KEYS[n], 0) + c
        else:
            cc_troops += [n] * c
    spells = {}
    for n, c in build["spells"].items():
        spells[SPELL_KEYS[n]] = spells.get(SPELL_KEYS[n], 0) + c
    heroes = [h for h in build["heroes"] if h in HEROES]
    funnel = build.get("funnel") or [h for h in FUNNEL_ORDER if h in heroes][:2]
    push = build.get("push") or [h for h in heroes if h not in funnel]
    flank, main, support, cleanup, breakers = [], [], [], [], []
    bulk = max(troops.items(), key=lambda kv: kv[1] * max(1, int(stats.attrs(kv[0]).get("housing") or 1)))[0] if troops else None
    lat = -4.0
    for n, c in troops.items():
        if n in SUPPORT:
            support.append((n, c))
        elif n in BREAKERS:
            breakers.append((n, c))
        elif n in CLEANUP and n != bulk:
            cleanup.append((n, c))
        elif n in FLANK and n != bulk and c <= 6:
            flank.append((n, c, lat))
            lat = -lat
        else:
            main.append((n, c))
    air = sum(c * int(stats.attrs(n).get("housing") or 1) for n, c in main if _flying(n)) > \
        0.5 * sum(c * int(stats.attrs(n).get("housing") or 1) for n, c in main)
    lightning = spells.get("lightning", 0)
    plan = AttackPlan(
        angle=angle, town_hall=th, seed=seed,
        label=f"{build['archetype']} #{build['build']} (TH{th}, real 3* {build['three_star']:.0%})",
        funnel_heroes=[(h, (-6.0 if i == 0 else 6.0)) for i, h in enumerate(funnel)],
        flank=flank,
        main=[Wave("main", main, spread=3.0 if air else 2.5)],
        support=[Wave("main", support, spread=1.0)] if support else [],
        push_heroes=push,
        cleanup=cleanup,
        breakers=breakers,
        siege=siege,
        cc_troops=cc_troops,
        spells=spells,
        cc_spells=cc_spells,
        ground=not air,
        zap_ad=(lightning, 0) if lightning >= 3 else (0, 0),
        loadouts=_loadouts(build, heroes),
        main_min=10.0 if air else 8.0, main_max=20.0 if air else 18.0,
    )
    plan.build_id = f"{build['archetype']}-{build['th']}-{build['build']}"
    if build.get("own_levels") or build["archetype"].startswith("user-"):
        # the user's own armies attack at the account's live levels
        # (data/your-levels.json, from the API), not the Town Hall max
        own = user_levels()
        plan.hero_levels = dict(own.get("hero_levels", {}))
        plan.troop_levels = {n: l for n, l in own.get("attack_levels", {}).items()}
        plan.equipment_levels = dict(own.get("equipment_levels", {}))
        plan.pet_levels = dict(own.get("pet_levels", {}))
    from .policy import for_army

    plan.pol = {**for_army(build["archetype"]), **build.get("pol", {})}  # adopted policy + per-army plays
    return plan


_USER = None


def user_levels() -> dict:
    global _USER
    if _USER is None:
        _USER = json.loads((Path(__file__).resolve().parents[2] / "data" / "your-levels.json").read_text())
    return _USER


def _loadouts(build, heroes):
    from .loadouts import HeroLoadout

    out = {h: DEFAULT_LOADOUTS[h] for h in heroes if h in DEFAULT_LOADOUTS}
    for h, spec in (build.get("loadouts") or {}).items():
        out[h] = HeroLoadout(h, tuple(spec[:2]), spec[2] if len(spec) > 2 else None)
    return out


def make_plan(army: str, angle: float, th: int, seed: int):
    """A plan for a scenario army: "meta:<archetype>-<th>-<build>" is a real
    build, anything else one of the scripted engine/plans.py armies."""
    if army.startswith("meta:"):
        return compose(build_by_id(army[5:]), angle=angle, seed=seed)
    if army.startswith("custom:"):
        return compose(build_by_id(army), angle=angle, seed=seed)
    from .engine.plans import ARMIES

    return ARMIES[army](angle=angle, town_hall=th, seed=seed)


def library(th: int):
    """[(build, weight)] for one attacker Town Hall; weights sum to 1."""
    d = data()
    rows = [b for b in d["builds"] if b["th"] == th]
    share = d["archetype_share_th18"]
    w = [share.get(b["archetype"], [0.02])[0] * b["share"] for b in rows]
    tot = sum(w) or 1.0
    return [(b, x / tot) for b, x in zip(rows, w)]


@lru_cache(maxsize=1)
def custom():
    return json.loads(CUSTOM.read_text(encoding="utf-8")) if CUSTOM.exists() else {"builds": []}


def build_by_id(bid: str) -> dict:
    if bid.startswith("custom:"):
        return next(b for b in custom()["builds"] if b["archetype"] == bid[7:])
    for b in data()["builds"]:
        if f"{b['archetype']}-{b['th']}-{b['build']}" == bid:
            return b
    raise KeyError(bid)
