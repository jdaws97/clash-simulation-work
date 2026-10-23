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
(archetype share split across the saved builds within the archetype).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from .engine import stats
from .engine.heroes import DEFAULT_LOADOUTS, HEROES
from .engine.plans import SPELL_NAMES, AttackPlan, Wave

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "meta-armies-2026-10-15.json"
CUSTOM = (
    ROOT / "data" / "custom-armies.json"
)  # new strategies to test (ids "custom:<name>")
BATTLES = ROOT / "data" / "live" / "battles.jsonl"
FAMILY_PRIOR_BATTLES = 10.0
SPELL_KEYS = {v: k for k, v in SPELL_NAMES.items()}
SIEGES = {
    "Log Launcher",
    "Sky Wagon",
    "Siege Barracks",
    "Troop Launcher",
    "Stone Slammer",
    "Battle Blimp",
    "Wall Wrecker",
    "Battle Drill",
    "Flame Flinger",
}
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
    bulk = (
        max(
            troops.items(),
            key=lambda kv: kv[1] * max(1, int(stats.attrs(kv[0]).get("housing") or 1)),
        )[0]
        if troops
        else None
    )
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
    air = sum(
        c * int(stats.attrs(n).get("housing") or 1) for n, c in main if _flying(n)
    ) > 0.5 * sum(c * int(stats.attrs(n).get("housing") or 1) for n, c in main)
    lightning = spells.get("lightning", 0)
    plan = AttackPlan(
        angle=angle,
        town_hall=th,
        seed=seed,
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
        main_min=10.0 if air else 8.0,
        main_max=20.0 if air else 18.0,
    )
    plan.build_id = f"{build['archetype']}-{build['th']}-{build['build']}"
    # a siege from the Clan Castle is a reinforcement, not the attacker's own
    # (Monolith counts only the own siege: battle.deploy)
    plan.siege_donated = bool(siege) and siege not in build["troops"]
    if build.get("own_levels") or build["archetype"].startswith("user-"):
        # the user's own armies attack at the account's live levels
        # (data/your-levels.json, from the API), not the Town Hall max
        own = user_levels()
        plan.hero_levels = dict(own.get("hero_levels", {}))
        attack = own.get("attack_levels", {})
        # spells are cast at their own researched levels (AttackPlan reads
        # spell_levels; troop_levels never reached the spells)
        plan.spell_levels = {n: l for n, l in attack.items() if n in SPELL_KEYS}
        plan.troop_levels = {
            n: l
            for n, l in attack.items()
            if n not in SPELL_KEYS and not (plan.siege_donated and n == siege)
        }  # a donated siege is the donor's
        plan.equipment_levels = dict(own.get("equipment_levels", {}))
        plan.pet_levels = dict(own.get("pet_levels", {}))
        # the account's Clan Castle caps donated spell levels (wiki: Clan Castle)
        buildings = own.get("levels", {})
        for attr, key in (
            ("clan_castle_level", "cc"),
            ("laboratory_level", "lab"),
            ("dark_spell_factory_level", "dsf"),
            ("spell_factory_level", "sf"),
        ):
            if isinstance(buildings.get(key), int):
                setattr(plan, attr, buildings[key])
    from .policy import for_army

    plan.pol = {
        **for_army(build["archetype"]),
        **build.get("pol", {}),
    }  # adopted policy + per-army plays
    return plan


_USER = None


def user_levels() -> dict:
    global _USER
    if _USER is None:
        _USER = json.loads(
            (
                Path(__file__).resolve().parents[2] / "data" / "your-levels.json"
            ).read_text()
        )
    return _USER


def _loadouts(build, heroes):
    from .loadouts import HeroLoadout

    out = {h: DEFAULT_LOADOUTS[h] for h in heroes if h in DEFAULT_LOADOUTS}
    for h, spec in (build.get("loadouts") or {}).items():
        out[h] = HeroLoadout(h, tuple(spec[:2]), spec[2] if len(spec) > 2 else None)
    return out


