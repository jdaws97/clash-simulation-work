"""Attack lab: run plan variants against one base and report the outcome,
when key units die (and what killed them), and how spread out the Throwers
get. Used to turn "my heroes and Root Riders die early" into concrete fixes.

Usage: python tools/baselab/attack_lab.py data/reference-bases/real-l1x.json
"""

from __future__ import annotations

import itertools
import json
import math
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from baselab.engine.plans import AttackPlan, Wave  # noqa: E402
from baselab.evaluate import SCOUT, STRENGTH, attacker_trophies, skill  # noqa: E402
from baselab.layout import Layout  # noqa: E402
from baselab.loadouts import HeroLoadout as L  # noqa: E402
from recommend_armies import account, personalise  # noqa: E402

WATCH = ("Dragon Duke", "Royal Champion", "Root Rider")

THROWER_LOADOUTS = {
    "Royal Champion": L("Royal Champion", ("Rocket Spear", "Electro Boots"), "Unicorn"),
    "Dragon Duke": L("Dragon Duke", ("Fire Heart", "Rocket Backpack"), "Phoenix"),
    "Archer Queen": L("Archer Queen", ("Giant Arrow", "Healer Puppet"), "Frosty"),
    "Grand Warden": L("Grand Warden", ("Eternal Tome", "Rage Gem"), "Electro Owl"),
}


def throwers(angle, seed):
    """The user's way: RC and Duke funnel first, Throwers + Healers push."""
    return AttackPlan(
        angle=angle, town_hall=16, seed=seed, label="Throwers (RC + Duke funnel)",
        funnel_heroes=[("Royal Champion", -6.0), ("Dragon Duke", 6.0)],
        flank=[("Balloon", 2, 0.0)],
        main=[Wave("main", [("Ice Golem", 2), ("Furnace", 1), ("Thrower", 11), ("Wizard", 2)], spread=2.5)],
        support=[Wave("main", [("Healer", 5)], spread=1.0)],
        push_heroes=["Archer Queen", "Grand Warden"],
        cleanup=[("Archer", 4)],
        breakers=[("Wall Breaker", 2)],
        siege="Log Launcher",
        cc_troops=["Thrower", "Thrower", "Thrower", "Wall Breaker"],
        spells={"totem": 4, "poison": 1, "freeze": 2, "revive": 2},
        cc_spells={"totem": 1, "freeze": 2},
        loadouts=dict(THROWER_LOADOUTS),
        main_min=8.0, main_max=18.0,
    )


def rr_throwers(angle, seed):
    """The Root Rider + Thrower hybrid as first recommended."""
    return AttackPlan(
        angle=angle, town_hall=16, seed=seed, label="Root Riders + Throwers",
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
        loadouts=dict(THROWER_LOADOUTS),
        main_min=8.0, main_max=18.0,
    )


def variant(name, angle, seed):
    army, _, fix = name.partition(":")
    p = (throwers if army == "throwers" else rr_throwers)(angle, seed)
    if "heroes_with_push" in fix:
        # no early hero funnel: RC and Duke walk in with the push behind the tanks
        p.funnel_heroes = []
        p.flank = [(n, c, -3.0) for n, c, _lat in p.flank]
        p.push_heroes = ["Royal Champion", "Dragon Duke"] + p.push_heroes
        p.main_min, p.main_max = 4.0, 8.0
    if "duke_only_funnel" in fix:
        # Duke funnels one side alone (Royal Rampage), RC goes in with the push
        p.funnel_heroes = [("Dragon Duke", 6.0)]
        p.flank = [(n, c, -6.0) for n, c, _lat in p.flank]
        p.push_heroes = ["Royal Champion"] + p.push_heroes
    if "revenge" in fix:
        p.loadouts["Dragon Duke"] = L("Dragon Duke", ("Revenge Deck", "Fire Heart"), "Phoenix")
    if "tight" in fix:
        p.main = [Wave(w.group, w.units, spread=1.0) for w in p.main]
        p.support = [Wave(w.group, w.units, spread=0.5) for w in p.support]
    if "healers_on_rr" in fix:
        # Healers dropped right on the Root Riders as they land (no 2 s gap)
        p.main = [Wave(w.group, w.units + [u for sw in p.support for u in sw.units], spread=w.spread) for w in p.main]
        p.support = []
    if "freeze_mono" in fix:
        # spend Freezes on the Monolith and Infernos first (they kill RRs and the Duke)
        p.freeze_first = ("mono", "inferno")
        p.spells["freeze"] = p.spells.get("freeze", 0)
    if "warden_first" in fix:
        # Warden leads so his Eternal Tome covers the Root Riders' first contact
        p.push_heroes = ["Grand Warden"] + [h for h in p.push_heroes if h != "Grand Warden"]
        p.main_min = max(p.main_min, 10.0)
    return p


