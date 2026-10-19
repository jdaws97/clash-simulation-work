"""Rank attack armies for the user's own account (live API levels).

Every candidate army runs at the user's real troop, spell, hero, equipment
and pet levels (profiles/private/api-player.json). Equipment the user does
not own is swapped for their best owned piece for that hero. Targets are the
human TH16 reference bases plus generated TH17 bases, which is what a TH16
meets in ranked. Strength uses the calibrated per-family attacker skill;
families without their own calibration borrow the closest one (flagged).

Usage: python tools/baselab/recommend_armies.py [--angles 6] [--th17 5]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.engine import stats  # noqa: E402
from baselab.engine.plans import ARMIES, AttackPlan, Wave  # noqa: E402
import itertools  # noqa: E402

from baselab.evaluate import SCOUT, STRENGTH, angles, attacker_trophies, skill  # noqa: E402
from baselab.generator import build, random_blueprint  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.loadouts import HeroLoadout as L  # noqa: E402

API = ROOT / "profiles" / "private" / "api-player.json"

# Super troops report level 1 in the API when not boosted; they follow their
# base troop (super level = cap - (base cap - base level)).
SUPER_BASE = {
    "Super Barbarian": "Barbarian", "Super Archer": "Archer", "Super Wall Breaker": "Wall Breaker", "Super Giant": "Giant",
    "Sneaky Goblin": "Goblin", "Super Miner": "Miner", "Rocket Balloon": "Balloon", "Inferno Dragon": "Baby Dragon",
    "Super Valkyrie": "Valkyrie", "Super Witch": "Witch", "Ice Hound": "Lava Hound", "Super Bowler": "Bowler",
    "Super Dragon": "Dragon", "Super Wizard": "Wizard", "Super Minion": "Minion", "Super Hog Rider": "Hog Rider",
    "Super Yeti": "Yeti",
}


def account(th=16):
    d = json.loads(API.read_text(encoding="utf-8"))
    lv = {}
    for sec in ("heroes", "heroEquipment", "troops", "spells"):
        for x in d.get(sec, []):
            if x.get("village", "home") == "home" and x["name"] in stats.registry():
                lv[x["name"]] = x["level"]
    for sup, base in SUPER_BASE.items():
        if sup in stats.registry() and base in lv:
            cap_s, cap_b = stats.max_level(sup, th), stats.max_level(base, th)
            if cap_s and cap_b:
                lv[sup] = max(1, min(cap_s, cap_s - (cap_b - lv[base])))
    return lv


def owned_equipment(lv):
    by_hero: dict = {}
    for n, r in stats.registry().items():
        if r["kind"] == "equipment" and n in lv:
            hero = r["attrs"].get("raw", {}).get("User")
            by_hero.setdefault(hero, []).append((lv[n], n))
    return {h: [n for _, n in sorted(v, reverse=True)] for h, v in by_hero.items()}


def personalise(plan: AttackPlan, lv: dict) -> AttackPlan:
    owned = owned_equipment(lv)
    plan.troop_levels = {n: v for n, v in lv.items() if stats.record(n)["kind"] in ("troop", "super_troop", "siege")}
    plan.spell_levels = {n: v for n, v in lv.items() if stats.record(n)["kind"] == "spell"}
    plan.hero_levels = {n: v for n, v in lv.items() if stats.record(n)["kind"] == "hero"}
    plan.pet_levels = {n: v for n, v in lv.items() if stats.record(n)["kind"] == "pet"}
    plan.equipment_levels = {n: v for n, v in lv.items() if stats.record(n)["kind"] == "equipment"}
    fixed = {}
    used_pets = set()
    for hero, lo in plan.loadouts.items():
        eq = [e for e in lo.equipment if e in lv]
        for e in owned.get(hero, []):
            if len(eq) >= 2:
                break
            if e not in eq:
                eq.append(e)
        pet = lo.pet if lo.pet in lv and lo.pet not in used_pets else None
        if pet is None:
            spare = sorted((v, n) for n, v in plan.pet_levels.items() if n not in used_pets)
            pet = spare[-1][1] if spare else None
        used_pets.add(pet)
        fixed[hero] = L(hero, tuple(eq[:2]), pet)
    plan.loadouts = fixed
    return plan


def user_rocket_minion(angle=0.0, town_hall=16, seed=0) -> AttackPlan:
    """The user's Super Minion / Rocket Balloon / Druid army (2* 70-89%)."""
    return AttackPlan(
        angle=angle, town_hall=town_hall, seed=seed, label="Rocket Balloons + Super Minions (your army)",
        funnel_heroes=[("Barbarian King", -6.0), ("Dragon Duke", 6.0)],
        flank=[("Rocket Balloon", 8, 0.0), ("Balloon", 2, 3.0)],
        main=[Wave("main", [("Ice Golem", 1), ("Super Minion", 5), ("Furnace", 2), ("Druid", 1), ("Wizard", 3), ("Headhunter", 3)], spread=3.0)],
        support=[Wave("main", [("Healer", 5)], spread=1.0)],
        push_heroes=["Archer Queen", "Grand Warden"],
        cleanup=[("Minion", 3), ("Archer", 3)],
        breakers=[("Wall Breaker", 5)],
        siege="Log Launcher",
        cc_troops=["Ice Golem", "Super Yeti"],
        spells={"invis": 3, "eq": 5, "recall": 1, "totem": 1},
        cc_spells={"iceblock": 1, "totem": 1, "poison": 1},
        loadouts={
            "Barbarian King": L("Barbarian King", ("Spiky Ball", "Stick Horse"), "Phoenix"),
            "Archer Queen": L("Archer Queen", ("Giant Arrow", "Action Figure"), "Unicorn"),
            "Grand Warden": L("Grand Warden", ("Rage Gem", "Fireball"), "Electro Owl"),
            "Dragon Duke": L("Dragon Duke", ("Rocket Backpack", "Fire Heart"), "Diggy"),
        },
        main_min=8.0, main_max=18.0,
    )