# Army archetype -> playbook family (data/playbooks/<family>.json, compiled
# from quote-checked video transcripts; docs/playbook-consolidation.md).
PLAYBOOK_FAMILY = {
    "root-rider": "root-rider",
    "user-rr": "root-rider",
    "mass-thrower": "thrower",
    "mass-dragons": "dragon",
    "e-drag-spam": "electro-dragon",
    "super-bowler-smash": "super-bowler",
    "mass-super-yeti": "yeti",
    "mass-meteor-golem": "meteor-golem",
    "user-air": "super-minion-air",
    "user-druid-ruin": "druid-ruin-witch",
    "mass-dragon-rider": "dragon-rider",
    "mass-super-dragon": "super-dragon",
}


@lru_cache(maxsize=None)
def _playbook(family: str):
    p = Path(__file__).resolve().parents[2] / "data" / "playbooks" / f"{family}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def playbooks_on() -> bool:
    import os

    return os.environ.get("BASELAB_PLAYBOOKS") == "1"


# Signature order for decoded armies; data/meta-armies-2026-10-15.json's
# Root Rider builds can contain mostly Throwers. Hydra stays in dragon.
TROOP_FAMILY = (
    ("Root Rider", "root-rider"),
    ("Thrower", "thrower"),
    ("Electro Dragon", "electro-dragon"),
    ("Super Bowler", "super-bowler"),
    ("Meteor Golem", "meteor-golem"),
    ("Super Yeti", "yeti"),
    ("Yeti", "yeti"),
    ("Ruin Witch", "druid-ruin-witch"),
    ("Super Minion", "super-minion-air"),
    ("Lava Hound", "lavaloon"),
    ("Dragon", "dragon"),
    # data/live/battles.jsonl also contains unsaved ground families.
    ("Witch", "witch"),
    ("Electro Titan", "electro-titan"),
    ("P.E.K.K.A", "pekka"),
    ("Super Dragon", "super-dragon"),
    ("Dragon Rider", "dragon-rider"),
)


def family_of(build: dict):
    fam = PLAYBOOK_FAMILY.get(build["archetype"])
    if fam:
        return fam
    troops = build.get("troops", {})
    for troop, f in TROOP_FAMILY:
        if troops.get(troop, 0) >= 2:
            return f
    return None


def plan_for_build(build: dict, angle: float, seed: int):
    """The attack plan for a build: its family's cited playbook when
    BASELAB_PLAYBOOKS=1 and one exists, otherwise the scripted compose()."""
    family = family_of(build) if playbooks_on() else None
    pb = _playbook(family) if family else None
    if pb is not None:
        from .engine.playbook import from_playbook

        # the charge flank alternates with the seed (the player's choice per base)
        return from_playbook(
            pb,
            angle=angle,
            seed=seed,
            th=build["th"],
            build=build,
            charge_side="left" if seed % 2 == 0 else "right",
        )
    return compose(build, angle=angle, seed=seed)


def make_plan(army: str, angle: float, th: int, seed: int):
    """A plan for a scenario army: "meta:<archetype>-<th>-<build>" is a real
    build, anything else one of the scripted engine/plans.py armies."""
    if army.startswith("meta:") or army.startswith("custom:"):
        build = build_by_id(army[5:] if army.startswith("meta:") else army)
        return plan_for_build(build, angle, seed)
    from .engine.plans import ARMIES

    return ARMIES[army](angle=angle, town_hall=th, seed=seed)


@lru_cache(maxsize=1)
def _share_troop_names():
    from .gamedata import raw

    # tools/baselab/decode_battlelog.py:15-29: troop share IDs omit 4000000.
    return {t["_id"] - 4000000: t["name"] for t in raw()["troops"]}


def _share_troops(code: str) -> dict:
    # tools/baselab/decode_battlelog.py:39,62-70; only camp troops set family.
    sections = dict(re.findall(r"([hiuds])([^hiuds]*)", code))
    troops = Counter()
    for part in sections.get("u", "").split("-"):
        match = re.fullmatch(r"([1-9]\d*)x(\d+)", part)
        if match is None:
            raise ValueError("missing or malformed camp troops")
        count, index = map(int, match.groups())
        name = _share_troop_names().get(index)
        if name is None:
            raise ValueError(f"unknown troop share ID {index}")
        troops[name] += count
    return dict(troops)