VARIANTS = [
    "throwers:", "throwers:revenge", "throwers:duke_only_funnel,revenge,tight",
    "throwers:duke_only_funnel,revenge,tight,freeze_mono",
    "rr:", "rr:revenge", "rr:freeze_mono", "rr:duke_only_funnel,revenge,tight,healers_on_rr,freeze_mono",
]


def run(job):
    vname, lj, angle, seed, modifier = job
    from baselab.engine.battle import Battle

    plan = personalise(variant(vname, angle, seed), account(16))
    plan.strength = STRENGTH["throwers"] * skill(seed)
    b = Battle(Layout.from_json(lj), plan, seed=seed, town_hall=16, modifier=modifier, record=True)
    killers: dict = {}
    orig = b.hit_unit

    def hit(u, amount, **kw):
        if u.team == "atk" and u.name in WATCH and u.alive:
            src = kw.get("src") or b._src
            d = killers.setdefault(u.name, {})
            d[src] = d.get(src, 0.0) + amount
        return orig(u, amount, **kw)

    b.hit_unit = hit
    spreads = []
    while b.t < b.max_time:
        b.step()
        if b.destroyed_counted >= b.total_counted:
            break
        if b._next_deploy >= len(b.deployments) and not plan.has_pending() and not any(u.alive and u.name != "Totem" for u in b.attackers):
            break
        if plan._phase in ("push", "done") and int(round(b.t * 10)) % 50 == 0:
            th = [u for u in b.attackers if u.alive and u.name == "Thrower"]
            if len(th) >= 3:
                cx = sum(u.x for u in th) / len(th)
                cy = sum(u.y for u in th) / len(th)
                spreads.append(statistics.mean(math.hypot(u.x - cx, u.y - cy) for u in th))
    r = b.result()
    first_death = {}
    rr_deaths = []
    for e in r.log:
        if e[1] == "dies" and e[2] in WATCH:
            first_death.setdefault(e[2], e[0])
            if e[2] == "Root Rider":
                rr_deaths.append(e[0])
    rr_life = statistics.mean(d - plan._main_at for d in rr_deaths) if rr_deaths else None
    top = {h: max(v, key=v.get) for h, v in killers.items()}
    return vname, modifier, seed, r.stars, r.destruction, first_death, top, (statistics.mean(spreads) if spreads else None), rr_life


def summarise(res, v, m):
    rows = [r for r in res if r[0] == v and r[1] == m]
    picked = [max(c, key=lambda r: (attacker_trophies(r[3], r[4]), r[4])) for c in itertools.combinations(rows, SCOUT)]
    out = {
        "three_star": sum(r[3] >= 3 for r in picked) / len(picked),
        "avg_stars": sum(r[3] for r in picked) / len(picked),
        "avg_destruction": sum(r[4] for r in picked) / len(picked),
        "duke_dies_s": statistics.median([r[5].get("Dragon Duke", 180) for r in rows]),
        "rc_dies_s": statistics.median([r[5].get("Royal Champion", 180) for r in rows]),
        "rr_life_after_drop_s": statistics.mean([r[8] for r in rows if r[8] is not None]) if any(r[8] is not None for r in rows) else None,
        "thrower_spread": statistics.mean([r[7] for r in rows if r[7] is not None]) if any(r[7] is not None for r in rows) else None,
    }
    kills: dict = {}
    for r in rows:
        for h, src in r[6].items():
            kills.setdefault(h, {}).setdefault(src, 0)
            kills[h][src] += 1
    out["hit_hardest_by"] = {h: sorted(kv.items(), key=lambda x: -x[1])[:3] for h, kv in kills.items()}
    return out


def main():
    lj = Layout.load(sys.argv[1]).to_json()
    mods = [None, "legend1"]
    jobs = [(v, lj, 6.283 * k / 16 + 0.1, k, m) for v in VARIANTS for m in mods for k in range(16)]
    with ProcessPoolExecutor() as ex:
        res = list(ex.map(run, jobs, chunksize=2))
    report = {}
    for v in VARIANTS:
        for m in mods:
            s = summarise(res, v, m)
            report[f"{v}/{m or 'electro'}"] = s
            rr = f"{s['rr_life_after_drop_s']:.0f}s" if s["rr_life_after_drop_s"] is not None else "-"
            sp = f"{s['thrower_spread']:.1f}" if s["thrower_spread"] is not None else "-"
            print(f"{v:42s} {m or 'electro':8s} 3*={s['three_star']:4.0%} stars={s['avg_stars']:.2f} dest={s['avg_destruction']:4.1f}% "
                  f"Duke dies {s['duke_dies_s']:.0f}s RC dies {s['rc_dies_s']:.0f}s RR live {rr} spread {sp}", flush=True)
            print("      hit hardest by:", s["hit_hardest_by"], flush=True)
    (ROOT / "output" / "attack-lab.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