def user_druid_rr(angle=0.0, town_hall=16, seed=0) -> AttackPlan:
    """The user's Druid / Root Rider / Ruin Witch army (3* 100% twice)."""
    return AttackPlan(
        angle=angle, town_hall=town_hall, seed=seed, label="Root Riders + Druids + Ruin Witches (your army)",
        funnel_heroes=[("Royal Champion", -6.0), ("Dragon Duke", 6.0)],
        flank=[("Rocket Balloon", 6, -4.0)],
        main=[Wave("main", [("Ice Golem", 1), ("Root Rider", 2), ("Valkyrie", 3), ("Super Minion", 3), ("Ruin Witch", 2)], spread=2.0)],
        support=[Wave("main", [("Healer", 5), ("Druid", 2)], spread=1.0)],
        push_heroes=["Archer Queen", "Grand Warden"],
        cleanup=[("Archer", 3)],
        siege="Log Launcher",
        cc_troops=["Ice Golem", "Ice Golem", "Root Rider"],
        spells={"invis": 3, "eq": 2, "freeze": 3, "revive": 1},
        cc_spells={"rage": 1, "freeze": 1},
        loadouts={
            "Royal Champion": L("Royal Champion", ("Electro Boots", "Rocket Spear"), "Spirit Fox"),
            "Dragon Duke": L("Dragon Duke", ("Fire Heart", "Rocket Backpack"), "Phoenix"),
            "Archer Queen": L("Archer Queen", ("Giant Arrow", "Action Figure"), "Unicorn"),
            "Grand Warden": L("Grand Warden", ("Fireball", "Rage Gem"), "Frosty"),
        },
        main_min=8.0, main_max=18.0,
    )


def hydra_portal(angle=0.0, town_hall=16, seed=0) -> AttackPlan:
    """Hydra with the Minion Prince on Portal Pendant: pull the push out of a
    finished side and drop it, healed and hasted, where buildings remain."""
    plan = ARMIES["hydra"](angle=angle, town_hall=town_hall, seed=seed)
    plan.label = "Hydra + Portal Pendant (Minion Prince)"
    plan.loadouts["Minion Prince"] = L("Minion Prince", ("Portal Pendant", "Dark Orb"), "Angry Jelly")
    return plan


def rr_throwers(angle=0.0, town_hall=16, seed=0) -> AttackPlan:
    """New hybrid: Root Riders open walls and tank for a Thrower line."""
    return AttackPlan(
        angle=angle, town_hall=town_hall, seed=seed, label="Root Riders + Throwers (hybrid)",
        funnel_heroes=[("Royal Champion", -6.0), ("Dragon Duke", 6.0)],
        flank=[("Rocket Balloon", 2, -4.0)],
        main=[Wave("main", [("Root Rider", 4), ("Thrower", 8), ("Ice Golem", 1)], spread=2.5)],
        support=[Wave("main", [("Healer", 5)], spread=1.0)],
        push_heroes=["Archer Queen", "Grand Warden"],
        cleanup=[("Minion", 4), ("Archer", 3)],
        siege="Log Launcher",
        cc_troops=["Thrower", "Thrower", "Thrower", "Wall Breaker"],
        spells={"invis": 3, "totem": 2, "freeze": 2, "rage": 1, "revive": 1},
        cc_spells={"totem": 1, "freeze": 2},
        loadouts={
            "Royal Champion": L("Royal Champion", ("Rocket Spear", "Electro Boots"), "Unicorn"),
            "Dragon Duke": L("Dragon Duke", ("Fire Heart", "Rocket Backpack"), "Phoenix"),
            "Archer Queen": L("Archer Queen", ("Healer Puppet", "Giant Arrow"), "Frosty"),
            "Grand Warden": L("Grand Warden", ("Eternal Tome", "Rage Gem"), "Electro Owl"),
        },
        main_min=8.0, main_max=18.0,
    )