@lru_cache(maxsize=1)
def ranked_observations() -> dict:
    """One run's ranked-defense counts; never retain names, tags or share codes."""
    result = {
        "available": False,
        "th_counts": {th: 0 for th in (16, 17, 18)},
        "family_counts": {th: {} for th in (16, 17, 18)},
        "unclassified": {th: 0 for th in (16, 17, 18)},
        "decode_failures": {th: 0 for th in (16, 17, 18)},
        "invalid_rows": 0,
    }
    try:
        handle = BATTLES.open(encoding="utf-8")
    except FileNotFoundError:
        return result
    result["available"] = True
    with handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                battle = json.loads(line)
            except ValueError:
                result["invalid_rows"] += 1
                continue
            if not isinstance(battle, dict):
                result["invalid_rows"] += 1
                continue
            if (
                battle.get("battleType") != "ranked"
                or battle.get("attack") is not False
            ):
                continue
            th = battle.get("opponentTownHallLevel")
            if type(th) is not int or th < 1:
                result["invalid_rows"] += 1
                continue
            # docs/GAP_ANALYSIS.md:16-21: ranked defenses, not own attacks.
            th = min(18, max(16, th))
            result["th_counts"][th] += 1
            try:
                troops = _share_troops(battle.get("armyShareCode") or "")
            except (TypeError, ValueError):
                result["decode_failures"][th] += 1
                continue
            family = family_of({"archetype": "observed", "troops": troops})
            if family is None:
                result["unclassified"][th] += 1
                continue
            counts = result["family_counts"][th]
            counts[family] = counts.get(family, 0) + 1
    return result


def ranked_family_shares(th: int) -> dict:
    """Add-one local shares mixed with TH18; local weight is n / (n + 10).

    n counts decoded, classified defenses at this TH. Smooth over the union
    of TH18-prior and locally observed families before masking absent builds.
    """
    prior = Counter()
    for archetype, values in data()["archetype_share_th18"].items():
        prior[PLAYBOOK_FAMILY.get(archetype, archetype)] += values[0]
    total = sum(prior.values())
    prior = {family: weight / total for family, weight in prior.items()}
    counts = ranked_observations()["family_counts"].get(th, {})
    n = sum(counts.values())
    local_weight = n / (n + FAMILY_PRIOR_BATTLES)
    families = sorted(prior.keys() | counts.keys())
    return {
        family: (1 - local_weight) * prior.get(family, 0.0)
        + local_weight * (counts.get(family, 0) + 1) / (n + len(families))
        for family in families
    }


def library(th: int, *, ranked: bool = False):
    """[(build, weight)] for one TH; ranked=True uses observed family shares.

    Unavailable families are omitted and the available mass is renormalized;
    evaluate.META_MIX_INFO reports observed families without saved builds.
    """
    d = data()
    rows = [b for b in d["builds"] if b["th"] == th]
    share = d["archetype_share_th18"]
    # data/meta-armies-2026-10-15.json: build.share is within its archetype.
    coverage = {}
    for b in rows:
        archetype = b["archetype"]
        coverage[archetype] = coverage.get(archetype, 0.0) + b["share"]
    w = [
        share.get(b["archetype"], [0.02])[0] * b["share"] / coverage[b["archetype"]]
        for b in rows
    ]
    if ranked:
        shares = ranked_family_shares(th)
        coverage = Counter()
        for b, weight in zip(rows, w):
            coverage[family_of(b)] += weight
        w = [
            shares[family_of(b)] * weight / coverage[family_of(b)]
            for b, weight in zip(rows, w)
        ]
    tot = sum(w) or 1.0
    return [(b, x / tot) for b, x in zip(rows, w)]


@lru_cache(maxsize=1)
def custom():
    return (
        json.loads(CUSTOM.read_text(encoding="utf-8"))
        if CUSTOM.exists()
        else {"builds": []}
    )


def build_by_id(bid: str) -> dict:
    if bid.startswith("custom:"):
        return next(b for b in custom()["builds"] if b["archetype"] == bid[7:])
    for b in data()["builds"]:
        if f"{b['archetype']}-{b['th']}-{b['build']}" == bid:
            return b
    raise KeyError(bid)