CANDIDATES = {
    "rootrider": (ARMIES["rootrider"], "rootrider", False),
    "throwers": (ARMIES["throwers"], "throwers", False),
    "hydra": (ARMIES["hydra"], "hydra", False),
    "edrag": (ARMIES["edrag"], "edrag", False),
    "rocket_minion": (user_rocket_minion, "throwers", True),
    "druid_rr": (user_druid_rr, "rootrider", True),
    "hydra_portal": (hydra_portal, "hydra", True),
    "rr_throwers": (rr_throwers, "throwers", True),
}


def _run(job):
    name, layout_json, angle, seed, k, modifier, craft, ti = job
    from baselab.engine.battle import Battle

    fn = CANDIDATES[name][0]
    plan = personalise(fn(angle=angle, town_hall=16, seed=seed), account(16))
    plan.strength = k * skill(seed)
    lay = Layout.from_json(layout_json)
    r = Battle(lay, plan, seed=seed, town_hall=lay.town_hall, modifier=modifier,
               defense_levels={"crafting": craft} if craft else None).run()
    return name, lay.town_hall, modifier, r.stars, r.destruction, ti


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--angles", type=int, default=6)
    ap.add_argument("--th17", type=int, default=3, help="generated TH17 bases to add when no optimized one exists")
    ap.add_argument("--extra", nargs="*", default=[], help="more layout JSON files to attack (e.g. optimized TH17/18 bases)")
    ap.add_argument("--modifiers", default="none,legend3,legend1")
    ap.add_argument("--armies", default=",".join(CANDIDATES))
    ap.add_argument("--only", action="store_true", help="attack only the --extra layouts")
    ap.add_argument("--crafting-level", type=int, default=0, help="defender's Crafted Defense module level (0 = TH cap)")
    ap.add_argument("--out", default=str(ROOT / "output" / "army-recommendations.json"))
    args = ap.parse_args()
    refs = ROOT / "data" / "reference-bases"
    targets = [] if args.only else [Layout.load(f) for f in sorted(refs.glob("real-*.json")) if f.stem != "real-l4x"]  # real-l4x is the user's own base
    targets += [Layout.load(f) for f in args.extra]
    have = {t.town_hall for t in targets}
    rng = random.Random(17)
    for th in (17, 18):
        if th in have or args.only:
            continue
        for i in range(args.th17):
            bp = random_blueprint(rng, seed=rng.randrange(10**6))
            bp.town_hall = th
            lay = build(bp)
            lay.name = f"gen-th{th}-{i}"
            targets.append(lay)
    mods = [None if m == "none" else m for m in args.modifiers.split(",")]
    names = args.armies.split(",")
    jobs = []
    for name in names:
        k = STRENGTH.get(CANDIDATES[name][1], 1.0)
        for ti, lay in enumerate(targets):
            lj = lay.to_json()
            for j, a in enumerate(angles(args.angles, offset=0.21 * ti)):
                for m in mods:
                    jobs.append((name, lj, a, j + 3 * ti, k, m, args.crafting_level, ti))
    print(f"{len(jobs)} battles over {len(targets)} targets: " + ", ".join(f"{t.name}(TH{t.town_hall})" for t in targets), flush=True)
    with ProcessPoolExecutor() as ex:
        res = list(ex.map(_run, jobs, chunksize=4))
    report = {"targets": [{"name": t.name, "town_hall": t.town_hall} for t in targets], "armies": {}}
    for name in names:
        rows = [r for r in res if r[0] == name]
        out = {}
        for th in sorted({r[1] for r in rows}):
            for m in mods:
                sub = [r for r in rows if r[1] == th and r[2] == m]
                if not sub:
                    continue
                # you scout and attack from the better of SCOUT sides
                picked = []
                for ti in sorted({r[5] for r in sub}):
                    grp = [r for r in sub if r[5] == ti]
                    for combo in itertools.combinations(grp, min(SCOUT, len(grp))):
                        picked.append(max(combo, key=lambda r: (attacker_trophies(r[3], r[4]), r[4])))
                out[f"TH{th}/{m or 'none'}"] = {
                    "three_star": round(sum(r[3] >= 3 for r in picked) / len(picked), 3),
                    "avg_stars": round(sum(r[3] for r in picked) / len(picked), 2),
                    "avg_destruction": round(sum(r[4] for r in picked) / len(picked), 1),
                    "n": len(sub),
                }
        plan = personalise(CANDIDATES[name][0](town_hall=16), account(16))
        report["armies"][name] = {
            "label": plan.label,
            "strength_family": CANDIDATES[name][1],
            "borrowed_calibration": CANDIDATES[name][2],
            "loadouts": {h: {"equipment": list(lo.equipment), "pet": lo.pet} for h, lo in plan.loadouts.items()},
            "housing": plan.housing(),
            "results": out,
        }
        print(name, json.dumps(out), flush=True)
    Path(args.out).write_text(json.dumps(report, indent=1))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
